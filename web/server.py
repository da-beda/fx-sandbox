#!/usr/bin/env python3
"""fxs ui — local frontend. Python 3.9+ stdlib only."""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
HOST = os.environ.get("FXS_UI_HOST", "127.0.0.1")
PORT = int(os.environ.get("FXS_UI_PORT", "8787"))
MODEL = os.environ.get("FX_MODEL", "zai/glm-5.2")
HOME = Path.home()
STATE_ROOT = HOME / ".local" / "share" / "fx-sandbox" / "state"
ENV_FILE = HOME / ".config" / "fx" / "env"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
FXS_LINE = re.compile(r"^fxs:")

DANGEROUS = {
    "/", "/bin", "/boot", "/dev", "/etc", "/lib", "/lib64", "/proc", "/root",
    "/run", "/sbin", "/sys", "/usr", "/var", "/Users", "/System", "/Library",
    "/Applications", "/private", "/Volumes", "/opt/homebrew",
}

PROC_LOCK = threading.Lock()
CURRENT: dict = {"proc": None}

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "dist", "target", "__pycache__",
    ".fx", ".next", "vendor",
}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
SAFE_FX = {
    "models", "usage", "credits", "balance", "permissions", "status",
    "doctor", "sessions", "workspace", "help", "version",
}
DEMO_MODELS = [
    {"id": "zai/glm-5.2", "label": "GLM 5.2"},
    {"id": "anthropic/claude-sonnet-4.6", "label": "Sonnet 4.6"},
    {"id": "openai/gpt-5.2", "label": "GPT-5.2"},
]


def load_env_file() -> None:
    if not ENV_FILE.is_file():
        return
    for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, _, v = line.partition("=")
        v = v.strip().strip("'").strip('"')
        os.environ.setdefault(k.strip(), v)


load_env_file()


def which(name: str) -> str | None:
    return shutil.which(name)


def demo_mode() -> bool:
    if os.environ.get("FXS_UI_DEMO") == "1":
        return True
    if os.environ.get("FXS_UI_DEMO") == "0":
        return False
    return which("fxs") is None and which("docker") is None


def workspace_ok(path: str) -> str:
    p = Path(path).expanduser()
    if not p.exists() or not p.is_dir():
        raise ValueError("not a directory")
    resolved = str(p.resolve())
    if resolved in DANGEROUS:
        raise ValueError("refusing that path")
    home = str(HOME)
    if resolved == home:
        raise ValueError("refusing $HOME")
    for bad in ("/.ssh", "/.gnupg", "/.aws", "/Library"):
        if resolved == home + bad:
            raise ValueError("refusing a secret directory")
    return resolved


def default_workspace() -> str:
    raw = os.environ.get("FX_WORKSPACE") or os.getcwd()
    try:
        return workspace_ok(raw)
    except ValueError:
        return ""


def has_key() -> bool:
    return os.environ.get("AI_GATEWAY_API_KEY", "").startswith("vck_")


def docker_state() -> str:
    if not which("docker"):
        return "missing"
    try:
        r = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=4,
        )
        return "running" if r.returncode == 0 else "idle"
    except Exception:
        return "idle"


def session_title(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")[:12000]
        data = json.loads(raw)
    except Exception:
        return path.name[:24]
    for key in ("title", "summary", "prompt"):
        v = data.get(key) if isinstance(data, dict) else None
        if isinstance(v, str) and v.strip():
            return v.strip()[:72]
    if isinstance(data, dict):
        msgs = data.get("messages") or data.get("turns") or []
        if isinstance(msgs, list):
            for m in msgs:
                if isinstance(m, dict):
                    t = m.get("content") or m.get("text") or ""
                    if isinstance(t, str) and t.strip():
                        return t.strip()[:72]
    return path.name[:24]


def list_sessions(ws: str) -> list[dict]:
    import hashlib

    h = hashlib.sha256(ws.encode()).hexdigest()[:16]
    d = STATE_ROOT / h
    sessions = d / "sessions"
    if not sessions.is_dir():
        return []
    out = []
    for p in sorted(sessions.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.name.startswith("."):
            continue
        sid = p.stem if p.suffix else p.name
        out.append({
            "id": sid,
            "title": session_title(p) if p.is_file() else sid[:24],
            "mtime": int(p.stat().st_mtime),
        })
    return out[:40]


def fuzzy_score(query: str, text: str) -> int:
    q = (query or "").lower()
    t = (text or "").lower()
    if not q:
        return 1
    if q in t:
        return 2000 - t.find(q) - (len(t) - len(q))
    i = 0
    score = 0
    last = -2
    for j, ch in enumerate(t):
        if i < len(q) and ch == q[i]:
            score += 6 if j == last + 1 else 1
            if j == 0 or t[j - 1] in "/-._ ":
                score += 10
            last = j
            i += 1
    return score if i == len(q) else 0


def list_files(ws: str, query: str) -> list[str]:
    scored: list[tuple[int, str]] = []
    root = Path(ws)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        rel_dir = os.path.relpath(dirpath, root)
        for name in filenames:
            if name.startswith("."):
                continue
            rel = name if rel_dir == "." else f"{rel_dir}/{name}"
            rel = rel.replace("\\", "/")
            s = fuzzy_score(query, rel)
            if query and s <= 0:
                continue
            scored.append((s, rel))
            if len(scored) >= 400:
                break
        if len(scored) >= 400:
            break
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [p for _, p in scored[:40]]


def extract_json(text: str):
    text = (text or "").strip()
    if not text:
        return None
    for start in (text.rfind("{"), text.find("{")):
        if start < 0:
            continue
        try:
            return json.loads(text[start:])
        except json.JSONDecodeError:
            continue
    return None


def fxs_bin() -> str | None:
    return which("fxs") or which("run-fx")


def clean_perm(raw) -> str:
    p = str(raw or "yolo")
    return p if p in ("ask", "auto", "yolo") else "yolo"


def run_fxs(ws: str, fx_args: list[str], perm: str = "yolo", timeout: int = 90) -> subprocess.CompletedProcess:
    bin_ = fxs_bin()
    if not bin_:
        raise FileNotFoundError("fxs is not on PATH")
    cmd = [bin_, "run", "-w", ws]
    if perm != "yolo":
        cmd.append("--no-yolo")
    cmd += ["--perm", perm, "--"] + fx_args
    env = os.environ.copy()
    env["FX_MODEL"] = MODEL
    env["FX_PERMISSION_MODE"] = perm
    return subprocess.run(
        cmd, capture_output=True, timeout=timeout, cwd=ws, env=env, text=True,
    )


def parse_models(text: str) -> list[dict]:
    found: list[dict] = []
    data = extract_json(text)
    rows = None
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("models") or data.get("data")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, str) and "/" in row:
                found.append({"id": row, "label": row.split("/")[-1]})
            elif isinstance(row, dict):
                mid = str(row.get("id") or row.get("model") or "")
                if mid:
                    found.append({"id": mid, "label": str(row.get("name") or mid.split("/")[-1])})
    else:
        for line in text.splitlines():
            line = ANSI.sub("", line).strip()
            if not line:
                continue
            mid = line.split()[0].strip("-*·")
            if "/" in mid and len(mid) < 80:
                found.append({"id": mid, "label": mid.split("/")[-1]})
    seen = set()
    out = []
    for m in found:
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        out.append(m)
    return out


def kill_current() -> None:
    with PROC_LOCK:
        proc = CURRENT.get("proc")
        CURRENT["proc"] = None
    if not proc or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass


class Handler(BaseHTTPRequestHandler):
    server_version = "fxs-ui/1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("fxs-ui: " + (fmt % args) + "\n")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        u = urlparse(self.path)
        if u.path == "/api/status":
            qs = parse_qs(u.query)
            ws = (qs.get("workspace") or [default_workspace()])[0]
            self._json(200, {
                "demo": demo_mode(),
                "workspace": ws,
                "model": MODEL,
                "key": has_key(),
                "docker": docker_state(),
                "fxs": bool(which("fxs")),
            })
            return
        if u.path == "/api/sessions":
            qs = parse_qs(u.query)
            ws = (qs.get("workspace") or [""])[0]
            try:
                ws = workspace_ok(ws) if ws else ""
                self._json(200, {"sessions": list_sessions(ws) if ws else []})
            except ValueError as e:
                self._json(400, {"error": str(e), "sessions": []})
            return
        if u.path == "/api/models":
            self._models()
            return
        if u.path == "/api/files":
            qs = parse_qs(u.query)
            try:
                ws = workspace_ok((qs.get("workspace") or [default_workspace()])[0] or "")
            except ValueError as e:
                self._json(400, {"error": str(e), "files": []})
                return
            q = (qs.get("q") or [""])[0]
            self._json(200, {"files": list_files(ws, q)})
            return
        self._static(u.path)

    def _static(self, path: str) -> None:
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        if ".." in rel:
            self._send(404, b"not found", "text/plain")
            return
        fp = (HERE / rel).resolve()
        try:
            fp.relative_to(HERE)
        except ValueError:
            self._send(404, b"not found", "text/plain")
            return
        if not fp.is_file():
            self._send(404, b"not found", "text/plain")
            return
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
        }.get(fp.suffix, "application/octet-stream")
        self._send(200, fp.read_bytes(), ctype)

    def do_POST(self) -> None:
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            payload = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            payload = {}
        if u.path == "/api/stop":
            kill_current()
            self._json(200, {"ok": True})
            return
        if u.path == "/api/ask":
            self._ask(payload)
            return
        if u.path == "/api/fx":
            self._fx(payload)
            return
        if u.path == "/api/model":
            self._set_model(payload)
            return
        self._json(404, {"error": "not found"})

    def _models(self) -> None:
        if demo_mode():
            self._json(200, {"models": DEMO_MODELS, "current": MODEL})
            return
        ws = default_workspace() or os.getcwd()
        try:
            ws = workspace_ok(ws)
            r = run_fxs(ws, ["models", "--json"], timeout=60)
            models = parse_models((r.stdout or "") + "\n" + (r.stderr or ""))
            if not models:
                r2 = run_fxs(ws, ["models"], timeout=60)
                models = parse_models((r2.stdout or "") + "\n" + (r2.stderr or ""))
        except Exception:
            models = DEMO_MODELS
        if not models:
            models = DEMO_MODELS
        self._json(200, {"models": models, "current": MODEL})

    def _set_model(self, payload: dict) -> None:
        global MODEL
        mid = str(payload.get("model") or "").strip()
        if not mid or "/" not in mid or len(mid) > 80:
            self._json(400, {"error": "bad model"})
            return
        MODEL = mid
        os.environ["FX_MODEL"] = mid
        self._json(200, {"model": MODEL})

    def _fx(self, payload: dict) -> None:
        args = payload.get("args")
        if not isinstance(args, list) or not args:
            self._json(400, {"error": "args required"})
            return
        cmd0 = str(args[0])
        if cmd0 not in SAFE_FX:
            self._json(400, {"error": "command not allowed"})
            return
        extra = [str(a)[:200] for a in args[1:8]]
        fx_args = [cmd0] + extra
        if demo_mode():
            demo = {
                "status": f"demo · {MODEL}",
                "usage": "—",
                "credits": "—",
                "balance": "—",
                "doctor": "demo",
                "help": "/new  /resume  /models  /permissions",
                "models": "\n".join(m["id"] for m in DEMO_MODELS),
                "sessions": "—",
                "workspace": default_workspace() or "—",
                "version": "fxs-ui",
                "permissions": "yolo",
            }
            self._json(200, {"ok": True, "text": demo.get(cmd0, cmd0)})
            return
        try:
            ws = workspace_ok(str(payload.get("workspace") or default_workspace() or ""))
        except ValueError as e:
            self._json(400, {"error": str(e)})
            return
        perm = clean_perm(payload.get("perm"))
        try:
            r = run_fxs(ws, fx_args, perm=perm, timeout=180)
        except Exception as e:
            self._json(500, {"error": str(e)})
            return
        text = ANSI.sub("", (r.stdout or "") + (("\n" + r.stderr) if r.stderr else ""))
        self._json(200, {"ok": r.returncode == 0, "text": text.strip()[-4000:], "code": r.returncode})

    def _ask(self, payload: dict) -> None:
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            self._json(400, {"error": "empty"})
            return
        try:
            ws = workspace_ok(str(payload.get("workspace") or default_workspace() or ""))
        except ValueError as e:
            self._json(400, {"error": str(e)})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def emit(obj: dict) -> None:
            try:
                self.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode())
                self.wfile.flush()
            except BrokenPipeError:
                pass

        if demo_mode():
            self._demo(prompt, emit)
            return
        perm = clean_perm(payload.get("perm") or ("yolo" if payload.get("yolo", True) else "auto"))
        self._run_fxs(
            prompt,
            ws,
            str(payload.get("resume") or ""),
            perm,
            payload.get("images") if isinstance(payload.get("images"), list) else [],
            emit,
        )

    def _demo(self, prompt: str, emit) -> None:
        emit({"type": "tools", "tools": [{"name": "read"}]})
        emit({"type": "activity", "text": "read"})
        time.sleep(0.18)
        text = (
            f"**{prompt.strip().splitlines()[0][:72]}**\n\n"
            "`/` commands · `@` files · ⋯ for the rest"
        )
        i = 0
        while i < len(text):
            emit({"type": "token", "text": text[i:i + 16]})
            i += 16
            time.sleep(0.012)
        emit({"type": "activity", "text": ""})
        emit({"type": "done"})

    def _run_fxs(self, prompt: str, ws: str, resume: str, perm: str, images: list, emit) -> None:
        bin_ = fxs_bin()
        if not bin_:
            emit({"type": "error", "text": "fxs is not on PATH"})
            emit({"type": "done"})
            return
        perm = clean_perm(perm)
        cmd = [bin_, "run", "-w", ws]
        if perm != "yolo":
            cmd.append("--no-yolo")
        cmd += ["--perm", perm, "--", "ask", "--json"]
        if perm == "yolo":
            cmd.append("--yolo")
        if resume:
            cmd += ["--resume", resume]
        for img in images[:4]:
            p = str(img)
            if not p or ".." in p:
                continue
            ext = os.path.splitext(p)[1].lower()
            if ext not in IMAGE_EXT:
                continue
            abs_img = p if os.path.isabs(p) else os.path.join(ws, p)
            if os.path.isfile(abs_img):
                cmd += ["--image", abs_img]
        cmd += ["--", prompt]
        env = os.environ.copy()
        env["FX_MODEL"] = MODEL
        env["FX_PERMISSION_MODE"] = perm
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ws,
                env=env,
                start_new_session=True,
            )
        except OSError as e:
            emit({"type": "error", "text": str(e)})
            emit({"type": "done"})
            return
        with PROC_LOCK:
            CURRENT["proc"] = proc

        def pump_err() -> None:
            assert proc.stderr is not None
            for raw in iter(proc.stderr.readline, b""):
                line = ANSI.sub("", raw.decode("utf-8", errors="replace")).rstrip()
                if not line or FXS_LINE.match(line):
                    continue
                emit({"type": "activity", "text": line[-120:]})

        t = threading.Thread(target=pump_err, daemon=True)
        t.start()
        chunks: list[str] = []
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read(256)
            if not chunk:
                break
            piece = ANSI.sub("", chunk.decode("utf-8", errors="replace"))
            if piece:
                chunks.append(piece)
        proc.wait()
        t.join(timeout=1)
        with PROC_LOCK:
            if CURRENT.get("proc") is proc:
                CURRENT["proc"] = None
        raw_out = "".join(chunks)
        data = extract_json(raw_out)
        if isinstance(data, dict):
            tools = data.get("tool_calls") or []
            if tools:
                names = []
                for tcall in tools:
                    if isinstance(tcall, dict):
                        names.append({"name": str(tcall.get("name") or "tool")})
                    else:
                        names.append({"name": str(tcall)})
                emit({"type": "tools", "tools": names})
            if data.get("session_id"):
                emit({"type": "session", "id": data["session_id"]})
            if data.get("model"):
                emit({"type": "model", "id": data["model"]})
            out = data.get("output") or data.get("error") or ""
            if out:
                emit({"type": "token", "text": str(out)})
            if data.get("error") and not data.get("output"):
                emit({"type": "error", "text": str(data["error"])})
        elif raw_out.strip():
            kept = []
            for line in raw_out.splitlines(True):
                if FXS_LINE.match(line):
                    continue
                kept.append(line)
            emit({"type": "token", "text": "".join(kept)})
        if proc.returncode not in (0, None):
            if proc.returncode and proc.returncode < 0:
                emit({"type": "activity", "text": "stopped"})
            else:
                emit({"type": "error", "text": f"exit {proc.returncode}"})
        emit({"type": "done"})


def pick_host_port() -> tuple[str, int]:
    host, port = HOST, PORT
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--host", "-H") and i + 1 < len(argv):
            host = argv[i + 1]; i += 2; continue
        if a in ("--port", "-p") and i + 1 < len(argv):
            port = int(argv[i + 1]); i += 2; continue
        if a == "--demo":
            os.environ["FXS_UI_DEMO"] = "1"; i += 1; continue
        if a == "--bind-all":
            host = "0.0.0.0"; i += 1; continue
        i += 1
    return host, port


def main() -> None:
    host, port = pick_host_port()
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    sys.stderr.write(f"fxs-ui: {url}  demo={demo_mode()}\n")
    if host in ("127.0.0.1", "localhost") and os.environ.get("FXS_UI_OPEN") != "0":
        opener = "open" if sys.platform == "darwin" else ("xdg-open" if which("xdg-open") else None)
        if opener:
            threading.Timer(
                0.4,
                lambda: subprocess.Popen(
                    [opener, url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ),
            ).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        kill_current()


if __name__ == "__main__":
    main()
