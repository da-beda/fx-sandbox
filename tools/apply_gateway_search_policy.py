#!/usr/bin/env python3
from pathlib import Path

GATEWAY = Path("extras/gateway/gateway.py")
TESTS = Path("extras/gateway/test_gateway.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def replace_count(text: str, old: str, new: str, expected: int, label: str) -> str:
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"{label}: expected exactly {expected} matches, got {count}")
    return text.replace(old, new)


g = GATEWAY.read_text(encoding="utf-8")
g = replace_once(
    g,
    "from urllib.parse import urlparse\n",
    "from urllib.parse import urlparse\n\nimport search_policy\n",
    "search policy import",
)
g = replace_once(
    g,
    '# Kept only for the legacy Vercel-search compatibility path. Provider\n# selection must never treat this as the installed fx build\'s product default.\nLEGACY_VERCEL_SEARCH_MODEL = "zai/glm-5.2"\n',
    "",
    "legacy search model constant",
)
g = replace_once(
    g,
    '''def _gateway_search_headers(key: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "ai-language-model-id": LEGACY_VERCEL_SEARCH_MODEL,
        "ai-language-model-streaming": "true",
        "ai-language-model-specification-version": GATEWAY_SPEC_VERSION,
        "ai-gateway-protocol-version": GATEWAY_PROTOCOL_VERSION,
    }
''',
    '''def _gateway_search_headers(key: str, model: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "ai-language-model-id": model,
        "ai-language-model-streaming": "true",
        "ai-language-model-specification-version": GATEWAY_SPEC_VERSION,
        "ai-gateway-protocol-version": GATEWAY_PROTOCOL_VERSION,
    }
''',
    "gateway search headers",
)
g = replace_once(
    g,
    '''    key = vercel_gateway_key()
    if not key:
        return {"error": SEARCH_NO_KEY}
    req = urllib.request.Request(
        GATEWAY_SEARCH_URL,
        data=_gateway_search_body(query, max_results),
        method="POST",
        headers=_gateway_search_headers(key),
    )
''',
    '''    key = vercel_gateway_key()
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
''',
    "gateway search model resolution",
)
if "LEGACY_VERCEL_SEARCH_MODEL" in g:
    raise SystemExit("legacy Vercel search model reference remains")
GATEWAY.write_text(g, encoding="utf-8")


t = TESTS.read_text(encoding="utf-8")
t = replace_count(
    t,
    '            "PERPLEXITY_API_KEY", "VERCEL_AI_GATEWAY_API_KEY",\n',
    '            "PERPLEXITY_API_KEY", "VERCEL_AI_GATEWAY_API_KEY",\n            "FXS_VERCEL_SEARCH_MODEL",\n',
    2,
    "test env cleanup",
)
t = replace_once(
    t,
    '        os.environ["VERCEL_AI_GATEWAY_API_KEY"] = "vck_search"\n        payload = (\n',
    '        os.environ["VERCEL_AI_GATEWAY_API_KEY"] = "vck_search"\n        os.environ["FXS_VERCEL_SEARCH_MODEL"] = "provider/search-worker"\n        payload = (\n',
    "gateway search fixture override",
)
t = replace_once(
    t,
    '            self.assertEqual(items.get("ai-language-model-specification-version"), "3")\n            return FakeSSE()\n',
    '            self.assertEqual(items.get("ai-language-model-specification-version"), "3")\n            self.assertEqual(items.get("ai-language-model-id"), "provider/search-worker")\n            return FakeSSE()\n',
    "gateway search selected model assertion",
)
# The two following tests need to reach the inference request itself so their
# error/fallback assertions remain focused on HTTP behavior rather than catalog lookup.
needle = '    def test_gateway_search_maps_credit_card_403(self):\n        import urllib.request\n        os.environ["VERCEL_AI_GATEWAY_API_KEY"] = "vck_search"\n'
t = replace_once(
    t,
    needle,
    needle + '        os.environ["FXS_VERCEL_SEARCH_MODEL"] = "provider/search-worker"\n',
    "credit-card fixture override",
)
needle = '    def test_gateway_403_falls_back_to_openrouter(self):\n        import urllib.request\n        os.environ["VERCEL_AI_GATEWAY_API_KEY"] = "vck_search"\n'
t = replace_once(
    t,
    needle,
    needle + '        os.environ["FXS_VERCEL_SEARCH_MODEL"] = "provider/search-worker"\n',
    "openrouter fallback fixture override",
)
TESTS.write_text(t, encoding="utf-8")
