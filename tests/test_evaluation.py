import inspect
import json
import time
import unittest
from collections.abc import Sequence
from typing import Any

from jev_frame import (
    AttemptAdmission,
    AttemptStatus,
    BaselineKind,
    CapabilityIdentity,
    CaseSplit,
    CompiledQuestion,
    DecisionClient,
    DecisionContext,
    DecisionInputs,
    EvaluationAccounting,
    EvaluationCase,
    EvaluationCriteria,
    EvaluationDisposition,
    EvaluationFailure,
    EvaluationLeakageError,
    EvaluationManifest,
    EvaluationObservation,
    EvaluationTask,
    EvaluationVariant,
    Judgment,
    NoulAnswer,
    NoulQuestion,
    ProviderAttempt,
    ProviderBatch,
    RunLimits,
    SemanticConfiguration,
    Subject,
    Usage,
    UsageCoverage,
    run_evaluations,
)


def limits() -> RunLimits:
    return RunLimits(4, 4, 2, 1, 2, 0, 0, 0, 0, 0)


def task(
    case_id: str,
    *,
    group: str,
    capabilities: tuple[CapabilityIdentity, ...],
    split: CaseSplit = CaseSplit.HELD_OUT,
    seed: int | None = None,
) -> EvaluationTask:
    return EvaluationTask(
        case_id,
        "synthetic:claims",
        "synthetic-v1",
        group,
        split,
        {"claim": "supported"},
        {"source": {"version": "v1"}},
        capabilities,
        "tenant-a",
        limits(),
        seed,
    )


class CapturingProvider:
    def __init__(self) -> None:
        self.states: list[Any] = []

    async def evaluate(
        self,
        *,
        state: Any,
        questions: Sequence[CompiledQuestion],
        requested_model: str,
        operation_id: str,
        timeout: float | None = None,
        admit_attempt: AttemptAdmission | None = None,
    ) -> ProviderBatch:
        del timeout
        self.states.append(state)
        attempt = ProviderAttempt(f"{operation_id}:1", 1, AttemptStatus.STARTED)
        if admit_attempt is not None:
            result = admit_attempt(attempt)
            if inspect.isawaitable(result):
                await result
        finished = ProviderAttempt(
            attempt.id,
            1,
            AttemptStatus.SUCCEEDED,
            request_id=f"request:{operation_id}",
        )
        return ProviderBatch(
            {questions[0].routing_id: NoulAnswer(0.95)},
            requested_model,
            "offline-returned-model",
            finished.request_id,
            Usage(UsageCoverage.COMPLETE, 4, 1, 1, 1),
            (finished,),
        )


class EvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_decision_comparison_keeps_labels_out_and_groups_variants(
        self,
    ) -> None:
        first_capabilities = (CapabilityIdentity("lookup", "1.0.0"),)
        second_capabilities = (
            CapabilityIdentity("lookup", "1.0.0"),
            CapabilityIdentity("corroborate", "1.0.0"),
        )
        cases = tuple(
            EvaluationCase(
                task(
                    case_id,
                    group="claim-family",
                    capabilities=capabilities,
                    seed=7,
                ),
                EvaluationCriteria(
                    ("supported",),
                    (frozenset({f"{case_id}:judgment"}),),
                    ("harmful",),
                    {"expected_label": f"PRIVATE_EXPECTED_{case_id}"},
                ),
            )
            for case_id, capabilities in (
                ("case-a", first_capabilities),
                ("case-a-variant", second_capabilities),
            )
        )
        manifest = EvaluationManifest("scenario-a", "1.0.0", cases)
        provider_states: list[Any] = []

        async def with_jev(case: EvaluationTask) -> EvaluationObservation:
            provider = CapturingProvider()
            judgment = Judgment(
                "support",
                "1.0.0",
                NoulQuestion("Is the claim supported?"),
                (Subject("claim"),),
            )
            client = DecisionClient(provider, model="offline-model")
            result = await client.evaluate(
                judgment,
                DecisionInputs(case.id, {"claim": case.task_inputs["claim"]}),
                DecisionContext(
                    case.scope,
                    time.monotonic() + 10,
                    case.limits,
                    run_id=case.id,
                ),
            )
            provider_states.extend(provider.states)
            assert client.ledger is not None
            accounting = EvaluationAccounting.from_ledger(
                await client.ledger.snapshot(),
                foreign_usage_expected=True,
            )
            return EvaluationObservation(
                EvaluationDisposition.COMPLETED,
                "supported",
                result.evidence_refs,
                automatic=True,
                captured_inputs=tuple(provider.states),
                accounting=accounting,
                verified_cost=0.01,
                requested_model=result.requested_model,
                returned_model=result.returned_model,
                sdk_version="typesafe-sdk-0.7.0",
                framework_version="direct-api",
            )

        def deterministic(case: EvaluationTask) -> EvaluationObservation:
            return EvaluationObservation(
                EvaluationDisposition.COMPLETED,
                "supported",
                (f"{case.id}:judgment",),
                captured_inputs=(case.task_inputs, case.permitted_evidence),
                accounting=EvaluationAccounting(
                    Usage(UsageCoverage.COMPLETE, 0, 0)
                ),
                verified_cost=0.0,
                framework_version="stdlib",
            )

        report = await run_evaluations(
            manifest,
            (
                EvaluationVariant(
                    "host-with-jev",
                    BaselineKind.HOST_WITH_JEV,
                    with_jev,
                    SemanticConfiguration(tools=2, judgments=1),
                ),
                EvaluationVariant(
                    "deterministic",
                    BaselineKind.DETERMINISTIC,
                    deterministic,
                    SemanticConfiguration(tools=2),
                ),
            ),
        )

        with_jev_summary = report.summaries[0]
        deterministic_summary = report.summaries[1]
        self.assertEqual(with_jev_summary.case_count, 2)
        self.assertEqual(with_jev_summary.group_count, 1)
        self.assertEqual(with_jev_summary.supported_completion.to_dict(), {
            "count": 1,
            "denominator": 1,
            "rate": 1.0,
        })
        self.assertIs(with_jev_summary.usage.coverage, UsageCoverage.PARTIAL)
        self.assertIsNone(with_jev_summary.usage.input_tokens)
        self.assertEqual(with_jev_summary.usage.provider_attempts, 2)
        self.assertFalse(
            deterministic_summary.unfamiliar_combinations_need_controller_change
        )
        serialized = report.to_json()
        self.assertNotIn("PRIVATE_EXPECTED", serialized)
        self.assertNotIn("PRIVATE_EXPECTED", json.dumps(provider_states))
        self.assertEqual(report.records[0].seed, 7)
        self.assertEqual(
            [item.id for item in report.records[1].capabilities],
            ["lookup", "corroborate"],
        )

    async def test_leakage_fails_closed_before_report(self) -> None:
        case = EvaluationCase(
            task(
                "leak-case",
                group="leak-group",
                capabilities=(CapabilityIdentity("lookup", "1.0.0"),),
            ),
            EvaluationCriteria(
                ("supported",),
                private_labels={"expected": "DO_NOT_PROJECT"},
            ),
        )

        def leaking(_: EvaluationTask) -> EvaluationObservation:
            return EvaluationObservation(
                EvaluationDisposition.COMPLETED,
                "supported",
                captured_inputs=({"answer": "DO_NOT_PROJECT"},),
            )

        with self.assertRaises(EvaluationLeakageError):
            await run_evaluations(
                EvaluationManifest("leakage", "1.0.0", (case,)),
                (
                    EvaluationVariant(
                        "leaking", BaselineKind.DETERMINISTIC, leaking
                    ),
                ),
            )

    async def test_failures_zero_denominators_and_unknown_cost_remain_visible(
        self,
    ) -> None:
        case = EvaluationCase(
            task(
                "escalation-case",
                group="missing-source",
                capabilities=(CapabilityIdentity("retrieve", "1.0.0"),),
            ),
            EvaluationCriteria(
                private_labels={"answer": "EVALUATOR_ONLY"},
                solvable=False,
                requires_escalation=True,
            ),
        )
        manifest = EvaluationManifest("failures", "1.0.0", (case,))

        def retrieval(_: EvaluationTask) -> EvaluationObservation:
            return EvaluationObservation(
                EvaluationDisposition.UNRESOLVED,
                failure=EvaluationFailure.RETRIEVAL,
                accounting=EvaluationAccounting(Usage()),
            )

        def unavailable(_: EvaluationTask) -> EvaluationObservation:
            raise RuntimeError("PRIVATE SERVICE FAILURE")

        report = await run_evaluations(
            manifest,
            (
                EvaluationVariant(
                    "retrieval", BaselineKind.AGENTIC, retrieval
                ),
                EvaluationVariant(
                    "service", BaselineKind.HOST_WITHOUT_JEV, unavailable
                ),
            ),
        )

        retrieval_summary, service_summary = report.summaries
        self.assertEqual(retrieval_summary.correct_escalation.count, 1)
        self.assertEqual(retrieval_summary.retrieval_failure.count, 1)
        self.assertEqual(retrieval_summary.supported_completion.denominator, 0)
        self.assertIsNone(retrieval_summary.supported_completion.rate)
        self.assertIsNone(
            retrieval_summary.verified_cost_per_supported_completion
        )
        self.assertEqual(service_summary.service_failure.count, 1)
        self.assertEqual(
            [record.failure for record in report.records],
            [EvaluationFailure.RETRIEVAL, EvaluationFailure.SERVICE],
        )
        self.assertNotIn("PRIVATE SERVICE FAILURE", report.to_json())

    async def test_harmful_error_and_unnecessary_handoff_stay_separate(self) -> None:
        case = EvaluationCase(
            task(
                "solvable-case",
                group="solvable-group",
                capabilities=(CapabilityIdentity("lookup", "1.0.0"),),
            ),
            EvaluationCriteria(
                ("good",),
                harmful_outcomes=("bad",),
                private_labels={"harmful": "PRIVATE_HARMFUL_LABEL"},
            ),
        )
        manifest = EvaluationManifest("negative-results", "1.0.0", (case,))

        def harmful(_: EvaluationTask) -> EvaluationObservation:
            return EvaluationObservation(
                EvaluationDisposition.COMPLETED,
                "bad",
                automatic=True,
                verified_cost=0.5,
            )

        def handoff(_: EvaluationTask) -> EvaluationObservation:
            return EvaluationObservation(EvaluationDisposition.HANDOFF)

        report = await run_evaluations(
            manifest,
            (
                EvaluationVariant("harmful", BaselineKind.AGENTIC, harmful),
                EvaluationVariant("handoff", BaselineKind.AGENTIC, handoff),
            ),
        )

        harmful_summary, handoff_summary = report.summaries
        self.assertEqual(harmful_summary.harmful_automatic_error.count, 1)
        self.assertEqual(harmful_summary.supported_completion.count, 0)
        self.assertIsNone(
            harmful_summary.verified_cost_per_supported_completion
        )
        self.assertEqual(handoff_summary.unnecessary_handoff.count, 1)
        self.assertEqual(handoff_summary.correct_escalation.denominator, 0)
        self.assertNotIn("PRIVATE_HARMFUL_LABEL", report.to_json())


if __name__ == "__main__":
    unittest.main()
