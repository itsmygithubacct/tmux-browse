"""Response helpers (_send_json/_send_html/_send_text).

Every endpoint emits through these, so pin their contract:
  - the right status and Content-Type,
  - Cache-Control: no-store (auth-protected session data must not be
    cached by browsers or shared proxies),
  - a byte-accurate Content-Length for multibyte UTF-8 (a char-count
    here would truncate or hang the response),
  - the encoded body actually written.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import server  # noqa: E402


class _SendShim:
    def __init__(self):
        self.status = None
        self.headers = {}
        self.ended = False
        self.body = None
        # _send_* call end_headers(), which emits the security headers and
        # then super().end_headers(); stub it to just record.
        self._tb_security_headers_sent = True  # skip the security emit path

    def send_response(self, code, message=None):
        self.status = code

    def send_header(self, key, value):
        self.headers[key] = value

    def end_headers(self):
        self.ended = True

    def _safe_write(self, body):
        self.body = body


class SendJsonTests(unittest.TestCase):

    def test_status_content_type_and_no_store(self):
        shim = _SendShim()
        server.Handler._send_json(shim, {"ok": True}, status=201)
        self.assertEqual(shim.status, 201)
        self.assertEqual(shim.headers["Content-Type"],
                         "application/json; charset=utf-8")
        self.assertEqual(shim.headers["Cache-Control"], "no-store")
        self.assertEqual(json.loads(shim.body.decode("utf-8")), {"ok": True})

    def test_default_status_200(self):
        shim = _SendShim()
        server.Handler._send_json(shim, {"x": 1})
        self.assertEqual(shim.status, 200)

    def test_content_length_matches_body_bytes(self):
        # json.dumps defaults to ensure_ascii, so the JSON body is ASCII
        # even for multibyte input — the contract here is just that
        # Content-Length equals the emitted byte count.
        shim = _SendShim()
        server.Handler._send_json(shim, {"msg": "café→“”"})
        self.assertEqual(int(shim.headers["Content-Length"]), len(shim.body))


class SendHtmlTextTests(unittest.TestCase):

    def test_html_headers(self):
        shim = _SendShim()
        server.Handler._send_html(shim, "<p>hi</p>", status=404)
        self.assertEqual(shim.status, 404)
        self.assertEqual(shim.headers["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(shim.headers["Cache-Control"], "no-store")
        self.assertEqual(int(shim.headers["Content-Length"]), len(shim.body))

    def test_html_content_length_is_byte_count_for_multibyte(self):
        # Unlike JSON, HTML encodes the raw string to UTF-8, so multibyte
        # characters make the byte count exceed the character count — the
        # Content-Length must be the byte count or the response truncates.
        shim = _SendShim()
        server.Handler._send_html(shim, "<p>café→“”</p>")
        self.assertEqual(int(shim.headers["Content-Length"]), len(shim.body))
        self.assertGreater(len(shim.body), len(shim.body.decode("utf-8")))

    def test_text_headers_and_no_store(self):
        shim = _SendShim()
        server.Handler._send_text(shim, "plain", status=400)
        self.assertEqual(shim.status, 400)
        self.assertEqual(shim.headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(shim.headers["Cache-Control"], "no-store")

    def test_text_replaces_undecodable_bytes_without_raising(self):
        # Lone surrogate can't encode strictly; errors="replace" must keep
        # it from blowing up the response path.
        shim = _SendShim()
        server.Handler._send_text(shim, "ok \udce2 tail")
        self.assertIsNotNone(shim.body)
        self.assertEqual(int(shim.headers["Content-Length"]), len(shim.body))


if __name__ == "__main__":
    unittest.main()
