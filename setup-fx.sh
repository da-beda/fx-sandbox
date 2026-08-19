#!/usr/bin/env bash
# setup-fx.sh — the fx-sandbox installer (stable curl name).
#
# After install the commands you actually type are:
#   fx      native agent (wrapper loads ~/.config/fx/env)
#   fxs     this toolkit: run / ask / build / status / key / uninstall
#
#   curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/setup-fx.sh | bash
#   fxs run                  # container sandbox
#   fxs ask "…"              # one-shot
#   fxs status
#
# Linux + macOS (Intel / Apple Silicon). Bash 3.2-safe. Never prints secrets.
#
set -euo pipefail
IFS=$'\n\t'

FX_CDN="${FX_CDN:-https://releases.fx.sh}"
KIT_DIR_DEFAULT="${HOME}/.local/share/fx-sandbox"
DEFAULT_MODEL="${FX_MODEL:-zai/glm-5.2}"
LOG_PREFIX="[fxs]"

CMD="install"           # install | unpack | build | run | ask | status | key | uninstall
MODE=""                 # host | container | auto
NONINTERACTIVE=0
WITH_DOCKER=0
BUILD_IMAGE=0
INSTALL_DEV_TOOLS=0
SYSTEM_INSTALL=0
SKIP_PACKAGES=0
SKIP_FX=0
CONFIGURE_ONLY=0
DOCTOR=0
ASSUME_YES=0
SKIP_KEY_PROMPT=0
FORCE_KEY_PROMPT=0
KEY_TIMEOUT="${KEY_TIMEOUT:-30}"
IMAGE_NAME="${FX_IMAGE_NAME:-fx-sandbox:latest}"
UNPACK_DIR=""

UNAME_S="$(uname -s)"
UNAME_M="$(uname -m)"

if [[ -t 2 ]]; then
  C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YEL=$'\033[33m'
  C_BLU=$'\033[34m'; C_OFF=$'\033[0m'
else
  C_RED=""; C_GRN=""; C_YEL=""; C_BLU=""; C_OFF=""
fi

log()  { printf '%s %s\n' "${C_BLU}${LOG_PREFIX}${C_OFF}" "$*" >&2; }
ok()   { printf '%s %s\n' "${C_GRN}${LOG_PREFIX}${C_OFF}" "$*" >&2; }
warn() { printf '%s %s\n' "${C_YEL}${LOG_PREFIX} warn:${C_OFF}" "$*" >&2; }
err()  { printf '%s %s\n' "${C_RED}${LOG_PREFIX} error:${C_OFF}" "$*" >&2; }
die()  { err "$*"; exit 1; }

need_cmd() { command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"; }
is_root() { [[ "$(id -u)" -eq 0 ]]; }
is_darwin() { [[ "$UNAME_S" == "Darwin" ]]; }
is_linux()  { [[ "$UNAME_S" == "Linux" ]]; }

is_piped() {
  local src="${BASH_SOURCE[0]:-}"
  case "$src" in
    ""|bash|-|stdin|/dev/fd/*|/proc/self/fd/*|/dev/stdin) return 0 ;;
  esac
  [[ -f "$src" ]] || return 0
  return 1
}

run_root() {
  if is_root; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    die "need root for: $*"
  fi
}

file_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    die "need sha256sum or shasum"
  fi
}

usage() {
  cat <<'EOF'
fxs — install fx and run it in a locked-down sandbox (macOS + Linux)

INSTALL
  curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/setup-fx.sh | bash
  curl -fsSL …/setup-fx.sh | bash -s -- --with-docker --build-image

COMMANDS
  install              Install fx + this toolkit (default for setup-fx.sh)
  run  [fx-args…]      Sandboxed fx against $PWD (default for `fxs`)
  ask  [fx-args…]      One-shot: run -- fx ask …
  sessions             List fxs sessions for this directory
  build                Build the fx-sandbox Docker image
  status               What is installed, keyed, and running
  key                  (Re)prompt for a Vercel AI Gateway key
  unpack [dir]         Write Dockerfile / compose / configs to disk
  uninstall            Remove fxs, the fx wrapper, and the kit
  help                 This help

INSTALL FLAGS
  --host / --in-container
  --with-docker        --build-image       --doctor
  --system             --install-dev-tools
  --configure-only     --skip-packages     --skip-fx
  --skip-key-prompt    --key-timeout SEC   (default 30; 0 = forever)
  --non-interactive    -y / --yes
  --image NAME         -h / --help

AFTER INSTALL
  fx           native agent — wrapper loads ~/.config/fx/env
  fxs          this command (also: fx-sandbox) — yolo inside Docker
  fxs status   check this machine
  fxs -c       resume last fxs session in \$PWD
  fxs --no-yolo  prompt before tools

The API key is stored in ~/.config/fx/env (0600), never in the image.
Companion files are embedded; the only extra download is the fx tarball.
EOF
}

# ---------------------------------------------------------------------------
# args
# ---------------------------------------------------------------------------
parse_args() {
  if [[ $# -gt 0 ]]; then
    case "$1" in
      install|unpack|build|run|ask|status|key|uninstall|doctor|help)
        CMD="$1"
        shift
        ;;
      sessions|session)
        CMD="run"
        RUN_ARGS=("$@")
        return 0
        ;;
      -h|--help)
        usage; exit 0
        ;;
    esac
  fi
  # `fxs` / `fx-sandbox` / `run-fx` default to the sandbox, not re-install.
  case "${0##*/}" in
    fxs|fx-sandbox|run-fx)
      if [[ "$CMD" == "install" ]]; then CMD="run"; fi
      ;;
  esac

  if [[ "$CMD" == "help" ]]; then usage; exit 0; fi

  if [[ "$CMD" == "unpack" ]]; then
    UNPACK_DIR="${1:-}"
    return 0
  fi

  if [[ "$CMD" == "run" || "$CMD" == "ask" ]]; then
    RUN_ARGS=("$@")
    return 0
  fi

  if [[ "$CMD" == "status" || "$CMD" == "key" || "$CMD" == "doctor" ]]; then
    return 0
  fi

  if [[ "$CMD" == "uninstall" ]]; then
    while [[ $# -gt 0 ]]; do
      case "$1" in
        -y|--yes) ASSUME_YES=1 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1 (try --help)" ;;
      esac
      shift
    done
    return 0
  fi

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --host) MODE="host" ;;
      --in-container|--container) MODE="container" ;;
      --non-interactive) NONINTERACTIVE=1 ;;
      -y|--yes) ASSUME_YES=1 ;;
      --system) SYSTEM_INSTALL=1 ;;
      --install-dev-tools) INSTALL_DEV_TOOLS=1 ;;
      --with-docker) WITH_DOCKER=1 ;;
      --build-image) BUILD_IMAGE=1 ;;
      --configure-only) CONFIGURE_ONLY=1 ;;
      --skip-apt|--skip-packages) SKIP_PACKAGES=1 ;;
      --skip-fx) SKIP_FX=1 ;;
      --doctor) DOCTOR=1 ;;
      --skip-key-prompt) SKIP_KEY_PROMPT=1 ;;
      --key-timeout)
        [[ $# -ge 2 ]] || die "--key-timeout needs a number of seconds"
        KEY_TIMEOUT="$2"; shift
        ;;
      --image)
        [[ $# -ge 2 ]] || die "--image needs a name"
        IMAGE_NAME="$2"; shift
        ;;
      -h|--help) usage; exit 0 ;;
      *) die "unknown argument: $1 (try --help)" ;;
    esac
    shift
  done
}

in_container() {
  [[ -f /.dockerenv ]] && return 0
  [[ -f /run/.containerenv ]] && return 0
  [[ "${container:-}" == "docker" || "${container:-}" == "podman" ]] && return 0
  if [[ -r /proc/1/cgroup ]] && grep -Eq 'docker|lxc|containerd|kubepods|libpod|podman' /proc/1/cgroup 2>/dev/null; then
    return 0
  fi
  if cat /proc/1/environ 2>/dev/null | tr '\0' '\n' | grep -q '^container='; then
    return 0
  fi
  return 1
}

require_supported_os() {
  case "$UNAME_S" in
    Linux|Darwin) ;;
    *) die "unsupported OS: ${UNAME_S} (need Linux or macOS)" ;;
  esac
}

linux_is_debianish() {
  [[ -r /etc/os-release ]] || return 1
  # shellcheck disable=SC1091
  . /etc/os-release
  case "${ID:-}:${ID_LIKE:-}" in
    ubuntu:*|debian:*|linuxmint:*|pop:*|*:debian*|*:ubuntu*) return 0 ;;
  esac
  return 1
}

detect_platform() {
  local os arch
  case "$UNAME_S" in
    Linux)  os="linux" ;;
    Darwin) os="macos" ;;
    *) die "unsupported OS: ${UNAME_S}" ;;
  esac
  case "$UNAME_M" in
    x86_64|amd64)  arch="x86_64" ;;
    arm64|aarch64) arch="aarch64" ;;
    *) die "unsupported architecture: ${UNAME_M}" ;;
  esac
  printf '%s-%s\n' "$os" "$arch"
}

kit_dest() {
  # Always the data dir. Never dirname($0): after install, `fxs` lives in
  # ~/.local/bin and writing a Dockerfile there is how we trash PATH.
  if [[ -n "${FX_KIT_DIR:-}" ]]; then
    printf '%s\n' "$FX_KIT_DIR"
    return
  fi
  printf '%s\n' "$KIT_DIR_DEFAULT"
}

# ---------------------------------------------------------------------------
# packages + fx binary
# ---------------------------------------------------------------------------
ensure_packages() {
  [[ $SKIP_PACKAGES -eq 1 ]] && { log "skipping packages"; return 0; }

  if is_darwin; then
    if [[ $INSTALL_DEV_TOOLS -eq 1 ]]; then
      if command -v brew >/dev/null 2>&1; then
        log "brew install git jq python3 ripgrep fd curl"
        brew install git jq python3 ripgrep fd curl || warn "brew install reported issues; continuing"
      else
        warn "Homebrew not found — skipping extra tools (https://brew.sh)."
      fi
    fi
    need_cmd curl
    need_cmd tar
    return 0
  fi

  if [[ "$MODE" == "container" ]] || linux_is_debianish; then
    ensure_apt_packages
    return 0
  fi

  warn "not Debian/Ubuntu; not running apt. Need curl + tar."
  need_cmd curl
  need_cmd tar
}

ensure_apt_packages() {
  command -v apt-get >/dev/null 2>&1 || die "apt-get not found"
  local pkgs="ca-certificates curl wget tar gzip xz-utils unzip"
  if [[ $INSTALL_DEV_TOOLS -eq 1 || "$MODE" == "container" ]]; then
    pkgs="$pkgs git jq python3 python3-pip python3-venv ripgrep fd-find less file patch bash"
  fi
  if [[ "$MODE" == "container" && $INSTALL_DEV_TOOLS -eq 1 ]]; then
    pkgs="$pkgs build-essential pkg-config"
  fi
  export DEBIAN_FRONTEND=noninteractive
  log "apt-get update"
  run_root apt-get update -y -qq
  # shellcheck disable=SC2086
  if ! run_root apt-get install -y --no-install-recommends $pkgs; then
    warn "retrying without optional packages"
    pkgs="ca-certificates curl wget tar gzip xz-utils unzip git jq python3 python3-pip less file patch bash"
    # shellcheck disable=SC2086
    run_root apt-get install -y --no-install-recommends $pkgs
  fi
  if [[ "$MODE" == "container" ]]; then
    run_root apt-get clean
    run_root rm -rf /var/lib/apt/lists/*
  fi
}

resolve_version() {
  if [[ -n "${FX_VERSION:-}" ]]; then
    printf '%s\n' "$FX_VERSION"
    return 0
  fi
  need_cmd curl
  local ver
  ver="$(curl -fsSL --retry 3 --retry-delay 1 "${FX_CDN}/latest.txt" | tr -d '[:space:]')"
  [[ -n "$ver" ]] || die "could not resolve latest fx version"
  printf '%s\n' "$ver"
}

install_dir_for_mode() {
  if [[ -n "${FX_INSTALL_DIR:-}" ]]; then
    printf '%s\n' "$FX_INSTALL_DIR"
    return 0
  fi
  if [[ "$MODE" == "container" || $SYSTEM_INSTALL -eq 1 ]]; then
    printf '/usr/local/bin\n'
  else
    printf '%s\n' "${HOME}/.local/bin"
  fi
}

extract_tar() {
  local archive="$1" dest="$2"
  if tar --no-same-owner -xzf "$archive" -C "$dest" 2>/dev/null; then
    return 0
  fi
  tar -xzf "$archive" -C "$dest"
}

download_and_install_fx() {
  [[ $SKIP_FX -eq 1 ]] && { log "skipping fx download"; return 0; }
  need_cmd curl
  need_cmd tar

  local version platform dest tmp archive url sumurl got expect
  version="$(resolve_version)"
  platform="$(detect_platform)"
  dest="$(install_dir_for_mode)"
  archive="fx-${platform}.tar.gz"
  url="${FX_CDN}/${version}/${archive}"
  sumurl="${url}.sha256"

  log "fx ${version} for ${platform}"
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/fx-setup.XXXXXX")"
  # shellcheck disable=SC2064
  trap 'rm -rf "'"$tmp"'"' EXIT

  curl -fsSL --retry 3 --retry-delay 1 -o "${tmp}/${archive}" "$url"
  curl -fsSL --retry 3 --retry-delay 1 -o "${tmp}/${archive}.sha256" "$sumurl"
  expect="$(awk '{print $1}' "${tmp}/${archive}.sha256" | tr -d '[:space:]')"
  got="$(file_sha256 "${tmp}/${archive}")"
  [[ "$expect" == "$got" ]] || die "sha256 mismatch for ${archive}"
  ok "checksum ok"

  extract_tar "${tmp}/${archive}" "$tmp"
  [[ -x "${tmp}/fx" ]] || die "archive did not contain an fx binary"

  local real
  if [[ "$dest" == /usr/local/bin || "$dest" == /usr/bin ]]; then
    run_root mkdir -p "$dest"
    run_root install -m 0755 "${tmp}/fx" "${dest}/fx"
    real="${dest}/fx"
  else
    # Keep the real binary out of PATH. ~/.local/bin/fx is a wrapper that
    # sources ~/.config/fx/env so the current (and every) shell sees the key.
    real="${HOME}/.local/share/fx-sandbox/bin/fx"
    mkdir -p "$(dirname "$real")" "$dest"
    install -m 0755 "${tmp}/fx" "$real"
    write_fx_wrapper "${dest}/fx" "$real"
  fi
  ok "installed $("$real" --version 2>/dev/null || echo fx) -> ${dest}/fx"
  rm -rf "$tmp"
  trap - EXIT
}

# Thin PATH wrapper: load the saved gateway key, then exec the real binary.
write_fx_wrapper() {
  local wrapper="$1" real="$2"
  {
    printf '%s\n' '#!/usr/bin/env bash'
    printf '%s\n' '# generated by setup-fx.sh — sources ~/.config/fx/env'
    printf '%s\n' 'if [ -z "${AI_GATEWAY_API_KEY:-}" ] && [ -r "${HOME}/.config/fx/env" ]; then'
    printf '%s\n' '  set -a'
    printf '%s\n' '  # shellcheck disable=SC1090'
    printf '%s\n' '  . "${HOME}/.config/fx/env"'
    printf '%s\n' '  set +a'
    printf '%s\n' 'fi'
    printf 'exec %q "$@"\n' "$real"
  } > "$wrapper"
  chmod 0755 "$wrapper"
}

# ---------------------------------------------------------------------------
# embedded kit (no extra downloads)
# ---------------------------------------------------------------------------

emit_dockerfile() {
cat <<'END_DOCKERFILE'
# syntax=docker/dockerfile:1.7
# Generated by setup-fx.sh. The image is always Linux; the host may be
# macOS or Linux. Never pass AI_GATEWAY_API_KEY as a build-arg.

ARG UBUNTU_VERSION=24.04
FROM ubuntu:${UBUNTU_VERSION}

ARG FX_VERSION=
ARG FX_MODEL=zai/glm-5.2
ARG FX_UID=1000
ARG FX_GID=1000
ARG TARGETARCH
# Optional apt mirror, e.g. http://de.ports.ubuntu.com/ubuntu-ports
ARG APT_MIRROR=

LABEL org.opencontainers.image.title="fx-sandbox" \
      org.opencontainers.image.description="Hardened Ubuntu image for Vercel Labs fx" \
      org.opencontainers.image.source="https://github.com/da-beda/fx-sandbox"

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FX_DISABLE_KEYCHAIN=1 \
    FX_MODEL=${FX_MODEL} \
    FX_PERMISSION_MODE=auto \
    FX_HOME=/home/fx/.fx \
    HOME=/home/fx \
    PATH=/usr/local/bin:/usr/sbin:/usr/bin:/bin

# Slim package set (no compiler toolchain). Retries + optional mirror
# because Docker Desktop on macOS often flakes on ports.ubuntu.com:80.
RUN set -eu; \
    printf 'Acquire::Retries "5";\nAcquire::http::Timeout "20";\nAcquire::https::Timeout "20";\n' \
      > /etc/apt/apt.conf.d/80-retries; \
    if [ -n "${APT_MIRROR}" ]; then \
      if [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then \
        sed -i "s|http://ports.ubuntu.com/ubuntu-ports|${APT_MIRROR}|g; s|http://archive.ubuntu.com/ubuntu|${APT_MIRROR}|g" \
          /etc/apt/sources.list.d/ubuntu.sources; \
      fi; \
    fi; \
    apt-get update -y; \
    apt-get install -y --no-install-recommends \
      passwd ca-certificates curl tar gzip git bash; \
    rm -rf /var/lib/apt/lists/*; \
    if ! getent group fx >/dev/null; then \
      /usr/sbin/groupadd --gid "${FX_GID}" fx 2>/dev/null || /usr/sbin/groupadd fx; \
    fi; \
    if ! id fx >/dev/null 2>&1; then \
      /usr/sbin/useradd --uid "${FX_UID}" --gid fx \
        --create-home --home-dir /home/fx \
        --shell /bin/bash \
        --comment "fx sandbox user" fx \
      2>/dev/null || /usr/sbin/useradd --gid fx \
        --create-home --home-dir /home/fx \
        --shell /bin/bash \
        --comment "fx sandbox user" fx; \
    fi; \
    mkdir -p /workspace /home/fx/.fx /home/fx/.config; \
    chown -R fx:fx /home/fx /workspace; \
    chmod 0700 /home/fx /home/fx/.fx

# fx is a Linux binary inside the image (linux-x86_64 / linux-aarch64).
RUN set -eu; \
    case "${TARGETARCH:-}" in \
      amd64) arch=x86_64 ;; \
      arm64) arch=aarch64 ;; \
      "") case "$(uname -m)" in x86_64|amd64) arch=x86_64 ;; arm64|aarch64) arch=aarch64 ;; *) echo "arch? $(uname -m)"; exit 1 ;; esac ;; \
      *) echo "unsupported TARGETARCH=${TARGETARCH}"; exit 1 ;; \
    esac; \
    ver="${FX_VERSION}"; \
    if [ -z "$ver" ]; then ver="$(curl -fsSL https://releases.fx.sh/latest.txt | tr -d "[:space:]")"; fi; \
    cd /tmp; \
    curl -fsSL -o fx.tgz "https://releases.fx.sh/${ver}/fx-linux-${arch}.tar.gz"; \
    curl -fsSL -o fx.sha "https://releases.fx.sh/${ver}/fx-linux-${arch}.tar.gz.sha256"; \
    got="$(sha256sum fx.tgz | awk "{print \$1}")"; \
    expect="$(awk "{print \$1}" fx.sha | tr -d "[:space:]")"; \
    [ "$got" = "$expect" ] || { echo "sha256 mismatch $got != $expect"; exit 1; }; \
    tar --no-same-owner -xzf fx.tgz; \
    install -m 0755 /tmp/fx /usr/local/bin/fx; \
    rm -rf /tmp/fx /tmp/fx.tgz /tmp/fx.sha; \
    fx --version

COPY entrypoint.sh /usr/local/bin/fx-entrypoint
COPY config/settings.json /usr/local/share/fx-sandbox/settings.json
COPY config/workspace.fx.json /usr/local/share/fx-sandbox/workspace.fx.json

RUN chmod 0755 /usr/local/bin/fx-entrypoint \
 && install -m 0600 -o fx -g fx /usr/local/share/fx-sandbox/settings.json /home/fx/.fx/settings.json \
 && printf "export FX_DISABLE_KEYCHAIN=1\\nexport FX_MODEL=%s\\n" "${FX_MODEL}" > /etc/profile.d/fx.sh \
 && chmod 0644 /etc/profile.d/fx.sh

USER fx:fx
WORKDIR /workspace
STOPSIGNAL SIGINT
ENTRYPOINT ["/usr/local/bin/fx-entrypoint"]
CMD ["fx"]
END_DOCKERFILE
}

emit_entrypoint() {
cat <<'END_ENTRYPOINT'
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

if [[ -z "${AI_GATEWAY_API_KEY:-}" && -z "${VERCEL_OIDC_TOKEN:-}" ]]; then
  warn "no AI_GATEWAY_API_KEY or VERCEL_OIDC_TOKEN in the environment."
  warn "fx will not be able to call a model until you pass one (see run-fx.sh)."
fi

# Never dump the key. Confirm only that it *looks* like a gateway token.
if [[ -n "${AI_GATEWAY_API_KEY:-}" && ! "${AI_GATEWAY_API_KEY}" =~ ^vck_ ]]; then
  warn "AI_GATEWAY_API_KEY does not start with vck_ — is this the right secret?"
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
END_ENTRYPOINT
}

emit_runfx() {
cat <<'END_RUNFX'
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
PERSIST_STATE="${FXS_PERSIST:-1}"
READ_ONLY_WS=0
GITCONFIG=0
NETWORK="${FX_NETWORK:-bridge}"
MEMORY="${FX_MEMORY:-2g}"
CPUS="${FX_CPUS:-2}"
PIDS="${FX_PIDS:-256}"
ALLOW_YOLO="${FXS_YOLO:-1}"
PULL=0
DRY=0
STATE_ROOT="${FXS_STATE_ROOT:-${HOME}/.local/share/fx-sandbox/state}"

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
  --persist-state        Keep sessions (default). Same as FXS_PERSIST=1
  --no-persist           Ephemeral ~/.fx (tmpfs only; nothing to resume)
  --gitconfig            Mount $HOME/.gitconfig read-only
  --network NET          Default bridge. `none` denies egress.
  --memory SIZE          default 2g
  --cpus N               default 2
  --pids N               default 256
  --image NAME           default fx-sandbox:latest
  --allow-yolo           Yolo (default). Same as FXS_YOLO=1
  --no-yolo              Ask before tools (fx auto/ask)
  --dry-run              Print the docker argv and exit
  -h, --help

Always on: --user $uid:$gid, --cap-drop ALL, no-new-privileges,
read-only rootfs, tmpfs home, no docker.sock. Refuses /, $HOME, /Users.

Yolo is the default: the container is the sandbox, so fx does not
prompt. Use --no-yolo if you want approval prompts.

Sessions are stored per host project under
  ~/.local/share/fx-sandbox/state/<hash>/
Host ~/.fx is never mounted. Resume only sees fxs sessions for this directory.

  fxs                                  # interactive, yolo
  fxs -c                               # resume last session here
  fxs --no-yolo                        # prompt on tools
  fxs ask "what is 17*19?"             # one-shot, yolo
  fxs sessions                         # list

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

ws_hash() {
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$1" | sha256sum | awk '{print substr($1,1,16)}'
  elif command -v shasum >/dev/null 2>&1; then
    printf '%s' "$1" | shasum -a 256 | awk '{print substr($1,1,16)}'
  else
    die "need sha256sum or shasum to name the session dir"
  fi
}

state_dir_for() {
  printf '%s/%s\n' "$STATE_ROOT" "$(ws_hash "$1")"
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
    --no-persist) PERSIST_STATE=0; shift ;;
    --gitconfig) GITCONFIG=1; shift ;;
    --network) NETWORK="$2"; shift 2 ;;
    --memory) MEMORY="$2"; shift 2 ;;
    --cpus) CPUS="$2"; shift 2 ;;
    --pids) PIDS="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --pull) PULL=1; shift ;;
    --allow-yolo) ALLOW_YOLO=1; shift ;;
    --no-yolo|--ask) ALLOW_YOLO=0; shift ;;
    --dry-run) DRY=1; shift ;;
    --) shift; FX_ARGS+=("$@"); break ;;
    --yolo)
      # Default is yolo; keep the token only if it is for `fx ask`.
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
    log "image ${IMAGE} missing — building it (needs Ubuntu packages; first time can take a few minutes)"
    BUILD_ARGS=(
      --tag "$IMAGE"
      --build-arg "FX_MODEL=${FX_MODEL:-zai/glm-5.2}"
    )
    if [[ -n "${FX_APT_MIRROR:-}" ]]; then
      BUILD_ARGS+=(--build-arg "APT_MIRROR=${FX_APT_MIRROR}")
      log "apt mirror: ${FX_APT_MIRROR}"
    fi
    docker build "${BUILD_ARGS[@]}" \
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
  # Per-host-project dir. A single global volume would make every repo
  # look like /workspace and mix "last" sessions.
  _state="$(state_dir_for "$WORKSPACE")"
  mkdir -p "${_state}"
  chmod 0700 "${_state}" 2>/dev/null || true
  printf '%s\n' "$WORKSPACE" > "${_state}/origin"
  DOCKER_ARGS+=(--mount "type=bind,src=${_state},dst=/home/fx/.fx")
  log "sessions=${_state}  (fxs run -c resumes last here)"
fi
if [[ $GITCONFIG -eq 1 && -f "${HOME}/.gitconfig" ]]; then
  DOCKER_ARGS+=(--mount "type=bind,src=${HOME}/.gitconfig,dst=/home/fx/.gitconfig,readonly")
fi

# If the caller passed nothing, drop into interactive fx.
# Flags like --yolo are not a command name.
if [[ ${#FX_ARGS[@]} -eq 0 ]]; then
  FX_ARGS=(fx)
elif [[ "${FX_ARGS[0]}" == -* ]]; then
  FX_ARGS=(fx "${FX_ARGS[@]}")
fi

# Interactive `fx` has no --yolo flag (only `fx ask --yolo` does).
# Default is yolo: set FX_PERMISSION_MODE, strip a stray top-level
# --yolo, and inject --yolo after `ask` so one-shots do not stall.
if [[ $ALLOW_YOLO -eq 1 ]]; then
  DOCKER_ARGS+=(-e "FX_PERMISSION_MODE=yolo")
  _kept=()
  _keep_yolo=0
  _saw_ask=0
  _have_ask_yolo=0
  for a in "${FX_ARGS[@]}"; do
    case "$a" in
      ask) _keep_yolo=1; _saw_ask=1; _kept+=("$a") ;;
      --yolo|yolo)
        if [[ $_keep_yolo -eq 1 ]]; then
          _kept+=("$a")
          _have_ask_yolo=1
        fi
        ;;
      *) _kept+=("$a") ;;
    esac
  done
  if [[ $_saw_ask -eq 1 && $_have_ask_yolo -eq 0 ]]; then
    _out=()
    for a in "${_kept[@]}"; do
      _out+=("$a")
      if [[ "$a" == "ask" ]]; then
        _out+=("--yolo")
      fi
    done
    _kept=("${_out[@]}")
  fi
  FX_ARGS=("${_kept[@]}")
  if [[ ${#FX_ARGS[@]} -eq 0 ]]; then
    FX_ARGS=(fx)
  fi
  log "yolo on — fx will not ask; isolation is the container"
fi

if [[ $ALLOW_YOLO -eq 0 ]]; then
  for a in "${FX_ARGS[@]}"; do
    if [[ "$a" == "--yolo" || "$a" == "yolo" ]]; then
      die "--yolo blocked (omit --no-yolo, or drop --yolo)"
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
END_RUNFX
}

emit_compose() {
cat <<'END_COMPOSE'
# Sandboxed fx agent.
#
#   cp .env.example .env          # put the key here, chmod 600
#   docker compose build
#   docker compose run --rm fx
#   docker compose run --rm fx ask "Summarise this repo"
#
# Override the project dir:
#   FX_WORKSPACE=/absolute/path/to/project docker compose run --rm fx
#
# This file is the safe-by-default shape. Do not add privileged: true,
# do not mount /var/run/docker.sock, do not bind-mount $HOME.

name: fx-sandbox

services:
  fx:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        FX_MODEL: ${FX_MODEL:-zai/glm-5.2}
    image: ${FX_IMAGE_NAME:-fx-sandbox:latest}
    working_dir: /workspace
    user: "${FX_UID:-1000}:${FX_GID:-1000}"
    read_only: true
    stdin_open: true
    tty: true
    init: true
    tmpfs:
      - /tmp:rw,noexec,nosuid,nodev,size=256m
      - /home/fx:rw,nosuid,nodev,mode=700,size=128m
    volumes:
      - type: bind
        source: ${FX_WORKSPACE:-.}
        target: /workspace
        bind:
          create_host_path: false
      # Optional durable session store. The API key is NOT kept here.
      - type: volume
        source: fx-state
        target: /home/fx/.fx
    environment:
      HOME: /home/fx
      FX_HOME: /home/fx/.fx
      FX_DISABLE_KEYCHAIN: "1"
      FX_MODEL: ${FX_MODEL:-zai/glm-5.2}
      FX_PERMISSION_MODE: ${FX_PERMISSION_MODE:-auto}
      AI_GATEWAY_API_KEY: ${AI_GATEWAY_API_KEY:-}
      TERM: ${TERM:-xterm-256color}
    env_file:
      - path: .env
        required: false
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    pids_limit: 256
    mem_limit: ${FX_MEMORY:-2g}
    cpus: ${FX_CPUS:-2.0}
    # Default bridge: fx must reach ai-gateway.vercel.sh and releases.fx.sh.
    # Set FX_NETWORK=none in .env to deny all egress (offline review only).
    network_mode: ${FX_NETWORK_MODE:-bridge}

volumes:
  fx-state:
    name: fx-state-${FX_UID:-1000}
END_COMPOSE
}

emit_settings() {
cat <<'END_SETTINGS'
{
  "model": "zai/glm-5.2",
  "permission_mode": "auto",
  "sandbox": "none",
  "auto_upgrade": false,
  "update_channel": "stable",
  "fast_mode": false
}
END_SETTINGS
}

emit_workspace_fx() {
cat <<'END_WORKSPACE_FX'
{
  "sandbox": "none",
  "max_agent_steps": 40,
  "max_tool_result_bytes": 200000
}
END_WORKSPACE_FX
}

emit_env_example() {
cat <<'END_ENV_EXAMPLE'
# Copy to .env and `chmod 600 .env`. Never commit .env.
#
#   cp .env.example .env
#   chmod 600 .env

AI_GATEWAY_API_KEY=vck_replace_me
FX_MODEL=zai/glm-5.2
FX_PERMISSION_MODE=auto

# Host uid:gid so files created in the bind-mount belong to you.
#   echo "FX_UID=$(id -u)" >> .env
#   echo "FX_GID=$(id -g)" >> .env
FX_UID=1000
FX_GID=1000

# Absolute path of the project you want fx to see.
# FX_WORKSPACE=/home/you/src/myapp

# Memory / CPU caps (compose)
# FX_MEMORY=2g
# FX_CPUS=2.0

# Use `none` to block all outbound network (model calls will fail).
# FX_NETWORK_MODE=bridge
END_ENV_EXAMPLE
}

emit_dockerignore() {
cat <<'END_DOCKERIGNORE'
.env
.env.*
!.env.example
**/.git
**/.fx
**/.ssh
**/.gnupg
**/.aws
**/.azure
**/.kube
**/.docker
**/node_modules
**/.venv
**/__pycache__
*.pem
*.key
id_rsa
id_ed25519
END_DOCKERIGNORE
}


write_file() {
  local path="$1"
  mkdir -p "$(dirname "$path")"
  cat > "$path"
}

write_kit() {
  local dest="${1:-}"
  [[ -n "$dest" ]] || dest="$(kit_dest)"
  mkdir -p "$dest/config"
  log "writing embedded kit -> ${dest}"
  emit_dockerfile     | write_file "${dest}/Dockerfile"
  emit_entrypoint     | write_file "${dest}/entrypoint.sh"
  emit_runfx          | write_file "${dest}/run-fx.sh"
  emit_compose        | write_file "${dest}/docker-compose.yml"
  emit_settings       | write_file "${dest}/config/settings.json"
  emit_workspace_fx   | write_file "${dest}/config/workspace.fx.json"
  emit_env_example    | write_file "${dest}/.env.example"
  emit_dockerignore   | write_file "${dest}/.dockerignore"
  chmod 0755 "${dest}/entrypoint.sh" "${dest}/run-fx.sh"
  persist_self "$dest"
  ok "kit ready"
  printf '%s\n' "$dest"
}

# Persist this installer as setup-fx.sh (stable name) and link `fxs` on PATH.
persist_self() {
  local dest="$1"
  local src="${BASH_SOURCE[0]:-}"
  local target="${dest}/setup-fx.sh"
  if [[ -n "$src" && -f "$src" && -f "$target" && "$src" -ef "$target" ]]; then
    chmod 0755 "$target" 2>/dev/null || true
    return 0
  fi
  if ! is_piped && [[ -n "$src" && -f "$src" ]]; then
    cp "$src" "$target"
  elif [[ ! -s "$target" ]] || is_piped; then
    curl -fsSL --retry 2 --retry-delay 1 \
      -o "$target" \
      "https://raw.githubusercontent.com/da-beda/fx-sandbox/main/setup-fx.sh" \
      || warn "could not persist setup-fx.sh into ${dest}"
  fi
  chmod 0755 "$target" 2>/dev/null || true
}

link_cli() {
  local dest here
  dest="$(install_dir_for_mode)"
  here="$1"
  mkdir -p "$dest"
  if [[ -x "${here}/setup-fx.sh" ]]; then
    ln -sfn "${here}/setup-fx.sh" "${dest}/fxs"
    ln -sfn "${here}/setup-fx.sh" "${dest}/fx-sandbox"
    ln -sfn "${here}/setup-fx.sh" "${dest}/setup-fx"
    ln -sfn "${here}/setup-fx.sh" "${dest}/setup-fx.sh"
    ln -sfn "${here}/setup-fx.sh" "${dest}/run-fx"
    ok "linked ${dest}/fxs"
  fi
  scrub_path_pollution "$dest"
}

# An older bug unpacked the kit into ~/.local/bin. Remove only those
# leaked names. Never touch fx / fxs / claude / uv / python*.
scrub_path_pollution() {
  local dest="${1:-$(install_dir_for_mode)}"
  local f removed=0
  # Only scrub the user bindir, never /usr/local/bin wholesale.
  case "$dest" in
    "${HOME}/.local/bin") ;;
    *) return 0 ;;
  esac
  for f in Dockerfile entrypoint.sh docker-compose.yml run-fx.sh \
           .env.example .dockerignore; do
    if [[ -e "${dest}/${f}" || -L "${dest}/${f}" ]]; then
      rm -f "${dest}/${f}"
      removed=1
    fi
  done
  if [[ -d "${dest}/config" ]]; then
    rm -f "${dest}/config/settings.json" "${dest}/config/workspace.fx.json"
    rmdir "${dest}/config" 2>/dev/null || true
    removed=1
  fi
  if [[ $removed -eq 1 ]]; then
    ok "removed leftover kit files from ${dest}"
  fi
}

append_path_line() {
  local rc="$1" dest="$2" marker="# fx CLI (setup-fx.sh)"
  [[ -n "$rc" ]] || return 0
  if [[ -f "$rc" ]] && grep -Fq "$dest" "$rc" 2>/dev/null; then
    return 0
  fi
  if [[ ! -f "$rc" ]]; then
    case "$rc" in
      */.zshrc|*/.zprofile|*/.bashrc|*/.bash_profile) : ;;
      *) return 0 ;;
    esac
    touch "$rc"
  fi
  {
    printf '\n%s\n' "$marker"
    printf 'export PATH="%s:$PATH"\n' "$dest"
    if is_linux; then
      printf 'export FX_DISABLE_KEYCHAIN="${FX_DISABLE_KEYCHAIN:-1}"\n'
    fi
    printf 'export FX_MODEL="${FX_MODEL:-%s}"\n' "$DEFAULT_MODEL"
  } >> "$rc"
  ok "appended PATH to ${rc}"
}

# Source ~/.config/fx/env from login/interactive shells so the user never
# has to export AI_GATEWAY_API_KEY by hand.
ensure_env_autoload() {
  [[ "$MODE" == "host" ]] || return 0
  local rc marker="# fx env (setup-fx.sh)"
  local block
  block="${marker}"'
if [ -f "$HOME/.config/fx/env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$HOME/.config/fx/env"
  set +a
fi'
  for rc in "${HOME}/.bashrc" "${HOME}/.zshrc" "${HOME}/.zprofile" "${HOME}/.profile"; do
    if [[ -f "$rc" ]] && grep -Fq "$marker" "$rc" 2>/dev/null; then
      continue
    fi
    touch "$rc"
    printf '\n%s\n' "$block" >> "$rc"
    ok "auto-load ~/.config/fx/env from ${rc}"
  done
  if [[ -f "${HOME}/.bash_profile" ]] && ! grep -Fq "$marker" "${HOME}/.bash_profile" 2>/dev/null; then
    printf '\n%s\n' "$block" >> "${HOME}/.bash_profile"
    ok "auto-load ~/.config/fx/env from ${HOME}/.bash_profile"
  fi
}

ensure_path_export() {
  local dest
  dest="$(install_dir_for_mode)"
  case ":${PATH}:" in
    *":${dest}:"*) ;;
    *) export PATH="${dest}:${PATH}" ;;
  esac
  [[ "$MODE" == "host" && $SYSTEM_INSTALL -eq 0 ]] || return 0
  append_path_line "${HOME}/.bashrc" "$dest"
  if is_darwin || [[ "${SHELL:-}" == *zsh ]]; then
    append_path_line "${HOME}/.zshrc" "$dest"
    append_path_line "${HOME}/.zprofile" "$dest"
  fi
  if [[ -f "${HOME}/.bash_profile" ]]; then
    append_path_line "${HOME}/.bash_profile" "$dest"
  fi
}

profile_dir() { printf '%s\n' "${FX_HOME:-${HOME}/.fx}"; }

sandbox_for_this_os() {
  if [[ "$MODE" == "container" ]]; then
    printf 'none\n'; return
  fi
  if is_darwin; then printf 'os\n'; else printf 'none\n'; fi
}

write_settings() {
  local dir settings sandbox
  dir="$(profile_dir)"
  settings="${dir}/settings.json"
  sandbox="$(sandbox_for_this_os)"
  mkdir -p "$dir"
  chmod 0700 "$dir" 2>/dev/null || true
  if [[ -f "$settings" ]]; then
    log "leaving existing ${settings} in place"
    return 0
  fi
  cat > "$settings" <<EOF
{
  "model": "${DEFAULT_MODEL}",
  "permission_mode": "auto",
  "sandbox": "${sandbox}",
  "auto_upgrade": false,
  "update_channel": "stable",
  "fast_mode": false
}
EOF
  chmod 0600 "$settings"
  ok "wrote ${settings} (sandbox=${sandbox})"
}

maybe_store_key_hint() {
  local key="${AI_GATEWAY_API_KEY:-}"
  [[ -n "$key" ]] || return 0
  if [[ "$MODE" == "container" ]]; then
    warn "AI_GATEWAY_API_KEY set during container setup; not written into the image."
    return 0
  fi
  local hint="${HOME}/.config/fx/env"
  mkdir -p "$(dirname "$hint")"
  chmod 0700 "$(dirname "$hint")" 2>/dev/null || true
  local old_umask
  old_umask="$(umask)"
  umask 077
  local escaped
  escaped="$(printf '%s' "$key" | sed "s/'/'\\\\''/g")"
  cat > "$hint" <<EOF
# generated by setup-fx.sh — mode 0600, never commit
export FX_MODEL="${DEFAULT_MODEL}"
export FX_PERMISSION_MODE="\${FX_PERMISSION_MODE:-auto}"
export AI_GATEWAY_API_KEY='${escaped}'
EOF
  if is_linux; then
    printf 'export FX_DISABLE_KEYCHAIN=1\n' >> "$hint"
  fi
  umask "$old_umask"
  chmod 0600 "$hint"
  ok "saved key to ${hint} (0600) — new shells pick it up automatically"
}

# Ask on the controlling TTY (so `curl | bash` still works). 30s timeout
# (override with --key-timeout / KEY_TIMEOUT) so a missing operator cannot
# stall a non-interactive install. Never echoes the secret.
prompt_gateway_key() {
  if [[ "$MODE" == "container" ]]; then
    return 0
  fi
  if [[ ${FORCE_KEY_PROMPT:-0} -eq 0 ]]; then
    if [[ $SKIP_KEY_PROMPT -eq 1 || $NONINTERACTIVE -eq 1 ]]; then
      log "skipping API key prompt"
      return 0
    fi
    if [[ "${CI:-}" == "true" || "${CI:-}" == "1" ]]; then
      log "CI=true — skipping API key prompt"
      return 0
    fi
    if [[ -n "${AI_GATEWAY_API_KEY:-}" ]]; then
      log "AI_GATEWAY_API_KEY already set in the environment"
      return 0
    fi
    if [[ -r "${HOME}/.config/fx/env" ]]; then
      # shellcheck disable=SC1091
      set -a
      # shellcheck disable=SC1090
      . "${HOME}/.config/fx/env"
      set +a
      if [[ -n "${AI_GATEWAY_API_KEY:-}" ]]; then
        ok "using existing key in ${HOME}/.config/fx/env"
        return 0
      fi
    fi
  else
    # fxs key: ignore a stale env var so the new paste wins.
    unset AI_GATEWAY_API_KEY
  fi

  # /dev/tty can exist as a node and still be unopenable (no controlling
  # terminal in CI / some containers). Probe by opening it.
  if ! { : < /dev/tty; } 2>/dev/null; then
    warn "no controlling TTY — skipping API key prompt"
    return 0
  fi

  printf '\n' >&2
  printf '%s Vercel AI Gateway key (vck_…)\n' "${LOG_PREFIX}" >&2
  printf '%s Hidden input · %ss timeout · Enter skips · later: fxs key\n' "${LOG_PREFIX}" "${KEY_TIMEOUT}" >&2
  printf '%s Key: ' "${LOG_PREFIX}" >&2

  local key="" status=0
  # IFS= keeps the value intact. -s hides it. -t is the hang-guard.
  # Read from /dev/tty so a piped installer can still take keyboard input.
  if [[ "${KEY_TIMEOUT}" == "0" ]]; then
    IFS= read -r -s key < /dev/tty || status=$?
  else
    IFS= read -r -s -t "${KEY_TIMEOUT}" key < /dev/tty || status=$?
  fi
  printf '\n' >&2

  if [[ $status -ne 0 ]]; then
    if [[ $status -gt 128 ]]; then
      warn "no key within ${KEY_TIMEOUT}s — continuing without one (later: fxs key)"
    else
      warn "key prompt skipped (later: fxs key)"
    fi
    return 0
  fi

  key="$(printf '%s' "$key" | tr -d '\r')"
  # trim leading/trailing whitespace without echo
  key="${key#"${key%%[![:space:]]*}"}"
  key="${key%"${key##*[![:space:]]}"}"

  if [[ -z "$key" ]]; then
    log "empty key — skipped (set one later with: fxs key)"
    return 0
  fi
  if [[ "$key" != vck_* ]]; then
    warn "value does not start with vck_ — storing it anyway"
  fi
  export AI_GATEWAY_API_KEY="$key"
  ok "key accepted (not printed)"
}

install_docker_engine() {
  [[ "$MODE" == "host" ]] || die "--with-docker is host-only"
  if command -v docker >/dev/null 2>&1; then
    ok "docker already present: $(docker --version 2>/dev/null || true)"
    return 0
  fi
  if is_darwin; then
    if command -v brew >/dev/null 2>&1; then
      log "brew install --cask docker"
      brew install --cask docker
      warn "Open Docker.app once, then re-run --build-image."
      return 0
    fi
    die "Install Docker Desktop: https://docs.docker.com/desktop/setup/install/mac-install/"
  fi
  if ! linux_is_debianish; then
    die "Install Docker Engine: https://docs.docker.com/engine/install/"
  fi
  log "installing Docker Engine"
  export DEBIAN_FRONTEND=noninteractive
  run_root apt-get update -y -qq
  run_root apt-get install -y --no-install-recommends ca-certificates curl gnupg
  run_root install -m 0755 -d /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/docker.asc ]]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | run_root tee /etc/apt/keyrings/docker.asc >/dev/null
    run_root chmod a+r /etc/apt/keyrings/docker.asc
  fi
  local codename arch
  # shellcheck disable=SC1091
  . /etc/os-release
  codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-stable}}"
  arch="$(dpkg --print-architecture)"
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' \
    "$arch" "$codename" | run_root tee /etc/apt/sources.list.d/docker.list >/dev/null
  run_root apt-get update -y -qq
  run_root apt-get install -y --no-install-recommends \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  if command -v systemctl >/dev/null 2>&1; then
    run_root systemctl enable --now docker 2>/dev/null || warn "could not enable docker.service"
  fi
  if ! is_root; then
    run_root usermod -aG docker "${USER}" || true
    warn "log out/in (or: newgrp docker) before using docker without sudo"
  fi
  ok "Docker Engine installed"
}

cmd_build() {
  need_cmd docker
  local here
  here="$(write_kit)"
  log "building ${IMAGE_NAME} from ${here} (linux image; host ${UNAME_S}/${UNAME_M})"
  BUILD_ARGS=(
    --pull
    --tag "$IMAGE_NAME"
    --build-arg "FX_VERSION=${FX_VERSION:-$(resolve_version)}"
    --build-arg "FX_MODEL=${DEFAULT_MODEL}"
  )
  if [[ -n "${FX_APT_MIRROR:-}" ]]; then
    BUILD_ARGS+=(--build-arg "APT_MIRROR=${FX_APT_MIRROR}")
    log "apt mirror: ${FX_APT_MIRROR}"
  fi
  docker build \
    "${BUILD_ARGS[@]}" \
    -f "${here}/Dockerfile" \
    "$here"
  ok "built ${IMAGE_NAME}"
}

cmd_run() {
  scrub_path_pollution
  local here
  here="$(write_kit)"
  if [[ ! -x "${here}/run-fx.sh" ]]; then
    die "run-fx.sh was not written to ${here}"
  fi
  if [[ "$CMD" == "ask" ]]; then
    exec "${here}/run-fx.sh" ask "${RUN_ARGS[@]+"${RUN_ARGS[@]}"}"
  fi
  exec "${here}/run-fx.sh" "${RUN_ARGS[@]+"${RUN_ARGS[@]}"}"
}

run_doctor() {
  local dest bin
  dest="$(install_dir_for_mode)"
  bin="${dest}/fx"
  [[ -x "$bin" ]] || bin="$(command -v fx || true)"
  [[ -x "$bin" ]] || die "fx not on PATH; export PATH=${dest}:\$PATH"
  log "fx version: $("$bin" --version 2>/dev/null || echo unknown)"
  if [[ -n "${AI_GATEWAY_API_KEY:-}" ]]; then
    FX_MODEL="$DEFAULT_MODEL" "$bin" doctor || warn "fx doctor reported issues"
  else
    warn "AI_GATEWAY_API_KEY unset — doctor will fail auth (expected)"
    FX_MODEL="$DEFAULT_MODEL" "$bin" doctor || true
  fi
}

cmd_status() {
  if [[ -z "$MODE" ]]; then
    if in_container; then MODE="container"; else MODE="host"; fi
  fi
  local dest bin key_state docker_state image_state path_state settings sandbox
  dest="$(install_dir_for_mode)"
  bin="${dest}/fx"
  [[ -x "$bin" ]] || bin="$(command -v fx || true)"

  if [[ -n "${AI_GATEWAY_API_KEY:-}" ]]; then
    key_state="ok (environment)"
  elif [[ -r "${HOME}/.config/fx/env" ]]; then
    key_state="ok (~/.config/fx/env)"
  else
    key_state="missing — run: fxs key"
  fi

  if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
      docker_state="running"
    else
      docker_state="installed, daemon not running"
    fi
  else
    docker_state="not installed"
  fi

  if command -v docker >/dev/null 2>&1 && docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    image_state="present (${IMAGE_NAME})"
  else
    image_state="not built — fxs build"
  fi

  case ":${PATH}:" in
    *":${dest}:"*) path_state="ok (${dest})" ;;
    *) path_state="missing ${dest} — export PATH=\"${dest}:\$PATH\"" ;;
  esac

  sandbox="$(sandbox_for_this_os)"
  settings="${HOME}/.fx/settings.json"
  if [[ -r "$settings" ]]; then
    local from_file
    from_file="$(awk -F '"' '/"sandbox"/ {print $4; exit}' "$settings" 2>/dev/null || true)"
    [[ -n "$from_file" ]] && sandbox="$from_file"
  fi
  [[ -n "$sandbox" ]] || sandbox="none"

  cat >&2 <<EOF
${LOG_PREFIX} status

  os       ${UNAME_S}/${UNAME_M}
  fx       $({ [[ -n "$bin" && -x "$bin" ]] && "$bin" --version; } 2>/dev/null || echo "not installed")
  path     ${path_state}
  key      ${key_state}
  model    ${DEFAULT_MODEL}
  sandbox  ${sandbox}   (fx native; Linux needs Docker)
  docker   ${docker_state}
  image    ${image_state}
  kit      $(kit_dest)
  cli      $(command -v fxs 2>/dev/null || echo "fxs not on PATH")

  fx ask --no-save "Reply with: GLM52_OK"
  fxs run
EOF
}

cmd_key() {
  if [[ -z "$MODE" ]]; then MODE="host"; fi
  FORCE_KEY_PROMPT=1
  SKIP_KEY_PROMPT=0
  NONINTERACTIVE=0
  prompt_gateway_key
  maybe_store_key_hint
  if [[ -n "${AI_GATEWAY_API_KEY:-}" ]]; then
    ok "key saved — new shells and the fx wrapper will pick it up"
  else
    warn "no key stored"
  fi
}

cmd_uninstall() {
  local dest kit state
  dest="$(install_dir_for_mode)"
  kit="$(kit_dest)"
  state="${HOME}/.local/share/fx-sandbox/state"

  cat >&2 <<EOF
${LOG_PREFIX} uninstall will remove:
  ${dest}/fx
  ${dest}/fxs  ${dest}/fx-sandbox  ${dest}/setup-fx  ${dest}/setup-fx.sh  ${dest}/run-fx
  ${kit}
EOF

  if [[ $ASSUME_YES -eq 0 ]]; then
    if ! { : < /dev/tty; } 2>/dev/null; then
      die "no TTY — re-run with: fxs uninstall -y"
    fi
    printf '%s continue? [y/N] (30s) ' "${LOG_PREFIX}" >&2
    local ans="" status=0
    IFS= read -r -t 30 ans < /dev/tty || status=$?
    printf '\n' >&2
    [[ $status -eq 0 && "$ans" =~ ^[Yy]$ ]] || die "aborted"
  fi

  rm -f "${dest}/fx" "${dest}/fxs" "${dest}/fx-sandbox" \
        "${dest}/setup-fx" "${dest}/setup-fx.sh" "${dest}/run-fx"
  rm -rf "${kit}"
  ok "removed CLI and kit"

  if [[ $ASSUME_YES -eq 1 ]]; then
    return 0
  fi
  if ! { : < /dev/tty; } 2>/dev/null; then
    return 0
  fi
  printf '%s also delete ~/.fx, ~/.config/fx, and fxs session state? [y/N] (30s) ' "${LOG_PREFIX}" >&2
  local ans2="" st2=0
  IFS= read -r -t 30 ans2 < /dev/tty || st2=$?
  printf '\n' >&2
  if [[ $st2 -eq 0 && "$ans2" =~ ^[Yy]$ ]]; then
    rm -rf "${HOME}/.fx" "${HOME}/.config/fx" "$state"
    ok "removed profile, key file, and ${state}"
  else
    log "left ~/.fx, ~/.config/fx, and ${state} in place"
  fi
}

cmd_install() {
  if [[ -z "$MODE" ]]; then
    if in_container; then MODE="container"; else MODE="host"; fi
  fi
  if [[ "$MODE" == "container" ]]; then
    INSTALL_DEV_TOOLS=1
    SYSTEM_INSTALL=1
  fi

  log "mode=${MODE} os=${UNAME_S} arch=${UNAME_M} piped=$(is_piped && echo yes || echo no)"
  require_supported_os

  if [[ $CONFIGURE_ONLY -eq 0 ]]; then
    ensure_packages
    download_and_install_fx
  fi

  local here=""
  if [[ "$MODE" == "host" ]]; then
    here="$(write_kit)"
    link_cli "$here"
  fi

  ensure_path_export
  ensure_env_autoload
  write_settings
  prompt_gateway_key
  maybe_store_key_hint

  if [[ $WITH_DOCKER -eq 1 ]]; then
    install_docker_engine
  fi
  if [[ $BUILD_IMAGE -eq 1 ]]; then
    cmd_build
  fi
  if [[ $DOCTOR -eq 1 ]]; then
    run_doctor
  fi

  local key_state="missing — fxs key"
  if [[ -n "${AI_GATEWAY_API_KEY:-}" ]]; then
    key_state="saved in ~/.config/fx/env"
  fi
  local ver
  ver="$("$(install_dir_for_mode)/fx" --version 2>/dev/null || echo '?')"

  cat >&2 <<EOF

${C_GRN}${LOG_PREFIX} done.${C_OFF}

  ${UNAME_S}/${UNAME_M}   fx ${ver}
  key     ${key_state}
  kit     ${here:-$(kit_dest)}

  This tab cannot inherit a piped install. Run:
    export PATH="\$HOME/.local/bin:\$PATH"

  fx ask --no-save "Reply with: GLM52_OK"    # native
  fxs                                        # Docker sandbox, yolo
  fxs -c                                     # resume last fxs session
  fxs status                                 # check this machine
  fxs key                                    # paste / replace the gateway key
EOF
}

main() {
  parse_args "$@"
  # Piped stdin (curl | bash) is not a TTY — that must NOT disable the
  # key prompt. We still auto-yes package managers so apt cannot hang.
  if [[ ! -t 0 ]]; then
    ASSUME_YES=1
  fi

  case "$CMD" in
    install) cmd_install ;;
    unpack)
      if [[ -n "$UNPACK_DIR" ]]; then
        write_kit "$UNPACK_DIR" >/dev/null
      else
        write_kit >/dev/null
      fi
      ;;
    build)
      if [[ -z "$MODE" ]]; then MODE="host"; fi
      cmd_build
      ;;
    run|ask)
      cmd_run
      ;;
    status)
      cmd_status
      ;;
    doctor)
      cmd_status
      run_doctor
      ;;
    key)
      cmd_key
      ;;
    uninstall)
      cmd_uninstall
      ;;
    *) die "unknown command: $CMD" ;;
  esac
}

main "$@"
