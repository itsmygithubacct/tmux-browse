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

    def test_startup_reconciles_surviving_ttyds(self):
        expected = {"checked": 2, "restarted": 1, "errors": []}
        with mock.patch.object(
            server.ttyd, "reconcile_running", return_value=expected,
        ) as reconcile:
            result = server._reconcile_ttyd_policy("127.0.0.1", None)
        self.assertEqual(result, expected)
        reconcile.assert_called_once_with(bind_addr="127.0.0.1", tls_paths=None)

    def test_startup_fails_closed_when_ttyd_policy_cannot_be_applied(self):
        with mock.patch.object(
            server.ttyd,
            "reconcile_running",
            return_value={
                "checked": 1,
                "restarted": 0,
                "errors": ["work: permission denied"],
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "permission denied"):
                server._reconcile_ttyd_policy("127.0.0.1", None)

    def test_serve_reconciles_before_constructing_http_server(self):
        with mock.patch.object(server.config, "ensure_dirs"), \
             mock.patch.object(
                 server.ttyd,
                 "gc_orphans",
                 return_value={"stale_pids_removed": 0, "ports_dropped": 0},
             ), \
             mock.patch.object(
                 server,
                 "_reconcile_ttyd_policy",
                 side_effect=RuntimeError("policy sentinel"),
             ) as reconcile, \
             mock.patch.object(server, "DashboardServer") as dashboard_server:
            with self.assertRaisesRegex(RuntimeError, "policy sentinel"):
                server.serve("127.0.0.1", 8096)
        reconcile.assert_called_once_with("127.0.0.1", None)
        dashboard_server.assert_not_called()

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
