# Dashboard reference

The dashboard is a single-page app served from `tmux_browse.py serve`.
It lists every local tmux session as a collapsible `<details>` pane and
embeds a [ttyd][ttyd] terminal in each pane on demand.

[ttyd]: https://github.com/tsl0922/ttyd

## Run

```bash
python3 tmux_browse.py serve                   # defaults: 0.0.0.0:8096
python3 tmux_browse.py serve --port 9000
python3 tmux_browse.py serve --bind 127.0.0.1  # local-only (dashboard + ttyd)
python3 tmux_browse.py serve -v                # log every request
python3 tmux_browse.py serve --auth s3cr3t     # require Bearer token
python3 tmux_browse.py serve --auth-file ~/.tb # first non-empty line = token
python3 tmux_browse.py serve --cert cert.pem --key key.pem   # HTTPS
```

Open `http://<host>:8096/` in a browser. The page starts with auto-refresh
disabled by default; use the bottom **Config** pane to enable periodic
refreshes and persist that choice to `~/.tmux-browse/dashboard-config.json`.

## Optional authentication

By default the dashboard is **unauthenticated** — any reachable client can
control every tmux session. Three ways to enable a Bearer-token gate:

```bash
python3 tmux_browse.py serve --auth s3cr3t
python3 tmux_browse.py serve --auth-file ~/.tmux-browse-token
TMUX_BROWSE_TOKEN=s3cr3t python3 tmux_browse.py serve
```

Priority when more than one is present: `--auth` > `--auth-file` >
`$TMUX_BROWSE_TOKEN`.

When enabled, every endpoint except `/health` requires one of:

- `Authorization: Bearer <token>` header (API consumers, including `tb web`)
- Cookie `tb_auth=<token>` (set automatically by the bootstrap step below)
- `GET /?token=<token>` — one-time bootstrap: sets the cookie, then
  302-redirects to `/` so the token doesn't hang around in the URL bar.

Open in a browser like:
```
http://host:8096/?token=s3cr3t
```
After redirect the URL is just `/` and the cookie carries the token for a
week (`HttpOnly; SameSite=Lax; Max-Age=604800`).

**Limitation (read carefully):** this auth token guards the dashboard HTTP
surface only. The per-session ttyd processes it spawns still listen on
their own ports and **are not protected by this token**. Anyone who can
reach those ports still gets shell access. For a real perimeter either
(a) run `serve --bind 127.0.0.1` and tunnel over SSH, or (b) put the whole
stack behind a reverse proxy that does TLS and auth. The token is a
"don't-accidentally-discover-it" layer, not a hardened gate.

`serve --bind` now propagates to spawned ttyds as well:

- `--bind 0.0.0.0` keeps ttyd reachable on all interfaces
- `--bind 127.0.0.1` keeps both dashboard and ttyd local-only
- a concrete host IP such as `--bind 192.168.1.10` is mapped to the owning
  NIC for ttyd's `--interface`

## Optional TLS (HTTPS)

By default the dashboard is **plaintext HTTP**. Opt in to TLS with a PEM
cert + key pair. The same pair is passed to every spawned ttyd so the
embedded terminal iframes work (browsers block `ws://` from an `https://`
origin as mixed content).

```bash
python3 tmux_browse.py serve --cert cert.pem --key key.pem
python3 tmux_browse.py serve --cert /etc/ssl/certs/host.pem \
                             --key  /etc/ssl/private/host.key
TMUX_BROWSE_CERT=cert.pem TMUX_BROWSE_KEY=key.pem python3 tmux_browse.py serve
```

Priority: `--cert/--key` > `$TMUX_BROWSE_CERT` / `$TMUX_BROWSE_KEY`. Both
halves of the pair must resolve together; half-configured TLS exits 8
(`ESTATE`).

**Self-signed for quick LAN use:**

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
    -keyout key.pem -out cert.pem -subj "/CN=localhost"
```

Browsers will show a "certificate not trusted" warning for any self-signed
cert; the exact UX varies (Chrome re-warns each session, Firefox stores an
exception until cleared, Safari differs again). For a cert your browser
actually trusts, use [mkcert][mkcert] (`mkcert -install`, then `mkcert
host.local`) or terminate TLS at a reverse proxy.

[mkcert]: https://github.com/FiloSottile/mkcert

**What TLS covers:**

- Dashboard HTTP (`:8096`) → HTTPS.
- Every ttyd port (`7700–7799`) inherits `--ssl --ssl-cert --ssl-key`.
- `tb web url` / `tb web start` return `https://…` URLs automatically,
  via a `.scheme` sidecar that `lib/ttyd.py` writes alongside the pidfile.

**What TLS does not cover:**

- Cert renewal — BYO. No auto-generation, no ACME client.
- Mutual TLS — there's no client-cert requirement; anyone who trusts the
  cert can still connect.
- Hardened defaults — no HSTS header is emitted and cipher selection uses
  Python's `ssl` defaults. If you care, front the dashboard with
  nginx/Caddy and terminate TLS there.

**Performance note.** Python's `http.server` defaults to HTTP/1.0, which
means each dashboard request is a fresh TCP + TLS handshake. ttyd's
terminal iframe is a single long-lived WebSocket, so the handshake cost
is only at connect time, not per keystroke. The 5 s auto-refresh is the
loop that pays TLS cost most visibly. On low-power ARM hardware (Pi,
Orange Pi) it's perceptible; on a desktop or server it isn't worth
worrying about. If you only need a perimeter on a trusted LAN, plain
HTTP + Bearer auth is cheaper and equally private to outsiders.

You can mix TLS and Bearer auth freely; they're orthogonal.

## UI — session pane summary

Each session is still a `<details>` pane, but the main area can now group
multiple panes into the same row for side-by-side viewing. The collapsed
**summary row** shows:

| Element | Meaning |
|---|---|
| session name | bold, accent-colour |
| `N clients` badge | number of attached tmux clients (green if ≥ 1) |
| `Nw` badge | window count |
| `:PORT` badge | only shown while ttyd is running; its listening port |
| `idle Xs\|m\|h\|d` | time since the session's log content last changed (SHA-256 of the trailing 8 KiB of `~/.tmux-browse/session-logs/<name>.log`, written via `tmux pipe-pane`). Falls back to tmux's `session_activity` for pre-existing sessions before the log is first created. |
| **Idle Alert** | button to the right of `idle …`; enables per-session idle notifications. Threshold is configured in the modal as hours + minutes (minimum 1 minute) with sound and/or prompt delivery. |
| **Open ↗** | green button; opens the live ttyd in a new browser tab. Only visible while ttyd is running. |
| **Log** | serves `tmux capture-pane` output for that session as `text/plain` in a new tab — the scrollback up to `history-limit`. |
| **Scroll** | orange button; invokes `tmux copy-mode` on the session's active pane (equivalent to `C-b [`). Useful when viewing through ttyd. |
| **▥** split button | blue button; click it to open a chooser of visible sessions, then place the current session on the right of the selected target. The same button is draggable: drag onto the left/right side of another pane to snap there, or drop near the middle to insert above it as its own row. Persisted in `localStorage`. |
| **Hide** | red button; moves the pane into a furled **Hidden (N)** section at the bottom of the page. The button flips to **Unhide** there. Persisted in `localStorage`. |
| **[▲▼]** reorder pad | clickable arrows move the pane up/down the main stack. Hidden sessions still use the stored flat order. Persisted in `localStorage`. |

## UI — expanded pane body

Expanding a pane for the first time auto-spawns `ttyd` for that session by
default and embeds the terminal in a resizable iframe. That launch-on-expand
behavior is configurable in the bottom **Config** pane. Drag the bottom-right
corner of the iframe to resize; the wrapper uses `resize: vertical` because
iframes swallow pointer events during a drag.

Body controls:

| Button | Action |
|---|---|
| **Launch** (green) | ensure ttyd is running for this session (idempotent) |
| **Stop ttyd** (orange) | stop the session's ttyd; the tmux session itself is untouched |
| **Kill** (red) | kill the tmux session (and its ttyd) |
| **Send bar** | text input + Send button below the iframe — sends text to the pane and presses Enter. Hidden by default; enable in Config. |
| **Phone keyboard addons** | floating row of touch-friendly buttons: arrow keys, Esc, C-c, C-b, Shift, PgUp, PgDn. Hidden by default; enable in Config. Sends via `POST /api/session/key`. |
| **Hot Buttons** (blue) | opens a wide in-page editor for up to 32 shared hot-button slots |

When a hot-button slot has a saved name + command, it appears to the right of
the **Hot Buttons** button in every expanded session pane. Clicking one sends
that slot's command to that pane's active terminal as a full line plus
`Enter`. The slots are global to the page and stored in `localStorage` per
browser.

Each visible hot button also gets a small orange loop toggle on its right.
The label shows either `∞` (run until stopped) or `Nx` for a configured loop
count. When toggled on, the button stays visually pressed and the dashboard
watches that session for idleness. Once the session has been idle for the
configured hot-loop wait time, it sends that hot button's command, then waits
for activity before arming the loop again. Click the loop toggle again to
stop it.

The top bar also includes a blue **Raw ttyd** button, a blue **Refresh**
button, and a red **Restart** button. **Raw ttyd** opens a standalone ttyd
shell not attached to tmux in a small wrapper page with:

- the embedded raw ttyd shell itself
- an **Open Direct** button to jump to the ttyd port URL
- a **Stop** button that terminates that raw shell

Closing that wrapper page also sends a best-effort stop request for the raw
shell, so Raw ttyd sessions are manageable from the UI instead of becoming
fire-and-forget background shells. **Restart** re-execs the dashboard server
process itself.

Idle alerts are browser-side. When enabled for a session, the dashboard
watches that session's `idle_seconds` value and fires once when the session
crosses the configured threshold. The threshold is expressed as hours +
minutes (minimum 1 minute). Polling cadence:

- If **auto-refresh** is on, the full `/api/sessions` refresh handles idle
  detection on its normal interval.
- Otherwise, a dedicated 60-second `pollIdleOnly()` loop still fetches
  `/api/sessions` to keep idle labels and alert firing current without
  rebuilding panes. Hidden sessions are skipped — if you hid it, you don't
  want to hear about it.

The alert rearms after the session becomes active again. The per-session
settings are stored in `localStorage`. Sound alerts work best after at least
one click or keypress
in the page, because browsers often block audio until the page has received a
user gesture.

Footer: `ttyd on port N ↗` is a link to that session's live ttyd URL;
`pid N`; `created X ago`. Clicking the port link opens the terminal in its
own tab.

## New session

Top of the page: a text input and a green **New session** button. Names
cannot contain whitespace, `:`, or `.`.

## Config section

Below **Hidden** there is a furled **Config** pane backed by
`~/.tmux-browse/dashboard-config.json`. It covers:

- **Behavior:** day/night mode, auto-refresh enable/seconds, hot-loop
  idle wait, launch-on-expand, furl side-by-side panes together, resize
  row of panes together, default ttyd height/min-height, idle alert
  sound.
- **Title Bar** (with All On/All Off): master toggle for the whole bar,
  plus individual toggles for title text, session count, new session
  field, Raw ttyd button, Refresh button, Restart button, status text.
- **Summary Row** (with All On/All Off): master toggle for all summary
  controls, plus session name, expand/collapse arrow, badges (attached,
  windows, port), idle text, idle alert button, Open/Log/Scroll/Split/
  Hide buttons, reorder pad.
- **Expanded Pane** (with All On/All Off): master toggle for the action
  buttons row, plus Launch, Stop ttyd, Kill, send bar, phone keyboard
  addons, Hot Buttons manager, hot-button loop toggles, footer, inline
  messages.
- **Phone Keys** (furled subsection): live draggable preview of the
  current mobile key layout. Add custom keys via label + tmux key name
  (e.g. `Tab`, `C-a`, `F5`). Click to remove, drag to reorder, reset
  to defaults. Stored in localStorage.
- **Lock config pane:** optional password that gates both the Config
  pane UI *and* every server-side mutation endpoint
  (`/api/dashboard-config`, `/api/tasks`, `/api/extensions/*`, and any
  mutation endpoint contributed by an enabled extension).
  `/api/config-lock/verify` issues a 32-byte unlock token with a
  12-hour TTL; the browser sends it as `X-TB-Unlock-Token` on every
  non-GET request. Password stored as SHA-256 hash at
  `~/.tmux-browse/config-lock-secret` (0600). Tokens live in server
  memory only — a restart forces re-unlock.
- **Pane Groups:** named buckets for sessions. Visible and Hidden
  always exist; create additional groups (e.g. Agents, Monitoring)
  with the editor in Config > Behavior. Each group renders as its
  own furled `<details>` block between the Visible stack and the
  Hidden drawer. A session lives in exactly one bucket at a time.
- **Extensions:** one card per known extension with a **Download and
  enable** button. Installation pulls the extension from git (using
  `git submodule update --init` if the path is already registered in
  `.gitmodules`, otherwise a shallow `git clone` at the catalog's
  pinned ref) and validates the manifest before flipping the
  enabled bit in `~/.tmux-browse/extensions.json`. A restart banner
  appears at the top of the page until you click **Restart now**;
  the loader activates the extension on restart. Install is
  config-lock gated. Once installed, each row grows a **Manage…**
  button that opens a modal exposing **Update to pinned ref**,
  **Disable** (or **Enable**), and **Uninstall**. State files under
  `~/.tmux-browse/` are kept by default — flip the *Also remove*
  checkbox before Uninstall to delete them. Headless hosts can drive
  the same actions from the repo root via the
  `make {install,update,enable,disable,uninstall}-<extension>` targets.

Action buttons: **Save Config**, **Load From File**, **Defaults**.

Extensions can extend this pane with their own subsections — e.g. the
agent extension adds an **Agent** editor and **Save / Reload / Remove
Agent** actions, and the QR extension adds **Show QR** / **Read QR**
buttons. See each extension's README for the controls it contributes.

## Agent / Runs / Tasks sections (extension)

When the
[tmux-browse-agent](https://github.com/itsmygithubacct/tmux-browse-agent)
extension is installed, the dashboard adds three furled sections —
**Agents**, **Runs**, and **Tasks** — for managing LLM agents, browsing
their run history, and launching task-scoped REPLs. Without that
extension installed, none of these sections render and core stays
purely a tmux dashboard. See the extension's README for the full
control layout.

## Connected Endpoints section

Shows all browser clients currently connected to the dashboard (seen
within the last 60 seconds). Each entry shows IP address, optional
nickname, idle time, and connection age. Features:

- **Set nickname** so other devices see a friendly name
- **Share Config** button pushes your full view config (layout, hidden
  panes, hot buttons, phone keys, theme, idle alerts) to another
  connected client. The recipient gets a `confirm()` prompt.
- Client list refreshes every 15 seconds; config inbox polled every
  10 seconds.

## Hidden section

A furled `<details>` at the bottom labelled **Hidden (N)**. Entries reorder
within that bucket independently of the main list. If all entries are
hidden, the main area shows "All sessions are hidden — open the list
below." If a hidden session is killed or disappears, it's automatically
dropped from the hidden set.

Hidden is one of two built-in pseudo-groups — the other is Visible.
Any additional user-defined groups created in Config > Behavior render
between Visible and Hidden as their own furled `<details>` blocks. The
**Move** button on each pane (text + folder-arrow icon) opens a popover
listing all buckets and a "+ New group…" entry, writing through the
same per-browser localStorage that backs Hidden/Visible.

## Ports & persistence

- Dashboard listens on `DASHBOARD_PORT` (default `8096`).
- Each tmux session is assigned a stable port from `TTYD_PORT_START..END`
  (default `7700..7799`). Assignments persist in
  `~/.tmux-browse/ports.json`; the file is flock-protected.
- PID files for running ttyd processes live under `~/.tmux-browse/pids/`.
- Combined stdout+stderr of each ttyd lives at
  `~/.tmux-browse/logs/<session>.log`.
- Dashboard config lives at `~/.tmux-browse/dashboard-config.json`.
- Task definitions live at `~/.tmux-browse/tasks.json`.
- Per-session pipe-pane logs live under `~/.tmux-browse/session-logs/`.

Extensions write their own state under `~/.tmux-browse/`. The agent
extension, for example, adds files like `agents.json`,
`agent-secrets.json`, `agent-run-index.jsonl`, and an `agent-logs/`
directory; see its README for the full list. Uninstalling an extension
keeps its state files unless you opt in to *Also remove*.

A session keeps its port forever, or until you explicitly drop it via
`tmux-browse ports --prune` (for sessions that no longer exist).

## HTTP API

All JSON responses use a stable `{ok, …}` envelope.

### Core endpoints (always present)

| Method | Path | Body / Query | Returns |
|--------|------|--------------|---------|
| GET    | `/`                 | — | HTML dashboard |
| GET    | `/health`           | — | `{ok: true}` |
| GET    | `/api/sessions`     | — | `{ok, sessions: [{name, windows, attached, created, activity, port, pid, ttyd_running, conversation_mode?, agent_name?}, …]}` (last two only when the agent extension is enabled) |
| GET    | `/api/ports`        | — | `{ok, assignments: {name: port}}` |
| GET    | `/api/dashboard-config` | — | `{ok, path, config}` |
| GET    | `/api/tasks`        | — | `{ok, tasks}` — task list (excludes archived) |
| GET    | `/api/clients`      | — | `{ok, clients, you}` — connected browser endpoints |
| GET    | `/api/clients/inbox` | — | `{ok, messages}` — pending config shares for this client |
| GET    | `/api/config-lock`  | — | `{ok, locked}` — whether config pane is password-locked |
| GET    | `/api/session/log`  | `?session=NAME&lines=N` | `text/plain` scrollback (N ∈ [1, 50 000], default 2 000) |
| GET    | `/api/extensions`   | — | `{ok, extensions: [{name, label, description, repo, installed, enabled, version, submodule, restart_pending, last_error}, …]}` |
| GET    | `/api/extensions/available` | — | `{ok, available}` — full catalog |
| POST   | `/api/ttyd/start`   | `{session}` | `{ok, port, pid, already, scheme, url}` |
| POST   | `/api/ttyd/raw`     | `{}` | `{ok, port, pid, name, scheme, url}` — launches a standalone shell ttyd |
| POST   | `/api/ttyd/stop`    | `{session}` | `{ok, pid?, already_stopped?}` |
| POST   | `/api/dashboard-config` | `{config}` | `{ok, path, config}` |
| POST   | `/api/tasks`        | `{title, repo_path, agent?, worktree_path?, branch?}` | `{ok, task}` |
| POST   | `/api/tasks/update`  | `{id, status?, agent?, ...}` | `{ok, task}` |
| POST   | `/api/tasks/launch`  | `{id}` | `{ok, task_id, session, port}` — 409 if the agent extension isn't enabled |
| POST   | `/api/session/new`  | `{name}` | `{ok, name}` |
| POST   | `/api/session/kill` | `{session}` | `{ok}` — also stops the ttyd |
| POST   | `/api/session/scroll` | `{session}` | `{ok}` — equivalent to `C-b [` |
| POST   | `/api/session/zoom` | `{session}` | `{ok}` — equivalent to `C-b z` |
| POST   | `/api/session/resize` | `{session, width, height}` | `{ok}` |
| POST   | `/api/session/type` | `{session, text}` | `{ok}` — sends `text` to the active pane and presses Enter |
| POST   | `/api/session/key`  | `{session, keys: [...]}` | `{ok}` — sends tmux key names (e.g. `Up`, `C-c`, `Escape`) |
| POST   | `/api/clients/nickname` | `{nickname}` | `{ok, client_id, nickname}` |
| POST   | `/api/extensions/install`   | `{name}` | `{ok, name, version, via, restart_required, message}` (config-lock gated) |
| POST   | `/api/extensions/enable`    | `{name}` | `{ok, name, entry, restart_required}` |
| POST   | `/api/extensions/disable`   | `{name}` | `{ok, name, entry, restart_required}` |
| POST   | `/api/extensions/update`    | `{name}` | `{ok, name, from_version, to_version, changed, via, restart_required, message}` |
| POST   | `/api/extensions/uninstall` | `{name, remove_state?}` | `{ok, name, restart_required, summary, message}` |
| POST   | `/api/clients/send-config`  | `{target, config_url}` | `{ok, sent}` — push config to another client |
| POST   | `/api/config-lock`  | `{password}` | `{ok, locked}` — set or clear (empty password = clear) |
| POST   | `/api/config-lock/verify` | `{password}` | `{ok, unlocked, unlock_token, ttl_seconds}` or 403 |
| POST   | `/api/server/restart` | `{}` | `{ok, restarting}` — re-exec the server process |

### Extension endpoints

Enabled extensions contribute their own routes through the loader; all
POSTs from extensions go through the same config-lock gate as core.

- **Agent** (`/api/agent-*` and `/api/agents*`) —
  [tmux-browse-agent](https://github.com/itsmygithubacct/tmux-browse-agent)
- **QR** (`GET /api/qr?data=TEXT` → SVG) —
  [tmux-browse-qr](https://github.com/itsmygithubacct/tmux-browse-qr)

Each extension's README documents its full route table.

## CLI companion

The same `tmux_browse.py` also exposes dashboard-focused CLI subcommands
(start/stop the server, inspect port assignments, launch or stop individual
ttyds):

```
tmux-browse serve [--port N] [--bind ADDR] [-v]
tmux-browse list                     # sessions + ttyd state, table form
tmux-browse status                   # human-readable summary
tmux-browse ports [--prune]
tmux-browse start <session> [--bind ADDR]   # ensure ttyd for <session>
tmux-browse stop  <session>
tmux-browse cleanup                  # stop every managed ttyd
tmux-browse install-ttyd [--force]
tmux-browse config [--json] [--reset] [--set KEY=VALUE ...]
```

For the richer, session-management-focused CLI, see [docs/tb.md](tb.md).

## Multiple hosts

The dashboard talks only to the local tmux server. To browse multiple
machines, run a copy of `tmux_browse.py serve` on each one — they're
independent, each has its own `~/.tmux-browse/ports.json`, and the browser
can bookmark each dashboard separately.
