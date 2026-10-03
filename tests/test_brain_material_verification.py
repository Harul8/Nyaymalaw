"""A source ID cannot by itself establish a model-written material fact."""
import json

import pytest

from nm.brain.conversation import Message, OpeningCandidate
from nm.brain.material import MaterialCandidate, PriorReference
from nm.brain.material_verification import verify_material_grounding
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage


class Model:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.JUDGE
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema))
        return ModelResult(
            text=None, data=next(self.replies), tier=tier, provider="offline",
            model="offline", usage=Usage(0, 0, 0), latency_ms=0,
            completion=Completion.COMPLETE)


def detail(quoted, statement, *, earlier=""):
    return MaterialCandidate(
        kind="event", statement=statement, quoted=quoted, relation="new",
        prior_references=(PriorReference("old", "advocate", earlier),)
        if earlier else (), matter_scope="proposed", basis="stated",
        importance="central", why_material="It bears on the reported events.",
        placement="unresolved")


def verdict(candidate_id, *, accept=True, reason="Grounded"):
    return {"candidate_id": candidate_id,
            "verdict": "accept" if accept else "reject", "reason": reason}


def test_one_batch_checks_details_and_opening_without_dropping_valid_peer():
    latest = "The supplier held the drawings. I sent a return request."
    good = detail("The supplier held the drawings.",
                  "The advocate reports that the supplier held the drawings.")
    invented = detail("I sent a return request.",
                      "The supplier admitted taking the drawings.")
    opening = OpeningCandidate(True, "Drawings dispute",
                               "The supplier admitted wrongdoing.")
    model = Model([{"verdicts": [
        verdict("D1"), verdict("D2", accept=False),
        verdict("O1", accept=False)]}])

    result = verify_material_grounding(
        model, candidates=(good, invented), opening=opening,
        earlier=(), latest=latest)

    assert result.details == (good,)
    assert result.rejected_details == 1
    assert result.opening_supported is False
    assert len(model.calls) == 1
    prompt, schema = model.calls[0]
    assert prompt.operation == "verify_material_grounding"
    assert all(heading in prompt.system for heading in
               ("Message:", "Purpose:", "Look for:", "Outcome:"))
    payload = json.loads(prompt.user)
    assert [row["candidate_id"] for row in payload["candidates"]] == [
        "D1", "D2", "O1"]
    assert schema["properties"]["verdicts"]["items"]["properties"][
        "candidate_id"]["enum"] == ["D1", "D2", "O1"]


def test_invalid_verdict_retries_only_the_unresolved_proposal():
    latest = "The supplier held the drawings. I sent a return request."
    first = detail("The supplier held the drawings.", "Supplier held drawings.")
    second = detail("I sent a return request.", "I requested return.")
    model = Model([{"verdicts": [
        verdict("D1"), verdict("D2", reason="")]},
        {"verdicts": [verdict("D2")]}])

    result = verify_material_grounding(
        model, candidates=(first, second),
        opening=OpeningCandidate(False, "", ""), earlier=(), latest=latest)

    assert result.details == (first, second)
    assert len(model.calls) == 2
    repair = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in repair["candidates"]] == ["D2"]
    assert "validation_issue" in repair


def test_changed_detail_supplies_earlier_advocate_words_and_full_context():
    earlier = (Message("old", "advocate", "The hearing is on Tuesday."),
               Message("old", "nm", "Please confirm the date."))
    latest = "Correction: the hearing is on Thursday."
    changed = detail(latest, "The advocate corrects the date to Thursday.",
                     earlier="The hearing is on Tuesday.")
    model = Model([{"verdicts": [verdict("D1")]}])

    verify_material_grounding(
        model, candidates=(changed,), opening=OpeningCandidate(False, "", ""),
        earlier=earlier, latest=latest)

    payload = json.loads(model.calls[0][0].user)
    assert [item["role"] for item in payload["earlier_conversation"]] == [
        "advocate", "nm"]
    assert payload["candidates"][0]["cited_earlier_passages"][0]["quoted"] == (
        "The hearing is on Tuesday.")


def test_unfinished_verification_refuses_to_save_unread_detail():
    latest = "The payment is disputed."
    proposed = detail(latest, "Payment is disputed.")
    model = Model([{"verdicts": []}, {"verdicts": []}])

    with pytest.raises(SchemaViolation, match="remained incomplete"):
        verify_material_grounding(
            model, candidates=(proposed,),
            opening=OpeningCandidate(False, "", ""), earlier=(), latest=latest)
    assert len(model.calls) == 2


def test_no_detail_or_opening_needs_no_call():
    model = Model([])
    result = verify_material_grounding(
        model, candidates=(), opening=OpeningCandidate(False, "", ""),
        earlier=(), latest="Hello")
    assert result.details == ()
    assert result.opening_supported is True
    assert model.calls == []


def test_an_accepted_verdict_cannot_admit_two_people_in_opening_prefix():
    latest = ("Our clients Mira Patel and Om Rao say a supplier retained "
              "their records after cancellation.")
    opening = OpeningCandidate(
        True, "Mira Patel and Om Rao: Return of records",
        "The clients report that the supplier retained their records.")
    model = Model([{"verdicts": [verdict("O1")]}])

    result = verify_material_grounding(
        model, candidates=(), opening=opening, earlier=(), latest=latest)

    assert result.opening_supported is False
    assert len(model.calls) == 1
    assert "exactly one person or entity" in model.calls[0][0].system


def test_a_single_entity_name_containing_and_is_not_split_mechanically():
    latest = "Our client North and South LLP says the supplier retained records."
    opening = OpeningCandidate(
        True, "North and South LLP: Return of records",
        "The client reports that the supplier retained records.")
    model = Model([{"verdicts": [verdict("O1")]}])

    result = verify_material_grounding(
        model, candidates=(), opening=opening, earlier=(), latest=latest)

    assert result.opening_supported is True
