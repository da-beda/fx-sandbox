#!/usr/bin/env python3
from pathlib import Path

GATEWAY = Path("extras/gateway/gateway.py")
TESTS = Path("extras/gateway/test_gateway.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


g = GATEWAY.read_text(encoding="utf-8")

g = replace_once(
    g,
    'VERCEL_DEFAULT_MODEL = "zai/glm-5.2"\n# Used when the current model is still the Vercel default (or empty).\nDEFAULT_MODELS = {\n    "vercel": VERCEL_DEFAULT_MODEL,\n',
    '# Kept only for the legacy Vercel-search compatibility path. Provider\n# selection must never treat this as the installed fx build\'s product default.\nLEGACY_VERCEL_SEARCH_MODEL = "zai/glm-5.2"\nDEFAULT_MODELS = {\n',
    "legacy Vercel default declaration",
)

start = g.index("def suggest_model(")
end = g.index("\n\ndef normalize_upstream_url", start)
new_suggest = '''def suggest_model(pid: str, current: str = "", catalog: Optional[list[str]] = None) -> str:
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
'''
g = g[:start] + new_suggest + g[end:]

g = replace_once(
    g,
    '"ai-language-model-id": VERCEL_DEFAULT_MODEL,',
    '"ai-language-model-id": LEGACY_VERCEL_SEARCH_MODEL,',
    "search-only Vercel model reference",
)

g = replace_once(
    g,
    '    load_env_file()\n    current_model = os.environ.get("FX_MODEL", "")\n    updates: dict[str, Optional[str]] = {\n',
    '    load_env_file()\n    previous_id = provider_id_for(configured_upstream())\n    current_model = os.environ.get("FX_MODEL", "")\n    updates: dict[str, Optional[str]] = {\n',
    "apply_provider previous provider",
)

g = replace_once(
    g,
    '    picked = (model or "").strip() or suggest_model(spec["id"], current_model)\n    if picked:\n        updates["FX_MODEL"] = picked\n',
    '    explicit_model = (model or "").strip()\n    carry_model = current_model if previous_id == spec["id"] else ""\n    picked = explicit_model or suggest_model(spec["id"], carry_model)\n    if picked:\n        updates["FX_MODEL"] = picked\n    elif previous_id != spec["id"]:\n        # Provider switches must not leak a model chosen under another backend.\n        # In particular, switching back to Vercel lets native fx choose its own\n        # current default instead of baking one into this compatibility layer.\n        updates["FX_MODEL"] = None\n',
    "apply_provider model selection",
)

g = replace_once(
    g,
    '        lines.append("# model: fx default is zai/glm-5.2. Override with FX_MODEL or `fxs models`.")',
    '        lines.append("# model: unset; the installed fx build chooses its native default.")',
    "print_env stale default",
)

store_start = g.index("def store_api_key(")
store_end = g.index("\n\ndef store_perplexity_key", store_start)
store = g[store_start:store_end]
store = replace_once(
    store,
    '    load_env_file()\n    hint = provider_from_key(key)\n',
    '    load_env_file()\n    was_upstream = bool(configured_upstream())\n    hint = provider_from_key(key)\n',
    "store_api_key previous provider",
)
store = replace_once(
    store,
    '        upsert_env({\n            "AI_GATEWAY_API_KEY": key,\n            "VERCEL_AI_GATEWAY_API_KEY": key,\n            "OPENAI_API_KEY": None,\n            "OPENROUTER_API_KEY": None,\n            "FX_UPSTREAM": None,\n            "OPENAI_BASE_URL": None,\n            "FX_UPSTREAM_API": None,\n            "FX_GATEWAY_BASE_URL": None,\n            "FX_GATEWAY_CHAT_URL": None,\n        })\n',
    '        updates: dict[str, Optional[str]] = {\n            "AI_GATEWAY_API_KEY": key,\n            "VERCEL_AI_GATEWAY_API_KEY": key,\n            "OPENAI_API_KEY": None,\n            "OPENROUTER_API_KEY": None,\n            "FX_UPSTREAM": None,\n            "OPENAI_BASE_URL": None,\n            "FX_UPSTREAM_API": None,\n            "FX_GATEWAY_BASE_URL": None,\n            "FX_GATEWAY_CHAT_URL": None,\n        }\n        if was_upstream:\n            updates["FX_MODEL"] = None\n        upsert_env(updates)\n',
    "store_api_key Vercel updates",
)
store = replace_once(
    store,
    '        stop_gateway()\n        out = current_provider()\n',
    '        if was_upstream:\n            os.environ.pop("FX_MODEL", None)\n        stop_gateway()\n        out = current_provider()\n',
    "store_api_key clear stale model",
)
g = g[:store_start] + store + g[store_end:]

if "VERCEL_DEFAULT_MODEL" in g:
    raise SystemExit("stale VERCEL_DEFAULT_MODEL reference remains")

GATEWAY.write_text(g, encoding="utf-8")


t = TESTS.read_text(encoding="utf-8")
t = replace_once(
    t,
    '        self.assertEqual(gateway.suggest_model("xai", "zai/glm-5.2"), "grok-4")\n        self.assertEqual(gateway.suggest_model("openai", ""), "gpt-4o")\n        self.assertEqual(gateway.suggest_model("vercel", "grok-4"), "zai/glm-5.2")\n',
    '        # suggest_model no longer guesses model provenance from magic ids;\n        # callers carry a current model only when staying on that provider.\n        self.assertEqual(gateway.suggest_model("xai", "zai/glm-5.2"), "zai/glm-5.2")\n        self.assertEqual(gateway.suggest_model("openai", ""), "gpt-4o")\n        self.assertEqual(gateway.suggest_model("vercel", "grok-4"), "")\n',
    "suggest_model provenance contract",
)
t = replace_once(
    t,
    '        self.assertEqual(saved["FX_MODEL"], "zai/glm-5.2")\n',
    '        self.assertNotIn("FX_MODEL", saved)\n',
    "Vercel switch expectation",
)

marker = '    def test_apply_custom_url_appends_v1(self):\n'
insert = '''    def test_switching_provider_uses_target_policy_not_previous_model(self):
        gateway.apply_provider("xai")
        out = gateway.apply_provider("openrouter")
        self.assertEqual(out["id"], "openrouter")
        self.assertEqual(out["model"], "stealth/ox-alpha")
        saved = gateway.parse_env_file(gateway.ENV_FILE)
        self.assertEqual(saved["FX_MODEL"], "stealth/ox-alpha")

'''
t = replace_once(t, marker, insert + marker, "provider switch regression test")

store_test_start = t.index("    def test_store_vck_clears_upstream(self):")
store_test_end = t.index("\n    def ", store_test_start + 8)
store_test = t[store_test_start:store_test_end]
store_test = replace_once(
    store_test,
    '        self.assertNotIn("FX_UPSTREAM", saved)\n',
    '        self.assertNotIn("FX_UPSTREAM", saved)\n        self.assertNotIn("FX_MODEL", saved)\n',
    "store vck clears direct model",
)
t = t[:store_test_start] + store_test + t[store_test_end:]

TESTS.write_text(t, encoding="utf-8")
