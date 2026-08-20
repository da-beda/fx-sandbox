# fx-sandbox

Install [fx](https://fx.sh) (Vercel Labs’ coding agent) and, optionally,
run it in a Docker sandbox that can see **one project directory**.

macOS (Intel + Apple Silicon, stock Bash 3.2) and Linux.

After install you type two commands:

| Command | Meaning |
| --- | --- |
| `fx` | Native agent. Wrapper loads your API key. |
| `fxs` | This toolkit: sandbox, status, key, uninstall. |

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/setup-fx.sh | bash
```

That installs `fx`, puts `fxs` on `~/.local/bin`, and asks for a
Vercel AI Gateway key (`vck_…`). Hidden input, 30s timeout.

Also build the sandbox image:

```bash
curl -fsSL https://raw.githubusercontent.com/da-beda/fx-sandbox/main/setup-fx.sh \
  | bash -s -- --with-docker --build-image
```

`curl | bash` cannot change the shell you are typing in. In **that**
tab:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Or open a new tab.

## Use

```bash
cd /path/to/one/project

fx ask --no-save "Reply with: GLM52_OK"   # native
fxs                                        # Docker sandbox, yolo
fxs -c                                     # resume last fxs session
fxs --no-yolo                              # prompt before tools
fxs ask "what is 17*19?"
fxs status
fxs key                                    # paste / replace the key
```

On macOS, native `fx` already uses the OS sandbox (`sandbox=os`).
Docker is optional and needs Docker Desktop **running**.

On Linux, native fx has no OS sandbox — prefer `fxs run`.

## Commands

| | |
| --- | --- |
| `fxs` / `fxs run` | Sandboxed fx against `$PWD` (yolo by default) |
| `fxs --no-yolo` | Same, but fx asks before tools |
| `fxs run -c` | Resume last fxs session in this directory |
| `fxs sessions` | List fxs sessions for `$PWD` |
| `fxs ask …` | One-shot `fx ask` in that container |
| `fxs ui` | Optional local web UI (`http://127.0.0.1:8787`) |
| `fxs build` | Build `fx-sandbox:latest` |
| `fxs status` | Binary, key, Docker, image, PATH |
| `fxs key` | (Re)prompt for the gateway key |
| `fxs unpack [dir]` | Write Dockerfile / compose out |
| `fxs uninstall` | Remove the CLI and kit (`-y` to skip confirm) |
| `fxs install` | Re-run the installer |

`setup-fx`, `setup-fx.sh`, `run-fx`, and `fx-sandbox` stay on PATH as
aliases of `fxs` so older docs keep working.

## Sessions

`fxs` keeps **its own** sessions, per project, under
`~/.local/share/fx-sandbox/state/<hash>/`. Host `~/.fx` is never mounted
(that would leak every native session into the box).

Inside the container the project is always `/workspace`, so a single
global volume would mix “last” across repos. The hash is of the host path.

```bash
fxs run                  # saves automatically
fxs run -c               # resume last fxs session in $PWD
fxs run --resume last
fxs sessions             # list
fxs run --no-persist     # ephemeral tmpfs home
```

Native `fx -c` still reads `~/.fx` and does not see fxs sessions.

## UI

Optional. Same sandbox, a quieter surface.

```bash
cd /path/to/one/project
fxs ui
```

Opens `http://127.0.0.1:8787`. No npm. Python 3 stdlib. `--bind-all` / `--port` if you need them. `--demo` if Docker is not up.

Folder, sessions (`--resume last`), yolo/auto, theme (system / light / dark), Esc to stop. Same sandbox as `fxs`.

Not a fork of Vercel’s coding-agent-template — that stack is a multi-user cloud product. This is one folder, one agent, one page.

## API key

Stored at `~/.config/fx/env` (mode `0600`). Sourced by the `fx`
wrapper and by `~/.zshrc` / `~/.bashrc` / `~/.profile`. Never written
into the Docker image.

Skip the prompt with `--skip-key-prompt`, `--non-interactive`,
`--in-container`, or `CI=true`. `--key-timeout SEC` changes the wait
(`0` = forever).

## Sandbox

`fxs run` always uses `--user $(id -u):$(id -g)`, a read-only rootfs,
tmpfs home, `--cap-drop ALL`, `no-new-privileges`, and a **single**
bind-mount: the project → `/workspace`. The key goes in via `-e`.

It refuses root, `/`, `$HOME`, `/Users`, `/System`, `/Library`, a
Docker socket, and `--yolo` unless you pass `--allow-yolo`.

It does **not** stop the model from reading or uploading that one
mounted project.

## Platforms

| | macOS | Linux | Image |
| --- | --- | --- | --- |
| fx binary | `macos-*` | `linux-*` | always Linux |
| fx `os` sandbox | yes | no | no |
| Isolation | native `os`, or Docker | **Docker** | the container |

`--with-docker`: Debian/Ubuntu → Engine; macOS → Docker Desktop cask
(`open -a Docker` once before `fxs build`).

Default model: `zai/glm-5.2` (not `-fast`).

## Network

1. `https://releases.fx.sh/…` — fx tarball + checksum  
2. Docker Hub — `ubuntu:24.04`, if you build the image  
3. `https://ai-gateway.vercel.sh` — model calls at run time  

The installer is self-contained. It does not fetch companion files
from GitHub except to persist a copy of itself onto disk after
`curl | bash`.

## Uninstall

```bash
fxs uninstall
# or:
rm -f ~/.local/bin/fx ~/.local/bin/fxs ~/.local/bin/fx-sandbox \
      ~/.local/bin/setup-fx ~/.local/bin/setup-fx.sh ~/.local/bin/run-fx
rm -rf ~/.local/share/fx-sandbox
```

`fxs uninstall` can also drop `~/.fx` and `~/.config/fx` (the key)
if you confirm.

Rotate a `vck_` key that has been pasted into chat:
<https://vercel.com/d?to=%2F%5Bteam%5D%2F%7E%2Fai-gateway%2Fapi-keys>
