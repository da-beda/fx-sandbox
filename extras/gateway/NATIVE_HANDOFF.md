# Native fx OpenAI-compatible handoff

The optional Gateway adapter must not be retired merely because an installed `fx` binary can send one text prompt to an OpenAI-compatible endpoint.

For `fx-sandbox`, native-provider handoff is a behavioral compatibility decision with separate evidence for transport and agentic tool flow.

## Known upstream activation contracts

Two upstream implementations are currently under active development and use different configuration surfaces:

| Probe contract | Upstream proposal | Chat Completions | Responses |
| --- | --- | --- | --- |
| `fx_openai` | `vercel-labs/fx#168` | yes | yes |
| `custom_endpoint` | `vercel-labs/fx#159` | yes | not currently declared |

The probe tests contracts independently. No version number or PR identity is sufficient evidence that either contract exists in the installed binary.

## Evidence levels

`native_fx.py --probe-transport` reports two distinct levels for each wire.

### 1. Text transport

The installed binary must:

1. select the expected loopback `/v1/chat/completions` or `/v1/responses` endpoint under the tested activation contract;
2. accept a streamed fake response;
3. return the deterministic marker in `fx ask --json` output;
4. exit successfully.

This populates:

- `openai_chat` / `openai_responses`
- `openai_chat_contracts` / `openai_responses_contracts`

### 2. Coding-agent tool round-trip

A text-capable contract is then tested with the same behavior upstream uses in its OpenAI-compatible end-to-end coverage:

1. the fake provider asks for the built-in `read_file` tool;
2. fx executes `read_file` against an isolated fixture inside the probe workspace;
3. fx sends a second model request;
4. that request must contain the fixture marker produced by the tool result;
5. the fake provider returns a final deterministic answer;
6. fx accepts it and exits successfully.

For Chat Completions the follow-up is ordinary tool-message history. For Responses the follow-up must include a `function_call_output` item.

This populates:

- `openai_chat_tools` / `openai_responses_tools`
- `openai_chat_tool_contracts` / `openai_responses_tool_contracts`

A contract may therefore be text-capable while still failing the tool gate. That is intentional.

## Routing rule

For an interactive coding-agent provider path, **text transport alone is insufficient**. Native fx should replace the adapter only when:

- the required wire is behaviorally available;
- the same contract passes the tool round-trip when the use case needs tools;
- the semantic fidelity requirements for the selected path are equivalent or better than the adapter;
- provider-specific features that still depend on the adapter have an explicit fallback.

Until those conditions hold, the adapter remains the compatibility path.

## Safety of the probe

The probe is credential-free and network-contained:

- each attempt receives an isolated HOME and workspace;
- API keys are dummy values;
- the target endpoint is an ephemeral `127.0.0.1` server;
- legacy Gateway environment values are redirected to an unreachable loopback port to prevent accidental external fallback;
- the tool fixture contains only a deterministic marker and `read_file` is the only required operation;
- no write, shell, network, or destructive tool is requested.

The synthetic `FXS_NATIVE_PROBE_TOOL_FILE` environment variable exists only so unit-test fake executables can emulate a tool result deterministically. Real fx does not consume it and must execute its normal `read_file` implementation.

## Current stable baseline

Current stable `fx 0.0.5` does not pass either known native OpenAI-compatible text contract, so the tool probes are not entered and the adapter remains required.
