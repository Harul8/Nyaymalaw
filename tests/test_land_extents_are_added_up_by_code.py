"""Land extents are added up by code (plan AN.27, P13d; invariant I6).

No step added extents: a model was left to say whether a claim could be matched, and a total less two smaller sales that comes to the
claimed figure was an inference nobody checked. Extents are read as a paper writes them (Ac.1.18 guntas, 6 acres 6 guntas, 29 guntas,
150 sq. yards) into guntas (40 to an acre), added by parcel with the same transfer counted once where papers report it, compared
with a stated whole extent, and rendered back as the papers write them - and a sum says it is only of what was found. The papers
here are synthetic.
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


def transfer(number, extent, *, parcel="Sy.No.487", to="Jelli Krishna", date="30-10-1985", sort="1985-10-30", total="",
             document="deed.pdf", pages=(1,), kind="sale"):
    return {"id": f"X{number}", "parcel": parcel, "extent": extent, "total": total, "to": to, "date": date, "sort": sort, "kind": kind,
            "document": document, "pages": list(pages)}


def test_the_sales_of_a_parcel_are_added_and_what_they_leave_of_its_stated_extent_is_named():
    (parcel,) = ledger([transfer(1, "Ac.1.18 guntas", total="Ac.8.24 guntas"),
                        transfer(2, "Ac.1.00", to="Jelli Jairam", sort="1986-01-02")])
    assert parcel["parcel"] == "Sy.No.487" and parcel["complete"] and parcel["sum"] == 98
    (total,) = parcel["totals"]
    assert (total["guntas"], total["leaves"]) == (344, 246) and render(total["leaves"]) == "6 acres 6 guntas (Ac.6.06)"


def test_the_same_transfer_reported_by_several_papers_is_counted_once_with_every_paper():
    (parcel,) = ledger([transfer(1, "Ac.1.18 guntas", document="deed.pdf"),
                        transfer(2, "Ac.1.18", parcel="Survey No. 487", to="JELLI  KRISHNA.", document="order.pdf", pages=(4,))])
    (only,) = parcel["transfers"]
    assert parcel["sum"] == 58 and only["ids"] == ["X1", "X2"]
    assert [p["document"] for p in only["papers"]] == ["deed.pdf", "order.pdf"]


def test_two_transfers_of_one_extent_on_one_day_to_different_buyers_are_two():
    (parcel,) = ledger([transfer(1, "Ac.0.29", to="Jelli Krishna"), transfer(2, "Ac.0.29", to="Jelli Jairam")])
    assert len(parcel["transfers"]) == 2 and parcel["sum"] == 58


def test_the_same_extent_to_the_same_buyer_on_two_days_is_two_transfers():
    (parcel,) = ledger([transfer(1, "Ac.0.29", sort="1985-10-30"), transfer(2, "Ac.0.29", sort="1986-10-30")])
    assert len(parcel["transfers"]) == 2 and parcel["sum"] == 58


def test_an_undated_transfer_is_told_apart_by_its_buyer_and_its_extent():
    (parcel,) = ledger([transfer(1, "Ac.0.29", sort="", date="undated"), transfer(2, "Ac.0.30", sort="", date="undated")])
    assert len(parcel["transfers"]) == 2


def test_an_extent_that_cannot_be_read_is_never_added_and_the_sum_says_it_is_not_complete():
    (parcel,) = ledger([transfer(1, "Ac.1.18 guntas", total="Ac.8.24"), transfer(2, "part of the land", to="Jelli Jairam"),
                        transfer(3, "Ac.1.45", to="Other")])
    assert parcel["sum"] == 58 and not parcel["complete"]
    assert [(u["id"], u["why"]) for u in parcel["unread"]] == [("X2", "no extent in these words"), ("X3", "the guntas are 40 or more")]
    assert parcel["totals"][0]["leaves"] is None, "no remainder is named while a transfer is unread"


def test_a_transfer_whose_words_were_not_found_on_its_page_is_never_added_nor_its_stated_extent_used():
    (parcel,) = ledger([transfer(1, "Ac.1.18", total="Ac.8.24"), {**transfer(2, "Ac.1.00", to="Other", total="Ac.9.00"), "anchored": False},
                        {**transfer(3, "Ac.0.10", to="Third"), "anchored": True}])
    assert parcel["sum"] == 68 and not parcel["complete"]
    assert [(u["id"], u["why"]) for u in parcel["unread"]] == [("X2", "its words were not found on the page")]
    assert [s["text"] for s in parcel["totals"]] == ["Ac.8.24"] and parcel["totals"][0]["leaves"] is None


def test_a_stated_extent_that_cannot_be_read_names_no_remainder_and_sales_beyond_the_whole_leave_less_than_nothing():
    (parcel,) = ledger([transfer(1, "Ac.1.18", total="the whole survey number")])
    assert parcel["totals"][0]["guntas"] is None and parcel["totals"][0]["leaves"] is None
    (parcel,) = ledger([transfer(1, "Ac.2.00", total="Ac.1.00")])
    assert parcel["totals"][0]["leaves"] == -40 and render(parcel["totals"][0]["leaves"]) == "-1 acre (Ac.1.00)"


def test_different_stated_extents_are_each_named_and_parcels_that_differ_are_kept_apart_in_the_papers_order():
    found = ledger([transfer(1, "Ac.1.18", total="Ac.8.24"), transfer(2, "Ac.0.29", parcel="Sy.No.487/A", total="Ac.2.00"),
                    transfer(3, "Ac.1.00", total="Ac.9.00"), transfer(4, "Ac.0.10", parcel="")])
    assert [p["parcel"] for p in found] == ["Sy.No.487", "Sy.No.487/A"] and len(found[0]["totals"]) == 2
    assert found[1]["sum"] == 29 and found[0]["sum"] == 98


def test_the_ledger_in_words_is_plain_data_and_says_it_is_only_of_what_was_found():
    out = shown([transfer(1, "Ac.1.18 guntas", total="Ac.8.24 guntas"), transfer(2, "Ac.1.00", to="Jelli Jairam", sort="1986-01-02")])
    json.dumps(out)
    (parcel,) = out
    assert parcel["sum"] == "2 acres 18 guntas (Ac.2.18)" and parcel["complete"] is True
    assert parcel["totals"][0]["leaves"] == "6 acres 6 guntas (Ac.6.06)" and parcel["totals"][0]["as"] == "8 acres 24 guntas (Ac.8.24)"
    assert parcel["caveat"] == extents.CAVEAT and "makes the sum wrong" in parcel["caveat"]
    assert parcel["transfers"][0]["in_guntas"] == "1 acre 18 guntas (Ac.1.18)" and parcel["transfers"][0]["read_as"] == "acres.guntas"
    assert shown([transfer(1, "nothing")])[0]["sum"] is None
