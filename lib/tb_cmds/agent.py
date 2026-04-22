"""Agent verbs: add/list/remove/run LLM agents over tb.py."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .. import agent_runner, agent_store, dashboard_config, output
from ..errors import UsageError


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def _consume_common_flags(argv: list[str], args: argparse.Namespace) -> list[str]:
    """Honor shared flags even when users place them after `tb agent ...`.

    `tb.py` documents `--json`, `--quiet`, and `--no-header` as shared flags
    that work in any position. The top-level parser handles the forms before
    `agent`, so this pass peels them out of the nested remainder as well.
    """
    rest: list[str] = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--":
            rest.extend(argv[i:])
            break
        if token == "--json":
            args.json = True
        elif token in {"--quiet", "-q"}:
            args.quiet = True
        elif token == "--no-header":
            args.no_header = True
        else:
            rest.append(token)
        i += 1
    return rest


def _read_api_key(ns: argparse.Namespace) -> str:
    if getattr(ns, "api_key", None):
        return ns.api_key
    if getattr(ns, "api_key_stdin", False):
        data = sys.stdin.read().strip()
        if not data:
            raise UsageError("no API key received on stdin")
        return data
    raise UsageError("provide --api-key or --api-key-stdin")


def _parse_add(argv: list[str]) -> argparse.Namespace:
    p = _Parser(prog="tb agent add")
    p.add_argument("name")
    p.add_argument("--api-key")
    p.add_argument("--api-key-stdin", action="store_true")
    p.add_argument("--model")
    p.add_argument("--base-url")
    p.add_argument("--provider")
    p.add_argument("--wire-api")
    return p.parse_args(argv)


def _parse_remove(argv: list[str]) -> argparse.Namespace:
    p = _Parser(prog="tb agent remove")
    p.add_argument("name")
    return p.parse_args(argv)


def _parse_run(name: str, argv: list[str]) -> argparse.Namespace:
    p = _Parser(prog=f"tb agent {name}")
    p.add_argument("prompt", nargs="+")
    p.add_argument("--steps", type=int, default=None)
    p.add_argument("--timeout", type=float, default=90.0)
    return p.parse_args(argv)


def _default_agent_steps() -> int:
    return max(1, int(dashboard_config.load().get("agent_max_steps", 100)))


def _rows() -> list[dict]:
    rows = []
    for row in agent_store.list_agents():
        rows.append({
            "name": row["name"],
            "provider": row.get("provider", "-"),
            "model": row.get("model", "-"),
            "base_url": row.get("base_url", "-"),
            "key": "yes" if row.get("has_api_key") else "no",
        })
    return rows


def cmd_agent(args: argparse.Namespace) -> int:
    mode = (args.mode or "").strip()
    rest = _consume_common_flags(list(args.rest or []), args)
    if not mode:
        raise UsageError("usage: tb agent <name> <prompt...> | tb agent add|list|remove|defaults ...")

    if mode in {"list", "ls"}:
        rows = _rows()
        if args.json:
            output.emit_json({"agents": rows})
        elif not args.quiet:
            output.emit_table(
                rows,
                [("name", "NAME"), ("provider", "PROVIDER"), ("model", "MODEL"),
                 ("base_url", "BASE_URL"), ("key", "KEY")],
                no_header=args.no_header,
                empty_message="(no configured agents)",
            )
        return 0

    if mode == "defaults":
        rows = []
        for name, spec in sorted(agent_store.load_catalog().items()):
            rows.append({
                "name": name,
                "provider": spec["provider"],
                "model": spec["model"],
                "base_url": spec["base_url"],
            })
        if args.json:
            output.emit_json({"defaults": rows})
        elif not args.quiet:
            output.emit_table(
                rows,
                [("name", "NAME"), ("provider", "PROVIDER"), ("model", "MODEL"), ("base_url", "BASE_URL")],
                no_header=args.no_header,
            )
        return 0

    if mode == "add":
        ns = _parse_add(rest)
        row = agent_store.add_agent(
            ns.name,
            _read_api_key(ns),
            model=ns.model,
            base_url=ns.base_url,
            provider=ns.provider,
            wire_api=ns.wire_api,
        )
        if args.json:
            output.emit_json({"added": row})
        elif not args.quiet:
            print(
                f"added agent {row['name']} ({row['provider']} {row['model']}) "
                f"using {row['base_url']}",
            )
        return 0

    if mode in {"remove", "rm", "delete"}:
        ns = _parse_remove(rest)
        removed = agent_store.remove_agent(ns.name)
        if args.json:
            output.emit_json({"removed": removed, "name": ns.name})
        elif not args.quiet:
            print("removed" if removed else "not found")
        return 0

    run = _parse_run(mode, rest)
    agent = agent_store.get_agent(mode)
    repo_root = Path(__file__).resolve().parents[2]
    result = agent_runner.run_agent(
        agent,
        " ".join(run.prompt),
        repo_root=repo_root,
        max_steps=max(1, run.steps if run.steps is not None else _default_agent_steps()),
        request_timeout=max(5.0, run.timeout),
    )
    if args.json:
        output.emit_json(result)
    elif not args.quiet:
        print(result["message"])
    return 0


def register(sub, common) -> None:
    p = sub.add_parser(
        "agent",
        help="configure and run LLM agents that operate through tb.py",
        parents=[common],
    )
    p.add_argument("mode", nargs="?")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_agent)
