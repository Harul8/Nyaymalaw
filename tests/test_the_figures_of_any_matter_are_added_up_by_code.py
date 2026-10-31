"""The figures of any matter are added up by code (plan AN.28, D3 and D7; invariant I6).

The ledger added land extents alone, read in one place's notation. The papers of any matter state figures - areas in acres and
guntas or cents, square yards, feet or metres, or hectares, and sums of money - so code reads each in a measure whose units convert,
adds areas with areas and sums with sums giver by giver, and lists a share, a rate or a period as written. Where the model read a
figure too (research v13), code adds only a reading the paper's words bear, and one document reported twice is one transaction. The
writer v14 and the review v12 are told of it in the same terms. The papers, names and figures here are invented.
"""
import json
from fractions import Fraction

import pytest

from nm.core_engine import answer_sources, research, response_authorities, response_review, response_writer
from nm.core_engine.extents import ledger, parse, parse_money, read, render_value, shown
from tests.test_core_research import _result, proposal, understanding
from tests.test_the_chronology_of_each_document import SCRIPT, row
from tests.test_the_plan_records_the_chronology import Beside, bundle, sent
from tests.test_the_plan_records_the_transfers import SOLD, transfer
from tests.test_the_review_is_shown_the_chronology import Reviewer
from tests.test_the_writer_and_review_are_shown_copies_read_differently import quiet
from tests.test_the_writer_and_review_are_shown_the_land_extents import matter
from tests.test_the_writer_is_shown_the_chronology import Writer

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("words,guntas,how", [
    ("Ac.1.18 cents", Fraction(236, 5), "acres.cents"), ("Ac. 2-50 cts", 100, "acres.cents"),
    ("1 acre 18 cents", Fraction(236, 5), "acres and cents"), ("Acres 3 Guntas 12", 132, "acres and guntas"),
    ("Ac. 3 Gts. 12", 132, "acres and guntas"), ("Acres 1 Cents 50", 60, "acres and cents"), ("Guntas 12", 12, "guntas"),
    ("50 cents", 20, "cents"), ("Cents 25", 10, "cents"), ("1,089 sq. ft", 1, "square feet"), ("2,178 sft", 2, "square feet"),
    ("1,210 square yards", 10, "square yards"), ("4,046.8564224 sq. m", 40, "square metres")])
def test_an_area_is_read_in_the_units_the_papers_of_any_place_use(words, guntas, how):
    assert parse(words) == (Fraction(guntas), how)


def test_an_area_is_said_back_in_the_unit_its_papers_use():
    assert render_value("area", parse("Ac.1.18 cents")[0], "cents") == "1 acre 18 cents (Ac.1.18)"
    assert render_value("area", parse("1,210 square yards")[0], "square yards") == "1,210 square yards"
    assert render_value("area", parse("4,046.8564224 sq. m")[0], "square metres") == "4,046.86 square metres"
    assert render_value("area", parse("0.40 hectares")[0], "hectares") == "0.40 hectares"
    assert render_value("area", Fraction(58), None) == "1 acre 18 guntas (Ac.1.18)", "guntas where the papers say nothing else"


@pytest.mark.parametrize("words,rupees,how", [
    ("Rs.2,50,000/-", 250000, "rupees in figures"), ("Rs. 2.5 lakhs", 250000, "rupees in figures"),
    ("Rs. 1.5 crores", 15000000, "rupees in figures"), ("50,000 rupees", 50000, "rupees in figures"),
    ("INR 10,700", 10700, "rupees in figures"), ("Rupees Two Lakhs Fifty Thousand only", 250000, "rupees in words"),
    ("one hundred and five rupees", 105, "rupees in words"),
    ("Rs.2,50,000/- (Rupees Two Lakhs Fifty Thousand only)", 250000, "rupees, in figures and in words")])
def test_a_sum_of_money_is_read_in_figures_or_in_words(words, rupees, how):
    assert parse_money(words) == (Fraction(rupees), how)


@pytest.mark.parametrize("words,why", [
    ("Rs.2,50,000/- (Rupees Two Lakhs Five Thousand only)", "the figures and the words give different sums"),
    ("Rs.500 and Rs.600", "more than one sum in these words"), ("a sum agreed between them", "no sum of money in these words")])
def test_words_that_are_not_one_sum_are_not_read_and_say_why(words, why):
    assert parse_money(words) == (None, why)


def test_a_sum_is_said_as_indian_papers_write_it():
    assert [render_value("money", Fraction(value)) for value in (250000, 1050, Fraction("12500.50"), -15000000)] == [
        "Rs 2,50,000", "Rs 1,050", "Rs 12,500.50", "-Rs 1,50,00,000"]


@pytest.mark.parametrize("extent,reading,expected", [
    ("Ac.1.18", "1 acre 18 guntas", ("area", 58, "acres.guntas")),
    ("Ac.1.18", "1 acre 18 cents", ("area", Fraction(236, 5), "acres and cents, as AI read words code reads more than one way")),
    ("Ac.1.45", "1 acre 45 cents", ("area", 58, "acres and cents, as AI read words code reads more than one way")),
    ("Rs.2,50,000/-", "Rs 250000", ("money", 250000, "rupees in figures")),
    ("Acres Three and Guntas Twelve", "3 acres 12 guntas",
     ("area", 132, "acres and guntas, as read by AI from words code could not read; its numbers are the paper's"))])
def test_the_model_reads_a_figure_and_code_takes_a_reading_the_papers_words_bear(extent, reading, expected):
    measure, value, how, _ = read(extent, reading)
    assert (measure, value, how) == expected


@pytest.mark.parametrize("extent,reading,why", [
    ("Ac.1.18", "1 acre 21 guntas",
     "code reads 1 acre 18 guntas (Ac.1.18) and the reading given for it 1 acre 21 guntas (Ac.1.21): two readings"),
    ("Acres Three and Guntas Twelve", "3 acres 13 guntas",
     "no extent in these words; the reading given for it has numbers the paper's words do not"),
    ("Rs 4,750 per month", "Rs 4750 per month", "a rate, not a sum: code adds areas and sums of money only"),
    ("1/3rd share", "a one-third share", "a share of a whole: code adds areas and sums of money only"),
    ("for 11 months", "11 months", "a period of time: code adds areas and sums of money only")])
def test_a_figure_read_two_ways_or_that_code_does_not_add_is_never_added_and_says_why(extent, reading, why):
    assert read(extent, reading) == (None, None, why, None)


def test_a_record_without_a_reading_is_read_as_before():
    assert read("Ac.1.18", None) == ("area", 58, "acres.guntas", "guntas") and read("Rs.500", None)[0] is None


def deal(number, figure, *, reading="", words=None, subject="Loan account 12", giver="Bank of Somewhere", receiver="Tarun Mehra",
         kind="loan", total="", date="1-1-2010", sort="2010-01-01", document="loan.pdf", instrument=""):
    """A transaction as research v13 records it (invented): its figure as written, the model's reading of it, the number of the
    document that records it and the words that record it."""
    return {"id": f"X{number}", "parcel": subject, "extent": figure, "reading": reading, "total": total, "from": giver,
            "to": receiver, "date": date, "sort": sort, "kind": kind, "document": document, "pages": [1], "instrument": instrument,
            "words": words if words is not None else f"{figure} out of {total}" if total else figure, "anchored": True}


def test_money_lent_and_paid_is_added_giver_by_giver_and_set_against_the_stated_sum():
    rows = [deal(1, "Rs.2,00,000/-", total="Rs.2,00,000/-"),
            deal(2, "Rs.50,000", giver="Tarun Mehra", receiver="Bank of Somewhere", kind="payment", date="1-1-2011", sort="2011-01-01"),
            deal(3, "Rs.25,000", giver="Tarun Mehra", receiver="Bank of Somewhere", kind="payment", date="1-1-2012", sort="2012-01-01")]
    (account,) = ledger(rows)
    lender, borrower = account["sellers"]
    assert lender["added"] == {"money": 200000} and borrower["added"] == {"money": 75000} and account["complete"]
    (stated,) = account["totals"]
    assert (stated["measure"], stated["value"]) == ("money", 200000)
    assert stated["by_seller"] == [{"seller": "Bank of Somewhere", "leaves": 0, "exceeds": None},
                                   {"seller": "Tarun Mehra", "leaves": 125000, "exceeds": None}]
    (said,) = shown(rows)
    json.dumps(said)
    assert said["sellers"][1]["added"] == "Rs 75,000" and said["totals"][0]["by_seller"][1]["leaves"] == "Rs 1,25,000"
    assert said["sellers"][1]["transfers"][0]["as"] == "Rs 50,000" and said["totals"][0]["measure"] == "money"


def test_areas_and_sums_of_one_property_are_added_apart_and_each_whole_is_set_against_its_own_measure():
    rows = [deal(1, "Ac.1.00", words="sold Ac.1.00 out of Ac.4.00", subject="Sy.No.12", giver="Tarun Mehra", receiver="Nisha Kapur",
                 kind="sale", total="Ac.4.00", document="deed.pdf"),
            deal(2, "Rs.5,00,000", words="paid Rs.5,00,000 of the price of Rs.8,00,000", subject="Sy.No.12", giver="Nisha Kapur",
                 receiver="Tarun Mehra", kind="payment", total="Rs.8,00,000", document="deed.pdf"),
            deal(3, "Rs.20,000", words="Tarun Mehra lent Rs.20,000", subject="Sy.No.12", giver="Tarun Mehra", receiver="Nisha Kapur",
                 date="2-2-2010", sort="2010-02-02", document="deed.pdf")]
    (plot,) = ledger(rows)
    seller, buyer = plot["sellers"]
    assert seller["added"] == {"area": 40, "money": 20000} and buyer["added"] == {"money": 500000}
    area, money = plot["totals"]
    assert area["by_seller"] == [{"seller": "Tarun Mehra", "leaves": 120, "exceeds": None}]
    assert money["by_seller"] == [{"seller": "Tarun Mehra", "leaves": 780000, "exceeds": None},
                                  {"seller": "Nisha Kapur", "leaves": 300000, "exceeds": None}]
    (said,) = shown(rows)
    assert said["sellers"][0]["added"] == "1 acre (Ac.1.00); Rs 20,000", "areas first, then sums, never added together"


def test_a_figure_or_a_whole_not_in_the_words_that_record_it_is_not_used_and_one_written_another_way_is():
    (account,) = ledger([deal(1, "Rs.2,00,000/-", words="a loan was given", total="Rs.5,00,000")])
    assert account["sellers"] == [] and [(u["id"], u["why"]) for u in account["unread"]] == [
        ("X1", "its figure is not in the words that record it")]
    assert account["totals"][0]["value"] is None and account["totals"][0]["how"] == "its figure is not in the words that record it"
    (account,) = ledger([deal(1, "Rs.2,00,000/-", words="a loan of Rupees Two Lakhs only")])
    assert account["sellers"][0]["added"] == {"money": 200000}
    (plot,) = ledger([deal(1, "Ac.1.18", words="an extent of Ac 1-18 guntas", subject="Sy.No.12", kind="sale")])
    assert plot["sellers"][0]["added"] == {"area": 58}


def test_two_readings_that_differ_are_never_added_and_a_reading_that_settles_a_notation_is_added_in_its_unit():
    (plot,) = ledger([deal(1, "Ac.1.18", reading="1 acre 21 guntas", subject="Sy.No.12", kind="sale")])
    assert plot["sellers"] == [] and plot["unread"][0]["why"].endswith(": two readings") and not plot["complete"]
    (plot,) = shown([deal(1, "Ac.1.18", reading="1 acre 18 cents", subject="Sy.No.12", kind="sale")])
    assert plot["sellers"][0]["added"] == "1 acre 18 cents (Ac.1.18)" and plot["sellers"][0]["transfers"][0]["as"] == plot[
        "sellers"][0]["added"]


def test_a_share_is_listed_and_not_added_and_a_lease_or_mortgage_is_never_added():
    rows = [deal(1, "Ac.1.00", words="Ac.1.00 out of Ac.4.00", subject="Sy.No.12", giver="Tarun Mehra", kind="sale", total="Ac.4.00"),
            deal(2, "1/3rd share", reading="a one-third share", words="his 1/3rd share", subject="Sy.No.12", giver="Tarun Mehra",
                 kind="sale", date="2-2-2012", sort="2012-02-02"),
            deal(3, "Rs.4,750 per month", reading="Rs 4750 per month", words="a rent of Rs.4,750 per month", subject="Sy.No.12",
                 giver="Tarun Mehra", kind="lease", date="3-3-2013", sort="2013-03-03"),
            deal(4, "Rs.1,30,000", words="mortgaged for Rs.1,30,000", subject="Sy.No.12", giver="Tarun Mehra", kind="mortgage",
                 date="4-4-2014", sort="2014-04-04")]
    (plot,) = ledger(rows)
    (giver,) = plot["sellers"]
    assert giver["added"] == {"area": 40} and not plot["complete"]
    assert [(u["id"], u["why"]) for u in plot["unread"]] == [("X2", "a share of a whole: code adds areas and sums of money only")]
    assert [(t["kind"], t["value"]) for t in giver["not_added"]] == [("lease", None), ("mortgage", 130000)]
    assert plot["totals"][0]["by_seller"] == [], "no remainder while a sale is not added"
    (said,) = shown(rows)
    assert [t["why"] for t in said["sellers"][0]["not_added"]] == [
        "a lease passes possession for a time, not what the owner holds", "a mortgage is security for a debt, not a sale"]


def test_one_document_reported_twice_is_one_transaction_and_reported_with_another_giver_is_linked_and_added_once():
    # Plan AN.28, B16 (invented): a deed by its number, in a paper that gives it another date and buyer's spelling, and in one that
    # names another giver for it.
    deed = deal(1, "Ac.2.00", subject="Sy.No.12", giver="Tarun Mehra", receiver="Nisha Kapur", kind="sale",
                instrument="Doc No. 1234/2001", document="deed.pdf")
    again = deal(2, "Ac.2.00", subject="Sy.No.12", giver="Tarun Mehra", receiver="N. Kapur", kind="sale",
                 instrument="Sale Deed No. 1234 of 2001", document="order.pdf", date="undated", sort="")
    rival = deal(3, "Ac.2.00", subject="Sy.No.12", giver="Imran Qadri", receiver="Nisha Kapur", kind="sale",
                 instrument="Doc. No. 1234/2001", document="plaint.pdf")
    (plot,) = ledger([deed, again, rival])
    first, second = plot["sellers"]
    assert first["names"] == ["Tarun Mehra"] and first["transfers"][0]["ids"] == ["X1", "X2"] and first["added"] == {"area": 80}
    assert second["names"] == ["Imran Qadri"] and second["transfers"] == [] and second["added"] == {}
    (linked,) = second["not_added"]
    assert (linked["twin_of"], linked["instrument"]) == ("X1", "Doc. No. 1234/2001")
    (said,) = shown([deed, again, rival])
    assert said["sellers"][1]["not_added"][0]["why"] == (
        "the same document (Doc. No. 1234/2001) as X1, which another paper reports with another giver: added once, there")


def test_two_documents_of_different_numbers_are_two_transactions_however_alike():
    (plot,) = ledger([deal(1, "Ac.2.00", subject="Sy.No.12", kind="sale", instrument="Doc No. 1234/2001"),
                      deal(2, "Ac.2.00", subject="Sy.No.12", kind="sale", instrument="Doc No. 1235/2001", document="deed2.pdf")])
    assert len(plot["sellers"][0]["transfers"]) == 2 and plot["sellers"][0]["added"] == {"area": 160}
    (plot,) = ledger([deal(1, "Ac.2.00", subject="Sy.No.12", kind="sale"),
                      deal(2, "Ac.2.00", subject="Sy.No.12", kind="sale", document="deed2.pdf")])
    assert len(plot["sellers"][0]["transfers"]) == 1, "without numbers, the same date, figure and receiver are one, as before"


def test_the_v13_transactions_prompt_is_for_any_matter_and_each_paper_is_read_with_the_whole_file_in_view():
    prompt = " ".join(research.TRANSACTIONS_V13.split())
    for part in ("Message:", "Purpose:", "Look for:", "Outcome:", "whatever moves property, money, shares, goods or a right",
                 "so that code can add the figures up for each property, account or subject", "You are not adding or working out",
                 "reading:", "instrument", "Work in a loop", "do not add or work out a figure the page does not give"):
        assert part in prompt, part
    assert research.TRANSACTION_KINDS == ("sale", "partition", "gift", "settlement", "decree", "lease", "mortgage", "loan", "payment",
                                          "other")
    model = Beside(SCRIPT, transfers=SOLD)
    research.transfers_of(model, bundle())
    reads = [prompt for prompt in model.calls if prompt.operation == "core_research_transfers" and '"to_check"' not in prompt.user]
    assert len(reads) == 2 and all(prompt.system == research.TRANSACTIONS_V13 for prompt in reads)
    for prompt in reads:
        mine, rest = prompt.user.split("The pages you read for:")[1], prompt.user.split("The pages you read for:")[0]
        other = "order.pdf" if 'Document: "deed.pdf"' in mine else "deed.pdf"
        assert f'Paper "{other}"' in rest and "The advocate's messages, oldest first:" in rest


def test_the_writer_v14_and_the_review_v12_are_shown_the_figures_in_general_terms_and_v13_keeps_its_own():
    ctx, record, sources = matter()
    model = Writer(quiet)
    draft = response_writer.write_section(model, ctx, record, sources, index=0, contract=response_writer.REPAIRED_CONTRACT)
    prompt, payload = model.seen[0]
    assert prompt.system == response_writer.SYSTEM_V14 and "land_extents" not in payload
    assert [p["parcel"] for p in payload["figures_added"]] == ["Sy.No.487", "Sy.No.487/A"]
    reviewer = Reviewer()
    response_review.review(reviewer, ctx, record, sources, draft, research.execution(record),
                           authority_evidence=response_authorities.check(ctx, record, sources, draft),
                           contract=response_review.WORDED_CONTRACT)
    assert reviewer.seen[0][1]["figures_added"] == payload["figures_added"] and "land_extents" not in reviewer.seen[0][1]
    writer = " ".join(response_writer.SYSTEM_V14.split())
    for part in ("Counting is code's work for figures as it is for days: do not add, subtract or convert areas, sums of money or any "
                 "other figures yourself", "Where figures_added is given, code added up the transactions NM found in the papers",
                 "the seller, donor, settlor, lender or payer - areas with areas and sums of money with sums of money",
                 "use a giver's added", "never add one giver's figures to another's",
                 "never what anyone holds, owes or has paid", "Name no remainder for a property or account whose complete is false"):
        assert part in writer, part
    assert "guntas" not in response_writer.SYSTEM_V14 and "land_extents" in response_writer.SYSTEM_V13
    review = " ".join(response_review.SYSTEM_V12.split())
    assert "Where figures_added is given, code added up the transactions NM found, giver by giver" in review
    assert "not as what anyone holds, owes or has paid, and never as a sum across givers" in review
    assert answer_sources.build(ctx, record) == sources


class LooksAgain(Beside):
    """A reader of transactions whose look again gives what `again` gives for its paper."""

    def __init__(self, first, again):
        super().__init__({}, transfers=first)
        self.again = again

    def structured(self, prompt, schema, tier, **kwargs):
        if prompt.operation == "core_research_transfers" and '"to_check"' in prompt.user:
            self.calls.append(prompt)
            return _result({"transfers": self.again.get(prompt.user.split('"')[1], [])}, tier)
        return super().structured(prompt, schema, tier, **kwargs)


PLOT = [row("t1", 1, "deed.pdf", 1, "Sale Deed No. 77 of 2003 dated 5-6-2003. The vendor sold an extent of Ac.1.18 guntas out of "
                                    "Ac.4.00 in Sy.No.12 to the purchaser for Rs.2,00,000.")]


def sale(extent, words, *, total="", reading="", date="5-6-2003"):
    return {**transfer(date, "Sy.No.12", extent, words, total=total, to="the purchaser"), "reading": reading,
            "instrument": "Sale Deed No. 77 of 2003"}


def test_a_transaction_code_cannot_use_is_looked_at_again_once_and_what_the_look_gives_is_kept():
    # Invented: the figure given is not the page's; looked at again, the model gives the page's own.
    model = LooksAgain({"deed.pdf": [sale("Ac.1.21", "The vendor sold an extent of Ac.1.18 guntas", reading="1 acre 21 guntas")]},
                       {"deed.pdf": [sale("Ac.1.18 guntas", "The vendor sold an extent of Ac.1.18 guntas out of Ac.4.00",
                                          total="Ac.4.00", reading="1 acre 18 guntas")]})
    (kept,), failures = research.transfers_of(model, sent(*PLOT))
    checked, = [prompt for prompt in model.calls if '"to_check"' in prompt.user]
    assert checked.system == research.TRANSACTIONS_CHECK and "code reads 1 acre 21 guntas (Ac.1.21)" not in checked.user
    assert '"why": "its figure is not in the words that record it"' in checked.user and failures == []
    assert (kept["extent"], kept["total"], kept["anchored"]) == ("Ac.1.18 guntas", "Ac.4.00", True)
    (plot,) = ledger([kept])
    assert plot["sellers"][0]["added"] == {"area": 58} and plot["totals"][0]["by_seller"][0]["leaves"] == 102


def test_a_transaction_still_at_fault_is_kept_listed_and_never_added_and_a_date_its_paper_lacks_is_dropped():
    first = [sale("Rs.3,00,000", "The vendor sold an extent of Ac.1.18 guntas", reading="Rs 300000", date="9-9-2009")]
    model = LooksAgain({"deed.pdf": first}, {"deed.pdf": first})
    (kept,), _ = research.transfers_of(model, sent(*PLOT))
    assert kept["date"] == "undated" and kept["sort"] == "", "a date on no page of its paper is not kept"
    (plot,) = ledger([kept])
    assert plot["sellers"] == [] and plot["unread"][0]["why"] == "its figure is not in the words that record it"


def test_a_paper_whose_transactions_all_check_out_needs_no_look_again():
    model = LooksAgain({"deed.pdf": [sale("Ac.1.18 guntas", "The vendor sold an extent of Ac.1.18 guntas out of Ac.4.00",
                                          total="Ac.4.00", reading="1 acre 18 guntas")]}, {})
    research.transfers_of(model, sent(*PLOT))
    assert not [prompt for prompt in model.calls if '"to_check"' in prompt.user]


def test_the_look_again_prompt_says_what_code_found_and_asks_for_the_pages_own_words():
    prompt = " ".join(research.TRANSACTIONS_CHECK.split())
    for part in ("Message:", "Purpose:", "Outcome:", "whose figure or whole is not in those words",
                 "whose figure code reads otherwise than your reading of it", "copied exactly from the page as they stand",
                 "so that it reads only one way", "or leave it out if the paper does not record it as you listed it", "Work in a loop"):
        assert part in prompt, part
    assert research.MAX_OUTPUT["transfers_check"] == 8000



def test_the_v13_understanding_names_the_client_the_parties_parts_and_the_subjects_each_with_words_code_finds():
    # Plan AN.28, piece 3d (findings A1 and B12), invented: whom the advocate acts for, each party's part in each proceeding the papers
    # name, and every subject they identify.
    prompt = " ".join(research.UNDERSTAND.split())
    for part in ("whether each is the advocate's client or one of the client's people (client)",
                 "each person's part in it (who brought it, who answers it, who else is joined), with the page's own words (parts)",
                 "Every subject of the matter the papers identify - a property, an account, a contract, a policy, a case or a document",
                 "so that none is overlooked"):
        assert part in prompt, part
    assert "Is anyone's part in a proceeding the papers name, or a subject the papers identify, missed or misread?" in " ".join(
        research.CHECK.split())
    wire = research.UNDERSTANDING_V13["properties"]
    assert set(wire["parties"]["items"]["required"]) == {"who", "role", "client", "parts"} and "subjects" in research.UNDERSTANDING_V13["required"]
    subject = understanding()
    subject["parties"] = [{"who": "the vendor", "role": "seller", "client": True,
                           "parts": [{"proceeding": "O.S. 17 of 2019", "part": "defendant", "words": "the vendor as defendant"}]}]
    subject["subjects"] = [{"identifier": "Sy.No.12", "what": "the land sold", "words": "the land in Sy.No.12"},
                           {"identifier": "A/c 9466", "what": "a loan account", "words": "loan account No. 9466"}]
    ctx = sent(row("t1", 1, "plaint.pdf", 1, "Suit O.S. 17 of 2019 is against the vendor as defendant over the land in Sy.No.12."))
    problems = research.code_checks(subject, ctx)
    assert [p["problem"].split(",")[0] for p in problems] == ["For the subject A/c 9466"], "only the words no page holds are refused"
    assert research.accept({**proposal(), "understanding": subject}, ctx)["proposal"]["understanding"]["subjects"][0]["identifier"] == "Sy.No.12"
    older = proposal()["understanding"]
    assert "subjects" not in older and research.accept(proposal(), ctx)["proposal"]["understanding"] == older, \
        "an understanding without them is kept as one that gives none"
