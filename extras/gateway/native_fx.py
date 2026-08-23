#!/usr/bin/env python3
"""Probe installed fx OpenAI-compatible capabilities without version guessing.

The handoff decision is behavioral. The installed fx is exercised against an
ephemeral loopback OpenAI-compatible server so transport and agentic tool flow
are proven rather than inferred from versions, help text, or unmerged PRs.

Two upstream configuration contracts are currently under active development:

* ``fx_openai`` — OPENAI_API_KEY + FX_OPENAI_BASE_URL + FX_OPENAI_API_STYLE
* ``custom_endpoint`` — FX_API_KEY + FX_BASE_URL (Chat Completions)

Each contract is tested independently. After a text transport succeeds, the
probe performs a second scenario that asks fx to execute its built-in read_file
tool and send the result back to the fake provider. No real provider credential
or external model traffic is involved.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

PROBE_MODEL = "fxs-native-probe-model"
CHAT_MARKER = "FXS_NATIVE_OPENAI_CHAT_OK"
RESPONSES_MARKER = "FXS_NATIVE_OPENAI_RESPONSES_OK"
CHAT_TOOL_MARKER = "FXS_NATIVE_OPENAI_CHAT_TOOL_OK"
RESPONSES_TOOL_MARKER = "FXS_NATIVE_OPENAI_RESPONSES_TOOL_OK"
TOOL_FILE_MARKER = "FXS_NATIVE_TOOL_FILE_OK"

CONTRACT_FX_OPENAI = "fx_openai"
CONTRACT_CUSTOM_ENDPOINT = "custom_endpoint"
CHAT_CONTRACTS = (CONTRACT_FX_OPENAI, CONTRACT_CUSTOM_ENDPOINT)
RESPONSES_CONTRACTS = (CONTRACT_FX_OPENAI,)


@dataclass(frozen=True)
class NativeFxCapabilities:
    available: bool = False
    version: str = ""
    transport_probed: bool = False
    openai_compatible: bool = False
    openai_chat: bool = False
    openai_responses: bool = False
    openai_chat_tools: bool = False
    openai_responses_tools: bool = False
    openai_chat_contracts: tuple[str, ...] = ()
    openai_responses_contracts: tuple[str, ...] = ()
    openai_chat_tool_contracts: tuple[str, ...] = ()
    openai_responses_tool_contracts: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def supports(self, api_style: str) -> bool:
        style = (api_style or "chat").strip().lower()
        if style == "responses":
            return self.openai_responses
        if style in ("chat", "completions", "chat-completions", "chat_completions"):
            return self.openai_chat
        return False

    def supports_tools(self, api_style: str) -> bool:
        style = (api_style or "chat").strip().lower()
        if style == "responses":
            return self.openai_responses_tools
        if style in ("chat", "completions", "chat-completions", "chat_completions"):
            return self.openai_chat_tools
        return False

    def contracts_for(self, api_style: str) -> tuple[str, ...]:
        style = (api_style or "chat").strip().lower()
        if style == "responses":
            return self.openai_responses_contracts
        if style in ("chat", "completions", "chat-completions", "chat_completions"):
            return self.openai_chat_contracts
        return ()

    def tool_contracts_for(self, api_style: str) -> tuple[str, ...]:
        style = (api_style or "chat").strip().lower()
        if style == "responses":
            return self.openai_responses_tool_contracts
        if style in ("chat", "completions", "chat-completions", "chat_completions"):
            return self.openai_chat_tool_contracts
        return ()

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        for key in (
            "openai_chat_contracts",
            "openai_responses_contracts",
            "openai_chat_tool_contracts",
            "openai_responses_tool_contracts",
            "evidence",
        ):
            out[key] = list(out[key])
        return out


def _run(argv: list[str], timeout: int = 8, **kwargs: Any) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
            **kwargs,
        )
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return proc.returncode, proc.stdout or ""


def _chat_text_payload(marker: str) -> bytes:
    chunks = [
        {
            "id": "chatcmpl-fxs-native-probe",
            "object": "chat.completion.chunk",
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": marker},
                "finish_reason": None,
            }],
        },
        {
            "id": "chatcmpl-fxs-native-probe",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
    ]
    return b"".join(
        b"data: " + json.dumps(chunk, separators=(",", ":")).encode() + b"\n\n"
        for chunk in chunks
    ) + b"data: [DONE]\n\n"


def _chat_tool_payload(path: str) -> bytes:
    chunk = {
        "id": "chatcmpl-fxs-native-tool",
        "object": "chat.completion.chunk",
        "choices": [{
            "index": 0,
            "delta": {
                "tool_calls": [{
                    "index": 0,
                    "id": "call_read",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"path": path}, separators=(",", ":")),
                    },
                }],
            },
            "finish_reason": "tool_calls",
        }],
    }
    return (
        b"data: " + json.dumps(chunk, separators=(",", ":")).encode()
        + b"\n\ndata: [DONE]\n\n"
    )


def _responses_text_payload(marker: str) -> bytes:
    events = [
        (
            "response.output_text.delta",
            {"type": "response.output_text.delta", "delta": marker},
        ),
        (
            "response.completed",
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "output": [{
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": marker}],
                    }],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            },
        ),
    ]
    return b"".join(
        b"event: " + event.encode() + b"\n"
        + b"data: " + json.dumps(data, separators=(",", ":")).encode() + b"\n\n"
        for event, data in events
    ) + b"data: [DONE]\n\n"


def _responses_tool_payload(path: str) -> bytes:
    arguments = json.dumps({"path": path}, separators=(",", ":"))
    events = [
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "type": "function_call",
                "call_id": "call_read",
                "name": "read_file",
                "arguments": "",
            },
        },
        {
            "type": "response.function_call_arguments.done",
            "output_index": 0,
            "name": "read_file",
            "arguments": arguments,
        },
        {
            "type": "response.completed",
            "response": {"status": "completed"},
        },
    ]
    return b"".join(
        b"event: " + str(event["type"]).encode() + b"\n"
        + b"data: " + json.dumps(event, separators=(",", ":")).encode() + b"\n\n"
        for event in events
    ) + b"data: [DONE]\n\n"


class _ProbeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *_args: Any) -> None:
        return

    @property
    def state(self) -> dict[str, Any]:
        return self.server.state  # type: ignore[attr-defined]

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, value: Any) -> None:
        self._send(code, json.dumps(value, separators=(",", ":")).encode(), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        self.state.setdefault("paths", []).append(self.path)
        if self.path == "/v1/models":
            self._json(200, {
                "object": "list",
                "data": [{"id": PROBE_MODEL, "object": "model"}],
            })
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        body = raw.decode("utf-8", "replace")
        self.state.setdefault("paths", []).append(self.path)
        self.state.setdefault("bodies", []).append(body)

        scenario = self.state.get("scenario") or "text"
        tool_path = str(self.state.get("tool_path") or "")

        if self.path == "/v1/chat/completions":
            count = int(self.state.get("chat_posts") or 0) + 1
            self.state["chat_posts"] = count
            if scenario == "tool" and count == 1:
                self._send(200, _chat_tool_payload(tool_path), "text/event-stream")
                return
            if scenario == "tool" and count == 2:
                seen = TOOL_FILE_MARKER in body
                self.state["tool_result_seen"] = seen
                if not seen:
                    self._json(400, {"error": "tool result marker missing"})
                    return
                self._send(200, _chat_text_payload(CHAT_TOOL_MARKER), "text/event-stream")
                return
            if scenario == "text" and count == 1:
                self._send(200, _chat_text_payload(CHAT_MARKER), "text/event-stream")
                return
            self._json(500, {"error": "unexpected chat probe request"})
            return

        if self.path == "/v1/responses":
            count = int(self.state.get("responses_posts") or 0) + 1
            self.state["responses_posts"] = count
            if scenario == "tool" and count == 1:
                self._send(200, _responses_tool_payload(tool_path), "text/event-stream")
                return
            if scenario == "tool" and count == 2:
                seen = TOOL_FILE_MARKER in body
                self.state["tool_result_seen"] = seen
                if not seen:
                    self._json(400, {"error": "tool result marker missing"})
                    return
                self._send(
                    200,
                    _responses_text_payload(RESPONSES_TOOL_MARKER),
                    "text/event-stream",
                )
                return
            if scenario == "text" and count == 1:
                self._send(200, _responses_text_payload(RESPONSES_MARKER), "text/event-stream")
                return
            self._json(500, {"error": "unexpected responses probe request"})
            return

        self._json(404, {"error": "not found"})


class _ProbeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *, scenario: str = "text", tool_path: str = "") -> None:
        super().__init__(("127.0.0.1", 0), _ProbeHandler)
        self.state: dict[str, Any] = {
            "scenario": scenario,
            "tool_path": tool_path,
            "tool_result_seen": False,
        }


def _clean_probe_environment() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "AI_GATEWAY_API_KEY",
        "VERCEL_AI_GATEWAY_API_KEY",
        "VERCEL_OIDC_TOKEN",
        "FX_GATEWAY_BASE_URL",
        "FX_GATEWAY_CHAT_URL",
        "FX_UPSTREAM",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "FX_OPENAI_BASE_URL",
        "FX_OPENAI_API_STYLE",
        "FX_BASE_URL",
        "FX_API_KEY",
        "OPENROUTER_API_KEY",
        "XAI_API_KEY",
        "FXS_NATIVE_PROBE_TOOL_FILE",
    ):
        env.pop(key, None)
    return env


def _apply_contract_environment(
    env: dict[str, str],
    contract: str,
    *,
    base_url: str,
    api_style: str,
) -> None:
    if contract == CONTRACT_FX_OPENAI:
        env.update({
            "OPENAI_API_KEY": "fxs-native-probe-key",
            "FX_OPENAI_BASE_URL": base_url,
            "FX_OPENAI_API_STYLE": api_style,
        })
        return
    if contract == CONTRACT_CUSTOM_ENDPOINT:
        if api_style != "chat":
            raise ValueError("custom_endpoint contract currently declares Chat only")
        env.update({
            "FX_API_KEY": "fxs-native-probe-key",
            "FX_BASE_URL": base_url,
        })
        return
    raise ValueError(f"unknown native fx probe contract: {contract}")


def _base_probe_environment(home: Path) -> dict[str, str]:
    env = _clean_probe_environment()
    env.update({
        "HOME": str(home),
        "FX_MODEL": PROBE_MODEL,
        "FX_SKIP_ONBOARDING": "1",
        # If an older fx ignores the tested OpenAI-compatible contract, keep
        # any legacy Gateway attempt local and fast instead of allowing the
        # capability probe to contact a real provider.
        "FX_GATEWAY_BASE_URL": "http://127.0.0.1:1",
        "FX_GATEWAY_CHAT_URL": "http://127.0.0.1:1/v3/ai/language-model",
    })
    return env


def _probe_transport(
    fx: str,
    api_style: str,
    contract: str,
    timeout: int = 20,
) -> tuple[bool, str]:
    style = "responses" if api_style == "responses" else "chat"
    if style == "responses" and contract not in RESPONSES_CONTRACTS:
        return False, f"{contract} does not declare a Responses wire"

    expected_path = "/v1/responses" if style == "responses" else "/v1/chat/completions"
    marker = RESPONSES_MARKER if style == "responses" else CHAT_MARKER

    server = _ProbeServer(scenario="text")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="fxs-native-probe-") as td:
            root = Path(td)
            home = root / "home"
            workspace = root / "workspace"
            home.mkdir()
            workspace.mkdir()
            (workspace / "README.md").write_text("fx native transport probe\n", encoding="utf-8")

            env = _base_probe_environment(home)
            _apply_contract_environment(
                env,
                contract,
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
                api_style=style,
            )
            rc, output = _run(
                [
                    fx,
                    "ask",
                    "--json",
                    "--yolo",
                    "--no-save",
                    f"Reply with exactly {marker}. Do not call tools.",
                ],
                timeout=timeout,
                cwd=workspace,
                env=env,
            )

        paths = list(server.state.get("paths") or [])
        reached = expected_path in paths
        parsed = marker in output
        if rc == 0 and reached and parsed:
            return True, f"native OpenAI {style} loopback probe passed via {contract}"
        reason = f"native OpenAI {style} loopback probe failed via {contract}"
        if reached and not parsed:
            reason += " (transport reached, response not accepted)"
        elif not reached:
            reason += " (transport not selected)"
        elif rc != 0:
            reason += f" (fx exit {rc})"
        return False, reason
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _probe_tool_roundtrip(
    fx: str,
    api_style: str,
    contract: str,
    timeout: int = 30,
) -> tuple[bool, str]:
    """Prove the native wire can execute read_file and replay its result."""
    style = "responses" if api_style == "responses" else "chat"
    if style == "responses" and contract not in RESPONSES_CONTRACTS:
        return False, f"{contract} does not declare a Responses wire"

    expected_path = "/v1/responses" if style == "responses" else "/v1/chat/completions"
    marker = RESPONSES_TOOL_MARKER if style == "responses" else CHAT_TOOL_MARKER

    with tempfile.TemporaryDirectory(prefix="fxs-native-tool-probe-") as td:
        root = Path(td)
        home = root / "home"
        workspace = root / "workspace"
        home.mkdir()
        workspace.mkdir()
        fixture = workspace / "fixture.txt"
        fixture.write_text(TOOL_FILE_MARKER + "\n", encoding="utf-8")

        server = _ProbeServer(scenario="tool", tool_path=str(fixture))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = _base_probe_environment(home)
            # Used only by deterministic synthetic fx fixtures in our unit
            # tests. Real fx ignores this variable and must execute read_file.
            env["FXS_NATIVE_PROBE_TOOL_FILE"] = str(fixture)
            _apply_contract_environment(
                env,
                contract,
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
                api_style=style,
            )
            rc, output = _run(
                [
                    fx,
                    "ask",
                    "--json",
                    "--yolo",
                    "--no-save",
                    f"Read {fixture} exactly once, then reply with exactly {marker}.",
                ],
                timeout=timeout,
                cwd=workspace,
                env=env,
            )

            paths = list(server.state.get("paths") or [])
            requests = sum(1 for path in paths if path == expected_path)
            replayed = bool(server.state.get("tool_result_seen"))
            parsed = marker in output
            if rc == 0 and requests >= 2 and replayed and parsed:
                return True, f"native OpenAI {style} tool round-trip passed via {contract}"
            reason = f"native OpenAI {style} tool round-trip failed via {contract}"
            if requests < 2:
                reason += " (no follow-up model request)"
            elif not replayed:
                reason += " (read_file result not replayed)"
            elif not parsed:
                reason += " (final response not accepted)"
            elif rc != 0:
                reason += f" (fx exit {rc})"
            return False, reason
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def probe_fx(
    path: Optional[str] = None,
    *,
    transport_probe: bool = False,
    timeout: int = 20,
) -> NativeFxCapabilities:
    fx = path or shutil.which("fx")
    if not fx:
        return NativeFxCapabilities()

    version_rc, version_out = _run([fx, "--version"])
    if version_rc != 0:
        return NativeFxCapabilities()
    version = " ".join(version_out.strip().split())
    if not transport_probe:
        return NativeFxCapabilities(available=True, version=version)

    chat_contracts: list[str] = []
    responses_contracts: list[str] = []
    chat_tool_contracts: list[str] = []
    responses_tool_contracts: list[str] = []
    evidence: list[str] = []

    for contract in CHAT_CONTRACTS:
        supported, detail = _probe_transport(fx, "chat", contract, timeout=timeout)
        if not supported:
            continue
        chat_contracts.append(contract)
        evidence.append(detail)
        tools, tool_detail = _probe_tool_roundtrip(
            fx,
            "chat",
            contract,
            timeout=max(timeout, 30),
        )
        if tools:
            chat_tool_contracts.append(contract)
            evidence.append(tool_detail)

    for contract in RESPONSES_CONTRACTS:
        supported, detail = _probe_transport(fx, "responses", contract, timeout=timeout)
        if not supported:
            continue
        responses_contracts.append(contract)
        evidence.append(detail)
        tools, tool_detail = _probe_tool_roundtrip(
            fx,
            "responses",
            contract,
            timeout=max(timeout, 30),
        )
        if tools:
            responses_tool_contracts.append(contract)
            evidence.append(tool_detail)

    return NativeFxCapabilities(
        available=True,
        version=version,
        transport_probed=True,
        openai_compatible=bool(chat_contracts or responses_contracts),
        openai_chat=bool(chat_contracts),
        openai_responses=bool(responses_contracts),
        openai_chat_tools=bool(chat_tool_contracts),
        openai_responses_tools=bool(responses_tool_contracts),
        openai_chat_contracts=tuple(chat_contracts),
        openai_responses_contracts=tuple(responses_contracts),
        openai_chat_tool_contracts=tuple(chat_tool_contracts),
        openai_responses_tool_contracts=tuple(responses_tool_contracts),
        evidence=tuple(evidence),
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Probe installed fx provider capabilities")
    parser.add_argument("--fx", default="", help="path to fx binary (default: PATH)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--probe-transport",
        action="store_true",
        help="exercise text and tool-flow behavior for known native OpenAI-compatible contracts",
    )
    parser.add_argument("--timeout", type=int, default=20, help="per-contract transport probe timeout in seconds")
    args = parser.parse_args(argv)

    result = probe_fx(
        args.fx or None,
        transport_probe=args.probe_transport,
        timeout=max(1, args.timeout),
    )
    if args.json:
        print(json.dumps(result.to_dict(), sort_keys=True))
    else:
        print(f"fx: {result.version or 'unavailable'}")
        print(f"transport probed: {'yes' if result.transport_probed else 'no'}")
        print(f"openai-compatible: {'yes' if result.openai_compatible else 'no'}")
        print(f"chat: {'yes' if result.openai_chat else 'no'}")
        print(f"chat contracts: {', '.join(result.openai_chat_contracts) or 'none'}")
        print(f"chat tools: {'yes' if result.openai_chat_tools else 'no'}")
        print(f"chat tool contracts: {', '.join(result.openai_chat_tool_contracts) or 'none'}")
        print(f"responses: {'yes' if result.openai_responses else 'no'}")
        print(f"responses contracts: {', '.join(result.openai_responses_contracts) or 'none'}")
        print(f"responses tools: {'yes' if result.openai_responses_tools else 'no'}")
        print(
            "responses tool contracts: "
            + (", ".join(result.openai_responses_tool_contracts) or "none")
        )
        for item in result.evidence:
            print(f"- {item}")
    return 0 if result.available else 1


if __name__ == "__main__":
    raise SystemExit(main())
