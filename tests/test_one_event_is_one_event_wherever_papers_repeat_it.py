"""An event that several papers record is one event wherever it is shown (plan AN.27, P22, part b).

In the replay of the reviewed bundle two of the seven papers are copies of one another, and 41 of the 249 events NM read were an event
the other paper had already recorded: the same passage, quoted to a different length. The plan keeps what each paper says, as it was
read; where the events are shown they are now counted once. Two events are one when they have the same day and kind, are read in
different papers, are on pages that are copies of one another, and the shorter quotation is, but for scan noise, wholly inside the
longer; an event that matches no other stands alone, and two different orders passed on one day, in each of two papers, pair with their
own copies. The papers here are synthetic.
"""
import copy

import pytest

from nm.core_engine import matter_board, research
from nm.core_engine.research import events_once
from tests.test_copies_that_read_a_figure_differently import passage
from tests.test_the_board_has_a_timeline import event as planned, turn
from tests.test_the_board_names_figures_copies_read_differently import paper

pytestmark = pytest.mark.class_a

ORDER = "The Joint Collector allowed the revision petition by an order dated 17-8-2019 and set aside the order of the Revenue Divisional Officer"
OTHER = "The Tahsildar passed an order in File B/53/2008 on 17-8-2019 granting mutation of the land to the purchasers named in the deed"
COPIES = {frozenset({("a", 1), ("b", 1)})}


def ev(number, source, sort="2019-08-17", kind="order", words=ORDER, pages=(1,), anchored=True):
    return {"id": f"E{number}", "date": sort or "undated", "sort": sort, "kind": kind, "what": f"what {number}", "said_by": "the court",
            "document": f"{source}.pdf", "source": source, "pages": list(pages), "words": words, "anchored": anchored}


def ids(groups):
    return [(group["event"]["id"], [other["id"] for other in group["also"]]) for group in groups]


def test_an_event_a_copy_of_its_page_records_again_is_one_event_and_the_fullest_quotation_stands_for_it():
    short, long_ = ev(1, "a"), ev(2, "b", words="12. It is submitted that " + ORDER + " in the appeals filed")
    assert ids(events_once([short, long_], COPIES)) == [("E2", ["E1"])]
    assert ids(events_once([long_, short], COPIES)) == [("E2", ["E1"])]
    assert ids(events_once([ev(1, "a"), ev(2, "b")], COPIES)) == [("E1", ["E2"])], "of equal quotations, the first stands"


def test_the_order_is_the_order_of_the_first_event_of_each_and_the_plan_is_left_as_it_was():
    events = [ev(1, "a"), ev(2, "b", words="It is submitted that " + ORDER), ev(3, "a", sort="2020-01-01", words=OTHER)]
    before = copy.deepcopy(events)
    groups = events_once(events, COPIES)
    assert ids(groups) == [("E2", ["E1"]), ("E3", [])] and events == before
    assert groups[0]["event"] is events[1] and groups[0]["also"][0] is events[0]


@pytest.mark.parametrize("other", [
    ev(2, "b", sort="2019-08-18"), ev(2, "b", kind="filing"), ev(2, "b", words=OTHER), ev(2, "b", words="the order of the Joint Collector"),
    ev(2, "b", anchored=False), ev(2, "b", pages=(2,)), ev(2, "a")])
def test_events_that_are_not_the_same_event_stay_apart(other):
    assert ids(events_once([ev(1, "a"), other], COPIES)) == [("E1", []), ("E2", [])]


def test_an_event_whose_words_were_not_found_is_never_one_with_another_whatever_pages_it_names():
    lost = ev(1, "a", anchored=False)
    assert ids(events_once([lost, ev(2, "b")], COPIES)) == [("E1", []), ("E2", [])]
    assert ids(events_once([ev(1, "a"), ev(2, "b", anchored=False)], COPIES)) == [("E1", []), ("E2", [])]


def test_without_copies_every_event_stands_alone():
    for none in ((), set(), None):
        assert ids(events_once([ev(1, "a"), ev(2, "b")], none)) == [("E1", []), ("E2", [])]
    assert events_once([], COPIES) == []


def test_two_orders_of_one_day_in_each_of_two_papers_pair_with_their_own_copies_whichever_is_read_first():
    first, second = ORDER, OTHER
    for b_order in ((first, second), (second, first)):
        events = [ev(1, "a", words=first), ev(2, "a", words=second), ev(3, "b", words=b_order[0]), ev(4, "b", words=b_order[1])]
        groups = events_once(events, COPIES)
        found = {frozenset(map(int, (group["event"]["id"][1:], *(o["id"][1:] for o in group["also"])))) for group in groups}
        assert found == {frozenset({1, 3 if b_order[0] == first else 4}), frozenset({2, 4 if b_order[0] == first else 3})}


def test_a_paper_never_has_two_of_its_events_in_one_event():
    assert ids(events_once([ev(1, "a"), ev(2, "a"), ev(3, "b")], COPIES)) == [("E1", ["E3"]), ("E2", [])]
    assert ids(events_once([ev(1, "a"), ev(2, "b"), ev(3, "b")], COPIES)) == [("E1", ["E2"]), ("E3", [])]


def test_an_event_joins_the_event_it_is_likeliest_to_be_and_not_the_first_that_will_do():
    noisy = ORDER.replace("Joint Collector", "J0int Co11ector").replace("dated", "daled")
    groups = events_once([ev(1, "a", words=noisy), ev(2, "a", words=ORDER), ev(3, "b", words=ORDER)], COPIES)
    assert ids(groups) == [("E1", []), ("E2", ["E3"])]


def test_a_third_paper_that_copies_a_page_of_the_second_joins_the_same_event():
    copies = {frozenset({("a", 1), ("b", 1)}), frozenset({("b", 1), ("c", 4)})}
    events = [ev(1, "a"), ev(2, "b", words="It is submitted that " + ORDER), ev(3, "c", pages=(4,), words="and further " + ORDER + " as stated")]
    assert ids(events_once(events, copies)) == [("E3", ["E1", "E2"])]
    assert ids(events_once(events, {frozenset({("a", 1), ("b", 1)})})) == [("E2", ["E1"]), ("E3", [])], "c copies nothing here"


def test_a_scan_that_reads_a_word_or_two_differently_is_still_the_same_passage_and_a_different_sentence_is_not():
    noisy = ORDER.replace("Joint Collector", "J0int Co11ector").replace("dated", "daled")
    assert research._held_in(ORDER, noisy) >= research.SAME_PASSAGE
    assert research._held_in(ORDER, "12. It is submitted that " + noisy + " in the appeals") >= research.SAME_PASSAGE
    assert research._held_in(ORDER, OTHER) < 0.6, "two orders of one day share only the words of orders"
    assert research._held_in("the Joint Collector", ORDER) == 0.0, "under four words say nothing of which event it is"
    assert research._held_in("the Joint Collector allowed", ORDER) == 1.0, "four words are enough to be held in the longer"
    assert research._held_in(ORDER, "") == 0.0 and research._held_in("", "") == 0.0


def test_words_that_are_only_somewhere_in_a_longer_sentence_are_not_the_passage():
    scattered = " ".join(f"{word} zz{n}" for n, word in enumerate(ORDER.split()))
    assert research._held_in(ORDER, scattered) < 0.2


def test_undated_events_are_one_by_the_same_rule():
    assert ids(events_once([ev(1, "a", sort=""), ev(2, "b", sort="", words="It is submitted that " + ORDER)], COPIES)) == [("E2", ["E1"])]
    assert ids(events_once([ev(1, "a", sort=""), ev(2, "b", sort="", words=OTHER)], COPIES)) == [("E1", []), ("E2", [])]
    assert ids(events_once([ev(1, "a", sort=""), ev(2, "b", sort="2019-08-17")], COPIES)) == [("E1", []), ("E2", [])]


# The board lists an event once, naming where else it is recorded; each paper's own count is what it gave.
SALE = "Sale deed number 596/80 dated 5.1.1980 the vendor sold to the purchasers an extent of 6.06 acres in the survey number"


def at(number, name, source, words, pages=(1,)):
    return planned(number, "5.1.1980", f"what {number}", document=name, source=source, pages=pages, words=words)


def test_the_board_lists_an_event_once_that_a_copy_of_its_page_records_again():
    events = [at(1, "deed.pdf", "t1:d1", SALE), at(2, "scan.pdf", "t1:d2", "12. It is submitted that " + SALE + " to them")]
    row = turn([paper("deed.pdf", passage()), paper("scan.pdf", passage())], events)
    shown = matter_board.board([row])["timeline"]
    (only,) = shown["events"]
    assert (only["id"], only["document"], only["pages"], only["located"]) == ("E2", "scan.pdf", [1], True)
    assert only["also_in"] == [{"document": "deed.pdf", "pages": [1]}]
    assert [(d["name"], d["events"]) for d in shown["documents"]] == [("deed.pdf", 1), ("scan.pdf", 1)], "each paper's own count stands"
    # What the board tells is its own to change: the plan it was read from is not touched.
    only["also_in"][0]["pages"].append(99)
    only["pages"].append(98)
    again = matter_board.board([row])["timeline"]["events"][0]
    assert (again["pages"], again["also_in"][0]["pages"]) == ([1], [1]) and events[0]["pages"] == [1] and events[1]["pages"] == [1]


def test_papers_that_are_not_copies_of_one_another_keep_their_events_and_an_event_alone_has_no_also_in():
    events = [at(1, "deed.pdf", "t1:d1", SALE), at(2, "scan.pdf", "t1:d2", SALE)]
    other = "A different paper entirely, of other words, about nothing the deed says. " * 12
    shown = matter_board.board([turn([paper("deed.pdf", passage()), paper("scan.pdf", other)], events)])["timeline"]
    assert [e["id"] for e in shown["events"]] == ["E1", "E2"] and all("also_in" not in e for e in shown["events"])


def test_a_copy_sent_in_a_later_turn_counts_with_the_event_of_the_earlier_one():
    first = turn([paper("deed.pdf", passage())], [at(1, "deed.pdf", "t1:d1", SALE)])
    second = turn([paper("scan.pdf", passage())], [at(1, "deed.pdf", "t1:d1", SALE), at(2, "scan.pdf", "t2:d1", SALE)], turn_id="t2")
    (only,) = matter_board.board([first, second])["timeline"]["events"]
    assert only["id"] == "E1" and only["also_in"] == [{"document": "scan.pdf", "pages": [1]}]
