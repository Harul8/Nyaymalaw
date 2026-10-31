"""The board adds up the land extents the papers record (plan AN.27, P13d slice 3 and P20; invariant I6).

The plan keeps the transfers of land each paper records (slice 2); the board shows, for each parcel, those whose words were found,
seller by seller - each seller's sales added by code and set against a paper's stated whole extent (what it leaves if that seller held
all of it, or how far the sales go beyond it) - and the caveat that a sum is only of what was found. What could not be read, whose words
were not found, or is not a sale, is listed and never added. One sale read on copies of a page is one. The board only reads what was
saved. The papers are synthetic.
"""
import pytest

from nm.core_engine import matter_board
from tests.test_copies_that_read_a_figure_differently import passage
from tests.test_the_board_has_a_timeline import turn
from tests.test_the_board_names_figures_copies_read_differently import paper

pytestmark = pytest.mark.class_a


def kept(number, parcel, extent, *, total="", to="Kiran Rao", frm="Hari Prasad", sort="1985-10-30", date="30-10-1985", anchored=True,
         document="deed.pdf", pages=(1,), kind="sale", source="t1:d1"):
    return {"id": f"X{number}", "date": date, "sort": sort, "kind": kind, "parcel": parcel, "extent": extent, "total": total,
            "from": frm, "to": to, "document": document, "source": source, "pages": list(pages) if anchored else [],
            "words": f"words of {number}", "anchored": anchored}


def extents_of(transfers):
    row = turn([], [])
    row["activities"]["research"]["plan"]["proposal"]["transfers"] = transfers
    return matter_board.board([row])["extents"]


def test_the_sales_of_a_seller_are_added_by_code_and_what_the_stated_whole_leaves_is_named():
    (parcel,) = extents_of([kept(1, "Sy.No.487", "Ac.1.18 guntas", total="Ac.8.24 guntas"),
                            kept(2, "Sy.No.487", "Ac.1.00", to="Mahesh Babu", sort="1986-01-02", date="2 January 1986")])
    (seller,) = parcel["sellers"]
    assert parcel["parcel"] == "Sy.No.487" and seller["names"] == ["Hari Prasad"] and parcel["complete"] is True
    assert seller["added"] == "2 acres 18 guntas (Ac.2.18)"
    assert parcel["totals"][0]["by_seller"] == [{"seller": "Hari Prasad", "leaves": "6 acres 6 guntas (Ac.6.06)", "exceeds": None}]
    assert [t["as"] for t in seller["transfers"]] == ["1 acre 18 guntas (Ac.1.18)", "1 acre (Ac.1.00)"]
    assert "makes the sum wrong" in parcel["caveat"] and "sum" not in parcel


def test_the_sales_of_different_sellers_are_kept_apart_and_a_seller_beyond_the_whole_is_named():
    (parcel,) = extents_of([kept(1, "Sy.No.487", "Ac.8.24", total="Ac.8.24"),
                            kept(2, "Sy.No.487", "Ac.2.20", to="Mahesh Babu", sort="1985-04-10"),
                            kept(3, "Sy.No.487", "Ac.1.00", frm="Syed Alam", to="Anil Kumar", sort="2005-04-02")])
    first, second = parcel["sellers"]
    assert (first["names"], first["added"]) == (["Hari Prasad"], "11 acres 4 guntas (Ac.11.04)")
    assert (second["names"], second["added"]) == (["Syed Alam"], "1 acre (Ac.1.00)")
    assert parcel["totals"][0]["by_seller"] == [
        {"seller": "Hari Prasad", "leaves": None, "exceeds": "2 acres 20 guntas (Ac.2.20)"},
        {"seller": "Syed Alam", "leaves": "7 acres 24 guntas (Ac.7.24)", "exceeds": None}]


def test_what_was_not_found_or_not_read_is_listed_and_never_added():
    (parcel,) = extents_of([kept(1, "Sy.No.487", "Ac.1.18", total="Ac.8.24"), kept(2, "Sy.No.487", "Ac.1.00", anchored=False, to="B"),
                            kept(3, "Sy.No.487", "part of the land", to="C")])
    assert parcel["sellers"][0]["added"] == "1 acre 18 guntas (Ac.1.18)" and parcel["complete"] is False
    assert [(n["id"], n["why"]) for n in parcel["not_read"]] == [("X2", "its words were not found on the page"),
                                                                 ("X3", "no extent in these words")]
    assert parcel["totals"][0]["by_seller"] == [], "no remainder while a transfer is unread"


def test_a_partition_is_listed_under_its_seller_with_why_it_is_not_added():
    (parcel,) = extents_of([kept(1, "Sy.No.487", "Ac.1.18"), kept(2, "Sy.No.487", "Ac.8.24", kind="partition", to="Anil Kumar")])
    (seller,) = parcel["sellers"]
    assert seller["added"] == "1 acre 18 guntas (Ac.1.18)"
    (other,) = seller["not_added"]
    assert (other["kind"], other["why"]) == ("partition", "a partition allots a share; it is not a sale")


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
    (seller,) = parcel["sellers"]
    (only,) = seller["transfers"]
    assert seller["added"] == "6 acres 6 guntas (Ac.6.06)" and only["also_read_as"] == ["Kiran Raao"]
    assert [p["document"] for p in only["papers"]] == ["deed.pdf", "scan.pdf"]
    # Papers that are not copies of one another are two, as before; a copy sent in a later turn counts with the earlier one.
    (parcel,) = matter_board.board([papers_with(sales, paper("deed.pdf", passage()),
                                                paper("scan.pdf", "A different paper entirely, of other words. " * 12))])["extents"]
    assert len(parcel["sellers"][0]["transfers"]) == 2 and parcel["sellers"][0]["added"] == "12 acres 12 guntas (Ac.12.12)"
    first = papers_with([sales[0]], paper("deed.pdf", passage()))
    second = papers_with(sales, paper("scan.pdf", passage()))
    second["turn_id"] = "t2"
    for sale in second["activities"]["research"]["plan"]["proposal"]["transfers"]:
        sale["source"] = "t2:d1" if sale["document"] == "scan.pdf" else "t1:d1"
    (parcel,) = matter_board.board([first, second])["extents"]
    assert len(parcel["sellers"][0]["transfers"]) == 1 and parcel["sellers"][0]["added"] == "6 acres 6 guntas (Ac.6.06)"


def test_a_partition_with_no_extent_is_listed_under_its_seller_and_the_parcel_is_still_complete():
    (parcel,) = extents_of([kept(1, "Sy.No.487", "Ac.1.18", total="Ac.8.24"),
                            kept(2, "Sy.No.487", "equal shares", kind="partition", frm="Anil Kumar", to="his sons", sort="1974-02-09")])
    assert parcel["complete"] is True and parcel["not_read"] == []
    assert parcel["totals"][0]["by_seller"] == [{"seller": "Hari Prasad", "leaves": "7 acres 6 guntas (Ac.7.06)", "exceeds": None}]
    (listed,) = parcel["sellers"][1]["not_added"]
    assert (listed["extent"], listed["as"], listed["kind"]) == ("equal shares", None, "partition")
