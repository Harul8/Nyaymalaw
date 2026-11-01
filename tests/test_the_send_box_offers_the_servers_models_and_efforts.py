"""The send box offers the server's own lists of models and efforts, and a message carries the advocate's choice to the turn
(plan AN.33, D23; piece 33n).

The owner, 1 Nov 2026: "given option in the UI to the users to select the model and also the reasoning level", "6 Luna being the
default model", "Just say terra costs 8-10x more and similarly for sol" and "Reset for new conversations". The server says what may
be chosen; a message that names anything else is refused before any work; the turn records what it ran with. The page's half - the
lists filled from the server, the defaults each time a conversation opens, the choice in the message only where it is not the
default, and the line under a reply - is checked by tests/js/turn_choice.mjs.
"""
import pytest

from nm.core_engine.conversation import chat_matter_id
from nm.core_engine.turn import saved_rows
from tests.test_core_served import send, served, successful  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a


def test_the_server_says_which_models_and_efforts_may_be_chosen_and_the_defaults(served):
    offered = served.client.get("/api/turn-choices")
    assert offered.status_code == 200
    assert offered.json() == {
        "models": [{"id": "gpt-6-luna", "label": "6 Luna", "cost": ""},
                   {"id": "gpt-6.1-terra", "label": "6.1 Terra", "cost": "about 8-10x Luna's cost"},
                   {"id": "gpt-6.1-sol", "label": "6.1 Sol", "cost": "about 16-20x Luna's cost"}],
        "efforts": [{"id": "low", "label": "Low"}, {"id": "medium", "label": "Medium"}, {"id": "high", "label": "High"},
                    {"id": "max", "label": "Max"}],
        "default": {"model": "gpt-6-luna", "effort": "medium"}}


def test_a_message_carries_the_choice_to_the_turn_which_records_what_it_ran_with(served):
    plain = successful(served)
    assert plain["metrics"]["chosen"] == {"model": "gpt-6-luna", "effort": "medium"}, "the defaults, recorded"
    chosen = successful(served, turn_id="turn-2", chat_id=plain["chat_id"], model="gpt-6.1-terra", effort="high")
    assert chosen["metrics"]["chosen"] == {"model": "gpt-6.1-terra", "effort": "high"}
    rows = saved_rows(served.store.load(chat_matter_id("core-owner@example.test", plain["chat_id"])), "core-owner@example.test")
    assert "model" not in rows[0]["request"] and "effort" not in rows[0]["request"]
    assert (rows[1]["request"]["model"], rows[1]["request"]["effort"]) == ("gpt-6.1-terra", "high")
    assert rows[1]["response"]["metrics"]["chosen"] == {"model": "gpt-6.1-terra", "effort": "high"}, "saved as it was sent"


@pytest.mark.parametrize("change", [{"model": "gpt-5.1"}, {"effort": "extreme"}, {"model": ""}])
def test_a_model_or_an_effort_the_server_does_not_offer_is_refused_before_any_work(served, change):
    calls = len(served.model.calls)
    refused = send(served, **change)
    assert refused.status_code == 422 and len(served.model.calls) == calls
