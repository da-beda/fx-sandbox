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


def supports(contract, style):
    if mode == "legacy":
        return False
    if mode == "fx-openai-chat":
        return contract == "fx_openai" and style == "chat"
    if mode == "fx-openai-responses":
        return contract == "fx_openai" and style in ("chat", "responses")
    if mode == "custom-chat":
        return contract == "custom_endpoint" and style == "chat"
    if mode == "both":
        if contract == "fx_openai":
            return style in ("chat", "responses")
        return contract == "custom_endpoint" and style == "chat"
    return False


def supports_tools(contract, style):
    # Deliberately separate text transport from agentic tool capability.
    if mode in ("legacy", "fx-openai-chat"):
        return False
    if mode == "fx-openai-responses":
        return contract == "fx_openai" and style in ("chat", "responses")
    if mode == "custom-chat":
        return contract == "custom_endpoint" and style == "chat"
    if mode == "both":
        return supports(contract, style)
    return False


def post(url, body):
    req = urllib.request.Request(
        url,
        data=json.dumps(body, separators=(",", ":")).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer probe"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        resp.read()


if args and args[0] == "ask":
    if os.environ.get("FX_OPENAI_BASE_URL"):
        contract = "fx_openai"
        style = os.environ.get("FX_OPENAI_API_STYLE", "chat")
        base = os.environ["FX_OPENAI_BASE_URL"].rstrip("/")
    elif os.environ.get("FX_BASE_URL"):
        contract = "custom_endpoint"
        style = "chat"
        base = os.environ["FX_BASE_URL"].rstrip("/")
    else:
        raise SystemExit(1)

    if not supports(contract, style):
        raise SystemExit(1)

    path = "/responses" if style == "responses" else "/chat/completions"
    url = base + path
    tool_file = os.environ.get("FXS_NATIVE_PROBE_TOOL_FILE", "")

    if not tool_file:
        post(url, {"model": os.environ.get("FX_MODEL", ""), "stream": True})
        if style == "responses":
            print("FXS_NATIVE_OPENAI_RESPONSES_OK")
        else:
            print("FXS_NATIVE_OPENAI_CHAT_OK")
        raise SystemExit(0)

    if not supports_tools(contract, style):
        # Reach the first tool-call response, but deliberately fail to replay a
        # result. This proves the probe distinguishes text transport from tools.
        post(url, {"model": os.environ.get("FX_MODEL", ""), "stream": True})
        raise SystemExit(1)

    with open(tool_file, "r", encoding="utf-8") as fh:
        content = fh.read()

    post(url, {"model": os.environ.get("FX_MODEL", ""), "stream": True})
    if style == "responses":
        follow_up = {
            "model": os.environ.get("FX_MODEL", ""),
            "stream": True,
            "input": [{
                "type": "function_call_output",
                "call_id": "call_read",
                "output": content,
            }],
        }
        marker = "FXS_NATIVE_OPENAI_RESPONSES_TOOL_OK"
    else:
        follow_up = {
            "model": os.environ.get("FX_MODEL", ""),
            "stream": True,
            "messages": [{
                "role": "tool",
                "tool_call_id": "call_read",
                "content": content,
            }],
        }
        marker = "FXS_NATIVE_OPENAI_CHAT_TOOL_OK"
    post(url, follow_up)
    print(marker)
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
        self.assertFalse(got.supports_tools("chat"))
        self.assertEqual(got.contracts_for("chat"), ())
        self.assertEqual(got.tool_contracts_for("chat"), ())

    def test_metadata_only_probe_never_claims_transport_or_tools(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(self.fake_fx("both", Path(td)))
        self.assertTrue(got.available)
        self.assertEqual(got.version, "fx 0.0.test")
        self.assertFalse(got.transport_probed)
        self.assertFalse(got.openai_compatible)
        self.assertFalse(got.openai_chat_tools)
        self.assertFalse(got.openai_responses_tools)
        self.assertEqual(got.openai_chat_contracts, ())
        self.assertEqual(got.openai_responses_contracts, ())
        self.assertEqual(got.openai_chat_tool_contracts, ())
        self.assertEqual(got.openai_responses_tool_contracts, ())

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
        self.assertFalse(got.openai_chat_tools)
        self.assertFalse(got.openai_responses_tools)
        self.assertEqual(got.openai_chat_contracts, ())
        self.assertEqual(got.openai_responses_contracts, ())
        self.assertEqual(got.openai_chat_tool_contracts, ())
        self.assertEqual(got.openai_responses_tool_contracts, ())
        self.assertEqual(got.evidence, ())

    def test_chat_transport_can_exist_without_tool_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(
                self.fake_fx("fx-openai-chat", Path(td)),
                transport_probe=True,
                timeout=5,
            )
        self.assertTrue(got.openai_compatible)
        self.assertTrue(got.supports("chat"))
        self.assertFalse(got.supports("responses"))
        self.assertFalse(got.supports_tools("chat"))
        self.assertFalse(got.supports_tools("responses"))
        self.assertEqual(got.contracts_for("chat"), (native_fx.CONTRACT_FX_OPENAI,))
        self.assertEqual(got.tool_contracts_for("chat"), ())
        self.assertTrue(any("fx_openai" in item and "chat" in item for item in got.evidence))
        self.assertFalse(any("tool round-trip" in item for item in got.evidence))

    def test_fx_openai_chat_and_responses_tool_roundtrips(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(
                self.fake_fx("fx-openai-responses", Path(td)),
                transport_probe=True,
                timeout=5,
            )
        self.assertTrue(got.openai_chat)
        self.assertTrue(got.openai_responses)
        self.assertTrue(got.openai_chat_tools)
        self.assertTrue(got.openai_responses_tools)
        self.assertEqual(got.openai_chat_contracts, (native_fx.CONTRACT_FX_OPENAI,))
        self.assertEqual(got.openai_responses_contracts, (native_fx.CONTRACT_FX_OPENAI,))
        self.assertEqual(got.openai_chat_tool_contracts, (native_fx.CONTRACT_FX_OPENAI,))
        self.assertEqual(got.openai_responses_tool_contracts, (native_fx.CONTRACT_FX_OPENAI,))
        self.assertTrue(any("chat tool round-trip" in item for item in got.evidence))
        self.assertTrue(any("responses tool round-trip" in item for item in got.evidence))

    def test_custom_endpoint_chat_tool_roundtrip_is_detected_independently(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(
                self.fake_fx("custom-chat", Path(td)),
                transport_probe=True,
                timeout=5,
            )
        self.assertTrue(got.openai_compatible)
        self.assertTrue(got.openai_chat)
        self.assertTrue(got.openai_chat_tools)
        self.assertFalse(got.openai_responses)
        self.assertFalse(got.openai_responses_tools)
        self.assertEqual(
            got.openai_chat_contracts,
            (native_fx.CONTRACT_CUSTOM_ENDPOINT,),
        )
        self.assertEqual(
            got.openai_chat_tool_contracts,
            (native_fx.CONTRACT_CUSTOM_ENDPOINT,),
        )
        self.assertEqual(got.openai_responses_contracts, ())
        self.assertEqual(got.openai_responses_tool_contracts, ())

    def test_all_working_transport_and_tool_contracts_report_preference_order(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(
                self.fake_fx("both", Path(td)),
                transport_probe=True,
                timeout=5,
            )
        expected_chat = (
            native_fx.CONTRACT_FX_OPENAI,
            native_fx.CONTRACT_CUSTOM_ENDPOINT,
        )
        expected_responses = (native_fx.CONTRACT_FX_OPENAI,)
        self.assertEqual(got.openai_chat_contracts, expected_chat)
        self.assertEqual(got.openai_responses_contracts, expected_responses)
        self.assertEqual(got.openai_chat_tool_contracts, expected_chat)
        self.assertEqual(got.openai_responses_tool_contracts, expected_responses)
        as_json = got.to_dict()
        self.assertEqual(as_json["openai_chat_contracts"], list(expected_chat))
        self.assertEqual(as_json["openai_responses_contracts"], list(expected_responses))
        self.assertEqual(as_json["openai_chat_tool_contracts"], list(expected_chat))
        self.assertEqual(as_json["openai_responses_tool_contracts"], list(expected_responses))

    def test_contract_environment_is_isolated(self):
        env = {
            "OPENAI_API_KEY": "external",
            "FX_OPENAI_BASE_URL": "https://should-be-cleared.invalid/v1",
            "FX_BASE_URL": "https://should-also-be-cleared.invalid/v1",
            "FX_API_KEY": "external",
            "FXS_NATIVE_PROBE_TOOL_FILE": "/should/not/leak",
            "OTHER": "keep",
        }
        original = dict(native_fx.os.environ)
        try:
            native_fx.os.environ.clear()
            native_fx.os.environ.update(env)
            cleaned = native_fx._clean_probe_environment()
        finally:
            native_fx.os.environ.clear()
            native_fx.os.environ.update(original)
        self.assertNotIn("OPENAI_API_KEY", cleaned)
        self.assertNotIn("FX_OPENAI_BASE_URL", cleaned)
        self.assertNotIn("FX_BASE_URL", cleaned)
        self.assertNotIn("FX_API_KEY", cleaned)
        self.assertNotIn("FXS_NATIVE_PROBE_TOOL_FILE", cleaned)
        self.assertEqual(cleaned["OTHER"], "keep")


if __name__ == "__main__":
    unittest.main(verbosity=2)
