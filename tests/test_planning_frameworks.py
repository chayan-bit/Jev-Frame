import os
import unittest
from typing import Any

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

try:
    from langchain_core.runnables import RunnableLambda
    from pydantic_ai import Agent, ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel
except ImportError as error:  # pragma: no cover - core-only installation
    raise unittest.SkipTest("planning framework extras are not installed") from error

from jev_frame import (
    GeneratedText,
    PlannerCapability,
    PlannerEngine,
    PlannerTurn,
    PlanStep,
    ProposedResult,
    RunContext,
    RunLimits,
    Runtime,
    TaskInputBinding,
    TerminalStatus,
    Tool,
    UsageCoverage,
)
from jev_frame.integrations.langchain import planner_callable as langchain_planner
from jev_frame.integrations.pydantic_ai import planner_callable as pydantic_planner


class UnexpectedProvider:
    async def evaluate(self, **arguments: Any) -> Any:
        raise AssertionError("planner fixture must not call a decision provider")


def capability(calls: list[str]) -> PlannerCapability:
    def draft(text: str) -> str:
        calls.append(text)
        return text

    return PlannerCapability(
        Tool(
            "draft",
            "1.0.0",
            "Draft generated text.",
            draft,
            {"text": TaskInputBinding(("text",))},
        ),
        generated_parameters=("text",),
    )


def plan(request: Any) -> PlannerTurn:
    if request.outcomes:
        return PlannerTurn(ProposedResult(request.outcomes[-1].value))
    return PlannerTurn(
        PlanStep(
            "draft",
            "draft",
            {"text": GeneratedText("framework draft", "scripted", "1.0.0")},
        )
    )


def engine(planner: Any, calls: list[str]) -> PlannerEngine[str]:
    runtime = Runtime(
        UnexpectedProvider(),
        model="unused",
        completion_checks={"step": lambda value, store: True},
    )
    return PlannerEngine(
        runtime,
        planner,
        (capability(calls),),
        result_type=str,
        result_validator=lambda value, store: True,
        step_acceptance_policy="step",
    )


def context(identifier: str) -> RunContext:
    return RunContext(
        "fixture",
        100.0,
        RunLimits(0, 0, 1, 0, 1, 0, 2, 1, 0, 0),
        clock=lambda: 0.0,
        run_id=identifier,
    )


class PlanningFrameworkTests(unittest.IsolatedAsyncioTestCase):
    async def test_langchain_runnable_owns_only_planner_calls(self) -> None:
        calls: list[str] = []
        runnable = RunnableLambda(plan)
        value = engine(langchain_planner(runnable), calls)

        result = await value.run("Draft through LangChain.", context("langchain-plan"))

        self.assertIs(result.status, TerminalStatus.COMPLETED)
        self.assertEqual(result.value, "framework draft")
        self.assertEqual(calls, ["framework draft"])
        self.assertTrue(
            all(item.coverage is UsageCoverage.UNKNOWN for item in result.planner_usage)
        )

    async def test_pydantic_ai_agent_owns_only_planner_calls(self) -> None:
        calls: list[str] = []
        agent = Agent(
            FunctionModel(
                lambda messages, info: ModelResponse(parts=[TextPart("proposal")])
            )
        )
        planner = pydantic_planner(
            agent,
            lambda request: request.objective,
            lambda output, request: plan(request),
        )
        value = engine(planner, calls)

        result = await value.run("Draft through Pydantic AI.", context("pydantic-plan"))

        self.assertIs(result.status, TerminalStatus.COMPLETED)
        self.assertEqual(result.value, "framework draft")
        self.assertEqual(calls, ["framework draft"])
        self.assertTrue(
            all(item.coverage is UsageCoverage.UNKNOWN for item in result.planner_usage)
        )


if __name__ == "__main__":
    unittest.main()
