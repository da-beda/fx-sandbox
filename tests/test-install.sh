#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
INSTALL="$ROOT/install.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/home" "$TMP/bin" "$TMP/data" "$TMP/fakebin"

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

bash -n "$INSTALL"
bash -n "$ROOT/setup-fx.sh"

HOME="$TMP/home" FXS_INSTALL_DIR="$TMP/bin" FXS_DATA_DIR="$TMP/data" \
  bash "$INSTALL" --fxs-only --no-build --non-interactive >/dev/null
[[ -x "$TMP/bin/fxs" ]] || fail "fxs was not installed"
[[ -f "$TMP/data/Dockerfile" ]] || fail "Dockerfile was not installed"
[[ ! -e "$TMP/bin/fx" ]] || fail "fxs-only installed native fx"

cat > "$TMP/fakebin/curl" <<'EOF_CURL'
#!/usr/bin/env bash
cat <<'EOF_UPSTREAM'
#!/usr/bin/env bash
mkdir -p "$HOME/.local/bin"
printf '#!/usr/bin/env bash\necho fake-fx\n' > "$HOME/.local/bin/fx"
chmod +x "$HOME/.local/bin/fx"
printf '%s\n' "$*" > "$HOME/native-installer-args"
EOF_UPSTREAM
EOF_CURL
chmod +x "$TMP/fakebin/curl"
PATH="$TMP/fakebin:$PATH" HOME="$TMP/home" FXS_INSTALL_DIR="$TMP/bin" FXS_DATA_DIR="$TMP/data" \
  bash "$INSTALL" --native-only --fx-version 9.9.9 --non-interactive >/dev/null
[[ -x "$TMP/home/.local/bin/fx" ]] || fail "native installer was not delegated"
[[ ! -e "$TMP/bin/setup-fx" ]] || fail "native-only installed fxs aliases"
grep -Fq '9.9.9' "$TMP/home/native-installer-args" || fail "fx version was not delegated upstream"

if HOME="$TMP/home" bash "$INSTALL" --native-only --fx-version 'bad/value' --non-interactive >/dev/null 2>&1; then
  fail "invalid installer fx version was accepted"
fi

if HOME="$TMP/home" bash "$INSTALL" --fxs-only --with-docker >/dev/null 2>&1; then
  fail "legacy Docker provisioning flag was accepted"
fi

# Remote fxs updates are all-or-nothing for the wrapper/Dockerfile pair. Run a
# copied installer without sibling source files so it must take the remote path;
# make the first fetch succeed and the second fail, then ensure the previous
# installation remains untouched.
cp "$INSTALL" "$TMP/remote-install.sh"
printf '#!/usr/bin/env bash\necho old-wrapper\n' > "$TMP/bin/fxs"
chmod +x "$TMP/bin/fxs"
printf 'OLD_DOCKERFILE\n' > "$TMP/data/Dockerfile"
cat > "$TMP/fakebin/curl" <<'EOF_REMOTE_CURL'
#!/usr/bin/env bash
out=""
url=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o)
      out="$2"
      shift 2
      ;;
    http://*|https://*)
      url="$1"
      shift
      ;;
    *) shift ;;
  esac
done
case "$url" in
  */fxs)
    printf '#!/usr/bin/env bash\necho new-wrapper\n' > "$out"
    exit 0
    ;;
  */Dockerfile)
    printf 'PARTIAL_NEW_DOCKERFILE\n' > "$out"
    exit 22
    ;;
  *) exit 22 ;;
esac
EOF_REMOTE_CURL
chmod +x "$TMP/fakebin/curl"
if PATH="$TMP/fakebin:$PATH" HOME="$TMP/home" FXS_INSTALL_DIR="$TMP/bin" FXS_DATA_DIR="$TMP/data" \
  bash "$TMP/remote-install.sh" --fxs-only --no-build --non-interactive >/dev/null 2>&1; then
  fail "partial remote fxs update unexpectedly succeeded"
fi
grep -Fq 'old-wrapper' "$TMP/bin/fxs" || fail "failed update replaced the existing fxs wrapper"
grep -Fq 'OLD_DOCKERFILE' "$TMP/data/Dockerfile" || fail "failed update replaced the existing Dockerfile"

# The compatibility shim must not turn an empty/failed remote fetch into a
# successful no-op. A copied shim has no adjacent install.sh and therefore takes
# the remote path.
cp "$ROOT/setup-fx.sh" "$TMP/setup-remote.sh"
cat > "$TMP/fakebin/curl" <<'EOF_FAIL_CURL'
#!/usr/bin/env bash
exit 22
EOF_FAIL_CURL
chmod +x "$TMP/fakebin/curl"
if PATH="$TMP/fakebin:$PATH" HOME="$TMP/home" bash "$TMP/setup-remote.sh" --fxs-only >/dev/null 2>&1; then
  fail "setup compatibility shim accepted a failed installer fetch"
fi

printf 'test-install: ok\n'
