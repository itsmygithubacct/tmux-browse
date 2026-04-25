// state.js — constants, normalizers, global state

const HIDDEN_KEY = "tmux-browse:hidden";
const ORDER_KEY  = "tmux-browse:order";
const LAYOUT_KEY = "tmux-browse:layout";
const HOT_KEY    = "tmux-browse:hot-buttons";
const IDLE_KEY   = "tmux-browse:idle-alerts";
const PHONE_KEYS_KEY = "tmux-browse:phone-keys";
const GROUPS_KEY = "tmux-browse:groups";
const AGENT_CONVERSATION_PREFIX = "agent-repl-";
const IDLE_SOUND_CHOICES = ["beep", "chime", "knock", "bell", "blip", "ding"];
const DASHBOARD_CONFIG_DEFAULTS = {
    auto_refresh: false,
    refresh_seconds: 5,
    hot_loop_idle_seconds: 5,
    agent_max_steps: 20,
    global_daily_token_budget: 0,
    launch_on_expand: true,
    default_ttyd_height_vh: 70,
    default_ttyd_min_height_px: 200,
    ttyd_cell_width_px: 7.7,
    ttyd_cell_height_px: 17,
    day_mode: false,
    idle_sound: "bell",
    show_topbar: true,
    show_topbar_title: true,
    show_topbar_count: true,
    show_topbar_new_session: true,
    show_topbar_raw_ttyd: false,
    show_topbar_refresh: false,
    show_topbar_restart: false,
    show_topbar_os_restart: true,
    show_launch_claude: false,
    show_launch_claude_yolo: false,
    show_launch_codex: false,
    show_launch_codex_yolo: false,
    show_launch_kimi: false,
    show_launch_kimi_yolo: false,
    show_launch_monitor: false,
    show_launch_top: false,
    launch_cwd: "",
    launch_ask_name: true,
    launch_open_tab: false,
    show_topbar_status: false,
    show_summary_row: true,
    show_summary_name: true,
    show_summary_arrow: true,
    furl_side_by_side: true,
    resize_row_together: true,
    show_body_actions: false,
    show_footer: true,
    show_inline_messages: true,
    show_attached_badge: false,
    show_window_badge: false,
    show_port_badge: false,
    show_idle_text: true,
    show_idle_alert_button: false,
    show_wc_idle_icon: true,
    show_wc_scroll_icon: true,
    show_summary_open: false,
    show_summary_log: false,
    show_wc_log_icon: true,
    show_summary_scroll: false,
    show_summary_split: false,
    show_summary_hide: false,
    show_wc_hide_icon: true,
    show_summary_reorder: false,
    show_summary_move: false,
    show_wc_move_icon: true,
    show_agents_pane: false,
    show_wc_close: true,
    show_wc_maximize: true,
    show_wc_minimize: false,
    show_body_launch: true,
    show_body_stop: true,
    show_body_kill: true,
    show_body_send_bar: false,
    show_body_phone_keys: false,
    show_body_hot_buttons: true,
    show_hot_loop_toggles: true,
};


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

// User-defined pane groups. "Visible" and "Hidden" are implicit pseudo-
// groups handled by existing code paths (state.hidden, visibleNames()).
// User groups live in `defs` + `membership`; panes without an explicit
// membership render in Visible as before.
function normalizeGroups(raw) {
    const out = { order: [], defs: {}, membership: {} };
    const src = (raw && typeof raw === "object") ? raw : {};
    if (src.defs && typeof src.defs === "object") {
        for (const [name, spec] of Object.entries(src.defs)) {
            if (!name || typeof name !== "string") continue;
            if (name === "Visible" || name === "Hidden") continue;  // reserved
            const def = spec && typeof spec === "object" ? spec : {};
            out.defs[name] = {
                label: typeof def.label === "string" ? def.label : name,
                open: def.open !== false,
            };
        }
    }
    if (Array.isArray(src.order)) {
        for (const name of src.order) {
            if (typeof name === "string" && out.defs[name] && !out.order.includes(name)) {
                out.order.push(name);
            }
        }
    }
    // Any defs missing from order get appended in iteration order.
    for (const name of Object.keys(out.defs)) {
        if (!out.order.includes(name)) out.order.push(name);
    }
    if (src.membership && typeof src.membership === "object") {
        for (const [session, group] of Object.entries(src.membership)) {
            if (typeof session !== "string" || typeof group !== "string") continue;
            if (out.defs[group]) out.membership[session] = group;
            // A membership pointing at an unknown group is dropped on load;
            // that sanitizes stale data without losing the pane (defaults to Visible).
        }
    }
    return out;
}

function normalizeIdleAlert(value) {
    const raw = value && typeof value === "object" ? value : {};
    const thresholdSec = Number(raw.thresholdSec);
    return {
        enabled: !!raw.enabled,
        thresholdSec: Number.isFinite(thresholdSec) && thresholdSec >= 60 ? Math.floor(thresholdSec) : 300,
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
        global_daily_token_budget: [0, 100000000],
        default_ttyd_height_vh: [20, 95],
        default_ttyd_min_height_px: [120, 900],
    };
    for (const [key, [lo, hi]] of Object.entries(ints)) {
        const n = Number(raw[key]);
        cfg[key] = Number.isFinite(n) ? Math.max(lo, Math.min(hi, Math.floor(n))) : DASHBOARD_CONFIG_DEFAULTS[key];
    }
    cfg.idle_sound = IDLE_SOUND_CHOICES.includes(raw.idle_sound)
        ? raw.idle_sound : DASHBOARD_CONFIG_DEFAULTS.idle_sound;
    cfg.launch_cwd = typeof raw.launch_cwd === "string" ? raw.launch_cwd.trim() : "";
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
    groups: normalizeGroups(loadJSON(GROUPS_KEY, {})),
    agentHooksForShare: null,
    conductorRules: [],
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
    dockerSupported: false,
};

function saveHidden(set) { saveJSON(HIDDEN_KEY, [...set]); }
function saveOrder(list) { saveJSON(ORDER_KEY, list); }
function saveLayout(rows) { saveJSON(LAYOUT_KEY, rows); }
function saveHot() { saveJSON(HOT_KEY, state.hot); }
function saveIdleAlerts() { saveJSON(IDLE_KEY, state.idleAlerts); }
function saveGroups() { saveJSON(GROUPS_KEY, state.groups); }

