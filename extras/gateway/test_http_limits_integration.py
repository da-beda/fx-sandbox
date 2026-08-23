#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gateway
import http_limits


class HttpBodyLimitIntegration(unittest.TestCase):
    def start_adapter(self, upstream: gateway.Upstream):
        server = gateway.GatewayServer("127.0.0.1:0", upstream)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def stop_adapter(self, server, thread):
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)

    def _declared_request_without_body(self, adapter, content_length: str):
        """Send headers only, then read the complete early-rejection response."""
        conn = http.client.HTTPConnection(
            adapter.server_address[0], adapter.server_address[1], timeout=3
        )
        try:
            conn.putrequest("POST", "/v3/ai/language-model")
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", content_length)
            conn.endheaders()
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_oversized_inbound_gateway_request_is_413_before_body_read(self):
        adapter, thread = self.start_adapter(
            gateway.Upstream("http://127.0.0.1:1/v1", "probe", timeout=1, api="chat")
        )
        try:
            status, body = self._declared_request_without_body(
                adapter, str(http_limits.GATEWAY_REQUEST_BYTES + 1)
            )
            self.assertEqual(status, 413)
            self.assertIn(b"local safety limit", body)
        finally:
            self.stop_adapter(adapter, thread)

    def test_negative_content_length_is_400_not_read_all(self):
        adapter, thread = self.start_adapter(
            gateway.Upstream("http://127.0.0.1:1/v1", "probe", timeout=1, api="chat")
        )
        try:
            status, body = self._declared_request_without_body(adapter, "-1")
            self.assertEqual(status, 400)
            self.assertIn(b"invalid Content-Length", body)
        finally:
            self.stop_adapter(adapter, thread)

    def _start_declared_upstream(self, *, status: int, declared_length: int):
        class DeclaredBody(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *_args):
                return

            def _reply(self):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(declared_length))
                self.end_headers()

            def do_GET(self):  # noqa: N802
                self._reply()

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                self._reply()

        server = ThreadingHTTPServer(("127.0.0.1", 0), DeclaredBody)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def _request_adapter(self, adapter, method: str, path: str, body=None, headers=None):
        conn = http.client.HTTPConnection(
            adapter.server_address[0], adapter.server_address[1], timeout=3
        )
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_declared_oversized_model_catalog_is_rejected_without_reading_body(self):
        upstream, upstream_thread = self._start_declared_upstream(
            status=200,
            declared_length=http_limits.MODEL_CATALOG_BYTES + 1,
        )
        adapter, adapter_thread = self.start_adapter(
            gateway.Upstream(
                f"http://127.0.0.1:{upstream.server_address[1]}/v1",
                "probe",
                timeout=3,
                api="chat",
            )
        )
        try:
            status, body = self._request_adapter(
                adapter, "GET", "/coding-agent/v1/models"
            )
            self.assertEqual(status, 502)
            self.assertIn(b"model catalog", body)
            self.assertIn(b"local safety limit", body)
        finally:
            self.stop_adapter(adapter, adapter_thread)
            upstream.shutdown()
            upstream.server_close()
            upstream_thread.join(timeout=1)

    def test_declared_oversized_nonstream_completion_is_rejected(self):
        upstream, upstream_thread = self._start_declared_upstream(
            status=200,
            declared_length=http_limits.NONSTREAM_COMPLETION_BYTES + 1,
        )
        adapter, adapter_thread = self.start_adapter(
            gateway.Upstream(
                f"http://127.0.0.1:{upstream.server_address[1]}/v1",
                "probe",
                timeout=3,
                api="chat",
            )
        )
        try:
            payload = json.dumps({
                "prompt": [{"role": "user", "content": "hello"}],
                "tools": [],
                "toolChoice": {"type": "auto"},
            }).encode()
            status, body = self._request_adapter(
                adapter,
                "POST",
                "/v3/ai/language-model",
                body=payload,
                headers={
                    "Content-Type": "application/json",
                    "ai-language-model-id": "probe-model",
                    "ai-language-model-streaming": "false",
                },
            )
            self.assertEqual(status, 502)
            self.assertIn(b"non-stream completion", body)
            self.assertIn(b"local safety limit", body)
        finally:
            self.stop_adapter(adapter, adapter_thread)
            upstream.shutdown()
            upstream.server_close()
            upstream_thread.join(timeout=1)

    def test_declared_oversized_provider_error_becomes_bounded_gateway_error(self):
        upstream, upstream_thread = self._start_declared_upstream(
            status=500,
            declared_length=http_limits.ERROR_BODY_BYTES + 1,
        )
        adapter, adapter_thread = self.start_adapter(
            gateway.Upstream(
                f"http://127.0.0.1:{upstream.server_address[1]}/v1",
                "probe",
                timeout=3,
                api="chat",
            )
        )
        try:
            payload = json.dumps({
                "prompt": [{"role": "user", "content": "hello"}],
                "tools": [],
                "toolChoice": {"type": "auto"},
            }).encode()
            status, body = self._request_adapter(
                adapter,
                "POST",
                "/v3/ai/language-model",
                body=payload,
                headers={
                    "Content-Type": "application/json",
                    "ai-language-model-id": "probe-model",
                    "ai-language-model-streaming": "false",
                },
            )
            self.assertEqual(status, 502)
            self.assertIn(b"upstream error body", body)
            self.assertIn(b"local safety limit", body)
        finally:
            self.stop_adapter(adapter, adapter_thread)
            upstream.shutdown()
            upstream.server_close()
            upstream_thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
