"""C7 — an inventoried item does not vanish because a read forgot it.

THE MEASURED DEFECT
---------------------
Driven, 6 September 2026, because a live read cannot be made to forget on
demand:

    turn 1  2 items  ['the original agreement', 'the invoices']
    turn 2  2 items
    turn 3  1 item   the read did not mention the agreement
    turn 4  0 items
    turn 5  2 items  it mentioned them again

Nothing happened to the evidence. This is the theory, the issues and the proof
positions again, on the last value of that shape the turn still threw away.

AND `Preservation` IS NOT A DERIVATION AT ALL
-----------------------------------------------
It records that a step was TAKEN, with an owner and a date. That is history —
not something re-derivable from an account that will never mention it again.
Losing it means `G-PRESERVE` blocks a step and asks a question the advocate
has already answered, which is the one thing the question machinery is built
not to do.

That is what makes this more than tidiness. An item flickering is confusing;
a preservation instruction flickering is the counterexample C7 exists for
arriving through the repair — *the item is inventoried, its holder is
recorded, and nothing was ever asked of anyone.*

NOTHING COMPARES TWO DESCRIPTIONS
-----------------------------------
"The original agreement" and "the original sale agreement" are one document
and share two words; two photocopies of different deeds read almost
identically. A similarity test gets both wrong, and the wrong direction —
merging two real items — loses one silently. The READ names the id, which is
the mechanism `restates` already established on the issue read.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core import evidence_item as inventory
from nm.core.evidence_item import (
    EvidenceItem,
    Form,
    Holder,
    Preservation,
)
from nm.domain.quotable import Quotable

pytestmark = pytest.mark.class_a

ACCOUNT = ("The original agreement is with the opponent's brother. "
           "We hold the invoices and a photocopy of the deed.")
Q = Quotable(turn="where do we stand?", file=ACCOUNT)


def _item(what="the original agreement", ident="evi_a", **kw):
    return EvidenceItem(what=what, id=ident, **kw)


def _row(what, quoted, already="", holder="client", form="original"):
    return {"what": what, "holder": holder, "form": form,
            "quoted": quoted, "already": already}


# ================================ the merge =================================

def test_an_item_survives_a_read_that_does_not_mention_it():
    """THE DEFECT, AS A RULE. Not "items are stored" — storing them and
    replacing the list from each read would pass that and change nothing."""
    standing = (_item(), _item("the invoices", "evi_b"))
    assert len(inventory.merge(standing, ())) == 2


def test_a_new_item_is_added():
    """THE BOUND. A merge that only ever kept the standing list would freeze
    the inventory on turn one — the opposite failure and just as bad."""
    merged = inventory.merge((_item(),), (_item("the site engineer", "evi_c"),))
    assert {i.what for i in merged} == {"the original agreement",
                                        "the site engineer"}


def test_a_preservation_step_is_never_lost_to_a_fresh_read():
    """WHAT MAKES THIS MORE THAN TIDINESS.

    `Preservation` records that a step was TAKEN, with an owner and a date.
    A fresh read knows nothing about it, and taking the fresh item wholesale
    would drop it — so G-PRESERVE fires again and the advocate is asked who is
    preserving a document they already answered for.
    """
    standing = (_item(preservation=Preservation(
        owner="the instructing solicitor", due=date(2026, 10, 1),
        issued_at=date(2026, 9, 2))),)
    merged = inventory.merge(standing, (_item(),))

    assert merged[0].preservation is not None, (
        "a fresh read that knew nothing about the preservation step erased "
        "it, so G-PRESERVE will ask again")
    assert merged[0].preservation.issued
    assert not inventory.unpreserved(merged), (
        "the item reads as unpreserved after a merge, which is the question "
        "the advocate already answered coming back")


def test_a_fresh_read_may_sharpen_a_facet_and_may_not_blank_one():
    """`UNKNOWN` and `NOT_ASSESSED` are what a read that did not look returns.
    Taking them over an answer somebody established is the flicker one field
    down."""
    standing = (_item(holder=Holder.OPPONENT, form=Form.ORIGINAL),)
    blanked = inventory.merge(standing, (_item(),))
    assert blanked[0].holder is Holder.OPPONENT
    assert blanked[0].form is Form.ORIGINAL

    sharpened = inventory.merge(
        (_item(),), (_item(holder=Holder.OPPONENT),))
    assert sharpened[0].holder is Holder.OPPONENT


def test_nothing_merges_two_items_by_comparing_their_descriptions():
    """CLAUDE.md §5, on the axis where it is most tempting here. Two items
    with no shared id are two items however alike they read."""
    a = _item("the original agreement", "evi_a")
    b = _item("the original sale agreement", "evi_b")
    assert len(inventory.merge((a,), (b,))) == 2


# =============================== the read ===================================

def test_the_read_is_shown_what_is_already_on_the_file():
    """Without this the read cannot name anything — it does not know what is
    there, so every rewording is a new item."""
    standing = (_item(),)
    prompt = inventory.build_inventory_prompt(Q, standing)
    assert "evi_a" in prompt.user
    assert "the original agreement" in prompt.user
    assert "already" in prompt.user

    first = inventory.build_inventory_prompt(Q)
    assert "ITEMS ALREADY ON THIS FILE" not in first.user, (
        "a file with no inventory was told to name one")


def test_a_named_id_is_carried_so_the_merge_has_a_key():
    standing = (_item(),)
    read = inventory.read_inventory(
        {"items": [_row("the agreement, original",
                        "The original agreement is with the opponent",
                        already="evi_a")]}, Q, standing)
    assert [i.id for i in read.items] == ["evi_a"]
    assert len(inventory.merge(standing, read.items)) == 1


def test_an_id_the_file_does_not_hold_is_dropped():
    """An `already` pointing at nothing would silently become a new item
    anyway; one pointing at another thread's item would merge two threads'
    evidence. Both are the silent direction."""
    standing = (_item(),)
    read = inventory.read_inventory(
        {"items": [_row("a different document", "We hold the invoices",
                        already="evi_elsewhere")]}, Q, standing)
    assert read.items and read.items[0].id != "evi_elsewhere"
    assert len(inventory.merge(standing, read.items)) == 2


def test_every_item_gets_an_id_even_without_a_named_one():
    """A merge keyed on the id cannot work on items that have none, and an
    item with no id would look new on every turn for ever."""
    read = inventory.read_inventory(
        {"items": [_row("the invoices", "We hold the invoices")]}, Q)
    assert read.items and read.items[0].id


# =============================== the store ==================================

def test_items_come_back_from_the_store_typed():
    """`Thread.evidence` is untyped, so the store returns plain dicts. Left
    implicit, the next turn would merge dicts against items, match nothing,
    and every item would look new every turn — this defect arriving through
    its own repair, which is what happened to the issues."""
    rows = [{
        "what": "the original agreement", "id": "evi_a",
        "holder": "opponent", "form": "original",
        "preservation": {"owner": "the instructing solicitor",
                         "due": "2026-10-01", "issued_at": "2026-09-02"},
    }]
    live = inventory.from_stored(rows)
    assert len(live) == 1
    assert isinstance(live[0], EvidenceItem)
    assert live[0].id == "evi_a"
    assert live[0].holder is Holder.OPPONENT
    assert live[0].preservation is not None
    assert live[0].preservation.owner == "the instructing solicitor"
    assert live[0].preservation.issued


def test_a_stored_row_that_cannot_be_rebuilt_is_dropped_and_the_rest_kept():
    live = inventory.from_stored([
        {"what": "the invoices", "id": "evi_b"},
        {"what": ""},
        {"what": "bad date", "preservation": {"owner": "x", "due": "nope"}},
        "not an item",
    ])
    assert [i.what for i in live] == ["the invoices"]


def test_an_unissued_preservation_survives_the_round_trip():
    """WRITTEN AND NEVER ISSUED is a distinct gap, and the document is gone
    either way. A round trip that lost `issued_at` would report it as issued
    and the second gap would never be raised."""
    live = inventory.from_stored([{
        "what": "the deed", "id": "evi_c",
        "preservation": {"owner": "counsel", "due": "2026-10-01"}}])
    assert live[0].preservation is not None
    assert not live[0].preservation.issued
    assert inventory.undelivered(live), (
        "a written-but-unissued instruction round-tripped as issued")


# ============================== on the wire =================================

def test_the_turn_persists_the_merged_inventory():
    """A merge that never reaches the store is a merge against an empty list
    every turn, which passes every test above and changes nothing."""
    import inspect

    from nm.core.turn import TurnEngine

    body = inspect.getsource(TurnEngine._inventory)
    assert 'concluded["evidence"]' in body, (
        "`_inventory` derived items and put none on `concluded`, so the "
        "write-back at the end of the turn has nothing to persist")
    assert "inventory.merge(standing" in body

    # AND EVERY SWEEP READS THE MERGED LIST. Running them on this turn's read
    # alone would ask only about the items the read happened to mention, so
    # an item that vanished would stop being asked about -- the document
    # going quietly missing that C7's counterexample is about.
    for sweep in ("unpreserved", "undelivered", "unasked"):
        assert f"inventory.{sweep}(live)" in body, (
            f"`{sweep}` runs on the fresh read rather than the merged list")


def test_what_is_carried_is_not_recited():
    """E-093, WHICH THIS FIX BROKE BEFORE IT FIXED IT.

    Persisting the inventory made every turn recite one more item than the
    last -- 13, 13, 14, 15, 16 elements across five turns on ONE thread. That
    is E-093's counterexample in as many words: *length growing with turn
    count, recitation bloat returning.* The failure is agreeable, because
    restating context reads as thorough, and nothing is wrong in any single
    turn -- which is why it needs a check across them.

    PERSISTING AND RECITING ARE DIFFERENT THINGS, and the turn was doing the
    second because it had never had the first. The rule is written here
    because the next persisted list will meet the same wall.
    """
    import inspect

    from nm.core.turn import TurnEngine

    body = inspect.getsource(TurnEngine._inventory)
    assert "for item in live:" in body, "the merged list is what is walked"
    assert "carried += 1" in body, (
        "every item is rendered on every turn, so the answer grows with the "
        "conversation -- which E-093 exists to refuse")
    assert "unchanged" in body and "not repeated here" in body, (
        "the carried items are silent, so an advocate cannot tell a short "
        "list from a short answer -- the third state going missing where it "
        "is easiest to miss")


def test_the_thread_carries_the_field():
    from nm.domain.matter import Thread

    assert Thread.create(label="t").evidence == ()
