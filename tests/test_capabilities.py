import asyncio
import unittest
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Any

from jev_frame import (
    AgentDefinition,
    CapabilityCatalog,
    CapabilityImportError,
    CompiledQuestion,
    CompletionContract,
    Coverage,
    EvidenceStore,
    ForeignToolDescriptor,
    ImportedToolSemantics,
    InputValidationError,
    OperatingPolicy,
    RunContext,
    RunLimits,
    Runtime,
    ScopeError,
    StaleCapabilityError,
    TaskInputBinding,
    TerminalStatus,
    ToolEffect,
    UnsupportedTypeError,
    mcp_tool_descriptor,
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}
OUTPUT_SCHEMA = {"type": "string"}


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
        raise AssertionError("capability-only run must not call the decision provider")


class FakeMCPSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Any:
        self.calls.append((name, arguments))
        return {"structuredContent": arguments["text"].upper()}


@dataclass(frozen=True, slots=True)
class Request:
    text: str


def descriptor(
    identifier: str,
    scopes: tuple[str, ...],
    invoke: Any,
    *,
    input_schema: Mapping[str, Any] = INPUT_SCHEMA,
) -> ForeignToolDescriptor:
    return ForeignToolDescriptor(
        identifier,
        "1.0.0",
        f"Transform text with {identifier}.",
        input_schema,
        OUTPUT_SCHEMA,
        invoke,
        scopes,
        "fixture",
    )


def semantics() -> ImportedToolSemantics:
    return ImportedToolSemantics(
        bindings={"text": TaskInputBinding(("text",))},
        effect=ToolEffect.READ,
        requires_evidence=(),
        produces_evidence=("result",),
        scope_requirements=("scope",),
    )


def definition(tool: Any) -> AgentDefinition[Request, str]:
    return AgentDefinition(
        "imported-tool-agent",
        "1.0.0",
        "Run one explicitly imported host tool.",
        Request,
        str,
        CompletionContract(("result",), {}, "accept"),
        OperatingPolicy("1.0.0", ("accept",)),
        tools=(tool,),
    )


def context(run_id: str = "imported-run") -> RunContext:
    return RunContext(
        "fixture",
        100.0,
        RunLimits(0, 0, 1, 0, 1, 0, 0, 0, 0, 0),
        clock=lambda: 0.0,
        run_id=run_id,
    )


class CapabilityCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_scoped_bounded_discovery_no_fit_and_expansion(self) -> None:
        async def invoke(arguments: Mapping[str, Any]) -> str:
            return str(arguments["text"])

        catalog = CapabilityCatalog(
            "host-tools",
            "1.0.0",
            (
                descriptor("alpha", ("fixture",), invoke),
                descriptor("beta", ("fixture",), invoke),
                descriptor("secret", ("other-tenant",), invoke),
            ),
            scopes=("fixture",),
            max_results=2,
        )

        first = catalog.discover("", "fixture", limit=1)
        second = catalog.expand(first, limit=1)
        no_fit = catalog.discover("missing", "fixture", limit=2)

        self.assertIs(first.coverage, Coverage.TRUNCATED)
        self.assertEqual(first.total_count, 2)
        self.assertIs(second.coverage, Coverage.COMPLETE)
        self.assertEqual(
            {
                candidate.description
                for candidate in first.candidates + second.candidates
            },
            {"Transform text with alpha.", "Transform text with beta."},
        )
        self.assertNotIn("secret", str(first))
        with self.assertRaisesRegex(ScopeError, "unavailable in this scope"):
            catalog.discover("", "other-tenant", limit=1)
        self.assertEqual(no_fit.candidates, ())
        self.assertIs(no_fit.coverage, Coverage.COMPLETE)
        self.assertEqual(no_fit.total_count, 0)

    async def test_activation_requires_semantics_and_rejects_changed_schema(
        self,
    ) -> None:
        calls = 0

        async def invoke(arguments: Mapping[str, Any]) -> str:
            nonlocal calls
            calls += 1
            return str(arguments["text"])

        original = CapabilityCatalog(
            "host-tools",
            "1.0.0",
            (descriptor("echo", ("fixture",), invoke),),
            ("fixture",),
        )
        reference = original.discover("echo", "fixture", limit=1).candidates[0].value

        with self.assertRaises(CapabilityImportError):
            original.activate(reference, ImportedToolSemantics())
        self.assertEqual(calls, 0)

        changed_schema = {
            "type": "object",
            "properties": {"text": {"type": "integer"}},
            "required": ["text"],
            "additionalProperties": False,
        }
        changed = CapabilityCatalog(
            "host-tools",
            "1.0.0",
            (
                descriptor(
                    "echo",
                    ("fixture",),
                    invoke,
                    input_schema=changed_schema,
                ),
            ),
            ("fixture",),
        )
        with self.assertRaises(StaleCapabilityError):
            changed.activate(reference, semantics())
        self.assertEqual(calls, 0)

    async def test_fake_mcp_dispatches_once_through_runtime(self) -> None:
        session = FakeMCPSession()
        foreign = mcp_tool_descriptor(
            session,
            {
                "name": "uppercase",
                "description": "Uppercase supplied text.",
                "inputSchema": INPUT_SCHEMA,
                "outputSchema": OUTPUT_SCHEMA,
            },
            version="1.0.0",
            scopes=("fixture",),
        )
        catalog = CapabilityCatalog("mcp-tools", "1.0.0", (foreign,), ("fixture",))
        reference = (
            catalog.discover("uppercase", "fixture", limit=1).candidates[0].value
        )
        tool = catalog.activate(reference, semantics())
        with self.assertRaises(InputValidationError):
            await tool.function(text=1)
        self.assertEqual(session.calls, [])
        runtime = Runtime(
            UnexpectedProvider(),
            model="unused",
            completion_checks={"accept": lambda value, store: True},
        )

        result = await runtime.run(definition(tool), Request("hello"), context())

        self.assertIs(result.status, TerminalStatus.COMPLETED)
        self.assertEqual(result.value, "HELLO")
        self.assertEqual(session.calls, [("uppercase", {"text": "hello"})])
        snapshot = await runtime.ledger.snapshot()  # type: ignore[union-attr]
        self.assertEqual(snapshot.tool_attempts, 1)

    async def test_activated_scope_is_enforced_after_tool_wrapping(self) -> None:
        calls: list[str] = []

        async def invoke(arguments: Mapping[str, Any]) -> str:
            calls.append(str(arguments["text"]))
            return str(arguments["text"])

        catalog = CapabilityCatalog(
            "host-tools",
            "1.0.0",
            (descriptor("echo", ("tenant-a",), invoke),),
            ("tenant-a",),
        )
        reference = catalog.discover("echo", "tenant-a", limit=1).candidates[0].value
        tool = catalog.activate(reference, semantics())
        wrapped = replace(tool, purpose="Wrapped by a host composition path.")
        runtime = Runtime(
            UnexpectedProvider(),
            model="unused",
            completion_checks={"accept": lambda value, store: True},
        )
        shared_limits = RunLimits(0, 0, 2, 0, 1, 0, 0, 0, 0, 0)

        allowed = await runtime.run(
            definition(wrapped),
            Request("allowed"),
            replace(context("allowed"), scope="tenant-a", limits=shared_limits),
        )
        denied = await runtime.run(
            definition(wrapped),
            Request("denied"),
            replace(context("denied"), scope="tenant-b", limits=shared_limits),
        )

        self.assertIs(allowed.status, TerminalStatus.COMPLETED)
        self.assertIs(denied.status, TerminalStatus.UNRESOLVED)
        self.assertEqual(denied.unresolved[0].reason.value, "permission_denial")
        self.assertEqual(calls, ["allowed"])

    async def test_mcp_explicit_error_status_fails_before_output_validation(self) -> None:
        output_schema = {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
            "additionalProperties": False,
        }

        class ErrorSession:
            def __init__(self, response: Any) -> None:
                self.response = response

            async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Any:
                return self.response

        responses = (
            {
                "isError": True,
                "structuredContent": {"message": "schema-valid secret"},
            },
            SimpleNamespace(
                isError=True,
                structuredContent={"message": "schema-valid secret"},
            ),
        )
        for index, response in enumerate(responses):
            foreign = mcp_tool_descriptor(
                ErrorSession(response),
                {
                    "name": f"read-{index}",
                    "description": "Return an explicit MCP error.",
                    "inputSchema": INPUT_SCHEMA,
                    "outputSchema": output_schema,
                },
                version="1.0.0",
                scopes=("fixture",),
            )
            catalog = CapabilityCatalog(
                f"errors-{index}", "1.0.0", (foreign,), ("fixture",)
            )
            reference = catalog.discover("error", "fixture", limit=1).candidates[0].value
            tool = catalog.activate(reference, semantics())
            store = EvidenceStore(lambda: 0.0)
            runtime = Runtime(
                UnexpectedProvider(),
                model="unused",
                completion_checks={"accept": lambda value, evidence: True},
            )

            result = await runtime.run(
                replace(definition(tool), output_type=tool.output_type),
                Request("secret"),
                replace(context(f"mcp-error-{index}"), evidence_session=store),
            )

            self.assertIs(result.status, TerminalStatus.FAILED)
            self.assertEqual(store.records, ())

    async def test_schema_validation_errors_and_cancellation_are_explicit(self) -> None:
        async def unsafe(arguments: Mapping[str, Any]) -> Any:
            return arguments

        with self.assertRaises(UnsupportedTypeError):
            descriptor(
                "unsafe",
                ("fixture",),
                unsafe,
                input_schema={
                    "type": "object",
                    "properties": {"value": {"$ref": "https://example.invalid"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
            )

        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def block(arguments: Mapping[str, Any]) -> str:
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            raise AssertionError("blocking fixture unexpectedly resumed")

        catalog = CapabilityCatalog(
            "host-tools",
            "1.0.0",
            (descriptor("block", ("fixture",), block),),
            ("fixture",),
        )
        reference = catalog.discover("block", "fixture", limit=1).candidates[0].value
        tool = catalog.activate(reference, semantics())
        task = asyncio.create_task(tool.function(text="wait"))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cancelled.is_set())

        async def fail(arguments: Mapping[str, Any]) -> str:
            raise LookupError("fixture failure")

        failed_catalog = CapabilityCatalog(
            "host-tools",
            "1.0.0",
            (descriptor("fail", ("fixture",), fail),),
            ("fixture",),
        )
        failed_reference = (
            failed_catalog.discover("fail", "fixture", limit=1).candidates[0].value
        )
        failed_tool = failed_catalog.activate(failed_reference, semantics())
        with self.assertRaisesRegex(LookupError, "fixture failure"):
            await failed_tool.function(text="value")

    async def test_mutation_import_fails_closed_before_dispatch(self) -> None:
        calls = 0

        async def invoke(arguments: Mapping[str, Any]) -> str:
            nonlocal calls
            calls += 1
            return "unexpected"

        catalog = CapabilityCatalog(
            "host-tools",
            "1.0.0",
            (descriptor("write", ("fixture",), invoke),),
            ("fixture",),
        )
        reference = catalog.discover("write", "fixture", limit=1).candidates[0].value
        mutation = semantics()
        mutation = ImportedToolSemantics(
            bindings=mutation.bindings,
            effect=ToolEffect.MUTATION,
            requires_evidence=(),
            produces_evidence=("result",),
            scope_requirements=("scope",),
        )
        with self.assertRaisesRegex(CapabilityImportError, "receipt contract"):
            catalog.activate(reference, mutation)
        self.assertEqual(calls, 0)


if __name__ == "__main__":
    unittest.main()
