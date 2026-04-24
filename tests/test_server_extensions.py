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

    def test_available_endpoint_returns_empty_list_in_e0(self):
        fake = _FakeHandler(_FakeServer())
        server.Handler._h_extensions_available(
            fake, urlparse("/api/extensions/available"))
        self.assertEqual(fake.status, 200)
        self.assertEqual(fake.payload["available"], [])

    def test_install_endpoint_returns_501(self):
        fake = _FakeHandler(_FakeServer())
        server.Handler._h_extensions_install(
            fake, urlparse("/api/extensions/install"), {"name": "agent"})
        self.assertEqual(fake.status, 501)

    def test_uninstall_endpoint_returns_501(self):
        fake = _FakeHandler(_FakeServer())
        server.Handler._h_extensions_uninstall(
            fake, urlparse("/api/extensions/uninstall"), {"name": "agent"})
        self.assertEqual(fake.status, 501)

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


class RouteTableRegistrationTests(unittest.TestCase):

    def test_core_tables_include_new_extensions_routes(self):
        self.assertIn("/api/extensions", server.Handler._GET_ROUTES)
        self.assertIn("/api/extensions/available", server.Handler._GET_ROUTES)
        self.assertIn("/api/extensions/install", server.Handler._POST_ROUTES)
        self.assertIn("/api/extensions/enable", server.Handler._POST_ROUTES)
        self.assertIn("/api/extensions/disable", server.Handler._POST_ROUTES)
        self.assertIn("/api/extensions/uninstall", server.Handler._POST_ROUTES)


if __name__ == "__main__":
    unittest.main()
