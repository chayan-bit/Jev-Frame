# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: complete JF-12 optional LangChain and LangGraph integration and checks T45 through T48, T52, T54 and T55, then continue with the next live unblocked issue.
- State: branch `codex/jev-frame-implementation`; JF-01 through JF-11 are closed, and JF-12 is fully verified locally pending commit and issue update.
- Decisions: pin the optional `langchain` extra to LangChain 1.4.2 and LangGraph 1.2.11, keep the core import independent, inject host-only state through `ToolRuntime`, leave dispatch with `ToolNode`, and bind required checkpoint output to a freshly reconstructed action digest.
- Changed files: `pyproject.toml`, `uv.lock`, `src/jev_frame/integrations/`, `tests/test_langchain_integration.py`, `examples/langchain_decision.py`, README.md, IMPLEMENTATION_PLAN.md, ISSUES.md, and this checkpoint.
- Checks: 80 tests pass with the optional adapter on isolated CPython 3.11 and 3.14; core-only imports without LangChain pass on both versions; the public example, Ruff format and checks, mypy over source and adapter surfaces, compileall, build, wheel metadata and isolated wheel import pass.
- Failures: a locally imported `ToolRuntime` annotation was initially invisible to `ToolNode.get_type_hints`; binding the concrete optional injection marker on the wrapper fixed the public-interface test.
- Evidence: one tool call produces one provider attempt and a full `DecisionResult` artifact; optional routing performs no Jev call; forged scope and provider failures stay typed; cancellation reaches the provider; changed arguments replace an older checkpoint; checkpoint rejection raises before a following action node.
- Remaining gates: no live model, hosted LangGraph service, application authorization, business mutation, publication, deployment or licensing was exercised or authorized.
- Next action: inspect the staged diff; commit JF-12; update and close #13 and tracker #1; then select the next live unblocked issue.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
