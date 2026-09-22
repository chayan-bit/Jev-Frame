from __future__ import annotations

import inspect
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import Any, TypeVar

from pydantic import TypeAdapter, ValidationError

from .compiler import CompiledQuestion
from .definitions import (
    ChoiceAnswer,
    InputValidationError,
    NoulAnswer,
    PrimitiveAnswer,
    ProviderError,
    RunLimits,
    ScoreAnswer,
    Tool,
    ToolEffect,
    Usage,
)
from .inspection import JevEvent
from .provider import AttemptAdmission, AttemptStatus, ProviderAttempt, ProviderBatch
from .state import StableSerializationError, canonical_digest, canonical_json

FIXTURE_SCHEMA_VERSION = "jev-frame.regression-fixture.v1"
_PUBLIC_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}").fullmatch


class FixtureError(InputValidationError):
    pass


class IncompleteFixtureError(FixtureError):
    pass


class UnexpectedFixtureCall(FixtureError):
    pass


class FixtureInputMismatch(FixtureError):
    pass


class FixtureCallKind(str, Enum):
    PROVIDER = "provider"
    TOOL = "tool"


class FixtureOutcome(str, Enum):
    RETURNED = "returned"
    FAILED = "failed"


class FixtureGapKind(str, Enum):
    REDACTED = "redacted"
    UNAVAILABLE = "unavailable"


def _identifier(value: str, name: str) -> None:
    if type(value) is not str or _PUBLIC_ID(value) is None:
        raise FixtureError(f"{name} must be a public identifier")


def _json_value(value: Any) -> Any:
    try:
        return json.loads(canonical_json(value))
    except StableSerializationError as error:
        raise FixtureError("fixture value is not safely serializable") from error


@dataclass(frozen=True, slots=True)
class FixtureGap:
    path: str
    kind: FixtureGapKind
    reason: str
    material: bool = False

    def __post_init__(self) -> None:
        _identifier(self.path, "fixture gap path")
        _identifier(self.reason, "fixture gap reason")
        if not isinstance(self.kind, FixtureGapKind) or type(self.material) is not bool:
            raise FixtureError("fixture gap kind and material flag are invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind.value,
            "reason": self.reason,
            "material": self.material,
        }


@dataclass(frozen=True, slots=True)
class FixtureSource:
    alias: str
    source_id: str
    source_version: str | None
    snapshot: Any = None
    retained: bool = False

    def __post_init__(self) -> None:
        _identifier(self.alias, "source alias")
        _identifier(self.source_id, "source id")
        if self.source_version is not None:
            _identifier(self.source_version, "source version")
        if type(self.retained) is not bool:
            raise FixtureError("source retained flag must be a boolean")
        object.__setattr__(
            self,
            "snapshot",
            _json_value(self.snapshot) if self.retained else None,
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "alias": self.alias,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "retained": self.retained,
        }
        if self.retained:
            result["snapshot"] = self.snapshot
        return result


@dataclass(frozen=True, slots=True)
class FixtureCall:
    alias: str
    kind: FixtureCallKind
    target_id: str
    target_version: str
    operation_id: str
    argument_fingerprint: str
    outcome: FixtureOutcome
    response: Any = None
    error_code: str | None = None
    effect: ToolEffect | None = None
    source_aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.alias, "call alias"),
            (self.target_id, "call target"),
            (self.target_version, "call target version"),
            (self.operation_id, "call operation id"),
            (self.argument_fingerprint, "call argument fingerprint"),
        ):
            _identifier(value, name)
        if not isinstance(self.kind, FixtureCallKind) or not isinstance(
            self.outcome, FixtureOutcome
        ):
            raise FixtureError("fixture call kind and outcome are invalid")
        if self.kind is FixtureCallKind.TOOL:
            if not isinstance(self.effect, ToolEffect):
                raise FixtureError("tool calls require an effect declaration")
        elif self.effect is not None:
            raise FixtureError("provider calls cannot declare a tool effect")
        if self.outcome is FixtureOutcome.FAILED:
            if self.error_code is None:
                raise FixtureError("failed calls require a public error code")
            _identifier(self.error_code, "call error code")
            if self.response is not None:
                raise FixtureError("failed calls cannot contain a response")
        elif self.error_code is not None:
            raise FixtureError("returned calls cannot contain an error code")
        if len(self.source_aliases) != len(set(self.source_aliases)):
            raise FixtureError("call source aliases must be unique")
        for alias in self.source_aliases:
            _identifier(alias, "call source alias")
        object.__setattr__(self, "response", _json_value(self.response))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "alias": self.alias,
            "kind": self.kind.value,
            "target_id": self.target_id,
            "target_version": self.target_version,
            "operation_id": self.operation_id,
            "argument_fingerprint": self.argument_fingerprint,
            "outcome": self.outcome.value,
            "source_aliases": list(self.source_aliases),
        }
        if self.outcome is FixtureOutcome.RETURNED:
            result["response"] = self.response
        else:
            result["error_code"] = self.error_code
        if self.effect is not None:
            result["effect"] = self.effect.value
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> FixtureCall:
        try:
            return cls(
                alias=value["alias"],
                kind=FixtureCallKind(value["kind"]),
                target_id=value["target_id"],
                target_version=value["target_version"],
                operation_id=value["operation_id"],
                argument_fingerprint=value["argument_fingerprint"],
                outcome=FixtureOutcome(value["outcome"]),
                response=value.get("response"),
                error_code=value.get("error_code"),
                effect=(
                    None
                    if value.get("effect") is None
                    else ToolEffect(value["effect"])
                ),
                source_aliases=tuple(value.get("source_aliases", ())),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise FixtureError("fixture call fields are invalid") from error


@dataclass(frozen=True, slots=True)
class CaptureAllowlist:
    event_sequences: frozenset[int] = frozenset()
    call_aliases: frozenset[str] = frozenset()
    source_aliases: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 1 for value in self.event_sequences):
            raise FixtureError("allowlisted event sequences must be positive integers")
        for values, name in (
            (self.call_aliases, "call alias"),
            (self.source_aliases, "source alias"),
        ):
            for value in values:
                _identifier(value, name)


@dataclass(frozen=True, slots=True)
class RegressionFixture:
    id: str
    run_id: str
    events: tuple[Mapping[str, Any], ...]
    calls: tuple[FixtureCall, ...]
    sources: tuple[FixtureSource, ...]
    required_source_aliases: tuple[str, ...] = ()
    gaps: tuple[FixtureGap, ...] = ()
    schema_version: str = FIXTURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != FIXTURE_SCHEMA_VERSION:
            raise FixtureError("unsupported fixture schema version")
        _identifier(self.id, "fixture id")
        _identifier(self.run_id, "fixture run id")
        if len({call.alias for call in self.calls}) != len(self.calls):
            raise FixtureError("fixture call aliases must be unique")
        if len({source.alias for source in self.sources}) != len(self.sources):
            raise FixtureError("fixture source aliases must be unique")
        if len(self.required_source_aliases) != len(set(self.required_source_aliases)):
            raise FixtureError("required source aliases must be unique")
        source_aliases = {source.alias for source in self.sources}
        for alias in self.required_source_aliases:
            _identifier(alias, "required source alias")
        unknown = {
            alias for call in self.calls for alias in call.source_aliases
        } - source_aliases
        if unknown:
            raise FixtureError("fixture calls reference unknown source aliases")
        object.__setattr__(
            self,
            "events",
            tuple(MappingProxyType(_json_value(event)) for event in self.events),
        )

    @property
    def complete(self) -> bool:
        sources = {source.alias: source for source in self.sources}
        required = set(self.required_source_aliases)
        required.update(alias for call in self.calls for alias in call.source_aliases)
        return not any(gap.material for gap in self.gaps) and all(
            alias in sources and sources[alias].retained for alias in required
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "run_id": self.run_id,
            "complete": self.complete,
            "events": [dict(event) for event in self.events],
            "calls": [call.to_dict() for call in self.calls],
            "sources": [source.to_dict() for source in self.sources],
            "required_source_aliases": list(self.required_source_aliases),
            "gaps": [gap.to_dict() for gap in self.gaps],
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RegressionFixture:
        if value.get("schema_version") != FIXTURE_SCHEMA_VERSION:
            raise FixtureError("unsupported fixture schema version")
        try:
            sources = tuple(
                FixtureSource(
                    alias=item["alias"],
                    source_id=item["source_id"],
                    source_version=item.get("source_version"),
                    snapshot=item.get("snapshot"),
                    retained=item["retained"],
                )
                for item in value.get("sources", ())
            )
            gaps = tuple(
                FixtureGap(
                    item["path"],
                    FixtureGapKind(item["kind"]),
                    item["reason"],
                    item["material"],
                )
                for item in value.get("gaps", ())
            )
            return cls(
                id=value["id"],
                run_id=value["run_id"],
                events=tuple(value.get("events", ())),
                calls=tuple(
                    FixtureCall.from_dict(item) for item in value.get("calls", ())
                ),
                sources=sources,
                required_source_aliases=tuple(
                    value.get("required_source_aliases", ())
                ),
                gaps=gaps,
                schema_version=value["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise FixtureError("fixture fields are invalid") from error

    @classmethod
    def from_json(cls, value: str) -> RegressionFixture:
        try:
            payload = json.loads(value)
        except (TypeError, json.JSONDecodeError) as error:
            raise FixtureError("fixture JSON is invalid") from error
        if not isinstance(payload, Mapping):
            raise FixtureError("fixture JSON must contain an object")
        return cls.from_dict(payload)


@dataclass(frozen=True, slots=True)
class EvaluatorAnnotations:
    fixture_id: str
    expected_outcome: Any
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.fixture_id, "annotation fixture id")
        object.__setattr__(self, "expected_outcome", _json_value(self.expected_outcome))
        if any(type(note) is not str or not note for note in self.notes):
            raise FixtureError("evaluator notes must be non-empty strings")


def capture_fixture(
    *,
    fixture_id: str,
    run_id: str,
    events: Sequence[JevEvent] = (),
    calls: Sequence[FixtureCall] = (),
    sources: Sequence[FixtureSource] = (),
    allowlist: CaptureAllowlist,
    required_source_aliases: Sequence[str] = (),
    gaps: Sequence[FixtureGap] = (),
) -> RegressionFixture:
    """Capture only explicitly named public records; arbitrary run state is not accepted."""

    return RegressionFixture(
        fixture_id,
        run_id,
        tuple(
            event.to_dict()
            for event in events
            if event.run_id == run_id and event.sequence in allowlist.event_sequences
        ),
        tuple(call for call in calls if call.alias in allowlist.call_aliases),
        tuple(source for source in sources if source.alias in allowlist.source_aliases),
        tuple(required_source_aliases),
        tuple(gaps),
    )


def _answer_data(answer: PrimitiveAnswer) -> dict[str, Any]:
    return _json_value(answer)


def _provider_response(batch: ProviderBatch) -> dict[str, Any]:
    return {
        "answers": {key: _answer_data(answer) for key, answer in batch.answers.items()},
        "requested_model": batch.requested_model,
        "returned_model": batch.returned_model,
        "request_id": batch.request_id,
        "usage": _json_value(batch.usage),
        "attempts": [_json_value(attempt) for attempt in batch.attempts],
    }


def _provider_fingerprint(
    *,
    state: Any,
    questions: Sequence[CompiledQuestion],
    requested_model: str,
    operation_id: str,
) -> str:
    return canonical_digest(
        {
            "state": state,
            "questions": tuple(questions),
            "requested_model": requested_model,
            "operation_id": operation_id,
        }
    )


def provider_fixture_call(
    alias: str,
    *,
    state: Any,
    questions: Sequence[CompiledQuestion],
    requested_model: str,
    operation_id: str,
    batch: ProviderBatch | None = None,
    error_code: str | None = None,
    source_aliases: Sequence[str] = (),
) -> FixtureCall:
    if (batch is None) == (error_code is None):
        raise FixtureError("provider call requires exactly one result or error code")
    return FixtureCall(
        alias,
        FixtureCallKind.PROVIDER,
        questions[0].judgment_id if questions else "provider",
        requested_model,
        operation_id,
        _provider_fingerprint(
            state=state,
            questions=questions,
            requested_model=requested_model,
            operation_id=operation_id,
        ),
        FixtureOutcome.RETURNED if batch is not None else FixtureOutcome.FAILED,
        None if batch is None else _provider_response(batch),
        error_code,
        source_aliases=tuple(source_aliases),
    )


def tool_fixture_call(
    alias: str,
    tool: Tool,
    arguments: Mapping[str, Any],
    *,
    operation_id: str,
    scripted_result: Any = None,
    error_code: str | None = None,
    source_aliases: Sequence[str] = (),
) -> FixtureCall:
    if error_code is not None and scripted_result is not None:
        raise FixtureError("failed tool calls cannot contain a scripted result")
    return FixtureCall(
        alias,
        FixtureCallKind.TOOL,
        tool.id,
        tool.version,
        operation_id,
        canonical_digest(
            {
                "tool_id": tool.id,
                "tool_version": tool.version,
                "arguments": arguments,
            }
        ),
        FixtureOutcome.FAILED if error_code is not None else FixtureOutcome.RETURNED,
        scripted_result,
        error_code,
        tool.effect,
        tuple(source_aliases),
    )


class ReplayProvider:
    def __init__(self, replay: OfflineReplay) -> None:
        self._replay = replay

    async def evaluate(
        self,
        *,
        state: Any,
        questions: Sequence[CompiledQuestion],
        requested_model: str,
        operation_id: str,
        timeout: float | None = None,
        admit_attempt: AttemptAdmission | None = None,
    ) -> ProviderBatch:
        del timeout
        call = self._replay._next(FixtureCallKind.PROVIDER, operation_id)
        fingerprint = _provider_fingerprint(
            state=state,
            questions=questions,
            requested_model=requested_model,
            operation_id=operation_id,
        )
        if fingerprint != call.argument_fingerprint:
            raise FixtureInputMismatch("provider inputs differ from the fixture")
        if call.outcome is FixtureOutcome.FAILED:
            raise ProviderError(f"recorded provider failure ({call.error_code})")
        response = call.response
        assert isinstance(response, Mapping)
        attempts = tuple(
            ProviderAttempt(
                item["id"],
                item["number"],
                AttemptStatus(item["status"]),
                item.get("code"),
                item.get("request_id"),
            )
            for item in response["attempts"]
        )
        if admit_attempt is not None:
            for attempt in attempts:
                admitted = admit_attempt(
                    ProviderAttempt(attempt.id, attempt.number, AttemptStatus.STARTED)
                )
                if inspect.isawaitable(admitted):
                    await admitted
        answers: dict[str, PrimitiveAnswer] = {}
        for key, value in response["answers"].items():
            if set(value) == {"choice", "probabilities", "confidence"}:
                answers[key] = ChoiceAnswer(
                    value["choice"], value["probabilities"], value["confidence"]
                )
            elif set(value) == {"probability_yes"}:
                answers[key] = NoulAnswer(value["probability_yes"])
            else:
                answers[key] = ScoreAnswer(
                    value["score"],
                    tuple(value["legend"]),
                    tuple(value["probabilities"]),
                    value["confidence"],
                )
        usage = TypeAdapter(Usage).validate_python(response["usage"])
        return ProviderBatch(
            answers,
            response["requested_model"],
            response["returned_model"],
            response["request_id"],
            usage,
            attempts,
        )


class _ReplayToolFunction:
    def __init__(self, replay: OfflineReplay, tool: Tool) -> None:
        self._replay = replay
        self._tool = tool
        self.__signature__ = inspect.signature(tool.function)
        self.__annotations__ = inspect.get_annotations(tool.function, eval_str=True)

    def __call__(self, **arguments: Any) -> Awaitable[Any]:
        return self._invoke(arguments)

    async def _invoke(self, arguments: Mapping[str, Any]) -> Any:
        tool = self._tool
        if not self._replay._remaining:
            raise UnexpectedFixtureCall("fixture contains no remaining call")
        expected = self._replay._remaining[0]
        call = self._replay._next(FixtureCallKind.TOOL, expected.operation_id)
        if call.target_id != tool.id:
            raise UnexpectedFixtureCall("tool identity differs from the fixture")
        fingerprint = canonical_digest(
            {
                "tool_id": tool.id,
                "tool_version": tool.version,
                "arguments": arguments,
            }
        )
        if fingerprint != call.argument_fingerprint:
            raise FixtureInputMismatch("tool arguments differ from the fixture")
        if (
            tool.mutation is not None
            and tool.mutation.idempotency_parameter
            and arguments[tool.mutation.idempotency_parameter] != call.operation_id
        ):
            raise FixtureInputMismatch(
                "mutation operation identity differs from the fixture"
            )
        if call.outcome is FixtureOutcome.FAILED:
            raise FixtureError(f"recorded tool failure ({call.error_code})")
        try:
            return TypeAdapter(tool.output_type).validate_python(call.response)
        except ValidationError as error:
            raise FixtureError("scripted tool result has the wrong type") from error


class OfflineReplay:
    """One-shot strict replay that owns only fixture-backed doubles."""

    def __init__(self, fixture: RegressionFixture) -> None:
        if not fixture.complete:
            raise IncompleteFixtureError(
                "fixture is incomplete because required evidence was omitted"
            )
        self.fixture = fixture
        self._remaining = list(fixture.calls)
        self.provider = ReplayProvider(self)

    def _next(self, kind: FixtureCallKind, operation_id: str) -> FixtureCall:
        if not self._remaining:
            raise UnexpectedFixtureCall("fixture contains no remaining call")
        call = self._remaining[0]
        if call.kind is not kind or call.operation_id != operation_id:
            raise UnexpectedFixtureCall("call identity differs from the fixture")
        return self._remaining.pop(0)

    @property
    def remaining_calls(self) -> tuple[str, ...]:
        return tuple(call.alias for call in self._remaining)

    def finish(self) -> None:
        if self._remaining:
            raise UnexpectedFixtureCall("fixture calls were not fully consumed")

    def tool_double(self, tool: Tool) -> Tool:
        matching = [
            call
            for call in self._remaining
            if call.kind is FixtureCallKind.TOOL and call.target_id == tool.id
        ]
        if not matching or any(
            call.target_version != tool.version or call.effect is not tool.effect
            for call in matching
        ):
            raise UnexpectedFixtureCall("no compatible tool call is registered")
        return replace(
            tool,
            function=_ReplayToolFunction(self, tool),
            blocking=False,
        )


@dataclass(frozen=True, slots=True)
class FindingDifference:
    key: str
    recorded: Any
    replayed: Any


def compare_findings(
    recorded: Mapping[str, Any], replayed: Mapping[str, Any]
) -> tuple[FindingDifference, ...]:
    return tuple(
        FindingDifference(key, recorded.get(key), replayed.get(key))
        for key in sorted(set(recorded) | set(replayed))
        if canonical_json(recorded.get(key)) != canonical_json(replayed.get(key))
    )


@dataclass(frozen=True, slots=True)
class ReevaluationRequest:
    fixture: RegressionFixture
    model: str
    policy_version: str
    limits: RunLimits

    def __post_init__(self) -> None:
        _identifier(self.model, "reevaluation model")
        _identifier(self.policy_version, "reevaluation policy version")


ReevaluationT = TypeVar("ReevaluationT")


async def reevaluate_fixture(
    fixture: RegressionFixture,
    *,
    model: str,
    policy_version: str,
    limits: RunLimits,
    operation: Callable[
        [ReevaluationRequest], ReevaluationT | Awaitable[ReevaluationT]
    ],
) -> ReevaluationT:
    """Run an explicitly supplied fresh operation; offline replay never calls this."""

    request = ReevaluationRequest(fixture, model, policy_version, limits)
    result = operation(request)
    return await result if inspect.isawaitable(result) else result
