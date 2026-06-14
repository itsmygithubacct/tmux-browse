"""Token redaction in request logs.

When --verbose is on, the stdlib logger writes the request line to
stderr — and a bootstrap URL carries ``?token=<secret>``. _redact_token
must scrub it; log_message must stay silent unless --verbose is set.
These are a security control, so pin the behaviour against regressions.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import server  # noqa: E402


class RedactTokenTests(unittest.TestCase):

    def test_redacts_leading_token_param(self):
        self.assertEqual(
            server._redact_token("GET /?token=s3cr3t HTTP/1.1"),
            "GET /?token=<redacted> HTTP/1.1")

    def test_redacts_token_mid_query_keeps_neighbours(self):
        out = server._redact_token("/api?foo=1&token=s3cr3t&bar=2")
        self.assertEqual(out, "/api?foo=1&token=<redacted>&bar=2")

    def test_case_insensitive(self):
        self.assertEqual(
            server._redact_token("/?TOKEN=abc"), "/?token=<redacted>")

    def test_redacts_value_with_url_safe_chars(self):
        # token_urlsafe values contain - and _; redaction must consume
        # the whole value, not stop early.
        out = server._redact_token("/?token=aB-_9xQ.kZ")
        self.assertEqual(out, "/?token=<redacted>")

    def test_no_token_is_unchanged(self):
        s = "GET /api/sessions HTTP/1.1"
        self.assertEqual(server._redact_token(s), s)

    def test_does_not_over_redact_similar_param(self):
        # A value that merely contains the word "token" (not a ?token=/
        # &token= param) must be left intact.
        s = "/?path=/token=keepme"
        self.assertEqual(server._redact_token(s), s)

    def test_redacts_every_occurrence(self):
        out = server._redact_token("/?token=a&x=1&token=b")
        self.assertEqual(out, "/?token=<redacted>&x=1&token=<redacted>")


class _LogShim:
    def __init__(self, verbose):
        self.server = type("S", (), {"verbose": verbose})()


class LogMessageGatingTests(unittest.TestCase):

    def test_silent_when_not_verbose(self):
        shim = _LogShim(verbose=False)
        buf = io.StringIO()
        with redirect_stderr(buf):
            # Must not raise and must not reach the stderr-writing super().
            server.Handler.log_message(shim, '"%s"', "GET /?token=s3cr3t HTTP/1.1")
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
