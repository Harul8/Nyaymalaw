"""Dispute coverage can exclude neutral account without erasing its purpose.

Scope and issue judgments are independently authored offline. These tests prove
that the existing owner admits their exact dispositions, checks representation
dependencies and preserves valid decisions within its correction bound. They do
not establish that the pinned model makes the scoped semantic judgment correctly.
"""
from __future__ import annotations

from copy import deepcopy

from nm.brain.dispute_verification import verify_disputes
from tests.brain_reader_fixture import fixture_coverage, fixture_disposition
from tests.test_brain_dispute_conflict_review_mechanics import (
    Model,
    candidate,
    decision,
    treatments,
)

SCOPE = {"requests": [{"request_index": 0, "material_purposes": ["account_contribution"]}]}
NEUTRAL = "Our client delivered the original inventory to the appointed examiner on 8 June."
ADVERSE = "The warehouse operator refused to return the entrusted equipment."


def assessment(payload, *, state, dispositions):
    """Each source's account purpose and scoped disposition are explicit choices."""
    return fixture_coverage(
        payload, state=state,
        source_decisions={identity: "account" for identity in payload["coverage_source_ids"]},
        dispositions=[fixture_disposition(payload, identity, status=status,
                                          candidate_ids=selected)
                      for identity, status, selected in dispositions],
        reason="The fixture owner separately assesses contestable issues in dispute-stage scope.")


def checked(model, *, latest, candidates=()):
    source_rows = treatments((), latest)
    before = deepcopy(source_rows)
    audit, coverage, status, disagreements = [], {}, {}, []
    retained = verify_disputes(
        model, candidates=candidates, earlier=(), latest=latest, active_disputes=(),
        source_treatments=source_rows, review_scope=deepcopy(SCOPE), audit=audit,
        coverage=coverage, review_status=status, source_disagreements=disagreements)
    assert source_rows == before
    assert all(row["content_role"] == "reported_matter_account" for row in source_rows.values())
    assert all(row["content_purpose"] == "account" for row in coverage["source_checks"])
    assert disagreements == []
    return retained, audit, coverage, status


def assert_original_account(coverage, identity, words, *, disposition):
    check, = [row for row in coverage["source_checks"] if row["source_id"] == identity]
    assert check["content_purpose"] == "account"
    assert check["quoted"] == words
    assert [(row["start"], row["end"], row["quoted"])
            for row in check["substantive_spans"]] == [(0, len(words), words)]
    row, = [row for row in coverage["dispositions"] if row["source_id"] == identity]
    assert row["status"] == disposition
    assert row["quoted"] == words
    assert row["start"] == 0 and row["end"] == len(words)
    return row


def test_neutral_account_allows_checked_empty_complete_dispute_scope_in_one_call():
    def judge(payload):
        assert payload["candidates"] == []
        assert payload["coverage_candidate_ids"] == payload["coverage_record_ids"] == []
        return {"verdicts": [], "coverage": assessment(payload, state="complete", dispositions=[
            ("L1", "outside_scope", []),
        ])}

    model = Model(judge)

    retained, audit, coverage, status = checked(model, latest=NEUTRAL)

    assert retained == () and audit == []
    assert coverage["state"] == "complete" and coverage["missing_source_ids"] == []
    row = assert_original_account(coverage, "L1", NEUTRAL, disposition="outside_scope")
    assert row["candidate_ids"] == row["record_ids"] == []
    assert status["state"] == "checked" and status["checked_items"] == 0
    assert len(model.calls) == 1 and model.claims == []


def test_rejected_neutral_dispute_candidate_does_not_make_scoped_coverage_incomplete():
    proposed = candidate(NEUTRAL)

    def judge(payload):
        return {"verdicts": [decision(
            "C1", "supporting_premise", accept=False, source="L1", words=NEUTRAL)],
            "coverage": assessment(payload, state="complete", dispositions=[
                ("L1", "outside_scope", []),
            ])}

    model = Model(judge)

    retained, audit, coverage, status = checked(model, latest=NEUTRAL, candidates=(proposed,))

    assert retained == () and audit[0]["verdict"] == "reject"
    assert audit[0]["account_check"]["supported"] is True
    assert coverage["state"] == "complete" and coverage["missing_source_ids"] == []
    assert_original_account(coverage, "L1", NEUTRAL, disposition="outside_scope")
    assert status["rejected_items"] == 1 and status["unread_items"] == 0
    assert len(model.calls) == 1 and model.claims == []


def test_neutral_account_and_independently_adverse_issue_have_separate_scoped_dispositions():
    proposed = candidate(ADVERSE)

    def judge(payload):
        return {"verdicts": [decision(
            "C1", "independent_dispute", accept=True, source="L2", words=ADVERSE)],
            "coverage": assessment(payload, state="complete", dispositions=[
                ("L1", "outside_scope", []), ("L2", "represented", ["C1"]),
            ])}

    model = Model(judge)

    retained, audit, coverage, status = checked(
        model, latest=NEUTRAL + " " + ADVERSE, candidates=(proposed,))

    assert retained == (proposed,) and audit[0]["verdict"] == "accept"
    assert coverage["state"] == "complete" and coverage["missing_source_ids"] == []
    assert_original_account(coverage, "L1", NEUTRAL, disposition="outside_scope")
    represented = assert_original_account(coverage, "L2", ADVERSE, disposition="represented")
    assert represented["candidate_ids"] == ["C1"]
    assert status["accepted_items"] == 1
    assert len(model.calls) == 1 and model.claims == []


def test_empty_candidates_cannot_hide_actual_missing_conflict_behind_neutral_outside_scope():
    def judge(payload):
        return {"verdicts": [], "coverage": assessment(payload, state="partial", dispositions=[
            ("L1", "outside_scope", []), ("L2", "missing", []),
        ])}

    model = Model(judge)

    retained, audit, coverage, status = checked(model, latest=NEUTRAL + " " + ADVERSE)

    assert retained == () and audit == []
    assert coverage["state"] == "partial" and coverage["missing_source_ids"] == ["L2"]
    assert_original_account(coverage, "L1", NEUTRAL, disposition="outside_scope")
    assert_original_account(coverage, "L2", ADVERSE, disposition="missing")
    assert coverage["missing_sources"][0]["quoted"] == ADVERSE
    assert status["unread_items"] == 0
    assert len(model.calls) == 1 and model.claims == []


def test_rejected_neutral_candidate_cannot_represent_an_actual_missing_issue():
    proposed = candidate(NEUTRAL)

    def judge(payload):
        return {"verdicts": [decision(
            "C1", "supporting_premise", accept=False, source="L1", words=NEUTRAL)],
            "coverage": assessment(payload, state="complete", dispositions=[
                ("L1", "outside_scope", []), ("L2", "represented", ["C1"]),
            ])}

    def correction(payload):
        assert payload["candidates"] == []
        assert payload["pending_review_keys"] == ["$coverage"]
        assert payload["retained_candidate_context"][0]["decision"]["verdict"] == "reject"
        assert "candidate not actually admitted" in payload["coverage_validation_issue"]
        return {"verdicts": [], "coverage": assessment(payload, state="partial", dispositions=[
            ("L1", "outside_scope", []), ("L2", "missing", []),
        ])}

    model = Model(judge, correction)

    retained, audit, coverage, status = checked(
        model, latest=NEUTRAL + " " + ADVERSE, candidates=(proposed,))

    assert retained == () and audit[0]["verdict"] == "reject"
    assert coverage["state"] == "partial" and coverage["missing_source_ids"] == ["L2"]
    assert_original_account(coverage, "L1", NEUTRAL, disposition="outside_scope")
    assert_original_account(coverage, "L2", ADVERSE, disposition="missing")
    assert status["unread_items"] == 0
    assert len(model.calls) == 2 and model.claims == ["verify_disputes:correction"]


def test_coverage_only_repair_keeps_independently_accepted_adverse_peer_and_neutral_rejection():
    neutral, adverse = candidate(NEUTRAL), candidate(ADVERSE)

    def judge(payload):
        return {"verdicts": [
            decision("C1", "supporting_premise", accept=False, source="L1", words=NEUTRAL),
            decision("C2", "independent_dispute", accept=True, source="L2", words=ADVERSE),
        ], "coverage": assessment(payload, state="complete", dispositions=[
            ("L1", "outside_scope", []), ("L2", "represented", ["C1"]),
        ])}

    def correction(payload):
        assert payload["candidates"] == []
        assert payload["pending_review_keys"] == ["$coverage"]
        assert [(row["candidate_id"], row["decision"]["verdict"])
                for row in payload["retained_candidate_context"]] == [
                    ("C1", "reject"), ("C2", "accept")]
        return {"verdicts": [], "coverage": assessment(payload, state="complete", dispositions=[
            ("L1", "outside_scope", []), ("L2", "represented", ["C2"]),
        ])}

    model = Model(judge, correction)

    retained, audit, coverage, status = checked(
        model, latest=NEUTRAL + " " + ADVERSE, candidates=(neutral, adverse))

    assert retained == (adverse,) and [row["verdict"] for row in audit] == ["reject", "accept"]
    assert coverage["state"] == "complete" and coverage["missing_source_ids"] == []
    assert_original_account(coverage, "L1", NEUTRAL, disposition="outside_scope")
    represented = assert_original_account(coverage, "L2", ADVERSE, disposition="represented")
    assert represented["candidate_ids"] == ["C2"]
    assert status["accepted_items"] == status["rejected_items"] == 1
    assert len(model.calls) == 2 and model.claims == ["verify_disputes:correction"]
