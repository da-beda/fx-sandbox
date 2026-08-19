# fx-sandbox

One Bash script that installs [fx](https://fx.sh) (Vercel Labs’ coding agent)
and, if you want it, a locked-down Docker sandbox so the agent only sees
**one project directory**.

Works on **macOS** (Intel and Apple Silicon, including stock Bash 3.2)
and **Linux**. You only need `setup-fx.sh` — the Dockerfile, entrypoint,
compose file, and `run-fx` wrapper are embedded in it.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/setup-fx.sh | bash
```

That installs the `fx` binary, writes `~/.fx/settings.json`, and asks
for a Vercel AI Gateway key (`vck_…`) on the terminal.

Add Docker and build the sandbox image in the same step:

```bash
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/setup-fx.sh \
  | bash -s -- --host --with-docker --build-image
```

Or keep the file and run commands yourself:

```bash
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/setup-fx.sh -o setup-fx.sh
chmod +x setup-fx.sh
./setup-fx.sh                            # install
./setup-fx.sh --host --with-docker --build-image
```

## Use

In the **same** terminal that ran `curl | bash`, load PATH + key first
(the parent shell cannot be changed by a pipe):

```bash
export PATH="$HOME/.local/bin:$PATH"
set -a && . ~/.config/fx/env && set +a
```

Or just open a new tab.

```bash
cd /path/to/one/project
fx ask --no-save "Reply with: GLM52_OK"   # native (macOS has an OS sandbox)
setup-fx run                               # container; needs Docker running
setup-fx ask "what is 17*19?"
run-fx                                     # same as setup-fx run
```

`fx` on PATH is a tiny wrapper that sources `~/.config/fx/env` before
execing the real binary, so you do not need `export` after a re-install.

On Linux, prefer `setup-fx run`. Native fx has **no OS sandbox** there.

On macOS, `run-fx` needs **Docker Desktop open** (whale idle in the
menu bar). If you only want native fx, skip Docker.

## API key

The installer prompts on the controlling TTY (so `curl | bash` still
works). The key is hidden as you paste it.

| | |
| --- | --- |
| Timeout | **30 seconds** — install continues if you skip or the session has no TTY |
| Stored at | `~/.config/fx/env` (mode `0600`) |
| Loaded by | `~/.bashrc`, `~/.zshrc`, `~/.zprofile`, `~/.profile` |
| Not stored in | the Docker image, git, or settings.json |

After install, open a new terminal. You should not need `export`.

Skip the prompt with `--skip-key-prompt`, `--non-interactive`,
`--in-container`, or `CI=true`. Change the wait with
`--key-timeout SEC` (`0` = wait forever).

## Commands

| Command | What it does |
| --- | --- |
| `setup-fx.sh` / `install` | Install fx + write the embedded kit |
| `setup-fx.sh run [args]` | `docker run` against `$PWD` with the sandbox flags |
| `setup-fx.sh ask [args]` | One-shot `fx ask` inside that container |
| `setup-fx.sh build` | Build `fx-sandbox:latest` from the embedded Dockerfile |
| `setup-fx.sh unpack [dir]` | Write Dockerfile, compose, configs out as normal files |

Useful install flags: `--host`, `--in-container`, `--with-docker`,
`--build-image`, `--doctor`, `--system`, `--install-dev-tools`,
`--skip-packages`, `--skip-fx`, `--configure-only`.

## What the sandbox actually enforces

`setup-fx.sh run` always:

- maps `--user $(id -u):$(id -g)` so files you create belong to you
- uses a read-only image rootfs + tmpfs `/tmp` and `$HOME`
- drops all capabilities and sets `no-new-privileges`
- bind-mounts **only** the project → `/workspace`
- injects the API key via `-e`, never `COPY`

It **refuses** to start as root, to mount `/`, `$HOME`, `/Users`,
`/System`, `/Library`, or a Docker socket, and to pass `--yolo`
unless you also pass `--allow-yolo`.

It does **not** stop the model from reading or uploading that one
mounted project, or from using secrets already sitting in it.

## Platforms

| | macOS host | Linux host | Image |
| --- | --- | --- | --- |
| fx binary | `macos-x86_64` / `macos-aarch64` | `linux-x86_64` / `linux-aarch64` | always Linux |
| fx `os` sandbox | yes | no | no |
| Isolation | native `os`, or Docker | **Docker** | the container |

`--with-docker` on Debian/Ubuntu installs Docker Engine. On macOS it
installs Docker Desktop via Homebrew (`brew install --cask docker`);
open Docker.app once before `--build-image`.

The image is Ubuntu 24.04. Docker Desktop on a Mac builds
`linux/arm64` or `linux/amd64` on its own.

Default model is `zai/glm-5.2` (not `-fast`).

## Network

After you have the script, it only talks to:

1. `https://releases.fx.sh/…` — fx tarball + `.sha256`
2. Docker Hub — `ubuntu:24.04`, if you build the image
3. `https://ai-gateway.vercel.sh` — at **run** time, for model calls

Companion files are not fetched from GitHub.

## Uninstall

```bash
rm -f ~/.local/bin/fx ~/.local/bin/run-fx ~/.local/bin/fx-sandbox
rm -rf ~/.fx ~/.config/fx ~/.local/share/fx-sandbox
docker image rm fx-sandbox:latest
docker volume ls | awk '/fx-state/ {print $2}' | xargs -r docker volume rm
```

Rotate a `vck_` key that has ever been pasted into chat:
<https://vercel.com/d?to=%2F%5Bteam%5D%2F%7E%2Fai-gateway%2Fapi-keys>
