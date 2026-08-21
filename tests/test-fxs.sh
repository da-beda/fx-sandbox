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