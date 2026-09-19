import json
import unittest
from dataclasses import dataclass

from pydantic import BaseModel

from jev_frame import (
    AgentDefinition,
    BindingGroup,
    Candidate,
    CandidateBinding,
    CandidateProvider,
    CandidateSet,
    ChoiceQuestion,
    CompilationDiagnostic,
    CompilerError,
    CompletionContract,
    Coverage,
    HostContextBinding,
    Judgment,
    NoulQuestion,
    OperatingPolicy,
    ScoreQuestion,
    SourceBinding,
    SourceField,
    Subject,
    TaskInputBinding,
    Tool,
    compile_agent,
    preview_agent,
)


@dataclass(frozen=True)
class Request:
    statement: str


class Result(BaseModel):
    document_id: str
    quote: str


def fixture_definition(calls: dict[str, int]) -> AgentDefinition[Request, Result]:
    def documents(_: Request) -> CandidateSet:
        calls["provider"] += 1
        raise AssertionError("preview must not retrieve")

    def read_document(document_id: str) -> str:
        calls["read"] += 1
        return document_id

    def assemble(document_id: str, quote: str) -> str:
        calls["assemble"] += 1
        return f"{document_id}: {quote}"

    selected = Judgment(
        "selected_document",
        "1.0.0",
        ChoiceQuestion("Which document supports the requested statement?"),
        (Subject("requested statement"), Subject("catalog document")),
        candidate_set="documents",
    )
    reader = Tool(
        "read_document",
        "1.0.0",
        "Read the selected document.",
        read_document,
        {"document_id": CandidateBinding("documents", "selected_document")},
        produces_evidence=("quote",),
    )
    result = Tool(
        "assemble_result",
        "1.0.0",
        "Copy the exact quote into a result finding.",
        assemble,
        {
            "document_id": CandidateBinding("documents", "selected_document"),
            "quote": SourceBinding("quote", SourceField(("text",))),
        },
        produces_evidence=("result_quote",),
    )
    return AgentDefinition(
        "document_support",
        "1.0.0",
        "Select a document and retain an exact source quote.",
        Request,
        Result,
        CompletionContract(
            ("selected_document", "result_quote"),
            {"document_id": "selected_document", "quote": "result_quote"},
            "policy",
        ),
        OperatingPolicy("1.0.0", ("policy",)),
        tools=(reader, result),
        judgments=(selected,),
        candidate_providers=(CandidateProvider("documents", "1.0.0", documents),),
    )


def snapshot(count: int = 2) -> CandidateSet:
    return CandidateSet(
        "documents",
        "1.0.0",
        tuple(
            Candidate(
                f"doc-{index}",
                f"document-{index}",
                f"Document {index}",
                "fixture",
                "v1",
            )
            for index in range(count)
        ),
        Coverage.COMPLETE,
        "fixture",
    )


class CompilerTests(unittest.TestCase):
    def test_scenario_a_compiles_without_dispatch_and_serializes(self) -> None:
        calls = {"provider": 0, "read": 0, "assemble": 0}
        definition = fixture_definition(calls)

        program = compile_agent(definition, candidate_sets={"documents": snapshot()})
        preview = preview_agent(definition, candidate_sets={"documents": snapshot()})

        self.assertEqual(calls, {"provider": 0, "read": 0, "assemble": 0})
        self.assertEqual(program.questions[0].subjects[0], "requested statement")
        self.assertIn("requested statement", program.questions[0].instructions)
        self.assertEqual(program.questions[0].options[-1].key, "__jev_frame_no_fit__")
        self.assertEqual(json.loads(program.to_json()), program.to_dict())
        self.assertEqual(preview["digest"], program.digest)
        self.assertNotIn("document-0", program.to_json())

    def test_missing_snapshot_is_precise_and_does_not_retrieve(self) -> None:
        calls = {"provider": 0, "read": 0, "assemble": 0}

        program = compile_agent(fixture_definition(calls))

        self.assertEqual(calls, {"provider": 0, "read": 0, "assemble": 0})
        self.assertFalse(program.questions[0].dispatchable)
        self.assertEqual(program.diagnostics[0].code, "missing_candidate_snapshot")
        self.assertEqual(program.diagnostics[0].reference, "documents")

    def test_partial_preview_names_missing_task_and_host_bindings(self) -> None:
        class Finding(BaseModel):
            finding: str

        calls = 0

        def produce(statement: str, tenant: str) -> str:
            nonlocal calls
            calls += 1
            return f"{tenant}:{statement}"

        tool = Tool(
            "produce",
            "1.0.0",
            "Produce a scoped finding.",
            produce,
            {
                "statement": TaskInputBinding(("statement",)),
                "tenant": HostContextBinding("tenant"),
            },
            produces_evidence=("finding",),
        )
        definition: AgentDefinition[Request, Finding] = AgentDefinition(
            "partial",
            "1.0.0",
            "Preview missing bindings.",
            Request,
            Finding,
            CompletionContract(("finding",), {"finding": "finding"}, "policy"),
            OperatingPolicy("1.0.0", ("policy",)),
            tools=(tool,),
        )

        partial = compile_agent(definition)
        complete = compile_agent(
            definition,
            task_input=Request("claim"),
            host_context_keys=("tenant",),
        )

        self.assertEqual(calls, 0)
        self.assertEqual(
            [(item.code, item.binding, item.reference) for item in partial.diagnostics],
            [
                ("missing_task_input", "statement", "statement"),
                ("missing_host_context", "tenant", "tenant"),
            ],
        )
        self.assertFalse(complete.diagnostics)

    def test_empty_or_failed_candidates_are_not_provider_questions(self) -> None:
        calls = {"provider": 0, "read": 0, "assemble": 0}
        definition = fixture_definition(calls)
        empty = snapshot(0)
        failed = CandidateSet(
            "documents",
            "1.0.0",
            (),
            Coverage.FAILED,
            "fixture",
            failure_reason="offline fixture failure",
        )

        empty_program = compile_agent(definition, candidate_sets={"documents": empty})
        failed_program = compile_agent(definition, candidate_sets={"documents": failed})

        self.assertFalse(empty_program.questions[0].dispatchable)
        self.assertFalse(failed_program.questions[0].dispatchable)
        self.assertIn(
            "deterministic_no_fit", {item.code for item in empty_program.diagnostics}
        )
        self.assertIn(
            "candidate_retrieval_failed",
            {item.code for item in failed_program.diagnostics},
        )
        self.assertEqual(calls, {"provider": 0, "read": 0, "assemble": 0})

    def test_unresolvable_completion_need_names_the_reference(self) -> None:
        calls = {"provider": 0, "read": 0, "assemble": 0}
        definition = fixture_definition(calls)
        broken: AgentDefinition[Request, Result] = AgentDefinition(
            definition.id,
            definition.version,
            definition.objective,
            definition.input_type,
            definition.output_type,
            CompletionContract(
                ("missing",),
                {"document_id": "missing", "quote": "missing"},
                "policy",
            ),
            definition.policy,
            definition.tools,
            definition.judgments,
            definition.candidate_providers,
        )

        with self.assertRaises(CompilerError) as caught:
            compile_agent(broken, candidate_sets={"documents": snapshot()})

        self.assertEqual(caught.exception.diagnostic.code, "missing_evidence_producer")
        self.assertEqual(caught.exception.diagnostic.reference, "missing")

    def test_dependencies_create_distinct_evaluation_stages(self) -> None:
        class Answer(BaseModel):
            answer: bool

        first = Judgment(
            "first",
            "1.0.0",
            NoulQuestion("Is the first claim supported?"),
            (Subject("first claim"),),
        )
        second = Judgment(
            "second",
            "1.0.0",
            NoulQuestion("Given the prior judgment, is the conclusion supported?"),
            (Subject("conclusion"),),
            dependencies=("first",),
        )
        definition: AgentDefinition[Request, Answer] = AgentDefinition(
            "dependent",
            "1.0.0",
            "Evaluate a dependent conclusion.",
            Request,
            Answer,
            CompletionContract(("second",), {"answer": "second"}, "policy"),
            OperatingPolicy("1.0.0", ("policy",)),
            judgments=(first, second),
        )

        default = compile_agent(definition)
        opaque = compile_agent(
            definition,
            question_ids={"first": "q-a7", "second": "q-z2"},
        )

        self.assertEqual(
            tuple(stage.question_ids for stage in opaque.stages),
            (("q-a7",), ("q-z2",)),
        )
        self.assertEqual(
            [question.instructions for question in default.questions],
            [question.instructions for question in opaque.questions],
        )
        self.assertNotIn("q-a7", opaque.questions[0].instructions)

    def test_dependency_cycles_fail_before_dispatch(self) -> None:
        class Answer(BaseModel):
            answer: bool

        first = Judgment(
            "first",
            "1.0.0",
            NoulQuestion("Evaluate the first claim."),
            (Subject("first claim"),),
            dependencies=("second",),
        )
        second = Judgment(
            "second",
            "1.0.0",
            NoulQuestion("Evaluate the second claim."),
            (Subject("second claim"),),
            dependencies=("first",),
        )
        definition: AgentDefinition[Request, Answer] = AgentDefinition(
            "cycle",
            "1.0.0",
            "Reject cyclic judgments.",
            Request,
            Answer,
            CompletionContract(("second",), {"answer": "second"}, "policy"),
            OperatingPolicy("1.0.0", ("policy",)),
            judgments=(first, second),
        )

        with self.assertRaises(CompilerError) as caught:
            compile_agent(definition)

        self.assertEqual(caught.exception.diagnostic.code, "dependency_cycle")

    def test_independent_candidate_bindings_cannot_form_a_tuple(self) -> None:
        class Updated(BaseModel):
            updated: str

        def documents(_: Request) -> CandidateSet:
            raise AssertionError("compile must not retrieve")

        def update(record: str, revision: str) -> str:
            return f"{record}@{revision}"

        first = Judgment(
            "record_choice",
            "1.0.0",
            ChoiceQuestion("Select a record."),
            (Subject("record"),),
            candidate_set="documents",
        )
        second = Judgment(
            "revision_choice",
            "1.0.0",
            ChoiceQuestion("Select a revision."),
            (Subject("revision"),),
            candidate_set="documents",
        )
        tool = Tool(
            "update",
            "1.0.0",
            "Build a correlated synthetic tuple.",
            update,
            {
                "record": CandidateBinding("documents", "record_choice"),
                "revision": CandidateBinding("documents", "revision_choice"),
            },
            binding_groups=(BindingGroup(("record", "revision")),),
            produces_evidence=("updated",),
        )
        definition: AgentDefinition[Request, Updated] = AgentDefinition(
            "tuple",
            "1.0.0",
            "Reject independently selected tuple fields.",
            Request,
            Updated,
            CompletionContract(("updated",), {"updated": "updated"}, "policy"),
            OperatingPolicy("1.0.0", ("policy",)),
            tools=(tool,),
            judgments=(first, second),
            candidate_providers=(CandidateProvider("documents", "1.0.0", documents),),
        )

        with self.assertRaises(CompilerError) as caught:
            compile_agent(definition, candidate_sets={"documents": snapshot()})

        self.assertEqual(caught.exception.diagnostic.code, "unsafe_binding_group")

    def test_primitive_limits_fail_instead_of_truncating(self) -> None:
        calls = {"provider": 0, "read": 0, "assemble": 0}
        with self.assertRaises(CompilerError) as choice_error:
            compile_agent(
                fixture_definition(calls),
                candidate_sets={"documents": snapshot(255)},
            )
        self.assertEqual(
            choice_error.exception.diagnostic.code, "choice_limit_exceeded"
        )

        class Scored(BaseModel):
            score: float

        judgment = Judgment(
            "score",
            "1.0.0",
            ScoreQuestion("Score the claim.", tuple(str(index) for index in range(11))),
            (Subject("claim"),),
        )
        definition: AgentDefinition[Request, Scored] = AgentDefinition(
            "score_limit",
            "1.0.0",
            "Reject oversized rubrics.",
            Request,
            Scored,
            CompletionContract(("score",), {"score": "score"}, "policy"),
            OperatingPolicy("1.0.0", ("policy",)),
            judgments=(judgment,),
        )
        with self.assertRaises(CompilerError) as score_error:
            compile_agent(definition)
        self.assertEqual(score_error.exception.diagnostic.code, "score_limit_exceeded")

    def test_bounded_revision_accepts_only_registered_capabilities(self) -> None:
        calls = {"provider": 0, "read": 0, "assemble": 0}
        definition = fixture_definition(calls)

        program = compile_agent(
            definition,
            candidate_sets={"documents": snapshot()},
            capability_revision=("read_document",),
            max_revision_steps=1,
        )
        self.assertIn("invoke:read_document", {node.id for node in program.nodes})
        with self.assertRaises(CompilerError) as caught:
            compile_agent(
                definition,
                candidate_sets={"documents": snapshot()},
                capability_revision=("os.system",),
                max_revision_steps=1,
            )
        self.assertEqual(caught.exception.diagnostic.code, "unknown_capability")

    def test_diagnostic_is_plain_serializable_data(self) -> None:
        diagnostic = CompilationDiagnostic(
            "missing", "Missing input.", "definition", reference="input"
        )
        self.assertEqual(
            diagnostic.to_dict(),
            {
                "code": "missing",
                "message": "Missing input.",
                "definition_id": "definition",
                "reference": "input",
            },
        )


if __name__ == "__main__":
    unittest.main()
