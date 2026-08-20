#!/usr/bin/env python3
"""fxs ui — tiny local frontend. No npm. Python 3.9+ stdlib only."""
from __future__ import annotations

import json
import os
import shutil
import socket
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

DANGEROUS = {
    "/", "/bin", "/boot", "/dev", "/etc", "/lib", "/lib64", "/proc", "/root",
    "/run", "/sbin", "/sys", "/usr", "/var", "/Users", "/System", "/Library",
    "/Applications", "/private", "/Volumes", "/opt/homebrew",
}


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
    for bad in (home + "/.ssh", home + "/.gnupg", home + "/.aws", home + "/Library"):
        if resolved == bad:
            raise ValueError("refusing a secret directory")
    return resolved


def has_key() -> bool:
    k = os.environ.get("AI_GATEWAY_API_KEY", "")
    return k.startswith("vck_")


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


def list_sessions(ws: str) -> list[dict]:
    import hashlib

    h = hashlib.sha256(ws.encode()).hexdigest()[:16]
    d = STATE_ROOT / h
    if not d.is_dir():
        return []
    out = []
    sessions = d / "sessions"
    if sessions.is_dir():
        for p in sorted(sessions.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            out.append({"id": p.name, "title": p.name[:24], "mtime": int(p.stat().st_mtime)})
    origin = d / "origin"
    return out[:40]


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
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        raw = json.dumps(obj).encode()
        self._send(code, raw, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        u = urlparse(self.path)
        if u.path == "/api/status":
            qs = parse_qs(u.query)
            ws = (qs.get("workspace") or [os.environ.get("FX_WORKSPACE", "")])[0]
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
        self._static(u.path)

    def _static(self, path: str) -> None:
        rel = path if path != "/" else "/index.html"
        rel = rel.lstrip("/")
        if ".." in rel or rel.startswith("/"):
            self._send(404, b"not found", "text/plain")
            return
        fp = (HERE / rel).resolve()
        if HERE not in fp.parents and fp != HERE:
            # file in HERE
            pass
        if not str(fp).startswith(str(HERE)) or not fp.is_file():
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
            self._json(400, {"error": "bad json"})
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
            ws = workspace_ok(str(payload.get("workspace") or ""))
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
        self._run_fxs(prompt, ws, payload.get("resume"), emit)

    def _demo(self, prompt: str, emit) -> None:
        text = (
            "Demo mode — Docker/fx is not on this machine, so nothing was run.\n\n"
            "On yours:\n\n"
            "```\ncd /path/to/project\nfxs ui\n```\n\n"
            "That talks to the same sandbox as `fxs` (one folder, yolo, GLM 5.2).\n\n"
            f"You asked: {prompt}"
        )
        for ch in text.split(" "):
            emit({"type": "token", "text": ch + " "})
            time.sleep(0.012)
        emit({"type": "done"})

    def _run_fxs(self, prompt: str, ws: str, resume, emit) -> None:
        fxs = which("fxs") or which("run-fx")
        if not fxs:
            emit({"type": "error", "text": "fxs is not on PATH"})
            emit({"type": "done"})
            return
        cmd = [fxs, "run", "-w", ws, "--", "ask", "--yolo", "--no-color"]
        if resume:
            cmd += ["--resume", str(resume)]
        cmd += ["--", prompt]
        emit({"type": "log", "text": " ".join(cmd[:6]) + " …"})
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=ws,
                env=os.environ.copy(),
            )
        except OSError as e:
            emit({"type": "error", "text": str(e)})
            emit({"type": "done"})
            return
        assert proc.stdout is not None
        buf = ""
        while True:
            chunk = proc.stdout.read(64)
            if not chunk:
                break
            try:
                piece = chunk.decode("utf-8", errors="replace")
            except Exception:
                piece = ""
            buf += piece
            emit({"type": "token", "text": piece})
        proc.wait()
        if proc.returncode not in (0, None):
            emit({"type": "error", "text": f"exit {proc.returncode}"})
        emit({"type": "done"})


def pick_host_port() -> tuple[str, int]:
    host = HOST
    port = PORT
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
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    sys.stderr.write(f"fxs-ui: {url}  demo={demo_mode()}\n")
    if host in ("127.0.0.1", "localhost") and os.environ.get("FXS_UI_OPEN") != "0":
        opener = "open" if sys.platform == "darwin" else ("xdg-open" if which("xdg-open") else None)
        if opener:
            threading.Timer(0.4, lambda: subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
