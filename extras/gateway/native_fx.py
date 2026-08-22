#!/usr/bin/env python3
"""Probe installed fx capabilities without relying on version numbers.

The handoff decision is behavioral: when requested, run the installed fx against
an ephemeral loopback OpenAI-compatible server and observe whether it actually
uses Chat Completions and/or Responses successfully. No provider credentials or
external model traffic are involved.
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


@dataclass(frozen=True)
class NativeFxCapabilities:
    available: bool = False
    version: str = ""
    transport_probed: bool = False
    openai_compatible: bool = False
    openai_chat: bool = False
    openai_responses: bool = False
    evidence: tuple[str, ...] = ()

    def supports(self, api_style: str) -> bool:
        style = (api_style or "chat").strip().lower()
        if style == "responses":
            return self.openai_responses
        if style in ("chat", "completions", "chat-completions", "chat_completions"):
            return self.openai_chat
        return False

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["evidence"] = list(self.evidence)
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
        self.state.setdefault("paths", []).append(self.path)
        self.state.setdefault("bodies", []).append(raw.decode("utf-8", "replace"))

        if self.path == "/v1/chat/completions":
            chunks = [
                {
                    "id": "chatcmpl-fxs-native-probe",
                    "object": "chat.completion.chunk",
                    "choices": [{
                        "index": 0,
                        "delta": {"role": "assistant", "content": CHAT_MARKER},
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
            payload = b"".join(
                b"data: " + json.dumps(chunk, separators=(",", ":")).encode() + b"\n\n"
                for chunk in chunks
            ) + b"data: [DONE]\n\n"
            self._send(200, payload, "text/event-stream")
            return

        if self.path == "/v1/responses":
            events = [
                (
                    "response.output_text.delta",
                    {"type": "response.output_text.delta", "delta": RESPONSES_MARKER},
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
                                "content": [{"type": "output_text", "text": RESPONSES_MARKER}],
                            }],
                            "usage": {"input_tokens": 1, "output_tokens": 1},
                        },
                    },
                ),
            ]
            payload = b"".join(
                b"event: " + event.encode() + b"\n"
                + b"data: " + json.dumps(data, separators=(",", ":")).encode() + b"\n\n"
                for event, data in events
            ) + b"data: [DONE]\n\n"
            self._send(200, payload, "text/event-stream")
            return

        self._json(404, {"error": "not found"})


class _ProbeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _ProbeHandler)
        self.state: dict[str, Any] = {}


def _probe_transport(fx: str, api_style: str, timeout: int = 20) -> tuple[bool, str]:
    style = "responses" if api_style == "responses" else "chat"
    expected_path = "/v1/responses" if style == "responses" else "/v1/chat/completions"
    marker = RESPONSES_MARKER if style == "responses" else CHAT_MARKER

    server = _ProbeServer()
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

            env = os.environ.copy()
            for key in (
                "AI_GATEWAY_API_KEY",
                "VERCEL_AI_GATEWAY_API_KEY",
                "VERCEL_OIDC_TOKEN",
                "FX_GATEWAY_BASE_URL",
                "FX_GATEWAY_CHAT_URL",
                "FX_UPSTREAM",
                "OPENAI_BASE_URL",
                "OPENROUTER_API_KEY",
                "XAI_API_KEY",
            ):
                env.pop(key, None)
            env.update({
                "HOME": str(home),
                "OPENAI_API_KEY": "fxs-native-probe-key",
                "FX_OPENAI_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                "FX_OPENAI_API_STYLE": style,
                "FX_MODEL": PROBE_MODEL,
                # If an older fx ignores the OpenAI-compatible contract, keep
                # any legacy Gateway attempt local and fast instead of allowing
                # the capability probe to contact a real provider.
                "FX_GATEWAY_BASE_URL": "http://127.0.0.1:1",
                "FX_GATEWAY_CHAT_URL": "http://127.0.0.1:1/v3/ai/language-model",
            })
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
            return True, f"native OpenAI {style} loopback probe passed"
        reason = f"native OpenAI {style} loopback probe failed"
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

    chat, chat_evidence = _probe_transport(fx, "chat", timeout=timeout)
    responses, responses_evidence = _probe_transport(fx, "responses", timeout=timeout)
    evidence = tuple(
        item
        for supported, item in (
            (chat, chat_evidence),
            (responses, responses_evidence),
        )
        if supported
    )
    return NativeFxCapabilities(
        available=True,
        version=version,
        transport_probed=True,
        openai_compatible=chat or responses,
        openai_chat=chat,
        openai_responses=responses,
        evidence=evidence,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Probe installed fx provider capabilities")
    parser.add_argument("--fx", default="", help="path to fx binary (default: PATH)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--probe-transport",
        action="store_true",
        help="exercise Chat Completions and Responses against an ephemeral loopback server",
    )
    parser.add_argument("--timeout", type=int, default=20, help="per-transport probe timeout in seconds")
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
        print(f"responses: {'yes' if result.openai_responses else 'no'}")
        for item in result.evidence:
            print(f"- {item}")
    return 0 if result.available else 1


if __name__ == "__main__":
    raise SystemExit(main())
