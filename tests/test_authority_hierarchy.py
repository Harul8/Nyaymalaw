"""The hierarchy rule: SC over HC, and a larger bench over a smaller one.

WHY THIS EXISTS, AND WHY IT NEARLY DIDN'T
------------------------------------------
This rule was declined once, on the ground that bench composition was recorded
for 7.5% of judgments and the rule would answer "cannot tell" for 92.5% of
them. That measurement came from `vector_store/`, the DERIVED layer, which
dropped the field. The source files carry `Bench:` on **90.2%**.

So the recommendation was wrong, and it was wrong because a claim about the
corpus was measured against an artefact of one extraction. Check `raw-1` exists
to stop that recurring; this file exists because the rule it blocked is real.

The pure tests run everywhere. The corpus-backed ones are class C and skip
cleanly when the index has not been built.
"""
from __future__ import annotations

import pytest

from nm.domain.traceability import refuses
from nm.knowledge.identity import (
    CaseIdentity,
    IdentityIndex,
    Precedence,
    Tier,
    supersedes,
)

pytestmark = pytest.mark.class_a


def case(court: str, bench: int | None = None, year: int = 2000,
         cid: str = "c") -> CaseIdentity:
    return CaseIdentity(case_id=cid, court=court, year=year, bench_size=bench)


# ==================================================== the tier rule ========

def test_the_supreme_court_is_senior_to_every_high_court():
    """Article 141. It does not depend on bench strength, and a Constitution
    Bench of a High Court does not out-rank a single judge of the Supreme
    Court."""
    sc = case("Supreme Court of India", bench=1)
    hc = case("High Court of Andhra Pradesh", bench=5)
    verdict, why = supersedes(sc, hc)
    assert verdict is Precedence.LEFT
    assert "senior" in why

    # And the same answer whichever way round it is asked.
    assert supersedes(hc, sc)[0] is Precedence.RIGHT


def test_the_predecessor_high_court_ranks_as_our_own():
    """The Andhra Pradesh High Court is the predecessor of the Telangana High
    Court for this territory, so it sits at the same tier — which is the whole
    basis of the `bind-1` decision."""
    assert case("High Court of Andhra Pradesh").tier is Tier.HC_OWN
    assert case("High Court of Telangana").tier is Tier.HC_OWN
    assert case("High Court of Kerala").tier is Tier.HC_OTHER


def test_an_unknown_court_never_out_ranks_a_known_one():
    """`UNKNOWN` is 0, not a middle value. An unrecognised court must not win a
    comparison by accident, and it must not quietly lose one either."""
    # NOT "Some Tribunal" — that IS recognised, as subordinate, and the
    # Supreme Court correctly beats it. The first version of this test used it
    # and failed; the premise was wrong, not the rule.
    verdict, why = supersedes(case("Bureau of Zonal Adjudication"),
                              case("Supreme Court of India"))
    assert verdict is Precedence.NOT_COMPARABLE
    assert "not assumed" in why


# =================================================== the bench rule ========

def test_a_larger_bench_supersedes_a_smaller_one_in_the_same_court():
    """THE RULE, as stated. A Constitution Bench governs over a Division Bench
    of the same court."""
    verdict, why = supersedes(
        case("Supreme Court of India", bench=5),
        case("Supreme Court of India", bench=2))
    assert verdict is Precedence.LEFT
    assert "Constitution Bench (5)" in why
    assert "Division Bench (2)" in why


@refuses("P2", 1)
def test_co_ordinate_benches_do_not_supersede_each_other():
    """THE COUNTEREXAMPLE. Two benches of equal strength that disagree is a
    real situation with a real answer — the point goes to a larger bench — and
    it is NOT a ranking problem. Picking a winner here would tell an advocate
    the law is settled when it is precisely what is unsettled.
    """
    verdict, why = supersedes(
        case("Supreme Court of India", bench=3, year=2010),
        case("Supreme Court of India", bench=3, year=1998))
    assert verdict is Precedence.NOT_COMPARABLE
    assert "co-ordinate" in why
    assert "larger bench" in why


def test_an_unrecorded_bench_blocks_the_comparison_rather_than_defaulting():
    """Bench is recorded for 90.2% of judgments, not all. The other 9.8% return
    `NOT_COMPARABLE` — never "assume two", which would silently demote every
    Constitution Bench whose header failed to parse."""
    verdict, why = supersedes(
        case("Supreme Court of India", bench=None),
        case("Supreme Court of India", bench=5))
    assert verdict is Precedence.NOT_COMPARABLE
    assert "not recorded" in why


def test_bench_strength_is_described_in_the_advocates_vocabulary():
    assert case("x", bench=1).describe() == "single judge"
    assert case("x", bench=2).describe() == "Division Bench (2)"
    assert case("x", bench=3).describe() == "3-judge bench"
    assert case("x", bench=5).describe() == "Constitution Bench (5)"
    assert case("x", bench=9).describe() == "Constitution Bench (9)"
    assert case("x", bench=None).describe() == "bench not recorded"


def test_an_absent_index_answers_not_known_rather_than_defaulting():
    """An unbuilt index must never be able to clear an authority."""
    ix = IdentityIndex("nowhere/identity.db")
    assert not ix.available
    assert ix.case("anything") is None
    assert not ix.addressable("anything")
    t = ix.treatment("anything")
    assert t.state.value == "not_checked"
    assert "not built" in t.scope
