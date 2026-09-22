# JF-22 delivery evidence

This record applies to the JF-22 changeset on `codex/jev-frame-implementation`, based on `a2599a9`.
Deterministic tests and examples ran on 2026-09-22 without using provider credentials or network access after dependency installation.

## Verified versions and artifacts

| Component | Verified version |
|---|---|
| Jev-Frame | 0.1.0 |
| CPython | 3.11.15 and 3.14.6 |
| TypeSafe SDK | 0.7.1 |
| Pydantic | 2.13.5 |
| LangChain | 1.4.2 |
| LangGraph | 1.2.11 |
| Pydantic AI Slim | 2.46.0 |

Official TypeSafe SDK, changelog, model, primitive, state, and response documentation was refreshed before delivery.
The selected SDK patch validates malformed API keys before transport and keeps supplied key material out of public error and client representations.
Current LangChain tool and LangGraph workflow documentation and the maintained Pydantic AI TypeSafe integration were also inspected before verification.
TypeSafe documentation identifies `jev-1.13.0` as the current stable text-only model, while this offline record makes no claim about live behavior.

`uv build --clear` produced `dist/jev_frame-0.1.0-py3-none-any.whl` and `dist/jev_frame-0.1.0.tar.gz`.
Archive inspection found only the public package and metadata in the wheel, and the package, README, tests, and build configuration in the source distribution.
No `.env`, VCS data, Codex workspace files, bytecode, local trace, credential, or private evaluation artifact was present.

## Commands and results

| Gate | Exact command | Result |
|---|---|---|
| CPython 3.11 suite | `uv run --python 3.11 --frozen --all-extras python -m unittest discover -s tests -v` | 142 tests passed on 3.11.15. |
| CPython 3.14 suite | `uv run --python 3.14 --frozen --all-extras python -m unittest discover -s tests -v` | 142 tests passed on 3.14.6. |
| Lint | `uv run --frozen --all-extras --with ruff ruff check src tests examples` | Passed. |
| Types | `uv run --frozen --all-extras --with mypy mypy src/jev_frame --ignore-missing-imports` | Passed across 22 source files. |
| Build | `uv build --clear` | Wheel and source distribution built. |
| Core wheel | `uv venv --python 3.11 /tmp/jev-core.7P2kcS` then `uv pip install --python /tmp/jev-core.7P2kcS/bin/python dist/jev_frame-0.1.0-py3-none-any.whl` | Public import passed with LangChain, LangGraph, and Pydantic AI absent. |
| Core examples | From `/tmp`, `env -u PYTHONPATH /tmp/jev-core.7P2kcS/bin/python /Users/chayanaggarwal/Code/Jev-Frame/examples/document_evidence.py` and the same command for `document_evidence_cases.py` | Passed from installed imports. |
| LangChain wheel | `uv venv --python 3.11 /tmp/jev-lang.a2Igj8` then `uv pip install --python /tmp/jev-lang.a2Igj8/bin/python 'dist/jev_frame-0.1.0-py3-none-any.whl[langchain]'` | Adapter import and `examples/langchain_decision.py` passed from `/tmp` with `PYTHONPATH` unset. |
| Pydantic AI wheel | `uv venv --python 3.11 /tmp/jev-pyd.fOedpb` then `uv pip install --python /tmp/jev-pyd.fOedpb/bin/python 'dist/jev_frame-0.1.0-py3-none-any.whl[pydantic-ai]'` | Adapter import and `examples/pydantic_ai_decision.py` passed from `/tmp` with `PYTHONPATH` unset. |
| Distribution safety | Standard-library `zipfile` and `tarfile` inspection of both artifacts | Expected paths only and no forbidden local or secret-bearing files. |

The initial attempt to run two `uv run --python` matrices concurrently was invalid because both commands rebuilt the same `.venv`.
The recorded results above are from sequential clean runs.

## Scenario coverage

| Scenario | Concrete offline evidence |
|---|---|
| A | `test_compiler.test_scenario_a_compiles_without_dispatch_and_serializes` and `test_runtime.test_scenario_a_completes_with_exact_source_and_separate_calls`. |
| B | `test_investigation.test_expansion_rechecks_only_selection_and_preserves_conflict`, `test_investigation.test_no_action_exhaustion_and_scope_denial_are_distinct`, and `test_investigation.test_unchanged_expansion_stops_with_no_progress`. |
| C | `test_policy.test_stale_source_after_authorization_blocks_dispatch`, `test_policy.test_lost_or_malformed_reply_reconciles_without_retry`, and `test_policy.test_inconclusive_reconciliation_stops_without_retry`. |
| D | `test_composition.test_two_conflicting_children_share_one_slot_and_one_ledger`, `test_composition.test_scope_and_evidence_widening_fail_before_child_access`, and `test_composition.test_parent_cancellation_reaches_child_work`. |
| E | `test_compiler.test_bounded_revision_accepts_only_registered_capabilities` and `test_planning.test_cycle_and_forbidden_mutation_are_rejected_without_dispatch`. |
| F | The complete LangChain, LangGraph, and Pydantic AI integration test modules, the planning-framework tests, and both installed adapter examples. |
| G | `test_planning.test_unseen_objective_runs_generated_sequence_and_validates_result`, `test_planning.test_failed_observation_causes_changed_bounded_proposal`, and `test_planning.test_executing_specialist_is_dispatched_once`. |
| H | The package, direct-decision, compiler preview, inspection, and offline-fixture replay test modules plus the installed document examples. |
| I | The capability catalog test module and `test_langchain_integration.test_existing_tool_uses_real_langchain_dispatch_once`. |
| J | The artifact test module and `test_planning.test_propose_select_filters_before_jev_and_handles_zero_survivors`. |
| K | The document collection test module and `test_investigation.test_typed_clarification_allows_a_linked_fresh_run`. |
| L | The calibration test module and grouped, leakage-safe evaluation checks in `test_evaluation`. |

## T01-T65 coverage

| Check | Concrete offline evidence |
|---|---|
| T01 | `test_definitions.test_missing_binding_fails_without_invoking_tool`. |
| T02 | `test_definitions.test_strict_validation_rejects_scalar_coercion` and `test_definitions.test_unsupported_signatures_and_types_fail`. |
| T03 | `test_state.test_duplicate_labels_retain_identity_and_revision`. |
| T04 | `test_state.test_coverage_states_and_no_fit_remain_distinct`, `test_compiler.test_empty_or_failed_candidates_are_not_provider_questions`, and bounded investigation tests. |
| T05 | `test_state.test_expiry_and_scope_are_checked_at_use_time`. |
| T06 | `test_state.test_invalidation_is_transitive_and_selective`. |
| T07 | `test_state.test_order_description_policy_and_model_change_fingerprint`. |
| T08 | `test_state.test_expiry_and_scope_are_checked_at_use_time`. |
| T09 | `test_state.test_conflicts_are_preserved_or_capacity_fails`. |
| T10 | `test_compiler.test_dependencies_create_distinct_evaluation_stages`. |
| T11 | `test_compiler.test_scenario_a_compiles_without_dispatch_and_serializes`. |
| T12 | `test_compiler.test_independent_candidate_bindings_cannot_form_a_tuple`. |
| T13 | `test_compiler.test_primitive_limits_fail_instead_of_truncating`. |
| T14 | `test_provider.test_semantically_invalid_answers_reject_the_batch` and `test_provider.test_nan_and_sdk_structural_failure_are_sanitized`. |
| T15 | `test_provider.test_wire_shape_and_primitive_semantics`. |
| T16 | `test_provider.test_retries_are_bounded_and_each_attempt_is_admitted_once` and `test_provider.test_retry_exhaustion_timeout_and_authentication_are_typed`. |
| T17 | `test_provider.test_unknown_usage_is_not_zero` and `test_decisions.test_usage_measurements_distinguish_accounting_strength`. |
| T18 | `test_runtime.test_independent_ready_judgments_share_no_answers`. |
| T19 | `test_runtime.test_inactive_branch_and_missing_completion_policy_are_unresolved`. |
| T20 | `test_runtime.test_concurrent_definitions_isolate_state_and_share_limits`. |
| T21 | `test_decisions.test_concurrent_calls_admit_at_most_one_final_attempt`. |
| T22 | `test_runtime.test_stale_inflight_answer_is_historical_not_accepted`. |
| T23 | `test_runtime.test_completion_requires_current_findings_before_and_after_policy`. |
| T24 | `test_policy.test_denied_authority_and_failed_acceptance_block_high_confidence`. |
| T25 | `test_policy.test_denied_authority_and_failed_acceptance_block_high_confidence`. |
| T26 | `test_policy.test_stale_source_after_authorization_blocks_dispatch` and `test_policy.test_final_mutation_freshness_check_follows_awaited_gates`. |
| T27 | `test_policy.test_lost_or_malformed_reply_reconciles_without_retry`. |
| T28 | `test_policy.test_inconclusive_reconciliation_stops_without_retry`. |
| T29 | `test_policy.test_post_dispatch_cancellation_preserves_unknown_outcome` and malformed-receipt reconciliation checks. |
| T30 | `test_policy.test_required_checkpoint_and_durable_intent_fail_closed`. |
| T31 | `test_investigation.test_expansion_rechecks_only_selection_and_preserves_conflict`. |
| T32 | `test_investigation.test_unchanged_expansion_stops_with_no_progress`. |
| T33 | `test_composition.test_scope_and_evidence_widening_fail_before_child_access`. |
| T34 | `test_composition.test_cycle_depth_and_count_limits_are_visible`. |
| T35 | `test_composition.test_parent_cancellation_reaches_child_work` and `test_composition.test_cancelled_child_effect_remains_unknown_in_parent_evidence`. |
| T36 | `test_composition.test_two_conflicting_children_share_one_slot_and_one_ledger`. |
| T37 | `test_composition.test_two_conflicting_children_share_one_slot_and_one_ledger` and `test_composition.test_unresolved_child_findings_keep_their_evidence`. |
| T38 | `test_planning.test_invented_tool_and_source_are_rejected_without_dispatch` and `test_planning.test_cycle_and_forbidden_mutation_are_rejected_without_dispatch`. |
| T39 | `test_inspection.test_hostile_failures_and_sink_errors_do_not_leak` and fixture-capture sanitization. |
| T40 | `test_evaluation.test_leakage_fails_closed_before_report` and `test_packages.test_evaluator_cases_never_enter_provider_state`. |
| T41 | `test_evaluation.test_public_decision_comparison_keeps_labels_out_and_groups_variants`. |
| T42 | `test_planning.test_unseen_objective_runs_generated_sequence_and_validates_result` and package reuse tests. |
| T43 | Fresh core and adapter-specific wheel installs and installed examples recorded above. |
| T44 | `test_decisions.test_evaluate_and_assess_record_provenance_without_an_agent`. |
| T45 | Native tool and node invocation tests in both optional integration modules. |
| T46 | `test_langchain_integration.test_forged_scope_and_provider_failure_remain_explicit` and `test_pydantic_ai_integration.test_scope_provider_failure_and_cancellation_remain_explicit`. |
| T47 | Optional-skip and required-rejection tests in both optional integration modules. |
| T48 | Current-action and current-output checkpoint tests in both optional integration modules. |
| T49 | `test_planning.test_failed_observation_causes_changed_bounded_proposal`. |
| T50 | `test_planning.test_invented_tool_and_source_are_rejected_without_dispatch` and `test_planning.test_fixed_arguments_cannot_be_overridden_by_planner_values`. |
| T51 | `test_planning.test_executing_specialist_is_dispatched_once`. |
| T52 | `test_planning.test_unchanged_plan_and_unaccepted_result_stop_explicitly` and bounded provider retry tests. |
| T53 | `test_planning.test_unseen_objective_runs_generated_sequence_and_validates_result`, `test_pydantic_ai_integration.test_fallback_response_does_not_claim_hidden_jev_usage`, and evaluation accounting tests. |
| T54 | Host cancellation tests in both optional integrations plus mutation freshness and uncertain-outcome policy tests. |
| T55 | Separate core, LangChain/LangGraph, and Pydantic AI wheel environments recorded above. |
| T56 | The direct-decision tests for all convenience operations, candidate edge cases, provenance, and usage. |
| T57 | The package test module, including two host bindings, collisions, versions, and evaluator isolation. |
| T58 | `test_compiler.test_partial_preview_names_missing_task_and_host_bindings` and permitted inspection-projection tests. |
| T59 | The fixture test module, including strict replay, incomplete evidence, and isolated mutation doubles. |
| T60 | The calibration test module, including frozen held-out configuration and shadow no-dispatch. |
| T61 | The capability catalog test module, including schema changes, scope, truncation, expansion, and MCP errors. |
| T62 | `test_planning.test_propose_select_filters_before_jev_and_handles_zero_survivors`. |
| T63 | The document collection test module, including truncated retrieval, Unicode duplicates, opposing sources, and stale versions. |
| T64 | `test_investigation.test_typed_clarification_allows_a_linked_fresh_run`. |
| T65 | The artifact test module, including exact failure, revision recomputation, semantic gating, and no-progress. |

## Bounded live evidence

Two sanitized run summaries record seven authorized synthetic requests on CPython 3.14.6 with TypeSafe SDK 0.7.1 and requested and returned model `jev-1.13.0`.
Choice, Noul, Score, a corrected two-stage dependency, and the public `Runtime` path passed through `TypeSafeProvider` and `DecisionClient`, with complete token, request, and question usage returned for each attempt.
The first run recorded four passing cases and one local `CompilerError` because the smoke script declared a dependency across separate client calls as though it were in one compiled definition.
The corrected run passed by importing the first returned model judgment as evidence for the second stage, which matches the framework's cross-call contract.
The first run's `git_revision` field is explicitly `unknown`.
The corrected run records base revision `a2599a9` plus the dirty JF-22 dependency and regression changes, so neither summary is mislabeled as evidence from the final commit.
The observed Choice confidence was 0.07, which is transport evidence rather than application reliability or a calibrated action threshold.

## Delivery levels and remaining gates

Levels A-C are supported by the contracts, the deterministic public-runtime scenarios, the complete offline matrix, clean installations, installed examples, and inspected distributions above.
Level D is supported only for the bounded TypeSafe SDK 0.7.1, `jev-1.13.0`, `TypeSafeProvider`, `DecisionClient`, and `Runtime` smoke described above.
Live LangChain, LangGraph, Pydantic AI, hybrid planner, fallback, consequential-effect, and other provider or model combinations remain pending.
Level E remains application-specific and requires the host owner to accept a frozen held-out policy and operational controls.
No package was published, deployed, released, or licensed, and no consequential real effect was attempted.
