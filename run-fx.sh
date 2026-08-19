#!/usr/bin/env bash
# Internal docker launcher. Prefer the public command:  fxs run
#
#   fxs run                         # interactive fx in $PWD
#   fxs ask "what is 17*19?"
#   fxs run -w ~/src/app
#   fxs run --read-only-workspace ask "review this repo"
#
# Required on the host:
#   docker, the image built by setup-fx.sh --build-image (or `docker compose build`)
#   AI_GATEWAY_API_KEY in the environment (or --env-file)
set -euo pipefail
IFS=$'\n\t'

# Resolve this script even when invoked via a symlink (~/.local/bin/run-fx).
_resolve_self_dir() {
  local src="${BASH_SOURCE[0]}"
  local target
  if [[ -L "$src" ]]; then
    if command -v readlink >/dev/null 2>&1; then
      if target="$(readlink -f "$src" 2>/dev/null)" && [[ -n "$target" ]]; then
        src="$target"
      else
        target="$(readlink "$src")"
        case "$target" in
          /*) src="$target" ;;
          *)  src="$(dirname "$src")/${target}" ;;
        esac
      fi
    fi
  fi
  (cd "$(dirname "$src")" && pwd -P)
}

readonly SCRIPT_DIR="$(_resolve_self_dir)"
IMAGE="${FX_IMAGE_NAME:-fx-sandbox:latest}"
WORKSPACE="${FX_WORKSPACE:-$PWD}"
ENV_FILE=""
NAME=""
PERSIST_STATE=0
READ_ONLY_WS=0
GITCONFIG=0
NETWORK="${FX_NETWORK:-bridge}"
MEMORY="${FX_MEMORY:-2g}"
CPUS="${FX_CPUS:-2}"
PIDS="${FX_PIDS:-256}"
ALLOW_YOLO=0
PULL=0
DRY=0

usage() {
  cat <<'EOF'
fxs run — fx inside a locked-down container

USAGE
  fxs run [flags] [--] [fx-args...]
  fxs ask [fx-args...]

FLAGS
  -w, --workspace DIR    Host directory to mount at /workspace (default: $PWD)
  --read-only-workspace  Mount the project read-only
  --env-file FILE        Extra env file (must be 0600)
  --name NAME            Container name (default: ephemeral)
  --persist-state        Keep ~/.fx sessions in a named docker volume
  --gitconfig            Mount $HOME/.gitconfig read-only
  --network NET          Default bridge. `none` denies egress.
  --memory SIZE          default 2g
  --cpus N               default 2
  --pids N               default 256
  --image NAME           default fx-sandbox:latest
  --allow-yolo           Permit --yolo (off by default)
  --dry-run              Print the docker argv and exit
  -h, --help

Always on: --user $uid:$gid, --cap-drop ALL, no-new-privileges,
read-only rootfs, tmpfs home, no docker.sock. Refuses /, $HOME, /Users.
EOF
}

die()  { printf 'fxs: error: %s\n' "$*" >&2; exit 1; }
warn() { printf 'fxs: warn: %s\n' "$*" >&2; }
log()  { printf 'fxs: %s\n' "$*" >&2; }

abs_path() {
  local target="$1"
  case "$target" in
    "~")  target="$HOME" ;;
    "~/"*) target="${HOME}/${target#~/}" ;;
  esac
  case "$target" in
    /*) ;;
    *) target="${PWD}/${target}" ;;
  esac
  local dir base
  dir="$(dirname "$target")"
  base="$(basename "$target")"
  (cd "$dir" && printf '%s/%s\n' "$(pwd -P)" "$base")
}

is_dangerous_workspace() {
  local ws="$1"
  case "$ws" in
    /|/bin|/boot|/dev|/etc|/lib|/lib64|/proc|/root|/run|/sbin|/sys|/usr|/var)
      return 0 ;;
    /Users|/System|/Library|/Applications|/private|/Volumes|/opt/homebrew)
      return 0 ;;
  esac
  [[ "$ws" == "${HOME}" ]] && return 0
  [[ "$ws" == "${HOME}/" ]] && return 0
  case "$ws" in
    "${HOME}/.ssh"|"${HOME}/.gnupg"|"${HOME}/.aws"|"${HOME}/.config"|"${HOME}/Library")
      return 0 ;;
  esac
  [[ -S "${ws}/docker.sock" || -S "${ws}/var/run/docker.sock" ]] && return 0
  return 1
}

contains_secret_dir() {
  local ws="$1"
  local n
  for n in .ssh .gnupg .aws .azure .kube .docker .password-store; do
    if [[ -e "${ws}/${n}" ]]; then
      printf '%s\n' "$n"
      return 0
    fi
  done
  return 1
}

# ---------------------------------------------------------------------------
# args: wrapper flags stop at first unknown / `--`
# ---------------------------------------------------------------------------
FX_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -w|--workspace)
      [[ $# -ge 2 ]] || die "--workspace needs a directory"
      WORKSPACE="$2"; shift 2
      ;;
    --read-only-workspace) READ_ONLY_WS=1; shift ;;
    --env-file)
      [[ $# -ge 2 ]] || die "--env-file needs a path"
      ENV_FILE="$2"; shift 2
      ;;
    --name) NAME="$2"; shift 2 ;;
    --persist-state) PERSIST_STATE=1; shift ;;
    --gitconfig) GITCONFIG=1; shift ;;
    --network) NETWORK="$2"; shift 2 ;;
    --memory) MEMORY="$2"; shift 2 ;;
    --cpus) CPUS="$2"; shift 2 ;;
    --pids) PIDS="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --pull) PULL=1; shift ;;
    --allow-yolo) ALLOW_YOLO=1; shift ;;
    --dry-run) DRY=1; shift ;;
    --) shift; FX_ARGS+=("$@"); break ;;
    --yolo)
      if [[ $ALLOW_YOLO -eq 0 ]]; then
        die "--yolo is blocked. rerun with --allow-yolo if you really want it (container-only safety net remains)."
      fi
      FX_ARGS+=("$1"); shift
      ;;
    -*)
      # unknown dashed arg: assume it belongs to fx
      FX_ARGS+=("$1"); shift
      ;;
    *)
      FX_ARGS+=("$@")
      break
      ;;
  esac
done

command -v docker >/dev/null 2>&1 || {
  printf 'fxs: error: docker is not on PATH\n' >&2
  printf '  macOS : brew install --cask docker && open -a Docker\n' >&2
  printf '  Linux : fxs install --with-docker\n' >&2
  printf '  native: on macOS, skip Docker — fx already uses the OS sandbox\n' >&2
  exit 1
}

if ! docker info >/dev/null 2>&1; then
  printf 'fxs: error: Docker is installed but the daemon is not running\n' >&2
  printf '  macOS : open -a Docker   # wait until the whale is idle\n' >&2
  printf '          then: docker info && fxs run\n' >&2
  printf '  Linux : sudo systemctl start docker\n' >&2
  printf '  native: on macOS you can skip Docker:  fx ask --no-save "hi"\n' >&2
  exit 1
fi

[[ "$(id -u)" -eq 0 ]] && die "do not run this wrapper as root; it would map uid 0 into the container"

WORKSPACE="$(abs_path "$WORKSPACE")"
[[ -d "$WORKSPACE" ]] || die "workspace is not a directory: ${WORKSPACE}"
if [[ "$WORKSPACE" == *","* ]]; then
  die "workspace path contains a comma; docker --mount cannot take it: ${WORKSPACE}"
fi
is_dangerous_workspace "$WORKSPACE" && die "refusing to mount ${WORKSPACE} (too broad / sensitive). pick a project directory."

if secret="$(contains_secret_dir "$WORKSPACE")"; then
  warn "workspace contains ${secret}/ — the agent will be able to read it."
  if [[ -t 0 && -z "${FX_I_UNDERSTAND_SECRETS:-}" ]]; then
    printf 'continue? [y/N] ' >&2
    read -r ans || ans=""
    [[ "${ans}" =~ ^[Yy]$ ]] || die "aborted"
  fi
fi

if [[ -n "$ENV_FILE" ]]; then
  [[ -f "$ENV_FILE" ]] || die "env file not found: ${ENV_FILE}"
  local_mode="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%OLp' "$ENV_FILE")"
  if [[ "$local_mode" != "600" && "$local_mode" != "0600" ]]; then
    die "env file ${ENV_FILE} must be mode 0600 (is ${local_mode})"
  fi
fi

if [[ -z "${AI_GATEWAY_API_KEY:-}" && -z "$ENV_FILE" && -z "${VERCEL_OIDC_TOKEN:-}" ]]; then
  # Convenient fallback: the file setup-fx.sh may have written.
  if [[ -r "${HOME}/.config/fx/env" ]]; then
    # shellcheck disable=SC1091
    set -a
    # shellcheck disable=SC1090
    . "${HOME}/.config/fx/env"
    set +a
    log "loaded ${HOME}/.config/fx/env"
  fi
fi

if [[ -z "${AI_GATEWAY_API_KEY:-}" && -z "$ENV_FILE" && -z "${VERCEL_OIDC_TOKEN:-}" ]]; then
  warn "AI_GATEWAY_API_KEY is unset. fx will start but cannot call a model."
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  if [[ -f "${SCRIPT_DIR}/Dockerfile" ]]; then
    log "image ${IMAGE} missing — building it"
    docker build --tag "$IMAGE" \
      --build-arg "FX_MODEL=${FX_MODEL:-zai/glm-5.2}" \
      -f "${SCRIPT_DIR}/Dockerfile" "$SCRIPT_DIR"
  else
    die "image ${IMAGE} not found and no Dockerfile next to this script"
  fi
fi

TTY_FLAGS=()
if [[ -t 0 && -t 1 ]]; then
  TTY_FLAGS+=(-it)
else
  TTY_FLAGS+=(-i)
fi

mount_spec="type=bind,src=${WORKSPACE},dst=/workspace"
if [[ $READ_ONLY_WS -eq 1 ]]; then
  mount_spec+=",readonly"
fi

DOCKER_ARGS=(
  run --rm
  "${TTY_FLAGS[@]}"
  --read-only
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=256m
  --tmpfs /home/fx:rw,nosuid,nodev,uid="$(id -u)",gid="$(id -g)",mode=700,size=128m
  --mount "${mount_spec}"
  --workdir /workspace
  --user "$(id -u):$(id -g)"
  --group-add "$(id -g)"
  --security-opt no-new-privileges:true
  --cap-drop ALL
  --pids-limit "$PIDS"
  --memory "$MEMORY"
  --cpus "$CPUS"
  --network "$NETWORK"
  -e "HOME=/home/fx"
  -e "FX_HOME=/home/fx/.fx"
  -e "FX_DISABLE_KEYCHAIN=1"
  -e "FX_MODEL=${FX_MODEL:-zai/glm-5.2}"
  -e "FX_PERMISSION_MODE=${FX_PERMISSION_MODE:-auto}"
  -e "TERM=${TERM:-xterm-256color}"
)

# Pass the key only via env (not a file in the workspace).
if [[ -n "${AI_GATEWAY_API_KEY:-}" ]]; then
  DOCKER_ARGS+=(-e "AI_GATEWAY_API_KEY")
fi
if [[ -n "${VERCEL_OIDC_TOKEN:-}" ]]; then
  DOCKER_ARGS+=(-e "VERCEL_OIDC_TOKEN")
fi
if [[ -n "$ENV_FILE" ]]; then
  DOCKER_ARGS+=(--env-file "$ENV_FILE")
fi
if [[ -n "$NAME" ]]; then
  DOCKER_ARGS+=(--name "$NAME")
fi
if [[ $PERSIST_STATE -eq 1 ]]; then
  # Named volume keeps sessions, not the API key (key stays in env).
  local_vol="fx-state-$(id -u)"
  DOCKER_ARGS+=(--mount "type=volume,src=${local_vol},dst=/home/fx/.fx")
fi
if [[ $GITCONFIG -eq 1 && -f "${HOME}/.gitconfig" ]]; then
  DOCKER_ARGS+=(--mount "type=bind,src=${HOME}/.gitconfig,dst=/home/fx/.gitconfig,readonly")
fi

# If the caller passed nothing, drop into interactive fx.
if [[ ${#FX_ARGS[@]} -eq 0 ]]; then
  FX_ARGS=(fx)
fi

if [[ $ALLOW_YOLO -eq 0 ]]; then
  for a in "${FX_ARGS[@]}"; do
    if [[ "$a" == "--yolo" || "$a" == "yolo" ]]; then
      die "--yolo blocked (pass --allow-yolo on the wrapper if you insist)"
    fi
  done
fi

if [[ $DRY -eq 1 ]]; then
  printf 'docker'
  printf ' %q' "${DOCKER_ARGS[@]}" "$IMAGE" "${FX_ARGS[@]}"
  printf '\n'
  exit 0
fi

if [[ $PULL -eq 1 ]]; then
  log "image is local-built; --pull ignored (we do not fetch a public prebuilt with your key)"
fi

log "workspace=${WORKSPACE}"
log "image=${IMAGE} user=$(id -u):$(id -g) net=${NETWORK} mem=${MEMORY}"
exec docker "${DOCKER_ARGS[@]}" "$IMAGE" "${FX_ARGS[@]}"
