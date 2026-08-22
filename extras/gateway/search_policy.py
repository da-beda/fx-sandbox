#!/usr/bin/env python3
"""Small policy boundary for the optional Vercel-backed web-search fallback.

Do not copy fx's current default model into the compatibility adapter. When the
adapter needs a private Gateway worker while another LLM provider is active,
resolve a tool-capable worker from the live Gateway catalog instead.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional

CATALOG_URL = "https://ai-gateway.vercel.sh/coding-agent/v1/models"
CACHE_TTL_SECONDS = 300.0
USER_AGENT = "fxs-gateway-search-policy/1"


@dataclass(frozen=True)
class SearchModelResolution:
    model: str = ""
    source: str = ""
    error: str = ""


_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, SearchModelResolution]] = {}


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _key_fingerprint(key: str) -> str:
    return hashlib.sha256((key or "").encode("utf-8")).hexdigest()[:16]


def _catalog_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("data")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def select_tool_capable_model(payload: Any) -> str:
    """Choose from server order; prefer explicit web-search capability if present."""
    tool_capable: list[str] = []
    web_search_capable: list[str] = []
    for row in _catalog_rows(payload):
        model_id = str(row.get("id") or "").strip()
        model_type = str(row.get("type") or row.get("model_type") or "language").lower()
        if not model_id or model_type not in ("", "language"):
            continue
        raw_tags = row.get("tags") or []
        tags = {
            str(tag).strip().lower().replace("_", "-")
            for tag in raw_tags
            if isinstance(tag, str) and str(tag).strip()
        }
        if "tool-use" not in tags:
            continue
        tool_capable.append(model_id)
        if "web-search" in tags or "websearch" in tags:
            web_search_capable.append(model_id)
    if web_search_capable:
        return web_search_capable[0]
    if tool_capable:
        return tool_capable[0]
    return ""


def _http_error(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", "replace")[:500]
    except Exception:
        raw = ""
    message = raw.strip()
    try:
        data = json.loads(raw or "{}")
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                message = str(err.get("message") or err.get("code") or message)
            elif isinstance(err, str):
                message = err
            elif data.get("message"):
                message = str(data.get("message"))
    except json.JSONDecodeError:
        pass
    message = " ".join(message.split())
    return f"Gateway model catalog HTTP {exc.code}" + (f": {message}" if message else "")


def _fetch_catalog(
    key: str,
    *,
    urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> SearchModelResolution:
    req = urllib.request.Request(
        CATALOG_URL,
        method="GET",
        headers={
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as exc:
        return SearchModelResolution(error=_http_error(exc))
    except Exception as exc:
        return SearchModelResolution(error=f"Gateway model catalog unavailable: {exc}")

    model = select_tool_capable_model(payload)
    if not model:
        return SearchModelResolution(
            error="Gateway model catalog did not advertise a tool-capable language model"
        )
    return SearchModelResolution(model=model, source="catalog")


def resolve_vercel_search_model(
    key: str,
    *,
    current_provider_is_vercel: bool = False,
    current_model: str = "",
    getenv: Callable[[str], Optional[str]] = os.environ.get,
    urlopen: Callable[..., Any] = urllib.request.urlopen,
    now: Callable[[], float] = time.monotonic,
) -> SearchModelResolution:
    """Resolve a Gateway worker without owning fx's native product default."""
    override = (getenv("FXS_VERCEL_SEARCH_MODEL") or "").strip()
    if override:
        return SearchModelResolution(model=override, source="override")

    current_model = (current_model or "").strip()
    if current_provider_is_vercel and current_model:
        return SearchModelResolution(model=current_model, source="active-gateway-model")

    key = (key or "").strip()
    if not key:
        return SearchModelResolution(error="Gateway API key is missing")

    cache_key = _key_fingerprint(key)
    stamp = now()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and cached[0] > stamp:
            return cached[1]

    resolved = _fetch_catalog(key, urlopen=urlopen)
    if resolved.model:
        with _CACHE_LOCK:
            _CACHE[cache_key] = (stamp + CACHE_TTL_SECONDS, resolved)
    return resolved
