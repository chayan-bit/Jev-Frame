import asyncio
import inspect
import time
import unittest
from collections.abc import Sequence
from dataclasses import dataclass, replace
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
    ConstantBinding,
    DecisionClient,
    EvidenceStore,
    EvidenceValue,
    GeneratedText,
    Judgment,
    Observation,
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


def context(identifier: str | None, run_limits: RunLimits) -> RunContext:
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
    async def test_fixed_arguments_cannot_be_overridden_by_planner_values(self) -> None:
        calls: list[tuple[str, str]] = []

        def read(account: str, query: str) -> str:
            calls.append((account, query))
            return f"{account}:{query}"

        capability = PlannerCapability(
            Tool(
                "read",
                "1.0.0",
                "Read from one fixed account.",
                read,
                {
                    "account": ConstantBinding("account-a"),
                    "query": TaskInputBinding(("query",)),
                },
            ),
            generated_parameters=("query",),
            fixed_arguments={"account": "account-a"},
        )
        store = EvidenceStore(lambda: 0.0)
        store.add(
            Observation(
                id="other-account",
                value="account-b",
                source_id="fixture",
                scope="fixture",
                observed_at=0.0,
            )
        )
        variants: tuple[EvidenceValue | GeneratedText | StepValue, ...] = (
            EvidenceValue("other-account"),
            GeneratedText("account-b", "fixture", "1.0.0"),
            StepValue("seed"),
        )
        for index, argument in enumerate(variants):
            steps = (
                (
                    PlanStep(
                        "seed",
                        "read",
                        {"query": GeneratedText("seed", "fixture", "1.0.0")},
                    ),
                    PlanStep(
                        "override",
                        "read",
                        {
                            "account": argument,
                            "query": GeneratedText("query", "fixture", "1.0.0"),
                        },
                        ("seed",) if isinstance(argument, StepValue) else (),
                    ),
                )
                if isinstance(argument, StepValue)
                else (
                    PlanStep(
                        "override",
                        "read",
                        {
                            "account": argument,
                            "query": GeneratedText("query", "fixture", "1.0.0"),
                        },
                    ),
                )
            )
            turns = iter(
                (
                    PlannerTurn(PlanRevision(steps)),
                    PlannerTurn(PlannerHandoff("invalid override")),
                )
            )
            result = await engine(
                lambda request, script=turns: next(script), (capability,)
            ).run(
                "Keep the host account fixed.",
                replace(
                    context(f"fixed-{index}", limits()), evidence_session=store
                ),
            )
            self.assertIs(result.status, TerminalStatus.UNRESOLVED)

        self.assertEqual(calls, [])

        def valid_planner(request: Any) -> PlannerTurn:
            if request.outcomes:
                return PlannerTurn(ProposedResult(request.outcomes[-1].value))
            return PlannerTurn(
                PlanStep(
                    "valid",
                    "read",
                    {"query": GeneratedText("query", "fixture", "1.0.0")},
                )
            )

        valid = await engine(valid_planner, (capability,)).run(
            "Use the fixed account.", context("fixed-valid", limits())
        )
        self.assertIs(valid.status, TerminalStatus.COMPLETED)
        self.assertEqual(calls, [("account-a", "query")])

    async def test_planner_and_validator_callbacks_obey_run_deadline(self) -> None:
        async def late_planner(request: Any) -> PlannerTurn:
            await asyncio.sleep(0.05)
            return PlannerTurn(ProposedResult("late"))

        deadline = time.monotonic() + 0.01
        late = await engine(late_planner, ()).run(
            "Do not accept late output.",
            RunContext(
                "fixture",
                deadline,
                limits(planner_calls=1, revisions=0, tools=0),
                clock=time.monotonic,
                run_id="late-planner",
            ),
        )
        self.assertIs(late.status, TerminalStatus.UNRESOLVED)
        self.assertIs(late.unresolved[0].reason, UnresolvedReason.BUDGET_EXHAUSTION)

        async def stalled_planner(request: Any) -> PlannerTurn:
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        stalled = await asyncio.wait_for(
            engine(stalled_planner, ()).run(
                "Bound a stalled planner.",
                RunContext(
                    "fixture",
                    time.monotonic() + 0.01,
                    limits(planner_calls=1, revisions=0, tools=0),
                    clock=time.monotonic,
                    run_id="stalled-planner",
                ),
            ),
            0.2,
        )
        self.assertIs(stalled.status, TerminalStatus.UNRESOLVED)

        async def stalled_validator(value: Any, store: EvidenceStore) -> bool:
            await asyncio.Event().wait()
            return True

        validated = await asyncio.wait_for(
            engine(
                lambda request: PlannerTurn(ProposedResult("candidate")),
                (),
                validator=stalled_validator,
            ).run(
                "Bound a stalled validator.",
                RunContext(
                    "fixture",
                    time.monotonic() + 0.01,
                    limits(planner_calls=1, revisions=0, tools=0),
                    clock=time.monotonic,
                    run_id="stalled-validator",
                ),
            ),
            0.2,
        )
        self.assertIs(validated.status, TerminalStatus.UNRESOLVED)

        now = [0.0]
        calls: list[str] = []

        def tool(value: str) -> str:
            calls.append(value)
            return value

        capability = PlannerCapability(
            Tool(
                "tool",
                "1.0.0",
                "Must not start after expiry.",
                tool,
                {"value": TaskInputBinding(("value",))},
            ),
            generated_parameters=("value",),
        )

        def expires(request: Any) -> PlannerTurn:
            now[0] = 2.0
            return PlannerTurn(
                PlanStep(
                    "late-step",
                    "tool",
                    {"value": GeneratedText("late", "fixture", "1.0.0")},
                )
            )

        expired = await engine(expires, (capability,)).run(
            "Do not start expired work.",
            RunContext(
                "fixture",
                1.0,
                limits(planner_calls=1, revisions=1, tools=1),
                clock=lambda: now[0],
                run_id="expired-step",
            ),
        )
        self.assertIs(expired.status, TerminalStatus.UNRESOLVED)
        self.assertEqual(calls, [])

        planner_started = asyncio.Event()

        async def cancellable(request: Any) -> PlannerTurn:
            planner_started.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        cancelled_task = asyncio.create_task(
            engine(cancellable, ()).run(
                "Propagate cancellation.",
                RunContext(
                    "fixture",
                    time.monotonic() + 10.0,
                    limits(planner_calls=1, revisions=0, tools=0),
                    clock=time.monotonic,
                    run_id="cancel-planner",
                ),
            )
        )
        await planner_started.wait()
        cancelled_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await cancelled_task

    async def test_effective_run_identity_is_unique_and_cross_turn_uses_evidence(
        self,
    ) -> None:
        calls: list[str] = []

        def draft(text: str) -> str:
            calls.append(text)
            return text

        capability = PlannerCapability(
            Tool(
                "draft",
                "1.0.0",
                "Draft text.",
                draft,
                {"text": TaskInputBinding(("text",))},
            ),
            generated_parameters=("text",),
        )

        def planner(request: Any) -> PlannerTurn:
            if request.outcomes:
                return PlannerTurn(ProposedResult(request.outcomes[-1].value))
            return PlannerTurn(
                PlanStep(
                    "draft",
                    "draft",
                    {
                        "text": GeneratedText(
                            request.objective, "fixture", "1.0.0"
                        )
                    },
                )
            )

        shared = Runtime(
            ScriptedProvider(),
            model="offline",
            completion_checks={"step": lambda value, store: True},
        )
        value = engine(planner, (capability,), runtime=shared)
        run_limits = limits(planner_calls=8, revisions=4, tools=4)
        store = EvidenceStore(lambda: 0.0)
        results = (
            await value.run(
                "implicit-one",
                replace(context(None, run_limits), evidence_session=store),
            ),
            await value.run(
                "implicit-two",
                replace(context(None, run_limits), evidence_session=store),
            ),
            await value.run("explicit-one", context("explicit-a", run_limits)),
            await value.run("explicit-two", context("explicit-b", run_limits)),
        )

        self.assertTrue(
            all(result.status is TerminalStatus.COMPLETED for result in results)
        )
        self.assertEqual(
            calls, ["implicit-one", "implicit-two", "explicit-one", "explicit-two"]
        )
        implicit_refs = tuple(
            result.outcomes[0].evidence_ref for result in results[:2]
        )
        self.assertEqual(len(set(implicit_refs)), 2)
        self.assertEqual(len(store.records), 2)

        sequence_calls: list[str] = []

        def find(query: str) -> str:
            sequence_calls.append("find")
            return "doc-1"

        def read(record_id: str) -> str:
            sequence_calls.append("read")
            return f"source:{record_id}"

        capabilities = (
            PlannerCapability(
                Tool(
                    "find",
                    "1.0.0",
                    "Find.",
                    find,
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
        )

        def continued(request: Any) -> PlannerTurn:
            if not request.outcomes:
                return PlannerTurn(
                    PlanStep(
                        "find",
                        "find",
                        {"query": GeneratedText("query", "fixture", "1.0.0")},
                    )
                )
            if len(request.outcomes) == 1:
                reference = request.outcomes[0].evidence_ref
                assert reference is not None
                return PlannerTurn(
                    PlanStep(
                        "read",
                        "read",
                        {"record_id": EvidenceValue(reference)},
                    )
                )
            return PlannerTurn(ProposedResult(request.outcomes[-1].value))

        continued_result = await engine(continued, capabilities).run(
            "Find then read across turns.",
            context("continued", limits(planner_calls=3, revisions=2, tools=2)),
        )
        self.assertIs(continued_result.status, TerminalStatus.COMPLETED)
        self.assertEqual(continued_result.value, "source:doc-1")
        self.assertEqual(sequence_calls, ["find", "read"])

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
