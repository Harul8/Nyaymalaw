"""The corpus evidence adapter — the three-state answer and the union rule.

Class C: needs the real corpus, so it runs on ingest rather than every commit,
and skips cleanly when the corpus is not attached.

THESE ARE THE TESTS THAT WOULD HAVE CAUGHT B-164
------------------------------------------------
The previous build recorded "Acts are PARTIALLY ingested" as a priority-one
blocker and struck three golden-scenario expectations on the strength of it.
The Acts were complete the whole time; the query hit the thin `snake_case`
store. That single defect shape has now produced a false gap three separate
times in this project, so it is pinned here against the real corpus rather
than trusted to discipline.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.adapters.evidence.corpus import CorpusEvidenceAdapter
from nm.bootstrap.composition import ROOT
from nm.knowledge.manifest import Manifest
from nm.ports.evidence import Coverage, EvidenceNeed

pytestmark = pytest.mark.class_c

CORPUS = ROOT / "legal_database" / "vector_store"


@pytest.fixture(scope="module")
def adapter():
    manifest = Manifest.load(ROOT / "spec" / "manifest.yaml")
    a = CorpusEvidenceAdapter(CORPUS, manifest)
    if not a.available:
        pytest.skip("the corpus is not attached")
    return a


def need(question: str) -> EvidenceNeed:
    return EvidenceNeed(question=question, governing_date=date(2026, 8, 29))


@pytest.mark.eval_id("E-002b")
def test_the_union_retrieves_a_section_the_thin_store_does_not_hold(adapter):
    """THE COUNTEREXAMPLE, against the real corpus.

    Specific Relief Act s.6 is ABSENT from `the_specific_relief_act_1963`,
    which holds 13 scattered sections. It is present in the uppercase copy,
    which holds all 44. A single-store lookup reports a gap that is not there.
    """
    result = adapter.fetch(need("client was dispossessed yesterday — what does "
                                "section 6 of the specific relief act give us?"))
    assert result.coverage is Coverage.ANSWERED, (
        f"s.6 must be found via the union. Got {result.coverage.value}: {result.missing}")
    finding = result.findings[0]
    assert "SPECIFIC RELIEF ACT, 1963" in finding.locator.upper()
    assert "dispossessed" in finding.span.lower()
    assert finding.usable


@pytest.mark.eval_id("E-002b")
def test_a_zero_result_names_the_stores_it_searched(adapter):
    """S3: a zero result that cannot name its index is indistinguishable from
    absence, and that is how three false gaps happened."""
    result = adapter.fetch(need("section 9999 of the specific relief act"))
    assert result.coverage is not Coverage.ANSWERED
    assert result.searched_stores, "a zero result must name where it looked"
    assert result.missing


@pytest.mark.eval_id("E-023")
def test_a_section_outside_intended_coverage_is_an_honest_refusal(adapter):
    """NOT_HELD is computed from the manifest, never inferred from a hit count,
    and it NAMES what is missing."""
    result = adapter.fetch(need("section 9999 of the specific relief act"))
    assert result.coverage is Coverage.NOT_HELD
    assert "9999" in result.missing


@pytest.mark.eval_id("E-023")
def test_an_unreadable_corpus_is_not_reported_as_nothing_held(tmp_path):
    """An absent input must never read as an answer.

    A corpus that cannot be read is HELD_NOT_FOUND -- a defect that escalates --
    and never NOT_HELD, which would tell the advocate the law does not exist.
    """
    manifest = Manifest.load(ROOT / "spec" / "manifest.yaml")
    broken = CorpusEvidenceAdapter(tmp_path / "nothing-here", manifest)
    result = broken.fetch(need("section 6 of the specific relief act"))
    assert result.coverage is Coverage.HELD_NOT_FOUND
    assert "not readable" in result.missing


def test_the_limitation_schedule_resolves_as_an_article(adapter):
    """Schedule Articles are `schedule_article` atoms and absent from the
    parents layer, so a section-shaped lookup finds none of them."""
    result = adapter.fetch(need("what is the limitation under article 65 for possession"))
    assert result.coverage is Coverage.ANSWERED
    assert "Article_65" in result.findings[0].locator


def test_the_governing_date_decides_which_code_answers(adapter):
    """THE ERA RULE, and it now bites rather than merely being possible.

    Both codes are held, so asking for each by name at today's date used to
    return both -- which proved only that the corpus was complete. The property
    that matters is that THE GOVERNING DATE PICKS: an offence in 2019 is
    answered from the IPC and one in 2025 from the BNS, and asking for the IPC
    at a 2025 date does NOT return the superseded text.
    """
    before = EvidenceNeed(question="section 447 of the indian penal code",
                          governing_date=date(2019, 6, 1))
    after = EvidenceNeed(question="section 329 of the bharatiya nyaya sanhita",
                         governing_date=date(2025, 6, 1))
    assert adapter.fetch(before).coverage is Coverage.ANSWERED
    assert adapter.fetch(after).coverage is Coverage.ANSWERED

    # The superseded code, asked for after its repeal. It is NOT served.
    stale = adapter.fetch(EvidenceNeed(
        question="section 447 of the indian penal code",
        governing_date=date(2025, 6, 1)))
    assert stale.coverage is not Coverage.ANSWERED
    # And the refusal says WHY -- not in force on that date -- rather than
    # reporting a gap in a corpus that plainly holds all 574 sections.
    assert "not in force" in (stale.missing or "")


def test_a_question_naming_no_provision_is_refused_rather_than_guessed(adapter):
    result = adapter.fetch(need("the limitation position on this file generally"))
    assert result.coverage is Coverage.NOT_HELD
    assert "no specific provision" in result.missing


@pytest.mark.eval_id("E-024")
def test_coverage_is_a_union_and_a_single_store_figure_is_refused(adapter):
    """THE COUNTEREXAMPLE: a coverage report saying the Act holds 13 of 44
    sections.

    That is B-164, the previous build's priority-one blocker. It struck three
    golden-scenario expectations on the strength of a figure measured from one
    store, and the Acts were complete the whole time. The same shape has since
    produced a false gap in this project three more times.

    Two things are asserted, and the second is what makes the first honest:
    the union finds what a single store does not, AND the single-store figure
    is genuinely different — so a check that passed by measuring one store
    would have been measuring a wrong number, not an unlucky one.
    """
    import sqlite3

    from nm.knowledge.manifest import Manifest

    manifest = Manifest.load(ROOT / "spec" / "manifest.yaml")
    entry = manifest.act("Specific Relief Act, 1963")
    assert entry and len(entry.act_patterns) > 1, (
        "the union rule is untestable against an Act held under one convention")

    con = sqlite3.connect(f"file:{CORPUS / 'chunks.db'}?mode=ro", uri=True)
    try:
        per_store, union = {}, set()
        for pattern in entry.act_patterns:
            rows = con.execute(
                "select distinct section_number from chunks where "
                "doc_type='bare_act' and act_id like ? and section_number is not null",
                (pattern,)).fetchall()
            found = {r[0] for r in rows}
            per_store[pattern] = found
            union |= found
    finally:
        con.close()

    smallest = min(per_store.values(), key=len)
    assert len(union) > len(smallest), (
        "the union adds nothing over the thinnest store, so this Act cannot "
        "demonstrate the rule")

    # THE SPECIFIC FALSE GAP: s.6 is absent from the thin copy and present in
    # the union. An advocate asking about summary possession got nothing.
    assert "6" not in smallest
    assert "6" in union

    # And the adapter, which is what actually serves, uses the union.
    result = adapter.fetch(need("section 6 of the specific relief act"))
    assert result.coverage is Coverage.ANSWERED
    assert len(result.searched_stores) > 1, (
        "a coverage answer that searched one store cannot refuse a "
        "single-store figure")
