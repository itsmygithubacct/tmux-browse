"""Build/repo hygiene guards.

- Every Makefile target with a recipe must be declared .PHONY. A
  non-phony target shadowed by a like-named file (e.g. a future `clean/`
  dir) silently won't run — a classic, hard-to-spot Make footgun.
- `make clean` actually removes a bytecode cache.
- .gitignore covers the caches so they can't be accidentally committed.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_MAKEFILE = _ROOT / "Makefile"
_GITIGNORE = _ROOT / ".gitignore"


def _makefile_targets(text: str) -> set[str]:
    targets = set()
    for line in text.splitlines():
        # A rule line: "name:" or "name: deps" at column 0 (not a variable
        # assignment, not an indented recipe line).
        m = re.match(r"^([a-zA-Z0-9_-]+)\s*:(?!=)", line)
        if m:
            targets.add(m.group(1))
    return targets


def _phony_targets(text: str) -> set[str]:
    # .PHONY may span multiple lines with trailing backslashes.
    names: set[str] = set()
    collecting = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(".PHONY:"):
            collecting = True
            stripped = stripped[len(".PHONY:"):]
        elif not collecting:
            continue
        cont = stripped.endswith("\\")
        names.update(stripped.rstrip("\\").split())
        if not cont:
            collecting = False
    return names


def _target_dependencies(text: str, target: str) -> set[str]:
    match = re.search(rf"^{re.escape(target)}\s*:\s*(.*)$", text,
                      flags=re.MULTILINE)
    return set(match.group(1).split()) if match else set()


class MakefilePhonyTests(unittest.TestCase):

    def setUp(self):
        self.text = _MAKEFILE.read_text(encoding="utf-8")

    def test_all_recipe_targets_are_phony(self):
        targets = _makefile_targets(self.text)
        phony = _phony_targets(self.text)
        missing = sorted(targets - phony)
        self.assertEqual(
            missing, [],
            f"these Makefile targets are not in .PHONY: {missing}")

    def test_clean_target_exists(self):
        self.assertIn("clean", _makefile_targets(self.text))

    def test_ci_runs_every_test_layer(self):
        self.assertEqual(
            _target_dependencies(self.text, "ci"),
            {"preflight", "test-core", "test", "test-extensions"},
        )


class MakeCleanBehaviourTests(unittest.TestCase):

    def test_make_clean_removes_pycache(self):
        make = shutil.which("make")
        if not make:
            self.skipTest("make not available")
        # Create a stray cache dir inside the repo, then clean it.
        marker_dir = _ROOT / "tests" / "__pycache__"
        marker = marker_dir / "_clean_probe.pyc"
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker.write_bytes(b"x")
        self.assertTrue(marker.exists())
        r = subprocess.run([make, "clean"], cwd=_ROOT,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(marker_dir.exists(),
                         "make clean should remove __pycache__ dirs")


class GitignoreTests(unittest.TestCase):

    def test_caches_are_ignored(self):
        text = _GITIGNORE.read_text(encoding="utf-8")
        for pat in ("__pycache__/", "*.pyc", ".pytest_cache/"):
            self.assertIn(pat, text, f"{pat} should be in .gitignore")


if __name__ == "__main__":
    unittest.main()
