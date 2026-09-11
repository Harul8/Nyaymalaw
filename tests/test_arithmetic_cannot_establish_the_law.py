"""THE LAW A COMPUTATION RESTS ON, ESTABLISHED BEFORE IT RUNS. BK-65-AC2. P22.

CLAUDE.md records the previous build's death in one sentence: twelve
mechanically-checked properties all passed on a transcript where the product
analysed a **twelve-year limitation on a trespass a day old**. The subtraction
was right. Every guard was green. The Article was wrong, and nothing was
looking at that, because nothing treated *which law governs* as a thing that
could be wrong.

`compute()` already refuses to invent a period — `Period` verifies itself
against the retrieved span, so no fabricated number reaches the arithmetic.
What it cannot refuse is a period that is real, correctly read, correctly
applied, and belongs to a different Article than the one this matter is under.

THE CRITERION'S MUTATION: *keep the arithmetic correct while substituting an
unsupported accrual rule or jurisdictional premise.* Expected failure: the
legal-premise check fails and the dependent conclusion cannot retain its prior
approval. Both halves are asserted — the block, and the invalidation of a
result already given.

This is `TRACE-D2`, which the scoped build gate has carried as a declared
failure since it was written.
"""
from __future__ import annotations

import pytest

from nm.core.premise import (
    REQUIRED,
    SUFFICIENT,
    Basis,
    Kind,
    Premise,
    Premises,
    assess,
    blocks,
    invalidated,
)
from nm.domain.traceability import refuses

pytestmark = pytest.mark.class_a


def _premises(**overrides) -> Premises:
    base = {
        Kind.APPLICABLE_LAW: Premise(
            Kind.APPLICABLE_LAW, "Limitation Act 1963, Article 65",
            Basis.ATTRIBUTED, source="the_limitation_act_1963#art65"),
        Kind.ACCRUAL_RULE: Premise(
            Kind.ACCRUAL_RULE, "when the possession becomes adverse",
            Basis.ATTRIBUTED, source="the_limitation_act_1963#art65"),
        Kind.JURISDICTION: Premise(
            Kind.JURISDICTION, "Telangana", Basis.STATED,
            source="the advocate stated the forum"),
    }
    base.update(overrides)
    return Premises(tuple(base.values()))


# ============================ the negative control ==========================

def test_a_fully_established_position_lets_the_arithmetic_run():
    """Without this, a check that blocked everything satisfies the file and
    the product computes nothing at all."""
    assert assess(_premises()) == []
    assert not blocks(_premises())


# ========================= the criterion's mutation =========================

@refuses("D2", 4)
@pytest.mark.parametrize("kind", list(Kind))
def test_an_inferred_premise_blocks_however_correct_the_arithmetic_is(kind):
    """*Substitute an unsupported accrual rule or jurisdictional premise.*

    Parametrised over all three because the criterion names applicable law,
    accrual AND jurisdiction, and a check that caught two of them would be the
    twelve-year-limitation defect with one fewer route in.
    """
    guessed = _premises(**{kind: Premise(
        kind, "something the product worked out", Basis.INFERRED,
        inferred_from="the word possession",
        alternatives=("Specific Relief Act s.6",))})
    found = assess(guessed)
    assert blocks(guessed), kind
    assert any("was not established" in p for p in found), found
    assert any("possession" in p for p in found), (
        "the note does not say what it inferred from, so the advocate cannot "
        "correct it in four words")
    assert any("Specific Relief Act s.6" in p for p in found), (
        "what else matched is not reported, which is CLAUDE.md §5's whole point")


@refuses("D2", 4)
def test_a_result_loses_its_approval_when_a_premise_moves():
    """The second half: *the dependent conclusion cannot retain its prior
    approval.* A stored answer is told the ground under it moved."""
    before = _premises()
    stamped = before.digest()
    assert invalidated(stamped, before) is None

    after = _premises(**{Kind.APPLICABLE_LAW: Premise(
        Kind.APPLICABLE_LAW, "Limitation Act 1963, Article 113",
        Basis.ATTRIBUTED, source="the_limitation_act_1963#art113")})
    said = invalidated(stamped, after)
    assert said and "no longer carries its earlier approval" in said


def test_an_invalidated_result_that_cannot_be_recomputed_says_so():
    """The more comfortable sentence is the wrong one. *Being recalculated*
    where the truth is *the law this rested on is now unestablished* tells the
    advocate to wait for a number that is not coming."""
    stamped = _premises().digest()
    unestablished = _premises(**{Kind.ACCRUAL_RULE: Premise(
        Kind.ACCRUAL_RULE, "unknown", Basis.UNESTABLISHED)})
    said = invalidated(stamped, unestablished)
    assert said and "cannot be recomputed until it is" in said
    assert "recalculat" not in said


# ====================== what each premise is for ============================

def test_the_three_premises_fail_differently_and_are_corrected_by_different_people():
    """A single `basis: str` collapses all three, and the advocate correcting
    it cannot say which of the three they are correcting."""
    said = {}
    for kind in Kind:
        found = assess(_premises(**{kind: Premise(kind, "x", Basis.UNESTABLISHED)}))
        assert len(found) == 1, (kind, found)
        said[kind] = found[0]
    assert len(set(said.values())) == 3, f"two premises read alike: {said}"
    assert "which provision governs" in said[Kind.APPLICABLE_LAW]
    assert "what starts the limitation period" in said[Kind.ACCRUAL_RULE]
    assert "which forum's law applies" in said[Kind.JURISDICTION]


@pytest.mark.parametrize("kind", list(Kind))
def test_a_missing_premise_is_not_a_satisfied_one(kind):
    """§9. An absent premise must not read as an established one, which is the
    single most repeated defect in this codebase."""
    kept = tuple(p for p in _premises().items if p.kind is not kind)
    found = assess(Premises(kept))
    assert any("has not been established at all" in p for p in found), found


def test_an_attributed_premise_with_no_source_is_an_assertion():
    """A source nobody can open is a citation-shaped decoration."""
    found = assess(_premises(**{Kind.APPLICABLE_LAW: Premise(
        Kind.APPLICABLE_LAW, "Article 65", Basis.ATTRIBUTED, source="")}))
    assert any("names none" in p for p in found), found


def test_the_advocate_is_never_second_guessed():
    """`STATED` is the strongest basis this product has. A check that demanded
    a source for what the advocate told it would be asking them to cite
    themselves."""
    stated = _premises(**{k: Premise(k, "as instructed", Basis.STATED)
                          for k in Kind})
    assert assess(stated) == []


# ========================= the shape of the control =========================

def test_only_stated_and_attributed_may_run_a_computation():
    """The omission is the control. An inferred premise is a question, and a
    number on the screen is acted on whatever the note beside it says."""
    assert set(SUFFICIENT) == {Basis.STATED, Basis.ATTRIBUTED}
    assert Basis.INFERRED not in SUFFICIENT
    assert Basis.UNESTABLISHED not in SUFFICIENT


def test_all_three_premises_are_required_and_none_is_assumed():
    """A computation needing only two would be one where the third was
    assumed, and jurisdiction is the one that is silent when it is wrong."""
    assert set(REQUIRED) == set(Kind)


def test_the_digest_moves_on_a_changed_premise_and_not_on_reordering():
    """The identity must be about the position, not about the order somebody
    happened to build the tuple in."""
    forward = _premises()
    backward = Premises(tuple(reversed(forward.items)))
    assert forward.digest() == backward.digest()

    moved = _premises(**{Kind.JURISDICTION: Premise(
        Kind.JURISDICTION, "Kerala", Basis.STATED, source="stated")})
    assert moved.digest() != forward.digest()

    rebased = _premises(**{Kind.JURISDICTION: Premise(
        Kind.JURISDICTION, "Telangana", Basis.INFERRED,
        inferred_from="the address on the sale deed")})
    assert rebased.digest() != forward.digest(), (
        "the same statement on a weaker basis is a different legal position "
        "and must not share an identity with the established one")
