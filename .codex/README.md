# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: complete JF-10 semantic acceptance, exact-action authorization, reconciliation, and checks T24 through T30 and T48, then continue with the next unblocked issue.
- State: branch `codex/jev-frame-implementation`; JF-01 through JF-09 are closed, and JF-10 has a fully verified offline implementation awaiting commit and issue update.
- Decisions: Python 3.11 or newer, local import `jev_frame`, `typesafe-sdk==0.7.0`, direct `pydantic>=2.12,<3`, and the public names and finite type subset in README `Frozen initial contract`.
- Changed files: `src/jev_frame/policy.py`, guarded paths in `src/jev_frame/runtime.py`, mutation metadata in `src/jev_frame/definitions.py`, write admission in `src/jev_frame/limits.py`, public exports in `src/jev_frame/__init__.py`, `tests/test_policy.py`, README.md, IMPLEMENTATION_PLAN.md, ISSUES.md, and this checkpoint.
- Checks: 70 tests passed on the project Python and isolated CPython 3.11 and 3.14 editable installs; the public example, Ruff check/format, mypy over 22 source files, compileall, `uv build`, an isolated CPython 3.11 wheel import, and `git diff --check` passed.
- Failures: GitHub MCP loading was unavailable, so live issues are read and updated through the authenticated GitHub CLI; no implementation blocker remains.
- Evidence: a 0.999 judgment cannot bypass rejected policy or denied/revoked authority; stale source revalidation blocks dispatch; lost and malformed replies reconcile one fake effect without retry; inconclusive reconciliation and post-dispatch cancellation preserve outcome-unknown; checkpoint errors and missing durable intent fail before effect; checkpoint records bind the exact action digest.
- Remaining gates: the JF-10 commit is pending; all effect tests are synthetic, and live provider compatibility, real application authorization, publication, deployment and licensing remain unauthorized.
- Next action: inspect and commit JF-10, post evidence, close #11, update tracker #1, then select the next issue from live prerequisites.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
