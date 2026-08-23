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
        self.assertEqual(got.contracts_for("chat"), ())

    def test_metadata_only_probe_never_claims_transport(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(self.fake_fx("both", Path(td)))
        self.assertTrue(got.available)
        self.assertEqual(got.version, "fx 0.0.test")
        self.assertFalse(got.transport_probed)
        self.assertFalse(got.openai_compatible)
        self.assertEqual(got.openai_chat_contracts, ())
        self.assertEqual(got.openai_responses_contracts, ())

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
        self.assertEqual(got.openai_chat_contracts, ())
        self.assertEqual(got.openai_responses_contracts, ())
        self.assertEqual(got.evidence, ())

    def test_fx_openai_chat_only_keeps_responses_on_adapter(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(
                self.fake_fx("fx-openai-chat", Path(td)),
                transport_probe=True,
                timeout=5,
            )
        self.assertTrue(got.openai_compatible)
        self.assertTrue(got.supports("chat"))
        self.assertFalse(got.supports("responses"))
        self.assertEqual(got.contracts_for("chat"), (native_fx.CONTRACT_FX_OPENAI,))
        self.assertEqual(got.contracts_for("responses"), ())
        self.assertTrue(any("fx_openai" in item and "chat" in item for item in got.evidence))

    def test_fx_openai_responses_requires_successful_responses_transport(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(
                self.fake_fx("fx-openai-responses", Path(td)),
                transport_probe=True,
                timeout=5,
            )
        self.assertTrue(got.openai_compatible)
        self.assertTrue(got.openai_chat)
        self.assertTrue(got.openai_responses)
        self.assertEqual(got.openai_chat_contracts, (native_fx.CONTRACT_FX_OPENAI,))
        self.assertEqual(got.openai_responses_contracts, (native_fx.CONTRACT_FX_OPENAI,))
        self.assertTrue(any("responses" in item for item in got.evidence))

    def test_custom_endpoint_contract_is_detected_independently(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(
                self.fake_fx("custom-chat", Path(td)),
                transport_probe=True,
                timeout=5,
            )
        self.assertTrue(got.openai_compatible)
        self.assertTrue(got.openai_chat)
        self.assertFalse(got.openai_responses)
        self.assertEqual(
            got.openai_chat_contracts,
            (native_fx.CONTRACT_CUSTOM_ENDPOINT,),
        )
        self.assertEqual(got.openai_responses_contracts, ())
        self.assertTrue(any("custom_endpoint" in item for item in got.evidence))

    def test_all_working_contracts_are_reported_in_preference_order(self):
        with tempfile.TemporaryDirectory() as td:
            got = native_fx.probe_fx(
                self.fake_fx("both", Path(td)),
                transport_probe=True,
                timeout=5,
            )
        self.assertEqual(
            got.openai_chat_contracts,
            (
                native_fx.CONTRACT_FX_OPENAI,
                native_fx.CONTRACT_CUSTOM_ENDPOINT,
            ),
        )
        self.assertEqual(
            got.openai_responses_contracts,
            (native_fx.CONTRACT_FX_OPENAI,),
        )
        as_json = got.to_dict()
        self.assertEqual(
            as_json["openai_chat_contracts"],
            [native_fx.CONTRACT_FX_OPENAI, native_fx.CONTRACT_CUSTOM_ENDPOINT],
        )
        self.assertEqual(
            as_json["openai_responses_contracts"],
            [native_fx.CONTRACT_FX_OPENAI],
        )

    def test_contract_environment_is_isolated(self):
        env = {
            "OPENAI_API_KEY": "external",
            "FX_OPENAI_BASE_URL": "https://should-be-cleared.invalid/v1",
            "FX_BASE_URL": "https://should-also-be-cleared.invalid/v1",
            "FX_API_KEY": "external",
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
        self.assertEqual(cleaned["OTHER"], "keep")


if __name__ == "__main__":
    unittest.main(verbosity=2)
