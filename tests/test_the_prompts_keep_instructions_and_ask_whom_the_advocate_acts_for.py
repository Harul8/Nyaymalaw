"""What the board calls the advocate's standing instructions, and whom the advocate acts for (plan AN.27, P14 and P16; invariant I7).

In the reviewed bundle the understanding's 'ruled_out' - which the board shows as "Your standing instructions" - held what the papers do
not establish, and the first answer neither knew whom the advocate acts for nor asked, though the papers had parties on opposite
sides. The understanding's prompt now keeps 'ruled_out' to what the advocate told NM not to do, in their words; and the writer of the
whole answer, and the overview that opens an answer of several disputes, ask whom the advocate acts for when the papers show parties on
opposite sides and nothing the advocate said tells it. The wording is measured by a bounded live run, not by these tests.
"""
import pytest

from nm.core_engine import research, response_writer

pytestmark = pytest.mark.class_a


def said(text):
    return " ".join(text.split())


def test_the_understanding_keeps_ruled_out_to_what_the_advocate_told_us_not_to_do():
    prompt = said(research.UNDERSTAND)
    for part in ("Also note, in the advocate's own words, anything they have told us not to do",
                 "in ruled_out, and where they have told us nothing of the kind leave ruled_out empty",
                 "What the papers leave open or unproved is not something the advocate ruled out: it belongs in the facts as "
                 "uncertain and in the facts we would still need"):
        assert part in prompt, part
    assert "not to assume a disputed event" not in prompt, "the instruction that invited the papers' open points into ruled_out"


def test_the_whole_answer_asks_whom_the_advocate_acts_for_where_the_papers_show_opposite_sides():
    prompt = said(response_writer.SYSTEM_V13)
    assert ("When you write the whole answer, and the papers show parties on opposite sides while nothing the advocate has said "
            "tells you whom they act for, ask that first, as one question: it decides which of those parties is adverse to them.") in prompt
    assert "adverse to them" not in said(response_writer.SYSTEM)


def test_the_overview_asks_it_first_among_the_choices_that_are_the_advocates():
    prompt = said(response_writer.OVERVIEW_SYSTEM_V13)
    assert ("Where the papers show parties on opposite sides and nothing the advocate has said tells you whom they act for, that is "
            "the first such question: it decides which parties are adverse to them.") in prompt
    assert "adverse to them" not in said(response_writer.OVERVIEW_SYSTEM)
