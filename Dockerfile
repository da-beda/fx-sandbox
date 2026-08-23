# Minimal reference runtime for fxs. It delegates fx installation to fx's own
# canonical installer instead of duplicating release/install logic here.
FROM ubuntu:24.04

LABEL org.opencontainers.image.title="fxs" \
      org.opencontainers.image.description="Minimal reference runtime for fx-sandbox" \
      org.opencontainers.image.source="https://github.com/da-beda/fx-sandbox"

# Keep OS dependencies in a layer that does not depend on FX_VERSION. When only
# fx changes, Docker can reuse this layer; when the Ubuntu base digest changes,
# --pull on the fxs build path correctly invalidates it.
RUN set -eu; \
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
