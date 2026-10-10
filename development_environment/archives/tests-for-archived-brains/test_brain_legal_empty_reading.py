"""Conditional independent empty-reading boundary; semantic judgments are scripted."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.legal_requirements import empty_reading_verification_valid, verify_findings
from nm.shared.model_port import ProviderUnavailable, SchemaViolation, Tier
from tests.test_brain_legal_requirements import CONVERSATION, REQUEST_SUBJECT, Model, request_hits


def check(source_id="s1", outcome="no_supported_finding"):
    return {"source_id": source_id, "outcome": outcome,
            "reason": "This scripted judgment addresses the source's use for this enquiry."}


def reply(subject_id="q1", checks=None):
    return {"subject_id": subject_id, "source_checks": checks if checks is not None else [check()]}


def review(model, *, searches=None, subjects=None):
    owned = subjects or (REQUEST_SUBJECT,)
    return verify_findings(model, subjects=owned,
                           material_by_subject={subject["id"]: [] for subject in owned},
                           proposed={subject["id"]: [] for subject in owned},
                           conversation=CONVERSATION, search_results=searches)


@pytest.mark.parametrize(("outcome", "derived", "state", "withheld"), [
    ("no_supported_finding", "no_supported_finding", "ok", 0),
    ("supports_useful_finding", "findings_omitted", "partial", 1),
    ("uncertain", "uncertain", "partial", 1),
])
def test_empty_findings_get_bounded_independent_supplied_passage_review(
        outcome, derived, state, withheld):
    searches = request_hits()
    searches["q1"]["candidates"][0].update(date="2020-11-02", jurisdiction="Source jurisdiction")
    untouched = deepcopy(searches)
    model = Model([{"readings": [reply(checks=[check(outcome=outcome)])]}])

    result = review(model, searches=searches)

    assert len(model.calls) == 1 and model.calls[0][2] is Tier.JUDGE
    assert model.calls[0][0].operation == "verify_empty_legal_reading"
    payload = json.loads(model.calls[0][0].user)
    assert payload["subjects"][0]["candidates"] == untouched["q1"]["candidates"]
    assert [(row["turn_id"], row["role"], "".join(span["text"] for span in row["source_spans"]))
            for row in payload["conversation"]] == [
                (message.turn_id, message.role, message.text) for message in CONVERSATION]
    assert result.rows == {"q1": []}
    coverage = result.coverage["q1"]
    assert coverage["state"] == state
    assert coverage["checked_items"] == 1 and coverage["unread_items"] == 0
    assert coverage["withheld_items"] == withheld
    assert coverage["semantic_extent"] == "supplied_retrieved_passages"
    receipt = coverage["empty_reading"]
    assert receipt["outcome"] == derived
    assert receipt["sources"] == untouched["q1"]["candidates"]
    assert empty_reading_verification_valid(receipt, subject_id="q1")
    assert searches == untouched


def test_complete_empty_pool_is_code_evidence_without_a_wasted_model_call():
    model = Model([])

    result = review(model, searches={"q1": {"state": "ok", "candidates": []}})

    assert model.calls == [] and result.rows == {"q1": []}
    coverage = result.coverage["q1"]
    assert coverage["state"] == "ok" and coverage["checked_items"] == 0
    assert coverage["semantic_extent"] == "no_supplied_passages"
    assert coverage["empty_reading"]["outcome"] == "no_supplied_passages"
    assert empty_reading_verification_valid(coverage["empty_reading"], subject_id="q1")


def test_missing_pool_is_unconfirmed_rather_than_completed_empty_research():
    model = Model([])

    result = review(model)

    assert model.calls == []
    assert result.coverage["q1"]["state"] == "partial"
    assert result.coverage["q1"]["unread_items"] == 1
    assert result.coverage["q1"]["semantic_extent"] == "unconfirmed"
    assert "empty_reading" not in result.coverage["q1"]


@pytest.mark.parametrize("state", ["partial", "unavailable"])
def test_incomplete_search_does_not_become_complete_empty_coverage(state):
    searches = request_hits()
    searches["q1"]["state"] = state
    if state == "unavailable":
        searches["q1"]["candidates"] = []
    model = Model([{"readings": [reply()]}])

    result = review(model, searches=searches)

    assert result.coverage["q1"]["state"] == state
    assert len(model.calls) == (1 if state == "partial" else 0)


def test_identical_owned_check_duplication_is_normalised_without_retry():
    exact = check()
    model = Model([{"readings": [reply(checks=[exact, deepcopy(exact)])]}])

    result = review(model, searches=request_hits())

    assert len(model.calls) == 1
    assert result.coverage["q1"]["empty_reading"]["source_checks"] == [exact]


def test_conflicting_checks_get_one_precise_correction():
    model = Model([{"readings": [reply(checks=[check(), check(outcome="uncertain")])]},
                   {"readings": [reply()]}])

    result = review(model, searches=request_hits())

    assert len(model.calls) == 2
    assert result.coverage["q1"]["state"] == "ok"
    repair = json.loads(model.calls[1][0].user)
    assert "conflicting" in repair["validation_issues"]["q1"]


def test_bad_source_reference_repairs_only_pending_subject_and_preserves_sound_peer():
    second = {**REQUEST_SUBJECT, "id": "q2", "question": "Explain another enquiry"}
    searches = request_hits()
    searches["q2"] = deepcopy(searches["q1"])
    searches["q2"]["candidates"][0]["id"] = "s2"
    model = Model([{"readings": [reply(checks=[check("s2")]), reply("q2", [check("s2")])]},
                   {"readings": [reply()]}])

    result = review(model, searches=searches, subjects=(REQUEST_SUBJECT, second))

    assert len(model.calls) == 2
    assert all(coverage["state"] == "ok" for coverage in result.coverage.values())
    repair = json.loads(model.calls[1][0].user)
    assert [row["subject"]["id"] for row in repair["subjects"]] == ["q1"]
    assert result.coverage["q2"]["checked_items"] == 1


@pytest.mark.parametrize("search_state", ["ok", "partial"])
def test_provider_outage_is_not_a_positive_empty_attestation(search_state):
    model = Model([ProviderUnavailable("offline injection")])
    searches = request_hits()
    searches["q1"]["state"] = search_state

    result = review(model, searches=searches)

    assert len(model.calls) == 1 and result.outage == "ProviderUnavailable"
    assert result.coverage["q1"]["state"] == "unavailable"
    assert result.coverage["q1"]["unread_items"] == 1
    assert "empty_reading" not in result.coverage["q1"]


def test_downgraded_empty_review_cannot_supply_independent_coverage():
    class DowngradedModel(Model):
        def structured(self, *args, **kwargs):
            result = super().structured(*args, **kwargs)
            return replace(result, tier=Tier.ROUTINE, downgraded_from=Tier.JUDGE)

    model = DowngradedModel([{"readings": [reply()]}])

    result = review(model, searches=request_hits())

    assert len(model.calls) == 1 and result.outage == "TierUnavailable"
    assert result.coverage["q1"]["state"] == "unavailable"
    assert "empty_reading" not in result.coverage["q1"]


def test_unknown_search_owner_fails_before_dispatch():
    model = Model([])
    with pytest.raises(SchemaViolation, match="owned subject IDs"):
        review(model, searches={"another-subject": request_hits()["q1"]})
    assert model.calls == []


def test_malformed_search_is_local_and_cannot_hide_a_reliably_empty_peer():
    second = {**REQUEST_SUBJECT, "id": "q2", "question": "Explain another enquiry"}
    model = Model([])
    searches = {"q1": {"state": "ok", "candidates": [{"id": "bad"}]},
                "q2": {"state": "ok", "candidates": []}}

    result = review(model, searches=searches, subjects=(REQUEST_SUBJECT, second))

    assert model.calls == []
    assert result.coverage["q1"]["state"] == "partial"
    assert result.coverage["q2"]["state"] == "ok"
    assert result.coverage["q2"]["empty_reading"]["outcome"] == "no_supplied_passages"
