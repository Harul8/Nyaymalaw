"""The atomic saved candidate is private and cannot author its own check clears."""
from __future__ import annotations

from dataclasses import replace

import pytest
from nm.adapters.store.file_store import FileMatterStore
from nm.core.brain_assessment import AssessmentService
from nm.core.brain_publication import PrivatePublicationService
from nm.core.brain_release import ReviewRefused
from nm.domain.budget import Budget
from nm.domain.loop import LoopLimits
from nm.ports.store import StaleWrite

from tests.test_final_checks_are_saved_and_charged_before_use import _setup

pytestmark = pytest.mark.class_a


def _ready(tmp_path):
    store, brain, outcome, review, _, finalizer = _setup(tmp_path)
    finalizer.prepare(outcome, review)
    assessor = AssessmentService(store=store, log=brain.log, session_current=lambda: True,
        supplement=finalizer.subjects, boundaries=finalizer.boundaries,
        current_tools_version=lambda: outcome.record.identity.tools_version,
        current_principles_version=lambda: outcome.record.identity.principles_version)
    assessment = assessor.assess(outcome, review, expected_version=store.load("mat_loop").version)
    return store, brain, outcome, review, finalizer, assessment, PrivatePublicationService(
        assessment=assessor, finalizer=finalizer)


def test_candidate_and_every_actual_receipt_land_in_one_cas_and_survive_restart(tmp_path):
    store, _, outcome, review, _, assessment, publication = _ready(tmp_path)
    old = store.load("mat_loop")
    result = publication.record(outcome, review, assessment,
                                original_message="Assess the notice requirement.")
    assert not result.client_ready and result.status == "private_withheld_candidate"
    assert result.matter_version == old.version + 1
    restarted = FileMatterStore(tmp_path, key="isolated-loop-key")
    actual = restarted.load("mat_loop")
    assert actual.loop_records[-1] == result.record
    stop = result.record.events[-1].payload
    assert len(stop["outputs"]) == 18 and len(stop["boundaries"]) == 6
    assert stop["client_ready"] is False and stop["released"] is False
    assert stop["candidate"]["elements"][0]["text"] == review.candidate_text
    assert any(row["assessed"] is None for row in stop["outputs"])
    assert actual.facts == old.facts and actual.threads == old.threads
    assert actual.turn_receipts == old.turn_receipts and not store.transcripts_for("mat_loop")
    assert actual.dependencies == old.dependencies  # No private graph supplants the public file.


def test_same_publication_retry_is_idempotent_and_keeps_unknowns(tmp_path):
    store, _, outcome, review, _, assessment, publication = _ready(tmp_path)
    first = publication.record(outcome, review, assessment,
                               original_message="Assess the notice requirement.")
    second = publication.record(outcome, review, assessment,
                                original_message="Assess the notice requirement.")
    assert second == first
    assert len([row for row in store.load("mat_loop").loop_records
                if row.identity.turn_id.endswith(":publication")]) == 1


@pytest.mark.parametrize("mutation", ["words", "check", "message"])
def test_a_caller_cannot_replace_the_checked_candidate_receipts_or_instruction(tmp_path, mutation):
    store, _, outcome, review, _, assessment, publication = _ready(tmp_path)
    message = "Assess the notice requirement."
    if mutation == "words":
        assessment = replace(assessment, candidate=replace(assessment.candidate,
            elements=(replace(assessment.candidate.elements[0],
                              text="Unchecked stronger advice."),)))
    elif mutation == "check":
        assessment = replace(assessment, outputs=tuple(replace(row, assessed=True)
                                                      for row in assessment.outputs))
    else:
        message = "A different instruction."
    old = store.load("mat_loop")
    with pytest.raises(ReviewRefused):
        publication.record(outcome, review, assessment, original_message=message)
    assert store.load("mat_loop") == old


def test_a_concurrent_transaction_prevents_the_candidate_and_receipts_together(tmp_path):
    store, _, outcome, review, _, assessment, publication = _ready(tmp_path)
    current = store.load("mat_loop")
    store.commit(replace(current, version=current.version + 1), expected_version=current.version)
    with pytest.raises(StaleWrite):
        publication.record(outcome, review, assessment,
                           original_message="Assess the notice requirement.")
    assert not any(row.identity.turn_id.endswith(":publication")
                   for row in store.load("mat_loop").loop_records)


def test_failure_at_the_atomic_store_boundary_leaves_no_half_publication(tmp_path):
    store, _, outcome, review, _, assessment, publication = _ready(tmp_path)
    before = store.load("mat_loop")
    original = store.commit

    def failed(matter, *, expected_version):
        if any(row.identity.turn_id.endswith(":publication") for row in matter.loop_records):
            raise OSError("Unavailable atomic write")
        return original(matter, expected_version=expected_version)

    store.commit = failed
    with pytest.raises(OSError):
        publication.record(outcome, review, assessment,
                           original_message="Assess the notice requirement.")
    assert store.load("mat_loop") == before


def test_session_end_before_publication_never_produces_a_normal_turn(tmp_path):
    store, _, outcome, review, finalizer, assessment, publication = _ready(tmp_path)
    finalizer.reader.session_current = lambda: False
    with pytest.raises(ReviewRefused, match="session"):
        publication.record(outcome, review, assessment,
                           original_message="Assess the notice requirement.")
    assert not store.load("mat_loop").turn_receipts


def test_actual_evaluation_publishes_receipts_atomically_before_returning_its_private_candidate(
        tmp_path):
    store, brain, _, _, finalizer, _, publication = _ready(tmp_path)
    brain.finalizer = finalizer
    brain.assessment = publication.assessment
    brain.publication = publication
    result = brain.evaluate(matter_id="mat_loop", turn_id="package-turn",
        message="Assess the notice requirement.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 10, 500))
    assert len(result.publications) == len(result.assessments) == 1
    saved = result.publications[0]
    assert saved.record == store.load("mat_loop").loop_records[-1]
    assert len(saved.record.events[-1].payload["outputs"]) == 18
    assert saved.record.events[-1].payload["candidate"]["elements"][0]["text"] == (
        result.assessments[0].candidate.elements[0].text)
    assert saved.status == "private_withheld_candidate" and not result.client_ready
    assert not store.load("mat_loop").turn_receipts and not store.transcripts_for("mat_loop")
    repeated = brain.evaluate(matter_id="mat_loop", turn_id="package-turn",
        message="Assess the notice requirement.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 10, 500))
    assert repeated.publications == result.publications
    assert len([row for row in store.load("mat_loop").loop_records
                if row.identity.turn_id.endswith(":publication")]) == 1
