import unittest

from jev_frame import (
    NO_FIT_KEY,
    AcceptanceEvidence,
    Candidate,
    CandidateOutcome,
    CandidateSelectionError,
    CandidateSet,
    Coverage,
    DefinitionError,
    Derivation,
    EvidenceScopeError,
    EvidenceStore,
    ExecutionReference,
    ExecutionState,
    ModelJudgment,
    NoulAnswer,
    Observation,
    SourceBindingError,
    SourceField,
    SourceSpan,
    StableSerializationError,
    StaleEvidenceError,
    ViewCapacityError,
    bind_source,
    candidate_snapshot_digest,
    canonical_digest,
    decision_fingerprint,
    select_candidate,
)


def observation(
    evidence_id: str,
    value: object,
    *,
    scope: str = "alpha",
    expires_at: float | None = None,
    dependencies: tuple[str, ...] = (),
    conflicts_with: tuple[str, ...] = (),
) -> Observation:
    return Observation(
        id=evidence_id,
        value=value,
        source_id="fixture",
        scope=scope,
        observed_at=10.0,
        expires_at=expires_at,
        dependencies=dependencies,
        conflicts_with=conflicts_with,
    )


def candidates(
    *items: Candidate,
    coverage: Coverage = Coverage.COMPLETE,
    scope: str = "alpha",
    failure_reason: str | None = None,
) -> CandidateSet:
    return CandidateSet(
        id="documents",
        version="1.0.0",
        candidates=items,
        coverage=coverage,
        scope=scope,
        failure_reason=failure_reason,
    )


class CandidateStateTests(unittest.TestCase):
    def test_duplicate_labels_retain_identity_and_revision(self) -> None:
        snapshot = candidates(
            Candidate("a", {"id": 1}, "Same label", "catalog", "v1"),
            Candidate("b", {"id": 2}, "Same label", "catalog", "v2"),
        )

        selected = select_candidate(snapshot, "b")

        assert selected.candidate is not None
        self.assertEqual(selected.candidate.key, "b")
        self.assertEqual(selected.candidate.source_version, "v2")
        with self.assertRaises(CandidateSelectionError):
            select_candidate(snapshot, "missing")

    def test_coverage_states_and_no_fit_remain_distinct(self) -> None:
        complete = candidates()
        truncated = candidates(coverage=Coverage.TRUNCATED)
        failed = candidates(coverage=Coverage.FAILED, failure_reason="offline")
        singleton = candidates(Candidate("only", 1, "Only item", "catalog"))

        self.assertIs(complete.coverage, Coverage.COMPLETE)
        self.assertIs(truncated.coverage, Coverage.TRUNCATED)
        self.assertEqual(failed.failure_reason, "offline")
        no_fit = select_candidate(singleton, NO_FIT_KEY)
        self.assertIs(no_fit.outcome, CandidateOutcome.NO_FIT)
        self.assertEqual(no_fit.coverage, Coverage.COMPLETE.value)

    def test_no_fit_key_cannot_be_a_candidate(self) -> None:
        with self.assertRaises(DefinitionError):
            candidates(Candidate(NO_FIT_KEY, 1, "Collision", "catalog"))

    def test_order_description_policy_and_model_change_fingerprint(self) -> None:
        first = Candidate("a", 1, "First", "catalog", "v1")
        second = Candidate("b", 2, "Second", "catalog", "v1")
        evidence = (observation("source", {"text": "fact"}),)

        def fingerprint(
            snapshot: CandidateSet, policy: str = "1.0.0", model: str = "jev-1"
        ) -> str:
            return decision_fingerprint(
                semantic_version="1.0.0",
                policy_version=policy,
                model_identity=model,
                projection_version="1.0.0",
                compiler_version="1.0.0",
                scope="alpha",
                evidence=evidence,
                candidate_sets=(snapshot,),
            )

        baseline = fingerprint(candidates(first, second))
        self.assertNotEqual(baseline, fingerprint(candidates(second, first)))
        self.assertNotEqual(
            baseline,
            fingerprint(
                candidates(Candidate("a", 1, "Changed", "catalog", "v1"), second)
            ),
        )
        self.assertNotEqual(
            baseline, fingerprint(candidates(first, second), policy="2.0.0")
        )
        self.assertNotEqual(
            baseline, fingerprint(candidates(first, second), model="jev-2")
        )

    def test_canonical_digest_rejects_unstable_values(self) -> None:
        self.assertEqual(
            canonical_digest({"b": 2, "a": 1}), canonical_digest({"a": 1, "b": 2})
        )
        with self.assertRaises(StableSerializationError):
            canonical_digest({1, 2})


class EvidenceStateTests(unittest.TestCase):
    def test_invalidation_is_transitive_and_selective(self) -> None:
        store = EvidenceStore(clock=lambda: 10.0)
        source = store.add(observation("source", "old"))
        derived = store.add(
            Derivation(
                id="derived",
                value="normalized",
                source_id="normalize",
                scope="alpha",
                observed_at=10.0,
                dependencies=(source.id,),
                transformation_id="normalize",
                transformation_version="1.0.0",
            )
        )
        judgment = store.add(
            ModelJudgment(
                id="judgment",
                value=NoulAnswer(0.9),
                source_id="jev",
                scope="alpha",
                observed_at=10.0,
                dependencies=(derived.id,),
                judgment_id="supported",
                judgment_version="1.0.0",
                question_semantics="Is the statement supported?",
                subjects=("statement",),
                answer=NoulAnswer(0.9),
                input_fingerprint="fingerprint",
                requested_model="jev-1",
                returned_model="jev-1.2",
            )
        )
        unrelated = store.add(observation("unrelated", "still current"))

        replacement = store.add(
            Observation(
                id="source-v2",
                value="new",
                source_id="fixture",
                scope="alpha",
                observed_at=11.0,
                supersedes=(source.id,),
            )
        )

        self.assertFalse(store.is_current(source.id))
        self.assertFalse(store.is_current(derived.id))
        self.assertFalse(store.is_current(judgment.id))
        self.assertTrue(store.is_current(unrelated.id))
        self.assertTrue(store.is_current(replacement.id))

    def test_expiry_and_scope_are_checked_at_use_time(self) -> None:
        now = [10.0]
        store = EvidenceStore(clock=lambda: now[0])
        store.add(observation("expiring", "value", expires_at=11.0))
        store.add(observation("private", "secret", scope="beta"))

        self.assertEqual(store.project(("expiring",), scope="alpha")[0].id, "expiring")
        now[0] = 11.0
        with self.assertRaises(StaleEvidenceError):
            store.project(("expiring",), scope="alpha")
        with self.assertRaises(EvidenceScopeError):
            store.project(("private",), scope="alpha")

    def test_conflicts_are_preserved_or_capacity_fails(self) -> None:
        store = EvidenceStore(clock=lambda: 10.0)
        store.add(observation("left", "yes"))
        store.add(
            Observation(
                id="right",
                value="no",
                source_id="fixture-2",
                scope="alpha",
                observed_at=11.0,
                supersedes=("left",),
                conflicts_with=("left",),
            )
        )

        view = store.project(("right",), scope="alpha")

        self.assertEqual({record.id for record in view}, {"left", "right"})
        with self.assertRaises(ViewCapacityError):
            store.project(("right",), scope="alpha", max_records=1)

    def test_exact_unicode_spans_and_fields_keep_source_identity(self) -> None:
        text = observation("text", "écho écho")
        structured = observation(
            "structured", {"items": [{"quote": "same"}, {"quote": "same"}]}
        )

        second = bind_source(text, SourceSpan(5, 9))
        field = bind_source(structured, SourceField(("items", 1, "quote")))

        self.assertEqual(second.value, "écho")
        self.assertEqual(second.evidence_id, "text")
        self.assertEqual(field.value, "same")
        assert isinstance(field.locator, SourceField)
        self.assertEqual(field.locator.path, ("items", 1, "quote"))
        with self.assertRaises(SourceBindingError):
            bind_source(text, SourceSpan(5, 99))

    def test_completed_effect_is_historical_but_later_reasoning_invalidates(
        self,
    ) -> None:
        store = EvidenceStore(clock=lambda: 10.0)
        source = store.add(observation("source", "accepted"))
        effect = store.add(
            ExecutionReference(
                id="effect",
                value={"receipt": "r1"},
                source_id="fake-service",
                scope="alpha",
                observed_at=10.0,
                dependencies=(source.id,),
                operation_id="op-1",
                state=ExecutionState.SUCCEEDED,
            )
        )
        later = store.add(
            AcceptanceEvidence(
                id="later",
                value="accepted",
                source_id="policy",
                scope="alpha",
                observed_at=10.0,
                dependencies=(effect.id,),
                judgment_ref="effect",
                policy_id="post-effect",
                policy_version="1.0.0",
            )
        )

        store.invalidate(source.id)

        self.assertTrue(store.is_current(effect.id))
        self.assertFalse(store.is_current(later.id))

    def test_candidate_snapshot_digest_covers_typed_value(self) -> None:
        left = candidates(Candidate("a", {"value": 1}, "Same", "catalog", "v1"))
        right = candidates(Candidate("a", {"value": 2}, "Same", "catalog", "v1"))

        self.assertNotEqual(
            candidate_snapshot_digest(left), candidate_snapshot_digest(right)
        )


if __name__ == "__main__":
    unittest.main()
