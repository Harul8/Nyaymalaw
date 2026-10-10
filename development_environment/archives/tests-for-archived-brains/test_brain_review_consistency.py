"""Inconsistent source checks repair the review, not the already checked writer."""
from __future__ import annotations

from copy import deepcopy

from nm.brain.continuation_verification import verify_continuation
from nm.brain.turn import chat_matter_id
from tests.brain_continuation_fixture import reviewed_verdicts
from tests.test_brain_continuation import ContinuationModel, _operation_names, unit, verdict
from tests.test_brain_continuation_service import PublicContinuationModel, send
from tests.test_brain_turn import plan


def inconsistent(payload, index):
    data = reviewed_verdicts(payload, verdict(*(row["request_index"] for row in payload["units"])))
    check = next(row for row in data["verdicts"] if row["request_index"] == index)
    check["block_checks"][-1].update(
        requires_legal_support=True, verdict="accept",
        reason="The proposed support flag and acceptance require a consistent decision.")
    return data


def test_inconsistent_accept_repairs_only_pending_review_without_rewriting_valid_peer():
    good, pending = unit(0), unit(1)
    original = deepcopy(pending)

    def corrected(payload):
        assert payload["units"] == [original]
        assert payload["validation_issues"][0]["request_index"] == 1
        issue = payload["validation_issues"][0]["issue"]
        assert "limit-1" in issue and "cannot accept" in issue
        assert "selected checked legal passage" in issue
        return verdict(1)

    model = ContinuationModel([lambda payload: inconsistent(payload, 1), corrected])
    result = verify_continuation(model, input_payload={
        "legal_sources": {}, "progress": {"state": "ok", "rows": []}}, units=(good, pending))

    assert result.decisions[0][0] is result.decisions[1][0] is True
    assert result.unavailable == ()
    assert _operation_names(model) == ["verify_continuation", "verify_continuation"]
    assert pending == original


def test_repeated_inconsistent_accept_is_unavailable_and_preserves_valid_peer():
    model = ContinuationModel([lambda payload: inconsistent(payload, 1)] * 2)
    result = verify_continuation(model, input_payload={
        "legal_sources": {}, "progress": {"state": "ok", "rows": []}},
                                 units=(unit(), unit(1)))

    assert set(result.decisions) == {0} and result.decisions[0][0] is True
    assert result.unavailable == (1,)
    assert len(model.calls) == 2
    assert [row["request_index"] for row in model.calls[-1][1]["units"]] == [1]


def test_missing_legal_support_with_explicit_block_rejection_is_a_complete_review():
    def rejected(payload):
        data = inconsistent(payload, 0)
        data["verdicts"][0]["block_checks"][-1]["verdict"] = "reject"
        return data

    model = ContinuationModel([rejected])
    result = verify_continuation(model, input_payload={
        "legal_sources": {}, "progress": {"state": "ok", "rows": []}}, units=(unit(),))

    assert result.decisions[0][0] is False and result.unavailable == ()
    assert "actual selected checked legal passage" in result.decisions[0][1]
    assert len(model.calls) == 1


def test_public_consistent_review_repairs_no_user_input_or_writer_and_replay_is_free(
        client, wired, monkeypatch):
    words = "I report holding two dated records. Summarise that account without legal assessment."
    proposed = unit(text="You report holding two dated records.")
    proposed["blocks"] = [proposed["blocks"][0], proposed["blocks"][2]]
    proposed["blocks"][1]["text"] = "This factual summary does not deliver a legal assessment."
    proposed.update(questions=[], sufficiency={"status": "complete", "block_id": "account-0"})
    model = PublicContinuationModel(
        [plan(words, step="legal_work")], [{"units": [proposed]}],
        checks=[lambda payload: inconsistent(payload, 0), verdict(0)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    answer = send(client, words, "review-contract-repair")
    replay = send(client, words, "review-contract-repair")

    assert answer["metrics"]["llm_calls"] == 4 and replay["metrics"]["llm_calls"] == 0
    assert [operation for operation, _ in model.calls] == [
        "interpret_conversation", "continue_conversation", "verify_continuation",
        "verify_continuation"]
    assert answer["continuation"]["coverage"][0]["state"] == "ok"
    assert [block["text"] for block in answer["elements"]] == [
        'Your message includes: “I report holding two dated records.”',
        "The requested conclusion remains unresolved on the supplied support."]
    execution = answer["material_coverage"]["execution"]
    assert execution["display"] is None and execution["record_changes"] == []
    assert answer["continuation"]["units"][0]["blocks"][0]["evidence_expression"] == {
        "operator": "source_account", "source_ids": ["L1"], "record_ids": [], "focus": "none"}
    assert "validation_issues" in model.calls[-1][1]
    saved = wired.store.load(chat_matter_id("adv_demo", answer["chat_id"]))
    assert len(saved.brain_chat) == 1 and saved.brain_chat[0]["message"] == words
    assert saved.brain_chat[0]["elements"] == answer["elements"]
