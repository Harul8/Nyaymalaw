"""The operator launcher cannot mint scope, consent, money or a client cutover."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from development_environment.developer_tooling import launch_fictional_brain as launch
from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_port import Tier

ACTOR = "advocate-one"
MATTER = "mat_000000000001"
REFERENCE = "OWNER-RECORDED-FICTIONAL-EVALUATION"


def _record(now):
    return {
        "schema": 2,
        "approval_reference": REFERENCE,
        "approved_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(minutes=45)).isoformat(),
        "actor_id": ACTOR,
        "matter_ids": [MATTER],
        "matter_attestations": [{
            "matter_id": MATTER,
            "classification": "fictional_only",
            "attested_by": ACTOR,
            "attested_at": now.isoformat(),
        }],
        "maximum_matter_count": 60,
        "maximum_total_usd": "5",
        "author_model": launch.AUTHOR,
        "verifier_model": launch.VERIFIER,
        "interaction_protocol_version": 7,
        "purpose": launch.PURPOSE,
    }


def _ledger(path, *, maximum=5_000_000, state="measured", charge=500,
            model=launch.AUTHOR):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE budget (singleton INTEGER PRIMARY KEY, maximum INTEGER)")
        db.execute("INSERT INTO budget VALUES (1, ?)", (maximum,))
        db.execute("CREATE TABLE attempts (charge INTEGER, state TEXT, model TEXT)")
        db.execute("INSERT INTO attempts VALUES (?,?,?)", (charge, state, model))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    from nm.app import model_permission

    now = datetime(2026, 9, 28, 10, tzinfo=timezone.utc)
    ledger = tmp_path / ".nm" / "evaluations" / "legal-brain-20260927-usd5.sqlite"
    _ledger(ledger)
    app = SimpleNamespace(
        store=SimpleNamespace(load=lambda ident: SimpleNamespace(id=ident, advocate_id=ACTOR)
                              if ident == MATTER else None),
        directory=object(),
        source_generation_guard=lambda: SimpleNamespace(
            version="exact-source-version", binding={"knowledge_bytes": {"one": "two"}}),
    )
    monkeypatch.setattr(model_permission, "require_permission", lambda *_: None)
    return tmp_path, now, ledger, app


def _validate(setup, record, **overrides):
    root, now, ledger, app = setup
    args = dict(actor=ACTOR, matter_ids=(MATTER,), approval_reference=REFERENCE,
                application=app, ledger=ledger, now=now)
    args.update(overrides)
    return launch.validate_authorization(record, **args)


def test_exact_current_private_fictional_scope_and_existing_ledger_pass(setup):
    _, now, _, _ = setup
    assert _validate(setup, _record(now)) == now + timedelta(minutes=45)


@pytest.mark.parametrize("unsafe", [
    "../mat_000000000001", "..", ".", "/mat_000000000001",
    "mat_000000000001/../mat_000000000001",
    "mat_000000000001\\..\\mat_000000000001",
    "C:\\mat_000000000001", "mat_000000000001.nm",
    "MAT_000000000001", "mat_000000000001%2f..",
])
def test_matter_ids_are_opaque_before_store_access(setup, unsafe):
    _, now, _, app = setup
    app.store.load = lambda _: (_ for _ in ()).throw(
        AssertionError("unsafe ID reached matter storage"))
    record = _record(now)
    record["matter_ids"] = [unsafe]
    record["matter_attestations"][0]["matter_id"] = unsafe
    with pytest.raises(launch.ApprovalRefused):
        _validate(setup, record, matter_ids=(unsafe,))


def test_both_live_matter_id_families_are_admitted_when_exactly_owned(setup):
    _, now, _, app = setup
    modern = "m_" + "a" * 32
    app.store.load = lambda ident: SimpleNamespace(id=ident, advocate_id=ACTOR)
    record = _record(now)
    record["matter_ids"] = [modern]
    record["matter_attestations"][0]["matter_id"] = modern
    assert _validate(setup, record, matter_ids=(modern,)) > now


@pytest.mark.parametrize("change", [
    {"actor_id": "foreign"},
    {"matter_ids": ["foreign"]},
    {"maximum_total_usd": "6"},
    {"author_model": "gpt-5.1-2025-11-13"},
    {"verifier_model": "gpt-4o-mini-2024-07-18"},
    {"purpose": "client_matters"},
    {"interaction_protocol_version": 999},
    {"schema": 1},
    {"extra_approval_flag": True},
])
def test_scope_money_models_and_unknown_fields_cannot_be_borrowed(setup, change):
    _, now, _, _ = setup
    with pytest.raises(launch.ApprovalRefused):
        _validate(setup, {**_record(now), **change})


@pytest.mark.parametrize("attestations", [
    [],
    [{"matter_id": MATTER, "classification": "real_client", "attested_by": ACTOR,
      "attested_at": "2026-09-28T10:00:00+00:00"}],
    [{"matter_id": MATTER, "classification": "fictional_only", "attested_by": "foreign",
      "attested_at": "2026-09-28T10:00:00+00:00"}],
])
def test_every_matter_needs_its_own_fictional_attestation(setup, attestations):
    _, now, _, _ = setup
    with pytest.raises(launch.ApprovalRefused):
        _validate(setup, {**_record(now), "matter_attestations": attestations})


def test_current_expiry_owner_and_account_permission_are_required(setup, monkeypatch):
    _, now, _, app = setup
    record = _record(now)
    for expired in (now.isoformat(), (now + timedelta(hours=3)).isoformat()):
        with pytest.raises(launch.ApprovalRefused):
            _validate(setup, {**record, "expires_at": expired})
    app.store.load = lambda _: SimpleNamespace(id=MATTER, advocate_id="foreign")
    with pytest.raises(launch.ApprovalRefused):
        _validate(setup, record)
    app.store.load = lambda _: SimpleNamespace(id="mat_000000000002", advocate_id=ACTOR)
    with pytest.raises(launch.ApprovalRefused):
        _validate(setup, record)
    app.store.load = lambda _: SimpleNamespace(id=MATTER, advocate_id=ACTOR)

    from nm.app import model_permission
    monkeypatch.setattr(model_permission, "require_permission",
                        lambda *_: (_ for _ in ()).throw(
                            model_permission.ModelPermissionRefused("permission revoked")))
    with pytest.raises(model_permission.ModelPermissionRefused):
        _validate(setup, record)


def test_missing_reset_or_overbound_ledger_is_not_a_new_budget(setup):
    _, now, ledger, _ = setup
    record = _record(now)
    ledger.unlink()
    with pytest.raises(launch.ApprovalRefused, match="original USD5 ledger is absent"):
        _validate(setup, record)
    _ledger(ledger, maximum=6_000_000)
    with pytest.raises(launch.ApprovalRefused):
        _validate(setup, record)
    ledger.unlink()
    _ledger(ledger, state="measured_over_bound")
    with pytest.raises(launch.ApprovalRefused):
        _validate(setup, record)
    with closing(sqlite3.connect(ledger)) as db, db:
        db.execute("DELETE FROM attempts")
    with pytest.raises(launch.ApprovalRefused):
        _validate(setup, record)


@pytest.mark.parametrize("bad", [
    {"charge": -1},
    {"charge": "not-a-number"},
    {"charge": 30_001},
    {"charge": 1, "state": "unrecognised"},
    {"charge": 1, "state": "measured_over_bound"},
    {"charge": 1, "state": "reserved_or_unknown"},
    {"charge": 500, "model": "unapproved-model"},
])
def test_malformed_existing_ledger_never_looks_like_remaining_money(setup, bad):
    _, now, ledger, _ = setup
    ledger.unlink()
    _ledger(ledger, **bad)
    with pytest.raises(launch.ApprovalRefused):
        _validate(setup, _record(now))


def test_total_over_five_dollars_is_refused_even_when_each_attempt_is_valid(setup):
    _, now, ledger, _ = setup
    with closing(sqlite3.connect(ledger)) as db, db:
        db.executemany("INSERT INTO attempts VALUES (?,?,?)",
                       [(550_000, "measured", launch.VERIFIER)] * 10)
    with pytest.raises(launch.ApprovalRefused):
        _validate(setup, _record(now))


def test_only_private_file_can_supply_authorization_and_change_revokes(setup, monkeypatch):
    root, _, ledger, app = setup
    now = datetime.now(timezone.utc)
    record = _record(now)
    private = root / ".nm" / "evaluations" / "current.json"
    private.write_text(json.dumps(record), encoding="utf8")
    loaded, fingerprint = launch._private_authorization(private, root=root)
    assert loaded == record and len(fingerprint) == 64
    external = root / "public.json"
    external.write_text(json.dumps(record), encoding="utf8")
    with pytest.raises(launch.ApprovalRefused):
        launch._private_authorization(external, root=root)

    monkeypatch.setattr(launch, "ROOT", root)
    monkeypatch.setattr(launch, "LEDGER", ledger)
    config = ModelConfig({
        Tier.ROUTINE: TierConfig(Tier.ROUTINE, "openai", launch.AUTHOR, None,
                                 "https://api.openai.com/v1"),
        Tier.JUDGE: TierConfig(Tier.JUDGE, "openai", launch.VERIFIER, None,
                               "https://api.openai.com/v1"),
    })
    pair = SimpleNamespace(config=config)
    grant = launch._install_grant(app, record=record, fingerprint=fingerprint,
        authorization_path=private, actor=ACTOR, matter_ids=(MATTER,),
        approval_reference=REFERENCE, expires=now + timedelta(minutes=45), pair=pair)
    assert grant.permission_current(app, grant.scope) is True
    class AfterExpiry(datetime):
        @classmethod
        def now(cls, tz=None):
            return now + timedelta(minutes=46)

    actual_datetime = launch.datetime
    monkeypatch.setattr(launch, "datetime", AfterExpiry)
    assert grant.permission_current(app, grant.scope) is False
    monkeypatch.setattr(launch, "datetime", actual_datetime)
    assert grant.permission_current(app, grant.scope) is True
    from nm.app import model_permission
    monkeypatch.setattr(model_permission, "require_permission",
                        lambda *_: (_ for _ in ()).throw(
                            model_permission.ModelPermissionRefused("permission revoked")))
    assert grant.permission_current(app, grant.scope) is False
    monkeypatch.setattr(model_permission, "require_permission", lambda *_: None)
    with closing(sqlite3.connect(ledger)) as db, db:
        db.execute("DELETE FROM attempts")
    assert grant.permission_current(app, grant.scope) is False
    with closing(sqlite3.connect(ledger)) as db, db:
        db.execute("INSERT INTO attempts VALUES (500,'measured',?)", (launch.AUTHOR,))
    private.write_text(json.dumps({**record, "matter_ids": ["foreign"]}), encoding="utf8")
    assert grant.permission_current(app, grant.scope) is False
