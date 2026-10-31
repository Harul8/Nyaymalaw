"""A figure a model worked out is not kept in the understanding (plan AN.27, P23, part A; AN.29, D9; invariants I6 and S13).

The replay of the reviewed bundle's first turn showed a model's arithmetic outside the ledger: the understanding wrote that two papers
"total" a figure, called the difference from a third paper a discrepancy, and the slip went into a fact and a line of what is missing and
then into the answer. Counting is code's work (figures.py adds the papers' transactions). NM's own mechanical check of the understanding
now refuses, in words to the model that wrote it, a figure - a number against a unit of the table of units - that neither the advocate's
messages nor the documents they sent give, so that the one revision the loop allows leaves it out. A figure is the same figure in whatever
unit of its kind it is written. The papers and figures here are synthetic.
"""
import pytest

from nm.core_engine import figures, research
from nm.core_engine.research import FIGURE_FIX, plan
from tests.test_core_research import Model, operations, proposal, understanding
from tests.test_core_understanding import context as turn

pytestmark = pytest.mark.class_a

SAID = ("Find the applicable law. The first invoice shows 25 kg and the second 30 kg. The purchase agreement is for 110 kg of grain "
        "from the warehouse.")
AGREEMENT = "Registered supply agreement. The supplier delivers 1.1 quintals out of the whole 6.05 tonnes. The yard is 242 sq. yds."
WORKED_OUT = "a total of 495 kg"


def page(name, number, text):
    return {"source_id": f"{name}:p{number}", "text": text, "document": {"name": name, "page": number, "read_by": "ai"}}


def papers(*pages, said=SAID, earlier=(), more=None):
    rows = [{"speaker": "advocate", "record_role": "original_account", "text": text} for text in earlier]
    return {"conversation": rows, "latest": {"text": said}, "documents": list(pages), **(more or {})}


def put(subject, path, text):
    *route, last = path
    holder = subject
    for step in route:
        holder = holder[step]
    if isinstance(holder[last], list):
        holder[last].append(text)
    else:
        holder[last] = text
    return subject


def stating(text, path=("facts", 0, "fact")):
    """The test_core_research understanding, with one related point, and some words of its own in one place."""
    subject = understanding()
    subject["related_points"] = [{"point": "Registration of the sale.", "why_it_matters": "It proves the sale.", "dispute_id": "D1"}]
    return put(subject, path, text)


def refused(text, ctx=None, path=("facts", 0, "fact")):
    return research.code_checks(stating(text, path), ctx or papers())


def test_a_total_nobody_gave_is_refused_to_the_model_that_wrote_it():
    (found,) = refused("The invoices of 25 and 30 kg total 55 kg, not 110 kg, so the figures do not agree.")
    assert "'55 kg'" in found["problem"] and "(fact F1)" in found["problem"]
    assert "is in none of the advocate's messages or the documents they sent" in found["problem"] and "worked out" in found["problem"]
    assert "110 kg" not in found["problem"] and "30 kg" not in found["problem"], "what the agreement and the invoices give is not refused"
    assert found["fix"] == FIGURE_FIX and "Do not work out a figure yourself" in found["fix"] and "copied as it stands" in found["fix"]


@pytest.mark.parametrize("words,shown", [("the invoices come to 55 kg", "55 kg"), ("together they hold 0.055 tonnes", "0.055 tonnes"),
                                         ("they come to 55\n kg", "55 kg"), ("a payment of Rs.1,730", "Rs.1,730")])
def test_a_figure_is_refused_in_whatever_unit_it_is_written_when_no_paper_gives_it(words, shown):
    (found,) = refused(words)
    assert f"'{shown}'" in found["problem"], "the figure is quoted back as it is written, on one line"
    assert found["fix"] == FIGURE_FIX


def test_a_figure_the_papers_give_is_not_refused_in_any_unit_of_its_kind_it_is_written():
    ctx = papers(page("agreement.pdf", 3, AGREEMENT))
    text = ("The first invoice is 25 kg and the second 30 kg; the agreement is for 110 kg (1.1 quintals, 0.11 tonnes); the supplier "
            "delivers 110000 grams out of 6050 kg (6.05 tonnes, 60.5 quintals); the yard is 242 square yards.")
    assert refused(text, ctx) == []


def test_the_advocates_earlier_messages_the_latest_one_and_every_page_give_figures_and_nothing_else_does():
    said = "Find the applicable law. The agreement is for 110 kg."
    earlier, register = ("My client sold 35 kg years ago.",), page("register.pdf", 2, "The register shows 315 kg.")
    text = "The client sold 35 kg, the agreement is for 110 kg and the register shows 315 kg."
    assert refused(text, papers(register, said=said, earlier=earlier)) == []
    for left, ctx in (("35 kg", papers(register, said=said)), ("110 kg", papers(register, said="Find the applicable law.", earlier=earlier)),
                      ("315 kg", papers(said=said, earlier=earlier))):
        (found,) = refused(text, ctx)
        assert f"'{left}'" in found["problem"], f"{left} is given by only one source"


def test_a_note_of_our_own_and_the_records_of_the_matter_are_not_messages_or_papers():
    ctx = papers(said="Find the applicable law.", more={
        "conversation": [{"speaker": "nm", "record_role": "nm_interpretation", "text": "The agreement is for 520 kg."}],
        "current_records": {"plan": "The agreement is for 520 kg."}})
    (found,) = refused("The agreement is for 520 kg.", ctx)
    assert "'520 kg'" in found["problem"]


def test_a_sum_of_money_the_model_worked_out_is_refused_as_any_figure_is_and_one_the_papers_give_is_not_in_any_notation():
    # Plan AN.28, D7 (invented): counting is code's work for sums of money as for quantities.
    ctx = papers(page("agreement.pdf", 3, "The price agreed is Rs.7,40,000/- (Rupees Seven Lakhs Forty Thousand only), of which Rs.2,10,000 "
                                          "was paid."))
    assert refused("The price was Rs. 7.4 lakhs, of which Rupees Two Lakhs Ten Thousand were paid.", ctx) == [], \
        "Rs. 7.4 lakhs is the amount Rs.7,40,000 is"
    (found,) = refused("The price was Rs.7,40,000, so Rs.5,30,000 remains to be paid.", ctx)
    assert "the figure 'Rs.5,30,000' (fact F1)" in found["problem"] and "worked out" in found["problem"] and found["fix"] == FIGURE_FIX
    assert research.code_checks(stating("A purchase."), papers()) == [], "an understanding with no figure is not touched"


PLACES = [
    (("summary",), "the summary"), (("asked",), "what was asked"), (("ruled_out",), "what was ruled out"),
    (("no_research_reason",), "the reason given for no research"), (("parties", 0, "role"), "the parties"),
    (("facts", 0, "fact"), "fact F1"),
    (("disputes", 0, "name"), "dispute D1"), (("disputes", 0, "why_it_matters"), "dispute D1"),
    (("disputes", 0, "rights_at_stake"), "dispute D1"), (("disputes", 0, "relief_sought"), "dispute D1"),
    (("disputes", 0, "missing_facts"), "dispute D1"),
    (("disputes", 0, "legal_questions", 0, "question"), "legal question D1Q1"),
    (("disputes", 0, "legal_questions", 0, "why_needed"), "legal question D1Q1"),
    (("disputes", 0, "legal_questions", 0, "open_alternative"), "legal question D1Q1"),
    (("disputes", 0, "legal_questions", 0, "law_to_check"), "legal question D1Q1"),
    (("related_points", 0, "point"), "the related points"), (("related_points", 0, "why_it_matters"), "the related points"),
]


@pytest.mark.parametrize("path,place", PLACES, ids=[".".join(str(step) for step in path) for path, _ in PLACES])
def test_every_place_in_the_understanding_is_read_and_named(path, place):
    (found,) = refused(WORKED_OUT, path=path)
    assert f"({place})" in found["problem"] and "'495 kg'" in found["problem"]


def test_a_quotation_is_left_to_its_own_check():
    subject = stating("A purchase.")
    subject["facts"][0]["advocate_words"] = "The first invoice shows 25 kg"
    assert research.code_checks(subject, papers()) == [], "words the advocate said are quoted as they are"
    subject["facts"][0]["advocate_words"] = "total 700 kg"
    (found,) = research.code_checks(subject, papers())
    assert "do not appear" in found["problem"] and "700 kg" in found["problem"], "refused once, as a quotation, and not again as a figure"
    assert found["fix"].startswith("Quote the exact words")


def test_each_figure_is_refused_once_with_every_place_it_is_stated_and_the_first_words_it_was_written_in():
    subject = stating("The invoices total 115 kg and come to 115 kg.")
    put(subject, ("summary",), "A dispute over 115 kg.")
    put(subject, ("disputes", 0, "legal_questions", 0, "question"), "Is a holding of 115 kg affected?")
    put(subject, ("related_points", 0, "point"), "A sale of 900 kg.")
    first, second = research.code_checks(subject, papers())
    assert "'115 kg'" in first["problem"] and "(the summary, fact F1, legal question D1Q1)" in first["problem"]
    assert "'900 kg'" in second["problem"] and "(the related points)" in second["problem"]


def test_numbers_that_are_not_figures_are_not_read_as_figures():
    text = ("The sale of lot number 12/3 under section 4.10 of the Act, registered on 12.10.2020 as document 55/2020, "
            "and a fee of 2.5 per cent was paid on the 14th.")
    assert refused(text) == []


def test_the_figures_are_found_by_the_figures_module_and_no_other_way():
    text = "110 kg,  242 sq. yds and\n55 kg and Rs.1,730"
    found = figures.quantities_in(" ".join(text.split()))
    assert [(words, unit) for words, _, unit in found] == [("110 kg", "kilogram"), ("242 sq. yds", "square_yard"),
                                                           ("55 kg", "kilogram"), ("Rs.1,730", "rupee")]
    problems = refused(text)
    assert [problem["problem"].split("'")[1] for problem in problems] == ["242 sq. yds", "55 kg", "Rs.1,730"], \
        "the figures the papers give (110 kg) are not refused, however the text is spaced"


def test_the_refusal_reaches_the_revising_step_and_the_revised_understanding_is_kept():
    slip = stating("The invoices of 25 and 30 kg total 55 kg, not 110 kg.")
    fixed = stating("The invoices show 25 and 30 kg and the purchase agreement 110 kg.")
    model = Model(slip, revisions=[fixed])
    admitted = plan(model, turn(SAID))
    assert operations(model)[:4] == ["core_research_understand", "core_research_check", "core_research_revise", "core_research_check"]
    revising = next(prompt for prompt in model.calls if prompt.operation == "core_research_revise").user
    assert "55 kg" in revising and FIGURE_FIX in revising, "the model that wrote it is told, in words"
    first, last = admitted["proposal"]["review_rounds"]
    assert len(first["code_problems"]) == 1 and last["code_problems"] == []
    assert admitted["proposal"]["understanding"] == fixed and admitted["issues"] == []


def test_a_revision_that_keeps_the_total_leaves_the_problem_open_in_the_record():
    slip = stating("The invoices of 25 and 30 kg total 55 kg, not 110 kg.")
    admitted = plan(Model(slip, revisions=[slip] * research.MAX_REVISIONS), turn(SAID))
    assert any("open problems" in issue["mismatch"] for issue in admitted["issues"])
    assert "55 kg" in admitted["proposal"]["review_rounds"][-1]["code_problems"][0]["problem"]


def test_a_saved_plan_is_picked_up_as_it_was_saved():
    saved = proposal()
    saved["understanding"]["facts"][0]["fact"] = "The invoices total 55 kg."
    admitted = research.accept(saved, turn("Find the applicable law."))
    assert admitted["issues"] == [] and admitted["proposal"]["understanding"]["facts"][0]["fact"] == "The invoices total 55 kg."
