"""server._record_post_processor_error: dedup + bounded growth.

A session post-processor (e.g. the federation merge) that keeps failing
must be recorded at most once per (name, message) so the 1Hz refresh
doesn't rewrite extensions.json every tick — and the dedup set must stay
bounded even when the failure message varies every time.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import server  # noqa: E402


class RecordPostProcessorErrorTests(unittest.TestCase):

    def setUp(self):
        server._post_processor_errors_seen.clear()

    tearDown = setUp

    def test_same_error_recorded_once(self):
        with mock.patch.object(server.extensions, "record_error") as rec:
            server._record_post_processor_error("fed", "boom")
            server._record_post_processor_error("fed", "boom")
            server._record_post_processor_error("fed", "boom")
        self.assertEqual(rec.call_count, 1)

    def test_distinct_messages_each_recorded(self):
        with mock.patch.object(server.extensions, "record_error") as rec:
            server._record_post_processor_error("fed", "boom-1")
            server._record_post_processor_error("fed", "boom-2")
        self.assertEqual(rec.call_count, 2)

    def test_set_is_bounded(self):
        cap = server._MAX_POST_PROCESSOR_ERRORS_SEEN
        with mock.patch.object(server.extensions, "record_error"):
            # Add cap+50 unique messages; the set must never exceed the cap.
            for i in range(cap + 50):
                server._record_post_processor_error("fed", f"err-{i}")
                self.assertLessEqual(len(server._post_processor_errors_seen), cap)

    def test_reset_rethrottles_but_keeps_recording(self):
        cap = server._MAX_POST_PROCESSOR_ERRORS_SEEN
        with mock.patch.object(server.extensions, "record_error") as rec:
            for i in range(cap + 5):
                server._record_post_processor_error("fed", f"err-{i}")
            # Every distinct message still produced a record_error call.
            self.assertEqual(rec.call_count, cap + 5)


if __name__ == "__main__":
    unittest.main()
