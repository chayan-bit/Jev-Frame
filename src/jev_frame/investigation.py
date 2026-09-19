from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from .definitions import (
    CandidateSet,
    ClarificationRequest,
    DefinitionError,
    ToolEffect,
    UnresolvedReason,
)
from .state import Evidence


@dataclass(frozen=True, slots=True)
class InvestigationNeed:
    reason: UnresolvedReason
    subjects: tuple[str, ...]
    needed: str | None
    scope: str
    attempt: int
    candidate_set: CandidateSet | None = None


@dataclass(frozen=True, slots=True)
class InvestigationResult:
    candidate_set: CandidateSet | None = None
    evidence: tuple[Evidence, ...] = ()
    clarification: ClarificationRequest | None = None

    def __post_init__(self) -> None:
        if (
            self.candidate_set is None
            and not self.evidence
            and self.clarification is None
        ):
            raise DefinitionError("investigation result must contain useful output")


InvestigationCallable = Callable[
    [InvestigationNeed], InvestigationResult | Awaitable[InvestigationResult]
]


@dataclass(frozen=True, slots=True)
class InvestigationAction:
    id: str
    reasons: tuple[UnresolvedReason, ...]
    function: InvestigationCallable = field(repr=False, compare=False)
    handles: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    priority: int = 100
    effect: ToolEffect = ToolEffect.READ
    timeout: float = 30.0
    blocking: bool = False

    def __post_init__(self) -> None:
        if type(self.id) is not str or not self.id:
            raise DefinitionError("investigation action id must be non-empty")
        if not self.reasons or any(
            not isinstance(reason, UnresolvedReason) for reason in self.reasons
        ):
            raise DefinitionError("investigation action reasons must be explicit")
        for values, name in (
            (self.handles, "handles"),
            (self.scopes, "scopes"),
        ):
            if len(values) != len(set(values)) or any(
                type(value) is not str or not value for value in values
            ):
                raise DefinitionError(
                    f"investigation action {name} must be unique strings"
                )
        if not callable(self.function):
            raise DefinitionError("investigation action function must be callable")
        if type(self.priority) is not int or self.priority < 0:
            raise DefinitionError("investigation priority must be nonnegative")
        if self.effect not in {ToolEffect.PURE, ToolEffect.READ}:
            raise DefinitionError("investigation actions cannot be mutations")
        if type(self.timeout) not in {int, float} or self.timeout <= 0:
            raise DefinitionError("investigation timeout must be positive")
        if type(self.blocking) is not bool or (
            self.blocking and inspect.iscoroutinefunction(self.function)
        ):
            raise DefinitionError(
                "async investigation actions cannot be declared blocking"
            )

    def applies(self, need: InvestigationNeed) -> bool:
        return (
            need.reason in self.reasons
            and (not self.handles or need.needed in self.handles)
            and (not self.scopes or need.scope in self.scopes)
        )
