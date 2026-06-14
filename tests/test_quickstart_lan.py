"""Guard the LAN quickstart's auth-by-default behaviour.

bin/quickstart_lan.sh binds 0.0.0.0, which exposes the per-session ttyd
shells as well as the dashboard. It must launch with an auth token by
default (the header promises one) and offer an explicit --no-auth
opt-out. This pins that contract — including that the token is passed
via the environment so it never lands in `ps`/argv — and that the
script stays syntactically valid.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "bin" / "quickstart_lan.sh"


class QuickstartLanAuthTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.text = _SCRIPT.read_text(encoding="utf-8")

    def test_script_exists_and_is_valid_bash(self):
        self.assertTrue(_SCRIPT.is_file())
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash not available")
        r = subprocess.run([bash, "-n", str(_SCRIPT)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_generates_token_by_default(self):
        # Token minted with the stdlib secrets module when not opted out.
        self.assertIn("secrets.token_urlsafe", self.text)

    def test_respects_preset_token(self):
        self.assertIn("TMUX_BROWSE_TOKEN:-", self.text)

    def test_has_no_auth_optout_flag(self):
        self.assertIn("--no-auth)", self.text)
        self.assertIn("NO_AUTH=0", self.text)

    def test_token_passed_via_env_not_argv(self):
        # export keeps the secret out of the process argument list.
        self.assertIn("export TMUX_BROWSE_TOKEN=", self.text)

    def test_warns_when_launched_without_auth(self):
        self.assertIn("WITHOUT auth", self.text)

    def test_header_documents_the_optout(self):
        header = self.text.split("set -euo pipefail")[0]
        self.assertIn("--no-auth", header)


if __name__ == "__main__":
    unittest.main()
