import asyncio
import json
import unittest
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from jev_frame import (
    NO_FIT_KEY,
    AcceptanceEvidence,
    AcceptanceRecord,
    AcceptanceStatus,
    AttemptAdmission,
    AttemptStatus,
    Candidate,
    CandidateSet,
    ChoiceAnswer,
    ChoiceQuestion,
    CompiledQuestion,
    Coverage,
    DecisionClient,
    DecisionContext,
    DecisionInputs,
    DiagnosticCategory,
    EventKind,
    EvidenceSelector,
    EvidenceStore,
    InspectionError,
    InspectionProjection,
    JevEvent,
    Judgment,
    Observation,
    ProviderAttempt,
    ProviderBatch,
    ProviderError,
    RunLimits,
    Subject,
    Unresolved,
    UnresolvedReason,
    Usage,
    UsageCoverage,
    diagnostic_for_unresolved,
    inspect_decision,
    serialize_decision_result,
)


def limits() -> RunLimits:
    return RunLimits(4, 4, 0, 0, 2, 0, 0, 0, 0, 0)


class ChoiceProvider:
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
        attempt = ProviderAttempt(f"{operation_id}:1", 1, AttemptStatus.STARTED)
        if admit_attempt is not None:
            await admit_attempt(attempt)  # type: ignore[misc]
        question = questions[0]
        answer = ChoiceAnswer(
            "doc-1",
            {
                option.key: 1.0 if option.key == "doc-1" else 0.0
                for option in question.options
            },
            1.0,
        )
        finished = ProviderAttempt(
            attempt.id, 1, AttemptStatus.SUCCEEDED, request_id="request-1"
        )
        return ProviderBatch(
            {question.routing_id: answer},
            requested_model,
            "returned-model",
            "request-1",
            Usage(UsageCoverage.COMPLETE, 12, 3, 1, 1),
            (finished,),
        )


class ExplodingProvider:
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
        raise ProviderError("HOSTILE_EXCEPTION_SECRET")


class BlockingProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()

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
        attempt = ProviderAttempt(f"{operation_id}:1", 1, AttemptStatus.STARTED)
        if admit_attempt is not None:
            await admit_attempt(attempt)  # type: ignore[misc]
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


def fixture() -> tuple[Judgment, DecisionInputs, EvidenceStore, CandidateSet]:
    judgment = Judgment(
        "choose_document",
        "1.0.0",
        ChoiceQuestion("PRIVATE QUESTION: choose the supporting document."),
        (Subject("request"),),
        (EvidenceSelector("request_source"),),
        candidate_set="documents",
    )
    observation = Observation(
        id="source-1",
        value="PRIVATE EVIDENCE",
        source_id="fixture-source",
        scope="tenant-a",
        observed_at=0.0,
        source_version="v1",
    )
    candidates = CandidateSet(
        "documents",
        "1.0.0",
        (
            Candidate(
                "doc-1",
                {"body": "PRIVATE CANDIDATE"},
                "PRIVATE DESCRIPTION",
                "catalog",
                "v2",
            ),
        ),
        Coverage.COMPLETE,
        "tenant-a",
    )
    inputs = DecisionInputs(
        "operation-1",
        {"request": "find support"},
        {"request_source": observation},
        {"documents": candidates},
    )
    return judgment, inputs, EvidenceStore(lambda: 0.0), candidates


class InspectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_events_round_trip_with_correlation_attempt_and_usage(self) -> None:
        judgment, inputs, store, _ = fixture()
        received: list[Mapping[str, Any]] = []
        context = DecisionContext(
            "tenant-a",
            100.0,
            limits(),
            host_dependencies={"token": "HOST_DEPENDENCY_SECRET"},
            clock=lambda: 0.0,
            event_sink=received.append,
            evidence_session=store,
            run_id="run-1",
            correlation_id="correlation-1",
            parent_operation_id="parent-1",
        )
        client = DecisionClient(ChoiceProvider(), model="requested-model")

        await client.evaluate(judgment, inputs, context)

        self.assertEqual(
            [event.kind for event in client.events],
            [
                EventKind.OPERATION_STARTED,
                EventKind.ATTEMPT_ADMITTED,
                EventKind.OPERATION_COMPLETED,
            ],
        )
        self.assertEqual([event.sequence for event in client.events], [1, 2, 3])
        attempt = JevEvent.from_dict(client.events[1].to_dict())
        completed = JevEvent.from_dict(client.events[2].to_dict())
        self.assertEqual(attempt.attempt_id, "operation-1:1")
        self.assertEqual(attempt.correlation_id, "correlation-1")
        self.assertEqual(attempt.parent_operation_id, "parent-1")
        self.assertEqual(completed.data["usage"]["coverage"], "complete")
        self.assertEqual(received, [event.to_dict() for event in client.events])
        self.assertNotIn("HOST_DEPENDENCY_SECRET", json.dumps(received))

    async def test_public_inspection_is_redacted_and_exact_projection_is_explicit(
        self,
    ) -> None:
        judgment, inputs, store, candidates = fixture()
        client = DecisionClient(ChoiceProvider(), model="requested-model")
        context = DecisionContext(
            "tenant-a",
            100.0,
            limits(),
            clock=lambda: 0.0,
            evidence_session=store,
        )
        result = await client.evaluate(judgment, inputs, context)
        acceptance = AcceptanceRecord(
            "support-policy", "1.0.0", AcceptanceStatus.ACCEPT, ("supported",)
        )
        store.add(
            AcceptanceEvidence(
                id="acceptance-1",
                value=acceptance,
                source_id="support-policy",
                scope="tenant-a",
                observed_at=0.0,
                dependencies=("operation-1:judgment",),
                judgment_ref="operation-1:judgment",
                policy_id="support-policy",
                policy_version="1.0.0",
            )
        )
        result = replace(
            result,
            evidence_refs=result.evidence_refs + ("acceptance-1",),
            acceptance=acceptance,
        )

        public = inspect_decision(
            result,
            store,
            candidate_set=candidates,
            accepted_bindings={"selected_source": "source-1"},
        ).to_dict()
        public_json = json.dumps(public)
        self.assertNotIn("PRIVATE EVIDENCE", public_json)
        self.assertNotIn("PRIVATE CANDIDATE", public_json)
        self.assertNotIn("PRIVATE DESCRIPTION", public_json)
        self.assertNotIn("PRIVATE QUESTION", public_json)
        self.assertEqual(public["accepted_bindings"]["selected_source"], "source-1")
        self.assertEqual(public["decision"]["acceptance"]["reasons"], ["supported"])
        self.assertEqual(
            [item["key"] for item in public["presented_candidates"]],
            ["doc-1", NO_FIT_KEY],
        )
        self.assertTrue(public["omitted"])

        with self.assertRaises(InspectionError):
            InspectionProjection(evidence_ids=frozenset({"source-1"}))
        exact = inspect_decision(
            result,
            store,
            candidate_set=candidates,
            projection=InspectionProjection.permitted_exact(
                evidence_ids=("source-1",),
                candidate_set_ids=("documents",),
                include_questions=True,
            ),
        ).to_dict()
        exact_json = json.dumps(exact)
        self.assertIn("PRIVATE EVIDENCE", exact_json)
        self.assertIn("PRIVATE CANDIDATE", exact_json)
        self.assertIn("PRIVATE QUESTION", exact_json)

        serialized = serialize_decision_result(result)
        self.assertEqual(serialized["answer"]["choice"], "doc-1")
        self.assertEqual(serialized["usage"]["coverage"], "complete")
        private_reason = replace(
            result,
            acceptance=replace(acceptance, reasons=("CREDENTIAL_SECRET",)),
        )
        self.assertEqual(
            serialize_decision_result(private_reason)["acceptance"]["reasons"],
            ["private_reason_omitted"],
        )

    async def test_hostile_failures_and_sink_errors_do_not_leak(self) -> None:
        judgment, inputs, store, _ = fixture()

        def hostile_sink(event: Mapping[str, Any]) -> None:
            raise RuntimeError("SINK_EXCEPTION_SECRET")

        client = DecisionClient(ExplodingProvider(), model="requested-model")
        context = DecisionContext(
            "tenant-a",
            100.0,
            limits(),
            host_dependencies={"password": "HOST_DEPENDENCY_SECRET"},
            authority_context={"authorization": "AUTHORIZATION_SECRET"},
            clock=lambda: 0.0,
            event_sink=hostile_sink,
            evidence_session=store,
        )

        with self.assertRaisesRegex(ProviderError, "HOSTILE_EXCEPTION_SECRET"):
            await client.evaluate(judgment, inputs, context)

        exposed = json.dumps([event.to_dict() for event in client.events])
        for secret in (
            "HOSTILE_EXCEPTION_SECRET",
            "SINK_EXCEPTION_SECRET",
            "HOST_DEPENDENCY_SECRET",
            "AUTHORIZATION_SECRET",
        ):
            self.assertNotIn(secret, exposed)
        failure = client.events[-1]
        self.assertIs(failure.kind, EventKind.OPERATION_FAILED)
        self.assertEqual(failure.reason_code, "provider_failure")
        self.assertEqual(failure.data["diagnostic"]["definition_id"], judgment.id)
        self.assertEqual(
            failure.data["diagnostic"]["source_path"], ["judgments", judgment.id]
        )

    async def test_cancellation_is_recorded_then_propagated(self) -> None:
        judgment, inputs, store, _ = fixture()
        provider = BlockingProvider()
        client = DecisionClient(provider, model="requested-model")
        context = DecisionContext(
            "tenant-a",
            100.0,
            limits(),
            clock=lambda: 0.0,
            evidence_session=store,
        )

        task = asyncio.create_task(client.evaluate(judgment, inputs, context))
        await provider.started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertIs(client.events[-1].kind, EventKind.OPERATION_CANCELLED)
        self.assertEqual(client.events[-1].reason_code, "cancelled")
        self.assertEqual(client.events[-1].data["diagnostic"]["code"], "cancelled")

    def test_semantic_diagnostic_names_correction_without_private_detail(self) -> None:
        unresolved = Unresolved(
            UnresolvedReason.INCOMPLETE_COVERAGE,
            ("request",),
            "PRIVATE UNCERTAINTY DETAIL",
            needed="expand-documents",
        )
        diagnostic = diagnostic_for_unresolved(
            unresolved,
            definition_id="choose_document",
            node_id="question-1",
            source_path=("candidate_sets", "documents"),
        ).to_dict()

        self.assertEqual(diagnostic["category"], DiagnosticCategory.SEMANTIC.value)
        self.assertEqual(diagnostic["code"], "incomplete_coverage")
        self.assertEqual(diagnostic["capability_id"], "expand-documents")
        self.assertNotIn("PRIVATE UNCERTAINTY DETAIL", json.dumps(diagnostic))


if __name__ == "__main__":
    unittest.main()
