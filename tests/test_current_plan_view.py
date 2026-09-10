"""The saved workbook is a derived reader view, not a status authority."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib

import pytest

from tools import plan_view

pytestmark = pytest.mark.class_a


@pytest.fixture(scope="module")
def saved_tables():
    assert plan_view.WORKBOOK.is_file(), "the canonical saved reader view is required"
    before = hashlib.sha256(plan_view.WORKBOOK.read_bytes()).hexdigest()
    tables = plan_view.load_view()
    assert hashlib.sha256(plan_view.WORKBOOK.read_bytes()).hexdigest() == before
    return tables


def _row(tables, sheet, column, value):
    return next(row for row in tables[sheet] if row[column] == value)


def test_saved_current_plan_matches_authored_registry_and_snapshot_sources(saved_tables):
    assert len(plan_view.SHEETS) == 28
    assert len(saved_tables["Work Items"]) >= 97
    assert len(saved_tables["Features"]) == 44
    assert len(saved_tables["Journey Steps"]) == 47
    assert len(saved_tables["Acceptance"]) >= 179
    assert len(saved_tables["Execution Packets"]) >= 45
    assert len(saved_tables["Command Contracts"]) >= 50
    assert len(saved_tables["Reconciliation"]) == 20
    assert plan_view.check_view(saved_tables) == []


def test_saved_media_policy_is_part_of_the_checked_reader_view(saved_tables):
    assert plan_view.check_view(saved_tables) == []
    tables = deepcopy(saved_tables)
    shared = [row for row in tables["Evaluation Details"] if row["Aspect"] == "Media policy"]
    assert shared and any(row["Field / order"] == "prohibited_operations" for row in shared)
    target = next(row for row in shared if row["Field / order"] == "prohibited_operations")
    before = target["Specification"]
    target["Specification"] = "Uncontrolled additional processing"
    assert before != target["Specification"]
    assert any("Evaluation Details" in problem for problem in plan_view.check_view(tables))


def test_saved_autonomy_contract_is_checked_without_promoting_runtime(saved_tables):
    assert plan_view.check_view(saved_tables) == []
    tables = deepcopy(saved_tables)
    rows = [r for r in tables["Evaluation Details"] if r["Scenario"] == "Autonomy contract"]
    assert len(rows) > 50
    execution = next(r for r in rows if r["Aspect"] == "execution_status")
    assert execution["Specification"] == "NOT_RUN"
    target = next(r for r in rows if r["Field / order"] == "canonical_writes")
    before = target["Specification"]
    target["Specification"] = "Agents write without acceptance"
    assert target["Specification"] != before
    assert any("Evaluation Details" in p for p in plan_view.check_view(tables))


@pytest.mark.parametrize("probe,expected", [
    ("drop_original_item", "Work Items: exact ID population/order differs; missing=['BK-21']"),
    ("duplicate_item", "Work Items: exact ID population/order differs"),
    ("change_status", "Work Items/BK-31: Delivery status differs from source"),
    ("change_wave", "Work Items/BK-21: Wave differs from source"),
    ("change_feature", "Features/A1: Implementation differs from source"),
    ("change_step_basis", "Journey Steps/STEP-A-01: Basis differs from source"),
    ("change_hash", "Sources: stale or incorrect hash docs/backlog/status.yaml"),
    ("drop_source", "Sources: exact authored snapshot-source population differs"),
    ("drop_acceptance", "Acceptance: exact ID population/order differs"),
    ("change_instruction", "Packet Guide: instruction population or content differs"),
    ("forge_scenario_pass", "Evaluation Specs/EVAL-001: Execution differs from source"),
    ("forge_decision", "Decisions/CHOICE-01: Current approval differs from source"),
    ("formula_error", "Reconciliation: saved formula error #REF!"),
    ("missing_formula", "Reconciliation!C4: formula or cached value differs"),
    ("wrong_formula_cache", "Reconciliation!C4: formula or cached value differs"),
    ("forged_zero_reconciliation", "Reconciliation/Items: Source count differs from source"),
    ("drop_control_row", "Reconciliation: exact control-row population differs"),
    ("promote_captured_artifact", "Sources: captured execution artifact must remain historical"),
])
def test_saved_plan_checker_rejects_real_cell_mutations(saved_tables, probe, expected):
    assert plan_view.check_view(saved_tables) == []
    tables = deepcopy(saved_tables)
    before = deepcopy(tables)
    if probe == "drop_original_item":
        original = _row(tables, "Work Items", "ID", "BK-21")
        tables["Work Items"].remove(original)
    elif probe == "duplicate_item":
        tables["Work Items"].append(deepcopy(tables["Work Items"][0]))
    elif probe == "change_status":
        row = _row(tables, "Work Items", "ID", "BK-31")
        assert row["Delivery status"] != "self-certified done"
        row["Delivery status"] = "self-certified done"
    elif probe == "change_wave":
        row = _row(tables, "Work Items", "ID", "BK-21")
        assert row["Wave"] != "W9"
        row["Wave"] = "W9"
    elif probe == "change_feature":
        _row(tables, "Features", "Feature", "A1")["Implementation"] = "self-certified"
    elif probe == "change_step_basis":
        _row(tables, "Journey Steps", "Step ID", "STEP-A-01")["Basis"] = "fabricated basis"
    elif probe == "change_hash":
        row = _row(tables, "Sources", "Source", "docs/backlog/status.yaml")
        assert row["Fingerprint / URL"] != "0" * 64
        row["Fingerprint / URL"] = "0" * 64
    elif probe == "drop_source":
        tables["Sources"].remove(_row(tables, "Sources", "Source", "docs/backlog/status.yaml"))
    elif probe == "drop_acceptance":
        row = _row(tables, "Acceptance", "Criterion", "BK-21-AC1")
        tables["Acceptance"].remove(row)
    elif probe == "change_instruction":
        tables["Packet Guide"][0]["Instruction"] = "Skip the registered proof and approve yourself."
    elif probe == "forge_scenario_pass":
        _row(tables, "Evaluation Specs", "Scenario", "EVAL-001")["Execution"] = "PASS"
    elif probe == "forge_decision":
        _row(tables, "Decisions", "Choice", "CHOICE-01")["Current approval"] = "Approved"
    elif probe == "formula_error":
        _row(tables, "Reconciliation", "Population", "Items")["Difference"] = "#REF!"
    elif probe == "missing_formula":
        row = next(r for r in tables["__formulas__"]
                   if r["sheet"] == "Reconciliation" and r["cell"] == "C4")
        tables["__formulas__"].remove(row)
    elif probe == "wrong_formula_cache":
        row = next(r for r in tables["__formulas__"]
                   if r["sheet"] == "Reconciliation" and r["cell"] == "C4")
        row["cached"] += 1
    elif probe == "forged_zero_reconciliation":
        row = _row(tables, "Reconciliation", "Population", "Items")
        assert row["Difference"] == 0
        row["Source count"] += 1
    elif probe == "drop_control_row":
        row = _row(tables, "Reconciliation", "Population", "Modules")
        tables["Reconciliation"].remove(row)
    elif probe == "promote_captured_artifact":
        row = _row(tables, "Sources", "Source", plan_view.CAPTURED_ARTIFACT)
        assert row["Role"] == "Captured execution artifact"
        row["Role"] = "Snapshot source"
    else:
        pytest.fail(f"unimplemented probe {probe}")
    assert tables != before, "a probe that mutates nothing proves nothing"
    errors = plan_view.check_view(tables)
    assert any(expected in error for error in errors), errors


def test_snapshot_text_hash_normalises_line_endings_but_binary_hash_does_not(tmp_path):
    text = tmp_path / "contract.md"
    text.write_bytes(b"one\r\ntwo\r\n")
    crlf = plan_view.source_hash(text)
    text.write_bytes(b"one\ntwo\n")
    assert plan_view.source_hash(text) == crlf
    binary = tmp_path / "document.docx"
    binary.write_bytes(b"one\r\ntwo\r\n")
    original = plan_view.source_hash(binary)
    binary.write_bytes(b"one\ntwo\n")
    assert plan_view.source_hash(binary) != original


def test_readable_excel_date_can_match_iso_but_an_unformatted_serial_cannot():
    expected = "2026-10-10T00:00:00Z"
    assert plan_view._same_value(datetime(2026, 10, 10), expected)
    assert not plan_view._same_value(46305, expected)
    assert not plan_view._same_value(datetime(2026, 10, 11), expected)
