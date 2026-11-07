"""The list of short forms and abbreviations judgments use for Acts (plan AN.45, D104) is written by Claude and CHECKED BY THE OWNER:
pipeline/act_aliases.json. It is read whole (the shape is exact), every held Act it names is a kept instrument of the one-copy
register, no two entries claim one way of writing, and an entry that has not been checked resolves nothing - so a draft can sit in
the repository without ever deciding what an Act is. Which Act a short form means is the owner's word, not this test's."""
import json
from pathlib import Path

import pytest

from nm.shared.citation_contracts import ActResolver, act_alias_index, instrument_key

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


def listed():
    return json.loads((ROOT / "pipeline" / "act_aliases.json").read_text(encoding="utf-8"))


def held_keys():
    register = json.loads((ROOT / "pipeline" / "instrument_copies.json").read_text(encoding="utf-8"))["documents"]
    return {entry["group"] for entry in register.values() if entry.get("role") == "kept" and entry.get("group")}


def test_the_list_is_read_whole_and_every_held_act_it_names_is_a_kept_instrument():
    document = listed()
    index = act_alias_index(document, checked_only=False)
    assert len(index) >= 50, "a list that names few short forms would prove little"
    kept = held_keys()
    named = {act["key"] for entry in document["aliases"] for act in entry["acts"] if act["key"] is not None}
    assert named and named <= kept, sorted(named - kept)
    for entry in document["aliases"]:
        assert all(act["from"] is None or act["to"] is None or act["from"] <= act["to"] for act in entry["acts"]), entry["as_written"]


def test_an_entry_the_owner_has_not_checked_resolves_nothing_and_one_they_have_does():
    document = listed()
    index = act_alias_index(document)
    for entry in document["aliases"]:
        assert all((instrument_key(way) in index) == entry["checked"] for way in entry["as_written"]), entry["as_written"]
    everything = ActResolver(held_keys(), act_alias_index(document, checked_only=False))
    answer = everything.resolve("NDPS Act", 1999)
    assert answer["state"] == "held" and answer["keys"] == ["narcotic drugs and psychotropic substances act 1985"]
    assert everything.resolve("Arbitration Act", 1985)["named"] == ["Arbitration Act, 1940"], "an Act the library does not hold is named"
    assert everything.resolve("IT Act", 2012)["state"] == "ambiguous", "income tax or information technology"
