"""Run one Jev decision through a host-owned Pydantic AI agent offline."""

import asyncio
import inspect
import os
from collections.abc import Sequence
from typing import Any

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from pydantic import BaseModel
from pydantic_ai import Agent, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from jev_frame import (
    AttemptAdmission,
    AttemptStatus,
    DecisionClient,
    DecisionContext,
    DecisionInputs,
    Judgment,
    NoulAnswer,
    NoulQuestion,
    ProviderAttempt,
    ProviderBatch,
    RunLimits,
    Subject,
    Usage,
    UsageCoverage,
)
from jev_frame.compiler import CompiledQuestion
from jev_frame.integrations.pydantic_ai import (
    PydanticAIDecisionContext,
    decision_tool,
)


class Arguments(BaseModel):
    statement: str


class OfflineProvider:
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
        answers = {question.routing_id: NoulAnswer(0.9) for question in questions}
        finished = ProviderAttempt(attempt.id, 1, AttemptStatus.SUCCEEDED)
        return ProviderBatch(
            answers,
            requested_model,
            "offline-model",
            None,
            Usage(UsageCoverage.COMPLETE, 3, 1, 1, len(questions)),
            (finished,),
        )


def inputs(arguments: BaseModel) -> DecisionInputs:
    if not isinstance(arguments, Arguments):
        raise TypeError("expected Arguments")
    return DecisionInputs(
        f"judge:{arguments.statement}", {"statement": arguments.statement}
    )


def scripted_model(messages: list[Any], info: AgentInfo) -> ModelResponse:
    if not any(
        isinstance(part, ToolReturnPart)
        for message in messages
        for part in message.parts
    ):
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "judge_clarity",
                    {"statement": "Typed boundaries are explicit."},
                )
            ]
        )
    return ModelResponse(parts=[TextPart("The advisory decision is recorded.")])


async def main() -> None:
    client = DecisionClient(OfflineProvider(), model="offline-requested")
    judgment = Judgment(
        "is_clear",
        "1.0.0",
        NoulQuestion("Is the statement clear?"),
        (Subject("statement"),),
    )
    judge = decision_tool(
        client,
        judgment,
        name="judge_clarity",
        description="Judge whether a statement is clear.",
        args_schema=Arguments,
    )
    limits = RunLimits(1, 1, 0, 0, 1, 0, 0, 0, 0, 0)
    context = PydanticAIDecisionContext(
        DecisionContext("example", 100.0, limits, clock=lambda: 0.0),
        inputs,
    )
    agent = Agent(
        FunctionModel(scripted_model),
        deps_type=PydanticAIDecisionContext,
        tools=[judge],
    )
    result = await agent.run("Assess the statement.", deps=context)
    returned = next(
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    )
    print(result.output)
    print(returned.content)
    print(returned.metadata)


if __name__ == "__main__":
    asyncio.run(main())
