# Threat model

fxs is designed to reduce host authority granted to an autonomous coding agent. It is not a VM and it is not a defense against Docker/container-runtime vulnerabilities.

## Protected by default

The agent does not receive the host Docker socket, host home directory, root filesystem, SSH directory, cloud credential directories, or arbitrary additional bind mounts. The container runs without capabilities and with `no-new-privileges`; its image filesystem is read-only. Only the selected project tree and fxs-owned per-project state are writable host-backed locations.

`fxs` rejects obviously dangerous workspace roots such as `/`, `$HOME`, system directories and common credential directories. It also fails closed when Docker is missing or stopped.

## Intentionally reachable

The selected project is readable and writable unless `--read-only-workspace` is used. The model can read code in that project and may send selected context to the configured inference service. Outbound network access is enabled unless `--offline` is used.

Exported upstream `FX_*` process controls are intentionally forwarded into the container. They can change fx behavior, tracing, recording, update synchronization and other upstream runtime features, but do not by themselves add host filesystem mounts or widen the Docker network boundary. Boundary-owned controls such as permission mode, browser opening and automatic self-upgrade remain fixed by fxs.

## Credentials

A credential passed into the container as an environment variable, or saved by fx inside the isolated fxs home, is visible to code running with the agent's uid. Docker isolates that credential from the host filesystem; it does not make the credential secret from the workload itself.

The preferred long-term hardening is a host-side credential/inference broker: the container talks to a narrow local proxy, while reusable provider credentials remain outside the container. That should remain a separate component rather than expanding core fxs.

## Host services

`host.docker.internal` is not added by default. `--host-gateway` explicitly expands reachability to host-local services and should be used only when required for local inference or another intentional host service.

## Image and upgrade boundary

The image filesystem is read-only, so fx cannot safely replace its own executable in place. fxs therefore forces `FX_AUTO_UPGRADE=0` and treats the image as the update unit. Rebuild or pull a newer image to update fx; pin the fx version at image build time when reproducibility matters.

This means native fx and sandboxed fx are not guaranteed to be the same version unless the operator keeps them aligned. That is a version-management property, not a fork of the agent loop.

## Custom images

`FXS_IMAGE` / `--image` may point to any image containing an `fx` executable. The image controls the toolchain available to the agent and may itself contain software with additional risk. fxs still applies the same container authority boundary around that image.
