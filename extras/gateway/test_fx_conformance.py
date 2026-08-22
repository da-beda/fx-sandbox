#!/usr/bin/env python3
"""Credential-free conformance test: real fx -> fxs gateway -> fake OpenAI /v1.

This intentionally exercises the public process boundary instead of importing fx
internals. It catches drift in fx's Gateway request/catalog/SSE contract while
keeping the fake upstream deterministic and offline.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gateway  # noqa: E402

MODEL = "fxs-conformance-model"
CHAT_MARKER = "FXS_CONFORMANCE_CHAT_OK"
RESPONSES_MARKER = "FXS_CONFORMANCE_RESPONSES_OK"


class FakeOpenAIHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *_args: Any) -> None:
        return

    @property
    def state(self) -> dict[str, Any]:
        return self.server.state  # type: ignore[attr-defined]

    def _json(self, code: int, value: Any) -> None:
        raw = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _sse(self, payload: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/models":
            self.state["models"] = self.state.get("models", 0) + 1
            self._json(200, {
                "object": "list",
                "data": [{
                    "id": MODEL,
                    "object": "model",
                    "context_window": 32768,
                    "max_tokens": 4096,
                }],
            })
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = None

        if self.path == "/v1/chat/completions":
            self.state.setdefault("chat", []).append(body)
            chunks = [
                {
                    "id": "chatcmpl-fxs",
                    "object": "chat.completion.chunk",
                    "choices": [{
                        "index": 0,
                        "delta": {"role": "assistant", "content": CHAT_MARKER},
                        "finish_reason": None,
                    }],
                },
                {
                    "id": "chatcmpl-fxs",
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            ]
            payload = b"".join(
                b"data: " + json.dumps(chunk, separators=(",", ":")).encode() + b"\n\n"
                for chunk in chunks
            ) + b"data: [DONE]\n\n"
            self._sse(payload)
            return

        if self.path == "/v1/responses":
            self.state.setdefault("responses", []).append(body)
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
                            "output": [],
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
            self._sse(payload)
            return

        self._json(404, {"error": "not found"})


class FakeOpenAIServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), FakeOpenAIHandler)
        self.state: dict[str, Any] = {}


class FxGatewayConformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = shutil.which("fx")
        if not cls.fx:
            raise RuntimeError("fx is required; install the current stable build before this test")
        version = subprocess.run(
            [cls.fx, "--version"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
        ).stdout.strip()
        print(f"conformance fx: {version}")

    def _run(self, api: str, marker: str, state_key: str) -> None:
        upstream = FakeOpenAIServer()
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()
        upstream_url = f"http://127.0.0.1:{upstream.server_port}/v1"

        adapter = gateway.GatewayServer(
            "127.0.0.1:0",
            gateway.Upstream(upstream_url, "local-test-key", api=api, provider_id="custom"),
        )
        adapter_thread = threading.Thread(target=adapter.serve_forever, daemon=True)
        adapter_thread.start()
        adapter_port = adapter.server_address[1]

        try:
            with tempfile.TemporaryDirectory(prefix="fxs-conformance-") as td:
                root = Path(td)
                home = root / "home"
                workspace = root / "workspace"
                home.mkdir()
                workspace.mkdir()
                (workspace / "README.md").write_text("fxs conformance fixture\n", encoding="utf-8")

                env = os.environ.copy()
                env.update({
                    "HOME": str(home),
                    "AI_GATEWAY_API_KEY": "local",
                    "FX_GATEWAY_BASE_URL": f"http://127.0.0.1:{adapter_port}",
                    "FX_GATEWAY_CHAT_URL": f"http://127.0.0.1:{adapter_port}/v3/ai/language-model",
                    "FX_MODEL": MODEL,
                })
                for key in (
                    "OPENAI_API_KEY",
                    "OPENAI_BASE_URL",
                    "FX_UPSTREAM",
                    "FX_PROVIDER",
                    "VERCEL_AI_GATEWAY_API_KEY",
                    "VERCEL_OIDC_TOKEN",
                ):
                    env.pop(key, None)

                proc = subprocess.run(
                    [
                        self.fx,
                        "ask",
                        "--json",
                        "--yolo",
                        "--no-save",
                        f"Reply with exactly {marker}. Do not call tools.",
                    ],
                    cwd=workspace,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=60,
                )
                combined = proc.stdout + "\n" + proc.stderr
                self.assertEqual(
                    proc.returncode,
                    0,
                    msg=f"fx failed in {api} mode\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
                )
                self.assertIn(marker, combined)

            calls = upstream.state.get(state_key) or []
            self.assertGreaterEqual(len(calls), 1, upstream.state)
            request = calls[-1]
            self.assertIsInstance(request, dict)
            self.assertEqual(request.get("model"), MODEL)
            if api == "chat":
                self.assertIsInstance(request.get("messages"), list)
            else:
                self.assertIsInstance(request.get("input"), list)
        finally:
            adapter.shutdown()
            adapter.server_close()
            upstream.shutdown()
            upstream.server_close()
            adapter_thread.join(timeout=2)
            upstream_thread.join(timeout=2)

    def test_current_fx_through_chat_completions_adapter(self) -> None:
        self._run("chat", CHAT_MARKER, "chat")

    def test_current_fx_through_responses_adapter(self) -> None:
        self._run("responses", RESPONSES_MARKER, "responses")


if __name__ == "__main__":
    unittest.main(verbosity=2)
