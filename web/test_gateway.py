#!/usr/bin/env python3
"""Stdlib tests for the Gateway → OpenAI translator. No network."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gateway


class Catalog(unittest.TestCase):
    def test_passes_ids_and_tags_tool_use(self):
        out = gateway.catalog(json.dumps({
            "object": "list",
            "data": [
                {"id": "glm-5.2", "object": "model"},
                {"id": "zai/glm-5.2", "context_window": 202752, "max_tokens": 8192},
                {"object": "model"},
                {"id": "gpt-oss:120b", "context_length": 128000},
            ],
        }).encode())
        parsed = json.loads(out)
        self.assertEqual(len(parsed["data"]), 3)
        self.assertEqual(parsed["data"][0]["id"], "glm-5.2")
        self.assertEqual(parsed["data"][0]["context_window"], 0)
        self.assertEqual(parsed["data"][1]["id"], "zai/glm-5.2")
        self.assertEqual(parsed["data"][1]["context_window"], 202752)
        self.assertEqual(parsed["data"][1]["max_tokens"], 8192)
        self.assertEqual(parsed["data"][2]["context_window"], 128000)
        for m in parsed["data"]:
            self.assertEqual(m["type"], "language")
            self.assertEqual(m["tags"], ["tool-use"])

    def test_invalid_json(self):
        with self.assertRaises(json.JSONDecodeError):
            gateway.catalog(b"[")


class ChatRequest(unittest.TestCase):
    def test_basic_prompt(self):
        req = gateway.chat_request("glm-5.2", True, json.dumps({
            "prompt": [
                {"role": "system", "content": "you are a tool"},
                {"role": "user", "content": [{"type": "text", "text": "hello"}]},
            ],
            "toolChoice": {"type": "auto"},
            "maxOutputTokens": 128,
        }).encode())
        self.assertEqual(req["model"], "glm-5.2")
        self.assertTrue(req["stream"])
        self.assertEqual(req["max_tokens"], 128)
        self.assertEqual(req["tool_choice"], "auto")
        self.assertEqual(len(req["messages"]), 2)
        self.assertEqual(req["messages"][0], {"role": "system", "content": "you are a tool"})
        self.assertEqual(req["messages"][1]["content"], "hello")

    def test_passes_model_through(self):
        for mid in ("glm-5.2", "zai/glm-5.2", "klia/custom", "gpt-oss:120b"):
            req = gateway.chat_request(mid, False, b'{"prompt":[{"role":"user","content":"hi"}]}')
            self.assertEqual(req["model"], mid)
            self.assertFalse(req["stream"])

    def test_tools_and_history(self):
        req = gateway.chat_request("m", False, json.dumps({
            "prompt": [
                {"role": "user", "content": [{"type": "text", "text": "list"}]},
                {"role": "assistant", "content": [
                    {"type": "text", "text": "ok"},
                    {"type": "tool-call", "toolCallId": "c1", "toolName": "bash",
                     "input": {"command": "ls"}},
                ]},
                {"role": "tool", "content": [
                    {"type": "tool-result", "toolCallId": "c1", "toolName": "bash",
                     "output": {"type": "text", "value": "a.txt"}},
                ]},
            ],
            "tools": [{"type": "function", "name": "bash", "description": "run",
                       "inputSchema": {"type": "object", "properties": {"command": {"type": "string"}}}}],
            "toolChoice": {"type": "required"},
        }).encode())
        self.assertEqual(req["tools"][0]["function"]["name"], "bash")
        self.assertEqual(req["tool_choice"], "required")
        self.assertEqual(len(req["messages"]), 3)
        asst = req["messages"][1]
        self.assertEqual(asst["content"], "ok")
        self.assertEqual(asst["tool_calls"][0]["id"], "c1")
        self.assertEqual(asst["tool_calls"][0]["function"]["arguments"], '{"command":"ls"}')
        tool = req["messages"][2]
        self.assertEqual(tool["role"], "tool")
        self.assertEqual(tool["tool_call_id"], "c1")
        self.assertEqual(tool["content"], "a.txt")

    def test_drops_images_keeps_text(self):
        req = gateway.chat_request("m", False, json.dumps({
            "prompt": [{"role": "user", "content": [
                {"type": "text", "text": "what is this"},
                {"type": "file", "data": "..."},
            ]}],
        }).encode())
        self.assertEqual(req["messages"][0]["content"], "what is this")

    def test_image_only_fails(self):
        with self.assertRaises(gateway.TranslateError) as cm:
            gateway.chat_request("m", False, json.dumps({
                "prompt": [{"role": "user", "content": [
                    {"type": "file", "mediaType": "image/png"},
                ]}],
            }).encode())
        self.assertEqual(cm.exception.code, gateway.ERR_IMAGE_ONLY)

    def test_missing_model(self):
        with self.assertRaises(gateway.TranslateError) as cm:
            gateway.chat_request("  ", False, b'{"prompt":[]}')
        self.assertEqual(cm.exception.code, gateway.ERR_MISSING_MODEL)

    def test_invalid_json(self):
        with self.assertRaises(gateway.TranslateError) as cm:
            gateway.chat_request("m", False, b"{")
        self.assertEqual(cm.exception.code, gateway.ERR_INVALID_BODY)

    def test_tool_choice_none_and_string(self):
        req = gateway.chat_request("m", False, b'{"prompt":[],"toolChoice":{"type":"none"}}')
        self.assertEqual(req["tool_choice"], "none")
        req = gateway.chat_request("m", False, b'{"prompt":[],"toolChoice":"auto"}')
        self.assertEqual(req["tool_choice"], "auto")

    def test_named_tool_choice_ignored(self):
        req = gateway.chat_request("m", False, json.dumps({
            "prompt": [], "toolChoice": {"type": "tool", "toolName": "bash"},
        }).encode())
        self.assertNotIn("tool_choice", req)

    def test_ignores_provider_options(self):
        req = gateway.chat_request("m", False, json.dumps({
            "prompt": [{"role": "user", "content": "hi"}],
            "providerOptions": {"gateway": {"speed": "fast"}},
            "reasoning": "high",
            "headers": {"user-agent": "fx"},
        }).encode())
        self.assertEqual(req["messages"][0]["content"], "hi")


class SSE(unittest.TestCase):
    def test_text_and_stop(self):
        s = gateway.Stream()
        got = []
        got += s.consume(b'{"choices":[{"delta":{"content":"Hel"}}]}')
        got += s.consume(b'{"choices":[{"delta":{"content":"lo"},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":2}}')
        self.assertEqual(s.close(), [])
        types = [json.loads(e)["type"] for e in got]
        self.assertEqual(types, ["text-delta", "text-delta", "finish"])
        self.assertEqual(json.loads(got[0])["delta"], "Hel")
        self.assertEqual(json.loads(got[2])["finishReason"]["unified"], "stop")
        self.assertEqual(json.loads(got[2])["usage"]["inputTokens"]["total"], 3)

    def test_tool_call_fragments(self):
        s = gateway.Stream()
        chunks = [
            '{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"bash","arguments":""}}]}}]}',
            '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"co"}}]}}]}',
            '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"mmand\\":\\"ls\\"}"}}]}}]}',
            '{"choices":[{"delta":{},"finish_reason":"tool_calls"}]}',
        ]
        got = []
        for c in chunks:
            got += s.consume(c)
        types = [json.loads(e)["type"] for e in got]
        self.assertEqual(types, [
            "tool-input-start", "tool-input-delta", "tool-input-delta",
            "tool-input-end", "tool-call", "finish",
        ])
        self.assertEqual(json.loads(got[0])["id"], "c1")
        call = json.loads(got[4])
        self.assertEqual(call["toolCallId"], "c1")
        self.assertEqual(call["input"], {"command": "ls"})
        self.assertEqual(json.loads(got[5])["finishReason"]["unified"], "tool-calls")

    def test_reasoning_delta(self):
        s = gateway.Stream()
        got = s.consume(b'{"choices":[{"delta":{"reasoning_content":"hmm"}}]}')
        self.assertEqual(got, [])

    def test_web_search_alias(self):
        s = gateway.Stream(allowed_tools=["perplexity_search", "web_fetch"])
        got = s.consume(json.dumps({
            "choices": [{"delta": {"tool_calls": [{
                "index": 0, "id": "c1",
                "function": {"name": "web_search", "arguments": '{"query":"example domain"}'},
            }]}}],
        }))
        got += s.consume(b'{"choices":[{"finish_reason":"tool_calls"}]}')
        start = json.loads(got[0])
        self.assertEqual(start["type"], "tool-input-start")
        self.assertEqual(start["toolName"], "perplexity_search")
        call = next(json.loads(e) for e in got if json.loads(e)["type"] == "tool-call")
        self.assertEqual(call["toolName"], "perplexity_search")
        self.assertEqual(call["input"], {"query": "example domain"})
        self.assertEqual(s.search_calls()[0]["name"], "perplexity_search")

    def test_canonical_tool_name(self):
        self.assertEqual(
            gateway.canonical_tool_name("web_search", ["perplexity_search", "web_fetch"]),
            "perplexity_search",
        )
        self.assertEqual(
            gateway.canonical_tool_name("web_fetch", ["perplexity_search", "web_fetch"]),
            "web_fetch",
        )
        self.assertEqual(
            gateway.canonical_tool_name("perplexity_search", ["perplexity_search", "web_fetch"]),
            "perplexity_search",
        )
        self.assertEqual(gateway.canonical_tool_name("bash", ["terminal"]), "terminal")
        self.assertNotEqual(
            gateway.canonical_tool_name("web_search", ["perplexity_search", "web_fetch"]),
            "web_fetch",
        )
        self.assertEqual(gateway.canonical_tool_name("list", ["list_files"]), "list_files")

    def test_mark_search_events_drops_search(self):
        events = [
            gateway._j({
                "type": "tool-input-start",
                "id": "s1",
                "toolName": "perplexity_search",
            }),
            gateway._j({"type": "tool-input-delta", "id": "s1", "delta": '{"query":"q"}'}),
            gateway._j({"type": "tool-input-end", "id": "s1"}),
            gateway._j({
                "type": "tool-call",
                "toolCallId": "s1",
                "toolName": "perplexity_search",
                "input": {"query": "hello world"},
            }),
            gateway._j({"type": "text-delta", "delta": "ok"}),
            gateway._j({"type": "finish", "finishReason": {"unified": "tool-calls"}}),
        ]
        out = [json.loads(e) for e in gateway.mark_search_events(events, {"s1"})]
        self.assertEqual([e["type"] for e in out], ["text-delta"])
        self.assertEqual(out[0]["delta"], "ok")

    def test_search_is_not_remapped_to_web_fetch(self):
        s = gateway.Stream(allowed_tools=["perplexity_search", "web_fetch"])
        got = s.consume(json.dumps({
            "choices": [{"delta": {"tool_calls": [{
                "index": 0, "id": "c1",
                "function": {"name": "perplexity_search", "arguments": '{"query":"latest rust"}'},
            }]}}],
        }))
        got += s.consume(b'{"choices":[{"finish_reason":"tool_calls"}]}')
        call = next(json.loads(e) for e in got if json.loads(e)["type"] == "tool-call")
        self.assertEqual(call["toolName"], "perplexity_search")
        self.assertEqual(call["input"], {"query": "latest rust"})
        self.assertNotIn("url", call["input"])

    def test_fail_emits_error_finish(self):
        s = gateway.Stream()
        got = s.fail("boom")
        types = [json.loads(e)["type"] for e in got]
        self.assertEqual(types, ["error", "finish"])
        self.assertEqual(json.loads(got[1])["finishReason"]["unified"], "error")

    def test_parallel_tools(self):
        s = gateway.Stream()
        got = s.consume(b'{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"a","function":{"name":"one","arguments":"{}"}},{"index":1,"id":"b","function":{"name":"two","arguments":"{}"}}]}}]}')
        got += s.consume(b'{"choices":[{"finish_reason":"tool_calls"}]}')
        ids = [json.loads(e)["toolCallId"] for e in got if json.loads(e)["type"] == "tool-call"]
        self.assertEqual(ids, ["a", "b"])

    def test_invalid_tool_json(self):
        s = gateway.Stream()
        got = s.consume(b'{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"bash","arguments":"{]"}}]}}]}')
        got += s.consume(b'{"choices":[{"finish_reason":"tool_calls"}]}')
        types = [json.loads(e)["type"] for e in got]
        self.assertIn("error", types)
        self.assertNotIn("tool-call", types)

    def test_finish_reasons(self):
        self.assertEqual(gateway.unified_finish("content_filter"), "content-filter")
        self.assertEqual(gateway.unified_finish("mystery"), "other")


class Loopback(unittest.TestCase):
    def test_accepts_loopback(self):
        gateway.require_loopback("127.0.0.1:18787")
        gateway.require_loopback("localhost:9")

    def test_rejects_lan(self):
        with self.assertRaises(ValueError):
            gateway.require_loopback("0.0.0.0:18787")
        with self.assertRaises(ValueError):
            gateway.require_loopback("192.168.1.4:80")


class Provider(unittest.TestCase):
    def test_presets(self):
        self.assertEqual(gateway.resolve_provider("xai")["url"], "https://api.x.ai/v1")
        self.assertEqual(gateway.resolve_provider("grok")["id"], "xai")
        self.assertEqual(gateway.resolve_provider("vercel")["url"], "")
        self.assertEqual(gateway.resolve_provider("together")["id"], "together")
        self.assertEqual(gateway.resolve_provider("https://example.com/v1")["id"], "custom")
        self.assertEqual(gateway.resolve_provider("https://example.com")["url"], "https://example.com/v1")

    def test_unknown(self):
        with self.assertRaises(ValueError):
            gateway.resolve_provider("nope")

    def test_host_rewrite(self):
        self.assertEqual(
            gateway.host_gateway_rewrite("http://127.0.0.1:11434/v1"),
            "http://host.docker.internal:11434/v1",
        )
        self.assertEqual(
            gateway.host_gateway_rewrite("https://api.x.ai/v1"),
            "https://api.x.ai/v1",
        )

    def test_suggest_model(self):
        self.assertEqual(gateway.suggest_model("xai", "zai/glm-5.2"), "grok-4")
        self.assertEqual(gateway.suggest_model("openai", ""), "gpt-4o")
        self.assertEqual(gateway.suggest_model("vercel", "grok-4"), "zai/glm-5.2")
        self.assertEqual(gateway.suggest_model("vercel", "anthropic/claude-sonnet-4.6"), "anthropic/claude-sonnet-4.6")
        self.assertEqual(
            gateway.suggest_model("xai", "zai/glm-5.2", ["grok-3", "grok-4"]),
            "grok-4",
        )
        self.assertEqual(
            gateway.suggest_model("ollama", "zai/glm-5.2", ["llama3.2", "mistral"]),
            "llama3.2",
        )
        self.assertEqual(
            gateway.suggest_model("xai", "grok-3", ["grok-3", "grok-4"]),
            "grok-3",
        )
        ids = [
            "openai/gpt-4o",
            "stealth/ox-alpha",
            "z-ai/glm-5.2:free",
            "openrouter/free",
        ]
        self.assertEqual(
            gateway.suggest_model("openrouter", "zai/glm-5.2", ids),
            "z-ai/glm-5.2:free",
        )
        self.assertEqual(
            gateway.suggest_model("openrouter", "", ids),
            "stealth/ox-alpha",
        )
        self.assertEqual(
            gateway.suggest_model("openrouter", "stealth/ox-alpha", ids),
            "stealth/ox-alpha",
        )
        self.assertTrue(gateway.is_free_model("stealth/ox-alpha"))
        self.assertTrue(gateway.is_free_model("openrouter/free"))
        self.assertTrue(gateway.is_free_model("z-ai/glm-5.2:free"))
        self.assertFalse(gateway.is_free_model("openai/gpt-4o"))
        self.assertEqual(gateway.model_label("stealth/ox-alpha"), "ox-alpha (free)")
        self.assertEqual(gateway.model_label("z-ai/glm-5.2:free"), "glm-5.2 (free)")

    def test_needs_key(self):
        self.assertTrue(gateway.provider_needs_key("xai"))
        self.assertFalse(gateway.provider_needs_key("ollama"))
        self.assertFalse(gateway.provider_needs_key("vercel"))


class EnvFile(unittest.TestCase):
    def test_upsert_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "env"
            gateway.upsert_env({"FX_UPSTREAM": "https://api.x.ai/v1", "OPENAI_API_KEY": "xai-secret"}, p)
            got = gateway.parse_env_file(p)
            self.assertEqual(got["FX_UPSTREAM"], "https://api.x.ai/v1")
            self.assertEqual(got["OPENAI_API_KEY"], "xai-secret")
            mode = oct(p.stat().st_mode & 0o777)
            self.assertEqual(mode, "0o600")
            gateway.upsert_env({"FX_UPSTREAM": None, "FX_MODEL": "grok-4"}, p)
            got = gateway.parse_env_file(p)
            self.assertNotIn("FX_UPSTREAM", got)
            self.assertEqual(got["FX_MODEL"], "grok-4")
            self.assertEqual(got["OPENAI_API_KEY"], "xai-secret")


class HTTP(unittest.TestCase):
    def setUp(self):
        self.saw_auth = ""
        self.saw_path = ""
        self.got_body = None
        self.mode = "models"

        class Up(BaseHTTPRequestHandler):
            parent = self

            def log_message(self, *a):
                return

            def do_GET(self):
                self.parent.saw_path = self.path
                self.parent.saw_auth = self.headers.get("Authorization") or ""
                body = b'{"data":[{"id":"glm-5.2"},{"id":"zai/glm-5.2"}]}'
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_POST(self):
                self.parent.saw_path = self.path
                self.parent.saw_auth = self.headers.get("Authorization") or ""
                n = int(self.headers.get("Content-Length") or 0)
                self.parent.got_body = json.loads(self.rfile.read(n) or b"{}")
                payload = (
                    b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
                    b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                    b'data: [DONE]\n\n'
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.up = ThreadingHTTPServer(("127.0.0.1", 0), Up)
        self.up_thread = threading.Thread(target=self.up.serve_forever, daemon=True)
        self.up_thread.start()
        up_port = self.up.server_address[1]
        self.gw = gateway.GatewayServer(
            f"127.0.0.1:0",
            gateway.Upstream(f"http://127.0.0.1:{up_port}/v1", "upstream-secret"),
        )
        # bind 0 then rewrite listen
        self.gw_thread = threading.Thread(target=self.gw.serve_forever, daemon=True)
        self.gw_thread.start()
        self.base = f"http://127.0.0.1:{self.gw.server_address[1]}"

    def tearDown(self):
        self.gw.shutdown()
        self.up.shutdown()
        self.gw.server_close()
        self.up.server_close()
        self.gw_thread.join(timeout=1)
        self.up_thread.join(timeout=1)

    def test_healthz_and_credits(self):
        r = urlopen(self.base + "/healthz", timeout=2)
        self.assertEqual(r.status, 200)
        self.assertEqual(r.read().strip(), b"ok")
        try:
            urlopen(self.base + "/coding-agent/v1/credits", timeout=2)
            self.fail("expected 404")
        except HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_models_rewrites_and_strips_fx_key(self):
        req = Request(self.base + "/coding-agent/v1/models")
        req.add_header("Authorization", "Bearer fx-dummy")
        r = urlopen(req, timeout=2)
        cat = json.loads(r.read())
        self.assertEqual(self.saw_auth, "Bearer upstream-secret")
        self.assertEqual(self.saw_path, "/v1/models")
        self.assertEqual([m["id"] for m in cat["data"]], ["glm-5.2", "zai/glm-5.2"])
        self.assertEqual(cat["data"][0]["tags"], ["tool-use"])

    def test_language_model_missing_header(self):
        req = Request(self.base + "/v3/ai/language-model", data=b'{"prompt":[]}', method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            urlopen(req, timeout=2)
            self.fail("expected 400")
        except HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_language_model_stream(self):
        body = json.dumps({"prompt": [{"role": "user", "content": "hi"}]}).encode()
        req = Request(self.base + "/v3/ai/language-model", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("ai-language-model-id", "glm-5.2")
        req.add_header("ai-language-model-streaming", "true")
        r = urlopen(req, timeout=2)
        text = r.read().decode()
        self.assertEqual(self.saw_auth, "Bearer upstream-secret")
        self.assertEqual(self.saw_path, "/v1/chat/completions")
        self.assertEqual(self.got_body["model"], "glm-5.2")
        self.assertTrue(self.got_body["stream"])
        self.assertIn("text-delta", text)
        self.assertIn("Hi", text)
        self.assertIn("finish", text)
        self.assertNotIn("choices", text)

    def test_language_model_nonstream(self):
        # Swap the upstream POST to JSON for this call.
        class OneShot(BaseHTTPRequestHandler):
            parent = self

            def log_message(self, *a):
                return

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(n)
                body = b'{"choices":[{"finish_reason":"stop","message":{"content":"pong"}}]}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self.send_response(404)
                self.end_headers()

        up = ThreadingHTTPServer(("127.0.0.1", 0), OneShot)
        t = threading.Thread(target=up.serve_forever, daemon=True)
        t.start()
        gw = gateway.GatewayServer(
            "127.0.0.1:0",
            gateway.Upstream(f"http://127.0.0.1:{up.server_address[1]}/v1", "k"),
        )
        gt = threading.Thread(target=gw.serve_forever, daemon=True)
        gt.start()
        try:
            body = json.dumps({"prompt": [{"role": "user", "content": "ping"}]}).encode()
            req = Request(
                f"http://127.0.0.1:{gw.server_address[1]}/v3/ai/language-model",
                data=body, method="POST",
            )
            req.add_header("Content-Type", "application/json")
            req.add_header("ai-language-model-id", "any/id")
            req.add_header("ai-language-model-streaming", "false")
            r = urlopen(req, timeout=2)
            self.assertIn(b"pong", r.read())
        finally:
            gw.shutdown(); up.shutdown()
            gw.server_close(); up.server_close()

    def test_upstream_401_forwarded(self):
        class Nope(BaseHTTPRequestHandler):
            def log_message(self, *a):
                return

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(n)
                body = b'{"error":{"message":"bad key"}}'
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self.send_response(404)
                self.end_headers()

        up = ThreadingHTTPServer(("127.0.0.1", 0), Nope)
        t = threading.Thread(target=up.serve_forever, daemon=True)
        t.start()
        gw = gateway.GatewayServer(
            "127.0.0.1:0",
            gateway.Upstream(f"http://127.0.0.1:{up.server_address[1]}/v1", "nope"),
        )
        gt = threading.Thread(target=gw.serve_forever, daemon=True)
        gt.start()
        try:
            body = json.dumps({"prompt": [{"role": "user", "content": "x"}]}).encode()
            req = Request(
                f"http://127.0.0.1:{gw.server_address[1]}/v3/ai/language-model",
                data=body, method="POST",
            )
            req.add_header("Content-Type", "application/json")
            req.add_header("ai-language-model-id", "m")
            req.add_header("ai-language-model-streaming", "true")
            r = urlopen(req, timeout=2)
            body = r.read()
            self.assertIn(b'"type":"error"', body)
            self.assertIn(b"Provider rejected the API key", body)
            self.assertIn(b"bad key", body)
        finally:
            gw.shutdown(); up.shutdown()
            gw.server_close(); up.server_close()

    def test_language_model_executes_search_and_continues(self):
        prev_keys = {}
        for k in (
            "PERPLEXITY_API_KEY", "VERCEL_AI_GATEWAY_API_KEY",
            "OPENROUTER_API_KEY", "OPENAI_API_KEY",
        ):
            prev_keys[k] = os.environ.get(k)
            os.environ[k] = ""
        prev_gw = os.environ.get("AI_GATEWAY_API_KEY")
        if (prev_gw or "").startswith("vck_"):
            os.environ["AI_GATEWAY_API_KEY"] = ""
        else:
            prev_gw = None
        posts: list[dict] = []

        class SearchUp(BaseHTTPRequestHandler):
            def log_message(self, *a):
                return

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                posts.append(body)
                if len(posts) == 1:
                    payload = (
                        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"s1","function":{"name":"web_search","arguments":"{\\"query\\":\\"hello world\\"}"}}]}}]}\n\n'
                        b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
                        b'data: [DONE]\n\n'
                    )
                else:
                    payload = (
                        b'data: {"choices":[{"delta":{"content":"no key yet"}}]}\n\n'
                        b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                        b'data: [DONE]\n\n'
                    )
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                self.send_response(404)
                self.end_headers()

        up = ThreadingHTTPServer(("127.0.0.1", 0), SearchUp)
        t = threading.Thread(target=up.serve_forever, daemon=True)
        t.start()
        gw = gateway.GatewayServer(
            "127.0.0.1:0",
            gateway.Upstream(f"http://127.0.0.1:{up.server_address[1]}/v1", "k"),
        )
        gt = threading.Thread(target=gw.serve_forever, daemon=True)
        gt.start()
        try:
            body = json.dumps({
                "prompt": [{"role": "user", "content": "search please"}],
                "tools": [{
                    "type": "function",
                    "name": "perplexity_search",
                    "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
                }, {
                    "type": "function",
                    "name": "web_fetch",
                    "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}},
                }],
            }).encode()
            req = Request(
                f"http://127.0.0.1:{gw.server_address[1]}/v3/ai/language-model",
                data=body, method="POST",
            )
            req.add_header("Content-Type", "application/json")
            req.add_header("ai-language-model-id", "m")
            req.add_header("ai-language-model-streaming", "true")
            r = urlopen(req, timeout=4)
            text = r.read().decode()
            self.assertIn("no key yet", text)
            self.assertNotIn("web_fetch", text)
            self.assertNotIn("providerExecuted", text)
            self.assertNotIn('"toolName":"perplexity_search"', text)
            self.assertEqual(len(posts), 2)
            roles = [m.get("role") for m in posts[1].get("messages") or []]
            self.assertIn("tool", roles)
            tool_msg = next(m for m in posts[1]["messages"] if m.get("role") == "tool")
            self.assertIn("Perplexity API key", tool_msg.get("content") or "")
            # OpenRouter sees a query field even if fx advertised an empty schema.
            tools = posts[0].get("tools") or []
            fn = tools[0]["function"]
            self.assertEqual(fn["name"], "perplexity_search")
            self.assertIn("query", (fn.get("parameters") or {}).get("properties") or {})
        finally:
            gw.shutdown(); up.shutdown()
            gw.server_close(); up.server_close()
            for k, v in prev_keys.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            if prev_gw is not None:
                os.environ["AI_GATEWAY_API_KEY"] = prev_gw


class IsolatedApply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.prev_paths = {
            "ENV_FILE": gateway.ENV_FILE,
            "STATE_DIR": gateway.STATE_DIR,
            "PID_FILE": gateway.PID_FILE,
            "LOG_FILE": gateway.LOG_FILE,
            "UPSTREAM_STAMP": gateway.UPSTREAM_STAMP,
        }
        gateway.ENV_FILE = d / "env"
        gateway.STATE_DIR = d / "state"
        gateway.PID_FILE = d / "state" / "gateway.pid"
        gateway.LOG_FILE = d / "state" / "gateway.log"
        gateway.UPSTREAM_STAMP = d / "state" / "gateway.upstream"
        self.prev_env = {}
        for k in (
            "FX_UPSTREAM", "OPENAI_BASE_URL", "OPENAI_API_KEY", "FX_MODEL",
            "AI_GATEWAY_API_KEY", "FXS_UI_LOCAL", "OLLAMA_API_KEY",
            "XAI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY",
            "FX_GATEWAY_BASE_URL",
            "FX_GATEWAY_CHAT_URL", "FX_UPSTREAM_API",
            "PERPLEXITY_API_KEY", "VERCEL_AI_GATEWAY_API_KEY",
        ):
            self.prev_env[k] = os.environ.pop(k, None)
        os.environ["FXS_UI_LOCAL"] = "1"

    def tearDown(self):
        for k, v in self.prev_paths.items():
            setattr(gateway, k, v)
        for k, v in self.prev_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        try:
            gateway.stop_gateway()
        except Exception:
            pass
        self.tmp.cleanup()

    def test_apply_xai_picks_grok_and_writes_env(self):
        out = gateway.apply_provider("xai")
        self.assertEqual(out["id"], "xai")
        self.assertEqual(out["url"], "https://api.x.ai/v1")
        self.assertEqual(out["model"], "grok-4")
        self.assertTrue(out["needs_key"])
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["FX_UPSTREAM"], "https://api.x.ai/v1")
        self.assertEqual(saved["FX_MODEL"], "grok-4")
        self.assertEqual(saved["AI_GATEWAY_API_KEY"], "local")
        self.assertEqual(out["api"], "auto")
        self.assertEqual(out["effective_api"], "responses")

    def test_apply_xai_api_chat(self):
        out = gateway.apply_provider("xai", api="chat")
        self.assertEqual(out["api"], "chat")
        self.assertEqual(out["effective_api"], "chat")
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["FX_UPSTREAM_API"], "chat")

    def test_apply_vercel_clears_upstream(self):
        gateway.apply_provider("xai")
        out = gateway.apply_provider("vercel")
        self.assertTrue(out["vercel"])
        self.assertFalse(out["url"])
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertNotIn("FX_UPSTREAM", saved)
        self.assertNotIn("FX_UPSTREAM_API", saved)
        self.assertEqual(saved["FX_MODEL"], "zai/glm-5.2")

    def test_apply_custom_url_appends_v1(self):
        out = gateway.apply_provider("https://example.com")
        self.assertEqual(out["id"], "custom")
        self.assertEqual(out["url"], "https://example.com/v1")

    def test_apply_keeps_explicit_model(self):
        out = gateway.apply_provider("xai", "grok-3")
        self.assertEqual(out["model"], "grok-3")

    def test_store_openai_key(self):
        gateway.apply_provider("xai")
        out = gateway.store_api_key("xai-secret")
        self.assertTrue(out["key"])
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["OPENAI_API_KEY"], "xai-secret")
        self.assertEqual(saved["FX_UPSTREAM"], "https://api.x.ai/v1")

    def test_store_vck_clears_upstream(self):
        gateway.apply_provider("xai")
        gateway.store_api_key("xai-secret")
        out = gateway.store_api_key("vck_abc")
        self.assertTrue(out["vercel"])
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["AI_GATEWAY_API_KEY"], "vck_abc")
        self.assertNotIn("OPENAI_API_KEY", saved)
        self.assertNotIn("FX_UPSTREAM", saved)

    def test_print_env(self):
        text = gateway.print_env("127.0.0.1:18787")
        self.assertIn("export FX_GATEWAY_BASE_URL=http://127.0.0.1:18787", text)
        self.assertIn("export FX_GATEWAY_CHAT_URL=http://127.0.0.1:18787/v3/ai/language-model", text)

    def test_cli_print_env(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gateway.main(["--print-env", "--listen", "127.0.0.1:18787"])
        self.assertEqual(rc, 0)
        self.assertIn("FX_GATEWAY_BASE_URL=http://127.0.0.1:18787", buf.getvalue())

    def test_cli_apply(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gateway.main(["--apply", "ollama"])
        self.assertEqual(rc, 0)
        info = json.loads(buf.getvalue())
        self.assertEqual(info["id"], "ollama")
        self.assertEqual(info["url"], "http://127.0.0.1:11434/v1")
        self.assertFalse(info["needs_key"])
        self.assertEqual(info["effective_api"], "chat")


    def test_apply_openrouter_defaults_chat(self):
        out = gateway.apply_provider("openrouter")
        self.assertEqual(out["id"], "openrouter")
        self.assertEqual(out["url"], "https://openrouter.ai/api/v1")
        self.assertEqual(out["model"], "stealth/ox-alpha")
        self.assertTrue(out["needs_key"])
        self.assertEqual(out["api"], "auto")
        self.assertEqual(out["effective_api"], "chat")
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["FX_UPSTREAM"], "https://openrouter.ai/api/v1")
        self.assertEqual(saved["AI_GATEWAY_API_KEY"], "local")
        self.assertNotIn("OPENAI_API_KEY", saved)

    def test_apply_openrouter_with_key(self):
        out = gateway.apply_provider("openrouter", key="sk-or-v1-testkey")
        self.assertEqual(out["id"], "openrouter")
        self.assertTrue(out["key"])
        self.assertFalse(out.get("needs_key"))
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["OPENAI_API_KEY"], "sk-or-v1-testkey")
        self.assertEqual(saved["AI_GATEWAY_API_KEY"], "local")

    def test_store_sk_or_selects_openrouter(self):
        out = gateway.store_api_key("sk-or-v1-pasted")
        self.assertEqual(out["id"], "openrouter")
        self.assertTrue(out["key"])
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["OPENAI_API_KEY"], "sk-or-v1-pasted")
        self.assertEqual(saved["FX_UPSTREAM"], "https://openrouter.ai/api/v1")

    def test_apply_vercel_with_openrouter_key_switches(self):
        out = gateway.apply_provider("vercel", key="sk-or-v1-from-chat")
        self.assertEqual(out["id"], "openrouter")
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["OPENAI_API_KEY"], "sk-or-v1-from-chat")

    def test_provider_from_key(self):
        self.assertEqual(gateway.provider_from_key("vck_abc"), "vercel")
        self.assertEqual(gateway.provider_from_key("sk-or-v1-abc"), "openrouter")
        self.assertEqual(gateway.provider_from_key("xai-secret"), "xai")
        self.assertEqual(gateway.provider_from_key("pplx-abc"), "perplexity")
        self.assertEqual(gateway.provider_from_key("sk-proj-openai"), "")

    def test_store_perplexity_key(self):
        out = gateway.store_perplexity_key("pplx-testkey")
        self.assertTrue(out.get("perplexity"))
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["PERPLEXITY_API_KEY"], "pplx-testkey")
        self.assertEqual(out.get("id"), "vercel")
        out = gateway.store_api_key("pplx-from-main-field")
        self.assertTrue(out.get("perplexity"))
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["PERPLEXITY_API_KEY"], "pplx-from-main-field")
        self.assertNotIn("OPENAI_API_KEY", saved)

    def test_run_perplexity_search_needs_key(self):
        out = gateway.run_perplexity_search({"query": "hello"})
        self.assertIn("Perplexity API key", out.get("error", ""))
        self.assertIn("Vercel AI Gateway", out.get("error", ""))
        self.assertEqual(gateway.run_perplexity_search({}).get("error"), "search query is required")
        out = gateway.run_perplexity_search({}, fallback_query="hello world")
        self.assertIn("pplx-", out.get("error", ""))
        self.assertNotEqual(out.get("error"), "search query is required")

    def test_openrouter_keeps_vercel_key_for_search(self):
        gateway.store_api_key("vck_gateway")
        self.assertTrue(gateway.current_provider().get("vercel"))
        out = gateway.apply_provider("openrouter", key="sk-or-v1-test")
        self.assertEqual(out["id"], "openrouter")
        self.assertTrue(out.get("gateway_search"))
        self.assertFalse(out.get("perplexity"))
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["VERCEL_AI_GATEWAY_API_KEY"], "vck_gateway")
        self.assertEqual(saved["AI_GATEWAY_API_KEY"], "local")
        self.assertEqual(saved["OPENAI_API_KEY"], "sk-or-v1-test")

    def test_switch_back_to_vercel_restores_key(self):
        gateway.store_api_key("vck_gateway")
        gateway.apply_provider("openrouter", key="sk-or-v1-test")
        out = gateway.apply_provider("vercel")
        self.assertTrue(out.get("vercel"))
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["AI_GATEWAY_API_KEY"], "vck_gateway")
        self.assertEqual(saved["VERCEL_AI_GATEWAY_API_KEY"], "vck_gateway")

    def test_store_vck_in_search_field_does_not_switch(self):
        gateway.apply_provider("openrouter", key="sk-or-v1-test")
        out = gateway.store_perplexity_key("vck_searchonly")
        self.assertEqual(out["id"], "openrouter")
        self.assertTrue(out.get("gateway_search"))
        self.assertFalse(out.get("perplexity"))
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["VERCEL_AI_GATEWAY_API_KEY"], "vck_searchonly")
        self.assertEqual(saved["OPENAI_API_KEY"], "sk-or-v1-test")
        self.assertEqual(saved["FX_UPSTREAM"], "https://openrouter.ai/api/v1")

    def test_run_gateway_search_when_no_pplx(self):
        import urllib.request
        os.environ["VERCEL_AI_GATEWAY_API_KEY"] = "vck_search"
        payload = (
            b'data: {"type":"tool-result","toolName":"perplexity_search",'
            b'"output":{"results":[{"title":"Hi","url":"https://example.com","snippet":"x"}]}}\n\n'
            b'data: {"type":"finish","finishReason":{"unified":"stop"}}\n\n'
        )
        class FakeSSE:
            def __init__(self):
                self._buf = io.BytesIO(payload)
                self.status = 200
                self.code = 200
                self.headers = {"Content-Type": "text/event-stream"}
            def readline(self, n=-1):
                return self._buf.readline()
            def read(self, n=-1):
                return self._buf.read()
            def close(self):
                return None
        orig = urllib.request.urlopen
        def fake_open(req, timeout=None):
            self.assertIn("ai-gateway.vercel.sh", req.full_url)
            self.assertIn("/v3/ai/language-model", req.full_url)
            items = {k.lower(): v for k, v in req.header_items()}
            self.assertTrue((items.get("authorization") or "").endswith("vck_search"))
            self.assertEqual(items.get("ai-gateway-protocol-version"), "0.0.1")
            self.assertEqual(items.get("ai-language-model-specification-version"), "3")
            return FakeSSE()
        urllib.request.urlopen = fake_open
        try:
            out = gateway.run_perplexity_search({"query": "hello world"})
        finally:
            urllib.request.urlopen = orig
        self.assertEqual(out.get("source"), "vercel-gateway")
        self.assertEqual(out["results"][0]["url"], "https://example.com")
        body = json.loads(gateway._gateway_search_body("hello world", 5))
        self.assertEqual(body["tools"][0]["id"], "gateway.perplexity_search")
        self.assertEqual(body["toolChoice"]["toolName"], "perplexity_search")

    def test_gateway_search_maps_credit_card_403(self):
        import urllib.request
        os.environ["VERCEL_AI_GATEWAY_API_KEY"] = "vck_search"
        orig = urllib.request.urlopen
        def fake_open(req, timeout=None):
            raise HTTPError(
                req.full_url, 403, "Forbidden", hdrs=None,
                fp=io.BytesIO(b'{"error":{"message":"AI Gateway requires a valid credit card on file to service requests."}}'),
            )
        urllib.request.urlopen = fake_open
        try:
            out = gateway.run_perplexity_search({"query": "hello world"})
        finally:
            urllib.request.urlopen = orig
        self.assertIn("credit card", out.get("error", "").lower())
        self.assertIn("pplx-", out.get("error", ""))
        self.assertNotIn("results", out)

    def test_gateway_403_falls_back_to_openrouter(self):
        import urllib.request
        os.environ["VERCEL_AI_GATEWAY_API_KEY"] = "vck_search"
        os.environ["OPENROUTER_API_KEY"] = "sk-or-fallback"
        orig = urllib.request.urlopen
        def fake_open(req, timeout=None):
            url = getattr(req, "full_url", "") or ""
            if "ai-gateway.vercel.sh" in url:
                raise HTTPError(
                    url, 403, "Forbidden", hdrs=None,
                    fp=io.BytesIO(b'{"error":{"message":"AI Gateway requires a valid credit card on file"}}'),
                )
            self.assertIn("openrouter.ai", url)
            class FakeResp:
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
                def read(self):
                    return json.dumps({
                        "choices": [{
                            "message": {
                                "annotations": [{
                                    "type": "url_citation",
                                    "url_citation": {
                                        "title": "Horst Schlämmer",
                                        "url": "https://de.wikipedia.org/wiki/Horst_Schlämmer",
                                        "content": "Comedy figure by Hape Kerkeling.",
                                    },
                                }]
                            }
                        }]
                    }).encode()
            return FakeResp()
        urllib.request.urlopen = fake_open
        try:
            out = gateway.run_perplexity_search({"query": "Horst Schlemmer"})
        finally:
            urllib.request.urlopen = orig
        self.assertEqual(out.get("source"), "openrouter")
        self.assertEqual(out["results"][0]["url"], "https://de.wikipedia.org/wiki/Horst_Schlämmer")

    def test_openrouter_annotations_parsed(self):
        data = {
            "choices": [{
                "message": {
                    "content": "ignored",
                    "annotations": [
                        {"type": "url_citation", "url_citation": {
                            "title": "A", "url": "https://a.example", "content": "aa"}},
                        {"type": "url_citation", "url_citation": {
                            "title": "A dup", "url": "https://a.example", "content": "skip"}},
                        {"type": "url_citation", "url_citation": {
                            "title": "B", "url": "https://b.example", "content": "bb"}},
                    ],
                }
            }]
        }
        out = gateway._hits_from_openrouter(data, "q", 5)
        self.assertEqual(out["source"], "openrouter")
        self.assertEqual([r["url"] for r in out["results"]], ["https://a.example", "https://b.example"])

    def test_gateway_event_accepts_provider_tool_name(self):
        parsed = gateway._tool_result_from_gateway_event({
            "type": "tool-output-available",
            "toolName": "gateway.perplexity_search",
            "output": {"value": [{"title": "T", "url": "https://t.example", "snippet": "s"}]},
        })
        self.assertEqual(parsed["results"][0]["url"], "https://t.example")

    def test_pplx_wins_over_gateway(self):
        import urllib.request
        os.environ["PERPLEXITY_API_KEY"] = "pplx-first"
        os.environ["VERCEL_AI_GATEWAY_API_KEY"] = "vck_second"
        class FakeResp:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def read(self):
                return json.dumps({"results": [{"title": "A", "url": "https://a.example", "snippet": "s"}]}).encode()
        orig = urllib.request.urlopen
        def fake_open(req, timeout=None):
            self.assertIn("api.perplexity.ai/search", req.full_url)
            return FakeResp()
        urllib.request.urlopen = fake_open
        try:
            out = gateway.run_perplexity_search({"query": "q"})
        finally:
            urllib.request.urlopen = orig
        self.assertEqual(out.get("source"), "perplexity")
        self.assertEqual(out["results"][0]["url"], "https://a.example")

    def test_stamp_changes_with_vercel_search_key(self):
        a = gateway._gateway_stamp("https://openrouter.ai/api/v1", "auto", "sk-or-a")
        os.environ["VERCEL_AI_GATEWAY_API_KEY"] = "vck_x"
        b = gateway._gateway_stamp("https://openrouter.ai/api/v1", "auto", "sk-or-a")
        self.assertNotEqual(a, b)
        self.assertFalse(gateway._stamp_matches(a, "https://openrouter.ai/api/v1", "auto", "sk-or-a"))
        self.assertTrue(gateway._stamp_matches(b, "https://openrouter.ai/api/v1", "auto", "sk-or-a"))

    def test_chat_request_enriches_search_schema(self):
        req = gateway.chat_request("m", False, json.dumps({
            "prompt": [{"role": "user", "content": "hi"}],
            "tools": [{"type": "function", "name": "perplexity_search",
                       "inputSchema": {"type": "object", "properties": {}}}],
        }).encode())
        fn = req["tools"][0]["function"]
        self.assertIn("query", fn["parameters"]["properties"])
        self.assertIn("query", fn["parameters"].get("required") or [])

    def test_run_perplexity_search_parses_results(self):
        import urllib.request
        os.environ["PERPLEXITY_API_KEY"] = "pplx-test"
        class FakeResp:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def read(self):
                return json.dumps({"results": [{
                    "title": "Example",
                    "url": "https://example.com",
                    "snippet": "hi",
                    "last_updated": "2026-01-01",
                }]}).encode()
        orig = urllib.request.urlopen
        def fake_open(req, timeout=None):
            self.assertIn("api.perplexity.ai/search", req.full_url)
            self.assertEqual(req.get_header("Authorization") or req.headers.get("Authorization"), "Bearer pplx-test")
            return FakeResp()
        urllib.request.urlopen = fake_open
        try:
            out = gateway.run_perplexity_search({"query": "hello world", "maxResults": 3})
        finally:
            urllib.request.urlopen = orig
        self.assertEqual(out["query"], "hello world")
        self.assertEqual(out["results"][0]["url"], "https://example.com")
        self.assertEqual(out["results"][0]["date"], "2026-01-01")

    def test_apply_provider_pplx_key_does_not_switch(self):
        gateway.apply_provider("openrouter", key="sk-or-v1-test")
        out = gateway.apply_provider("openrouter", key="pplx-secret")
        self.assertEqual(out["id"], "openrouter")
        self.assertTrue(out.get("perplexity"))
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["PERPLEXITY_API_KEY"], "pplx-secret")
        self.assertEqual(saved["OPENAI_API_KEY"], "sk-or-v1-test")

    def test_stamp_changes_with_perplexity_key(self):
        a = gateway._gateway_stamp("https://openrouter.ai/api/v1", "auto", "sk-or-a")
        os.environ["PERPLEXITY_API_KEY"] = "pplx-x"
        b = gateway._gateway_stamp("https://openrouter.ai/api/v1", "auto", "sk-or-a")
        self.assertNotEqual(a, b)
        self.assertFalse(gateway._stamp_matches(a, "https://openrouter.ai/api/v1", "auto", "sk-or-a"))
        self.assertTrue(gateway._stamp_matches(b, "https://openrouter.ai/api/v1", "auto", "sk-or-a"))

    def test_openrouter_env_key_is_read(self):
        os.environ["OPENROUTER_API_KEY"] = "sk-or-from-env"
        self.assertEqual(gateway.api_key_from_env(), "sk-or-from-env")

    def test_upstream_http_error_messages(self):
        msg = gateway.upstream_http_error(
            401, b'{"error":{"message":"No cookie auth credentials found"}}',
        )
        self.assertIn("Provider rejected the API key", msg)
        self.assertIn("HTTP 401", msg)
        self.assertIn("No cookie auth", msg)
        msg = gateway.upstream_http_error(
            403, b'{"error":{"message":"Key limit exceeded (total limit)"}}',
        )
        self.assertIn("Provider forbidden", msg)
        self.assertIn("HTTP 403", msg)
        self.assertIn("Key limit exceeded", msg)

    def test_stamp_includes_key_fingerprint(self):
        a = gateway._gateway_stamp("https://openrouter.ai/api/v1", "auto", "sk-or-a")
        b = gateway._gateway_stamp("https://openrouter.ai/api/v1", "auto", "sk-or-b")
        self.assertNotEqual(a, b)
        self.assertTrue(gateway._stamp_matches(a, "https://openrouter.ai/api/v1", "auto", "sk-or-a"))
        self.assertFalse(gateway._stamp_matches(a, "https://openrouter.ai/api/v1", "auto", "sk-or-b"))
        old = "https://openrouter.ai/api/v1\nauto\n"
        self.assertFalse(gateway._stamp_matches(old, "https://openrouter.ai/api/v1", "auto", "sk-or-a"))

    def test_cli_apply_api(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gateway.main(["--apply", "openai", "--api", "responses"])
        self.assertEqual(rc, 0)
        info = json.loads(buf.getvalue())
        self.assertEqual(info["id"], "openai")
        self.assertEqual(info["api"], "responses")
        self.assertEqual(info["effective_api"], "responses")
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["FX_UPSTREAM_API"], "responses")


class ApiMode(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(gateway.normalize_api("auto"), "auto")
        self.assertEqual(gateway.normalize_api("CHAT"), "chat")
        self.assertEqual(gateway.normalize_api("completions"), "chat")
        self.assertEqual(gateway.normalize_api("responses"), "responses")
        self.assertEqual(gateway.normalize_api("/v1/responses"), "responses")
        with self.assertRaises(ValueError):
            gateway.normalize_api("grpc")

    def test_effective_defaults(self):
        self.assertEqual(gateway.effective_api("openai", "auto"), "responses")
        self.assertEqual(gateway.effective_api("xai", "auto"), "responses")
        self.assertEqual(gateway.effective_api("ollama", "auto"), "chat")
        self.assertEqual(gateway.effective_api("groq", "auto"), "chat")
        self.assertEqual(gateway.effective_api("openai", "chat"), "chat")
        self.assertEqual(gateway.effective_api("ollama", "responses"), "responses")

    def test_fallback_codes(self):
        self.assertTrue(gateway.should_fallback_to_chat(404))
        self.assertTrue(gateway.should_fallback_to_chat(405))
        self.assertTrue(gateway.should_fallback_to_chat(501))
        self.assertFalse(gateway.should_fallback_to_chat(401))
        self.assertFalse(gateway.should_fallback_to_chat(500))
        self.assertTrue(gateway.should_fallback_to_chat(400, b'{"error":"Unknown request URL"}'))
        self.assertTrue(gateway.should_fallback_to_chat(400, b"does not support /responses"))
        self.assertFalse(gateway.should_fallback_to_chat(400, b'{"error":"invalid model"}'))


class ResponsesTranslate(unittest.TestCase):
    def test_basic_prompt_and_store_false(self):
        req = gateway.responses_request("grok-4", True, json.dumps({
            "prompt": [
                {"role": "system", "content": "you are a tool"},
                {"role": "user", "content": [{"type": "text", "text": "hello"}]},
            ],
            "maxOutputTokens": 128,
            "reasoning": "high",
        }).encode())
        self.assertEqual(req["model"], "grok-4")
        self.assertTrue(req["stream"])
        self.assertIs(req["store"], False)
        self.assertEqual(req["max_output_tokens"], 128)
        self.assertEqual(req["reasoning"], {"effort": "high"})
        self.assertEqual(req["input"][0], {"role": "system", "content": "you are a tool"})
        self.assertEqual(req["input"][1], {"role": "user", "content": "hello"})
        self.assertNotIn("messages", req)

    def test_tools_flattened_and_history(self):
        req = gateway.responses_request("m", False, json.dumps({
            "prompt": [
                {"role": "user", "content": [{"type": "text", "text": "list"}]},
                {"role": "assistant", "content": [
                    {"type": "text", "text": "ok"},
                    {"type": "tool-call", "toolCallId": "c1", "toolName": "bash",
                     "input": {"command": "ls"}},
                ]},
                {"role": "tool", "content": [
                    {"type": "tool-result", "toolCallId": "c1", "toolName": "bash",
                     "output": {"type": "text", "value": "a.txt"}},
                ]},
            ],
            "tools": [{"type": "function", "name": "bash", "description": "run",
                       "inputSchema": {"type": "object", "properties": {"command": {"type": "string"}}}}],
            "toolChoice": {"type": "required"},
        }).encode())
        self.assertEqual(req["tools"][0], {
            "type": "function",
            "name": "bash",
            "description": "run",
            "parameters": {"type": "object", "properties": {"command": {"type": "string"}}},
        })
        self.assertNotIn("function", req["tools"][0])
        self.assertEqual(req["tool_choice"], "required")
        kinds = [i.get("type") or i.get("role") for i in req["input"]]
        self.assertEqual(kinds, ["user", "assistant", "function_call", "function_call_output"])
        self.assertEqual(req["input"][2]["call_id"], "c1")
        self.assertEqual(req["input"][2]["name"], "bash")
        self.assertEqual(req["input"][3]["output"], "a.txt")

    def test_to_chat_text(self):
        raw = json.dumps({
            "status": "completed",
            "output": [{"type": "message", "content": [
                {"type": "output_text", "text": "pong"},
            ]}],
            "usage": {"input_tokens": 4, "output_tokens": 1},
        }).encode()
        out = json.loads(gateway.responses_to_chat(raw))
        self.assertEqual(out["choices"][0]["message"]["content"], "pong")
        self.assertEqual(out["choices"][0]["finish_reason"], "stop")
        self.assertEqual(out["usage"]["prompt_tokens"], 4)

    def test_to_chat_tools(self):
        raw = {
            "status": "completed",
            "output": [{
                "type": "function_call",
                "call_id": "c1",
                "name": "bash",
                "arguments": '{"command":"ls"}',
            }],
        }
        out = json.loads(gateway.responses_to_chat(raw))
        msg = out["choices"][0]["message"]
        self.assertEqual(out["choices"][0]["finish_reason"], "tool_calls")
        self.assertEqual(msg["tool_calls"][0]["id"], "c1")
        self.assertEqual(msg["tool_calls"][0]["function"]["name"], "bash")

    def test_to_chat_output_text_fallback(self):
        out = json.loads(gateway.responses_to_chat({"output_text": "hi", "output": []}))
        self.assertEqual(out["choices"][0]["message"]["content"], "hi")

    def test_incomplete_length(self):
        out = json.loads(gateway.responses_to_chat({
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "cut"}]}],
        }))
        self.assertEqual(out["choices"][0]["finish_reason"], "length")


class ResponseSSE(unittest.TestCase):
    def test_text_and_completed(self):
        s = gateway.ResponseStream()
        got = []
        got += s.consume(b'{"type":"response.output_text.delta","delta":"Hel"}')
        got += s.consume(b'{"type":"response.output_text.delta","delta":"lo"}')
        got += s.consume(json.dumps({
            "type": "response.completed",
            "response": {"status": "completed", "usage": {"input_tokens": 3, "output_tokens": 2}},
        }))
        self.assertEqual(s.close(), [])
        types = [json.loads(e)["type"] for e in got]
        self.assertEqual(types, ["text-delta", "text-delta", "finish"])
        self.assertEqual(json.loads(got[0])["delta"], "Hel")
        self.assertEqual(json.loads(got[2])["finishReason"]["unified"], "stop")
        self.assertEqual(json.loads(got[2])["usage"]["inputTokens"]["total"], 3)

    def test_tool_call_deltas(self):
        s = gateway.ResponseStream()
        got = []
        got += s.consume(json.dumps({
            "type": "response.output_item.added",
            "item": {"id": "fc_1", "type": "function_call", "call_id": "c1", "name": "bash", "arguments": ""},
        }))
        got += s.consume(json.dumps({
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_1", "call_id": "c1", "delta": '{"command":',
        }))
        got += s.consume(json.dumps({
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_1", "delta": '"ls"}',
        }))
        got += s.consume(json.dumps({
            "type": "response.completed",
            "response": {"status": "completed", "output": []},
        }))
        types = [json.loads(e)["type"] for e in got]
        self.assertEqual(types, [
            "tool-input-start", "tool-input-delta", "tool-input-delta",
            "tool-input-end", "tool-call", "finish",
        ])
        call = json.loads(got[4])
        self.assertEqual(call["toolCallId"], "c1")
        self.assertEqual(call["input"], {"command": "ls"})
        self.assertEqual(json.loads(got[5])["finishReason"]["unified"], "tool-calls")

    def test_harvest_function_call_on_completed(self):
        s = gateway.ResponseStream()
        got = s.consume(json.dumps({
            "type": "response.completed",
            "response": {
                "status": "completed",
                "output": [{
                    "type": "function_call",
                    "call_id": "c9",
                    "name": "bash",
                    "arguments": '{"command":"pwd"}',
                }],
            },
        }))
        types = [json.loads(e)["type"] for e in got]
        self.assertEqual(types, [
            "tool-input-start", "tool-input-delta", "tool-input-end", "tool-call", "finish",
        ])
        self.assertEqual(json.loads(got[3])["input"], {"command": "pwd"})

    def test_reasoning_delta(self):
        s = gateway.ResponseStream()
        got = s.consume(b'{"type":"response.reasoning_summary_text.delta","delta":"hmm"}')
        self.assertEqual(json.loads(got[0])["type"], "reasoning-delta")
        self.assertEqual(json.loads(got[0])["delta"], "hmm")

    def test_read_sse_injects_event_type(self):
        class Fake:
            def __init__(self):
                raw = (
                    b"event: response.output_text.delta\n"
                    b"data: {\"delta\":\"Hi\"}\n"
                    b"\n"
                    b"event: response.completed\n"
                    b"data: {\"response\":{\"status\":\"completed\"}}\n"
                    b"\n"
                )
                self._buf = io.BytesIO(raw)

            def readline(self):
                return self._buf.readline()

        payloads = list(gateway.read_sse_data(Fake()))
        self.assertEqual(json.loads(payloads[0])["type"], "response.output_text.delta")
        self.assertEqual(json.loads(payloads[0])["delta"], "Hi")
        self.assertEqual(json.loads(payloads[1])["type"], "response.completed")


class ResponsesHTTP(unittest.TestCase):
    def _serve(self, handler, api="responses", provider_id="openai"):
        up = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        t = threading.Thread(target=up.serve_forever, daemon=True)
        t.start()
        gw = gateway.GatewayServer(
            "127.0.0.1:0",
            gateway.Upstream(
                f"http://127.0.0.1:{up.server_address[1]}/v1",
                "k",
                api=api,
                provider_id=provider_id,
            ),
        )
        gt = threading.Thread(target=gw.serve_forever, daemon=True)
        gt.start()
        return up, t, gw, gt

    def _stop(self, up, t, gw, gt):
        gw.shutdown(); up.shutdown()
        gw.server_close(); up.server_close()
        gt.join(timeout=1); t.join(timeout=1)

    def test_stream_uses_responses(self):
        saw = {"path": "", "body": None}

        class Up(BaseHTTPRequestHandler):
            def log_message(self, *a):
                return

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                saw["path"] = self.path
                saw["body"] = json.loads(self.rfile.read(n) or b"{}")
                payload = (
                    b"event: response.output_text.delta\n"
                    b'data: {"type":"response.output_text.delta","delta":"Hi"}\n\n'
                    b"event: response.completed\n"
                    b'data: {"type":"response.completed","response":{"status":"completed"}}\n\n'
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        up, t, gw, gt = self._serve(Up)
        try:
            body = json.dumps({"prompt": [{"role": "user", "content": "hi"}]}).encode()
            req = Request(
                f"http://127.0.0.1:{gw.server_address[1]}/v3/ai/language-model",
                data=body, method="POST",
            )
            req.add_header("Content-Type", "application/json")
            req.add_header("ai-language-model-id", "grok-4")
            req.add_header("ai-language-model-streaming", "true")
            r = urlopen(req, timeout=2)
            text = r.read().decode()
            self.assertEqual(saw["path"], "/v1/responses")
            self.assertIs(saw["body"]["store"], False)
            self.assertEqual(saw["body"]["model"], "grok-4")
            self.assertIn("text-delta", text)
            self.assertIn("Hi", text)
            self.assertIn("finish", text)
            self.assertNotIn("choices", text)
        finally:
            self._stop(up, t, gw, gt)

    def test_nonstream_rewritten_to_chat(self):
        class Up(BaseHTTPRequestHandler):
            def log_message(self, *a):
                return

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(n)
                body = json.dumps({
                    "status": "completed",
                    "output": [{"type": "message", "content": [
                        {"type": "output_text", "text": "pong"},
                    ]}],
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        up, t, gw, gt = self._serve(Up)
        try:
            body = json.dumps({"prompt": [{"role": "user", "content": "ping"}]}).encode()
            req = Request(
                f"http://127.0.0.1:{gw.server_address[1]}/v3/ai/language-model",
                data=body, method="POST",
            )
            req.add_header("Content-Type", "application/json")
            req.add_header("ai-language-model-id", "any/id")
            req.add_header("ai-language-model-streaming", "false")
            r = urlopen(req, timeout=2)
            out = json.loads(r.read())
            self.assertEqual(out["choices"][0]["message"]["content"], "pong")
        finally:
            self._stop(up, t, gw, gt)

    def test_auto_falls_back_on_404(self):
        saw = []

        class Up(BaseHTTPRequestHandler):
            def log_message(self, *a):
                return

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(n)
                saw.append(self.path)
                if self.path.endswith("/responses"):
                    body = b'{"error":"Unknown request URL"}'
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                payload = (
                    b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
                    b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                    b"data: [DONE]\n\n"
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        up, t, gw, gt = self._serve(Up, api="auto", provider_id="openai")
        try:
            body = json.dumps({"prompt": [{"role": "user", "content": "hi"}]}).encode()
            req = Request(
                f"http://127.0.0.1:{gw.server_address[1]}/v3/ai/language-model",
                data=body, method="POST",
            )
            req.add_header("Content-Type", "application/json")
            req.add_header("ai-language-model-id", "gpt-4o")
            req.add_header("ai-language-model-streaming", "true")
            r = urlopen(req, timeout=2)
            text = r.read().decode()
            self.assertEqual(saw, ["/v1/responses", "/v1/chat/completions"])
            self.assertIn("text-delta", text)
            self.assertIn("Hi", text)
        finally:
            self._stop(up, t, gw, gt)


if __name__ == "__main__":
    unittest.main()
