"""A section named in an Act of a year we do not hold is not read from the Act of another year (plan AN.51, 51a; D195; the
review's F-02; D228's fifth test; AN.48 register item 8).

A plan that named section 6 of an Act "of 1890" was read section 6 of the held Act of 1907, because a name whose year no held
copy carries proposed every held Act of that title - right for ranking a search, wrong for showing a section's words under a
name the advocate wrote: section 6 of one year's Act is not section 6 of another's. The search still proposes the held Act;
the reading by number says 'not held', with code's reason. The judgments' resolver already answered a written year this
way. The Act and its sections are invented.
"""
from __future__ import annotations

import pytest

from nm.core_engine import research, retrieval
from nm.core_engine.retrieval import HybridSearcher, validate_search
from nm.shared.citation_contracts import (
    ANOTHER_YEAR_HELD, ActResolver, act_alias_index, instrument_candidates, instruments_to_read,
)
from tests.test_current_brain_retrieval import Collection
from tests.test_the_law_a_question_names_is_read_by_its_number import ACT, KEY, QUERIES, Named

pytestmark = pytest.mark.class_a
OF_ANOTHER_YEAR = "Imagined Relief Act, 1890"
WITHOUT_A_YEAR = "Imagined Relief Act"
HELD = frozenset({KEY})


def searched(name, aliases=None):
    named = [{"act": name, "section": "6"}]
    record = HybridSearcher({"provision": Named(), "judgment": Collection("judgment")}, aliases=aliases).search(
        QUERIES, [name], results=research.FOR_PICK, named=named)
    assert validate_search(record, QUERIES, [name], named) == record
    return record


def test_a_section_of_the_act_of_a_year_not_held_is_not_held_and_never_read():
    record = searched(OF_ANOTHER_YEAR)
    (entry,) = record["named"]
    assert (entry["state"], entry["found"], entry["reason"]) == ("not_held", [], ANOTHER_YEAR_HELD)
    assert record["named_found"] == []


def test_the_search_is_still_ranked_by_the_held_act_of_that_title():
    assert searched(OF_ANOTHER_YEAR)["instruments"] == [{"name": OF_ANOTHER_YEAR, "candidates": [KEY]}]
    assert instrument_candidates(OF_ANOTHER_YEAR, HELD) == (KEY,)


@pytest.mark.parametrize("name", [ACT, WITHOUT_A_YEAR])
def test_the_year_held_and_a_name_without_a_year_are_read_as_before(name):
    record = searched(name)
    assert [entry["state"] for entry in record["named"]] == ["read"] and len(record["named_found"]) == 1


def test_the_one_rule_says_what_may_be_read_and_why_not():
    assert instruments_to_read(ACT, HELD) == ((KEY,), "")
    assert instruments_to_read(WITHOUT_A_YEAR, HELD) == ((KEY,), "")
    assert instruments_to_read(OF_ANOTHER_YEAR, HELD) == ((), ANOTHER_YEAR_HELD)
    assert instruments_to_read("An Act Nobody Holds, 1999", HELD) == ((), "")
    assert instruments_to_read("", HELD) == ((), "")


def test_a_name_without_a_year_keeps_every_held_act_of_the_title():
    two = frozenset({"imagined relief act 1907", "imagined relief act 1950"})
    assert instruments_to_read(WITHOUT_A_YEAR, two) == (("imagined relief act 1907", "imagined relief act 1950"), "")
    assert instruments_to_read("Imagined Relief Act, 1950", two) == (("imagined relief act 1950",), "")
    assert instruments_to_read(OF_ANOTHER_YEAR, two) == ((), ANOTHER_YEAR_HELD)


def test_a_checked_short_name_with_its_acts_year_is_read_and_with_another_year_is_not():
    short = act_alias_index({"schema": 1, "status": "synthetic", "aliases": [
        {"as_written": ["Relief Act"], "acts": [{"key": KEY, "title": ACT, "from": 1907, "to": None}], "checked": True}]})
    assert instruments_to_read("Relief Act", HELD, short) == ((KEY,), "")
    assert instruments_to_read("Relief Act, 1907", HELD, short) == ((KEY,), "")
    assert instruments_to_read("Relief Act, 1890", HELD, short) == ((), "")
    assert [entry["state"] for entry in searched("Relief Act, 1907", short)["named"]] == ["read"]
    assert [entry["state"] for entry in searched("Relief Act, 1890", short)["named"]] == ["not_held"]


def test_the_judgments_resolver_answers_a_written_year_the_same_way():
    resolver = ActResolver(HELD)
    assert resolver.resolve(OF_ANOTHER_YEAR)["state"] == "not_held"
    assert resolver.resolve(ACT)["keys"] == [KEY]
    assert resolver.resolve(WITHOUT_A_YEAR)["keys"] == [KEY]


def test_the_search_record_keeps_its_contract():
    assert searched(OF_ANOTHER_YEAR)["contract"] == retrieval.CONTRACT
