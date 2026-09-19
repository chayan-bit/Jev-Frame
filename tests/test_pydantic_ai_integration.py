import asyncio
import inspect
import os
import unittest
from collections.abc import Mapping, Sequence
from enum import IntEnum
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

try:
    from pydantic import BaseModel, Field
    from pydantic_ai import (
        Agent,
        ModelResponse,
        RequestUsage,
        TextPart,
        ToolCallPart,
        UseEnumMemberDocstrings,
    )
    from pydantic_ai.messages import ToolReturnPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel
    from pydantic_ai.models.typesafe import TypeSafeModel
    from pydantic_ai.providers.typesafe import TypeSafeProvider
except ImportError as error:  # pragma: no cover - core-only installation
    raise unittest.SkipTest("jev-frame[pydantic-ai] is not installed") from error

from typesafe_sdk import (
    Noul,
    Score,
    SystemOneResponse,
)
from typesafe_sdk import (
    NoulAnswer as SDKNoulAnswer,
)
from typesafe_sdk import (
    ScoreAnswer as SDKScoreAnswer,
)
from typesafe_sdk import (
    Usage as SDKUsage,
)

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
    ScoreAnswer,
    ScoreQuestion,
    Subject,
    Usage,
    UsageCoverage,
)
from jev_frame.compiler import CompiledQuestion
from jev_frame.integrations.pydantic_ai import (
    CheckpointedOutput,
    PydanticAIDecisionContext,
    RequiredCheckpointRejected,
    decision_tool,
    inspect_native_typesafe_usage,
    required_checkpoint_output,
)


class DecisionArguments(BaseModel):
    statement: str


class Draft(BaseModel):
    statement: str


class OfflineProvider:
    def __init__(
        self,
        answer: NoulAnswer | ScoreAnswer | None = None,
        *,
        failure: bool = False,
        block: bool = False,
    ) -> None:
        self.answer = NoulAnswer(0.91) if answer is None else answer
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
        answers = {question.routing_id: self.answer for question in questions}
        finished = ProviderAttempt(attempt.id, 1, AttemptStatus.SUCCEEDED)
        return ProviderBatch(
            answers,
            requested_model,
            "offline-model",
            None,
            Usage(UsageCoverage.COMPLETE, 4, 1, 1, len(questions)),
            (finished,),
        )


def limits() -> RunLimits:
    return RunLimits(10, 10, 0, 0, 2, 0, 0, 0, 0, 0)


def judgment(*, score: bool = False) -> Judgment:
    primitive = (
        ScoreQuestion("How clear is the statement?", ("opaque", "partial", "clear"))
        if score
        else NoulQuestion("Does the excerpt support the statement?")
    )
    return Judgment(
        "clarity" if score else "supports",
        "1.0.0",
        primitive,
        (Subject("statement"),),
        (EvidenceSelector("excerpt"),),
    )


def host_context(*, evidence_scope: str = "fixture") -> PydanticAIDecisionContext:
    decision_context = DecisionContext("fixture", 100.0, limits(), clock=lambda: 0.0)

    def inputs(arguments: BaseModel) -> DecisionInputs:
        if not isinstance(arguments, DecisionArguments):
            raise TypeError("expected DecisionArguments")
        statement = arguments.statement
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

    return PydanticAIDecisionContext(decision_context, inputs)


def tool_model(name: str, arguments: dict[str, Any], schemas: list[Any]) -> Any:
    def respond(messages: list[Any], info: AgentInfo) -> ModelResponse:
        schemas[:] = info.function_tools
        if not any(
            isinstance(part, ToolReturnPart)
            for message in messages
            for part in message.parts
        ):
            return ModelResponse(parts=[ToolCallPart(name, arguments)])
        return ModelResponse(parts=[TextPart("done")])

    return FunctionModel(respond)


def tool_return(result: Any) -> ToolReturnPart:
    return next(
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    )


class PydanticAIDecisionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_advisory_tool_preserves_noul_artifact_and_host_context(self) -> None:
        provider = OfflineProvider()
        client = DecisionClient(provider, model="offline-requested")
        tool = decision_tool(
            client,
            judgment(),
            name="judge_support",
            description="Judge whether the evidence supports the statement.",
            args_schema=DecisionArguments,
        )
        schemas: list[Any] = []
        agent = Agent(
            tool_model("judge_support", {"statement": "claim"}, schemas),
            deps_type=PydanticAIDecisionContext,
            tools=[tool],
        )

        result = await agent.run("Use the advisory tool.", deps=host_context())

        returned = tool_return(result)
        self.assertIsInstance(returned.content, Mapping)
        self.assertEqual(provider.calls, ["judge:claim"])
        self.assertEqual(returned.metadata.answer, NoulAnswer(0.91))
        assert isinstance(returned.content, Mapping)
        self.assertEqual(returned.content["returned_model"], "offline-model")
        self.assertNotIn("Synthetic offline evidence", str(returned.content))
        self.assertEqual(
            set(schemas[0].parameters_json_schema["properties"]), {"statement"}
        )
        snapshot = await client.ledger.snapshot()  # type: ignore[union-attr]
        self.assertEqual(snapshot.provider_attempts, 1)

    async def test_score_semantics_and_optional_skip(self) -> None:
        score = ScoreAnswer(
            1.4,
            ("opaque", "partial", "clear"),
            (0.1, 0.4, 0.5),
            0.8,
        )
        provider = OfflineProvider(score)
        tool = decision_tool(
            DecisionClient(provider, model="offline-requested"),
            judgment(score=True),
            name="judge_clarity",
            description="Score statement clarity.",
            args_schema=DecisionArguments,
        )
        agent = Agent(
            tool_model("judge_clarity", {"statement": "claim"}, []),
            deps_type=PydanticAIDecisionContext,
            tools=[tool],
        )

        result = await agent.run("Use the advisory tool.", deps=host_context())

        self.assertEqual(tool_return(result).metadata.answer, score)
        skipped = OfflineProvider()
        skip_agent = Agent(
            FunctionModel(
                lambda messages, info: ModelResponse(parts=[TextPart("skip")])
            )
        )
        skip_result = await skip_agent.run("Do not use tools.")
        self.assertEqual(skip_result.output, "skip")
        self.assertEqual(skipped.calls, [])

    async def test_scope_provider_failure_and_cancellation_remain_explicit(
        self,
    ) -> None:
        provider = OfflineProvider()
        tool = decision_tool(
            DecisionClient(provider, model="offline-requested"),
            judgment(),
            name="judge_support",
            description="Judge support.",
            args_schema=DecisionArguments,
        )
        agent = Agent(
            tool_model("judge_support", {"statement": "claim"}, []),
            deps_type=PydanticAIDecisionContext,
            tools=[tool],
        )
        with self.assertRaises(InputValidationError):
            await agent.run("Use the tool.", deps=host_context(evidence_scope="forged"))

        failed = OfflineProvider(failure=True)
        failed_tool = decision_tool(
            DecisionClient(failed, model="offline-requested"),
            judgment(),
            name="judge_support",
            description="Judge support.",
            args_schema=DecisionArguments,
        )
        failed_agent = Agent(
            tool_model("judge_support", {"statement": "claim"}, []),
            deps_type=PydanticAIDecisionContext,
            tools=[failed_tool],
        )
        with self.assertRaises(ProviderDispatchError):
            await failed_agent.run("Use the tool.", deps=host_context())

        blocked = OfflineProvider(block=True)
        blocked_tool = decision_tool(
            DecisionClient(blocked, model="offline-requested"),
            judgment(),
            name="judge_support",
            description="Judge support.",
            args_schema=DecisionArguments,
        )
        blocked_agent = Agent(
            tool_model("judge_support", {"statement": "claim"}, []),
            deps_type=PydanticAIDecisionContext,
            tools=[blocked_tool],
        )
        task = asyncio.create_task(
            blocked_agent.run("Use the tool.", deps=host_context())
        )
        await blocked.started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(blocked.cancelled.is_set())


def proposal(host: PydanticAIDecisionContext, draft: BaseModel) -> ActionProposal:
    if not isinstance(draft, Draft):
        raise TypeError("expected Draft")
    return ActionProposal(
        "publish-1",
        "draft.publish",
        "1.0.0",
        {"statement": draft.statement},
        host.decision_context.scope,
        {"draft": "v1"},
    )


def output_model(statement: str, seen: list[AgentInfo]) -> FunctionModel:
    def respond(messages: list[Any], info: AgentInfo) -> ModelResponse:
        seen.append(info)
        return ModelResponse(
            parts=[ToolCallPart("accepted_draft", {"statement": statement})]
        )

    return FunctionModel(respond)


class PydanticAIRequiredCheckpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_output_function_checks_each_current_artifact(self) -> None:
        checked: list[str] = []

        def accept(action: ActionProposal) -> AcceptanceStatus:
            checked.append(action.digest)
            return AcceptanceStatus.ACCEPT

        output = required_checkpoint_output(
            RequiredCheckpoint("accepted_draft", "1.0.0", accept),
            proposal,
            name="accepted_draft",
            description="Accept the current draft only after its checkpoint.",
            args_schema=Draft,
        )
        seen: list[AgentInfo] = []
        agent = Agent(
            output_model("first", seen),
            output_type=output,
            deps_type=PydanticAIDecisionContext,
        )
        first = await agent.run("Submit the draft.", deps=host_context())
        changed = await Agent(
            output_model("changed", seen),
            output_type=output,
            deps_type=PydanticAIDecisionContext,
        ).run("Submit the changed draft.", deps=host_context())

        self.assertIsInstance(first.output, CheckpointedOutput)
        self.assertNotEqual(
            first.output.checkpoint.action_digest,
            changed.output.checkpoint.action_digest,
        )
        self.assertEqual(
            checked,
            [
                first.output.checkpoint.action_digest,
                changed.output.checkpoint.action_digest,
            ],
        )
        self.assertEqual(seen[0].function_tools, [])
        self.assertEqual(
            [item.name for item in seen[0].output_tools], ["accepted_draft"]
        )

    async def test_rejected_output_function_fails_closed(self) -> None:
        output = required_checkpoint_output(
            RequiredCheckpoint(
                "accepted_draft", "1.0.0", lambda action: AcceptanceStatus.REJECT
            ),
            proposal,
            name="accepted_draft",
            description="Accept the current draft only after its checkpoint.",
            args_schema=Draft,
        )
        agent = Agent(
            output_model("blocked", []),
            output_type=output,
            deps_type=PydanticAIDecisionContext,
        )

        with self.assertRaises(RequiredCheckpointRejected):
            await agent.run("Submit the draft.", deps=host_context())


class Clarity(UseEnumMemberDocstrings, IntEnum):
    """How clearly the statement communicates its meaning."""

    opaque = 0
    """The meaning is not recoverable."""

    partial = 1
    """The main point is present but incomplete."""

    clear = 2
    """The statement is complete and actionable."""


class NativeReview(BaseModel):
    """Review a synthetic statement."""

    support: float = Field(ge=0, le=1, description="Is the statement supported?")
    clarity: Clarity = Field(description="How clearly is it expressed?")


class OfflineTypeSafeClient:
    _config = SimpleNamespace(base_url="https://offline.invalid")

    async def system_one(
        self,
        state: Any,
        questions: Mapping[str, Any],
        *,
        model: str | None = None,
        retry: Any = None,
        timeout: Any = None,
        **kwargs: Any,
    ) -> SystemOneResponse:
        answers: dict[str, Any] = {}
        for name, question in questions.items():
            if isinstance(question, Noul):
                answers[name] = SDKNoulAnswer(noul=0.73)
            elif isinstance(question, Score):
                answers[name] = SDKScoreAnswer(
                    score=1.2,
                    confidence=0.8,
                    legend={0: "opaque", 1: "partial", 2: "clear"},
                    probabilities={0: 0.1, 1: 0.6, 2: 0.3},
                )
            else:
                raise TypeError(f"unexpected native question {type(question)!r}")
        return SystemOneResponse(
            model="jev-offline",
            usage=SDKUsage(input_tokens=5, output_tokens=2),
            answers=answers,
        )

    async def aclose(self) -> None:
        return None


class NativeTypeSafeConformanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_probability_and_score_metadata_are_observable(self) -> None:
        provider = TypeSafeProvider(typesafe_client=OfflineTypeSafeClient())  # type: ignore[call-overload]
        model = TypeSafeModel("jev-test", provider=provider)

        result = await Agent(model, output_type=NativeReview).run("fixture")

        self.assertEqual(result.output.support, 0.73)
        self.assertEqual(result.output.clarity, Clarity.partial)
        self.assertIsNotNone(result.response.provider_details)
        assert result.response.provider_details is not None
        self.assertEqual(result.response.provider_details["scores"]["clarity"], 1.2)
        self.assertEqual(
            result.response.provider_details["probabilities"]["clarity"],
            {"0": 0.1, "1": 0.6, "2": 0.3},
        )
        usage = inspect_native_typesafe_usage(result.response)
        self.assertEqual(usage.coverage, UsageCoverage.PARTIAL)
        self.assertEqual((usage.input_tokens, usage.output_tokens), (5, 2))
        self.assertIsNone(usage.request_count)

    async def test_fallback_response_does_not_claim_hidden_jev_usage(self) -> None:
        response = ModelResponse(
            parts=[TextPart("fallback")],
            usage=RequestUsage(input_tokens=9, output_tokens=3),
            model_name="offline-fallback",
        )

        usage = inspect_native_typesafe_usage(response)

        self.assertEqual(usage.coverage, UsageCoverage.UNKNOWN)
        self.assertIsNone(usage.request_count)
        self.assertEqual(usage.returned_model, "offline-fallback")


if __name__ == "__main__":
    unittest.main()
