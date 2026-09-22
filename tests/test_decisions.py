import asyncio
import inspect
import unittest
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from jev_frame import (
    NO_FIT_KEY,
    AttemptAdmission,
    AttemptStatus,
    BudgetExhaustedError,
    Candidate,
    CandidateOutcome,
    CandidateSet,
    ChoiceAnswer,
    ChoiceQuestion,
    CompiledQuestion,
    Coverage,
    DecisionClient,
    DecisionContext,
    DecisionInputs,
    DecisionResult,
    EvidenceSelector,
    EvidenceStore,
    FilterVerdict,
    Judgment,
    ModelJudgment,
    NoulAnswer,
    NoulQuestion,
    Observation,
    ProviderAttempt,
    ProviderBatch,
    RunLimits,
    ScoreAnswer,
    ScoreQuestion,
    SourceField,
    SourceSpan,
    Subject,
    Usage,
    UsageCoverage,
    UsageLedger,
    UsageMeasurementKind,
)

Answerer = Callable[[CompiledQuestion, Mapping[str, Any], str], Any]


class ScriptedProvider:
    def __init__(self, answerer: Answerer) -> None:
        self.answerer = answerer
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
            if inspect.isawaitable(admitted):
                await admitted
        self.calls.append(operation_id)
        answers = {
            question.routing_id: self.answerer(question, state, operation_id)
            for question in questions
        }
        finished = ProviderAttempt(
            attempt.id, 1, AttemptStatus.SUCCEEDED, request_id=f"request:{operation_id}"
        )
        return ProviderBatch(
            answers,
            requested_model,
            "jev-scripted-1",
            finished.request_id,
            Usage(UsageCoverage.COMPLETE, 10, 2, 1, len(questions)),
            (finished,),
        )


def limits(
    *, attempts: int = 20, questions: int = 20, concurrency: int = 2
) -> RunLimits:
    return RunLimits(attempts, questions, 0, 0, concurrency, 0, 0, 0, 0, 0)


def context(
    run_limits: RunLimits | None = None, store: EvidenceStore | None = None
) -> DecisionContext:
    clock = lambda: 0.0
    return DecisionContext(
        "fixture",
        100.0,
        limits() if run_limits is None else run_limits,
        clock=clock,
        evidence_session=EvidenceStore(clock) if store is None else store,
    )


def catalog(
    candidates: tuple[Candidate, ...], coverage: Coverage = Coverage.COMPLETE
) -> CandidateSet:
    return CandidateSet(
        "documents",
        "1.0.0",
        candidates,
        coverage,
        "fixture",
        expansion_ref=("expand-documents" if coverage is Coverage.TRUNCATED else None),
    )


class DecisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_evaluate_and_assess_record_provenance_without_an_agent(self) -> None:
        provider = ScriptedProvider(lambda question, state, operation: NoulAnswer(0.91))
        store = EvidenceStore(lambda: 0.0)
        client = DecisionClient(provider, model="jev-test")
        judgment = Judgment(
            "supports",
            "1.0.0",
            NoulQuestion("Does the source support the claim?"),
            (Subject("claim"),),
            (EvidenceSelector("excerpt"),),
        )
        observation = Observation(
            id="source-1",
            value="A retained fixture excerpt.",
            source_id="fixture",
            scope="fixture",
            observed_at=0.0,
            source_version="v1",
        )
        first = DecisionInputs(
            "decision-1",
            {"claim": "Claim A"},
            {"excerpt": observation},
        )
        second = DecisionInputs(
            "decision-2",
            {"claim": "Claim B"},
            {"excerpt": observation},
        )
        third = DecisionInputs(
            "decision-3",
            {"claim": "Claim C"},
            {"excerpt": observation},
        )
        decision_context = context(store=store)

        result = await client.evaluate(judgment, first, decision_context)
        assessed = await client.assess(judgment, second, decision_context)
        portable = client.as_callable(judgment)
        wrapped = await portable(third, decision_context)

        self.assertIsInstance(result.answer, NoulAnswer)
        self.assertIsNone(result.acceptance)
        self.assertNotEqual(result.input_fingerprint, assessed.input_fingerprint)
        self.assertIsInstance(wrapped.answer, NoulAnswer)
        record = store.get("decision-1:judgment")
        self.assertIsInstance(record, ModelJudgment)
        assert isinstance(record, ModelJudgment)
        self.assertEqual(record.dependencies, ("source-1",))
        self.assertEqual(record.requested_model, "jev-test")
        snapshot = await client.ledger.snapshot()  # type: ignore[union-attr]
        self.assertEqual(snapshot.provider_attempts, 3)
        self.assertEqual(snapshot.submitted_questions, 3)
        self.assertEqual(
            [item.input_tokens for item in snapshot.measurements], [10, 10, 10]
        )

    async def test_select_preserves_zero_singleton_duplicate_and_no_fit(self) -> None:
        selected = {
            "single": "doc-1",
            "duplicate": "doc-2",
            "no-fit": NO_FIT_KEY,
        }
        provider = ScriptedProvider(
            lambda question, state, operation: ChoiceAnswer(
                selected[operation],
                {
                    option.key: (1.0 if option.key == selected[operation] else 0.0)
                    for option in question.options
                },
                1.0,
            )
        )
        client = DecisionClient(provider, model="jev-test")
        judgment = Judgment(
            "select_document",
            "1.0.0",
            ChoiceQuestion("Which document fits?"),
            (Subject("request"),),
            candidate_set="documents",
        )
        decision_context = context()

        empty = await client.select(
            judgment,
            DecisionInputs(
                "empty",
                {"request": "find"},
                candidate_sets={"documents": catalog(())},
            ),
            decision_context,
        )
        one = Candidate("doc-1", "value-1", "Same label", "fixture", "v1")
        two = Candidate("doc-2", "value-2", "Same label", "fixture", "v2")
        singleton = await client.select(
            judgment,
            DecisionInputs(
                "single",
                {"request": "find"},
                candidate_sets={"documents": catalog((one,))},
            ),
            decision_context,
        )
        duplicate = await client.select(
            judgment,
            DecisionInputs(
                "duplicate",
                {"request": "find"},
                candidate_sets={"documents": catalog((one, two))},
            ),
            decision_context,
        )
        no_fit = await client.select(
            judgment,
            DecisionInputs(
                "no-fit",
                {"request": "find"},
                candidate_sets={"documents": catalog((one, two), Coverage.TRUNCATED)},
            ),
            decision_context,
        )

        self.assertIs(empty.selection.outcome, CandidateOutcome.NO_FIT)  # type: ignore[union-attr]
        self.assertIsNone(empty.decision)
        self.assertNotIn("empty", provider.calls)
        self.assertEqual(singleton.selection.candidate.key, "doc-1")  # type: ignore[union-attr]
        self.assertEqual(duplicate.selection.candidate.key, "doc-2")  # type: ignore[union-attr]
        self.assertIs(no_fit.selection.outcome, CandidateOutcome.NO_FIT)  # type: ignore[union-attr]
        self.assertIsNotNone(no_fit.unresolved)
        self.assertEqual(no_fit.unresolved.needed, "expand-documents")  # type: ignore[union-attr]

    async def test_filter_score_and_exact_source_extraction(self) -> None:
        def answer(
            question: CompiledQuestion, state: Mapping[str, Any], operation: str
        ) -> Any:
            if question.primitive == "noul":
                return NoulAnswer(0.9 if state["subjects"]["item"] == "keep" else 0.1)
            return ScoreAnswer(1.7, ("low", "medium", "high"), (0.1, 0.1, 0.8), 0.9)

        provider = ScriptedProvider(answer)
        client = DecisionClient(provider, model="jev-test")
        decision_context = context()
        assessment = Judgment(
            "filter_item",
            "1.0.0",
            NoulQuestion("Should this item be kept?"),
            (Subject("item"),),
        )
        scored = Judgment(
            "score_item",
            "1.0.0",
            ScoreQuestion("Score this item.", ("low", "medium", "high")),
            (Subject("item"),),
        )

        filtered = await client.filter(
            assessment,
            (
                DecisionInputs("keep", {"item": "keep"}),
                DecisionInputs("drop", {"item": "drop"}),
            ),
            decision_context,
            classify=lambda value: value.probability_yes >= 0.5,
        )
        score = await client.score(
            scored,
            DecisionInputs("score", {"item": "fixture"}),
            decision_context,
        )
        source = Observation(
            id="unicode-source",
            value={"text": "A🙂BC"},
            source_id="fixture",
            scope="fixture",
            observed_at=0.0,
            source_version="v1",
        )
        field = await client.extract_source(
            source, SourceField(("text",)), decision_context
        )
        text_source = Observation(
            id="unicode-text",
            value="A🙂BC",
            source_id="fixture",
            scope="fixture",
            observed_at=0.0,
        )
        span = await client.extract_source(
            text_source, SourceSpan(1, 3), decision_context
        )

        self.assertEqual(
            [item.verdict for item in filtered],
            [FilterVerdict.ACCEPTED, FilterVerdict.REJECTED],
        )
        self.assertIsInstance(score.answer, ScoreAnswer)
        assert isinstance(score.answer, ScoreAnswer)
        self.assertEqual(score.answer.score, 1.7)
        self.assertEqual(field.value, "A🙂BC")
        self.assertEqual(span.value, "🙂B")
        self.assertEqual(span.source_version, None)

    async def test_concurrent_calls_admit_at_most_one_final_attempt(self) -> None:
        provider = ScriptedProvider(lambda question, state, operation: NoulAnswer(0.5))
        run_limits = limits(attempts=1, questions=1, concurrency=2)
        ledger = UsageLedger(run_limits)
        client = DecisionClient(provider, model="jev-test", ledger=ledger)
        judgment = Judgment(
            "race",
            "1.0.0",
            NoulQuestion("Is this supported?"),
            (Subject("item"),),
        )
        decision_context = context(run_limits)

        results = await asyncio.gather(
            client.evaluate(
                judgment, DecisionInputs("race-a", {"item": "a"}), decision_context
            ),
            client.evaluate(
                judgment, DecisionInputs("race-b", {"item": "b"}), decision_context
            ),
            return_exceptions=True,
        )

        self.assertEqual(sum(isinstance(item, DecisionResult) for item in results), 1)
        self.assertEqual(
            sum(isinstance(item, BudgetExhaustedError) for item in results), 1
        )
        self.assertEqual(len(provider.calls), 1)
        snapshot = await ledger.snapshot()
        self.assertEqual(snapshot.provider_attempts, 1)
        self.assertEqual(snapshot.submitted_questions, 1)
        self.assertEqual(snapshot.active_operations, 0)

    async def test_usage_measurements_distinguish_accounting_strength(self) -> None:
        ledger = UsageLedger(limits())
        await ledger.record_estimate("estimate", input_tokens=8)
        await ledger.reserve_usage("reserve", input_tokens=12, output_tokens=4)
        await ledger.release_reservation("reserve")
        await ledger.record_usage(
            "observed", Usage(UsageCoverage.COMPLETE, 10, 2, 1, 3)
        )
        await ledger.record_usage("unknown", Usage())

        snapshot = await ledger.snapshot()
        kinds = {item.kind for item in snapshot.measurements}
        self.assertEqual(
            kinds,
            {
                UsageMeasurementKind.ESTIMATED,
                UsageMeasurementKind.RESERVED,
                UsageMeasurementKind.RELEASED,
                UsageMeasurementKind.OBSERVED,
                UsageMeasurementKind.UNKNOWN,
            },
        )
        observed = next(
            item
            for item in snapshot.measurements
            if item.kind is UsageMeasurementKind.OBSERVED
        )
        self.assertEqual(observed.input_tokens, 10)
        self.assertEqual(observed.output_tokens, 2)


if __name__ == "__main__":
    unittest.main()
