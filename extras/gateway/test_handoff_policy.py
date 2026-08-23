#!/usr/bin/env python3
from __future__ import annotations

import unittest

import handoff_policy
from native_fx import NativeFxCapabilities


class NativeHandoffPolicy(unittest.TestCase):
    def caps(self, **kwargs) -> NativeFxCapabilities:
        values = {
            "available": True,
            "version": "fx test",
            "transport_probed": True,
        }
        values.update(kwargs)
        return NativeFxCapabilities(**values)

    def test_empty_released_capabilities_keep_adapter(self):
        decision = handoff_policy.decide_native_handoff(self.caps())
        self.assertFalse(decision.use_native)
        self.assertEqual(decision.reason_code, "transport-unproven")
        self.assertEqual(decision.missing, ("transport",))

    def test_candidate_evidence_never_authorizes_production_by_default(self):
        caps = self.caps(
            openai_compatible=True,
            openai_chat=True,
            openai_chat_tools=True,
            openai_chat_contracts=("fx_openai",),
            openai_chat_tool_contracts=("fx_openai",),
        )
        decision = handoff_policy.decide_native_handoff(caps, source="candidate")
        self.assertFalse(decision.use_native)
        self.assertEqual(decision.reason_code, "released-evidence-required")
        self.assertIn("released_evidence", decision.missing)

    def test_candidate_can_be_enabled_for_observational_ci(self):
        caps = self.caps(
            openai_compatible=True,
            openai_chat=True,
            openai_chat_tools=True,
            openai_chat_contracts=("fx_openai",),
            openai_chat_tool_contracts=("fx_openai",),
        )
        decision = handoff_policy.decide_native_handoff(
            caps,
            source="candidate",
            allow_candidate=True,
        )
        self.assertTrue(decision.use_native)
        self.assertEqual(decision.contract, "fx_openai")

    def test_text_only_transport_is_not_enough_for_default_coding_agent(self):
        caps = self.caps(
            openai_compatible=True,
            openai_chat=True,
            openai_chat_contracts=("fx_openai",),
        )
        decision = handoff_policy.decide_native_handoff(caps)
        self.assertFalse(decision.use_native)
        self.assertEqual(decision.reason_code, "tools-unproven")
        self.assertEqual(decision.missing, ("tools",))

    def test_released_chat_tool_contract_can_use_native(self):
        caps = self.caps(
            openai_compatible=True,
            openai_chat=True,
            openai_chat_tools=True,
            openai_chat_contracts=("custom_endpoint",),
            openai_chat_tool_contracts=("custom_endpoint",),
        )
        decision = handoff_policy.decide_native_handoff(caps)
        self.assertTrue(decision.use_native)
        self.assertEqual(decision.contract, "custom_endpoint")
        self.assertEqual(decision.reason_code, "native-evidence-satisfied")

    def test_responses_requires_responses_tool_contract(self):
        caps = self.caps(
            openai_compatible=True,
            openai_chat=True,
            openai_chat_tools=True,
            openai_chat_contracts=("custom_endpoint",),
            openai_chat_tool_contracts=("custom_endpoint",),
        )
        decision = handoff_policy.decide_native_handoff(
            caps,
            handoff_policy.HandoffRequirements(api_style="responses"),
        )
        self.assertFalse(decision.use_native)
        self.assertEqual(decision.reason_code, "transport-unproven")

    def test_transport_and_tools_must_be_proven_by_same_contract(self):
        caps = self.caps(
            openai_compatible=True,
            openai_chat=True,
            openai_chat_tools=True,
            openai_chat_contracts=("contract_a",),
            openai_chat_tool_contracts=("contract_b",),
        )
        decision = handoff_policy.decide_native_handoff(caps)
        self.assertFalse(decision.use_native)
        self.assertEqual(decision.reason_code, "tools-unproven")

    def test_semantic_requirement_fails_closed_without_evidence(self):
        caps = self.caps(
            openai_compatible=True,
            openai_responses=True,
            openai_responses_tools=True,
            openai_responses_contracts=("fx_openai",),
            openai_responses_tool_contracts=("fx_openai",),
        )
        requirements = handoff_policy.HandoffRequirements(
            api_style="responses",
            semantics=("images", "structured-output"),
        )
        decision = handoff_policy.decide_native_handoff(caps, requirements)
        self.assertFalse(decision.use_native)
        self.assertEqual(decision.reason_code, "semantics-unproven")
        self.assertEqual(decision.missing, ("images", "structured_output"))

    def test_semantic_evidence_must_belong_to_selected_contract(self):
        caps = self.caps(
            openai_compatible=True,
            openai_responses=True,
            openai_responses_tools=True,
            openai_responses_contracts=("fx_openai", "other"),
            openai_responses_tool_contracts=("fx_openai", "other"),
        )
        requirements = handoff_policy.HandoffRequirements(
            api_style="responses",
            semantics=("images", "structured_output"),
        )
        decision = handoff_policy.decide_native_handoff(
            caps,
            requirements,
            semantic_evidence={
                "fx_openai": {"images"},
                "other": {"structured_output"},
            },
        )
        self.assertFalse(decision.use_native)
        self.assertEqual(decision.reason_code, "semantics-unproven")

    def test_complete_semantic_evidence_allows_same_contract(self):
        caps = self.caps(
            openai_compatible=True,
            openai_responses=True,
            openai_responses_tools=True,
            openai_responses_contracts=("fx_openai", "other"),
            openai_responses_tool_contracts=("fx_openai", "other"),
        )
        requirements = handoff_policy.HandoffRequirements(
            api_style="responses",
            semantics=("images", "structured-output"),
        )
        decision = handoff_policy.decide_native_handoff(
            caps,
            requirements,
            semantic_evidence={
                "fx_openai": {"images", "structured_output"},
            },
        )
        self.assertTrue(decision.use_native)
        self.assertEqual(decision.contract, "fx_openai")

    def test_preferred_contract_order_is_respected_only_within_proven_set(self):
        caps = self.caps(
            openai_compatible=True,
            openai_chat=True,
            openai_chat_tools=True,
            openai_chat_contracts=("first", "second"),
            openai_chat_tool_contracts=("first", "second"),
        )
        requirements = handoff_policy.HandoffRequirements(
            preferred_contracts=("second",),
        )
        decision = handoff_policy.decide_native_handoff(caps, requirements)
        self.assertTrue(decision.use_native)
        self.assertEqual(decision.contract, "second")

    def test_adapter_mode_always_wins(self):
        caps = self.caps(
            openai_compatible=True,
            openai_chat=True,
            openai_chat_tools=True,
            openai_chat_contracts=("fx_openai",),
            openai_chat_tool_contracts=("fx_openai",),
        )
        decision = handoff_policy.decide_native_handoff(caps, mode="adapter")
        self.assertFalse(decision.use_native)
        self.assertEqual(decision.reason_code, "adapter-forced")

    def test_native_mode_is_not_an_unsafe_override(self):
        decision = handoff_policy.decide_native_handoff(
            self.caps(),
            mode="native",
        )
        self.assertFalse(decision.use_native)
        self.assertEqual(decision.reason_code, "transport-unproven")

    def test_tool_requirement_can_be_disabled_for_text_only_use_case(self):
        caps = self.caps(
            openai_compatible=True,
            openai_chat=True,
            openai_chat_contracts=("fx_openai",),
        )
        requirements = handoff_policy.HandoffRequirements(tools=False)
        decision = handoff_policy.decide_native_handoff(caps, requirements)
        self.assertTrue(decision.use_native)
        self.assertEqual(decision.contract, "fx_openai")

    def test_invalid_style_source_and_mode_are_rejected(self):
        with self.assertRaises(ValueError):
            handoff_policy.decide_native_handoff(
                self.caps(), handoff_policy.HandoffRequirements(api_style="grpc")
            )
        with self.assertRaises(ValueError):
            handoff_policy.decide_native_handoff(self.caps(), source="branch")
        with self.assertRaises(ValueError):
            handoff_policy.decide_native_handoff(self.caps(), mode="force")

    def test_decision_serialization_is_stable(self):
        decision = handoff_policy.HandoffDecision(
            route="adapter",
            reason_code="semantics-unproven",
            missing=("images",),
        )
        self.assertEqual(
            decision.to_dict(),
            {
                "route": "adapter",
                "contract": "",
                "reason_code": "semantics-unproven",
                "missing": ["images"],
                "use_native": False,
            },
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
