# Minimal reference runtime for fxs. It delegates fx installation to fx's own
# canonical installer instead of duplicating release/install logic here.
FROM ubuntu:24.04

LABEL org.opencontainers.image.title="fxs" \
      org.opencontainers.image.description="Minimal reference runtime for fx-sandbox" \
      org.opencontainers.image.source="https://github.com/da-beda/fx-sandbox"

# OS package freshness is a separate cache axis from FX_VERSION. Supported
# builders supply a small refresh token (daily for local fxs builds, unique per
# tagged release), so package updates are not hidden indefinitely behind a
# cached apt layer while an fx-only update can still reuse that layer.
ARG FXS_OS_REFRESH
RUN set -eu; \
    [ -n "$FXS_OS_REFRESH" ] || { \
      echo 'FXS_OS_REFRESH is required; use: fxs --build-image' >&2; \
      exit 1; \
    }; \
    case "$FXS_OS_REFRESH" in \
      *[!0-9A-Za-z._+-]*) echo "invalid FXS_OS_REFRESH: $FXS_OS_REFRESH" >&2; exit 1 ;; \
    esac; \
    : "os-refresh=$FXS_OS_REFRESH"; \
    apt-get update -qq; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl tar git bash; \
    rm -rf /var/lib/apt/lists/*

ARG FX_VERSION

# Supported builders (fxs, CI, releases) always resolve/pin FX_VERSION before
# Docker starts. Refuse an ambiguous raw build instead of letting Docker cache a
# remote "latest" lookup that is invisible to its cache key.
RUN set -eu; \
    [ -n "$FX_VERSION" ] || { \
      echo 'FX_VERSION is required; use: fxs --build-image' >&2; \
      exit 1; \
    }; \
    case "$FX_VERSION" in \
      *[!0-9A-Za-z._+-]*) echo "invalid FX_VERSION: $FX_VERSION" >&2; exit 1 ;; \
    esac; \
    curl -fsSL --retry 3 --connect-timeout 10 --max-time 60 https://fx.sh/setup.sh \
      | FX_INSTALL_DIR=/usr/local/bin bash -s -- "$FX_VERSION"; \
    fx --version

ENV HOME=/home/fx
WORKDIR /workspace
CMD ["fx"]
