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
        # Plan AN.58 (D288): two models, each with what it is for; Auto and 6.1 Sol no longer offered.
        "models": [{"id": "gpt-6-luna", "label": "6 Luna (routine work)", "cost": ""},
                   {"id": "gpt-6.1-terra", "label": "6.1 Terra (complex matters)", "cost": "about 8-10x Luna's cost"}],
        # How thorough NM is, in plain words, each the effort it was before.
        "efforts": [{"id": "low", "label": "Quick"}, {"id": "medium", "label": "Standard"}, {"id": "high", "label": "Thorough"},
                    {"id": "max", "label": "Most thorough"}],
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


@pytest.mark.parametrize("change", [{"model": "gpt-5.1"}, {"effort": "extreme"}, {"model": ""},
                                    # D288: offered before, offered no longer - a new message may not name them.
                                    {"model": "gpt-6.1-sol"}, {"model": "auto"}])
def test_a_model_or_an_effort_the_server_does_not_offer_is_refused_before_any_work(served, change):
    calls = len(served.model.calls)
    refused = send(served, **change)
    assert refused.status_code == 422 and len(served.model.calls) == calls


def test_a_turn_with_no_choice_saved_is_bound_as_written_on_luna_and_reviewed_on_it(served, monkeypatch):
    """Plan AN.51 (D289, kept by D294): a go-ahead takes the model from the saved request, which names no default; the turn is still
    bound as written on 6 Luna, so that every call of it, the review among them, runs on Luna and never on the installation's own
    tiers."""
    seen, binding = [], served.app._model_for

    def bound(advocate_id, **asked):
        seen.append(asked.get("text_model"))
        return binding(advocate_id, **asked)
    monkeypatch.setattr(served.app, "_model_for", bound)
    served.app.run_turn(advocate_id="core-owner@example.test", session_current=lambda: True,
                        message="Inspect this reported account.", turn_id="turn-1")
    assert seen and set(seen) == {"gpt-6-luna"}
