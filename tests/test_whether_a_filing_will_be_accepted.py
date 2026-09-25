"""LB-125. FORUM, VALUATION AND COURT FEE -- and why they ship as a named gap.

THE DEFECT THIS FILE IS ABOUT. `forum`, `valuation` and `court_fees` have been
declared thresholds since D1 and each answered BLOCKED on every turn with the
map's generic sentence, because nothing assessed them. An advocate reading
*not assessed on this thread* three times learned nothing, and could not tell
those rows apart from a threshold somebody had looked at.

WHAT IS AND IS NOT CLAIMED HERE. This slice does NOT compute a court fee. The
schedule that fixes it is not among the corpus's intended coverage, measured
against the manifest, and a fee computed from a schedule nobody versioned is
wrong in a way that reads exactly like right. So the row names the titles that
would have to be held, which is something an advocate can act on.

AND THE GAP IS MEASURED, NOT WRITTEN DOWN. These tests hold that in both
directions: with the instruments absent the answer names them, and with the
instruments present and versioned the SAME code answers differently, with
nothing edited. A claim about the corpus that nothing compares to the corpus is
B-141, and it went unnoticed for eight days the last time.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from nm.core import thresholds
from nm.core.turn import TurnInput
from nm.knowledge import filing_requirement as curated
from nm.ports.filing_requirement import Requirement, SourceState

from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a


# ============================================== the doubles for a manifest ==

@dataclass(frozen=True)
class _Entry:
    act_name: str


class _Manifest:
    """A manifest holding exactly the titles a test names.

    Not the real `Manifest`: its loader reads yaml off disk, and a double that
    answered through it would be testing yaml.
    """

    def __init__(self, *titles: str) -> None:
        self.entries = tuple(_Entry(t) for t in titles)


def _all_titles() -> tuple[str, ...]:
    return tuple({a.act_name
                  for group in curated.AUTHORITIES.values() for a in group})


# ======================================= the table, and what it may not do ==

def test_every_authority_says_where_it_came_from_and_what_it_answers():
    assert curated.AUTHORITIES, "the table is empty, so this checks nothing"
    for requirement, group in curated.AUTHORITIES.items():
        assert group, requirement
        for authority in group:
            assert authority.requirement is requirement
            assert authority.act_name.strip()
            assert authority.curated_from.strip()
            assert authority.what_it_would_answer.strip()


def test_every_requirement_is_a_declared_threshold():
    """THE ROW EXISTS TO ANSWER A THRESHOLD THAT WAS ALREADY DECLARED. A
    requirement with no threshold would compute something nothing shows."""
    for requirement in Requirement:
        assert thresholds.Threshold(requirement.value)


def test_an_act_is_matched_by_exact_title_and_never_by_overlap():
    """CLAUDE.md section 5, where it bites hardest. Measured there: `Indian`
    matched the Easements Act to the Evidence Act, and the shared year matched
    it to the Transfer of Property Act. A wrong Act here decides the fee.

    A manifest holding a title that merely SHARES WORDS must not satisfy the
    requirement.
    """
    near_misses = _Manifest("Court Fees Act, 1870",
                            "Telangana Civil Courts Act",
                            "Code of Civil Procedure, 1908")
    for requirement in Requirement:
        got = curated.readiness(requirement, near_misses)
        assert got.state is SourceState.NOT_INTENDED, (requirement, got.state)


# ================================================== the four states ========

def test_an_installation_that_cannot_ask_says_so_and_never_says_not_held():
    """THE THIRD STATE, AND IT IS THE ONE THAT KEEPS BEING COLLAPSED
    (CLAUDE.md section 9). An installation with no manifest has not learned
    that the schedule is missing -- it has learned nothing. `NOT_MEASURED` is
    not `NOT_INTENDED`, and the output has to say which."""
    for requirement in Requirement:
        got = curated.readiness(requirement, None)
        assert got.state is SourceState.NOT_MEASURED
        assert got.state is not SourceState.NOT_INTENDED
        assert not got.computable
        assert "not the same as knowing it cannot" in got.why


def test_the_gap_is_named_by_title_rather_than_merely_refused():
    """A REFUSAL AN ADVOCATE CANNOT ACT ON IS NOT AN ANSWER. The titles are
    what they hand to whoever maintains the corpus."""
    manifest = _Manifest("Code of Civil Procedure, 1908")
    fee = curated.readiness(Requirement.COURT_FEES, manifest)
    assert fee.state is SourceState.NOT_INTENDED
    assert fee.missing
    for title in fee.missing:
        assert title in fee.why


def test_a_requirement_read_from_two_instruments_is_unanswered_if_one_is_missing():
    """FORUM NEEDS BOTH: the Code fixes the order in which the question is
    asked, and state law fixes the pecuniary tier. Half-answered is not
    answered, and saying WHICH half is missing is the useful part."""
    manifest = _Manifest("Code of Civil Procedure, 1908")
    forum = curated.readiness(Requirement.FORUM, manifest)
    assert forum.state is SourceState.NOT_INTENDED
    assert forum.missing == ("Telangana Civil Courts Act, 1972",)
    assert "Code of Civil Procedure" not in " ".join(forum.missing)


def test_a_held_act_with_no_recorded_schedule_version_computes_nothing():
    """`HELD_UNVERSIONED` IS NOT A WEAKER `HELD`. A fee from a schedule whose
    version nobody recorded is wrong in a way that reads exactly like right --
    the amendment that moved it leaves no trace in the figure. This is defect
    shape S11's argument: the dense index was knowable as unusable only
    because it shipped an identity."""
    manifest = _Manifest(*_all_titles())
    for requirement in Requirement:
        got = curated.readiness(requirement, manifest)
        assert got.state is SourceState.HELD_UNVERSIONED, requirement
        assert not got.computable


def test_the_same_code_answers_differently_when_the_corpus_catches_up(monkeypatch):
    """THE MEASUREMENT IS MADE, NOT WRITTEN DOWN (B-141). If the answer were a
    sentence in the source, this test could not pass without an edit -- which
    is exactly what makes a documented gap a gap that outlives its cause."""
    manifest = _Manifest(*_all_titles())
    monkeypatch.setattr(curated, "SCHEDULE_VERSIONS",
                        {t: "as amended to 1 April 2026" for t in _all_titles()})
    for requirement in Requirement:
        got = curated.readiness(requirement, manifest)
        assert got.state is SourceState.HELD_AND_VERSIONED, requirement
        assert got.computable


def test_no_version_is_recorded_today_and_the_table_says_why():
    """THE MEASURED POSITION, held as a test so it cannot silently change. A
    version added without the instrument that fixed it would make a fee
    computable on nobody's authority."""
    assert curated.SCHEDULE_VERSIONS == {}


# ================================================= on the threshold map ====

def test_a_blocked_row_carries_the_measured_reason_not_the_maps_own():
    for requirement in Requirement:
        row = thresholds.from_filing_requirement(
            curated.readiness(requirement, _Manifest()))
        assert row.state is thresholds.ThresholdState.BLOCKED
        assert row.reason != thresholds.NOT_ASSESSED
        assert row.threshold.value == requirement.value


def test_not_applicable_is_never_reached_from_a_filing_requirement():
    """EVERY FILING HAS A FORUM, A VALUATION AND A FEE. The question is only
    whether this product can read them, so "does not arise" would be the
    silence D1 forbids wearing a finding's clothes."""
    for manifest in (None, _Manifest(), _Manifest(*_all_titles())):
        for requirement in Requirement:
            row = thresholds.from_filing_requirement(
                curated.readiness(requirement, manifest))
            assert row.state is not thresholds.ThresholdState.NOT_APPLICABLE


# ===================================================== on the served turn ==

BRIEF = ("We act for the plaintiff at Hyderabad. Goods were supplied against "
         "invoices on 14 March 2023 and were never paid for. We want to sue.")


def _said(out):
    return " ".join(e.text for e in out.answer.elements)


def test_the_advocate_is_told_which_instrument_is_missing(tmp_path):
    """A GUARD THAT IS RIGHT IN THE KNOWLEDGE PLANE AND NEVER REACHES THE
    ANSWER IS NOT A GUARD (CLAUDE.md section 8)."""
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF))
    said = _said(out)
    assert "Telangana Court Fees and Suits Valuation Act, 1956" in said, said[-1500:]
    assert "Telangana Civil Courts Act, 1972" in said


def test_no_fee_or_tier_figure_is_ever_served(tmp_path):
    """LB-125's NEVER. A figure would be an estimate from a schedule nobody
    holds, and an estimate is what this row exists to refuse."""
    import re

    engine, _ = build(tmp_path)
    said = _said(engine.run(TurnInput(advocate_id="adv_1", message=BRIEF)))
    for claimed in ("court fee payable", "the fee is", "fee of Rs",
                    "pecuniary tier is"):
        assert claimed not in said, claimed
    assert not re.search(r"(Rs\.?|₹)\s*[\d,]+", said), said[-800:]


def test_an_unwired_installation_keeps_the_maps_own_reason(tmp_path):
    """AN ABSENT PORT IS NOT A FINDING. With nothing wired the three rows read
    exactly as they did before this table existed -- an installation that
    cannot measure must not report a gap it has not measured."""
    engine, _ = build(tmp_path)
    engine._filing = None
    said = _said(engine.run(TurnInput(advocate_id="adv_1", message=BRIEF)))
    assert "Telangana Court Fees and Suits Valuation Act, 1956" not in said
    assert "Telangana Civil Courts Act, 1972" not in said
