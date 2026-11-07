"""Who is an admin, and at what level (plan AN.46, piece 46a; owner decisions D117-D118, 7 Nov 2026).

Three access levels: Advocate, Admin and Admin (view only). The server's settings name the two admin levels; every other
account is an advocate. A mistake in the setting locks someone out and never raises anyone."""
from __future__ import annotations

import dataclasses

import pytest

from nm.arrive.admin_access import SETTING, Action, Level, permits, roster_from
from nm.arrive.advocate_contracts import AdvocateIdentity

pytestmark = pytest.mark.class_a


def roster(text):
    return roster_from({SETTING: text})


def test_the_two_levels_are_read_with_the_address_folded_as_every_account_id_is():
    named = roster("  Rahul@Example.TEST : admin , d.shah@chambers.example:VIEW-ONLY ")
    assert named.level_of("rahul@example.test") is Level.ADMIN
    assert named.level_of("RAHUL@example.test ") is Level.ADMIN
    assert named.level_of("d.shah@chambers.example") is Level.VIEW_ONLY
    assert named.rejected == 0
    assert named.named() == (("d.shah@chambers.example", Level.VIEW_ONLY), ("rahul@example.test", Level.ADMIN))


def test_nobody_is_an_admin_when_the_setting_is_absent_empty_or_blank():
    for settings in (None, {}, {SETTING: ""}, {SETTING: "  ,  , "}):
        named = roster_from(settings)
        assert named.named() == () and named.rejected == 0
        assert named.level_of("anyone@example.test") is None


def test_an_address_with_no_level_is_never_an_admin_there_is_no_default_level():
    named = roster("rahul@example.test")
    assert named.level_of("rahul@example.test") is None
    assert named.rejected == 1


def test_a_misspelt_or_unknown_level_locks_the_person_out_and_raises_nobody():
    named = roster("a@example.test:operater,b@example.test:viewer,c@example.test:root,d@example.test:admin")
    assert all(named.level_of(f"{who}@example.test") is None for who in "abc")
    assert named.level_of("d@example.test") is Level.ADMIN
    assert named.rejected == 3


def test_something_that_cannot_be_an_account_id_is_not_an_admin():
    named = roster("not-an-address:admin,../x@example.test:admin,a/b@example.test:admin,ok@example.test:admin")
    assert named.named() == (("ok@example.test", Level.ADMIN),)
    assert named.rejected == 3


def test_an_address_named_twice_at_two_levels_takes_the_lower_whatever_the_order():
    for text in ("a@example.test:admin,a@example.test:view-only", "a@example.test:view-only,a@example.test:admin"):
        named = roster(text)
        assert named.level_of("a@example.test") is Level.VIEW_ONLY
        assert named.rejected == 1
    twice = roster("a@example.test:admin,A@example.test:admin")
    assert twice.level_of("a@example.test") is Level.ADMIN and twice.rejected == 0


def test_a_view_only_admin_may_see_and_change_nothing_and_an_advocate_may_not_even_see():
    changes = [action for action in Action if action is not Action.SEE]
    assert changes, "the area has changes to guard"
    assert permits(Level.ADMIN, Action.SEE) and all(permits(Level.ADMIN, action) for action in changes)
    assert permits(Level.VIEW_ONLY, Action.SEE) and not any(permits(Level.VIEW_ONLY, action) for action in changes)
    assert not any(permits(None, action) for action in Action)


def test_the_roster_cannot_be_changed_after_it_is_read():
    named = roster("a@example.test:view-only")
    with pytest.raises(TypeError):
        named.levels["a@example.test"] = Level.ADMIN
    with pytest.raises(dataclasses.FrozenInstanceError):
        named.rejected = 0


def test_a_strange_id_asked_about_is_simply_not_an_admin():
    named = roster("a@example.test:admin")
    for odd in (None, "", "   ", 7, b"a@example.test", "a@example.test\x00"):
        assert named.level_of(odd) is None


def test_an_account_has_no_field_that_could_carry_a_level_so_the_settings_are_the_only_place():
    fields = {field.name for field in dataclasses.fields(AdvocateIdentity)}
    assert fields.isdisjoint({"admin", "level", "role", "is_admin", "access", "access_level", "permissions"}), fields
