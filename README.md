# fx-sandbox

**fxs is fx in a box. Same fx. Same agent loop. One host project. Less host authority.**

```text
fx <args>  = native fx
fxs <args> = upstream fx + an external container boundary
```

`fx-sandbox` deliberately stays below the agent layer. It does not add a planner,
provider implementation, model policy, custom auth system, browser UI, project
configuration format, or alternate agent loop. Those belong to upstream
[`vercel-labs/fx`](https://github.com/vercel-labs/fx).

What `fxs` adds is a deliberately small external authority boundary around the
unmodified upstream `fx` binary.

## What the boundary does

For one selected host project, `fxs`:

- bind-mounts that project at `/workspace`;
- keeps fx state in a private per-project home outside the repository;
- runs as the calling uid/gid rather than root;
- uses a read-only image root filesystem;
- drops all Linux capabilities;
- enables `no-new-privileges`;
- supplies an isolated `/tmp`;
- never mounts the Docker socket;
- does not expose `host.docker.internal` unless explicitly requested; and
- never falls back to native `fx` if Docker is unavailable.

The default fx permission mode inside this boundary is `yolo`: Docker is the
primary authority boundary. Use `fxs --ask` or `fxs --auto` when you explicitly
want fx's approval layer as well.

## Install

The installer can install native fx, fxs, or both:

```bash
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/install.sh | bash
```

Non-interactive examples:

```bash
# native fx + fxs (default when no TTY is available)
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/install.sh | bash -s -- --both

# fxs only
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/install.sh | bash -s -- --fxs-only

# native fx only
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/install.sh | bash -s -- --native-only
```

Native installation is delegated directly to fx's canonical installer at
`https://fx.sh/setup.sh`. fxs does not wrap the native binary, manage native
credentials, or modify native fx settings.

Docker is a prerequisite for fxs and is **never installed or configured by this
project**. If Docker is not running during installation, build the reference
image later:

```bash
fxs --build-image
```

For reproducible automation, pin both projects:

```bash
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/<fxs-tag>/install.sh \
  | bash -s -- --both --fxs-ref <fxs-tag> --fx-version <fx-version>
```

## Use

```bash
cd /path/to/project
fxs
fxs ask "review this repository"
fxs -c
fxs --ask
fxs --model <model-id>
fxs --steps 40
fxs --offline
```

Wrapper-specific options must come before the first fx command/argument. Once
`fxs` sees an unrecognized argument, the remainder is passed to fx unchanged.
Use `--` to terminate fxs option parsing explicitly:

```bash
fxs -- --help
```

`fxs` itself does not impose a model, step limit, context limit, tool-result
limit, provider policy, or project `.fx.json`.

## Upstream process controls

Exported upstream `FX_*` process controls are forwarded into the container
automatically rather than mirrored in an fxs-maintained allowlist. That keeps
tracing, recording, update synchronization, theming, and new upstream process
controls usable without an fxs release just to add another variable name.

The explicit exceptions are boundary-owned values:

- `FX_PERMISSION_MODE` is set by fxs (`yolo` by default, or `--ask` / `--auto`).
- `FX_AUTO_UPGRADE=0` is forced because the image root filesystem is read-only.
- `FX_NO_OPEN_BROWSER=1` is forced so container auth prints URLs instead of trying to open a host browser.
- `FX_MODEL` and `FX_MAX_AGENT_STEPS` are forwarded explicitly so the fxs convenience flags work even when their shell variables were not exported.

The upstream credentials `AI_GATEWAY_API_KEY` and `VERCEL_OIDC_TOKEN` are also
passed when they are explicitly present in the host environment. Subscription
login state created by commands such as `fxs login ...` lives in the isolated
fxs home and does not require mounting native `~/.fx`.

## Authentication and state

Native auth stays native:

```bash
fx login
# or
fx setup
```

Sandboxed fx has separate per-project state under:

```text
~/.local/share/fxs/state/<workspace-hash>/home
```

Authenticate the sandboxed instance with the normal fx commands:

```bash
fxs login
# or
fxs setup
```

Different host projects therefore do not silently share fx sessions or profile
state, even though every container sees its selected project at `/workspace`.

## fx versions and upgrades

The **container image is the fx update unit**. Since the image root is read-only,
fxs disables in-container self-upgrade:

```text
FX_AUTO_UPGRADE=0
```

Refresh the reference image to the current stable fx release with:

```bash
fxs --build-image
```

An unpinned refresh resolves `https://releases.fx.sh/latest.txt` on the host and
passes that exact version into the Docker build. The fx version is therefore
part of Docker's cache key; a newly published stable release cannot be hidden by
an old cached installer layer.

Native fx and an existing fxs image may legitimately differ. Compare explicitly
when parity matters:

```bash
fx --version
fxs -- --version
```

Pin an exact upstream release when reproducibility matters:

```bash
fxs --build-image --fx-version <version>
```

## Tracking fast upstream development

fx is experimental and changes quickly. `fx-sandbox` therefore avoids copying
provider catalogs, provider protocols, terminal presentation, model defaults,
or agent-loop behavior.

CI validates the shell wrapper on Linux and macOS and exercises the current
stable fx image. A scheduled **upstream canary** independently rebuilds the
current stable fx release and runs a small wrapper/image contract smoke test, so
a new fx release can break loudly even if this repository has had no recent
commits.

Historical provider-translation and browser-UI experiments that previously lived
on `main` are preserved on the branch
`archive/legacy-experiments-2026-08-22`; they are intentionally no longer part of
the maintained surface.

## Resource and network policy

The wrapper does not guess a CPU or RAM budget. Limits are opt-in:

```bash
fxs --memory 8g --cpus 8 --pids 1024
```

Outbound networking is enabled by default because fx needs inference access.
Disable it with:

```bash
fxs --offline
```

`host.docker.internal` is not added by default. When local inference or another
intentional host service requires it:

```bash
fxs --host-gateway
```

That explicitly widens the boundary.

## Custom development images

`FXS_IMAGE` (or `--image`) may point to any image with an `fx` executable on
`PATH`. A project-specific image can therefore provide its own compilers and SDKs
while fxs supplies containment.

One simple pattern is to copy fx from the reference image:

```Dockerfile
FROM fxs:latest AS fxs
FROM my-project-dev:latest
COPY --from=fxs /usr/local/bin/fx /usr/local/bin/fx
```

Then run:

```bash
docker build -t my-project-fxs -f Dockerfile.fxs .
FXS_IMAGE=my-project-fxs fxs
```

No automatic Dev Container orchestration is added; that would turn the wrapper
back into a framework.

## Security boundary

The selected workspace is intentionally readable by the agent and may be sent in
model/tool context. Credentials passed into the container are readable by code
executing inside that container. Docker limits host authority; it does not hide
in-container secrets from the workload.

See [docs/DESIGN.md](docs/DESIGN.md) and
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

## Development

```bash
bash -n fxs install.sh setup-fx.sh tests/*.sh
bash tests/run.sh
```

CI runs the shell tests on Linux and macOS and verifies the wrapper against a
freshly built current-stable fx image. Tagged releases build and keylessly sign
multi-architecture reference images for `linux/amd64` and `linux/arm64`.
