"""Every call of a turn is estimated before it is sent and kept beside what it cost, and the turn keeps its estimates beside what it
spent (plan AN.37, D41 and D45). Diagnostics only: nothing is held back or cut short. Offline; no provider."""
from __future__ import annotations

import logging
from decimal import Decimal

import pytest

from nm.core_engine import estimates
from nm.core_engine.calls import TurnCalls
from nm.shared.budget_contracts import Completion
from nm.shared.model_config import token_pricing
from nm.shared.model_port import ModelResult, Prompt, Tier, TierUnavailable, Usage

pytestmark = pytest.mark.class_a

SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}


class Provider:
    """Answers each call at the cost the test gives, on the model it names."""

    def __init__(self, cost=0.001, model="gpt-6-luna", names=True):
        self.cost, self.model, self.sent = cost, model, []
        if not names:
            self.resolved_model = None

    def context_budget(self, tier):
        return 1_000_000

    def resolved_model(self, tier):
        if self.model is None:
            raise TierUnavailable("not configured")
        return self.model

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.sent.append(prompt)
        return ModelResult(None, {"a": "b"}, tier, "openai", self.model or "unknown", Usage(10, 10, self.cost), 1,
                           completion=Completion.COMPLETE)


def call(calls, operation="core_response_writer", effort="medium", user="x" * 40_000):
    return calls.structured(Prompt(system="", user=user, operation=operation, effort=effort), SCHEMA, Tier.HARD,
                            max_tokens=1000)


def test_a_call_is_priced_at_fresh_input_and_its_steps_usual_output_moved_by_its_level():
    luna = token_pricing("gpt-6-luna")
    expected = luna.cost_usd(100_000, estimates.USUAL_OUTPUT["core_response_writer"])
    assert estimates.call_usd("gpt-6-luna", 100_000, "core_response_writer", own="medium", sent="medium") == expected
    higher = estimates.call_usd("gpt-6-luna", 100_000, "core_response_writer", own="medium", sent="high")
    assert higher == luna.cost_usd(100_000, round(estimates.USUAL_OUTPUT["core_response_writer"] * 2.5))
    # A step never measured takes the default; a model without an established price, no estimate at all.
    assert estimates.call_usd("gpt-6-luna", 0, "core_not_measured") == luna.cost_usd(0, round(estimates.USUAL_DEFAULT))
    assert estimates.call_usd("no-such-model", 100_000, "core_response_writer") is None


def test_a_turn_on_a_dearer_model_or_a_higher_level_is_expected_to_cost_more():
    luna = estimates.turn_start_usd("gpt-6-luna", 2, "medium")
    assert luna == pytest.approx(0.20)
    ratio = token_pricing("gpt-6.1-terra").output_rate / token_pricing("gpt-6-luna").output_rate
    assert estimates.turn_start_usd("gpt-6.1-terra", 2, "medium") == pytest.approx(0.20 * float(ratio))
    assert estimates.turn_start_usd("gpt-6-luna", 2, "high") > luna > estimates.turn_start_usd("gpt-6-luna", 2, "low")
    # Once planned: what is spent, and the usual for each dispute, with the overview where there are two or more.
    assert estimates.turn_planned_usd("gpt-6-luna", 0.05, 1, "medium") == pytest.approx(0.05 + 0.08)
    assert estimates.turn_planned_usd("gpt-6-luna", 0.05, 3, "medium") == pytest.approx(0.05 + 0.24 + 0.02)
    assert estimates.turn_start_usd("no-such-model", 1, "medium") is None


def test_each_call_keeps_its_level_and_estimate_beside_what_it_cost():
    provider = Provider(cost=0.001)
    calls = TurnCalls(provider)
    call(calls)
    record = calls.calls[0]
    assert record["effort"] == "medium" and record["cost_usd"] == 0.001
    # Its input as counted when it was sent, its step's usual output at its level, at the price of the model it names.
    assert record["estimated_usd"] == pytest.approx(estimates.call_usd(
        "gpt-6-luna", record_tokens(provider.sent[0]), "core_response_writer", own="medium", sent="medium"))
    # The advocate's choice of effort moves the level sent, and the estimate with it.
    high = TurnCalls(Provider(), effort="high")
    call(high)
    assert high.calls[0]["effort"] == "high" and high.calls[0]["estimated_usd"] > record["estimated_usd"]


def record_tokens(prompt):
    import json

    from nm.shared.model_port import estimate_tokens
    return estimate_tokens((prompt.system or "") + prompt.user + json.dumps(SCHEMA))


def test_a_model_that_names_none_leaves_the_call_unestimated_and_the_call_goes_as_before():
    for provider in (Provider(names=False), Provider(model=None)):
        calls = TurnCalls(provider)
        assert call(calls).data == {"a": "b"}
        assert calls.calls[0]["estimated_usd"] is None
        assert calls.metrics()["estimate"]["calls_usd"] is None


def test_the_turn_keeps_its_estimates_beside_what_it_spent_and_says_where_spending_passed_them(caplog):
    cheap = TurnCalls(Provider(cost=0.0001))
    call(cheap)
    cheap.expect("start", 0.05)
    kept = cheap.metrics()["estimate"]
    assert kept["calls_estimated"] == 1 and kept["start_usd"] == 0.05 and kept["spent_usd"] == 0.0001
    assert kept["passed"] == []
    # A call that costs far more than its estimate is said in the log, and the turn's estimates it passed are listed;
    # the call's answer is returned as it would be (D45).
    dear = TurnCalls(Provider(cost=5.0))
    with caplog.at_level(logging.WARNING, logger="nm.core_engine.calls"):
        assert call(dear).data == {"a": "b"}
    assert any("more than 3.0 times its estimate" in message for message in caplog.messages)
    dear.expect("start", 0.10)
    dear.expect("planned", 0.20)
    dear.expect("unknown stage", 1.0)  # only the turn's own two stages are kept
    assert dear.metrics()["estimate"]["passed"] == ["calls", "start", "planned"]
    assert "unknown stage_usd" not in dear.metrics()["estimate"]


def test_estimates_hold_nothing_back():
    """D45: the estimate never limits what a call may write or whether it is sent."""
    provider = Provider(cost=100.0)
    calls = TurnCalls(provider)
    for _ in range(3):
        call(calls)
    assert len(provider.sent) == 3 and Decimal(str(calls.metrics()["estimate"]["spent_usd"])) == Decimal("300.0")


def test_a_turn_keeps_its_rough_estimate_and_the_one_made_once_its_plan_is_known(store):
    """Through the real turn: before the plan, from the papers sent (none here: one turn's worth); once planned, what was
    spent and the usual for each dispute (one here). The scripted calls cost nothing, so no estimate is passed."""
    from tests.test_core_turn import ScriptedModel, run
    model = ScriptedModel(legal=True)
    model.resolved_model = lambda tier: "gpt-6-luna"
    response = run(store, model)
    kept = response["metrics"]["estimate"]
    assert kept["start_usd"] == pytest.approx(estimates.turn_start_usd("gpt-6-luna", 0, "medium"))
    assert kept["planned_usd"] == pytest.approx(estimates.turn_planned_usd("gpt-6-luna", 0.0, 1, "medium"))
    assert kept["calls_estimated"] == response["metrics"]["llm_calls"] and kept["passed"] == []
    assert all(call["effort"] is not None or call["operation"].endswith(("phrases", "pick")) for call in
               response["metrics"]["calls"])


def test_a_turn_whose_model_names_none_keeps_no_estimate_of_its_own(store):
    from tests.test_core_turn import ScriptedModel, run
    kept = run(store, ScriptedModel(legal=True))["metrics"]["estimate"]
    assert "start_usd" not in kept and "planned_usd" not in kept and kept["calls_usd"] is None


@pytest.fixture
def store(tmp_path):
    from nm.shared.store_file_store import FileMatterStore
    return FileMatterStore(tmp_path, key="synthetic-estimate-fixture")
