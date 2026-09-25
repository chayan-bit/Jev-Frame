"""Evaluate one Jev judgment offline with a scripted provider."""

import asyncio
import inspect
import time
from collections.abc import Sequence
from typing import Any

from jev_frame import (
    AttemptAdmission,
    AttemptStatus,
    DecisionClient,
    DecisionContext,
    DecisionInputs,
    Judgment,
    NoulAnswer,
    NoulQuestion,
    PrimitiveAnswer,
    ProviderAttempt,
    ProviderBatch,
    RunLimits,
    Subject,
    Usage,
    UsageCoverage,
)
from jev_frame.compiler import CompiledQuestion

# Every class of work needs an explicit finite budget; zero disables it.
LIMITS = RunLimits(
    provider_attempts=1,
    submitted_questions=1,
    tool_attempts=0,
    investigation_steps=0,
    concurrent_operations=1,
    writes=0,
    planner_calls=0,
    plan_revisions=0,
    child_depth=0,
    child_runs=0,
)


class OfflineProvider:
    """Answers every yes/no (Noul) question with probability 0.9."""

    def answer(self, question: CompiledQuestion) -> PrimitiveAnswer:
        return NoulAnswer(0.9)

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
        attempt = ProviderAttempt(f"{operation_id}:1", 1, AttemptStatus.STARTED)
        if admit_attempt is not None:
            admitted = admit_attempt(attempt)
            if inspect.isawaitable(admitted):
                await admitted
        return ProviderBatch(
            {question.routing_id: self.answer(question) for question in questions},
            requested_model,
            "offline-model",
            None,
            Usage(UsageCoverage.COMPLETE, 3, 1, 1, len(questions)),
            (ProviderAttempt(attempt.id, 1, AttemptStatus.SUCCEEDED),),
        )


async def main() -> None:
    client = DecisionClient(OfflineProvider(), model="offline")
    judgment = Judgment(
        "is_clear",
        "1.0.0",
        NoulQuestion("Is the statement clear?"),
        (Subject("statement"),),
    )
    result = await client.evaluate(
        judgment,
        DecisionInputs("q-1", {"statement": "Typed boundaries are explicit."}),
        DecisionContext("quickstart", time.monotonic() + 30.0, LIMITS),
    )
    print(result.answer, result.returned_model, result.usage.submitted_questions)


if __name__ == "__main__":
    asyncio.run(main())
