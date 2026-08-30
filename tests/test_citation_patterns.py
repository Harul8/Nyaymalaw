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
from datetime import date
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

    # THE POSITIVE CONTROL. The scan finding nothing is only evidence if
    # the scan can find something -- and a regex that matches nothing
    # passes the assertion above exactly as a clean codebase does.
    planted = 'SECTION = re.compile(r"\\b(?:sections?|sec)\\s*(\\d+)")'
    assert pattern.search(planted), (
        "the scan does not recognise a second provision pattern even when "
        "one is put in front of it, so its silence means nothing")


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


def test_no_act_title_is_a_substring_of_another():
    """WHAT MAKES EXACT TITLE MATCHING SAFE.

    An Act is identified by its title appearing in the question. That is only
    unambiguous while no title contains another — the moment one does, a
    question naming the longer Act also matches the shorter, and the choice
    between them is back to being a guess.

    True of today's 17 Acts. It is a property of the manifest, not a law, so it
    is checked rather than assumed: the eighteenth Act is where it would break.
    """
    from nm.knowledge.manifest import Manifest

    m = Manifest.load(ROOT / "spec" / "manifest.yaml")
    titles = {e.act_name: e.act_name.split(",")[0].strip().lower()
              for e in m.entries}
    collisions = [(a, b) for a, ta in titles.items()
                  for b, tb in titles.items() if ta != tb and ta in tb]
    assert not collisions, (
        "one Act's title contains another's, so matching on the title is "
        f"ambiguous: {collisions}")


def test_no_keyword_is_claimed_by_two_acts():
    """The other half. Keyword routing only produces ONE candidate honestly
    while each keyword belongs to one Act; a shared keyword makes the winner
    depend on iteration order, which is a coin toss wearing a score."""
    import collections

    from nm.knowledge.manifest import Manifest

    m = Manifest.load(ROOT / "spec" / "manifest.yaml")
    owners = collections.defaultdict(list)
    for e in m.entries:
        for k in e.keywords:
            owners[k.lower()].append(e.act_name)
    shared = {k: v for k, v in owners.items() if len(v) > 1}
    assert not shared, f"keywords claimed by more than one Act: {shared}"


def test_an_inferred_act_names_what_else_it_could_have_been():
    """A wrong inference must be visible at a glance. The correction handle
    matters more than the guess."""
    from datetime import date

    from nm.knowledge.manifest import Manifest

    m = Manifest.load(ROOT / "spec" / "manifest.yaml")
    r = m.resolve("he was dispossessed and the claim may be time-barred",
                  date(2026, 8, 30))
    assert r.must_disclose
    assert r.alternatives, "more than one Act matched and only one was named"
    assert "also matched" in r.note()


def test_two_acts_may_share_a_title_only_if_their_windows_do_not_overlap():
    """THE HOLE THE SUBSTRING TEST LEAVES, closed.

    `test_no_act_title_is_a_substring_of_another` skips the case where two
    titles are EQUAL (`ta != tb`), so the manifest can hold two Acts whose
    titles differ only by year — `Consumer Protection Act, 1986` and
    `Consumer Protection Act, 2019` — and nothing objects.

    That is safe, and it is safe for a reason rather than by luck: `_named_in`
    filters on the governing date, so "the Consumer Protection Act" resolves to
    the 1986 Act on a 2015 matter and the 2019 Act on a 2025 one. It stops
    being safe the moment two same-titled Acts are in force at the same time —
    then the title identifies nothing and the choice is a guess, which is the
    one thing exact matching exists to prevent.

    The same reasoning already carries the IPC/BNS and CrPC/BNSS pairs. This
    makes it a checked property instead of an assumption.
    """
    from nm.knowledge.manifest import Manifest, title_without_year

    m = Manifest.load(ROOT / "spec" / "manifest.yaml")
    by_title: dict[str, list] = {}
    for e in m.entries:
        by_title.setdefault(title_without_year(e.act_name).lower(), []).append(e)

    for title, entries in by_title.items():
        if len(entries) < 2:
            continue
        for i, a in enumerate(entries):
            for b in entries[i + 1:]:
                a_to = a.in_force_to or date(9999, 12, 31)
                b_to = b.in_force_to or date(9999, 12, 31)
                a_from = a.in_force_from or date(1, 1, 1)
                b_from = b.in_force_from or date(1, 1, 1)
                overlap = a_from <= b_to and b_from <= a_to
                assert not overlap, (
                    f"{a.act_name!r} and {b.act_name!r} share the title "
                    f"{title!r} and are BOTH in force between "
                    f"{max(a_from, b_from)} and {min(a_to, b_to)}. An advocate "
                    f"naming that title identifies neither, and the resolver "
                    f"would pick one by list order — a guess wearing the shape "
                    f"of an exact match.")


def test_a_superseded_act_is_declared_rather_than_dropped():
    """A matter governed by an Act no longer in force is not a corpus gap.

    Dropping the 1986 Consumer Protection Act would make a 2015 consumer
    matter report NOT HELD for a statute the corpus holds in full — the same
    failure the CrPC transition produces, where a keyword match on an out-of-
    force Act must surface as "that Act existed, on a different date" rather
    than as a flat absence.
    """
    from nm.knowledge.manifest import ActBasis, Manifest

    m = Manifest.load(ROOT / "spec" / "manifest.yaml")

    old = m.resolve("section 12 of the Consumer Protection Act",
                    on=date(2015, 6, 1))
    assert old.entry is not None and old.basis is ActBasis.NAMED
    assert "1986" in old.entry.act_name, (
        f"a 2015 consumer matter resolved to {old.entry.act_name!r}")

    new = m.resolve("section 35 of the Consumer Protection Act",
                    on=date(2025, 6, 1))
    assert new.entry is not None and "2019" in new.entry.act_name
