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
- Completed: slices A through D repair the validation, scope, evidence, execution, and reconciliation boundaries; slice E rejects planner overrides before dispatch, bounds asynchronous planner and validator callbacks, and propagates one effective root identity through step and evidence namespaces.
- Checks: planner regressions cover all accepted argument variants, valid fixed arguments, late and stalled callbacks, expired step dispatch, external cancellation, sequential implicit and explicit identities, shared evidence, and cross-turn `EvidenceValue`; all 11 planning and optional-framework tests pass with Ruff and mypy.
- Failures: all eleven supplied synthetic audit probes reproduced against `d3743ed`; planner probes now show bounded late results and two implicit runs dispatching independently, while the old cross-turn `StepValue` probe remains unresolved because that reference is intentionally revision-local.
- Remaining: synchronize the README and implementation plan, run the complete audit probes and verification matrix, inspect all diffs, and report any uncovered regression.
- External gates: no live provider, real external effect, paid compute, publication, deployment, push, PR, or GitHub issue mutation is authorized by the audit task.
- Next action: commit slice E, document the corrected contracts and revision-local `StepValue` rule, then run full source, examples, build, wheel, and supported-Python verification.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
