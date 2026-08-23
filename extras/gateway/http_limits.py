#!/usr/bin/env python3
"""Finite body limits for the optional Gateway compatibility proxy.

OpenAI-compatible endpoints are untrusted input. Streaming responses are bounded
in ``stream_limits.py``; this module covers non-stream HTTP bodies and the
loopback Gateway request body so alternate code paths cannot bypass those
resource ceilings.
"""
from __future__ import annotations

from typing import Any

MODEL_CATALOG_BYTES = 4 * 1024 * 1024
ERROR_BODY_BYTES = 1 * 1024 * 1024
SEARCH_RESPONSE_BYTES = 8 * 1024 * 1024
NONSTREAM_COMPLETION_BYTES = 64 * 1024 * 1024
GATEWAY_REQUEST_BYTES = 64 * 1024 * 1024


class BodyLimitError(ValueError):
    pass


class InvalidContentLength(BodyLimitError):
    pass


class RequestBodyTooLarge(BodyLimitError):
    pass


def _declared_length(resp: Any) -> int | None:
    headers = getattr(resp, "headers", None)
    if headers is None:
        return None
    try:
        raw = headers.get("Content-Length")
    except Exception:
        return None
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def read_limited(resp: Any, maximum: int, label: str) -> bytes:
    """Read at most ``maximum`` bytes, rejecting declared or observed overflow."""
    if maximum <= 0:
        raise ValueError("maximum must be positive")
    declared = _declared_length(resp)
    if declared is not None and declared > maximum:
        raise BodyLimitError(f"{label} exceeds local safety limit ({maximum} bytes)")

    try:
        body = resp.read(maximum + 1)
    except TypeError:
        # Several deterministic test doubles implement the older read() shape.
        # Real urllib/http.client responses accept an amount argument. Preserve
        # fixture compatibility while still rejecting the returned body size.
        body = resp.read()
    if body is None:
        body = b""
    if not isinstance(body, (bytes, bytearray)):
        raise BodyLimitError(f"{label} did not return bytes")
    body = bytes(body)
    if len(body) > maximum:
        raise BodyLimitError(f"{label} exceeds local safety limit ({maximum} bytes)")
    return body


def parse_content_length(raw: Any, maximum: int = GATEWAY_REQUEST_BYTES) -> int:
    """Validate an inbound Content-Length without allowing negative/read-all values."""
    if maximum <= 0:
        raise ValueError("maximum must be positive")
    if raw in (None, ""):
        return 0
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise InvalidContentLength("invalid Content-Length") from exc
    if value < 0:
        raise InvalidContentLength("invalid Content-Length")
    if value > maximum:
        raise RequestBodyTooLarge(
            f"Gateway request exceeds local safety limit ({maximum} bytes)"
        )
    return value
