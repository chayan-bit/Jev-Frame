import inspect
import unittest
from collections.abc import Sequence
from typing import Any

from jev_frame import (
    AttemptAdmission,
    AttemptStatus,
    ChoiceAnswer,
    ClaimEvidenceOutcome,
    CompiledQuestion,
    Coverage,
    DecisionClient,
    DocumentCollectionWorkflow,
    DocumentRecord,
    EvidenceStore,
    PassagePage,
    PassageRecord,
    ProviderAttempt,
    ProviderBatch,
    RunContext,
    RunLimits,
    UnresolvedReason,
    Usage,
    UsageCoverage,
)


class PassageProvider:
    def __init__(self, choices: Sequence[str]) -> None:
        self.choices = tuple(choices)
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
        choice = self.choices[len(self.calls)]
        self.calls.append(operation_id)
        question = questions[0]
        return ProviderBatch(
            {
                question.routing_id: ChoiceAnswer(
                    choice,
                    {
                        option.key: 1.0 if option.key == choice else 0.0
                        for option in question.options
                    },
                    1.0,
                )
            },
            requested_model,
            "offline",
            operation_id,
            Usage(UsageCoverage.COMPLETE, 2, 1, 1, 1),
            (ProviderAttempt(attempt.id, 1, AttemptStatus.SUCCEEDED),),
        )


def context(store: EvidenceStore | None = None) -> RunContext:
    return RunContext(
        "fixture",
        100.0,
        RunLimits(12, 12, 0, 0, 2, 0, 0, 0, 0, 0),
        clock=lambda: 0.0,
        evidence_session=store,
    )


class DocumentCollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_pages_preserve_unicode_duplicates_conflicts_and_coverage(
        self,
    ) -> None:
        first_text = "Café α supports. Repeated. Repeated."
        second_text = "The source refutes the claim."
        documents = {
            "doc-a": DocumentRecord("doc-a", first_text, "v1"),
            "doc-b": DocumentRecord("doc-b", second_text, "v2"),
        }
        first_end = len("Café α supports.")
        repeated_one = first_text.index("Repeated.")
        repeated_two = first_text.index("Repeated.", repeated_one + 1)
        support = PassageRecord(
            "doc-a", "Duplicate title", first_text[:first_end], 0, first_end, "v1"
        )
        refute = PassageRecord(
            "doc-b", "Duplicate title", second_text, 0, len(second_text), "v2"
        )
        duplicate = PassageRecord(
            "doc-a",
            "Duplicate title",
            "Repeated.",
            repeated_two,
            repeated_two + len("Repeated."),
            "v1",
        )
        pages = {
            None: PassagePage(
                (support, refute), Coverage.TRUNCATED, "second", total_count=3
            ),
            "second": PassagePage((duplicate,), Coverage.COMPLETE, total_count=3),
        }

        def retrieve(
            query: str, cursor: str | None, limit: int, scope: str
        ) -> PassagePage:
            self.assertEqual((query, limit, scope), ("claim", 2, "fixture"))
            return pages[cursor]

        provider = PassageProvider(("supports", "refutes", "unknown"))
        workflow = DocumentCollectionWorkflow(
            DecisionClient(provider, model="offline"), retrieve, page_size=2
        )
        result = await workflow.assess(
            "claim", "The claim is true.", documents, context()
        )

        self.assertIs(result.coverage, Coverage.COMPLETE)
        self.assertEqual(result.pages_retrieved, 2)
        self.assertEqual(len(result.assessments), 3)
        self.assertEqual(
            [value.outcome for value in result.assessments],
            [
                ClaimEvidenceOutcome.SUPPORTS,
                ClaimEvidenceOutcome.REFUTES,
                ClaimEvidenceOutcome.UNKNOWN,
            ],
        )
        self.assertEqual(result.assessments[0].passage.text, "Café α supports.")
        self.assertNotEqual(support.id, duplicate.id)
        self.assertEqual(repeated_one + len("Repeated. "), repeated_two)
        self.assertTrue(
            any(
                value.reason is UnresolvedReason.SOURCE_CONFLICT
                for value in result.unresolved
            )
        )
        self.assertFalse(hasattr(result, "probability"))
        self.assertEqual(len(provider.calls), 3)

    async def test_truncated_page_never_claims_complete_absence(self) -> None:
        document = DocumentRecord("doc", "An unrelated passage.", "v1")
        passage = PassageRecord(
            "doc", "Result", document.text, 0, len(document.text), "v1"
        )

        def retrieve(
            query: str, cursor: str | None, limit: int, scope: str
        ) -> PassagePage:
            return PassagePage((passage,), Coverage.TRUNCATED, "more", 10)

        provider = PassageProvider(("unknown",))
        workflow = DocumentCollectionWorkflow(
            DecisionClient(provider, model="offline"),
            retrieve,
            page_size=1,
            max_pages=1,
        )
        result = await workflow.assess(
            "query", "Missing claim.", {"doc": document}, context()
        )

        self.assertIs(result.coverage, Coverage.TRUNCATED)
        self.assertTrue(
            any(
                value.reason is UnresolvedReason.INCOMPLETE_COVERAGE
                for value in result.unresolved
            )
        )
        self.assertFalse(
            any(
                value.reason is UnresolvedReason.MISSING_EVIDENCE
                for value in result.unresolved
            )
        )

    async def test_changed_version_and_offsets_fail_before_assessment(self) -> None:
        current = DocumentRecord("doc", "Current source.", "v2")
        stale = PassageRecord("doc", "Result", "Old", 0, 3, "v1")

        def retrieve(
            query: str, cursor: str | None, limit: int, scope: str
        ) -> PassagePage:
            return PassagePage((stale,), Coverage.COMPLETE, total_count=1)

        provider = PassageProvider(())
        workflow = DocumentCollectionWorkflow(
            DecisionClient(provider, model="offline"), retrieve
        )
        result = await workflow.assess(
            "query", "Claim.", {"doc": current}, context(EvidenceStore(lambda: 0.0))
        )

        self.assertEqual(provider.calls, [])
        self.assertTrue(
            any(
                value.reason is UnresolvedReason.STALE_SOURCE
                for value in result.unresolved
            )
        )


if __name__ == "__main__":
    unittest.main()
