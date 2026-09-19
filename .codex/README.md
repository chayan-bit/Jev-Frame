# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: complete JF-15 typed agent composition and T33 through T37, then continue with the next live unblocked issue.
- State: branch `codex/jev-frame-implementation`; JF-01 through JF-14 are closed, and JF-15 is implemented and verified locally pending commit and issue update.
- Decisions: reuse `Runtime.run` through `Runtime.agent_as_tool`, require exact parent scope and authority, project only explicitly permitted evidence and host dependencies, namespace imported evidence, share one ledger and deadline, and avoid reserving a parent operation slot around a child run.
- Changed files: `src/jev_frame/definitions.py`, `src/jev_frame/limits.py`, `src/jev_frame/runtime.py`, `src/jev_frame/__init__.py`, `tests/test_composition.py`, README.md, IMPLEMENTATION_PLAN.md, ISSUES.md, and this checkpoint.
- Checks: seven focused composition tests pass; all 100 tests pass with all extras on isolated CPython 3.11 and 3.14; 88 core tests pass with two optional modules skipped on each version; Ruff, mypy, compileall, build, wheel metadata and isolated wheel import checks pass.
- Failures: the cancellation-effect fixture initially allowed zero writes and then used an invalid scalar dataclass completion binding; the fixture now admits exactly one synthetic write and declares the typed result bindings correctly.
- Evidence: scope and evidence widening fail before child access, cycles and depth/count overflow remain typed, one-slot parent/child work completes, opposing findings and unresolved provenance remain separate, underlying attempts count once, parent policy stays authoritative, cancellation reaches child work, and an admitted cancelled child mutation imports an unknown execution outcome.
- Remaining gates: no live provider, consequential real effect, distributed worker, durable cross-run resume, publication, deployment or licensing was exercised or authorized.
- Next action: review the staged diff, commit JF-15, update and close #16 and tracker #1, then select the next live unblocked issue.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
