import asyncio
import inspect
import unittest
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from jev_frame import (
    AgentDefinition,
    AttemptAdmission,
    AttemptStatus,
    Candidate,
    CandidateSet,
    ChoiceAnswer,
    CompiledQuestion,
    CompletionContract,
    Coverage,
    DocumentEvidencePackage,
    DocumentEvidenceRequest,
    DocumentEvidenceResult,
    DocumentRecord,
    EventKind,
    EvidenceStore,
    Judgment,
    ModelJudgment,
    NoulAnswer,
    NoulQuestion,
    Observation,
    OperatingPolicy,
    ProviderAttempt,
    ProviderBatch,
    ProviderDispatchError,
    RunContext,
    RunLimits,
    Runtime,
    RuntimeConfigurationError,
    Subject,
    TaskInputBinding,
    TerminalStatus,
    Tool,
    UnresolvedReason,
    Usage,
    UsageCoverage,
    bind_document_evidence_package,
)

CATALOG_A = {
    "a-1": DocumentRecord("a-1", "Alpha supports the claim exactly.", "a-v1"),
}
CATALOG_B = {
    "b-1": DocumentRecord("b-1", "Beta supports the other claim exactly.", "b-v1"),
}


def retrieve_documents(
    query: str, scope: str, documents: Mapping[str, DocumentRecord]
) -> CandidateSet:
    return CandidateSet(
        "documents",
        "1.0.0",
        tuple(
            Candidate(key, key, f"Document for {query}", "synthetic", value.version)
            for key, value in documents.items()
        ),
        Coverage.COMPLETE,
        scope,
    )


def read_document(
    document_id: str, documents: Mapping[str, DocumentRecord]
) -> DocumentRecord:
    return documents[document_id]


def accept_document(value: Any, store: EvidenceStore) -> bool:
    return (
        isinstance(value, DocumentEvidenceResult)
        and value.assessment.probability_yes >= 0.5
        and store.is_current("document_excerpt")
    )


def accept_any(value: Any, store: EvidenceStore) -> bool:
    return True


def bound_package() -> DocumentEvidencePackage:
    return bind_document_evidence_package(
        retrieve_documents=retrieve_documents,
        read_document=read_document,
    )


def document_definition(
    identifier: str, package: DocumentEvidencePackage
) -> AgentDefinition[DocumentEvidenceRequest, DocumentEvidenceResult]:
    return AgentDefinition(
        identifier,
        "1.0.0",
        "Select a document and assess its exact source text.",
        package.input_type,
        package.output_type,
        package.completion("application-policy"),
        OperatingPolicy("1.0.0", ("application-policy",)),
        packages=(package.capabilities,),
    )


def run_limits(*, provider_attempts: int = 20, tool_attempts: int = 20) -> RunLimits:
    return RunLimits(
        provider_attempts,
        provider_attempts,
        tool_attempts,
        0,
        4,
        0,
        0,
        0,
        0,
        0,
    )


class ScriptedRuntimeProvider:
    def __init__(
        self,
        *,
        block_judgment: str | None = None,
        fail: bool = False,
        delay: float = 0.0,
    ) -> None:
        self.block_judgment = block_judgment
        self.fail = fail
        self.delay = delay
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.judgments: list[str] = []
        self.batch_sizes: list[int] = []
        self.states: list[Mapping[str, Any]] = []
        self.active = 0
        self.max_active = 0

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
            admitted = admit_attempt(attempt)
            if inspect.isawaitable(admitted):
                await admitted
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        question = questions[0]
        self.judgments.append(question.judgment_id)
        self.batch_sizes.append(len(questions))
        self.states.append(state)
        try:
            if self.block_judgment == question.judgment_id:
                self.started.set()
                await self.release.wait()
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.fail:
                failed = ProviderAttempt(
                    attempt.id, 1, AttemptStatus.FAILED, code="unavailable"
                )
                raise ProviderDispatchError("unavailable", (failed,))
            answer: ChoiceAnswer | NoulAnswer
            if question.primitive == "choice":
                selected = question.options[0].key
                answer = ChoiceAnswer(
                    selected,
                    {
                        option.key: 1.0 if option.key == selected else 0.0
                        for option in question.options
                    },
                    1.0,
                )
            else:
                answer = NoulAnswer(0.9)
            finished = ProviderAttempt(
                attempt.id, 1, AttemptStatus.SUCCEEDED, request_id=operation_id
            )
            return ProviderBatch(
                {question.routing_id: answer},
                requested_model,
                "scripted",
                operation_id,
                Usage(UsageCoverage.COMPLETE, 5, 1, 1, 1),
                (finished,),
            )
        finally:
            self.active -= 1


@dataclass(frozen=True, slots=True)
class BranchRequest:
    topic: str


@dataclass(frozen=True, slots=True)
class BranchResult:
    required: NoulAnswer


@dataclass(frozen=True, slots=True)
class ParallelResult:
    first: NoulAnswer
    second: NoulAnswer


def parallel_definition() -> AgentDefinition[BranchRequest, ParallelResult]:
    judgments = tuple(
        Judgment(
            identifier,
            "1.0.0",
            NoulQuestion(f"Is {identifier} supported?"),
            (Subject("topic"),),
        )
        for identifier in ("first", "second")
    )
    return AgentDefinition(
        "parallel_agent",
        "1.0.0",
        "Assess two independent questions over one authorized view.",
        BranchRequest,
        ParallelResult,
        completion=CompletionContract(
            tuple(item.id for item in judgments),
            {item.id: item.id for item in judgments},
            "application-policy",
        ),
        policy=OperatingPolicy("1.0.0", ("application-policy",)),
        judgments=judgments,
    )


def inactive_definition() -> AgentDefinition[BranchRequest, BranchResult]:
    judgment = Judgment(
        "inactive_requirement",
        "1.0.0",
        NoulQuestion("Is the inactive requirement supported?"),
        (Subject("topic"),),
        applicability="never",
    )
    return AgentDefinition(
        "inactive_agent",
        "1.0.0",
        "Do not complete from an inactive speculative branch.",
        BranchRequest,
        BranchResult,
        completion=CompletionContract(
            (judgment.id,), {"required": judgment.id}, "application-policy"
        ),
        policy=OperatingPolicy("1.0.0", ("application-policy",)),
        judgments=(judgment,),
    )


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_completion_requires_current_findings_before_and_after_policy(
        self,
    ) -> None:
        @dataclass(frozen=True, slots=True)
        class Request:
            text: str

        started = asyncio.Event()
        release = asyncio.Event()

        async def derive(text: str) -> str:
            started.set()
            await release.wait()
            return text.upper()

        tool = Tool(
            "derive",
            "1.0.0",
            "Derive a result from current evidence.",
            derive,
            {"text": TaskInputBinding(("text",))},
            requires_evidence=("source",),
            produces_evidence=("result",),
        )
        definition: AgentDefinition[Request, str] = AgentDefinition(
            "stale-completion",
            "1.0.0",
            "Reject stale required findings.",
            Request,
            str,
            CompletionContract(("result",), {}, "application-policy"),
            OperatingPolicy("1.0.0", ("application-policy",)),
            tools=(tool,),
        )
        store = EvidenceStore(lambda: 0.0)
        store.add(
            Observation(
                id="source",
                value="current",
                source_id="fixture",
                scope="fixture",
                observed_at=0.0,
            )
        )
        store.add(
            Observation(
                id="independent",
                value="still current",
                source_id="fixture",
                scope="fixture",
                observed_at=0.0,
            )
        )
        runtime = Runtime(
            ScriptedRuntimeProvider(),
            model="unused",
            completion_checks={"application-policy": accept_any},
        )
        task = asyncio.create_task(
            runtime.run(
                definition,
                Request("secret"),
                RunContext(
                    "fixture",
                    100.0,
                    run_limits(provider_attempts=0, tool_attempts=1),
                    clock=lambda: 0.0,
                    evidence_session=store,
                    run_id="stale-read",
                ),
            )
        )
        await started.wait()
        store.invalidate("source")
        release.set()

        result = await task

        self.assertIs(result.status, TerminalStatus.UNRESOLVED)
        self.assertIs(result.unresolved[0].reason, UnresolvedReason.STALE_SOURCE)
        self.assertFalse(store.is_current("result"))
        self.assertTrue(store.is_current("independent"))

        check_started = asyncio.Event()
        check_release = asyncio.Event()

        async def completion_check(value: Any, evidence: EvidenceStore) -> bool:
            check_started.set()
            await check_release.wait()
            return True

        second_store = EvidenceStore(lambda: 0.0)
        second_store.add(
            Observation(
                id="source",
                value="current",
                source_id="fixture",
                scope="fixture",
                observed_at=0.0,
            )
        )
        second_runtime = Runtime(
            ScriptedRuntimeProvider(),
            model="unused",
            completion_checks={"application-policy": completion_check},
        )
        second = asyncio.create_task(
            second_runtime.run(
                definition,
                Request("secret"),
                RunContext(
                    "fixture",
                    100.0,
                    run_limits(provider_attempts=0, tool_attempts=1),
                    clock=lambda: 0.0,
                    evidence_session=second_store,
                    run_id="stale-policy",
                ),
            )
        )
        await check_started.wait()
        second_store.invalidate("source")
        check_release.set()
        checked = await second

        self.assertIs(checked.status, TerminalStatus.UNRESOLVED)
        self.assertIs(checked.unresolved[0].reason, UnresolvedReason.STALE_SOURCE)

    async def test_independent_ready_judgments_share_no_answers(self) -> None:
        provider = ScriptedRuntimeProvider(delay=0.01)
        runtime = Runtime(
            provider,
            model="scripted",
            completion_checks={"application-policy": accept_any},
        )

        result = await runtime.run(
            parallel_definition(),
            BranchRequest("fixture"),
            RunContext(
                "fixture",
                100.0,
                run_limits(tool_attempts=0),
                clock=lambda: 0.0,
                run_id="parallel",
            ),
        )

        self.assertIs(result.status, TerminalStatus.COMPLETED)
        self.assertEqual(set(provider.judgments), {"first", "second"})
        self.assertGreaterEqual(provider.max_active, 2)
        self.assertTrue(
            all(set(state["subjects"]) == {"topic"} for state in provider.states)
        )

    async def test_scenario_a_completes_with_exact_source_and_separate_calls(
        self,
    ) -> None:
        package = bound_package()
        provider = ScriptedRuntimeProvider()
        runtime = Runtime(
            provider,
            model="scripted",
            completion_checks={"application-policy": accept_document},
        )
        context = RunContext(
            "fixture",
            100.0,
            run_limits(),
            host_dependencies={"documents": CATALOG_A},
            clock=lambda: 0.0,
            run_id="scenario-a",
        )

        result = await runtime.run(
            document_definition("document_agent", package),
            DocumentEvidenceRequest("alpha", "Alpha supports the claim exactly."),
            context,
        )

        self.assertIs(result.status, TerminalStatus.COMPLETED)
        self.assertIsInstance(result.value, DocumentEvidenceResult)
        value = cast(DocumentEvidenceResult, result.value)
        self.assertEqual(value.excerpt, CATALOG_A["a-1"].text)
        self.assertEqual(
            provider.judgments, ["select_document", "assess_document_support"]
        )
        self.assertEqual(provider.batch_sizes, [1, 1])
        self.assertIn("document_excerpt", result.evidence_refs)
        self.assertTrue(
            any(ref.endswith(":accept:select_document") for ref in result.evidence_refs)
        )
        self.assertEqual(result.usage.provider_attempts, 2)

    async def test_concurrent_definitions_isolate_state_and_share_limits(self) -> None:
        package = bound_package()
        provider = ScriptedRuntimeProvider(delay=0.01)
        runtime = Runtime(
            provider,
            model="scripted",
            completion_checks={"application-policy": accept_document},
        )
        limits = run_limits()
        contexts = (
            RunContext(
                "fixture",
                100.0,
                limits,
                host_dependencies={"documents": CATALOG_A},
                clock=lambda: 0.0,
                run_id="run-a",
            ),
            RunContext(
                "fixture",
                100.0,
                limits,
                host_dependencies={"documents": CATALOG_B},
                clock=lambda: 0.0,
                run_id="run-b",
            ),
        )

        first, second = await asyncio.gather(
            runtime.run(
                document_definition("agent-a", package),
                DocumentEvidenceRequest("alpha", "Alpha supports the claim exactly."),
                contexts[0],
            ),
            runtime.run(
                document_definition("agent-b", package),
                DocumentEvidenceRequest(
                    "beta", "Beta supports the other claim exactly."
                ),
                contexts[1],
            ),
        )

        first_value = cast(DocumentEvidenceResult, first.value)
        second_value = cast(DocumentEvidenceResult, second.value)
        self.assertEqual(first_value.excerpt, CATALOG_A["a-1"].text)
        self.assertEqual(second_value.excerpt, CATALOG_B["b-1"].text)
        self.assertGreaterEqual(provider.max_active, 2)
        snapshot = await runtime.ledger.snapshot()  # type: ignore[union-attr]
        self.assertEqual(snapshot.provider_attempts, 4)
        self.assertEqual(snapshot.tool_attempts, 6)
        self.assertEqual({event.run_id for event in runtime.events}, {"run-a", "run-b"})

    async def test_inactive_branch_and_missing_completion_policy_are_unresolved(
        self,
    ) -> None:
        provider = ScriptedRuntimeProvider()
        runtime = Runtime(
            provider,
            model="scripted",
            completion_checks={"application-policy": accept_any},
            applicability_checks={"never": lambda findings: False},
        )
        inactive = await runtime.run(
            inactive_definition(),
            BranchRequest("fixture"),
            RunContext(
                "fixture",
                100.0,
                run_limits(tool_attempts=0),
                clock=lambda: 0.0,
                run_id="inactive",
            ),
        )

        self.assertIs(inactive.status, TerminalStatus.UNRESOLVED)
        self.assertIs(inactive.unresolved[0].reason, UnresolvedReason.NO_PROGRESS)
        self.assertFalse(provider.judgments)

        package = bound_package()
        unsupported_runtime = Runtime(
            ScriptedRuntimeProvider(), model="scripted", completion_checks={}
        )
        unsupported = await unsupported_runtime.run(
            document_definition("unsupported", package),
            DocumentEvidenceRequest("alpha", "claim"),
            RunContext(
                "fixture",
                100.0,
                run_limits(),
                host_dependencies={"documents": CATALOG_A},
                clock=lambda: 0.0,
                run_id="unsupported",
            ),
        )
        self.assertIs(unsupported.status, TerminalStatus.UNRESOLVED)
        self.assertIs(
            unsupported.unresolved[0].reason,
            UnresolvedReason.UNACCEPTED_JUDGMENT,
        )

    async def test_stale_inflight_answer_is_historical_not_accepted(self) -> None:
        package = bound_package()
        provider = ScriptedRuntimeProvider(block_judgment="assess_document_support")
        runtime = Runtime(
            provider,
            model="scripted",
            completion_checks={"application-policy": accept_document},
        )
        store = EvidenceStore(lambda: 0.0)
        task = asyncio.create_task(
            runtime.run(
                document_definition("stale-agent", package),
                DocumentEvidenceRequest("alpha", "claim"),
                RunContext(
                    "fixture",
                    100.0,
                    run_limits(),
                    host_dependencies={"documents": CATALOG_A},
                    clock=lambda: 0.0,
                    evidence_session=store,
                    run_id="stale-run",
                ),
            )
        )
        await provider.started.wait()
        store.invalidate("document_excerpt")
        provider.release.set()

        result = await task

        self.assertIs(result.status, TerminalStatus.UNRESOLVED)
        self.assertIs(result.unresolved[0].reason, UnresolvedReason.STALE_SOURCE)
        late = store.get("stale-run:judge:assess_document_support:judgment")
        self.assertIsInstance(late, ModelJudgment)
        self.assertFalse(store.is_current(late.id))
        self.assertEqual(result.usage.provider_attempts, 2)

    async def test_exhaustion_cancellation_and_service_failure_are_distinct(
        self,
    ) -> None:
        package = bound_package()
        definition = document_definition("failure-agent", package)
        request = DocumentEvidenceRequest("alpha", "claim")

        exhausted_runtime = Runtime(
            ScriptedRuntimeProvider(),
            model="scripted",
            completion_checks={"application-policy": accept_document},
        )
        exhausted = await exhausted_runtime.run(
            definition,
            request,
            RunContext(
                "fixture",
                100.0,
                run_limits(tool_attempts=0),
                host_dependencies={"documents": CATALOG_A},
                clock=lambda: 0.0,
                run_id="exhausted",
            ),
        )
        self.assertIs(exhausted.status, TerminalStatus.UNRESOLVED)
        self.assertIs(
            exhausted.unresolved[0].reason, UnresolvedReason.BUDGET_EXHAUSTION
        )
        self.assertTrue(
            any(
                event.kind is EventKind.OPERATION_UNRESOLVED
                for event in exhausted_runtime.events
            )
        )

        failing_runtime = Runtime(
            ScriptedRuntimeProvider(fail=True),
            model="scripted",
            completion_checks={"application-policy": accept_document},
        )
        failed = await failing_runtime.run(
            definition,
            request,
            RunContext(
                "fixture",
                100.0,
                run_limits(),
                host_dependencies={"documents": CATALOG_A},
                clock=lambda: 0.0,
                run_id="failed",
            ),
        )
        self.assertIs(failed.status, TerminalStatus.FAILED)
        self.assertEqual(failed.failure, "provider_failure")

        blocking_provider = ScriptedRuntimeProvider(block_judgment="select_document")
        cancelled_runtime = Runtime(
            blocking_provider,
            model="scripted",
            completion_checks={"application-policy": accept_document},
        )
        cancelled_task = asyncio.create_task(
            cancelled_runtime.run(
                definition,
                request,
                RunContext(
                    "fixture",
                    100.0,
                    run_limits(),
                    host_dependencies={"documents": CATALOG_A},
                    clock=lambda: 0.0,
                    run_id="cancelled",
                ),
            )
        )
        await blocking_provider.started.wait()
        cancelled_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await cancelled_task
        cancelled = cancelled_runtime.result_for("cancelled")
        self.assertIsNotNone(cancelled)
        self.assertIs(cancelled.status, TerminalStatus.CANCELLED)  # type: ignore[union-attr]

    async def test_sync_wrapper_rejects_an_existing_event_loop(self) -> None:
        package = bound_package()
        runtime = Runtime(
            ScriptedRuntimeProvider(),
            model="scripted",
            completion_checks={"application-policy": accept_document},
        )
        with self.assertRaises(RuntimeConfigurationError):
            runtime.run_sync(
                document_definition("sync-agent", package),
                DocumentEvidenceRequest("alpha", "claim"),
                RunContext(
                    "fixture",
                    100.0,
                    run_limits(),
                    host_dependencies={"documents": CATALOG_A},
                    clock=lambda: 0.0,
                    run_id="sync-loop",
                ),
            )


class RuntimeSyncTests(unittest.TestCase):
    def test_sync_wrapper_runs_outside_an_event_loop(self) -> None:
        package = bound_package()
        runtime = Runtime(
            ScriptedRuntimeProvider(),
            model="scripted",
            completion_checks={"application-policy": accept_document},
        )

        result = runtime.run_sync(
            document_definition("sync-agent", package),
            DocumentEvidenceRequest("alpha", "claim"),
            RunContext(
                "fixture",
                100.0,
                run_limits(),
                host_dependencies={"documents": CATALOG_A},
                clock=lambda: 0.0,
                run_id="sync-run",
            ),
        )

        self.assertIs(result.status, TerminalStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
