
const HIDDEN_KEY = "tmux-browse:hidden";
const ORDER_KEY  = "tmux-browse:order";
const LAYOUT_KEY = "tmux-browse:layout";
const HOT_KEY    = "tmux-browse:hot-buttons";
const IDLE_KEY   = "tmux-browse:idle-alerts";
const IDLE_SOUND_CHOICES = ["beep", "chime", "knock", "bell", "blip", "ding"];
const DASHBOARD_CONFIG_DEFAULTS = {
    auto_refresh: false,
    refresh_seconds: 5,
    hot_loop_idle_seconds: 5,
    launch_on_expand: true,
    default_ttyd_height_vh: 70,
    default_ttyd_min_height_px: 200,
    idle_sound: "beep",
    show_topbar_status: true,
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
    const open = state.hotEditor.open || state.idleEditor.open || state.splitPicker.open;
    document.body.style.overflow = open ? "hidden" : "";
}

function configFieldMap() {
    return {
        auto_refresh: document.getElementById("cfg-auto-refresh"),
        refresh_seconds: document.getElementById("cfg-refresh-seconds"),
        hot_loop_idle_seconds: document.getElementById("cfg-hot-loop-idle-seconds"),
        launch_on_expand: document.getElementById("cfg-launch-on-expand"),
        default_ttyd_height_vh: document.getElementById("cfg-default-height"),
        default_ttyd_min_height_px: document.getElementById("cfg-min-height"),
        idle_sound: document.getElementById("cfg-idle-sound"),
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
    return true;
}

function readAgentForm() {
    const fields = agentFieldMap();
    const payload = {
        name: fields.name.value.trim(),
        provider: fields.provider.value.trim(),
        model: fields.model.value.trim(),
        base_url: fields.base_url.value.trim(),
        wire_api: fields.wire_api.value,
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

function updateTopbarStatus() {
    const cfg = state.config;
    const node = document.getElementById("topbar-status");
    if (!node) return;
    const parts = [];
    parts.push(cfg.auto_refresh ? `auto-refresh ${cfg.refresh_seconds}s` : "auto-refresh off");
    parts.push(cfg.launch_on_expand ? "ttyd spawns on pane expand" : "manual ttyd launch");
    parts.push(`hot loop wait ${cfg.hot_loop_idle_seconds}s`);
    parts.push(`default ttyd height ${cfg.default_ttyd_height_vh}vh`);
    node.textContent = parts.join(" · ");
    setVisible(node, cfg.show_topbar_status);
}

function renderConfigForm() {
    const cfg = state.config;
    const fields = configFieldMap();
    for (const [key, input] of Object.entries(fields)) {
        if (!input) continue;
        if (input.type === "checkbox") input.checked = !!cfg[key];
        else input.value = cfg[key];
    }
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
    setVisible(rec.hotManageBtn, cfg.show_body_hot_buttons, "");
    setVisible(rec.msg, cfg.show_inline_messages, "");
    setVisible(rec.footer, cfg.show_footer, "flex");
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
    updateTopbarStatus();
    scheduleRefreshLoop();
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

function previewDashboardConfig() {
    state.config = readConfigForm();
    applyDashboardConfig();
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
    if (state.hidden.has(sessionName)) {
        state.hidden.delete(sessionName);
        saveHidden(state.hidden);
    }
    removeFromLayout(sessionName);
    const targetPos = findLayoutPosition(targetName);
    if (!targetPos) return;
    const row = state.layout[targetPos.row];
    const insertAt = side === "left" ? targetPos.col : targetPos.col + 1;
    row.splice(insertAt, 0, sessionName);
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

    const summary = el("summary", {},
        sname, sbadges, idleWrap,
        el("span", { class: "summary-actions" },
            summaryTabLink, logLink, scrollBtn, splitBtn, hideBtn, reorderPad),
    );

    const msg = el("span", { id: "msg-" + id, class: "inline-msg dim" });
    const bodyKillBtn = el("button", {
        class: "btn red", onclick: () => killSession(s.name),
    }, "Kill");
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
        launchBtn, stopBtn, bodyKillBtn, msg, hotManageBtn, ...hotPairs.map((pair) => pair.wrap),
    );

    const iframe = el("iframe", {
        id: "iframe-" + id, class: "pane-iframe",
        allow: "clipboard-read; clipboard-write",
    });
    const iframeWrap = el("div", { class: "ttyd-resize-wrap" }, iframe);

    const fPort = el("span"), fPid = el("span"), fCreated = el("span");
    const footer = el("div", { class: "pane-footer" }, fPort, fPid, fCreated);

    const details = el("details", { class: "session", "data-session": s.name },
        summary, el("div", { class: "pane-body" }, actions, iframeWrap, footer),
    );

    details.addEventListener("toggle", () => {
        if (details.open && state.config.launch_on_expand && !state.openPanes.has(s.name)) {
            launch(s.name);
        }
    });

    // Drag-and-drop: only the reorderPad initiates drags. Any <details> is a
    // valid drop target — dropping on it inserts the dragged pane before it.
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
        iframe, iframeWrap, fPort, fPid, fCreated, footer,
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
    document.getElementById("idle-close-btn").addEventListener("click", closeIdleEditor);
    document.getElementById("idle-save-btn").addEventListener("click", saveIdleEditor);
    document.getElementById("idle-clear-btn").addEventListener("click", clearIdleEditor);
    document.getElementById("split-close-btn").addEventListener("click", closeSplitPicker);
    document.getElementById("split-search").addEventListener("input", (e) => {
        state.splitPicker.filter = e.target.value || "";
        renderSplitPicker();
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
        if (e.key === "Escape" && state.hotEditor.open) closeHotButtons();
        if (e.key === "Escape" && state.idleEditor.open) closeIdleEditor();
        if (e.key === "Escape" && state.splitPicker.open) closeSplitPicker();
    });
    renderConfigForm();
    updateTopbarStatus();
    renderAgentSelectors();
    await loadDashboardConfig();
    await loadAgents();
    await refresh();
    scheduleRefreshLoop();
});
