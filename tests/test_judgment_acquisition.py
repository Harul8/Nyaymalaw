"""P44 selection is scope-first, explainable and citation-age safe."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from nm.knowledge.acquisition import (
    POLICY_ID,
    POLICY_VERSION,
    AcquiredArtifact,
    AcquisitionRoute,
    AcquisitionScope,
    JudgmentCandidate,
    ReconciliationState,
    SelectionState,
    reconcile_acquisition,
    select_candidates,
    stage_acquisition,
)
from nm.knowledge.source_registry import RightsState
from tools import fetch_judgments, scrape_judgments
from tools import reconcile_acquisition as reconcile_cli


def _scope(**overrides) -> AcquisitionScope:
    values = {
        "route": AcquisitionRoute.API,
        "source": "api.indiankanoon.org",
        "jurisdiction": "telangana",
        "document_types": ("telangana",),
        "from_date": date(2019, 1, 1),
        "to_date": date(2026, 12, 31),
        "discovery_budget": 10,
        "selection_budget": 2,
        "authorization_id": "AUTH-SYNTHETIC-1",
        "issuing_bodies": ("High Court for the State of Telangana",),
        "source_rights": RightsState.PERMITTED,
    }
    values.update(overrides)
    return AcquisitionScope(**values)


def _candidate(candidate_id: str, year: int | None, citations: int | None,
               **overrides) -> JudgmentCandidate:
    values = {
        "candidate_id": candidate_id,
        "source": "api.indiankanoon.org",
        "jurisdiction": "telangana",
        "issuing_body": "High Court for the State of Telangana",
        "document_type": "telangana",
        "source_url": f"https://example.invalid/doc/{candidate_id}",
        "source_date": date(year, 6, 1) if year is not None else None,
        "citation_count": citations,
    }
    values.update(overrides)
    return JudgmentCandidate(**values)


def _by_id(report):
    return {row.candidate_id: row for row in report.decisions}


def test_recent_zero_citation_case_is_not_hidden_by_an_older_popular_case():
    report = select_candidates(_scope(selection_budget=1), (
        _candidate("old-popular", 2020, 1000),
        _candidate("recent-zero", 2026, 0),
    ))

    rows = _by_id(report)
    assert rows["recent-zero"].state is SelectionState.SELECTED
    assert rows["old-popular"].state is SelectionState.REJECTED
    assert "selection budget" in rows["old-popular"].reasons[0]
    assert report.policy_id == POLICY_ID
    assert report.policy_version == POLICY_VERSION


def test_citation_priority_applies_only_inside_the_same_year_cohort():
    report = select_candidates(_scope(selection_budget=2), (
        _candidate("recent-zero", 2026, 0),
        _candidate("recent-ten", 2026, 10),
        _candidate("old-thousand", 2025, 1000),
    ))

    assert report.selected_ids == ("recent-ten", "recent-zero")
    assert _by_id(report)["old-thousand"].state is SelectionState.REJECTED


def test_missing_citation_metadata_is_unknown_not_zero_or_ineligible():
    report = select_candidates(_scope(selection_budget=1), (
        _candidate("recent-unknown", 2026, None),
    ))
    row = report.decisions[0]
    assert row.state is SelectionState.SELECTED
    assert any("unavailable" in reason for reason in row.reasons)
    assert all("citation count 0" not in reason for reason in row.reasons)


def test_exact_scope_rejects_popular_but_ineligible_material():
    report = select_candidates(_scope(), (
        _candidate("wrong-source", 2026, 500, source="other.example"),
        _candidate("wrong-court", 2026, 500, jurisdiction="kerala"),
        _candidate("wrong-type", 2026, 500, document_type="supremecourt"),
        _candidate("too-old", 2018, 500),
    ))
    assert report.count(SelectionState.REJECTED) == 4
    assert report.selected_ids == ()
    assert all(row.reasons for row in report.decisions)


def test_missing_date_unreadable_and_duplicate_candidates_remain_visible():
    first = _candidate("first", 2026, 0)
    report = select_candidates(_scope(), (
        _candidate("missing-date", None, 0),
        _candidate("unreadable", 2026, 0, readable=False),
        first,
        replace(first, candidate_id="different-id"),
    ))
    rows = _by_id(report)
    assert rows["missing-date"].state is SelectionState.UNRESOLVED
    assert rows["unreadable"].state is SelectionState.UNRESOLVED
    assert rows["different-id"].state is SelectionState.REJECTED
    assert "duplicate" in rows["different-id"].reasons[0]


def test_discovery_and_selection_budgets_reconcile_the_whole_population():
    report = select_candidates(
        _scope(discovery_budget=2, selection_budget=1),
        tuple(_candidate(f"case-{number}", 2026, number) for number in range(4)),
    )
    assert report.observed == 4
    assert report.count(SelectionState.SELECTED) == 1
    assert report.count(SelectionState.REJECTED) == 3
    assert report.count(SelectionState.UNRESOLVED) == 0


def test_authorization_is_part_of_scope_identity():
    first = _scope(authorization_id="AUTH-ONE")
    second = _scope(authorization_id="AUTH-TWO")
    assert first.scope_id != second.scope_id


def test_api_entrypoint_uses_shared_selection_and_quarantine(
        tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_judgments, "STAGING", tmp_path)
    monkeypatch.setattr(fetch_judgments, "time", type(
        "Clock", (), {"sleep": staticmethod(lambda _delay: None)},
    ))

    def fake_search(_query, _doctype, _fromdate, _todate, pagenum):
        if pagenum == 0:
            return {"docs": [{"tid": "100"}, {"tid": "101"}]}
        return {"docs": []}

    def fake_document(docid):
        return {
            "tid": str(docid),
            "court": "High Court for the State of Telangana",
            "publishdate": "2026-08-01",
            "citedbyList": [] if docid == 100 else [{"tid": "x"}],
        }

    monkeypatch.setattr(fetch_judgments, "search", fake_search)
    monkeypatch.setattr(fetch_judgments, "document", fake_document)

    selected = fetch_judgments.run(
        2026, fetch_judgments.TELANGANA, want=2, cap=2, delay=0,
        query="", authorization_id="AUTH-API-SYNTHETIC",
        # THE BENCH AND THE REVIEWED RIGHT ARE PART OF THE AUTHORISATION.
        # A doctype is a jurisdiction, and an authorisation id is a reference
        # to a decision rather than the decision itself.
        issuing_bodies=("High Court for the State of Telangana",),
        source_rights=RightsState.PERMITTED,
    )

    [run] = [path for path in tmp_path.iterdir() if path.is_dir()]
    receipt = json.loads((run / "receipt.json").read_text(encoding="utf8"))
    assert selected == 2
    assert receipt["route"] == "api"
    assert receipt["authorization_id"] == "AUTH-API-SYNTHETIC"
    assert receipt["published"] is False
    assert receipt["source_state"] == {
        "rights_state": "unknown",
        "review_state": "unreviewed",
        "publication_state": "candidate",
    }


def test_web_entrypoint_records_legacy_citation_input_without_filtering(
        tmp_path, monkeypatch):
    monkeypatch.setattr(scrape_judgments, "STAGING", tmp_path)
    monkeypatch.setattr(
        scrape_judgments, "robots_allows", lambda _path: (True, "allowed"),
    )

    def fake_get(url, budget):
        if budget["spent"] >= budget["cap"]:
            raise scrape_judgments.Refused("cap reached")
        budget["spent"] += 1
        if "/search/" in url:
            return '<a href="/doc/200/">A</a>'
        return (
            "<title>Recent Zero</title>"
            "<span>published 2026-06-01</span>"
            '<a href="citedby:200">0</a>'
        )

    monkeypatch.setattr(scrape_judgments, "_get", fake_get)

    assert scrape_judgments.run(
        [2026], pages=1, legacy_min_cited=999, cap=10,
        selection_budget=1, authorization_id="AUTH-WEB-SYNTHETIC",
        source_rights=RightsState.PERMITTED,
    ) == 0

    [run] = [path for path in tmp_path.iterdir() if path.is_dir()]
    receipt = json.loads((run / "receipt.json").read_text(encoding="utf8"))
    assert receipt["route"] == "web"
    assert receipt["counts"]["accepted"] == 1
    assert receipt["selection"]["decisions"][0]["candidate_id"] == "200"
    assert receipt["selection"]["decisions"][0]["state"] == "selected"


def test_web_entrypoint_refuses_request_budget_exhaustion_without_receipt(
        tmp_path, monkeypatch):
    monkeypatch.setattr(scrape_judgments, "STAGING", tmp_path)
    monkeypatch.setattr(
        scrape_judgments, "robots_allows", lambda _path: (True, "allowed"),
    )

    def fake_get(url, budget):
        if budget["spent"] >= budget["cap"]:
            raise scrape_judgments.Refused("cap reached")
        budget["spent"] += 1
        assert "/search/" in url
        return '<a href="/doc/300/">A</a>'

    monkeypatch.setattr(scrape_judgments, "_get", fake_get)

    assert scrape_judgments.run(
        [2026], pages=1, legacy_min_cited=0, cap=1,
        selection_budget=1, authorization_id="AUTH-WEB-CAPPED",
        source_rights=RightsState.PERMITTED,
    ) == 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.class_a
def test_p44_integration_witness_covers_both_entrypoints_and_reconcile_command(
        tmp_path, monkeypatch, capsys):
    test_api_entrypoint_uses_shared_selection_and_quarantine(
        tmp_path / "api", monkeypatch,
    )
    test_web_entrypoint_records_legacy_citation_input_without_filtering(
        tmp_path / "web", monkeypatch,
    )

    candidate = _candidate("cli-candidate", 2026, 0)
    scope = _scope(selection_budget=1)
    selection = select_candidates(scope, (candidate,))
    run = stage_acquisition(
        tmp_path / "reconcile",
        run_id="cli-witness",
        scope=scope,
        selection=selection,
        artifacts=(AcquiredArtifact(
            candidate.candidate_id,
            candidate.canonical_source_id,
            candidate.source_url,
            b"cli witness",
        ),),
        observed_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
    )
    monkeypatch.setattr("sys.argv", ["reconcile_acquisition", str(run)])
    assert reconcile_cli.main() == 0
    assert "complete: 1 staged" in capsys.readouterr().out


@pytest.mark.class_a
def test_p44_adversarial_witness_covers_bias_scope_and_receipt_guards(tmp_path):
    bias = select_candidates(_scope(selection_budget=1), (
        _candidate("old-popular", 2020, 1000),
        _candidate("recent-zero", 2026, 0),
    ))
    scope = select_candidates(_scope(), (
        _candidate("popular-but-wrong-source", 2026, 999, source="outside"),
    ))
    assert _by_id(bias)["recent-zero"].state is SelectionState.SELECTED
    assert _by_id(scope)["popular-but-wrong-source"].state is SelectionState.REJECTED

    candidate = _candidate("tamper", 2026, 1)
    acquisition_scope = _scope(selection_budget=1)
    selection = select_candidates(acquisition_scope, (candidate,))
    run = stage_acquisition(
        tmp_path,
        run_id="tamper",
        scope=acquisition_scope,
        selection=selection,
        artifacts=(AcquiredArtifact(
            candidate.candidate_id,
            candidate.canonical_source_id,
            candidate.source_url,
            b"tamper witness",
        ),),
        observed_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
    )
    receipt_path = run / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf8"))
    receipt["source_state"]["rights_state"] = "permitted"
    receipt_path.write_text(json.dumps(receipt), encoding="utf8")

    report = reconcile_acquisition(run)
    assert report.state is ReconciliationState.REFUSED
    assert any("quarantine source state" in reason for reason in report.reasons)
