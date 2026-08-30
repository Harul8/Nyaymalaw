"""One copy of "how an advocate writes a provision reference", and only one.

WHAT HAPPENED, AND WHY THE TEST IS SHAPED LIKE THIS
----------------------------------------------------
The grounding gate and the evidence adapter each had their own pattern for
reading a provision reference out of text. The gate's was hardened against a
false positive — `O.S. 442/2023` parsing as "section 442", because `O.S. 442`
contains `S. 442`. The adapter's was not, because nothing connected them.

One realistic brief then did this:

    "We act for the plaintiff in O.S. 442/2023 ... what is the step under
     section 6 of the Specific Relief Act?"

    -> retrieval looked up Specific Relief Act s.442
    -> found nothing, reported NOT_HELD
    -> the model answered about s.6
    -> the grounding gate correctly withheld the turn, because s.6 had never
       been retrieved

Two components each behaving correctly, one useless answer, and the defect
living in the gap between them. It was invisible to unit tests and obvious the
first time seven realistic turns ran end to end.

CLAUDE.md rule 4 is the fix, and it is why the last test here exists: the
question is not *where is the other copy* but **what makes a second copy
impossible**. A grep is a weak enforcement mechanism, and it is a great deal
stronger than a memo.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from nm.domain.citation import cases_named, provisions_cited, wanted_section
from nm.domain.traceability import refuses

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]


@refuses("H2", 0)
def test_a_case_number_is_not_a_section_number():
    """THE COUNTEREXAMPLE, in both directions.

    `O.S. 442/2023` is an Original Suit. Reading it as section 442 sends
    retrieval after a provision that does not exist and then reports the
    absence as a corpus gap.
    """
    brief = ("We act for the plaintiff in O.S. 442/2023 before the City Civil "
             "Court. What is the step under section 6 of the Specific Relief Act?")
    assert wanted_section(brief) == "6"
    assert provisions_cited(brief) == {"6"}

    for number in ("O.S. 442/2023", "R.S.A. 12 of 2019", "C.C. 77/2025",
                   "W.P. 8891/2024", "Crl.M.P. 1234/2021"):
        assert not provisions_cited(number), (
            f"{number} is a number of record, not a provision")


def test_ordinary_provision_references_still_match():
    """The other half of the flag-calibration rule. A gate that stops matching
    real citations protects nothing."""
    assert provisions_cited("under section 138 of the NI Act") == {"138"}
    assert provisions_cited("see s. 53A and sec 65") == {"53A", "65"}
    assert provisions_cited("Article 65 governs") == {"65"}
    assert provisions_cited("an injunction under Order XXXIX") == {"XXXIX"}


def test_a_schedule_article_resolves_to_the_key_the_corpus_uses():
    """All 137 Limitation Act Articles are `schedule_article` atoms keyed
    `Article_65`, and they are absent from the parents layer entirely — so a
    section-shaped lookup finds none of them and returns a confident zero."""
    assert wanted_section("limitation under article 65 for possession") == "Article_65"


def test_case_names_are_found_and_prose_is_not():
    assert cases_named("settled by Ramesh Kumar v State of Telangana")
    assert not cases_named("the landlord has issued a quit notice to the tenant")
    assert not cases_named("we act for the plaintiff in a possession suit")


def test_no_module_defines_its_own_provision_pattern():
    """WHAT MAKES THE SECOND COPY IMPOSSIBLE.

    If nothing structurally refuses the duplicate, THAT is the defect — not the
    duplicate. This scan is the structural refusal available in Python: a new
    `section|sec|s\\.` regex anywhere in `nm/` outside the canonical module
    fails the build, and whoever writes it is pointed at the one to import.
    """
    canonical = ROOT / "nm" / "domain" / "citation.py"
    pattern = re.compile(r"re\.compile\([^)]*(?:sections?|article|\bsec\b)",
                         re.I | re.S)
    offenders = []
    for path in sorted((ROOT / "nm").rglob("*.py")):
        if path == canonical:
            continue
        if pattern.search(path.read_text(encoding="utf8")):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "a second provision-reference pattern exists in "
        + ", ".join(offenders)
        + " — import from nm.domain.citation instead. The last time there were "
          "two, one was hardened and the other was not, and a realistic brief "
          "retrieved the wrong section and reported a corpus gap.")


# ============================================ no fuzzy identity ============

@refuses("H3", 0)
def test_an_act_is_named_or_it_is_inferred_and_never_silently_matched():
    """NO FUZZY MATCH DECIDES WHICH DOCUMENT IS RETRIEVED.

    Common words run through every Indian statute title, so overlap scoring is
    not a weak signal — it is a wrong one. Measured in one session:

        "Indian Easements Act 1882" -> "Indian Evidence Act, 1872"  (word)
        "Indian Easements Act 1882" -> "Transfer of Property Act"   (year)
        a s.53A question about the TPA -> the Specific Relief Act   (keyword)

    and in the other direction, matching case NAMES reached 0.83% of judgments
    while matching reporter CITATIONS — an exact key — reached 90.9%.

    Keyword routing survives because an advocate who names no Act still needs
    an answer. What it may no longer do is IDENTIFY: it yields a candidate
    whose basis is `inferred`, and an inferred Act is disclosed so the advocate
    can correct it — the same rule the product already applies to posture.
    """
    from datetime import date

    from nm.knowledge.manifest import ActBasis, Manifest

    m = Manifest.load(ROOT / "spec" / "manifest.yaml")
    on = date(2026, 8, 30)

    named = m.resolve("does section 53A of the Transfer of Property Act apply", on)
    assert named.basis is ActBasis.NAMED
    assert named.entry.act_name == "Transfer of Property Act, 1882"
    assert not named.must_disclose, "an Act the advocate named needs no caveat"

    guessed = m.resolve("he was dispossessed yesterday and wants it back", on)
    assert guessed.basis is ActBasis.INFERRED
    assert guessed.must_disclose, "an inferred Act must be disclosed"
    assert "did not name an Act" in guessed.note()
    assert guessed.matched_on, "the note must say WHAT it was inferred from"

    assert m.resolve("what is the weather in Hyderabad", on).entry is None


def test_a_named_act_beats_every_keyword_score():
    """B-016. Keyword scoring reads the WHOLE question, so the more context an
    advocate gave, the more likely it was to be outvoted — a brief full of
    `possession` and `dispossessed` asking about s.53A of the Transfer of
    Property Act resolved to the Specific Relief Act and reported a corpus gap
    for a provision the corpus holds."""
    from datetime import date

    from nm.knowledge.manifest import ActBasis, Manifest

    m = Manifest.load(ROOT / "spec" / "manifest.yaml")
    brief = ("client was dispossessed from the property and wants possession "
             "back; does section 53A of the Transfer of Property Act protect "
             "him after the injunction and the declaration")
    r = m.resolve(brief, date(2026, 8, 30))
    assert r.entry.act_name == "Transfer of Property Act, 1882"
    assert r.basis is ActBasis.NAMED
