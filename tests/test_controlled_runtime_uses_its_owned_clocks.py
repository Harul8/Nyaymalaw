"""The real caller/runner/context/retry share supplied clocks, never prompt dates."""
import json
from datetime import date, datetime, timezone

import pytest

from nm.legal_brain.controlled_brain import ControlledBrain
from nm.legal_brain.loop_contracts import StopReason
from nm.shared.model_port import ToolCall
from tests.test_the_controlled_brain_is_actually_wired import _brain
from tests.test_the_loop_records_work_before_using_it import _limits, _response

pytestmark = pytest.mark.class_a


def test_real_caller_context_events_elapsed_and_retry_keep_actual_clock_owners(tmp_path):
    store, model, original = _brain(tmp_path)
    now = datetime(2032, 4, 9, 18, 20, tzinfo=timezone.utc)
    forum_day = date(2032, 4, 10)
    ticks, dates, clocks = [], [], []

    def monotonic():
        value = 12.0 + len(ticks) * 0.01
        ticks.append(value)
        return value

    def today():
        dates.append(forum_day)
        return forum_day

    def clock():
        clocks.append(now)
        return now

    brain = ControlledBrain(store=store, model=model, principles=original.principles,
        log=original.log, registry=original.registry, scope=original.scope,
        cost_ceiling=lambda *_: 0.03, session_current=lambda: True,
        clock=clock, monotonic=monotonic, today=today)
    model.tool_call.return_value = _response(
        ToolCall("q1", "submit", {"answer": "Check the file."}))
    initial = store.load("mat_loop")
    outcome = brain.run(matter_id=initial.id, turn_id="owned-clock",
        message="An instruction mentioning 1901 is not the runtime date.", limits=_limits())
    assert outcome.reason is StopReason.PROPOSAL
    assert all(event.at == now.isoformat() for event in outcome.record.events)
    captured = outcome.record.events[0].payload["context"]
    assert json.loads(captured["brief"]["text"])["data"]["checklist_context_as_of"] == "2032-04-10"
    assert dates == [forum_day]
    assert len(ticks) > 1 and clocks
    assert outcome.budget.spend.elapsed_ms > 0
    spent_ticks, spent_clocks = len(ticks), len(clocks)
    again = brain.run(matter_id=initial.id, turn_id="owned-clock",
        message="An instruction mentioning 1901 is not the runtime date.", limits=_limits())
    assert again == outcome and model.tool_call.call_count == 1
    assert len(ticks) == spent_ticks and len(clocks) == spent_clocks
    assert dates == [forum_day] * 3  # New brief plus retry-currentness read.
    current = store.load(initial.id)
    assert current.facts == initial.facts and current.threads == initial.threads
    assert not current.turn_receipts


@pytest.mark.parametrize("owner", ["clock", "monotonic", "today"])
def test_serialized_or_model_authored_clock_values_are_not_runtime_owners(tmp_path, owner):
    store, model, original = _brain(tmp_path)
    with pytest.raises(ValueError, match="clock owners"):
        ControlledBrain(store=store, model=model, principles=original.principles,
            log=original.log, registry=original.registry, scope=original.scope,
            cost_ceiling=lambda *_: 0.03, session_current=lambda: True,
            **{owner: "2032-04-10"})
    assert model.tool_call.call_count == 0
    assert not store.load("mat_loop").loop_records
