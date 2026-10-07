"""Scripted review tests prove release mechanics, not semantic accuracy."""
from copy import deepcopy
import json

import pytest

from nm.brain.release import prepare_release, render_saved_release
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ContextOverflow, ModelError, ModelResult, SchemaViolation, Tier, Usage


class ReviewModel:
    def __init__(self, result, *, budget=30000, complete=Completion.COMPLETE):
        self.result, self.budget, self.complete = result, budget, complete
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.ROUTINE
        return self.budget

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema, tier, max_tokens))
        return ModelResult(text=None, data=deepcopy(self.result), tier=tier,
                           provider="offline", model="offline", usage=Usage(10, 5, 0),
                           latency_ms=7, completion=self.complete)


def prepared(message="Hello.", *, material=False, action=False, history=(), draft="Hello."):
    sources = [{"id": f"history_{i}", "message": deepcopy(row)}
               for i, row in enumerate(history, start=1)]
    sources.append({"id": "current", "message": {"role": "advocate", "text": message}})
    return {"state": "prepared_unreviewed", "sources": sources, "issues": [],
            "proposal": {"reply_draft": draft, "material": [{
                "id": "material:1", "state": "proposed", "source_ids": ["current"],
                "understanding": "The user reports receiving an unsigned draft.",
            }] if material else [], "actions": [{
                "id": "action:1", "state": "planned", "source_ids": ["current"],
                "requested_outcome": "Explain the wording.", "activities": ["Read and explain it."],
                "constraints": ["Do not send anything."], "missing_information": [],
            }] if action else []}}


def unit(identity, *, verdict="supported", sources=None, reason="none"):
    return {"unit_id": identity, "verdict": verdict,
            "source_ids": ["current"] if sources is None else sources, "reason": reason}


def review(*units, greeting=False, omissions=None):
    return {"greeting": greeting, "unit_reviews": list(units), "omissions": omissions or []}


def test_greeting_is_code_owned_and_draft_completion_can_never_be_rendered():
    model = ReviewModel(review(greeting=True))
    proposal = prepared(draft="I filed your case and verified all evidence.")
    saved = prepare_release(model, proposal, "greeting")
    assert saved["state"] == "ready" and saved["service_status"] is None
    assert [row["text"] for row in saved["elements"]] == ["Hello. How can I help?"]
    assert "filed your case" not in json.dumps(saved)
    assert len(model.calls) == 1
    prompt, schema, tier, limit = model.calls[0]
    assert prompt.operation == "review_prepared_response" and tier is Tier.ROUTINE
    assert limit > 0 and set(schema["properties"]) == {"greeting", "unit_reviews", "omissions"}
    payload = json.loads(prompt.user)
    assert list(payload)[0] == "original_conversation"
    assert payload["preparation"]["reply_draft"] == proposal["proposal"]["reply_draft"]
    assert render_saved_release(saved) == saved
    assert len(model.calls) == 1  # Reopening is deterministic and makes no model call.


def test_information_renders_exact_original_words_attributed_to_the_user():
    message = "  I received a draft.\nIt is not signed—so far as I know.  "
    proposal = prepared(message, material=True,
                        history=[{"role": "nm", "text": "Please describe what you received."}])
    model = ReviewModel(review(unit("material:1")))
    result = prepare_release(model, proposal, "information")
    assert [row["text"] for row in result["elements"]] == [f"You reported: “{message}”"]
    assert "The user reports receiving" not in result["elements"][0]["text"]
    payload = json.loads(model.calls[0][0].user)
    assert payload["original_conversation"] == proposal["sources"]
    assert result["sources"] == proposal["sources"]


def test_action_is_original_request_and_explicitly_not_execution():
    message = "Explain this wording. Do not send it to anyone."
    result = prepare_release(ReviewModel(review(unit("action:1"))),
                             prepared(message, action=True), "action")
    assert result["elements"][0]["text"] == f"Your requested work: “{message}”"
    assert result["elements"][1]["text"] == (
        "This step proposes work only; it does not carry out the requested activities.")
    assert not any("Read and explain it." in row["text"] for row in result["elements"])


def test_unsupported_peer_is_held_while_supported_peer_survives():
    proposal = prepared("I received a draft. Explain it.", material=True, action=True)
    checked = review(unit("material:1"), unit("action:1", verdict="unsupported", reason="restriction"))
    result = prepare_release(ReviewModel(checked), proposal, "mixed")
    assert len(result["elements"]) == 1 and result["state"] == "partial"
    assert result["service_status"] == "Some of this message could not be prepared for a response."
    assert render_saved_release(result) == result


def test_rejected_review_returns_service_status_not_a_fabricated_answer():
    result = prepare_release(ReviewModel(review(unit("material:1", verdict="unsupported",
                                                  reason="contradiction"))),
                             prepared("The draft was not signed.", material=True), "information")
    assert result["state"] == "withheld" and result["elements"] == []
    assert result["service_status"] == "A response could not be prepared for this message."


def test_omission_keeps_supported_work_without_claiming_complete_coverage():
    proposal = prepared("I received a draft. Also compare the revised wording.", material=True)
    checked = review(unit("material:1"), omissions=[{"source_id": "current", "kind": "action"}])
    result = prepare_release(ReviewModel(checked), proposal, "information")
    assert result["state"] == "partial" and result["service_status"]
    assert result["proof"]["omissions"] == checked["omissions"]


@pytest.mark.parametrize("alter", [
    lambda proof: proof.update(reply="I have completed it."),
    lambda proof: proof["unit_reviews"][0].update(text="Changed quotation"),
    lambda proof: proof["unit_reviews"][0].update(source_ids=["foreign"]),
    lambda proof: proof["unit_reviews"][0].update(unit_id="foreign:1"),
    lambda proof: proof["unit_reviews"].clear(),
    lambda proof: proof["unit_reviews"].append(deepcopy(proof["unit_reviews"][0])),
    lambda proof: proof["unit_reviews"][0].update(reason="contradiction"),
    lambda proof: proof["unit_reviews"][0].update(source_ids=[]),
    lambda proof: proof["omissions"].append({"source_id": "foreign", "kind": "action"}),
])
def test_invalid_review_is_rejected_without_a_private_retry(alter):
    checked = review(unit("material:1"))
    alter(checked)
    model = ReviewModel(checked)
    with pytest.raises(SchemaViolation) as caught:
        prepare_release(model, prepared("I received a draft.", material=True), "information")
    assert len(model.calls) == 1
    assert caught.value.usage == Usage(10, 5, 0) and caught.value.latency_ms == 7


def test_nm_context_is_not_rendered_as_advocate_source():
    proposal = prepared("That is not right.", material=True,
                        history=[{"role": "nm", "text": "The document was signed."}])
    proposal["proposal"]["material"][0]["source_ids"] = ["history_1", "current"]
    with pytest.raises(SchemaViolation, match="NM wording"):
        prepare_release(ReviewModel(review(unit("material:1", sources=["history_1"]))),
                        proposal, "information")


def test_follow_up_action_needs_current_request_even_when_prior_request_is_exact():
    proposal = prepared("Please continue.", action=True,
                        history=[{"role": "advocate", "text": "Explain the draft."}])
    proposal["proposal"]["actions"][0]["source_ids"] = ["history_1", "current"]
    with pytest.raises(SchemaViolation, match="current request"):
        prepare_release(ReviewModel(review(unit("action:1", sources=["history_1"]))), proposal, "action")
    result = prepare_release(ReviewModel(review(unit("action:1", sources=["history_1", "current"]))),
                             proposal, "action")
    assert "Explain the draft." in result["elements"][0]["text"]
    assert "Please continue." in result["elements"][1]["text"]


def test_duplicate_source_selection_is_harmless_and_does_not_duplicate_public_text():
    result = prepare_release(ReviewModel(review(unit("material:1", sources=["current", "current"]))),
                             prepared("I received a draft.", material=True), "information")
    assert len(result["elements"]) == 1
    assert result["proof"]["unit_reviews"][0]["source_ids"] == ["current"]


@pytest.mark.parametrize("alter", [
    lambda saved: saved.update(renderer_version="future_version"),
    lambda saved: saved.update(reply="I have completed the task."),
    lambda saved: saved["elements"][0].update(text="Different original words"),
    lambda saved: saved["sources"][-1]["message"].update(text="Different original words"),
    lambda saved: saved.update(state="completed"),
    lambda saved: saved.update(service_status="Everything is saved and verified."),
    lambda saved: saved["units"]["material:1"].update(kind=[]),
])
def test_replay_refuses_changed_source_display_contract_or_status(alter):
    saved = prepare_release(ReviewModel(review(unit("material:1"))),
                            prepared("I received a draft.", material=True), "information")
    alter(saved)
    with pytest.raises(SchemaViolation):
        render_saved_release(saved)


def test_context_overflow_is_not_trimmed_and_fails_before_dispatch():
    model = ReviewModel(review(greeting=True), budget=20)
    with pytest.raises(ContextOverflow):
        prepare_release(model, prepared(), "greeting")
    assert model.calls == []


def test_incomplete_review_cannot_be_salvaged_or_privately_retried():
    model = ReviewModel(review(greeting=True), complete=Completion.NOT_ESTABLISHED)
    with pytest.raises(ModelError) as caught:
        prepare_release(model, prepared(), "greeting")
    assert caught.value.usage == Usage(10, 5, 0) and len(model.calls) == 1


def test_untrusted_source_context_fails_before_model_dispatch():
    proposal = prepared()
    proposal["sources"][-1]["message"]["role"] = "nm"
    model = ReviewModel(review(greeting=True))
    with pytest.raises(SchemaViolation):
        prepare_release(model, proposal, "greeting")
    assert model.calls == []
