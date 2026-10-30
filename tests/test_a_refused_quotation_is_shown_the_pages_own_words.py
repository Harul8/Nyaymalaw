"""A quotation the check refuses is shown the page's own words nearest to it (plan AN.27, P21; invariants I1 and I4).

NM's own check of its reading never reached "sound" in the replay of the reviewed bundle's first turn, and the code's exact-words check
was all of what it raised. The check already reads the words inside a fact's quotation marks, and it was right to refuse what it
refused: in one fact the model had written a passive as an active inside the marks ("the Tahsildar was directed to implement" quoted
as "directed the Tahsildar to implement"), in another it had mended a letter the scan misread ("lssue" quoted as "Issue"). The message
said where the quotation stopped matching but not what the page says there, and two rounds of revision left both as they were. The
message now also gives the page's own words around the longest run of the quotation that a page does hold, so that what is quoted
next can be copied. Nothing is loosened: a quotation is found exactly or it is not. The papers here are synthetic.
"""
import pytest

from nm.core_engine import research
from nm.core_engine.research import Pages

pytestmark = pytest.mark.class_a

PASSIVE = ("The respondents contend that the revenue officials acted within their powers. Having heard the parties, the Revenue Divisional "
           "Officer passed a well-considered order and the Tahsildar was directed to implement the name of these respondents for an "
           "extent of Ac.1.18 guntas (each Ac.0.29 guntas) in Survey No. 100 of the village, and the appeal was dismissed.")
SLIP = ("Learned Government Advocate accept$ notice on behalf of the State.\nlssue notice to private respondents returnable within six "
        "weeks.\nProcess fee to be paid within seven days.\nList the matter on the date fixed.")


def page(name, number, text):
    return {"source_id": f"{name}:p{number}", "text": text, "document": {"name": name, "page": number, "read_by": "ai"}}


def context(*pages, said="Please read the papers."):
    return {"conversation": [], "latest": {"text": said}, "documents": list(pages)}


def facts(words):
    return {"facts": [{"id": "F1", "fact": "A direction.", "advocate_words": words, "certainty": "reported"}],
            "disputes": [], "related_points": [], "needs_research": False}


def problem_for(words, *pages):
    (problem,) = research.code_checks(facts(words), context(*pages))
    return problem


def test_words_that_make_a_passive_active_inside_the_marks_are_refused_and_the_pages_own_words_are_shown():
    found = problem_for('The RDO “directed the Tahsildar to implement the name of these respondents for an extent of Ac.1.18 guntas”',
                        page("counter.pdf", 7, "Nothing here."), page("order.pdf", 8, PASSIVE))
    said = found["problem"]
    assert "do not appear" in said and "the nearest words on a page (order.pdf, page 8) read '" in said
    assert "tahsildar was directed to implement the name of these respondents for an extent of ac.1.18 guntas" in said.split("read '")[1]
    assert found["fix"].startswith("Quote the exact words") and "as they stand" in found["fix"]


def test_a_letter_the_scan_misread_is_shown_as_the_page_has_it_so_it_can_be_copied():
    found = problem_for("“Issue notice to private respondents returnable within six weeks”", page("order.pdf", 12, SLIP))
    said = found["problem"].split("read '")[1]
    assert "lssue notice to private respondents returnable within six weeks." in said and "(order.pdf, page 12)" in found["problem"]
    # Copied as it stands, it is found: the check is exact, and was never loosened.
    assert research.code_checks(facts("“lssue notice to private respondents returnable within six weeks”"), context(page("order.pdf", 12, SLIP))) == []


def test_the_words_around_the_run_are_a_few_on_each_side_not_the_whole_page():
    said = problem_for("“directed the Tahsildar to implement the name of these respondents”", page("order.pdf", 8, PASSIVE))["problem"]
    words = said.split("read '")[1].rsplit("'", 1)[0].split(" ")
    tokens = " ".join(PASSIVE.split()).casefold().split(" ")
    start = tokens.index("implement") - 1          # the run is "to implement the name of these respondents": seven words
    assert words == tokens[start - 8:start + 7 + 8], words
    assert len(words) < len(tokens) / 2


def test_the_longest_run_is_the_one_shown_and_a_run_on_another_document_names_that_document():
    other = "The Tahsildar was directed to attend. The order directed the Tahsildar, Hyderabad West to mutate his name."
    said = problem_for("“directed the Tahsildar to implement the name of these respondents for an extent of Ac.1.18 guntas”",
                       page("first.pdf", 2, other), page("second.pdf", 5, PASSIVE))["problem"]
    assert "(second.pdf, page 5)" in said and "first.pdf" not in said


def test_words_nowhere_on_a_page_or_too_few_in_a_row_get_no_excerpt():
    nowhere = problem_for("the court dismissed the appeal with costs", page("order.pdf", 8, PASSIVE))["problem"]
    assert "not found from their first words" in nowhere and "nearest" not in nowhere
    short = problem_for("“the Tahsildar was told”", page("order.pdf", 8, PASSIVE))["problem"]
    assert "nearest" not in short, "three words in a row say nothing about where a quotation is from"
    # A quotation longer than the finder will search for is refused as before, with where it stops matching and no excerpt.
    long_words = [f"word{n}" for n in range(research.NEAREST_WORDS + 1)]
    held = page("order.pdf", 8, PASSIVE + " " + " ".join(long_words[:60]))
    refused = problem_for("“" + " ".join(long_words) + "”", held)["problem"]
    assert "do not appear" in refused and "nearest" not in refused
    assert "nearest" in problem_for("“" + " ".join(long_words[:61]) + "”", held)["problem"], "within the cap the same page is shown"


def test_the_nearest_words_of_a_run_that_goes_over_a_page_break_are_not_guessed_at():
    foot = "In the meanwhile revenue officers are directed to continue to maintain the name of the original owner in the records"
    head = "pending the decision of the civil court. The matter is posted."
    quoted = "“to maintain the name of the original owner in the records pending the decision of the civil court and the costs”"
    said = problem_for(quoted, page("order.pdf", 8, foot), page("order.pdf", 9, head))["problem"]
    assert "do not appear" in said
    assert "(order.pdf, page 8) read '" in said, "the longest run that one page holds is shown"
    tokens = " ".join(foot.split()).casefold().split(" ")
    start = tokens.index("maintain") - 1           # "to maintain the name of the original owner in the records": eleven words, the foot's end
    assert said.split("read '")[1].rsplit("'", 1)[0] == " ".join(tokens[max(0, start - 8):start + 11 + 8])


def test_the_readers_marks_are_not_the_pages_words_in_what_is_shown_either():
    marked = ("The Tahsildar was directed to implement the name\n[stamp: CERTIFIED TRUE COPY]\n[signature]\nof these respondents for an "
              "extent of Ac.1.18 guntas.")
    said = problem_for("“directed the Tahsildar to implement the name of these respondents for an extent of Ac.1.18 guntas”",
                       page("order.pdf", 8, marked))["problem"]
    shown = said.split("read '")[1]
    assert "to implement the name of these respondents for an extent of ac.1.18 guntas." in shown
    assert "stamp" not in shown and "signature" not in shown


def test_nearest_is_the_finders_and_leaves_the_pages_and_the_checks_as_they_were():
    pages = Pages.of_context(context(page("order.pdf", 8, PASSIVE)))
    near = pages.nearest("directed the tahsildar to implement the name of these respondents for an extent of ac.1.18 guntas")
    assert (near["document"], near["page"]) == ("order.pdf", 8) and near["run"].startswith("to implement the name of these")
    assert pages.nearest("the court dismissed the appeal") is None and pages.nearest("one two three") is None
    assert research.code_checks(facts("“the Tahsildar was directed to implement the name of these respondents”"),
                                context(page("order.pdf", 8, PASSIVE))) == []
