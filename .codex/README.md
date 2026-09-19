# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Implementation checkpoint

- Objective: complete JF-01 contract freeze, then implement JF-02 package foundations and checks T01-T02.
- State: branch `codex/jev-frame-implementation`; JF-01 is documentation-only and runtime implementation has not started.
- Decisions: Python 3.11 or newer, local import `jev_frame`, `typesafe-sdk==0.7.0`, direct `pydantic>=2.12,<3`, and the public names and finite type subset in README `Frozen initial contract`.
- Changed files: README.md, IMPLEMENTATION_PLAN.md, ISSUES.md, and this continuation document for JF-01.
- Checks: `uv run --isolated --python 3.11|3.14 --with 'typesafe-sdk==0.7.0' python -c '<import and primitive construction>'` passed on CPython 3.11.15 and 3.14.6 with Pydantic 2.13.5; `git diff --check` passed; documentation/source metadata was refreshed without a provider call.
- Failures: GitHub MCP loading was unavailable, so live issues are read and updated through the authenticated GitHub CLI; no implementation blocker remains.
- Evidence: live #1 and #2 bodies were read; TypeSafe SDK 0.7.0, Pydantic AI 2.46.0, LangChain 1.4.2, and LangGraph 1.2.11 metadata and current official docs were inspected.
- Remaining gates: named adapter conformance belongs to JF-12/JF-13; live provider calls, consequential effects, publication, deployment, and licensing remain unauthorized.
- Next action: validate and commit JF-01, post issue evidence, close #2, update tracker #1, then start JF-02.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
