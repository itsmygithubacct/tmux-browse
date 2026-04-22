"""Top-level dashboard HTML template."""

import json

from . import static


def render_index() -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>tmux-browse</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>{static.CSS}</style>
</head>
<body>
<div class="topbar">
    <h1>tmux sessions <span class="dim" id="count" style="font-size:0.85rem"></span></h1>
    <input type="text" id="new-name" placeholder="new session name" />
    <button class="btn green" id="new-btn">New session</button>
    <button class="btn blue" id="raw-btn" title="open a standalone ttyd shell not attached to tmux">Raw ttyd</button>
    <button class="btn blue" id="refresh-btn">Refresh</button>
    <span class="dim" id="topbar-status" style="margin-left:auto;font-size:0.8rem">
        auto-refresh off &middot; ttyd spawns on pane expand
    </span>
    <button class="btn red" id="restart-btn" title="restart the dashboard server process">Restart</button>
</div>
<div id="sessions"></div>
<details id="hidden-wrap" class="hidden-list" hidden>
    <summary>Hidden (<span id="hidden-count">0</span>)</summary>
    <div id="sessions-hidden"></div>
</details>
<details id="config-wrap" class="config-pane">
    <summary>Config</summary>
    <div class="config-body">
        <div class="config-grid">
            <section class="config-card">
                <div class="config-card-title">Behavior</div>
                <label class="check-row">
                    <input type="checkbox" id="cfg-auto-refresh" />
                    <span>Enable auto refresh</span>
                </label>
                <label class="field">
                    <span>Refresh seconds</span>
                    <input type="number" id="cfg-refresh-seconds" min="1" max="300" step="1" />
                </label>
                <label class="field">
                    <span>Hot loop idle wait seconds</span>
                    <input type="number" id="cfg-hot-loop-idle-seconds" min="1" max="3600" step="1" />
                </label>
                <label class="field">
                    <span>Default agent step budget</span>
                    <input type="number" id="cfg-agent-max-steps" min="1" max="1000" step="1" />
                </label>
                <label class="check-row">
                    <input type="checkbox" id="cfg-launch-on-expand" />
                    <span>Launch ttyd when a pane opens</span>
                </label>
                <label class="field">
                    <span>Default ttyd height (vh)</span>
                    <input type="number" id="cfg-default-height" min="20" max="95" step="1" />
                </label>
                <label class="field">
                    <span>Default ttyd min height (px)</span>
                    <input type="number" id="cfg-min-height" min="120" max="900" step="10" />
                </label>
                <label class="field">
                    <span>Idle alert sound</span>
                    <span class="sound-row">
                        <select id="cfg-idle-sound">
                            <option value="beep">Beep (880 Hz sine)</option>
                            <option value="chime">Chime (two-note)</option>
                            <option value="knock">Knock (double thud)</option>
                            <option value="bell">Bell (long decay)</option>
                            <option value="blip">Blip (short square)</option>
                            <option value="ding">Ding (high sine)</option>
                        </select>
                        <button type="button" class="btn" id="cfg-sound-test" title="play the selected sound">Test</button>
                    </span>
                </label>
            </section>
            <section class="config-card">
                <div class="config-card-title">Summary Row <button class="btn toggle-all-btn" type="button" id="cfg-toggle-all-summary">All On</button></div>
                <label class="check-row"><input type="checkbox" id="cfg-show-attached-badge" /><span>Attached clients badge</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-window-badge" /><span>Window count badge</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-port-badge" /><span>Running ttyd port badge</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-idle-text" /><span>Idle text</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-idle-alert-button" /><span>Idle Alert button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-open" /><span>Open button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-log" /><span>Log button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-scroll" /><span>Scroll button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-split" /><span>Side-by-side button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-hide" /><span>Hide button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-reorder" /><span>Reorder pad</span></label>
            </section>
            <section class="config-card">
                <div class="config-card-title">Expanded Pane <button class="btn toggle-all-btn" type="button" id="cfg-toggle-all-body">All On</button></div>
                <label class="check-row"><input type="checkbox" id="cfg-show-body-launch" /><span>Launch button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-body-stop" /><span>Stop ttyd button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-body-kill" /><span>Kill button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-body-send-bar" /><span>Send bar</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-body-hot-buttons" /><span>Hot Buttons manager</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-hot-loop-toggles" /><span>Hot-button loop toggles</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-footer" /><span>Footer metadata</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-inline-messages" /><span>Inline status messages</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-topbar-status" /><span>Top bar status text</span></label>
            </section>
            <section class="config-card">
                <div class="config-card-title">Agent</div>
                <label class="field">
                    <span>Configured agent</span>
                    <select id="cfg-agent-existing"></select>
                </label>
                <label class="field">
                    <span>Preset</span>
                    <select id="cfg-agent-preset"></select>
                </label>
                <label class="field">
                    <span>Name</span>
                    <input type="text" id="cfg-agent-name" placeholder="gpt" />
                </label>
                <label class="field">
                    <span>Provider</span>
                    <input type="text" id="cfg-agent-provider" placeholder="openai" />
                </label>
                <label class="field">
                    <span>Model</span>
                    <input type="text" id="cfg-agent-model" placeholder="gpt-5.4" />
                </label>
                <label class="field">
                    <span>Base URL</span>
                    <input type="url" id="cfg-agent-base-url" placeholder="https://api.openai.com/v1" />
                </label>
                <label class="field">
                    <span>Wire API</span>
                    <select id="cfg-agent-wire-api">
                        <option value="openai-chat">openai-chat</option>
                        <option value="anthropic-messages">anthropic-messages</option>
                    </select>
                </label>
                <label class="field">
                    <span>API key</span>
                    <input type="password" id="cfg-agent-api-key" placeholder="Leave blank to keep existing key" />
                </label>
                <div class="hot-editor-actions">
                    <button class="btn green" id="cfg-agent-save-btn" type="button">Save Agent</button>
                    <button class="btn blue" id="cfg-agent-reload-btn" type="button">Reload Agents</button>
                    <button class="btn red" id="cfg-agent-remove-btn" type="button">Remove Agent</button>
                </div>
                <div class="dim config-card-note" id="cfg-agent-summary">
                    Agents are stored separately from dashboard-config.json.
                </div>
                <div class="dim" id="cfg-agent-status">
                    Load a preset or existing agent, then save to write ~/.tmux-browse/agents.json and the secret store.
                </div>
            </section>
        </div>
        <div class="config-actions">
            <button class="btn green" id="cfg-save-btn">Save Config</button>
            <button class="btn blue" id="cfg-load-btn">Load From File</button>
            <button class="btn" id="cfg-reset-btn">Defaults</button>
            <span class="dim" id="cfg-status">Saved to ~/.tmux-browse/dashboard-config.json</span>
        </div>
    </div>
</details>
<details id="agents-wrap" class="config-pane" hidden>
    <summary>Agents (<span id="agents-count">0</span>)</summary>
    <div class="config-body">
        <div id="agents-pane" class="agent-grid"></div>
    </div>
</details>
<div id="agent-steps-modal" class="modal-backdrop" hidden>
    <div class="modal-card hot-modal" role="dialog" aria-modal="true" aria-labelledby="agent-steps-modal-title">
        <div class="modal-head">
            <div>
                <div class="modal-eyebrow">Agent Transcript</div>
                <h2 id="agent-steps-modal-title">Agent Steps</h2>
            </div>
            <button class="btn" id="agent-steps-close-btn" title="close the step viewer">Close</button>
        </div>
        <div class="agent-steps-grid">
            <div class="hot-slot-list" id="agent-steps-list"></div>
            <div class="agent-steps-detail" id="agent-steps-detail"></div>
        </div>
    </div>
</div>
<div id="hot-modal" class="modal-backdrop" hidden>
    <div class="modal-card hot-modal" role="dialog" aria-modal="true" aria-labelledby="hot-modal-title">
        <div class="modal-head">
            <div>
                <div class="modal-eyebrow">Global shortcuts</div>
                <h2 id="hot-modal-title">Hot Buttons</h2>
            </div>
            <button class="btn" id="hot-close-btn" title="close the hot-button editor">Close</button>
        </div>
        <div class="hot-editor-grid">
            <div class="hot-slot-list" id="hot-slot-list"></div>
            <div class="hot-editor-form">
                <label class="field">
                    <span>Button name</span>
                    <input type="text" id="hot-name" maxlength="40" placeholder="Review + improve" />
                </label>
                <label class="field">
                    <span>Command text</span>
                    <textarea id="hot-command" rows="6" placeholder="review and improve"></textarea>
                </label>
                <label class="field">
                    <span>Loop count</span>
                    <input type="number" id="hot-loop-count" min="0" step="1" value="0" />
                </label>
                <div class="hot-editor-actions">
                    <button class="btn green" id="hot-save-btn">Save</button>
                    <button class="btn red" id="hot-clear-btn">Clear</button>
                </div>
                <div class="dim hot-editor-hint">
                    Edit from any pane. The same shared hot buttons appear in every session pane and send their command to that pane's active terminal. Loop count `0` means run forever; any positive number stops after that many idle-triggered sends.
                </div>
            </div>
        </div>
    </div>
</div>
<div id="workflow-modal" class="modal-backdrop" hidden>
    <div class="modal-card hot-modal" role="dialog" aria-modal="true" aria-labelledby="workflow-modal-title">
        <div class="modal-head">
            <div>
                <div class="modal-eyebrow">Conversation Mode</div>
                <h2 id="workflow-modal-title">Agent Workflows</h2>
            </div>
            <button class="btn" id="workflow-close-btn" title="close the workflow editor">Close</button>
        </div>
        <div class="hot-editor-grid">
            <div class="hot-slot-list" id="workflow-slot-list"></div>
            <div class="hot-editor-form">
                <label class="field">
                    <span>Workflow name</span>
                    <input type="text" id="workflow-name" maxlength="80" placeholder="Morning sweep" />
                </label>
                <label class="field">
                    <span>Prompt</span>
                    <textarea id="workflow-prompt" rows="6" placeholder="tell me what changed in the panes since the last run"></textarea>
                </label>
                <label class="field">
                    <span>Run every seconds</span>
                    <input type="number" id="workflow-interval" min="5" max="86400" step="5" value="300" />
                </label>
                <div class="hot-editor-actions">
                    <button class="btn green" id="workflow-save-btn">Save</button>
                    <button class="btn red" id="workflow-clear-btn">Clear</button>
                </div>
                <div class="dim hot-editor-hint">
                    Workflows are saved server-side and run in the conversation REPL pane when the workflow switch is enabled. Each workflow sends its prompt into the agent REPL on its own interval.
                </div>
            </div>
        </div>
    </div>
</div>
<div id="idle-modal" class="modal-backdrop" hidden>
    <div class="modal-card idle-modal" role="dialog" aria-modal="true" aria-labelledby="idle-modal-title">
        <div class="modal-head">
            <div>
                <div class="modal-eyebrow">Session monitoring</div>
                <h2 id="idle-modal-title">Idle Alert</h2>
            </div>
            <button class="btn" id="idle-close-btn" title="close the idle-alert editor">Close</button>
        </div>
        <div class="idle-editor-form">
            <label class="check-row">
                <input type="checkbox" id="idle-enabled" />
                <span>Enable idle detection for this session</span>
            </label>
            <label class="field">
                <span>Trigger after idle seconds</span>
                <input type="number" id="idle-threshold" min="5" step="5" value="300" />
            </label>
            <div class="field">
                <span>Notification type</span>
                <label class="check-row">
                    <input type="checkbox" id="idle-sound" checked />
                    <span>Sound</span>
                </label>
                <label class="check-row">
                    <input type="checkbox" id="idle-prompt" />
                    <span>Prompt</span>
                </label>
            </div>
            <div class="hot-editor-actions">
                <button class="btn green" id="idle-save-btn">Save</button>
                <button class="btn red" id="idle-clear-btn">Disable</button>
            </div>
            <div class="dim hot-editor-hint">
                When enabled, the dashboard watches this session's idle timer and fires once when it crosses the configured threshold. It rearms after the session becomes active again.
            </div>
        </div>
    </div>
</div>
<div id="split-modal" class="modal-backdrop" hidden>
    <div class="modal-card split-modal" role="dialog" aria-modal="true" aria-labelledby="split-modal-title">
        <div class="modal-head">
            <div>
                <div class="modal-eyebrow">Side By Side</div>
                <h2 id="split-modal-title">Split Right</h2>
            </div>
            <button class="btn" id="split-close-btn" title="close the split chooser">Close</button>
        </div>
        <div class="split-picker-body">
            <label class="field">
                <span>Filter sessions</span>
                <input type="text" id="split-search" class="split-search" placeholder="Search visible sessions" />
            </label>
            <div class="split-target-list" id="split-target-list"></div>
            <div class="dim hot-editor-hint">
                Pick a session to place the current one on its right. You can also drag the split button onto a session and snap left, right, or above it.
            </div>
        </div>
    </div>
</div>
<script>{static.JS}</script>
</body>
</html>
"""


def render_raw_ttyd(name: str, port: int, scheme: str) -> str:
    quoted_name = json.dumps(name)
    quoted_port = json.dumps(port)
    quoted_scheme = json.dumps("https" if scheme == "https" else "http")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>raw ttyd</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{
    margin: 0;
    font: 14px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: #0d1117;
    color: #e6edf3;
}}
.raw-shell {{
    min-height: 100vh;
    display: grid;
    grid-template-rows: auto 1fr;
}}
.raw-topbar {{
    display: flex;
    gap: 0.75rem;
    align-items: center;
    padding: 0.85rem 1rem;
    border-bottom: 1px solid #30363d;
    background: #161b22;
}}
.raw-title {{
    font-weight: 600;
}}
.raw-meta {{
    color: #8b949e;
    font-size: 0.88rem;
}}
.raw-spacer {{
    margin-left: auto;
}}
.btn {{
    border: 1px solid #30363d;
    border-radius: 6px;
    background: #21262d;
    color: #e6edf3;
    padding: 0.45rem 0.75rem;
    cursor: pointer;
}}
.btn.red {{
    background: #3b1117;
    border-color: #8b1e2d;
}}
.btn:disabled {{
    opacity: 0.65;
    cursor: default;
}}
#raw-msg {{
    color: #8b949e;
    font-size: 0.88rem;
}}
iframe {{
    width: 100%;
    height: calc(100vh - 58px);
    border: 0;
    background: #000;
}}
</style>
</head>
<body>
<div class="raw-shell">
    <div class="raw-topbar">
        <div>
            <div class="raw-title" id="raw-title"></div>
            <div class="raw-meta" id="raw-meta"></div>
        </div>
        <span class="raw-spacer"></span>
        <span id="raw-msg">Running</span>
        <button class="btn" id="raw-open-direct" type="button">Open Direct</button>
        <button class="btn red" id="raw-stop" type="button">Stop</button>
    </div>
    <iframe id="raw-frame" allow="clipboard-read; clipboard-write"></iframe>
</div>
<script>
const rawName = {quoted_name};
const rawPort = {quoted_port};
const rawScheme = {quoted_scheme};
let stopping = false;

function ttydUrl(port) {{
    return `${{rawScheme}}//${{window.location.hostname}}:${{port}}/`;
}}

async function stopRaw(closeWindow = false) {{
    if (stopping) return;
    stopping = true;
    document.getElementById("raw-stop").disabled = true;
    document.getElementById("raw-msg").textContent = "Stopping…";
    try {{
        const res = await fetch("/api/ttyd/stop", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ session: rawName }}),
            keepalive: true,
        }});
        const text = await res.text();
        let data = {{}};
        try {{ data = text ? JSON.parse(text) : {{ ok: res.ok }}; }} catch {{ data = {{ ok: res.ok }}; }}
        document.getElementById("raw-msg").textContent = data.ok ? "Stopped" : `Error: ${{data.error || "unknown"}}`;
    }} catch (_err) {{
        document.getElementById("raw-msg").textContent = "Stop request failed";
    }}
    if (closeWindow) window.close();
}}

window.addEventListener("pagehide", () => {{
    if (stopping) return;
    const blob = new Blob([JSON.stringify({{ session: rawName }})], {{ type: "application/json" }});
    navigator.sendBeacon("/api/ttyd/stop", blob);
}});

const url = ttydUrl(rawPort);
document.title = `raw ttyd · ${{rawName}}`;
document.getElementById("raw-title").textContent = rawName;
document.getElementById("raw-meta").textContent = `port ${{rawPort}}`;
document.getElementById("raw-frame").src = url;
document.getElementById("raw-open-direct").addEventListener("click", () => window.open(url, "_blank", "noopener"));
document.getElementById("raw-stop").addEventListener("click", () => stopRaw(true));
</script>
</body>
</html>
"""
