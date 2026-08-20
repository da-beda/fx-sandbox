#!/usr/bin/env python3
"""fxs ui — local frontend. Python 3.9+ stdlib only."""
from __future__ import annotations

import json
import os
import re
import hashlib
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
sys.path.insert(0, str(HERE))
import gateway
HOST = os.environ.get("FXS_UI_HOST", "127.0.0.1")
PORT = int(os.environ.get("FXS_UI_PORT", "8787"))
MODEL = os.environ.get("FX_MODEL", "zai/glm-5.2")
HOME = Path.home()
STATE_ROOT = HOME / ".local" / "share" / "fx-sandbox" / "state"
ENV_FILE = HOME / ".config" / "fx" / "env"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
FXS_LINE = re.compile(r"^fxs:")
NOTICE_ATT = re.compile(r"attempt\s+(\d+)\s*/\s*(\d+)", re.I)
NOTICE_WAIT = re.compile(r"in\s+(\d+)\s*s", re.I)
BRACKET_TOOL = re.compile(r"^\[([a-z0-9_]+)\]\s*(.*)$", re.I)
SID_OK = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
TOOL_KIND = {
    "read": ("read", "Read"),
    "write": ("write", "Wrote"),
    "edit": ("write", "Edited"),
    "open_file": ("read", "Read"),
    "file_info": ("read", "Read"),
    "write_file": ("write", "Wrote"),
    "edit_file": ("write", "Edited"),
    "delete_file": ("delete", "Deleted"),
    "rename_file": ("write", "Renamed"),
    "copy_file": ("write", "Copied"),
    "create_folder": ("list", "Created"),
    "list_files": ("list", "Listed"),
    "glob_files": ("search", "Found"),
    "grep_files": ("search", "Searched"),
    "semantic_search": ("search", "Searched"),
    "run_command": ("run", "Ran"),
    "bash": ("run", "Ran"),
    "shell": ("run", "Ran"),
    "web_search": ("web", "Searched"),
    "web_fetch": ("web", "Fetched"),
    "fetch": ("web", "Fetched"),
    "search": ("search", "Searched"),
    "subagent": ("agent", "Agent"),
    "vision": ("image", "Looked"),
    "ask_user_question": ("status", "Asked"),
    "install_skill": ("skill", "Skill"),
}

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
MAX_TREE = 800
MAX_TEXT = 1_000_000
MAX_IMAGE = 4_000_000
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
SAFE_FX = {
    "models", "usage", "credits", "balance", "permissions", "status",
    "doctor", "sessions", "workspace", "help", "version",
}
CATALOG_MODELS = [
    {"id": "zai/glm-5.2", "label": "GLM 5.2"},
    {"id": "anthropic/claude-sonnet-4.6", "label": "Sonnet 4.6"},
    {"id": "openai/gpt-5.2", "label": "GPT-5.2"},
]
PREFERRED_MODELS = [m["id"] for m in CATALOG_MODELS]
HIDDEN_UNLESS_CURRENT = {"zai/glm-5.2-fast"}
MAX_MODELS = 48


def load_env_file() -> None:
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:]
            k, _, v = line.partition("=")
            v = v.strip().strip("'").strip('"')
            os.environ.setdefault(k.strip(), v)
    if not os.environ.get("AI_GATEWAY_API_KEY", "").startswith("vck_"):
        key_file = HOME / ".fx" / "api-key"
        if key_file.is_file():
            try:
                k = key_file.read_text(encoding="utf-8").strip()
                if k.startswith("vck_"):
                    os.environ.setdefault("AI_GATEWAY_API_KEY", k)
            except OSError:
                pass


load_env_file()
MODEL = os.environ.get("FX_MODEL", MODEL)
if MODEL == "zai/glm-5.2-fast":
    MODEL = "zai/glm-5.2"
    os.environ["FX_MODEL"] = MODEL


def boot_gateway() -> None:
    if local_mode():
        return
    if not gateway.configured_upstream():
        return
    try:
        gateway.ensure_gateway()
    except Exception as e:
        sys.stderr.write(f"fxs-ui: gateway: {e}\n")


def shorten(s: str, n: int = 72) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def parse_step(line: str) -> dict | None:
    line = ANSI.sub("", line or "").strip()
    if not line or FXS_LINE.match(line):
        return None
    if line.startswith("[notice]"):
        body = re.sub(r"^[⚠✓]\s*", "", line[8:].strip())
        low = body.lower()
        if "paused after" in low:
            return {
                "type": "step", "id": "retry", "kind": "retry",
                "label": "Model unavailable", "detail": "gave up", "status": "warn",
            }
        if "recovered" in low or "succeeded on attempt" in low:
            return {
                "type": "step", "id": "retry", "kind": "ok",
                "label": "Model recovered", "status": "ok",
            }
        if "retrying" in low or "unavailable" in low or "503" in body:
            att = NOTICE_ATT.search(body)
            wait = NOTICE_WAIT.search(body)
            detail = f"{att.group(1)}/{att.group(2)}" if att else ""
            if wait:
                detail = (detail + " · " if detail else "") + wait.group(1) + "s"
            return {
                "type": "step", "id": "retry", "kind": "retry",
                "label": "Waiting on the model", "detail": detail, "status": "running",
            }
        head = body.split("·")[0].strip()
        return {
            "type": "step", "kind": "status",
            "label": shorten(head, 64), "status": "running",
        }
    m = BRACKET_TOOL.match(line)
    if m:
        raw = m.group(1).lower()
        rest = m.group(2).strip()
        kind, verb = TOOL_KIND.get(raw, ("tool", raw.replace("_", " ")))
        path = rest if rest and (("/" in rest) or ("." in rest)) else ""
        label = f"{verb} {shorten(Path(rest).name if path else rest, 48)}".strip() if rest else verb
        return {
            "type": "step", "kind": kind, "label": label,
            "detail": rest, "path": path, "status": "running",
        }
    if len(line) > 180:
        line = line[-120:]
    return {"type": "step", "kind": "status", "label": shorten(line, 64), "status": "running"}


def tool_step(tcall) -> dict:
    if not isinstance(tcall, dict):
        name = str(tcall).strip()
        tcall = {"name": name}
    name = str(tcall.get("name") or "tool").strip()
    parts = name.split(None, 1)
    key = parts[0].lower().replace("-", "_")
    rest = parts[1] if len(parts) > 1 else ""
    kind, verb = TOOL_KIND.get(key, ("tool", key.replace("_", " ")))
    path = str(tcall.get("path") or tcall.get("file") or tcall.get("target") or "")
    cmd = str(tcall.get("command") or tcall.get("cmd") or "")
    query = str(tcall.get("query") or tcall.get("pattern") or "")
    extra = path or cmd or query or rest
    if extra and not path and ("/" in extra or "." in extra) and " " not in extra:
        path = extra
    label = verb
    if extra:
        shown = Path(extra).name if path else extra
        label = f"{verb} {shorten(shown, 42)}".strip()
    st = str(tcall.get("status") or "ok").lower()
    if st in ("success", "ok", "completed", "done"):
        st = "ok"
    elif st in ("error", "failed", "fail"):
        st = "warn"
    else:
        st = "running" if st in ("running", "in_progress", "pending") else "ok"
    return {
        "type": "step", "kind": kind, "label": label,
        "detail": extra, "path": path, "status": st,
    }


def which(name: str) -> str | None:
    return shutil.which(name)


def local_mode() -> bool:
    if os.environ.get("FXS_UI_LOCAL") == "1":
        return True
    if os.environ.get("FXS_UI_LOCAL") == "0":
        return False
    return not can_live()


def sandbox_ok() -> bool:
    if os.geteuid() == 0:
        return False
    if not (which("fxs") or which("run-fx")):
        return False
    return docker_state() == "running"


def can_live() -> bool:
    if which("fx"):
        return True
    return sandbox_ok()


def backend_name() -> str:
    if local_mode():
        return "offline"
    if sandbox_ok():
        return "sandbox"
    if which("fx"):
        return "native"
    return "offline"


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
    return bool(gateway.current_provider().get("key"))


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


def session_root(ws: str) -> Path:
    h = hashlib.sha256(ws.encode()).hexdigest()[:16]
    return STATE_ROOT / h / "sessions"


def session_path(ws: str, sid: str) -> Path | None:
    if not SID_OK.match(sid or ""):
        return None
    root = session_root(ws)
    if not root.is_dir():
        return None
    try:
        root_r = root.resolve()
    except OSError:
        return None
    for p in (root / f"{sid}.json", root / sid):
        try:
            if p.is_file() and p.resolve().parent == root_r:
                return p
        except OSError:
            continue
    return None


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
    sessions = session_root(ws)
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


def _message_text(m: dict) -> str:
    content = m.get("content") or m.get("text") or ""
    if isinstance(content, list):
        parts = []
        for x in content:
            if isinstance(x, dict):
                parts.append(str(x.get("text") or ""))
            elif isinstance(x, str):
                parts.append(x)
        content = "".join(parts)
    if not isinstance(content, str):
        content = str(content)
    return content.strip()


def read_session(ws: str, sid: str) -> dict | None:
    p = session_path(ws, sid)
    if not p:
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace")[:200_000])
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    msgs = []
    raw = data.get("messages") or data.get("turns") or []
    if isinstance(raw, list):
        for m in raw[:80]:
            if not isinstance(m, dict):
                continue
            role = str(m.get("role") or "assistant")
            if role not in ("user", "assistant", "system", "tool"):
                role = "assistant"
            text = _message_text(m)
            if text:
                msgs.append({"role": role, "content": text[:8000]})
    return {
        "id": sid,
        "title": session_title(p),
        "mtime": int(p.stat().st_mtime),
        "messages": msgs,
    }


def delete_session(ws: str, sid: str) -> bool:
    p = session_path(ws, sid)
    if not p:
        return False
    try:
        p.unlink()
    except OSError:
        return False
    return True


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


def resolve_in_ws(ws: str, rel: str) -> Path:
    rel = (rel or "").replace("\\", "/").strip()
    if rel.startswith("/"):
        rel = rel.lstrip("/")
    if not rel or rel in (".", "..") or ".." in Path(rel).parts:
        raise ValueError("bad path")
    root = Path(ws).resolve()
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise ValueError("outside workspace")
    return target


def list_tree(ws: str) -> dict:
    root = Path(ws)
    count = 0
    truncated = False

    def walk(dirpath: Path, rel: str) -> list:
        nonlocal count, truncated
        items: list[dict] = []
        try:
            entries = sorted(
                dirpath.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except OSError:
            return items
        for p in entries:
            if truncated:
                break
            name = p.name
            if name.startswith(".") or name in SKIP_DIRS:
                continue
            count += 1
            if count > MAX_TREE:
                truncated = True
                break
            child = name if not rel else f"{rel}/{name}"
            if p.is_dir() and not p.is_symlink():
                items.append({
                    "name": name,
                    "path": child,
                    "type": "dir",
                    "children": walk(p, child),
                })
            elif p.is_file():
                try:
                    size = int(p.stat().st_size)
                except OSError:
                    size = 0
                items.append({
                    "name": name,
                    "path": child,
                    "type": "file",
                    "size": size,
                })
        return items

    return {"tree": walk(root, ""), "truncated": truncated, "count": count}


def read_workspace_file(ws: str, rel: str) -> dict:
    p = resolve_in_ws(ws, rel)
    if not p.is_file():
        raise ValueError("not a file")
    ext = p.suffix.lower()
    try:
        size = int(p.stat().st_size)
    except OSError:
        size = 0
    if ext in IMAGE_EXT:
        if size > MAX_IMAGE:
            return {"kind": "binary", "path": rel, "size": size, "name": p.name}
        import base64
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }[ext]
        src = "data:" + mime + ";base64," + base64.b64encode(p.read_bytes()).decode("ascii")
        return {"kind": "image", "path": rel, "size": size, "name": p.name, "src": src}
    if size > MAX_TEXT:
        return {"kind": "binary", "path": rel, "size": size, "name": p.name}
    raw = p.read_bytes()
    if b"\0" in raw[:8192]:
        return {"kind": "binary", "path": rel, "size": size, "name": p.name}
    return {
        "kind": "text",
        "path": rel,
        "size": size,
        "name": p.name,
        "text": raw.decode("utf-8", errors="replace"),
    }


def write_workspace_file(ws: str, rel: str, text: str) -> dict:
    p = resolve_in_ws(ws, rel)
    if p.exists() and not p.is_file():
        raise ValueError("not a file")
    p.parent.mkdir(parents=True, exist_ok=True)
    data = text if isinstance(text, str) else ""
    p.write_text(data, encoding="utf-8")
    return {"ok": True, "path": rel, "size": int(p.stat().st_size), "name": p.name}


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


def fx_bin() -> str | None:
    return which("fx")


def clean_perm(raw) -> str:
    p = str(raw or "yolo")
    return p if p in ("ask", "auto", "yolo") else "yolo"


def agent_argv(ws: str, fx_args: list[str], perm: str) -> list[str]:
    perm = clean_perm(perm)
    args = list(fx_args)
    if args and args[0] == "fx":
        args = args[1:]
    if sandbox_ok():
        bin_ = fxs_bin()
        if not bin_:
            raise FileNotFoundError("fxs is not on PATH")
        cmd = [bin_, "run", "-w", ws]
        if perm != "yolo":
            cmd.append("--no-yolo")
        cmd += ["--"] + args
        return cmd
    fx = fx_bin()
    if not fx:
        raise FileNotFoundError("fx is not on PATH")
    return [fx] + args


def run_fxs(ws: str, fx_args: list[str], perm: str = "yolo", timeout: int = 90) -> subprocess.CompletedProcess:
    cmd = agent_argv(ws, fx_args, perm)
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
        rows = data.get("models") or data.get("data") or data.get("ids")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, str) and row.strip():
                mid = row.strip()
                found.append({"id": mid, "label": mid.split("/")[-1]})
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
            if not mid or len(mid) > 120:
                continue
            if mid.lower() in ("default", "models", "id", "name", "model"):
                continue
            if "/" in mid or re.match(r"^[A-Za-z0-9_.:-]+$", mid):
                found.append({"id": mid, "label": mid.split("/")[-1]})
    seen = set()
    out = []
    for m in found:
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        out.append(m)
    return out


def rank_models(found: list[dict], current: str) -> list[dict]:
    by_id: dict[str, dict] = {}
    for m in found:
        mid = m["id"]
        if mid in HIDDEN_UNLESS_CURRENT and mid != current:
            continue
        by_id[mid] = m
    out: list[dict] = []
    for pid in PREFERRED_MODELS:
        if pid in by_id:
            m = by_id.pop(pid)
            label = next((c["label"] for c in CATALOG_MODELS if c["id"] == pid), m.get("label") or pid.split("/")[-1])
            out.append({"id": pid, "label": label})
        elif pid == current:
            label = next((c["label"] for c in CATALOG_MODELS if c["id"] == pid), pid.split("/")[-1])
            out.append({"id": pid, "label": label})
    for m in found:
        if m["id"] in by_id:
            out.append(by_id.pop(m["id"]))
    if current and current not in {m["id"] for m in out}:
        out.insert(0, {"id": current, "label": current.split("/")[-1]})
    return out[:MAX_MODELS]


def recover_error(stdout: str, stderr: str) -> str:
    blob = ((stdout or "") + "\n" + (stderr or "")).strip()
    data = extract_json(blob)
    if isinstance(data, dict):
        for key in ("error", "message", "errorMessage", "detail"):
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
            if isinstance(v, dict):
                msg = v.get("message") or v.get("code") or v.get("type")
                if msg:
                    return str(msg)
        code = data.get("code") or data.get("error_code") or data.get("type")
        if code:
            return str(code)
    lowered = blob.lower()
    if "provider_unavailable" in lowered or "http 503" in lowered or " 503 " in lowered:
        return "GLM 5.2 is unavailable (provider 503). Try again in a moment."
    if "customer_verification_required" in lowered:
        return "AI Gateway needs a card on file for this route."
    if "rate_limit" in lowered:
        return "Rate limited. Try again shortly."
    lines = [ANSI.sub("", ln).strip() for ln in blob.splitlines()]
    lines = [ln for ln in lines if ln and not FXS_LINE.match(ln)]
    if lines:
        return lines[-1][:400]
    return "fx failed"


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

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self) -> None:
        u = urlparse(self.path)
        if u.path == "/api/status":
            qs = parse_qs(u.query)
            ws = (qs.get("workspace") or [default_workspace()])[0]
            self._json(200, {
                "live": not local_mode(),
                "workspace": ws,
                "default_workspace": default_workspace(),
                "model": MODEL,
                "key": has_key(),
                "docker": docker_state(),
                "fxs": bool(which("fxs") or which("run-fx")),
                "fx": bool(which("fx")),
                "backend": backend_name(),
                "provider": gateway.current_provider(),
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
        if u.path == "/api/session":
            qs = parse_qs(u.query)
            try:
                ws = workspace_ok((qs.get("workspace") or [""])[0] or "")
            except ValueError as e:
                self._json(400, {"error": str(e)})
                return
            sid = (qs.get("id") or [""])[0]
            data = read_session(ws, sid)
            if not data:
                self._json(404, {"error": "not found"})
                return
            self._json(200, data)
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
        if u.path == "/api/tree":
            qs = parse_qs(u.query)
            try:
                ws = workspace_ok((qs.get("workspace") or [default_workspace()])[0] or "")
            except ValueError as e:
                self._json(400, {"error": str(e), "tree": []})
                return
            self._json(200, list_tree(ws))
            return
        if u.path == "/api/file":
            qs = parse_qs(u.query)
            try:
                ws = workspace_ok((qs.get("workspace") or [default_workspace()])[0] or "")
                rel = (qs.get("path") or [""])[0]
                if (qs.get("raw") or ["0"])[0] in ("1", "true", "yes"):
                    p = resolve_in_ws(ws, rel)
                    if not p.is_file():
                        self._send(404, b"not found", "text/plain")
                        return
                    ext = p.suffix.lower()
                    if ext not in IMAGE_EXT:
                        self._send(404, b"not found", "text/plain")
                        return
                    size = int(p.stat().st_size)
                    if size > MAX_IMAGE:
                        self._send(413, b"too large", "text/plain")
                        return
                    mime = {
                        ".png": "image/png",
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".webp": "image/webp",
                        ".gif": "image/gif",
                    }[ext]
                    self._send(200, p.read_bytes(), mime)
                    return
                self._json(200, read_workspace_file(ws, rel))
            except (ValueError, OSError) as e:
                self._json(400, {"error": str(e)})
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
        if u.path == "/api/provider":
            self._set_provider(payload)
            return
        if u.path == "/api/key":
            self._set_key(payload)
            return
        if u.path == "/api/file":
            try:
                ws = workspace_ok(str(payload.get("workspace") or default_workspace() or ""))
                rel = str(payload.get("path") or "")
                self._json(200, write_workspace_file(ws, rel, str(payload.get("text") or "")))
            except (ValueError, OSError) as e:
                self._json(400, {"error": str(e)})
            return
        self._json(404, {"error": "not found"})

    def do_DELETE(self) -> None:
        u = urlparse(self.path)
        if u.path == "/api/session":
            qs = parse_qs(u.query)
            try:
                ws = workspace_ok((qs.get("workspace") or [""])[0] or "")
            except ValueError as e:
                self._json(400, {"error": str(e)})
                return
            sid = (qs.get("id") or [""])[0]
            if delete_session(ws, sid):
                self._json(200, {"ok": True})
            else:
                self._json(404, {"error": "not found"})
            return
        self._json(404, {"error": "not found"})

    def _models(self) -> None:
        if local_mode():
            prov = gateway.current_provider()
            if not prov.get("vercel"):
                mid = MODEL or prov.get("model") or ""
                self._json(200, {
                    "models": [{"id": mid, "label": mid.split("/")[-1]}] if mid else [],
                    "current": MODEL,
                })
                return
            self._json(200, {"models": CATALOG_MODELS, "current": MODEL})
            return
        ws = default_workspace() or os.getcwd()
        models: list[dict] = []
        try:
            if gateway.configured_upstream():
                gateway.ensure_gateway()
                ids = gateway.fetch_catalog()
                models = [{"id": i, "label": i.split("/")[-1]} for i in ids]
            if not models:
                ws = workspace_ok(ws)
                r = run_fxs(ws, ["models", "--json"], timeout=60)
                models = parse_models((r.stdout or "") + "\n" + (r.stderr or ""))
                if not models:
                    r2 = run_fxs(ws, ["models"], timeout=60)
                    models = parse_models((r2.stdout or "") + "\n" + (r2.stderr or ""))
        except Exception:
            models = []
        vercel = gateway.current_provider().get("vercel", True)
        fallback = list(CATALOG_MODELS) if vercel else (
            [{"id": MODEL, "label": MODEL.split("/")[-1]}] if MODEL else []
        )
        models = rank_models(models or fallback, MODEL)
        if not models:
            models = fallback
        self._json(200, {"models": models, "current": MODEL})

    def _set_model(self, payload: dict) -> None:
        global MODEL
        mid = str(payload.get("model") or "").strip()
        if not mid or len(mid) > 120 or any(c in mid for c in " \n\t"):
            self._json(400, {"error": "bad model"})
            return
        MODEL = mid
        os.environ["FX_MODEL"] = mid
        try:
            gateway.upsert_env({"FX_MODEL": mid})
        except OSError:
            pass
        self._json(200, {"model": MODEL})

    def _set_provider(self, payload: dict) -> None:
        name = str(payload.get("provider") or payload.get("url") or "").strip()
        model = str(payload.get("model") or "").strip()
        api = str(payload.get("api") or "").strip()
        if not name:
            if api:
                cur = gateway.current_provider()
                name = cur.get("url") or cur.get("id") or "vercel"
            else:
                self._json(200, gateway.current_provider())
                return
        try:
            info = gateway.apply_provider(name, model, api=api)
        except ValueError as e:
            self._json(400, {"error": str(e)})
            return
        global MODEL
        if model:
            MODEL = model
        elif info.get("model"):
            MODEL = info["model"]
        if MODEL:
            os.environ["FX_MODEL"] = MODEL
        self._json(200, info)

    def _set_key(self, payload: dict) -> None:
        key = str(payload.get("key") or "").strip()
        try:
            info = gateway.store_api_key(key)
        except ValueError as e:
            self._json(400, {"error": str(e)})
            return
        self._json(200, {"ok": True, "key": bool(info.get("key")), "provider": info.get("id")})

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
        if local_mode():
            catalog = {
                "status": MODEL,
                "usage": "—",
                "credits": "—",
                "balance": "—",
                "doctor": "ok",
                "help": "/new  /settings  /models  /permissions",
                "models": "\n".join(m["id"] for m in CATALOG_MODELS),
                "sessions": "—",
                "workspace": default_workspace() or "—",
                "version": "fxs",
                "permissions": "yolo",
            }
            self._json(200, {"ok": True, "text": catalog.get(cmd0, cmd0)})
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

        emit_lock = threading.Lock()

        def emit(obj: dict) -> None:
            with emit_lock:
                try:
                    self.wfile.write(("data: " + json.dumps(obj) + "\n\n").encode())
                    self.wfile.flush()
                except BrokenPipeError:
                    pass

        if local_mode():
            self._local_reply(prompt, ws, emit)
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

    def _local_reply(self, prompt: str, ws: str, emit) -> None:
        files = list_files(ws, "")[:12]
        if files:
            emit(tool_step({"name": "read_file", "path": files[0], "status": "ok"}))
            time.sleep(0.08)
        readme = Path(ws) / "README.md"
        excerpt = ""
        if readme.is_file():
            try:
                excerpt = readme.read_text(encoding="utf-8", errors="replace").strip()
                excerpt = "\n".join(excerpt.splitlines()[:12])
            except OSError:
                excerpt = ""
        if excerpt:
            text = excerpt
        elif files:
            text = "\n".join(files[:10])
        else:
            text = prompt.strip().splitlines()[0][:120]
        i = 0
        while i < len(text):
            emit({"type": "token", "text": text[i:i + 24]})
            i += 24
            time.sleep(0.008)
        emit({"type": "done"})

    def _run_fxs(self, prompt: str, ws: str, resume: str, perm: str, images: list, emit) -> None:
        perm = clean_perm(perm)
        base = ["ask", "--json"]
        if perm == "yolo":
            base.append("--yolo")
        resume_flag: list[str] = []
        if resume and resume != "last":
            resume_flag = ["--resume", str(resume)[:80]]
        elif resume == "last" and sandbox_ok() and list_sessions(ws):
            resume_flag = ["--resume", "last"]
        img_flags: list[str] = []
        for img in images[:4]:
            p = str(img)
            if not p or ".." in p:
                continue
            ext = os.path.splitext(p)[1].lower()
            if ext not in IMAGE_EXT:
                continue
            abs_img = p if os.path.isabs(p) else os.path.join(ws, p)
            if os.path.isfile(abs_img):
                img_flags += ["--image", abs_img]

        raw_out = ""
        err_text = ""
        proc = None
        pending_steps: list[dict] = []
        attempt_resume = bool(resume_flag)
        while True:
            fx_args = base + resume_flag + img_flags + ["--", prompt]
            try:
                cmd = agent_argv(ws, fx_args, perm)
            except FileNotFoundError as e:
                emit({"type": "error", "text": str(e)})
                emit({"type": "done"})
                return
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

            err_chunks: list[str] = []
            pending_steps = []

            def pump_err() -> None:
                assert proc.stderr is not None
                for raw in iter(proc.stderr.readline, b""):
                    line = ANSI.sub("", raw.decode("utf-8", errors="replace")).rstrip()
                    if not line or FXS_LINE.match(line):
                        continue
                    err_chunks.append(line)
                    step = parse_step(line)
                    if not step:
                        continue
                    if resume_flag:
                        pending_steps.append(step)
                    else:
                        emit(step)

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
            err_text = "\n".join(err_chunks)
            blob = raw_out + "\n" + err_text
            if attempt_resume and "NoSavedSessions" in blob:
                resume_flag = []
                attempt_resume = False
                continue
            break

        for step in pending_steps:
            emit(step)
        data = extract_json(raw_out) or extract_json(err_text)
        emitted = False
        if isinstance(data, dict):
            tools = data.get("tool_calls") or []
            if tools:
                for tcall in tools:
                    emit(tool_step(tcall))
            if data.get("session_id"):
                emit({"type": "session", "id": data["session_id"]})
            if data.get("model"):
                emit({"type": "model", "id": data["model"]})
            out = data.get("output") or ""
            if out:
                emit({"type": "token", "text": str(out)})
                emitted = True
            err = data.get("error")
            if err and not out:
                emit({"type": "error", "text": recover_error(raw_out, err_text)})
                emitted = True
        elif raw_out.strip():
            kept = []
            for line in raw_out.splitlines(True):
                if FXS_LINE.match(line):
                    continue
                kept.append(line)
            text = "".join(kept).strip()
            if text:
                emit({"type": "token", "text": "".join(kept)})
                emitted = True
        if proc is not None and proc.returncode not in (0, None):
            if proc.returncode and proc.returncode < 0:
                emit({"type": "step", "id": "run", "kind": "status",
                      "label": "Stopped", "status": "warn"})
            elif not emitted:
                emit({"type": "error", "text": recover_error(raw_out, err_text)})
        elif not emitted and (raw_out.strip() or err_text.strip()):
            emit({"type": "error", "text": recover_error(raw_out, err_text)})
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
        if a in ("--offline", "--local"):
            os.environ["FXS_UI_LOCAL"] = "1"; i += 1; continue
        if a == "--bind-all":
            host = "0.0.0.0"; i += 1; continue
        i += 1
    return host, port


def main() -> None:
    host, port = pick_host_port()
    boot_gateway()
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    sys.stderr.write(f"fxs-ui: {url}\n")
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
