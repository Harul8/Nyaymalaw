"""Fresh detail coverage has its own domain; saved proofs keep their owners.

All source purposes, support and sufficiency judgments below are independently
scripted fixtures. These tests exercise actual admission, shared correction,
cache, save and replay boundaries. They do not establish that a real Judge
detects omissions, or that a source-sized quotation preserves every proposition.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from nm.brain import record_review
from nm.brain.conversation import Message, OpeningCandidate
from nm.brain.material import addressed_sources
from nm.brain.material_verification import verify_material_grounding
from nm.brain.turn import _CountedModel
from tests.brain_verdict_quarantine_support import Judge
from tests.test_brain_material import send
from tests.test_brain_material_coverage import detail
from tests.test_brain_material_purpose import PurposeModel, open_account, seed_plan
from tests.test_brain_post_application_coverage import applied, assessment, opening_proof
from tests.test_brain_source_support_coverage import disposition, purpose_check, treatment

pytestmark = pytest.mark.class_a

FIRST = "The custodian retained the signed delivery note."
SECOND = "The courier delivered a separate duplicate."
WORDS = FIRST + " " + SECOND
SCOPE = {"requests": [{"request_index": 0, "material_purposes": ["account_capture"]}]}
NO_OPENING = OpeningCandidate(False, "", "")


def sources(earlier, latest, *, non_account=()):
    _, current, prior = addressed_sources(earlier, latest)
    references = {
        identity: {"turn_id": ref.turn_id, "role": ref.role, "quoted": ref.quoted}
        for identity, ref in prior.items() if ref.role == "advocate"
    }
    references.update({identity: {"turn_id": "latest", "role": "advocate", "quoted": words}
                       for identity, words in current.items()})
    return {identity: treatment(reference, role=(
        "work_instruction" if identity in non_account else "reported_matter_account"))
        for identity, reference in references.items()}


def current_record(identity, words=FIRST, *, turn="latest"):
    return {"id": identity, "kind": "event", "statement": words, "quoted": words,
            "source_turn_id": turn, "matter_scope": "current", "placement": "matter",
            "grounding": {"contract": "preserved-original-proof", "support": [words]}}


def current_dispute(identity):
    return {**current_record(identity), "kind": "dispute", "label": "Reported document custody",
            "identification": "identified", "placement": ""}


def positive(payload, identity, source="L1"):
    reference = payload["source_treatments"][source]
    return {
        "candidate_id": identity, "verdict": "accept", "operation_supported": True,
        "reason": "The explicitly selected original account supports this whole proposal.",
        "account_check": {
            "content_role": "reported_matter_account", "supported": True,
            "introduces_legal_analysis": False, "source_ids": [source],
            "source_checks": [{
                "source_id": source, "supplies_account_content": True,
                "supports_proposal": True,
                "support_spans": [{"start": 0, "end": len(reference["quoted"])}],
                "reason": "The exact original words support this attributed proposition.",
            }], "reason": "Attribution and the distinct underlying proposition are preserved.",
        }, "target_checks": [],
    }


def coverage(payload, selected, *, purposes=None, state=None):
    """The test owner declares every source disposition, never the extractor."""
    purposes = purposes or {}
    checks, portions = [], []
    for identity, reference in payload["source_treatments"].items():
        purpose = purposes.get(identity, "account")
        checks.append(purpose_check(identity, reference, purpose=purpose))
        if purpose != "account":
            continue
        status, records, candidates = selected[identity]
        portions.append(disposition(
            identity, (0, len(reference["quoted"])), status=status,
            records=records, candidates=candidates))
    if state is None:
        state = "partial" if any(row["status"] in ("missing", "unresolved")
                                  for row in portions) else "complete"
    return {"state": state, "reason": "Each original account portion has its declared disposition.",
            "source_checks": checks, "dispositions": portions}


def run(judge, *, candidates=(), opening=NO_OPENING, latest=FIRST, earlier=(),
        active_material=(), active_disputes=(), treatments=None, cache=None):
    sink = {}
    result = verify_material_grounding(
        judge, candidates=candidates, opening=opening, earlier=earlier, latest=latest,
        active_material=active_material, active_disputes=active_disputes,
        source_treatments=treatments or sources(earlier, latest),
        review_scope=deepcopy(SCOPE), coverage=sink, review_state=cache)
    return result, sink


@pytest.mark.parametrize("representation", ["heading", "opening"])
def test_heading_or_opening_cannot_complete_material_detail_coverage(representation):
    def first(payload):
        selected = ("represented", ("issue",), ()) if representation == "heading" else (
            "represented", (), ("O1",))
        return {"verdicts": [positive(payload, "O1")] if representation == "opening" else [],
                "coverage": coverage(payload, {"L1": selected})}

    def correction(payload):
        return {"verdicts": [],
                "coverage": coverage(payload, {"L1": ("missing", (), ())})}

    port = Judge([first, correction])
    model = _CountedModel(port)
    opening = OpeningCandidate(True, "Reported document custody", FIRST) if (
        representation == "opening") else NO_OPENING
    disputes = (current_dispute("issue"),) if representation == "heading" else ()

    result, sink = run(model, opening=opening, active_disputes=disputes)

    assert sink["state"] == "partial" and sink["missing_source_ids"] == ["L1"]
    assert result.details == () and result.opening_supported
    assert len(port.calls) == 2
    assert port.calls[1]["payload"]["candidates"] == []
    if representation == "opening":
        retained = port.calls[1]["payload"]["retained_candidate_context"]
        assert [(row["candidate_id"], row["decision"]["verdict"]) for row in retained] == [
            ("O1", "accept")]
    assert model.metrics()["recovery"]["reserved_calls"] == 1
    assert model.metrics()["recovery"]["events"][0]["phase"] == (
        "verify_material_grounding:correction")


def test_schema_limits_material_representation_but_keeps_full_review_context():
    earlier = (Message("old-advocate", "advocate", SECOND),
               Message("old-nm", "nm", "The earlier derived account remains open for review."))
    detail_row, dispute_row = current_record("material"), current_dispute("issue")
    candidate = detail(FIRST)
    original_sources = sources(earlier, FIRST)
    original = deepcopy((earlier, detail_row, dispute_row, original_sources))
    cache = {}

    def reply(payload):
        return {"verdicts": [positive(payload, "D1"), positive(payload, "O1")],
                "coverage": coverage(payload, {
                    "P1S1": ("outside_scope", (), ()),
                    "L1": ("represented", ("material",), ("D1",)),
                })}

    port = Judge([reply])
    result, sink = run(port, candidates=(candidate,), earlier=earlier,
                       opening=OpeningCandidate(True, "Reported custody", FIRST),
                       active_material=(detail_row,), active_disputes=(dispute_row,),
                       treatments=original_sources, cache=cache)

    assert result.details == (candidate,) and result.opening_supported
    assert sink["state"] == "complete" and len(port.calls) == 1
    payload, schema = port.calls[0]["payload"], port.calls[0]["schema"]
    assert payload["coverage_record_ids"] == ["material"]
    assert payload["coverage_candidate_ids"] == ["D1"]
    choices = schema["properties"]["coverage"]["properties"]["dispositions"]["items"]
    assert choices["properties"]["record_ids"]["items"]["enum"] == ["material"]
    assert choices["properties"]["candidate_ids"]["items"]["enum"] == ["D1"]
    assert schema["properties"]["verdicts"]["items"]["properties"][
        "candidate_id"]["enum"] == ["D1", "O1"]
    assert [row["id"] for row in payload["active_disputes"]] == ["issue"]
    assert [row["candidate_id"] for row in payload["candidates"]] == ["D1", "O1"]
    assert ["".join(span["text"] for span in row["source_spans"])
            for row in payload["earlier_conversation"]] == [row.text for row in earlier]
    assert "".join(row["text"] for row in payload["latest_message_spans"]) == FIRST
    assert (earlier, detail_row, dispute_row, original_sources) == original
    assert cache["cache"].source_treatments == original_sources
    assert set(cache["cache"].decisions) == {"D1", "O1"}
    assert "coverage_record_ids" not in cache["cache"].context
    assert "coverage_candidate_ids" not in cache["cache"].context
    assert sink["selection_contract"] == record_review.COVERAGE_SELECTION_CONTRACT
    assert sink["contract"] == record_review.ACCOUNT_COVERAGE_CONTRACT


def test_faithful_current_material_completes_without_new_extraction_or_operation():
    record = current_record("material")
    original = deepcopy(record)
    port = Judge([lambda payload: {
        "verdicts": [], "coverage": coverage(payload, {
            "L1": ("represented", ("material",), ())})}])
    model = _CountedModel(port, recovery_limit=0)

    result, sink = run(model, active_material=(record,))

    assert result.details == () and sink["state"] == "complete"
    assert sink["dispositions"][0]["record_ids"] == ["material"]
    assert record == original and record["grounding"] == original["grounding"]
    assert model.metrics()["llm_calls"] == 1
    assert model.metrics()["recovery"]["events"] == []


@pytest.mark.parametrize("accepted", [True, False])
def test_checked_opening_verdict_with_no_detail_candidate_keeps_current_material_complete(accepted):
    def reply(payload):
        row = positive(payload, "O1")
        if not accepted:
            row.update(verdict="reject", operation_supported=False,
                       reason="This opening description is unsupported by the original account.")
            row["account_check"].update(
                content_role="uncertain", supported=False, source_ids=[], source_checks=[],
                reason="The supplied opening description does not preserve this account.")
        return {"verdicts": [row], "coverage": coverage(payload, {
            "L1": ("represented", ("material",), ())})}

    port = Judge([reply])
    model = _CountedModel(port, recovery_limit=0)
    result, sink = run(model, active_material=(current_record("material"),),
                       opening=OpeningCandidate(True, "Reported custody", FIRST))

    assert result.details == () and result.opening_supported is accepted
    assert sink["state"] == "complete" and sink["missing_source_ids"] == []
    assert model.metrics()["llm_calls"] == 1 and model.metrics()["recovery"]["events"] == []


def test_honest_missing_material_is_partial_without_needless_correction():
    port = Judge([lambda payload: {
        "verdicts": [], "coverage": coverage(payload, {"L1": ("missing", (), ())})}])
    model = _CountedModel(port, recovery_limit=0)

    result, sink = run(model)

    assert result.details == () and sink["state"] == "partial"
    assert sink["missing_sources"][0]["quoted"] == FIRST
    assert model.metrics()["llm_calls"] == 1
    assert model.metrics()["recovery"]["events"] == []


@pytest.mark.parametrize("judgment", ["non_account", "outside_scope"])
def test_checked_empty_or_outside_scope_content_needs_no_material_representation(judgment):
    latest = ("Please review the supplied draft without adopting it."
              if judgment == "non_account" else
              "The custodian retained another matter's signed delivery note.")
    original_sources = sources((), latest,
                               non_account=("L1",) if judgment == "non_account" else ())
    port = Judge([lambda payload: {
        "verdicts": [], "coverage": coverage(
            payload, {"L1": ("outside_scope", (), ())},
            purposes={"L1": judgment} if judgment == "non_account" else {})}])
    model = _CountedModel(port, recovery_limit=0)

    result, sink = run(model, latest=latest, treatments=original_sources)

    assert result.details == () and sink["state"] == "complete"
    assert sink["missing_source_ids"] == []
    assert model.metrics()["llm_calls"] == 1 and model.metrics()["recovery"]["events"] == []


@pytest.mark.parametrize("representation", ["current", "candidate"])
def test_unread_opening_does_not_invalidate_independent_material_coverage(representation):
    candidate = detail(FIRST)
    record = current_record("material")

    def reply(payload):
        verdicts = [positive(payload, "D1")] if any(
            row["candidate_id"] == "D1" for row in payload["candidates"]) else []
        selected = ("represented", ("material",), ()) if representation == "current" else (
            "represented", (), ("D1",))
        return {"verdicts": verdicts, "coverage": coverage(payload, {"L1": selected})}

    port = Judge([reply, reply])
    result, sink = run(
        port, candidates=(candidate,) if representation == "candidate" else (),
        active_material=(record,) if representation == "current" else (),
        opening=OpeningCandidate(True, "Reported custody", FIRST))

    assert result.details == ((candidate,) if representation == "candidate" else ())
    assert result.opening_unread and not result.opening_supported
    assert len(port.calls) == 2
    assert [row["candidate_id"] for row in port.calls[1]["payload"]["candidates"]] == ["O1"]
    assert sink["state"] == "complete" and sink["missing_source_ids"] == []
    assert "admission_holds" not in sink


def test_unread_detail_keeps_sound_peer_but_cannot_complete_material_coverage():
    first, second = detail(FIRST), detail(SECOND)

    def reply(payload):
        verdicts = [positive(payload, "D1")] if any(
            row["candidate_id"] == "D1" for row in payload["candidates"]) else []
        return {"verdicts": verdicts, "coverage": coverage(payload, {
            "L1": ("represented", (), ("D1",)), "L2": ("missing", (), ())})}

    port = Judge([reply, reply])
    result, sink = run(port, candidates=(first, second), latest=WORDS)

    assert result.details == (first,) and result.unread_details == 1
    assert sink["state"] != "complete" and sink["missing_source_ids"] == ["L2"]
    assert sink["dispositions"][0]["candidate_ids"] == ["D1"]
    correction = port.calls[1]["payload"]
    assert [row["candidate_id"] for row in correction["candidates"]] == ["D2"]
    assert [row["candidate_id"] for row in correction["retained_candidate_context"]] == ["D1"]


def test_cached_positive_detail_and_opening_remain_owned_during_coverage_recheck():
    candidate, cache = detail(FIRST), {}
    opening = OpeningCandidate(True, "Reported custody", FIRST)
    def first(payload):
        return {"verdicts": [positive(payload, "D1"), positive(payload, "O1")],
                "coverage": coverage(payload, {"L1": ("represented", (), ("D1",))})}
    def second(payload):
        assert payload["candidates"] == []
        return {"verdicts": [],
                "coverage": coverage(payload, {"L1": ("represented", (), ("D1",))})}
    port = Judge([first, second])
    run(port, candidates=(candidate,), opening=opening, cache=cache)
    original_cache = deepcopy(cache["cache"])

    result, sink = run(port, candidates=(candidate,), opening=opening, cache=cache)

    assert result.details == (candidate,) and result.opening_supported
    assert sink["state"] == "complete" and cache["cache"] == original_cache
    assert [row["candidate_id"] for row in port.calls[1]["payload"][
        "retained_candidate_context"]] == ["D1", "O1"]


@pytest.mark.parametrize("representation", ["opening", "dispute"])
def test_historical_representation_keeps_its_saved_owner_and_metadata(representation):
    saved = assessment(candidates=("O1",), peer=False) if representation == "opening" else (
        assessment(records=("saved-dispute",), peer=False))
    original = deepcopy(saved)

    result = applied(saved, active=() if representation == "opening" else ("saved-dispute",),
                     opening=opening_proof() if representation == "opening" else None)

    assert result == original and saved == original and result is not saved
    assert result["selection_contract"] == record_review.COVERAGE_SELECTION_CONTRACT
    missing_owner = applied(saved, active=())
    assert missing_owner["state"] == "partial" and missing_owner["missing_source_ids"] == ["north"]


def test_public_material_save_reopen_and_replay_keep_detail_proof_and_original_words(
        client, wired, monkeypatch):
    account = "The carrier holds the original delivery note, and its location is uncertain."
    model = PurposeModel([seed_plan(account)])
    opened = open_account(client, wired, monkeypatch, model, account, turn_id="domain-original")
    saved = wired.store.load(opened["matter_id"])
    original = deepcopy(saved.brain_chat[0])
    response = client.get(f"/api/matters/{opened['matter_id']}")
    assert response.status_code == 200, response.text
    material = response.json()["material_record"]
    assert len(material["rows"]) == 1 and material["rows"][0]["quoted"] == account
    detail_coverage = opened["material_coverage"]["execution"]["stages"][
        "detail_review"]["account_coverage"]
    assert detail_coverage["state"] == "complete"
    assert all("O1" not in row["candidate_ids"] for row in detail_coverage["dispositions"])
    calls = len(model.seen)

    replay = send(client, account, "domain-original")

    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] and replay.json()["metrics"]["llm_calls"] == 0
    assert len(model.seen) == calls and replay.json()["elements"] == opened["elements"]
    assert wired.store.load(opened["matter_id"]).brain_chat[0] == original
    assert original["message"] == account
    assert original["response"]["material_coverage"]["execution"]["coverage_application"]["seal"]
