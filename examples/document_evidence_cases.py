"""Evaluator-only synthetic cases; this module is never imported by Jev-Frame."""

from dataclasses import dataclass

from jev_frame import DocumentEvidenceRequest


@dataclass(frozen=True, slots=True)
class RegressionCaseDescriptor:
    id: str
    package_version: str
    dataset_version: str
    group_id: str
    inputs: DocumentEvidenceRequest
    expected_selection: str
    evaluator_note: str


CASES = (
    RegressionCaseDescriptor(
        "catalog-a-launch-day",
        "1.0.0",
        "synthetic-v1",
        "launch-day",
        DocumentEvidenceRequest("launch day", "The launch occurred on Tuesday."),
        "a-1",
        "Evaluator-only expected answer for the synthetic A catalog.",
    ),
    RegressionCaseDescriptor(
        "catalog-b-launch-day",
        "1.0.0",
        "synthetic-v1",
        "launch-day",
        DocumentEvidenceRequest("launch day", "The launch was postponed to Friday."),
        "b-1",
        "Evaluator-only expected answer for the synthetic B catalog.",
    ),
)
