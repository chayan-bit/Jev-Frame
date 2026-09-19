# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- The objective was to implement and verify the eleven authorized audit correctness fixes before resuming JF-17.
- The branch is `codex/jev-frame-implementation`, the audited baseline is `d3743ed`, JF-01 through JF-16 are committed, and GitHub #17 is closed.
- Commits `755454f`, `5005ab8`, `f37a95d`, `10cd337`, and `9fc7d1c` repair strict values, immutable snapshots, imported scope, MCP errors, completion and mutation freshness, reconciliation evidence, planner arguments, deadlines, and run identities.
- The changed implementation and regression files are `src/jev_frame/definitions.py`, `src/jev_frame/state.py`, `src/jev_frame/capabilities.py`, `src/jev_frame/runtime.py`, `src/jev_frame/planning.py`, and their focused existing test modules.
- The command `uv run --frozen --all-extras python -m unittest discover -s tests -v` passes all 119 tests.
- The commands `uv run --frozen --all-extras --with ruff ruff check src tests examples` and `uv run --frozen --all-extras --with mypy mypy src/jev_frame --ignore-missing-imports` pass with no findings.
- The full 119-test suite passes in isolated CPython 3.11 and 3.14 environments, and both versions compile `src` and `examples` successfully.
- All three offline examples pass, `uv build` produces the wheel and source distribution, and a Python 3.11 environment outside the checkout imports the installed wheel without LangChain or Pydantic AI installed.
- The supplied execution and MCP probes now fail closed, the planner probe has unique implicit identities and bounded late work, and the evidence probe stops at the expected strict-Literal rejection before reaching its old mutable-snapshot check.
- The regression suite separately proves immutable detached snapshots and documents that `StepValue` is revision-local while cross-turn reuse uses `StepOutcome.evidence_ref` through `EvidenceValue`.
- The remaining gates are live-provider compatibility, application acceptance calibration, consequential real effects, publication, deployment, push, PR creation, and GitHub issue mutation, none of which was authorized by the audit task.
- The next action is to inspect and commit the synchronized documentation, then resume JF-17 only under the original backlog authorization.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
