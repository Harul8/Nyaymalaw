"""Offline adoption contracts reject claims of authority they cannot establish."""
from __future__ import annotations

import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from tools import blueprint
from tools.blueprint_approvals import adoption_blockers, adoption_labels, check_approvals

pytestmark = pytest.mark.class_a


def _fixture():
    contracts = blueprint.load_contracts()
    # Synthetic attestation only, constructed in memory. No real approval is
    # authored or a verified human/signature result simulated by this fixture.
    artifact = {"ref": "synthetic://not-a-real-signed-artifact", "sha256": "a" * 64}
    person = {"person_id": "synthetic-person", "name": "Fictional reviewer",
              "role": "engineering owner", "authority_basis": "Synthetic test only",
              "authority_evidence": deepcopy(artifact)}
    record = {
        "id": "ADOPT-synthetic-01", "choice": "CHOICE-02", "proposal_sha256": "b" * 64,
        "scope": {"gate": "confidential_pilot", "environment": "synthetic-local",
                  "release_profile": "synthetic-pilot", "release_manifest": deepcopy(artifact),
                  "configuration": deepcopy(artifact), "coverage_manifest": deepcopy(artifact),
                  "packets": ["P03"], "capabilities": ["synthetic-reading"],
                  "data_classes": ["synthetic"], "run_id": None},
        "approvers": [person], "signed_record": deepcopy(artifact),
        "approved_at": "2026-09-01T09:00:00Z", "effective_from": "2026-09-01T10:00:00Z",
        "valid_until": "2026-10-01T10:00:00Z", "conditions": [], "supersedes": [],
    }
    store = deepcopy(contracts["approvals"])
    store["records"] = [record]
    store["revocations"] = []
    return contracts, store, record


def _errors(contracts, store):
    return check_approvals(store, contracts["approval_schema"],
                           contracts["decisions"], contracts["packets"])


def test_empty_adoption_store_is_valid_structure_but_not_approval():
    contracts = blueprint.load_contracts()
    store = {"schema": 1, "purpose": "Synthetic empty population", "records": [], "revocations": []}
    assert len(contracts["decisions"]["choices"]) == 10
    assert _errors(contracts, store) == []
    labels = adoption_labels(store, contracts["decisions"])
    assert len(labels) == 10
    assert set(labels.values()) == {"no adoption record recorded"}
    assert len(adoption_blockers(store, contracts["decisions"])) == 10


def test_structurally_valid_manual_attestation_is_not_machine_verified():
    contracts, store, record = _fixture()
    assert _errors(contracts, store) == []
    contracts["approvals"] = store
    labels = adoption_labels(store, contracts["decisions"])
    assert "approval not machine-resolved / manual verification required" in labels["CHOICE-02"]
    assert record["id"] in labels["CHOICE-02"]
    assert labels["CHOICE-01"] == "no adoption record recorded"
    blockers = blueprint.readiness_blockers(contracts)
    # BK-80-AC6 IS NOW IMPLEMENTED, so the criterion's own "until implemented,
    # report it as not machine-resolved" clause no longer applies. What this
    # test protects is unchanged and is asserted more sharply below: a record
    # scoped to a PACKET gate must not authorise a DEPLOYMENT gate, and the
    # reason must name which gate rather than abstaining about all of them.
    assert any("CHOICE-02" in line and "out_of_scope" in line
               for line in blockers), blockers
    assert not any("has not approved" in line for line in blockers)
    assert any("cannot authorise deployment" in line for line in blockers)
    # The proposal remains a proposal; populating a separate store does not
    # author a second ready flag or silently mutate the choice catalogue.
    assert all(row["approval"] is None for row in contracts["decisions"]["choices"])


@pytest.mark.parametrize("store", [None, {}, {"records": []},
                                   {"schema": 1, "purpose": "x", "records": [None], "revocations": []}])
def test_unavailable_or_unreadable_population_never_reads_as_no_approval(store):
    contracts = blueprint.load_contracts()
    labels = adoption_labels(store, contracts["decisions"])
    assert len(labels) == 10
    assert all("evaluation unavailable" in label for label in labels.values())
    assert not any("no adoption record" in label for label in labels.values())


@pytest.mark.parametrize("probe,expected", [
    ("missing_population", "records"), ("unknown_store_field", "Additional properties"),
    ("authored_valid", "Additional properties"), ("authored_verified", "Additional properties"),
    ("synthetic_bypass", "Additional properties"), ("missing_signer", "approvers"),
    ("missing_authority_evidence", "authority_evidence"), ("missing_signed_record", "signed_record"),
    ("malformed_digest", "does not match"), ("unknown_choice", "unknown choice"),
    ("digest_trailing_newline", "too long"),
    ("unknown_packet", "unknown packet"), ("wrong_packet_choice", "does not govern packet"),
    ("wrong_gate", "gate does not apply"), ("wildcard_scope", "does not match"),
    ("empty_scope", "non-empty"), ("missing_configuration", "configuration"),
    ("missing_expiry", "valid_until"), ("date_without_timezone", "date-time"),
    ("malformed_date", "date-time"), ("impossible_date", "date-time"),
    ("invalid_offset_minutes", "date-time"), ("invalid_offset_hours", "date-time"),
    ("reversed_effectiveness", "approved_at <= effective_from"),
    ("zero_validity", "effective_from < valid_until"),
    ("duplicate_record", "duplicate record"), ("duplicate_approver", "duplicate approvers"),
    ("duplicate_condition", "duplicate conditions"),
    ("dangling_supersession", "unknown superseded"),
    ("self_supersession", "supersession requires older"),
    ("dangling_revocation", "unknown revoked record"),
    ("revocation_before_approval", "revocation predates approval"),
    ("duplicate_revocation", "duplicate revocation"),
])
def test_adoption_controls_reject_planted_failures(probe, expected):
    contracts, store, row = _fixture()
    assert _errors(contracts, store) == []
    before = deepcopy(store)
    if probe == "missing_population":
        del store["records"]
    elif probe == "unknown_store_field":
        store["verified"] = True
    elif probe in {"authored_valid", "authored_verified", "synthetic_bypass"}:
        row[{"authored_valid": "status", "authored_verified": "verified",
             "synthetic_bypass": "accept_as_verified_for_test"}[probe]] = True
    elif probe == "missing_signer":
        row["approvers"].clear()
    elif probe == "missing_authority_evidence":
        del row["approvers"][0]["authority_evidence"]
    elif probe == "missing_signed_record":
        del row["signed_record"]
    elif probe == "malformed_digest":
        row["signed_record"]["sha256"] = "trusted"
    elif probe == "digest_trailing_newline":
        row["signed_record"]["sha256"] += "\n"
    elif probe == "unknown_choice":
        row["choice"] = "CHOICE-99"
    elif probe == "unknown_packet":
        row["scope"]["packets"] = ["P999"]
    elif probe == "wrong_packet_choice":
        other = next(p for p in contracts["packets"]["packets"] if "CHOICE-02" not in p["decisions"])
        row["scope"]["packets"] = [other["id"]]
    elif probe == "wrong_gate":
        row["scope"]["gate"] = "procurement"
    elif probe == "wildcard_scope":
        row["scope"]["environment"] = "*"
    elif probe == "empty_scope":
        row["scope"]["capabilities"].clear()
    elif probe == "missing_configuration":
        del row["scope"]["configuration"]
    elif probe == "missing_expiry":
        del row["valid_until"]
    elif probe in {"date_without_timezone", "malformed_date", "impossible_date",
                   "invalid_offset_minutes", "invalid_offset_hours"}:
        row["valid_until"] = {"date_without_timezone": "2026-10-01T10:00:00",
                              "malformed_date": "soon", "impossible_date": "2026-02-30T10:00:00Z",
                              "invalid_offset_minutes": "2026-10-01T10:00:00+01:99",
                              "invalid_offset_hours": "2026-10-01T10:00:00+25:01"}[probe]
    elif probe == "reversed_effectiveness":
        row["effective_from"] = "2026-09-01T08:00:00Z"
    elif probe == "zero_validity":
        row["valid_until"] = row["effective_from"]
    elif probe == "duplicate_record":
        store["records"].append(deepcopy(row))
    elif probe == "duplicate_approver":
        row["approvers"].append(deepcopy(row["approvers"][0]))
    elif probe == "duplicate_condition":
        condition = {"id": "synthetic-condition", "requirement": "Inspect synthetic artifact",
                     "evidence": deepcopy(row["signed_record"])}
        row["conditions"] = [condition, deepcopy(condition)]
    elif probe == "dangling_supersession":
        row["supersedes"] = ["ADOPT-missing"]
    elif probe == "self_supersession":
        row["supersedes"] = [row["id"]]
    elif probe in {"dangling_revocation", "revocation_before_approval", "duplicate_revocation"}:
        revoked = {"id": "REVOKE-synthetic-01", "approval_id": row["id"],
                   "effective_at": "2026-09-01T12:00:00Z",
                   "revoked_by": deepcopy(row["approvers"][0]), "reason": "Synthetic test only",
                   "signed_record": deepcopy(row["signed_record"])}
        store["revocations"] = [revoked]
        if probe == "dangling_revocation":
            revoked["approval_id"] = "ADOPT-missing"
        elif probe == "revocation_before_approval":
            revoked["effective_at"] = "2026-08-01T12:00:00Z"
        else:
            store["revocations"].append(deepcopy(revoked))
    else:
        pytest.fail(f"Unimplemented probe {probe}")
    assert store != before, "The planted failure must actually change its intended input"
    errors = _errors(contracts, store)
    assert any(expected in error for error in errors), errors


def test_bounded_run_permission_requires_exact_run_identity():
    contracts, store, row = _fixture()
    row["choice"] = "CHOICE-06"
    row["scope"]["packets"] = [next(p["id"] for p in contracts["packets"]["packets"]
                                     if "CHOICE-06" in p["decisions"])]
    for gate in ("approved_real_model", "paid_or_long_load"):
        row["scope"]["gate"] = gate
        row["scope"]["run_id"] = "synthetic-one-run"
        assert _errors(contracts, store) == []
        row["scope"]["run_id"] = None
        assert any("run_id" in error for error in _errors(contracts, store))


@pytest.mark.parametrize("probe,expected", [
    ("remote", "references must be local"), ("dangling", "dangling reference"),
    ("invalid_type", "invalid schema"),
    ("remote_metaschema", "unsupported identity or metaschema"),
    ("nested_id", "rebasing is forbidden"),
    ("nested_metaschema", "rebasing is forbidden"),
    ("dynamic_ref", "dynamic/recursive resolution is forbidden"),
    ("recursive_ref", "dynamic/recursive resolution is forbidden"),
])
def test_adoption_schema_cannot_fetch_remote_or_dangling_definitions(probe, expected):
    contracts, store, _ = _fixture()
    assert _errors(contracts, store) == []
    before = deepcopy(contracts["approval_schema"])
    prop = contracts["approval_schema"]["properties"]["purpose"]
    assert "$ref" in prop
    if probe == "remote":
        prop["$ref"] = "https://example.invalid/do-not-fetch"
    elif probe == "dangling":
        prop["$ref"] = "#/$defs/does-not-exist"
    elif probe == "invalid_type":
        contracts["approval_schema"]["type"] = "a-new-json-type"
    elif probe == "remote_metaschema":
        contracts["approval_schema"]["$schema"] = "https://example.invalid/do-not-fetch"
    else:
        inserted = {"nested_id": "$id", "nested_metaschema": "$schema",
                    "dynamic_ref": "$dynamicRef", "recursive_ref": "$recursiveRef"}[probe]
        assert inserted not in prop
        prop[inserted] = "https://example.invalid/do-not-fetch"
    assert contracts["approval_schema"] != before
    assert any(expected in error for error in _errors(contracts, store))


def test_signed_history_is_retained_without_becoming_a_validity_claim():
    contracts, store, first = _fixture()
    second = deepcopy(first)
    second["id"] = "ADOPT-synthetic-02"
    second["approved_at"] = "2026-09-02T09:00:00Z"
    second["effective_from"] = "2026-09-02T10:00:00Z"
    second["supersedes"] = [first["id"]]
    store["records"].append(second)
    store["revocations"] = [{"id": "REVOKE-synthetic-02", "approval_id": second["id"],
                            "effective_at": "2026-09-03T12:00:00Z",
                            "revoked_by": deepcopy(first["approvers"][0]), "reason": "Synthetic test",
                            "signed_record": deepcopy(first["signed_record"])}]
    assert _errors(contracts, store) == []
    label = adoption_labels(store, contracts["decisions"])["CHOICE-02"]
    assert first["id"] in label and second["id"] in label
    assert "manual verification required" in label
    store["records"].reverse()
    assert adoption_labels(store, contracts["decisions"])["CHOICE-02"] == label


@pytest.mark.parametrize("probe", ["missing", "unreadable", "malformed", "duplicate_key", "invalid_utf8"])
def test_cli_reports_unavailable_adoption_register_without_empty_success(tmp_path, monkeypatch, capsys, probe):
    # Read the real contract population from an isolated copy. The CLI keeps its
    # actual module/backlog/source checks; only the loader's root is redirected.
    # Neither the loader result nor any validation/readiness verdict is mocked.
    contracts_dir = tmp_path / "docs/blueprint"
    contracts_dir.mkdir(parents=True)
    source_dir = blueprint.ROOT / "docs/blueprint"
    sources = sorted(source_dir.rglob("*.json"))
    assert sources and (source_dir / "approvals.json") in sources
    for source in sources:
        relative = source.relative_to(source_dir)
        destination = contracts_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    actual_load = blueprint.load_contracts
    modules, registry = blueprint.load()
    assert blueprint.check_all(modules, registry, actual_load(tmp_path)) == []
    register = contracts_dir / "approvals.json"
    assert register.is_file()
    if probe == "missing":
        register.unlink()
    elif probe == "unreadable":
        register.unlink()
        register.mkdir()  # Actual OS read failure, independent of user chmod privileges.
    elif probe == "malformed":
        register.write_text('{"schema":', encoding="utf-8")
    elif probe == "duplicate_key":
        register.write_text('{"schema":1,"schema":1,"purpose":"x","records":[],"revocations":[]}',
                            encoding="utf-8")
    else:
        register.write_bytes(b"\xff\xfe\x80")
    loaded = actual_load(tmp_path)
    assert loaded["approvals"] is None, "Unavailable data must never become an empty valid register"
    errors = blueprint.check_all(modules, registry, loaded)
    assert any("approvals: register unavailable" in error for error in errors), errors
    monkeypatch.setattr(blueprint, "load_contracts", lambda: actual_load(tmp_path))
    for command in ("check", "readiness"):
        monkeypatch.setattr("sys.argv", [str(Path(blueprint.__file__)), command])
        assert blueprint.main() == 1
        output = capsys.readouterr().out
        assert "FAIL: approvals: register unavailable" in output
        assert "no adoption record recorded" not in output
        if command == "readiness":
            # UNREADABLE IS NOT EMPTY, and that is the whole point of this
            # parametrisation. The wording moved when the resolver replaced the
            # abstention; the distinction it exists to protect did not.
            assert "CHOICE-01" in output and "unverified" in output, output
            assert "unreadable" in output or "does not verify" in output
            assert "cannot authorise deployment" in output
