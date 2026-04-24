"""End-to-end sanity for the agent extension's load lifecycle.

Proves that the E0 loader actually wires the agent extension's routes,
UI blocks, static JS, CLI verb, and startup/shutdown hooks to core when
enabled — and that disabling it removes the entire agent surface
without breaking the rest of the dashboard.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config as cfg  # noqa: E402
from lib import extensions  # noqa: E402


class AgentExtensionLifecycleTests(unittest.TestCase):

    def setUp(self):
        self._state = tempfile.TemporaryDirectory()
        state_path = Path(self._state.name)
        self._enabled_file = state_path / "extensions.json"
        self._patches = [
            mock.patch.object(cfg, "STATE_DIR", state_path),
            mock.patch.object(extensions, "ENABLED_FILE", self._enabled_file),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._state.cleanup()

    def test_bootstrap_enables_bundled_agent_extension(self):
        extensions.bootstrap_default_enabled()
        self.assertTrue(self._enabled_file.exists())
        data = json.loads(self._enabled_file.read_text())
        self.assertIn("agent", data)
        self.assertTrue(data["agent"]["enabled"])

    def test_load_enabled_returns_agent_surface(self):
        extensions.bootstrap_default_enabled()
        reg = extensions.load_enabled(core_version_override="0.7.0.4")
        # Routes from server/routes.py
        self.assertIn("/api/agents", reg.get_routes)
        self.assertIn("/api/agents", reg.post_routes)
        self.assertIn("/api/agent-log", reg.get_routes)
        # CLI verb from tb_cmds/agent.py
        self.assertIn("agent", reg.cli_verbs)
        # UI blocks from ui_blocks.html
        self.assertIn("agents_section", reg.ui_blocks)
        self.assertIn("config_agent", reg.ui_blocks)
        # Static JS from static/
        self.assertEqual(
            sorted(p.name for p in reg.static_js),
            ["agents.js", "runs.js", "tasks.js"],
        )
        # Startup + shutdown hooks from startup.py
        self.assertEqual(len(reg.startup), 1)
        self.assertEqual(len(reg.shutdown), 1)

    def test_disable_removes_agent_surface(self):
        extensions.bootstrap_default_enabled()
        extensions.disable("agent")
        reg = extensions.load_enabled(core_version_override="0.7.0.4")
        self.assertEqual(reg.get_routes, {})
        self.assertEqual(reg.post_routes, {})
        self.assertEqual(reg.ui_blocks, {})
        self.assertEqual(reg.static_js, [])
        self.assertEqual(reg.cli_verbs, {})

    def test_bootstrap_preserves_operator_decisions(self):
        # When the operator has already set state, bootstrap leaves it
        # alone. This matters most for disabled-by-operator extensions
        # that must not get silently re-enabled on every boot.
        self._enabled_file.write_text(json.dumps({
            "agent": {"enabled": False, "disabled_ts": 1, "source": "user"},
        }))
        extensions.bootstrap_default_enabled()
        state = json.loads(self._enabled_file.read_text())
        self.assertFalse(state["agent"]["enabled"])


if __name__ == "__main__":
    unittest.main()
