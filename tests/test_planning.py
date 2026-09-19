import inspect
import unittest
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from jev_frame import (
    AgentDefinition,
    AttemptAdmission,
    AttemptStatus,
    CandidateOutcome,
    ChildRunPolicy,
    ChoiceAnswer,
    ChoiceQuestion,
    CompiledQuestion,
    CompletionContract,
    DecisionClient,
    EvidenceValue,
    GeneratedText,
    Judgment,
    OperatingPolicy,
    PlannerCapability,
    PlannerEngine,
    PlannerHandoff,
    PlannerTurn,
    PlanRevision,
    PlanStep,
    ProposedAlternative,
    ProposedResult,
    ProviderAttempt,
    ProviderBatch,
    RunContext,
    RunLimits,
    Runtime,
    StepValue,
    Subject,
    TaskInputBinding,
    TerminalStatus,
    Tool,
    UnresolvedReason,
    Usage,
    UsageCoverage,
    propose_select,
)


class ScriptedProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

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
        question = questions[0]
        answer = ChoiceAnswer(
            question.options[0].key,
            {
                option.key: 1.0 if index == 0 else 0.0
                for index, option in enumerate(question.options)
            },
            1.0,
        )
        return ProviderBatch(
            {question.routing_id: answer},
            requested_model,
            "offline",
            operation_id,
            Usage(UsageCoverage.COMPLETE, 2, 1, 1, 1),
            (ProviderAttempt(attempt.id, 1, AttemptStatus.SUCCEEDED),),
        )


def limits(
    *, planner_calls: int = 3, revisions: int = 2, tools: int = 4, children: int = 0
) -> RunLimits:
    return RunLimits(2, 2, tools, 0, 2, 0, planner_calls, revisions, 1, children)


def context(identifier: str, run_limits: RunLimits) -> RunContext:
    return RunContext(
        "fixture", 100.0, run_limits, clock=lambda: 0.0, run_id=identifier
    )


def engine(
    planner: Any,
    capabilities: Sequence[PlannerCapability],
    *,
    runtime: Runtime | None = None,
    validator: Any = lambda value, store: True,
) -> PlannerEngine[str]:
    shared = runtime or Runtime(
        ScriptedProvider(),
        model="offline",
        completion_checks={"step": lambda value, store: True},
    )
    return PlannerEngine(
        shared,
        planner,
        capabilities,
        result_type=str,
        result_validator=validator,
        step_acceptance_policy="step",
    )


class PlanningTests(unittest.IsolatedAsyncioTestCase):
    async def test_unseen_objective_runs_generated_sequence_and_validates_result(
        self,
    ) -> None:
        calls: list[tuple[str, str]] = []

        def search(query: str) -> str:
            calls.append(("search", query))
            return "doc-1"

        def read(record_id: str) -> str:
            calls.append(("read", record_id))
            return "source text"

        def draft(source: str, instruction: str) -> str:
            calls.append(("draft", instruction))
            return f"{instruction}: {source}"

        capabilities = (
            PlannerCapability(
                Tool(
                    "search",
                    "1.0.0",
                    "Search.",
                    search,
                    {"query": TaskInputBinding(("query",))},
                ),
                generated_parameters=("query",),
            ),
            PlannerCapability(
                Tool(
                    "read",
                    "1.0.0",
                    "Read.",
                    read,
                    {"record_id": TaskInputBinding(("record_id",))},
                )
            ),
            PlannerCapability(
                Tool(
                    "draft",
                    "1.0.0",
                    "Draft.",
                    draft,
                    {
                        "source": TaskInputBinding(("source",)),
                        "instruction": TaskInputBinding(("instruction",)),
                    },
                ),
                generated_parameters=("instruction",),
            ),
        )

        async def planner(request: Any) -> PlannerTurn:
            if not request.outcomes:
                return PlannerTurn(
                    PlanRevision(
                        (
                            PlanStep(
                                "find",
                                "search",
                                {
                                    "query": GeneratedText(
                                        "new objective query", "fixture", "1.0.0"
                                    )
                                },
                            ),
                            PlanStep(
                                "read",
                                "read",
                                {"record_id": StepValue("find")},
                                ("find",),
                            ),
                            PlanStep(
                                "draft",
                                "draft",
                                {
                                    "source": StepValue("read"),
                                    "instruction": GeneratedText(
                                        "compare", "fixture", "1.0.0"
                                    ),
                                },
                                ("read",),
                            ),
                        )
                    )
                )
            return PlannerTurn(ProposedResult(request.outcomes[-1].value))

        value = engine(planner, capabilities)
        result = await value.run(
            "Compare a newly requested source.",
            context("sequence", limits(planner_calls=2, revisions=1, tools=3)),
        )

        self.assertIs(result.status, TerminalStatus.COMPLETED)
        self.assertEqual(result.value, "compare: source text")
        self.assertEqual(
            calls,
            [
                ("search", "new objective query"),
                ("read", "doc-1"),
                ("draft", "compare"),
            ],
        )
        snapshot = await value.runtime.ledger.snapshot()  # type: ignore[union-attr]
        self.assertEqual(snapshot.planner_calls, 2)
        self.assertEqual(snapshot.plan_revisions, 1)
        self.assertEqual(snapshot.tool_attempts, 3)
        self.assertTrue(
            all(item.coverage is UsageCoverage.UNKNOWN for item in result.planner_usage)
        )

    async def test_failed_observation_causes_changed_bounded_proposal(self) -> None:
        calls: list[str] = []

        def retrieve(query: str) -> str:
            calls.append(query)
            if query == "bad":
                raise LookupError("offline miss")
            return "recovered"

        capability = PlannerCapability(
            Tool(
                "retrieve",
                "1.0.0",
                "Retrieve.",
                retrieve,
                {"query": TaskInputBinding(("query",))},
            ),
            generated_parameters=("query",),
        )

        def planner(request: Any) -> PlannerTurn:
            if not request.outcomes:
                query = "bad"
            elif request.outcomes[-1].status is TerminalStatus.FAILED:
                query = "good"
            else:
                return PlannerTurn(ProposedResult(request.outcomes[-1].value))
            return PlannerTurn(
                PlanStep(
                    f"retrieve-{query}",
                    "retrieve",
                    {"query": GeneratedText(query, "fixture", "1.0.0")},
                )
            )

        value = engine(planner, (capability,))
        result = await value.run("Recover from a miss.", context("replan", limits()))

        self.assertIs(result.status, TerminalStatus.COMPLETED)
        self.assertEqual(result.value, "recovered")
        self.assertEqual(calls, ["bad", "good"])
        self.assertEqual(len(result.outcomes), 2)

    async def test_invented_tool_and_source_are_rejected_without_dispatch(self) -> None:
        calls: list[str] = []

        def read(record_id: str) -> str:
            calls.append(record_id)
            return record_id

        capability = PlannerCapability(
            Tool(
                "read",
                "1.0.0",
                "Read.",
                read,
                {"record_id": TaskInputBinding(("record_id",))},
            )
        )
        turns = iter(
            (
                PlannerTurn(PlanStep("fake-tool", "os.system", {})),
                PlannerTurn(
                    PlanStep(
                        "fake-source",
                        "read",
                        {"record_id": EvidenceValue("invented-record")},
                    )
                ),
                PlannerTurn(PlannerHandoff("no valid source")),
            )
        )
        value = engine(lambda request: next(turns), (capability,))

        result = await value.run(
            "Reject fabricated identities.", context("invalid", limits())
        )

        self.assertIs(result.status, TerminalStatus.UNRESOLVED)
        self.assertIs(result.unresolved[0].reason, UnresolvedReason.MISSING_CAPABILITY)
        self.assertEqual(calls, [])
        self.assertEqual(len(result.outcomes), 2)

    async def test_unchanged_plan_and_unaccepted_result_stop_explicitly(self) -> None:
        calls: list[str] = []

        def draft(text: str) -> str:
            calls.append(text)
            return text

        capability = PlannerCapability(
            Tool(
                "draft", "1.0.0", "Draft.", draft, {"text": TaskInputBinding(("text",))}
            ),
            generated_parameters=("text",),
        )
        repeated = PlanStep(
            "draft", "draft", {"text": GeneratedText("same", "fixture", "1.0.0")}
        )
        value = engine(lambda request: PlannerTurn(repeated), (capability,))
        stalled = await value.run("Stop repetition.", context("repeat", limits()))
        self.assertIs(stalled.status, TerminalStatus.UNRESOLVED)
        self.assertIs(stalled.unresolved[0].reason, UnresolvedReason.NO_PROGRESS)
        self.assertEqual(calls, ["same"])

        turns = iter((PlannerTurn(repeated), PlannerTurn(ProposedResult("same"))))
        rejected_engine = engine(
            lambda request: next(turns),
            (capability,),
            validator=lambda value, store: False,
        )
        rejected = await rejected_engine.run(
            "Require host completion.", context("reject-result", limits())
        )
        self.assertIs(rejected.status, TerminalStatus.UNRESOLVED)
        self.assertIs(
            rejected.unresolved[0].reason, UnresolvedReason.UNACCEPTED_JUDGMENT
        )

    async def test_executing_specialist_is_dispatched_once(self) -> None:
        calls: list[str] = []

        @dataclass(frozen=True, slots=True)
        class ChildInput:
            value: str

        def execute(value: str) -> str:
            calls.append(value)
            return f"done:{value}"

        child_tool = Tool(
            "execute",
            "1.0.0",
            "Execute once.",
            execute,
            {"value": TaskInputBinding(("value",))},
            produces_evidence=("executed",),
        )
        child: AgentDefinition[ChildInput, str] = AgentDefinition(
            "executor",
            "1.0.0",
            "Execute the delegated subtask.",
            ChildInput,
            str,
            CompletionContract(("executed",), {}, "child"),
            OperatingPolicy("1.0.0", ("child",)),
            tools=(child_tool,),
        )
        shared = Runtime(
            ScriptedProvider(),
            model="offline",
            completion_checks={
                "step": lambda value, store: True,
                "child": lambda value, store: True,
            },
        )
        specialist_tool = shared.agent_as_tool(
            child,
            input_binding=TaskInputBinding(("inputs",)),
            output_evidence="specialist-output",
            policy=ChildRunPolicy("fixture"),
            tool_id="specialist",
        )
        capability = PlannerCapability(
            specialist_tool, fixed_arguments={"inputs": ChildInput("task")}
        )

        def planner(request: Any) -> PlannerTurn:
            if not request.outcomes:
                return PlannerTurn(PlanStep("delegate", "specialist", {}))
            return PlannerTurn(ProposedResult(request.outcomes[-1].value))

        value = engine(planner, (capability,), runtime=shared)
        result = await value.run(
            "Delegate one executing specialist.",
            context(
                "specialist-plan",
                limits(planner_calls=2, revisions=1, tools=1, children=1),
            ),
        )

        self.assertIs(result.status, TerminalStatus.COMPLETED)
        self.assertEqual(result.value, "done:task")
        self.assertEqual(calls, ["task"])
        snapshot = await shared.ledger.snapshot()  # type: ignore[union-attr]
        self.assertEqual(snapshot.child_runs, 1)
        self.assertEqual(snapshot.tool_attempts, 1)

    async def test_propose_select_filters_before_jev_and_handles_zero_survivors(
        self,
    ) -> None:
        provider = ScriptedProvider()
        client = DecisionClient(provider, model="offline")
        judgment = Judgment(
            "choose",
            "1.0.0",
            ChoiceQuestion("Choose the best valid proposal."),
            (Subject("objective"),),
            candidate_set="proposals",
        )
        decision_context = context("proposal", limits())
        alternatives = (
            ProposedAlternative("bad", "invented", "Invalid.", "fixture", "1.0.0"),
        )

        empty = await propose_select(
            client,
            judgment,
            alternatives,
            validate=lambda value: False,
            subjects={"objective": "choose"},
            evidence={},
            context=decision_context,
        )

        self.assertEqual(empty.rejected_keys, ("bad",))
        self.assertEqual(provider.calls, [])
        assert empty.selection.selection is not None
        self.assertIs(empty.selection.selection.outcome, CandidateOutcome.NO_FIT)

        valid = await propose_select(
            client,
            judgment,
            (ProposedAlternative("good", "supported", "Valid.", "fixture", "1.0.0"),),
            validate=lambda value: True,
            subjects={"objective": "choose"},
            evidence={},
            context=decision_context,
        )
        assert valid.selection.selection is not None
        assert valid.selection.selection.candidate is not None
        self.assertEqual(valid.selection.selection.candidate.key, "good")
        self.assertEqual(len(provider.calls), 1)


if __name__ == "__main__":
    unittest.main()
