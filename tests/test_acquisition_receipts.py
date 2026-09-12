"""P44 quarantine receipts reconcile bytes, failures and interruptions."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from nm.knowledge.acquisition import (
    AcquiredArtifact,
    AcquisitionRefused,
    AcquisitionRoute,
    AcquisitionScope,
    JudgmentCandidate,
    ReconciliationState,
    quarantine_source_state,
    reconcile_acquisition,
    select_candidates,
    stage_acquisition,
)
from tools import reconcile_acquisition as reconcile_cli

NOW = datetime(2026, 9, 11, tzinfo=timezone.utc)


def _scope(selection_budget: int = 2) -> AcquisitionScope:
    return AcquisitionScope(
        route=AcquisitionRoute.API,
        source="api.indiankanoon.org",
        jurisdiction="telangana",
        document_types=("telangana",),
        from_date=date(2019, 1, 1),
        to_date=date(2026, 12, 31),
        discovery_budget=4,
        selection_budget=selection_budget,
        authorization_id="AUTH-SYNTHETIC-RECEIPT",
    )


def _candidate(candidate_id: str, citations: int = 0) -> JudgmentCandidate:
    return JudgmentCandidate(
        candidate_id=candidate_id,
        source="api.indiankanoon.org",
        jurisdiction="telangana",
        issuing_body="High Court for the State of Telangana",
        document_type="telangana",
        source_url=f"https://example.invalid/doc/{candidate_id}",
        source_date=date(2026, 8, 1),
        citation_count=citations,
    )


def _artifact(candidate: JudgmentCandidate, payload: bytes | None = None,
              error: str = "") -> AcquiredArtifact:
    return AcquiredArtifact(
        candidate_id=candidate.candidate_id,
        source_id=candidate.canonical_source_id,
        source_url=candidate.source_url,
        payload=payload,
        error=error,
    )


def _stage(tmp_path, *, run_id="run-1", candidates=None, artifacts=None,
           selection_budget=2, stop_after_writes=None):
    candidates = candidates or (_candidate("a", 1), _candidate("b", 0))
    scope = _scope(selection_budget)
    selection = select_candidates(scope, candidates)
    artifacts = artifacts or tuple(
        _artifact(candidate, f"document-{candidate.candidate_id}".encode())
        for candidate in candidates if candidate.candidate_id in selection.selected_ids
    )
    return stage_acquisition(
        tmp_path, run_id=run_id, scope=scope, selection=selection,
        artifacts=artifacts, observed_at=NOW,
        stop_after_writes=stop_after_writes,
    )


def test_complete_receipt_records_full_digests_and_reconciled_counts(tmp_path):
    run = _stage(tmp_path)
    report = reconcile_acquisition(run)
    receipt = json.loads((run / "receipt.json").read_text(encoding="utf8"))

    assert report.state is ReconciliationState.COMPLETE
    assert report.observed == 2
    assert report.accepted == report.staged == 2
    assert report.rejected == report.unresolved == report.failed == 0
    assert receipt["published"] is False
    assert receipt["source_state"] == quarantine_source_state()
    assert all(len(row["sha256"]) == 64 for row in receipt["artifacts"])
    assert all(
        {key: row[key] for key in quarantine_source_state()}
        == quarantine_source_state()
        for row in receipt["artifacts"]
    )
    assert all(len(row["source_id"].split("_", 1)[1]) == 64
               for row in receipt["artifacts"])


def test_run_id_and_existing_run_cannot_escape_or_overwrite(tmp_path):
    _stage(tmp_path, run_id="immutable")
    with pytest.raises(AcquisitionRefused, match="already exists"):
        _stage(tmp_path, run_id="immutable")
    with pytest.raises(ValueError, match="filesystem-safe"):
        _stage(tmp_path, run_id="../escape")
    assert not (tmp_path.parent / "escape").exists()


def test_stage_refuses_unsupported_selection_policy(tmp_path):
    candidate = _candidate("a")
    scope = _scope(selection_budget=1)
    selection = select_candidates(scope, (candidate,))
    forged = replace(selection, policy_version=selection.policy_version + 1)

    with pytest.raises(AcquisitionRefused, match="unsupported acquisition policy"):
        stage_acquisition(
            tmp_path, run_id="unsupported-policy", scope=scope,
            selection=forged,
            artifacts=(_artifact(candidate, b"document-a"),),
            observed_at=NOW,
        )


def test_interruption_leaves_a_detectable_partial_without_a_receipt(tmp_path):
    with pytest.raises(InterruptedError):
        _stage(tmp_path, run_id="interrupted", stop_after_writes=1)
    partial = tmp_path / "interrupted.partial"
    assert partial.is_dir()
    assert not (partial / "receipt.json").exists()
    report = reconcile_acquisition(partial)
    assert report.state is ReconciliationState.PARTIAL
    assert "partial" in report.reasons[0]


def test_failed_and_duplicate_responses_are_recorded_not_staged_twice(tmp_path):
    candidate = _candidate("a")
    failed = _artifact(candidate, None, "malformed response")
    run = _stage(
        tmp_path, run_id="failed", candidates=(candidate,),
        artifacts=(failed,), selection_budget=1,
    )
    assert reconcile_acquisition(run).failed == 1

    duplicate = _artifact(candidate, b"first")
    run = _stage(
        tmp_path, run_id="duplicate", candidates=(candidate,),
        artifacts=(duplicate, duplicate), selection_budget=1,
    )
    report = reconcile_acquisition(run)
    assert report.state is ReconciliationState.COMPLETE
    assert report.failed == 1 and report.staged == 0


@pytest.mark.parametrize("mutation, expected_reason", [
    ("changed_bytes", "artifact bytes changed"),
    ("missing_file", "missing or unaccounted"),
    ("extra_file", "missing or unaccounted"),
    ("path_escape", "escapes or is missing"),
    ("wrong_count", "staged count says"),
    ("published_true", "unpublished quarantine"),
    ("missing_source_state", "quarantine source state"),
    ("wrong_artifact_state", "invalid rights_state"),
    ("wrong_policy", "unsupported selection policy"),
    ("wrong_selection_policy", "unsupported selection policy"),
    ("wrong_selection_scope", "scope does not match"),
    ("wrong_selection_observed", "observed population does not match"),
])
def test_reconciliation_refuses_corruption_and_unaccounted_files(
        tmp_path, mutation, expected_reason):
    run = _stage(tmp_path, run_id=mutation)
    receipt_path = run / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf8"))
    artifact = receipt["artifacts"][0]
    source_file = run / artifact["file"]
    if mutation == "changed_bytes":
        source_file.write_bytes(b"changed")
    elif mutation == "missing_file":
        source_file.unlink()
    elif mutation == "extra_file":
        (run / "unaccounted.source").write_bytes(b"extra")
    elif mutation == "path_escape":
        outside = tmp_path / "outside.source"
        outside.write_bytes(b"outside")
        artifact["file"] = "../outside.source"
        artifact["bytes"] = len(b"outside")
        artifact["sha256"] = hashlib.sha256(b"outside").hexdigest()
        receipt_path.write_text(json.dumps(receipt), encoding="utf8")
    elif mutation == "wrong_count":
        receipt["counts"]["staged"] = 99
        receipt_path.write_text(json.dumps(receipt), encoding="utf8")
    elif mutation == "published_true":
        receipt["published"] = True
        receipt_path.write_text(json.dumps(receipt), encoding="utf8")
    elif mutation == "missing_source_state":
        receipt.pop("source_state")
        receipt_path.write_text(json.dumps(receipt), encoding="utf8")
    elif mutation == "wrong_artifact_state":
        artifact["rights_state"] = "permitted"
        receipt_path.write_text(json.dumps(receipt), encoding="utf8")
    elif mutation == "wrong_policy":
        receipt["selection_policy"]["version"] = 999
        receipt_path.write_text(json.dumps(receipt), encoding="utf8")
    elif mutation == "wrong_selection_policy":
        receipt["selection"]["policy_version"] = 999
        receipt_path.write_text(json.dumps(receipt), encoding="utf8")
    elif mutation == "wrong_selection_scope":
        receipt["selection"]["scope_id"] = "other-scope"
        receipt_path.write_text(json.dumps(receipt), encoding="utf8")
    elif mutation == "wrong_selection_observed":
        receipt["selection"]["observed"] = 99
        receipt_path.write_text(json.dumps(receipt), encoding="utf8")

    report = reconcile_acquisition(run)
    assert report.state is ReconciliationState.REFUSED or (
        mutation == "wrong_count" and report.state is ReconciliationState.PARTIAL
    )
    assert any(expected_reason in reason for reason in report.reasons)


def test_budget_exhaustion_is_reconciled_as_a_selection_decision(tmp_path):
    candidates = tuple(_candidate(f"case-{number}", number) for number in range(4))
    run = _stage(
        tmp_path, run_id="budget", candidates=candidates,
        selection_budget=2,
    )
    report = reconcile_acquisition(run)
    assert report.state is ReconciliationState.COMPLETE
    assert report.observed == 4
    assert report.accepted == 2
    assert report.rejected == 2


def test_reconciliation_command_reports_complete_and_non_complete(
        tmp_path, monkeypatch, capsys):
    run = _stage(tmp_path, run_id="cli")
    monkeypatch.setattr("sys.argv", ["reconcile_acquisition", str(run)])
    assert reconcile_cli.main() == 0
    assert "complete: 2 staged" in capsys.readouterr().out

    monkeypatch.setattr(
        "sys.argv",
        ["reconcile_acquisition", str(tmp_path / "missing"), "--json"],
    )
    assert reconcile_cli.main() == 2
    report = json.loads(capsys.readouterr().out)
    assert report["state"] == "not_assessed"
