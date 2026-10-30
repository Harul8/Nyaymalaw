"""The board names the figures that copies of a page read differently (plan AN.27, P13; invariant I6).

The board derives them from the pages saved with the turns up to the one it shows, by the same finder that finds them anywhere
(copy_figures); it names both readings and chooses neither. The papers here are synthetic.
"""
import pytest

from nm.core_engine import matter_board
from tests.test_the_board_has_a_timeline import turn
from tests.test_copies_that_read_a_figure_differently import passage

pytestmark = pytest.mark.class_a


def paper(name, *texts, recording=False):
    return {"document_ref": "doc", "name": name, "unread": [],
            "pages": [{"number": n, "text": text, "read_by": "local"} for n, text in enumerate(texts, 1)],
            **({"recording": True} if recording else {})}


def copies(*documents, extra=()):
    return matter_board.board([turn(list(documents), [], turn_id="t1"), *extra])["copies"]


def test_two_copies_read_differently_are_named_with_both_readings_and_the_words_before():
    (found,) = copies(paper("deed.pdf", "Cover page.", passage("6.06")), paper("scan.pdf", passage("6.16")))
    assert found["first"] == {"document": "deed.pdf", "page": 2} and found["second"] == {"document": "scan.pdf", "page": 1}
    (figure,) = found["figures"]
    assert (figure["first"], figure["second"]) == ("6.06", "6.16") and figure["after"].endswith("an extent of")


def test_copies_that_agree_and_a_matter_with_one_paper_have_none():
    assert copies(paper("deed.pdf", passage()), paper("scan.pdf", passage())) == []
    assert copies(paper("deed.pdf", passage("6.06"))) == []
    assert matter_board.board([turn([], [])])["copies"] == []


def test_two_files_of_one_name_are_two_papers_and_a_recording_is_not_compared():
    (found,) = copies(paper("deed.pdf", passage("6.06")), paper("deed.pdf", passage("6.16")))
    assert found["first"]["document"] == found["second"]["document"] == "deed.pdf"
    assert copies(paper("a.mp3", passage("6.06"), recording=True), paper("b.mp3", passage("6.16"), recording=True)) == []


def test_papers_sent_in_earlier_turns_are_compared_with_those_of_the_turn_shown():
    first = turn([paper("deed.pdf", passage("6.06"))], [], turn_id="t1")
    second = turn([paper("scan.pdf", passage("6.16"))], [], turn_id="t2")
    assert len(matter_board.board([first, second])["copies"]) == 1
    later = turn([paper("late.pdf", passage("6.26"))], [], turn_id="t3", empty=True)
    assert len(matter_board.board([first, second, later])["copies"]) == 1, "a later turn that set out no matter adds nothing"
