"""Offline durable ownership/fencing checks; no model or matter content is stored."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import sqlite3

import pytest

from nm.shared.turn_attempt_port import AttemptRefused, TurnAttemptPort
from nm.shared.turn_attempt_store import FileTurnAttempts

pytestmark = pytest.mark.class_a

IDENTITY = hashlib.sha256(b"synthetic-owner/synthetic-chat/turn-one").hexdigest()
REQUEST = hashlib.sha256(b"private test narrative plus original context version").hexdigest()
OTHER = hashlib.sha256(b"different request").hexdigest()


@pytest.fixture
def ledger(tmp_path): return FileTurnAttempts(tmp_path / "turn-attempts.sqlite3")


def refused(code, action):
    with pytest.raises(AttemptRefused) as caught:
        action()
    assert caught.value.code == code and str(caught.value) == code


def test_claim_is_content_free_and_running_survives_a_process_restart(ledger):
    assert isinstance(ledger, TurnAttemptPort)
    claim = ledger.claim(IDENTITY, REQUEST)
    assert set(claim) == {"token", "correction_used"}
    assert len(claim["token"]) == 64 and claim["correction_used"] is False
    reopened = FileTurnAttempts(ledger.path)
    refused("busy", lambda: reopened.claim(IDENTITY, REQUEST))
    wire = ledger.path.read_bytes()
    for private in (b"synthetic-owner", b"synthetic-chat", b"private test narrative",
                    b"NM_MODEL_API_KEY", b"rejected draft"):
        assert private not in wire


def test_changed_request_conflicts_even_after_explicit_retryable_finish(ledger):
    claimed = ledger.claim(IDENTITY, REQUEST)
    refused("conflict", lambda: ledger.claim(IDENTITY, OTHER))
    ledger.finish(IDENTITY, claimed["token"], "retryable", "provider_unavailable")
    refused("conflict", lambda: FileTurnAttempts(ledger.path).claim(IDENTITY, OTHER))


def test_retry_preserves_spent_allowance_and_changes_the_fencing_token(ledger):
    first = ledger.claim(IDENTITY, REQUEST)
    ledger.consume_correction(IDENTITY, first["token"])
    refused("terminal", lambda: ledger.consume_correction(IDENTITY, first["token"]))
    ledger.finish(IDENTITY, first["token"], "retryable", "provider_unavailable")
    second = FileTurnAttempts(ledger.path).claim(IDENTITY, REQUEST)
    assert second["correction_used"] is True and second["token"] != first["token"]
    refused("conflict", lambda: ledger.finish(IDENTITY, first["token"], "terminal"))
    refused("conflict", lambda: ledger.consume_correction(IDENTITY, first["token"]))
    refused("terminal", lambda: ledger.consume_correction(IDENTITY, second["token"]))


def test_unused_correction_is_available_after_retryable_provider_failure(ledger):
    first = ledger.claim(IDENTITY, REQUEST)
    ledger.finish(IDENTITY, first["token"], "retryable")
    second = ledger.claim(IDENTITY, REQUEST)
    assert second["correction_used"] is False
    ledger.consume_correction(IDENTITY, second["token"])


@pytest.mark.parametrize("state,code", [("terminal", "terminal"), ("finished", "terminal"),
                                        ("unconfirmed", "unconfirmed")])
def test_final_states_cannot_be_reopened_or_downgraded(ledger, state, code):
    claimed = ledger.claim(IDENTITY, REQUEST)
    ledger.finish(IDENTITY, claimed["token"], state, "owned_status")
    reopened = FileTurnAttempts(ledger.path)
    reopened.finish(IDENTITY, claimed["token"], state, "owned_status")  # Lost ack replay.
    refused(code, lambda: reopened.claim(IDENTITY, REQUEST))
    refused(code, lambda: reopened.finish(IDENTITY, claimed["token"], "retryable"))
    refused(code, lambda: reopened.consume_correction(IDENTITY, claimed["token"]))
    refused(code, lambda: reopened.finish(IDENTITY, claimed["token"], state, "changed_status"))


def test_different_opaque_owners_are_independent(ledger):
    first = ledger.claim(IDENTITY, REQUEST)
    ledger.finish(IDENTITY, first["token"], "terminal")
    assert ledger.claim(OTHER, REQUEST)["correction_used"] is False


def test_two_concurrent_claimants_cannot_both_dispatch(ledger):
    def claim(_):
        try:
            return FileTurnAttempts(ledger.path).claim(IDENTITY, REQUEST)
        except AttemptRefused as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, range(2)))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert results.count("busy") == 1


def test_two_concurrent_correction_requests_consume_only_once(ledger):
    claim = ledger.claim(IDENTITY, REQUEST)
    def consume(_):
        try:
            FileTurnAttempts(ledger.path).consume_correction(IDENTITY, claim["token"])
            return "consumed"
        except AttemptRefused as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(consume, range(2)))
    assert sorted(results) == ["consumed", "terminal"]


@pytest.mark.parametrize("damage", ["version", "column", "extra_table", "missing_table", "trigger"])
def test_unknown_database_schema_is_refused_without_automatic_migration(ledger, damage):
    claim = ledger.claim(IDENTITY, REQUEST)
    with sqlite3.connect(ledger.path) as db:
        if damage == "version": db.execute("PRAGMA user_version=99")
        elif damage == "column": db.execute("ALTER TABLE turn_attempts ADD COLUMN ignored TEXT")
        elif damage == "extra_table": db.execute("CREATE TABLE unrelated(value TEXT)")
        elif damage == "missing_table": db.execute("DROP TABLE turn_attempts")
        else: db.execute("CREATE TRIGGER change_owner AFTER INSERT ON turn_attempts BEGIN SELECT 1; END")
    refused("storage", lambda: ledger.finish(IDENTITY, claim["token"], "retryable"))
    refused("storage", lambda: FileTurnAttempts(ledger.path))


@pytest.mark.parametrize("field,value", [("state", "invented_state"), ("correction_used", 7),
    ("request_digest", "private message"), ("token", "changed"), ("code", "not valid metadata")])
def test_corrupt_attempt_never_becomes_a_new_claim(ledger, field, value):
    ledger.claim(IDENTITY, REQUEST)
    with sqlite3.connect(ledger.path) as db:
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute(f"UPDATE turn_attempts SET {field}=? WHERE identity=?", (value, IDENTITY))
    refused("storage", lambda: ledger.claim(IDENTITY, REQUEST))


def test_disappeared_database_is_not_recreated_by_an_existing_adapter(ledger):
    ledger.claim(IDENTITY, REQUEST)
    ledger.path.unlink()
    refused("storage", lambda: ledger.claim(IDENTITY, REQUEST))
    assert not ledger.path.exists()


def test_existing_empty_or_non_sqlite_file_is_not_reinitialized(tmp_path):
    for name, content in (("empty.sqlite3", b""), ("broken.sqlite3", b"damaged database")):
        path = tmp_path / name
        path.write_bytes(content)
        refused("storage", lambda: FileTurnAttempts(path))
        assert path.read_bytes() == content


def test_lost_claim_acknowledgement_keeps_conservative_running_ownership(ledger, monkeypatch):
    original = ledger._transaction
    @contextmanager
    def lose_ack():
        with original() as db:
            yield db
        raise AttemptRefused("storage")
    monkeypatch.setattr(ledger, "_transaction", lose_ack)
    refused("storage", lambda: ledger.claim(IDENTITY, REQUEST))
    refused("busy", lambda: FileTurnAttempts(ledger.path).claim(IDENTITY, REQUEST))


def test_lost_correction_acknowledgement_does_not_restore_allowance(ledger, monkeypatch):
    claimed = ledger.claim(IDENTITY, REQUEST)
    original = ledger._transaction
    @contextmanager
    def lose_ack():
        with original() as db:
            yield db
        raise AttemptRefused("storage")
    monkeypatch.setattr(ledger, "_transaction", lose_ack)
    refused("storage", lambda: ledger.consume_correction(IDENTITY, claimed["token"]))
    reopened = FileTurnAttempts(ledger.path)
    reopened.finish(IDENTITY, claimed["token"], "retryable")
    assert reopened.claim(IDENTITY, REQUEST)["correction_used"] is True


def test_unrecognised_identity_token_state_and_prose_are_not_stored(ledger):
    refused("conflict", lambda: ledger.claim("A client name", REQUEST))
    refused("conflict", lambda: ledger.claim(IDENTITY, "A private user message"))
    refused("conflict", lambda: ledger.consume_correction(IDENTITY, OTHER))
    refused("conflict", lambda: ledger.finish(IDENTITY, OTHER, "terminal"))
    claim = ledger.claim(IDENTITY, REQUEST)
    refused("conflict", lambda: ledger.finish(IDENTITY, claim["token"], "invented_state"))
    refused("conflict", lambda: ledger.finish(IDENTITY, claim["token"], "retryable", "Private client words."))
    refused("busy", lambda: ledger.claim(IDENTITY, REQUEST))
    wire = ledger.path.read_bytes()
    assert b"A client name" not in wire and b"A private user message" not in wire


def test_invalid_state_does_not_consume_or_change_a_claim(ledger):
    claim = ledger.claim(IDENTITY, REQUEST)
    refused("conflict", lambda: ledger.finish(IDENTITY, claim["token"], ["terminal"]))
    ledger.consume_correction(IDENTITY, claim["token"])
    ledger.finish(IDENTITY, claim["token"], "terminal", "G-GROUND")
