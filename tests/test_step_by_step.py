"""A matter worked step by step, as a junior works with a senior (plan AN.48, piece 48a; owner decisions D134-D166, 9 Nov 2026).

Sent step by step, a message stops for the advocate's go-ahead after each step - understood, researched, written - and Done finishes
it as one answer; end to end runs the rest without stopping; a message sent without asking for steps runs end to end exactly as
before. Each stop keeps everything finished (the AN.41 record), with the go-ahead and after which step it waits (48a2); each step
claims its own attempt (D150). Offline: scripted models and a synthetic store; the words are invented."""
import pytest

from nm.core_engine import steps, turn
from nm.core_engine.conversation import ConversationRefused, chat_matter_id, shown_of, stored_chat
from nm.shared.turn_attempt_store import FileTurnAttempts
from tests.test_core_answer_sections import Scripted, through_turns
from tests.test_core_turn import FileMatterStore, run

RESEARCH = {"core_research_pick", "core_research_judgment_pick", "core_research_further", "core_calculation"}


@pytest.fixture
def store(tmp_path):
    return FileMatterStore(tmp_path, key="synthetic-turn-fixture")


def held(store):
    return shown_of(store.load(chat_matter_id("owner", stored_chat("owner", None, "t1"))))


def waits(store, model, go, after):
    """One step run; it stops for the advocate after `after`, keeping what it finished."""
    with pytest.raises(ConversationRefused) as refused:
        run(store, model, go=go)
    assert refused.value.code == "waiting" and refused.value.kept and refused.value.retryable
    assert refused.value.status == 409
    record = held(store)
    assert record["stopped"]["code"] == "waiting" and steps.waiting_of(record) == after
    return record


def research_made(model):
    return [name for name, _ in model.calls if name in RESEARCH]


def test_each_step_stops_for_the_advocate_and_done_saves_the_answer_end_to_end_would(store, tmp_path):
    scripted = Scripted()
    model = through_turns(scripted)
    understood = waits(store, model, steps.first(), "understood")
    assert understood["steps"]["understood"] is not None and understood["steps"]["parts"] == {}
    assert not research_made(model), "nothing is researched before the advocate's go-ahead"
    assert not scripted.payloads("core_response_writer")

    researched = waits(store, model, steps.given(understood["go"], "next", written=False), "researched")
    assert set(researched["steps"]["parts"]) == {"D1", "D2"} and researched["steps"]["answered"] is None
    assert research_made(model) and not scripted.payloads("core_response_writer"), "researched, nothing written"

    written = waits(store, model, steps.given(researched["go"], "next", written=False), "written")
    assert len(written["steps"]["answered"]["sections"]) == 2 and written["steps"]["answered"]["cross_check"] is None
    assert len(scripted.payloads("core_response_writer")) == 2
    assert not scripted.payloads("core_response_cross_check") and not scripted.payloads("core_response_overview")

    before = len(research_made(model))
    response = run(store, model, go=steps.given(written["go"], "done", written=True))
    assert response["committed"] == "committed" and held(store) is None
    assert len(scripted.payloads("core_response_writer")) == 2, "the analyses are not written again"
    assert len(scripted.payloads("core_response_cross_check")) == 1 and len(scripted.payloads("core_response_overview")) == 1
    assert len(research_made(model)) == before, "nor researched again"

    # The same message end to end, in a store of its own: the same answer.
    other = FileMatterStore(tmp_path / "end-to-end", key="synthetic-turn-fixture")
    whole = run(other, through_turns(Scripted()))
    assert whole["elements"] == response["elements"]
    mine = turn.saved_rows(store.load(chat_matter_id("owner", response["chat_id"])), "owner")[0]["activities"]
    theirs = turn.saved_rows(other.load(chat_matter_id("owner", whole["chat_id"])), "owner")[0]["activities"]
    assert mine == theirs


def test_end_to_end_at_a_stop_runs_every_remaining_step_without_stopping(store):
    scripted = Scripted()
    model = through_turns(scripted)
    understood = waits(store, model, steps.first(), "understood")
    response = run(store, model, go=steps.given(understood["go"], "end_to_end", written=False))
    assert response["committed"] == "committed" and held(store) is None
    assert len(scripted.payloads("core_response_writer")) == 2 and len(scripted.payloads("core_response_overview")) == 1


def test_done_before_any_analysis_saves_the_matter_as_it_stands_with_no_step_run(store):
    model = through_turns(Scripted())
    understood = waits(store, model, steps.first(), "understood")
    assert steps.given(understood["go"], "done", written=False) is None, "Done before an analysis runs no step"
    matter = store.load(chat_matter_id("owner", understood["request"]["chat_id"]))
    response = turn.done(store, matter, "owner", "t1", session_current=lambda: True)
    assert response["service_status"].startswith(turn.STOPS["done"])
    assert [row["turn_id"] for row in turn.saved_rows(store.load(matter.id), "owner")] == ["t1"] and held(store) is None


def test_a_message_sent_without_steps_runs_end_to_end_and_keeps_no_go_ahead(store):
    seen = {}
    model = through_turns(Scripted())
    first = model.structured

    def structured(prompt, schema, tier, **kwargs):
        seen.setdefault("held", held(store))
        return first(prompt, schema, tier, **kwargs)
    model.structured = structured
    response = run(store, model)
    assert response["committed"] == "committed"
    assert "go" not in seen["held"], "the record of an end-to-end turn is exactly as before 48a"


def test_each_step_claims_an_attempt_of_its_own_and_a_waiting_turn_is_not_released_at_a_restart(store):
    attempts = FileTurnAttempts(store._root / "attempts.sqlite")
    model = through_turns(Scripted())
    with pytest.raises(ConversationRefused):
        run(store, model, go=steps.first(), attempts=attempts)
    understood = held(store)
    with pytest.raises(ConversationRefused):
        run(store, model, go=steps.given(understood["go"], "next", written=False), attempts=attempts)
    import sqlite3
    with sqlite3.connect(store._root / "attempts.sqlite") as db:
        rows = db.execute("select state, code from turn_attempts").fetchall()
    assert sorted(rows) == [("retryable", "waiting"), ("retryable", "waiting")], "one attempt a step (D150), each waiting"
    assert attempts.release_ended("interrupted") == 0, "a waiting turn is never released as interrupted (D153)"


def test_the_stop_says_what_was_done_what_comes_next_and_what_it_offers(store):
    model = through_turns(Scripted())
    understood = waits(store, model, steps.first(), "understood")
    card = steps.card(understood)
    assert card["after"] == "understood" and card["next"] == "research"
    assert [go["choice"] for go in card["gos"]] == ["next", "end_to_end", "done"]
    assert card["done_said"] == steps.DONE_SAID["understood"] and steps.waiting_said(understood) == "Waiting for you: research"


def test_a_go_ahead_is_refused_where_the_turn_does_not_wait_for_it():
    with pytest.raises(ValueError):
        steps.given(steps.first(), "next", written=False)  # not waiting
    waiting = steps.waited(steps.first(), "understood")
    with pytest.raises(ValueError):
        steps.given(waiting, "sideways", written=False)
    assert steps.given(waiting, "next", written=False) == {"mode": "steps", "allowed": ["research"], "n": 2, "waiting": None}
    assert steps.given(waiting, "end_to_end", written=False)["allowed"] == ["research", "write", "finish"]
    assert not steps.valid({**waiting, "allowed": ["dance"]}) and steps.valid(waiting)
