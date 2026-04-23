# Changelog

## 0.6.0 — Agent operations platform

### Agent runtime foundations (Phase 0)

- **`run_id` on every agent run.** Each `run_agent` call gets a unique,
  time-sortable identifier (8-hex epoch + 12-hex random).
- **Structured provider results.** `ProviderResult` dataclass replaces
  bare-string returns from provider adapters — carries `content`,
  `usage` (token counts), and `raw_model`.
- **Lifecycle log entries.** Every run emits `run_started`,
  `run_completed`, `run_failed`, or `run_rate_limited` to the agent log
  with schema version tagging.
- **Persistent conversations.** REPL sessions now write turns to
  append-only JSONL files under `~/.tmux-browse/agent-conversations/`.
  Resume on restart; `/history`, `/clear`, `/new` commands in the REPL.

### Live agent status (Phase 1)

- **Status derivation engine.** New `agent_status.py` infers per-agent
  status (running / idle / error / rate\_limited / workflow\_paused)
  from the latest log entry and workflow config.
- **Dashboard badges.** Each agent card in the Agents pane shows a
  colored status badge, reason text, and relative last-activity time.
- **Status in API.** `GET /api/agents` now includes `status`,
  `status_reason`, and `last_activity_ts` per agent.

### Server-side workflow scheduler (Phase 2)

- **Background scheduler.** A daemon thread in the dashboard server
  evaluates due workflows every 10 s and runs them via `run_agent`.
  Browser no longer drives workflow execution — it observes only.
- **Scheduler lock.** PID-based file lock prevents duplicate dashboard
  processes from both executing workflows.
- **Workflow history.** Append-only JSONL run log plus atomic per-workflow
  state file (last run, next run, failure count).
- **New endpoints.** `GET /api/agent-workflow-state`,
  `GET /api/agent-workflow-runs`.

### Searchable run index (Phase 3)

- **Run index.** Completed and failed runs are indexed in
  `~/.tmux-browse/agent-run-index.jsonl` with prompt/message previews,
  step counts, duration, and tool verbs used.
- **Filtered search.** `GET /api/agent-runs` supports query params:
  `agent`, `status`, `since`, `until`, `q` (text), `tool`, `limit`.
- **Single-run lookup.** `GET /api/agent-run?run_id=X`.
- **Dashboard Runs section.** Search bar with agent/status dropdowns and
  result cards showing status badges, metrics, and relative timestamps.

### Conversation forking (Phase 4)

- **Fork conversations.** `agent_conversations.fork()` copies all turns
  into a new conversation with `parent_id` linkage. Original and fork
  diverge independently.
- **REPL support.** `/fork` command and `--fork` CLI flag on
  `tb agent repl`.
- **Dashboard button.** "Fork REPL" on each agent card creates a forked
  conversation and opens it in a new tmux session.
- **Server endpoint.** `POST /api/agent-conversation-fork`.

### Task / worktree mode (Phase 5)

- **Task abstraction.** Optional tasks with title, repo path, worktree
  path, assigned agent, linked tmux session, and status
  (open/done/archived). Persisted at `~/.tmux-browse/tasks.json`.
- **Git worktree management.** Auto-creates worktrees under
  `~/.tmux-browse/worktrees/` with `tb-task/<slug>` branches.
- **Task CRUD.** `GET /api/tasks`, `POST /api/tasks` (create),
  `POST /api/tasks/update`, `POST /api/tasks/launch`.
- **Dashboard Tasks section.** Create form with title/repo/agent fields,
  task cards with Launch and Done buttons.

### Cost accounting (Phase 6)

- **Per-run cost tracking.** Token usage from `ProviderResult` is
  recorded in `~/.tmux-browse/agent-costs.jsonl` on every run.
- **Aggregation.** `agent_costs.per_agent_totals()` and
  `daily_totals()` for dashboard and API consumers.
- **Endpoint.** `GET /api/agent-costs` returns per-agent and daily
  token totals.
- **Dashboard summary.** Token usage line below agent cards.

### Sandbox profiles (Phase 7)

- **Sandbox field on agents.** Optional `sandbox` (host / worktree) in
  agent config, normalized with validation, defaults to `host`.
- **Dashboard selector.** Sandbox dropdown in the agent config form.

### Other features

- **Phone keyboard addons.** Floating row of touch-friendly buttons
  below each ttyd iframe: arrow keys, Esc, C-c, C-b, Shift, PgUp,
  PgDn. Disabled by default; enable via Config > Expanded Pane >
  "Phone keyboard addons". New `POST /api/session/key` endpoint sends
  tmux key sequences.
- **Send bar.** Text input below each pane to send commands to the tmux
  session. Disabled by default; enable in Config.
- **Config section toggle buttons.** "All On" / "All Off" buttons on
  Summary Row and Expanded Pane config cards.

### Tests

304 tests (up from 168 at the start of 0.5.0 work). New test files:
`test_agent_runs`, `test_agent_conversations`, `test_agent_status`,
`test_agent_scheduler`, `test_agent_scheduler_lock`,
`test_agent_workflow_runs`, `test_agent_run_index`, `test_agent_costs`,
`test_tasks`, `test_worktrees`, `test_agent_runtime`, `test_agent_logs`.

## 0.4.1 — Dashboard agent editor + default tweaks

### Features

- **Dashboard agent config UI.** New "Agent" card inside the Config pane
  lets you load a built-in preset or existing agent, edit
  provider/model/base URL/wire API/API key, and save or remove agents —
  all backed by `~/.tmux-browse/agents.json` and the private
  `agent-secrets.json` secret store.
- **`save_agent` upsert semantics.** Saving an agent without an API key
  now preserves the previously stored key, so you can update model or
  provider without re-entering the secret.
- **`catalog_rows` helper.** New function exposes the built-in agent
  catalog as a flat list for the dashboard preset selector.
- **Server agent routes.** `GET /api/agents` returns configured agents,
  catalog defaults, and file paths. `POST /api/agents` saves an agent;
  `POST /api/agents/remove` deletes one. Errors map to structured JSON
  with appropriate HTTP status codes.

### Defaults changed

- **Auto refresh off by default.** Dashboard no longer auto-refreshes on
  first load; toggle it on in Config if desired.
- **Launch / Stop ttyd / Kill buttons hidden by default.** Reduces
  visual clutter for new users; re-enable via the Config visibility
  toggles.

### Tests

- New `test_server_agents.py` covering route registration, save, remove,
  and error-mapping handlers.
- New `test_agent_store.py` cases for `save_agent` key-preservation and
  missing-key validation.

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
