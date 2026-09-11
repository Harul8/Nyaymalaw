"""A SOURCE MAY BE RELIED ON ONLY WHEN THE RECORD CLAIMS ENOUGH. BK-84-AC1.

The corpus holds a draft and an enacted Act in the same shape, an Act as it
stood in 2019 and as amended in 2023 in the same shape, and a High Court
judgement that binds Telangana beside one that does not. Every one of them
retrieves successfully.

THE CRITERION'S MUTATION IS FOUR SUBSTITUTIONS: *a draft, a stale provision, an
unreadable source or a wrong High Court as verified controlling law*, and the
expected failure is that use is withheld **with the precise unresolved basis**.
A single "cannot verify" tells the advocate nothing they can act on; the four
causes have four different remedies.

WHAT THIS DOES NOT DO, stated so it is not assumed. It decides whether the
RECORD is checkable, not whether the LAW is good. BK-84-AC1 also requires
`counsel_review`, and no code in this repository can supply the authority that
evidence level demands — under BK-80-AC1 a counsel review must carry a stated
and evidenced qualification, which is a person's, not a program's.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.knowledge.provenance import (
    SUPPORTED_JURISDICTIONS,
    SourceRecord,
    Standing,
    Treatment,
    reliable,
    unresolved,
)

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 11)


def _record(**overrides) -> SourceRecord:
    base = {
        "source_id": "raw_data/acts/specific_relief_1963.txt",
        "canonical_id": "UNION OF INDIA_1963_1_THE SPECIFIC RELIEF ACT, 1963",
        "title": "The Specific Relief Act, 1963",
        "jurisdiction": "union_of_india",
        "language": "en",
        "standing": Standing.ENACTED,
        "treatment": Treatment.UNTREATED,
        "digest": "a" * 64,
        "effective_from": date(1964, 3, 1),
        "observed_at": date(2026, 8, 29),
        "supported": ("union_of_india", "telangana"),
    }
    base.update(overrides)
    return SourceRecord(**base)


# ============================ the negative control ==========================

def test_a_complete_record_is_reliable():
    """Without this, a checker that withheld everything satisfies the whole
    file and the product answers nothing."""
    assert unresolved(_record(), as_of=TODAY, binding_on="telangana") == []
    assert reliable(_record(), as_of=TODAY)


# ======================= the criterion's four mutations =====================

def test_a_draft_is_not_enacted_law():
    found = unresolved(_record(standing=Standing.DRAFT), as_of=TODAY)
    assert any("DRAFT" in p for p in found), found


@pytest.mark.parametrize("mutation,expected", [
    ({"effective_from": None}, "date this took effect is not recorded"),
    ({"effective_from": date(2027, 1, 1)}, "after 2026-09-11"),
    ({"observed_at": None}, "read from its source is not recorded"),
    ({"standing": Standing.REPEALED}, "repealed"),
    ({"standing": Standing.AMENDED, "amended_by": ()}, "names no amending"),
])
def test_a_stale_provision_is_withheld_with_its_reason(mutation, expected):
    found = unresolved(_record(**mutation), as_of=TODAY)
    assert any(expected in p for p in found), (mutation, found)


@pytest.mark.parametrize("field", ["source_id", "canonical_id", "title",
                                   "jurisdiction", "language", "digest"])
@pytest.mark.parametrize("value", ["", "   "])
def test_an_unidentifiable_source_cannot_be_constructed_at_all(field, value):
    """*An unreadable source as verified controlling law.*

    REFUSED AT THE TYPE, not reported by `unresolved`. The first version built
    the record and asked whether reliance was refused -- and once
    `@refuses_blank_text` was added the constructor raised first, so the
    assertion was about a branch nothing could reach. Making it impossible to
    hold an unidentifiable record beats reporting one afterwards, and a
    whitespace value is the half that `if not x` misses.
    """
    with pytest.raises(ValueError) as refused:
        _record(**{field: value})
    assert field in str(refused.value)


def test_a_wrong_high_court_is_refused_by_relationship_and_not_by_label():
    """*A wrong High Court as verified controlling law.*

    B-044 is why this is asked as a relationship: RG-01 counted a court LABEL
    no record carries, got zero, and told the advocate no High Court output was
    held for this jurisdiction while 4,280 binding judgements sat on disk.
    """
    outside = unresolved(_record(jurisdiction="kerala"), as_of=TODAY)
    assert any("kerala" in p and "outside the declared coverage" in p
               for p in outside), outside

    # And the other direction: held, but not declared to bind this forum.
    narrow = unresolved(_record(supported=("union_of_india",)),
                        as_of=TODAY, binding_on="telangana")
    assert any("not declared to support" in p for p in narrow), narrow


# ===================== undeclared is never universal ========================

def test_an_undeclared_coverage_is_not_a_universal_one():
    """P19's second expectation: *India-only operations never imply all-India
    verified coverage.* An empty `supported` is an unanswered question."""
    found = unresolved(_record(supported=()), as_of=TODAY, binding_on="telangana")
    assert any("declares no supported coverage" in p for p in found), found


def test_an_undetermined_standing_is_not_an_enacted_one():
    """§9. The default is not `enacted`; it is nobody having looked."""
    found = unresolved(_record(standing=Standing.UNDETERMINED), as_of=TODAY)
    assert any("nobody has established" in p for p in found), found


def test_unchecked_treatment_is_reported_rather_than_assumed_clean():
    found = unresolved(_record(treatment=Treatment.UNDETERMINED), as_of=TODAY)
    assert any("no later treatment" in p for p in found), found
    overruled = unresolved(_record(treatment=Treatment.OVERRULED), as_of=TODAY)
    assert any("overruled" in p for p in overruled), overruled


# ========================= the reasons are precise ==========================

def test_each_cause_reports_its_own_remedy_and_not_one_summary():
    """Four substitutions, four distinct sentences. The expected failure is
    that use is withheld with the PRECISE basis."""
    causes = {
        "draft": _record(standing=Standing.DRAFT),
        "stale": _record(effective_from=None),
        "unchecked treatment": _record(treatment=Treatment.UNDETERMINED),
        "wrong forum": _record(jurisdiction="kerala"),
    }
    said = {}
    for name, record in causes.items():
        found = unresolved(record, as_of=TODAY)
        assert found, name
        said[name] = found[0]
    assert len(set(said.values())) == len(said), (
        f"two causes report the same sentence: {said}")


def test_the_declared_coverage_is_this_products_actual_scope():
    """Telangana and the Union of India, which `docs/BASELINE.md` records as a
    standing product decision -- not a value invented here."""
    assert set(SUPPORTED_JURISDICTIONS) == {"telangana", "union_of_india"}


def test_reliance_is_all_or_nothing():
    """There is no partial reliance: an advocate either may cite this or may
    not, and a half-reliable authority is one somebody cites anyway."""
    assert reliable(_record(), as_of=TODAY)
    assert not reliable(_record(standing=Standing.DRAFT), as_of=TODAY)
