"""Actual dispatched author context, pinned history recovery, no client delivery."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.legal_brain.brain_context import (
    ContextPolicy,
    ContextRefused,
    ContextSession,
    assemble_brief,
)
from nm.legal_brain.loop_contracts import LoopLimits
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import ToolCall
from nm.work_the_file.matter_contracts import Thread
from tests.test_private_preview_display_records_only_checked_shown_words import (
    QUESTION,
    _question,
    acknowledge,
)
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a


def _run(brain, *, turn_id="later_turn", selected_issue_ids=()):
    brain.model.tool_call.side_effect = [replace(_response(ToolCall(
        "ack", "propose_conversation", {"text": "Understood."})), model="scripted:author")]
    result = brain.run(matter_id="mat_loop", turn_id=turn_id, message="Thank you.",
        selected_issue_ids=selected_issue_ids,
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 12, 400))
    sent = brain.model.tool_call.call_args.kwargs["messages"]
    return result, sent


def test_actual_author_dispatch_includes_checked_shown_question_but_not_unseen_proposal(tmp_path):
    store, brain, _, _, service, _ = _question(tmp_path)
    acknowledge(service)
    before = store.load("mat_loop")
    outcome, messages = _run(brain)
    data = json.loads(messages[0].text)["data"]
    assert data["private_display_history_as_of_version"] == before.version
    assert data["displayed_private_questions"][0]["text"] == QUESTION
    assert data["displayed_private_questions"][0]["state"] == (
        "historical_private_preview_display_not_current_legal_validity")
    assert "PRIVATE UNREVIEWED WORDING" not in messages[0].text
    assert not before.asked and not store.load("mat_loop").asked
    assert not store.load("mat_loop").turn_receipts
    assert outcome.record.events[0].payload["context"]["brief"]["text"] == messages[0].text


def test_new_author_context_never_calls_an_unseen_private_candidate_already_asked(tmp_path):
    _, brain, _, _, _, _ = _question(tmp_path)
    _, messages = _run(brain)
    assert json.loads(messages[0].text)["data"]["displayed_private_questions"] == []
    assert QUESTION not in messages[0].text


def test_a_late_display_does_not_rewrite_existing_dispatch_or_replay_identity(tmp_path):
    store, brain, _, _, service, _ = _question(tmp_path)
    outcome, messages = _run(brain, turn_id="before_late_display")
    assert json.loads(messages[0].text)["data"]["displayed_private_questions"] == []
    acknowledge(service)
    after = store.load("mat_loop")
    brain.model.tool_call.side_effect = lambda *_args, **_kwargs: pytest.fail("Replay cannot spend")
    replay = brain.run(matter_id="mat_loop", turn_id="before_late_display", message="Thank you.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 12, 400))
    assert replay.record == outcome.record and store.load("mat_loop") == after
    _, new_messages = _run(brain, turn_id="after_late_display")
    assert json.loads(new_messages[0].text)["data"]["displayed_private_questions"][0][
        "text"] == QUESTION


def test_compaction_and_recovery_keep_prior_shown_words_and_the_original_history_boundary(tmp_path):
    store, brain, _, _, service, _ = _question(tmp_path)
    acknowledge(service)
    matter = store.load("mat_loop")
    brief = assemble_brief(matter, advocate_id="adv_loop", display_before_version=matter.version)
    session = ContextSession(brain.principles.load(), brain.registry.definitions, brief,
        provider=brain.model.provider, model=brain.model.resolved_model(None))
    # Audit-only writes may advance transaction versions, never the displayed history pin.
    current = replace(matter, version=matter.version + 1)
    store.commit(current, expected_version=matter.version)
    session.compact(current, reason="Controlled exact capacity recovery")
    data = json.loads(session.messages[0].text)["data"]
    assert data["private_display_history_as_of_version"] == matter.version
    assert data["displayed_private_questions"][0]["text"] == QUESTION
    restored = ContextSession.from_record(session.to_record(), current, advocate_id="adv_loop")
    assert restored.to_record() == session.to_record()


def test_a_display_from_a_different_selected_dispute_is_not_inherited(tmp_path):
    store, brain, _, _, service, _ = _question(tmp_path)
    acknowledge(service)
    matter = store.load("mat_loop")
    other = Thread.create("Another recorded dispute")
    store.commit(replace(matter, threads=(*matter.threads, other), version=matter.version + 1),
                 expected_version=matter.version)
    _, messages = _run(brain, selected_issue_ids=(other.id,))
    assert json.loads(messages[0].text)["data"]["displayed_private_questions"] == []
    assert QUESTION not in messages[0].text


def test_bounded_context_refuses_oversized_checked_display_history_instead_of_truncating(tmp_path):
    store, brain, _, _, service, _ = _question(tmp_path)
    acknowledge(service)
    matter = store.load("mat_loop")
    plain = assemble_brief(matter, advocate_id="adv_loop")
    from nm.shared.model_port import estimate_tokens

    policy = ContextPolicy(max_tokens=estimate_tokens(plain.text) + 100, reserve_tokens=99)
    assert assemble_brief(matter, advocate_id="adv_loop", policy=policy).text == plain.text
    with pytest.raises(ContextRefused, match="cannot fit"):
        assemble_brief(matter, advocate_id="adv_loop", policy=policy,
                       display_before_version=matter.version)
    assert store.load("mat_loop") == matter and not brain.model.tool_call.call_args.kwargs.get(
        "truncate")


@pytest.mark.parametrize("what", ["anchor", "words", "source"])
def test_recovery_rejects_authored_display_history_or_source_identity(tmp_path, what):
    store, brain, _, _, service, _ = _question(tmp_path)
    acknowledge(service)
    matter = store.load("mat_loop")
    session = ContextSession(brain.principles.load(), brain.registry.definitions,
        assemble_brief(matter, advocate_id="adv_loop", display_before_version=matter.version),
        provider=brain.model.provider, model=brain.model.resolved_model(None))
    record = deepcopy(session.to_record())
    if what == "source":
        source = next(row for row in record["brief"]["sources"]
                      if row["kind"] == "historical_private_preview_question")
        source["version"] = "forged"
    else:
        data = json.loads(record["brief"]["text"])
        if what == "anchor":
            data["data"]["private_display_history_as_of_version"] = matter.version + 1
        else:
            data["data"]["displayed_private_questions"][0]["text"] = "Unchecked question"
        record["brief"]["text"] = json.dumps(data)
    assert record != session.to_record()
    with pytest.raises(ContextRefused):
        ContextSession.from_record(record, matter, advocate_id="adv_loop")
