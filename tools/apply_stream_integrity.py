#!/usr/bin/env python3
from pathlib import Path

GATEWAY = Path("extras/gateway/gateway.py")
TESTS = Path("extras/gateway/test_gateway.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


g = GATEWAY.read_text(encoding="utf-8")
g = replace_once(
    g,
    '''    def close(self) -> list[bytes]:
        if self.finished:
            return []
        return self._finalize("stop", {})
''',
    '''    def close(self, terminal: bool = False) -> list[bytes]:
        """Close a stream without converting bare EOF into success.

        A provider finish reason / Responses terminal event marks ``finished``
        before this method runs. ``terminal=True`` is reserved for an explicit
        SSE ``[DONE]`` sentinel. A bare transport EOF is incomplete evidence and
        must fail instead of being committed as a successful turn.
        """
        if self.finished:
            return []
        if terminal:
            return self._finalize("stop", {})
        return self.fail("upstream stream ended before a terminal event")
''',
    "stream close integrity",
)
g = replace_once(
    g,
    '''            try:
                for data in read_sse_data(resp):
                    if data.strip() == "[DONE]":
                        break
                    self._write_search_events(conv.consume(data), conv)
                self._write_search_events(conv.close(), conv)
            except Exception as e:
''',
    '''            try:
                saw_done = False
                for data in read_sse_data(resp):
                    if data.strip() == "[DONE]":
                        saw_done = True
                        break
                    self._write_search_events(conv.consume(data), conv)
                self._write_search_events(conv.close(terminal=saw_done), conv)
            except Exception as e:
''',
    "stream loop terminal evidence",
)
GATEWAY.write_text(g, encoding="utf-8")


t = TESTS.read_text(encoding="utf-8")
marker = '    def test_tool_call_fragments(self):\n'
insert = '''    def test_bare_eof_after_partial_chat_is_error(self):
        s = gateway.Stream()
        got = s.consume(b'{"choices":[{"delta":{"content":"partial"}}]}')
        got += s.close()
        parsed = [json.loads(e) for e in got]
        self.assertEqual([e["type"] for e in parsed], ["text-delta", "error", "finish"])
        self.assertIn("terminal event", str(parsed[1].get("error") or ""))
        self.assertEqual(parsed[2]["finishReason"]["unified"], "error")

    def test_done_sentinel_can_close_without_finish_chunk(self):
        s = gateway.Stream()
        got = s.consume(b'{"choices":[{"delta":{"content":"complete"}}]}')
        got += s.close(terminal=True)
        parsed = [json.loads(e) for e in got]
        self.assertEqual([e["type"] for e in parsed], ["text-delta", "finish"])
        self.assertEqual(parsed[1]["finishReason"]["unified"], "stop")

'''
t = replace_once(t, marker, insert + marker, "chat EOF regression tests")

response_marker = '    def test_tool_call_deltas(self):\n'
response_insert = '''    def test_bare_eof_after_partial_responses_stream_is_error(self):
        s = gateway.ResponseStream()
        got = s.consume(b'{"type":"response.output_text.delta","delta":"partial"}')
        got += s.close()
        parsed = [json.loads(e) for e in got]
        self.assertEqual([e["type"] for e in parsed], ["text-delta", "error", "finish"])
        self.assertIn("terminal event", str(parsed[1].get("error") or ""))
        self.assertEqual(parsed[2]["finishReason"]["unified"], "error")

'''
t = replace_once(t, response_marker, response_insert + response_marker, "Responses EOF regression test")
TESTS.write_text(t, encoding="utf-8")
