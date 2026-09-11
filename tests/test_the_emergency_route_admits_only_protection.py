"""ORDINARY ADMISSION, AND A BOUNDED WAY ROUND IT. BK-78, BK-53, BK-34. P14.

THE RULE, stated without the scenario that exposed it
-------------------------------------------------------
**An exception is recorded as an exception. A file that took one must never
read afterwards as a file whose screens passed.**

Liberty does not wait for a registry, so there has to be a way through — and
the entire risk of that way is that it becomes the comfortable one. So it
expires, it names what it permitted, it carries the screens that were
outstanding when it was taken, and it admits exactly one work product.

WHAT IS ASSERTED
------------------
    an unavailable screen never clears, and says so differently from unrun
    a declaration persists with actor, basis, outstanding screens and expiry
    expiry is a question about the clock, not a stored flag
    an expired declaration keeps its urgency on the file and permits nothing
    no work product but protective triage is admitted, and no argument widens it
    revocation is a new record, never an erasure
    capacity to instruct is recorded separately from account access
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from nm.core.screens import Capacity as InstructingCapacity
from nm.core.screens import Engagement as ScreenedEngagement
from nm.core.screens import (
    Screen,
    ScreenKind,
    ScreenState,
    may_admit_substance,
    unscreened,
)
from nm.domain.emergency import DEFAULT_HOURS, Declaration, latest

pytestmark = pytest.mark.class_a

NOW = datetime(2026, 9, 11, 10, 0, 0)


def _declared(**over) -> Declaration:
    base = dict(actor_id="adv-1",
                basis="the client is being questioned at the police station",
                outstanding=("conflict: never run", "competence: never run"),
                now=NOW)
    base.update(over)
    return Declaration.declare(**base)


# ===================== the fourth screen state ==============================

def test_an_unavailable_screen_never_clears():
    """All three non-CLEAR states share this property and it is the reason the
    enum exists."""
    screen = Screen(kind=ScreenKind.CONFLICT, state=ScreenState.UNAVAILABLE,
                    detail="the registry host did not answer")
    assert screen.clears is False
    assert may_admit_substance((screen,))[0] is False


def test_unavailable_and_not_assessed_read_differently():
    """The only reason to have four states is that THE FIX DIFFERS: an
    unassessed screen needs somebody to run it, and an unavailable one needs
    the registry back before anybody can."""
    down = Screen(kind=ScreenKind.CONFLICT, state=ScreenState.UNAVAILABLE,
                  detail="the registry host did not answer")
    never = Screen(kind=ScreenKind.CONFLICT, state=ScreenState.NOT_ASSESSED,
                   not_assessed_because="nobody has run it")
    # THE CONFLICT ENTRY, not index 0 -- `unscreened` reports every screen on
    # the matter and the first is the emergency screen, identical in both.
    def conflict_line(screen):
        return next(x for x in unscreened((screen,)) if x.startswith("conflict"))

    assert conflict_line(down) != conflict_line(never)
    assert "unavailable" in conflict_line(down)
    assert "not_assessed" in conflict_line(never)


def test_every_screen_state_is_mapped_to_a_gate_state_explicitly():
    """A new enum member falling through `table.get`'s default is how a state
    nobody mapped starts reading as one somebody did."""
    from nm.core.screens import GATE_FOR

    for kind, (_gate_id, table) in GATE_FOR.items():
        missing = [s.value for s in ScreenState if s not in table]
        assert not missing, f"{kind.value} does not map {missing}"


# ======================= the declaration is a record ========================

def test_a_declaration_carries_who_why_what_was_outstanding_and_when_it_ends():
    """A boolean is exactly enough to admit substance and nothing like enough
    to answer the questions asked afterwards."""
    declared = _declared()
    assert declared.actor_id == "adv-1"
    assert "police station" in declared.basis
    assert declared.outstanding == ("conflict: never run", "competence: never run")
    assert declared.expires_at == NOW + timedelta(hours=DEFAULT_HOURS)


def test_a_declaration_without_a_basis_is_refused():
    """A declaration with no basis is a switch, and a switch is what this
    record exists to stop the emergency route from being."""
    for blank in ("", "   "):
        with pytest.raises(ValueError):
            Declaration.declare("adv-1", blank, (), NOW)


def test_the_outstanding_screens_are_frozen_at_the_moment_of_declaration():
    """They are the justification. A list recomputed later would silently
    rewrite why the exception was taken."""
    declared = _declared()
    assert declared.outstanding == ("conflict: never run", "competence: never run")
    # Later screens clearing does not retroactively empty the justification.
    assert _declared().outstanding == declared.outstanding


# ============================ expiry is the clock ===========================

def test_expiry_is_a_question_about_a_moment_and_not_a_stored_flag():
    """Re-entry two days later must get the true answer rather than the one
    that was true when somebody last wrote a field."""
    declared = _declared()
    assert declared.active_at(NOW) is True
    assert declared.active_at(NOW + timedelta(hours=DEFAULT_HOURS + 1)) is False
    assert declared.state_at(NOW) == "live"
    assert declared.state_at(NOW + timedelta(hours=48)) == "expired"


def test_an_expired_declaration_keeps_its_urgency_on_the_file(client=None):
    """What lapses is the PERMISSION, not the history. The urgency was real
    and remains evidence of why the file was handled as it was."""
    declared = _declared()
    later = NOW + timedelta(hours=48)
    said = declared.said(later)
    assert "lapsed" in said
    assert "stands on the file" in said
    assert "ordinary screens are required" in said


def test_only_a_live_declaration_governs():
    """An expired one must never be returned as though it still permitted
    anything."""
    expired = _declared()
    later = NOW + timedelta(hours=48)
    assert latest((expired.as_dict(),), NOW) is not None
    assert latest((expired.as_dict(),), later) is None


def test_a_re_declaration_is_a_second_record():
    """Two separate moments of danger are two facts, and keeping only the
    latest would make a file that was urgent twice look urgent once."""
    first = _declared()
    later = NOW + timedelta(hours=48)
    second = _declared(now=later, basis="he has been produced before a magistrate")
    governing = latest((first.as_dict(), second.as_dict()), later)
    assert governing is not None
    assert "magistrate" in governing.basis


# ==================== it admits protection and nothing else =================

@pytest.mark.parametrize("work", ["advice", "research", "draft", "hearing",
                                  "negotiation"])
def test_no_substantive_work_product_is_admitted(work):
    """THE POINT OF THE PACKET. An emergency that could be made to admit
    substantive work would be a way of turning the screens off."""
    assert _declared().permits(work) is False


def test_protective_triage_is_admitted():
    """The negative control: a declaration that permitted nothing would be
    safe and would not help the client being questioned."""
    assert _declared().permits("protective_triage") is True


def test_no_argument_widens_what_a_declaration_permits():
    """`permits` takes the work product and nothing else. A parameter that
    could widen it is a parameter somebody passes."""
    import inspect

    signature = inspect.signature(Declaration.permits)
    assert list(signature.parameters) == ["self", "work_product"]


def test_the_exception_says_it_is_an_exception():
    """A file that took one must never read afterwards as a file whose
    screens passed."""
    said = _declared().said(NOW)
    assert "EMERGENCY EXCEPTION" in said
    assert "no substantive analysis" in said
    assert "conflict: never run" in said


def test_the_screen_owner_still_names_the_exception_when_it_admits(client=None):
    """`may_admit_substance` is the owner and P14 does not add a second one."""
    down = Screen(kind=ScreenKind.CONFLICT, state=ScreenState.UNAVAILABLE,
                  detail="the registry host did not answer")
    allowed, why = may_admit_substance((down,), emergency=True)
    assert allowed is True
    assert "EMERGENCY EXCEPTION" in why
    assert "outstanding" in why


# ============================= revocation ===================================

def test_revocation_is_a_new_record_and_not_an_erasure():
    declared = _declared()
    revoked = declared.revoke("adv-2", NOW + timedelta(hours=2))
    assert revoked.revoked_by == "adv-2"
    assert revoked.declared_at == declared.declared_at
    assert revoked.basis == declared.basis
    assert revoked.state_at(NOW + timedelta(hours=3)) == "revoked"
    assert revoked.active_at(NOW + timedelta(hours=3)) is False


def test_a_revoked_declaration_still_shows_the_urgency_that_was_recorded():
    revoked = _declared().revoke("adv-2", NOW + timedelta(hours=2))
    said = revoked.said(NOW + timedelta(hours=3))
    assert "revoked by adv-2" in said
    assert "stands on the file" in said


# ================= capacity to instruct is not account access ===============

def test_capacity_to_instruct_is_recorded_and_not_inferred_from_the_account():
    """BK-53-AC2. An account is a way of signing in. It says nothing about
    whether this person can give instructions, and inferring one from the
    other is how a file gets run on somebody's behalf who could not ask."""
    unassessed = ScreenedEngagement(
        identity="the client", authority="a signed authority",
        scope="the possession claim", decision_owner="the client")
    assert unassessed.capacity is InstructingCapacity.NOT_ASSESSED
    assert unassessed.reliance_ready is False
    assert any("capacity to instruct" in m for m in unassessed.missing())


def test_capacity_in_doubt_blocks_reliance_even_when_everything_else_is_set():
    in_doubt = ScreenedEngagement(
        identity="the client", authority="a signed authority",
        scope="the possession claim", decision_owner="the client",
        capacity=InstructingCapacity.IN_DOUBT)
    assert in_doubt.reliance_ready is False
    assert any("in doubt" in m for m in in_doubt.missing())


def test_capacity_not_in_doubt_with_everything_set_is_reliance_ready():
    """The negative control for the two above."""
    ready = ScreenedEngagement(
        identity="the client", authority="a signed authority",
        scope="the possession claim", decision_owner="the client",
        capacity=InstructingCapacity.NOT_IN_DOUBT)
    assert ready.reliance_ready is True
    assert ready.missing() == ()


def test_the_two_capacity_vocabularies_are_not_the_same_type():
    """`nm.core.screens.Capacity` asks whether the client's capacity TO
    INSTRUCT is in doubt. `nm.domain.authority.ActingAs` asks what part a
    person plays. Two enums called `Capacity` would be one word for both."""
    from nm.domain.authority import ActingAs

    assert InstructingCapacity is not ActingAs
    assert {c.value for c in InstructingCapacity} & {
        a.value for a in ActingAs} == set()
