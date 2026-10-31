"""The figures of any matter are added up by code (plan AN.27, P13d; AN.28, D3 and D7; AN.29, D9; invariant I6).

The papers of any matter state figures - sums of money, areas, lengths, weights and volumes in whatever units a paper uses, shares, rates
and periods. The model reads each figure into numbers and units from the words of the page, since it knows how papers write them; code
checks that every number stands in those words (and the unit as written), converts by its table of units, adds a giver's figures to
that giver's alone, dimension by dimension, never a share, a rate or a period, counts one transaction once however many papers report
it, and says in words what it did. It reads by no notation of any kind of matter. The papers, names and figures here are invented.
"""
import json
from fractions import Fraction

import pytest

from nm.core_engine import figures
from nm.core_engine.figures import fault, instrument_key, ledger, quantities_in, read, render, shown, subject_key
from tests.test_the_plan_records_the_transfers import reading

pytestmark = pytest.mark.class_a


def one(number, unit, written):
    return {"number": number, "unit": unit, "written": written}


def quantity(dimension, *parts):
    return {"dimension": dimension, "parts": list(parts)}


@pytest.mark.parametrize("figure,given,words,dimension,base", [
    ("2 kg 350 g", quantity("mass", one("2", "kilogram", "kg"), one("350", "gram", "g")), "sold 2 kg 350 g of grain", "mass", 2350),
    ("Rs. 2.5 lakhs", quantity("money", one("2.5", "lakh", "lakhs")), "a loan of Rs. 2.5 lakhs", "money", 250000),
    ("Rs.2,50,000/-", quantity("money", one("250000", "rupee", "Rs")), "a loan of Rs.2,50,000/- only", "money", 250000),
    ("Rupees Two Lakhs Fifty Thousand only", quantity("money", one("250000", "rupee", "rupees")),
     "a loan of Rupees Two Lakhs Fifty Thousand only", "money", 250000),
    ("1.5 crores", quantity("money", one("1.5", "crore", "crores")), "paid 1.5 crores", "money", 15000000),
    ("1 m 25 cm", quantity("length", one("1", "metre", "m"), one("25", "centimetre", "cm")), "a pipe of 1 m 25 cm", "length", Fraction(125, 100)),
    ("1,100 sq. ft", quantity("area", one("1100", "square_foot", "sq. ft")), "a floor of 1,100 sq. ft", "area",
     1100 * Fraction("0.09290304")),
    ("4 hectares", quantity("area", one("4", "hectare", "hectares")), "an area of 4 hectares", "area", 40000),
    ("12 litres", quantity("volume", one("12", "litre", "litres")), "filled with 12 litres", "volume", 12),
])
def test_a_figure_is_read_into_numbers_and_units_and_code_converts_them_by_its_table(figure, given, words, dimension, base):
    found, value, how, ladder = read(figure, given, words)
    assert (found, value) == (dimension, Fraction(base))
    assert ladder == tuple(part["unit"] for part in given["parts"]) and "every number is the page's own" in how


@pytest.mark.parametrize("named,key", [("Sq. Ft.", "square_foot"), ("kgs", "kilogram"), ("Acres", "acre"), ("LAKHS", "lakh"),
                                       ("square metres", "square_metre"), ("sq m", "square_metre"), ("Rs.", "rupee"), ("₹", "rupee"),
                                       ("hectare", "hectare"), ("square_foot", "square_foot"), ("Litres", "litre")])
def test_a_unit_a_model_names_in_plain_words_is_found_in_the_table_however_it_is_set(named, key):
    assert figures.unit_named(named) == key
    assert figures.unit_named("bushel") is None and figures.unit_named("") is None and figures.unit_named(None) is None


def test_a_unit_code_does_not_know_is_never_converted_and_says_so():
    given = quantity("mass", one("5", "bushel", "bushels"))
    assert read("5 bushels", given, "sold 5 bushels of grain") == (None, None, "a unit it is read in is not one code can convert", None)
    assert fault({"figure": "5 bushels", "quantity": given, "words": "sold 5 bushels of grain"}) == (
        "a unit it is read in is not one code can convert")
    named = quantity("mass", one("Kilograms", "kilogram", "kg"))
    assert read("5 kg", {"dimension": "mass", "parts": [{"number": "5", "unit": "Kilograms", "written": "kg"}]}, "sold 5 kg")[:2] == (
        "mass", Fraction(5000)), "a model's own name for a unit that the table knows is converted"
    assert named["parts"][0]["unit"] == "kilogram"


@pytest.mark.parametrize("given,words,why", [
    (quantity("money", one("6000", "rupee", "Rs")), "paid Rs.1,260", figures.NOT_IN_WORDS),
    (quantity("money", one("1260", "rupee", "dollars")), "paid Rs.1,260", "the unit as written is not in the words that record it"),
    (quantity("mass", one("5", "rupee", "Rs")), "paid Rs.5 for it", "its units are not all of the kind the figure is"),
    (quantity("money", one("about five", "rupee", "Rs")), "paid Rs.5", "a number read from it is not a number code can read"),
    (quantity("money"), "paid Rs.5", "no number and unit were read from it"),
    (quantity("weight", one("5", "kilogram", "kg")), "5 kg", "its kind of figure is not one code adds"),
])
def test_a_reading_the_words_do_not_bear_is_never_used_and_says_why(given, words, why):
    assert read("anything", given, words) == (None, None, why, None)
    assert fault({"figure": "anything", "quantity": given, "words": words}) == why


@pytest.mark.parametrize("dimension,words", [("share", "his one-third share"), ("rate", "a rent of Rs.4,750 per month"),
                                              ("period", "for a term of 11 months"), ("none", "a sum agreed between them")])
def test_a_share_a_rate_a_period_or_no_figure_is_listed_and_is_no_fault(dimension, words):
    figure = "" if dimension == "none" else "as written"
    assert read(figure, quantity(dimension), words) == (None, None, figures.LISTED_ONLY[dimension], None)
    assert fault({"figure": figure, "quantity": quantity(dimension), "words": words}) is None


def test_a_figure_written_but_read_as_no_figure_is_a_fault_the_model_is_told_of():
    assert fault({"figure": "Rs.500", "quantity": quantity("none"), "words": "paid Rs.500"}) == "no quantity was read from it"


def test_a_stated_whole_is_checked_the_same_way_and_a_fault_in_it_is_named_as_the_whole():
    given = {"figure": "5 kg", "quantity": reading("5 kg"), "whole": "20 kg", "whole_quantity": reading("20 kg"),
             "words": "sold 5 kg out of 20 kg"}
    assert fault(given) is None
    assert fault({**given, "words": "sold 5 kg of the stock"}) == "the whole it gives: " + figures.NOT_IN_WORDS


@pytest.mark.parametrize("dimension,value,ladder,said", [
    ("money", 250000, (), "Rs 2,50,000"), ("money", 1050, (), "Rs 1,050"), ("money", Fraction("12500.50"), (), "Rs 12,500.50"),
    ("money", -15000000, (), "-Rs 1,50,00,000"), ("money", Fraction(1, 2), (), "Rs 0.50"),
    ("mass", 2_350, ("kilogram", "gram"), "2 kilograms 350 grams"), ("mass", 2_000, ("kilogram", "gram"), "2 kilograms"),
    ("mass", 1_000, ("kilogram",), "1 kilogram"), ("length", Fraction(125, 100), ("metre", "centimetre"), "1 metre 25 centimetres"),
    ("area", 10_000, ("hectare",), "1 hectare"), ("area", Fraction("4046.86"), ("square_metre",), "4,046.86 square metres"),
    ("volume", 12, (), "12 litres"), ("length", Fraction(3, 2), ("metre",), "1.50 metres"), ("mass", Fraction(5, 2), ("gram",), "2.50 grams")])
def test_a_figure_is_said_back_in_the_units_its_papers_wrote_it_in(dimension, value, ladder, said):
    assert render(dimension, value, ladder) == said


def test_a_half_goes_up_as_a_paper_rounds_it_not_to_the_even():
    assert render("money", Fraction("0.125")) == "Rs 0.13" and render("money", Fraction("0.135")) == "Rs 0.14"


def test_figures_are_found_in_words_by_the_tables_aliases_alone():
    found = quantities_in("paid Rs.1,260 and 12 kg of grain and 3 metres of pipe, then INR 10,700 and 40 sq. yards")
    assert [(number, unit) for _, number, unit in found] == [
        ("1,260", "rupee"), ("12", "kilogram"), ("3", "metre"), ("10,700", "rupee"), ("40", "square_yard")]
    assert quantities_in("no figure here, only the year 2001 and clause 7") == []


def test_a_scale_after_a_number_makes_it_a_figure_of_that_scale_not_rupees_and_a_stray_word():
    found = quantities_in("The price was Rs. 7.4 lakhs, then Rs.1,260 and Rs. 3 crore and 2 lakh")
    assert [(words, unit) for words, _, unit in found] == [("7.4 lakhs", "lakh"), ("Rs.1,260", "rupee"), ("3 crore", "crore"),
                                                           ("2 lakh", "lakh")]


@pytest.mark.parametrize("first,second,same", [
    ("Loan Account 12", "loan account 12.", True), ("Account No. 12", "account no 12", True), ("Lot 487/A", "Lot 487 / A", True),
    ("Loan account 12", "Loan account 21", False), ("Lot 487/A", "Lot 487A", False), ("Account 12", "Account 12 (savings)", False),
    ("ఖాతా 12", "ఖాతా  12", True), ("ఖాతా 12", "అప్పు 12", False)])
def test_a_subject_is_one_key_by_its_tidied_words_and_no_more(first, second, same):
    assert (subject_key(first) == subject_key(second)) is same
    assert subject_key("") == "" and subject_key(" . ") == ""


@pytest.mark.parametrize("first,second,same", [
    ("Doc No. 1234/2001", "Agreement No. 1234 of 2001", True), ("Doc No. 1234/2001", "Doc No. 1235/2001", False),
    ("No. 77 of 2003", "77/03", True), ("Ref 9", "9", True)])
def test_a_document_is_one_key_by_its_numbers_and_a_year_by_its_last_two_digits(first, second, same):
    assert (instrument_key(first) == instrument_key(second)) is same
    assert instrument_key("the deed") is None and instrument_key("") is None and instrument_key(None) is None


def deal(number, figure, *, given=None, whole="", whole_given=None, words=None, subject="Loan account 12", giver="Bank of Somewhere",
         receiver="Tarun Mehra", kind="loan", date="1-1-2010", sort="2010-01-01", document="loan.pdf", pages=(1,), instrument="",
         giver_died="", giver_died_sort="", anchored=True):
    """A transaction as research v13 records it (invented): its figure as written and the model's reading of it (as `reading` reads
    one number against one unit unless `given` says otherwise), any whole, the number of the document that records it and the words
    that record it."""
    return {"id": f"X{number}", "subject": subject, "figure": figure, "quantity": given or reading(figure), "whole": whole,
            "whole_quantity": whole_given or reading(whole), "from": giver, "to": receiver, "date": date, "sort": sort, "kind": kind,
            "document": document, "source": document, "pages": list(pages), "instrument": instrument, "giver_died": giver_died,
            "giver_died_sort": giver_died_sort, "anchored": anchored,
            "words": words if words is not None else f"{figure} out of {whole}" if whole else figure}


def test_money_lent_and_paid_is_added_giver_by_giver_and_set_against_the_stated_sum():
    rows = [deal(1, "Rs.2,00,000/-", whole="Rs.2,00,000/-"),
            deal(2, "Rs.50,000", giver="Tarun Mehra", receiver="Bank of Somewhere", kind="payment", date="1-1-2011", sort="2011-01-01"),
            deal(3, "Rs.25,000", giver="Tarun Mehra", receiver="Bank of Somewhere", kind="payment", date="1-1-2012", sort="2012-01-01")]
    (account,) = ledger(rows)
    lender, borrower = account["givers"]
    assert lender["added"] == {"money": 200000} and borrower["added"] == {"money": 75000} and account["complete"]
    (stated,) = account["totals"]
    assert (stated["dimension"], stated["value"]) == ("money", 200000)
    assert stated["by_giver"] == [{"giver": "Bank of Somewhere", "leaves": 0, "exceeds": None},
                                  {"giver": "Tarun Mehra", "leaves": 125000, "exceeds": None}]
    (said,) = shown(rows)
    json.dumps(said)
    assert said["givers"][1]["added"] == "Rs 75,000" and said["totals"][0]["by_giver"][1]["leaves"] == "Rs 1,25,000"
    assert said["givers"][1]["counted"][0]["as"] == "Rs 50,000" and said["totals"][0]["dimension"] == "money"
    assert said["subject"] == "Loan account 12" and said["complete"] is True and said["caveat"] == figures.CAVEAT


def test_quantities_and_sums_of_one_subject_are_added_apart_and_each_whole_is_set_against_its_own_dimension():
    rows = [deal(1, "1 hectare", words="sold 1 hectare out of 4 hectares", whole="4 hectares", subject="Farm 12", giver="Tarun Mehra",
                 receiver="Nisha Kapur", kind="sale", document="deed.pdf"),
            deal(2, "Rs.5,00,000", words="paid Rs.5,00,000 of the price of Rs.8,00,000", whole="Rs.8,00,000", subject="Farm 12",
                 giver="Nisha Kapur", receiver="Tarun Mehra", kind="payment", document="deed.pdf"),
            deal(3, "Rs.20,000", words="Tarun Mehra lent Rs.20,000", subject="Farm 12", giver="Tarun Mehra", receiver="Nisha Kapur",
                 date="2-2-2010", sort="2010-02-02", document="deed.pdf")]
    (farm,) = ledger(rows)
    seller, buyer = farm["givers"]
    assert seller["added"] == {"area": 10_000, "money": 20000} and buyer["added"] == {"money": 500000}
    area, money = farm["totals"]
    assert area["by_giver"] == [{"giver": "Tarun Mehra", "leaves": 30_000, "exceeds": None}]
    assert money["by_giver"] == [{"giver": "Tarun Mehra", "leaves": 780000, "exceeds": None},
                                 {"giver": "Nisha Kapur", "leaves": 300000, "exceeds": None}]
    (said,) = shown(rows)
    assert said["givers"][0]["added"] == "Rs 20,000; 1 hectare", "a sum and an area, never added together"


def test_a_giver_whose_figures_go_beyond_the_whole_is_named_and_a_giver_who_gave_less_is_set_against_it():
    rows = [deal(1, "12 kg", whole="20 kg", words="sold 12 kg out of 20 kg", subject="Stock 3", giver="Asha", kind="sale"),
            deal(2, "9 kg", words="sold 9 kg", subject="Stock 3", giver="Asha", kind="sale", date="2-1-2010", sort="2010-01-02"),
            deal(3, "5 kg", words="gave 5 kg", subject="Stock 3", giver="Farida", kind="gift", date="3-1-2010", sort="2010-01-03")]
    (stock,) = ledger(rows)
    (stated,) = stock["totals"]
    assert stated["by_giver"] == [{"giver": "Asha", "leaves": None, "exceeds": 1000}, {"giver": "Farida", "leaves": 15000, "exceeds": None}]
    (said,) = shown(rows)
    assert said["totals"][0]["by_giver"] == [{"giver": "Asha", "leaves": None, "exceeds": "1 kilogram"},
                                             {"giver": "Farida", "leaves": "15 kilograms", "exceeds": None}]


def test_a_figure_or_a_whole_not_in_the_words_that_record_it_is_not_used_and_one_written_another_way_is():
    (account,) = ledger([deal(1, "Rs.2,00,000/-", words="a loan was given", whole="Rs.5,00,000")])
    assert account["givers"] == [] and [(u["id"], u["why"]) for u in account["unread"]] == [("X1", figures.NOT_IN_WORDS)]
    assert account["totals"][0]["value"] is None and account["totals"][0]["how"] == figures.NOT_IN_WORDS
    (account,) = ledger([deal(1, "Rs.2,00,000/-", words="a loan of Rupees Two Lakhs only",
                              given=quantity("money", one("200000", "rupee", "Rupees")))])
    assert account["givers"][0]["added"] == {"money": 200000}
    (farm,) = ledger([deal(1, "1 hectare 20 ares", words="an area of one hectare and 20 ares", subject="Farm 12", kind="sale",
                           given=quantity("area", one("1", "hectare", "hectare")))])
    assert farm["givers"][0]["added"] == {"area": 10_000}, "the reading is the model's; code checks only that its numbers are the page's"


def test_a_transaction_whose_words_were_not_found_on_the_page_supports_no_figure_and_no_whole():
    rows = [deal(1, "Rs.2,00,000", whole="Rs.5,00,000", anchored=False, pages=()), deal(2, "Rs.1,000", date="2-1-2010", sort="2010-01-02")]
    (account,) = ledger(rows)
    assert [(u["id"], u["why"], u["pages"]) for u in account["unread"]] == [("X1", "its words were not found on the page", [])]
    assert account["totals"] == [] and not account["complete"] and account["givers"][0]["added"] == {"money": 1000}


def test_a_share_a_rate_and_a_period_are_listed_and_not_added_and_a_lease_or_a_mortgage_is_never_added():
    rows = [deal(1, "1 hectare", words="1 hectare out of 4 hectares", whole="4 hectares", subject="Farm 12", giver="Tarun Mehra",
                 kind="sale"),
            deal(2, "1/3rd share", given=quantity("share"), words="his 1/3rd share", subject="Farm 12", giver="Tarun Mehra", kind="sale",
                 date="2-2-2012", sort="2012-02-02"),
            deal(3, "Rs.4,750 per month", given=quantity("rate"), words="a rent of Rs.4,750 per month", subject="Farm 12",
                 giver="Tarun Mehra", kind="lease", date="3-3-2013", sort="2013-03-03"),
            deal(4, "Rs.1,30,000", words="mortgaged for Rs.1,30,000", subject="Farm 12", giver="Tarun Mehra", kind="mortgage",
                 date="4-4-2014", sort="2014-04-04")]
    (farm,) = ledger(rows)
    (giver,) = farm["givers"]
    assert giver["added"] == {"area": 10_000} and not farm["complete"]
    assert [(u["id"], u["why"]) for u in farm["unread"]] == [("X2", figures.LISTED_ONLY["share"])]
    assert [(t["kind"], t["value"]) for t in giver["listed"]] == [("lease", None), ("mortgage", 130000)]
    assert farm["totals"][0]["by_giver"] == [], "no remainder while a sale is not added"
    (said,) = shown(rows)
    assert [t["why"] for t in said["givers"][0]["listed"]] == [
        "a lease passes use for a time, not what the owner holds", "a mortgage is security for a debt, not a sale"]


@pytest.mark.parametrize("kind,why", [("partition", "a partition allots a share; it is not a sale"),
                                      ("decree", "a court's decree is not the giver's own transfer"),
                                      ("other", "not a sale, a gift, a settlement, a loan or a payment")])
def test_a_partition_a_decree_or_anything_else_is_listed_with_why_and_never_added_nor_makes_the_subject_incomplete(kind, why):
    rows = [deal(1, "10 kg", kind="sale", words="sold 10 kg", subject="Stock 3", giver="Asha"),
            deal(2, "equal shares", given=quantity("share"), kind=kind, words="in equal shares", subject="Stock 3", giver="Asha")]
    (stock,) = ledger(rows)
    assert stock["complete"] and stock["givers"][0]["added"] == {"mass": 10_000}
    (said,) = shown(rows)
    assert [(t["kind"], t["why"]) for t in said["givers"][0]["listed"]] == [(kind, why)]


def test_a_transaction_with_no_giver_named_is_listed_and_added_to_no_one():
    (stock,) = shown([deal(1, "10 kg", kind="sale", words="sold 10 kg", subject="Stock 3", giver="")])
    (unnamed,) = stock["givers"]
    assert (unnamed["names"], unnamed["added"], len(unnamed["counted"])) == ([], None, 1)


def test_two_spellings_of_a_giver_are_two_givers_unless_the_papers_make_them_one_transaction():
    rows = [deal(1, "10 kg", words="sold 10 kg", kind="sale", subject="Stock 3", giver="Asha Rao", document="a.pdf"),
            deal(2, "10 kg", words="sold 10 kg", kind="sale", subject="Stock 3", giver="Asha Raao", document="b.pdf",
                 date="2-1-2010", sort="2010-01-02")]
    (stock,) = ledger(rows)
    assert [group["names"] for group in stock["givers"]] == [["Asha Rao"], ["Asha Raao"]], "alike is not the same"
    same = [rows[0], {**rows[1], "date": rows[0]["date"], "sort": rows[0]["sort"], "to": rows[0]["to"]}]
    (stock,) = ledger(same)
    assert len(stock["givers"]) == 1 and stock["givers"][0]["counted"][0]["ids"] == ["X1", "X2"]
    assert stock["givers"][0]["names"] == ["Asha Rao", "Asha Raao"], "one transaction its giver's name was read two ways"


def test_one_document_reported_twice_is_one_transaction_and_reported_with_another_giver_is_linked_and_added_once():
    # Plan AN.28, B16 (invented): an agreement by its number, in a paper that gives it another date and receiver's spelling, and in
    # one that names another giver for it.
    deed = deal(1, "20 kg", subject="Stock 3", giver="Tarun Mehra", receiver="Nisha Kapur", kind="sale",
                instrument="Doc No. 1234/2001", document="deed.pdf")
    again = deal(2, "20 kg", subject="Stock 3", giver="Tarun Mehra", receiver="N. Kapur", kind="sale",
                 instrument="Agreement No. 1234 of 2001", document="order.pdf", date="undated", sort="")
    rival = deal(3, "20 kg", subject="Stock 3", giver="Imran Qadri", receiver="Nisha Kapur", kind="sale",
                 instrument="Doc. No. 1234/2001", document="plaint.pdf")
    (stock,) = ledger([deed, again, rival])
    first, second = stock["givers"]
    assert first["names"] == ["Tarun Mehra"] and first["counted"][0]["ids"] == ["X1", "X2"] and first["added"] == {"mass": 20_000}
    assert second["names"] == ["Imran Qadri"] and second["counted"] == [] and second["added"] == {}
    (linked,) = second["listed"]
    assert (linked["twin_of"], linked["instrument"]) == ("X1", "Doc. No. 1234/2001")
    (said,) = shown([deed, again, rival])
    assert said["givers"][1]["listed"][0]["why"] == (
        "the same document (Doc. No. 1234/2001) as X1, which another paper reports with another giver: added once, there")


def test_two_documents_of_different_numbers_are_two_transactions_however_alike():
    (stock,) = ledger([deal(1, "20 kg", subject="Stock 3", kind="sale", instrument="Doc No. 1234/2001"),
                       deal(2, "20 kg", subject="Stock 3", kind="sale", instrument="Doc No. 1235/2001", document="deed2.pdf")])
    assert len(stock["givers"][0]["counted"]) == 2 and stock["givers"][0]["added"] == {"mass": 40_000}
    (stock,) = ledger([deal(1, "20 kg", subject="Stock 3", kind="sale"),
                       deal(2, "20 kg", subject="Stock 3", kind="sale", document="deed2.pdf")])
    assert len(stock["givers"][0]["counted"]) == 1, "without numbers, the same date, figure and receiver are one"


def on_copies(*pairs):
    return {frozenset(pair) for pair in pairs}


COPIED = on_copies((("deed.pdf", 1), ("scan.pdf", 1)))


def test_one_sale_read_on_two_copies_of_a_page_is_one_whatever_the_receivers_name_was_read_as():
    both = [deal(1, "6 kg", kind="sale", subject="Stock 3", receiver="Anil Kumar", document="deed.pdf"),
            deal(2, "6 kg", kind="sale", subject="Stock 3", receiver="Anil Kumaar", document="scan.pdf")]
    assert ledger(both)[0]["givers"][0]["added"] == {"mass": 12_000}, "without the pages' copies a name read two ways is two receivers"
    (stock,) = ledger(both, COPIED)
    (giver,) = stock["givers"]
    (only,) = giver["counted"]
    assert giver["added"] == {"mass": 6_000} and only["ids"] == ["X1", "X2"] and only["to"] == "Anil Kumar"
    assert only["names"] == ["Anil Kumar", "Anil Kumaar"] and [p["document"] for p in only["papers"]] == ["deed.pdf", "scan.pdf"]
    (said,) = shown(both, COPIED)
    assert said["givers"][0]["added"] == "6 kilograms" and said["givers"][0]["counted"][0]["also_read_as"] == ["Anil Kumaar"]
    assert "also_read_as" not in shown([deal(1, "6 kg", kind="sale", subject="Stock 3")], COPIED)[0]["givers"][0]["counted"][0]


def test_papers_that_are_not_copies_of_one_another_are_told_apart_by_the_receiver_and_copies_do_not_make_different_things_one():
    both = [deal(1, "6 kg", kind="sale", subject="Stock 3", receiver="Anil Kumar", document="deed.pdf"),
            deal(2, "6 kg", kind="sale", subject="Stock 3", receiver="Anil Kumaar", document="order.pdf")]
    assert len(ledger(both, COPIED)[0]["givers"][0]["counted"]) == 2
    assert len(ledger(both, on_copies((("deed.pdf", 1), ("order.pdf", 2))))[0]["givers"][0]["counted"]) == 2, "copies of another page"
    for other in (deal(2, "7 kg", kind="sale", subject="Stock 3", receiver="Anil Kumaar", document="scan.pdf"),
                  deal(2, "6 kg", kind="gift", subject="Stock 3", receiver="Anil Kumaar", document="scan.pdf"),
                  deal(2, "6 kg", kind="sale", subject="Stock 3", receiver="Anil Kumaar", document="scan.pdf", sort="1986-10-30")):
        first = deal(1, "6 kg", kind="sale", subject="Stock 3", receiver="Anil Kumar", document="deed.pdf")
        assert len(ledger([first, other], COPIED)[0]["givers"][0]["counted"]) == 2


def test_two_sales_of_one_day_on_a_page_and_its_copy_are_two_not_one_and_not_four():
    both_sales = [deal(1, "3 kg", kind="sale", subject="Stock 3", receiver="Kiran Rao", document="deed.pdf"),
                  deal(2, "3 kg", kind="sale", subject="Stock 3", receiver="Mahesh Babu", document="deed.pdf"),
                  deal(3, "3 kg", kind="sale", subject="Stock 3", receiver="Kiran Raao", document="scan.pdf"),
                  deal(4, "3 kg", kind="sale", subject="Stock 3", receiver="Mahesh Babu", document="scan.pdf")]
    (stock,) = ledger(both_sales, COPIED)
    (giver,) = stock["givers"]
    assert len(giver["counted"]) == 2 and giver["added"] == {"mass": 6_000} and sorted(len(t["ids"]) for t in giver["counted"]) == [2, 2]
    # Where the copy was read for only one of them, the other stays and the one copy joins one of the two.
    (stock,) = ledger(both_sales[:3], COPIED)
    assert len(stock["givers"][0]["counted"]) == 2 and stock["givers"][0]["added"] == {"mass": 6_000}


def test_a_third_paper_that_copies_a_page_of_the_second_joins_the_same_transaction():
    copied = on_copies((("deed.pdf", 1), ("scan.pdf", 1)), (("scan.pdf", 1), ("late.pdf", 4)))
    (stock,) = ledger([deal(1, "6 kg", kind="sale", subject="Stock 3", receiver="S. Prakash", document="deed.pdf"),
                       deal(2, "6 kg", kind="sale", subject="Stock 3", receiver="S. Praksh", document="scan.pdf"),
                       deal(3, "6 kg", kind="sale", subject="Stock 3", receiver="S Prakaash", document="late.pdf", pages=(4,))], copied)
    (giver,) = stock["givers"]
    (only,) = giver["counted"]
    assert only["ids"] == ["X1", "X2", "X3"] and only["names"] == ["S. Prakash", "S. Praksh", "S Prakaash"]
    assert giver["added"] == {"mass": 6_000}


def test_a_paper_never_counts_two_of_its_own_transactions_as_one_because_a_copy_reports_one():
    (stock,) = ledger([deal(1, "3 kg", kind="sale", subject="Stock 3", receiver="Kiran Rao", document="deed.pdf"),
                       deal(2, "3 kg", kind="sale", subject="Stock 3", receiver="Mahesh Babu", document="deed.pdf"),
                       deal(3, "3 kg", kind="sale", subject="Stock 3", receiver="Kiran Raao", document="scan.pdf")], COPIED)
    assert len(stock["givers"][0]["counted"]) == 2 and stock["givers"][0]["added"] == {"mass": 6_000}


def test_a_transaction_with_no_pages_is_never_taken_for_a_copy_and_the_turns_own_key_of_a_document_names_its_pages():
    keyed = [{**deal(1, "6 kg", kind="sale", subject="Stock 3", receiver="One", document="deed.pdf"), "source": "t1:d1"},
             {**deal(2, "6 kg", kind="sale", subject="Stock 3", receiver="Two", document="scan.pdf"), "source": "t1:d2"}]
    assert len(ledger(keyed, COPIED)[0]["givers"][0]["counted"]) == 2, "the pages are those of the turn's documents, not file names"
    assert len(ledger(keyed, on_copies((("t1:d1", 1), ("t1:d2", 1))))[0]["givers"][0]["counted"]) == 1
    bare = [deal(1, "6 kg", kind="sale", subject="Stock 3", document="deed.pdf", pages=()),
            deal(2, "6 kg", kind="sale", subject="Stock 3", receiver="Two", document="scan.pdf", pages=())]
    assert len(ledger(bare, COPIED)[0]["givers"][0]["counted"]) == 2


def test_a_transaction_dated_after_its_givers_recorded_death_carries_a_remark_and_is_still_listed_as_found():
    # Plan AN.29, B17 (invented): a sale dated 5 June 2003 by a giver whose death, 4 April 2003, a paper of the file records.
    after = deal(1, "500 kg", kind="sale", subject="Stock 3", giver="Asha Rao", date="5-6-2003", sort="2003-06-05",
                 giver_died="4-4-2003", giver_died_sort="2003-04-04")
    before = deal(2, "100 kg", kind="sale", subject="Stock 3", giver="Asha Rao", date="1-2-2003", sort="2003-02-01",
                  giver_died="4-4-2003", giver_died_sort="2003-04-04", receiver="Other")
    (stock,) = ledger([after, before])
    first, second = stock["givers"][0]["counted"]
    assert first["remark"] == "dated after the death of the giver that the papers record (4-4-2003)" and "remark" not in second
    assert stock["givers"][0]["added"] == {"mass": 600_000}, "found and added as the papers state it; the remark is the advocate's to weigh"
    (said,) = shown([after, before])
    assert said["givers"][0]["counted"][0]["remark"] == first["remark"] and "remark" not in said["givers"][0]["counted"][1]


@pytest.mark.parametrize("sort,died,remarked", [("2004-01-01", "2003", True), ("2003-06-05", "2003", False), ("", "2003-04-04", False),
                                                ("2003-04-05", "2003-04-04", True), ("2003-04-04", "2003-04-04", False),
                                                ("2003-04-03", "2003-04-04", False), ("2003-06", "2003-04-04", True), ("2003-06-05", "", False)])
def test_a_date_stands_after_a_death_to_the_precision_both_are_given_to(sort, died, remarked):
    assert figures._after(sort, died) is remarked


def test_the_ledger_in_words_is_plain_data_and_says_what_a_sum_is():
    out = shown([deal(1, "10 kg", words="sold 10 kg out of 40 kg", whole="40 kg", kind="sale", subject="Stock 3", giver="Asha Rao"),
                 deal(2, "5 kg", words="gave 5 kg", kind="gift", subject="Stock 3", giver="Asha Rao", receiver="Other", sort="1986-01-02"),
                 deal(3, "equal shares", given=quantity("share"), kind="partition", subject="Stock 3", giver="Asha Rao",
                      receiver="her sons", sort="1974-02-09", words="equal shares")])
    json.dumps(out)
    (stock,) = out
    (giver,) = stock["givers"]
    assert giver["added"] == "15 kilograms" and stock["complete"] is True and giver["names"] == ["Asha Rao"]
    assert stock["totals"][0]["by_giver"] == [{"giver": "Asha Rao", "leaves": "25 kilograms", "exceeds": None}]
    assert stock["totals"][0]["as"] == "40 kilograms" and "sum" not in stock
    (kept,) = giver["listed"]
    assert kept["kind"] == "partition" and kept["why"] == "a partition allots a share; it is not a sale" and kept["as"] is None
    assert [(t["figure"], t["as"], t["read_as"]) for t in giver["counted"]][0] == (
        "10 kg", "10 kilograms", "read from the words as 10 kilograms; every number is the page's own")
    # P20: what a sum is, said once for every ledger - an addition of accounts as stated, giver by giver, not what anyone holds.
    for part in ("whoever states them, giver by giver", "added to that giver's alone", "rival, overlapping or the same thing described twice",
                 "not what anyone holds, owes or has paid", "written two ways",
                 "sums of money with sums of money and each kind of quantity with its own, never a share, a rate or a period"):
        assert part in figures.CAVEAT, part
    assert stock["caveat"] == figures.CAVEAT and shown([deal(1, "nothing", given=quantity("none"), words="nothing")])[0]["givers"] == []
