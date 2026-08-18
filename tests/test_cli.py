"""CLI entry point (tmux_browse.py): parser wiring + argument validation.

The top-level CLI had no coverage; these tests exercise the parser and
the pure validation branches in cmd_serve / cmd_config without touching
tmux, ttyd, or the network.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "tmux-cli", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import tmux_browse  # noqa: E402


class ParserTests(unittest.TestCase):

    def test_serve_defaults(self):
        args = tmux_browse._build_parser().parse_args(["serve"])
        self.assertEqual(args.cmd, "serve")
        self.assertEqual(args.bind, "0.0.0.0")
        self.assertIs(args.func, tmux_browse.cmd_serve)

    def test_subcommand_required(self):
        with self.assertRaises(SystemExit):
            tmux_browse._build_parser().parse_args([])

    def test_unknown_subcommand_errors(self):
        with self.assertRaises(SystemExit):
            tmux_browse._build_parser().parse_args(["frobnicate"])

    def test_help_works_when_docstrings_are_stripped(self):
        proc = subprocess.run(
            [sys.executable, "-OO", str(_ROOT / "tmux_browse.py"), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("tmux-browse CLI.", proc.stdout)


class CmdServePortTests(unittest.TestCase):

    def _serve_args(self, port):
        # --skip-checks so the doctor prereq probe is bypassed.
        return tmux_browse._build_parser().parse_args(
            ["serve", "--skip-checks", "--port", str(port)])

    def test_rejects_port_too_high(self):
        with mock.patch.object(tmux_browse.server, "serve") as m_serve:
            rc = tmux_browse.cmd_serve(self._serve_args(99999))
        self.assertEqual(rc, 2)
        m_serve.assert_not_called()

    def test_rejects_port_zero(self):
        with mock.patch.object(tmux_browse.server, "serve") as m_serve:
            rc = tmux_browse.cmd_serve(self._serve_args(0))
        self.assertEqual(rc, 2)
        m_serve.assert_not_called()

    def test_accepts_valid_port(self):
        with mock.patch.object(tmux_browse.server, "serve") as m_serve, \
                mock.patch.object(tmux_browse.auth, "load_token",
                                  return_value=None), \
                mock.patch.object(tmux_browse.tls, "load_tls_paths",
                                  return_value=None):
            rc = tmux_browse.cmd_serve(self._serve_args(8096))
        self.assertEqual(rc, 0)
        m_serve.assert_called_once()
        self.assertEqual(m_serve.call_args.kwargs["port"], 8096)


class CmdConfigTests(unittest.TestCase):

    def _args(self, *, reset=False, set_=None, json=False):
        return SimpleNamespace(reset=reset, set=set_ or [], json=json)

    def test_reset_and_set_conflict(self):
        rc = tmux_browse.cmd_config(self._args(reset=True, set_=["a=b"]))
        self.assertEqual(rc, 2)

    def test_set_without_equals_is_usage_error(self):
        with mock.patch.object(tmux_browse.dashboard_config, "load",
                               return_value={}), \
                mock.patch.object(tmux_browse.dashboard_config, "DEFAULTS",
                                  {"theme": "dark"}):
            rc = tmux_browse.cmd_config(self._args(set_=["bogus"]))
        self.assertEqual(rc, 2)

    def test_set_unknown_key_is_usage_error(self):
        with mock.patch.object(tmux_browse.dashboard_config, "load",
                               return_value={"theme": "dark"}), \
                mock.patch.object(tmux_browse.dashboard_config, "DEFAULTS",
                                  {"theme": "dark"}):
            rc = tmux_browse.cmd_config(self._args(set_=["nope=1"]))
        self.assertEqual(rc, 2)

    def test_set_known_keys_update_one_batch(self):
        updated = {}

        def fake_update_values(changes):
            updated.update(changes)
            return {"theme": changes["theme"], "refresh_seconds": 12}

        with mock.patch.object(
            tmux_browse.dashboard_config, "DEFAULTS",
            {"theme": "dark", "refresh_seconds": 5},
        ), mock.patch.object(
            tmux_browse.dashboard_config, "update_values",
            side_effect=fake_update_values,
        ) as update_values, mock.patch.object(
            tmux_browse.dashboard_config, "load",
        ) as load:
            rc = tmux_browse.cmd_config(self._args(
                set_=["theme=light", "refresh_seconds=12"],
            ))
        self.assertEqual(rc, 0)
        self.assertEqual(updated, {"theme": "light", "refresh_seconds": "12"})
        update_values.assert_called_once_with(updated)
        load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
