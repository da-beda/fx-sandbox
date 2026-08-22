#!/usr/bin/env python3
from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_fx


FIXTURE = r'''#!/usr/bin/env python3
import json
import os
import sys
import urllib.request

mode = __MODE__
args = sys.argv[1:]
if args == ["--version"]:
    print("fx 0.0.test")
    raise SystemExit(0)
if args and args[0] == "ask":
    style = os.environ.get("FX_OPENAI_API_STYLE", "chat")
    if mode == "legacy" or (style == "responses" and mode != "responses"):
        raise SystemExit(1)
    base = os.environ["FX_OPENAI_BASE_URL"].rstrip("/")
    path = "/responses" if style == "responses" else "/chat/completions"
    body = json.dumps({"model": os.environ.get("FX_MODEL", ""), "stream": True}).encode()
    req = urllib.request.Request(
        base + path,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer probe"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        resp.read()
    if style == "responses":
        print("FXS_NATIVE_OPENAI_RESPONSES_OK")
    else:
        print("FXS_NATIVE_OPENAI_CHAT_OK")
    raise SystemExit(0)
raise SystemExit(2)
'''


class NativeFxProbe(unittest.TestCase):
    def fake_fx(self, mode: str, root: Path) -> str:
        path = root / "fx"
        path.write_text(FIXTURE.replace("__MODE__", repr(mode)), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return str(path)

    def test_missing_binary_is_not_available(self):
        got = native_fx.probe_fx("/definitely/not/fx", transport_probe=True)
        self.assertFalse(got.available)
        self.assertFalse(got.openai_compatible)
        self.assertFalse(got.supports("chat"))

    def test_metadata_only_probe_never_claims_transport(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(self.fake_fx("responses", Path(td)))
        self.assertTrue(got.available)
        self.assertEqual(got.version, "fx 0.0.test")
        self.assertFalse(got.transport_probed)
        self.assertFalse(got.openai_compatible)

    def test_legacy_fx_never_triggers_handoff(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(
                self.fake_fx("legacy", Path(td)),
                transport_probe=True,
                timeout=5,
            )
        self.assertTrue(got.available)
        self.assertTrue(got.transport_probed)
        self.assertFalse(got.openai_compatible)
        self.assertFalse(got.openai_chat)
        self.assertFalse(got.openai_responses)
        self.assertEqual(got.evidence, ())

    def test_chat_only_native_transport_keeps_responses_on_adapter(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(
                self.fake_fx("chat", Path(td)),
                transport_probe=True,
                timeout=5,
            )
        self.assertTrue(got.openai_compatible)
        self.assertTrue(got.supports("chat"))
        self.assertFalse(got.supports("responses"))
        self.assertTrue(any("chat" in item for item in got.evidence))

    def test_responses_requires_successful_responses_transport(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(
                self.fake_fx("responses", Path(td)),
                transport_probe=True,
                timeout=5,
            )
        self.assertTrue(got.openai_compatible)
        self.assertTrue(got.openai_chat)
        self.assertTrue(got.openai_responses)
        self.assertTrue(got.supports("responses"))
        self.assertTrue(any("responses" in item for item in got.evidence))


if __name__ == "__main__":
    unittest.main(verbosity=2)
