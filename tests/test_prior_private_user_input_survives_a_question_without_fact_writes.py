"""Actual multi-turn lead context, not a template or model transcript replay."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock

import pytest
from nm.adapters.principles_file import FilePrinciples
from nm.core.brain_context import ContextPolicy, ContextRefused, ContextSession, assemble_brief
from nm.core.controlled_brain import ControlledBrain, EvaluationScope
from nm.core.original_instruction import InstructionRefused, prior_instructions
from nm.core.tools import Boundary, foundation_tools
from nm.domain.budget import Budget
from nm.domain.loop import LoopEvent, LoopLimits, LoopMode, LoopRecord, StepKind
from nm.domain.matter import Thread
from nm.ports.model import ToolCall, estimate_tokens

from tests.test_reviewed_private_preview_checks_saved_words import changed_payload
from tests.test_the_loop_records_work_before_using_it import _response, _setup

pytestmark = pytest.mark.class_a
BRIEF = ("I advise Ananya. Her father's land is claimed by her brother under a disputed "
         "family arrangement. The neighbour has separately blocked access. A shop tenant "
         "has withheld rent; Ananya disputes his account of repairs. No suit is pending. "
         "Assess the distinct disputes, preserve the denials and tell me what matters next.")
REPLY = "The access was blocked on 4 March. I do not have the unsigned family note."


def setup(tmp_path):
    store, identity, log, model, _ = _setup(tmp_path)
    registry = foundation_tools(store, Mock(), manifest=Mock(), source_version="controlled-gen",
        before=lambda *_: Boundary(True, "Controlled scoped admission"),
        after=lambda *_: Boundary(True, "Controlled result admission"))
    model.context_budget.return_value = 100000
    brain = ControlledBrain(store=store, model=model, log=log, principles=FilePrinciples(),
        registry=registry, scope=EvaluationScope("CONTROLLED", "adv_loop",
            frozenset({identity.matter_id}), LoopMode.SYNTHETIC),
        session_current=lambda: True, cost_ceiling=lambda *_: 0.03)
    return store, brain


def run(brain, turn, message, *, selected_issue_ids=(), cancelled=False):
    brain.model.tool_call.side_effect = [_response(ToolCall(
        "question", "ask_advocate", {"question": "Which date was access blocked?"}))]
    outcome = brain.run(matter_id="mat_loop", turn_id=turn, message=message,
        selected_issue_ids=selected_issue_ids, cancelled=lambda: cancelled,
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 12, 400))
    return outcome


def data_sent(brain):
    return json.loads(brain.model.tool_call.call_args.kwargs["messages"][0].text)["data"]


def test_actual_reply_retains_original_three_dispute_brief_when_question_wrote_no_facts(tmp_path):
    store, brain = setup(tmp_path)
    first = run(brain, "opening", BRIEF)
    assert not store.load("mat_loop").facts and not store.load("mat_loop").threads
    second = run(brain, "answer", REPLY)
    sent = data_sent(brain)
    assert brain.model.tool_call.call_args.args[0].user == REPLY
    history = sent["admitted_private_instructions"]
    assert len(history) == 1 and history[0]["original_instruction"]["text"] == BRIEF
    assert history[0]["turn_id"] == first.record.identity.turn_id
    assert history[0]["detail_state"] == (
        "exact_prior_user_input_not_case_fact_or_current_authorization")
    assert history[0]["original_instruction"]["trust"] == (
        "user_instruction_not_established_fact_or_legal_authority")
    assert "Which date was access blocked?" not in json.dumps(history)
    assert not store.load("mat_loop").facts and not store.load("mat_loop").asked
    assert second.record.events[0].payload["context"]["brief"]["text"] == (
        brain.model.tool_call.call_args.kwargs["messages"][0].text)


def test_correction_keeps_both_original_accounts_without_establishing_either_as_truth(tmp_path):
    store, brain = setup(tmp_path)
    run(brain, "opening", BRIEF)
    correction = "Correction: the shop is let to a company, not to the individual director."
    run(brain, "correction", correction)
    run(brain, "continue", "Consider that correction without silently erasing the original.")
    rows = data_sent(brain)["admitted_private_instructions"]
    assert [row["original_instruction"]["text"] for row in rows] == [BRIEF, correction]
    assert all(row["original_instruction"]["trust"] == (
        "user_instruction_not_established_fact_or_legal_authority") for row in rows)
    assert not store.load("mat_loop").facts


def test_current_pending_special_child_or_future_input_is_not_inherited(tmp_path):
    store, brain = setup(tmp_path)
    first = run(brain, "opening", BRIEF)
    matter = store.load("mat_loop")
    pending_identity = replace(first.record.identity, turn_id="pending")
    # Rebuild the pending identity's valid one-event chain.
    pending = LoopRecord(pending_identity, (LoopEvent.create(1, StepKind.START,
        first.record.events[0].at, first.record.events[0].payload, pending_identity.fingerprint),))
    child_payload = first.record.events[0].payload
    child_context = deepcopy(child_payload["context"])
    child_data = json.loads(child_context["brief"]["text"])
    child_data["material_kind"] = "checked_task_research"
    child_context["brief"]["text"] = json.dumps(child_data)
    child = changed_payload(first.record, 0, context=child_context)
    store.commit(replace(matter, loop_records=(pending, child), version=matter.version + 1),
                 expected_version=matter.version)
    current = store.load("mat_loop")
    brief = assemble_brief(current, advocate_id="adv_loop",
        display_before_version=current.version, include_admitted_instructions=True)
    assert json.loads(brief.text)["data"]["admitted_private_instructions"] == []
    # The future/current admission cannot become its own prior input.
    plain = assemble_brief(matter, advocate_id="adv_loop", display_before_version=1,
                           include_admitted_instructions=True)
    assert json.loads(plain.text)["data"]["admitted_private_instructions"] == []


def test_old_predispatch_missing_input_stays_explicitly_not_recorded(tmp_path):
    store, brain = setup(tmp_path)
    first = run(brain, "old_stopped", BRIEF, cancelled=True)
    start = first.record.events[0].payload
    start.pop("original_instruction")
    events, previous = [], first.record.identity.fingerprint
    for event in first.record.events:
        rebuilt = LoopEvent.create(event.sequence, event.kind, event.at,
            start if event.sequence == 1 else event.payload, previous)
        events.append(rebuilt)
        previous = rebuilt.fingerprint
    old = LoopRecord(first.record.identity, tuple(events))
    matter = store.load("mat_loop")
    store.commit(replace(matter, loop_records=(old,), version=matter.version + 1),
                 expected_version=matter.version)
    run(brain, "later", REPLY)
    row = data_sent(brain)["admitted_private_instructions"][0]
    assert row["detail_state"] == "not_recorded"
    assert row["original_instruction"]["state"] == "not_recorded"
    assert row["original_instruction"]["text"] == ""


def test_initial_history_pin_makes_later_input_writes_irrelevant_to_exact_retry(tmp_path):
    store, brain = setup(tmp_path)
    run(brain, "opening", BRIEF)
    second = run(brain, "answer", REPLY)
    captured = second.record.events[0].payload["context"]
    run(brain, "subsequent", "Another later clarification.")
    before = store.load("mat_loop")
    brain.model.tool_call.side_effect = lambda *_args, **_kwargs: pytest.fail("Replay cannot spend")
    replay = brain.run(matter_id="mat_loop", turn_id="answer", message=REPLY,
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 12, 400))
    assert replay.record == second.record and store.load("mat_loop") == before
    recovered = ContextSession.from_record(captured, before, advocate_id="adv_loop")
    assert recovered.to_record() == captured
    recovered.compact(before, reason="Controlled pinned history compaction")
    assert [row["original_instruction"]["text"] for row in json.loads(
        recovered.brief.text)["data"]["admitted_private_instructions"]] == [BRIEF]


def test_selected_scope_omission_is_explicit_and_never_reveals_unrelated_original_words(tmp_path):
    store, brain = setup(tmp_path)
    matter = store.load("mat_loop")
    left, right = Thread.create("Recorded dispute one"), Thread.create("Recorded dispute two")
    store.commit(replace(matter, threads=(left, right), version=matter.version + 1),
                 expected_version=matter.version)
    run(brain, "left_instruction", BRIEF, selected_issue_ids=(left.id,))
    run(brain, "right_work", REPLY, selected_issue_ids=(right.id,))
    row = data_sent(brain)["admitted_private_instructions"][0]
    assert row["detail_state"] == "outside_selected_issue_scope"
    assert "text" not in row["original_instruction"]
    assert BRIEF not in json.dumps(data_sent(brain))


def test_context_budget_refuses_complete_nonfitting_original_history_without_truncating(tmp_path):
    store, brain = setup(tmp_path)
    run(brain, "opening", BRIEF)
    matter = store.load("mat_loop")
    plain = assemble_brief(matter, advocate_id="adv_loop", display_before_version=matter.version)
    policy = ContextPolicy(max_tokens=estimate_tokens(plain.text) + 100, reserve_tokens=99)
    with pytest.raises(ContextRefused, match="cannot fit"):
        assemble_brief(matter, advocate_id="adv_loop", display_before_version=matter.version,
                       include_admitted_instructions=True, policy=policy)
    assert store.load("mat_loop") == matter


@pytest.mark.parametrize("what", ["words", "identity", "scope"])
def test_recovery_cannot_author_history_words_or_bypass_the_selected_scope(tmp_path, what):
    store, brain = setup(tmp_path)
    run(brain, "opening", BRIEF)
    second = run(brain, "answer", REPLY)
    record = deepcopy(second.record.events[0].payload["context"])
    encoded = json.loads(record["brief"]["text"])
    row = encoded["data"]["admitted_private_instructions"][0]
    if what == "words":
        row["original_instruction"]["text"] = "Different alleged instruction"
    elif what == "identity":
        row["original_instruction"]["text_identity"] = "0" * 64
    else:
        row["selected_issue_ids"] = ["outside"]
    record["brief"]["text"] = json.dumps(encoded)
    assert record != second.record.events[0].payload["context"]
    with pytest.raises(ContextRefused):
        ContextSession.from_record(record, store.load("mat_loop"), advocate_id="adv_loop")


def test_prior_source_selector_uses_the_same_pinned_mode_and_exact_record_as_context(tmp_path):
    store, brain = setup(tmp_path)
    first = run(brain, "opening", BRIEF)
    matter = store.load("mat_loop")
    rows = prior_instructions(matter, actor=brain.scope.advocate_id,
                             mode=LoopMode.SYNTHETIC, before_version=matter.version)
    assert len(rows) == 1 and rows[0].record == first.record
    assert rows[0].original.text == BRIEF and rows[0].selected_issue_ids == ()
    assert prior_instructions(matter, actor=brain.scope.advocate_id,
                              mode=LoopMode.RECORDED, before_version=matter.version) == ()
    assert prior_instructions(matter, actor=brain.scope.advocate_id,
                              mode=LoopMode.SYNTHETIC,
                              before_version=first.record.identity.matter_version) == ()


@pytest.mark.parametrize("change", ["foreign_actor", "foreign_file", "duplicate", "input"])
def test_prior_source_selector_refuses_ambiguous_foreign_or_changed_admitted_input(
        tmp_path, change):
    store, brain = setup(tmp_path)
    first = run(brain, "opening", BRIEF)
    matter = store.load("mat_loop")
    source = first.record
    if change in {"foreign_actor", "foreign_file"}:
        identity = replace(source.identity, **{
            "advocate_id" if change == "foreign_actor" else "matter_id": "foreign"})
        events, previous = [], identity.fingerprint
        for event in source.events:
            rebuilt = LoopEvent.create(event.sequence, event.kind, event.at,
                                       event.payload, previous)
            events.append(rebuilt)
            previous = rebuilt.fingerprint
        source = LoopRecord(identity, tuple(events))
    elif change == "input":
        raw = first.record.events[0].payload["original_instruction"]
        raw["text"] = "Different prior input."
        source = changed_payload(source, 0, original_instruction=raw)
    records = (source, source) if change == "duplicate" else (source,)
    altered = replace(matter, loop_records=records)
    with pytest.raises(InstructionRefused):
        prior_instructions(altered, actor=brain.scope.advocate_id,
                           mode=LoopMode.SYNTHETIC, before_version=matter.version)
    with pytest.raises(ContextRefused):
        assemble_brief(altered, advocate_id=brain.scope.advocate_id,
            display_before_version=matter.version, include_admitted_instructions=True)
