# Jev-Frame implementation plan for Sol

Prepared on 2026-09-17 against repository revision `5e99044` and the current [README](README.md).
Extended on 2026-09-19 to make existing LLM frameworks, direct decision calls, and objective-driven hybrid planning part of the proposed scope.
The 2026-09-19 issue-planning revision also accepts the ten developer-experience and capability additions described in Section 5.9.
JF-01 refreshed provider and framework compatibility on 2026-09-19 and froze the initial contract documented in the README and Section 4.
This remains an implementation handoff, not a claim that the frozen API imports exist.
Use Sol with high reasoning effort when implementation is separately authorized.
The 2026-09-19 implementation request authorizes local implementation, tests, local builds, regular commits, and issue updates on branch `codex/jev-frame-implementation`.
It does not authorize pushing, pull requests, publication, deployment, licensing, paid provider calls, or consequential real effects.

## 1. Outcome and scope

Build one embeddable Python framework in which developers define specialized agents through typed tools, semantic judgments, candidate providers, completion contracts, and operating policies.
All definitions run through the same compiler, evidence store, scheduler, provider adapter, and execution controls.
Expose the decision path independently so another framework can call Jev without adopting the scheduler or defining a complete agent.
An agent author must not need to assemble TypeSafe requests or copy an event loop for each application.
A run must return a supported typed result or an explicit incomplete outcome with its evidence, unresolved items, trace, and usage.

Implement the README in successive usable slices rather than treating the first read-only example as the completed framework.
The complete initial target includes adaptive investigation, selective recomputation, guarded writes, typed composition, direct decision calls, optional framework adapters, hybrid LLM planning, and evaluation support.
Integrate host-supplied LLM agents through maintained framework interfaces and test doubles; the core does not build another model transport or silently choose a provider.
A durable database, distributed scheduler, hosted service, visual builder, and published package are outside this target.
The ten additions in Section 5.9 are included in the initial target and tracked through `ISSUES.md`.

### 1.1 Current baseline

- JF-02 adds the local `jev_frame` package manifest, strict public definitions, explicit bindings, contexts, usage and result variants, a lockfile, and focused offline checks.
- JF-03 adds immutable candidate snapshots, run-local provenance records, scoped evidence views, canonical fingerprints, and selective transitive invalidation.
- JF-04 adds pure backward compilation, explicit judgment stages, bounded question construction, registered capability-revision validation, and serializable offline preview.
- JF-05 adds the official asynchronous SDK adapter, framework-owned bounded retries, strict primitive response validation, request and attempt metadata, and explicit unknown usage.
- JF-06 adds standalone decision operations, injected evidence sessions, exact source extraction, portable callables, and the shared atomic admission and usage ledger.
- JF-07 adds schema-versioned sanitized events, allowlisted result serialization, permitted exact inspection, omitted-field manifests, and actionable public diagnostics.
- JF-08 adds typed candidate-provider bindings, package configuration identity, a generic document-evidence package, public synthetic authoring examples, and evaluator-separated regression descriptors.
- JF-09 adds the shared read-only scheduler, exact-source completion, isolated run state, shared admission, stale-input rejection, and explicit terminal outcomes.
- JF-10 adds versioned semantic acceptance, exact-action checkpoints and authorization, durable host intent, guarded synthetic mutations, explicit receipts, and reconciliation without blind retry.
- JF-11 adds bounded unresolved-reason actions, candidate expansion, progress fingerprints, selective judgment reevaluation, conflict-preserving evidence, and typed clarification for fresh linked runs.
- There is no framework adapter, CI configuration, or selected license yet.
- Generated environments and local build artifacts remain ignored.
- JF-01 freezes the initial public names and signatures, the local `jev_frame` import name, run-local persistence, and host-owned acceptance thresholds.
- `.codex/config.toml` currently contains a comment and does not enforce a model selection; the continuation note now reflects this.
- Select Sol high explicitly when starting implementation.

### 1.2 Completion levels

| Level | Required outcome | What may be claimed |
|---|---|---|
| A: contract complete | Public contracts, compiler rules, errors, and representative scenarios are specified and validated offline. | The design is implementable, with remaining uncertainties listed. |
| B: read-only vertical slice | A definition retrieves candidates, evaluates Jev judgments, executes authorized reads, and returns evidence-backed results through the shared runtime. | The read-only runtime works for the tested contracts. |
| C: README feature complete | The runtime, integrations, and all ten Section 5.9 features pass their deterministic acceptance checks. | The initial framework implements the documented capabilities under its stated limitations. |
| D: provider verified | Each claimed Jev or hybrid integration passes a bounded, explicitly authorized live smoke run. | Only the recorded provider/framework/model combinations work for the tested versions and accounts. |
| E: application accepted | A host application's frozen policy passes its held-out evaluation and operational controls. | That application may enable only the actions its owner authorizes. |

Do not collapse these levels into a single claim of production readiness.
No level authorizes publication or resolves licensing.

## 2. Verified provider facts and reuse decision

Official documentation and package metadata were refreshed on 2026-09-19.
The documentation must still be checked when the adapter issue is implemented because the SDK is changing quickly.
These facts constrain the adapter; the framework contracts in later sections are proposed project decisions.

| Verified fact | Implementation consequence | Primary source |
|---|---|---|
| The Python package is `typesafe-sdk`, with `AsyncTypeSafeClient` and `TypeSafeClient`. | Reuse official transport, authentication, request handling, and response parsing. | [Python SDK](https://docs.typesafe.ai/sdk/python.md) |
| The documented SDK changelog lists v0.7.0 on 2026-09-18, changes serialization from `msgspec` to Pydantic, and adds `response_model`; v0.6.0 changed Score criteria to an ordered sequence. | Pin and test SDK 0.7.0 instead of copying older response or dictionary-based Score examples. | [SDK changelog](https://docs.typesafe.ai/sdk/python/changelog.md) |
| Every question in a request sees the same state and is evaluated independently. | Batch only compatible ready judgments and split genuine dependencies across calls. | [State](https://docs.typesafe.ai/concepts/state.md) |
| Question IDs are response routing keys and are not inference inputs. | Put subject identity, relevant paths, and full question meaning in instructions. | [Primitives](https://docs.typesafe.ai/primitives.md) |
| Choice returns a label, a distribution, and confidence. | Preserve all three and verify the label against the supplied snapshot. | [Answers](https://docs.typesafe.ai/sdk/python/api/types/responses.md) |
| Noul returns the probability of yes without a separate confidence field. | Keep a distinct answer variant and never fabricate a confidence value. | [Noul](https://docs.typesafe.ai/primitives/noul.md) |
| Score returns an expected value over ordered rubric levels, a distribution, a legend, and confidence. | Preserve fractional values and level order rather than coercing the answer into a category. | [Score](https://docs.typesafe.ai/primitives/score.md) |
| The current Score documentation allows 2–10 levels, and the source-value cookbook documents at most 255 Choice options. | Verify limits against the selected version and count a no-fit option within the Choice limit. | [Score](https://docs.typesafe.ai/primitives/score.md), [Source-value selection](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook.md) |
| Choice and Score confidence describe their distributions. | Do not interpret confidence as authorization or proof of correctness. | [Confidence](https://docs.typesafe.ai/confidence.md) |
| The SDK supports retries and timeouts, while reported token usage can be absent. | Choose one retry owner and represent unknown usage explicitly. | [Retries](https://docs.typesafe.ai/sdk/python/api/retries.md), [Answers](https://docs.typesafe.ai/sdk/python/api/types/responses.md) |
| Jev accepts text and structured text state rather than images, audio, or video. | Require a separately authorized preprocessing capability for nontext input. | [System One](https://docs.typesafe.ai/concepts/system-one.md) |

### 2.1 Maintained alternatives surveyed

The following is a bounded comparison of documented capabilities, not a benchmark or a claim that Jev-Frame is superior.

| Existing option | Reusable capability | Decision for this plan |
|---|---|---|
| Official TypeSafe SDK | Native Jev primitives, provider clients, transport, and response types. | Required integration rather than a replacement HTTP client. |
| Pydantic Graph | Typed asynchronous graphs and state machines independently of Pydantic AI. | Revisit if its graph machinery materially simplifies the required scheduler semantics; do not add it merely to store a small dependency graph. |
| LangGraph | Stateful workflow orchestration, persistence, and human intervention support. | A credible host-level alternative when durable workflows become necessary; do not require its platform or conversational abstractions for the initial library. |
| Python standard library | Async tasks, cancellation, semaphores, dataclasses, signature inspection, hashing, and topological checks. | Default internal implementation tools, with no generic workflow engine of our own. |

The [Pydantic Graph documentation](https://ai.pydantic.dev/graph/) and [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview) support the capability comparison.
Their [Pydantic release history](https://github.com/pydantic/pydantic-ai/releases) and [LangGraph release history](https://github.com/langchain-ai/langgraph/releases) showed current release activity when inspected.
No existing framework was installed or benchmarked during planning.
Sol should confirm maintenance and compatibility during Phase 0, then stop surveying unless a specific requirement remains unmet.

### 2.2 Frozen dependency and packaging baseline

- Require Python 3.11 or newer for standard asynchronous task groups and timeout handling; CPython 3.11.15 and 3.14.6 are the JF-01 compatibility points, not the final delivery matrix.
- Use `jev_frame` as the local import name without claiming ownership of a package registry name.
- Pin the initial official provider dependency to `typesafe-sdk==0.7.0`.
- Declare `pydantic>=2.12,<3` directly and use strict `TypeAdapter` validation at typed application boundaries.
- The isolated JF-01 checks resolved Pydantic 2.13.5 with SDK 0.7.0 on both tested Python versions.
- Prefer frozen dataclasses for internal records and Pydantic only at the supported public boundary.
- Do not implement a new recursive Python type validator, general schema language, or plugin discovery system.
- Use standard-library `unittest`, including asynchronous test support, unless actual test complexity justifies a different runner.
- Create a manifest and build configuration only after implementation authorization, and keep build artifacts local.
- Record the tested SDK version and Python versions without presenting untested version ranges as supported.
- Keep LangChain/LangGraph and Pydantic AI integrations optional, with separate dependency groups and lazy imports when implementation starts.
- Use the host's configured LLM clients and native agent loops rather than introducing another model gateway.

### 2.3 Framework integration sources and reuse update

Official framework documentation and PyPI package metadata were inspected on 2026-09-19 for this extension and JF-01.
[LangChain tools](https://docs.langchain.com/oss/python/langchain/tools) support callable tools and host-injected context.
[LangGraph workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents) provide the outer agent loop and explicit control-flow placement.
[Pydantic AI tools](https://pydantic.dev/docs/ai/tools-toolsets/tools/) offer functions, context injection, and reusable toolsets.
Its [native TypeSafe integration](https://pydantic.dev/docs/ai/models/typesafe/) already exposes Jev decisions and LLM fallback patterns.
That integration's documented fallback can omit an earlier Jev request from final response usage, and function-tool hooks do not cover output functions.
These are specific accounting and interception cases to verify before advertising adapter guarantees.
Use native functionality when it meets the contract; preserve Jev primitive semantics and metadata through the official SDK decision path when a native mapping is insufficient.

The current optional compatibility targets are Pydantic AI 2.46.0, LangChain 1.4.2, and LangGraph 1.2.11; their dedicated issues must install and exercise those exact interfaces with offline doubles before support is claimed.
Pydantic AI's `TypeSafeModel` exposes confidence, distributions, unrounded scores, returned model identity, and Jev request count through provider details when available.
Its fallback response can omit earlier Jev usage, its generic request count can understate multi-request Jev steps, and function-tool hooks do not intercept output functions.
The canonical Jev-Frame evidence path therefore remains the official TypeSafe SDK adapter, while native Pydantic AI support is reused as a host integration with explicit metadata coverage.
LangChain's current `ToolRuntime` keeps invocation context outside the model-visible schema, and LangGraph leaves outer-loop and tool-node execution ownership with the host.
Keep the scope of tested native support explicit rather than promising compatibility with every LLM framework.

## 3. Invariants that every phase must preserve

Assign these identifiers to acceptance checks so future changes can be traced to the README.

| ID | Invariant |
|---|---|
| I01 | Every judgment has explicit subjects, semantics, evidence dependencies, and alternatives or a rubric. |
| I02 | A question never consumes another answer from the same Jev request. |
| I03 | A selected candidate must belong to the exact candidate snapshot shown to Jev. |
| I04 | A valid individual argument does not establish that a correlated argument tuple is valid. |
| I05 | Observations, exact derivations, model judgments, and acceptance or authorization records remain distinguishable. |
| I06 | Changed inputs invalidate dependent results transitively, while unrelated results remain reusable. |
| I07 | Evidence, caches, batches, tools, and children respect scope and authorization boundaries. |
| I08 | Confidence, evidence sufficiency, action selection, and execution authority are separate checks. |
| I09 | No external mutation is speculative, and an ambiguous outcome is reconciled before retry. |
| I10 | Budgets and deadlines apply across the entire run tree, including retries, speculation, and fallback work. |
| I11 | An unresolved result identifies why progress stopped without claiming supported completion. |
| I12 | Child results and generated proposals do not become trusted observations or executable policy automatically. |
| I13 | Evaluation labels and evaluator-only metadata never reach runtime decision inputs. |
| I14 | Several agent definitions share one implementation of the runtime, with isolated per-run state. |
| I15 | Completion requires a valid result contract and supporting evidence, not merely a confident model answer. |
| I16 | One owner controls each outer loop and each tool dispatch; a decision call never silently launches a second agent loop. |
| I17 | Foreign model output remains a proposal, and foreign usage or effects outside the integration boundary are not claimed as controlled or fully accounted. |

## 4. Frozen initial public contract

All names and signatures in this section are a frozen specification target, not working imports.
Change them only through a synchronized contract revision when a concrete scenario exposes a problem.
Prefer ordinary Python definitions and explicit callables over decorators with hidden behavior.
Keep SDK-specific objects behind the provider boundary so applications do not need to construct transport requests.

### 4.1 Agent definitions and runtime entry points

| Proposed surface | Required semantics |
|---|---|
| `AgentDefinition` | Contains a stable ID, explicit version, objective family, input type, tool and judgment registrations, candidate providers, output type, completion evaluator, and operating policy. |
| `Tool` | Wraps a typed callable with purpose, argument-source declarations, named evidence it requires and can produce, output type, effect classification, scope requirements, timeout, and retry or reconciliation contract. |
| `Judgment` | Declares Choice, Noul, or Score semantics, subject selectors, evidence selectors, dependencies, alternatives or rubric, applicability conditions, and an acceptance-policy reference. |
| `CompletionContract` | Declares required findings, typed result-field bindings, an evidence acceptance check, and whether particular negative findings constitute completion. |
| `CapabilityPackage` | Groups ordinary versioned tool, judgment, and candidate-provider definitions for explicit registration without creating another runtime. |
| `CandidateSet` | Contains the exact ordered candidates, source references, retrieval scope and version, coverage metadata, and a bounded expansion reference. |
| `Evidence` | Contains a typed value and immutable provenance metadata, with an explicit evidence kind and links to its inputs. |
| `RunContext` | Carries host-supplied scope, authority, dependencies, clock, cancellation, limits, and tracing settings without making secrets model-visible. |
| `Runtime.run(agent, inputs, context)` | Provides the asynchronous entry point and returns `RunResult[T]` using isolated state for this run. |
| `Runtime.run_sync(agent, inputs, context)` | Delegates to the asynchronous implementation and rejects use inside an already running event loop with a clear error. |
| `RunResult[T]` | Contains terminal status, a supported value only when complete, partial findings separately, evidence references, unresolved records, trace, and usage. |
| `agent.as_tool(...)` | Adapts an existing definition into a typed capability with narrower authority and the same shared runtime. |
| `DecisionClient.evaluate(judgment, inputs, context)` | Runs a scoped decision through shared compilation, evidence projection, and provider validation without an `AgentDefinition` or outer scheduler. |
| `DecisionResult` | Preserves the primitive answer, subjects, evidence and candidate references, input fingerprint, usage, and optional acceptance assessment; it never implies task completion or execution authority. |
| `Planner` | An optional typed callable over objective, permitted evidence, registered capability descriptions, and prior outcomes that returns a bounded step or plan revision. |
| Framework adapter | Maps a decision callable or Jev agent into a host tool/node and maps host agents into explicit capabilities, with declared lifecycle and accounting ownership. |

Agent definitions are reusable and immutable after validation.
Application services and credentials are supplied at run time through host dependencies, not embedded in serializable definitions.
A definition version identifies the author's semantic contract; a separate canonical digest identifies the compiled configuration used for a run.
Do not attempt to serialize arbitrary Python function closures or infer their correctness from a hash.
Record explicit tool and transformation versions, plus the application revision when available.
Capability registration is explicit Python composition rather than automatic scanning of installed packages.
Reject conflicting capability identifiers instead of silently replacing an existing registration.

### 4.2 Supported types and argument sources

The finite initial subset is `str`, `int`, `float`, `bool`, `None`, string-valued enums, literals, lists, string-keyed mappings, `T | None`, dataclasses, and Pydantic `BaseModel` records composed from the same subset.
General unions, tuples, sets, unresolved annotations, variadic and positional-only parameters, arbitrary objects, and unsupported generics are rejected initially.
Reject unsupported signatures, unresolved annotations, variadic parameters, and arbitrary object values during definition validation.
Do not coerce a string into an integer, a boolean into an identifier, or a fabricated default into a source value silently.
Compare literal members by both exact scalar type and value, so Python's equality between booleans and integers cannot cross their declared boundary.

Every tool parameter must have exactly one declared binding strategy.

| Binding strategy | Source of the final value | Required validation |
|---|---|---|
| Task input | A validated input field selected by an explicit path. | The path exists, its value has the declared type, and it belongs to this run's scope. |
| Host context | A host dependency or identity value. | It cannot be overwritten by model output and is excluded from model state unless explicitly projected. |
| Constant or function default | A definition value or an omitted optional argument. | Omission differs from explicit `None`, and default use has a recorded reason. |
| Candidate selection | A member of a recorded candidate snapshot. | Resolve the selected opaque key back to the original typed value and revalidate membership and scope. |
| Source span | An exact value extracted from an immutable source snapshot. | Preserve the original span or field path and copy its value rather than asking Jev to retype it. |
| Exact derivation | An approved deterministic transformation of known inputs. | Record transformation version, input references, and output validation. |
| Prior judgment | A previously accepted result with explicit dependencies. | Require a later evaluation boundary and a current input fingerprint. |
| Optional generated value | The typed output of an explicitly registered generation capability. | Apply structural, semantic, evidence, and authority checks before consumption. |

When several arguments are related, a binding group supplies valid tuples or a first selection narrows subsequent candidates.
For example, a selected record ID and revision must come from the same retrieved record, rather than independent pools of IDs and revisions.
For bounded multiple selection, use explicit per-candidate judgments or approved subset candidates and validate cardinality and tuple constraints afterward.
Do not enumerate every possible subset or Cartesian product without a bounded requirement.
A missing binding strategy is a definition error rather than permission to generate a value.
For hybrid workflows, authors can explicitly permit generated query strings, drafts, or other typed values without listing every possible string as a candidate.
That permission does not permit generated record identities, fabricated source spans, or replacement host credentials.

### 4.2.1 Minimal embedded decision contract

A direct call requires only a valid judgment, its subject/evidence/candidate inputs, and scoped execution context.
Use the same validators, compiler rules, SDK adapter, and evidence records as a complete agent run; do not maintain a second implementation of Jev semantics.
Dependent judgments require resolved inputs or separate calls, while an independent batch remains an optional convenience over the same contract.
Return an unassessed decision when no acceptance policy is configured, so applications can use it for advisory ranking, routing, or analysis.
An unassessed decision cannot satisfy Jev-Frame's completion contract or authorize a protected action.
Represent provider and validation failures as explicit errors; never turn them into an accepted answer or an empty-success result.
Keep evidence in a supplied run/session context when several host calls need provenance or invalidation, without requiring the host to adopt a new persistent store.
Adapters must register observations through the typed boundary and refresh source versions rather than treating a changed foreign message list as automatically synchronized evidence.

### 4.3 Candidate contract

Each candidate has an opaque local key, a typed value, model-visible descriptive fields, provenance, and a source version where available.
Separate execution-only fields from model-visible fields, and reject evaluator labels from the latter.
Detach and recursively freeze list and mapping values when the snapshot is created, and reject mutable dataclass or Pydantic model candidates.
Snapshot identity includes candidate membership, order, descriptions, source versions, and the retrieval query or expansion parameters.
Use a reserved no-fit outcome that cannot collide with a real candidate key.

Coverage must distinguish a complete query result, a truncated result, and unknown completeness.
An empty complete result, an empty failed retrieval, and a nonempty shortlist with no suitable match are different outcomes.
No-fit on a truncated shortlist does not establish that no matching item exists outside it.
Keep any total-count estimate explicitly optional.
Expansion returns a new snapshot and spends the same run budget.
If a Choice limit is exceeded, narrow or expand retrieval through the declared provider rather than silently dropping candidates or treating probabilities from separate batches as globally comparable.
Selecting a single remaining candidate still needs a suitability check when the semantic task permits no-fit.

### 4.4 Evidence contract

Each evidence record needs an ID, kind, typed value or retrievable reference, source identifier, scope, observation time, optional expiry, source version, and derivation dependencies.
Model judgments additionally retain question semantics, subject references, presented candidate snapshot, primitive answer, provider/model information, and the exact input fingerprint.
Acceptance records refer to the evidence and judgment versions they accepted.
Execution authorizations are separate, short-lived host decisions and cannot be serialized back as permanent permission.

Preserve contradictory observations even if one is newer or more confident.
Mark supersession and conflict relationships explicitly instead of overwriting the earlier record.
An evidence view includes the original source references and the contradictions relevant to the judgment.
If view-size limits would remove required evidence or conflicts, fail with an explicit insufficiency reason or invoke an authorized reduction capability.
Never turn silent truncation into a supported answer.

Use a run-local append-only collection plus indexes initially.
Keep private values out of ordinary event logs while retaining enough local evidence to explain the result to an authorized caller.
An optional event sink is an application callback, not a default external telemetry service.

### 4.5 Results and failures

Use a small terminal status set: `completed`, `unresolved`, `failed`, and `cancelled`.
Represent budget exhaustion, denied permission, missing evidence, no-fit, and ambiguous execution as typed reasons rather than introducing a separate status for every case.
Expose verified partial findings separately from the final output value.

An unresolved record contains its reason code, subjects, blocking evidence or candidate references, actions attempted, attempts or coverage limits reached, and the host input or capability needed to proceed.
Reasons must distinguish missing evidence, source conflict, incomplete candidate coverage, refuted claim, semantic ambiguity, missing capability, unaccepted judgment, permission denial, stale source, unknown write outcome, and budget exhaustion.
A refuted proposition may be a valid completed negative answer when the result contract permits it; it is not automatically a service failure.

Definition errors and invalid caller inputs fail before provider or tool effects occur.
Expected provider, tool, policy, and budget outcomes become structured run records and terminal results when recoverable progress is impossible.
Unexpected implementation exceptions preserve a sanitized cause and fail the run rather than masquerading as model uncertainty.
Task cancellation must propagate through asynchronous callers; record a cancelled outcome for inspection without swallowing the caller's cancellation signal.
Never include credentials, raw authorization headers, or unfiltered exception bodies in public diagnostics.

## 5. Runtime design

### 5.1 Compiler and internal decision program

Use a small typed node representation rather than a new programming language.
The initial node kinds are candidate retrieval, deterministic derivation, Jev judgment, tool invocation, and completion evaluation.
Child runs and optional generation are specialized tool capabilities using the same scheduling path.
Each node has an ID, versioned definition reference, explicit input references, output contract, applicability predicate, and effect classification.

The initial program must have an explicit derivation from the public definition.
Start from the completion contract's required findings and result-field bindings, resolve their registered judgment and evidence references, and recursively identify their required inputs.
Task inputs and host-supplied observations satisfy matching evidence slots directly.
Unsatisfied slots become named investigation needs with candidate providers or tools whose declared outputs can supply them.
These output declarations describe possible contributions, not a guarantee that a tool will find sufficient evidence.
When exactly one permitted capability can supply a need, bind and schedule it once its inputs are available.
When several capabilities are applicable, use a declared deterministic priority or an explicit action-selection judgment over those capabilities.
If a source is absent, bindings are unresolved, or the available vocabulary cannot express the objective, return a missing-capability or ambiguity outcome rather than inferring hidden orchestration from prose.

This means a simple agent author supplies an objective, typed capabilities, judgments, and a completion contract, while the compiler constructs the dependency program.
An advanced author can supply explicit dependency and applicability declarations through the same definitions.
The deterministic compiler does not synthesize arbitrary workflows from an objective string alone.
Hybrid objective-driven planning is provided by a configured LLM planner or an external framework loop under Section 5.8.
Unfamiliar combinations of registered tools work when their declared inputs and outputs compose, without changing the scheduler or inventing undeclared conversions.
Optional generated proposals extend this process only through the validated registered-capability boundary in Section 5.7.

The compiler must:

1. Validate unique identifiers, tool signatures, source bindings, referenced capabilities, and supported output types.
2. Resolve subject and evidence selectors without executing arbitrary model-generated paths or code.
3. Reject missing dependencies and dependency cycles within a compiled program.
4. Validate primitive-specific criteria, candidate limits, reserved no-fit keys, and correlated binding groups.
5. Produce questions that repeat all required meaning in instructions and point to explicit state fields.
6. Separate answer dependencies from branch applicability so a speculative premise is not mistaken for an established fact.
7. Emit diagnostics identifying the definition, node, subject, and invalid reference.
8. Produce a stable inspectable program before network or tool execution.

A compiler may check that a semantic description exists, but cannot prove the description is unambiguous or correct.
Make that limitation visible in API documentation and evaluation requirements.
Dynamic investigation adds validated instances of registered templates in a new bounded revision of the program.
Do not allow generated plans to inject arbitrary callable names, import paths, or new execution policies.

### 5.2 Fingerprints and invalidation

Define a judgment input fingerprint over the agent and judgment versions, explicit subjects, evidence contents and versions, candidate presentation, policy version, model selection, and compiler/projection version.
Include scope and authorization compatibility in reuse checks even if those fields are deliberately absent from model-visible state.
Preserve rubric and candidate order when creating canonical digests.
Do not hash Python `repr`, unordered sets, object identity, or secret-bearing host dependencies.
Non-JSON values must pass through an explicit stable serializer or remain noncacheable.

Maintain reverse dependency indexes so a changed input marks its dependent judgments, acceptance records, bindings, and pending actions stale transitively.
Check freshness at use time as well as when a timer or update occurs.
A completed external action is a historical fact and cannot be undone by cache invalidation.
Invalidate subsequent reasoning about it rather than replaying the action.

Record requested and returned model identifiers separately.
Prefer a pinned model identifier for reproducible evaluation.
If the provider returns only an alias with no resolved revision, say that the actual revision is unknown and disable reuse across provider calls where model identity cannot be established safely.
Do not claim reproducible model identity from `jev-latest` alone.

### 5.3 Scheduler

Use one asynchronous scheduler per run and shared runtime limits across concurrent runs.
Begin with deterministic scheduling order for ready work so tests and traces remain understandable.
Use standard task groups and bounded semaphores rather than a distributed queue.

For each scheduling round:

1. Check cancellation, deadline, and the shared budget before admitting new work.
2. Invalidate expired or changed inputs and identify applicable ready nodes.
3. Evaluate deterministic checks and construct the smallest sufficient evidence views.
4. Group independent Jev judgments only when they share a compatible authorized state projection, model configuration, and request limits.
5. Reserve resource capacity and request budget before dispatch.
6. Execute compatible reads concurrently and evaluate Jev batches.
7. Validate responses against the dispatched snapshot and discard stale late results from acceptance, while still accounting for their cost.
8. Record observations, judgments, and policy decisions separately.
9. Admit write proposals only through the guarded execution path.
10. Evaluate completion, choose a bounded investigation step if needed, or terminate with a specific unresolved reason.

All questions in a batch see the same state, so batching must never expose one tenant's evidence to another or widen a judgment's allowed projection accidentally.
Initially batch identical compatible views; add view union only with explicit projection rules and tests demonstrating no leakage or irrelevant-context change.
Speculative questions state their premise explicitly and their answers remain conditional until the branch applies.
Do not use a speculative answer in completion, a tool binding, or a child run when its premise is false or unaccepted.
External writes are never dispatched merely because their branches might become applicable.
Resolve required and result-bound completion evidence in the current scope immediately before and after an awaited semantic completion callback.

Document consistency groups for reads against mutable sources.
If a host cannot offer a coherent snapshot, preserve source versions and surface incompatible observations as a conflict.
For synchronous tools, support quick deterministic functions directly and explicitly declared blocking functions through a bounded thread executor.
Cancelling an awaiting task cannot stop a Python thread or undo an external request, so running effects must remain tracked until reconciled.
Do not advertise forceful cancellation or hard isolation for arbitrary user callables.

### 5.4 Budgets and usage

At minimum track provider attempts, submitted questions, tool attempts, investigation steps, active operations, child depth, total child runs, and a monotonic deadline.
Require finite positive limits for admitted work and a finite deadline through `RunContext`, with zero permitted to disable a class of work such as writes or child calls.
Reject negative limits, impossible timeout combinations, and unspecified unlimited retries during context validation.
Offer a documented conservative convenience preset only after the representative scenarios establish reasonable values, and do not confuse those values with provider service limits.
Allow optional token and monetary ceilings only with clearly documented accounting strength.
Use one shared ledger for the parent and children, with atomic reservations before concurrent dispatch.
Separate planned reservations, observed usage, unknown usage, and released unused reservations.
Count retry attempts and speculative judgments even when their results are discarded.

Do not multiply a batch's token usage by its number of questions.
Do not add child aggregates to parent totals when the same underlying operations are already in the shared ledger.
Deduplicate accounting by internal operation and attempt identity.
An absent token count or unknown price is not zero cost.
Only claim a verified monetary cost when a versioned rate source or actual billing evidence supports it.
If the provider cannot expose an enforceable per-call token bound, describe token and money limits as admission estimates plus observed stopping, not guaranteed billing caps.
Applications requiring a hard monetary ceiling must reject dispatch when no defensible worst-case reservation is available.

### 5.5 Acceptance and guarded execution

A semantic acceptance policy consumes primitive answers, evidence completeness, freshness, conflicts, and application-defined risk criteria.
It returns accept, investigate, reject, or handoff with explicit reasons.
There is no universal confidence threshold and no multiplication of answer probabilities under an assumed statistical independence model.
Evaluation independence inside one request does not establish statistical independence of errors.
Without an application acceptance policy, expose the judgment for inspection and leave a full agent run unresolved rather than automatically accepting it.
Standalone decision calls may return that unassessed judgment successfully without claiming accepted task completion.

Before invoking an effectful tool, perform all of these independent checks:

1. Confirm that the selected action and all bindings still reference accepted, current inputs.
2. Strictly validate the final argument object and every correlated constraint.
3. Ask the host authorizer about the exact tool, arguments, scope, effect, and current authority context.
4. Verify source versions or obtain downstream conditional-write preconditions.
5. Confirm the time and shared budget reservations.
6. Record a proposed operation and its idempotency or reconciliation identifiers.
7. Execute through the tool adapter, which owns the downstream transaction guarantee.
8. Validate and record the effect receipt before treating the task as complete.

Model-visible text cannot grant authority, alter host identity, or disable validation.
Host approval applies to an exact action digest, scope, source versions, and validity period, and must be checked again if any of them change.
After any awaited authorization, persistence, admission, or checkpoint call, revalidate the deadline, exact arguments, evidence versions, action digest, and authorization immediately before dispatch.
This local guard does not replace a downstream conditional write or transaction.
Require an explicit mutation effect declaration; do not infer safety from a function name or a model judgment.

Use the write states `proposed`, `authorized`, `in_flight`, `succeeded`, `failed_before_effect`, and `outcome_unknown`.
Only a trustworthy downstream guarantee can justify `failed_before_effect` after dispatch.
A timeout, lost response, cancelled wait, or invalid receipt after a request may have been accepted must enter `outcome_unknown`.
Record that local `outcome_unknown` evidence before propagating cancellation, even when no durable store is configured.
Reconcile through an operation lookup or equivalent read before another attempt.
Retry with the same idempotency key only when the downstream contract makes that safe, or when reconciliation establishes that the earlier effect did not occur and current authorization still permits it.
Preserve a trusted `failed_before_effect` reconciliation receipt as the final failed outcome instead of degrading it to unknown.
If reconciliation is unavailable or inconclusive, return an unresolved execution outcome and do not retry blindly.

With an in-memory runtime, process termination loses local intent records.
Consequential real writes therefore require a host-managed durable intent/receipt mechanism and downstream reconciliation or idempotency support.
The initial core must refuse such real writes without the required host contract, while allowing synthetic fixtures and explicitly supported low-risk tools.
Do not implement a database merely to obscure this boundary, and do not claim exactly-once execution.

### 5.6 Adaptive investigation

Register which capabilities can address each unresolved reason and which evidence or candidate sets they can add or refresh.
The runtime proposes a finite set of applicable next actions from these registrations.
Use deterministic prioritization when only one action is useful, and a Jev choice among explicit bounded action candidates only when semantic selection adds value.

Examples of useful progress include retrieving a missing record, expanding a truncated shortlist, checking an alternative source, refreshing an expired observation, or requesting a precise host clarification.
Repeated evaluation with unchanged inputs merely to obtain greater confidence is not progress.
Fingerprint investigation attempts by unresolved issue, action, arguments, and input version.
Do not repeat the same successful but unhelpful action without a changed hypothesis or new information.
Keep transport retries distinct from semantic investigation attempts.
Terminate when completion is accepted, no applicable action remains, an attempt limit is reached, authority is denied, cancellation occurs, or the budget expires.

### 5.7 Composition and optional generation

A child run uses the same runtime implementation with a new run ID and parent relationship.
Intersect parent authority with the child's declared requirements and requested scope; never allow a child to widen either.
Child evidence projections must satisfy both parent export rules and child read permissions.
Detect cycles using the active definition ancestry and enforce explicit depth and child-count limits.
Reject recursive re-entry by default instead of treating a depth limit as a sufficient explanation of recursion semantics.
Propagate cancellation and deadlines through the run tree.
Reserve child work against the shared budget without holding a parent semaphore in a way that deadlocks the child scheduler.
Import child results as typed findings with provenance, including unresolved or conflicting findings.
Do not replace a parent's acceptance or authorization policy with a child's confidence.

An optional reasoning or generation capability is a host-registered typed tool with its own scope, budget, and data-export authorization.
The core ships a contract and deterministic test double, while optional adapters connect explicitly configured host LLM agents.
Generated plans may reference registered capabilities, candidate or source values, and explicitly permitted typed generated arguments.
Validate their structure, dependency graph, argument bindings, and required evidence before compilation.
Generated text remains a derived proposal and must satisfy the result contract before it becomes an accepted output.
Do not execute generated source code, import generated modules, or promote generated plans into permanent policy.

### 5.8 Existing LLM frameworks and hybrid control flow

Support three placements using the same decision machinery: a direct callable inside an external loop, a complete Jev agent exposed as a capability, and an LLM planner capability inside a Jev-Frame run.
Each adapter declares who owns the outer loop, tools, retry policy, cancellation, state persistence, and total usage accounting.
An external loop keeps its existing memory, streaming, tools, and human-intervention facilities.
Jev-Frame controls only the operations routed through its public boundary.

#### Host-owned loop

Expose a configured judgment as an ordinary asynchronous callable with a finite typed input/output schema.
Wrap that callable as a LangChain tool, LangGraph node, or Pydantic AI tool using public host interfaces.
Prefer a documented thin wrapper over an adapter class when registration alone suffices.
The host injects identity, authority, dependencies, and session context; these values are never model-editable tool arguments.
An optional judgment tool can be selected by the LLM, while a required evaluation is placed in a host-controlled node, hook, or executor wrapper.
A required gate fails closed on evaluation errors or unresolved policy, and its result is bound to the exact current action or artifact being checked.
Changing the action or artifact invalidates that gate result.
Never describe an optional tool as an unskippable gate, and verify coverage for special execution paths such as output functions, direct tool calls, and resumed work.
Keep the complete decision record available to the application even if the model sees only a compact result projection.
LLM-suggested judgments are permitted as bounded advisory questions with explicit subjects and alternatives; protected acceptance criteria and authority remain host-owned.

#### Jev-Frame-owned loop

An optional planner receives an objective string, the available capability catalog, current observations, prior action outcomes, and remaining limits.
It returns a next action, a finite dependency plan, a clarification need, or a proposed final result through a typed response contract.
Validate newly generated plan instances against registered tools, argument-source rules, dependencies, and effect declarations before admission.
Reject any proposed argument whose name is also supplied by the capability's fixed arguments, independently of the proposed value source.
Treat `StepValue` and `depends_on` as references within one `PlanRevision`; use a prior outcome's recorded evidence reference with `EvidenceValue` across planner turns.
Run the configured Jev judgments on plan candidates, evidence, intermediate artifacts, or completion wherever the author places them.
Use the normal tool executor and completion policy, then feed actual outcomes back to the planner when replanning is needed.
Bound planning calls and plan revisions alongside investigation, and stop unchanged proposal cycles with an unresolved reason.
Generate one effective root run identity when the caller omits one, and use it to namespace planner calls, revisions, steps, and evidence records.
Bound asynchronous planner and result-validator callbacks by the monotonic run deadline while preserving cancellation.
Reject a blocking synchronous callback's result if it returns after the deadline, but do not claim that Python can safely interrupt arbitrary synchronous code.
Validate a proposed final result against the host-defined completion contract; an LLM's declaration that it is done does not replace that check.
For unrestricted objectives, a general result contract may accept a typed deliverable or clarification instead of enumerating every possible task in advance.

The LLM can construct unfamiliar tool sequences and free-form content without a prewritten workflow.
The plan compiler remains a validator and dependency builder, so new task shapes do not require new scheduler code.
By default, planner calls propose work and do not execute the same external tools internally.
If a host-supplied agent owns an entire delegated subtask, register that call as an executing capability with its actual effects and return its receipts; do not execute its completed steps again.

#### Interoperability contracts

| Concern | Required behavior |
|---|---|
| Schemas | Map supported public types explicitly and reject lossy mappings; foreign tool schemas do not supply missing provenance or effect contracts. |
| Tool reuse | Wrap an existing tool callable with declared bindings, scope, and effects when importing it into Jev-Frame. |
| State | Project only permitted fields; preserve observations, generated proposals, and judgments as different records. |
| Cancellation | Propagate the host signal and deadline to admitted calls, retaining unknown effect outcomes where cancellation cannot undo work. |
| Budgets | Reserve each observable operation once; a host must integrate its own LLM operations to claim a shared global ceiling. |
| Retries | Declare a single retry owner per operation and retain attempt identities across framework wrappers. |
| Usage | Report Jev and LLM usage separately and aggregate only when both are observable, including discarded and fallback attempts. |
| Events | Bridge correlation IDs and sanitized progress events; do not claim token streaming for an atomic Jev response. |
| Persistence | Let the host checkpoint its workflow; revalidate evidence and authorization on reentry and reconcile pending effects before replay. |
| Dependencies | Core-only installation works without host frameworks; test each optional adapter against recorded versions. |

Initial reference coverage is LangChain/LangGraph and Pydantic AI, plus a plain asynchronous Python caller.
Reuse Pydantic AI's native Jev support after checking metadata, primitive mappings, and accounting against the contract.
Do not make an untested native mapping the source of canonical Jev evidence or silently fabricate missing raw distributions.
Other frameworks may consume the callable API without an integration-specific dependency in the core.

### 5.9 Developer experience and capability baseline

All ten features below are part of the planned initial delivery.
JF-01 freezes the public convenience names in the README, and none is an implemented API yet.

| ID | Feature | Implementation contract |
|---|---|---|
| F01 | Decision operations | Implement select, filter, assess, score, and exact source extraction as thin compositions of the shared decision path. |
| F02 | Reusable packages | Register versioned tools, judgments, bindable host functions, examples, and evaluator-separated regression cases explicitly. |
| F03 | Preview/debugger | Expose a serializable offline compiled preview and post-run inspection of actual evidence, decisions, argument bindings, and policy reasons. |
| F04 | Capture/replay | Capture only explicitly selected sanitized records and replay through provider/tool doubles with no live execution. |
| F05 | Examples-to-policy | Fit on validation cases, freeze a policy, evaluate untouched cases, and compare advisory shadow judgments without business effects. |
| F06 | Tool reuse/discovery | Import existing host tools or host-supplied MCP descriptors with explicit missing semantic metadata and bounded scoped catalog retrieval. |
| F07 | Propose/select | Generate a bounded set of typed alternatives, filter invalid candidates deterministically, and evaluate surviving snapshots with Jev. |
| F08 | Document collections | Compose retrieval, passage selection, claim assessment, and deterministic evidence aggregation with coverage and contradiction records. |
| F09 | Useful investigation | Rank applicable evidence actions using declared priorities first, with optional bounded semantic selection and precise clarification outcomes. |
| F10 | Generate/verify | Compose generation, deterministic checks, semantic assessments, and bounded revision using the existing planner/runtime. |

#### Decision operations and reusable packages

Selection always permits no-fit when the semantic contract permits it, including a singleton candidate set.
Filtering produces per-item verdicts and explicit unresolved items; batch-independent questions only over compatible authorized evidence views.
Assessment preserves Noul probability semantics, scoring preserves ordered rubric levels and fractional results, and extraction copies an exact source field or span.
Any optional ranking composition must declare its comparison strategy and preserve ties and unknowns; a new global ranking primitive is not required for initial delivery.
Report the number of provider attempts and questions for composed operations.

Reusable packages declare versioned inputs, evidence needs, bindings, tool effects, and completion semantics while accepting application functions by explicit registration.
Keep examples and evaluation labels outside model-visible definitions and runtime imports.
Supply one generic document-evidence package whose small parts can be used by a plain caller and both reference frameworks.
Do not automatically adopt a package's example thresholds as an application's acceptance policy.

#### Developer inspection and fixture replay

Offline preview performs no tool, provider, or candidate-retrieval calls; display unresolved inputs as such when no snapshot is supplied.
Show exact permitted questions and projections to authorized callers while default serialized logs remain redacted.
Expose declared dependencies, selected source bindings, acceptance reasons, and usage coverage rather than a fabricated model rationale.
Use schema-versioned deterministic event records and the existing optional event sink, without a web UI or telemetry service requirement.

Capture is explicit and allowlisted, with stable local aliases for references and a manifest of redaction or unavailable fields.
If redaction removes evidence needed to reproduce the behavior, mark the fixture incomplete for that purpose and refuse a false claim of faithful replay.
Replay dispatches only registered test doubles, matches recorded call identities and inputs, and fails on an unexpected call or missing fixture.
Keep a deterministic replay distinct from an explicitly requested reevaluation against a new model or policy.
No captured trace is an executable resume token, authorization grant, or permission to repeat an effect.

#### Tool catalogs and document evidence

Use a finite host-registered tool catalog and public framework/MCP interfaces; do not scan the machine or open new server connections automatically.
Validate or reject foreign schemas against the supported type subset, and require explicit bindings, scope, and effect metadata missing from their descriptors.
Bind every activated foreign tool to the exact catalog scope and reject cross-scope dispatch before argument evaluation or invocation.
Treat MCP `isError` or equivalent protocol status as failure before validating structured result content.
Refresh changed tool schemas under a new version and invalidate affected pending choices.
Retrieve a scoped shortlist with coverage metadata before semantic selection, retain a no-fit outcome, and bound expansion.
The host supplies an already configured MCP session; transport, credentials, approvals, and connection lifecycle remain its responsibility.

Document processing lives in a generic capability package using injected retrieval and immutable source snapshots.
Passage offsets or field paths resolve against the exact retained source version, including Unicode and duplicate-text cases.
Derive aggregate findings from explicit claim-evidence links and preserve opposing findings.
Report retrieval and document coverage separately from judgment acceptance, and never compare probabilities from separate shortlists as globally normalized values.
No vector database, crawler, PDF engine, or new retrieval service is required.

#### Hybrid recipes and calibration

Propose/select accepts typed LLM-produced alternatives with their generator metadata and marks them as proposals.
Remove structurally invalid or forbidden candidates before evaluation; handle zero survivors and explicit no-fit without invoking an arbitrary fallback.
Generated record IDs do not become valid references without resolution against a supplied source or candidate snapshot.

Generate/verify accepts an artifact type, a registered generator, named deterministic and semantic checks, and a bounded revision policy.
Every finding identifies the artifact revision and relevant evidence, so checks rerun when their inputs change.
Treat failed or errored required deterministic checks as blocking; semantic confidence cannot override them.
Deduplicate unchanged revisions and stop at success, handoff, no progress, cancellation, deadline, or budget exhaustion.
The core does not run generated programs; any compiler, test runner, or execution sandbox is an explicitly registered host capability.

Clarification is a typed unresolved request describing the missing field, relevant subjects, and allowed answer shape.
A host response becomes new validated input with provenance and requires normal evidence and authority revalidation.
Initial support permits a new linked run or host-managed continuation; it does not promise core durable resume.

Calibration consumes evaluator-only labels in a separate path and reports counts, coverage, errors, and handoffs for candidate policies.
Freeze the selected policy and dataset split before held-out testing, with no automatic promotion after inspecting held-out failures.
Shadow comparisons consume permitted immutable observations and never execute the candidate policy's business tools.
Offline shadow comparisons use recorded outcomes; live advisory calls require configured provider access and explicit budgets.
Do not infer downstream outcomes for actions the real application did not take; retain incomplete counterfactual coverage.

## 6. Representative scenarios to drive implementation

Use small synthetic fixtures with no customer data, credentials, private evaluation history, or business policy copied into the core.
The examples below describe behavior rather than executable code.
Keep their domain logic in examples and fixtures so they demonstrate framework generality.

### Scenario A: Select a document and quote its relevant source field

The task asks which document in an explicitly supplied catalog supports a statement.
A candidate provider returns documents with stable keys, versions, and relevant excerpts.
Jev selects a candidate or no-fit, and a deterministic tool returns an exact field or source span.
The result contains the selected document, exact source value, supporting judgments, and source references.
Unrelated documents, duplicate titles, misleading descriptions, missing candidates, and no-fit are all fixture variants.

This is the first complete read-only vertical slice.
Success requires no application code that constructs a Jev request or manages its own scheduler.

### Scenario B: Resolve incomplete or contradictory evidence

The first retrieval returns a truncated shortlist with no accepted match.
The framework expands retrieval once, obtains an additional candidate, and reevaluates only the affected judgments.
A separate variant supplies conflicting sources and permits a registered corroborating read.
The result either satisfies the contract with preserved provenance or returns a conflict or coverage issue with the attempted steps.
Another variant returns identical evidence repeatedly and must terminate without a confidence-seeking loop.

### Scenario C: Conditionally update a synthetic versioned record

The task identifies a record and proposes a label change in an in-memory fake service.
The candidate tuple binds the record ID and expected revision together.
The host authorizer approves the exact update independently of semantic confidence.
One fixture changes the revision before execution, one denies authority, and one commits the write but loses the reply.
The runtime must block the stale update, block the unauthorized update, and reconcile the lost reply without duplicating the effect.
This scenario validates the write machinery without connecting to a real external system.

### Scenario D: Compose two specialists and preserve disagreement

A parent delegates two bounded evidence checks to definitions using the same runtime.
The children see only their permitted evidence and share the parent's limits.
One fixture produces compatible findings and another produces conflicting findings.
The parent retains both evidence chains and uses its own completion policy rather than choosing the more confident child automatically.
Additional variants exercise cancellation, an attempted authority increase, a cycle, and simultaneous budget exhaustion.

### Scenario E: Reject or validate an optional generated proposal

An explicit test capability supplies a proposed plan when the available decision vocabulary is insufficient.
One proposal uses registered tools and valid bindings, and another invents a tool or introduces an unauthorized mutation.
The valid plan still passes the same compiler and acceptance path, while the invalid plan produces a specific rejected-proposal outcome.
No secondary model access is necessary to test this contract.

### Scenario F: Add Jev to an existing LLM agent

A host-framework agent receives the objective to compare public documents and draft a recommendation.
Its scripted LLM chooses retrieval queries, gathers fixture documents, calls a Jev evidence judgment, and revises its draft after a conflict is reported.
Run the scenario through real LangChain/LangGraph and Pydantic AI framework interfaces with offline model doubles, and through a plain asynchronous caller.
The application keeps its original outer loop and tools without defining a Jev-Frame agent or duplicating orchestration.
One variant exposes Jev as an optional advisory tool; another places a required judgment before accepting the final draft.
Check that skipping the optional tool is allowed, bypassing the required boundary is blocked, and changing the draft invalidates its earlier acceptance.
Preserve both models' observable usage, source references, host cancellation, and errors across the adapter.

### Scenario G: Plan and replan from an objective

A Jev-Frame run receives a new objective to find suitable reference documents and produce a short comparison, without a task-specific dependency graph.
A configured planner proposes a search, then a source read, then a generated draft, using existing registered capabilities.
A failed read or conflicting observation causes a different next step, and Jev evaluates the configured evidence or completion judgments.
Use a host-framework agent with a scripted model as the planner, then verify a separately registered executing specialist does not have its completed actions replayed.
Reject invented tools and invalid source identities while allowing declared generated query strings and draft content.
The run ends with an accepted deliverable, clarification, or explicit unresolved outcome under bounded planning revisions.
Offline success proves integration mechanics; a live hybrid demonstration is a separate provider gate.

### Scenario H: Reuse, preview, and replay a decision package

Bind one generic document-evidence package to two synthetic catalogs without modifying the package or runtime.
Preview unresolved and fully supplied decisions offline, then exercise select, filter, assess, score, and source extraction with scripted responses.
Capture an explicitly allowlisted failure, add an evaluator-only expected outcome, and replay it with network and real tool dispatch blocked.
Redaction that removes required evidence must produce an incomplete-fixture diagnostic.

### Scenario I: Import tools and select a scoped capability

A host supplies framework tools and a fake MCP session with a versioned finite catalog.
Declare missing bindings and effects, retrieve a bounded subset, and select or expand without exposing another scope's capabilities.
A changed schema, unsupported type, incomplete coverage, and missing no-fit are negative variants.

### Scenario J: Generate, select, and verify an artifact

A scripted generator proposes several drafts, including an invalid candidate.
Deterministic validation removes invalid candidates before Jev assesses the remaining snapshot.
The selected artifact fails a required exact check, receives actionable feedback, and is revised once successfully.
High semantic confidence cannot bypass the exact failure, and unchanged drafts terminate under progress limits.

### Scenario K: Investigate evidence across a large collection

Injected retrieval supplies more documents than fit in one decision and reports truncation.
Retrieve and bind passages, assess separate claims, retain conflicting sources, and aggregate supported findings with visible coverage gaps.
An ambiguity variant requires a typed user clarification, followed by a linked run with validated additional input.
No global ranking may be inferred from independently normalized batch answers.

### Scenario L: Calibrate and shadow an application policy

Use separate synthetic validation and held-out case groups to compare versioned acceptance policies.
Freeze a selected policy and measure it on held-out data, preserving failures and zero-denominator metrics.
Run the candidate policy against immutable recorded observations in shadow mode and verify no business tool can dispatch.
Do not report unavailable counterfactual outcomes or missing provider usage as known successes or zero cost.

## 7. File ownership and dependency direction

Create files when their phase needs them rather than scaffolding an empty tree.
The following is a responsibility map, not a requirement for a class or package per concept.
Keep small related responsibilities together until real complexity warrants a split.

| Proposed path | Responsibility | May depend on |
|---|---|---|
| `src/jev_frame/__init__.py` | Small public export surface. | Public definitions, runtime entry point, and results. |
| `src/jev_frame/definitions.py` | Typed definitions, bindings, candidate contracts, and definition validation. | Standard library and chosen boundary validation library. |
| `src/jev_frame/state.py` | Evidence, fingerprints, dependency indexes, unresolved records, and run snapshots. | Definitions and deterministic helpers. |
| `src/jev_frame/compiler.py` | Definition-to-program compilation and Jev question construction. | Definitions and state views. |
| `src/jev_frame/provider.py` | Thin official SDK adapter and normalized answer variants. | SDK and internal question/result contracts. |
| `src/jev_frame/decisions.py` | Standalone public decision calls using the shared compiler, state, and adapter. | Compiler, state, provider, and optional policy. |
| `src/jev_frame/policy.py` | Semantic acceptance and exact-action authorization contracts. | Definitions and evidence records. |
| `src/jev_frame/runtime.py` | Scheduler, shared budget, tool dispatch, investigation, composition, and cancellation. | Compiler, state, provider, and policy. |
| `src/jev_frame/evaluation.py` | Offline case runner, metrics, split manifests, and report serialization. | Public runtime API without privileged access to labels during a run. |
| `src/jev_frame/integrations/` | Thin optional framework wrappers only where plain callable registration is insufficient. | Public Jev-Frame contracts and the selected optional host framework. |
| `tests/` | Deterministic contract, behavior, and failure-injection checks. | Public API plus narrowly justified internals. |
| `examples/` | Generic runnable scenarios, added only after the implementation exists. | Public imports only. |

Split execution or composition out of `runtime.py` only when the implemented logic becomes difficult to inspect in one module.
The runtime must never import example definitions or evaluator answer keys.
Application adapters must depend on the public API, with no application-specific switch statements inside the scheduler.
Only the provider adapter should need knowledge of SDK response representations.
Keep installation, limits, decisions, and current implementation status in the README as features become real.

## 8. Ordered implementation work packages

Every phase ends with a usable checked increment and a compact checkpoint.
The phase sections group architectural outcomes, while `ISSUES.md` supplies the finer-grained implementation order and explicit prerequisites.
Foundations such as diagnostics, event records, and admission accounting are delivered before the full runtime and reused by later phases.
Do not treat a later phase heading as permission to duplicate an earlier shared facility.
The owner is Sol high; independent native delegation is optional only when separately authorized and must not become a worker hierarchy.
Do not introduce an arbitrary time estimate as a substitute for acceptance evidence.
If a phase is blocked on live access, complete its offline work and record the exact remaining gate.

### Phase 0 — Refresh sources and freeze the contract

**Depends on:** explicit authorization to implement.

**Actions:**

1. Read the current README, AGENTS, this plan, working-tree status, and relevant uncommitted diffs.
2. Refresh the official SDK docs, changelog, primitive limits, native Pydantic AI Jev support, and maintained-alternative comparison.
3. Verify SDK Python requirements and choose a specific tested version without calling the paid API.
4. Confirm the finite supported annotation subset and boundary validation dependency.
5. Write the proposed public API specification into the README, including nonexecutable representative authoring shapes until code exists.
6. Record run statuses, primitive response variants, default denial behavior, the local import name, and persistence limitations.
7. Define synthetic fixture cases and their expected evidence paths separately from their model-visible inputs.
8. Select a validation split, a held-out split, and a policy-version format before tuning semantic thresholds.
9. Specify the minimal direct decision API, planner responses, and adapter ownership contracts for the three usage modes.

**Acceptance:** the contract can express all twelve representative scenarios without a new application-written event loop or application logic in the core.
An existing host loop can use Jev without an `AgentDefinition`, and objective-driven planning composes through registered capabilities.
Every open issue is marked either a reversible default, a compatibility check, or an owner decision.
Licensing and publication may remain unresolved because they do not block local implementation.

**JF-01 result:** completed as a documentation-only contract freeze.
The README now fixes the supported types, bindings, entry points, failure variants, ownership rules, scenario paths, fixture identity, split rules, and policy versioning.
Read-only isolated checks imported SDK 0.7.0 and instantiated Choice, Noul, and Score on CPython 3.11.15 and 3.14.6 without provider access.
Named-framework execution remains assigned to JF-12 and JF-13 rather than being claimed from documentation inspection.

### Phase 1 — Package skeleton and typed boundaries

**Depends on:** Phase 0.

**Actions:**

1. Add the minimal local package layout and manifest for the selected Python, SDK, and validator versions.
2. Implement immutable definitions, binding strategies, result variants, limits, and typed diagnostics.
3. Inspect callable signatures and reject incomplete semantic or source contracts before execution.
4. Implement strict task-input and tool-output validation through the chosen library.
5. Keep importing the package free of network calls, environment mutation, and credential requirements.
6. Add tests for valid definitions, unsupported annotations, duplicate names, missing bindings, and invalid input or output values.

**Acceptance:** local import and definition validation work offline, invalid definitions trigger no tool/provider invocation, and the documented annotation subset is accurate.

**JF-02 result:** implemented in `src/jev_frame/definitions.py` with public exports and focused standard-library tests.
Missing bindings, unsupported signatures and types, unresolved annotations, scalar coercion, conflicting IDs, invalid references, unsafe mutation metadata, invalid limits, and falsely complete usage fail before any operation.
The suite passes against editable installs on CPython 3.11.15 and 3.14.6, and the built wheel imports without credentials or optional frameworks.

### Phase 2 — Evidence and candidate state

**Depends on:** Phase 1.

**Actions:**

1. Implement distinct evidence record kinds, source references, immutable candidate snapshots, and coverage metadata.
2. Implement exact field/span binding and deterministic derivation provenance.
3. Build view projection with explicit scope checks, source links, and contradiction preservation.
4. Implement stable serialization, digests, reverse dependency indexes, and freshness checks with an injectable clock.
5. Invalidate judgments, accepted bindings, and pending actions when relevant evidence, candidates, or versions change.
6. Add tests for duplicate candidate labels with distinct identities, reserved no-fit collisions, missing spans, scope leaks, source conflicts, and transitive invalidation.

**Acceptance:** replacing one source snapshot invalidates only its dependent decisions, candidate reordering changes the relevant fingerprint, and unauthorized evidence never enters a decision view.

**JF-03 result:** implemented in `src/jev_frame/state.py` with the candidate contract extended in `src/jev_frame/definitions.py`.
Candidate snapshots preserve identity, order, coverage, retrieval provenance, and explicit no-fit outcomes.
Evidence records preserve scope, freshness, exact source bindings, dependencies, supersession, conflicts, and completed-effect history.
Focused tests cover T03-T09, including duplicate labels, reserved-key collisions, coverage states, deterministic fingerprints, Unicode spans, scope rejection, contradiction capacity, expiry, and selective transitive invalidation.

### Phase 3 — Pure decision compiler

**Depends on:** Phases 1–2.

**Actions:**

1. Implement typed nodes and explicit dependency edges with deterministic ordering.
2. Derive the required dependency program from the completion contract and registered evidence producers, then compile supported judgments to provider-neutral request specifications.
3. Make subjects, state paths, candidate descriptions, and speculative premises explicit in every generated question.
4. Compile correlated arguments as tuple selection or sequentially constrained binding.
5. Validate primitive limits, absent references, unsupported return contracts, and cycles.
6. Expose an inspectable compilation result for debugging without secrets or hidden execution.
7. Supply the offline preview portion of F03 with unresolved inputs represented explicitly and no hidden retrieval.

**Acceptance:** request-shape tests prove that renamed question IDs do not remove semantic information, dependent questions occupy different stages, and invalid tuples cannot be constructed by the binder.
The compiler constructs Scenario A from public contracts without requiring an application-written scheduler, and an unresolvable evidence requirement yields a precise diagnostic.
No network is required for compiler tests.

**JF-04 result:** implemented in `src/jev_frame/compiler.py` with public `compile_agent` and `preview_agent` entry points.
The compiler walks backward from completion references, resolves unique registered producers, validates tool bindings and result fields, separates dependent judgment stages from applicability, and emits stable inspectable nodes and diagnostics without invoking callbacks.
The candidate contract now uses explicit `Judgment.candidate_set` for dynamic Choice questions; dynamic choices cannot mix fixed criteria, add the reserved no-fit option, and count it toward the 255-option bound.
Focused checks cover T10-T13 and the preview portion of T58, including opaque routing IDs, cycles, correlated tuple rejection, primitive limits, partially bound previews, bounded registered revisions, callback non-dispatch, deterministic no-fit, and failed retrieval.

### Phase 4 — SDK adapter and offline provider checks

**Depends on:** Phase 3.

**Actions:**

1. Implement a thin asynchronous adapter around the selected official client.
2. Preserve Choice, Noul, and Score answer variants, request IDs, model metadata, distributions, and optional usage.
3. Verify answer IDs, types, candidate membership, probability ranges, finite numbers, rubric levels, and documented normalization tolerances.
4. Reject missing or malformed required answers before the batch can authorize downstream work.
5. Configure client ownership explicitly so a runtime does not close a host-owned shared client accidentally.
6. Choose one retry owner and ensure actual attempts are observable and budgeted.
7. Prefer SDK retry support when its behavior can satisfy the run budget; otherwise disable SDK retries and add only the bounded admission logic required at the adapter boundary.
8. Use an SDK-supported fake transport or client double to test payloads, parsing, timeout, authentication failure, throttling, and cleanup.

**Acceptance:** SDK wire behavior is exercised offline, Noul has no invented confidence, fractional Score values survive, and retry layers cannot multiply each other.
Live compatibility remains a separate unpassed gate until Phase 11.

**JF-05 result:** implemented in `src/jev_frame/provider.py` around the public `AsyncTypeSafeClient.system_one` interface from `typesafe-sdk==0.7.0`.
The adapter disables SDK retries per call, admits and records each framework-owned attempt once, preserves request and model identity, counts every resubmitted question, and leaves host-owned clients open.
Strict batch validation covers answer completeness and type, candidate membership, finite probabilities and confidence, normalization within `1e-3`, exact ordered Score legends, fractional Score range, and optional nonnegative usage.
Focused SDK mock-transport checks cover T14-T17, including unknown candidates, missing and malformed answers, NaN, bad distributions, near-zero Noul, fractional Score, throttling, retry exhaustion, timeout, authentication, cancellation, cleanup, sanitized failures, and unknown usage.
No live request or paid provider usage was performed, so live compatibility remains explicitly unverified.

### Phase 4A — Embedded decisions and portable integration

**Depends on:** Phases 1–4.

**Actions:**

1. Expose the standalone decision call and result using the shared compiler, evidence state, and provider adapter.
2. Demonstrate a plain asynchronous call and the public callable boundary for thin host wrappers.
3. Exercise advisory host invocation with offline doubles and a scripted Jev provider; complete named-framework conformance in its own adapter issue after core policy contracts exist.
4. Check supported native Pydantic AI Jev behavior before adding custom mapping code, recording any metadata gap.
5. Bind host context outside model-visible arguments and preserve errors, cancellation, provenance, and separately observable usage.
6. Implement the advisory portion of Scenario F, with optional dependencies isolated from core imports.
7. Implement the shared request-admission, deadline, and usage primitives needed by direct calls, then reuse them in the Phase 5 scheduler.
8. Add F01 decision operations as thin shared compositions and establish the early F02 package and F03 inspection contracts.

**Acceptance:** a host callable invokes Jev without adopting the Jev-Frame scheduler, and importing the core requires neither host framework.
This provides a usable portable integration before full standalone-agent delivery; named-framework adapters add their required checkpoints after Phase 6 and complete hybrid flows follow Phase 8.

**JF-06 result:** implemented in `src/jev_frame/decisions.py` and `src/jev_frame/limits.py` over the existing compiler, evidence store, and provider adapter.
`DecisionClient` exposes evaluate, select, filter, assess, score, exact source extraction, and a portable callable without constructing an `AgentDefinition` or outer scheduler.
Direct inputs enforce exact subject, evidence, candidate, and scope mappings; recorded decision fingerprints now include subject values as required by the contract.
Selection preserves opaque candidate identity, duplicate labels, singleton suitability and explicit no-fit, while incomplete no-fit retains its coverage gap and expansion reference.
The initial filter path keeps separately scoped items in separately accounted requests and uses an explicit host classifier instead of inventing a universal Noul threshold.
`UsageLedger` atomically admits operations, attempts and questions, deduplicates identities, enforces monotonic deadlines and concurrency, and keeps observed, estimated, reserved, released and unknown token measurements distinct.
Focused checks cover T17, T21, T44 and T56 with a credential-free scripted provider, including all five convenience operations, exact provenance, portable invocation, zero/singleton/duplicate/no-fit selection, per-item filtering, subject-sensitive fingerprints, one-winner concurrent admission, and non-multiplied batch token usage.

**JF-07 result:** implemented in `src/jev_frame/inspection.py` and wired into the existing direct decision path.
`jev-frame.event.v1` records run-local sequence, run, correlation, parent-operation, operation and attempt identities through an optional application callback with no default external destination.
Event payload keys are allowlisted per kind, provider and sink exception text is never copied, attempt IDs and usage coverage survive round-trip serialization, and cancellation is recorded before it propagates.
Default decision serialization and inspection expose actual primitive answers, provenance links, candidate keys, accepted bindings, public policy reasons, unresolved reason codes and an omitted-field manifest without evidence values or host context.
Exact evidence, questions, candidate contents and unresolved detail require an explicit permitted projection and remain constrained to the recorded evidence store and matching candidate digest.
Public diagnostics distinguish definition, service and semantic failures and identify the responsible definition, node, source path, corrective action and optional capability without fabricating model rationale.
Focused checks cover T39 and the completed-decision portion of T58 with synthetic data, including hostile exception, dependency and authorization secrets, sink failure, exact projection, provenance resolution, accepted policy evidence, event correlation and cancellation.

**JF-08 result:** implemented in `src/jev_frame/packages.py` using the existing definitions, compiler, direct decisions and exact-source state machinery.
Candidate providers now require an explicit typed binding for every parameter, and the compiler records those sources without invoking the provider.
Compiled programs retain package IDs and versions in their canonical configuration, so a package-only version change alters the digest without hashing arbitrary function closures.
`bind_document_evidence_package` validates stateless typed retrieval and read functions before execution and returns ordinary tools, judgments and a candidate provider inside the existing `CapabilityPackage`.
The generic package composes selection, catalog-backed reading, exact text-field extraction, claim assessment, evidence requirements and result requirements, while its completion helper requires an application-owned acceptance-policy ID.
Two synthetic applications bind different functions and catalogs and use the package judgments and exact-source locator directly without package or runtime changes.
Public authoring examples use only `jev_frame` imports, and evaluator-only expected outcomes remain in a separate module that is absent from runtime definitions and provider inputs.
Focused checks cover T57, missing and incompatible functions, duplicate capability IDs, version-only digest changes, direct operations and evaluator-label isolation without invoking live services.

### Phase 5 — Read-only vertical slice

**Depends on:** Phase 4A and its shared admission primitives, alongside Phases 2–4.

**Actions:**

1. Implement isolated run state, node lifecycle, the ready queue, compatible batching, and authorized read execution.
2. Implement the shared budget ledger, deadline checks, bounded concurrency, and cancellation propagation.
3. Add deterministic completion evaluation and explicit unresolved output.
4. Expose asynchronous and synchronous public run entry points over the same runtime.
5. Complete Scenario A using public API imports and a scripted provider.
6. Run two different definitions concurrently to demonstrate state isolation and runtime reuse.
7. Record a compact trace linking requests, evidence, decisions, tool invocations, and result fields.

**Acceptance:** Scenario A completes or escalates correctly through the public API, all required work is accounted for, incompatible scopes are not batched, and no application-specific branch appears in the controller.
This phase achieves Level B with offline provider evidence, not full README completion.

**JF-09 result:** implemented in `src/jev_frame/runtime.py` over the existing compiler, evidence store, direct decision client, provider adapter, admission ledger, and event log.
Candidate retrieval is explicit, ready nodes run in stable compiler order under bounded concurrency, and dependent judgments are separate calls over refreshed evidence.
Each run has isolated evidence and findings while concurrent definitions share the runtime ledger and operation semaphore.
Only pure and read tools are admitted, blocking callables use bounded threads, and cancellation records a result before propagating without claiming that the underlying thread stopped.
Completion strictly constructs the declared output type and then requires an application-owned semantic callback, so schema validity alone cannot complete a run.
Late answers over invalidated inputs remain historical, cost is retained, and staleness, exhaustion, unsupported completion, provider failure, and cancellation remain distinct observable outcomes.
Focused offline checks cover T18 through T23 using deterministic provider and tool doubles; live provider compatibility remains a separate unauthorized gate.

### Phase 6 — Acceptance policy and guarded writes

**Depends on:** Phase 5, including its Phase 4A foundations; optional framework adapters are not prerequisites.

**Actions:**

1. Add versioned semantic acceptance and the exact-action host authorizer.
2. Implement current-input revalidation and source-version preconditions immediately before dispatch.
3. Implement write operation states, receipt validation, idempotency identity, and reconciliation.
4. Require host durable intent support for consequential writes that outlive the process.
5. Make mutation disabled unless the host supplies an appropriate explicit authorization and execution contract.
6. Complete Scenario C against a fake service that supports version checks and injected lost replies.
7. Test revocation between proposal and dispatch, mismatched approval digests, denied actions, and cancellation after a possible effect.
8. Provide a framework-neutral required-checkpoint contract, testing failures and changed artifacts with a fake host; named adapters later prove dispatch-path coverage in Scenario F.

**Acceptance:** no confidence value bypasses host authority, stale source versions prevent effects, and a committed-but-timed-out operation results in one verified effect after reconciliation.

**JF-10 result:** implemented in `src/jev_frame/policy.py` and the existing shared runtime.
Versioned `AcceptancePolicy` receives the native primitive answer, current evidence records and candidate coverage and records accept, investigate, reject or handoff separately from execution authority.
`ActionProposal` computes a stable digest over the exact tool version, validated arguments, scope, source versions and mutation effect; the host authorizer is consulted again immediately before dispatch so denial, expiry or revocation fails closed.
`RequiredCheckpoint` returns an action-digest-bound record, and checkpoint errors or a changed action cannot reuse an earlier decision.
The write path records proposed, authorized and in-flight states in the host's durable intent store before dispatch, validates typed receipts, marks possibly accepted failures and cancellation outcome-unknown, and uses only the declared reconciliation lookup without blind retry.
An explicit string `MutationContract.idempotency_parameter` resolves the prior contract ambiguity between claiming idempotency support and identifying the actual downstream key argument.
Focused synthetic checks cover T24 through T30 and the neutral required-checkpoint foundation for T48; no real effect, live provider, database or exactly-once claim is involved.
Real external mutations remain disabled unless separately authorized and accepted for the host application.

### Phase 7 — Adaptive investigation and selective recomputation

**Depends on:** Phase 5 for read-only investigation; effectful actions additionally require Phase 6.

**Actions:**

1. Add typed unresolved reasons and capability registrations describing the issues they can address.
2. Generate only applicable next-action candidates with bounded expansion and retry limits.
3. Implement progress fingerprints and reject repeated unchanged investigation steps.
4. Recompile affected program instances and retain unrelated current judgments.
5. Complete Scenario B with missing evidence, truncation, conflicting sources, and no-progress variants.
6. Distinguish service retry exhaustion from exhausted investigation coverage in results and traces.
7. Deliver F09 precise clarification outcomes and bounded useful-action selection, and reuse these in the F08 document-evidence package.

**Acceptance:** a newly discovered candidate can change the result, unnecessary judgments are not recomputed, contradictions remain visible, and unchanged evidence cannot produce an infinite loop.

**JF-11 result:** implemented in `src/jev_frame/investigation.py` and the existing shared runtime and ledger.
`InvestigationAction` explicitly declares the unresolved reasons, need IDs, scopes, priority, effect and callback that it can address; mutation actions are rejected at definition time.
The runtime selects the first applicable stable-priority action, admits a semantic investigation and its read call separately, fingerprints the unresolved issue plus current inputs, candidate snapshots and evidence, and stops unchanged output as no-progress.
A changed candidate snapshot reevaluates only the affected selection under a new decision operation ID, while unrelated current judgments and all earlier provider usage remain retained.
Evidence returned by an investigation uses the ordinary append-only store and can link contradictions without replacing either source.
`ClarificationRequest` validates a supported answer type for one missing path and returns through `RunResult.clarifications`; the host can create a fresh linked run with the answer, but the core does not persist or resume a suspended run.
Focused synthetic checks cover T04, T31, T32 and T64, including no action, exhausted investigation budget and denied scope.

### Phase 8 — Typed composition and hybrid planning

**Depends on:** Phase 7.

**Actions:**

1. Adapt an agent definition to a tool through the same runtime entry point.
2. Enforce parent-child scope intersection, shared budget, depth/count limits, and ancestry cycle checks.
3. Preserve child evidence references, conflicts, partial outcomes, and cancellation state.
4. Avoid parent/child semaphore deadlocks and test simultaneous child admission.
5. Add the explicit typed generation capability contract and validate returned plan proposals.
6. Complete Scenarios D and E entirely with local fixtures and scripted capability outputs.
7. Adapt configured host LLM agents as proposal-only planners or explicitly executing specialists, preserving their distinct responsibilities.
8. Support bounded next-step planning, plan revisions, typed generated arguments, and proposed final results through the normal compiler and completion checks.
9. Complete Scenarios F and G with actual optional-framework interfaces and offline model doubles, including replanning after changed evidence.
10. Verify event correlation, external-usage gaps, retry ownership, cancellation, and absence of duplicate tool dispatch.
11. Complete F06 tool import/discovery, F07 propose/select, and F10 generate/verify using the shared registry, compiler, and executor.

**Acceptance:** a child cannot increase authority or spend outside the parent ledger, cancellation reaches all children, conflicting child outputs survive, and generated plans cannot invent executable capabilities.
Both host-owned and Jev-Frame-owned loops work with a configured LLM agent; a new objective does not require a new scheduler branch or prewritten task graph.
Provider connections are explicitly supplied by the host, and no live LLM credentials are needed for offline conformance.

### Phase 9 — Inspection and host persistence boundary

**Depends on:** Phases 5–8.

**Actions:**

1. Stabilize schema-versioned run-result and event serialization with provenance links.
2. Add an optional host event sink and explicit sensitive-field projection rules.
3. Ensure evidence, trace, and usage can be inspected without exposing host dependency objects or credentials.
4. Document in-memory lifetime and the host responsibilities for durable operations and retained source records.
5. Permit exporting an inspection snapshot without implying that it is safe to execute again.
6. Test that exported findings resolve to their provenance and that restricted fields do not leak through errors or traces.
7. Complete F03 run inspection and F04 explicit sanitized fixture capture and deterministic replay without implementing live resume.

**Acceptance:** a caller can explain every accepted result field and effect receipt from exported permitted metadata, while private payload retention remains a deliberate host choice.
Automatic restart/resume is deferred until a host persistence contract and migration policy are explicitly implemented.
Never provide a nominal resume method that can replay writes from a trace.

### Phase 10 — Evaluation and evidence of generality

**Depends on:** Phases 5–9, with fixture design established in Phase 0.

**Actions:**

1. Implement an offline evaluation runner using only the public runtime API.
2. Keep runtime inputs and evaluator-only outcomes in separate structures and process paths.
3. Measure the metrics and baselines in Section 10 under matched conditions.
4. Fit any application acceptance thresholds on the validation split and freeze a versioned policy before held-out runs.
5. Test unfamiliar combinations of already registered capabilities without changing runtime code.
6. Count domain-specific definitions and semantic configuration separately from core implementation changes.
7. Serialize reports with dataset versions, case groups, configuration digests, model/SDK metadata, and known limitations.
8. Compare the same host LLM agent with and without Jev at selected points, including the overhead and outcomes of replanning and handoffs.
9. Complete F05 validation-only calibration, held-out policy reporting, and side-effect-free shadow comparisons.

**Acceptance:** deterministic cases pass, leakage checks pass, held-out reporting distinguishes completion and escalation, and failures are retained rather than omitted from aggregate results.
A small synthetic suite demonstrates mechanics rather than real-world reliability.

### Phase 11 — Live smoke, documentation, and local delivery

**Depends on:** Phases 1–10 for complete delivery, although a bounded live adapter smoke may be authorized earlier.

**Actions:**

1. Run all deterministic checks in a clean project environment and build a local installable artifact.
2. Validate the artifact in a fresh environment and run public examples from installed imports.
3. With explicit authorization for the provider call budget and data submission, run synthetic Choice, Noul, Score, and dependent-two-stage smoke cases.
4. Record the actual SDK version, requested/returned model identifiers, observed usage, request count, latency, and unavailable fields.
5. Keep real mutation testing separate from the provider smoke and require the target application's authority and acceptance evidence.
6. Update the README with working local setup commands, supported examples, API contracts, implemented status, and precise remaining limitations.
7. Update the Codex continuation checkpoint so it reflects actual implementation state and model selection behavior.
8. Report tests, live checks, skipped or blocked gates, remaining risks, and exact changed files.
9. Validate optional integrations in separate environments and, when authorized, record live LLM-plus-Jev evidence independently of the Jev-only smoke.

**Acceptance:** Levels A–C are complete, Level D is either supported by recorded live evidence or explicitly marked blocked, and no unsupported Level E claim appears.
Do not publish, release, change visibility, select a license, or deploy as part of local implementation delivery.

## 9. Behavioral acceptance matrix

Use the smallest tests that demonstrate these behaviors, with deterministic clocks, scripted provider answers, and controlled fake services.
Parameterize closely related cases rather than building a testing framework.
Each check must assert an observable result or prohibited effect, not merely mirror the implementation.

| ID | Setup and trigger | Required observable result | Phase |
|---|---|---|---|
| T01 | A tool parameter has a type but no source binding. | Definition validation fails before any operation. | 1 |
| T02 | A caller supplies a string for a strict numeric field or an unsupported object. | Input is rejected without coercion or provider access. | 1 |
| T03 | Two candidates have the same display label but different IDs and versions. | Binding preserves the selected identity and its provenance. | 2 |
| T04 | Retrieval is empty, failed, truncated, or complete with no match. | Outcomes preserve these distinctions and expand only when allowed. | 2, 7 |
| T05 | A decision view requests another scope's evidence. | Projection fails and no cross-scope payload is sent. | 2 |
| T06 | One evidence item changes after two dependent judgments and one unrelated judgment. | Only the transitive dependents become stale. | 2 |
| T07 | Policy, model identity, candidate order, or candidate description changes. | Affected accepted decisions are not reused. | 2, 5 |
| T08 | A source expires without any explicit update event. | Use-time freshness check prevents stale acceptance. | 2, 5 |
| T09 | Contradictory evidence would exceed the view budget. | The runtime preserves the conflict or reports insufficient view capacity. | 2 |
| T10 | Question B depends on answer A. | A and B cannot be evaluated as dependent answers in one batch. | 3 |
| T11 | Question IDs are replaced with opaque strings. | Instructions still name the correct subjects and meaning. | 3 |
| T12 | Independent argument values combine into an invalid tuple. | Tuple binding or a sequential constraint prevents dispatch. | 3 |
| T13 | Candidate or rubric limits are exceeded. | Compilation reports a bounded contract error instead of silent truncation. | 3 |
| T14 | A fake provider returns an unknown candidate, wrong type, missing answer, NaN, or invalid distribution. | The affected batch fails validation and enables no effects. | 4 |
| T15 | Noul is near zero and Score is fractional. | Noul remains a probability of yes and Score remains fractional without fabricated confidence. | 4 |
| T16 | A provider throttles, then succeeds or exhausts the retry budget. | Attempts remain bounded and counted once each. | 4 |
| T17 | Usage metadata is missing. | The result reports unknown usage rather than zero. | 4, 5 |
| T18 | Independent questions share an authorized view. | They can be batched without consuming each other's answers. | 5 |
| T19 | A speculative branch is not selected or accepted. | Its answer cannot complete the run or bind an executed action. | 5 |
| T20 | Different agents run concurrently through one runtime. | Their evidence and results remain isolated while shared limits hold. | 5 |
| T21 | Two operations race for the final budget reservation. | At most one is admitted, with no overspend from the race. | 5 |
| T22 | Input changes while a provider request is in flight. | The late answer is retained as historical evidence but is not accepted as current. | 5 |
| T23 | The output is schema-valid but lacks required supporting evidence. | Completion is rejected or remains unresolved. | 5 |
| T24 | Confidence is high but authorization is absent, denied, or revoked. | No write occurs. | 6 |
| T25 | Authority is valid but evidence acceptance fails. | No write occurs. | 6 |
| T26 | The source version or approval-bound arguments change before execution. | Conditional execution fails safely or authorization is renewed for the new exact action. | 6 |
| T27 | A write commits but its response is lost. | The outcome becomes unknown, reconciliation observes the effect, and no duplicate is sent. | 6 |
| T28 | Reconciliation cannot establish whether a write happened. | The run remains unresolved with no blind retry. | 6 |
| T29 | A possibly completed write is cancelled or returns a malformed receipt. | It is not mislabeled failed-before-effect. | 6 |
| T30 | An application requests consequential writes without durable host intent support. | The contract is rejected before the external effect. | 6 |
| T31 | Retrieval expansion adds a suitable candidate. | Affected selection is recomputed and unrelated decisions remain reusable. | 7 |
| T32 | Investigation returns unchanged evidence or repeats identical arguments. | Progress detection stops the loop with a specific unresolved reason. | 7 |
| T33 | A child requests wider authority or unauthorized evidence. | Scope intersection rejects the expansion. | 8 |
| T34 | A child cycle, depth overflow, or child-count overflow is attempted. | Dispatch is bounded and the cause is visible. | 8 |
| T35 | Parent cancellation occurs while children and synchronous tool work are active. | New work stops, cooperative work cancels, and potentially active effects remain tracked. | 8 |
| T36 | Children consume usage concurrently. | The parent reports each underlying operation once within the shared ledger. | 8 |
| T37 | Two child results conflict. | Both findings and evidence chains remain available. | 8 |
| T38 | A generated plan invents a tool, forms a cycle, or requests a forbidden mutation. | Compilation or authorization rejects it without executing generated code. | 8 |
| T39 | Credentials and sensitive source text appear in host dependencies or a raised error. | Default trace/result serialization does not leak them. | 9 |
| T40 | Evaluator labels or privileged metadata are attached to a case. | Captured provider/tool inputs exclude them. | 10 |
| T41 | Repeated variants originate from the same source case. | Reports group them and do not count them as independent samples. | 10 |
| T42 | A new definition combines existing tools in an unseen valid arrangement. | It runs without a change to the central controller. | 10 |
| T43 | A local package is installed into a clean environment. | Public imports and documented examples work without repository-relative imports. | 11 |
| T44 | A plain asynchronous caller invokes a judgment without an agent definition. | A typed decision with provenance returns without starting an outer scheduler. | 4A |
| T45 | Each reference host registers and invokes a Jev callable with offline model doubles. | Native tool/node invocation preserves result variants and errors without copying the host loop. | 4A |
| T46 | A model supplies a replacement identity, scope, or evidence from another run. | Host context cannot be overwritten and unauthorized evidence is rejected. | 4A |
| T47 | The LLM skips an optional Jev tool or attempts to bypass a required checkpoint. | Optional use remains optional; the required host path rejects an unassessed result. | 6, 8 |
| T48 | A checked draft or action is changed, or the required judge fails. | Earlier acceptance cannot authorize the changed item and the gate fails closed. | 6 |
| T49 | A planner receives a new objective and a tool later reports conflicting evidence. | It forms and revises a valid capability sequence without changing the controller. | 8 |
| T50 | A planner proposes new query text, a fabricated record ID, or an unregistered tool. | Declared generated text is permitted while invalid identities and capabilities are rejected. | 8 |
| T51 | A configured specialist already executes an action and returns its receipt. | The parent imports the outcome without dispatching that action again. | 8 |
| T52 | Planner revisions repeat or host and SDK retries could multiply. | A declared retry owner and progress limits bound attempts, with all visible calls accounted. | 4A, 8 |
| T53 | External LLM usage or an earlier Jev fallback attempt is unavailable. | Combined usage is incomplete, never reported as a fully verified total. | 8, 10 |
| T54 | A host cancels or resumes work with changed evidence or an uncertain write receipt. | New dispatch stops or revalidates, and pending effects reconcile before retry. | 8, 9 |
| T55 | Core-only and adapter-specific packages are installed separately. | Core imports need no host framework, and reference adapters pass on recorded versions. | 11 |
| T56 | Invoke the five convenience operations with empty, singleton, duplicate, and unresolved candidates. | Primitive semantics, exact source identity, no-fit, and per-item uncertainty survive; request counts are accurate. | 4A |
| T57 | Bind one versioned package to different host functions and attach evaluator cases. | Reuse requires no core changes, collisions fail, and evaluator data never enters runtime definitions. | 4A, 10 |
| T58 | Preview a partially bound definition and inspect a completed decision. | Preview dispatches nothing; diagnostics identify exact missing bindings and inspection exposes only permitted recorded evidence. | 3, 4A, 9 |
| T59 | Capture and replay a mutation-containing trace or a fixture with missing/redacted evidence. | Test doubles handle every call, no live effect or provider runs, and incomplete reproduction fails explicitly. | 9 |
| T60 | Calibrate on validation cases, evaluate frozen held-out cases, then shadow business observations. | Labels stay outside model inputs, thresholds do not retune on test failures, and shadow cannot dispatch business effects. | 10 |
| T61 | Import foreign tools, change a schema, or discover across a truncated catalog. | Missing semantics fail before dispatch, changed versions invalidate selections, and scope/coverage remain explicit. | 8 |
| T62 | A generator proposes invalid alternatives, unsupported factual IDs, or zero usable candidates. | Deterministic filtering precedes Jev, provenance remains proposed, and zero/no-fit terminates without fabricated selection. | 8 |
| T63 | Evaluate claims over truncated document retrieval with duplicate Unicode passages and opposing sources. | Exact source/version bindings and contradictions remain, coverage gaps are visible, and no global batch-probability ranking is invented. | 7 |
| T64 | Investigation needs a user field, then receives a host-supplied clarification. | A typed unresolved request is returned; validated new input can start a linked run without implying durable resume. | 7 |
| T65 | A generated artifact fails an exact check while semantic confidence is high, or repeats unchanged. | Completion remains blocked, revision-specific checks rerun as needed, and bounded no-progress termination occurs. | 8 |

Do not use tests that require real credentials in the default suite.
Live provider tests must be explicitly selected, bounded, and omitted from ordinary offline checks.
No network access should be necessary for deterministic behavioral validation after dependencies are installed.

## 10. Evaluation protocol

### 10.1 Case records and leakage prevention

Each case has an ID, source lineage, dataset version, group ID, split, task inputs, permitted initial evidence, capability registry, scope, limits, and evaluator-only acceptance criteria.
The runtime receives only the task portion and never the expected answer or expected tool sequence.
Use allowlisted projections rather than removing a known label field from an otherwise unrestricted object.
Compare captured model state, candidate metadata, tool arguments, and generated-plan inputs against evaluator-only fields.
Assess acceptable evidence paths, including alternative valid retrieval orders, instead of requiring an exact predetermined trace.

### 10.2 Baselines

Use at least these comparisons where meaningful:

1. A sufficient-evidence Jev run receives all evidence needed for the decision up front.
2. An agentic Jev-Frame run receives the starting evidence and must retrieve missing information through the registered capabilities.
3. A deterministic baseline performs the parts solvable by exact rules or lookup alone.
4. A relevant existing framework or application baseline may be added only with a compatible public task and explicit authorization for any extra provider cost.
5. For hybrid cases, use the same host-framework LLM agent with and without the proposed Jev decision placements, holding tools, evidence, and budgets constant.

For the sufficient-evidence comparison, report the privileged evidence difference explicitly rather than pretending it measures retrieval ability.
For matched alternatives, hold the dataset split, task contract, evidence availability, allowed tools, permissions, and budgets constant.
Separate orchestration overhead from provider latency and distinguish cold and warm conditions when reporting them.

### 10.3 Required metrics

| Metric | Definition or reporting rule |
|---|---|
| Supported independent completion | A run completes without a handoff and the evaluator accepts both the result and its evidence. |
| Correct escalation | The run hands off or remains unresolved when the available evidence, capability, or authority cannot support completion. |
| Harmful automatic error | An automatically accepted result or executed effect violates the case's designated harmful-error criterion. |
| Unnecessary handoff | The case was solvable within its permitted tools and budget but the run escalated unnecessarily. |
| Retrieval failure | Necessary candidates or evidence were not found, separately from a wrong judgment on adequate evidence. |
| Service failure | Provider or tool availability prevented completion, separately from semantic uncertainty. |
| Latency | Report run latency and relevant stage latency with sample counts and distribution summaries. |
| Verified cost per correct completion | Divide verified total cost for the evaluated cohort, including its failed runs, by supported correct completions. |
| Semantic configuration burden | Report new tools, judgments, candidate providers, binding contracts, and domain-specific policy needed for a new domain. |
| Runtime generality | Report whether unfamiliar valid tool combinations required any core controller changes. |

Return undefined cost per correct completion when there are no correct completions or cost is not verifiable.
Report the counts and denominators behind every rate.
Keep supported completion and correct escalation separate rather than hiding harmful errors in one combined accuracy number.
Report seed values when the provider or fixture generator supports them, and otherwise record repetitions without inventing a seed guarantee.
Group repeated or near-duplicate cases and report variation across independent case groups.
Preserve negative results and explain the scope of small samples.

### 10.4 Acceptance policy calibration

Use validation data to select application thresholds and acceptance rules.
Freeze the policy version, model selection, prompt or semantic definitions, retrieval configuration, and dataset version before held-out evaluation.
Any change after inspecting held-out failures requires a new evaluation version and an untouched test set for a new generalization claim.
The framework provides measurement and policy plumbing, while the host application owns acceptable error rates and consequential-action activation.
Without those criteria, report the measured behavior and keep automatic consequential actions disabled.

## 11. Decision register and explicit limits

| Decision | Default for implementation | Revisit when |
|---|---|---|
| Public API naming | Use the names frozen in README `Frozen initial contract` and Section 4. | A representative scenario exposes ambiguity or unnecessary configuration through a synchronized contract revision. |
| Package name | Use `jev_frame` locally, with no public registry name claim. | The owner authorizes publication planning. |
| License | Leave undecided. | The owner selects a license before distribution or publication. |
| Runtime form | An embeddable decision API and optional shared agent scheduler, with one outer-loop owner per integration. | A concrete integration requires another execution surface. |
| Storage | Run-local memory plus host callbacks and explicit durability contracts for consequential writes. | Crash-safe resume becomes a funded and explicitly scoped requirement. |
| Cross-run cache | No cross-run semantic reuse initially. | Compatibility, authority revocation, source retention, and model identity rules are implemented and tested. |
| Acceptance thresholds | Host-owned, versioned, and calibrated, with no universal built-in value. | Validation evidence supports a particular application policy. |
| Model identity | Prefer an explicit model version and retain returned metadata. | The provider's version-resolution contract changes. |
| Planning and generation | A configured host-framework agent or callable, with offline doubles and explicit generated-value bindings. | A new framework requires a concrete public adapter or a new capability. |
| Reference integrations | Optional LangChain/LangGraph and Pydantic AI wrappers plus ordinary asynchronous calls, reusing native Jev support when adequate. | A requested integration passes its versioned conformance checks. |
| Global accounting | Control admitted Jev-Frame work and report external usage coverage explicitly. | A host provides admission hooks and complete attempt-level accounting for the whole loop. |
| Recursive agent calls | Reject active-ancestry cycles. | A concrete bounded recursive algorithm and budget semantics are specified. |
| Real side effects | Disabled without host authority and downstream execution guarantees. | The exact application action has passed its operational and semantic gates. |
| Persistence/resume | Export inspection state and opt-in offline test fixtures without executable live resume. | A host-backed state and operation journal, compatibility policy, and crash tests exist. |
| Reusable recipes | Explicit ordinary Python packages and host functions, including document evidence and hybrid verification. | A concrete use case requires additional domain packages. |
| Tool discovery | Scoped selection from a host-registered finite catalog or supplied MCP session. | A separately scoped requirement needs new transport or registry infrastructure. |
| CI | Start with reproducible local checks. | The owner authorizes repository CI and its selected platform or project policy requires it. |
| Distribution | Build and validate locally only. | The owner explicitly requests release or publication. |

The framework validates structure and enforces its execution contracts, but cannot prove semantic correctness, source truth, complete retrieval, or honest effect declarations by arbitrary application code.
An embeddable Python library is not a sandbox for hostile tools or policies.
The host remains responsible for credentials, actual access enforcement, trusted tool implementations, downstream transactions, and data-retention rules.
Do not create a database, message broker, web server, telemetry platform, general plugin registry, or second agent runtime to fill unspecified future needs.

## 12. Sol execution instructions and checkpoint

When the owner explicitly starts implementation, use the following handoff instruction:

> Implement Jev-Frame according to the current README and IMPLEMENTATION_PLAN.md using Sol at high reasoning effort.
> Preserve unrelated changes and inspect the current repository before editing.
> Work through the phases in dependency order, beginning with the public contract and one complete read-only scenario.
> Use the official TypeSafe SDK, keep all agent definitions on one shared runtime, and preserve the listed invariants.
> Expose the standalone decision API early, reuse native framework integrations, and complete both host-owned and Jev-Frame-owned hybrid scenarios without duplicating event loops.
> Make reversible implementation decisions without repeatedly asking for confirmation.
> Do not publish, deploy, select a license, submit private data to a provider, incur new paid-provider usage, or enable consequential real writes without the required explicit authorization.
> Complete offline implementation and checks while any live gate is blocked, and report the blocked gate separately.
> Maintain a compact checkpoint, keep README implementation claims accurate, and deliver concrete acceptance evidence rather than equating a successful build with completion.

At every substantive stopping point, update a compact continuation entry in `.codex/README.md` with the following fields:

| Field | Required content |
|---|---|
| Objective | Current phase and concrete acceptance target. |
| Decisions | Selected SDK/Python versions and any changed provisional API decisions. |
| Changed files | Files actually edited and their responsibilities. |
| Checks | Exact runnable checks and their observed outcomes. |
| Failures | Reproductions, unresolved risks, and the latest hypothesis. |
| Evidence | Local result artifacts, source references, and live request metadata where permitted. |
| Remaining gates | Missing authorization, account access, policy calibration, or publication decisions. |
| Next action | The next bounded implementation step. |

### Planning checkpoint

- Objective: produce a detailed implementation plan for Sol from the current README without starting implementation.
- Completed: repository inspection, current TypeSafe documentation verification, a maintained-alternative survey, and an independent read-only requirements audit by Sol high.
- Deliverables: this plan and a README link identifying it as a proposed implementation handoff.
- Implementation state: no source code, executable examples, dependencies, tests, CI, or package artifacts created.
- Evidence limits: no SDK installation, live Jev request, benchmark, or external mutation was performed.
- Next action: on implementation authorization, start Phase 0 and record the tested dependency and API decisions.

### Framework integration extension checkpoint — 2026-09-19

- Objective: make Jev composable with existing LLM frameworks and enable objective-driven planning through a configured LLM.
- Decisions: three usage modes, a public decision callable, optional reference integrations, one owner per loop and dispatch, and native Pydantic AI reuse where compatible.
- Changed files: `README.md` and `IMPLEMENTATION_PLAN.md` only.
- Completed checks: official framework documentation inspected and proposal references reconciled across API contracts, architecture, scenarios, phases, and acceptance checks.
- Failure: direct TypeSafe documentation retrieval failed; provider facts remain dated and require refresh in Phase 0.
- Evidence: Section 2.3 source links and new Scenarios F/G and checks T44–T55 describe the proposed integration and its verification targets.
- Implementation state: design only; no framework imports, live model calls, implementation code, dependencies, or tests were created or executed.
- Next action: after implementation is requested, freeze both direct and agent APIs in Phase 0 and deliver Phase 4A before completing the standalone runtime.

### GitHub backlog checkpoint — 2026-09-19

- Objective: incorporate F01–F10 and publish scoped Sol implementation issues with synchronized repository documentation.
- Decisions: product scope lives in README, detailed behavioral contracts in this plan, and issue dependencies and acceptance ownership in `ISSUES.md`.
- Coverage: Scenarios A–L and checks T01–T65 cover the existing framework and the ten additions.
- Changed files: README, this plan, issue roadmap, and `.codex/README.md`; implementation remains unstarted.
- Authorization: the user requested committing and pushing expanded documentation to main without a pull request.
- Evidence: GitHub tracker #1 and implementation issues #2–#23 are published, and every posted body matches its prepared specification.
- Verification: the 22-task prerequisite graph is acyclic and every F01–F10 feature and T01–T65 check is mapped; complete the documentation diff and remote commit checks before handoff.
- Next action: implement the first contract issue when requested, using Sol high and the roadmap's prerequisites.

### JF-01 contract freeze checkpoint — 2026-09-19

- Objective: freeze the public contracts and refresh provider and host-framework compatibility without creating runtime code.
- Decisions: Python 3.11 or newer, local import `jev_frame`, `typesafe-sdk==0.7.0`, direct `pydantic>=2.12,<3`, strict finite annotation support, ordinary explicit registrations, and the public names in README `Frozen initial contract`.
- Compatibility: isolated imports and primitive construction passed on CPython 3.11.15 and 3.14.6 with SDK 0.7.0 and Pydantic 2.13.5; no API request was made.
- Framework evidence: current documentation and metadata were inspected for Pydantic AI 2.46.0, LangChain 1.4.2, and LangGraph 1.2.11; executable adapter conformance remains owned by JF-12 and JF-13.
- Contract coverage: README walks Scenarios A-L and specifies direct decisions, agent runs, planner variants, bindings, evidence, policy, authorization, events, fixtures, splits, and failure behavior.
- Remaining gates: package/runtime implementation starts at JF-02, live provider compatibility requires separate authorization, licensing remains undecided, and no publication is authorized.
- Next action: create the minimal package manifest and typed definition boundaries for JF-02, then prove T01 and T02 offline.

### JF-12 LangChain and LangGraph integration checkpoint — 2026-09-19

- Objective: expose direct Jev decisions and exact-action checkpoints through the recorded LangChain 1.4.2 and LangGraph 1.2.11 public interfaces without adding another scheduler.
- Decisions: the optional `langchain` extra owns both pinned host dependencies, `ToolRuntime` carries non-model host context, `ToolNode` remains the dispatcher, and the required node always reconstructs and checks the current action proposal.
- Verification: offline tests invoke real `StateGraph` and `ToolNode` interfaces, preserve the full `DecisionResult` artifact, reject forged scope and provider failure, propagate cancellation, count one provider attempt, permit an omitted optional tool, reject a failed checkpoint, and invalidate an older checkpoint after changed arguments.
- Core boundary: `jev_frame` imports without either optional framework, and the adapter is loaded only from `jev_frame.integrations.langchain`.
- Remaining gates: no live model, hosted LangGraph service, application authorization, business mutation, publication, or deployment was exercised or authorized.

### JF-13 Pydantic AI integration checkpoint — 2026-09-19

- Objective: expose direct Jev decisions and exact-output checkpoints through Pydantic AI 2.46.0 while using its native TypeSafe support only where the translated semantics remain observable.
- Decisions: the optional `pydantic-ai` extra uses `pydantic-ai-slim[typesafe]`, host state stays in `RunContext.deps`, compact tool results use `ToolReturn.return_value`, complete Jev records use private `ToolReturn.metadata`, and required output functions perform their own exact-action checkpoint instead of relying on function-tool hooks.
- Native reuse: scripted `TypeSafeModel` conformance preserves a bounded Noul probability, returns the nearest rubric level while retaining the fractional score and distribution, and leaves usage partial or unknown when the real Jev request count is absent.
- Verification: offline tests invoke real `Agent`, `FunctionModel`, `Tool`, `ToolOutput`, and `TypeSafeModel` interfaces; cover optional skip, Noul and Score records, hidden scope, provider failure, cancellation, changed output, rejected checkpoint, special output-tool placement, and fallback usage omission.
- Remaining gates: no live TypeSafe or fallback model, application authorization, business mutation, publication, or deployment was exercised or authorized.

### JF-14 existing-tool import and discovery checkpoint — 2026-09-19

- Objective: import explicitly supplied host tools and retrieve bounded capability candidates without scanning packages, opening sessions, or inferring authority from foreign schemas.
- Decisions: catalog queries filter scope before deterministic text matching, candidate keys bind catalog, tool, descriptor version, schema digest and scope, complete empty snapshots mean no-fit, and expansion remains bounded by the catalog maximum.
- Activation: application metadata must supply every binding, effect, evidence declaration and scope requirement before an ordinary `Tool` is created; changed schemas invalidate selections and the shared runtime owns the one admitted dispatch.
- Schema boundary: only closed finite JSON Schema structures that map losslessly to the frozen type subset are accepted; foreign mutations require an application-authored Jev `Tool` because their receipt and reconciliation contract cannot be inferred from schemas.
- Verification: focused offline checks use a fake configured MCP session and a real LangChain tool with no remote service, and cover missing semantics, scope isolation, truncation, no-fit, bounded expansion, malformed schemas, stale versions, strict runtime dispatch, errors and cancellation.
- Remaining gates: no real MCP server, remote framework service, credentials, business mutation, semantic catalog selection, publication, or deployment was exercised or authorized.

### JF-15 typed composition checkpoint — 2026-09-19

- Objective: expose an `AgentDefinition` as a typed capability that reuses the same runtime while isolating child evidence and bounding shared authority, depth, count, deadline and usage.
- Decisions: child scope and authority equal the parent's values, host dependencies and evidence are explicit allowlists, only the child read/export intersection is projected, active definition ancestry rejects cycles, and imported evidence receives run-scoped identities.
- Accounting: child wrappers admit a child identity but hold no operation or semaphore reservation, underlying provider, tool and write attempts remain in the shared atomic ledger, and child usage aggregates are added once to the parent result rather than to the ledger again.
- Outcomes: completed child values enter normal parent evidence, unresolved findings remain partial, conflicting specialists remain separate, child attempts cannot supersede parent evidence, and cancelled ambiguous effects import their `OUTCOME_UNKNOWN` execution references before cancellation propagates.
- Verification: focused synthetic tests cover exact scope and evidence intersection, cycles, depth and count exhaustion, one-slot execution, concurrent attempt identities, contradictory findings, parent completion rejection, unresolved provenance, cancellation and an admitted synthetic child mutation with an unknown outcome.
- Remaining gates: no live provider, consequential real effect, distributed worker, durable cross-run resume, publication, or deployment was exercised or authorized.

### JF-16 hybrid planning checkpoint — 2026-09-19

- Objective: run unfamiliar objectives through bounded typed plans, actual-outcome replanning, host acceptance, and a propose-filter-select recipe without giving generated text execution authority.
- Decisions: one asynchronous callable owns planner generation, every step names a registered capability, generated values are distinct from evidence and completed-step references, the shared runtime owns dispatch, and the host owns final semantic acceptance.
- Limits: planner calls and revisions use stable identities in the shared atomic ledger, unchanged plan fingerprints stop no-progress loops, and missing provider usage remains unknown rather than zero.
- Outcomes: invalid plans return typed validation outcomes without dispatch, failed step outcomes return to the planner, clarification and handoff remain explicit, and a final proposal completes only after strict output validation and the host acceptance predicate.
- Frameworks: real LangChain `RunnableLambda` and Pydantic AI `Agent` plus `FunctionModel` interfaces drive the planner offline while Jev-Frame retains dispatch and completion ownership.
- Verification: six focused core tests and two optional-framework tests cover an unseen three-step objective, changed retrieval, invented tools and evidence, no-progress, rejected completion, one-time specialist effects, zero-survivor no-fit, and one admitted Jev selection.
- Remaining gates: no live planner, live TypeSafe request, consequential real effect, application acceptance calibration, publication, or deployment was exercised or authorized.

### Correctness audit checkpoint — 2026-09-20

- The objective was to repair the eleven reported validation, scope, evidence, execution, reconciliation, and planning boundary defects without expanding the roadmap.
- Commits `755454f`, `5005ab8`, `f37a95d`, `10cd337`, and `9fc7d1c` contain the implementation and focused regressions.
- The shared boundaries now enforce exact literal types, detached immutable candidate snapshots, exact imported activation scope, MCP protocol errors, current completion evidence, final mutation revalidation, preserved unknown reconciliation evidence, trusted no-effect reconciliation, planner fixed arguments, callback deadlines, and consistent run identities.
- `StepValue` and `depends_on` remain revision-local by contract, while cross-turn reuse resolves the prior `StepOutcome.evidence_ref` through `EvidenceValue`.
- The full 119-test suite passes under CPython 3.11 and 3.14 with all optional integrations, Ruff and mypy pass, all offline examples pass, both distribution artifacts build, and an isolated core-only wheel import passes.
- The supplied audit probes now fail closed or return the documented unresolved or failed states, with one expected early `InputValidationError` proving the strict-Literal boundary.
- No live model, consequential external write, application acceptance calibration, publication, deployment, push, pull request, or GitHub issue mutation was exercised under the audit authorization.
