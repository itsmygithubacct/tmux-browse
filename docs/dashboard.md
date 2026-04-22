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
| `idle Xs\|m\|h\|d` | time since last tmux-measured activity |
| **Idle Alert** | button to the right of `idle …`; enables per-session idle notifications with a threshold and sound/prompt mode |
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
watches that session's `idle_seconds` value during the normal refresh loop
and fires once when the session crosses the configured threshold. It rearms
after the session becomes active again. The per-session settings are stored
in `localStorage`. Sound alerts work best after at least one click or keypress
in the page, because browsers often block audio until the page has received a
user gesture.

Footer: `ttyd on port N ↗` is a link to that session's live ttyd URL;
`pid N`; `created X ago`. Clicking the port link opens the terminal in its
own tab.

## New session

Top of the page: a text input and a green **New session** button. Names
cannot contain whitespace, `:`, or `.`.

## Config section

Below **Hidden** there is a furled **Config** pane. It includes both the
server-backed dashboard config file at `~/.tmux-browse/dashboard-config.json`
and an agent editor backed by the agent store under `~/.tmux-browse/`.

It covers:

- Auto-refresh enable/seconds
- Hot-loop idle wait seconds
- Default agent step budget
- Launch-on-expand behavior
- Default ttyd iframe height and min height
- Agent setup: load a built-in preset or existing agent, edit provider/model/
  base URL/wire API, and save or remove the stored definition
- Visibility toggles for summary buttons, expanded-pane buttons, badges,
  footer metadata, inline status messages, and top-bar status text

Use **Save Config** to write the file, **Load From File** to discard unsaved
changes and reload it, and **Defaults** to preview the built-in defaults
before saving them. Agent actions are separate: **Save Agent**, **Reload
Agents**, and **Remove Agent** write `~/.tmux-browse/agents.json` plus the
private `~/.tmux-browse/agent-secrets.json` secret store. The same
dashboard config file can now also be inspected and edited from the CLI via
`tb config show|get|set|reset`.

## Agents section

When one or more agents exist, the dashboard also shows a furled **Agents**
pane. Each configured agent gets:

- a **Log** button that opens the persisted agent action log
- a **Start REPL** / **Open REPL** button that creates or reuses a tmux
  conversation session named `agent-repl-<agent>` and opens its ttyd

Those conversation sessions still appear in the main session grid like any
other tmux session. When a session is in conversation mode, its expanded pane
adds a **Workflows** button and a workflow on/off switch. Workflows are
scheduled prompts saved server-side in `~/.tmux-browse/agent-workflows.json`;
when enabled, the browser sends those prompts into the REPL pane on their
configured intervals.

## Hidden section

A furled `<details>` at the bottom labelled **Hidden (N)**. Entries reorder
within that bucket independently of the main list. If all entries are
hidden, the main area shows "All sessions are hidden — open the list
below." If a hidden session is killed or disappears, it's automatically
dropped from the hidden set.

## Ports & persistence

- Dashboard listens on `DASHBOARD_PORT` (default `8096`).
- Each tmux session is assigned a stable port from `TTYD_PORT_START..END`
  (default `7700..7799`). Assignments persist in
  `~/.tmux-browse/ports.json`; the file is flock-protected.
- PID files for running ttyd processes live under `~/.tmux-browse/pids/`.
- Combined stdout+stderr of each ttyd lives at
  `~/.tmux-browse/logs/<session>.log`.
- Dashboard config lives at `~/.tmux-browse/dashboard-config.json`.
- Agent metadata lives at `~/.tmux-browse/agents.json`.
- Agent API keys live at `~/.tmux-browse/agent-secrets.json`.
- Agent action logs live under `~/.tmux-browse/agent-logs/`.
- Agent workflow schedules live at `~/.tmux-browse/agent-workflows.json`.

A session keeps its port forever, or until you explicitly drop it via
`tmux-browse ports --prune` (for sessions that no longer exist).

## HTTP API

All JSON responses use a stable `{ok, …}` envelope.

| Method | Path | Body / Query | Returns |
|--------|------|--------------|---------|
| GET    | `/`                 | — | HTML dashboard |
| GET    | `/health`           | — | `{ok: true}` |
| GET    | `/api/sessions`     | — | `{ok, sessions: [{name, windows, attached, created, activity, port, pid, ttyd_running}, …]}` |
| GET    | `/api/ports`        | — | `{ok, assignments: {name: port}}` |
| GET    | `/api/dashboard-config` | — | `{ok, path, config}` |
| GET    | `/api/agents`       | — | `{ok, agents, defaults, paths}` |
| GET    | `/api/agent-log`    | `?name=AGENT&limit=N` | `text/plain` formatted agent action log |
| GET    | `/api/agent-workflows` | — | `{ok, path, config}` |
| GET    | `/api/session/log`  | `?session=NAME&lines=N` | `text/plain` scrollback (N ∈ [1, 50 000], default 2 000) |
| GET    | `/raw-ttyd`         | `?name=NAME&port=N&scheme=http|https` | HTML wrapper page for a managed raw ttyd shell |
| POST   | `/api/ttyd/start`   | `{session}` | `{ok, port, pid, already, scheme, url}` |
| POST   | `/api/ttyd/raw`     | `{}` | `{ok, port, pid, name, scheme, url}` — launches a standalone shell ttyd |
| POST   | `/api/ttyd/stop`    | `{session}` | `{ok, pid?, already_stopped?}` |
| POST   | `/api/dashboard-config` | `{config}` | `{ok, path, config}` |
| POST   | `/api/agents`       | `{agent: {name, provider, model, base_url, wire_api, api_key?}}` | `{ok, agent}` |
| POST   | `/api/agents/remove` | `{name}` | `{ok, removed, name}` |
| POST   | `/api/agent-workflows` | `{config}` | `{ok, path, config}` |
| POST   | `/api/agent-conversation` | `{name}` | `{ok, agent, session, port, scheme, already}` |
| POST   | `/api/session/new`  | `{name}` | `{ok, name}` |
| POST   | `/api/session/kill` | `{session}` | `{ok}` — also stops the ttyd |
| POST   | `/api/session/scroll` | `{session}` | `{ok}` — equivalent to `C-b [` |
| POST   | `/api/session/type` | `{session, text}` | `{ok}` — sends `text` to the active pane and presses Enter |

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
