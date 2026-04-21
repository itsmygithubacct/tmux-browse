"""Top-level dashboard HTML template."""

from . import static


def render_index() -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>tmux-browse</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{static.CSS}</style>
</head>
<body>
<div class="topbar">
    <h1>tmux sessions <span class="dim" id="count" style="font-size:0.85rem"></span></h1>
    <input type="text" id="new-name" placeholder="new session name" />
    <button class="btn green" id="new-btn">New session</button>
    <button class="btn blue" id="refresh-btn">Refresh</button>
    <span class="dim" style="margin-left:auto;font-size:0.8rem">
        auto-refresh 5s &middot; ttyd spawns on pane expand
    </span>
    <button class="btn red" id="restart-btn" title="restart the dashboard server process">Restart</button>
</div>
<div id="sessions"></div>
<details id="hidden-wrap" class="hidden-list" hidden>
    <summary>Hidden (<span id="hidden-count">0</span>)</summary>
    <div id="sessions-hidden"></div>
</details>
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
                <div class="hot-editor-actions">
                    <button class="btn green" id="hot-save-btn">Save</button>
                    <button class="btn red" id="hot-clear-btn">Clear</button>
                </div>
                <div class="dim hot-editor-hint">
                    Edit from any pane. The same shared hot buttons appear in every session pane and send their command to that pane's active terminal.
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
<script>{static.JS}</script>
</body>
</html>
"""
