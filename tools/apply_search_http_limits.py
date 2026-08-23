#!/usr/bin/env python3
from pathlib import Path

path = Path("extras/gateway/gateway.py")
g = path.read_text(encoding="utf-8")


def replace_function(text: str, start_sig: str, next_sig: str, body: str) -> str:
    start = text.index(start_sig)
    end = text.index(next_sig, start)
    return text[:start] + body.rstrip() + "\n\n\n" + text[end:]


g = replace_function(
    g,
    "def _gateway_http_error(exc: urllib.error.HTTPError) -> str:\n",
    "def _search_has_hits(out: Any) -> bool:\n",
    '''def _gateway_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        raw = http_limits.read_limited(
            exc,
            http_limits.ERROR_BODY_BYTES,
            "Vercel Gateway search error body",
        ).decode("utf-8", "replace")[:500]
    except http_limits.BodyLimitError as limit_error:
        return f"Vercel AI Gateway search failed (HTTP {exc.code}). {limit_error}"
    except Exception:
        raw = ""
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
''',
)

g = replace_function(
    g,
    "def run_direct_perplexity_search(query: str, max_results: int = 5) -> dict[str, Any]:\n",
    "def _gateway_search_body(query: str, max_results: int) -> bytes:\n",
    '''def run_direct_perplexity_search(query: str, max_results: int = 5) -> dict[str, Any]:
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
            raw = http_limits.read_limited(
                resp,
                http_limits.SEARCH_RESPONSE_BYTES,
                "Perplexity search response",
            )
            data = json.loads(raw.decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        try:
            err = http_limits.read_limited(
                e,
                http_limits.ERROR_BODY_BYTES,
                "Perplexity search error body",
            ).decode("utf-8", "replace")[:300]
        except http_limits.BodyLimitError as limit_error:
            err = str(limit_error)
        except Exception:
            err = ""
        return {"error": f"Perplexity search failed (HTTP {e.code}). {err}"}
    except http_limits.BodyLimitError as e:
        return {"error": f"Perplexity search failed. {e}"}
    except Exception as e:
        return {"error": f"Perplexity search failed. {e}"}
    rows = data.get("results") if isinstance(data, dict) else None
    out = _normalize_search_hits(query, rows, max_results)
    if "results" in out:
        out["source"] = "perplexity"
    return out
''',
)

g = replace_function(
    g,
    "def run_openrouter_search(query: str, max_results: int = 5) -> dict[str, Any]:\n",
    "class Stream:\n",
    '''def run_openrouter_search(query: str, max_results: int = 5) -> dict[str, Any]:
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
            raw = http_limits.read_limited(
                resp,
                http_limits.SEARCH_RESPONSE_BYTES,
                "OpenRouter search response",
            )
            data = json.loads(raw.decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        try:
            err = http_limits.read_limited(
                e,
                http_limits.ERROR_BODY_BYTES,
                "OpenRouter search error body",
            ).decode("utf-8", "replace")[:300]
        except http_limits.BodyLimitError as limit_error:
            err = str(limit_error)
        except Exception:
            err = ""
        return {"error": f"OpenRouter search failed (HTTP {e.code}). {err}"}
    except http_limits.BodyLimitError as e:
        return {"error": f"OpenRouter search failed. {e}"}
    except Exception as e:
        return {"error": f"OpenRouter search failed. {e}"}
    return _hits_from_openrouter(data, query, max_results)
''',
)

path.write_text(g, encoding="utf-8")
