"""BK-36 — kill the connection at four points, and the brief lands once.

WHAT WAS MISSING, AND IT WAS ONE THING
----------------------------------------
The store already refused two writers: a per-matter lock, an exact version
check, and an engine that will not apply the same turn id twice. What the
BROWSER did was clear the textarea before the request and send no turn id.

So the two halves never met:

  * the server could recognise a repeated turn and was never told which turn
    it was, so a retry after a lost response was a NEW turn and put the same
    brief on the file twice;
  * the only copy of what the advocate had written lived in a failed card in
    memory, gone on reload and gone on sign-out.

Both are the same absence -- an identity for the attempt that outlives the
attempt. These are the four moments BK-36 names, driven on the served path.

WHY THE SERVED PATH AND NOT THE ENGINE
----------------------------------------
Because the defect was never in the engine. `engine.run` has refused a
repeated `turn_id` for slices; the browser did not send one. CLAUDE.md §8 in
its plainest form: a guard that is right in the core and absent at the
composition root is not a guard, and every defect the first external review
found lived in that gap.
"""
from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 8)
BRIEF = ("We act for the plaintiff at Hyderabad. Goods were supplied against "
         "invoices on 14 March 2023 and were never paid for.")


def _turn(client, message: str, **extra) -> dict:
    body = {"message": message, "today": TODAY.isoformat(), **extra}
    return client.post("/api/turn", json=body)


def _times_briefed(client, matter_id: str, message: str) -> int:
    """How many times this brief appears in the transcript that was SERVED.

    THE TRANSCRIPT AND NOT THE BOARD. The board is a status view -- six
    fields, no analysis, no chronology -- so counting rows there answers a
    different question and would have answered it `0` for every case. The
    transcript is the only thing that keeps what the advocate wrote, which
    makes it the only place a duplicated brief is visible AS a duplicate.
    """
    r = client.get(f"/api/matters/{matter_id}/transcript")
    assert r.status_code == 200, r.text
    turns = r.json().get("turns", [])
    said = [t for t in turns
            if message.strip()[:60] in (t.get("message") or t.get("brief") or "")]
    return len(said)


# =========================================== 1. after commit, before response ==

def test_a_retry_after_a_lost_response_does_not_write_the_brief_twice(client):
    """THE CASE THIS ROW EXISTS FOR.

    The server commits, the response never arrives, the advocate presses send
    again. Without a turn id that is a second turn and the same brief goes on
    the file twice -- and an advocate reading their own chronology cannot tell
    a duplicate from two genuinely similar events.
    """
    first = _turn(client, BRIEF, turn_id="turn_fixed_for_this_test")
    assert first.status_code == 200, first.text
    body = first.json()
    matter_id = body["matter_id"]
    assert body["committed"] == "committed"
    assert _times_briefed(client, matter_id, BRIEF) == 1

    # THE SAME TURN, ARRIVING AGAIN. This is what the browser now sends: the
    # id was minted before the first attempt and the retry reuses it.
    again = _turn(client, BRIEF, turn_id="turn_fixed_for_this_test",
                  matter_id=matter_id)
    assert again.status_code == 200, again.text
    assert again.json()["committed"] == "replayed", (
        "the server took the retry as a new turn; the brief is on the file "
        "twice and nothing says so")
    assert _times_briefed(client, matter_id, BRIEF) == 1, (
        "the retry recorded the brief a second time")


def test_two_different_briefs_are_two_turns(client):
    """THE POSITIVE CONTROL, and it is not decoration.

    An engine that answered `replayed` to everything would pass the test
    above perfectly while recording nothing at all. This is the direction
    that catches it.
    """
    first = _turn(client, BRIEF, turn_id="turn_one")
    assert first.status_code == 200, first.text
    matter_id = first.json()["matter_id"]

    second = _turn(client, "The defendant wrote on 12 June 2024 admitting the "
                           "amount was outstanding.",
                   turn_id="turn_two", matter_id=matter_id)
    assert second.status_code == 200, second.text
    assert second.json()["committed"] == "committed"
    assert _times_briefed(client, matter_id, "The defendant wrote") == 1, (
        "a genuinely new brief was treated as a replay and recorded nothing")


# ================================================== 2. a file that has moved ==

def test_a_brief_written_on_a_version_this_caller_never_read_is_refused(client):
    """TWO TABS. One loads the matter, the other works it, the first sends.

    The first tab is writing onto a file it has never seen -- its answer will
    be derived from a chronology missing everything the other tab added. The
    refusal names both versions so the caller can re-read rather than guess.
    """
    opened = _turn(client, BRIEF, turn_id="turn_a")
    matter_id = opened.json()["matter_id"]
    stale_version = opened.json()["matter_version"]

    moved = _turn(client, "The goods were delivered on 20 March 2023.",
                  turn_id="turn_b", matter_id=matter_id)
    assert moved.status_code == 200, moved.text
    assert moved.json()["matter_version"] > stale_version

    late = _turn(client, "And the invoices were raised the same week.",
                 turn_id="turn_c", matter_id=matter_id,
                 expected_version=stale_version)
    assert late.status_code == 409, (
        f"a write on a version this caller never read was accepted: "
        f"{late.status_code}")
    detail = late.json()["detail"]
    assert detail["committed"] == "not_committed", (
        "the caller cannot tell whether its brief was saved")
    assert detail["matter_version"] > detail["expected_version"]


def test_a_caller_that_does_not_check_is_not_refused(client):
    """`None` IS `I DID NOT CHECK`, NOT `I CHECKED AND IT MATCHED`.

    Tools and tests legitimately hold no version. Refusing them would make
    the field mandatory by the back door; treating absence as a match would
    be the S1 shape the whole check exists to avoid.
    """
    opened = _turn(client, BRIEF, turn_id="turn_d")
    matter_id = opened.json()["matter_id"]
    _turn(client, "The goods were delivered on 20 March 2023.",
          turn_id="turn_e", matter_id=matter_id)

    late = _turn(client, "And the invoices were raised the same week.",
                 turn_id="turn_f", matter_id=matter_id)
    assert late.status_code == 200, late.text


# ============================================ 3. every failure carries a handle ==

def test_a_refusal_names_the_turn_so_a_retry_can_be_the_same_turn(client):
    """`The turn was refused: HTTP 500` cannot be retried safely.

    The caller does not know whether the brief landed, and has no id to send
    again with -- so its only options are to lose the brief or risk a second
    copy. Every failure this route can raise now carries the id and says
    whether anything was committed.
    """
    opened = _turn(client, BRIEF, turn_id="turn_g")
    matter_id = opened.json()["matter_id"]
    version = opened.json()["matter_version"]
    _turn(client, "The goods were delivered on 20 March 2023.",
          turn_id="turn_h", matter_id=matter_id)

    refused = _turn(client, "late", turn_id="turn_i", matter_id=matter_id,
                    expected_version=version)
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["turn_id"] == "turn_i", (
        "the failure does not name the turn, so a retry cannot be the same one")
    assert detail["committed"] == "not_committed"


# ===================================================== 4. the browser's half ==

def test_the_page_mints_the_turn_id_and_the_retry_reuses_it():
    """THE HALF THAT WAS MISSING, checked on the script itself.

    Read from the text rather than from a browser so it runs every commit;
    `tests/test_the_journey_login_to_logout.py` drives the same behaviour in
    a real page. Both are worth having -- this one fails in seconds and names
    the line.
    """
    import pathlib
    script = (pathlib.Path(__file__).resolve().parents[1]
              / "web" / "app.js").read_text(encoding="utf-8")

    assert "function newTurnId" in script, (
        "the page does not mint a turn id, so a retry after a lost response "
        "is a new turn and the brief lands twice")
    assert "turn_id: entry.turnId" in script, (
        "the turn id is minted and not sent")
    assert "expected_version: state.matterVersion" in script, (
        "the page does not say which version it believes it is writing on")

    # THE COMPOSER IS NOT CLEARED BEFORE THE REQUEST. It was, and a request
    # that failed before commitment took the advocate's only copy with it.
    submit = script.split("$('composer').addEventListener")[1].split("});")[0]
    assert "box.value = ''" not in submit, (
        "the composer is cleared before the brief is known to be saved")
