#!/usr/bin/env bash
# install.sh — install native fx, fxs, or both without turning fxs into a
# package manager or host provisioner.
set -euo pipefail
IFS=$'\n\t'

TARGET=""
NONINTERACTIVE=0
BUILD_MODE=auto
FX_VERSION="${FX_VERSION:-}"
FXS_REF="${FXS_REF:-main}"
FXS_INSTALL_DIR="${FXS_INSTALL_DIR:-${HOME}/.local/bin}"
FXS_DATA_DIR="${FXS_DATA_DIR:-${HOME}/.local/share/fxs}"
FXS_IMAGE="${FXS_IMAGE:-fxs:latest}"
RAW_BASE="${FXS_RAW_BASE:-https://raw.githubusercontent.com/da-beda/fx-sandbox}"

usage() {
  cat <<'EOF_USAGE'
fx-sandbox installer

USAGE
  install.sh [--both | --fxs-only | --native-only] [options]

MODES
  --both          native fx + fxs (default for non-interactive use)
  --fxs-only      install only the sandbox wrapper and reference Dockerfile
  --native-only   delegate only to fx's canonical installer

OPTIONS
  --fx-version V  pin the fx version (native and reference image)
  --fxs-ref REF   fetch fxs files from this git tag/branch (default: main)
  --build-image   require building the reference image during installation
  --no-build      never build the reference image during installation
  --non-interactive
  -h, --help

ALIASES
  --sandbox-only = --fxs-only
  --fx-only      = --native-only
  --skip-fx      = --fxs-only

Docker itself is never installed or configured by this script.
EOF_USAGE
}

die()  { printf 'install.sh: %s\n' "$*" >&2; exit 1; }
warn() { printf 'install.sh: warning: %s\n' "$*" >&2; }
log()  { printf 'install.sh: %s\n' "$*" >&2; }

curl_retry() {
  curl -fsSL --retry 3 --connect-timeout 10 --max-time 60 "$@"
}

validate_fx_version() {
  local version="$1"
  [[ -n "$version" ]] || die "fx version must not be empty"
  case "$version" in
    *[!0-9A-Za-z._+-]*) die "invalid fx version: $version" ;;
  esac
}

set_target() {
  local next="$1"
  if [[ -n "$TARGET" && "$TARGET" != "$next" ]]; then
    die "conflicting install modes: $TARGET and $next"
  fi
  TARGET="$next"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --both) set_target both; shift ;;
    --fxs-only|--sandbox-only|--skip-fx) set_target fxs; shift ;;
    --native-only|--fx-only) set_target native; shift ;;
    --fx-version)
      [[ $# -ge 2 && -n "$2" ]] || die "--fx-version needs a version"
      FX_VERSION="$2"; shift 2 ;;
    --fxs-ref)
      [[ $# -ge 2 && -n "$2" ]] || die "--fxs-ref needs a ref"
      FXS_REF="$2"; shift 2 ;;
    --build-image) BUILD_MODE=yes; shift ;;
    --no-build) BUILD_MODE=no; shift ;;
    --non-interactive) NONINTERACTIVE=1; shift ;;
    --with-docker)
      die "--with-docker was removed. Install Docker separately; fxs never provisions the host."
      ;;
    --system|--install-dev-tools|--configure-only|--skip-packages|--skip-apt)
      die "$1 belonged to the old host-provisioning installer and is no longer supported"
      ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -z "$FX_VERSION" ]] || validate_fx_version "$FX_VERSION"

have_tty() { { : < /dev/tty; } 2>/dev/null; }

choose_target() {
  [[ -n "$TARGET" ]] && return 0
  if [[ "$NONINTERACTIVE" == "1" || "${CI:-}" == "1" || "${CI:-}" == "true" ]] || ! have_tty; then
    TARGET=both
    return 0
  fi
  cat >/dev/tty <<'EOF_PROMPT'

What do you want to install?

  1) Both          native fx + sandboxed fxs  [recommended]
  2) fxs only      sandbox wrapper only; Docker required to run it
  3) Native only   canonical host-native fx

EOF_PROMPT
  printf 'Choice [1]: ' >/dev/tty
  local answer=""
  IFS= read -r answer </dev/tty || answer=""
  case "$answer" in
    ''|1|both|Both) TARGET=both ;;
    2|fxs|sandbox|fxs-only) TARGET=fxs ;;
    3|fx|native|native-only) TARGET=native ;;
    *) die "invalid choice: $answer" ;;
  esac
}

choose_target
command -v curl >/dev/null 2>&1 || die "curl is required"

install_native_fx() {
  log "native fx -> canonical https://fx.sh/setup.sh"
  if [[ -n "$FX_VERSION" ]]; then
    curl_retry https://fx.sh/setup.sh | bash -s -- "$FX_VERSION"
  else
    curl_retry https://fx.sh/setup.sh | bash
  fi
}

local_source_dir() {
  local src="${BASH_SOURCE[0]:-}"
  [[ -n "$src" && -f "$src" ]] || return 1
  local d
  d="$(cd "$(dirname "$src")" && pwd -P)"
  [[ -f "$d/fxs" && -f "$d/Dockerfile" ]] || return 1
  printf '%s\n' "$d"
}

fetch_or_copy() {
  local rel="$1" dest="$2" srcdir=""
  if srcdir="$(local_source_dir 2>/dev/null)"; then
    cp "$srcdir/$rel" "$dest"
  else
    curl_retry -o "$dest" "${RAW_BASE}/${FXS_REF}/${rel}"
  fi
}

install_fxs() {
  mkdir -p "$FXS_INSTALL_DIR" "$FXS_DATA_DIR"
  local tmpdir
  tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/fxs-install.XXXXXX")"

  # Fetch/copy the complete pair before replacing either installed file. A
  # transient failure must not leave a new wrapper with an old/partial Dockerfile.
  if ! fetch_or_copy fxs "$tmpdir/fxs"; then
    rm -rf "$tmpdir"
    die "could not obtain fxs"
  fi
  if ! fetch_or_copy Dockerfile "$tmpdir/Dockerfile"; then
    rm -rf "$tmpdir"
    die "could not obtain the reference Dockerfile"
  fi

  install -m 0755 "$tmpdir/fxs" "$FXS_INSTALL_DIR/fxs"
  install -m 0644 "$tmpdir/Dockerfile" "$FXS_DATA_DIR/Dockerfile"
  rm -rf "$tmpdir"
  log "fxs -> $FXS_INSTALL_DIR/fxs"

  case ":$PATH:" in
    *":$FXS_INSTALL_DIR:"*) ;;
    *) warn "$FXS_INSTALL_DIR is not on PATH; add: export PATH=\"$FXS_INSTALL_DIR:\$PATH\"" ;;
  esac

  if [[ "$BUILD_MODE" == "no" ]]; then
    return 0
  fi
  if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    if [[ "$BUILD_MODE" == "yes" ]]; then
      die "Docker is required by --build-image but is unavailable or stopped"
    fi
    warn "Docker is unavailable/stopped. fxs is installed but will fail closed until Docker is ready."
    warn "Then build the reference image with: fxs --build-image"
    return 0
  fi
  log "building reference image $FXS_IMAGE"
  FXS_DOCKERFILE="$FXS_DATA_DIR/Dockerfile" \
  FXS_IMAGE="$FXS_IMAGE" \
  FXS_FX_VERSION="$FX_VERSION" \
    "$FXS_INSTALL_DIR/fxs" --build-image
}

case "$TARGET" in
  native) install_native_fx ;;
  fxs) install_fxs ;;
  both) install_native_fx; install_fxs ;;
  *) die "internal error: target=$TARGET" ;;
esac

cat >&2 <<EOF_DONE

Done.
  native fx: $([[ "$TARGET" == native || "$TARGET" == both ]] && echo installed || echo skipped)
  fxs:       $([[ "$TARGET" == fxs || "$TARGET" == both ]] && echo installed || echo skipped)

Native authentication remains fx-owned:  fx login  /  fx setup
Sandboxed authentication lives in fxs's isolated project state:  fxs login  /  fxs setup
EOF_DONE
