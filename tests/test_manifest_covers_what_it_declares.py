"""Every Act the manifest DECLARES must actually retrieve from the corpus.

WHY THIS EXISTS
---------------
The manifest states INTENDED coverage, and that is load-bearing: a miss inside
it escalates as a RETRIEVAL DEFECT, while a miss outside it is an honest corpus
gap. So a declared Act the corpus cannot serve turns a real gap into a reported
defect — the worse of the two, because it sends someone hunting a bug in the
lookup.

B-048 added five Acts and REFUSED a sixth on the measurement: Motor Vehicles
matched 381 chunks across six ids and every one was a notification, an
amendment, or an Andhra taxation Act — the principal Act is not held. That
refusal was the right call and it was made by hand, at a terminal, once.

Nothing checked it afterwards. The register named "verified by retrieval: all
six probe sections ANSWERED from the corpus" as the check, which is a
description of something I did, not something that runs — and
`tests/test_defect_register.py` caught exactly that on its first execution.

THE OTHER DIRECTION IS NOT CHECKED HERE, deliberately. "Every Act in the corpus
should be in the manifest" is false: the corpus holds thousands of instruments
and the manifest is a curated list of what this product claims to answer for.
Coverage breadth is a product decision, recorded in BASELINE.md; what this file
refuses is a CLAIM the corpus cannot honour.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "legal_database" / "vector_store"

pytestmark = pytest.mark.class_c


@pytest.fixture(scope="module")
def adapter():
    if not (CORPUS / "chunks.db").exists():
        pytest.skip("the corpus is not attached")
    from nm.adapters.evidence.corpus import CorpusEvidenceAdapter
    from nm.knowledge.manifest import Manifest

    manifest = Manifest.load(ROOT / "spec" / "manifest.yaml")
    return CorpusEvidenceAdapter(CORPUS, manifest), manifest


def test_the_manifest_declares_enough_acts_to_be_worth_checking(adapter):
    _, manifest = adapter
    assert len(manifest.entries) >= 15, (
        f"only {len(manifest.entries)} Acts declared — this file would then be "
        f"asserting almost nothing")


def test_every_declared_act_retrieves_at_least_one_intended_section(adapter):
    """THE CHECK B-048 SHOULD HAVE COME WITH.

    For each declared Act, take the FIRST section it claims and ask the real
    adapter for it, at a date the Act was in force. An Act that cannot answer
    for the first provision it declares is a claim the corpus cannot honour.
    """
    from nm.ports.evidence import Coverage, EvidenceNeed

    ad, manifest = adapter
    failures: list[str] = []
    for entry in manifest.entries:
        section = _first_intended(entry)
        if section is None:
            failures.append(f"{entry.act_name}: declares no intended sections")
            continue
        on = _in_force_date(entry)
        need = EvidenceNeed(
            question=f"section {section} of the {entry.act_name}",
            governing_date=on)
        result = ad.fetch(need)
        if result.coverage is not Coverage.ANSWERED:
            failures.append(
                f"{entry.act_name}: s.{section} on {on} -> "
                f"{result.coverage.value} ({(result.missing or '')[:90]})")

    assert not failures, (
        f"{len(failures)} declared Act(s) cannot serve the first provision they "
        f"claim:\n  " + "\n  ".join(failures)
        + "\n\nThe manifest states INTENDED coverage, so a miss inside it "
          "escalates as a RETRIEVAL DEFECT rather than reading as an honest "
          "corpus gap. Either the patterns are wrong, or the Act should not be "
          "declared — Motor Vehicles was refused for exactly this reason.")


def test_an_act_the_corpus_cannot_serve_is_caught(adapter):
    """THE POSITIVE CONTROL.

    The test above asserts that a bad state is absent, which a check that
    always returns nothing also satisfies. So a declaration the corpus cannot
    honour is planted, and the adapter must fail to answer it — otherwise the
    check above proves nothing about the checker.
    """
    import dataclasses

    from nm.adapters.evidence.corpus import CorpusEvidenceAdapter
    from nm.knowledge.manifest import ManifestEntry
    from nm.ports.evidence import Coverage, EvidenceNeed

    _, manifest = adapter
    ghost = ManifestEntry(
        act_name="Motor Vehicles Act, 1988",
        act_patterns=("%THE MOTOR VEHICLES ACT, 1988%",),
        intended_sections=frozenset({"166"}),
        in_force_from=date(1989, 7, 1), in_force_to=None,
        keywords=("motor accident claim",))
    # A FRESH manifest rather than a mutated one: `Manifest` is frozen, and
    # that is right -- a test that could reach in and edit the live manifest
    # would be a test that can leave the next one measuring something else.
    planted = dataclasses.replace(manifest, entries=(*manifest.entries, ghost))
    result = CorpusEvidenceAdapter(CORPUS, planted).fetch(EvidenceNeed(
        question="section 166 of the Motor Vehicles Act",
        governing_date=date(2025, 1, 1)))
    assert result.coverage is not Coverage.ANSWERED, (
        "the corpus answered for an Act whose principal text it does not "
        "hold — the check above would then pass on anything")


def _first_intended(entry) -> str | None:
    """The lowest plain section number the Act declares.

    Ranges are expanded by the loader, so this is a set of strings. Schedule
    Articles and lettered sections are skipped: they are legitimate, and they
    are not the simplest thing to ask for.
    """
    plain = sorted((s for s in entry.intended_sections if s.isdigit()), key=int)
    return plain[0] if plain else (sorted(entry.intended_sections)[0]
                                   if entry.intended_sections else None)


def _in_force_date(entry) -> date:
    """A date the Act was certainly in force.

    Asking on today's date would fail every superseded Act for the right
    reason and the wrong purpose — this file checks retrieval, not the era
    rule, which `tests/test_corpus_evidence.py` already covers.
    """
    if entry.in_force_to is not None:
        return entry.in_force_to
    start = entry.in_force_from or date(1950, 1, 1)
    return max(start, date(2025, 1, 1))
