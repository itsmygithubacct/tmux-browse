"""ttyd HTTP route response contracts."""

import sys
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import server  # noqa: E402


class _Handler:
    _ttyd_url = server.Handler._ttyd_url

    def __init__(self):
        self.headers = {"Host": "10.0.0.9:8096"}
        self.server = type("S", (), {
            "server_address": ("0.0.0.0", 8096),
            "tls_paths": None,
            "ttyd_bind_addr": "0.0.0.0",
        })()
        self.payload = None
        self.status = None

    def _check_unlock(self):
        return True

    def _send_json(self, payload, status=200):
        self.payload = payload
        self.status = status


class TtydRouteTests(unittest.TestCase):

    def test_start_response_includes_peer_reachable_url(self):
        handler = _Handler()
        with mock.patch.object(server.routes_ttyd.sessions, "exists", return_value=True), \
             mock.patch.object(
                 server.routes_ttyd.ttyd,
                 "start",
                 return_value={
                     "ok": True,
                     "port": 7704,
                     "pid": 123,
                     "already": False,
                     "scheme": "http",
                 },
             ):
            server.routes_ttyd.h_ttyd_start(
                handler, urlparse("/api/ttyd/start"), {"session": "work"},
            )
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.payload["url"], "http://10.0.0.9:7704/")

    def test_raw_response_includes_url(self):
        handler = _Handler()
        with mock.patch.object(
            server.routes_ttyd.ttyd,
            "start_raw",
            return_value={
                "ok": True,
                "port": 7705,
                "pid": 124,
                "name": "raw-shell-1",
                "scheme": "http",
            },
        ):
            server.routes_ttyd.h_ttyd_raw(
                handler, urlparse("/api/ttyd/raw"), {},
            )
        self.assertEqual(handler.payload["url"], "http://10.0.0.9:7705/")


if __name__ == "__main__":
    unittest.main()
