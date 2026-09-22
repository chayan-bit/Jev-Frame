# Jev-Frame project instructions

## Project state

Read `README.md` before work.
This repository is being implemented through the accepted GitHub backlog on `codex/jev-frame-implementation`.
Create implementation code, examples, dependencies, tests, CI, or packages only within the current authorized issue scope.

## Project boundary

Build a general developer-facing framework for Jev agents.
Keep application-specific integrations, business policies, customer data, private evaluation history, and credentials outside the core repository.
Use generic examples and public primary sources.

## Architecture

Keep the public programming API separate from the shared runtime within one framework.
Specialized agents should be definitions and capability packages, not copied event loops.
Reuse the official TypeSafe SDK where suitable.
Before future implementation, read current TypeSafe documentation and survey existing maintained solutions.
Keep proposed interfaces clearly distinguished from implemented behavior.

Jev questions in one request are independent.
Make subjects and candidate bindings explicit, preserve evidence provenance, and distinguish uncertainty from execution authority.
Never claim that typed output or model confidence guarantees correctness.

## Work style

Preserve unrelated changes and keep scope narrow.
For implementation when authorized, use Sol at high reasoning effort as requested by the project owner.
Do not create worker hierarchies or repeated review loops without an explicit request.
Use one complete sentence per line in prose-heavy Markdown.
Keep design decisions and known limitations in the README until additional documents are needed.

## Security and publication

Never commit secrets, local environments, generated traces, or client data.
Keep credentials in environment variables or a secret manager.
Do not change repository visibility, deploy, release, or publish packages without an explicit request.
Licensing is undecided.
