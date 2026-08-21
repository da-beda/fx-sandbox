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

if HOME="$TMP/home" bash "$INSTALL" --fxs-only --with-docker >/dev/null 2>&1; then
  fail "legacy Docker provisioning flag was accepted"
fi

printf 'test-install: ok\n'
