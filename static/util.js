// util.js — DOM helpers, formatting, API wrapper

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
    const stateOpen = state.hotEditor.open || state.idleEditor.open || state.splitPicker.open || state.workflowEditor.open || state.stepViewer.open;
    const helpOpen = !document.getElementById("tmux-help-modal")?.hidden;
    const qrOpen = !document.getElementById("qr-modal")?.hidden;
    document.body.style.overflow = (stateOpen || helpOpen || qrOpen) ? "hidden" : "";
}

function setVisible(node, visible, display = "") {
    if (!node) return;
    node.hidden = !visible;
    node.style.display = visible ? display : "none";
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


const UNLOCK_TOKEN_KEY = "tmux-browse:unlock-token";

function getStoredUnlockToken() {
    try { return localStorage.getItem(UNLOCK_TOKEN_KEY) || ""; }
    catch { return ""; }
}

function setStoredUnlockToken(token) {
    try {
        if (token) localStorage.setItem(UNLOCK_TOKEN_KEY, token);
        else localStorage.removeItem(UNLOCK_TOKEN_KEY);
    } catch (_) { /* storage disabled — nothing we can do */ }
}

async function api(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
    }
    // Attach the unlock token on every non-GET — the server ignores it when
    // no config lock is active, so this is safe without feature-detection.
    if (method && method.toUpperCase() !== "GET") {
        const token = getStoredUnlockToken();
        if (token) opts.headers["X-TB-Unlock-Token"] = token;
    }
    let r = await fetch(path, opts);
    // 403 with the "config locked" error means the token was missing,
    // stale, or the lock was just set. Prompt for the password once and
    // retry; if the retry still 403s, give up and let the caller render
    // the error normally.
    if (r.status === 403) {
        const probe = await r.clone().text();
        if (probe.includes("config locked") && typeof promptForUnlock === "function") {
            const got = await promptForUnlock();
            if (got) {
                opts.headers["X-TB-Unlock-Token"] = got;
                r = await fetch(path, opts);
            }
        } else {
            // Return the parsed original response below.
            const text = probe;
            try { return JSON.parse(text); }
            catch { return { ok: false, raw: text, status: 403 }; }
        }
    }
    const text = await r.text();
    if (!text) {
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


function cssId(s) {
    return s.replace(/[^a-zA-Z0-9_-]/g, "_");
}
