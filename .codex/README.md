# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: implement the eleven authorized audit correctness fixes before resuming JF-17.
- State: branch `codex/jev-frame-implementation` at audited baseline `d3743ed`; JF-01 through JF-16 are committed and GitHub #17 is closed.
- Completed: strict exact-type `Literal` validation now covers nested supported values, and candidate snapshots detach and freeze their candidate collection, nested values, and retrieval metadata.
- Checks: the two new slice-A regressions fail on the audited baseline and pass after the shared fixes; 51 affected definition, state, compiler, decision, capability, and planning tests pass; Ruff and focused mypy pass.
- Failures: all eleven supplied synthetic audit probes reproduced against `d3743ed`; the original evidence probe now stops at the expected `InputValidationError` for `Literal[1, 2]` with `True`.
- Remaining: imported scope, MCP error status, completion and mutation freshness, reconciliation outcomes and cancellation, planner fixed arguments, deadlines, identities, StepValue clarification, synchronized documentation, and the full verification matrix.
- External gates: no live provider, real external effect, paid compute, publication, deployment, push, PR, or GitHub issue mutation is authorized by the audit task.
- Next action: commit slice A, then reproduce and fix imported capability scope and explicit MCP failures at their shared adapter and dispatch boundaries.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
