"""Independent private-extraction review; scripted outputs prove contracts only."""
from copy import deepcopy
import json

import pytest

from nm.brain.release import prepare_release, render_saved_release
from nm.shared.model_port import SchemaViolation, Tier, Usage
from tests.test_brain_disputes_objectives import (
    ExtractionModel, extract, item, output, selection,
)
from tests.test_new_brain_release import ReviewModel, historical_v1_release


def unit(identity="dispute:1", verdict="supported", reason="none"):
    return {"unit_id": identity, "verdict": verdict, "reason": reason}


def review(*units, greeting=False, omissions=None):
    return {"greeting": greeting, "unit_reviews": list(units), "omissions": omissions or []}


def prepared(*, disputes=None, objectives=None, message="The supplier refuses delivery.", history=None):
    return extract(ExtractionModel(output(disputes=disputes, objectives=objectives)),
                   message=message, history=history)


def release(proposal=None, proof=None, label="information"):
    proposal = prepared(disputes=[item()]) if proposal is None else proposal
    proof = review(unit()) if proof is None else proof
    return prepare_release(ReviewModel(proof), proposal, label)


def test_new_extraction_has_one_independent_review_with_owned_passages_and_no_public_material():
    proposal = prepared(disputes=[item()])
    original = deepcopy(proposal)
    model = ReviewModel(review(unit()))
    saved = prepare_release(model, proposal, "information")
    assert saved["renderer_version"] == "disputes_objectives_release_v2"
    assert saved["state"] == "ready" and saved["service_status"] is None
    assert [row["text"] for row in saved["elements"]] == ["Message received."]
    assert saved["units"]["dispute:1"]["proposal"] == proposal["proposal"]["disputes"][0]
    assert saved["sources"] == proposal["sources"]
    assert proposal == original and len(model.calls) == 1
    prompt, schema, tier, limit = model.calls[0]
    assert tier is Tier.ROUTINE and limit > 0
    for section in ("Message:", "Purpose:", "Look for:", "Outcome:"):
        assert section in prompt.system
    payload = json.loads(prompt.user)
    assert payload["original_conversation"] == proposal["sources"]
    assert payload["preparation"] == proposal["proposal"]
    review_properties = schema["properties"]["unit_reviews"]["items"]["properties"]
    assert set(review_properties) == {"unit_id", "verdict", "reason"}
    omission_kind = schema["properties"]["omissions"]["items"]["properties"]["kind"]
    assert set(omission_kind["enum"]) == {"disputes", "objectives"}
    assert render_saved_release(saved) == saved
    assert len(model.calls) == 1


def test_focused_review_input_is_identical_under_every_label_while_saved_metadata_is_retained():
    proposal = prepared(disputes=[item()])
    dispatched = []
    for label in ("greeting", "information", "action", "mixed"):
        model = ReviewModel(review(unit()))
        saved = prepare_release(model, proposal, label)
        prompt, schema, tier, limit = model.calls[0]
        payload = json.loads(prompt.user)
        assert "proposed_label" not in payload
        assert payload["original_conversation"] == proposal["sources"]
        assert payload["preparation"] == proposal["proposal"]
        assert saved["label"] == label
        dispatched.append((prompt.system, payload, schema, tier, limit))
        assert len(model.calls) == 1
    assert all(call == dispatched[0] for call in dispatched[1:])


def test_legacy_material_preparation_keeps_its_label_in_the_unchanged_reviewer_payload():
    from tests.test_new_brain_release import prepared as legacy_prepared, review as legacy_review
    proposal = legacy_prepared()
    model = ReviewModel(legacy_review(greeting=True))
    saved = prepare_release(model, proposal, "greeting")
    assert json.loads(model.calls[0][0].user)["proposed_label"] == "greeting"
    assert saved["renderer_version"] == "initial_brain_release_v2"
    assert len(model.calls) == 1


@pytest.mark.parametrize("label", ["greeting", "information", "action", "mixed"])
def test_reviewed_empty_extraction_is_valid_without_fabricating_a_dispute_or_objective(label):
    proposal = prepared(message="Please explain the process.")
    saved = release(proposal, review(), label)
    assert saved["units"] == {} and saved["issues"] == []
    assert saved["state"] == "ready" and saved["service_status"] is None
    assert [row["text"] for row in saved["elements"]] == ["Message received."]
    assert render_saved_release(saved) == saved


def test_empty_greeting_uses_only_the_fixed_social_acknowledgement():
    saved = release(prepared(message="Hello."), review(greeting=True), "greeting")
    assert [row["text"] for row in saved["elements"]] == ["Hello. How can I help?"]
    assert saved["state"] == "ready" and saved["units"] == {}


def test_objective_is_independent_and_need_not_have_an_associated_dispute():
    message = "I want access restored."
    proposal = prepared(objectives=[item("Restoration of access", [selection()])], message=message)
    saved = release(proposal, review(unit("objective:1")))
    assert set(saved["units"]) == {"objective:1"}
    assert saved["units"]["objective:1"]["kind"] == "objectives"
    assert saved["state"] == "ready"
    assert [row["text"] for row in saved["elements"]] == ["Message received."]


def test_injected_scope_rejection_holds_work_instruction_without_erasing_a_distinct_matter_objective():
    """Proves handling of reviewer decisions, not detection of the semantic error."""
    message = "Review the agreement. I want the arrangement to end."
    proposal = prepared(objectives=[
        item("Review the agreement", [selection("current:p1")]),
        item("The user wants the arrangement to end", [selection("current:p2")]),
    ], message=message)
    checked = review(unit("objective:1", "unsupported", "scope"), unit("objective:2"))
    saved = release(proposal, checked, "action")
    assert saved["state"] == "partial" and saved["service_status"] is None
    assert saved["proof"]["unit_reviews"] == checked["unit_reviews"]
    assert set(saved["units"]) == {"objective:1", "objective:2"}
    assert saved["units"]["objective:2"]["proposal"]["description"] == (
        "The user wants the arrangement to end")
    assert [row["text"] for row in saved["elements"]] == ["Message received."]
    assert render_saved_release(saved) == saved


@pytest.mark.parametrize("latest", [
    "Thank you, that's all for now.",
    "Tell me how to use the search page.",
])
def test_injected_scope_rejection_of_revived_history_does_not_block_a_legitimate_empty_turn(latest):
    """Injected rejection tests scope handling; a live reviewer must establish meaning."""
    history = [{"role": "advocate", "text": "I want access restored."},
               {"role": "nm", "text": "Message received."}]
    revived = prepared(objectives=[item("Restoration of access", [
        selection("history_1:p1"), selection("current:p1", "context")])],
        message=latest, history=history)
    rejected = release(revived, review(unit("objective:1", "unsupported", "scope")))
    assert rejected["state"] == "withheld" and rejected["elements"] == []
    assert rejected["proof"]["unit_reviews"][0]["reason"] == "scope"
    empty = prepared(message=latest, history=history)
    accepted = release(empty, review())
    assert accepted["state"] == "ready" and accepted["units"] == {}
    assert [row["text"] for row in accepted["elements"]] == ["Message received."]
    assert accepted["sources"] == rejected["sources"] == empty["sources"]
    assert render_saved_release(accepted) == accepted


def test_review_examines_earlier_original_support_and_nm_context_without_treating_nm_as_evidence():
    history = [{"role": "advocate", "text": "I want access restored, not ownership."},
               {"role": "nm", "text": "You seek ownership."}]
    message = "Review your earlier interpretation."
    proposal = prepared(objectives=[item("Restoration of access", [
        selection("history_1:p1"),
        selection("history_2:p1", "context"),
        selection("current:p1", "context")])], message=message, history=history)
    model = ReviewModel(review(unit("objective:1")))
    saved = prepare_release(model, proposal, "action")
    assert saved["state"] == "ready"
    assert saved["units"]["objective:1"]["proposal"]["passages"][1]["purpose"] == "context"
    assert json.loads(model.calls[0][0].user)["original_conversation"] == proposal["sources"]
    assert render_saved_release(saved) == saved


def test_selected_repeated_passage_keeps_its_owned_occurrence_through_review_and_replay():
    message = "No!No!"
    proposal = prepared(disputes=[item("The second refusal", [selection("current:p2")])], message=message)
    saved = release(proposal)
    chosen = saved["units"]["dispute:1"]["proposal"]["passages"][0]
    assert chosen == {"source_id": "current", "quote": "No!", "start": 3, "end": 6,
                      "passage_id": "current:p2", "purpose": "support"}
    assert render_saved_release(saved) == saved
    assert chosen == proposal["proposal"]["disputes"][0]["passages"][0]


def test_original_unicode_and_cross_partition_qualification_reach_independent_review_unchanged():
    message = "  प्रवेश रोका गया। They denied access;\nI do not know who authorised it.  "
    proposal = prepared(disputes=[item("Reported refusal of access; authorisation is unknown", [
        selection("current:p1"), selection("current:p2")], "Authorisation is unknown.")], message=message)
    model = ReviewModel(review(unit()))
    saved = prepare_release(model, proposal, "information")
    passages = saved["units"]["dispute:1"]["proposal"]["passages"]
    assert "".join(row["quote"] for row in passages) == message
    assert all(message[row["start"]:row["end"]] == row["quote"] for row in passages)
    payload = json.loads(model.calls[0][0].user)
    assert payload["original_conversation"][-1]["message"]["text"] == message
    assert render_saved_release(saved) == saved


def test_mechanically_held_peer_is_preserved_privately_without_erasing_supported_extraction():
    proposal = prepared(disputes=[item(description=""), item()])
    saved = release(proposal, review(unit("dispute:2")))
    assert saved["state"] == "partial" and saved["service_status"] is None
    assert saved["issues"] == proposal["issues"]
    assert set(saved["units"]) == {"dispute:2"}
    assert [row["text"] for row in saved["elements"]] == ["Message received."]
    assert render_saved_release(saved) == saved


def test_semantically_rejected_peer_remains_private_and_does_not_erase_the_supported_peer():
    proposal = prepared(disputes=[item(), item(description="Unsupported interpretation")])
    checked = review(unit(), unit("dispute:2", "unsupported", "unsupported_addition"))
    saved = release(proposal, checked)
    assert saved["state"] == "partial" and saved["service_status"] is None
    assert saved["proof"] == checked
    assert [row["text"] for row in saved["elements"]] == ["Message received."]


@pytest.mark.parametrize("proposal,checked", [
    (prepared(disputes=[item()]), review(unit(verdict="unsupported", reason="contradiction"))),
    (prepared(disputes=[item()]), review(unit(verdict="unresolved", reason="unresolved_reference"))),
    (prepared(disputes=[item(description="")]), review()),
    (prepared(), review(omissions=[{"source_id": "current", "kind": "objectives"}])),
])
def test_rejected_or_unexamined_content_cannot_masquerade_as_reviewed_empty_extraction(proposal, checked):
    saved = release(proposal, checked)
    assert saved["state"] == "withheld" and saved["elements"] == []
    assert saved["service_status"] == "A response could not be prepared for this message."
    assert render_saved_release(saved) == saved


def test_significant_omission_leaves_valid_work_private_and_explicitly_incomplete():
    checked = review(unit(), omissions=[{"source_id": "current", "kind": "objectives"}])
    saved = release(proof=checked)
    assert saved["state"] == "partial" and saved["service_status"] is None
    assert saved["proof"]["omissions"] == checked["omissions"]


@pytest.mark.parametrize("alter", [
    lambda proof: proof.update(reply="I completed the matter."),
    lambda proof: proof["unit_reviews"][0].update(source_ids=["current"]),
    lambda proof: proof["unit_reviews"][0].update(unit_id="dispute:99"),
    lambda proof: proof["unit_reviews"].clear(),
    lambda proof: proof["unit_reviews"].append(deepcopy(proof["unit_reviews"][0])),
    lambda proof: proof["unit_reviews"][0].update(reason="contradiction"),
    lambda proof: proof["unit_reviews"][0].update(verdict="unsupported"),
    lambda proof: proof["omissions"].append({"source_id": "foreign", "kind": "disputes"}),
    lambda proof: proof["omissions"].append({"source_id": "current", "kind": "actions"}),
    lambda proof: proof["omissions"].append({"source_id": "current", "kind": "material"}),
])
def test_invalid_review_is_one_typed_rejection_without_a_private_retry(alter):
    checked = review(unit())
    alter(checked)
    model = ReviewModel(checked)
    with pytest.raises(SchemaViolation) as caught:
        prepare_release(model, prepared(disputes=[item()]), "information")
    assert len(model.calls) == 1
    assert caught.value.usage == Usage(10, 5, 0)


def test_nm_context_cannot_be_the_original_source_of_an_extraction_omission():
    proposal = prepared(disputes=[item()], history=[{"role": "nm", "text": "Earlier model interpretation."}])
    checked = review(unit(), omissions=[{"source_id": "history_1", "kind": "disputes"}])
    with pytest.raises(SchemaViolation):
        release(proposal, checked)


@pytest.mark.parametrize("alter", [
    lambda saved: saved.update(renderer_version="future_release_v1"),
    lambda saved: saved.update(renderer_version="initial_brain_release_v2"),
    lambda saved: saved.update(renderer_version="disputes_objectives_release_v1"),
    lambda saved: saved["units"]["dispute:1"]["proposal"]["passages"][0].pop("passage_id"),
    lambda saved: saved["units"]["dispute:1"]["proposal"]["passages"][0].update(start=1),
    lambda saved: saved["units"]["dispute:1"]["proposal"]["passages"][0].update(end=1),
    lambda saved: saved["units"]["dispute:1"]["proposal"]["passages"][0].update(quote="The supplier delivered."),
    lambda saved: saved["units"]["dispute:1"]["proposal"].update(source_ids=["foreign"]),
    lambda saved: saved["sources"][-1]["message"].update(text="A different original message."),
    lambda saved: saved["proof"]["unit_reviews"][0].update(unit_id="foreign:1"),
    lambda saved: saved["elements"][0].update(text="The dispute has been resolved."),
])
def test_new_saved_release_revalidates_owned_exact_passages_and_closed_public_expression(alter):
    saved = release()
    alter(saved)
    with pytest.raises(SchemaViolation):
        render_saved_release(saved)


def test_legacy_v1_and_v2_snapshots_remain_separate_replay_contracts():
    from tests.test_new_brain_release import prepared as legacy_prepared, review as legacy_review
    v1 = historical_v1_release("The draft is unsigned.", information=True)
    v2 = prepare_release(ReviewModel(legacy_review(greeting=True)), legacy_prepared(), "greeting")
    assert v2["renderer_version"] == "initial_brain_release_v2"
    for saved in (v1, v2):
        before = deepcopy(saved)
        assert render_saved_release(saved) == before
        assert saved == before


def historical_focused_v1_release():
    """Old raw-quote extraction and its explicit old release envelope."""
    from nm.brain.disputes_objectives import _prepare
    message = "The supplier refuses delivery."
    sources = [{"id": "current", "message": {"role": "advocate", "text": message}}]
    legacy = _prepare({"disputes": [{"description": "Supplier's refusal to deliver",
        "passages": [{"source_id": "current", "quote": message, "purpose": "support"}],
        "uncertainty": None}], "objectives": []}, sources)
    assert legacy["contract"] == "disputes_objectives_v1"
    return {"renderer_version": "disputes_objectives_release_v1", "label": "information",
            "sources": legacy["sources"],
            "units": {"dispute:1": {"kind": "disputes", "proposal": legacy["proposal"]["disputes"][0]}},
            "issues": [], "proof": review(unit()), "elements": [{
                "kind": "finding", "text": "Message received.", "thread": None, "by_when": None,
                "no_deadline_reason": None, "signal": "none", "collapsible": False,
                "disclosure": False, "refs": [], "source": None, "section": "answer"}],
            "service_status": None, "state": "ready"}


def test_historical_focused_raw_quote_release_replays_without_upgrade_or_new_selections():
    saved = historical_focused_v1_release()
    before = deepcopy(saved)
    assert render_saved_release(saved) == before
    assert saved == before
    assert "passage_id" not in saved["units"]["dispute:1"]["proposal"]["passages"][0]


@pytest.mark.parametrize("alter", [
    lambda saved: saved.update(renderer_version="disputes_objectives_release_v2"),
    lambda saved: saved["units"]["dispute:1"]["proposal"]["passages"][0].update(passage_id="current:p1"),
    lambda saved: saved["units"]["dispute:1"]["proposal"]["passages"][0].update(start=1),
])
def test_historical_focused_quote_format_cannot_be_silently_upgraded_or_rebound(alter):
    saved = historical_focused_v1_release()
    alter(saved)
    with pytest.raises(SchemaViolation):
        render_saved_release(saved)


def test_unknown_saved_version_is_rejected_even_when_extraction_is_empty():
    saved = release(prepared(message="Please explain the process."), review())
    assert saved["units"] == {}
    saved["renderer_version"] = "future_disputes_objectives_release_v9"
    with pytest.raises(SchemaViolation):
        render_saved_release(saved)


@pytest.mark.parametrize("nonempty", [False, True])
def test_malformed_extraction_contract_is_refused_before_review_dispatch(nonempty):
    proposal = prepared(disputes=[item()] if nonempty else [])
    proposal["contract"] = "future_disputes_objectives_v2"
    model = ReviewModel(review(unit()))
    with pytest.raises(SchemaViolation):
        prepare_release(model, proposal, "information")
    assert model.calls == []
