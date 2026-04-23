// config.js — dashboard configuration form and application

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


function setConfigStatus(text, tone = "dim") {
    const node = document.getElementById("cfg-status");
    if (!node) return;
    node.textContent = text;
    node.className = tone;
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
    // Show/hide phone keys config pane based on the enable toggle
    const phoneKeysWrap = document.getElementById("phone-keys-wrap");
    if (phoneKeysWrap) phoneKeysWrap.hidden = !state.config.show_body_phone_keys;
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


function previewDashboardConfig() {
    state.config = readConfigForm();
    applyDashboardConfig();
    updateToggleAllButtons();
    setConfigStatus("previewing unsaved config", "dim");
}

// One short shaped note — the building block every preset below uses.
