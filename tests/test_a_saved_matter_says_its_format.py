"""A saved matter says its format, and what this code would drop is refused (plan AN.50, piece 50g2; D193; the review's F-34).

The reader builds a matter from the fields the running code declares, so after the code was rolled back, a matter saved by newer
code loaded without error, lost the newer fields, and the next save wrote it back without them - a silent downgrade of a saved
conversation (P46). Each save now says the format of what it saved. Code never opens a format newer than its own, and refuses a
record of its own format that holds a field it does not declare; a matter saved before matters said their format reads as it
always did. The stored shape of each format is pinned here, so a field added without moving the number on fails this file.
Offline: a temporary store and invented matters.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from types import UnionType
from typing import Union, get_args, get_origin, get_type_hints

import pytest

from nm.shared import store_file_store
from nm.shared.store_file_store import MATTER_FORMAT, FileMatterStore, SavedShapeUnknown
from nm.work_the_file.matter_contracts import Fact, Matter, Provenance

pytestmark = pytest.mark.class_a
KEY = "matter-format-control-" + "k" * 24

#: The stored shape of each format: every type a matter is rebuilt from, with its declared fields, hashed. A CHANGE HERE IS A
#: CHANGE OF FORMAT: move MATTER_FORMAT on by one in nm/shared/store_file_store.py and add the new number's shape below; never
#: replace the shape of a number that matters have been saved as.
SHAPES = {1: "67eec533a1b5bd90b23aa406d8fd937eeb25cbd73b977c70556ce04117fd69de"}


def stored_shape():
    """Every dataclass the reader builds a matter from, by the reader's own walk, with its declared fields."""
    seen = {}

    def walk(cls):
        origin = get_origin(cls)
        if origin in (Union, UnionType):
            inner = [each for each in get_args(cls) if each is not type(None)]
            return walk(inner[0]) if inner else None
        if origin in (tuple, list, set, frozenset):
            return walk(get_args(cls)[0]) if get_args(cls) else None
        if isinstance(cls, type) and is_dataclass(cls) and cls.__name__ not in seen:
            seen[cls.__name__] = sorted(field.name for field in fields(cls))
            hints = get_type_hints(cls)
            for field in fields(cls):
                walk(hints.get(field.name, object))
        return None
    walk(Matter)
    return hashlib.sha256(json.dumps(sorted(seen.items())).encode("utf8")).hexdigest()


def test_the_stored_shape_is_the_one_pinned_for_this_format():
    assert MATTER_FORMAT in SHAPES, "a new format's shape is pinned here when the number is moved on"
    assert stored_shape() == SHAPES[MATTER_FORMAT], (
        "a field a saved matter holds was added, taken away or renamed without moving MATTER_FORMAT on: code rolled back "
        "from this version would open such a matter and save it back without the field. Move the number on by one and pin "
        "the new shape")
    assert store_file_store._FORMAT_KEY not in {field.name for field in fields(Matter)}


@pytest.fixture
def store(tmp_path):
    kept = FileMatterStore(tmp_path / "store", key=KEY)
    fact = Fact(id="fact-1", statement="An invented fact.", provenance=Provenance(kind="advocate_statement", turn="turn-1"))
    kept.commit(Matter(id="matter-1", advocate_id="adv", title="First", version=1, facts=(fact,)), expected_version=0)
    return kept


def document(store):
    return json.loads(store._open("matter-1", (store._matters / "matter-1.nm").read_bytes()))


def rewritten(store, change):
    """The saved matter as other code would have saved it: its document changed, sealed again, and its record of the last save
    (50e), which was of the file as it was, taken away."""
    changed = document(store)
    change(changed)
    (store._matters / "matter-1.nm").write_bytes(store._seal("matter-1", json.dumps(changed).encode("utf8")))
    (store._root / "saved-versions" / "matter-1.json").unlink(missing_ok=True)
    return (store._matters / "matter-1.nm").read_bytes()


def test_a_save_says_the_format_of_what_it_saved_and_reads_back(store):
    assert document(store)["stored_format"] == MATTER_FORMAT
    loaded = store.load("matter-1")
    assert loaded.title == "First" and loaded.facts[0].statement == "An invented fact."
    assert [matter.title for matter in store.list_for("adv")] == ["First"]


def test_a_matter_saved_by_newer_code_is_not_opened_not_saved_over_and_listed_as_unreadable(store):
    def as_newer_code_saves(changed):
        changed["stored_format"] = MATTER_FORMAT + 1
        changed["a_field_of_newer_code"] = {"kept": "by the newer code"}
    saved = rewritten(store, as_newer_code_saves)

    with pytest.raises(SavedShapeUnknown, match="newer code saved it"):
        store.load("matter-1")
    with pytest.raises(SavedShapeUnknown):
        store.commit(Matter(id="matter-1", advocate_id="adv", title="Saved by the older code", version=2), expected_version=1)
    assert (store._matters / "matter-1.nm").read_bytes() == saved, "the file is as the newer code left it"
    listed = store.list_for("adv")
    assert listed.matters == () and listed.unreadable == ("matter-1",)


@pytest.mark.parametrize("where", ["the matter", "a fact inside it"])
def test_a_record_of_this_format_holding_a_field_this_code_does_not_declare_is_refused_not_stripped(store, where):
    def with_an_undeclared_field(changed):
        (changed if where == "the matter" else changed["facts"][0])["a_field_nobody_declared"] = "words of the client"
    rewritten(store, with_an_undeclared_field)
    with pytest.raises(SavedShapeUnknown) as refused:
        store.load("matter-1")
    assert "a_field_nobody_declared" in str(refused.value) and "words of the client" not in str(refused.value), (
        "the refusal names the field and never what it holds")


@pytest.mark.parametrize("said", [0, -1, "1", 1.5, True, None])
def test_a_format_that_is_not_a_number_this_code_knows_is_refused(store, said):
    rewritten(store, lambda changed: changed.update(stored_format=said))
    with pytest.raises(SavedShapeUnknown):
        store.load("matter-1")


def test_a_matter_saved_before_matters_said_their_format_reads_as_it_always_did_and_its_next_save_says_one(store):
    def as_saved_before(changed):
        del changed["stored_format"]
        changed["a_field_taken_away_since"] = "left by code long gone"
    rewritten(store, as_saved_before)
    loaded = store.load("matter-1")
    assert loaded.title == "First" and loaded.facts[0].statement == "An invented fact."
    store.commit(Matter(id="matter-1", advocate_id="adv", title="Second", version=2), expected_version=1)
    assert document(store)["stored_format"] == MATTER_FORMAT


def test_a_matter_of_an_earlier_format_is_read_as_that_format_and_the_next_is_still_refused(store, monkeypatch):
    """As code one format on reads: the matter saved above says the format before its own."""
    monkeypatch.setattr(store_file_store, "MATTER_FORMAT", MATTER_FORMAT + 1)
    rewritten(store, lambda changed: changed.update(a_field_the_later_format_took_away="x"))
    assert store.load("matter-1").title == "First", "an earlier format may hold what the later one took away"
    rewritten(store, lambda changed: changed.update(stored_format=MATTER_FORMAT + 2))
    with pytest.raises(SavedShapeUnknown):
        store.load("matter-1")
