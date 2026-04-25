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
state.extensionManage = state.extensionManage || { open: false, name: "" };

async function loadExtensions() {
    const r = await api("GET", "/api/extensions");
    if (!r || !r.ok) return;
    state.extensions = r.extensions || [];
    // Trust the server's per-extension ``restart_pending`` flag as the
    // source of truth. The dict is in-memory on the server and gets
    // wiped on dashboard restart, so a fresh count after restart
    // correctly drops to 0.
    let pending = 0;
    for (const row of state.extensions) {
        if (row.restart_pending) pending += 1;
    }
    state.extensionsPendingRestart = pending;
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
    if (row.installed) {
        const manage = el("button",
            { class: "btn", type: "button" }, "Manage…");
        if (disabled) manage.disabled = true;
        manage.addEventListener("click", () => openExtensionManageModal(row.name));
        wrap.appendChild(manage);
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

function rowByName(name) {
    return (state.extensions || []).find((r) => r.name === name) || null;
}

function openExtensionManageModal(name) {
    state.extensionManage = { open: true, name };
    const modal = document.getElementById("extension-manage-modal");
    if (!modal) return;
    renderManageModal();
    modal.hidden = false;
}

function closeExtensionManageModal() {
    state.extensionManage = { open: false, name: "" };
    const modal = document.getElementById("extension-manage-modal");
    if (modal) modal.hidden = true;
    const errBox = document.getElementById("extension-manage-error");
    if (errBox) { errBox.hidden = true; errBox.textContent = ""; }
    const chk = document.getElementById("extension-manage-remove-state");
    if (chk) chk.checked = false;
    const statusBox = document.getElementById("extension-manage-status");
    if (statusBox) statusBox.textContent = "";
}

function renderManageModal() {
    const name = state.extensionManage.name;
    const row = rowByName(name);
    if (!row) { closeExtensionManageModal(); return; }
    const title = document.getElementById("extension-manage-modal-title");
    if (title) title.textContent = `Manage · ${row.label || row.name}`;
    setText("extension-manage-version", row.version || "—");
    setText("extension-manage-source",
        row.submodule ? `submodule at extensions/${row.name}/`
                      : `clone at extensions/${row.name}/`);
    let stateLabel = "not installed";
    if (row.restart_pending) stateLabel = "enabled · restart pending";
    else if (row.enabled) stateLabel = "enabled";
    else if (row.installed) stateLabel = "installed, disabled";
    setText("extension-manage-state", stateLabel);
    const toggle = document.getElementById("extension-manage-toggle");
    if (toggle) {
        toggle.textContent = row.enabled ? "Disable" : "Enable";
        toggle.className = row.enabled ? "btn" : "btn green";
    }
}

function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
}

function setManageStatus(text) {
    const node = document.getElementById("extension-manage-status");
    if (node) node.textContent = text;
}

function setManageError(stage, msg) {
    const box = document.getElementById("extension-manage-error");
    if (!box) return;
    if (!msg) { box.hidden = true; box.textContent = ""; return; }
    box.hidden = false;
    box.textContent = `${stage || "error"}: ${msg}`;
}

async function manageUpdate() {
    const name = state.extensionManage.name;
    if (!name) return;
    setManageError(null, null);
    setManageStatus("Running git fetch / checkout…");
    const r = await api("POST", "/api/extensions/update", { name });
    if (!r || !r.ok) {
        setManageError((r && r.stage) || "error", (r && r.error) || "update failed");
        setManageStatus("");
        return;
    }
    if (r.changed) {
        state.extensionsBannerDismissed = false;
        setManageStatus(`Updated ${r.from_version || "?"} → ${r.to_version}. Restart to activate.`);
    } else {
        setManageStatus(`Already at ${r.to_version}.`);
    }
    await loadExtensions();
    renderManageModal();
}

async function manageToggle() {
    const name = state.extensionManage.name;
    const row = rowByName(name);
    if (!row) return;
    setManageError(null, null);
    const verb = row.enabled ? "disable" : "enable";
    setManageStatus(`Running ${verb}…`);
    const r = await api("POST", `/api/extensions/${verb}`, { name });
    if (!r || !r.ok) {
        setManageError(verb, (r && r.error) || `${verb} failed`);
        setManageStatus("");
        return;
    }
    state.extensionsBannerDismissed = false;
    setManageStatus(`${verb.charAt(0).toUpperCase() + verb.slice(1)}d. Restart to activate.`);
    await loadExtensions();
    renderManageModal();
}

async function manageUninstall() {
    const name = state.extensionManage.name;
    if (!name) return;
    const chk = document.getElementById("extension-manage-remove-state");
    const removeState = !!(chk && chk.checked);
    let confirmText;
    if (removeState) {
        confirmText = `Uninstall ${name} AND delete its state files under ~/.tmux-browse/? This cannot be undone.`;
    } else {
        confirmText = `Uninstall ${name}? Code will be removed; state files stay.`;
    }
    if (!confirm(confirmText)) return;
    setManageError(null, null);
    setManageStatus("Running uninstall…");
    const r = await api("POST", "/api/extensions/uninstall",
        { name, remove_state: removeState });
    if (!r || !r.ok) {
        setManageError((r && r.stage) || "error", (r && r.error) || "uninstall failed");
        setManageStatus("");
        return;
    }
    state.extensionsBannerDismissed = false;
    const removed = (r.summary && r.summary.state_removed) || [];
    const tail = removeState
        ? ` (${removed.length} state path${removed.length === 1 ? "" : "s"} removed)`
        : "";
    setManageStatus(`Uninstalled${tail}. Restart to drop routes and UI.`);
    await loadExtensions();
    // Row is now "not installed" — just close the modal.
    setTimeout(closeExtensionManageModal, 800);
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
    // Manage modal bindings.
    const closeBtn = document.getElementById("extension-manage-close");
    if (closeBtn) closeBtn.addEventListener("click", closeExtensionManageModal);
    const modal = document.getElementById("extension-manage-modal");
    if (modal) {
        modal.addEventListener("click", (e) => {
            if (e.target === modal) closeExtensionManageModal();
        });
    }
    const updateBtn = document.getElementById("extension-manage-update");
    if (updateBtn) updateBtn.addEventListener("click", manageUpdate);
    const toggleBtn = document.getElementById("extension-manage-toggle");
    if (toggleBtn) toggleBtn.addEventListener("click", manageToggle);
    const uninstallBtn = document.getElementById("extension-manage-uninstall");
    if (uninstallBtn) uninstallBtn.addEventListener("click", manageUninstall);
    loadExtensions();
}

// Run once after the core bootstrap. The init order matters: state.js
// must have set up state.* first. A 0ms timeout is enough to defer past
// the synchronous bundle.
setTimeout(initExtensionsCard, 0);
