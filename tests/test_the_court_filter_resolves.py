"""BK-38 — a court filter that resolves, and a zero that says what ran.

WHAT WAS MEASURED, 8 September 2026
-------------------------------------
The filter was `lower(court) = lower(?)`. The authority index holds exactly
two court values --

    SELECT court, COUNT(*) FROM paras GROUP BY court
    Supreme Court of India          395,734
    High Court of Andhra Pradesh     55,814

-- so an advocate typing `Supreme Court` got ZERO from a corpus holding nearly
four hundred thousand Supreme Court paragraphs.

A ZERO FROM AN EXACT-MATCH FILTER READS AS AN EMPTY CORPUS, and this
repository has recorded that trap three times already against the legal
corpus (B-163: *a zero result must name the index it came from*). Here it was
worse than a wrong index: the right index, the right query, and a filter that
silently matched nothing.

WHY THIS IS NOT FUZZY MATCHING
--------------------------------
CLAUDE.md §5 is that fuzzy may RANK, never IDENTIFY -- and a court filter
identifies. The resolution goes through `normalise_court`, which maps free
text onto a CLOSED vocabulary of courts and returns UNKNOWN rather than
guessing, and then through `STORED_AS`, which is a two-entry table measured
off the index itself. Nothing is scored and nothing is nearest-matched.

AND ONE ALIAS IS A LEGAL DECISION, NOT A CONVENIENCE
------------------------------------------------------
`Telangana High Court` resolves to `High Court of Andhra Pradesh`, because
Andhra Pradesh High Court judgements ARE Telangana judgements and every one
of them binds -- the standing decision in `docs/BASELINE.md` §1.1. RG-01
already cost this product a blocked release by counting a court LABEL instead
of the binding relationship.
"""
from __future__ import annotations

import pytest
from nm.knowledge.jurisdiction import STORED_AS, Court, stored_court

pytestmark = pytest.mark.class_a


# ============================================================ it resolves ====

@pytest.mark.parametrize("typed,expected", [
    ("Supreme Court", "Supreme Court of India"),
    ("supreme court of india", "Supreme Court of India"),
    ("SUPREME COURT OF INDIA", "Supreme Court of India"),
    ("Andhra Pradesh High Court", "High Court of Andhra Pradesh"),
    ("Telangana High Court", "High Court of Andhra Pradesh"),
    ("High Court of Andhra Pradesh", "High Court of Andhra Pradesh"),
])
def test_common_spellings_reach_the_same_stored_value(typed, expected):
    """THE DEFECT, AS A RULE. `Supreme Court` returned zero from 395,734."""
    value, said = stored_court(typed)
    assert value == expected, f"{typed!r} resolved to {value!r}"
    assert expected in said, f"the disclosure does not name what ran: {said!r}"


def test_telangana_reaches_the_andhra_pradesh_bench():
    """THE ONE ALIAS THAT IS A LEGAL DECISION, kept as its own test so it
    cannot be deleted as a duplicate of the parametrised row above."""
    value, _ = stored_court("Telangana")
    assert value == "High Court of Andhra Pradesh", (
        "Telangana resolves to nothing, so an advocate in Telangana asking "
        "for their own High Court is told the corpus holds none of it -- "
        "while 4,280 binding judgements sit in the index")


# ================================================== and it refuses to guess ==

def test_a_court_this_index_does_not_hold_returns_nothing_and_says_so():
    """A ZERO THAT NAMES ITS FILTER. `Bombay High Court` is a real court and
    this index holds none of it, which is a different fact from the query
    matching nothing -- and the advocate can only tell them apart if the
    answer says which."""
    value, said = stored_court("Bombay High Court")
    assert value == "", f"a court the index does not hold resolved to {value!r}"
    assert "holds nothing for" in said or "matches no court" in said, said
    # AND IT NAMES WHAT IS HELD, so the advocate knows what to ask for.
    assert "Supreme Court of India" in said
    assert "High Court of Andhra Pradesh" in said


def test_an_unrecognised_string_is_not_coerced_to_the_commonest_court():
    """The safe direction. A mis-attributed authority is worse than an
    unattributed one, which is `normalise_court`'s own recorded rule."""
    value, said = stored_court("Court of Chancery")
    assert value == "", f"an unrecognised court resolved to {value!r}"
    assert "Supreme Court of India" not in said.split("It holds")[0]


def test_no_filter_is_distinguishable_from_a_filter_that_matched_nothing():
    """THREE STATES. `None` means the advocate asked for no court; `""` means
    they asked for one this index cannot answer. Collapsing them would let a
    filtered search report itself as unfiltered."""
    assert stored_court(None)[0] is None
    assert stored_court("")[0] is None
    assert stored_court("   ")[0] is None
    assert stored_court("Bombay High Court")[0] == ""


# ======================================================== positive controls ==

def test_the_stored_values_are_the_ones_the_index_holds():
    """A CONTROL ON THE TABLE ITSELF.

    `STORED_AS` is a measurement -- `SELECT court, COUNT(*) FROM paras GROUP
    BY court` on 8 September 2026 -- and a measurement written into code
    stops being one. This is what fails if somebody edits the spelling: two
    values, and the exact strings the index uses.
    """
    assert set(STORED_AS.values()) == {
        "Supreme Court of India", "High Court of Andhra Pradesh"}
    assert STORED_AS[Court.SUPREME_COURT] == "Supreme Court of India"
    # BOTH AP AND TELANGANA POINT AT THE SAME BENCH. If they ever diverge,
    # a Telangana search silently stops covering the judgements that bind it.
    assert STORED_AS[Court.HC_TELANGANA] == STORED_AS[Court.HC_ANDHRA_PRADESH]


def test_the_resolver_can_tell_a_hit_from_a_miss():
    """A CONTROL ON THE RESOLVER. One that returned `""` for everything would
    pass every refusal test above and break every search."""
    assert stored_court("Supreme Court")[0]
    assert not stored_court("Bombay High Court")[0]
