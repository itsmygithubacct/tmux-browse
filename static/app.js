
const HIDDEN_KEY = "tmux-browse:hidden";
const ORDER_KEY  = "tmux-browse:order";
const LAYOUT_KEY = "tmux-browse:layout";
const HOT_KEY    = "tmux-browse:hot-buttons";
const IDLE_KEY   = "tmux-browse:idle-alerts";
const PHONE_KEYS_KEY = "tmux-browse:phone-keys";
const AGENT_CONVERSATION_PREFIX = "agent-repl-";
const IDLE_SOUND_CHOICES = ["beep", "chime", "knock", "bell", "blip", "ding"];
const DASHBOARD_CONFIG_DEFAULTS = {
    auto_refresh: false,
    refresh_seconds: 5,
    hot_loop_idle_seconds: 5,
    agent_max_steps: 20,
    launch_on_expand: true,
    default_ttyd_height_vh: 70,
    default_ttyd_min_height_px: 200,
    day_mode: false,
    idle_sound: "beep",
    show_topbar: true,
    show_topbar_title: true,
    show_topbar_count: true,
    show_topbar_new_session: true,
    show_topbar_raw_ttyd: true,
    show_topbar_refresh: true,
    show_topbar_restart: true,
    show_topbar_status: true,
    show_summary_row: true,
    show_summary_name: true,
    show_summary_arrow: true,
    furl_side_by_side: true,
    resize_row_together: true,
    show_body_actions: true,
    show_footer: true,
    show_inline_messages: true,
    show_attached_badge: true,
    show_window_badge: true,
    show_port_badge: true,
    show_idle_text: true,
    show_idle_alert_button: true,
    show_summary_open: true,
    show_summary_log: true,
    show_summary_scroll: true,
    show_summary_split: true,
    show_summary_hide: true,
    show_summary_reorder: true,
    show_body_launch: false,
    show_body_stop: false,
    show_body_kill: false,
    show_body_send_bar: false,
    show_body_phone_keys: false,
    show_body_hot_buttons: true,
    show_hot_loop_toggles: true,
};

function loadJSON(key, fallback) {
    try {
        const raw = localStorage.getItem(key);
        if (!raw) return fallback;
        return JSON.parse(raw);
    } catch { return fallback; }
}
function saveJSON(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); }
    catch { /* quota / private mode — ignore */ }
}

function normalizeHotSlot(value) {
    if (typeof value === "string") {
        const text = value.trim();
        return { name: text ? hotButtonLabel(text) : "", text, loopCount: 0 };
    }
    if (value && typeof value === "object") {
        const name = typeof value.name === "string" ? value.name.trim() : "";
        const text = typeof value.text === "string" ? value.text.trim() : "";
        const rawLoopCount = Number(value.loopCount);
        const loopCount = Number.isFinite(rawLoopCount) && rawLoopCount >= 0
            ? Math.floor(rawLoopCount)
            : 0;
        return { name, text, loopCount };
    }
    return { name: "", text: "", loopCount: 0 };
}

function normalizeHotButtons(value) {
    const raw = Array.isArray(value) ? value.slice(0, 32) : [];
    while (raw.length < 32) raw.push({ name: "", text: "" });
    return raw.map(normalizeHotSlot);
}

function normalizeIdleAlert(value) {
    const raw = value && typeof value === "object" ? value : {};
    const thresholdSec = Number(raw.thresholdSec);
    return {
        enabled: !!raw.enabled,
        thresholdSec: Number.isFinite(thresholdSec) && thresholdSec >= 5 ? Math.floor(thresholdSec) : 300,
        sound: raw.sound !== false,
        prompt: !!raw.prompt,
    };
}

function normalizeWorkflowSlot(value) {
    const raw = value && typeof value === "object" ? value : {};
    const interval = Number(raw.interval_seconds);
    return {
        name: typeof raw.name === "string" ? raw.name.trim() : "",
        prompt: typeof raw.prompt === "string" ? raw.prompt.trim() : "",
        interval_seconds: Number.isFinite(interval) ? Math.max(5, Math.min(86400, Math.floor(interval))) : 300,
    };
}

function normalizeAgentWorkflowConfig(value) {
    const raw = value && typeof value === "object" ? value : {};
    const agents = raw.agents && typeof raw.agents === "object" ? raw.agents : {};
    const out = { agents: {} };
    for (const [name, spec] of Object.entries(agents)) {
        const workflows = Array.isArray(spec && spec.workflows) ? spec.workflows.slice(0, 8) : [];
        while (workflows.length < 8) workflows.push({ name: "", prompt: "", interval_seconds: 300 });
        out.agents[name] = {
            enabled: !!(spec && spec.enabled),
            workflows: workflows.map(normalizeWorkflowSlot),
        };
    }
    return out;
}

function normalizeDashboardConfig(value) {
    const raw = value && typeof value === "object" ? value : {};
    const cfg = { ...DASHBOARD_CONFIG_DEFAULTS };
    const boolKeys = Object.entries(DASHBOARD_CONFIG_DEFAULTS)
        .filter(([, v]) => typeof v === "boolean")
        .map(([k]) => k);
    for (const key of boolKeys) {
        cfg[key] = typeof raw[key] === "boolean" ? raw[key] : DASHBOARD_CONFIG_DEFAULTS[key];
    }
    const ints = {
        refresh_seconds: [1, 300],
        hot_loop_idle_seconds: [1, 3600],
        agent_max_steps: [1, 1000],
        default_ttyd_height_vh: [20, 95],
        default_ttyd_min_height_px: [120, 900],
    };
    for (const [key, [lo, hi]] of Object.entries(ints)) {
        const n = Number(raw[key]);
        cfg[key] = Number.isFinite(n) ? Math.max(lo, Math.min(hi, Math.floor(n))) : DASHBOARD_CONFIG_DEFAULTS[key];
    }
    cfg.idle_sound = IDLE_SOUND_CHOICES.includes(raw.idle_sound)
        ? raw.idle_sound : DASHBOARD_CONFIG_DEFAULTS.idle_sound;
    return cfg;
}

const state = {
    sessions: [],
    openPanes: new Set(),
    nodes: new Map(),
    hidden: new Set(loadJSON(HIDDEN_KEY, [])),
    order: loadJSON(ORDER_KEY, []),   // user-defined priority list; unlisted sessions sort after
    layout: loadJSON(LAYOUT_KEY, []),
    config: normalizeDashboardConfig(DASHBOARD_CONFIG_DEFAULTS),
    configPath: "",
    refreshTimer: null,
    hot: normalizeHotButtons(loadJSON(HOT_KEY, [])),
    hotEditor: { open: false, slot: 0, session: "" },
    idleAlerts: loadJSON(IDLE_KEY, {}),
    idleRuntime: {},
    idleEditor: { open: false, session: "" },
    splitPicker: { open: false, session: "", filter: "" },
    workflowEditor: { open: false, agent: "", slot: 0 },
    stepViewer: { open: false, agent: "", entries: [], selected: 0, path: "" },
    workflowConfig: normalizeAgentWorkflowConfig({}),
    workflowPath: "",
    workflowServerState: {},
    schedulerRunning: false,
    audioCtx: null,
    hotLoops: {},
    agents: [],
    agentDefaults: [],
    agentPaths: { agents: "", secrets: "" },
};

function saveHidden(set) { saveJSON(HIDDEN_KEY, [...set]); }
function saveOrder(list) { saveJSON(ORDER_KEY, list); }
function saveLayout(rows) { saveJSON(LAYOUT_KEY, rows); }
function saveHot() { saveJSON(HOT_KEY, state.hot); }
function saveIdleAlerts() { saveJSON(IDLE_KEY, state.idleAlerts); }

function el(tag, attrs, ...children) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
        if (k === "class") e.className = v;
        else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
        else if (v !== undefined && v !== null) e.setAttribute(k, v);
    }
    for (const c of children) {
        if (c === null || c === undefined) continue;
        e.append(c.nodeType ? c : document.createTextNode(String(c)));
    }
    return e;
}

function killClick(session) {
    return (e) => {
        // Buttons inside <summary> would otherwise toggle the <details>.
        e.preventDefault();
        e.stopPropagation();
        killSession(session);
    };
}

// Any interactive element inside <summary> will otherwise toggle the pane.
function stopSummaryToggle(e) {
    e.stopPropagation();
}

function syncModalChrome() {
    const open = state.hotEditor.open || state.idleEditor.open || state.splitPicker.open || state.workflowEditor.open || state.stepViewer.open;
    document.body.style.overflow = open ? "hidden" : "";
}

function configFieldMap() {
    return {
        auto_refresh: document.getElementById("cfg-auto-refresh"),
        refresh_seconds: document.getElementById("cfg-refresh-seconds"),
        hot_loop_idle_seconds: document.getElementById("cfg-hot-loop-idle-seconds"),
        agent_max_steps: document.getElementById("cfg-agent-max-steps"),
        launch_on_expand: document.getElementById("cfg-launch-on-expand"),
        default_ttyd_height_vh: document.getElementById("cfg-default-height"),
        default_ttyd_min_height_px: document.getElementById("cfg-min-height"),
        day_mode: document.getElementById("cfg-day-mode"),
        idle_sound: document.getElementById("cfg-idle-sound"),
        show_topbar: document.getElementById("cfg-show-topbar"),
        show_topbar_title: document.getElementById("cfg-show-topbar-title"),
        show_topbar_count: document.getElementById("cfg-show-topbar-count"),
        show_topbar_new_session: document.getElementById("cfg-show-topbar-new-session"),
        show_topbar_raw_ttyd: document.getElementById("cfg-show-topbar-raw-ttyd"),
        show_topbar_refresh: document.getElementById("cfg-show-topbar-refresh"),
        show_topbar_restart: document.getElementById("cfg-show-topbar-restart"),
        show_summary_row: document.getElementById("cfg-show-summary-row"),
        show_summary_name: document.getElementById("cfg-show-summary-name"),
        show_summary_arrow: document.getElementById("cfg-show-summary-arrow"),
        furl_side_by_side: document.getElementById("cfg-furl-side-by-side"),
        resize_row_together: document.getElementById("cfg-resize-row-together"),
        show_body_actions: document.getElementById("cfg-show-body-actions"),
        show_attached_badge: document.getElementById("cfg-show-attached-badge"),
        show_window_badge: document.getElementById("cfg-show-window-badge"),
        show_port_badge: document.getElementById("cfg-show-port-badge"),
        show_idle_text: document.getElementById("cfg-show-idle-text"),
        show_idle_alert_button: document.getElementById("cfg-show-idle-alert-button"),
        show_summary_open: document.getElementById("cfg-show-summary-open"),
        show_summary_log: document.getElementById("cfg-show-summary-log"),
        show_summary_scroll: document.getElementById("cfg-show-summary-scroll"),
        show_summary_split: document.getElementById("cfg-show-summary-split"),
        show_summary_hide: document.getElementById("cfg-show-summary-hide"),
        show_summary_reorder: document.getElementById("cfg-show-summary-reorder"),
        show_body_launch: document.getElementById("cfg-show-body-launch"),
        show_body_stop: document.getElementById("cfg-show-body-stop"),
        show_body_kill: document.getElementById("cfg-show-body-kill"),
        show_body_send_bar: document.getElementById("cfg-show-body-send-bar"),
        show_body_phone_keys: document.getElementById("cfg-show-body-phone-keys"),
        show_body_hot_buttons: document.getElementById("cfg-show-body-hot-buttons"),
        show_hot_loop_toggles: document.getElementById("cfg-show-hot-loop-toggles"),
        show_footer: document.getElementById("cfg-show-footer"),
        show_inline_messages: document.getElementById("cfg-show-inline-messages"),
        show_topbar_status: document.getElementById("cfg-show-topbar-status"),
    };
}

function setVisible(node, visible, display = "") {
    if (!node) return;
    node.hidden = !visible;
    node.style.display = visible ? display : "none";
}

function setConfigStatus(text, tone = "dim") {
    const node = document.getElementById("cfg-status");
    if (!node) return;
    node.textContent = text;
    node.className = tone;
}

function setAgentStatus(text, tone = "dim") {
    const node = document.getElementById("cfg-agent-status");
    if (!node) return;
    node.textContent = text;
    node.className = tone;
}

function agentFieldMap() {
    return {
        existing: document.getElementById("cfg-agent-existing"),
        preset: document.getElementById("cfg-agent-preset"),
        name: document.getElementById("cfg-agent-name"),
        provider: document.getElementById("cfg-agent-provider"),
        model: document.getElementById("cfg-agent-model"),
        base_url: document.getElementById("cfg-agent-base-url"),
        wire_api: document.getElementById("cfg-agent-wire-api"),
        sandbox: document.getElementById("cfg-agent-sandbox"),
        api_key: document.getElementById("cfg-agent-api-key"),
    };
}

function agentSummaryText() {
    const bits = [];
    if (state.agents.length) bits.push(`configured: ${state.agents.map(r => r.name).join(", ")}`);
    else bits.push("configured: none");
    if (state.agentPaths.agents) bits.push(state.agentPaths.agents);
    return bits.join(" · ");
}

function conversationSessionName(agentName) {
    return AGENT_CONVERSATION_PREFIX + (agentName || "").trim().toLowerCase();
}

function workflowEntry(agentName) {
    const name = (agentName || "").trim().toLowerCase();
    if (!state.workflowConfig.agents[name]) {
        state.workflowConfig.agents[name] = {
            enabled: false,
            workflows: Array.from({ length: 8 }, () => ({ name: "", prompt: "", interval_seconds: 300 })),
        };
    }
    return state.workflowConfig.agents[name];
}

function agentStatusLabel(status) {
    const labels = {
        running: "Running",
        idle: "Idle",
        error: "Error",
        rate_limited: "Rate Limited",
        workflow_paused: "Paused",
    };
    return labels[status] || status || "unknown";
}

function agentLastActivity(ts) {
    if (!ts) return "";
    return fmtAgeSeconds(Math.max(0, Math.floor(Date.now() / 1000) - ts)) + " ago";
}

function renderAgentsPane() {
    const wrap = document.getElementById("agents-wrap");
    const count = document.getElementById("agents-count");
    const root = document.getElementById("agents-pane");
    if (!wrap || !count || !root) return;
    count.textContent = String(state.agents.length);
    wrap.hidden = state.agents.length === 0;
    root.innerHTML = "";
    for (const row of state.agents) {
        const sessionName = conversationSessionName(row.name);
        const live = state.sessions.find((s) => s.name === sessionName);
        const st = row.status || "idle";
        const reason = row.status_reason || "";
        const lastTs = row.last_activity_ts || 0;
        const statusLine = [];
        if (reason) statusLine.push(reason);
        const lastAct = agentLastActivity(lastTs);
        if (lastAct) statusLine.push(lastAct);
        if (live) statusLine.push(`session ${sessionName} on port ${live.port || "—"}`);

        root.append(el("section", { class: "agent-card" },
            el("div", { class: "agent-card-head" },
                el("div", {},
                    el("div", { class: "agent-card-title" }, row.name),
                    el("div", { class: "dim agent-card-meta" }, `${row.provider || "custom"} · ${row.model || "no model"}`),
                ),
                el("div", { class: "agent-card-actions" },
                    el("button", {
                        class: "btn blue",
                        type: "button",
                        onclick: () => openAgentSteps(row.name),
                    }, "Steps"),
                    el("a", {
                        class: "btn",
                        target: "_blank",
                        rel: "noopener",
                        href: `/api/agent-log?name=${encodeURIComponent(row.name)}`,
                    }, "Log"),
                    el("button", {
                        class: "btn green",
                        type: "button",
                        onclick: () => openAgentConversation(row.name),
                    }, live ? "Open REPL" : "Start REPL"),
                    el("button", {
                        class: "btn",
                        type: "button",
                        onclick: () => forkAgentConversation(row.name),
                    }, "Fork REPL"),
                ),
            ),
            el("div", { class: "agent-card-status" },
                el("span", { class: `agent-status-badge s-${st}` }, agentStatusLabel(st)),
                el("span", {}, statusLine.join(" · ")),
            ),
        ));
    }
}

// --- Costs ---

async function loadCostSummary() {
    const node = document.getElementById("cost-summary");
    if (!node) return;
    const r = await api("GET", "/api/agent-costs");
    if (!r.ok) { node.textContent = ""; return; }
    const agents = r.per_agent || {};
    const names = Object.keys(agents);
    if (!names.length) { node.textContent = ""; return; }
    const parts = names.map((name) => {
        const a = agents[name];
        return `${name}: ${(a.total_tokens || 0).toLocaleString()} tokens (${a.runs} runs)`;
    });
    node.textContent = "Usage: " + parts.join(" · ");
}

// --- Tasks ---

async function loadTasks() {
    const r = await api("GET", "/api/tasks");
    if (!r.ok) return;
    renderTasksPane(r.tasks || []);
}

function renderTasksPane(tasks) {
    const count = document.getElementById("tasks-count");
    const root = document.getElementById("tasks-pane");
    if (!root) return;
    if (count) count.textContent = String(tasks.length);
    root.innerHTML = "";
    if (!tasks.length) {
        root.append(el("div", { class: "dim" }, "(no tasks)"));
        return;
    }
    for (const t of tasks) {
        const statusCls = `task-status-${t.status || "open"}`;
        root.append(el("div", { class: "run-row" },
            el("span", { class: statusCls, style: "font-weight:700;font-size:0.82rem" },
                (t.status || "open").toUpperCase()),
            el("div", {},
                el("div", {}, `${t.title || "untitled"}`),
                el("div", { class: "run-row-meta" },
                    [
                        t.agent ? `agent: ${t.agent}` : null,
                        t.worktree_path ? `worktree` : null,
                        t.repo_path || null,
                    ].filter(Boolean).join(" · "),
                ),
            ),
            el("div", { class: "agent-card-actions" },
                t.agent && t.status === "open"
                    ? el("button", { class: "btn green", type: "button",
                          onclick: () => launchTask(t.id) }, "Launch")
                    : el("span"),
                t.status === "open"
                    ? el("button", { class: "btn", type: "button",
                          onclick: () => markTaskDone(t.id) }, "Done")
                    : el("span"),
            ),
        ));
    }
}

async function createTask() {
    const title = document.getElementById("task-title").value.trim();
    const repo = document.getElementById("task-repo").value.trim();
    const agent = document.getElementById("task-agent").value;
    if (!title || !repo) return;
    const r = await api("POST", "/api/tasks", { title, repo_path: repo, agent: agent || null });
    if (r.ok) {
        document.getElementById("task-title").value = "";
        document.getElementById("task-repo").value = "";
        await loadTasks();
    }
}

async function launchTask(id) {
    const r = await api("POST", "/api/tasks/launch", { id });
    if (r.ok && r.port) window.open(ttydUrl(r.port), "_blank", "noopener");
    await refresh();
}

async function markTaskDone(id) {
    await api("POST", "/api/tasks/update", { id, status: "done" });
    await loadTasks();
}

function populateTaskAgentSelect() {
    const sel = document.getElementById("task-agent");
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = "";
    sel.append(el("option", { value: "" }, "No agent"));
    for (const row of state.agents) {
        sel.append(el("option", { value: row.name }, row.name));
    }
    sel.value = current;
}

function runStatusLabel(status) {
    const labels = { run_completed: "OK", run_failed: "Failed", run_rate_limited: "Rate Limited" };
    return labels[status] || status || "?";
}

function runStatusClass(status) {
    if (status === "run_completed") return "s-idle";
    if (status === "run_rate_limited") return "s-rate_limited";
    if (status === "run_failed") return "s-error";
    return "";
}

async function searchRuns() {
    const q = (document.getElementById("runs-search-q").value || "").trim();
    const agent = document.getElementById("runs-filter-agent").value;
    const status = document.getElementById("runs-filter-status").value;
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (agent) params.set("agent", agent);
    if (status) params.set("status", status);
    params.set("limit", "80");
    const r = await api("GET", "/api/agent-runs?" + params.toString());
    renderRunsPane(r.ok ? (r.runs || []) : []);
}

function renderRunsPane(runs) {
    const wrap = document.getElementById("runs-wrap");
    const count = document.getElementById("runs-count");
    const root = document.getElementById("runs-pane");
    if (!wrap || !root) return;
    wrap.hidden = false;
    if (count) count.textContent = String(runs.length);
    root.innerHTML = "";
    if (!runs.length) {
        root.append(el("div", { class: "dim" }, "(no matching runs)"));
        return;
    }
    for (const run of runs) {
        const dur = run.duration_s != null ? `${run.duration_s}s` : "";
        const tools = (run.tools_used || []).join(", ");
        root.append(el("div", { class: "run-row" },
            el("span", { class: `agent-status-badge ${runStatusClass(run.status)}` }, runStatusLabel(run.status)),
            el("div", {},
                el("div", {}, `${run.agent || "?"} · ${run.steps || 0} steps · ${dur}`),
                el("div", { class: "run-row-meta" }, run.prompt_preview || ""),
                run.message_preview ? el("div", { class: "run-row-meta" }, run.message_preview) : el("span"),
            ),
            el("div", { class: "run-row-meta" },
                run.finished_ts ? agentLastActivity(run.finished_ts) : "",
                tools ? ` · ${tools}` : "",
            ),
        ));
    }
}

function populateRunAgentFilter() {
    const sel = document.getElementById("runs-filter-agent");
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = "";
    sel.append(el("option", { value: "" }, "All agents"));
    for (const row of state.agents) {
        sel.append(el("option", { value: row.name }, row.name));
    }
    sel.value = current;
}

function _stepBlock(label, text, cls = "agent-step-block") {
    return el("div", { class: cls },
        el("div", { class: "agent-step-label" }, label),
        el("pre", { class: "agent-step-pre" }, text),
    );
}

function renderAgentStepsModal() {
    const title = document.getElementById("agent-steps-modal-title");
    const list = document.getElementById("agent-steps-list");
    const detail = document.getElementById("agent-steps-detail");
    const entries = state.stepViewer.entries || [];
    const agent = state.stepViewer.agent || "";
    title.textContent = `Agent Steps · ${agent}`;
    list.textContent = "";
    detail.textContent = "";
    if (!entries.length) {
        list.append(el("div", { class: "dim split-empty" }, `No logged runs for ${agent}.`));
        return;
    }
    const selected = Math.max(0, Math.min(state.stepViewer.selected, entries.length - 1));
    state.stepViewer.selected = selected;
    entries.forEach((entry, idx) => {
        const steps = Array.isArray(entry.transcript) ? entry.transcript.length : 0;
        const prompt = (entry.prompt || "").trim() || "(no prompt)";
        list.append(el("button", {
            class: idx === selected ? "hot-slot-item active" : "hot-slot-item",
            type: "button",
            onclick: () => {
                state.stepViewer.selected = idx;
                renderAgentStepsModal();
            },
        },
        el("span", { class: "hot-slot-kicker" }, `${entry.origin || "-"} · ${entry.status || "-"} · ${steps} steps`),
        el("span", { class: "hot-slot-name" }, prompt.length > 72 ? `${prompt.slice(0, 72)}...` : prompt),
        el("span", { class: "hot-slot-command" }, entry.message || entry.error || `ts ${entry.ts || 0}`),
        ));
    });
    const entry = entries[selected] || {};
    detail.append(
        el("div", { class: "agent-step-meta" },
            el("div", {}, `origin: ${entry.origin || "-"}`),
            el("div", {}, `status: ${entry.status || "-"}`),
            el("div", {}, `steps: ${Array.isArray(entry.transcript) ? entry.transcript.length : 0}`),
            el("div", {}, `log: ${state.stepViewer.path || "-"}`),
        ),
    );
    if (entry.prompt) detail.append(_stepBlock("Prompt", entry.prompt));
    if (entry.message) detail.append(_stepBlock("Final Message", entry.message));
    if (entry.error) detail.append(_stepBlock("Error", entry.error, "agent-step-block err"));
    if (Array.isArray(entry.transcript)) {
        for (const item of entry.transcript) {
            const step = item && item.step !== undefined ? item.step : "?";
            const wrap = el("div", { class: "agent-step-block" },
                el("div", { class: "agent-step-label" }, `Step ${step}`),
            );
            if (item.action) wrap.append(el("pre", { class: "agent-step-pre" }, JSON.stringify(item.action, null, 2)));
            if (item.parse_error) wrap.append(el("pre", { class: "agent-step-pre err" }, String(item.parse_error)));
            if (item.tool_result) wrap.append(el("pre", { class: "agent-step-pre" }, JSON.stringify(item.tool_result, null, 2)));
            detail.append(wrap);
        }
    }
}

async function openAgentSteps(agentName) {
    const name = (agentName || "").trim().toLowerCase();
    const r = await api("GET", `/api/agent-log-json?name=${encodeURIComponent(name)}&limit=20`);
    if (!r.ok) {
        setAgentStatus("error loading agent steps: " + (r.error || "unknown"), "err");
        return;
    }
    state.stepViewer.open = true;
    state.stepViewer.agent = name;
    state.stepViewer.entries = Array.isArray(r.entries) ? [...r.entries].reverse() : [];
    state.stepViewer.selected = 0;
    state.stepViewer.path = r.path || "";
    renderAgentStepsModal();
    document.getElementById("agent-steps-modal").hidden = false;
    syncModalChrome();
}

function closeAgentSteps() {
    state.stepViewer.open = false;
    document.getElementById("agent-steps-modal").hidden = true;
    syncModalChrome();
}

function renderAgentSummary() {
    const node = document.getElementById("cfg-agent-summary");
    if (!node) return;
    node.textContent = agentSummaryText();
}

function populateSelect(node, rows, firstLabel, labelFn) {
    if (!node) return;
    node.innerHTML = "";
    node.append(el("option", { value: "" }, firstLabel));
    for (const row of rows) {
        node.append(el("option", { value: row.name }, labelFn(row)));
    }
}

function renderAgentSelectors(selectedName = "", selectedPreset = "") {
    const fields = agentFieldMap();
    populateSelect(fields.existing, state.agents, "New agent", (row) =>
        `${row.name} (${row.provider || "custom"} · ${row.model || "no model"})`,
    );
    populateSelect(fields.preset, state.agentDefaults, "Custom / manual", (row) =>
        `${row.label || row.name} (${row.name})`,
    );
    fields.existing.value = selectedName || "";
    fields.preset.value = selectedPreset || "";
    renderAgentSummary();
}

function findAgentRow(name) {
    return state.agents.find((row) => row.name === name) || null;
}

function findAgentDefault(name) {
    return state.agentDefaults.find((row) => row.name === name) || null;
}

function currentAgentConstraint() {
    const fields = agentFieldMap();
    const name = (fields.name.value || fields.existing.value || fields.preset.value || "").trim().toLowerCase();
    if (name === "kimi") {
        return {
            provider: "kimi",
            wire_api: "anthropic-messages",
            message: "kimi is locked to the Kimi coding endpoint and Anthropic wire format",
        };
    }
    return null;
}

function enforceAgentConstraint() {
    const fields = agentFieldMap();
    const constraint = currentAgentConstraint();
    const locked = !!constraint;
    if (constraint) {
        fields.provider.value = constraint.provider;
        fields.wire_api.value = constraint.wire_api;
    }
    fields.provider.readOnly = locked;
    fields.wire_api.disabled = locked;
    return constraint;
}

function fillAgentForm(row, opts = {}) {
    const fields = agentFieldMap();
    const preset = opts.presetName !== undefined ? opts.presetName : (findAgentDefault(row.name) ? row.name : "");
    fields.name.value = row.name || "";
    fields.provider.value = row.provider || "";
    fields.model.value = row.model || "";
    fields.base_url.value = row.base_url || "";
    fields.wire_api.value = row.wire_api || "openai-chat";
    fields.sandbox.value = row.sandbox || "host";
    fields.api_key.value = "";
    fields.existing.value = opts.existingName !== undefined ? opts.existingName : (row.name || "");
    fields.preset.value = preset;
    enforceAgentConstraint();
}

function clearAgentForm() {
    fillAgentForm({
        name: "",
        provider: "",
        model: "",
        base_url: "",
        wire_api: "openai-chat",
    }, { existingName: "", presetName: "" });
}

function loadExistingAgentIntoForm() {
    const fields = agentFieldMap();
    const row = findAgentRow(fields.existing.value);
    if (!row) {
        clearAgentForm();
        setAgentStatus("editing a new agent", "dim");
        return;
    }
    fillAgentForm(row);
    const constraint = enforceAgentConstraint();
    setAgentStatus(constraint
        ? constraint.message
        : row.has_api_key
        ? `loaded ${row.name}; leave API key blank to keep the stored secret`
        : `loaded ${row.name}; add an API key before saving`, constraint ? "dim" : (row.has_api_key ? "dim" : "err"));
}

function applyAgentPreset() {
    const fields = agentFieldMap();
    const preset = findAgentDefault(fields.preset.value);
    if (!preset) return;
    if (!fields.name.value.trim() || fields.existing.value !== fields.name.value.trim()) {
        fields.name.value = preset.name;
    }
    fields.provider.value = preset.provider || "";
    fields.model.value = preset.model || "";
    fields.base_url.value = preset.base_url || "";
    fields.wire_api.value = preset.wire_api || "openai-chat";
    if (fields.existing.value && fields.existing.value !== fields.name.value.trim()) {
        fields.existing.value = "";
    }
    const constraint = enforceAgentConstraint();
    setAgentStatus(constraint ? constraint.message : `loaded preset ${preset.name}`, "dim");
}

async function loadAgents(selectedName = "") {
    const current = selectedName || agentFieldMap().existing.value || agentFieldMap().name.value.trim();
    const r = await api("GET", "/api/agents");
    if (!r.ok) {
        setAgentStatus("error loading agents: " + (r.error || "unknown"), "err");
        return false;
    }
    state.agents = Array.isArray(r.agents) ? r.agents : [];
    state.agentDefaults = Array.isArray(r.defaults) ? r.defaults : [];
    state.agentPaths = r.paths || { agents: "", secrets: "" };
    const selectedRow = findAgentRow(current);
    renderAgentSelectors(selectedRow ? selectedRow.name : "", findAgentDefault(current) ? current : "");
    if (selectedRow) fillAgentForm(selectedRow);
    else if (!current && state.agents.length) {
        renderAgentSelectors(state.agents[0].name, findAgentDefault(state.agents[0].name) ? state.agents[0].name : "");
        fillAgentForm(state.agents[0]);
    } else if (!current) {
        clearAgentForm();
    } else {
        enforceAgentConstraint();
    }
    renderAgentsPane();
    populateRunAgentFilter();
    populateTaskAgentSelect();
    return true;
}

async function loadAgentWorkflows(showStatus = false) {
    const r = await api("GET", "/api/agent-workflows");
    if (!r.ok) {
        if (showStatus) setAgentStatus("error loading workflows: " + (r.error || "unknown"), "err");
        return false;
    }
    state.workflowConfig = normalizeAgentWorkflowConfig(r.config);
    state.workflowPath = r.path || "";
    scheduleWorkflowLoop();
    return true;
}

async function saveAgentWorkflows(showStatus = false) {
    const r = await api("POST", "/api/agent-workflows", { config: state.workflowConfig });
    if (!r.ok) {
        if (showStatus) setAgentStatus("error saving workflows: " + (r.error || "unknown"), "err");
        return false;
    }
    state.workflowConfig = normalizeAgentWorkflowConfig(r.config);
    state.workflowPath = r.path || "";
    scheduleWorkflowLoop();
    return true;
}

async function openAgentConversation(name) {
    const r = await api("POST", "/api/agent-conversation", { name });
    if (!r.ok) {
        setAgentStatus("error opening conversation mode: " + (r.error || "unknown"), "err");
        return;
    }
    await refresh();
    window.open(ttydUrl(r.port), "_blank", "noopener");
}

async function forkAgentConversation(name) {
    const r = await api("POST", "/api/agent-conversation-fork", { name });
    if (!r.ok) {
        setAgentStatus("error forking conversation: " + (r.error || "unknown"), "err");
        return;
    }
    setAgentStatus(`forked ${name} conversation into ${r.session}`, "ok");
    await refresh();
    if (r.port) window.open(ttydUrl(r.port), "_blank", "noopener");
}

function readAgentForm() {
    const fields = agentFieldMap();
    const payload = {
        name: fields.name.value.trim(),
        provider: fields.provider.value.trim(),
        model: fields.model.value.trim(),
        base_url: fields.base_url.value.trim(),
        wire_api: fields.wire_api.value,
        sandbox: fields.sandbox.value,
    };
    const constraint = currentAgentConstraint();
    if (constraint) {
        payload.provider = constraint.provider;
        payload.wire_api = constraint.wire_api;
    }
    const apiKey = fields.api_key.value.trim();
    if (apiKey) payload.api_key = apiKey;
    return payload;
}

async function saveAgentConfig() {
    const payload = readAgentForm();
    const r = await api("POST", "/api/agents", { agent: payload });
    if (!r.ok) {
        setAgentStatus("error saving agent: " + (r.error || "unknown"), "err");
        return;
    }
    await loadAgents(r.agent && r.agent.name ? r.agent.name : payload.name);
    setAgentStatus(`saved agent ${r.agent.name}`, "ok");
}

async function removeAgentConfig() {
    const fields = agentFieldMap();
    const name = fields.name.value.trim() || fields.existing.value;
    if (!name) {
        setAgentStatus("enter or load an agent name before removing", "err");
        return;
    }
    const r = await api("POST", "/api/agents/remove", { name });
    if (!r.ok) {
        setAgentStatus("error removing agent: " + (r.error || "unknown"), "err");
        return;
    }
    await loadAgents("");
    clearAgentForm();
    setAgentStatus(r.removed ? `removed agent ${name}` : `agent ${name} was not configured`, r.removed ? "ok" : "dim");
}

function applyTopbarConfig() {
    const cfg = state.config;
    const bar = document.querySelector(".topbar");
    if (!bar) return;
    setVisible(bar, cfg.show_topbar, "flex");

    // Title + count
    const h1 = bar.querySelector("h1");
    if (h1) setVisible(h1, cfg.show_topbar_title);
    setVisible(document.getElementById("count"), cfg.show_topbar_count);

    // New session input + button
    setVisible(document.getElementById("new-name"), cfg.show_topbar_new_session);
    setVisible(document.getElementById("new-btn"), cfg.show_topbar_new_session);

    // Individual buttons
    setVisible(document.getElementById("raw-btn"), cfg.show_topbar_raw_ttyd);
    setVisible(document.getElementById("refresh-btn"), cfg.show_topbar_refresh);
    setVisible(document.getElementById("restart-btn"), cfg.show_topbar_restart);

    // Status text
    const statusNode = document.getElementById("topbar-status");
    if (statusNode) {
        const parts = [];
        parts.push(cfg.auto_refresh ? `auto-refresh ${cfg.refresh_seconds}s` : "auto-refresh off");
        parts.push(cfg.launch_on_expand ? "ttyd spawns on pane expand" : "manual ttyd launch");
        parts.push(`hot loop wait ${cfg.hot_loop_idle_seconds}s`);
        parts.push(`agent steps ${cfg.agent_max_steps}`);
        parts.push(`default ttyd height ${cfg.default_ttyd_height_vh}vh`);
        statusNode.textContent = parts.join(" · ");
        setVisible(statusNode, cfg.show_topbar_status);
    }
}

function applySummaryRowConfig(rec) {
    const cfg = state.config;
    const summary = rec.details.querySelector("summary");
    if (summary) {
        const actions = summary.querySelector(".summary-actions");
        if (actions) setVisible(actions, cfg.show_summary_row, "flex");
        const sname = summary.querySelector(".sname");
        if (sname) setVisible(sname, cfg.show_summary_name);
    }
    rec.details.classList.toggle("hide-arrow", !cfg.show_summary_arrow);
}

function applyBodyActionsConfig(rec) {
    const cfg = state.config;
    const actions = rec.details.querySelector(".pane-actions");
    if (actions) setVisible(actions, cfg.show_body_actions, "flex");
}

const TOPBAR_TOGGLE_KEYS = [
    "show_topbar_title", "show_topbar_count", "show_topbar_new_session",
    "show_topbar_raw_ttyd", "show_topbar_refresh", "show_topbar_restart",
    "show_topbar_status",
];
const SUMMARY_TOGGLE_KEYS = [
    "show_attached_badge", "show_window_badge", "show_port_badge",
    "show_idle_text", "show_idle_alert_button", "show_summary_open",
    "show_summary_log", "show_summary_scroll", "show_summary_split",
    "show_summary_hide", "show_summary_reorder",
];
const BODY_TOGGLE_KEYS = [
    "show_body_launch", "show_body_stop", "show_body_kill",
    "show_body_send_bar", "show_body_phone_keys", "show_body_hot_buttons", "show_hot_loop_toggles",
    "show_footer", "show_inline_messages",
];

function toggleAllSection(keys, btn) {
    const fields = configFieldMap();
    const allOn = keys.every((k) => fields[k] && fields[k].checked);
    const target = !allOn;
    for (const k of keys) {
        if (fields[k]) fields[k].checked = target;
    }
    btn.textContent = target ? "All Off" : "All On";
    previewDashboardConfig();
}

function updateToggleAllButtons() {
    const fields = configFieldMap();
    const topbarBtn = document.getElementById("cfg-toggle-all-topbar");
    const summaryBtn = document.getElementById("cfg-toggle-all-summary");
    const bodyBtn = document.getElementById("cfg-toggle-all-body");
    if (topbarBtn) {
        topbarBtn.textContent = TOPBAR_TOGGLE_KEYS.every((k) => fields[k] && fields[k].checked) ? "All Off" : "All On";
    }
    if (summaryBtn) {
        summaryBtn.textContent = SUMMARY_TOGGLE_KEYS.every((k) => fields[k] && fields[k].checked) ? "All Off" : "All On";
    }
    if (bodyBtn) {
        bodyBtn.textContent = BODY_TOGGLE_KEYS.every((k) => fields[k] && fields[k].checked) ? "All Off" : "All On";
    }
}

function renderConfigForm() {
    const cfg = state.config;
    const fields = configFieldMap();
    for (const [key, input] of Object.entries(fields)) {
        if (!input) continue;
        if (input.type === "checkbox") input.checked = !!cfg[key];
        else input.value = cfg[key];
    }
    updateToggleAllButtons();
}

function readConfigForm() {
    const raw = {};
    for (const [key, input] of Object.entries(configFieldMap())) {
        if (!input) continue;
        raw[key] = input.type === "checkbox" ? input.checked : input.value;
    }
    return normalizeDashboardConfig(raw);
}

function scheduleRefreshLoop() {
    if (state.refreshTimer) clearInterval(state.refreshTimer);
    state.refreshTimer = null;
    if (!state.config.auto_refresh) return;
    state.refreshTimer = setInterval(refresh, state.config.refresh_seconds * 1000);
}

function scheduleWorkflowLoop() {
    // Workflow execution is now server-side. This loop just polls
    // the server's workflow state so the UI stays current.
    setInterval(loadWorkflowState, 15000);
}

function applyDashboardConfigToPane(rec) {
    const cfg = state.config;
    const idleVisible = cfg.show_idle_text || cfg.show_idle_alert_button;
    setVisible(rec.idleWrap, idleVisible, "inline-flex");
    setVisible(rec.idle, cfg.show_idle_text, "");
    setVisible(rec.idleAlertBtn, cfg.show_idle_alert_button, "");
    setVisible(rec.summaryTabLink, cfg.show_summary_open && rec.summaryTabLink.dataset.available === "1", "");
    setVisible(rec.logLink, cfg.show_summary_log, "");
    setVisible(rec.scrollBtn, cfg.show_summary_scroll, "");
    setVisible(rec.splitBtn, cfg.show_summary_split, "");
    setVisible(rec.hideBtn, cfg.show_summary_hide, "");
    setVisible(rec.reorderPad, cfg.show_summary_reorder, "inline-flex");
    setVisible(rec.launchBtn, cfg.show_body_launch, "");
    setVisible(rec.stopBtn, cfg.show_body_stop, "");
    setVisible(rec.killBtn, cfg.show_body_kill, "");
    setVisible(rec.sendBar, cfg.show_body_send_bar, "flex");
    setVisible(rec.phoneKeys, cfg.show_body_phone_keys, "flex");
    setVisible(rec.hotManageBtn, cfg.show_body_hot_buttons, "");
    setVisible(rec.msg, cfg.show_inline_messages, "");
    setVisible(rec.footer, cfg.show_footer, "flex");
    applySummaryRowConfig(rec);
    applyBodyActionsConfig(rec);
    // Defaults flow via CSS custom properties on :root (see applyDashboardConfig),
    // so they don't fight the browser's native resize handle's inline style.height.
    for (const pair of rec.hotPairs) {
        if (!cfg.show_body_hot_buttons) {
            pair.wrap.hidden = true;
            pair.wrap.style.display = "none";
            pair.loopBtn.hidden = true;
            pair.loopBtn.style.display = "none";
            continue;
        }
        const present = !pair.cmdBtn.disabled;
        pair.wrap.hidden = !present;
        pair.wrap.style.display = present ? "inline-flex" : "none";
        const loopVisible = present && cfg.show_hot_loop_toggles;
        pair.loopBtn.hidden = !loopVisible;
        pair.loopBtn.style.display = loopVisible ? "inline-flex" : "none";
    }
}

function applyDashboardConfig() {
    state.config = normalizeDashboardConfig(state.config);
    renderConfigForm();
    applyTopbarConfig();
    scheduleRefreshLoop();
    document.documentElement.classList.toggle("day-mode", !!state.config.day_mode);
    const root = document.documentElement.style;
    root.setProperty("--ttyd-default-height", `${state.config.default_ttyd_height_vh}vh`);
    root.setProperty("--ttyd-default-min-height", `${state.config.default_ttyd_min_height_px}px`);
    for (const rec of state.nodes.values()) applyDashboardConfigToPane(rec);
}

async function loadDashboardConfig(showStatus = false) {
    const r = await api("GET", "/api/dashboard-config");
    if (!r.ok) {
        if (showStatus) setConfigStatus("error loading config: " + (r.error || "unknown"), "err");
        return false;
    }
    state.config = normalizeDashboardConfig(r.config);
    state.configPath = r.path || "";
    applyDashboardConfig();
    if (showStatus) setConfigStatus(`loaded ${state.configPath}`, "ok");
    return true;
}

async function saveDashboardConfig() {
    state.config = readConfigForm();
    applyDashboardConfig();
    const r = await api("POST", "/api/dashboard-config", { config: state.config });
    if (!r.ok) {
        setConfigStatus("error saving config: " + (r.error || "unknown"), "err");
        return;
    }
    state.config = normalizeDashboardConfig(r.config);
    state.configPath = r.path || "";
    applyDashboardConfig();
    setConfigStatus(`saved ${state.configPath}`, "ok");
}

async function reloadDashboardConfig() {
    await loadDashboardConfig(true);
    refresh();
}

function resetDashboardConfig() {
    state.config = normalizeDashboardConfig(DASHBOARD_CONFIG_DEFAULTS);
    applyDashboardConfig();
    setConfigStatus("loaded defaults locally; save to persist", "dim");
    refresh();
}

// --- Phone keys config ---

const DEFAULT_PHONE_KEYS = [
    { label: "\u2191", keys: ["Up"] },
    { label: "\u2193", keys: ["Down"] },
    { label: "\u2190", keys: ["Left"] },
    { label: "\u2192", keys: ["Right"] },
    { label: "Esc", keys: ["Escape"] },
    { label: "C-c", keys: ["C-c"] },
    { label: "C-b", keys: ["C-b"] },
    { label: "Shift", keys: [] },
    { label: "PgUp", keys: ["PageUp"] },
    { label: "PgDn", keys: ["PageDown"] },
];

function loadPhoneKeys() {
    return loadJSON(PHONE_KEYS_KEY, null) || [...DEFAULT_PHONE_KEYS];
}

function savePhoneKeys(keys) {
    saveJSON(PHONE_KEYS_KEY, keys);
}

function renderPhoneKeysPreview() {
    const root = document.getElementById("phone-keys-preview");
    if (!root) return;
    root.innerHTML = "";
    const keys = loadPhoneKeys();
    keys.forEach((def, idx) => {
        const btn = el("button", {
            class: "phone-key", type: "button", draggable: "true",
            title: `tmux: ${(def.keys || []).join(" ") || "(none)"} — click to remove`,
            onclick: () => {
                keys.splice(idx, 1);
                savePhoneKeys(keys);
                renderPhoneKeysPreview();
            },
        }, def.label);
        btn.addEventListener("dragstart", (e) => {
            e.dataTransfer.setData("text/x-phone-key-idx", String(idx));
            e.dataTransfer.effectAllowed = "move";
        });
        btn.addEventListener("dragover", (e) => {
            if (e.dataTransfer.types.includes("text/x-phone-key-idx")) {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
            }
        });
        btn.addEventListener("drop", (e) => {
            const fromIdx = parseInt(e.dataTransfer.getData("text/x-phone-key-idx"), 10);
            if (isNaN(fromIdx) || fromIdx === idx) return;
            e.preventDefault();
            const [moved] = keys.splice(fromIdx, 1);
            keys.splice(idx, 0, moved);
            savePhoneKeys(keys);
            renderPhoneKeysPreview();
        });
        root.append(btn);
    });
}

function addPhoneKey() {
    const labelInput = document.getElementById("phone-key-label");
    const tmuxInput = document.getElementById("phone-key-tmux");
    const label = (labelInput.value || "").trim();
    const tmux = (tmuxInput.value || "").trim();
    if (!label || !tmux) return;
    const keys = loadPhoneKeys();
    keys.push({ label, keys: [tmux] });
    savePhoneKeys(keys);
    labelInput.value = "";
    tmuxInput.value = "";
    renderPhoneKeysPreview();
}

function resetPhoneKeys() {
    savePhoneKeys([...DEFAULT_PHONE_KEYS]);
    renderPhoneKeysPreview();
}

// --- Config lock ---

let configUnlocked = true;

async function checkConfigLock() {
    const r = await api("GET", "/api/config-lock");
    if (r.ok && r.locked) {
        configUnlocked = false;
        const lockStatus = document.getElementById("cfg-lock-status");
        if (lockStatus) lockStatus.textContent = "locked";
    }
}

function guardConfigOpen(e) {
    const wrap = document.getElementById("config-wrap");
    if (!wrap) return;
    if (configUnlocked) return;
    if (wrap.open) return;
    e.preventDefault();
    const password = prompt("Enter config password:");
    if (!password) return;
    api("POST", "/api/config-lock/verify", { password }).then((r) => {
        if (r.ok && r.unlocked) {
            configUnlocked = true;
            wrap.open = true;
            const lockStatus = document.getElementById("cfg-lock-status");
            if (lockStatus) lockStatus.textContent = "unlocked this session";
        } else {
            alert("Wrong password.");
        }
    });
}

async function setConfigLock() {
    const pw = document.getElementById("cfg-lock-password").value.trim();
    if (!pw) return;
    const r = await api("POST", "/api/config-lock", { password: pw });
    const lockStatus = document.getElementById("cfg-lock-status");
    if (r.ok) {
        document.getElementById("cfg-lock-password").value = "";
        if (lockStatus) lockStatus.textContent = r.locked ? "lock set" : "lock cleared";
    }
}

async function clearConfigLock() {
    const r = await api("POST", "/api/config-lock", { password: "" });
    const lockStatus = document.getElementById("cfg-lock-status");
    if (r.ok && lockStatus) {
        lockStatus.textContent = "lock removed";
        configUnlocked = true;
    }
}

// --- Connected endpoints ---

let myClientId = "";

async function loadClients() {
    const r = await api("GET", "/api/clients");
    if (!r.ok) return;
    myClientId = r.you || "";
    const youLabel = document.getElementById("client-you-id");
    if (youLabel) youLabel.textContent = `you: ${myClientId}`;
    renderClientsPane(r.clients || []);
}

function renderClientsPane(clients) {
    const count = document.getElementById("clients-count");
    const root = document.getElementById("clients-pane");
    if (!root) return;
    if (count) count.textContent = String(clients.length);
    root.innerHTML = "";
    for (const c of clients) {
        const isMe = c.client_id === myClientId;
        const label = c.nickname || c.ip;
        root.append(el("div", { class: "run-row" },
            el("span", { style: `font-weight:700;font-size:0.85rem;color:${isMe ? "var(--green)" : "var(--fg)"}` },
                label + (isMe ? " (you)" : "")),
            el("div", {},
                el("div", { class: "run-row-meta" },
                    `idle ${fmtAgeSeconds(c.idle_seconds)} · connected ${fmtAgeSeconds(Math.max(0, Math.floor(Date.now() / 1000) - c.first_seen))} ago`),
                el("div", { class: "run-row-meta" }, c.client_id),
            ),
            isMe
                ? el("span")
                : el("button", {
                    class: "btn blue", type: "button",
                    onclick: () => shareConfigTo(c.client_id, label),
                  }, "Share Config"),
        ));
    }
}

async function setClientNickname() {
    const input = document.getElementById("client-nickname");
    const nick = (input.value || "").trim();
    if (!nick) return;
    await api("POST", "/api/clients/nickname", { nickname: nick });
    input.value = "";
    await loadClients();
}

async function shareConfigTo(targetId, targetLabel) {
    const cfg = collectViewConfig();
    const json = JSON.stringify(cfg);
    const b64 = btoa(unescape(encodeURIComponent(json)));
    const configUrl = `${location.origin}/?import-cfg=${b64}`;
    const r = await api("POST", "/api/clients/send-config", { target: targetId, config_url: configUrl });
    if (r.ok) {
        setConfigStatus(`config sent to ${targetLabel}`, "ok");
    } else {
        setConfigStatus(`failed to send: ${r.error || "unknown"}`, "err");
    }
}

async function checkClientInbox() {
    const r = await api("GET", "/api/clients/inbox");
    if (!r.ok || !r.messages || !r.messages.length) return;
    for (const msg of r.messages) {
        const accept = confirm(`${msg.from} shared their config with you. Apply it?`);
        if (accept) {
            const match = msg.config_url.match(/[?&]import-cfg=([A-Za-z0-9+/=]+)/);
            if (match) {
                const json = decodeURIComponent(escape(atob(match[1])));
                const cfg = JSON.parse(json);
                applyViewConfig(cfg);
                setConfigStatus(`applied config from ${msg.from}`, "ok");
            }
        }
    }
}

// --- QR config transfer ---

function collectViewConfig() {
    return {
        dashboard: state.config,
        hidden: [...state.hidden],
        order: state.order,
        layout: state.layout,
        hot: state.hot,
        idleAlerts: state.idleAlerts,
        phoneKeys: loadPhoneKeys(),
    };
}

function applyViewConfig(cfg) {
    if (cfg.dashboard) {
        state.config = normalizeDashboardConfig(cfg.dashboard);
        applyDashboardConfig();
    }
    if (cfg.hidden) {
        state.hidden = new Set(cfg.hidden);
        saveHidden(state.hidden);
    }
    if (cfg.order) {
        state.order = cfg.order;
        saveOrder(state.order);
    }
    if (cfg.layout) {
        state.layout = cfg.layout;
        persistLayoutState();
    }
    if (cfg.hot) {
        state.hot = normalizeHotButtons(cfg.hot);
        saveHot();
    }
    if (cfg.idleAlerts) {
        state.idleAlerts = cfg.idleAlerts;
        saveIdleAlerts();
    }
    if (cfg.phoneKeys) {
        savePhoneKeys(cfg.phoneKeys);
        renderPhoneKeysPreview();
    }
    renderLayout();
    refresh();
}

async function showConfigQR() {
    const cfg = collectViewConfig();
    const json = JSON.stringify(cfg);
    const b64 = btoa(unescape(encodeURIComponent(json)));
    const url = `${location.origin}/?import-cfg=${b64}`;

    const display = document.getElementById("qr-display");
    const status = document.getElementById("qr-status");
    const video = document.getElementById("qr-video");
    video.style.display = "none";
    display.innerHTML = "";
    status.textContent = "loading QR...";

    const r = await fetch(`/api/qr?data=${encodeURIComponent(url)}`);
    if (r.ok) {
        display.innerHTML = await r.text();
        status.textContent = `${json.length} bytes of config · scan this from your phone`;
    } else {
        status.textContent = "QR generation failed — config may be too large";
    }

    document.getElementById("qr-modal").hidden = false;
    document.getElementById("qr-modal-title").textContent = "Share Config via QR";
}

let qrStream = null;

async function scanConfigQR() {
    const display = document.getElementById("qr-display");
    const status = document.getElementById("qr-status");
    const video = document.getElementById("qr-video");
    display.innerHTML = "";

    if (!("BarcodeDetector" in window)) {
        status.textContent = "BarcodeDetector not supported in this browser. Use Chrome on Android.";
        document.getElementById("qr-modal").hidden = false;
        document.getElementById("qr-modal-title").textContent = "Read QR";
        return;
    }

    try {
        qrStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    } catch (e) {
        status.textContent = "Camera access denied: " + e.message;
        document.getElementById("qr-modal").hidden = false;
        document.getElementById("qr-modal-title").textContent = "Read QR";
        return;
    }

    video.srcObject = qrStream;
    video.style.display = "block";
    status.textContent = "Point camera at QR code...";
    document.getElementById("qr-modal").hidden = false;
    document.getElementById("qr-modal-title").textContent = "Read QR";

    const detector = new BarcodeDetector({ formats: ["qr_code"] });
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");

    const scan = async () => {
        if (!qrStream || video.style.display === "none") return;
        if (video.readyState < video.HAVE_ENOUGH_DATA) {
            requestAnimationFrame(scan);
            return;
        }
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        ctx.drawImage(video, 0, 0);
        try {
            const codes = await detector.detect(canvas);
            if (codes.length > 0) {
                const raw = codes[0].rawValue;
                const match = raw.match(/[?&]import-cfg=([A-Za-z0-9+/=]+)/);
                if (match) {
                    const json = decodeURIComponent(escape(atob(match[1])));
                    const cfg = JSON.parse(json);
                    applyViewConfig(cfg);
                    stopQRStream();
                    status.textContent = "Config imported successfully!";
                    video.style.display = "none";
                    return;
                }
            }
        } catch (e) { /* scan failed, retry */ }
        requestAnimationFrame(scan);
    };
    requestAnimationFrame(scan);
}

function stopQRStream() {
    if (qrStream) {
        for (const track of qrStream.getTracks()) track.stop();
        qrStream = null;
    }
}

function closeQRModal() {
    stopQRStream();
    document.getElementById("qr-modal").hidden = true;
    document.getElementById("qr-video").style.display = "none";
}

// Handle ?import-cfg= URL parameter on page load
function checkImportCfgParam() {
    const params = new URLSearchParams(location.search);
    const b64 = params.get("import-cfg");
    if (!b64) return;
    try {
        const json = decodeURIComponent(escape(atob(b64)));
        const cfg = JSON.parse(json);
        applyViewConfig(cfg);
        // Clean URL
        history.replaceState(null, "", location.pathname);
    } catch (e) {
        console.error("Failed to import config from URL:", e);
    }
}

function previewDashboardConfig() {
    state.config = readConfigForm();
    applyDashboardConfig();
    updateToggleAllButtons();
    setConfigStatus("previewing unsaved config", "dim");
}

// One short shaped note — the building block every preset below uses.
function _schedNote(ctx, { freq, type = "sine", start = 0, dur = 0.35, peak = 0.035 }) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.value = 0.0001;
    osc.connect(gain);
    gain.connect(ctx.destination);
    const t0 = ctx.currentTime + start;
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(peak, t0 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
}

const IDLE_SOUND_PRESETS = {
    beep:  (ctx) => _schedNote(ctx, { freq: 880, type: "sine", dur: 0.35 }),
    chime: (ctx) => {
        _schedNote(ctx, { freq: 1046.5, type: "sine", start: 0.00, dur: 0.45 });
        _schedNote(ctx, { freq: 1318.5, type: "sine", start: 0.08, dur: 0.45 });
    },
    knock: (ctx) => {
        _schedNote(ctx, { freq: 180, type: "sine", start: 0.00, dur: 0.08, peak: 0.08 });
        _schedNote(ctx, { freq: 180, type: "sine", start: 0.14, dur: 0.08, peak: 0.08 });
    },
    bell:  (ctx) => _schedNote(ctx, { freq: 1760, type: "triangle", dur: 0.9, peak: 0.04 }),
    blip:  (ctx) => _schedNote(ctx, { freq: 440, type: "square", dur: 0.15, peak: 0.02 }),
    ding:  (ctx) => _schedNote(ctx, { freq: 2093, type: "sine", dur: 0.6, peak: 0.03 }),
};

function playIdleTone(name) {
    // Don't create an AudioContext here — Chrome logs a warning if one is
    // constructed before a user gesture. primeAudio() (below) constructs it
    // on the first pointerdown / keydown; until then, idle tones are silent.
    const ctx = state.audioCtx;
    if (!ctx || ctx.state !== "running") return;
    const preset = IDLE_SOUND_PRESETS[name] || IDLE_SOUND_PRESETS[state.config.idle_sound] || IDLE_SOUND_PRESETS.beep;
    preset(ctx);
}

function primeAudio() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    if (!state.audioCtx) state.audioCtx = new Ctx();
    if (state.audioCtx.state === "suspended") {
        state.audioCtx.resume().catch(() => {});
    }
}

function fmtAgeSeconds(secs) {
    if (secs === null || secs === undefined) return "";
    secs = Math.max(0, Math.floor(secs));
    if (secs < 60) return secs + "s";
    if (secs < 3600) return Math.floor(secs / 60) + "m";
    if (secs < 86400) return Math.floor(secs / 3600) + "h";
    return Math.floor(secs / 86400) + "d";
}
// Backward-compat for any callers still handing us an epoch.
function fmtAge(epoch) {
    if (!epoch) return "";
    return fmtAgeSeconds(Date.now() / 1000 - epoch);
}

async function api(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
    }
    const r = await fetch(path, opts);
    const text = await r.text();
    if (!text) {
        // Empty 2xx should not look like success with an undefined shape.
        return { ok: r.ok, empty: true, status: r.status };
    }
    try { return JSON.parse(text); }
    catch { return { ok: r.ok, raw: text, status: r.status }; }
}

function ttydUrl(port) {
    // Always use the same host the dashboard is served on. That way the page
    // works whether you reach it via IP, hostname, or localhost.
    return `${window.location.protocol}//${window.location.hostname}:${port}/`;
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

function renderLayout() {
    syncLayoutState();
    const root = document.getElementById("sessions");
    root.textContent = "";
    for (const row of state.layout) {
        const rowEl = el("div", { class: "session-row" });
        for (const name of row) {
            const rec = state.nodes.get(name);
            if (rec) rowEl.append(rec.details);
        }
        if (rowEl.childNodes.length) root.append(rowEl);
    }
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

function cssId(s) {
    return s.replace(/[^a-zA-Z0-9_-]/g, "_");
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

    const summary = el("summary", { draggable: "true" },
        sname, sbadges, idleWrap,
        el("span", { class: "summary-actions" },
            summaryTabLink, logLink, scrollBtn, splitBtn, hideBtn, reorderPad),
    );

    const msg = el("span", { id: "msg-" + id, class: "inline-msg dim" });
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
    const iframeWrap = el("div", { class: "ttyd-resize-wrap" }, iframe);

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

    const details = el("details", { class: "session", "data-session": s.name },
        summary, el("div", { class: "pane-body" }, actions, iframeWrap, sendBar, phoneKeys, footer),
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

    // Drag-and-drop: reorderPad, splitBtn, and summary all initiate drags.
    // Any <details> is a valid drop target.
    const clearDropClasses = () => details.classList.remove("drag-over", "drop-left", "drop-right");
    details.addEventListener("dragover", (e) => {
        const splitDrag = e.dataTransfer.types.includes("text/x-tmux-browse-split");
        const reorderDrag = e.dataTransfer.types.includes("text/x-tmux-browse-session");
        if (!splitDrag && !reorderDrag) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        clearDropClasses();
        details.classList.add("drag-over");
        if (splitDrag) {
            const rect = details.getBoundingClientRect();
            const ratio = (e.clientX - rect.left) / Math.max(rect.width, 1);
            if (ratio <= 0.28) details.classList.add("drop-left");
            else if (ratio >= 0.72) details.classList.add("drop-right");
        }
    });
    details.addEventListener("dragleave", clearDropClasses);
    details.addEventListener("drop", (e) => {
        const draggedSplit = e.dataTransfer.getData("text/x-tmux-browse-split");
        const draggedReorder = e.dataTransfer.getData("text/x-tmux-browse-session");
        clearDropClasses();
        if (!draggedSplit && !draggedReorder) return;
        e.preventDefault();
        if (draggedSplit) {
            const rect = details.getBoundingClientRect();
            const ratio = (e.clientX - rect.left) / Math.max(rect.width, 1);
            const side = ratio <= 0.28 ? "left" : (ratio >= 0.72 ? "right" : "center");
            dropOnSession(s.name, draggedSplit, side);
            return;
        }
        dropOnSession(s.name, draggedReorder, "center");
    });

    return {
        details, sbadges, idle, idleWrap, idleAlertBtn,
        summaryTabLink, logLink, scrollBtn, splitBtn, hideBtn, reorderPad,
        launchBtn, stopBtn, killBtn: bodyKillBtn, hotManageBtn, msg,
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

function dropOnSession(targetName, draggedName, side = "center") {
    if (!draggedName || draggedName === targetName) return;
    if (side === "left" || side === "right") {
        putSessionBeside(targetName, draggedName, side);
        return;
    }
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
    renderLayout();
    if (state.splitPicker.open) renderSplitPicker();
}

document.addEventListener("DOMContentLoaded", async () => {
    document.getElementById("refresh-btn").addEventListener("click", refresh);
    document.getElementById("new-btn").addEventListener("click", newSession);
    document.getElementById("raw-btn").addEventListener("click", openRawTtyd);
    document.getElementById("restart-btn").addEventListener("click", restartDashboard);
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
    await loadClients();
    scheduleRefreshLoop();
    setInterval(loadClients, 15000);
    setInterval(checkClientInbox, 10000);
});
