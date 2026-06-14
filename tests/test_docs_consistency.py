"""Keep the README in sync with the security knobs the code exposes.

These features are near-useless if undocumented, and docs drift silently.
Assert the README documents the host-guard env vars the server actually
reads and the LAN quickstart's --no-auth opt-out the script actually has.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "tmux-cli"))
sys.path.insert(0, str(_ROOT))

from lib import server  # noqa: E402


class ReadmeDocumentsSecurityKnobsTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.readme = (_ROOT / "README.md").read_text(encoding="utf-8")
        # Whitespace-normalised copy so prose assertions don't break when a
        # sentence wraps across lines.
        cls.readme_flat = " ".join(cls.readme.split())
        cls.lan = (_ROOT / "bin" / "quickstart_lan.sh").read_text(encoding="utf-8")
        cls.server_src = (_ROOT / "lib" / "server.py").read_text(encoding="utf-8")

    def test_host_guard_env_vars_are_documented(self):
        # The vars the server reads in _build_allowed_hosts must appear in
        # the README so reverse-proxy / Tailscale users can find them.
        for var in ("TMUX_BROWSE_ALLOWED_HOSTS", "TMUX_BROWSE_DISABLE_HOST_CHECK"):
            self.assertIn(var, self.server_src,
                          f"{var} should be read by the server")
            self.assertIn(var, self.readme_flat,
                          f"{var} is a real knob but undocumented in README")

    def test_lan_quickstart_no_auth_flag_is_documented(self):
        # The opt-out the script offers must be discoverable in the README.
        self.assertIn("--no-auth", self.lan)
        self.assertIn("--no-auth", self.readme_flat)

    def test_readme_states_lan_quickstart_is_token_protected(self):
        # The LAN quickstart now mints a token by default; the README must
        # say so (and tie it to a token), so the old "unauthenticated"
        # framing can't silently re-attach to it.
        self.assertIn("LAN quickstart", self.readme_flat)
        # The sentence introducing the LAN quickstart's auth behaviour
        # mentions a bearer token and a default launch.
        self.assertIn("generates a bearer token and launches with it by default",
                      self.readme_flat)


if __name__ == "__main__":
    unittest.main()
