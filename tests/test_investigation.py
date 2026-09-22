import asyncio
import unittest
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, cast

from jev_frame import (
    NO_FIT_KEY,
    AgentDefinition,
    AttemptAdmission,
    AttemptStatus,
    Candidate,
    CandidateBinding,
    CandidateProvider,
    CandidateSet,
    ChoiceAnswer,
    ChoiceQuestion,
    ClarificationRequest,
    CompiledQuestion,
    CompletionContract,
    Coverage,
    EvidenceStore,
    HostContextBinding,
    InvestigationAction,
    InvestigationNeed,
    InvestigationResult,
    Judgment,
    NoulAnswer,
    NoulQuestion,
    Observation,
    OperatingPolicy,
    ProviderAttempt,
    ProviderBatch,
    RunContext,
    RunLimits,
    Runtime,
    Subject,
    TaskInputBinding,
    TerminalStatus,
    Tool,
    ToolEffect,
    UnresolvedReason,
    Usage,
    UsageCoverage,
)


@dataclass(frozen=True, slots=True)
class SearchRequest:
    query: str


@dataclass(frozen=True, slots=True)
class SearchResult:
    selection: ChoiceAnswer
    text: str
    unrelated: NoulAnswer


@dataclass(frozen=True, slots=True)
class ClarifiedRequest:
    topic: str
    region: str


@dataclass(frozen=True, slots=True)
class ClarifiedResult:
    answer: NoulAnswer


CATALOG = {"bad": "irrelevant", "target": "exact target evidence"}


def retrieve(query: str, scope: str) -> CandidateSet:
    return CandidateSet(
        "documents",
        "1.0.0",
        (Candidate("bad", "bad", "irrelevant document", "fixture", "v1"),),
        Coverage.TRUNCATED,
        scope,
        query=query,
        expansion_ref="expand-documents",
    )


def retrieve_complete(query: str, scope: str) -> CandidateSet:
    return CandidateSet(
        "documents",
        "1.0.0",
        (Candidate("bad", "bad", "irrelevant document", "fixture", "v1"),),
        Coverage.COMPLETE,
        scope,
        query=query,
    )


def read_document(document_id: str, catalog: Mapping[str, str]) -> str:
    return catalog[document_id]


class InvestigatingProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

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
            if asyncio.iscoroutine(admitted):
                await admitted
        question = questions[0]
        self.calls.append(question.judgment_id)
        if question.primitive == "choice":
            keys = [option.key for option in question.options]
            choice = "target" if "target" in keys else NO_FIT_KEY
            answer: ChoiceAnswer | NoulAnswer = ChoiceAnswer(
                choice,
                {key: 1.0 if key == choice else 0.0 for key in keys},
                1.0,
            )
        else:
            answer = NoulAnswer(0.8)
        return ProviderBatch(
            {question.routing_id: answer},
            requested_model,
            "scripted",
            operation_id,
            Usage(UsageCoverage.COMPLETE, 1, 1, 1, 1),
            (
                ProviderAttempt(
                    attempt.id,
                    1,
                    AttemptStatus.SUCCEEDED,
                    request_id=operation_id,
                ),
            ),
        )


def search_definition() -> AgentDefinition[SearchRequest, SearchResult]:
    choose = Judgment(
        "choose_document",
        "1.0.0",
        ChoiceQuestion("Which document answers the query?"),
        (Subject("query"),),
        candidate_set="documents",
    )
    unrelated = Judgment(
        "unrelated_check",
        "1.0.0",
        NoulQuestion("Is this an unrelated stable check?"),
        (Subject("query"),),
    )
    read = Tool(
        "read_document",
        "1.0.0",
        "Read the selected synthetic document.",
        read_document,
        {
            "document_id": CandidateBinding("documents", "choose_document"),
            "catalog": HostContextBinding("catalog"),
        },
        effect=ToolEffect.READ,
        produces_evidence=("document_text",),
    )
    provider = CandidateProvider(
        "documents",
        "1.0.0",
        retrieve,
        {
            "query": TaskInputBinding(("query",)),
            "scope": HostContextBinding("scope"),
        },
    )
    return AgentDefinition(
        "search_agent",
        "1.0.0",
        "Expand a truncated search only when the first selection has no fit.",
        SearchRequest,
        SearchResult,
        CompletionContract(
            ("choose_document", "document_text", "unrelated_check"),
            {
                "selection": "choose_document",
                "text": "document_text",
                "unrelated": "unrelated_check",
            },
            "completion",
        ),
        OperatingPolicy("1.0.0", ("completion",)),
        tools=(read,),
        judgments=(choose, unrelated),
        candidate_providers=(provider,),
    )


def complete_no_fit_definition() -> AgentDefinition[SearchRequest, SearchResult]:
    definition = search_definition()
    return replace(
        definition,
        candidate_providers=(
            CandidateProvider(
                "documents",
                "1.0.0",
                retrieve_complete,
                {
                    "query": TaskInputBinding(("query",)),
                    "scope": HostContextBinding("scope"),
                },
            ),
        ),
    )


def clarified_definition() -> AgentDefinition[ClarifiedRequest, ClarifiedResult]:
    judgment = Judgment(
        "regional_answer",
        "1.0.0",
        NoulQuestion("Is the topic applicable in the supplied region?"),
        (Subject("region"),),
    )
    return AgentDefinition(
        "clarified_agent",
        "1.0.0",
        "Require a region before evaluation.",
        ClarifiedRequest,
        ClarifiedResult,
        CompletionContract(
            ("regional_answer",), {"answer": "regional_answer"}, "completion"
        ),
        OperatingPolicy("1.0.0", ("completion",)),
        judgments=(judgment,),
    )


def run_limits(*, investigation_steps: int = 2) -> RunLimits:
    return RunLimits(8, 8, 8, investigation_steps, 4, 0, 0, 0, 0, 0)


def context(
    run_id: str,
    *,
    store: EvidenceStore | None = None,
    investigation_steps: int = 2,
    parent: str | None = None,
) -> RunContext:
    return RunContext(
        "fixture",
        100.0,
        run_limits(investigation_steps=investigation_steps),
        host_dependencies={"catalog": CATALOG},
        evidence_session=store,
        clock=lambda: 0.0,
        run_id=run_id,
        parent_operation_id=parent,
    )


class InvestigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_expansion_rechecks_only_selection_and_preserves_conflict(
        self,
    ) -> None:
        provider = InvestigatingProvider()
        store = EvidenceStore(lambda: 0.0)
        store.add(
            Observation(
                id="source-a",
                value="original claim",
                source_id="fixture:a",
                scope="fixture",
                observed_at=0.0,
                source_version="v1",
            )
        )
        action_calls: list[InvestigationNeed] = []

        def expand(need: InvestigationNeed) -> InvestigationResult:
            action_calls.append(need)
            return InvestigationResult(
                CandidateSet(
                    "documents",
                    "2.0.0",
                    (
                        Candidate("bad", "bad", "irrelevant document", "fixture", "v1"),
                        Candidate(
                            "target",
                            "target",
                            "target document",
                            "fixture",
                            "v2",
                        ),
                    ),
                    Coverage.COMPLETE,
                    "fixture",
                    query="target",
                ),
                evidence=(
                    Observation(
                        id="source-b",
                        value="contradictory claim",
                        source_id="fixture:b",
                        scope="fixture",
                        observed_at=0.0,
                        source_version="v1",
                        conflicts_with=("source-a",),
                    ),
                ),
            )

        runtime = Runtime(
            provider,
            model="scripted",
            completion_checks={"completion": lambda value, evidence: True},
            investigation_actions=(
                InvestigationAction(
                    "expand-documents",
                    (UnresolvedReason.INCOMPLETE_COVERAGE,),
                    expand,
                    handles=("expand-documents",),
                    priority=1,
                ),
            ),
        )

        result = await runtime.run(
            search_definition(),
            SearchRequest("target"),
            context("expanded", store=store),
        )

        self.assertIs(result.status, TerminalStatus.COMPLETED)
        self.assertEqual(cast(SearchResult, result.value).text, CATALOG["target"])
        self.assertEqual(provider.calls.count("choose_document"), 2)
        self.assertEqual(provider.calls.count("unrelated_check"), 1)
        self.assertEqual(len(action_calls), 1)
        self.assertEqual(result.usage.provider_attempts, 3)
        self.assertEqual(result.usage.submitted_questions, 3)
        self.assertEqual(result.usage.input_tokens, 3)
        self.assertEqual(result.usage.output_tokens, 3)
        projected = {
            record.id for record in store.project(("source-b",), scope="fixture")
        }
        self.assertEqual(projected, {"source-a", "source-b"})

    async def test_unchanged_expansion_stops_with_no_progress(self) -> None:
        provider = InvestigatingProvider()

        def unchanged(need: InvestigationNeed) -> InvestigationResult:
            assert need.candidate_set is not None
            return InvestigationResult(candidate_set=need.candidate_set)

        runtime = Runtime(
            provider,
            model="scripted",
            completion_checks={"completion": lambda value, evidence: True},
            investigation_actions=(
                InvestigationAction(
                    "expand-documents",
                    (UnresolvedReason.INCOMPLETE_COVERAGE,),
                    unchanged,
                    handles=("expand-documents",),
                ),
            ),
        )

        result = await runtime.run(
            search_definition(), SearchRequest("target"), context("unchanged")
        )

        self.assertIs(result.status, TerminalStatus.UNRESOLVED)
        self.assertIs(result.unresolved[0].reason, UnresolvedReason.NO_PROGRESS)
        self.assertEqual(provider.calls.count("choose_document"), 1)
        self.assertEqual(result.usage.provider_attempts, 2)
        self.assertEqual(result.usage.submitted_questions, 2)

    async def test_complete_no_fit_preserves_usage(self) -> None:
        provider = InvestigatingProvider()
        runtime = Runtime(
            provider,
            model="scripted",
            completion_checks={"completion": lambda value, evidence: True},
        )

        result = await runtime.run(
            complete_no_fit_definition(),
            SearchRequest("target"),
            context("complete-no-fit"),
        )

        self.assertIs(result.status, TerminalStatus.UNRESOLVED)
        self.assertIs(result.unresolved[0].reason, UnresolvedReason.REFUTED_CLAIM)
        self.assertEqual(provider.calls.count("choose_document"), 1)
        self.assertEqual(result.usage.provider_attempts, 2)
        self.assertEqual(result.usage.submitted_questions, 2)
        self.assertEqual(result.usage.input_tokens, 2)
        self.assertEqual(result.usage.output_tokens, 2)

    async def test_failed_investigation_preserves_prior_selection_usage(self) -> None:
        provider = InvestigatingProvider()

        def fail(_: InvestigationNeed) -> InvestigationResult:
            raise RuntimeError("synthetic expansion failure")

        runtime = Runtime(
            provider,
            model="scripted",
            completion_checks={"completion": lambda value, evidence: True},
            investigation_actions=(
                InvestigationAction(
                    "expand-documents",
                    (UnresolvedReason.INCOMPLETE_COVERAGE,),
                    fail,
                    handles=("expand-documents",),
                ),
            ),
        )

        result = await runtime.run(
            search_definition(),
            SearchRequest("target"),
            context("failed-expansion"),
        )

        self.assertIs(result.status, TerminalStatus.FAILED)
        self.assertEqual(provider.calls.count("choose_document"), 1)
        self.assertEqual(result.usage.provider_attempts, 2)
        self.assertEqual(result.usage.submitted_questions, 2)

    async def test_no_action_exhaustion_and_scope_denial_are_distinct(self) -> None:
        cases = (
            (
                "no-action",
                (),
                2,
                UnresolvedReason.INCOMPLETE_COVERAGE,
            ),
            (
                "exhausted",
                (
                    InvestigationAction(
                        "expand-documents",
                        (UnresolvedReason.INCOMPLETE_COVERAGE,),
                        lambda need: InvestigationResult(
                            candidate_set=need.candidate_set
                        ),
                        handles=("expand-documents",),
                    ),
                ),
                0,
                UnresolvedReason.BUDGET_EXHAUSTION,
            ),
            (
                "denied-scope",
                (
                    InvestigationAction(
                        "expand-documents",
                        (UnresolvedReason.INCOMPLETE_COVERAGE,),
                        lambda need: InvestigationResult(
                            candidate_set=need.candidate_set
                        ),
                        handles=("expand-documents",),
                        scopes=("other",),
                    ),
                ),
                2,
                UnresolvedReason.PERMISSION_DENIAL,
            ),
        )
        for run_id, actions, steps, expected in cases:
            with self.subTest(run_id=run_id):
                runtime = Runtime(
                    InvestigatingProvider(),
                    model="scripted",
                    completion_checks={"completion": lambda value, evidence: True},
                    investigation_actions=actions,
                )
                result = await runtime.run(
                    search_definition(),
                    SearchRequest("target"),
                    context(run_id, investigation_steps=steps),
                )
                self.assertIs(result.status, TerminalStatus.UNRESOLVED)
                self.assertIs(result.unresolved[0].reason, expected)
                self.assertEqual(result.usage.provider_attempts, 2)
                self.assertEqual(result.usage.submitted_questions, 2)

    async def test_typed_clarification_allows_a_linked_fresh_run(self) -> None:
        provider = InvestigatingProvider()
        request = ClarificationRequest(
            "region",
            ("topic",),
            ("region",),
            str,
            "Which region should be evaluated?",
            "clarified_agent",
        )
        runtime = Runtime(
            provider,
            model="scripted",
            completion_checks={"completion": lambda value, evidence: True},
            clarifications=(request,),
        )

        missing = await runtime.run(
            clarified_definition(),
            cast(ClarifiedRequest, {"topic": "fixture"}),
            context("clarification", investigation_steps=0),
        )

        self.assertIs(missing.status, TerminalStatus.UNRESOLVED)
        self.assertEqual(missing.clarifications, (request,))
        answer = request.validate_answer("us-east")
        completed = await runtime.run(
            clarified_definition(),
            ClarifiedRequest("fixture", answer),
            context(
                "clarification-linked",
                investigation_steps=0,
                parent="clarification:run",
            ),
        )
        self.assertIs(completed.status, TerminalStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
