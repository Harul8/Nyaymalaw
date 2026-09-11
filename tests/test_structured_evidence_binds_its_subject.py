"""Structured evidence must authenticate its exact subject and reviewer."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization

from tests.p03_evidence_support import TrustHarness
from tools.backlog import _structured_record, _structured_record_legacy
from tools.evidence import verification_fingerprint
from tools.evidence_verification import configured_verifier
from tools.structured_evidence import RECORDS, SCHEMA, problems

pytestmark = pytest.mark.class_a

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
TREE = "0123456789abcdef0123"
CONFIG = "configuration-2026-09"


def _record(**overrides) -> dict:
    base = {
        "schema": SCHEMA,
        "criterion": "BK-99-AC1",
        "level": "counsel_review",
        "result": "PASS",
        "subject": "Whether the withheld-turn wording is usable by an advocate",
        "method": {
            "procedure": "Read every withheld turn and score it against the rubric",
            "steps": ["enumerate the population", "inspect original output",
                      "record a supported finding for each rubric dimension"],
        },
        "actor": {"person_id": "alice", "name": "A. Reviewer"},
        "authority": {
            "role": "Advocate", "basis": "State Bar enrolment AP/1234/2005",
            "evidence": None,
        },
        "rubric": {
            "identity": "docs/Archives/JOURNEY.md §5 stage rubric",
            "findings": [{
                "id": "usable-withholding", "result": "PASS",
                "basis": "all twelve turns named the reason and next action",
            }],
        },
        "population": {"count": 12, "described": "every withheld turn in slice 4"},
        "reservations": [],
        "observed_at": "2026-09-11T09:00:00+00:00",
        "subject_identity": {
            "kind": "source", "value": TREE,
            "valid_from": "2026-09-11T00:00:00+00:00",
            "valid_until": "2026-10-11T00:00:00+00:00",
        },
        "configuration_identity": CONFIG,
        "attestation": None,
    }
    base.update(overrides)
    return base


@pytest.fixture
def evidence():
    harness = TrustHarness(RECORDS, base=RECORDS.parents[2])
    made: list = []
    serial = 0

    def write(record: dict, name: str = "PROBE-AC1.json") -> tuple[str, TrustHarness]:
        nonlocal serial
        serial += 1
        authority = record.get("authority")
        if isinstance(authority, dict) and not authority.get("evidence"):
            authority["evidence"] = harness.authority(
                f"probe-authority-{serial}.json", person="alice",
                role=str(authority.get("role") or "Advocate"),
                basis=str(authority.get("basis") or "State Bar enrolment AP/1234/2005"),
                scopes=[f"evidence:{record.get('level')}"], now=NOW,
            )
        payload = {key: value for key, value in record.items() if key != "attestation"}
        signer = ((record.get("actor") or {}).get("person_id")
                  if isinstance(record.get("actor"), dict) else "alice")
        record["attestation"] = harness.signed(
            f"probe-attestation-{serial}.json", payload,
            (signer,) if signer in harness.keys else ("alice",),
        )
        path = RECORDS / name
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        made.extend([path, RECORDS / f"probe-authority-{serial}.json",
                     RECORDS / f"probe-attestation-{serial}.json"])
        return f"docs/backlog/evidence/{name}", harness

    yield write
    for path in made:
        path.unlink(missing_ok=True)


def _check(ref: str, harness: TrustHarness, level: str = "counsel_review",
           **kwargs) -> list[str]:
    return problems(
        "BK-99-AC1", level, ref, now=NOW, source_fingerprint=TREE,
        configuration_identity=CONFIG, verifier=harness.verifier, **kwargs,
    )


def test_a_complete_authenticated_record_confers_a_pass(evidence):
    ref, harness = evidence(_record())
    assert _check(ref, harness) == []


def test_a_record_whose_subject_or_configuration_moved_is_stale(evidence):
    ref, harness = evidence(_record())
    moved = problems(
        "BK-99-AC1", "counsel_review", ref, now=NOW,
        source_fingerprint="f" * 20, configuration_identity="another-config",
        verifier=harness.verifier,
    )
    assert any("no longer running" in problem for problem in moved)
    assert any("current configuration" in problem for problem in moved)
    assert _structured_record_legacy("BK-99-AC1", "counsel_review", ref) == []

    unattributed = _record(
        actor={"person_id": "unattributed", "name": "Unknown reviewer"})
    ref, harness = evidence(unattributed, "PROBE-AC1-UNATTRIBUTED.json")
    found = _check(ref, harness)
    assert any("required signer" in problem for problem in found), found


def test_changing_the_indexed_record_after_signature_is_refused(evidence):
    ref, harness = evidence(_record())
    path = RECORDS.parents[2] / ref
    record = json.loads(path.read_text(encoding="utf-8"))
    record["population"]["count"] = 13
    path.write_text(json.dumps(record), encoding="utf-8")
    found = _check(ref, harness)
    assert any("payload does not match" in problem for problem in found), found


def test_an_unconfigured_verifier_is_unavailable_not_valid(evidence):
    ref, _ = evidence(_record())
    found = problems(
        "BK-99-AC1", "counsel_review", ref, now=NOW,
        source_fingerprint=TREE, configuration_identity=CONFIG,
    )
    assert any("verification unavailable" in problem for problem in found), found


def test_operator_owned_public_trust_configuration_is_usable(evidence, tmp_path):
    ref, harness = evidence(_record())
    keys = []
    for person in ("authority-root", "alice"):
        pem = harness.keys[person].public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        keys.append({"person_id": person, "key_id": "key-1", "public_key": pem})
    trust = tmp_path / "trust.json"
    trust.write_text(json.dumps({
        "schema": 1, "configuration_identity": CONFIG,
        "allowed_roots": [str(RECORDS)],
        "authority_issuers": ["authority-root"], "keys": keys,
    }), encoding="utf-8")
    verifier = configured_verifier(
        base=RECORDS.parents[2], environment={"NM_EVIDENCE_TRUST": str(trust)})
    assert problems(
        "BK-99-AC1", "counsel_review", ref, now=NOW,
        source_fingerprint=TREE, configuration_identity=CONFIG,
        verifier=verifier,
    ) == []


def test_the_completion_consumer_rechecks_operator_configuration(evidence,
                                                                  tmp_path,
                                                                  monkeypatch):
    current_tree = verification_fingerprint()
    record = _record(subject_identity={
        "kind": "source", "value": current_tree,
        "valid_from": "2026-09-11T00:00:00+00:00",
        "valid_until": "2026-10-11T00:00:00+00:00",
    })
    ref, harness = evidence(record)
    keys = []
    for person in ("authority-root", "alice"):
        pem = harness.keys[person].public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        keys.append({"person_id": person, "key_id": "key-1", "public_key": pem})
    trust = tmp_path / "trust.json"
    trust.write_text(json.dumps({
        "schema": 1, "configuration_identity": CONFIG,
        "allowed_roots": [str(RECORDS)],
        "authority_issuers": ["authority-root"], "keys": keys,
    }), encoding="utf-8")
    monkeypatch.setenv("NM_EVIDENCE_TRUST", str(trust))
    assert _structured_record("BK-99-AC1", "counsel_review", ref) == []

    changed = json.loads(trust.read_text(encoding="utf-8"))
    changed["configuration_identity"] = "configuration-2026-10"
    trust.write_text(json.dumps(changed), encoding="utf-8")
    found = _structured_record("BK-99-AC1", "counsel_review", ref)
    assert any("current configuration" in problem for problem in found), found


@pytest.mark.parametrize("field", [
    "subject", "method", "actor", "authority", "rubric", "population",
    "observed_at", "subject_identity", "configuration_identity",
])
def test_every_binding_field_is_required(evidence, field):
    ref, harness = evidence(_record(**{field: ""}))
    assert any(field in problem for problem in _check(ref, harness)), field


@pytest.mark.parametrize("change,expected", [
    ({"method": {"procedure": "named only", "steps": []}}, "method steps"),
    ({"rubric": {"identity": "named only", "findings": []}},
     "substantive finding population"),
    ({"rubric": {"identity": "r", "findings": [{
        "id": "one", "result": "NOT_ASSESSED", "basis": "not reviewed",
    }]}}, "PASS record has rubric finding"),
])
def test_present_but_substantively_unperformed_method_cannot_pass(
        evidence, change, expected):
    ref, harness = evidence(_record(**change))
    assert any(expected in problem for problem in _check(ref, harness))


def test_reservations_may_be_empty_and_may_not_be_absent(evidence):
    ref, harness = evidence(_record(reservations=[]))
    assert _check(ref, harness) == []
    absent = _record()
    del absent["reservations"]
    ref, harness = evidence(absent, "PROBE-AC1-B.json")
    assert any("reservations" in problem for problem in _check(ref, harness))


@pytest.mark.parametrize("population,expected", [
    ({"count": 0, "described": "nothing"}, "positive count"),
    ({"count": 12}, "not described"),
    ({"described": "twelve turns"}, "positive count"),
    ({"count": True, "described": "a boolean"}, "positive count"),
    ("twelve turns", "must be an object"),
])
def test_population_is_counted_and_described(evidence, population, expected):
    ref, harness = evidence(_record(population=population))
    assert any(expected in problem for problem in _check(ref, harness))


@pytest.mark.parametrize("level,missing", [
    ("model_eval", "model"),
    ("model_eval", "prompt_identity"),
    ("model_eval", "corpus_identity"),
])
def test_model_evidence_binds_reproducibility_inputs(evidence, level, missing):
    complete = {"model": "m", "prompt_identity": "p", "corpus_identity": "c"}
    complete.pop(missing)
    ref, harness = evidence(_record(level=level, **complete))
    found = _check(ref, harness, level=level)
    assert any(missing in problem for problem in found), found


def test_every_record_expires_and_expiry_is_exclusive(evidence):
    identity = {"kind": "external", "valid_until": NOW.isoformat()}
    ref, harness = evidence(_record(subject_identity=identity))
    assert any("validity ended" in problem for problem in _check(ref, harness))

    unbounded = {"kind": "source", "value": TREE}
    ref, harness = evidence(_record(subject_identity=unbounded), "PROBE-AC1-C.json")
    assert any("valid_until" in problem for problem in _check(ref, harness))


def test_a_future_observation_is_refused(evidence):
    ref, harness = evidence(_record(
        observed_at=(NOW + timedelta(days=1)).isoformat()))
    assert any("future" in problem for problem in _check(ref, harness))


@pytest.mark.parametrize("ref,expected", [
    ("", "no structured evidence record"),
    ("docs/backlog/evidence/report.json#a-row", "no structured evidence record"),
    ("../../etc/passwd", "outside docs/backlog/evidence"),
    ("docs/backlog/evidence/not-there.json", "cannot be read"),
])
def test_an_unreadable_reference_is_refused(ref, expected):
    found = problems("BK-99-AC1", "counsel_review", ref, now=NOW)
    assert any(expected in problem for problem in found), found


def test_a_record_from_before_this_schema_is_not_grandfathered():
    found = _structured_record(
        "BK-21-AC4", "production_measure",
        "docs/backlog/evidence/BK-21-AC4.json",
    )
    assert any("unsupported schema" in problem for problem in found), found
