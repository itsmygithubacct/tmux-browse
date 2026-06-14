"""Connected-client tracking + config-share routes (lib/server_routes/clients).

Covers the shared-state behaviour that had no test: nickname trimming,
inbox delivery + bound, pop-clears-on-read, and the config_url
validation guarding /api/clients/send-config.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import server  # noqa: E402
from lib.server_routes import clients as routes_clients  # noqa: E402


class _HandlerShim:
    """Minimal Handler stand-in for the clients routes."""

    def __init__(self, *, ip="10.0.0.1", ua="agent/1", unlocked=True):
        self.client_address = (ip, 4321)
        self.headers = {"User-Agent": ua}
        self._unlocked = unlocked
        self.sent = []

    def _check_unlock(self):
        return self._unlocked

    def _send_json(self, obj, status=200):
        self.sent.append((status, obj))

    @property
    def last(self):
        return self.sent[-1]


class ClientRoutesTests(unittest.TestCase):

    def setUp(self):
        # Mutate the module globals in place so the lazily-imported
        # references inside the route handlers stay valid.
        server._clients.clear()
        server._client_inbox.clear()

    tearDown = setUp

    def _register(self, ip, ua="agent/1"):
        h = _HandlerShim(ip=ip, ua=ua)
        return h, server._touch_client(h)

    # --- nickname ---------------------------------------------------------

    def test_nickname_is_trimmed_to_30_chars(self):
        h = _HandlerShim(ip="10.0.0.5")
        routes_clients.h_clients_nickname(h, None, {"nickname": "x" * 100})
        status, payload = h.last
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["nickname"]), 30)
        self.assertEqual(server._clients[payload["client_id"]]["nickname"],
                         "x" * 30)

    def test_nickname_gated_by_unlock(self):
        h = _HandlerShim(unlocked=False)
        routes_clients.h_clients_nickname(h, None, {"nickname": "nope"})
        # _check_unlock False short-circuits before any _send_json here.
        self.assertEqual(h.sent, [])

    # --- send-config validation ------------------------------------------

    def test_send_config_missing_fields(self):
        h, _ = self._register("10.0.0.1")
        routes_clients.h_clients_send_config(h, None, {"target": "", "config_url": ""})
        self.assertEqual(h.last[0], 400)

    def test_send_config_rejects_non_http_scheme(self):
        sender, _ = self._register("10.0.0.1")
        _, target_id = self._register("10.0.0.2")
        routes_clients.h_clients_send_config(
            sender, None,
            {"target": target_id, "config_url": "javascript:alert(1)"})
        status, payload = sender.last
        self.assertEqual(status, 400)
        self.assertIn("http(s)", payload["error"])
        self.assertEqual(server._client_inbox.get(target_id, []), [])

    def test_send_config_rejects_overlong_url(self):
        sender, _ = self._register("10.0.0.1")
        _, target_id = self._register("10.0.0.2")
        long_url = "http://h/?import-cfg=" + ("A" * 9000)
        routes_clients.h_clients_send_config(
            sender, None, {"target": target_id, "config_url": long_url})
        self.assertEqual(sender.last[0], 400)

    def test_send_config_unknown_target(self):
        sender, _ = self._register("10.0.0.1")
        routes_clients.h_clients_send_config(
            sender, None,
            {"target": "deadbeef0000", "config_url": "http://h/?import-cfg=AA"})
        self.assertEqual(sender.last[0], 404)

    def test_send_config_delivers_to_inbox(self):
        sender, sender_id = self._register("10.0.0.1")
        _, target_id = self._register("10.0.0.2")
        url = "https://host/?import-cfg=eyJhIjoxfQ=="
        routes_clients.h_clients_send_config(
            sender, None, {"target": target_id, "config_url": url})
        self.assertTrue(sender.last[1]["sent"])
        inbox = server._client_inbox[target_id]
        self.assertEqual(len(inbox), 1)
        self.assertEqual(inbox[0]["config_url"], url)
        self.assertEqual(inbox[0]["from_id"], sender_id)

    def test_inbox_is_bounded_to_10(self):
        sender, _ = self._register("10.0.0.1")
        _, target_id = self._register("10.0.0.2")
        for i in range(15):
            routes_clients.h_clients_send_config(
                sender, None,
                {"target": target_id,
                 "config_url": f"http://h/?import-cfg=tag{i}"})
        inbox = server._client_inbox[target_id]
        self.assertEqual(len(inbox), 10)
        # Oldest dropped — the last 10 (tags 5..14) survive.
        self.assertIn("tag14", inbox[-1]["config_url"])
        self.assertIn("tag5", inbox[0]["config_url"])

    # --- inbox read clears ------------------------------------------------

    def test_inbox_pop_clears_messages(self):
        sender, _ = self._register("10.0.0.1")
        target, target_id = self._register("10.0.0.2")
        routes_clients.h_clients_send_config(
            sender, None,
            {"target": target_id, "config_url": "http://h/?import-cfg=AA"})
        # The target reads its own inbox.
        routes_clients.h_clients_inbox(target, None)
        status, payload = target.last
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["messages"]), 1)
        self.assertNotIn(target_id, server._client_inbox)


if __name__ == "__main__":
    unittest.main()
