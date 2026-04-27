// Shared hot buttons (per-page, persisted to localStorage via state.js)
// plus per-session hot loops that fire a saved command after the
// pane has been idle for ``hot_loop_idle_seconds``.
//
// renderHotButtons is called from the per-pane render path in panes.js;
// sendHotButton/checkHotLoops are called from refresh; the editor
// modal (open/close/select/save/clear/render) is wired from the
// DOMContentLoaded handler.

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
