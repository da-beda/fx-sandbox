# Search HTTP body boundaries

The Gateway adapter has three search-related HTTP clients in addition to the main model proxy:

1. direct Perplexity Search API;
2. Vercel AI Gateway model-catalog resolution for the private search worker;
3. OpenRouter server-side web search.

Their success and error bodies are untrusted input and use the same bounded-reader infrastructure as the main adapter.

## Limits

| Search path | Maximum body |
| --- | ---: |
| Vercel search-model catalog | 4 MiB |
| Perplexity successful JSON response | 8 MiB |
| OpenRouter successful JSON response | 8 MiB |
| Any search HTTP error body | 1 MiB |

Vercel Gateway **search execution** itself is SSE and remains governed by the stream limits in `stream_limits.py` rather than the 8 MiB JSON limit.

The 8 MiB search-response ceiling is intentionally large relative to the adapter's maximum of 20 normalized results. It is a memory/resource boundary, not a result-count, quality, or provider policy.

## Bounded behavior

All non-SSE search clients call `http_limits.read_limited()`:

- an oversized declared `Content-Length` is rejected before body consumption;
- chunked/undeclared responses are read with `maximum + 1` to detect observed overflow;
- HTTP error bodies are bounded before JSON/message parsing;
- no error path performs an unlimited read and then slices the resulting string afterward.

A search-side body-limit failure is returned through the existing provider-specific search error result. The normal fallback order remains unchanged:

```text
Perplexity direct -> Vercel Gateway -> OpenRouter
```

If one backend fails because its response violates a local resource limit, `run_perplexity_search()` can still continue to the next configured backend exactly as it does for other backend failures.

## Model-catalog policy

The Vercel-backed search worker continues to be selected from the authenticated live catalog. Bounding the catalog changes only resource handling; it does not change model ordering, the explicit `FXS_VERCEL_SEARCH_MODEL` override, active-Gateway model reuse, cache semantics, or the tool-capability selection rule.

## Verification

```bash
python3 extras/gateway/test_search_http_limits.py
python3 extras/gateway/test_search_policy.py
```

Dedicated coverage includes oversized catalog success/error responses, Perplexity success/error responses, OpenRouter success/error responses, and Vercel Gateway search error parsing. Cross-platform Gateway CI runs this coverage on Ubuntu and macOS.
