"""Agent status derivation from logs and workflow config."""

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import agent_status as st  # noqa: E402
from lib.agent_runs import (  # noqa: E402
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_RATE_LIMITED,
    STATUS_STARTED,
)


class StatusDerivationTests(unittest.TestCase):

    def test_no_log_entry_returns_idle(self):
        with mock.patch("lib.agent_status.agent_logs.get_latest_entry", return_value=None), \
             mock.patch("lib.agent_status._workflow_paused", return_value=False):
            result = st.get_status("gpt")
        self.assertEqual(result["status"], st.AgentStatus.IDLE)
        self.assertEqual(result["last_ts"], 0)

    def test_recent_run_started_returns_running(self):
        now = int(time.time())
        entry = {"ts": now - 10, "status": STATUS_STARTED, "prompt": "check sessions"}
        with mock.patch("lib.agent_status.agent_logs.get_latest_entry", return_value=entry), \
             mock.patch("lib.agent_status._workflow_paused", return_value=False):
            result = st.get_status("gpt")
        self.assertEqual(result["status"], st.AgentStatus.RUNNING)
        self.assertIn("check sessions", result["reason"])

    def test_old_run_started_returns_idle_stalled(self):
        now = int(time.time())
        entry = {"ts": now - 600, "status": STATUS_STARTED, "prompt": "check sessions"}
        with mock.patch("lib.agent_status.agent_logs.get_latest_entry", return_value=entry), \
             mock.patch("lib.agent_status._workflow_paused", return_value=False):
            result = st.get_status("gpt")
        self.assertEqual(result["status"], st.AgentStatus.IDLE)
        self.assertIn("stalled", result["reason"])

    def test_run_completed_returns_idle_with_message(self):
        now = int(time.time())
        entry = {"ts": now - 30, "status": STATUS_COMPLETED, "message": "found 3 sessions"}
        with mock.patch("lib.agent_status.agent_logs.get_latest_entry", return_value=entry), \
             mock.patch("lib.agent_status._workflow_paused", return_value=False):
            result = st.get_status("gpt")
        self.assertEqual(result["status"], st.AgentStatus.IDLE)
        self.assertIn("found 3 sessions", result["reason"])

    def test_run_failed_returns_error(self):
        now = int(time.time())
        entry = {"ts": now - 30, "status": STATUS_FAILED, "error": "connection refused"}
        with mock.patch("lib.agent_status.agent_logs.get_latest_entry", return_value=entry), \
             mock.patch("lib.agent_status._workflow_paused", return_value=False):
            result = st.get_status("gpt")
        self.assertEqual(result["status"], st.AgentStatus.ERROR)
        self.assertIn("connection refused", result["reason"])

    def test_rate_limited_returns_rate_limited(self):
        now = int(time.time())
        entry = {"ts": now - 5, "status": STATUS_RATE_LIMITED, "error": "429 Too Many Requests"}
        with mock.patch("lib.agent_status.agent_logs.get_latest_entry", return_value=entry), \
             mock.patch("lib.agent_status._workflow_paused", return_value=False):
            result = st.get_status("gpt")
        self.assertEqual(result["status"], st.AgentStatus.RATE_LIMITED)

    def test_workflow_paused_returns_workflow_paused(self):
        now = int(time.time())
        entry = {"ts": now - 30, "status": STATUS_COMPLETED, "message": "ok"}
        with mock.patch("lib.agent_status.agent_logs.get_latest_entry", return_value=entry), \
             mock.patch("lib.agent_status._workflow_paused", return_value=True):
            result = st.get_status("gpt")
        self.assertEqual(result["status"], st.AgentStatus.WORKFLOW_PAUSED)

    def test_workflow_paused_no_logs(self):
        with mock.patch("lib.agent_status.agent_logs.get_latest_entry", return_value=None), \
             mock.patch("lib.agent_status._workflow_paused", return_value=True):
            result = st.get_status("gpt")
        self.assertEqual(result["status"], st.AgentStatus.WORKFLOW_PAUSED)


class WorkflowPausedTests(unittest.TestCase):

    def test_no_workflows_not_paused(self):
        with mock.patch("lib.agent_status.agent_workflows.load", return_value={"agents": {}}):
            self.assertFalse(st._workflow_paused("gpt"))

    def test_enabled_workflows_not_paused(self):
        wf = {"agents": {"gpt": {
            "enabled": True,
            "workflows": [{"name": "check", "prompt": "check all", "interval_seconds": 60}],
        }}}
        with mock.patch("lib.agent_status.agent_workflows.load", return_value=wf):
            self.assertFalse(st._workflow_paused("gpt"))

    def test_disabled_workflows_is_paused(self):
        wf = {"agents": {"gpt": {
            "enabled": False,
            "workflows": [{"name": "check", "prompt": "check all", "interval_seconds": 60}],
        }}}
        with mock.patch("lib.agent_status.agent_workflows.load", return_value=wf):
            self.assertTrue(st._workflow_paused("gpt"))

    def test_empty_workflows_not_paused(self):
        wf = {"agents": {"gpt": {
            "enabled": False,
            "workflows": [{"name": "", "prompt": "", "interval_seconds": 300}],
        }}}
        with mock.patch("lib.agent_status.agent_workflows.load", return_value=wf):
            self.assertFalse(st._workflow_paused("gpt"))


class GetAllStatusesTests(unittest.TestCase):

    def test_returns_status_for_each_agent(self):
        agents = [
            {"name": "gpt", "provider": "openai"},
            {"name": "opus", "provider": "anthropic"},
        ]
        with mock.patch("lib.agent_status.agent_store.list_agents", return_value=agents), \
             mock.patch("lib.agent_status.agent_logs.get_latest_entry", return_value=None), \
             mock.patch("lib.agent_status._workflow_paused", return_value=False):
            result = st.get_all_statuses()
        self.assertIn("gpt", result)
        self.assertIn("opus", result)
        self.assertEqual(result["gpt"]["status"], st.AgentStatus.IDLE)


if __name__ == "__main__":
    unittest.main()
