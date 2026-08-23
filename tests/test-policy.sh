#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"

fail() { printf 'policy: %s\n' "$*" >&2; exit 1; }

if grep -RniE 'glm-5|OPENAI_API_KEY|XAI_API_KEY|GROQ_API_KEY|python3|gateway\.py' \
  "$ROOT/fxs" "$ROOT/install.sh" "$ROOT/setup-fx.sh" "$ROOT/Dockerfile"; then
  fail "core policy violation"
fi

[[ ! -e "$ROOT/config/workspace.fx.json" ]] || fail "workspace config must not exist"

grep -Fq 'Same fx. Same agent loop. One host project. Less host authority.' "$ROOT/README.md" \
  || fail "final positioning missing"
grep -Fq 'FX_AUTO_UPGRADE=0' "$ROOT/fxs" \
  || fail "image update-unit policy missing"
grep -Fq 'FX_*)' "$ROOT/fxs" \
  || fail "generic upstream FX_* passthrough missing"
grep -Fq -- 'docker build --pull' "$ROOT/fxs" \
  || fail "explicit image refresh must pull the current base manifest"
grep -Fq 'fx cannot self-upgrade inside fxs' "$ROOT/fxs" \
  || fail "explicit fx upgrade boundary guidance missing"

# FX_VERSION must not invalidate the OS dependency layer. Keep the required ARG
# after the apt layer and before the canonical fx install layer.
apt_line="$(grep -n 'apt-get update -qq' "$ROOT/Dockerfile" | head -n 1 | cut -d: -f1)"
arg_line="$(grep -nE '^ARG FX_VERSION(=|$)' "$ROOT/Dockerfile" | head -n 1 | cut -d: -f1)"
fx_line="$(grep -n 'FX_INSTALL_DIR=/usr/local/bin' "$ROOT/Dockerfile" | head -n 1 | cut -d: -f1)"
[[ -n "$apt_line" && -n "$arg_line" && -n "$fx_line" ]] || fail "Dockerfile cache-layer markers missing"
[[ "$apt_line" -lt "$arg_line" && "$arg_line" -lt "$fx_line" ]] \
  || fail "FX_VERSION must only affect the fx-install layer"
grep -Fq 'FX_VERSION is required; use: fxs --build-image' "$ROOT/Dockerfile" \
  || fail "reference image must reject ambiguous raw latest builds"

# Image refreshes must never use the installed fxs data/state directory as
# Docker build context. The runtime prepares a one-file temporary context, and
# the repository itself denies context contents by default as defense in depth.
grep -Fq 'fxs-build.XXXXXX' "$ROOT/fxs" \
  || fail "isolated Docker build context is missing"
grep -Fq 'cp "$DOCKERFILE" "$build_context/Dockerfile"' "$ROOT/fxs" \
  || fail "reference Dockerfile is not copied into isolated build context"
first_context_rule="$(grep -vE '^[[:space:]]*(#|$)' "$ROOT/.dockerignore" | head -n 1)"
[[ "$first_context_rule" == '**' ]] || fail ".dockerignore must deny context by default"
grep -Fxq '!Dockerfile' "$ROOT/.dockerignore" || fail "Dockerfile allow-rule missing from .dockerignore"

# Post-refactor docs/examples must describe the actual boundary rather than the
# retired web/installer architecture.
grep -Fq '**/__pycache__/' "$ROOT/.gitignore" || fail "generic Python cache ignore missing"
if grep -Fq 'web/__pycache__/' "$ROOT/.gitignore"; then
  fail "stale pre-refactor web ignore remains"
fi
grep -Fq 'does not imply host or LAN isolation' "$ROOT/docs/THREAT_MODEL.md" \
  || fail "network-boundary nuance missing from threat model"
grep -Fq 'build context' "$ROOT/docs/THREAT_MODEL.md" \
  || fail "Docker build-context boundary is not documented"
grep -Fq 'Supply-chain boundary' "$ROOT/docs/THREAT_MODEL.md" \
  || fail "upstream supply-chain trust boundary is not documented"
if grep -Fq 'v0.2.0' "$ROOT/README.md"; then
  fail "README still references nonexistent v0.2.0 tag"
fi

# The illustrative Compose path must not quietly become a weaker second image
# builder or run as root by default.
if grep -Eq '^[[:space:]]+build:' "$ROOT/examples/docker-compose.yml"; then
  fail "Compose example must use an image built by the authoritative fxs path"
fi
grep -Fq 'user: "${FXS_UID:-1000}:${FXS_GID:-1000}"' "$ROOT/examples/docker-compose.yml" \
  || fail "Compose example must set a non-root uid/gid"
grep -Fq 'FX_AUTO_UPGRADE=0' "$ROOT/examples/docker-compose.yml" \
  || fail "Compose example must disable in-image fx self-upgrade"

# Retained optional surfaces get their own tests without becoming core runtime
# dependencies. Release metadata must record the embedded upstream fx version.
grep -Fq 'python3 extras/gateway/test_gateway.py' "$ROOT/.github/workflows/ci.yml" \
  || fail "gateway extras are not exercised in CI"
grep -Fq 'python3 extras/ui/test_server.py' "$ROOT/.github/workflows/ci.yml" \
  || fail "UI extras are not exercised in CI"
grep -Fq 'shellcheck --severity=warning' "$ROOT/.github/workflows/ci.yml" \
  || fail "shell lint is not exercised in CI"
grep -Fq 'UPSTREAM_FX_VERSION' "$ROOT/.github/workflows/release-image.yml" \
  || fail "release does not record embedded fx version"
[[ -f "$ROOT/.github/workflows/upstream-canary.yml" ]] \
  || fail "upstream compatibility canary missing"

# All third-party workflow actions must be pinned to immutable 40-hex commit
# SHAs. Dependabot keeps those pinned dependencies current without returning to
# mutable major-version refs in privileged workflows.
if grep -RniE '^[[:space:]]*-[[:space:]]+uses:[[:space:]]+[^[:space:]#]+@v[0-9]' \
  "$ROOT/.github/workflows"; then
  fail "GitHub Actions must not use mutable @vN refs"
fi
while IFS= read -r use_line; do
  ref="${use_line##*@}"
  ref="${ref%% *}"
  [[ "$ref" =~ ^[0-9a-f]{40}$ ]] || fail "GitHub Action is not pinned to a 40-hex SHA: $use_line"
done < <(grep -RhE '^[[:space:]]*-[[:space:]]+uses:[[:space:]]+' "$ROOT/.github/workflows")
[[ -f "$ROOT/.github/dependabot.yml" ]] || fail "Dependabot config missing for pinned GitHub Actions"
grep -Fq 'package-ecosystem: github-actions' "$ROOT/.github/dependabot.yml" \
  || fail "Dependabot is not configured for GitHub Actions"

printf 'test-policy: ok\n'
