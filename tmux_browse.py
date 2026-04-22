#!/usr/bin/env python3
"""tmux-browse CLI.

Subcommands:
    serve          Run the dashboard HTTP server.
    list           Show tmux sessions and ttyd state.
    ports          Show the session → port registry.
    start <name>   Ensure a ttyd is running for a session.
    stop <name>    Stop the ttyd for a session.
    cleanup        Stop every managed ttyd.
    install-ttyd   Download the ttyd static binary into ~/.local/bin.
    status         Combined status view (sessions + ttyds + port budget).
    config         Inspect or modify dashboard config file.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib import (
    auth,
    config,
    dashboard_config,
    ports,
    server,
    sessions,
    tls,
    ttyd,
    ttyd_installer,
)
from lib.errors import TBError


def cmd_serve(args: argparse.Namespace) -> int:
    token = auth.load_token(cli_token=args.auth, cli_token_file=args.auth_file)
    tls_paths = tls.load_tls_paths(cli_cert=args.cert, cli_key=args.key)
    server.serve(
        bind=args.bind, port=args.port, verbose=args.verbose,
        expected_token=token, tls_paths=tls_paths,
    )
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    rows = sessions.list_sessions()
    assignments = ports.all_assignments()
    if not rows:
        print("(no tmux sessions)")
        return 0
    print(f"{'SESSION':<24} {'WIN':>4} {'ATT':>4} {'PORT':>6} {'TTYD':<8} {'IDLE':>8}")
    now = int(time.time())
    for s in rows:
        port = assignments.get(s["name"])
        running = "running" if ttyd.read_pid(s["name"]) is not None else "-"
        idle_s = max(0, now - s["activity"])
        print(
            f"{s['name']:<24.24} {s['windows']:>4} {s['attached']:>4} "
            f"{(port or '-'):>6} {running:<8} {idle_s:>7}s",
        )
    return 0


def cmd_ports(args: argparse.Namespace) -> int:
    if args.prune:
        active = {s["name"] for s in sessions.list_sessions()}
        dropped = ports.prune(active)
        if dropped:
            print(f"dropped {len(dropped)} stale assignment(s): {', '.join(dropped)}")
        else:
            print("no stale assignments")
        return 0
    assignments = ports.all_assignments()
    if not assignments:
        print(f"(no assignments yet — range {config.TTYD_PORT_START}-{config.TTYD_PORT_END})")
        return 0
    for name, port in sorted(assignments.items(), key=lambda kv: kv[1]):
        print(f"{port:>5}  {name}")
    total = config.TTYD_PORT_END - config.TTYD_PORT_START + 1
    print(f"\n{len(assignments)}/{total} ports assigned")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    if not sessions.exists(args.session):
        print(f"error: no tmux session named '{args.session}'", file=sys.stderr)
        return 1
    tls_paths = tls.load_tls_paths(cli_cert=args.cert, cli_key=args.key)
    r = ttyd.start(args.session, tls_paths=tls_paths, bind_addr=args.bind)
    if not r.get("ok"):
        print(f"error: {r.get('error')}", file=sys.stderr)
        return 1
    if r.get("already"):
        print(f"already running on port {r.get('port')} (pid {r.get('pid', '?')})")
    else:
        print(f"started on port {r.get('port')} (pid {r.get('pid')})")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    r = ttyd.stop(args.session)
    if not r.get("ok"):
        print(f"error: {r.get('error')}", file=sys.stderr)
        return 1
    if r.get("already_stopped"):
        print("not running")
    else:
        print(f"stopped (pid {r.get('pid')})")
    return 0


def cmd_cleanup(_args: argparse.Namespace) -> int:
    n = ttyd.stop_all()
    print(f"stopped {n} ttyd process(es)")
    return 0


def cmd_install_ttyd(args: argparse.Namespace) -> int:
    r = ttyd_installer.install(force=args.force)
    if not r.get("ok"):
        print(f"error: {r.get('error')}", file=sys.stderr)
        return 1
    path = r.get("path")
    if r.get("note"):
        print(f"{path}: {r['note']}")
    else:
        print(f"installed ttyd {r.get('version')} → {path}")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    svc_sessions = sessions.list_sessions()
    ttyd_rows = ttyd.status_all()
    print(f"tmux sessions: {len(svc_sessions)}")
    for s in svc_sessions:
        print(f"  - {s['name']} ({s['windows']}w, {s['attached']} attached)")
    if not svc_sessions:
        print("  (none)")
    print()
    running = [r for r in ttyd_rows if r["running"]]
    print(f"managed ttyds running: {len(running)}")
    for r in ttyd_rows:
        marker = "●" if r["running"] else "○"
        print(f"  {marker} {r['session']:<24} port={r['port'] or '-'}  pid={r['pid'] or '-'}")
    if not ttyd_rows:
        print("  (none)")
    print()
    total = config.TTYD_PORT_END - config.TTYD_PORT_START + 1
    print(f"ports assigned: {len(ports.all_assignments())}/{total}")
    ttyd_path = config.ttyd_executable()
    print(f"ttyd binary:    {ttyd_path}")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    if args.reset and args.set:
        print("error: --reset cannot be combined with --set", file=sys.stderr)
        return 2
    if args.reset:
        cfg = dashboard_config.save(dashboard_config.DEFAULTS)
    elif args.set:
        cfg = dashboard_config.load()
        pending = dict(cfg)
        valid_keys = set(dashboard_config.DEFAULTS.keys())
        for item in args.set:
            if "=" not in item:
                print(f"error: invalid --set '{item}' (expected key=value)", file=sys.stderr)
                return 2
            key, value = item.split("=", 1)
            key = key.strip()
            if key not in valid_keys:
                print(f"error: unknown config key '{key}'", file=sys.stderr)
                return 2
            pending[key] = value.strip()
        cfg = dashboard_config.save(pending)
    else:
        cfg = dashboard_config.load()

    if args.json:
        print(json.dumps({
            "path": str(config.DASHBOARD_CONFIG_FILE),
            "config": cfg,
        }, indent=2, sort_keys=True))
        return 0

    print(config.DASHBOARD_CONFIG_FILE)
    for key in sorted(cfg):
        print(f"{key:<28} {cfg[key]}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tmux-browse", description=__doc__.strip().splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s_serve = sub.add_parser("serve", help="run the dashboard HTTP server")
    s_serve.add_argument("--port", type=int, default=config.DASHBOARD_PORT,
                         help=f"dashboard port (default {config.DASHBOARD_PORT})")
    s_serve.add_argument("--bind", default="0.0.0.0", help="bind address (default 0.0.0.0)")
    s_serve.add_argument("-v", "--verbose", action="store_true", help="log every request")
    s_serve.add_argument("--auth", metavar="TOKEN", default=None,
                         help="require Bearer token for every request. "
                              "Default off. Also honours $TMUX_BROWSE_TOKEN and "
                              "--auth-file.")
    s_serve.add_argument("--auth-file", metavar="PATH", default=None,
                         help="read token from this file (first non-empty line)")
    s_serve.add_argument("--cert", metavar="PATH", default=None,
                         help="TLS certificate (PEM). Also honours $TMUX_BROWSE_CERT. "
                              "When set, --key is required too, and spawned ttyds "
                              "inherit the same cert/key.")
    s_serve.add_argument("--key", metavar="PATH", default=None,
                         help="TLS private key (PEM). Also honours $TMUX_BROWSE_KEY.")
    s_serve.set_defaults(func=cmd_serve)

    s_list = sub.add_parser("list", help="show tmux sessions and ttyd state")
    s_list.set_defaults(func=cmd_list)

    s_ports = sub.add_parser("ports", help="show the port registry")
    s_ports.add_argument("--prune", action="store_true",
                         help="drop assignments whose tmux session no longer exists")
    s_ports.set_defaults(func=cmd_ports)

    s_start = sub.add_parser("start", help="start ttyd for a tmux session")
    s_start.add_argument("session")
    s_start.add_argument("--bind", default="0.0.0.0",
                         help="bind ttyd to the dashboard address (default 0.0.0.0)")
    s_start.add_argument("--cert", metavar="PATH", default=None,
                         help="TLS cert for ttyd (--ssl). Also honours $TMUX_BROWSE_CERT.")
    s_start.add_argument("--key", metavar="PATH", default=None,
                         help="TLS key for ttyd (--ssl). Also honours $TMUX_BROWSE_KEY.")
    s_start.set_defaults(func=cmd_start)

    s_stop = sub.add_parser("stop", help="stop ttyd for a tmux session")
    s_stop.add_argument("session")
    s_stop.set_defaults(func=cmd_stop)

    s_cleanup = sub.add_parser("cleanup", help="stop every managed ttyd")
    s_cleanup.set_defaults(func=cmd_cleanup)

    s_install = sub.add_parser("install-ttyd",
                               help="download the ttyd static binary into ~/.local/bin")
    s_install.add_argument("--force", action="store_true", help="reinstall even if present")
    s_install.set_defaults(func=cmd_install_ttyd)

    s_status = sub.add_parser("status", help="combined status view")
    s_status.set_defaults(func=cmd_status)

    s_config = sub.add_parser("config", help="inspect or modify dashboard config")
    s_config.add_argument("--json", action="store_true", help="print config as JSON")
    s_config.add_argument("--reset", action="store_true", help="reset config file to defaults")
    s_config.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                          help="set a config value and save (may be repeated)")
    s_config.set_defaults(func=cmd_config)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except TBError as e:
        print(f"tmux-browse: {e.message}", file=sys.stderr)
        return e.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
