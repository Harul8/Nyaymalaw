"""Mechanical fresh selection and canonical reuse, without semantic quality claims."""
from copy import deepcopy

import pytest

from nm.brain import material_verification as owner
from nm.brain.conversation import OpeningCandidate
from nm.shared.model_port import on_the_wire, require_schema
from tests.test_brain_source_support_verifiers import (
    RawJudge,
    coverage,
    disposition,
    proposal,
    source_catalogue,
    verdict,
)

SCOPE = {"requests": [{"request_index": 0, "material_purposes": ["account_contribution"]}]}


def wire_verdict(reference, *, index=1, source_id="L1", identity=None):
    result = verdict("material", reference, index=index, source_id=source_id)
    if identity is not None:
        result["candidate_id"] = identity
    del result["account_check"]["source_ids"]
    return result


def checked(model, latest, candidates, treatments, *, state=None, recheck=(), opening=None,
            scope=None):
    state = {} if state is None else state
    assessed, disagreements = {}, []
    result = owner.verify_material_grounding(
        model, candidates=candidates, earlier=(), latest=latest,
        opening=opening or OpeningCandidate(False, "", ""), current_matter_id="matter",
        source_treatments=treatments, source_disagreements=disagreements,
        review_state=state, recheck_source_ids=recheck, review_scope=scope, coverage=assessed)
    return result, state["cache"].decisions, assessed, disagreements


def test_default_material_schema_keeps_the_complete_canonical_contract():
    latest = "The collector may have received the crate; the date is uncertain."
    references, _ = source_catalogue(latest)
    schema = owner._schema(("D1",), tuple(references), source_references=references)
    row = verdict("material", references["L1"])
    before = deepcopy((row, references))

    require_schema({"verdicts": [row]}, schema)

    account = schema["properties"]["verdicts"]["items"]["properties"]["account_check"]
    assert "source_ids" in account["properties"] and "source_ids" in account["required"]
    assert (row, references) == before


def test_fresh_material_schema_has_one_required_checked_source_selection():
    latest = "The consignee reports that the delivery date remains unconfirmed."
    references, _ = source_catalogue(latest)
    schema = owner._schema(("D1",), tuple(references), source_references=references, wire=True)
    provider = on_the_wire(schema)
    account = provider["properties"]["verdicts"]["items"]["properties"]["account_check"]

    assert "source_ids" not in account["properties"]
    assert set(account["required"]) == set(account["properties"])
    assert "source_checks" in account["required"]
    require_schema({"verdicts": [wire_verdict(references["L1"])]}, schema)


def test_fresh_material_call_marks_selection_and_keeps_exact_canonical_proof_once():
    latest = "The collector reports that the storage key was retained."
    references, treatments = source_catalogue(latest)
    candidate = proposal("material", latest)
    canonical = verdict("material", references["L1"])
    before = deepcopy((canonical, treatments))
    # This ordinary scripted fixture explicitly transports faithful old proof
    # only after the producer declares the fresh selection contract.
    model = RawJudge([{"verdicts": [canonical]}])

    result, decisions, _, disagreements = checked(model, latest, (candidate,), treatments)

    assert result.details == (candidate,) and result.unread_proposals == ()
    assert disagreements == [] and len(model.calls) == 1
    call = model.calls[0]
    assert call["payload"]["review_selection_contract"] == "checked_source_selection_v1"
    account_schema = on_the_wire(call["schema"])["properties"]["verdicts"]["items"][
        "properties"]["account_check"]
    assert "source_ids" not in account_schema["properties"]
    expected = deepcopy(canonical)
    del expected["account_check"]["source_ids"]
    assert call["output"] == {"verdicts": [expected]}
    require_schema(call["output"], call["schema"])
    assert decisions == {"D1": canonical}
    assert (canonical, treatments) == before


def test_raw_authored_source_ids_are_rejected_before_material_source_diagnostics():
    latest = "The porter reports that the receipt was retained."
    references, treatments = source_catalogue(latest)
    candidate = proposal("material", latest)
    authored = verdict("material", references["L1"])
    authored["account_check"]["source_checks"][0].update(
        supplies_account_content=False, supports_proposal=False, support_spans=[])
    good = wire_verdict(references["L1"])
    model = RawJudge([{"verdicts": [authored]}, {"verdicts": [good]}], transport=False)

    result, decisions, _, disagreements = checked(model, latest, (candidate,), treatments)

    assert result.details == (candidate,) and result.unread_proposals == ()
    assert len(model.calls) == 2 and disagreements == []
    correction = model.calls[1]["payload"]
    assert [row["candidate_id"] for row in correction["candidates"]] == ["D1"]
    assert "D1" in correction["validation_issue"] and "server-owned" in correction[
        "validation_issue"]
    assert decisions["D1"]["account_check"] == {**good["account_check"], "source_ids": ["L1"]}


@pytest.mark.parametrize("contradictory", [False, True])
def test_repeated_material_source_checks_need_bounded_repair_preserving_peer(contradictory):
    first_words = "The north handler retained the key."
    second_words = "The south handler retained the receipt."
    latest = first_words + " " + second_words
    references, treatments = source_catalogue(latest)
    candidates = (proposal("material", first_words), proposal("material", second_words))
    peer = wire_verdict(references["L1"])
    bad = wire_verdict(references["L2"], index=2, source_id="L2")
    duplicate = deepcopy(bad["account_check"]["source_checks"][0])
    if contradictory:
        duplicate.update(supplies_account_content=False, supports_proposal=False, support_spans=[])
    bad["account_check"]["source_checks"].append(duplicate)
    good = wire_verdict(references["L2"], index=2, source_id="L2")
    model = RawJudge([{"verdicts": [peer, bad]}, {"verdicts": [good]}], transport=False)

    result, decisions, _, disagreements = checked(model, latest, candidates, treatments)

    assert result.details == candidates and result.unread_proposals == () and disagreements == []
    assert len(model.calls) == 2
    correction = model.calls[1]["payload"]
    assert [row["candidate_id"] for row in correction["candidates"]] == ["D2"]
    assert "source_checks repeats a source_id" in correction["validation_issue"]
    canonical_peer = {**peer, "account_check": {**peer["account_check"], "source_ids": ["L1"]}}
    assert correction["retained_candidate_context"][0]["decision"] == canonical_peer
    assert decisions["D1"] == canonical_peer


def test_material_cache_rereads_complete_canonical_proof_with_zero_calls():
    latest = "The custodian reports that the access key remains missing."
    references, treatments = source_catalogue(latest)
    candidate = proposal("material", latest)
    canonical = verdict("material", references["L1"])
    state = {}
    first = RawJudge([{"verdicts": [canonical]}])
    original, decisions, _, _ = checked(first, latest, (candidate,), treatments, state=state)
    assert original.details == (candidate,) and decisions == {"D1": canonical}
    cache = deepcopy(state["cache"])
    second = RawJudge([], transport=False)

    result, decisions, _, disagreements = checked(second, latest, (candidate,), treatments,
                                                 state=state)

    assert result == original and decisions == {"D1": canonical}
    assert second.calls == [] and disagreements == []
    assert state["cache"] == cache


def test_material_source_recheck_retains_unrelated_canonical_peer():
    first_words = "The first collector reports a missing certificate."
    second_words = "The second collector reports a missing voucher."
    latest = first_words + " " + second_words
    references, treatments = source_catalogue(latest)
    candidates = (proposal("material", first_words), proposal("material", second_words))
    canonical = (verdict("material", references["L1"]),
                 verdict("material", references["L2"], index=2, source_id="L2"))
    state = {}
    first = RawJudge([{"verdicts": list(canonical)}])
    assert checked(first, latest, candidates, treatments, state=state)[0].details == candidates
    changed = deepcopy(treatments)
    changed["L1"]["content_role"] = "reported_party_position"
    second = RawJudge([{"verdicts": [canonical[0]]}])

    result, decisions, _, disagreements = checked(
        second, latest, candidates, changed, state=state, recheck=("L1",))

    assert result.details == candidates and result.unread_proposals == () and disagreements == []
    assert len(second.calls) == 1
    payload = second.calls[0]["payload"]
    assert [row["candidate_id"] for row in payload["candidates"]] == ["D1"]
    assert payload["retained_candidate_context"][0]["decision"] == canonical[1]
    assert decisions["D2"] == canonical[1]


def test_unread_opening_selection_preserves_admitted_detail_and_complete_material_coverage():
    latest = "The keeper reports that the cabinet key was retained."
    references, treatments = source_catalogue(latest)
    candidate = proposal("material", latest)
    opening = OpeningCandidate(True, "Cabinet key retention", latest)
    detail = wire_verdict(references["L1"])
    bad_opening = wire_verdict(references["L1"], identity="O1")
    bad_opening["account_check"]["source_checks"].append(deepcopy(
        bad_opening["account_check"]["source_checks"][0]))
    assessed = coverage(references, dispositions=[
        disposition("L1", references["L1"], status="represented", candidate_ids=("D1",))])
    model = RawJudge([{"verdicts": [detail, bad_opening], "coverage": assessed},
                      {"verdicts": [bad_opening]}], transport=False)

    result, decisions, checked_coverage, disagreements = checked(
        model, latest, (candidate,), treatments, opening=opening, scope=SCOPE)

    assert result.details == (candidate,) and not result.opening_supported and result.opening_unread
    assert [row["candidate_id"] for row in result.unread_proposals] == ["O1"]
    assert decisions["D1"]["account_check"]["source_ids"] == ["L1"]
    assert checked_coverage["state"] == "complete" and disagreements == []
    assert len(model.calls) == 2
    original, correction = (row["payload"] for row in model.calls)
    assert original["coverage_candidate_ids"] == ["D1"]
    assert [row["candidate_id"] for row in correction["candidates"]] == ["O1"]
    assert "coverage_source_ids" not in correction
    assert "coverage" not in model.calls[1]["schema"]["properties"]
    assert correction["retained_candidate_context"][0]["decision"] == decisions["D1"]
