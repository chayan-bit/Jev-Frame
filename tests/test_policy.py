import asyncio
import unittest
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, cast

from jev_frame import (
    AcceptancePolicy,
    AcceptanceStatus,
    AgentDefinition,
    AttemptAdmission,
    AttemptStatus,
    AuthorizationRecord,
    CompiledQuestion,
    CompletionContract,
    EvidenceSelector,
    EvidenceStore,
    ExecutionReceipt,
    ExecutionState,
    Judgment,
    JudgmentBinding,
    MutationContract,
    NoulAnswer,
    NoulQuestion,
    OperatingPolicy,
    ProviderAttempt,
    ProviderBatch,
    RequiredCheckpoint,
    RunContext,
    RunLimits,
    Runtime,
    SourceBinding,
    SourceField,
    Subject,
    TaskInputBinding,
    TerminalStatus,
    Tool,
    ToolEffect,
    UnresolvedReason,
    Usage,
    UsageCoverage,
    WriteRecord,
)


@dataclass(frozen=True, slots=True)
class RecordState:
    id: str
    value: str
    version: str


@dataclass(frozen=True, slots=True)
class UpdateRequest:
    record_id: str
    value: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class UpdateResult:
    receipt: ExecutionReceipt


class JudgmentProvider:
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
            if asyncio.iscoroutine(admitted):
                await admitted
        question = questions[0]
        return ProviderBatch(
            {question.routing_id: NoulAnswer(0.999)},
            requested_model,
            "scripted",
            operation_id,
            Usage(UsageCoverage.COMPLETE, 1, 1, 1, 1),
            (
                ProviderAttempt(
                    attempt.id,
                    1,
                    AttemptStatus.SUCCEEDED,
                    request_id=operation_id,
                ),
            ),
        )


class FakeService:
    def __init__(self, mode: str = "success") -> None:
        self.mode = mode
        self.state = RecordState("record-1", "old", "v1")
        self.calls = 0
        self.effects = 0
        self.receipts: dict[str, ExecutionReceipt] = {}
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    def read(self, record_id: str) -> RecordState:
        if record_id != self.state.id:
            raise KeyError(record_id)
        return self.state

    async def update(
        self,
        record_id: str,
        value: str,
        expected_version: str,
        idempotency_key: str,
        approval: NoulAnswer,
    ) -> ExecutionReceipt:
        self.calls += 1
        self.started.set()
        if self.mode == "block":
            await self.release.wait()
        if record_id != self.state.id or expected_version != self.state.version:
            return ExecutionReceipt(
                idempotency_key, ExecutionState.FAILED_BEFORE_EFFECT
            )
        self.effects += 1
        self.state = RecordState(record_id, value, f"v{self.effects + 1}")
        receipt = ExecutionReceipt(
            idempotency_key,
            ExecutionState.SUCCEEDED,
            f"effect-{self.effects}",
            self.state.version,
        )
        self.receipts[idempotency_key] = receipt
        if self.mode in {"lost", "inconclusive"}:
            raise TimeoutError("synthetic lost reply")
        if self.mode == "malformed":
            return "invalid"  # type: ignore[return-value]
        return receipt

    def reconcile(self, operation_id: str) -> ExecutionReceipt | None:
        if self.mode == "inconclusive":
            return None
        return self.receipts.get(operation_id)


class IntentStore:
    def __init__(self) -> None:
        self.history: list[WriteRecord] = []

    def record(self, value: WriteRecord) -> None:
        self.history.append(value)


class FakeAuthorizer:
    def __init__(
        self,
        *,
        allowed: bool = True,
        revoke_after_first: bool = False,
        after: Any = None,
    ) -> None:
        self.allowed = allowed
        self.revoke_after_first = revoke_after_first
        self.after = after
        self.proposals: list[Any] = []

    def authorize(self, proposal: Any, authority_context: Any) -> AuthorizationRecord:
        self.proposals.append(proposal)
        if self.after is not None:
            self.after()
        return AuthorizationRecord(
            proposal.digest,
            proposal.scope,
            self.allowed and not (self.revoke_after_first and len(self.proposals) > 1),
            100.0,
            ("fixture",),
        )


def definition(service: FakeService) -> AgentDefinition[UpdateRequest, UpdateResult]:
    read = Tool(
        "read_record",
        "1.0.0",
        "Read one versioned synthetic record.",
        service.read,
        {"record_id": TaskInputBinding(("record_id",))},
        effect=ToolEffect.READ,
        produces_evidence=("record_snapshot",),
    )
    approval = Judgment(
        "approve_update",
        "1.0.0",
        NoulQuestion("Is the requested update semantically acceptable?"),
        (Subject("value"),),
        evidence=(EvidenceSelector("record_snapshot"),),
        acceptance_policy="semantic",
    )
    update = Tool(
        "update_record",
        "1.0.0",
        "Update one synthetic record with a version precondition.",
        service.update,
        {
            "record_id": SourceBinding("record_snapshot", SourceField(("id",))),
            "value": TaskInputBinding(("value",)),
            "expected_version": SourceBinding(
                "record_snapshot", SourceField(("version",))
            ),
            "idempotency_key": TaskInputBinding(("idempotency_key",)),
            "approval": JudgmentBinding("approve_update"),
        },
        effect=ToolEffect.MUTATION,
        mutation=MutationContract(
            True,
            service.reconcile,
            True,
            "idempotency_key",
        ),
        requires_evidence=("record_snapshot",),
        produces_evidence=("update_receipt",),
    )
    return AgentDefinition(
        "update_agent",
        "1.0.0",
        "Apply one accepted and authorized synthetic update.",
        UpdateRequest,
        UpdateResult,
        CompletionContract(
            ("update_receipt",), {"receipt": "update_receipt"}, "completion"
        ),
        OperatingPolicy("1.0.0", ("semantic", "completion")),
        tools=(read, update),
        judgments=(approval,),
    )


def limits() -> RunLimits:
    return RunLimits(4, 4, 4, 0, 4, 1, 0, 0, 0, 0)


def runtime(
    service: FakeService,
    *,
    semantic: AcceptanceStatus = AcceptanceStatus.ACCEPT,
    authorizer: FakeAuthorizer | None = None,
    intent_store: IntentStore | None = None,
    checkpoint: RequiredCheckpoint | None = None,
) -> Runtime:
    return Runtime(
        JudgmentProvider(),
        model="scripted",
        completion_checks={"completion": lambda value, store: True},
        acceptance_policies={
            "semantic": AcceptancePolicy("semantic", "1.0.0", lambda value: semantic)
        },
        authorizer=FakeAuthorizer() if authorizer is None else authorizer,
        intent_store=IntentStore() if intent_store is None else intent_store,
        required_checkpoint=checkpoint,
    )


def context(*, store: EvidenceStore | None = None, run_id: str = "write") -> RunContext:
    return RunContext(
        "fixture",
        100.0,
        limits(),
        authority_context={"principal": "fixture"},
        evidence_session=store,
        clock=lambda: 0.0,
        run_id=run_id,
    )


class PolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_final_mutation_freshness_check_follows_awaited_gates(self) -> None:
        class SecondAuthorizationInvalidates(FakeAuthorizer):
            def __init__(self, store: EvidenceStore) -> None:
                super().__init__()
                self.store = store

            def authorize(
                self, proposal: Any, authority_context: Any
            ) -> AuthorizationRecord:
                result = super().authorize(proposal, authority_context)
                if len(self.proposals) == 2:
                    self.store.invalidate("record_snapshot")
                return result

        source_store = EvidenceStore(lambda: 0.0)
        source_service = FakeService()
        source_result = await runtime(
            source_service,
            authorizer=SecondAuthorizationInvalidates(source_store),
        ).run(
            definition(source_service),
            UpdateRequest("record-1", "new", "second-auth"),
            context(store=source_store, run_id="second-auth"),
        )

        self.assertIs(source_result.status, TerminalStatus.UNRESOLVED)
        self.assertIs(source_result.unresolved[0].reason, UnresolvedReason.STALE_SOURCE)
        self.assertEqual(source_service.calls, 0)

        persistence_store = EvidenceStore(lambda: 0.0)

        class InvalidateDuringPersistence:
            def __init__(self) -> None:
                self.history: list[WriteRecord] = []

            async def record(self, value: WriteRecord) -> None:
                self.history.append(value)
                if value.state is ExecutionState.IN_FLIGHT:
                    await asyncio.sleep(0)
                    persistence_store.invalidate("record_snapshot")

        persisted = InvalidateDuringPersistence()
        persistence_service = FakeService()
        persistence_result = await runtime(
            persistence_service, intent_store=cast(IntentStore, persisted)
        ).run(
            definition(persistence_service),
            UpdateRequest("record-1", "new", "persist-race"),
            context(store=persistence_store, run_id="persist-race"),
        )

        self.assertIs(persistence_result.status, TerminalStatus.UNRESOLVED)
        self.assertIs(
            persistence_result.unresolved[0].reason, UnresolvedReason.STALE_SOURCE
        )
        self.assertEqual(persistence_service.calls, 0)
        self.assertIs(persisted.history[-1].state, ExecutionState.FAILED_BEFORE_EFFECT)

        now = [0.0]

        class ExpiringAuthorizer(FakeAuthorizer):
            def authorize(
                self, proposal: Any, authority_context: Any
            ) -> AuthorizationRecord:
                self.proposals.append(proposal)
                return AuthorizationRecord(
                    proposal.digest, proposal.scope, True, 1.0, ("fixture",)
                )

        class ExpireDuringPersistence:
            def __init__(self) -> None:
                self.history: list[WriteRecord] = []

            async def record(self, value: WriteRecord) -> None:
                self.history.append(value)
                if value.state is ExecutionState.IN_FLIGHT:
                    await asyncio.sleep(0)
                    now[0] = 1.0

        expiring = ExpireDuringPersistence()
        expiry_service = FakeService()
        expiry_result = await runtime(
            expiry_service,
            authorizer=ExpiringAuthorizer(),
            intent_store=cast(IntentStore, expiring),
        ).run(
            definition(expiry_service),
            UpdateRequest("record-1", "new", "expiry-race"),
            replace(
                context(run_id="expiry-race"),
                deadline=10.0,
                clock=lambda: now[0],
            ),
        )

        self.assertIs(expiry_result.status, TerminalStatus.UNRESOLVED)
        self.assertIs(
            expiry_result.unresolved[0].reason, UnresolvedReason.PERMISSION_DENIAL
        )
        self.assertEqual(expiry_service.calls, 0)
        self.assertIs(expiring.history[-1].state, ExecutionState.FAILED_BEFORE_EFFECT)

    async def test_denied_authority_and_failed_acceptance_block_high_confidence(
        self,
    ) -> None:
        denied_service = FakeService()
        denied = await runtime(
            denied_service, authorizer=FakeAuthorizer(allowed=False)
        ).run(
            definition(denied_service),
            UpdateRequest("record-1", "new", "denied-key"),
            context(run_id="denied"),
        )
        self.assertIs(denied.status, TerminalStatus.UNRESOLVED)
        self.assertIs(denied.unresolved[0].reason, UnresolvedReason.PERMISSION_DENIAL)
        self.assertEqual(denied_service.calls, 0)

        revoked_service = FakeService()
        revoked = await runtime(
            revoked_service,
            authorizer=FakeAuthorizer(revoke_after_first=True),
        ).run(
            definition(revoked_service),
            UpdateRequest("record-1", "new", "revoked-key"),
            context(run_id="revoked"),
        )
        self.assertIs(revoked.status, TerminalStatus.UNRESOLVED)
        self.assertIs(revoked.unresolved[0].reason, UnresolvedReason.PERMISSION_DENIAL)
        self.assertEqual(revoked_service.calls, 0)

        rejected_service = FakeService()
        rejected = await runtime(
            rejected_service, semantic=AcceptanceStatus.REJECT
        ).run(
            definition(rejected_service),
            UpdateRequest("record-1", "new", "rejected-key"),
            context(run_id="rejected"),
        )
        self.assertIs(rejected.status, TerminalStatus.UNRESOLVED)
        self.assertIs(rejected.unresolved[0].reason, UnresolvedReason.REFUTED_CLAIM)
        self.assertEqual(rejected_service.calls, 0)

    async def test_stale_source_after_authorization_blocks_dispatch(self) -> None:
        service = FakeService()
        store = EvidenceStore(lambda: 0.0)
        authorizer = FakeAuthorizer(after=lambda: store.invalidate("record_snapshot"))

        result = await runtime(service, authorizer=authorizer).run(
            definition(service),
            UpdateRequest("record-1", "new", "stale-key"),
            context(store=store, run_id="stale-write"),
        )

        self.assertIs(result.status, TerminalStatus.UNRESOLVED)
        self.assertIs(result.unresolved[0].reason, UnresolvedReason.STALE_SOURCE)
        self.assertEqual(service.calls, 0)

    async def test_lost_or_malformed_reply_reconciles_without_retry(self) -> None:
        for mode in ("lost", "malformed"):
            with self.subTest(mode=mode):
                service = FakeService(mode)
                intents = IntentStore()

                result = await runtime(service, intent_store=intents).run(
                    definition(service),
                    UpdateRequest("record-1", "new", f"{mode}-key"),
                    context(run_id=f"{mode}-reply"),
                )

                self.assertIs(result.status, TerminalStatus.COMPLETED)
                self.assertEqual(service.calls, 1)
                self.assertEqual(service.effects, 1)
                self.assertIn(
                    ExecutionState.OUTCOME_UNKNOWN,
                    [item.state for item in intents.history],
                )
                self.assertIs(intents.history[-1].state, ExecutionState.SUCCEEDED)

    async def test_inconclusive_reconciliation_stops_without_retry(self) -> None:
        service = FakeService("inconclusive")
        intents = IntentStore()

        result = await runtime(service, intent_store=intents).run(
            definition(service),
            UpdateRequest("record-1", "new", "unknown-key"),
            context(run_id="unknown-write"),
        )

        self.assertIs(result.status, TerminalStatus.UNRESOLVED)
        self.assertIs(
            result.unresolved[0].reason, UnresolvedReason.UNKNOWN_WRITE_OUTCOME
        )
        self.assertEqual(service.calls, 1)
        self.assertEqual(service.effects, 1)
        self.assertIs(intents.history[-1].state, ExecutionState.OUTCOME_UNKNOWN)

    async def test_post_dispatch_cancellation_preserves_unknown_outcome(self) -> None:
        service = FakeService("block")
        intents = IntentStore()
        guarded = runtime(service, intent_store=intents)
        task = asyncio.create_task(
            guarded.run(
                definition(service),
                UpdateRequest("record-1", "new", "cancel-key"),
                context(run_id="cancel-write"),
            )
        )
        await service.started.wait()
        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertEqual(service.calls, 1)
        self.assertEqual(service.effects, 0)
        self.assertIs(intents.history[-1].state, ExecutionState.OUTCOME_UNKNOWN)
        cancelled = guarded.result_for("cancel-write")
        self.assertIs(cancelled.status, TerminalStatus.CANCELLED)  # type: ignore[union-attr]

    async def test_required_checkpoint_and_durable_intent_fail_closed(self) -> None:
        service = FakeService()
        failing = RequiredCheckpoint(
            "gate",
            "1.0.0",
            lambda proposal: (_ for _ in ()).throw(RuntimeError("fixture")),
        )
        gated = await runtime(service, checkpoint=failing).run(
            definition(service),
            UpdateRequest("record-1", "new", "gate-key"),
            context(run_id="gate-error"),
        )
        self.assertIs(gated.status, TerminalStatus.UNRESOLVED)
        self.assertIs(gated.unresolved[0].reason, UnresolvedReason.UNACCEPTED_JUDGMENT)
        self.assertEqual(service.calls, 0)

        no_intent = Runtime(
            JudgmentProvider(),
            model="scripted",
            completion_checks={"completion": lambda value, store: True},
            acceptance_policies={
                "semantic": AcceptancePolicy(
                    "semantic", "1.0.0", lambda value: AcceptanceStatus.ACCEPT
                )
            },
            authorizer=FakeAuthorizer(),
        )
        missing = await no_intent.run(
            definition(service),
            UpdateRequest("record-1", "new", "no-intent-key"),
            context(run_id="no-intent"),
        )
        self.assertIs(missing.status, TerminalStatus.UNRESOLVED)
        self.assertIs(missing.unresolved[0].reason, UnresolvedReason.PERMISSION_DENIAL)
        self.assertEqual(service.calls, 0)

    async def test_checkpoint_record_is_bound_to_exact_action_digest(self) -> None:
        checkpoint = RequiredCheckpoint(
            "gate", "1.0.0", lambda proposal: AcceptanceStatus.ACCEPT
        )
        service = FakeService()
        guarded = runtime(service, checkpoint=checkpoint)
        result = await guarded.run(
            definition(service),
            UpdateRequest("record-1", "new", "exact-key"),
            context(run_id="exact-action"),
        )

        self.assertIs(result.status, TerminalStatus.COMPLETED)
        proposal = guarded.intent_store.history[0].proposal  # type: ignore[union-attr]
        approval = await checkpoint.check(proposal)
        changed = type(proposal)(
            proposal.operation_id,
            proposal.tool_id,
            proposal.tool_version,
            {**proposal.arguments, "value": "changed"},
            proposal.scope,
            proposal.source_versions,
        )
        self.assertTrue(approval.accepts(proposal))
        self.assertFalse(approval.accepts(changed))


if __name__ == "__main__":
    unittest.main()
