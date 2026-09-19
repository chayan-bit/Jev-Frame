"""Run one Jev decision through a host-owned LangGraph ToolNode offline."""

import asyncio
import inspect
from collections.abc import Mapping, Sequence
from typing import Any

from langchain.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel

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
from jev_frame.integrations.langchain import (
    LangChainDecisionContext,
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


def inputs(arguments: Mapping[str, Any]) -> DecisionInputs:
    statement = arguments["statement"]
    return DecisionInputs(f"judge:{statement}", {"statement": statement})


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
    graph = StateGraph(MessagesState, context_schema=LangChainDecisionContext)
    graph.add_node("tools", ToolNode([judge], handle_tool_errors=False))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    limits = RunLimits(1, 1, 0, 0, 1, 0, 0, 0, 0, 0)
    context = LangChainDecisionContext(
        DecisionContext("example", 100.0, limits, clock=lambda: 0.0),
        inputs,
    )
    result = await graph.compile().ainvoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "judge_clarity",
                            "args": {"statement": "Typed boundaries are explicit."},
                            "id": "call-1",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        },
        context=context,
    )
    message = result["messages"][-1]
    print(message.content)
    print(message.artifact)


if __name__ == "__main__":
    asyncio.run(main())
