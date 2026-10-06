"""Matter ownership is independent of proof and ambiguous records stay visible."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.dispute_state import proposed_disputes
from nm.brain.material import extract_details
from nm.brain.material_state import material_record
from nm.work_the_file.matter_contracts import Matter
from tests.test_brain_material import Model as ServiceModel
from tests.test_brain_material import material, plan, send
from tests.test_brain_material_specialist import Model, candidate


def _dispute():
    return {"id": "issue", "label": "Contested amount", "statement": "The amount is disputed.",
            "source_turn_id": "first", "quoted": "The amount is disputed.",
            "matter_scope": "proposed"}


@pytest.mark.parametrize("has_current_matter", (False, True))
def test_linked_assignment_owns_scope_without_an_independent_scope_choice(
        has_current_matter):
    original = {**candidate(source_id="L1", scope="uncertain"),
                "basis": "uncertain", "placement": "disputes", "dispute_ids": ["issue"]}
    scope = "current" if has_current_matter else "proposed"
    model = Model({"details": [original]})
    dispute = _dispute()
    before = deepcopy(dispute)

    rows = extract_details(model, earlier=(), latest="The amount may be three units.",
                           current_matter_id="mat_scope" if has_current_matter else None,
                           disputes=(dispute,))

    assert len(model.calls) == 1
    assert rows[0].matter_scope == scope
    assert rows[0].basis == "uncertain"
    assert rows[0].quoted == "The amount may be three units."
    payload = json.loads(model.calls[0][0].user)
    target = next(row for row in payload["assignment_targets"] if row["id"] == "issue")
    assert target["matter_scope"] == scope
    assert target["record"] == {**dispute, "record_role": "nm_interpretation"}
    assert dispute == before
    fields = model.calls[0][1]["properties"]["new_items"]["items"]["properties"]
    assert not {"matter_scope", "dispute_ids", "placement"}.intersection(fields)


def test_genuinely_ambiguous_ownership_can_remove_the_link_in_the_same_correction():
    linked = {**candidate(source_id="L1", scope="uncertain"),
              "assignment_ids": ["issue", "matter:uncertain"]}
    held = {**linked, "assignment_ids": ["matter:uncertain"]}
    model = Model({"details": [linked]}, repair={"details": [held]})

    rows = extract_details(model, earlier=(), latest="This amount may concern another file.",
                           current_matter_id="mat_scope", disputes=(_dispute(),))

    assert len(model.calls) == 2
    assert rows[0].matter_scope == "uncertain"
    assert rows[0].placement == "unresolved" and rows[0].dispute_ids == ()


def test_clear_opening_ownership_preserves_uncertain_basis_in_one_call():
    row = {**candidate(source_id="L1", scope="proposed"),
           "basis": "uncertain", "placement": "disputes", "dispute_ids": ["issue"]}
    model = Model({"details": [row]})

    result = extract_details(model, earlier=(), latest="The amount may be three units.",
                             current_matter_id=None, disputes=(_dispute(),))

    assert len(model.calls) == 1
    assert result[0].matter_scope == "proposed" and result[0].basis == "uncertain"
    assert "a described record is not proof of its contents" in model.calls[0][0].system


def _saved(turn_id, words, proposals, *, route="matter"):
    elements = [{"text": "An attributed saved response."}]
    return {"turn_id": turn_id, "advocate_id": "adv", "matter_id": "mat_scope",
            "message": words, "committed": True, "release_state": "released",
            "elements": elements, "response": {"turn_id": turn_id, "route": route,
                                                "material": proposals, "elements": elements}}


def _record(row, turn_id, index):
    return {**row, "id": f"{turn_id}:material:{index}", "source_turn_id": turn_id,
            "state": "proposed", "grounding": "advocate_semantic_v1"}


def _matter(*turns):
    return Matter(id="mat_scope", advocate_id="adv", title="Scope test", brain_chat=turns)


def _project(matter):
    return material_record(matter, disputes=proposed_disputes(matter))


def test_attributable_ambiguous_material_is_held_with_partial_coverage_and_no_promotion():
    words = "An amount was paid. It may relate to another file."
    held = _record(material("circumstance", "The reported payment may concern another file.",
                            "It may relate to another file.", scope="uncertain",
                            basis="uncertain", placement="unresolved"), "first", 1)
    matter = _matter(_saved("first", words, [held]))
    before = deepcopy(matter.brain_chat)

    result = _project(matter)

    assert result["state"] == "ok" and result["problems"] == []
    assert result["rows"] == result["matter"] == result["unresolved"] == []
    assert result["excluded_scope"] == [held]
    assert result["coverage"]["state"] == "partial"
    assert result["coverage"]["ambiguous_scope_items"] == 1
    assert result["coverage"]["diagnostics"]
    assert matter.brain_chat == before


def test_clear_peers_survive_ambiguous_scope_and_held_rows_can_be_explicitly_resolved():
    words = "A receipt exists. The amount may concern another file."
    clear = _record(material("evidence", "A receipt is reported.", "A receipt exists.",
                             placement="matter", basis="described_record"), "first", 1)
    held = _record(material("circumstance", "Ownership of the reported amount is unclear.",
                            "The amount may concern another file.", scope="uncertain"),
                   "first", 2)
    matter = _matter(_saved("first", words, [clear, held]))
    before = _project(matter)
    assert before["rows"] == before["matter"] == [clear]
    assert before["excluded_scope"] == [held]
    clarification = "That amount belongs to this file; the amount is still uncertain."
    resolved = _record(material(
        "circumstance", "The advocate places the uncertain amount in this file.", clarification,
        relation="corrects", scope="current", basis="uncertain", placement="matter",
        related_material_ids=(held["id"],), references=({
            "turn_id": "first", "role": "advocate", "quoted": held["quoted"]},)), "second", 1)

    result = _project(replace(matter, brain_chat=(*matter.brain_chat,
                                                _saved("second", clarification, [resolved]))))

    assert result["state"] == "ok" and result["coverage"]["state"] == "ok"
    assert result["rows"] == [clear, resolved] and result["excluded_scope"] == []
    assert result["rows"][1]["basis"] == "uncertain"
    assert result["rows"][1]["prior_references"][0]["quoted"] == held["quoted"]


def test_ambiguous_source_corruption_is_an_integrity_failure_not_an_empty_success():
    held = _record(material("event", "An event may concern another file.", "Invented passage",
                            scope="uncertain"), "first", 1)
    result = _project(_matter(_saved("first", "The actual saved account.", [held])))

    assert result["state"] == "incomplete" and result["coverage"]["state"] == "unavailable"
    assert result["excluded_scope"] == [] and result["problems"]


def test_legacy_held_interpretation_exposes_only_exact_words_and_missing_verification():
    words = "A record may concern another file."
    held = _record(material("evidence", "Unreviewed interpretation of a record.", words,
                            scope="uncertain", placement="matter"), "first", 1)
    held.pop("grounding")

    result = _project(_matter(_saved("first", words, [held])))

    assert result["state"] == "ok" and result["coverage"]["state"] == "partial"
    assert result["coverage"]["legacy_unverified_items"] == 1
    assert result["excluded_scope"][0]["statement"] == words
    assert result["excluded_scope"][0]["grounding"] == "legacy_unverified"
    assert result["rows"] == []


@pytest.mark.parametrize("scope", ("other", "none", "proposed"))
def test_known_other_ownership_is_not_promoted_or_called_ambiguous(scope):
    first = _saved("first", "The first file is being discussed.", [])
    words = "A record is held for another file."
    outside = _record(material("evidence", "A record is reported elsewhere.", words,
                               scope=scope), "second", 1)
    result = _project(_matter(first, _saved("second", words, [outside])))

    assert result["state"] == result["coverage"]["state"] == "ok"
    assert result["rows"] == result["excluded_scope"] == []


def test_existing_ambiguous_linked_record_is_held_not_silently_assigned():
    words = "The amount is disputed. A receipt may exist."
    issue = _record(material("dispute", "Contested amount", "The amount is disputed."),
                    "first", 1)
    held = _record(material("evidence", "A receipt may exist.", "A receipt may exist.",
                            scope="uncertain", basis="uncertain", placement="disputes",
                            dispute_ids=(issue["id"],)), "first", 2)
    result = _project(_matter(_saved("first", words, [issue, held])))

    assert result["state"] == "ok" and result["coverage"]["state"] == "partial"
    assert result["by_dispute"][issue["id"]] == []
    assert result["excluded_scope"] == [held]


@pytest.mark.parametrize("relation", ("corrects", "withdraws"))
def test_saved_ambiguous_revision_cannot_retire_owned_material(relation):
    original_words = "The amount was four units."
    original = _record(material("circumstance", original_words, original_words,
                                placement="matter"), "first", 1)
    attempted_words = "That account may concern another file."
    attempted = _record(material(
        "circumstance", attempted_words, attempted_words, relation=relation,
        scope="uncertain", related_material_ids=(original["id"],),
        references=({"turn_id": "first", "role": "advocate",
                     "quoted": original_words},)), "second", 1)

    result = _project(_matter(_saved("first", original_words, [original]),
                              _saved("second", attempted_words, [attempted])))

    assert result["state"] == "ok" and result["coverage"]["state"] == "partial"
    assert result["rows"] == result["matter"] == [original]
    assert result["excluded_scope"] == [attempted]
    assert result["coverage"]["ambiguous_scope_items"] == 1
    assert any("without changing" in issue for issue in result["coverage"]["diagnostics"])


def test_ambiguous_revision_can_retire_an_already_held_target():
    first = "The amount may relate to another file."
    held = _record(material("circumstance", first, first, scope="uncertain"), "first", 1)
    latest = "Correction: it may be three units in that other file."
    corrected = _record(material(
        "circumstance", latest, latest, scope="uncertain", relation="corrects",
        related_material_ids=(held["id"],), references=({
            "turn_id": "first", "role": "advocate", "quoted": first},)), "second", 1)

    result = _project(_matter(_saved("first", first, [held]),
                              _saved("second", latest, [corrected])))

    assert result["state"] == "ok" and result["rows"] == []
    assert result["excluded_scope"] == [corrected]
    assert result["coverage"]["ambiguous_scope_items"] == 1


def test_public_ambiguous_revision_gets_feedback_and_cannot_withdraw_current_record(
        client, wired, monkeypatch):
    first = "The reported amount is four units."
    original = material("circumstance", first, first, placement="matter")
    latest = "That amount may instead concern another file, but I am not sure."
    attempted = material(
        "circumstance", latest, latest, scope="uncertain", relation="corrects",
        related_material_ids=("ownership-first:material:1",), references=({
            "turn_id": "ownership-first", "role": "advocate", "quoted": first},))

    class Repairing(ServiceModel):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            if prompt.operation == "extract_legal_details" and "validation_issue" in json.loads(
                    prompt.user):
                changes = result.data["changes"]
                result = replace(result, data={"new_items": [
                    {key: value for key, value in row.items()
                     if key not in ("relation", "related_material_ids")} for row in changes],
                    "changes": []})
            return result

    model = Repairing([plan(first, candidates=[original], opening=True,
                            material_purposes=("account_contribution",)),
                       plan(latest, candidates=[attempted],
                            material_purposes=("account_contribution",))])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, first, "ownership-first")
    assert opened.status_code == 200, opened.text

    changed = send(client, latest, "ownership-change", opened=opened.json())

    assert changed.status_code == 200, changed.text
    result = changed.json()
    assert result["metrics"]["llm_calls"] == 9
    assert result["material"][0]["relation"] == "new"
    assert result["material"][0]["matter_scope"] == "uncertain"
    record = client.get(f"/api/matters/{result['matter_id']}").json()["material_record"]
    assert record["state"] == "ok" and record["coverage"]["state"] == "partial"
    assert [row["id"] for row in record["rows"]] == ["ownership-first:material:1"]
    assert [row["id"] for row in record["excluded_scope"]] == ["ownership-change:material:1"]
    assert len(wired.store.load(result["matter_id"]).brain_chat) == 2


def test_public_boundary_single_assignment_preserves_fact_uncertainty_without_repair(
        client, wired, monkeypatch):
    words = "The charge is disputed. A receipt may be held."
    disputed = material("dispute", "Contested charge", "The charge is disputed.")
    uncertain = material("evidence", "A receipt may be held.", "A receipt may be held.",
                         scope="uncertain", basis="uncertain", placement="disputes",
                         dispute_ids=("scope-first:material:1",))

    model = ServiceModel([plan(words, candidates=[disputed, uncertain], opening=True,
                               material_purposes=("account_contribution",))])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    response = send(client, words, "scope-first")

    assert response.status_code == 200, response.text
    result = response.json()
    assert [row["matter_scope"] for row in result["material"]] == ["proposed", "proposed"]
    assert result["material"][1]["basis"] == "uncertain"
    assert result["metrics"]["llm_calls"] == 8
    assert sum(call.operation == "extract_legal_details" for call in model.material_calls) == 1
    assert len(wired.store.load(result["matter_id"]).brain_chat) == 1
    record = client.get(f"/api/matters/{result['matter_id']}").json()["material_record"]
    assert record["coverage"]["state"] == "ok"
    assert record["by_dispute"]["scope-first:material:1"][0]["basis"] == "uncertain"
