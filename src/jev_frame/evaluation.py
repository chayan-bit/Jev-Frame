from __future__ import annotations

import inspect
import json
import math
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from .definitions import InputValidationError, RunLimits, Usage, UsageCoverage
from .limits import LedgerSnapshot, UsageMeasurementKind
from .state import StableSerializationError, canonical_digest, canonical_json


class EvaluationError(InputValidationError):
    pass


class EvaluationLeakageError(EvaluationError):
    pass


class CaseSplit(str, Enum):
    VALIDATION = "validation"
    HELD_OUT = "held_out"


class BaselineKind(str, Enum):
    SUFFICIENT_EVIDENCE = "sufficient_evidence_jev"
    AGENTIC = "agentic_jev"
    DETERMINISTIC = "deterministic"
    HOST_WITH_JEV = "host_with_jev"
    HOST_WITHOUT_JEV = "host_without_jev"


class EvaluationDisposition(str, Enum):
    COMPLETED = "completed"
    HANDOFF = "handoff"
    UNRESOLVED = "unresolved"
    FAILED = "failed"


class EvaluationFailure(str, Enum):
    NONE = "none"
    RETRIEVAL = "retrieval_failure"
    SERVICE = "service_failure"


def _text(value: str, name: str) -> None:
    if type(value) is not str or not value:
        raise EvaluationError(f"{name} must be a non-empty string")


def _json_value(value: Any) -> Any:
    try:
        return json.loads(canonical_json(value))
    except StableSerializationError as error:
        raise EvaluationError("evaluation value is not safely serializable") from error


@dataclass(frozen=True, slots=True)
class CapabilityIdentity:
    id: str
    version: str

    def __post_init__(self) -> None:
        _text(self.id, "capability id")
        _text(self.version, "capability version")


@dataclass(frozen=True, slots=True)
class EvaluationTask:
    id: str
    source_lineage: str
    dataset_version: str
    group_id: str
    split: CaseSplit
    task_inputs: Any
    permitted_evidence: Mapping[str, Any]
    capabilities: tuple[CapabilityIdentity, ...]
    scope: str
    limits: RunLimits
    seed: int | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "case id"),
            (self.source_lineage, "source lineage"),
            (self.dataset_version, "dataset version"),
            (self.group_id, "source group id"),
            (self.scope, "case scope"),
        ):
            _text(value, name)
        if not isinstance(self.split, CaseSplit):
            raise EvaluationError("case split must use CaseSplit")
        if not isinstance(self.limits, RunLimits):
            raise EvaluationError("case limits must use RunLimits")
        if self.seed is not None and type(self.seed) is not int:
            raise EvaluationError("case seed must be an integer when supplied")
        if len({item.id for item in self.capabilities}) != len(self.capabilities):
            raise EvaluationError("case capability identities must be unique")
        object.__setattr__(self, "task_inputs", _json_value(self.task_inputs))
        object.__setattr__(
            self,
            "permitted_evidence",
            MappingProxyType(_json_value(self.permitted_evidence)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_lineage": self.source_lineage,
            "dataset_version": self.dataset_version,
            "group_id": self.group_id,
            "split": self.split.value,
            "task_inputs": self.task_inputs,
            "permitted_evidence": dict(self.permitted_evidence),
            "capabilities": [
                {"id": item.id, "version": item.version}
                for item in self.capabilities
            ],
            "scope": self.scope,
            "limits": _json_value(self.limits),
            "seed": self.seed,
        }


@dataclass(frozen=True, slots=True)
class EvaluationCriteria:
    acceptable_outcomes: tuple[Any, ...] = ()
    acceptable_evidence_paths: tuple[frozenset[str], ...] = ()
    harmful_outcomes: tuple[Any, ...] = ()
    private_labels: Mapping[str, Any] = field(default_factory=dict)
    solvable: bool = True
    requires_escalation: bool = False

    def __post_init__(self) -> None:
        if type(self.solvable) is not bool or type(self.requires_escalation) is not bool:
            raise EvaluationError("criteria flags must be booleans")
        if self.solvable and self.requires_escalation:
            raise EvaluationError("a solvable case cannot require escalation")
        object.__setattr__(
            self,
            "acceptable_outcomes",
            tuple(_json_value(item) for item in self.acceptable_outcomes),
        )
        object.__setattr__(
            self,
            "harmful_outcomes",
            tuple(_json_value(item) for item in self.harmful_outcomes),
        )
        object.__setattr__(
            self,
            "private_labels",
            MappingProxyType(_json_value(self.private_labels)),
        )
        for path in self.acceptable_evidence_paths:
            if not path or any(type(reference) is not str or not reference for reference in path):
                raise EvaluationError("acceptable evidence paths require references")


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    task: EvaluationTask
    criteria: EvaluationCriteria

    def __post_init__(self) -> None:
        if not isinstance(self.task, EvaluationTask) or not isinstance(
            self.criteria, EvaluationCriteria
        ):
            raise EvaluationError("evaluation cases require task and criteria records")


@dataclass(frozen=True, slots=True)
class EvaluationManifest:
    id: str
    version: str
    cases: tuple[EvaluationCase, ...]

    def __post_init__(self) -> None:
        _text(self.id, "manifest id")
        _text(self.version, "manifest version")
        if not self.cases or len({case.task.id for case in self.cases}) != len(
            self.cases
        ):
            raise EvaluationError("manifest case ids must be non-empty and unique")
        groups: dict[str, tuple[CaseSplit, str, str, bool, bool]] = {}
        for case in self.cases:
            group = (
                case.task.split,
                case.task.source_lineage,
                case.task.dataset_version,
                case.criteria.solvable,
                case.criteria.requires_escalation,
            )
            previous = groups.setdefault(case.task.group_id, group)
            if previous != group:
                raise EvaluationError(
                    "one source group cannot cross splits or evaluator categories"
                )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "id": self.id,
                "version": self.version,
                "tasks": [case.task.to_dict() for case in self.cases],
            }
        )


def _usage_from_ledger(snapshot: LedgerSnapshot) -> Usage:
    selected: dict[str, Any] = {}
    for measurement in snapshot.measurements:
        if measurement.kind not in {
            UsageMeasurementKind.OBSERVED,
            UsageMeasurementKind.UNKNOWN,
        }:
            continue
        previous = selected.get(measurement.operation_id)
        if previous is None or measurement.kind is UsageMeasurementKind.OBSERVED:
            selected[measurement.operation_id] = measurement
    measurements = tuple(selected.values())
    if not measurements:
        return Usage(
            UsageCoverage.COMPLETE
            if snapshot.provider_attempts == 0
            else UsageCoverage.UNKNOWN,
            0 if snapshot.provider_attempts == 0 else None,
            0 if snapshot.provider_attempts == 0 else None,
            snapshot.provider_attempts,
            snapshot.submitted_questions,
        )
    coverage = (
        UsageCoverage.COMPLETE
        if all(item.coverage is UsageCoverage.COMPLETE for item in measurements)
        else UsageCoverage.UNKNOWN
        if all(item.coverage is UsageCoverage.UNKNOWN for item in measurements)
        else UsageCoverage.PARTIAL
    )
    input_tokens = (
        sum(item.input_tokens for item in measurements if item.input_tokens is not None)
        if all(item.input_tokens is not None for item in measurements)
        else None
    )
    output_tokens = (
        sum(
            item.output_tokens
            for item in measurements
            if item.output_tokens is not None
        )
        if all(item.output_tokens is not None for item in measurements)
        else None
    )
    return Usage(
        coverage,
        input_tokens,
        output_tokens,
        snapshot.provider_attempts,
        snapshot.submitted_questions,
    )


def _combine_usage(values: Sequence[Usage]) -> Usage:
    if not values:
        return Usage(UsageCoverage.COMPLETE, 0, 0)
    coverage = (
        UsageCoverage.COMPLETE
        if all(value.coverage is UsageCoverage.COMPLETE for value in values)
        else UsageCoverage.UNKNOWN
        if all(value.coverage is UsageCoverage.UNKNOWN for value in values)
        else UsageCoverage.PARTIAL
    )
    return Usage(
        coverage,
        (
            sum(value.input_tokens for value in values if value.input_tokens is not None)
            if all(value.input_tokens is not None for value in values)
            else None
        ),
        (
            sum(
                value.output_tokens
                for value in values
                if value.output_tokens is not None
            )
            if all(value.output_tokens is not None for value in values)
            else None
        ),
        sum(value.provider_attempts for value in values),
        sum(value.submitted_questions for value in values),
    )


@dataclass(frozen=True, slots=True)
class EvaluationAccounting:
    shared_usage: Usage
    tool_attempts: int = 0
    planner_calls: int = 0
    foreign_usage: Usage | None = None
    foreign_usage_expected: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.shared_usage, Usage):
            raise EvaluationError("shared usage must use Usage")
        if self.foreign_usage is not None and not isinstance(self.foreign_usage, Usage):
            raise EvaluationError("foreign usage must use Usage when supplied")
        if type(self.foreign_usage_expected) is not bool or any(
            type(value) is not int or value < 0
            for value in (self.tool_attempts, self.planner_calls)
        ):
            raise EvaluationError("accounting counts and flags are invalid")

    @classmethod
    def from_ledger(
        cls,
        snapshot: LedgerSnapshot,
        *,
        foreign_usage: Usage | None = None,
        foreign_usage_expected: bool = False,
    ) -> EvaluationAccounting:
        return cls(
            _usage_from_ledger(snapshot),
            snapshot.tool_attempts,
            snapshot.planner_calls,
            foreign_usage,
            foreign_usage_expected,
        )

    @property
    def combined_usage(self) -> Usage:
        if self.foreign_usage is not None:
            return _combine_usage((self.shared_usage, self.foreign_usage))
        if self.foreign_usage_expected:
            return Usage(
                UsageCoverage.UNKNOWN
                if self.shared_usage.coverage is UsageCoverage.UNKNOWN
                else UsageCoverage.PARTIAL,
                provider_attempts=self.shared_usage.provider_attempts,
                submitted_questions=self.shared_usage.submitted_questions,
            )
        return self.shared_usage


@dataclass(frozen=True, slots=True)
class EvaluationObservation:
    disposition: EvaluationDisposition
    outcome: Any = None
    evidence_refs: tuple[str, ...] = ()
    failure: EvaluationFailure = EvaluationFailure.NONE
    automatic: bool = False
    captured_inputs: tuple[Any, ...] = ()
    accounting: EvaluationAccounting = field(
        default_factory=lambda: EvaluationAccounting(Usage())
    )
    verified_cost: float | None = None
    stage_latencies: Mapping[str, float] = field(default_factory=dict)
    requested_model: str | None = None
    returned_model: str | None = None
    sdk_version: str | None = None
    framework_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, EvaluationDisposition) or not isinstance(
            self.failure, EvaluationFailure
        ):
            raise EvaluationError("observation disposition and failure are invalid")
        if type(self.automatic) is not bool:
            raise EvaluationError("observation automatic flag must be a boolean")
        if len(self.evidence_refs) != len(set(self.evidence_refs)) or any(
            type(value) is not str or not value for value in self.evidence_refs
        ):
            raise EvaluationError("observation evidence references must be unique")
        if self.verified_cost is not None and (
            type(self.verified_cost) not in {int, float}
            or not math.isfinite(self.verified_cost)
            or self.verified_cost < 0
        ):
            raise EvaluationError("verified cost must be finite and nonnegative")
        latencies = dict(self.stage_latencies)
        if any(
            type(value) not in {int, float}
            or not math.isfinite(value)
            or value < 0
            for value in latencies.values()
        ):
            raise EvaluationError("stage latencies must be finite and nonnegative")
        for value, name in (
            (self.requested_model, "requested model"),
            (self.returned_model, "returned model"),
            (self.sdk_version, "SDK version"),
            (self.framework_version, "framework version"),
        ):
            if value is not None:
                _text(value, name)
        object.__setattr__(self, "outcome", _json_value(self.outcome))
        object.__setattr__(
            self,
            "captured_inputs",
            tuple(_json_value(value) for value in self.captured_inputs),
        )
        object.__setattr__(self, "stage_latencies", MappingProxyType(latencies))


@dataclass(frozen=True, slots=True)
class SemanticConfiguration:
    tools: int = 0
    judgments: int = 0
    candidate_providers: int = 0
    binding_contracts: int = 0
    domain_policies: int = 0
    controller_changes: int = 0

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 0
            for value in (
                self.tools,
                self.judgments,
                self.candidate_providers,
                self.binding_contracts,
                self.domain_policies,
                self.controller_changes,
            )
        ):
            raise EvaluationError("semantic configuration counts must be nonnegative")


EvaluationOperation = Callable[
    [EvaluationTask], EvaluationObservation | Awaitable[EvaluationObservation]
]


@dataclass(frozen=True, slots=True)
class EvaluationVariant:
    id: str
    kind: BaselineKind
    operation: EvaluationOperation = field(repr=False, compare=False)
    configuration: SemanticConfiguration = field(
        default_factory=SemanticConfiguration
    )

    def __post_init__(self) -> None:
        _text(self.id, "evaluation variant id")
        if not isinstance(self.kind, BaselineKind) or not callable(self.operation):
            raise EvaluationError("evaluation variant kind and operation are invalid")


@dataclass(frozen=True, slots=True)
class MetricCount:
    count: int
    denominator: int

    @property
    def rate(self) -> float | None:
        return self.count / self.denominator if self.denominator else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "denominator": self.denominator,
            "rate": self.rate,
        }


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    case_id: str
    group_id: str
    split: CaseSplit
    source_lineage: str
    dataset_version: str
    seed: int | None
    capabilities: tuple[CapabilityIdentity, ...]
    variant_id: str
    disposition: EvaluationDisposition
    failure: EvaluationFailure
    supported_completion: bool
    correct_escalation: bool
    harmful_automatic_error: bool
    unnecessary_handoff: bool
    outcome: Any
    evidence_refs: tuple[str, ...]
    latency_seconds: float
    observation: EvaluationObservation = field(repr=False)
    solvable: bool = field(repr=False)
    requires_escalation: bool = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        usage = self.observation.accounting.combined_usage
        return {
            "case_id": self.case_id,
            "group_id": self.group_id,
            "split": self.split.value,
            "source_lineage": self.source_lineage,
            "dataset_version": self.dataset_version,
            "seed": self.seed,
            "capabilities": [
                {"id": item.id, "version": item.version}
                for item in self.capabilities
            ],
            "variant_id": self.variant_id,
            "disposition": self.disposition.value,
            "failure": self.failure.value,
            "supported_completion": self.supported_completion,
            "correct_escalation": self.correct_escalation,
            "harmful_automatic_error": self.harmful_automatic_error,
            "unnecessary_handoff": self.unnecessary_handoff,
            "outcome": self.outcome,
            "evidence_refs": list(self.evidence_refs),
            "latency_seconds": self.latency_seconds,
            "stage_latencies": dict(self.observation.stage_latencies),
            "usage": _json_value(usage),
            "verified_cost": self.observation.verified_cost,
            "requested_model": self.observation.requested_model,
            "returned_model": self.observation.returned_model,
            "sdk_version": self.observation.sdk_version,
            "framework_version": self.observation.framework_version,
        }


def _latency_summary(records: Sequence[EvaluationRecord]) -> dict[str, Any]:
    values = sorted(record.latency_seconds for record in records)
    if not values:
        return {"count": 0, "minimum": None, "median": None, "p95": None, "maximum": None}
    return {
        "count": len(values),
        "minimum": values[0],
        "median": values[(len(values) - 1) // 2],
        "p95": values[math.ceil(len(values) * 0.95) - 1],
        "maximum": values[-1],
    }


@dataclass(frozen=True, slots=True)
class VariantSummary:
    variant_id: str
    kind: BaselineKind
    case_count: int
    group_count: int
    supported_completion: MetricCount
    correct_escalation: MetricCount
    harmful_automatic_error: MetricCount
    unnecessary_handoff: MetricCount
    retrieval_failure: MetricCount
    service_failure: MetricCount
    latency: Mapping[str, Any]
    usage: Usage
    verified_cost_total: float | None
    verified_cost_per_supported_completion: float | None
    semantic_configuration: SemanticConfiguration

    @property
    def unfamiliar_combinations_need_controller_change(self) -> bool:
        return self.semantic_configuration.controller_changes > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "kind": self.kind.value,
            "case_count": self.case_count,
            "independent_group_count": self.group_count,
            "supported_completion": self.supported_completion.to_dict(),
            "correct_escalation": self.correct_escalation.to_dict(),
            "harmful_automatic_error": self.harmful_automatic_error.to_dict(),
            "unnecessary_handoff": self.unnecessary_handoff.to_dict(),
            "retrieval_failure": self.retrieval_failure.to_dict(),
            "service_failure": self.service_failure.to_dict(),
            "latency": dict(self.latency),
            "usage": _json_value(self.usage),
            "verified_cost_total": self.verified_cost_total,
            "verified_cost_per_supported_completion": self.verified_cost_per_supported_completion,
            "semantic_configuration": _json_value(self.semantic_configuration),
            "runtime_generality": {
                "controller_changes": self.semantic_configuration.controller_changes,
                "new_valid_combinations_without_core_change": not self.unfamiliar_combinations_need_controller_change,
            },
        }


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    manifest_id: str
    manifest_version: str
    manifest_digest: str
    records: tuple[EvaluationRecord, ...]
    summaries: tuple[VariantSummary, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "manifest_version": self.manifest_version,
            "manifest_digest": self.manifest_digest,
            "records": [record.to_dict() for record in self.records],
            "summaries": [summary.to_dict() for summary in self.summaries],
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict())


def _contains_value(container: Any, target: Any) -> bool:
    if type(container) is type(target) and container == target:
        return True
    if isinstance(container, Mapping):
        return any(_contains_value(value, target) for value in container.values())
    if isinstance(container, (list, tuple)):
        return any(_contains_value(value, target) for value in container)
    return False


def _matches(value: Any, expected: Sequence[Any]) -> bool:
    serialized = canonical_json(value)
    return any(serialized == canonical_json(item) for item in expected)


def _record(
    case: EvaluationCase,
    variant: EvaluationVariant,
    observation: EvaluationObservation,
    latency: float,
) -> EvaluationRecord:
    for label in case.criteria.private_labels.values():
        if any(_contains_value(value, label) for value in observation.captured_inputs):
            raise EvaluationLeakageError(
                f"evaluator-only value reached captured inputs for {case.task.id}"
            )
    evidence = set(observation.evidence_refs)
    evidence_ok = not case.criteria.acceptable_evidence_paths or any(
        path.issubset(evidence) for path in case.criteria.acceptable_evidence_paths
    )
    outcome_ok = bool(case.criteria.acceptable_outcomes) and _matches(
        observation.outcome, case.criteria.acceptable_outcomes
    )
    harmful = observation.automatic and _matches(
        observation.outcome, case.criteria.harmful_outcomes
    )
    escalated = observation.disposition in {
        EvaluationDisposition.HANDOFF,
        EvaluationDisposition.UNRESOLVED,
    }
    supported = (
        observation.disposition is EvaluationDisposition.COMPLETED
        and outcome_ok
        and evidence_ok
        and not harmful
    )
    return EvaluationRecord(
        case.task.id,
        case.task.group_id,
        case.task.split,
        case.task.source_lineage,
        case.task.dataset_version,
        case.task.seed,
        case.task.capabilities,
        variant.id,
        observation.disposition,
        observation.failure,
        supported,
        escalated and case.criteria.requires_escalation,
        harmful,
        escalated and case.criteria.solvable,
        observation.outcome,
        observation.evidence_refs,
        latency,
        observation,
        case.criteria.solvable,
        case.criteria.requires_escalation,
    )


def _metric(
    groups: Mapping[str, Sequence[EvaluationRecord]],
    *,
    eligible: Callable[[Sequence[EvaluationRecord]], bool],
    matched: Callable[[EvaluationRecord], bool],
    positive: bool,
) -> MetricCount:
    selected = [records for records in groups.values() if eligible(records)]
    count = sum(
        all(matched(record) for record in records)
        if positive
        else any(matched(record) for record in records)
        for records in selected
    )
    return MetricCount(count, len(selected))


def _summary(
    variant: EvaluationVariant, records: Sequence[EvaluationRecord]
) -> VariantSummary:
    groups: dict[str, list[EvaluationRecord]] = defaultdict(list)
    for record in records:
        groups[record.group_id].append(record)
    all_groups = lambda _: True
    solvable = lambda rows: rows[0].solvable
    escalation = lambda rows: rows[0].requires_escalation
    usages = tuple(record.observation.accounting.combined_usage for record in records)
    costs = tuple(record.observation.verified_cost for record in records)
    supported_cases = sum(record.supported_completion for record in records)
    verified_total = (
        sum(cost for cost in costs if cost is not None)
        if all(cost is not None for cost in costs)
        else None
    )
    return VariantSummary(
        variant.id,
        variant.kind,
        len(records),
        len(groups),
        _metric(
            groups,
            eligible=solvable,
            matched=lambda record: record.supported_completion,
            positive=True,
        ),
        _metric(
            groups,
            eligible=escalation,
            matched=lambda record: record.correct_escalation,
            positive=True,
        ),
        _metric(
            groups,
            eligible=all_groups,
            matched=lambda record: record.harmful_automatic_error,
            positive=False,
        ),
        _metric(
            groups,
            eligible=solvable,
            matched=lambda record: record.unnecessary_handoff,
            positive=False,
        ),
        _metric(
            groups,
            eligible=all_groups,
            matched=lambda record: record.failure is EvaluationFailure.RETRIEVAL,
            positive=False,
        ),
        _metric(
            groups,
            eligible=all_groups,
            matched=lambda record: record.failure is EvaluationFailure.SERVICE,
            positive=False,
        ),
        MappingProxyType(_latency_summary(records)),
        _combine_usage(usages),
        verified_total,
        (
            verified_total / supported_cases
            if verified_total is not None and supported_cases
            else None
        ),
        variant.configuration,
    )


async def run_evaluations(
    manifest: EvaluationManifest,
    variants: Sequence[EvaluationVariant],
    *,
    clock: Callable[[], float] = time.perf_counter,
) -> EvaluationReport:
    if not isinstance(manifest, EvaluationManifest):
        raise EvaluationError("manifest must use EvaluationManifest")
    if not variants or len({variant.id for variant in variants}) != len(variants):
        raise EvaluationError("evaluation variant ids must be non-empty and unique")
    records: list[EvaluationRecord] = []
    for variant in variants:
        for case in manifest.cases:
            started = clock()
            try:
                result = variant.operation(case.task)
                observation = await result if inspect.isawaitable(result) else result
                if not isinstance(observation, EvaluationObservation):
                    raise EvaluationError(
                        "evaluation operations must return EvaluationObservation"
                    )
            except EvaluationLeakageError:
                raise
            except Exception:  # noqa: BLE001 - preserve the category, not private text
                observation = EvaluationObservation(
                    EvaluationDisposition.FAILED,
                    failure=EvaluationFailure.SERVICE,
                )
            latency = clock() - started
            if not math.isfinite(latency) or latency < 0:
                raise EvaluationError("evaluation clock produced invalid latency")
            records.append(_record(case, variant, observation, latency))
    summaries = tuple(
        _summary(
            variant,
            tuple(record for record in records if record.variant_id == variant.id),
        )
        for variant in variants
    )
    return EvaluationReport(
        manifest.id,
        manifest.version,
        manifest.digest,
        tuple(records),
        summaries,
    )
