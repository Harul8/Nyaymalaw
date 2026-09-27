"""Real registry dispatch uses the source-owned interest contract exactly once."""
from dataclasses import replace
from unittest.mock import Mock

import pytest

from nm.legal_brain.loop_contracts import StopReason
from nm.shared.model_port import ToolCall
from nm.work_the_file.matter_contracts import Thread
from tests.test_controlled_brain_composition_keeps_the_account_boundary import _compose, _scope
from tests.test_the_loop_records_work_before_using_it import _limits, _response

pytestmark = pytest.mark.class_a


def test_real_composition_has_one_interest_owner_and_missing_review_cannot_compute(client):
    app, matter, scope = _scope(client)
    app.store.commit(replace(matter, threads=(Thread("one", "A recorded dispute"),),
                             version=matter.version + 1), expected_version=matter.version)
    author = Mock()
    author.provider = "scripted"
    author.resolved_model.return_value = "recorded-v1"
    author.context_budget.return_value = 100000
    author.tool_call.side_effect = [
        _response(ToolCall("inspect", "inspect_tool", {"name": "compute_interest"})),
        _response(ToolCall("compute", "compute_interest", {
            "thread_id": "one", "selection_id": "no-review-record"})),
        _response(ToolCall("question", "ask_advocate", {
            "question": "Which document records the agreed interest terms?"}))]
    app.model.inner.inner = author
    brain = _compose(app, scope)
    population = [row for row in brain.registry.definitions if row.name == "compute_interest"]
    assert len(population) == 1
    assert set(population[0].parameters["properties"]) == {"thread_id", "selection_id"}
    outcome = brain.run(matter_id=matter.id, turn_id="interest-composition",
        message="Check the recorded contractual interest.", limits=_limits())
    assert outcome.reason is StopReason.QUESTION
    receipts = [event.payload["receipt"] for event in outcome.record.events
        if event.kind.value == "tool_returned"
        and event.payload["receipt"]["tool"] == "compute_interest"]
    assert len(receipts) == 1
    assert receipts[0]["data"] == {} and receipts[0]["assessment"] == "not_assessed"
    assert receipts[0]["availability"] == "unavailable"
    assert "source literals" in receipts[0]["receipt"]["method"]
    current = app.store.load(matter.id)
    assert not current.turn_receipts and not current.facts
    assert current.threads[0].id == "one" and not current.threads[0].deadlines
