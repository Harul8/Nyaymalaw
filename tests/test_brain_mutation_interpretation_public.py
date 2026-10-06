"""Scope transport reaches authenticated service admission and atomic storage."""
from copy import deepcopy

import pytest

from nm.brain import conversation as brain
from nm.brain import turn as brain_turn
from tests.test_brain_mutation_interpretation import Model, item, response, scope
from tests.test_brain_turn import Model as PublicModel


@pytest.mark.parametrize("fault", ("missing-scopes", "foreign-target", "purpose-mismatch"))
def test_public_invalid_scope_contract_never_saves_or_releases_work(
        client, wired, monkeypatch, fault):
    words = "The recipient retained the original record."
    grant = scope(targets=(), relations=("new",))
    proposed = response(item(words, scopes=(grant,), purposes=("account_contribution",),
                             matter_scope="proposed", relation="new"))
    if fault == "missing-scopes":
        proposed["items"][0].pop("mutation_scopes")
    elif fault == "foreign-target":
        grant["target_ids"] = ["unowned-record"]
    else:
        proposed["items"][0]["material_purposes"] = []
    model = Model(deepcopy(proposed), deepcopy(proposed))
    monkeypatch.setattr(brain_turn, "interpret", brain.interpret)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    turn_id = "invalid-scope-" + fault

    served = client.post("/api/turn", json={"message": words, "turn_id": turn_id})

    assert served.status_code == 503, served.text
    assert served.json()["detail"]["committed"] == "not_committed"
    assert wired.store.load(brain_turn.chat_matter_id("adv_demo", turn_id)) is None
    assert len(model.calls) == 2
    assert {prompt.operation for prompt, _ in model.calls} == {"interpret_conversation"}


def test_public_valid_empty_scope_delivers_and_reopens_a_supported_ordinary_reply(
        client, wired, monkeypatch):
    words = "Hello."
    proposed = response(item(words, matter_scope="none", relation="new", intent="request"))
    proposed["items"][0]["reply"] = "Hello. What would you like help with?"
    model = PublicModel([proposed])
    monkeypatch.setattr(brain_turn, "interpret", brain.interpret)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    served = client.post("/api/turn", json={"message": words, "turn_id": "ordinary-empty-scope"})

    assert served.status_code == 200, served.text
    data = served.json()
    saved = wired.store.load(brain_turn.chat_matter_id("adv_demo", data["chat_id"]))
    assert saved.brain_chat[-1]["response"]["elements"] == data["elements"]
    assert data["material"] == []
    assert data["blocked"] is False
    assert model.all_calls == [
        "interpret_conversation", "continue_conversation", "verify_continuation"]
