"""The board adds up the figures the papers record (plan AN.27, P13d slice 3 and P20; AN.28, D7; AN.29, D9; invariant I6).

The plan keeps the transactions each paper records (slice 2); the board shows, for each subject, those whose words were found, giver by
giver - each giver's figures added by code, each kind of quantity with its own, and set against a paper's stated whole (what it leaves
if all of it was that giver's, or how far the giver's figures go beyond it) - and the caveat that a sum is only of what was found. What
could not be read, whose words were not found, or is not added, is listed and never added. One transaction read on copies of a page is
one, and one dated after its giver's recorded death carries a remark. The board only reads what was saved. The papers are synthetic.
"""
import pytest

from nm.core_engine import matter_board
from tests.test_copies_that_read_a_figure_differently import passage
from tests.test_the_board_has_a_timeline import turn
from tests.test_the_board_names_figures_copies_read_differently import paper
from tests.test_the_plan_records_the_transfers import reading

pytestmark = pytest.mark.class_a

SHARE = {"dimension": "share", "parts": []}


def kept(number, subject, figure, *, whole="", to="Kiran Rao", frm="Hari Prasad", sort="1985-10-30", date="30-10-1985", anchored=True,
         document="deed.pdf", pages=(1,), kind="sale", source="t1:d1", quantity=None, giver_died="", giver_died_sort=""):
    return {"id": f"X{number}", "date": date, "sort": sort, "kind": kind, "subject": subject, "figure": figure,
            "quantity": quantity or reading(figure), "whole": whole, "whole_quantity": reading(whole), "from": frm, "to": to,
            "instrument": "", "giver_died": giver_died, "giver_died_sort": giver_died_sort, "document": document, "source": source,
            "pages": list(pages) if anchored else [], "words": f"{figure} out of {whole}" if whole else figure, "anchored": anchored}


def figures_of(transactions):
    row = turn([], [])
    row["activities"]["research"]["plan"]["proposal"]["transfers"] = transactions
    return matter_board.board([row])["figures"]


def test_the_figures_of_a_giver_are_added_by_code_and_what_the_stated_whole_leaves_is_named():
    (subject,) = figures_of([kept(1, "Contract 487", "118 kg", whole="824 kg"),
                             kept(2, "Contract 487", "125 kg", to="Mahesh Babu", sort="1986-01-02", date="2 January 1986")])
    (giver,) = subject["givers"]
    assert subject["subject"] == "Contract 487" and giver["names"] == ["Hari Prasad"] and subject["complete"] is True
    assert giver["added"] == "243 kilograms"
    assert subject["totals"][0]["by_giver"] == [{"giver": "Hari Prasad", "leaves": "581 kilograms", "exceeds": None}]
    assert [t["as"] for t in giver["counted"]] == ["118 kilograms", "125 kilograms"]
    assert "makes the sum wrong" in subject["caveat"] and "sum" not in subject


def test_the_figures_of_different_givers_are_kept_apart_and_a_giver_beyond_the_whole_is_named():
    (subject,) = figures_of([kept(1, "Contract 487", "824 kg", whole="824 kg"),
                             kept(2, "Contract 487", "220 kg", to="Mahesh Babu", sort="1985-04-10"),
                             kept(3, "Contract 487", "100 kg", frm="Syed Alam", to="Anil Kumar", sort="2005-04-02")])
    first, second = subject["givers"]
    assert (first["names"], first["added"]) == (["Hari Prasad"], "1,044 kilograms")
    assert (second["names"], second["added"]) == (["Syed Alam"], "100 kilograms")
    assert subject["totals"][0]["by_giver"] == [
        {"giver": "Hari Prasad", "leaves": None, "exceeds": "220 kilograms"},
        {"giver": "Syed Alam", "leaves": "724 kilograms", "exceeds": None}]


def test_money_and_quantities_of_one_subject_are_added_apart():
    (subject,) = figures_of([kept(1, "Contract 487", "118 kg", whole="824 kg"),
                             kept(2, "Contract 487", "Rs.1,260", kind="payment", sort="1985-11-01", date="1-11-1985")])
    (giver,) = subject["givers"]
    assert giver["added"] == "Rs 1,260; 118 kilograms"
    assert [(t["dimension"], t["as"]) for t in subject["totals"]] == [("mass", "824 kilograms")]


def test_what_was_not_found_or_not_read_is_listed_and_never_added():
    (subject,) = figures_of([kept(1, "Contract 487", "118 kg", whole="824 kg"), kept(2, "Contract 487", "100 kg", anchored=False, to="B"),
                             kept(3, "Contract 487", "part of the stock", to="C")])
    assert subject["givers"][0]["added"] == "118 kilograms" and subject["complete"] is False
    assert [(n["id"], n["why"]) for n in subject["not_read"]] == [("X2", "its words were not found on the page"),
                                                                  ("X3", "no quantity was read from it")]
    assert subject["totals"][0]["by_giver"] == [], "no remainder while a transaction is unread"


def test_a_partition_is_listed_under_its_giver_with_why_it_is_not_added():
    (subject,) = figures_of([kept(1, "Contract 487", "118 kg"), kept(2, "Contract 487", "824 kg", kind="partition", to="Anil Kumar")])
    (giver,) = subject["givers"]
    assert giver["added"] == "118 kilograms"
    (other,) = giver["listed"]
    assert (other["kind"], other["why"]) == ("partition", "a partition allots a share; it is not a sale")


def test_subjects_are_kept_apart_and_a_plan_with_no_transactions_or_before_them_has_none():
    found = figures_of([kept(1, "Contract 487", "118 kg"), kept(2, "Contract 487/A", "29 kg", to="B")])
    assert [s["subject"] for s in found] == ["Contract 487", "Contract 487/A"]
    assert figures_of([]) == []
    row = turn([], [])
    assert "transfers" not in row["activities"]["research"]["plan"]["proposal"] and matter_board.board([row])["figures"] == []
    assert "extents" not in matter_board.board([row])


def papers_with(transactions, *documents):
    row = turn(list(documents), [])
    row["activities"]["research"]["plan"]["proposal"]["transfers"] = transactions
    return row


def test_one_sale_read_on_two_copies_of_a_page_is_added_once_and_both_readings_of_the_receiver_are_shown():
    sales = [kept(1, "Contract 487", "6.06 tonnes", to="Kiran Rao", document="deed.pdf", source="t1:d1"),
             kept(2, "Contract 487", "6.06 tonnes", to="Kiran Raao", document="scan.pdf", source="t1:d2")]
    (subject,) = matter_board.board([papers_with(sales, paper("deed.pdf", passage()), paper("scan.pdf", passage()))])["figures"]
    (giver,) = subject["givers"]
    (only,) = giver["counted"]
    assert giver["added"] == "6.06 tonnes" and only["also_read_as"] == ["Kiran Raao"]
    assert [p["document"] for p in only["papers"]] == ["deed.pdf", "scan.pdf"]
    # Papers that are not copies of one another are two, as before; a copy sent in a later turn counts with the earlier one.
    (subject,) = matter_board.board([papers_with(sales, paper("deed.pdf", passage()),
                                                 paper("scan.pdf", "A different paper entirely, of other words. " * 12))])["figures"]
    assert len(subject["givers"][0]["counted"]) == 2 and subject["givers"][0]["added"] == "12.12 tonnes"
    first = papers_with([sales[0]], paper("deed.pdf", passage()))
    second = papers_with(sales, paper("scan.pdf", passage()))
    second["turn_id"] = "t2"
    for sale in second["activities"]["research"]["plan"]["proposal"]["transfers"]:
        sale["source"] = "t2:d1" if sale["document"] == "scan.pdf" else "t1:d1"
    (subject,) = matter_board.board([first, second])["figures"]
    assert len(subject["givers"][0]["counted"]) == 1 and subject["givers"][0]["added"] == "6.06 tonnes"


def test_a_partition_with_no_figure_is_listed_under_its_giver_and_the_subject_is_still_complete():
    (subject,) = figures_of([kept(1, "Contract 487", "125 kg", whole="824 kg"),
                             kept(2, "Contract 487", "equal shares", kind="partition", frm="Anil Kumar", to="his sons",
                                  sort="1974-02-09", quantity=SHARE)])
    assert subject["complete"] is True and subject["not_read"] == []
    assert subject["totals"][0]["by_giver"] == [{"giver": "Hari Prasad", "leaves": "699 kilograms", "exceeds": None}]
    (listed,) = subject["givers"][1]["listed"]
    assert (listed["figure"], listed["as"], listed["kind"]) == ("equal shares", None, "partition")


def test_a_transaction_dated_after_its_givers_recorded_death_carries_the_remark_to_the_board():
    after = kept(1, "Contract 487", "118 kg", sort="2003-06-05", date="5-6-2003", giver_died="4-4-2003", giver_died_sort="2003-04-04")
    before = kept(2, "Contract 487", "125 kg", to="Other", sort="2003-02-01", date="1-2-2003", giver_died="4-4-2003",
                  giver_died_sort="2003-04-04")
    (subject,) = figures_of([before, after])
    first, second = subject["givers"][0]["counted"]
    assert "remark" not in first and second["remark"] == "dated after the death of the giver that the papers record (4-4-2003)"
    assert subject["givers"][0]["added"] == "243 kilograms", "added as the papers state it; the remark is the advocate's to weigh"
