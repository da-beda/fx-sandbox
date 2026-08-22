#!/usr/bin/env python3
"""Executable protocol-fidelity inventory for the optional Gateway adapter.

This module probes translation behavior instead of maintaining a hand-written
feature checklist. It is intentionally small and credential-free. A future
native fx transport can be compared against the same semantic cases before the
adapter is bypassed for any capability.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import gateway  # noqa: E402

PASS = "pass"
DEGRADED = "degraded"


@dataclass(frozen=True)
class FidelityResult:
    feature: str
    chat: str
    responses: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _body(value: dict) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def _base_prompt(content="hello") -> dict:
    return {
        "prompt": [{"role": "user", "content": content}],
        "toolChoice": {"type": "auto"},
    }


def probe_text() -> FidelityResult:
    body = _body(_base_prompt([{"type": "text", "text": "hello"}]))
    chat = gateway.chat_request("model", True, body)
    responses = gateway.responses_request("model", True, body)
    chat_ok = chat["messages"] == [{"role": "user", "content": "hello"}]
    response_ok = responses["input"] == [{"role": "user", "content": "hello"}]
    return FidelityResult(
        "text",
        PASS if chat_ok else DEGRADED,
        PASS if response_ok else DEGRADED,
        "plain user text survives request translation",
    )


def probe_output_limit() -> FidelityResult:
    request = _base_prompt()
    request["maxOutputTokens"] = 4096
    body = _body(request)
    chat = gateway.chat_request("model", True, body)
    responses = gateway.responses_request("model", True, body)
    return FidelityResult(
        "max_output_tokens",
        PASS if chat.get("max_tokens") == 4096 else DEGRADED,
        PASS if responses.get("max_output_tokens") == 4096 else DEGRADED,
        "Gateway maxOutputTokens maps to the target API output limit",
    )


def probe_tools_and_history() -> FidelityResult:
    request = {
        "prompt": [
            {"role": "user", "content": [{"type": "text", "text": "list"}]},
            {
                "role": "assistant",
                "content": [{
                    "type": "tool-call",
                    "toolCallId": "call_1",
                    "toolName": "terminal",
                    "input": {"command": "ls"},
                }],
            },
            {
                "role": "tool",
                "content": [{
                    "type": "tool-result",
                    "toolCallId": "call_1",
                    "toolName": "terminal",
                    "output": {"type": "text", "value": "a.txt"},
                }],
            },
        ],
        "tools": [{
            "type": "function",
            "name": "terminal",
            "description": "Run a command",
            "inputSchema": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        }],
        "toolChoice": {"type": "auto"},
    }
    body = _body(request)
    chat = gateway.chat_request("model", True, body)
    responses = gateway.responses_request("model", True, body)
    chat_calls = chat["messages"][1].get("tool_calls") or []
    chat_result = chat["messages"][2]
    chat_ok = (
        bool(chat.get("tools"))
        and len(chat_calls) == 1
        and chat_calls[0]["id"] == "call_1"
        and chat_result.get("tool_call_id") == "call_1"
        and chat_result.get("content") == "a.txt"
    )
    response_types = [item.get("type") for item in responses.get("input") or []]
    responses_ok = (
        bool(responses.get("tools"))
        and "function_call" in response_types
        and "function_call_output" in response_types
    )
    return FidelityResult(
        "tools_and_history",
        PASS if chat_ok else DEGRADED,
        PASS if responses_ok else DEGRADED,
        "function schemas, assistant calls, and tool results retain call identity",
    )


def probe_named_tool_choice() -> FidelityResult:
    request = _base_prompt()
    request["tools"] = [{
        "type": "function",
        "name": "terminal",
        "description": "Run a command",
        "inputSchema": {"type": "object", "properties": {}},
    }]
    request["toolChoice"] = {"type": "tool", "toolName": "terminal"}
    body = _body(request)
    chat = gateway.chat_request("model", True, body)
    responses = gateway.responses_request("model", True, body)
    return FidelityResult(
        "named_tool_choice",
        PASS if chat.get("tool_choice") else DEGRADED,
        PASS if responses.get("tool_choice") else DEGRADED,
        "a Gateway request that pins one tool is currently accepted but the pin is dropped",
    )


def probe_reasoning() -> FidelityResult:
    request = _base_prompt()
    request["reasoning"] = "high"
    body = _body(request)
    chat = gateway.chat_request("model", True, body)
    responses = gateway.responses_request("model", True, body)
    return FidelityResult(
        "reasoning_effort",
        PASS if chat.get("reasoning") == {"effort": "high"} else DEGRADED,
        PASS if responses.get("reasoning") == {"effort": "high"} else DEGRADED,
        "reasoning effort is represented by Responses; Chat currently drops it",
    )


def probe_images() -> FidelityResult:
    request = _base_prompt([
        {"type": "text", "text": "describe"},
        {"type": "file", "mediaType": "image/png", "data": "aGVsbG8="},
    ])
    body = _body(request)
    chat = gateway.chat_request("model", True, body)
    responses = gateway.responses_request("model", True, body)
    chat_content = chat["messages"][0].get("content")
    response_content = responses["input"][0].get("content")
    chat_kept_image = isinstance(chat_content, list) and any(
        isinstance(item, dict) and item.get("type") in ("image_url", "input_image")
        for item in chat_content
    )
    responses_kept_image = isinstance(response_content, list) and any(
        isinstance(item, dict) and item.get("type") == "input_image"
        for item in response_content
    )

    image_only_rejected = False
    image_only = _body(_base_prompt([
        {"type": "file", "mediaType": "image/png", "data": "aGVsbG8="},
    ]))
    try:
        gateway.chat_request("model", True, image_only)
    except gateway.TranslateError as exc:
        image_only_rejected = exc.code == gateway.ERR_IMAGE_ONLY

    detail = (
        "Gateway file parts are currently dropped when text is present; "
        "image-only input is rejected"
        if image_only_rejected
        else "Gateway image semantics are not fully preserved"
    )
    return FidelityResult(
        "image_input",
        PASS if chat_kept_image else DEGRADED,
        PASS if responses_kept_image else DEGRADED,
        detail,
    )


def probe_structured_output() -> FidelityResult:
    request = _base_prompt()
    request["responseFormat"] = {
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
    body = _body(request)
    chat = gateway.chat_request("model", True, body)
    responses = gateway.responses_request("model", True, body)
    chat_kept = "response_format" in chat
    responses_kept = bool(
        responses.get("text")
        or responses.get("response_format")
        or responses.get("responseFormat")
    )
    return FidelityResult(
        "structured_output",
        PASS if chat_kept else DEGRADED,
        PASS if responses_kept else DEGRADED,
        "Gateway responseFormat is currently accepted but not forwarded",
    )


def probe_stream_text() -> FidelityResult:
    stream = gateway.Stream()
    chat_events = stream.consume(
        b'{"choices":[{"delta":{"content":"hello"},"finish_reason":"stop"}]}'
    )
    chat_types = [json.loads(event)["type"] for event in chat_events]

    responses_stream = gateway.ResponseStream()
    response_events = responses_stream.consume(
        b'{"type":"response.output_text.delta","delta":"hello"}'
    )
    response_types = [json.loads(event)["type"] for event in response_events]
    return FidelityResult(
        "streamed_text",
        PASS if "text-delta" in chat_types else DEGRADED,
        PASS if "text-delta" in response_types else DEGRADED,
        "streamed text deltas translate into Gateway text-delta events",
    )


def probe_stream_tool_calls() -> FidelityResult:
    stream = gateway.Stream(allowed_tools=["terminal"])
    events = stream.consume(
        json.dumps({
            "choices": [{"delta": {"tool_calls": [{
                "index": 0,
                "id": "call_1",
                "function": {"name": "terminal", "arguments": "{}"},
            }]}}],
        })
    )
    events += stream.consume(b'{"choices":[{"delta":{},"finish_reason":"tool_calls"}]}')
    chat_types = [json.loads(event)["type"] for event in events]

    responses_stream = gateway.ResponseStream(allowed_tools=["terminal"])
    response_events = responses_stream.consume(json.dumps({
        "type": "response.output_item.added",
        "item": {
            "type": "function_call",
            "id": "item_1",
            "call_id": "call_1",
            "name": "terminal",
            "arguments": "{}",
        },
    }))
    response_events += responses_stream.consume(json.dumps({
        "type": "response.completed",
        "response": {"status": "completed", "output": []},
    }))
    response_types = [json.loads(event)["type"] for event in response_events]
    return FidelityResult(
        "streamed_tool_calls",
        PASS if "tool-call" in chat_types else DEGRADED,
        PASS if "tool-call" in response_types else DEGRADED,
        "streamed function calls retain tool identity and arguments",
    )


def probe_stream_reasoning() -> FidelityResult:
    # Chat-compatible servers expose reasoning under non-standard fields, which
    # this adapter intentionally does not forward today.
    chat = gateway.Stream()
    chat_events = chat.consume(
        b'{"choices":[{"delta":{"reasoning_content":"think"}}]}'
    )
    responses_stream = gateway.ResponseStream()
    response_events = responses_stream.consume(
        b'{"type":"response.reasoning_summary_text.delta","delta":"think"}'
    )
    response_types = [json.loads(event)["type"] for event in response_events]
    return FidelityResult(
        "streamed_reasoning",
        PASS if any(json.loads(event).get("type") == "reasoning-delta" for event in chat_events) else DEGRADED,
        PASS if "reasoning-delta" in response_types else DEGRADED,
        "Responses reasoning deltas are preserved; non-standard Chat reasoning deltas are dropped",
    )


PROBES: tuple[Callable[[], FidelityResult], ...] = (
    probe_text,
    probe_output_limit,
    probe_tools_and_history,
    probe_named_tool_choice,
    probe_reasoning,
    probe_images,
    probe_structured_output,
    probe_stream_text,
    probe_stream_tool_calls,
    probe_stream_reasoning,
)


def evaluate() -> list[FidelityResult]:
    return [probe() for probe in PROBES]


def as_document() -> dict:
    rows = [result.to_dict() for result in evaluate()]
    return {
        "schema": 1,
        "status_semantics": {
            PASS: "semantic case preserved by this adapter path",
            DEGRADED: "request is accepted or partially translated but semantics are lost or rejected",
        },
        "features": rows,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Probe fx-sandbox Gateway protocol fidelity")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)
    document = as_document()
    if args.json:
        print(json.dumps(document, sort_keys=True))
        return 0
    print("feature\tchat\tresponses\tdetail")
    for row in document["features"]:
        print(f"{row['feature']}\t{row['chat']}\t{row['responses']}\t{row['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
