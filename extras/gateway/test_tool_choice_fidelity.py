#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import tool_choice_fidelity


class ToolChoiceFidelity(unittest.TestCase):
    def test_simple_choices_match_both_apis(self):
        for value in ("auto", "required", "none"):
            with self.subTest(value=value):
                self.assertEqual(tool_choice_fidelity.translate(value, "chat"), value)
                self.assertEqual(tool_choice_fidelity.translate({"type": value}, "responses"), value)

    def test_named_chat_choice(self):
        self.assertEqual(
            tool_choice_fidelity.translate(
                {"type": "tool", "toolName": "terminal"},
                "chat",
            ),
            {"type": "function", "function": {"name": "terminal"}},
        )

    def test_named_responses_choice(self):
        self.assertEqual(
            tool_choice_fidelity.translate(
                {"type": "tool", "toolName": "terminal"},
                "responses",
            ),
            {"type": "function", "name": "terminal"},
        )

    def test_missing_or_unknown_choice_is_not_invented(self):
        for raw in (None, {}, {"type": "tool"}, {"type": "mystery"}, "mystery"):
            with self.subTest(raw=raw):
                self.assertIsNone(tool_choice_fidelity.translate(raw, "chat"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
