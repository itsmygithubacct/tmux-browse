# Changelog

## Unreleased — CI workflow + cross-repo version preflight

Maintenance additions that catch version-drift bugs between core
and the agent submodule before they ship:

- `.github/workflows/ci.yml` — core now has CI. Checks out with
  submodules recursive, installs tmux, runs `make preflight` then
  `make test`. Same cadence as the extension's existing workflow.
- `scripts/preflight.py` — four checks run on every PR and before
  every release:
  1. **Submodule populated** — fails fast if
     `extensions/agent/manifest.json` is missing.
  2. **Catalog `pinned_ref` matches submodule tag** — catches the
     "I bumped `.gitmodules` but forgot `catalog.py`" case.
  3. **Core's `__version__` satisfies the extension's
     `min_tmux_browse`** — stricter than the loader's runtime
     check, so bad pairings surface at dev time.
  4. **Submodule manifest version matches its git tag** —
     cosmetic but catches tag/manifest drift.
- `make preflight` and `make ci` targets wrap the script.
- `tests/test_preflight.py` — 11 cases, each check exercised with
  both passing and failing fixtures.

Full suite: 590 tests green (was 579).

## 0.7.1.2 — Extension Manage modal + CLI (2026-04-24)

Completes the extension-management surface. After install (E3), the
only way out was to hand-edit `extensions.json` or delete the
submodule tree manually. E4 fills the remaining verbs:

- **Update** — advances an installed extension to its catalog-
  pinned ref. Submodule path uses `git submodule update --remote`;
  fresh-clone path uses `git fetch` + `git checkout`. Post-update
  manifest is validated against the current core version so a
  bumped extension that now requires a newer core surfaces
  cleanly instead of silently activating.
- **Disable** — flips the enabled bit off (was already available
  from E0; E4 wires it into the Manage modal). Code stays on disk.
- **Uninstall** — removes the extension's code. Submodule path
  calls `git submodule deinit -f`; fresh-clone path `rmtree`s the
  directory. State files under `~/.tmux-browse/` are **kept by
  default** so an uninstall/reinstall round-trip doesn't lose
  agent history. Opt-in state removal is a three-step gate:
  a Manage-modal checkbox, a `confirm()` dialog, and the
  `--remove-state` flag on the CLI.

### UI

- Config > Extensions rows now include a **Manage…** button once
  the extension is installed. It opens a modal showing installed
  version, source (submodule vs clone), and current status,
  with three actions (Update, Disable/Enable, Uninstall) and the
  opt-in state-removal checkbox.

### Headless CLI

- `python3 -m lib.extensions {list,install,update,enable,disable,
  uninstall}` drives the same functions as the HTTP endpoints.
- Makefile targets at the repo root: `make install-agent`,
  `update-agent`, `enable-agent`, `disable-agent`,
  `uninstall-agent`, `uninstall-agent-with-state`, plus
  `list-extensions` and `test`.
- Intentionally *not* gated by the dashboard config-lock —
  shell access already implies file-system access, so an
  HTTP-level secret here would be cargo-culting.

### New endpoints

- `POST /api/extensions/update` — takes `{"name": "..."}`, returns
  `{from_version, to_version, changed, via, restart_required}`.
- `POST /api/extensions/uninstall` real implementation (was the E0
  501 stub). Takes `{"name": "...", "remove_state": bool}`; returns
  a summary of paths removed and paths that weren't on disk.

### Tests

- `tests/test_extensions_manage.py` — 15 new cases: clone-path
  update, fetch failure, submodule update path, unchanged-version
  idempotence, too-new-manifest validation, clone-path uninstall
  (keep state), state-removal deletes declared paths, missing-path
  reporting, submodule uninstall calls `deinit`, idempotent
  uninstall of a missing tree, and three CLI-driver cases
  confirming `python3 -m lib.extensions` goes through the same
  functions as the HTTP handlers.

Full suite: 579 tests green.

## 0.7.1.1 — Config > Extensions install UI (2026-04-24)

One-click install for the agent extension (and any future extension
that lands in `lib/extensions/catalog.py`). The Config pane gains an
**Extensions** card that lists every known extension with a
**Download and enable** button; clicking it fetches the extension
from git, validates the manifest, flips the enabled bit, and shows
a restart banner at the top of the page. Clicking **Restart now**
on the banner hits `/api/server/restart` and the loader activates
the extension on the next boot.

### What's new

- `lib/extensions/catalog.py` — `KNOWN` dict describing each
  installable extension (name, label, description, repo URL,
  pinned ref, submodule path). One entry today: `agent` pinned at
  `v0.7.1-agent`.
- `lib/extensions.install()` — materialises an extension on disk
  via `git submodule update --init` when the path is already a
  registered submodule, else a shallow `git clone` at the pinned
  ref. Validates the fetched manifest. Cleans up partial trees on
  failure so a retry starts clean.
- `lib/extensions.InstallError(stage, msg)` — structured failure
  surface. Stages: `exists`, `clone`, `submodule_init`, `validate`,
  `unknown`. UI renders stage + verbatim message.
- `POST /api/extensions/install` replaces the E0 501 stub. Takes
  `{"name": "<catalog-entry>"}`, returns `InstallResult` fields
  plus `restart_required: true`. Config-lock gated.
- `GET /api/extensions` gains per-row `label` / `description` /
  `repo` / `submodule` / `restart_pending` fields from the catalog
  so the Config card renders in one round trip.
- `GET /api/extensions/available` returns the full catalog (was
  an empty list in E0).
- `static/extensions.js` + `lib/templates.py` Extensions card +
  a restart banner in the page shell. Banner is sticky across tab
  reloads (state pulled from `/api/extensions.restart_pending`) and
  dismissible per session.

### Tests

- `tests/test_extensions_install.py` — eight new cases covering
  fresh-clone success, clone failure (cleanup), manifest-invalid
  failure (cleanup), too-new-extension rejection, non-empty target
  dir rejection, unknown-name rejection, timeout, and the
  submodule-path fast track. `subprocess.run` is mocked so the
  tests don't touch the network.
- `tests/test_config_lock.py` gains two cases confirming
  `/api/extensions/install` and `/api/extensions/enable` return
  403 when the dashboard is locked without a valid token.
- `tests/test_server_extensions.py` updated for the new response
  shape and install semantics.

Full suite: 564 tests green.

## 0.7.1 — agent platform split out to its own repo (2026-04-24)

The agent platform — every `/api/agent-*` endpoint, the `tb agent`
CLI verb, the workflow scheduler, the conductor, the Agent Settings
config card, the Agents / Runs / Tasks sections, and the transcript +
workflow modals — now lives in a separate repository,
[tmux-browse-agent](https://github.com/itsmygithubacct/tmux-browse-agent),
and attaches to core as a git submodule at `extensions/agent/`.

Landed in three phases on a single release so the history is
reviewable and each phase kept the test suite green:

- **E0** — extension loader substrate.
- **E1** — relocate the agent platform into `extensions/agent/`
  behind the loader.
- **E2** — split `extensions/agent/` out into its own repo; attach
  as a submodule; remove the first-start default-enable.

**Upgrade note (if you used the agent platform pre-split):** after
pulling 0.7.1 the Agents pane and `tb agent` CLI are no longer
auto-enabled. Two choices:

1. **Opt in** — go to Config → Extensions → Agents module → Enable
   in the running dashboard. (Or hand-edit `~/.tmux-browse/extensions.json`
   to `{"agent": {"enabled": true}}`.) Requires `git submodule update
   --init` or `git clone --recursive` to have the submodule on disk
   first; the install UI in a forthcoming release drives that too.
2. **Ignore** — the core dashboard keeps working without agents.
   Your saved `~/.tmux-browse/agents.json`, secrets, logs, and
   history are untouched; only the load-at-start bit flipped.

### What moved out

- `lib/agent_*.py` (20 modules), `lib/agent_modes/`, and
  `lib/tb_cmds/agent.py` → the new repo under `agent/*`,
  `agent/modes/`, and `tb_cmds/agent.py`.
- All 24 `/api/agent-*` HTTP handlers cut from `lib/server.Handler`
  into `server/routes.py` as free functions taking `handler` as their
  first arg.
- Agent HTML slots (Agent Settings card, Agents / Runs / Tasks
  sections, transcript + workflow modals) moved from
  `lib/templates.py` into `ui_blocks.html`; the loader fills core's
  `<!--slot:name-->` markers.
- `static/{agents,runs,tasks}.js` → the new repo's `static/`.
- Every `test_agent_*.py` → the new repo's `tests/`; core's runner
  pulls them back in via `tests/test_extension_agent_tests.py` when
  the submodule is checked out.

Net: ~5000 lines leave core. `grep -r '^from lib import agent_' lib/`
returns nothing.

### What stayed

- `lib/docker_sandbox.py`, `lib/session_logs.py`, `lib/tasks.py`,
  `lib/worktrees.py`, `lib/sessions.py` — the primitives the extension
  uses via `agent.core_api`. That's the one file in the extension
  that tracks core's API surface; anything else importing from
  `lib.*` is a bug.
- First-boot `~/.tmux-browse/` is clean — no `extensions.json` is
  auto-written. Extensions are opt-in from now on.

### New in core

- `lib/extensions/` package: manifest parsing, registration merging
  with fail-closed collision detection, per-extension sys.path
  isolation, and slot-based template injection. Extensions declare
  their surface via `manifest.json` and a handful of dotted-path
  entry points.
- `lib/templates.render_index()` now accepts `ui_blocks` and
  `extension_js`; injection points live under `<!--slot:name-->`
  markers. An empty `ui_blocks` dict produces the exact HTML that
  shipped in 0.7.0.4.
- `lib/static.build_js(extension_js)` concatenates core JS with each
  extension's `static/*.js`, with a `window.__tbExtensions` footer
  between them so extension init can register after the core
  bootstrap.
- `lib/extensions/submodule.py` wraps `git submodule update --init`
  and `--remote` for the Config-pane install / update buttons.

### New endpoints

- `GET /api/extensions` — status list (installed / enabled /
  version / last error per extension).
- `GET /api/extensions/available` — catalogue of known extensions
  (empty in 0.7.1; populated when the install UI lands).
- `POST /api/extensions/enable` / `disable` — flag flip with
  config-lock gating. `restart_required: true` in the response
  since the loader runs once per server process.
- `POST /api/extensions/install` / `uninstall` — 501 stubs;
  real implementations land alongside the install UI.

### Tests

- `tests/test_extensions.py` + `tests/test_server_extensions.py`:
  loader, manifest, registry, UI-block parsing, route wiring, index
  slot injection, the five endpoints. Fixtures under
  `tests/fixtures/ext_hello/` and `tests/fixtures/ext_bad_collide/`
  exercise success and conflict paths.
- `tests/test_extension_agent_lifecycle.py`: proves enable → load
  → disable round-trips against the real submodule checkout.
- `tests/test_extensions_submodule.py`: `.gitmodules` parser and
  the `subprocess.run` shape, with `git` mocked.
- `tests/test_extension_agent_tests.py`: loader shim that pulls the
  extension's own `extensions/agent/tests/` under
  `python3 -m unittest discover tests`, using a fresh `TestLoader`
  to avoid clobbering the outer walk's `top_level_dir`.

Full suite: 554 tests green.

### Compatibility

- `tmux-browse-agent` v0.7.1-agent targets `tmux-browse >= 0.7.1`
  per its `manifest.json` `min_tmux_browse`. Earlier extension
  tags (v0.7.0.4-agent) were a pre-release carve; don't use them.
- The submodule is pinned at a specific commit in `.gitmodules`;
  advancing the pin is deliberate.

## 0.7.0.4 — README and default polish (2026-04-24)

Small follow-up to 0.7.0.3. No behaviour changes at the agent-runtime
layer.

### Dashboard defaults

- The Move text button on each pane's summary row now defaults off,
  matching the pattern already in use for Hide, Log, and Scroll
  (text buttons ship off; icons ship on). The folder-arrow
  `wc-move-icon` stays visible by default.

### Documentation

- The README gains a Built-in agent platform section covering
  agents + providers, sandbox modes, the cycle and work modes, the
  conductor rule engine, observability via the run index, and the
  extensible tool registry. Opens with an explicit "under active
  development" heads-up; the two-surface / stdlib-only / ttyd-only
  framing in the opening blurb stays as it was.

## 0.7.0.3 — Agent modes and extensible tool surface (2026-04-24)

Adds long-running agent modes (cycle, work) that compose on top of
the existing single-turn runner, teaches the dashboard about agent
modes, and introduces a pluggable tool registry with `read_file`
as the first non-`tb_command` tool.

> **Heads-up:** the agent-mode feature (cycle, work) is under active
> development. Behaviour and defaults may shift between patch
> releases; treat this surface as unstable until a minor-version
> bump lands.

### Agent modes: `cycle` and `work`

Two new agent-level modes, each a thin orchestrator above the
existing run loop — no new scheduler, no new log format, no new
conversation store.

- **Cycle mode.** One planning-then-execute turn per invocation.
  The agent reads a goal (inline, from a file, or proposes one),
  returns a short plan, then runs against that plan with the
  normal tool budget. Goal file defaults to
  `~/.tmux-browse/agent-cycle/<agent>.txt`. CLI: `tb agent cycle`.
  Dashboard: Cycle button on each agent card.
- **Work mode.** File-backed task queue runner. One task per line
  (plaintext or JSON); a sibling `.done` file tracks completions
  so re-running the same file resumes cleanly. Stops on empty
  queue, daily budget exhaustion, cumulative step cap, stop
  signal, or `--stop-on-error`. CLI: `tb agent work`. Dashboard:
  Work button on each agent card.

### Mode-aware status

Each agent's derived status carries the `mode` and `mode_phase`
inferred from the most recent run. The Agents pane renders a grey
badge alongside the status badge — `cycle / plan`, `cycle / exec`,
`work`, or blank for generic runs. The Runs search filter gains
an **Origin** dropdown covering CLI, REPL, Scheduler, Conductor,
Cycle, Work, and Retry.

### Extensible tool registry

Agents now declare which tools they're allowed to call. Each tool
ships a host dispatch and (where applicable) a Docker-sandbox
dispatch, both of which route through the same run-log substrate
so every invocation is auditable.

- **`tb_command`** — the existing tool, unchanged for every
  existing agent.
- **`read_file`** — bounded file read, default 16 KiB, hard cap
  64 KiB. Host paths are validated against the same sensitive-
  directory blocklist used by the sandbox; Docker mode only
  accepts paths under `/workspace` or `/opt/tmux-browse`.

Per-agent `tools` field defaults to `["tb_command"]` so every
existing agent is bit-identical after upgrade. Agents with more
than the default get an `Enabled tools:` block in their system
prompt; calls to tools that aren't enabled are rejected cleanly
with an explicit error.

### Deferred

- **Drive mode.** Was scoped alongside cycle and work but held back
  pending a solid termination contract; ships in a follow-up.
- **Tools checkbox in the agent form.** The `tools` field can be
  set on disk or via the CLI today; a dashboard checkbox group
  lands in a follow-up.

## 0.7.0.2 — Conductor, structured REPL, pane groups (2026-04-24)

Patch-level release (not formally tagged; 0.7.0.3 is the first tag
after v0.7.0) covering agent-side automation features — a
conductor rule engine above event hooks, REPL primitives modelled
on tmuxai, and dashboard-side organisation features including
user-defined pane groups, a Move-to button, and server-side
config-lock enforcement.

### Conductor rule engine

A thin rule engine above event hooks that adds three capabilities
individual hooks can't express:

- **State across events** — rolling-window counters
  (`within_last` + `count_at_least`), keyed by `(rule_id, agent)`.
  A rule can require "three failures in one hour" without any
  external state.
- **Cross-agent routing** — a new `run_agent` action spawns a run
  on a different agent with `$.original_prompt` substitution. On
  Sonnet rate-limit, failover to Opus automatically.
- **Decision log** — every fired rule appends a JSONL record to
  `~/.tmux-browse/agent-conductor.jsonl` so operators can always
  answer "why did this happen?".

Rules live in `~/.tmux-browse/agent-conductor.json`. The editor sits
in Config → Agent Settings alongside Event Hooks, each agent card
grows a "Conductor: N" badge that opens a recent-decisions view,
the Runs search gains an origin filter, and QR share carries the
rule set across devices. A runaway-loop guard drops same-rule
same-agent re-entry within 5 seconds so rules whose actions might
re-cause the triggering event can't fork-bomb.

### Structured REPL primitives

MVP of the tmuxai-style REPL shape. Per-agent context (exec target,
observed panes, mode, tick) persists at
`~/.tmux-browse/agent-contexts/<agent>.json`. A per-agent knowledge
base holds small text files under `~/.tmux-browse/agent-kb/<agent>/`
with a 128 KiB total cap; contents prepend to the system prompt on
every turn.

New `tb agent repl` slash-commands: `/exec`, `/watch`, `/unwatch`,
`/mode`, `/tick`, `/kb add|rm|ls`, `/context`. Each agent card in the
dashboard gains a **Context** button that opens a read-only summary.

Explicitly deferred to a follow-up: watch-mode auto-turn loop
(observed-pane hash change → auto invocation) and `/squash`
compaction. Current slash-commands thread the mode value through
the context but don't enforce observe/act/watch at the loop layer
yet.

### Server-side config-lock enforcement

Until now the config-lock password gated only the Config pane UI; a
bare `curl -X POST /api/agents` on a LAN bypassed it entirely. This
closes that gap without adding a full auth system.

- `/api/config-lock/verify` now returns a 32-byte `unlock_token` with
  a 12-hour TTL, held in server memory. Clients send it as
  `X-TB-Unlock-Token` on every non-GET request.
- The gate (`_check_unlock`) fronts every mutation endpoint:
  `/api/agents`, `/api/agents/remove`, `/api/agent-hooks`,
  `/api/agent-workflows`, `/api/dashboard-config`, `/api/tasks`,
  `/api/tasks/update`, and `/api/config-lock` itself. GETs, session
  lifecycle, ttyd, and agent launch are deliberately not gated.
- Clearing the lock drops every issued token.
- Client (`api()` in `static/util.js`) automatically prompts and
  retries once when a 403 "config locked" is returned.

### User-defined pane groups

Named buckets generalize the old Visible/Hidden binary:

- Config > Behavior gains a Pane Groups editor (Add / Rename /
  Remove). Visible and Hidden are reserved and non-removable.
- A pane belongs to exactly one bucket at a time. Hide still sends
  to Hidden; moves between groups go through the new Move button.
- Groups render as their own furled `<details class="group-wrap">`
  between the Visible stack and the Hidden drawer.

### Move-to button and popover

- New blue **Move** text button and folder-arrow icon button on each
  pane's summary row, gated by `show_summary_move` /
  `show_wc_move_icon` (both default on).
- Popover lists Visible, every user group, Hidden, and an inline
  "+ New group…" option.
- Click-outside and Escape close it.

### QR / link config share, broadened

`collectViewConfig()` / `applyViewConfig()` now carry pane-group
definitions + membership and a cached copy of the server-side event
hooks. Importing hooks from a QR POSTs through `/api/agent-hooks`,
so the config-lock gate holds naturally. Excluded by design: unlock
tokens, agent API keys, and per-conversation REPL state.

## 0.7.0 — Docker sandbox and content-hash idle (2026-04-24)

### Idle detection and session logging

- **Content-hash idle.** Every session is piped to
  `~/.tmux-browse/session-logs/<name>.log` via `tmux pipe-pane`.
  `idle_seconds` is now derived from a SHA-256 of the log tail rather
  than tmux's `session_activity`, so cursor blinks no longer look like
  activity and a long-thinking agent with no output is reported
  accurately. Falls back to `session_activity` for pre-existing
  sessions before their log exists. New module `lib/session_logs.py`.
- **Idle-alert threshold in hours + minutes.** The per-session idle
  modal replaces the old seconds-only input with two fields (hours and
  minutes), each with native up/down arrows. Minimum threshold bumped
  from 5 s to 60 s.
- **Always-on idle polling.** When `auto_refresh` is off, a 60-second
  `pollIdleOnly()` loop still fetches `/api/sessions` so idle labels
  and alerts update without a full refresh. Hidden sessions are
  skipped.

### Dashboard UI defaults and polish

- **Quieter summary row.** Attached-clients and port badges drop their
  green/orange accents; all badges now inherit the base grey styling.
  Window-count and port-badge defaults flip to off; the attached-clients
  default mirrors the canonical `~/.tmux-browse/dashboard-config.json`.
- **Hide/unhide tooltip.** The Hide button and incognito icon now flip
  their `title` to "unhide this session" when the session is in the
  hidden list.
- **Lock config pane** moved to the top of the Config body (furled by
  default) so access control sits above the settings it gates.
- **Multi-viewer sizing.** `ttyd_wrap.sh` now gives every ttyd viewer
  its own grouped tmux session (via `new-session -t`, with
  `window-size latest` and `destroy-unattached on`) so one narrow
  viewer can't pin every other viewer's windows to its size.
- **Pane Admin and Connected Endpoints are now Config subsections.**
  Both were top-level config-panes; they fit better nested under
  Config since they configure the view rather than show session
  content. Connected Endpoints sits at the bottom of the Config body.
- **"Clear Local Cache" button.** A new red button in the Config
  actions row removes every `tmux-browse:*` key from `localStorage`
  plus `sessionStorage`, then reloads. Server-side state is
  untouched. Useful when a secondary device's cached view diverges
  from what you want and DevTools is awkward to reach.

### Docker sandbox for `tb agent`

- **New sandbox mode: `docker`.** Agents configured with
  `sandbox=docker` run their `tb_command` tool inside a short-lived
  container with its own tmux server (session `sandbox`,
  `/workspace`). The agent loop, provider API calls, and run logging
  stay on the host; only execution moves into the container. API keys
  never enter the container. `run_agent()` owns lifecycle in one
  try/finally and is the sole owner — scheduler and CLI only pass a
  spec. Fail-closed: missing Docker or failed startup is a hard run
  failure, never a host fallback.
- **Isolation enforced at the boundary.** `exec_tb()` rejects any
  non-`sandbox:` target before invoking `docker exec`, so a misbehaving
  model can't reach host tmux even if it ignores the system prompt.
- **Host-global capability flag.** `/api/agents` exposes
  `docker_supported`; the UI hides the Docker option on hosts without
  Docker but preserves saved `sandbox=docker` config as
  `docker (unavailable on this host)` rather than rewriting it.
- `Dockerfile.sandbox` ships a minimal `ubuntu:24.04 + python3 + tmux`
  image. See `docs/tb.md` for the `Sandbox modes` section.

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

### Dashboard UI features

- **Day / night mode.** Light theme toggle in Config > Behavior.
  Default: dark (night mode). Shares via QR/config transfer.
- **Granular title bar config.** Master toggle hides the entire bar;
  individual toggles for title text, session count, new session field,
  Raw ttyd, Refresh, Restart buttons, and status text. All On/All Off
  button per section.
- **Granular summary row config.** Master toggle hides all summary
  controls. Individual toggles for session name and expand/collapse
  arrow. Hiding the arrow prevents pane furl/unfurl.
- **Granular expanded pane config.** Master toggle hides the action
  buttons row. Individual toggles for each button.
- **Phone keyboard addons.** Floating row of touch-friendly buttons
  below each ttyd iframe. Fully customizable: add any key via label +
  tmux key name, drag to reorder, click to remove. Own furled config
  subsection with live preview. Stored in localStorage.
- **Send bar.** Text input below each pane to send commands to the tmux
  session. Disabled by default; enable in Config.
- **Drag summary bar to snap side-by-side.** Tap the summary bar to
  furl/unfurl (unchanged); drag it onto another session's left/right
  half to snap side-by-side (up to 4 panes per row). Drag to center
  to reorder above.
- **Furl side-by-side together.** When one pane in a row is furled, all
  siblings furl too (and vice versa). Config toggle, default on.
- **Resize row together.** Dragging one iframe's resize handle
  propagates the height to all siblings in the row via ResizeObserver.
  Config toggle, default on.
- **Config section toggle buttons.** "All On" / "All Off" buttons on
  Title Bar, Summary Row, and Expanded Pane config cards.
- **Config pane lock.** Optional password stored as SHA-256 hash at
  `~/.tmux-browse/config-lock-secret`. When locked, Config pane
  prompts for password. CLI `tb config set/reset` also checks the
  lock. Prevents agents from modifying their own step budget.
- **QR code config transfer.** Export full view config (layout, hidden,
  hot buttons, phone keys, theme, etc.) as a QR code. Scan from
  phone camera using BarcodeDetector API. Also works as a URL with
  `?import-cfg=BASE64` parameter. Server-side QR generation via pure-
  Python encoder (`lib/qr.py`).
- **Connected Endpoints pane.** Shows all browser clients connected to
  the dashboard with IP, nickname, and idle time. "Share Config"
  button pushes your view config to another client. Recipients get a
  confirm prompt. Endpoints: `GET /api/clients`,
  `POST /api/clients/nickname`, `POST /api/clients/send-config`,
  `GET /api/clients/inbox`.

### Internal

- **JS module split.** `static/app.js` (2,876 lines) split into 10
  focused modules under `static/`. Concatenated at import time by
  `lib/static.py` — browser still gets one inlined `<script>` block.
  No build step, no ES modules, no behavioral changes.

### Tests

304 tests (up from 168 at the start of 0.6.0 work). New test files:
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
