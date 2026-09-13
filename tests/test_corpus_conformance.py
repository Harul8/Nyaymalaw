"""Exact-base corpus repair witnesses. All inputs are synthetic and local."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from nm.adapters.evidence.corpus import CorpusEvidenceAdapter
from nm.adapters.search.authority import AuthorityIndexSearch
from nm.knowledge import source_registry
from nm.knowledge.acquisition import ReconciliationState, reconcile_acquisition
from nm.knowledge.manifest import (
    CorpusDependency,
    CorpusPublicationRefused,
    get_corpus,
    record_corpus_dependency,
    rollback_corpus,
    withdraw_corpus,
)
from nm.ports.evidence import Coverage, EvidenceNeed
from tests.test_acquisition_receipts import _stage
from tests.test_immutable_corpus_publication import (
    NOW,
    _publish,
    _runtime_publication,
)
from tools import fetch_judgments, layercheck, scrape_judgments

pytestmark = pytest.mark.class_a


def _withdraw(snapshot):
    return withdraw_corpus(
        snapshot.root,
        snapshot_id=snapshot.snapshot_id,
        source_version_ids=snapshot.manifest["expected_versions"],
        reason="synthetic source no longer approved",
        observed_at=NOW + timedelta(minutes=1),
    )


def test_a_previously_open_source_refuses_new_reads_after_withdrawal(tmp_path):
    snapshot = _publish(tmp_path)
    version = snapshot.manifest["expected_versions"][0]
    assert snapshot.get_source(version) == b"law-v1"
    _withdraw(snapshot)
    with pytest.raises(CorpusPublicationRefused, match="withdrawn"):
        snapshot.get_source(version)


def test_both_live_adapters_refuse_a_generation_withdrawn_after_construction(tmp_path):
    snapshot = _runtime_publication(tmp_path)
    evidence = CorpusEvidenceAdapter.from_published_snapshot(snapshot)
    search = AuthorityIndexSearch.from_published_snapshot(snapshot)
    assert search.search("possession").coverage is Coverage.ANSWERED
    _withdraw(snapshot)
    result = search.search("possession")
    assert result.coverage is Coverage.NOT_ASSESSED and not result.hits
    assert "withdrawn" in result.why
    fetched = evidence.fetch(EvidenceNeed(
        question="possession", governing_date=NOW.date(), want_authority=True,
    ))
    assert fetched.coverage is not Coverage.ANSWERED
    assert "withdrawn" in fetched.missing
    assert not evidence.available


def test_withdrawal_during_search_cannot_escape_as_a_result(tmp_path, monkeypatch):
    snapshot = _runtime_publication(tmp_path)
    search = AuthorityIndexSearch.from_published_snapshot(snapshot)
    original = search._search

    def withdraw_after_read(*args, **kwargs):
        result = original(*args, **kwargs)
        assert result.coverage is Coverage.ANSWERED
        _withdraw(snapshot)
        return result

    monkeypatch.setattr(search, "_search", withdraw_after_read)
    result = search.search("possession")
    assert result.coverage is Coverage.NOT_ASSESSED
    assert not result.hits and "withdrawn" in result.why


def test_unavailable_withdrawal_register_is_not_a_clean_read(tmp_path, monkeypatch):
    snapshot = _publish(tmp_path)
    original = Path.iterdir

    def denied(path):
        if path == tmp_path / "withdrawals":
            raise PermissionError("synthetic denied withdrawal register")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", denied)
    with pytest.raises(CorpusPublicationRefused, match="unavailable"):
        snapshot.get_source(snapshot.manifest["expected_versions"][0])


def test_rollback_records_only_work_whose_source_versions_changed(tmp_path):
    old = _publish(tmp_path)
    new = _publish(tmp_path, b"law-v2", release="r2", identifier="SYN-2")
    for work_id, snapshot in (("old-unaffected", old), ("new-affected", new)):
        record_corpus_dependency(tmp_path, CorpusDependency(
            work_id, snapshot.snapshot_id,
            tuple(snapshot.manifest["expected_versions"]), NOW,
        ))
    restored = rollback_corpus(
        tmp_path, target_snapshot_id=old.snapshot_id,
        reason="synthetic regression", observed_at=NOW + timedelta(minutes=2),
    )
    event = json.loads((tmp_path / "transitions"
                        / f"{restored.pointer['transition_id']}.json").read_text())
    assert event["affected_work"] == ["new-affected"]
    assert event["reassessment_required"] is True
    assert old.get_source(old.manifest["expected_versions"][0]) == b"law-v1"


def test_rollback_does_not_stale_work_on_a_shared_unchanged_version(tmp_path):
    first = _publish(tmp_path)
    second = _publish(tmp_path, release="same-law")
    record_corpus_dependency(tmp_path, CorpusDependency(
        "unchanged-work", second.snapshot_id,
        tuple(second.manifest["expected_versions"]), NOW,
    ))
    restored = rollback_corpus(
        tmp_path, target_snapshot_id=first.snapshot_id,
        reason="synthetic index rollback", observed_at=NOW,
    )
    event = json.loads((tmp_path / "transitions"
                        / f"{restored.pointer['transition_id']}.json").read_text())
    assert event["affected_work"] == []


@pytest.mark.parametrize("operation", ["rollback", "withdrawal"])
@pytest.mark.parametrize("availability", ["missing", "unreadable"])
def test_unavailable_dependency_register_cannot_erase_affected_work(
    tmp_path, monkeypatch, operation, availability,
):
    old = _publish(tmp_path)
    new = _publish(tmp_path, b"law-v2", release="r2", identifier="SYN-2")
    record_corpus_dependency(tmp_path, CorpusDependency(
        "dependent-work", new.snapshot_id,
        tuple(new.manifest["expected_versions"]), NOW,
    ))
    directory = tmp_path / "dependencies"
    assert len(list(directory.iterdir())) == 1
    pointer_before = (tmp_path / "current.json").read_bytes()
    records_before = {
        name: set((tmp_path / name).iterdir())
        for name in ("transitions", "withdrawals")
    }
    if availability == "missing":
        directory.rename(tmp_path / "retained-dependencies")
    else:
        original = Path.iterdir

        def denied(path):
            if path == directory:
                raise PermissionError("synthetic denied dependency register")
            return original(path)

        monkeypatch.setattr(Path, "iterdir", denied)
    with pytest.raises(CorpusPublicationRefused,
                       match="dependency register is unavailable"):
        if operation == "rollback":
            rollback_corpus(
                tmp_path, target_snapshot_id=old.snapshot_id,
                reason="synthetic rollback", observed_at=NOW,
            )
        else:
            _withdraw(new)
    assert (tmp_path / "current.json").read_bytes() == pointer_before
    assert get_corpus(tmp_path).snapshot_id == new.snapshot_id
    for name, records in records_before.items():
        assert set((tmp_path / name).iterdir()) == records


def test_equal_counts_cannot_hide_a_receipt_candidate_substitution(tmp_path):
    run = _stage(tmp_path)
    receipt_path = run / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    assert receipt["artifacts"][0]["candidate_id"] == "a"
    receipt["artifacts"][0]["candidate_id"] = "unselected"
    receipt_path.write_text(json.dumps(receipt))
    report = reconcile_acquisition(run)
    assert report.state is ReconciliationState.REFUSED
    assert any("identit" in reason for reason in report.reasons)


@pytest.mark.parametrize("field,value", [("counts", []), ("selection", []),
                                       ("artifacts", {})])
def test_malformed_receipt_populations_return_refusal_not_an_exception(tmp_path, field, value):
    run = _stage(tmp_path)
    path = run / "receipt.json"
    receipt = json.loads(path.read_text())
    assert isinstance(receipt[field], (dict, list)) and receipt[field] != value
    receipt[field] = value
    path.write_text(json.dumps(receipt))
    assert reconcile_acquisition(run).state is ReconciliationState.REFUSED


def test_inventory_never_opens_a_file_reported_as_a_link(tmp_path, monkeypatch):
    alias = tmp_path / "source-alias.txt"
    alias.write_bytes(b"synthetic linked content")
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path:
                        path == alias or original(path))
    monkeypatch.setattr(source_registry, "_sha256", lambda _path:
                        pytest.fail("linked content was opened"))
    report = source_registry.inventory_sources(tmp_path, observed_at=NOW)
    assert report.status is source_registry.Assessment.PARTIAL
    assert report.assets[0].digest_state is source_registry.DigestState.EXCLUDED


def test_unreadable_directory_is_not_silently_omitted_from_complete_inventory(
    tmp_path, monkeypatch,
):
    (tmp_path / "known.txt").write_bytes(b"known")

    def denied_walk(root, *, onerror=None, **_kwargs):
        yield str(root), [], ["known.txt"]
        if onerror is not None:
            onerror(PermissionError("synthetic denied subtree"))

    monkeypatch.setattr(source_registry.os, "walk", denied_walk)
    report = source_registry.inventory_sources(tmp_path, observed_at=NOW)
    assert report.status is source_registry.Assessment.PARTIAL
    assert any("traversal" in value for value in report.reservations)


def test_unhashed_assets_do_not_confer_a_complete_inventory(tmp_path):
    (tmp_path / "bounded.txt").write_bytes(b"12345")
    report = source_registry.inventory_sources(
        tmp_path, observed_at=NOW, max_hash_bytes=4,
    )
    assert report.unhashed == 1
    assert report.status is source_registry.Assessment.PARTIAL


def test_consumer_inventory_does_not_open_private_or_linked_code(tmp_path, monkeypatch):
    private = tmp_path / "chat_history"
    private.mkdir()
    (private / "private.py").write_text("legal_database")
    alias = tmp_path / "alias.py"
    alias.write_text("legal_database")
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path:
                        path == alias or original(path))
    assert source_registry.find_consumers(tmp_path, ("legal_database",)) == ()


def test_api_plan_and_request_use_the_same_explicit_date_interval(tmp_path, monkeypatch):
    start, end = date(2026, 9, 1), date(2026, 9, 12)
    rows = fetch_judgments.plan([2026], "telangana", 1, from_date=start, to_date=end)
    assert rows[0]["fromdate"] == "01-09-2026"
    assert rows[0]["todate"] == "12-09-2026"
    seen = []

    def search(_query, _doctype, fromdate, todate, _page):
        seen.append((fromdate, todate))
        return {"docs": [{"tid": "1"}]}

    monkeypatch.setattr(fetch_judgments, "search", search)
    monkeypatch.setattr(fetch_judgments, "document", lambda _id: {
        "tid": "1", "publishdate": "2026-09-11", "court": "telangana",
        "citedbyList": [],
    })
    monkeypatch.setattr(fetch_judgments.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(fetch_judgments, "STAGING", tmp_path)
    assert fetch_judgments.run(
        2026, "telangana", 1, 1, 0, "", "AUTH-SYNTHETIC",
        from_date=start, to_date=end,
    ) == 1
    assert seen == [("01-09-2026", "12-09-2026")]


def test_web_selection_uses_explicit_dates_including_recent_uncited_law(tmp_path, monkeypatch):
    monkeypatch.setattr(scrape_judgments, "STAGING", tmp_path)
    monkeypatch.setattr(scrape_judgments, "robots_allows", lambda _path: (True, "synthetic"))
    monkeypatch.setattr(scrape_judgments, "_get", lambda url, _budget:
                        '<a href="/doc/1/">one</a>' if "/search/" in url else
                        '<title>Recent</title><span>published 2026-09-11</span>')
    assert scrape_judgments.run(
        [2026], 1, 999, 10, 1, "AUTH-SYNTHETIC",
        from_date=date(2026, 9, 1), to_date=date(2026, 9, 12),
    ) == 0
    [run] = list(tmp_path.iterdir())
    receipt = json.loads((run / "receipt.json").read_text())
    assert receipt["counts"]["accepted"] == 1


@pytest.mark.parametrize("layer,statement,expected", [
    ("domain", "from nm.infrastructure.cleanup import discard", 1),
    ("core", "from nm.infrastructure.cleanup import discard", 1),
    ("ports", "from nm.infrastructure.cleanup import discard", 1),
    ("infrastructure", "import requests", 1),
    ("infrastructure", "import nm.core.turn", 1),
    ("adapters", "from nm.infrastructure.cleanup import discard", 0),
    ("knowledge", "from nm.infrastructure.cleanup import discard", 0),
    ("infrastructure", "import pathlib", 0),
])
def test_restricted_infrastructure_is_reachable_only_from_concrete_io_layers(
    tmp_path, monkeypatch, layer, statement, expected,
):
    source = tmp_path / "nm"
    destination = source / layer / "probe.py"
    destination.parent.mkdir(parents=True)
    destination.write_text(statement)
    monkeypatch.setattr(layercheck, "ROOT", tmp_path)
    monkeypatch.setattr(layercheck, "SRC", source)
    assert layercheck.main() == expected


def test_cleanup_failure_does_not_replace_the_publication_outcome(tmp_path, monkeypatch):
    from nm.domain.names import discard, discard_tree

    def refused(*_args, **_kwargs):
        raise PermissionError("synthetic held-open file")

    monkeypatch.setattr(Path, "unlink", refused)
    monkeypatch.setattr("nm.domain.names.shutil.rmtree", refused)
    assert discard(tmp_path / "file") is False
    assert discard_tree(tmp_path / "tree") is False


@pytest.mark.parametrize("root_state,expected", [
    ("present", False), ("absent", True), ("unreadable", False),
])
def test_tree_cleanup_checks_root_after_a_nested_file_disappears(
    tmp_path, monkeypatch, root_state, expected,
):
    from nm.domain.names import discard_tree

    root = tmp_path / "temporary-tree"
    if root_state != "absent":
        root.mkdir()

    def nested_missing(_path):
        raise FileNotFoundError("synthetic concurrently removed child")

    monkeypatch.setattr("nm.domain.names.shutil.rmtree", nested_missing)
    if root_state == "unreadable":
        original = Path.lstat

        def denied(path):
            if path == root:
                raise PermissionError("synthetic unavailable root status")
            return original(path)

        monkeypatch.setattr(Path, "lstat", denied)
    assert discard_tree(root) is expected
