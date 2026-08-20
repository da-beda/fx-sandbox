#!/usr/bin/env bash
# fx-entrypoint — last-line safety checks before exec'ing fx inside the image.
#
# This is defense in depth. The real policy lives in run-fx.sh (how docker
# is invoked). If someone `docker run`s the image by hand, we still refuse
# the obviously-dangerous cases.
set -euo pipefail

log()  { printf '[fx-entrypoint] %s\n' "$*" >&2; }
warn() { printf '[fx-entrypoint] warn: %s\n' "$*" >&2; }
die()  { printf '[fx-entrypoint] error: %s\n' "$*" >&2; exit 1; }

umask 077

export HOME="${HOME:-/home/fx}"
export FX_DISABLE_KEYCHAIN="${FX_DISABLE_KEYCHAIN:-1}"
export FX_MODEL="${FX_MODEL:-zai/glm-5.2}"
export FX_PERMISSION_MODE="${FX_PERMISSION_MODE:-auto}"
export FX_HOME="${FX_HOME:-${HOME}/.fx}"

# ---------------------------------------------------------------------------
# refuse to be a confused deputy
# ---------------------------------------------------------------------------
if [[ "$(id -u)" -eq 0 && "${FX_ALLOW_ROOT:-}" != "1" ]]; then
  die "refusing to run as root. run-fx.sh maps your host uid, or set FX_ALLOW_ROOT=1 (don't)."
fi

if [[ -e /var/run/docker.sock || -e /run/docker.sock ]]; then
  die "Docker socket is mounted inside the sandbox. That breaks isolation. Unmount it."
fi

if [[ -d /host || -d /host-root ]]; then
  die "a host-root mount is present (/host). That is not a sandbox."
fi

case "${PWD}" in
  /|/root|/home|/etc|/usr|/var|/boot|/proc|/sys)
    die "refusing to use ${PWD} as the workspace"
    ;;
esac

# Writable home: the runtime usually gives us a tmpfs or named volume.
# If the operator overrode --user to a uid that does not own /home/fx,
# fall back to a tmpfs-backed path under /tmp.
ensure_dir() {
  local d="$1" mode="${2:-700}"
  mkdir -p "$d" 2>/dev/null || true
  chmod "$mode" "$d" 2>/dev/null || true
  [[ -d "$d" && -w "$d" ]]
}

if ! ensure_dir "$HOME" 700; then
  HOME="/tmp/fx-home-$(id -u)"
  export HOME
  export FX_HOME="${HOME}/.fx"
  ensure_dir "$HOME" 700 || die "HOME ${HOME} is not writable"
  warn "HOME remapped to ${HOME} (uid $(id -u) cannot write the image home)"
fi
ensure_dir "$FX_HOME" 700 || die "cannot create ${FX_HOME}"

if [[ ! -f "${FX_HOME}/settings.json" ]]; then
  if [[ -r /usr/local/share/fx-sandbox/settings.json ]]; then
    cp /usr/local/share/fx-sandbox/settings.json "${FX_HOME}/settings.json"
    chmod 0600 "${FX_HOME}/settings.json" || true
  fi
fi

# Optional project-level defaults. Never overwrite a repo's own .fx.json.
if [[ -d /workspace && ! -e /workspace/.fx.json && -r /usr/local/share/fx-sandbox/workspace.fx.json ]]; then
  if [[ -w /workspace ]]; then
    cp /usr/local/share/fx-sandbox/workspace.fx.json /workspace/.fx.json
  fi
fi

if [[ -z "${FX_UPSTREAM:-${OPENAI_BASE_URL:-}}" ]]; then
  if [[ -z "${AI_GATEWAY_API_KEY:-}" && -z "${VERCEL_OIDC_TOKEN:-}" ]]; then
    warn "no AI_GATEWAY_API_KEY or VERCEL_OIDC_TOKEN in the environment."
    warn "fx will not be able to call a model until you pass one (see run-fx.sh)."
  fi
  # Never dump the key. Confirm only that it *looks* like a gateway token.
  if [[ -n "${AI_GATEWAY_API_KEY:-}" && ! "${AI_GATEWAY_API_KEY}" =~ ^vck_ ]]; then
    warn "AI_GATEWAY_API_KEY does not start with vck_ — is this the right secret?"
  fi
else
  # OpenAI-compatible /v1: run the translator on loopback. fx will not
  # send traffic anywhere else.
  _gw_py="/usr/local/share/fx-sandbox/gateway.py"
  _gw_listen="127.0.0.1:18787"
  _up="${FX_UPSTREAM:-${OPENAI_BASE_URL}}"
  if [[ ! -f "$_gw_py" ]] || ! command -v python3 >/dev/null 2>&1; then
    warn "OpenAI-compatible upstream is set, but this image cannot translate it."
    warn "Rebuild the image: fxs build"
  else
    python3 "$_gw_py" --listen "$_gw_listen" --upstream "$_up" \
      >/tmp/fx-gateway.log 2>&1 &
    _i=0
    while [[ $_i -lt 40 ]]; do
      if python3 -c "import urllib.request; urllib.request.urlopen('http://${_gw_listen}/healthz', timeout=0.2).read()" >/dev/null 2>&1; then
        break
      fi
      sleep 0.05
      _i=$((_i + 1))
    done
    export FX_GATEWAY_BASE_URL="http://${_gw_listen}"
    export FX_GATEWAY_CHAT_URL="http://${_gw_listen}/v3/ai/language-model"
    if [[ -z "${AI_GATEWAY_API_KEY:-}" ]]; then
      export AI_GATEWAY_API_KEY=local
    fi
    log "openai gateway → ${_up}"
  fi
fi

# Default command is `fx`. Prefix it for fx subcommands and for flags
# like `--yolo` (`exec --yolo` is a bash error).
if [[ $# -eq 0 ]]; then
  set -- fx
elif [[ "$1" == -* ]]; then
  set -- fx "$@"
elif [[ "$1" != fx && "$1" != /usr/local/bin/fx && "$1" != bash && "$1" != sh ]]; then
  case "$1" in
    ask|doctor|status|models|permissions|credits|balance|usage|sessions|session|pr|issue|help)
      set -- fx "$@"
      ;;
  esac
fi

# Extra guard: yolo is an explicit, loud choice.
if [[ "${FX_PERMISSION_MODE}" == "yolo" || " $* " == *" --yolo "* ]]; then
  warn "YOLO requested: fx permissions AND sandboxing are disabled."
  warn "You are relying entirely on this container's isolation + the mounted volume."
fi

exec "$@"
