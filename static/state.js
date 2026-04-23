// state.js — constants, normalizers, global state

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
    global_daily_token_budget: 0,
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
    show_wc_close: true,
    show_wc_maximize: true,
    show_wc_minimize: false,
    show_body_launch: false,
    show_body_stop: false,
    show_body_kill: false,
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

