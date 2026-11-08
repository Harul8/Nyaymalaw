"""A short name the owner has checked proposes the held Act it names, and only then (plan AN.47, piece 47a; D129-D131).

Before this a plan naming "the Evidence Act" was told no held Act had that name, because the held Act is "Indian Evidence Act, 1872". The
owner's checked list of short forms (pipeline/act_aliases.json) now proposes the Act, as a search candidate and never as a resolved identity.
Synthetic alias lists and held keys: what the real list reaches is measured against the real register, not here."""
from __future__ import annotations

import pytest

from nm.shared.citation_contracts import act_alias_index, instrument_candidates

HELD = frozenset({"indian evidence act 1872", "bharatiya sakshya adhiniyam 2023", "consumer protection act 1986",
                  "consumer protection act 2019", "indian penal code 1860"})


def entry(ways, acts, checked=True):
    return {"as_written": ways, "acts": acts, "checked": checked}


def act(key, title, start, end=None):
    return {"key": key, "title": title, "from": start, "to": end}


def listing(*entries):
    return {"schema": 1, "status": "synthetic", "aliases": list(entries)}


def candidates(name, *entries, held=HELD):
    return instrument_candidates(name, held, act_alias_index(listing(*entries)) if entries else None)


IEA = act("indian evidence act 1872", "Indian Evidence Act, 1872", 1872, 2024)
BSA = act("bharatiya sakshya adhiniyam 2023", "Bharatiya Sakshya Adhiniyam, 2023", 2023)
ONE = entry(["Evidence Act"], [IEA])
TWO = entry(["Evidence Act"], [IEA, BSA])


def test_without_the_list_a_short_name_finds_nothing_as_before():
    assert candidates("Evidence Act") == ()
    assert candidates("The Evidence Act") == ()


def test_a_checked_short_name_proposes_the_held_act_it_names():
    assert candidates("Evidence Act", ONE) == ("indian evidence act 1872",)
    assert candidates("the Evidence Act", ONE) == ("indian evidence act 1872",)


def test_a_draft_entry_proposes_nothing():
    assert candidates("Evidence Act", entry(["Evidence Act"], [IEA], checked=False)) == ()


def test_a_short_name_for_several_acts_keeps_every_held_one_so_the_ambiguity_is_asked_about():
    assert candidates("Evidence Act", TWO) == ("bharatiya sakshya adhiniyam 2023", "indian evidence act 1872")


def test_an_act_the_library_does_not_hold_proposes_nothing_and_a_held_sister_is_still_proposed():
    assert candidates("Evidence Act", TWO, held=HELD - {"bharatiya sakshya adhiniyam 2023"}) == ("indian evidence act 1872",)
    not_held = entry(["Arbitration Act"], [act("arbitration and conciliation act 1996", "Arbitration and Conciliation Act, 1996", 1996)])
    assert candidates("Arbitration Act", not_held) == ()
    assert candidates("Evidence Act", entry(["Evidence Act"], [{**IEA, "key": None}])) == ()


def test_a_year_written_beside_the_short_name_must_be_the_first_year_of_an_act_it_names():
    assert candidates("Evidence Act, 1872", TWO) == ("indian evidence act 1872",)
    assert candidates("Evidence Act 2023", TWO) == ("bharatiya sakshya adhiniyam 2023",)
    assert candidates("Evidence Act, 1995", TWO) == ()


def test_a_name_that_finds_an_act_by_itself_is_not_changed_by_an_alias():
    steering = entry(["Consumer Protection Act"], [act("consumer protection act 2019", "Consumer Protection Act, 2019", 2019)])
    assert candidates("Consumer Protection Act", steering) == ("consumer protection act 1986", "consumer protection act 2019")
    assert candidates("Indian Evidence Act, 1872", ONE) == ("indian evidence act 1872",)
    assert candidates("Consumer Protection Act, 1950", steering) == ("consumer protection act 1986", "consumer protection act 2019")


def test_a_name_on_no_list_and_held_by_no_title_is_still_not_guessed():
    assert candidates("Evidence Law", ONE) == ()
    assert candidates("Penal Law", ONE) == ()
    assert candidates("", ONE) == ()


@pytest.mark.parametrize("held", [frozenset(), set(), ()])
def test_no_held_instruments_means_no_candidates_by_any_route(held):
    assert candidates("Evidence Act", ONE, held=held) == ()
