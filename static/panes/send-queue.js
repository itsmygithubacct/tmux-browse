// Send-bar repeater. ``sendToPane`` either fires once and returns or,
// when the count is > 1, queues the remaining sends and lets
// ``checkSendQueue`` fire each one after the pane has been idle long
// enough (state.config.hot_loop_idle_seconds + a 60s cooldown).
//
// renderSendQueueStatus updates the per-pane "waiting / cooldown /
// sending" inline label that the dashboard shows next to the send
// bar; sendKeysToPane is the thin POST wrapper used by hardware-key
// rows in the phone-keyboard addon.

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
