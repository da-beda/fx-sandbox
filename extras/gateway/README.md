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

## Compatibility contract

The adapter is tested at two levels:

```bash
python3 extras/gateway/test_gateway.py
python3 extras/ui/test_server.py
```

CI additionally installs the current stable `fx` and runs it end-to-end through this adapter against a deterministic fake OpenAI-compatible server in both Chat Completions and Responses modes:

```bash
python3 extras/gateway/test_fx_conformance.py
```

That conformance test is credential-free and catches drift in the real `fx` catalog/request/SSE boundary rather than only testing Python helpers in isolation.

The adapter is not installed by `install.sh`, and Python is not part of the minimal reference `fxs` image. It remains an optional sibling component rather than part of the containment runtime.
