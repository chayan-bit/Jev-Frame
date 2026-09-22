from __future__ import annotations

import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from .definitions import InputValidationError, Tool, Usage
from .evaluation import (
    CaseSplit,
    EvaluationCase,
    EvaluationManifest,
    EvaluationRecord,
    EvaluationReport,
    MetricCount,
)
from .state import StableSerializationError, canonical_digest, canonical_json


class CalibrationError(InputValidationError):
    pass


class FrozenPolicyMismatch(CalibrationError):
    pass


class ShadowEffectError(CalibrationError):
    pass


class PolicyAction(str, Enum):
    ACCEPT = "accept"
    HANDOFF = "handoff"
    REJECT = "reject"


class PolicyArtifactStatus(str, Enum):
    PROPOSED = "proposed"


def _text(value: str, name: str) -> None:
    if type(value) is not str or not value:
        raise CalibrationError(f"{name} must be a non-empty string")


def _json_value(value: Any) -> Any:
    try:
        import json

        return json.loads(canonical_json(value))
    except StableSerializationError as error:
        raise CalibrationError("calibration value is not safely serializable") from error


@dataclass(frozen=True, slots=True)
class PolicyObservation:
    case_id: str
    group_id: str
    variant_id: str
    outcome: Any
    evidence_refs: tuple[str, ...]
    usage: Usage
    requested_model: str | None = None
    returned_model: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.case_id, "policy observation case id"),
            (self.group_id, "policy observation group id"),
            (self.variant_id, "policy observation variant id"),
        ):
            _text(value, name)
        if not isinstance(self.usage, Usage):
            raise CalibrationError("policy observation usage must use Usage")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise CalibrationError("policy observation evidence must be unique")
        object.__setattr__(self, "outcome", _json_value(self.outcome))

    @classmethod
    def from_record(cls, record: EvaluationRecord) -> PolicyObservation:
        return cls(
            record.case_id,
            record.group_id,
            record.variant_id,
            record.outcome,
            record.evidence_refs,
            record.observation.accounting.combined_usage,
            record.observation.requested_model,
            record.observation.returned_model,
        )


PolicyEvaluator = Callable[
    [PolicyObservation], PolicyAction | Awaitable[PolicyAction]
]


@dataclass(frozen=True, slots=True)
class PolicyCandidate:
    id: str
    version: str
    evaluator: PolicyEvaluator = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _text(self.id, "policy candidate id")
        _text(self.version, "policy candidate version")
        if not callable(self.evaluator):
            raise CalibrationError("policy candidate evaluator must be callable")


@dataclass(frozen=True, slots=True)
class PolicyCaseResult:
    case_id: str
    group_id: str
    action: PolicyAction
    supported_acceptance: bool
    correct_escalation: bool
    harmful_automatic_error: bool
    unnecessary_handoff: bool


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    candidate_id: str
    candidate_version: str
    split: CaseSplit
    results: tuple[PolicyCaseResult, ...]
    group_count: int
    coverage: MetricCount
    supported_acceptance: MetricCount
    correct_escalation: MetricCount
    harmful_automatic_error: MetricCount
    unnecessary_handoff: MetricCount

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_version": self.candidate_version,
            "split": self.split.value,
            "case_count": len(self.results),
            "independent_group_count": self.group_count,
            "coverage": self.coverage.to_dict(),
            "supported_acceptance": self.supported_acceptance.to_dict(),
            "correct_escalation": self.correct_escalation.to_dict(),
            "harmful_automatic_error": self.harmful_automatic_error.to_dict(),
            "unnecessary_handoff": self.unnecessary_handoff.to_dict(),
            "results": [
                {
                    "case_id": result.case_id,
                    "group_id": result.group_id,
                    "action": result.action.value,
                    "supported_acceptance": result.supported_acceptance,
                    "correct_escalation": result.correct_escalation,
                    "harmful_automatic_error": result.harmful_automatic_error,
                    "unnecessary_handoff": result.unnecessary_handoff,
                }
                for result in self.results
            ],
        }


@dataclass(frozen=True, slots=True)
class FrozenPolicyArtifact:
    evaluation_version: str
    policy_id: str
    policy_version: str
    manifest_id: str
    manifest_version: str
    manifest_digest: str
    validation_digest: str
    model_identity: str
    judgment_versions: Mapping[str, str]
    retrieval_configuration_digest: str
    dataset_versions: tuple[str, ...]
    status: PolicyArtifactStatus = PolicyArtifactStatus.PROPOSED

    def __post_init__(self) -> None:
        for value, name in (
            (self.evaluation_version, "evaluation version"),
            (self.policy_id, "policy id"),
            (self.policy_version, "policy version"),
            (self.manifest_id, "manifest id"),
            (self.manifest_version, "manifest version"),
            (self.manifest_digest, "manifest digest"),
            (self.validation_digest, "validation digest"),
            (self.model_identity, "model identity"),
            (self.retrieval_configuration_digest, "retrieval configuration digest"),
        ):
            _text(value, name)
        if not isinstance(self.status, PolicyArtifactStatus):
            raise CalibrationError("policy artifact status is invalid")
        versions = dict(self.judgment_versions)
        if any(type(key) is not str or not key or type(value) is not str or not value for key, value in versions.items()):
            raise CalibrationError("judgment versions must use non-empty strings")
        if not self.dataset_versions or len(self.dataset_versions) != len(
            set(self.dataset_versions)
        ) or any(
            type(value) is not str or not value for value in self.dataset_versions
        ):
            raise CalibrationError("dataset versions must be non-empty and unique")
        object.__setattr__(self, "judgment_versions", MappingProxyType(versions))

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_version": self.evaluation_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "manifest_id": self.manifest_id,
            "manifest_version": self.manifest_version,
            "manifest_digest": self.manifest_digest,
            "validation_digest": self.validation_digest,
            "model_identity": self.model_identity,
            "judgment_versions": dict(self.judgment_versions),
            "retrieval_configuration_digest": self.retrieval_configuration_digest,
            "dataset_versions": list(self.dataset_versions),
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    artifact: FrozenPolicyArtifact
    validation_evaluations: tuple[PolicyEvaluation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact.to_dict(),
            "validation_evaluations": [
                evaluation.to_dict() for evaluation in self.validation_evaluations
            ],
        }


@dataclass(frozen=True, slots=True)
class EvaluatorCorrection:
    case_id: str
    proposed_labels: Mapping[str, Any]
    rationale: str
    reviewed: bool = False

    def __post_init__(self) -> None:
        _text(self.case_id, "correction case id")
        _text(self.rationale, "correction rationale")
        if type(self.reviewed) is not bool:
            raise CalibrationError("correction reviewed flag must be a boolean")
        object.__setattr__(
            self,
            "proposed_labels",
            MappingProxyType(_json_value(self.proposed_labels)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "proposed_labels": dict(self.proposed_labels),
            "rationale": self.rationale,
            "reviewed": self.reviewed,
        }


@dataclass(frozen=True, slots=True)
class FrozenPolicyReport:
    artifact: FrozenPolicyArtifact
    held_out_evaluation: PolicyEvaluation

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact.to_dict(),
            "held_out_evaluation": self.held_out_evaluation.to_dict(),
        }


def _equal(value: Any, expected: Any) -> bool:
    return canonical_json(value) == canonical_json(expected)


def _case_map(manifest: EvaluationManifest) -> dict[str, EvaluationCase]:
    return {case.task.id: case for case in manifest.cases}


def _records(
    manifest: EvaluationManifest,
    report: EvaluationReport,
    *,
    variant_id: str,
    split: CaseSplit,
) -> tuple[tuple[EvaluationCase, EvaluationRecord], ...]:
    if (
        report.manifest_id != manifest.id
        or report.manifest_version != manifest.version
        or report.manifest_digest != manifest.digest
    ):
        raise CalibrationError("evaluation report does not match the manifest")
    cases = _case_map(manifest)
    selected = tuple(
        (cases[record.case_id], record)
        for record in report.records
        if record.variant_id == variant_id and record.split is split
    )
    expected = {
        case.task.id for case in manifest.cases if case.task.split is split
    }
    if (
        {record.case_id for _, record in selected} != expected
        or len(selected) != len(expected)
    ):
        raise CalibrationError("evaluation report is missing split records")
    return selected


async def _evaluate_candidate(
    candidate: PolicyCandidate,
    selected: Sequence[tuple[EvaluationCase, EvaluationRecord]],
    split: CaseSplit,
) -> PolicyEvaluation:
    results: list[PolicyCaseResult] = []
    for case, record in selected:
        action = candidate.evaluator(PolicyObservation.from_record(record))
        action = await action if inspect.isawaitable(action) else action
        if not isinstance(action, PolicyAction):
            raise CalibrationError("policy evaluator returned an invalid action")
        outcome_ok = any(
            _equal(record.outcome, expected)
            for expected in case.criteria.acceptable_outcomes
        )
        evidence = set(record.evidence_refs)
        evidence_ok = not case.criteria.acceptable_evidence_paths or any(
            path.issubset(evidence)
            for path in case.criteria.acceptable_evidence_paths
        )
        harmful = any(
            _equal(record.outcome, expected)
            for expected in case.criteria.harmful_outcomes
        )
        escalated = action in {PolicyAction.HANDOFF, PolicyAction.REJECT}
        results.append(
            PolicyCaseResult(
                record.case_id,
                record.group_id,
                action,
                action is PolicyAction.ACCEPT
                and outcome_ok
                and evidence_ok
                and not harmful,
                escalated and case.criteria.requires_escalation,
                action is PolicyAction.ACCEPT and harmful,
                escalated and case.criteria.solvable,
            )
        )
    groups: dict[str, list[PolicyCaseResult]] = defaultdict(list)
    for result in results:
        groups[result.group_id].append(result)
    case_by_group = {case.task.group_id: case for case, _ in selected}

    def metric(
        field_name: str,
        *,
        eligible: Callable[[EvaluationCase], bool] = lambda _: True,
        positive: bool,
    ) -> MetricCount:
        chosen = [
            values
            for group, values in groups.items()
            if eligible(case_by_group[group])
        ]
        count = sum(
            all(getattr(value, field_name) for value in values)
            if positive
            else any(getattr(value, field_name) for value in values)
            for values in chosen
        )
        return MetricCount(count, len(chosen))

    return PolicyEvaluation(
        candidate.id,
        candidate.version,
        split,
        tuple(results),
        len(groups),
        MetricCount(
            sum(
                any(value.action is PolicyAction.ACCEPT for value in values)
                for values in groups.values()
            ),
            len(groups),
        ),
        metric(
            "supported_acceptance",
            eligible=lambda case: case.criteria.solvable,
            positive=True,
        ),
        metric(
            "correct_escalation",
            eligible=lambda case: case.criteria.requires_escalation,
            positive=True,
        ),
        metric("harmful_automatic_error", positive=False),
        metric(
            "unnecessary_handoff",
            eligible=lambda case: case.criteria.solvable,
            positive=False,
        ),
    )


PolicySelector = Callable[
    [tuple[PolicyEvaluation, ...]], str | Awaitable[str]
]


def _split_digest(manifest: EvaluationManifest, split: CaseSplit) -> str:
    return canonical_digest(
        [
            case.task.to_dict()
            for case in manifest.cases
            if case.task.split is split
        ]
    )


async def calibrate_policies(
    manifest: EvaluationManifest,
    report: EvaluationReport,
    candidates: Sequence[PolicyCandidate],
    *,
    variant_id: str,
    evaluation_version: str,
    model_identity: str,
    judgment_versions: Mapping[str, str],
    retrieval_configuration: Mapping[str, Any],
    selector: PolicySelector,
) -> CalibrationResult:
    if not candidates or len({candidate.id for candidate in candidates}) != len(
        candidates
    ):
        raise CalibrationError("policy candidate ids must be non-empty and unique")
    selected = _records(
        manifest, report, variant_id=variant_id, split=CaseSplit.VALIDATION
    )
    if not selected:
        raise CalibrationError("policy calibration requires validation cases")
    evaluations = tuple(
        [
            await _evaluate_candidate(candidate, selected, CaseSplit.VALIDATION)
            for candidate in candidates
        ]
    )
    chosen_id = selector(evaluations)
    chosen_id = await chosen_id if inspect.isawaitable(chosen_id) else chosen_id
    chosen = next((candidate for candidate in candidates if candidate.id == chosen_id), None)
    if chosen is None:
        raise CalibrationError("selector returned an unknown policy candidate")
    artifact = FrozenPolicyArtifact(
        evaluation_version,
        chosen.id,
        chosen.version,
        manifest.id,
        manifest.version,
        manifest.digest,
        _split_digest(manifest, CaseSplit.VALIDATION),
        model_identity,
        judgment_versions,
        canonical_digest(retrieval_configuration),
        tuple(sorted({case.task.dataset_version for case in manifest.cases})),
    )
    return CalibrationResult(artifact, evaluations)


async def evaluate_frozen_policy(
    artifact: FrozenPolicyArtifact,
    manifest: EvaluationManifest,
    report: EvaluationReport,
    candidate: PolicyCandidate,
    *,
    variant_id: str,
    model_identity: str,
    judgment_versions: Mapping[str, str],
    retrieval_configuration: Mapping[str, Any],
) -> FrozenPolicyReport:
    if (
        artifact.status is not PolicyArtifactStatus.PROPOSED
        or artifact.policy_id != candidate.id
        or artifact.policy_version != candidate.version
        or artifact.manifest_id != manifest.id
        or artifact.manifest_version != manifest.version
        or artifact.manifest_digest != manifest.digest
        or artifact.validation_digest
        != _split_digest(manifest, CaseSplit.VALIDATION)
        or artifact.model_identity != model_identity
        or dict(artifact.judgment_versions) != dict(judgment_versions)
        or artifact.retrieval_configuration_digest
        != canonical_digest(retrieval_configuration)
        or artifact.dataset_versions
        != tuple(sorted({case.task.dataset_version for case in manifest.cases}))
    ):
        raise FrozenPolicyMismatch("held-out evaluation configuration is not frozen")
    selected = _records(
        manifest, report, variant_id=variant_id, split=CaseSplit.HELD_OUT
    )
    if not selected:
        raise CalibrationError("frozen policy evaluation requires held-out cases")
    evaluation = await _evaluate_candidate(candidate, selected, CaseSplit.HELD_OUT)
    return FrozenPolicyReport(artifact, evaluation)


class ShadowExecutor:
    """Executor boundary for advisory shadow runs; it dispatches no tools."""

    async def dispatch(self, tool: Tool, arguments: Mapping[str, Any]) -> Any:
        del tool, arguments
        raise ShadowEffectError("shadow comparisons cannot dispatch business tools")


@dataclass(frozen=True, slots=True)
class ShadowObservation:
    id: str
    policy_input: PolicyObservation
    actual_action: PolicyAction
    actual_outcome: Any = None
    actual_outcome_observed: bool = False

    def __post_init__(self) -> None:
        _text(self.id, "shadow observation id")
        if not isinstance(self.policy_input, PolicyObservation) or not isinstance(
            self.actual_action, PolicyAction
        ):
            raise CalibrationError("shadow observation fields are invalid")
        if type(self.actual_outcome_observed) is not bool:
            raise CalibrationError("shadow outcome flag must be a boolean")
        if not self.actual_outcome_observed and self.actual_outcome is not None:
            raise CalibrationError("an unobserved actual outcome must remain unknown")
        object.__setattr__(self, "actual_outcome", _json_value(self.actual_outcome))


ShadowOperation = Callable[
    [PolicyObservation, ShadowExecutor],
    PolicyAction | Awaitable[PolicyAction],
]


@dataclass(frozen=True, slots=True)
class ShadowResult:
    observation_id: str
    actual_action: PolicyAction
    candidate_action: PolicyAction
    actual_outcome: Any
    counterfactual_outcome: Any
    counterfactual_outcome_known: bool
    usage: Usage

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "actual_action": self.actual_action.value,
            "candidate_action": self.candidate_action.value,
            "actual_outcome": self.actual_outcome,
            "counterfactual_outcome": self.counterfactual_outcome,
            "counterfactual_outcome_known": self.counterfactual_outcome_known,
            "usage": _json_value(self.usage),
        }


async def run_shadow_comparison(
    observations: Sequence[ShadowObservation],
    operation: ShadowOperation,
) -> tuple[ShadowResult, ...]:
    if not observations or len({item.id for item in observations}) != len(observations):
        raise CalibrationError("shadow observation ids must be non-empty and unique")
    if not callable(operation):
        raise CalibrationError("shadow operation must be callable")
    executor = ShadowExecutor()
    results: list[ShadowResult] = []
    for observation in observations:
        action = operation(observation.policy_input, executor)
        action = await action if inspect.isawaitable(action) else action
        if not isinstance(action, PolicyAction):
            raise CalibrationError("shadow operation returned an invalid action")
        same_action = action is observation.actual_action
        known = same_action and observation.actual_outcome_observed
        results.append(
            ShadowResult(
                observation.id,
                observation.actual_action,
                action,
                observation.actual_outcome,
                observation.actual_outcome if known else None,
                known,
                observation.policy_input.usage,
            )
        )
    return tuple(results)
