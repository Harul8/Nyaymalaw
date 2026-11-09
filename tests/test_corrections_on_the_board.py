"""A correction sent while a matter waits (plan AN.48, piece 48g; owner decisions D146, D148, D161): the message reader names the item
of what NM read that it changes - a fact of the understanding or an event of the papers' timeline - and its corrected value; code
checks the item is one NM read, keeps the correction as the advocate's message with it (48h), says what it marked, and the board shows
the corrected value on that item, marked as the advocate's. A correction of a date a worked-out time limit runs from is critical by
code: the limits are worked out again and the analyses written are checked at once. Offline: scripted models; the words are
invented."""
from nm.core_engine import calculation, steps
from tests.test_a_message_while_a_matter_waits import CHAT, Reader, held, judged, reading, say, waiting_matter
from tests.test_additions_are_the_advocates_messages import reviews_reading, written_one
from tests.test_core_answer_sections import Scripted
from tests.test_core_served import served  # noqa: F401 - pytest fixture

FACT = "The advocate seeks the applicable law."
VALUE = "The advocate seeks the law on a lease."
WORDS = "It is about a lease, not a loan."


def correction(item="F1", value=VALUE, **out):
    return judged(kind="correction", disputes=["D1"], corrects="what the advocate seeks", item=item, value=value,
                  said="Taken as a correction of what NM read.", **out)


def board(served):
    return served.client.get(f"/api/chats/{CHAT}/board").json()


def test_a_correction_names_its_item_code_checks_it_keeps_it_and_the_board_marks_it(served):
    waiting_matter(served)
    assert all("corrected" not in fact for fact in board(served)["facts"])
    reader = Reader(correction())
    reading(served, reader)
    reply = say(served, WORDS)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "heard"
    assert reply.json()["detail"]["heard"]["said"] == (
        f'Taken as a correction of what NM read. On the board, "{FACT}" is marked as corrected by you: {VALUE}'), "code says it"
    assert reader.asked[0]["what_we_read"]["facts"] == [{"id": "F1", "fact": FACT}], "the reader names it from what NM read"
    added, = held(served)["added"]
    assert added["text"] == WORDS and added["corrects"] == {"item": "F1", "value": VALUE}, "kept as the advocate's message, with it"
    fact, = [fact for fact in board(served)["facts"] if fact["id"] == "F1"]
    assert fact["corrected"] == {"value": VALUE} and fact["fact"] == FACT, "the paper's own reading stays beside the mark"


def test_a_correction_of_an_item_nm_did_not_read_is_kept_without_a_mark_and_said(served):
    waiting_matter(served)
    reading(served, Reader(correction(item="F9")))
    reply = say(served, WORDS)
    assert "NM could not tell which item of what it read this corrects" in reply.json()["detail"]["heard"]["said"]
    added, = held(served)["added"]
    assert added["text"] == WORDS and "corrects" not in added
    assert all("corrected" not in fact for fact in board(served)["facts"])


def test_the_board_marks_the_event_a_correction_changes_the_latest_correction_standing():
    from nm.app.api import _corrected
    shown = {"state": "ready", "facts": [{"id": "F1", "fact": FACT}],
             "timeline": {"state": "ready", "events": [{"id": "E1", "date": "1 May 2009", "what": "The sale deed"}, {"id": "E2"}]}}
    saved = [{"added": [{"text": "a", "documents": [], "at": "t", "corrects": {"item": "E1", "value": "1 May 2019"}}]}]
    waiting = {"added": [{"text": "b", "documents": [], "at": "t", "corrects": {"item": "E1", "value": "2 May 2019"}}]}
    marked = _corrected(shown, saved, waiting)
    assert marked["timeline"]["events"][0] == {"id": "E1", "date": "1 May 2009", "what": "The sale deed",
                                               "corrected": {"value": "2 May 2019"}}, "the paper's reading stays beside it"
    assert "corrected" not in marked["timeline"]["events"][1] and marked["facts"] == shown["facts"]
    assert _corrected(shown, [], None) is shown, "nothing corrected: the board as it was"


def test_code_knows_which_dates_a_worked_out_time_limit_runs_from():
    chronology = [{"id": "E1", "sort": "2024-03-10"}, {"id": "E2", "sort": "2024-05-01"}, {"id": "E3", "sort": ""}]
    record = {"understood": {"plan": {"proposal": {"chronology": chronology}}},
              "limits": {"calculations": [{"start": {"date": "2024-03-10"}}]}}
    assert steps.limit_rests_on(record, "E1")
    assert not any(steps.limit_rests_on(record, item) for item in ("E2", "E3", "F1"))
    assert not steps.limit_rests_on({**record, "limits": None}, "E1"), "no time limit worked out"


def counted(monkeypatch):
    calls = []
    work_out = calculation.work_out

    def counting(*args, **kwargs):
        calls.append(1)
        return work_out(*args, **kwargs)
    monkeypatch.setattr(calculation, "work_out", counting)
    return calls


def test_a_correction_a_time_limit_rests_on_is_critical_and_the_limits_are_worked_out_again(served, monkeypatch):
    scripted = Scripted()
    written_one(served, scripted)
    monkeypatch.setattr(steps, "limit_rests_on", lambda record, item: item == "F1")
    worked = counted(monkeypatch)
    reading(served, Reader(correction(critical=False)))
    reply = say(served, WORDS)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", "critical by code: checked at once"
    assert worked, "the time limits are worked out again"
    assert reviews_reading(scripted, WORDS), "the analysis written is reviewed again with the correction"
    record = held(served)
    assert record["added"][0]["corrects"] == {"item": "F1", "value": VALUE} and "recheck" not in record["go"]


def test_a_correction_no_time_limit_rests_on_keeps_the_limits_worked_out(served, monkeypatch):
    scripted = Scripted()
    written_one(served, scripted)
    worked = counted(monkeypatch)
    reading(served, Reader(correction(critical=False)))
    reply = say(served, WORDS)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "heard"
    assert held(served)["go"]["recheck"] is True, "not critical: checked at the next run that writes, or at Done (48h)"
    reading(served, Reader(correction(critical=True)))
    reply = say(served, "And the lease is of the ground floor only.")
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "waiting", "critical: checked at once"
    assert reviews_reading(scripted, WORDS) and not worked, "the time limits worked out before are kept"
