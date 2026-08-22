#!/usr/bin/env python3
from pathlib import Path

GATEWAY = Path("extras/gateway/gateway.py")
MATRIX_TEST = Path("extras/gateway/test_fidelity_matrix.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


g = GATEWAY.read_text(encoding="utf-8")
g = replace_once(
    g,
    "import search_policy\n",
    "import search_policy\nimport responses_fidelity\n",
    "Responses fidelity import",
)
g = replace_once(
    g,
    "def chat_request(model: str, stream: bool, body: bytes) -> dict[str, Any]:\n",
    "def chat_request(\n    model: str,\n    stream: bool,\n    body: bytes,\n    *,\n    allow_image_only: bool = False,\n) -> dict[str, Any]:\n",
    "chat_request signature",
)
g = replace_once(
    g,
    "    if last_user_image_only:\n        raise TranslateError(ERR_IMAGE_ONLY, ERR_IMAGE_ONLY)\n",
    "    if last_user_image_only and not allow_image_only:\n        raise TranslateError(ERR_IMAGE_ONLY, ERR_IMAGE_ONLY)\n",
    "image-only gate",
)
g = replace_once(
    g,
    "    out = responses_from_chat(chat_request(model, stream, body))\n",
    "    out = responses_from_chat(\n        chat_request(model, stream, body, allow_image_only=True)\n    )\n",
    "Responses request base conversion",
)
g = replace_once(
    g,
    "    if reasoning:\n        out[\"reasoning\"] = reasoning\n    return out\n",
    "    if reasoning:\n        out[\"reasoning\"] = reasoning\n    responses_fidelity.apply_gateway_extensions(out, inbound)\n    return out\n",
    "Responses extensions",
)
GATEWAY.write_text(g, encoding="utf-8")


t = MATRIX_TEST.read_text(encoding="utf-8")
t = replace_once(
    t,
    '        for feature in ("named_tool_choice", "image_input", "structured_output"):\n            with self.subTest(feature=feature):\n                self.assertEqual(self.rows[feature].chat, "degraded")\n                self.assertEqual(self.rows[feature].responses, "degraded")\n',
    '        self.assertEqual(self.rows["named_tool_choice"].chat, "degraded")\n        self.assertEqual(self.rows["named_tool_choice"].responses, "degraded")\n        for feature in ("image_input", "structured_output"):\n            with self.subTest(feature=feature):\n                self.assertEqual(self.rows[feature].chat, "degraded")\n                self.assertEqual(self.rows[feature].responses, "pass")\n',
    "fidelity matrix expected improvements",
)
MATRIX_TEST.write_text(t, encoding="utf-8")
