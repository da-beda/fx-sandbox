#!/usr/bin/env python3
from __future__ import annotations

import io
import os
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gateway
import http_limits
import search_policy


class DeclaredResponse:
    def __init__(self, body: bytes = b"{}", *, declared: int | None = None) -> None:
        self.body = body
        self.headers = {}
        if declared is not None:
            self.headers["Content-Length"] = str(declared)
        self.read_calls: list[int] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, n=-1):
        self.read_calls.append(n)
        return self.body if n is None or n < 0 else self.body[:n]


class SearchHttpLimits(unittest.TestCase):
    def setUp(self):
        search_policy.clear_cache()
        self.saved = {}
        for key in (
            "PERPLEXITY_API_KEY",
            "OPENROUTER_API_KEY",
            "OPENAI_API_KEY",
            "FX_UPSTREAM",
            "FX_MODEL",
            "VERCEL_AI_GATEWAY_API_KEY",
            "AI_GATEWAY_API_KEY",
        ):
            self.saved[key] = os.environ.pop(key, None)
        self.original_urlopen = gateway.urllib.request.urlopen

    def tearDown(self):
        gateway.urllib.request.urlopen = self.original_urlopen
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        search_policy.clear_cache()

    def test_search_response_limit_is_large_but_finite(self):
        self.assertEqual(http_limits.SEARCH_RESPONSE_BYTES, 8 * 1024 * 1024)

    def test_search_policy_catalog_rejects_declared_overflow_before_read(self):
        response = DeclaredResponse(
            declared=http_limits.MODEL_CATALOG_BYTES + 1,
        )
        got = search_policy.resolve_vercel_search_model(
            "vck_test",
            getenv=lambda _name: None,
            urlopen=lambda *_a, **_k: response,
        )
        self.assertFalse(got.model)
        self.assertIn("search-model catalog", got.error)
        self.assertIn("local safety limit", got.error)
        self.assertEqual(response.read_calls, [])

    def test_search_policy_http_error_body_is_bounded(self):
        error = HTTPError(
            "https://example.invalid/catalog",
            403,
            "Forbidden",
            hdrs={"Content-Length": str(http_limits.ERROR_BODY_BYTES + 1)},
            fp=io.BytesIO(b"ignored"),
        )
        got = search_policy.resolve_vercel_search_model(
            "vck_test",
            getenv=lambda _name: None,
            urlopen=lambda *_a, **_k: (_ for _ in ()).throw(error),
        )
        self.assertFalse(got.model)
        self.assertIn("HTTP 403", got.error)
        self.assertIn("error body", got.error)
        self.assertIn("local safety limit", got.error)

    def test_direct_perplexity_success_body_is_bounded(self):
        os.environ["PERPLEXITY_API_KEY"] = "pplx-test"
        response = DeclaredResponse(
            declared=http_limits.SEARCH_RESPONSE_BYTES + 1,
        )
        gateway.urllib.request.urlopen = lambda *_a, **_k: response
        got = gateway.run_direct_perplexity_search("query", 5)
        self.assertIn("Perplexity search failed", got.get("error", ""))
        self.assertIn("local safety limit", got.get("error", ""))
        self.assertEqual(response.read_calls, [])

    def test_openrouter_success_body_is_bounded(self):
        os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
        response = DeclaredResponse(
            declared=http_limits.SEARCH_RESPONSE_BYTES + 1,
        )
        gateway.urllib.request.urlopen = lambda *_a, **_k: response
        got = gateway.run_openrouter_search("query", 5)
        self.assertIn("OpenRouter search failed", got.get("error", ""))
        self.assertIn("local safety limit", got.get("error", ""))
        self.assertEqual(response.read_calls, [])

    def test_direct_perplexity_error_body_is_bounded(self):
        os.environ["PERPLEXITY_API_KEY"] = "pplx-test"
        error = HTTPError(
            "https://api.perplexity.ai/search",
            500,
            "Server Error",
            hdrs={"Content-Length": str(http_limits.ERROR_BODY_BYTES + 1)},
            fp=io.BytesIO(b"ignored"),
        )
        gateway.urllib.request.urlopen = lambda *_a, **_k: (_ for _ in ()).throw(error)
        got = gateway.run_direct_perplexity_search("query", 5)
        self.assertIn("HTTP 500", got.get("error", ""))
        self.assertIn("error body", got.get("error", ""))
        self.assertIn("local safety limit", got.get("error", ""))

    def test_openrouter_error_body_is_bounded(self):
        os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
        error = HTTPError(
            "https://openrouter.ai/api/v1/chat/completions",
            500,
            "Server Error",
            hdrs={"Content-Length": str(http_limits.ERROR_BODY_BYTES + 1)},
            fp=io.BytesIO(b"ignored"),
        )
        gateway.urllib.request.urlopen = lambda *_a, **_k: (_ for _ in ()).throw(error)
        got = gateway.run_openrouter_search("query", 5)
        self.assertIn("HTTP 500", got.get("error", ""))
        self.assertIn("error body", got.get("error", ""))
        self.assertIn("local safety limit", got.get("error", ""))

    def test_vercel_gateway_search_error_body_is_bounded(self):
        error = HTTPError(
            "https://ai-gateway.vercel.sh/v3/ai/language-model",
            500,
            "Server Error",
            hdrs={"Content-Length": str(http_limits.ERROR_BODY_BYTES + 1)},
            fp=io.BytesIO(b"ignored"),
        )
        message = gateway._gateway_http_error(error)
        self.assertIn("HTTP 500", message)
        self.assertIn("error body", message)
        self.assertIn("local safety limit", message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
