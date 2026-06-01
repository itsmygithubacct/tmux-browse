"""Session route guards for malformed input and tmux failures."""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.server_routes import sessions as routes_sessions  # noqa: E402


class _FakeHandler:
    def __init__(self):
        self.payload = None
        self.status = None
        self.server = type("S", (), {})()

    def _send_json(self, payload, status=200):
        self.payload = payload
        self.status = status

    def _check_unlock(self):
        # No config lock under test — let mutations through. Lock
        # enforcement itself is covered by tests/test_config_lock.py.
        return True


class SessionResizeRouteTests(unittest.TestCase):

    def test_rejects_non_integer_dimensions(self):
        fake = _FakeHandler()
        routes_sessions.h_session_resize(
            fake,
            urlparse("/api/session/resize"),
            {"session": "demo", "cols": "wide", "rows": "10"},
        )
        self.assertEqual(fake.status, 400)
        self.assertIn("integers", fake.payload["error"])

    def test_surfaces_tmux_unavailable_as_503(self):
        fake = _FakeHandler()
        with mock.patch(
            "lib.server_routes.sessions.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="tmux", timeout=10),
        ):
            routes_sessions.h_session_resize(
                fake,
                urlparse("/api/session/resize"),
                {"session": "demo", "cols": "80", "rows": "24"},
            )
        self.assertEqual(fake.status, 503)
        self.assertEqual(fake.payload["error"], "tmux unavailable")
