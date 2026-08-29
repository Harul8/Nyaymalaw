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


def test_the_era_pair_is_retrievable_on_both_sides(adapter):
    """The era rule is only testable because both codes are held."""
    old = adapter.fetch(need("section 447 of the indian penal code"))
    new = adapter.fetch(need("section 329 of the bharatiya nyaya sanhita"))
    assert old.coverage is Coverage.ANSWERED
    assert new.coverage is Coverage.ANSWERED


def test_a_question_naming_no_provision_is_refused_rather_than_guessed(adapter):
    result = adapter.fetch(need("the limitation position on this file generally"))
    assert result.coverage is Coverage.NOT_HELD
    assert "no specific provision" in result.missing
