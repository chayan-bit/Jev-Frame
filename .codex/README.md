# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: complete JF-05 official SDK transport and checks T14-T17, then implement JF-06 standalone decisions and shared admission accounting.
- State: branch `codex/jev-frame-implementation`; JF-01 through JF-04 are closed, and JF-05 has a passing offline implementation awaiting final verification, commit, and issue update.
- Decisions: Python 3.11 or newer, local import `jev_frame`, `typesafe-sdk==0.7.0`, direct `pydantic>=2.12,<3`, and the public names and finite type subset in README `Frozen initial contract`.
- Changed files: `src/jev_frame/compiler.py`, `src/jev_frame/provider.py`, `src/jev_frame/__init__.py`, `tests/test_provider.py`, README.md, IMPLEMENTATION_PLAN.md, ISSUES.md, and this checkpoint.
- Checks: `uv run python -m unittest discover -s tests -q` passed 40 tests; the same suite passed through isolated editable installs on CPython 3.11 and 3.14; Ruff check/format, mypy, compileall, `uv build`, an isolated CPython 3.11 wheel import, and `git diff --check` passed.
- Failures: GitHub MCP loading was unavailable, so live issues are read and updated through the authenticated GitHub CLI; no implementation blocker remains.
- Evidence: real SDK mock-transport requests preserve compiled Choice, Noul, and Score wire shapes; strict validation rejects unknown candidates, missing or mistyped answers, NaN, invalid distributions, rubric mismatch, and malformed SDK responses; near-zero Noul and fractional Score survive; retries remain bounded with one admission per real attempt; authentication is not retried; host-owned clients remain open; cancellation propagates; absent tokens remain unknown.
- Remaining gates: live provider compatibility was not exercised because paid or live calls are not authorized; standalone decisions, shared ledger admission, consequential effects, publication, deployment, and licensing remain assigned or unauthorized as documented.
- Next action: commit JF-05, post evidence, close #6, update tracker #1, then implement JF-06 standalone decision operations and concurrency-safe admission accounting.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
