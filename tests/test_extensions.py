"""Extension loader substrate — manifest parsing, single-extension
load, registration merging, UI-block parsing."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import extensions  # noqa: E402
from lib import config as cfg  # noqa: E402
from lib.extensions import loader as loader_mod  # noqa: E402
from lib.extensions import manifest as manifest_mod  # noqa: E402
from lib.extensions import registry as registry_mod  # noqa: E402


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


class ManifestTests(unittest.TestCase):

    def _write(self, tmp: Path, data: dict) -> Path:
        path = tmp / "manifest.json"
        path.write_text(json.dumps(data))
        return path

    def test_valid_manifest_round_trips(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(Path(d), {
                "name": "x", "version": "1.0", "module": "x",
                "min_tmux_browse": "0.7.0.4",
                "routes_entry": "x:register",
            })
            m = manifest_mod.Manifest.load(path)
        self.assertEqual(m.name, "x")
        self.assertEqual(m.routes_entry, "x:register")
        self.assertIsNone(m.cli_entry)

    def test_rejects_missing_required_keys(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(Path(d), {"name": "x", "version": "1.0"})
            with self.assertRaises(manifest_mod.ManifestError):
                manifest_mod.Manifest.load(path)

    def test_rejects_unknown_keys(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(Path(d), {
                "name": "x", "version": "1", "module": "x",
                "min_tmux_browse": "0.7.0.4", "routes_entry": "x:register",
                "surprise_field": "nope",
            })
            with self.assertRaises(manifest_mod.ManifestError):
                manifest_mod.Manifest.load(path)

    def test_rejects_wrong_type(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(Path(d), {
                "name": "x", "version": "1", "module": "x",
                "min_tmux_browse": "0.7.0.4", "state_paths": "not-a-list",
                "routes_entry": "x:register",
            })
            with self.assertRaises(manifest_mod.ManifestError):
                manifest_mod.Manifest.load(path)

    def test_validate_rejects_too_new(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(Path(d), {
                "name": "x", "version": "1", "module": "x",
                "min_tmux_browse": "9.9.9",
                "routes_entry": "x:register",
            })
            m = manifest_mod.Manifest.load(path)
        with self.assertRaises(manifest_mod.ManifestError):
            m.validate(core_version="0.7.0.4")

    def test_validate_requires_at_least_one_entry_point(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(Path(d), {
                "name": "x", "version": "1", "module": "x",
                "min_tmux_browse": "0.1.0",
            })
            m = manifest_mod.Manifest.load(path)
        with self.assertRaises(manifest_mod.ManifestError):
            m.validate(core_version="0.7.0.4")


class UiBlocksTests(unittest.TestCase):

    def test_parse_ui_blocks(self):
        blocks = registry_mod.parse_ui_blocks(
            FIXTURE_ROOT / "ext_hello" / "ui_blocks.html")
        self.assertIn("topbar_extras", blocks)
        self.assertIn("config_extras", blocks)
        self.assertIn("ext_hello loaded", blocks["topbar_extras"])


class LoadOneTests(unittest.TestCase):

    def test_loads_hello_fixture(self):
        reg = loader_mod.load_one(
            FIXTURE_ROOT / "ext_hello", core_version="0.7.0.4")
        self.assertIn("/api/ext-hello", reg.get_routes)
        self.assertIn("hello", reg.cli_verbs)
        self.assertIn("topbar_extras", reg.ui_blocks)
        self.assertTrue(any(p.name == "hello.js" for p in reg.static_js))

    def test_missing_manifest_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(loader_mod.ExtensionLoadError) as ctx:
                loader_mod.load_one(Path(d), core_version="0.7.0.4")
        self.assertEqual(ctx.exception.stage, "manifest")

    def test_invalid_entry_point_raises(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "manifest.json").write_text(json.dumps({
                "name": "ext_broken", "version": "0", "module": "ext_broken",
                "min_tmux_browse": "0.1.0",
                "routes_entry": "nowhere:register",
            }))
            with self.assertRaises(loader_mod.ExtensionLoadError) as ctx:
                loader_mod.load_one(tmp, core_version="0.7.0.4")
        self.assertEqual(ctx.exception.stage, "import")


class MergedRegistryTests(unittest.TestCase):

    def test_merge_adds_routes(self):
        merged = registry_mod.MergedRegistry()
        reg = registry_mod.Registration(
            name="a",
            get_routes={"/api/a": lambda *x: None},
            post_routes={"/api/a/save": lambda *x: None},
        )
        merged.add(reg)
        self.assertIn("/api/a", merged.get_routes)
        self.assertIn("/api/a/save", merged.post_routes)

    def test_route_collision_with_core_raises(self):
        merged = registry_mod.MergedRegistry()
        reg = registry_mod.Registration(
            name="a", get_routes={"/api/sessions": lambda *x: None})
        with self.assertRaises(registry_mod.RegistryConflict) as ctx:
            merged.add(reg, core_get_routes={"/api/sessions"})
        self.assertIn("core", str(ctx.exception))

    def test_route_collision_between_extensions_raises(self):
        merged = registry_mod.MergedRegistry()
        merged.add(registry_mod.Registration(
            name="a", get_routes={"/api/shared": lambda *x: None}))
        with self.assertRaises(registry_mod.RegistryConflict):
            merged.add(registry_mod.Registration(
                name="b", get_routes={"/api/shared": lambda *x: None}))

    def test_cli_verb_collision_with_core_raises(self):
        merged = registry_mod.MergedRegistry()
        with self.assertRaises(registry_mod.RegistryConflict):
            merged.add(
                registry_mod.Registration(
                    name="a", cli_verbs={"agent": lambda *a: None}),
                core_cli_verbs={"agent"})

    def test_slot_collision_raises(self):
        merged = registry_mod.MergedRegistry()
        merged.add(registry_mod.Registration(
            name="a", ui_blocks={"topbar_extras": "<a/>"}))
        with self.assertRaises(registry_mod.RegistryConflict):
            merged.add(registry_mod.Registration(
                name="b", ui_blocks={"topbar_extras": "<b/>"}))


class _IsolatedExtensions:
    """Point EXTENSIONS_ROOT + ENABLED_FILE at a tempdir so tests don't
    see whatever the host has installed."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._state = tempfile.TemporaryDirectory()
        self._ext_root = Path(self._tmp.name)
        self._enabled_file = Path(self._state.name) / "extensions.json"
        self._patches = [
            mock.patch.object(extensions, "EXTENSIONS_ROOT", self._ext_root),
            mock.patch.object(extensions, "ENABLED_FILE", self._enabled_file),
            mock.patch.object(cfg, "STATE_DIR", Path(self._state.name)),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()
        self._state.cleanup()

    def _install_fixture(self, fixture_name: str, dest_name: str | None = None):
        dest = self._ext_root / (dest_name or fixture_name)
        shutil.copytree(FIXTURE_ROOT / fixture_name, dest)
        return dest


class DiscoverAndStatusTests(_IsolatedExtensions, unittest.TestCase):

    def test_empty_discover(self):
        self.assertEqual(extensions.discover(), [])
        self.assertEqual(extensions.status(), [])

    def test_status_reports_discovered_extension(self):
        self._install_fixture("ext_hello")
        rows = extensions.status()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "ext_hello")
        self.assertTrue(rows[0]["installed"])
        self.assertFalse(rows[0]["enabled"])
        self.assertEqual(rows[0]["version"], "0.0.1")

    def test_enable_and_disable_round_trip(self):
        self._install_fixture("ext_hello")
        extensions.enable("ext_hello")
        self.assertTrue(extensions.status()[0]["enabled"])
        extensions.disable("ext_hello")
        self.assertFalse(extensions.status()[0]["enabled"])

    def test_status_surfaces_enabled_name_with_no_directory(self):
        extensions.enable("ghost")
        rows = extensions.status()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "ghost")
        self.assertFalse(rows[0]["installed"])


class LoadEnabledTests(_IsolatedExtensions, unittest.TestCase):

    def test_empty_when_nothing_enabled(self):
        self._install_fixture("ext_hello")
        merged = extensions.load_enabled(core_version_override="0.7.0.4")
        self.assertEqual(merged.get_routes, {})

    def test_loads_enabled_extension(self):
        self._install_fixture("ext_hello")
        extensions.enable("ext_hello")
        merged = extensions.load_enabled(core_version_override="0.7.0.4")
        self.assertIn("/api/ext-hello", merged.get_routes)
        self.assertIn("hello", merged.cli_verbs)
        self.assertIn("topbar_extras", merged.ui_blocks)

    def test_core_route_collision_raises(self):
        self._install_fixture("ext_bad_collide")
        extensions.enable("ext_bad_collide")
        with self.assertRaises(registry_mod.RegistryConflict):
            extensions.load_enabled(
                core_get_routes={"/api/sessions"},
                core_version_override="0.7.0.4")

    def test_bad_extension_is_skipped_not_fatal(self):
        """A failed extension load records its error and is skipped;
        other extensions continue to load."""
        self._install_fixture("ext_hello")
        extensions.enable("ext_hello")
        # Inject a broken extension next to the hello one.
        broken = self._ext_root / "ext_broken"
        broken.mkdir()
        (broken / "manifest.json").write_text(json.dumps({
            "name": "ext_broken", "version": "0", "module": "ext_broken",
            "min_tmux_browse": "0.1.0", "routes_entry": "nowhere:register",
        }))
        extensions.enable("ext_broken")
        merged = extensions.load_enabled(core_version_override="0.7.0.4")
        # Hello's route is present despite broken failing.
        self.assertIn("/api/ext-hello", merged.get_routes)
        # Broken's error is persisted.
        rows = {r["name"]: r for r in extensions.status()}
        self.assertIsNotNone(rows["ext_broken"]["last_error"])


class TemplateSlotTests(unittest.TestCase):

    def test_default_render_consumes_all_slot_markers(self):
        from lib import templates
        html = templates.render_index()
        self.assertNotIn("<!--slot:", html,
                         "an unreplaced slot marker leaked into output")

    def test_filled_slot_renders_content(self):
        from lib import templates
        html = templates.render_index(
            ui_blocks={"topbar_extras": "<span id=\"injected-topbar\"/>"})
        self.assertIn("injected-topbar", html)

    def test_missing_slot_substitutes_empty(self):
        from lib import templates
        # ui_blocks has a name that doesn't match any marker → harmless.
        html = templates.render_index(
            ui_blocks={"there_is_no_such_slot_marker": "<x/>"})
        self.assertNotIn("there_is_no_such_slot_marker", html)


class BuildJsTests(unittest.TestCase):

    def test_build_js_no_extensions_returns_core_bundle(self):
        from lib import static
        self.assertEqual(static.build_js(None), static.JS)
        self.assertEqual(static.build_js([]), static.JS)

    def test_build_js_appends_extension_js(self):
        from lib import static
        hello = FIXTURE_ROOT / "ext_hello" / "static" / "hello.js"
        bundle = static.build_js([hello])
        self.assertIn(static.JS, bundle)
        self.assertIn("__extHelloLoaded", bundle)
        self.assertIn("window.__tbExtensions", bundle)

    def test_build_js_skips_missing_extension_file(self):
        from lib import static
        missing = FIXTURE_ROOT / "ext_hello" / "static" / "does_not_exist.js"
        # Should not raise.
        bundle = static.build_js([missing])
        self.assertIn(static.JS, bundle)


if __name__ == "__main__":
    unittest.main()
