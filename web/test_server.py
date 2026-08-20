#!/usr/bin/env python3
"""Unit tests for fxs ui helpers. Stdlib only."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
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

    def test_openrouter_free_first(self):
        found = [
            {"id": "openai/gpt-4o", "label": "gpt-4o"},
            {"id": "stealth/ox-alpha", "label": "ox-alpha"},
            {"id": "z-ai/glm-5.2:free", "label": "glm-5.2:free"},
        ]
        ranked = server.rank_models(found, "stealth/ox-alpha", prefer_free=True)
        ids = [m["id"] for m in ranked]
        self.assertEqual(ids[0], "stealth/ox-alpha")
        self.assertEqual(ids[1], "z-ai/glm-5.2:free")
        self.assertEqual(ids[-1], "openai/gpt-4o")
        self.assertIn("(free)", ranked[0]["label"])


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


class Sessions(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.prev = server.STATE_ROOT
        server.STATE_ROOT = self.tmp
        self.ws = "/tmp/fxs-test-ws"

    def tearDown(self):
        server.STATE_ROOT = self.prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, sid, payload):
        d = server.session_root(self.ws)
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{sid}.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        return p

    def test_read_roundtrip(self):
        self._write("abc-1", {
            "title": "Hello",
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": [{"text": "yo"}]},
            ],
        })
        data = server.read_session(self.ws, "abc-1")
        self.assertEqual(data["id"], "abc-1")
        self.assertEqual(data["title"], "Hello")
        self.assertEqual([m["content"] for m in data["messages"]], ["hi", "yo"])

    def test_rejects_bad_id(self):
        self._write("ok", {"title": "x", "messages": []})
        self.assertIsNone(server.session_path(self.ws, "../ok"))
        self.assertIsNone(server.session_path(self.ws, "ok/../ok"))
        self.assertIsNone(server.session_path(self.ws, ""))
        self.assertIsNone(server.read_session(self.ws, "missing"))

    def test_delete(self):
        self._write("gone", {"title": "x", "messages": [{"role": "user", "content": "bye"}]})
        self.assertTrue(server.delete_session(self.ws, "gone"))
        self.assertIsNone(server.read_session(self.ws, "gone"))
        self.assertFalse(server.delete_session(self.ws, "gone"))

    def test_list(self):
        self._write("a", {"title": "One", "messages": [{"role": "user", "content": "x"}]})
        rows = server.list_sessions(self.ws)
        self.assertEqual(rows[0]["id"], "a")
        self.assertEqual(rows[0]["title"], "One")


class Steps(unittest.TestCase):
    def test_read_file_kind(self):
        s = server.tool_step({"name": "read_file", "path": "README.md", "status": "ok"})
        self.assertEqual(s["kind"], "read")
        self.assertEqual(s["path"], "README.md")
        self.assertEqual(s["status"], "ok")

    def test_arguments_json_path(self):
        s = server.tool_step({
            "name": "read_file",
            "arguments_json": '{"path":"web/app.js"}',
            "status": "success",
        })
        self.assertEqual(s["kind"], "read")
        self.assertEqual(s["path"], "web/app.js")
        self.assertEqual(s["status"], "ok")

    def test_run_command_kind(self):
        s = server.tool_step({"name": "run_command", "command": "fx status --json"})
        self.assertEqual(s["kind"], "run")
        self.assertIn("fx status", s["detail"])

    def test_grep_kind(self):
        s = server.tool_step({"name": "grep_files", "query": "TOOL_KIND"})
        self.assertEqual(s["kind"], "search")

    def test_bracket_read(self):
        s = server.parse_step("[read_file] web/app.js")
        self.assertEqual(s["kind"], "read")
        self.assertEqual(s["path"], "web/app.js")

    def test_recovered(self):
        self.assertIsNone(server.parse_step("[notice] recovered on attempt 3"))

    def test_progress_reading(self):
        s = server.parse_step("● Reading README.md")
        self.assertEqual(s["kind"], "read")
        self.assertEqual(s["path"], "README.md")
        self.assertEqual(s["status"], "running")

    def test_progress_reading_done(self):
        s = server.parse_step("Reading README.md")
        self.assertEqual(s["kind"], "read")
        self.assertEqual(s["path"], "README.md")
        self.assertEqual(s["status"], "ok")

    def test_progress_listing(self):
        s = server.parse_step("Listing web")
        self.assertEqual(s["kind"], "list")
        self.assertEqual(s["path"], "web")
        self.assertEqual(s["status"], "ok")

    def test_progress_listing_running(self):
        s = server.parse_step("● Listing web")
        self.assertEqual(s["kind"], "list")
        self.assertEqual(s["status"], "running")
        self.assertEqual(s["path"], "web")

    def test_progress_pathless_dropped_into_kind(self):
        s = server.parse_step("● Reading")
        self.assertEqual(s["kind"], "read")
        self.assertEqual(s["path"], "")
        self.assertEqual(s["status"], "running")

    def test_noise_dropped(self):
        self.assertIsNone(server.parse_step("Hi! What can I help you with?"))
        self.assertIsNone(server.parse_step('{"type":"assistant"}'))
        self.assertIsNone(server.parse_step("[notice] something else"))

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
