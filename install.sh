#!/usr/bin/env bash
# Alias for setup-fx.sh (same installer, shorter URL).
#   curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/install.sh | bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd -P)" || here=""
if [[ -n "$here" && -f "${here}/setup-fx.sh" ]]; then
  exec bash "${here}/setup-fx.sh" "$@"
fi
url="${SETUP_FX_URL:-https://raw.githubusercontent.com/da-beda/fx-sandbox/main/setup-fx.sh}"
exec bash -c "$(curl -fsSL "$url")" bash "$@"
