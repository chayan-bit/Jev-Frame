# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: complete JF-08 reusable decision packages, the generic document-evidence package, and check T57, then implement JF-09 shared read-only scheduling.
- State: branch `codex/jev-frame-implementation`; JF-01 through JF-07 are closed, and JF-08 has a fully verified offline implementation awaiting commit and issue update.
- Decisions: Python 3.11 or newer, local import `jev_frame`, `typesafe-sdk==0.7.0`, direct `pydantic>=2.12,<3`, and the public names and finite type subset in README `Frozen initial contract`.
- Changed files: `src/jev_frame/packages.py`, `src/jev_frame/definitions.py`, `src/jev_frame/compiler.py`, `src/jev_frame/__init__.py`, `examples/document_evidence.py`, `examples/document_evidence_cases.py`, `tests/test_packages.py`, the adjusted candidate-provider fixtures, README.md, IMPLEMENTATION_PLAN.md, ISSUES.md, and this checkpoint.
- Checks: 55 tests passed on the project Python and isolated CPython 3.11 and 3.14 editable installs; the public example, Ruff check/format, mypy, compileall, `uv build`, an isolated CPython 3.11 wheel import, and `git diff --check` passed.
- Failures: GitHub MCP loading was unavailable, so live issues are read and updated through the authenticated GitHub CLI; no implementation blocker remains.
- Evidence: one generic package binds two typed retrieval and read implementations without code changes; candidate-provider and tool bindings keep catalogs in host context; package parts run through direct selection, assessment and exact-source extraction; missing functions, incompatible annotations and duplicate capability IDs fail before execution; package-only version changes alter the compiled digest; evaluator cases remain outside runtime definitions and provider inputs.
- Remaining gates: the read-only scheduler is not implemented, large-collection evidence processing remains JF-18, adapter demonstrations remain JF-12/JF-13, and live provider compatibility, publication, deployment and licensing remain unauthorized.
- Next action: commit JF-08, post evidence, close #9, update tracker #1, then implement JF-09 shared read-only scheduling and completion.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
