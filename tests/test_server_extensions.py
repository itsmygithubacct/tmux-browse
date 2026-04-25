"""End-to-end wiring of the extension loader into the HTTP server.

Exercises ``lib/server.py``'s extension-awareness: the Handler's
two-phase route lookup, ``_h_index`` passing ui_blocks/extension_js
into templates.render_index, and the five /api/extensions/* endpoints.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import extensions, server  # noqa: E402
from lib import config as cfg  # noqa: E402
from lib.extensions import MergedRegistry, Registration  # noqa: E402


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


class _FakeHandler:
    def __init__(self, server_obj=None, headers=None):
        self.payload = None
        self.status = None
        self.body_bytes = None
        self.body_ct = None
        self.server = server_obj or _FakeServer()
        self.headers = headers or {}

    def _send_json(self, obj, status=200):
        self.payload = obj
        self.status = status

    def _send_html(self, html, status=200):
        self.body_bytes = html.encode("utf-8")
        self.body_ct = "text/html"
        self.status = status

    def _send_tb_error(self, err):
        return server.Handler._send_tb_error(self, err)

    def _check_unlock(self):
        return server.Handler._check_unlock(self)


class _FakeServer:
    def __init__(self):
        self.extension_registry = MergedRegistry()


class ExtensionRouteWiringTests(unittest.TestCase):
    """Hits the Handler's dispatch path directly to verify extension
    routes are consulted after core routes."""

    def test_extension_get_route_dispatches(self):
        calls = []
        def ext_handler(handler, parsed):
            calls.append(parsed.path)
            handler._send_json({"ok": True, "from": "ext"})
        reg = MergedRegistry()
        reg.get_routes["/api/ext-route"] = ext_handler
        fake = _FakeHandler(_FakeServer())
        fake.server.extension_registry = reg
        # Manual dispatch mimicking Handler.do_GET's fallback branch.
        handler = server.Handler._GET_ROUTES.get("/api/ext-route")
        if handler is None:
            ext = fake.server.extension_registry.get_routes.get("/api/ext-route")
            self.assertIsNotNone(ext)
            ext(fake, urlparse("/api/ext-route"))
        self.assertEqual(calls, ["/api/ext-route"])
        self.assertTrue(fake.payload["ok"])


class IndexTemplateSlotsTests(unittest.TestCase):

    def test_index_injects_extension_ui_blocks(self):
        fake = _FakeHandler(_FakeServer())
        fake.server.extension_registry = MergedRegistry()
        fake.server.extension_registry.ui_blocks["topbar_extras"] = \
            '<span id="probe-ext-block"/>'
        server.Handler._h_index(fake, urlparse("/"))
        self.assertEqual(fake.status, 200)
        self.assertIn(b"probe-ext-block", fake.body_bytes)


class ExtensionsStatusEndpointTests(unittest.TestCase):
    """GET /api/extensions returns the extensions.status() list."""

    def _patch_state(self):
        tmp = tempfile.TemporaryDirectory()
        ext_root = Path(tmp.name) / "ext"
        ext_root.mkdir()
        state_dir = Path(tmp.name) / "state"
        state_dir.mkdir()
        patches = [
            mock.patch.object(extensions, "EXTENSIONS_ROOT", ext_root),
            mock.patch.object(extensions, "ENABLED_FILE",
                              state_dir / "extensions.json"),
            mock.patch.object(cfg, "STATE_DIR", state_dir),
        ]
        for p in patches:
            p.start()
        return tmp, ext_root, patches

    def test_status_endpoint_returns_installed_extension(self):
        tmp, ext_root, patches = self._patch_state()
        try:
            shutil.copytree(FIXTURE_ROOT / "ext_hello",
                            ext_root / "ext_hello")
            fake = _FakeHandler(_FakeServer())
            server.Handler._h_extensions_status(fake, urlparse("/api/extensions"))
            self.assertEqual(fake.status, 200)
            names = [e["name"] for e in fake.payload["extensions"]]
            self.assertIn("ext_hello", names)
        finally:
            for p in patches:
                p.stop()
            tmp.cleanup()

    def test_available_endpoint_lists_catalog_entries(self):
        fake = _FakeHandler(_FakeServer())
        server.Handler._h_extensions_available(
            fake, urlparse("/api/extensions/available"))
        self.assertEqual(fake.status, 200)
        names = [e["name"] for e in fake.payload["available"]]
        self.assertIn("agent", names)

    def test_install_endpoint_rejects_unknown_name(self):
        fake = _FakeHandler(_FakeServer())
        server.Handler._h_extensions_install(
            fake, urlparse("/api/extensions/install"), {"name": "bogus"})
        self.assertEqual(fake.status, 400)
        self.assertEqual(fake.payload["stage"], "unknown")

    def test_uninstall_endpoint_rejects_missing_name(self):
        fake = _FakeHandler(_FakeServer())
        server.Handler._h_extensions_uninstall(
            fake, urlparse("/api/extensions/uninstall"), {})
        self.assertEqual(fake.status, 400)

    def test_enable_endpoint_rejects_missing_name(self):
        fake = _FakeHandler(_FakeServer())
        server.Handler._h_extensions_enable(
            fake, urlparse("/api/extensions/enable"), {})
        self.assertEqual(fake.status, 400)

    def test_enable_endpoint_flips_the_bit(self):
        tmp, ext_root, patches = self._patch_state()
        try:
            fake = _FakeHandler(_FakeServer())
            server.Handler._h_extensions_enable(
                fake, urlparse("/api/extensions/enable"), {"name": "demo"})
            self.assertEqual(fake.status, 200)
            self.assertTrue(fake.payload["ok"])
            self.assertTrue(fake.payload["restart_required"])
            # Verify persistence.
            self.assertTrue(
                (extensions._read_enabled())["demo"]["enabled"])
        finally:
            for p in patches:
                p.stop()
            tmp.cleanup()

    def test_disable_endpoint_flips_the_bit_off(self):
        tmp, ext_root, patches = self._patch_state()
        try:
            extensions.enable("demo")
            fake = _FakeHandler(_FakeServer())
            server.Handler._h_extensions_disable(
                fake, urlparse("/api/extensions/disable"), {"name": "demo"})
            self.assertEqual(fake.status, 200)
            self.assertFalse(
                (extensions._read_enabled())["demo"]["enabled"])
        finally:
            for p in patches:
                p.stop()
            tmp.cleanup()

    def test_update_endpoint_rejects_missing_name(self):
        fake = _FakeHandler(_FakeServer())
        server.Handler._h_extensions_update(
            fake, urlparse("/api/extensions/update"), {})
        self.assertEqual(fake.status, 400)

    def test_update_endpoint_surfaces_update_error_with_stage(self):
        fake = _FakeHandler(_FakeServer())
        with mock.patch.object(
            extensions, "update",
            side_effect=extensions.UpdateError("fetch", "no network"),
        ):
            server.Handler._h_extensions_update(
                fake, urlparse("/api/extensions/update"), {"name": "demo"})
        self.assertEqual(fake.status, 500)
        self.assertEqual(fake.payload["stage"], "fetch")
        self.assertIn("no network", fake.payload["error"])

    def test_update_endpoint_changed_response_signals_restart(self):
        from pathlib import Path as _Path
        result = extensions.UpdateResult(
            name="demo", from_version="0.1.0", to_version="0.2.0",
            path=_Path("/tmp/demo"), via="clone", changed=True)
        fake = _FakeHandler(_FakeServer())
        with mock.patch.object(extensions, "update", return_value=result):
            server.Handler._h_extensions_update(
                fake, urlparse("/api/extensions/update"), {"name": "demo"})
        self.assertEqual(fake.status, 200)
        self.assertTrue(fake.payload["ok"])
        self.assertTrue(fake.payload["changed"])
        self.assertTrue(fake.payload["restart_required"])
        self.assertEqual(fake.payload["from_version"], "0.1.0")
        self.assertEqual(fake.payload["to_version"], "0.2.0")

    def test_update_endpoint_unchanged_skips_restart_flag(self):
        from pathlib import Path as _Path
        result = extensions.UpdateResult(
            name="demo", from_version="0.2.0", to_version="0.2.0",
            path=_Path("/tmp/demo"), via="clone", changed=False)
        fake = _FakeHandler(_FakeServer())
        with mock.patch.object(extensions, "update", return_value=result):
            server.Handler._h_extensions_update(
                fake, urlparse("/api/extensions/update"), {"name": "demo"})
        self.assertEqual(fake.status, 200)
        self.assertFalse(fake.payload["changed"])
        self.assertFalse(fake.payload["restart_required"])


class TasksLaunchAgentExtensionGuardTests(unittest.TestCase):
    """`_h_tasks_launch` shells out to ``tb agent repl ...``. Refuse
    cleanly when the agent extension hasn't registered the verb,
    instead of spawning a tmux session that crashes silently."""

    def _server_without_agent_verb(self):
        s = _FakeServer()
        # Empty cli_verbs — no extension registered "agent".
        return s

    def _server_with_agent_verb(self):
        s = _FakeServer()
        s.extension_registry.cli_verbs["agent"] = lambda *a, **kw: None
        return s

    def test_refuses_when_agent_verb_not_registered(self):
        from lib import tasks as tasks_mod
        with mock.patch.object(tasks_mod, "get_task", return_value={
            "id": "t1", "agent": "opus", "repo_path": "/tmp",
        }):
            fake = _FakeHandler(self._server_without_agent_verb())
            server.Handler._h_tasks_launch(
                fake, urlparse("/api/tasks/launch"), {"id": "t1"})
        self.assertEqual(fake.status, 409)
        self.assertIn("agent extension", fake.payload["error"])

    def test_proceeds_when_agent_verb_registered(self):
        from lib import sessions, tasks as tasks_mod, ttyd
        with mock.patch.object(tasks_mod, "get_task", return_value={
            "id": "t1", "agent": "opus", "repo_path": "/tmp",
        }), mock.patch.object(tasks_mod, "update"), \
             mock.patch.object(sessions, "exists", return_value=True), \
             mock.patch.object(ttyd, "start", return_value={"port": 9999}):
            fake = _FakeHandler(self._server_with_agent_verb())
            server.Handler._h_tasks_launch(
                fake, urlparse("/api/tasks/launch"), {"id": "t1"})
        self.assertEqual(fake.status, 200)
        self.assertTrue(fake.payload["ok"])


class RouteTableRegistrationTests(unittest.TestCase):

    def test_core_tables_include_new_extensions_routes(self):
        self.assertIn("/api/extensions", server.Handler._GET_ROUTES)
        self.assertIn("/api/extensions/available", server.Handler._GET_ROUTES)
        self.assertIn("/api/extensions/install", server.Handler._POST_ROUTES)
        self.assertIn("/api/extensions/enable", server.Handler._POST_ROUTES)
        self.assertIn("/api/extensions/disable", server.Handler._POST_ROUTES)
        self.assertIn("/api/extensions/uninstall", server.Handler._POST_ROUTES)
        self.assertIn("/api/extensions/update", server.Handler._POST_ROUTES)


if __name__ == "__main__":
    unittest.main()
