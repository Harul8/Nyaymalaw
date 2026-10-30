"""Figures that two copies of one page read differently are flagged by code (plan AN.27, P13; invariant I6).

Two scans of one passage were read separately by the AI and gave 6.06 and 6.16, and NM called it a disagreement in the papers and then
reasoned from it. Copies are now found by their words, and the figures in which they differ are named with the words before them;
nothing says which reading is right. The papers here are synthetic, of the same shape.
"""
import pytest

from nm.core_engine import copy_figures
from nm.core_engine.copy_figures import differences

pytestmark = pytest.mark.class_a

FILLER = " ".join(f"term{n}" for n in range(60))


def passage(extent="6.06", deed="596/80", date="5.1.1980", filler=FILLER):
    return (f"Sale deed number {deed} dated {date} the vendor sold to the purchasers an extent of {extent} acres in the survey "
            f"number of the village {filler} registered at the office of the sub registrar")


def page(document, number, text, key=None, **more):
    return {"document": document, "key": key or document, "page": number, "text": text, **more}


def test_two_copies_that_read_a_figure_differently_are_flagged_with_both_readings_and_the_words_before_it():
    found = differences([page("deed.pdf", 3, passage("6.06")), page("scan.pdf", 1, passage("6.16"))])
    (finding,) = found
    assert (finding["first"]["document"], finding["first"]["page"]) == ("deed.pdf", 3)
    assert (finding["second"]["document"], finding["second"]["page"]) == ("scan.pdf", 1)
    (figure,) = finding["figures"]
    assert (figure["first"], figure["second"]) == ("6.06", "6.16") and figure["after"].endswith("an extent of")


def test_copies_that_agree_are_not_flagged():
    assert differences([page("deed.pdf", 3, passage()), page("scan.pdf", 1, passage())]) == []


def test_a_word_read_differently_is_not_a_figure_and_a_figure_written_otherwise_is_not_a_difference():
    other = passage().replace("vendor", "vender").replace("registrar", "registrer")
    assert differences([page("a.pdf", 1, passage()), page("b.pdf", 1, other)]) == []
    assert differences([page("a.pdf", 1, passage("6.06")), page("b.pdf", 1, passage("6-06"))]) == []
    assert differences([page("a.pdf", 1, passage("6.06")), page("b.pdf", 1, passage("6 06"))]) == []


def test_several_figures_that_differ_are_all_named():
    found = differences([page("a.pdf", 1, passage("6.06", "596/80", "5.1.1980")), page("b.pdf", 1, passage("6.16", "596/89", "5.1.1980"))])
    assert [(f["first"], f["second"]) for f in found[0]["figures"]] == [("596/80", "596/89"), ("6.06", "6.16")]


def test_two_pages_of_one_form_with_figures_of_their_own_are_not_copies():
    rows_a = " ".join(f"survey {n} extent {n}.{n % 40:02d} khata {n * 3}" for n in range(1, 25))
    rows_b = " ".join(f"survey {n + 100} extent {n + 7}.{(n + 5) % 40:02d} khata {n * 3 + 1}" for n in range(1, 25))
    assert differences([page("a.pdf", 1, rows_a), page("b.pdf", 1, rows_b)]) == []


def test_pages_of_one_document_are_not_compared_with_each_other_and_two_files_of_one_name_are_two_documents():
    same = [page("deed.pdf", 1, passage("6.06")), page("deed.pdf", 2, passage("6.16"))]
    assert differences(same) == []
    two_files = [page("deed.pdf", 1, passage("6.06"), key="t1:d1"), page("deed.pdf", 1, passage("6.16"), key="t2:d1")]
    assert len(differences(two_files)) == 1


def test_a_page_too_short_to_be_a_copy_and_a_recording_are_left_alone():
    assert differences([page("a.pdf", 1, "extent 6.06 acres"), page("b.pdf", 1, "extent 6.16 acres")]) == []
    assert differences([page("a.mp3", 1, passage("6.06"), recording=True), page("b.mp3", 1, passage("6.16"), recording=True)]) == []


def test_the_readers_notes_are_not_words_of_the_page():
    noted = passage("6.06").replace("registered", "[stamp: CERTIFIED TRUE COPY] registered")
    assert differences([page("a.pdf", 1, noted), page("b.pdf", 1, passage("6.16"))])[0]["figures"][0]["second"] == "6.16"


def test_a_pair_is_named_once_the_ids_are_kept_and_the_findings_are_bounded(monkeypatch):
    found = differences([page("a.pdf", 1, passage("6.06"), id="DOC1"), page("b.pdf", 1, passage("6.16"), id="DOC2")])
    assert len(found) == 1 and (found[0]["first"]["id"], found[0]["second"]["id"]) == ("DOC1", "DOC2")
    monkeypatch.setattr(copy_figures, "MOST_FOUND", 2)
    many = [page(f"{n}.pdf", 1, passage(f"6.{n:02d}")) for n in range(1, 6)]
    assert len(differences(many)) == 2


def test_pages_that_say_different_things_are_not_copies():
    other = " ".join(f"other{n}" for n in range(80)) + " extent of 6.16 acres"
    assert differences([page("a.pdf", 1, passage("6.06")), page("b.pdf", 1, other)]) == []


def test_pages_that_share_only_part_of_their_wording_are_not_copies():
    half = " ".join(f"term{n}" for n in range(40)) + " " + " ".join(f"other{n}" for n in range(20))
    assert differences([page("a.pdf", 1, passage("6.06")), page("b.pdf", 1, passage("6.16", filler=half))]) == []


def test_two_pages_of_one_form_that_say_the_same_but_differ_in_many_figures_are_not_copies():
    fixed = " ".join("clause" + chr(97 + n % 26) + chr(97 + n // 26) for n in range(80))
    lines = [f"line{n} entry {n}.{n:02d} khata {n * 3}" for n in range(1, 11)]
    changed = [line if n > 5 else f"line{n} entry {n}.{n + 1:02d} khata {n * 3 + 1}" for n, line in enumerate(lines, 1)]
    assert differences([page("a.pdf", 1, fixed + " " + " ".join(lines)), page("b.pdf", 1, fixed + " " + " ".join(changed))]) == []
    few = [line if n > 1 else f"line{n} entry {n}.{n + 1:02d} khata {n * 3 + 1}" for n, line in enumerate(lines, 1)]
    assert len(differences([page("a.pdf", 1, fixed + " " + " ".join(lines)), page("b.pdf", 1, fixed + " " + " ".join(few))])[0]["figures"]) == 2


def test_a_copy_of_a_few_words_is_not_a_page_to_compare():
    short = ("Sale deed number 596/80 dated 5.1.1980 the vendor sold to the purchasers an extent of {} acres in the survey number "
             "of the village registered at the office of the sub registrar")
    assert len(short.split()) < copy_figures.MIN_WORDS
    assert differences([page("a.pdf", 1, short.format("6.06")), page("b.pdf", 1, short.format("6.16"))]) == []


def test_a_note_the_reader_made_is_not_a_figure_of_the_page():
    first = passage().replace("registered", "[handwritten: 1] registered")
    second = passage().replace("registered", "[handwritten: 2] registered")
    assert differences([page("a.pdf", 1, first), page("b.pdf", 1, second)]) == []


def test_a_figure_in_words_in_one_copy_and_in_numerals_in_the_other_is_not_a_different_figure():
    assert differences([page("a.pdf", 1, passage("six")), page("b.pdf", 1, passage("6"))]) == []


# Every pair of copies, whether or not their figures agree (plan AN.27, P20 (b)): a transaction two papers report on copies of one page is
# one, and the pages' words say so.
def test_copies_are_every_pair_of_pages_that_are_copies_of_one_page_whether_or_not_their_figures_agree():
    pages = [page("deed.pdf", 3, passage("6.06"), key="t1:d1"), page("scan.pdf", 1, passage("6.06"), key="t1:d2"),
             page("late.pdf", 2, passage("6.16"), key="t1:d3")]
    assert copy_figures.copies(pages) == {frozenset({("t1:d1", 3), ("t1:d2", 1)}), frozenset({("t1:d1", 3), ("t1:d3", 2)}),
                                          frozenset({("t1:d2", 1), ("t1:d3", 2)})}
    assert differences(pages[:2]) == [], "the two that agree are copies, but there is nothing to flag"
    assert [d["second"]["document"] for d in differences(pages)] == ["late.pdf", "late.pdf"]


def test_pages_of_one_document_a_form_with_figures_of_its_own_a_short_page_and_a_recording_are_not_copies():
    assert copy_figures.copies([page("deed.pdf", 1, passage()), page("deed.pdf", 2, passage())]) == set()
    rows_a = " ".join(f"survey {n} extent {n}.{n % 40:02d} khata {n * 3}" for n in range(1, 25))
    rows_b = " ".join(f"survey {n + 100} extent {n + 7}.{(n + 5) % 40:02d} khata {n * 3 + 1}" for n in range(1, 25))
    assert copy_figures.copies([page("a.pdf", 1, rows_a), page("b.pdf", 1, rows_b)]) == set()
    assert copy_figures.copies([page("a.pdf", 1, "extent 6.06 acres"), page("b.pdf", 1, "extent 6.06 acres")]) == set()
    assert copy_figures.copies([page("a.mp3", 1, passage(), recording=True), page("b.mp3", 1, passage(), recording=True)]) == set()
    assert copy_figures.copies([]) == set()
