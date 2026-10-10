"""Fresh Judge transport and canonical reuse; no semantic detection is measured."""
from copy import deepcopy

import pytest

from nm.brain import dispute_verification as owner
from nm.shared.model_port import on_the_wire, require_schema
from tests.brain_reader_fixture import fresh_review_reply
from tests.test_brain_source_support_verifiers import RawJudge, proposal, source_catalogue, verdict


def wire_verdict(reference, *, index=1, source_id="L1"):
    result = verdict("dispute", reference, index=index, source_id=source_id)
    del result["account_check"]["source_ids"]
    return result


def checked(model, latest, candidates, treatments, *, state=None, recheck=()):
    audit, status, disagreements = [], {}, []
    retained = owner.verify_disputes(
        model, candidates=candidates, earlier=(), latest=latest, active_disputes=(),
        source_treatments=treatments, audit=audit, review_status=status,
        source_disagreements=disagreements, review_state=state, recheck_source_ids=recheck)
    return retained, audit, status, disagreements


def test_fresh_provider_selects_once_and_admission_preserves_complete_canonical_proof():
    latest = "The freight owner disputes the carrier's reported receipt."
    references, treatments = source_catalogue(latest)
    candidate = proposal("dispute", latest)
    row = wire_verdict(references["L1"])
    before = deepcopy((row, treatments))
    model = RawJudge([{"verdicts": [row]}], transport=False)

    retained, audit, status, disagreements = checked(model, latest, (candidate,), treatments)

    assert retained == (candidate,) and status["state"] == "checked"
    assert disagreements == [] and len(model.calls) == 1
    call = model.calls[0]
    assert call["payload"]["review_selection_contract"] == "checked_source_selection_v1"
    provider = on_the_wire(call["schema"])
    for branch in provider["properties"]["verdicts"]["items"]["anyOf"]:
        account = branch["properties"]["account_check"]
        assert "source_ids" not in account["properties"]
        assert set(account["required"]) == set(account["properties"])
    require_schema(call["output"], call["schema"])
    canonical = audit[0]["account_check"]
    assert canonical == {**row["account_check"], "source_ids": ["L1"]}
    assert (row, treatments) == before


def test_zero_call_cached_reread_validates_canonical_proof_without_transporting_it():
    latest = "The carrier disputes responsibility for the missing parcel."
    references, treatments = source_catalogue(latest)
    candidate = proposal("dispute", latest)
    state = {}
    first = RawJudge([{"verdicts": [wire_verdict(references["L1"])]}], transport=False)
    retained, original_audit, _, _ = checked(first, latest, (candidate,), treatments, state=state)
    assert retained == (candidate,) and len(first.calls) == 1
    cached = deepcopy(state["cache"].decisions)
    assert cached["C1"]["account_check"]["source_ids"] == ["L1"]
    second = RawJudge([], transport=False)

    retained, audit, status, disagreements = checked(
        second, latest, (candidate,), treatments, state=state)

    assert retained == (candidate,) and second.calls == []
    assert status["state"] == "checked" and disagreements == []
    assert audit == original_audit and state["cache"].decisions == cached


def test_source_recheck_invalidates_only_its_dependent_candidate():
    first_words = "The north receiver disputes the missing consignment."
    second_words = "The south receiver disputes the handling charge."
    latest = first_words + " " + second_words
    references, treatments = source_catalogue(latest)
    candidates = (proposal("dispute", first_words), proposal("dispute", second_words))
    state = {}
    first = RawJudge([{"verdicts": [
        wire_verdict(references["L1"]),
        wire_verdict(references["L2"], index=2, source_id="L2"),
    ]}], transport=False)
    assert checked(first, latest, candidates, treatments, state=state)[0] == candidates
    peer = deepcopy(state["cache"].decisions["C2"])
    changed = deepcopy(treatments)
    changed["L1"]["content_role"] = "reported_party_position"
    second = RawJudge([{"verdicts": [wire_verdict(references["L1"])]}], transport=False)

    retained, audit, status, disagreements = checked(
        second, latest, candidates, changed, state=state, recheck=("L1",))

    assert retained == candidates and status["state"] == "checked" and disagreements == []
    assert len(second.calls) == 1
    payload = second.calls[0]["payload"]
    assert [row["candidate_id"] for row in payload["candidates"]] == ["C1"]
    assert payload["retained_candidate_context"][0]["decision"] == peer
    assert {key: value for key, value in audit[1].items() if key != "proposal"} == peer


def test_authored_source_ids_are_rejected_before_source_role_diagnostics():
    latest = "The carrier disputes the attributed delivery account."
    references, treatments = source_catalogue(latest)
    candidate = proposal("dispute", latest)
    authored = verdict("dispute", references["L1"])
    # An independently authored purpose contradiction cannot become a diagnostic
    # until the fresh transport object has passed its schema and selection gate.
    authored["account_check"]["source_checks"][0].update(
        supplies_account_content=False, supports_proposal=False, support_spans=[])
    model = RawJudge([{"verdicts": [authored]},
                      {"verdicts": [wire_verdict(references["L1"])]}], transport=False)

    retained, audit, status, disagreements = checked(model, latest, (candidate,), treatments)

    assert retained == (candidate,) and status["state"] == "checked"
    assert len(model.calls) == 2 and disagreements == []
    assert "C1" in model.calls[1]["payload"]["validation_issue"]
    assert "server-owned" in model.calls[1]["payload"]["validation_issue"]
    assert audit[0]["account_check"]["source_ids"] == ["L1"]


@pytest.mark.parametrize("contradictory", [False, True])
def test_repeated_source_checks_require_bounded_repair_preserving_valid_peer(contradictory):
    first_words = "The seller disputes payment for the north delivery."
    second_words = "The buyer disputes damage to the south delivery."
    latest = first_words + " " + second_words
    references, treatments = source_catalogue(latest)
    candidates = (proposal("dispute", first_words), proposal("dispute", second_words))
    peer = wire_verdict(references["L1"])
    bad = wire_verdict(references["L2"], index=2, source_id="L2")
    duplicate = deepcopy(bad["account_check"]["source_checks"][0])
    if contradictory:
        duplicate.update(supplies_account_content=False, supports_proposal=False, support_spans=[])
    bad["account_check"]["source_checks"].append(duplicate)
    fixed = wire_verdict(references["L2"], index=2, source_id="L2")
    model = RawJudge([{"verdicts": [peer, bad]}, {"verdicts": [fixed]}], transport=False)

    retained, audit, status, disagreements = checked(model, latest, candidates, treatments)

    assert retained == candidates and status["state"] == "checked" and disagreements == []
    assert len(model.calls) == 2
    correction = model.calls[1]["payload"]
    assert [row["candidate_id"] for row in correction["candidates"]] == ["C2"]
    assert "source_checks repeats a source_id" in correction["validation_issue"]
    canonical_peer = {**peer, "account_check": {**peer["account_check"], "source_ids": ["L1"]}}
    assert correction["retained_candidate_context"][0]["decision"] == canonical_peer
    assert {key: value for key, value in audit[0].items() if key != "proposal"} == canonical_peer


def fixture_payload():
    return {"review_selection_contract": "checked_source_selection_v1", "candidates": [{
        "candidate_id": "C1", "allowed_account_source_ids": ["L1", "L2"],
    }]}


def fixture_reply():
    return {"verdicts": [{"candidate_id": "C1", "account_check": {
        "source_ids": ["L1", "L2"], "source_checks": [
            {"source_id": "L2", "supplies_account_content": False,
             "supports_proposal": False, "support_spans": [], "reason": "Context only."},
            {"source_id": "L1", "supplies_account_content": True,
             "supports_proposal": True, "support_spans": [{"start": 2, "end": 19}],
             "reason": "Exact scripted support."},
        ], "reason": "Keep this authored evidence unchanged.",
    }}]}


def test_fixture_transport_is_explicit_copied_and_preserves_all_authored_evidence():
    payload, data = fixture_payload(), fixture_reply()
    before = deepcopy((payload, data))
    expected = deepcopy(data)
    del expected["verdicts"][0]["account_check"]["source_ids"]

    assert fresh_review_reply(payload, data) == expected
    assert fresh_review_reply({"original_input": payload}, data) == expected
    assert fresh_review_reply({}, data) == data
    assert (payload, data) == before


@pytest.mark.parametrize("defect", ["repeated_ids", "repeated_checks", "mismatch", "foreign",
                                   "malformed_ids", "unknown_candidate"])
def test_fixture_transport_does_not_erase_authored_selection_defects(defect):
    payload, data = fixture_payload(), fixture_reply()
    row = data["verdicts"][0]
    account = row["account_check"]
    if defect == "repeated_ids":
        account["source_ids"].append("L1")
    elif defect == "repeated_checks":
        account["source_checks"].append(deepcopy(account["source_checks"][0]))
    elif defect == "mismatch":
        account["source_ids"] = ["L1"]
    elif defect == "foreign":
        account["source_ids"].append("foreign")
        account["source_checks"].append({"source_id": "foreign"})
    elif defect == "malformed_ids":
        account["source_ids"] = "L1"
    else:
        row["candidate_id"] = ["C1"]
    before = deepcopy((payload, data))

    assert fresh_review_reply(payload, data) == data
    assert (payload, data) == before
