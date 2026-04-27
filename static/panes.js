// panes.js — refresh loop, init, cross-cutting helpers.
//
// Per-feature code lives in static/panes/<feature>.js, concatenated in
// declared order by lib/static.py. The split keeps each feature small
// enough to read in one screenful while preserving the no-build-step
// constraint:
//
//   idle-alerts.js   per-session idle alerts
//   hot-buttons.js   shared hot buttons + per-session hot loops
//   send-queue.js    send-bar single + repeat-with-cooldown queue
//   lifecycle.js     launch/stop ttyd, kill/new session, raw shells,
//                    iframe-fit helpers, restart dashboard
//   layout.js        drag/drop, ordering, hidden / pane-group bookkeeping
//   modals.js        workflow editor + split picker
//   render.js        createPane + updatePane (per-session DOM)
//
// Functions in those files reach core via top-level ``function``
// declarations that hoist into ``window`` after concatenation. This
// file (panes.js) loads last among the panes/* files, so its
// DOMContentLoaded handler can call into anything declared earlier.

// applySessions is the DOM-update half of refresh(). Both the
// polling path (refresh()) and the SSE path (startSessionStream())
// feed this same function so they share the dedup, ordering,
// hidden-set GC, and render-pane diff logic.
async function applySessions(sessions, tmuxUnreachable) {
    state.sessions = sessions;
    showTmuxUnreachableBanner(!!tmuxUnreachable);
    checkIdleAlerts(sessions);
    await checkHotLoops(sessions);
    await checkSendQueue(sessions);
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

async function refresh() {
    const r = await api("GET", "/api/sessions");
    const sessions = (r && r.sessions) || [];
    await applySessions(sessions, !!(r && r.tmux_unreachable));
}

// SSE subscriber. When the dashboard's refresh_strategy is "sse"
// (default) and the browser supports EventSource, we hold open a
// single long-lived /api/sessions/stream connection and feed each
// pushed payload into applySessions(). Returns true on successful
// open; false if SSE is unsupported or disabled by config (caller
// falls back to interval polling).
function startSessionStream() {
    if (state.sessionStream) return true;  // already running
    if (state.config.refresh_strategy === "poll") return false;
    if (typeof EventSource === "undefined") return false;
    let ev;
    try {
        ev = new EventSource("/api/sessions/stream");
    } catch (_) {
        return false;
    }
    ev.onmessage = (e) => {
        let data;
        try { data = JSON.parse(e.data); }
        catch (_) { return; }
        const sessions = (data && data.sessions) || [];
        applySessions(sessions, !!(data && data.tmux_unreachable))
            .catch(() => {});
    };
    ev.onerror = () => {
        // EventSource auto-reconnects on transient failures. We log
        // for diagnosis but don't tear down — the browser handles it.
    };
    state.sessionStream = ev;
    return true;
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
    // Try SSE first (default); fall back to interval polling driven
    // by the existing scheduleRefreshLoop when SSE is disabled,
    // unsupported, or the config flag asks for polling.
    if (!startSessionStream()) {
        scheduleRefreshLoop();
    }
    setInterval(pollIdleOnly, 60000);
    setInterval(loadClients, 15000);
    setInterval(checkClientInbox, 10000);
    startFederationPoll();
});
