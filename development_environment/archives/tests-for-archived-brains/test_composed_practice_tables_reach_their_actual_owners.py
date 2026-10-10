"""A declared curated capability reaches its actual owner in the served composition."""
from dataclasses import fields
from unittest.mock import Mock

import pytest

from nm.Archives.legal_brain.procedure.governing_law_port import Limb, Pending
from nm.Archives.legal_brain.orchestrate.loop_contracts import StopReason
from nm.Archives.legal_brain.orchestrate.tools import Assessment
from nm.shared.model_port import ToolCall
from tests.test_controlled_brain_composition_keeps_the_account_boundary import _compose, _scope
from tests.test_the_loop_records_work_before_using_it import _limits, _response

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("limb", list(Limb))
def test_composed_governing_lookup_reaches_curation_without_inventing_unknown_premises(
        client, limb):
    app, matter, scope = _scope(client)
    model = Mock()
    model.provider = "scripted"
    model.resolved_model.return_value = "recorded-v1"
    model.context_budget.return_value = 100000
    model.tool_call.side_effect = [
        _response(ToolCall("inspect", "inspect_tool", {"name": "governing_code"})),
        _response(ToolCall("lookup", "governing_code", {
            "limb": limb.value, "on": None, "pending": Pending.UNKNOWN.value})),
        _response(ToolCall("question", "ask_advocate", {"question": "Which date is recorded?"}))]
    app.model.inner.inner = model
    output = _compose(app, scope).run(matter_id=matter.id, turn_id=f"governing-{limb.value}",
                                      message="Check the recorded governing-law uncertainty.",
                                      limits=_limits())
    assert output.reason is StopReason.QUESTION
    results = [event.payload["receipt"] for event in output.record.events
               if event.kind.value == "tool_returned"
               and event.payload["receipt"]["tool"] == "governing_code"]
    assert len(results) == 1
    result = results[0]
    assert result["availability"] != "unavailable", result
    assert result["assessment"] == Assessment.NOT_ASSESSED.value
    assert result["data"]["guide"][0]["act"] == ""
    assert result["data"]["guide"][0]["rule"]["limb"] == limb.value
    assert result["data"]["guide"][0]["curated_from"].strip()


def test_composed_practice_table_population_is_explicit_and_complete(client, monkeypatch):
    from nm.Archives.legal_brain.orchestrate import tool_catalogue

    app, _, scope = _scope(client)
    captured = []
    actual = tool_catalogue.catalogue_tools

    def capture(*args, **kwargs):
        captured.append(kwargs["tables"])
        return actual(*args, **kwargs)

    monkeypatch.setattr(tool_catalogue, "catalogue_tools", capture)
    _compose(app, scope)
    assert len(captured) == 1
    population = [row.name for row in fields(tool_catalogue.PracticeTables)
                  if row.name != "version"]
    assert population and "governing" in population
    missing = [name for name in population if getattr(captured[0], name) is None]
    assert not missing, missing
