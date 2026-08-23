#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
FXS="$ROOT/fxs"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/home" "$TMP/project"

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
assert_has() {
  if [[ "$1" != *"$2"* ]]; then
    printf 'output: %s\n' "$1" >&2
    fail "expected output to contain: $2"
  fi
}
assert_not_has() {
  if [[ "$1" == *"$2"* ]]; then
    printf 'output: %s\n' "$1" >&2
    fail "expected output not to contain: $2"
  fi
}

bash -n "$FXS"

# Bash 3.2 (the stock macOS shell) and newer Bash versions render printf %q
# slightly differently. Assert invariant argv tokens rather than whitespace-
# joined command fragments.
out="$(HOME="$TMP/home" TERM=xterm "$FXS" --dry-run -w "$TMP/project" --model vendor/model --steps 40 ask hello)"
assert_has "$out" "--cap-drop"
assert_has "$out" "ALL"
assert_has "$out" "no-new-privileges:true"
assert_has "$out" "FX_PERMISSION_MODE=yolo"
assert_has "$out" "FX_AUTO_UPGRADE=0"
assert_has "$out" "FX_NO_OPEN_BROWSER=1"
assert_has "$out" "FX_MODEL"
assert_has "$out" "FX_MAX_AGENT_STEPS"
assert_has "$out" "vendor/model"
assert_has "$out" "fx"
assert_has "$out" "ask"
assert_has "$out" "hello"
assert_not_has "$out" "--memory"
assert_not_has "$out" "--cpus"
assert_not_has "$out" "--pids-limit"
assert_not_has "$out" "host.docker.internal"
[[ ! -e "$TMP/project/.fx.json" ]] || fail "fxs created .fx.json"

# Upstream FX_* controls pass through without a maintained allowlist. Wrapper-
# owned controls remain authoritative; a host attempt to re-enable self-upgrade
# must not fight the read-only image filesystem.
out="$(HOME="$TMP/home" FX_TRACE=1 FX_TRACE_SCOPES=agent FX_SYNC_UPDATES=off \
  FX_FUTURE_TEST=sentinel FX_AUTO_UPGRADE=1 \
  "$FXS" --dry-run -w "$TMP/project")"
assert_has "$out" "FX_TRACE"
assert_has "$out" "FX_TRACE_SCOPES"
assert_has "$out" "FX_SYNC_UPDATES"
assert_has "$out" "FX_FUTURE_TEST"
assert_has "$out" "FX_AUTO_UPGRADE=0"
assert_not_has "$out" "FX_AUTO_UPGRADE=1"

# Explicit upstream self-upgrade cannot work against the intentionally read-only
# image. Fail before Docker launch with the correct image-refresh guidance.
if HOME="$TMP/home" "$FXS" --dry-run upgrade >/tmp/fxs-upgrade.out 2>/tmp/fxs-upgrade.err; then
  fail "fxs forwarded fx upgrade into the read-only image"
fi
grep -Fq 'fxs --build-image' /tmp/fxs-upgrade.err || fail "fxs upgrade did not explain the image update path"

# An unpinned image refresh resolves the current stable fx version on the host
# and passes exact, cache-visible fx + OS-refresh build args. Explicit fx pins
# bypass latest-version resolution. The OS token is controlled in this test so
# cache behavior can be asserted deterministically.
#
# Reproduce the installed layout too: the reference Dockerfile lives beside
# fxs-owned state. The Docker daemon must receive only a temporary one-file build
# context, never the containing state directory.
mkdir -p "$TMP/buildbin" "$TMP/data/state/project/home"
cp "$ROOT/Dockerfile" "$TMP/data/Dockerfile"
printf 'DO_NOT_SEND_ME\n' > "$TMP/data/state/project/home/secret"
cat > "$TMP/buildbin/docker" <<'EOF_DOCKER'
#!/usr/bin/env bash
case "${1:-}" in
  info) exit 0 ;;
  build)
    shift
    printf '%s\n' "$@" > "${FXS_BUILD_LOG:?}"
    context=""
    for arg in "$@"; do context="$arg"; done
    printf '%s\n' "$context" > "${FXS_CONTEXT_PATH_LOG:?}"
    (cd "$context" && /bin/ls -A) > "${FXS_CONTEXT_LOG:?}"
    exit 0
    ;;
  *) exit 0 ;;
esac
EOF_DOCKER
cat > "$TMP/buildbin/curl" <<'EOF_CURL'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${FXS_CURL_LOG:?}"
printf '0.0.99\n'
EOF_CURL
chmod +x "$TMP/buildbin/docker" "$TMP/buildbin/curl"
: > "$TMP/curl.log"
PATH="$TMP/buildbin:$PATH" HOME="$TMP/home" FXS_OS_REFRESH=2026-08-23 \
  FXS_BUILD_LOG="$TMP/build.log" FXS_CONTEXT_LOG="$TMP/context.log" \
  FXS_CONTEXT_PATH_LOG="$TMP/context-path.log" FXS_CURL_LOG="$TMP/curl.log" \
  FXS_DOCKERFILE="$TMP/data/Dockerfile" FXS_IMAGE=fxs-refresh-test \
  "$FXS" --build-image >/dev/null
build_out="$(cat "$TMP/build.log")"
assert_has "$build_out" "--pull"
assert_has "$build_out" "--build-arg"
assert_has "$build_out" "FXS_OS_REFRESH=2026-08-23"
assert_has "$build_out" "FX_VERSION=0.0.99"
curl_out="$(cat "$TMP/curl.log")"
assert_has "$curl_out" "https://releases.fx.sh/latest.txt"
context_out="$(cat "$TMP/context.log")"
[[ "$context_out" == "Dockerfile" ]] || fail "Docker build context exposed files beyond Dockerfile: $context_out"
context_path="$(cat "$TMP/context-path.log")"
[[ "$context_path" != "$TMP/data" ]] || fail "Docker build used the fxs data/state directory as context"
[[ ! -e "$context_path" ]] || fail "temporary Docker build context was not cleaned up"

curl_before="$curl_out"
PATH="$TMP/buildbin:$PATH" HOME="$TMP/home" FXS_OS_REFRESH=2026-08-23 \
  FXS_BUILD_LOG="$TMP/build.log" FXS_CONTEXT_LOG="$TMP/context.log" \
  FXS_CONTEXT_PATH_LOG="$TMP/context-path.log" FXS_CURL_LOG="$TMP/curl.log" \
  FXS_DOCKERFILE="$TMP/data/Dockerfile" FXS_IMAGE=fxs-refresh-test \
  "$FXS" --build-image --fx-version 9.9.9 >/dev/null
build_out="$(cat "$TMP/build.log")"
assert_has "$build_out" "--pull"
assert_has "$build_out" "FXS_OS_REFRESH=2026-08-23"
assert_has "$build_out" "FX_VERSION=9.9.9"
curl_after="$(cat "$TMP/curl.log")"
[[ "$curl_after" == "$curl_before" ]] || fail "pinned build unexpectedly resolved latest fx"

# Explicit versions/tokens are untrusted input and must not become arbitrary
# Docker build-arg content. Fail before docker build and before any latest lookup.
: > "$TMP/build.log"
curl_before="$curl_after"
if PATH="$TMP/buildbin:$PATH" HOME="$TMP/home" FXS_OS_REFRESH=2026-08-23 \
  FXS_BUILD_LOG="$TMP/build.log" FXS_CONTEXT_LOG="$TMP/context.log" \
  FXS_CONTEXT_PATH_LOG="$TMP/context-path.log" FXS_CURL_LOG="$TMP/curl.log" \
  FXS_DOCKERFILE="$TMP/data/Dockerfile" FXS_IMAGE=fxs-refresh-test \
  "$FXS" --build-image --fx-version 'bad/value' >/dev/null 2>&1; then
  fail "invalid fx version was accepted"
fi
[[ ! -s "$TMP/build.log" ]] || fail "invalid fx version reached docker build"
curl_after="$(cat "$TMP/curl.log")"
[[ "$curl_after" == "$curl_before" ]] || fail "invalid pinned build unexpectedly resolved latest fx"

: > "$TMP/build.log"
if PATH="$TMP/buildbin:$PATH" HOME="$TMP/home" FXS_OS_REFRESH='bad/token' \
  FXS_BUILD_LOG="$TMP/build.log" FXS_CONTEXT_LOG="$TMP/context.log" \
  FXS_CONTEXT_PATH_LOG="$TMP/context-path.log" FXS_CURL_LOG="$TMP/curl.log" \
  FXS_DOCKERFILE="$TMP/data/Dockerfile" FXS_IMAGE=fxs-refresh-test \
  "$FXS" --build-image --fx-version 9.9.9 >/dev/null 2>&1; then
  fail "invalid OS refresh token was accepted"
fi
[[ ! -s "$TMP/build.log" ]] || fail "invalid OS refresh token reached docker build"

out="$(HOME="$TMP/home" "$FXS" --dry-run -w "$TMP/project" --ask --host-gateway --memory 4g --cpus 6 --pids 512)"
assert_has "$out" "FX_PERMISSION_MODE=ask"
assert_has "$out" "host.docker.internal:host-gateway"
assert_has "$out" "--memory"
assert_has "$out" "4g"
assert_has "$out" "--cpus"
assert_has "$out" "6"
assert_has "$out" "--pids-limit"
assert_has "$out" "512"

out="$(HOME="$TMP/home" "$FXS" --dry-run -w "$TMP/project" --offline --read-only-workspace)"
assert_has "$out" "--network"
assert_has "$out" "none"
assert_has "$out" "readonly"

if HOME="$TMP/home" "$FXS" --dry-run -w "$TMP/home" >/dev/null 2>&1; then
  fail "dangerous HOME workspace was accepted"
fi

mkdir -p "$TMP/nodocker"
for c in bash dirname pwd sha256sum shasum awk printf env; do
  p="$(command -v "$c" 2>/dev/null || true)"
  [[ -n "$p" ]] && ln -sf "$p" "$TMP/nodocker/$c"
done
cat > "$TMP/nodocker/id" <<'EOF_ID'
#!/usr/bin/env bash
case "${1:-}" in
  -u) echo 1000 ;;
  -g) echo 1000 ;;
  *) echo 1000 ;;
esac
EOF_ID
chmod +x "$TMP/nodocker/id"
if PATH="$TMP/nodocker" HOME="$TMP/home" /bin/bash "$FXS" -w "$TMP/project" >/tmp/fxs-test.out 2>/tmp/fxs-test.err; then
  fail "fxs silently ran without Docker"
fi
grep -q "Docker is not available" /tmp/fxs-test.err || fail "missing fail-closed Docker error"

printf 'test-fxs: ok\n'
