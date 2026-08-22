#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import search_policy


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class SearchPolicy(unittest.TestCase):
    def setUp(self):
        search_policy.clear_cache()

    def tearDown(self):
        search_policy.clear_cache()

    def test_prefers_explicit_web_search_tag(self):
        payload = {
            "data": [
                {"id": "provider/tool", "type": "language", "tags": ["tool-use"]},
                {"id": "provider/search", "type": "language", "tags": ["tool-use", "web-search"]},
            ]
        }
        self.assertEqual(search_policy.select_tool_capable_model(payload), "provider/search")

    def test_falls_back_to_first_tool_capable_model_in_server_order(self):
        payload = {
            "data": [
                {"id": "provider/plain", "type": "language", "tags": []},
                {"id": "provider/first-tool", "type": "language", "tags": ["tool-use"]},
                {"id": "provider/second-tool", "type": "language", "tags": ["tool-use"]},
            ]
        }
        self.assertEqual(search_policy.select_tool_capable_model(payload), "provider/first-tool")

    def test_ignores_non_language_and_non_tool_models(self):
        payload = {
            "data": [
                {"id": "provider/embed", "type": "embedding", "tags": ["tool-use"]},
                {"id": "provider/plain", "type": "language", "tags": []},
            ]
        }
        self.assertEqual(search_policy.select_tool_capable_model(payload), "")

    def test_override_wins_without_network(self):
        calls = []
        got = search_policy.resolve_vercel_search_model(
            "vck_test",
            getenv=lambda name: "provider/override" if name == "FXS_VERCEL_SEARCH_MODEL" else None,
            urlopen=lambda *_a, **_k: calls.append(True),
        )
        self.assertEqual(got.model, "provider/override")
        self.assertEqual(got.source, "override")
        self.assertEqual(calls, [])

    def test_active_gateway_model_wins_without_network(self):
        calls = []
        got = search_policy.resolve_vercel_search_model(
            "vck_test",
            current_provider_is_vercel=True,
            current_model="provider/active",
            getenv=lambda _name: None,
            urlopen=lambda *_a, **_k: calls.append(True),
        )
        self.assertEqual(got.model, "provider/active")
        self.assertEqual(got.source, "active-gateway-model")
        self.assertEqual(calls, [])

    def test_non_gateway_current_model_is_not_reused(self):
        seen = []

        def fake_open(req, timeout=None):
            seen.append((req.full_url, timeout, dict(req.header_items())))
            return FakeResponse({
                "data": [{"id": "provider/catalog", "type": "language", "tags": ["tool-use"]}]
            })

        got = search_policy.resolve_vercel_search_model(
            "vck_test",
            current_provider_is_vercel=False,
            current_model="grok-4",
            getenv=lambda _name: None,
            urlopen=fake_open,
        )
        self.assertEqual(got.model, "provider/catalog")
        self.assertEqual(got.source, "catalog")
        self.assertEqual(seen[0][0], search_policy.CATALOG_URL)
        headers = {k.lower(): v for k, v in seen[0][2].items()}
        self.assertTrue(headers.get("authorization", "").endswith("vck_test"))

    def test_catalog_result_is_cached_without_storing_raw_key_as_cache_key(self):
        calls = []

        def fake_open(_req, timeout=None):
            calls.append(timeout)
            return FakeResponse({
                "data": [{"id": "provider/catalog", "type": "language", "tags": ["tool-use"]}]
            })

        first = search_policy.resolve_vercel_search_model(
            "vck_secret",
            getenv=lambda _name: None,
            urlopen=fake_open,
            now=lambda: 10.0,
        )
        second = search_policy.resolve_vercel_search_model(
            "vck_secret",
            getenv=lambda _name: None,
            urlopen=lambda *_a, **_k: self.fail("cache miss"),
            now=lambda: 11.0,
        )
        self.assertEqual(first.model, "provider/catalog")
        self.assertEqual(second.model, "provider/catalog")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("vck_secret", search_policy._CACHE)

    def test_http_error_preserves_gateway_message(self):
        def fake_open(req, timeout=None):
            raise HTTPError(
                req.full_url,
                403,
                "Forbidden",
                hdrs=None,
                fp=io.BytesIO(b'{"error":{"message":"credit card required"}}'),
            )

        got = search_policy.resolve_vercel_search_model(
            "vck_test",
            getenv=lambda _name: None,
            urlopen=fake_open,
        )
        self.assertFalse(got.model)
        self.assertIn("HTTP 403", got.error)
        self.assertIn("credit card required", got.error)

    def test_no_tool_capable_catalog_is_explicit_failure(self):
        got = search_policy.resolve_vercel_search_model(
            "vck_test",
            getenv=lambda _name: None,
            urlopen=lambda *_a, **_k: FakeResponse({
                "data": [{"id": "provider/plain", "type": "language", "tags": []}]
            }),
        )
        self.assertFalse(got.model)
        self.assertIn("tool-capable", got.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
