#!/usr/bin/env python3
from pathlib import Path

GATEWAY = Path("extras/gateway/gateway.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


g = GATEWAY.read_text(encoding="utf-8")
g = replace_once(
    g,
    "import stream_cancel\n",
    "import stream_cancel\nimport stream_limits\n",
    "stream limits import",
)

g = replace_once(
    g,
    '''class Stream:
    def __init__(self, allowed_tools: Optional[list[str]] = None) -> None:
        self.tools: dict[int, dict[str, Any]] = {}
        self.order: list[int] = []
        self.finished = False
        self.allowed_tools = list(allowed_tools or [])
''',
    '''class Stream:
    def __init__(
        self,
        allowed_tools: Optional[list[str]] = None,
        *,
        limits: Optional[stream_limits.StreamLimits] = None,
    ) -> None:
        self.tools: dict[Any, dict[str, Any]] = {}
        self.order: list[Any] = []
        self.finished = False
        self.allowed_tools = list(allowed_tools or [])
        self.limits = limits or stream_limits.DEFAULT_LIMITS
''',
    "Stream limits state",
)

g = replace_once(
    g,
    '''            if call.get("id"):
                acc["id"] = call["id"]
            elif not acc["id"]:
                acc["id"] = f"call_{idx}"
            fn = call.get("function") or {}
            if fn.get("name"):
                acc["name"] = canonical_tool_name(fn["name"], self.allowed_tools)
''',
    '''            if call.get("id"):
                acc["id"] = stream_limits.require_identity(
                    call["id"], self.limits, "tool call id"
                )
            elif not acc["id"]:
                acc["id"] = f"call_{idx}"
            fn = call.get("function") or {}
            if fn.get("name"):
                canonical = canonical_tool_name(fn["name"], self.allowed_tools)
                acc["name"] = stream_limits.require_identity(
                    canonical, self.limits, "tool name"
                )
''',
    "Chat tool identity limits",
)

g = replace_once(
    g,
    '''            args = fn.get("arguments") or ""
            if args:
                acc["args"] += args
                if acc["started"]:
''',
    '''            args = fn.get("arguments") or ""
            if args:
                stream_limits.append_arguments(acc, args, self.limits)
                if acc["started"]:
''',
    "Chat tool argument limit",
)

g = replace_once(
    g,
    '''    def _tool(self, index: int) -> dict[str, Any]:
        acc = self.tools.get(index)
        if acc is None:
            acc = {"id": "", "name": "", "args": "", "started": False}
            self.tools[index] = acc
            self.order.append(index)
        return acc
''',
    '''    def _tool(self, index: int) -> dict[str, Any]:
        acc = self.tools.get(index)
        if acc is None:
            stream_limits.reserve_tool(len(self.order), self.limits)
            acc = {
                "id": "",
                "name": "",
                "args": "",
                "_args_bytes": 0,
                "started": False,
            }
            self.tools[index] = acc
            self.order.append(index)
        return acc
''',
    "Chat tool count limit",
)

g = replace_once(
    g,
    '''    def __init__(self, allowed_tools: Optional[list[str]] = None) -> None:
        super().__init__(allowed_tools)
        self.ids: dict[str, str] = {}  # item_id → call_id
''',
    '''    def __init__(
        self,
        allowed_tools: Optional[list[str]] = None,
        *,
        limits: Optional[stream_limits.StreamLimits] = None,
    ) -> None:
        super().__init__(allowed_tools, limits=limits)
        self.ids: dict[str, str] = {}  # item_id → call_id
''',
    "Responses limits state",
)

g = replace_once(
    g,
    '''        if t == "response.function_call_arguments.delta":
            acc = self._acc_for(chunk)
            args = chunk.get("delta") or ""
            if args:
                acc["args"] += args
                if acc["started"]:
''',
    '''        if t == "response.function_call_arguments.delta":
            acc = self._acc_for(chunk)
            args = chunk.get("delta") or ""
            if args:
                stream_limits.append_arguments(acc, args, self.limits)
                if acc["started"]:
''',
    "Responses argument delta limit",
)

g = replace_once(
    g,
    '''        if t == "response.function_call_arguments.done":
            acc = self._acc_for(chunk)
            final = chunk.get("arguments")
            if isinstance(final, str) and final and not acc["args"]:
                acc["args"] = final
            return events
''',
    '''        if t == "response.function_call_arguments.done":
            acc = self._acc_for(chunk)
            final = chunk.get("arguments")
            if final and not acc["args"]:
                stream_limits.append_arguments(acc, final, self.limits)
            return events
''',
    "Responses final arguments limit",
)

start = g.index("    def _item_added(self, item: dict) -> list[bytes]:")
end = g.index("\n    def _item_done", start)
new_item_added = '''    def _item_added(self, item: dict) -> list[bytes]:
        if (item or {}).get("type") != "function_call":
            return []
        raw_call_id = item.get("call_id") or item.get("id") or ""
        raw_item_id = item.get("id") or ""
        call_id = (
            stream_limits.require_identity(raw_call_id, self.limits, "tool call id")
            if raw_call_id else ""
        )
        item_id = (
            stream_limits.require_identity(raw_item_id, self.limits, "provider item id")
            if raw_item_id else ""
        )
        if item_id and call_id:
            self.ids[item_id] = call_id
        acc = self._named(call_id or item_id)
        if call_id:
            acc["id"] = call_id
        if item.get("name"):
            canonical = canonical_tool_name(item["name"], self.allowed_tools)
            acc["name"] = stream_limits.require_identity(
                canonical, self.limits, "tool name"
            )
        if item.get("arguments"):
            stream_limits.append_arguments(acc, item["arguments"], self.limits)
        events: list[bytes] = []
        if not acc["started"] and acc["id"] and acc["name"]:
            acc["started"] = True
            events.append(_j({
                "type": "tool-input-start",
                "id": acc["id"],
                "toolName": acc["name"],
            }))
            if item.get("arguments"):
                events.append(_j({
                    "type": "tool-input-delta",
                    "id": acc["id"],
                    "delta": item["arguments"],
                }))
        return events
'''
g = g[:start] + new_item_added + g[end:]

g = replace_once(
    g,
    '''        if acc and acc.get("started"):
            if item.get("arguments") and not acc["args"]:
                acc["args"] = item["arguments"]
            return []
''',
    '''        if acc and acc.get("started"):
            if item.get("arguments") and not acc["args"]:
                stream_limits.append_arguments(acc, item["arguments"], self.limits)
            return []
''',
    "Responses item done limit",
)

start = g.index("    def _acc_for(self, chunk: dict) -> dict[str, Any]:")
end = g.index("\n\ndef _sse_payload", start)
new_tail = '''    def _acc_for(self, chunk: dict) -> dict[str, Any]:
        raw_item_id = chunk.get("item_id") or ""
        item_id = (
            stream_limits.require_identity(raw_item_id, self.limits, "provider item id")
            if raw_item_id else ""
        )
        raw_call_id = chunk.get("call_id") or self.ids.get(item_id) or item_id
        call_id = (
            stream_limits.require_identity(raw_call_id, self.limits, "tool call id")
            if raw_call_id else ""
        )
        if item_id and call_id:
            self.ids[item_id] = call_id
        return self._named(call_id)

    def _named(self, key: str) -> dict[str, Any]:
        key = key or f"anon{len(self.order)}"
        key = stream_limits.require_identity(key, self.limits, "tool call id")
        acc = self.tools.get(key)
        if acc is None:
            stream_limits.reserve_tool(len(self.order), self.limits)
            acc = {
                "id": key,
                "name": "",
                "args": "",
                "_args_bytes": 0,
                "started": False,
            }
            self.tools[key] = acc
            self.order.append(key)
        if not acc["id"]:
            acc["id"] = key
        return acc
'''
g = g[:start] + new_tail + g[end:]

start = g.index("def read_sse_data(resp) -> Iterable[str]:")
end = g.index("\n\ndef _j", start)
new_reader = '''def read_sse_data(
    resp,
    *,
    limits: Optional[stream_limits.StreamLimits] = None,
) -> Iterable[str]:
    """Yield bounded SSE payloads. Prefer JSON `type`; fall back to `event:`."""
    active = limits or stream_limits.DEFAULT_LIMITS
    buf: list[str] = []
    event = ""
    aggregate_bytes = 0
    event_count = 0

    def reserve_event() -> None:
        nonlocal event_count
        event_count += 1
        if event_count > active.sse_events:
            raise stream_limits.StreamLimitError(
                f"SSE event count exceeds local safety limit ({active.sse_events})"
            )

    while True:
        raw = resp.readline(active.sse_line_bytes + 1)
        if len(raw) > active.sse_line_bytes:
            raise stream_limits.StreamLimitError(
                f"SSE line exceeds local safety limit ({active.sse_line_bytes} bytes)"
            )
        aggregate_bytes = stream_limits.checked_total(
            aggregate_bytes,
            len(raw),
            active.sse_aggregate_bytes,
            "SSE aggregate",
        )
        if not raw:
            if buf:
                reserve_event()
                yield _sse_payload(event, buf)
            return
        line = raw.decode("utf-8", "replace").rstrip("\\r\\n")
        if line == "":
            if buf:
                reserve_event()
                yield _sse_payload(event, buf)
                buf = []
            event = ""
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[6:].strip()
            continue
        if line.startswith("data:"):
            buf.append(line[5:].lstrip())
'''
g = g[:start] + new_reader + g[end:]

GATEWAY.write_text(g, encoding="utf-8")
