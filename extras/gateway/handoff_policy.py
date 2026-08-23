#!/usr/bin/env python3
"""Fail-closed policy for deciding whether native fx may replace the adapter.

Capability discovery and routing are intentionally separate concerns. A draft
upstream candidate may prove that a transport works, while production routing
must still require released-binary evidence and all semantics needed by the
current use case.

This module performs no probing and changes no runtime route by itself. It turns
an already-collected ``NativeFxCapabilities`` snapshot plus explicit semantic
evidence into a deterministic ``native`` or ``adapter`` decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

from native_fx import NativeFxCapabilities

_CHAT_ALIASES = {"chat", "completions", "chat-completions", "chat_completions"}
_VALID_SOURCES = {"released", "candidate", "unknown"}
_VALID_MODES = {"auto", "native", "adapter"}


@dataclass(frozen=True)
class HandoffRequirements:
    """Capabilities the selected provider path must preserve."""

    api_style: str = "chat"
    tools: bool = True
    semantics: tuple[str, ...] = ()
    preferred_contracts: tuple[str, ...] = ()

    def normalized_api_style(self) -> str:
        style = (self.api_style or "chat").strip().lower()
        if style == "responses":
            return "responses"
        if style in _CHAT_ALIASES:
            return "chat"
        raise ValueError(f"unsupported API style: {self.api_style}")

    def normalized_semantics(self) -> tuple[str, ...]:
        out: list[str] = []
        seen: set[str] = set()
        for raw in self.semantics:
            value = str(raw or "").strip().lower().replace("-", "_")
            if not value or value in seen:
                continue
            seen.add(value)
            out.append(value)
        return tuple(out)


@dataclass(frozen=True)
class HandoffDecision:
    route: str
    contract: str = ""
    reason_code: str = ""
    missing: tuple[str, ...] = ()

    @property
    def use_native(self) -> bool:
        return self.route == "native"

    def to_dict(self) -> dict:
        return {
            "route": self.route,
            "contract": self.contract,
            "reason_code": self.reason_code,
            "missing": list(self.missing),
            "use_native": self.use_native,
        }


def _contract_order(
    available: Iterable[str],
    preferred: Iterable[str],
) -> tuple[str, ...]:
    available_list = [str(item) for item in available if str(item)]
    available_set = set(available_list)
    out: list[str] = []
    for item in preferred:
        value = str(item or "")
        if value in available_set and value not in out:
            out.append(value)
    for value in available_list:
        if value not in out:
            out.append(value)
    return tuple(out)


def _semantic_set(
    semantic_evidence: Optional[Mapping[str, Iterable[str]]],
    contract: str,
) -> set[str]:
    if not semantic_evidence:
        return set()
    values = semantic_evidence.get(contract) or ()
    return {
        str(value or "").strip().lower().replace("-", "_")
        for value in values
        if str(value or "").strip()
    }


def decide_native_handoff(
    capabilities: NativeFxCapabilities,
    requirements: HandoffRequirements = HandoffRequirements(),
    *,
    source: str = "released",
    mode: str = "auto",
    allow_candidate: bool = False,
    semantic_evidence: Optional[Mapping[str, Iterable[str]]] = None,
) -> HandoffDecision:
    """Choose native fx only when one contract proves every required property.

    ``source`` describes where the capability snapshot came from. Production
    callers should use the default ``released``. Candidate evidence is useful
    for CI/observability but cannot authorize native routing unless the caller
    opts in explicitly with ``allow_candidate=True``.

    ``mode='native'`` is a preference, not an unsafe override: it still fails
    closed to the adapter when evidence is insufficient.
    """

    source = (source or "unknown").strip().lower()
    if source not in _VALID_SOURCES:
        raise ValueError(f"unsupported handoff evidence source: {source}")
    mode = (mode or "auto").strip().lower()
    if mode not in _VALID_MODES:
        raise ValueError(f"unsupported handoff mode: {mode}")
    if mode == "adapter":
        return HandoffDecision(
            route="adapter",
            reason_code="adapter-forced",
        )

    if source != "released" and not (source == "candidate" and allow_candidate):
        return HandoffDecision(
            route="adapter",
            reason_code="released-evidence-required",
            missing=("released_evidence",),
        )

    style = requirements.normalized_api_style()
    required_semantics = requirements.normalized_semantics()

    if style == "responses":
        transport_contracts = capabilities.openai_responses_contracts
        tool_contracts = capabilities.openai_responses_tool_contracts
    else:
        transport_contracts = capabilities.openai_chat_contracts
        tool_contracts = capabilities.openai_chat_tool_contracts

    ordered = _contract_order(transport_contracts, requirements.preferred_contracts)
    if not ordered:
        return HandoffDecision(
            route="adapter",
            reason_code="transport-unproven",
            missing=("transport",),
        )

    if requirements.tools:
        tool_set = set(tool_contracts)
        ordered = tuple(contract for contract in ordered if contract in tool_set)
        if not ordered:
            return HandoffDecision(
                route="adapter",
                reason_code="tools-unproven",
                missing=("tools",),
            )

    if required_semantics:
        for contract in ordered:
            proven = _semantic_set(semantic_evidence, contract)
            if all(item in proven for item in required_semantics):
                return HandoffDecision(
                    route="native",
                    contract=contract,
                    reason_code="native-evidence-satisfied",
                )
        return HandoffDecision(
            route="adapter",
            reason_code="semantics-unproven",
            missing=required_semantics,
        )

    return HandoffDecision(
        route="native",
        contract=ordered[0],
        reason_code="native-evidence-satisfied",
    )
