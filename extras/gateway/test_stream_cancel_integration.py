#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gateway


class StreamCancellationIntegration(unittest.TestCase):
    def test_downstream_disconnect_aborts_hanging_upstream_stream(self):
        upstream_started = threading.Event()
        upstream_disconnected = threading.Event()

        class HangingUpstream(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                return

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                if self.path != "/v1/chat/completions":
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return

                payload = (
                    b'data: {"choices":[{"index":0,"delta":{"content":"partial"},'
                    b'"finish_reason":null}]}\n\n'
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
                self.wfile.flush()
                upstream_started.set()

                # The model intentionally never produces a terminal event. The
                # gateway-side cancellation watcher must close this connection
                # after the downstream fx socket disappears.
                self.connection.settimeout(3.0)
                try:
                    data = self.connection.recv(1)
                    if data == b"":
                        upstream_disconnected.set()
                except (ConnectionResetError, BrokenPipeError, OSError):
                    upstream_disconnected.set()

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), HangingUpstream)
        upstream.daemon_threads = True
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()

        adapter = gateway.GatewayServer(
            "127.0.0.1:0",
            gateway.Upstream(
                f"http://127.0.0.1:{upstream.server_address[1]}/v1",
                "probe-key",
                timeout=30,
                api="chat",
                provider_id="custom",
            ),
        )
        adapter_thread = threading.Thread(target=adapter.serve_forever, daemon=True)
        adapter_thread.start()

        downstream = socket.create_connection(adapter.server_address, timeout=2)
        try:
            body = json.dumps({
                "prompt": [{"role": "user", "content": "hello"}],
                "tools": [],
                "toolChoice": {"type": "auto"},
            }, separators=(",", ":")).encode()
            request = (
                b"POST /v3/ai/language-model HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Type: application/json\r\n"
                b"Accept: text/event-stream\r\n"
                b"ai-language-model-id: probe-model\r\n"
                b"ai-language-model-streaming: true\r\n"
                + f"Content-Length: {len(body)}\r\n".encode()
                + b"\r\n"
                + body
            )
            downstream.sendall(request)
            downstream.settimeout(2)

            received = b""
            while b"partial" not in received:
                chunk = downstream.recv(4096)
                self.assertTrue(chunk, "gateway closed before forwarding partial SSE")
                received += chunk
            self.assertTrue(upstream_started.wait(1), "upstream stream never started")

            # This is the fx-side cancellation signal. No provider timeout or
            # artificial model-idle deadline is involved.
            downstream.close()
            self.assertTrue(
                upstream_disconnected.wait(1.5),
                "upstream socket stayed open after downstream cancellation",
            )
        finally:
            try:
                downstream.close()
            except OSError:
                pass
            adapter.shutdown()
            upstream.shutdown()
            adapter.server_close()
            upstream.server_close()
            adapter_thread.join(timeout=1)
            upstream_thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
