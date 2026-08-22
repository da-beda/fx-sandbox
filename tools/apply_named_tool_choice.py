#!/usr/bin/env python3
from pathlib import Path

GATEWAY = Path("extras/gateway/gateway.py")
GATEWAY_TESTS = Path("extras/gateway/test_gateway.py")
MATRIX_TEST = Path("extras/gateway/test_fidelity_matrix.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


g = GATEWAY.read_text(encoding="utf-8")
g = replace_once(
    g,
    "import responses_fidelity\n",
    "import responses_fidelity\nimport tool_choice_fidelity\n",
    "tool-choice fidelity import",
)
g = replace_once(
    g,
    '''def tool_choice(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw or None
    if isinstance(raw, dict):
        t = raw.get("type") or ""
        if t in ("auto", "required", "none"):
            return t
    return None
''',
    '''def tool_choice(raw: Any) -> Any:
    return tool_choice_fidelity.translate(raw, "chat")
''',
    "chat tool-choice translator",
)
g = replace_once(
    g,
    '''    reasoning = _responses_reasoning(inbound if isinstance(inbound, dict) else {})
    if reasoning:
        out["reasoning"] = reasoning
    responses_fidelity.apply_gateway_extensions(out, inbound)
    return out
''',
    '''    inbound_dict = inbound if isinstance(inbound, dict) else {}
    reasoning = _responses_reasoning(inbound_dict)
    if reasoning:
        out["reasoning"] = reasoning
    choice = tool_choice_fidelity.translate(inbound_dict.get("toolChoice"), "responses")
    if choice is not None:
        out["tool_choice"] = choice
    else:
        out.pop("tool_choice", None)
    responses_fidelity.apply_gateway_extensions(out, inbound_dict)
    return out
''',
    "Responses tool-choice translator",
)
GATEWAY.write_text(g, encoding="utf-8")


t = GATEWAY_TESTS.read_text(encoding="utf-8")
t = replace_once(
    t,
    '''    def test_named_tool_choice_ignored(self):
        req = gateway.chat_request("m", False, json.dumps({
            "prompt": [], "toolChoice": {"type": "tool", "toolName": "bash"},
        }).encode())
        self.assertNotIn("tool_choice", req)
''',
    '''    def test_named_tool_choice_preserved(self):
        body = json.dumps({
            "prompt": [], "toolChoice": {"type": "tool", "toolName": "bash"},
        }).encode()
        chat = gateway.chat_request("m", False, body)
        self.assertEqual(chat["tool_choice"], {
            "type": "function", "function": {"name": "bash"},
        })
        responses = gateway.responses_request("m", False, body)
        self.assertEqual(responses["tool_choice"], {
            "type": "function", "name": "bash",
        })
''',
    "named tool-choice regression test",
)
GATEWAY_TESTS.write_text(t, encoding="utf-8")


m = MATRIX_TEST.read_text(encoding="utf-8")
m = replace_once(
    m,
    '''        self.assertEqual(self.rows["named_tool_choice"].chat, "degraded")
        self.assertEqual(self.rows["named_tool_choice"].responses, "degraded")
        for feature in ("image_input", "structured_output"):
''',
    '''        self.assertEqual(self.rows["named_tool_choice"].chat, "pass")
        self.assertEqual(self.rows["named_tool_choice"].responses, "pass")
        for feature in ("image_input", "structured_output"):
''',
    "fidelity matrix named-tool expectation",
)
MATRIX_TEST.write_text(m, encoding="utf-8")
