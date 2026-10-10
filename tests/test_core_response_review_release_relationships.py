"""Observable release/recovery relationships; scripted verdicts are not semantic proof."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from nm.core_engine.conversation import ConversationRefused, chat_matter_id
from nm.core_engine.response_writer import accept as accept_draft
from nm.core_engine.turn import saved_rows
from nm.shared.store_file_store import FileMatterStore
from tests.test_core_response_review import Model, positive, request, review, setup, validate
from tests.test_core_turn import ScriptedModel, run


pytestmark = pytest.mark.class_a


def use(source_id):
    assert isinstance(source_id, str)
    return {"source_id": source_id, "source_kind": "account"}


class MissingWorkModel(ScriptedModel):
    """Inject a precise omission verdict to exercise the actual correction owner."""
    message = ("Hello. The delivery date is unknown. Summarise the account. "
               "List the unanswered questions.")

    def __init__(self, *, reject_repair=False, consume_shape_correction=False):
        super().__init__()
        self.reject_repair = reject_repair
        self.consume_shape_correction = consume_shape_correction
        self.writes = 0

    def structured(self, prompt, schema, tier, **kwargs):
        result = super().structured(prompt, schema, tier, **kwargs)
        data = json.loads(prompt.user)
        if prompt.operation not in {"core_response_writer", "core_response_review"}:
            return result
        latest = data["original_context"]["latest"]

        def ref(quote):
            return {"source_id": latest["source_id"], "quote": quote}

        summary = ref("Summarise the account.")
        questions = ref("List the unanswered questions.")
        if prompt.operation == "core_response_writer":
            self.writes += 1
            address = {"source_id": latest["source_id"]}
            out = {"units": [
                {"kind": "greeting", "text": "Hello.",
                 "addresses": [deepcopy(address)], "uses": []},
                {"kind": "account", "text": "You report that the delivery date is unknown.",
                 "addresses": [deepcopy(address)], "uses": [use(latest["source_id"])]},
            ]}
            if self.consume_shape_correction and self.writes == 1:
                out["units"][0]["addresses"][0]["quote"] = "Words absent from the source"
            elif self.writes > 1 and not (self.reject_repair or self.consume_shape_correction):
                out["units"].append({"kind": "question", "text": "When was the delivery?",
                                     "addresses": [deepcopy(address)], "uses": []})
        else:
            units = data["complete_draft_proposal"]["units"]
            missing = len(units) == 2  # A fixture decision, never the production meaning check.
            out = {"verdict": "reject" if missing else "accept",
                "units": [{"unit_id": unit["id"], "verdict": "supported",
                           "reason": "Independently supported fixture unit."} for unit in units],
                "request_coverage": [
                    {"request": summary, "disposition": "addressed",
                     "unit_ids": [units[1]["id"]], "reason": "The attributed account is supplied."},
                    {"request": questions, "disposition": "missing" if missing else "addressed",
                     "unit_ids": [] if missing else [units[2]["id"]],
                     "reason": "The independent question work is absent." if missing
                               else "The requested question is supplied."}],
                "findings": [{"category": "omission", "unit_ids": [], "sources": [questions],
                    "mismatch": "The independent request for questions has no delivered result or limit."}]
                    if missing else []}
        return replace(result, data=out)


def test_missing_work_rewrites_once_preserving_supported_peer_then_rechecks_and_saves(tmp_path):
    store = FileMatterStore(tmp_path, key="synthetic-release-relationships")
    model = MissingWorkModel()
    response = run(store, model, message=model.message)
    assert response["metrics"]["llm_calls"] == 6
    assert response["metrics"]["draft_corrections"] == 1
    assert [name for name, _ in model.calls] == [
        "core_understanding", "core_research_plan", "core_response_writer",
        "core_response_review", "core_response_writer", "core_response_review"]
    first_review, rewrite, final_review = [model.calls[i][1] for i in (3, 4, 5)]
    original_peer = first_review["complete_draft_proposal"]["units"][1]
    assert final_review["complete_draft_proposal"]["units"][1] == original_peer
    assert rewrite["original_context"] == final_review["original_context"]
    assert rewrite["original_context"]["latest"]["text"] == model.message
    assert rewrite["correction"]["mismatch"][0]["unit_ids"] == []
    assert rewrite["correction"]["mismatch"][0]["sources"][0]["quote"] == "List the unanswered questions."
    assert len(rewrite["correction"]["rejected_draft"]["units"]) == 2
    assert "correction" not in final_review
    rows = saved_rows(store.load(chat_matter_id("owner", response["chat_id"])), "owner")
    assert len(rows) == 1 and rows[0]["message"] == model.message
    assert rows[0]["response"] == response
    assert rows[0]["records"] == {} and rows[0]["work"] == []


@pytest.mark.parametrize("settings,expected_calls", [
    ({"reject_repair": True}, 6), ({"consume_shape_correction": True}, 5)])
def test_missing_work_cannot_reset_shared_correction_or_save_after_terminal_rejection(
        tmp_path, settings, expected_calls):
    store = FileMatterStore(tmp_path, key="synthetic-release-relationships")
    model = MissingWorkModel(**settings)
    with pytest.raises(ConversationRefused) as error:
        run(store, model, message=model.message)
    assert error.value.code == "answer_withheld" and not error.value.retryable
    assert len(model.calls) == expected_calls
    assert not store.list_for("owner").matters
    with pytest.raises(ConversationRefused):
        run(store, model, message=model.message)
    assert len(model.calls) == expected_calls


def test_address_and_support_stay_distinct_for_review_and_correction_binding():
    earlier = {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
               "record_role": "original_account", "text": "I reported four crates."}
    ctx, record, sources, _ = setup(
        text="The corrected reported quantity is five crates. Summarise the correction.",
        history=[earlier])
    latest = {"source_id": ctx["latest"]["source_id"], "quote": None}
    proposal = {"units": [{"kind": "account", "text": "Your corrected reported quantity is five crates.",
                           "addresses": [{"source_id": latest["source_id"]}],
                           "uses": [use(earlier["source_id"])]}]}
    draft = accept_draft(proposal, ctx, sources)
    rejection = positive(draft, requests=[request(ctx, draft, disposition="missing")])
    rejection["verdict"] = "reject"
    rejection["units"][0]["verdict"] = "rejected"
    rejection["findings"] = [{"category": "grounding", "unit_ids": [draft["units"][0]["id"]],
        "sources": [latest], "mismatch": "The assertion selects the earlier quantity as support; "
        "the correction appears only in its address and is not a selected factual dependency."}]
    model = Model(rejection)
    rejected = review(model, ctx, record, sources, draft)
    shown = json.loads(model.calls[0][0].user)["complete_draft_proposal"]["units"][0]
    assert shown["addresses"] == [latest] and shown["uses"][0]["source_id"] == earlier["source_id"]
    assert not rejected["accepted"] and validate(rejected, ctx, record, sources, draft) == rejected
    corrected = deepcopy(proposal)
    corrected["units"][0]["uses"] = [use(latest["source_id"])]
    repaired = accept_draft(corrected, ctx, sources)
    accepted = review(Model(positive(repaired, requests=[request(ctx, repaired)])),
                      ctx, record, sources, repaired)
    assert accepted["accepted"] and accepted["bound_digest"] != rejected["bound_digest"]


def test_explicit_supported_limit_can_coexist_with_independent_read_only_result():
    text = ("I have not supplied the record. Assess its contents. "
            "Separately, list what information I should provide.")
    ctx, record, sources, _ = setup(text=text)
    identity = ctx["latest"]["source_id"]
    assess = {"source_id": identity, "quote": "Assess its contents."}
    information = {"source_id": identity, "quote": "list what information I should provide."}
    draft = accept_draft({"units": [
        {"kind": "limitation", "text": "The record has not been supplied here, so its contents "
         "cannot be assessed from this conversation.", "addresses": [{"source_id": identity}],
         "uses": [use(identity)]},
        {"kind": "next_step", "text": "Please provide the record and explain what you want its assessment to resolve.",
         "addresses": [{"source_id": identity}], "uses": []}]}, ctx, sources)
    expected = positive(draft, requests=[
        request(ctx, draft, request=assess, disposition="justified_limit",
                reason="The delivered unit explains the actual missing supplied source."),
        request(ctx, draft, request=information, unit_ids=[draft["units"][1]["id"]],
                reason="The independent information request has its own delivered result.")])
    execution = {"operations": [], "record_changes": [], "persistence": "not_yet_committed"}
    accepted = review(Model(expected), ctx, record, sources, draft, execution)
    assert accepted["accepted"] and validate(accepted, ctx, record, sources, draft, execution) == accepted


def test_paused_earlier_work_does_not_mechanically_require_resumption_for_a_social_close():
    earlier = {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
               "record_role": "original_account",
               "text": "Review the reported disagreement when I ask to continue."}
    ctx, record, sources, _ = setup(text="Thank you, goodbye.", history=[earlier])
    ctx["saved_work"] = [{"id": "pending-review", "state": "pending"}]
    draft = accept_draft({"units": [{"kind": "greeting", "text": "You're welcome. Goodbye.",
        "addresses": [{"source_id": ctx["latest"]["source_id"]}], "uses": []}]}, ctx, sources)
    model = Model(positive(draft))
    accepted = review(model, ctx, record, sources, draft)
    payload = json.loads(model.calls[0][0].user)
    assert payload["original_context"] == ctx
    assert accepted["accepted"] and accepted["proposal"]["request_coverage"] == []
    # This proves the mechanics do not invent work from a pending flag. The model
    # still owns whether this particular request/response is substantively adequate.
