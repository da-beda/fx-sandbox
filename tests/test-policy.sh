#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"

if grep -RniE 'glm-5|OPENAI_API_KEY|XAI_API_KEY|GROQ_API_KEY|python3|gateway\.py' \
  "$ROOT/fxs" "$ROOT/install.sh" "$ROOT/setup-fx.sh" "$ROOT/Dockerfile"; then
  echo "core policy violation" >&2
  exit 1
fi

[[ ! -e "$ROOT/config/workspace.fx.json" ]] || { echo "workspace config must not exist" >&2; exit 1; }
[[ ! -e "$ROOT/extras" ]] || { echo "provider/UI experiments must not live on main" >&2; exit 1; }
[[ ! -e "$ROOT/examples" ]] || { echo "alternate sandbox launchers must not live on main" >&2; exit 1; }

grep -Fq 'Same fx. Same agent loop. One host project. Less host authority.' "$ROOT/README.md" \
  || { echo "final positioning missing" >&2; exit 1; }
grep -Fq 'FX_AUTO_UPGRADE=0' "$ROOT/fxs" \
  || { echo "image update-unit policy missing" >&2; exit 1; }
grep -Fq 'FX_*)' "$ROOT/fxs" \
  || { echo "generic upstream FX_* passthrough missing" >&2; exit 1; }
grep -Fq 'upstream-canary' "$ROOT/README.md" "$ROOT/.github/workflows/upstream-canary.yml" \
  || { echo "upstream drift canary missing" >&2; exit 1; }

printf 'test-policy: ok\n'
