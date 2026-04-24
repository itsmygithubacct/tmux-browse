// sharing.js — connected endpoints and QR config transfer

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

// Sharable dashboard state — anything in this payload round-trips
// through QR or import-cfg link. Deliberately excluded:
// - unlockToken: per-device security; never leaves the browser.
// - agents.json / agent-secrets.json: server-side, hold API keys.
// - REPL conversations / KB (Phase C): ephemeral, per-conversation.
function collectViewConfig() {
    return {
        dashboard: state.config,
        hidden: [...state.hidden],
        order: state.order,
        layout: state.layout,
        hot: state.hot,
        idleAlerts: state.idleAlerts,
        phoneKeys: loadPhoneKeys(),
        groups: state.groups,
        hooks: state.agentHooksForShare || null,  // populated by hooks editor on load
        conductor: state.conductorRules || null,   // rule set, not decision log
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
    if (cfg.groups) {
        state.groups = normalizeGroups(cfg.groups);
        saveGroups();
    }
    if (cfg.hooks) {
        // Persist via the gated server endpoint. If this host has a
        // config lock, api() will prompt for the unlock token.
        api("POST", "/api/agent-hooks", { hooks: cfg.hooks }).then((r) => {
            if (r && r.ok && r.hooks) {
                state.agentHooksForShare = r.hooks;
                if (typeof renderHooksEditor === "function") renderHooksEditor();
            }
        });
    }
    if (cfg.conductor) {
        // Same shape as the Conductor editor submits: {rules: [...]}.
        // Server validates and config-lock gates it.
        api("POST", "/api/agent-conductor", { rules: cfg.conductor }).then((r) => {
            if (r && r.ok) {
                state.conductorRules = r.rules || [];
                if (typeof loadConductor === "function") loadConductor();
            }
        });
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

