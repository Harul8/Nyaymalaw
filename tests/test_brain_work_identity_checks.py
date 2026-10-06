"""Durable work identities follow their scoped meaning, not general approval."""
from __future__ import annotations

from copy import deepcopy

import pytest

from nm.brain.continuation_verification import verify_continuation
from nm.brain.turn import chat_matter_id
from nm.brain.work_state import project_work
from tests.brain_continuation_fixture import reviewed_verdicts
from tests.test_brain_continuation import ContinuationModel, _continue, unit, verdict
from tests.test_brain_continuation_service import PublicContinuationModel, send
from tests.test_brain_turn import plan


def account(text, *, existing=""):
    proposed = unit(text=text)
    proposed["blocks"] = [proposed["blocks"][0]]
    proposed.update(questions=[], sufficiency={"status": "complete", "block_id": "account-0"},
                    work={"existing_id": existing, "create": not bool(existing)})
    return proposed


def check_payload(model, proposed, *, questions=()):
    return verify_continuation(model, input_payload={
        "legal_sources": {}, "progress": {"state": "ok", "rows": list(questions)},
    }, units=(proposed,))


@pytest.mark.parametrize("fault", ["wrong_task", "changed_scope", "missing_transition",
                                  "wrong_transition_status", "missing_question",
                                  "duplicate_question"])
def test_unread_identity_checks_retry_only_the_checker_once(fault):
    proposed = unit()
    proposed["work"] = {"existing_id": "task", "create": False}
    proposed["questions"][0]["existing_id"] = "question"
    proposed["progress_updates"] = [{
        "target_id": "task", "status": "complete", "block_id": "account-0",
        "span_ids": [], "reason": "The full task was delivered.",
    }]
    progress = [{"id": "question", "kind": "question", "status": "pending"}]

    def incomplete(payload):
        data = reviewed_verdicts(payload, verdict(0))
        row = data["verdicts"][0]
        if fault == "wrong_task":
            row["work_check"]["existing_id"] = "another-task"
        elif fault == "changed_scope":
            row["work_check"].pop("scope_preserved")
        elif fault == "missing_transition":
            row["progress_checks"] = []
        elif fault == "wrong_transition_status":
            row["progress_checks"][0]["status"] = "pending"
        elif fault == "missing_question":
            row["question_resolutions"] = []
        else:
            row["question_resolutions"] *= 2
        return data

    model = ContinuationModel([incomplete, verdict(0)])
    result = check_payload(model, proposed, questions=progress)

    assert result.decisions[0][0] is True and result.unavailable == ()
    assert len(model.calls) == 2
    assert [prompt.operation for prompt, _ in model.calls] == [
        "verify_continuation", "verify_continuation"]
    assert model.calls[1][1]["validation_issues"]


@pytest.mark.parametrize("check_field", ["scope_preserved", "result_supported"])
def test_failed_progress_check_overrides_whole_unit_acceptance(check_field):
    proposed = account("Only one part of the requested comparison has been delivered.")
    proposed["progress_updates"] = [{
        "target_id": "$work", "status": "complete", "block_id": "account-0",
        "span_ids": [], "reason": "The smaller step was answered.",
    }]

    def conflicting(payload):
        data = reviewed_verdicts(payload, verdict(0))
        data["verdicts"][0]["progress_checks"][0].update({
            check_field: False,
            "reason": "A smaller delivered step does not complete the task's full scope.",
        })
        return data

    model = ContinuationModel([conflicting])
    result = check_payload(model, proposed)

    assert result.decisions[0][0] is False
    assert "full scope" in result.decisions[0][1]
    assert len(model.calls) == 1


def test_changed_question_identity_overrides_general_acceptance_without_verbatim_rule():
    proposed = unit(question="Which record describes the transfer?")
    proposed["questions"][0]["existing_id"] = "question"

    def conflicting(payload):
        data = reviewed_verdicts(payload, verdict(0))
        data["verdicts"][0]["proposal_checks"][0].update(
            identity_preserved=False,
            reason="The saved question asks who holds the object; this asks for a record.")
        return data

    model = ContinuationModel([conflicting])
    result = check_payload(model, proposed, questions=[{
        "id": "question", "kind": "question", "status": "pending"}])

    assert result.decisions[0][0] is False
    assert "who holds" in result.decisions[0][1]
    assert len(model.calls) == 1


def test_supported_question_rephrasing_reuses_identity_without_exact_text_matching():
    proposed = unit(question="Which person holds those objects at present?")
    proposed["questions"][0]["existing_id"] = "question"
    model = ContinuationModel([verdict(0)])
    result = check_payload(model, proposed, questions=[{
        "id": "question", "kind": "question", "status": "pending",
        "text": "Who currently has custody of the objects?",
        "purpose": "Identify present custody.",
    }])

    assert result.decisions[0][0] is True and len(model.calls) == 1


def test_checked_resolution_cannot_silently_leave_an_answered_question_pending():
    proposed = account("You report that the recipient now holds the objects.")

    def identify_omitted_transition(payload):
        data = reviewed_verdicts(payload, verdict(0))
        data["verdicts"][0]["question_resolutions"] = [{
            "question_id": "question", "status": "complete", "block_id": "account-0",
        }]
        return data

    model = ContinuationModel([identify_omitted_transition])
    result = check_payload(model, proposed, questions=[{
        "id": "question", "kind": "question", "status": "pending",
        "text": "Who holds the objects?",
    }])

    assert result.decisions[0][0] is False
    assert "include the attributed status change" in result.decisions[0][1]
    assert len(model.calls) == 1


def test_mislinked_saved_task_scope_overrides_general_acceptance():
    proposed = account("You request a different outcome.", existing="task")

    def conflicting(payload):
        data = reviewed_verdicts(payload, verdict(0))
        data["verdicts"][0]["work_check"].update(
            scope_preserved=False,
            reason="The requested new outcome does not belong to the selected saved task.")
        return data

    model = ContinuationModel([conflicting])
    result = check_payload(model, proposed)

    assert result.decisions[0][0] is False
    assert "saved task" in result.decisions[0][1]
    assert len(model.calls) == 1


def test_public_narrow_answer_preserves_broader_task_after_bounded_writer_repair(
        client, wired, monkeypatch):
    first_words = "Prepare a comparison of all records when they are available."
    later_words = "For now, tell me only which record is promised: the receipt is promised."
    opening = plan(first_words, step="legal_work")
    later = plan(later_words, step="legal_work", relation="continues")
    initial = account("You request a comparison when the records become available.")
    identity = {}

    def narrow_with_false_completion(payload):
        identity["task"] = payload["progress"]["rows"][0]["id"]
        response = account("You report that the receipt is promised.", existing=identity["task"])
        response["progress_updates"] = [{
            "target_id": "$work", "status": "complete", "block_id": "account-0",
            "span_ids": [], "reason": "The immediate factual question is answered.",
        }]
        return {"units": [response]}

    def reject_broad_completion(payload):
        data = reviewed_verdicts(payload, verdict(0))
        data["verdicts"][0]["progress_checks"][0].update(
            result_supported=False,
            reason="Identifying a promised record does not deliver the requested full comparison.")
        return data

    def repair(payload):
        assert "full comparison" in payload["correction"]["validation_issues"][0]["issue"]
        return {"units": [account("You report that the receipt is promised.",
                                  existing=identity["task"])]}

    model = PublicContinuationModel(
        [opening, later], [{"units": [initial]}, narrow_with_false_completion, repair],
        checks=[verdict(0), reject_broad_completion, verdict(0)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    first = send(client, first_words, "broad-task")
    saved_id = chat_matter_id("adv_demo", first["chat_id"])
    original = deepcopy(wired.store.load(saved_id).brain_chat[0])
    answer = send(client, later_words, "narrow-answer", opened=first)
    replay = send(client, later_words, "narrow-answer", opened=first)

    assert first["metrics"]["llm_calls"] == 3
    assert answer["metrics"]["llm_calls"] == 5 and replay["metrics"]["llm_calls"] == 0
    saved = wired.store.load(saved_id)
    assert saved.brain_chat[0] == original and len(saved.brain_chat) == 2
    progress = project_work(saved)
    assert len(progress["rows"]) == 1 and progress["rows"][0]["status"] == "pending"
    assert progress["rows"][0]["text"] == first_words
    assert answer["continuation"]["units"][0]["sufficiency"]["status"] == "complete"


def test_public_answered_question_is_retired_and_different_need_gets_own_identity(
        client, wired, monkeypatch):
    first_words = "Two objects have been moved. Help clarify who holds them."
    later_words = "The courier now holds both objects. Which record describes the transfer?"
    opening = plan(first_words, step="legal_work")
    later = plan(later_words, step="legal_work", relation="continues")
    initial = unit(text="You report two moved objects.", question="Who holds the objects now?")
    initial["questions"][0]["purpose"] = "Identify current custody."
    identities = {}

    def changed_need(payload):
        rows = payload["progress"]["rows"]
        identities["task"] = next(row["id"] for row in rows if row["kind"] == "task")
        identities["question"] = next(row["id"] for row in rows if row["kind"] == "question")
        response = unit(text="You report that the courier holds both objects.",
                        question="Which record describes the transfer?")
        response["work"] = {"existing_id": identities["task"], "create": False}
        response["questions"][0].update(existing_id=identities["question"],
                                         purpose="Identify the transfer record.")
        return {"units": [response]}

    def reject_changed_identity(payload):
        data = reviewed_verdicts(payload, verdict(0))
        row = data["verdicts"][0]
        row["proposal_checks"][0].update(
            identity_preserved=False,
            reason="A record question differs from the saved custody question.")
        row["question_resolutions"][0].update(status="complete", block_id="account-0")
        return data

    def repair(payload):
        response = changed_need(payload)["units"][0]
        response["questions"][0]["existing_id"] = ""
        response["progress_updates"] = [{
            "target_id": identities["question"], "status": "complete", "block_id": "account-0",
            "span_ids": ["L1"], "reason": "The reported current custody answers the earlier need.",
        }]
        return {"units": [response]}

    model = PublicContinuationModel(
        [opening, later], [{"units": [initial]}, changed_need, repair],
        checks=[verdict(0), reject_changed_identity, verdict(0)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    first = send(client, first_words, "original-information-need")
    saved_id = chat_matter_id("adv_demo", first["chat_id"])
    original = deepcopy(wired.store.load(saved_id).brain_chat[0])
    answer = send(client, later_words, "answered-and-new-need", opened=first)
    replay = send(client, later_words, "answered-and-new-need", opened=first)

    assert first["metrics"]["llm_calls"] == 3
    assert answer["metrics"]["llm_calls"] == 5 and replay["metrics"]["llm_calls"] == 0
    saved = wired.store.load(saved_id)
    assert saved.brain_chat[0] == original and len(saved.brain_chat) == 2
    progress = project_work(saved)
    questions = [row for row in progress["rows"] if row["kind"] == "question"]
    assert [(row["text"], row["status"]) for row in questions] == [
        ("Who holds the objects now?", "complete"),
        ("Which record describes the transfer?", "pending")]
    assert questions[0]["id"] != questions[1]["id"]
    assert next(row for row in progress["rows"] if row["kind"] == "task")["status"] == "pending"
    assert progress["events"][-1]["target_id"] == questions[0]["id"]


@pytest.mark.parametrize("shared", ["questions", "question_and_work"])
def test_public_distinct_proposals_share_paragraph_and_remain_individually_checked(
        client, wired, monkeypatch, shared):
    words = "Help clarify missing custody and timing details, and offer a record comparison."
    routing = plan(words, step="legal_work")
    proposed = unit(text="You ask to clarify the missing details.")
    proposed["blocks"] = proposed["blocks"][:2]
    proposal = proposed["questions"][0]
    proposal.update(purpose="Identify current custody.")
    second = {"id": "second-proposal", "existing_id": "", "block_id": "question-0",
              "target_ids": []}
    if shared == "questions":
        proposed["blocks"][1]["text"] = "Who holds the record now, and when was it transferred?"
        proposed["questions"].append({**second, "purpose": "Identify the transfer time."})
    else:
        proposed["blocks"][1]["text"] = (
            "Who holds the record now? If you want, I can compare it with the reported account.")
        proposed["next_work"] = [{**second, "purpose": "Offer a comparison if requested."}]
    proposed["sufficiency"] = {"status": "complete", "block_id": "account-0"}

    def inspect_proposals(payload):
        data = reviewed_verdicts(payload, verdict(0))
        checks = data["verdicts"][0]["proposal_checks"]
        assert len(checks) == 2
        assert all(check["block_id"] == "question-0" for check in checks)
        assert len({(check["section"], check["proposal_id"]) for check in checks}) == 2
        return data

    model = PublicContinuationModel([routing], [{"units": [proposed]}],
                                    checks=[inspect_proposals])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, words, "shared-proposal-paragraph")
    replay = send(client, words, "shared-proposal-paragraph")

    assert answer["metrics"]["llm_calls"] == 3 and replay["metrics"]["llm_calls"] == 0
    assert [operation for operation, _ in model.calls] == [
        "interpret_conversation", "continue_conversation", "verify_continuation"]
    saved = wired.store.load(chat_matter_id("adv_demo", answer["chat_id"]))
    progress = project_work(saved)
    entries = [row for row in progress["rows"] if row["origin"] == "proposed"]
    assert len(entries) == 2 and entries[0]["id"] != entries[1]["id"]
    assert entries[0]["block_id"] == entries[1]["block_id"] == "question-0"
    assert entries[0]["purpose"] != entries[1]["purpose"]
    assert len(answer["elements"]) == 3
    assert answer["elements"][-1]["text"] == "No changes were made to the saved record."
    assert len(saved.brain_chat) == 1


def test_public_copied_question_is_not_a_new_task_and_reaches_independent_review(
        client, wired, monkeypatch):
    words = "Help identify who currently holds the record."
    routing = plan(words, step="legal_work")
    original = unit(text="You ask who holds the record.", question="Who holds the record now?")
    original["questions"][0]["purpose"] = "Identify current custody."
    duplicated = deepcopy(original)
    duplicated["next_work"] = [deepcopy(duplicated["questions"][0])]

    def reject_disguised_task(payload):
        data = reviewed_verdicts(payload, verdict(0))
        check = next(check for check in data["verdicts"][0]["proposal_checks"]
                     if check["section"] == "next_work")
        check.update(purpose_expressed=False, identity_preserved=False,
                     reason="The paragraph asks for custody; it expresses no separate work offer.")
        return data

    model = PublicContinuationModel([routing], [{"units": [duplicated]}, {"units": [original]}],
                                    checks=[reject_disguised_task, verdict(0)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, words, "copied-question-task")
    replay = send(client, words, "copied-question-task")

    assert answer["metrics"]["llm_calls"] == 5 and replay["metrics"]["llm_calls"] == 0
    assert [operation for operation, _ in model.calls] == [
        "interpret_conversation", "continue_conversation", "verify_continuation",
        "continue_conversation", "verify_continuation"]
    assert answer["continuation"]["units"][0]["next_work"] == []
    saved = wired.store.load(chat_matter_id("adv_demo", answer["chat_id"]))
    progress = project_work(saved)
    assert len(saved.brain_chat) == 1
    assert [(row["kind"], row["origin"]) for row in progress["rows"]] == [
        ("task", "requested"), ("question", "proposed")]


@pytest.mark.parametrize("fault,path", [
    ("empty_id", "questions[0].id"),
    ("empty_purpose", "questions[0].purpose"),
    ("missing_block", "questions[0].block_id"),
    ("foreign_target", "questions[0].target_ids"),
    ("duplicate_id", "questions[1].id"),
    ("wrong_saved_kind", "questions[0].existing_id"),
])
def test_public_link_fault_feedback_names_exact_field_and_retains_valid_peer(
        client, wired, monkeypatch, fault, path):
    words = "Clarify two independent questions about what information should be checked."
    routing = plan(words, step="legal_work")
    routing["items"].append({**routing["items"][0], "request": "Clarify the second question."})
    fixed = unit(text="You ask what information should be checked.")
    peer = unit(1, text="You also request a separate clarification.")
    broken = deepcopy(fixed)
    link = broken["questions"][0]
    if fault == "empty_id":
        link["id"] = " "
    elif fault == "empty_purpose":
        link["purpose"] = " "
    elif fault == "missing_block":
        link["block_id"] = "absent-block"
    elif fault == "foreign_target":
        link["target_ids"] = ["another-file-record", "another-file-record"]
    elif fault == "duplicate_id":
        broken["questions"].append(deepcopy(link))
    else:
        link["existing_id"] = "unknown-saved-owner"

    def repair(payload):
        issues = payload["correction"]["validation_issues"]
        assert len(issues) == 1 and issues[0]["request_index"] == 0
        assert path in issues[0]["issue"]
        if fault == "missing_block":
            assert "absent-block" in issues[0]["issue"]
            assert "question-0" in issues[0]["issue"]
        if fault == "foreign_target":
            assert "another-file-record" in issues[0]["issue"]
            assert "record_catalogue" in issues[0]["issue"]
        assert [row["request_index"] for row in payload["work_items"]] == [0]
        return {"units": [fixed]}

    model = PublicContinuationModel([routing], [{"units": [broken, peer]}, repair])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, words, "precise-owner-correction")
    replay = send(client, words, "precise-owner-correction")

    assert answer["metrics"]["llm_calls"] == 5 and replay["metrics"]["llm_calls"] == 0
    checks = [payload for operation, payload in model.calls if operation == "verify_continuation"]
    assert [[row["request_index"] for row in payload["units"]] for payload in checks] == [[1], [0]]
    assert [row["state"] for row in answer["continuation"]["coverage"]] == ["ok", "ok"]
    assert [row["request_index"] for row in answer["continuation"]["units"]] == [0, 1]
    saved = wired.store.load(chat_matter_id("adv_demo", answer["chat_id"]))
    assert [row["message"] for row in saved.brain_chat] == [words]


def test_repeated_known_target_selection_is_idempotent_after_owner_validation():
    selected = ["D2", "D1", "D2", "D1"]
    proposed = unit()
    proposed["questions"][0]["target_ids"] = selected
    untouched = deepcopy(proposed)
    disputes = {"state": "ok", "rows": [
        {"id": "D1", "label": "First attributed dispute"},
        {"id": "D2", "label": "Second attributed dispute"},
    ]}
    model = ContinuationModel([{"units": [proposed]}, verdict(0)])

    result = _continue(model, disputes=disputes)

    assert len(model.calls) == 2
    assert result.coverage[0]["state"] == "ok"
    assert result.units[0]["questions"][0]["target_ids"] == ["D2", "D1"]
    assert model.calls[1][1]["units"][0]["questions"][0]["target_ids"] == ["D2", "D1"]
    assert proposed == untouched


def test_duplicate_targets_cannot_hide_an_unknown_record_identity():
    proposed = unit()
    proposed["questions"][0]["target_ids"] = ["D1", "D1", "foreign", "foreign"]
    disputes = {"state": "ok", "rows": [{"id": "D1", "label": "Attributed dispute"}]}
    model = ContinuationModel([{"units": [proposed]}, {"units": [proposed]}])

    result = _continue(model, disputes=disputes)

    assert len(model.calls) == 2 and result.units == ()
    assert result.coverage[0]["state"] == "unavailable"
    correction = model.calls[1][1]["correction"]["validation_issues"][0]["issue"]
    assert "questions[0].target_ids" in correction and "foreign" in correction
    assert all(prompt.operation == "continue_conversation" for prompt, _ in model.calls)
