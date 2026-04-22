"""Background workflow scheduler."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import agent_scheduler as sched  # noqa: E402
from lib.agent_providers import ProviderResult  # noqa: E402


class SchedulerTickTests(unittest.TestCase):
    """Unit-test the scheduler's _tick logic without threads."""

    def _make_scheduler(self):
        s = sched.Scheduler(repo_root=Path("/tmp"))
        return s

    def test_tick_skips_disabled_agents(self):
        s = self._make_scheduler()
        wf = {"agents": {"gpt": {
            "enabled": False,
            "workflows": [{"name": "check", "prompt": "check all", "interval_seconds": 60}],
        }}}
        with mock.patch("lib.agent_scheduler.agent_scheduler_lock.is_owned", return_value=True), \
             mock.patch("lib.agent_scheduler.agent_workflows.load", return_value=wf), \
             mock.patch("lib.agent_scheduler.agent_workflow_runs.is_due") as is_due:
            s._tick()
        is_due.assert_not_called()

    def test_tick_skips_empty_prompts(self):
        s = self._make_scheduler()
        wf = {"agents": {"gpt": {
            "enabled": True,
            "workflows": [{"name": "empty", "prompt": "", "interval_seconds": 60}],
        }}}
        with mock.patch("lib.agent_scheduler.agent_scheduler_lock.is_owned", return_value=True), \
             mock.patch("lib.agent_scheduler.agent_workflows.load", return_value=wf), \
             mock.patch("lib.agent_scheduler.agent_workflow_runs.is_due") as is_due:
            s._tick()
        is_due.assert_not_called()

    def test_tick_runs_due_workflow(self):
        s = self._make_scheduler()
        wf = {"agents": {"gpt": {
            "enabled": True,
            "workflows": [{"name": "check", "prompt": "check all", "interval_seconds": 60}],
        }}}
        with mock.patch("lib.agent_scheduler.agent_scheduler_lock.is_owned", return_value=True), \
             mock.patch("lib.agent_scheduler.agent_workflows.load", return_value=wf), \
             mock.patch("lib.agent_scheduler.agent_workflow_runs.is_due", return_value=True), \
             mock.patch.object(s, "_run_workflow") as run_wf:
            s._tick()
        run_wf.assert_called_once_with("gpt", 0, "check all", 60)

    def test_tick_skips_not_due_workflow(self):
        s = self._make_scheduler()
        wf = {"agents": {"gpt": {
            "enabled": True,
            "workflows": [{"name": "check", "prompt": "check all", "interval_seconds": 60}],
        }}}
        with mock.patch("lib.agent_scheduler.agent_scheduler_lock.is_owned", return_value=True), \
             mock.patch("lib.agent_scheduler.agent_workflows.load", return_value=wf), \
             mock.patch("lib.agent_scheduler.agent_workflow_runs.is_due", return_value=False), \
             mock.patch.object(s, "_run_workflow") as run_wf:
            s._tick()
        run_wf.assert_not_called()

    def test_tick_skips_when_not_lock_owner(self):
        s = self._make_scheduler()
        with mock.patch("lib.agent_scheduler.agent_scheduler_lock.is_owned", return_value=False), \
             mock.patch("lib.agent_scheduler.agent_workflows.load") as load:
            s._tick()
        load.assert_not_called()


class RunWorkflowTests(unittest.TestCase):

    def test_records_ok_result(self):
        s = sched.Scheduler(repo_root=Path("/tmp"))
        agent = {"name": "gpt", "model": "m", "wire_api": "openai-chat", "api_key": "k", "base_url": "http://x"}
        with mock.patch("lib.agent_scheduler.agent_store.get_agent", return_value=agent), \
             mock.patch("lib.agent_scheduler.agent_runner.run_agent", return_value={"message": "ok"}), \
             mock.patch("lib.agent_scheduler.agent_workflow_runs.record_result") as rec:
            s._run_workflow("gpt", 0, "check all", 60)
        rec.assert_called_once()
        self.assertEqual(rec.call_args.kwargs["status"], "ok")

    def test_records_error_result(self):
        s = sched.Scheduler(repo_root=Path("/tmp"))
        agent = {"name": "gpt", "model": "m", "wire_api": "openai-chat", "api_key": "k", "base_url": "http://x"}
        with mock.patch("lib.agent_scheduler.agent_store.get_agent", return_value=agent), \
             mock.patch("lib.agent_scheduler.agent_runner.run_agent", side_effect=Exception("fail")), \
             mock.patch("lib.agent_scheduler.agent_workflow_runs.record_result") as rec:
            s._run_workflow("gpt", 0, "check all", 60)
        rec.assert_called_once()
        self.assertEqual(rec.call_args.kwargs["status"], "error")
        self.assertIn("fail", rec.call_args.kwargs["error"])

    def test_records_error_when_agent_not_configured(self):
        s = sched.Scheduler(repo_root=Path("/tmp"))
        with mock.patch("lib.agent_scheduler.agent_store.get_agent", side_effect=Exception("not found")), \
             mock.patch("lib.agent_scheduler.agent_workflow_runs.record_result") as rec:
            s._run_workflow("missing", 0, "check all", 60)
        rec.assert_called_once()
        self.assertEqual(rec.call_args.kwargs["status"], "error")
        self.assertIn("not configured", rec.call_args.kwargs["error"])


if __name__ == "__main__":
    unittest.main()
