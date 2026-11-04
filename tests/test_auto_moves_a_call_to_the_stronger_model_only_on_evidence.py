"""Auto (plan AN.38, D47-D49): every step runs on 6 Luna, and a call moves to 6.1 Terra only on evidence code sees in the turn -
a piece whose statements were found wrong twice (D51), an understanding still faulted after its revision, papers that differ before the time limits are worked
out. Offline; scripted ports stand for the two models."""
from __future__ import annotations

import pytest

from nm.core_engine import routing
from nm.core_engine.calls import TurnCalls
from nm.shared.budget_contracts import Completion
from nm.shared.model_config import AUTO_TURN, DEFAULT_TURN_MODEL, TURN_CHOICES, TURN_MODELS
from nm.shared.model_port import ModelResult, Prompt, Tier, Usage
from tests.test_core_served import served  # noqa: F401 -- the fixture

pytestmark = pytest.mark.class_a
SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}


class Port:
    #: It answers a second look itself (the suite's stand-in rewrites one otherwise).
    knows_second_look = True

    def __init__(self, model):
        self.model, self.sent = model, []

    def context_budget(self, tier):
        return 1_000_000

    def resolved_model(self, tier):
        return self.model

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.sent.append(prompt.operation)
        return ModelResult(None, {"a": "b"}, tier, "openai", self.model, Usage(10, 10, 0.0), 1,
                           completion=Completion.COMPLETE)


def call(calls, operation):
    return calls.structured(Prompt(system="", user="u", operation=operation, effort="medium"), SCHEMA, Tier.HARD,
                            max_tokens=100)


def test_the_rules_move_a_call_only_on_evidence():
    assert not routing.escalated("core_response_writer", corrections=1, earlier=5)
    assert routing.escalated("core_response_writer", corrections=2, earlier=0)
    assert not routing.escalated("core_research_revise", corrections=0, earlier=0)
    assert routing.escalated("core_research_revise", corrections=0, earlier=1)
    assert not routing.escalated("core_calculation", corrections=0, earlier=0)
    assert routing.escalated("core_calculation", corrections=0, earlier=0, evidence={"papers_differ"})
    assert not routing.escalated("core_response_writer", corrections=0, earlier=0, evidence={"papers_differ"})
    # Sol is never Auto's stronger model (D49).
    assert routing.STRONGER == "gpt-6.1-terra"


def test_under_auto_a_piece_faulted_twice_has_its_later_tries_and_their_reviews_on_the_stronger_model():
    base, stronger = Port("gpt-6-luna"), Port("gpt-6.1-terra")
    calls = TurnCalls(base, stronger=stronger)
    with calls.scope("s1", 5):
        call(calls, "core_response_writer")
        calls.spend("core_response_repair")
        call(calls, "core_response_repair")
        calls.spend("core_response_repair")
        call(calls, "core_response_repair")  # the second look after the second fault
        with calls.scope("s1.review3", 1):
            call(calls, "core_response_review")  # the review of it
    assert base.sent == ["core_response_writer", "core_response_repair"]
    assert stronger.sent == ["core_response_repair", "core_response_review"]
    assert [c.get("routed", False) for c in calls.calls] == [False, False, True, True]
    assert calls.calls[2]["model"] == "gpt-6.1-terra"
    # The estimate is made on the model the call is sent to.
    assert calls.calls[2]["estimated_usd"] > calls.calls[1]["estimated_usd"]


def test_under_auto_a_take_up_of_what_was_missing_and_a_rewrite_for_form_do_not_count_as_faults():
    # D51 (owner, 4 Nov 2026): only the rounds that found the piece's statements wrong or misleading count.
    base, stronger = Port("gpt-6-luna"), Port("gpt-6.1-terra")
    calls = TurnCalls(base, stronger=stronger)
    with calls.scope("s1", 6):
        call(calls, "core_response_writer")
        calls.spend("core_response_writer")  # a rewrite for form
        call(calls, "core_response_writer")
        calls.spend("core_response_take_up")
        call(calls, "core_response_take_up")
        calls.spend("core_response_repair")
        call(calls, "core_response_repair")  # one fault so far: still Luna
        with calls.scope("s1.review2", 2):
            calls.spend("core_response_review")  # the review's own form
            call(calls, "core_response_review")
        calls.spend("core_response_repair")
        call(calls, "core_response_repair")  # the second: Terra
    assert base.sent == ["core_response_writer", "core_response_writer", "core_response_take_up", "core_response_repair",
                         "core_response_review"]
    assert stronger.sent == ["core_response_repair"]
    # Every correction still counts against the piece's own allowance.
    assert calls.used("s1") == 4


def test_under_auto_the_second_revision_of_the_understanding_and_the_time_limits_after_differing_papers_move():
    base, stronger = Port("gpt-6-luna"), Port("gpt-6.1-terra")
    calls = TurnCalls(base, stronger=stronger)
    call(calls, "core_research_revise")
    call(calls, "core_research_revise")
    call(calls, "core_calculation")
    calls.found("papers_differ")
    call(calls, "core_calculation")
    assert base.sent == ["core_research_revise", "core_calculation"]
    assert stronger.sent == ["core_research_revise", "core_calculation"]


def test_without_auto_no_call_ever_moves():
    base = Port("gpt-6-luna")
    calls = TurnCalls(base)
    with calls.scope("s1", 5):
        for _ in range(3):
            call(calls, "core_response_writer")
            calls.spend("core_response_writer")
    calls.found("papers_differ")
    call(calls, "core_calculation")
    assert base.sent == ["core_response_writer"] * 3 + ["core_calculation"]
    assert not any(c.get("routed") for c in calls.calls)


def test_auto_is_offered_beside_the_models_with_luna_the_default(served):
    assert [model for model, _, _ in TURN_CHOICES] == ["gpt-6-luna", AUTO_TURN, "gpt-6.1-terra", "gpt-6.1-sol"]
    assert TURN_MODELS[0][0] == DEFAULT_TURN_MODEL and AUTO_TURN not in {model for model, _, _ in TURN_MODELS}
    offered = served.client.get("/api/turn-choices").json()
    assert [item["id"] for item in offered["models"]] == [model for model, _, _ in TURN_CHOICES]
    assert offered["default"]["model"] == DEFAULT_TURN_MODEL


def test_a_turn_sent_on_auto_is_answered_and_saved_with_its_choice(served):
    from nm.core_engine import turn
    from nm.core_engine.conversation import chat_matter_id
    reply = served.client.post("/api/turn", json={"message": "Inspect this reported account.", "turn_id": "turn-1",
                                                   "model": AUTO_TURN})
    assert reply.status_code == 200, reply.text
    row = turn.saved_rows(served.store.load(chat_matter_id("core-owner@example.test", reply.json()["chat_id"])),
                          "core-owner@example.test")[0]
    assert row["request"]["model"] == AUTO_TURN
    assert reply.json()["metrics"]["chosen"]["model"] == AUTO_TURN
    # Nothing in this plain turn moved a call.
    assert not any(call.get("routed") for call in reply.json()["metrics"]["calls"])
    refused = served.client.post("/api/turn", json={"message": "Inspect.", "turn_id": "turn-2", "model": "gpt-6.1-best"})
    assert refused.status_code == 422
