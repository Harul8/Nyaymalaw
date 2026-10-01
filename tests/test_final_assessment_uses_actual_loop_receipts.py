"""P51 final assembly cannot certify subjects that were never assessed."""
from __future__ import annotations

from dataclasses import replace

import pytest

from nm.Archives.legal_brain.verify.brain_assessment import (
    AssessmentRefused,
    AssessmentService,
    captured_retrievals,
)
from nm.Archives.legal_brain.verify.brain_release import IndependentReview, prepare_claims
from nm.Archives.legal_brain.retrieve.evidence_port import Coverage
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopEvent, LoopRecord, StepKind
from nm.Archives.legal_brain.verify.output_checks import BoundarySubjects, OutputSubjects
from nm.Archives.legal_brain.verify.verifier import VerifiedRelease, release_verified
from tests.test_claims_reach_the_independent_review_from_the_saved_loop import _case
from tests.test_independent_claim_verifier import response

pytestmark = pytest.mark.class_a


def _service(store, brain, outcome, **kwargs):
    return AssessmentService(
        store=store, log=brain.log, session_current=lambda: True,
        current_tools_version=lambda: outcome.record.identity.tools_version,
        current_principles_version=lambda: outcome.record.identity.principles_version,
        **kwargs)


def _receipts(assessment):
    return {row.gate_id: row for row in (*assessment.outputs, *assessment.boundaries)}


def test_actual_saved_review_assembles_exact_candidate_without_invented_checks(tmp_path):
    store, brain, outcome, judge, original = _case(tmp_path)
    review = brain.review(outcome)
    calls = len(judge.prompts)
    assessment = _service(store, brain, outcome).assess(outcome, review)
    assert len(judge.prompts) == calls
    assert not assessment.client_ready and not assessment.checks_complete
    assert len(assessment.outputs) == 18 and len(assessment.boundaries) == 6
    assert assessment.candidate.elements[0].text == original["text"]
    assert not assessment.withheld and not assessment.partial
    checked = _receipts(assessment)
    for id in ("G-GROUND", "G-QUOTE", "G-ATTRIB", "G-INFORCE", "G-BINDING", "G-DATE",
               "G-NOTHELD", "G-HELDNOTFOUND", "G-NOTASSESSED"):
        assert checked[id].assessed is True, (id, checked[id])
    for id in ("G-CONSISTENT", "G-CONSERVE", "G-CASCADE", "G-CURRENCY", "G-STALE",
               "G-READ", "G-MODEL", "G-COVERAGE", "G-COMPETENCE",
               "G-EMERGENCY", "G-CONFLICT", "G-SCOPE", "G-CAPACITY", "G-DUTY", "G-UNSCREENED"):
        assert checked[id].assessed is None, (id, checked[id])
    assert assessment.matter_version == store.load("mat_loop").version
    assert not store.load("mat_loop").turn_receipts


def test_journal_appends_are_not_case_corrections_and_admitted_commit_version_is_compared(tmp_path):
    store, brain, outcome, _, _ = _case(tmp_path)
    review = brain.review(outcome)
    current = store.load("mat_loop").version
    assert current > outcome.record.identity.matter_version
    service = _service(store, brain, outcome)
    checked = service.assess(outcome, review, expected_version=current)
    assert _receipts(checked)["G-STALE"].assessed is True
    stale = service.assess(outcome, review, expected_version=current - 1)
    assert _receipts(stale)["G-STALE"].assessed is False
    assert not stale.client_ready


@pytest.mark.parametrize("mutation", ["verdict", "budget", "release", "extra_words"])
def test_authored_review_cannot_replace_actual_sealed_review(tmp_path, mutation):
    store, brain, outcome, _, _ = _case(tmp_path)
    review = brain.review(outcome)
    if mutation == "verdict":
        record = replace(review.records[0], reason="Caller claims approval.")
        review = replace(review, records=(record,))
    elif mutation == "budget":
        review = replace(review, budget=replace(review.budget, max_cost_usd=100))
    elif mutation == "release":
        review = replace(review, result=VerifiedRelease((), ()))
    else:
        package = replace(review.packages[0], claim="An extra unchecked final conclusion.")
        review = replace(review, packages=(package,))
    with pytest.raises(AssessmentRefused):
        _service(store, brain, outcome).assess(outcome, review)


def test_known_false_independent_inference_is_withheld_not_private_released(tmp_path):
    store, brain, outcome, _, _ = _case(tmp_path, judged=response(inference=False))
    review = brain.review(outcome)
    assessment = _service(store, brain, outcome).assess(outcome, review)
    assert assessment.candidate is None and assessment.withheld
    assert not assessment.checks_complete and not assessment.client_ready
    assert _receipts(assessment)["G-GROUND"].assessed is None


def test_partial_release_contains_only_dependency_closed_checked_paragraphs(tmp_path):
    _, _, _, _, original = _case(tmp_path / "seed")
    first = {**original, "id": "p1"}
    second = {**original, "id": "p2", "text": "The known contradiction is unresolved."}
    store, brain, outcome, judge, _ = _case(tmp_path / "partial", claims=[first, second])
    actual = judge.structured
    count = 0

    def judge_once(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            judge._structured_responses["claim_verification"] = response(inference=False)
        return actual(*args, **kwargs)

    judge.structured = judge_once
    review = brain.review(outcome)
    assessment = _service(store, brain, outcome).assess(outcome, review)
    assert assessment.partial
    assert tuple(row.text for row in assessment.candidate.elements) == (first["text"],)
    assert tuple(row[0] for row in assessment.withheld) == ("p2",)
    assert not assessment.client_ready


@pytest.mark.parametrize("generation", ["source", "principles"])
def test_current_generation_movement_refuses_old_candidate(tmp_path, generation):
    store, brain, outcome, _, _ = _case(tmp_path)
    review = brain.review(outcome)
    service = _service(store, brain, outcome)
    if generation == "source":
        service.current_tools_version = lambda: "new-source-generation"
    else:
        service.current_principles_version = lambda: "new-principles-generation"
    with pytest.raises(AssessmentRefused, match="generation changed"):
        service.assess(outcome, review)


def test_missing_generation_observer_does_not_become_a_pass(tmp_path):
    store, brain, outcome, _, _ = _case(tmp_path)
    review = brain.review(outcome)
    service = AssessmentService(store=store, log=brain.log, session_current=lambda: True)
    assessment = service.assess(outcome, review)
    assert set(assessment.missing_receipts) == {
        "current tool/source generation", "current principles generation"}
    assert not assessment.checks_complete and not assessment.client_ready


def test_supplement_cannot_replace_actual_final_words_or_source_population(tmp_path):
    store, brain, outcome, _, _ = _case(tmp_path)
    review = brain.review(outcome)
    service = _service(store, brain, outcome,
                       supplement=lambda *_: OutputSubjects(retrieved=()))
    with pytest.raises(AssessmentRefused, match="cannot replace"):
        service.assess(outcome, review)


def test_a_new_case_correction_or_session_end_invalidates_the_assessment(tmp_path):
    store, brain, outcome, _, _ = _case(tmp_path)
    review = brain.review(outcome)
    service = _service(store, brain, outcome)
    service.session_current = lambda: False
    with pytest.raises(AssessmentRefused, match="session"):
        service.assess(outcome, review)
    service.session_current = lambda: True
    saved = store.load("mat_loop")
    store.commit(replace(saved, facts=(replace(saved.facts[0], statement="Corrected account."),),
                         version=saved.version + 1), expected_version=saved.version)
    with pytest.raises(AssessmentRefused, match="changed"):
        service.assess(outcome, review)


def test_change_during_a_real_boundary_read_is_not_recorded_as_final_current_proof(tmp_path):
    store, brain, outcome, _, _ = _case(tmp_path)
    review = brain.review(outcome)

    def change(matter, _outcome):
        store.commit(replace(matter, version=matter.version + 1), expected_version=matter.version)
        return BoundarySubjects()

    service = _service(store, brain, outcome, boundaries=change)
    with pytest.raises(AssessmentRefused, match="changed while"):
        service.assess(outcome, review)


def test_a_primary_read_must_correlate_to_its_actual_dispatch_and_exact_capture(tmp_path):
    _, _, outcome, _, _ = _case(tmp_path)
    changed = []
    for event in outcome.record.events:
        payload = event.payload
        if event.kind is StepKind.TOOL_RETURNED and payload["receipt"]["kind"] == "source":
            finding = payload["receipt"]["receipt"]["primary_reads"][0]["findings"][0]
            finding["span"] = "Altered source."
        previous = changed[-1].fingerprint if changed else outcome.record.identity.fingerprint
        changed.append(LoopEvent.create(event.sequence, event.kind, event.at, payload, previous))
    forged = replace(outcome, record=LoopRecord(outcome.record.identity, tuple(changed)))
    with pytest.raises(AssessmentRefused, match="source capture"):
        captured_retrievals(forged)


def test_missing_judge_receipt_is_explicitly_withheld_without_dispatching_one(tmp_path):
    store, brain, outcome, judge, _ = _case(tmp_path)
    packages = prepare_claims(outcome, store.load("mat_loop"))
    review = IndependentReview(packages, (), release_verified(packages, ()), outcome.budget)
    assessment = _service(store, brain, outcome).assess(outcome, review)
    assert not judge.prompts
    assert assessment.candidate is None
    assert assessment.withheld == (("p1", "Independent verification was not recorded"),)
    assert not assessment.client_ready


def test_preflight_refusal_with_no_paid_review_is_retained_as_a_real_withheld_receipt(tmp_path):
    _, _, _, _, original = _case(tmp_path / "seed")
    store, brain, outcome, judge, _ = _case(tmp_path / "missing", claims=[{
        **original, "sources": []}])
    review = brain.review(outcome)
    assessment = _service(store, brain, outcome).assess(outcome, review)
    assert not judge.prompts and assessment.withheld and assessment.candidate is None
    assert review.budget.spend.cost_usd == outcome.budget.spend.cost_usd


@pytest.mark.parametrize("coverage", [Coverage.NOT_HELD, Coverage.HELD_NOT_FOUND,
                                      Coverage.NOT_ASSESSED, Coverage.SEARCHED_NO_MATCH])
def test_actual_primary_coverage_states_survive_the_saved_receipt_decoder(tmp_path, coverage):
    _, _, outcome, _, _ = _case(tmp_path)
    changed = []
    for event in outcome.record.events:
        payload = event.payload
        if event.kind is StepKind.TOOL_RETURNED and payload["receipt"]["kind"] == "source":
            envelope = payload["receipt"]
            envelope["data"] = {}
            envelope["outcome"] = "failed" if coverage is Coverage.NOT_ASSESSED else "no_results"
            envelope["availability"] = ("unavailable" if coverage is Coverage.NOT_ASSESSED
                                         else "partial")
            envelope["assessment"] = "not_assessed"
            envelope["reason"] = "Actual named read boundary."
            envelope["receipt"]["locators"] = []
            read = envelope["receipt"]["primary_reads"][0]
            read.update(coverage=coverage.value, findings=[], missing="Actual named read boundary.")
        previous = changed[-1].fingerprint if changed else outcome.record.identity.fingerprint
        changed.append(LoopEvent.create(event.sequence, event.kind, event.at, payload, previous))
    current = replace(outcome, record=LoopRecord(outcome.record.identity, tuple(changed)))
    results, needs = captured_retrievals(current)
    assert results[0].coverage is coverage and not results[0].findings
    assert needs and needs[0].governing_date.isoformat() == "2026-01-01"


def test_observer_generation_change_during_final_checks_invalidates_the_assessment(tmp_path):
    store, brain, outcome, _, _ = _case(tmp_path)
    review = brain.review(outcome)
    generation = outcome.record.identity.tools_version

    def change(*_):
        nonlocal generation
        generation = "new-source-generation"
        return OutputSubjects()

    service = _service(store, brain, outcome, supplement=change)
    service.current_tools_version = lambda: generation
    with pytest.raises(AssessmentRefused, match="changed during"):
        service.assess(outcome, review)


def test_private_assessment_cannot_have_an_empty_check_population(tmp_path):
    store, brain, outcome, _, _ = _case(tmp_path)
    assessment = _service(store, brain, outcome).assess(outcome, brain.review(outcome))
    with pytest.raises(ValueError, match="complete distinct"):
        replace(assessment, outputs=(), boundaries=())
    with pytest.raises(ValueError, match="positive matter version"):
        replace(assessment, matter_version=True)
