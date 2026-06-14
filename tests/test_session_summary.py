"""Direct coverage for server._session_summary — the core row builder
behind every dashboard refresh. Exercises the degradation and
row-synthesis branches with all I/O mocked.
"""

from __future__ import annotations

import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import host_identity as hi, server  # noqa: E402


def _tmux_row(name, *, windows=1, attached=0, created=1000, activity=2000):
    return {"name": name, "windows": windows, "attached": attached,
            "created": created, "activity": activity}


class SessionSummaryTests(unittest.TestCase):

    def _summary(self, *, responsive=True, tmux_rows=None,
                 assignments=None, pids=None):
        tmux_rows = tmux_rows or []
        assignments = assignments or {}
        pids = pids or {}
        with ExitStack() as es:
            p = es.enter_context
            p(mock.patch.object(server.sessions, "server_responsive",
                                return_value=responsive))
            p(mock.patch.object(server.sessions, "list_sessions",
                                return_value=tmux_rows))
            p(mock.patch.object(server.session_logs, "ensure_logging_all"))
            p(mock.patch.object(server.session_logs, "idle_seconds",
                                return_value=None))
            p(mock.patch.object(server.ports, "all_assignments",
                                return_value=assignments))
            p(mock.patch.object(server.ttyd, "read_pid",
                                side_effect=lambda name: pids.get(name)))
            p(mock.patch.object(server.sessions, "get_cached_snapshot",
                                return_value=""))
            p(mock.patch.object(server.sessions, "gc_snapshots"))
            p(mock.patch.object(hi, "get_or_create_device_id",
                                return_value="dev-1"))
            p(mock.patch.object(hi, "get_hostname", return_value="host-c"))
            # merge_peers=False keeps this to local rows only.
            return server._session_summary(merge_peers=False)

    def test_tmux_unreachable_sets_flag_and_skips_listing(self):
        summary = self._summary(responsive=False,
                                assignments={"work": 7700},
                                pids={"work": 123})
        self.assertTrue(summary.tmux_unreachable)
        # A non-raw assignment is NOT synthesized into a row.
        self.assertEqual(summary.rows, [])

    def test_normal_tmux_session_row(self):
        summary = self._summary(
            tmux_rows=[_tmux_row("work")],
            assignments={"work": 7700}, pids={"work": 123})
        self.assertFalse(summary.tmux_unreachable)
        self.assertEqual(len(summary.rows), 1)
        r = summary.rows[0]
        self.assertEqual(r["kind"], "tmux")
        self.assertEqual(r["name"], "work")
        self.assertEqual(r["port"], 7700)
        self.assertEqual(r["pid"], 123)
        self.assertTrue(r["ttyd_running"])
        self.assertEqual(r["device_id"], "dev-1")
        self.assertEqual(r["peer_hostname"], "host-c")

    def test_tmux_session_without_ttyd_is_not_running(self):
        summary = self._summary(
            tmux_rows=[_tmux_row("work")], assignments={"work": 7700}, pids={})
        r = summary.rows[0]
        self.assertIsNone(r["pid"])
        self.assertFalse(r["ttyd_running"])

    def test_idle_falls_back_to_activity_when_no_log(self):
        # idle_seconds() mocked to None -> idle = now - activity.
        summary = self._summary(
            tmux_rows=[_tmux_row("work", activity=0)],
            assignments={}, pids={})
        self.assertGreater(summary.rows[0]["idle_seconds"], 0)

    def test_live_raw_shell_is_synthesized(self):
        summary = self._summary(
            assignments={"raw-shell-abc": 7701}, pids={"raw-shell-abc": 999})
        self.assertEqual(len(summary.rows), 1)
        r = summary.rows[0]
        self.assertEqual(r["kind"], "raw")
        self.assertEqual(r["port"], 7701)
        self.assertTrue(r["ttyd_running"])
        self.assertEqual(r["idle_seconds"], 0)

    def test_dead_raw_shell_is_skipped(self):
        summary = self._summary(
            assignments={"raw-shell-abc": 7701}, pids={})  # read_pid -> None
        self.assertEqual(summary.rows, [])

    def test_non_raw_orphan_assignment_is_skipped(self):
        # An assignment that's neither a live tmux session nor a raw-shell-*
        # name contributes nothing.
        summary = self._summary(
            assignments={"ghost": 7702}, pids={"ghost": 5})
        self.assertEqual(summary.rows, [])

    # --- per-request snapshot budget (degradation branch) ----------------

    def _summary_over_budget(self, *, seed_cache):
        """Run _session_summary with the 200ms snapshot budget already
        exhausted. Returns (summary, get_cached_snapshot_mock)."""
        row = _tmux_row("work")
        with ExitStack() as es:
            p = es.enter_context
            p(mock.patch.object(server.sessions, "server_responsive",
                                return_value=True))
            p(mock.patch.object(server.sessions, "list_sessions",
                                return_value=[row]))
            p(mock.patch.object(server.session_logs, "ensure_logging_all"))
            p(mock.patch.object(server.session_logs, "idle_seconds",
                                return_value=None))
            p(mock.patch.object(server.ports, "all_assignments",
                                return_value={"work": 7700}))
            p(mock.patch.object(server.ttyd, "read_pid",
                                side_effect=lambda n: None))
            gcs = p(mock.patch.object(server.sessions, "get_cached_snapshot"))
            p(mock.patch.object(server.sessions, "gc_snapshots"))
            p(mock.patch.object(hi, "get_or_create_device_id",
                                return_value="dev"))
            p(mock.patch.object(hi, "get_hostname", return_value="h"))
            # First perf_counter call sets the deadline; every later call is
            # well past it, forcing the over-budget branch.
            p(mock.patch.object(server.time, "perf_counter",
                                side_effect=[1000.0] + [2000.0] * 20))
            server.sessions._snapshot_cache.pop("work", None)
            if seed_cache is not None:
                server.sessions._snapshot_cache["work"] = (123, seed_cache)
            try:
                return server._session_summary(merge_peers=False), gcs
            finally:
                server.sessions._snapshot_cache.pop("work", None)

    def test_over_budget_serves_cached_snapshot_without_recapture(self):
        summary, gcs = self._summary_over_budget(seed_cache="STALE-SNAP")
        self.assertEqual(summary.rows[0]["snapshot"], "STALE-SNAP")
        gcs.assert_not_called()  # over budget: must not re-capture

    def test_over_budget_empty_snapshot_when_no_cache(self):
        summary, gcs = self._summary_over_budget(seed_cache=None)
        self.assertEqual(summary.rows[0]["snapshot"], "")
        gcs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
