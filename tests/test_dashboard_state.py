"""Dashboard state-file lifecycle (lib/server._write/_clear_dashboard_state).

~/.tmux-browse/dashboard.json records the running dashboard's pid/bind/
port so bin/update.sh can find and restart it. _clear_dashboard_state
must only delete the file when it belongs to *this* process — otherwise
a second instance (or a crashed-then-restarted one) could wipe a live
dashboard's state out from under update.sh.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import server  # noqa: E402


class DashboardStateTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "dashboard.json"
        self._patch = mock.patch.object(server.config, "DASHBOARD_FILE", self.path)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_write_records_pid_bind_port(self):
        server._write_dashboard_state("0.0.0.0", 8096)
        data = json.loads(self.path.read_text())
        self.assertEqual(data["pid"], os.getpid())
        self.assertEqual(data["bind"], "0.0.0.0")
        self.assertEqual(data["port"], 8096)
        self.assertIn("started_at", data)

    def test_clear_removes_own_state(self):
        server._write_dashboard_state("127.0.0.1", 8096)
        self.assertTrue(self.path.exists())
        server._clear_dashboard_state()
        self.assertFalse(self.path.exists())

    def test_clear_keeps_other_process_state(self):
        # A state file owned by a different pid must survive our clear,
        # so we never wipe another running dashboard's record.
        self.path.write_text(json.dumps(
            {"pid": os.getpid() + 1, "bind": "0.0.0.0", "port": 8096,
             "started_at": 0}))
        server._clear_dashboard_state()
        self.assertTrue(self.path.exists(),
                        "must not delete a state file owned by another pid")

    def test_clear_removes_corrupt_state(self):
        self.path.write_text("{ not json")
        server._clear_dashboard_state()
        self.assertFalse(self.path.exists())

    def test_clear_when_absent_is_noop(self):
        self.assertFalse(self.path.exists())
        server._clear_dashboard_state()  # must not raise
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
