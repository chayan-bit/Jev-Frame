# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: complete JF-03 evidence provenance, candidate snapshots, and checks T03-T09, then implement the JF-04 pure compiler.
- State: branch `codex/jev-frame-implementation`; JF-01 and JF-02 are closed, and JF-03 has a verified local implementation awaiting commit and issue update.
- Decisions: Python 3.11 or newer, local import `jev_frame`, `typesafe-sdk==0.7.0`, direct `pydantic>=2.12,<3`, and the public names and finite type subset in README `Frozen initial contract`.
- Changed files: `src/jev_frame/definitions.py`, `src/jev_frame/state.py`, `src/jev_frame/__init__.py`, `tests/test_definitions.py`, `tests/test_state.py`, README.md, IMPLEMENTATION_PLAN.md, ISSUES.md, and this checkpoint.
- Checks: `uv run python -m unittest discover -s tests -q` passed 22 tests; the same suite passed through isolated editable installs on CPython 3.11 and 3.14; `uvx ruff check src tests`, `uvx ruff format --check src tests`, `uv run --with mypy mypy src tests`, `uv run python -m compileall -q src tests`, `uv build`, an isolated CPython 3.11 wheel import, and `git diff --check` passed.
- Failures: GitHub MCP loading was unavailable, so live issues are read and updated through the authenticated GitHub CLI; no implementation blocker remains.
- Evidence: candidate identity survives duplicate labels and revisions; complete, truncated, unknown, failed, and no-fit outcomes stay distinct; candidate order and semantic metadata alter fingerprints; exact Unicode spans retain source identity; scope and freshness are checked at use time; conflicts are preserved or projection fails; invalidation is selective and transitive; completed effects remain historical while later dependent reasoning becomes stale.
- Remaining gates: no JF-03 live-provider gate exists; compiler, named adapters, provider calls, consequential effects, publication, deployment, and licensing remain assigned or unauthorized as documented.
- Next action: commit JF-03, post evidence, close #4, update tracker #1, then implement JF-04 compiler and preview behavior.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
