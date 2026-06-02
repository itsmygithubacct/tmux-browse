"""Low-level Handler guards around malformed input and late failures."""

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import server  # noqa: E402
from lib.errors import UsageError  # noqa: E402


class _ReadJsonShim:
    def __init__(self, headers=None, raw=b"{}"):
        self.headers = headers or {}
        self.rfile = io.BytesIO(raw)


class _UnexpectedErrorShim:
    def __init__(self, started=False):
        self.server = type("S", (), {"verbose": False})()
        self._tb_response_started = started
        self.calls = []

    def _send_json(self, obj, status=200):
        self.calls.append((status, obj))


class ReadJsonTests(unittest.TestCase):

    def test_invalid_content_length_raises_usage_error(self):
        shim = _ReadJsonShim(headers={"Content-Length": "abc"})
        with self.assertRaises(UsageError):
            server.Handler._read_json(shim)

    def test_invalid_json_body_returns_empty_dict(self):
        shim = _ReadJsonShim(headers={"Content-Length": "3"}, raw=b"{x}")
        self.assertEqual(server.Handler._read_json(shim), {})


class UnexpectedErrorTests(unittest.TestCase):

    def test_sends_json_when_no_response_started(self):
        shim = _UnexpectedErrorShim(started=False)
        server.Handler._send_unexpected_error(shim, RuntimeError("boom"))
        self.assertEqual(len(shim.calls), 1)
        status, payload = shim.calls[0]
        self.assertEqual(status, 500)
        self.assertEqual(payload["error"], "internal server error")

    def test_does_not_double_write_after_response_started(self):
        shim = _UnexpectedErrorShim(started=True)
        server.Handler._send_unexpected_error(shim, RuntimeError("boom"))
        self.assertEqual(shim.calls, [])
