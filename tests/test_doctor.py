"""Prerequisite checks — make sure missing tmux/ttyd is reported with
the right status, and the install hint matches the detected package
manager."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import doctor  # noqa: E402


class CheckTests(unittest.TestCase):

    def test_tmux_missing_marks_status_missing(self):
        with mock.patch("lib.doctor.shutil.which", return_value=None):
            r = doctor._check_tmux()
        self.assertEqual(r.name, "tmux")
        self.assertEqual(r.status, "missing")
        self.assertFalse(r.ok)
        self.assertIsNone(r.path)
        self.assertIn("not on $PATH", r.detail or "")
        self.assertIsNotNone(r.hint)

    def test_tmux_present_returns_version(self):
        proc = mock.Mock(returncode=0, stdout="tmux 3.4\n", stderr="")
        with mock.patch("lib.doctor.shutil.which", return_value="/usr/bin/tmux"), \
             mock.patch("lib.doctor.subprocess.run", return_value=proc):
            r = doctor._check_tmux()
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.path, "/usr/bin/tmux")
        self.assertEqual(r.version, "tmux 3.4")
        self.assertIsNone(r.hint)

    def test_ttyd_missing_when_neither_bundled_nor_path(self):
        bundled = mock.Mock()
        bundled.is_file.return_value = False
        bundled.__str__ = lambda self: "/home/x/.local/bin/ttyd"
        with mock.patch.object(doctor.config, "TTYD_BIN", bundled), \
             mock.patch("lib.doctor.shutil.which", return_value=None):
            r = doctor._check_ttyd()
        self.assertEqual(r.status, "missing")
        self.assertIsNotNone(r.hint)
        self.assertIn("install-ttyd", r.hint)

    def test_ttyd_prefers_bundled_over_path(self):
        bundled = mock.Mock()
        bundled.is_file.return_value = True
        bundled.__str__ = lambda self: "/home/x/.local/bin/ttyd"
        proc = mock.Mock(returncode=0, stdout="ttyd version 1.7.7\n", stderr="")
        with mock.patch.object(doctor.config, "TTYD_BIN", bundled), \
             mock.patch("lib.doctor.os.access", return_value=True), \
             mock.patch("lib.doctor.shutil.which", return_value="/usr/local/bin/ttyd"), \
             mock.patch("lib.doctor.subprocess.run", return_value=proc):
            r = doctor._check_ttyd()
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.path, "/home/x/.local/bin/ttyd")
        self.assertEqual(r.version, "ttyd version 1.7.7")

    def test_required_missing_filters_to_failures_only(self):
        results = [
            doctor.Result("tmux", "ok", "/usr/bin/tmux", "tmux 3.4", None, None),
            doctor.Result("ttyd", "missing", None, None, "not found", "go install it"),
        ]
        bad = doctor.required_missing(results)
        self.assertEqual([r.name for r in bad], ["ttyd"])

    def test_format_table_includes_hint_for_missing(self):
        results = [
            doctor.Result("tmux", "missing", None, None, "not on $PATH",
                          "sudo apt install tmux"),
        ]
        out = doctor.format_table(results)
        self.assertIn("tmux", out)
        self.assertIn("missing", out)
        self.assertIn("sudo apt install tmux", out)


class HintDetectionTests(unittest.TestCase):

    def test_apt_hint(self):
        with mock.patch("lib.doctor._detect_pkg_manager", return_value="apt"):
            self.assertEqual(doctor._tmux_install_hint(), "sudo apt install tmux")

    def test_brew_hint(self):
        with mock.patch("lib.doctor._detect_pkg_manager", return_value="brew"):
            self.assertEqual(doctor._tmux_install_hint(), "brew install tmux")

    def test_no_manager_falls_back_to_generic(self):
        with mock.patch("lib.doctor._detect_pkg_manager", return_value=None):
            hint = doctor._tmux_install_hint()
        self.assertIn("package manager", hint)


if __name__ == "__main__":
    unittest.main()
