"""Durable scoped progress is a checked projection, never another fact store."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from nm.brain.conversation import (
    IncompleteConversation,
    Message,
    OpeningCandidate,
    TurnPlan,
    WorkItem,
)
from nm.brain.source_snapshots import source_snapshots
from nm.brain.work_state import project_work, seal_progress
from nm.work_the_file.matter_contracts import Matter


def scope(request="Review the available account", *, intent="request", matter_scope="current"):
    return TurnPlan((WorkItem(request, "new", matter_scope, "ordinary", "legal_work",
                             intent=intent),),
                    request, OpeningCandidate(False, "", ""), False)


def proposed(turn_id, words, *, create=True, existing="", question=True,
             next_work=False, updates=None, sufficiency="needs_input"):
    reference = dict(type="conversation", id="L1", turn_id=turn_id,
                     role="advocate", text=words)
    block = dict(id="response", kind="assessment", text="A supported response to the account.",
                 span_ids=["L1"], record_ids=[], legal_source_ids=[],
                 uncertainty="reported", references=[reference])
    blocks = [block]
    questions, steps = [], []
    if question:
        blocks.append({**deepcopy(block), "id": "question", "kind": "question",
                       "text": "What outcome do you want?"})
        questions.append(dict(id="objective", existing_id="", block_id="question",
                              purpose="Understand the requested outcome.", target_ids=[]))
    if next_work:
        blocks.append({**deepcopy(block), "id": "next", "kind": "next_step",
                       "text": "Review the available record."})
        steps.append(dict(id="review", existing_id="", block_id="next",
                          purpose="Assess the reported record.", target_ids=[]))
    return dict(units=[dict(
        request_index=0, blocks=blocks, questions=questions, next_work=steps,
        sufficiency=dict(status=sufficiency, block_id="response"),
        work=dict(existing_id=existing, create=create), progress_updates=updates or [],
        verification="source_aware_continuation_v1")], coverage=[dict(request_index=0, state="ok")])


def append(matter, turn_id, words, continuation, *, seal=True, plan=None):
    if seal:
        work = continuation["units"][0]["work"] if continuation["units"] else {}
        intent = "request" if work.get("create") or work.get("existing_id") else "contribution"
        continuation = seal_progress(continuation, matter_id=str(matter.id), turn_id=turn_id,
                                     plan=plan or scope(intent=intent),
                                     prior_progress=project_work(matter))
    elements = []
    for unit in continuation["units"]:
        for block in unit["blocks"]:
            sources = source_snapshots(block["references"])
            elements.append(dict(text=block["text"], sources=sources,
                                 source=sources[0] if sources else None,
                                 refs=[source["locator"] for source in sources],
                                 continuation_request_index=unit["request_index"],
                                 continuation_block_id=block["id"]))
    response = dict(turn_id=turn_id, matter_id=str(matter.id), elements=elements,
                    continuation=continuation)
    row = dict(turn_id=turn_id, message=words, advocate_id=matter.advocate_id,
               matter_id=str(matter.id), elements=deepcopy(elements), response=response,
               committed=True, release_state="released")
    return replace(matter, brain_chat=(*matter.brain_chat, row))


def opened():
    matter = Matter(id="progress-matter", advocate_id="adv_owner", title="An account")
    words = "Please review the account and clarify what you need."
    return append(matter, "first", words, proposed("first", words, next_work=True))


def transition(target_id, status, *, spans=True):
    return dict(target_id=target_id, status=status, block_id="response",
                reason="The advocate's attributed words support this change.",
                span_ids=["L1"] if spans else [])


def test_projection_has_stable_server_ids_and_separate_requested_proposed_origins():
    matter = opened()
    saved = deepcopy(matter.brain_chat)
    first = project_work(matter)
    reopened = project_work(replace(matter, brain_chat=deepcopy(matter.brain_chat)))

    assert reopened == first
    assert matter.brain_chat == saved
    assert [(row["kind"], row["origin"], row["status"]) for row in first["rows"]] == [
        ("task", "requested", "pending"), ("question", "proposed", "pending"),
        ("task", "proposed", "pending")]
    assert len({row["id"] for row in first["rows"]}) == 3
    assert all(row["id"].startswith("wp_") for row in first["rows"])
    assert first["active_work"] == "Review the available account"
    assert first["coverage"] == {"older_progress": "tracked"}
    assert all(row["matter_scope"] == "current" for row in first["rows"])
    task = first["rows"][0]
    assert all(row["task_id"] == task["id"] for row in first["rows"][1:])


@pytest.mark.parametrize("status", ["complete", "promised", "unavailable", "deferred", "cancelled"])
def test_question_transitions_are_sourced_without_changing_scoped_task(status):
    matter = opened()
    before = project_work(matter)
    question = before["rows"][1]
    words = "Here is my response to your question."
    updated = append(matter, "answer", words, proposed(
        "answer", words, create=False, question=False,
        updates=[transition(question["id"], status)]))

    after = project_work(updated)

    assert len(after["rows"]) == 3
    assert after["rows"][1]["status"] == status
    assert after["rows"][0] == before["rows"][0]
    assert after["events"][-1]["target_id"] == question["id"]
    assert after["events"][-1]["turn_id"] == "answer"
    assert after["events"][-1]["span_ids"] == ["L1"]


def test_repeated_question_reuses_identity_and_unavailable_requires_a_changed_distinction():
    matter = opened()
    question_id = project_work(matter)["rows"][1]["id"]
    words = "Please continue the clarification."
    response = proposed("repeat", words, create=False)
    response["units"][0]["questions"][0]["existing_id"] = question_id
    repeated = append(matter, "repeat", words, response)
    assert len(project_work(repeated)["rows"]) == 3

    unavailable = append(repeated, "unavailable", "I cannot obtain that information.", proposed(
        "unavailable", "I cannot obtain that information.", create=False, question=False,
        updates=[transition(question_id, "unavailable")]))
    with pytest.raises(IncompleteConversation, match="repeated without a supported change"):
        reasked = deepcopy(response)
        reasked["units"][0]["blocks"] = proposed("reask", words)["units"][0]["blocks"]
        append(unavailable, "reask", words, reasked)

    changed = proposed("changed", "I now have the information.", create=False,
                       updates=[transition(question_id, "pending")])
    changed["units"][0]["questions"][0]["existing_id"] = question_id
    resumed = append(unavailable, "changed", "I now have the information.", changed)
    assert project_work(resumed)["rows"][1]["status"] == "pending"


def test_explicit_scoped_completion_is_separate_from_sufficiency_and_matter_closure():
    matter = Matter(id="new-progress", advocate_id="adv_owner", title="A requested scope")
    words = "Please assess this narrow account."
    assessment = proposed("assessment", words, question=False, sufficiency="complete")
    pending = append(matter, "assessment", words, assessment)
    assert project_work(pending)["rows"][0]["status"] == "pending"

    explicit = proposed("complete", words, question=False, sufficiency="complete",
                        updates=[transition("$work", "complete")])
    delivered = append(matter, "complete", words, explicit)
    progress = project_work(delivered)
    assert progress["rows"][0]["status"] == "complete"
    assert progress["active_work"] == ""
    assert delivered.brain_ready is True
    assert delivered.brain_chat[0]["response"]["continuation"]["units"][0][
        "progress_updates"][0]["target_id"] == progress["rows"][0]["id"]
    assert "closed" not in progress


def test_earlier_attributed_answer_can_reconcile_a_question_without_losing_speaker():
    matter = opened()
    question_id = project_work(matter)["rows"][1]["id"]
    words = "Use the answer I already gave."
    response = proposed("reconcile", words, create=False, question=False,
                        updates=[{**transition(question_id, "complete"), "span_ids": ["P1S1"]}])
    block = response["units"][0]["blocks"][0]
    block["span_ids"].append("P1S1")
    block["references"].append(dict(type="conversation", id="P1S1", role="advocate",
                                     turn_id="first", text=matter.brain_chat[0]["message"]))
    updated = append(matter, "reconcile", words, response)
    history = (Message("first", "advocate", matter.brain_chat[0]["message"]),)
    assert project_work(updated, prior_conversation=history)["rows"][1]["status"] == "complete"
    assert project_work(updated, prior_conversation=history)["coverage"] == {
        "older_progress": "tracked"}


def test_untracked_stage_one_questions_survive_without_inventing_a_requested_task():
    matter = Matter(id="legacy-progress", advocate_id="adv_owner", title="Earlier work")
    words = "I have an earlier account."
    response = proposed("earlier", words)
    unit = response["units"][0]
    unit.pop("work")
    unit.pop("progress_updates")
    for row in unit["questions"]:
        row.pop("existing_id")
    saved = append(matter, "earlier", words, response, seal=False)

    progress = project_work(saved)

    assert len(progress["rows"]) == 1
    assert progress["rows"][0]["kind"] == "question"
    assert progress["rows"][0]["matter_scope"] == "uncertain"
    assert progress["rows"][0]["status"] == "pending"
    assert progress["active_work"] == ""
    assert progress["coverage"]["older_progress"] == "untracked"
    assert progress["diagnostics"]


@pytest.mark.parametrize("damage", [
    "server_id", "missing_version", "unknown_target", "speaker", "source_words",
    "displayed_text", "row_owner", "response_identity", "unreleased", "duplicate_turn",
])
def test_saved_progress_integrity_failures_are_not_projected_as_empty_or_complete(damage):
    matter = opened()
    rows = deepcopy(matter.brain_chat)
    row = rows[0]
    unit = row["response"]["continuation"]["units"][0]
    if damage == "server_id":
        unit["work"]["progress_id"] = "wp_foreign"
    elif damage == "missing_version":
        unit.pop("progress_version")
    elif damage == "unknown_target":
        unit["progress_updates"] = [transition("foreign", "complete")]
    elif damage == "speaker":
        unit["blocks"][0]["references"][0]["role"] = "nm"
    elif damage == "source_words":
        unit["blocks"][0]["references"][0]["text"] = "Invented source words."
    elif damage == "displayed_text":
        row["elements"][0]["text"] = row["response"]["elements"][0]["text"] = "Other words."
    elif damage == "row_owner":
        row["advocate_id"] = "other-owner"
    elif damage == "response_identity":
        row["response"]["turn_id"] = "other-turn"
    elif damage == "unreleased":
        row["release_state"] = "withheld"
    else:
        rows = (*rows, deepcopy(row))

    with pytest.raises(IncompleteConversation):
        project_work(SimpleNamespace(id=matter.id, advocate_id=matter.advocate_id, brain_chat=rows))


@pytest.mark.parametrize("status", ["complete", "promised", "unavailable", "deferred", "cancelled"])
def test_question_status_changes_need_advocate_support(status):
    matter = opened()
    question_id = project_work(matter)["rows"][1]["id"]
    words = "Continue."
    with pytest.raises(IncompleteConversation, match="supporting words"):
        append(matter, "unsupported", words, proposed(
            "unsupported", words, create=False, question=False,
            updates=[transition(question_id, status, spans=False)]))


def test_local_work_alias_without_a_scoped_task_is_rejected():
    matter = opened()
    words = "This is a factual correction only."
    with pytest.raises(IncompleteConversation, match="no selected task"):
        append(matter, "unscoped", words, proposed(
            "unscoped", words, create=False, question=False,
            updates=[transition("$work", "complete")]))


def test_an_aside_has_no_progress_event_and_retains_existing_obligations():
    matter = opened()
    before = project_work(matter)
    row = dict(turn_id="aside", advocate_id=matter.advocate_id, matter_id=str(matter.id),
               message="Hello again.", committed=True, release_state="released",
               elements=[{"text": "Hello."}],
               response={"turn_id": "aside", "elements": [{"text": "Hello."}]})
    after = project_work(replace(matter, brain_chat=(*matter.brain_chat, row)))
    assert after == before


def test_request_cannot_disappear_from_progress_and_contribution_cannot_invent_a_task():
    matter = Matter(id="intent-progress", advocate_id="adv_owner", title="Intent")
    words = "Please perform the requested work."
    with pytest.raises(IncompleteConversation, match="no durable task association"):
        append(matter, "lost-request", words, proposed(
            "lost-request", words, create=False), plan=scope())
    with pytest.raises(IncompleteConversation, match="unrequested task"):
        append(matter, "invented-request", words, proposed(
            "invented-request", words), plan=scope(intent="contribution"))


def test_scoped_links_follow_the_selected_task_without_assuming_current_matter():
    matter = Matter(id="scope-progress", advocate_id="adv_owner", title="Scoped work")
    words = "A question concerning a separate matter."
    other = append(matter, "other", words, proposed("other", words),
                   plan=scope(matter_scope="other"))
    prior = project_work(other)
    assert all(row["matter_scope"] == "other" for row in prior["rows"])
    followup = "A factual contribution to that earlier work."
    updated = append(other, "followup", followup, proposed(
        "followup", followup, create=False, existing=prior["rows"][0]["id"]),
        plan=scope(intent="contribution", matter_scope="uncertain"))
    assert project_work(updated)["rows"][-1]["matter_scope"] == "other"


def test_question_and_next_work_have_distinct_displayed_owners():
    matter = Matter(id="owner-progress", advocate_id="adv_owner", title="Owned work")
    words = "Please review the account."
    response = proposed("shared", words, next_work=True)
    response["units"][0]["next_work"][0]["block_id"] = "question"
    with pytest.raises(IncompleteConversation, match="distinct displayed owner"):
        append(matter, "shared", words, response)


def test_historical_missing_intent_stays_explicitly_untracked_without_inventing_intent():
    matter = opened()
    rows = deepcopy(matter.brain_chat)
    unit = rows[0]["response"]["continuation"]["units"][0]
    unit["progress_version"] = 1
    work = unit["work"]
    work.pop("intent")
    progress = project_work(replace(matter, brain_chat=rows))
    assert progress["coverage"]["older_progress"] == "untracked"
    assert all(row["matter_scope"] == "current" for row in progress["rows"])
    assert progress["rows"][0]["origin"] == "unassessed"
    assert progress["active_work"] == ""
    assert "intent" not in work


def test_historical_role_overlap_preserves_source_identity_and_is_explicitly_untracked():
    matter = opened()
    rows = deepcopy(matter.brain_chat)
    unit = rows[0]["response"]["continuation"]["units"][0]
    unit["progress_version"] = 1
    unit["work"].pop("intent")
    unit["next_work"][0]["block_id"] = unit["questions"][0]["block_id"]
    historical = replace(matter, brain_chat=rows)
    raw = deepcopy(historical.brain_chat)

    progress = project_work(historical)

    assert historical.brain_chat == raw
    assert progress["coverage"]["older_progress"] == "untracked"
    assert len(progress["rows"]) == 3
    assert progress["rows"][1]["text"] == progress["rows"][2]["text"]
    assert len({row["id"] for row in progress["rows"]}) == 3

    unit["blocks"][1]["references"][0]["text"] = "An invented historical passage."
    with pytest.raises(IncompleteConversation):
        project_work(replace(matter, brain_chat=rows))


def test_new_progress_has_its_own_version_and_cannot_omit_interpreted_intent():
    matter = opened()
    rows = deepcopy(matter.brain_chat)
    unit = rows[0]["response"]["continuation"]["units"][0]
    assert unit["progress_version"] == 2
    unit["work"].pop("intent")
    with pytest.raises(IncompleteConversation, match="intent"):
        project_work(replace(matter, brain_chat=rows))


def test_already_completed_selected_task_needs_no_duplicate_lifecycle_transition():
    matter = Matter(id="complete-progress", advocate_id="adv_owner", title="A scoped task")
    words = "Please complete this narrow assessment."
    delivered = append(matter, "delivered", words, proposed(
        "delivered", words, question=False, sufficiency="complete",
        updates=[transition("$work", "complete")]))
    before = project_work(delivered)
    task_id = before["rows"][0]["id"]
    review = "Show me the earlier completed assessment."
    inspected = append(delivered, "inspection", review, proposed(
        "inspection", review, create=False, existing=task_id, question=False,
        sufficiency="complete"))

    after = project_work(inspected)

    assert after["rows"] == before["rows"]
    assert after["events"] == before["events"]
    assert after["active_work"] == ""
    assert len(inspected.brain_chat) == 2
    assert inspected.brain_chat[-1]["response"]["continuation"]["units"][0][
        "progress_updates"] == []


@pytest.mark.parametrize("status", ["pending", "promised", "unavailable", "deferred", "cancelled"])
def test_complete_immediate_reply_preserves_broader_noncomplete_task(status):
    matter = opened()
    task_id = project_work(matter)["rows"][0]["id"]
    if status != "pending":
        words = "My availability or direction for this task has changed."
        matter = append(matter, "change", words, proposed(
            "change", words, create=False, existing=task_id, question=False,
            updates=[transition(task_id, status)]))
    before = project_work(matter)
    request = "Give the next clarification within the ongoing assessment."
    answered = append(matter, "reply-complete", request, proposed(
        "reply-complete", request, create=False, existing=task_id, question=False,
        sufficiency="complete"))

    after = project_work(answered)

    assert after["rows"] == before["rows"]
    assert after["events"] == before["events"]
    assert after["rows"][0]["status"] == status
