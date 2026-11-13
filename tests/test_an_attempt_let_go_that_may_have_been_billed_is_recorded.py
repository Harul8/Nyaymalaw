"""An attempt let go after the provider may have done the work is recorded, its cost not established (plan AN.52, 52i4; D215).

The transport sends a request again when the one before it failed in a way that may pass. Two of those ways - the client stopped
waiting (a timeout) and the connection was lost - leave the provider free to have done the work and billed it all the same. The
meter recorded the call once: answered, at the cost of the answering attempt, 'attempts: 2' - so the operator's totals, which
count calls and cost, showed a cost that looked whole. Each attempt let go that way is now a record of its own: outcome
'abandoned', cost not established and so charged to no allowance, counted among the calls whose cost is not established. A rate
limit and the provider's own server error are not such attempts: the provider says it did not do the work.

Two files, said so: nm/shared/model_transport.py notes the attempts let go, and nm/shared/model_metered.py, which alone knows
the account, keeps them. The usage store and its fixed fields are unchanged.

Offline: a stand-in adapter that sends through the real transport; no provider; no model call.
"""
from __future__ import annotations

import pytest

from nm.arrive.store_usage import FileUsage
from nm.shared import model_transport
from nm.shared.model_metered import MeteredModel
from nm.shared.model_port import ModelError, ModelResult, Prompt, ProviderUnavailable, Tier, Usage

pytestmark = pytest.mark.class_a
WHO = "metered@example.test"


def _sdk(name):
    return type(name, (Exception,), {})(f"the provider's {name}")


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(model_transport.time, "sleep", lambda seconds: None)


class _Adapter:
    """Sends each request through the real transport; each attempt fails as `failures` says, in turn, then answers."""

    provider = "stand-in"

    def __init__(self, *failures):
        self.failures = list(failures)

    def resolved_model(self, tier):
        return "stand-in-model-1"

    def context_budget(self, tier):
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        def attempt():
            if self.failures:
                raise _sdk(self.failures.pop(0))
            return "answered"
        _response, retries = model_transport.request_with_retries(attempt, model="stand-in-model-1")
        return ModelResult(text=None, data={"ok": True}, tier=tier, provider="stand-in", model="stand-in-model-1",
                           usage=Usage(1000, 200, 0.0042), latency_ms=5, retries=retries)


def _metered(*failures):
    records = []
    return MeteredModel(inner=_Adapter(*failures), record=records.append), records


def _ask(model):
    return model.structured(Prompt(system="s", user="u", operation="core_research_pick"), {"type": "object"}, Tier.ROUTINE)


@pytest.mark.parametrize("let_go", ["APITimeoutError", "APIConnectionError"])
def test_an_answered_call_after_an_attempt_let_go_keeps_that_attempt_as_its_own_record(let_go):
    model, records = _metered(let_go)
    assert _ask(model).data == {"ok": True}
    abandoned, answered = records
    assert (abandoned["outcome"], abandoned["attempts"], abandoned["micro_usd"]) == ("abandoned", 1, None)
    assert (abandoned["kind"], abandoned["operation"], abandoned["tier"], abandoned["model"]) == (
        "structured", "core_research_pick", "routine", "stand-in-model-1")
    assert all(abandoned[name] is None for name in ("tokens_in", "tokens_out", "cached_tokens", "cache_write_tokens"))
    assert (answered["outcome"], answered["attempts"], answered["micro_usd"]) == ("ok", 2, 4200), "the answer as before"


@pytest.mark.parametrize("not_let_go", ["RateLimitError", "InternalServerError", "OverloadedError"])
def test_an_attempt_the_provider_says_it_did_not_do_is_not_recorded_as_one_that_may_have_been_billed(not_let_go):
    model, records = _metered(not_let_go)
    _ask(model)
    assert [record["outcome"] for record in records] == ["ok"] and records[0]["attempts"] == 2


def test_a_call_answered_at_once_is_one_record_as_before():
    model, records = _metered()
    _ask(model)
    assert [(record["outcome"], record["attempts"]) for record in records] == [("ok", 1)]


def test_a_call_that_fails_after_attempts_let_go_keeps_each_and_its_failure():
    model, records = _metered("APITimeoutError", "APITimeoutError", "APITimeoutError")
    with pytest.raises(ModelError) as failed:
        _ask(model)
    assert isinstance(failed.value, ProviderUnavailable)
    assert [record["outcome"] for record in records] == ["abandoned", "abandoned", "ProviderUnavailable"], (
        "the two let go and sent again are records of their own; the last is the call's failure, as before")
    assert all(record["micro_usd"] is None for record in records)
    assert records[-1]["attempts"] == 3, "the failure still counts every attempt of the call"


def test_outside_a_meter_the_transport_notes_nothing_and_sends_as_before():
    attempts = iter([_sdk("APITimeoutError")])

    def attempt():
        failure = next(attempts, None)
        if failure is not None:
            raise failure
        return "answered"
    assert model_transport.request_with_retries(attempt) == ("answered", 1)


def test_the_usage_store_keeps_it_and_the_totals_count_it_among_the_costs_not_established(tmp_path):
    usage = FileUsage(tmp_path / "usage.sqlite")
    model = MeteredModel(inner=_Adapter("APITimeoutError"), record=lambda call: usage.record(WHO, call))
    _ask(model)
    totals = usage.totals()
    assert totals["calls"] == 2 and totals["not_established"] == 1 and totals["micro_usd"] == 4200
    by_outcome = {row["outcome"]: row for row in totals["by_outcome"]}
    assert by_outcome["abandoned"]["calls"] == 1 and by_outcome["abandoned"]["not_established"] == 1
    assert usage.standing(WHO)["spent"] == 4200, "a cost not established is charged to no allowance"
