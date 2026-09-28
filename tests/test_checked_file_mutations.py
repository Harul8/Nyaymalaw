"""P50 writes are current, attributed assertions; receipts never certify truth."""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date
from unittest.mock import Mock

import pytest

from nm.legal_brain.orchestrate.loop_contracts import StopReason
from nm.legal_brain.orchestrate.tools import (
    Boundary,
    PreparedToolResult,
    ToolContext,
    ToolRefused,
    ToolRegistry,
)
from nm.legal_brain.reason.issue_contracts import (
    Disposition,
    DispositionState,
    Issue,
    IssueKind,
    from_stored,
)
from nm.legal_brain.reason.requirements_contracts import (
    Force,
    Requirement,
    State,
    applicability_identity,
    checklist,
    key,
)
from nm.shared.model_port import SchemaViolation, ToolCall
from nm.shared.store_file_store import FileMatterStore
from nm.work_the_file import dependency
from nm.work_the_file.file_mutation import (
    MutationRefused,
    prepare_admission,
    prepare_correction,
    prepare_dispute,
    prepare_issue,
    prepare_requirement_answer,
)
from nm.work_the_file.file_mutation_contracts import FileMutation
from nm.work_the_file.matter_contracts import Certainty, Fact, Matter, Provenance, Side, Thread
from nm.work_the_file.write_tools import write_tools

pytestmark = pytest.mark.class_a
TODAY = date(2026, 9, 27)
WORDS = "The original is unavailable. I will provide the receipt tomorrow."
ALLOW = Boundary(True, "controlled attributed test scope")


def fixture():
    requirement = Requirement("Receipt", "It affects service", "The notice must be served.",
                              "Retrieved Act", "act:1", Force.REQUIRED, "source-version")
    first = Thread("thr_one", "First distinct matter", requirements=(requirement,))
    context = applicability_identity(first)
    first = replace(first, requirements=(replace(requirement, context_identity=context),),
                    requirement_reads={requirement.locator: requirement.source_identity},
                    requirement_read_contexts={requirement.locator: context})
    threads = (first,
               Thread("thr_two", "Second independent matter"))
    matter = Matter("mat_one", "adv_one", "Private file", threads=threads, version=7)
    return matter, {"advocate_id": matter.advocate_id, "current_version": matter.version,
                    "turn_id": "turn_one", "message": WORDS}


@pytest.mark.parametrize("words", ["The bank retained the instrument.",
                                  "I saw the boundary removed on Tuesday."])
def test_file_writes_use_trusted_messages_not_model_facts(words):
    matter, trusted = fixture()
    trusted["message"] = words
    mutation, detail = prepare_admission(matter, **trusted, quoted=words,
                                         thread_ids=("thr_one",))
    assert mutation.before == matter and not matter.facts
    assert mutation.after.version == matter.version and detail["asserted_only"]
    fact = mutation.after.facts[0]
    assert fact.statement == words == fact.exact_words
    assert fact.certainty is Certainty.ASSERTED and fact.confirmed is None
    assert fact.provenance == Provenance("advocate_statement", "turn_one", span=words)
    assert mutation.after.threads[0].chronology == (fact.id,)
    assert mutation.after.threads[1] == matter.threads[1]
    with pytest.raises(MutationRefused, match="original advocate message"):
        prepare_admission(matter, **trusted, quoted="A model's invented conclusion.",
                          thread_ids=("thr_one",))


def test_a_fresh_file_accepts_its_first_dispute_without_inventing_the_clients_side():
    matter, trusted = fixture()
    matter = replace(matter, threads=())
    mutation, detail = prepare_dispute(matter, **trusted, label="Service question", quoted=WORDS)
    thread = mutation.after.threads[0]
    assert thread.id == detail["thread_id"] and thread.chronology == (detail["fact_id"],)
    assert not thread.assessed and not thread.parties and not thread.posture.resolved
    assert not thread.requirements and not thread.deadlines
    assert mutation.after.facts[0].statement == WORDS
    assert mutation.after.version == matter.version
    with pytest.raises(MutationRefused, match="already recorded"):
        prepare_dispute(mutation.after, **trusted, label="Service question", quoted=WORDS)
    assert len(mutation.after.threads) == 1


def test_same_parties_and_similar_labels_never_silently_identify_or_merge_disputes():
    matter, trusted = fixture()
    statements = ("A and B dispute the title.", "A and B dispute the rent.")
    trusted["message"] = " ".join(statements)
    first, _ = prepare_dispute(matter, **trusted, label="A and B dispute", quoted=statements[0])
    second, _ = prepare_dispute(first.after, **trusted, label="A and B dispute",
                                 quoted=statements[1])
    assert len(second.after.threads) == 4
    assert second.after.threads[:2] == matter.threads
    assert second.after.threads[2].id != second.after.threads[3].id
    assert second.after.threads[2].chronology == second.after.threads[3].chronology
    assert len(second.after.facts) == 1
    assert second.after.facts[0].statement == trusted["message"]
    later_words = "A later issue concerns a different instrument."
    later, _ = prepare_dispute(second.after, **{**trusted,
        "message": later_words, "turn_id": "later"}, label="A and B disputes",
        quoted=later_words)
    assert later.after.threads[:4] == second.after.threads
    assert len(later.after.threads) == 5


def test_a_new_dispute_cannot_claim_a_completed_or_cleared_position():
    matter, trusted = fixture()
    mutation, _ = prepare_dispute(matter, **trusted, label="New question", quoted=WORDS)
    appended = mutation.after.threads[-1]
    for changed in (replace(appended, assessed=("review_current",)),
                    replace(appended, parties={"Invented client": "client"}),
                    replace(appended, requirement_reads={"not-read": "invented"})):
        with pytest.raises(ValueError, match="unassessed"):
            FileMutation(matter, replace(mutation.after,
                threads=(*mutation.after.threads[:-1], changed)), matter.advocate_id)


@pytest.mark.parametrize("message,selected", [
    ("Opposing counsel alleges payment was made, but our client denies it.", "payment was made"),
    ("If a receipt were signed, service might be established. No signed receipt is held.",
     "a receipt were signed"),
    ("The witness says the key was returned; I cannot confirm their account.",
     "the key was returned"),
    ("I previously said notice arrived, but that statement is inaccurate.", "notice arrived"),
])
def test_selected_spans_never_drop_attribution_denial_or_hypothetical_context(message, selected):
    matter, trusted = fixture()
    mutation, detail = prepare_admission(matter, **{**trusted, "message": message},
                                         quoted=selected, thread_ids=("thr_one",))
    fact = mutation.after.facts[0]
    assert fact.statement == fact.exact_words == fact.provenance.span == message
    assert detail["selected_span"] == selected
    assert fact.certainty is Certainty.ASSERTED and fact.confirmed is None


@pytest.mark.parametrize("changed", ["actor", "version", "unknown_thread", "duplicate_scope",
                                    "missing_original"])
def test_attribution_and_exact_dispute_scope_are_required(changed):
    matter, trusted = fixture()
    tids = ("thr_one",)
    if changed == "actor":
        trusted["advocate_id"] = "another"
    elif changed == "version":
        trusted["current_version"] -= 1
    elif changed == "missing_original":
        trusted["message"] = ""
    else:
        tids = ("foreign",) if changed == "unknown_thread" else ("thr_one", "thr_one")
    with pytest.raises(MutationRefused):
        prepare_admission(matter, **trusted, quoted=WORDS, thread_ids=tids)


def test_file_writes_cannot_change_permissions_or_journal_identity():
    matter, trusted = fixture()
    prepared, _ = prepare_admission(matter, **trusted, quoted=WORDS, thread_ids=("thr_one",))
    for changed in (replace(prepared.after, advocate_id="other"),
                    replace(prepared.after, title="Replaced without authority"),
                    replace(prepared.after, commission={"invented": "authority"}),
                    replace(prepared.after, version=matter.version + 1),
                    replace(prepared.after, turns_applied=("invented",))):
        with pytest.raises(ValueError):
            FileMutation(matter, changed, matter.advocate_id)
    fact = prepared.after.facts[0]
    for forged in (replace(fact, certainty=Certainty.DOCUMENTED),
                   replace(fact, confirmed=True), replace(fact, date=TODAY),
                   replace(fact, exact_words="The original")):
        with pytest.raises(ValueError, match="assertions"):
            FileMutation(matter, replace(prepared.after, facts=(forged,)), matter.advocate_id)


def test_nested_projection_tampering_is_detected_not_committed():
    matter, trusted = fixture()
    prepared, _ = prepare_admission(matter, **trusted, quoted=WORDS, thread_ids=("thr_one",))
    ident = prepared.identity
    prepared.after.dependencies["invented"] = "not the checked delta"
    with pytest.raises(ValueError, match="changed after"):
        _ = prepared.identity
    assert len(ident) == 64 and not matter.dependencies


@pytest.mark.parametrize("answer,quote,due,expected_due", [
    ("held", "The receipt gives the service date.", "", ""),
    ("unavailable", "The original is unavailable.", "", ""),
    ("promised", "I will provide the receipt tomorrow.", "tomorrow", "2026-09-28"),
    ("outstanding", "I do not know the service date.", "", ""),
])
def test_checklist_states_come_from_scoped_current_words_not_manual_ticks(
        answer, quote, due, expected_due):
    matter, trusted = fixture()
    trusted["message"] = quote
    req = key(matter.threads[0].requirements[0])
    mutation, _ = prepare_requirement_answer(matter, **trusted, thread_id="thr_one",
        requirement_key=req, answer=answer, quoted=quote, due_expression=due, today=TODAY)
    item = checklist(mutation.after.threads[0], mutation.after.facts)[0]
    assert item.state is State.OUTSTANDING
    assert item.outcome.state is State(answer) and item.outcome.requires_review
    assert item.outcome.basis == quote and item.outcome.due == expected_due
    assert mutation.after.facts[0].certainty is Certainty.ASSERTED
    assert mutation.after.threads[1] == matter.threads[1]
    assert mutation.after.version == matter.version


@pytest.mark.parametrize("key_change,quote,due", [
    ("missing", WORDS, ""), (None, "Invented source", ""),
    (None, "The original is unavailable.", "next year"),
])
def test_unaccepted_checklist_answers_do_not_claim_a_successful_write(key_change, quote, due):
    matter, trusted = fixture()
    with pytest.raises(MutationRefused):
        prepare_requirement_answer(matter, **trusted, thread_id="thr_one",
            requirement_key=key_change or key(matter.threads[0].requirements[0]),
            answer="promised", quoted=quote, due_expression=due, today=TODAY)
    assert not matter.facts and not matter.threads[0].requirement_outcomes


def test_correction_preserves_prior_account_and_invalidates_exact_dependent_closure():
    matter, trusted = fixture()
    old = Fact("fact_old", "The account I am correcting.", Provenance("advocate_statement", "old"))
    independent = Fact("fact_other", "Independent account.",
                       Provenance("advocate_statement", "old"))
    matter = replace(matter, facts=(old, independent), threads=(
        replace(matter.threads[0], chronology=(old.id,)),
        replace(matter.threads[1], chronology=(independent.id,))))
    ledger, _, _ = dependency.sync_inputs(dependency.Ledger(), matter)
    for name, source in (("affected", old.id), ("independent", independent.id)):
        ledger = dependency.record(ledger, dependency.Node(name, "prior value", shown=name,
            rests_on=(dependency.Rest(dependency.InputKind.FACT, source, 1),)))
    ledger = dependency.record(ledger, dependency.Node(
        "transitive", "prior consequence", shown="dependent",
        rests_on=(dependency.Rest(dependency.InputKind.DERIVED, "affected", 1),)))
    matter = replace(matter, dependencies=ledger.as_dict())
    mutation, detail = prepare_correction(matter, **trusted, old_fact_id=old.id,
                                          quoted=WORDS, today=TODAY)
    assert mutation.after.fact(old.id).statement == old.statement
    assert mutation.after.fact(old.id).superseded_by == detail["fact_id"]
    updated = dependency.Ledger.from_stored(mutation.after.dependencies)
    assert updated.node("affected").currency is dependency.Currency.STALE
    assert updated.node("transitive").currency is dependency.Currency.STALE
    assert updated.node("independent") == ledger.node("independent")
    assert set(detail["stale_nodes"]) == {"affected", "transitive"}
    assert mutation.after.threads[1] == matter.threads[1]
    assert mutation.after.version == matter.version


def test_grounded_issue_append_preserves_every_standing_identity_and_disposition():
    matter, trusted = fixture()
    standing = Issue("thr_one", "Existing question", id="iss_existing",
        kind=IssueKind.PROCEDURAL, runs_against=Side.MOVING, proof="Original account",
        disposition=Disposition(DispositionState.PARKED, "A recorded reason"),
        serves_theory="theory-one", provisions=("section-one",), authorities=("case-one",),
        deadline="deadline-one")
    matter = replace(matter, threads=(replace(matter.threads[0], issues=(asdict(standing),)),
                                      matter.threads[1]))
    mutation, _ = prepare_issue(matter, **trusted, thread_id="thr_one",
        statement="What follows if the original cannot be obtained?", kind="substantive",
        runs_against="unknown", quoted="The original is unavailable.")
    assert mutation.after.threads[0].issues[0] == asdict(standing)
    assert from_stored(mutation.after.threads[0].issues)[0] == standing
    assert len(mutation.after.threads[0].issues) == 2
    assert not mutation.after.facts


def test_a_later_requirement_answer_keeps_the_previous_answer_and_rejects_false_ticks():
    matter, trusted = fixture()
    req = key(matter.threads[0].requirements[0])
    first, _ = prepare_requirement_answer(matter, **trusted, thread_id="thr_one",
        requirement_key=req, answer="promised", quoted=WORDS,
        due_expression="tomorrow", today=TODAY)
    later = "The receipt supplies the service date."
    second, _ = prepare_requirement_answer(first.after, **{**trusted,
        "turn_id": "later_turn", "message": later}, thread_id="thr_one",
        requirement_key=req, answer="held", quoted=later, due_expression="", today=TODAY)
    outcome = second.after.threads[0].requirement_outcomes[req]
    assert outcome["history"][-1]["state"] == "promised"
    forged = {**outcome, "history": []}
    with pytest.raises(ValueError, match="history"):
        FileMutation(first.after, replace(second.after, threads=(
            replace(second.after.threads[0], requirement_outcomes={req: forged}),
            second.after.threads[1])), matter.advocate_id)
    forged = {**outcome, "fact": "a-nonexistent-fact"}
    with pytest.raises(ValueError, match="scoped attributed fact"):
        FileMutation(first.after, replace(second.after, threads=(
            replace(second.after.threads[0], requirement_outcomes={req: forged}),
            second.after.threads[1])), matter.advocate_id)


def test_prepared_write_tools_never_commit_and_still_pass_both_registry_boundaries():
    from tests.test_legal_brain_tool_catalogue import fixture as read_fixture

    matter, _ = fixture()
    store = Mock(load=Mock(return_value=matter))
    _, context, *_ = read_fixture()
    context = ToolContext(replace(context.identity, matter_version=matter.version),
                          original_message=WORDS)
    tools = write_tools(store, today=lambda: TODAY)
    before, after = Mock(return_value=ALLOW), Mock(return_value=ALLOW)
    registry = ToolRegistry(tools, before=before, after=after)
    args = {"quoted": WORDS, "thread_ids": ["thr_one"]}
    result = registry.invoke(ToolCall("write-one", "write_fact", args), context)
    assert isinstance(result, PreparedToolResult)
    assert result.envelope.receipt["snapshot"] == result.mutation.identity
    before.assert_called_once()
    after.assert_called_once()
    store.commit.assert_not_called()
    for denied in ("before", "after"):
        boundary = Mock(return_value=Boundary(False, "not authorized"))
        blocked = ToolRegistry(tools, before=boundary if denied == "before" else before,
                               after=boundary if denied == "after" else after)
        with pytest.raises(ToolRefused):
            blocked.invoke(ToolCall("denied", "write_fact", args), context)
    with pytest.raises(SchemaViolation):
        registry.invoke(ToolCall("forged", "write_fact", {**args, "advocate_id": "other"}), context)
    store.commit.assert_not_called()


def test_actual_controlled_loop_applies_assertion_and_receipt_in_one_saved_version(tmp_path):
    from tests.test_the_controlled_brain_is_actually_wired import _brain
    from tests.test_the_loop_records_work_before_using_it import _limits, _response

    store, model, brain = _brain(tmp_path)
    initial = store.load("mat_loop")
    store.commit(replace(initial, threads=(Thread("thr_one", "Recorded question"),),
                         version=initial.version + 1), expected_version=initial.version)
    brain.registry = brain.registry.extend(write_tools(store, today=lambda: TODAY))
    brain._runner._tools = brain.registry
    model.tool_call.side_effect = [
        _response(ToolCall("w1", "write_fact", {"quoted": WORDS, "thread_ids": ["thr_one"]})),
        _response(ToolCall("p1", "submit", {"answer": "An unchecked candidate."})),
    ]
    outcome = brain.run(matter_id="mat_loop", turn_id="write_turn", message=WORDS,
                        limits=_limits())
    assert outcome.reason is StopReason.PROPOSAL
    restored = FileMatterStore(tmp_path, key="isolated-loop-key").load("mat_loop")
    assert restored.facts[0].statement == WORDS and len(restored.facts) == 1
    assert restored.loop_records == (outcome.record,)
    assert restored.version == outcome.record.identity.matter_version + len(outcome.record.events)
    changes = [event for event in outcome.record.events if "mutation_identity" in event.payload]
    assert len(changes) == 1 and changes[0].payload["checked_snapshot"]
    assert not restored.turn_receipts, "a file assertion is not released advice"


def test_the_actual_first_input_can_create_and_work_an_unassessed_dispute(tmp_path):
    from tests.test_the_controlled_brain_is_actually_wired import _brain
    from tests.test_the_loop_records_work_before_using_it import _limits, _response

    store, model, brain = _brain(tmp_path)
    assert not store.load("mat_loop").threads
    brain.registry = brain.registry.extend(write_tools(store, today=lambda: TODAY))
    brain._runner._tools = brain.registry

    def respond(*_args, **_kw):
        if model.tool_call.call_count == 1:
            return _response(ToolCall("new", "create_dispute", {
                "label": "Availability of original material", "quoted": WORDS}))
        if model.tool_call.call_count == 2:
            tid = store.load("mat_loop").threads[0].id
            return _response(ToolCall("question", "add_issue", {
                "thread_id": tid, "statement": "What does the unavailable original affect?",
                "kind": "substantive", "runs_against": "unknown",
                "quoted": "The original is unavailable."}))
        return _response(ToolCall("done", "submit", {"answer": "An unreleased assessment."}))

    model.tool_call.side_effect = respond
    outcome = brain.run(matter_id="mat_loop", turn_id="first_input", message=WORDS,
                        limits=_limits())
    assert outcome.reason is StopReason.PROPOSAL
    saved = store.load("mat_loop")
    assert len(saved.threads) == 1 and len(saved.facts) == 1
    assert len(from_stored(saved.threads[0].issues)) == 1
    assert not saved.threads[0].posture.resolved and not saved.threads[0].assessed
    assert saved.version == outcome.record.identity.matter_version + len(outcome.record.events)
    assert len([e for e in outcome.record.events if "mutation_identity" in e.payload]) == 2
