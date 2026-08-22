#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import fidelity_matrix


class FidelityMatrix(unittest.TestCase):
    def setUp(self):
        self.rows = {row.feature: row for row in fidelity_matrix.evaluate()}

    def test_required_cases_are_present(self):
        self.assertEqual(
            set(self.rows),
            {
                "text",
                "max_output_tokens",
                "tools_and_history",
                "named_tool_choice",
                "reasoning_effort",
                "image_input",
                "structured_output",
                "streamed_text",
                "streamed_tool_calls",
                "streamed_reasoning",
            },
        )

    def test_current_pass_surface_is_explicit(self):
        expected = {
            "text": ("pass", "pass"),
            "max_output_tokens": ("pass", "pass"),
            "tools_and_history": ("pass", "pass"),
            "reasoning_effort": ("degraded", "pass"),
            "streamed_text": ("pass", "pass"),
            "streamed_tool_calls": ("pass", "pass"),
            "streamed_reasoning": ("degraded", "pass"),
        }
        for feature, (chat, responses) in expected.items():
            with self.subTest(feature=feature):
                self.assertEqual(self.rows[feature].chat, chat)
                self.assertEqual(self.rows[feature].responses, responses)

    def test_known_gaps_are_not_silently_promoted(self):
        for feature in ("named_tool_choice", "image_input", "structured_output"):
            with self.subTest(feature=feature):
                self.assertEqual(self.rows[feature].chat, "degraded")
                self.assertEqual(self.rows[feature].responses, "degraded")

    def test_json_cli_is_machine_readable(self):
        proc = subprocess.run(
            [sys.executable, str(HERE / "fidelity_matrix.py"), "--json"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
        doc = json.loads(proc.stdout)
        self.assertEqual(doc["schema"], 1)
        self.assertEqual(len(doc["features"]), len(self.rows))
        self.assertEqual(doc["status_semantics"]["pass"], "semantic case preserved by this adapter path")


if __name__ == "__main__":
    unittest.main(verbosity=2)
