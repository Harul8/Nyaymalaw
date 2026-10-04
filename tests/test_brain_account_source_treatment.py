"""A candidate-free source read owns purpose; later reviewers cannot upgrade it."""
import json
from copy import deepcopy

import pytest

from nm.brain.conversation import Message
from nm.brain.dispute_verification import verify_disputes
from nm.brain.material import addressed_sources
from nm.brain.record_review import (
    SOURCE_TREATMENT_CONTRACT,
    classify_account_sources,
    substantive_source_treatments,
)
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage
from tests.test_brain_dispute_verification import _candidate


class SourceModel:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.ROUTINE
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema))
        return ModelResult(text=None, data=next(self.replies), tier=tier, provider="offline",
                           model="offline", usage=Usage(0, 0, 0), latency_ms=0,
                           completion=Completion.COMPLETE)


def reply(roles):
    return {"source_treatments": [{"source_id": key, "content_role": role,
                                  "reason": "The source's original framing determines its use."}
                                 for key, role in roles.items()]}


def test_source_read_preserves_complete_transcript_without_candidate_framing_and_remaps_exactly():
    earlier = (
        Message("account", "advocate", "The other side demands payment."),
        Message("answer", "nm", "This is a legal conclusion from an earlier NM analysis."),
        Message("review", "advocate", "A draft asserts the earlier account is legally sufficient. "
                "I do not adopt its analysis."),
    )
    latest = "Review the draft. Please note the carrier retained our receipt."
    payload, _, _ = addressed_sources(earlier, latest)
    before = deepcopy(payload)
    roles = {"P1S1": "reported_party_position", "P3S1": "examination_material",
             "P3S2": "work_instruction", "L1": "work_instruction", "L2": "mixed"}
    model = SourceModel([reply(roles)])

    catalogue = classify_account_sources(model, payload=payload, latest_turn_id="latest")

    sent = json.loads(model.calls[0][0].user)
    assert sent == {**before, "source_ids": list(roles)}
    assert payload == before and len(model.calls) == 1
    assert model.calls[0][0].operation == "classify_account_sources"
    assert all(name in model.calls[0][0].system for name in (
        "Message:", "Purpose:", "Look for:", "Outcome:"))
    assert "P2S1" not in catalogue
    assert catalogue["P1S1"] == {
        "turn_id": "account", "role": "advocate", "quoted": earlier[0].text,
        "content_role": "reported_party_position", "reason": reply(roles)[
            "source_treatments"][0]["reason"]}
    _, _, research_sources = addressed_sources(
        (*earlier, Message("latest", "advocate", latest)), "")
    research_sources = {key: ref for key, ref in research_sources.items() if ref.role == "advocate"}
    remapped = substantive_source_treatments(catalogue, research_sources)
    assert set(remapped) == {"P1S1", "P4S2"}
    assert remapped["P4S2"] == catalogue["L2"]
    all_roles = substantive_source_treatments(catalogue, research_sources, substantive_only=False)
    assert set(all_roles) == {"P1S1", "P3S1", "P3S2", "P4S1", "P4S2"}
    assert all_roles["P4S1"]["content_role"] == "work_instruction"
    assert SOURCE_TREATMENT_CONTRACT == "independent_account_source_treatment_v1"


@pytest.mark.parametrize("damage", ["missing", "duplicate", "foreign", "empty_reason"])
def test_incomplete_source_catalogue_gets_one_precise_same_input_correction(damage):
    payload, _, _ = addressed_sources((), "The party retained records. Review this account.")
    correct = reply({"L1": "reported_matter_account", "L2": "work_instruction"})
    wrong = deepcopy(correct)
    if damage == "missing":
        wrong["source_treatments"].pop()
    elif damage == "duplicate":
        wrong["source_treatments"].append(deepcopy(wrong["source_treatments"][0]))
    elif damage == "foreign":
        wrong["source_treatments"][0]["source_id"] = "unowned"
    else:
        wrong["source_treatments"][0]["reason"] = "  "
    model = SourceModel([wrong, correct])

    result = classify_account_sources(model, payload=payload, latest_turn_id="current")

    assert set(result) == {"L1", "L2"} and len(model.calls) == 2
    correction = json.loads(model.calls[1][0].user)
    assert correction["original_input"] == json.loads(model.calls[0][0].user)
    assert correction["validation_issue"] and correction["rejected_output"] == wrong


def test_missing_independent_catalogue_cannot_be_reconstructed_by_candidate_judge():
    candidate = _candidate("Review this work.", "Untrusted formulation")
    with pytest.raises(SchemaViolation, match="every owned advocate span"):
        verify_disputes(None, candidates=(candidate,), earlier=(), latest="Review this work.",
                        active_disputes=())


def test_candidate_formulations_are_refused_at_source_reader_boundary():
    payload, _, _ = addressed_sources((), "Read the account.")
    with pytest.raises(SchemaViolation, match="only the owned transcript"):
        classify_account_sources(None, payload={**payload, "candidates": []},
                                 latest_turn_id="current")


def test_conflicting_treatment_of_identical_canonical_span_remains_unclassified():
    _, _, refs = addressed_sources((Message("same", "advocate", "The party demands payment."),), "")
    canonical = {"turn_id": "same", "role": "advocate", "quoted": "The party demands payment.",
                 "content_role": "reported_party_position", "reason": "Scripted position"}
    catalogue = {"first": canonical,
                 "second": {**canonical, "content_role": "examination_material"}}
    assert substantive_source_treatments(catalogue, refs) == {}
