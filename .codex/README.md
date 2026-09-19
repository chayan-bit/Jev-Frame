# Codex workspace

Open this repository as a local Codex project.
Read the root `README.md` and `AGENTS.md` for project intent and work constraints.
The root `AGENTS.md` is the project instruction entry point; this file is continuation context.

Use Sol with high reasoning effort explicitly when implementing an assigned issue.
The project-local configuration currently contains only a comment and does not enforce model selection.
It contains no credentials, sandbox overrides, approval overrides, or startup commands.
Project-local configuration may require the normal Codex project trust step before it is applied.

## Issue-planning checkpoint

- Objective: prepare a consistent, dependency-ordered GitHub backlog for the framework, LLM integrations, and ten accepted developer/capability features.
- State: documentation and repository initialization only; no framework implementation or executable examples.
- Design: standalone decision API plus optional shared runtime; external frameworks can own the loop, and configured LLMs can plan within Jev-Frame.
- Scope: reusable framework machinery; application-specific capabilities remain separate.
- Decisions: use `README.md` for product scope, `IMPLEMENTATION_PLAN.md` for behavioral contracts, and `ISSUES.md` for the GitHub work breakdown and dependencies.
- Changed files: README, implementation plan, issue roadmap, and this continuation document; no implementation files.
- Evidence: GitHub tracker #1 links 22 implementation issues (#2–#23), with Scenarios A–L, all F01–F10 features and T01–T65 checks mapped in ISSUES.md.
- Checks: all 23 live issue bodies match their prepared content; prerequisite ordering is acyclic and every acceptance check has an owner.
- Authorization: commit and push the four reconciled documentation files directly to main, without opening a pull request.
- Remaining gates: implementation is not started by issue creation; paid calls, consequential real effects, licensing, and release still require their respective authorization.
- Next work: when asked to implement an issue, first verify its prerequisites and follow its acceptance criteria using Sol high.

Use current official TypeSafe documentation when work resumes.
Do not copy private project history or local credentials into this repository.
