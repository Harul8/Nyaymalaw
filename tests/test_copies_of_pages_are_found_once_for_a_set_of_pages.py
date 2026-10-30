"""The copies among a set of pages are found once, however often they are asked for (plan AN.27, P22, part a).

The board, the writer, the review and the date check each ask which pages are copies of one another, and finding them among hundreds of
pages takes seconds (0.4 s at 300 pages and 1.4 s at 600, for each ask). They are now found once for a set of pages and kept for the
next to ask, the last few sets only; what is kept is where in the pages the copies are, so a caller whose pages say the same but carry
other IDs is answered in its own, and a caller is given its own copy of what it is told. The pages here are synthetic.
"""
import threading

import pytest

from nm.core_engine import copy_figures
from tests.test_copies_that_read_a_figure_differently import page, passage

pytestmark = pytest.mark.class_a


@pytest.fixture(autouse=True)
def nothing_kept():
    copy_figures._found.clear()
    yield
    copy_figures._found.clear()


@pytest.fixture
def finds(monkeypatch):
    """How many times the pages were really searched for copies."""
    searched = []
    real = copy_figures._pairs

    def counted(pages):
        searched.append(len(pages))
        return real(pages)
    monkeypatch.setattr(copy_figures, "_pairs", counted)
    return searched


def two(first="6.06", second="6.16", **more):
    return [page("deed.pdf", 3, passage(first), key="t1:d1", **more), page("scan.pdf", 1, passage(second), key="t1:d2", **more)]


def test_the_copies_among_the_same_pages_are_found_once_however_often_they_are_asked_for(finds):
    pages = two()
    first, copies = copy_figures.differences(pages), copy_figures.copies(pages)
    assert copy_figures.differences(pages) == first and copy_figures.copies(pages) == copies
    assert copy_figures.differences(list(pages)) == first
    assert len(finds) == 1
    assert copies == {frozenset({("t1:d1", 3), ("t1:d2", 1)})} and first[0]["figures"][0]["first"] == "6.06"


def test_pages_that_say_something_else_are_searched_again(finds):
    base = two()
    copy_figures.copies(base)
    changed_words = two(second="6.26")
    assert copy_figures.differences(changed_words)[0]["figures"][0]["second"] == "6.26" and len(finds) == 2
    other_page = [dict(base[0], page=4), base[1]]
    assert copy_figures.copies(other_page) == {frozenset({("t1:d1", 4), ("t1:d2", 1)})} and len(finds) == 3
    other_paper = [dict(base[0], key="t1:d9"), base[1]]
    assert copy_figures.copies(other_paper) == {frozenset({("t1:d9", 3), ("t1:d2", 1)})} and len(finds) == 4
    same_paper = [dict(base[0], key="t1:d2"), base[1]]
    assert copy_figures.copies(same_paper) == set() and len(finds) == 5, "pages of one paper are not copies of one another"
    recorded = [dict(base[0], recording=True), base[1]]
    assert copy_figures.copies(recorded) == set() and len(finds) == 6, "a recording is not compared"
    assert copy_figures.copies(base[:1]) == set() and copy_figures.copies(base[::-1]) == {frozenset({("t1:d1", 3), ("t1:d2", 1)})}
    assert len(finds) == 8, "fewer pages, or the same pages in another order, are another set"


def test_the_same_words_under_other_ids_are_answered_in_their_own_ids(finds):
    one = copy_figures.differences(two(id="DOC1"))
    other = [dict(p, id=f"DOC{n}") for n, p in enumerate(two(), 7)]
    again = copy_figures.differences(other)
    assert (one[0]["first"]["id"], one[0]["second"]["id"]) == ("DOC1", "DOC1")
    assert (again[0]["first"]["id"], again[0]["second"]["id"]) == ("DOC7", "DOC8")
    assert len(finds) == 1, "the pages say the same, so they were searched once"


def test_what_a_caller_is_given_is_its_own_to_change(finds):
    pages = two()
    told = copy_figures.differences(pages)
    told[0]["figures"][0]["first"] = "changed"
    told[0]["figures"].append({"first": "x", "second": "y", "after": ""})
    told.append("extra")
    copy_figures.copies(pages).clear()
    again = copy_figures.differences(pages)
    assert len(again) == 1 and again[0]["figures"] == [{"first": "6.06", "second": "6.16", "after": again[0]["figures"][0]["after"]}]
    assert copy_figures.copies(pages) == {frozenset({("t1:d1", 3), ("t1:d2", 1)})} and len(finds) == 1


def test_only_the_last_few_sets_are_kept_and_the_one_asked_for_most_recently_is_the_last_to_go(finds, monkeypatch):
    monkeypatch.setattr(copy_figures, "KEPT", 3)
    sets = [two(first=f"6.{n:02d}", second=f"6.{n + 50:02d}") for n in range(1, 5)]
    for each in sets:
        copy_figures.copies(each)
    assert len(finds) == 4
    copy_figures.copies(sets[1])
    assert len(finds) == 4, "still kept"
    copy_figures.copies(sets[0])
    assert len(finds) == 5, "the first was let go when the fourth came"
    copy_figures.copies(sets[1])
    assert len(finds) == 5, "asked for since, so it outlived the third"
    copy_figures.copies(sets[2])
    assert len(finds) == 6, "the third, asked for longest ago, was let go"


def test_what_is_told_is_what_a_search_of_those_pages_finds():
    rows_a = " ".join(f"survey {n} extent {n}.{n % 40:02d} khata {n * 3}" for n in range(1, 25))
    rows_b = " ".join(f"survey {n + 100} extent {n + 7}.{(n + 5) % 40:02d} khata {n * 3 + 1}" for n in range(1, 25))
    sets = [two(), two("6.06", "6.06"), [page("a.pdf", 1, rows_a, key="a"), page("b.pdf", 1, rows_b, key="b")],
            [page("a.pdf", 1, passage(), key="a"), page("b.pdf", 1, passage("6.16"), key="b"), page("c.pdf", 2, passage("6.26"), key="c")], []]
    for pages in sets:
        direct = list(copy_figures._pairs(pages))
        assert copy_figures.copies(pages) == {frozenset({(pages[i]["key"], pages[i]["page"]), (pages[j]["key"], pages[j]["page"])})
                                              for i, j, _ in direct}
        assert [(f["first"]["page"], f["second"]["page"], f["figures"]) for f in copy_figures.differences(pages)] == [
            (pages[i]["page"], pages[j]["page"], figures) for i, j, figures in direct if figures]


def test_pages_given_as_a_stream_are_read_as_the_set_they_make(finds):
    pages = two()
    assert copy_figures.copies(iter(pages)) == copy_figures.copies(pages) and len(finds) == 1


def test_many_askers_at_once_are_all_told_the_same():
    pages = two()
    told, errors = [], []

    def ask():
        try:
            told.append((copy_figures.copies(pages), copy_figures.differences(pages)))
        except Exception as exc:  # noqa: BLE001 - the test reports what went wrong
            errors.append(exc)
    threads = [threading.Thread(target=ask) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == [] and len(told) == 12 and all(each == told[0] for each in told)
