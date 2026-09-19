import asyncio
import inspect
import json
import unittest
from collections.abc import Mapping, Sequence
from typing import Any, NotRequired, TypedDict

try:
    from langchain.messages import AIMessage
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode
    from pydantic import BaseModel
except ImportError as error:  # pragma: no cover - core-only installation
    raise unittest.SkipTest("jev-frame[langchain] is not installed") from error

from jev_frame import (
    AcceptanceStatus,
    ActionProposal,
    AttemptAdmission,
    AttemptStatus,
    DecisionClient,
    DecisionContext,
    DecisionInputs,
    EvidenceSelector,
    InputValidationError,
    Judgment,
    NoulAnswer,
    NoulQuestion,
    Observation,
    ProviderAttempt,
    ProviderBatch,
    ProviderDispatchError,
    RequiredCheckpoint,
    RunLimits,
    Subject,
    Usage,
    UsageCoverage,
)
from jev_frame.compiler import CompiledQuestion
from jev_frame.integrations.langchain import (
    LangChainDecisionContext,
    RequiredCheckpointRejected,
    decision_tool,
    required_checkpoint_node,
)
from jev_frame.policy import CheckpointRecord


class DecisionArguments(BaseModel):
    statement: str


class OfflineProvider:
    def __init__(self, *, failure: bool = False, block: bool = False) -> None:
        self.failure = failure
        self.block = block
        self.calls: list[str] = []
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

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
        self.calls.append(operation_id)
        self.started.set()
        if self.failure:
            raise ProviderDispatchError("offline_failure", (attempt,))
        if self.block:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
        answers = {question.routing_id: NoulAnswer(0.91) for question in questions}
        finished = ProviderAttempt(
            attempt.id,
            1,
            AttemptStatus.SUCCEEDED,
            request_id=f"request:{operation_id}",
        )
        return ProviderBatch(
            answers,
            requested_model,
            "offline-model",
            finished.request_id,
            Usage(UsageCoverage.COMPLETE, 4, 1, 1, len(questions)),
            (finished,),
        )


def limits() -> RunLimits:
    return RunLimits(10, 10, 0, 0, 2, 0, 0, 0, 0, 0)


def judgment() -> Judgment:
    return Judgment(
        "supports",
        "1.0.0",
        NoulQuestion("Does the excerpt support the statement?"),
        (Subject("statement"),),
        (EvidenceSelector("excerpt"),),
    )


def host_context(*, evidence_scope: str = "fixture") -> LangChainDecisionContext:
    decision_context = DecisionContext("fixture", 100.0, limits(), clock=lambda: 0.0)

    def inputs(arguments: Mapping[str, Any]) -> DecisionInputs:
        statement = arguments["statement"]
        return DecisionInputs(
            f"judge:{statement}",
            {"statement": statement},
            {
                "excerpt": Observation(
                    id=f"source:{statement}",
                    value="Synthetic offline evidence.",
                    source_id="fixture",
                    scope=evidence_scope,
                    observed_at=0.0,
                    source_version="v1",
                )
            },
        )

    return LangChainDecisionContext(decision_context, inputs)


def compiled_tool(provider: OfflineProvider) -> tuple[Any, Any]:
    client = DecisionClient(provider, model="offline-requested")
    tool = decision_tool(
        client,
        judgment(),
        name="judge_support",
        description="Judge whether an excerpt supports a statement.",
        args_schema=DecisionArguments,
    )
    graph = StateGraph(MessagesState, context_schema=LangChainDecisionContext)
    graph.add_node("tools", ToolNode([tool], handle_tool_errors=False))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    return graph.compile(), client


def invocation(statement: str = "claim") -> dict[str, Any]:
    return {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "judge_support",
                        "args": {"statement": statement},
                        "id": "tool-1",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    }


class LangChainDecisionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_node_preserves_host_loop_and_full_artifact(self) -> None:
        provider = OfflineProvider()
        graph, client = compiled_tool(provider)

        result = await graph.ainvoke(invocation(), context=host_context())

        message = result["messages"][-1]
        self.assertEqual(provider.calls, ["judge:claim"])
        self.assertEqual(message.artifact.answer, NoulAnswer(0.91))
        self.assertEqual(json.loads(message.content)["returned_model"], "offline-model")
        self.assertNotIn("Synthetic offline evidence", message.content)
        snapshot = await client.ledger.snapshot()  # type: ignore[union-attr]
        self.assertEqual(snapshot.provider_attempts, 1)
        self.assertEqual(snapshot.submitted_questions, 1)

    async def test_host_can_skip_the_optional_tool(self) -> None:
        provider = OfflineProvider()
        graph = StateGraph(MessagesState, context_schema=LangChainDecisionContext)
        graph.add_node("host", lambda state: {})
        graph.add_edge(START, "host")
        graph.add_edge("host", END)

        await graph.compile().ainvoke({"messages": []}, context=host_context())

        self.assertEqual(provider.calls, [])

    async def test_forged_scope_and_provider_failure_remain_explicit(self) -> None:
        graph, _ = compiled_tool(OfflineProvider())
        with self.assertRaises(InputValidationError):
            await graph.ainvoke(
                invocation(), context=host_context(evidence_scope="forged")
            )

        failed, _ = compiled_tool(OfflineProvider(failure=True))
        with self.assertRaises(ProviderDispatchError):
            await failed.ainvoke(invocation(), context=host_context())

    async def test_graph_cancellation_reaches_the_provider(self) -> None:
        provider = OfflineProvider(block=True)
        graph, _ = compiled_tool(provider)
        task = asyncio.create_task(graph.ainvoke(invocation(), context=host_context()))
        await provider.started.wait()

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertTrue(provider.cancelled.is_set())
        self.assertEqual(provider.calls, ["judge:claim"])


class ActionState(TypedDict):
    arguments: dict[str, Any]
    checkpoint: NotRequired[CheckpointRecord]


def proposal(state: ActionState) -> ActionProposal:
    return ActionProposal(
        "write-1",
        "records.update",
        "1.0.0",
        state["arguments"],
        "fixture",
        {"record": "v1"},
    )


class LangGraphCheckpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_required_node_rechecks_the_current_action(self) -> None:
        checked: list[str] = []

        def accept(action: ActionProposal) -> AcceptanceStatus:
            checked.append(action.digest)
            return AcceptanceStatus.ACCEPT

        node = required_checkpoint_node(
            RequiredCheckpoint("safe_write", "1.0.0", accept), proposal
        )
        graph = StateGraph(ActionState)
        graph.add_node("checkpoint", node)  # type: ignore[arg-type]
        graph.add_edge(START, "checkpoint")
        graph.add_edge("checkpoint", END)
        runnable = graph.compile()

        first = await runnable.ainvoke({"arguments": {"value": 1}})
        changed = await runnable.ainvoke(
            {
                "arguments": {"value": 2},
                "checkpoint": first["checkpoint"],
            }
        )

        self.assertNotEqual(
            first["checkpoint"].action_digest,
            changed["checkpoint"].action_digest,
        )
        self.assertEqual(
            checked,
            [first["checkpoint"].action_digest, changed["checkpoint"].action_digest],
        )

    async def test_required_node_rejects_instead_of_forwarding(self) -> None:
        executed: list[bool] = []

        def execute(state: ActionState) -> dict[str, Any]:
            executed.append(True)
            return {}

        node = required_checkpoint_node(
            RequiredCheckpoint(
                "safe_write", "1.0.0", lambda action: AcceptanceStatus.REJECT
            ),
            proposal,
        )
        graph = StateGraph(ActionState)
        graph.add_node("checkpoint", node)  # type: ignore[arg-type]
        graph.add_node("execute", execute)
        graph.add_edge(START, "checkpoint")
        graph.add_edge("checkpoint", "execute")
        graph.add_edge("execute", END)

        with self.assertRaises(RequiredCheckpointRejected):
            await graph.compile().ainvoke({"arguments": {"value": 1}})
        self.assertEqual(executed, [])


if __name__ == "__main__":
    unittest.main()
