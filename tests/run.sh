#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd -P)"
"$here/test-fxs.sh"
"$here/test-install.sh"
"$here/test-policy.sh"
