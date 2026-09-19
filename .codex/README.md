# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: complete JF-02 package foundations and checks T01-T02, then implement JF-03 evidence state.
- State: branch `codex/jev-frame-implementation`; JF-01 is closed and JF-02 has a verified local implementation awaiting commit and issue update.
- Decisions: Python 3.11 or newer, local import `jev_frame`, `typesafe-sdk==0.7.0`, direct `pydantic>=2.12,<3`, and the public names and finite type subset in README `Frozen initial contract`.
- Changed files: `pyproject.toml`, `uv.lock`, `src/jev_frame/definitions.py`, `src/jev_frame/__init__.py`, `tests/test_definitions.py`, AGENTS.md, README.md, IMPLEMENTATION_PLAN.md, ISSUES.md, and this checkpoint.
- Checks: `uv run python -m unittest discover -s tests -v` passed 11 tests; the same command through isolated editable installs passed on CPython 3.11.15 and 3.14.6; `uvx ruff check src tests`, `uvx ruff format --check src tests`, `uv run --with mypy mypy src tests`, `uv run python -m compileall -q src tests`, `uv build`, and a CPython 3.11 isolated wheel import all passed.
- Failures: GitHub MCP loading was unavailable, so live issues are read and updated through the authenticated GitHub CLI; no implementation blocker remains.
- Evidence: missing bindings leave the synthetic callable untouched; strict validation rejects string-to-int and bool-to-string coercion; default omission and explicit `None` remain distinct; imports succeed without `TYPESAFE_API_KEY` or optional frameworks; unknown usage is represented by `None` plus `UsageCoverage.UNKNOWN`.
- Remaining gates: no JF-02 live gate remains; named adapters, provider calls, consequential effects, publication, deployment, and licensing remain assigned or unauthorized as documented.
- Next action: commit JF-02, post evidence, close #3, update tracker #1, then implement JF-03 evidence provenance and invalidation.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
