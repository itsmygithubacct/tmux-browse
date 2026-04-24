"""scripts/preflight.py catches each kind of cross-repo drift.

Rather than run the real script against a mocked filesystem — which
would require patching ``subprocess.run`` and a lot of paths — the
tests import the check functions and patch their dependencies
directly. The integration "does preflight actually exit 1 on a
broken tree" case is left to CI, which runs the real script.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import preflight  # noqa: E402


class _IsolatedRepoMixin:
    """Redirect preflight's REPO / SUBMODULE / MANIFEST paths to a temp."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self._submodule = root / "extensions" / "agent"
        self._manifest = self._submodule / "manifest.json"
        self._patches = [
            mock.patch.object(preflight, "REPO", root),
            mock.patch.object(preflight, "SUBMODULE", self._submodule),
            mock.patch.object(preflight, "MANIFEST", self._manifest),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def _populate(self, *, version: str = "0.7.1",
                  min_core: str = "0.7.1") -> None:
        self._submodule.mkdir(parents=True, exist_ok=True)
        self._manifest.write_text(json.dumps({
            "name": "agent",
            "version": version,
            "module": "agent",
            "min_tmux_browse": min_core,
        }))


class SubmodulePopulatedTests(_IsolatedRepoMixin, unittest.TestCase):

    def test_missing_manifest_fails(self):
        self.assertFalse(preflight.check_submodule_populated())

    def test_present_manifest_passes(self):
        self._populate()
        self.assertTrue(preflight.check_submodule_populated())


class PinnedRefMatchesCatalogTests(_IsolatedRepoMixin, unittest.TestCase):

    def _git_returns(self, tag: str, *, rc: int = 0):
        return (rc, tag, "")

    def test_catalog_and_submodule_agree(self):
        self._populate()
        catalog = {"agent": {"pinned_ref": "v0.7.1-agent"}}
        with mock.patch.object(preflight, "_git",
                               return_value=self._git_returns("v0.7.1-agent")), \
             mock.patch.dict(sys.modules, {}, clear=False), \
             mock.patch("lib.extensions.catalog.KNOWN", catalog):
            self.assertTrue(preflight.check_pinned_ref_matches_catalog())

    def test_mismatch_fails(self):
        self._populate()
        catalog = {"agent": {"pinned_ref": "v0.7.2-agent"}}
        with mock.patch.object(preflight, "_git",
                               return_value=self._git_returns("v0.7.1-agent")), \
             mock.patch("lib.extensions.catalog.KNOWN", catalog):
            self.assertFalse(preflight.check_pinned_ref_matches_catalog())

    def test_submodule_not_on_tag_fails(self):
        self._populate()
        catalog = {"agent": {"pinned_ref": "v0.7.1-agent"}}
        with mock.patch.object(preflight, "_git",
                               return_value=(128, "", "fatal: no tag")), \
             mock.patch("lib.extensions.catalog.KNOWN", catalog):
            self.assertFalse(preflight.check_pinned_ref_matches_catalog())


class CoreSatisfiesMinTests(_IsolatedRepoMixin, unittest.TestCase):

    def test_core_newer_than_required_passes(self):
        self._populate(min_core="0.7.0")
        with mock.patch("lib.__version__", "0.7.1.2"):
            self.assertTrue(preflight.check_core_satisfies_min())

    def test_core_equal_passes(self):
        self._populate(min_core="0.7.1")
        with mock.patch("lib.__version__", "0.7.1"):
            self.assertTrue(preflight.check_core_satisfies_min())

    def test_core_older_than_required_fails(self):
        self._populate(min_core="0.9.0")
        with mock.patch("lib.__version__", "0.7.1"):
            self.assertFalse(preflight.check_core_satisfies_min())


class ManifestVersionMatchesTagTests(_IsolatedRepoMixin, unittest.TestCase):

    def test_tag_and_manifest_match(self):
        self._populate(version="0.7.1")
        with mock.patch.object(preflight, "_git",
                               return_value=(0, "v0.7.1-agent", "")):
            self.assertTrue(preflight.check_manifest_version_matches_tag())

    def test_mismatch_fails(self):
        self._populate(version="0.7.0")
        with mock.patch.object(preflight, "_git",
                               return_value=(0, "v0.7.1-agent", "")):
            self.assertFalse(preflight.check_manifest_version_matches_tag())

    def test_non_matching_tag_format_fails(self):
        self._populate(version="0.7.1")
        with mock.patch.object(preflight, "_git",
                               return_value=(0, "random-tag", "")):
            self.assertFalse(preflight.check_manifest_version_matches_tag())


if __name__ == "__main__":
    unittest.main()
