"""Static contracts for same-origin remote-pane actions."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class FederationClientRoutingTests(unittest.TestCase):

    def test_peer_api_uses_local_allowlisted_proxy(self):
        util = (ROOT / "static" / "util.js").read_text(encoding="utf-8")
        lifecycle = (ROOT / "static" / "panes" / "lifecycle.js").read_text(
            encoding="utf-8",
        )
        self.assertIn('"/api/peers/proxy"', util)
        self.assertIn("device_id: peer.deviceId", util)
        self.assertNotIn("baseUrl + path", util + lifecycle)

    def test_all_remote_pane_mutations_use_peer_api(self):
        sources = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8")
            for relative in (
                "static/panes/lifecycle.js",
                "static/panes/send-queue.js",
                "static/panes/hot-buttons.js",
            )
        )
        for path in (
            "/api/ttyd/start",
            "/api/ttyd/stop",
            "/api/session/kill",
            "/api/session/resize",
            "/api/session/scroll",
            "/api/session/zoom",
            "/api/session/type",
            "/api/session/key",
        ):
            self.assertIn(f'_peerApi(session, "POST", "{path}"', sources)
        self.assertNotIn('api("POST", "/api/ttyd/stop"', sources)

    def test_ttyd_fallback_replaces_port_structurally(self):
        util = (ROOT / "static" / "util.js").read_text(encoding="utf-8")
        lifecycle = (ROOT / "static" / "panes" / "lifecycle.js").read_text(
            encoding="utf-8",
        )
        self.assertIn("url.port = String(port)", util)
        self.assertNotIn("baseUrl.replace", lifecycle)

    def test_refresh_keeps_remote_ttyd_and_log_urls_on_the_peer(self):
        util = (ROOT / "static" / "util.js").read_text(encoding="utf-8")
        render = (ROOT / "static" / "panes" / "render.js").read_text(
            encoding="utf-8",
        )
        self.assertIn("function sessionTtydUrl(session)", util)
        self.assertIn('"/api/peers/session-log"', util)
        self.assertIn("sessionTtydUrl(s)", render)
        self.assertIn("sessionLogUrl(s)", render)
        self.assertNotIn("ttydUrl(s.port)", render)


if __name__ == "__main__":
    unittest.main()
