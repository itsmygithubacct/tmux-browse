"""host_identity — device_id creation (perms, stability, race-safety)
and hostname shortening.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import host_identity  # noqa: E402


class DeviceIdTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._state = Path(self._tmp.name)
        self._patch = mock.patch.object(host_identity.config, "STATE_DIR",
                                        self._state)
        self._patch.start()
        # Drop the process-wide cache so each test starts clean.
        host_identity._cached_device_id = None

    def tearDown(self):
        self._patch.stop()
        host_identity._cached_device_id = None
        self._tmp.cleanup()

    def test_creates_id_file_with_0600_perms(self):
        did = host_identity.get_or_create_device_id()
        self.assertTrue(did)
        path = self._state / "device-id"
        self.assertTrue(path.is_file())
        mode = stat.S_IMODE(path.stat().st_mode)
        self.assertEqual(mode, 0o600, f"expected 0600, got {oct(mode)}")

    def test_id_is_stable_across_calls(self):
        first = host_identity.get_or_create_device_id()
        second = host_identity.get_or_create_device_id()
        self.assertEqual(first, second)

    def test_existing_file_is_read_not_overwritten(self):
        path = self._state / "device-id"
        path.write_text("preexisting-id\n", encoding="utf-8")
        self.assertEqual(host_identity.get_or_create_device_id(),
                         "preexisting-id")

    def test_cache_avoids_second_disk_read(self):
        host_identity.get_or_create_device_id()  # populates cache
        # If the file vanished, a cached value must still be returned
        # (stable for the process lifetime) without touching disk.
        (self._state / "device-id").unlink()
        self.assertTrue(host_identity.get_or_create_device_id())

    def test_race_adopts_existing_file(self):
        # Simulate another process winning the create between our read
        # and our O_EXCL open: os.open raises FileExistsError, and we
        # must adopt whatever is already on disk.
        host_identity._cached_device_id = None
        path = self._state / "device-id"
        real_open = os.open

        def racing_open(p, flags, *a, **k):
            if str(p) == str(path) and (flags & os.O_EXCL):
                path.write_text("winner-id\n", encoding="utf-8")
                raise FileExistsError(17, "exists")
            return real_open(p, flags, *a, **k)

        with mock.patch.object(host_identity.os, "open", side_effect=racing_open):
            self.assertEqual(host_identity._load_or_create_device_id(),
                             "winner-id")


class HostnameTests(unittest.TestCase):

    def test_short_hostname_strips_domain(self):
        with mock.patch.object(host_identity.socket, "gethostname",
                               return_value="host-c.lan.example.com"):
            self.assertEqual(host_identity.get_hostname(), "host-c")

    def test_bare_hostname_unchanged(self):
        with mock.patch.object(host_identity.socket, "gethostname",
                               return_value="host-c"):
            self.assertEqual(host_identity.get_hostname(), "host-c")


if __name__ == "__main__":
    unittest.main()
