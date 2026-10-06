"""Attribution and authority for a material-record operation are distinct checks.

Offline verdicts exercise the shipped acceptance boundary, not model quality.
All accounts and review propositions below are synthetic.
"""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.conversation import Message, OpeningCandidate
from nm.brain.material import MaterialCandidate, PriorReference
from nm.brain.material_verification import verify_material_grounding
from tests.brain_reader_fixture import classified_verifier, reviewed_record_verdicts
from tests.test_brain_material import Model, material, plan, send
from tests.test_brain_material_verification import Model as CheckerModel

verify_material_grounding = classified_verifier(verify_material_grounding)
FIRST = "We paid the contractor an advance of 4 lakh."
ORIGINAL = "The advocate reports an advance payment of 4 lakh."
CORRECTION = "Correction: our advance payment was 3 lakh, not 4 lakh."
CORRECTED = "The advocate corrects the advance payment to 3 lakh."
REVIEW_WORDS = "The client paid 3 lakh and no other payment is relevant."
REVIEW = (f"A junior wrote, '{REVIEW_WORDS}' Please critique that analysis; "
          "I have not adopted its account or conclusion.")
REVIEW_REPLACEMENT = "The advocate's advance payment was 3 lakh."
POSITION = "The contractor now says the bank receipt is incomplete."
REPORTED_POSITION = "The contractor reportedly says the bank receipt is incomplete."


def _decision(candidate_id, *, supported=True, accept=True):
    return {"candidate_id": candidate_id, "operation_supported": supported,
            "verdict": "accept" if accept else "reject",
            "reason": "The latest attributed contribution supports the operation."
            if supported else "The supplied proposition is for review or a different "
            "account, not a supported revision of the selected saved proposition."}


def _candidate(statement, latest, *, relation="new", basis="stated"):
    return MaterialCandidate(
        kind="position", statement=statement, quoted=latest,
        relation=relation, matter_scope="current", basis=basis,
        importance="relevant", why_material="It bears on the reported account.",
        placement="matter", related_material_ids=("original:material:1",)
        if relation != "new" else (),
        prior_references=(PriorReference("original", "advocate", FIRST),)
        if relation != "new" else ())


def test_inconsistent_accept_repairs_only_that_operation_and_preserves_peer_context():
    revised = _candidate(REVIEW_REPLACEMENT, REVIEW, relation="corrects")
    reported = _candidate(REPORTED_POSITION, POSITION, basis="attributed")
    latest = f"{REVIEW} {POSITION} That is their allegation; we dispute it."
    checker = CheckerModel([
        {"verdicts": [_decision("D1", supported=False), _decision("D2")]},
        {"verdicts": [_decision("D1", supported=False, accept=False)]},
    ])
    prior = {"id": "original:material:1", "statement": ORIGINAL,
             "quoted": FIRST, "source_turn_id": "original", "basis": "stated"}

    result = verify_material_grounding(
        checker, candidates=(revised, reported),
        opening=OpeningCandidate(False, "", ""), latest=latest,
        earlier=(Message("original", "advocate", FIRST),),
        prior_material=(prior,), current_matter_id="synthetic-matter")

    assert result.details == (reported,)
    assert len(checker.calls) == 2
    schema = checker.calls[0][1]["properties"]["verdicts"]["items"]
    assert "operation_supported" in schema["required"]
    assert schema["properties"]["operation_supported"] == {"type": "boolean"}
    repair = json.loads(checker.calls[1][0].user)
    assert [row["candidate_id"] for row in repair["candidates"]] == ["D1"]
    assert repair["retained_candidate_context"][0]["candidate_id"] == "D2"
    assert repair["retained_candidate_context"][0]["decision"]["verdict"] == "accept"
    assert "operation_supported true" in repair["validation_issue"]
    assert repair["linked_records"] == [
        {"id": prior["id"], "type": "material", "record": {
            **prior, "record_role": "nm_interpretation"}}]
    audit, = result.rejected_proposals
    assert audit["operation_supported"] is False
    assert audit["verdict"] == "reject"
    assert audit["proposal"]["related_material_ids"] == (prior["id"],)
    assert all(heading in checker.calls[0][0].system for heading in
               ("Message:", "Purpose:", "Look for:", "Outcome:"))


@pytest.mark.parametrize("candidate_type", ("detail", "opening"))
def test_an_accept_without_supported_operation_never_releases(candidate_type):
    candidate_id = "D1" if candidate_type == "detail" else "O1"
    checker = CheckerModel([
        {"verdicts": [_decision(candidate_id, supported=False)]},
        {"verdicts": [_decision(candidate_id, supported=False)]},
    ])

    result = verify_material_grounding(
        checker, candidates=(_candidate(ORIGINAL, FIRST),)
        if candidate_type == "detail" else (),
        opening=OpeningCandidate(candidate_type == "opening", "Payment account", FIRST),
        latest=FIRST, earlier=(), current_matter_id="synthetic-matter")
    assert len(checker.calls) == 2
    assert result.details == ()
    assert result.opening_supported is (candidate_type != "opening")
    assert len(result.unread_proposals) == 1
    unread, = result.unread_proposals
    assert unread["candidate_id"] == candidate_id
    assert unread["verdict"] == "unassessed"
    assert unread["admission_issue"] == "review_unavailable"
    assert unread["validation_issues"] == ["accept conflicts with operation_supported=false"]


def test_missing_operation_decision_is_not_treated_as_implicit_support():
    missing = _decision("D1")
    missing.pop("operation_supported")
    checker = CheckerModel([
        {"verdicts": [missing]},
        {"verdicts": [_decision("D1")]},
    ])
    proposed = _candidate(ORIGINAL, FIRST)
    result = verify_material_grounding(
        checker, candidates=(proposed,), opening=OpeningCandidate(False, "", ""),
        latest=FIRST, earlier=(), current_matter_id="synthetic-matter")
    assert result.details == (proposed,)
    assert len(checker.calls) == 2


class OperationModel(Model):
    """Return explicitly scripted independent decisions, without word inference."""

    def __init__(self, plans, rejected_statements=()):
        super().__init__(plans)
        self.rejected_statements = set(rejected_statements)
        self.material_checks = []

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        if prompt.operation != "verify_material_grounding":
            return result
        payload = json.loads(prompt.user)
        self.material_checks.append(payload)
        verdicts = []
        for row in payload["candidates"]:
            supported = row.get("statement") not in self.rejected_statements
            verdicts.append(_decision(row["candidate_id"], supported=supported,
                                      accept=supported))
        return replace(result, data=reviewed_record_verdicts(
            payload, {"verdicts": verdicts}, scripted_full_scope=True))


def _change(statement, latest, *, basis="stated"):
    return material(
        "circumstance", statement, latest, relation="corrects", basis=basis,
        scope="current", placement="matter",
        related_material_ids=("original:material:1",),
        references=({"turn_id": "original", "role": "advocate", "quoted": FIRST},))


@pytest.mark.parametrize("mode", (
    "nonadopted_review", "nm_reasoning", "ambiguous_reference", "different_account",
    "actual_correction", "mixed",
))
def test_public_material_change_needs_latest_support_and_retains_valid_mixed_content(
        client, wired, monkeypatch, mode):
    original = material("circumstance", ORIGINAL, FIRST,
                        scope="proposed", placement="matter")
    candidates = []
    rejected = []
    if mode in ("nonadopted_review", "mixed"):
        latest = REVIEW
        candidates.append(_change(REVIEW_REPLACEMENT, REVIEW_WORDS, basis="attributed"))
        rejected.append(REVIEW_REPLACEMENT)
    elif mode == "nm_reasoning":
        latest = "Your earlier analysis changed the payment amount. Please explain it."
        candidates.append(_change(REVIEW_REPLACEMENT,
                                  "Your earlier analysis changed the payment amount.",
                                  basis="inferred"))
        rejected.append(REVIEW_REPLACEMENT)
    elif mode == "ambiguous_reference":
        latest = "She changed it yesterday. Does that settle things?"
        candidates.append(_change(REVIEW_REPLACEMENT, "She changed it yesterday.",
                                  basis="uncertain"))
        rejected.append(REVIEW_REPLACEMENT)
    elif mode == "different_account":
        latest = "On a different client file, the advance payment was 3 lakh."
        candidates.append(_change(REVIEW_REPLACEMENT, latest))
        rejected.append(REVIEW_REPLACEMENT)
    else:
        latest = CORRECTION
    if mode in ("actual_correction", "mixed"):
        if mode == "mixed":
            latest += f" {CORRECTION} {POSITION} That is their reported view, which we dispute."
        candidates.append(_change(CORRECTED, CORRECTION))
    if mode == "mixed":
        candidates.append(material("position", REPORTED_POSITION, POSITION,
                                   scope="current", basis="attributed", placement="matter"))
    # Deliberately request account reading for the unsupported work-product
    # cases too: independent admission must reject the faulty router/proposal
    # combination without treating examination as authority to change facts.
    model = OperationModel([
        plan(FIRST, candidates=[original], opening=True,
             material_purposes=("account_contribution",)),
        plan(latest, candidates=candidates, material_purposes=("account_contribution",)),
    ], rejected)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    opened = send(client, FIRST, "original")
    assert opened.status_code == 200, opened.text
    original_turn = deepcopy(wired.store.load(opened.json()["matter_id"]).brain_chat[0])
    response = send(client, latest, "followup", opened=opened.json())
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["metrics"]["llm_calls"] == 8
    assert [row["operation"] for row in answer["metrics"]["model_calls"]] == [
        "interpret_conversation", "classify_account_sources", "extract_disputes", "verify_disputes",
        "extract_legal_details",
        "verify_material_grounding", "continue_conversation", "verify_continuation"]
    assert len(model.material_checks) == 2
    checked = model.material_checks[-1]
    assert "".join(row["text"] for row in checked["latest_message_spans"]) == latest
    assert "".join(row["text"] for row in
                   checked["earlier_conversation"][0]["source_spans"]) == FIRST
    assert checked["linked_records"][0]["record"]["statement"] == ORIGINAL

    projected = client.get(f"/api/matters/{answer['matter_id']}")
    assert projected.status_code == 200, projected.text
    record = projected.json()["material_record"]
    assert record["state"] == "ok"
    rows = {row["statement"]: row for row in record["rows"]}
    expected = {CORRECTED} if mode in ("actual_correction", "mixed") else {ORIGINAL}
    if mode == "mixed":
        expected.add(REPORTED_POSITION)
    assert set(rows) == expected
    if mode in ("actual_correction", "mixed"):
        assert rows[CORRECTED]["related_material_ids"] == ["original:material:1"]
        assert rows[CORRECTED]["relation"] == "corrects"
        assert len(record["history"]) == (3 if mode == "mixed" else 2)
    else:
        assert rows[ORIGINAL]["id"] == "original:material:1"
        assert len(record["history"]) == 1
    if mode == "mixed":
        assert rows[REPORTED_POSITION]["basis"] == "attributed"
        assert rows[REPORTED_POSITION]["relation"] == "new"
        assert rows[REPORTED_POSITION]["related_material_ids"] == []

    saved = wired.store.load(answer["matter_id"])
    assert saved.brain_chat[0] == original_turn
    assert [row["message"] for row in saved.brain_chat] == [FIRST, latest]
    assert saved.facts == ()
    audit = saved.brain_chat[-1]["response"]["material_coverage"]["rejected_proposals"]
    assert len(audit) == len(rejected)
    if rejected:
        assert audit[0]["operation_supported"] is False
        assert audit[0]["verdict"] == "reject"
        assert audit[0]["proposal"]["related_material_ids"] == ["original:material:1"]
    replay = send(client, latest, "followup", opened=opened.json())
    assert replay.status_code == 200, replay.text
    assert replay.json()["metrics"]["llm_calls"] == 0
    assert len(wired.store.load(answer["matter_id"]).brain_chat) == 2
