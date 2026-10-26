"""The usage sidecar (plan AN.17): each account's trial given once, every call kept and charged at the
cost established, nothing else writable through it, and a schema it did not make refused. Offline,
against a temporary file."""
from __future__ import annotations

import hashlib
import sqlite3

import pytest

from nm.arrive.store_usage import FileUsage
from nm.arrive.usage_port import CALL_FIELDS, TRIAL_MICRO_USD, UsagePort, UsageRefused

pytestmark = pytest.mark.class_a

ADVOCATE = "Advocate@Chambers.in"


def call(**changes):
    record = {"kind": "structured", "operation": "core_understanding", "tier": "routine", "model": "gpt-6-luna",
              "outcome": "ok", "attempts": 1, "tokens_in": 1200, "tokens_out": 300, "cached_tokens": 0,
              "cache_write_tokens": 0, "audio_seconds": None, "micro_usd": 270}
    record.update(changes)
    return record


@pytest.fixture
def usage(tmp_path):
    return FileUsage(tmp_path / "usage.sqlite")


def test_it_is_the_usage_port(usage):
    assert isinstance(usage, UsagePort)


def test_the_first_read_gives_the_trial_once_and_only_once(usage, tmp_path):
    first = usage.standing(ADVOCATE)
    assert first == {"granted": TRIAL_MICRO_USD, "spent": 0, "left": 100, "noticed": None}
    assert usage.standing(ADVOCATE) == first
    # The same account however its id is typed; a store opened again remembers it.
    assert FileUsage(tmp_path / "usage.sqlite").standing("  advocate@chambers.IN ") == first
    with sqlite3.connect(tmp_path / "usage.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM grants WHERE kind='trial'").fetchone() == (1,)


def test_every_call_is_kept_and_charged_at_the_cost_established(usage):
    usage.record(ADVOCATE, call(micro_usd=150_000))
    assert usage.standing(ADVOCATE)["left"] == 50
    # A failed call is kept too: charged at the usage the provider reported, or kept as not established.
    usage.record(ADVOCATE, call(outcome="SchemaViolation", micro_usd=75_000))
    usage.record(ADVOCATE, call(outcome="ProviderUnavailable", attempts=3, tokens_in=None, tokens_out=None,
                                cached_tokens=None, cache_write_tokens=None, micro_usd=None))
    standing = usage.standing(ADVOCATE)
    assert standing["spent"] == 225_000 and standing["left"] == 25
    totals = usage.totals()
    assert totals["calls"] == 3 and totals["micro_usd"] == 225_000 and totals["not_established"] == 1
    assert {row["outcome"]: row["calls"] for row in totals["by_outcome"]} == {
        "ok": 1, "SchemaViolation": 1, "ProviderUnavailable": 1}


def test_an_allowance_can_end_below_nothing_and_reads_as_nothing_left(usage):
    usage.record(ADVOCATE, call(micro_usd=TRIAL_MICRO_USD + 4_000))
    assert usage.standing(ADVOCATE)["left"] == 0


def test_accounts_are_kept_apart_and_named_only_by_a_digest(usage, tmp_path):
    usage.record(ADVOCATE, call(micro_usd=150_000))
    assert usage.standing("someone@else.in")["left"] == 100
    with sqlite3.connect(tmp_path / "usage.sqlite") as db:
        stored = {row[0] for row in db.execute("SELECT account FROM grants UNION SELECT account FROM calls")}
    assert hashlib.sha256(b"advocate@chambers.in").hexdigest() in stored
    raw = (tmp_path / "usage.sqlite").read_bytes()
    assert b"chambers" not in raw and b"else.in" not in raw


def test_an_operator_grant_adds_usage_and_starts_the_notices_again(usage):
    usage.record(ADVOCATE, call(micro_usd=297_000))
    usage.noticed(ADVOCATE, 1)
    standing = usage.grant(ADVOCATE, 4_700_000, note="owner development, 26 Oct 2026")
    assert standing == {"granted": 5_000_000, "spent": 297_000, "left": 95, "noticed": None}
    for wrong in (0, -5, 1_000_000_001, 2.5):
        with pytest.raises(ValueError):
            usage.grant(ADVOCATE, wrong, note="typo")
    with pytest.raises(ValueError):
        usage.grant(ADVOCATE, 1_000, note="  ")


def test_a_notice_once_shown_is_never_brought_back_by_an_older_page(usage):
    usage.noticed(ADVOCATE, 9)
    usage.noticed(ADVOCATE, 10)
    assert usage.standing(ADVOCATE)["noticed"] == 9
    with pytest.raises(ValueError):
        usage.noticed(ADVOCATE, 12)


@pytest.mark.parametrize("change", [
    {"operation": "the client admitted possession in 2011"}, {"model": "gpt 6"}, {"kind": "chat"},
    {"outcome": ""}, {"attempts": 0}, {"tokens_in": -1}, {"micro_usd": 1.5}, {"audio_seconds": "12"},
])
def test_nothing_but_a_calls_names_and_numbers_can_be_written(usage, change):
    with pytest.raises(ValueError):
        usage.record(ADVOCATE, call(**change))


def test_a_record_with_a_field_more_or_less_is_refused(usage):
    with pytest.raises(ValueError):
        usage.record(ADVOCATE, {**call(), "prompt": "words"})
    with pytest.raises(ValueError):
        usage.record(ADVOCATE, {name: value for name, value in call().items() if name != "micro_usd"})
    assert len(CALL_FIELDS) == 12


def test_a_store_it_did_not_make_is_refused_and_a_lost_file_is_not_remade(tmp_path):
    foreign = tmp_path / "foreign.sqlite"
    with sqlite3.connect(foreign) as db:
        db.execute("CREATE TABLE calls (account TEXT)")
    with pytest.raises(UsageRefused):
        FileUsage(foreign)
    usage = FileUsage(tmp_path / "usage.sqlite")
    (tmp_path / "usage.sqlite").unlink()
    with pytest.raises(UsageRefused):
        usage.standing(ADVOCATE)
