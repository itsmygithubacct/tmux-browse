"""Git worktree helpers — unit tests that don't require real git repos."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import worktrees as wt  # noqa: E402


class SlugifyTests(unittest.TestCase):

    def test_lowercase_and_dashes(self):
        self.assertEqual(wt._slugify("Fix the Bug!"), "fix-the-bug")

    def test_empty_string(self):
        self.assertEqual(wt._slugify(""), "task")

    def test_truncates_long_input(self):
        slug = wt._slugify("a" * 100)
        self.assertLessEqual(len(slug), 60)


if __name__ == "__main__":
    unittest.main()
