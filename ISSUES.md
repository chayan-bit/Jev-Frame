# Jev-Frame implementation issue roadmap

Status: implementation authorized on branch `codex/jev-frame-implementation`.
JF-01 freezes the contracts, JF-02 supplies typed foundations, JF-03 supplies shared state, JF-04 supplies compilation, JF-05 supplies the SDK adapter, JF-06 supplies direct decisions and shared admission, JF-07 supplies sanitized events and inspection, JF-08 supplies reusable packages, JF-09 supplies the shared read-only runtime, JF-10 supplies guarded synthetic write execution, JF-11 supplies bounded investigation and typed clarification, JF-12 supplies the optional LangChain and LangGraph adapter, JF-13 supplies the optional Pydantic AI adapter with tested native TypeSafe reuse boundaries, JF-14 supplies explicit host-tool import and bounded scoped discovery, JF-15 supplies typed specialist composition under shared run-tree limits, and JF-16 supplies bounded objective-driven planning and propose-select recipes.
Use Sol at high reasoning effort explicitly when implementing an assigned issue.
Local implementation is now requested under the repository and issue boundaries below.

Roadmap tracker: [#1](https://github.com/chayan-bit/Jev-Frame/issues/1).
Product scope is defined in [README.md](README.md), behavioral contracts in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), and operating constraints in [AGENTS.md](AGENTS.md).
This document maps the same scope to independently reviewable work; it does not add a competing architecture.
Public API names and dependency versions are frozen by [JF-01 / #2](https://github.com/chayan-bit/Jev-Frame/issues/2) and summarized in README `Frozen initial contract`.

## How to execute an issue

1. Read the current source documents, the issue, its prerequisites, and relevant worktree changes.
2. Verify that prerequisite contracts and checks are actually available; a closed issue without the required behavior is not sufficient evidence.
3. Implement only the named responsibility using the existing shared helpers and runtime.
4. Add the smallest checks that fail on the listed behavioral errors, using synthetic data and offline provider/tool doubles by default.
5. Update implementation claims and the compact checkpoint with exact changed files, commands, observed results, failures, evidence, and next action.
6. Report remaining live-provider or application gates separately from completed local work.

Numbering is a stable work identifier, not a requirement to implement every issue in numeric order.
All dependency edges below point to earlier identifiers, so the graph is acyclic.
The ten accepted feature additions F01–F10 are initial-delivery scope rather than optional future ideas.

## Scoped work and acceptance ownership

Each linked issue contains its outcome, ownership, ordered approach, acceptance checklist, exclusions and implementation rules.
The tracker is coordination only and does not duplicate an implementation task.

| Work item | Scope | Prerequisites | Plan acceptance checks |
|---|---|---|---|
| [JF-01 / #2](https://github.com/chayan-bit/Jev-Frame/issues/2) | Freeze public contracts and verify provider/framework compatibility | None | A–L / F01–F10 contract coverage |
| [JF-02 / #3](https://github.com/chayan-bit/Jev-Frame/issues/3) | Implement package foundations, typed definitions and explicit argument bindings | [JF-01 / #2](https://github.com/chayan-bit/Jev-Frame/issues/2) | T01, T02 |
| [JF-03 / #4](https://github.com/chayan-bit/Jev-Frame/issues/4) | Implement evidence provenance, candidate snapshots and selective invalidation | [JF-02 / #3](https://github.com/chayan-bit/Jev-Frame/issues/3) | T03, T04, T05, T06, T07, T08, T09 |
| [JF-04 / #5](https://github.com/chayan-bit/Jev-Frame/issues/5) | Implement the pure decision compiler and offline preview | [JF-03 / #4](https://github.com/chayan-bit/Jev-Frame/issues/4) | T10, T11, T12, T13, T58 |
| [JF-05 / #6](https://github.com/chayan-bit/Jev-Frame/issues/6) | Implement the official TypeSafe SDK adapter and strict response validation | [JF-04 / #5](https://github.com/chayan-bit/Jev-Frame/issues/5) | T14, T15, T16, T17 |
| [JF-06 / #7](https://github.com/chayan-bit/Jev-Frame/issues/7) | Implement standalone decision operations and shared admission accounting | [JF-05 / #6](https://github.com/chayan-bit/Jev-Frame/issues/6) | T17, T21, T44, T56 |
| [JF-07 / #8](https://github.com/chayan-bit/Jev-Frame/issues/8) | Implement sanitized events, result inspection and actionable diagnostics | [JF-06 / #7](https://github.com/chayan-bit/Jev-Frame/issues/7) | T39, T58 |
| [JF-08 / #9](https://github.com/chayan-bit/Jev-Frame/issues/9) | Implement reusable decision packages and a generic evidence package | [JF-07 / #8](https://github.com/chayan-bit/Jev-Frame/issues/8) | T57 |
| [JF-09 / #10](https://github.com/chayan-bit/Jev-Frame/issues/10) | Implement the shared read-only agent scheduler and completion flow | [JF-07 / #8](https://github.com/chayan-bit/Jev-Frame/issues/8) | T18, T19, T20, T21, T22, T23 |
| [JF-10 / #11](https://github.com/chayan-bit/Jev-Frame/issues/11) | Implement acceptance policies, exact-action authorization and write reconciliation | [JF-09 / #10](https://github.com/chayan-bit/Jev-Frame/issues/10) | T24, T25, T26, T27, T28, T29, T30, T48 |
| [JF-11 / #12](https://github.com/chayan-bit/Jev-Frame/issues/12) | Implement bounded investigation, retrieval expansion and typed clarification | [JF-09 / #10](https://github.com/chayan-bit/Jev-Frame/issues/10) | T04, T31, T32, T64 |
| [JF-12 / #13](https://github.com/chayan-bit/Jev-Frame/issues/13) | Add the optional LangChain and LangGraph integration | [JF-10 / #11](https://github.com/chayan-bit/Jev-Frame/issues/11) | T45, T46, T47, T48, T52, T54, T55 |
| [JF-13 / #14](https://github.com/chayan-bit/Jev-Frame/issues/14) | Add the optional Pydantic AI integration and verify native Jev reuse | [JF-10 / #11](https://github.com/chayan-bit/Jev-Frame/issues/11) | T45, T46, T47, T48, T52, T53, T54, T55 |
| [JF-14 / #15](https://github.com/chayan-bit/Jev-Frame/issues/15) | Implement existing-tool import and bounded scoped capability discovery | [JF-08 / #9](https://github.com/chayan-bit/Jev-Frame/issues/9), [JF-12 / #13](https://github.com/chayan-bit/Jev-Frame/issues/13), [JF-13 / #14](https://github.com/chayan-bit/Jev-Frame/issues/14) | T61 |
| [JF-15 / #16](https://github.com/chayan-bit/Jev-Frame/issues/16) | Implement typed agent composition and shared run-tree limits | [JF-10 / #11](https://github.com/chayan-bit/Jev-Frame/issues/11) | T33, T34, T35, T36, T37 |
| [JF-16 / #17](https://github.com/chayan-bit/Jev-Frame/issues/17) | Implement objective-driven hybrid planning and propose-select recipes | [JF-11 / #12](https://github.com/chayan-bit/Jev-Frame/issues/12), [JF-14 / #15](https://github.com/chayan-bit/Jev-Frame/issues/15), [JF-15 / #16](https://github.com/chayan-bit/Jev-Frame/issues/16) | T38, T49, T50, T51, T52, T53, T62 |
| [JF-17 / #18](https://github.com/chayan-bit/Jev-Frame/issues/18) | Implement bounded artifact generation, verification and revision | [JF-16 / #17](https://github.com/chayan-bit/Jev-Frame/issues/17) | T65 |
| [JF-18 / #19](https://github.com/chayan-bit/Jev-Frame/issues/19) | Implement a reusable evidence workflow for large document collections | [JF-08 / #9](https://github.com/chayan-bit/Jev-Frame/issues/9), [JF-11 / #12](https://github.com/chayan-bit/Jev-Frame/issues/12) | T63 |
| [JF-19 / #20](https://github.com/chayan-bit/Jev-Frame/issues/20) | Implement opt-in sanitized run capture and offline regression replay | [JF-09 / #10](https://github.com/chayan-bit/Jev-Frame/issues/10) | T59 |
| [JF-20 / #21](https://github.com/chayan-bit/Jev-Frame/issues/21) | Implement offline evaluations, leakage checks and integration comparisons | [JF-12 / #13](https://github.com/chayan-bit/Jev-Frame/issues/13), [JF-13 / #14](https://github.com/chayan-bit/Jev-Frame/issues/14), [JF-15 / #16](https://github.com/chayan-bit/Jev-Frame/issues/16), [JF-16 / #17](https://github.com/chayan-bit/Jev-Frame/issues/17), [JF-17 / #18](https://github.com/chayan-bit/Jev-Frame/issues/18), [JF-18 / #19](https://github.com/chayan-bit/Jev-Frame/issues/19), [JF-19 / #20](https://github.com/chayan-bit/Jev-Frame/issues/20) | T40, T41, T42, T53 |
| [JF-21 / #22](https://github.com/chayan-bit/Jev-Frame/issues/22) | Implement policy calibration and side-effect-free shadow comparisons | [JF-20 / #21](https://github.com/chayan-bit/Jev-Frame/issues/21) | T60 |
| [JF-22 / #23](https://github.com/chayan-bit/Jev-Frame/issues/23) | Verify clean installations, full scenario coverage and documented delivery gates | [JF-01 / #2](https://github.com/chayan-bit/Jev-Frame/issues/2), [JF-02 / #3](https://github.com/chayan-bit/Jev-Frame/issues/3), [JF-03 / #4](https://github.com/chayan-bit/Jev-Frame/issues/4), [JF-04 / #5](https://github.com/chayan-bit/Jev-Frame/issues/5), [JF-05 / #6](https://github.com/chayan-bit/Jev-Frame/issues/6), [JF-06 / #7](https://github.com/chayan-bit/Jev-Frame/issues/7), [JF-07 / #8](https://github.com/chayan-bit/Jev-Frame/issues/8), [JF-08 / #9](https://github.com/chayan-bit/Jev-Frame/issues/9), [JF-09 / #10](https://github.com/chayan-bit/Jev-Frame/issues/10), [JF-10 / #11](https://github.com/chayan-bit/Jev-Frame/issues/11), [JF-11 / #12](https://github.com/chayan-bit/Jev-Frame/issues/12), [JF-12 / #13](https://github.com/chayan-bit/Jev-Frame/issues/13), [JF-13 / #14](https://github.com/chayan-bit/Jev-Frame/issues/14), [JF-14 / #15](https://github.com/chayan-bit/Jev-Frame/issues/15), [JF-15 / #16](https://github.com/chayan-bit/Jev-Frame/issues/16), [JF-16 / #17](https://github.com/chayan-bit/Jev-Frame/issues/17), [JF-17 / #18](https://github.com/chayan-bit/Jev-Frame/issues/18), [JF-18 / #19](https://github.com/chayan-bit/Jev-Frame/issues/19), [JF-19 / #20](https://github.com/chayan-bit/Jev-Frame/issues/20), [JF-20 / #21](https://github.com/chayan-bit/Jev-Frame/issues/21), [JF-21 / #22](https://github.com/chayan-bit/Jev-Frame/issues/22) | T43, T55 |

## Feature coverage

| Feature | Accepted addition | Delivery issues | Dedicated checks |
|---|---|---|---|
| F01 | Decision operations | [JF-06 / #7](https://github.com/chayan-bit/Jev-Frame/issues/7) | T56 |
| F02 | Reusable decision packages | [JF-08 / #9](https://github.com/chayan-bit/Jev-Frame/issues/9), [JF-20 / #21](https://github.com/chayan-bit/Jev-Frame/issues/21) | T57 |
| F03 | Preview and debugger | [JF-04 / #5](https://github.com/chayan-bit/Jev-Frame/issues/5), [JF-07 / #8](https://github.com/chayan-bit/Jev-Frame/issues/8) | T58 |
| F04 | Capture and offline replay | [JF-19 / #20](https://github.com/chayan-bit/Jev-Frame/issues/20) | T59 |
| F05 | Calibration and shadow mode | [JF-20 / #21](https://github.com/chayan-bit/Jev-Frame/issues/21), [JF-21 / #22](https://github.com/chayan-bit/Jev-Frame/issues/22) | T60 |
| F06 | Existing tools and scoped discovery | [JF-12 / #13](https://github.com/chayan-bit/Jev-Frame/issues/13), [JF-13 / #14](https://github.com/chayan-bit/Jev-Frame/issues/14), [JF-14 / #15](https://github.com/chayan-bit/Jev-Frame/issues/15) | T61 |
| F07 | LLM propose / validate / Jev select | [JF-16 / #17](https://github.com/chayan-bit/Jev-Frame/issues/17) | T62 |
| F08 | Large document evidence processing | [JF-18 / #19](https://github.com/chayan-bit/Jev-Frame/issues/19) | T63 |
| F09 | Useful investigation and clarification | [JF-11 / #12](https://github.com/chayan-bit/Jev-Frame/issues/12) | T31, T32, T64 |
| F10 | Generate / verify / revise | [JF-17 / #18](https://github.com/chayan-bit/Jev-Frame/issues/18) | T65 |

## Practical delivery order

- Foundation: JF-01 through JF-07 produce the contracts, typed boundaries, evidence, compiler, provider adapter, direct operations, shared accounting, and inspection.
- Reuse and runtime: JF-08 and JF-09 add packages and the read-only agent scheduler.
- Independent next work after JF-09: JF-10 adds guarded execution, JF-11 adds read-only investigation, and JF-19 adds capture/replay.
- Reference integrations: JF-12 and JF-13 consume JF-10's neutral gate contract and existing decision APIs.
- Extended capabilities: JF-14 imports host tools, JF-15 composes specialists, JF-16 integrates planning, JF-17 verifies generated artifacts, and JF-18 handles document collections through injected retrieval.
- Evaluation and delivery: JF-20 compares complete scenarios, JF-21 calibrates policies and shadows observations, and JF-22 verifies clean installations and delivery evidence.

Parallel implementation is possible only when dependencies and file ownership permit it; these issues do not authorize a worker hierarchy.
Core guarded execution does not depend on optional host frameworks.
Read-only investigation does not depend on write execution, while any effectful investigation still requires the guarded path.
Move JF-19 earlier after its prerequisites when replay fixtures help later work.

## Shared boundaries

Use the official TypeSafe SDK where suitable and reuse native framework support after testing primitive semantics and metadata preservation.
One owner controls each loop, retry policy, and actual tool dispatch.
All Jev-Frame definitions share a runtime; existing host frameworks may keep their own outer loop.
Confidence, evidence acceptance, and permission remain separate.
Question dependencies require separate evaluation boundaries, candidate IDs bind to exact presented snapshots, and Noul/Score keep their native semantics.

An offline preview performs no calls, fixture replay runs only doubles, and shadow comparisons cannot dispatch business effects.
Live reevaluation is a distinct explicitly selected operation with configured access and budgets.
Tool discovery queries a finite host-supplied catalog; it cannot scan the machine, activate arbitrary capabilities, or open remote sessions automatically.
Generated plans and artifacts remain proposals until their structural and completion checks pass.
No direct decision call or recorded approval authorizes an unrelated action.

Keep expected answers and evaluator metadata outside runtime inputs, preserve source scope and contradictions, and report unknown cost or coverage explicitly.
No database, broker, model gateway, hosted UI, new agent engine, or public package release is required by this backlog.
No live paid calls, consequential real writes, publication, visibility changes, or licensing selection are authorized by issue creation.
There is no guarantee that detailed issues eliminate implementation errors; their explicit contracts and regression checks make errors detectable and reviewable.

## Delivery gates

| Level | Required evidence |
|---|---|
| A | Contracts express Scenarios A–L and define failure behavior. |
| B | Read-only Scenario A completes through the public runtime with deterministic providers. |
| C | All F01–F10 features, T01–T65 checks, and reference integration scenarios pass offline. |
| D | Each claimed provider/framework/model combination has separately authorized recorded live evidence, or is explicitly pending. |
| E | A host application's owner accepts its frozen held-out policy and operational controls. |

Local installation and offline fixtures cannot establish Level D or E.
Each issue is complete only when its stated local acceptance evidence is available; JF-22 may complete local delivery with a clearly pending live gate.
JF-22 local delivery evidence, including exact Scenario A-L and T01-T65 mappings and the narrowly scoped live smoke boundary, is recorded in [DELIVERY_EVIDENCE.md](DELIVERY_EVIDENCE.md).
