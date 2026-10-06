"""Public duplicate-word correction retains the actually selected source span."""
import json
from copy import deepcopy
from dataclasses import replace

from tests.test_brain_material import Model, fixture_scope_judgment, material, plan, send

ORIGINAL = "The event happened on Monday."
CORRECTION = "Sorry, Tuesday. Sorry, Tuesday."


class SelectedSecondSpanModel(Model):
    def structured(self, prompt, schema, tier, *, max_tokens=None):
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        payload = json.loads(prompt.user)
        data = deepcopy(result.data)
        if prompt.operation == "interpret_conversation" and payload["latest_message"] == CORRECTION:
            data["items"][0]["mutation_scopes"] = [{
                "authority_kind": "account_contribution", "authority_source_ids": ["L2"],
                "target_scope": "exact", "target_ids": ["source-seed:material:1"],
                "permitted_relations": ["corrects"],
            }]
        elif prompt.operation == "extract_legal_details" and data["changes"]:
            data["changes"][0]["source_id"] = "L2"
        elif prompt.operation == "verify_material_grounding" and any(
                row.get("relation") == "corrects" for row in payload["candidates"]):
            # The independent Judge checks the selected repeated correction
            # and the earlier event it changes. Coverage separately declares
            # that both identical current occurrences report that correction.
            for row in data["verdicts"]:
                selected = ["L2", "P1S1"]
                row["account_check"].update(source_ids=selected, source_checks=[{
                    "source_id": identity, "supplies_account_content": True,
                    "supports_proposal": True,
                    "support_spans": [{"start": 0, "end": len(
                        payload["source_treatments"][identity]["quoted"])}],
                    "reason": "The independent fixture Judge checks this original event account.",
                } for identity in selected])
            data["coverage"] = fixture_scope_judgment(
                payload, data, source_purposes=self.source_purposes,
                coverage_links=self.coverage_links)
        return replace(result, data=data)


def test_public_repeated_current_words_save_selected_span_correction_and_replay_without_retry(
        client, wired, monkeypatch):
    old = material("event", "The advocate reports Monday.", ORIGINAL, placement="matter")
    revised = material(
        "event", "The advocate corrects the event to Tuesday.", "Sorry, Tuesday.",
        relation="corrects", scope="current", placement="matter",
        references=({"turn_id": "source-seed", "role": "advocate", "quoted": ORIGINAL},),
        related_material_ids=("source-seed:material:1",))
    model = SelectedSecondSpanModel([
        plan(ORIGINAL, candidates=[old], opening=True,
             material_purposes=("account_contribution",)),
        plan(CORRECTION, candidates=[revised], material_purposes=("account_contribution",),
             record_disposition="performed", coverage_links={
                 "Sorry, Tuesday.": {"record_ids": [], "candidate_ids": ["D1"]}}),
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, ORIGINAL, "source-seed")
    assert opened.status_code == 200, opened.text
    first = deepcopy(wired.store.load(opened.json()["matter_id"]).brain_chat[0])
    response = send(client, CORRECTION, "source-correction", opened=opened.json())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["metrics"]["llm_calls"] == 8
    assert len(result["material"]) == 1
    corrected, = result["material"]
    assert corrected["source_id"] == "L2" and corrected["quoted"] == "Sorry, Tuesday."
    assert corrected["mutation_authority"]["current_source_reference"]["source_id"] == "L2"
    saved = wired.store.load(opened.json()["matter_id"])
    assert saved.brain_chat[0] == first and saved.brain_chat[-1]["message"] == CORRECTION
    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record

    reopened = material_record(saved, disputes=proposed_disputes(saved))
    assert reopened["state"] == "ok"
    assert [row["id"] for row in reopened["rows"]] == ["source-correction:material:1"]
    replay = send(client, CORRECTION, "source-correction", opened=opened.json())
    assert replay.status_code == 200, replay.text
    assert replay.json()["metrics"]["llm_calls"] == 0
    assert replay.json()["material"] == result["material"]
