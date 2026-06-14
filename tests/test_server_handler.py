"""Low-level Handler guards around malformed input and late failures."""

import io
import os
import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import server  # noqa: E402
from lib.errors import UsageError  # noqa: E402


class _ReadJsonShim:
    def __init__(self, headers=None, raw=b"{}", connection=None):
        self.headers = headers or {}
        self.rfile = raw if hasattr(raw, "read") else io.BytesIO(raw)
        self.connection = connection


class _ConnShim:
    def __init__(self, timeout=None):
        self.timeout = timeout

    def gettimeout(self):
        return self.timeout

    def settimeout(self, timeout):
        self.timeout = timeout


class _TimeoutReader:
    def read(self, _n):
        raise socket.timeout("slow body")


class _UnexpectedErrorShim:
    def __init__(self, started=False):
        self.server = type("S", (), {"verbose": False})()
        self._tb_response_started = started
        self.calls = []

    def _send_json(self, obj, status=200):
        self.calls.append((status, obj))


class ReadJsonTests(unittest.TestCase):

    def test_invalid_content_length_raises_usage_error(self):
        shim = _ReadJsonShim(headers={"Content-Length": "abc"})
        with self.assertRaises(UsageError):
            server.Handler._read_json(shim)

    def test_invalid_json_body_returns_empty_dict(self):
        shim = _ReadJsonShim(headers={"Content-Length": "3"}, raw=b"{x}")
        self.assertEqual(server.Handler._read_json(shim), {})

    def test_oversized_body_raises_usage_error(self):
        shim = _ReadJsonShim(
            headers={"Content-Length": str(server._MAX_JSON_BODY_BYTES + 1)},
            raw=b"{}",
        )
        with self.assertRaises(UsageError):
            server.Handler._read_json(shim)

    def test_body_read_timeout_raises_usage_error(self):
        conn = _ConnShim(timeout=None)
        shim = _ReadJsonShim(
            headers={"Content-Length": "2"},
            raw=_TimeoutReader(),
            connection=conn,
        )
        with self.assertRaises(UsageError):
            server.Handler._read_json(shim)
        self.assertIsNone(conn.timeout)


class HostWithoutPortTests(unittest.TestCase):

    def test_bare_name(self):
        self.assertEqual(server._host_without_port("example.com"), "example.com")

    def test_name_with_port(self):
        self.assertEqual(server._host_without_port("example.com:8096"), "example.com")

    def test_ipv4_with_port(self):
        self.assertEqual(server._host_without_port("127.0.0.1:8096"), "127.0.0.1")

    def test_ipv6_bracketed_with_port(self):
        self.assertEqual(server._host_without_port("[::1]:8096"), "::1")

    def test_ipv6_bracketed_no_port(self):
        self.assertEqual(server._host_without_port("[::1]"), "::1")

    def test_empty(self):
        self.assertEqual(server._host_without_port(""), "")


class _RebindShim:
    """Minimal stand-in for a Handler exercising ``_rebind_gate``."""

    def __init__(self, *, allowed, headers, path="/api/session/type"):
        self.server = type("S", (), {"allowed_hosts": allowed})()
        self.headers = headers
        self.path = path
        self.sent = []

    def _send_json(self, obj, status=200):
        self.sent.append((status, obj))


class RebindGateTests(unittest.TestCase):

    ALLOWED = frozenset({"localhost", "127.0.0.1", "192.168.1.154"})

    def test_disabled_when_allowed_is_none(self):
        shim = _RebindShim(allowed=None, headers={"Host": "evil.example"})
        self.assertTrue(server.Handler._rebind_gate(shim))
        self.assertEqual(shim.sent, [])

    def test_allows_known_host(self):
        shim = _RebindShim(allowed=self.ALLOWED, headers={"Host": "127.0.0.1:8096"})
        self.assertTrue(server.Handler._rebind_gate(shim))
        self.assertEqual(shim.sent, [])

    def test_rejects_unknown_host(self):
        shim = _RebindShim(allowed=self.ALLOWED, headers={"Host": "attacker.test:8096"})
        self.assertFalse(server.Handler._rebind_gate(shim))
        self.assertEqual(shim.sent[0][0], 403)

    def test_rejects_cross_origin_even_with_allowed_host(self):
        # The classic rebinding/CSRF shape: Host looks right but the page
        # driving the request lives on the attacker's origin.
        shim = _RebindShim(
            allowed=self.ALLOWED,
            headers={"Host": "127.0.0.1:8096",
                     "Origin": "http://attacker.test"})
        self.assertFalse(server.Handler._rebind_gate(shim))
        self.assertEqual(shim.sent[0][0], 403)

    def test_allows_same_origin(self):
        shim = _RebindShim(
            allowed=self.ALLOWED,
            headers={"Host": "192.168.1.154:8096",
                     "Origin": "http://192.168.1.154:8096"})
        self.assertTrue(server.Handler._rebind_gate(shim))
        self.assertEqual(shim.sent, [])

    def test_open_path_is_never_gated(self):
        shim = _RebindShim(
            allowed=self.ALLOWED, headers={"Host": "attacker.test"},
            path="/health")
        self.assertTrue(server.Handler._rebind_gate(shim))
        self.assertEqual(shim.sent, [])


class BuildAllowedHostsTests(unittest.TestCase):

    def setUp(self):
        for k in ("TMUX_BROWSE_DISABLE_HOST_CHECK", "TMUX_BROWSE_ALLOWED_HOSTS"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.setUp()

    def test_disabled_returns_none(self):
        os.environ["TMUX_BROWSE_DISABLE_HOST_CHECK"] = "1"
        self.assertIsNone(server._build_allowed_hosts("0.0.0.0"))

    def test_always_includes_loopback(self):
        allowed = server._build_allowed_hosts("0.0.0.0")
        self.assertIn("localhost", allowed)
        self.assertIn("127.0.0.1", allowed)

    def test_concrete_bind_is_allowed(self):
        allowed = server._build_allowed_hosts("192.168.1.154")
        self.assertIn("192.168.1.154", allowed)

    def test_extra_hosts_from_env(self):
        os.environ["TMUX_BROWSE_ALLOWED_HOSTS"] = "dash.example.com, tb.local"
        allowed = server._build_allowed_hosts("0.0.0.0")
        self.assertIn("dash.example.com", allowed)
        self.assertIn("tb.local", allowed)

    def test_primary_outbound_ip_included_when_available(self):
        # On a host with any default route the primary LAN IP must be in
        # the allow-set so a LAN client reaching us by IP isn't rejected.
        primary = server._primary_outbound_ip()
        if primary is None:
            self.skipTest("no routable interface in this environment")
        self.assertIn(primary.lower(), server._build_allowed_hosts("0.0.0.0"))


class PrimaryOutboundIpTests(unittest.TestCase):

    def test_returns_ip_or_none(self):
        result = server._primary_outbound_ip()
        if result is not None:
            # Looks like a dotted-quad; never loopback (we connect outward).
            parts = result.split(".")
            self.assertEqual(len(parts), 4)
            self.assertTrue(all(p.isdigit() for p in parts))


class UnexpectedErrorTests(unittest.TestCase):

    def test_sends_json_when_no_response_started(self):
        shim = _UnexpectedErrorShim(started=False)
        server.Handler._send_unexpected_error(shim, RuntimeError("boom"))
        self.assertEqual(len(shim.calls), 1)
        status, payload = shim.calls[0]
        self.assertEqual(status, 500)
        self.assertEqual(payload["error"], "internal server error")

    def test_does_not_double_write_after_response_started(self):
        shim = _UnexpectedErrorShim(started=True)
        server.Handler._send_unexpected_error(shim, RuntimeError("boom"))
        self.assertEqual(shim.calls, [])


class TbErrorTests(unittest.TestCase):

    def test_sends_json_when_no_response_started(self):
        shim = _UnexpectedErrorShim(started=False)
        server.Handler._send_tb_error(shim, UsageError("bad input"))
        self.assertEqual(len(shim.calls), 1)
        status, payload = shim.calls[0]
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "bad input")

    def test_does_not_double_write_after_response_started(self):
        # A handler that already began a response then raised a TBError must
        # not get a second status line written over the in-flight one.
        shim = _UnexpectedErrorShim(started=True)
        server.Handler._send_tb_error(shim, UsageError("bad input"))
        self.assertEqual(shim.calls, [])
