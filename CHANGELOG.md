# Changelog

## 0.7.5.0 — Quickstart scripts, ttyd reconcile, agent catalog bump (2026-04-29)

Three loosely-related improvements ship together:

**Quickstart entry points.** `bin/quickstart_local.sh` and
`bin/quickstart_lan.sh` are curl-pipeable bootstraps. Each detects
the latest core release tag, shallow-clones it, runs
`tmux_browse.py doctor` to see what's missing, installs only the
prereqs that aren't already present, and launches the server. The
two variants differ only in default bind address (127.0.0.1 vs
0.0.0.0). Both are linked from the README's Install section.

**ttyd pidfile reconcile.** Three stacking failure modes used to
produce the "panes go black, never recover" symptom — pidfile
flap (transient /proc reads misclassified as dead), an iframe that
blanked on the first `ttyd_running:false` poll, and federation
poll recursion under a busy peer mesh. Fixed in `lib/ttyd.py`,
`lib/server.py`, `lib/server_routes/sessions.py`, and
`static/panes/render.js`:

- `_pid_alive` now distinguishes ESRCH/ENOENT (definitely dead)
  from EPERM and other transient errors (assume alive).
- `_reconcile_pidfile` scans `/proc` for a ttyd whose argv
  references the session's wrapper and rewrites the pidfile +
  scheme sidecar so subsequent `read_pid` calls hit the fast
  path. Self-heals "pidfile vanished, ttyd still alive."
- Frontend needs five consecutive `ttyd_running:false` readings
  before clearing the iframe `src`. Single-tick noise no longer
  destroys a working terminal.
- Peer-originated `/api/sessions` requests pass `?local=1` to skip
  the federation merge, breaking the recursive aggregation cascade
  that turned N peers polling at 1 Hz into N\*(1+N) handler hits.
- `request_queue_size` raised from the stdlib default of 5 to 128
  so SYN floods of peer polls don't drop.

Plus an iframe `sandbox` attribute that suppresses ttyd's built-in
beforeunload prompt so re-launching or expanding a pane no longer
pops a "Leave site?" dialog.

**Agent extension catalog.** Pin moved from `v0.7.2-agent` to
`v0.7.3-agent`. The new extension release adds the CLI-agent
breadth surface (10 supported CLI agents — Claude Code, Codex,
OpenCode, Vibe, Gemini, Cursor, Copilot, Pi, Droid, settl) with
spawn / status / hooks / launch UI. See the agent extension's own
CHANGELOG for the K-phase detail.

### Acceptance

- 741 tests, no new failures (pre-existing test-isolation flake
  in `test_extension_agent_lifecycle` is unchanged).
- A dashboard with multiple expanded ttyd panes survives a
  pidfile flap without blanking.
- Peer mesh holds steady under simultaneous polls.

## 0.7.4.1 — Fix ttyd iframe flicker under SSE refresh (2026-04-27)

Regression introduced by 0.7.2.2's SSE refresh: `renderLayout()`
clears `#sessions` and re-appends every pane's `<details>` on
every refresh tick. With the previous 5-second polling cadence
this was tolerable churn; with SSE pushing updates roughly every
second it caused embedded ttyd iframes to detach/reattach
constantly — browsers reload an iframe on detach, so each pane
flashed to black, started its ttyd reconnect, and got torn down
again before the WebSocket finished negotiating. Result: panes
that never stabilised.

The fix is a layout signature memo. `renderLayout()` now
computes a JSON signature over the bits that actually affect the
DOM tree (current visible layout, hidden set, group definitions
+ memberships, live session names) and short-circuits when the
signature matches the last call. On a quiet dashboard that's
every refresh; on a layout change (new session, rename, hide,
move, drag-drop, group edit) the signature differs and the full
rebuild fires once.

`refreshHiddenChrome()` still runs on every invocation so the
hidden-count badge stays current even when the DOM rebuild is
skipped.

### Acceptance

- 625/625 tests still passing.
- A dashboard with multiple expanded ttyd panes stays
  stable under SSE — no flicker, no reconnect storms.
- Adding/removing/hiding a session still refreshes the layout
  on the next tick.

## 0.7.4.0 — Federation pairing model + Config UI (2026-04-27)

Replaces 0.7.3.0's auto-trust LAN federation with explicit
**request → accept** pairing on both sides. Discovery still
happens automatically (UDP beacons unchanged), but no peer's
sessions appear in your dashboard until both operators have
clicked through the handshake.

Sub-version bump (0.7.3 → 0.7.4) because the change is a
default-deny behaviour shift: users upgrading from 0.7.3.0
will see their previously-aggregated peers go quiet until they
re-pair via the new Config UI. This is the right safety
default — 0.7.3.0's "trust everyone on the LAN" was too
permissive for shared networks.

### How pairing works

Discovery (UDP beacon on port 8095) is unchanged. The new step:

1. Operator on hostA clicks **Request Pair** on hostB's row in
   the Federation Config card.
2. hostA POSTs to `hostB/api/peers/pair-request`. hostB records
   it as a pending request and surfaces it in its own
   Federation card with **Accept** / **Decline** buttons.
3. Operator on hostB clicks **Accept**. hostB writes the pair
   to `~/.tmux-browse/paired-peers.json` AND POSTs back to
   `hostA/api/peers/pair-accept-callback`. hostA writes its
   own record IFF it has an outgoing record for hostB
   (preventing unsolicited "we accepted" messages).
4. Both sides paired. Session aggregation now fetches from
   each other; sessions appear with the `<hostname>:` prefix.

Either side can **Unpair** at any time. We don't notify the
peer; their pairing state is their own concern (the next
beacon arrives, the row goes back to `discovered` on the
unpaired side).

### New: Federation Config card

In Config → Federation, every visible peer gets one row with
the right action button:

| Status | Button |
|---|---|
| `discovered` (online) | **Request Pair** |
| `request-sent` | (waiting label) |
| `request-pending` | **Accept** / **Decline** |
| `paired` | **Unpair** |

The badge in the section header counts actionable rows
(paired + pair-pending + request-sent), so an incoming
request is visible without expanding the section. Polls
`/api/peers` every 5 seconds.

### Server-side surface

- `lib/federation/store.py` (new): persistent paired-peers
  set + in-memory pending-request store + outgoing-request
  tracker. Atomic file writes (`.tmp` + replace) at mode 0600.
- `lib/server_routes/peers.py` extended: now exposes
  `pair-request`, `pair-accept-callback`, `pair-request-out`,
  `pair-accept`, `pair-decline`, `unpair`. The two callback
  routes are unauthenticated (the operator hasn't trusted the
  peer yet); the four operator-action routes are config-lock
  gated.
- `_merge_peer_sessions` now filters peers through
  `is_paired()` before any HTTP fetch — discovered-but-
  unpaired peers contribute zero rows.

### Security properties

- A hostile peer **can** broadcast a fake hostname and queue a
  pair request to you (which you'll see and decline).
- A hostile peer **cannot** write itself into your paired set,
  read your sessions, or replay an old accept (each
  pair-accept-callback requires a fresh outgoing record on the
  receiver — only Request Pair creates one).

### Local symmetry (folded H6)

Local session rows now also carry `device_id` and
`peer_hostname` (was `null`). The frontend host badge logic
distinguishes local (subtle grey) from remote (accent blue),
and only shows the local badge when at least one remote is
also present — solo dashboards stay clean.

### Tests

- `tests/test_federation.py` adds 12 tests covering paired
  store persistence, pending TTL, outgoing-record tracking,
  the pair-accept-callback security guard (refuses callbacks
  from peers we never asked), and the aggregation-only-when-
  paired property. Suite: 613 → 625 tests, all green.

### Upgrade notes

After upgrading from 0.7.3.0, your dashboard will not show
any remote sessions until you re-pair via the new Federation
Config card. The paired-peers file is created on first pair;
no migration needed.

If you want the old auto-trust behaviour back for a single
process, there's no flag for it (intentionally). Operators
on truly trusted single-tenant LANs can pair once after
upgrade and the pair persists across restarts; the request
overhead is one click per peer, total.

## 0.7.3.0 — LAN federation (2026-04-27)

Two or more tmux-browse instances on the same LAN now
auto-discover each other and merge their session lists in one
dashboard. Each remote session's name is prefixed with its
peer's hostname (`hostA:work`); clicking through routes the
ttyd iframe directly to the peer.

Sub-version bump (0.7.2 → 0.7.3) because the change adds new
HTTP routes, a new UDP listener thread, a new CLI flag, and a
new trust model that operators need to know about before they
upgrade.

### What's new

- **Auto-discovery via UDP broadcast.** Each instance beacons
  its identity to UDP `255.255.255.255:8095` every five
  seconds and listens on the same port. Stdlib-only sockets,
  no mDNS / zeroconf dependency. Discovered peers expire 15
  seconds after their last beacon.
- **Aggregated session list.** `_session_summary()` fetches
  each known peer's `/api/sessions` in parallel (1.5s per-peer
  timeout, 2s total budget). Failed/slow peers contribute
  nothing for that tick.
- **Hostname prefix.** Remote rows arrive with
  `name="<hostname>:<originalname>"` and a `peer_url` /
  `device_id` tag, used to route iframe loads + lifecycle
  calls back to the originating peer.
- **Hostname badge in the dashboard.** Subtle small-caps badge
  in the summary row marks federated rows so they're visible
  at a glance without overwhelming local sessions.
- **`--no-federation` flag.** Disables the broadcaster +
  listener and skips the aggregation merge. Use on untrusted
  networks.
- **`/api/peers` route.** Lists discovered peers with their
  device_id, hostname, port, scheme, version, last_seen, and
  derived url.

### New files

- `lib/federation/__init__.py` — peer registry, device-id
  persistence, broadcaster, listener, `start_federation()`.
- `lib/server_routes/peers.py` — `/api/peers` route handler.
- `tests/test_federation.py` — 12 unit tests for the device
  id, peer registry, beacon payload shape, and fetcher error
  paths. Suite: 601 → 613 tests.
- `docs/federation.md` — design, trust model, limitations,
  firewall verification recipe.

### Trust model

> **Important:** any host on the same broadcast domain can
> claim to be a peer. Federation is appropriate for trusted
> single-user / single-tenant LANs only. Disable on shared or
> untrusted networks with `--no-federation`. See
> `docs/federation.md` for the full discussion.

### Limits worth knowing

- **Same scheme across peers.** A dashboard running over
  HTTPS cannot embed an iframe from a peer running plain HTTP
  (browsers block mixed content). Run all peers on one
  scheme.
- **No auth handshake between peers.** Mismatched auth tokens
  silently exclude the misconfigured peer from the merge.
- **Two tmux-browse processes on one host.** Only one can
  bind the UDP listener port. The second still beacons but
  doesn't see incoming peers; logged at WARN at startup.
- **No proxy mode.** Browsers connect directly to peer ttyd
  ports, so the peer's ttyd port range must be reachable from
  your browser.

### Acceptance

- 613/613 tests green.
- `/api/peers` reports the live peer list.
- Two-host smoke test (manual): both hosts see each other's
  sessions within ~10s of starting; the hostname-prefixed
  panes render the host badge; expanding a remote pane loads
  ttyd from the peer's port; killing a remote session works.

## 0.7.2.3 — Live pane preview tiles (2026-04-27)

Each session pane now shows the last ~20 lines of its active
pane as a small ANSI-colored monospace tile while the pane is
collapsed. When you expand a pane, the live ttyd takes over —
the static snapshot only shows where it adds value (the "what's
happening across all my sessions" glance).

### Server side

- `lib/sessions.py` adds `capture_pane_snapshot(name, lines=20)`
  + a 10s cache (`get_cached_snapshot`) + cache GC for vanished
  sessions. Two requests within the TTL share one subprocess
  call — important at the SSE 1Hz cadence.
- `_session_summary()` populates a new `snapshot` field per row.
  Per-request budget of 200ms caps the worst-case latency when
  many sessions are simultaneously stale; sessions over budget
  serve cached or empty snapshots and refresh on the next tick.

### Client side

- New `static/panes/snapshot.js` with `ansiToHtml()` (SGR escape
  parser, 16-color + 256-color fg/bg) and
  `trimTrailingBlankLines()` (the muxplex lesson — trim before
  slicing so sessions with cursor near top still show content).
- `static/panes/render.js::createPane` adds a `<pre
  class=\"pane-snapshot\">` inside the `<summary>` so the tile
  is visible while collapsed. `updatePane` fills it on each
  state update.
- CSS: 9px monospace, max 240px height, hidden via `:empty` for
  raw shells and via `details[open]` so the live ttyd doesn't
  compete with a static snapshot.

### Config

- New dashboard config key `show_pane_snapshot` (default `true`)
  with a checkbox in the Summary Row section. Toggle is
  immediate — no reload needed.

### Forward-compat

- Each row now also carries a `device_id` field (always `null`
  here) — placeholder for Phase I's federation work, which
  needs it to mark remote-host sessions.

### Acceptance

- Session pane shows last ~20 lines as colored monospace text
  while collapsed; live ttyd when expanded.
- Toggle hides/shows snapshots; layout reflows cleanly.
- 601/601 tests still passing. Cold call ~900ms (7 sessions
  capturing fresh), warm call ~146ms (cache hits).

## 0.7.2.2 — SSE-driven session refresh (2026-04-27)

The dashboard now stays live by default — session list, ttyd
state, bell counters, and tmux-unreachable status all flow
through a Server-Sent Events stream instead of waiting for the
5-second polling tick.

### What changed

- New route `GET /api/sessions/stream` (in
  `lib/server_routes/sessions_stream.py`) emits
  `text/event-stream` with one `data:` event per state change.
  Polls `_session_summary()` once per second; emits only on
  diff so an idle dashboard generates near-zero traffic.
  Sends a keepalive comment line every 25s to survive proxies
  that drop idle TCP.
- New config knob `refresh_strategy` (`"sse"` default | `"poll"`)
  in `lib/dashboard_config.py`. Set to `"poll"` if SSE is
  blocked by your network or proxy.
- Client side: `static/panes.js` factors `refresh()` into a
  thin polling wrapper and a shared `applySessions()` that
  both the polling path and the SSE path feed. New
  `startSessionStream()` opens an `EventSource` on load;
  falls back to `scheduleRefreshLoop()`'s interval polling
  only when SSE is unsupported or disabled.
- `state.sessionStream` tracks the live `EventSource` so
  duplicate starts are no-ops and tab close cleanly drops the
  server-side handler thread.

### Behaviour change worth noting

Previously the dashboard required users to flip the
`auto_refresh` toggle to get live updates. With SSE on by
default, updates land within ~1s of any tmux change without
that toggle. The `auto_refresh` + `refresh_seconds` knobs
still gate the polling fallback path (used when SSE is
disabled or unavailable).

### Acceptance

- `curl -N http://host/api/sessions/stream` streams
  newline-separated `data:` events; only emits on state
  change.
- Killing a session via `tmux kill-session -t foo` updates
  the dashboard within ~2s.
- Closing the browser tab cleanly exits the server-side
  handler thread (no leak across tab churn).
- 601/601 tests still passing.

## 0.7.2.1 — PWA install on mobile (2026-04-27)

Adds a Web App Manifest and a minimal service worker so the
dashboard installs to a phone's home screen as an app, stripping
the URL bar. The dashboard runs identically without the PWA
layer — this is purely a phone-UX affordance.

### What's new

- `static/manifest.webmanifest` — declares the install
  metadata, two icon sizes (192px, 512px) with adaptive-icon
  purpose.
- `static/service-worker.js` — ~30 lines of cache-first fetch
  handler. Caches the shell (manifest + icons + favicon) and
  nothing else; the dashboard HTML and `/api/*` routes always
  hit the network so a server restart is reflected immediately
  and session data never goes stale.
- `static/pwa-192.png`, `static/pwa-512.png` — icon assets,
  rasterised from `static/favicon.svg`.
- `bin/generate-pwa-icons.sh` — regenerable: edit the SVG,
  rerun the script, commit the new PNGs.
- `bin/install-prereqs.sh` gains `--dev` to install the
  ImageMagick + librsvg toolchain that the icon-regen script
  needs. Runtime install path is unchanged.

### Server side

- Four new GET routes — `/manifest.webmanifest`,
  `/service-worker.js`, `/pwa-192.png`, `/pwa-512.png` — handled
  by free functions in `lib/server_routes/meta.py`.
- The service worker is served with `Cache-Control: no-cache,
  max-age=0` and `Service-Worker-Allowed: /` so updates land on
  next page load.

### HTML head

- `lib/templates.py` adds the manifest link, theme-color meta,
  Apple PWA meta tags, and the apple-touch-icon link.
- A small inline script registers the service worker on
  `https://` or localhost only. Plaintext HTTP silently no-ops
  (browsers don't allow SW registration over plain HTTP, which
  is the right gate for tmux-browse's "trusted LAN" default).

### Acceptance

- Chrome on Android over HTTPS shows "Install app" in the menu.
- iOS Safari "Add to Home Screen" launches without the URL bar.
- DevTools → Application → Manifest shows the manifest with no
  warnings; both icons load.
- Plaintext HTTP: the SW does not register (verified in the
  Application panel), but the dashboard otherwise works.
- 601/601 tests still passing — no functional change.

## 0.7.2.0 — Remote-access recipes + README polish (2026-04-27)

Docs-only release. First in the 0.7.2.x line; sub-version bump
because it sets up subsequent releases (PWA, SSE, snapshots) that
will all reference these recipes.

### Remote-access recipes

- `docs/recipes-remote.md` — five self-contained patterns for
  reaching the dashboard from off-LAN: SSH tunnel, Tailscale
  Funnel (with the "Funnel not enabled" tailnet-ACL fix surfaced
  inline), Cloudflare quick tunnel, Cloudflare named tunnel
  with operator-owned DNS, and reverse proxy. Each ends with a
  security note pairing the recipe with `--auth`.
- `README.md` Install section gains a one-line pointer to the
  recipes doc.
- `docs/dashboard.md`'s "Optional authentication" section gets a
  cross-reference to the recipes for the "real perimeter" case.

### README polish

- New "Why this is shaped the way it is" subsection between the
  optional-extensions table and Quick Start. Surfaces the
  stdlib-only / no-build-step rationale and points at
  `docs/architecture.md` for the full module map.

## 0.7.1.9 — Split static/panes.js by feature (2026-04-27)

Pure refactor — no behaviour change. Phase B of the deferred
candidates from 0.7.1.7. Companion to 0.7.1.8's server.py split.

``static/panes.js`` was 2,050 lines holding 81 functions covering
init, refresh, pane DOM construction, drag/drop, layout, the
hidden drawer + pane groups, idle alerts, hot buttons, the send-
queue repeater, every modal dialog, and every session-lifecycle
button handler. Cross-cutting changes touched the same file as
everything else; the recent fresh-clone init bugs were the most
visible symptom.

Split by feature into ``static/panes/``, with each file
concatenated by ``lib/static.py`` in declared load order:

- ``panes/idle-alerts.js`` — idle threshold modal + per-session
  arming + firing (sound / prompt)
- ``panes/hot-buttons.js`` — shared hot button slots + per-session
  hot loops with idle-gating
- ``panes/send-queue.js`` — send-bar single send and the repeat
  queue with idle + 60s cooldown
- ``panes/lifecycle.js`` — launchCodingSession, launch / stopTtyd /
  killSession / stopRawShell / newSession / restartDashboard, plus
  the iframe-fit helpers (resizePane / stepIframeSize /
  fitTmuxToIframe)
- ``panes/layout.js`` — drag/drop, ordering, the move-menu
  popover, hidden drawer chrome, user-defined pane groups
- ``panes/modals.js`` — workflow editor (agent-extension surface
  with structural guards) + split picker
- ``panes/render.js`` — createPane / updatePane: the per-session
  DOM construction (~440 lines of one function plus its tick
  updater)

``panes.js`` itself shrinks from 2,050 → 293 lines and now holds
just the cross-cutting bits: ``refresh``,
``showTmuxUnreachableBanner``, the ``bind`` /
``callExt`` / ``awaitExt`` / ``bindExt`` shim helpers, and the
``DOMContentLoaded`` init handler that wires every button.

Every function in the new files declares with ``function``, not
``const fn =``, so the names hoist into ``window`` after
concatenation. ``lib/static.py``'s ``_JS_FILES`` ordering matters
— ``panes.js`` loads last among the panes/* files so its init
handler can call into anything declared earlier.

No JS or HTML test exists for the dashboard surface; verification
was the existing 601-test Python suite (still green) plus a
manual UI walk through the 14-item smoke checklist documented in
the planning notes (no console errors, agent-extension and
no-extension dashboards both load, drag/drop / split / hide /
hot-button-loop / send-queue / idle-alert / tmux-unreachable
banner all behave as before).

## 0.7.1.8 — Extract server.py route handlers into lib/server_routes/ (2026-04-27)

Pure refactor — no behaviour change, no public API change, JSON
shapes byte-identical. Phase A of the deferred candidates from the
0.7.1.7 review.

`lib/server.py` was 1,246 lines holding 37 ``_h_*`` route-handler
methods on a single ``Handler`` class. The class also held the HTTP
plumbing (auth gate, body parsing, JSON envelope helpers, dispatch
tables). Adding a new route or finding an existing one's body meant
scrolling through 36 unrelated handlers in one file.

Split the handler bodies into per-feature modules under
``lib/server_routes/``, mirroring the shape ``lib/tb_cmds/`` already
uses for ``tb`` verbs:

- ``lib/server_routes/meta.py`` — index, favicon, health, server-restart
- ``lib/server_routes/sessions.py`` — sessions list, log, lifecycle, type/key/scroll/zoom/resize/kill
- ``lib/server_routes/ttyd.py`` — start, raw, stop
- ``lib/server_routes/ports.py`` — port registry
- ``lib/server_routes/clients.py`` — connected-browser tracking + config sharing
- ``lib/server_routes/config.py`` — dashboard config + config-lock
- ``lib/server_routes/extensions.py`` — status / available / install / uninstall / update / enable / disable
- ``lib/server_routes/tasks.py`` — task store + worktree-based launch

Each module exports free functions named ``h_*(handler, parsed[, body])``;
the dispatch tables in ``Handler._GET_ROUTES`` / ``_POST_ROUTES``
target them directly. ``Handler`` itself keeps the HTTP plumbing
(``_send_json``, ``_send_html``, ``_check_unlock``, ``_auth_gate``,
``do_GET``/``do_POST``) and the dispatch tables — nothing else.

State that ``Handler`` and its helpers also touch — ``_clients``,
``_client_inbox``, ``_unlock_tokens``, ``_extensions_pending_restart``,
``_session_summary``, the various ``_log_html`` helpers — stays in
``lib/server.py``. The route modules import them lazily where
needed so the load-time dependency stays one-way.

``lib/server.py`` shrinks from 1,246 → 671 lines. Two test files
(``tests/test_config_lock.py``, ``tests/test_server_extensions.py``)
that previously called ``server.Handler._h_X`` directly are
mechanically updated to call ``server.routes_X.h_Y`` — that's the
new public path for these handlers.

The route-table-immutability test still passes — it asserts on the
*set* of registered paths, not the identity of handler functions.
Full suite: 601 tests green.

Phase B (split static/panes.js by feature) is the next planned
refactor — see the planning doc in ``~/research/tmux-browse/`` for
the full plan.

## 0.7.1.7 — Extension-call shim + SessionSummary dataclass (2026-04-27)

Two small, surgical refactors prompted by the regressions and churn
of the last few releases. No behaviour change; both are about
preventing a class of bugs and a class of signature churn.

### `callExt` / `awaitExt` / `bindExt` in `static/panes.js`

- Three releases in a row added `typeof X === "function"` guards
  to a different init or refresh path that called an
  agent-extension global. The pattern was easy to forget — anyone
  writing a new extension call had to remember to wrap it. Result:
  fresh-clone init crashed twice on different missing names before
  the third release wrapped them all.
- Added `callExt(name, ...args)`, `awaitExt(name, ...args)`, and
  `bindExt(id, event, handlerName)` next to the existing `bind()`
  helper. Each looks the function up by name on `window` and
  silently returns `undefined` (or skips the binding) when the
  extension isn't installed.
- Migrated 21 call sites to the helpers — every previously
  `typeof`-guarded call to `loadAgents`, `renderAgentsPane`,
  `renderPaneAdmin`, `renderAgentSelectors`, `populateRunAgentFilter`,
  `populateTaskAgentSelect`, `loadAgentWorkflows`, `searchRuns`,
  `loadTasks`, `loadCostSummary`, `loadHooks`, `loadConductor`,
  `loadNotifications`, `saveAgentConfig`, `removeAgentConfig`,
  `closeAgentSteps`, `createTask`, `saveWorkflowEditor`,
  `clearWorkflowEditor`, `saveHooks`, `resetHooks`, `saveConductor`,
  `setAgentStatus`, `agentFieldMap`, and `enforceAgentConstraint`.
- Adding a new extension call is now `callExt("foo")` or
  `bindExt("btn-id", "click", "foo")`; review picks up the
  pattern at a glance.

### `SessionSummary` dataclass in `lib/server.py`

- `_session_summary()` previously returned `tuple[list[dict], bool]`.
  The 0.7.1.5 banner work added the second tuple element; the next
  flag (e.g. "tmux server upgrading") would mutate the signature
  again and force every caller and test to update positionally.
- Wrap the return in a small `SessionSummary` dataclass with named
  fields (`rows`, `tmux_unreachable`). Sole caller updated to
  destructure by name. JSON shape unchanged.

### Misc

- 601/601 tests still passing — pure refactor, no new tests
  required.

## 0.7.1.6 — Prerequisite check, fail-fast preflight, install script (2026-04-26)

A fresh-clone install on a host without `ttyd` (or `tmux`) used to
fail mid-flight: `tmux_browse.py serve` started, the dashboard
loaded, then expanding any pane returned the buried "ttyd binary
not found" error. New machines hit this first thing. Surface it
upfront and offer a one-shot installer.

### `tmux-browse doctor`

- `lib/doctor.py` runs a stdlib-only check for tmux and ttyd:
  resolves the binary path, captures the `--version` line, and
  emits a per-host install hint (apt / dnf / yum / pacman /
  zypper / apk / brew / port / pkg) for anything missing. The
  ttyd check prefers the bundled `~/.local/bin/ttyd` over `$PATH`
  so the dashboard sees the same binary `lib/ttyd.py` will spawn.
- `tmux-browse doctor` prints the report and exits 0 when both
  prereqs are present, 8 (`ESTATE`) when something's missing.

### `serve` preflight

- `tmux_browse.py serve` calls `doctor.check()` before binding the
  socket. If anything required is missing it prints the failing
  rows + remediation hint and exits 8 instead of starting a
  half-broken dashboard. Pass `--skip-checks` to override (useful
  in container builds that install ttyd later).

### `bin/install-prereqs.sh`

- One-shot installer that detects the host package manager,
  installs tmux from it (with `sudo` when needed, never
  silently), then runs the bundled `install-ttyd` for the ttyd
  static binary, then re-runs `doctor` to verify. Idempotent —
  re-running after a partial success skips what's already
  installed. Every command it runs is printed first.

### Tests

- `tests/test_doctor.py` covers nine cases: missing tmux,
  present tmux returning a version, ttyd missing when neither
  `~/.local/bin/ttyd` nor `$PATH` has it, ttyd preferring the
  bundled path, the `required_missing` filter, the `format_table`
  hint inclusion, and the apt / brew / no-manager hint
  detection. Full suite: 601 tests green (was 592).

### Docs

- `README.md` Install section leads with `bin/install-prereqs.sh`
  and documents the new `doctor` verb + `--skip-checks` flag.
- Layout reflects the two new files (`lib/doctor.py`,
  `bin/install-prereqs.sh`).

## 0.7.1.5 — Fresh-clone init fixes + tmux-unreachable banner (2026-04-26)

Patch release on top of 0.7.1.4. Three init crashes that surfaced
on a brand-new clone with no extensions installed are fixed; a new
banner replaces the silent "0 sessions" mode the dashboard fell into
when tmux's socket existed but the server had stopped responding;
and the core docs are slimmed to point at the extension repos
instead of inlining their surface. No public API or extension
contract changes.

### Fresh-clone init no longer crashes without the agent extension

- `static/panes.js` referenced four agent-extension button IDs
  (`hooks-save-btn`, `hooks-reset-btn`, `conductor-save-btn`,
  `conductor-reload-btn`) and 11 agent-extension-only init helpers
  (`renderAgentSelectors`, `loadAgents`, `populateRunAgentFilter`,
  `populateTaskAgentSelect`, `loadAgentWorkflows`, `searchRuns`,
  `loadTasks`, `loadCostSummary`, `loadHooks`, `loadConductor`,
  `loadNotifications`) directly. On a fresh clone without the
  agent extension installed those identifiers do not exist —
  `getElementById` returned `null`, the helpers threw
  `ReferenceError`, and the `DOMContentLoaded` handler aborted
  partway through. Refresh, idle polling, and client tracking
  never wired up; users saw a half-bootstrapped dashboard with
  none of the JS-driven affordances working.
- `refresh()` had the same problem with `renderAgentsPane()` and
  `renderPaneAdmin()` — the `count` text was the only update that
  survived each refresh tick.
- All such call sites now go through the existing null-safe
  `bind()` helper or a `typeof X === "function"` guard. Healthy
  installs (with or without the agent extension) behave exactly
  as before.

### "tmux server unreachable" banner

- When tmux's socket file exists but the server isn't responding
  (memory pressure, stuck client, OOM-killed worker), every
  `/api/sessions` request used to eat its full subprocess
  timeout and ultimately render "0 sessions". Operators chased
  ghosts in the dashboard code instead of looking at tmux.
- `lib/sessions.py::server_responsive()` adds a cheap
  `tmux display-message` probe with a 2 s timeout.
  `server_running()` and `list_sessions()` now treat
  `subprocess.TimeoutExpired` as "no usable server" instead of
  raising, so a hung server can't take down `/api/sessions`.
- `lib/server.py::_session_summary()` probes first; on failure
  it short-circuits the heavier `list-sessions` calls, returns
  `(rows, tmux_unreachable=True)`, and `/api/sessions` exposes
  the flag. Raw-shell rows still render — their state lives in
  the port registry, not tmux. `ensure_logging_all()` is wrapped
  best-effort so a single pipe-pane hiccup can't fail the
  request.
- `static/panes.js::showTmuxUnreachableBanner()` injects a
  top-of-page banner whenever `tmux_unreachable` is true and
  hides it when tmux comes back. Healthy-case JSON shape is
  unchanged for consumers that don't care about the flag.

### Core docs slimmed to link out to extension repos

- The README's ~80-line "Built-in agent platform" section is
  replaced with a 12-line "Optional extensions" table covering
  agent / qr / sandbox.
- `README.md`'s Layout section is refreshed — the listed
  `lib/agent_*.py` and `lib/qr.py` files no longer live in
  core; agent code moved to `extensions/agent/` in 0.7.1.
- `docs/dashboard.md`: the **Agents / Runs / Tasks** sections
  collapse to one pointer paragraph, the agent endpoint table
  becomes a one-line pointer, and the per-extension state-file
  enumeration is replaced with a single bullet noting that
  extensions write under `~/.tmux-browse/`.
- `docs/tb.md`: the ~200-line `tb agent ...` reference (subverbs,
  REPL slash-commands, sandbox modes) collapses to a 10-line
  pointer to `tmux-browse-agent`.
- Net result: -393 lines from core docs, with readers now
  routed to each extension repo for depth instead of reading
  duplicated content drifting from upstream.

Full suite: 592 tests green.

## 0.7.1.4 — Inline raw shells, fit-to-iframe controls, send-bar repeater (2026-04-26)

Round of dashboard polish on top of 0.7.1.3. No extension contract
changes — agent / sandbox / qr submodule pins are unchanged; this
release is core-only.

### Top-level launcher

- New `./tmux-browse` shell script in the repo root. Runs the
  dashboard with no args (same as `python3 tmux_browse.py serve`)
  and forwards everything else to the existing CLI surface
  (`./tmux-browse list`, `./tmux-browse install-ttyd`, etc.).
  Resolves its own directory so a symlink in `~/.local/bin` works.

### Raw ttyd shells become first-class panes

- Clicking **Raw ttyd** previously navigated the browser to a
  separate `/raw-ttyd?...` wrapper page. The shell now renders
  inline as a regular pane in the session list, with the same
  drag-to-reorder, ▲/▼ move buttons, snap-left/snap-right split
  affordance, and `×` close button (routed to `/api/ttyd/stop`
  instead of `tmux kill-session`). Display label is `shell ·
  raw-shell-<uid>`; the underlying name format is unchanged.
- `start_raw` now persists the port via `ports.assign(name)` so
  the shell survives a page reload. `ttyd.stop` releases the port
  for `raw-shell-*` names; `gc_orphans` keeps live raw-shell
  assignments off the prune list.
- `_sessions_payload` walks the port registry for `raw-shell-*`
  entries with a live pidfile and emits them with `kind: "raw"`.
  Tmux sessions get `kind: "tmux"`. CSS hides the tmux-only
  summary controls (Idle Alert, Log, Scroll, Hide, send bar,
  phone keys, footer) on raw-shell rows.
- The legacy `/raw-ttyd` wrapper route + `render_raw_ttyd`
  template function are gone. Bookmarks to that URL now 404;
  relaunching from the dashboard is the path forward.

### Fit-to-iframe + ±W / ±H step buttons

- The window-chrome row gains a fit-to-iframe icon (corner
  arrows) that runs `tmux resize-window` with both `-x cols` and
  `-y rows` derived from the iframe's actual pixel dimensions.
  The maximize square now stretches the wrapper to 90vh **and**
  refits tmux on the next animation frame; the embedded terminal
  visibly reflows to fill its container instead of leaving a
  gutter.
- New `±W` / `±H` step buttons sit left of the fit icon. Each
  click adjusts the iframe's pixel size (80 px width, 60 px
  height per step) and re-fits tmux. `+w` / `+h` ship visible by
  default; `-w` / `-h` ship hidden. All four are individually
  toggleable via Config > Expanded Pane > window controls.
- `lib/dashboard_config.py` adds `ttyd_cell_width_px` (default
  7.7) and `ttyd_cell_height_px` (default 17) so operators on
  different fonts / browser zoom can tune the fit calculation.
  The inline status message reports the actual numbers used:
  e.g. `tmux 154×38 (iframe 1188×648px, cell 7.7×17px)`.
- The redundant summary-row pane-zoom icon (`wc-zoom-icon`,
  triggered `resize-pane -Z` — a no-op on single-pane windows)
  is removed; same SVG, less-useful primitive.
- `/api/session/resize` now accepts an optional `rows` parameter
  alongside `cols` and emits `-y rows` to `tmux resize-window`
  when present. Bounds: cols ∈ [20, 500], rows ∈ [5, 200].

### Send-bar repeater

- The send bar gets a number input (default 1, max 99) next to
  the Send button. Bump it past 1: the first send fires
  immediately, the rest queue. Each queued send waits for the
  pane's `idle_seconds` to cross `hot_loop_idle_seconds`, holds
  for a 60s cooldown, re-checks idle right before firing, then
  posts. Inline status reports queue position (`waiting for
  idle`, `idle, Ns cooldown`, `sending…`).
- `checkSendQueue(rows)` runs each refresh tick; pane reactivation
  during cooldown restarts the clock so a busy pane isn't
  interrupted by a stray send.

### Restart banner correctness

- The restart banner used to render visible at all times — the
  CSS rule had `display: flex` unconditionally, beating the HTML5
  `hidden` attribute. JS toggling `node.hidden` had no visual
  effect; the Dismiss button appeared dead; "Restart the dashboard
  to activate 0 newly enabled extensions" rendered when nothing
  was pending. Constrain the flex layout to `:not([hidden])` and
  trust the server's `restart_pending` count on every refresh
  rather than incrementing a local cumulative counter.

### Log auto-scroll-to-bottom

- `/api/session/log?html=1` returns a minimal HTML wrapper that
  scrolls the buffer to the bottom on load. Both the core
  dashboard's per-pane Log button and the agent extension's
  per-agent Log button pass the flag; scripted callers without
  `html=1` keep the unchanged `text/plain` response.

### Other fixes from the post-split review

- `_h_tasks_launch` now refuses with HTTP 409 when the agent
  extension isn't enabled (instead of silently spawning a tmux
  session running the unknown verb `tb agent`).
- `lib/server.py` and `lib/sessions.py` lose two dead imports
  (`UsageError`, `parse`).
- `static/panes.js` init now uses a null-safe `bind()` helper for
  every binding that targets agent-extension-only DOM IDs or
  handlers — without this, a no-extensions install would crash
  mid-init and leave the dashboard half-bootstrapped.
- `/api/extensions/update` gains four endpoint-level tests
  (missing name → 400, UpdateError surfaces stage,
  changed=true signals restart, unchanged version skips it). The
  route-table assertion now lists the update endpoint.
- Stale doc references cleaned up across `docs/architecture.md`,
  `docs/dashboard.md`, `docs/tb.md`, and `README.md` — module
  layout reflects the post-split reality, the HTTP API table is
  split into core / agent / qr sections, and `/api/tasks` POST
  body shape matches what the server actually accepts.

Full suite: 592 tests green.

## 0.7.1.3 — Docker sandbox + QR sharing carved out; lib lean pass (2026-04-24)

Three modules leave core, in keeping with the E0-E4 extension
pattern:

- **`lib/worktrees.py` → `tmux-browse-agent/agent/worktrees.py`** at
  v0.7.2-agent. Agent-only helper; `lib/tasks.py` no longer creates
  git worktrees — it stores `worktree_path` / `branch` as opaque
  strings and leaves lifecycle to whoever created them.
- **`lib/docker_sandbox.py` → new
  [`tmux-browse-sandbox`](https://github.com/itsmygithubacct/tmux-browse-sandbox)
  repo** at v0.7.2-sandbox. Library-only extension; the loader
  prepends every enabled extension's dir to `sys.path` before
  any `load_one()` runs, so the agent extension just does
  `import sandbox as docker_sandbox`.
- **`lib/qr.py` + `/api/qr` + Show QR / Read QR buttons + scanner
  modal → new
  [`tmux-browse-qr`](https://github.com/itsmygithubacct/tmux-browse-qr)
  repo** at v0.7.2-qr. Fills two new slots
  (`config_actions_extras`, `qr_modal`) via the extension loader.

### Catalog

`KNOWN` in `lib/extensions/catalog.py` now lists all three:
`agent` (at v0.7.2-agent), `sandbox` (v0.7.2-sandbox), `qr` (v0.7.2-qr).
Install via the Config pane or the Makefile.

### Loader changes

- Library-only extensions are explicitly supported. A manifest
  with no entry points validates fine; the loader still prepends
  its dir to `sys.path`, which is the whole point.
- `load_enabled()` now does a two-pass dance: first it prepends
  every enabled extension to `sys.path`, then it calls
  `load_one()` on each. Cross-extension imports (e.g.
  `agent.tool_registry` importing from `sandbox`) resolve at
  module-load time regardless of alphabetical discovery order.
- `scripts/preflight.py` generalises from agent-only to catalog-
  driven: it runs the four version-alignment checks against every
  entry in `KNOWN` and exits non-zero on any mismatch.
- `tests/test_extension_agent_tests.py` now walks every installed
  submodule under `extensions/` and loads their test files via
  `importlib.util.spec_from_file_location` with uniquified module
  names — avoids the `tests` package-name collision that
  `unittest.discover` would otherwise hit between core's implicit
  namespace package and each extension's explicit one.

### Net diff in core

~915 lines leave `lib/` (docker_sandbox + qr + worktrees source, plus their
tests). `lib/tasks.py` loses the worktree-creation path but keeps
the same on-disk schema. `lib/server.py` loses one import, one
handler, one route entry. `lib/templates.py` adds two slots and
drops the QR modal + buttons. `static/sharing.js` loses the
Show/Read QR functions. `static/panes.js` loses three event
bindings.

### Migration

Existing installs: `git submodule update --init --recursive` brings
in the new submodules. Users who had Docker sandbox agents or QR
config share enabled will need to click **Config → Extensions →
Enable** on each of `sandbox` and `qr`; the agent extension's
Docker-mode code lazy-imports sandbox, so a Docker-agent run on an
install without the sandbox extension enabled raises at tool-call
time with a clear ImportError message.

Full suite: 586 tests green.

### CI + preflight (landed alongside the carves)

- `.github/workflows/ci.yml` — core now has CI. Checks out with
  submodules recursive, installs tmux, runs `make preflight` then
  `make test`.
- `scripts/preflight.py` — catalog-driven. Four checks per
  submodule: populated, pinned_ref matches tag, core satisfies
  min_tmux_browse, manifest version matches tag. Exit 1 on any
  mismatch; grep-friendly `FAIL: <ext>/<check>: <msg>` lines on
  stderr.
- `make preflight` and `make ci` wrap the script.
- `tests/test_preflight.py` — cases for each check, passing and
  failing.

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
