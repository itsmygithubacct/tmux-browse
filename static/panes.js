// panes.js — session panes, layout, hot buttons, idle alerts, modals, refresh

async function launchCodingSession(label, cmd) {
    const slug = label.toLowerCase().replace(/[\s-]+/g, "_");
    let name;
    if (state.config.launch_ask_name) {
        name = prompt(`Name the tmux session:`, slug);
        if (!name) return;
        name = name.trim().replace(/\s+/g, "_");
    } else {
        const uid = Date.now().toString(36).slice(-4);
        name = `${slug}_${uid}`;
    }
    const cwd = state.config.launch_cwd || undefined;
    const r = await api("POST", "/api/session/new", { name, cmd, cwd, launch_ttyd: true });
    if (r.ok && r.port) {
        if (state.config.launch_open_tab) {
            window.open(ttydUrl(r.port), "_blank", "noopener");
        }
        await refresh();
    } else if (r.ok) {
        await refresh();
    } else {
        alert(r.error || "launch failed");
    }
}

async function resizePane(session, cols) {
    await api("POST", "/api/session/resize", { session, cols });
    const rec = state.nodes.get(session);
    if (!rec || !rec.iframeWrap) return;
    const cur = rec.iframeWrap.style.height;
    const maxH = "90vh";
    const defaultH = `${state.config.default_ttyd_height_vh || 70}vh`;
    // Toggle: if already at max, go to default; otherwise go to max
    rec.iframeWrap.style.height = cur === maxH ? defaultH : maxH;
}

// Step sizes for the ±W / ±H buttons next to the fit icon. Roughly
// 10 cells of width and 3 cells of height at the default cell metrics
// (7.7 × 17 px) — small enough to feel like fine-tuning, large enough
// that one click is visibly different.
const STEP_PX_W = 80;
const STEP_PX_H = 60;

// Adjust the iframe wrapper's pixel size in one axis, then re-fit
// tmux to the new dimensions. Bottom of the iframe is the only
// edge that can grow vertically without affecting other panes;
// horizontal grow goes beyond the layout row's natural share, which
// is intentional — operators who want a single pane wider can
// override the row's even-share behavior by hand.
function stepIframeSize(session, axis, deltaPx) {
    const rec = state.nodes.get(session);
    if (!rec || !rec.iframeWrap) return;
    const wrap = rec.iframeWrap;
    if (axis === "w") {
        // Anchor to current pixel width before applying delta — without
        // this the very first click loses the percentage-based default.
        const curW = wrap.getBoundingClientRect().width;
        const next = Math.max(160, Math.round(curW + deltaPx));
        wrap.style.width = next + "px";
        wrap.style.maxWidth = "none";  // override layout-row constraints
    } else if (axis === "h") {
        const curH = wrap.getBoundingClientRect().height;
        const next = Math.max(120, Math.round(curH + deltaPx));
        wrap.style.height = next + "px";
    }
    requestAnimationFrame(() => fitTmuxToIframe(session));
}

// Resize the tmux window to match the iframe's actual dimensions so the
// embedded terminal fills its visible area instead of leaving blank
// borders. Used by both the maximize button and the dedicated tmux-
// resize chrome icon.
//
// Cell-size dimensions live in dashboard config (ttyd_cell_width_px /
// ttyd_cell_height_px) so operators on different fonts / browser zoom
// can tune. Defaults match ttyd's default 15px monospace at 1× DPI
// (~7.7 × 17). Math.round (not floor) is intentional — under-fill by
// half a cell is better than the visible blank gutter Math.floor
// produced.
async function fitTmuxToIframe(session) {
    const rec = state.nodes.get(session);
    if (!rec || !rec.iframeWrap || !rec.iframe) return;
    // The iframe's content box gives us the actual pixels available to
    // ttyd's xterm.js. iframeWrap.clientWidth includes padding/borders
    // so prefer iframe.clientWidth when present.
    const w = rec.iframe.clientWidth || rec.iframeWrap.clientWidth;
    const h = rec.iframe.clientHeight || rec.iframeWrap.clientHeight;
    if (!w || !h) return;
    const cellW = Number(state.config.ttyd_cell_width_px) || 7.7;
    const cellH = Number(state.config.ttyd_cell_height_px) || 17;
    const cols = Math.max(20, Math.min(500, Math.round(w / cellW)));
    const rows = Math.max(5, Math.min(200, Math.round(h / cellH)));
    const r = await api("POST", "/api/session/resize", { session, cols, rows });
    const msg = document.getElementById("msg-" + cssId(session));
    if (msg) {
        msg.textContent = r.ok
            ? `tmux ${cols}×${rows} (iframe ${w}×${h}px, cell ${cellW}×${cellH}px)`
            : ("resize error: " + (r.error || "unknown"));
        msg.className = r.ok ? "inline-msg ok" : "inline-msg err";
    }
}

async function launch(session) {
    const msg = document.getElementById("msg-" + cssId(session));
    if (msg) msg.textContent = "starting…";
    const r = await api("POST", "/api/ttyd/start", { session });
    if (!r.ok) {
        if (msg) { msg.textContent = "error: " + (r.error || "unknown"); msg.className = "inline-msg err"; }
        return;
    }
    const url = ttydUrl(r.port);
    const iframe = document.getElementById("iframe-" + cssId(session));
    if (iframe) iframe.src = url;
    if (msg) { msg.textContent = r.already ? "attached" : "launched"; msg.className = "inline-msg ok"; }
    state.openPanes.add(session);
}

const SEND_QUEUE_COOLDOWN_SECONDS = 60;

async function sendToPane(session, inputEl, countEl) {
    const text = inputEl.value.trim();
    if (!text) return;
    const count = Math.max(1, Math.min(99, Number(countEl?.value) || 1));
    const r = await api("POST", "/api/session/type", { session, text });
    if (!r.ok) {
        const msgEl = document.getElementById("msg-" + cssId(session));
        if (msgEl) {
            msgEl.textContent = "send error: " + (r.error || "unknown");
            msgEl.className = "inline-msg err";
        }
        return;
    }
    inputEl.value = "";
    if (count <= 1) return;
    // Repeat sends are queued: each subsequent send waits for the
    // pane to go idle plus a one-minute cooldown, with a re-check of
    // idle right before sending. ``checkSendQueue`` runs on every
    // refresh tick.
    state.sendQueue = state.sendQueue || {};
    state.sendQueue[session] = {
        text,
        remaining: count - 1,
        idleConfirmedAt: 0,  // epoch seconds when current cooldown began
        busy: false,
    };
    if (countEl) countEl.value = "1";
    renderSendQueueStatus(session);
}

// Idle-gated repeat for ``sendToPane``. Walks any pending queues each
// refresh tick and either advances them (idle confirmed → set
// cooldown clock; cooldown elapsed AND still idle → fire next send;
// remaining hits 0 → drop entry) or sits tight.
async function checkSendQueue(rows) {
    state.sendQueue = state.sendQueue || {};
    if (!Object.keys(state.sendQueue).length) return;
    const idleThreshold = state.config.hot_loop_idle_seconds || 5;
    const now = Math.floor(Date.now() / 1000);
    const byName = new Map(rows.map((r) => [r.name, r]));
    for (const [session, entry] of Object.entries(state.sendQueue)) {
        const row = byName.get(session);
        if (!row) {
            delete state.sendQueue[session];
            renderSendQueueStatus(session);
            continue;
        }
        if (entry.busy) continue;
        const idleSecs = row.idle_seconds || 0;
        if (idleSecs < idleThreshold) {
            // Pane went active again — restart the cooldown clock so
            // the next send waits a fresh minute.
            entry.idleConfirmedAt = 0;
            renderSendQueueStatus(session);
            continue;
        }
        if (!entry.idleConfirmedAt) {
            entry.idleConfirmedAt = now;
            renderSendQueueStatus(session);
            continue;
        }
        if (now - entry.idleConfirmedAt < SEND_QUEUE_COOLDOWN_SECONDS) {
            renderSendQueueStatus(session);
            continue;
        }
        // Re-check idle one more time right before sending.
        if (idleSecs < idleThreshold) continue;
        entry.busy = true;
        try {
            const r = await api("POST", "/api/session/type",
                                { session, text: entry.text });
            if (!r.ok) {
                const msgEl = document.getElementById("msg-" + cssId(session));
                if (msgEl) {
                    msgEl.textContent = "queued send error: " + (r.error || "unknown");
                    msgEl.className = "inline-msg err";
                }
                delete state.sendQueue[session];
                renderSendQueueStatus(session);
                continue;
            }
            entry.remaining = Math.max(0, entry.remaining - 1);
            entry.idleConfirmedAt = 0;
            if (entry.remaining === 0) {
                delete state.sendQueue[session];
            }
        } finally {
            entry.busy = false;
        }
        renderSendQueueStatus(session);
    }
}

function renderSendQueueStatus(session) {
    const rec = state.nodes.get(session);
    if (!rec || !rec.sendStatus) return;
    const entry = (state.sendQueue || {})[session];
    if (!entry) {
        rec.sendStatus.textContent = "";
        return;
    }
    if (entry.busy) {
        rec.sendStatus.textContent = `sending… (${entry.remaining} more queued)`;
    } else if (!entry.idleConfirmedAt) {
        rec.sendStatus.textContent = `${entry.remaining} more queued · waiting for idle`;
    } else {
        const left = Math.max(0,
            SEND_QUEUE_COOLDOWN_SECONDS - (Math.floor(Date.now() / 1000) - entry.idleConfirmedAt));
        rec.sendStatus.textContent = `${entry.remaining} more queued · idle, ${left}s cooldown`;
    }
}

async function sendKeysToPane(session, keys) {
    await api("POST", "/api/session/key", { session, keys });
}

async function openRawTtyd() {
    const r = await api("POST", "/api/ttyd/raw", {});
    if (!r.ok) {
        alert("Error: " + (r.error || "unknown"));
        return;
    }
    // The new shell appears in /api/sessions on the next refresh and
    // gets rendered through the standard pane pipeline — same move /
    // snap / drag affordances as a tmux pane.
    if (r.name) {
        state.openPanes.add(r.name);
        if (!state.order.includes(r.name)) {
            state.order.push(r.name);
            saveOrder(state.order);
        }
    }
    await refresh();
    if (r.name) {
        const rec = state.nodes.get(r.name);
        if (rec && rec.details) {
            rec.details.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
    }
}

async function enterCopyMode(session) {
    const msg = document.getElementById("msg-" + cssId(session));
    const r = await api("POST", "/api/session/scroll", { session });
    if (msg) {
        msg.textContent = r.ok ? "scroll mode" : ("error: " + (r.error || ""));
        msg.className = r.ok ? "inline-msg ok" : "inline-msg err";
    }
}

// Toggle tmux's pane-zoom on the active pane of the session.
// Equivalent to the C-b z binding (`resize-pane -Z`). The same call
// un-zooms if the pane is already zoomed.
async function zoomPane(session) {
    const msg = document.getElementById("msg-" + cssId(session));
    const r = await api("POST", "/api/session/zoom", { session });
    if (msg) {
        msg.textContent = r.ok ? "pane zoom toggled" : ("error: " + (r.error || ""));
        msg.className = r.ok ? "inline-msg ok" : "inline-msg err";
    }
}


function hotButtonsFor(session) {
    return state.hot.map(normalizeHotSlot);
}

function hotButtonLabel(text) {
    const trimmed = String(text || "").trim();
    if (!trimmed) return "";
    return trimmed.length > 18 ? trimmed.slice(0, 17) + "…" : trimmed;
}

function hotLoopCountLabel(slot, remaining = null) {
    const loopCount = Number(slot && slot.loopCount) || 0;
    if (remaining !== null && remaining !== undefined) {
        return remaining > 0 ? `${remaining}x` : "0x";
    }
    return loopCount > 0 ? `${loopCount}x` : "∞";
}

function hotLoopKey(session, slot) {
    return `${session}::${slot}`;
}

function idleAlertFor(session) {
    return normalizeIdleAlert(state.idleAlerts[session]);
}

function visibleSessionNames() {
    // Visible = not hidden AND not in a user-defined group.
    return state.sessions.map((s) => s.name).filter((n) =>
        !state.hidden.has(n) && !state.groups.membership[n]);
}

function hiddenSessionNames() {
    return state.sessions.map((s) => s.name).filter((n) => state.hidden.has(n));
}

function sessionsInGroup(groupName) {
    return state.sessions
        .map((s) => s.name)
        .filter((n) => state.groups.membership[n] === groupName);
}

// Popover menu for the Move button. Lists all reachable buckets
// (Visible + user groups + Hidden) and an inline "New group…" option.
// Click-outside and Escape close it.
let _moveMenuOpen = null;

function openMoveMenu(sessionName, anchorEl) {
    closeMoveMenu();
    const current = state.groups.membership[sessionName]
        || (state.hidden.has(sessionName) ? "Hidden" : "Visible");
    const menu = el("div", { class: "move-menu" });
    const heading = el("div", { class: "move-menu-head" },
        `Move "${sessionName}" to:`);
    menu.append(heading);
    const rowFor = (group) => {
        const isCurrent = group === current;
        const row = el("div", {
            class: "move-menu-row" + (isCurrent ? " current" : ""),
            onclick: (e) => {
                e.preventDefault();
                e.stopPropagation();
                moveSessionToGroup(sessionName, group);
                closeMoveMenu();
            },
        }, group + (isCurrent ? "  (current)" : ""));
        return row;
    };
    menu.append(rowFor("Visible"));
    for (const g of state.groups.order) {
        if (state.groups.defs[g]) menu.append(rowFor(g));
    }
    menu.append(rowFor("Hidden"));
    menu.append(el("div", { class: "move-menu-sep" }));
    menu.append(el("div", {
        class: "move-menu-row new-group",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            const name = prompt("New group name:");
            closeMoveMenu();
            if (!name) return;
            const trimmed = name.trim();
            if (!trimmed || trimmed === "Visible" || trimmed === "Hidden") return;
            if (!state.groups.defs[trimmed]) {
                state.groups.defs[trimmed] = { label: trimmed, open: true };
                state.groups.order.push(trimmed);
                saveGroups();
            }
            moveSessionToGroup(sessionName, trimmed);
        },
    }, "+ New group…"));
    // Anchor below the clicked button.
    const rect = anchorEl.getBoundingClientRect();
    menu.style.top = `${rect.bottom + window.scrollY + 4}px`;
    menu.style.left = `${rect.left + window.scrollX}px`;
    document.body.append(menu);
    _moveMenuOpen = menu;
    // Delay binding the outside-click listener so the click that opened
    // the menu doesn't immediately close it.
    setTimeout(() => {
        document.addEventListener("click", closeMoveMenu, { once: true });
        document.addEventListener("keydown", _escCloseMoveMenu);
    }, 0);
}

function closeMoveMenu() {
    if (_moveMenuOpen) {
        _moveMenuOpen.remove();
        _moveMenuOpen = null;
    }
    document.removeEventListener("keydown", _escCloseMoveMenu);
}

function _escCloseMoveMenu(e) {
    if (e.key === "Escape") closeMoveMenu();
}

// Unified mover. Clears conflicting placements so a session is only in
// one place at a time (Visible / Hidden / one user group).
function moveSessionToGroup(sessionName, groupName) {
    const isUserGroup = state.groups.defs[groupName] !== undefined;
    if (groupName === "Visible") {
        state.hidden.delete(sessionName);
        delete state.groups.membership[sessionName];
    } else if (groupName === "Hidden") {
        delete state.groups.membership[sessionName];
        state.hidden.add(sessionName);
    } else if (isUserGroup) {
        state.hidden.delete(sessionName);
        state.groups.membership[sessionName] = groupName;
    } else {
        return;  // unknown group
    }
    saveHidden(state.hidden);
    saveGroups();
    refresh();
}

function flattenRows(rows) {
    return rows.flatMap((row) => Array.isArray(row) ? row : []);
}

function normalizeLayoutRows(rows, visibleNames) {
    const visible = new Set(visibleNames);
    const out = [];
    const seen = new Set();
    if (Array.isArray(rows)) {
        for (const rawRow of rows) {
            if (!Array.isArray(rawRow)) continue;
            const row = rawRow.filter((name) => visible.has(name) && !seen.has(name));
            if (!row.length) continue;
            row.forEach((name) => seen.add(name));
            out.push(row);
        }
    }
    for (const name of sortedSessionNames(visibleNames.filter((name) => !seen.has(name)))) {
        out.push([name]);
    }
    return out;
}

function syncLayoutState() {
    state.layout = normalizeLayoutRows(state.layout, visibleSessionNames());
    return state.layout;
}

function persistLayoutState() {
    syncLayoutState();
    saveLayout(state.layout);
    state.order = [...flattenRows(state.layout), ...sortedSessionNames(hiddenSessionNames())];
    saveOrder(state.order);
}

function findLayoutPosition(name) {
    for (let row = 0; row < state.layout.length; row += 1) {
        const col = state.layout[row].indexOf(name);
        if (col >= 0) return { row, col };
    }
    return null;
}

function removeFromLayout(name) {
    const pos = findLayoutPosition(name);
    if (!pos) return null;
    state.layout[pos.row].splice(pos.col, 1);
    if (!state.layout[pos.row].length) state.layout.splice(pos.row, 1);
    return pos;
}

function placeSessionRow(name, rowIndex) {
    const idx = Math.max(0, Math.min(rowIndex, state.layout.length));
    state.layout.splice(idx, 0, [name]);
}

function putSessionBeside(targetName, sessionName, side) {
    if (!sessionName || !targetName || sessionName === targetName) return;
    if (state.hidden.has(targetName)) return;
    syncLayoutState();
    const targetPos = findLayoutPosition(targetName);
    if (!targetPos) return;
    const row = state.layout[targetPos.row];
    // Cap at 4 panes side-by-side
    if (row.length >= 4 && !row.includes(sessionName)) return;
    if (state.hidden.has(sessionName)) {
        state.hidden.delete(sessionName);
        saveHidden(state.hidden);
    }
    removeFromLayout(sessionName);
    // Re-find after removal may have shifted indices
    const pos = findLayoutPosition(targetName);
    if (!pos) return;
    const targetRow = state.layout[pos.row];
    const insertAt = side === "left" ? pos.col : pos.col + 1;
    targetRow.splice(insertAt, 0, sessionName);
    persistLayoutState();
    renderLayout();
}

function placeSessionAbove(targetName, sessionName) {
    if (!sessionName || !targetName || sessionName === targetName) return;
    const sameBucket = state.hidden.has(sessionName) === state.hidden.has(targetName);
    if (!sameBucket) return;
    if (state.hidden.has(sessionName)) {
        const liveNames = state.sessions.map((s) => s.name);
        const bucket = liveNames.filter((n) => state.hidden.has(n));
        const current = sortedSessionNames(bucket).filter((n) => n !== sessionName);
        const to = current.indexOf(targetName);
        if (to < 0) return;
        current.splice(to, 0, sessionName);
        const visibleFlat = flattenRows(syncLayoutState());
        state.order = [...visibleFlat, ...current];
        saveOrder(state.order);
        renderLayout();
        return;
    }
    syncLayoutState();
    removeFromLayout(sessionName);
    const targetPos = findLayoutPosition(targetName);
    if (!targetPos) return;
    placeSessionRow(sessionName, targetPos.row);
    persistLayoutState();
    renderLayout();
}

function placeSessionBelow(targetName, sessionName) {
    if (!sessionName || !targetName || sessionName === targetName) return;
    if (state.hidden.has(sessionName) !== state.hidden.has(targetName)) return;
    if (state.hidden.has(sessionName)) return;
    syncLayoutState();
    removeFromLayout(sessionName);
    const targetPos = findLayoutPosition(targetName);
    if (!targetPos) return;
    placeSessionRow(sessionName, targetPos.row + 1);
    persistLayoutState();
    renderLayout();
}

function _makeDropBar(insertRowIdx) {
    const bar = el("div", { class: "row-drop-bar" });
    bar.addEventListener("dragover", (e) => {
        if (!e.dataTransfer.types.includes("text/x-tmux-browse-split") &&
            !e.dataTransfer.types.includes("text/x-tmux-browse-session")) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        bar.classList.add("visible");
    });
    bar.addEventListener("dragleave", () => bar.classList.remove("visible"));
    bar.addEventListener("drop", (e) => {
        const name = e.dataTransfer.getData("text/x-tmux-browse-split") ||
                     e.dataTransfer.getData("text/x-tmux-browse-session");
        bar.classList.remove("visible");
        if (!name) return;
        e.preventDefault();
        syncLayoutState();
        if (state.hidden.has(name)) {
            state.hidden.delete(name);
            saveHidden(state.hidden);
        }
        removeFromLayout(name);
        placeSessionRow(name, insertRowIdx);
        persistLayoutState();
        renderLayout();
    });
    return bar;
}

function renderLayout() {
    syncLayoutState();
    const root = document.getElementById("sessions");
    root.textContent = "";
    for (let ri = 0; ri < state.layout.length; ri++) {
        const row = state.layout[ri];
        // Drop bar before this row
        root.append(_makeDropBar(ri));
        const rowEl = el("div", { class: "session-row" });
        for (const name of row) {
            const rec = state.nodes.get(name);
            if (rec) rowEl.append(rec.details);
        }
        if (rowEl.childNodes.length) root.append(rowEl);
    }
    // Drop bar after last row
    if (state.layout.length) root.append(_makeDropBar(state.layout.length));
    if (!state.layout.length) {
        root.append(el("div", { id: "empty", class: "empty-state" },
            state.sessions.length === 0
                ? "No tmux sessions. Create one above."
                : "All sessions are hidden — open the list below."));
    }

    // User-defined pane groups render between the visible stack and the
    // Hidden drawer. Each group is its own furled <details> with its own
    // pane order derived from `state.order` but scoped to group members.
    const groupsRoot = document.getElementById("sessions-groups");
    if (groupsRoot) {
        groupsRoot.textContent = "";
        for (const groupName of state.groups.order) {
            const def = state.groups.defs[groupName];
            if (!def) continue;
            const members = sortedSessionNames(sessionsInGroup(groupName));
            const wrap = el("details", {
                id: `group-wrap-${cssId(groupName)}`,
                class: "group-wrap",
                "data-group": groupName,
            });
            if (def.open !== false || members.length) wrap.open = def.open !== false;
            const summary = el("summary", {},
                `${def.label || groupName} (${members.length})`);
            wrap.append(summary);
            const body = el("div", { class: "group-body" });
            for (const name of members) {
                const rec = state.nodes.get(name);
                if (rec) body.append(rec.details);
            }
            wrap.append(body);
            groupsRoot.append(wrap);
        }
    }

    const hiddenRoot = document.getElementById("sessions-hidden");
    hiddenRoot.textContent = "";
    for (const name of sortedSessionNames(hiddenSessionNames())) {
        const rec = state.nodes.get(name);
        if (rec) hiddenRoot.append(rec.details);
    }
    refreshHiddenChrome();
}


function openIdleEditor(session) {
    state.idleEditor.open = true;
    state.idleEditor.session = session;
    renderIdleEditor();
    document.getElementById("idle-modal").hidden = false;
    syncModalChrome();
}

function closeIdleEditor() {
    state.idleEditor.open = false;
    document.getElementById("idle-modal").hidden = true;
    syncModalChrome();
}

function renderIdleEditor() {
    const session = state.idleEditor.session;
    const cfg = idleAlertFor(session);
    document.getElementById("idle-modal-title").textContent = `Idle Alert · ${session}`;
    document.getElementById("idle-enabled").checked = cfg.enabled;
    const totalSec = Math.max(60, cfg.thresholdSec);
    document.getElementById("idle-threshold-hours").value = Math.floor(totalSec / 3600);
    document.getElementById("idle-threshold-minutes").value = Math.floor((totalSec % 3600) / 60);
    document.getElementById("idle-sound").checked = cfg.sound;
    document.getElementById("idle-prompt").checked = cfg.prompt;
}

function saveIdleEditor() {
    const session = state.idleEditor.session;
    const enabled = document.getElementById("idle-enabled").checked;
    const hours = Math.max(0, Math.floor(Number(document.getElementById("idle-threshold-hours").value) || 0));
    const minutes = Math.max(0, Math.floor(Number(document.getElementById("idle-threshold-minutes").value) || 0));
    const threshold = Math.max(60, hours * 3600 + minutes * 60);
    const sound = document.getElementById("idle-sound").checked;
    const prompt = document.getElementById("idle-prompt").checked;
    if (enabled && !sound && !prompt) {
        alert("Choose sound, prompt, or both.");
        return;
    }
    state.idleAlerts[session] = {
        enabled,
        thresholdSec: threshold,
        sound,
        prompt,
    };
    state.idleRuntime[session] = false;
    saveIdleAlerts();
    const rec = state.nodes.get(session);
    const row = state.sessions.find((s) => s.name === session);
    if (rec && row) updatePane(rec, row);
    closeIdleEditor();
}

function clearIdleEditor() {
    const session = state.idleEditor.session;
    delete state.idleAlerts[session];
    delete state.idleRuntime[session];
    saveIdleAlerts();
    const rec = state.nodes.get(session);
    const row = state.sessions.find((s) => s.name === session);
    if (rec && row) updatePane(rec, row);
    closeIdleEditor();
}


function fireIdleAlert(session, idleSeconds, cfg) {
    if (cfg.sound) playIdleTone();
    if (cfg.prompt) {
        window.alert(
            `Session '${session}' has been idle for ${fmtAgeSeconds(idleSeconds)} ` +
            `(threshold ${fmtAgeSeconds(cfg.thresholdSec)}).`
        );
    }
}

function checkIdleAlerts(rows) {
    const live = new Set(rows.map((s) => s.name));
    for (const [name, armed] of Object.entries(state.idleRuntime)) {
        if (!live.has(name)) delete state.idleRuntime[name];
    }
    for (const row of rows) {
        const cfg = idleAlertFor(row.name);
        if (!cfg.enabled) {
            state.idleRuntime[row.name] = false;
            continue;
        }
        const idle = row.idle_seconds || 0;
        const crossed = idle >= cfg.thresholdSec;
        const alreadyFired = !!state.idleRuntime[row.name];
        if (crossed && !alreadyFired) {
            state.idleRuntime[row.name] = true;
            fireIdleAlert(row.name, idle, cfg);
        } else if (!crossed) {
            state.idleRuntime[row.name] = false;
        }
    }
}


function renderHotButtons(session) {
    const rec = state.nodes.get(session);
    if (!rec) return;
    const cfg = state.config;
    const slots = hotButtonsFor(session);
    slots.forEach((slot, idx) => {
        const pair = rec.hotPairs[idx];
        const btn = pair.cmdBtn;
        const present = !!slot.text.trim();
        const buttonsVisible = present && cfg.show_body_hot_buttons;
        pair.wrap.hidden = !buttonsVisible;
        pair.wrap.style.display = buttonsVisible ? "inline-flex" : "none";
        const loopVisible = buttonsVisible && cfg.show_hot_loop_toggles;
        pair.loopBtn.hidden = !loopVisible;
        pair.loopBtn.style.display = loopVisible ? "inline-flex" : "none";
        btn.disabled = !present;
        btn.textContent = hotButtonLabel(slot.name || slot.text);
        btn.title = present
            ? `${slot.name || "Hot Button " + (idx + 1)}: ${slot.text} (loop ${hotLoopCountLabel(slot)})`
            : `hot button ${idx + 1} is empty`;
        if (!present) delete state.hotLoops[hotLoopKey(session, idx)];
        const loopState = state.hotLoops[hotLoopKey(session, idx)];
        const active = !!loopState;
        pair.loopBtn.className = active ? "btn orange hot-loop-btn is-active" : "btn orange hot-loop-btn";
        pair.loopBtn.textContent = active
            ? hotLoopCountLabel(slot, loopState.remaining)
            : hotLoopCountLabel(slot);
        pair.loopBtn.title = active
            ? `looping '${slot.name || "Hot Button " + (idx + 1)}' while ${session} is idle; ${loopState.remaining === null ? "no limit" : `${loopState.remaining} sends remaining`}`
            : `start loop for '${slot.name || "Hot Button " + (idx + 1)}' (${slot.loopCount > 0 ? `${slot.loopCount} sends max` : "runs until stopped"})`;
    });
}

async function sendHotButton(session, slot) {
    const slots = hotButtonsFor(session);
    const picked = slots[slot] || { name: "", text: "" };
    const text = picked.text || "";
    if (!text.trim()) return;
    const msg = document.getElementById("msg-" + cssId(session));
    if (msg) {
        msg.textContent = `sending hot ${slot + 1}…`;
        msg.className = "inline-msg dim";
    }
    const r = await api("POST", "/api/session/type", { session, text });
    if (msg) {
        msg.textContent = r.ok ? `sent: ${hotButtonLabel(picked.name || text)}` : ("error: " + (r.error || ""));
        msg.className = r.ok ? "inline-msg ok" : "inline-msg err";
    }
}

function toggleHotLoop(session, slot) {
    const picked = hotButtonsFor(session)[slot] || { name: "", text: "", loopCount: 0 };
    if (!picked.text.trim()) return;
    const key = hotLoopKey(session, slot);
    if (state.hotLoops[key]) delete state.hotLoops[key];
    else state.hotLoops[key] = {
        waitingForActive: false,
        busy: false,
        remaining: picked.loopCount > 0 ? picked.loopCount : null,
    };
    renderHotButtons(session);
}

async function checkHotLoops(rows) {
    const byName = new Map(rows.map((row) => [row.name, row]));
    for (const [key, loop] of Object.entries(state.hotLoops)) {
        const splitAt = key.lastIndexOf("::");
        const session = key.slice(0, splitAt);
        const slot = Number(key.slice(splitAt + 2));
        const row = byName.get(session);
        const picked = hotButtonsFor(session)[slot] || { name: "", text: "", loopCount: 0 };
        if (!row || !picked.text.trim()) {
            delete state.hotLoops[key];
            continue;
        }
        if (loop.busy) continue;
        if ((row.idle_seconds || 0) < state.config.hot_loop_idle_seconds) {
            loop.waitingForActive = false;
            continue;
        }
        if (loop.waitingForActive) continue;
        loop.busy = true;
        try {
            await sendHotButton(session, slot);
            if (loop.remaining !== null) {
                loop.remaining = Math.max(0, loop.remaining - 1);
                if (loop.remaining === 0) {
                    delete state.hotLoops[key];
                    renderHotButtons(session);
                    continue;
                }
            }
            loop.waitingForActive = true;
        } finally {
            loop.busy = false;
        }
        renderHotButtons(session);
    }
}


function openHotButtons(session, slot = 0) {
    state.hotEditor.open = true;
    state.hotEditor.session = session;
    state.hotEditor.slot = slot;
    renderHotEditor();
    document.getElementById("hot-modal").hidden = false;
    syncModalChrome();
}

function closeHotButtons() {
    state.hotEditor.open = false;
    document.getElementById("hot-modal").hidden = true;
    syncModalChrome();
}


function renderWorkflowEditor() {
    // The workflow modal HTML lives in the agent extension's
    // ui_blocks.html. When that extension isn't loaded the IDs below
    // don't exist; bail out instead of crashing on null.textContent.
    const title = document.getElementById("workflow-modal-title");
    const list = document.getElementById("workflow-slot-list");
    const nameInp = document.getElementById("workflow-name");
    const promptInp = document.getElementById("workflow-prompt");
    const intervalInp = document.getElementById("workflow-interval");
    if (!title || !list || !nameInp || !promptInp || !intervalInp) return;
    const agent = state.workflowEditor.agent;
    const slot = state.workflowEditor.slot;
    const entry = workflowEntry(agent);
    const slots = entry.workflows;
    const row = slots[slot] || { name: "", prompt: "", interval_seconds: 300 };
    title.textContent = `Agent Workflows · ${agent}`;
    nameInp.value = row.name;
    promptInp.value = row.prompt;
    intervalInp.value = row.interval_seconds;
    list.textContent = "";
    slots.forEach((workflow, idx) => {
        const present = !!workflow.prompt.trim();
        list.append(el("button", {
            class: idx === slot ? "hot-slot-item active" : "hot-slot-item",
            type: "button",
            onclick: () => {
                state.workflowEditor.slot = idx;
                renderWorkflowEditor();
            },
        },
        el("span", { class: "hot-slot-kicker" }, `Workflow ${idx + 1}`),
        el("span", { class: "hot-slot-name" }, workflow.name || (present ? `Every ${workflow.interval_seconds}s` : "Empty slot")),
        el("span", { class: "hot-slot-command" }, present ? workflow.prompt : "Create scheduled workflow"),
        ));
    });
}

function openWorkflowEditor(agentName, slot = 0) {
    const modal = document.getElementById("workflow-modal");
    if (!modal) return;
    state.workflowEditor.open = true;
    state.workflowEditor.agent = (agentName || "").trim().toLowerCase();
    state.workflowEditor.slot = slot;
    workflowEntry(state.workflowEditor.agent);
    renderWorkflowEditor();
    modal.hidden = false;
    syncModalChrome();
}

function closeWorkflowEditor() {
    const modal = document.getElementById("workflow-modal");
    state.workflowEditor.open = false;
    if (modal) modal.hidden = true;
    syncModalChrome();
}

async function saveWorkflowEditor() {
    const agent = state.workflowEditor.agent;
    const slot = state.workflowEditor.slot;
    const entry = workflowEntry(agent);
    entry.workflows[slot] = normalizeWorkflowSlot({
        name: document.getElementById("workflow-name").value,
        prompt: document.getElementById("workflow-prompt").value,
        interval_seconds: document.getElementById("workflow-interval").value,
    });
    await saveAgentWorkflows(true);
    renderWorkflowEditor();
    refresh();
}

async function clearWorkflowEditor() {
    const agent = state.workflowEditor.agent;
    const slot = state.workflowEditor.slot;
    const entry = workflowEntry(agent);
    entry.workflows[slot] = { name: "", prompt: "", interval_seconds: 300 };
    await saveAgentWorkflows(true);
    renderWorkflowEditor();
    refresh();
}

async function toggleWorkflowEnabled(agentName) {
    const entry = workflowEntry(agentName);
    entry.enabled = !entry.enabled;
    // Workflow execution is now server-side; toggling just saves config.
    await saveAgentWorkflows(true);
    refresh();
}

async function loadWorkflowState() {
    const r = await api("GET", "/api/agent-workflow-state");
    if (r.ok) {
        state.workflowServerState = r.state || {};
        state.schedulerRunning = !!r.scheduler_running;
    }
}


function openSplitPicker(session) {
    state.splitPicker.open = true;
    state.splitPicker.session = session;
    state.splitPicker.filter = "";
    renderSplitPicker();
    document.getElementById("split-modal").hidden = false;
    syncModalChrome();
    const search = document.getElementById("split-search");
    if (search) search.focus();
}

function closeSplitPicker() {
    state.splitPicker.open = false;
    document.getElementById("split-modal").hidden = true;
    syncModalChrome();
}

function chooseSplitTarget(targetName) {
    putSessionBeside(targetName, state.splitPicker.session, "right");
    closeSplitPicker();
}

function renderSplitPicker() {
    const source = state.splitPicker.session;
    const list = document.getElementById("split-target-list");
    const title = document.getElementById("split-modal-title");
    const filter = state.splitPicker.filter.trim().toLowerCase();
    title.textContent = `Split Right · ${source}`;
    list.textContent = "";
    const candidates = state.sessions
        .filter((s) => s.name !== source && !state.hidden.has(s.name))
        .filter((s) => !filter || s.name.toLowerCase().includes(filter));
    if (!candidates.length) {
        list.append(el("div", { class: "dim split-empty" },
            filter
                ? "No visible sessions match that filter."
                : "No other visible sessions are available."));
        return;
    }
    for (const s of candidates) {
        list.append(el("button", {
            class: "split-target-item",
            type: "button",
            onclick: () => chooseSplitTarget(s.name),
            title: `place ${source} to the right of ${s.name}`,
        },
            el("div", { class: "split-target-title" },
                s.name,
                el("span", { class: "badge" }, `${s.windows}w`),
                s.attached > 0 ? el("span", { class: "badge attached" }, `${s.attached} clients`) : null,
            ),
            el("div", { class: "split-target-meta" },
                `idle ${s.idle_seconds !== undefined ? fmtAgeSeconds(s.idle_seconds) : fmtAge(s.activity)}`),
        ));
    }
}

function selectHotSlot(slot) {
    state.hotEditor.slot = slot;
    renderHotEditor();
}


function renderHotEditor() {
    const slots = hotButtonsFor();
    const slotList = document.getElementById("hot-slot-list");
    slotList.textContent = "";
    let selectedExists = false;
    slots.forEach((slot, idx) => {
        const present = !!(slot.name || slot.text);
        if (!present) return;
        if (idx === state.hotEditor.slot) selectedExists = true;
        slotList.append(el("button", {
            class: `hot-slot-item${idx === state.hotEditor.slot ? " active" : ""}`,
            onclick: () => selectHotSlot(idx),
            type: "button",
        },
            el("span", { class: "hot-slot-kicker" }, `Slot ${idx + 1}`),
            el("span", { class: "hot-slot-name" }, slot.name || "Unnamed button"),
            el("span", { class: "hot-slot-command" },
                `${slot.text || "No command yet"}${slot.loopCount > 0 ? ` · loop ${slot.loopCount}x` : " · loop ∞"}`),
        ));
    });
    if (!selectedExists) {
        const emptySlot = slots.findIndex((slot) => !(slot.name || slot.text));
        if (emptySlot >= 0) state.hotEditor.slot = emptySlot;
    }
    const addSlot = slots.findIndex((slot) => !(slot.name || slot.text));
    if (addSlot >= 0) {
        slotList.append(el("button", {
            class: `hot-slot-item hot-slot-add${addSlot === state.hotEditor.slot ? " active" : ""}`,
            onclick: () => selectHotSlot(addSlot),
            type: "button",
        },
            el("span", { class: "hot-slot-name" }, "Add a Button"),
            el("span", { class: "hot-slot-command" }, `Create hot button ${addSlot + 1}`),
        ));
    }
    const current = slots[state.hotEditor.slot] || { name: "", text: "" };
    document.getElementById("hot-name").value = current.name;
    document.getElementById("hot-command").value = current.text;
    document.getElementById("hot-loop-count").value = current.loopCount || 0;
    document.getElementById("hot-modal-title").textContent =
        `Hot Buttons · ${state.hotEditor.session}`;
}

function saveHotButton() {
    const slot = state.hotEditor.slot;
    const loopCount = Math.max(0, Math.floor(Number(document.getElementById("hot-loop-count").value) || 0));
    state.hot[slot] = {
        name: document.getElementById("hot-name").value.trim(),
        text: document.getElementById("hot-command").value.trim(),
        loopCount,
    };
    const key = hotLoopKey(state.hotEditor.session, slot);
    if (state.hotLoops[key]) {
        state.hotLoops[key].remaining = loopCount > 0 ? loopCount : null;
        state.hotLoops[key].waitingForActive = false;
    }
    saveHot();
    for (const s of state.sessions) renderHotButtons(s.name);
    renderHotEditor();
}

function clearHotButton() {
    state.hot[state.hotEditor.slot] = { name: "", text: "", loopCount: 0 };
    delete state.hotLoops[hotLoopKey(state.hotEditor.session, state.hotEditor.slot)];
    saveHot();
    for (const s of state.sessions) renderHotButtons(s.name);
    renderHotEditor();
}


async function stopTtyd(session) {
    const r = await api("POST", "/api/ttyd/stop", { session });
    const msg = document.getElementById("msg-" + cssId(session));
    if (msg) {
        msg.textContent = r.ok ? "stopped" : ("error: " + (r.error || ""));
        msg.className = r.ok ? "inline-msg dim" : "inline-msg err";
    }
    const iframe = document.getElementById("iframe-" + cssId(session));
    if (iframe) iframe.removeAttribute("src");
    state.openPanes.delete(session);
    refresh();
}

async function killSession(session) {
    if (!confirm(`Kill tmux session '${session}'? This terminates all its programs.`)) return;
    const r = await api("POST", "/api/session/kill", { session });
    const msg = document.getElementById("msg-" + cssId(session));
    if (msg) {
        msg.textContent = r.ok ? "killed" : ("error: " + (r.error || ""));
        msg.className = r.ok ? "inline-msg ok" : "inline-msg err";
    }
    state.openPanes.delete(session);
    refresh();
}

// Counterpart to killSession for raw ttyd shells: there's no tmux
// session to kill, just a ttyd process to stop. The pane is removed
// on the next refresh because the server drops the shell from
// /api/sessions when its pidfile is gone.
async function stopRawShell(name) {
    const r = await api("POST", "/api/ttyd/stop", { session: name });
    const msg = document.getElementById("msg-" + cssId(name));
    if (msg && r) {
        msg.textContent = r.ok ? "stopped" : ("error: " + (r.error || ""));
        msg.className = r.ok ? "inline-msg ok" : "inline-msg err";
    }
    state.openPanes.delete(name);
    refresh();
}

async function newSession() {
    const input = document.getElementById("new-name");
    const name = input.value.trim();
    if (!name) return;
    const r = await api("POST", "/api/session/new", { name });
    if (r.ok) { input.value = ""; refresh(); }
    else alert("Error: " + (r.error || "unknown"));
}

async function restartDashboard() {
    const btn = document.getElementById("restart-btn");
    if (!confirm("Restart the tmux-browse dashboard server?")) return;
    btn.disabled = true;
    btn.textContent = "Restarting…";
    const r = await api("POST", "/api/server/restart", {});
    if (!r.ok) {
        btn.disabled = false;
        btn.textContent = "Restart";
        alert("Error: " + (r.error || "unknown"));
        return;
    }
    setTimeout(() => { window.location.reload(); }, 1200);
}


// Create a pane once per session and reuse it across refreshes, so active
// iframes aren't torn down and rebuilt every 5 s.
function createPane(s) {
    const id = cssId(s.name);
    const isRaw = s.kind === "raw";
    // Display label: raw shells get the friendly "shell · <uid>" prefix
    // (the underlying name keeps its ``raw-shell-`` prefix because that's
    // what every server-side pidfile / port-registry / stop call expects).
    const displayName = isRaw ? `shell · ${s.name}` : s.name;
    const sname = el("span", { class: "sname" }, displayName);
    const sbadges = el("span", { class: "sbadges" });
    const idle = el("span", { class: "dim" });
    const idleAlertBtn = el("button", {
        class: "btn blue summary-idle-alert",
        type: "button",
        onmousedown: (e) => {
            e.preventDefault();
            e.stopPropagation();
        },
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            openIdleEditor(s.name);
        },
        title: "configure idle detection for this session",
    }, "Idle Alert");
    const idleIconBtn = el("button", {
        class: "wc-btn wc-idle-icon",
        type: "button",
        onmousedown: (e) => { e.preventDefault(); e.stopPropagation(); },
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); openIdleEditor(s.name); },
        title: "configure idle detection",
    });
    idleIconBtn.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5"><ellipse cx="8" cy="8" rx="6.5" ry="4"/><circle cx="8" cy="8" r="1.5" fill="currentColor"/></svg>';
    const idleWrap = el("span", { class: "summary-idle-wrap" }, idle, idleAlertBtn, idleIconBtn);
    const summaryTabLink = el("a", {
        class: "btn green summary-open",
        target: "_blank", rel: "noopener",
        title: "open ttyd in its own tab",
        onclick: stopSummaryToggle,
        href: "#",
        style: "display:none;text-decoration:none",
    }, "Open ↗");
    const logLink = el("a", {
        class: "btn summary-log",
        target: "_blank", rel: "noopener",
        title: "tmux scrollback for this session",
        onclick: stopSummaryToggle,
        href: `/api/session/log?session=${encodeURIComponent(s.name)}&html=1`,
        style: "text-decoration:none",
    }, "Log");
    const logIconBtn = el("a", {
        class: "wc-btn wc-log-icon",
        target: "_blank", rel: "noopener",
        title: "view tmux log (scrollback dump)",
        onclick: stopSummaryToggle,
        href: `/api/session/log?session=${encodeURIComponent(s.name)}&html=1`,
    });
    logIconBtn.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor"><path d="M2 1h8l4 4v10H2V1zm8 0v4h4M4 8h8M4 11h6"/><path d="M2 1h8l4 4v10H2V1z" fill="none" stroke="currentColor" stroke-width="1.2"/><line x1="4" y1="8" x2="12" y2="8" stroke="currentColor" stroke-width="1"/><line x1="4" y1="10.5" x2="10" y2="10.5" stroke="currentColor" stroke-width="1"/><line x1="4" y1="6" x2="8" y2="6" stroke="currentColor" stroke-width="1"/></svg>';
    const scrollBtn = el("button", {
        class: "btn orange summary-scroll",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            enterCopyMode(s.name);
        },
        title: "enter tmux copy-mode so you can scroll back (equivalent to C-b [)",
    }, "Scroll");
    const scrollIconBtn = el("button", {
        class: "wc-btn wc-scroll-icon",
        type: "button",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            enterCopyMode(s.name);
        },
        title: "enter tmux copy-mode (live scrollback — C-b [)",
    });
    scrollIconBtn.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4l3-3 3 3"/><path d="M5 12l3 3 3-3"/><line x1="8" y1="1" x2="8" y2="15"/></svg>';
    const moveBtn = el("button", {
        class: "btn blue summary-move",
        type: "button",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            openMoveMenu(s.name, e.currentTarget);
        },
        title: "move this session to another pane group",
    }, "Move");
    const moveIconBtn = el("button", {
        class: "wc-btn wc-move-icon",
        type: "button",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            openMoveMenu(s.name, e.currentTarget);
        },
        title: "move this session to another pane group",
    });
    moveIconBtn.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 5.5 v7 a1 1 0 0 0 1 1 h11 a1 1 0 0 0 1 -1 v-6 a1 1 0 0 0 -1 -1 h-6 l-1.5 -1.5 h-3.5 a1 1 0 0 0 -1 1 z"/><path d="M7 9 h4 m0 0 l-1.5 -1.5 m1.5 1.5 l-1.5 1.5"/></svg>';
    const hideBtn = el("button", {
        class: "btn red summary-hide",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleHidden(s.name);
        },
        title: "move to the hidden list at the bottom of the page",
    }, "Hide");
    const hideIconBtn = el("button", {
        class: "wc-btn wc-hide-icon",
        type: "button",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleHidden(s.name);
        },
        title: "hide this session",
    });
    hideIconBtn.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor"><path d="M13 5c0-1-1.5-3-5-3S3 4 3 5c0 0-.5 0-1 .5S1.5 7 2 7h12c.5 0 .5-1 0-1.5S13 5 13 5zm-8.5 3a2.5 2.5 0 0 0-1.3 4.6c.3.2.7.4 1.3.4h7c.6 0 1-.2 1.3-.4A2.5 2.5 0 0 0 11.5 8h-7zM6 10.5a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm6 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"/></svg>';
    const splitBtn = el("button", {
        class: "btn blue split-btn",
        type: "button",
        draggable: "true",
        onmousedown: (e) => {
            e.preventDefault();
            e.stopPropagation();
        },
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            openSplitPicker(s.name);
        },
        ondragstart: (e) => {
            e.stopPropagation();
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData("text/x-tmux-browse-split", s.name);
        },
        title: "click to place this session to the right of another; drag onto a session to snap left, right, or above",
    }, "▥");

    const upBtn = el("button", {
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); moveSession(s.name, -1); },
        title: "move up",
    }, "▲");
    const downBtn = el("button", {
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); moveSession(s.name, +1); },
        title: "move down",
    }, "▼");
    const reorderPad = el("span", {
        class: "reorder-pad",
        draggable: "true",
        title: "drag to reorder",
        ondragstart: (e) => {
            e.stopPropagation();
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData("text/x-tmux-browse-session", s.name);
        },
        onclick: stopSummaryToggle,
    }, upBtn, downBtn);

    const msg = el("span", { id: "msg-" + id, class: "inline-msg dim" });

    const wcMinimize = el("button", {
        class: "wc-btn wc-minimize", type: "button",
        title: "minimize (furl pane)",
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); if (details.open) details.open = false; },
    }, "\u2013");
    // Step buttons \u2014 adjust the iframe wrapper's pixel dimensions in
    // fixed increments, then run fit-to-iframe so tmux dimensions
    // catch up. Width is bounded to the parent layout row's width;
    // overshooting just clips. Height is unbounded.
    const mkStepBtn = (label, title, axis, delta) => {
        const btn = el("button", {
            class: "wc-btn wc-step", type: "button", title,
            onclick: (e) => {
                e.preventDefault(); e.stopPropagation();
                stepIframeSize(s.name, axis, delta);
            },
        }, label);
        return btn;
    };
    const wcMinusW = mkStepBtn("-w", "shrink iframe width by " + STEP_PX_W + "px", "w", -STEP_PX_W);
    const wcPlusW  = mkStepBtn("+w", "grow iframe width by "   + STEP_PX_W + "px", "w", +STEP_PX_W);
    const wcMinusH = mkStepBtn("-h", "shrink iframe height by " + STEP_PX_H + "px", "h", -STEP_PX_H);
    const wcPlusH  = mkStepBtn("+h", "grow iframe height by "   + STEP_PX_H + "px", "h", +STEP_PX_H);
    // Standalone tmux-resize button \u2014 fits the tmux window dimensions
    // to the iframe's actual pixel area (cols/rows derived from xterm
    // cell size). The previous ``resize-pane -Z`` toggle was a no-op
    // for the common single-pane window case, so this is the action
    // operators actually want here.
    const wcTmuxResize = el("button", {
        class: "wc-btn wc-tmux-resize", type: "button",
        title: "fit tmux window dimensions to the iframe area",
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); fitTmuxToIframe(s.name); },
    });
    wcTmuxResize.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M2 6V2h4"/><path d="M14 6V2h-4"/><path d="M2 10v4h4"/><path d="M14 10v4h-4"/></svg>';
    const wcMaximize = el("button", {
        class: "wc-btn wc-maximize", type: "button",
        title: "maximize: stretch iframe to 90vh and fit tmux to it",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            // Step 1: grow the iframe wrapper to (almost) the full
            // viewport. Step 2: wait one frame for the layout to
            // settle, then resize tmux to match the new iframe area.
            const rec = state.nodes.get(s.name);
            if (rec && rec.iframeWrap) {
                const cur = rec.iframeWrap.style.height;
                const maxH = "90vh";
                const defaultH = `${state.config.default_ttyd_height_vh || 70}vh`;
                rec.iframeWrap.style.height = cur === maxH ? defaultH : maxH;
            }
            requestAnimationFrame(() => fitTmuxToIframe(s.name));
        },
    }, "\u25a1");
    // Raw shells aren't tmux \u2014 closing them stops the ttyd directly
    // instead of running ``tmux kill-session`` (which would error).
    const closeAction = isRaw
        ? () => stopRawShell(s.name)
        : () => killSession(s.name);
    const wcClose = el("button", {
        class: "wc-btn wc-close", type: "button",
        title: isRaw ? "close (stop ttyd shell)" : "close (kill session)",
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); closeAction(); },
    }, "\u00d7");
    const wcControls = el("span", { class: "wc-controls" },
        wcMinimize, wcMinusW, wcPlusW, wcMinusH, wcPlusH,
        wcTmuxResize, wcMaximize, wcClose);

    const summary = el("summary", { draggable: "true" },
        sname, msg, sbadges, idleWrap,
        el("span", { class: "summary-actions" },
            summaryTabLink, logLink, logIconBtn, scrollBtn, scrollIconBtn, splitBtn, moveBtn, moveIconBtn, hideBtn, hideIconBtn, reorderPad, wcControls),
    );
    const bodyKillBtn = el("button", {
        class: "btn red",
        onclick: closeAction,
    }, isRaw ? "Stop" : "Kill");
    const workflowBtn = el("button", {
        class: "btn blue", onclick: () => openWorkflowEditor(s.agent_name || ""),
        title: "edit scheduled prompts for this conversation-mode agent pane",
    }, "Workflows");
    const workflowToggleInput = el("input", {
        type: "checkbox",
        onchange: () => toggleWorkflowEnabled(s.agent_name || ""),
    });
    const workflowToggleText = el("span", { class: "workflow-switch-text" }, "Workflows");
    const workflowToggle = el("label", {
        class: "workflow-switch",
        title: "enable or disable scheduled workflow prompts for this agent conversation pane",
    }, workflowToggleInput, el("span", { class: "workflow-switch-track" }, el("span", { class: "workflow-switch-thumb" })), workflowToggleText);
    const hotManageBtn = el("button", {
        class: "btn blue", onclick: () => openHotButtons(s.name),
        title: "edit the shared hot buttons that appear in every session pane",
    }, "Hot Buttons");
    const hotPairs = Array.from({ length: 32 }, (_, idx) => {
        const cmdBtn = el("button", {
            class: "btn orange hot-chip",
            onclick: () => sendHotButton(s.name, idx),
            disabled: "disabled",
        });
        const loopBtn = el("button", {
            class: "btn orange hot-loop-btn",
            onclick: () => toggleHotLoop(s.name, idx),
            title: "start loop",
            type: "button",
        }, "⟳");
        const wrap = el("span", { class: "hot-pair", hidden: "hidden" }, cmdBtn, loopBtn);
        return { wrap, cmdBtn, loopBtn };
    });
    const launchBtn = el("button", { class: "btn green", onclick: () => launch(s.name) }, "Launch");
    const stopBtn = el("button", { class: "btn orange", onclick: () => stopTtyd(s.name) }, "Stop ttyd");
    const actions = el("div", { class: "pane-actions" },
        launchBtn, stopBtn, bodyKillBtn, workflowBtn, workflowToggle, msg, hotManageBtn, ...hotPairs.map((pair) => pair.wrap),
    );

    const iframe = el("iframe", {
        id: "iframe-" + id, class: "pane-iframe",
        allow: "clipboard-read; clipboard-write",
    });
    const dragShield = el("div", { class: "drag-shield" });
    const iframeWrap = el("div", { class: "ttyd-resize-wrap" }, iframe, dragShield);

    // Resize row together: when this pane's iframe wrapper is resized,
    // propagate the height to all sibling panes in the same layout row.
    let resizeSyncing = false;
    new ResizeObserver(() => {
        if (resizeSyncing || !state.config.resize_row_together) return;
        const pos = findLayoutPosition(s.name);
        if (!pos || !state.layout[pos.row] || state.layout[pos.row].length <= 1) return;
        const h = iframeWrap.style.height;
        if (!h) return;
        resizeSyncing = true;
        for (const peer of state.layout[pos.row]) {
            if (peer === s.name) continue;
            const peerRec = state.nodes.get(peer);
            if (peerRec && peerRec.iframeWrap) peerRec.iframeWrap.style.height = h;
        }
        resizeSyncing = false;
    }).observe(iframeWrap);

    const sendInput = el("input", {
        type: "text", class: "send-bar-input",
        placeholder: `Send to ${s.name}...`,
    });
    const sendCount = el("input", {
        type: "number", class: "send-bar-count",
        min: "1", max: "99", step: "1", value: "1",
        title: ("send N times — repeats wait for the pane to go idle "
            + "plus a 60s cooldown, with a re-check before each send"),
    });
    const sendBtn = el("button",
        { class: "btn green", onclick: () => sendToPane(s.name, sendInput, sendCount) },
        "Send");
    sendInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") sendToPane(s.name, sendInput, sendCount);
    });
    const sendStatus = el("span", { class: "send-bar-status dim" });
    const sendBar = el("div", { class: "send-bar" },
        sendInput, sendCount, sendBtn, sendStatus);

    const phoneKeys = el("div", { class: "phone-keys" },
        ...loadPhoneKeys().map((def) =>
            el("button", {
                class: "phone-key", type: "button",
                onclick: () => { if (def.keys && def.keys.length) sendKeysToPane(s.name, def.keys); },
            }, def.label),
        ),
    );

    const fPort = el("span"), fPid = el("span"), fCreated = el("span");
    const footer = el("div", { class: "pane-footer" }, fPort, fPid, fCreated);

    const dropOverlay = el("div", { class: "drop-overlay" });
    const details = el("details", {
        class: isRaw ? "session session-raw" : "session",
        "data-session": s.name,
    },
        summary, el("div", { class: "pane-body" }, actions, iframeWrap, sendBar, phoneKeys, footer),
        dropOverlay,
    );

    details.addEventListener("toggle", () => {
        if (details.open && state.config.launch_on_expand && !state.openPanes.has(s.name)) {
            launch(s.name);
        }
        // Furl side-by-side: when one pane in a row closes, close all in the row
        if (!details.open && state.config.furl_side_by_side) {
            const pos = findLayoutPosition(s.name);
            if (pos && state.layout[pos.row] && state.layout[pos.row].length > 1) {
                for (const peer of state.layout[pos.row]) {
                    if (peer === s.name) continue;
                    const peerRec = state.nodes.get(peer);
                    if (peerRec && peerRec.details.open) peerRec.details.open = false;
                }
            }
        }
        if (details.open && state.config.furl_side_by_side) {
            const pos = findLayoutPosition(s.name);
            if (pos && state.layout[pos.row] && state.layout[pos.row].length > 1) {
                for (const peer of state.layout[pos.row]) {
                    if (peer === s.name) continue;
                    const peerRec = state.nodes.get(peer);
                    if (peerRec && !peerRec.details.open) peerRec.details.open = true;
                }
            }
        }
    });

    // Summary bar drag: dropping on left/right half of another session
    // snaps side-by-side; dropping above (center) reorders.
    summary.addEventListener("dragstart", (e) => {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/x-tmux-browse-split", s.name);
        e.dataTransfer.setData("text/x-tmux-browse-session", s.name);
    });

    // Drag-and-drop with tilix-style 4-zone triangle detection.
    // The pane is divided into 4 triangles meeting at the center point:
    //   LEFT:   (0,0) → (0,H) → (W/2,H/2)
    //   RIGHT:  (W,0) → (W,H) → (W/2,H/2)
    //   TOP:    (0,0) → (W,0) → (W/2,H/2)
    //   BOTTOM: (0,H) → (W,H) → (W/2,H/2)
    const DROP_ZONES = ["drop-left", "drop-right", "drop-top", "drop-bottom"];
    const clearDropClasses = () => details.classList.remove(...DROP_ZONES);

    function getDropZone(e) {
        const rect = details.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const w = rect.width;
        const h = rect.height;
        if (w < 1 || h < 1) return null;
        // Normalize to 0..1
        const nx = x / w;
        const ny = y / h;
        // The two diagonals divide the rectangle into 4 triangles:
        // diagonal 1: top-left to bottom-right (ny = nx)
        // diagonal 2: top-right to bottom-left (ny = 1 - nx)
        const aboveDiag1 = ny < nx;
        const aboveDiag2 = ny < (1 - nx);
        if (aboveDiag2 && !aboveDiag1) return "left";
        if (aboveDiag1 && aboveDiag2) return "top";
        if (aboveDiag1 && !aboveDiag2) return "right";
        return "bottom";
    }

    details.addEventListener("dragover", (e) => {
        const hasDrag = e.dataTransfer.types.includes("text/x-tmux-browse-split") ||
                        e.dataTransfer.types.includes("text/x-tmux-browse-session");
        if (!hasDrag) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        clearDropClasses();
        const zone = getDropZone(e);
        if (zone) details.classList.add("drop-" + zone);
    });
    details.addEventListener("dragleave", (e) => {
        // Only clear if actually leaving the details element, not moving between children
        if (!details.contains(e.relatedTarget)) clearDropClasses();
    });
    details.addEventListener("drop", (e) => {
        const draggedSplit = e.dataTransfer.getData("text/x-tmux-browse-split");
        const draggedReorder = e.dataTransfer.getData("text/x-tmux-browse-session");
        clearDropClasses();
        if (!draggedSplit && !draggedReorder) return;
        e.preventDefault();
        const zone = getDropZone(e);
        const name = draggedSplit || draggedReorder;
        dropOnSession(s.name, name, zone || "top");
    });

    return {
        details, sbadges, idle, idleWrap, idleAlertBtn, idleIconBtn,
        summaryTabLink, logLink, logIconBtn, scrollBtn, scrollIconBtn, splitBtn, moveBtn, moveIconBtn, hideBtn, hideIconBtn, reorderPad,
        launchBtn, stopBtn, killBtn: bodyKillBtn, hotManageBtn, msg,
        wcClose, wcMaximize, wcMinimize, wcTmuxResize,
        wcPlusW, wcMinusW, wcPlusH, wcMinusH,
        workflowBtn, workflowToggle, workflowToggleInput, workflowToggleText,
        iframe, iframeWrap, sendBar, sendStatus, phoneKeys, fPort, fPid, fCreated, footer,
        hotPairs,
    };
}


function updatePane(rec, s) {
    const cfg = state.config;
    // Badges
    rec.sbadges.textContent = "";
    if (cfg.show_attached_badge && s.attached > 0) {
        rec.sbadges.append(el("span", { class: "badge attached" }, `${s.attached} clients`));
    }
    if (cfg.show_window_badge) {
        rec.sbadges.append(el("span", { class: "badge" }, `${s.windows}w`));
    }
    if (cfg.show_port_badge && s.ttyd_running) {
        rec.sbadges.append(el("span", { class: "badge running" }, `:${s.port}`));
    }
    // Prefer the server-computed ages to avoid clock-skew surprises.
    rec.idle.textContent = `idle ${s.idle_seconds !== undefined
        ? fmtAgeSeconds(s.idle_seconds)
        : fmtAge(s.activity)}`;
    const idleCfg = idleAlertFor(s.name);
    rec.idleAlertBtn.textContent = idleCfg.enabled
        ? `Idle Alert ${fmtAgeSeconds(idleCfg.thresholdSec)}`
        : "Idle Alert";
    rec.idleAlertBtn.className = idleCfg.enabled
        ? "btn green summary-idle-alert"
        : "btn blue summary-idle-alert";
    rec.idleAlertBtn.title = idleCfg.enabled
        ? `enabled: ${idleCfg.sound ? "sound" : ""}${idleCfg.sound && idleCfg.prompt ? " + " : ""}${idleCfg.prompt ? "prompt" : ""}`
        : "configure idle detection for this session";
    rec.idleIconBtn.style.color = idleCfg.enabled ? "var(--green)" : "";

    // Summary "Open" button: hidden entirely until ttyd is running.
    const url = s.ttyd_running ? ttydUrl(s.port) : "#";
    rec.summaryTabLink.href = url;
    rec.summaryTabLink.dataset.available = s.ttyd_running ? "1" : "0";

    // Footer — make the "port N" tag a link that opens the ttyd in a new tab.
    rec.fPort.textContent = "";
    if (s.ttyd_running && s.port) {
        const a = el("a", {
            class: "summary-link",
            target: "_blank", rel: "noopener",
            href: url,
            title: "open ttyd in a new tab",
        }, `ttyd on port ${s.port} ↗`);
        rec.fPort.append(a);
    } else {
        rec.fPort.textContent = `port ${s.port || "—"}`;
    }
    rec.fPid.textContent = `pid ${s.pid || "—"}`;
    rec.fCreated.textContent = `created ${s.created_seconds_ago !== undefined
        ? fmtAgeSeconds(s.created_seconds_ago)
        : fmtAge(s.created)} ago`;
    const workflow = s.agent_name ? workflowEntry(s.agent_name) : { enabled: false };
    rec.workflowToggleInput.checked = !!workflow.enabled;
    rec.workflowToggle.classList.toggle("is-on", !!workflow.enabled);
    rec.workflowToggleText.textContent = workflow.enabled ? "Workflows On" : "Workflows Off";
    setVisible(rec.workflowBtn, !!s.conversation_mode, "");
    setVisible(rec.workflowToggle, !!s.conversation_mode, "inline-flex");

    // Iframe src: set it once when ttyd comes up AND pane is open;
    // never blow it away on refresh unless ttyd went down.
    const iframeUrl = s.ttyd_running ? ttydUrl(s.port) : null;
    const cur = rec.iframe.getAttribute("src") || "";
    if (iframeUrl && state.openPanes.has(s.name) && cur !== iframeUrl) {
        rec.iframe.setAttribute("src", iframeUrl);
    }
    if (!iframeUrl && cur) {
        rec.iframe.removeAttribute("src");
    }
    renderHotButtons(s.name);
    applyDashboardConfigToPane(rec);
}

function sortedSessionNames(names) {
    // Honour state.order first (filtered to existing sessions in their stored
    // order), then append any unordered sessions alphabetically.
    const set = new Set(names);
    const ordered = state.order.filter(n => set.has(n));
    const seen = new Set(ordered);
    const rest = [...names].filter(n => !seen.has(n)).sort();
    return [...ordered, ...rest];
}

function placePane(rec, name) {
    const hidden = state.hidden.has(name);
    rec.hideBtn.textContent = hidden ? "Unhide" : "Hide";
    rec.hideBtn.title = hidden
        ? "unhide this session"
        : "move to the hidden list at the bottom of the page";
    if (rec.hideIconBtn) {
        rec.hideIconBtn.title = hidden ? "unhide this session" : "hide this session";
    }
}

function reappendInOrder() {
    renderLayout();
}

function moveSession(name, delta) {
    if (!state.hidden.has(name)) {
        syncLayoutState();
        const pos = findLayoutPosition(name);
        if (!pos) return;
        removeFromLayout(name);
        const insertAt = delta < 0
            ? Math.max(0, pos.row - 1)
            : Math.min(state.layout.length, pos.row + 1);
        placeSessionRow(name, insertAt);
        persistLayoutState();
        renderLayout();
        return;
    }
    // Build the concrete ordering for the list this session lives in, then
    // swap it with its neighbour. The result becomes the new user order.
    const liveNames = state.sessions.map(s => s.name);
    const bucket = state.hidden.has(name)
        ? liveNames.filter(n => state.hidden.has(n))
        : liveNames.filter(n => !state.hidden.has(n));
    const current = sortedSessionNames(bucket);
    const i = current.indexOf(name);
    const j = i + delta;
    if (i < 0 || j < 0 || j >= current.length) return;
    [current[i], current[j]] = [current[j], current[i]];

    // Merge: both buckets are authoritative for their members; persist a
    // combined order so we don't drop ordering of the other bucket.
    const otherBucket = state.hidden.has(name)
        ? sortedSessionNames(liveNames.filter(n => !state.hidden.has(n)))
        : sortedSessionNames(liveNames.filter(n => state.hidden.has(n)));
    const newOrder = state.hidden.has(name)
        ? [...otherBucket, ...current]
        : [...current, ...otherBucket];
    state.order = newOrder;
    saveOrder(state.order);
    reappendInOrder();
}


function dropOnSession(targetName, draggedName, side = "top") {
    if (!draggedName || draggedName === targetName) return;
    if (side === "left" || side === "right") {
        putSessionBeside(targetName, draggedName, side);
        return;
    }
    if (side === "bottom") {
        placeSessionBelow(targetName, draggedName);
        return;
    }
    // "top" or any other value = insert above
    placeSessionAbove(targetName, draggedName);
}

function refreshHiddenChrome() {
    const wrap = document.getElementById("hidden-wrap");
    const count = document.getElementById("hidden-count");
    // Count only sessions that actually exist — stale entries in the set
    // (e.g., a killed session) shouldn't inflate the badge.
    const liveNames = new Set(state.sessions.map(s => s.name));
    let n = 0;
    for (const h of state.hidden) if (liveNames.has(h)) n += 1;
    count.textContent = String(n);
    wrap.hidden = n === 0;
    // Keep the Config > Pane Groups editor counts fresh too.
    if (typeof renderPaneGroupsEditor === "function") renderPaneGroupsEditor();
}

function toggleHidden(name) {
    if (state.hidden.has(name)) {
        state.hidden.delete(name);
    } else {
        state.hidden.add(name);
        // Hiding a pane also takes it out of any user-defined group so it's
        // only in one place at a time. Unhiding returns it to Visible, not
        // to its previous group (user can Move it back explicitly).
        if (state.groups.membership[name]) {
            delete state.groups.membership[name];
            saveGroups();
        }
        removeFromLayout(name);
    }
    saveHidden(state.hidden);
    persistLayoutState();
    const rec = state.nodes.get(name);
    if (rec) placePane(rec, name);
    refreshHiddenChrome();
    renderLayout();
}


async function refresh() {
    const r = await api("GET", "/api/sessions");
    const sessions = (r && r.sessions) || [];
    state.sessions = sessions;
    showTmuxUnreachableBanner(!!(r && r.tmux_unreachable));
    checkIdleAlerts(sessions);
    await checkHotLoops(sessions);
    await checkSendQueue(sessions);
    const root = document.getElementById("sessions");
    const seen = new Set();

    // Index the raw session list by name so we can walk it in user order.
    const byName = new Map(sessions.map(s => [s.name, s]));
    for (const name of sortedSessionNames(sessions.map(s => s.name))) {
        const s = byName.get(name);
        seen.add(name);
        let rec = state.nodes.get(name);
        if (!rec) {
            rec = createPane(s);
            state.nodes.set(name, rec);
        }
        placePane(rec, name);
        updatePane(rec, s);
    }
    // Remove panes for sessions that no longer exist
    for (const [name, rec] of state.nodes) {
        if (!seen.has(name)) {
            rec.details.remove();
            state.nodes.delete(name);
            state.openPanes.delete(name);
        }
    }

    // Prune hidden-set entries for sessions that no longer exist so the list
    // doesn't grow forever as sessions come and go.
    let changed = false;
    for (const h of [...state.hidden]) {
        if (!seen.has(h)) { state.hidden.delete(h); changed = true; }
    }
    if (changed) saveHidden(state.hidden);

    // Same treatment for state.order — otherwise it grows monotonically
    // as sessions come and go over a long-lived page session.
    const prevOrderLen = state.order.length;
    state.order = state.order.filter(n => seen.has(n));
    if (state.order.length !== prevOrderLen) saveOrder(state.order);

    document.getElementById("count").textContent =
        `${sessions.length} session${sessions.length === 1 ? "" : "s"}`;
    callExt("renderAgentsPane");
    callExt("renderPaneAdmin");
    renderLayout();
    if (state.splitPicker.open) renderSplitPicker();
}

// Surface "tmux server is unreachable" prominently — without this the
// dashboard silently shows "0 sessions" when tmux is hung (memory
// pressure, stuck client) and operators chase ghosts in the dashboard
// code. The banner is purely informational; raw-shell rows still render
// normally underneath.
function showTmuxUnreachableBanner(show) {
    let banner = document.getElementById("tmux-unreachable-banner");
    if (!show) {
        if (banner) banner.hidden = true;
        return;
    }
    if (!banner) {
        banner = document.createElement("div");
        banner.id = "tmux-unreachable-banner";
        banner.className = "ext-restart-banner";
        banner.style.background = "#3b1117";
        banner.style.borderColor = "#8b1e2d";
        banner.textContent = "tmux server is not responding — session list is unavailable. " +
            "Check `tmux ls` from a shell; the server may be wedged (memory pressure, stuck client).";
        const sessionsEl = document.getElementById("sessions");
        sessionsEl.parentNode.insertBefore(banner, sessionsEl);
    }
    banner.hidden = false;
}

// Null-safe wiring helper. Many of the bindings below target DOM IDs
// or handler functions that only exist when an extension is loaded
// (the agent extension contributes the workflow / step-viewer / agent
// editor markup and code; without it those getElementById calls return
// null and the surrounding init would crash, taking the whole
// dashboard with it). ``bind`` skips silently when either side is
// missing so a no-extensions install still boots.
function bind(id, event, handler) {
    const el = document.getElementById(id);
    if (!el || typeof handler !== "function") return;
    el.addEventListener(event, handler);
}

// Extension-call shims. The agent extension exposes its handlers as
// loose globals (window.loadAgents, window.renderAgentsPane, …);
// without it the names are undefined and a direct call throws
// ReferenceError, taking down whichever init/refresh path made the
// call. These helpers funnel every "is the extension here?" check
// through one place — adding a new extension call is just
// ``callExt("foo")`` instead of remembering to write a typeof guard
// at every site.
function callExt(name, ...args) {
    const fn = (typeof window !== "undefined") ? window[name] : undefined;
    return (typeof fn === "function") ? fn(...args) : undefined;
}
async function awaitExt(name, ...args) {
    const fn = (typeof window !== "undefined") ? window[name] : undefined;
    return (typeof fn === "function") ? await fn(...args) : undefined;
}
// Variant of ``bind`` that resolves the handler by name — used when the
// handler itself lives in an extension. Skips silently if either the
// element or the named global is missing.
function bindExt(id, event, handlerName) {
    const fn = (typeof window !== "undefined") ? window[handlerName] : undefined;
    bind(id, event, typeof fn === "function" ? fn : null);
}

document.addEventListener("DOMContentLoaded", async () => {
    // Shield iframes during any drag so drag events reach parent panes
    document.addEventListener("dragstart", () => document.body.classList.add("dragging"));
    document.addEventListener("dragend", () => document.body.classList.remove("dragging"));

    document.getElementById("refresh-btn").addEventListener("click", refresh);
    document.getElementById("new-btn").addEventListener("click", newSession);
    document.getElementById("raw-btn").addEventListener("click", openRawTtyd);
    document.getElementById("restart-btn").addEventListener("click", restartDashboard);
    document.getElementById("os-restart-btn").addEventListener("click", restartDashboard);
    document.getElementById("tmux-help-btn").addEventListener("click", () => {
        document.getElementById("tmux-help-modal").hidden = false;
        syncModalChrome();
    });
    document.getElementById("tmux-help-close-btn").addEventListener("click", () => {
        document.getElementById("tmux-help-modal").hidden = true;
        syncModalChrome();
    });
    document.getElementById("tmux-help-modal").addEventListener("click", (e) => {
        if (e.target.id === "tmux-help-modal") {
            document.getElementById("tmux-help-modal").hidden = true;
            syncModalChrome();
        }
    });
    document.getElementById("launch-claude-btn").addEventListener("click", () => launchCodingSession("claude", "claude"));
    document.getElementById("launch-claude-yolo-btn").addEventListener("click", () => launchCodingSession("claude-yolo", "claude --dangerously-skip-permissions"));
    document.getElementById("launch-codex-btn").addEventListener("click", () => launchCodingSession("codex", "codex"));
    document.getElementById("launch-codex-yolo-btn").addEventListener("click", () => launchCodingSession("codex-yolo", "codex --full-auto"));
    document.getElementById("launch-kimi-btn").addEventListener("click", () => launchCodingSession("kimi", "kimi-code"));
    document.getElementById("launch-kimi-yolo-btn").addEventListener("click", () => launchCodingSession("kimi-yolo", "kimi-code --yolo"));
    document.getElementById("launch-monitor-btn").addEventListener("click", () => launchCodingSession("sysmon", "sysmon"));
    document.getElementById("launch-top-btn").addEventListener("click", () => launchCodingSession("top", "systop"));
    document.getElementById("cfg-save-btn").addEventListener("click", saveDashboardConfig);
    document.getElementById("cfg-load-btn").addEventListener("click", reloadDashboardConfig);
    document.getElementById("cfg-reset-btn").addEventListener("click", resetDashboardConfig);
    document.getElementById("client-nick-btn").addEventListener("click", setClientNickname);
    document.getElementById("config-wrap").addEventListener("click", guardConfigOpen);
    document.getElementById("cfg-clear-cache-btn").addEventListener("click", clearLocalCache);
    document.getElementById("pane-group-add-btn").addEventListener("click", addPaneGroup);
    document.getElementById("pane-group-new-name").addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); addPaneGroup(); }
    });
    document.getElementById("phone-key-add-btn").addEventListener("click", addPhoneKey);
    document.getElementById("phone-key-reset-btn").addEventListener("click", resetPhoneKeys);
    document.getElementById("cfg-lock-set-btn").addEventListener("click", setConfigLock);
    document.getElementById("cfg-lock-clear-btn").addEventListener("click", clearConfigLock);
    bindExt("hooks-save-btn", "click", "saveHooks");
    bindExt("hooks-reset-btn", "click", "resetHooks");
    bindExt("conductor-save-btn", "click", "saveConductor");
    bindExt("conductor-reload-btn", "click", "loadConductor");
    document.getElementById("cfg-toggle-all-topbar").addEventListener("click", (e) => toggleAllSection(TOPBAR_TOGGLE_KEYS, e.currentTarget));
    document.getElementById("cfg-toggle-all-summary").addEventListener("click", (e) => toggleAllSection(SUMMARY_TOGGLE_KEYS, e.currentTarget));
    document.getElementById("cfg-toggle-all-body").addEventListener("click", (e) => toggleAllSection(BODY_TOGGLE_KEYS, e.currentTarget));
    document.getElementById("cfg-sound-test").addEventListener("click", () => {
        primeAudio();
        playIdleTone(document.getElementById("cfg-idle-sound").value);
    });
    // Agent-extension-only bindings — bindExt skips silently when the
    // extension isn't installed, so a no-extensions install still
    // finishes init.
    bindExt("cfg-agent-save-btn", "click", "saveAgentConfig");
    bind("cfg-agent-reload-btn", "click", async () => {
        const ok = await awaitExt("loadAgents");
        if (ok) callExt("setAgentStatus", "reloaded agent list", "ok");
    });
    bindExt("cfg-agent-remove-btn", "click", "removeAgentConfig");
    bindExt("agent-steps-close-btn", "click", "closeAgentSteps");
    bindExt("runs-search-btn", "click", "searchRuns");
    bind("runs-search-q", "keydown", (e) => {
        if (e.key === "Enter") callExt("searchRuns");
    });
    bindExt("task-create-btn", "click", "createTask");
    const fm = callExt("agentFieldMap");
    if (fm) {
        if (fm.existing) fm.existing.addEventListener("change", loadExistingAgentIntoForm);
        if (fm.preset) fm.preset.addEventListener("change", applyAgentPreset);
        if (fm.name) fm.name.addEventListener("input", () => {
            const fields = callExt("agentFieldMap");
            if (!fields) return;
            if (fields.existing.value && fields.name.value.trim() !== fields.existing.value) fields.existing.value = "";
            const constraint = callExt("enforceAgentConstraint");
            if (constraint) callExt("setAgentStatus", constraint.message, "dim");
        });
    }
    for (const input of Object.values(configFieldMap())) {
        if (!input) continue;
        input.addEventListener("input", previewDashboardConfig);
        input.addEventListener("change", previewDashboardConfig);
    }
    document.getElementById("hot-close-btn").addEventListener("click", closeHotButtons);
    document.getElementById("hot-save-btn").addEventListener("click", saveHotButton);
    document.getElementById("hot-clear-btn").addEventListener("click", clearHotButton);
    bind("workflow-close-btn", "click", closeWorkflowEditor);
    bindExt("workflow-save-btn", "click", "saveWorkflowEditor");
    bindExt("workflow-clear-btn", "click", "clearWorkflowEditor");
    document.getElementById("idle-close-btn").addEventListener("click", closeIdleEditor);
    document.getElementById("idle-save-btn").addEventListener("click", saveIdleEditor);
    document.getElementById("idle-clear-btn").addEventListener("click", clearIdleEditor);
    document.getElementById("split-close-btn").addEventListener("click", closeSplitPicker);
    document.getElementById("split-search").addEventListener("input", (e) => {
        state.splitPicker.filter = e.target.value || "";
        renderSplitPicker();
    });
    bind("agent-steps-modal", "click", (e) => {
        if (e.target.id === "agent-steps-modal") callExt("closeAgentSteps");
    });
    bind("workflow-modal", "click", (e) => {
        if (e.target.id === "workflow-modal") closeWorkflowEditor();
    });
    document.getElementById("hot-modal").addEventListener("click", (e) => {
        if (e.target.id === "hot-modal") closeHotButtons();
    });
    document.getElementById("idle-modal").addEventListener("click", (e) => {
        if (e.target.id === "idle-modal") closeIdleEditor();
    });
    document.getElementById("split-modal").addEventListener("click", (e) => {
        if (e.target.id === "split-modal") closeSplitPicker();
    });
    document.getElementById("new-name").addEventListener("keydown", (e) => {
        if (e.key === "Enter") newSession();
    });
    document.addEventListener("pointerdown", primeAudio, { passive: true });
    document.addEventListener("keydown", primeAudio);
    document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape") return;
        if (state.stepViewer && state.stepViewer.open) callExt("closeAgentSteps");
        if (state.hotEditor.open) closeHotButtons();
        if (state.workflowEditor && state.workflowEditor.open) closeWorkflowEditor();
        if (state.idleEditor.open) closeIdleEditor();
        if (state.splitPicker.open) closeSplitPicker();
    });
    renderConfigForm();
    checkImportCfgParam();
    applyTopbarConfig();
    callExt("renderAgentSelectors");
    renderPhoneKeysPreview();
    await checkConfigLock();
    await loadDashboardConfig();
    await awaitExt("loadAgents");
    callExt("populateRunAgentFilter");
    callExt("populateTaskAgentSelect");
    await awaitExt("loadAgentWorkflows");
    await refresh();
    await awaitExt("searchRuns");
    await awaitExt("loadTasks");
    await awaitExt("loadCostSummary");
    await awaitExt("loadHooks");
    await awaitExt("loadConductor");
    await awaitExt("loadNotifications");
    await loadClients();
    scheduleRefreshLoop();
    setInterval(pollIdleOnly, 60000);
    setInterval(loadClients, 15000);
    setInterval(checkClientInbox, 10000);
});
