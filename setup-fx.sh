#!/usr/bin/env bash
# Backwards-compatible entry point. The old self-embedding installer has been
# retired; installation now lives in install.sh only.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd -P)" || here=""
if [[ -n "$here" && -f "$here/install.sh" ]]; then
  exec bash "$here/install.sh" "$@"
fi
ref="${FXS_REF:-main}"
url="${FXS_INSTALLER_URL:-https://raw.githubusercontent.com/da-beda/fx-sandbox/${ref}/install.sh}"
exec bash -c "$(curl -fsSL "$url")" bash "$@"
