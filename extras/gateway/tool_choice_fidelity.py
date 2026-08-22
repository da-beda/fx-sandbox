#!/usr/bin/env python3
"""Translate Gateway toolChoice into the target OpenAI API shape."""
from __future__ import annotations

from typing import Any


def translate(raw: Any, api: str) -> Any:
    if isinstance(raw, str):
        kind = raw.strip().lower()
        return kind if kind in ("auto", "required", "none") else None
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("type") or "").strip().lower()
    if kind in ("auto", "required", "none"):
        return kind
    if kind != "tool":
        return None
    name = str(raw.get("toolName") or raw.get("tool_name") or raw.get("name") or "").strip()
    if not name:
        return None
    if (api or "chat").strip().lower() == "responses":
        return {"type": "function", "name": name}
    return {"type": "function", "function": {"name": name}}
