"""Route-table integrity guards.

The dispatcher calls GET handlers as ``fn(handler, parsed)`` and POST
handlers as ``fn(handler, parsed, body)``. Two easy mistakes break that
contract silently until a request hits the route:

  * wiring a handler into the wrong table (arity mismatch -> TypeError
    500 at request time), and
  * defining an ``h_*`` handler but forgetting to wire it (dead code).

These tests catch both at import time.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import server_routes  # noqa: E402
from lib.server import Handler  # noqa: E402


def _positional_arity(fn) -> int:
    return len([p for p in inspect.signature(fn).parameters.values()
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])


def _defined_handlers():
    """Every ``h_*`` function defined directly in a server_routes module."""
    out = []
    for mod_info in pkgutil.iter_modules(server_routes.__path__):
        mod = importlib.import_module(f"lib.server_routes.{mod_info.name}")
        for name, obj in vars(mod).items():
            if (name.startswith("h_") and inspect.isfunction(obj)
                    and obj.__module__ == mod.__name__):
                out.append(obj)
    return out


class RouteArityTests(unittest.TestCase):

    def test_get_handlers_take_handler_and_parsed(self):
        for path, fn in Handler._GET_ROUTES.items():
            self.assertEqual(
                _positional_arity(fn), 2,
                f"GET {path} -> {fn.__name__} must take (handler, parsed)")

    def test_post_handlers_take_handler_parsed_body(self):
        for path, fn in Handler._POST_ROUTES.items():
            self.assertEqual(
                _positional_arity(fn), 3,
                f"POST {path} -> {fn.__name__} must take "
                "(handler, parsed, body)")


class RouteWiringTests(unittest.TestCase):

    def test_no_orphan_handlers(self):
        wired = set(Handler._GET_ROUTES.values()) | set(Handler._POST_ROUTES.values())
        orphans = [f"{fn.__module__}.{fn.__name__}"
                   for fn in _defined_handlers() if fn not in wired]
        self.assertEqual(
            orphans, [],
            "these h_* handlers are defined but not wired into a route "
            "table (dead code or a forgotten registration):\n"
            + "\n".join(orphans))

    def test_a_handler_is_not_wired_into_both_tables(self):
        # The same callable serving both GET and POST would receive a
        # different arg count per method — almost certainly a bug.
        both = set(Handler._GET_ROUTES.values()) & set(Handler._POST_ROUTES.values())
        self.assertEqual(both, set(),
                         f"handler(s) wired into both GET and POST: {both}")


if __name__ == "__main__":
    unittest.main()
