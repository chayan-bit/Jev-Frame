import inspect
import unittest
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from jev_frame import (
    ArtifactCheck,
    ArtifactCheckKind,
    ArtifactCheckResult,
    ArtifactCompletionContract,
    ArtifactSemanticCheck,
    AttemptAdmission,
    AttemptStatus,
    CompiledQuestion,
    GenerateVerifyRecipe,
    Judgment,
    NoulAnswer,
    NoulQuestion,
    PlannerCapability,
    ProviderAttempt,
    ProviderBatch,
    RunContext,
    RunLimits,
    Runtime,
    Subject,
    TaskInputBinding,
    TerminalStatus,
    Tool,
    UnresolvedReason,
    Usage,
    UsageCoverage,
)


@dataclass(frozen=True, slots=True)
class Draft:
    title: str
    body: str


class SemanticProvider:
    def __init__(self, probabilities: Sequence[float] = (0.99,)) -> None:
        self.calls: list[str] = []
        self.probabilities = tuple(probabilities)

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
        self.calls.append(operation_id)
        question = questions[0]
        probability = self.probabilities[len(self.calls) - 1]
        return ProviderBatch(
            {question.routing_id: NoulAnswer(probability)},
            requested_model,
            "offline",
            operation_id,
            Usage(UsageCoverage.COMPLETE, 2, 1, 1, 1),
            (ProviderAttempt(attempt.id, 1, AttemptStatus.SUCCEEDED),),
        )


def context(identifier: str) -> RunContext:
    return RunContext(
        "fixture",
        100.0,
        RunLimits(2, 2, 8, 0, 2, 0, 8, 8, 0, 0),
        clock=lambda: 0.0,
        run_id=identifier,
    )


def recipe(
    generator: Any,
    exact_check: Any,
    provider: SemanticProvider,
    *,
    max_revisions: int = 2,
) -> tuple[GenerateVerifyRecipe[Draft], Runtime]:
    generator_capability = PlannerCapability(
        Tool(
            "draft",
            "1.0.0",
            "Generate one draft from bounded feedback.",
            generator,
            {"prompt": TaskInputBinding(("prompt",))},
        ),
        generated_parameters=("prompt",),
    )
    deterministic = ArtifactCheck(
        PlannerCapability(
            Tool(
                "exact-title",
                "1.0.0",
                "Require a non-empty title.",
                exact_check,
                {"artifact": TaskInputBinding(("artifact",))},
            )
        ),
        "artifact",
        ("title",),
    )
    judgment = Judgment(
        "semantic-body",
        "1.0.0",
        NoulQuestion("Is the artifact body suitable?"),
        (Subject("artifact"),),
    )
    semantic = ArtifactSemanticCheck[Draft](
        judgment,
        lambda artifact: {"artifact": artifact.body},
        lambda decision: ArtifactCheckResult(
            isinstance(decision.answer, NoulAnswer)
            and decision.answer.probability_yes >= 0.9,
            "The body satisfies the semantic check.",
            "body",
        ),
        supports_fields=("body",),
    )
    value = GenerateVerifyRecipe[Draft](
        Draft,
        generator_capability,
        "prompt",
        (deterministic,),
        (semantic,),
        ArtifactCompletionContract(
            ("exact-title", "semantic-body"), ("title", "body")
        ),
        max_revisions,
        "step",
    )
    runtime = Runtime(
        provider,
        model="offline",
        completion_checks={"step": lambda value, store: True},
    )
    return value, runtime


class ArtifactRecipeTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_feedback_revises_before_semantic_acceptance(self) -> None:
        prompts: list[str] = []
        exact_values: list[Draft] = []

        def generate(prompt: str) -> Draft:
            prompts.append(prompt)
            if len(prompts) == 1:
                return Draft("", "raise SystemExit('not executed')")
            return Draft("Verified", "raise SystemExit('not executed')")

        def exact(artifact: Draft) -> ArtifactCheckResult:
            exact_values.append(artifact)
            return ArtifactCheckResult(
                bool(artifact.title),
                "Add a title." if not artifact.title else "The title is present.",
                "title",
            )

        provider = SemanticProvider()
        value, runtime = recipe(generate, exact, provider)
        result = await value.run(runtime, "Produce a verified draft.", context("revise"))

        self.assertIs(result.status, TerminalStatus.COMPLETED)
        self.assertEqual(result.value.title, "Verified")
        self.assertEqual(len(result.revisions), 2)
        self.assertNotEqual(result.revisions[0].digest, result.revisions[1].digest)
        self.assertEqual([item.title for item in exact_values], ["", "Verified"])
        self.assertIn('"findings"', prompts[1])
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(
            [finding.check_kind for finding in result.findings],
            [
                ArtifactCheckKind.DETERMINISTIC,
                ArtifactCheckKind.DETERMINISTIC,
                ArtifactCheckKind.SEMANTIC,
            ],
        )
        current = result.revisions[-1]
        current_findings = [
            finding
            for finding in result.findings
            if finding.artifact_revision_id == current.id
        ]
        self.assertTrue(all(finding.passed for finding in current_findings))
        self.assertEqual(
            {
                field
                for finding in current_findings
                for field in finding.supports_fields
            },
            {"title", "body"},
        )
        self.assertIsNotNone(runtime.ledger)
        snapshot = await runtime.ledger.snapshot()  # type: ignore[union-attr]
        self.assertEqual(snapshot.provider_attempts, 1)
        self.assertEqual(snapshot.tool_attempts, 5)
        self.assertEqual(snapshot.planner_calls, 6)
        self.assertEqual(snapshot.plan_revisions, 5)

    async def test_required_exact_error_blocks_high_semantic_score(self) -> None:
        def generate(prompt: str) -> Draft:
            return Draft("", "looks plausible")

        def exact(artifact: Draft) -> ArtifactCheckResult:
            raise RuntimeError("private-validator-detail")

        provider = SemanticProvider()
        value, runtime = recipe(generate, exact, provider, max_revisions=1)
        result = await value.run(runtime, "Produce a draft.", context("error"))

        self.assertIs(result.status, TerminalStatus.UNRESOLVED)
        self.assertIs(result.unresolved[0].reason, UnresolvedReason.BUDGET_EXHAUSTION)
        self.assertEqual(provider.calls, [])
        self.assertEqual(len(result.findings), 1)
        self.assertFalse(result.findings[0].passed)
        self.assertNotIn("private-validator-detail", result.findings[0].message)

    async def test_new_revision_recomputes_old_passing_checks(self) -> None:
        generated = iter((Draft("First", "weak"), Draft("Second", "supported")))
        exact_values: list[Draft] = []

        def generate(prompt: str) -> Draft:
            return next(generated)

        def exact(artifact: Draft) -> ArtifactCheckResult:
            exact_values.append(artifact)
            return ArtifactCheckResult(True, "The title is present.", "title")

        provider = SemanticProvider((0.1, 0.99))
        value, runtime = recipe(generate, exact, provider)
        result = await value.run(runtime, "Produce a draft.", context("recheck"))

        self.assertIs(result.status, TerminalStatus.COMPLETED)
        self.assertEqual(result.value, Draft("Second", "supported"))
        self.assertEqual(
            exact_values, [revision.value for revision in result.revisions]
        )
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(
            [
                finding.artifact_revision_id
                for finding in result.findings
                if finding.check_id == "exact-title"
            ],
            [revision.id for revision in result.revisions],
        )

    async def test_identical_artifact_stops_without_rechecking(self) -> None:
        generator_calls = 0
        exact_calls = 0

        def generate(prompt: str) -> Draft:
            nonlocal generator_calls
            generator_calls += 1
            return Draft("", "unchanged")

        def exact(artifact: Draft) -> ArtifactCheckResult:
            nonlocal exact_calls
            exact_calls += 1
            return ArtifactCheckResult(False, "Add a title.", "title")

        provider = SemanticProvider()
        value, runtime = recipe(generate, exact, provider, max_revisions=3)
        result = await value.run(runtime, "Produce a draft.", context("repeat"))

        self.assertIs(result.status, TerminalStatus.UNRESOLVED)
        self.assertIs(result.unresolved[0].reason, UnresolvedReason.NO_PROGRESS)
        self.assertEqual(generator_calls, 2)
        self.assertEqual(exact_calls, 1)
        self.assertEqual(len(result.revisions), 1)
        self.assertEqual(provider.calls, [])


if __name__ == "__main__":
    unittest.main()
