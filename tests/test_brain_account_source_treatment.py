"""A candidate-free source read owns purpose; later reviewers cannot upgrade it."""
import json
from copy import deepcopy

import pytest

from nm.brain.conversation import Message
from nm.brain.dispute_verification import verify_disputes
from nm.brain.material import addressed_sources
from nm.brain.record_review import (
    SOURCE_SELECTION_CONTRACT,
    SOURCE_TREATMENT_CONTRACT,
    classify_account_sources,
    substantive_source_treatments,
)
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage
from tests.brain_reader_fixture import source_portion_reply
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
        data = source_portion_reply(json.loads(prompt.user), next(self.replies))
        return ModelResult(text=None, data=data, tier=tier, provider="offline",
                           model="offline", usage=Usage(0, 0, 0), latency_ms=0,
                           completion=Completion.COMPLETE)


def reply(roles):
    return {"source_treatments": {key: {
        "content_role": role, "reason": "The source's original framing determines its use."}
        for key, role in roles.items()}}


def test_source_read_preserves_complete_transcript_without_candidate_framing_and_remaps_exactly():
    earlier = (
        Message("account", "advocate", "The other side demands payment."),
        Message("answer", "nm", "This is a legal conclusion from an earlier NM analysis."),
        Message("review", "advocate", "A draft asserts the earlier account is legally sufficient. "
                "I do not adopt its analysis."),
    )
    latest = "Review the draft. Please note the carrier retained our receipt."
    payload, current, prior = addressed_sources(earlier, latest)
    before = deepcopy(payload)
    roles = {"P1S1": "reported_party_position", "P3S1": "examination_material",
             "P3S2": "work_instruction", "L1": "work_instruction", "L2": "mixed"}
    model = SourceModel([reply(roles)])

    catalogue = classify_account_sources(model, payload=payload, latest_turn_id="latest")

    sent = json.loads(model.calls[0][0].user)
    expected_input = {**before, "source_ids": list(roles)}
    if sent.get("source_selection_contract") == SOURCE_SELECTION_CONTRACT:
        expected_input.update(
            source_selection_contract=SOURCE_SELECTION_CONTRACT,
            original_source_catalogue={
                **{identity: {"turn_id": reference.turn_id, "role": reference.role,
                              "quoted": reference.quoted}
                   for identity, reference in prior.items() if reference.role == "advocate"},
                **{identity: {"turn_id": "latest", "role": "advocate", "quoted": words}
                   for identity, words in current.items()},
            })
    assert sent == expected_input
    assert payload == before and len(model.calls) == 1
    assert model.calls[0][0].operation == "classify_account_sources"
    assert all(name in model.calls[0][0].system for name in (
        "Message:", "Purpose:", "Look for:", "Outcome:"))
    schema = model.calls[0][1]["properties"]["source_treatments"]
    assert schema["type"] == "object" and schema["additionalProperties"] is False
    assert schema["required"] == list(roles) and set(schema["properties"]) == set(roles)
    for entry in schema["properties"].values():
        for branch in entry.get("anyOf", [entry]):
            assert branch["additionalProperties"] is False
            fields = {"content_role", "reason"}
            if sent.get("source_selection_contract") == SOURCE_SELECTION_CONTRACT:
                fields.add("substantive_spans")
                offsets = branch["properties"]["substantive_spans"]["items"]
                assert set(offsets["required"]) == set(offsets["properties"]) == {"start", "end"}
            assert set(branch["required"]) == set(branch["properties"]) == fields
    assert "P2S1" not in catalogue
    expected_row = {
        "turn_id": "account", "role": "advocate", "quoted": earlier[0].text,
        "content_role": "reported_party_position", "reason": reply(roles)[
            "source_treatments"]["P1S1"]["reason"]}
    row = catalogue["P1S1"]
    if sent.get("source_selection_contract") == SOURCE_SELECTION_CONTRACT:
        assert row["selection_contract"] == SOURCE_SELECTION_CONTRACT
        assert len(row["substantive_spans"]) == 1
        portion = row["substantive_spans"][0]
        assert portion["start"] == 0 and portion["end"] == len(earlier[0].text)
        assert portion["quoted"] == earlier[0].text and portion["anchor_id"].startswith("asp_")
        expected_row.update(selection_contract=SOURCE_SELECTION_CONTRACT,
                            substantive_spans=row["substantive_spans"])
    assert row == expected_row
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


@pytest.mark.parametrize("damage", [
    "missing", "wrong_envelope", "repeated_source_id", "foreign", "empty_reason", "blank_reason",
])
def test_incomplete_source_catalogue_gets_one_precise_same_input_correction(damage):
    payload, _, _ = addressed_sources((), "The party retained records. Review this account.")
    correct = reply({"L1": "reported_matter_account", "L2": "work_instruction"})
    wrong = deepcopy(correct)
    if damage == "missing":
        wrong["source_treatments"].pop("L2")
    elif damage == "wrong_envelope":
        wrong["source_treatments"] = [
            {"source_id": key, **row} for key, row in wrong["source_treatments"].items()]
    elif damage == "repeated_source_id":
        wrong["source_treatments"]["L1"]["source_id"] = "L1"
    elif damage == "foreign":
        wrong["source_treatments"]["unowned"] = deepcopy(wrong["source_treatments"]["L1"])
    else:
        wrong["source_treatments"]["L1"]["reason"] = "  " if damage == "blank_reason" else ""
    model = SourceModel([wrong, correct])

    result = classify_account_sources(model, payload=payload, latest_turn_id="current")

    assert set(result) == {"L1", "L2"} and len(model.calls) == 2
    correction = json.loads(model.calls[1][0].user)
    assert correction["original_input"] == json.loads(model.calls[0][0].user)
    assert correction["validation_issue"] and correction["rejected_output"] == source_portion_reply(
        correction["original_input"], wrong)


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
