from __future__ import annotations

import inspect
import math
import re
import time
import types
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from types import MappingProxyType, NoneType
from typing import (
    Any,
    Generic,
    Literal,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from pydantic import BaseModel, TypeAdapter, ValidationError


class JevFrameError(Exception):
    """Base class for public Jev-Frame failures."""


class DefinitionError(JevFrameError):
    """A reusable definition is structurally invalid."""


class BindingError(DefinitionError):
    """A tool argument source is missing or invalid."""


class UnsupportedTypeError(DefinitionError):
    """An annotation falls outside the supported public subset."""


class InputValidationError(JevFrameError):
    """A caller value fails strict boundary validation."""


class ScopeError(JevFrameError):
    """A value or operation is outside the active scope."""


class StaleInputError(JevFrameError):
    """An input changed after the operation was prepared."""


class ProviderError(JevFrameError):
    """The configured decision provider failed."""


class ProviderTimeoutError(ProviderError):
    """The configured decision provider timed out."""


class ResponseValidationError(ProviderError):
    """A provider response did not match the dispatched request."""


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"


MISSING = _Missing()
_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _text(value: str, name: str) -> None:
    if type(value) is not str or not value.strip():
        raise DefinitionError(f"{name} must be a non-empty string")


def _version(value: str, name: str = "version") -> None:
    if type(value) is not str or _VERSION.fullmatch(value) is None:
        raise DefinitionError(f"{name} must be a semantic version")


def _supported(annotation: Any, seen: set[type[Any]] | None = None) -> bool:
    if annotation in {str, int, float, bool, None, NoneType}:
        return True
    if annotation in {Any, object, inspect.Signature.empty} or isinstance(
        annotation, str
    ):
        return False

    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is Literal:
        return bool(arguments) and all(
            value is None or type(value) in {str, int, float, bool}
            for value in arguments
        )
    if origin is list:
        return len(arguments) == 1 and _supported(arguments[0], seen)
    if origin in {dict, Mapping}:
        return (
            len(arguments) == 2
            and arguments[0] is str
            and _supported(arguments[1], seen)
        )
    if origin in {Union, types.UnionType}:
        non_null = tuple(
            argument for argument in arguments if argument not in {None, NoneType}
        )
        return (
            len(arguments) == 2 and len(non_null) == 1 and _supported(non_null[0], seen)
        )

    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return issubclass(annotation, str) and all(
            type(member.value) is str for member in annotation
        )

    if not isinstance(annotation, type):
        return False
    seen = set() if seen is None else seen
    if annotation in seen:
        return True
    seen.add(annotation)

    if issubclass(annotation, BaseModel):
        return all(
            model_field.annotation is not None
            and _supported(model_field.annotation, seen)
            for model_field in cast(type[BaseModel], annotation).model_fields.values()
        )
    if is_dataclass(annotation):
        try:
            hints = get_type_hints(annotation, include_extras=True)
        except (NameError, TypeError) as error:
            raise UnsupportedTypeError(
                f"cannot resolve annotations for {annotation.__name__}"
            ) from error
        return all(
            name in hints and _supported(hints[name], seen)
            for name in (item.name for item in fields(annotation))
        )
    return False


def ensure_supported_type(annotation: Any, name: str = "annotation") -> None:
    """Reject annotations outside the finite public type subset."""

    if not _supported(annotation):
        raise UnsupportedTypeError(f"unsupported {name}: {annotation!r}")


def _literal_types_match(annotation: Any, value: Any) -> bool:
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is Literal:
        return any(type(value) is type(option) and value == option for option in arguments)
    if origin is list and isinstance(value, list):
        return all(_literal_types_match(arguments[0], item) for item in value)
    if origin in {dict, Mapping} and isinstance(value, Mapping):
        return all(_literal_types_match(arguments[1], item) for item in value.values())
    if origin in {Union, types.UnionType}:
        if value is None:
            return True
        child = next(
            item for item in arguments if item not in {None, NoneType}
        )
        return _literal_types_match(child, value)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if isinstance(value, annotation):
            return all(
                field.annotation is None
                or _literal_types_match(field.annotation, getattr(value, name))
                for name, field in annotation.model_fields.items()
            )
        if isinstance(value, Mapping):
            return all(
                name not in value
                or field.annotation is None
                or _literal_types_match(field.annotation, value[name])
                for name, field in annotation.model_fields.items()
            )
    if isinstance(annotation, type) and is_dataclass(annotation):
        hints = get_type_hints(annotation, include_extras=True)
        if isinstance(value, annotation):
            return all(
                _literal_types_match(hints[item.name], getattr(value, item.name))
                for item in fields(annotation)
            )
    return True


def validate_value(annotation: Any, value: Any, name: str = "value") -> Any:
    """Validate a caller value without scalar coercion."""

    ensure_supported_type(annotation, name)
    if not _literal_types_match(annotation, value):
        raise InputValidationError(f"invalid {name}")
    try:
        return TypeAdapter(annotation).validate_python(value, strict=True)
    except ValidationError as error:
        raise InputValidationError(f"invalid {name}") from error


@dataclass(frozen=True, slots=True)
class TaskInputBinding:
    path: tuple[str | int, ...]

    def __post_init__(self) -> None:
        if not self.path or any(type(part) not in {str, int} for part in self.path):
            raise BindingError(
                "task input paths must contain string or integer segments"
            )


@dataclass(frozen=True, slots=True)
class HostContextBinding:
    key: str

    def __post_init__(self) -> None:
        _text(self.key, "host context key")


@dataclass(frozen=True, slots=True)
class ConstantBinding:
    value: Any


@dataclass(frozen=True, slots=True)
class DefaultBinding:
    pass


@dataclass(frozen=True, slots=True)
class CandidateBinding:
    snapshot: str
    selection: str

    def __post_init__(self) -> None:
        _text(self.snapshot, "candidate snapshot")
        _text(self.selection, "candidate selection")


@dataclass(frozen=True, slots=True)
class SourceField:
    path: tuple[str | int, ...]

    def __post_init__(self) -> None:
        if not self.path or any(type(part) not in {str, int} for part in self.path):
            raise BindingError(
                "source field paths must contain string or integer segments"
            )


@dataclass(frozen=True, slots=True)
class SourceSpan:
    start: int
    end: int

    def __post_init__(self) -> None:
        if (
            type(self.start) is not int
            or type(self.end) is not int
            or self.start < 0
            or self.end < self.start
        ):
            raise BindingError("source span must be a valid half-open character range")


@dataclass(frozen=True, slots=True)
class SourceBinding:
    evidence: str
    field_or_span: SourceField | SourceSpan

    def __post_init__(self) -> None:
        _text(self.evidence, "source evidence")


@dataclass(frozen=True, slots=True)
class DerivationBinding:
    transformation: str
    inputs: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.transformation, "transformation")
        if not self.inputs or any(
            type(value) is not str or not value for value in self.inputs
        ):
            raise BindingError("a derivation requires named inputs")


@dataclass(frozen=True, slots=True)
class JudgmentBinding:
    judgment: str

    def __post_init__(self) -> None:
        _text(self.judgment, "judgment binding")


@dataclass(frozen=True, slots=True)
class GeneratedBinding:
    capability: str

    def __post_init__(self) -> None:
        _text(self.capability, "generation capability")


Binding = (
    TaskInputBinding
    | HostContextBinding
    | ConstantBinding
    | DefaultBinding
    | CandidateBinding
    | SourceBinding
    | DerivationBinding
    | JudgmentBinding
    | GeneratedBinding
)
_BINDING_TYPES = (
    TaskInputBinding,
    HostContextBinding,
    ConstantBinding,
    DefaultBinding,
    CandidateBinding,
    SourceBinding,
    DerivationBinding,
    JudgmentBinding,
    GeneratedBinding,
)


@dataclass(frozen=True, slots=True)
class BindingGroup:
    parameters: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.parameters) < 2 or len(set(self.parameters)) != len(
            self.parameters
        ):
            raise BindingError(
                "a binding group requires at least two unique parameters"
            )


class ToolEffect(str, Enum):
    PURE = "pure"
    READ = "read"
    MUTATION = "mutation"


class RetryOwner(str, Enum):
    NONE = "none"
    RUNTIME = "runtime"
    CALLABLE = "callable"


@dataclass(frozen=True, slots=True)
class MutationContract:
    supports_idempotency_key: bool
    reconcile: Callable[[str], Any] | None = None
    durable_intent_required: bool = True
    idempotency_parameter: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.supports_idempotency_key) is not bool
            or type(self.durable_intent_required) is not bool
        ):
            raise DefinitionError("mutation contract flags must be booleans")
        if self.reconcile is not None and not callable(self.reconcile):
            raise DefinitionError("mutation reconciliation must be callable")
        if not self.supports_idempotency_key and self.reconcile is None:
            raise DefinitionError(
                "a mutation needs idempotency support or reconciliation"
            )
        if self.supports_idempotency_key:
            if self.idempotency_parameter is None:
                raise DefinitionError(
                    "idempotency support requires its tool parameter name"
                )
            _text(self.idempotency_parameter, "idempotency parameter")
        elif self.idempotency_parameter is not None:
            raise DefinitionError(
                "an idempotency parameter requires idempotency support"
            )


@dataclass(frozen=True, slots=True)
class Tool:
    id: str
    version: str
    purpose: str
    function: Callable[..., Any] = field(repr=False, compare=False)
    bindings: Mapping[str, Binding]
    effect: ToolEffect = ToolEffect.PURE
    timeout: float = 30.0
    retry_owner: RetryOwner = RetryOwner.NONE
    binding_groups: tuple[BindingGroup, ...] = ()
    mutation: MutationContract | None = None
    requires_evidence: tuple[str, ...] = ()
    produces_evidence: tuple[str, ...] = ()
    scope_requirements: tuple[str, ...] = ()
    blocking: bool = False
    output_type: Any = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _text(self.id, "tool id")
        _version(self.version)
        _text(self.purpose, "tool purpose")
        if not callable(self.function):
            raise DefinitionError("tool function must be callable")
        if type(self.blocking) is not bool or (
            self.blocking and inspect.iscoroutinefunction(self.function)
        ):
            raise DefinitionError(
                "tool blocking must be a boolean and asynchronous tools cannot be blocking"
            )
        if (
            type(self.timeout) not in {int, float}
            or not math.isfinite(self.timeout)
            or self.timeout <= 0
        ):
            raise DefinitionError("tool timeout must be finite and positive")
        if not isinstance(self.effect, ToolEffect) or not isinstance(
            self.retry_owner, RetryOwner
        ):
            raise DefinitionError(
                "tool effect and retry owner must use their public enums"
            )
        if self.effect is ToolEffect.MUTATION and self.mutation is None:
            raise DefinitionError("mutation tools require a mutation contract")
        if self.effect is not ToolEffect.MUTATION and self.mutation is not None:
            raise DefinitionError("only mutation tools may declare a mutation contract")
        for name, values in (
            ("required evidence", self.requires_evidence),
            ("produced evidence", self.produces_evidence),
            ("scope requirements", self.scope_requirements),
        ):
            if len(values) != len(set(values)) or any(
                type(value) is not str or not value for value in values
            ):
                raise DefinitionError(
                    f"tool {name} must contain unique non-empty names"
                )

        signature = inspect.signature(self.function)
        try:
            hints = get_type_hints(self.function, include_extras=True)
        except (NameError, TypeError) as error:
            raise UnsupportedTypeError(
                f"cannot resolve annotations for tool {self.id}"
            ) from error
        parameters = signature.parameters
        if self.mutation is not None and self.mutation.idempotency_parameter not in {
            None,
            *parameters,
        }:
            raise DefinitionError(
                "mutation idempotency parameter is not a tool parameter"
            )
        if (
            self.mutation is not None
            and self.mutation.idempotency_parameter is not None
            and hints[self.mutation.idempotency_parameter] is not str
        ):
            raise DefinitionError("mutation idempotency parameter must be a string")
        for parameter in parameters.values():
            if parameter.kind in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }:
                raise DefinitionError(
                    f"unsupported parameter {parameter.name} on tool {self.id}"
                )
            if parameter.name not in hints:
                raise UnsupportedTypeError(
                    f"missing annotation for {self.id}.{parameter.name}"
                )
            ensure_supported_type(hints[parameter.name], f"{self.id}.{parameter.name}")
        if "return" not in hints:
            raise UnsupportedTypeError(f"missing return annotation for tool {self.id}")
        ensure_supported_type(hints["return"], f"{self.id} return")

        if not isinstance(self.bindings, Mapping):
            raise BindingError(f"tool {self.id} bindings must be a mapping")
        binding_names = set(self.bindings)
        parameter_names = set(parameters)
        if binding_names != parameter_names:
            missing = sorted(parameter_names - binding_names)
            extra = sorted(binding_names - parameter_names)
            raise BindingError(
                f"tool {self.id} bindings mismatch; missing={missing}, extra={extra}"
            )
        for name, binding in self.bindings.items():
            if not isinstance(binding, _BINDING_TYPES):
                raise BindingError(f"{self.id}.{name} has an unsupported binding")
            parameter = parameters[name]
            annotation = hints[name]
            if isinstance(binding, DefaultBinding):
                if parameter.default is inspect.Parameter.empty:
                    raise BindingError(f"{self.id}.{name} has no default")
                validate_value(
                    annotation, parameter.default, f"{self.id}.{name} default"
                )
            elif isinstance(binding, ConstantBinding):
                validate_value(annotation, binding.value, f"{self.id}.{name} constant")
        for group in self.binding_groups:
            unknown = set(group.parameters) - parameter_names
            if unknown:
                raise BindingError(
                    f"tool {self.id} binding group references {sorted(unknown)}"
                )

        object.__setattr__(self, "bindings", MappingProxyType(dict(self.bindings)))
        object.__setattr__(self, "output_type", hints["return"])


@dataclass(frozen=True, slots=True)
class ChoiceOption:
    key: str
    description: str | None = None

    def __post_init__(self) -> None:
        _text(self.key, "choice key")
        if self.description is not None:
            _text(self.description, "choice description")


@dataclass(frozen=True, slots=True)
class ChoiceQuestion:
    instructions: str
    criteria: tuple[ChoiceOption, ...] = ()

    def __post_init__(self) -> None:
        _text(self.instructions, "choice instructions")
        keys = [option.key for option in self.criteria]
        if len(keys) == 1 or len(keys) != len(set(keys)):
            raise DefinitionError(
                "choice criteria must be empty for a candidate set or contain at least two unique keys"
            )


@dataclass(frozen=True, slots=True)
class NoulQuestion:
    instructions: str
    true_description: str | None = None
    false_description: str | None = None

    def __post_init__(self) -> None:
        _text(self.instructions, "Noul instructions")
        if self.true_description is not None:
            _text(self.true_description, "Noul true description")
        if self.false_description is not None:
            _text(self.false_description, "Noul false description")


@dataclass(frozen=True, slots=True)
class ScoreQuestion:
    instructions: str
    criteria: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.instructions, "Score instructions")
        if len(self.criteria) < 2 or any(
            type(value) is not str or not value.strip() for value in self.criteria
        ):
            raise DefinitionError(
                "Score criteria require at least two described levels"
            )


Question = ChoiceQuestion | NoulQuestion | ScoreQuestion


@dataclass(frozen=True, slots=True)
class Subject:
    name: str

    def __post_init__(self) -> None:
        _text(self.name, "subject name")


@dataclass(frozen=True, slots=True)
class EvidenceSelector:
    name: str

    def __post_init__(self) -> None:
        _text(self.name, "evidence selector")


@dataclass(frozen=True, slots=True)
class Judgment:
    id: str
    version: str
    primitive: Question
    subjects: tuple[Subject, ...]
    evidence: tuple[EvidenceSelector, ...] = ()
    dependencies: tuple[str, ...] = ()
    acceptance_policy: str | None = None
    applicability: str | None = None
    candidate_set: str | None = None

    def __post_init__(self) -> None:
        _text(self.id, "judgment id")
        _version(self.version)
        if not isinstance(
            self.primitive, (ChoiceQuestion, NoulQuestion, ScoreQuestion)
        ):
            raise DefinitionError("judgment primitive must be a public question type")
        if not self.subjects or any(
            not isinstance(value, Subject) for value in self.subjects
        ):
            raise DefinitionError("a judgment requires explicit subjects")
        if any(not isinstance(value, EvidenceSelector) for value in self.evidence):
            raise DefinitionError("judgment evidence must use EvidenceSelector")
        if len({value.name for value in self.evidence}) != len(self.evidence):
            raise DefinitionError("judgment evidence must be unique")
        if len(self.dependencies) != len(set(self.dependencies)):
            raise DefinitionError("judgment dependencies must be unique")
        if self.applicability is not None:
            _text(self.applicability, "judgment applicability")
        if self.candidate_set is not None:
            _text(self.candidate_set, "judgment candidate set")
            if not isinstance(self.primitive, ChoiceQuestion):
                raise DefinitionError("only Choice judgments may use a candidate set")
            if self.primitive.criteria:
                raise DefinitionError(
                    "a Choice judgment cannot mix fixed criteria with a candidate set"
                )
        elif isinstance(self.primitive, ChoiceQuestion) and not self.primitive.criteria:
            raise DefinitionError(
                "a Choice judgment needs fixed criteria or a candidate set"
            )


class Coverage(str, Enum):
    COMPLETE = "complete"
    TRUNCATED = "truncated"
    UNKNOWN = "unknown"
    FAILED = "failed"


NO_FIT_KEY = "__jev_frame_no_fit__"


class _FrozenList(list[Any]):
    def _immutable(self, *_: Any, **__: Any) -> None:
        raise TypeError("candidate snapshot values are immutable")

    __delitem__ = __iadd__ = __imul__ = __setitem__ = _immutable  # type: ignore[assignment]
    append = clear = extend = insert = pop = remove = reverse = sort = _immutable  # type: ignore[assignment]


class _FrozenDict(dict[str, Any]):
    def _immutable(self, *_: Any, **__: Any) -> None:
        raise TypeError("candidate snapshot values are immutable")

    __delitem__ = __ior__ = __setitem__ = _immutable  # type: ignore[assignment]
    clear = pop = popitem = setdefault = update = _immutable  # type: ignore[assignment]


def _freeze_candidate_value(value: Any) -> Any:
    if value is None or type(value) in {str, bool, int, float} or isinstance(value, Enum):
        return value
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise DefinitionError("candidate mappings require string keys")
        return _FrozenDict(
            {key: _freeze_candidate_value(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return _FrozenList(_freeze_candidate_value(item) for item in value)
    if isinstance(value, BaseModel):
        if not value.model_config.get("frozen", False):
            raise DefinitionError("candidate models must be frozen")
        return value.model_copy(
            deep=True,
            update={
                name: _freeze_candidate_value(getattr(value, name))
                for name in value.__class__.model_fields
            },
        )
    if is_dataclass(value) and not isinstance(value, type):
        parameters = cast(Any, value).__dataclass_params__
        if not parameters.frozen:
            raise DefinitionError("candidate dataclasses must be frozen")
        frozen = deepcopy(value)
        for item in fields(value):
            object.__setattr__(
                frozen, item.name, _freeze_candidate_value(getattr(value, item.name))
            )
        return frozen
    raise DefinitionError(
        f"unsupported candidate value type: {type(value).__name__}"
    )


@dataclass(frozen=True, slots=True)
class Candidate:
    key: str
    value: Any = field(repr=False)
    description: str
    source_id: str
    source_version: str | None = None

    def __post_init__(self) -> None:
        _text(self.key, "candidate key")
        _text(self.description, "candidate description")
        _text(self.source_id, "candidate source")
        object.__setattr__(self, "value", _freeze_candidate_value(self.value))


@dataclass(frozen=True, slots=True)
class CandidateSet:
    id: str
    version: str
    candidates: tuple[Candidate, ...]
    coverage: Coverage
    scope: str
    total_count: int | None = None
    query: str | None = None
    retrieval_parameters: Mapping[str, Any] = field(default_factory=dict)
    expansion_ref: str | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        _text(self.id, "candidate set id")
        _version(self.version)
        candidates = tuple(self.candidates)
        if any(not isinstance(candidate, Candidate) for candidate in candidates):
            raise DefinitionError("candidate snapshots require Candidate values")
        object.__setattr__(self, "candidates", candidates)
        if not isinstance(self.coverage, Coverage):
            raise DefinitionError("candidate coverage must use Coverage")
        _text(self.scope, "candidate scope")
        keys = [candidate.key for candidate in self.candidates]
        if len(keys) != len(set(keys)):
            raise DefinitionError("candidate keys must be unique")
        if NO_FIT_KEY in keys:
            raise DefinitionError("candidate key collides with the reserved no-fit key")
        if self.total_count is not None and (
            type(self.total_count) is not int or self.total_count < len(self.candidates)
        ):
            raise DefinitionError(
                "candidate total count cannot be smaller than the snapshot"
            )
        if self.coverage is Coverage.FAILED and not self.failure_reason:
            raise DefinitionError("failed retrieval requires a failure reason")
        if self.coverage is not Coverage.FAILED and self.failure_reason is not None:
            raise DefinitionError("only failed retrieval may include a failure reason")
        if self.query is not None:
            _text(self.query, "candidate query")
        if self.expansion_ref is not None:
            _text(self.expansion_ref, "candidate expansion reference")
        if not isinstance(self.retrieval_parameters, Mapping):
            raise DefinitionError("retrieval parameters must be a mapping")
        object.__setattr__(
            self,
            "retrieval_parameters",
            _freeze_candidate_value(self.retrieval_parameters),
        )


@dataclass(frozen=True, slots=True)
class CandidateProvider:
    id: str
    version: str
    function: Callable[..., CandidateSet] = field(repr=False, compare=False)
    bindings: Mapping[str, Binding] = field(default_factory=dict)
    blocking: bool = False

    def __post_init__(self) -> None:
        _text(self.id, "candidate provider id")
        _version(self.version)
        if not callable(self.function):
            raise DefinitionError("candidate provider must be callable")
        if type(self.blocking) is not bool or (
            self.blocking and inspect.iscoroutinefunction(self.function)
        ):
            raise DefinitionError(
                "candidate provider blocking must be a boolean and asynchronous providers cannot be blocking"
            )
        if not isinstance(self.bindings, Mapping):
            raise BindingError("candidate provider bindings must be a mapping")
        signature = inspect.signature(self.function)
        try:
            hints = get_type_hints(self.function, include_extras=True)
        except (NameError, TypeError) as error:
            raise UnsupportedTypeError(
                f"cannot resolve annotations for candidate provider {self.id}"
            ) from error
        parameters = signature.parameters
        if set(parameters) != set(self.bindings):
            raise BindingError(
                f"candidate provider {self.id} bindings must match its parameters"
            )
        for name, parameter in parameters.items():
            if parameter.kind in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }:
                raise DefinitionError(
                    f"unsupported parameter {name} on candidate provider {self.id}"
                )
            annotation = hints.get(name)
            if annotation is None:
                raise UnsupportedTypeError(
                    f"missing annotation for candidate provider {self.id}.{name}"
                )
            ensure_supported_type(annotation, f"candidate provider {self.id}.{name}")
            binding = self.bindings[name]
            if not isinstance(
                binding,
                (TaskInputBinding, HostContextBinding, ConstantBinding, DefaultBinding),
            ):
                raise BindingError(
                    f"candidate provider {self.id}.{name} has an unsupported binding"
                )
            if isinstance(binding, ConstantBinding):
                validate_value(annotation, binding.value, f"{self.id}.{name} constant")
            elif isinstance(binding, DefaultBinding):
                if parameter.default is inspect.Parameter.empty:
                    raise BindingError(f"{self.id}.{name} has no default")
                validate_value(
                    annotation, parameter.default, f"{self.id}.{name} default"
                )
        if hints.get("return") is not CandidateSet:
            raise UnsupportedTypeError(
                f"candidate provider {self.id} must return CandidateSet"
            )
        object.__setattr__(self, "bindings", MappingProxyType(dict(self.bindings)))


@dataclass(frozen=True, slots=True)
class CompletionContract:
    required_findings: tuple[str, ...]
    result_bindings: Mapping[str, str]
    acceptance_policy: str
    completed_negative_findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.required_findings or any(
            type(value) is not str or not value for value in self.required_findings
        ):
            raise DefinitionError("completion requires at least one finding")
        _text(self.acceptance_policy, "completion acceptance policy")
        if len(self.completed_negative_findings) != len(
            set(self.completed_negative_findings)
        ):
            raise DefinitionError("completed negative findings must be unique")
        if not isinstance(self.result_bindings, Mapping):
            raise DefinitionError("completion result bindings must be a mapping")
        if any(
            type(key) is not str or not key or type(value) is not str or not value
            for key, value in self.result_bindings.items()
        ):
            raise DefinitionError(
                "completion result bindings require string names and references"
            )
        object.__setattr__(
            self, "result_bindings", MappingProxyType(dict(self.result_bindings))
        )


@dataclass(frozen=True, slots=True)
class CapabilityPackage:
    id: str
    version: str
    tools: tuple[Tool, ...] = ()
    judgments: tuple[Judgment, ...] = ()
    candidate_providers: tuple[CandidateProvider, ...] = ()

    def __post_init__(self) -> None:
        _text(self.id, "capability package id")
        _version(self.version)
        _unique_ids(self.tools, self.judgments, self.candidate_providers)


def _unique_ids(*groups: tuple[Any, ...]) -> None:
    identifiers = [item.id for group in groups for item in group]
    duplicates = sorted(
        {identifier for identifier in identifiers if identifiers.count(identifier) > 1}
    )
    if duplicates:
        raise DefinitionError(f"conflicting identifiers: {duplicates}")


@dataclass(frozen=True, slots=True)
class OperatingPolicy:
    version: str
    acceptance_policies: tuple[str, ...]

    def __post_init__(self) -> None:
        _version(self.version)
        if len(self.acceptance_policies) != len(set(self.acceptance_policies)):
            raise DefinitionError("acceptance policy identifiers must be unique")


InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


@dataclass(frozen=True, slots=True)
class AgentDefinition(Generic[InputT, OutputT]):
    id: str
    version: str
    objective: str
    input_type: Any
    output_type: Any
    completion: CompletionContract
    policy: OperatingPolicy
    tools: tuple[Tool, ...] = ()
    judgments: tuple[Judgment, ...] = ()
    candidate_providers: tuple[CandidateProvider, ...] = ()
    packages: tuple[CapabilityPackage, ...] = ()

    def __post_init__(self) -> None:
        _text(self.id, "agent id")
        _version(self.version)
        _text(self.objective, "agent objective")
        ensure_supported_type(self.input_type, "agent input")
        ensure_supported_type(self.output_type, "agent output")
        package_tools = tuple(
            tool for package in self.packages for tool in package.tools
        )
        package_judgments = tuple(
            judgment for package in self.packages for judgment in package.judgments
        )
        package_providers = tuple(
            provider
            for package in self.packages
            for provider in package.candidate_providers
        )
        all_tools = self.tools + package_tools
        all_judgments = self.judgments + package_judgments
        all_providers = self.candidate_providers + package_providers
        _unique_ids(all_tools, all_judgments, all_providers, self.packages)

        policy_ids = set(self.policy.acceptance_policies)
        if self.completion.acceptance_policy not in policy_ids:
            raise DefinitionError(
                "completion references an unregistered acceptance policy"
            )
        judgment_ids = {judgment.id for judgment in all_judgments}
        capability_ids = {tool.id for tool in all_tools}
        for judgment in all_judgments:
            missing_dependencies = set(judgment.dependencies) - judgment_ids
            if missing_dependencies:
                raise DefinitionError(
                    f"judgment {judgment.id} references missing dependencies {sorted(missing_dependencies)}"
                )
            if (
                judgment.acceptance_policy is not None
                and judgment.acceptance_policy not in policy_ids
            ):
                raise DefinitionError(
                    f"judgment {judgment.id} references an unregistered policy"
                )
        for tool in all_tools:
            for binding in tool.bindings.values():
                if (
                    isinstance(binding, JudgmentBinding)
                    and binding.judgment not in judgment_ids
                ):
                    raise BindingError(
                        f"tool {tool.id} references unknown judgment {binding.judgment}"
                    )
                if (
                    isinstance(binding, GeneratedBinding)
                    and binding.capability not in capability_ids
                ):
                    raise BindingError(
                        f"tool {tool.id} references unknown capability {binding.capability}"
                    )


@dataclass(frozen=True, slots=True)
class RunLimits:
    provider_attempts: int
    submitted_questions: int
    tool_attempts: int
    investigation_steps: int
    concurrent_operations: int
    writes: int
    planner_calls: int
    plan_revisions: int
    child_depth: int
    child_runs: int

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if type(value) is not int or value < 0:
                raise DefinitionError(f"{item.name} must be a nonnegative integer")
        if self.concurrent_operations == 0 and any(
            getattr(self, name) > 0
            for name in (
                "provider_attempts",
                "tool_attempts",
                "planner_calls",
                "child_runs",
            )
        ):
            raise DefinitionError(
                "concurrent_operations cannot be zero when operations are enabled"
            )


@dataclass(frozen=True, slots=True)
class RunContext:
    scope: str
    deadline: float
    limits: RunLimits
    host_dependencies: Mapping[str, Any] = field(
        default_factory=dict, repr=False, compare=False
    )
    authority_context: Any = field(default=None, repr=False, compare=False)
    clock: Callable[[], float] = field(
        default=time.monotonic, repr=False, compare=False
    )
    event_sink: Callable[[Mapping[str, Any]], None] | None = field(
        default=None, repr=False, compare=False
    )
    evidence_session: Any = field(default=None, repr=False, compare=False)
    run_id: str | None = None
    correlation_id: str | None = None
    parent_operation_id: str | None = None
    definition_ancestry: tuple[str, ...] = ()
    child_depth: int = 0

    def __post_init__(self) -> None:
        _text(self.scope, "run scope")
        if (
            type(self.deadline) not in {int, float}
            or not math.isfinite(self.deadline)
            or self.deadline <= 0
        ):
            raise DefinitionError("deadline must be finite and positive")
        if not isinstance(self.host_dependencies, Mapping):
            raise DefinitionError("host dependencies must be a mapping")
        if not callable(self.clock):
            raise DefinitionError("run clock must be callable")
        if self.event_sink is not None and not callable(self.event_sink):
            raise DefinitionError("event sink must be callable")
        for value, name in (
            (self.run_id, "run id"),
            (self.correlation_id, "correlation id"),
            (self.parent_operation_id, "parent operation id"),
        ):
            if value is not None:
                _text(value, name)
        if len(self.definition_ancestry) != len(set(self.definition_ancestry)) or any(
            type(value) is not str or not value for value in self.definition_ancestry
        ):
            raise DefinitionError(
                "definition ancestry must contain unique non-empty identifiers"
            )
        if type(self.child_depth) is not int or self.child_depth < 0:
            raise DefinitionError("child depth must be a nonnegative integer")
        object.__setattr__(
            self, "host_dependencies", MappingProxyType(dict(self.host_dependencies))
        )


DecisionContext = RunContext


class UsageCoverage(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Usage:
    coverage: UsageCoverage = UsageCoverage.UNKNOWN
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_attempts: int = 0
    submitted_questions: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.coverage, UsageCoverage):
            raise DefinitionError("usage coverage must use UsageCoverage")
        for name in ("input_tokens", "output_tokens"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise DefinitionError(f"{name} must be unknown or nonnegative")
        for name in ("provider_attempts", "submitted_questions"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise DefinitionError(f"{name} must be nonnegative")
        if self.coverage is UsageCoverage.COMPLETE and (
            self.input_tokens is None or self.output_tokens is None
        ):
            raise DefinitionError("complete usage requires token counts")


@dataclass(frozen=True, slots=True)
class ChoiceAnswer:
    choice: str
    probabilities: Mapping[str, float]
    confidence: float


@dataclass(frozen=True, slots=True)
class NoulAnswer:
    probability_yes: float


@dataclass(frozen=True, slots=True)
class ScoreAnswer:
    score: float
    legend: tuple[str, ...]
    probabilities: tuple[float, ...]
    confidence: float


PrimitiveAnswer = ChoiceAnswer | NoulAnswer | ScoreAnswer


class AcceptanceStatus(str, Enum):
    ACCEPT = "accept"
    INVESTIGATE = "investigate"
    REJECT = "reject"
    HANDOFF = "handoff"
    UNASSESSED = "unassessed"


@dataclass(frozen=True, slots=True)
class AcceptanceRecord:
    policy_id: str
    policy_version: str
    status: AcceptanceStatus
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.policy_id, "acceptance policy id")
        _version(self.policy_version, "acceptance policy version")
        if not isinstance(self.status, AcceptanceStatus):
            raise DefinitionError("acceptance status must use AcceptanceStatus")


@dataclass(frozen=True, slots=True)
class DecisionResult:
    answer: PrimitiveAnswer
    subjects: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    input_fingerprint: str
    requested_model: str
    returned_model: str | None
    usage: Usage = field(default_factory=Usage)
    acceptance: AcceptanceRecord | None = None


class TerminalStatus(str, Enum):
    COMPLETED = "completed"
    UNRESOLVED = "unresolved"
    FAILED = "failed"
    CANCELLED = "cancelled"


class UnresolvedReason(str, Enum):
    MISSING_EVIDENCE = "missing_evidence"
    SOURCE_CONFLICT = "source_conflict"
    INCOMPLETE_COVERAGE = "incomplete_coverage"
    REFUTED_CLAIM = "refuted_claim"
    SEMANTIC_AMBIGUITY = "semantic_ambiguity"
    MISSING_CAPABILITY = "missing_capability"
    UNACCEPTED_JUDGMENT = "unaccepted_judgment"
    PERMISSION_DENIAL = "permission_denial"
    STALE_SOURCE = "stale_source"
    UNKNOWN_WRITE_OUTCOME = "unknown_write_outcome"
    BUDGET_EXHAUSTION = "budget_exhaustion"
    NO_PROGRESS = "no_progress"


@dataclass(frozen=True, slots=True)
class Unresolved:
    reason: UnresolvedReason
    subjects: tuple[str, ...]
    detail: str
    attempted_actions: tuple[str, ...] = ()
    needed: str | None = None


@dataclass(frozen=True, slots=True)
class ClarificationRequest:
    id: str
    subjects: tuple[str, ...]
    missing_path: tuple[str | int, ...]
    answer_type: Any = field(repr=False, compare=False)
    prompt: str
    definition_id: str | None = None

    def __post_init__(self) -> None:
        _text(self.id, "clarification id")
        if not self.subjects or any(
            type(subject) is not str or not subject for subject in self.subjects
        ):
            raise DefinitionError("clarification subjects must be non-empty strings")
        if not self.missing_path or any(
            type(part) not in {str, int} or part == "" for part in self.missing_path
        ):
            raise DefinitionError("clarification path must be non-empty")
        ensure_supported_type(self.answer_type, f"clarification {self.id} answer")
        _text(self.prompt, "clarification prompt")
        if self.definition_id is not None:
            _text(self.definition_id, "clarification definition id")

    def validate_answer(self, value: Any) -> Any:
        return validate_value(
            self.answer_type, value, f"clarification {self.id} answer"
        )


ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class RunResult(Generic[ResultT]):
    status: TerminalStatus
    value: ResultT | _Missing = MISSING
    partial_findings: tuple[Any, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    unresolved: tuple[Unresolved, ...] = ()
    clarifications: tuple[ClarificationRequest, ...] = ()
    trace: tuple[Mapping[str, Any], ...] = ()
    usage: Usage = field(default_factory=Usage)
    failure: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, TerminalStatus):
            raise DefinitionError("run status must use TerminalStatus")
        if self.status is TerminalStatus.COMPLETED and self.value is MISSING:
            raise DefinitionError("a completed result requires a value")
        if self.status is not TerminalStatus.COMPLETED and self.value is not MISSING:
            raise DefinitionError("only a completed result may contain a value")
        if self.status is TerminalStatus.UNRESOLVED and not self.unresolved:
            raise DefinitionError("an unresolved result requires a reason")
