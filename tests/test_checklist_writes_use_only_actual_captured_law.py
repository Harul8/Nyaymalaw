"""Grounded checklist proposals use the same atomic file/journal transaction."""
from dataclasses import replace

import pytest
from nm.adapters.store.file_store import FileMatterStore
from nm.core.source_writes import SourceRequirementMutation, source_write_tools
from nm.core.tools import PreparedToolResult
from nm.domain.file_mutation import FileMutation
from nm.domain.loop import LoopLimits, StepKind, StopReason
from nm.domain.matter import Thread
from nm.domain.requirements import Force, Requirement, State, checklist
from nm.ports.model import ToolCall

from tests.test_claims_reach_the_independent_review_from_the_saved_loop import _case
from tests.test_independent_claim_verifier import finding
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a

PRIOR = Requirement("Earlier material", "An earlier exact clause", "Earlier recorded clause.",
                    "Earlier source", "old:clause", Force.STRENGTHENING, "old-source")
ROW = {"need": "The notice", "why": "The retrieved clause conditions the benefit on notice.",
       "span": "A benefit requires notice.", "locator": finding().locator, "force": "required"}


def _run(tmp_path, *, rows=None, read=True, source_version="generation-1", narrow=False):
    threads = (Thread("thr_notice", "Notice question", requirements=(PRIOR,)),
               Thread("thr_other", "Independent question"))
    store, brain, initial, _, claim = _case(tmp_path, threads=threads)
    tools = source_write_tools(store, source_version=source_version)
    prepared = []
    original = tools[0].handler

    def observe(*args):
        value = original(*args)
        if isinstance(value, PreparedToolResult):
            prepared.append(value.mutation)
        return value

    tools = (replace(tools[0], handler=observe),)
    brain.registry = brain.registry.extend(tools)
    brain._runner._tools = brain.registry
    calls = ([ToolCall("read-law", "read_provision", {
        "act": "Recorded primary rule", "section": "1", "as_of": "2026-01-01"})]
             if read else [])
    calls.extend((ToolCall("checklist", "record_requirements", {
        "thread_id": "thr_notice", "requirements": rows if rows is not None else [ROW]}),
        ToolCall("done", "submit_answer", {"claims": [claim]})))
    brain.model.tool_call.side_effect = [replace(_response(call),
        provider="scripted", model="scripted:author") for call in calls]
    outcome = brain.run(matter_id="mat_loop", turn_id="checklist-turn",
        message="Assess the material needed for the notice question.",
        selected_issue_ids=("thr_other",) if narrow else (),
        limits=LoopLimits(initial.budget, 10, 500))
    return store, brain, outcome, prepared


def test_requirements_use_the_actual_parent_read_and_shared_merge(tmp_path):
    store, _, outcome, prepared = _run(tmp_path)
    assert outcome.reason is StopReason.PROPOSAL and len(prepared) == 1
    actual = FileMatterStore(tmp_path, key="isolated-loop-key").load("mat_loop")
    assert Requirement.restore(actual.threads[0].requirements[0]) == PRIOR
    new = Requirement.restore(actual.threads[0].requirements[1])
    assert new.span == ROW["span"] and new.locator == finding().locator and new.source_identity
    assert new.force is Force.REQUIRED
    assert not actual.threads[0].assessed and not actual.threads[0].requirement_outcomes
    assert all(row.state is State.OUTSTANDING for row in checklist(actual.threads[0]))
    assert not actual.threads[1].requirements and not actual.turn_receipts
    saved = next(event for event in outcome.record.events if "mutation_identity" in event.payload)
    assert saved.kind is StepKind.TOOL_RETURNED
    assert saved.payload["receipt"]["assessment"] == "not_assessed"
    assert saved.payload["receipt"]["data"]["legal_interpretation"] == "not_assessed"
    assert saved.payload["mutation_identity"] == prepared[0].identity


@pytest.mark.parametrize("changes", [
    {"rows": [{**ROW, "locator": "somewhere:else"}]},
    {"rows": [{**ROW, "span": "A remembered rule the retrieved passage does not carry."}]},
    {"rows": [{**ROW, "span": "notice"}]}, {"rows": [ROW, ROW]},
    {"rows": [ROW, {**ROW, "need": "The same notice in different words"}]},
    {"read": False}, {"source_version": "another-generation"}, {"narrow": True},
])
def test_a_source_write_cannot_promote_guessed_or_foreign_law_into_a_checklist(tmp_path, changes):
    store, _, outcome, prepared = _run(tmp_path, **changes)
    assert outcome.reason is StopReason.REFUSED
    assert not prepared
    assert tuple(Requirement.restore(row) for row in
                 store.load("mat_loop").threads[0].requirements) == (PRIOR,)


@pytest.mark.parametrize("mutation", ["erase", "reviewed", "held", "client", "span"])
def test_requirement_proposals_cannot_certify_answers_or_delete_prior_work(tmp_path, mutation):
    _, _, _, prepared = _run(tmp_path)
    proposal = prepared[0]
    thread = proposal.after.threads[0]
    if mutation == "erase":
        thread = replace(thread, requirements=thread.requirements[1:])
    elif mutation == "reviewed":
        thread = replace(thread, assessed=("review_current",))
    elif mutation == "held":
        thread = replace(thread, requirement_outcomes={"unknown": {
            "state": "held", "basis": "Model says held", "at": "now", "fact": "invented"}})
    elif mutation == "client":
        thread = replace(thread, parties={"Invented client": "client"})
    else:
        thread = replace(thread, requirements=(PRIOR,
            replace(thread.requirements[1], span="A fabricated quotation.")))
    after = replace(proposal.after, threads=(thread, proposal.after.threads[1]))
    with pytest.raises(ValueError, match="mutation|assessment|requirement|dispute"):
        SourceRequirementMutation(proposal.before, after, proposal.advocate_id,
            proposal.thread_id, proposal.turn_id, proposal.source_version, proposal.proposed)
    # The default assertion mutation still has no authority to write legal rows.
    with pytest.raises(ValueError, match="unapproved dispute field"):
        FileMutation(proposal.before, proposal.after, proposal.advocate_id)


def test_the_atomic_writer_refuses_an_arbitrary_subclass_that_skips_validation(tmp_path):
    from nm.domain.loop import LoopEvent

    store, brain, outcome, prepared = _run(tmp_path)

    class Untrusted(FileMutation):
        def _validate_projection(self):
            pass

    before = store.load("mat_loop")
    forged = Untrusted(before, replace(before, advocate_id="other-actor"), before.advocate_id)
    event = LoopEvent.create(len(outcome.record.events) + 1, StepKind.TOOL_RETURNED,
        outcome.record.events[-1].at, {"mutation_identity": forged.identity},
        outcome.record.events[-1].fingerprint)
    with pytest.raises(ValueError, match="exact committed tool receipt"):
        brain.log.append_mutation(outcome.record.identity, event, forged)
    assert store.load("mat_loop") == before
    assert type(prepared[0]) is SourceRequirementMutation
