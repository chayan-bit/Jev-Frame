# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: complete JF-14 existing-tool import, bounded scoped discovery, and T61, then continue with the next live unblocked issue.
- State: branch `codex/jev-frame-implementation`; JF-01 through JF-13 are closed, and JF-14 is implemented and verified locally pending commit and issue update.
- Decisions: accept only explicit finite descriptors, filter scope before lookup, bind opaque candidate keys to descriptor schema digests, require all missing semantics at activation, reuse the ordinary `Tool` and runtime, and reject foreign mutation import unless the application authors the full Jev receipt contract.
- Changed files: `src/jev_frame/capabilities.py`, `src/jev_frame/__init__.py`, `src/jev_frame/integrations/langchain.py`, `tests/test_capabilities.py`, `tests/test_langchain_integration.py`, README.md, IMPLEMENTATION_PLAN.md, ISSUES.md, and this checkpoint.
- Checks: five core capability tests and seven LangChain integration tests pass; all 93 tests pass with all extras on isolated CPython 3.11 and 3.14; 81 core tests pass with two optional modules skipped on each version; Ruff, mypy, compileall, build, wheel metadata and isolated wheel import checks pass.
- Failures: an empty query initially violated the existing `CandidateSet` non-empty query invariant; it is now recorded as an absent query while expansion retains the deterministic empty query.
- Evidence: missing semantics and mutations fail before calls, unauthorized scopes never enter candidate totals, truncation and complete no-fit differ, expansion is bounded, changed schemas invalidate selections, malformed schemas fail, cancellation and errors propagate, fake MCP dispatch enters the runtime once, and a real LangChain tool uses `ainvoke` once.
- Remaining gates: no real MCP server, remote framework service, credentials, business mutation, model-based catalog selection, publication, deployment or licensing was exercised or authorized.
- Next action: inspect the staged diff, commit JF-14, update and close #15 and tracker #1, then select the next live unblocked issue.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
