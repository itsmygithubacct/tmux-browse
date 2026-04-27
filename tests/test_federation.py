"""Federation peer registry + beacon serialization tests.

The UDP listener/broadcaster threads aren't unit-tested here —
network state isn't reproducible in CI. Instead we cover the
pure-Python pieces: device-id persistence, peer registry GC,
beacon JSON shape, and the urllib-based peer fetcher's error
paths. End-to-end LAN tests are part of the manual smoke
checklist documented in CHANGELOG-style notes alongside the
Phase I release."""

import json
import sys
import time
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import federation  # noqa: E402


class DeviceIdTests(unittest.TestCase):
    """Per-host UUID persistence to ~/.tmux-browse/device-id."""

    def setUp(self):
        # Each test gets its own STATE_DIR so writes don't leak.
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tmp.name) / ".tmux-browse"
        self._patch = mock.patch.object(federation.config,
                                         "STATE_DIR", self.state_dir)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self.tmp.cleanup()

    def test_creates_uuid_on_first_call(self):
        did = federation.get_or_create_device_id()
        self.assertRegex(did, r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        # Persists to disk.
        path = self.state_dir / "device-id"
        self.assertTrue(path.exists())
        self.assertEqual(path.read_text().strip(), did)

    def test_persistent_across_calls(self):
        a = federation.get_or_create_device_id()
        b = federation.get_or_create_device_id()
        self.assertEqual(a, b)


class PeerRegistryTests(unittest.TestCase):
    """Thread-safe peer dict + TTL-based GC."""

    def setUp(self):
        federation.clear_peers()

    def tearDown(self):
        federation.clear_peers()

    def _peer(self, did="alpha", hostname="alpha", last_seen=None):
        return federation.PeerInfo(
            device_id=did, hostname=hostname,
            dashboard_port=8096, scheme="http",
            version="test",
            last_seen=last_seen if last_seen is not None else int(time.time()),
            addr="10.0.0.1",
        )

    def test_upsert_and_list(self):
        p = self._peer()
        federation.upsert_peer(p)
        rows = federation.list_peers()
        self.assertEqual([r.device_id for r in rows], ["alpha"])

    def test_upsert_replaces_existing(self):
        federation.upsert_peer(self._peer(hostname="alpha"))
        federation.upsert_peer(self._peer(hostname="alpha-renamed"))
        rows = federation.list_peers()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].hostname, "alpha-renamed")

    def test_list_peers_filters_stale(self):
        # last_seen far in the past
        federation.upsert_peer(self._peer(last_seen=int(time.time()) - 1000))
        rows = federation.list_peers()
        self.assertEqual(rows, [])

    def test_gc_drops_stale(self):
        federation.upsert_peer(self._peer(did="fresh"))
        federation.upsert_peer(self._peer(did="stale", last_seen=int(time.time()) - 1000))
        dropped = federation.gc_peers()
        self.assertEqual(dropped, 1)
        live = [p.device_id for p in federation.list_peers()]
        self.assertEqual(live, ["fresh"])

    def test_peer_info_base_url(self):
        p = federation.PeerInfo(
            device_id="x", hostname="alpha",
            dashboard_port=9090, scheme="https",
            version="t", last_seen=0, addr="10.0.0.5",
        )
        self.assertEqual(p.base_url, "https://10.0.0.5:9090")


class BeaconPayloadTests(unittest.TestCase):
    """Wire format the broadcaster sends and the listener expects."""

    def test_payload_round_trip(self):
        my = federation.PeerInfo(
            device_id="abc-123", hostname="alpha",
            dashboard_port=8096, scheme="http",
            version="0.7.3.0", last_seen=0, addr="",
        )
        wire = federation._beacon_payload(my, 42)
        msg = json.loads(wire.decode())
        self.assertEqual(msg["device_id"], "abc-123")
        self.assertEqual(msg["hostname"], "alpha")
        self.assertEqual(msg["dashboard_port"], 8096)
        self.assertEqual(msg["scheme"], "http")
        self.assertEqual(msg["version"], "0.7.3.0")
        self.assertEqual(msg["beacon_seq"], 42)

    def test_payload_under_typical_mtu(self):
        # Beacons must fit in a single UDP datagram; 1500 byte MTU
        # less ~50 of headers leaves ~1450 bytes of payload. The
        # actual payload is small — guard against future bloat.
        my = federation.PeerInfo(
            device_id="x" * 36, hostname="h" * 64,
            dashboard_port=65535, scheme="https",
            version="x" * 32, last_seen=0, addr="",
        )
        wire = federation._beacon_payload(my, 999_999_999)
        self.assertLess(len(wire), 1400)


class FetchPeerSessionsTests(unittest.TestCase):
    """The urllib-based GET <peer>/api/sessions wrapper.

    Not unit-tested in :mod:`lib.federation` because it lives in
    :mod:`lib.server` (where the rest of the merge logic is). Test
    it here anyway so the federation surface has one home."""

    def test_url_error_returns_empty(self):
        from lib import server
        with mock.patch("lib.server.urllib.request.urlopen",
                         side_effect=URLError("boom")):
            rows = server._fetch_peer_sessions("http://10.0.0.1:8096")
        self.assertEqual(rows, [])

    def test_well_formed_response_returns_rows(self):
        from lib import server
        body = json.dumps({"ok": True, "sessions": [
            {"name": "foo"}, {"name": "bar"},
        ]}).encode()
        fake = mock.MagicMock()
        fake.read.return_value = body
        fake.__enter__ = lambda self: self
        fake.__exit__ = lambda self, *a: False
        with mock.patch("lib.server.urllib.request.urlopen", return_value=fake):
            rows = server._fetch_peer_sessions("http://10.0.0.1:8096")
        self.assertEqual([r["name"] for r in rows], ["foo", "bar"])

    def test_malformed_json_returns_empty(self):
        from lib import server
        fake = mock.MagicMock()
        fake.read.return_value = b"not json{"
        fake.__enter__ = lambda self: self
        fake.__exit__ = lambda self, *a: False
        with mock.patch("lib.server.urllib.request.urlopen", return_value=fake):
            rows = server._fetch_peer_sessions("http://10.0.0.1:8096")
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
