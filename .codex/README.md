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
- Completed: slices A through C repair validation, snapshots, capability boundaries, completion freshness, and final mutation revalidation; slice D records local unknown-write evidence when reconciliation is cancelled and handles trusted no-effect receipts explicitly.
- Checks: cancellation regressions pass with and without a durable store, no-effect and mismatched receipt cases pass, and 26 policy, runtime, and composition tests pass with Ruff and mypy.
- Failures: all eleven supplied synthetic audit probes reproduced against `d3743ed`; the execution probe now shows zero stale effects, stale completion unresolved, cancellation retaining one local unknown reference, and reconciled no-effect ending failed rather than unknown.
- Remaining: planner fixed arguments, deadlines, identities, StepValue clarification, synchronized documentation, and the full verification matrix.
- External gates: no live provider, real external effect, paid compute, publication, deployment, push, PR, or GitHub issue mutation is authorized by the audit task.
- Next action: commit slice D, then repair planner fixed-argument validation, callback deadlines, and effective run identities in one planner-focused slice.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
