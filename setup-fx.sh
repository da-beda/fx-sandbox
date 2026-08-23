#!/usr/bin/env bash
# Backwards-compatible entry point. The old self-embedding installer has been
# retired; installation now lives in install.sh only.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd -P)" || here=""
if [[ -n "$here" && -f "$here/install.sh" ]]; then
  exec bash "$here/install.sh" "$@"
fi

command -v curl >/dev/null 2>&1 || {
  printf 'setup-fx.sh: curl is required\n' >&2
  exit 1
}

ref="${FXS_REF:-main}"
url="${FXS_INSTALLER_URL:-https://raw.githubusercontent.com/da-beda/fx-sandbox/${ref}/install.sh}"
installer=""
if ! installer="$(curl -fsSL --retry 3 --connect-timeout 10 --max-time 60 "$url")"; then
  printf 'setup-fx.sh: failed to fetch installer: %s\n' "$url" >&2
  exit 1
fi
[[ -n "$installer" ]] || {
  printf 'setup-fx.sh: fetched installer was empty: %s\n' "$url" >&2
  exit 1
}
exec bash -c "$installer" bash "$@"
