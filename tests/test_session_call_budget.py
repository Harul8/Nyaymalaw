"""One conservative cap owns every configured tier, request and physical retry."""
from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS  # noqa: N814 -- SDK-shaped fixture

import pytest

from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.model_call_budget import CallBudget, SessionCallBudget
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import (
    ConfigurationError,
    OutputTruncated,
    Prompt,
    ProviderUnavailable,
    Tier,
)

ROUTINE = "gpt-4.1-mini-2025-04-14"
JUDGE = "gpt-5.1"
SNAPSHOT = "gpt-5.1-2025-11-13"
pytestmark = pytest.mark.class_a


def _rows(path):
    with sqlite3.connect(path) as db:
        return db.execute(
            "SELECT model,charge,state,reservation FROM attempts ORDER BY at").fetchall()


def _response(model, *, stop="stop", incoming=1000, outgoing=20):
    return NS(model=model, id="synthetic-receipt",
              usage=NS(prompt_tokens=incoming, completion_tokens=outgoing),
              choices=[NS(finish_reason=stop, message=NS(content="Checked response."))])


def _model(session, create):
    config = ModelConfig(tiers={
        tier: TierConfig(tier, "openai", name, "fake", None)
        for tier, name in ((Tier.ROUTINE, ROUTINE), (Tier.JUDGE, JUDGE))})
    return OpenAIModelAdapter(config, client=NS(chat=NS(completions=NS(create=create))),
                              call_budget=session).for_matter_text(lambda: None)


def test_current_output_allowance_uses_full_verified_context_and_checked_alias(tmp_path):
    session = SessionCallBudget(tmp_path / "cap.db", "3", models=(ROUTINE, JUDGE))
    routine, limit = session.for_request(ROUTINE, 512)
    judge, _ = session.for_request(JUDGE, 1024)
    assert limit == 512
    assert routine.reservation == 419_850
    assert judge.reservation == 510_240
    token = judge.reserve(JUDGE)
    judge.settle(token, _response(SNAPSHOT))
    assert _rows(session.path) == [(JUDGE, 1450, "measured", 510_240)]
    assert session.status()["maximum_usd"] == 3


def test_different_request_ceiling_or_alias_policy_cannot_settle_captured_terms(tmp_path):
    session = SessionCallBudget(tmp_path / "cap.db", "3", models=(JUDGE,))
    original, _ = session.for_request(JUDGE, 1024)
    token = original.reserve(JUDGE)
    changed, _ = session.for_request(JUDGE, 2048)
    with pytest.raises(ConfigurationError, match="captured"):
        changed.settle(token, _response(SNAPSHOT))
    changed_policy = CallBudget(session.path, "3", model=JUDGE,
                                price_per_million=("1.25", "10.0"),
                                reservation_micro_usd=original.reservation)
    with pytest.raises(ConfigurationError, match="captured"):
        changed_policy.settle(token, _response(JUDGE))
    original.settle(token, _response(SNAPSHOT))


def test_shared_cap_is_atomic_across_different_models_and_restart(tmp_path):
    path = tmp_path / "cap.db"
    session = SessionCallBudget(path, "1", models=(ROUTINE, JUDGE))

    def reserve(index):
        name = (ROUTINE, JUDGE)[index % 2]
        request, _ = session.for_request(name, 1024)
        try:
            request.reserve(name)
            return True
        except ProviderUnavailable:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        successes = sum(pool.map(reserve, range(8)))
    assert successes in (1, 2)
    assert 0 < session.status()["charged_usd"] <= 1
    restarted = SessionCallBudget(path, "1", models=(ROUTINE, JUDGE))
    assert restarted.status() == session.status()
    for name in (ROUTINE, JUDGE):
        request, _ = restarted.for_request(name, 1024)
        with pytest.raises(ProviderUnavailable, match="budget"):
            request.reserve(name)
    with pytest.raises(ConfigurationError, match="reset"):
        SessionCallBudget(path, "3", models=(ROUTINE, JUDGE))


@pytest.mark.parametrize("models", (("gpt-5.2",), ("text-embedding-3-large",), ("unknown",)))
def test_unverified_model_terms_fail_before_creating_a_ledger(tmp_path, models):
    path = tmp_path / "cap.db"
    with pytest.raises(ConfigurationError, match="verified"):
        SessionCallBudget(path, "3", models=models)
    assert not path.exists()


@pytest.mark.parametrize("limit", (True, 0, -1, 128001, "100"))
def test_invalid_or_excessive_output_ceiling_cannot_reserve(tmp_path, limit):
    session = SessionCallBudget(tmp_path / "cap.db", "3", models=(JUDGE,))
    with pytest.raises(ConfigurationError, match="output ceiling"):
        session.for_request(JUDGE, limit)
    assert session.status()["attempts"] == 0


def test_alias_does_not_authorise_foreign_snapshot_and_missing_identity_stays_charged(tmp_path):
    session = SessionCallBudget(tmp_path / "cap.db", "3", models=(JUDGE,))
    request, _ = session.for_request(JUDGE, 1024)
    token = request.reserve(JUDGE)
    with pytest.raises(ConfigurationError, match="model identity"):
        request.settle(token, _response("gpt-5.1-2099-01-01"))
    request.settle(token, _response(None))
    assert _rows(session.path) == [(JUDGE, 510240, "reserved_or_unknown", 510240)]


def test_adapter_preserves_current_output_allowance_and_reserves_both_tiers(tmp_path):
    session = SessionCallBudget(tmp_path / "cap.db", "3", models=(ROUTINE, JUDGE))
    wires = []

    def create(**kwargs):
        assert _rows(session.path)[-1][2] == "reserved_or_unknown"
        wires.append(kwargs)
        return _response(SNAPSHOT if kwargs["model"] == JUDGE else ROUTINE)

    model = _model(session, create)
    model.complete(Prompt(user="Whole unchanged context."), Tier.ROUTINE, max_tokens=777)
    model.complete(Prompt(user="Independent whole-context check."), Tier.JUDGE, max_tokens=1234)
    assert [(wire["model"], wire["max_completion_tokens"]) for wire in wires] == [
        (ROUTINE, 777), (JUDGE, 1234)]
    assert all(row[2] == "measured" for row in _rows(session.path))


def test_absent_output_allowance_is_explicit_full_verified_ceiling(tmp_path):
    session = SessionCallBudget(tmp_path / "cap.db", "3", models=(JUDGE,))
    wires = []

    def create(**kwargs):
        wires.append(kwargs)
        return _response(SNAPSHOT)

    _model(session, create).complete(Prompt(user="Unchanged request."), Tier.JUDGE)
    assert wires[0]["max_completion_tokens"] == 128000
    assert _rows(session.path)[0][3] == 1_780_000


def test_every_physical_retry_reserves_and_unknown_attempt_is_not_refunded(tmp_path, monkeypatch):
    from nm.shared import model_transport

    session = SessionCallBudget(tmp_path / "cap.db", "2", models=(JUDGE,))
    seen = []

    def create(**_):
        seen.append(len(_rows(session.path)))
        assert _rows(session.path)[-1][2] == "reserved_or_unknown"
        if len(seen) == 1:
            raise RuntimeError("429 rate limit")
        return _response(SNAPSHOT)

    monkeypatch.setattr(model_transport.time, "sleep", lambda _: None)
    result = _model(session, create).complete(Prompt(user="Unchanged request."), Tier.JUDGE,
                                             max_tokens=1024)
    assert seen == [1, 2] and result.retries == 1
    assert _rows(session.path) == [
        (JUDGE, 510240, "reserved_or_unknown", 510240),
        (JUDGE, 1450, "measured", 510240)]


def test_unfunded_retry_never_reaches_provider(tmp_path, monkeypatch):
    from nm.shared import model_transport

    session = SessionCallBudget(tmp_path / "cap.db", "0.511", models=(JUDGE,))
    wires = []

    def create(**_):
        wires.append(True)
        raise RuntimeError("429 rate limit")

    monkeypatch.setattr(model_transport.time, "sleep", lambda _: None)
    with pytest.raises(ProviderUnavailable, match="budget"):
        _model(session, create).complete(Prompt(user="Whole request."), Tier.JUDGE,
                                         max_tokens=1024)
    assert wires == [True]
    assert session.status()["charged_usd"] == .51024


def test_paid_truncation_is_settled_before_analysis_rejects_it(tmp_path):
    session = SessionCallBudget(tmp_path / "cap.db", "3", models=(JUDGE,))
    model = _model(session, lambda **_: _response(SNAPSHOT, stop="length"))
    with pytest.raises(OutputTruncated):
        model.complete(Prompt(user="Whole request."), Tier.JUDGE, max_tokens=1024)
    assert _rows(session.path) == [(JUDGE, 1450, "measured", 510240)]


def test_permission_refusal_and_embedding_never_spend_session_money(tmp_path):
    session = SessionCallBudget(tmp_path / "cap.db", "3", models=(JUDGE,))

    def never(**_):
        pytest.fail("No wire is authorised")

    def refuse():
        raise ModelPermissionRefused("Session revoked")

    model = _model(session, never).for_matter_text(refuse)
    with pytest.raises(ModelPermissionRefused):
        model.complete(Prompt(user="Whole request."), Tier.JUDGE, max_tokens=1024)
    with pytest.raises(ModelPermissionRefused, match="embeddings"):
        model.embed(("text",))
    assert session.status()["attempts"] == 0
