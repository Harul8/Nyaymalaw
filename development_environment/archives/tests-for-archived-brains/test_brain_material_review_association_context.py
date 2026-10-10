"""Reviewer input and reuse only; scripted decisions establish no semantic accuracy.

Whether the pinned Judge detects compound details or omitted direct links still
requires independently labelled live evaluation, including legitimate neighbours.
"""

from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import material_verification as owner
from nm.brain.conversation import Message, OpeningCandidate
from nm.shared.model_port import SchemaViolation
from tests.test_brain_source_support_verifiers import (
    RawJudge,
    proposal,
    source_catalogue,
    verdict,
)

ORIGINAL = "The courier may have delivered the cylinder, but I did not confirm receipt."
LATEST = "The receiver says the seal was broken after handover."
EARLIER = (
    Message("account", "advocate", ORIGINAL),
    Message("analysis", "nm", "Delivery and acceptance are established."),
)
DISPUTES = (
    {"id": "delivery-issue", "label": "Delivery disagreement",
     "statement": "Delivery and acceptance are established.",
     "source_turn_id": "account", "quoted": ORIGINAL},
    {"id": "condition-issue", "label": "Condition disagreement",
     "statement": "The receiver reports damage to the seal.",
     "source_turn_id": "current", "quoted": LATEST},
)


def _check(model, candidates, *, latest=LATEST, disputes=DISPUTES, state=None):
    references, treatments = source_catalogue(
        latest, earlier=EARLIER, roles={"L1": "reported_party_position"})
    assessed, disagreements = {}, []
    result = owner.verify_material_grounding(
        model, candidates=candidates, earlier=EARLIER, latest=latest,
        opening=OpeningCandidate(False, "", ""), current_matter_id="matter-31",
        active_disputes=disputes, source_treatments=treatments, review_scope=None,
        coverage=assessed, source_disagreements=disagreements, review_state=state)
    assert assessed == {}
    assert disagreements == []
    return result, references, treatments


def _assert_catalogue(payload, disputes=DISPUTES):
    assert payload["active_disputes"] == [
        {**row, "record_role": "nm_interpretation"} for row in disputes]
    assert "review_scope" not in payload
    assert "coverage_source_ids" not in payload
    assert "coverage_record_ids" not in payload
    assert "coverage_candidate_ids" not in payload


@pytest.mark.parametrize("selected", ((), ("condition-issue",)))
def test_review_without_coverage_sees_all_disputes_separately_from_selected_links(selected):
    references, _ = source_catalogue(LATEST, earlier=EARLIER)
    candidate = replace(proposal("material", LATEST), dispute_ids=selected,
                        placement="disputes" if selected else "matter")
    model = RawJudge([{"verdicts": [verdict("material", references["L1"])]}])
    before = deepcopy((DISPUTES, candidate))

    result, references, treatments = _check(model, (candidate,))

    assert result.details == (candidate,) and len(model.calls) == 1
    payload = model.calls[0]["payload"]
    _assert_catalogue(payload)
    assert payload["linked_records"] == [
        {"id": row["id"], "type": "dispute",
         "record": {**row, "record_role": "nm_interpretation"}}
        for row in DISPUTES if row["id"] in selected]
    assert payload["candidates"][0]["dispute_ids"] == list(selected)
    assert payload["source_treatments"] == references
    assert treatments["L1"]["content_role"] == "reported_party_position"
    assert all(set(row) == {"turn_id", "role", "quoted"}
               for row in payload["source_treatments"].values())
    assert "P2S1" not in payload["source_treatments"]
    assert [(row["turn_id"], row["role"], "".join(
        span["text"] for span in row["source_spans"]))
        for row in payload["earlier_conversation"]] == [
            (message.turn_id, message.role, message.text) for message in EARLIER]
    allowed = payload["candidates"][0]["allowed_account_source_ids"]
    assert allowed == ["L1"]
    assert not set(allowed).intersection(row["id"] for row in DISPUTES)
    assert model.calls[0]["schema"]["required"] == ["verdicts"]
    assert (DISPUTES, candidate) == before


def test_review_without_any_disputes_still_declares_the_empty_owned_catalogue():
    references, _ = source_catalogue(LATEST, earlier=EARLIER)
    candidate = proposal("material", LATEST)
    model = RawJudge([{"verdicts": [verdict("material", references["L1"])]}])

    result, _, _ = _check(model, (candidate,), disputes=())

    assert result.details == (candidate,) and len(model.calls) == 1
    _assert_catalogue(model.calls[0]["payload"], ())
    assert model.calls[0]["payload"]["linked_records"] == []


def test_bounded_review_correction_retains_full_catalogue_and_checked_peer():
    second = "The receiver cannot identify who removed the seal."
    latest = LATEST + " " + second
    references, _ = source_catalogue(latest, earlier=EARLIER)
    candidates = (proposal("material", LATEST), proposal("material", second))
    peer = verdict("material", references["L1"])
    bad = verdict("material", references["L2"], index=2, source_id="L2")
    bad["operation_supported"] = False
    good = verdict("material", references["L2"], index=2, source_id="L2")
    model = RawJudge([{"verdicts": [peer, bad]}, {"verdicts": [good]}])

    result, _, _ = _check(model, candidates, latest=latest)

    assert result.details == candidates and len(model.calls) == 2
    for call in model.calls:
        _assert_catalogue(call["payload"])
        assert call["schema"]["required"] == ["verdicts"]
    correction = model.calls[1]["payload"]
    assert [row["candidate_id"] for row in correction["candidates"]] == ["D2"]
    assert [row["candidate_id"] for row in correction["retained_candidate_context"]] == ["D1"]
    assert correction["retained_candidate_context"][0]["decision"] == peer
    assert correction["earlier_conversation"] == model.calls[0]["payload"]["earlier_conversation"]
    assert correction["source_treatments"] == references


def test_unchanged_association_context_reuses_checked_review_without_another_call():
    references, _ = source_catalogue(LATEST, earlier=EARLIER)
    candidate = proposal("material", LATEST)
    state = {}
    first = RawJudge([{"verdicts": [verdict("material", references["L1"])]}])
    original, _, _ = _check(first, (candidate,), state=state)
    cache = deepcopy(state["cache"])
    reread = RawJudge([])

    result, _, _ = _check(reread, (candidate,), state=state)

    assert result == original and reread.calls == []
    assert state["cache"] == cache


def test_reuse_cannot_ignore_a_changed_previously_supplied_unselected_dispute():
    references, _ = source_catalogue(LATEST, earlier=EARLIER)
    candidate = proposal("material", LATEST)
    state = {}
    first = RawJudge([{"verdicts": [verdict("material", references["L1"])]}])
    _check(first, (candidate,), state=state)
    before = deepcopy(state)
    changed = deepcopy(DISPUTES)
    changed[0]["statement"] = "Receipt remains unconfirmed in the reported account."
    reread = RawJudge([])

    with pytest.raises(SchemaViolation, match="changed a prior owned record"):
        _check(reread, (candidate,), disputes=changed, state=state)

    assert reread.calls == [] and state == before


def test_dispute_context_alone_does_not_start_an_unrequested_review():
    model = RawJudge([])

    result, _, _ = _check(model, ())

    assert result.details == () and result.opening_supported
    assert model.calls == []
