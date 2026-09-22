import unittest
from typing import Any

from jev_frame import (
    CaptureAllowlist,
    CompiledQuestion,
    ConstantBinding,
    EvaluatorAnnotations,
    EventKind,
    EventLog,
    ExecutionReceipt,
    ExecutionState,
    FixtureError,
    FixtureGap,
    FixtureGapKind,
    FixtureInputMismatch,
    FixtureSource,
    IncompleteFixtureError,
    MutationContract,
    NoulAnswer,
    OfflineReplay,
    ProviderAttempt,
    ProviderBatch,
    RunLimits,
    Tool,
    ToolEffect,
    UnexpectedFixtureCall,
    Usage,
    UsageCoverage,
    capture_fixture,
    compare_findings,
    provider_fixture_call,
    reevaluate_fixture,
    tool_fixture_call,
)
from jev_frame.provider import AttemptStatus


def question() -> CompiledQuestion:
    return CompiledQuestion(
        routing_id="support:1.0.0",
        judgment_id="support",
        primitive="noul",
        instructions="Is the claim supported?",
        subjects=("claim",),
        evidence=(),
        dependencies=(),
        true_description=None,
        false_description=None,
    )


def batch() -> ProviderBatch:
    attempt = ProviderAttempt(
        "run-1:decision:1",
        1,
        AttemptStatus.SUCCEEDED,
        request_id="request-1",
    )
    return ProviderBatch(
        {"support:1.0.0": NoulAnswer(0.9)},
        "offline-model",
        "recorded-model",
        "request-1",
        Usage(UsageCoverage.COMPLETE, 3, 1, 1, 1),
        (attempt,),
    )


def limits() -> RunLimits:
    return RunLimits(2, 2, 2, 1, 2, 0, 0, 0, 0, 0)


class FixtureTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_is_allowlisted_and_labels_never_enter_manifest(self) -> None:
        log = EventLog()
        event = log.emit(
            EventKind.OPERATION_FAILED,
            run_id="run-1",
            correlation_id="correlation-1",
            operation_id="decision-1",
            reason_code="provider_failure",
            data={
                "definition_id": "support",
                "question_id": "support:1.0.0",
                "diagnostic": {"code": "provider_failure"},
            },
        )
        selected = FixtureSource(
            "claim-source", "document-1", "v1", {"claim": "safe"}, True
        )
        private = FixtureSource(
            "private-source", "vault", "v1", {"token": "SECRET_TOKEN"}, True
        )
        provider_call = provider_fixture_call(
            "provider-1",
            state={"claim": "safe"},
            questions=(question(),),
            requested_model="offline-model",
            operation_id="decision-1",
            batch=batch(),
            source_aliases=("claim-source",),
        )
        fixture = capture_fixture(
            fixture_id="JF-H-capture-failure-v1",
            run_id="run-1",
            events=(event,),
            calls=(provider_call,),
            sources=(selected, private),
            allowlist=CaptureAllowlist(
                frozenset({1}),
                frozenset({"provider-1"}),
                frozenset({"claim-source"}),
            ),
        )
        labels = EvaluatorAnnotations(
            fixture.id, {"expected": "EXPECTED_LABEL"}, ("evaluator only",)
        )

        serialized = fixture.to_json()
        self.assertTrue(fixture.complete)
        self.assertNotIn("SECRET_TOKEN", serialized)
        self.assertNotIn("private-source", serialized)
        self.assertNotIn("EXPECTED_LABEL", serialized)
        self.assertEqual(labels.expected_outcome["expected"], "EXPECTED_LABEL")
        self.assertEqual(
            fixture,
            fixture.from_json(serialized),
        )

    async def test_provider_replay_is_deterministic_and_fails_closed(self) -> None:
        state = {"claim": "safe"}
        call = provider_fixture_call(
            "provider-1",
            state=state,
            questions=(question(),),
            requested_model="offline-model",
            operation_id="decision-1",
            batch=batch(),
        )
        fixture = capture_fixture(
            fixture_id="JF-H-provider-replay-v1",
            run_id="run-1",
            calls=(call,),
            allowlist=CaptureAllowlist(call_aliases=frozenset({call.alias})),
        )
        admitted: list[str] = []
        replay = OfflineReplay(fixture)
        result = await replay.provider.evaluate(
            state=state,
            questions=(question(),),
            requested_model="offline-model",
            operation_id="decision-1",
            admit_attempt=lambda attempt: admitted.append(attempt.id),
        )

        self.assertEqual(result, batch())
        self.assertEqual(admitted, ["run-1:decision:1"])
        replay.finish()
        with self.assertRaises(UnexpectedFixtureCall):
            await replay.provider.evaluate(
                state=state,
                questions=(question(),),
                requested_model="offline-model",
                operation_id="decision-1",
            )

        mismatch = OfflineReplay(fixture)
        with self.assertRaises(FixtureInputMismatch):
            await mismatch.provider.evaluate(
                state={"claim": "changed"},
                questions=(question(),),
                requested_model="offline-model",
                operation_id="decision-1",
            )

    async def test_incomplete_evidence_and_unknown_versions_are_rejected(self) -> None:
        fixture = capture_fixture(
            fixture_id="JF-H-incomplete-v1",
            run_id="run-1",
            sources=(FixtureSource("claim-source", "document-1", "v1"),),
            allowlist=CaptureAllowlist(
                source_aliases=frozenset({"claim-source"})
            ),
            required_source_aliases=("claim-source",),
            gaps=(
                FixtureGap(
                    "sources.claim-source.snapshot",
                    FixtureGapKind.REDACTED,
                    "sensitive_value",
                    True,
                ),
            ),
        )
        self.assertFalse(fixture.complete)
        with self.assertRaises(IncompleteFixtureError):
            OfflineReplay(fixture)

        payload = fixture.to_dict()
        payload["schema_version"] = "jev-frame.regression-fixture.v999"
        with self.assertRaises(FixtureError):
            fixture.from_dict(payload)

    async def test_mutation_replay_returns_receipt_without_original_effect(self) -> None:
        invoked = 0

        async def write_record(value: str, operation_id: str) -> ExecutionReceipt:
            nonlocal invoked
            invoked += 1
            return ExecutionReceipt(operation_id, ExecutionState.SUCCEEDED, value)

        tool = Tool(
            "write-record",
            "1.0.0",
            "Write one synthetic record.",
            write_record,
            {
                "value": ConstantBinding("record-1"),
                "operation_id": ConstantBinding("write-1"),
            },
            effect=ToolEffect.MUTATION,
            mutation=MutationContract(
                True,
                durable_intent_required=False,
                idempotency_parameter="operation_id",
            ),
        )
        arguments = {"value": "record-1", "operation_id": "write-1"}
        receipt = ExecutionReceipt(
            "write-1", ExecutionState.SUCCEEDED, "external-1", "v2"
        )
        call = tool_fixture_call(
            "tool-1",
            tool,
            arguments,
            operation_id="write-1",
            scripted_result=receipt,
        )
        fixture = capture_fixture(
            fixture_id="JF-H-mutation-replay-v1",
            run_id="run-1",
            calls=(call,),
            allowlist=CaptureAllowlist(call_aliases=frozenset({call.alias})),
        )
        replay = OfflineReplay(fixture)
        double = replay.tool_double(tool)

        result = await double.function(**arguments)

        self.assertEqual(result, receipt)
        self.assertEqual(invoked, 0)
        self.assertIs(double.effect, ToolEffect.MUTATION)
        replay.finish()
        with self.assertRaises(UnexpectedFixtureCall):
            await double.function(**arguments)

    async def test_finding_diff_and_reevaluation_are_explicitly_separate(self) -> None:
        fixture = capture_fixture(
            fixture_id="JF-H-reevaluation-v1",
            run_id="run-1",
            allowlist=CaptureAllowlist(),
        )
        observed: list[Any] = []

        def fresh(request: Any) -> str:
            observed.append(request)
            return "fresh-result"

        result = await reevaluate_fixture(
            fixture,
            model="new-model",
            policy_version="policy:package:2.0.0",
            limits=limits(),
            operation=fresh,
        )
        differences = compare_findings(
            {"status": "failed", "kept": 1},
            {"status": "completed", "kept": 1},
        )

        self.assertEqual(result, "fresh-result")
        self.assertEqual(observed[0].model, "new-model")
        self.assertEqual(observed[0].policy_version, "policy:package:2.0.0")
        self.assertEqual([difference.key for difference in differences], ["status"])
        self.assertEqual(OfflineReplay(fixture).remaining_calls, ())


if __name__ == "__main__":
    unittest.main()
