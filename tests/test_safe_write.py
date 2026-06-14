"""Handler._safe_write resilience.

SSE subscribers and federation peers routinely drop the socket mid-write
when their timeout fires; that must not crash the response path. But a
genuine, unexpected write error must still propagate (not be silently
eaten). Pin both halves.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import server  # noqa: E402


class _Wfile:
    def __init__(self, raise_exc=None):
        self._raise = raise_exc
        self.written = b""

    def write(self, body):
        if self._raise is not None:
            raise self._raise
        self.written += body


class _Shim:
    def __init__(self, wfile):
        self.wfile = wfile


class SafeWriteTests(unittest.TestCase):

    def test_writes_body_through(self):
        shim = _Shim(_Wfile())
        server.Handler._safe_write(shim, b"hello")
        self.assertEqual(shim.wfile.written, b"hello")

    def test_broken_pipe_is_swallowed(self):
        shim = _Shim(_Wfile(BrokenPipeError()))
        server.Handler._safe_write(shim, b"x")  # must not raise

    def test_connection_reset_is_swallowed(self):
        shim = _Shim(_Wfile(ConnectionResetError()))
        server.Handler._safe_write(shim, b"x")  # must not raise

    def test_unexpected_error_propagates(self):
        # A non-disconnect error must NOT be hidden — that would mask real
        # bugs behind a silently-truncated response.
        shim = _Shim(_Wfile(ValueError("boom")))
        with self.assertRaises(ValueError):
            server.Handler._safe_write(shim, b"x")


if __name__ == "__main__":
    unittest.main()
