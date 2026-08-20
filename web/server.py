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


def list_models() -> list[dict]:
    fallback = [
        {"id": "zai/glm-5.2"},
        {"id": "zai/glm-5.2-fast", "note": "not in the free promo"},
    ]
    fx = which("fx")
    if not fx or demo_mode():
        return fallback
    try:
        r = subprocess.run(
            [fx, "models", "--json"],
            capture_output=True,
            timeout=12,
            text=True,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return fallback
        data = json.loads(r.stdout)
    except Exception:
        return fallback
    rows = data if isinstance(data, list) else data.get("models") or data.get("data") or []
    out = []
    for m in rows:
        if isinstance(m, str):
            out.append({"id": m})
        elif isinstance(m, dict):
            mid = m.get("id") or m.get("model") or m.get("name")
            if mid:
                out.append({"id": mid})
    return out or fallback


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
            self._json(200, {"models": list_models()})
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
        self._json(404, {"error": "not found"})

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
        self._run_fxs(
            prompt,
            ws,
            str(payload.get("resume") or ""),
            bool(payload.get("yolo", True)),
            str(payload.get("model") or MODEL),
            emit,
        )

    def _demo(self, prompt: str, emit) -> None:
        emit({"type": "tools", "tools": [{"name": "read"}, {"name": "search"}]})
        emit({"type": "activity", "text": "read"})
        time.sleep(0.25)
        text = (
            f"**{prompt.strip()[:48]}**\n\n"
            "Demo — this machine has no Docker, so nothing ran.\n\n"
            "On yours:\n\n"
            "```\ncd /path/to/project\nfxs ui\n```\n\n"
            "Same sandbox as `fxs`. `/` opens commands. Esc stops."
        )
        for word in text.split(" "):
            emit({"type": "token", "text": word + " "})
            time.sleep(0.016)
        emit({"type": "activity", "text": ""})
        emit({"type": "done"})

    def _run_fxs(self, prompt: str, ws: str, resume: str, yolo: bool, model: str, emit) -> None:
        fxs = which("fxs") or which("run-fx")
        if not fxs:
            emit({"type": "error", "text": "fxs is not on PATH"})
            emit({"type": "done"})
            return
        cmd = [fxs, "run", "-w", ws]
        if not yolo:
            cmd.append("--no-yolo")
        cmd += ["--", "ask"]
        if yolo:
            cmd.append("--yolo")
        if resume:
            cmd += ["--resume", resume]
        cmd += ["--", prompt]
        env = os.environ.copy()
        env["FX_MODEL"] = model or MODEL
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
            last = ""
            for raw in iter(proc.stderr.readline, b""):
                line = ANSI.sub("", raw.decode("utf-8", errors="replace")).rstrip()
                if not line or FXS_LINE.match(line):
                    continue
                last = line[-120:]
                emit({"type": "activity", "text": last})

        t = threading.Thread(target=pump_err, daemon=True)
        t.start()
        assert proc.stdout is not None
        collected = []
        while True:
            chunk = proc.stdout.read(80)
            if not chunk:
                break
            piece = ANSI.sub("", chunk.decode("utf-8", errors="replace"))
            if not piece:
                continue
            kept = []
            for line in piece.splitlines(True):
                if FXS_LINE.match(line):
                    continue
                kept.append(line)
            if kept:
                text = "".join(kept)
                collected.append(text)
                emit({"type": "token", "text": text})
        proc.wait()
        t.join(timeout=1)
        with PROC_LOCK:
            if CURRENT.get("proc") is proc:
                CURRENT["proc"] = None
        blob = "".join(collected).strip()
        if blob.startswith("{"):
            try:
                data = json.loads(blob)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict):
                sid = data.get("session_id")
                if sid:
                    emit({"type": "session", "id": sid})
                tools = data.get("tool_calls") or []
                if tools:
                    emit({"type": "tools", "tools": tools})
        if proc.returncode not in (0, None):
            if proc.returncode and proc.returncode < 0:
                emit({"type": "activity", "text": "stopped"})
            else:
                emit({"type": "error", "text": f"exit {proc.returncode}"})
        emit({"type": "done"})


class Server(ThreadingHTTPServer):
    allow_reuse_address = True


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
        i += 1
    return host, port


def main() -> None:
    host, port = pick_host_port()
    httpd = Server((host, port), Handler)
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
