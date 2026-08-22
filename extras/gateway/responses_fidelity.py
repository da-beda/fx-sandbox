#!/usr/bin/env python3
"""OpenAI Responses-specific semantic adapters for Gateway request extensions.

These mappings follow the same wire concepts used by upstream fx's native
OpenAI-compatible Responses work while remaining independent of provider/model
capability admission. This module does not claim that an arbitrary local model
supports vision or structured output; it only preserves the semantics when fx
has already emitted them.
"""
from __future__ import annotations

from typing import Any


def _image_part(part: Any) -> dict[str, Any] | None:
    if not isinstance(part, dict) or part.get("type") != "file":
        return None
    media_type = str(part.get("mediaType") or part.get("media_type") or "").strip().lower()
    data = part.get("data")
    if not media_type.startswith("image/") or not isinstance(data, str) or not data:
        return None
    url = data if data.startswith("data:") else f"data:{media_type};base64,{data}"
    return {
        "type": "input_image",
        "image_url": url,
        "detail": "auto",
    }


def _user_multimodal_content(raw: Any) -> list[dict[str, Any]] | None:
    if not isinstance(raw, list):
        return None
    out: list[dict[str, Any]] = []
    saw_image = False
    for part in raw:
        if not isinstance(part, dict):
            continue
        ptype = str(part.get("type") or "text")
        if ptype in ("text", ""):
            text = str(part.get("text") or "")
            if text:
                out.append({"type": "input_text", "text": text})
            continue
        image = _image_part(part)
        if image is not None:
            out.append(image)
            saw_image = True
    return out if saw_image else None


def preserve_user_images(responses: dict[str, Any], prompt: Any) -> None:
    """Replace matching Responses user items with multimodal content in place."""
    if not isinstance(prompt, list):
        return
    source_users = [
        msg for msg in prompt
        if isinstance(msg, dict) and msg.get("role") == "user"
    ]
    if not source_users:
        return

    user_index = 0
    for item in responses.get("input") or []:
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        if user_index >= len(source_users):
            break
        source = source_users[user_index]
        user_index += 1
        content = _user_multimodal_content(source.get("content"))
        if content is not None:
            item["content"] = content


def structured_response_format(raw: Any) -> dict[str, Any] | None:
    """Gateway responseFormat -> OpenAI Responses text.format json_schema."""
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("type") or "").strip().lower()
    name = str(raw.get("name") or "").strip()
    schema = raw.get("schema")
    if kind != "json" or not name or not isinstance(schema, dict):
        return None
    fmt: dict[str, Any] = {
        "type": "json_schema",
        "name": name,
        "schema": schema,
        "strict": True,
    }
    description = raw.get("description")
    if isinstance(description, str) and description:
        fmt["description"] = description
    return fmt


def apply_gateway_extensions(responses: dict[str, Any], inbound: Any) -> dict[str, Any]:
    if not isinstance(inbound, dict):
        return responses
    preserve_user_images(responses, inbound.get("prompt"))
    fmt = structured_response_format(inbound.get("responseFormat"))
    if fmt is not None:
        responses["text"] = {"format": fmt}
    return responses
