# Changelog

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
