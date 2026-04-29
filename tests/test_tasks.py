"""Task CRUD and persistence."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import tasks  # noqa: E402
from lib.errors import UsageError  # noqa: E402


class _TmpMixin:
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        d = Path(self._tmpdir.name)
        self._p_file = mock.patch.object(tasks, "TASKS_FILE", d / "tasks.json")
        self._p_file.start()
        # Core tasks doesn't touch git anymore — worktree provisioning
        # lives in the agent extension. Tests just need a repo-ish dir.
        self._repo = d / "repo"
        self._repo.mkdir()

    def tearDown(self):
        self._p_file.stop()
        self._tmpdir.cleanup()


class CreateTests(_TmpMixin, unittest.TestCase):

    def test_create_returns_task(self):
        t = tasks.create(title="fix bug", repo_path=str(self._repo))
        self.assertEqual(t["title"], "fix bug")
        self.assertEqual(t["status"], "open")
        self.assertIn("id", t)

    def test_create_with_agent(self):
        t = tasks.create(title="fix bug", repo_path=str(self._repo), agent="opus")
        self.assertEqual(t["agent"], "opus")

    def test_create_empty_title_raises(self):
        with self.assertRaises(UsageError):
            tasks.create(title="", repo_path=str(self._repo))

    def test_create_bad_repo_raises(self):
        with self.assertRaises(UsageError):
            tasks.create(title="test", repo_path="/nonexistent/path")

    def test_create_records_worktree_path_verbatim(self):
        # Callers (e.g. the agent extension) provision the worktree
        # themselves and pass the path to ``create``. Core stores it
        # as opaque data.
        t = tasks.create(
            title="simple", repo_path=str(self._repo),
            worktree_path="/tmp/somewhere", branch="tb-task/simple")
        self.assertEqual(t["worktree_path"], "/tmp/somewhere")
        self.assertEqual(t["branch"], "tb-task/simple")

    def test_create_defaults_worktree_path_to_empty(self):
        t = tasks.create(title="simple", repo_path=str(self._repo))
        self.assertEqual(t["worktree_path"], "")
        self.assertEqual(t["branch"], "")


class ListTests(_TmpMixin, unittest.TestCase):

    def test_list_empty(self):
        self.assertEqual(tasks.list_tasks(), [])

    def test_list_returns_created(self):
        tasks.create(title="a", repo_path=str(self._repo))
        tasks.create(title="b", repo_path=str(self._repo))
        self.assertEqual(len(tasks.list_tasks()), 2)

    def test_list_excludes_archived(self):
        t = tasks.create(title="old", repo_path=str(self._repo))
        tasks.update(t["id"], status="archived")
        self.assertEqual(len(tasks.list_tasks()), 0)
        self.assertEqual(len(tasks.list_tasks(include_archived=True)), 1)

    def test_list_filter_by_status(self):
        t1 = tasks.create(title="a", repo_path=str(self._repo))
        t2 = tasks.create(title="b", repo_path=str(self._repo))
        tasks.update(t1["id"], status="done")
        done = tasks.list_tasks(status="done")
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["id"], t1["id"])


class UpdateTests(_TmpMixin, unittest.TestCase):

    def test_update_status(self):
        t = tasks.create(title="test", repo_path=str(self._repo))
        updated = tasks.update(t["id"], status="done")
        self.assertEqual(updated["status"], "done")

    def test_update_invalid_status(self):
        t = tasks.create(title="test", repo_path=str(self._repo))
        with self.assertRaises(UsageError):
            tasks.update(t["id"], status="invalid")

    def test_update_nonexistent_raises(self):
        with self.assertRaises(UsageError):
            tasks.update("no-such-id", status="done")


class GetTests(_TmpMixin, unittest.TestCase):

    def test_get_existing(self):
        t = tasks.create(title="test", repo_path=str(self._repo))
        got = tasks.get_task(t["id"])
        self.assertEqual(got["title"], "test")

    def test_get_nonexistent(self):
        self.assertIsNone(tasks.get_task("nope"))


class ArchiveTests(_TmpMixin, unittest.TestCase):

    def test_archive_sets_status(self):
        t = tasks.create(title="old", repo_path=str(self._repo))
        archived = tasks.archive(t["id"])
        self.assertEqual(archived["status"], "archived")


if __name__ == "__main__":
    unittest.main()
