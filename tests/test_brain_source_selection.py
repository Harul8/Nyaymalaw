"""Repeated citation declarations do not multiply or weaken source evidence."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.material import PriorReference, resolve_sources
from nm.shared.model_port import SchemaViolation
from tests.test_brain_material import Model, material, plan, send


def test_selection_normalizes_exact_durable_references_after_validating_all_ids():
    earlier = PriorReference("turn-one", "advocate", "The reported amount is four.")
    nm_words = PriorReference("turn-one", "nm", earlier.quoted)
    another_turn = PriorReference("turn-two", "advocate", earlier.quoted)
    different_passage = PriorReference("turn-one", "advocate", "The reported amount is three.")
    prior = {"P1": earlier, "alias": earlier, "NM": nm_words,
             "P2": another_turn, "different": different_passage}
    selected = [{"source_id": "L1",
                 "prior_source_ids": ["P1", "P1", "NM", "alias", "P2", "different"],
                 "statement": "The advocate corrects the reported amount."}]
    before = deepcopy(selected)

    result = resolve_sources(selected, latest={"L1": "Correction."}, prior=prior)

    assert result == [{"statement": selected[0]["statement"], "quoted": "Correction.",
                       "prior_references": [vars(earlier), vars(nm_words),
                                            vars(another_turn), vars(different_passage)]}]
    assert selected == before
    assert prior == {"P1": earlier, "alias": earlier, "NM": nm_words,
                     "P2": another_turn, "different": different_passage}


@pytest.mark.parametrize("invalid", ("unknown", 7, None, {"id": "P1"}))
def test_invalid_selection_after_identical_references_is_not_masked(invalid):
    selected = [{"source_id": "L1", "prior_source_ids": ["P1", "P1", invalid]}]
    before = deepcopy(selected)

    with pytest.raises(SchemaViolation, match="source selection is invalid"):
        resolve_sources(selected, latest={"L1": "Latest words."},
                        prior={"P1": PriorReference("original", "advocate", "Prior words.")})
    assert selected == before


FIRST_PASSAGE = "We paid the contractor an advance of 4 lakh."
FIRST = f"{FIRST_PASSAGE} {FIRST_PASSAGE}"
CORRECTION = "Correction: the advance was 3 lakh, not 4 lakh."


class RepeatedSelectionModel(Model):
    def __init__(self, plans, *, invalid=None):
        super().__init__(plans)
        self.invalid = invalid
        self.raw_selections = []
        self.grounding_inputs = []

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        payload = json.loads(prompt.user)
        if prompt.operation == "verify_material_grounding":
            self.grounding_inputs.append(payload)
        if prompt.operation != "extract_legal_details":
            return result
        data = deepcopy(result.data)
        if "repairs" in data:
            groups = [unit["proposals"] for identity, unit in data["repairs"].items()
                      if unit.get("field", identity.split(":", 1)[0]) == "changes"]
        else:
            groups = [data["changes"]]
        if not any(groups):
            return result
        original = payload.get("original_input", payload)
        references = [span["id"] for message in original["earlier_conversation"]
                      if message["turn_id"] == "original" and message["role"] == "advocate"
                      for span in message["source_spans"] if span["text"].strip() == FIRST_PASSAGE]
        assert len(references) == 2
        for proposals in groups:
            for row in proposals:
                row["prior_source_ids"] = [references[0], references[0], references[1]]
                if self.invalid is not None:
                    row["prior_source_ids"].append(self.invalid)
                self.raw_selections.append(deepcopy(row["prior_source_ids"]))
        return replace(result, data=data)


def _public_model(*, invalid=None):
    original = material("circumstance", "The advocate reports an advance of 4 lakh.",
                        FIRST_PASSAGE, placement="matter")
    correction = material(
        "circumstance", "The advocate corrects the advance to 3 lakh.", CORRECTION,
        relation="corrects", scope="current", placement="matter",
        references=({"turn_id": "original", "role": "advocate", "quoted": FIRST_PASSAGE},),
        related_material_ids=("original:material:1",))
    return RepeatedSelectionModel([
        plan(FIRST, candidates=[original], opening=True,
             material_purposes=("account_contribution",)),
        plan(CORRECTION, candidates=[correction], material_purposes=("account_contribution",)),
    ], invalid=invalid)


def test_public_repeated_ids_and_aliases_reach_existing_judge_once_before_saving(
        client, wired, monkeypatch):
    model = _public_model()
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, FIRST, "original")
    assert opened.status_code == 200, opened.text
    before = deepcopy(wired.store.load(opened.json()["matter_id"]).brain_chat[0])

    response = send(client, CORRECTION, "correction", opened=opened.json())

    assert response.status_code == 200, response.text
    assert response.json()["metrics"]["llm_calls"] == 8
    assert len(model.raw_selections) == 1
    assert len(model.grounding_inputs) == 2
    checked = model.grounding_inputs[-1]
    candidate, = checked["candidates"]
    exact_ref = {"turn_id": "original", "role": "advocate", "quoted": FIRST_PASSAGE}
    assert candidate["cited_earlier_passages"] == [exact_ref]
    assert checked["linked_records"][0]["record"]["id"] == "original:material:1"
    saved = wired.store.load(opened.json()["matter_id"])
    assert saved.brain_chat[0] == before
    saved_material, = saved.brain_chat[-1]["response"]["material"]
    assert saved_material["prior_references"] == [exact_ref]
    assert saved_material["grounding"] == "advocate_semantic_v1"
    assert saved_material["related_material_ids"] == ["original:material:1"]
    assert saved.brain_chat[-1]["response"]["material_coverage"]["rejected_proposals"] == []
    assert [turn["message"] for turn in saved.brain_chat] == [FIRST, CORRECTION]
    replay = send(client, CORRECTION, "correction", opened=opened.json())
    assert replay.status_code == 200, replay.text
    assert replay.json()["metrics"]["llm_calls"] == 0


@pytest.mark.parametrize("invalid", ("unknown", 7))
def test_public_invalid_id_after_repeats_stops_before_judge_or_commit(
        client, wired, monkeypatch, invalid):
    model = _public_model(invalid=invalid)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, FIRST, "original")
    assert opened.status_code == 200, opened.text
    before = deepcopy(wired.store.load(opened.json()["matter_id"]).brain_chat)

    response = send(client, CORRECTION, "correction", opened=opened.json())

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["committed"] == "not_committed"
    assert len(model.raw_selections) == 2
    assert all(selection[-1] == invalid for selection in model.raw_selections)
    repairs = [json.loads(prompt.user) for prompt in model.material_calls
               if "validation_issue" in json.loads(prompt.user)]
    assert len(repairs) == 1
    assert repairs[0]["failed_units"][0]["unit_id"] == "changes:1"
    assert repairs[0]["failed_units"][0]["proposal"]["prior_source_ids"][-1] == invalid
    assert len(model.grounding_inputs) == 1
    assert wired.store.load(opened.json()["matter_id"]).brain_chat == before
