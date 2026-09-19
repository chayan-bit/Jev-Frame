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
- Completed: slices A and B repair strict values, snapshots, imported scope, and MCP failures; slice C requires current completion evidence before and after host checks and performs the final exact mutation revalidation after awaited persistence and authorization gates.
- Checks: new deterministic regressions cover invalidation during a read, an awaited completion check, second authorization, in-flight persistence, and authorization expiry; 24 runtime, policy, and composition tests pass; Ruff and mypy pass.
- Failures: all eleven supplied synthetic audit probes reproduced against `d3743ed`; rerun probes now show zero cross-scope calls, failed explicit MCP responses, zero stale mutation effects, and stale read completion ending unresolved.
- Remaining: reconciliation outcomes and cancellation, planner fixed arguments, deadlines, identities, StepValue clarification, synchronized documentation, and the full verification matrix.
- External gates: no live provider, real external effect, paid compute, publication, deployment, push, PR, or GitHub issue mutation is authorized by the audit task.
- Next action: commit slice C, then preserve local unknown-write evidence across reconciliation cancellation and classify trusted no-effect reconciliation receipts.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
