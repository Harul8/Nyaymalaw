"""The board adds up the land extents the papers record (plan AN.27, P13d, slice 3; invariant I6).

The plan keeps the transfers of land each paper records (slice 2); the board now shows, for each parcel, those whose words were found,
added up by code, with what a paper's stated whole extent leaves and the caveat that a sum is only of what was found. What could not
be read, or whose words were not found, is listed and never added. The board only reads what was saved. The papers are synthetic.
"""
import pytest

from nm.core_engine import matter_board
from tests.test_copies_that_read_a_figure_differently import passage
from tests.test_the_board_has_a_timeline import turn
from tests.test_the_board_names_figures_copies_read_differently import paper

pytestmark = pytest.mark.class_a


def kept(number, parcel, extent, *, total="", to="Jelli Krishna", sort="1985-10-30", date="30-10-1985", anchored=True,
         document="deed.pdf", pages=(1,), kind="sale", source="t1:d1"):
    return {"id": f"X{number}", "date": date, "sort": sort, "kind": kind, "parcel": parcel, "extent": extent, "total": total,
            "from": "the vendor", "to": to, "document": document, "source": source, "pages": list(pages) if anchored else [],
            "words": f"words of {number}", "anchored": anchored}


def extents_of(transfers):
    row = turn([], [])
    row["activities"]["research"]["plan"]["proposal"]["transfers"] = transfers
    return matter_board.board([row])["extents"]


def test_the_transfers_of_a_parcel_are_added_by_code_and_what_the_stated_whole_leaves_is_named():
    (parcel,) = extents_of([kept(1, "Sy.No.487", "Ac.1.18 guntas", total="Ac.8.24 guntas"),
                            kept(2, "Sy.No.487", "Ac.1.00", to="Jelli Jairam", sort="1986-01-02", date="2 January 1986")])
    assert parcel["parcel"] == "Sy.No.487" and parcel["sum"] == "2 acres 18 guntas (Ac.2.18)" and parcel["complete"] is True
    assert parcel["totals"][0]["leaves"] == "6 acres 6 guntas (Ac.6.06)"
    assert [t["in_guntas"] for t in parcel["transfers"]] == ["1 acre 18 guntas (Ac.1.18)", "1 acre (Ac.1.00)"]
    assert "makes the sum wrong" in parcel["caveat"]


def test_what_was_not_found_or_not_read_is_listed_and_never_added():
    (parcel,) = extents_of([kept(1, "Sy.No.487", "Ac.1.18", total="Ac.8.24"), kept(2, "Sy.No.487", "Ac.1.00", anchored=False, to="B"),
                            kept(3, "Sy.No.487", "part of the land", to="C")])
    assert parcel["sum"] == "1 acre 18 guntas (Ac.1.18)" and parcel["complete"] is False
    assert [(n["id"], n["why"]) for n in parcel["not_read"]] == [("X2", "its words were not found on the page"),
                                                                 ("X3", "no extent in these words")]
    assert parcel["totals"][0]["leaves"] is None, "no remainder while a transfer is unread"


def test_parcels_are_kept_apart_and_a_plan_with_no_transfers_or_before_them_has_none():
    found = extents_of([kept(1, "Sy.No.487", "Ac.1.18"), kept(2, "Sy.No.487/A", "Ac.0.29", to="B")])
    assert [p["parcel"] for p in found] == ["Sy.No.487", "Sy.No.487/A"]
    assert extents_of([]) == []
    row = turn([], [])
    assert "transfers" not in row["activities"]["research"]["plan"]["proposal"] and matter_board.board([row])["extents"] == []


def papers_with(transfers, *documents):
    row = turn(list(documents), [])
    row["activities"]["research"]["plan"]["proposal"]["transfers"] = transfers
    return row


def test_one_sale_read_on_two_copies_of_a_page_is_added_once_and_both_readings_of_the_buyer_are_shown():
    sales = [kept(1, "Sy.No.487", "Ac.6.06", to="Kiran Rao", document="deed.pdf", source="t1:d1"),
             kept(2, "Sy.No.487", "Ac.6.06", to="Kiran Raao", document="scan.pdf", source="t1:d2")]
    (parcel,) = matter_board.board([papers_with(sales, paper("deed.pdf", passage()), paper("scan.pdf", passage()))])["extents"]
    (only,) = parcel["transfers"]
    assert parcel["sum"] == "6 acres 6 guntas (Ac.6.06)" and only["also_read_as"] == ["Kiran Raao"]
    assert [p["document"] for p in only["papers"]] == ["deed.pdf", "scan.pdf"]
    # Papers that are not copies of one another are two, as before; a copy sent in a later turn counts with the earlier one.
    (parcel,) = matter_board.board([papers_with(sales, paper("deed.pdf", passage()),
                                                paper("scan.pdf", "A different paper entirely, of other words. " * 12))])["extents"]
    assert len(parcel["transfers"]) == 2 and parcel["sum"] == "12 acres 12 guntas (Ac.12.12)"
    first = papers_with([sales[0]], paper("deed.pdf", passage()))
    second = papers_with(sales, paper("scan.pdf", passage()))
    second["turn_id"] = "t2"
    for sale in second["activities"]["research"]["plan"]["proposal"]["transfers"]:
        sale["source"] = "t2:d1" if sale["document"] == "scan.pdf" else "t1:d1"
    (parcel,) = matter_board.board([first, second])["extents"]
    assert len(parcel["transfers"]) == 1 and parcel["sum"] == "6 acres 6 guntas (Ac.6.06)"
