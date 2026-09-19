# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: complete JF-16 objective-driven hybrid planning and T38, T49 through T53, and T62, then continue with the next live unblocked issue.
- State: branch `codex/jev-frame-implementation`; JF-01 through JF-15 are closed, and JF-16 is implemented and verified locally pending commit and issue update.
- Decisions: accept one asynchronous typed planner callable, validate every plan against registered capabilities and exact sources, dispatch only through the shared runtime, count calls and revisions in the shared ledger, stop unchanged revisions, and keep final semantic acceptance host-owned.
- Changed files: `src/jev_frame/planning.py`, shared compiler, runtime and limits modules, public exports, both optional framework adapters, two planning test modules, README.md, IMPLEMENTATION_PLAN.md, ISSUES.md, and this checkpoint.
- Checks: eight focused planning tests pass; all 108 tests pass with all extras and all 95 core tests pass with three skips on isolated CPython 3.11 and 3.14; Ruff, mypy, compileall, source and wheel builds, metadata inspection, and an isolated wheel import pass.
- Failures: the first repository-wide Ruff command omitted the ephemeral Ruff dependency and failed before linting; rerunning with `--with ruff` passed without source changes.
- Evidence: an unseen three-step plan completes with source-bound inputs, failed retrieval causes a changed proposal, invented tools and evidence never dispatch, unchanged plans stop, host rejection blocks completion, a composed specialist executes once, empty filtered candidates avoid a Jev call, and real offline LangChain and Pydantic AI planner interfaces preserve loop ownership.
- Remaining gates: no live provider, consequential real effect, application acceptance calibration, publication, deployment or licensing was exercised or authorized.
- Next action: inspect the staged diff, commit JF-16, update and close #17 and tracker #1, then select the next live unblocked issue.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
