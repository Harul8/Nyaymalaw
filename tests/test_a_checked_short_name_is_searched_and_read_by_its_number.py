"""The search meets the owner's checked short names of Acts (plan AN.47, piece 47b; D129, D131-D133).

A plan that names "the Contract Act" or a section of "the Relief Act" was told no held Act had that name, because the held Acts are
"Indian Contract Act, 1872" and so on. HybridSearcher now carries the owner's checked list: a short name proposes the held Act it names,
for the Acts a plan names (searched inside) and for the sections a plan names (read by number). A list that cannot be read costs only
the short names. The Acts and sections are invented, except where the real list is loaded to see that it loads."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from nm.core_engine import research, retrieval
from nm.core_engine.retrieval import HybridSearcher, checked_aliases, validate_search
from nm.shared.citation_contracts import act_alias_index
from tests.test_core_search_named_instruments import collection
from tests.test_current_brain_retrieval import QUERIES, Collection
from tests.test_the_law_a_question_names_is_read_by_its_number import KEY, Named
from tests.test_the_law_a_question_names_is_read_by_its_number import QUERIES as SECTION_QUERIES

pytestmark = pytest.mark.class_a


def listing(ways, key, title, start, checked=True):
    return {"schema": 1, "status": "synthetic", "aliases": [
        {"as_written": ways, "acts": [{"key": key, "title": title, "from": start, "to": None}], "checked": checked}]}


CONTRACT = act_alias_index(listing(["Contract Act"], "indian contract act 1872", "Indian Contract Act, 1872", 1872))
RELIEF = act_alias_index(listing(["Relief Act"], KEY, "Imagined Relief Act, 1907", 1907))


def test_a_checked_short_name_is_searched_inside_the_act_it_names(tmp_path, monkeypatch):
    (tmp_path / "without").mkdir()
    (tmp_path / "with").mkdir()
    held, calls = collection(tmp_path / "without", monkeypatch)
    plain = HybridSearcher({"provision": held, "judgment": Collection("judgment")}).search(QUERIES, ["Contract Act"])
    assert plain["instruments"] == [{"name": "Contract Act", "candidates": []}]
    assert ("words", [0]) not in calls
    held, calls = collection(tmp_path / "with", monkeypatch)
    with_list = HybridSearcher({"provision": held, "judgment": Collection("judgment")}, aliases=CONTRACT).search(QUERIES, ["Contract Act"])
    assert with_list["instruments"] == [{"name": "Contract Act", "candidates": ["indian contract act 1872"]}]
    assert ("words", [0]) in calls and ("vectors", [0]) in calls
    assert with_list["contract"] == retrieval.ONE_READING_CONTRACT == plain["contract"]


def test_a_section_named_under_a_short_name_is_read_by_its_number_and_without_the_list_is_not_held():
    named = [{"act": "Relief Act", "section": "6"}]

    def searched(aliases):
        return HybridSearcher({"provision": Named(), "judgment": Collection("judgment")}, aliases=aliases).search(
            SECTION_QUERIES, ["Relief Act"], results=research.FOR_PICK, named=named)
    without = searched(None)
    assert [(entry["state"], entry["reason"]) for entry in without["named"]] == [("not_held", "No Act we hold is this name")]
    read = searched(RELIEF)
    assert [entry["state"] for entry in read["named"]] == ["read"] and len(read["named_found"]) == 1
    assert read["named_found"][0]["position"] == 7 and read["named"][0]["found"] == [read["named_found"][0]["id"]]
    assert read["instruments"] == [{"name": "Relief Act", "candidates": [KEY]}]
    assert validate_search(read, SECTION_QUERIES, ["Relief Act"], named) == read


def test_the_list_is_read_for_its_checked_entries_only(tmp_path):
    document = listing(["Relief Act"], KEY, "Imagined Relief Act, 1907", 1907)
    document["aliases"].append({"as_written": ["Draft Act"], "acts": [{"key": KEY, "title": "x", "from": None, "to": None}], "checked": False})
    path = tmp_path / "act_aliases.json"
    path.write_text(json.dumps(document), encoding="utf8")
    index = checked_aliases(path)
    assert sorted(index) == ["relief act"]


@pytest.mark.parametrize("content", [None, "{not json", json.dumps({"schema": 2, "aliases": []}), json.dumps({"schema": 1, "aliases": "x"}),
                                     json.dumps(listing(["A Act", "A Act"], "k", "t", 1)["aliases"] * 2)])
def test_a_list_that_cannot_be_used_costs_only_the_short_names_and_says_so(tmp_path, caplog, content):
    path = tmp_path / "act_aliases.json"
    if content is not None:
        path.write_text(content, encoding="utf8")
    with caplog.at_level(logging.WARNING, logger=retrieval.log.name):
        assert checked_aliases(path) == {}
    assert "Act alias list cannot be used" in caplog.text


def test_two_entries_claiming_one_way_of_writing_cost_the_short_names_not_the_search(tmp_path, caplog):
    twice = listing(["Relief Act"], KEY, "Imagined Relief Act, 1907", 1907)
    twice["aliases"].append(twice["aliases"][0] | {"acts": [{"key": None, "title": "Other", "from": 1, "to": None}]})
    path = tmp_path / "act_aliases.json"
    path.write_text(json.dumps(twice), encoding="utf8")
    assert checked_aliases(path) == {}


def test_the_owners_real_list_is_one_the_product_can_read():
    index = checked_aliases(Path(__file__).resolve().parents[1] / "pipeline" / "act_aliases.json")
    assert len({id(entry) for entry in index.values()}) == 59 and "evidence act" in index
