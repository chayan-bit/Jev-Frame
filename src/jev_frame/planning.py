from __future__ import annotations

import inspect
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Generic, Protocol, TypeVar, get_type_hints

from .decisions import DecisionClient, DecisionInputs, SelectionResult
from .definitions import (
    MISSING,
    AgentDefinition,
    Binding,
    Candidate,
    CandidateSet,
    ClarificationRequest,
    CompletionContract,
    ConstantBinding,
    Coverage,
    DecisionContext,
    Judgment,
    OperatingPolicy,
    RunContext,
    SourceField,
    TerminalStatus,
    Tool,
    ToolEffect,
    Unresolved,
    UnresolvedReason,
    Usage,
    validate_value,
)
from .limits import BudgetExhaustedError, DeadlineExceededError
from .runtime import Runtime
from .state import Evidence, EvidenceStore, bind_source, canonical_digest


class PlanningError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GeneratedText:
    value: str
    generator_id: str
    generator_version: str

    def __post_init__(self) -> None:
        for value in (self.value, self.generator_id, self.generator_version):
            if type(value) is not str or not value:
                raise PlanningError("generated text metadata must be non-empty")


@dataclass(frozen=True, slots=True)
class EvidenceValue:
    evidence_id: str
    path: tuple[str | int, ...] = ()

    def __post_init__(self) -> None:
        if type(self.evidence_id) is not str or not self.evidence_id:
            raise PlanningError("evidence value requires an evidence id")
        if any(type(part) not in {str, int} for part in self.path):
            raise PlanningError("evidence value path is invalid")


@dataclass(frozen=True, slots=True)
class StepValue:
    step_id: str
    path: tuple[str | int, ...] = ()

    def __post_init__(self) -> None:
        if type(self.step_id) is not str or not self.step_id:
            raise PlanningError("step value requires a step id")
        if any(type(part) not in {str, int} for part in self.path):
            raise PlanningError("step value path is invalid")


PlanArgument = GeneratedText | EvidenceValue | StepValue


@dataclass(frozen=True, slots=True)
class PlanStep:
    id: str
    capability_id: str
    arguments: Mapping[str, PlanArgument]
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.id) is not str or not self.id:
            raise PlanningError("plan step id must be non-empty")
        if type(self.capability_id) is not str or not self.capability_id:
            raise PlanningError("plan capability id must be non-empty")
        if not isinstance(self.arguments, Mapping) or any(
            type(name) is not str
            or not name
            or not isinstance(value, (GeneratedText, EvidenceValue, StepValue))
            for name, value in self.arguments.items()
        ):
            raise PlanningError(
                "plan arguments must use typed generated or source values"
            )
        if len(self.depends_on) != len(set(self.depends_on)) or any(
            type(value) is not str or not value for value in self.depends_on
        ):
            raise PlanningError("plan dependencies must be unique identifiers")
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True, slots=True)
class PlanRevision:
    steps: tuple[PlanStep, ...]

    def __post_init__(self) -> None:
        if not self.steps or any(not isinstance(step, PlanStep) for step in self.steps):
            raise PlanningError("a plan revision requires typed steps")
        identifiers = [step.id for step in self.steps]
        if len(identifiers) != len(set(identifiers)):
            raise PlanningError("plan step ids must be unique")


@dataclass(frozen=True, slots=True)
class ProposedResult:
    value: Any


@dataclass(frozen=True, slots=True)
class PlannerHandoff:
    reason: str

    def __post_init__(self) -> None:
        if type(self.reason) is not str or not self.reason:
            raise PlanningError("planner handoff reason must be non-empty")


PlannerResponse = (
    PlanStep | PlanRevision | ClarificationRequest | ProposedResult | PlannerHandoff
)


@dataclass(frozen=True, slots=True)
class PlannerTurn:
    response: PlannerResponse
    usage: Usage = field(default_factory=Usage)

    def __post_init__(self) -> None:
        if not isinstance(
            self.response,
            (
                PlanStep,
                PlanRevision,
                ClarificationRequest,
                ProposedResult,
                PlannerHandoff,
            ),
        ):
            raise PlanningError("planner returned an unsupported response")
        if not isinstance(self.usage, Usage):
            raise PlanningError("planner usage must use Usage")


@dataclass(frozen=True, slots=True)
class CapabilityDescription:
    id: str
    version: str
    purpose: str
    effect: ToolEffect
    generated_parameters: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlannerRequest:
    objective: str
    capabilities: tuple[CapabilityDescription, ...]
    observations: tuple[Evidence, ...]
    outcomes: tuple[StepOutcome, ...]
    remaining_calls: int
    remaining_revisions: int


class Planner(Protocol):
    def __call__(
        self, request: PlannerRequest
    ) -> PlannerTurn | Awaitable[PlannerTurn]: ...


@dataclass(frozen=True, slots=True)
class PlannerCapability:
    tool: Tool
    generated_parameters: tuple[str, ...] = ()
    fixed_arguments: Mapping[str, Any] = field(default_factory=dict)
    allow_mutation: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.tool, Tool):
            raise PlanningError("planner capability must wrap a Tool")
        parameters = set(inspect.signature(self.tool.function).parameters)
        if len(self.generated_parameters) != len(
            set(self.generated_parameters)
        ) or not set(self.generated_parameters).issubset(parameters):
            raise PlanningError("generated parameters must name unique tool parameters")
        if not isinstance(self.fixed_arguments, Mapping) or not set(
            self.fixed_arguments
        ).issubset(parameters):
            raise PlanningError("fixed arguments must name tool parameters")
        if set(self.generated_parameters) & set(self.fixed_arguments):
            raise PlanningError("a fixed argument cannot also be generated")
        if type(self.allow_mutation) is not bool:
            raise PlanningError("allow_mutation must be boolean")
        object.__setattr__(
            self, "fixed_arguments", MappingProxyType(dict(self.fixed_arguments))
        )

    @property
    def description(self) -> CapabilityDescription:
        return CapabilityDescription(
            self.tool.id,
            self.tool.version,
            self.tool.purpose,
            self.tool.effect,
            self.generated_parameters,
        )


@dataclass(frozen=True, slots=True)
class StepOutcome:
    step_id: str
    capability_id: str
    status: TerminalStatus
    value: Any = MISSING
    evidence_ref: str | None = None
    unresolved: tuple[Unresolved, ...] = ()
    failure: str | None = None
    usage: Usage = field(default_factory=Usage)


ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class PlanningResult(Generic[ResultT]):
    status: TerminalStatus
    value: ResultT | Any = MISSING
    outcomes: tuple[StepOutcome, ...] = ()
    unresolved: tuple[Unresolved, ...] = ()
    clarifications: tuple[ClarificationRequest, ...] = ()
    planner_usage: tuple[Usage, ...] = ()
    step_usage: tuple[Usage, ...] = ()


ResultValidator = Callable[[Any, EvidenceStore], bool | Awaitable[bool]]


class PlannerEngine(Generic[ResultT]):
    def __init__(
        self,
        runtime: Runtime,
        planner: Planner,
        capabilities: Sequence[PlannerCapability],
        *,
        result_type: Any,
        result_validator: ResultValidator,
        step_acceptance_policy: str,
        permitted_evidence: Sequence[str] = (),
    ) -> None:
        if not isinstance(runtime, Runtime) or not callable(planner):
            raise PlanningError(
                "planner engine requires a runtime and callable planner"
            )
        if not callable(result_validator):
            raise PlanningError("result validator must be callable")
        if type(step_acceptance_policy) is not str or not step_acceptance_policy:
            raise PlanningError("step acceptance policy must be non-empty")
        values = tuple(capabilities)
        if any(not isinstance(value, PlannerCapability) for value in values):
            raise PlanningError("capabilities must use PlannerCapability")
        identifiers = [value.tool.id for value in values]
        if len(identifiers) != len(set(identifiers)):
            raise PlanningError("planner capability ids must be unique")
        self.runtime = runtime
        self.planner = planner
        self.capabilities = {value.tool.id: value for value in values}
        self.result_type = result_type
        self.result_validator = result_validator
        self.step_acceptance_policy = step_acceptance_policy
        self.permitted_evidence = tuple(permitted_evidence)

    async def run(self, objective: str, context: RunContext) -> PlanningResult[ResultT]:
        if type(objective) is not str or not objective:
            raise PlanningError("objective must be non-empty")
        store = (
            EvidenceStore(context.clock)
            if context.evidence_session is None
            else context.evidence_session
        )
        if not isinstance(store, EvidenceStore):
            raise PlanningError("planner evidence session must be an EvidenceStore")
        root_id = context.run_id or uuid.uuid4().hex
        ledger = self.runtime._ledger_for(context)
        outcomes: list[StepOutcome] = []
        planner_usage: list[Usage] = []
        fingerprints: set[str] = set()
        revision = 0
        while True:
            call_number = len(planner_usage) + 1
            call_id = f"{root_id}:planner:{call_number}"
            try:
                await ledger.admit_planner_call(
                    call_id, deadline=context.deadline, clock=context.clock
                )
                observations = store.project(
                    self.permitted_evidence, scope=context.scope
                )
                request = PlannerRequest(
                    objective,
                    tuple(value.description for value in self.capabilities.values()),
                    observations,
                    tuple(outcomes),
                    context.limits.planner_calls - call_number,
                    context.limits.plan_revisions - revision,
                )
                turn = self.planner(request)
                if inspect.isawaitable(turn):
                    turn = await turn
                if not isinstance(turn, PlannerTurn):
                    raise PlanningError("planner must return PlannerTurn")
                planner_usage.append(turn.usage)
                await ledger.record_usage(call_id, turn.usage)
                response = turn.response
                if isinstance(response, ProposedResult):
                    value = validate_value(
                        self.result_type, response.value, "proposed result"
                    )
                    accepted = self.result_validator(value, store)
                    if inspect.isawaitable(accepted):
                        accepted = await accepted
                    if accepted is True:
                        return PlanningResult(
                            TerminalStatus.COMPLETED,
                            value,
                            tuple(outcomes),
                            planner_usage=tuple(planner_usage),
                            step_usage=tuple(item.usage for item in outcomes),
                        )
                    return self._unresolved(
                        outcomes,
                        planner_usage,
                        UnresolvedReason.UNACCEPTED_JUDGMENT,
                        "the planner's proposed result failed host completion",
                        needed="result_validator",
                    )
                if isinstance(response, ClarificationRequest):
                    result = self._unresolved(
                        outcomes,
                        planner_usage,
                        UnresolvedReason.MISSING_EVIDENCE,
                        "the planner requested host clarification",
                        needed=response.id,
                    )
                    return replace(result, clarifications=(response,))
                if isinstance(response, PlannerHandoff):
                    return self._unresolved(
                        outcomes,
                        planner_usage,
                        UnresolvedReason.MISSING_CAPABILITY,
                        response.reason,
                        needed="host_handoff",
                    )
                plan = (
                    response
                    if isinstance(response, PlanRevision)
                    else PlanRevision((response,))
                )
                fingerprint = canonical_digest(plan)
                if fingerprint in fingerprints:
                    return self._unresolved(
                        outcomes,
                        planner_usage,
                        UnresolvedReason.NO_PROGRESS,
                        "the planner repeated an unchanged proposal",
                        needed="changed_plan",
                    )
                fingerprints.add(fingerprint)
                revision += 1
                await ledger.admit_plan_revision(
                    f"{root_id}:revision:{revision}",
                    deadline=context.deadline,
                    clock=context.clock,
                )
                try:
                    ordered = self._validate_plan(plan)
                except PlanningError as error:
                    outcomes.append(
                        StepOutcome(
                            f"revision-{revision}",
                            "planner",
                            TerminalStatus.FAILED,
                            failure=str(error),
                        )
                    )
                    continue
                step_refs: dict[str, str] = {}
                for step in ordered:
                    try:
                        outcome = await self._execute_step(
                            step, revision, objective, context, store, step_refs
                        )
                    except PlanningError as error:
                        outcome = StepOutcome(
                            step.id,
                            step.capability_id,
                            TerminalStatus.FAILED,
                            failure=str(error),
                        )
                    outcomes.append(outcome)
                    if outcome.evidence_ref is not None:
                        step_refs[step.id] = outcome.evidence_ref
                    if outcome.status is not TerminalStatus.COMPLETED:
                        break
            except (BudgetExhaustedError, DeadlineExceededError) as error:
                return self._unresolved(
                    outcomes,
                    planner_usage,
                    UnresolvedReason.BUDGET_EXHAUSTION,
                    "the shared planner limit or deadline was exhausted",
                    needed=type(error).__name__,
                )

    def _validate_plan(self, plan: PlanRevision) -> tuple[PlanStep, ...]:
        steps = {step.id: step for step in plan.steps}
        for step in plan.steps:
            capability = self.capabilities.get(step.capability_id)
            if capability is None:
                raise PlanningError(f"unknown capability {step.capability_id}")
            if (
                capability.tool.effect is ToolEffect.MUTATION
                and not capability.allow_mutation
            ):
                raise PlanningError(f"forbidden mutation {step.capability_id}")
            unknown = set(step.depends_on) - set(steps)
            if unknown or step.id in step.depends_on:
                raise PlanningError(f"invalid dependencies for step {step.id}")
        ordered: list[PlanStep] = []
        remaining = dict(steps)
        while remaining:
            ready = [
                step
                for step in remaining.values()
                if set(step.depends_on).issubset(item.id for item in ordered)
            ]
            if not ready:
                raise PlanningError("plan dependency cycle")
            for step in plan.steps:
                if step in ready:
                    ordered.append(step)
                    remaining.pop(step.id)
        return tuple(ordered)

    async def _execute_step(
        self,
        step: PlanStep,
        revision: int,
        objective: str,
        context: RunContext,
        store: EvidenceStore,
        step_refs: Mapping[str, str],
    ) -> StepOutcome:
        capability = self.capabilities[step.capability_id]
        tool = capability.tool
        signature = inspect.signature(tool.function)
        hints = get_type_hints(tool.function, include_extras=True)
        supplied = set(step.arguments) | set(capability.fixed_arguments)
        if supplied != set(signature.parameters):
            raise PlanningError(f"step {step.id} arguments do not match {tool.id}")
        bindings: dict[str, Binding] = {
            name: ConstantBinding(value)
            for name, value in capability.fixed_arguments.items()
        }
        evidence_dependencies: list[str] = []
        for name, argument in step.arguments.items():
            if isinstance(argument, GeneratedText):
                if name not in capability.generated_parameters:
                    raise PlanningError(f"{tool.id}.{name} cannot be generated")
                value: Any = argument.value
            else:
                if isinstance(argument, StepValue):
                    try:
                        evidence_id = step_refs[argument.step_id]
                    except KeyError as error:
                        raise PlanningError(
                            f"step {step.id} references unavailable step {argument.step_id}"
                        ) from error
                    if argument.step_id not in step.depends_on:
                        raise PlanningError(
                            f"step {step.id} must depend on {argument.step_id}"
                        )
                else:
                    evidence_id = argument.evidence_id
                try:
                    record = store.require_current(evidence_id, context.scope)
                except Exception as error:
                    raise PlanningError(
                        f"step {step.id} references unavailable evidence {evidence_id}"
                    ) from error
                path = argument.path
                value = (
                    record.value
                    if not path
                    else bind_source(record, SourceField(path)).value  # type: ignore[arg-type]
                )
                evidence_dependencies.append(evidence_id)
            validate_value(hints[name], value, f"{tool.id}.{name}")
            bindings[name] = ConstantBinding(value)
        evidence_id = f"plan:{revision}:{step.id}"
        planned_tool = replace(
            tool,
            bindings=bindings,
            requires_evidence=tuple(
                dict.fromkeys((*tool.requires_evidence, *evidence_dependencies))
            ),
            produces_evidence=(evidence_id,),
        )
        definition: AgentDefinition[str, Any] = AgentDefinition(
            f"plan-step-{revision}-{step.id}",
            "1.0.0",
            f"Execute validated plan step {step.id}.",
            str,
            tool.output_type,
            CompletionContract((evidence_id,), {}, self.step_acceptance_policy),
            OperatingPolicy("1.0.0", (self.step_acceptance_policy,)),
            tools=(planned_tool,),
        )
        step_context = replace(
            context,
            evidence_session=store,
            run_id=f"{context.run_id or 'plan'}:revision:{revision}:step:{step.id}",
        )
        result = await self.runtime.run(definition, objective, step_context)
        return StepOutcome(
            step.id,
            step.capability_id,
            result.status,
            result.value,
            evidence_id if result.status is TerminalStatus.COMPLETED else None,
            result.unresolved,
            result.failure,
            result.usage,
        )

    @staticmethod
    def _unresolved(
        outcomes: Sequence[StepOutcome],
        planner_usage: Sequence[Usage],
        reason: UnresolvedReason,
        detail: str,
        *,
        needed: str,
    ) -> PlanningResult[Any]:
        return PlanningResult(
            TerminalStatus.UNRESOLVED,
            outcomes=tuple(outcomes),
            unresolved=(Unresolved(reason, ("objective",), detail, needed=needed),),
            planner_usage=tuple(planner_usage),
            step_usage=tuple(item.usage for item in outcomes),
        )


ProposalT = TypeVar("ProposalT")


@dataclass(frozen=True, slots=True)
class ProposedAlternative(Generic[ProposalT]):
    key: str
    value: ProposalT
    description: str
    generator_id: str
    generator_version: str


@dataclass(frozen=True, slots=True)
class ProposalSelection(Generic[ProposalT]):
    valid: tuple[ProposedAlternative[ProposalT], ...]
    rejected_keys: tuple[str, ...]
    selection: SelectionResult


async def propose_select(
    client: DecisionClient,
    judgment: Judgment,
    alternatives: Sequence[ProposedAlternative[ProposalT]],
    *,
    validate: Callable[[ProposalT], bool],
    subjects: Mapping[str, Any],
    evidence: Mapping[str, Evidence],
    context: DecisionContext,
) -> ProposalSelection[ProposalT]:
    if not callable(validate):
        raise PlanningError("proposal validator must be callable")
    valid: list[ProposedAlternative[ProposalT]] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for alternative in alternatives:
        if not isinstance(alternative, ProposedAlternative) or alternative.key in seen:
            raise PlanningError("proposal keys must be unique typed alternatives")
        seen.add(alternative.key)
        if validate(alternative.value):
            valid.append(alternative)
        else:
            rejected.append(alternative.key)
    snapshot = CandidateSet(
        judgment.candidate_set or "proposals",
        "1.0.0",
        tuple(
            Candidate(
                alternative.key,
                alternative,
                alternative.description,
                alternative.generator_id,
                alternative.generator_version,
            )
            for alternative in valid
        ),
        Coverage.COMPLETE,
        context.scope,
        total_count=len(valid),
    )
    inputs = DecisionInputs(
        f"propose-select:{uuid.uuid4().hex}",
        subjects,
        evidence,
        {snapshot.id: snapshot},
    )
    selection = await client.select(judgment, inputs, context)
    return ProposalSelection(tuple(valid), tuple(rejected), selection)
