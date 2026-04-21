# tmux-browse

Two ways to look at your tmux sessions:

1. **A web dashboard** — every local tmux session shown as a collapsible pane
   with an embedded [ttyd][ttyd] terminal. Launch, open in a tab, scroll back,
   hide, reorder, kill.
2. **`tb`, a CLI** — read, write, create, and exit tmux sessions from the
   shell or from an LLM tool-use loop. Tables for humans, stable JSON for
   machines.

Both share the same Python library. Stdlib-only (`http.server`, `urllib`,
`subprocess`) — no pip dependencies; the only external is `ttyd` itself,
which the CLI can install for you.

![tmux-browse dashboard](tmux_browse.png)

[ttyd]: https://github.com/tsl0922/ttyd

## Install

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

## Ports

| Thing | Port(s) |
|---|---|
| Dashboard | `8096` (override with `--port`) |
| Per-session ttyd | `7700–7799` (100 slots) |

Change in `lib/config.py` if they clash with something on your machine.

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
│   ├── ttyd_installer.py
│   ├── targeting.py / errors.py / output.py        # tb primitives
│   ├── exec_runner.py                              # tb exec strategies
│   └── tb_cmds/                                    # one module per verb group
├── bin/
│   └── ttyd_wrap.sh          # attach-only wrapper (exits on tty drop)
├── docs/
│   ├── dashboard.md
│   ├── tb.md
│   ├── recipes.md
│   └── architecture.md
├── CHANGELOG.md
└── requirements_tmux_browse.txt   # empty — stdlib only
```
