# Changelog

## 0.4.0 — Hardening + modularity pass

### Features

- **Dashboard config pane + file-backed settings.** New furled **Config**
  section below **Hidden** with save/load controls backed by
  `~/.tmux-browse/dashboard-config.json`. Covers refresh cadence, default
  ttyd height, hot-loop idle wait, and broad button/metadata visibility
  toggles.
- **CLI access to dashboard config.** New `tmux-browse config` subcommand
  can print, reset, and update the same dashboard config file without using
  the web UI.
- **`tb agent` orchestration.** Added secure agent storage plus `tb agent`
  defaults/add/list/remove/run. Built-in aliases cover `sonnet`, `opus`,
  `gpt`, `kimi`, and `minimax`; runtime operates through `tb.py` commands
  instead of a separate shell integration.
- **External agent catalog.** Built-in defaults can now be overridden via
  `~/.tmux-browse/agent-catalog.json` — bump a model version without
  editing source.
- **Dashboard side-by-side layout.** Visible sessions can now be grouped
  into the same row. A new blue `▥` summary button opens a chooser that
  places the current session to the right of another visible session.
- **Drag-to-snap split placement.** Drag the `▥` button onto another
  session to snap left or right, or drop near the middle to insert the
  dragged session above the target as its own row.
- **Layout persistence.** Visible row/group layout is stored in
  `localStorage` so side-by-side arrangements survive refreshes.
- **Raw ttyd launcher.** New top-bar **Raw ttyd** button opens a standalone
  ttyd shell not attached to tmux.
- **Hot-button loop counters.** Each hot button now has an optional loop
  count; `0` means infinite, positive values stop after that many loop
  sends.
- **LAN multi-device access documented.** README now covers how phone / PC
  / laptop attach to the same sessions simultaneously, with guidance for
  TLS + token gates before exposing beyond a trusted LAN.

### Correctness & security

- **Graceful SIGTERM.** The dashboard now unblocks `serve_forever()` on
  `SIGTERM` in addition to `SIGINT`, so `systemctl stop` / container
  orchestration shut it down cleanly.
- **Per-session spawn lock.** Concurrent `POST /api/ttyd/start` for the
  same session no longer races — only one actually spawns ttyd, the
  others see the existing PID.
- **Atomic PID / scheme file writes.** Readers no longer see half-written
  pidfiles during a spawn.
- **Startup GC of orphan state.** When the dashboard boots it removes
  pidfiles for dead ttyds and drops port assignments for tmux sessions
  that no longer exist.
- **TLS 1.2 minimum.** Pinned explicitly instead of inheriting the
  Python-build default.
- **Bind-aware ttyd interface resolution.** When the dashboard binds to a
  concrete LAN address, the spawned ttyds inherit the matching interface
  via `--interface`, with a BSD/macOS `ifconfig` fallback and a
  per-process cache so repeated spawns don't re-exec `ip addr show`.
- **Collision-resistant raw-shell names.** Two clicks within the same
  millisecond now always get distinct names.

### Internal refactor / code quality

- **Typed `DashboardServer` subclass** replaces dynamic attribute
  attachment on `ThreadingHTTPServer` — no more `# type: ignore` on
  server setup.
- **Dispatch-dict routes.** `Handler.do_GET` / `do_POST` now look up
  named `_h_*` methods in `MappingProxyType` route tables; adding a
  route is one method + one dict entry. Subclass mutation is blocked.
- **Split `_auth_gate`** — auth check and token-stripping redirect are
  now separate methods.
- **Provider abstraction.** Agent wire-API adapters live in their own
  `agent_providers.py` with a `PROVIDERS` registry; adding a new wire
  protocol is a single function + registry entry.
- **Extracted dashboard assets.** `lib/static.py` dropped from 67 KB to
  1.2 KB; CSS and JS now live in `static/app.css` / `static/app.js`
  where editors syntax-highlight them.
- **Unit test skeleton.** Stdlib-only `python3 -m unittest discover -s
  tests` covers targeting, output formatting, port registry (incl.
  corrupt-registry recovery), atomic PID writes, filename round-trips,
  and interface-cache/ifconfig parsing — 36 tests.
- **`tb_cmds/_common.py`** hosts `parse_target` / `require_target` so
  the package `__init__` can import submodules at the top cleanly.
- **`poll_until` helper** dedupes the sentinel + idle polling loops in
  `exec_runner`.
- **Single-source version.** `__version__` lives in `lib/__init__.py`;
  `tb.py` and the HTTP `Server:` header both read it from there.

## 0.3.0 — TLS

- **New feature — optional HTTPS for the dashboard.** Enable with
  `--cert PATH --key PATH`, or `$TMUX_BROWSE_CERT` / `$TMUX_BROWSE_KEY`.
  The same cert/key are passed to every spawned ttyd via
  `--ssl --ssl-cert --ssl-key`, so the embedded terminal iframes work
  without tripping the browser's mixed-content rule. Half-configured TLS
  (only cert, only key) exits 8 (`ESTATE`). BYO cert only — stdlib-only
  principle preserved.
- **`tb web url` / `tb web start`** now emit `https://…` when the
  running ttyd was spawned with TLS. State is tracked via a
  `<session>.scheme` sidecar next to the pidfile.
- **`tmux-browse start`** accepts `--cert`/`--key` too (plus env), for
  launching a single TLS ttyd without the dashboard.

## 0.2.0 — Review pass

- **`tb ls` / `tb exists` / `tb snapshot` now work with zero tmux sessions**
  (previously exited `ENOSERVER`).
- **`tb exec`**: on timeout, now interrupts the pane with `C-c` by default;
  opt out with `--no-interrupt`. New `--clear` flag resets any half-typed
  readline buffer before sending the wrapper. `--json` payload no longer
  wraps with a redundant inner `ok`; includes `strategy` and, in plain
  mode, prints a status footer showing which strategy ran.
- **`tb exists --json`** now always exits 0 with `{exists: bool}`; plain
  mode unchanged (silent; 0/3).
- **`tb tail --json`** emits `{target, lines, content}` envelope on non-follow.
- **`tb paste`** now errors out on TTY stdin instead of hanging forever.
- **`tb ls`**: new `--running-within SEC` overrides the 30 s threshold.
- **Port registry** is now resilient to corrupt/unwritable `ports.json`
  (new exit `ESTATE` / 8; recovers a corrupt file with a backup).
- **PID-reuse defence** in ttyd tracker: verifies `/proc/<pid>/comm == ttyd`.
- **Filename safety** for session names with `/` etc — reversible
  percent-encoding instead of lossy `_` replacement.
- **New feature — optional dashboard auth** (default: off). Enable with
  `--auth TOKEN`, `--auth-file PATH`, or `$TMUX_BROWSE_TOKEN`. Supports
  `Authorization: Bearer`, cookie, and `?token=` bootstrap redirect.
  `EAUTH` / exit 9 on failure. Documented caveat: ttyd ports still open.
- Ages (`idle_seconds`, `created_seconds_ago`) computed server-side — no
  more "idle 0s" after clock skew.
- Frontend `state.order` / `state.hidden` are pruned for dead sessions.
- `bin/ttyd_wrap.sh` uses `=SESSION` exact-match, matching Python-side
  behaviour.
- Misc: dead `completion` entry removed, `--json` + `--human` precedence
  documented, `tb new --attach` from non-TTY now uses `EUSAGE` exit code,
  `tb web url` no-port returns 0 in both plain and JSON.

## 0.1.0 — Initial release

- Web dashboard (`tmux_browse.py serve`) listing every local tmux session
  as a collapsible pane with an on-demand ttyd iframe.
  - Summary row: Open / Log / Scroll / Hide / reorder pad.
  - Resizable iframes, drag-to-reorder, furled "Hidden (N)" bucket.
  - Stable per-session port assignments persisted under
    `~/.tmux-browse/ports.json`.
- `tb` CLI with 19 verbs (`ls`, `show`, `capture`, `tail`, `exists`,
  `send`, `type`, `key`, `paste`, `exec`, `new`, `kill`, `rename`,
  `attach`, `wait`, `watch`, `web start/stop/url`, `snapshot`,
  `describe`).
  - Stable `--json` envelope (`{ok, data}` / `{ok: false, error, code,
    exit}`) on every verb.
  - Distinct exit codes (`EUSAGE`, `ENOENT`, `EEXIST`, `ETIMEDOUT`,
    `ENOSERVER`, `ETMUX`).
  - Sentinel-based `exec` with idle-strategy fallback for non-shell
    panes.
- Documentation under `docs/` (dashboard, tb, recipes, architecture).
