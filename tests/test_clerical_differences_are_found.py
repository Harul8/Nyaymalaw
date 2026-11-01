"""Words quoted from a page are found when they differ from it only in what cannot change their meaning (plan AN.33, D18; piece 33a).

Two blind readings of an advocate's papers (AN.31, 1 Nov 2026) quoted 109 points; the exact finder turned 17 away, every one for a
clerical reason - a word the scan reader split, spacing or stops in a case number, a space before a comma, a handwritten number the
page reader put inside a square-bracket note, a doubled mark, a bullet. The tolerant finder finds what cannot change the meaning, and
still never takes one number for another, a different letter or a dropped word for the page's: those are for a model to settle with
code's evidence (33b). Saved records keep the exact finder (P46). The papers here are invented, of the same shapes.
"""
import pytest

from nm.core_engine import research
from nm.core_engine.research import EXACT_FINDER, TOLERANT_FINDER, Pages, fact_pieces

pytestmark = pytest.mark.class_a


def page(text, name="order.pdf", number=1):
    return {"document": name, "page": number, "text": text}


def finds(words, *pages, version=TOLERANT_FINDER):
    finder = Pages(pages, version)
    return all(finder.holding(piece) is not None for piece in fact_pieces(words))


SPLIT = "the orders made as to the plot of the appli cant in W.P.No.512 of 2021 are quashed"
MEMO = "Ref. LR[handwritten: 812] /2013 Dated: [handwritten: 14] -05-2013 :: NOTE :: Sub:- copies of registers"
CASE = "near the bus stand, some town C. R. P no: 345 of 2019 between: 1. Sri T. Ramesh"


@pytest.mark.parametrize("on_the_page, quoted", [
    # a word the scan reader split
    (SPLIT, "the plot of the applicant in W.P.No.512 of 2021 are quashed"),
    ("on consent, we d eem it fit to direct that the stay shall continue", "on consent, we deem it fit to direct that the stay"),
    # spacing and stops in a case number, and the words beside it
    (CASE, "C.R.P. No: 345 of 2019 between: 1. Sri T. Ramesh"),
    ("relating to Plot No. 210 vide letter dated 3-9-2014 and obtained the papers",
     "relating to plot. no. 210 vide letter dated 3-9-2014 and obtained the papers"),
    # a space before a comma
    ("learned standing counsel appearing for the corporation , for the respondents",
     "appearing for the corporation, for the respondents"),
    # a word broken over a line with a hyphen
    ("the notice was served on a wrong ad-\ndress, namely the old office", "served on a wrong address, namely the old office"),
    # a mark the reader doubled, and a bullet
    ("certified copy of the ledger for the years 1981-82 (Part A) & & 1990-91 to 1993-94 - Reg.",
     "the ledger for the years 1981-82 (Part A) & 1990-91 to 1993-94"),
    ("Work still to do:\n\n• Identity proofs of all the members are to be filed with the office",
     "work still to do: identity proofs of all the members are to be filed"),
    # spacing around the strokes of a file number
    ("the officer passed transfer orders in file no. K / 2257 / 2012 dated 14-8-2013",
     "passed transfer orders in file no. K/2257/2012 dated 14-8-2013"),
])
def test_a_clerical_difference_is_found_by_the_tolerant_finder_and_not_by_the_exact_one(on_the_page, quoted):
    assert finds(quoted, page(on_the_page))
    assert not finds(quoted, page(on_the_page), version=EXACT_FINDER)


def test_handwriting_the_reader_transcribed_in_a_note_is_the_pages_own_words():
    assert finds("Ref. LR 812 /2013 Dated: 14 -05-2013", page(MEMO))
    assert not finds("Ref. LR 812 /2013 Dated: 14 -05-2013", page(MEMO), version=EXACT_FINDER)
    note = "Sub:- the registers of the ward [Handwritten note at the foot, partly illegible: check the earlier entries first]"
    assert finds("the registers of the ward check the earlier entries first", page(note))
    assert not finds("the registers of the ward check the earlier entries first", page(note), version=EXACT_FINDER)


def test_what_the_tolerant_finder_keeps_is_the_pages_own_words():
    pages, words = Pages([page(SPLIT)], TOLERANT_FINDER).located(fact_pieces("plot of the applicant in W.P.No.512 of 2021")[0])
    assert pages[0]["text"] == SPLIT
    assert words == "plot of the appli cant in W.P.No.512 of 2021"
    _, words = Pages([page(MEMO)], TOLERANT_FINDER).located(fact_pieces("LR 812 /2013 Dated: 14 -05-2013")[0])
    assert words == "LR[handwritten: 812] /2013 Dated: [handwritten: 14] -05-2013"


@pytest.mark.parametrize("on_the_page, quoted", [
    # a different digit
    ("the certificate records that she was born on 21-11-1964 at the hospital", "records that she was born on 21-11-1966 at the hospital"),
    # a space a scan put inside a number is not code's to take away: one number is never read as another
    ("to annul the order dated 9.02.2017 made in O.S.No.4418 of 201 6 and decree it",
     "the order dated 9.02.2017 made in O.S.No.4418 of 2016"),
    ("a quantity of 2 75 kg was entered in the register against the lot", "a quantity of 275 kg was entered in the register"),
    # a stop between digits counts
    ("a length of 2.75 metres along the said boundary wall", "a length of 27.5 metres along the said boundary wall"),
    ("a length of 2.75 metres along the said boundary wall", "a length of 275 metres along the said boundary wall"),
    # a different letter, as a scan misreads one or a name is spelt otherwise
    ("the said Sri M. Zubain and others filed their written arguments", "the said Sri M. Zubin and others filed their written arguments"),
    ("the learned counsel take$ notice for the bank in this case", "the learned counsel takes notice for the bank in this case"),
    # a dropped word
    ("in a hurried way issued transfer orders in file no. K/2257/2012", "in a hurried way issued orders in file no. K/2257/2012"),
    # a reader's note that is not handwriting is the reader's, not the page's
    ("[stamp: Registrar of Assurances, Some District] The deed was presented for registration",
     "Registrar of Assurances, Some District The deed was presented for registration"),
    # words that begin inside a longer word of the page, or end inside a longer number (a split word elsewhere keeps the exact
    # finder from taking them first)
    ("the award of the pl ot was made by the officer in the year", "ward of the plot was made by the officer"),
    ("the civil sui t of 2015 was disposed of by the court", "the civil suit of 201"),
])
def test_a_difference_that_may_change_the_meaning_is_never_found(on_the_page, quoted):
    assert not finds(quoted, page(on_the_page))


def test_a_sentence_that_runs_over_a_page_break_with_a_word_the_scan_split_is_found_and_kept_as_the_pages_two_passages():
    foot = ("12. For these reasons the revision is allowed. The orders, made as to the plot of the appel lant in C.R.P.No.88 of "
            "2020, are quashed. The interim applications awai ting orders, if any, shall stand\n[stamp: CERTIFIED TRUE COPY]")
    head = "7\n\ndisposed of. Each side shall bear its own costs.\n[signature]\nJUDGE"
    two = [page(foot, "order.pdf", 6), page(head, "order.pdf", 7)]
    quoted = ("the plot of the appellant in C.R.P.No.88 of 2020, are quashed. The interim applications awaiting orders, if any, shall "
              "stand disposed of. Each side shall bear its own costs")
    assert not finds(quoted, *two, version=EXACT_FINDER)
    pages, words = Pages(two, TOLERANT_FINDER).located(fact_pieces(quoted)[0])
    assert [p["page"] for p in pages] == [6, 7]
    assert words == ("the plot of the appel lant in C.R.P.No.88 of 2020, are quashed. The interim applications awai ting orders, if "
                     "any, shall stand ... disposed of. Each side shall bear its own costs")
    assert finds(words, *two, version=EXACT_FINDER)


@pytest.mark.parametrize("on_the_page, quoted", [
    (SPLIT, "the plot of the applicant in W.P.No.512 of 2021 are quashed"),
    (MEMO, "Ref. LR 812 /2013 Dated: 14 -05-2013"),
    (CASE, "C.R.P. No: 345 of 2019 between: 1. Sri T. Ramesh"),
])
def test_the_pages_own_words_the_tolerant_finder_keeps_are_found_by_the_exact_finder(on_the_page, quoted):
    _, words = Pages([page(on_the_page)], TOLERANT_FINDER).located(fact_pieces(quoted)[0])
    assert finds(words, page(on_the_page), version=EXACT_FINDER)


def test_words_too_short_to_place_are_found_only_exactly():
    assert not finds("appellant", page("the plot of the appel lant"))
    assert finds("appellant", page("the plot of the appellant"))


def test_words_on_two_documents_are_never_joined():
    first, second = page("the decree was passed in favour of the", "one.pdf"), page("plain tiff by the court below", "two.pdf")
    assert not finds("passed in favour of the plaintiff by the court below", first, second)


def test_the_exact_finder_is_unchanged_and_the_tolerant_one_finds_all_it_finds():
    ending = ("The suit is decreed and in the meanwhile the depot is directed to continue to keep the goods of the plaintiff in its "
              "stores to a quantity of 240 kg and 60 kg\n\n[stamp: CERTIFIED TRUE COPY]\n[signature]")
    going = "[Handwritten: 552/-]\n\nrespectively in Lot No. 7 of the depot. The suit is decreed."
    two = [page(ending, "decree.pdf", 1), page(going, "decree.pdf", 2)]
    quoted = "a quantity of 240 kg and 60 kg respectively in Lot No. 7 of the depot"
    for version in (EXACT_FINDER, TOLERANT_FINDER):
        held = Pages(two, version).holding(fact_pieces(quoted)[0])
        assert held is not None
        assert [p["page"] for p in held] == [1, 2]
    assert Pages(two, TOLERANT_FINDER).located(fact_pieces(quoted)[0]) == (
        two, "a quantity of 240 kg and 60 kg ... respectively in Lot No. 7 of the depot")
    assert Pages.of_context({"documents": []}).version == EXACT_FINDER


def test_only_the_two_versions_exist_and_only_the_tolerant_one_gives_the_pages_words():
    exact = Pages([], EXACT_FINDER)
    with pytest.raises(ValueError):
        exact.located("anything at all here")
    with pytest.raises(ValueError):
        Pages([], 3)


def test_the_nearest_words_shown_for_a_refused_quotation_come_from_the_page_whichever_finder_placed_them():
    text = ("the orders made as to the plot of the appli cant in W.P.No.512 of 2021 measuring 4.25 metres are quashed "
            "and the interim applications shall stand closed")
    piece = fact_pieces("plot of the applicant in W.P.No.512 of 2021 measuring 4.85 metres")[0]
    finder = Pages([page(text)], TOLERANT_FINDER)
    assert finder.holding(piece) is None
    near = finder.nearest(piece)
    assert near is not None
    assert near["page"] == 1
    assert "appli cant" in near["words"]
    assert "they match up to" in finder.stops(piece)


def test_the_tolerant_reading_keeps_numbers_and_their_marks_as_they_stand():
    letters, where = research._tolerant("Lot 2.75 on 14–08–1993, No. 201 6 [stamp: X] and [handwritten: 45]")
    assert letters == "lot2.75on14-08-1993no201 6and45"
    assert len(where) == len(letters)
