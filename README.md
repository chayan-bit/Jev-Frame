# Jev-Frame

Jev-Frame is a Python framework for building typed decision agents on top of TypeSafe's Jev API and for adding Jev decisions to existing LLM agents.
You describe typed tools, semantic judgments, candidate sets, completion contracts, and operating limits, and the framework compiles Jev questions, tracks evidence with provenance, schedules work under shared budgets, and returns either a supported typed result or an explicit unresolved outcome.
It is an independent open-source project and not an official TypeSafe product.
Live decisions need a TypeSafe API key, while definitions, compilation, previews, the offline runtime, fixtures, and the test suite run without any key or network access.

## Install

Jev-Frame requires Python 3.11 or newer.
It is not published on PyPI yet, so install it from a tagged Git revision:

```sh
pip install "jev-frame @ git+https://github.com/chayan-bit/Jev-Frame@v0.1.0"
```

Optional integrations are available as extras:

```sh
pip install "jev-frame[langchain] @ git+https://github.com/chayan-bit/Jev-Frame@v0.1.0"
pip install "jev-frame[pydantic-ai] @ git+https://github.com/chayan-bit/Jev-Frame@v0.1.0"
```

The `langchain` extra installs LangChain and LangGraph, and the `pydantic-ai` extra installs Pydantic AI Slim with its TypeSafe model.
Importing `jev_frame` performs no network request, credential lookup, or optional-framework import.

## Quickstart

This example evaluates one yes/no (Noul) judgment through the direct decision API.
It uses a scripted offline provider, so it runs without an API key.
The same code is in [`examples/quickstart.py`](examples/quickstart.py).

```python
"""Evaluate one Jev judgment offline with a scripted provider."""

import asyncio
import inspect
import time
from collections.abc import Sequence
from typing import Any

from jev_frame import (
    AttemptAdmission,
    AttemptStatus,
    DecisionClient,
    DecisionContext,
    DecisionInputs,
    Judgment,
    NoulAnswer,
    NoulQuestion,
    ProviderAttempt,
    ProviderBatch,
    RunLimits,
    Subject,
    Usage,
    UsageCoverage,
)
from jev_frame.compiler import CompiledQuestion


class OfflineProvider:
    """Answers every yes/no (Noul) question with probability 0.9."""

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
        return ProviderBatch(
            {question.routing_id: NoulAnswer(0.9) for question in questions},
            requested_model,
            "offline-model",
            None,
            Usage(UsageCoverage.COMPLETE, 3, 1, 1, len(questions)),
            (ProviderAttempt(attempt.id, 1, AttemptStatus.SUCCEEDED),),
        )


async def main() -> None:
    client = DecisionClient(OfflineProvider(), model="offline")
    judgment = Judgment(
        "is_clear",
        "1.0.0",
        NoulQuestion("Is the statement clear?"),
        (Subject("statement"),),
    )
    limits = RunLimits(
        provider_attempts=1,
        submitted_questions=1,
        tool_attempts=0,
        investigation_steps=0,
        concurrent_operations=1,
        writes=0,
        planner_calls=0,
        plan_revisions=0,
        child_depth=0,
        child_runs=0,
    )
    result = await client.evaluate(
        judgment,
        DecisionInputs("q-1", {"statement": "Typed boundaries are explicit."}),
        DecisionContext("quickstart", time.monotonic() + 30.0, limits),
    )
    print(result.answer, result.returned_model, result.usage.submitted_questions)


if __name__ == "__main__":
    asyncio.run(main())
```

Running it prints:

```text
NoulAnswer(probability_yes=0.9) offline-model 1
```

To make a live call, replace the offline provider with the official SDK adapter and pin a Jev model.
`TypeSafeProvider` reads `TYPESAFE_API_KEY` from the environment when no key is passed.

```python
from jev_frame import TypeSafeProvider

async with TypeSafeProvider() as provider:
    client = DecisionClient(provider, model="jev-1.13.0")
    result = await client.evaluate(judgment, inputs, context)
```

More examples:

- [`examples/document_evidence.py`](examples/document_evidence.py) binds the generic document-evidence capability package to two host catalogs.
- [`examples/langchain_decision.py`](examples/langchain_decision.py) runs a Jev decision as a tool inside a host-owned LangGraph `ToolNode` (needs the `langchain` extra).
- [`examples/pydantic_ai_decision.py`](examples/pydantic_ai_decision.py) runs a Jev decision as a tool inside a host-owned Pydantic AI agent (needs the `pydantic-ai` extra).

## API overview

Everything public is exported from the top-level `jev_frame` package.

| Area | Main names | Purpose |
|---|---|---|
| Definitions | `Judgment`, `ChoiceQuestion`, `NoulQuestion`, `ScoreQuestion`, `Tool`, `AgentDefinition`, `RunLimits`, `RunContext` | Strict, versioned descriptions of decisions, tools, agents, and operating limits. |
| Direct decisions | `DecisionClient`, `DecisionInputs`, `DecisionResult` | Call `evaluate`, `assess`, `score`, `select`, `filter`, or `extract_source` without adopting the scheduler. |
| Provider | `TypeSafeProvider` | Asynchronous adapter over the official `typesafe-sdk` with bounded retries and strict response validation. |
| Evidence state | `EvidenceStore`, `Evidence`, `CandidateSet`, `Candidate` | Immutable candidate snapshots, provenance records, scoped views, fingerprints, and selective invalidation. |
| Compiler | `compile_agent`, `compile_judgment`, `preview_agent` | Pure dependency compilation and serializable offline previews with no dispatch. |
| Runtime | `Runtime`, `CompletionCheck`, `ChildRunPolicy` | Shared scheduler for reads, guarded mutations, completion checks, cancellation, and child runs. |
| Policy | `AcceptancePolicy`, `Authorizer`, `ActionProposal`, `ExecutionReceipt` | Versioned acceptance, exact-action authorization, and reconciliation of uncertain writes. |
| Planning | `Planner`, `PlanStep`, `propose_select` | Bounded LLM-driven planning and replanning over registered capabilities. |
| Artifacts and documents | `GenerateVerifyRecipe`, `DocumentCollectionWorkflow`, `bind_document_evidence_package` | Generate-verify-revise loops and document claim assessment with exact passage provenance. |
| Inspection | `EventLog`, `inspect_decision`, `serialize_decision_result` | Sanitized events, permitted inspection projections, and actionable diagnostics. |
| Fixtures and evaluation | `capture_fixture`, `OfflineReplay`, `run_evaluations`, `calibrate_policies` | Sanitized regression fixtures, offline replay, grouped evaluation reports, and policy calibration. |
| Integrations | `jev_frame.integrations.langchain`, `jev_frame.integrations.pydantic_ai` | Decision tools, checkpoints, and planner adapters for host-owned LangChain, LangGraph, and Pydantic AI loops. |

See [docs/architecture.md](docs/architecture.md) for the full design and public contracts, [docs/design.md](docs/design.md) for the original implementation plan, and [docs/verification.md](docs/verification.md) for the 0.1.0 verification record.

## Development

The project uses [uv](https://docs.astral.sh/uv/) and a checked-in lockfile.

```sh
uv sync --frozen --all-extras
uv run --frozen --all-extras python -m unittest discover -s tests -v
uv run --frozen --all-extras ruff check src tests examples
uv run --frozen --all-extras mypy src
uv build
```

The test suite is fully offline and never needs credentials.
See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines and [SECURITY.md](SECURITY.md) for reporting vulnerabilities.

## Further reading

- [TypeSafe documentation index](https://docs.typesafe.ai/llms.txt)
- [HTTP API](https://docs.typesafe.ai/api.md)
- [Primitives](https://docs.typesafe.ai/primitives.md)
- [Confidence](https://docs.typesafe.ai/confidence.md)
- [Pydantic AI TypeSafe integration](https://ai.pydantic.dev/models/typesafe/)
- [LangGraph workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)

## License

Jev-Frame is released under the [MIT License](LICENSE).
