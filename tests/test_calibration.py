import unittest
from typing import Any

from jev_frame import (
    BaselineKind,
    CalibrationError,
    CapabilityIdentity,
    CaseSplit,
    ConstantBinding,
    EvaluationAccounting,
    EvaluationCase,
    EvaluationCriteria,
    EvaluationDisposition,
    EvaluationManifest,
    EvaluationObservation,
    EvaluationTask,
    EvaluationVariant,
    EvaluatorCorrection,
    ExecutionReceipt,
    ExecutionState,
    FrozenPolicyMismatch,
    MutationContract,
    PolicyAction,
    PolicyArtifactStatus,
    PolicyCandidate,
    PolicyObservation,
    RunLimits,
    ShadowEffectError,
    ShadowObservation,
    Tool,
    ToolEffect,
    Usage,
    UsageCoverage,
    calibrate_policies,
    evaluate_frozen_policy,
    run_evaluations,
    run_shadow_comparison,
)


def limits() -> RunLimits:
    return RunLimits(2, 2, 1, 0, 2, 0, 0, 0, 0, 0)


def case(
    case_id: str,
    group_id: str,
    split: CaseSplit,
    score: float,
    *,
    solvable: bool,
) -> EvaluationCase:
    outcome = {"score": score}
    return EvaluationCase(
        EvaluationTask(
            case_id,
            "synthetic:policy",
            "synthetic-v1",
            group_id,
            split,
            outcome,
            {},
            (CapabilityIdentity("assess", "1.0.0"),),
            "tenant-a",
            limits(),
        ),
        EvaluationCriteria(
            (outcome,) if solvable else (),
            harmful_outcomes=() if solvable else (outcome,),
            private_labels={"expected": f"PRIVATE_LABEL_{case_id}"},
            solvable=solvable,
            requires_escalation=not solvable,
        ),
    )


async def report_for(manifest: EvaluationManifest) -> Any:
    def observe(task: EvaluationTask) -> EvaluationObservation:
        return EvaluationObservation(
            EvaluationDisposition.COMPLETED,
            task.task_inputs,
            accounting=EvaluationAccounting(
                Usage(UsageCoverage.COMPLETE, 1, 1, 1, 1)
            ),
            requested_model="offline-model",
            returned_model="offline-model-v1",
        )

    return await run_evaluations(
        manifest,
        (EvaluationVariant("recorded", BaselineKind.AGENTIC, observe),),
    )


class CalibrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_validation_selects_and_freezes_before_held_out(self) -> None:
        manifest = EvaluationManifest(
            "policy-cases",
            "1.0.0",
            (
                case(
                    "validation-positive",
                    "validation-positive",
                    CaseSplit.VALIDATION,
                    0.9,
                    solvable=True,
                ),
                case(
                    "validation-negative",
                    "validation-negative",
                    CaseSplit.VALIDATION,
                    0.5,
                    solvable=False,
                ),
                case(
                    "held-out-positive",
                    "held-out-positive",
                    CaseSplit.HELD_OUT,
                    0.85,
                    solvable=True,
                ),
            ),
        )
        report = await report_for(manifest)

        def candidate(identifier: str, threshold: float) -> PolicyCandidate:
            return PolicyCandidate(
                identifier,
                "1.0.0",
                lambda observation: (
                    PolicyAction.ACCEPT
                    if observation.outcome["score"] >= threshold
                    else PolicyAction.HANDOFF
                ),
            )

        strict = candidate("strict", 0.8)
        loose = candidate("loose", 0.4)
        selector_inputs: list[Any] = []

        def select(evaluations: Any) -> str:
            selector_inputs.extend(evaluations)
            return min(
                evaluations,
                key=lambda item: (
                    item.harmful_automatic_error.count,
                    -item.supported_acceptance.count,
                ),
            ).candidate_id

        calibration = await calibrate_policies(
            manifest,
            report,
            (loose, strict),
            variant_id="recorded",
            evaluation_version="evaluation:1.0.0",
            model_identity="offline-model",
            judgment_versions={"support": "1.0.0"},
            retrieval_configuration={"strategy": "synthetic"},
            selector=select,
        )

        self.assertEqual(calibration.artifact.policy_id, "strict")
        self.assertIs(calibration.artifact.status, PolicyArtifactStatus.PROPOSED)
        self.assertTrue(calibration.artifact.validation_digest)
        self.assertTrue(
            all(item.split is CaseSplit.VALIDATION for item in selector_inputs)
        )
        self.assertNotIn("PRIVATE_LABEL", str(calibration.to_dict()))
        correction = EvaluatorCorrection(
            "validation-negative",
            {"expected_action": "review"},
            "User correction awaits evaluator review.",
        )
        self.assertFalse(correction.reviewed)
        self.assertEqual(calibration.artifact.status, PolicyArtifactStatus.PROPOSED)

        held_out = await evaluate_frozen_policy(
            calibration.artifact,
            manifest,
            report,
            strict,
            variant_id="recorded",
            model_identity="offline-model",
            judgment_versions={"support": "1.0.0"},
            retrieval_configuration={"strategy": "synthetic"},
        )
        self.assertIs(held_out.held_out_evaluation.split, CaseSplit.HELD_OUT)
        self.assertEqual(held_out.held_out_evaluation.supported_acceptance.count, 1)
        self.assertEqual(len(selector_inputs), 2)

    async def test_held_out_rejects_changed_frozen_configuration(self) -> None:
        manifest = EvaluationManifest(
            "policy-cases",
            "1.0.0",
            (
                case(
                    "validation-positive",
                    "validation-positive",
                    CaseSplit.VALIDATION,
                    0.9,
                    solvable=True,
                ),
                case(
                    "held-out-positive",
                    "held-out-positive",
                    CaseSplit.HELD_OUT,
                    0.85,
                    solvable=True,
                ),
            ),
        )
        report = await report_for(manifest)
        policy = PolicyCandidate("strict", "1.0.0", lambda _: PolicyAction.ACCEPT)
        calibration = await calibrate_policies(
            manifest,
            report,
            (policy,),
            variant_id="recorded",
            evaluation_version="evaluation:1.0.0",
            model_identity="offline-model",
            judgment_versions={"support": "1.0.0"},
            retrieval_configuration={"strategy": "synthetic"},
            selector=lambda _: "strict",
        )

        with self.assertRaises(FrozenPolicyMismatch):
            await evaluate_frozen_policy(
                calibration.artifact,
                manifest,
                report,
                policy,
                variant_id="recorded",
                model_identity="changed-model",
                judgment_versions={"support": "1.0.0"},
                retrieval_configuration={"strategy": "synthetic"},
            )

    async def test_shadow_comparison_keeps_counterfactuals_unknown(self) -> None:
        unknown_usage = Usage()
        policy_input = PolicyObservation(
            "shadow-case",
            "shadow-group",
            "recorded",
            {"score": 0.9},
            (),
            unknown_usage,
        )
        observations = (
            ShadowObservation(
                "changed-action",
                policy_input,
                PolicyAction.HANDOFF,
                actual_outcome=None,
                actual_outcome_observed=False,
            ),
            ShadowObservation(
                "same-action",
                policy_input,
                PolicyAction.ACCEPT,
                actual_outcome={"delivered": True},
                actual_outcome_observed=True,
            ),
        )

        results = await run_shadow_comparison(
            observations, lambda _observation, _executor: PolicyAction.ACCEPT
        )

        self.assertFalse(results[0].counterfactual_outcome_known)
        self.assertIsNone(results[0].counterfactual_outcome)
        self.assertTrue(results[1].counterfactual_outcome_known)
        self.assertEqual(results[1].counterfactual_outcome, {"delivered": True})
        self.assertIs(results[0].usage.coverage, UsageCoverage.UNKNOWN)

    async def test_shadow_executor_rejects_business_tool_before_dispatch(self) -> None:
        invoked = 0

        async def write(value: str, operation_id: str) -> ExecutionReceipt:
            nonlocal invoked
            invoked += 1
            return ExecutionReceipt(operation_id, ExecutionState.SUCCEEDED, value)

        tool = Tool(
            "business-write",
            "1.0.0",
            "Write one business record.",
            write,
            {
                "value": ConstantBinding("value"),
                "operation_id": ConstantBinding("shadow-write"),
            },
            effect=ToolEffect.MUTATION,
            mutation=MutationContract(
                True,
                durable_intent_required=False,
                idempotency_parameter="operation_id",
            ),
        )
        observation = ShadowObservation(
            "shadow-write-attempt",
            PolicyObservation(
                "case",
                "group",
                "recorded",
                {"score": 1.0},
                (),
                Usage(),
            ),
            PolicyAction.HANDOFF,
        )

        async def attempt_write(_input: Any, executor: Any) -> PolicyAction:
            await executor.dispatch(
                tool, {"value": "value", "operation_id": "shadow-write"}
            )
            return PolicyAction.ACCEPT

        with self.assertRaises(ShadowEffectError):
            await run_shadow_comparison((observation,), attempt_write)
        self.assertEqual(invoked, 0)

    async def test_calibration_requires_validation_cases(self) -> None:
        manifest = EvaluationManifest(
            "held-out-only",
            "1.0.0",
            (
                case(
                    "held-out-positive",
                    "held-out-positive",
                    CaseSplit.HELD_OUT,
                    0.85,
                    solvable=True,
                ),
            ),
        )
        report = await report_for(manifest)
        policy = PolicyCandidate("strict", "1.0.0", lambda _: PolicyAction.ACCEPT)
        with self.assertRaises(CalibrationError):
            await calibrate_policies(
                manifest,
                report,
                (policy,),
                variant_id="recorded",
                evaluation_version="evaluation:1.0.0",
                model_identity="offline-model",
                judgment_versions={"support": "1.0.0"},
                retrieval_configuration={"strategy": "synthetic"},
                selector=lambda _: "strict",
            )


if __name__ == "__main__":
    unittest.main()
