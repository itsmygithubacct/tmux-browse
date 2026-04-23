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
    const open = state.hotEditor.open || state.idleEditor.open || state.splitPicker.open || state.workflowEditor.open || state.stepViewer.open;
    document.body.style.overflow = open ? "hidden" : "";
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


function cssId(s) {
    return s.replace(/[^a-zA-Z0-9_-]/g, "_");
}

// Create a pane once per session and reuse it across refreshes, so active
