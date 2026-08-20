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
NOTICE_ATT = re.compile(r"attempt\s+(\d+)\s*/\s*(\d+)", re.I)
NOTICE_WAIT = re.compile(r"in\s+(\d+)\s*s", re.I)
BRACKET_TOOL = re.compile(r"^\[([a-z0-9_]+)\]\s*(.*)$", re.I)
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
CURRENT: dict = {"proc": None, "acp": None, "sid": None, "ws": None}

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
MODEL = os.environ.get("FX_MODEL", MODEL)


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


def fxs_bin() -> str | None:
    return which("fxs") or which("run-fx")


def fx_bin() -> str | None:
    return which("fx")


def agent() -> tuple[str, str]:
    fxs = fxs_bin()
    fx = fx_bin()
    if fxs and docker_state() == "running":
        return "fxs", fxs
    if fx:
        return "fx", fx
    if fxs:
        return "fxs", fxs
    return "", ""


def local_mode() -> bool:
    if os.environ.get("FXS_UI_LOCAL") == "1":
        return True
    if os.environ.get("FXS_UI_LOCAL") == "0":
        return False
    return not agent()[0]


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

    out: list[dict] = []
    seen: set[str] = set()

    def add(item: dict) -> None:
        sid = str(item.get("id") or "")
        if not sid or sid in seen:
            return
        seen.add(sid)
        out.append(item)

    try:
        ws_res = str(Path(ws).resolve()) if ws else ""
    except Exception:
        ws_res = ws or ""

    fx_root = HOME / ".fx" / "sessions"
    if fx_root.is_dir():
        rows = []
        for p in fx_root.iterdir():
            if not p.is_dir() or p.name.startswith(".") or p.name == "index.pending":
                continue
            meta: dict = {}
            for name in ("session.json", "display.json"):
                fp = p / name
                if not fp.is_file():
                    continue
                try:
                    data = json.loads(fp.read_text(encoding="utf-8", errors="replace")[:20000])
                except Exception:
                    continue
                if isinstance(data, dict):
                    meta.update(data)
            origin = str(meta.get("workspace_root") or meta.get("origin_workspace_root") or "")
            if ws_res and origin:
                try:
                    if str(Path(origin).resolve()) != ws_res:
                        continue
                except Exception:
                    if origin not in (ws, ws_res):
                        continue
            title = str(meta.get("title") or meta.get("preview") or "").strip()
            mtime = int(meta.get("updated_at_ms") or 0)
            if mtime > 10_000_000_000:
                mtime //= 1000
            if not mtime:
                try:
                    mtime = int(p.stat().st_mtime)
                except OSError:
                    mtime = 0
            rows.append({"id": p.name, "title": (title[:72] if title else p.name[:24]), "mtime": mtime})
        rows.sort(key=lambda x: -x["mtime"])
        for row in rows:
            add(row)

    h = hashlib.sha256(ws.encode()).hexdigest()[:16]
    sessions = STATE_ROOT / h / "sessions"
    if sessions.is_dir():
        for p in sorted(sessions.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.name.startswith("."):
                continue
            sid = p.stem if p.suffix else p.name
            add({
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


def clean_perm(raw) -> str:
    p = str(raw or "yolo")
    return p if p in ("ask", "auto", "yolo") else "yolo"


def run_fxs(ws: str, fx_args: list[str], perm: str = "yolo", timeout: int = 90) -> subprocess.CompletedProcess:
    kind, bin_ = agent()
    if not bin_:
        raise FileNotFoundError("fx is not on PATH")
    if kind == "fxs":
        cmd = [bin_, "run", "-w", ws]
        if perm != "yolo":
            cmd.append("--no-yolo")
        cmd += ["--"] + fx_args
    else:
        cmd = [bin_] + fx_args
    env = os.environ.copy()
    env["FX_MODEL"] = MODEL
    env["FX_PERMISSION_MODE"] = perm
    env.setdefault("FX_DISABLE_KEYCHAIN", "1")
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


ACP_KIND = {
    "read": "read", "edit": "write", "delete": "delete", "move": "write",
    "search": "search", "execute": "run", "think": "status",
    "fetch": "web", "other": "tool",
}
STEP_ID_OK = re.compile(r"[^A-Za-z0-9_-]+")


def step_id(raw) -> str:
    return STEP_ID_OK.sub("", str(raw or ""))[:80]


class AcpClient:
    """JSON-RPC 2.0 ACP client over fx acp stdio."""

    def __init__(self, fx: str, cwd: str, model: str, env: dict) -> None:
        self.cwd = cwd
        self.model = model
        self._id = 0
        self._pending: dict[int, dict] = {}
        self._lock = threading.Lock()
        self._turn = threading.Lock()
        self._alive = True
        self.perm = "yolo"
        self.on_update = None
        log = STATE_ROOT / "acp.log"
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            log = Path("/tmp/fx-acp.log")
        self.proc = subprocess.Popen(
            [fx, "acp", "--model", model, "--log-file", str(log)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            start_new_session=True,
            bufsize=0,
        )
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        self._err = threading.Thread(target=self._read_err, daemon=True)
        self._err.start()

    def alive(self) -> bool:
        return self._alive and self.proc.poll() is None

    def close(self) -> None:
        self._alive = False
        with self._lock:
            waiting = list(self._pending.values())
            self._pending.clear()
        for slot in waiting:
            slot["error"] = {"message": "closed"}
            slot["event"].set()
        try:
            if self.proc.poll() is None:
                os.killpg(self.proc.pid, signal.SIGTERM)
        except Exception:
            try:
                self.proc.terminate()
            except Exception:
                pass

    def _send(self, obj: dict) -> None:
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        with self._lock:
            assert self.proc.stdin is not None
            self.proc.stdin.write(line.encode("utf-8"))
            self.proc.stdin.flush()

    def notify(self, method: str, params) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params, timeout: float = 30) -> dict:
        ev = threading.Event()
        slot: dict = {"event": ev, "result": None, "error": None}
        with self._lock:
            self._id += 1
            rid = self._id
            self._pending[rid] = slot
            assert self.proc.stdin is not None
            line = json.dumps(
                {"jsonrpc": "2.0", "id": rid, "method": method, "params": params},
                ensure_ascii=False,
            ) + "\n"
            self.proc.stdin.write(line.encode("utf-8"))
            self.proc.stdin.flush()
        if not ev.wait(timeout):
            with self._lock:
                self._pending.pop(rid, None)
            raise TimeoutError(method + " timed out")
        if slot["error"]:
            err = slot["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise RuntimeError(msg or method)
        return slot["result"] if isinstance(slot["result"], dict) else {}

    def _reply(self, rid, result=None, error=None) -> None:
        msg: dict = {"jsonrpc": "2.0", "id": rid}
        if error is not None:
            msg["error"] = error
        else:
            msg["result"] = result if result is not None else {}
        self._send(msg)

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for raw in iter(self.proc.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            rid = msg.get("id")
            method = msg.get("method")
            if method and rid is not None:
                self._agent_request(rid, method, msg.get("params") or {})
                continue
            if rid is not None:
                with self._lock:
                    slot = self._pending.pop(rid, None)
                if not slot:
                    continue
                slot["result"] = msg.get("result")
                slot["error"] = msg.get("error")
                slot["event"].set()
                continue
            if method == "session/update":
                cb = self.on_update
                if cb:
                    try:
                        cb(msg.get("params") or {})
                    except Exception:
                        pass
        self._alive = False

    def _read_err(self) -> None:
        assert self.proc.stderr is not None
        for raw in iter(self.proc.stderr.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            step = parse_step(line)
            cb = self.on_update
            if step and cb:
                try:
                    cb({"update": {"sessionUpdate": "stderr_step", "step": step}})
                except Exception:
                    pass

    def _agent_request(self, rid, method: str, params: dict) -> None:
        if method == "session/request_permission":
            opts = params.get("options") or []
            prefer = "allow_always" if self.perm == "yolo" else "allow_once"
            pick = next((o for o in opts if o.get("kind") == prefer), None)
            if not pick:
                pick = next((o for o in opts if str(o.get("kind", "")).startswith("allow")), None)
            if not pick and opts:
                pick = opts[0]
            if pick:
                self._reply(rid, {"outcome": {"outcome": "selected", "optionId": pick.get("optionId")}})
            else:
                self._reply(rid, {"outcome": {"outcome": "selected", "optionId": "allow-once"}})
            return
        self._reply(rid, error={"code": -32601, "message": "method not found"})

    def initialize(self) -> dict:
        # Do not advertise fs/terminal — fx then uses its own tools, which
        # show up as tool_call updates in the activity trail.
        return self.request("initialize", {
            "protocolVersion": 1,
            "clientInfo": {"name": "fxs-ui", "title": "fxs", "version": "1"},
            "clientCapabilities": {},
        }, timeout=20)

    def new_session(self) -> dict:
        return self.request("session/new", {
            "cwd": self.cwd, "mcpServers": [],
        }, timeout=30)

    def resume_session(self, sid: str) -> dict:
        return self.request("session/resume", {
            "sessionId": sid, "cwd": self.cwd, "mcpServers": [],
        }, timeout=20)

    def load_session(self, sid: str) -> dict:
        return self.request("session/load", {
            "sessionId": sid, "cwd": self.cwd, "mcpServers": [],
        }, timeout=30)

    def set_mode(self, sid: str, perm: str) -> None:
        mode = "ask" if perm == "ask" else "code"
        try:
            self.request("session/set_mode", {"sessionId": sid, "modeId": mode}, timeout=10)
        except Exception:
            try:
                self.request("session/set_config_option", {
                    "sessionId": sid, "configId": "mode", "value": mode,
                }, timeout=10)
            except Exception:
                pass

    def prompt(self, sid: str, text: str, timeout: float = 600) -> dict:
        with self._turn:
            return self.request("session/prompt", {
                "sessionId": sid,
                "prompt": [{"type": "text", "text": text}],
            }, timeout=timeout)

    def cancel(self, sid: str) -> None:
        try:
            self.notify("session/cancel", {"sessionId": sid})
        except Exception:
            pass


def acp_rel(ws: str, path: str) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve().relative_to(Path(ws).resolve()))
    except Exception:
        return path


def acp_step_from_tool(update: dict, ws: str, prev: dict | None = None) -> dict:
    raw_kind = str(update.get("kind") or "")
    if raw_kind:
        kind = ACP_KIND.get(raw_kind, "tool")
    elif prev and prev.get("kind"):
        kind = str(prev.get("kind") or "tool")
    else:
        kind = "tool"
    title = str(update.get("title") or "")
    if not title and prev:
        title = str(prev.get("label") or "")
    if not title:
        title = kind
    st = str(update.get("status") or "in_progress").lower()
    if st in ("completed", "success", "ok"):
        status = "ok"
    elif st in ("failed", "error", "cancelled"):
        status = "warn"
    else:
        status = "running"
    path = ""
    locs = update.get("locations") or []
    if isinstance(locs, list) and locs:
        loc0 = locs[0] if isinstance(locs[0], dict) else {}
        path = acp_rel(ws, str(loc0.get("path") or ""))
    raw = update.get("rawInput") if isinstance(update.get("rawInput"), dict) else {}
    if not path:
        path = acp_rel(ws, str(raw.get("path") or raw.get("file") or raw.get("target") or ""))
    if not path and prev:
        path = str(prev.get("path") or "")
    cmd = str(raw.get("command") or raw.get("cmd") or "")
    label = shorten(title, 64)
    if path and Path(path).name not in label:
        label = f"{label} {Path(path).name}".strip()
    elif cmd and cmd not in label:
        label = f"{label} {shorten(cmd, 40)}".strip()
    tid = step_id(update.get("toolCallId") or (prev or {}).get("id") or "")
    return {
        "type": "step", "id": tid or None, "kind": kind,
        "label": label, "path": path, "status": status,
    }


def acp_info_step(update: dict) -> dict | None:
    meta = update.get("_meta") if isinstance(update.get("_meta"), dict) else {}
    fxm = meta.get("fx") if isinstance(meta.get("fx"), dict) else {}
    rec = None
    for cand in (fxm.get("modelResponseRecovery"), update.get("modelResponseRecovery"), fxm):
        if isinstance(cand, dict) and cand:
            rec = cand
            break
    blob = ""
    try:
        blob = json.dumps(update, ensure_ascii=False)
    except Exception:
        blob = str(update)
    low = blob.lower()
    recovered = "recovered" in low or "succeeded on attempt" in low
    retrying = (
        "retry" in low or "unavailable" in low or "503" in blob
        or "paused after" in low or "modelresponserecovery" in low
    )
    if isinstance(rec, dict):
        cause = str(rec.get("cause") or rec.get("action") or rec.get("outcome") or "")
        if "recover" in cause.lower() or rec.get("recovered") or rec.get("succeeded"):
            recovered = True
        if rec.get("action") == "retry_request" or "retry" in cause.lower() or "unavailable" in cause.lower():
            retrying = True
    if not recovered and not retrying:
        return None
    att = total = wait = None
    if isinstance(rec, dict):
        att = rec.get("attempt") or rec.get("attempts") or rec.get("providerAttempts") or rec.get("try")
        total = rec.get("limit") or rec.get("max") or rec.get("maxAttempts") or rec.get("total")
        wait = rec.get("waitMs") or rec.get("delayMs") or rec.get("retryInMs") or rec.get("in")
        if isinstance(att, str) and "/" in att:
            a, _, b = att.partition("/")
            att, total = a, total or b
    detail = ""
    if att and total:
        detail = f"{att}/{total}"
    elif att:
        detail = str(att)
    if wait not in (None, ""):
        try:
            w = float(wait)
            if w > 50:
                w = w / 1000.0
            detail = (detail + " · " if detail else "") + (str(int(w)) + "s")
        except Exception:
            pass
    if recovered:
        return {
            "type": "step", "id": "retry", "kind": "ok",
            "label": "Model recovered", "status": "ok",
        }
    if "paused after" in low or "gave up" in low:
        return {
            "type": "step", "id": "retry", "kind": "retry",
            "label": "Model unavailable", "detail": "gave up", "status": "warn",
        }
    return {
        "type": "step", "id": "retry", "kind": "retry",
        "label": "Waiting on the model", "detail": detail, "status": "running",
    }


def acp_chunk_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        t = content.get("text")
        return t if isinstance(t, str) else ""
    if isinstance(content, list):
        return "".join(acp_chunk_text(x) for x in content)
    return ""


def ensure_acp(ws: str, model: str, perm: str) -> AcpClient:
    with PROC_LOCK:
        acp = CURRENT.get("acp")
        if acp and acp.alive() and CURRENT.get("ws") == ws and acp.model == model:
            acp.perm = perm
            return acp
        if acp:
            acp.close()
            CURRENT["acp"] = None
            CURRENT["proc"] = None
            CURRENT["sid"] = None
        fx = fx_bin()
        if not fx:
            raise FileNotFoundError("fx is not on PATH")
        env = os.environ.copy()
        env["FX_MODEL"] = model
        env["FX_PERMISSION_MODE"] = perm
        env.setdefault("FX_DISABLE_KEYCHAIN", "1")
        acp = AcpClient(fx, ws, model, env)
        CURRENT["acp"] = acp
        CURRENT["proc"] = acp.proc
        CURRENT["ws"] = ws
        CURRENT["sid"] = None
    acp.perm = perm
    try:
        acp.initialize()
    except Exception:
        acp.close()
        with PROC_LOCK:
            if CURRENT.get("acp") is acp:
                CURRENT["acp"] = None
                CURRENT["proc"] = None
        raise
    return acp


def acp_open_session(acp: AcpClient, resume: str, replay_gate: dict) -> str:
    resume = (resume or "").strip()
    if resume == "last":
        cur = CURRENT.get("sid")
        resume = str(cur) if cur else ""
    if resume and CURRENT.get("sid") == resume and acp.alive():
        return resume
    if resume:
        try:
            res = acp.resume_session(resume)
            sid = str((res or {}).get("sessionId") or resume)
            return sid
        except Exception:
            try:
                replay_gate["on"] = True
                acp.load_session(resume)
                return resume
            except Exception:
                pass
            finally:
                replay_gate["on"] = False
    res = acp.new_session()
    sid = str((res or {}).get("sessionId") or "")
    if not sid:
        raise RuntimeError("fx acp did not return a session")
    return sid


def kill_current() -> None:
    with PROC_LOCK:
        acp = CURRENT.get("acp")
        sid = CURRENT.get("sid")
    if acp and sid:
        acp.cancel(sid)
        return
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
                "fxs": bool(which("fxs")),
                "fx": bool(which("fx")),
                "agent": agent()[0] or None,
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
        if u.path == "/api/file":
            try:
                ws = workspace_ok(str(payload.get("workspace") or default_workspace() or ""))
                rel = str(payload.get("path") or "")
                self._json(200, write_workspace_file(ws, rel, str(payload.get("text") or "")))
            except (ValueError, OSError) as e:
                self._json(400, {"error": str(e)})
            return
        self._json(404, {"error": "not found"})

    def _models(self) -> None:
        if local_mode():
            self._json(200, {"models": CATALOG_MODELS, "current": MODEL})
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
            models = CATALOG_MODELS
        if not models:
            models = CATALOG_MODELS
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
        images = payload.get("images") if isinstance(payload.get("images"), list) else []
        resume = str(payload.get("resume") or "")
        if not self._run_acp(prompt, ws, resume, perm, images, emit):
            self._run_fxs(prompt, ws, resume, perm, images, emit)


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

    def _run_acp(self, prompt: str, ws: str, resume: str, perm: str, images: list, emit) -> bool:
        if images or not fx_bin():
            return False
        try:
            acp = ensure_acp(ws, MODEL, perm)
        except Exception:
            return False

        replay = {"on": False}
        tools: dict[str, dict] = {}

        def on_update(params) -> None:
            if not isinstance(params, dict):
                return
            update = params.get("update") if isinstance(params.get("update"), dict) else {}
            kind = str(update.get("sessionUpdate") or update.get("type") or "")
            if kind == "stderr_step":
                step = update.get("step")
                if isinstance(step, dict):
                    emit(step)
                return
            if kind in ("agent_message_chunk", "agent_thought_chunk"):
                if replay["on"] or kind == "agent_thought_chunk":
                    return
                text = acp_chunk_text(update.get("content"))
                if text:
                    emit({"type": "token", "text": text})
                return
            if kind in ("tool_call", "tool_call_update"):
                tid = step_id(update.get("toolCallId") or "")
                step = acp_step_from_tool(update, ws, tools.get(tid))
                if tid:
                    tools[tid] = step
                emit(step)
                return
            if kind in ("session_info_update", "session_info"):
                step = acp_info_step(update)
                if step:
                    emit(step)

        acp.on_update = on_update
        sid = ""
        try:
            sid = acp_open_session(acp, resume, replay)
            with PROC_LOCK:
                CURRENT["sid"] = sid
            emit({"type": "session", "id": sid})
            acp.set_mode(sid, perm)
            result = acp.prompt(sid, prompt, timeout=600)
            stop = str((result or {}).get("stopReason") or "")
            if stop == "cancelled":
                emit({"type": "step", "id": "run", "kind": "status",
                      "label": "Stopped", "status": "warn"})
            elif stop and stop not in ("end_turn", "max_tokens"):
                emit({"type": "step", "id": "run", "kind": "status",
                      "label": stop.replace("_", " "), "status": "warn"})
        except TimeoutError:
            if sid:
                acp.cancel(sid)
            emit({"type": "error", "text": "timed out"})
        except Exception as e:
            emit({"type": "error", "text": str(e)})
        finally:
            acp.on_update = None
            emit({"type": "done"})
        return True

    def _run_fxs(self, prompt: str, ws: str, resume: str, perm: str, images: list, emit) -> None:

        kind, bin_ = agent()
        if not bin_:
            emit({"type": "error", "text": "fx is not on PATH"})
            emit({"type": "done"})
            return
        perm = clean_perm(perm)
        if kind == "fxs":
            cmd = [bin_, "run", "-w", ws]
            if perm != "yolo":
                cmd.append("--no-yolo")
            cmd += ["--", "ask", "--json"]
            if perm == "yolo":
                cmd.append("--yolo")
        else:
            cmd = [bin_, "ask", "--json"]
            if perm == "yolo":
                cmd.append("--yolo")
            elif perm == "auto":
                cmd.append("--auto")
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
        env.setdefault("FX_DISABLE_KEYCHAIN", "1")
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
                line = raw.decode("utf-8", errors="replace").rstrip()
                step = parse_step(line)
                if step:
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
        data = extract_json(raw_out)
        if isinstance(data, dict):
            tools = data.get("tool_calls") or []
            if tools:
                for tcall in tools:
                    emit(tool_step(tcall))
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
                emit({"type": "step", "id": "run", "kind": "status",
                      "label": "Stopped", "status": "warn"})
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
        if a in ("--offline", "--local"):
            os.environ["FXS_UI_LOCAL"] = "1"; i += 1; continue
        if a == "--bind-all":
            host = "0.0.0.0"; i += 1; continue
        i += 1
    return host, port


def main() -> None:
    host, port = pick_host_port()
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
