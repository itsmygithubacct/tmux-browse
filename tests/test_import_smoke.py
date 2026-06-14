"""Import smoke test: every main-repo module imports cleanly.

Catches circular imports, typos, and references to names removed during
refactoring (e.g. dead imports) before they surface at request time.
Only the dashboard repo's own modules are checked; the vendored
tmux-cli core and extension submodules have their own suites.
"""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "tmux-cli", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Modules that live in THIS repo's lib/ (not the merged-in submodule core).
_REPO_LIB = _ROOT / "lib"


def _repo_modules():
    mods = ["tmux_browse"]
    for py in sorted(_REPO_LIB.rglob("*.py")):
        if "__pycache__" in py.parts or py.name == "__init__.py":
            continue
        rel = py.relative_to(_ROOT).with_suffix("")
        mods.append(".".join(rel.parts))
    return mods


class ImportSmokeTests(unittest.TestCase):

    def test_repo_modules_import_cleanly(self):
        failures = []
        for name in _repo_modules():
            try:
                importlib.import_module(name)
            except Exception as exc:  # noqa: broad — reporting all at once
                failures.append(f"{name}: {exc!r}")
        self.assertEqual(failures, [],
                         "modules failed to import:\n" + "\n".join(failures))

    def test_finds_a_reasonable_module_set(self):
        # Guard the discovery itself — if globbing breaks we'd vacuously pass.
        mods = _repo_modules()
        self.assertIn("tmux_browse", mods)
        self.assertIn("lib.server", mods)
        self.assertGreater(len(mods), 10)


if __name__ == "__main__":
    unittest.main()
