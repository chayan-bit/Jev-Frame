from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from .compiler import CompilerError
from .definitions import (
    AcceptanceRecord,
    BindingError,
    CandidateSet,
    ChoiceAnswer,
    DecisionResult,
    DefinitionError,
    InputValidationError,
    JevFrameError,
    NoulAnswer,
    PrimitiveAnswer,
    ProviderError,
    ScopeError,
    ScoreAnswer,
    StaleInputError,
    Unresolved,
    UnresolvedReason,
    UnsupportedTypeError,
    Usage,
)
from .limits import AdmissionError
from .state import (
    AcceptanceEvidence,
    EvidenceStore,
    ModelJudgment,
    StableSerializationError,
    candidate_snapshot_digest,
    canonical_json,
)

EVENT_SCHEMA_VERSION = "jev-frame.event.v1"
DECISION_RESULT_SCHEMA_VERSION = "jev-frame.decision-result.v1"
INSPECTION_SCHEMA_VERSION = "jev-frame.inspection.v1"
_PUBLIC_REASON = re.compile(r"[a-z][a-z0-9_]{0,63}").fullmatch


class EventSerializationError(JevFrameError):
    pass


class InspectionError(JevFrameError):
    pass


class EventKind(str, Enum):
    OPERATION_STARTED = "operation_started"
    ATTEMPT_ADMITTED = "attempt_admitted"
    OPERATION_COMPLETED = "operation_completed"
    OPERATION_UNRESOLVED = "operation_unresolved"
    OPERATION_FAILED = "operation_failed"
    OPERATION_CANCELLED = "operation_cancelled"


_EVENT_DATA_FIELDS = {
    EventKind.OPERATION_STARTED: {
        "definition_id",
        "definition_version",
        "question_id",
    },
    EventKind.ATTEMPT_ADMITTED: {
        "definition_id",
        "question_id",
        "attempt_number",
        "attempt_status",
    },
    EventKind.OPERATION_COMPLETED: {
        "definition_id",
        "question_id",
        "result_fingerprint",
        "evidence_refs",
        "usage",
    },
    EventKind.OPERATION_UNRESOLVED: {
        "definition_id",
        "question_id",
        "diagnostic",
    },
    EventKind.OPERATION_FAILED: {"definition_id", "question_id", "diagnostic"},
    EventKind.OPERATION_CANCELLED: {"definition_id", "question_id", "diagnostic"},
}


def _text(value: Any, name: str) -> None:
    if type(value) is not str or not value:
        raise EventSerializationError(f"{name} must be a non-empty string")


def _json_value(value: Any) -> Any:
    return json.loads(canonical_json(value))


@dataclass(frozen=True, slots=True)
class JevEvent:
    sequence: int
    kind: EventKind
    run_id: str
    correlation_id: str
    operation_id: str
    data: Mapping[str, Any] = field(default_factory=dict)
    parent_operation_id: str | None = None
    attempt_id: str | None = None
    reason_code: str | None = None
    schema_version: str = EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EVENT_SCHEMA_VERSION:
            raise EventSerializationError("unsupported event schema version")
        if type(self.sequence) is not int or self.sequence < 1:
            raise EventSerializationError("event sequence must be positive")
        if not isinstance(self.kind, EventKind):
            raise EventSerializationError("event kind must use EventKind")
        for value, name in (
            (self.run_id, "run id"),
            (self.correlation_id, "correlation id"),
            (self.operation_id, "operation id"),
        ):
            _text(value, name)
        for optional_value, name in (
            (self.parent_operation_id, "parent operation id"),
            (self.attempt_id, "attempt id"),
            (self.reason_code, "reason code"),
        ):
            if optional_value is not None:
                _text(optional_value, name)
        if self.reason_code is not None and not _PUBLIC_REASON(self.reason_code):
            raise EventSerializationError("reason code is not a public identifier")
        if not isinstance(self.data, Mapping):
            raise EventSerializationError("event data must be a mapping")
        unexpected = set(self.data) - _EVENT_DATA_FIELDS[self.kind]
        if unexpected:
            raise EventSerializationError(
                f"event data contains fields not allowed for {self.kind.value}"
            )
        try:
            data = _json_value(self.data)
        except StableSerializationError as error:
            raise EventSerializationError(
                "event data is not safely serializable"
            ) from error
        object.__setattr__(self, "data", MappingProxyType(data))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "kind": self.kind.value,
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "operation_id": self.operation_id,
            "data": dict(self.data),
        }
        for name in ("parent_operation_id", "attempt_id", "reason_code"):
            value = getattr(self, name)
            if value is not None:
                result[name] = value
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> JevEvent:
        allowed = {
            "schema_version",
            "sequence",
            "kind",
            "run_id",
            "correlation_id",
            "operation_id",
            "data",
            "parent_operation_id",
            "attempt_id",
            "reason_code",
        }
        if not isinstance(value, Mapping) or set(value) - allowed:
            raise EventSerializationError("event contains unknown fields")
        try:
            return cls(
                schema_version=value["schema_version"],
                sequence=value["sequence"],
                kind=EventKind(value["kind"]),
                run_id=value["run_id"],
                correlation_id=value["correlation_id"],
                operation_id=value["operation_id"],
                parent_operation_id=value.get("parent_operation_id"),
                attempt_id=value.get("attempt_id"),
                reason_code=value.get("reason_code"),
                data=value.get("data", {}),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise EventSerializationError("event fields are invalid") from error


EventSink = Callable[[Mapping[str, Any]], None]


class EventLog:
    """Run-local sanitized events; sink failures never change decision semantics."""

    def __init__(self) -> None:
        self._events: list[JevEvent] = []
        self._sequences: dict[str, int] = {}
        self._sink_failures = 0

    @property
    def events(self) -> tuple[JevEvent, ...]:
        return tuple(self._events)

    @property
    def sink_failures(self) -> int:
        return self._sink_failures

    def emit(
        self,
        kind: EventKind,
        *,
        run_id: str,
        correlation_id: str,
        operation_id: str,
        data: Mapping[str, Any] | None = None,
        parent_operation_id: str | None = None,
        attempt_id: str | None = None,
        reason_code: str | None = None,
        sink: EventSink | None = None,
    ) -> JevEvent:
        sequence = self._sequences.get(run_id, 0) + 1
        event = JevEvent(
            sequence,
            kind,
            run_id,
            correlation_id,
            operation_id,
            {} if data is None else data,
            parent_operation_id,
            attempt_id,
            reason_code,
        )
        self._sequences[run_id] = sequence
        self._events.append(event)
        if sink is not None:
            try:
                sink(event.to_dict())
            except Exception:  # noqa: BLE001 - observability cannot fail the decision
                self._sink_failures += 1
        return event


class DiagnosticCategory(str, Enum):
    DEFINITION = "definition"
    SERVICE = "service"
    SEMANTIC = "semantic"


@dataclass(frozen=True, slots=True)
class PublicDiagnostic:
    category: DiagnosticCategory
    code: str
    definition_id: str
    node_id: str | None = None
    source_path: tuple[str, ...] = ()
    corrective_action: str | None = None
    capability_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "category": self.category.value,
            "code": self.code,
            "definition_id": self.definition_id,
            "source_path": list(self.source_path),
        }
        for name in ("node_id", "corrective_action", "capability_id"):
            value = getattr(self, name)
            if value is not None:
                result[name] = value
        return result


def diagnostic_for_error(
    error: BaseException,
    *,
    definition_id: str,
    node_id: str | None = None,
    source_path: tuple[str, ...] = (),
) -> PublicDiagnostic:
    if isinstance(error, asyncio.CancelledError):
        return PublicDiagnostic(
            DiagnosticCategory.SERVICE,
            "cancelled",
            definition_id,
            node_id,
            source_path,
            "resume_only_from_fresh_host_state",
        )
    if isinstance(error, CompilerError):
        item = error.diagnostic
        return PublicDiagnostic(
            DiagnosticCategory.DEFINITION,
            item.code,
            item.definition_id,
            item.node_id,
            source_path,
            "correct_the_definition_or_supply_the_named_binding",
            item.reference,
        )
    if isinstance(error, (DefinitionError, BindingError, UnsupportedTypeError)):
        return PublicDiagnostic(
            DiagnosticCategory.DEFINITION,
            "invalid_definition",
            definition_id,
            node_id,
            source_path,
            "correct_the_definition",
        )
    if isinstance(error, (InputValidationError, ScopeError)):
        return PublicDiagnostic(
            DiagnosticCategory.DEFINITION,
            "invalid_input",
            definition_id,
            node_id,
            source_path,
            "correct_the_named_input_or_scope",
        )
    if isinstance(error, StaleInputError):
        return PublicDiagnostic(
            DiagnosticCategory.SEMANTIC,
            "stale_input",
            definition_id,
            node_id,
            source_path,
            "refresh_source_evidence",
        )
    if isinstance(error, AdmissionError):
        return PublicDiagnostic(
            DiagnosticCategory.SERVICE,
            "admission_rejected",
            definition_id,
            node_id,
            source_path,
            "release_or_increase_the_named_run_limit",
        )
    if isinstance(error, ProviderError):
        return PublicDiagnostic(
            DiagnosticCategory.SERVICE,
            "provider_failure",
            definition_id,
            node_id,
            source_path,
            "retry_or_change_the_provider_configuration",
        )
    return PublicDiagnostic(
        DiagnosticCategory.SERVICE,
        "internal_failure",
        definition_id,
        node_id,
        source_path,
        "inspect_the_private_local_exception",
    )


def diagnostic_for_unresolved(
    unresolved: Unresolved,
    *,
    definition_id: str,
    node_id: str | None = None,
    source_path: tuple[str, ...] = (),
) -> PublicDiagnostic:
    correction = {
        UnresolvedReason.MISSING_EVIDENCE: "supply_or_retrieve_the_named_evidence",
        UnresolvedReason.SOURCE_CONFLICT: "resolve_or_preserve_the_source_conflict",
        UnresolvedReason.INCOMPLETE_COVERAGE: "expand_the_candidate_snapshot",
        UnresolvedReason.REFUTED_CLAIM: "handle_the_verified_negative_result",
        UnresolvedReason.SEMANTIC_AMBIGUITY: "clarify_the_named_subject",
        UnresolvedReason.MISSING_CAPABILITY: "register_the_named_capability",
        UnresolvedReason.UNACCEPTED_JUDGMENT: "apply_an_acceptance_policy",
        UnresolvedReason.PERMISSION_DENIAL: "obtain_exact_action_authority",
        UnresolvedReason.STALE_SOURCE: "refresh_source_evidence",
        UnresolvedReason.UNKNOWN_WRITE_OUTCOME: "reconcile_the_external_effect",
        UnresolvedReason.BUDGET_EXHAUSTION: "increase_or_release_the_named_run_limit",
        UnresolvedReason.NO_PROGRESS: "supply_new_evidence_or_handoff",
    }[unresolved.reason]
    return PublicDiagnostic(
        DiagnosticCategory.SEMANTIC,
        unresolved.reason.value,
        definition_id,
        node_id,
        source_path,
        correction,
        unresolved.needed,
    )


def _usage_data(usage: Usage) -> dict[str, Any]:
    return {
        "coverage": usage.coverage.value,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "provider_attempts": usage.provider_attempts,
        "submitted_questions": usage.submitted_questions,
    }


def _answer_data(answer: PrimitiveAnswer) -> dict[str, Any]:
    if isinstance(answer, ChoiceAnswer):
        return {
            "primitive": "choice",
            "choice": answer.choice,
            "probabilities": dict(answer.probabilities),
            "confidence": answer.confidence,
        }
    if isinstance(answer, NoulAnswer):
        return {"primitive": "noul", "probability_yes": answer.probability_yes}
    assert isinstance(answer, ScoreAnswer)
    return {
        "primitive": "score",
        "score": answer.score,
        "legend": list(answer.legend),
        "probabilities": list(answer.probabilities),
        "confidence": answer.confidence,
    }


def _acceptance_data(acceptance: AcceptanceRecord | None) -> dict[str, Any] | None:
    if acceptance is None:
        return None
    return {
        "policy_id": acceptance.policy_id,
        "policy_version": acceptance.policy_version,
        "status": acceptance.status.value,
        "reasons": [
            reason if _PUBLIC_REASON(reason) else "private_reason_omitted"
            for reason in acceptance.reasons
        ],
    }


def serialize_decision_result(result: DecisionResult) -> dict[str, Any]:
    """Return the allowlisted public result; no context or evidence values enter it."""

    payload = {
        "schema_version": DECISION_RESULT_SCHEMA_VERSION,
        "answer": _answer_data(result.answer),
        "subjects": list(result.subjects),
        "evidence_refs": list(result.evidence_refs),
        "input_fingerprint": result.input_fingerprint,
        "requested_model": result.requested_model,
        "returned_model": result.returned_model,
        "usage": _usage_data(result.usage),
        "acceptance": _acceptance_data(result.acceptance),
    }
    try:
        serialized = _json_value(payload)
    except StableSerializationError as error:
        raise EventSerializationError(
            "decision result is not safely serializable"
        ) from error
    assert isinstance(serialized, dict)
    return serialized


@dataclass(frozen=True, slots=True)
class InspectionProjection:
    evidence_ids: frozenset[str] = frozenset()
    candidate_set_ids: frozenset[str] = frozenset()
    include_questions: bool = False
    include_unresolved_details: bool = False
    permitted: bool = False

    def __post_init__(self) -> None:
        if (
            self.evidence_ids
            or self.candidate_set_ids
            or self.include_questions
            or self.include_unresolved_details
        ) and not self.permitted:
            raise InspectionError("private inspection requires a permitted projection")

    @classmethod
    def permitted_exact(
        cls,
        *,
        evidence_ids: Sequence[str] = (),
        candidate_set_ids: Sequence[str] = (),
        include_questions: bool = False,
        include_unresolved_details: bool = False,
    ) -> InspectionProjection:
        return cls(
            frozenset(evidence_ids),
            frozenset(candidate_set_ids),
            include_questions,
            include_unresolved_details,
            True,
        )


@dataclass(frozen=True, slots=True)
class OmittedField:
    path: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class DecisionInspection:
    decision: Mapping[str, Any]
    evidence: tuple[Mapping[str, Any], ...]
    presented_candidates: tuple[Mapping[str, Any], ...]
    accepted_bindings: Mapping[str, str]
    unresolved: tuple[Mapping[str, Any], ...]
    omitted: tuple[OmittedField, ...]
    schema_version: str = INSPECTION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision": dict(self.decision),
            "evidence": [dict(item) for item in self.evidence],
            "presented_candidates": [dict(item) for item in self.presented_candidates],
            "accepted_bindings": dict(self.accepted_bindings),
            "unresolved": [dict(item) for item in self.unresolved],
            "omitted": [item.to_dict() for item in self.omitted],
        }


def inspect_decision(
    result: DecisionResult,
    store: EvidenceStore,
    *,
    candidate_set: CandidateSet | None = None,
    accepted_bindings: Mapping[str, str] | None = None,
    unresolved: Sequence[Unresolved] = (),
    projection: InspectionProjection | None = None,
) -> DecisionInspection:
    projection = InspectionProjection() if projection is None else projection
    records = tuple(store.get(reference) for reference in result.evidence_refs)
    judgments = tuple(
        record
        for record in records
        if isinstance(record, ModelJudgment)
        and record.input_fingerprint == result.input_fingerprint
        and record.answer == result.answer
    )
    if len(judgments) != 1:
        raise InspectionError("decision does not resolve to one recorded judgment")
    judgment = judgments[0]
    if (
        judgment.requested_model != result.requested_model
        or judgment.returned_model != result.returned_model
        or judgment.subjects != result.subjects
    ):
        raise InspectionError("decision metadata differs from its recorded judgment")
    view = store.project(result.evidence_refs, scope=judgment.scope)
    view_ids = {record.id for record in view}
    bindings = {} if accepted_bindings is None else dict(accepted_bindings)
    if any(reference not in view_ids for reference in bindings.values()):
        raise InspectionError("an accepted binding lacks recorded evidence")
    if result.acceptance is not None and not any(
        isinstance(record, AcceptanceEvidence)
        and record.judgment_ref == judgment.id
        and record.policy_id == result.acceptance.policy_id
        and record.policy_version == result.acceptance.policy_version
        and record.value == result.acceptance
        for record in view
    ):
        raise InspectionError("acceptance lacks a recorded policy evidence link")

    omitted: list[OmittedField] = []
    evidence: list[Mapping[str, Any]] = []
    for record in view:
        item: dict[str, Any] = {
            "id": record.id,
            "kind": record.kind.value,
            "source_id": record.source_id,
            "source_version": record.source_version,
            "dependencies": list(record.dependencies),
            "supersedes": list(record.supersedes),
            "conflicts_with": list(record.conflicts_with),
            "current": store.is_current(record.id),
        }
        value_path = f"evidence.{record.id}.value"
        if record.id in projection.evidence_ids:
            try:
                item["value"] = _json_value(record.value)
            except StableSerializationError:
                omitted.append(OmittedField(value_path, "value_not_serializable"))
        else:
            omitted.append(OmittedField(value_path, "not_permitted"))
        evidence.append(item)

    decision = serialize_decision_result(result)
    if projection.include_questions:
        decision["question"] = judgment.question_semantics
    else:
        omitted.append(OmittedField("decision.question", "not_permitted"))

    candidates: list[Mapping[str, Any]] = [
        {"key": key} for key in judgment.presented_candidate_keys
    ]
    if judgment.candidate_snapshot_digest is not None:
        if candidate_set is None:
            omitted.append(
                OmittedField("presented_candidates.details", "snapshot_unavailable")
            )
        elif (
            candidate_snapshot_digest(candidate_set)
            != judgment.candidate_snapshot_digest
        ):
            raise InspectionError(
                "candidate snapshot differs from the recorded decision"
            )
        elif candidate_set.id in projection.candidate_set_ids:
            candidates = []
            by_key = {
                candidate.key: candidate for candidate in candidate_set.candidates
            }
            for key in judgment.presented_candidate_keys:
                candidate = by_key.get(key)
                if candidate is None:
                    candidates.append({"key": key})
                    continue
                item = {
                    "key": candidate.key,
                    "description": candidate.description,
                    "source_id": candidate.source_id,
                    "source_version": candidate.source_version,
                }
                try:
                    item["value"] = _json_value(candidate.value)
                except StableSerializationError:
                    omitted.append(
                        OmittedField(
                            f"presented_candidates.{candidate.key}.value",
                            "value_not_serializable",
                        )
                    )
                candidates.append(item)
        else:
            omitted.append(
                OmittedField("presented_candidates.details", "not_permitted")
            )

    unresolved_data: list[Mapping[str, Any]] = []
    for index, unresolved_item in enumerate(unresolved):
        serialized: dict[str, Any] = {
            "reason": unresolved_item.reason.value,
            "subjects": list(unresolved_item.subjects),
            "attempted_actions": list(unresolved_item.attempted_actions),
            "needed": unresolved_item.needed,
        }
        if projection.include_unresolved_details:
            serialized["detail"] = unresolved_item.detail
        else:
            omitted.append(OmittedField(f"unresolved.{index}.detail", "not_permitted"))
        unresolved_data.append(serialized)

    return DecisionInspection(
        MappingProxyType(decision),
        tuple(MappingProxyType(dict(item)) for item in evidence),
        tuple(MappingProxyType(dict(item)) for item in candidates),
        MappingProxyType(bindings),
        tuple(MappingProxyType(dict(item)) for item in unresolved_data),
        tuple(omitted),
    )
