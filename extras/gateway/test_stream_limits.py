#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gateway
import stream_limits


def limits(**overrides) -> stream_limits.StreamLimits:
    values = {
        "sse_line_bytes": 1024,
        "sse_aggregate_bytes": 4096,
        "sse_events": 32,
        "tool_calls": 8,
        "tool_identity_bytes": 128,
        "tool_arguments_bytes": 1024,
    }
    values.update(overrides)
    return stream_limits.StreamLimits(**values)


class SseLimits(unittest.TestCase):
    def test_oversized_sse_line_is_rejected_before_json_decode(self):
        lim = limits(sse_line_bytes=16, sse_aggregate_bytes=128)
        source = io.BytesIO(b"data: " + b"x" * 32 + b"\n\n")
        with self.assertRaises(stream_limits.StreamLimitError) as cm:
            list(gateway.read_sse_data(source, limits=lim))
        self.assertIn("SSE line", str(cm.exception))

    def test_aggregate_stream_bytes_are_bounded(self):
        lim = limits(sse_line_bytes=64, sse_aggregate_bytes=24)
        source = io.BytesIO(
            b'data: {"x":1}\n\n'
            b'data: {"x":2}\n\n'
        )
        with self.assertRaises(stream_limits.StreamLimitError) as cm:
            list(gateway.read_sse_data(source, limits=lim))
        self.assertIn("SSE aggregate", str(cm.exception))

    def test_event_count_is_bounded(self):
        lim = limits(sse_events=2)
        source = io.BytesIO(b"data: 1\n\ndata: 2\n\ndata: 3\n\n")
        with self.assertRaises(stream_limits.StreamLimitError) as cm:
            list(gateway.read_sse_data(source, limits=lim))
        self.assertIn("event count", str(cm.exception))

    def test_normal_multiline_sse_event_still_joins_data_lines(self):
        lim = limits()
        source = io.BytesIO(b"event: custom\ndata: {\"value\":\ndata: 1}\n\n")
        payloads = list(gateway.read_sse_data(source, limits=lim))
        self.assertEqual(len(payloads), 1)
        parsed = json.loads(payloads[0])
        self.assertEqual(parsed["type"], "custom")
        self.assertEqual(parsed["value"], 1)


class ToolLimits(unittest.TestCase):
    def test_chat_tool_argument_accumulator_is_bounded(self):
        s = gateway.Stream(limits=limits(tool_arguments_bytes=8))
        payload = json.dumps({
            "choices": [{"delta": {"tool_calls": [{
                "index": 0,
                "id": "c1",
                "function": {"name": "terminal", "arguments": "123456789"},
            }]}}],
        })
        with self.assertRaises(stream_limits.StreamLimitError) as cm:
            s.consume(payload)
        self.assertIn("tool arguments", str(cm.exception))

    def test_responses_tool_argument_accumulator_is_bounded(self):
        s = gateway.ResponseStream(limits=limits(tool_arguments_bytes=8))
        s.consume(json.dumps({
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "id": "fc_1",
                "type": "function_call",
                "call_id": "c1",
                "name": "terminal",
            },
        }))
        with self.assertRaises(stream_limits.StreamLimitError) as cm:
            s.consume(json.dumps({
                "type": "response.function_call_arguments.delta",
                "output_index": 0,
                "item_id": "fc_1",
                "delta": "123456789",
            }))
        self.assertIn("tool arguments", str(cm.exception))

    def test_chat_tool_count_is_bounded(self):
        s = gateway.Stream(limits=limits(tool_calls=1))
        payload = json.dumps({
            "choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "c1", "function": {"name": "one", "arguments": "{}"}},
                {"index": 1, "id": "c2", "function": {"name": "two", "arguments": "{}"}},
            ]}}],
        })
        with self.assertRaises(stream_limits.StreamLimitError) as cm:
            s.consume(payload)
        self.assertIn("tool call count", str(cm.exception))

    def test_tool_identity_is_bounded(self):
        s = gateway.Stream(limits=limits(tool_identity_bytes=4))
        payload = json.dumps({
            "choices": [{"delta": {"tool_calls": [{
                "index": 0,
                "id": "call-too-long",
                "function": {"name": "tool", "arguments": "{}"},
            }]}}],
        })
        with self.assertRaises(stream_limits.StreamLimitError) as cm:
            s.consume(payload)
        self.assertIn("tool call id", str(cm.exception))

    def test_within_limit_tool_stream_preserves_existing_behavior(self):
        s = gateway.Stream(limits=limits(tool_arguments_bytes=64, tool_identity_bytes=32))
        got = s.consume(json.dumps({
            "choices": [{"delta": {"tool_calls": [{
                "index": 0,
                "id": "c1",
                "function": {"name": "terminal", "arguments": '{"command":"pwd"}'},
            }]}}],
        }))
        got += s.consume(json.dumps({
            "choices": [{"delta": {}, "finish_reason": "tool_calls"}],
        }))
        parsed = [json.loads(event) for event in got]
        call = next(event for event in parsed if event.get("type") == "tool-call")
        self.assertEqual(call["toolCallId"], "c1")
        self.assertEqual(call["input"], {"command": "pwd"})


class LimitDefinitions(unittest.TestCase):
    def test_defaults_are_large_but_finite(self):
        lim = stream_limits.DEFAULT_LIMITS
        self.assertEqual(lim.sse_line_bytes, 32 * 1024 * 1024)
        self.assertEqual(lim.sse_aggregate_bytes, 64 * 1024 * 1024)
        self.assertEqual(lim.sse_events, 100_000)
        self.assertEqual(lim.tool_calls, 128)
        self.assertEqual(lim.tool_identity_bytes, 1024)
        self.assertEqual(lim.tool_arguments_bytes, 4 * 1024 * 1024)

    def test_non_positive_limits_are_rejected(self):
        with self.assertRaises(ValueError):
            limits(tool_calls=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
