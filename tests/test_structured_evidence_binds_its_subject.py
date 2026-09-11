"""EVIDENCE A MACHINE DID NOT PRODUCE, BOUND TO WHAT IT WAS ABOUT. BK-80-AC1.

A Class-A result carries its own identity — a fingerprint, an exit code, a node
list. A counsel review, a model evaluation and a production measurement carry
none of that: they are a person or a run asserting something.

The register accepted five fields and treated the resulting PASS as good
forever. THE CRITERION'S OWN NEGATIVE CONTROL IS RUN HERE AGAINST BOTH THE OLD
AND NEW RULES, so "the new rules refuse what the old ones admitted" is measured
rather than claimed:

    reuse a PASS record after changing its subject
    replace a qualified review with an unattributable assertion

WHY THERE IS NO GRANDFATHER CLAUSE
------------------------------------
The one record in `docs/backlog/evidence/` predates this schema and binds none
of what the criterion requires. Accepting it because it is old is absence
reading as success in the one function that decides whether work is proven —
which is the shape this repository has now paid for three times. It fails, and
`BK-21-AC4` moves from PASS to NOT_RUN until somebody who observed that
credential rotation records what it was about.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from tools.backlog import _structured_record, _structured_record_legacy
from tools.structured_evidence import RECORDS, problems

pytestmark = pytest.mark.class_a

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
TREE = "0123456789abcdef0123"


def _record(**overrides) -> dict:
    """A complete, qualified counsel review. Every test starts from valid."""
    base = {
        "schema": 1,
        "criterion": "BK-99-AC1",
        "level": "counsel_review",
        "result": "PASS",
        "subject": "Whether the withheld-turn wording is usable by an advocate",
        "method": "Read twelve withheld turns against the rubric and scored each",
        "actor": "A. Reviewer",
        "authority": "Advocate, enrolled AP/1234/2005, 18 years practice",
        "rubric": "docs/Archives/JOURNEY.md §5 stage rubric, all six dimensions",
        "population": {"count": 12, "described": "every withheld turn in slice 4"},
        "reservations": [],
        "observed_at": "2026-09-11T09:00:00+00:00",
        "subject_identity": {
            "kind": "source",
            "value": TREE,
            "valid_from": "2026-09-11T00:00:00+00:00",
        },
    }
    base.update(overrides)
    return base


@pytest.fixture
def written(tmp_path, monkeypatch):
    """Records live under `docs/backlog/evidence`, so the test writes there and
    removes what it wrote. A tmp_path record would be refused for being outside
    the directory, which is a check worth keeping rather than working around."""
    made: list = []

    def write(record: dict, name: str = "PROBE-AC1.json") -> str:
        path = RECORDS / name
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        made.append(path)
        return f"docs/backlog/evidence/{name}"

    yield write
    for path in made:
        path.unlink(missing_ok=True)


def _check(ref: str, level: str = "counsel_review", **kwargs) -> list[str]:
    return problems("BK-99-AC1", level, ref, now=NOW,
                    source_fingerprint=TREE, **kwargs)


# ============================ the negative control ==========================

def test_a_record_whose_subject_moved_can_no_longer_confer_a_pass(written):
    """*Reuse a PASS record after changing its subject.* THE HALF THE OLD
    RULES COULD NOT SEE: `subject` was prose, so nothing compared it."""
    ref = written(_record())
    assert _check(ref) == [], "the baseline record is not valid"

    moved = problems("BK-99-AC1", "counsel_review", ref, now=NOW,
                     source_fingerprint="ffffffffffffffffffff")
    assert moved, "a judgement about code that is no longer running still passed"
    assert any("no longer running" in p for p in moved), moved

    # AND THE OLD RULES ADMITTED IT. This is the measurement, not the claim.
    assert _structured_record_legacy("BK-99-AC1", "counsel_review", ref) == []


def test_an_unattributable_assertion_is_not_a_qualified_review(written):
    """*Replace a qualified review with an unattributable assertion.*"""
    stripped = _record(actor="someone", authority="", rubric="")
    ref = written(stripped)
    found = _check(ref)
    assert any("authority" in p for p in found), found
    assert any("rubric" in p for p in found), found

    # The old rules read `actor: "someone"` as sufficient attribution.
    assert _structured_record_legacy("BK-99-AC1", "counsel_review", ref) == []


# =========================== what it now requires ===========================

@pytest.mark.parametrize("field", [
    "subject", "method", "actor", "authority", "rubric", "population",
    "observed_at", "subject_identity",
])
def test_every_binding_field_is_required(written, field):
    ref = written(_record(**{field: ""}))
    found = _check(ref)
    assert any(field in p for p in found), (field, found)


def test_reservations_may_be_empty_and_may_not_be_absent(written):
    """§9 in a single field. An empty list is a reviewer saying they had none;
    a missing key is nobody having asked, and those are different facts."""
    assert _check(written(_record(reservations=[]))) == []

    absent = _record()
    del absent["reservations"]
    found = _check(written(absent, "PROBE-AC1-B.json"))
    assert any("reservations" in p for p in found), found


@pytest.mark.parametrize("population,expected", [
    ({"count": 0, "described": "nothing"}, "positive count"),
    ({"count": 12}, "not described"),
    ({"described": "twelve turns"}, "positive count"),
    ({"count": True, "described": "a boolean"}, "positive count"),
    ("twelve turns", "must be an object"),
])
def test_the_population_is_a_counted_and_described_set(written, population, expected):
    """*It worked* about an unstated number of cases is not a measurement."""
    found = _check(written(_record(population=population)))
    assert any(expected in p for p in found), (population, found)


@pytest.mark.parametrize("level,missing", [
    ("model_eval", "model"),
    ("model_eval", "prompt_identity"),
    ("model_eval", "corpus_identity"),
    ("production_measure", "configuration"),
])
def test_a_level_must_bind_what_makes_it_reproducible(written, level, missing):
    """The same prompt against a different model is a different fact."""
    full = {"model": "m", "prompt_identity": "p", "corpus_identity": "c",
            "configuration": "cfg"}
    full.pop(missing)
    ref = written(_record(level=level, **full))
    found = problems("BK-99-AC1", level, ref, now=NOW, source_fingerprint=TREE)
    assert any(missing in p for p in found), (missing, found)


# ====================== either it moves or it expires =======================

def test_an_external_subject_must_carry_a_validity_period(written):
    """A provider's behaviour cannot be recomputed here, so nothing but time
    can retire the record. Without `valid_until` it is PASS forever."""
    ref = written(_record(subject_identity={"kind": "external"}))
    found = _check(ref)
    assert any("valid_until" in p for p in found), found


def test_an_expired_external_record_stops_conferring_a_pass(written):
    ref = written(_record(subject_identity={
        "kind": "external",
        "valid_until": (NOW - timedelta(days=1)).isoformat()}))
    found = _check(ref)
    assert any("validity ended" in p for p in found), found

    still = written(_record(subject_identity={
        "kind": "external",
        "valid_until": (NOW + timedelta(days=30)).isoformat()}),
        "PROBE-AC1-C.json")
    assert _check(still) == []


def test_there_is_no_kind_that_is_neither_checkable_nor_bounded(written):
    """The rule in one assertion: every subject either moves or expires."""
    ref = written(_record(subject_identity={"kind": "trust_me", "value": "x"}))
    found = _check(ref)
    assert any("PASS forever" in p for p in found), found


def test_a_record_observed_before_its_own_validity_began_is_refused(written):
    ref = written(_record(
        observed_at="2026-01-01T00:00:00+00:00",
        subject_identity={"kind": "source", "value": TREE,
                          "valid_from": "2026-09-01T00:00:00+00:00"}))
    found = _check(ref)
    assert any("before its own validity" in p for p in found), found


# ============================ the reader refuses ============================

@pytest.mark.parametrize("ref,expected", [
    ("", "no structured evidence record"),
    ("docs/backlog/evidence/report.json#a-row", "no structured evidence record"),
    ("../../etc/passwd", "outside docs/backlog/evidence"),
    ("docs/backlog/evidence/not-there.json", "cannot be read"),
])
def test_an_unreadable_reference_is_refused_and_never_read_as_absent(ref, expected):
    found = problems("BK-99-AC1", "counsel_review", ref, now=NOW)
    assert any(expected in p for p in found), (ref, found)


def test_a_record_from_before_this_schema_is_refused_rather_than_grandfathered():
    """THE REAL ONE IN THE TREE, and the consequence is stated rather than
    avoided: BK-21-AC4 moves from PASS to NOT_RUN until whoever observed that
    credential rotation records what it was about."""
    found = _structured_record(
        "BK-21-AC4", "production_measure",
        "docs/backlog/evidence/BK-21-AC4.json")
    assert found, "the legacy record still confers a PASS"
    assert any("unsupported schema" in p for p in found), found
