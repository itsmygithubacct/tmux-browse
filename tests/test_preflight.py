"""scripts/preflight.py — catalog-driven version alignment check.

Exercises ``check_one`` against a tmpdir fixture standing in for a
catalog entry's submodule. The real-world pass/fail is also
covered by ``make preflight`` in CI.
"""

from __future__ import annotations

import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import preflight  # noqa: E402


def _manifest(version: str, min_core: str) -> str:
    return json.dumps({
        "name": "sandbox", "version": version, "module": "sandbox",
        "min_tmux_browse": min_core,
    })


class CheckOneTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self._root = root
        self._patch = mock.patch.object(preflight, "REPO", root)
        self._patch.start()
        self._sub = root / "extensions" / "sandbox"
        self._sub.mkdir(parents=True)
        self._manifest_path = self._sub / "manifest.json"

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def _spec(self, pinned_ref: str = "v0.7.2-sandbox") -> dict:
        return {
            "submodule_path": "extensions/sandbox",
            "pinned_ref": pinned_ref,
        }

    def test_missing_manifest_returns_false(self):
        with mock.patch.object(preflight, "_core_version", return_value="0.7.1.2"):
            self.assertFalse(preflight.check_one("sandbox", self._spec()))

    def test_happy_path_passes(self):
        self._manifest_path.write_text(_manifest("0.7.2", "0.7.1"))
        git_ret = (0, "v0.7.2-sandbox", "")
        with mock.patch.object(preflight, "_git", return_value=git_ret), \
             mock.patch.object(preflight, "_core_version",
                               return_value="0.7.1.2"):
            self.assertTrue(preflight.check_one("sandbox", self._spec()))

    def test_pinned_ref_mismatch_fails(self):
        self._manifest_path.write_text(_manifest("0.7.2", "0.7.1"))
        # Submodule is at v0.7.1-sandbox but catalog says v0.7.2-sandbox.
        with mock.patch.object(preflight, "_git",
                               return_value=(0, "v0.7.1-sandbox", "")), \
             mock.patch.object(preflight, "_core_version",
                               return_value="0.7.1.2"):
            self.assertFalse(preflight.check_one("sandbox", self._spec()))

    def test_min_core_too_new_fails(self):
        self._manifest_path.write_text(_manifest("0.7.2", "9.9.9"))
        with mock.patch.object(preflight, "_git",
                               return_value=(0, "v0.7.2-sandbox", "")), \
             mock.patch.object(preflight, "_core_version",
                               return_value="0.7.1.2"):
            self.assertFalse(preflight.check_one("sandbox", self._spec()))

    def test_tag_and_manifest_version_mismatch_fails(self):
        # Tag says -0.7.2- but manifest says 0.7.1
        self._manifest_path.write_text(_manifest("0.7.1", "0.7.1"))
        with mock.patch.object(preflight, "_git",
                               return_value=(0, "v0.7.2-sandbox", "")), \
             mock.patch.object(preflight, "_core_version",
                               return_value="0.7.1.2"):
            self.assertFalse(preflight.check_one("sandbox", self._spec()))

    def test_non_matching_tag_format_fails(self):
        self._manifest_path.write_text(_manifest("0.7.2", "0.7.1"))
        with mock.patch.object(preflight, "_git",
                               return_value=(0, "random-tag", "")), \
             mock.patch.object(preflight, "_core_version",
                               return_value="0.7.1.2"):
            self.assertFalse(preflight.check_one("sandbox", self._spec()))


if __name__ == "__main__":
    unittest.main()
