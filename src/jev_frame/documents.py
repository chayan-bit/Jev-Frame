from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum

from .decisions import DecisionClient, DecisionInputs
from .definitions import (
    ChoiceAnswer,
    ChoiceOption,
    ChoiceQuestion,
    Coverage,
    DecisionContext,
    DecisionResult,
    EvidenceSelector,
    InputValidationError,
    Judgment,
    SourceSpan,
    Subject,
    Unresolved,
    UnresolvedReason,
)
from .packages import DocumentRecord
from .state import (
    EvidenceNotFoundError,
    EvidenceStore,
    Observation,
    canonical_digest,
    evidence_digest,
)

SUPPORTS = "supports"
REFUTES = "refutes"
UNKNOWN = "unknown"
PASSAGE_EVIDENCE = "passage"


class DocumentCollectionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PassageRecord:
    document_id: str
    title: str
    text: str
    start: int
    end: int
    source_version: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.document_id, "document id"),
            (self.title, "passage title"),
            (self.source_version, "source version"),
        ):
            if type(value) is not str or not value:
                raise DocumentCollectionError(f"{name} must be non-empty")
        if type(self.text) is not str:
            raise DocumentCollectionError("passage text must be a string")
        SourceSpan(self.start, self.end)

    @property
    def id(self) -> str:
        return f"{self.document_id}:{self.source_version}:{self.start}:{self.end}"


@dataclass(frozen=True, slots=True)
class PassagePage:
    passages: tuple[PassageRecord, ...]
    coverage: Coverage
    next_cursor: str | None = None
    total_count: int | None = None

    def __post_init__(self) -> None:
        if any(not isinstance(value, PassageRecord) for value in self.passages):
            raise DocumentCollectionError("passage pages require passage records")
        if len({value.id for value in self.passages}) != len(self.passages):
            raise DocumentCollectionError("passage identities must be unique per page")
        if not isinstance(self.coverage, Coverage):
            raise DocumentCollectionError("passage coverage must use Coverage")
        if self.next_cursor is not None and (
            type(self.next_cursor) is not str or not self.next_cursor
        ):
            raise DocumentCollectionError("passage cursor must be non-empty")
        if self.total_count is not None and (
            type(self.total_count) is not int or self.total_count < len(self.passages)
        ):
            raise DocumentCollectionError("passage total count is invalid")
        if self.coverage is Coverage.COMPLETE and self.next_cursor is not None:
            raise DocumentCollectionError("complete passage pages cannot expand")


class ClaimEvidenceOutcome(str, Enum):
    SUPPORTS = SUPPORTS
    REFUTES = REFUTES
    UNKNOWN = UNKNOWN


@dataclass(frozen=True, slots=True)
class PassageAssessment:
    passage: PassageRecord
    outcome: ClaimEvidenceOutcome
    source_ref: str
    passage_ref: str
    decision: DecisionResult


@dataclass(frozen=True, slots=True)
class DocumentCollectionResult:
    assessments: tuple[PassageAssessment, ...]
    coverage: Coverage
    pages_retrieved: int
    attempted_cursors: tuple[str, ...]
    unresolved: tuple[Unresolved, ...] = ()

    @property
    def supporting(self) -> tuple[PassageAssessment, ...]:
        return tuple(
            value
            for value in self.assessments
            if value.outcome is ClaimEvidenceOutcome.SUPPORTS
        )

    @property
    def refuting(self) -> tuple[PassageAssessment, ...]:
        return tuple(
            value
            for value in self.assessments
            if value.outcome is ClaimEvidenceOutcome.REFUTES
        )


RetrievePassages = Callable[
    [str, str | None, int, str], PassagePage | Awaitable[PassagePage]
]


def _add_once(store: EvidenceStore, record: Observation) -> None:
    try:
        current = store.get(record.id)
    except EvidenceNotFoundError:
        store.add(record)
        return
    if evidence_digest(current) != evidence_digest(record):
        raise InputValidationError("evidence id identifies different document content")


def document_claim_judgment(version: str = "1.0.0") -> Judgment:
    return Judgment(
        "assess_passage_claim",
        version,
        ChoiceQuestion(
            "Classify how the exact passage bears on the claim.",
            (
                ChoiceOption(SUPPORTS, "The passage supports the claim."),
                ChoiceOption(REFUTES, "The passage refutes the claim."),
                ChoiceOption(UNKNOWN, "The passage does not resolve the claim."),
            ),
        ),
        (Subject("claim"), Subject("document")),
        (EvidenceSelector(PASSAGE_EVIDENCE),),
    )


@dataclass(frozen=True, slots=True)
class DocumentCollectionWorkflow:
    client: DecisionClient = field(repr=False, compare=False)
    retrieve: RetrievePassages = field(repr=False, compare=False)
    judgment: Judgment = field(default_factory=document_claim_judgment)
    page_size: int = 16
    max_pages: int = 4

    def __post_init__(self) -> None:
        if not isinstance(self.client, DecisionClient) or not callable(self.retrieve):
            raise DocumentCollectionError(
                "document workflow requires a decision client and retriever"
            )
        if type(self.page_size) is not int or self.page_size <= 0:
            raise DocumentCollectionError("document page size must be positive")
        if type(self.max_pages) is not int or self.max_pages <= 0:
            raise DocumentCollectionError("document page limit must be positive")
        if not isinstance(self.judgment.primitive, ChoiceQuestion) or tuple(
            option.key for option in self.judgment.primitive.criteria
        ) != (SUPPORTS, REFUTES, UNKNOWN):
            raise DocumentCollectionError(
                "document judgment must use support, refute, and unknown choices"
            )
        if tuple(subject.name for subject in self.judgment.subjects) != (
            "claim",
            "document",
        ) or tuple(selector.name for selector in self.judgment.evidence) != (
            PASSAGE_EVIDENCE,
        ):
            raise DocumentCollectionError("document judgment contract is incompatible")

    async def assess(
        self,
        query: str,
        claim: str,
        documents: Mapping[str, DocumentRecord],
        context: DecisionContext,
    ) -> DocumentCollectionResult:
        if type(query) is not str or not query or type(claim) is not str or not claim:
            raise InputValidationError("document query and claim must be non-empty")
        if not isinstance(documents, Mapping) or any(
            key != value.id or not isinstance(value, DocumentRecord)
            for key, value in documents.items()
        ):
            raise InputValidationError("documents must be keyed DocumentRecord values")
        store = (
            EvidenceStore(context.clock)
            if context.evidence_session is None
            else context.evidence_session
        )
        if not isinstance(store, EvidenceStore):
            raise InputValidationError(
                "document evidence session must be an EvidenceStore"
            )
        decision_context = replace(context, evidence_session=store)
        assessments: list[PassageAssessment] = []
        unresolved: list[Unresolved] = []
        seen_passages: set[str] = set()
        cursors: list[str] = []
        cursor: str | None = None
        coverage = Coverage.UNKNOWN
        pages = 0
        while pages < self.max_pages:
            cursor_key = cursor or "<start>"
            if cursor_key in cursors:
                unresolved.append(
                    Unresolved(
                        UnresolvedReason.NO_PROGRESS,
                        ("claim",),
                        "passage retrieval repeated a cursor",
                        tuple(cursors),
                        needed=cursor,
                    )
                )
                break
            cursors.append(cursor_key)
            page = self.retrieve(query, cursor, self.page_size, context.scope)
            if inspect.isawaitable(page):
                page = await page
            if not isinstance(page, PassagePage):
                raise DocumentCollectionError("retriever must return PassagePage")
            pages += 1
            coverage = page.coverage
            for passage in page.passages:
                if passage.id in seen_passages:
                    continue
                seen_passages.add(passage.id)
                try:
                    assessment = await self._assess_passage(
                        passage, claim, documents, decision_context, store
                    )
                except InputValidationError as error:
                    unresolved.append(
                        Unresolved(
                            UnresolvedReason.STALE_SOURCE,
                            ("claim", passage.document_id),
                            str(error),
                            tuple(cursors),
                            needed=passage.id,
                        )
                    )
                    continue
                assessments.append(assessment)
            if page.coverage is Coverage.COMPLETE:
                break
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        if coverage is not Coverage.COMPLETE:
            unresolved.append(
                Unresolved(
                    UnresolvedReason.INCOMPLETE_COVERAGE,
                    ("claim",),
                    "retrieval did not establish complete document coverage",
                    tuple(cursors),
                    needed=cursor,
                )
            )
        outcomes = {value.outcome for value in assessments}
        if {
            ClaimEvidenceOutcome.SUPPORTS,
            ClaimEvidenceOutcome.REFUTES,
        }.issubset(outcomes):
            unresolved.append(
                Unresolved(
                    UnresolvedReason.SOURCE_CONFLICT,
                    ("claim",),
                    "current sources both support and refute the claim",
                    tuple(value.passage.id for value in assessments),
                )
            )
        elif coverage is Coverage.COMPLETE and not any(
            value.outcome is ClaimEvidenceOutcome.SUPPORTS for value in assessments
        ):
            unresolved.append(
                Unresolved(
                    UnresolvedReason.MISSING_EVIDENCE,
                    ("claim",),
                    "no assessed passage supports the claim",
                    tuple(value.passage.id for value in assessments),
                )
            )
        return DocumentCollectionResult(
            tuple(assessments), coverage, pages, tuple(cursors), tuple(unresolved)
        )

    async def _assess_passage(
        self,
        passage: PassageRecord,
        claim: str,
        documents: Mapping[str, DocumentRecord],
        context: DecisionContext,
        store: EvidenceStore,
    ) -> PassageAssessment:
        document = documents.get(passage.document_id)
        if document is None or document.version != passage.source_version:
            raise InputValidationError("passage source version is unavailable")
        if passage.end > len(document.text) or (
            document.text[passage.start : passage.end] != passage.text
        ):
            raise InputValidationError("passage offsets do not match retained source")
        source_id = f"document:{document.id}:{document.version}"
        _add_once(
            store,
            Observation(
                id=source_id,
                value=document.text,
                source_id=document.id,
                scope=context.scope,
                observed_at=context.clock(),
                source_version=document.version,
            ),
        )
        source = store.require_current(source_id, context.scope)
        if not isinstance(source, Observation):
            raise InputValidationError("document source is not an observation")
        bound = await self.client.extract_source(
            source, SourceSpan(passage.start, passage.end), context
        )
        passage_ref = f"passage:{canonical_digest(passage)}"
        _add_once(
            store,
            Observation(
                id=passage_ref,
                value=bound.value,
                source_id=bound.source_id,
                scope=context.scope,
                observed_at=context.clock(),
                source_version=bound.source_version,
                dependencies=(source_id,),
            ),
        )
        decision = await self.client.evaluate(
            self.judgment,
            DecisionInputs(
                f"claim:{canonical_digest((claim, passage.id))}",
                {"claim": claim, "document": passage.document_id},
                {PASSAGE_EVIDENCE: store.require_current(passage_ref, context.scope)},
            ),
            context,
        )
        answer = decision.answer
        if not isinstance(answer, ChoiceAnswer):
            raise DocumentCollectionError(
                "document judgment returned another primitive"
            )
        return PassageAssessment(
            passage,
            ClaimEvidenceOutcome(answer.choice),
            source_id,
            passage_ref,
            decision,
        )
