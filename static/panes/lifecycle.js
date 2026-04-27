// Pane lifecycle helpers: launch coding sessions, start/stop ttyd,
// kill tmux sessions, kick a raw shell, create a new session via the
// top-bar input, restart the dashboard server, and the iframe-fit
// helpers (resizePane / stepIframeSize / fitTmuxToIframe) that drive
// the ±W / ±H / fit chrome.
//
// All of these are top-level handlers wired into the dashboard either
// from button clicks (panes.js init) or from per-pane controls
// rendered by createPane.

const STEP_PX_W = 80;
const STEP_PX_H = 60;

// Federation routing: when a session lives on a remote peer the
// row carries peer_url + peer_hostname. Local API calls (start /
// stop ttyd, kill, etc.) need to hit the peer's HTTP surface, not
// ours, and must use the un-prefixed session name. _peerInfo()
// returns the row's federation tags or null for local sessions.
function _peerInfo(displayName) {
    const row = state.sessions.find((r) => r.name === displayName);
    if (!row || !row.peer_url) return null;
    return {
        baseUrl: row.peer_url,
        hostname: row.peer_hostname || displayName.split(":")[0],
        // The tmux session name on the *peer* — strip our hostname prefix.
        realName: displayName.includes(":") ? displayName.slice(displayName.indexOf(":") + 1) : displayName,
    };
}

// API helper that respects federation routing. Passes the
// fully-qualified URL when the session is remote so fetch() goes
// directly to the peer; falls back to the relative path for local.
async function _peerApi(displayName, method, path, body) {
    const p = _peerInfo(displayName);
    if (!p) return await api(method, path, body);
    return await api(method, p.baseUrl + path, body);
}

// Resolve to the real session name on whichever host owns it.
function _peerSessionName(displayName) {
    const p = _peerInfo(displayName);
    return p ? p.realName : displayName;
}

async function launchCodingSession(label, cmd) {
    const slug = label.toLowerCase().replace(/[\s-]+/g, "_");
    let name;
    if (state.config.launch_ask_name) {
        name = prompt(`Name the tmux session:`, slug);
        if (!name) return;
        name = name.trim().replace(/\s+/g, "_");
    } else {
        const uid = Date.now().toString(36).slice(-4);
        name = `${slug}_${uid}`;
    }
    const cwd = state.config.launch_cwd || undefined;
    const r = await api("POST", "/api/session/new", { name, cmd, cwd, launch_ttyd: true });
    if (r.ok && r.port) {
        if (state.config.launch_open_tab) {
            window.open(ttydUrl(r.port), "_blank", "noopener");
        }
        await refresh();
    } else if (r.ok) {
        await refresh();
    } else {
        alert(r.error || "launch failed");
    }
}

async function resizePane(session, cols) {
    await api("POST", "/api/session/resize", { session, cols });
    const rec = state.nodes.get(session);
    if (!rec || !rec.iframeWrap) return;
    const cur = rec.iframeWrap.style.height;
    const maxH = "90vh";
    const defaultH = `${state.config.default_ttyd_height_vh || 70}vh`;
    // Toggle: if already at max, go to default; otherwise go to max
    rec.iframeWrap.style.height = cur === maxH ? defaultH : maxH;
}

// Adjust the iframe wrapper's pixel size in one axis, then re-fit
// tmux to the new dimensions. Bottom of the iframe is the only
// edge that can grow vertically without affecting other panes;
// horizontal grow goes beyond the layout row's natural share, which
// is intentional — operators who want a single pane wider can
// override the row's even-share behavior by hand.
function stepIframeSize(session, axis, deltaPx) {
    const rec = state.nodes.get(session);
    if (!rec || !rec.iframeWrap) return;
    const wrap = rec.iframeWrap;
    if (axis === "w") {
        // Anchor to current pixel width before applying delta — without
        // this the very first click loses the percentage-based default.
        const curW = wrap.getBoundingClientRect().width;
        const next = Math.max(160, Math.round(curW + deltaPx));
        wrap.style.width = next + "px";
        wrap.style.maxWidth = "none";  // override layout-row constraints
    } else if (axis === "h") {
        const curH = wrap.getBoundingClientRect().height;
        const next = Math.max(120, Math.round(curH + deltaPx));
        wrap.style.height = next + "px";
    }
    requestAnimationFrame(() => fitTmuxToIframe(session));
}

// Resize the tmux window to match the iframe's actual dimensions so the
// embedded terminal fills its visible area instead of leaving blank
// borders. Used by both the maximize button and the dedicated tmux-
// resize chrome icon.
async function fitTmuxToIframe(session) {
    const rec = state.nodes.get(session);
    if (!rec || !rec.iframeWrap || !rec.iframe) return;
    const w = rec.iframe.clientWidth || rec.iframeWrap.clientWidth;
    const h = rec.iframe.clientHeight || rec.iframeWrap.clientHeight;
    if (!w || !h) return;
    const cellW = Number(state.config.ttyd_cell_width_px) || 7.7;
    const cellH = Number(state.config.ttyd_cell_height_px) || 17;
    const cols = Math.max(20, Math.min(500, Math.round(w / cellW)));
    const rows = Math.max(5, Math.min(200, Math.round(h / cellH)));
    const r = await api("POST", "/api/session/resize", { session, cols, rows });
    const msg = document.getElementById("msg-" + cssId(session));
    if (msg) {
        msg.textContent = r.ok
            ? `tmux ${cols}×${rows} (iframe ${w}×${h}px, cell ${cellW}×${cellH}px)`
            : ("resize error: " + (r.error || "unknown"));
        msg.className = r.ok ? "inline-msg ok" : "inline-msg err";
    }
}

async function launch(session) {
    const msg = document.getElementById("msg-" + cssId(session));
    if (msg) msg.textContent = "starting…";
    const peer = _peerInfo(session);
    const r = await _peerApi(session, "POST", "/api/ttyd/start",
                              { session: _peerSessionName(session) });
    if (!r.ok) {
        if (msg) { msg.textContent = "error: " + (r.error || "unknown"); msg.className = "inline-msg err"; }
        return;
    }
    // Local sessions: ttydUrl(port) builds a same-origin URL so the
    // browser hits 7700-7799 on the dashboard host. Remote sessions:
    // the peer's response carries a 'url' field already pointing at
    // its own host:port, which is exactly what we want — the browser
    // connects directly to the peer's ttyd.
    const url = peer ? (r.url || `${peer.baseUrl.replace(/\/$/, "")}:${r.port}`) : ttydUrl(r.port);
    const iframe = document.getElementById("iframe-" + cssId(session));
    if (iframe) iframe.src = url;
    if (msg) { msg.textContent = r.already ? "attached" : "launched"; msg.className = "inline-msg ok"; }
    state.openPanes.add(session);
}

async function openRawTtyd() {
    const r = await api("POST", "/api/ttyd/raw", {});
    if (!r.ok) {
        alert("Error: " + (r.error || "unknown"));
        return;
    }
    if (r.name) {
        state.openPanes.add(r.name);
        if (!state.order.includes(r.name)) {
            state.order.push(r.name);
            saveOrder(state.order);
        }
    }
    await refresh();
    if (r.name) {
        const rec = state.nodes.get(r.name);
        if (rec && rec.details) {
            rec.details.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
    }
}

async function enterCopyMode(session) {
    const msg = document.getElementById("msg-" + cssId(session));
    const r = await api("POST", "/api/session/scroll", { session });
    if (msg) {
        msg.textContent = r.ok ? "scroll mode" : ("error: " + (r.error || ""));
        msg.className = r.ok ? "inline-msg ok" : "inline-msg err";
    }
}

// Toggle tmux's pane-zoom on the active pane of the session
// (equivalent to the C-b z binding / ``resize-pane -Z``).
async function zoomPane(session) {
    const msg = document.getElementById("msg-" + cssId(session));
    const r = await api("POST", "/api/session/zoom", { session });
    if (msg) {
        msg.textContent = r.ok ? "pane zoom toggled" : ("error: " + (r.error || ""));
        msg.className = r.ok ? "inline-msg ok" : "inline-msg err";
    }
}

async function stopTtyd(session) {
    const r = await _peerApi(session, "POST", "/api/ttyd/stop",
                              { session: _peerSessionName(session) });
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
    const r = await _peerApi(session, "POST", "/api/session/kill",
                              { session: _peerSessionName(session) });
    const msg = document.getElementById("msg-" + cssId(session));
    if (msg) {
        msg.textContent = r.ok ? "killed" : ("error: " + (r.error || ""));
        msg.className = r.ok ? "inline-msg ok" : "inline-msg err";
    }
    state.openPanes.delete(session);
    refresh();
}

// Counterpart to killSession for raw ttyd shells: there's no tmux
// session to kill, just a ttyd process to stop. The pane is removed
// on the next refresh because the server drops the shell from
// /api/sessions when its pidfile is gone.
async function stopRawShell(name) {
    const r = await api("POST", "/api/ttyd/stop", { session: name });
    const msg = document.getElementById("msg-" + cssId(name));
    if (msg && r) {
        msg.textContent = r.ok ? "stopped" : ("error: " + (r.error || ""));
        msg.className = r.ok ? "inline-msg ok" : "inline-msg err";
    }
    state.openPanes.delete(name);
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
