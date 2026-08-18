"""Static safety checks for the self-update shell script."""

from __future__ import annotations

import unittest
from pathlib import Path


_SCRIPT = (Path(__file__).resolve().parents[1] / "bin" / "update.sh").read_text()


class UpdateScriptSafetyTests(unittest.TestCase):
    def test_submodule_alignment_failures_are_fatal(self):
        update_commands = [
            line
            for line in _SCRIPT.splitlines()
            if "g submodule update --recursive" in line
        ]
        self.assertEqual(len(update_commands), 2)
        self.assertNotIn('|| warn "some submodules failed to update', _SCRIPT)
        self.assertNotIn("g submodule update --recursive >/dev/null 2>&1 || true", _SCRIPT)
        self.assertEqual(
            _SCRIPT.count('|| die "installed submodules failed to align with $REF'),
            2,
        )


if __name__ == "__main__":
    unittest.main()
