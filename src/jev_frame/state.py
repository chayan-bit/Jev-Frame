from __future__ import annotations

import hashlib
import json
import math
import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel

from .definitions import (
    NO_FIT_KEY,
    Candidate,
    CandidateSet,
    JevFrameError,
    PrimitiveAnswer,
    SourceField,
    SourceSpan,
)


class StateError(JevFrameError):
    """Base class for evidence and candidate state failures."""


class StableSerializationError(StateError):
    """A value has no approved deterministic serialization."""


class EvidenceNotFoundError(StateError):
    """An evidence reference does not exist."""


class EvidenceScopeError(StateError):
    """Evidence is outside the requested scope."""


class StaleEvidenceError(StateError):
    """Evidence or one of its dependencies is no longer current."""


class ViewCapacityError(StateError):
    """A complete authorized evidence view exceeds its configured capacity."""


class SourceBindingError(StateError):
    """An exact source field or span cannot be resolved."""


class CandidateSelectionError(StateError):
    """A selected key is not in the exact candidate snapshot."""


class EvidenceKind(str, Enum):
    OBSERVATION = "observation"
    DERIVATION = "derivation"
    JUDGMENT = "judgment"
    ACCEPTANCE = "acceptance"
    EXECUTION_REFERENCE = "execution_reference"


def _name(value: str, field_name: str) -> None:
    if type(value) is not str or not value:
        raise StateError(f"{field_name} must be a non-empty string")


def _names(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)) or any(
        type(value) is not str or not value for value in values
    ):
        raise StateError(f"{field_name} must contain unique non-empty strings")


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceRecord:
    id: str
    value: Any
    source_id: str
    scope: str
    observed_at: float
    source_version: str | None = None
    expires_at: float | None = None
    dependencies: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    conflicts_with: tuple[str, ...] = ()
    kind: ClassVar[EvidenceKind]

    def __post_init__(self) -> None:
        _name(self.id, "evidence id")
        _name(self.source_id, "source id")
        _name(self.scope, "evidence scope")
        if type(self.observed_at) not in {int, float} or not math.isfinite(
            self.observed_at
        ):
            raise StateError("observed_at must be finite")
        if self.expires_at is not None and (
            type(self.expires_at) not in {int, float}
            or not math.isfinite(self.expires_at)
            or self.expires_at < self.observed_at
        ):
            raise StateError("expires_at must be finite and not precede observation")
        _names(self.dependencies, "evidence dependencies")
        _names(self.supersedes, "superseded evidence")
        _names(self.conflicts_with, "conflicting evidence")
        if (
            self.id in self.dependencies
            or self.id in self.supersedes
            or self.id in self.conflicts_with
        ):
            raise StateError("evidence cannot reference itself")


@dataclass(frozen=True, slots=True, kw_only=True)
class Observation(EvidenceRecord):
    kind: ClassVar[EvidenceKind] = EvidenceKind.OBSERVATION


@dataclass(frozen=True, slots=True, kw_only=True)
class Derivation(EvidenceRecord):
    transformation_id: str
    transformation_version: str
    kind: ClassVar[EvidenceKind] = EvidenceKind.DERIVATION

    def __post_init__(self) -> None:
        super(Derivation, self).__post_init__()
        _name(self.transformation_id, "transformation id")
        _name(self.transformation_version, "transformation version")
        if not self.dependencies:
            raise StateError("a derivation requires input evidence")


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelJudgment(EvidenceRecord):
    judgment_id: str
    judgment_version: str
    question_semantics: str
    subjects: tuple[str, ...]
    answer: PrimitiveAnswer
    input_fingerprint: str
    requested_model: str
    returned_model: str | None
    candidate_snapshot_digest: str | None = None
    kind: ClassVar[EvidenceKind] = EvidenceKind.JUDGMENT

    def __post_init__(self) -> None:
        super(ModelJudgment, self).__post_init__()
        for value, name in (
            (self.judgment_id, "judgment id"),
            (self.judgment_version, "judgment version"),
            (self.question_semantics, "question semantics"),
            (self.input_fingerprint, "input fingerprint"),
            (self.requested_model, "requested model"),
        ):
            _name(value, name)
        _names(self.subjects, "judgment subjects")
        if self.returned_model is not None:
            _name(self.returned_model, "returned model")


@dataclass(frozen=True, slots=True, kw_only=True)
class AcceptanceEvidence(EvidenceRecord):
    judgment_ref: str
    policy_id: str
    policy_version: str
    kind: ClassVar[EvidenceKind] = EvidenceKind.ACCEPTANCE

    def __post_init__(self) -> None:
        super(AcceptanceEvidence, self).__post_init__()
        _name(self.judgment_ref, "accepted judgment")
        _name(self.policy_id, "policy id")
        _name(self.policy_version, "policy version")
        if self.judgment_ref not in self.dependencies:
            raise StateError("acceptance must depend on its judgment")


class ExecutionState(str, Enum):
    PROPOSED = "proposed"
    AUTHORIZED = "authorized"
    IN_FLIGHT = "in_flight"
    SUCCEEDED = "succeeded"
    FAILED_BEFORE_EFFECT = "failed_before_effect"
    OUTCOME_UNKNOWN = "outcome_unknown"


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionReference(EvidenceRecord):
    operation_id: str
    state: ExecutionState
    kind: ClassVar[EvidenceKind] = EvidenceKind.EXECUTION_REFERENCE

    def __post_init__(self) -> None:
        super(ExecutionReference, self).__post_init__()
        _name(self.operation_id, "operation id")
        if not isinstance(self.state, ExecutionState):
            raise StateError("execution state must use ExecutionState")

    @property
    def completed(self) -> bool:
        return self.state is ExecutionState.SUCCEEDED


Evidence = (
    Observation | Derivation | ModelJudgment | AcceptanceEvidence | ExecutionReference
)


def _normalize(value: Any) -> Any:
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise StableSerializationError("non-finite floats are not stable values")
        return value
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="python", round_trip=True))
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _normalize(getattr(value, item.name))
            for item in fields(value)
            if not item.name.startswith("_")
        }
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise StableSerializationError("stable mappings require string keys")
        return {key: _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    raise StableSerializationError(
        f"unsupported stable value type: {type(value).__name__}"
    )


def canonical_json(value: Any) -> str:
    """Serialize an approved value deterministically without Python repr."""

    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def evidence_digest(record: Evidence) -> str:
    payload = {item.name: getattr(record, item.name) for item in fields(record)}
    payload["kind"] = record.kind.value
    return canonical_digest(payload)


def candidate_snapshot_digest(snapshot: CandidateSet) -> str:
    return canonical_digest(
        {
            "id": snapshot.id,
            "version": snapshot.version,
            "scope": snapshot.scope,
            "coverage": snapshot.coverage.value,
            "total_count": snapshot.total_count,
            "query": snapshot.query,
            "retrieval_parameters": snapshot.retrieval_parameters,
            "expansion_ref": snapshot.expansion_ref,
            "failure_reason": snapshot.failure_reason,
            "candidates": [
                {
                    "key": candidate.key,
                    "value": candidate.value,
                    "description": candidate.description,
                    "source_id": candidate.source_id,
                    "source_version": candidate.source_version,
                }
                for candidate in snapshot.candidates
            ],
        }
    )


class CandidateOutcome(str, Enum):
    SELECTED = "selected"
    NO_FIT = "no_fit"


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    snapshot_digest: str
    coverage: str
    outcome: CandidateOutcome
    candidate: Candidate | None = None


def select_candidate(snapshot: CandidateSet, key: str) -> CandidateSelection:
    digest = candidate_snapshot_digest(snapshot)
    if key == NO_FIT_KEY:
        return CandidateSelection(
            digest, snapshot.coverage.value, CandidateOutcome.NO_FIT
        )
    for candidate in snapshot.candidates:
        if candidate.key == key:
            return CandidateSelection(
                digest,
                snapshot.coverage.value,
                CandidateOutcome.SELECTED,
                candidate,
            )
    raise CandidateSelectionError(
        f"candidate key {key!r} is not in snapshot {snapshot.id}"
    )


@dataclass(frozen=True, slots=True)
class BoundSource:
    value: Any
    evidence_id: str
    source_id: str
    source_version: str | None
    locator: SourceField | SourceSpan


def bind_source(record: Observation, locator: SourceField | SourceSpan) -> BoundSource:
    value = record.value
    if isinstance(locator, SourceSpan):
        if type(value) is not str or locator.end > len(value):
            raise SourceBindingError("source span does not fit the retained text")
        selected = value[locator.start : locator.end]
    else:
        selected = value
        for part in locator.path:
            if (
                isinstance(selected, BaseModel)
                and type(part) is str
                and part in selected.__class__.model_fields
            ):
                selected = getattr(selected, part)
            elif (
                is_dataclass(selected)
                and not isinstance(selected, type)
                and type(part) is str
            ):
                allowed = {item.name for item in fields(selected)}
                if part not in allowed:
                    raise SourceBindingError(f"missing source field {part!r}")
                selected = getattr(selected, part)
            elif isinstance(selected, Mapping) and part in selected:
                selected = selected[part]
            elif (
                isinstance(selected, Sequence)
                and not isinstance(selected, (str, bytes))
                and type(part) is int
            ):
                if part < 0 or part >= len(selected):
                    raise SourceBindingError(f"source index {part} is out of range")
                selected = selected[part]
            else:
                raise SourceBindingError(f"missing source field {part!r}")
    return BoundSource(
        selected, record.id, record.source_id, record.source_version, locator
    )


class EvidenceStore:
    """Run-local append-only evidence with scope, conflict, and dependency indexes."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        if not callable(clock):
            raise StateError("evidence clock must be callable")
        self._clock = clock
        self._records: dict[str, Evidence] = {}
        self._dependents: dict[str, set[str]] = defaultdict(set)
        self._conflicts: dict[str, set[str]] = defaultdict(set)
        self._stale: set[str] = set()

    @property
    def records(self) -> tuple[Evidence, ...]:
        return tuple(self._records.values())

    def add(self, record: Evidence) -> Evidence:
        if not isinstance(
            record,
            (
                Observation,
                Derivation,
                ModelJudgment,
                AcceptanceEvidence,
                ExecutionReference,
            ),
        ):
            raise StateError("unsupported evidence record")
        if record.id in self._records:
            raise StateError(f"duplicate evidence id {record.id}")
        references = record.dependencies + record.supersedes + record.conflicts_with
        for reference in references:
            related = self._records.get(reference)
            if related is None:
                raise EvidenceNotFoundError(reference)
            if related.scope != record.scope:
                raise EvidenceScopeError("evidence relationships cannot cross scopes")

        self._records[record.id] = record
        for dependency in record.dependencies:
            self._dependents[dependency].add(record.id)
        for conflict in record.conflicts_with:
            self._conflicts[record.id].add(conflict)
            self._conflicts[conflict].add(record.id)
        for superseded in record.supersedes:
            self.invalidate(superseded)
        return record

    def get(self, evidence_id: str) -> Evidence:
        try:
            return self._records[evidence_id]
        except KeyError as error:
            raise EvidenceNotFoundError(evidence_id) from error

    def invalidate(self, evidence_id: str) -> frozenset[str]:
        self.get(evidence_id)
        queue = [evidence_id]
        affected: set[str] = set()
        while queue:
            current = queue.pop()
            if current in affected:
                continue
            affected.add(current)
            record = self._records[current]
            if not (isinstance(record, ExecutionReference) and record.completed):
                self._stale.add(current)
            queue.extend(self._dependents.get(current, ()))
        return frozenset(affected)

    def is_current(
        self,
        evidence_id: str,
        *,
        at: float | None = None,
        _checking: set[str] | None = None,
    ) -> bool:
        record = self.get(evidence_id)
        if isinstance(record, ExecutionReference) and record.completed:
            return True
        now = self._clock() if at is None else at
        if evidence_id in self._stale or (
            record.expires_at is not None and now >= record.expires_at
        ):
            return False
        checking = set() if _checking is None else _checking
        if evidence_id in checking:
            raise StateError("evidence dependency cycle")
        checking.add(evidence_id)
        try:
            return all(
                self.is_current(dependency, at=now, _checking=checking)
                for dependency in record.dependencies
            )
        finally:
            checking.remove(evidence_id)

    def require_current(self, evidence_id: str, scope: str) -> Evidence:
        record = self.get(evidence_id)
        if record.scope != scope:
            raise EvidenceScopeError(f"evidence {evidence_id} is outside scope {scope}")
        if not self.is_current(evidence_id):
            raise StaleEvidenceError(evidence_id)
        return record

    def project(
        self,
        evidence_ids: Sequence[str],
        *,
        scope: str,
        max_records: int | None = None,
    ) -> tuple[Evidence, ...]:
        if max_records is not None and (
            type(max_records) is not int or max_records < 0
        ):
            raise ViewCapacityError("view capacity must be a nonnegative integer")
        included: set[str] = set()
        queue = [(evidence_id, True) for evidence_id in evidence_ids]
        while queue:
            evidence_id, must_be_current = queue.pop()
            if must_be_current:
                record = self.require_current(evidence_id, scope)
            else:
                record = self.get(evidence_id)
                if record.scope != scope:
                    raise EvidenceScopeError(
                        f"evidence {evidence_id} is outside scope {scope}"
                    )
            if evidence_id in included:
                continue
            included.add(evidence_id)
            queue.extend(
                (dependency, must_be_current) for dependency in record.dependencies
            )
            queue.extend(
                (conflict, False) for conflict in self._conflicts.get(evidence_id, ())
            )
        if max_records is not None and len(included) > max_records:
            raise ViewCapacityError(
                f"complete evidence view needs {len(included)} records, capacity is {max_records}"
            )
        return tuple(record for key, record in self._records.items() if key in included)


def decision_fingerprint(
    *,
    semantic_version: str,
    policy_version: str,
    model_identity: str,
    projection_version: str,
    compiler_version: str,
    scope: str,
    evidence: Sequence[Evidence],
    candidate_sets: Sequence[CandidateSet] = (),
) -> str:
    return canonical_digest(
        {
            "semantic_version": semantic_version,
            "policy_version": policy_version,
            "model_identity": model_identity,
            "projection_version": projection_version,
            "compiler_version": compiler_version,
            "scope": scope,
            "evidence": [evidence_digest(record) for record in evidence],
            "candidate_sets": [
                candidate_snapshot_digest(snapshot) for snapshot in candidate_sets
            ],
        }
    )
