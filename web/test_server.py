#!/usr/bin/env python3
"""Unit tests for fxs ui helpers. Stdlib only."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server


class ParseModels(unittest.TestCase):
    def test_ids_shape(self):
        raw = '{"kind":"models","count":3,"ids":["zai/glm-5.2-fast","zai/glm-5.2","openai/gpt-5.2"]}'
        found = server.parse_models(raw)
        ids = [m["id"] for m in found]
        self.assertEqual(ids, ["zai/glm-5.2-fast", "zai/glm-5.2", "openai/gpt-5.2"])

    def test_models_key(self):
        raw = '{"models":[{"id":"zai/glm-5.2","name":"GLM 5.2"}]}'
        found = server.parse_models(raw)
        self.assertEqual(found[0]["id"], "zai/glm-5.2")
        self.assertEqual(found[0]["label"], "GLM 5.2")

    def test_plain_lines(self):
        found = server.parse_models("  zai/glm-5.2   default\nanthropic/claude-sonnet-4.6")
        self.assertEqual(found[0]["id"], "zai/glm-5.2")

    def test_ids_without_slash(self):
        found = server.parse_models("grok-4\nllama3.2")
        self.assertEqual([m["id"] for m in found], ["grok-4", "llama3.2"])


class RankModels(unittest.TestCase):
    def test_glm_first_hides_fast(self):
        found = [
            {"id": "zai/glm-5.2-fast", "label": "glm-5.2-fast"},
            {"id": "openai/gpt-5.2", "label": "gpt-5.2"},
            {"id": "zai/glm-5.2", "label": "glm-5.2"},
        ]
        ranked = server.rank_models(found, "zai/glm-5.2")
        ids = [m["id"] for m in ranked]
        self.assertEqual(ids[0], "zai/glm-5.2")
        self.assertNotIn("zai/glm-5.2-fast", ids)

    def test_keeps_fast_if_current(self):
        found = [{"id": "zai/glm-5.2-fast", "label": "fast"}, {"id": "zai/glm-5.2", "label": "glm"}]
        ranked = server.rank_models(found, "zai/glm-5.2-fast")
        self.assertEqual(ranked[0]["id"], "zai/glm-5.2")
        self.assertIn("zai/glm-5.2-fast", [m["id"] for m in ranked])

    def test_does_not_invent_glm_for_other_host(self):
        found = [{"id": "grok-4", "label": "grok-4"}]
        ranked = server.rank_models(found, "grok-4")
        ids = [m["id"] for m in ranked]
        self.assertEqual(ids[0], "grok-4")
        self.assertNotIn("zai/glm-5.2", ids)


class RecoverError(unittest.TestCase):
    def test_provider_unavailable(self):
        msg = server.recover_error("", "retry 10/10 provider_unavailable HTTP 503")
        self.assertIn("503", msg)

    def test_json_error(self):
        msg = server.recover_error('{"error":"nope"}', "")
        self.assertEqual(msg, "nope")


class LocalMode(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("FXS_UI_LOCAL", None)

    def test_offline_flag(self):
        os.environ["FXS_UI_LOCAL"] = "1"
        self.assertTrue(server.local_mode())

    def test_force_live(self):
        os.environ["FXS_UI_LOCAL"] = "0"
        self.assertFalse(server.local_mode())


class Perm(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(server.clean_perm("ask"), "ask")
        self.assertEqual(server.clean_perm("nope"), "yolo")


class ReleaseCopy(unittest.TestCase):
    def test_no_demo_in_ui_copy(self):
        here = Path(__file__).resolve().parent
        blob = "\n".join(
            p.read_text(encoding="utf-8")
            for p in [here / "server.py", here / "index.html", here / "app.js"]
        ).lower()
        self.assertNotIn("--demo", blob)
        self.assertNotIn("demo", blob)
        self.assertNotIn("sample", blob)


if __name__ == "__main__":
    unittest.main()
