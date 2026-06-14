"""CLI entry point (tmux_browse.py): parser wiring + argument validation.

The top-level CLI had no coverage; these tests exercise the parser and
the pure validation branches in cmd_serve / cmd_config without touching
tmux, ttyd, or the network.
"""

from __future__ import annotations

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

    def test_set_known_key_saves(self):
        saved = {}

        def fake_save(cfg):
            saved.update(cfg)
            return cfg

        with mock.patch.object(tmux_browse.dashboard_config, "load",
                               return_value={"theme": "dark"}), \
                mock.patch.object(tmux_browse.dashboard_config, "DEFAULTS",
                                  {"theme": "dark"}), \
                mock.patch.object(tmux_browse.dashboard_config, "save",
                                  side_effect=fake_save):
            rc = tmux_browse.cmd_config(self._args(set_=["theme=light"]))
        self.assertEqual(rc, 0)
        self.assertEqual(saved["theme"], "light")


if __name__ == "__main__":
    unittest.main()
