# syntax=docker/dockerfile:1.7
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

ARG FX_VERSION=

# FX_VERSION is intentionally first consumed here so a new fx release invalidates
# only the fx-install layer when the base image itself has not changed.
RUN set -eu; \
    if [ -n "$FX_VERSION" ]; then \
      curl -fsSL --retry 3 --connect-timeout 10 --max-time 60 https://fx.sh/setup.sh \
        | FX_INSTALL_DIR=/usr/local/bin bash -s -- "$FX_VERSION"; \
    else \
      curl -fsSL --retry 3 --connect-timeout 10 --max-time 60 https://fx.sh/setup.sh \
        | FX_INSTALL_DIR=/usr/local/bin bash; \
    fi; \
    fx --version

ENV HOME=/home/fx
WORKDIR /workspace
CMD ["fx"]
