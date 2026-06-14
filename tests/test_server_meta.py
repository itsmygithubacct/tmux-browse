"""Static-asset meta routes: correct serving + graceful 404 on a
missing asset (instead of an opaque 500), and PWA-icon name allowlist.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.server_routes import meta as routes_meta  # noqa: E402


class _FakeHandler:
    def __init__(self):
        self.status = None
        self.headers = {}
        self.body = None
        self.json = None
        self.json_status = None
        self.ended = False

    def send_response(self, code):
        self.status = code

    def send_header(self, key, value):
        self.headers[key] = value

    def end_headers(self):
        self.ended = True

    def _safe_write(self, body):
        self.body = body

    def _send_json(self, obj, status=200):
        self.json = obj
        self.json_status = status


class StaticAssetServingTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.static = Path(self._tmp.name)
        self._patch = mock.patch.object(routes_meta, "_STATIC_DIR", self.static)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_manifest_served_when_present(self):
        (self.static / "manifest.webmanifest").write_bytes(b'{"name":"tb"}')
        h = _FakeHandler()
        routes_meta.h_manifest(h, urlparse("/manifest.webmanifest"))
        self.assertEqual(h.status, 200)
        self.assertEqual(h.headers["Content-Type"], "application/manifest+json")
        self.assertEqual(h.headers["Content-Length"], "13")
        self.assertEqual(h.body, b'{"name":"tb"}')

    def test_manifest_missing_is_clean_404(self):
        h = _FakeHandler()
        routes_meta.h_manifest(h, urlparse("/manifest.webmanifest"))
        self.assertEqual(h.json_status, 404)
        self.assertIn("manifest.webmanifest", h.json["error"])
        self.assertIsNone(h.status)  # no 200 line emitted

    def test_service_worker_headers_and_present(self):
        (self.static / "service-worker.js").write_bytes(b"// sw")
        h = _FakeHandler()
        routes_meta.h_service_worker(h, urlparse("/service-worker.js"))
        self.assertEqual(h.status, 200)
        self.assertEqual(h.headers["Cache-Control"], "no-cache, max-age=0")
        self.assertEqual(h.headers["Service-Worker-Allowed"], "/")

    def test_service_worker_missing_is_clean_404(self):
        h = _FakeHandler()
        routes_meta.h_service_worker(h, urlparse("/service-worker.js"))
        self.assertEqual(h.json_status, 404)

    def test_pwa_icon_unknown_name_404(self):
        h = _FakeHandler()
        routes_meta.h_pwa_icon(h, urlparse("/pwa-999.png"))
        self.assertEqual(h.json_status, 404)
        self.assertEqual(h.json["error"], "not found")

    def test_pwa_icon_known_but_missing_file_404(self):
        h = _FakeHandler()
        routes_meta.h_pwa_icon(h, urlparse("/pwa-192.png"))
        self.assertEqual(h.json_status, 404)
        self.assertIn("pwa-192.png", h.json["error"])

    def test_pwa_icon_served_when_present(self):
        (self.static / "pwa-192.png").write_bytes(b"\x89PNG")
        h = _FakeHandler()
        routes_meta.h_pwa_icon(h, urlparse("/pwa-192.png"))
        self.assertEqual(h.status, 200)
        self.assertEqual(h.headers["Content-Type"], "image/png")
        self.assertEqual(h.body, b"\x89PNG")


if __name__ == "__main__":
    unittest.main()
