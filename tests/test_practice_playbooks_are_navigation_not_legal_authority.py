"""Owner guidance is inspectable/versioned, not a substitute for retrieved law."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nm.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult
from nm.legal_brain.retrieve.practice_playbooks import playbook_tools
from nm.legal_brain.retrieve.practice_playbooks_adapter import FilePracticePlaybooks
from nm.legal_brain.retrieve.practice_playbooks_port import PlaybooksSnapshot, PlaybooksUnavailable
from nm.legal_brain.common.principles_file_adapter import FilePrinciples
from nm.legal_brain.orchestrate.tools import Assessment, ToolRefused

pytestmark = pytest.mark.class_a
CONTEXT = SimpleNamespace(identity=SimpleNamespace(turn_id="playbook-test"))


def _snapshot(body):
    return PlaybooksSnapshot(json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False))


def test_playbook_tools_keep_guidance_distinct_from_law_and_permission():
    port = FilePracticePlaybooks()
    snapshot = port.load()
    assert {row["id"] for row in snapshot.catalogue} == {
        "cheque-dishonour", "tenancy", "partition", "money-recovery", "bail"}
    evidence = Mock()
    evidence.read_provision.return_value = EvidenceResult(
        Coverage.NOT_HELD, missing="The pointed provision is not held in this test population.")
    tools = {row.definition.name: row for row in playbook_tools(
        port, snapshot=snapshot, evidence=evidence)}
    catalogue = tools["read_playbook_catalogue"].handler({}, CONTEXT)
    assert catalogue.data["population"] == 5
    assert not catalogue.data["grants_permission"]
    result = tools["read_practice_playbook"].handler({"id": "cheque-dishonour"}, CONTEXT)
    assert result.assessment is Assessment.NOT_ASSESSED
    assert not result.data["establishes_facts_or_law"]
    assert result.data["pointers"][0]["state"] == "not_located"
    pointer = result.data["playbook"]["pointers"][0]
    evidence.read_provision.assert_called_once_with(pointer["act"], pointer["section"], as_of=None)
    with pytest.raises(ToolRefused, match="exact playbook"):
        tools["read_practice_playbook"].handler({"id": "a-party-named-in-the-case"}, CONTEXT)


@pytest.mark.parametrize("mutation", ["empty", "duplicate", "unknown_field", "pointer_url",
                                      "rule_flag", "multiline", "boolean_schema"])
def test_playbook_population_and_closed_shape_refuse_false_catalogues(mutation):
    body = FilePracticePlaybooks().load().payload
    if mutation == "empty":
        body["playbooks"] = []
    elif mutation == "duplicate":
        body["playbooks"].append(body["playbooks"][0])
    elif mutation == "unknown_field":
        body["playbooks"][0]["verified"] = True
    elif mutation == "pointer_url":
        body["playbooks"][0]["pointers"][0]["url"] = "https://not-a-held-source.invalid"
    elif mutation == "rule_flag":
        body["playbooks"][0]["pointers"][0]["current"] = True
    elif mutation == "multiline":
        body["playbooks"][0]["summary"] += "\nAnother line"
    else:
        body["schema"] = True
    with pytest.raises(ValueError):
        _snapshot(body)


def test_playbook_changes_move_the_actual_owner_prefix_and_refuse_midturn_reads():
    port = Mock()
    snapshot = FilePracticePlaybooks().load()
    port.load.return_value = snapshot
    before = FilePrinciples(playbooks=port).load()
    assert "OWNER-EDITED PRACTICE NAVIGATION CATALOGUE" in before.text
    assert before.text.count('"id": "cheque-dishonour"') == 1
    assert snapshot.payload["playbooks"][0]["guidance"] not in before.text
    tool = playbook_tools(port, snapshot=snapshot, evidence=Mock())[0]
    body = snapshot.payload
    body["playbooks"][0]["guidance"] += " Review a newly supplied source independently."
    port.load.return_value = _snapshot(body)
    assert FilePrinciples(playbooks=port).load().version != before.version
    with pytest.raises(ToolRefused, match="changed"):
        tool.handler({}, None)


def test_actual_composition_installs_owner_playbooks_without_an_extra_model_call(client):
    from nm.shared.model_port import ToolCall
    from tests.test_controlled_brain_composition_keeps_the_account_boundary import _compose, _scope
    from tests.test_the_loop_records_work_before_using_it import _limits, _response

    app, matter, scope = _scope(client)
    author = Mock()
    author.provider = "scripted"
    author.resolved_model.return_value = "recorded-v1"
    author.context_budget.return_value = 100000
    author.tool_call.side_effect = [
        _response(ToolCall("inspect", "inspect_tool", {"name": "read_playbook_catalogue"})),
        _response(ToolCall("catalogue", "read_playbook_catalogue", {})),
        _response(ToolCall("ask", "ask_advocate", {"question": "Which document is held?"}))]
    app.model.inner.inner = author
    result = _compose(app, scope).run(matter_id=matter.id, turn_id="playbook-navigation",
                                     message="Review the available material.", limits=_limits())
    assert author.tool_call.call_count == 3
    assert "OWNER-EDITED PRACTICE NAVIGATION CATALOGUE" in result.record.events[0].payload[
        "context"]["system"]
    returned = [row.payload["receipt"] for row in result.record.events
        if row.kind.value == "tool_returned" and row.payload["receipt"]["tool"]
        == "read_playbook_catalogue"]
    assert len(returned) == 1 and returned[0]["data"]["population"] == 5
    assert not app.store.load(matter.id).turn_receipts


def test_owner_file_cannot_silently_reuse_a_missing_copy(tmp_path):
    with pytest.raises(PlaybooksUnavailable):
        FilePracticePlaybooks(tmp_path / "not-held.json").load()
