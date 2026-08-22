#!/usr/bin/env python3
"""Loopback translator: fx Gateway protocol → OpenAI-compatible /v1.

fx only accepts loopback HTTP and speaks `/v3/ai/language-model`, not
OpenAI Chat Completions. This process is the missing server — same job as
https://github.com/BorjaGM1/fx-openai, in the Python 3 stdlib so `fxs`
does not need a second binary or a second terminal.

  fx  --Gateway-->  127.0.0.1:18787  --/v1-->  OpenAI / xAI / Ollama / …

Wire format: PROTOCOL.md in fx-openai (catalog rewrite, prompt→messages,
SSE text-delta / tool-input-* / finish). OpenAI and xAI default to
POST /v1/responses (reasoning, tool items, store=false). Everyone else
stays on /v1/chat/completions; auto falls back if /responses is missing.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlparse

# `extras/ui/gateway.py` is a symlink to this file. Resolve the real source
# directory so sibling compatibility modules remain importable through either
# entry point without duplicating them into the WebUI tree.
_GATEWAY_MODULE_DIR = str(Path(__file__).resolve().parent)
if _GATEWAY_MODULE_DIR not in sys.path:
    sys.path.insert(0, _GATEWAY_MODULE_DIR)
import search_policy

LISTEN_DEFAULT = os.environ.get("FXS_GATEWAY_LISTEN", "127.0.0.1:18787")
USER_AGENT = "fxs-gateway/1"
HOME = Path.home()
ENV_FILE = HOME / ".config" / "fx" / "env"
STATE_DIR = Path(
    os.environ.get("FXS_GATEWAY_STATE", str(HOME / ".local" / "share" / "fx-sandbox"))
)
PID_FILE = Path(os.environ.get("FXS_GATEWAY_PID", str(STATE_DIR / "gateway.pid")))
LOG_FILE = Path(os.environ.get("FXS_GATEWAY_LOG", str(STATE_DIR / "gateway.log")))
UPSTREAM_STAMP = STATE_DIR / "gateway.upstream"

PROVIDERS: list[dict[str, str]] = [
    {"id": "vercel", "label": "Vercel AI Gateway", "url": ""},
    {"id": "openai", "label": "OpenAI", "url": "https://api.openai.com/v1"},
    {"id": "xai", "label": "xAI", "url": "https://api.x.ai/v1"},
    {"id": "openrouter", "label": "OpenRouter", "url": "https://openrouter.ai/api/v1"},
    {"id": "ollama", "label": "Ollama", "url": "http://127.0.0.1:11434/v1"},
    {"id": "lmstudio", "label": "LM Studio", "url": "http://127.0.0.1:1234/v1"},
    {"id": "groq", "label": "Groq", "url": "https://api.groq.com/openai/v1"},
    {"id": "together", "label": "Together", "url": "https://api.together.xyz/v1"},
    {"id": "fireworks", "label": "Fireworks", "url": "https://api.fireworks.ai/inference/v1"},
    {"id": "deepseek", "label": "DeepSeek", "url": "https://api.deepseek.com/v1"},
    {"id": "mistral", "label": "Mistral", "url": "https://api.mistral.ai/v1"},
]
PROVIDER_BY_ID = {p["id"]: p for p in PROVIDERS}
PROVIDER_ALIASES = {
    "gateway": "vercel",
    "ai-gateway": "vercel",
    "grok": "xai",
    "llama.cpp": "lmstudio",
    "llamacpp": "lmstudio",
    "together.ai": "together",
    "togetherai": "together",
}
DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "xai": "grok-4",
    "openrouter": "stealth/ox-alpha",
    "groq": "llama-3.3-70b-versatile",
    "together": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
    "fireworks": "accounts/fireworks/models/llama-v3p1-70b-instruct",
    "deepseek": "deepseek-chat",
    "mistral": "mistral-large-latest",
    "ollama": "",
    "lmstudio": "",
    "custom": "",
}
LOCAL_PROVIDERS = {"ollama", "lmstudio"}
# Hosts that prefer /v1/responses (reasoning + tool items). Others stay on
# chat/completions unless the user sets FX_UPSTREAM_API=responses.
RESPONSES_DEFAULT = {"openai", "xai"}
# OpenRouter paid ids 403 on a free/exhausted key. Prefer these, then :free.
OPENROUTER_FREE_HINTS = (
    "stealth/ox-alpha",
    "openrouter/free",
    "z-ai/glm-5.2:free",
    "openai/gpt-oss-20b:free",
)
_REASONING_EFFORT = {"none", "minimal", "low", "medium", "high", "xhigh"}


ERR_INVALID_BODY = "invalid gateway request body"
ERR_IMAGE_ONLY = "image-only user message is not supported"
ERR_MISSING_MODEL = "missing ai-language-model-id"

# ---------------------------------------------------------------------------
# env file
# ---------------------------------------------------------------------------

_EXPORT = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def parse_env_file(path: Optional[Path] = None) -> dict[str, str]:
    if path is None:
        path = ENV_FILE
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _EXPORT.match(line)
        if not m:
            continue
        val = m.group(2).strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        out[m.group(1)] = val
    return out


def load_env_file(path: Optional[Path] = None) -> None:
    for k, v in parse_env_file(path).items():
        os.environ.setdefault(k, v)


def upsert_env(updates: dict[str, Optional[str]], path: Optional[Path] = None) -> None:
    """Set or delete keys in ~/.config/fx/env. None / '' deletes. Mode 0600."""
    if path is None:
        path = ENV_FILE
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    existing: list[str] = []
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            existing = []
    drop = set(updates)
    kept: list[str] = []
    if not existing:
        kept.append("# generated by fxs — mode 0600, never commit")
    for line in existing:
        m = _EXPORT.match(line.strip())
        if m and m.group(1) in drop:
            continue
        kept.append(line)
    for key, value in updates.items():
        if value is None or value == "":
            continue
        escaped = value.replace("'", "'\\''")
        kept.append(f"export {key}='{escaped}'")
    while kept and kept[-1] == "":
        kept.pop()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(kept) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def api_key_from_env(getenv: Callable[[str], str] = lambda k: os.environ.get(k, "")) -> str:
    for k in (
        "OPENAI_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_API_KEY",
        "XAI_API_KEY", "GROQ_API_KEY",
    ):
        v = getenv(k)
        if v:
            return v
    return ""


def provider_from_key(key: str) -> str:
    k = (key or "").strip()
    if k.startswith("vck_"):
        return "vercel"
    if k.startswith("sk-or-"):
        return "openrouter"
    if k.startswith("xai-"):
        return "xai"
    if k.startswith("pplx-"):
        return "perplexity"
    return ""


def configured_upstream(getenv: Callable[[str], str] = lambda k: os.environ.get(k, "")) -> str:
    return (getenv("FX_UPSTREAM") or getenv("OPENAI_BASE_URL") or "").rstrip("/")


def normalize_api(raw: str) -> str:
    v = (raw or "auto").strip().lower()
    if v in ("chat", "completions", "chat.completions", "chat_completions", "completion"):
        return "chat"
    if v in ("responses", "response", "/responses", "v1/responses", "/v1/responses"):
        return "responses"
    if v in ("auto", "", "default"):
        return "auto"
    raise ValueError(f"unknown API {raw!r} (try auto, chat, responses)")


def configured_api(getenv: Callable[[str], str] = lambda k: os.environ.get(k, "")) -> str:
    try:
        return normalize_api(getenv("FX_UPSTREAM_API") or "auto")
    except ValueError:
        return "auto"


def effective_api(pid: str = "", api: str = "") -> str:
    """Concrete upstream path: 'chat' or 'responses'."""
    mode = api or configured_api()
    if mode in ("chat", "responses"):
        return mode
    pid = pid or provider_id_for(configured_upstream())
    return "responses" if pid in RESPONSES_DEFAULT else "chat"


def resolve_provider(name_or_url: str) -> dict[str, str]:
    raw = (name_or_url or "").strip()
    if not raw or raw.lower() in ("vercel", "gateway", "ai-gateway", "default"):
        return dict(PROVIDER_BY_ID["vercel"])
    low = raw.lower()
    low = PROVIDER_ALIASES.get(low, low)
    if low in PROVIDER_BY_ID:
        return dict(PROVIDER_BY_ID[low])
    if raw.startswith("http://") or raw.startswith("https://"):
        url = normalize_upstream_url(raw)
        pid = provider_id_for(url)
        label = PROVIDER_BY_ID.get(pid, {}).get("label") or urlparse(url).netloc or "Custom"
        return {"id": pid if pid != "vercel" else "custom", "label": label, "url": url}
    raise ValueError(
        f"unknown provider {raw!r} (try vercel, openai, xai, openrouter, ollama, groq, together, or a /v1 URL)"
    )


def provider_id_for(url: str) -> str:
    u = (url or "").rstrip("/")
    if not u:
        return "vercel"
    for p in PROVIDERS:
        if p["url"] and p["url"].rstrip("/") == u:
            return p["id"]
    host = (urlparse(u).hostname or "").lower()
    if host in ("api.openai.com",):
        return "openai"
    if host in ("api.x.ai", "x.ai"):
        return "xai"
    if "openrouter.ai" in host:
        return "openrouter"
    if host in ("127.0.0.1", "localhost", "::1") and u.endswith(":11434/v1"):
        return "ollama"
    if host in ("127.0.0.1", "localhost", "::1") and u.endswith(":1234/v1"):
        return "lmstudio"
    if "groq.com" in host:
        return "groq"
    if "together.xyz" in host or "together.ai" in host:
        return "together"
    if "fireworks.ai" in host:
        return "fireworks"
    if "deepseek.com" in host:
        return "deepseek"
    if "mistral.ai" in host:
        return "mistral"
    return "custom"


def provider_needs_key(pid: str) -> bool:
    return pid not in ("vercel", "") and pid not in LOCAL_PROVIDERS


def is_free_model(mid: str) -> bool:
    m = (mid or "").strip().lower()
    if not m:
        return False
    if m.endswith(":free") or m == "openrouter/free":
        return True
    return m.startswith("stealth/")


def model_label(mid: str) -> str:
    raw = (mid or "").strip()
    if not raw:
        return ""
    name = raw.split("/")[-1]
    if name.endswith(":free"):
        return name[:-5] + " (free)"
    if is_free_model(raw):
        return name + " (free)"
    return name


def _openrouter_alias(current: str, ids: list[str]) -> str:
    if not current:
        return ""
    if current in ids:
        return current
    tail = current.split("/")[-1]
    for c in (
        current + ":free",
        "z-ai/" + tail,
        "z-ai/" + tail + ":free",
        "openai/" + tail,
        "openai/" + tail + ":free",
    ):
        if c in ids:
            return c
    for i in ids:
        if i.endswith("/" + tail) or i.endswith("/" + tail + ":free"):
            return i
    return ""


def upstream_http_error(code: int, body: bytes) -> str:
    text = (body or b"").decode("utf-8", errors="replace")
    msg = ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = str(err.get("message") or err.get("code") or "")
        elif isinstance(err, str):
            msg = err
        elif data.get("message"):
            msg = str(data.get("message"))
    if not msg:
        line = text.strip().splitlines()[0] if text.strip() else ""
        msg = line[:240]
    msg = " ".join(str(msg).split())
    if code == 401:
        prefix = "Provider rejected the API key"
    elif code == 403:
        prefix = "Provider forbidden"
    elif code == 429:
        prefix = "Provider rate-limited"
    else:
        prefix = "Provider error"
    return f"{prefix} (HTTP {code})" + (f". {msg}" if msg else "")


def suggest_model(pid: str, current: str = "", catalog: Optional[list[str]] = None) -> str:
    """Pick a model the selected provider can serve without owning fx defaults.

    A current model is only meaningful when the caller knows it belongs to the
    provider being selected. When a live catalog exists it is authoritative;
    otherwise provider presets are compatibility hints for non-Vercel backends.
    Vercel with no explicit/current model returns empty so the installed fx
    build chooses its own native default.
    """
    pid = pid or "vercel"
    current = (current or "").strip()
    ids = [i for i in (catalog or []) if i]
    if ids:
        if pid == "openrouter":
            alias = _openrouter_alias(current, ids)
            if alias:
                return alias
            for hint in OPENROUTER_FREE_HINTS:
                if hint in ids:
                    return hint
            for i in ids:
                if is_free_model(i):
                    return i
            return ids[0]
        if current in ids:
            return current
        hint = DEFAULT_MODELS.get(pid) or ""
        if hint in ids:
            return hint
        prefix = hint.split("/")[-1] if hint else ""
        if prefix:
            for i in ids:
                if i == prefix or i.endswith("/" + prefix) or i.endswith(":" + prefix):
                    return i
        return ids[0]
    if pid == "vercel":
        return current if current and "/" in current else ""
    hint = DEFAULT_MODELS.get(pid) or ""
    return current or hint


def normalize_upstream_url(url: str) -> str:
    url = (url or "").rstrip("/")
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.path in ("", "/"):
        return url + "/v1"
    return url


def current_provider() -> dict[str, Any]:
    load_env_file()
    up = configured_upstream()
    pid = provider_id_for(up)
    label = next((p["label"] for p in PROVIDERS if p["id"] == pid), "Custom")
    if pid == "custom":
        label = urlparse(up).netloc or up or "Custom"
    key = api_key_from_env()
    vck = os.environ.get("AI_GATEWAY_API_KEY", "")
    if not up:
        has = vck.startswith("vck_")
    else:
        has = bool(key) or (pid in LOCAL_PROVIDERS)
    return {
        "id": pid,
        "label": label if up else "Vercel AI Gateway",
        "url": up,
        "key": has,
        "vercel": not up,
        "model": os.environ.get("FX_MODEL", ""),
        "api": "vercel" if not up else configured_api(),
        "effective_api": "vercel" if not up else effective_api(pid),
        "providers": PROVIDERS,
        "perplexity": bool((os.environ.get("PERPLEXITY_API_KEY") or "").strip()),
        "gateway_search": bool(vercel_gateway_key()),
        "openrouter_search": bool(openrouter_api_key()),
    }


def host_gateway_rewrite(url: str) -> str:
    """Point container loopback at the Docker host (Ollama on the laptop)."""
    if not url:
        return url
    return re.sub(
        r"^(https?://)(?:127\.0\.0\.1|localhost|\[::1\])(?=[:/]|$)",
        r"\1host.docker.internal",
        url,
        count=1,
    )


# ---------------------------------------------------------------------------
# translate: catalog
# ---------------------------------------------------------------------------

def catalog(raw: bytes) -> bytes:
    data = json.loads(raw.decode() if isinstance(raw, (bytes, bytearray)) else raw)
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        items = []
    out = []
    for m in items:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        if not mid:
            continue
        window = int(m.get("context_window") or 0) or int(m.get("context_length") or 0)
        max_tok = int(m.get("max_tokens") or 0) or int(m.get("max_output_tokens") or 0)
        out.append({
            "id": mid,
            "type": "language",
            "tags": ["tool-use"],
            "context_window": window,
            "max_tokens": max_tok,
        })
    return json.dumps({"data": out}, separators=(",", ":")).encode()


# ---------------------------------------------------------------------------
# translate: Gateway request → OpenAI chat
# ---------------------------------------------------------------------------

class TranslateError(ValueError):
    def __init__(self, msg: str, code: str = ERR_INVALID_BODY):
        super().__init__(msg)
        self.code = code


def chat_request(model: str, stream: bool, body: bytes) -> dict[str, Any]:
    if not (model or "").strip():
        raise TranslateError(ERR_MISSING_MODEL, ERR_MISSING_MODEL)
    try:
        inbound = json.loads(body.decode() if body else b"{}")
    except json.JSONDecodeError as e:
        raise TranslateError(f"{ERR_INVALID_BODY}: {e}", ERR_INVALID_BODY) from e
    if not isinstance(inbound, dict):
        raise TranslateError(ERR_INVALID_BODY, ERR_INVALID_BODY)

    out: dict[str, Any] = {"model": model, "stream": stream, "messages": []}
    if inbound.get("maxOutputTokens"):
        out["max_tokens"] = inbound["maxOutputTokens"]

    last_user_image_only = False
    for msg in inbound.get("prompt") or []:
        converted, image_only = convert_message(msg)
        if (msg or {}).get("role") == "user":
            last_user_image_only = image_only
        out["messages"].extend(converted)
    if last_user_image_only:
        raise TranslateError(ERR_IMAGE_ONLY, ERR_IMAGE_ONLY)

    tools = []
    for tool in inbound.get("tools") or []:
        name = (tool or {}).get("name") or ""
        if not name:
            continue
        params = tool.get("inputSchema")
        if not params:
            params = {"type": "object", "properties": {}}
        if name in SEARCH_TOOL_NAMES:
            params = ensure_search_schema(params)
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": tool.get("description") or search_tool_description(name),
                "parameters": params,
            },
        })
    if tools:
        out["tools"] = tools
    choice = tool_choice(inbound.get("toolChoice"))
    if choice is not None:
        out["tool_choice"] = choice
    return out


def convert_message(msg: dict) -> tuple[list[dict], bool]:
    role = (msg or {}).get("role") or ""
    raw = msg.get("content")
    if raw is None:
        if not role:
            return [], False
        return [{"role": role}], False
    if isinstance(raw, str):
        return [{"role": role, "content": raw}], False
    if not isinstance(raw, list):
        raise TranslateError(f"{ERR_INVALID_BODY}: content must be a string or array")

    text: list[str] = []
    calls: list[dict] = []
    results: list[dict] = []
    had_non_text = False
    for part in raw:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type") or "text"
        if ptype in ("text", ""):
            text.append(part.get("text") or "")
        elif ptype == "tool-call":
            calls.append({
                "id": part.get("toolCallId") or "",
                "type": "function",
                "function": {
                    "name": part.get("toolName") or "",
                    "arguments": raw_to_arguments(part.get("input")),
                },
            })
        elif ptype == "tool-result":
            results.append({
                "id": part.get("toolCallId") or "",
                "name": part.get("toolName") or "",
                "content": tool_output_text(part.get("output")),
            })
        else:
            had_non_text = True

    if role == "tool" or (results and role != "assistant"):
        out = [{
            "role": "tool",
            "tool_call_id": r["id"],
            "content": r["content"],
        } for r in results]
        if not out:
            out = [{"role": "tool", "content": "".join(text)}]
        return out, False

    image_only = had_non_text and not "".join(text) and not calls
    converted: dict[str, Any] = {"role": role, "content": "".join(text)}
    if calls:
        converted["tool_calls"] = calls
    return [converted], image_only


def raw_to_arguments(raw: Any) -> str:
    if raw is None:
        return "{}"
    if isinstance(raw, str):
        return raw
    return json.dumps(raw, separators=(",", ":"))


def tool_output_text(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        if raw.get("value"):
            return str(raw["value"])
        return json.dumps(raw, separators=(",", ":"))
    return str(raw)


def tool_choice(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw or None
    if isinstance(raw, dict):
        t = raw.get("type") or ""
        if t in ("auto", "required", "none"):
            return t
    return None


# ---------------------------------------------------------------------------
# translate: Gateway request → OpenAI Responses API
# ---------------------------------------------------------------------------

def responses_request(model: str, stream: bool, body: bytes) -> dict[str, Any]:
    """Same inbound Gateway body, outbound /v1/responses.

    store is always false: a coding-agent sandbox should not leave prompts
    on the provider's servers.
    """
    out = responses_from_chat(chat_request(model, stream, body))
    try:
        inbound = json.loads(body.decode() if body else b"{}")
    except json.JSONDecodeError:
        inbound = {}
    reasoning = _responses_reasoning(inbound if isinstance(inbound, dict) else {})
    if reasoning:
        out["reasoning"] = reasoning
    return out


def responses_from_chat(chat: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "model": chat["model"],
        "stream": bool(chat.get("stream")),
        "store": False,
        "input": chat_messages_to_input(chat.get("messages") or []),
    }
    if chat.get("max_tokens"):
        out["max_output_tokens"] = chat["max_tokens"]
    tools = []
    for tool in chat.get("tools") or []:
        fn = (tool or {}).get("function") or {}
        name = fn.get("name") or ""
        if not name:
            continue
        tools.append({
            "type": "function",
            "name": name,
            "description": fn.get("description") or "",
            "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    if tools:
        out["tools"] = tools
    if chat.get("tool_choice") is not None:
        out["tool_choice"] = chat["tool_choice"]
    return out


def _responses_reasoning(inbound: dict) -> Optional[dict]:
    r = (inbound or {}).get("reasoning")
    if r in (None, "", False):
        return None
    if isinstance(r, dict):
        effort = str(r.get("effort") or r.get("level") or "").strip().lower()
        out: dict[str, Any] = {}
        if effort in _REASONING_EFFORT:
            out["effort"] = effort
        if r.get("summary") not in (None, ""):
            out["summary"] = r["summary"]
        return out or None
    if isinstance(r, str) and r.strip().lower() in _REASONING_EFFORT:
        return {"effort": r.strip().lower()}
    return None


def chat_messages_to_input(messages: list[dict]) -> list[dict]:
    """Chat Completions messages[] → Responses input[] items."""
    items: list[dict] = []
    for msg in messages or []:
        role = (msg or {}).get("role") or ""
        if role == "tool":
            items.append({
                "type": "function_call_output",
                "call_id": msg.get("tool_call_id") or "",
                "output": msg.get("content") or "",
            })
            continue
        content = msg.get("content") or ""
        calls = msg.get("tool_calls") or []
        if role in ("system", "user", "assistant") and (content or not calls):
            items.append({"role": role, "content": content})
        for tc in calls:
            fn = (tc or {}).get("function") or {}
            items.append({
                "type": "function_call",
                "call_id": tc.get("id") or "",
                "name": fn.get("name") or "",
                "arguments": fn.get("arguments") or "{}",
            })
    return items


def responses_to_chat(raw: bytes | str | dict) -> bytes:
    """Non-stream Responses JSON → the OpenAI chat shape fx's workers expect."""
    if isinstance(raw, dict):
        data = raw
    else:
        if isinstance(raw, bytes):
            raw = raw.decode()
        data = json.loads(raw or "{}")
    text: list[str] = []
    tool_calls: list[dict] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        t = item.get("type") or ""
        if t == "message":
            for part in item.get("content") or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in ("output_text", "text") and part.get("text"):
                    text.append(str(part["text"]))
        elif t == "function_call":
            tool_calls.append({
                "id": item.get("call_id") or item.get("id") or "",
                "type": "function",
                "function": {
                    "name": item.get("name") or "",
                    "arguments": item.get("arguments") or "{}",
                },
            })
    if not text and data.get("output_text"):
        text.append(str(data["output_text"]))
    finish = "tool_calls" if tool_calls else "stop"
    status = data.get("status") or ""
    if status == "incomplete":
        reason = str((data.get("incomplete_details") or {}).get("reason") or "")
        if "filter" in reason:
            finish = "content_filter"
        else:
            finish = "length"
    elif status == "failed":
        finish = "stop"
    msg: dict[str, Any] = {"role": "assistant", "content": "".join(text)}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    out: dict[str, Any] = {"choices": [{"finish_reason": finish, "message": msg}]}
    usage = data.get("usage") or {}
    pin = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    cout = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    if pin or cout:
        out["usage"] = {"prompt_tokens": pin, "completion_tokens": cout}
    return json.dumps(out, separators=(",", ":")).encode()


def responses_usage(resp_obj: dict) -> dict:
    usage = (resp_obj or {}).get("usage") or {}
    return {
        "prompt_tokens": int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
    }


def should_fallback_to_chat(code: int, body: bytes = b"") -> bool:
    """404/405/501, or a 400/422 that means 'this host has no /responses'."""
    if code in (404, 405, 501):
        return True
    if code not in (400, 422):
        return False
    text = (body or b"").decode("utf-8", "replace").lower()
    needles = (
        "unknown request url", "not found", "no route", "unrecognized",
        "invalid url", "unknown endpoint", "unknown path", "/chat/completions",
        "does not support", "not supported",
        "unknown parameter", "unknown field", "unexpected keyword",
        "extra inputs are not permitted",
    )
    return any(n in text for n in needles)


# ---------------------------------------------------------------------------
# translate: OpenAI SSE → Gateway events
# ---------------------------------------------------------------------------

def unified_finish(reason: str) -> str:
    return {
        "stop": "stop",
        "length": "length",
        "content_filter": "content-filter",
        "tool_calls": "tool-calls",
        "error": "error",
    }.get(reason, "other")


# Shell names models often emit; fx 0.0.4's catalog uses `terminal`.
TOOL_NAME_ALIASES = {
    "bash": "terminal",
    "shell": "terminal",
    "run_command": "terminal",
    "command": "terminal",
    "exec": "terminal",
    "read": "read_file",
    "write": "write_file",
    "edit": "edit_file",
    "grep": "grep_files",
    "glob": "glob_files",
    "ls": "list_files",
    "list": "list_files",
    "fetch": "web_fetch",
}
SEARCH_TOOL_NAMES = {"perplexity_search", "web_search", "search_web"}


def search_tool_description(name: str) -> str:
    if name in SEARCH_TOOL_NAMES:
        return "Search the public web. Pass {\"query\": \"...\"}."
    return ""


def ensure_search_schema(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        params = {"type": "object", "properties": {}}
    else:
        params = dict(params)
    props = params.get("properties")
    if not isinstance(props, dict):
        props = {}
    else:
        props = dict(props)
    if "query" not in props:
        props["query"] = {
            "type": "string",
            "description": "Search query. Required. At least two characters.",
        }
        req = [r for r in (params.get("required") or []) if r]
        if "query" not in req:
            params["required"] = req + ["query"]
    params["properties"] = props
    if not params.get("type"):
        params["type"] = "object"
    return params


def canonical_tool_name(name: str, allowed: Optional[list[str]] = None) -> str:
    raw = (name or "").strip()
    if not raw:
        return raw
    allow = {a for a in (allowed or []) if a}
    if raw in SEARCH_TOOL_NAMES:
        if "perplexity_search" in allow:
            return "perplexity_search"
        if raw in allow:
            return raw
        if "web_search" in allow:
            return "web_search"
        return "perplexity_search"
    if raw in allow:
        return raw
    alias = TOOL_NAME_ALIASES.get(raw) or TOOL_NAME_ALIASES.get(raw.lower())
    if alias and (not allow or alias in allow):
        return alias
    return raw


def perplexity_api_key() -> str:
    load_env_file()
    return (os.environ.get("PERPLEXITY_API_KEY") or "").strip()


def vercel_gateway_key() -> str:
    """A real vck_ key, even when the LLM is OpenRouter and fx sees AI_GATEWAY_API_KEY=local."""
    load_env_file()
    for k in ("VERCEL_AI_GATEWAY_API_KEY", "AI_GATEWAY_API_KEY"):
        v = (os.environ.get(k) or "").strip()
        if v.startswith("vck_"):
            return v
    return ""


def openrouter_api_key() -> str:
    load_env_file()
    for k in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        v = (os.environ.get(k) or "").strip()
        if v.startswith("sk-or"):
            return v
    return ""


def remember_vercel_key(key: str = "") -> str:
    """Keep a vck_ so web search can use AI Gateway after switching LLM providers."""
    key = (key or "").strip()
    if not key.startswith("vck_"):
        key = vercel_gateway_key()
    if not key.startswith("vck_"):
        return ""
    upsert_env({"VERCEL_AI_GATEWAY_API_KEY": key})
    os.environ["VERCEL_AI_GATEWAY_API_KEY"] = key
    return key


def _search_query_from_input(inp: Any, fallback_query: str = "") -> str:
    if not isinstance(inp, dict):
        inp = {}
    query = str(inp.get("query") or inp.get("q") or inp.get("search") or "").strip()
    if not query:
        for key, val in inp.items():
            if key in ("maxResults", "max_results", "maxTokens", "max_tokens"):
                continue
            if isinstance(val, str) and len(val.strip()) >= 2:
                query = val.strip()
                break
    if not query:
        query = str(fallback_query or "").strip()
    return query


def _normalize_search_hits(query: str, rows: Any, limit: int) -> dict[str, Any]:
    if not isinstance(rows, list):
        return {"error": "search returned no results"}
    out = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        out.append({
            "title": row.get("title") or "",
            "url": row.get("url") or "",
            "snippet": str(row.get("snippet") or "")[:800],
            "date": row.get("date") or row.get("last_updated") or row.get("lastUpdated") or "",
        })
    return {"query": query, "results": out, "source": "perplexity"}


SEARCH_NO_KEY = (
    "Web search needs a Perplexity API key (pplx-…), a billed Vercel AI Gateway key (vck_…), "
    "or an OpenRouter key. Add one in Settings → Provider."
)
GATEWAY_SEARCH_URL = "https://ai-gateway.vercel.sh/v3/ai/language-model"
GATEWAY_PROTOCOL_VERSION = "0.0.1"
GATEWAY_SPEC_VERSION = "3"
GATEWAY_CARD_HINT = (
    "Vercel AI Gateway needs a credit card on the Vercel account to run search. "
    "Add a card at vercel.com, or paste a Perplexity API key (pplx-…) in "
    "Settings → Provider → Web search. Do not fetch search-engine HTML pages."
)


def _gateway_search_headers(key: str, model: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "ai-language-model-id": model,
        "ai-language-model-streaming": "true",
        "ai-language-model-specification-version": GATEWAY_SPEC_VERSION,
        "ai-gateway-protocol-version": GATEWAY_PROTOCOL_VERSION,
    }


def _gateway_http_error(exc: urllib.error.HTTPError) -> str:
    raw = exc.read().decode("utf-8", "replace")[:500]
    msg = raw
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                msg = str(err.get("message") or err.get("code") or raw)
            elif isinstance(err, str):
                msg = err
    except json.JSONDecodeError:
        pass
    low = (msg + " " + raw).lower()
    if exc.code in (401, 403) and (
        "credit card" in low or "customer_verification" in low
    ):
        return GATEWAY_CARD_HINT
    return f"Vercel AI Gateway search failed (HTTP {exc.code}). {msg}"


def _search_has_hits(out: Any) -> bool:
    return isinstance(out, dict) and isinstance(out.get("results"), list) and bool(out["results"])


def run_perplexity_search(inp: Any, fallback_query: str = "") -> dict[str, Any]:
    """pplx- first, then Vercel Gateway, then OpenRouter web search. Never raises."""
    if not isinstance(inp, dict):
        inp = {}
    query = _search_query_from_input(inp, fallback_query)
    if not query:
        return {"error": "search query is required"}
    raw_n = inp.get("maxResults") or inp.get("max_results") or 5
    try:
        max_results = max(1, min(int(raw_n), 20))
    except (TypeError, ValueError):
        max_results = 5
    last: dict[str, Any] = {"error": SEARCH_NO_KEY}
    if perplexity_api_key():
        last = run_direct_perplexity_search(query, max_results)
        if _search_has_hits(last):
            return last
    if vercel_gateway_key():
        last = run_gateway_search(query, max_results)
        if _search_has_hits(last):
            return last
    if openrouter_api_key():
        last = run_openrouter_search(query, max_results)
        if _search_has_hits(last):
            return last
    return last


def run_direct_perplexity_search(query: str, max_results: int = 5) -> dict[str, Any]:
    key = perplexity_api_key()
    if not key:
        return {"error": SEARCH_NO_KEY}
    body = json.dumps({"query": query, "max_results": max_results}).encode()
    req = urllib.request.Request(
        "https://api.perplexity.ai/search",
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")[:300]
        return {"error": f"Perplexity search failed (HTTP {e.code}). {err}"}
    except Exception as e:
        return {"error": f"Perplexity search failed. {e}"}
    rows = data.get("results") if isinstance(data, dict) else None
    out = _normalize_search_hits(query, rows, max_results)
    if "results" in out:
        out["source"] = "perplexity"
    return out


def _gateway_search_body(query: str, max_results: int) -> bytes:
    return json.dumps({
        "prompt": [{
            "role": "user",
            "content": [{
                "type": "text",
                "text": "Call perplexity_search once with query " + json.dumps(query) + ". Do not answer otherwise.",
            }],
        }],
        "tools": [{
            "type": "provider",
            "id": "gateway.perplexity_search",
            "name": "perplexity_search",
            "args": {"maxResults": max_results},
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "number"},
                },
                "required": ["query"],
            },
        }],
        "toolChoice": {"type": "tool", "toolName": "perplexity_search"},
        "maxOutputTokens": 512,
    }, separators=(",", ":")).encode()


def _is_search_tool_name(name: str) -> bool:
    n = (name or "").strip()
    if not n:
        return False
    if n in SEARCH_TOOL_NAMES:
        return True
    low = n.lower()
    return "perplexity_search" in low or low in ("search", "websearch")


def _tool_result_from_gateway_event(obj: Any) -> Optional[dict[str, Any]]:
    if not isinstance(obj, dict):
        return None
    if obj.get("type") not in ("tool-result", "tool-output-available"):
        return None
    name = obj.get("toolName") or obj.get("name") or ""
    if name and not _is_search_tool_name(str(name)):
        return None
    raw = obj.get("output")
    if raw is None:
        raw = obj.get("result")
    if isinstance(raw, dict) and isinstance(raw.get("value"), dict):
        raw = raw["value"]
    elif isinstance(raw, dict) and isinstance(raw.get("value"), list):
        raw = {"results": raw["value"]}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {"error": raw[:400]}
    if isinstance(raw, list):
        return {"results": raw}
    if isinstance(raw, dict):
        return raw
    return None


def run_gateway_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Ask Vercel AI Gateway to execute perplexity_search. Never raises."""
    key = vercel_gateway_key()
    if not key:
        return {"error": SEARCH_NO_KEY}
    gateway_is_active = not bool(configured_upstream())
    resolution = search_policy.resolve_vercel_search_model(
        key,
        current_provider_is_vercel=gateway_is_active,
        current_model=(os.environ.get("FX_MODEL") or "") if gateway_is_active else "",
    )
    if not resolution.model:
        low = (resolution.error or "").lower()
        if "credit card" in low or "customer_verification" in low:
            return {"error": GATEWAY_CARD_HINT}
        detail = resolution.error or "could not resolve a tool-capable Gateway worker"
        return {"error": "Vercel AI Gateway search unavailable. " + detail}
    req = urllib.request.Request(
        GATEWAY_SEARCH_URL,
        data=_gateway_search_body(query, max_results),
        method="POST",
        headers=_gateway_search_headers(key, resolution.model),
    )
    try:
        resp = urllib.request.urlopen(req, timeout=45)
    except urllib.error.HTTPError as e:
        return {"error": _gateway_http_error(e)}
    except Exception as e:
        return {"error": f"Vercel AI Gateway search failed. {e}"}
    found: Optional[dict[str, Any]] = None
    try:
        for data in read_sse_data(resp):
            if not data or data.strip() == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            parsed = _tool_result_from_gateway_event(obj)
            if parsed is not None:
                found = parsed
                break
    except Exception as e:
        return {"error": f"Vercel AI Gateway search failed. {e}"}
    finally:
        try:
            resp.close()
        except Exception:
            pass
    if found is None:
        return {"error": "Vercel AI Gateway did not run web search."}
    if found.get("error") and not found.get("results"):
        msg = found.get("message") or found.get("error")
        return {"error": f"Vercel AI Gateway search failed. {msg}"}
    rows = found.get("results") if isinstance(found.get("results"), list) else None
    if rows is None:
        return found if found.get("query") or found.get("results") else {"error": "Vercel AI Gateway returned no results"}
    out = _normalize_search_hits(query, rows, max_results)
    out["source"] = "vercel-gateway"
    return out


def _openrouter_search_model() -> str:
    up = configured_upstream()
    if provider_id_for(up) == "openrouter":
        m = (os.environ.get("FX_MODEL") or "").strip()
        if m:
            return m
    return "stealth/ox-alpha"


def _hits_from_openrouter(data: Any, query: str, limit: int) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"error": "OpenRouter search returned no results"}
    if data.get("error"):
        err = data["error"]
        if isinstance(err, dict):
            err = err.get("message") or err
        return {"error": f"OpenRouter search failed. {err}"}
    choice = (data.get("choices") or [{}])[0] or {}
    msg = choice.get("message") or {}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ann in msg.get("annotations") or []:
        if not isinstance(ann, dict):
            continue
        cit = ann.get("url_citation") if isinstance(ann.get("url_citation"), dict) else None
        if not cit:
            continue
        url = str(cit.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        rows.append({
            "title": cit.get("title") or "",
            "url": url,
            "snippet": str(cit.get("content") or cit.get("snippet") or "")[:800],
            "date": cit.get("date") or "",
        })
        if len(rows) >= limit:
            break
    if rows:
        return {"query": query, "results": rows, "source": "openrouter"}
    raw = msg.get("content")
    if isinstance(raw, str) and raw.strip().startswith("["):
        try:
            parsed = json.loads(raw.strip())
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            out = _normalize_search_hits(query, parsed, limit)
            if _search_has_hits(out):
                out["source"] = "openrouter"
                return out
    return {"error": "OpenRouter search returned no results"}


def run_openrouter_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """OpenRouter server-side web search using the saved sk-or key. Never raises."""
    key = openrouter_api_key()
    if not key:
        return {"error": SEARCH_NO_KEY}
    body = json.dumps({
        "model": _openrouter_search_model(),
        "stream": False,
        "max_tokens": 256,
        "messages": [{
            "role": "user",
            "content": "Search the web for " + json.dumps(query) + ". Use the web search tool.",
        }],
        "tools": [{
            "type": "openrouter:web_search",
            "parameters": {"max_results": max_results},
        }],
        "tool_choice": "required",
    }, separators=(",", ":")).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "HTTP-Referer": "https://fxs.local",
            "X-Title": "fxs",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")[:300]
        return {"error": f"OpenRouter search failed (HTTP {e.code}). {err}"}
    except Exception as e:
        return {"error": f"OpenRouter search failed. {e}"}
    return _hits_from_openrouter(data, query, max_results)


class Stream:
    def __init__(self, allowed_tools: Optional[list[str]] = None) -> None:
        self.tools: dict[int, dict[str, Any]] = {}
        self.order: list[int] = []
        self.finished = False
        self.allowed_tools = list(allowed_tools or [])

    def consume(self, data: bytes | str) -> list[bytes]:
        if isinstance(data, str):
            data = data.encode()
        data = data.strip()
        if not data or data == b"[DONE]":
            return []
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            return []
        events: list[bytes] = []
        err = chunk.get("error")
        if err not in (None, "", {}, []):
            events.append(_j({"type": "error", "error": err}))
        choices = chunk.get("choices") or []
        if not choices:
            return events
        choice = choices[0]
        delta = choice.get("delta") or {}
        content = delta.get("content") or ""
        if content:
            events.append(_j({"type": "text-delta", "delta": content}))
        # OpenRouter stealth models stream `reasoning` before tool_calls.
        # fx treats an open reasoning part as MalformedProviderResultIdentity
        # when a tool-input-start follows, so we do not forward it.
        calls = delta.get("tool_calls") or (choice.get("message") or {}).get("tool_calls") or []
        for call in calls:
            idx = int(call.get("index") or 0)
            acc = self._tool(idx)
            if call.get("id"):
                acc["id"] = call["id"]
            elif not acc["id"]:
                acc["id"] = f"call_{idx}"
            fn = call.get("function") or {}
            if fn.get("name"):
                acc["name"] = canonical_tool_name(fn["name"], self.allowed_tools)
            if not acc["started"] and acc["id"] and acc["name"]:
                acc["started"] = True
                events.append(_j({
                    "type": "tool-input-start",
                    "id": acc["id"],
                    "toolName": acc["name"],
                }))
            args = fn.get("arguments") or ""
            if args:
                acc["args"] += args
                if acc["started"]:
                    events.append(_j({
                        "type": "tool-input-delta",
                        "id": acc["id"],
                        "delta": args,
                    }))
        if choice.get("finish_reason"):
            events.extend(self._finalize(choice["finish_reason"], chunk.get("usage") or {}))
        return events

    def close(self) -> list[bytes]:
        if self.finished:
            return []
        return self._finalize("stop", {})

    def fail(self, msg: str = "") -> list[bytes]:
        if not msg:
            msg = "upstream stream interrupted"
        err = _j({"type": "error", "error": msg})
        if self.finished:
            return [err]
        self.finished = True
        return [err, _j({"type": "finish", "finishReason": {"unified": "error"}})]

    def search_calls(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for idx in self.order:
            acc = self.tools.get(idx)
            if not acc or not acc.get("id"):
                continue
            name = acc.get("name") or ""
            if name not in SEARCH_TOOL_NAMES:
                continue
            try:
                parsed = json.loads(acc.get("args") or "{}")
            except json.JSONDecodeError:
                parsed = {}
            if not isinstance(parsed, dict):
                parsed = {}
            out.append({"id": acc["id"], "name": name, "input": parsed})
        return out

    def has_client_tools(self) -> bool:
        search_ids = {t["id"] for t in self.search_calls()}
        for idx in self.order:
            acc = self.tools.get(idx)
            if acc and acc.get("id") and acc["id"] not in search_ids:
                return True
        return False

    def _finalize(self, reason: str, usage: dict) -> list[bytes]:
        if self.finished:
            return []
        self.finished = True
        events: list[bytes] = []
        for idx in self.order:
            acc = self.tools.get(idx)
            if not acc or not acc.get("id"):
                continue
            if acc.get("started"):
                events.append(_j({"type": "tool-input-end", "id": acc["id"]}))
            args = acc.get("args") or "{}"
            try:
                parsed = json.loads(args)
                if not isinstance(parsed, dict):
                    raise ValueError("not object")
                events.append(_j({
                    "type": "tool-call",
                    "toolCallId": acc["id"],
                    "toolName": acc.get("name") or "",
                    "input": parsed,
                }))
            except (json.JSONDecodeError, ValueError):
                events.append(_j({"type": "error", "error": "tool arguments are not valid JSON"}))
        finish: dict[str, Any] = {
            "type": "finish",
            "finishReason": {"unified": unified_finish(reason)},
        }
        pin = int(usage.get("prompt_tokens") or 0)
        cout = int(usage.get("completion_tokens") or 0)
        if pin or cout:
            finish["usage"] = {
                "inputTokens": {"total": pin},
                "outputTokens": {"total": cout},
            }
        events.append(_j(finish))
        return events

    def _tool(self, index: int) -> dict[str, Any]:
        acc = self.tools.get(index)
        if acc is None:
            acc = {"id": "", "name": "", "args": "", "started": False}
            self.tools[index] = acc
            self.order.append(index)
        return acc


class ResponseStream(Stream):
    """OpenAI Responses SSE (`response.output_text.delta`, …) → Gateway events."""

    def __init__(self, allowed_tools: Optional[list[str]] = None) -> None:
        super().__init__(allowed_tools)
        self.ids: dict[str, str] = {}  # item_id → call_id

    def consume(self, data: bytes | str) -> list[bytes]:
        if isinstance(data, str):
            data = data.encode()
        data = data.strip()
        if not data or data == b"[DONE]":
            return []
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            return []
        if not isinstance(chunk, dict):
            return []
        t = chunk.get("type") or ""
        events: list[bytes] = []
        if t == "error" or chunk.get("error") not in (None, "", {}, []) and t in ("error", "response.failed", ""):
            err = chunk.get("error") or chunk.get("message") or chunk
            events.append(_j({"type": "error", "error": err}))
            if t == "response.failed":
                events.extend(self._finalize("error", responses_usage(chunk.get("response") or {})))
            return events
        if t in ("response.output_text.delta", "response.refusal.delta"):
            delta = chunk.get("delta") or ""
            if delta:
                events.append(_j({"type": "text-delta", "delta": delta}))
            return events
        if t in (
            "response.reasoning_summary_text.delta",
            "response.reasoning_text.delta",
            "response.reasoning.delta",
        ):
            delta = chunk.get("delta") or ""
            if delta:
                events.append(_j({"type": "reasoning-delta", "delta": delta}))
            return events
        if t == "response.output_item.added":
            events.extend(self._item_added(chunk.get("item") or {}))
            return events
        if t == "response.output_item.done":
            events.extend(self._item_done(chunk.get("item") or {}))
            return events
        if t == "response.function_call_arguments.delta":
            acc = self._acc_for(chunk)
            args = chunk.get("delta") or ""
            if args:
                acc["args"] += args
                if acc["started"]:
                    events.append(_j({
                        "type": "tool-input-delta",
                        "id": acc["id"],
                        "delta": args,
                    }))
            return events
        if t == "response.function_call_arguments.done":
            acc = self._acc_for(chunk)
            final = chunk.get("arguments")
            if isinstance(final, str) and final and not acc["args"]:
                acc["args"] = final
            return events
        if t == "response.completed":
            resp = chunk.get("response") or {}
            events.extend(self._harvest_output(resp.get("output") or []))
            events.extend(self._finalize(self._reason_from(resp), responses_usage(resp)))
            return events
        if t == "response.incomplete":
            resp = chunk.get("response") or {}
            events.extend(self._harvest_output(resp.get("output") or []))
            events.extend(self._finalize(self._reason_from(resp), responses_usage(resp)))
            return events
        if t == "response.failed":
            resp = chunk.get("response") or {}
            err = (resp.get("error") or chunk.get("error") or "upstream failed")
            events.append(_j({"type": "error", "error": err}))
            events.extend(self._finalize("error", responses_usage(resp)))
            return events
        return events

    def _reason_from(self, resp: dict) -> str:
        status = (resp or {}).get("status") or ""
        if status == "failed":
            return "error"
        if status == "incomplete":
            reason = str(((resp or {}).get("incomplete_details") or {}).get("reason") or "")
            if "filter" in reason:
                return "content_filter"
            return "length"
        if self.order:
            return "tool_calls"
        return "stop"

    def _item_added(self, item: dict) -> list[bytes]:
        if (item or {}).get("type") != "function_call":
            return []
        call_id = item.get("call_id") or item.get("id") or ""
        item_id = item.get("id") or ""
        if item_id and call_id:
            self.ids[item_id] = call_id
        acc = self._named(call_id or item_id)
        if call_id:
            acc["id"] = call_id
        if item.get("name"):
            acc["name"] = canonical_tool_name(item["name"], self.allowed_tools)
        if item.get("arguments"):
            acc["args"] += item["arguments"]
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

    def _item_done(self, item: dict) -> list[bytes]:
        if (item or {}).get("type") != "function_call":
            return []
        call_id = item.get("call_id") or item.get("id") or ""
        item_id = item.get("id") or ""
        acc = None
        if call_id:
            acc = self.tools.get(call_id)
        if acc is None and item_id:
            acc = self.tools.get(self.ids.get(item_id, item_id))
        if acc and acc.get("started"):
            if item.get("arguments") and not acc["args"]:
                acc["args"] = item["arguments"]
            return []
        return self._item_added(item)

    def _harvest_output(self, output: list) -> list[bytes]:
        """Catch function_call items that never streamed argument deltas."""
        events: list[bytes] = []
        for item in output or []:
            if not isinstance(item, dict) or item.get("type") != "function_call":
                continue
            call_id = item.get("call_id") or item.get("id") or ""
            acc = self.tools.get(call_id) if call_id else None
            if acc and acc.get("started"):
                continue
            events.extend(self._item_added(item))
        return events

    def _acc_for(self, chunk: dict) -> dict[str, Any]:
        item_id = chunk.get("item_id") or ""
        call_id = chunk.get("call_id") or self.ids.get(item_id) or item_id
        if item_id and call_id:
            self.ids[item_id] = call_id
        return self._named(call_id)

    def _named(self, key: str) -> dict[str, Any]:
        key = key or f"anon{len(self.order)}"
        acc = self.tools.get(key)
        if acc is None:
            acc = {"id": key, "name": "", "args": "", "started": False}
            self.tools[key] = acc
            self.order.append(key)
        if not acc["id"]:
            acc["id"] = key
        return acc


def _sse_payload(event: str, buf: list[str]) -> str:
    payload = "\n".join(buf)
    if event and payload and payload.strip() != "[DONE]":
        try:
            obj = json.loads(payload)
            if isinstance(obj, dict) and not obj.get("type"):
                obj["type"] = event
                return json.dumps(obj, separators=(",", ":"))
        except json.JSONDecodeError:
            pass
    return payload


def read_sse_data(resp) -> Iterable[str]:
    """Yield SSE data payloads. Prefer JSON `type`; fall back to `event:`."""
    buf: list[str] = []
    event = ""
    while True:
        raw = resp.readline()
        if not raw:
            if buf:
                yield _sse_payload(event, buf)
            return
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if line == "":
            if buf:
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


def _j(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode()


def last_user_text(messages: list[dict]) -> str:
    for msg in reversed(messages or []):
        if (msg or {}).get("role") != "user":
            continue
        raw = msg.get("content")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, list):
            parts = [str(p.get("text") or "") for p in raw if isinstance(p, dict)]
            text = "".join(parts).strip()
            if text:
                return text
    return ""


def mark_search_events(events: Iterable[bytes], search_ids: set[str]) -> list[bytes]:
    """Drop provider-search events so fx never sees a Vercel-only tool identity."""
    out: list[bytes] = []
    for ev in events:
        try:
            obj = json.loads(ev)
        except json.JSONDecodeError:
            out.append(ev)
            continue
        t = obj.get("type") or ""
        if t == "tool-input-start" and obj.get("toolName") in SEARCH_TOOL_NAMES:
            continue
        if t in ("tool-input-delta", "tool-input-end") and obj.get("id") in search_ids:
            continue
        if t == "tool-call" and (
            obj.get("toolCallId") in search_ids or obj.get("toolName") in SEARCH_TOOL_NAMES
        ):
            continue
        if t == "finish" and search_ids:
            continue
        out.append(ev)
    return out


def write_sse(event: bytes) -> bytes:
    return b"data: " + event + b"\n\n"


# ---------------------------------------------------------------------------
# upstream HTTP
# ---------------------------------------------------------------------------

class _BufferedResp:
    """Replay a body we already consumed (fallback / error path)."""

    def __init__(self, code: int, body: bytes, ctype: str = "application/json"):
        self.status = code
        self.code = code
        self.headers = {"Content-Type": ctype}
        self._body = body

    def read(self, n: int = -1) -> bytes:
        return self._body

    def readline(self, n: int = -1) -> bytes:
        return b""

    def close(self) -> None:
        return None


class Upstream:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 600,
        api: str = "auto",
        provider_id: str = "",
    ) -> None:
        self.base = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.api = api or "auto"  # auto | chat | responses
        self.provider_id = provider_id or provider_id_for(base_url)
        self._force_chat = False

    def use_responses(self) -> bool:
        if self._force_chat:
            return False
        return effective_api(self.provider_id, self.api) == "responses"

    def models(self):
        return self._do("GET", self.base + "/models", None, False, timeout=30)

    def chat(self, req: dict):
        body = json.dumps(req).encode()
        return self._do("POST", self.base + "/chat/completions", body, bool(req.get("stream")))

    def responses(self, req: dict):
        body = json.dumps(req).encode()
        return self._do("POST", self.base + "/responses", body, bool(req.get("stream")))

    def complete(self, chat_req: dict, responses_req: dict):
        """POST /responses or /chat/completions. Auto falls back to chat on 404."""
        if not self.use_responses():
            return self.chat(chat_req), False
        if not responses_req:
            responses_req = responses_from_chat(chat_req)
        resp = self.responses(responses_req)
        code = getattr(resp, "status", None) or getattr(resp, "code", 200)
        if self.api == "auto" and code != 200:
            peek = b""
            try:
                peek = resp.read()
            except Exception:
                peek = b""
            try:
                resp.close()
            except Exception:
                pass
            if should_fallback_to_chat(code, peek):
                self._force_chat = True
                sys.stderr.write("fxs-gateway: /responses missing — falling back to /chat/completions\n")
                return self.chat(chat_req), False
            # Not a fallback case (401, 400-invalid-body, …): re-wrap the body.
            return _BufferedResp(code, peek), True
        return resp, True

    def _do(self, method: str, url: str, body: Optional[bytes], stream: bool, timeout: Optional[int] = None):
        headers = {"User-Agent": USER_AGENT}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if stream:
            headers["Accept"] = "text/event-stream"
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        host = (urlparse(self.base).hostname or "").lower()
        if "openrouter.ai" in host:
            headers["HTTP-Referer"] = "https://github.com/da-beda/fx-sandbox"
            headers["X-Title"] = "fxs"
        r = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            return urllib.request.urlopen(r, timeout=timeout if timeout is not None else self.timeout)
        except urllib.error.HTTPError as e:
            return e


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------

def require_loopback(addr: str) -> None:
    host, sep, port = addr.rpartition(":")
    if not sep or not port:
        raise ValueError(f"listen {addr!r}: port required")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if host in ("localhost", "127.0.0.1", "::1"):
        return
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as e:
        raise ValueError(f"listen {addr!r}: {e}") from e
    for info in infos:
        ip = info[4][0]
        if ip.startswith("127.") or ip in ("::1", "0:0:0:0:0:0:0:1"):
            return
    raise ValueError(f"listen must be loopback (127.0.0.1, localhost, ::1), got {addr!r}")


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = USER_AGENT
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("fxs-gateway: " + (fmt % args) + "\n")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, code: int, obj: Any) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] == "/healthz":
            self._send(200, b"ok\n", "text/plain; charset=utf-8")
            return
        if self.path.startswith("/coding-agent/v1/credits"):
            self._json(404, {"error": "not found"})
            return
        if self.path.startswith("/coding-agent/v1/models"):
            self._models()
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] == "/v3/ai/language-model":
            self._language_model()
            return
        self._json(404, {"error": "not found"})

    def _models(self) -> None:
        up: Upstream = self.server.upstream  # type: ignore[attr-defined]
        try:
            resp = up.models()
        except Exception as e:
            self._json(502, {"error": str(e)})
            return
        try:
            body = resp.read()
            code = getattr(resp, "status", None) or getattr(resp, "code", 200)
            if code != 200:
                self._send(code, body, resp.headers.get("Content-Type") or "application/json")
                return
            try:
                out = catalog(body)
            except Exception as e:
                self._json(502, {"error": "upstream models: " + str(e)})
                return
            self._send(200, out, "application/json")
        finally:
            try:
                resp.close()
            except Exception:
                pass

    def _language_model(self) -> None:
        model = self.headers.get("ai-language-model-id") or ""
        stream = (self.headers.get("ai-language-model-streaming") or "").lower() == "true"
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            chat_req = chat_request(model, stream, raw)
        except TranslateError as e:
            self._json(400, {"error": str(e)})
            return
        up: Upstream = self.server.upstream  # type: ignore[attr-defined]
        resp_req = responses_from_chat(chat_req) if up.use_responses() else {}
        try:
            inbound = json.loads(raw.decode() if raw else b"{}")
        except json.JSONDecodeError:
            inbound = {}
        allowed = [
            str(t.get("name") or "")
            for t in (inbound.get("tools") or [])
            if isinstance(t, dict) and t.get("name")
        ]
        if resp_req:
            reasoning = _responses_reasoning(inbound if isinstance(inbound, dict) else {})
            if reasoning:
                resp_req["reasoning"] = reasoning
        try:
            resp, used_responses = up.complete(chat_req, resp_req)
        except Exception as e:
            self._json(502, {"error": str(e)})
            return
        try:
            code = getattr(resp, "status", None) or getattr(resp, "code", 200)
            if code != 200:
                body = resp.read()
                msg = upstream_http_error(code, body)
                if stream:
                    try:
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.send_header("Cache-Control", "no-cache")
                        self.send_header("Connection", "close")
                        self.end_headers()
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    conv: Stream = Stream(allowed)
                    self._write_events(conv.fail(msg))
                    self.close_connection = True
                    return
                self._json(502, {"error": msg})
                return
            if not stream:
                body = resp.read()
                if used_responses:
                    try:
                        body = responses_to_chat(body)
                    except Exception:
                        pass
                ctype = "application/json"
                self._send(200, body, ctype)
                return
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
            except (BrokenPipeError, ConnectionResetError):
                return
            conv: Stream = ResponseStream(allowed) if used_responses else Stream(allowed)
            try:
                self._stream_with_search(up, chat_req, resp_req, resp, used_responses, allowed, conv)
            except Exception as e:
                self._write_events(Stream(allowed).fail(str(e)))
            self.close_connection = True
        finally:
            try:
                resp.close()
            except Exception:
                pass

    def _write_search_events(self, events: Iterable[bytes], conv: "Stream") -> None:
        ids = {t["id"] for t in conv.search_calls()}
        self._write_events(mark_search_events(events, ids))

    def _stream_with_search(
        self,
        up: "Upstream",
        chat_req: dict,
        resp_req: dict,
        resp: Any,
        used_responses: bool,
        allowed: list[str],
        conv: "Stream",
    ) -> None:
        messages = list(chat_req.get("messages") or [])
        first = True
        for _round in range(6):
            if not first:
                chat_req = dict(chat_req)
                chat_req["messages"] = messages
                next_resp_req = responses_from_chat(chat_req) if up.use_responses() else {}
                try:
                    resp, used_responses = up.complete(chat_req, next_resp_req)
                except Exception as e:
                    self._write_events(Stream(allowed).fail(str(e)))
                    return
                code = getattr(resp, "status", None) or getattr(resp, "code", 200)
                if code != 200:
                    body = resp.read()
                    msg = upstream_http_error(code, body)
                    self._write_events(Stream(allowed).fail(msg))
                    return
                conv = ResponseStream(allowed) if used_responses else Stream(allowed)
            first = False
            try:
                for data in read_sse_data(resp):
                    if data.strip() == "[DONE]":
                        break
                    self._write_search_events(conv.consume(data), conv)
                self._write_search_events(conv.close(), conv)
            except Exception as e:
                self._write_events(conv.fail(str(e)))
                return
            finally:
                try:
                    resp.close()
                except Exception:
                    pass
            searches = conv.search_calls()
            if not searches:
                return
            fallback = last_user_text(messages)
            assistant: dict[str, Any] = {"role": "assistant", "content": None, "tool_calls": []}
            tool_msgs: list[dict[str, Any]] = []
            for t in searches:
                result = run_perplexity_search(t["input"], fallback_query=fallback)
                assistant["tool_calls"].append({
                    "id": t["id"],
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "arguments": json.dumps(t["input"], separators=(",", ":")),
                    },
                })
                tool_msgs.append({
                    "role": "tool",
                    "tool_call_id": t["id"],
                    "content": json.dumps(result, separators=(",", ":")),
                })
            if conv.has_client_tools():
                self._write_events([_j({
                    "type": "finish",
                    "finishReason": {"unified": "tool-calls"},
                })])
                return
            messages = messages + [assistant] + tool_msgs
        self._write_events(Stream(allowed).fail("search loop exceeded"))

    def _write_events(self, events: Iterable[bytes]) -> None:
        try:
            for ev in events:
                self.wfile.write(write_sse(ev))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


class GatewayServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, listen: str, upstream: Upstream):
        host, _, port = listen.rpartition(":")
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        super().__init__((host, int(port)), GatewayHandler)
        self.upstream = upstream
        self.listen = listen


def serve(listen: str, base_url: str, api_key: str, api: str = "auto") -> None:
    require_loopback(listen)
    key = api_key or "ollama"
    pid = provider_id_for(base_url)
    try:
        api = normalize_api(api)
    except ValueError:
        api = "auto"
    mode = effective_api(pid, api)
    srv = GatewayServer(
        listen,
        Upstream(base_url, key, api=api, provider_id=pid),
    )
    sys.stderr.write(f"fxs-gateway: http://{listen}  →  {base_url.rstrip('/')}  [{mode}]\n")
    for line in print_env(listen).strip().splitlines():
        sys.stderr.write("fxs-gateway:   " + line + "\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


def print_env(listen: str = LISTEN_DEFAULT) -> str:
    base = "http://" + listen
    lines = [
        f"export FX_GATEWAY_BASE_URL={base}",
        f"export FX_GATEWAY_CHAT_URL={base}/v3/ai/language-model",
        "export AI_GATEWAY_API_KEY=${AI_GATEWAY_API_KEY:-local}",
    ]
    model = os.environ.get("FX_MODEL", "")
    if model:
        escaped = model.replace("'", "'\\''")
        lines.append(f"export FX_MODEL='{escaped}'")
    else:
        lines.append("# model: unset; the installed fx build chooses its native default.")
    return "\n".join(lines) + "\n"


def healthz_ok(listen: str, timeout: float = 0.4) -> bool:
    host, _, port = listen.rpartition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=timeout) as s:
            s.sendall(b"GET /healthz HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
            buf = b""
            while True:
                chunk = s.recv(1024)
                if not chunk:
                    break
                buf += chunk
                if b"\r\n\r\n" in buf:
                    break
        return b" 200 " in buf.split(b"\r\n", 1)[0] and b"ok" in buf.lower()
    except OSError:
        return False


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_gateway(listen: str = LISTEN_DEFAULT) -> None:
    if PID_FILE.is_file():
        try:
            pid = int(PID_FILE.read_text().strip() or "0")
        except ValueError:
            pid = 0
        if _pid_running(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        try:
            PID_FILE.unlink()
        except OSError:
            pass
    try:
        UPSTREAM_STAMP.unlink()
    except OSError:
        pass


def _gateway_stamp(upstream: str, api: str, api_key: str = "") -> str:
    return (
        f"{upstream.rstrip('/')}\n{api}\n{_key_fp(api_key)}\n"
        f"{_key_fp(perplexity_api_key())}\n{_key_fp(vercel_gateway_key())}\n"
    )


def _key_fp(key: str) -> str:
    if not key:
        return "-"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _stamp_matches(text: str, upstream: str, api: str, api_key: str = "") -> bool:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) < 3:
        return False
    if not (
        lines[0].rstrip("/") == upstream.rstrip("/")
        and lines[1] == api
        and lines[2] == _key_fp(api_key)
    ):
        return False
    have_pplx = lines[3] if len(lines) > 3 else "-"
    have_vck = lines[4] if len(lines) > 4 else "-"
    return have_pplx == _key_fp(perplexity_api_key()) and have_vck == _key_fp(vercel_gateway_key())


def ensure_gateway(
    listen: str = LISTEN_DEFAULT,
    upstream: str = "",
    api_key: str = "",
    script: Optional[Path] = None,
    api: str = "",
) -> dict[str, str]:
    """Start the translator if needed. Safe to call from fx / fxs / the UI."""
    load_env_file()
    upstream = (upstream or configured_upstream()).rstrip("/")
    if not upstream:
        return {"enabled": "0"}
    try:
        api = normalize_api(api or configured_api())
    except ValueError:
        api = "auto"
    api_key = api_key or api_key_from_env()
    pid = provider_id_for(upstream)
    if provider_needs_key(pid) and not api_key:
        label = PROVIDER_BY_ID.get(pid, {}).get("label") or pid
        raise RuntimeError(f"{label} needs an API key")
    api_key = api_key or "ollama"
    stamp = _gateway_stamp(upstream, api, api_key)
    if healthz_ok(listen):
        want = ""
        if UPSTREAM_STAMP.is_file():
            try:
                want = UPSTREAM_STAMP.read_text(encoding="utf-8")
            except OSError:
                want = ""
        if _stamp_matches(want, upstream, api, api_key):
            os.environ["FX_GATEWAY_BASE_URL"] = "http://" + listen
            os.environ["FX_GATEWAY_CHAT_URL"] = "http://" + listen + "/v3/ai/language-model"
            os.environ.setdefault("AI_GATEWAY_API_KEY", "local")
            return {
                "enabled": "1",
                "listen": listen,
                "upstream": upstream,
                "api": api,
                "env": print_env(listen),
            }
        stop_gateway(listen)
        time.sleep(0.15)

    script = script or Path(__file__).resolve()
    STATE_DIR.mkdir(parents=True, mode=0o700, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = api_key
    env["OPENAI_BASE_URL"] = upstream
    env["FX_UPSTREAM"] = upstream
    env["FX_UPSTREAM_API"] = api
    logf = open(LOG_FILE, "ab", buffering=0)
    proc = subprocess.Popen(
        [sys.executable, str(script), "--listen", listen, "--upstream", upstream, "--api", api],
        stdin=subprocess.DEVNULL,
        stdout=logf,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
        close_fds=True,
    )
    try:
        logf.close()
    except Exception:
        pass
    PID_FILE.write_text(str(proc.pid) + "\n", encoding="utf-8")
    try:
        os.chmod(PID_FILE, 0o600)
    except OSError:
        pass
    UPSTREAM_STAMP.write_text(stamp, encoding="utf-8")
    deadline = time.time() + 4.0
    while time.time() < deadline:
        if healthz_ok(listen):
            break
        if proc.poll() is not None:
            raise RuntimeError(f"gateway exited {proc.returncode}; see {LOG_FILE}")
        time.sleep(0.05)
    else:
        raise RuntimeError(f"gateway did not become ready on {listen}; see {LOG_FILE}")
    os.environ["FX_GATEWAY_BASE_URL"] = "http://" + listen
    os.environ["FX_GATEWAY_CHAT_URL"] = "http://" + listen + "/v3/ai/language-model"
    os.environ.setdefault("AI_GATEWAY_API_KEY", "local")
    return {
        "enabled": "1",
        "listen": listen,
        "upstream": upstream,
        "api": api,
        "env": print_env(listen),
    }


def fetch_catalog(listen: str = LISTEN_DEFAULT) -> list[str]:
    """Model ids from a running translator. Empty if it is down."""
    if not healthz_ok(listen):
        return []
    try:
        with urllib.request.urlopen(
            f"http://{listen}/coding-agent/v1/models", timeout=8
        ) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return []
    out: list[str] = []
    for m in (data.get("data") if isinstance(data, dict) else None) or []:
        if isinstance(m, dict) and m.get("id"):
            out.append(str(m["id"]))
    return out


def store_api_key(key: str) -> dict[str, Any]:
    """Persist a Vercel vck_ key or an OpenAI-compatible secret. Never echo it."""
    key = (key or "").strip()
    if not key:
        raise ValueError("empty key")
    load_env_file()
    was_upstream = bool(configured_upstream())
    hint = provider_from_key(key)
    if hint == "perplexity" or key.startswith("pplx-"):
        return store_perplexity_key(key)
    if hint == "vercel" or key.startswith("vck_"):
        remember_vercel_key(key)
        updates: dict[str, Optional[str]] = {
            "AI_GATEWAY_API_KEY": key,
            "VERCEL_AI_GATEWAY_API_KEY": key,
            "OPENAI_API_KEY": None,
            "OPENROUTER_API_KEY": None,
            "FX_UPSTREAM": None,
            "OPENAI_BASE_URL": None,
            "FX_UPSTREAM_API": None,
            "FX_GATEWAY_BASE_URL": None,
            "FX_GATEWAY_CHAT_URL": None,
        }
        if was_upstream:
            updates["FX_MODEL"] = None
        upsert_env(updates)
        os.environ["AI_GATEWAY_API_KEY"] = key
        os.environ["VERCEL_AI_GATEWAY_API_KEY"] = key
        for k in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "FX_UPSTREAM", "OPENAI_BASE_URL",
                  "FX_UPSTREAM_API", "FX_GATEWAY_BASE_URL", "FX_GATEWAY_CHAT_URL"):
            os.environ.pop(k, None)
        if was_upstream:
            os.environ.pop("FX_MODEL", None)
        stop_gateway()
        out = current_provider()
        out["saved"] = True
        return out
    load_env_file()
    cur_gw = (os.environ.get("AI_GATEWAY_API_KEY") or "").strip()
    if cur_gw.startswith("vck_"):
        remember_vercel_key(cur_gw)
    updates: dict[str, Optional[str]] = {
        "OPENAI_API_KEY": key,
        "AI_GATEWAY_API_KEY": "local",
    }
    upsert_env(updates)
    os.environ["OPENAI_API_KEY"] = key
    os.environ["AI_GATEWAY_API_KEY"] = "local"
    cur_id = provider_id_for(configured_upstream())
    if hint and hint not in ("", "vercel") and cur_id != hint:
        return apply_provider(hint, key=key)
    stop_gateway()
    offline = os.environ.get("FXS_UI_LOCAL", "") in ("1", "true", "yes")
    warn = ""
    if configured_upstream() and not offline:
        try:
            ensure_gateway()
        except Exception as e:
            warn = str(e)
    out = current_provider()
    out["saved"] = True
    if warn:
        out["warn"] = warn
    return out


def store_perplexity_key(key: str) -> dict[str, Any]:
    """Persist a search key. pplx- hits Perplexity directly; vck_ is Gateway search-only."""
    key = (key or "").strip()
    if key.startswith("vck_"):
        return store_vercel_search_key(key)
    load_env_file()
    if not key or key.lower() in ("clear", "none", "-"):
        upsert_env({"PERPLEXITY_API_KEY": None})
        os.environ.pop("PERPLEXITY_API_KEY", None)
    else:
        upsert_env({"PERPLEXITY_API_KEY": key})
        os.environ["PERPLEXITY_API_KEY"] = key
    return _after_search_key()


def store_vercel_search_key(key: str) -> dict[str, Any]:
    """Persist VERCEL_AI_GATEWAY_API_KEY for search without switching the LLM provider."""
    key = (key or "").strip()
    load_env_file()
    if not key or key.lower() in ("clear", "none", "-"):
        upsert_env({"VERCEL_AI_GATEWAY_API_KEY": None})
        os.environ.pop("VERCEL_AI_GATEWAY_API_KEY", None)
    else:
        remember_vercel_key(key)
    return _after_search_key()


def _after_search_key() -> dict[str, Any]:
    offline = os.environ.get("FXS_UI_LOCAL", "") in ("1", "true", "yes")
    warn = ""
    if configured_upstream() and not offline:
        try:
            stop_gateway()
            ensure_gateway()
        except Exception as e:
            warn = str(e)
    out = current_provider()
    out["saved"] = True
    if warn:
        out["warn"] = warn
    return out


def apply_provider(name_or_url: str, model: str = "", api: str = "", key: str = "") -> dict[str, Any]:
    key = (key or "").strip()
    hint = provider_from_key(key)
    if hint == "perplexity" or key.startswith("pplx-"):
        store_perplexity_key(key)
        key = ""
        hint = ""
    if hint == "vercel" or key.startswith("vck_"):
        return store_api_key(key)
    spec = resolve_provider(name_or_url)
    if hint and spec["id"] in ("vercel", "") and hint not in ("vercel", ""):
        return apply_provider(hint, model=model, api=api, key=key)
    load_env_file()
    previous_id = provider_id_for(configured_upstream())
    current_model = os.environ.get("FX_MODEL", "")
    updates: dict[str, Optional[str]] = {
        "FX_UPSTREAM": spec["url"] or None,
        "OPENAI_BASE_URL": spec["url"] or None,
    }
    if key:
        updates["OPENAI_API_KEY"] = key
    if spec["url"]:
        current = parse_env_file()
        gw_key = current.get("AI_GATEWAY_API_KEY", "")
        if gw_key.startswith("vck_"):
            updates["VERCEL_AI_GATEWAY_API_KEY"] = gw_key
        if not gw_key or gw_key.startswith("vck_"):
            updates["AI_GATEWAY_API_KEY"] = "local"
        if api:
            updates["FX_UPSTREAM_API"] = normalize_api(api)
    else:
        current = parse_env_file()
        saved_vck = current.get("VERCEL_AI_GATEWAY_API_KEY") or ""
        if current.get("AI_GATEWAY_API_KEY") == "local":
            updates["AI_GATEWAY_API_KEY"] = saved_vck if saved_vck.startswith("vck_") else None
        elif saved_vck.startswith("vck_") and not (current.get("AI_GATEWAY_API_KEY") or "").startswith("vck_"):
            updates["AI_GATEWAY_API_KEY"] = saved_vck
        updates["FX_UPSTREAM_API"] = None
        updates["FX_GATEWAY_BASE_URL"] = None
        updates["FX_GATEWAY_CHAT_URL"] = None
    explicit_model = (model or "").strip()
    carry_model = current_model if previous_id == spec["id"] else ""
    picked = explicit_model or suggest_model(spec["id"], carry_model)
    if picked:
        updates["FX_MODEL"] = picked
    elif previous_id != spec["id"]:
        # Provider switches must not leak a model chosen under another backend.
        # In particular, switching back to Vercel lets native fx choose its own
        # current default instead of baking one into this compatibility layer.
        updates["FX_MODEL"] = None
    upsert_env(updates)
    for k, v in updates.items():
        if v:
            os.environ[k] = v
        elif k in os.environ and v is None:
            os.environ.pop(k, None)
    offline = os.environ.get("FXS_UI_LOCAL", "") in ("1", "true", "yes")
    probe = bool(spec["url"]) and not offline
    if probe and provider_needs_key(spec["id"]) and not api_key_from_env():
        probe = False
        stop_gateway()
        os.environ.pop("FX_GATEWAY_BASE_URL", None)
        os.environ.pop("FX_GATEWAY_CHAT_URL", None)
    if probe:
        try:
            ensure_gateway(upstream=spec["url"], api=api or configured_api())
            catalog = fetch_catalog()
            if catalog:
                refined = suggest_model(spec["id"], os.environ.get("FX_MODEL", picked), catalog)
                if refined and refined != os.environ.get("FX_MODEL"):
                    upsert_env({"FX_MODEL": refined})
                    os.environ["FX_MODEL"] = refined
                    picked = refined
        except Exception as e:
            spec = dict(spec)
            spec["warn"] = str(e)
    else:
        if not spec["url"]:
            stop_gateway()
            os.environ.pop("FX_GATEWAY_BASE_URL", None)
            os.environ.pop("FX_GATEWAY_CHAT_URL", None)
    out = current_provider()
    if spec.get("warn"):
        out["warn"] = spec["warn"]
    out["needs_key"] = bool(spec["url"]) and provider_needs_key(out.get("id") or spec["id"]) and not out.get("key")
    return out


def _usage() -> str:
    return """fxs-gateway — fx Gateway protocol → OpenAI-compatible /v1

Usage:
  fxs-gateway [--listen 127.0.0.1:18787] [--upstream URL] [--api auto|chat|responses]
  fxs-gateway --ensure [--print-env]
  fxs-gateway --apply xai [--model grok-4] [--api responses]
  fxs-gateway --print-env
  fxs-gateway --stop

fx will not send traffic off loopback. Point FX_UPSTREAM at the provider
(/v1) and let this process sit on 127.0.0.1. `fxs provider xai` starts it
and picks a model that host actually lists.

OpenAI and xAI default to POST /v1/responses (reasoning, tool items,
store=false). Everyone else stays on /v1/chat/completions. Auto falls
back if /responses is missing. Override with --api or FX_UPSTREAM_API.
"""


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    listen = LISTEN_DEFAULT
    upstream = ""
    cli_api = ""
    do_print = False
    do_ensure = False
    do_stop = False
    do_howto = False
    do_apply = ""
    apply_model = ""
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            sys.stdout.write(_usage())
            return 0
        if a in ("--listen", "-listen") and i + 1 < len(argv):
            listen = argv[i + 1]; i += 2; continue
        if a in ("--upstream", "-upstream") and i + 1 < len(argv):
            upstream = argv[i + 1]; i += 2; continue
        if a in ("--api", "-api") and i + 1 < len(argv):
            cli_api = argv[i + 1]; i += 2; continue
        if a in ("--print-env", "-print-env"):
            do_print = True; i += 1; continue
        if a == "--ensure":
            do_ensure = True; i += 1; continue
        if a == "--stop":
            do_stop = True; i += 1; continue
        if a == "--apply" and i + 1 < len(argv):
            do_apply = argv[i + 1]; i += 2; continue
        if a in ("--model", "-m") and i + 1 < len(argv):
            apply_model = argv[i + 1]; i += 2; continue
        if a in ("--howto", "-howto"):
            do_howto = True; i += 1; continue
        if a in ("--version", "-version"):
            sys.stdout.write("fxs-gateway 1\n"); return 0
        sys.stderr.write(f"fxs-gateway: unknown argument {a}\n")
        return 2
    load_env_file()
    upstream = (upstream or configured_upstream() or os.environ.get("OPENAI_BASE_URL") or "").rstrip("/")
    if cli_api:
        try:
            cli_api = normalize_api(cli_api)
        except ValueError as e:
            sys.stderr.write(f"fxs-gateway: {e}\n")
            return 2
    if do_howto:
        sys.stdout.write(_usage())
        return 0
    if do_apply:
        try:
            info = apply_provider(do_apply, apply_model, api=cli_api)
        except ValueError as e:
            sys.stderr.write(f"fxs-gateway: {e}\n")
            return 2
        sys.stdout.write(json.dumps(info) + "\n")
        return 0
    if do_stop:
        stop_gateway(listen)
        return 0
    if do_ensure:
        if not upstream:
            return 0
        try:
            info = ensure_gateway(listen=listen, upstream=upstream, api=cli_api)
        except Exception as e:
            sys.stderr.write(f"fxs-gateway: {e}\n")
            return 1
        if do_print:
            sys.stdout.write(info.get("env") or print_env(listen))
        return 0
    if do_print:
        sys.stdout.write(print_env(listen))
        return 0
    if not upstream:
        sys.stderr.write("fxs-gateway: need --upstream or FX_UPSTREAM / OPENAI_BASE_URL\n")
        return 2
    key = api_key_from_env()
    if not key:
        key = "ollama"
        sys.stderr.write("fxs-gateway: no OPENAI_API_KEY; using dummy key \"ollama\"\n")
    serve(listen, upstream, key, api=cli_api or configured_api())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
