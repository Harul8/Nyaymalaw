"""Plan AN.52 (D282, 17 Nov 2026: "D282 - yes"): Search again is offered, and NM never searches again by itself. Where a dispute's
research holds a search that failed, the stop after research says so in code's words - 51e's sentence, for that dispute - and offers
Search again beside the go-aheads; taking it searches only the questions that failed, the dispute's other searches given back as
saved, and what was written for that dispute on the failed search is written again once. A later go-ahead does not search again.
The step record a restart reads knows the new go-ahead, and a store of the version before is carried over. Offline: scripted models
and search; the words are invented; not browser QA."""
import sqlite3
from concurrent.futures import Future
from typing import get_args

import pytest

from nm.app.api import TurnGo
from nm.core_engine import message_reader, steps as stepwise
from nm.core_engine.retrieval import HybridSearcher
from nm.shared import step_record_store
from nm.shared.step_record_store import _SQL_V2, VERSION, FileStepRecords
from tests.guided import intake
from tests.test_a_message_while_a_matter_waits import CHAT, SENT, held
from tests.test_additions_are_the_advocates_messages import go
from tests.test_core_answer_sections import Scripted, scripted_answers

AWAY = "Synthetic: the ranking machine was away"


def failing(monkeypatch, served):
    """Every search is counted by its query IDs; the searches of the questions named in fail[0] fail while it is set."""
    asked, fail, first = [], [set()], HybridSearcher.search_many

    def search_many(self, searches, **kwargs):
        asked.extend(query["query_id"] for search in searches for query in search[0])
        futures = first(self, searches, **kwargs)
        out = []
        for search, future in zip(searches, futures, strict=True):
            if any(query["query_id"].split(":q")[0] in fail[0] for query in search[0]):
                broken = Future()
                broken.set_exception(RuntimeError(AWAY))  # the real search still runs, and counts itself done once
                out.append(broken)
            else:
                out.append(future)
        return out
    monkeypatch.setattr(HybridSearcher, "search_many", search_many)
    return asked, fail


def card(served):
    return served.client.get(f"/api/chats/{CHAT}").json()["pending"]["stopped"]["waiting"]


def offered(served):
    return [{key: option[key] for key in ("choice", "disputes", "said")} for option in card(served)["gos"]]


def test_a_failed_search_is_offered_again_never_made_again_by_itself_and_made_again_alone(served, monkeypatch):
    scripted = Scripted()
    scripted_answers(served, scripted)
    asked, fail = failing(monkeypatch, served)
    assert served.client.post("/api/turn", json=SENT).json()["detail"]["code"] == "waiting"
    intake(served.client, CHAT)  # AN.62-AN.64: a new matter is taken through guided intake first
    work = held(served)["steps"]["understood"]["plan"]["work"]
    lost = next(item["id"] for item in work if item["dispute"]["id"] == "D1")
    fail[0] = {lost}
    assert go(served, "research").json()["detail"]["code"] == "waiting"
    before = held(served)["steps"]["parts"]
    assert set(before["D1"]["failures"]) == {lost} and not before["D2"]["failures"]
    # The stop says what could not be searched, in code's words, and offers Search again for that dispute only, after the go-aheads.
    said = card(served)["unsearched"]
    assert said == [f"For 1 question of Dispute 1 the held law could not be searched, and nothing was taken for it. {AWAY}.",
                    stepwise.AGAIN_SAID]
    assert offered(served)[-1] == {"choice": "search_again", "disputes": ["D1"], "said": "Search again: Dispute 1"}
    assert [option["choice"] for option in offered(served)].count("search_again") == 1

    # A go-ahead does not search again by itself: the analysis is written on the research as it stands.
    fail[0] = set()
    asked.clear()
    assert go(served, "write", ["D1"]).json()["detail"]["code"] == "waiting"
    assert not asked and set(held(served)["steps"]["parts"]["D1"]["failures"]) == {lost}
    written = len(scripted.payloads("core_response_writer", "D1"))
    assert written and offered(served)[-1]["choice"] == "search_again"

    # Search again: only the question that failed is searched; the dispute's analysis is written again once; the other is kept.
    assert go(served, "search_again", ["D1"]).json()["detail"]["code"] == "waiting"
    assert asked and {query.split(":q")[0] for query in asked} == {lost}
    after = held(served)
    assert not after["steps"]["parts"]["D1"]["failures"] and lost in after["steps"]["parts"]["D1"]["searches"]
    assert {key: value for key, value in after["steps"]["parts"]["D1"]["searches"].items() if key != lost} == {
        key: value for key, value in before["D1"]["searches"].items()}
    assert after["steps"]["parts"]["D2"] == before["D2"]
    assert len(scripted.payloads("core_response_writer", "D1")) > written
    assert stepwise.waiting_of(after) == "written" and "search_again" not in [option["choice"] for option in offered(served)]
    assert card(served)["unsearched"] == []


def test_search_again_is_refused_where_no_search_failed_and_names_one_dispute(served, monkeypatch):
    scripted_answers(served, Scripted())
    asked, fail = failing(monkeypatch, served)
    assert served.client.post("/api/turn", json=SENT).json()["detail"]["code"] == "waiting"
    intake(served.client, CHAT)  # AN.62-AN.64: a new matter is taken through guided intake first
    assert go(served, "search_again", ["D1"]).json()["detail"]["code"] == "not_offered", "nothing researched yet"
    assert go(served, "research").json()["detail"]["code"] == "waiting"
    assert go(served, "search_again", ["D1"]).json()["detail"]["code"] == "not_offered", "no search failed"
    assert "search_again" not in [option["choice"] for option in offered(served)]


def test_an_answer_written_as_a_whole_is_searched_again_as_a_whole(served, monkeypatch):
    scripted_answers(served, Scripted())
    served.model.disputes = 1
    asked, fail = failing(monkeypatch, served)
    assert served.client.post("/api/turn", json=SENT).json()["detail"]["code"] == "waiting"
    intake(served.client, CHAT)  # AN.62-AN.64: a new matter is taken through guided intake first
    fail[0] = {item["id"] for item in held(served)["steps"]["understood"]["plan"]["work"]}
    assert go(served, "research").json()["detail"]["code"] == "waiting"
    assert offered(served)[-1] == {"choice": "search_again", "disputes": None, "said": "Search again"}
    assert card(served)["unsearched"][0].startswith("For ") and " of " not in card(served)["unsearched"][0].split(" the held")[0]
    fail[0] = set()
    assert go(served, "search_again", ["D1"]).json()["detail"]["code"] == "not_offered", "the whole answer names no dispute"
    assert go(served, "search_again").json()["detail"]["code"] == "waiting"
    assert stepwise.waiting_of(held(served)) == "researched" and card(served)["unsearched"] == []


def test_every_list_of_go_aheads_knows_search_again():
    # The guided stops' own moves (AN.62-AN.64) go by their own route and are never a step's record; the reader also reads a
    # batch of disputes as its step (D309), and a specific request as work (61b), which no button gives.
    taken = set(stepwise.GOS) - set(stepwise.MOVES)
    assert "search_again" in taken and "draft" in taken and stepwise.WORK not in taken
    assert taken == set(step_record_store.CHOICES) == set(get_args(TurnGo.model_fields["choice"].annotation))
    assert set(message_reader.CHOICES) == set(stepwise.GOS) | set(message_reader.BATCH_CHOICES) | {stepwise.WORK}


def test_a_version_two_step_store_is_carried_over_with_its_records_as_they_were(tmp_path):
    path = tmp_path / "step-records.sqlite"
    with sqlite3.connect(path) as db:
        db.execute(_SQL_V2)
        db.execute("PRAGMA user_version=2")
        db.execute("INSERT INTO steps VALUES (?,?,?,?,?,?,?,?,?)",
                   ("a@example.test", "t1", "c1", "go", "write", '["D1"]', "f" * 64, 0, "2027-03-01T09:00:00+00:00"))
    records = FileStepRecords(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == VERSION == 4
    (kept,) = records.left()
    assert kept["choice"] == "write" and kept["taken_at"] == "2027-03-01T09:00:00+00:00" and kept["disputes"] == ["D1"]
    records.taken("a@example.test", "t2", route="go", chat_id="c1", choice="search_again", disputes=["D1"], session="f" * 64)
    assert {each["turn_id"]: each["choice"] for each in records.left()} == {"t1": "write", "t2": "search_again"}
    with pytest.raises(ValueError):
        records.taken("a@example.test", "t3", route="go", choice="sideways")
