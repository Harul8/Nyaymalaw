"""A CORRECTION REACHES EVERY DEPENDENT CONCLUSION AND NO OTHER. BK-65-AC1. P18.

THE RULE, stated without the scenario that exposed it
-------------------------------------------------------
**Changing a material predicate invalidates every conclusion derived from it,
transitively, and no unrelated conclusion — while preserving the prior state,
the input versions it was computed from, and the reason it changed.**

Both halves fail in opposite directions and both are expensive:

    TOO SMALL   stale advice keeps being served as current. The advocate acted
                on Tuesday against a date that moved on Thursday, and nothing
                on the file says so.
    TOO LARGE   the independent analysis they have already relied on is thrown
                away with the affected one. That trains them to ignore
                invalidation, and then the one that mattered arrives in a
                place they have learned to skip.

WHAT IS ASSERTED
------------------
    a first observation is the input arriving, not a change
    a correction reaches the closure TRANSITIVELY, through derived edges
    an independent conclusion is not touched, re-stamped or re-reasoned
    the prior value, the moved versions and the reason are all kept
    a cycle terminates and is reported rather than hanging
    a node whose dependencies are unrecorded can never be certified current
    rework is bounded, and exhaustion leaves the node STALE and says so
    a stale conclusion cannot be presented as current or released
    staleness survives a restart, because it is persisted and not in a process

EVAL-010's planted negative is the last test here: serving a value derived from
source version 1 as current after version 2 has been accepted must be refused,
and the refusal must name the stale source version rather than saying no.
"""
from __future__ import annotations

import pytest
from nm.core import cascade
from nm.core.dependency import (
    REWORK_LIMIT,
    Currency,
    InputKind,
    Ledger,
    Node,
    Rest,
    claim,
    closure,
    digest_of,
    due,
    from_derived,
    invalidate,
    observe,
    presentable,
    recomputed,
    record,
    released,
    report,
    rework_failed,
    withheld,
)

pytestmark = pytest.mark.class_a

AT = "2026-09-12T10:00:00+05:30"


def _two_issues() -> Ledger:
    """Two independent issues on one file, and a deadline derived from one.

    THE FIXTURE IS THE ARGUMENT. `meeting-timeline` rests on the meeting date;
    `party-role` rests on something else entirely; `filing-deadline` rests on
    the TIMELINE and not on the date, so reaching it at all requires the
    transitive edge that `cascade.Derived.from_facts` cannot express.
    """
    ledger = Ledger()
    ledger, _ = observe(ledger, InputKind.FACT, "source-date",
                        digest_of("Meeting: 02 September 2026"),
                        reason="recorded at intake")
    ledger, _ = observe(ledger, InputKind.FACT, "source-role",
                        digest_of("The client is the plaintiff"),
                        reason="recorded at intake")
    ledger = record(ledger, Node(
        name="meeting-timeline", value="2026-09-02",
        shown="the meeting timeline", computed_at=AT,
        rests_on=(Rest(InputKind.FACT, "source-date"),)))
    ledger = record(ledger, Node(
        name="party-role", value="plaintiff", shown="the party role",
        computed_at=AT, rests_on=(Rest(InputKind.FACT, "source-role"),)))
    ledger = record(ledger, Node(
        name="filing-deadline", value="2026-10-02", shown="the filing deadline",
        computed_at=AT, rests_on=(Rest(InputKind.DERIVED, "meeting-timeline"),)))
    return ledger


def _corrected(ledger: Ledger) -> tuple[Ledger, tuple[str, ...]]:
    ledger, moved = observe(
        ledger, InputKind.FACT, "source-date",
        digest_of("Meeting: 03 September 2026"),
        reason="corrected by adv-1: the meeting was on the 3rd")
    assert moved is True
    return invalidate(
        ledger, (Rest(InputKind.FACT, "source-date", 2),),
        reason="corrected by adv-1: the meeting was on the 3rd", at=AT)


# ======================= observing an input ================================

def test_a_first_observation_is_the_input_arriving_and_not_a_change():
    """Treating version 1 as a move would invalidate everything computed on
    the turn that recorded it — announcing a correction on a file where
    nothing has been corrected, which is §5.4's noise problem exactly."""
    ledger, moved = observe(Ledger(), InputKind.FACT, "f1",
                            digest_of("something"), reason="intake")
    assert moved is False
    assert ledger.input_of(InputKind.FACT, "f1").version == 1


def test_re_observing_the_same_content_is_not_a_change():
    """The ordinary case. A turn that reads the same fact again has not
    corrected it, and a version that bumped on every read would make the
    closure fire on every turn."""
    ledger, _ = observe(Ledger(), InputKind.FACT, "f1", digest_of("same"))
    ledger, moved = observe(ledger, InputKind.FACT, "f1", digest_of("same"))
    assert moved is False
    assert ledger.input_of(InputKind.FACT, "f1").version == 1


def test_changed_content_moves_the_version_and_keeps_the_reason():
    ledger, _ = observe(Ledger(), InputKind.FACT, "f1", digest_of("was"))
    ledger, moved = observe(ledger, InputKind.FACT, "f1", digest_of("now"),
                            reason="corrected by adv-1")
    assert moved is True
    tracked = ledger.input_of(InputKind.FACT, "f1")
    assert tracked.version == 2
    assert "adv-1" in tracked.reason


def test_a_withdrawal_is_kept_apart_from_a_correction():
    """A corrected input yields a new value; a withdrawn one yields none at
    all, and the advocate's next move differs."""
    ledger, _ = observe(Ledger(), InputKind.AUTHORITY, "src-v1",
                        digest_of("held"))
    ledger, moved = observe(ledger, InputKind.AUTHORITY, "src-v1",
                            digest_of("withdrawn"), withdrawn=True,
                            reason="withdrawn from the published corpus")
    assert moved is True
    assert ledger.input_of(InputKind.AUTHORITY, "src-v1").withdrawn is True


# =========================== the closure ====================================

def test_a_correction_reaches_the_dependent_conclusion():
    ledger, affected = _corrected(_two_issues())
    assert "meeting-timeline" in affected
    assert ledger.node("meeting-timeline").currency is Currency.STALE


def test_it_reaches_transitively_through_a_derived_edge():
    """THE EDGE `cascade` CANNOT EXPRESS. `filing-deadline` names no fact at
    all — it rests on the timeline — so a mechanism keyed on fact ids reaches
    it never, however many turns pass."""
    ledger, affected = _corrected(_two_issues())
    assert "filing-deadline" in affected
    assert ledger.node("filing-deadline").currency is Currency.STALE
    assert "fed into" in ledger.node("filing-deadline").stale_because


def test_the_independent_issue_is_left_completely_alone():
    """THE OTHER HALF OF THE CRITERION, and the one a coarse implementation
    loses. Not merely still current — untouched: same value, same reason, same
    timestamp, no revision written against it."""
    before = _two_issues()
    original = before.node("party-role")
    after, affected = _corrected(before)

    assert "party-role" not in affected
    assert after.node("party-role") == original
    assert after.revisions_of("party-role") == ()
    assert after.node("party-role").currency is Currency.CURRENT


def test_a_direct_change_and_an_indirect_one_are_said_differently():
    """'the date you corrected' and 'something the date you corrected fed
    into' are different facts, and an advocate reading the second as the first
    goes looking for a correction they did not make."""
    ledger, _ = _corrected(_two_issues())
    direct = ledger.node("meeting-timeline").stale_because
    indirect = ledger.node("filing-deadline").stale_because
    assert "now version 2" in direct
    assert direct != indirect
    assert "fed into" in indirect
    # AND NEITHER NAMES AN INPUT BY ITS KEY. This asserted the id was in the
    # sentence -- current behaviour, and the leak: an advocate reads
    # `stale_because` on the cover.
    assert "source-date" not in direct and "source-date" not in indirect
    assert "the case-file entry it rests on" in direct


def test_a_cycle_terminates_and_reports_both_nodes():
    """A derived value that rests on itself round a ring is a defect in
    whatever recorded it. A closure that HUNG on one would take the product
    down rather than reporting the ring."""
    ledger = Ledger()
    ledger, _ = observe(ledger, InputKind.FACT, "f1", digest_of("a"))
    ledger = record(ledger, Node(
        name="A", value="1", rests_on=(Rest(InputKind.FACT, "f1"),
                                       Rest(InputKind.DERIVED, "B"))))
    ledger = record(ledger, Node(
        name="B", value="2", rests_on=(Rest(InputKind.DERIVED, "A"),)))
    reached = closure(ledger, (Rest(InputKind.FACT, "f1", 2),))
    assert set(reached) == {"A", "B"}


def test_a_change_to_an_input_nothing_rests_on_reaches_nothing():
    """The negative control for the closure: it must be capable of returning
    empty, or 'it invalidated the right things' is unfalsifiable."""
    ledger = _two_issues()
    after, affected = invalidate(
        ledger, (Rest(InputKind.FACT, "source-unrelated", 2),),
        reason="a fact nothing was derived from", at=AT)
    assert affected == ()
    assert after == ledger


# ============== the prior state, the versions and the reason ================

def test_the_prior_value_is_kept_with_the_reason_it_changed():
    ledger, _ = _corrected(_two_issues())
    revisions = ledger.revisions_of("meeting-timeline")
    assert len(revisions) == 1
    assert revisions[0].was == "2026-09-02"
    assert revisions[0].now == ""      # not recomputed yet, and says so
    assert "adv-1" in revisions[0].reason
    assert revisions[0].at == AT


def test_both_source_versions_survive_the_correction():
    """EVAL-010's `history.source_versions` — `{1, 2}`. Recomputing re-stamps
    the node with version 2, so without the prior edge record the file would
    hold no evidence that version 1 was ever relied on."""
    ledger, _ = _corrected(_two_issues())
    assert ledger.source_versions("meeting-timeline") == (1, 2)

    ledger = recomputed(ledger, "meeting-timeline", "2026-09-03", at=AT)
    assert ledger.source_versions("meeting-timeline") == (1, 2)


def test_recomputing_closes_the_revision_rather_than_opening_a_second():
    """One correction is one entry with a `was` and a `now`. Two entries make
    a single change read as two, which is the same defect as one dispute
    recorded twice."""
    ledger, _ = _corrected(_two_issues())
    ledger = recomputed(ledger, "meeting-timeline", "2026-09-03", at=AT)
    revisions = ledger.revisions_of("meeting-timeline")
    assert len(revisions) == 1
    assert (revisions[0].was, revisions[0].now) == ("2026-09-02", "2026-09-03")
    assert ledger.node("meeting-timeline").currency is Currency.CURRENT


# ============ unknown dependency information certifies nothing ==============

def test_a_node_that_records_no_inputs_is_never_current():
    """DEFECT SHAPE S1 AIMED AT THE MECHANISM THAT EXISTS TO CATCH IT. Nothing
    touched it because nobody recorded what could touch it, and reading that
    as 'unaffected' is an absence read as a clean result."""
    node = Node(name="orphan", value="something", rests_on=())
    assert node.currency is Currency.NOT_ESTABLISHED
    assert "nothing records what this rests on" in node.stale_because


def test_a_node_declaring_an_unknown_dependency_is_never_current():
    node = Node(name="partly-known", value="x",
                rests_on=(Rest(InputKind.FACT, "f1"),
                          Rest(InputKind.UNKNOWN, "undeclared")))
    assert node.currency is Currency.NOT_ESTABLISHED


def test_not_established_is_refused_by_the_same_gate_as_stale():
    ledger = record(Ledger(), Node(name="orphan", value="x", rests_on=()))
    allowed, why = presentable(ledger, "orphan")
    assert allowed is False
    assert "not_established" in why or "nothing records" in why


def test_a_conclusion_with_no_dependency_record_at_all_is_refused():
    """The direction this module must fail in. A name the ledger has never
    heard of has no established currency, and answering 'fine' for it would
    make the control silent for exactly the conclusions nobody recorded."""
    allowed, why = presentable(Ledger(), "never-recorded")
    assert allowed is False
    assert "no dependency record" in why


def test_the_three_states_declare_their_escape():
    assert Currency.not_established() is Currency.NOT_ESTABLISHED
    assert InputKind.not_established() is InputKind.UNKNOWN
    assert Currency.CURRENT.usable is True
    for other in (Currency.STALE, Currency.REWORKING, Currency.NOT_ESTABLISHED):
        assert other.usable is False


# ============================ bounded rework ================================

def test_a_stale_node_is_offered_for_rework_and_a_current_one_is_not():
    ledger, _ = _corrected(_two_issues())
    offered = {n.name for n in due(ledger)}
    assert offered == {"meeting-timeline", "filing-deadline"}


def test_a_claimed_node_is_not_offered_again():
    """Two runners must not both take one node, and the state lives on the
    node rather than in a runner's memory so a restart cannot lose it."""
    ledger, _ = _corrected(_two_issues())
    ledger = claim(ledger, "meeting-timeline")
    assert ledger.node("meeting-timeline").currency is Currency.REWORKING
    assert "meeting-timeline" not in {n.name for n in due(ledger)}


def test_a_node_being_reworked_is_still_not_current():
    """The window between 'we noticed' and 'we finished' is exactly where
    stale advice gets served."""
    ledger, _ = _corrected(_two_issues())
    ledger = claim(ledger, "meeting-timeline")
    assert presentable(ledger, "meeting-timeline")[0] is False


def test_rework_stops_at_the_bound_and_leaves_the_node_stale():
    """A QUEUE THAT GIVES UP AND MARKS THE NODE CURRENT IS WORSE THAN NO
    QUEUE: it converts a known-stale conclusion into a certified one at the
    moment nobody is watching."""
    ledger, _ = _corrected(_two_issues())
    for _ in range(REWORK_LIMIT):
        ledger = claim(ledger, "meeting-timeline")
        ledger = rework_failed(ledger, "meeting-timeline",
                               "the chronology read did not run")
    node = ledger.node("meeting-timeline")
    assert node.currency is Currency.STALE
    assert node.rework_exhausted is True
    assert node.rework_attempts == REWORK_LIMIT
    assert "stopped at the bound" in node.stale_because
    assert "meeting-timeline" not in {n.name for n in due(ledger)}
    assert presentable(ledger, "meeting-timeline")[0] is False


def test_a_new_correction_re_opens_an_exhausted_node():
    """A node that exhausted its rework against yesterday's correction has not
    exhausted it against today's."""
    ledger, _ = _corrected(_two_issues())
    for _ in range(REWORK_LIMIT):
        ledger = claim(ledger, "meeting-timeline")
        ledger = rework_failed(ledger, "meeting-timeline", "unavailable")
    ledger, _ = observe(ledger, InputKind.FACT, "source-date",
                        digest_of("Meeting: 04 September 2026"),
                        reason="corrected again")
    ledger, _ = invalidate(ledger, (Rest(InputKind.FACT, "source-date", 3),),
                           reason="corrected again", at=AT)
    assert ledger.node("meeting-timeline").rework_exhausted is False
    assert "meeting-timeline" in {n.name for n in due(ledger)}


# =========================== enforcement ====================================

def test_release_is_blocked_by_one_stale_conclusion():
    """A read may show a stale value LABELLED stale — hiding it would tell the
    advocate there was never a conclusion. A release ASSERTS the file is
    current, and one stale node makes that assertion false."""
    ledger = _two_issues()
    assert released(ledger)[0] is True

    ledger, _ = _corrected(ledger)
    ok, blocking = released(ledger)
    assert ok is False
    assert any("filing deadline" in line for line in blocking)


def test_withheld_names_every_reason_and_is_empty_on_a_clean_file():
    ledger = _two_issues()
    names = ("meeting-timeline", "party-role", "filing-deadline")
    assert withheld(ledger, names) == ()

    ledger, _ = _corrected(ledger)
    reasons = withheld(ledger, names)
    assert len(reasons) == 2
    assert not any("party role" in r for r in reasons)


def test_the_report_is_one_line_when_nothing_is_stale():
    """§5.4's bound, one level down. A currency section printed every turn
    trains the advocate to skip it."""
    lines = report(_two_issues())
    assert len(lines) == 1
    assert "current" in lines[0]


def test_the_report_names_what_is_stale_and_why():
    ledger, _ = _corrected(_two_issues())
    lines = report(ledger)
    assert any("the meeting timeline" in line for line in lines)
    assert any("adv-1" in line for line in lines)


# ============================ restart =======================================

def test_staleness_survives_a_restart():
    """EVAL-010 restarts between the correction and the read for exactly this
    reason: a currency that lives in a process is one a restart silently
    converts to `current`."""
    ledger, _ = _corrected(_two_issues())
    restored = Ledger.from_stored(ledger.as_dict())

    assert restored.node("meeting-timeline").currency is Currency.STALE
    assert restored.node("filing-deadline").currency is Currency.STALE
    assert restored.node("party-role").currency is Currency.CURRENT
    assert restored.source_versions("meeting-timeline") == (1, 2)
    assert restored.revisions_of("meeting-timeline")[0].was == "2026-09-02"
    assert released(restored)[0] is False


def test_an_unreadable_ledger_withholds_rather_than_certifies():
    """Empty is the safe direction HERE and it is worth saying why, because
    elsewhere an empty result read as success is the defect: an unrecorded
    node is refused by `presentable`, so losing the ledger withholds
    conclusions rather than certifying them."""
    for junk in (None, "", [], {"nodes": "not a list"}):
        restored = Ledger.from_stored(junk)
        assert presentable(restored, "meeting-timeline")[0] is False


def test_an_unreadable_edge_kind_becomes_unknown_rather_than_disappearing():
    """Dropping the edge would make the node look like it rested on less than
    it did, and a smaller dependency set is a node that stays current through
    a change that reached it."""
    stored = _two_issues().as_dict()
    stored["nodes"][0]["rests_on"][0]["kind"] = "a-kind-from-the-future"
    restored = Ledger.from_stored(stored)
    node = restored.node("meeting-timeline")
    assert any(r.kind is InputKind.UNKNOWN for r in node.rests_on)
    assert presentable(restored, "meeting-timeline")[0] is False


# ================ the one bridge to the cascade snapshot ====================

def test_a_ledger_node_is_built_from_the_cascade_row_the_turn_already_made():
    """ONE STATEMENT IN THE PRODUCT of what a derived value rests on. A second
    place naming the same facts is CLAUDE.md section 4's defect at the centre
    of an invalidation mechanism — the two would drift, and the one that
    drifts smaller stops reaching a conclusion a change touched."""
    row = cascade.Derived(name="limitation on thr_1", value="2027-06-12",
                          shown="the limitation on 'the possession claim'",
                          from_facts=("fact_a", "fact_b"))
    node = from_derived(row, premises=("premise:article",),
                        authorities=("src-v1",), at=AT)

    assert node.name == row.name
    assert node.shown == row.shown
    assert {(r.kind, r.id) for r in node.rests_on} == {
        (InputKind.FACT, "fact_a"), (InputKind.FACT, "fact_b"),
        (InputKind.PREMISE, "premise:article"),
        (InputKind.AUTHORITY, "src-v1")}
    assert node.currency is Currency.CURRENT


def test_a_declared_unknown_input_makes_the_derived_node_uncertifiable():
    """The honest declaration is permitted; the SILENT version is what is
    refused — a computation with unrecorded inputs looking exactly like one
    with none."""
    row = cascade.Derived(name="theory", value="x", from_facts=("fact_a",))
    node = from_derived(row, unknown=True, at=AT)
    assert node.currency is Currency.NOT_ESTABLISHED


# ==================== EVAL-010's planted negative ===========================

def test_a_value_from_a_superseded_source_version_cannot_be_served_as_current():
    """EVAL-010's planted negative, in terms.

        MUTATION: serve `meeting-timeline`, derived from source version 1, as
                  current after version 2 has been accepted.
        EXPECTED REFUSAL: `source_version_stale`.

    The refusal must NAME the stale source version. A bare 'no' leaves the
    advocate unable to tell a withheld conclusion from one that was never
    computed, which is the distinction this whole module is built on.
    """
    ledger, _ = _corrected(_two_issues())

    allowed, why = presentable(ledger, "meeting-timeline")
    assert allowed is False, (
        "a conclusion computed from source version 1 was served as current "
        "after version 2 was accepted")
    # SAID IN WORDS, not by the input's key -- `why` is what the cover shows.
    assert "the case-file entry it rests on" in why
    assert "source-date" not in why
    assert "version 2" in why

    # AND THE STALE VALUE IS STILL ON THE FILE, labelled. Hiding it would tell
    # the advocate there had never been a timeline.
    assert ledger.node("meeting-timeline").value == "2026-09-02"
    assert ledger.node("meeting-timeline").as_dict()["usable"] is False
