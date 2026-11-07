"""The Admin diagnostics (plan AN.46, piece 46i; owner decisions D119 and D128, 7 Nov 2026): is the service well? The server and its code,
the model service, turns in progress, recent turns, the held law, the document scanner, sign-in security, free disk, account mail and the
admin list - each from counts, sizes and short names, each on its own source so that one that cannot be read makes only its own check
unavailable, and none of them carrying an address, a message or a word of an advocate's work. Synthetic stores and files."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nm.app import api
from nm.app.admin_api import admin_router
from nm.app.admin_views import content_free, diagnostics_view
from nm.app.composition import Application
from nm.arrive.admin_access import SETTING, roster_from
from nm.arrive.admin_checks import AdminChecks
from nm.arrive.admin_port import AdminChecksPort, AdminTurnsPort, AdminUnavailable, Consumption, TurnDay, TurnsSummary
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, csrf_token, enrol, utcnow
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.shared.store_file_store import FileMatterStore
from nm.shared.turn_attempt_store import FileTurnAttempts
from tests.test_core_served import KEY, PASSWORD
from tests.test_core_turn import ScriptedModel, searcher

pytestmark = pytest.mark.class_a
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
ROSTER = roster_from({SETTING: "boss@example.test:admin"})


def checks_in(tmp_path, **settings):
    (tmp_path / "root").mkdir(exist_ok=True)
    return AdminChecks(storage=tmp_path / "matters", root=tmp_path / "root", settings=settings, corpus_dir=tmp_path / "law")


@pytest.fixture
def places(tmp_path):
    (tmp_path / "matters").mkdir()
    (tmp_path / "law").mkdir()
    return tmp_path


# -------------------------------------------------------------------------- the sources ---

def test_it_is_the_checks_port(places):
    assert isinstance(checks_in(places), AdminChecks) and hasattr(AdminChecksPort, "law")


def test_turn_attempts_are_counted_by_state_and_a_missing_file_is_zeros_not_a_failure(places):
    checks = checks_in(places)
    assert checks.turn_attempts() == {"running": 0, "retryable": 0, "unconfirmed": 0, "terminal": 0, "finished": 0}
    attempts = FileTurnAttempts(places / "matters" / "turn-attempts.sqlite")
    token = attempts.claim("a" * 64, "b" * 64)["token"]
    attempts.claim("c" * 64, "d" * 64)
    attempts.finish("a" * 64, token, "finished")
    found = checks.turn_attempts()
    assert (found["running"], found["finished"]) == (1, 1)


def test_a_turn_attempt_file_that_will_not_open_is_none_so_only_its_check_fails(places):
    (places / "matters" / "turn-attempts.sqlite").write_bytes(b"not a database at all")
    assert checks_in(places).turn_attempts() is None


def test_the_sign_in_log_is_counted_by_kind_after_the_time_given_and_holds_nobody_s_name(places):
    log = places / "matters" / "auth.log"
    log.write_text("\n".join([
        "2026-11-07T08:00:00.1\tsomeone@example.test\tauthenticated",
        "2026-11-07T08:01:00.1\tsomeone@example.test\twrong password",
        "2026-11-07T08:02:00.1\tother@example.test\tno such advocate",
        "2026-11-07T08:03:00.1\tother@example.test\twrong password",
        "2026-11-07T08:04:00.1\tsomeone@example.test\tsession refused: no activity for 30 minutes; idle since 2026-11-07T07:00",
        "2026-11-07T08:05:00.1\tsomeone@example.test\tsomething new nobody counted",
        "2026-11-06T08:00:00.1\told@example.test\twrong password",
        "a line with no tabs", "not-a-time\tx@example.test\tauthenticated"]) + "\n", encoding="utf8")
    found = checks_in(places).sign_ins(datetime(2026, 11, 7, 0, 0))
    assert found["signed_in"] == 1 and found["wrong_password"] == 2 and found["unknown_account"] == 1
    assert found["session_ended_idle"] == 1 and found["other"] == 1
    assert "example.test" not in repr(found)


def test_no_sign_in_log_is_zeros_and_an_unreadable_one_is_none(places):
    assert set(checks_in(places).sign_ins(datetime(2026, 1, 1)).values()) == {0}
    (places / "matters" / "auth.log").mkdir()
    assert checks_in(places).sign_ins(datetime(2026, 1, 1)) is None


def test_disk_gives_free_and_total_for_the_matters_and_the_law(places):
    found = checks_in(places).disk()
    assert set(found) == {"records", "law"} and all(found[k]["free"] > 0 and found[k]["total"] >= found[k]["free"] for k in found)


def lineage(places, name, file, *, size, passages=10, vectors=10, sampled=5, same=5, bm25=True):
    root = places / "root" / ".nm" / "retrieval"
    root.mkdir(parents=True, exist_ok=True)
    (places / "law" / f"{name}.index").write_bytes(b"v" * size)
    (places / "law" / f"{name}.db").write_bytes(b"d")
    if bm25:
        (places / "law" / f"{name}_bm25").mkdir(exist_ok=True)
    (root / file).write_text(json.dumps({
        "passages": passages, "model": "synthetic-model", "recorded_at": "2026-10-01T00:00:00+00:00",
        "vector_index": {"path": f"{name}.index", "vectors": vectors, "bytes": 100},
        "passage_store": {"path": f"{name}.db", "count": passages}, "bm25": {"path": f"{name}_bm25"},
        "verified": {"sampled": sampled, "same_vector": same}}), encoding="utf8")


def test_the_law_is_reported_from_its_lineage_record_with_sizes_compared_not_hashes(places):
    lineage(places, "acts", "bare_acts.lineage.json", size=100)
    lineage(places, "cases", "judgments.lineage.json", size=99)
    acts, cases = checks_in(places).law()
    assert (acts["collection"], acts["readable"], acts["passages"], acts["files_present"], acts["sizes_as_recorded"]) == (
        "acts", True, 10, True, True)
    assert cases["collection"] == "judgments" and cases["files_present"] and cases["sizes_as_recorded"] is False
    assert acts["model"] == "synthetic-model" and acts["bm25_present"] is True


def test_a_missing_file_a_missing_word_index_and_an_unreadable_record_are_each_said(places):
    lineage(places, "acts", "bare_acts.lineage.json", size=100, bm25=False)
    (places / "law" / "acts.index").unlink()
    (places / "root" / ".nm" / "retrieval" / "judgments.lineage.json").write_text("{not json", encoding="utf8")
    acts, cases = checks_in(places).law()
    assert acts["files_present"] is False and acts["sizes_as_recorded"] is False and acts["bm25_present"] is False
    assert cases["readable"] is False and "passages" not in cases


def test_the_scanner_is_configured_present_and_its_definitions_dated(places):
    assert checks_in(places).scanner() == {"configured": False, "present": False, "definitions_age_days": None}
    definitions = places / "definitions"
    definitions.mkdir()
    scan = places / "clamscan.exe"
    scan.write_bytes(b"x")
    fresh = definitions / "main.cvd"
    fresh.write_bytes(b"x")
    two_days = time.time() - 2 * 86400
    os.utime(fresh, (two_days, two_days))
    found = checks_in(places, NM_CLAMSCAN=str(scan), NM_CLAMAV_DATABASE=str(definitions)).scanner()
    assert found["configured"] and found["present"] and 1.9 <= found["definitions_age_days"] <= 2.1
    assert checks_in(places, NM_CLAMSCAN=str(places / "gone.exe"), NM_CLAMAV_DATABASE=str(definitions)).scanner()["present"] is False


def test_the_outbox_counts_waiting_messages_and_says_whether_any_mail_leaves_the_computer(places):
    assert checks_in(places).outbox() == {"provider": "local-outbox", "delivery": "disabled", "queued": 0, "reaches_a_mailbox": False}
    (places / "matters" / "outbox").mkdir()
    for number in range(3):
        (places / "matters" / "outbox" / f"m{number}.sealed").write_bytes(b"x")
    assert checks_in(places).outbox()["queued"] == 3
    assert checks_in(places, NM_MAIL_PROVIDER="gmail", NM_MAIL_DELIVERY="enabled").outbox()["reaches_a_mailbox"] is True


# --------------------------------------------------------------------------- the view ---

class Usage:
    def __init__(self, rows=(), fails=False):
        self.rows, self.fails = rows, fails

    def consumption(self, since, until, grouping):
        if self.fails:
            raise AdminUnavailable("usage")
        return tuple(Consumption((outcome,), calls, 0, 0, 0, 0, 0, 0, 0.0) for outcome, calls in self.rows)


class Turns:
    def __init__(self, day=None, fails=False):
        self.day, self.fails = day or TurnDay("2026-11-07", answered=3), fails

    def summary(self, since, until):
        if self.fails:
            raise AdminUnavailable("turns")
        return TurnsSummary((self.day,), 40, 90, NOW - timedelta(days=1))


class Checks:
    def __init__(self, **changes):
        self.parts = {
            "turn_attempts": {"running": 1, "retryable": 2, "unconfirmed": 0, "terminal": 0, "finished": 9},
            "sign_ins": {"signed_in": 4, "wrong_password": 1, "unknown_account": 0, "other": 0},
            "disk": {"records": {"free": 100 * 1024 ** 3, "total": 500 * 1024 ** 3}, "law": {"free": 100 * 1024 ** 3, "total": 500 * 1024 ** 3}},
            "law": ({"collection": "acts", "readable": True, "passages": 5, "vectors": 5, "model": "m", "recorded_at": "t", "sampled": 3,
                     "same_vector": 3, "files_present": True, "sizes_as_recorded": True, "bm25_present": True},),
            "scanner": {"configured": True, "present": True, "definitions_age_days": 0.5},
            "outbox": {"provider": "local-outbox", "delivery": "disabled", "queued": 0, "reaches_a_mailbox": False}}
        self.parts.update(changes)

    def turn_attempts(self): return self.parts["turn_attempts"]
    def sign_ins(self, since): return self.parts["sign_ins"]
    def disk(self): return self.parts["disk"]
    def law(self): return self.parts["law"]
    def scanner(self): return self.parts["scanner"]

    def outbox(self):
        if self.parts["outbox"] is None:
            raise AdminUnavailable("outbox")
        return self.parts["outbox"]


CURRENT = {"code_state": "current", "serving": "abcdef0123456789", "tree": "abcdef0123456789"}
PROVIDER = {"provider": "openai", "model": "gpt-6-luna"}


def states(page):
    return {c["id"]: c["state"] for c in page["checks"]}


def view(checks=None, usage=None, turns=None, serving=CURRENT, roster=ROSTER):
    return diagnostics_view(roster, usage or Usage([("ok", 40)]), turns or Turns(), checks or Checks(), NOW, serving, PROVIDER)


def test_a_well_service_is_ok_on_every_check_but_notes_that_mail_stays_on_this_computer():
    page = view()
    assert states(page) == {"server": "ok", "model_service": "ok", "turns_in_progress": "ok", "recent_turns": "ok",
                            "law_acts": "ok", "scanner": "ok", "sign_in_security": "ok", "disk": "ok", "mail": "note",
                            "admin_setting": "ok"}
    assert page["summary"] == {"ok": 9, "attention": 0, "note": 1, "unavailable": 0} and content_free(page)
    assert next(c for c in page["checks"] if c["id"] == "server")["facts"]["running_code"] == "abcdef012345"


def test_stale_code_an_unwell_model_service_unconfirmed_turns_and_a_busy_sign_in_day_each_ask_for_attention():
    page = view(Checks(turn_attempts={"running": 0, "retryable": 0, "unconfirmed": 2, "terminal": 0, "finished": 0},
                       sign_ins={"signed_in": 0, "wrong_password": 15, "unknown_account": 6, "other": 0}),
                Usage([("ok", 10), ("failed", 5)]), Turns(TurnDay("2026-11-07", answered=2, failed=4)),
                {"code_state": "stale", "serving": "a" * 16, "tree": "b" * 16})
    assert {k: v for k, v in states(page).items() if v == "attention"}.keys() == {
        "server", "model_service", "turns_in_progress", "recent_turns", "sign_in_security"}


def test_a_few_calls_are_too_few_to_call_the_model_service_unwell():
    assert states(view(usage=Usage([("ok", 1), ("failed", 2)])))["model_service"] == "ok"


def test_not_assessed_code_is_unavailable_not_current():
    assert states(view(serving={"code_state": "not_assessed"}))["server"] == "unavailable"
    assert states(view(serving={}))["server"] == "unavailable"


def test_the_law_is_in_attention_when_a_file_is_missing_or_a_size_or_a_sample_disagrees_and_unavailable_when_unreadable():
    base = Checks().parts["law"][0]
    for change in ({"files_present": False}, {"sizes_as_recorded": False}, {"bm25_present": False}, {"same_vector": 2},
                   {"passages": 9}):
        assert states(view(Checks(law=({**base, **change},))))["law_acts"] == "attention", change
    assert states(view(Checks(law=({"collection": "acts", "readable": False},))))["law_acts"] == "unavailable"


def test_the_scanner_is_in_attention_when_missing_unconfigured_or_its_definitions_are_old():
    for scanner in ({"configured": False, "present": False, "definitions_age_days": None},
                    {"configured": True, "present": False, "definitions_age_days": 1},
                    {"configured": True, "present": True, "definitions_age_days": 9},
                    {"configured": True, "present": True, "definitions_age_days": None}):
        assert states(view(Checks(scanner=scanner)))["scanner"] == "attention", scanner


def test_low_free_disk_is_attention_by_amount_or_by_share():
    low_amount = {"records": {"free": 5 * 1024 ** 3, "total": 50 * 1024 ** 3}, "law": {"free": 100 * 1024 ** 3, "total": 500 * 1024 ** 3}}
    low_share = {"records": {"free": 40 * 1024 ** 3, "total": 1000 * 1024 ** 3}, "law": {"free": 100 * 1024 ** 3, "total": 500 * 1024 ** 3}}
    assert states(view(Checks(disk=low_amount)))["disk"] == "attention" and states(view(Checks(disk=low_share)))["disk"] == "attention"


def test_a_filling_outbox_is_attention_and_mail_that_reaches_a_mailbox_is_ok():
    assert states(view(Checks(outbox={"provider": "local-outbox", "delivery": "disabled", "queued": 25, "reaches_a_mailbox": False})))[
        "mail"] == "attention"
    assert states(view(Checks(outbox={"provider": "gmail", "delivery": "enabled", "queued": 0, "reaches_a_mailbox": True})))["mail"] == "ok"


def test_a_setting_with_ignored_entries_is_attention():
    assert states(view(roster=roster_from({SETTING: "boss@example.test:admin, typo"})))["admin_setting"] == "attention"


def test_a_source_that_cannot_be_read_makes_only_its_own_check_unavailable():
    page = view(Checks(turn_attempts=None, sign_ins=None, disk=None, outbox=None), Usage(fails=True), Turns(fails=True))
    assert states(page) == {"server": "ok", "model_service": "unavailable", "turns_in_progress": "unavailable",
                            "recent_turns": "unavailable", "law_acts": "ok", "scanner": "ok", "sign_in_security": "unavailable",
                            "disk": "unavailable", "mail": "unavailable", "admin_setting": "ok"}
    assert page["summary"]["unavailable"] == 6


# ------------------------------------------------------------------------- the routes ---

BOSS, VIEWER, ADVOCATE = "boss@example.test", "viewer@example.test", "advocate@example.test"


@pytest.fixture
def served(tmp_path, monkeypatch):
    directory = FileDirectory(tmp_path, key=KEY)
    for who in (BOSS, VIEWER, ADVOCATE):
        directory.enrol(Enrolment(AdvocateIdentity(who, who.split("@")[0].title()), enrol(PASSWORD)))
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    app = Application(root=Path(__file__).resolve().parents[1], model=model, store=FileMatterStore(tmp_path, key=KEY),
                      directory=directory, mail=FileOutbox(tmp_path, key=KEY), legal_search=searcher(),
                      audit_root=tmp_path / "audit", environment={
                          "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path), "NM_MODEL_PROVIDER": "scripted",
                          "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
                          "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts"), "NM_ADMINS": f"{BOSS}:admin,{VIEWER}:view-only"})
    monkeypatch.setattr(api, "_application", app)
    web = FastAPI()
    web.include_router(admin_router(application=api.application, signed_in=api.signed_in, csrf=api.CsrfProtected,
                                    admit_attempt=api._admit_auth_attempt, serving=api.serving_state))
    clients = []

    def client(who):
        made = TestClient(web)
        clients.append(made)
        token = app.directory.open_session(who, api._device("device-1", "testclient"), utcnow())
        made.cookies.update({"nm_session": token, "nm_device": "device-1", "nm_csrf": csrf_token(token)})
        made.headers.update({"origin": "http://testserver", "x-nm-csrf": csrf_token(token)})
        return made

    yield client
    for each in clients:
        each.close()


def test_both_admin_levels_are_given_the_diagnostics_and_an_advocate_is_given_the_404_of_an_address_that_is_not_there(served):
    for who in (BOSS, VIEWER):
        reply = served(who).get("/api/admin/diagnostics")
        assert reply.status_code == 200, reply.text
        page = reply.json()
        assert {c["id"] for c in page["checks"]} >= {"server", "model_service", "law_acts", "law_judgments", "scanner", "disk", "mail"}
        assert page["summary"]["ok"] + page["summary"]["attention"] + page["summary"]["note"] + page["summary"]["unavailable"] == len(
            page["checks"])
    advocate = served(ADVOCATE)
    assert advocate.get("/api/admin/diagnostics").json() == advocate.get("/api/admin/nothing-here").json()
    assert advocate.get("/api/admin/diagnostics").status_code == 404
    assert "example.test" not in served(BOSS).get("/api/admin/diagnostics").text
