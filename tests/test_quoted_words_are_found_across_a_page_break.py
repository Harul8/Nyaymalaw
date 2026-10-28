"""Words quoted from a document are found wherever the document holds them (plan AN.27, P1; invariant I1).

A fact's quoted words must be in what the advocate or the documents gave. They were matched against the pages joined as they
stand, so a sentence that ran over a page break - with the page's stamp, signature and the reader's marks between the halves -
was "not found", and the problem did not say which words failed. The papers here are synthetic, of the same shape.
"""
import pytest

from nm.core_engine import research
from nm.core_engine.research import Pages

pytestmark = pytest.mark.class_a

SENTENCE = ("revenue officers are directed to continue to maintain the name of the original owner in the records against land "
            "to an extent of Ac.1.18 guntas and Ac.1.00 respectively in Survey No. 100 of the village. However none of the "
            "parties should register conveyances of the above extent till the issue is adjudicated.")
FOOT = ("The petition is disposed of and in the meanwhile revenue officers are directed to continue to maintain the name of the "
        "original owner in the records against land to an extent of Ac.1.18 guntas and Ac.1.00\n\n"
        "[stamp: CERTIFIED TO BE TRUE COPY]\n[signature]\nAdministrative Officer\nCOLLECTORATE\nSome District\n[signature]")
HEAD = ("[Handwritten: 4831/-]\n\nrespectively in Survey No. 100 of the village. However none of the parties should register "
        "conveyances of the above extent till the issue is adjudicated.\"\n\nThe petition is disposed of.")


def page(name, number, text):
    return {"source_id": f"{name}:p{number}", "text": text, "document": {"name": name, "page": number, "read_by": "ai"}}


def context(*pages, said="Please read the papers."):
    return {"conversation": [], "latest": {"text": said}, "documents": list(pages)}


def facts(words):
    return {"facts": [{"id": "F1", "fact": "A direction.", "advocate_words": words, "certainty": "reported"}],
            "disputes": [], "related_points": [], "needs_research": False}


def problems(words, *pages, said="Please read the papers."):
    return research.code_checks(facts(words), context(*pages, said=said))


def test_a_sentence_that_runs_over_a_page_break_is_found_past_the_stamp_the_signature_and_the_readers_marks():
    one, two = page("order.pdf", 8, FOOT), page("order.pdf", 9, HEAD)
    assert problems(SENTENCE, one, two) == []
    pages = Pages.of_context(context(one, two))
    assert pages.holding(research.fact_pieces(SENTENCE)[0]) == pages.pages, "both pages hold the words"


def test_the_same_words_with_one_word_changed_are_not_found_and_the_problem_says_where_they_stop_matching():
    changed = SENTENCE.replace("Ac.1.00", "Ac.2.00")
    found = problems(changed, page("order.pdf", 8, FOOT), page("order.pdf", 9, HEAD))
    (problem,) = found
    assert "do not appear" in problem["problem"]
    assert "match up to '... an extent of ac.1.18 guntas and'" in problem["problem"], problem["problem"]
    assert "not found from 'ac.2.00 respectively in survey no. 100 of the village. however none of'" in problem["problem"]
    assert problem["fix"].startswith("Quote the exact words")


def test_words_that_are_nowhere_in_the_papers_are_said_not_to_be_found_from_their_first_words():
    (problem,) = problems("the court dismissed the appeal with costs", page("order.pdf", 8, FOOT), page("order.pdf", 9, HEAD))
    assert "not found from their first words: 'the court dismissed the appeal with costs'" in problem["problem"]


def test_words_split_between_two_documents_are_not_found():
    assert problems(SENTENCE, page("one.pdf", 8, FOOT), page("two.pdf", 9, HEAD))


def test_words_split_between_pages_that_are_not_next_to_each_other_are_not_found():
    assert problems(SENTENCE, page("order.pdf", 8, FOOT), page("order.pdf", 10, HEAD))
    assert problems(SENTENCE, page("order.pdf", 9, HEAD), page("order.pdf", 8, FOOT)), "the second page must follow the first"


def test_a_foot_or_head_longer_than_the_allowance_stops_a_sentence_running_over():
    stamps = "Stamp duty paid. "           # 17 characters; the allowance for a page's foot or head is 400
    within = (page("order.pdf", 8, FOOT + "\n" + stamps * 20), page("order.pdf", 9, stamps * 20 + HEAD))
    assert problems(SENTENCE, *within) == []
    assert problems(SENTENCE, page("order.pdf", 8, FOOT + "\n" + stamps * 25), page("order.pdf", 9, HEAD))
    assert problems(SENTENCE, page("order.pdf", 8, FOOT), page("order.pdf", 9, stamps * 24 + HEAD))


def test_words_joined_with_an_ellipsis_from_separate_pages_are_still_found():
    one, three = page("order.pdf", 1, FOOT), page("order.pdf", 3, HEAD)
    assert problems('"Ac.1.18 guntas and Ac.1.00" ... "till the issue is adjudicated"', one, three) == []


def test_a_sentence_goes_over_a_page_break_only_between_whole_words():
    assert problems("pay the compensation due in full", page("a.pdf", 1, "We shall pay the compensation"),
                    page("a.pdf", 2, "due in full.")) == []
    cut_in_a_word = (page("a.pdf", 1, "We shall pay the compens"), page("a.pdf", 2, "ation due in full."))
    assert problems("pay the compensation due in full", *cut_in_a_word)
    # The quotation may not cut a word the page does not cut, nor start the head's words in the middle of one.
    foot = page("a.pdf", 1, "We shall pay the compensation")
    assert problems("pay the compensat due in full", foot, page("a.pdf", 2, "due in full."))
    assert problems("pay the compensation due in full", foot, page("a.pdf", 2, "xdue in full."))


def test_the_readers_marks_inside_a_page_do_not_stop_a_match_and_may_be_quoted():
    here = page("memo.pdf", 1, "The sum was [signature] paid in full on the day.")
    assert problems("the sum was paid in full", here) == []
    assert problems("the sum was [signature] paid in full", here) == []
    assert problems("the sum was paid in part", here)


def test_words_in_the_advocates_own_message_need_no_document():
    assert problems("the cheque bounced", said="The cheque bounced on Monday.") == []
    assert problems("the cheque cleared", said="The cheque bounced on Monday.")


def test_a_recording_has_no_pages_to_run_over_and_is_not_a_mistake():
    first = {"source_id": "call.mp3:1", "text": "We agreed the sum was", "document": {"name": "call.mp3", "recording": True}}
    second = {"source_id": "call.mp3:2", "text": "five thousand rupees.", "document": {"name": "call.mp3", "recording": True}}
    assert problems("we agreed the sum was", first, second) == []
    assert problems("the sum was five thousand rupees", first, second), "two parts of a recording are not consecutive pages"


def test_nothing_in_the_papers_is_found_for_words_that_are_not_there():
    assert problems("the court dismissed the appeal", page("order.pdf", 8, FOOT), page("order.pdf", 9, HEAD))
    assert Pages([]).holding("anything") is None
