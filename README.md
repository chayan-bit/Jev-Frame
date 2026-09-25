# Jev-Frame

**Typed, auditable Jev decisions for Python agents, with an optional shared runtime.**

[![CI](https://github.com/chayan-bit/Jev-Frame/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/chayan-bit/Jev-Frame/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/chayan-bit/Jev-Frame?sort=semver)](https://github.com/chayan-bit/Jev-Frame/releases)
[![License: MIT](https://img.shields.io/github/license/chayan-bit/Jev-Frame)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![Typed](https://img.shields.io/badge/typing-typed-informational)](src/jev_frame/py.typed)

<p align="center">
  <img src="docs/demos/quickstart.gif" alt="Running the Jev-Frame quickstart offline: one typed yes/no judgment returns NoulAnswer(probability_yes=0.9)" width="760">
  <br>
  <sub><a href="docs/demos/quickstart.mp4">MP4 version</a> · rendered from <a href="docs/demos/quickstart.tape">docs/demos/quickstart.tape</a></sub>
</p>

Jev-Frame is a Python framework for building typed decision agents on top of TypeSafe's Jev API and for adding Jev decisions to agents you already have.
You describe typed tools, judgments, candidate sets, completion contracts, and operating limits.
The framework compiles Jev questions, tracks evidence with provenance, schedules work under shared budgets, and returns either a supported typed result or an explicit unresolved outcome.
It is an independent open-source project and not an official TypeSafe product.

Looking for a drop-in way to attach Jev to an existing coding-agent harness?
See the companion project [jev-harness](https://github.com/chayan-bit/jev-harness), which is built on Jev-Frame.

## Why Jev-Frame

Jev answers structured questions (Choice, Noul, and Score) with probabilities instead of generating free text.
That makes it a good fit for the decision points of an agent: which document to trust, whether a claim is supported, how good a draft is, or whether an action may proceed.
Using it well still takes a lot of plumbing: candidate binding, evidence freshness, retries, budgets, no-fit handling, and a clear line between "the model is confident" and "the action is authorized".
Jev-Frame is that plumbing, written once, typed, and tested offline.

## Features

- **Direct decisions.** Call `evaluate`, `select`, `filter`, `assess`, `score`, or `extract_source` from any code without adopting a scheduler.
- **Typed, strict boundaries.** Definitions are immutable and versioned, values are validated strictly, and scalars are never coerced silently.
- **Candidate sets with honest no-fit.** Jev can only select what it was shown, an empty complete snapshot resolves to no-fit without a provider call, and truncated retrieval never claims global absence.
- **Evidence with provenance.** Append-only records, scoped views, fingerprints, conflict links, and selective invalidation when inputs change.
- **Offline preview.** Compile questions, candidate metadata, and argument sources to JSON before any dispatch.
- **Shared runtime (optional).** Dependency-aware scheduling, bounded investigation, guarded mutations with exact-action authorization, typed child agents, and LLM planning under one budget.
- **Evaluation and calibration.** Sanitized fixtures, offline replay, grouped leakage-safe evaluation reports, frozen policy calibration, and side-effect-free shadow comparisons.
- **Framework adapters.** Decision tools and checkpoints for host-owned LangChain, LangGraph, and Pydantic AI loops.
- **Offline by default.** Importing `jev_frame` performs no network request or credential lookup, and the whole test suite runs without an API key.

## Install

Jev-Frame requires Python 3.11 or newer.
It is not published on PyPI yet, so install it from a tagged Git revision:

```sh
pip install "jev-frame @ git+https://github.com/chayan-bit/Jev-Frame@v0.1.1" # x-release-please-version
```

Optional integrations are available as extras:

```sh
pip install "jev-frame[langchain] @ git+https://github.com/chayan-bit/Jev-Frame@v0.1.1" # x-release-please-version
pip install "jev-frame[pydantic-ai] @ git+https://github.com/chayan-bit/Jev-Frame@v0.1.1" # x-release-please-version
```

The `langchain` extra installs LangChain and LangGraph, and the `pydantic-ai` extra installs Pydantic AI Slim with its TypeSafe model.

## Quickstart (60 seconds, no API key)

This evaluates one yes/no (Noul) judgment through the direct decision API.
It uses a scripted offline provider, so it runs without an API key or network access.
The same code is in [`examples/quickstart.py`](examples/quickstart.py).

<!-- same-as: examples/quickstart.py -->
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
    PrimitiveAnswer,
    ProviderAttempt,
    ProviderBatch,
    RunLimits,
    Subject,
    Usage,
    UsageCoverage,
)
from jev_frame.compiler import CompiledQuestion

# Every class of work needs an explicit finite budget; zero disables it.
LIMITS = RunLimits(
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


class OfflineProvider:
    """Answers every yes/no (Noul) question with probability 0.9."""

    def answer(self, question: CompiledQuestion) -> PrimitiveAnswer:
        return NoulAnswer(0.9)

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
            {question.routing_id: self.answer(question) for question in questions},
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
    result = await client.evaluate(
        judgment,
        DecisionInputs("q-1", {"statement": "Typed boundaries are explicit."}),
        DecisionContext("quickstart", time.monotonic() + 30.0, LIMITS),
    )
    print(result.answer, result.returned_model, result.usage.submitted_questions)


if __name__ == "__main__":
    asyncio.run(main())
```

Running it prints:

```text
NoulAnswer(probability_yes=0.9) offline-model 1
```

To make a live call, construct `TypeSafeProvider()` instead of `OfflineProvider()` inside `async with`, and pin a Jev model such as `model="jev-1.13.0"`.
`TypeSafeProvider` reads `TYPESAFE_API_KEY` from the environment when you do not pass `api_key=...`.

## Core concepts

| Concept | What it is |
|---|---|
| `Judgment` | A versioned question with one primitive (`ChoiceQuestion`, `NoulQuestion`, or `ScoreQuestion`), named subjects, evidence selectors, and an optional candidate set. |
| `DecisionClient` | The smallest surface: direct decision operations over a supplied context, with shared admission and usage accounting. |
| `DecisionContext` / `RunContext` | Scope, a monotonic deadline, `RunLimits`, and optional host dependencies, event sink, and identifiers for one operation or run. |
| `RunLimits` | Finite budgets for provider attempts, questions, tools, investigation, concurrency, writes, planning, and child runs. |
| `CandidateSet` | An immutable, scoped snapshot of the options Jev may choose from, with coverage (`COMPLETE`, `TRUNCATED`, `UNKNOWN`, or `FAILED`). |
| `EvidenceStore` | Append-only observations, derivations, judgments, acceptance, and execution references with provenance and invalidation. |
| `AgentDefinition` + `Runtime` | Optional: a versioned agent (tools, judgments, completion contract, operating policy) run by the shared scheduler. |
| `AcceptancePolicy` / `Authorizer` | Separate host-owned decisions: whether a result is accepted, and whether one exact action may execute. |

A decision without an acceptance policy is `unassessed`: it is a useful observation, but it cannot complete an agent run or authorize an action.

## Usage guides

The snippets below continue from the quickstart and reuse its `OfflineProvider`, `LIMITS`, and imports.
Every code block in this README is executed in CI by [`scripts/check_readme.py`](scripts/check_readme.py).

### Select among candidates

Give Jev an explicit snapshot of candidates and it returns one of them, or no-fit.
This provider always picks the first option so the output is deterministic.

```python
from jev_frame import Candidate, CandidateSet, ChoiceAnswer, ChoiceQuestion, Coverage


class FirstOptionProvider(OfflineProvider):
    """Picks the first option of every Choice question with confidence 0.8."""

    def answer(self, question):
        keys = [option.key for option in question.options]
        rest = 0.2 / (len(keys) - 1)
        return ChoiceAnswer(keys[0], {key: 0.8 if key == keys[0] else rest for key in keys}, 0.8)


catalog = CandidateSet(
    "documents",
    "1.0.0",
    (
        Candidate("doc-1", "release-notes.md", "Release notes for 0.1.0", "docs", "v3"),
        Candidate("doc-2", "onboarding.md", "Guide for new contributors", "docs", "v7"),
    ),
    Coverage.COMPLETE,
    "quickstart",
)
pick_document = Judgment(
    "pick_document",
    "1.0.0",
    ChoiceQuestion("Which document answers the question?"),
    (Subject("question"),),
    candidate_set="documents",
)


async def select(snapshot):
    client = DecisionClient(FirstOptionProvider(), model="offline")
    inputs = DecisionInputs(
        "q-2", {"question": "What changed in 0.1.0?"}, candidate_sets={"documents": snapshot}
    )
    context = DecisionContext("quickstart", time.monotonic() + 30.0, LIMITS)
    return await client.select(pick_document, inputs, context)


picked = asyncio.run(select(catalog))
print(picked.selection.outcome.value, picked.selection.candidate.value)

empty = CandidateSet("documents", "1.0.0", (), Coverage.COMPLETE, "quickstart")
nothing = asyncio.run(select(empty))
print(nothing.selection.outcome.value, nothing.usage.provider_attempts)
```

```text
selected release-notes.md
no_fit 0
```

The selected candidate's execution value (`release-notes.md`) never reaches the model; Jev only sees keys and descriptions.
The empty snapshot resolved to no-fit deterministically, with zero provider attempts.

### Preview compiled questions before dispatch

`compile_judgment` and `preview_agent` are pure: they call no provider and no tool.

```python
from jev_frame import compile_judgment

question = compile_judgment(pick_document, candidate_set=catalog)
print(question.primitive, [option.key for option in question.options])
```

```text
choice ['doc-1', 'doc-2', '__jev_frame_no_fit__']
```

The reserved no-fit option is always added to dynamic Choice questions, so Jev is never forced to pick a wrong candidate.
`preview_agent(definition)` returns the same information for a whole `AgentDefinition` as JSON-compatible data.

### Inspect and serialize results

`serialize_decision_result` emits an allowlisted record that is safe to log or return to a model.

```python
from jev_frame import serialize_decision_result

record = serialize_decision_result(picked.decision)
print(record["answer"]["choice"], record["answer"]["confidence"], record["usage"]["coverage"])
print(sorted(record))
```

```text
doc-1 0.8 complete
['acceptance', 'answer', 'evidence_refs', 'input_fingerprint', 'requested_model', 'returned_model', 'schema_version', 'subjects', 'usage']
```

Evidence values, exact questions, and candidate contents stay out of the record unless you pass an explicit `InspectionProjection.permitted_exact(...)` to `inspect_decision`.

### Use Jev inside LangGraph or Pydantic AI

The host framework keeps its loop, memory, and tool dispatch; Jev-Frame supplies a decision tool.

<p align="center"><img src="docs/demos/frameworks.gif" alt="Running the LangGraph ToolNode and Pydantic AI examples offline" width="760"></p>

- [`examples/langchain_decision.py`](examples/langchain_decision.py) runs a Jev decision as a tool inside a host-owned LangGraph `ToolNode` (needs the `langchain` extra).
- [`examples/pydantic_ai_decision.py`](examples/pydantic_ai_decision.py) runs a Jev decision as a tool inside a host-owned Pydantic AI agent (needs the `pydantic-ai` extra).
- `required_checkpoint_node` (LangGraph) and `required_checkpoint_output` (Pydantic AI) put a Jev check on a route the model cannot skip.

### Reuse one decision package across catalogs

<p align="center"><img src="docs/demos/documents.gif" alt="Binding the document-evidence package to two host catalogs" width="760"></p>

[`examples/document_evidence.py`](examples/document_evidence.py) binds the generic document-evidence package to two different host catalogs without changing the package.
[`examples/document_evidence_cases.py`](examples/document_evidence_cases.py) keeps evaluator-only expected answers in a separate module that Jev-Frame never imports.

### Calibrate before you trust a threshold

`run_evaluations`, `calibrate_policies`, `evaluate_frozen_policy`, and `run_shadow_comparison` compare acceptance policies on grouped validation cases, freeze one, and report on held-out cases.
The [jev-harness calibration example](https://github.com/chayan-bit/jev-harness/blob/main/examples/calibration.py) runs that flow end to end on a synthetic corpus.

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
| Planning | `PlannerEngine`, `PlanStep`, `propose_select` | Bounded LLM-driven planning and replanning over registered capabilities. |
| Artifacts and documents | `GenerateVerifyRecipe`, `DocumentCollectionWorkflow`, `bind_document_evidence_package` | Generate-verify-revise loops and document claim assessment with exact passage provenance. |
| Inspection | `EventLog`, `inspect_decision`, `serialize_decision_result` | Sanitized events, permitted inspection projections, and actionable diagnostics. |
| Fixtures and evaluation | `capture_fixture`, `OfflineReplay`, `run_evaluations`, `calibrate_policies` | Sanitized regression fixtures, offline replay, grouped evaluation reports, and policy calibration. |
| Integrations | `jev_frame.integrations.langchain`, `jev_frame.integrations.pydantic_ai` | Decision tools, checkpoints, and planner adapters for host-owned LangChain, LangGraph, and Pydantic AI loops. |

The [architecture guide](docs/architecture.md) documents every contract in depth, and the [documentation index](docs/README.md) lists everything else.

## Safety and authority boundaries

- **Confidence is not permission.** Acceptance (`AcceptancePolicy`) and execution authority (`Authorizer`) are separate, host-owned records, and an unassessed decision authorizes nothing.
- **Mutations are gated.** A `MUTATION` tool runs only after a versioned policy, any required checkpoint, a current exact-action authorization, revalidated arguments and sources, write admission, and durable intent.
- **No blind retries.** An ambiguous write is recorded as `outcome_unknown` and only the tool's declared reconciliation lookup may run.
- **Jev only picks what it saw.** Selections resolve against the exact recorded snapshot, and changed evidence makes late answers stale.
- **Bounded everything.** Every class of work has a finite budget and a monotonic deadline, and cancellation propagates to child work.
- **No hidden I/O.** Import performs no network or credential access, no telemetry is configured by default, and diagnostics never copy credentials or host dependency values.
- **Host owns the rest.** Tenant scope, storage, approvals, and side effects outside Jev-Frame stay with your application.

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities and handling keys.

## FAQ

**Do I need a TypeSafe API key?**
Only for live decisions.
Definitions, compilation, previews, the offline runtime, fixtures, examples, and the test suite all run without one.

**Is this an official TypeSafe project?**
No, it is an independent MIT-licensed project that uses the official `typesafe-sdk`.

**Do I have to use the Jev-Frame runtime?**
No.
`DecisionClient` works inside any loop, and the LangChain and Pydantic AI adapters leave loop ownership with the host framework.

**Why not just ask an LLM for JSON?**
Jev returns probability distributions over options you supply, which lets you set thresholds, detect no-fit, and audit exactly what was asked.
Jev-Frame keeps those guarantees intact across retries, budgets, and evidence changes.

**Which Python versions are supported?**
Python 3.11 and newer; CI runs the suite on 3.11 and 3.14.

**Is it on PyPI?**
Not yet; install from a tagged Git revision as shown above.

## Roadmap

Planned work and ideas are tracked in [GitHub issues](https://github.com/chayan-bit/Jev-Frame/issues) and [discussions](https://github.com/chayan-bit/Jev-Frame/discussions).
Release history is in [CHANGELOG.md](CHANGELOG.md).

## Development

The project uses [uv](https://docs.astral.sh/uv/) and a checked-in lockfile.

```sh
uv sync --frozen --all-extras
uv run --frozen --all-extras python -m unittest discover -s tests
uv run --frozen --all-extras ruff check src tests examples scripts
uv run --frozen --all-extras mypy src
uv build
```

The test suite is fully offline and never needs credentials.

## Contributing

Contributions are welcome.
Read [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow, commit conventions, and the demo-video requirement for pull requests, and follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

Jev-Frame is released under the [MIT License](LICENSE).
