"""An extent a model worked out is not kept in the understanding (plan AN.27, P23, part A; invariants I6 and S13).

The replay of the reviewed bundle's first turn showed a model's arithmetic on extents outside the ledger: the understanding wrote that
two passbooks "total" an extent whose guntas were over 39, called the difference from a third paper a discrepancy, and the slip went into
a fact and a line of what is missing and then into the answer. 40 guntas make an acre, and counting is code's work (extents.py adds the
papers' transfers of land). NM's own mechanical check of the understanding now refuses, in words to the model that wrote it, an extent
that neither the advocate's messages nor the documents they sent give - one whose notation no paper can use included - so that the one
revision the loop allows leaves it out. An extent is the same extent in whatever notation it is written. The papers and figures here
are synthetic.
"""
from fractions import Fraction

import pytest

from nm.core_engine import extents, research
from nm.core_engine.research import EXTENT_FIX, plan
from tests.test_core_research import Model, operations, proposal, understanding
from tests.test_core_understanding import context as turn

pytestmark = pytest.mark.class_a

SAID = ("Find the applicable law. The first passbook shows 25 guntas and the second 30 guntas. The purchase deed is for Ac.1.10 guntas "
        "of the survey number.")
DEED = "Registered sale deed. The vendor conveys Ac.2-30 gts out of the whole 6.05 acres. The plot is 242 sq. yds."
WORKED_OUT = "a total of Ac.5.05 guntas"


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


def test_a_total_whose_guntas_are_forty_or_more_is_refused_to_the_model_that_wrote_it():
    (found,) = refused("The passbooks of 25 and 30 guntas total Ac.0.55, not Ac.1.10, so the figures do not agree.")
    assert "'Ac.0.55'" in found["problem"] and "(fact F1)" in found["problem"] and "40 guntas make an acre" in found["problem"]
    assert "Ac.1.10" not in found["problem"] and "25 guntas" not in found["problem"], "what the deed and the passbooks give is not refused"
    assert found["fix"] == EXTENT_FIX and "Do not work out an extent or a sum yourself" in found["fix"]
    assert "copied as it stands" in found["fix"]


@pytest.mark.parametrize("words,shown", [("the passbooks come to 55 guntas", "55 guntas"), ("the passbooks come to Ac.1.15", "Ac.1.15"),
                                         ("together they hold 1 acre 15 guntas", "1 acre 15 guntas"), ("about 1.15 acres", "1.15 acres"),
                                         ("they come to Ac.1.15\n guntas", "Ac.1.15 guntas")])
def test_a_total_in_a_notation_a_paper_can_use_is_refused_all_the_same_when_no_paper_gives_it(words, shown):
    (found,) = refused(words)
    assert "is in none of the advocate's messages or the documents they sent" in found["problem"] and "worked out" in found["problem"]
    assert "40 guntas make an acre" not in found["problem"]
    assert f"'{shown}'" in found["problem"], "the extent is quoted back as it is written, on one line"
    assert found["fix"] == EXTENT_FIX


def test_an_extent_the_papers_give_is_not_refused_in_any_notation_it_is_written():
    ctx = papers(page("deed.pdf", 3, DEED))
    text = ("The first passbook is Ac.0.25 and the second 30 gts; the deed is for 1 acre 10 guntas (1.10 acres, 50 guntas); the vendor "
            "conveys 2 acres 30 guntas (110 guntas, Ac.2.30) out of 6 acres 5 guntas (Ac.6.05, 245 guntas); the plot is 2 guntas, or "
            "242 square yards.")
    assert refused(text, ctx) == []


def test_the_advocates_earlier_messages_the_latest_one_and_every_page_give_extents_and_nothing_else_does():
    said = "Find the applicable law. The deed is for Ac.1.10 guntas."
    earlier, deed = ("My client sold Ac.0.35 guntas years ago.",), page("register.pdf", 2, "The register shows 3 acres 15 guntas.")
    text = "The client sold Ac.0.35, the deed is for Ac.1.10 and the register shows Ac.3.15."
    assert refused(text, papers(deed, said=said, earlier=earlier)) == []
    for left, ctx in (("Ac.0.35", papers(deed, said=said)), ("Ac.1.10", papers(deed, said="Find the applicable law.", earlier=earlier)),
                      ("Ac.3.15", papers(said=said, earlier=earlier))):
        (found,) = refused(text, ctx)
        assert f"'{left}'" in found["problem"], f"{left} is given by only one source"


def test_a_note_of_our_own_and_the_records_of_the_matter_are_not_messages_or_papers():
    ctx = papers(said="Find the applicable law.", more={
        "conversation": [{"speaker": "nm", "record_role": "nm_interpretation", "text": "The deed is for Ac.5.20 guntas."}],
        "current_records": {"plan": "The deed is for Ac.5.20 guntas."}})
    (found,) = refused("The deed is for Ac.5.20 guntas.", ctx)
    assert "'Ac.5.20 guntas'" in found["problem"]


def test_an_extent_no_paper_can_write_is_let_through_when_a_paper_itself_writes_it_in_those_figures():
    ctx = papers(page("register.pdf", 1, "The old register shows Ac.0.45 against the plot."))
    assert refused("The register shows Ac.0.45 against the plot.", ctx) == []
    assert refused("The register shows ac.0.45 guntas against the plot.", ctx) == [], "the same figures, however they are set"
    (found,) = refused("The register shows Ac.0.46 against the plot.", ctx)
    assert "'Ac.0.46'" in found["problem"] and "40 guntas make an acre" in found["problem"]


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
    assert f"({place})" in found["problem"] and "'Ac.5.05 guntas'" in found["problem"]


def test_a_quotation_is_left_to_its_own_check():
    subject = stating("A purchase.")
    subject["facts"][0]["advocate_words"] = "The first passbook shows 25 guntas"
    assert research.code_checks(subject, papers()) == [], "words the advocate said are quoted as they are"
    subject["facts"][0]["advocate_words"] = "total Ac.7.00 guntas"
    (found,) = research.code_checks(subject, papers())
    assert "do not appear" in found["problem"] and "Ac.7.00" in found["problem"], "refused once, as a quotation, and not again as an extent"
    assert found["fix"].startswith("Quote the exact words")


def test_each_extent_is_refused_once_with_every_place_it_is_stated_and_the_first_words_it_was_written_in():
    subject = stating("The passbooks total Ac.1.15 and come to 55 guntas.")
    put(subject, ("summary",), "A dispute over 55 guntas.")
    put(subject, ("disputes", 0, "legal_questions", 0, "question"), "Is a holding of 1 acre 15 guntas affected?")
    put(subject, ("related_points", 0, "point"), "A sale of Ac.9.00 guntas.")
    first, second = research.code_checks(subject, papers())
    assert "'55 guntas'" in first["problem"] and "(the summary, fact F1, legal question D1Q1)" in first["problem"]
    assert "'Ac.9.00 guntas'" in second["problem"] and "(the related points)" in second["problem"]


def test_numbers_that_are_not_extents_are_not_read_as_extents():
    text = ("The sale of survey number 12/3 under section 4.10 of the Act, registered on 12.10.2020 as document 55/2020, "
            "and a fee of 2.5 per cent was paid on the 14th.")
    assert refused(text) == []


def test_a_sum_the_model_worked_out_is_refused_as_an_extent_is_and_one_the_papers_give_is_not_in_any_notation():
    # Plan AN.28, D7 (invented): counting is code's work for sums of money as for extents.
    ctx = papers(page("deed.pdf", 3, "The price agreed is Rs.7,40,000/- (Rupees Seven Lakhs Forty Thousand only), of which Rs.2,10,000 "
                                     "was paid."))
    assert refused("The price was Rs. 7.4 lakhs, of which Rupees Two Lakhs Ten Thousand were paid.", ctx) == []
    (found,) = refused("The price was Rs.7,40,000, so Rs.5,30,000 remains to be paid.", ctx)
    assert "the sum 'Rs.5,30,000' (fact F1)" in found["problem"] and "worked out" in found["problem"] and found["fix"] == EXTENT_FIX
    assert research.code_checks(stating("A purchase."), papers()) == [], "an understanding with no extent is not touched"


def test_the_extents_are_read_by_the_extents_module_and_no_other_way():
    found = research._extents_written("Ac.1.10 guntas,  242 sq. yds and\nAc.0.55")
    assert [(words, value) for words, value, _ in found] == [("Ac.1.10 guntas", Fraction(50)), ("242 sq. yds", Fraction(2)),
                                                             ("Ac.0.55", None)]
    assert all(extents.parse(words)[0] == value for words, value, _ in found), "the same reading as the ledger's"
    assert found[0][2] == Fraction(50) and found[2][2] == (0, 55), "an extent no paper can write is itself by its figures"


def test_the_refusal_reaches_the_revising_step_and_the_revised_understanding_is_kept():
    slip = stating("The passbooks of 25 and 30 guntas total Ac.0.55, not Ac.1.10.")
    fixed = stating("The passbooks show 25 and 30 guntas and the purchase deed Ac.1.10 guntas.")
    model = Model(slip, revisions=[fixed])
    admitted = plan(model, turn(SAID))
    assert operations(model)[:4] == ["core_research_understand", "core_research_check", "core_research_revise", "core_research_check"]
    revising = next(prompt for prompt in model.calls if prompt.operation == "core_research_revise").user
    assert "Ac.0.55" in revising and EXTENT_FIX in revising, "the model that wrote it is told, in words"
    first, last = admitted["proposal"]["review_rounds"]
    assert len(first["code_problems"]) == 1 and last["code_problems"] == []
    assert admitted["proposal"]["understanding"] == fixed and admitted["issues"] == []


def test_a_revision_that_keeps_the_total_leaves_the_problem_open_in_the_record():
    slip = stating("The passbooks of 25 and 30 guntas total Ac.0.55, not Ac.1.10.")
    admitted = plan(Model(slip, revisions=[slip] * research.MAX_REVISIONS), turn(SAID))
    assert any("open problems" in issue["mismatch"] for issue in admitted["issues"])
    assert "Ac.0.55" in admitted["proposal"]["review_rounds"][-1]["code_problems"][0]["problem"]


def test_a_saved_plan_is_picked_up_as_it_was_saved():
    saved = proposal()
    saved["understanding"]["facts"][0]["fact"] = "The passbooks total Ac.0.55."
    admitted = research.accept(saved, turn("Find the applicable law."))
    assert admitted["issues"] == [] and admitted["proposal"]["understanding"]["facts"][0]["fact"] == "The passbooks total Ac.0.55."
