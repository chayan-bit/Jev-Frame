# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: complete JF-06 standalone decisions, shared admission, and checks T17/T21/T44/T56, then implement JF-07 sanitized events and inspection.
- State: branch `codex/jev-frame-implementation`; JF-01 through JF-05 are closed, and JF-06 has a fully verified offline implementation awaiting commit and issue update.
- Decisions: Python 3.11 or newer, local import `jev_frame`, `typesafe-sdk==0.7.0`, direct `pydantic>=2.12,<3`, and the public names and finite type subset in README `Frozen initial contract`.
- Changed files: `src/jev_frame/compiler.py`, `src/jev_frame/state.py`, `src/jev_frame/limits.py`, `src/jev_frame/decisions.py`, `src/jev_frame/__init__.py`, `tests/test_decisions.py`, README.md, IMPLEMENTATION_PLAN.md, ISSUES.md, and this checkpoint.
- Checks: 45 tests passed on the project Python and isolated CPython 3.11 and 3.14 editable installs; Ruff check/format, mypy, compileall, `uv build`, an isolated CPython 3.11 wheel import, and `git diff --check` passed.
- Failures: GitHub MCP loading was unavailable, so live issues are read and updated through the authenticated GitHub CLI; no implementation blocker remains.
- Evidence: a credential-free scripted provider exercises evaluate plus all five convenience operations without an agent definition; direct decisions retain evidence and model provenance; subject changes alter fingerprints; zero candidates avoid provider dispatch; singleton and duplicate-label selection retain exact identity; incomplete no-fit retains expansion need; filter outcomes preserve every item; exact Unicode extraction is deterministic; two concurrent requests racing for one attempt admit exactly one; ledger measurements keep observed, estimated, reserved, released and unknown usage distinct.
- Remaining gates: direct decisions are locally verified only; live provider compatibility, post-run diagnostics, the agent scheduler, consequential effects, publication, deployment, and licensing remain assigned or unauthorized as documented.
- Next action: commit JF-06, post evidence, close #7, update tracker #1, then implement JF-07 sanitized events, result inspection, and actionable diagnostics.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
