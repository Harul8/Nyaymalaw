"""Real conversational writes require exact saved independent relevance review."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from nm.legal_brain.orchestrate.loop_contracts import LoopLimits, StepKind, StopReason
from nm.legal_brain.reason import requirements
from nm.legal_brain.reason.requirements_contracts import (
    Force,
    Outcome,
    Requirement,
    State,
    checklist,
    key,
)
from nm.legal_brain.verify.brain_assessment import AssessmentService
from nm.legal_brain.verify.checklist_review import ChecklistReviewService, classifications_for
from nm.shared.model_port import ProviderUnavailable, ToolCall
from nm.work_the_file import deadlines, dispute_agenda, summary
from nm.work_the_file.matter_contracts import Certainty, Thread
from nm.work_the_file.write_tools import write_tools
from tests.test_claims_reach_the_independent_review_from_the_saved_loop import _case
from tests.test_independent_claim_verifier import finding, premise, response
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
TODAY = date(2026, 9, 27)
PASSAGE = requirements.Passage(finding().ref, finding().span,
                               finding().source_kind.value, finding().locator)
NEED = Requirement("The notice", "Notice is a condition in the retrieved clause.",
                   "A benefit requires notice.", finding().ref, finding().locator,
                   Force.REQUIRED, PASSAGE.identity)


def run_conversation(tmp_path, *, answer="held", words="The notice was served yesterday.",
                     judged=None, terminal="ask_advocate", error=None, max_children=2,
                     current_source=PASSAGE.identity, read=True, due="", source_current=None):
    thread = Thread("thr_notice", "Notice dispute", requirements=(NEED,),
                    requirement_reads={NEED.locator: current_source}, chronology=("fact_1",))
    context = requirements.applicability_identity(thread, (premise(),))
    thread = replace(thread, requirements=(replace(NEED, context_identity=context),),
                     requirement_read_contexts={NEED.locator: context})
    store, brain, initial, judge, claim = _case(tmp_path, threads=(thread,),
                                              judged=judged, children=max_children)
    judge.error = error
    brain.registry = brain.registry.extend(write_tools(store, today=lambda: TODAY))
    brain._runner._tools = brain.registry
    brain.checklist_review = ChecklistReviewService(brain.reviewer, source_current=source_current)
    brain.assessment = AssessmentService(store=store, log=brain.log, session_current=lambda: True)
    calls = ([ToolCall("source", "read_provision", {
        "act": "Recorded primary rule", "section": "1", "as_of": "2026-01-01"})]
             if read else [])
    calls.append(ToolCall("classification", "record_requirement_answer", {
        "thread_id": thread.id, "requirement_key": key(NEED), "answer": answer,
        "quoted": words, "due_expression": due}))
    calls.append(ToolCall("terminal", terminal,
        {"question": "Which further information can you supply?"} if terminal == "ask_advocate"
        else {"text": "Thank you; I have noted that information."}
        if terminal == "propose_conversation"
        else {"claims": [claim]}))
    brain.model.tool_call.side_effect = [replace(_response(call),
        provider="scripted", model="scripted:author") for call in calls]
    result = brain.evaluate(matter_id="mat_loop", turn_id="conversation-checklist",
        message=words, limits=LoopLimits(initial.budget, 15, 500), max_repairs=0)
    return store, brain, result, judge


@pytest.mark.parametrize("answer,words,due,expected", [
    ("held", "The notice was served yesterday.", "", State.HELD),
    ("promised", "I will provide the notice tomorrow.", "tomorrow", State.PROMISED),
    ("unavailable", "The notice is unavailable.", "", State.UNAVAILABLE),
    ("outstanding", "I do not know whether any notice was served.", "", State.OUTSTANDING),
])
def test_question_turn_checks_actual_reply_before_any_completion_claim(
        tmp_path, answer, words, due, expected):
    store, _, result, judge = run_conversation(tmp_path, answer=answer, words=words, due=due)
    file = store.load("mat_loop")
    assert result.stop == StopReason.QUESTION.value and len(result.checklist_reviews) == 1
    assert result.checklist_reviews[0].review.result.released and len(judge.prompts) == 1
    assert result.budget.spend.children == 1 and not result.client_ready and not file.turn_receipts
    thread = file.threads[0]
    item = requirements.checklist(thread, file.facts, records=file.loop_records)[0]
    assert item.state is expected and item.independently_reviewed
    # The stored field remains only a proposal, not an authored pass or tick.
    raw = Outcome.restore(thread.requirement_outcomes[key(NEED)])
    assert raw.requires_review and checklist(thread, file.facts)[0].state is State.OUTSTANDING
    fact = file.fact(raw.fact)
    assert fact.statement == words and fact.certainty is Certainty.ASSERTED
    assert fact.confirmed is None and not fact.date
    assert "relevance-only" in judge.prompts[0].user and words in judge.prompts[0].user
    assert "establishes neither factual truth" in judge.prompts[0].user
    package_id = result.checklist_reviews[0].review.packages[0].id
    actual = next(row for row in file.loop_records
                  if row.identity.turn_id == f"conversation-checklist:verify:{package_id}")
    assert actual.events[-1].payload["released"] is False
    assert actual.events[0].payload["parent"] == result.attempts[0].record.identity.fingerprint
    assert actual.events[1].kind is StepKind.MODEL_STARTED
    board = dispute_agenda.project(file)["disputes"][0]
    assert board["requirements"][0]["state"] == expected.value
    assert board["nothing_to_ask"] is (expected is not State.OUTSTANDING)
    assert board["requirements_settled"] is (expected not in (State.OUTSTANDING, State.PROMISED))
    memory = summary.build(file).as_dict()
    assert memory["threads"][0]["requirements"]["held"] == int(expected is State.HELD)
    reminders = [row for row in deadlines.read_matter(file).rows
                 if row.kind is deadlines.DeadlineKind.INFORMATION_FOLLOWUP]
    assert bool(reminders) is (expected is State.PROMISED)


@pytest.mark.parametrize("words,judged", [
    ("No notice was served; I deny that it was.", response(inference=False)),
    ("I only have a certificate, not the notice.", response(applies=False)),
    ("Was any notice required? I do not know.", response(inference=None)),
    ("Perhaps my client mentioned notice; I cannot confirm.", response(opposition=False)),
])
def test_exact_words_and_provenance_do_not_certify_semantically_wrong_held(
        tmp_path, words, judged):
    store, _, result, judge = run_conversation(tmp_path, words=words, judged=judged)
    file = store.load("mat_loop")
    item = requirements.checklist(file.threads[0], file.facts, records=file.loop_records)[0]
    assert len(judge.prompts) == 1 and item.state is State.OUTSTANDING
    assert item.outcome.state is State.HELD and item.outcome.requires_review
    assert result.checklist_reviews[0].unresolved and result.limitations
    assert not classifications_for(file.threads[0], file.facts, file.loop_records)
    assert not dispute_agenda.project(file)["disputes"][0]["requirements_settled"]


def test_provider_failure_remains_grey_and_charges_the_exact_existing_budget(tmp_path):
    store, _, result, judge = run_conversation(tmp_path, error=ProviderUnavailable("Unavailable"))
    file = store.load("mat_loop")
    assert len(judge.prompts) == 1 and result.budget.spend.cost_usd >= 0.06
    assert result.checklist_reviews[0].unresolved and result.budget.spend.children == 1
    assert requirements.checklist(file.threads[0], file.facts,
                                  records=file.loop_records)[0].state is State.OUTSTANDING


@pytest.mark.parametrize("change", ["certainty", "denial", "withdrawn", "source", "need"])
def test_changed_material_subject_invalidates_the_receipt_without_erasing_history(tmp_path, change):
    store, _, _, _ = run_conversation(tmp_path)
    file = store.load("mat_loop")
    thread = file.threads[0]
    before = Outcome.restore(thread.requirement_outcomes[key(NEED)])
    assert classifications_for(thread, file.facts, file.loop_records)
    facts = file.facts
    if change in ("certainty", "denial", "withdrawn"):
        updates = ({"certainty": Certainty.DOCUMENTED} if change == "certainty"
                   else {"statement": "The notice was not served.", "exact_words": None}
                   if change == "denial"
                   else {"superseded_by": "new-fact"})
        facts = tuple(replace(row, **updates) if row.id == before.fact else row for row in facts)
    elif change == "source":
        thread = replace(thread, requirement_reads={NEED.locator: "changed-source"})
    else:
        thread = replace(thread, requirements=(replace(NEED, need="A different legal need"),))
    assert not classifications_for(thread, facts, file.loop_records)
    assert requirements.checklist(thread, facts,
                                  records=file.loop_records)[0].state is State.OUTSTANDING
    assert thread.requirement_outcomes == file.threads[0].requirement_outcomes
    assert before.state is State.HELD  # No automatic history deletion or re-authorship.


def test_unchanged_subject_does_not_expire_at_an_invented_daily_threshold(tmp_path):
    store, _, _, _ = run_conversation(tmp_path)
    file = store.load("mat_loop")
    far_later = datetime.now(timezone.utc) + timedelta(days=365)
    assert classifications_for(file.threads[0], file.facts, file.loop_records, now=far_later)
    before_recording = datetime(2000, 1, 1, tzinfo=timezone.utc)
    assert not classifications_for(file.threads[0], file.facts, file.loop_records,
                                    now=before_recording)


def test_missing_actual_law_refuses_review_before_spending_and_keeps_candidate(tmp_path):
    store, _, result, judge = run_conversation(tmp_path, read=False)
    file = store.load("mat_loop")
    assert result.stop == "review_refused" and not judge.prompts
    assert not classifications_for(file.threads[0], file.facts, file.loop_records)
    assert requirements.checklist(file.threads[0], file.facts,
                                  records=file.loop_records)[0].state is State.OUTSTANDING


def test_checklist_and_final_answer_reviews_share_one_whole_task_budget(tmp_path):
    store, _, result, judge = run_conversation(tmp_path, terminal="submit_answer", max_children=1)
    assert len(judge.prompts) == 1 and result.budget.spend.children == 1
    assert result.checklist_reviews[0].review.result.released
    # Finishing the last admitted child is permitted; a new merits review is not.
    assert result.stop == "budget" and not result.assessments
    file = store.load("mat_loop")
    assert classifications_for(file.threads[0], file.facts, file.loop_records)
    assert not file.turn_receipts


def test_final_answer_decoder_counts_supplemental_review_and_replays_without_new_spend(tmp_path):
    store, brain, result, judge = run_conversation(tmp_path, terminal="submit_answer")
    assert len(judge.prompts) == 2 and result.budget.spend.children == 2
    assert result.assessments and result.assessments[0].review.budget.spend.children == 2
    repeated = brain.review(result.attempts[0])
    assert repeated.budget.spend.children == 2 and len(judge.prompts) == 2
    assert len(store.load("mat_loop").loop_records) == 4


def test_conversational_label_cannot_skip_classification_review_or_release_the_text(tmp_path):
    store, _, result, judge = run_conversation(tmp_path, terminal="propose_conversation")
    assert result.stop == StopReason.CONVERSATION.value and len(judge.prompts) == 1
    assert result.checklist_reviews[0].review.result.released and not result.assessments
    assert not result.publications and not result.client_ready
    file = store.load("mat_loop")
    assert not file.turn_receipts
    assert requirements.checklist(file.threads[0], file.facts,
                                  records=file.loop_records)[0].state is State.HELD


def current_fixture_source(source, generation):
    """The exact held fixture reader's observed result, never a generic clear."""
    return source == finding() and generation == "generation-1"


def test_ordinary_reply_reuses_actual_cached_clause_without_an_extra_source_dispatch(tmp_path):
    store, brain, result, judge = run_conversation(tmp_path, read=False,
                                                  source_current=current_fixture_source)
    assert result.stop == StopReason.QUESTION.value and len(judge.prompts) == 1
    parent = result.attempts[0].record
    calls = [event.payload["call"]["name"] for event in parent.events
             if event.kind is StepKind.TOOL_STARTED]
    assert calls == ["record_requirement_answer", "ask_advocate"]
    assert brain.model.tool_call.call_count == 4  # Two setup calls, two reply calls, no reread.
    file = store.load("mat_loop")
    thread = file.threads[0]
    assert not classifications_for(thread, file.facts, file.loop_records)
    assert classifications_for(thread, file.facts, file.loop_records,
                               source_current=current_fixture_source)
    projection = requirements.context_projection(thread, file.facts, TODAY,
        records=file.loop_records, source_current=current_fixture_source)
    assert projection["items"][0]["state"] == "held" and projection["settled"]
    assert dispute_agenda.project(file, source_current=current_fixture_source
                                  )["disputes"][0]["requirements_settled"]
    assert summary.build(file, source_current=current_fixture_source
                         ).as_dict()["threads"][0]["requirements"]["held"] == 1
    # The same saved review is reconstructed with no additional model spend.
    repeated = brain.checklist_review.review(result.attempts[0])
    assert repeated.review.budget == result.checklist_reviews[0].review.budget
    assert len(judge.prompts) == 1


@pytest.mark.parametrize("read", [True, False])
def test_known_current_source_refusal_blocks_both_immediate_and_cached_review(tmp_path, read):
    store, _, result, judge = run_conversation(tmp_path, read=read,
        source_current=lambda source, generation: not current_fixture_source(source, generation))
    assert result.stop == "review_refused" and not judge.prompts
    file = store.load("mat_loop")
    assert not classifications_for(file.threads[0], file.facts, file.loop_records,
                                    source_current=current_fixture_source)


@pytest.mark.parametrize("change", ["generation", "withdrawn", "unavailable"])
def test_a_saved_positive_immediate_proof_cannot_override_actual_source_owner_refusal(
        tmp_path, change):
    store, _, _, _ = run_conversation(tmp_path, source_current=current_fixture_source)
    file = store.load("mat_loop")
    assert classifications_for(file.threads[0], file.facts, file.loop_records,
                               source_current=current_fixture_source)

    def changed_owner(source, generation):
        if change == "generation":
            return source == finding() and generation == "another-generation"
        return False  # The actual withdrawal/unavailable owner has no current read.

    assert not classifications_for(file.threads[0], file.facts, file.loop_records,
                                    source_current=changed_owner)
    assert not dispute_agenda.project(file, source_current=changed_owner
                                      )["disputes"][0]["requirements_settled"]


@pytest.mark.parametrize("change", ["matter", "actor", "source_generation"])
def test_cached_source_cannot_borrow_a_foreign_file_actor_or_read_generation(tmp_path, change):
    store, _, result, _ = run_conversation(tmp_path, read=False,
                                          source_current=current_fixture_source)
    file = store.load("mat_loop")
    original = next(row for row in file.loop_records if row.identity.turn_id == "package-turn")
    if change == "source_generation":
        def observer(source, generation):
            return source == finding() and generation == "foreign-version"
        records = file.loop_records
    else:
        # Diagnose raw supplied records: a foreign identity must never grant a
        # cached finding even when its words and full metadata match.
        identity = replace(original.identity,
            matter_id="foreign-matter" if change == "matter" else original.identity.matter_id,
            advocate_id="foreign-actor" if change == "actor" else original.identity.advocate_id)
        changed = SimpleNamespace(identity=identity, terminal=True, events=original.events)
        records = tuple(changed if row is original else row for row in file.loop_records)
        observer = current_fixture_source
    assert result.checklist_reviews[0].review.result.released
    assert not classifications_for(file.threads[0], file.facts, records, source_current=observer)
