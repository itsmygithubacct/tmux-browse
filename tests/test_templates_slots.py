"""Template slot contract: extension UI blocks must target real slots,
and the declared _SLOTS set must stay in sync with the template markers.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import static, templates  # noqa: E402


class ValidateUiBlocksTests(unittest.TestCase):

    def test_none_and_empty_are_ok(self):
        templates.validate_ui_blocks(None)
        templates.validate_ui_blocks({})

    def test_known_slots_pass(self):
        blocks = {slot: "<div></div>" for slot in templates.known_slots()}
        templates.validate_ui_blocks(blocks)  # must not raise

    def test_unknown_slot_raises_with_helpful_message(self):
        with self.assertRaises(ValueError) as ctx:
            templates.validate_ui_blocks({"topbar_extra": "<div></div>"})
        msg = str(ctx.exception)
        self.assertIn("topbar_extra", msg)
        self.assertIn("known slots", msg)

    def test_mix_of_known_and_unknown_reports_only_unknown(self):
        known = next(iter(templates.known_slots()))
        with self.assertRaises(ValueError) as ctx:
            templates.validate_ui_blocks({known: "x", "bogus_slot": "y"})
        self.assertIn("bogus_slot", str(ctx.exception))
        self.assertNotIn(known, str(ctx.exception).split("known slots")[0])


class SlotDriftTests(unittest.TestCase):

    def test_declared_slots_match_template_markers(self):
        # Bidirectional: every <!--slot:X--> marker in the rendered
        # template must be declared in _SLOTS, and every declared slot
        # must have a real marker. Catches drift when a slot is added to
        # one place but not the other.
        raw = templates._render(static.JS)
        markers = set(templates._SLOT_RE.findall(raw))
        self.assertEqual(markers, set(templates.known_slots()))


if __name__ == "__main__":
    unittest.main()
