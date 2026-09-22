from __future__ import annotations

import inspect
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import Any, Generic, TypeVar, get_type_hints

from .decisions import DecisionInputs
from .definitions import (
    MISSING,
    DecisionResult,
    DefinitionError,
    InputValidationError,
    Judgment,
    RunContext,
    TaskInputBinding,
    TerminalStatus,
    Tool,
    ToolEffect,
    Unresolved,
    UnresolvedReason,
    Usage,
    _freeze_candidate_value,
    ensure_supported_type,
    validate_value,
)
from .planning import (
    EvidenceValue,
    GeneratedText,
    PlannerCapability,
    PlannerEngine,
    PlannerHandoff,
    PlannerRequest,
    PlannerTurn,
    PlanningResult,
    PlanRevision,
    PlanStep,
    ProposedResult,
    StepOutcome,
)
from .runtime import Runtime
from .state import (
    EvidenceStore,
    Observation,
    StateError,
    canonical_digest,
    canonical_json,
)


class ArtifactRecipeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactCheckResult:
    passed: bool
    message: str
    field_ref: str | None = None
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        if type(self.passed) is not bool:
            raise ArtifactRecipeError("artifact check result must be boolean")
        if type(self.message) is not str or not self.message:
            raise ArtifactRecipeError("artifact check result requires a message")
        for value, name in (
            (self.field_ref, "field reference"),
            (self.evidence_ref, "evidence reference"),
        ):
            if value is not None and (type(value) is not str or not value):
                raise ArtifactRecipeError(f"artifact {name} must be non-empty")


def _field_names(values: Sequence[str], name: str) -> tuple[str, ...]:
    result = tuple(values)
    if len(result) != len(set(result)) or any(
        type(value) is not str or not value for value in result
    ):
        raise ArtifactRecipeError(f"{name} must contain unique non-empty names")
    return result


@dataclass(frozen=True, slots=True)
class ArtifactCheck:
    capability: PlannerCapability
    artifact_parameter: str
    supports_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.capability, PlannerCapability):
            raise ArtifactRecipeError("artifact check requires a planner capability")
        if type(self.artifact_parameter) is not str or not self.artifact_parameter:
            raise ArtifactRecipeError("artifact check requires an artifact parameter")
        parameters = set(inspect.signature(self.capability.tool.function).parameters)
        if self.artifact_parameter not in parameters:
            raise ArtifactRecipeError("artifact check parameter is not in its tool")
        if self.artifact_parameter in self.capability.fixed_arguments:
            raise ArtifactRecipeError("artifact check parameter cannot be fixed")
        if self.capability.generated_parameters:
            raise ArtifactRecipeError("artifact checks cannot use generated parameters")
        if parameters != {
            self.artifact_parameter,
            *self.capability.fixed_arguments,
        }:
            raise ArtifactRecipeError("artifact check parameters must be fixed or artifact")
        if self.capability.tool.output_type is not ArtifactCheckResult:
            raise ArtifactRecipeError("artifact check must return ArtifactCheckResult")
        object.__setattr__(
            self,
            "supports_fields",
            _field_names(self.supports_fields, "supported fields"),
        )

    @property
    def id(self) -> str:
        return self.capability.tool.id


ArtifactT = TypeVar("ArtifactT")
SubjectFactory = Callable[[ArtifactT], Mapping[str, Any]]
SemanticClassifier = Callable[[DecisionResult], ArtifactCheckResult]


@dataclass(frozen=True, slots=True)
class ArtifactSemanticCheck(Generic[ArtifactT]):
    judgment: Judgment
    subjects: SubjectFactory[ArtifactT] = field(repr=False, compare=False)
    classify: SemanticClassifier = field(repr=False, compare=False)
    evidence_refs: Mapping[str, str] = field(default_factory=dict)
    supports_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.judgment, Judgment):
            raise ArtifactRecipeError("semantic check requires a judgment")
        if not callable(self.subjects) or not callable(self.classify):
            raise ArtifactRecipeError("semantic check callbacks must be callable")
        if not isinstance(self.evidence_refs, Mapping) or any(
            type(name) is not str
            or not name
            or type(reference) is not str
            or not reference
            for name, reference in self.evidence_refs.items()
        ):
            raise ArtifactRecipeError("semantic evidence references must be named ids")
        expected_evidence = {selector.name for selector in self.judgment.evidence}
        if set(self.evidence_refs) != expected_evidence:
            raise ArtifactRecipeError(
                "semantic evidence references must match judgment selectors"
            )
        object.__setattr__(
            self, "evidence_refs", MappingProxyType(dict(self.evidence_refs))
        )
        object.__setattr__(
            self,
            "supports_fields",
            _field_names(self.supports_fields, "supported fields"),
        )

    @property
    def id(self) -> str:
        return self.judgment.id


@dataclass(frozen=True, slots=True)
class ArtifactCompletionContract:
    required_checks: tuple[str, ...]
    required_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "required_checks",
            _field_names(self.required_checks, "required checks"),
        )
        object.__setattr__(
            self,
            "required_fields",
            _field_names(self.required_fields, "required fields"),
        )
        if not self.required_checks:
            raise ArtifactRecipeError("artifact completion requires at least one check")


class ArtifactCheckKind(str, Enum):
    DETERMINISTIC = "deterministic"
    SEMANTIC = "semantic"


@dataclass(frozen=True, slots=True)
class ArtifactRevision(Generic[ArtifactT]):
    id: str
    digest: str
    value: ArtifactT
    generator_id: str
    generator_version: str
    evidence_ref: str
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArtifactFinding:
    check_id: str
    check_kind: ArtifactCheckKind
    artifact_revision_id: str
    passed: bool
    required: bool
    message: str
    field_ref: str | None
    evidence_ref: str | None
    source_refs: tuple[str, ...]
    supports_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GenerateVerifyResult(Generic[ArtifactT]):
    status: TerminalStatus
    value: ArtifactT | Any = MISSING
    revisions: tuple[ArtifactRevision[ArtifactT], ...] = ()
    findings: tuple[ArtifactFinding, ...] = ()
    unresolved: tuple[Unresolved, ...] = ()
    planner_usage: tuple[Usage, ...] = ()
    step_usage: tuple[Usage, ...] = ()


@dataclass(frozen=True, slots=True)
class _CheckSpec:
    id: str
    kind: ArtifactCheckKind
    capability: PlannerCapability
    artifact_parameter: str
    supports_fields: tuple[str, ...]


class _GenerateVerifyPlanner(Generic[ArtifactT]):
    def __init__(
        self,
        recipe: GenerateVerifyRecipe[ArtifactT],
        deterministic: tuple[_CheckSpec, ...],
        semantic: tuple[_CheckSpec, ...],
        context: RunContext,
        store: EvidenceStore,
    ) -> None:
        self.recipe = recipe
        self.deterministic = deterministic
        self.semantic = semantic
        self.context = context
        self.store = store
        self.stage = "initial"
        self.processed = 0
        self.current: ArtifactRevision[ArtifactT] | None = None
        self.revisions: list[ArtifactRevision[ArtifactT]] = []
        self.findings: list[ArtifactFinding] = []
        self.digests: set[str] = set()
        self.stop_reason: UnresolvedReason | None = None
        self.stop_detail = ""

    def __call__(self, request: PlannerRequest) -> PlannerTurn:
        outcomes = request.outcomes[self.processed :]
        self.processed = len(request.outcomes)
        if self.stage == "initial":
            return self._generate(request.objective)
        if self.stage == "generation":
            return self._after_generation(outcomes, request.objective)
        if self.stage == "deterministic":
            return self._after_checks(
                outcomes, self.deterministic, request.objective
            )
        if self.stage == "semantic":
            return self._after_checks(outcomes, self.semantic, request.objective)
        raise ArtifactRecipeError("artifact planner entered an invalid state")

    def _generate(self, prompt: str) -> PlannerTurn:
        self.stage = "generation"
        generator = self.recipe.generator
        return PlannerTurn(
            PlanStep(
                "generate-artifact",
                generator.tool.id,
                {
                    self.recipe.prompt_parameter: GeneratedText(
                        prompt, generator.tool.id, generator.tool.version
                    )
                },
            )
        )

    def _after_generation(
        self, outcomes: tuple[StepOutcome, ...], objective: str
    ) -> PlannerTurn:
        outcome = outcomes[0] if outcomes else None
        if (
            outcome is None
            or outcome.capability_id != self.recipe.generator.tool.id
            or outcome.status is not TerminalStatus.COMPLETED
            or outcome.evidence_ref is None
        ):
            return self._stop(
                UnresolvedReason.MISSING_CAPABILITY,
                "the registered artifact generator did not complete",
            )
        try:
            value = validate_value(
                self.recipe.artifact_type, outcome.value, "artifact"
            )
            value = _freeze_candidate_value(value)
            digest = canonical_digest(value)
        except (
            DefinitionError,
            InputValidationError,
            StateError,
            TypeError,
            ValueError,
        ):
            return self._stop(
                UnresolvedReason.UNACCEPTED_JUDGMENT,
                "the generated artifact was not a stable supported value",
            )
        if digest in self.digests:
            return self._stop(
                UnresolvedReason.NO_PROGRESS,
                "the generator repeated an unchanged artifact",
            )
        self.digests.add(digest)
        root_id = self.context.run_id
        assert root_id is not None
        revision_id = f"{root_id}:artifact:{digest}"
        record = Observation(
            id=revision_id,
            value=value,
            source_id=f"generator:{self.recipe.generator.tool.id}",
            scope=self.context.scope,
            observed_at=self.context.clock(),
            source_version=self.recipe.generator.tool.version,
            dependencies=(outcome.evidence_ref,),
        )
        self.store.add(record)
        revision = ArtifactRevision(
            revision_id,
            digest,
            value,
            self.recipe.generator.tool.id,
            self.recipe.generator.tool.version,
            revision_id,
            tuple(
                dict.fromkeys(
                    (
                        outcome.evidence_ref,
                        *self.recipe.generator.tool.requires_evidence,
                    )
                )
            ),
        )
        self.current = revision
        self.revisions.append(revision)
        if self.deterministic:
            return self._checks(self.deterministic)
        if self.semantic:
            return self._checks(self.semantic)
        return self._complete()

    def _checks(self, checks: tuple[_CheckSpec, ...]) -> PlannerTurn:
        assert self.current is not None
        self.stage = checks[0].kind.value
        return PlannerTurn(
            PlanRevision(
                tuple(
                    PlanStep(
                        f"{check.kind.value}-{check.id}",
                        check.capability.tool.id,
                        {
                            check.artifact_parameter: EvidenceValue(
                                self.current.evidence_ref
                            )
                        },
                    )
                    for check in checks
                )
            )
        )

    def _after_checks(
        self,
        outcomes: tuple[StepOutcome, ...],
        checks: tuple[_CheckSpec, ...],
        objective: str,
    ) -> PlannerTurn:
        assert self.current is not None
        by_capability = {outcome.capability_id: outcome for outcome in outcomes}
        new_findings: list[ArtifactFinding] = []
        for check in checks:
            outcome = by_capability.get(check.capability.tool.id)
            result = (
                outcome.value
                if outcome is not None
                and outcome.status is TerminalStatus.COMPLETED
                and isinstance(outcome.value, ArtifactCheckResult)
                else ArtifactCheckResult(
                    False,
                    f"{check.kind.value} check did not produce a valid result",
                )
            )
            evidence_ref = None if outcome is None else outcome.evidence_ref
            source_refs = tuple(
                dict.fromkeys(
                    value
                    for value in (
                        self.current.evidence_ref,
                        result.evidence_ref,
                    )
                    if value is not None
                )
            )
            finding = ArtifactFinding(
                check.id,
                check.kind,
                self.current.id,
                result.passed,
                check.id in self.recipe.completion.required_checks,
                result.message,
                result.field_ref,
                evidence_ref,
                source_refs,
                check.supports_fields,
            )
            new_findings.append(finding)
            self.findings.append(finding)
        if any(finding.required and not finding.passed for finding in new_findings):
            if len(self.revisions) >= self.recipe.max_revisions:
                return self._stop(
                    UnresolvedReason.BUDGET_EXHAUSTION,
                    "the artifact revision limit was exhausted",
                )
            return self._generate(self._feedback(objective, new_findings))
        if (
            checks
            and checks[0].kind is ArtifactCheckKind.DETERMINISTIC
            and self.semantic
        ):
            return self._checks(self.semantic)
        return self._complete()

    def _feedback(
        self, objective: str, findings: Sequence[ArtifactFinding]
    ) -> str:
        assert self.current is not None
        return canonical_json(
            {
                "objective": objective,
                "artifact_revision": self.current.id,
                "findings": [
                    {
                        "check": finding.check_id,
                        "kind": finding.check_kind.value,
                        "message": finding.message,
                        "field": finding.field_ref,
                    }
                    for finding in findings
                    if finding.required and not finding.passed
                ],
            }
        )

    def _complete(self) -> PlannerTurn:
        assert self.current is not None
        self.stage = "complete"
        return PlannerTurn(ProposedResult(self.current.value))

    def _stop(self, reason: UnresolvedReason, detail: str) -> PlannerTurn:
        self.stage = "stopped"
        self.stop_reason = reason
        self.stop_detail = detail
        return PlannerTurn(PlannerHandoff(detail))


@dataclass(frozen=True, slots=True)
class GenerateVerifyRecipe(Generic[ArtifactT]):
    artifact_type: Any
    generator: PlannerCapability
    prompt_parameter: str
    deterministic_checks: tuple[ArtifactCheck, ...]
    semantic_checks: tuple[ArtifactSemanticCheck[ArtifactT], ...]
    completion: ArtifactCompletionContract
    max_revisions: int
    step_acceptance_policy: str

    def __post_init__(self) -> None:
        ensure_supported_type(self.artifact_type, "artifact type")
        if not isinstance(self.generator, PlannerCapability):
            raise ArtifactRecipeError("artifact generator requires a planner capability")
        if type(self.prompt_parameter) is not str or not self.prompt_parameter:
            raise ArtifactRecipeError("artifact generator requires a prompt parameter")
        parameters = set(inspect.signature(self.generator.tool.function).parameters)
        if self.prompt_parameter not in self.generator.generated_parameters:
            raise ArtifactRecipeError("artifact prompt must be a generated parameter")
        if self.generator.generated_parameters != (self.prompt_parameter,):
            raise ArtifactRecipeError("artifact generator supports one generated prompt")
        if parameters != {
            self.prompt_parameter,
            *self.generator.fixed_arguments,
        }:
            raise ArtifactRecipeError("generator parameters must be fixed or prompt")
        hints = get_type_hints(self.generator.tool.function, include_extras=True)
        if hints[self.prompt_parameter] is not str:
            raise ArtifactRecipeError("artifact generator prompt must be a string")
        if self.generator.tool.output_type != self.artifact_type:
            raise ArtifactRecipeError("artifact generator return type must match recipe")
        if any(
            not isinstance(check, ArtifactCheck)
            for check in self.deterministic_checks
        ) or any(
            not isinstance(check, ArtifactSemanticCheck)
            for check in self.semantic_checks
        ):
            raise ArtifactRecipeError("artifact checks use their public definitions")
        checks: tuple[ArtifactCheck | ArtifactSemanticCheck[ArtifactT], ...] = (
            *self.deterministic_checks,
            *self.semantic_checks,
        )
        identifiers = tuple(check.id for check in checks)
        if len(identifiers) != len(set(identifiers)):
            raise ArtifactRecipeError("artifact check ids must be unique")
        missing = set(self.completion.required_checks) - set(identifiers)
        if missing:
            raise ArtifactRecipeError(f"unknown required artifact checks {sorted(missing)}")
        for check in self.deterministic_checks:
            annotation = get_type_hints(
                check.capability.tool.function, include_extras=True
            )[check.artifact_parameter]
            if annotation != self.artifact_type:
                raise ArtifactRecipeError(
                    f"artifact check {check.id} input type must match recipe"
                )
        required_support = {
            field_name
            for check in checks
            if check.id in self.completion.required_checks
            for field_name in check.supports_fields
        }
        missing_fields = set(self.completion.required_fields) - required_support
        if missing_fields:
            raise ArtifactRecipeError(
                f"artifact fields lack required checks {sorted(missing_fields)}"
            )
        if type(self.max_revisions) is not int or self.max_revisions <= 0:
            raise ArtifactRecipeError("artifact revisions must be positive")
        if (
            type(self.step_acceptance_policy) is not str
            or not self.step_acceptance_policy
        ):
            raise ArtifactRecipeError("artifact step policy must be non-empty")

    async def run(
        self, runtime: Runtime, objective: str, context: RunContext
    ) -> GenerateVerifyResult[ArtifactT]:
        if not isinstance(runtime, Runtime):
            raise ArtifactRecipeError("artifact recipe requires a Runtime")
        if type(objective) is not str or not objective:
            raise ArtifactRecipeError("artifact objective must be non-empty")
        store = (
            EvidenceStore(context.clock)
            if context.evidence_session is None
            else context.evidence_session
        )
        if not isinstance(store, EvidenceStore):
            raise ArtifactRecipeError("artifact evidence session must be an EvidenceStore")
        root_id = context.run_id or uuid.uuid4().hex
        run_context = replace(
            context,
            run_id=root_id,
            correlation_id=context.correlation_id or root_id,
            evidence_session=store,
        )
        deterministic = tuple(
            _CheckSpec(
                check.id,
                ArtifactCheckKind.DETERMINISTIC,
                check.capability,
                check.artifact_parameter,
                check.supports_fields,
            )
            for check in self.deterministic_checks
        )
        semantic = tuple(
            self._semantic_spec(runtime, check, run_context, store)
            for check in self.semantic_checks
        )
        capabilities = (
            self.generator,
            *(check.capability for check in deterministic),
            *(check.capability for check in semantic),
        )
        capability_ids = tuple(value.tool.id for value in capabilities)
        if len(capability_ids) != len(set(capability_ids)):
            raise ArtifactRecipeError("artifact capability ids must be unique")
        planner = _GenerateVerifyPlanner(
            self, deterministic, semantic, run_context, store
        )

        def accepts(value: Any, evidence: EvidenceStore) -> bool:
            current = planner.current
            try:
                digest = canonical_digest(value)
            except StateError:
                return False
            if current is None or digest != current.digest:
                return False
            findings = {
                finding.check_id: finding
                for finding in planner.findings
                if finding.artifact_revision_id == current.id
            }
            try:
                evidence.require_current(current.evidence_ref, run_context.scope)
                for check_id in self.completion.required_checks:
                    finding = findings.get(check_id)
                    if finding is None or not finding.passed:
                        return False
                    if finding.evidence_ref is None:
                        return False
                    evidence.require_current(finding.evidence_ref, run_context.scope)
                    for reference in finding.source_refs:
                        evidence.require_current(reference, run_context.scope)
            except StateError:
                return False
            supported = {
                field_name
                for finding in findings.values()
                if finding.required and finding.passed
                for field_name in finding.supports_fields
            }
            return set(self.completion.required_fields).issubset(supported)

        result: PlanningResult[ArtifactT] = await PlannerEngine(
            runtime,
            planner,
            capabilities,
            result_type=self.artifact_type,
            result_validator=accepts,
            step_acceptance_policy=self.step_acceptance_policy,
        ).run(objective, run_context)
        unresolved = result.unresolved
        if planner.stop_reason is not None:
            unresolved = (
                Unresolved(
                    planner.stop_reason,
                    ("artifact",),
                    planner.stop_detail,
                    needed="changed_artifact",
                ),
            )
        return GenerateVerifyResult(
            result.status,
            result.value,
            tuple(planner.revisions),
            tuple(planner.findings),
            unresolved,
            result.planner_usage,
            result.step_usage,
        )

    def _semantic_spec(
        self,
        runtime: Runtime,
        check: ArtifactSemanticCheck[ArtifactT],
        context: RunContext,
        store: EvidenceStore,
    ) -> _CheckSpec:
        async def evaluate_artifact(artifact: Any) -> ArtifactCheckResult:
            evidence = {
                name: store.require_current(reference, context.scope)
                for name, reference in check.evidence_refs.items()
            }
            inputs = DecisionInputs(
                f"{context.run_id}:artifact:{canonical_digest(artifact)}:{check.id}",
                check.subjects(artifact),
                evidence,
            )
            decision = await runtime._decision_client.evaluate(
                check.judgment, inputs, context
            )
            result = check.classify(decision)
            if not isinstance(result, ArtifactCheckResult):
                raise ArtifactRecipeError(
                    "semantic classifier must return ArtifactCheckResult"
                )
            if result.evidence_ref is None:
                result = replace(result, evidence_ref=decision.evidence_refs[-1])
            return result

        evaluate_artifact.__annotations__ = {
            "artifact": self.artifact_type,
            "return": ArtifactCheckResult,
        }
        capability = PlannerCapability(
            Tool(
                f"artifact-semantic-{check.id}",
                check.judgment.version,
                f"Evaluate artifact with judgment {check.id}.",
                evaluate_artifact,
                {"artifact": TaskInputBinding(("artifact",))},
                effect=ToolEffect.READ,
            )
        )
        return _CheckSpec(
            check.id,
            ArtifactCheckKind.SEMANTIC,
            capability,
            "artifact",
            check.supports_fields,
        )
