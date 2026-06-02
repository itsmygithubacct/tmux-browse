"""ttyd binary installer — release-manifest SHA-256 verification."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import ttyd_installer  # noqa: E402


_BINARY = b"\x7fELF fake-ttyd-binary payload"
_BIN_SHA = hashlib.sha256(_BINARY).hexdigest()
_BIN_URL = "https://example.test/ttyd.x86_64"
_SUMS_URL = "https://example.test/SHA256SUMS"


def _release_json(include_sums: bool) -> bytes:
    assets = [{"name": "ttyd.x86_64", "browser_download_url": _BIN_URL}]
    if include_sums:
        assets.append({"name": "SHA256SUMS", "browser_download_url": _SUMS_URL})
    return json.dumps({"tag_name": "1.7.7", "assets": assets}).encode()


def _make_http_get(*, include_sums: bool, sums_hash: str):
    sums_body = (f"{sums_hash}  ttyd.x86_64\n"
                 f"{'0' * 64}  ttyd.aarch64\n").encode()

    def fake_http_get(url, accept="application/octet-stream"):
        if url == ttyd_installer.RELEASE_API:
            return _release_json(include_sums)
        if url == _BIN_URL:
            return _BINARY
        if url == _SUMS_URL:
            return sums_body
        raise AssertionError(f"unexpected URL: {url}")

    return fake_http_get


class TtydChecksumTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "ttyd"
        self._patches = [
            mock.patch.object(ttyd_installer.config, "TTYD_BIN", self.target),
            mock.patch.object(ttyd_installer.platform, "machine",
                              return_value="x86_64"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_matching_checksum_installs_and_reports_verified(self):
        with mock.patch.object(ttyd_installer, "_http_get",
                               _make_http_get(include_sums=True,
                                              sums_hash=_BIN_SHA)):
            r = ttyd_installer.install()
        self.assertTrue(r["ok"])
        self.assertTrue(r["sha256_verified"])
        self.assertEqual(r["sha256"], _BIN_SHA)
        self.assertTrue(self.target.is_file())
        self.assertEqual(self.target.read_bytes(), _BINARY)

    def test_mismatched_checksum_refuses_install(self):
        with mock.patch.object(ttyd_installer, "_http_get",
                               _make_http_get(include_sums=True,
                                              sums_hash="a" * 64)):
            r = ttyd_installer.install()
        self.assertFalse(r["ok"])
        self.assertIn("checksum mismatch", r["error"])
        # The bad binary must NOT be left on disk.
        self.assertFalse(self.target.exists())

    def test_missing_manifest_installs_but_flags_unverified(self):
        with mock.patch.object(ttyd_installer, "_http_get",
                               _make_http_get(include_sums=False,
                                              sums_hash=_BIN_SHA)):
            r = ttyd_installer.install()
        self.assertTrue(r["ok"])
        self.assertFalse(r["sha256_verified"])
        self.assertTrue(self.target.is_file())


if __name__ == "__main__":
    unittest.main()
