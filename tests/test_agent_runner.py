"""Agent runner JSON extraction."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import agent_runner  # noqa: E402
from lib.errors import UsageError  # noqa: E402


class ExtractJsonTests(unittest.TestCase):

    def test_extracts_json_after_think_preamble(self):
        text = (
            "<think>I should inspect tmux state first.</think>\n\n"
            '{"type":"tool","tool":"tb_command","args":["snapshot","--json"],"stdin":""}'
        )
        data = agent_runner._extract_json(text)
        self.assertEqual(data["type"], "tool")
        self.assertEqual(data["tool"], "tb_command")

    def test_non_json_error_uses_preview_label(self):
        with self.assertRaises(UsageError) as ctx:
            agent_runner._extract_json("hello there")
        self.assertIn("preview", str(ctx.exception))

    def test_run_agent_repairs_non_json_reply(self):
        replies = iter([
            "Here's what I found in the panes.",
            '{"type":"final","message":"done"}',
        ])
        with mock.patch("lib.agent_runner.agent_providers.complete", side_effect=lambda *a, **k: next(replies)), mock.patch(
            "lib.agent_runner.agent_logs.append_entry",
        ) as append_entry:
            result = agent_runner.run_agent(
                {"name": "minimax", "model": "MiniMax-M2.7", "wire_api": "openai-chat"},
                "check panes",
                repo_root=Path("/tmp"),
                max_steps=3,
                request_timeout=1.0,
            )
        self.assertEqual(result["message"], "done")
        self.assertEqual(result["steps"], 2)
        self.assertIn("parse_error", result["transcript"][0])
        append_entry.assert_called_once()
        self.assertEqual(append_entry.call_args.args[0], "minimax")

    def test_logs_error_run(self):
        with mock.patch("lib.agent_runner.agent_providers.complete", side_effect=UsageError("bad response")), mock.patch(
            "lib.agent_runner.agent_logs.append_entry",
        ) as append_entry:
            with self.assertRaises(UsageError):
                agent_runner.run_agent(
                    {"name": "gpt", "model": "gpt-5.4", "wire_api": "openai-chat"},
                    "check panes",
                    repo_root=Path("/tmp"),
                    max_steps=3,
                    request_timeout=1.0,
                )
        self.assertEqual(append_entry.call_args.args[0], "gpt")
        self.assertEqual(append_entry.call_args.args[1]["status"], "error")

    def test_compact_snapshot_payload(self):
        payload = agent_runner._compact_json_envelope({
            "ok": True,
            "data": {
                "sessions": [{"name": "a", "windows": 1, "attached": 0}] * 10,
                "panes": [{"session": "a"}] * 20,
                "ttyd": {"running": [{"running": True}, {"running": False}]},
                "dashboard": {"listening": True},
            },
        })
        self.assertEqual(payload["kind"], "snapshot-summary")
        self.assertEqual(payload["session_count"], 10)
        self.assertEqual(len(payload["sessions"]), 8)

    def test_compact_content_payload(self):
        payload = agent_runner._compact_json_envelope({
            "ok": True,
            "data": {
                "target": "work",
                "lines": 2000,
                "content": "x" * 3000,
            },
        })
        self.assertEqual(payload["kind"], "content-preview")
        self.assertIn("[truncated]", payload["content_preview"])


if __name__ == "__main__":
    unittest.main()
