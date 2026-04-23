# tmux-browse

Two ways to look at your tmux sessions:

1. **A web dashboard** — every local tmux session shown as a collapsible pane
   with an embedded [ttyd][ttyd] terminal. Launch, open in a tab, scroll back,
   hide, reorder, kill.
2. **`tb`, a CLI** — read, write, create, and exit tmux sessions from the
   shell or from an LLM tool-use loop. Tables for humans, stable JSON for
   machines.

Both share the same Python library. Stdlib-only (`http.server`, `urllib`,
`subprocess`, `ssl`) — no pip dependencies; the only external is `ttyd`
itself, which the CLI can install for you.

![tmux-browse dashboard](tmux_browse.png)

[ttyd]: https://github.com/tsl0922/ttyd

## Install

Prerequisites:

- `python3`
- `tmux`
- `ttyd` on `$PATH`, or let `install-ttyd` fetch it into `~/.local/bin`

```bash
# One-time: fetch the ttyd static binary into ~/.local/bin
python3 tmux_browse.py install-ttyd

# Run the dashboard
python3 tmux_browse.py serve         # → http://<host>:8096/

# Or use the CLI
python3 tb.py ls
python3 tb.py exec work --json -- pytest -q
```

`install-ttyd` is only needed where `ttyd` isn't already on `$PATH`. If your
distro packages it (Debian/Ubuntu `apt install ttyd`, Homebrew `brew install
ttyd`), that works too.

## Quick Start

If you want to try it immediately, create a throwaway tmux session first:

```bash
# Create a scratch session
python3 tb.py new demo

# Run a command inside it
python3 tb.py exec demo --json -- pwd

# Start the dashboard
python3 tmux_browse.py serve
```

Then open `http://localhost:8096/` on the same machine. The dashboard is most
useful once at least one tmux session exists.

## Drive an agent from the terminal, watch it in the browser

![Driving a coding agent from one pane, output in another](tmux_browse_2.png)

Because `tb` exposes tmux as a CLI, an agent can use it as a tool: you run
the agent in one session and tell it to drive a coding session (claude,
codex, aider, …) in another, pinning the build/test output to a third.
Each session is its own pane in the dashboard, so you watch the whole
pipeline from a second monitor or your phone.

```bash
# Three sessions: the agent, the coding session it drives, the output pane
tb new agent
tb new coder
tb new website_terminal

# Start a coding agent in "coder" and a long-running build in "website_terminal"
tb type coder "claude"
tb type website_terminal "npm run dev"

# Kick off the orchestrating agent and give it the targets as instructions
tb type agent "gpt"
tb type agent "drive 'coder' to add a /health endpoint; surface build output in 'website_terminal'"
```

The agent uses `tb type coder "..."` to prompt the coding session and
`tb capture website_terminal` to read back what the build produced —
everything stays visible in the dashboard the whole time.

See [docs/recipes.md](docs/recipes.md) for the full LLM tool-use pattern
(`snapshot` → `exec` + `wait` → `capture`).

## Same sessions, any device on your LAN

The dashboard binds `0.0.0.0` by default, so every terminal you see in the
browser is **the real tmux session on the host** — not a copy. Open the same
URL from another device on the LAN and you're attached to the exact same
panes. Close your laptop, pick it up on your phone, keep typing.

```bash
# On the host running tmux (e.g. your workstation or a Raspberry Pi)
python3 tmux_browse.py serve               # → :8096 on every interface

# Find the host's LAN IP
ip -4 addr show | awk '/inet / && !/127\./ {print $2}' | cut -d/ -f1
```

Then on any other device on the same LAN:

- **Phone / tablet:** open `http://<host-ip>:8096/` in the browser. Each
  session pane embeds a full ttyd terminal — tap into one and type; the
  keystrokes land on the host's tmux server, not a snapshot. Pinch-zoom,
  swipe between panes, copy/paste all work.
- **Another laptop or PC:** same URL. Multiple people (or the same person
  across devices) can watch and drive the same session simultaneously — tmux
  already handles the multi-client attach; ttyd just forwards a browser
  socket to the attach.

Because everything stays on the host, your devices don't need any local
state: no ssh keys, no tmux config, no shell history. The phone in your
pocket is just a window onto the workstation.

### Before exposing on a LAN

The default build is **unauthenticated plaintext HTTP**. Anyone on the
network segment can open any of your tmux panes. Turn on both gates
before using this outside of a trusted single-user LAN:

```bash
# Generate a self-signed cert (one-off) + pick a token
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
    -keyout key.pem -out cert.pem -subj "/CN=$(hostname)"
TOKEN=$(openssl rand -hex 24)

# Serve with TLS + auth
python3 tmux_browse.py serve --cert cert.pem --key key.pem --auth "$TOKEN"
# → https://<host-ip>:8096/?token=<TOKEN> from any device
```

Phones will warn about the self-signed cert — accept once and it's pinned.
For a stricter setup (public network, multiple users, untrusted devices),
front the dashboard with an authenticating reverse proxy or reach it over
a VPN / SSH port-forward instead.

## Ports

| Thing | Port(s) |
|---|---|
| Dashboard | `8096` (override with `--port`) |
| Per-session ttyd | `7700–7799` (100 slots) |

Change in `lib/config.py` if they clash with something on your machine.
By default both the dashboard and spawned ttyds are reachable on every
interface. `tmux_browse.py serve --bind 127.0.0.1` keeps both local-only;
other concrete bind addresses are mapped to the owning NIC when ttyd is
started.

## Documentation

- **[docs/dashboard.md](docs/dashboard.md)** — web dashboard: UI reference,
  HTTP API, reordering / hiding.
- **[docs/tb.md](docs/tb.md)** — the `tb` CLI: verbs, flags, exit codes,
  LLM-friendly patterns.
- **[docs/recipes.md](docs/recipes.md)** — cookbook of concrete human and
  agent recipes.
- **[docs/architecture.md](docs/architecture.md)** — why the project is
  shaped the way it is (stdlib-only, sentinel-based exec, ttyd wrapper
  lifecycle, port registry).
- **[CHANGELOG.md](CHANGELOG.md)** — version history.

## Security

The dashboard ships **unauthenticated and plaintext HTTP by default** —
anyone who can reach the port can open a terminal attached to any of your
tmux sessions, and traffic on the wire is readable.

Two opt-in gates ship in-box:

```bash
# Bearer-token auth
python3 tmux_browse.py serve --auth s3cr3t                  # or --auth-file, or $TMUX_BROWSE_TOKEN
python3 tmux_browse.py serve --auth-file ~/.tmux-browse-token   # first non-empty line = token

# TLS (BYO cert; the same cert/key are passed to every spawned ttyd)
python3 tmux_browse.py serve --cert cert.pem --key key.pem  # or $TMUX_BROWSE_CERT / $TMUX_BROWSE_KEY

# Both together
python3 tmux_browse.py serve --auth s3cr3t --cert cert.pem --key key.pem
```

A quick self-signed cert for LAN use:

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
    -keyout key.pem -out cert.pem -subj "/CN=localhost"
```

Auth guards the dashboard HTTP surface only; TLS covers both the dashboard
*and* every spawned ttyd on 7700–7799 (otherwise browsers would block the
iframe's `ws://` as mixed content). For a hardened perimeter, still prefer
an authenticating reverse proxy or SSH tunnel. See
[docs/dashboard.md](docs/dashboard.md#optional-authentication).

The dashboard UI also includes shared hot buttons, per-session idle alerts,
and a self-restart control; see [docs/dashboard.md](docs/dashboard.md) for the
current control layout and behavior.

## Layout

```
tmux-browse/
├── tmux_browse.py            # dashboard CLI
├── tb.py                     # tmux CLI for humans + LLMs
├── lib/
│   ├── config.py / ports.py / sessions.py / ttyd.py
│   ├── server.py / templates.py / static.py        # dashboard internals
│   ├── auth.py / tls.py                            # optional auth + HTTPS
│   ├── dashboard_config.py                         # saved dashboard settings
│   ├── agent_store.py / agent_providers.py        # agent config + wire adapters
│   ├── agent_runner.py / agent_runtime.py         # execution loop + session mgmt
│   ├── agent_logs.py / agent_run_index.py         # per-agent logs + searchable index
│   ├── agent_conversations.py                      # persistent REPL turn history
│   ├── agent_status.py                             # live status derivation
│   ├── agent_costs.py                              # per-run token tracking
│   ├── agent_runs.py                               # run_id + lifecycle constants
│   ├── agent_scheduler.py / agent_scheduler_lock.py  # background workflow engine
│   ├── agent_workflows.py / agent_workflow_runs.py   # workflow config + history
│   ├── tasks.py / worktrees.py                     # optional task/worktree mode
│   ├── ttyd_installer.py
│   ├── targeting.py / errors.py / output.py       # tb primitives
│   ├── exec_runner.py                             # tb exec strategies
│   └── tb_cmds/                                   # one module per verb group
│       ├── agent.py                               # tb agent subcommands
│       ├── web.py / bulk.py / lifecycle.py
│       └── read.py / write.py / observe.py
├── static/
│   ├── app.css / app.js / favicon.svg             # dashboard frontend assets
├── bin/
│   └── ttyd_wrap.sh          # attach-only wrapper (exits on tty drop)
├── tests/                    # 304 stdlib unittest tests
├── docs/
│   ├── dashboard.md
│   ├── tb.md
│   ├── recipes.md
│   └── architecture.md
├── CHANGELOG.md
├── LICENSE
└── requirements_tmux_browse.txt   # intentionally unused; runtime is stdlib-only
```
