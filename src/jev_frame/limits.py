from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum

from .definitions import JevFrameError, RunLimits, Usage, UsageCoverage
from .provider import ProviderAttempt


class AdmissionError(JevFrameError):
    """A shared limit or deadline rejected work before dispatch."""


class BudgetExhaustedError(AdmissionError):
    pass


class DeadlineExceededError(AdmissionError):
    pass


class ChildRunLimitError(BudgetExhaustedError):
    pass


class UsageMeasurementKind(str, Enum):
    OBSERVED = "observed"
    ESTIMATED = "estimated"
    RESERVED = "reserved"
    RELEASED = "released"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class UsageMeasurement:
    operation_id: str
    kind: UsageMeasurementKind
    input_tokens: int | None = None
    output_tokens: int | None = None
    coverage: UsageCoverage = UsageCoverage.UNKNOWN

    def __post_init__(self) -> None:
        if type(self.operation_id) is not str or not self.operation_id:
            raise ValueError("usage operation_id must be a non-empty string")
        if not isinstance(self.kind, UsageMeasurementKind) or not isinstance(
            self.coverage, UsageCoverage
        ):
            raise TypeError("usage kind and coverage must use their public enums")
        for name in ("input_tokens", "output_tokens"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be unknown or nonnegative")


@dataclass(frozen=True, slots=True)
class LedgerSnapshot:
    provider_attempts: int
    submitted_questions: int
    tool_attempts: int
    investigation_steps: int
    writes: int
    child_runs: int
    max_child_depth: int
    planner_calls: int
    plan_revisions: int
    active_operations: int
    attempt_ids: tuple[str, ...]
    tool_attempt_ids: tuple[str, ...]
    investigation_ids: tuple[str, ...]
    write_ids: tuple[str, ...]
    child_run_ids: tuple[str, ...]
    planner_call_ids: tuple[str, ...]
    plan_revision_ids: tuple[str, ...]
    measurements: tuple[UsageMeasurement, ...]


class UsageLedger:
    """One atomic in-memory admission and usage ledger shared by callers and runs."""

    def __init__(self, limits: RunLimits) -> None:
        if not isinstance(limits, RunLimits):
            raise TypeError("limits must be RunLimits")
        self.limits = limits
        self._lock = asyncio.Lock()
        self._attempt_questions: dict[str, int] = {}
        self._tool_attempts: set[str] = set()
        self._investigations: set[str] = set()
        self._writes: set[str] = set()
        self._child_runs: dict[str, int] = {}
        self._planner_calls: set[str] = set()
        self._plan_revisions: set[str] = set()
        self._active: set[str] = set()
        self._operations: set[str] = set()
        self._measurements: dict[
            tuple[str, UsageMeasurementKind], UsageMeasurement
        ] = {}

    @staticmethod
    def _check_deadline(deadline: float, clock: Callable[[], float]) -> None:
        if clock() >= deadline:
            raise DeadlineExceededError("deadline expired before dispatch")

    @asynccontextmanager
    async def operation(
        self,
        operation_id: str,
        *,
        deadline: float,
        clock: Callable[[], float],
    ) -> AsyncIterator[None]:
        if type(operation_id) is not str or not operation_id:
            raise ValueError("operation_id must be a non-empty string")
        self._check_deadline(deadline, clock)
        async with self._lock:
            if operation_id in self._operations:
                raise AdmissionError(f"operation {operation_id!r} was already admitted")
            if len(self._active) >= self.limits.concurrent_operations:
                raise BudgetExhaustedError("concurrent operation limit exhausted")
            self._active.add(operation_id)
            self._operations.add(operation_id)
        try:
            yield
        finally:
            async with self._lock:
                self._active.discard(operation_id)

    async def admit_provider_attempt(
        self,
        attempt: ProviderAttempt,
        question_count: int,
        *,
        deadline: float,
        clock: Callable[[], float],
    ) -> None:
        if type(attempt.id) is not str or not attempt.id:
            raise ValueError("attempt id must be a non-empty string")
        if type(question_count) is not int or question_count < 1:
            raise ValueError("question_count must be a positive integer")
        self._check_deadline(deadline, clock)
        async with self._lock:
            previous = self._attempt_questions.get(attempt.id)
            if previous is not None:
                if previous != question_count:
                    raise AdmissionError("an attempt identity changed question count")
                return
            if len(self._attempt_questions) >= self.limits.provider_attempts:
                raise BudgetExhaustedError("provider attempt limit exhausted")
            used_questions = sum(self._attempt_questions.values())
            if used_questions + question_count > self.limits.submitted_questions:
                raise BudgetExhaustedError("submitted question limit exhausted")
            self._attempt_questions[attempt.id] = question_count

    async def record_usage(self, operation_id: str, usage: Usage) -> None:
        kind = (
            UsageMeasurementKind.UNKNOWN
            if usage.coverage is UsageCoverage.UNKNOWN
            else UsageMeasurementKind.OBSERVED
        )
        await self._record(
            UsageMeasurement(
                operation_id,
                kind,
                usage.input_tokens,
                usage.output_tokens,
                usage.coverage,
            )
        )

    async def admit_tool_attempt(
        self,
        attempt_id: str,
        *,
        deadline: float,
        clock: Callable[[], float],
    ) -> None:
        if type(attempt_id) is not str or not attempt_id:
            raise ValueError("tool attempt id must be a non-empty string")
        self._check_deadline(deadline, clock)
        async with self._lock:
            if attempt_id in self._tool_attempts:
                return
            if len(self._tool_attempts) >= self.limits.tool_attempts:
                raise BudgetExhaustedError("tool attempt limit exhausted")
            self._tool_attempts.add(attempt_id)

    async def admit_write(
        self,
        operation_id: str,
        *,
        deadline: float,
        clock: Callable[[], float],
    ) -> None:
        if type(operation_id) is not str or not operation_id:
            raise ValueError("write operation id must be a non-empty string")
        self._check_deadline(deadline, clock)
        async with self._lock:
            if operation_id in self._writes:
                return
            if len(self._writes) >= self.limits.writes:
                raise BudgetExhaustedError("write limit exhausted")
            self._writes.add(operation_id)

    async def admit_investigation(
        self,
        investigation_id: str,
        *,
        deadline: float,
        clock: Callable[[], float],
    ) -> None:
        if type(investigation_id) is not str or not investigation_id:
            raise ValueError("investigation id must be a non-empty string")
        self._check_deadline(deadline, clock)
        async with self._lock:
            if investigation_id in self._investigations:
                return
            if len(self._investigations) >= self.limits.investigation_steps:
                raise BudgetExhaustedError("investigation step limit exhausted")
            self._investigations.add(investigation_id)

    async def admit_child_run(
        self,
        run_id: str,
        depth: int,
        *,
        deadline: float,
        clock: Callable[[], float],
    ) -> None:
        if type(run_id) is not str or not run_id:
            raise ValueError("child run id must be a non-empty string")
        if type(depth) is not int or depth < 1:
            raise ValueError("child depth must be a positive integer")
        self._check_deadline(deadline, clock)
        async with self._lock:
            previous = self._child_runs.get(run_id)
            if previous is not None:
                if previous != depth:
                    raise AdmissionError("a child run identity changed depth")
                return
            if depth > self.limits.child_depth:
                raise ChildRunLimitError("child depth limit exhausted")
            if len(self._child_runs) >= self.limits.child_runs:
                raise ChildRunLimitError("child run count limit exhausted")
            self._child_runs[run_id] = depth

    async def admit_planner_call(
        self,
        call_id: str,
        *,
        deadline: float,
        clock: Callable[[], float],
    ) -> None:
        await self._admit_named(
            call_id,
            self._planner_calls,
            self.limits.planner_calls,
            "planner call",
            deadline,
            clock,
        )

    async def admit_plan_revision(
        self,
        revision_id: str,
        *,
        deadline: float,
        clock: Callable[[], float],
    ) -> None:
        await self._admit_named(
            revision_id,
            self._plan_revisions,
            self.limits.plan_revisions,
            "plan revision",
            deadline,
            clock,
        )

    async def _admit_named(
        self,
        identifier: str,
        values: set[str],
        limit: int,
        name: str,
        deadline: float,
        clock: Callable[[], float],
    ) -> None:
        if type(identifier) is not str or not identifier:
            raise ValueError(f"{name} id must be a non-empty string")
        self._check_deadline(deadline, clock)
        async with self._lock:
            if identifier in values:
                return
            if len(values) >= limit:
                raise BudgetExhaustedError(f"{name} limit exhausted")
            values.add(identifier)

    async def record_estimate(
        self,
        operation_id: str,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        await self._record(
            UsageMeasurement(
                operation_id,
                UsageMeasurementKind.ESTIMATED,
                input_tokens,
                output_tokens,
            )
        )

    async def reserve_usage(
        self,
        operation_id: str,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        await self._record(
            UsageMeasurement(
                operation_id,
                UsageMeasurementKind.RESERVED,
                input_tokens,
                output_tokens,
            )
        )

    async def release_reservation(self, operation_id: str) -> None:
        async with self._lock:
            reservation = self._measurements.get(
                (operation_id, UsageMeasurementKind.RESERVED)
            )
            if reservation is None:
                raise AdmissionError(f"operation {operation_id!r} has no reservation")
            self._measurements[(operation_id, UsageMeasurementKind.RELEASED)] = (
                UsageMeasurement(
                    operation_id,
                    UsageMeasurementKind.RELEASED,
                    reservation.input_tokens,
                    reservation.output_tokens,
                )
            )

    async def _record(self, measurement: UsageMeasurement) -> None:
        key = (measurement.operation_id, measurement.kind)
        async with self._lock:
            previous = self._measurements.get(key)
            if previous is not None and previous != measurement:
                raise AdmissionError(
                    "usage identity was recorded with different values"
                )
            self._measurements[key] = measurement

    async def snapshot(self) -> LedgerSnapshot:
        async with self._lock:
            return LedgerSnapshot(
                len(self._attempt_questions),
                sum(self._attempt_questions.values()),
                len(self._tool_attempts),
                len(self._investigations),
                len(self._writes),
                len(self._child_runs),
                max(self._child_runs.values(), default=0),
                len(self._planner_calls),
                len(self._plan_revisions),
                len(self._active),
                tuple(self._attempt_questions),
                tuple(self._tool_attempts),
                tuple(self._investigations),
                tuple(self._writes),
                tuple(self._child_runs),
                tuple(self._planner_calls),
                tuple(self._plan_revisions),
                tuple(self._measurements.values()),
            )
