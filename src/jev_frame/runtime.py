from __future__ import annotations

import asyncio
import inspect
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol, TypeVar, cast, get_type_hints

from pydantic import BaseModel

from .compiler import CompiledNode, NodeKind, compile_agent
from .decisions import (
    DecisionClient,
    DecisionInputs,
    DecisionProvider,
    StaleDecisionResult,
)
from .definitions import (
    AcceptanceRecord,
    AcceptanceStatus,
    AgentDefinition,
    CandidateBinding,
    CandidateProvider,
    CandidateSet,
    ChoiceQuestion,
    ConstantBinding,
    DefaultBinding,
    DerivationBinding,
    GeneratedBinding,
    HostContextBinding,
    InputValidationError,
    Judgment,
    JudgmentBinding,
    ProviderError,
    RunContext,
    RunResult,
    SourceBinding,
    StaleInputError,
    TaskInputBinding,
    TerminalStatus,
    Tool,
    ToolEffect,
    Unresolved,
    UnresolvedReason,
    Usage,
    UsageCoverage,
    validate_value,
)
from .inspection import (
    EventKind,
    EventLog,
    JevEvent,
    diagnostic_for_error,
    diagnostic_for_unresolved,
)
from .limits import (
    AdmissionError,
    BudgetExhaustedError,
    DeadlineExceededError,
    UsageLedger,
)
from .state import (
    AcceptanceEvidence,
    Derivation,
    EvidenceStore,
    ModelJudgment,
    Observation,
    bind_source,
)

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")
CompletionCheck = Callable[[Any, EvidenceStore], bool | Awaitable[bool]]
ApplicabilityCheck = Callable[[Mapping[str, Any]], bool | Awaitable[bool]]


class RuntimeConfigurationError(InputValidationError):
    pass


class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class RuntimeProvider(DecisionProvider, Protocol):
    pass


@dataclass(slots=True)
class _RunState:
    store: EvidenceStore
    candidates: dict[str, CandidateSet]
    findings: dict[str, Any]
    selections: dict[str, Any]
    decision_refs: dict[str, str]
    statuses: dict[str, NodeStatus]
    usages: list[Usage]


class _RunUnresolved(Exception):
    def __init__(self, unresolved: Unresolved) -> None:
        self.unresolved = unresolved
        super().__init__(unresolved.reason.value)


class _ToolFailure(Exception):
    pass


def _read_path(value: Any, path: Sequence[str | int]) -> Any:
    current = value
    for part in path:
        if isinstance(current, BaseModel) and type(part) is str:
            if part not in current.__class__.model_fields:
                raise _RunUnresolved(
                    Unresolved(
                        UnresolvedReason.MISSING_EVIDENCE,
                        (str(part),),
                        "a task input path is unavailable",
                        needed=str(part),
                    )
                )
            current = getattr(current, part)
        elif (
            is_dataclass(current)
            and not isinstance(current, type)
            and type(part) is str
        ):
            names = {item.name for item in fields(current)}
            if part not in names:
                raise _RunUnresolved(
                    Unresolved(
                        UnresolvedReason.MISSING_EVIDENCE,
                        (str(part),),
                        "a task input path is unavailable",
                        needed=str(part),
                    )
                )
            current = getattr(current, part)
        elif isinstance(current, Mapping) and part in current:  # noqa: SIM114
            current = current[part]
        elif (
            isinstance(current, Sequence)
            and not isinstance(current, (str, bytes))
            and type(part) is int
            and 0 <= part < len(current)
        ):
            current = current[part]
        else:
            raise _RunUnresolved(
                Unresolved(
                    UnresolvedReason.MISSING_EVIDENCE,
                    (str(part),),
                    "a task input path is unavailable",
                    needed=str(part),
                )
            )
    return current


def _usage_total(values: Sequence[Usage]) -> Usage:
    if not values:
        return Usage()
    coverage = (
        UsageCoverage.COMPLETE
        if all(value.coverage is UsageCoverage.COMPLETE for value in values)
        else UsageCoverage.UNKNOWN
        if all(value.coverage is UsageCoverage.UNKNOWN for value in values)
        else UsageCoverage.PARTIAL
    )
    input_tokens = (
        sum(value.input_tokens for value in values if value.input_tokens is not None)
        if all(value.input_tokens is not None for value in values)
        else None
    )
    output_tokens = (
        sum(value.output_tokens for value in values if value.output_tokens is not None)
        if all(value.output_tokens is not None for value in values)
        else None
    )
    return Usage(
        coverage,
        input_tokens,
        output_tokens,
        sum(value.provider_attempts for value in values),
        sum(value.submitted_questions for value in values),
    )


class Runtime:
    """One deterministic read-only scheduler shared by every agent definition."""

    def __init__(
        self,
        provider: RuntimeProvider,
        *,
        model: str,
        completion_checks: Mapping[str, CompletionCheck],
        applicability_checks: Mapping[str, ApplicabilityCheck] | None = None,
        ledger: UsageLedger | None = None,
        event_log: EventLog | None = None,
    ) -> None:
        if type(model) is not str or not model.strip():
            raise RuntimeConfigurationError("model must be a non-empty string")
        if not isinstance(completion_checks, Mapping) or any(
            type(key) is not str or not key or not callable(value)
            for key, value in completion_checks.items()
        ):
            raise RuntimeConfigurationError("completion checks must be named callables")
        checks = {} if applicability_checks is None else dict(applicability_checks)
        if any(
            type(key) is not str or not key or not callable(value)
            for key, value in checks.items()
        ):
            raise RuntimeConfigurationError(
                "applicability checks must be named callables"
            )
        self.model = model
        self.completion_checks = dict(completion_checks)
        self.applicability_checks = checks
        self.event_log = EventLog() if event_log is None else event_log
        self.ledger = ledger
        self._semaphore: asyncio.Semaphore | None = None
        self._decision_client = DecisionClient(
            provider,
            model=model,
            ledger=ledger,
            event_log=self.event_log,
        )
        self._results: dict[str, RunResult[Any]] = {}

    @property
    def events(self) -> tuple[JevEvent, ...]:
        return self.event_log.events

    def result_for(self, run_id: str) -> RunResult[Any] | None:
        return self._results.get(run_id)

    def _ledger_for(self, context: RunContext) -> UsageLedger:
        ledger = self._decision_client._ledger_for(context)
        if self.ledger is None:
            self.ledger = ledger
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(context.limits.concurrent_operations)
        elif ledger.limits != context.limits:
            raise RuntimeConfigurationError(
                "run limits differ from the shared runtime ledger"
            )
        return ledger

    def _emit(
        self,
        context: RunContext,
        kind: EventKind,
        *,
        operation_id: str,
        definition_id: str,
        question_id: str | None = None,
        attempt_id: str | None = None,
        reason_code: str | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        run_id = context.run_id
        assert run_id is not None
        payload = {"definition_id": definition_id}
        if question_id is not None:
            payload["question_id"] = question_id
        if data is not None:
            payload.update(data)
        self.event_log.emit(
            kind,
            run_id=run_id,
            correlation_id=context.correlation_id or run_id,
            operation_id=operation_id,
            parent_operation_id=context.parent_operation_id,
            attempt_id=attempt_id,
            reason_code=reason_code,
            data=payload,
            sink=context.event_sink,
        )

    def _trace(self, run_id: str) -> tuple[Mapping[str, Any], ...]:
        return tuple(event.to_dict() for event in self.events if event.run_id == run_id)

    def _record_result(self, run_id: str, result: RunResult[Any]) -> RunResult[Any]:
        traced = replace(result, trace=self._trace(run_id))
        self._results[run_id] = traced
        return traced

    @staticmethod
    def _definitions(
        definition: AgentDefinition[Any, Any],
    ) -> tuple[dict[str, Tool], dict[str, Judgment], dict[str, CandidateProvider]]:
        tools = {tool.id: tool for tool in definition.tools}
        judgments = {judgment.id: judgment for judgment in definition.judgments}
        providers = {
            provider.id: provider for provider in definition.candidate_providers
        }
        for package in definition.packages:
            tools.update((tool.id, tool) for tool in package.tools)
            judgments.update((judgment.id, judgment) for judgment in package.judgments)
            providers.update(
                (provider.id, provider) for provider in package.candidate_providers
            )
        return tools, judgments, providers

    @staticmethod
    def _host_value(context: RunContext, key: str) -> Any:
        if key == "scope":
            return context.scope
        try:
            return context.host_dependencies[key]
        except KeyError as error:
            raise _RunUnresolved(
                Unresolved(
                    UnresolvedReason.MISSING_EVIDENCE,
                    (key,),
                    "a required host dependency is unavailable",
                    needed=key,
                )
            ) from error

    def _simple_arguments(
        self,
        bindings: Mapping[str, Any],
        inputs: Any,
        context: RunContext,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, binding in bindings.items():
            if isinstance(binding, TaskInputBinding):
                result[name] = _read_path(inputs, binding.path)
            elif isinstance(binding, HostContextBinding):
                result[name] = self._host_value(context, binding.key)
            elif isinstance(binding, ConstantBinding):
                result[name] = binding.value
            elif isinstance(binding, DefaultBinding):
                continue
            else:
                raise _RunUnresolved(
                    Unresolved(
                        UnresolvedReason.MISSING_CAPABILITY,
                        (name,),
                        "the candidate provider uses an unsupported binding",
                        needed=type(binding).__name__,
                    )
                )
        return result

    async def _call(
        self,
        function: Callable[..., Any],
        arguments: Mapping[str, Any],
        *,
        blocking: bool,
        timeout: float,
    ) -> Any:
        if timeout <= 0:
            raise DeadlineExceededError("deadline expired before dispatch")
        if blocking:
            return await asyncio.wait_for(
                asyncio.to_thread(function, **arguments), timeout
            )
        value = function(**arguments)
        if inspect.isawaitable(value):
            return await asyncio.wait_for(value, timeout)
        return value

    async def _run_read_operation(
        self,
        *,
        operation_id: str,
        definition_id: str,
        node_id: str,
        function: Callable[..., Any],
        arguments: Mapping[str, Any],
        blocking: bool,
        timeout: float,
        context: RunContext,
    ) -> Any:
        ledger = self._ledger_for(context)
        assert self._semaphore is not None
        attempt_id = f"{operation_id}:1"
        self._emit(
            context,
            EventKind.OPERATION_STARTED,
            operation_id=operation_id,
            definition_id=definition_id,
            question_id=node_id,
            data={"definition_version": "runtime"},
        )
        async with (
            self._semaphore,
            ledger.operation(
                operation_id, deadline=context.deadline, clock=context.clock
            ),
        ):
            await ledger.admit_tool_attempt(
                attempt_id, deadline=context.deadline, clock=context.clock
            )
            self._emit(
                context,
                EventKind.ATTEMPT_ADMITTED,
                operation_id=operation_id,
                definition_id=definition_id,
                question_id=node_id,
                attempt_id=attempt_id,
                data={"attempt_number": 1, "attempt_status": "started"},
            )
            value = await self._call(
                function,
                arguments,
                blocking=blocking,
                timeout=min(timeout, context.deadline - context.clock()),
            )
        return value

    async def _retrieve(
        self,
        provider: CandidateProvider,
        inputs: Any,
        context: RunContext,
    ) -> CandidateSet:
        run_id = context.run_id
        assert run_id is not None
        operation_id = f"{run_id}:retrieve:{provider.id}"
        arguments = self._simple_arguments(provider.bindings, inputs, context)
        value = await self._run_read_operation(
            operation_id=operation_id,
            definition_id=provider.id,
            node_id=f"retrieve:{provider.id}",
            function=provider.function,
            arguments=arguments,
            blocking=provider.blocking,
            timeout=context.deadline - context.clock(),
            context=context,
        )
        if not isinstance(value, CandidateSet):
            raise _ToolFailure("candidate provider returned an invalid snapshot")
        if value.id != provider.id or value.scope != context.scope:
            raise _ToolFailure("candidate provider returned an incompatible snapshot")
        self._emit(
            context,
            EventKind.OPERATION_COMPLETED,
            operation_id=operation_id,
            definition_id=provider.id,
            question_id=f"retrieve:{provider.id}",
            data={
                "result_fingerprint": f"{provider.id}:{value.version}",
                "evidence_refs": [],
                "usage": {
                    "coverage": "unknown",
                    "input_tokens": None,
                    "output_tokens": None,
                    "provider_attempts": 0,
                    "submitted_questions": 0,
                },
            },
        )
        return value

    def _tool_arguments(
        self,
        tool: Tool,
        inputs: Any,
        context: RunContext,
        state: _RunState,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        result: dict[str, Any] = {}
        dependencies: list[str] = []
        hints = get_type_hints(tool.function, include_extras=True)
        for evidence_id in tool.requires_evidence:
            record = state.store.require_current(evidence_id, context.scope)
            dependencies.append(record.id)
        for name, binding in tool.bindings.items():
            if isinstance(binding, TaskInputBinding):
                value = _read_path(inputs, binding.path)
            elif isinstance(binding, HostContextBinding):
                value = self._host_value(context, binding.key)
            elif isinstance(binding, ConstantBinding):
                value = binding.value
            elif isinstance(binding, DefaultBinding):
                continue
            elif isinstance(binding, CandidateBinding):
                selection = state.selections.get(binding.selection)
                if selection is None or selection.candidate is None:
                    raise _RunUnresolved(
                        Unresolved(
                            UnresolvedReason.MISSING_EVIDENCE,
                            (binding.selection,),
                            "a candidate selection is unavailable",
                            needed=binding.selection,
                        )
                    )
                value = selection.candidate.value
                reference = state.decision_refs.get(binding.selection)
                if reference is not None:
                    state.store.require_current(reference, context.scope)
                    dependencies.append(reference)
            elif isinstance(binding, SourceBinding):
                record = state.store.require_current(binding.evidence, context.scope)
                value = bind_source(record, binding.field_or_span).value  # type: ignore[arg-type]
                dependencies.append(record.id)
            elif isinstance(binding, JudgmentBinding):
                if binding.judgment not in state.findings:
                    raise _RunUnresolved(
                        Unresolved(
                            UnresolvedReason.MISSING_EVIDENCE,
                            (binding.judgment,),
                            "a prior judgment is unavailable",
                            needed=binding.judgment,
                        )
                    )
                value = state.findings[binding.judgment]
                reference = state.decision_refs.get(binding.judgment)
                if reference is not None:
                    state.store.require_current(reference, context.scope)
                    dependencies.append(reference)
            elif isinstance(binding, (DerivationBinding, GeneratedBinding)):
                raise _RunUnresolved(
                    Unresolved(
                        UnresolvedReason.MISSING_CAPABILITY,
                        (name,),
                        "this read-only scheduler cannot resolve the declared binding",
                        needed=type(binding).__name__,
                    )
                )
            else:  # pragma: no cover - definitions validate binding kinds.
                raise TypeError("unsupported binding")
            result[name] = validate_value(hints[name], value, f"{tool.id}.{name}")
        return result, tuple(dict.fromkeys(dependencies))

    async def _execute_tool(
        self,
        tool: Tool,
        node: CompiledNode,
        inputs: Any,
        context: RunContext,
        state: _RunState,
    ) -> None:
        if tool.effect is ToolEffect.MUTATION:
            raise _RunUnresolved(
                Unresolved(
                    UnresolvedReason.PERMISSION_DENIAL,
                    (tool.id,),
                    "the read-only runtime does not dispatch mutations",
                    needed=tool.id,
                )
            )
        run_id = context.run_id
        assert run_id is not None
        arguments, dependencies = self._tool_arguments(tool, inputs, context, state)
        operation_id = f"{run_id}:tool:{tool.id}"
        try:
            value = await self._run_read_operation(
                operation_id=operation_id,
                definition_id=tool.id,
                node_id=node.id,
                function=tool.function,
                arguments=arguments,
                blocking=tool.blocking,
                timeout=tool.timeout,
                context=context,
            )
            value = validate_value(tool.output_type, value, f"{tool.id} output")
        except asyncio.CancelledError:
            raise
        except (AdmissionError, _RunUnresolved):
            raise
        except Exception as error:
            diagnostic = diagnostic_for_error(
                error,
                definition_id=tool.id,
                node_id=node.id,
                source_path=("tools", tool.id),
            )
            self._emit(
                context,
                EventKind.OPERATION_FAILED,
                operation_id=operation_id,
                definition_id=tool.id,
                question_id=node.id,
                reason_code=diagnostic.code,
                data={"diagnostic": diagnostic.to_dict()},
            )
            raise _ToolFailure("tool execution failed") from error

        outputs: Mapping[str, Any]
        if len(tool.produces_evidence) == 1:
            outputs = {tool.produces_evidence[0]: value}
        elif not tool.produces_evidence:
            outputs = {}
        elif isinstance(value, Mapping) and set(value) == set(tool.produces_evidence):
            outputs = value
        else:
            raise _ToolFailure("tool output does not match declared evidence")
        evidence_refs: list[str] = []
        for evidence_id, output in outputs.items():
            common = {
                "id": evidence_id,
                "value": output,
                "source_id": f"tool:{tool.id}",
                "scope": context.scope,
                "observed_at": context.clock(),
                "source_version": tool.version,
                "dependencies": dependencies,
            }
            record: Derivation | Observation
            if tool.effect is ToolEffect.PURE and dependencies:
                record = Derivation(
                    **common,
                    transformation_id=tool.id,
                    transformation_version=tool.version,
                )
            else:
                record = Observation(**common)
            state.store.add(record)
            state.findings[evidence_id] = output
            evidence_refs.append(evidence_id)
        self._emit(
            context,
            EventKind.OPERATION_COMPLETED,
            operation_id=operation_id,
            definition_id=tool.id,
            question_id=node.id,
            data={
                "result_fingerprint": f"{tool.id}:{tool.version}",
                "evidence_refs": evidence_refs,
                "usage": {
                    "coverage": "unknown",
                    "input_tokens": None,
                    "output_tokens": None,
                    "provider_attempts": 0,
                    "submitted_questions": 0,
                },
            },
        )

    async def _is_applicable(self, judgment: Judgment, state: _RunState) -> bool:
        if judgment.applicability is None:
            return True
        check = self.applicability_checks.get(judgment.applicability)
        if check is None:
            raise _RunUnresolved(
                Unresolved(
                    UnresolvedReason.SEMANTIC_AMBIGUITY,
                    (judgment.id,),
                    "a declared applicability check is unavailable",
                    needed=judgment.applicability,
                )
            )
        value = check(MappingProxyType(dict(state.findings)))
        if inspect.isawaitable(value):
            value = await value
        if type(value) is not bool:
            raise _ToolFailure("applicability check must return bool")
        return value

    def _subject_value(self, name: str, inputs: Any, state: _RunState) -> Any:
        try:
            return _read_path(inputs, (name,))
        except _RunUnresolved:
            pass
        if name in state.findings:
            return state.findings[name]
        for selection in state.selections.values():
            if selection.candidate is not None and name in {"document", "candidate"}:
                candidate = selection.candidate
                return getattr(candidate.value, "id", candidate.key)
        raise _RunUnresolved(
            Unresolved(
                UnresolvedReason.MISSING_EVIDENCE,
                (name,),
                "a judgment subject is unavailable",
                needed=name,
            )
        )

    async def _execute_judgment(
        self,
        judgment: Judgment,
        node: CompiledNode,
        inputs: Any,
        context: RunContext,
        state: _RunState,
    ) -> None:
        if not await self._is_applicable(judgment, state):
            state.statuses[node.id] = NodeStatus.SKIPPED
            return
        subjects = {
            subject.name: self._subject_value(subject.name, inputs, state)
            for subject in judgment.subjects
        }
        evidence = {
            selector.name: state.store.require_current(selector.name, context.scope)
            for selector in judgment.evidence
        }
        candidates = (
            {}
            if judgment.candidate_set is None
            else {judgment.candidate_set: state.candidates[judgment.candidate_set]}
        )
        run_id = context.run_id
        assert run_id is not None
        decision_inputs = DecisionInputs(
            f"{run_id}:judge:{judgment.id}",
            subjects,
            evidence,
            candidates,
        )
        assert self._semaphore is not None
        async with self._semaphore:
            if isinstance(judgment.primitive, ChoiceQuestion) and candidates:
                selected = await self._decision_client.select(
                    judgment, decision_inputs, context
                )
                if selected.decision is None or selected.selection is None:
                    raise _RunUnresolved(
                        selected.unresolved
                        or Unresolved(
                            UnresolvedReason.REFUTED_CLAIM,
                            tuple(subjects),
                            "no candidate satisfied the judgment",
                        )
                    )
                state.selections[judgment.id] = selected.selection
                decision = selected.decision
            else:
                decision = await self._decision_client.evaluate(
                    judgment, decision_inputs, context
                )
        state.findings[judgment.id] = decision.answer
        state.decision_refs[judgment.id] = decision.evidence_refs[-1]
        state.usages.append(decision.usage)

    async def _execute_node(
        self,
        node: CompiledNode,
        tools: Mapping[str, Tool],
        judgments: Mapping[str, Judgment],
        inputs: Any,
        context: RunContext,
        state: _RunState,
    ) -> None:
        state.statuses[node.id] = NodeStatus.RUNNING
        if node.kind is NodeKind.INVOCATION:
            await self._execute_tool(
                tools[node.definition_id], node, inputs, context, state
            )
        elif node.kind is NodeKind.JUDGMENT:
            await self._execute_judgment(
                judgments[node.definition_id], node, inputs, context, state
            )
        if state.statuses[node.id] is NodeStatus.RUNNING:
            state.statuses[node.id] = NodeStatus.COMPLETED

    async def _completion(
        self,
        definition: AgentDefinition[Any, Any],
        context: RunContext,
        state: _RunState,
    ) -> Any:
        missing = [
            reference
            for reference in definition.completion.required_findings
            if reference not in state.findings
        ]
        if missing:
            raise _RunUnresolved(
                Unresolved(
                    UnresolvedReason.MISSING_EVIDENCE,
                    tuple(missing),
                    "required completion findings are unavailable",
                    needed=missing[0],
                )
            )
        values = {
            field: state.findings[reference]
            for field, reference in definition.completion.result_bindings.items()
        }
        proposed: Any
        if is_dataclass(definition.output_type):
            hints = get_type_hints(definition.output_type, include_extras=True)
            validated = {
                field.name: validate_value(
                    hints[field.name],
                    values[field.name],
                    f"{definition.id} completion.{field.name}",
                )
                for field in fields(definition.output_type)
            }
            proposed = cast(Callable[..., Any], definition.output_type)(**validated)
        elif isinstance(definition.output_type, type) and issubclass(
            definition.output_type, BaseModel
        ):
            proposed = definition.output_type.model_validate(values, strict=True)
        else:
            if values:
                raise _ToolFailure("scalar completion cannot use named bindings")
            reference = definition.completion.required_findings[0]
            proposed = validate_value(
                definition.output_type,
                state.findings[reference],
                f"{definition.id} completion",
            )
        check = self.completion_checks.get(definition.completion.acceptance_policy)
        if check is None:
            raise _RunUnresolved(
                Unresolved(
                    UnresolvedReason.UNACCEPTED_JUDGMENT,
                    tuple(definition.completion.required_findings),
                    "the application did not supply the completion policy",
                    needed=definition.completion.acceptance_policy,
                )
            )
        accepted = check(proposed, state.store)
        if inspect.isawaitable(accepted):
            accepted = await accepted
        if type(accepted) is not bool:
            raise _ToolFailure("completion check must return bool")
        if not accepted:
            raise _RunUnresolved(
                Unresolved(
                    UnresolvedReason.UNACCEPTED_JUDGMENT,
                    tuple(definition.completion.required_findings),
                    "the application completion policy did not accept the result",
                    needed=definition.completion.acceptance_policy,
                )
            )
        for judgment_id, reference in state.decision_refs.items():
            record = state.store.require_current(reference, context.scope)
            if not isinstance(record, ModelJudgment):
                continue
            acceptance = AcceptanceRecord(
                definition.completion.acceptance_policy,
                definition.policy.version,
                AcceptanceStatus.ACCEPT,
                ("completion_check_passed",),
            )
            state.store.add(
                AcceptanceEvidence(
                    id=f"{context.run_id}:accept:{judgment_id}",
                    value=acceptance,
                    source_id=f"policy:{definition.completion.acceptance_policy}",
                    scope=context.scope,
                    observed_at=context.clock(),
                    dependencies=(reference,),
                    judgment_ref=reference,
                    policy_id=acceptance.policy_id,
                    policy_version=acceptance.policy_version,
                )
            )
        return proposed

    async def run(
        self,
        definition: AgentDefinition[InputT, OutputT],
        inputs: InputT,
        context: RunContext,
    ) -> RunResult[OutputT]:
        run_id = context.run_id or uuid.uuid4().hex
        store = (
            EvidenceStore(context.clock)
            if context.evidence_session is None
            else context.evidence_session
        )
        if not isinstance(store, EvidenceStore):
            raise RuntimeConfigurationError("evidence_session must be an EvidenceStore")
        run_context = replace(
            context,
            run_id=run_id,
            correlation_id=context.correlation_id or run_id,
            evidence_session=store,
        )
        self._ledger_for(run_context)
        checked_inputs = validate_value(
            definition.input_type, inputs, f"{definition.id} input"
        )
        tools, judgments, providers = self._definitions(definition)
        if any(tool.effect is ToolEffect.MUTATION for tool in tools.values()):
            unresolved = Unresolved(
                UnresolvedReason.PERMISSION_DENIAL,
                (definition.id,),
                "the read-only runtime cannot admit mutation tools",
            )
            return self._record_result(
                run_id,
                RunResult(
                    TerminalStatus.UNRESOLVED,
                    partial_findings=(),
                    unresolved=(unresolved,),
                ),
            )
        self._emit(
            run_context,
            EventKind.OPERATION_STARTED,
            operation_id=f"{run_id}:run",
            definition_id=definition.id,
            data={"definition_version": definition.version},
        )
        state = _RunState(store, {}, {}, {}, {}, {}, [])
        try:
            initial = compile_agent(
                definition,
                task_input=checked_inputs,
                available_evidence=tuple(record.id for record in store.records),
                host_context_keys=("scope", *run_context.host_dependencies),
            )
            retrieval_ids = tuple(
                node.definition_id
                for node in initial.nodes
                if node.kind is NodeKind.RETRIEVAL
            )
            snapshots = await asyncio.gather(
                *(
                    self._retrieve(providers[provider_id], checked_inputs, run_context)
                    for provider_id in retrieval_ids
                )
            )
            state.candidates.update((snapshot.id, snapshot) for snapshot in snapshots)
            program = compile_agent(
                definition,
                candidate_sets=state.candidates,
                task_input=checked_inputs,
                available_evidence=tuple(record.id for record in store.records),
                host_context_keys=("scope", *run_context.host_dependencies),
            )
            state.statuses = {
                node.id: (
                    NodeStatus.COMPLETED
                    if node.kind is NodeKind.RETRIEVAL
                    else NodeStatus.PENDING
                )
                for node in program.nodes
            }
            nodes = {node.id: node for node in program.nodes}
            completion_node = next(
                node for node in program.nodes if node.kind is NodeKind.COMPLETION
            )
            pending = [
                node.id
                for node in program.nodes
                if node.kind not in {NodeKind.RETRIEVAL, NodeKind.COMPLETION}
            ]
            while pending:
                for node_id in tuple(pending):
                    if any(
                        state.statuses[dependency] is NodeStatus.SKIPPED
                        for dependency in nodes[node_id].dependencies
                    ):
                        state.statuses[node_id] = NodeStatus.SKIPPED
                        pending.remove(node_id)
                ready = [
                    node_id
                    for node_id in pending
                    if all(
                        state.statuses[dependency] is NodeStatus.COMPLETED
                        for dependency in nodes[node_id].dependencies
                    )
                ]
                if not ready:
                    raise _RunUnresolved(
                        Unresolved(
                            UnresolvedReason.NO_PROGRESS,
                            (definition.id,),
                            "no remaining node has satisfied dependencies",
                        )
                    )
                outcomes = await asyncio.gather(
                    *(
                        self._execute_node(
                            nodes[node_id],
                            tools,
                            judgments,
                            checked_inputs,
                            run_context,
                            state,
                        )
                        for node_id in ready
                    ),
                    return_exceptions=True,
                )
                for node_id, outcome in zip(ready, outcomes, strict=True):
                    pending.remove(node_id)
                    if isinstance(outcome, BaseException):
                        state.statuses[node_id] = NodeStatus.FAILED
                        raise outcome
            if any(
                state.statuses[dependency] is not NodeStatus.COMPLETED
                for dependency in completion_node.dependencies
            ):
                raise _RunUnresolved(
                    Unresolved(
                        UnresolvedReason.NO_PROGRESS,
                        (definition.id,),
                        "an inactive or unresolved branch blocks completion",
                    )
                )
            value = await self._completion(definition, run_context, state)
            state.statuses[completion_node.id] = NodeStatus.COMPLETED
            usage = _usage_total(state.usages)
            self._emit(
                run_context,
                EventKind.OPERATION_COMPLETED,
                operation_id=f"{run_id}:run",
                definition_id=definition.id,
                question_id=completion_node.id,
                data={
                    "result_fingerprint": program.digest,
                    "evidence_refs": [record.id for record in store.records],
                    "usage": {
                        "coverage": usage.coverage.value,
                        "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                        "provider_attempts": usage.provider_attempts,
                        "submitted_questions": usage.submitted_questions,
                    },
                },
            )
            result: RunResult[OutputT] = RunResult(
                TerminalStatus.COMPLETED,
                value=value,
                partial_findings=tuple(state.findings.values()),
                evidence_refs=tuple(record.id for record in store.records),
                usage=usage,
            )
            return self._record_result(run_id, result)
        except asyncio.CancelledError as error:
            diagnostic = diagnostic_for_error(
                error,
                definition_id=definition.id,
                node_id=None,
                source_path=("runs", run_id),
            )
            self._emit(
                run_context,
                EventKind.OPERATION_CANCELLED,
                operation_id=f"{run_id}:run",
                definition_id=definition.id,
                reason_code=diagnostic.code,
                data={"diagnostic": diagnostic.to_dict()},
            )
            self._record_result(
                run_id,
                RunResult(
                    TerminalStatus.CANCELLED,
                    partial_findings=tuple(state.findings.values()),
                    evidence_refs=tuple(record.id for record in store.records),
                    usage=_usage_total(state.usages),
                    failure="cancelled",
                ),
            )
            raise
        except _RunUnresolved as error:
            diagnostic = diagnostic_for_unresolved(
                error.unresolved,
                definition_id=definition.id,
                source_path=("runs", run_id),
            )
            self._emit(
                run_context,
                EventKind.OPERATION_UNRESOLVED,
                operation_id=f"{run_id}:run",
                definition_id=definition.id,
                reason_code=diagnostic.code,
                data={"diagnostic": diagnostic.to_dict()},
            )
            result = RunResult(
                TerminalStatus.UNRESOLVED,
                partial_findings=tuple(state.findings.values()),
                evidence_refs=tuple(record.id for record in store.records),
                unresolved=(error.unresolved,),
                usage=_usage_total(state.usages),
            )
            return self._record_result(run_id, result)
        except StaleInputError as error:
            if isinstance(error, StaleDecisionResult):
                state.usages.append(error.usage)
            unresolved = Unresolved(
                UnresolvedReason.STALE_SOURCE,
                (definition.id,),
                "an input changed while a decision was in flight",
                needed="refresh_source_evidence",
            )
            diagnostic = diagnostic_for_unresolved(
                unresolved,
                definition_id=definition.id,
                source_path=("runs", run_id),
            )
            self._emit(
                run_context,
                EventKind.OPERATION_UNRESOLVED,
                operation_id=f"{run_id}:run",
                definition_id=definition.id,
                reason_code=diagnostic.code,
                data={"diagnostic": diagnostic.to_dict()},
            )
            result = RunResult(
                TerminalStatus.UNRESOLVED,
                partial_findings=tuple(state.findings.values()),
                evidence_refs=tuple(record.id for record in store.records),
                unresolved=(unresolved,),
                usage=_usage_total(state.usages),
            )
            return self._record_result(run_id, result)
        except (BudgetExhaustedError, DeadlineExceededError) as error:
            unresolved = Unresolved(
                UnresolvedReason.BUDGET_EXHAUSTION,
                (definition.id,),
                "a shared run limit or deadline was exhausted",
                needed=type(error).__name__,
            )
            diagnostic = diagnostic_for_unresolved(
                unresolved,
                definition_id=definition.id,
                source_path=("runs", run_id),
            )
            self._emit(
                run_context,
                EventKind.OPERATION_UNRESOLVED,
                operation_id=f"{run_id}:run",
                definition_id=definition.id,
                reason_code=diagnostic.code,
                data={"diagnostic": diagnostic.to_dict()},
            )
            result = RunResult(
                TerminalStatus.UNRESOLVED,
                partial_findings=tuple(state.findings.values()),
                evidence_refs=tuple(record.id for record in store.records),
                unresolved=(unresolved,),
                usage=_usage_total(state.usages),
            )
            return self._record_result(run_id, result)
        except ProviderError as error:
            attempts = len(getattr(error, "attempts", ()))
            state.usages.append(
                Usage(provider_attempts=attempts, submitted_questions=attempts)
            )
            diagnostic = diagnostic_for_error(
                error,
                definition_id=definition.id,
                source_path=("runs", run_id),
            )
            self._emit(
                run_context,
                EventKind.OPERATION_FAILED,
                operation_id=f"{run_id}:run",
                definition_id=definition.id,
                reason_code=diagnostic.code,
                data={"diagnostic": diagnostic.to_dict()},
            )
            result = RunResult(
                TerminalStatus.FAILED,
                partial_findings=tuple(state.findings.values()),
                evidence_refs=tuple(record.id for record in store.records),
                usage=_usage_total(state.usages),
                failure=diagnostic.code,
            )
            return self._record_result(run_id, result)
        except Exception as error:  # noqa: BLE001 - convert to a sanitized run result
            diagnostic = diagnostic_for_error(
                error,
                definition_id=definition.id,
                source_path=("runs", run_id),
            )
            self._emit(
                run_context,
                EventKind.OPERATION_FAILED,
                operation_id=f"{run_id}:run",
                definition_id=definition.id,
                reason_code=diagnostic.code,
                data={"diagnostic": diagnostic.to_dict()},
            )
            result = RunResult(
                TerminalStatus.FAILED,
                partial_findings=tuple(state.findings.values()),
                evidence_refs=tuple(record.id for record in store.records),
                usage=_usage_total(state.usages),
                failure=diagnostic.code,
            )
            return self._record_result(run_id, result)

    def run_sync(
        self,
        definition: AgentDefinition[InputT, OutputT],
        inputs: InputT,
        context: RunContext,
    ) -> RunResult[OutputT]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run(definition, inputs, context))
        raise RuntimeConfigurationError(
            "Runtime.run_sync cannot be called from a running event loop"
        )
