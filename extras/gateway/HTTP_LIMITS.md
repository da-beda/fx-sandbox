# Gateway HTTP body resource boundaries

The optional OpenAI-compatible Gateway adapter treats every upstream provider response as untrusted input. `stream_limits.py` bounds SSE framing and streamed tool state; `http_limits.py` covers the HTTP paths that do not pass through the SSE reader.

These limits are **resource-safety ceilings**, not model token limits, latency limits, or product policy. They are deliberately large relative to normal coding-agent traffic.

## Default ceilings

| Boundary | Maximum |
| --- | ---: |
| Upstream `/v1/models` response | 4 MiB |
| Upstream error response | 1 MiB |
| Upstream non-stream completion | 64 MiB |
| Downstream loopback Gateway request | 64 MiB |

## Upstream reads

`http_limits.read_limited()` handles model catalogs, provider errors, non-stream completions, and the `/responses` compatibility-fallback error peek.

For a real `urllib` / `http.client` response it first checks a valid declared `Content-Length`. A value above the local ceiling is rejected before the body is consumed. Otherwise the response is read with `maximum + 1` bytes, so a chunked response or a server that omits `Content-Length` cannot evade the ceiling.

Deterministic legacy test doubles that expose only `read()` remain usable, but the returned value is still type-checked and size-checked after the read. Production HTTP responses use the bounded form.

## Downstream loopback request

The adapter previously converted `Content-Length` directly with `int()` and passed it to `rfile.read()`. A negative value can become an unbounded `read(-1)`, while an arbitrarily large positive value can request an arbitrarily large allocation/read.

`http_limits.parse_content_length()` now classifies the header before body consumption:

- missing or zero → zero-length body;
- malformed or negative → HTTP **400**;
- above 64 MiB → HTTP **413**;
- otherwise → exact bounded body read.

The request limit applies to the loopback Vercel-Gateway-shaped body presented by fx. It does not change the upstream model's own context or output-token budget.

## Failure behavior

An upstream body exceeding a local ceiling never becomes successful partial state:

- oversized model catalog → bounded HTTP 502 Gateway error;
- oversized non-stream completion → bounded HTTP 502 Gateway error;
- oversized provider error body → bounded Gateway error without reading the declared body;
- oversized `/responses` fallback body → fallback is not inferred from unbounded input;
- oversized downstream request → HTTP 413 before body read.

Streaming generation continues to use the separate terminal-evidence, cancellation, and SSE/tool-state rules documented in the gateway README.

## Verification

Unit coverage:

```bash
python3 extras/gateway/test_http_limits.py
```

Real loopback-proxy coverage:

```bash
python3 extras/gateway/test_http_limits_integration.py
```

The integration suite proves early 400/413 request rejection and bounded catalog, non-stream completion, and provider-error behavior through the actual `GatewayHandler` HTTP path.
