"""Malformed captures and lost authority are not authored mistakes worth retrying."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date

import pytest

from nm.legal_brain.verify.brain_assessment import AssessmentService
from nm.legal_brain.verify.brain_finalization import FinalizationService, SavedCheckReader
from nm.legal_brain.verify.brain_release import ProposalBindingRefused, ReviewRefused, prepare_claims
from nm.legal_brain.orchestrate.loop_contracts import LoopEvent, LoopLimits, LoopRecord, StepKind, StopReason
from nm.shared.budget_contracts import Budget
from tests.test_claims_reach_the_independent_review_from_the_saved_loop import _case
from tests.test_document_words_reach_review_without_becoming_facts_or_law import (
    _case as document_case,
)

pytestmark = pytest.mark.class_a


def plant(store, outcome, mutate):
    """Rehash and persist an actual closed journal, not a mocked source verdict."""
    previous, events = outcome.record.identity.fingerprint, []
    for event in outcome.record.events:
        payload = deepcopy(event.payload)
        mutate(event.kind, payload)
        rebuilt = LoopEvent.create(event.sequence, event.kind, event.at, payload, previous)
        events.append(rebuilt)
        previous = rebuilt.fingerprint
    record = LoopRecord(outcome.record.identity, tuple(events))
    current = store.load(record.identity.matter_id)
    updated = replace(current, loop_records=tuple(
        record if row.identity == record.identity else row for row in current.loop_records),
        version=current.version + 1)
    store.commit(updated, expected_version=current.version)
    stop = record.events[-1].payload
    return replace(outcome, record=record, proposal=stop["proposal"])


def finalize(store, brain, outcome, *, document_current=None):
    reader = SavedCheckReader(store=store, log=brain.log, model=brain.model,
        session_current=lambda: True, cost_ceiling=lambda *_: 0.03,
        current_tools_version=lambda: brain.registry.version,
        current_principles_version=lambda: brain.principles.load().version,
        document_current=document_current)
    brain.finalizer = FinalizationService(reader=reader, today=lambda: date(2026, 9, 27),
                                          jurisdiction="Not established")
    brain.assessment = AssessmentService(store=store, log=brain.log,
        session_current=lambda: True, current_tools_version=reader.current_tools_version,
        current_principles_version=reader.current_principles_version,
        document_current=document_current)
    return reader


def evaluate(brain, outcome):
    return brain.evaluate(matter_id=outcome.record.identity.matter_id,
        turn_id=outcome.record.identity.turn_id, message="Assess the notice requirement.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 10, 500))


@pytest.mark.parametrize("authored", ["empty", "duplicate"])
@pytest.mark.parametrize("capture", ["missing_field", "foreign_locator"])
def test_real_malformed_captures_precede_every_repairable_authored_population(
        tmp_path, authored, capture):
    store, brain, outcome, judge, claim = _case(tmp_path)
    def mutate(kind, payload):
        if kind is StepKind.TOOL_RETURNED and payload["receipt"]["kind"] == "source":
            found = payload["receipt"]["data"]["findings"][0]
            if capture == "missing_field":
                del found["span"]
            else:
                found["locator"] = "a-foreign-unreceipted-source"
        if kind is StepKind.STOP:
            payload["proposal"]["claims"] = [] if authored == "empty" else [claim, claim]
    altered = plant(store, outcome, mutate)
    assert brain.log.read(altered.record.identity) == altered.record
    with pytest.raises(ReviewRefused) as caught:
        prepare_claims(altered, store.load("mat_loop"))
    assert not isinstance(caught.value, ProposalBindingRefused)
    finalize(store, brain, altered)
    calls = brain.model.tool_call.call_count
    result = evaluate(brain, altered)
    assert result.stop == "review_refused" and len(result.attempts) == 1
    assert result.budget.spend.discarded_results == 0
    assert brain.model.tool_call.call_count == calls and not judge.prompts
    assert not result.client_ready and not store.load("mat_loop").turn_receipts


@pytest.mark.parametrize("lost", ["session", "generation", "principles"])
def test_actual_final_reader_checks_runtime_owners_before_binding_can_purchase_a_retry(
        tmp_path, lost):
    store, brain, outcome, judge, _ = _case(tmp_path, claims=[])
    reader = finalize(store, brain, outcome)
    if lost == "session":
        reader.session_current = lambda: False
    elif lost == "generation":
        reader.current_tools_version = lambda: "actual-generation-no-longer-current"
    else:
        reader.current_principles_version = lambda: "actual-principles-no-longer-current"
    calls = brain.model.tool_call.call_count
    result = evaluate(brain, outcome)
    assert result.stop == "review_refused" and len(result.attempts) == 1
    assert brain.model.tool_call.call_count == calls and not judge.prompts
    assert result.budget.spend.discarded_results == 0 and not result.assessments


@pytest.mark.parametrize("capture", ["digest", "request"])
def test_malformed_actual_document_capture_is_not_a_missing_authored_quote(tmp_path, capture):
    store, brain, outcome, judge, _, _, current = document_case(tmp_path)
    def mutate(kind, payload):
        if kind is StepKind.TOOL_RETURNED and payload["receipt"]["tool"] == "quote_matter":
            receipt = payload["receipt"]
            if capture == "digest":
                receipt["data"]["source"]["source_sha256"] = "not-a-digest"
            else:
                receipt["receipt"]["snapshot"] = "a-different-captured-read"
        if kind is StepKind.STOP:
            payload["proposal"]["claims"] = []
    altered = plant(store, outcome, mutate)
    reader = finalize(store, brain, altered, document_current=current)
    for check in (lambda: brain.review(altered), lambda: reader.current(altered)):
        with pytest.raises(ReviewRefused) as caught:
            check()
        assert not isinstance(caught.value, ProposalBindingRefused)
    assert not judge.prompts and not store.load("mat_one").turn_receipts


@pytest.mark.parametrize("admission", ["missing_reader", "negative_reader", "revoked_document"])
def test_all_captured_documents_retain_real_admission_before_bad_author_references(
        tmp_path, admission):
    store, brain, outcome, judge, documents, original, current = document_case(tmp_path)
    def mutate(kind, payload):
        if kind is StepKind.STOP:
            payload["proposal"]["claims"][0]["sources"][0]["quote"] = "Invented source words."
    altered = plant(store, outcome, mutate)
    if admission == "missing_reader":
        current = None
    elif admission == "negative_reader":
        def current(*_):
            return False
    else:
        documents.revoke("mat_one", "adv_one", store.load("mat_one").version, original)
    brain.reviewer.document_current = current
    reader = finalize(store, brain, altered, document_current=current)
    for check in (lambda: brain.review(altered), lambda: reader.current(altered)):
        with pytest.raises(ReviewRefused) as caught:
            check()
        assert not isinstance(caught.value, ProposalBindingRefused)
    assert not judge.prompts and not store.load("mat_one").facts


def test_a_changed_terminal_reason_is_capture_failure_not_an_authored_reference_failure(tmp_path):
    store, brain, outcome, judge, _ = _case(tmp_path, claims=[])
    altered = plant(store, outcome, lambda kind, payload: payload.update(
        reason=StopReason.QUESTION.value) if kind is StepKind.STOP else None)
    with pytest.raises(ReviewRefused) as caught:
        brain.review(altered)
    assert not isinstance(caught.value, ProposalBindingRefused) and not judge.prompts


def test_unchanged_admitted_document_still_reaches_distinct_review_without_fact_promotion(tmp_path):
    store, brain, outcome, judge, _, _, current = document_case(tmp_path)
    reader = finalize(store, brain, outcome, document_current=current)
    assert reader.current(outcome).id == "mat_one"
    reviewed = brain.review(outcome)
    assert reviewed.result.released and len(judge.prompts) == 1
    assert not reviewed.client_ready and not store.load("mat_one").facts
