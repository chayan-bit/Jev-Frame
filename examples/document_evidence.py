"""Synthetic public-import example for binding one package to two catalogs."""

from collections.abc import Mapping

from jev_frame import (
    Candidate,
    CandidateSet,
    Coverage,
    DocumentEvidencePackage,
    DocumentRecord,
    bind_document_evidence_package,
)

CATALOG_A = {
    "a-1": DocumentRecord("a-1", "The launch occurred on Tuesday.", "a-v1"),
}
CATALOG_B = {
    "b-1": DocumentRecord("b-1", "The launch was postponed to Friday.", "b-v1"),
}


def retrieve_a(
    query: str, scope: str, documents: Mapping[str, DocumentRecord]
) -> CandidateSet:
    return CandidateSet(
        "documents",
        "1.0.0",
        tuple(
            Candidate(
                key, key, f"Synthetic A document for {query}", "a", document.version
            )
            for key, document in documents.items()
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
            Candidate(
                key, key, f"Synthetic B document for {query}", "b", document.version
            )
            for key, document in documents.items()
        ),
        Coverage.COMPLETE,
        scope,
    )


def read_a(document_id: str, documents: Mapping[str, DocumentRecord]) -> DocumentRecord:
    return documents[document_id]


def read_b(document_id: str, documents: Mapping[str, DocumentRecord]) -> DocumentRecord:
    return documents[document_id]


def build_examples() -> tuple[DocumentEvidencePackage, DocumentEvidencePackage]:
    return (
        bind_document_evidence_package(
            retrieve_documents=retrieve_a,
            read_document=read_a,
        ),
        bind_document_evidence_package(
            retrieve_documents=retrieve_b,
            read_document=read_b,
        ),
    )


if __name__ == "__main__":
    first, second = build_examples()
    assert first.id == second.id == "document_evidence"
    assert (
        first.capabilities.candidate_providers[0].function
        is not second.capabilities.candidate_providers[0].function
    )
