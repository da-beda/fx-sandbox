# Sandboxed fx — one script, Linux + macOS

**You only need `setup-fx.sh`.** The Dockerfile, entrypoint, `run-fx`
wrapper, compose file, and configs are *embedded in that file* and
written out on demand. `curl | bash` does not fetch anything else
except the fx release tarball and its `.sha256`.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/setup-fx.sh | bash
```

With Docker + the sandbox image:

```bash
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/setup-fx.sh \
  | bash -s -- --host --with-docker --build-image --doctor
```

Save the file and keep using it (no other files required):

```bash
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/setup-fx.sh \
  -o setup-fx.sh
chmod +x setup-fx.sh

./setup-fx.sh                            # install fx
./setup-fx.sh --host --with-docker --build-image
./setup-fx.sh run                        # sandboxed fx on $PWD
./setup-fx.sh ask --no-save "Reply with: GLM52_OK"
./setup-fx.sh unpack ./out               # optional: emit Dockerfile etc.
```

Works on **macOS** (Intel + Apple Silicon, stock Bash 3.2) and **Linux**.

The installer asks for a Vercel AI Gateway key on the controlling TTY
(so `curl | bash` still works). Input is hidden, there is a **30 second
timeout**, and an empty / timed-out answer just continues. The key is
written to `~/.config/fx/env` (mode 0600) and sourced from
`~/.bashrc` / `~/.zshrc` / `~/.profile` — **no `export` needed**
afterwards. `--non-interactive`, `--skip-key-prompt`, `CI=true`, and
`--in-container` skip the prompt. `--key-timeout SEC` changes the wait
(`0` = wait forever). The key is never baked into the Docker image.

## What the script contains

| Embedded | Written when |
| --- | --- |
| `Dockerfile` (self-contained Linux image — installs fx itself) | `install` / `unpack` / `build` / `run` |
| `entrypoint.sh` | same |
| `run-fx.sh` (locked-down `docker run`) | same |
| `docker-compose.yml`, `.env.example`, configs | same |

Network after you have the `.sh`:

1. `https://releases.fx.sh/<ver>/fx-<os>-<arch>.tar.gz` + `.sha256`
2. (optional) Docker Hub, to pull `ubuntu:24.04` when you `--build-image`

No GitHub raw fetches of companion files.

## Platform notes

| | macOS host | Linux host | Container image |
|---|---|---|---|
| fx binary | `macos-x86_64` / `macos-aarch64` | `linux-x86_64` / `linux-aarch64` | always `linux-*` |
| fx native sandbox | `os` | `none` (unsupported) | `none` |
| Isolation | native `os` **or** Docker | **Docker** (`setup-fx.sh run`) | the container |

`--with-docker`: Debian/Ubuntu → Engine apt; macOS → Docker Desktop cask.

`setup-fx.sh run` refuses `/`, `$HOME`, `/Users`, `/System`, `/Library`,
the Docker socket, root, and `--yolo` (unless `--allow-yolo`).

## After install

```bash
# key already in ~/.config/fx/env — open a new shell, or:
#   set -a && . ~/.config/fx/env && set +a

cd /path/to/one/project
setup-fx.sh run          # or: run-fx
setup-fx.sh ask "what is 17*19?"
```

Repo (optional extras for browsing): [github.com/da-beda/fx-sandbox](https://github.com/da-beda/fx-sandbox)
