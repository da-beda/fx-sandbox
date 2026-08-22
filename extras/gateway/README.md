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

Do not infer native provider support from an `fx` version number, branch name, or help-text guess. The upstream OpenAI-compatible work is environment-driven, so `native_fx.py` can exercise the installed binary against an ephemeral loopback `/v1` server using the documented provider contract:

```bash
python3 extras/gateway/native_fx.py --json --probe-transport
```

The probe uses no real provider credential and sends no model request to the Internet. It gives `fx` an isolated HOME, a dummy `OPENAI_API_KEY`, a loopback `FX_OPENAI_BASE_URL`, an explicit `FX_OPENAI_API_STYLE`, and a deterministic fake model. Chat Completions and Responses are tested independently. A capability is considered native only when the installed binary selects the expected `/v1` transport, accepts its streamed response, exits successfully, and returns the probe marker.

Running the command without `--probe-transport` is metadata-only and deliberately claims no provider capability:

```bash
python3 extras/gateway/native_fx.py --json
```

This gives the WebUI and future migration work a conservative rule: switch a provider path to native `fx` only after the installed binary itself proves the required wire works. Until then, keep using the adapter. Native Chat support alone is also not enough to retire the adapter's Responses path.

## Compatibility contract

The adapter is tested at two levels:

```bash
python3 extras/gateway/test_gateway.py
python3 extras/gateway/test_native_fx.py
python3 extras/ui/test_server.py
```

CI additionally installs the current stable `fx`, behaviorally probes its native OpenAI-compatible transports, and runs it end-to-end through this adapter against a deterministic fake OpenAI-compatible server in both Chat Completions and Responses modes:

```bash
python3 extras/gateway/native_fx.py --json --probe-transport
python3 extras/gateway/test_fx_conformance.py
```

Both checks are credential-free. Together they distinguish two independent facts: whether native `fx` can replace a compatibility path, and whether the adapter still works with the real current `fx` Gateway contract.

The adapter is not installed by `install.sh`, and Python is not part of the minimal reference `fxs` image. It remains an optional sibling component rather than part of the containment runtime.
