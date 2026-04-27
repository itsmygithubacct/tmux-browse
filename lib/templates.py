"""Top-level dashboard HTML template."""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import static


# Named injection points that extensions can fill. Each slot is marked
# in the template source with ``<!--slot:name-->`` and substituted for
# the extension-supplied HTML at render time. Missing slots render
# empty, so the lean (no-extensions) build produces the historical
# dashboard HTML unchanged.
#
# The full set is declared here rather than being free-form so typos in
# an extension's ui_blocks.html fail loudly at startup instead of
# silently landing nothing on the page.
_SLOTS: tuple[str, ...] = (
    "topbar_extras",
    "config_actions_extras",
    "config_extras",
    "config_agent",
    "agents_section",
    "notifications_section",
    "agent_modals",
    "qr_modal",
)

_SLOT_RE = re.compile(r"<!--slot:([a-z_][a-z0-9_]*)-->")


def _apply_slots(html: str, ui_blocks: dict[str, str] | None) -> str:
    blocks = ui_blocks or {}
    return _SLOT_RE.sub(lambda m: blocks.get(m.group(1), ""), html)


def render_index(ui_blocks: dict[str, str] | None = None,
                 extension_js: list[Path] | None = None) -> str:
    js = static.build_js(extension_js) if extension_js else static.JS
    html = _render(js)
    return _apply_slots(html, ui_blocks)


def _render(js: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>tmux-browse</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#0d1117">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="apple-touch-icon" href="/pwa-192.png">
<style>{static.CSS}</style>
</head>
<body>
<div id="extensions-restart-banner" class="ext-restart-banner" hidden>
    <span id="extensions-restart-msg">Restart the dashboard to activate the extension.</span>
    <button class="btn green" id="extensions-restart-btn" type="button">Restart now</button>
    <button class="btn" id="extensions-restart-dismiss" type="button" title="Hide until next install or enable">Dismiss</button>
</div>
<div class="topbar">
    <h1>tmux sessions <span class="dim" id="count" style="font-size:0.85rem"></span>
        <button class="tmux-help-btn" id="tmux-help-btn" type="button" title="tmux hot keys">?</button>
    </h1>
    <input type="text" id="new-name" placeholder="new session name" />
    <button class="btn green" id="new-btn">New</button>
    <button class="btn" id="launch-claude-btn" title="Launch Claude Code" hidden>Claude</button>
    <button class="btn" id="launch-claude-yolo-btn" title="Launch Claude --dangerously-skip-permissions" hidden>Claude YOLO</button>
    <button class="btn" id="launch-codex-btn" title="Launch Codex" hidden>Codex</button>
    <button class="btn" id="launch-codex-yolo-btn" title="Launch Codex --full-auto" hidden>Codex YOLO</button>
    <button class="btn" id="launch-kimi-btn" title="Launch Kimi Code" hidden>Kimi</button>
    <button class="btn" id="launch-kimi-yolo-btn" title="Launch Kimi Code --yolo" hidden>Kimi YOLO</button>
    <button class="btn" id="launch-monitor-btn" title="Launch lightweight system monitor" hidden>Monitor</button>
    <button class="btn" id="launch-top-btn" title="Launch top/htop/glances" hidden>Top</button>
    <button class="btn blue" id="raw-btn" title="open a standalone ttyd shell not attached to tmux">Raw ttyd</button>
    <button class="btn blue" id="refresh-btn">Refresh</button>
    <span class="dim" id="topbar-status" style="margin-left:auto;font-size:0.8rem">
        auto-refresh off &middot; ttyd spawns on pane expand
    </span>
    <button class="btn red" id="restart-btn" title="restart the dashboard server process">Restart</button>
    <button class="btn red" id="os-restart-btn" title="restart the dashboard server process" style="margin-left:auto" hidden>&#x23FB;</button>
    <!--slot:topbar_extras-->
</div>
<div id="sessions"></div>
<div id="sessions-groups"></div>
<details id="hidden-wrap" class="hidden-list" hidden>
    <summary>Hidden (<span id="hidden-count">0</span>)</summary>
    <div id="sessions-hidden"></div>
</details>
<details id="config-wrap" class="config-pane">
    <summary>Config</summary>
    <div class="config-body">
        <details class="config-lock-section">
            <summary class="dim" style="cursor:pointer;font-size:0.82rem">Lock config pane</summary>
            <div style="display:flex;gap:0.5rem;align-items:center;margin-top:0.4rem;flex-wrap:wrap">
                <input type="password" id="cfg-lock-password" placeholder="Set or change password" style="flex:1;min-width:140px;background:var(--surface);color:var(--fg);border:1px solid var(--border);border-radius:4px;padding:0.3rem 0.5rem;font-size:0.85rem" />
                <button class="btn green" id="cfg-lock-set-btn" type="button">Set Lock</button>
                <button class="btn red" id="cfg-lock-clear-btn" type="button">Remove Lock</button>
                <span class="dim" id="cfg-lock-status" style="font-size:0.82rem"></span>
            </div>
        </details>
        <div class="config-grid">
            <section class="config-card">
                <div class="config-card-title">Behavior</div>
                <label class="check-row">
                    <input type="checkbox" id="cfg-day-mode" />
                    <span>Day mode (light theme)</span>
                </label>
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
                <label class="field">
                    <span>Global daily token budget (0 = unlimited)</span>
                    <input type="number" id="cfg-global-daily-budget" min="0" step="100000" />
                </label>
                <label class="check-row">
                    <input type="checkbox" id="cfg-launch-on-expand" />
                    <span>Launch ttyd when a pane opens</span>
                </label>
                <label class="check-row">
                    <input type="checkbox" id="cfg-furl-side-by-side" />
                    <span>Furl side-by-side panes together</span>
                </label>
                <label class="check-row">
                    <input type="checkbox" id="cfg-resize-row-together" />
                    <span>Resize row of panes together</span>
                </label>
                <label class="check-row">
                    <input type="checkbox" id="cfg-show-agents-pane" />
                    <span>Show Agents pane (off by default)</span>
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
                <div class="pane-groups-editor">
                    <div class="config-card-title" style="font-size:0.82rem;margin-top:0.6rem">Pane Groups</div>
                    <div class="dim" style="font-size:0.75rem;margin-bottom:0.35rem">
                        Named buckets for session panes. Visible and Hidden always exist.
                    </div>
                    <div id="pane-groups-list" style="display:grid;gap:0.25rem"></div>
                    <div style="display:flex;gap:0.4rem;margin-top:0.45rem;flex-wrap:wrap">
                        <input type="text" id="pane-group-new-name" placeholder="New group name" style="flex:1;min-width:120px;background:var(--surface);color:var(--fg);border:1px solid var(--border);border-radius:4px;padding:0.3rem 0.5rem;font-size:0.85rem" />
                        <button class="btn green" id="pane-group-add-btn" type="button">Add</button>
                    </div>
                </div>
            </section>
            <section class="config-card">
                <div class="config-card-title">Title Bar <button class="btn toggle-all-btn" type="button" id="cfg-toggle-all-topbar">All On</button></div>
                <label class="check-row"><input type="checkbox" id="cfg-show-topbar" /><span>Show title bar</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-topbar-title" /><span>Title text</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-topbar-count" /><span>Session count</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-topbar-new-session" /><span>New session field</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-topbar-raw-ttyd" /><span>Raw ttyd button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-topbar-refresh" /><span>Refresh button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-topbar-restart" /><span>Restart button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-topbar-os-restart" /><span>Restart icon (&#x23FB;)</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-launch-claude" /><span>Claude launcher</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-launch-claude-yolo" /><span>Claude YOLO launcher</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-launch-codex" /><span>Codex launcher</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-launch-codex-yolo" /><span>Codex YOLO launcher</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-launch-kimi" /><span>Kimi launcher</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-launch-kimi-yolo" /><span>Kimi YOLO launcher</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-launch-monitor" /><span>System monitor launcher</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-launch-top" /><span>Top/htop/glances launcher</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-launch-ask-name" /><span>Ask for session name on launch</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-launch-open-tab" /><span>Open tab on launch</span></label>
                <label class="field">
                    <span>Launcher working directory</span>
                    <input type="text" id="cfg-launch-cwd" placeholder="e.g. ~/myproject" />
                </label>
                <label class="check-row"><input type="checkbox" id="cfg-show-topbar-status" /><span>Status text</span></label>
            </section>
            <section class="config-card">
                <div class="config-card-title">Summary Row <button class="btn toggle-all-btn" type="button" id="cfg-toggle-all-summary">All On</button></div>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-row" /><span>Show summary row controls</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-name" /><span>Session name</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-arrow" /><span>Expand/collapse arrow</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-attached-badge" /><span>Attached clients badge</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-window-badge" /><span>Window count badge</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-port-badge" /><span>Running ttyd port badge</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-idle-text" /><span>Idle text</span></label>
                <div class="dim" style="font-size:0.72rem;margin:0.3rem 0 0.1rem;text-transform:uppercase;letter-spacing:0.05em;color:var(--accent)">Icon style pane controls</div>
                <label class="check-row"><input type="checkbox" id="cfg-show-wc-close" /><span>Close (x)</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-wc-maximize" /><span>Maximize</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-wc-minimize" /><span>Minimize</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-wc-step-plus-w" /><span>+W (grow iframe width)</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-wc-step-plus-h" /><span>+H (grow iframe height)</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-wc-step-minus-w" /><span>-W (shrink iframe width)</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-wc-step-minus-h" /><span>-H (shrink iframe height)</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-wc-hide-icon" /><span>Hide (incognito)</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-wc-move-icon" /><span>Move-to (folder-arrow)</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-wc-log-icon" /><span>Log (document)</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-wc-scroll-icon" /><span>Scroll (copy-mode)</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-wc-idle-icon" /><span>Idle alert (eye)</span></label>
                <div class="dim" style="font-size:0.72rem;margin:0.3rem 0 0.1rem;text-transform:uppercase;letter-spacing:0.05em;color:var(--accent)">Textual pane controls</div>
                <label class="check-row"><input type="checkbox" id="cfg-show-idle-alert-button" /><span>Idle Alert button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-open" /><span>Open button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-log" /><span>Log button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-scroll" /><span>Scroll button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-split" /><span>Side-by-side button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-hide" /><span>Hide button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-move" /><span>Move-to button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-summary-reorder" /><span>Reorder pad</span></label>
            </section>
            <section class="config-card">
                <div class="config-card-title">Expanded Pane <button class="btn toggle-all-btn" type="button" id="cfg-toggle-all-body">All On</button></div>
                <label class="check-row"><input type="checkbox" id="cfg-show-body-actions" /><span>Show action buttons row</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-body-launch" /><span>Launch button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-body-stop" /><span>Stop ttyd button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-body-kill" /><span>Kill button</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-body-send-bar" /><span>Send bar</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-body-phone-keys" /><span>Phone keyboard addons</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-body-hot-buttons" /><span>Hot Buttons manager</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-hot-loop-toggles" /><span>Hot-button loop toggles</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-footer" /><span>Footer metadata</span></label>
                <label class="check-row"><input type="checkbox" id="cfg-show-inline-messages" /><span>Inline status messages</span></label>
            </section>
        </div>
        <div class="config-actions">
            <button class="btn green" id="cfg-save-btn">Save Config</button>
            <button class="btn blue" id="cfg-load-btn">Load From File</button>
            <button class="btn" id="cfg-reset-btn">Defaults</button>
            <!--slot:config_actions_extras-->
            <button class="btn red" id="cfg-clear-cache-btn" title="Wipe this browser's tmux-browse settings (hidden, order, layout, hot buttons, idle alerts, phone keys) and reload">Clear Local Cache</button>
            <span class="dim" id="cfg-status">Saved to ~/.tmux-browse/dashboard-config.json</span>
        </div>
        <!--slot:config_agent-->
        <!--slot:config_extras-->
        <details id="extensions-wrap" class="config-subsection" open>
            <summary>Extensions</summary>
            <div class="config-body">
                <div class="dim" style="font-size:0.82rem;margin-bottom:0.5rem">
                    Optional modules that add functionality to tmux-browse.
                    Installing an extension pulls it from git; restart the
                    dashboard to activate it.
                </div>
                <div id="extensions-list" style="display:grid;gap:0.5rem"></div>
                <div id="extensions-status" class="dim" style="font-size:0.82rem;margin-top:0.4rem"></div>
            </div>
        </details>
        <details id="pane-admin-wrap" class="config-subsection">
            <summary>Pane Admin</summary>
            <div class="config-body">
                <div id="pane-admin-list"></div>
            </div>
        </details>
        <details id="clients-wrap" class="config-subsection">
            <summary>Connected Endpoints (<span id="clients-count">0</span>)</summary>
            <div class="config-body">
                <div style="display:flex;gap:0.5rem;margin-bottom:0.5rem;align-items:center;flex-wrap:wrap">
                    <input type="text" id="client-nickname" placeholder="Set your nickname" style="flex:1;min-width:120px;background:var(--surface);color:var(--fg);border:1px solid var(--border);border-radius:4px;padding:0.3rem 0.5rem;font-size:0.85rem" />
                    <button class="btn green" id="client-nick-btn" type="button">Set</button>
                    <span class="dim" id="client-you-id" style="font-size:0.78rem"></span>
                </div>
                <div id="clients-pane" class="agent-grid"></div>
            </div>
        </details>
    </div>
</details>
<details id="phone-keys-wrap" class="config-pane" hidden>
    <summary>Phone Keys Config</summary>
    <div class="config-body">
        <div id="phone-keys-preview" class="phone-keys" style="min-height:2rem"></div>
        <div style="display:flex;gap:0.4rem;margin-top:0.5rem;flex-wrap:wrap;align-items:center">
            <input type="text" id="phone-key-label" placeholder="Label (e.g. Tab)" style="width:5rem;background:var(--surface);color:var(--fg);border:1px solid var(--border);border-radius:4px;padding:0.3rem 0.5rem;font-size:0.85rem" />
            <input type="text" id="phone-key-tmux" placeholder="tmux key (e.g. Tab, C-a)" style="width:8rem;background:var(--surface);color:var(--fg);border:1px solid var(--border);border-radius:4px;padding:0.3rem 0.5rem;font-size:0.85rem" />
            <button class="btn green" id="phone-key-add-btn" type="button">Add Key</button>
            <button class="btn" id="phone-key-reset-btn" type="button">Reset to Defaults</button>
        </div>
        <div class="dim" style="margin-top:0.4rem;font-size:0.78rem">Drag buttons to reorder. Click a button to remove it. Changes save automatically.</div>
    </div>
</details>
<!--slot:qr_modal-->
<!--slot:agents_section-->
<!--slot:notifications_section-->
<div id="tmux-help-modal" class="modal-backdrop" hidden>
    <div class="modal-card" role="dialog" aria-modal="true" style="max-width:960px">
        <div class="modal-head">
            <h2>tmux Quick Keys</h2>
            <button class="btn" id="tmux-help-close-btn">Close</button>
        </div>
        <div class="tmux-help-body">
            <p class="dim">Prefix key: <strong>Ctrl+B</strong> — press and release, then press the command key.</p>
            <div class="tmux-help-grid">
                <div class="tmux-help-section">
                    <h3>Sessions</h3>
                    <div class="hk"><kbd>d</kbd> Detach</div>
                    <div class="hk"><kbd>s</kbd> List sessions</div>
                    <div class="hk"><kbd>$</kbd> Rename session</div>
                    <div class="hk"><kbd>(</kbd> <kbd>)</kbd> Prev / next session</div>
                </div>
                <div class="tmux-help-section">
                    <h3>Windows</h3>
                    <div class="hk"><kbd>c</kbd> New window</div>
                    <div class="hk"><kbd>n</kbd> <kbd>p</kbd> Next / prev window</div>
                    <div class="hk"><kbd>0-9</kbd> Select window by number</div>
                    <div class="hk"><kbd>w</kbd> Choose window</div>
                    <div class="hk"><kbd>,</kbd> Rename window</div>
                    <div class="hk"><kbd>&amp;</kbd> Close window</div>
                    <div class="hk"><kbd>l</kbd> Last window</div>
                </div>
                <div class="tmux-help-section">
                    <h3>Panes</h3>
                    <div class="hk"><kbd>"</kbd> Split top/bottom</div>
                    <div class="hk"><kbd>%</kbd> Split left/right</div>
                    <div class="hk"><kbd>Arrow</kbd> Move between panes</div>
                    <div class="hk"><kbd>z</kbd> Zoom (toggle fullscreen)</div>
                    <div class="hk"><kbd>x</kbd> Close pane</div>
                    <div class="hk"><kbd>!</kbd> Break pane to window</div>
                    <div class="hk"><kbd>Space</kbd> Cycle layouts</div>
                    <div class="hk"><kbd>q</kbd> Show pane numbers</div>
                </div>
                <div class="tmux-help-section">
                    <h3>Resize</h3>
                    <div class="hk"><kbd>Ctrl+Arrow</kbd> Resize by 1</div>
                    <div class="hk"><kbd>Alt+Arrow</kbd> Resize by 5</div>
                </div>
                <div class="tmux-help-section">
                    <h3>Copy Mode</h3>
                    <div class="hk"><kbd>[</kbd> Enter copy mode</div>
                    <div class="hk"><kbd>Ctrl+R</kbd> Search backward</div>
                    <div class="hk"><kbd>Ctrl+S</kbd> Search forward</div>
                    <div class="hk"><kbd>n</kbd> <kbd>N</kbd> Next / prev match</div>
                    <div class="hk"><kbd>Space</kbd> Start selection</div>
                    <div class="hk"><kbd>Enter</kbd> Copy and exit</div>
                    <div class="hk"><kbd>q</kbd> Exit copy mode</div>
                    <div class="hk"><kbd>]</kbd> Paste (outside copy mode)</div>
                </div>
                <div class="tmux-help-section">
                    <h3>Misc</h3>
                    <div class="hk"><kbd>:</kbd> Command prompt</div>
                    <div class="hk"><kbd>?</kbd> List all keybindings</div>
                    <div class="hk"><kbd>t</kbd> Clock</div>
                    <div class="hk"><kbd>i</kbd> Pane info</div>
                </div>
            </div>
            <p class="dim" style="margin-top:0.8rem;font-size:0.78rem">
                All keys shown are pressed after the prefix (Ctrl+B).
                See <a href="/docs/tmux-guide.md" target="_blank" style="color:var(--accent)">docs/tmux-guide.md</a> for the full guide.
            </p>
        </div>
    </div>
</div>
<!--slot:agent_modals-->
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
            <div class="field">
                <span>Trigger after idle</span>
                <div class="idle-threshold-row">
                    <label class="idle-threshold-cell">
                        <input type="number" id="idle-threshold-hours" min="0" step="1" value="0" />
                        <span class="dim">hours</span>
                    </label>
                    <label class="idle-threshold-cell">
                        <input type="number" id="idle-threshold-minutes" min="0" max="59" step="1" value="5" />
                        <span class="dim">minutes</span>
                    </label>
                </div>
            </div>
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
<div id="extension-manage-modal" class="modal-backdrop" hidden>
    <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="extension-manage-modal-title">
        <div class="modal-head">
            <div>
                <div class="modal-eyebrow">Extension</div>
                <h2 id="extension-manage-modal-title">Manage</h2>
            </div>
            <button class="btn" id="extension-manage-close" type="button" title="close the manage dialog">Close</button>
        </div>
        <div class="extension-manage-body">
            <dl class="extension-manage-facts">
                <dt>Installed</dt><dd id="extension-manage-version">—</dd>
                <dt>Source</dt><dd id="extension-manage-source">—</dd>
                <dt>Status</dt><dd id="extension-manage-state">—</dd>
            </dl>
            <div class="extension-manage-actions">
                <button class="btn blue" id="extension-manage-update" type="button">Update to pinned ref</button>
                <span class="dim" id="extension-manage-update-hint" style="font-size:0.78rem">Fetches upstream and re-validates the manifest.</span>
            </div>
            <div class="extension-manage-actions">
                <button class="btn" id="extension-manage-toggle" type="button">Disable</button>
                <span class="dim" style="font-size:0.78rem">Keep code; flip off next start.</span>
            </div>
            <div class="extension-manage-actions">
                <label class="check-row" style="align-items:flex-start;gap:0.4rem">
                    <input type="checkbox" id="extension-manage-remove-state" />
                    <span>Also remove this extension's state files under <code>~/.tmux-browse/</code>. <strong>Irreversible.</strong></span>
                </label>
            </div>
            <div class="extension-manage-actions">
                <button class="btn red" id="extension-manage-uninstall" type="button">Uninstall</button>
                <span class="dim" id="extension-manage-uninstall-hint" style="font-size:0.78rem">Removes code. Keeps state unless the box above is ticked.</span>
            </div>
            <div id="extension-manage-status" class="dim" style="font-size:0.82rem;margin-top:0.4rem"></div>
            <div id="extension-manage-error" class="ext-card-error" hidden></div>
        </div>
    </div>
</div>
<script>{js}</script>
<script>
// Register the PWA service worker, but only on HTTPS (or localhost,
// where browsers permit registration without a cert). Plaintext HTTP
// over a LAN silently no-ops, which is what we want — the dashboard
// still works without the SW; install-to-home-screen just isn't
// offered.
if ("serviceWorker" in navigator
    && (location.protocol === "https:" || location.hostname === "localhost"
        || location.hostname === "127.0.0.1")) {{
    navigator.serviceWorker.register("/service-worker.js").catch(() => {{}});
}}
</script>
</body>
</html>
"""


