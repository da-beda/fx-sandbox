#!/usr/bin/env python3
"""Resource limits for untrusted OpenAI-compatible streaming responses.

An OpenAI-compatible endpoint may be local, remote, experimental, or malicious.
The adapter therefore must not let SSE framing or streamed tool state grow
without bound. Defaults intentionally mirror the scale of upstream fx's native
OpenAI transport rather than imposing small latency/quality-oriented limits.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class StreamLimitError(ValueError):
    pass


@dataclass(frozen=True)
class StreamLimits:
    # Matches upstream's native OpenAI transport scale: large enough for heavily
    # escaped structured events, but finite against accidental/malicious input.
    sse_line_bytes: int = 32 * 1024 * 1024
    sse_aggregate_bytes: int = 64 * 1024 * 1024
    sse_events: int = 100_000
    tool_calls: int = 128
    tool_identity_bytes: int = 1024
    tool_arguments_bytes: int = 4 * 1024 * 1024

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if int(value) <= 0:
                raise ValueError(f"{name} must be positive")


DEFAULT_LIMITS = StreamLimits()


def utf8_size(value: str) -> int:
    return len(value.encode("utf-8", "strict"))


def checked_total(current: int, additional: int, maximum: int, label: str) -> int:
    if current < 0 or additional < 0 or maximum <= 0:
        raise StreamLimitError(f"invalid {label} accounting")
    total = current + additional
    if total > maximum:
        raise StreamLimitError(f"{label} exceeds local safety limit ({maximum} bytes)")
    return total


def require_identity(value: Any, limits: StreamLimits, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise StreamLimitError(f"{label} is missing or not a string")
    if utf8_size(value) > limits.tool_identity_bytes:
        raise StreamLimitError(
            f"{label} exceeds local safety limit ({limits.tool_identity_bytes} bytes)"
        )
    return value


def reserve_tool(existing_count: int, limits: StreamLimits) -> None:
    if existing_count >= limits.tool_calls:
        raise StreamLimitError(
            f"tool call count exceeds local safety limit ({limits.tool_calls})"
        )


def append_arguments(acc: dict[str, Any], delta: Any, limits: StreamLimits) -> None:
    if not isinstance(delta, str):
        raise StreamLimitError("tool arguments are not a string")
    if not delta:
        return
    previous = acc.get("args") or ""
    if not isinstance(previous, str):
        raise StreamLimitError("tool argument accumulator is invalid")
    current_bytes = acc.get("_args_bytes")
    if not isinstance(current_bytes, int):
        current_bytes = utf8_size(previous)
    total = checked_total(
        current_bytes,
        utf8_size(delta),
        limits.tool_arguments_bytes,
        "tool arguments",
    )
    acc["args"] = previous + delta
    acc["_args_bytes"] = total
