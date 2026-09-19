# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: complete JF-09 shared read-only scheduling and checks T18 through T23, then implement JF-10 guarded write execution.
- State: branch `codex/jev-frame-implementation`; JF-01 through JF-08 are closed, and JF-09 has a fully verified offline implementation awaiting commit and issue update.
- Decisions: Python 3.11 or newer, local import `jev_frame`, `typesafe-sdk==0.7.0`, direct `pydantic>=2.12,<3`, and the public names and finite type subset in README `Frozen initial contract`.
- Changed files: `src/jev_frame/runtime.py`, `src/jev_frame/definitions.py`, `src/jev_frame/decisions.py`, `src/jev_frame/limits.py`, `src/jev_frame/inspection.py`, `src/jev_frame/packages.py`, `src/jev_frame/__init__.py`, `examples/document_evidence.py`, `tests/test_packages.py`, `tests/test_runtime.py`, README.md, IMPLEMENTATION_PLAN.md, ISSUES.md, and this checkpoint.
- Checks: 63 tests passed on the project Python and isolated CPython 3.11 and 3.14 editable installs; the public example, Ruff check/format, mypy over 20 source files, compileall, `uv build`, an isolated CPython 3.11 wheel import, and `git diff --check` passed.
- Failures: GitHub MCP loading was unavailable, so live issues are read and updated through the authenticated GitHub CLI; no implementation blocker remains.
- Evidence: Scenario A returns the exact selected source with provenance; dependent judgments use separate requests; concurrent definitions keep isolated evidence while sharing limits; inactive branches cannot complete; stale late answers remain historical; exhaustion, unsupported completion, provider failure, and cancellation are distinct; the synchronous wrapper rejects a running loop.
- Remaining gates: the JF-09 commit is pending; guarded writes remain JF-10, and live provider compatibility, publication, deployment and licensing remain unauthorized.
- Next action: inspect and commit the verified JF-09 diff, post evidence, close #10, update tracker #1, then implement JF-10 guarded execution.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
