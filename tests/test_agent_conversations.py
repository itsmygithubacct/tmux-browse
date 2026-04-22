"""Persistent conversation storage for agent REPLs."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import agent_conversations as ac  # noqa: E402


class _TmpDirMixin:
    """Redirect CONVERSATIONS_DIR to a temp dir for each test."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(
            ac, "CONVERSATIONS_DIR", Path(self._tmpdir.name),
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmpdir.cleanup()


class CreateTests(_TmpDirMixin, unittest.TestCase):

    def test_create_returns_conversation_id(self):
        cid = ac.create("opus")
        self.assertIsInstance(cid, str)
        self.assertGreater(len(cid), 5)

    def test_create_writes_header(self):
        cid = ac.create("opus")
        header = ac.load_header(cid)
        self.assertIsNotNone(header)
        self.assertEqual(header["type"], "header")
        self.assertEqual(header["agent_name"], "opus")
        self.assertEqual(header["conversation_id"], cid)
        self.assertIsNone(header["parent_id"])

    def test_create_with_parent(self):
        parent = ac.create("opus")
        child = ac.create("opus", parent_id=parent)
        header = ac.load_header(child)
        self.assertEqual(header["parent_id"], parent)


class TurnTests(_TmpDirMixin, unittest.TestCase):

    def test_append_and_load_turns(self):
        cid = ac.create("gpt")
        ac.append_turn(cid, role="user", content="hello")
        ac.append_turn(cid, role="assistant", content="hi there", run_id="r1")
        turns = ac.load_turns(cid)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["role"], "user")
        self.assertEqual(turns[0]["content"], "hello")
        self.assertEqual(turns[1]["role"], "assistant")
        self.assertEqual(turns[1]["run_id"], "r1")

    def test_load_messages_returns_role_content_pairs(self):
        cid = ac.create("gpt")
        ac.append_turn(cid, role="user", content="what sessions?")
        ac.append_turn(cid, role="assistant", content="found 3")
        msgs = ac.load_messages(cid)
        self.assertEqual(msgs, [
            {"role": "user", "content": "what sessions?"},
            {"role": "assistant", "content": "found 3"},
        ])

    def test_load_turns_of_nonexistent_returns_empty(self):
        self.assertEqual(ac.load_turns("nonexistent"), [])

    def test_load_messages_of_nonexistent_returns_empty(self):
        self.assertEqual(ac.load_messages("nonexistent"), [])


class ListTests(_TmpDirMixin, unittest.TestCase):

    def test_list_all(self):
        ac.create("opus")
        ac.create("gpt")
        convos = ac.list_conversations()
        self.assertEqual(len(convos), 2)
        names = {c["agent_name"] for c in convos}
        self.assertEqual(names, {"opus", "gpt"})

    def test_list_filtered(self):
        ac.create("opus")
        ac.create("gpt")
        convos = ac.list_conversations(agent_name="opus")
        self.assertEqual(len(convos), 1)
        self.assertEqual(convos[0]["agent_name"], "opus")


class ClearTests(_TmpDirMixin, unittest.TestCase):

    def test_clear_existing(self):
        cid = ac.create("opus")
        self.assertTrue(ac.clear(cid))
        self.assertIsNone(ac.load_header(cid))

    def test_clear_nonexistent(self):
        self.assertFalse(ac.clear("nonexistent"))


if __name__ == "__main__":
    unittest.main()
