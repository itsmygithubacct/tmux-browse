"""Shared SSE producer hub: one summary per tick, fanned out to all
subscribers; producer lifecycle tied to subscriber count."""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import server  # noqa: E402
from lib.server import SessionSummary, _SessionStreamHub  # noqa: E402


def _wait_until(pred, timeout=2.0, step=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(step)
    return pred()


class SessionStreamHubTests(unittest.TestCase):

    def test_subscriber_receives_computed_payload(self):
        holder = {"s": SessionSummary(rows=[{"name": "a"}], tmux_unreachable=False)}
        with mock.patch.object(server, "_session_summary",
                               lambda *a, **k: holder["s"]):
            hub = _SessionStreamHub(interval=0.02)
            v0, _ = hub.subscribe()
            try:
                v1, p1 = hub.wait(v0, timeout=2.0)
                self.assertGreater(v1, v0)
                self.assertIn('"name":"a"', p1)
            finally:
                hub.unsubscribe()

    def test_payload_change_bumps_version(self):
        holder = {"s": SessionSummary(rows=[{"name": "a"}], tmux_unreachable=False)}
        with mock.patch.object(server, "_session_summary",
                               lambda *a, **k: holder["s"]):
            hub = _SessionStreamHub(interval=0.02)
            v0, _ = hub.subscribe()
            try:
                v1, p1 = hub.wait(v0, timeout=2.0)
                self.assertIn('"name":"a"', p1)
                # A new summary must produce a new version + payload.
                holder["s"] = SessionSummary(rows=[{"name": "b"}],
                                             tmux_unreachable=False)
                v2, p2 = hub.wait(v1, timeout=2.0)
                self.assertGreater(v2, v1)
                self.assertIn('"name":"b"', p2)
            finally:
                hub.unsubscribe()

    def test_unchanged_summary_does_not_bump_version(self):
        with mock.patch.object(
                server, "_session_summary",
                lambda *a, **k: SessionSummary(rows=[{"name": "a"}])):
            hub = _SessionStreamHub(interval=0.02)
            v0, _ = hub.subscribe()
            try:
                v1, _ = hub.wait(v0, timeout=2.0)
                # No change in summary → wait times out at the same version.
                t0 = time.monotonic()
                v2, _ = hub.wait(v1, timeout=0.3)
                self.assertEqual(v2, v1)
                self.assertGreaterEqual(time.monotonic() - t0, 0.25)
            finally:
                hub.unsubscribe()

    def test_single_producer_for_multiple_subscribers(self):
        with mock.patch.object(
                server, "_session_summary",
                lambda *a, **k: SessionSummary(rows=[{"name": "a"}])):
            hub = _SessionStreamHub(interval=0.02)
            hub.subscribe()
            hub.subscribe()
            try:
                self.assertTrue(_wait_until(lambda: hub._version >= 1))
                producers = [t for t in threading.enumerate()
                             if t.name == "sse-session-producer" and t.is_alive()]
                # The two subscribers share exactly one producer thread.
                self.assertEqual(len(producers), 1)
                self.assertIsNotNone(hub._thread)
            finally:
                hub.unsubscribe()
                hub.unsubscribe()

    def test_producer_stops_when_last_subscriber_leaves(self):
        with mock.patch.object(
                server, "_session_summary",
                lambda *a, **k: SessionSummary(rows=[{"name": "a"}])):
            hub = _SessionStreamHub(interval=0.02)
            hub.subscribe()
            hub.subscribe()
            self.assertTrue(_wait_until(lambda: hub._thread is not None))
            hub.unsubscribe()
            # One subscriber remains → producer still running.
            self.assertFalse(_wait_until(lambda: hub._thread is None, timeout=0.2))
            hub.unsubscribe()
            # Zero subscribers → producer exits and clears itself.
            self.assertTrue(_wait_until(lambda: hub._thread is None, timeout=2.0))


if __name__ == "__main__":
    unittest.main()
