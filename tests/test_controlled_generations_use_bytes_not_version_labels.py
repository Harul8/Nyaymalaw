"""Real byte and publication drift, including a same-stat counterexample."""
import os
from pathlib import Path

import pytest

from nm.legal_brain.controlled_generations import GenerationGuard, GenerationUnavailable
from nm.legal_brain.manifest_sources import PublishedCorpus, withdraw_corpus
from tests.test_immutable_corpus_publication import NOW, _publish

pytestmark = pytest.mark.class_a


def practice(tmp_path):
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "rule.py").write_text("RULE = 'recorded'", encoding="utf8")
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("coverage: recorded", encoding="utf8")
    return root, manifest


@pytest.mark.parametrize("change", ["same_stat", "new_owner", "deleted", "manifest", "empty"])
def test_bound_population_refuses_changed_removed_or_added_bytes(tmp_path, change):
    root, manifest = practice(tmp_path)
    guard = GenerationGuard(knowledge_root=root, manifest_path=manifest)
    guard.require_current()
    assert guard.binding["corpus"]["state"] == "legacy_unsealed_freshness_not_established"
    path = root / "rule.py"
    if change == "same_stat":
        stat = path.stat()
        path.write_text("RULE = 'alteredd'", encoding="utf8")
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        assert path.stat().st_size == stat.st_size
    elif change == "new_owner":
        (root / "later.py").write_text("NEW = 'table'", encoding="utf8")
    elif change in {"deleted", "empty"}:
        path.unlink()
    else:
        manifest.write_text("coverage: changed!", encoding="utf8")
    with pytest.raises(GenerationUnavailable):
        guard.require_current()


def test_actual_published_generation_and_its_withdrawal_are_read_by_the_existing_owner(tmp_path):
    root, manifest = practice(tmp_path)
    corpus_root = tmp_path / "published"
    published = _publish(corpus_root)
    snapshot = PublishedCorpus.open(corpus_root)
    assert snapshot.snapshot_id == published.snapshot_id
    guard = GenerationGuard(knowledge_root=root, manifest_path=manifest, snapshot=snapshot)
    guard.require_current()
    assert guard.binding["corpus"]["state"] == "bound_immutable_publication"
    withdraw_corpus(corpus_root, snapshot_id=snapshot.snapshot_id,
        source_version_ids=snapshot.manifest["expected_versions"],
        reason="Controlled withdrawal", observed_at=NOW)
    with pytest.raises(GenerationUnavailable):
        guard.require_current()


def test_inaccessible_knowledge_root_cannot_mean_unchanged(tmp_path):
    with pytest.raises(GenerationUnavailable):
        GenerationGuard(knowledge_root=Path(tmp_path / "absent"))
