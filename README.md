# fx-sandbox

**fxs is fx in a box. Same fx. Same agent loop. One host project. Less host authority.**

```text
fx <args>  = native fx
fxs <args> = upstream fx + an external container boundary
```

The project deliberately does not add a planner, provider layer, model policy,
custom auth system, project config, or alternate agent loop. If upstream fx
already solves something, fxs does not reimplement it.

"Same fx" means the unmodified upstream fx binary and agent loop. The container
still has a deliberately different execution environment: isolated HOME/state,
Linux filesystem/process semantics, a read-only image, and a different authority
boundary. Native fx and an existing fxs image can also be on different fx
versions until the image is rebuilt or updated.

## What fxs adds

`fxs` exposes one host project directory to a Docker container, runs as your
uid/gid, uses a read-only image filesystem, drops all Linux capabilities,
enables `no-new-privileges`, never mounts the Docker socket, and keeps fx state
outside the project in a per-project home.

The default fx permission mode inside that boundary is `yolo`: Docker is the
authority boundary, so fx does not need a second approval loop. Use `fxs --ask`
or `fxs --auto` when you explicitly want fx's permission layer too.

If Docker is unavailable, stopped, or the wrapper is run as root, **fxs exits**.
It never falls back to native `fx`.

## Install

The friendly installer lets you choose native fx, fxs, or both:

```bash
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/install.sh | bash
```

For automation:

```bash
# both (also the non-interactive default)
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/install.sh | bash -s -- --both

# sandbox wrapper only
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/install.sh | bash -s -- --fxs-only

# native fx only
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/install.sh | bash -s -- --native-only
```

Native installation is delegated directly to fx's canonical installer at
`https://fx.sh/setup.sh`. fxs does not wrap the native binary, manage native
credentials, or modify native fx settings.

Docker is a prerequisite for fxs and is **never installed or configured by this
project**. If Docker is already running, the installer builds the small reference
image once. Otherwise install/start Docker yourself and run:

```bash
fxs --build-image
```

To pin both project revisions in automation, use an **existing** fxs release tag
and an explicit fx version (replace the placeholders with real published values):

```bash
FXS_TAG='<fxs-tag>'
FX_VERSION='<fx-version>'
curl -fsSL "https://raw.githubusercontent.com/da-beda/fx-sandbox/${FXS_TAG}/install.sh" \
  | bash -s -- --both --fxs-ref "$FXS_TAG" --fx-version "$FX_VERSION"
```

This pins the fxs source revision and fx version. It does not make a locally
rebuilt Ubuntu image bit-for-bit reproducible; use a published image digest when
an exact image artifact identity is required.

## Use

```bash
cd /path/to/project
fxs
fxs ask "review this repository"
fxs -c
fxs --ask
fxs --model <gateway-model-id>
fxs --steps 40
fxs --offline
```

Unknown arguments are passed to fx unchanged. Wrapper-specific options must come
before the fx command/arguments; use `--` to end fxs option parsing explicitly.

`fxs --deep` and `fxs --autonomous` remain compatibility aliases for `--steps 0`,
but unlimited steps are already upstream fx's default. fxs itself does not
impose a step limit, model, tool-result limit, context setting, or `.fx.json`.

## Upstream process controls

Exported upstream `FX_*` process controls are forwarded into the container
automatically instead of being copied into an fxs-maintained allowlist. That
means fx features such as tracing, recording, update synchronization, theming,
and future upstream process controls can work without an fxs release merely to
add another variable name.

The explicit exceptions are the few values owned by the containment boundary:

- `FX_PERMISSION_MODE` is set from fxs policy (`yolo` by default, or `--ask` / `--auto`).
- `FX_AUTO_UPGRADE=0` is forced because the image root filesystem is read-only.
- `FX_NO_OPEN_BROWSER=1` is forced so container authentication prints URLs instead of trying to open a host browser.
- `FX_MODEL` and `FX_MAX_AGENT_STEPS` are forwarded explicitly so `--model` and `--steps` work even when the shell variables were not exported.

The two upstream credentials that do not use the `FX_` prefix,
`AI_GATEWAY_API_KEY` and `VERCEL_OIDC_TOKEN`, are also passed when explicitly
present in the host environment.

## Authentication and state

Native auth stays native:

```bash
fx login
# or
fx setup
```

Sandboxed fx has a separate per-project home under:

```text
~/.local/share/fxs/state/<workspace-hash>/home
```

Authenticate there with:

```bash
fxs login
# or
fxs setup
```

This isolation is intentional: native `~/.fx` is never mounted into the
container and sessions from different host projects do not collide.

## fx and fxs updates

The **container image is the fx update unit**. Upstream fx can normally replace
its own executable during auto-upgrade, but fxs intentionally runs a read-only
image filesystem. To avoid a pointless/failing self-update path, fxs forces:

```text
FX_AUTO_UPGRADE=0
```

Refresh the reference image to the current stable fx and current base-image
manifest with:

```bash
fxs --build-image
```

The Dockerfile keeps OS dependencies and fx installation in separate layers, so
a new fx release invalidates the fx-install layer without needlessly rebuilding
the OS layer when the Ubuntu base itself is unchanged.

An existing image can legitimately lag behind native fx. When exact fx-version
parity matters, compare explicitly:

```bash
fx --version
fxs -- --version
```

Pin only the fx version with:

```bash
fxs --build-image --fx-version <version>
```

Explicit pins skip the latest-fx lookup, but the Ubuntu base tag and distribution
packages remain external inputs. For tagged fxs releases, the release workflow
records `UPSTREAM_FX_VERSION`, publishes a multi-architecture image, and signs its
immutable image digest.

`fxs` itself has no background updater. Refresh the installed wrapper and
reference Dockerfile explicitly by rerunning the installer:

```bash
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/install.sh \
  | bash -s -- --fxs-only --no-build
```

Or refresh the wrapper **and** rebuild the image in one explicit operation when
Docker is available:

```bash
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/install.sh \
  | bash -s -- --fxs-only --build-image
```

## No startup writes to the repository

Starting fxs does not create `.fx.json`, copy helper files into the project, or
rebuild its own installation. The first project write comes from fx/the agent
itself.

The normal runtime path is simply:

```text
fxs -> docker run -> fx
```

## Resource and network policy

The wrapper does not guess a CPU or RAM budget. Limits are opt-in:

```bash
fxs --memory 8g --cpus 8 --pids 1024
```

Outbound networking is enabled by default for inference. Disable it with:

```bash
fxs --offline
```

`host.docker.internal` is **not** added by default. When local inference or
another intentional host service requires that convenience alias:

```bash
fxs --host-gateway
```

That is an explicit widening of the boundary, but the absence of the alias is
**not** a host/LAN firewall. Docker bridge networking can still reach routable
Internet/LAN destinations and, depending on platform/routing/service bindings,
may reach host services by other addresses. `--network NET` is an advanced
escape hatch; using a more permissive network such as host networking further
reduces isolation. Use `--offline` when network denial is required.

## Custom development images

`FXS_IMAGE` (or `--image`) may point to any image that has an `fx` executable on
`PATH`. This lets the project image supply compilers/SDKs while fxs supplies
containment.

A simple pattern is to inject the fx binary from the reference image:

```Dockerfile
FROM fxs:latest AS fxs
FROM my-project-dev:latest
COPY --from=fxs /usr/local/bin/fx /usr/local/bin/fx
```

Then:

```bash
docker build -t my-project-fxs -f Dockerfile.fxs .
FXS_IMAGE=my-project-fxs fxs
```

No automatic Dev Container orchestration is added; that would turn the wrapper
back into a framework.

## Optional siblings

The core installation has no Python dependency and does not include provider
translation or a browser UI.

- `extras/gateway/` retains the OpenAI-compatible translation experiment.
- `extras/ui/` retains the browser UI experiment.
- `examples/docker-compose.yml` is illustrative only; `fxs` is the authoritative sandbox launcher.

These extras can evolve independently without changing the core containment
contract. Their stdlib unit suites run in CI, but their older provider/state
conveniences remain intentionally separate from core fxs.

The Compose example is runtime-only: build or refresh the image through `fxs`
first, then use Compose only when you explicitly want that illustrative shape.
It intentionally uses an ephemeral home instead of reproducing fxs's per-project
persistent-state policy.

## Security boundary

The selected workspace is available to the agent and can be uploaded in
model/tool context. A credential passed into the container is also readable by
code executing inside that container. The Docker boundary protects the host; it
does not magically hide in-container credentials from the workload.

A host-side credential/inference broker is the preferred future hardening for
reusable secrets, but it should remain a separate component rather than
expanding core fxs.

See [docs/DESIGN.md](docs/DESIGN.md) and
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

## Development

```bash
bash -n fxs install.sh setup-fx.sh tests/*.sh
bash tests/run.sh
python3 extras/gateway/test_gateway.py
python3 extras/ui/test_server.py
```

CI runs the core shell tests on Linux and macOS, runs the retained extras' stdlib
unit suites on Linux, validates the Compose example, and exercises the current
stable fx through the real fxs wrapper. Tagged releases build and keylessly sign
multi-architecture reference images for `linux/amd64` and `linux/arm64`.
