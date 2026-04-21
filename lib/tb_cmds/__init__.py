"""``tb`` CLI subcommand registry.

Each module in this package defines ``register(subparsers)`` that adds its
verbs to the shared argparse subparser set. The entry script (``tb.py``)
imports and calls them all.
"""

from __future__ import annotations

from .. import sessions, targeting
from ..errors import SessionNotFound, UsageError
from ..targeting import Target


def parse_target(expr: str) -> Target:
    """Parse a target expression, mapping ValueError → UsageError."""
    try:
        return targeting.parse(expr)
    except ValueError as e:
        raise UsageError(str(e))


def require_target(expr: str) -> Target:
    """Parse + validate existence. The standard preamble for target-taking verbs.

    Raises ``UsageError`` for malformed expressions and ``SessionNotFound``
    when the session doesn't exist — both map to stable exit codes.
    """
    t = parse_target(expr)
    if not sessions.exists(t.session):
        raise SessionNotFound(f"no such session: {t.session}")
    return t


from . import bulk, lifecycle, observe, read, web, write  # noqa: E402


def register_all(subparsers, common) -> None:
    read.register(subparsers, common)
    write.register(subparsers, common)
    lifecycle.register(subparsers, common)
    observe.register(subparsers, common)
    web.register(subparsers, common)
    bulk.register(subparsers, common)
