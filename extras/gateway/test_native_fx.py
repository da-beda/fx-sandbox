#!/usr/bin/env python3
from __future__ import annotations

import os
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_fx


FIXTURE = r'''#!/usr/bin/env python3
import sys
mode = __MODE__
args = sys.argv[1:]
if args == ["--version"]:
    print("fx 0.0.test")
    raise SystemExit(0)
if args == ["setup", "--help"]:
    if mode == "legacy":
        print("Usage: fx setup")
    else:
        print("Usage: fx setup [openai-compatible]")
    raise SystemExit(0)
if args == ["--help"]:
    print("fx help")
    raise SystemExit(0)
if args == ["setup", "openai-compatible", "--help"]:
    if mode == "legacy":
        print("unknown setup target")
        raise SystemExit(2)
    if mode == "chat":
        print("OpenAI-compatible Chat Completions; configure FX_OPENAI_BASE_URL")
    else:
        print("OpenAI-compatible Chat Completions; FX_OPENAI_BASE_URL; FX_OPENAI_API_STYLE=chat|responses; /responses")
    raise SystemExit(0)
print("unsupported fixture command", args)
raise SystemExit(2)
'''


class NativeFxProbe(unittest.TestCase):
    def fake_fx(self, mode: str, root: Path) -> str:
        path = root / "fx"
        path.write_text(FIXTURE.replace("__MODE__", repr(mode)), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return str(path)

    def test_missing_binary_is_not_available(self):
        got = native_fx.probe_fx("/definitely/not/fx")
        self.assertFalse(got.available)
        self.assertFalse(got.openai_compatible)
        self.assertFalse(got.supports("chat"))

    def test_legacy_fx_never_triggers_handoff(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(self.fake_fx("legacy", Path(td)))
        self.assertTrue(got.available)
        self.assertFalse(got.openai_compatible)
        self.assertFalse(got.openai_chat)
        self.assertFalse(got.openai_responses)

    def test_chat_only_native_surface_keeps_responses_on_adapter(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(self.fake_fx("chat", Path(td)))
        self.assertTrue(got.openai_compatible)
        self.assertTrue(got.supports("chat"))
        self.assertFalse(got.supports("responses"))

    def test_responses_requires_explicit_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(self.fake_fx("responses", Path(td)))
        self.assertTrue(got.openai_compatible)
        self.assertTrue(got.openai_chat)
        self.assertTrue(got.openai_responses)
        self.assertTrue(got.supports("responses"))
        self.assertTrue(any("responses" in item for item in got.evidence))


if __name__ == "__main__":
    unittest.main(verbosity=2)
