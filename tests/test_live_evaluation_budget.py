"""Paid evaluation cannot reset cost on a retry, failure or process restart."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS  # noqa: N814 -- compact SDK-shaped fixture

import pytest
from nm.adapters.model.call_budget import MODEL, CallBudget
from nm.adapters.model.config import ModelConfig, TierConfig
from nm.adapters.model.openai_adapter import OpenAIModelAdapter
from nm.domain.external_ai import ModelPermissionRefused
from nm.ports.model import ConfigurationError, Prompt, ProviderUnavailable, Tier

pytestmark = pytest.mark.class_a


def rows(path):
    with sqlite3.connect(path) as db:
        return db.execute("SELECT charge,state,response_id FROM attempts").fetchall()


def test_reservation_survives_restart_and_precedes_dispatch(tmp_path):
    path = tmp_path / "budget.db"
    first = CallBudget(path, "0.03")
    first.reserve(MODEL)
    second = CallBudget(path, "0.03")
    with pytest.raises(ProviderUnavailable):
        second.reserve(MODEL)
    assert rows(path) == [(30000, "reserved_or_unknown", None)]
    with pytest.raises(ConfigurationError):
        CallBudget(path, "25")


def test_concurrent_requests_share_one_budget(tmp_path):
    path = tmp_path / "budget.db"
    budget = CallBudget(path, "0.03")

    def attempt(_):
        try:
            budget.reserve(MODEL)
            return True
        except ProviderUnavailable:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(attempt, range(8))) == 1
    assert len(rows(path)) == 1


@pytest.mark.parametrize("bad", ["gpt-5.1", "gpt-4o-mini", "scripted-1", ""])
def test_other_models_cannot_spend_the_approved_budget(tmp_path, bad):
    with pytest.raises(ConfigurationError):
        CallBudget(tmp_path / "budget.db", "25").reserve(bad)


def test_missing_usage_is_not_a_free_call(tmp_path):
    path = tmp_path / "budget.db"
    budget = CallBudget(path, "25")
    token = budget.reserve(MODEL)
    budget.settle(token, NS(usage=None))
    assert rows(path)[0][:2] == (30000, "reserved_or_unknown")


def test_accounting_happens_before_truncated_response_is_rejected(tmp_path):
    from nm.ports.model import OutputTruncated

    path = tmp_path / "budget.db"
    budget = CallBudget(path, "25")

    def create(**_):
        assert rows(path)[0][1] == "reserved_or_unknown"
        return NS(
            id="synthetic-response-id",
            usage=NS(prompt_tokens=100, completion_tokens=20),
            choices=[NS(finish_reason="length")],
        )

    cfg = ModelConfig(tiers={Tier.ROUTINE: TierConfig(Tier.ROUTINE, "openai", MODEL, "fake", None)})
    client = NS(chat=NS(completions=NS(create=create)))
    model = OpenAIModelAdapter(cfg, client=client, call_budget=budget).for_matter_text(lambda: None)
    with pytest.raises(OutputTruncated):
        model.complete(Prompt(system="", user="synthetic"), Tier.ROUTINE)
    assert rows(path) == [(27, "measured", "synthetic-response-id")]


def test_permission_refusal_precedes_reservation_and_wire(tmp_path):
    path = tmp_path / "budget.db"
    budget = CallBudget(path, "25")
    cfg = ModelConfig(tiers={Tier.ROUTINE: TierConfig(Tier.ROUTINE, "openai", MODEL, "fake", None)})

    def refuse():
        raise ModelPermissionRefused("withdrawn")

    def never(**_):
        pytest.fail("not permitted")

    model = OpenAIModelAdapter(
        cfg, client=NS(chat=NS(completions=NS(create=never))), call_budget=budget
    ).for_matter_text(refuse)
    with pytest.raises(ModelPermissionRefused):
        model.complete(Prompt(system="", user="synthetic"), Tier.ROUTINE)
    assert rows(path) == []


def test_retry_must_fund_a_new_attempt_without_releasing_the_unknown_one(tmp_path, monkeypatch):
    from nm.adapters.model import openai_adapter

    path = tmp_path / "budget.db"
    budget = CallBudget(path, "0.03")
    cfg = ModelConfig(tiers={Tier.ROUTINE: TierConfig(Tier.ROUTINE, "openai", MODEL, "fake", None)})
    attempts = []

    def limited(**_):
        attempts.append("wire")
        raise RuntimeError("429 rate limit")

    monkeypatch.setattr(openai_adapter.time, "sleep", lambda _: None)
    model = OpenAIModelAdapter(
        cfg, client=NS(chat=NS(completions=NS(create=limited))), call_budget=budget
    ).for_matter_text(lambda: None)
    with pytest.raises(ProviderUnavailable, match="budget"):
        model.complete(Prompt(system="", user="synthetic"), Tier.ROUTINE)
    assert attempts == ["wire"]
    assert rows(path) == [(30000, "reserved_or_unknown", None)]
