"""BK-33 — a matter list an advocate can act on, and four deadline states.

WHAT THE LIST SAID BEFORE THIS
--------------------------------
Every row: `client: adv_demo` -- the advocate's own id, which is the one thing
every row on their own list has in common, so the column that exists to tell
ten matters apart told them apart by nothing. The title was the first 60
characters of the opening brief, cut mid-word, so ten recovery matters were
ten rows beginning *"We act for the plaintiff at Hyderabad. Goods were
suppl"*. `last_touched` was the VERSION NUMBER: a matter written to nine times
sorted above one written to twice yesterday.

THE DEADLINE COLUMN IS THE ONE THAT COULD HURT SOMEBODY
---------------------------------------------------------
The projection refuses to default and carries the real vocabulary --
`not_assessed`, `none_on_this_matter`, and `DeadlineStatus`'s own `future`,
`near`, `passed`, `not_computed` -- and it was right to. The
CALLERS passed no register at all, so every row reported `not_assessed`, and
the browser rendered `next_deadline || 'none recorded'`, which turns the first
two into the same sentence.

    "Nobody has worked out the deadlines on this file"
    "This file has no deadlines"

are opposite facts. An advocate acting on the second while the first is true
has been told the file is clear by a product that never looked, at the top of
the list they scan first thing in the morning. That is defect shape S1 in the
most expensive place it could be.

THE REGISTER WAS ON THE FILE THE WHOLE TIME. `Thread.deadlines` holds what the
last turn derived; nothing read it. The projection's own docstring says a
default of `()` would be "a decision taken on behalf of every call site that
forgets one" -- and every call site forgot.
"""
from __future__ import annotations

from datetime import date

import pytest
from nm.core.turn import _matter_name

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 8)
BRIEF = ("We act for the plaintiff at Hyderabad. Goods were supplied against "
         "invoices on 14 March 2023 and were never paid for.")


# =============================================== the name, and the fallback ==

def test_a_matter_is_named_for_its_parties():
    """`X v Y` is how every cause list an advocate has read names a file."""
    assert _matter_name(BRIEF, {"Ramesh Traders": "client",
                                "Kiran Steels": "adverse"}) == \
        "Ramesh Traders v Kiran Steels"


def test_a_matter_with_no_parties_is_cut_on_a_word():
    """THE FALLBACK, and the defect it replaces is visible in one character.

    `message[:60]` gave "...Goods were suppl". A name an advocate cannot read
    is not a name, and ten of them are ten rows they have to open to tell
    apart.
    """
    name = _matter_name(BRIEF, {})
    assert name.endswith("…"), f"the cut is not marked: {name!r}"
    # THE RULE IS THE END, NOT THE START. A first draft asserted the name did
    # not begin "...Goods were suppl", which "Goods were supplied…" also does
    # -- a check that fails on the fix.
    assert "suppl…" not in name, f"the name ends mid-word: {name!r}"
    # ON A WORD BOUNDARY: no half word before the ellipsis.
    assert name[:-1].rstrip().split()[-1] in BRIEF.split(), (
        f"the name ends mid-word: {name!r}")


def test_a_matter_with_only_one_side_says_which():
    """Half a party set is not nothing, and it is not a pair either."""
    assert _matter_name(BRIEF, {"Ramesh Traders": "client"}) == "Ramesh Traders"
    assert _matter_name(BRIEF, {"Kiran Steels": "adverse"}) == \
        "against Kiran Steels"


# ====================================== the four states, on the served path ==

def _open(client, message=BRIEF, **extra):
    body = {"message": message, "today": TODAY.isoformat(), **extra}
    r = client.post("/api/turn", json=body)
    assert r.status_code == 200, r.text
    return r.json()["matter_id"]


def test_the_list_names_the_client_and_not_the_advocate(client):
    """The column that exists to tell files apart must tell them apart."""
    _open(client, parties={"Ramesh Traders": "client",
                           "Kiran Steels": "adverse"},
          release={"scope": "recovery"},
          capacity={"state": "not_in_doubt", "basis": "explicit fixture assessment"})

    rows = client.get("/api/matters").json()["matters"]
    assert rows, "the list is empty"
    row = rows[0]
    assert row["client"] == "Ramesh Traders", (
        f"the list says the client is {row['client']!r}; the advocate's own "
        f"id is on every row and distinguishes nothing")
    assert row["opponent"] == "Kiran Steels"
    assert row["matter"] == "Ramesh Traders v Kiran Steels"


def test_last_worked_is_a_date_and_not_a_write_count(client):
    """`last_touched` was `m.version`. A counter is not a time."""
    _open(client, parties={"A Co": "client", "B Co": "adverse"},
          release={"scope": "recovery"},
          capacity={"state": "not_in_doubt", "basis": "explicit fixture assessment"})
    row = client.get("/api/matters").json()["matters"][0]

    assert row["last_touched"] == TODAY.isoformat(), (
        f"last worked reads {row['last_touched']!r}, which is not a date")
    # AND THE COUNTER IS NOT ON THIS LIST AT ALL. It was exposed briefly as
    # `version` so this test could assert it still existed; the matter list
    # is what an advocate SCANS, and a write counter is not something they
    # act on -- `test_neither_board_carries_analysis` refused it, correctly.
    # The board carries it, where a caller that needs it can read it.
    assert "version" not in row


def test_not_assessed_and_none_are_not_the_same_row(client):
    """THE ONE THAT COULD HURT SOMEBODY.

    A file whose deadlines nobody computed and a file with no deadlines must
    not render alike. The register is derived on a turn and written to the
    thread, so a matter that has been advised on reports a real state.
    """
    _open(client, parties={"C Co": "client", "D Co": "adverse"},
          release={"scope": "recovery"},
          capacity={"state": "not_in_doubt", "basis": "explicit fixture assessment"})
    row = client.get("/api/matters").json()["matters"][0]

    assert row["next_deadline_status"] != "not_assessed", (
        "the matter has been advised on and its register is on the thread, "
        "and the list still reports that nobody assessed the deadlines")
    # THE REAL VOCABULARY, read off `DeadlineStatus` rather than invented.
    # A first draft asserted `upcoming`, which this product has never used --
    # a test that names states the code does not have is asserting about a
    # product that does not exist.
    assert row["next_deadline_status"] in (
        "future", "near", "passed", "not_computed",
        "none_on_this_matter"), row["next_deadline_status"]


def test_the_board_reads_the_register_too(client):
    """The same defect, one route over. Both projections take a register and
    both were called with `None`."""
    matter_id = _open(client, parties={"E Co": "client", "F Co": "adverse"},
                      release={"scope": "recovery"},
                      capacity={"state": "not_in_doubt", "basis": "explicit fixture assessment"})
    board = client.get(f"/api/matters/{matter_id}").json()
    states = {t["next_deadline_status"] for t in board["threads"]}

    assert states, "the board has no threads at all"
    assert states != {"not_assessed"}, (
        "every thread on an advised matter reports that nobody assessed its "
        "deadlines, while the register is sitting on the thread")


def test_the_browser_renders_the_four_states_apart():
    """THE HALF THAT IS IN THE PAGE, checked on the script.

    The projection can be perfectly right and the screen still say "none
    recorded" for both -- which is what it did. `tests/test_the_journey...`
    drives the rendering in a browser; this fails in seconds and names the
    line.
    """
    import pathlib
    script = (pathlib.Path(__file__).resolve().parents[1]
              / "frontend" / "app.js").read_text(encoding="utf-8")

    assert "function deadlineField" in script, (
        "nothing in the page distinguishes the four deadline states")
    body = script.split("function deadlineField")[1].split("\nasync function")[0]
    for state in ("not_assessed", "none_on_this_matter", "passed"):
        assert state in body, (
            f"the renderer does not handle {state!r}, so it collapses into "
            f"whatever the fallback says")
    assert "not assessed" in body, (
        "the unassessed state is not named to the advocate in words")
