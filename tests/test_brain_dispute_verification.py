"""A proposed dispute needs an independent attributed decision before saving."""
import json

import pytest

from nm.brain.conversation import Message
from nm.brain.dispute_verification import verify_disputes
from nm.brain.material import MaterialCandidate, PriorReference
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ModelResult,
    ProviderUnavailable,
    SchemaViolation,
    Tier,
    Usage,
)


def _candidate(quoted: str, label: str, *, relation: str = "new",
               earlier: str = "") -> MaterialCandidate:
    return MaterialCandidate(
        kind="dispute", statement=f"Whether {label.lower()} is contested.",
        quoted=quoted, relation=relation,
        prior_references=(PriorReference("old", "advocate", earlier),)
        if earlier else (),
        matter_scope="current", basis="stated", importance="central",
        why_material="A practical conclusion is needed.",
        label=label, identification="identified", clarification="",
    )


def _verdict(candidate_id: str, *, accept: bool) -> dict:
    return {"candidate_id": candidate_id,
            "candidate_role": ("independent_dispute" if accept
                               else "evidence_gap_or_question"),
            "verdict": "accept" if accept else "reject",
            "reason": "Attributable dispute" if accept else "No new dispute"}


class Model:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.ROUTINE
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema, tier, max_tokens))
        answer = next(self.replies)
        if isinstance(answer, Exception):
            raise answer
        return ModelResult(
            text=None, data=answer, tier=tier, provider="offline",
            model="offline", usage=Usage(0, 0, 0), latency_ms=0,
            completion=Completion.COMPLETE)


def test_batch_checks_independent_disputes_and_withholds_unrelated_request():
    latest = "The supplier retained our tools. Please continue the research."
    candidates = (
        _candidate("The supplier retained our tools.", "Supplier retained tools"),
        _candidate("Please continue the research.", "Research request"),
    )
    model = Model([{"verdicts": [
        _verdict("C1", accept=True),
        _verdict("C2", accept=False),
    ]}])

    result = verify_disputes(
        model, candidates=candidates, earlier=(), latest=latest,
        active_disputes=())

    assert result == candidates[:1]
    assert len(model.calls) == 1
    prompt, schema, tier, _ = model.calls[0]
    assert prompt.operation == "verify_disputes" and tier is Tier.ROUTINE
    assert all(heading in prompt.system for heading in
               ("Message:", "Purpose:", "Look for:", "Outcome:"))
    payload = json.loads(prompt.user)
    assert [row["candidate_id"] for row in payload["candidates"]] == ["C1", "C2"]
    assert "".join(row["text"] for row in payload["latest_message_spans"]) == latest
    assert schema["properties"]["verdicts"]["items"]["properties"][
        "candidate_id"]["enum"] == ["C1", "C2"]


def test_bad_candidate_verdict_is_repaired_without_rechecking_valid_peer():
    latest = "The tenant disputes the charge. The tenant contests the notice."
    candidates = (
        _candidate("The tenant disputes the charge.", "Charge dispute"),
        _candidate("The tenant contests the notice.", "Notice dispute"),
    )
    model = Model([
        {"verdicts": [
            _verdict("C1", accept=True),
            {"candidate_id": "C2", "verdict": "accept", "reason": ""},
        ]},
        {"verdicts": [
            _verdict("C2", accept=True),
        ]},
    ])

    assert verify_disputes(
        model, candidates=candidates, earlier=(), latest=latest,
        active_disputes=()) == candidates
    assert len(model.calls) == 2
    repair_payload = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in repair_payload["candidates"]] == ["C2"]
    assert "validation_issue" in repair_payload


def test_premise_cannot_be_accepted_as_an_independent_dispute():
    latest = "The supplier had a duty to deliver. The supplier did not deliver."
    candidates = (
        _candidate("The supplier had a duty to deliver.", "Delivery duty"),
        _candidate("The supplier did not deliver.", "Non-delivery"),
    )
    role_mismatch = {**_verdict("C1", accept=True),
                     "candidate_role": "supporting_premise"}
    model = Model([
        {"verdicts": [role_mismatch, _verdict("C2", accept=True)]},
        {"verdicts": [{**role_mismatch, "verdict": "reject"}]},
    ])

    result = verify_disputes(model, candidates=candidates, earlier=(),
                             latest=latest, active_disputes=())

    assert result == candidates[1:]
    assert len(model.calls) == 2
    assert [row["candidate_id"] for row in
            json.loads(model.calls[1][0].user)["candidates"]] == ["C1"]


def test_changed_dispute_supplies_attributed_earlier_advocate_words():
    earlier = (Message("old", "advocate", "The charge was withheld in July."),)
    latest = "Correction: the charge was withheld in August."
    candidate = _candidate(latest, "Charge withheld in August",
                           relation="corrects", earlier=earlier[0].text)
    model = Model([{"verdicts": [_verdict("C1", accept=True)]}])

    assert verify_disputes(model, candidates=(candidate,), earlier=earlier,
                           latest=latest, active_disputes=()) == (candidate,)
    payload = json.loads(model.calls[0][0].user)
    assert payload["earlier_conversation"][0]["role"] == "advocate"
    assert payload["candidates"][0]["cited_earlier_passages"][0]["quoted"] == (
        earlier[0].text)


def test_incomplete_verification_refuses_to_silently_drop_a_candidate():
    latest = "The payment is disputed."
    candidate = _candidate(latest, "Payment dispute")
    model = Model([{"verdicts": []}, {"verdicts": []}])

    with pytest.raises(SchemaViolation, match="remained incomplete"):
        verify_disputes(model, candidates=(candidate,), earlier=(),
                        latest=latest, active_disputes=())
    assert len(model.calls) == 2


def test_provider_outage_remains_visible_to_turn_boundary():
    latest = "The payment is disputed."
    candidate = _candidate(latest, "Payment dispute")
    model = Model([ProviderUnavailable("offline")])

    with pytest.raises(ProviderUnavailable):
        verify_disputes(model, candidates=(candidate,), earlier=(),
                        latest=latest, active_disputes=())
    assert len(model.calls) == 1
