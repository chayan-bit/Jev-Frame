from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any, NoReturn

from pydantic import BaseModel

from .definitions import (
    MISSING,
    NO_FIT_KEY,
    AgentDefinition,
    Binding,
    CandidateBinding,
    CandidateProvider,
    CandidateSet,
    ChoiceQuestion,
    ConstantBinding,
    DefaultBinding,
    DefinitionError,
    DerivationBinding,
    GeneratedBinding,
    HostContextBinding,
    Judgment,
    JudgmentBinding,
    NoulQuestion,
    ScoreQuestion,
    SourceBinding,
    TaskInputBinding,
    Tool,
    ToolEffect,
    validate_value,
)
from .state import canonical_digest, canonical_json

MAX_CHOICE_OPTIONS = 255
MAX_SCORE_LEVELS = 10


class CompilerError(DefinitionError):
    """A definition cannot produce a safe, bounded decision program."""

    def __init__(self, diagnostic: CompilationDiagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)


class NodeKind(str, Enum):
    RETRIEVAL = "retrieval"
    DERIVATION = "derivation"
    JUDGMENT = "judgment"
    INVOCATION = "invocation"
    COMPLETION = "completion"


@dataclass(frozen=True, slots=True)
class CompilationDiagnostic:
    code: str
    message: str
    definition_id: str
    node_id: str | None = None
    subject: str | None = None
    binding: str | None = None
    reference: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            item.name: getattr(self, item.name)
            for item in fields(self)
            if getattr(self, item.name) is not None
        }


@dataclass(frozen=True, slots=True)
class CompiledBinding:
    parameter: str
    source: str
    reference: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"parameter": self.parameter, "source": self.source}
        if self.reference is not None:
            result["reference"] = self.reference
        return result


@dataclass(frozen=True, slots=True)
class CompiledNode:
    id: str
    kind: NodeKind
    definition_id: str
    version: str
    dependencies: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    applicability: str | None = None
    effect: str | None = None
    bindings: tuple[CompiledBinding, ...] = ()
    unresolved: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind.value,
            "definition_id": self.definition_id,
            "version": self.version,
            "dependencies": list(self.dependencies),
            "outputs": list(self.outputs),
            "bindings": [binding.to_dict() for binding in self.bindings],
            "unresolved": list(self.unresolved),
        }
        if self.applicability is not None:
            result["applicability"] = self.applicability
        if self.effect is not None:
            result["effect"] = self.effect
        return result


@dataclass(frozen=True, slots=True)
class CompiledOption:
    key: str
    description: str
    source_id: str | None = None
    source_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "key": self.key,
            "description": self.description,
        }
        if self.source_id is not None:
            result["source_id"] = self.source_id
        if self.source_version is not None:
            result["source_version"] = self.source_version
        return result


@dataclass(frozen=True, slots=True)
class CompiledQuestion:
    routing_id: str
    judgment_id: str
    primitive: str
    instructions: str
    subjects: tuple[str, ...]
    evidence: tuple[str, ...]
    dependencies: tuple[str, ...]
    applicability: str | None = None
    candidate_set: str | None = None
    options: tuple[CompiledOption, ...] = ()
    score_levels: tuple[str, ...] = ()
    true_description: str | None = None
    false_description: str | None = None
    dispatchable: bool = True

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "routing_id": self.routing_id,
            "judgment_id": self.judgment_id,
            "primitive": self.primitive,
            "instructions": self.instructions,
            "subjects": list(self.subjects),
            "evidence": list(self.evidence),
            "dependencies": list(self.dependencies),
            "options": [option.to_dict() for option in self.options],
            "score_levels": list(self.score_levels),
            "dispatchable": self.dispatchable,
        }
        if self.applicability is not None:
            result["applicability"] = self.applicability
        if self.candidate_set is not None:
            result["candidate_set"] = self.candidate_set
        if self.true_description is not None:
            result["true_description"] = self.true_description
        if self.false_description is not None:
            result["false_description"] = self.false_description
        return result


@dataclass(frozen=True, slots=True)
class EvaluationStage:
    index: int
    question_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "question_ids": list(self.question_ids)}


@dataclass(frozen=True, slots=True)
class CandidatePreview:
    id: str
    version: str | None
    coverage: str | None
    scope: str | None
    supplied: bool
    options: tuple[CompiledOption, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "coverage": self.coverage,
            "scope": self.scope,
            "supplied": self.supplied,
            "options": [option.to_dict() for option in self.options],
        }


@dataclass(frozen=True, slots=True)
class CompiledProgram:
    definition_id: str
    definition_version: str
    nodes: tuple[CompiledNode, ...]
    questions: tuple[CompiledQuestion, ...]
    stages: tuple[EvaluationStage, ...]
    candidates: tuple[CandidatePreview, ...]
    package_versions: tuple[tuple[str, str], ...] = ()
    diagnostics: tuple[CompilationDiagnostic, ...] = ()

    def _payload(self) -> dict[str, Any]:
        return {
            "definition_id": self.definition_id,
            "definition_version": self.definition_version,
            "nodes": [node.to_dict() for node in self.nodes],
            "questions": [question.to_dict() for question in self.questions],
            "stages": [stage.to_dict() for stage in self.stages],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "packages": [
                {"id": package_id, "version": version}
                for package_id, version in self.package_versions
            ],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["digest"] = self.digest
        return payload

    def to_json(self) -> str:
        return canonical_json(self.to_dict())


def _read_path(value: Any, path: tuple[str | int, ...]) -> bool:
    current = value
    for part in path:
        if isinstance(current, BaseModel) and type(part) is str:
            if part not in current.__class__.model_fields:
                return False
            current = getattr(current, part)
        elif (
            is_dataclass(current)
            and not isinstance(current, type)
            and type(part) is str
        ):
            if part not in {item.name for item in fields(current)}:
                return False
            current = getattr(current, part)
        elif isinstance(current, Mapping):
            if part not in current:
                return False
            current = current[part]
        elif (
            isinstance(current, Sequence)
            and not isinstance(current, (str, bytes))
            and type(part) is int
            and 0 <= part < len(current)
        ):
            current = current[part]
        else:
            return False
    return True


def _definition_fields(annotation: Any) -> set[str] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return set(annotation.model_fields)
    if isinstance(annotation, type) and is_dataclass(annotation):
        return {item.name for item in fields(annotation)}
    return None


class _Compiler:
    def __init__(
        self,
        definition: AgentDefinition[Any, Any],
        *,
        candidate_sets: Mapping[str, CandidateSet],
        available_evidence: Collection[str],
        task_input: Any,
        host_context_keys: Collection[str],
        question_ids: Mapping[str, str],
        capability_roots: tuple[str, ...],
    ) -> None:
        self.definition = definition
        self.snapshots = dict(candidate_sets)
        self.available_evidence = frozenset(available_evidence)
        self.task_input = task_input
        self.host_context_keys = frozenset(host_context_keys)
        self.question_ids = dict(question_ids)
        self.capability_roots = capability_roots
        self.tools = {
            item.id: item
            for item in definition.tools
            + tuple(tool for package in definition.packages for tool in package.tools)
        }
        self.judgments = {
            item.id: item
            for item in definition.judgments
            + tuple(
                judgment
                for package in definition.packages
                for judgment in package.judgments
            )
        }
        self.providers = {
            item.id: item
            for item in definition.candidate_providers
            + tuple(
                provider
                for package in definition.packages
                for provider in package.candidate_providers
            )
        }
        self.producers: dict[str, list[Tool]] = {}
        for tool in self.tools.values():
            for output in tool.produces_evidence:
                self.producers.setdefault(output, []).append(tool)
        self.nodes: dict[str, CompiledNode] = {}
        self.questions: dict[str, CompiledQuestion] = {}
        self.candidates: dict[str, CandidatePreview] = {}
        self.diagnostics: list[CompilationDiagnostic] = []
        self.visiting: set[str] = set()

    def fail(
        self,
        code: str,
        message: str,
        *,
        node_id: str | None = None,
        subject: str | None = None,
        binding: str | None = None,
        reference: str | None = None,
    ) -> NoReturn:
        raise CompilerError(
            CompilationDiagnostic(
                code,
                message,
                self.definition.id,
                node_id,
                subject,
                binding,
                reference,
            )
        )

    def compile(self) -> CompiledProgram:
        unknown_snapshots = set(self.snapshots) - set(self.providers)
        if unknown_snapshots:
            self.fail(
                "unknown_candidate_snapshot",
                f"definition {self.definition.id} has snapshots for unregistered providers {sorted(unknown_snapshots)}",
                reference=min(unknown_snapshots),
            )
        unknown_question_ids = set(self.question_ids) - set(self.judgments)
        if unknown_question_ids:
            self.fail(
                "unknown_question_id",
                f"question routing overrides reference unknown judgments {sorted(unknown_question_ids)}",
                reference=min(unknown_question_ids),
            )
        if len(set(self.question_ids.values())) != len(self.question_ids):
            self.fail(
                "duplicate_question_id",
                "question routing IDs must be unique",
            )
        if self.task_input is not MISSING:
            self.task_input = validate_value(
                self.definition.input_type,
                self.task_input,
                f"{self.definition.id} preview input",
            )
        self._validate_output_contract()

        roots = tuple(
            dict.fromkeys(
                self.definition.completion.required_findings
                + tuple(self.definition.completion.result_bindings.values())
            )
        )
        completion_dependencies = [
            self.resolve_need(root, "completion") for root in roots
        ]
        for capability in self.capability_roots:
            completion_dependencies.append(self.visit_tool(self.tools[capability]))
        completion_id = f"complete:{self.definition.id}"
        self.nodes[completion_id] = CompiledNode(
            completion_id,
            NodeKind.COMPLETION,
            self.definition.id,
            self.definition.version,
            tuple(dict.fromkeys(item for item in completion_dependencies if item)),
            tuple(self.definition.completion.result_bindings),
        )
        stages = self._stages()
        return CompiledProgram(
            self.definition.id,
            self.definition.version,
            tuple(self.nodes.values()),
            tuple(self.questions.values()),
            stages,
            tuple(self.candidates.values()),
            tuple(
                (package.id, package.version) for package in self.definition.packages
            ),
            tuple(self.diagnostics),
        )

    def _validate_output_contract(self) -> None:
        output_fields = _definition_fields(self.definition.output_type)
        binding_fields = set(self.definition.completion.result_bindings)
        if output_fields is None:
            if binding_fields:
                self.fail(
                    "unsupported_result_binding",
                    "scalar outputs cannot use named result bindings",
                    node_id=f"complete:{self.definition.id}",
                )
        elif binding_fields and binding_fields != output_fields:
            self.fail(
                "result_binding_mismatch",
                f"completion result bindings mismatch; missing={sorted(output_fields - binding_fields)}, extra={sorted(binding_fields - output_fields)}",
                node_id=f"complete:{self.definition.id}",
            )

    def resolve_need(
        self,
        reference: str,
        subject: str,
        *,
        binding: str | None = None,
    ) -> str | None:
        if reference in self.available_evidence:
            return None
        if reference in self.judgments:
            return self.visit_judgment(self.judgments[reference])
        if reference in self.providers:
            return self.visit_provider(reference, subject)
        producers = self.producers.get(reference, [])
        if len(producers) == 1:
            return self.visit_tool(producers[0])
        if len(producers) > 1:
            self.fail(
                "ambiguous_evidence_producer",
                f"evidence {reference!r} has multiple permitted producers {[item.id for item in producers]}",
                subject=subject,
                binding=binding,
                reference=reference,
            )
        self.fail(
            "missing_evidence_producer",
            f"definition {self.definition.id} cannot produce required reference {reference!r} for {subject}",
            subject=subject,
            binding=binding,
            reference=reference,
        )

    def visit_provider(self, provider_id: str, subject: str) -> str:
        node_id = f"retrieve:{provider_id}"
        if node_id in self.nodes:
            return node_id
        provider = self.providers[provider_id]
        snapshot = self.snapshots.get(provider_id)
        unresolved: tuple[str, ...] = ()
        if snapshot is None:
            unresolved = (provider_id,)
            self.diagnostics.append(
                CompilationDiagnostic(
                    "missing_candidate_snapshot",
                    f"candidate snapshot {provider_id!r} is required for {subject}",
                    self.definition.id,
                    node_id,
                    subject,
                    reference=provider_id,
                )
            )
            preview = CandidatePreview(provider_id, None, None, None, False)
        else:
            if snapshot.id != provider_id:
                self.fail(
                    "candidate_snapshot_mismatch",
                    f"candidate snapshot key {provider_id!r} contains id {snapshot.id!r}",
                    node_id=node_id,
                    subject=subject,
                    reference=provider_id,
                )
            options = tuple(
                CompiledOption(
                    item.key,
                    item.description,
                    item.source_id,
                    item.source_version,
                )
                for item in snapshot.candidates
            )
            preview = CandidatePreview(
                snapshot.id,
                snapshot.version,
                snapshot.coverage.value,
                snapshot.scope,
                True,
                options,
            )
        bindings: list[CompiledBinding] = []
        for parameter, binding in provider.bindings.items():
            compiled, _ = self._binding(provider, parameter, binding)
            bindings.append(compiled)
        self.candidates[provider_id] = preview
        self.nodes[node_id] = CompiledNode(
            node_id,
            NodeKind.RETRIEVAL,
            provider.id,
            provider.version,
            outputs=(provider_id,),
            effect=ToolEffect.READ.value,
            bindings=tuple(bindings),
            unresolved=unresolved,
        )
        return node_id

    def visit_judgment(self, judgment: Judgment) -> str:
        node_id = f"judge:{judgment.id}"
        if node_id in self.nodes:
            return node_id
        if node_id in self.visiting:
            self.fail(
                "dependency_cycle",
                f"judgment dependency cycle reaches {judgment.id}",
                node_id=node_id,
                subject=judgment.subjects[0].name,
                reference=judgment.id,
            )
        self.visiting.add(node_id)
        dependencies: list[str] = []
        for dependency_id in judgment.dependencies:
            dependencies.append(self.visit_judgment(self.judgments[dependency_id]))
        for selector in judgment.evidence:
            dependency = self.resolve_need(
                selector.name,
                judgment.id,
                binding=selector.name,
            )
            if dependency:
                dependencies.append(dependency)
        if judgment.candidate_set is not None:
            if judgment.candidate_set not in self.providers:
                self.fail(
                    "unknown_candidate_provider",
                    f"judgment {judgment.id} references unknown candidate provider {judgment.candidate_set}",
                    node_id=node_id,
                    subject=judgment.subjects[0].name,
                    reference=judgment.candidate_set,
                )
            dependencies.append(
                self.visit_provider(judgment.candidate_set, judgment.id)
            )
        question = self._question(judgment, tuple(dict.fromkeys(dependencies)))
        self.questions[judgment.id] = question
        self.nodes[node_id] = CompiledNode(
            node_id,
            NodeKind.JUDGMENT,
            judgment.id,
            judgment.version,
            tuple(dict.fromkeys(dependencies)),
            (judgment.id,),
            judgment.applicability,
            unresolved=(() if question.dispatchable else (judgment.id,)),
        )
        self.visiting.remove(node_id)
        return node_id

    def _question(
        self, judgment: Judgment, dependencies: tuple[str, ...]
    ) -> CompiledQuestion:
        primitive = judgment.primitive
        subjects = tuple(item.name for item in judgment.subjects)
        evidence = tuple(item.name for item in judgment.evidence)
        instructions = primitive.instructions.rstrip()
        instructions += f"\nSubjects: {', '.join(subjects)}."
        if evidence:
            instructions += f"\nEvidence paths: {', '.join(evidence)}."
        options: tuple[CompiledOption, ...] = ()
        score_levels: tuple[str, ...] = ()
        true_description: str | None = None
        false_description: str | None = None
        primitive_name: str
        dispatchable = all(not self.nodes[item].unresolved for item in dependencies)
        if isinstance(primitive, ChoiceQuestion):
            primitive_name = "choice"
            if judgment.candidate_set is None:
                options = tuple(
                    CompiledOption(item.key, item.description or item.key)
                    for item in primitive.criteria
                )
            else:
                candidate = self.candidates[judgment.candidate_set]
                if candidate.supplied:
                    options = candidate.options + (
                        CompiledOption(
                            NO_FIT_KEY,
                            "None of the supplied candidates fit.",
                        ),
                    )
                    snapshot = self.snapshots[judgment.candidate_set]
                    if snapshot.coverage.value == "failed":
                        dispatchable = False
                        self.diagnostics.append(
                            CompilationDiagnostic(
                                "candidate_retrieval_failed",
                                f"candidate retrieval {snapshot.id!r} failed and cannot be dispatched",
                                self.definition.id,
                                f"judge:{judgment.id}",
                                subjects[0],
                                reference=snapshot.id,
                            )
                        )
                    elif not snapshot.candidates:
                        dispatchable = False
                        self.diagnostics.append(
                            CompilationDiagnostic(
                                "deterministic_no_fit",
                                f"candidate snapshot {snapshot.id!r} is empty; no provider question is needed",
                                self.definition.id,
                                f"judge:{judgment.id}",
                                subjects[0],
                                reference=snapshot.id,
                            )
                        )
                else:
                    dispatchable = False
            if len(options) > MAX_CHOICE_OPTIONS:
                self.fail(
                    "choice_limit_exceeded",
                    f"judgment {judgment.id} has {len(options)} Choice options; maximum is {MAX_CHOICE_OPTIONS} including no-fit",
                    node_id=f"judge:{judgment.id}",
                    subject=subjects[0],
                    reference=judgment.candidate_set,
                )
        elif isinstance(primitive, NoulQuestion):
            primitive_name = "noul"
            true_description = primitive.true_description
            false_description = primitive.false_description
        elif isinstance(primitive, ScoreQuestion):
            primitive_name = "score"
            score_levels = primitive.criteria
            if len(score_levels) > MAX_SCORE_LEVELS:
                self.fail(
                    "score_limit_exceeded",
                    f"judgment {judgment.id} has {len(score_levels)} Score levels; maximum is {MAX_SCORE_LEVELS}",
                    node_id=f"judge:{judgment.id}",
                    subject=subjects[0],
                )
        else:  # pragma: no cover - Judgment validates this boundary.
            raise TypeError("unsupported primitive")
        return CompiledQuestion(
            self.question_ids.get(judgment.id, f"question:{judgment.id}"),
            judgment.id,
            primitive_name,
            instructions,
            subjects,
            evidence,
            judgment.dependencies,
            judgment.applicability,
            judgment.candidate_set,
            options,
            score_levels,
            true_description,
            false_description,
            dispatchable,
        )

    def visit_tool(self, tool: Tool) -> str:
        node_id = f"invoke:{tool.id}"
        if node_id in self.nodes:
            return node_id
        if node_id in self.visiting:
            self.fail(
                "dependency_cycle",
                f"capability dependency cycle reaches {tool.id}",
                node_id=node_id,
                reference=tool.id,
            )
        self.visiting.add(node_id)
        dependencies: list[str] = []
        bindings: list[CompiledBinding] = []
        for evidence in tool.requires_evidence:
            dependency = self.resolve_need(evidence, tool.id)
            if dependency:
                dependencies.append(dependency)
        for parameter, binding in tool.bindings.items():
            compiled, binding_dependencies = self._binding(tool, parameter, binding)
            bindings.append(compiled)
            dependencies.extend(binding_dependencies)
        self._validate_binding_groups(tool)
        unresolved_items = [
            diagnostic.reference or diagnostic.binding or "input"
            for diagnostic in self.diagnostics
            if diagnostic.node_id == node_id
        ]
        for dependency in dependencies:
            unresolved_items.extend(self.nodes[dependency].unresolved)
        unresolved = tuple(dict.fromkeys(unresolved_items))
        self.nodes[node_id] = CompiledNode(
            node_id,
            NodeKind.INVOCATION,
            tool.id,
            tool.version,
            tuple(dict.fromkeys(dependencies)),
            tool.produces_evidence,
            effect=tool.effect.value,
            bindings=tuple(bindings),
            unresolved=unresolved,
        )
        self.visiting.remove(node_id)
        return node_id

    def _binding(
        self, tool: Tool | CandidateProvider, parameter: str, binding: Binding
    ) -> tuple[CompiledBinding, list[str]]:
        node_id = (
            f"invoke:{tool.id}" if isinstance(tool, Tool) else f"retrieve:{tool.id}"
        )
        dependencies: list[str] = []
        if isinstance(binding, TaskInputBinding):
            reference = ".".join(str(item) for item in binding.path)
            if self.task_input is MISSING or not _read_path(
                self.task_input, binding.path
            ):
                self.diagnostics.append(
                    CompilationDiagnostic(
                        "missing_task_input",
                        f"tool {tool.id} binding {parameter} needs task input {reference}",
                        self.definition.id,
                        node_id,
                        tool.id,
                        parameter,
                        reference,
                    )
                )
            return CompiledBinding(parameter, "task_input", reference), dependencies
        if isinstance(binding, HostContextBinding):
            if binding.key not in self.host_context_keys:
                self.diagnostics.append(
                    CompilationDiagnostic(
                        "missing_host_context",
                        f"tool {tool.id} binding {parameter} needs host context {binding.key}",
                        self.definition.id,
                        node_id,
                        tool.id,
                        parameter,
                        binding.key,
                    )
                )
            return CompiledBinding(parameter, "host_context", binding.key), dependencies
        if isinstance(binding, ConstantBinding):
            return CompiledBinding(parameter, "constant"), dependencies
        if isinstance(binding, DefaultBinding):
            return CompiledBinding(parameter, "default"), dependencies
        if isinstance(binding, CandidateBinding):
            if binding.snapshot not in self.providers:
                self.fail(
                    "unknown_candidate_provider",
                    f"tool {tool.id} binding {parameter} references unknown candidate provider {binding.snapshot}",
                    node_id=node_id,
                    subject=tool.id,
                    binding=parameter,
                    reference=binding.snapshot,
                )
            selection = self.judgments.get(binding.selection)
            if selection is None or selection.candidate_set != binding.snapshot:
                self.fail(
                    "invalid_candidate_selection",
                    f"tool {tool.id} binding {parameter} must use a Choice judgment over candidate set {binding.snapshot}",
                    node_id=node_id,
                    subject=tool.id,
                    binding=parameter,
                    reference=binding.selection,
                )
            dependencies.extend(
                (
                    self.visit_provider(binding.snapshot, tool.id),
                    self.visit_judgment(selection),
                )
            )
            return (
                CompiledBinding(
                    parameter,
                    "candidate",
                    f"{binding.snapshot}:{binding.selection}",
                ),
                dependencies,
            )
        if isinstance(binding, SourceBinding):
            dependency = self.resolve_need(binding.evidence, tool.id, binding=parameter)
            if dependency:
                dependencies.append(dependency)
            return CompiledBinding(parameter, "source", binding.evidence), dependencies
        if isinstance(binding, DerivationBinding):
            transformation = self.tools.get(binding.transformation)
            if transformation is None or transformation.effect is not ToolEffect.PURE:
                self.fail(
                    "unknown_derivation",
                    f"tool {tool.id} binding {parameter} requires a registered pure transformation {binding.transformation}",
                    node_id=node_id,
                    subject=tool.id,
                    binding=parameter,
                    reference=binding.transformation,
                )
            derived_dependencies: list[str] = []
            for item in binding.inputs:
                dependency = self.resolve_need(item, tool.id, binding=parameter)
                if dependency:
                    derived_dependencies.append(dependency)
            transform_node = self.visit_tool(transformation)
            derivation_id = f"derive:{tool.id}:{parameter}"
            self.nodes[derivation_id] = CompiledNode(
                derivation_id,
                NodeKind.DERIVATION,
                transformation.id,
                transformation.version,
                tuple(dict.fromkeys(derived_dependencies + [transform_node])),
                (f"{tool.id}.{parameter}",),
                effect=ToolEffect.PURE.value,
            )
            dependencies.append(derivation_id)
            return (
                CompiledBinding(parameter, "derivation", binding.transformation),
                dependencies,
            )
        if isinstance(binding, JudgmentBinding):
            judgment = self.judgments[binding.judgment]
            dependencies.append(self.visit_judgment(judgment))
            return (
                CompiledBinding(parameter, "judgment", binding.judgment),
                dependencies,
            )
        if isinstance(binding, GeneratedBinding):
            capability = self.tools.get(binding.capability)
            if capability is None:
                self.fail(
                    "non_executable_capability",
                    f"tool {tool.id} binding {parameter} requires an executable registered tool capability",
                    node_id=node_id,
                    subject=tool.id,
                    binding=parameter,
                    reference=binding.capability,
                )
            dependencies.append(self.visit_tool(capability))
            return (
                CompiledBinding(parameter, "generated", binding.capability),
                dependencies,
            )
        raise TypeError("Tool validates binding variants")

    def _validate_binding_groups(self, tool: Tool) -> None:
        for group in tool.binding_groups:
            group_bindings = [tool.bindings[name] for name in group.parameters]
            candidate_bindings = [
                item for item in group_bindings if isinstance(item, CandidateBinding)
            ]
            if not candidate_bindings:
                continue
            sources = {(item.snapshot, item.selection) for item in candidate_bindings}
            if len(candidate_bindings) != len(group_bindings) or len(sources) != 1:
                self.fail(
                    "unsafe_binding_group",
                    f"tool {tool.id} binding group {group.parameters} does not share one candidate tuple selection",
                    node_id=f"invoke:{tool.id}",
                    subject=tool.id,
                    binding=",".join(group.parameters),
                )

    def _stages(self) -> tuple[EvaluationStage, ...]:
        routing_ids = [question.routing_id for question in self.questions.values()]
        if len(routing_ids) != len(set(routing_ids)):
            self.fail(
                "duplicate_question_id",
                "compiled question routing IDs must be unique",
            )
        levels: dict[str, int] = {}

        def level(judgment_id: str, stack: set[str]) -> int:
            if judgment_id in levels:
                return levels[judgment_id]
            if judgment_id in stack:
                self.fail(
                    "dependency_cycle",
                    f"judgment dependency cycle reaches {judgment_id}",
                    node_id=f"judge:{judgment_id}",
                    reference=judgment_id,
                )
            stack.add(judgment_id)
            judgment = self.judgments[judgment_id]
            value = (
                max(level(item, stack) for item in judgment.dependencies) + 1
                if judgment.dependencies
                else 0
            )
            stack.remove(judgment_id)
            levels[judgment_id] = value
            return value

        for judgment_id in self.questions:
            level(judgment_id, set())
        grouped: dict[int, list[str]] = {}
        for judgment_id, question in self.questions.items():
            grouped.setdefault(levels[judgment_id], []).append(question.routing_id)
        return tuple(
            EvaluationStage(index, tuple(grouped[index])) for index in sorted(grouped)
        )


def _validate_revision_capabilities(
    definition: AgentDefinition[Any, Any],
    capability_ids: Sequence[str],
    max_steps: int,
) -> tuple[str, ...]:
    if type(max_steps) is not int or max_steps < 0:
        raise DefinitionError("revision max_steps must be a nonnegative integer")
    if len(capability_ids) > max_steps:
        raise DefinitionError(
            f"revision has {len(capability_ids)} steps, maximum is {max_steps}"
        )
    if len(capability_ids) != len(set(capability_ids)):
        raise DefinitionError("a revision cannot repeat a capability")
    tools = {
        tool.id
        for tool in definition.tools
        + tuple(tool for package in definition.packages for tool in package.tools)
    }
    unknown = [item for item in capability_ids if item not in tools]
    if unknown:
        raise CompilerError(
            CompilationDiagnostic(
                "unknown_capability",
                f"definition {definition.id} does not register capabilities {unknown}",
                definition.id,
                reference=unknown[0],
            )
        )
    return tuple(capability_ids)


def compile_judgment(
    judgment: Judgment,
    *,
    candidate_set: CandidateSet | None = None,
    routing_id: str | None = None,
    resolved_dependencies: Collection[str] = (),
) -> CompiledQuestion:
    """Compile one direct decision through the same provider-neutral contract."""

    missing_dependencies = set(judgment.dependencies) - set(resolved_dependencies)
    if missing_dependencies:
        raise CompilerError(
            CompilationDiagnostic(
                "unresolved_judgment_dependency",
                f"judgment {judgment.id} requires prior judgments {sorted(missing_dependencies)}",
                judgment.id,
                f"judge:{judgment.id}",
                judgment.subjects[0].name,
                reference=min(missing_dependencies),
            )
        )
    if judgment.candidate_set is None and candidate_set is not None:
        raise CompilerError(
            CompilationDiagnostic(
                "unexpected_candidate_snapshot",
                f"judgment {judgment.id} does not declare a candidate set",
                judgment.id,
                f"judge:{judgment.id}",
                judgment.subjects[0].name,
                reference=candidate_set.id,
            )
        )
    if judgment.candidate_set is not None and (
        candidate_set is None or candidate_set.id != judgment.candidate_set
    ):
        raise CompilerError(
            CompilationDiagnostic(
                "missing_candidate_snapshot",
                f"judgment {judgment.id} requires candidate set {judgment.candidate_set}",
                judgment.id,
                f"judge:{judgment.id}",
                judgment.subjects[0].name,
                reference=judgment.candidate_set,
            )
        )
    primitive = judgment.primitive
    subjects = tuple(item.name for item in judgment.subjects)
    evidence = tuple(item.name for item in judgment.evidence)
    instructions = primitive.instructions.rstrip()
    instructions += f"\nSubjects: {', '.join(subjects)}."
    if evidence:
        instructions += f"\nEvidence paths: {', '.join(evidence)}."
    options: tuple[CompiledOption, ...] = ()
    score_levels: tuple[str, ...] = ()
    true_description: str | None = None
    false_description: str | None = None
    if isinstance(primitive, ChoiceQuestion):
        primitive_name = "choice"
        if candidate_set is None:
            options = tuple(
                CompiledOption(item.key, item.description or item.key)
                for item in primitive.criteria
            )
        else:
            if candidate_set.coverage.value == "failed":
                raise CompilerError(
                    CompilationDiagnostic(
                        "candidate_retrieval_failed",
                        f"candidate set {candidate_set.id} failed retrieval",
                        judgment.id,
                        f"judge:{judgment.id}",
                        subjects[0],
                        reference=candidate_set.id,
                    )
                )
            if not candidate_set.candidates:
                raise CompilerError(
                    CompilationDiagnostic(
                        "deterministic_no_fit",
                        f"candidate set {candidate_set.id} is empty",
                        judgment.id,
                        f"judge:{judgment.id}",
                        subjects[0],
                        reference=candidate_set.id,
                    )
                )
            options = tuple(
                CompiledOption(
                    item.key,
                    item.description,
                    item.source_id,
                    item.source_version,
                )
                for item in candidate_set.candidates
            ) + (CompiledOption(NO_FIT_KEY, "None of the supplied candidates fit."),)
        if len(options) > MAX_CHOICE_OPTIONS:
            raise CompilerError(
                CompilationDiagnostic(
                    "choice_limit_exceeded",
                    f"judgment {judgment.id} exceeds {MAX_CHOICE_OPTIONS} Choice options including no-fit",
                    judgment.id,
                    f"judge:{judgment.id}",
                    subjects[0],
                    reference=judgment.candidate_set,
                )
            )
    elif isinstance(primitive, NoulQuestion):
        primitive_name = "noul"
        true_description = primitive.true_description
        false_description = primitive.false_description
    elif isinstance(primitive, ScoreQuestion):
        primitive_name = "score"
        score_levels = primitive.criteria
        if len(score_levels) > MAX_SCORE_LEVELS:
            raise CompilerError(
                CompilationDiagnostic(
                    "score_limit_exceeded",
                    f"judgment {judgment.id} exceeds {MAX_SCORE_LEVELS} Score levels",
                    judgment.id,
                    f"judge:{judgment.id}",
                    subjects[0],
                )
            )
    else:  # pragma: no cover - Judgment validates the boundary.
        raise TypeError("unsupported primitive")
    return CompiledQuestion(
        routing_id or f"question:{judgment.id}",
        judgment.id,
        primitive_name,
        instructions,
        subjects,
        evidence,
        judgment.dependencies,
        judgment.applicability,
        judgment.candidate_set,
        options,
        score_levels,
        true_description,
        false_description,
    )


def compile_agent(
    definition: AgentDefinition[Any, Any],
    *,
    candidate_sets: Mapping[str, CandidateSet] | None = None,
    available_evidence: Collection[str] = (),
    task_input: Any = MISSING,
    host_context_keys: Collection[str] = (),
    question_ids: Mapping[str, str] | None = None,
    capability_revision: Sequence[str] = (),
    max_revision_steps: int = 0,
) -> CompiledProgram:
    """Compile definitions and supplied snapshots without invoking any callback."""

    capabilities = _validate_revision_capabilities(
        definition, capability_revision, max_revision_steps
    )
    return _Compiler(
        definition,
        candidate_sets={} if candidate_sets is None else candidate_sets,
        available_evidence=available_evidence,
        task_input=task_input,
        host_context_keys=host_context_keys,
        question_ids={} if question_ids is None else question_ids,
        capability_roots=capabilities,
    ).compile()


def preview_agent(
    definition: AgentDefinition[Any, Any], **kwargs: Any
) -> dict[str, Any]:
    """Return a stable JSON-compatible view of :func:`compile_agent`."""

    return compile_agent(definition, **kwargs).to_dict()
