#!/usr/bin/env python3
"""Probe observable fx CLI capabilities without relying on version numbers.

The adapter must not disappear merely because an upstream branch or release number
suggests overlap. This module provides a conservative handoff gate: native fx is
considered capable only when its installed CLI explicitly advertises the relevant
OpenAI-compatible setup surface.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class NativeFxCapabilities:
    available: bool = False
    version: str = ""
    openai_compatible: bool = False
    openai_chat: bool = False
    openai_responses: bool = False
    evidence: tuple[str, ...] = ()

    def supports(self, api_style: str) -> bool:
        style = (api_style or "chat").strip().lower()
        if style == "responses":
            return self.openai_responses
        if style in ("chat", "completions", "chat-completions", "chat_completions"):
            return self.openai_chat
        return False

    def to_dict(self) -> dict:
        out = asdict(self)
        out["evidence"] = list(self.evidence)
        return out


def _run(argv: list[str], timeout: int = 8) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return proc.returncode, proc.stdout or ""


def _has_any(text: str, needles: Iterable[str]) -> bool:
    low = (text or "").lower()
    return any(needle.lower() in low for needle in needles)


def probe_fx(path: Optional[str] = None) -> NativeFxCapabilities:
    fx = path or shutil.which("fx")
    if not fx:
        return NativeFxCapabilities()

    version_rc, version_out = _run([fx, "--version"])
    if version_rc != 0:
        return NativeFxCapabilities()
    version = " ".join(version_out.strip().split())

    evidence: list[str] = []
    setup_rc, setup_help = _run([fx, "setup", "--help"])
    _root_rc, root_help = _run([fx, "--help"])
    combined = "\n".join(part for part in (setup_help, root_help) if part)

    advertises_openai = setup_rc == 0 and _has_any(
        combined,
        ("openai-compatible", "openai compatible"),
    )
    if not advertises_openai:
        return NativeFxCapabilities(
            available=True,
            version=version,
        )
    evidence.append("setup advertises openai-compatible")

    # Some older fx builds accept arbitrary setup subcommands with --help and
    # return success. Only interrogate the detailed target after its parent help
    # explicitly advertises it, otherwise that false-positive is meaningless.
    detail_rc, detail_help = _run([fx, "setup", "openai-compatible", "--help"])
    detail_ok = detail_rc == 0 and bool(detail_help.strip())
    if detail_ok:
        evidence.append("setup openai-compatible --help succeeds")

    native = detail_ok
    detail = "\n".join((combined, detail_help))

    # Chat Completions is the minimum contract for the native OpenAI-compatible
    # provider proposal. Only mark it available after the setup surface exists.
    chat = native and _has_any(
        detail,
        (
            "chat completions",
            "chat/completions",
            "openai-compatible",
            "openai compatible",
        ),
    )
    if chat:
        evidence.append("native chat-compatible transport advertised")

    # Responses support is intentionally stricter. A generic OpenAI-compatible
    # setup surface is not enough to retire the adapter's Responses path.
    responses = native and _has_any(
        detail,
        (
            "fx_openai_api_style",
            "openai_api_style",
            "/responses",
            "responses api",
            "api style: responses",
            "api-style responses",
        ),
    )
    if responses:
        evidence.append("native responses transport advertised")

    return NativeFxCapabilities(
        available=True,
        version=version,
        openai_compatible=native,
        openai_chat=chat,
        openai_responses=responses,
        evidence=tuple(evidence),
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Probe installed fx provider capabilities")
    parser.add_argument("--fx", default="", help="path to fx binary (default: PATH)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    result = probe_fx(args.fx or None)
    if args.json:
        print(json.dumps(result.to_dict(), sort_keys=True))
    else:
        print(f"fx: {result.version or 'unavailable'}")
        print(f"openai-compatible: {'yes' if result.openai_compatible else 'no'}")
        print(f"chat: {'yes' if result.openai_chat else 'no'}")
        print(f"responses: {'yes' if result.openai_responses else 'no'}")
        for item in result.evidence:
            print(f"- {item}")
    return 0 if result.available else 1


if __name__ == "__main__":
    raise SystemExit(main())
