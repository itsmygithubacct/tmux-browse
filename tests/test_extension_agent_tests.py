"""Run ``extensions/agent/tests/`` from within the core test runner.

This is a loader shim. Until the agent extension moves out of the
monorepo (E2), its test suite lives under ``extensions/agent/tests/``
and core's ``python3 -m unittest discover tests`` must still pick them
up to keep CI green.

``load_tests`` is unittest's extensibility hook: the runner calls it
in place of default discovery for this module, and we return the
extension's test suite instead. When E2 ships, this file goes away.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_EXT = _REPO / "extensions" / "agent"
_EXT_TESTS = _EXT / "tests"


def load_tests(_loader: unittest.TestLoader, _tests, _pattern):
    if not _EXT_TESTS.is_dir():
        return unittest.TestSuite()
    # Both the repo root (so ``lib.*`` imports) and the extension root
    # (so ``server.routes`` / ``agent.*`` / ``tb_cmds.agent`` imports)
    # must be resolvable when the extension tests execute.
    for p in (_REPO, _EXT):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)
    # Use a fresh loader — discover() mutates ``_top_level_dir`` on the
    # one passed in, which would poison the outer walk that called us.
    inner = unittest.TestLoader()
    return inner.discover(
        start_dir=str(_EXT_TESTS),
        top_level_dir=str(_EXT),
    )
