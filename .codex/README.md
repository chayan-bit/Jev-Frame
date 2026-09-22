# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- JF-22 / GitHub #23 local delivery is complete on `codex/jev-frame-implementation` and awaits GitHub delivery steps.
- `DELIVERY_EVIDENCE.md` records exact Scenario A-L and T01-T65 coverage, commands, versions, clean installations, installed examples, artifact inspection, live scope, and pending gates.
- The selected provider dependency is `typesafe-sdk==0.7.1`; the lockfile and credential-safe configuration regression are synchronized.
- A T38 regression proves planner cycles and unapproved mutations fail before tool dispatch.
- The full 142-test suite passes on CPython 3.11.15 and 3.14.6 with all extras.
- Ruff passes `src`, `tests`, and `examples`, and mypy passes all 22 source files.
- Fresh CPython 3.11 core-only, LangChain and LangGraph, and Pydantic AI wheel environments import the intended surfaces and run all documented examples.
- The wheel and source distribution pass path and private-marker inspection.
- Seven authorized synthetic requests support only the recorded TypeSafe SDK 0.7.1 and `jev-1.13.0` `TypeSafeProvider`, `DecisionClient`, and `Runtime` smoke.
- Live optional-framework, hybrid, fallback, and consequential-effect combinations remain pending, and Level E remains application-specific.
- No package was published, released, deployed, licensed, or used for a consequential real effect.
- The remaining action is to commit JF-22, create and review the pull request, merge it when accepted, and then start the separately prepared downstream-agent work.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
