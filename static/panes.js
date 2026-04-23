// panes.js — session panes, layout, hot buttons, idle alerts, modals, refresh

async function resizePane(session, cols) {
    await api("POST", "/api/session/resize", { session, cols });
    const rec = state.nodes.get(session);
    if (rec && rec.iframeWrap) {
        const defaultH = state.config.default_ttyd_height_vh || 70;
        rec.iframeWrap.style.height = `${defaultH}vh`;
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

async function sendToPane(session, inputEl) {
    const text = inputEl.value.trim();
    if (!text) return;
    const r = await api("POST", "/api/session/type", { session, text });
    if (r.ok) inputEl.value = "";
}

async function sendKeysToPane(session, keys) {
    await api("POST", "/api/session/key", { session, keys });
}

async function openRawTtyd() {
    const tab = window.open("about:blank", "_blank", "noopener");
    const r = await api("POST", "/api/ttyd/raw", {});
    if (!r.ok) {
        if (tab) tab.close();
        alert("Error: " + (r.error || "unknown"));
        return;
    }
    const pageUrl = `/raw-ttyd?name=${encodeURIComponent(r.name || "")}&port=${encodeURIComponent(r.port || "")}&scheme=${encodeURIComponent(r.scheme || "")}`;
    if (tab) tab.location = pageUrl;
    else window.open(pageUrl, "_blank", "noopener");
}

async function enterCopyMode(session) {
    const msg = document.getElementById("msg-" + cssId(session));
    const r = await api("POST", "/api/session/scroll", { session });
    if (msg) {
        msg.textContent = r.ok ? "scroll mode" : ("error: " + (r.error || ""));
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
    return state.sessions.map((s) => s.name).filter((n) => !state.hidden.has(n));
}

function hiddenSessionNames() {
    return state.sessions.map((s) => s.name).filter((n) => state.hidden.has(n));
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
    document.getElementById("idle-threshold").value = cfg.thresholdSec;
    document.getElementById("idle-sound").checked = cfg.sound;
    document.getElementById("idle-prompt").checked = cfg.prompt;
}

function saveIdleEditor() {
    const session = state.idleEditor.session;
    const enabled = document.getElementById("idle-enabled").checked;
    const threshold = Math.max(5, Math.floor(Number(document.getElementById("idle-threshold").value) || 300));
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
    const agent = state.workflowEditor.agent;
    const slot = state.workflowEditor.slot;
    const entry = workflowEntry(agent);
    const slots = entry.workflows;
    const title = document.getElementById("workflow-modal-title");
    const list = document.getElementById("workflow-slot-list");
    const row = slots[slot] || { name: "", prompt: "", interval_seconds: 300 };
    title.textContent = `Agent Workflows · ${agent}`;
    document.getElementById("workflow-name").value = row.name;
    document.getElementById("workflow-prompt").value = row.prompt;
    document.getElementById("workflow-interval").value = row.interval_seconds;
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
    state.workflowEditor.open = true;
    state.workflowEditor.agent = (agentName || "").trim().toLowerCase();
    state.workflowEditor.slot = slot;
    workflowEntry(state.workflowEditor.agent);
    renderWorkflowEditor();
    document.getElementById("workflow-modal").hidden = false;
    syncModalChrome();
}

function closeWorkflowEditor() {
    state.workflowEditor.open = false;
    document.getElementById("workflow-modal").hidden = true;
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
    const sname = el("span", { class: "sname" }, s.name);
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
    const idleWrap = el("span", { class: "summary-idle-wrap" }, idle, idleAlertBtn);
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
        href: `/api/session/log?session=${encodeURIComponent(s.name)}`,
        style: "text-decoration:none",
    }, "Log");
    const scrollBtn = el("button", {
        class: "btn orange summary-scroll",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            enterCopyMode(s.name);
        },
        title: "enter tmux copy-mode so you can scroll back (equivalent to C-b [)",
    }, "Scroll");
    const hideBtn = el("button", {
        class: "btn red summary-hide",
        onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            toggleHidden(s.name);
        },
        title: "move to the hidden list at the bottom of the page",
    }, "Hide");
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
    const wcMaximize = el("button", {
        class: "wc-btn wc-maximize", type: "button",
        title: "maximize (resize to 160 columns)",
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); resizePane(s.name, 160); },
    }, "\u25a1");
    const wcClose = el("button", {
        class: "wc-btn wc-close", type: "button",
        title: "close (kill session)",
        onclick: (e) => { e.preventDefault(); e.stopPropagation(); killSession(s.name); },
    }, "\u00d7");
    const wcControls = el("span", { class: "wc-controls" }, wcMinimize, wcMaximize, wcClose);

    const summary = el("summary", { draggable: "true" },
        sname, msg, sbadges, idleWrap,
        el("span", { class: "summary-actions" },
            summaryTabLink, logLink, scrollBtn, splitBtn, hideBtn, reorderPad, wcControls),
    );
    const bodyKillBtn = el("button", {
        class: "btn red", onclick: () => killSession(s.name),
    }, "Kill");
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
    const sendBtn = el("button", { class: "btn green", onclick: () => sendToPane(s.name, sendInput) }, "Send");
    sendInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendToPane(s.name, sendInput); });
    const sendBar = el("div", { class: "send-bar" }, sendInput, sendBtn);

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
    const details = el("details", { class: "session", "data-session": s.name },
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
        details, sbadges, idle, idleWrap, idleAlertBtn,
        summaryTabLink, logLink, scrollBtn, splitBtn, hideBtn, reorderPad,
        launchBtn, stopBtn, killBtn: bodyKillBtn, hotManageBtn, msg,
        wcClose, wcMaximize, wcMinimize,
        workflowBtn, workflowToggle, workflowToggleInput, workflowToggleText,
        iframe, iframeWrap, sendBar, phoneKeys, fPort, fPid, fCreated, footer,
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
    rec.hideBtn.textContent = state.hidden.has(name) ? "Unhide" : "Hide";
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
}

function toggleHidden(name) {
    if (state.hidden.has(name)) state.hidden.delete(name);
    else {
        state.hidden.add(name);
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
    checkIdleAlerts(sessions);
    await checkHotLoops(sessions);
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
    renderAgentsPane();
    renderPaneAdmin();
    renderLayout();
    if (state.splitPicker.open) renderSplitPicker();
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
    document.getElementById("cfg-save-btn").addEventListener("click", saveDashboardConfig);
    document.getElementById("cfg-load-btn").addEventListener("click", reloadDashboardConfig);
    document.getElementById("cfg-reset-btn").addEventListener("click", resetDashboardConfig);
    document.getElementById("client-nick-btn").addEventListener("click", setClientNickname);
    document.getElementById("config-wrap").addEventListener("click", guardConfigOpen);
    document.getElementById("cfg-qr-show-btn").addEventListener("click", showConfigQR);
    document.getElementById("cfg-qr-scan-btn").addEventListener("click", scanConfigQR);
    document.getElementById("qr-close-btn").addEventListener("click", closeQRModal);
    document.getElementById("qr-modal").addEventListener("click", (e) => { if (e.target.id === "qr-modal") closeQRModal(); });
    document.getElementById("phone-key-add-btn").addEventListener("click", addPhoneKey);
    document.getElementById("phone-key-reset-btn").addEventListener("click", resetPhoneKeys);
    document.getElementById("cfg-lock-set-btn").addEventListener("click", setConfigLock);
    document.getElementById("cfg-lock-clear-btn").addEventListener("click", clearConfigLock);
    document.getElementById("hooks-save-btn").addEventListener("click", saveHooks);
    document.getElementById("hooks-reset-btn").addEventListener("click", resetHooks);
    document.getElementById("cfg-toggle-all-topbar").addEventListener("click", (e) => toggleAllSection(TOPBAR_TOGGLE_KEYS, e.currentTarget));
    document.getElementById("cfg-toggle-all-summary").addEventListener("click", (e) => toggleAllSection(SUMMARY_TOGGLE_KEYS, e.currentTarget));
    document.getElementById("cfg-toggle-all-body").addEventListener("click", (e) => toggleAllSection(BODY_TOGGLE_KEYS, e.currentTarget));
    document.getElementById("cfg-sound-test").addEventListener("click", () => {
        primeAudio();
        playIdleTone(document.getElementById("cfg-idle-sound").value);
    });
    document.getElementById("cfg-agent-save-btn").addEventListener("click", saveAgentConfig);
    document.getElementById("cfg-agent-reload-btn").addEventListener("click", async () => {
        const ok = await loadAgents();
        if (ok) setAgentStatus("reloaded agent list", "ok");
    });
    document.getElementById("cfg-agent-remove-btn").addEventListener("click", removeAgentConfig);
    document.getElementById("agent-steps-close-btn").addEventListener("click", closeAgentSteps);
    document.getElementById("runs-search-btn").addEventListener("click", searchRuns);
    document.getElementById("runs-search-q").addEventListener("keydown", (e) => { if (e.key === "Enter") searchRuns(); });
    document.getElementById("task-create-btn").addEventListener("click", createTask);
    agentFieldMap().existing.addEventListener("change", loadExistingAgentIntoForm);
    agentFieldMap().preset.addEventListener("change", applyAgentPreset);
    agentFieldMap().name.addEventListener("input", () => {
        const fields = agentFieldMap();
        if (fields.existing.value && fields.name.value.trim() !== fields.existing.value) fields.existing.value = "";
        const constraint = enforceAgentConstraint();
        if (constraint) setAgentStatus(constraint.message, "dim");
    });
    for (const input of Object.values(configFieldMap())) {
        if (!input) continue;
        input.addEventListener("input", previewDashboardConfig);
        input.addEventListener("change", previewDashboardConfig);
    }
    document.getElementById("hot-close-btn").addEventListener("click", closeHotButtons);
    document.getElementById("hot-save-btn").addEventListener("click", saveHotButton);
    document.getElementById("hot-clear-btn").addEventListener("click", clearHotButton);
    document.getElementById("workflow-close-btn").addEventListener("click", closeWorkflowEditor);
    document.getElementById("workflow-save-btn").addEventListener("click", saveWorkflowEditor);
    document.getElementById("workflow-clear-btn").addEventListener("click", clearWorkflowEditor);
    document.getElementById("idle-close-btn").addEventListener("click", closeIdleEditor);
    document.getElementById("idle-save-btn").addEventListener("click", saveIdleEditor);
    document.getElementById("idle-clear-btn").addEventListener("click", clearIdleEditor);
    document.getElementById("split-close-btn").addEventListener("click", closeSplitPicker);
    document.getElementById("split-search").addEventListener("input", (e) => {
        state.splitPicker.filter = e.target.value || "";
        renderSplitPicker();
    });
    document.getElementById("agent-steps-modal").addEventListener("click", (e) => {
        if (e.target.id === "agent-steps-modal") closeAgentSteps();
    });
    document.getElementById("hot-modal").addEventListener("click", (e) => {
        if (e.target.id === "hot-modal") closeHotButtons();
    });
    document.getElementById("workflow-modal").addEventListener("click", (e) => {
        if (e.target.id === "workflow-modal") closeWorkflowEditor();
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
        if (e.key === "Escape" && state.stepViewer.open) closeAgentSteps();
        if (e.key === "Escape" && state.hotEditor.open) closeHotButtons();
        if (e.key === "Escape" && state.workflowEditor.open) closeWorkflowEditor();
        if (e.key === "Escape" && state.idleEditor.open) closeIdleEditor();
        if (e.key === "Escape" && state.splitPicker.open) closeSplitPicker();
    });
    renderConfigForm();
    checkImportCfgParam();
    applyTopbarConfig();
    renderAgentSelectors();
    renderPhoneKeysPreview();
    await checkConfigLock();
    await loadDashboardConfig();
    await loadAgents();
    populateRunAgentFilter();
    populateTaskAgentSelect();
    await loadAgentWorkflows();
    await refresh();
    await searchRuns();
    await loadTasks();
    await loadCostSummary();
    await loadHooks();
    await loadNotifications();
    await loadClients();
    scheduleRefreshLoop();
    setInterval(loadClients, 15000);
    setInterval(checkClientInbox, 10000);
});
