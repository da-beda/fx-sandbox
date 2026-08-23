# Design: fxs is fx in a box

**Same fx. Same agent loop. One host project. Less host authority.**

`fxs` owns containment and nothing above it.

```text
fx <args>  = native fx
fxs <args> = upstream fx + an external container boundary
```

"Same fx" means the unmodified upstream fx binary and agent loop. It does not
mean the native host and a container image are guaranteed to run the same fx
version forever, or that a Linux container is identical to the host OS.

## Invariants

1. **No native fallback.** `fxs` either runs in the configured container or exits non-zero.
2. **No workspace mutation at startup.** `fxs` never creates `.fx.json` or any other project file.
3. **No model policy.** If `FX_MODEL` is unset, fx resolves its own model exactly as upstream defines it.
4. **No agent-loop policy.** Step count, context and tool-result retention stay at upstream fx defaults unless the user explicitly overrides them.
5. **One deliberate permission override.** `fxs` defaults `FX_PERMISSION_MODE=yolo` because Docker is the authority boundary. `--ask` and `--auto` are explicit alternatives.
6. **The image is the update unit.** The root filesystem is read-only, so `fxs` forces `FX_AUTO_UPGRADE=0`. An unpinned `fxs --build-image` resolves fx's current stable release on the host, refreshes the configured base-image manifest, and passes the exact fx version into the Docker build. Explicit `--fx-version` pins bypass the latest-fx lookup.
7. **Upstream process controls pass through.** Exported `FX_*` controls are forwarded generically instead of being maintained as a semantic allowlist. Wrapper-owned controls are the explicit exceptions.
8. **One host project tree.** The selected workspace is the only host project tree exposed by default.
9. **Isolated state.** Each workspace gets its own private fxs home outside the project tree.
10. **No host provisioning.** fxs never installs Docker, edits daemon configuration, adds package repositories, or changes group membership.
11. **No provider protocol logic in core.** Provider compatibility belongs in optional adapters.
12. **Quiet runtime.** Successful startup does no installer work and emits no wrapper chatter unless `--verbose` is requested.

## Authority boundary

The default container has a read-only root filesystem, no Linux capabilities, `no-new-privileges`, an isolated `/tmp`, a non-root uid/gid matching the caller, and no Docker socket. The workspace is bind-mounted at `/workspace`. Per-project state is mounted at `/home/fx`.

Outbound networking remains enabled because fx needs inference access. `--offline` removes container networking. Access to `host.docker.internal` is *not* added by default; `--host-gateway` adds that convenience alias explicitly. The absence of the alias is not a host/LAN firewall: bridge networking can still reach routable destinations, and `--network NET` can deliberately widen the boundary further. See the threat model for the precise network assumptions.

CPU, memory and PID limits are opt-in. Coding workloads should not fail because the wrapper guessed an undersized resource budget.

## State and authentication

Native `fx` owns native state and credentials under upstream's `~/.fx` rules. fxs never wraps or rewrites the native binary.

Sandboxed fx state is intentionally separate under `~/.local/share/fxs/state/<workspace-hash>/home`. That prevents sessions/settings from different host projects from colliding even though each project appears as `/workspace` in its own container.

Users can authenticate sandboxed fx with `fxs login` / `fxs setup`, or pass upstream-supported process credentials such as `AI_GATEWAY_API_KEY` or `VERCEL_OIDC_TOKEN`.

## Process semantics

`fxs` does not maintain a list of every upstream `FX_*` runtime control. Exported
`FX_*` variables flow into the container automatically so tracing, recording,
update synchronization, theming and future upstream process controls do not need
an fxs release merely to become available.

The explicit exceptions are boundary-owned values:

- `FX_PERMISSION_MODE` — defaults to `yolo`, with `--ask` / `--auto` overrides.
- `FX_AUTO_UPGRADE` — forced to `0`; the read-only image is the update unit.
- `FX_NO_OPEN_BROWSER` — forced to `1`; authentication URLs are printed from the container.
- `FX_MODEL` / `FX_MAX_AGENT_STEPS` — forwarded explicitly so `--model` / `--steps` also work when those shell variables were not exported.

## Version and image semantics

A native `fx` install and an existing `fxs` image can legitimately be on different
fx versions. Compare them explicitly when parity matters:

```bash
fx --version
fxs -- --version
```

Refresh the reference image to the current stable upstream fx release and current
base-image manifest:

```bash
fxs --build-image
```

For an unpinned refresh, `fxs` first resolves `https://releases.fx.sh/latest.txt`
on the host, then passes the exact result as `FX_VERSION=<version>` to the Docker
build. The Dockerfile keeps OS dependencies and fx installation in separate
layers: a new fx release invalidates the fx layer, while a changed base-image
digest invalidates the OS layer.

To pin the **fx version**, build with:

```bash
fxs --build-image --fx-version <version>
```

Explicit pins do not query the latest-fx pointer, but this is not a promise of
bit-for-bit image reproducibility. The Ubuntu base tag, distribution packages and
canonical installer remain external inputs unless separately pinned. For a
published release, the signed image digest is the immutable artifact identity;
`UPSTREAM_FX_VERSION` records which fx release was embedded.

## Optional siblings

`extras/ui` and `extras/gateway` are retained as optional experiments. They are not installed, imported or required by core fxs. The core runtime has no Python dependency.

Their own stdlib test suites are kept in CI so preserving them does not silently turn into preserving broken files. Their older provider/state conveniences remain intentionally separate from the core containment contract.

`examples/docker-compose.yml` is illustrative only. It is a runtime example around an image already built/refreshed by `fxs`; `fxs` remains the single authoritative sandbox construction path.
