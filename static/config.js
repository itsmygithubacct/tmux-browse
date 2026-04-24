// config.js — dashboard configuration form and application

function configFieldMap() {
    return {
        auto_refresh: document.getElementById("cfg-auto-refresh"),
        refresh_seconds: document.getElementById("cfg-refresh-seconds"),
        hot_loop_idle_seconds: document.getElementById("cfg-hot-loop-idle-seconds"),
        agent_max_steps: document.getElementById("cfg-agent-max-steps"),
        global_daily_token_budget: document.getElementById("cfg-global-daily-budget"),
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
        show_topbar_os_restart: document.getElementById("cfg-show-topbar-os-restart"),
        show_launch_claude: document.getElementById("cfg-show-launch-claude"),
        show_launch_claude_yolo: document.getElementById("cfg-show-launch-claude-yolo"),
        show_launch_codex: document.getElementById("cfg-show-launch-codex"),
        show_launch_codex_yolo: document.getElementById("cfg-show-launch-codex-yolo"),
        show_launch_kimi: document.getElementById("cfg-show-launch-kimi"),
        show_launch_kimi_yolo: document.getElementById("cfg-show-launch-kimi-yolo"),
        show_launch_monitor: document.getElementById("cfg-show-launch-monitor"),
        show_launch_top: document.getElementById("cfg-show-launch-top"),
        launch_ask_name: document.getElementById("cfg-launch-ask-name"),
        launch_open_tab: document.getElementById("cfg-launch-open-tab"),
        launch_cwd: document.getElementById("cfg-launch-cwd"),
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
        show_summary_move: document.getElementById("cfg-show-summary-move"),
        show_wc_move_icon: document.getElementById("cfg-show-wc-move-icon"),
        show_wc_close: document.getElementById("cfg-show-wc-close"),
        show_wc_maximize: document.getElementById("cfg-show-wc-maximize"),
        show_wc_minimize: document.getElementById("cfg-show-wc-minimize"),
        show_wc_hide_icon: document.getElementById("cfg-show-wc-hide-icon"),
        show_wc_log_icon: document.getElementById("cfg-show-wc-log-icon"),
        show_wc_idle_icon: document.getElementById("cfg-show-wc-idle-icon"),
        show_wc_scroll_icon: document.getElementById("cfg-show-wc-scroll-icon"),
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
    setVisible(document.getElementById("os-restart-btn"), cfg.show_topbar_os_restart);

    // Launcher buttons
    setVisible(document.getElementById("launch-claude-btn"), cfg.show_launch_claude);
    setVisible(document.getElementById("launch-claude-yolo-btn"), cfg.show_launch_claude_yolo);
    setVisible(document.getElementById("launch-codex-btn"), cfg.show_launch_codex);
    setVisible(document.getElementById("launch-codex-yolo-btn"), cfg.show_launch_codex_yolo);
    setVisible(document.getElementById("launch-kimi-btn"), cfg.show_launch_kimi);
    setVisible(document.getElementById("launch-kimi-yolo-btn"), cfg.show_launch_kimi_yolo);
    setVisible(document.getElementById("launch-monitor-btn"), cfg.show_launch_monitor);
    setVisible(document.getElementById("launch-top-btn"), cfg.show_launch_top);

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
    "show_topbar_os_restart",
    "show_launch_claude", "show_launch_claude_yolo",
    "show_launch_codex", "show_launch_codex_yolo",
    "show_launch_kimi", "show_launch_kimi_yolo",
    "show_launch_monitor", "show_launch_top",
    "show_topbar_status",
];
const SUMMARY_TOGGLE_KEYS = [
    "show_attached_badge", "show_window_badge", "show_port_badge",
    "show_idle_text", "show_idle_alert_button", "show_summary_open",
    "show_summary_log", "show_summary_scroll", "show_summary_split",
    "show_summary_hide", "show_summary_reorder", "show_summary_move",
    "show_wc_close", "show_wc_maximize", "show_wc_minimize", "show_wc_hide_icon", "show_wc_log_icon", "show_wc_idle_icon", "show_wc_scroll_icon", "show_wc_move_icon",
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


// --- Pane Groups editor ---
//
// Visible and Hidden are implicit pseudo-groups handled by the main
// renderer; the editor manages user-defined groups only. Each row shows
// the group name and its member count with Rename/Remove controls.
// Removing a group migrates its members back to Visible.

function renderPaneGroupsEditor() {
    const list = document.getElementById("pane-groups-list");
    if (!list) return;
    list.textContent = "";
    const makeRow = (label, count, buttons) => {
        const row = el("div", {
            style: "display:flex;align-items:center;gap:0.4rem;font-size:0.82rem;padding:0.2rem 0;border-bottom:1px dotted var(--border)",
        },
            el("span", { style: "flex:1" }, label),
            el("span", { class: "dim", style: "font-size:0.75rem" }, `(${count})`),
        );
        for (const b of buttons) row.append(b);
        return row;
    };
    list.append(makeRow("Visible", visibleSessionNames().length, []));
    for (const groupName of state.groups.order) {
        const def = state.groups.defs[groupName];
        if (!def) continue;
        const count = sessionsInGroup(groupName).length;
        const rename = el("button", {
            class: "btn", type: "button",
            onclick: () => renamePaneGroup(groupName),
        }, "Rename");
        const remove = el("button", {
            class: "btn red", type: "button",
            onclick: () => removePaneGroup(groupName),
        }, "Remove");
        list.append(makeRow(def.label || groupName, count, [rename, remove]));
    }
    list.append(makeRow("Hidden", hiddenSessionNames().length, []));
}

function addPaneGroup() {
    const input = document.getElementById("pane-group-new-name");
    const name = (input && input.value || "").trim();
    if (!name) return;
    if (name === "Visible" || name === "Hidden") {
        alert(`"${name}" is reserved.`);
        return;
    }
    if (state.groups.defs[name]) {
        alert("Group already exists.");
        return;
    }
    state.groups.defs[name] = { label: name, open: true };
    state.groups.order.push(name);
    saveGroups();
    if (input) input.value = "";
    renderPaneGroupsEditor();
    renderLayout();
}

function renamePaneGroup(oldName) {
    const newName = prompt(`Rename "${oldName}" to:`, oldName);
    if (!newName || newName === oldName) return;
    if (newName === "Visible" || newName === "Hidden") {
        alert(`"${newName}" is reserved.`);
        return;
    }
    if (state.groups.defs[newName]) {
        alert("A group with that name already exists.");
        return;
    }
    const def = state.groups.defs[oldName];
    delete state.groups.defs[oldName];
    state.groups.defs[newName] = { ...def, label: newName };
    state.groups.order = state.groups.order.map((g) => g === oldName ? newName : g);
    for (const [session, group] of Object.entries(state.groups.membership)) {
        if (group === oldName) state.groups.membership[session] = newName;
    }
    saveGroups();
    renderPaneGroupsEditor();
    renderLayout();
}

function removePaneGroup(name) {
    if (!confirm(`Remove group "${name}"? Its panes return to Visible.`)) return;
    delete state.groups.defs[name];
    state.groups.order = state.groups.order.filter((g) => g !== name);
    for (const [session, group] of Object.entries(state.groups.membership)) {
        if (group === name) delete state.groups.membership[session];
    }
    saveGroups();
    renderPaneGroupsEditor();
    renderLayout();
}

function scheduleRefreshLoop() {
    if (state.refreshTimer) clearInterval(state.refreshTimer);
    state.refreshTimer = null;
    if (!state.config.auto_refresh) return;
    state.refreshTimer = setInterval(refresh, state.config.refresh_seconds * 1000);
}

// Minute-by-minute poll that keeps idle-alert detection and each visible
// pane's "idle Xs" label current even when auto-refresh is off. Hidden
// sessions are skipped — we don't fire alerts for them and don't update
// their labels. Fetches /api/sessions and touches only the DOM text,
// never rebuilding pane structure.
async function pollIdleOnly() {
    // If auto-refresh is running, it already refreshes idle state — skip.
    if (state.config.auto_refresh) return;
    try {
        const r = await api("GET", "/api/sessions");
        const sessions = (r && r.sessions) || [];
        state.sessions = sessions;
        const visible = sessions.filter((s) => !state.hidden.has(s.name));
        checkIdleAlerts(visible);
        for (const s of visible) {
            const rec = state.nodes.get(s.name);
            if (!rec) continue;
            rec.idle.textContent = `idle ${s.idle_seconds !== undefined
                ? fmtAgeSeconds(s.idle_seconds)
                : fmtAge(s.activity)}`;
        }
    } catch (_) {
        // silent — next tick will retry
    }
}

function scheduleWorkflowLoop() {
    // Workflow execution is now server-side. This loop just polls
    // the server's workflow state so the UI stays current.
    setInterval(loadWorkflowState, 15000);
}


function applyDashboardConfigToPane(rec) {
    const cfg = state.config;
    const idleVisible = cfg.show_idle_text || cfg.show_idle_alert_button || cfg.show_wc_idle_icon;
    setVisible(rec.idleWrap, idleVisible, "inline-flex");
    setVisible(rec.idle, cfg.show_idle_text, "");
    setVisible(rec.idleAlertBtn, cfg.show_idle_alert_button, "");
    setVisible(rec.idleIconBtn, cfg.show_wc_idle_icon, "inline-flex");
    setVisible(rec.summaryTabLink, cfg.show_summary_open && rec.summaryTabLink.dataset.available === "1", "");
    setVisible(rec.logLink, cfg.show_summary_log, "");
    setVisible(rec.scrollBtn, cfg.show_summary_scroll, "");
    setVisible(rec.splitBtn, cfg.show_summary_split, "");
    setVisible(rec.hideBtn, cfg.show_summary_hide, "");
    setVisible(rec.moveBtn, cfg.show_summary_move, "");
    setVisible(rec.moveIconBtn, cfg.show_wc_move_icon, "inline-flex");
    setVisible(rec.reorderPad, cfg.show_summary_reorder, "inline-flex");
    setVisible(rec.launchBtn, cfg.show_body_launch, "");
    setVisible(rec.stopBtn, cfg.show_body_stop, "");
    setVisible(rec.killBtn, cfg.show_body_kill, "");
    setVisible(rec.wcClose, cfg.show_wc_close, "inline-flex");
    setVisible(rec.wcMaximize, cfg.show_wc_maximize, "inline-flex");
    setVisible(rec.wcMinimize, cfg.show_wc_minimize, "inline-flex");
    setVisible(rec.hideIconBtn, cfg.show_wc_hide_icon, "inline-flex");
    setVisible(rec.logIconBtn, cfg.show_wc_log_icon, "inline-flex");
    setVisible(rec.scrollIconBtn, cfg.show_wc_scroll_icon, "inline-flex");
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

// Wipe everything tmux-browse has written to this browser's localStorage
// and sessionStorage, then reload so state rebuilds from empty.
// Only keys under the "tmux-browse:" namespace are removed, so any other
// site sharing this origin is untouched. The dashboard-config.json on the
// server is not affected — that lives outside the browser.
function clearLocalCache() {
    const msg = "This will clear all tmux-browse settings stored in this browser "
        + "(hidden sessions, pane order, layout, hot buttons, idle alerts, phone keys) "
        + "and reload the page. Server-side config is untouched. Continue?";
    if (!confirm(msg)) return;
    try {
        const doomed = [];
        for (let i = 0; i < localStorage.length; i++) {
            const k = localStorage.key(i);
            if (k && k.startsWith("tmux-browse:")) doomed.push(k);
        }
        for (const k of doomed) localStorage.removeItem(k);
        sessionStorage.clear();
    } catch (_) {
        // private-mode / quota / disabled storage — nothing to clear
    }
    location.reload();
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
    promptForUnlock().then((token) => {
        if (!token) return;
        configUnlocked = true;
        wrap.open = true;
        const lockStatus = document.getElementById("cfg-lock-status");
        if (lockStatus) lockStatus.textContent = "unlocked this session";
    });
}

// Shared prompt-and-verify flow used by both guardConfigOpen and by
// util.js's api() when it gets a 403 with "config locked". Returns the
// issued token on success, "" on cancel or wrong password.
async function promptForUnlock() {
    const password = prompt("Enter config password:");
    if (!password) return "";
    // Bypass the retry loop in api() for this call — send a plain fetch
    // so a bad password doesn't spin the retry.
    const r = await fetch("/api/config-lock/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
    });
    const data = await r.json().catch(() => ({}));
    if (r.ok && data.unlocked && data.unlock_token) {
        setStoredUnlockToken(data.unlock_token);
        return data.unlock_token;
    }
    alert("Wrong password.");
    return "";
}

async function setConfigLock() {
    const pw = document.getElementById("cfg-lock-password").value.trim();
    if (!pw) return;
    const r = await api("POST", "/api/config-lock", { password: pw });
    const lockStatus = document.getElementById("cfg-lock-status");
    if (r.ok) {
        document.getElementById("cfg-lock-password").value = "";
        if (lockStatus) lockStatus.textContent = r.locked ? "lock set" : "lock cleared";
        // Immediately verify so this session gets an unlock token — otherwise
        // the very next write would 403 and re-prompt the user who *just*
        // set the password.
        if (r.locked) {
            const verify = await fetch("/api/config-lock/verify", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ password: pw }),
            }).then(v => v.json()).catch(() => null);
            if (verify && verify.unlock_token) {
                setStoredUnlockToken(verify.unlock_token);
            }
        }
    }
}

async function clearConfigLock() {
    const r = await api("POST", "/api/config-lock", { password: "" });
    const lockStatus = document.getElementById("cfg-lock-status");
    if (r.ok && lockStatus) {
        lockStatus.textContent = "lock removed";
        configUnlocked = true;
        setStoredUnlockToken("");
    }
}


function previewDashboardConfig() {
    state.config = readConfigForm();
    applyDashboardConfig();
    updateToggleAllButtons();
    setConfigStatus("previewing unsaved config", "dim");
}

// One short shaped note — the building block every preset below uses.
