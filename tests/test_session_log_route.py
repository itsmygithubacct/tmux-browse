"""h_session_log route: param handling + html/text response selection.

The function-level HTML escaping is covered in test_log_html_escaping;
this covers the route wrapper around it — the entry point at
/api/session/log.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.server_routes import sessions as routes_sessions  # noqa: E402


class _FakeHandler:
    def __init__(self):
        self.text = None
        self.text_status = None
        self.html = None
        self.html_status = None

    def _send_text(self, text, status=200):
        self.text = text
        self.text_status = status

    def _send_html(self, html, status=200):
        self.html = html
        self.html_status = status


def _parsed(query):
    return urlparse(f"/api/session/log?{query}")


class SessionLogRouteTests(unittest.TestCase):

    def test_missing_session_is_400(self):
        h = _FakeHandler()
        routes_sessions.h_session_log(h, _parsed("lines=10"))
        self.assertEqual(h.text_status, 400)
        self.assertIn("missing 'session'", h.text)

    def test_success_text_mode(self):
        h = _FakeHandler()
        with mock.patch.object(routes_sessions.sessions, "capture_target",
                               return_value=(True, "scrollback")):
            routes_sessions.h_session_log(h, _parsed("session=work"))
        self.assertEqual(h.text, "scrollback")
        self.assertEqual(h.text_status, 200)
        self.assertIsNone(h.html)

    def test_success_html_mode_wraps_content(self):
        h = _FakeHandler()
        with mock.patch.object(routes_sessions.sessions, "capture_target",
                               return_value=(True, "<x>")):
            routes_sessions.h_session_log(h, _parsed("session=work&html=1"))
        self.assertEqual(h.html_status, 200)
        self.assertIn("&lt;x&gt;", h.html)       # content escaped
        self.assertIn("window.scrollTo", h.html)  # log page chrome present

    def test_capture_failure_text_is_404(self):
        h = _FakeHandler()
        with mock.patch.object(routes_sessions.sessions, "capture_target",
                               return_value=(False, "no such session: work")):
            routes_sessions.h_session_log(h, _parsed("session=work"))
        self.assertEqual(h.text_status, 404)
        self.assertIn("no such session", h.text)

    def test_capture_failure_html_is_404(self):
        h = _FakeHandler()
        with mock.patch.object(routes_sessions.sessions, "capture_target",
                               return_value=(False, "boom")):
            routes_sessions.h_session_log(h, _parsed("session=work&html=1"))
        self.assertEqual(h.html_status, 404)
        self.assertIn("boom", h.html)

    def test_lines_clamped_to_max(self):
        h = _FakeHandler()
        with mock.patch.object(routes_sessions.sessions, "capture_target",
                               return_value=(True, "")) as cap:
            routes_sessions.h_session_log(h, _parsed("session=work&lines=999999"))
        self.assertEqual(cap.call_args.kwargs["lines"], 50000)

    def test_lines_clamped_to_min(self):
        h = _FakeHandler()
        with mock.patch.object(routes_sessions.sessions, "capture_target",
                               return_value=(True, "")) as cap:
            routes_sessions.h_session_log(h, _parsed("session=work&lines=0"))
        self.assertEqual(cap.call_args.kwargs["lines"], 1)

    def test_lines_invalid_falls_back_to_default(self):
        h = _FakeHandler()
        with mock.patch.object(routes_sessions.sessions, "capture_target",
                               return_value=(True, "")) as cap:
            routes_sessions.h_session_log(h, _parsed("session=work&lines=abc"))
        self.assertEqual(cap.call_args.kwargs["lines"], 2000)


if __name__ == "__main__":
    unittest.main()
