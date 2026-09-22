import asyncio
import unittest
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from jev_frame import (
    AgentDefinition,
    AuthorizationRecord,
    ChildRunPolicy,
    CompiledQuestion,
    CompletionContract,
    EvidenceStore,
    ExecutionReceipt,
    ExecutionReference,
    ExecutionState,
    MutationContract,
    OperatingPolicy,
    RunContext,
    RunLimits,
    Runtime,
    RuntimeConfigurationError,
    TaskInputBinding,
    TerminalStatus,
    Tool,
    ToolEffect,
    UnresolvedReason,
)


class UnexpectedProvider:
    async def evaluate(
        self,
        *,
        state: Any,
        questions: Sequence[CompiledQuestion],
        requested_model: str,
        operation_id: str,
        timeout: float | None = None,
        admit_attempt: Any = None,
    ) -> Any:
        raise AssertionError("composition fixture must not call a provider")


@dataclass(frozen=True, slots=True)
class SpecialistRequest:
    topic: str


@dataclass(frozen=True, slots=True)
class ParentRequest:
    left: SpecialistRequest
    right: SpecialistRequest


@dataclass(frozen=True, slots=True)
class CombinedResult:
    left: str
    right: str


@dataclass(frozen=True, slots=True)
class MutationRequest:
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class MutationParentRequest:
    child: MutationRequest


@dataclass(frozen=True, slots=True)
class MutationResult:
    receipt: ExecutionReceipt


@dataclass(frozen=True, slots=True)
class MutationParentResult:
    child: MutationResult


class AllowAuthorizer:
    def __init__(self) -> None:
        self.contexts: list[Any] = []

    def authorize(self, proposal: Any, authority_context: Any) -> AuthorizationRecord:
        self.contexts.append(authority_context)
        return AuthorizationRecord(proposal.digest, proposal.scope, True, 100.0)


def specialist(
    identifier: str,
    answer: str,
    calls: list[str],
    *,
    started: asyncio.Event | None = None,
    cancelled: asyncio.Event | None = None,
) -> AgentDefinition[SpecialistRequest, str]:
    async def inspect_topic(topic: str) -> str:
        calls.append(identifier)
        if started is not None:
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                assert cancelled is not None
                cancelled.set()
                raise
        return f"{answer}:{topic}"

    tool = Tool(
        f"{identifier}_inspect",
        "1.0.0",
        f"Inspect a topic as {identifier}.",
        inspect_topic,
        {"topic": TaskInputBinding(("topic",))},
        produces_evidence=(f"{identifier}_finding",),
    )
    return AgentDefinition(
        identifier,
        "1.0.0",
        f"Return the {identifier} finding.",
        SpecialistRequest,
        str,
        CompletionContract((f"{identifier}_finding",), {}, "child-complete"),
        OperatingPolicy("1.0.0", ("child-complete",)),
        tools=(tool,),
    )


def mutation_specialist(
    started: asyncio.Event,
    cancelled: asyncio.Event,
) -> AgentDefinition[MutationRequest, MutationResult]:
    async def mutate(idempotency_key: str) -> ExecutionReceipt:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        raise AssertionError("mutation fixture unexpectedly resumed")

    tool = Tool(
        "child_mutation",
        "1.0.0",
        "Run one cancellable synthetic mutation.",
        mutate,
        {"idempotency_key": TaskInputBinding(("idempotency_key",))},
        effect=ToolEffect.MUTATION,
        mutation=MutationContract(True, None, False, "idempotency_key"),
        produces_evidence=("mutation_receipt",),
    )
    return AgentDefinition(
        "mutation-child",
        "1.0.0",
        "Exercise cancellation of an admitted child effect.",
        MutationRequest,
        MutationResult,
        CompletionContract(
            ("mutation_receipt",),
            {"receipt": "mutation_receipt"},
            "child-complete",
        ),
        OperatingPolicy("1.0.0", ("child-complete",)),
        tools=(tool,),
    )


def parent_definition(
    runtime: Runtime,
    left: AgentDefinition[SpecialistRequest, str],
    right: AgentDefinition[SpecialistRequest, str],
    *,
    left_policy: ChildRunPolicy | None = None,
    right_policy: ChildRunPolicy | None = None,
    identifier: str = "parent",
) -> AgentDefinition[ParentRequest, CombinedResult]:
    policy = ChildRunPolicy("fixture")
    left_tool = runtime.agent_as_tool(
        left,
        input_binding=TaskInputBinding(("left",)),
        output_evidence="left",
        policy=left_policy or policy,
        tool_id="left_specialist",
    )
    right_tool = runtime.agent_as_tool(
        right,
        input_binding=TaskInputBinding(("right",)),
        output_evidence="right",
        policy=right_policy or policy,
        tool_id="right_specialist",
    )
    return AgentDefinition(
        identifier,
        "1.0.0",
        "Retain both specialist findings.",
        ParentRequest,
        CombinedResult,
        CompletionContract(
            ("left", "right"),
            {"left": "left", "right": "right"},
            "parent-complete",
        ),
        OperatingPolicy("1.0.0", ("parent-complete",)),
        tools=(left_tool, right_tool),
    )


def limits(
    *,
    tool_attempts: int = 2,
    concurrency: int = 1,
    child_depth: int = 1,
    child_runs: int = 2,
    writes: int = 0,
) -> RunLimits:
    return RunLimits(
        0,
        0,
        tool_attempts,
        0,
        concurrency,
        writes,
        0,
        0,
        child_depth,
        child_runs,
    )


def context(
    run_id: str,
    run_limits: RunLimits,
    *,
    store: EvidenceStore | None = None,
    authority: Any = None,
) -> RunContext:
    return RunContext(
        "fixture",
        100.0,
        run_limits,
        authority_context=authority,
        clock=lambda: 0.0,
        evidence_session=store,
        run_id=run_id,
    )


def runtime(*, accept_parent: bool = True, accept_child: bool = True) -> Runtime:
    return Runtime(
        UnexpectedProvider(),
        model="unused",
        completion_checks={
            "child-complete": lambda value, store: accept_child,
            "parent-complete": lambda value, store: accept_parent,
        },
    )


class CompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_conflicting_children_share_one_slot_and_one_ledger(self) -> None:
        calls: list[str] = []
        value = runtime()
        definition = parent_definition(
            value,
            specialist("left", "supports", calls),
            specialist("right", "refutes", calls),
        )
        store = EvidenceStore(lambda: 0.0)

        result = await value.run(
            definition,
            ParentRequest(SpecialistRequest("claim"), SpecialistRequest("claim")),
            context("parent-run", limits(), store=store, authority={"role": "reader"}),
        )

        self.assertIs(result.status, TerminalStatus.COMPLETED)
        self.assertEqual(
            result.value,
            CombinedResult("supports:claim", "refutes:claim"),
        )
        self.assertCountEqual(calls, ["left", "right"])
        self.assertEqual(len(store.get("left").dependencies), 1)
        self.assertEqual(len(store.get("right").dependencies), 1)
        self.assertIn(
            ":child:left_specialist:evidence:", store.get("left").dependencies[0]
        )
        self.assertIn(
            ":child:right_specialist:evidence:", store.get("right").dependencies[0]
        )
        snapshot = await value.ledger.snapshot()  # type: ignore[union-attr]
        self.assertEqual(snapshot.child_runs, 2)
        self.assertEqual(snapshot.max_child_depth, 1)
        self.assertEqual(snapshot.tool_attempts, 2)
        self.assertEqual(snapshot.active_operations, 0)
        self.assertEqual(len(snapshot.tool_attempt_ids), 2)

    async def test_parent_policy_still_decides_completion(self) -> None:
        calls: list[str] = []
        value = runtime(accept_parent=False)
        definition = parent_definition(
            value,
            specialist("left", "supports", calls),
            specialist("right", "supports", calls),
        )

        result = await value.run(
            definition,
            ParentRequest(SpecialistRequest("claim"), SpecialistRequest("claim")),
            context("policy-run", limits()),
        )

        self.assertIs(result.status, TerminalStatus.UNRESOLVED)
        self.assertIs(result.unresolved[0].reason, UnresolvedReason.UNACCEPTED_JUDGMENT)
        self.assertCountEqual(calls, ["left", "right"])

    async def test_unresolved_child_findings_keep_their_evidence(self) -> None:
        calls: list[str] = []
        value = runtime(accept_child=False)
        definition = parent_definition(
            value,
            specialist("left", "supports", calls),
            specialist("right", "refutes", calls),
        )
        store = EvidenceStore(lambda: 0.0)

        result = await value.run(
            definition,
            ParentRequest(SpecialistRequest("claim"), SpecialistRequest("claim")),
            context("unresolved-run", limits(), store=store),
        )

        self.assertIs(result.status, TerminalStatus.UNRESOLVED)
        self.assertIn("supports:claim", result.partial_findings)
        self.assertIn("refutes:claim", result.partial_findings)
        imported = [
            record
            for record in store.records
            if ":child:" in record.id and ":evidence:" in record.id
        ]
        self.assertEqual(len(imported), 2)
        self.assertEqual(
            {record.source_id for record in imported},
            {
                "tool:left_inspect",
                "tool:right_inspect",
            },
        )

    async def test_scope_and_evidence_widening_fail_before_child_access(self) -> None:
        calls: list[str] = []
        value = runtime()
        left = specialist("left", "supports", calls)
        right = specialist("right", "refutes", calls)
        definition = parent_definition(
            value,
            left,
            right,
            left_policy=ChildRunPolicy("other-scope"),
        )

        result = await value.run(
            definition,
            ParentRequest(SpecialistRequest("claim"), SpecialistRequest("claim")),
            context("scope-run", limits()),
        )

        self.assertIs(result.status, TerminalStatus.UNRESOLVED)
        self.assertIs(result.unresolved[0].reason, UnresolvedReason.PERMISSION_DENIAL)
        self.assertNotIn("left", calls)

        with self.assertRaises(RuntimeConfigurationError):
            ChildRunPolicy(
                "fixture",
                export_evidence=("public",),
                read_evidence=("private",),
            )

    async def test_cycle_depth_and_count_limits_are_visible(self) -> None:
        calls: list[str] = []
        value = runtime()
        base = specialist("cycle", "unused", calls)
        cycle_tool = value.agent_as_tool(
            base,
            input_binding=TaskInputBinding(("left",)),
            output_evidence="left",
            policy=ChildRunPolicy("fixture"),
            tool_id="cycle_specialist",
        )
        cycle_parent: AgentDefinition[ParentRequest, str] = AgentDefinition(
            "cycle",
            "1.0.0",
            "Reject recursive re-entry.",
            ParentRequest,
            str,
            CompletionContract(("left",), {}, "parent-complete"),
            OperatingPolicy("1.0.0", ("parent-complete",)),
            tools=(cycle_tool,),
        )
        request = ParentRequest(SpecialistRequest("claim"), SpecialistRequest("claim"))

        cycled = await value.run(
            cycle_parent, request, context("cycle-run", limits(child_runs=1))
        )

        self.assertIs(cycled.status, TerminalStatus.UNRESOLVED)
        self.assertIs(cycled.unresolved[0].reason, UnresolvedReason.NO_PROGRESS)
        self.assertEqual(calls, [])

        depth_runtime = runtime()
        depth_parent = parent_definition(
            depth_runtime,
            specialist("left", "supports", calls),
            specialist("right", "refutes", calls),
        )
        depth = await depth_runtime.run(
            depth_parent,
            request,
            context(
                "depth-run",
                limits(child_depth=0, child_runs=2),
            ),
        )
        self.assertIs(depth.status, TerminalStatus.UNRESOLVED)
        self.assertIs(depth.unresolved[0].reason, UnresolvedReason.BUDGET_EXHAUSTION)

        count_calls: list[str] = []
        count_runtime = runtime()
        count_parent = parent_definition(
            count_runtime,
            specialist("left", "supports", count_calls),
            specialist("right", "refutes", count_calls),
        )
        count = await count_runtime.run(
            count_parent,
            request,
            context("count-run", limits(child_runs=1)),
        )
        self.assertIs(count.status, TerminalStatus.UNRESOLVED)
        self.assertIs(count.unresolved[0].reason, UnresolvedReason.BUDGET_EXHAUSTION)
        count_snapshot = await count_runtime.ledger.snapshot()  # type: ignore[union-attr]
        self.assertEqual(count_snapshot.child_runs, 1)
        self.assertEqual(len(count_calls), 1)

    async def test_parent_cancellation_reaches_child_work(self) -> None:
        started = asyncio.Event()
        cancelled = asyncio.Event()
        calls: list[str] = []
        value = runtime()
        definition = parent_definition(
            value,
            specialist(
                "left",
                "supports",
                calls,
                started=started,
                cancelled=cancelled,
            ),
            specialist("right", "refutes", calls),
        )
        store = EvidenceStore(lambda: 0.0)
        task = asyncio.create_task(
            value.run(
                definition,
                ParentRequest(SpecialistRequest("claim"), SpecialistRequest("claim")),
                context("cancel-run", limits(), store=store),
            )
        )
        await started.wait()

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertTrue(cancelled.is_set())
        child_result = value.result_for("cancel-run:child:left_specialist")
        self.assertIsNotNone(child_result)
        assert child_result is not None
        self.assertIs(child_result.status, TerminalStatus.CANCELLED)
        parent_result = value.result_for("cancel-run")
        self.assertIsNotNone(parent_result)
        assert parent_result is not None
        self.assertIs(parent_result.status, TerminalStatus.CANCELLED)
        snapshot = await value.ledger.snapshot()  # type: ignore[union-attr]
        self.assertEqual(snapshot.active_operations, 0)
        self.assertLessEqual(snapshot.child_runs, 2)

    async def test_cancelled_child_effect_remains_unknown_in_parent_evidence(
        self,
    ) -> None:
        started = asyncio.Event()
        cancelled = asyncio.Event()
        authorizer = AllowAuthorizer()
        authority = {"role": "writer"}
        value = Runtime(
            UnexpectedProvider(),
            model="unused",
            completion_checks={
                "child-complete": lambda result, store: True,
                "parent-complete": lambda result, store: True,
            },
            authorizer=authorizer,
        )
        child = mutation_specialist(started, cancelled)
        child_tool = value.agent_as_tool(
            child,
            input_binding=TaskInputBinding(("child",)),
            output_evidence="child_receipt",
            policy=ChildRunPolicy("fixture"),
            tool_id="mutation_specialist",
        )
        parent: AgentDefinition[MutationParentRequest, MutationParentResult] = (
            AgentDefinition(
                "mutation-parent",
                "1.0.0",
                "Retain the child mutation receipt.",
                MutationParentRequest,
                MutationParentResult,
                CompletionContract(
                    ("child_receipt",),
                    {"child": "child_receipt"},
                    "parent-complete",
                ),
                OperatingPolicy("1.0.0", ("parent-complete",)),
                tools=(child_tool,),
            )
        )
        store = EvidenceStore(lambda: 0.0)
        task = asyncio.create_task(
            value.run(
                parent,
                MutationParentRequest(MutationRequest("mutation-1")),
                context(
                    "mutation-parent-run",
                    limits(
                        tool_attempts=1,
                        child_runs=1,
                        writes=1,
                    ),
                    store=store,
                    authority=authority,
                ),
            )
        )
        start_wait = asyncio.create_task(started.wait())
        done, _ = await asyncio.wait(
            (task, start_wait), timeout=2.0, return_when=asyncio.FIRST_COMPLETED
        )
        if task in done:
            self.fail(f"mutation child ended before dispatch: {task.result()!r}")
        if start_wait not in done:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.fail("mutation child did not reach dispatch")

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertTrue(cancelled.is_set())
        self.assertTrue(authorizer.contexts)
        self.assertTrue(all(item is authority for item in authorizer.contexts))
        imported = [
            record for record in store.records if isinstance(record, ExecutionReference)
        ]
        self.assertEqual(len(imported), 1)
        self.assertIs(imported[0].state, ExecutionState.OUTCOME_UNKNOWN)


if __name__ == "__main__":
    unittest.main()
