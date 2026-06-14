"""Handler._auth_gate composition.

The individual auth helpers are covered in test_auth.py; this exercises
the gate that wires them together on every request: auth-disabled and
open paths pass, a missing/bad token gets a 401, and a valid token
(via Authorization, cookie, or query) passes.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import server  # noqa: E402


class _AuthShim:
    def __init__(self, *, expected, path="/api/sessions", headers=None):
        self.server = type("S", (), {"expected_token": expected})()
        self.path = path
        self.headers = headers or {}
        self.status = None

    # auth.send_401 drives these:
    def send_response(self, code, *a):
        self.status = code

    def send_header(self, *a):
        pass

    def end_headers(self):
        pass

    def _safe_write(self, body):
        pass

    # Redirect rewriting is covered by TokenStripRedirectTests; stub it so
    # _auth_gate's auth decision is what's under test here.
    def _maybe_strip_token_redirect(self, token):
        return False


def _gate(shim):
    return server.Handler._auth_gate(shim)


class AuthGateTests(unittest.TestCase):

    def test_auth_disabled_allows_everything(self):
        shim = _AuthShim(expected=None, headers={})
        self.assertTrue(_gate(shim))
        self.assertIsNone(shim.status)

    def test_open_path_allowed_without_token(self):
        shim = _AuthShim(expected="tok", path="/health", headers={})
        self.assertTrue(_gate(shim))
        self.assertIsNone(shim.status)

    def test_missing_token_gets_401(self):
        shim = _AuthShim(expected="tok", headers={})
        self.assertFalse(_gate(shim))
        self.assertEqual(shim.status, 401)

    def test_wrong_token_gets_401(self):
        shim = _AuthShim(expected="tok",
                         headers={"Authorization": "Bearer nope"})
        self.assertFalse(_gate(shim))
        self.assertEqual(shim.status, 401)

    def test_valid_bearer_token_passes(self):
        shim = _AuthShim(expected="tok",
                         headers={"Authorization": "Bearer tok"})
        self.assertTrue(_gate(shim))
        self.assertIsNone(shim.status)

    def test_valid_cookie_token_passes(self):
        shim = _AuthShim(expected="tok",
                         headers={"Cookie": "tb_auth=tok"})
        self.assertTrue(_gate(shim))
        self.assertIsNone(shim.status)

    def test_valid_query_token_passes(self):
        shim = _AuthShim(expected="tok", path="/api/sessions?token=tok")
        self.assertTrue(_gate(shim))
        self.assertIsNone(shim.status)


if __name__ == "__main__":
    unittest.main()
