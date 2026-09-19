# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: complete JF-13 optional Pydantic AI integration and checks T45 through T48 and T52 through T55, then continue with the next live unblocked issue.
- State: branch `codex/jev-frame-implementation`; JF-01 through JF-12 are closed, and JF-13 is implemented and verified locally pending commit and issue update.
- Decisions: pin `pydantic-ai-slim[typesafe]==2.46.0`, keep host state in `RunContext.deps`, preserve full decisions in `ToolReturn.metadata`, place required checks inside a `ToolOutput` function, and reuse native `TypeSafeModel` only with explicit semantic and usage coverage.
- Changed files: `pyproject.toml`, `uv.lock`, `src/jev_frame/integrations/pydantic_ai.py`, `tests/test_pydantic_ai_integration.py`, `examples/pydantic_ai_decision.py`, README.md, IMPLEMENTATION_PLAN.md, ISSUES.md, and this checkpoint.
- Checks: seven focused adapter and native conformance tests and the public example pass; all 87 tests pass with all extras on isolated CPython 3.11 and 3.14; core-only imports, Ruff, mypy, compileall, build, wheel metadata and wheel import checks pass.
- Failures: the scripted SDK double initially lacked two current optional request keywords, and native direct-output responses did not carry a real request count; the double now matches the public call and usage remains partial rather than inferred complete.
- Evidence: advisory Noul and Score tools retain complete canonical artifacts, optional routing skips Jev, forged scope and provider failures remain typed, cancellation reaches the provider, guarded output functions recheck changed drafts and reject failures, native Noul remains unrounded, native Score keeps its fractional metadata, and fallback usage remains unknown.
- Remaining gates: no live TypeSafe or fallback model, application authorization, business mutation, publication, deployment or licensing was exercised or authorized.
- Next action: inspect the staged diff, commit JF-13, update and close #14 and tracker #1, then select the next live unblocked issue.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
