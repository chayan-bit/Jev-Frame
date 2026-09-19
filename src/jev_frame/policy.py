from __future__ import annotations

import inspect
import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol

from .definitions import (
    AcceptanceRecord,
    AcceptanceStatus,
    JevFrameError,
    PrimitiveAnswer,
    ToolEffect,
)
from .state import Evidence, ExecutionState, canonical_digest


class PolicyError(JevFrameError):
    pass


class EffectNotStartedError(JevFrameError):
    """A trusted adapter established that dispatch did not reach the effect."""


@dataclass(frozen=True, slots=True)
class PolicyInput:
    answer: PrimitiveAnswer
    evidence: tuple[Evidence, ...] = ()
    candidate_coverage: str | None = None


PolicyEvaluator = Callable[
    [PolicyInput],
    AcceptanceRecord
    | AcceptanceStatus
    | Awaitable[AcceptanceRecord | AcceptanceStatus],
]


@dataclass(frozen=True, slots=True)
class AcceptancePolicy:
    id: str
    version: str
    evaluator: PolicyEvaluator = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.id) is not str or not self.id:
            raise PolicyError("acceptance policy id must be a non-empty string")
        if type(self.version) is not str or not self.version:
            raise PolicyError("acceptance policy version must be a non-empty string")
        if not callable(self.evaluator):
            raise PolicyError("acceptance policy evaluator must be callable")

    async def evaluate(self, value: PolicyInput) -> AcceptanceRecord:
        result = self.evaluator(value)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, AcceptanceStatus):
            return AcceptanceRecord(self.id, self.version, result)
        if not isinstance(result, AcceptanceRecord):
            raise PolicyError("acceptance policy returned an invalid result")
        if result.policy_id != self.id or result.policy_version != self.version:
            raise PolicyError("acceptance policy returned mismatched identity")
        return result


@dataclass(frozen=True, slots=True)
class ActionProposal:
    operation_id: str
    tool_id: str
    tool_version: str
    arguments: Mapping[str, Any]
    scope: str
    source_versions: Mapping[str, str | None]
    effect: ToolEffect = ToolEffect.MUTATION
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        for value, name in (
            (self.operation_id, "operation id"),
            (self.tool_id, "tool id"),
            (self.tool_version, "tool version"),
            (self.scope, "scope"),
        ):
            if type(value) is not str or not value:
                raise PolicyError(f"{name} must be a non-empty string")
        if (
            not isinstance(self.effect, ToolEffect)
            or self.effect is not ToolEffect.MUTATION
        ):
            raise PolicyError("guarded actions must declare the mutation effect")
        if not isinstance(self.arguments, Mapping) or not isinstance(
            self.source_versions, Mapping
        ):
            raise PolicyError("action arguments and source versions must be mappings")
        arguments = dict(self.arguments)
        source_versions = dict(self.source_versions)
        try:
            digest = canonical_digest(
                {
                    "tool_id": self.tool_id,
                    "tool_version": self.tool_version,
                    "arguments": arguments,
                    "scope": self.scope,
                    "source_versions": source_versions,
                    "effect": self.effect.value,
                }
            )
        except Exception as error:
            raise PolicyError("action is not stably serializable") from error
        object.__setattr__(self, "arguments", MappingProxyType(arguments))
        object.__setattr__(self, "source_versions", MappingProxyType(source_versions))
        object.__setattr__(self, "digest", digest)


@dataclass(frozen=True, slots=True)
class AuthorizationRecord:
    action_digest: str
    scope: str
    authorized: bool
    expires_at: float
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.action_digest) is not str or not self.action_digest:
            raise PolicyError("authorization action digest must be non-empty")
        if type(self.scope) is not str or not self.scope:
            raise PolicyError("authorization scope must be non-empty")
        if type(self.authorized) is not bool:
            raise PolicyError("authorization decision must be boolean")
        if type(self.expires_at) not in {int, float} or not math.isfinite(
            self.expires_at
        ):
            raise PolicyError("authorization expiry must be finite")
        if any(type(reason) is not str or not reason for reason in self.reasons):
            raise PolicyError("authorization reasons must be non-empty strings")

    def permits(self, proposal: ActionProposal, now: float) -> bool:
        return (
            self.authorized
            and self.action_digest == proposal.digest
            and self.scope == proposal.scope
            and now < self.expires_at
        )


class Authorizer(Protocol):
    def authorize(
        self, proposal: ActionProposal, authority_context: Any
    ) -> AuthorizationRecord | Awaitable[AuthorizationRecord]: ...


CheckpointEvaluator = Callable[
    [ActionProposal],
    AcceptanceRecord
    | AcceptanceStatus
    | Awaitable[AcceptanceRecord | AcceptanceStatus],
]


@dataclass(frozen=True, slots=True)
class CheckpointRecord:
    checkpoint_id: str
    checkpoint_version: str
    action_digest: str
    status: AcceptanceStatus
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.checkpoint_id, "checkpoint id"),
            (self.checkpoint_version, "checkpoint version"),
            (self.action_digest, "checkpoint action digest"),
        ):
            if type(value) is not str or not value:
                raise PolicyError(f"{name} must be a non-empty string")
        if not isinstance(self.status, AcceptanceStatus):
            raise PolicyError("checkpoint status must use AcceptanceStatus")

    def accepts(self, proposal: ActionProposal) -> bool:
        return (
            self.status is AcceptanceStatus.ACCEPT
            and self.action_digest == proposal.digest
        )


@dataclass(frozen=True, slots=True)
class RequiredCheckpoint:
    id: str
    version: str
    evaluator: CheckpointEvaluator = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.id) is not str or not self.id:
            raise PolicyError("checkpoint id must be a non-empty string")
        if type(self.version) is not str or not self.version:
            raise PolicyError("checkpoint version must be a non-empty string")
        if not callable(self.evaluator):
            raise PolicyError("checkpoint evaluator must be callable")

    async def check(self, proposal: ActionProposal) -> CheckpointRecord:
        result = self.evaluator(proposal)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, AcceptanceStatus):
            result = AcceptanceRecord(self.id, self.version, result)
        if not isinstance(result, AcceptanceRecord):
            raise PolicyError("required checkpoint returned an invalid result")
        if result.policy_id != self.id or result.policy_version != self.version:
            raise PolicyError("required checkpoint returned mismatched identity")
        return CheckpointRecord(
            self.id,
            self.version,
            proposal.digest,
            result.status,
            result.reasons,
        )


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    operation_id: str
    state: ExecutionState
    external_id: str | None = None
    source_version: str | None = None

    def __post_init__(self) -> None:
        if type(self.operation_id) is not str or not self.operation_id:
            raise PolicyError("receipt operation id must be non-empty")
        if self.state not in {
            ExecutionState.SUCCEEDED,
            ExecutionState.FAILED_BEFORE_EFFECT,
            ExecutionState.OUTCOME_UNKNOWN,
        }:
            raise PolicyError("receipt has an invalid terminal state")
        for value, name in (
            (self.external_id, "external id"),
            (self.source_version, "source version"),
        ):
            if value is not None and (type(value) is not str or not value):
                raise PolicyError(f"{name} must be a non-empty string when present")


@dataclass(frozen=True, slots=True)
class WriteRecord:
    proposal: ActionProposal
    state: ExecutionState
    authorization: AuthorizationRecord | None = None
    receipt: ExecutionReceipt | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, ActionProposal) or not isinstance(
            self.state, ExecutionState
        ):
            raise PolicyError("write record has invalid proposal or state")
        if self.authorization is not None and not isinstance(
            self.authorization, AuthorizationRecord
        ):
            raise PolicyError("write authorization has an invalid type")
        if self.receipt is not None and not isinstance(self.receipt, ExecutionReceipt):
            raise PolicyError("write receipt has an invalid type")
        if self.state is ExecutionState.PROPOSED and (
            self.authorization is not None or self.receipt is not None
        ):
            raise PolicyError("proposed writes cannot have authorization or receipt")
        if self.state is not ExecutionState.PROPOSED and self.authorization is None:
            raise PolicyError("post-proposal writes require authorization")
        if self.authorization is not None and (
            self.authorization.action_digest != self.proposal.digest
            or self.authorization.scope != self.proposal.scope
        ):
            raise PolicyError("write authorization does not match its proposal")
        if self.receipt is not None and (
            self.receipt.operation_id != self.proposal.operation_id
            or (
                self.state is not ExecutionState.OUTCOME_UNKNOWN
                and self.receipt.state is not self.state
            )
        ):
            raise PolicyError("write receipt does not match its operation state")


class DurableIntentStore(Protocol):
    def record(self, value: WriteRecord) -> None | Awaitable[None]: ...


async def maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def source_versions(evidence: Sequence[Evidence]) -> Mapping[str, str | None]:
    return MappingProxyType({record.id: record.source_version for record in evidence})
