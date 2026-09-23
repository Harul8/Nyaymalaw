"""DG-02: refuse dependent/unknown steps without blocking useful gathering."""

import json
from datetime import date

import pytest
from nm.adapters.model.scripted import SCRIPTED_READS, ScriptedModelAdapter
from nm.adapters.store.file_store import FileMatterStore
from nm.core import limitation, step_dependency
from nm.core.turn import TurnEngine
from nm.domain.answer import ElementKind
from nm.domain.matter import Side
from nm.domain.metrics import TurnMetrics
from nm.ports.model import ModelError

from tests.test_turn_contract import KEY, _Evidence, _model_config

pytestmark = pytest.mark.class_a


def test_served_refusal_removes_old_recommendation_and_survives_reload(client, monkeypatch):
    first = client.post("/api/turn", json={
        "message": "We act for the plaintiff supplier at Hyderabad. Goods were never paid for.",
        "today": "2026-09-22"})
    assert first.status_code == 200, first.text
    matter_id = first.json()["matter_id"]
    assert matter_id and any(e["kind"] == "action" for e in first.json()["elements"])

    def dependent(user):
        return json.dumps({"step": json.loads(user)["step"], "dependence": "dependent",
                           "reason": "The proposed step depends on the unresolved window."})
    monkeypatch.setitem(SCRIPTED_READS, "step_dependency", dependent)
    second = client.post("/api/turn", json={
        "matter_id": matter_id, "message": "What next on these unpaid goods?",
        "today": "2026-09-22"})
    assert second.status_code == 200, second.text
    assert not any(e["kind"] == "action" for e in second.json()["elements"])
    assert any("not released a limitation-dependent" in e["text"]
               for e in second.json()["elements"])
    assert any(g["gate"] == "G-LIMITATION"
               for g in second.json()["metrics"]["gates_fired"])
    loaded = client.get(f"/api/matters/{matter_id}")
    assert loaded.status_code == 200, loaded.text
    assert "not released a limitation-dependent" in client.get(
        f"/api/matters/{matter_id}/transcript").text
    # Read the real saved aggregate too; a renderer-only refusal is insufficient.
    from nm.edge.api import application
    saved = application().store.load(matter_id)
    assert saved.threads
    assert all(not thread.recommendation for thread in saved.threads)


@pytest.mark.parametrize(
    "state", [None, limitation.LimitationState.NOT_COMPUTED, limitation.LimitationState.CONDITIONAL]
)
@pytest.mark.parametrize("dependence", list(step_dependency.Dependence))
def test_unsettled_position_gates_the_proposed_step_not_the_thread(
    tmp_path, monkeypatch, state, dependence
):
    def answer(user):
        return json.dumps(
            {
                "step": json.loads(user)["step"],
                "dependence": dependence.value,
                "reason": "The supplied step's dependence was assessed.",
            }
        )

    monkeypatch.setitem(SCRIPTED_READS, "step_dependency", answer)
    engine = TurnEngine(
        model=ScriptedModelAdapter(_model_config()),
        store=FileMatterStore(tmp_path, key=KEY),
        evidence=_Evidence(),
    )
    position = (
        None
        if state is None
        else limitation.Limitation(
            for_side=Side.MOVING, state=state, not_computed_because="Accrual is unresolved"
        )
    )
    metrics = TurnMetrics(turn_id="test-turn")
    result = engine._limitation_step("A proposed next step.", position, metrics, "thread-1", "file")
    if dependence is step_dependency.Dependence.INDEPENDENT:
        assert result is None
    else:
        assert result.kind is ElementKind.QUESTION
        assert result.gate == "G-LIMITATION"
        assert "gathering evidence" in result.text
    assert any(g.gate_id == "G-LIMITATION" for g in metrics.gates_fired)


@pytest.mark.parametrize(
    "state", [limitation.LimitationState.COMPUTED, limitation.LimitationState.NOT_APPLICABLE]
)
def test_established_position_does_not_spend_a_dependency_call(tmp_path, monkeypatch, state):
    def never(_):
        pytest.fail("established positions do not need a dependency classification")

    monkeypatch.setitem(SCRIPTED_READS, "step_dependency", never)
    engine = TurnEngine(
        model=ScriptedModelAdapter(_model_config()),
        store=FileMatterStore(tmp_path, key=KEY),
        evidence=_Evidence(),
    )
    position = limitation.Limitation(for_side=Side.MOVING, state=state, expires_on=date(2027, 1, 1))
    assert (
        engine._limitation_step("Next step", position, TurnMetrics(turn_id="test-turn"), "t", "")
        is None
    )


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"dependence": "independent", "step": "different", "reason": "assessed"},
        {"dependence": "independent", "step": "target", "reason": " "},
        {"dependence": "invented", "step": "target", "reason": "assessed"},
    ],
)
def test_missing_or_unbound_assessment_is_unknown(data):
    assert step_dependency.interpret(data, "target") is step_dependency.Dependence.UNKNOWN


def test_dependency_schema_binds_the_whole_candidate_without_mutating_the_base():
    from jsonschema import ValidationError, validate
    step = "Provisional view\nThe record does not establish the missing date."
    schema = step_dependency.schema_for(step)
    # A WELL-FORMED ANSWER UNDER THE CURRENT CONTRACT, which since 23 September
    # 2026 carries the two halves the verdict is derived from.
    data = {"dependence": "independent", "step": step, "reason": "No legal outcome asserted.",
            "right_if_in_time": "yes", "right_if_out_of_time": "yes"}
    validate(data, schema)
    with pytest.raises(ValidationError):
        validate({**data, "step": "Provisional view"}, schema)
    assert "enum" not in step_dependency.SCHEMA["properties"]["step"]
    assert step_dependency.assess({**data, "step": "Provisional view"}, step, "file").dependence \
        is step_dependency.Dependence.UNKNOWN


def test_explanation_is_not_a_blanket_exemption_from_the_limitation_boundary():
    prompt = step_dependency.build_prompt("Explain the missing date", "file")
    assert "not automatically independent" in prompt.system
    assert "maintainability, entitlement to relief" in prompt.system
    assert "any dependent action" in prompt.system


def test_unavailable_classifier_does_not_release_a_directive(tmp_path, monkeypatch):
    def unavailable(_):
        raise ModelError("unavailable")

    monkeypatch.setitem(SCRIPTED_READS, "step_dependency", unavailable)
    engine = TurnEngine(
        model=ScriptedModelAdapter(_model_config()),
        store=FileMatterStore(tmp_path, key=KEY),
        evidence=_Evidence(),
    )
    assert (
        engine._limitation_step("Proceed", None, TurnMetrics(turn_id="test-turn"), "t", "").gate
        == "G-LIMITATION"
    )
