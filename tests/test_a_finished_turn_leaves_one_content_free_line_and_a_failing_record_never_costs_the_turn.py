"""A finished turn leaves one content-free line, and the record failing never costs the turn (plan AN.46, piece 46h; owner decision D120,
7 Nov 2026: "Yes add it"). Through the real login and stack with a scripted model; the turn's own outcomes are driven by the turn code."""
from __future__ import annotations

import hashlib
import logging
import sqlite3
from contextlib import closing

import pytest

from nm.arrive.turn_event_port import TurnEventRefused
from nm.core_engine import turn as turn_code
from nm.core_engine.conversation import ConversationRefused
from nm.core_engine.documents import DocumentRefused
from nm.shared.egress_contracts import EgressRefused
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.arrive.usage_port import AllowanceUsedUp
from tests.test_core_served import OWNER, served, successful  # noqa: F401 -- the fixture

pytestmark = pytest.mark.class_a
DIGEST = hashlib.sha256(OWNER.encode("utf8")).hexdigest()


def lines(served):
    path = served.app.environment["NM_MATTER_STORE"] + "/turn-events.sqlite"
    with closing(sqlite3.connect(path)) as db:
        return db.execute("SELECT account,started_at,ended_at,seconds,outcome,model,effort,calls,micro_usd,documents "
                          "FROM turns ORDER BY id").fetchall()


def run(served, **changes):
    asked = {"advocate_id": OWNER, "session_current": lambda: True, "message": "Inspect this reported account.",
             "turn_id": "turn-x"}
    asked.update(changes)
    return served.app.run_turn(**asked)


def raising(monkeypatch, exc):
    def process(*args, **kwargs):
        raise exc
    monkeypatch.setattr(turn_code, "process", process)


def test_an_answered_turn_leaves_one_line_with_the_calls_cost_and_account_digest_and_no_word_of_the_turn(served):
    reply = successful(served, message="PURPLE-ELEPHANT-4471 the tenant refused the notice")
    (line,) = lines(served)
    account, started, ended, seconds, outcome, model, effort, calls, micro_usd, documents = line
    assert (account, outcome, model, effort, documents) == (DIGEST, "answered", "gpt-6-luna", "medium", 0)  # the page sends its defaults, which are what the advocate chose
    assert calls == reply["metrics"]["llm_calls"] and micro_usd == round(reply["metrics"]["cost_usd"] * 1_000_000)
    assert started <= ended and seconds >= 0
    on_disk = (served.app.environment["NM_MATTER_STORE"] + "/turn-events.sqlite")
    data = open(on_disk, "rb").read()
    for private in (b"PURPLE-ELEPHANT", b"tenant", reply["chat_id"].encode(), reply["turn_id"].encode(), OWNER.encode()):
        assert private not in data


def test_the_choices_the_advocate_made_and_the_documents_sent_are_on_the_line(served, monkeypatch):
    monkeypatch.setattr(turn_code, "process", lambda *a, **k: {"metrics": {"llm_calls": 4, "cost_usd": 0.0123}})
    run(served, model_choice="gpt-6-1-sol", effort="high", document_refs=())
    (line,) = lines(served)
    assert line[4:] == ("answered", "gpt-6-1-sol", "high", 4, 12_300, 0)


def test_reopening_a_saved_answer_is_not_a_turn_and_leaves_no_line(served):
    first = successful(served)
    assert len(lines(served)) == 1
    again = successful(served, chat_id=first["chat_id"])
    assert again["replayed"] and len(lines(served)) == 1


@pytest.mark.parametrize("exc, how", [
    (ConversationRefused("stopped", status=409, code="stopped", retryable=True), "stopped"),
    (ConversationRefused("sign in", status=401), "refused"),
    (ConversationRefused("earlier answer", status=409, code="turn_in_progress"), "refused"),
    (ConversationRefused("allowance", status=402, code="usage_limit"), "refused"),
    (ConversationRefused("withheld", status=409, code="answer_withheld"), "failed"),
    (ConversationRefused("unreadable", status=409, code="history_unavailable"), "failed"),
    (ConversationRefused("down", status=503, code="response_unavailable"), "failed"),
    (ConversationRefused("unsure", status=503, code="attempt_unconfirmed", committed="unconfirmed"), "failed"),
    (DocumentRefused("a document it could not use"), "refused"),
    (ModelPermissionRefused("AI sharing is off"), "refused"),
    (AllowanceUsedUp("used up"), "refused"),
    (RuntimeError("a fault of NM's own"), "failed"),
])
def test_a_turn_that_does_not_finish_says_how_it_ended_and_the_error_goes_on_unchanged(served, monkeypatch, exc, how):
    raising(monkeypatch, exc)
    with pytest.raises(type(exc)) as raised:
        run(served)
    assert raised.value is exc
    assert [line[4] for line in lines(served)] == [how] and lines(served)[0][7] is None


def test_the_calls_a_stopped_turn_made_before_it_stopped_are_on_its_line(served, monkeypatch):
    stopped = ConversationRefused("stopped", status=409, code="stopped", retryable=True)
    stopped.metrics = {"llm_calls": 6, "cost_usd": 0.5}
    raising(monkeypatch, stopped)
    with pytest.raises(ConversationRefused):
        run(served)
    assert lines(served)[0][4:9] == ("stopped", "default", "default", 6, 500_000)


@pytest.mark.parametrize("failing", [TurnEventRefused("storage"), EgressRefused("not admitted"), ValueError("bad line")])
def test_when_the_record_fails_the_answer_is_still_given_and_only_the_kind_of_fault_is_logged(served, caplog, failing):
    class Broken:
        def record(self, account_id, event):
            raise failing

    served.app.turn_events = Broken()
    with caplog.at_level(logging.WARNING, logger="nm.turns"):
        reply = successful(served)
    assert reply["committed"] == "committed"
    assert any(type(failing).__name__ in record.getMessage() for record in caplog.records)
    assert all(OWNER not in record.getMessage() for record in caplog.records)


def test_when_the_record_fails_the_turn_s_own_error_is_not_replaced_by_it(served, monkeypatch):
    class Broken:
        def record(self, account_id, event):
            raise TurnEventRefused("storage")

    served.app.turn_events = Broken()
    original = RuntimeError("a fault of NM's own")
    raising(monkeypatch, original)
    with pytest.raises(RuntimeError) as raised:
        run(served)
    assert raised.value is original
