from __future__ import annotations

from datetime import datetime, timezone

import pytest

from nm.knowledge.source_registry import (
    Assessment,
    AssetKind,
    DigestState,
    inventory_sources,
)
from tools.inventory_legal_sources import main

NOW = datetime(2026, 9, 11, tzinfo=timezone.utc)


def sample_tree(tmp_path):
    root = tmp_path / "corpus"
    (root / "raw_data" / "CaseLaws").mkdir(parents=True)
    (root / "raw_data" / "CaseLaws" / "one.txt").write_text("same", encoding="utf8")
    (root / "raw_data" / "CaseLaws" / "copy.txt").write_text("same", encoding="utf8")
    (root / "vector_store").mkdir()
    (root / "vector_store" / "chunks.db").write_bytes(b"derived")
    (root / "misc").mkdir()
    (root / "misc" / "mystery.bin").write_bytes(b"unknown")
    (root / "backups").mkdir()
    (root / "backups" / "old.bak").write_bytes(b"backup")
    (root / "chat_history").mkdir()
    (root / "chat_history" / "private.txt").write_text("do not open", encoding="utf8")
    return root


def test_inventory_distinguishes_roles_duplicates_private_content_and_consumers(tmp_path):
    root = sample_tree(tmp_path)
    code = tmp_path / "code"
    code.mkdir()
    (code / "reader.py").write_text('PATH = "legal_database/vector_store/chunks.db"\n')

    report = inventory_sources(
        root, observed_at=NOW, max_hash_bytes=100,
        consumer_root=code, consumer_terms=("legal_database", "chunks.db"),
    )

    assert report.status is Assessment.COMPLETE
    by_path = {row.path: row for row in report.assets}
    assert by_path["raw_data/CaseLaws/one.txt"].kind is AssetKind.RENDITION
    assert by_path["vector_store/chunks.db"].kind is AssetKind.PROJECTION
    assert by_path["backups/old.bak"].kind is AssetKind.BACKUP
    assert by_path["misc/mystery.bin"].kind is AssetKind.UNKNOWN
    duplicate_rows = [row for row in report.assets if row.duplicate_of]
    assert len(duplicate_rows) == 1
    assert {duplicate_rows[0].path, duplicate_rows[0].duplicate_of} == {
        "raw_data/CaseLaws/copy.txt", "raw_data/CaseLaws/one.txt"
    }
    private = [row for row in report.assets if row.kind is AssetKind.PRIVATE]
    assert private and all(row.digest_state is DigestState.EXCLUDED for row in private)
    assert all("private.txt" not in row.path for row in report.assets)
    assert {(row.path, row.reference) for row in report.consumers} == {
        ("reader.py", "legal_database"), ("reader.py", "chunks.db")
    }


def test_missing_empty_bounded_and_cancelled_populations_never_look_complete(tmp_path):
    missing = inventory_sources(tmp_path / "missing", observed_at=NOW)
    assert missing.status is Assessment.NOT_ASSESSED
    assert missing.reservations

    empty = tmp_path / "empty"
    empty.mkdir()
    assert inventory_sources(empty, observed_at=NOW).status is Assessment.NOT_ASSESSED

    root = sample_tree(tmp_path)
    bounded = inventory_sources(root, observed_at=NOW, max_entries=2)
    assert bounded.status is Assessment.PARTIAL
    assert "entry limit" in " ".join(bounded.reservations)

    cancelled = inventory_sources(
        root, observed_at=NOW, cancel_after=2,
    )
    assert cancelled.status is Assessment.PARTIAL
    assert "cancelled" in " ".join(cancelled.reservations)


def test_large_and_failed_reads_are_visible_not_absence(tmp_path, monkeypatch):
    root = tmp_path / "corpus"
    root.mkdir()
    large = root / "large.bin"
    large.write_bytes(b"12345")
    report = inventory_sources(root, observed_at=NOW, max_hash_bytes=4)
    assert report.unhashed == 1
    assert report.assets[0].digest_state is DigestState.NOT_ASSESSED

    original = __import__("nm.knowledge.source_registry", fromlist=["_sha256"])
    monkeypatch.setattr(original, "_sha256", lambda _path: (_ for _ in ()).throw(PermissionError()))
    failed = inventory_sources(root, observed_at=NOW, max_hash_bytes=10)
    assert failed.status is Assessment.PARTIAL
    assert failed.unreadable == 1
    assert failed.assets[0].digest_state is DigestState.UNREADABLE


def test_cli_refuses_to_write_its_report_inside_the_source(tmp_path, monkeypatch):
    root = sample_tree(tmp_path)
    monkeypatch.setattr("sys.argv", [
        "inventory", "--source-root", str(root),
        "--output", str(root / "report.json"),
    ])
    with pytest.raises(SystemExit) as refused:
        main()
    assert refused.value.code == 2
    assert not (root / "report.json").exists()
