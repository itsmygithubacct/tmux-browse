"""Server-side config-lock enforcement: tokens gate mutation endpoints."""

import hashlib
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import server  # noqa: E402
from lib import config as cfg  # noqa: E402


class _FakeHandler:
    def __init__(self, headers=None):
        self.payload = None
        self.status = None
        self.headers = headers or {}

    def _send_json(self, obj, status=200):
        self.payload = obj
        self.status = status

    def _send_tb_error(self, err):
        return server.Handler._send_tb_error(self, err)

    def _check_unlock(self):
        return server.Handler._check_unlock(self)


class _LockedConfigMixin:
    """Point CONFIG_LOCK_FILE at a tempdir and set a known password."""

    password = "hunter2"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(
            cfg, "CONFIG_LOCK_FILE", Path(self._tmp.name) / "lock")
        self._patch.start()
        cfg.CONFIG_LOCK_FILE.write_text(
            hashlib.sha256(self.password.encode()).hexdigest() + "\n")
        server._unlock_tokens.clear()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()


class UnlockTokenTests(_LockedConfigMixin, unittest.TestCase):

    def test_verify_issues_token_on_correct_password(self):
        fake = _FakeHandler()
        server.routes_config.h_config_lock_verify(
            fake, urlparse("/api/config-lock/verify"),
            {"password": self.password})
        self.assertEqual(fake.status, 200)
        self.assertTrue(fake.payload["unlocked"])
        self.assertIn("unlock_token", fake.payload)
        token = fake.payload["unlock_token"]
        self.assertTrue(server._unlock_token_valid(token))

    def test_verify_rejects_wrong_password_without_token(self):
        fake = _FakeHandler()
        server.routes_config.h_config_lock_verify(
            fake, urlparse("/api/config-lock/verify"),
            {"password": "wrong"})
        self.assertEqual(fake.status, 403)
        self.assertNotIn("unlock_token", fake.payload)

    def test_status_does_not_leak_tokens(self):
        server._issue_unlock_token()
        fake = _FakeHandler()
        server.routes_config.h_config_lock_status(
            fake, urlparse("/api/config-lock"))
        self.assertNotIn("unlock_token", fake.payload or {})

    def test_expired_token_is_invalid(self):
        # Issue a token, then rewind expiry into the past.
        t = server._issue_unlock_token()
        server._unlock_tokens[t] = int(time.time()) - 1
        self.assertFalse(server._unlock_token_valid(t))

    def test_valid_token_passes_check(self):
        t = server._issue_unlock_token()
        self.assertTrue(server._unlock_token_valid(t))


class MutationGateTests(_LockedConfigMixin, unittest.TestCase):
    """Core mutation endpoints require a valid unlock token when locked."""

    def test_dashboard_config_post_gated(self):
        fake = _FakeHandler(headers={})
        server.routes_config.h_dashboard_config_post(
            fake, urlparse("/api/dashboard-config"), {"config": {}})
        self.assertEqual(fake.status, 403)

    def test_tasks_create_gated(self):
        fake = _FakeHandler(headers={})
        server.routes_tasks.h_tasks_create(
            fake, urlparse("/api/tasks"), {"title": "t"})
        self.assertEqual(fake.status, 403)

    def test_config_lock_set_gated_when_already_locked(self):
        # Clearing an active lock without a valid token must fail.
        fake = _FakeHandler(headers={})
        server.routes_config.h_config_lock_set(
            fake, urlparse("/api/config-lock"), {"password": ""})
        self.assertEqual(fake.status, 403)

    def test_extensions_install_gated(self):
        fake = _FakeHandler(headers={})
        server.routes_extensions.h_extensions_install(
            fake, urlparse("/api/extensions/install"), {"name": "agent"})
        self.assertEqual(fake.status, 403)

    def test_extensions_enable_gated(self):
        fake = _FakeHandler(headers={})
        server.routes_extensions.h_extensions_enable(
            fake, urlparse("/api/extensions/enable"), {"name": "agent"})
        self.assertEqual(fake.status, 403)


# Agent-endpoint lock coverage lives in
# ``extensions/agent/tests/test_config_lock_agent_endpoints.py`` and runs
# through the extension test shim.


if __name__ == "__main__":
    unittest.main()
