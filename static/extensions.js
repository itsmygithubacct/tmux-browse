// extensions.js — Config > Extensions card + restart banner.
//
// Reads /api/extensions (enhanced in E3 with label / description / repo /
// submodule / restart_pending per row), renders one card per catalog
// entry, and drives the install / enable / disable lifecycle. Locked
// dashboards are handled by util.js's api() wrapper — a 403 triggers
// the unlock prompt and replays the request.

state.extensionsPendingRestart = state.extensionsPendingRestart || 0;
state.extensionsBannerDismissed = false;
state.extensionRowBusy = state.extensionRowBusy || {};
state.extensionRowError = state.extensionRowError || {};

async function loadExtensions() {
    const r = await api("GET", "/api/extensions");
    if (!r || !r.ok) return;
    state.extensions = r.extensions || [];
    // If any row comes back with restart_pending=true (server-side
    // memory), reflect that into the banner counter.
    let pending = 0;
    for (const row of state.extensions) {
        if (row.restart_pending) pending += 1;
    }
    if (pending > 0 && state.extensionsPendingRestart === 0) {
        state.extensionsPendingRestart = pending;
    }
    renderExtensionsCard();
    renderRestartBanner();
}

function renderExtensionsCard() {
    const root = document.getElementById("extensions-list");
    if (!root) return;
    root.textContent = "";
    const rows = state.extensions || [];
    if (rows.length === 0) {
        const note = document.createElement("div");
        note.className = "dim";
        note.style.fontSize = "0.82rem";
        note.textContent = "No extensions discovered.";
        root.appendChild(note);
        return;
    }
    for (const row of rows) {
        root.appendChild(renderExtensionRow(row));
    }
}

function renderExtensionRow(row) {
    const busy = state.extensionRowBusy[row.name];
    const err = state.extensionRowError[row.name];
    const card = el("div", { class: "ext-card" });

    const head = el("div", { class: "ext-card-head" },
        el("span", { class: "ext-card-label" }, row.label || row.name));
    head.appendChild(renderExtensionState(row, busy));
    card.appendChild(head);

    if (row.description) {
        card.appendChild(el("div", { class: "ext-card-desc" }, row.description));
    }
    if (err) {
        const errBox = el("div", { class: "ext-card-error" });
        errBox.textContent = `${err.stage || "error"}: ${err.msg || ""}`;
        card.appendChild(errBox);
    }
    card.appendChild(renderExtensionActions(row, busy));
    return card;
}

function renderExtensionState(row, busy) {
    if (busy === "installing") return el("span", { class: "ext-card-state" }, "installing…");
    if (busy === "enabling") return el("span", { class: "ext-card-state" }, "enabling…");
    if (row.last_error || state.extensionRowError[row.name]) {
        return el("span", { class: "ext-card-state error" }, "error");
    }
    if (row.restart_pending) {
        return el("span", { class: "ext-card-state enabled" }, "restart pending");
    }
    if (row.enabled && row.installed) {
        return el("span", { class: "ext-card-state enabled" }, "enabled");
    }
    if (row.installed) {
        return el("span", { class: "ext-card-state installed" }, "installed");
    }
    return el("span", { class: "ext-card-state" }, "not installed");
}

function renderExtensionActions(row, busy) {
    const wrap = el("div", { class: "ext-card-actions" });
    const disabled = !!busy;

    const primary = primaryExtensionAction(row);
    if (primary) {
        const btn = el("button",
            { class: `btn ${primary.color || "green"}`, type: "button" },
            primary.label);
        if (disabled) btn.disabled = true;
        btn.addEventListener("click", primary.action);
        wrap.appendChild(btn);
    }
    if (row.repo) {
        const link = document.createElement("a");
        link.className = "btn";
        link.href = row.repo;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = "View on GitHub ↗";
        wrap.appendChild(link);
    }
    return wrap;
}

function primaryExtensionAction(row) {
    const name = row.name;
    if (row.restart_pending) {
        return {
            label: "Restart to activate",
            color: "green",
            action: () => restartForExtensions(),
        };
    }
    if (!row.installed) {
        return {
            label: "Download and enable",
            color: "green",
            action: () => installExtension(name),
        };
    }
    if (row.installed && !row.enabled) {
        return {
            label: "Enable",
            color: "green",
            action: () => enableExtension(name),
        };
    }
    // installed + enabled + not pending restart: the happy steady state.
    return null;
}

async function installExtension(name) {
    setExtensionBusy(name, "installing");
    const r = await api("POST", "/api/extensions/install", { name });
    clearExtensionBusy(name);
    if (!r || !r.ok) {
        state.extensionRowError[name] = {
            stage: (r && r.stage) || "unknown",
            msg: (r && r.error) || "install failed",
        };
        renderExtensionsCard();
        return;
    }
    delete state.extensionRowError[name];
    state.extensionsPendingRestart = (state.extensionsPendingRestart || 0) + 1;
    state.extensionsBannerDismissed = false;
    await loadExtensions();
}

async function enableExtension(name) {
    setExtensionBusy(name, "enabling");
    const r = await api("POST", "/api/extensions/enable", { name });
    clearExtensionBusy(name);
    if (!r || !r.ok) {
        state.extensionRowError[name] = { stage: "enable", msg: (r && r.error) || "enable failed" };
        renderExtensionsCard();
        return;
    }
    delete state.extensionRowError[name];
    state.extensionsPendingRestart = (state.extensionsPendingRestart || 0) + 1;
    state.extensionsBannerDismissed = false;
    await loadExtensions();
}

function setExtensionBusy(name, kind) {
    state.extensionRowBusy[name] = kind;
    renderExtensionsCard();
}

function clearExtensionBusy(name) {
    delete state.extensionRowBusy[name];
    renderExtensionsCard();
}

function renderRestartBanner() {
    const node = document.getElementById("extensions-restart-banner");
    if (!node) return;
    const pending = state.extensionsPendingRestart || 0;
    const visible = pending > 0 && !state.extensionsBannerDismissed;
    node.hidden = !visible;
    const msg = document.getElementById("extensions-restart-msg");
    if (msg) {
        msg.textContent = pending === 1
            ? "Restart the dashboard to activate the newly enabled extension."
            : `Restart the dashboard to activate ${pending} newly enabled extensions.`;
    }
}

async function restartForExtensions() {
    try {
        await api("POST", "/api/server/restart", {});
    } catch (_) {
        // The request will often never return because the server exits
        // mid-response. That's expected — the page will either reload
        // itself or the user hits refresh.
    }
}

function initExtensionsCard() {
    const restartBtn = document.getElementById("extensions-restart-btn");
    if (restartBtn) restartBtn.addEventListener("click", restartForExtensions);
    const dismissBtn = document.getElementById("extensions-restart-dismiss");
    if (dismissBtn) {
        dismissBtn.addEventListener("click", () => {
            state.extensionsBannerDismissed = true;
            renderRestartBanner();
        });
    }
    loadExtensions();
}

// Run once after the core bootstrap. The init order matters: state.js
// must have set up state.* first. A 0ms timeout is enough to defer past
// the synchronous bundle.
setTimeout(initExtensionsCard, 0);
