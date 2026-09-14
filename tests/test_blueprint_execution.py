"""Execution planning controls must reject real mutations for the intended reason.

These are Class-A static-contract tests, not browser, legal or deployment proof.
Every probe starts from the current valid population and changes an existing
field (except the expressly forbidden authored-state insertion).
"""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from assurance.control_plane import blueprint
from assurance.control_plane.blueprint_execution import check_decisions, check_packets
from assurance.control_plane.evidence import verification_fingerprint

pytestmark = pytest.mark.class_a


def _fixture():
    modules, registry = blueprint.load()
    contracts = blueprint.load_contracts()
    populations = {
        "commands": {row["id"] for row in contracts["commands"]["x-commands"]},
        "decisions": {row["id"] for row in contracts["decisions"]["choices"]},
        "scenarios": {row["id"] for row in contracts["evaluations"]["synthetic_cases"]},
    }
    return modules, registry, contracts, populations


def _packet_errors(modules, registry, contracts, populations):
    return check_packets(contracts["packets"], registry, modules,
                         populations["commands"], populations["decisions"],
                         populations["scenarios"], blueprint.ROOT)


def _packet(contracts, identifier):
    return next(row for row in contracts["packets"]["packets"]
                if row["id"] == identifier)


def _item(registry, identifier):
    return next(row for row in registry["items"] if row["id"] == identifier)


def _criterion(registry, identifier):
    return next(ac for row in registry["items"] for ac in row.get("acceptance") or []
                if ac["id"] == identifier)


def test_execution_packets_cover_current_active_criteria_with_single_final_owners():
    modules, registry, contracts, populations = _fixture()
    packets = contracts["packets"]["packets"]
    required = {ac["id"] for row in registry["items"]
                if not row.get("legacy")
                and row["delivery_status"] not in {"deferred", "superseded"}
                and row["id"] not in {"BK-87", "BK-89", "BK-90"}
                for ac in row.get("acceptance") or []}
    final = [ac for row in packets for ac in row["final_criteria"]]
    assert len(packets) >= 45
    assert len(required) >= 175
    assert len(populations["commands"]) >= 50
    assert len(populations["scenarios"]) >= 28
    assert len(final) == len(set(final)) == len(required)
    assert set(final) == required
    assert _packet_errors(modules, registry, contracts, populations) == []


@pytest.mark.parametrize("probe,expected", [
    ("empty_packets", "packets: empty population"),
    ("duplicate_packet", "packets: invalid or duplicate IDs"),
    ("work_namespace_collision", "packets: IDs collide with work-item namespace"),
    ("unknown_packet_reference", "unknown prerequisites reference P999"),
    ("unknown_module", "P01: unknown module or kind"),
    ("malformed_module", "P01: unknown module or kind"),
    ("unknown_kind", "P01: unknown module or kind"),
    ("unknown_criterion", "unknown criteria reference BK-999-AC1"),
    ("missing_final_owner", "packets: no final owner for BK-80-AC3"),
    ("double_final_owner", "invalid final owner population BK-80-AC3 (2)"),
    ("final_without_contribution", "final criterion BK-80-AC3 is not a contribution"),
    ("reversed_contribution", "reversed/missing contribution P16 for BK-54-AC1"),
    ("mixed_item_packet_cycle", "combined dependency cycle:"),
    ("active_item_without_criteria", "BK-80: active item has no acceptance criteria"),
    ("criterion_without_requirement", "BK-80-AC3 lacks criterion-specific proof specification"),
    ("criterion_without_negative", "BK-80-AC3 lacks criterion-specific proof specification"),
    ("criterion_without_method", "BK-80-AC3 lacks criterion-specific proof specification"),
    ("empty_proof", "P01: negative proof empty or unknown scenario"),
    ("unknown_proof", "P01: live proof empty or unknown scenario"),
    ("empty_inputs", "P01: empty or malformed inputs"),
    ("empty_outputs", "P01: empty or malformed outputs"),
    ("empty_steps", "P01: empty or malformed steps"),
    ("empty_rollback", "P01: missing rollback"),
    ("empty_boundaries", "P01: missing source boundaries"),
    ("boundary_escape", "P01: boundary escapes workspace"),
    ("missing_existing_boundary", "P01: missing existing boundary"),
    ("authored_status", "authored status forbidden"),
    ("unknown_command", "unknown commands reference absent-command"),
    ("unknown_decision", "unknown decisions reference CHOICE-99"),
    ("unknown_completed_item", "unknown requires_completed_items reference BK-999"),
    ("empty_decisions", "P01: empty or malformed decisions"),
    ("unowned_command", "packets: command has no execution owner upload-chunk"),
    ("empty_execution_policy", "execution policy missing, unknown or blank"),
    ("unknown_execution_policy", "execution policy missing, unknown or blank"),
])
def test_execution_packet_controls_reject_planted_failures(probe, expected):
    modules, registry, contracts, populations = _fixture()
    assert _packet_errors(modules, registry, contracts, populations) == []
    before = deepcopy((modules, registry, contracts, populations))
    rows = contracts["packets"]["packets"]
    first = _packet(contracts, "P01")
    if probe == "empty_packets":
        rows.clear()
    elif probe == "duplicate_packet":
        rows.append(deepcopy(first))
    elif probe == "work_namespace_collision":
        assert _item(registry, "BK-88")
        assert not any(row["id"] == "BK-88" for row in rows)
        _packet(contracts, "P12")["id"] = "BK-88"
        # Rename genuine incoming edges too: an unrelated dangling-reference
        # complaint must not stand in for refusing graph namespace overwrite.
        for row in rows:
            row["prerequisites"] = ["BK-88" if ref == "P12" else ref
                                    for ref in row["prerequisites"]]
    elif probe == "unknown_packet_reference":
        first["prerequisites"].append("P999")
    elif probe == "unknown_module":
        first["module"] = "M99"
    elif probe == "malformed_module":
        first["module"] = ["M00"]
    elif probe == "unknown_kind":
        first["kind"] = "self_certified"
    elif probe == "unknown_criterion":
        first["criteria"].append("BK-999-AC1")
    elif probe == "missing_final_owner":
        assert "BK-80-AC3" in first["final_criteria"]
        first["final_criteria"].remove("BK-80-AC3")
    elif probe == "double_final_owner":
        other = _packet(contracts, "P03")
        other["criteria"].append("BK-80-AC3")
        other["final_criteria"].append("BK-80-AC3")
    elif probe == "final_without_contribution":
        assert "BK-80-AC3" in first["criteria"]
        first["criteria"].remove("BK-80-AC3")
    elif probe == "reversed_contribution":
        first["criteria"].append("BK-54-AC1")
        first["final_criteria"].append("BK-54-AC1")
        final = _packet(contracts, "P25")
        assert "BK-54-AC1" in final["final_criteria"]
        final["final_criteria"].remove("BK-54-AC1")
    elif probe == "mixed_item_packet_cycle":
        # Packet-only and item-only DAGs remain separately acyclic. The real
        # cycle crosses BK-88 -> BK-83 -> final P38 -> P12 -> BK-88.
        _packet(contracts, "P12")["requires_completed_items"].append("BK-88")
    elif probe == "active_item_without_criteria":
        item = _item(registry, "BK-80")
        assert not item.get("legacy") and item["acceptance"]
        item["acceptance"].clear()
    elif probe == "criterion_without_requirement":
        _criterion(registry, "BK-80-AC3")["requirement"] = " "
    elif probe == "criterion_without_negative":
        criterion = _criterion(registry, "BK-80-AC3")
        assert criterion["negative_control"]["mutation"]
        criterion["negative_control"]["mutation"] = ""
    elif probe == "criterion_without_method":
        _criterion(registry, "BK-80-AC3")["required_evidence"].clear()
    elif probe == "empty_proof":
        first["proof"]["negative"].clear()
    elif probe == "unknown_proof":
        first["proof"]["live"] = ["EVAL-999"]
    elif probe == "empty_inputs":
        first["inputs"].clear()
    elif probe == "empty_outputs":
        first["outputs"].clear()
    elif probe == "empty_steps":
        first["steps"].clear()
    elif probe == "empty_rollback":
        first["rollback"] = " "
    elif probe == "empty_boundaries":
        first["boundaries"].clear()
    elif probe == "boundary_escape":
        first["boundaries"][0]["path"] = "../outside-workspace.txt"
    elif probe == "missing_existing_boundary":
        first["boundaries"][0]["path"] = "docs/blueprint/NO_SUCH_BOUNDARY.py"
    elif probe == "authored_status":
        assert "status" not in first
        first["status"] = "done"
    elif probe == "unknown_command":
        first["commands"].append("absent-command")
    elif probe == "unknown_decision":
        first["decisions"].append("CHOICE-99")
    elif probe == "unknown_completed_item":
        first["requires_completed_items"].append("BK-999")
    elif probe == "empty_decisions":
        first["decisions"].clear()
    elif probe == "unowned_command":
        owners = [row for row in rows if "upload-chunk" in row["commands"]]
        assert owners, "the command must be genuinely mapped before removing it"
        for owner in owners:
            owner["commands"].remove("upload-chunk")
    elif probe == "empty_execution_policy":
        contracts["packets"]["execution_policy"]["proof_semantics"] = " "
    elif probe == "unknown_execution_policy":
        policy = contracts["packets"]["execution_policy"]
        assert "self_approved" not in policy
        policy["self_approved"] = "true"
    else:
        pytest.fail(f"unimplemented probe {probe}")
    assert (modules, registry, contracts, populations) != before, (
        "a probe that mutates nothing proves nothing")
    errors = _packet_errors(modules, registry, contracts, populations)
    assert any(expected in error for error in errors), errors
    if probe == "mixed_item_packet_cycle":
        assert any("P12" in error and "BK-88" in error
                   and "combined dependency cycle" in error for error in errors), errors


@pytest.mark.parametrize("probe,expected", [
    ("empty_decisions", "decisions: empty population"),
    ("missing_decision", "expected ten unique CHOICE-01 through CHOICE-10"),
    ("duplicate_decision", "expected ten unique CHOICE-01 through CHOICE-10"),
    ("unknown_decision", "expected ten unique CHOICE-01 through CHOICE-10"),
    ("forged_approval", "approval is not a verified release record"),
    ("empty_approver", "CHOICE-01: missing approver"),
    ("empty_owner", "CHOICE-01: invalid owner criteria"),
    ("unknown_owner", "CHOICE-01: invalid owner criteria"),
    ("missing_confidential_scope", "confidential approval boundary missing"),
    ("local_permission_as_approval", "unknown local permission policy"),
    ("missing_real_model_scope", "CHOICE-05: real-model approval boundary missing"),
    ("missing_paid_load_scope", "CHOICE-06: paid/load approval boundary missing"),
    ("missing_procurement_scope", "CHOICE-05: procurement approval boundary missing"),
])
def test_decision_controls_reject_planted_authority(probe, expected):
    _, registry, contracts, _ = _fixture()
    catalog = contracts["decisions"]
    criteria = {ac["id"] for row in registry["items"]
                for ac in row.get("acceptance") or []}
    assert check_decisions(catalog, criteria) == []
    before = deepcopy(catalog)
    rows = catalog["choices"]
    first = next(row for row in rows if row["id"] == "CHOICE-01")
    if probe == "empty_decisions":
        rows.clear()
    elif probe == "missing_decision":
        rows.pop()
    elif probe == "duplicate_decision":
        rows.append(deepcopy(first))
    elif probe == "unknown_decision":
        first["id"] = "CHOICE-99"
    elif probe == "forged_approval":
        assert first["approval"] is None
        first["approval"] = {"state": "approved", "author": "self"}
    elif probe == "empty_approver":
        first["approver"] = " "
    elif probe == "empty_owner":
        first["owner_criteria"].clear()
    elif probe == "unknown_owner":
        first["owner_criteria"] = ["BK-999-AC1"]
    elif probe == "missing_confidential_scope":
        assert "confidential_pilot" in first["approval_required_for"]
        first["approval_required_for"].remove("confidential_pilot")
    elif probe == "local_permission_as_approval":
        first["local_synthetic"] = "approved_for_production"
    elif probe == "missing_real_model_scope":
        selected = next(row for row in rows if row["id"] == "CHOICE-05")
        assert "approved_real_model" in selected["approval_required_for"]
        selected["approval_required_for"].remove("approved_real_model")
    elif probe == "missing_procurement_scope":
        selected = next(row for row in rows if row["id"] == "CHOICE-05")
        assert "procurement" in selected["approval_required_for"]
        selected["approval_required_for"].remove("procurement")
    elif probe == "missing_paid_load_scope":
        selected = next(row for row in rows if row["id"] == "CHOICE-06")
        assert "paid_or_long_load" in selected["approval_required_for"]
        selected["approval_required_for"].remove("paid_or_long_load")
    else:
        pytest.fail(f"unimplemented probe {probe}")
    assert catalog != before, "a probe that mutates nothing proves nothing"
    errors = check_decisions(catalog, criteria)
    assert any(expected in error for error in errors), errors


@pytest.mark.parametrize("suffix", [".json", ".md"])
def test_new_nested_blueprint_contracts_change_fingerprint_on_add_edit_delete(tmp_path, suffix):
    """Discover the tree, not yesterday's handpicked contract file list."""
    directory = tmp_path / "docs" / "blueprint" / "new-family"
    directory.mkdir(parents=True)
    baseline = verification_fingerprint(tmp_path)
    contract = directory / ("new-contract" + suffix)
    assert not contract.exists()
    contract.write_text('{"scope": "synthetic"}\n', encoding="utf-8")
    added = verification_fingerprint(tmp_path)
    assert added != baseline
    contract.write_text('{"scope": "confidential"}\n', encoding="utf-8")
    edited = verification_fingerprint(tmp_path)
    assert edited not in {baseline, added}
    contract.unlink()
    assert not contract.exists()
    assert verification_fingerprint(tmp_path) == baseline


def test_generated_execution_verdict_is_not_its_own_fingerprint_authority(tmp_path):
    """Promoting a result cannot invalidate the source identity that earned it."""
    directory = tmp_path / "docs" / "backlog" / "evidence"
    directory.mkdir(parents=True)
    baseline = verification_fingerprint(tmp_path)
    verdict = directory / "class_a.json"
    verdict.write_text(json.dumps({"result": "FAIL"}), encoding="utf-8")
    assert verification_fingerprint(tmp_path) == baseline
    verdict.write_text(json.dumps({"result": "PASS"}), encoding="utf-8")
    assert verification_fingerprint(tmp_path) == baseline


def test_packet_cycle_probe_uses_existing_completed_item_and_real_final_owner():
    """Keep the mixed-graph counterexample meaningful as the plan evolves."""
    modules, registry, contracts, populations = _fixture()
    assert _packet_errors(modules, registry, contracts, populations) == []
    assert "BK-83" in _item(registry, "BK-88")["depends_on"]
    assert "BK-83-AC3" in _packet(contracts, "P38")["final_criteria"]
    assert "P12" in _packet(contracts, "P38")["prerequisites"]
    assert "BK-88" not in _packet(contracts, "P12")["requires_completed_items"]
