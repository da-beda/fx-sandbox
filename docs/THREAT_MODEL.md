# Threat model

fxs is designed to reduce host authority granted to an autonomous coding agent. It is not a VM and it is not a defense against Docker/container-runtime vulnerabilities.

## Protected by default

The agent does not receive the host Docker socket, host home directory, root filesystem, SSH directory, cloud credential directories, or arbitrary additional bind mounts. The container runs without capabilities and with `no-new-privileges`; its image filesystem is read-only. Only the selected project tree and fxs-owned per-project state are writable host-backed locations.

`fxs` rejects obviously dangerous workspace roots such as `/`, `$HOME`, system directories and common credential directories. It also fails closed when Docker is missing or stopped.

## Intentionally reachable

The selected project is readable and writable unless `--read-only-workspace` is used. The model can read code in that project and may send selected context to the configured inference service. Outbound network access is enabled unless `--offline` is used.

Exported upstream `FX_*` process controls are intentionally forwarded into the container. They can change fx behavior, tracing, recording, update synchronization and other upstream runtime features, but do not by themselves add host filesystem mounts or choose a different Docker network. Boundary-owned controls such as permission mode, browser opening and automatic self-upgrade remain fixed by fxs.

## Credentials

A credential passed into the container as an environment variable, or saved by fx inside the isolated fxs home, is visible to code running with the agent's uid. Docker isolates that credential from the host filesystem; it does not make the credential secret from the workload itself.

The preferred long-term hardening is a host-side credential/inference broker: the container talks to a narrow local proxy, while reusable provider credentials remain outside the container. That should remain a separate component rather than expanding core fxs.

## Network and host services

The default network is Docker `bridge`, because fx normally needs outbound inference access. `host.docker.internal` is not added by default; `--host-gateway` adds that convenience alias explicitly for intentional host-local services.

**The absence of that alias does not imply host or LAN isolation.** A bridge-networked container can reach the Internet and routable LAN destinations, and depending on Docker platform, host routing and service bindings it may also reach host services through other routable addresses. Use `--offline` (`--network none`) when network denial is required.

`--network NET` is an explicit advanced escape hatch. Choosing a more permissive network changes the authority boundary. In particular, `--network host` on platforms that support host networking gives the container substantially broader access to the host network namespace and should be treated as a deliberate reduction in isolation.

## Image and upgrade boundary

The image filesystem is read-only, so fx cannot safely replace its own executable in place. fxs therefore forces `FX_AUTO_UPGRADE=0` and treats the image as the update unit.

An unpinned `fxs --build-image` resolves the current stable fx version on the host, refreshes the base-image manifest, and passes the exact fx version into Docker as a build argument. A new fx release therefore invalidates the fx-install cache layer; a changed Ubuntu base digest invalidates the OS dependency layer. Explicit `--fx-version` pins the fx version and bypasses the latest-version lookup.

The reference Docker build context is deliberately isolated from persistent fxs data. The installed Dockerfile normally lives under `~/.local/share/fxs`, next to the default `state/` tree, but `fxs --build-image` copies only that Dockerfile into a fresh temporary directory and uses the temporary directory as Docker's build context. The temporary context is removed after the build. This prevents session/auth/state files from being sent to the Docker daemon or a remote builder merely because they share a parent directory with the installed Dockerfile. The repository `.dockerignore` also denies context contents by default as defense in depth.

Pinning `FX_VERSION` is **not** a promise of bit-for-bit image reproducibility: the Ubuntu base tag, distribution packages and upstream canonical installer are still external inputs unless separately pinned. A published image digest is the immutable identity for a released image.

This means native fx and sandboxed fx are not guaranteed to be the same version unless the operator keeps them aligned. That is a version-management property, not a fork of the agent loop.

## Custom images

`FXS_IMAGE` / `--image` may point to any image containing an `fx` executable. The image controls the toolchain available to the agent and may itself contain software with additional risk. fxs still applies the same container authority boundary around that image.
