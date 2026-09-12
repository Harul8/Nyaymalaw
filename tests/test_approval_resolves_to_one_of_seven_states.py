"""Only authenticated, exact and current adoption can authorise one gate."""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from tests.p03_evidence_support import TrustHarness
from tools.blueprint_approvals import (
    EVALUATION_UNAVAILABLE,
    EXPIRED,
    NOT_RECORDED,
    OUT_OF_SCOPE,
    REVOKED,
    STALE,
    STATES,
    UNVERIFIED,
    VALID,
    resolve,
    resolve_packet_approvals,
)
from tools.evidence_verification import canonical_json

pytestmark = pytest.mark.class_a

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


@dataclass
class Context:
    harness: TrustHarness
    choice: dict
    choices: dict
    packets: dict
    schema: dict
    record: dict
    store: dict
    attempt: dict


def _context(tmp_path, *, gate="confidential_pilot", run_id=None,
             people=("alice",), signed_by=None, authority_scopes=None,
             conditions=(), valid_until="2026-12-01T00:00:00+00:00") -> Context:
    harness = TrustHarness(tmp_path, base=ROOT)
    choice = {
        "id": "CHOICE-02", "title": "Synthetic decision",
        "approval_required_for": [gate],
    }
    choices = {"choices": [choice]}
    packets = {"packets": [{"id": "P03", "decisions": ["CHOICE-02"]}]}
    schema = json.loads((ROOT / "docs/blueprint/approvals.schema.json")
                        .read_text(encoding="utf-8"))
    artifacts = {
        name: harness.raw(f"{name}.json", f"{name}-bytes".encode())
        for name in ("release_manifest", "configuration", "coverage_manifest")
    }
    scope = {
        "gate": gate, "environment": "isolated-test", "release_profile": "pilot",
        **artifacts, "packets": ["P03"],
        "capabilities": ["evidence-resolution"], "data_classes": ["synthetic"],
        "run_id": run_id,
    }
    approvers = []
    for person in people:
        role = "accountable owner"
        basis = "delegated by the product owner"
        scopes = authority_scopes or [f"approval:CHOICE-02:{gate}"]
        approvers.append({
            "person_id": person, "name": person.title(), "role": role,
            "authority_basis": basis,
            "authority_evidence": harness.authority(
                f"authority-{person}.json", person=person, role=role, basis=basis,
                scopes=scopes, now=NOW,
            ),
        })
    proposal = hashlib.sha256(canonical_json(choice)).hexdigest()
    record = {
        "id": "ADOPT-01", "choice": "CHOICE-02",
        "proposal_sha256": proposal, "scope": scope,
        "approvers": approvers, "signed_record": None,
        "approved_at": "2026-09-01T00:00:00+00:00",
        "effective_from": "2026-09-02T00:00:00+00:00",
        "valid_until": valid_until,
        "conditions": list(conditions), "supersedes": [],
    }
    payload = {key: value for key, value in record.items() if key != "signed_record"}
    record["signed_record"] = harness.signed(
        "adoption.json", payload, tuple(signed_by or people))
    store = {"schema": 1, "purpose": "synthetic Class-A adoption",
             "records": [record], "revocations": []}
    attempt = {
        "choice": "CHOICE-02", "gate": gate, "packet": "P03",
        "proposal_sha256": proposal, "environment": "isolated-test",
        "release_profile": "pilot", **artifacts,
        "capabilities": ["evidence-resolution"], "data_classes": ["synthetic"],
        "run_id": run_id, "required_approvers": frozenset(people),
        "verifier": harness.verifier, "now": NOW, "schema": schema,
    }
    return Context(harness, choice, choices, packets, schema, record, store, attempt)


_DEFAULT_STORE = object()


def _resolve(context: Context, store=_DEFAULT_STORE, **overrides):
    options = dict(context.attempt)
    options.update(overrides)
    return resolve(
        context.store if store is _DEFAULT_STORE else store,
        context.choices, context.packets, **options,
    )


def _resign(context: Context, name="adoption-revised.json", signers=None):
    payload = {key: value for key, value in context.record.items()
               if key != "signed_record"}
    context.record["signed_record"] = context.harness.signed(
        name, payload, tuple(signers or [p["person_id"]
                                        for p in context.record["approvers"]]))


def _add_revocation(context: Context) -> dict:
    person = context.record["approvers"][0]
    revoker = dict(person)
    revoker["authority_evidence"] = context.harness.authority(
        "revoke-authority.json", person="alice", role=person["role"],
        basis=person["authority_basis"],
        scopes=["revoke:CHOICE-02:confidential_pilot"], now=NOW)
    revocation = {
        "id": "REVOKE-01", "approval_id": "ADOPT-01",
        "effective_at": "2026-09-05T00:00:00+00:00",
        "revoked_by": revoker, "reason": "authority withdrawn",
        "signed_record": None,
    }
    payload = {key: value for key, value in revocation.items()
               if key != "signed_record"}
    revocation["signed_record"] = context.harness.signed(
        "revocation.json", payload, ("alice",))
    context.store["revocations"] = [revocation]
    return revocation


def test_a_complete_authentic_matching_approval_authorises_one_prerequisite(tmp_path):
    context = _context(tmp_path)
    got = _resolve(context)
    assert got.state == VALID, got.why
    assert got.authorises and got.record == "ADOPT-01"
    assert got.availability == "available"


def test_a_digest_string_without_a_verifier_never_becomes_authority(tmp_path):
    context = _context(tmp_path)
    got = _resolve(context, verifier=None)
    assert got.state == UNVERIFIED and not got.authorises
    assert got.availability == EVALUATION_UNAVAILABLE


def test_empty_store_and_unreadable_store_are_different(tmp_path):
    context = _context(tmp_path)
    empty = {"schema": 1, "purpose": "empty", "records": [], "revocations": []}
    assert _resolve(context, empty).state == NOT_RECORDED
    for unreadable in (None, {}, {"records": "not a list"}, []):
        got = _resolve(context, unreadable)
        assert got.state == UNVERIFIED
        assert got.availability == EVALUATION_UNAVAILABLE


def test_changed_signed_payload_or_artifact_bytes_is_refused(tmp_path):
    context = _context(tmp_path)
    context.record["scope"]["capabilities"].append("new-power")
    got = _resolve(context, capabilities=["evidence-resolution", "new-power"])
    assert got.state == UNVERIFIED and "payload does not match" in got.why

    context = _context(tmp_path / "bytes")
    config = ROOT / context.record["scope"]["configuration"]["ref"]
    config.write_bytes(b"changed")
    got = _resolve(context)
    assert got.state == UNVERIFIED and "digest" in got.why


def test_missing_joint_signer_or_wrong_authority_scope_is_unverified(tmp_path):
    joint = _context(tmp_path / "joint", people=("alice", "bob"),
                     signed_by=("alice",))
    assert _resolve(joint).state == UNVERIFIED

    wrong = _context(tmp_path / "scope", authority_scopes=["approval:CHOICE-02:production"])
    got = _resolve(wrong)
    assert got.state == UNVERIFIED and "does not cover" in got.why


@pytest.mark.parametrize("field,value", [
    ("environment", "another-environment"),
    ("release_profile", "production"),
    ("packet", "P42"),
    ("capabilities", ["external-action"]),
    ("data_classes", ["client-confidential"]),
])
def test_scope_cannot_be_widened(tmp_path, field, value):
    context = _context(tmp_path)
    got = _resolve(context, **{field: value})
    assert got.state == OUT_OF_SCOPE and not got.authorises


def test_changed_proposal_configuration_or_manifest_is_stale(tmp_path):
    context = _context(tmp_path)
    assert _resolve(context, proposal_sha256="d" * 64).state == STALE
    for field in ("configuration", "release_manifest", "coverage_manifest"):
        attempted = dict(context.attempt[field], sha256="e" * 64)
        assert _resolve(context, **{field: attempted}).state == STALE


def test_not_yet_effective_exact_expiry_and_expired_are_distinct(tmp_path):
    context = _context(tmp_path / "future")
    before = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
    assert _resolve(context, now=before).state == UNVERIFIED

    exact = _context(tmp_path / "exact", valid_until=NOW.isoformat())
    assert _resolve(exact).state == EXPIRED

    after = _context(tmp_path / "after",
                     valid_until="2026-09-10T00:00:00+00:00")
    assert _resolve(after).state == EXPIRED


def test_verified_revocation_revokes_and_forged_revocation_blocks(tmp_path):
    context = _context(tmp_path / "valid")
    assert _resolve(context).state == VALID
    revocation = _add_revocation(context)
    assert _resolve(context).state == REVOKED

    revocation["reason"] = "forged different reason"
    got = _resolve(context)
    assert got.state == UNVERIFIED and "competing revocation" in got.why


def test_bk80_ac6_refuses_stale_revoked_unauthorised_and_wider_use(tmp_path):
    stale = _context(tmp_path / "stale")
    results = [_resolve(stale, proposal_sha256="d" * 64)]

    unauthorised = _context(tmp_path / "unauthorised", signed_by=("mallory",))
    results.append(_resolve(unauthorised))

    wider = _context(tmp_path / "wider")
    results.append(_resolve(wider, data_classes=["client-confidential"]))

    revoked = _context(tmp_path / "revoked")
    _add_revocation(revoked)
    results.append(_resolve(revoked))

    expired = _context(
        tmp_path / "expired", valid_until="2026-09-10T00:00:00+00:00")
    results.append(_resolve(expired))

    assert [result.state for result in results] == [
        STALE, UNVERIFIED, OUT_OF_SCOPE, REVOKED, EXPIRED,
    ]
    assert all(not result.authorises for result in results)


def test_a_verified_narrower_replacement_supersedes_the_prior_scope(tmp_path):
    context = _context(tmp_path)
    context.record["scope"]["capabilities"].append("external-action")
    _resign(context, "adoption-broader.json")

    replacement = copy.deepcopy(context.record)
    replacement.update({
        "id": "ADOPT-02",
        "approved_at": "2026-09-03T00:00:00+00:00",
        "effective_from": "2026-09-04T00:00:00+00:00",
        "supersedes": ["ADOPT-01"],
        "signed_record": None,
    })
    replacement["scope"]["capabilities"] = ["evidence-resolution"]
    payload = {key: value for key, value in replacement.items()
               if key != "signed_record"}
    replacement["signed_record"] = context.harness.signed(
        "adoption-narrower.json", payload, ("alice",))
    context.store["records"].append(replacement)

    current = _resolve(context)
    assert current.state == VALID and current.record == "ADOPT-02"
    refused = _resolve(
        context, capabilities=["evidence-resolution", "external-action"])
    assert refused.state == OUT_OF_SCOPE
    assert "external-action" in refused.why

    replacement["valid_until"] = "2027-01-01T00:00:00+00:00"
    forged = _resolve(context)
    assert forged.state == UNVERIFIED
    assert "payload does not match" in forged.why


def test_a_separate_gate_record_does_not_hide_the_attempted_gate(tmp_path):
    context = _context(tmp_path)
    context.choice["approval_required_for"].append("production")
    other = copy.deepcopy(context.record)
    other.update({
        "id": "ADOPT-02",
        "approved_at": "2026-09-03T00:00:00+00:00",
        "effective_from": "2026-09-04T00:00:00+00:00",
        "signed_record": None,
    })
    other["scope"]["gate"] = "production"
    person = other["approvers"][0]
    person["authority_evidence"] = context.harness.authority(
        "authority-production.json", person="alice", role=person["role"],
        basis=person["authority_basis"],
        scopes=["approval:CHOICE-02:production"], now=NOW)
    payload = {key: value for key, value in other.items()
               if key != "signed_record"}
    other["signed_record"] = context.harness.signed(
        "adoption-production.json", payload, ("alice",))
    context.store["records"].append(other)

    got = _resolve(context)
    assert got.state == VALID and got.record == "ADOPT-01"


def test_verified_condition_is_current_and_tampering_blocks(tmp_path):
    harness = TrustHarness(tmp_path, base=ROOT)
    evidence = harness.condition(
        "condition.json", approval_id="ADOPT-01", condition_id="COND-1",
        requirement="isolated rehearsal", now=NOW)
    context = _context(tmp_path, conditions=({
        "id": "COND-1", "requirement": "isolated rehearsal", "evidence": evidence,
    },))
    # The context owns its own verifier, so recreate the condition through it.
    context.record["conditions"][0]["evidence"] = context.harness.condition(
        "condition-owned.json", approval_id="ADOPT-01", condition_id="COND-1",
        requirement="isolated rehearsal", now=NOW)
    _resign(context)
    assert _resolve(context).state == VALID
    context.record["conditions"][0]["requirement"] = "a different rehearsal"
    assert _resolve(context).state == UNVERIFIED


def test_time_or_trust_unavailable_is_an_assessment_state(tmp_path):
    context = _context(tmp_path)
    got = _resolve(context, time_available=False)
    assert got.availability == EVALUATION_UNAVAILABLE
    assert not got.authorises


def test_bounded_run_cannot_be_replayed(tmp_path):
    context = _context(tmp_path, gate="approved_real_model", run_id="run-001")
    got = _resolve(context, used_run_ids=frozenset({"run-001"}))
    assert got.state == OUT_OF_SCOPE and "already consumed" in got.why


def test_actual_packet_resolution_checks_only_its_applicable_choices(tmp_path):
    context = _context(tmp_path)
    unrelated = {"id": "CHOICE-09", "title": "Unrelated procurement",
                 "approval_required_for": ["procurement"]}
    context.choices["choices"].append(unrelated)
    context.packets["packets"][0]["decisions"].append("CHOICE-09")
    got = resolve_packet_approvals(
        context.store, context.choices, context.packets,
        packet="P03", gate="confidential_pilot", environment="isolated-test",
        release_profile="pilot",
        release_manifest=context.attempt["release_manifest"],
        configuration=context.attempt["configuration"],
        coverage_manifest=context.attempt["coverage_manifest"],
        capabilities=["evidence-resolution"], data_classes=["synthetic"],
        run_id=None, proposal_sha256={"CHOICE-02": context.attempt["proposal_sha256"]},
        required_approvers={"CHOICE-02": frozenset({"alice"})},
        verifier=context.harness.verifier, now=NOW, schema=context.schema,
    )
    assert set(got) == {"CHOICE-02"}
    assert got["CHOICE-02"].state == VALID


def test_unrelated_local_synthetic_packet_has_no_blanket_approval_block(tmp_path):
    context = _context(tmp_path)
    context.packets["packets"].append({"id": "P99", "decisions": ["CHOICE-02"]})
    got = resolve_packet_approvals(
        context.store, context.choices, context.packets,
        packet="P99", gate="local_synthetic", environment="local",
        release_profile="prototype",
        release_manifest=context.attempt["release_manifest"],
        configuration=context.attempt["configuration"],
        coverage_manifest=context.attempt["coverage_manifest"],
        capabilities=["unit-test"], data_classes=["synthetic"], run_id=None,
        proposal_sha256={}, required_approvers={},
        verifier=context.harness.verifier, now=NOW,
    )
    assert got == {}


def test_only_valid_authorises_and_all_seven_states_remain_distinct(tmp_path):
    context = _context(tmp_path)
    assert set(STATES) == {
        NOT_RECORDED, UNVERIFIED, VALID, STALE, EXPIRED, REVOKED, OUT_OF_SCOPE,
    }
    for got in (_resolve(context), _resolve(context, environment="other"),
                _resolve(context, proposal_sha256="d" * 64)):
        assert got.why and got.authorises == (got.state == VALID)


def test_the_resolver_has_no_measurement_or_proposal_flag_input():
    accepted = set(inspect.signature(resolve).parameters)
    forbidden = {"result", "results", "evaluation", "evaluations", "measurement",
                 "passed", "coverage", "proposal_flag", "approved"}
    assert not (accepted & forbidden), sorted(accepted & forbidden)
