"""Real signatures with test-only keys; no production legal approval is supplied."""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization

from nm.Archives.legal_brain.retrieve.provision_review import (
    CRITERION,
    FINDINGS,
    RUBRIC,
    build_revision_review_owner,
)
from nm.Archives.legal_brain.retrieve.provision_revision_sources import RevisionReviewRequest, SelectionState
from tests.p03_evidence_support import TrustHarness
from tests.test_provision_revisions_need_owned_interval_proof import CHECKED, population

pytestmark = pytest.mark.class_a
NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
CONFIG = "synthetic-revision-trust-1"


class ReviewedFixture:
    def __init__(self, root, *, title="Synthetic Procedure Act, 2001", section="7"):
        self.root = root
        self.evidence = root / "docs" / "backlog" / "evidence"
        self.harness = TrustHarness(self.evidence, base=root)
        self.pop = population(title=title, section=section)
        self.section = section
        self.revision = self.pop[4]
        expected = self.pop[6](self.revision)
        self.request = RevisionReviewRequest(
            expected.subject_id, expected.authority_digest, expected.version_ids, CHECKED
        )
        self.clock = NOW
        self.config = root / "trust.json"
        self.trust()

    def trust(self, **changes):
        config = {
            "schema": 1, "configuration_identity": CONFIG,
            "allowed_roots": [str(self.evidence)],
            "authority_issuers": ["authority-root"],
            "keys": [{
                "person_id": person, "key_id": "key-1",
                "public_key": key.public_key().public_bytes(
                    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
                ).decode("ascii"),
            } for person, key in self.harness.keys.items()],
        }
        config.update(changes)
        self.config.write_text(json.dumps(config), encoding="utf8")

    def record(self):
        request = self.request
        return {
            "schema": 2, "criterion": CRITERION, "level": "counsel_review", "result": "PASS",
            "subject": {
                "kind": "provision_revision", "subject_id": request.subject_id,
                "authority_digest": request.authority_digest,
                "version_ids": list(request.version_ids),
            },
            "method": {"procedure": "Review every held proof and exact dated interval",
                       "steps": ["read exact text", "test both interval boundaries"]},
            "actor": {"person_id": "alice", "name": "Synthetic A. Reviewer"},
            "authority": {"role": "Advocate", "basis": "Synthetic Bar qualification",
                          "evidence": None},
            "rubric": {"identity": RUBRIC, "findings": [
                {"id": key, "result": "PASS", "basis": "Inspected the synthetic primary proof"}
                for key in sorted(FINDINGS)
            ]},
            "population": {"count": len(request.version_ids),
                           "described": "Every exact held source version for this revision"},
            "reservations": [], "observed_at": (NOW - timedelta(hours=1)).isoformat(),
            "subject_identity": {"kind": "source", "value": request.subject_id,
                                 "valid_until": (NOW + timedelta(days=1)).isoformat()},
            "configuration_identity": CONFIG, "attestation": None,
        }

    def write(self, record=None, *, name="review.json", signer="alice", grant=None):
        record = copy.deepcopy(self.record() if record is None else record)
        authority = record["authority"]
        authority["evidence"] = grant or self.harness.authority(
            name + ".authority", person=record["actor"]["person_id"],
            role=authority["role"], basis=authority["basis"],
            scopes=["evidence:counsel_review"], now=NOW,
        )
        payload = {key: value for key, value in record.items() if key != "attestation"}
        record["attestation"] = self.harness.signed(name + ".signed", payload, (signer,))
        path = self.evidence / name
        path.write_text(json.dumps(record), encoding="utf8")
        return "docs/backlog/evidence/" + name, record

    def owner(self, refs, **changes):
        options = dict(base=self.root, artifact_refs=refs, now=lambda: self.clock,
                       environment={"NM_EVIDENCE_TRUST": str(self.config)})
        options.update(changes)
        return build_revision_review_owner(**options)


@pytest.mark.parametrize("title,section", [
    ("Synthetic Procedure Act, 2001", "7"),
    ("Synthetic Revenue Rules, 1997", "Article_17"),
    ("Synthetic Property Code, 1888", "40A"),
])
def test_actual_signed_review_and_issuer_chain_select_exact_revision(tmp_path, title, section):
    fixture = ReviewedFixture(tmp_path, title=title, section=section)
    ref, record = fixture.write()
    owner = fixture.owner((ref,))
    approval = owner(fixture.request)
    assert approval is not None
    proof = approval.qualification
    assert proof is not None
    assert (proof.person_id, proof.role, proof.basis, proof.issuer_ids) == (
        "alice", "Advocate", "Synthetic Bar qualification", ("authority-root",)
    )
    assert proof.authority_sha256 == record["authority"]["evidence"]["sha256"]
    assert json.loads(proof.grant_payload_json)["scopes"] == ["evidence:counsel_review"]
    registry, contents, source = fixture.pop[:3]
    selected = registry.select_provision_revision(
        source.source_id, section, CHECKED, checked_at=CHECKED,
        source_bytes=contents.get, review_owner=owner,
    )
    assert selected.state is SelectionState.SELECTED
    assert selected.revision == fixture.revision
    captured = selected.as_record()["approval"]["qualification"]
    assert captured["authority_sha256"] == proof.authority_sha256
    assert captured["issuer_ids"] == ["authority-root"]
    assert captured["valid_until"] == proof.valid_until


@pytest.mark.parametrize("change", [
    {"subject_id": "other-revision"}, {"authority_digest": "f" * 64},
    {"version_ids": ("unknown-version",)}, {"version_ids": ()},
    {"checked_at": CHECKED - timedelta(days=1)}, {"checked_at": NOW},
])
def test_receipt_does_not_transfer_to_a_different_subject_proof_population_or_date(
    tmp_path, change
):
    fixture = ReviewedFixture(tmp_path)
    ref, _record = fixture.write()
    assert fixture.owner((ref,))(replace(fixture.request, **change)) is None


@pytest.mark.parametrize("change", [
    lambda row: row["subject"].update(authority_digest="f" * 64),
    lambda row: row["subject"]["version_ids"].pop(),
    lambda row: row["subject"]["version_ids"].append("extra"),
    lambda row: row["subject"]["version_ids"].reverse(),
    lambda row: row["subject"].update(reviewed=True),
    lambda row: row["population"].update(count=True),
    lambda row: row["population"].update(count=3.0),
    lambda row: row.update(schema=2.0),
    lambda row: row.update(reservations=["Effective interval not established"]),
    lambda row: row["rubric"]["findings"].pop(),
    lambda row: row["rubric"].update(identity="self-qualified"),
    lambda row: row["rubric"]["findings"][0].update(result="NOT_ASSESSED"),
    lambda row: row["subject_identity"].update(value="unrelated-subject"),
    lambda row: row.update(configuration_identity="old-policy"),
    lambda row: row.update(result="WITHDRAWN"),
    lambda row: row.update(criterion="other-criterion"),
    lambda row: row.update(level="production_measure"),
])
def test_authentication_does_not_fill_missing_or_incompatible_legal_review_bindings(
    tmp_path, change
):
    fixture = ReviewedFixture(tmp_path)
    record = fixture.record()
    change(record)
    ref, _row = fixture.write(record)
    assert fixture.owner((ref,))(fixture.request) is None


def test_no_trust_no_review_and_caller_flags_remain_unassessed(tmp_path):
    fixture = ReviewedFixture(tmp_path)
    ref, record = fixture.write()
    assert fixture.owner((ref,), environment={})(fixture.request) is None
    assert fixture.owner(())(fixture.request) is None
    assert fixture.owner(("docs/backlog/evidence/not-there.json",))(fixture.request) is None
    record["attestation"] = {"ref": ref, "sha256": "a" * 64}
    (fixture.evidence / "review.json").write_text(json.dumps(record), encoding="utf8")
    assert fixture.owner((ref,))(fixture.request) is None


@pytest.mark.parametrize("variant", ["role", "basis", "person", "scope", "issuer", "expiry"])
def test_grant_kind_alone_is_not_qualified_current_authority(tmp_path, variant):
    fixture = ReviewedFixture(tmp_path)
    record = fixture.record()
    payload = {
        "kind": "authority_grant", "person_id": "alice", "role": "Advocate",
        "basis": "Synthetic Bar qualification", "scopes": ["evidence:counsel_review"],
        "valid_from": (NOW - timedelta(days=2)).isoformat(),
        "valid_until": (NOW + timedelta(days=2)).isoformat(),
    }
    issuer = "authority-root"
    if variant == "role":
        record["authority"]["role"] = payload["role"] = "Account holder"
    elif variant == "basis":
        payload["basis"] = "Another person's qualification"
    elif variant == "person":
        payload["person_id"] = "bob"
    elif variant == "scope":
        payload["scopes"] = ["evidence:production_measure"]
    elif variant == "issuer":
        issuer = "mallory"
    elif variant == "expiry":
        payload["valid_until"] = NOW.isoformat()
    grant = fixture.harness.signed("grant.json", payload, (issuer,))
    ref, _record = fixture.write(record, grant=grant)
    assert fixture.owner((ref,))(fixture.request) is None


def test_current_key_rotation_issuer_revocation_and_artifact_withdrawal_are_rechecked(tmp_path):
    fixture = ReviewedFixture(tmp_path)
    ref, record = fixture.write()
    owner = fixture.owner((ref,))
    assert owner(fixture.request) is not None
    fixture.trust(authority_issuers=["bob"])
    assert owner(fixture.request) is None
    fixture.trust()
    assert owner(fixture.request) is not None
    document = json.loads(fixture.config.read_text(encoding="utf8"))
    document["keys"] = [row for row in document["keys"] if row["person_id"] != "alice"]
    fixture.config.write_text(json.dumps(document), encoding="utf8")
    assert owner(fixture.request) is None
    fixture.trust()
    record["population"]["described"] = "Changed after signing"
    (fixture.evidence / "review.json").write_text(json.dumps(record), encoding="utf8")
    assert owner(fixture.request) is None
    fixture.write()
    assert owner(fixture.request) is not None
    (fixture.evidence / "review.json").unlink()
    assert owner(fixture.request) is None


def test_expiry_uses_actual_instant_not_the_receipts_date_only_boundary(tmp_path):
    fixture = ReviewedFixture(tmp_path)
    record = fixture.record()
    record["subject_identity"]["valid_until"] = (NOW + timedelta(minutes=30)).isoformat()
    ref, _record = fixture.write(record)
    owner = fixture.owner((ref,))
    assert owner(fixture.request) is not None
    fixture.clock = NOW + timedelta(minutes=30)
    assert owner(fixture.request) is None


def test_a_second_positive_or_withdrawn_matching_record_is_not_ranked_away(tmp_path):
    fixture = ReviewedFixture(tmp_path)
    first, _record = fixture.write()
    second, _record = fixture.write(name="second.json")
    assert fixture.owner((first, second))(fixture.request) is None
    withdrawn = fixture.record()
    withdrawn["result"] = "FAIL"
    fixture.write(withdrawn, name="second.json")
    assert fixture.owner((first, second))(fixture.request) is None


@pytest.mark.parametrize("ref", [
    "", "https://law.example/review.json", "../review.json", "review.json",
    "docs/backlog/evidence/review.json#approve", "/tmp/review.json",
])
def test_bootstrap_allowlist_is_bounded_to_the_existing_evidence_namespace(tmp_path, ref):
    fixture = ReviewedFixture(tmp_path)
    with pytest.raises(ValueError):
        fixture.owner((ref,))


def test_signatures_and_grants_cannot_escape_the_evidence_root_even_if_trust_allows_it(tmp_path):
    fixture = ReviewedFixture(tmp_path)
    fixture.trust(allowed_roots=[str(tmp_path)])
    external = tmp_path / "outside.json"
    external.write_text("{}", encoding="utf8")
    ref, record = fixture.write()
    record["authority"]["evidence"]["ref"] = "outside.json"
    payload = {key: value for key, value in record.items() if key != "attestation"}
    record["attestation"] = fixture.harness.signed("outside-grant.signed", payload, ("alice",))
    (fixture.evidence / "review.json").write_text(json.dumps(record), encoding="utf8")
    assert fixture.owner((ref,))(fixture.request) is None


@pytest.mark.parametrize("raw", [b"not json", b'{"subject": NaN}', b'{"subject":{},"subject":{}}'])
def test_unusable_original_records_do_not_become_absent_success(tmp_path, raw):
    fixture = ReviewedFixture(tmp_path)
    path = fixture.evidence / "bad.json"
    path.write_bytes(raw)
    assert fixture.owner(("docs/backlog/evidence/bad.json",))(fixture.request) is None


def test_review_fails_closed_if_its_original_grant_changes_during_the_lookup(tmp_path, monkeypatch):
    fixture = ReviewedFixture(tmp_path)
    ref, record = fixture.write()
    from nm.Archives.legal_brain.retrieve import provision_review

    actual = provision_review.problems_for_record
    calls = 0

    def changing(*args, **kwargs):
        nonlocal calls
        result = actual(*args, **kwargs)
        calls += 1
        if calls == 2:
            path = fixture.root / record["authority"]["evidence"]["ref"]
            path.write_bytes(b"withdrawn")
        return result

    monkeypatch.setattr(provision_review, "problems_for_record", changing)
    assert fixture.owner((ref,))(fixture.request) is None


def test_unreviewed_candidate_can_not_override_an_original_negative_review(tmp_path):
    fixture = ReviewedFixture(tmp_path)
    record = fixture.record()
    record["result"] = "FAIL"
    record["rubric"]["findings"][0]["result"] = "FAIL"
    ref, _record = fixture.write(record)
    registry, content, source = fixture.pop[:3]
    result = registry.select_provision_revision(
        source.source_id, fixture.section, CHECKED, checked_at=CHECKED,
        source_bytes=content.get, review_owner=fixture.owner((ref,)),
    )
    assert result.state is SelectionState.NOT_ASSESSED
    assert result.approval is None
