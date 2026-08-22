#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import responses_fidelity


class ResponsesFidelity(unittest.TestCase):
    def test_preserves_text_and_image_order(self):
        out = {"input": [{"role": "user", "content": "describe"}]}
        prompt = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "before"},
                {"type": "file", "mediaType": "image/png", "data": "YWJj"},
                {"type": "text", "text": "after"},
            ],
        }]
        responses_fidelity.preserve_user_images(out, prompt)
        self.assertEqual(out["input"][0]["content"], [
            {"type": "input_text", "text": "before"},
            {
                "type": "input_image",
                "image_url": "data:image/png;base64,YWJj",
                "detail": "auto",
            },
            {"type": "input_text", "text": "after"},
        ])

    def test_preserves_image_only_user_message(self):
        out = {"input": [{"role": "user", "content": ""}]}
        prompt = [{
            "role": "user",
            "content": [{"type": "file", "mediaType": "image/jpeg", "data": "YWJj"}],
        }]
        responses_fidelity.preserve_user_images(out, prompt)
        self.assertEqual(out["input"][0]["content"][0]["type"], "input_image")
        self.assertEqual(out["input"][0]["content"][0]["image_url"], "data:image/jpeg;base64,YWJj")

    def test_existing_data_url_is_not_double_wrapped(self):
        out = {"input": [{"role": "user", "content": ""}]}
        prompt = [{
            "role": "user",
            "content": [{
                "type": "file",
                "mediaType": "image/webp",
                "data": "data:image/webp;base64,YWJj",
            }],
        }]
        responses_fidelity.preserve_user_images(out, prompt)
        self.assertEqual(
            out["input"][0]["content"][0]["image_url"],
            "data:image/webp;base64,YWJj",
        )

    def test_non_image_file_does_not_claim_image_support(self):
        out = {"input": [{"role": "user", "content": "read"}]}
        prompt = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "read"},
                {"type": "file", "mediaType": "application/pdf", "data": "YWJj"},
            ],
        }]
        responses_fidelity.preserve_user_images(out, prompt)
        self.assertEqual(out["input"][0]["content"], "read")

    def test_multiple_user_messages_align_independently(self):
        out = {
            "input": [
                {"role": "user", "content": "first"},
                {"type": "message", "role": "assistant", "content": "ok"},
                {"role": "user", "content": "second"},
            ]
        }
        prompt = [
            {"role": "user", "content": [{"type": "text", "text": "first"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "second"},
                    {"type": "file", "mediaType": "image/png", "data": "YWJj"},
                ],
            },
        ]
        responses_fidelity.preserve_user_images(out, prompt)
        self.assertEqual(out["input"][0]["content"], "first")
        self.assertEqual(out["input"][2]["content"][0], {"type": "input_text", "text": "second"})
        self.assertEqual(out["input"][2]["content"][1]["type"], "input_image")

    def test_structured_response_format(self):
        raw = {
            "type": "json",
            "name": "fixture",
            "description": "fixture schema",
            "schema": {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
        }
        got = responses_fidelity.structured_response_format(raw)
        self.assertEqual(got, {
            "type": "json_schema",
            "name": "fixture",
            "description": "fixture schema",
            "schema": raw["schema"],
            "strict": True,
        })

    def test_invalid_structured_format_is_not_invented(self):
        for raw in (
            None,
            {},
            {"type": "text", "name": "x", "schema": {}},
            {"type": "json", "schema": {}},
            {"type": "json", "name": "x", "schema": []},
        ):
            with self.subTest(raw=raw):
                self.assertIsNone(responses_fidelity.structured_response_format(raw))

    def test_apply_gateway_extensions_combines_features(self):
        out = {"input": [{"role": "user", "content": "describe"}]}
        inbound = {
            "prompt": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe"},
                    {"type": "file", "mediaType": "image/png", "data": "YWJj"},
                ],
            }],
            "responseFormat": {
                "type": "json",
                "name": "vision",
                "schema": {"type": "object"},
            },
        }
        responses_fidelity.apply_gateway_extensions(out, inbound)
        self.assertEqual(out["input"][0]["content"][1]["type"], "input_image")
        self.assertEqual(out["text"]["format"]["type"], "json_schema")
        self.assertTrue(out["text"]["format"]["strict"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
