# Architecture

Why the project is shaped the way it is. Everything here is a deliberate
choice driven by the scope: "a single-host tmux toolkit that stays out of
the way."

## Principles

1. **Stdlib-only Python**, no pip dependencies. The whole thing is `http.server`,
   `urllib`, `subprocess`, `json`. That means: no virtualenv dance required
   to try it, no supply-chain surprises, and the project runs on whatever
   Python a freshly imaged Linux box ships with.
2. **Two CLIs, one library.** `tmux_browse.py` (dashboard) and `tb.py`
   (general CLI) share everything under `lib/`. A bug fixed in
   `lib/sessions.py` improves both surfaces at once.
3. **Stable contracts.** Exit codes, error `code` strings, and JSON
   envelopes don't change between patch versions. Human messages can.
4. **Boring defaults.** Sensible port numbers, 0.0.0.0 bind, no
   authentication — trusted-network assumptions, documented loudly in
   `docs/dashboard.md`.

## Module map

```
lib/config.py         ports + paths (one place to tune)
lib/ports.py          JSON+flock registry: session name → stable port
lib/sessions.py       everything tmux-related (enumerate, capture, send)
lib/ttyd.py           spawn/stop/track per-session ttyd, PID files, port probes
lib/ttyd_installer.py fetch the ttyd static binary from GitHub releases
lib/server.py         http.server handler + JSON API
lib/templates.py      dashboard HTML
lib/static.py         dashboard CSS + JS (embedded as Python strings)
lib/targeting.py      Target dataclass + parser for session[:window[.pane]]
lib/errors.py         typed exceptions → stable exit codes
lib/output.py         table/JSON emitters with TTY-aware colour
lib/exec_runner.py    `tb exec` sentinel + idle strategies
lib/tls.py            optional TLS: cert/key resolve, SSLContext builder
lib/tb_cmds/          one module per tb verb group (read/write/lifecycle/…)
```

Entry points:

- `tmux_browse.py` — dashboard CLI (serve, list, ports, start/stop ttyd, …)
- `tb.py` — general CLI, thin dispatch over `lib/tb_cmds/`

## Why `http.server` instead of a framework

The dashboard's route set is ~10 endpoints. Adding Flask would require
users to set up a venv or install packages. `http.server` with a
`BaseHTTPRequestHandler` is ~200 lines of code and handles this fine. The
one trade-off is that we don't get the free middleware ecosystem; the only
thing we'd actually want (auth) is deliberately not provided anyway
(trusted-network model).

`ThreadingHTTPServer` + `daemon_threads=True` is enough for the tens of
concurrent requests the dashboard ever sees.

## Why the port registry

Users want **bookmarkable URLs**. If ttyd's port for "session X" changed
every time the dashboard restarted, bookmarks and iframe URLs would rot.
So:

- `lib/ports.py` persists `{session_name: port}` to JSON
- A session keeps its port forever (unless explicitly pruned)
- Allocations scan from `next_port` and wrap; never collide
- The file is `fcntl.flock`-protected so dashboard threads + CLI
  invocations don't race

Pruning is opt-in (`tmux-browse ports --prune`) — never automatic — because
the cost of a lost bookmark outweighs the cost of a few unused entries.

## Why `bin/ttyd_wrap.sh` exists

We don't just launch `ttyd bash` directly. We launch
`ttyd -W bash bin/ttyd_wrap.sh <session>`. The wrapper:

1. **Attaches to the named tmux session** — enabling multi-client terminal
   sharing (dashboard iframe + local `tmux attach` see the same state).
2. **Never creates sessions implicitly** — session creation is an explicit
   user action, keeping the tool predictable.
3. **Exits as soon as its tty disappears** via a `tty_alive` guard
   (`[ -t 0 ] && [ -t 1 ]`). Without that, every WebSocket reconnect
   leaks a wrapper process that lingers as a stale tmux client,
   eventually exhausting the tmux server's fd budget. This is a real
   failure mode observed in production; the `tty_alive` guard is the fix.

## Why the sentinel-based `exec`

Reading a command's output from tmux without modifying the user's shell
environment is harder than it looks. Two options:

- **Idle heuristic** — silence = done. Works anywhere, but can't see
  backgrounded output or get the exit status. `exit_status` is `null`.
- **Sentinel wrapping** — append
  `; printf '\n__TB_<tag>_END_%d__\n' $?` to the user's command, then
  poll `capture-pane` until the END marker shows up. Reliable;
  returns real exit status; trim is trivial (delete after the marker).

We prefer sentinel when the pane's `pane_current_command` is a shell
(`bash`/`zsh`/`fish`/`sh`), fall back to idle otherwise. `--strategy` lets
you force either.

The sentinel tag is 6 bytes of `secrets.token_hex`, so no risk of
colliding with whatever the user happens to be running.

## Why `lib/tb_cmds/` splits per verb group

`tb` has 19 verbs. A single 1500-line CLI file gets ugly. Splitting by
concern (read / write / lifecycle / observe / web / bulk) means:

- Each module is 100–200 lines, easy to skim.
- Adding a new verb = editing one file.
- Shared dispatch: every module exports `register(sub, common)`; the
  entry `tb.py` just loops over them via `register_all`.

The `common` argparse parent parser is the key to `--json`, `--quiet`,
`--no-header` working both before and after the verb.

## Why no shell completions (yet)

Not needed for LLM use; humans can get it quickly from `--help`. We can
add them later with `tb completion {bash,zsh,fish}` — the verb set is
already machine-readable from argparse introspection.

## Optional dashboard auth

`lib/auth.py` provides opt-in Bearer-token auth with stable exit-code
`EAUTH` (9). It's a thin gate — resolves `--auth` / `--auth-file` /
`$TMUX_BROWSE_TOKEN` in that priority, taking the first non-empty line from
the auth file, then checks `Authorization` / cookie / `?token=` query per
request with a constant-time compare. `/health` is deliberately exempt so
monitoring still works. The ttyd ports it spawns aren't covered by the same
token — documented in `docs/dashboard.md` because it's the obvious gotcha.

## Optional TLS

`lib/tls.py` resolves a `(cert, key)` pair from `--cert`/`--key` or
`$TMUX_BROWSE_CERT` / `$TMUX_BROWSE_KEY`, validates readability, and
returns an `ssl.SSLContext` (`PROTOCOL_TLS_SERVER`) that `lib/server.py`
uses to wrap the listening socket. Half-configured TLS is a hard error
(`ESTATE` / exit 8), not a silent fallback — more visible than guessing.

**Why the cert also goes to ttyd.** Browsers block `ws://` iframes
loaded from an `https://` origin as mixed content. So when the dashboard
serves HTTPS, every spawned ttyd must too. `lib/ttyd.py::start` accepts
the same `(cert, key)` paths and appends `--ssl --ssl-cert --ssl-key` to
the ttyd argv. It also writes a `<session>.scheme` sidecar in `PID_DIR`
so `tb web url` (a separate CLI process) knows which scheme to emit.
The sidecar is deleted alongside the pidfile on `stop()`.

BYO cert only — no auto-generation. A self-signed `openssl req` recipe
is documented in the README; a hardened stack belongs behind a reverse
proxy, not inside this tool.

Why stdlib-only still works here: Python's `ssl` is stdlib; `ttyd --ssl`
ships with ttyd. Nothing new to install.

## Frontend: one HTML file, no build step

`lib/templates.py` and `lib/static.py` embed the full HTML/CSS/JS as Python
strings. The server renders `index.html` once per request with the static
assets inline — no separate static-file serving, no build tooling, no bundler.
The JS is ~300 lines of vanilla, no dependencies.

The whole page is re-hydrated every 5 s by calling `/api/sessions` and
diffing DOM panes against the new data (`state.nodes` map). This avoids
reloading the `<iframe>`s, which would tear down active ttyd connections.
Age fields (`idle_seconds`, `created_seconds_ago`) are computed server-side
so clock skew between browser and server doesn't report "idle 0s" for
every session after a laptop wake.

Reordering and hiding state live in `localStorage` (`tmux-browse:order`
and `tmux-browse:hidden`), per-browser per-origin. Intentionally not
server-side: ordering preferences are a viewer concern, not a machine
concern, so two people hitting the same dashboard from different browsers
can arrange their views differently.

## Failure modes we actively guard against

| Hazard | Mitigation |
|---|---|
| Stale ttyd wrappers pile up as tmux clients | `tty_alive` guard in `bin/ttyd_wrap.sh` |
| Port collision on restart | `lib/ports.py` probes + refuses to stomp a listening port |
| Dashboard PID file left behind after crash | PID files are re-validated (`os.kill(pid, 0)`) before use |
| Concurrent port allocations race | `fcntl.flock` on `ports.json` |
| tmux prefix-matching ambiguity | Most tmux commands use `=name` for exact match; `capture-pane` uses `name:` |
| Iframe reload on every 5 s refresh | DOM diff instead of full re-render |
| Keyboard events swallowed while dragging iframe | `.ttyd-resize-wrap` wrapper owns the resize handle |
| Sentinel collision with user output | 48-bit random tag per `exec` call |
| `paste` mangled by terminal quirks | `load-buffer` + `paste-buffer -d` instead of `send-keys -l` |

## Extending

To add a new tb verb:

1. Pick a module in `lib/tb_cmds/` (or add a new one if it's a new group).
2. Write the `cmd_foo(args)` function. Raise a `TBError` subclass on
   failure; return `0` on success.
3. Add the subparser in the module's `register(sub, common)`, pass
   `parents=[common]` so global flags inherit. Wire
   `p.set_defaults(func=cmd_foo)`.
4. If it's a new module, call it from `lib/tb_cmds/__init__.py::register_all`.

To add a new HTTP route:

1. Extend the handler in `lib/server.py`'s `do_GET` / `do_POST`.
2. Delegate to a helper in `lib/sessions.py` or `lib/ttyd.py` rather than
   shelling out inline.
3. Return via `_send_json` / `_send_text` / `_send_html` so the
   Content-Type and envelope stay consistent.

To change dashboard behaviour:

- CSS → `lib/static.py::CSS`
- JS → `lib/static.py::JS`
- HTML skeleton → `lib/templates.py`

No build step; restart the server to see changes.
