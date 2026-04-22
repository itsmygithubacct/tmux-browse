"""``tb`` CLI subcommand registry.

Each module in this package defines ``register(subparsers, common)`` that
adds its verbs to the shared argparse subparser set. ``tb.py`` imports
``register_all`` below and calls it once.

Shared helpers (``parse_target``, ``require_target``) live in ``_common``
and are re-exported here so existing ``from . import parse_target`` imports
inside submodules keep working.
"""

from __future__ import annotations

from . import agent, bulk, lifecycle, observe, read, web, write
from ._common import parse_target, require_target

__all__ = ["parse_target", "require_target", "register_all"]


def register_all(subparsers, common) -> None:
    read.register(subparsers, common)
    write.register(subparsers, common)
    lifecycle.register(subparsers, common)
    observe.register(subparsers, common)
    web.register(subparsers, common)
    bulk.register(subparsers, common)
    agent.register(subparsers, common)
