# syntax=docker/dockerfile:1.7
# Minimal reference runtime for fxs. It delegates fx installation to fx's own
# canonical installer instead of duplicating release/install logic here.
FROM ubuntu:24.04

ARG FX_VERSION=

LABEL org.opencontainers.image.title="fxs" \
      org.opencontainers.image.description="Minimal reference runtime for fx-sandbox" \
      org.opencontainers.image.source="https://github.com/da-beda/fx-sandbox"

RUN set -eu; \
    apt-get update -qq; \
    apt-get install -y --no-install-recommends ca-certificates curl tar git bash; \
    rm -rf /var/lib/apt/lists/*; \
    if [ -n "$FX_VERSION" ]; then \
      curl -fsSL https://fx.sh/setup.sh | FX_INSTALL_DIR=/usr/local/bin bash -s -- "$FX_VERSION"; \
    else \
      curl -fsSL https://fx.sh/setup.sh | FX_INSTALL_DIR=/usr/local/bin bash; \
    fi; \
    fx --version

ENV HOME=/home/fx
WORKDIR /workspace
CMD ["fx"]
