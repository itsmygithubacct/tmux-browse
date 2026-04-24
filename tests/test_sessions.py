"""Session enumeration — primarily the group-dedup logic that hides
ttyd_wrap.sh's per-viewer grouped sessions from the dashboard and CLI."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import sessions  # noqa: E402


def _tmux_row(name, group, windows=1, attached=0, created=1000, activity=1100):
    """Build one tab-separated row matching _SESSION_FORMAT."""
    return f"{name}\t{windows}\t{attached}\t{created}\t{activity}\t{group}"


class ListSessionsDedupTests(unittest.TestCase):

    def _run(self, rows):
        mock_proc = mock.Mock(returncode=0, stdout="\n".join(rows) + "\n")
        with mock.patch("lib.sessions.subprocess.run", return_value=mock_proc):
            return sessions.list_sessions()

    def test_ungrouped_sessions_pass_through(self):
        rows = [_tmux_row("work", ""), _tmux_row("notes", "")]
        out = self._run(rows)
        self.assertEqual([r["name"] for r in out], ["notes", "work"])

    def test_primary_wins_over_viewers(self):
        rows = [
            _tmux_row("claude_code", "claude_code"),
            _tmux_row("claude_code-v1-1", "claude_code"),
            _tmux_row("claude_code-v1-2", "claude_code"),
        ]
        out = self._run(rows)
        names = [r["name"] for r in out]
        self.assertEqual(names, ["claude_code"])

    def test_orphan_group_keeps_one_viewer(self):
        # No primary present — one viewer survives so the work is still
        # reachable in the listing.
        rows = [
            _tmux_row("music-v1-1", "music"),
            _tmux_row("music-v2-2", "music"),
        ]
        out = self._run(rows)
        names = [r["name"] for r in out]
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].startswith("music-v"))

    def test_mixed_groups_and_ungrouped(self):
        rows = [
            _tmux_row("scratch", ""),
            _tmux_row("claude_code", "claude_code"),
            _tmux_row("claude_code-v1-1", "claude_code"),
            _tmux_row("orphan-v1-1", "orphan"),
        ]
        out = self._run(rows)
        names = sorted(r["name"] for r in out)
        self.assertEqual(len(names), 3)
        self.assertIn("scratch", names)
        self.assertIn("claude_code", names)
        self.assertTrue(any(n.startswith("orphan-v") for n in names))

    def test_primary_wins_regardless_of_ordering(self):
        # Viewer comes first in tmux output, primary second — primary still wins.
        rows = [
            _tmux_row("claude_code-v1-1", "claude_code"),
            _tmux_row("claude_code", "claude_code"),
        ]
        out = self._run(rows)
        self.assertEqual([r["name"] for r in out], ["claude_code"])

    def test_attached_and_activity_fields_preserved(self):
        rows = [_tmux_row("work", "", attached=3, activity=2500)]
        out = self._run(rows)
        self.assertEqual(out[0]["attached"], 3)
        self.assertEqual(out[0]["activity"], 2500)


if __name__ == "__main__":
    unittest.main()
