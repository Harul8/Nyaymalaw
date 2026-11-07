"""What the Admin pages are told (plan AN.46, piece 46f; owner decisions D118-D119, 7 Nov 2026): the users, one user, the usage and
the overview - usage statistics, balance and consumption beside the account facts they belong to, and no conversation, file or
record. Built over the real directory and usage readers on synthetic accounts and calls."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from nm.app import admin_views
from nm.app.admin_views import PERIODS, content_free, digest, overview_view, user_view, users_view, usage_view
from nm.arrive import store_usage
from nm.arrive.admin_access import SETTING, roster_from
from nm.arrive.admin_directory import AdminFileDirectory
from nm.arrive.admin_usage import AdminUsage
from nm.arrive.advocate_contracts import (PRIVACY_NOTICE_VERSION, AdvocateIdentity, Enrolment, enrol,
                                          registration_consent)
from nm.arrive.professional_access_contracts import ProfessionalApproval
from nm.arrive.store_directory import FileDirectory
from nm.arrive.store_usage import FileUsage
from nm.arrive.usage_port import TRIAL_MICRO_USD
from nm.shared.external_ai_contracts import NOTICE_VERSION, ModelPermission

pytestmark = pytest.mark.class_a

KEY = "Synthetic-admin-views-key-52"
PASSWORD = "Synthetic-fixture-password-72!"
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)  # 17:30 on 7 Nov in India
ROSTER = roster_from({SETTING: "boss@example.test:admin, viewer@example.test:view-only"})


def call(**changes):
    record = {"kind": "structured", "operation": "core_understanding", "tier": "routine", "model": "gpt-6-luna",
              "outcome": "ok", "attempts": 1, "tokens_in": 1000, "tokens_out": 200, "cached_tokens": 100,
              "cache_write_tokens": 50, "audio_seconds": None, "micro_usd": 1000}
    record.update(changes)
    return record


class World:
    def __init__(self, tmp_path, monkeypatch):
        self.tmp_path = tmp_path
        self.directory = FileDirectory(tmp_path, key=KEY)
        self.usage = FileUsage(tmp_path / "usage.sqlite")
        self.clock = {"at": NOW}
        monkeypatch.setattr(store_usage, "_now", lambda: self.clock["at"].isoformat(timespec="seconds"))
        self.admin_directory = AdminFileDirectory(tmp_path, key=KEY)
        self.admin_usage = AdminUsage(tmp_path / "usage.sqlite")

    def account(self, who, name=None, *, sharing=False, approval_days=None, start=True):
        self.directory.enrol(Enrolment(AdvocateIdentity(who, name or who.split("@")[0]), enrol(PASSWORD),
                                       NOW - timedelta(days=60)))
        if sharing:
            self.directory.record_model_permission(
                ModelPermission(who, NOTICE_VERSION, True, NOW - timedelta(days=3), 1), expected_version=0)
        if approval_days is not None:
            self.directory.record_professional_approval(
                ProfessionalApproval(who, "reviewer@example.test", "certificate", "ref", "a" * 64,
                                     NOW - timedelta(days=20), NOW + timedelta(days=approval_days)),
                expected_version=0, now=NOW)
        if start:
            self.usage.standing(who)
        return who

    def spend(self, who, when, **changes):
        self.clock["at"] = when
        self.usage.record(who, call(**changes))

    def views(self, **kwargs):
        args = (ROSTER, self.admin_directory, self.admin_usage)
        return {"users": users_view(*args, NOW), "usage": usage_view(*args, NOW, 30),
                "overview": overview_view(*args, NOW)}


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


def populate(world):
    world.account("boss@example.test", "Boss", sharing=True)
    world.account("viewer@example.test", "Viewer")
    world.account("anita@example.test", "Anita Rao", sharing=True, approval_days=10)
    world.account("never@example.test", "Never Used", start=False)
    world.spend("anita@example.test", NOW - timedelta(days=2), micro_usd=TRIAL_MICRO_USD - 20_000)
    world.spend("anita@example.test", NOW - timedelta(days=1), model="gpt-6-1-sol", operation="response_writer", micro_usd=5000)
    world.spend("boss@example.test", NOW - timedelta(hours=2), micro_usd=7000)
    world.spend("viewer@example.test", NOW - timedelta(hours=1), outcome="ProviderUnavailable", micro_usd=None)
    world.directory.open_session("anita@example.test", "d1", NOW - timedelta(minutes=20), client_label="Chrome on Windows")


def test_the_users_page_gives_each_account_its_level_status_approval_sharing_and_allowance(world):
    populate(world)
    page = users_view(ROSTER, world.admin_directory, world.admin_usage, NOW)
    rows = {r["id"]: r for r in page["accounts"]}
    assert [r["id"] for r in page["accounts"]] == sorted(rows)
    assert (rows["boss@example.test"]["level"], rows["boss@example.test"]["level_label"]) == ("admin", "Admin")
    assert rows["viewer@example.test"]["level_label"] == "Admin (view only)"
    anita = rows["anita@example.test"]
    assert (anita["level"], anita["level_label"], anita["status"]) == ("advocate", "Advocate", "active")
    assert anita["professional"] == {"state": "approved", "valid_until": (NOW + timedelta(days=10)).isoformat()}
    assert anita["ai_sharing"] is True and anita["live_sessions"] == 1 and anita["name"] == "Anita Rao"
    assert anita["allowance"] == {"started": True, "granted": TRIAL_MICRO_USD, "spent": TRIAL_MICRO_USD - 15_000, "left_percent": 5}
    assert rows["never@example.test"]["allowance"] == {"started": False, "granted": None, "spent": None, "left_percent": None}
    assert page["totals"] == {"accounts": 4, "admins": 2, "advocates": 2, "suspended": 0, "unreadable": 0, "waiting": 0,
                              "ai_sharing_on": 2, "approved": 1}


def test_a_suspended_account_an_unreadable_one_and_an_email_waiting_are_facts_beside_the_level(world, tmp_path):
    world.account("paused@example.test", "Paused")
    path = world.directory._advocate_path("paused@example.test")
    doc = json.loads(path.read_text())
    doc["suspended"] = {"by": "boss@example.test"}
    path.write_text(json.dumps(doc))
    (tmp_path / "advocates" / "broken@example.test.nm").write_bytes(b"\x00damaged")
    world.directory.begin_pending_registration(
        Enrolment(AdvocateIdentity(id="waiting@example.test", name="Waiting", email="waiting@example.test"), enrol(PASSWORD),
                  NOW - timedelta(hours=1), registration_consent(PRIVACY_NOTICE_VERSION, True, True, NOW)),
        NOW - timedelta(hours=1))
    page = users_view(ROSTER, world.admin_directory, world.admin_usage, NOW)
    rows = {r["id"]: r for r in page["accounts"]}
    assert rows["paused@example.test"]["status"] == "suspended" and rows["paused@example.test"]["level"] == "advocate"
    assert rows["broken@example.test"]["status"] == "unreadable"
    assert rows["broken@example.test"]["allowance"]["started"] is False and rows["broken@example.test"]["ai_sharing"] is None
    assert [w["email"] for w in page["waiting"]] == ["waiting@example.test"] and page["waiting_readable"]
    assert page["totals"]["suspended"] == 1 and page["totals"]["unreadable"] == 1 and page["totals"]["waiting"] == 1


def test_one_users_page_has_their_devices_allowance_and_a_quiet_day_for_every_day_of_the_period(world):
    populate(world)
    page = user_view("Anita@Example.test", ROSTER, world.admin_directory, world.admin_usage, NOW)
    assert page["id"] == "anita@example.test" and page["allowance"]["left_percent"] == 5
    assert [(s["client_label"], s["live"]) for s in page["sessions"]] == [("Chrome on Windows", True)]
    days = page["usage"]["by_day"]
    assert len(days) == 30 and days[-1]["day"] == "2026-11-07" and days[0]["day"] == "2026-10-09"
    assert {d["day"]: (d["calls"], d["micro_usd"]) for d in days if d["calls"]} == {
        "2026-11-05": (1, TRIAL_MICRO_USD - 20_000), "2026-11-06": (1, 5000)}
    assert page["usage"]["totals"]["calls"] == 2 and page["usage"]["totals"]["micro_usd"] == TRIAL_MICRO_USD - 15_000
    assert user_view("nobody@example.test", ROSTER, world.admin_directory, world.admin_usage, NOW) is None


def test_the_usage_page_has_the_totals_the_daily_cost_by_model_the_top_accounts_and_the_funnel(world):
    populate(world)
    page = usage_view(ROSTER, world.admin_directory, world.admin_usage, NOW, 7)
    assert page["period"]["days"] == 7 and [d["day"] for d in page["by_day"]] == [
        f"2026-11-0{n}" for n in range(1, 8)]
    assert page["tiles"]["calls"] == 4 and page["tiles"]["cost_not_established"] == 1
    assert page["tiles"]["micro_usd"] == TRIAL_MICRO_USD - 20_000 + 5000 + 7000
    assert page["tiles"]["active_accounts"] == 3
    assert page["models"] == ["gpt-6-1-sol", "gpt-6-luna"]
    the_sixth = {d["day"]: d for d in page["by_day"]}["2026-11-06"]
    assert the_sixth["models"] == {"gpt-6-1-sol": 5000} and the_sixth["calls"] == 1
    assert [t["id"] for t in page["top_accounts"]][:1] == ["anita@example.test"]
    assert page["top_accounts"][0]["name"] == "Anita Rao"
    assert {o["outcome"]: o["calls"] for o in page["by_outcome"]} == {"ProviderUnavailable": 1, "ok": 3}
    assert page["funnel"] == {"waiting": 0, "accounts": 4, "ai_sharing_on": 2, "started_allowance": 3, "used_in_period": 3}
    assert page["answers"] == {"available": False, "needs": "the turn record"}


def test_spend_by_an_account_the_directory_no_longer_holds_is_still_counted_without_a_name(world):
    populate(world)
    world.spend("gone@example.test", NOW - timedelta(hours=3), micro_usd=999_999)
    top = usage_view(ROSTER, world.admin_directory, world.admin_usage, NOW, 7)["top_accounts"][0]
    assert top == {"id": None, "name": "", "calls": 1, "micro_usd": 999_999}


def test_the_overview_says_what_needs_attention_and_nothing_that_does_not(world):
    populate(world)
    page = overview_view(ROSTER, world.admin_directory, world.admin_usage, NOW)
    assert {item["kind"]: item["count"] for item in page["needs_attention"]} == {"allowance_low": 1, "approval_ending": 1}
    assert page["accounts"]["accounts"] == 4 and page["live_sessions"] == 1 and page["signed_in_last_7_days"] == 1
    assert page["week"]["tiles"]["calls"] == 4 and len(page["week"]["by_day"]) == 7


def test_only_the_listed_periods_are_answered(world):
    populate(world)
    assert PERIODS == (7, 30, 90)
    for bad in (0, 1, 14, 365, "30", None):
        with pytest.raises(ValueError):
            usage_view(ROSTER, world.admin_directory, world.admin_usage, NOW, bad)


def test_every_page_is_content_free_and_carries_no_address_other_than_an_accounts_own(world):
    populate(world)
    shown = world.views()
    for page in shown.values():
        content_free(page)
    text = json.dumps(shown)
    for secret in ("scrypt", "salt", PASSWORD, KEY):
        assert secret not in text
    assert {"users", "usage", "overview"} == set(shown)


def test_a_payload_with_a_key_an_advocate_s_work_would_sit_under_is_refused_wherever_it_is(world):
    for bad in ({"message": "x"}, {"a": {"b": [{"Matter": 1}]}}, [{"deep": ({"token": "t"},)}], {"x": {"Document": {}}}):
        with pytest.raises(ValueError):
            content_free(bad)
    assert content_free({"tokens_in": 3, "name": "ok", "answers": {"available": False}}) is not None
    assert digest("Anita@Example.test ") == digest("anita@example.test") and len(digest("a@b.test")) == 64
    assert admin_views.FORBIDDEN_KEYS >= {"message", "matter", "document", "chat", "password", "token"}
