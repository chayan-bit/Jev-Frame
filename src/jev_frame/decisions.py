from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol

from typesafe_sdk import JSONContent

from .compiler import CompiledQuestion, compile_judgment
from .definitions import (
    NO_FIT_KEY,
    CandidateSet,
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionContext,
    DecisionResult,
    InputValidationError,
    Judgment,
    NoulAnswer,
    NoulQuestion,
    ProviderError,
    ScoreQuestion,
    SourceField,
    SourceSpan,
    StaleInputError,
    Unresolved,
    UnresolvedReason,
    Usage,
)
from .inspection import (
    EventKind,
    EventLog,
    JevEvent,
    diagnostic_for_error,
    serialize_decision_result,
)
from .limits import AdmissionError, DeadlineExceededError, UsageLedger
from .provider import (
    AttemptAdmission,
    ProviderAttempt,
    ProviderBatch,
    ProviderResponseError,
)
from .state import (
    BoundSource,
    CandidateSelection,
    EvidenceNotFoundError,
    EvidenceStore,
    ModelJudgment,
    Observation,
    bind_source,
    candidate_snapshot_digest,
    decision_fingerprint,
    evidence_digest,
    select_candidate,
)


@dataclass(frozen=True, slots=True)
class DecisionInputs:
    id: str
    subjects: Mapping[str, Any]
    evidence: Mapping[str, Observation] = field(default_factory=dict)
    candidate_sets: Mapping[str, CandidateSet] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.id) is not str or not self.id:
            raise InputValidationError("decision input id must be a non-empty string")
        for name, values in (
            ("subjects", self.subjects),
            ("evidence", self.evidence),
            ("candidate_sets", self.candidate_sets),
        ):
            if not isinstance(values, Mapping) or any(
                type(key) is not str or not key for key in values
            ):
                raise InputValidationError(f"decision {name} must use string keys")
        if any(not isinstance(value, Observation) for value in self.evidence.values()):
            raise InputValidationError("decision evidence values must be observations")
        if any(
            not isinstance(value, CandidateSet)
            for value in self.candidate_sets.values()
        ):
            raise InputValidationError(
                "decision candidate values must be candidate snapshots"
            )
        object.__setattr__(self, "subjects", MappingProxyType(dict(self.subjects)))
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))
        object.__setattr__(
            self, "candidate_sets", MappingProxyType(dict(self.candidate_sets))
        )


@dataclass(frozen=True, slots=True)
class SelectionResult:
    selection: CandidateSelection | None
    decision: DecisionResult | None = None
    unresolved: Unresolved | None = None
    usage: Usage = field(default_factory=Usage)


class FilterVerdict(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNASSESSED = "unassessed"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class FilterItemResult:
    item_id: str
    verdict: FilterVerdict
    decision: DecisionResult | None = None
    reason: str | None = None


class DecisionProvider(Protocol):
    async def evaluate(
        self,
        *,
        state: JSONContent,
        questions: Sequence[CompiledQuestion],
        requested_model: str,
        operation_id: str,
        timeout: float | None = None,
        admit_attempt: AttemptAdmission | None = None,
    ) -> ProviderBatch: ...


def _store(context: DecisionContext) -> EvidenceStore:
    if context.evidence_session is None:
        return EvidenceStore(context.clock)
    if not isinstance(context.evidence_session, EvidenceStore):
        raise InputValidationError("evidence_session must be an EvidenceStore")
    return context.evidence_session


def _register(store: EvidenceStore, record: Observation) -> None:
    try:
        current = store.get(record.id)
    except EvidenceNotFoundError:
        store.add(record)
        return
    if evidence_digest(current) != evidence_digest(record):
        raise InputValidationError(
            f"evidence id {record.id!r} already identifies different content"
        )


class DecisionClient:
    """Direct Jev decisions without an agent definition or scheduler."""

    def __init__(
        self,
        provider: DecisionProvider,
        *,
        model: str,
        ledger: UsageLedger | None = None,
        event_log: EventLog | None = None,
    ) -> None:
        if type(model) is not str or not model.strip():
            raise ValueError("model must be a non-empty string")
        self.provider = provider
        self.model = model
        self._ledger = ledger
        self._event_log = EventLog() if event_log is None else event_log

    def _ledger_for(self, context: DecisionContext) -> UsageLedger:
        if self._ledger is None:
            self._ledger = UsageLedger(context.limits)
        elif self._ledger.limits != context.limits:
            raise InputValidationError(
                "decision context limits differ from the shared ledger"
            )
        return self._ledger

    @property
    def ledger(self) -> UsageLedger | None:
        return self._ledger

    @property
    def events(self) -> tuple[JevEvent, ...]:
        return self._event_log.events

    def _validate_inputs(
        self,
        judgment: Judgment,
        inputs: DecisionInputs,
        context: DecisionContext,
    ) -> tuple[CandidateSet | None, EvidenceStore, tuple[Observation, ...]]:
        subject_names = tuple(subject.name for subject in judgment.subjects)
        if set(inputs.subjects) != set(subject_names):
            raise InputValidationError(
                f"judgment subjects mismatch; expected={sorted(subject_names)}, supplied={sorted(inputs.subjects)}"
            )
        evidence_names = tuple(selector.name for selector in judgment.evidence)
        if set(inputs.evidence) != set(evidence_names):
            raise InputValidationError(
                f"judgment evidence mismatch; expected={sorted(evidence_names)}, supplied={sorted(inputs.evidence)}"
            )
        candidate_set: CandidateSet | None = None
        if judgment.candidate_set is not None:
            candidate_set = inputs.candidate_sets.get(judgment.candidate_set)
            if candidate_set is None:
                raise InputValidationError(
                    f"missing candidate set {judgment.candidate_set!r}"
                )
            if set(inputs.candidate_sets) != {judgment.candidate_set}:
                raise InputValidationError("unexpected candidate sets supplied")
            if candidate_set.id != judgment.candidate_set:
                raise InputValidationError("candidate snapshot identity mismatch")
            if candidate_set.scope != context.scope:
                raise InputValidationError(
                    "candidate set is outside the decision scope"
                )
        elif inputs.candidate_sets:
            raise InputValidationError("judgment does not accept a candidate set")
        store = _store(context)
        records = tuple(inputs.evidence.values())
        for record in records:
            if record.scope != context.scope:
                raise InputValidationError("evidence is outside the decision scope")
            _register(store, record)
            store.require_current(record.id, context.scope)
        return candidate_set, store, records

    async def evaluate(
        self,
        judgment: Judgment,
        inputs: DecisionInputs,
        context: DecisionContext,
    ) -> DecisionResult:
        run_id = context.run_id or inputs.id
        correlation_id = context.correlation_id or run_id
        node_id: str | None = None

        def emit(
            kind: EventKind,
            *,
            data: Mapping[str, Any],
            attempt_id: str | None = None,
            reason_code: str | None = None,
        ) -> None:
            self._event_log.emit(
                kind,
                run_id=run_id,
                correlation_id=correlation_id,
                operation_id=inputs.id,
                parent_operation_id=context.parent_operation_id,
                attempt_id=attempt_id,
                reason_code=reason_code,
                data=data,
                sink=context.event_sink,
            )

        emit(
            EventKind.OPERATION_STARTED,
            data={
                "definition_id": judgment.id,
                "definition_version": judgment.version,
            },
        )
        try:
            subject_names = tuple(subject.name for subject in judgment.subjects)
            candidate_set, store, records = self._validate_inputs(
                judgment, inputs, context
            )
            question = compile_judgment(judgment, candidate_set=candidate_set)
            node_id = question.routing_id
            fingerprint = decision_fingerprint(
                semantic_version=judgment.version,
                policy_version=judgment.acceptance_policy or "unassessed",
                model_identity=self.model,
                projection_version="1.0.0",
                compiler_version="1.0.0",
                scope=context.scope,
                evidence=records,
                candidate_sets=(() if candidate_set is None else (candidate_set,)),
                subjects=inputs.subjects,
            )
            state = {
                "subjects": dict(inputs.subjects),
                "evidence": {
                    name: record.value for name, record in inputs.evidence.items()
                },
            }
            ledger = self._ledger_for(context)

            async def admit(attempt: ProviderAttempt) -> None:
                await ledger.admit_provider_attempt(
                    attempt,
                    1,
                    deadline=context.deadline,
                    clock=context.clock,
                )
                emit(
                    EventKind.ATTEMPT_ADMITTED,
                    attempt_id=attempt.id,
                    data={
                        "definition_id": judgment.id,
                        "question_id": question.routing_id,
                        "attempt_number": attempt.number,
                        "attempt_status": attempt.status.value,
                    },
                )

            async with ledger.operation(
                inputs.id, deadline=context.deadline, clock=context.clock
            ):
                timeout = context.deadline - context.clock()
                if timeout <= 0:
                    raise DeadlineExceededError("deadline expired before dispatch")
                batch = await self.provider.evaluate(
                    state=state,
                    questions=(question,),
                    requested_model=self.model,
                    operation_id=inputs.id,
                    timeout=timeout,
                    admit_attempt=admit,
                )
            await ledger.record_usage(inputs.id, batch.usage)
            answer = batch.answers[question.routing_id]
            judgment_record = ModelJudgment(
                id=f"{inputs.id}:judgment",
                value=answer,
                source_id=f"typesafe:{batch.request_id or batch.attempts[-1].id}",
                scope=context.scope,
                observed_at=context.clock(),
                dependencies=tuple(record.id for record in records),
                judgment_id=judgment.id,
                judgment_version=judgment.version,
                question_semantics=question.instructions,
                subjects=subject_names,
                answer=answer,
                input_fingerprint=fingerprint,
                requested_model=batch.requested_model,
                returned_model=batch.returned_model,
                candidate_snapshot_digest=(
                    None
                    if candidate_set is None
                    else candidate_snapshot_digest(candidate_set)
                ),
                presented_candidate_keys=tuple(
                    option.key for option in question.options
                ),
            )
            store.add(judgment_record)
            if not store.is_current(judgment_record.id):
                raise StaleInputError(
                    "decision inputs changed while the provider request was in flight"
                )
            result = DecisionResult(
                answer,
                subject_names,
                tuple(record.id for record in records) + (judgment_record.id,),
                fingerprint,
                batch.requested_model,
                batch.returned_model,
                batch.usage,
            )
            emit(
                EventKind.OPERATION_COMPLETED,
                data={
                    "definition_id": judgment.id,
                    "question_id": question.routing_id,
                    "result_fingerprint": fingerprint,
                    "evidence_refs": list(result.evidence_refs),
                    "usage": serialize_decision_result(result)["usage"],
                },
            )
            return result
        except asyncio.CancelledError as error:
            diagnostic = diagnostic_for_error(
                error,
                definition_id=judgment.id,
                node_id=node_id,
                source_path=("judgments", judgment.id),
            )
            emit(
                EventKind.OPERATION_CANCELLED,
                reason_code=diagnostic.code,
                data={
                    "definition_id": judgment.id,
                    "question_id": node_id,
                    "diagnostic": diagnostic.to_dict(),
                },
            )
            raise
        except ProviderError as error:
            attempts = len(getattr(error, "attempts", ()))
            await self._ledger_for(context).record_usage(
                inputs.id,
                Usage(provider_attempts=attempts, submitted_questions=attempts),
            )
            diagnostic = diagnostic_for_error(
                error,
                definition_id=judgment.id,
                node_id=node_id,
                source_path=("judgments", judgment.id),
            )
            emit(
                EventKind.OPERATION_FAILED,
                reason_code=diagnostic.code,
                data={
                    "definition_id": judgment.id,
                    "question_id": node_id,
                    "diagnostic": diagnostic.to_dict(),
                },
            )
            raise
        except Exception as error:
            diagnostic = diagnostic_for_error(
                error,
                definition_id=judgment.id,
                node_id=node_id,
                source_path=("judgments", judgment.id),
            )
            emit(
                EventKind.OPERATION_FAILED,
                reason_code=diagnostic.code,
                data={
                    "definition_id": judgment.id,
                    "question_id": node_id,
                    "diagnostic": diagnostic.to_dict(),
                },
            )
            raise

    async def assess(
        self,
        judgment: Judgment,
        inputs: DecisionInputs,
        context: DecisionContext,
    ) -> DecisionResult:
        if not isinstance(judgment.primitive, NoulQuestion):
            raise InputValidationError("assess requires a Noul judgment")
        return await self.evaluate(judgment, inputs, context)

    async def score(
        self,
        judgment: Judgment,
        inputs: DecisionInputs,
        context: DecisionContext,
    ) -> DecisionResult:
        if not isinstance(judgment.primitive, ScoreQuestion):
            raise InputValidationError("score requires a Score judgment")
        return await self.evaluate(judgment, inputs, context)

    async def select(
        self,
        judgment: Judgment,
        inputs: DecisionInputs,
        context: DecisionContext,
    ) -> SelectionResult:
        if not isinstance(judgment.primitive, ChoiceQuestion):
            raise InputValidationError("select requires a Choice judgment")
        if judgment.candidate_set is None:
            raise InputValidationError("select requires a dynamic candidate set")
        snapshot, _, _ = self._validate_inputs(judgment, inputs, context)
        assert snapshot is not None
        if snapshot.coverage.value == "failed":
            return SelectionResult(
                None,
                unresolved=Unresolved(
                    UnresolvedReason.MISSING_EVIDENCE,
                    tuple(inputs.subjects),
                    snapshot.failure_reason or "candidate retrieval failed",
                    needed=snapshot.expansion_ref,
                ),
            )
        if not snapshot.candidates:
            selection = select_candidate(snapshot, NO_FIT_KEY)
            unresolved = (
                None
                if snapshot.coverage.value == "complete"
                else Unresolved(
                    UnresolvedReason.INCOMPLETE_COVERAGE,
                    tuple(inputs.subjects),
                    "the empty candidate snapshot is not known to be complete",
                    needed=snapshot.expansion_ref,
                )
            )
            return SelectionResult(selection, unresolved=unresolved)
        decision = await self.evaluate(judgment, inputs, context)
        answer = decision.answer
        if not isinstance(answer, ChoiceAnswer):
            raise ProviderResponseError("primitive_type_mismatch", ())
        selection = select_candidate(snapshot, answer.choice)
        unresolved = (
            Unresolved(
                UnresolvedReason.INCOMPLETE_COVERAGE,
                tuple(inputs.subjects),
                "no-fit applies only to the supplied incomplete snapshot",
                needed=snapshot.expansion_ref,
            )
            if answer.choice == NO_FIT_KEY and snapshot.coverage.value != "complete"
            else None
        )
        return SelectionResult(selection, decision, unresolved, decision.usage)

    async def filter(
        self,
        judgment: Judgment,
        items: Sequence[DecisionInputs],
        context: DecisionContext,
        *,
        classify: Callable[[NoulAnswer], bool | None] | None = None,
    ) -> tuple[FilterItemResult, ...]:
        if not isinstance(judgment.primitive, NoulQuestion):
            raise InputValidationError("filter requires a Noul judgment")
        results: list[FilterItemResult] = []
        for item in items:
            try:
                decision = await self.assess(judgment, item, context)
            except (ProviderError, AdmissionError, StaleInputError) as error:
                results.append(
                    FilterItemResult(
                        item.id,
                        FilterVerdict.UNRESOLVED,
                        reason=type(error).__name__,
                    )
                )
                continue
            answer = decision.answer
            assert isinstance(answer, NoulAnswer)
            accepted = None if classify is None else classify(answer)
            verdict = (
                FilterVerdict.UNASSESSED
                if accepted is None
                else FilterVerdict.ACCEPTED
                if accepted
                else FilterVerdict.REJECTED
            )
            results.append(FilterItemResult(item.id, verdict, decision))
        return tuple(results)

    async def extract_source(
        self,
        record: Observation,
        locator: SourceField | SourceSpan,
        context: DecisionContext,
    ) -> BoundSource:
        if record.scope != context.scope:
            raise InputValidationError("source is outside the decision scope")
        store = _store(context)
        _register(store, record)
        store.require_current(record.id, context.scope)
        return bind_source(record, locator)

    def as_callable(
        self, judgment: Judgment
    ) -> Callable[[DecisionInputs, DecisionContext], Any]:
        async def decide(
            inputs: DecisionInputs, context: DecisionContext
        ) -> DecisionResult:
            return await self.evaluate(judgment, inputs, context)

        return decide
