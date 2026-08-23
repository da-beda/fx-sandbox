#!/usr/bin/env python3
from __future__ import annotations

import unittest

import http_limits


class Headers(dict):
    pass


class BoundedResponse:
    def __init__(self, body: bytes, declared: int | None = None) -> None:
        self.body = body
        self.headers = Headers()
        if declared is not None:
            self.headers["Content-Length"] = str(declared)
        self.read_sizes: list[int] = []

    def read(self, n=-1):
        self.read_sizes.append(n)
        return self.body if n is None or n < 0 else self.body[:n]


class LegacyResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.headers = Headers()

    def read(self):
        return self.body


class HttpBodyLimits(unittest.TestCase):
    def test_bounded_read_uses_maximum_plus_one(self):
        resp = BoundedResponse(b"abcd")
        self.assertEqual(http_limits.read_limited(resp, 4, "body"), b"abcd")
        self.assertEqual(resp.read_sizes, [5])

    def test_observed_overflow_is_rejected(self):
        resp = BoundedResponse(b"abcde")
        with self.assertRaises(http_limits.BodyLimitError) as cm:
            http_limits.read_limited(resp, 4, "body")
        self.assertIn("body", str(cm.exception))

    def test_declared_overflow_is_rejected_before_read(self):
        resp = BoundedResponse(b"x", declared=100)
        with self.assertRaises(http_limits.BodyLimitError):
            http_limits.read_limited(resp, 4, "catalog")
        self.assertEqual(resp.read_sizes, [])

    def test_legacy_test_double_is_checked_after_read(self):
        self.assertEqual(
            http_limits.read_limited(LegacyResponse(b"abcd"), 4, "body"),
            b"abcd",
        )
        with self.assertRaises(http_limits.BodyLimitError):
            http_limits.read_limited(LegacyResponse(b"abcde"), 4, "body")

    def test_non_bytes_body_is_rejected(self):
        class Bad:
            headers = Headers()
            def read(self, _n=-1):
                return "not-bytes"
        with self.assertRaises(http_limits.BodyLimitError):
            http_limits.read_limited(Bad(), 16, "body")

    def test_content_length_accepts_missing_zero_and_boundary(self):
        self.assertEqual(http_limits.parse_content_length(None, 10), 0)
        self.assertEqual(http_limits.parse_content_length("0", 10), 0)
        self.assertEqual(http_limits.parse_content_length("10", 10), 10)

    def test_content_length_rejects_negative_invalid_and_overflow(self):
        for raw in ("-1", "abc", "11"):
            with self.subTest(raw=raw):
                with self.assertRaises(http_limits.BodyLimitError):
                    http_limits.parse_content_length(raw, 10)

    def test_default_limits_are_large_but_finite(self):
        self.assertEqual(http_limits.MODEL_CATALOG_BYTES, 4 * 1024 * 1024)
        self.assertEqual(http_limits.ERROR_BODY_BYTES, 1 * 1024 * 1024)
        self.assertEqual(http_limits.NONSTREAM_COMPLETION_BYTES, 64 * 1024 * 1024)
        self.assertEqual(http_limits.GATEWAY_REQUEST_BYTES, 64 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main(verbosity=2)
