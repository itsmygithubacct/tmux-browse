"""Inline CSS and JS used by the dashboard (stdlib-only, no build step)."""

CSS = """
:root {
    --bg: #0d1117;
    --fg: #e6edf3;
    --dim: #8b949e;
    --border: #30363d;
    --accent: #58a6ff;
    --blue: #58a6ff;
    --green: #3fb950;
    --yellow: #d29922;
    --red: #f85149;
    --orange: #f0883e;
    --card: #161b22;
    --card-2: #11161d;
}
* { box-sizing: border-box; }
body {
    margin: 0;
    padding: 1rem 1.25rem 4rem;
    font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
    background: var(--bg);
    color: var(--fg);
    font-size: 14px;
    line-height: 1.4;
}
h1 {
    font-size: 1.2rem;
    margin: 0;
    color: var(--accent);
    white-space: nowrap;
}
.topbar {
    display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;
    margin-bottom: 1rem;
}
.topbar input[type=text] {
    background: var(--card); border: 1px solid var(--border); color: var(--fg);
    padding: 0.35rem 0.5rem; border-radius: 4px; font-family: inherit;
}
.btn {
    background: transparent; border: 1px solid var(--border); color: var(--fg);
    padding: 0.3rem 0.7rem; border-radius: 4px; cursor: pointer;
    font-family: inherit; font-size: 0.85rem; transition: 0.15s ease;
}
.btn:hover { border-color: var(--accent); color: var(--accent); background: rgba(88, 166, 255, 0.12); }
.btn.green { color: var(--green); border-color: var(--green); }
.btn.blue  { color: var(--blue);  border-color: var(--blue); }
.btn.yellow{ color: var(--yellow);border-color: var(--yellow); }
.btn.red   { color: var(--red);   border-color: var(--red); }
.btn.orange{ color: var(--orange);border-color: var(--orange); }
.btn.green:hover { color: var(--green); border-color: var(--green); background: rgba(63, 185, 80, 0.12); }
.btn.blue:hover  { color: var(--blue);  border-color: var(--blue);  background: rgba(88, 166, 255, 0.12); }
.btn.yellow:hover{ color: var(--yellow);border-color: var(--yellow);background: rgba(210, 153, 34, 0.14); }
.btn.red:hover   { color: var(--red);   border-color: var(--red);   background: rgba(248, 81, 73, 0.12); }
.btn.orange:hover{ color: var(--orange);border-color: var(--orange);background: rgba(240, 136, 62, 0.12); }
.btn[disabled] {
    opacity: 0.55;
    cursor: default;
    pointer-events: none;
}
.dim { color: var(--dim); }
.ok  { color: var(--green); }
.err { color: var(--red); }

details.session {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 6px;
    margin: 0.5rem 0;
    overflow: hidden;
}
details.session > summary {
    cursor: pointer;
    padding: 0.5rem 0.75rem;
    list-style: none;
    display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;
}
details.session > summary::-webkit-details-marker { display: none; }
details.session > summary::before {
    content: "▸"; color: var(--dim); width: 1ch; display: inline-block;
    transition: transform 0.15s;
}
details.session[open] > summary::before { content: "▾"; }
.sname   { font-weight: 600; color: var(--accent); }
.sbadges { display: flex; gap: 0.4rem; margin-left: 0.4rem; }
.badge   {
    font-size: 0.72rem; padding: 0.05rem 0.4rem; border-radius: 10px;
    border: 1px solid var(--border); color: var(--dim);
}
.badge.attached { border-color: var(--green); color: var(--green); }
.badge.running  { border-color: var(--orange); color: var(--orange); }

.summary-actions {
    margin-left: auto; display: flex; align-items: center; gap: 0.4rem;
}
.summary-idle-wrap {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
}
.summary-idle-alert {
    padding: 0.15rem 0.5rem;
    font-size: 0.75rem;
}

.pane-body {
    padding: 0.6rem 0.75rem 0.75rem;
    border-top: 1px solid var(--border);
    background: #0d1117;
}
.pane-actions {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    align-items: center;
    margin-bottom: 0.6rem;
}
.hot-chip {
    flex: 0 0 auto;
    width: auto;
    text-align: left;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.hot-pair {
    display: inline-flex;
    align-items: stretch;
    gap: 0.25rem;
}
.hot-loop-btn {
    width: 2rem;
    min-width: 2rem;
    padding: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
}
.hot-loop-btn.is-active {
    background: rgba(240, 136, 62, 0.22);
    box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.45);
    transform: translateY(1px);
}
/* Wrap the iframe in a resizable div — iframes themselves swallow pointer
   events while dragging, so the user-drag handle has to live on a parent. */
.ttyd-resize-wrap {
    width: 100%;
    height: 70vh;
    min-height: 200px;
    max-height: 95vh;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: #000;
    resize: vertical;
    overflow: hidden;
    position: relative;
}
.pane-iframe {
    width: 100%; height: 100%;
    border: 0;
    background: #000;
}
.summary-link {
    color: var(--accent); text-decoration: none; font-size: 0.85rem;
    padding: 0 0.35rem; border-radius: 3px;
}
.summary-link:hover { background: rgba(88, 166, 255, 0.12); }
.summary-link.disabled { color: var(--dim); pointer-events: none; }
.pane-footer {
    margin-top: 0.4rem; font-size: 0.75rem; color: var(--dim);
    display: flex; gap: 0.8rem; flex-wrap: wrap;
}
.empty-state { color: var(--dim); text-align: center; padding: 2rem; }
.status-line { font-size: 0.78rem; color: var(--dim); margin-top: 0.3rem; }
.inline-msg { font-size: 0.8rem; margin-left: 0.5rem; }

.reorder-pad {
    display: inline-flex;
    flex-direction: column;
    align-items: stretch;
    gap: 1px;
    line-height: 1;
    cursor: grab;
    user-select: none;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1px 2px;
}
.reorder-pad:active { cursor: grabbing; }
.reorder-pad button {
    background: transparent;
    border: 0;
    color: var(--dim);
    cursor: pointer;
    font-family: inherit;
    font-size: 0.7rem;
    padding: 0;
    line-height: 0.9;
}
.reorder-pad button:hover { color: var(--accent); }
details.session.drag-over {
    outline: 2px dashed var(--accent);
    outline-offset: -2px;
}

.hidden-list {
    margin-top: 1.5rem;
    border-top: 1px dashed var(--border);
    padding-top: 0.75rem;
}
.hidden-list > summary {
    cursor: pointer;
    color: var(--dim);
    font-size: 0.85rem;
    padding: 0.3rem 0.2rem;
    list-style: none;
}
.hidden-list > summary::-webkit-details-marker { display: none; }
.hidden-list > summary::before {
    content: "▸"; margin-right: 0.4rem;
}
.hidden-list[open] > summary::before { content: "▾"; }

.modal-backdrop {
    position: fixed;
    inset: 0;
    z-index: 20;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 2rem 1.25rem;
    background: rgba(4, 8, 13, 0.82);
    backdrop-filter: blur(4px);
}
.modal-backdrop[hidden] {
    display: none !important;
}
.modal-card {
    width: min(1100px, calc(100vw - 2.5rem));
    border: 1px solid var(--border);
    border-radius: 12px;
    background: linear-gradient(180deg, rgba(22, 27, 34, 0.98), rgba(13, 17, 23, 0.98));
    box-shadow: 0 22px 70px rgba(0, 0, 0, 0.45);
}
.modal-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 1rem 1.1rem;
    border-bottom: 1px solid var(--border);
}
.modal-head h2 {
    margin: 0.15rem 0 0;
    font-size: 1.1rem;
    color: var(--fg);
}
.modal-eyebrow {
    font-size: 0.74rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--accent);
}
.hot-editor-grid {
    display: grid;
    grid-template-columns: minmax(240px, 320px) minmax(0, 1fr);
    gap: 1rem;
    padding: 1rem 1.1rem 1.1rem;
}
.hot-slot-list {
    display: grid;
    gap: 0.55rem;
}
.hot-slot-add {
    justify-content: center;
    text-align: center;
    border-style: dashed;
    color: var(--accent);
}
.hot-slot-item {
    width: 100%;
    text-align: left;
    padding: 0.8rem 0.9rem;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--card-2);
    color: var(--fg);
    cursor: pointer;
}
.hot-slot-item.active {
    border-color: var(--accent);
    background: rgba(88, 166, 255, 0.12);
}
.hot-slot-kicker {
    display: block;
    margin-bottom: 0.3rem;
    font-size: 0.74rem;
    color: var(--dim);
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.hot-slot-name {
    display: block;
    font-weight: 600;
    margin-bottom: 0.25rem;
}
.hot-slot-command {
    display: block;
    color: var(--dim);
    font-size: 0.82rem;
    line-height: 1.35;
    word-break: break-word;
}
.hot-editor-form {
    display: grid;
    gap: 0.9rem;
}
.field {
    display: grid;
    gap: 0.4rem;
}
.check-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    color: var(--fg);
}
.check-row input[type="checkbox"] {
    width: 1rem;
    height: 1rem;
    accent-color: var(--accent);
}
.field span {
    color: var(--dim);
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.field input,
.field textarea {
    width: 100%;
    background: var(--card-2);
    border: 1px solid var(--border);
    color: var(--fg);
    border-radius: 8px;
    padding: 0.75rem 0.85rem;
    font: inherit;
}
.field textarea {
    min-height: 10rem;
    resize: vertical;
}
.field input:focus,
.field textarea:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.14);
}
.hot-editor-actions {
    display: flex;
    gap: 0.6rem;
    flex-wrap: wrap;
}
.hot-editor-hint {
    padding-top: 0.1rem;
    line-height: 1.5;
}
.idle-editor-form {
    display: grid;
    gap: 0.9rem;
    padding: 1rem 1.1rem 1.1rem;
}
@media (max-width: 820px) {
    .hot-editor-grid {
        grid-template-columns: 1fr;
    }
}
"""

JS = """
const HIDDEN_KEY = "tmux-browse:hidden";
const ORDER_KEY  = "tmux-browse:order";
const HOT_KEY    = "tmux-browse:hot-buttons";
const IDLE_KEY   = "tmux-browse:idle-alerts";
const HOT_LOOP_IDLE_SEC = 5;

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
        return { name: text ? hotButtonLabel(text) : "", text };
    }
    if (value && typeof value === "object") {
        const name = typeof value.name === "string" ? value.name.trim() : "";
        const text = typeof value.text === "string" ? value.text.trim() : "";
        return { name, text };
    }
    return { name: "", text: "" };
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

const state = {
    sessions: [],
    openPanes: new Set(),
    nodes: new Map(),
    hidden: new Set(loadJSON(HIDDEN_KEY, [])),
    order: loadJSON(ORDER_KEY, []),   // user-defined priority list; unlisted sessions sort after
    hot: normalizeHotButtons(loadJSON(HOT_KEY, [])),
    hotEditor: { open: false, slot: 0, session: "" },
    idleAlerts: loadJSON(IDLE_KEY, {}),
    idleRuntime: {},
    idleEditor: { open: false, session: "" },
    audioCtx: null,
    hotLoops: {},
};

function saveHidden(set) { saveJSON(HIDDEN_KEY, [...set]); }
function saveOrder(list) { saveJSON(ORDER_KEY, list); }
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

function playIdleTone() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    if (!state.audioCtx) state.audioCtx = new Ctx();
    const ctx = state.audioCtx;
    if (ctx.state === "suspended") {
        ctx.resume().catch(() => {});
        if (ctx.state === "suspended") return;
    }
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    gain.gain.value = 0.0001;
    osc.connect(gain);
    gain.connect(ctx.destination);
    const now = ctx.currentTime;
    gain.gain.exponentialRampToValueAtTime(0.035, now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.35);
    osc.start(now);
    osc.stop(now + 0.38);
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

function hotLoopKey(session, slot) {
    return `${session}::${slot}`;
}

function idleAlertFor(session) {
    return normalizeIdleAlert(state.idleAlerts[session]);
}

function openIdleEditor(session) {
    state.idleEditor.open = true;
    state.idleEditor.session = session;
    renderIdleEditor();
    document.getElementById("idle-modal").hidden = false;
    document.body.style.overflow = "hidden";
}

function closeIdleEditor() {
    state.idleEditor.open = false;
    document.getElementById("idle-modal").hidden = true;
    document.body.style.overflow = "";
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
    const slots = hotButtonsFor(session);
    slots.forEach((slot, idx) => {
        const pair = rec.hotPairs[idx];
        const btn = pair.cmdBtn;
        const present = !!slot.text.trim();
        pair.wrap.hidden = !present;
        pair.wrap.style.display = present ? "inline-flex" : "none";
        pair.loopBtn.hidden = !present;
        pair.loopBtn.style.display = present ? "inline-flex" : "none";
        btn.disabled = !present;
        btn.textContent = hotButtonLabel(slot.name || slot.text);
        btn.title = present ? `${slot.name || "Hot Button " + (idx + 1)}: ${slot.text}` : `hot button ${idx + 1} is empty`;
        if (!present) delete state.hotLoops[hotLoopKey(session, idx)];
        const active = !!state.hotLoops[hotLoopKey(session, idx)];
        pair.loopBtn.className = active ? "btn orange hot-loop-btn is-active" : "btn orange hot-loop-btn";
        pair.loopBtn.title = active
            ? `looping '${slot.name || "Hot Button " + (idx + 1)}' while ${session} is idle`
            : `start loop for '${slot.name || "Hot Button " + (idx + 1)}'`;
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
    const picked = hotButtonsFor(session)[slot] || { name: "", text: "" };
    if (!picked.text.trim()) return;
    const key = hotLoopKey(session, slot);
    if (state.hotLoops[key]) delete state.hotLoops[key];
    else state.hotLoops[key] = { waitingForActive: false, busy: false };
    renderHotButtons(session);
}

async function checkHotLoops(rows) {
    const byName = new Map(rows.map((row) => [row.name, row]));
    for (const [key, loop] of Object.entries(state.hotLoops)) {
        const splitAt = key.lastIndexOf("::");
        const session = key.slice(0, splitAt);
        const slot = Number(key.slice(splitAt + 2));
        const row = byName.get(session);
        const picked = hotButtonsFor(session)[slot] || { name: "", text: "" };
        if (!row || !picked.text.trim()) {
            delete state.hotLoops[key];
            continue;
        }
        if (loop.busy) continue;
        if ((row.idle_seconds || 0) < HOT_LOOP_IDLE_SEC) {
            loop.waitingForActive = false;
            continue;
        }
        if (loop.waitingForActive) continue;
        loop.busy = true;
        try {
            await sendHotButton(session, slot);
            loop.waitingForActive = true;
        } finally {
            loop.busy = false;
        }
    }
}

function openHotButtons(session, slot = 0) {
    state.hotEditor.open = true;
    state.hotEditor.session = session;
    state.hotEditor.slot = slot;
    renderHotEditor();
    document.getElementById("hot-modal").hidden = false;
    document.body.style.overflow = "hidden";
}

function closeHotButtons() {
    state.hotEditor.open = false;
    document.getElementById("hot-modal").hidden = true;
    document.body.style.overflow = "";
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
            el("span", { class: "hot-slot-command" }, slot.text || "No command yet"),
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
    document.getElementById("hot-modal-title").textContent =
        `Hot Buttons · ${state.hotEditor.session}`;
}

function saveHotButton() {
    const slot = state.hotEditor.slot;
    state.hot[slot] = {
        name: document.getElementById("hot-name").value.trim(),
        text: document.getElementById("hot-command").value.trim(),
    };
    saveHot();
    for (const s of state.sessions) renderHotButtons(s.name);
    renderHotEditor();
}

function clearHotButton() {
    state.hot[state.hotEditor.slot] = { name: "", text: "" };
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
            summaryTabLink, logLink, scrollBtn, hideBtn, reorderPad),
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
    const actions = el("div", { class: "pane-actions" },
        el("button", { class: "btn green", onclick: () => launch(s.name) }, "Launch"),
        el("button", { class: "btn orange", onclick: () => stopTtyd(s.name) }, "Stop ttyd"),
        bodyKillBtn, msg, hotManageBtn, ...hotPairs.map((pair) => pair.wrap),
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
        if (details.open && !state.openPanes.has(s.name)) {
            launch(s.name);
        }
    });

    // Drag-and-drop: only the reorderPad initiates drags. Any <details> is a
    // valid drop target — dropping on it inserts the dragged pane before it.
    details.addEventListener("dragover", (e) => {
        if (!e.dataTransfer.types.includes("text/x-tmux-browse-session")) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        details.classList.add("drag-over");
    });
    details.addEventListener("dragleave", () => details.classList.remove("drag-over"));
    details.addEventListener("drop", (e) => {
        const dragged = e.dataTransfer.getData("text/x-tmux-browse-session");
        details.classList.remove("drag-over");
        if (!dragged) return;
        e.preventDefault();
        dropOnSession(s.name, dragged);
    });

    return {
        details, sbadges, idle, idleAlertBtn,
        summaryTabLink, logLink, hideBtn,
        iframe, fPort, fPid, fCreated,
        hotPairs,
    };
}

function updatePane(rec, s) {
    // Badges
    rec.sbadges.textContent = "";
    if (s.attached > 0) {
        rec.sbadges.append(el("span", { class: "badge attached" }, `${s.attached} clients`));
    }
    rec.sbadges.append(el("span", { class: "badge" }, `${s.windows}w`));
    if (s.ttyd_running) {
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
    rec.summaryTabLink.style.display = s.ttyd_running ? "" : "none";

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
    const target = state.hidden.has(name)
        ? document.getElementById("sessions-hidden")
        : document.getElementById("sessions");
    if (rec.details.parentNode !== target) {
        target.append(rec.details);
    }
    rec.hideBtn.textContent = state.hidden.has(name) ? "Unhide" : "Hide";
}

function reappendInOrder() {
    // Walk visible sessions in sorted order and re-append each pane so the
    // DOM matches state.order. Re-appending an existing node just moves it.
    const visible = state.sessions
        .map(s => s.name)
        .filter(n => !state.hidden.has(n));
    const main = document.getElementById("sessions");
    for (const name of sortedSessionNames(visible)) {
        const rec = state.nodes.get(name);
        if (rec) main.append(rec.details);
    }
    const hiddenNames = state.sessions
        .map(s => s.name)
        .filter(n => state.hidden.has(n));
    const hiddenRoot = document.getElementById("sessions-hidden");
    for (const name of sortedSessionNames(hiddenNames)) {
        const rec = state.nodes.get(name);
        if (rec) hiddenRoot.append(rec.details);
    }
}

function moveSession(name, delta) {
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

function dropOnSession(targetName, draggedName) {
    if (!draggedName || draggedName === targetName) return;
    const liveNames = state.sessions.map(s => s.name);
    const sameBucket = state.hidden.has(draggedName) === state.hidden.has(targetName);
    if (!sameBucket) return;  // dragging between main/hidden lists isn't a reorder

    const bucket = state.hidden.has(draggedName)
        ? liveNames.filter(n => state.hidden.has(n))
        : liveNames.filter(n => !state.hidden.has(n));
    const current = sortedSessionNames(bucket);
    const from = current.indexOf(draggedName);
    let to = current.indexOf(targetName);
    if (from < 0 || to < 0) return;
    current.splice(from, 1);
    if (from < to) to -= 1;  // index shifts after removal
    current.splice(to, 0, draggedName);

    const otherBucket = state.hidden.has(draggedName)
        ? sortedSessionNames(liveNames.filter(n => !state.hidden.has(n)))
        : sortedSessionNames(liveNames.filter(n => state.hidden.has(n)));
    state.order = state.hidden.has(draggedName)
        ? [...otherBucket, ...current]
        : [...current, ...otherBucket];
    saveOrder(state.order);
    reappendInOrder();
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
    else state.hidden.add(name);
    saveHidden(state.hidden);
    const rec = state.nodes.get(name);
    if (rec) placePane(rec, name);
    refreshHiddenChrome();
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

    const visibleCount = sessions.filter(s => !state.hidden.has(s.name)).length;
    const empty = document.getElementById("empty");
    if (visibleCount === 0 && !empty) {
        root.append(el("div", { id: "empty", class: "empty-state" },
            sessions.length === 0
                ? "No tmux sessions. Create one above."
                : "All sessions are hidden — open the list below."));
    } else if (visibleCount > 0 && empty) {
        empty.remove();
    }

    document.getElementById("count").textContent =
        `${sessions.length} session${sessions.length === 1 ? "" : "s"}`;
    refreshHiddenChrome();
}

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("refresh-btn").addEventListener("click", refresh);
    document.getElementById("new-btn").addEventListener("click", newSession);
    document.getElementById("restart-btn").addEventListener("click", restartDashboard);
    document.getElementById("hot-close-btn").addEventListener("click", closeHotButtons);
    document.getElementById("hot-save-btn").addEventListener("click", saveHotButton);
    document.getElementById("hot-clear-btn").addEventListener("click", clearHotButton);
    document.getElementById("idle-close-btn").addEventListener("click", closeIdleEditor);
    document.getElementById("idle-save-btn").addEventListener("click", saveIdleEditor);
    document.getElementById("idle-clear-btn").addEventListener("click", clearIdleEditor);
    document.getElementById("hot-modal").addEventListener("click", (e) => {
        if (e.target.id === "hot-modal") closeHotButtons();
    });
    document.getElementById("idle-modal").addEventListener("click", (e) => {
        if (e.target.id === "idle-modal") closeIdleEditor();
    });
    document.getElementById("new-name").addEventListener("keydown", (e) => {
        if (e.key === "Enter") newSession();
    });
    document.addEventListener("pointerdown", primeAudio, { passive: true });
    document.addEventListener("keydown", primeAudio);
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && state.hotEditor.open) closeHotButtons();
        if (e.key === "Escape" && state.idleEditor.open) closeIdleEditor();
    });
    refresh();
    setInterval(refresh, 5000);
});
"""
