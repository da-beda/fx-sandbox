# Optional Gateway Adapter

This directory contains the optional OpenAI-compatible compatibility backend used by `fx-sandbox` and the browser UI when the selected `fx` build does not natively support the required provider path.

Core `fxs` deliberately stays provider-agnostic. It owns containment; it does not own provider catalogs, API formats, model defaults, or provider credentials. The adapter remains outside core and translates the loopback Vercel Gateway surface expected by current stable `fx` into OpenAI-compatible `/v1` Chat Completions or Responses traffic.

## Why this still exists

Current upstream `fx` has native Vercel AI Gateway, Codex subscription, and Grok subscription providers. Native OpenAI-compatible/local inference support is also under active upstream development. Until that support lands and reaches the capability coverage needed here, this adapter provides direct API-key and local-server paths such as OpenAI, xAI, OpenRouter, Ollama, LM Studio, vLLM, llama.cpp, Groq, Together, Fireworks, DeepSeek, Mistral, and arbitrary compatible `/v1` endpoints.

The intended migration rule is conservative:

- prefer native upstream `fx` when it provides the requested provider and required capabilities;
- retain this adapter as a compatibility/fallback path for older `fx` builds or provider capabilities not yet covered natively;
- do not emulate upstream provider policy when transport translation is sufficient;
- never remove the WebUI or provider paths merely because an overlapping upstream implementation exists.

## Native handoff gate

Do not infer native provider support from an `fx` version number, branch name, PR number, or help-text guess. There are currently two competing upstream local-inference contracts: PR #168 proposes `OPENAI_API_KEY` + `FX_OPENAI_BASE_URL` + `FX_OPENAI_API_STYLE`, while PR #159 proposes `FX_API_KEY` + `FX_BASE_URL` for Chat Completions. Either design, or a successor derived from one of them, could land first.

`native_fx.py` therefore tests the installed binary behaviorally against an ephemeral loopback `/v1` server:

```bash
python3 extras/gateway/native_fx.py --json --probe-transport
```

The probe uses no real provider credential and sends no model request to the Internet. Each known configuration contract gets its own isolated HOME and environment so one proposal cannot make another appear to work accidentally. Chat Completions and Responses are tested independently. A capability is considered native only when the installed binary selects the expected loopback endpoint, accepts its streamed response, exits successfully, and returns the probe marker.

Machine-readable output includes the exact contracts that succeeded, for example `openai_chat_contracts: ["fx_openai", "custom_endpoint"]` and `openai_responses_contracts: ["fx_openai"]`. That matters for later routing: knowing that native transport exists is not enough; the WebUI also needs to know which installed configuration contract actually activates it.

Running the command without `--probe-transport` is metadata-only and deliberately claims no provider capability:

```bash
python3 extras/gateway/native_fx.py --json
```

This gives the WebUI and future migration work a conservative rule: switch a provider path to native `fx` only after the installed binary itself proves the required wire and reports the contract needed to configure it. Until then, keep using the adapter. Native Chat support alone is also not enough to retire the adapter's Responses path.

## Stream completion integrity

A streaming provider must produce terminal evidence before the adapter commits a successful turn. Valid terminal evidence is a Chat Completions finish reason, a terminal Responses event, or an explicit SSE `[DONE]` sentinel.

A bare transport EOF is **not** terminal evidence. If an upstream server emits partial text or tool arguments and then disconnects without one of the terminal conditions above, the adapter emits an error finish rather than manufacturing `stop`. This prevents a truncated local-model response from being recorded as a successful agent turn. `[DONE]` without a preceding finish chunk remains accepted for compatible servers that use the sentinel itself as the terminal marker.

## Vercel-backed search with another LLM provider

The WebUI can retain a Vercel AI Gateway key for web search while the main model runs through OpenRouter, xAI, Ollama, or another OpenAI-compatible endpoint. That search path must not copy upstream `fx`'s current default model into this repository.

`search_policy.py` therefore resolves the private Gateway search worker independently:

1. `FXS_VERCEL_SEARCH_MODEL` is an explicit override for troubleshooting or pinning.
2. When Vercel itself is the active provider and `FX_MODEL` is explicitly set, that active Gateway model is reused.
3. Otherwise the authenticated `/coding-agent/v1/models` catalog is queried. A language model explicitly tagged for web search is preferred; otherwise the first server-ordered `tool-use` language model is used.
4. Successful catalog resolution is cached for five minutes by API-key fingerprint. The raw key is never used as the cache key or persisted by this policy module.
5. If no suitable worker can be resolved, Vercel search returns an explicit error and the existing search chain can still fall through to OpenRouter when configured.

This keeps the search feature while removing the maintenance dependency on whichever model happens to be upstream `fx`'s product default that week.

## Protocol fidelity is executable

`fidelity_matrix.py` probes semantic translation cases instead of relying on a hand-maintained feature checklist:

```bash
python3 extras/gateway/fidelity_matrix.py
python3 extras/gateway/fidelity_matrix.py --json
```

The matrix covers text, output limits, tool schemas/history, named tool choice, reasoning, image input, structured output, streamed text, streamed tool calls, and streamed reasoning for both Chat Completions and Responses paths. `pass` means the semantic case is preserved; `degraded` means the request is accepted or partially translated but some semantics are lost or rejected.

The adapter now preserves three semantics that were previously dropped:

- Gateway image file parts become ordered OpenAI Responses `input_image` data URLs alongside `input_text` parts. This preserves an image **after fx has already admitted it**; it does not mark arbitrary local models as vision-capable.
- Gateway JSON `responseFormat` becomes OpenAI Responses `text.format` with `type: json_schema` and `strict: true`.
- Gateway named tool pinning maps to the native named-function choice on both wires: Chat Completions uses `{"type":"function","function":{"name":"..."}}`, while Responses uses `{"type":"function","name":"..."}`. Simple `auto`, `required`, and `none` choices remain unchanged.

The remaining deliberate gaps stay visible: Chat-mode reasoning/image/structured-output handling remains degraded, while Responses preserves reasoning, reasoning deltas, admitted images, structured output, and named tool choice. These rows are frozen in CI so every future fidelity improvement changes both implementation and evidence together.

This is also the migration contract for native upstream support: a native transport being present is not sufficient by itself. The WebUI should prefer native `fx` for a capability only when the installed binary's required semantics are proven equivalent or better for that use case.

## Compatibility contract

The adapter is tested at multiple levels:

```bash
python3 extras/gateway/test_gateway.py
python3 extras/gateway/test_search_policy.py
python3 extras/gateway/test_responses_fidelity.py
python3 extras/gateway/test_tool_choice_fidelity.py
python3 extras/gateway/test_fidelity_matrix.py
python3 extras/gateway/test_native_fx.py
python3 extras/ui/test_server.py
```

CI additionally installs the current stable `fx`, behaviorally probes its native OpenAI-compatible transports, and runs it end-to-end through this adapter against a deterministic fake OpenAI-compatible server in both Chat Completions and Responses modes:

```bash
python3 extras/gateway/native_fx.py --json --probe-transport
python3 extras/gateway/test_fx_conformance.py
```

Both checks are credential-free. Together they distinguish three independent facts: whether native `fx` can replace a compatibility path, whether the adapter still works with the real current `fx` Gateway contract, and whether feature semantics are being preserved rather than silently dropped.

The adapter is not installed by `install.sh`, and Python is not part of the minimal reference `fxs` image. It remains an optional sibling component rather than part of the containment runtime.
