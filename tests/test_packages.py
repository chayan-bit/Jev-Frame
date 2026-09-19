import inspect
import json
import runpy
import unittest
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from jev_frame import (
    AgentDefinition,
    AttemptAdmission,
    AttemptStatus,
    Candidate,
    CandidateSet,
    ChoiceAnswer,
    CompiledQuestion,
    Coverage,
    DecisionClient,
    DecisionContext,
    DecisionInputs,
    DefinitionError,
    DocumentEvidencePackage,
    DocumentEvidenceRequest,
    DocumentRecord,
    EvidenceStore,
    NoulAnswer,
    Observation,
    OperatingPolicy,
    ProviderAttempt,
    ProviderBatch,
    RunLimits,
    UnsupportedTypeError,
    Usage,
    UsageCoverage,
    bind_document_evidence_package,
    compile_agent,
)

CATALOG_A = {
    "a-1": DocumentRecord("a-1", "Alpha supports the claim.", "a-v1"),
}
CATALOG_B = {
    "b-1": DocumentRecord("b-1", "Beta supports a different claim.", "b-v1"),
}


def retrieve_a(
    query: str, scope: str, documents: Mapping[str, DocumentRecord]
) -> CandidateSet:
    return CandidateSet(
        "documents",
        "1.0.0",
        tuple(
            Candidate(key, value, f"A result for {query}", "catalog-a", value.version)
            for key, value in documents.items()
        ),
        Coverage.COMPLETE,
        scope,
    )


def retrieve_b(
    query: str, scope: str, documents: Mapping[str, DocumentRecord]
) -> CandidateSet:
    return CandidateSet(
        "documents",
        "1.0.0",
        tuple(
            Candidate(key, value, f"B result for {query}", "catalog-b", value.version)
            for key, value in documents.items()
        ),
        Coverage.COMPLETE,
        scope,
    )


def read_a(document_id: str, documents: Mapping[str, DocumentRecord]) -> DocumentRecord:
    return documents[document_id]


def read_b(document_id: str, documents: Mapping[str, DocumentRecord]) -> DocumentRecord:
    return documents[document_id]


def wrong_reader(document_id: str, documents: Mapping[str, DocumentRecord]) -> str:
    return document_id


class PackageProvider:
    def __init__(self) -> None:
        self.payloads: list[Mapping[str, Any]] = []

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
        question = questions[0]
        self.payloads.append(
            {"state": state, "questions": [item.to_dict() for item in questions]}
        )
        answer: ChoiceAnswer | NoulAnswer
        if question.primitive == "choice":
            selected = question.options[0].key
            answer = ChoiceAnswer(
                selected,
                {
                    option.key: 1.0 if option.key == selected else 0.0
                    for option in question.options
                },
                1.0,
            )
        else:
            answer = NoulAnswer(0.8)
        finished = ProviderAttempt(
            attempt.id, 1, AttemptStatus.SUCCEEDED, request_id=operation_id
        )
        return ProviderBatch(
            {question.routing_id: answer},
            requested_model,
            "scripted",
            operation_id,
            Usage(UsageCoverage.COMPLETE, 4, 1, 1, 1),
            (finished,),
        )


def package(
    retrieve: Any = retrieve_a,
    reader: Any = read_a,
    *,
    version: str = "1.0.0",
) -> DocumentEvidencePackage:
    return bind_document_evidence_package(
        retrieve_documents=retrieve,
        read_document=reader,
        version=version,
    )


def definition(
    document_package: DocumentEvidencePackage,
    *,
    capabilities: Any = None,
) -> AgentDefinition[DocumentEvidenceRequest, Any]:
    return AgentDefinition(
        "document_agent",
        "1.0.0",
        "Find a document and assess whether its exact text supports a claim.",
        document_package.input_type,
        document_package.output_type,
        document_package.completion("application-policy"),
        OperatingPolicy("1.0.0", ("application-policy",)),
        packages=(
            document_package.capabilities if capabilities is None else capabilities,
        ),
    )


class PackageTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_applications_reuse_package_operations_directly(self) -> None:
        first = package(retrieve_a, read_a)
        second = package(retrieve_b, read_b)
        provider = PackageProvider()
        client = DecisionClient(provider, model="scripted")
        store = EvidenceStore(lambda: 0.0)
        context = DecisionContext(
            "fixture",
            100.0,
            RunLimits(10, 10, 0, 0, 2, 0, 0, 0, 0, 0),
            clock=lambda: 0.0,
            evidence_session=store,
        )

        for index, (bound, catalog) in enumerate(
            ((first, CATALOG_A), (second, CATALOG_B)), start=1
        ):
            snapshot = bound.capabilities.candidate_providers[0].function(
                "support", "fixture", catalog
            )
            selected = await client.select(
                bound.selection,
                DecisionInputs(
                    f"select-{index}",
                    {"query": "support"},
                    candidate_sets={"documents": snapshot},
                ),
                context,
            )
            assert selected.selection is not None
            assert selected.selection.candidate is not None
            document = selected.selection.candidate.value
            source = Observation(
                id=f"document-{index}",
                value=document,
                source_id=selected.selection.candidate.source_id,
                scope="fixture",
                observed_at=0.0,
                source_version=document.version,
            )
            excerpt = await client.extract_source(source, bound.exact_source, context)
            assessment = await client.assess(
                bound.assessment,
                DecisionInputs(
                    f"assess-{index}",
                    {"claim": "support", "document": document.id},
                    {
                        "document_excerpt": Observation(
                            id=f"excerpt-{index}",
                            value=excerpt.value,
                            source_id=excerpt.source_id,
                            scope="fixture",
                            observed_at=0.0,
                            source_version=excerpt.source_version,
                        )
                    },
                ),
                context,
            )
            self.assertIsInstance(assessment.answer, NoulAnswer)
            reader = bound.capabilities.tools[0].function
            self.assertEqual(reader(document.id, catalog), document)

        self.assertEqual(first.id, second.id)
        self.assertIsNot(
            first.capabilities.candidate_providers[0].function,
            second.capabilities.candidate_providers[0].function,
        )
        self.assertIsNot(
            first.capabilities.tools[0].function,
            second.capabilities.tools[0].function,
        )

    async def test_evaluator_cases_never_enter_provider_state(self) -> None:
        bound = package()
        provider = PackageProvider()
        client = DecisionClient(provider, model="scripted")
        context = DecisionContext(
            "fixture",
            100.0,
            RunLimits(2, 2, 0, 0, 1, 0, 0, 0, 0, 0),
            clock=lambda: 0.0,
        )
        case_module = runpy.run_path(
            str(Path(__file__).parents[1] / "examples/document_evidence_cases.py")
        )
        evaluator_cases = case_module["CASES"]
        snapshot = retrieve_a("support", "fixture", CATALOG_A)

        await client.select(
            bound.selection,
            DecisionInputs(
                "label-isolation",
                {"query": "support"},
                candidate_sets={"documents": snapshot},
            ),
            context,
        )

        provider_input = json.dumps(provider.payloads)
        self.assertNotIn("expected_selection", provider_input)
        self.assertNotIn(evaluator_cases[0].evaluator_note, provider_input)
        self.assertFalse(hasattr(bound.capabilities, "regression_cases"))

    def test_binding_failures_and_capability_collisions_precede_execution(self) -> None:
        with self.assertRaises(DefinitionError):
            package(None, read_a)
        with self.assertRaises(UnsupportedTypeError):
            package(retrieve_a, wrong_reader)
        bound = package()
        with self.assertRaises(DefinitionError):
            AgentDefinition(
                "conflict",
                "1.0.0",
                "Reject duplicate registrations.",
                bound.input_type,
                bound.output_type,
                bound.completion("application-policy"),
                OperatingPolicy("1.0.0", ("application-policy",)),
                judgments=(bound.selection,),
                packages=(bound.capabilities,),
            )

    def test_package_version_changes_compiled_configuration(self) -> None:
        bound = package()
        version_only_change = replace(bound.capabilities, version="2.0.0")
        request = DocumentEvidenceRequest("support", "Alpha supports the claim.")
        snapshot = retrieve_a(request.query, "fixture", CATALOG_A)

        first = compile_agent(
            definition(bound),
            candidate_sets={"documents": snapshot},
            task_input=request,
            host_context_keys=("scope", "documents"),
        )
        second = compile_agent(
            definition(bound, capabilities=version_only_change),
            candidate_sets={"documents": snapshot},
            task_input=request,
            host_context_keys=("scope", "documents"),
        )

        self.assertEqual(first.package_versions, (("document_evidence", "1.0.0"),))
        self.assertEqual(second.package_versions, (("document_evidence", "2.0.0"),))
        self.assertNotEqual(first.digest, second.digest)

    def test_public_example_binds_two_synthetic_catalogs(self) -> None:
        example = runpy.run_path(
            str(Path(__file__).parents[1] / "examples/document_evidence.py")
        )
        first, second = example["build_examples"]()

        self.assertEqual(first.id, second.id)
        self.assertIsNot(
            first.capabilities.candidate_providers[0].function,
            second.capabilities.candidate_providers[0].function,
        )


if __name__ == "__main__":
    unittest.main()
