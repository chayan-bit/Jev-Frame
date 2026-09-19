from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, get_type_hints

from .definitions import (
    CandidateBinding,
    CandidateProvider,
    CandidateSet,
    CapabilityPackage,
    ChoiceAnswer,
    ChoiceQuestion,
    CompletionContract,
    DefinitionError,
    EvidenceSelector,
    HostContextBinding,
    Judgment,
    NoulAnswer,
    NoulQuestion,
    RetryOwner,
    SourceBinding,
    SourceField,
    Subject,
    TaskInputBinding,
    Tool,
    ToolEffect,
    UnsupportedTypeError,
)

DOCUMENT_CANDIDATES = "documents"
SELECT_DOCUMENT = "select_document"
READ_DOCUMENT = "read_document"
EXTRACT_DOCUMENT_TEXT = "extract_document_text"
ASSESS_DOCUMENT_SUPPORT = "assess_document_support"
DOCUMENT_RECORD = "document_record"
DOCUMENT_EXCERPT = "document_excerpt"


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    id: str
    text: str
    version: str


@dataclass(frozen=True, slots=True)
class DocumentEvidenceRequest:
    query: str
    claim: str


@dataclass(frozen=True, slots=True)
class DocumentEvidenceResult:
    selection: ChoiceAnswer
    assessment: NoulAnswer
    excerpt: str


@dataclass(frozen=True, slots=True)
class DocumentEvidencePackage:
    capabilities: CapabilityPackage
    selection: Judgment
    assessment: Judgment
    exact_source: SourceField
    result_requirements: Mapping[str, str]
    input_type: type[DocumentEvidenceRequest] = DocumentEvidenceRequest
    output_type: type[DocumentEvidenceResult] = DocumentEvidenceResult

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "result_requirements",
            MappingProxyType(dict(self.result_requirements)),
        )

    @property
    def id(self) -> str:
        return self.capabilities.id

    @property
    def version(self) -> str:
        return self.capabilities.version

    def completion(self, acceptance_policy: str) -> CompletionContract:
        """Bind application-owned acceptance; the package supplies no threshold."""

        return CompletionContract(
            tuple(self.result_requirements.values()),
            self.result_requirements,
            acceptance_policy,
        )


def _validate_host_function(
    function: Callable[..., Any] | None,
    *,
    name: str,
    parameters: Mapping[str, Any],
    returns: Any,
) -> Callable[..., Any]:
    if function is None or not callable(function):
        raise DefinitionError(f"document evidence package requires {name}")
    if inspect.iscoroutinefunction(function):
        raise DefinitionError(f"{name} must be a synchronous host function")
    signature = inspect.signature(function)
    if tuple(signature.parameters) != tuple(parameters) or any(
        item.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }
        for item in signature.parameters.values()
    ):
        raise DefinitionError(
            f"{name} must accept exactly {tuple(parameters)} as named parameters"
        )
    try:
        hints = get_type_hints(function, include_extras=True)
    except (NameError, TypeError) as error:
        raise UnsupportedTypeError(f"cannot resolve annotations for {name}") from error
    expected = dict(parameters)
    expected["return"] = returns
    if hints != expected:
        raise UnsupportedTypeError(f"{name} annotations do not match its contract")
    return function


def _extract_document_text(excerpt: str) -> str:
    return excerpt


def bind_document_evidence_package(
    *,
    retrieve_documents: Callable[[str, str, Mapping[str, DocumentRecord]], CandidateSet]
    | None,
    read_document: Callable[[str, Mapping[str, DocumentRecord]], DocumentRecord] | None,
    package_id: str = "document_evidence",
    version: str = "1.0.0",
) -> DocumentEvidencePackage:
    """Bind stateless typed host functions to the generic document decisions."""

    retrieve = _validate_host_function(
        retrieve_documents,
        name="retrieve_documents",
        parameters={
            "query": str,
            "scope": str,
            "documents": Mapping[str, DocumentRecord],
        },
        returns=CandidateSet,
    )
    reader = _validate_host_function(
        read_document,
        name="read_document",
        parameters={
            "document_id": str,
            "documents": Mapping[str, DocumentRecord],
        },
        returns=DocumentRecord,
    )
    selection = Judgment(
        SELECT_DOCUMENT,
        version,
        ChoiceQuestion(
            "Select the document that best fits the query, or choose no-fit."
        ),
        (Subject("query"),),
        candidate_set=DOCUMENT_CANDIDATES,
    )
    assessment = Judgment(
        ASSESS_DOCUMENT_SUPPORT,
        version,
        NoulQuestion(
            "Does the exact document excerpt support the claim?",
            "The excerpt supports the claim.",
            "The excerpt does not support the claim.",
        ),
        (Subject("claim"), Subject("document")),
        (EvidenceSelector(DOCUMENT_EXCERPT),),
    )
    read_tool = Tool(
        READ_DOCUMENT,
        version,
        "Read the selected document from an application-supplied catalog.",
        reader,
        {
            "document_id": CandidateBinding(DOCUMENT_CANDIDATES, SELECT_DOCUMENT),
            "documents": HostContextBinding("documents"),
        },
        ToolEffect.READ,
        retry_owner=RetryOwner.CALLABLE,
        produces_evidence=(DOCUMENT_RECORD,),
        scope_requirements=("scope",),
    )
    extract_tool = Tool(
        EXTRACT_DOCUMENT_TEXT,
        version,
        "Copy the exact text field from the retained document record.",
        _extract_document_text,
        {
            "excerpt": SourceBinding(
                DOCUMENT_RECORD,
                SourceField(("text",)),
            )
        },
        ToolEffect.PURE,
        requires_evidence=(DOCUMENT_RECORD,),
        produces_evidence=(DOCUMENT_EXCERPT,),
    )
    capabilities = CapabilityPackage(
        package_id,
        version,
        (read_tool, extract_tool),
        (selection, assessment),
        (
            CandidateProvider(
                DOCUMENT_CANDIDATES,
                version,
                retrieve,
                {
                    "query": TaskInputBinding(("query",)),
                    "scope": HostContextBinding("scope"),
                    "documents": HostContextBinding("documents"),
                },
            ),
        ),
    )
    return DocumentEvidencePackage(
        capabilities,
        selection,
        assessment,
        SourceField(("text",)),
        {
            "selection": SELECT_DOCUMENT,
            "assessment": ASSESS_DOCUMENT_SUPPORT,
            "excerpt": DOCUMENT_EXCERPT,
        },
    )
