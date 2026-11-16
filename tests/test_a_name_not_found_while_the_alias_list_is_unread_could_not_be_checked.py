"""A name that finds no Act while the checked short names could not be read is 'could not be checked', not 'not held' (plan
AN.51, 51g; D204; the review's F-24; AN.48 register item 9).

The owner's checked list of short names (pipeline/act_aliases.json) is what makes "the Relief Act" the held "Imagined Relief
Act, 1907". When the list could not be read the search went on without it - rightly - and then told the advocate that no held
Act had that name: an absence it had not established. The unread state is now carried with the (empty) index: a named section
whose Act finds nothing is recorded as unavailable with code's reason, and a search whose plan named such an Act carries the
gap, so it is 'partial'. A name that finds its Act without the list is read as before. The Acts are invented.
"""
from __future__ import annotations

import json

import pytest

from nm.core_engine import research, retrieval
from nm.core_engine.retrieval import ALIASES_UNREAD, HybridSearcher, UnreadAliases, checked_aliases, validate_search
from nm.shared.citation_contracts import ANOTHER_YEAR_HELD
from tests.test_current_brain_retrieval import Collection
from tests.test_the_law_a_question_names_is_read_by_its_number import ACT, QUERIES, Named

pytestmark = pytest.mark.class_a


def unread(tmp_path):
    return checked_aliases(tmp_path / "no-such-list.json")


def searched(name, aliases, section="6"):
    named = [{"act": name, "section": section}]
    record = HybridSearcher({"provision": Named(), "judgment": Collection("judgment")}, aliases=aliases).search(
        QUERIES, [name], results=research.FOR_PICK, named=named)
    assert validate_search(record, QUERIES, [name], named) == record
    return record


@pytest.mark.parametrize("content", [None, "{not json", json.dumps({"schema": 2, "aliases": []})])
def test_a_list_that_cannot_be_read_says_that_it_is_unread(tmp_path, content):
    path = tmp_path / "act_aliases.json"
    if content is not None:
        path.write_text(content, encoding="utf8")
    index = checked_aliases(path)
    assert index == {} and isinstance(index, UnreadAliases) and index.unavailable


def test_a_list_that_is_read_and_is_empty_is_not_unread(tmp_path):
    path = tmp_path / "act_aliases.json"
    path.write_text(json.dumps({"schema": 1, "status": "synthetic", "aliases": []}), encoding="utf8")
    assert not getattr(checked_aliases(path), "unavailable", "")


def test_a_named_section_whose_act_finds_nothing_could_not_be_checked(tmp_path):
    record = searched("Relief Act", unread(tmp_path))
    (entry,) = record["named"]
    assert (entry["state"], entry["found"], entry["reason"]) == ("unavailable", [], ALIASES_UNREAD)
    assert record["state"] == "partial"
    assert {"kind": "provision", "query_id": None, "stage": "instruments", "reason": ALIASES_UNREAD} in record["issues"]


def test_with_the_list_read_the_same_name_is_not_held_as_before():
    record = searched("Relief Act", {})
    assert [(entry["state"], entry["reason"]) for entry in record["named"]] == [("not_held", "No Act we hold is this name")]
    assert not any(issue["stage"] == "instruments" for issue in record["issues"])


def test_a_name_that_finds_its_act_without_the_list_is_read_and_carries_no_gap(tmp_path):
    record = searched(ACT, unread(tmp_path))
    assert [entry["state"] for entry in record["named"]] == ["read"]
    assert not any(issue["stage"] == "instruments" for issue in record["issues"])


def test_what_the_list_could_not_change_keeps_its_own_answer(tmp_path):
    """A year no held Act of the title carries is not held whatever the list says; so is a number the held Act does not have."""
    another_year = searched("Imagined Relief Act, 1890", unread(tmp_path))
    assert [(entry["state"], entry["reason"]) for entry in another_year["named"]] == [("not_held", ANOTHER_YEAR_HELD)]
    no_such_section = searched(ACT, unread(tmp_path), section="99")
    assert [entry["state"] for entry in no_such_section["named"]] == ["not_held"]


def test_the_search_record_keeps_its_contract(tmp_path):
    assert searched("Relief Act", unread(tmp_path))["contract"] == retrieval.CONTRACT
