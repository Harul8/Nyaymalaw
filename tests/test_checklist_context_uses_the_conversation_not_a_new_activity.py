"""One checklist owner, exact past assertions and source-bound revalidation."""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import date, timedelta
from unittest.mock import Mock

import pytest

from nm.Archives.legal_brain.communicate.register_contracts import PEER
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopIdentity, LoopMode, StopReason, digest
from nm.Archives.legal_brain.orchestrate.tool_catalogue import catalogue_tools
from nm.Archives.legal_brain.orchestrate.tools import (
    Boundary,
    PreparedToolResult,
    ToolContext,
    ToolRefused,
    ToolRegistry,
)
from nm.Archives.legal_brain.reason import requirements
from nm.Archives.legal_brain.reason.requirements_contracts import Force, Requirement, State, checklist, key
from nm.Archives.legal_brain.understand import brain_context
from nm.Archives.legal_brain.understand.brain_context import ContextRefused, ContextSession, assemble_brief
from nm.shared.model_port import ToolCall
from nm.work_the_file.file_mutation import MutationRefused, prepare_requirement_answer
from nm.work_the_file.matter_contracts import Fact, Matter, Provenance, Thread
from nm.work_the_file.write_tools import write_tools
from tests.test_brain_context_is_a_checked_file_projection import snapshot, tools

pytestmark = pytest.mark.class_a
TODAY = date(2026, 9, 27)
ALLOW = Boundary(True, "controlled scope")


def fixture():
    clause = Requirement("The service account", "It changes the route", "A notice must be served.",
                         "Actual captured law", "law:1", Force.REQUIRED, "read-one")
    words = "Opposing counsel says notice arrived; our client denies receiving it."
    fact = Fact("old-assertion", words, Provenance("advocate_statement", "old-turn", span=words),
                exact_words=words)
    other = Fact("other-assertion", "An independent dispute's account.",
                 Provenance("advocate_statement", "other-turn"))
    thread = Thread("one", "One distinct dispute", chronology=(fact.id,), requirements=(clause,),
                    requirement_reads={clause.locator: clause.source_identity})
    context = requirements.applicability_identity(thread, (fact, other))
    thread = replace(thread, requirements=(replace(clause, context_identity=context),),
                     requirement_read_contexts={clause.locator: context})
    matter = Matter("file", "advocate", "Two disputes", version=3, facts=(fact, other),
                    threads=(thread, Thread("two", "Other dispute", chronology=(other.id,))))
    trusted = {"advocate_id": matter.advocate_id, "current_version": matter.version,
               "turn_id": "current-turn", "message": "Assess what is already on the file."}
    return matter, trusted


def revalidate(matter, trusted, *, state="held", quote=None, due="", today=TODAY, **overrides):
    return prepare_requirement_answer(matter, **trusted, thread_id="one",
        requirement_key=key(matter.thread("one").requirements[0]), answer=state,
        quoted=quote or matter.fact("old-assertion").statement,
        due_expression=due, today=today, fact_id="old-assertion", **overrides)


def test_existing_assertion_revalidation_preserves_the_whole_account_and_never_reasks():
    matter, trusted = fixture()
    mutation, detail = revalidate(matter, trusted)
    assert mutation.after.facts == matter.facts
    assert mutation.after.thread("two") == matter.thread("two")
    item = checklist(mutation.after.thread("one"), mutation.after.facts)[0]
    assert item.state is State.OUTSTANDING and item.outcome.fact == "old-assertion"
    assert item.outcome.state is State.HELD and item.outcome.requires_review
    assert item.outcome.source_identity == "read-one"
    assert item.outcome.basis == matter.fact("old-assertion").statement
    assert detail["earlier_assertion_reused"] and not detail["legal_truth_established"]
    assert not detail["checklist_context"]["asking_complete"]
    assert detail["checklist_context"]["items"][0]["proposed_state"] == "held"
    assert detail["checklist_context"]["items"][0]["answer_statement"] == item.outcome.basis


def test_changed_source_cannot_borrow_the_prior_answer_generation_but_can_reuse_its_words():
    matter, trusted = fixture()
    first, _ = revalidate(matter, trusted)
    old = first.after.thread("one")
    changed_clause = replace(old.requirements[0], source_identity="read-two")
    changed = replace(first.after, threads=(replace(old, requirements=(changed_clause,),
                      requirement_reads={changed_clause.locator: "read-two"}),
                      first.after.thread("two")))
    assert checklist(changed.thread("one"), changed.facts)[0].state is State.OUTSTANDING
    prior = copy.deepcopy(changed.thread("one").requirement_outcomes)
    updated, _ = revalidate(changed, trusted)
    outcome = checklist(updated.after.thread("one"), updated.after.facts)[0].outcome
    assert outcome.source_identity == "read-two" and outcome.fact == "old-assertion"
    assert outcome.basis == matter.fact("old-assertion").statement
    assert updated.after.thread("one").requirement_outcomes[key(changed_clause)]["history"] == [
        {k: v for k, v in next(iter(prior.values())).items() if k != "history"}]
    assert changed.thread("one").requirement_outcomes == prior


@pytest.mark.parametrize("bad", ["withdrawn", "other_dispute", "document", "false_quote",
                                 "unrefreshed_requirement", "missing_assertion"])
def test_old_assertion_reuse_cannot_invent_borrow_or_revive_an_answer(bad):
    matter, trusted = fixture()
    quote = matter.fact("old-assertion").statement
    if bad == "withdrawn":
        matter = replace(matter, facts=(replace(matter.facts[0], superseded_by="replacement"),
                                       matter.facts[1]))
    elif bad == "other_dispute":
        matter = replace(matter, threads=(replace(matter.thread("one"), chronology=()),
                                         matter.thread("two")))
    elif bad == "document":
        matter = replace(matter, facts=(replace(matter.facts[0],
            provenance=Provenance("document", "old-turn", document="original", page=1)),
            matter.facts[1]))
    elif bad == "false_quote":
        quote = "Words never supplied by the advocate."
    elif bad == "unrefreshed_requirement":
        matter = replace(matter, threads=(replace(matter.thread("one"),
            requirement_reads={"law:1": "different-read"}), matter.thread("two")))
    else:
        matter = replace(matter, facts=(matter.facts[1],))
    with pytest.raises(MutationRefused):
        revalidate(matter, trusted, quote=quote)


def test_an_old_relative_promise_keeps_its_anchor_instead_of_restarting_the_clock():
    matter, trusted = fixture()
    words = "I will supply the original tomorrow."
    fact = replace(matter.facts[0], statement=words, exact_words=words,
                   provenance=Provenance("advocate_statement", trusted["turn_id"], span=words))
    matter = replace(matter, facts=(fact, matter.facts[1]))
    first, _ = revalidate(matter, trusted, state="promised", quote=words, due="tomorrow")
    later = {**trusted, "turn_id": "law-reread-turn"}
    refreshed, detail = revalidate(first.after, later, state="promised", quote=words,
                                   due="tomorrow", today=TODAY + timedelta(days=4))
    item = checklist(refreshed.after.thread("one"), refreshed.after.facts)[0]
    assert item.outcome.due == "2026-09-28"
    assert item.state is State.OUTSTANDING and item.outcome.state is State.PROMISED
    assert item.outcome.requires_review
    assert not detail["checklist_context"]["items"][0]["due_now"]
    assert not detail["checklist_context"]["settled"]
    assert detail["checklist_context"]["followups_are_not_legal_deadlines"]
    unanchored, _ = revalidate(matter, later, state="promised", quote=words, due="tomorrow",
                               today=TODAY + timedelta(days=4))
    assert checklist(unanchored.after.thread("one"), unanchored.after.facts)[0].outcome.due == ""


def test_checked_prefix_reader_and_write_receipt_share_exact_derived_checklist_state():
    matter, trusted = fixture()
    store = Mock(load=Mock(return_value=matter))
    registry = ToolRegistry(write_tools(store, today=lambda: TODAY),
                            before=lambda *_: ALLOW, after=lambda *_: ALLOW)
    identity = LoopIdentity(matter.id, matter.advocate_id, trusted["turn_id"], digest("offer"),
                           digest("principles"), registry.version, matter.version,
                           LoopMode.RECORDED)
    context = ToolContext(identity, original_message=trusted["message"], issue_ids=("one",))
    result = registry.invoke(ToolCall("old-info", "record_existing_requirement_answer", {
        "thread_id": "one", "requirement_key": key(matter.thread("one").requirements[0]),
        "answer": "unavailable", "quoted": matter.facts[0].statement,
        "due_expression": "", "fact_id": matter.facts[0].id}), context)
    assert isinstance(result, PreparedToolResult)
    updated = result.mutation.after
    expected = requirements.context_projection(updated.thread("one"), updated.facts, TODAY)
    assert result.envelope.data["checklist_context"] == expected
    prefix = json.loads(assemble_brief(updated, ("one",), advocate_id="advocate",
                                      as_of=TODAY).text)["data"]
    assert prefix["threads"][0]["checklist_context"] == expected
    assert prefix["threads"][0]["requirement_outcomes"]
    store.load.return_value = updated
    reader = ToolRegistry(catalogue_tools(store, Mock(), source_version="actual-source",
        today=lambda: TODAY), before=lambda *_: ALLOW, after=lambda *_: ALLOW)
    returned = reader.invoke(ToolCall("read", "read_thread", {"thread_id": "one"}),
        replace(context, identity=replace(identity, tools_version=reader.version)))
    assert returned.data["checklist_context"] == expected
    assert updated.facts == matter.facts


def test_existing_information_is_applied_in_the_actual_loop_without_an_extra_user_activity(
        tmp_path):
    from tests.test_the_controlled_brain_is_actually_wired import _brain
    from tests.test_the_loop_records_work_before_using_it import _limits, _response

    store, model, brain = _brain(tmp_path)
    initial = store.load("mat_loop")
    matter, _ = fixture()
    store.commit(replace(matter, id=initial.id, advocate_id=initial.advocate_id,
        version=initial.version + 1), expected_version=initial.version)
    brain.registry = brain.registry.extend(write_tools(store, today=lambda: TODAY))
    brain._runner._tools = brain.registry
    model.tool_call.side_effect = [
        _response(ToolCall("answer-known", "record_existing_requirement_answer", {
            "thread_id": "one", "requirement_key": key(matter.thread("one").requirements[0]),
            "fact_id": "old-assertion", "answer": "held", "quoted": matter.facts[0].statement,
            "due_expression": ""})),
        _response(ToolCall("done", "submit", {"answer": "An unreleased candidate."})),
    ]
    result = brain.run(matter_id="mat_loop", turn_id="new-law-known-information",
        message="Use the account I already supplied.", selected_issue_ids=("one",),
        limits=_limits())
    assert result.reason is StopReason.PROPOSAL
    saved = store.load("mat_loop")
    assert saved.facts == matter.facts
    proposed = checklist(saved.thread("one"), saved.facts)[0]
    assert proposed.state is State.OUTSTANDING
    assert proposed.outcome.state is State.HELD and proposed.outcome.requires_review
    assert model.tool_call.call_count == 2
    assert saved.version == result.record.identity.matter_version + len(result.record.events)
    returned = next(event for event in result.record.events
                    if event.kind.value == "tool_returned" and "mutation_identity" in event.payload)
    assert returned.payload["receipt"]["data"]["earlier_assertion_reused"]
    assert not saved.turn_receipts, "information held is not legal advice or client cutover"


def test_recorded_work_scope_cannot_be_broadened_by_a_model_write_argument():
    matter, trusted = fixture()
    store = Mock(load=Mock(return_value=matter))
    registry = ToolRegistry(write_tools(store, today=lambda: TODAY),
                            before=lambda *_: ALLOW, after=lambda *_: ALLOW)
    identity = LoopIdentity(matter.id, matter.advocate_id, trusted["turn_id"], digest("offer"),
                           digest("principles"), registry.version, matter.version,
                           LoopMode.RECORDED)
    context = ToolContext(identity, original_message=trusted["message"], issue_ids=("one",))
    bad_calls = (
        ToolCall("new", "create_dispute", {"label": "Unrequested third dispute",
                                            "quoted": trusted["message"]}),
        ToolCall("borrow", "write_fact", {"thread_ids": ["two"],
                                           "quoted": trusted["message"]}),
        ToolCall("other", "correct_fact", {"old_fact_id": "other-assertion",
                                            "quoted": trusted["message"]}),
    )
    for call in bad_calls:
        with pytest.raises(ToolRefused, match="scope|narrowed|Narrowed"):
            registry.invoke(call, context)
    assert store.load.return_value == matter


def test_missing_or_unreadable_checklist_is_never_a_complete_conversation():
    matter, _ = fixture()
    thread = replace(matter.thread("one"), requirements=())
    absent = requirements.context_projection(thread, matter.facts, TODAY)
    assert absent["summary"]["state"] == "not_established"
    assert not absent["asking_complete"] and not absent["settled"]
    held, _ = revalidate(matter, fixture()[1])
    malformed = replace(held.after.thread("one"), requirements=(
        *held.after.thread("one").requirements, {"need": "A corrupted extra requirement"}))
    projection = requirements.context_projection(malformed, held.after.facts, TODAY)
    assert projection["unreadable_requirements"] == 1
    assert not projection["asking_complete"] and not projection["settled"]
    duplicate = replace(held.after.thread("one"), requirements=(
        *held.after.thread("one").requirements, *held.after.thread("one").requirements))
    repeated = requirements.context_projection(duplicate, held.after.facts, TODAY)
    assert repeated["duplicate_requirements"] == 1
    assert not repeated["asking_complete"] and not repeated["settled"]
    unanswered = requirements.context_projection(matter.thread("one"), matter.facts, TODAY)
    assert unanswered["items"][0]["answer_status"] == "not_established"


def test_the_controlled_communication_owner_is_once_versioned_and_cannot_be_replaced(monkeypatch):
    matter, _ = fixture()
    context = ContextSession(snapshot(), tools(), assemble_brief(matter, advocate_id="advocate"),
                             provider="scripted", model="held")
    assert context.system.count(PEER) == 1
    assert context.generations[-1]["communication_owner_identity"] == digest({"peer": PEER})
    with pytest.raises(ContextRefused, match="appears twice"):
        ContextSession(snapshot(PEER), tools(), context.brief, provider="scripted", model="held")
    recorded = context.to_record()
    monkeypatch.setattr(brain_context, "PEER", PEER + "\nA materially changed policy.")
    with pytest.raises(ContextRefused):
        context.assert_request(context.system, context.messages, model="held")
    with pytest.raises(ContextRefused):
        ContextSession.from_record(recorded, matter, advocate_id="advocate")
