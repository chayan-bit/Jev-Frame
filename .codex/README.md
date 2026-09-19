# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: complete JF-04 pure compilation, offline preview, and checks T10-T13/T58, then implement the JF-05 official SDK adapter.
- State: branch `codex/jev-frame-implementation`; JF-01 through JF-03 are closed, and JF-04 has a passing local implementation awaiting final verification, commit, and issue update.
- Decisions: Python 3.11 or newer, local import `jev_frame`, `typesafe-sdk==0.7.0`, direct `pydantic>=2.12,<3`, and the public names and finite type subset in README `Frozen initial contract`.
- Changed files: `src/jev_frame/definitions.py`, `src/jev_frame/compiler.py`, `src/jev_frame/__init__.py`, `tests/test_compiler.py`, README.md, IMPLEMENTATION_PLAN.md, ISSUES.md, and this checkpoint.
- Checks: `uv run python -m unittest discover -s tests -q` passed 33 tests; the same suite passed through isolated editable installs on CPython 3.11 and 3.14; Ruff check/format, mypy, compileall, `uv build`, an isolated CPython 3.11 wheel import, and `git diff --check` passed.
- Failures: GitHub MCP loading was unavailable, so live issues are read and updated through the authenticated GitHub CLI; no implementation blocker remains.
- Evidence: Scenario A compiles without calling provider or tool functions; opaque routing IDs preserve question semantics; dependent judgments occupy distinct stages; independent candidate selections cannot form a correlated tuple; oversized Choice and Score contracts fail without truncation; missing task, host, candidate, producer, and capability references have exact diagnostics; previews omit typed candidate values and callable objects.
- Remaining gates: no JF-04 live-provider gate exists; post-run inspection remains assigned to JF-07, while the SDK adapter, decision execution, consequential effects, publication, deployment, and licensing remain assigned or unauthorized as documented.
- Next action: commit JF-04, post evidence, close #5, update tracker #1, then implement JF-05 with the official TypeSafe SDK and deterministic client doubles.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
