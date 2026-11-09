"""A matter worked step by step, dispute by dispute, as a junior works with a senior (plan AN.48, pieces 48a-48b; owner decisions
D134-D166, 9 Nov 2026).

Sent step by step, a message stops for the advocate's go-ahead after each step - understood, researched, written - and Done finishes
it as one answer; end to end runs the rest without stopping; a message sent without asking for steps runs end to end exactly as
before. Research and the analyses run for the disputes the advocate names; the others wait (48b). Each stop keeps everything
finished (the AN.41 record), with the go-ahead and after which step it waits (48a2); each step claims its own attempt (D150).
Offline: scripted models and a synthetic store; the words are invented."""
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


def go(record, choice, disputes=None):
    return steps.given(record["go"], choice, held=record, disputes=disputes)


def research_made(model):
    return [name for name, _ in model.calls if name in RESEARCH]


def picked(model):
    """The disputes whose law was chosen, by the pick calls made for them."""
    return {payload.get("dispute", {}).get("id") or payload.get("dispute_id") for name, payload in model.calls
            if name == "core_research_pick"}


def test_each_step_stops_for_the_advocate_and_done_saves_the_answer_end_to_end_would(store, tmp_path):
    scripted = Scripted()
    model = through_turns(scripted)
    understood = waits(store, model, steps.first(), "understood")
    assert understood["steps"]["understood"] is not None and understood["steps"]["parts"] == {}
    assert not research_made(model), "nothing is researched before the advocate's go-ahead"
    assert not scripted.payloads("core_response_writer")

    researched = waits(store, model, go(understood, "next"), "researched")
    assert set(researched["steps"]["parts"]) == {"D1", "D2"} and researched["steps"]["answered"] is None
    assert research_made(model) and not scripted.payloads("core_response_writer"), "researched, nothing written"

    written = waits(store, model, go(researched, "next"), "written")
    assert len(written["steps"]["answered"]["sections"]) == 2 and written["steps"]["answered"]["cross_check"] is None
    assert len(scripted.payloads("core_response_writer")) == 2
    assert not scripted.payloads("core_response_cross_check") and not scripted.payloads("core_response_overview")

    before = len(research_made(model))
    response = run(store, model, go=go(written, "done"))
    assert response["committed"] == "committed" and held(store) is None
    assert response.get("service_status") is None, "every analysis written: nothing to say above the answer"
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


def test_one_dispute_is_researched_and_written_while_the_other_waits_then_the_other(store):
    """48b (D144, D163): research and the analysis run only for the dispute named; the other waits, offered at each stop."""
    scripted = Scripted()
    model = through_turns(scripted)
    understood = waits(store, model, steps.first(), "understood")
    offered = [(g["choice"], g["disputes"]) for g in steps.card(understood)["gos"]]
    assert offered == [("research", None), ("research", ["D1"]), ("research", ["D2"]), ("end_to_end", None), ("done", None)]

    first = waits(store, model, go(understood, "research", ["D1"]), "researched")
    assert set(first["steps"]["parts"]) == {"D1"}, "only the dispute named is researched"
    gos = [(g["choice"], g["disputes"]) for g in steps.card(first)["gos"]]
    assert ("research", ["D2"]) in gos and ("write", ["D1"]) in gos and ("write", ["D2"]) not in gos

    written = waits(store, model, go(first, "write", ["D1"]), "written")
    assert [s["dispute_id"] for s in written["steps"]["answered"]["sections"]] == ["D1"]
    assert len(scripted.payloads("core_response_writer", "D1")) == 1 and not scripted.payloads("core_response_writer", "D2")
    assert not scripted.payloads("core_response_overview"), "the overview waits for the advocate to finish"

    second = waits(store, model, go(written, "research", ["D2"]), "researched")
    assert set(second["steps"]["parts"]) == {"D1", "D2"}
    both = waits(store, model, go(second, "write", ["D2"]), "written")
    assert sorted(s["dispute_id"] for s in both["steps"]["answered"]["sections"]) == ["D1", "D2"]
    assert len(scripted.payloads("core_response_writer", "D1")) == 1, "the first analysis is not written again"
    assert [g["said"] for g in steps.card(both)["gos"]] == ["Done: check the analyses against each other and save"]

    response = run(store, model, go=go(both, "done"))
    assert response["committed"] == "committed" and response.get("service_status") is None
    assert len(scripted.payloads("core_response_cross_check")) == 1


def test_done_with_one_analysis_of_two_saves_it_and_says_the_other_was_not_asked_for(store):
    model = through_turns(Scripted())
    understood = waits(store, model, steps.first(), "understood")
    first = waits(store, model, go(understood, "research", ["D1"]), "researched")
    written = waits(store, model, go(first, "write", ["D1"]), "written")
    response = run(store, model, go=go(written, "done"))
    assert response["committed"] == "committed" and held(store) is None
    assert response["service_status"] == turn.PARTLY_SAID.format(written=1, of=2)
    activity = turn.saved_rows(store.load(chat_matter_id("owner", response["chat_id"])), "owner")[0]["activities"]
    assert [((s["fallback"] or {}).get("reason")) for s in activity["sections"]] == [None, "interrupted"]


def test_a_dispute_is_offered_only_for_the_step_it_can_take(store):
    model = through_turns(Scripted())
    understood = waits(store, model, steps.first(), "understood")
    with pytest.raises(ValueError):
        go(understood, "write", ["D1"])  # not researched yet
    with pytest.raises(ValueError):
        go(understood, "research", ["D9"])  # no such dispute
    with pytest.raises(ValueError):
        go(understood, "end_to_end", ["D1"])  # end to end is for the whole matter
    first = waits(store, model, go(understood, "research", ["D1"]), "researched")
    with pytest.raises(ValueError):
        go(first, "research", ["D1"])  # already researched


def test_end_to_end_at_a_stop_runs_every_remaining_step_without_stopping(store):
    scripted = Scripted()
    model = through_turns(scripted)
    understood = waits(store, model, steps.first(), "understood")
    first = waits(store, model, go(understood, "research", ["D1"]), "researched")
    response = run(store, model, go=go(first, "end_to_end"))
    assert response["committed"] == "committed" and held(store) is None and response.get("service_status") is None
    assert len(scripted.payloads("core_response_writer")) == 2 and len(scripted.payloads("core_response_overview")) == 1


def test_done_before_any_analysis_saves_the_matter_as_it_stands_with_no_step_run(store):
    model = through_turns(Scripted())
    understood = waits(store, model, steps.first(), "understood")
    assert go(understood, "done") is None, "Done before an analysis runs no step"
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
        run(store, model, go=go(understood, "next"), attempts=attempts)
    import sqlite3
    with sqlite3.connect(store._root / "attempts.sqlite") as db:
        rows = db.execute("select state, code from turn_attempts").fetchall()
    assert sorted(rows) == [("retryable", "waiting"), ("retryable", "waiting")], "one attempt a step (D150), each waiting"
    assert attempts.release_ended("interrupted") == 0, "a waiting turn is never released as interrupted (D153)"


def test_the_stop_says_what_was_done_what_comes_next_and_what_it_offers(store):
    model = through_turns(Scripted())
    understood = waits(store, model, steps.first(), "understood")
    card = steps.card(understood)
    assert card["after"] == "understood" and card["next_said"] == steps.NEXT_SAID["research"]
    assert [d["id"] for d in card["disputes"]] == ["D1", "D2"] and not any(d["researched"] for d in card["disputes"])
    assert card["done_said"].startswith("NM has read your papers") and steps.waiting_said(understood) == "Waiting for you: research"


def test_a_go_ahead_is_refused_where_the_turn_does_not_wait_for_it():
    record = {"steps": {}, "go": steps.first()}
    with pytest.raises(ValueError):
        steps.given(steps.first(), "next", held=record)  # not waiting
    waiting = steps.waited(steps.first(), "understood")
    with pytest.raises(ValueError):
        steps.given(waiting, "sideways", held={"steps": {}, "go": waiting})
    assert not steps.valid({**waiting, "allowed": ["dance"]}) and steps.valid(waiting)
    assert steps.valid({**waiting, "disputes": ["D1"]}) and not steps.valid({**waiting, "disputes": []})
