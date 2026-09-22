import os
import subprocess
import sys
import unittest
from dataclasses import dataclass
from typing import Literal, cast

from pydantic import BaseModel

from jev_frame import (
    AgentDefinition,
    Binding,
    BindingError,
    BindingGroup,
    Candidate,
    CandidateProvider,
    CandidateSet,
    ChoiceOption,
    ChoiceQuestion,
    CompletionContract,
    ConstantBinding,
    Coverage,
    DefaultBinding,
    DefinitionError,
    EvidenceSelector,
    HostContextBinding,
    InputValidationError,
    Judgment,
    MutationContract,
    NoulQuestion,
    OperatingPolicy,
    RunContext,
    RunLimits,
    Subject,
    TaskInputBinding,
    Tool,
    ToolEffect,
    UnsupportedTypeError,
    Usage,
    UsageCoverage,
    validate_value,
)


@dataclass(frozen=True)
class Request:
    statement: str
    limit: int


class Result(BaseModel):
    document_id: str


def read_document(document_id: str, limit: int = 10) -> str:
    return document_id[:limit]


def catalog(statement: str) -> CandidateSet:
    return CandidateSet(
        id="documents",
        version="1.0.0",
        candidates=(Candidate("doc-1", "doc-1", "Document one", "fixture"),),
        coverage=Coverage.COMPLETE,
        scope="fixture",
    )


class DefinitionTests(unittest.TestCase):
    def test_representative_definition_uses_public_api(self) -> None:
        tool = Tool(
            id="read_document",
            version="1.0.0",
            purpose="Read a selected document.",
            function=read_document,
            bindings={
                "document_id": HostContextBinding("document_id"),
                "limit": DefaultBinding(),
            },
            binding_groups=(BindingGroup(("document_id", "limit")),),
        )
        judgment = Judgment(
            id="select_document",
            version="1.0.0",
            primitive=ChoiceQuestion(
                "Which document supports the statement?",
                (
                    ChoiceOption("doc-1", "Document one"),
                    ChoiceOption("no-fit", "None fit"),
                ),
            ),
            subjects=(Subject("statement"),),
            evidence=(EvidenceSelector("documents"),),
        )
        definition: AgentDefinition[Request, Result] = AgentDefinition(
            id="document_support",
            version="1.0.0",
            objective="Select supporting evidence.",
            input_type=Request,
            output_type=Result,
            completion=CompletionContract(
                required_findings=("selected_document",),
                result_bindings={"document_id": "selected_document"},
                acceptance_policy="document-policy",
            ),
            policy=OperatingPolicy("1.0.0", ("document-policy",)),
            tools=(tool,),
            judgments=(judgment,),
            candidate_providers=(
                CandidateProvider(
                    "documents",
                    "1.0.0",
                    catalog,
                    {"statement": TaskInputBinding(("statement",))},
                ),
            ),
        )

        self.assertEqual(definition.id, "document_support")
        self.assertIsInstance(tool.bindings["limit"], DefaultBinding)

    def test_missing_binding_fails_without_invoking_tool(self) -> None:
        calls = 0

        def operation(value: int) -> int:
            nonlocal calls
            calls += 1
            return value

        with self.assertRaises(BindingError):
            Tool("operation", "1.0.0", "Return a value.", operation, {})

        self.assertEqual(calls, 0)

    def test_defaults_omission_and_none_are_distinct(self) -> None:
        def operation(omitted: int = 7, explicit_none: int | None = 9) -> int:
            return omitted if explicit_none is None else explicit_none

        tool = Tool(
            "operation",
            "1.0.0",
            "Observe binding identity.",
            operation,
            {
                "omitted": DefaultBinding(),
                "explicit_none": ConstantBinding(None),
            },
        )

        self.assertIsInstance(tool.bindings["omitted"], DefaultBinding)
        explicit_none = tool.bindings["explicit_none"]
        self.assertIsInstance(explicit_none, ConstantBinding)
        assert isinstance(explicit_none, ConstantBinding)
        self.assertIsNone(explicit_none.value)

    def test_strict_validation_rejects_scalar_coercion(self) -> None:
        with self.assertRaises(InputValidationError):
            validate_value(int, "12", "count")
        with self.assertRaises(InputValidationError):
            validate_value(str, True, "identifier")

        self.assertEqual(validate_value(int, 12, "count"), 12)
        self.assertEqual(validate_value(str, "12", "identifier"), "12")

    def test_literal_validation_preserves_exact_scalar_types(self) -> None:
        with self.assertRaises(InputValidationError):
            validate_value(Literal[1, 2], True, "choice")
        with self.assertRaises(InputValidationError):
            validate_value(Literal[True], 1, "choice")
        with self.assertRaises(InputValidationError):
            validate_value(Literal[1.0], 1, "choice")
        with self.assertRaises(InputValidationError):
            validate_value(list[Literal[1, 2]], [1, True], "choices")

        self.assertEqual(validate_value(Literal[1, 2], 1, "choice"), 1)
        self.assertEqual(validate_value(Literal[1, 2], 2, "choice"), 2)
        self.assertEqual(validate_value(Literal[1.0], 1.0, "choice"), 1.0)

        def use(choice: Literal[1, 2]) -> str:
            return str(choice)

        with self.assertRaises(InputValidationError):
            Tool(
                "literal",
                "1.0.0",
                "Reject an equal value of the wrong scalar type.",
                use,
                {"choice": ConstantBinding(True)},
            )

    def test_unsupported_signatures_and_types_fail(self) -> None:
        def variadic(*values: int) -> int:
            return sum(values)

        def arbitrary(value: object) -> int:
            return 1

        def identity(value: int) -> int:
            return value

        with self.assertRaises(DefinitionError):
            Tool(
                "variadic",
                "1.0.0",
                "Reject variadic input.",
                variadic,
                {"values": TaskInputBinding(("values",))},
            )
        with self.assertRaises(UnsupportedTypeError):
            Tool(
                "arbitrary",
                "1.0.0",
                "Reject arbitrary objects.",
                arbitrary,
                {"value": TaskInputBinding(("value",))},
            )
        with self.assertRaises(BindingError):
            Tool(
                "bad_binding",
                "1.0.0",
                "Reject implicit model input.",
                identity,
                {"value": cast(Binding, "model")},
            )

    def test_unresolved_annotations_fail(self) -> None:
        def unresolved(value: int) -> int:
            return value

        unresolved.__annotations__["value"] = "MissingType"

        with self.assertRaises(UnsupportedTypeError):
            Tool(
                "unresolved",
                "1.0.0",
                "Reject unresolved annotations.",
                unresolved,
                {"value": TaskInputBinding(("value",))},
            )

    def test_duplicate_ids_fail(self) -> None:
        first = Judgment(
            "same", "1.0.0", NoulQuestion("Is this supported?"), (Subject("subject"),)
        )
        second = Judgment(
            "same", "1.0.1", NoulQuestion("Is this current?"), (Subject("subject"),)
        )

        with self.assertRaises(DefinitionError):
            AgentDefinition(
                "duplicate",
                "1.0.0",
                "Reject collisions.",
                Request,
                Result,
                CompletionContract(("answer",), {"document_id": "answer"}, "policy"),
                OperatingPolicy("1.0.0", ("policy",)),
                judgments=(first, second),
            )

    def test_definition_references_must_be_registered(self) -> None:
        judgment = Judgment(
            "dependent",
            "1.0.0",
            NoulQuestion("Is this supported?"),
            (Subject("subject"),),
            dependencies=("missing",),
        )

        with self.assertRaises(DefinitionError):
            AgentDefinition(
                "missing_reference",
                "1.0.0",
                "Reject missing references.",
                Request,
                Result,
                CompletionContract(("answer",), {"document_id": "answer"}, "policy"),
                OperatingPolicy("1.0.0", ("policy",)),
                judgments=(judgment,),
            )

    def test_mutations_require_recovery_metadata(self) -> None:
        def update(value: int) -> int:
            return value

        with self.assertRaises(DefinitionError):
            Tool(
                "update",
                "1.0.0",
                "Update a synthetic value.",
                update,
                {"value": TaskInputBinding(("value",))},
                effect=ToolEffect.MUTATION,
            )
        with self.assertRaises(DefinitionError):
            MutationContract(False)

    def test_limits_deadlines_and_unknown_usage_are_explicit(self) -> None:
        limits = RunLimits(1, 1, 0, 0, 1, 0, 0, 0, 0, 0)
        context = RunContext("fixture", 1.0, limits)
        usage = Usage()

        self.assertEqual(context.scope, "fixture")
        self.assertIs(usage.coverage, UsageCoverage.UNKNOWN)
        self.assertIsNone(usage.input_tokens)
        with self.assertRaises(DefinitionError):
            RunLimits(-1, 1, 0, 0, 1, 0, 0, 0, 0, 0)
        with self.assertRaises(DefinitionError):
            RunContext("fixture", float("inf"), limits)
        with self.assertRaises(DefinitionError):
            Usage(UsageCoverage.COMPLETE)

    def test_core_import_needs_no_credentials_or_optional_frameworks(self) -> None:
        environment = os.environ.copy()
        environment.pop("TYPESAFE_API_KEY", None)
        completed = subprocess.run(
            [sys.executable, "-I", "-c", "import jev_frame"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
