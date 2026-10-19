"""ADVICE AT THE MATURITY IT HAS. BK-50-AC1, BK-96-AC2, BK-96-AC3. P26.

WHAT THIS DEFENDS
-------------------
`Recommendation` was carried in `test_reached_from_production.UNTYPED` for as
long as this product has existed:

    E2. BUILT AS A STRING. `turn._recommend` composes prose; the PRD declares
    a record. B-074 is what an untyped recommendation costs -- nothing could
    ask it what it was based on, so it contradicted the finding printed
    beneath it.

So the defect is not that the sentence was wrong. It is that the sentence was
the ONLY thing there: nothing could ask the recommendation what it rested on,
what would change it, or whether its date was attributed to anything. These
tests are about what the record must be able to answer.

THE FABRICATION THIS REFUSES IS THE SUBTLE ONE. A template with seven slots
invites seven plausible sentences, and a plausible owner beside a plausible
date reads exactly like a checked one. Every field this product cannot fill
stays EMPTY and is reported by `absent()` -- being told "no fallback was
established" is useful; being told an invented fallback is worse than silence.
"""
from __future__ import annotations


import pytest

from nm.advise.brief_contracts import ORDER, Section

pytestmark = pytest.mark.class_a


# ================================================== 1. maturity is derived ===


# ============================================ 2. the record and its absences ==


# ================================== 3. what may not reach the renderer =======


# ========================================== 4. BK-50-AC1: the answer shape ====

def test_the_answer_leads_with_the_position_and_not_with_background():
    """BK-50-AC1 and BK-96-AC3 meet here. The criterion is explicit that this
    is about *the applicable named sections and ordering promised by the advice
    contract, not an arbitrary minimum heading count* -- so it is asserted on
    `brief.ORDER`, which is the contract, rather than on how many headings
    happen to be rendered."""
    assert ORDER[0] is Section.POSITION, (
        f"the answer opens with {ORDER[0].value}; counsel opens an advice "
        f"looking for the position and the step")
    assert ORDER.index(Section.NEXT) < ORDER.index(Section.BECAUSE), (
        "the working is ordered above the step, so the reader reconstructs "
        "the recommendation instead of being told it")
    assert ORDER[-1] is Section.AUDIT


# ================================= 5. the served turn, BK-96-AC2 integration ==


