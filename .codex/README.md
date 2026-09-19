# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: complete JF-07 sanitized events, result inspection, actionable diagnostics, and checks T39/T58, then implement JF-08 reusable decision packages.
- State: branch `codex/jev-frame-implementation`; JF-01 through JF-06 are closed, and JF-07 has a fully verified offline implementation awaiting commit and issue update.
- Decisions: Python 3.11 or newer, local import `jev_frame`, `typesafe-sdk==0.7.0`, direct `pydantic>=2.12,<3`, and the public names and finite type subset in README `Frozen initial contract`.
- Changed files: `src/jev_frame/inspection.py`, `src/jev_frame/decisions.py`, `src/jev_frame/definitions.py`, `src/jev_frame/state.py`, `src/jev_frame/__init__.py`, `tests/test_inspection.py`, README.md, IMPLEMENTATION_PLAN.md, ISSUES.md, and this checkpoint.
- Checks: 50 tests passed on the project Python and isolated CPython 3.11 and 3.14 editable installs; Ruff check/format, mypy, compileall, `uv build`, an isolated CPython 3.11 wheel import, and `git diff --check` passed.
- Failures: GitHub MCP loading was unavailable, so live issues are read and updated through the authenticated GitHub CLI; no implementation blocker remains.
- Evidence: direct decisions emit correlated schema-versioned start, attempt, completion, failure and cancellation events; attempt IDs and usage coverage survive round trips; default inspection resolves recorded provenance while redacting evidence, questions, candidate contents, arbitrary exception text, dependency values and authorization values; explicit permitted projection reveals only requested exact fields; accepted bindings and policy evidence are verified; diagnostics separate definition, service and semantic outcomes and name corrective inputs.
- Remaining gates: direct-decision inspection is locally verified only; scheduler-wide run inspection, fixture capture/replay, durable persistence, live provider compatibility, consequential effects, publication, deployment, and licensing remain assigned or unauthorized as documented.
- Next action: commit JF-07, post evidence, close #8, update tracker #1, then implement JF-08 reusable decision packages and generic evidence package.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
