"""A delegated source-set digest never substitutes for its actual read generation."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from nm.legal_brain.procedure.calculation_tools import CalculationSource, _source_on_file
from nm.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult
from nm.legal_brain.orchestrate.loop_contracts import StepKind, StopReason
from nm.legal_brain.reason.source_writes import source_write_tools
from nm.legal_brain.retrieve.tool_sources import findings_from_record, source_envelope
from nm.shared.model_port import ToolCall
from tests.test_independent_claim_verifier import finding
from tests.test_nested_research_has_one_budget_and_one_writer import finish, run, setup
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
GENERATION = "recorded-source-v1"


def child_only_source(tmp_path, *, primary=True, current_generation=GENERATION):
    def read(_args, _context):
        result = EvidenceResult(Coverage.ANSWERED, (finding(),), searched_stores=("held",))
        return source_envelope("read_law", "held-v1", "held", GENERATION, (), {},
                               primary_reads=(result,) if primary else (),
                               reason="Support remains unassessed.")

    store, model, brain, _ = setup(tmp_path, source_handler=read)
    brain.registry = brain.registry.extend(source_write_tools(
        store, source_version=current_generation))
    brain._runner._tools = brain.registry
    count = 0

    def reply(prompt, *_args, **_kwargs):
        nonlocal count
        if prompt.operation != "controlled_legal_brain":
            count += 1
            return _response(ToolCall("read-child", "read_law", {})) if count == 1 else _response(
                finish())
        if model.tool_call.call_count == 1:
            return _response(ToolCall("delegate", "research", {
                "question": "Read the source for the notice requirement.",
                "issue_ids": ["dispute_one"]}))
        if model.tool_call.call_count == 4:
            return _response(ToolCall("record", "record_requirements", {
                "thread_id": "dispute_one", "requirements": [{
                    "need": "The notice", "why": "The exact clause requires notice.",
                    "span": "A benefit requires notice.", "locator": finding().locator,
                    "force": "required"}]}))
        return _response(ToolCall("finish-parent", "submit", {"answer": "Private proposal."}))

    model.tool_call.side_effect = reply
    outcome = run(brain)
    event = next(row for row in outcome.record.events if row.kind is StepKind.TOOL_RETURNED
                 and row.payload["call_id"] == "delegate")
    source = CalculationSource(outcome.record.identity.turn_id, "delegate",
                               event.fingerprint, finding())
    return store.load("mat_loop"), outcome, event, source


def test_actual_child_generation_feeds_checklist_and_exact_primary_calculation_receipt(tmp_path):
    file, outcome, event, source = child_only_source(tmp_path)
    assert outcome.reason is StopReason.PROPOSAL
    assert event.payload["receipt"]["receipt"]["source_version"] != GENERATION
    assert findings_from_record(outcome.record, source_version=GENERATION) == (finding(),)
    assert findings_from_record(outcome.record, source_version="foreign-generation") == ()
    assert file.threads[0].requirements and not file.threads[0].requirement_outcomes
    result = _source_on_file(file, source, GENERATION)
    assert result and result["source_version"] == GENERATION
    assert result["original_reader"] == "read_law"
    assert _source_on_file(file, source, "foreign-generation") is None


def test_wrong_current_generation_cannot_relabel_a_child_read_as_current(tmp_path):
    file, outcome, _, source = child_only_source(tmp_path, current_generation="foreign-generation")
    assert outcome.reason is StopReason.REFUSED and not file.threads[0].requirements
    assert _source_on_file(file, source, "foreign-generation") is None


@pytest.mark.parametrize("change", ["count", "missing_start", "reader", "promote_aggregate"])
def test_aggregate_dictionary_and_broken_child_correlation_never_become_owned_law(tmp_path, change):
    _, outcome, event, _ = child_only_source(tmp_path)
    payload = deepcopy(event.payload)
    if change == "count":
        payload["child_steps"] += 1
    elif change == "missing_start":
        payload["child_transcript"] = [row for row in payload["child_transcript"]
                                       if row["kind"] != "tool_started"]
        payload["child_steps"] = sum(row["kind"] == "model_started"
                                     for row in payload["child_transcript"])
    elif change == "reader":
        next(row for row in payload["child_transcript"] if row["kind"] == "tool_returned"
             )["receipt"]["tool"] = "another-read"
    else:
        # Delete actual reads but retain an aggregate claiming exactly the same law.
        payload["child_transcript"] = []
        payload["child_steps"] = 0
    # Exercise the pure decoder with a corrupted input, not fabricate a sealed
    # LoopEvent that the real journal constructor would already refuse.
    changed = SimpleNamespace(kind=event.kind, payload=payload)
    record = SimpleNamespace(events=tuple(changed if row is event else row
                                          for row in outcome.record.events))
    if change == "promote_aggregate":
        assert findings_from_record(record, source_version=GENERATION) == ()
    else:
        with pytest.raises(ValueError):
            findings_from_record(record, source_version=GENERATION)
