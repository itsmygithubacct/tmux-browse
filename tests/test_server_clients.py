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

    # --- stale-client pruning --------------------------------------------

    def test_prune_drops_idle_clients_and_inboxes(self):
        now = 1_000_000
        server._clients["fresh"] = {"client_id": "fresh", "ip": "1.1.1.1",
                                    "last_seen": now}
        server._clients["stale"] = {"client_id": "stale", "ip": "2.2.2.2",
                                    "last_seen": now - server._CLIENT_TIMEOUT - 1}
        server._client_inbox["stale"] = [{"x": 1}]
        server._prune_clients(now)
        self.assertIn("fresh", server._clients)
        self.assertNotIn("stale", server._clients)
        self.assertNotIn("stale", server._client_inbox)

    def test_touch_new_client_prunes_stale_even_without_clients_poll(self):
        # Simulate a long-lived dashboard where /api/clients is never hit
        # (Connected pane disabled): a stale entry must still be swept when
        # a *new* client registers via any request.
        server._clients["stale"] = {"client_id": "stale", "ip": "9.9.9.9",
                                    "last_seen": 0}
        # _touch_client uses real time.time(); the stale entry (last_seen=0)
        # is far past the timeout.
        h = _HandlerShim(ip="10.0.0.99", ua="new")
        server._touch_client(h)
        self.assertNotIn("stale", server._clients,
                         "registering a new client should sweep stale ones")

    def test_touch_existing_client_does_not_prune(self):
        # A heartbeat from an already-known client must not trigger a sweep
        # (keeps the hot path cheap). The stale entry stays until a new
        # client or an /api/clients poll prunes it.
        h = _HandlerShim(ip="10.0.0.1", ua="known")
        cid = server._touch_client(h)
        server._clients["stale"] = {"client_id": "stale", "ip": "9.9.9.9",
                                    "last_seen": 0}
        server._touch_client(h)  # same fingerprint -> not a new client
        self.assertIn("stale", server._clients)
        self.assertIn(cid, server._clients)

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
