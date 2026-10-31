"""Land extents are added up by code (plan AN.27, P13d; invariant I6).

No step added extents: a model was left to say whether a claim could be matched, and a total less two smaller sales that comes to the
claimed figure was an inference nobody checked. Extents are read as a paper writes them (Ac.1.18 guntas, 6 acres 6 guntas, 29 guntas,
150 sq. yards) into guntas (40 to an acre), added seller by seller with the same transfer counted once where papers report it (P20),
compared with a stated whole extent, and rendered back as the papers write them - and a sum says it is only of what was found. The
papers here are synthetic.
"""
import json
from fractions import Fraction

import pytest

from nm.core_engine import extents
from nm.core_engine.extents import ledger, parcel_key, parse, render, shown

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("words,guntas,how", [
    ("Ac.1.18 guntas", 58, "acres.guntas"), ("Ac.0.29 guntas", 29, "acres.guntas"), ("Ac. 8-24", 344, "acres.guntas"),
    ("an extent of Ac.8.24 guntas in Sy.No.487", 344, "acres.guntas"),
    ("6 acres 6 guntas", 246, "acres and guntas"), ("6 acres and 6 guntas", 246, "acres and guntas"),
    ("6.06 acres", 246, "acres and guntas written 6.06"), ("6.50 acres", 260, "decimal acres"), ("6.5 acres", 260, "decimal acres"),
    ("6 acres", 240, "acres"), ("29 guntas", 29, "guntas"), ("1 gunta", 1, "guntas"),
])
def test_an_extent_is_read_as_the_paper_writes_it(words, guntas, how):
    assert parse(words) == (Fraction(guntas), how)


def test_square_yards_are_read_in_guntas():
    assert parse("242 sq. yards") == (Fraction(2), "square yards") and parse("121 square yards")[0] == 1


@pytest.mark.parametrize("words,why", [
    ("Ac.1.45", "the guntas are 40 or more"), ("no figure here", "no extent in these words"), ("", "no extent in these words"),
    ("Ac.1.18 guntas (each Ac.0.29 guntas)", "more than one extent in these words"),
    ("Ac.1.18 and Ac.2.20", "more than one extent in these words")])
def test_words_that_are_not_one_extent_are_not_read_and_say_why(words, why):
    assert parse(words) == (None, why)


@pytest.mark.parametrize("guntas,shown_as", [
    (58, "1 acre 18 guntas (Ac.1.18)"), (246, "6 acres 6 guntas (Ac.6.06)"), (29, "29 guntas (Ac.0.29)"), (0, "0 guntas (Ac.0.00)"),
    (40, "1 acre (Ac.1.00)"), (-29, "-29 guntas (Ac.0.29)"), (81, "2 acres 1 gunta (Ac.2.01)"),
    (Fraction(3, 2), "1.50 guntas")])
def test_guntas_are_rendered_as_the_papers_write_them(guntas, shown_as):
    assert render(guntas) == shown_as


@pytest.mark.parametrize("parcel,key", [("Sy.No.487", "487"), ("Survey No. 487", "487"), ("Sy.No.487/A/1A", "487/a/1a"),
                                        ("Sy. No. 487 / A", "487/a"), ("487", "487"), ("S.No.12", "12"), ("", "")])
def test_a_parcel_is_one_key_however_it_is_written(parcel, key):
    assert parcel_key(parcel) == key


def transfer(number, extent, *, parcel="Sy.No.487", to="Kiran Rao", frm="Hari Prasad", date="30-10-1985", sort="1985-10-30", total="",
             document="deed.pdf", pages=(1,), kind="sale"):
    return {"id": f"X{number}", "parcel": parcel, "extent": extent, "total": total, "from": frm, "to": to, "date": date, "sort": sort,
            "kind": kind, "document": document, "pages": list(pages)}


def test_the_sales_of_a_seller_are_added_and_what_they_leave_of_the_stated_extent_is_named():
    (parcel,) = ledger([transfer(1, "Ac.1.18 guntas", total="Ac.8.24 guntas"),
                        transfer(2, "Ac.1.00", to="Mahesh Babu", sort="1986-01-02")])
    assert parcel["parcel"] == "Sy.No.487" and parcel["complete"]
    (seller,) = parcel["sellers"]
    assert seller["names"] == ["Hari Prasad"] and seller["added"].get("area") == 98
    (total,) = parcel["totals"]
    assert total["value"] == 344 and total["by_seller"] == [{"seller": "Hari Prasad", "leaves": 246, "exceeds": None}]
    assert render(total["by_seller"][0]["leaves"]) == "6 acres 6 guntas (Ac.6.06)"


def test_the_sales_of_different_sellers_are_never_added_together():
    (parcel,) = ledger([transfer(1, "Ac.8.24", frm="Hari Prasad", total="Ac.8.24"),
                        transfer(2, "Ac.2.20", frm="Syed Alam", to="Mahesh Babu", sort="1985-04-10", date="10-4-1985")])
    first, second = parcel["sellers"]
    assert (first["names"], first["added"].get("area")) == (["Hari Prasad"], 344) and (second["names"], second["added"].get("area")) == (["Syed Alam"], 100)
    assert [(b["seller"], b["leaves"], b["exceeds"]) for b in parcel["totals"][0]["by_seller"]] == [
        ("Hari Prasad", 0, None), ("Syed Alam", 244, None)]
    assert "sum" not in parcel and "transfers" not in parcel, "no figure for the parcel as a whole: rival chains of title are not one holding"


def test_a_seller_whose_sales_go_beyond_the_stated_whole_is_named_by_how_far_whether_or_not_every_transfer_was_read():
    sales = [transfer(1, "Ac.8.24", to="First Buyer", total="Ac.8.24"), transfer(2, "Ac.2.20", to="Mahesh Babu", sort="1985-04-10"),
             transfer(3, "Ac.1.18", to="Kiran Rao", sort="1985-10-30"), transfer(4, "Ac.4.16", to="Anil Kumar", sort="2004-06-28")]
    (parcel,) = ledger(sales)
    (seller,) = parcel["sellers"]
    assert seller["added"].get("area") == 678
    (against,) = parcel["totals"][0]["by_seller"]
    assert (against["seller"], against["leaves"], against["exceeds"]) == ("Hari Prasad", None, 334)
    assert render(against["exceeds"]) == "8 acres 14 guntas (Ac.8.14)"
    (parcel,) = ledger([*sales, transfer(5, "part of the land", to="Priya Devi")])
    assert not parcel["complete"] and parcel["totals"][0]["by_seller"][0]["exceeds"] == 334, "more can only be more"


def test_the_same_transfer_reported_by_several_papers_is_counted_once_with_every_paper():
    (parcel,) = ledger([transfer(1, "Ac.1.18 guntas", document="deed.pdf"),
                        transfer(2, "Ac.1.18", parcel="Survey No. 487", to="KIRAN  RAO.", document="order.pdf", pages=(4,))])
    (seller,) = parcel["sellers"]
    (only,) = seller["transfers"]
    assert seller["added"].get("area") == 58 and only["ids"] == ["X1", "X2"]
    assert [p["document"] for p in only["papers"]] == ["deed.pdf", "order.pdf"]


def test_two_transfers_of_one_extent_on_one_day_to_different_buyers_are_two():
    (parcel,) = ledger([transfer(1, "Ac.0.29", to="Kiran Rao"), transfer(2, "Ac.0.29", to="Mahesh Babu")])
    (seller,) = parcel["sellers"]
    assert len(seller["transfers"]) == 2 and seller["added"].get("area") == 58


def test_the_same_extent_to_the_same_buyer_on_two_days_is_two_transfers():
    (parcel,) = ledger([transfer(1, "Ac.0.29", sort="1985-10-30"), transfer(2, "Ac.0.29", sort="1986-10-30")])
    (seller,) = parcel["sellers"]
    assert len(seller["transfers"]) == 2 and seller["added"].get("area") == 58


def test_an_undated_transfer_is_told_apart_by_its_buyer_and_its_extent():
    (parcel,) = ledger([transfer(1, "Ac.0.29", sort="", date="undated"), transfer(2, "Ac.0.30", sort="", date="undated")])
    assert len(parcel["sellers"][0]["transfers"]) == 2


def test_an_extent_that_cannot_be_read_is_never_added_and_the_parcel_says_it_is_not_complete():
    (parcel,) = ledger([transfer(1, "Ac.1.18 guntas", total="Ac.8.24"), transfer(2, "part of the land", to="Mahesh Babu"),
                        transfer(3, "Ac.1.45", to="Other")])
    assert parcel["sellers"][0]["added"].get("area") == 58 and not parcel["complete"]
    assert [(u["id"], u["why"]) for u in parcel["unread"]] == [("X2", "no extent in these words"), ("X3", "the guntas are 40 or more")]
    assert parcel["totals"][0]["by_seller"] == [], "no remainder is named while a transfer is unread"


def test_a_transfer_whose_words_were_not_found_on_its_page_is_never_added_nor_its_stated_extent_used():
    (parcel,) = ledger([transfer(1, "Ac.1.18", total="Ac.8.24"), {**transfer(2, "Ac.1.00", to="Other", total="Ac.9.00"), "anchored": False},
                        {**transfer(3, "Ac.0.10", to="Third"), "anchored": True}])
    assert parcel["sellers"][0]["added"].get("area") == 68 and not parcel["complete"]
    assert [(u["id"], u["why"]) for u in parcel["unread"]] == [("X2", "its words were not found on the page")]
    assert [s["text"] for s in parcel["totals"]] == ["Ac.8.24"] and parcel["totals"][0]["by_seller"] == []


def test_a_stated_extent_that_cannot_be_read_names_no_remainder_and_sales_beyond_the_whole_are_named_as_beyond_it():
    (parcel,) = ledger([transfer(1, "Ac.1.18", total="the whole survey number")])
    assert parcel["totals"][0]["value"] is None and parcel["totals"][0]["by_seller"] == []
    (parcel,) = ledger([transfer(1, "Ac.2.00", total="Ac.1.00")])
    (against,) = parcel["totals"][0]["by_seller"]
    assert (against["leaves"], against["exceeds"]) == (None, 40) and render(against["exceeds"]) == "1 acre (Ac.1.00)"


def test_different_stated_extents_are_each_named_and_parcels_that_differ_are_kept_apart_in_the_papers_order():
    found = ledger([transfer(1, "Ac.1.18", total="Ac.8.24"), transfer(2, "Ac.0.29", parcel="Sy.No.487/A", total="Ac.2.00"),
                    transfer(3, "Ac.1.00", total="Ac.9.00"), transfer(4, "Ac.0.10", parcel="")])
    assert [p["parcel"] for p in found] == ["Sy.No.487", "Sy.No.487/A"] and len(found[0]["totals"]) == 2
    assert found[1]["sellers"][0]["added"].get("area") == 29 and found[0]["sellers"][0]["added"].get("area") == 98


def test_a_partition_a_decree_and_anything_else_is_listed_under_the_seller_and_never_added():
    (parcel,) = ledger([transfer(1, "Ac.1.00", to="Mahesh Babu", sort="1990-01-01"), transfer(2, "Ac.8.24", kind="partition"),
                        transfer(3, "Ac.2.00", kind="decree", to="Anil Kumar", sort="1995-01-01"),
                        transfer(4, "Ac.0.10", kind="other", to="S. Prakash", sort="1996-01-01"),
                        transfer(5, "Ac.0.20", kind="gift", to="Priya Devi", sort="1991-01-01"),
                        transfer(6, "Ac.0.30", kind="settlement", to="Ravi Teja", sort="1992-01-01")])
    (seller,) = parcel["sellers"]
    assert [t["kind"] for t in seller["transfers"]] == ["sale", "gift", "settlement"] and seller["added"].get("area") == 40 + 20 + 30
    assert [t["kind"] for t in seller["not_added"]] == ["partition", "decree", "other"]
    (only,) = ledger([transfer(1, "Ac.8.24", kind="partition")])[0]["sellers"]
    assert only["added"].get("area") is None and only["transfers"] == [] and len(only["not_added"]) == 1


def test_a_transfer_whose_seller_is_not_named_is_listed_and_added_to_no_one():
    (parcel,) = ledger([transfer(1, "Ac.1.00", frm="", to="Mahesh Babu"),
                        transfer(2, "Ac.2.00", frm="Hari Prasad", to="Kiran Rao", sort="1986-01-02", total="Ac.8.24")])
    unnamed, named = parcel["sellers"]
    assert (unnamed["names"], unnamed["added"].get("area"), len(unnamed["transfers"])) == ([], None, 1) and named["added"].get("area") == 80
    assert [b["seller"] for b in parcel["totals"][0]["by_seller"]] == ["Hari Prasad"]


def test_two_spellings_of_a_sellers_name_are_one_seller_only_where_the_papers_make_them_so():
    copied = {frozenset({("deed.pdf", 1), ("scan.pdf", 1)})}
    sales = [transfer(1, "Ac.2.20", frm="Syed Alam", to="Kiran Rao", document="deed.pdf"),
             transfer(2, "Ac.2.20", frm="Syed Alaam", to="Kiran Raao", document="scan.pdf"),
             transfer(3, "Ac.1.18", frm="Syed Alaam", to="Mahesh Babu", sort="1986-01-02", document="order.pdf", pages=(2,))]
    (parcel,) = ledger(sales, copied)
    (seller,) = parcel["sellers"]
    assert seller["names"] == ["Syed Alam", "Syed Alaam"] and seller["added"].get("area") == 158 and len(seller["transfers"]) == 2
    (parcel,) = ledger(sales)
    first, second = parcel["sellers"]
    assert (first["names"], first["added"].get("area")) == (["Syed Alam"], 100) and (second["names"], second["added"].get("area")) == (["Syed Alaam"], 158), \
        "alike is not the same: two spellings nothing links are two sellers"


def test_the_ledger_in_words_is_plain_data_and_says_what_a_sum_is():
    out = shown([transfer(1, "Ac.1.18 guntas", total="Ac.8.24 guntas"), transfer(2, "Ac.1.00", to="Mahesh Babu", sort="1986-01-02"),
                 transfer(3, "Ac.8.24", kind="partition", to="Anil Kumar", sort="1974-02-09")])
    json.dumps(out)
    (parcel,) = out
    (seller,) = parcel["sellers"]
    assert seller["added"] == "2 acres 18 guntas (Ac.2.18)" and parcel["complete"] is True and seller["names"] == ["Hari Prasad"]
    assert parcel["totals"][0]["by_seller"] == [{"seller": "Hari Prasad", "leaves": "6 acres 6 guntas (Ac.6.06)", "exceeds": None}]
    assert parcel["totals"][0]["as"] == "8 acres 24 guntas (Ac.8.24)" and "sum" not in parcel
    (kept,) = seller["not_added"]
    assert kept["kind"] == "partition" and kept["why"] == "a partition allots a share; it is not a sale"
    assert parcel["caveat"] == extents.CAVEAT and "makes the sum wrong" in parcel["caveat"]
    # P20: what a sum is, said once for every ledger - an addition of accounts as stated, giver by giver, not what anyone holds (AN.28,
    # D7: of any transaction).
    assert "whoever states them, giver by giver" in extents.CAVEAT and "added to that giver's alone" in extents.CAVEAT
    assert "rival, overlapping or the same thing described twice" in extents.CAVEAT
    assert "not what anyone holds, owes or has paid" in extents.CAVEAT and "written two ways" in extents.CAVEAT
    assert "areas with areas and sums of money with sums of money, never a share, a rate or a period" in extents.CAVEAT
    assert seller["transfers"][0]["as"] == "1 acre 18 guntas (Ac.1.18)" and seller["transfers"][0]["read_as"] == "acres.guntas"
    assert shown([transfer(1, "nothing")])[0]["sellers"] == []
    (unnamed,) = shown([transfer(1, "Ac.1.00", frm="")])[0]["sellers"]
    assert (unnamed["names"], unnamed["added"], len(unnamed["transfers"])) == ([], None, 1), "added to no one, but listed"


# One transaction is counted once by where it is read (plan AN.27, P20 (b)): the near-copy papers of the reviewed bundle each reported the
# same sales, and a buyer's name read two ways was counted as two buyers.
def on_copies(*pairs):
    return {frozenset(pair) for pair in pairs}


COPIED = on_copies((("deed.pdf", 1), ("scan.pdf", 1)))


def test_one_sale_read_on_two_copies_of_a_page_is_one_whatever_the_buyers_name_was_read_as():
    both = [transfer(1, "Ac.6.06", to="Anil Kumar", document="deed.pdf"),
            transfer(2, "Ac.6.06", to="Anil Kumaar", document="scan.pdf")]
    assert ledger(both)[0]["sellers"][0]["added"].get("area") == 2 * 246, "without the pages' copies a name read two ways is two buyers (the caveat says so)"
    (parcel,) = ledger(both, COPIED)
    (seller,) = parcel["sellers"]
    (only,) = seller["transfers"]
    assert seller["added"].get("area") == 246 and only["ids"] == ["X1", "X2"] and only["to"] == "Anil Kumar"
    assert only["names"] == ["Anil Kumar", "Anil Kumaar"]
    assert [p["document"] for p in only["papers"]] == ["deed.pdf", "scan.pdf"]
    (parcel,) = shown(both, COPIED)
    assert parcel["sellers"][0]["added"] == "6 acres 6 guntas (Ac.6.06)"
    assert parcel["sellers"][0]["transfers"][0]["also_read_as"] == ["Anil Kumaar"]
    assert "also_read_as" not in shown([transfer(1, "Ac.6.06")], COPIED)[0]["sellers"][0]["transfers"][0]


def test_papers_that_are_not_copies_of_one_another_are_told_apart_by_the_buyer_as_before():
    both = [transfer(1, "Ac.6.06", to="Anil Kumar", document="deed.pdf"),
            transfer(2, "Ac.6.06", to="Anil Kumaar", document="order.pdf")]
    assert len(ledger(both, COPIED)[0]["sellers"][0]["transfers"]) == 2
    assert len(ledger(both, on_copies((("deed.pdf", 1), ("order.pdf", 2))))[0]["sellers"][0]["transfers"]) == 2, "copies of another page"


def test_copies_of_a_page_do_not_make_different_transactions_one():
    for other in (transfer(2, "Ac.6.00", to="Anil Kumaar", document="scan.pdf"),
                  transfer(2, "Ac.6.06", to="Anil Kumaar", document="scan.pdf", kind="gift"),
                  transfer(2, "Ac.6.06", to="Anil Kumaar", document="scan.pdf", sort="1986-10-30", date="30-10-1986")):
        first = transfer(1, "Ac.6.06", to="Anil Kumar", document="deed.pdf")
        assert len(ledger([first, other], COPIED)[0]["sellers"][0]["transfers"]) == 2


def test_two_sales_of_one_day_on_a_page_and_its_copy_are_two_not_one_and_not_four():
    both_sales = [transfer(1, "Ac.0.29", to="Kiran Rao", document="deed.pdf"), transfer(2, "Ac.0.29", to="Mahesh Babu", document="deed.pdf"),
                  transfer(3, "Ac.0.29", to="Kiran Raao", document="scan.pdf"), transfer(4, "Ac.0.29", to="Mahesh Babu", document="scan.pdf")]
    (parcel,) = ledger(both_sales, COPIED)
    (seller,) = parcel["sellers"]
    assert len(seller["transfers"]) == 2 and seller["added"].get("area") == 58
    assert sorted(len(t["ids"]) for t in seller["transfers"]) == [2, 2]
    # Where the copy was read for only one of them, the other stays and the one copy joins one of the two.
    (parcel,) = ledger(both_sales[:3], COPIED)
    assert len(parcel["sellers"][0]["transfers"]) == 2 and parcel["sellers"][0]["added"].get("area") == 58


def test_a_third_paper_that_copies_a_page_of_the_second_joins_the_same_transaction():
    copied = on_copies((("deed.pdf", 1), ("scan.pdf", 1)), (("scan.pdf", 1), ("late.pdf", 4)))
    (parcel,) = ledger([transfer(1, "Ac.6.06", to="S. Prakash", document="deed.pdf"), transfer(2, "Ac.6.06", to="S. Praksh", document="scan.pdf"),
                        transfer(3, "Ac.6.06", to="S Prakaash", document="late.pdf", pages=(4,))], copied)
    (seller,) = parcel["sellers"]
    (only,) = seller["transfers"]
    assert only["ids"] == ["X1", "X2", "X3"] and only["names"] == ["S. Prakash", "S. Praksh", "S Prakaash"] and seller["added"].get("area") == 246


def test_a_copy_that_reports_two_of_a_kind_for_the_one_its_original_reports_is_one_and_one_more():
    (parcel,) = ledger([transfer(1, "Ac.0.29", to="Kiran Rao", document="deed.pdf"),
                        transfer(2, "Ac.0.29", to="Kiran Raao", document="scan.pdf"),
                        transfer(3, "Ac.0.29", to="Mahesh Babu", document="scan.pdf")], COPIED)
    assert len(parcel["sellers"][0]["transfers"]) == 2 and parcel["sellers"][0]["added"].get("area") == 58


def test_a_paper_that_is_no_copy_but_reads_the_buyer_as_the_copy_did_adds_nothing_to_the_sale_either():
    copied = on_copies((("deed.pdf", 1), ("scan.pdf", 1)))
    (parcel,) = ledger([transfer(1, "Ac.6.06", to="S. Prakash", document="deed.pdf"), transfer(2, "Ac.6.06", to="S. Praksh", document="scan.pdf"),
                        transfer(3, "Ac.6.06", to="S. Praksh", document="order.pdf", pages=(2,))], copied)
    (seller,) = parcel["sellers"]
    (only,) = seller["transfers"]
    assert only["ids"] == ["X1", "X2", "X3"] and seller["added"].get("area") == 246


def test_a_paper_never_counts_two_of_its_own_transfers_as_one_because_a_copy_reports_one():
    (parcel,) = ledger([transfer(1, "Ac.0.29", to="Kiran Rao", document="deed.pdf"), transfer(2, "Ac.0.29", to="Mahesh Babu", document="deed.pdf"),
                        transfer(3, "Ac.0.29", to="Kiran Raao", document="scan.pdf")], COPIED)
    assert len(parcel["sellers"][0]["transfers"]) == 2 and parcel["sellers"][0]["added"].get("area") == 58


def test_a_transfer_with_no_pages_is_never_taken_for_a_copy_and_the_turns_own_key_of_a_document_is_what_the_pages_are_read_by():
    keyed = [{**transfer(1, "Ac.6.06", to="One", document="deed.pdf"), "source": "t1:d1"},
             {**transfer(2, "Ac.6.06", to="Two", document="scan.pdf"), "source": "t1:d2"}]
    assert len(ledger(keyed, COPIED)[0]["sellers"][0]["transfers"]) == 2, "the pages are those of the turn's documents, not the file names"
    assert len(ledger(keyed, on_copies((("t1:d1", 1), ("t1:d2", 1))))[0]["sellers"][0]["transfers"]) == 1
    assert len(ledger([transfer(1, "Ac.6.06", document="deed.pdf", pages=()), transfer(2, "Ac.6.06", to="Two", document="scan.pdf", pages=())],
                      COPIED)[0]["sellers"][0]["transfers"]) == 2


# The papers' own abbreviations, and a transfer that is never added (plan AN.27, P20 (d)): found by the replay of the reviewed bundle, where
# two partitions written "Ac.8.24 gts" were not read - "gts" was not known after Ac.8.24, so "24 gts" was a second extent - and the
# parcel they were in was called incomplete for them.
@pytest.mark.parametrize("words,guntas,how", [
    ("Ac.8.24 gts", 344, "acres.guntas"), ("Ac.8.24 gts.", 344, "acres.guntas"), ("Ac. 8-24 Gts.", 344, "acres.guntas"),
    ("Acs.2-20 gts", 100, "acres.guntas"), ("Acs. 2.20 Gts.", 100, "acres.guntas"), ("an extent of Ac.1.18 gts in Sy.No.201", 58, "acres.guntas"),
    ("6 acs 6 gts", 246, "acres and guntas"), ("6 Acs. 6 Gts.", 246, "acres and guntas"), ("6.5 acs", 260, "decimal acres"),
    ("6 acs", 240, "acres")])
def test_the_abbreviations_the_papers_use_are_read_as_the_extent_they_write(words, guntas, how):
    assert parse(words) == (Fraction(guntas), how)


@pytest.mark.parametrize("words", ["Ac.8.24 gts and Ac.1.18 gts", "Ac.8.24 gts (each Ac.0.29 gts)", "Acs.2-20 gts and 5 gts", "6 acs 6 gts and 4 acs"])
def test_two_extents_written_with_the_abbreviations_are_still_two(words):
    assert parse(words) == (None, "more than one extent in these words")


def test_a_partition_or_a_decree_whose_extent_cannot_be_read_is_listed_and_does_not_make_the_parcel_incomplete():
    (parcel,) = ledger([transfer(1, "Ac.1.18", total="Ac.8.24"),
                        transfer(2, "equal shares", kind="partition", frm="Anil Kumar", to="his sons", sort="1974-02-09", date="9-2-1974"),
                        transfer(3, "", kind="decree", frm="Anil Kumar", to="Priya Devi", sort="1990-01-01", date="1 January 1990")])
    assert parcel["complete"] is True and parcel["unread"] == []
    seller, other = parcel["sellers"]
    assert (seller["names"], seller["added"].get("area")) == (["Hari Prasad"], 58) and (other["names"], other["added"].get("area")) == (["Anil Kumar"], None)
    assert [(t["kind"], t["value"], t["how"]) for t in other["not_added"]] == [
        ("partition", None, "no extent in these words"), ("decree", None, "no extent in these words")]
    assert parcel["totals"][0]["by_seller"] == [{"seller": "Hari Prasad", "leaves": 286, "exceeds": None}], "a remainder is named"
    (shown_parcel,) = shown([transfer(1, "Ac.1.18"), transfer(2, "equal shares", kind="partition", frm="Anil Kumar")])
    (kept,) = shown_parcel["sellers"][1]["not_added"]
    assert (kept["as"], kept["extent"], kept["read_as"]) == (None, "equal shares", "no extent in these words")
    assert kept["why"] == "a partition allots a share; it is not a sale"
    json.dumps(shown_parcel)


def test_a_sale_gift_or_settlement_whose_extent_cannot_be_read_still_makes_the_parcel_incomplete():
    for kind in ("sale", "gift", "settlement"):
        (parcel,) = ledger([transfer(1, "Ac.1.18", total="Ac.8.24"), transfer(2, "part of the land", kind=kind, to="Mahesh Babu")])
        assert parcel["complete"] is False and [u["id"] for u in parcel["unread"]] == ["X2"]
        assert parcel["totals"][0]["by_seller"] == []


def test_two_copies_of_a_partition_with_no_extent_are_one_partition():
    copied = {frozenset({("deed.pdf", 1), ("scan.pdf", 1)})}
    (parcel,) = ledger([transfer(1, "equal shares", kind="partition", frm="Anil Kumar", document="deed.pdf"),
                        transfer(2, "equal shares", kind="partition", frm="Anil Kumar", document="scan.pdf")], copied)
    assert [len(t["ids"]) for t in parcel["sellers"][0]["not_added"]] == [2]


def test_a_stated_whole_written_two_ways_is_one_stated_whole_and_two_that_differ_are_two():
    (parcel,) = ledger([transfer(1, "Ac.1.18", total="Ac.8.24 guntas"), transfer(2, "Ac.1.00", total="Ac.8.24 gts", to="Mahesh Babu"),
                        transfer(3, "Ac.0.10", total="8 acres 24 guntas", to="Anil Kumar"), transfer(4, "Ac.0.20", total="Ac.9.00", to="Priya Devi")])
    assert [(t["text"], t["value"], t["ids"]) for t in parcel["totals"]] == [
        ("Ac.8.24 guntas", 344, ["X1", "X2", "X3"]), ("Ac.9.00", 360, ["X4"])]
    assert len(parcel["totals"][0]["by_seller"]) == 1, "told once, not once for each way it was written"
    (parcel,) = ledger([transfer(1, "Ac.1.18", total="the whole survey number"), transfer(2, "Ac.1.00", total="the whole  survey number",
                                                                                      to="Mahesh Babu")])
    assert [(t["text"], t["ids"]) for t in parcel["totals"]] == [("the whole survey number", ["X1", "X2"])], "unreadable ones by their words"
    (parcel,) = ledger([transfer(1, "Ac.1.18", total="the whole survey number"), transfer(2, "Ac.1.00", total="the entire field", to="Mahesh Babu")])
    assert [t["text"] for t in parcel["totals"]] == ["the whole survey number", "the entire field"], "unreadable ones that differ are two"


@pytest.mark.parametrize("words,guntas", [
    ("Ac 3 – 12 Guntas", 132), ("Ac 3 — 12 gts", 132), ("Ac. 3−12", 132), ("Acre 7", 280), ("Acres 7", 280),
    ("Ac 7", 280), ("Acre 7 guntas", 7)])
def test_an_extent_is_read_whatever_its_dash_and_with_the_unit_before_a_whole_number(words, guntas):
    # Plan AN.28, B14 and B15 (invented figures): a long dash between acres and guntas, and the word before a whole number of acres.
    assert extents.parse(words)[0] == guntas
