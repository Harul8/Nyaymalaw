"""The real Application installs candidates and trust separately; neither is approval."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nm.app.composition import Application
from nm.arrive.store_directory import FileDirectory
from nm.Archives.legal_brain.retrieve.provision_registry_composition import REGISTRY_MEMBER, RegistryLoadState
from nm.Archives.legal_brain.retrieve.provision_revision_sources import (
    AuthorityRole,
    AuthoritySpan,
    ProvisionRevision,
    RevisionKind,
    SelectionState,
    TransitionState,
    _wire,
)
from nm.shared.store_file_store import FileMatterStore
from tests.test_immutable_corpus_publication import (
    KEY,
    NOW,
    _artefact,
    _publish,
    _registered,
    _runtime_publication,
    _scripted_model,
    _sqlite_payload,
)

pytestmark = pytest.mark.class_a


def _candidate_publication(tmp_path, *, malformed=False):
    payload = b"Synthetic wording. Enactment. Commencement."
    registry, version = _registered(payload)
    span = AuthoritySpan(version.version_id, "synthetic wording", 0, 18, AuthorityRole.WORDING)
    revision = ProvisionRevision(version.source.source_id, "1", span, RevisionKind.ORIGINAL,
        NOW.date(), None, NOW.date(), (
            AuthoritySpan(version.version_id, "synthetic enactment", 19, 29,
                          AuthorityRole.ENACTMENT),
            AuthoritySpan(version.version_id, "synthetic start", 30, len(payload),
                          AuthorityRole.COMMENCEMENT)), (), TransitionState.NOT_APPLICABLE, ())
    candidate = {"schema": 1, "sources": [_wire(version.source)],
                 "versions": [_wire(version)], "aliases": [
                     {"reference": version.source.display_name,
                      "source_id": version.source.source_id}],
                 "revisions": [revision.as_record()],
                 "review_artifacts": ["docs/backlog/evidence/synthetic-not-issued.json"]}
    if malformed:
        candidate["unexpected_approval"] = True
    members = (
        ("corpus/chunks.db", _sqlite_payload(tmp_path / "chunks.fixture", authority=False)),
        ("indexes/authority.db", _sqlite_payload(tmp_path / "authority.fixture", authority=True)),
        ("corpus/manifest.yaml", b"corpus_version: r1\nacts: []\n"),
        (REGISTRY_MEMBER, json.dumps(candidate, sort_keys=True).encode()))
    published = _publish(tmp_path / "published", payload=payload, registry=registry,
        version=version, artefacts=tuple(_artefact(path, value, version.version_id)
                                       for path, value in members))
    return published, version, revision, payload


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("NM_CORPUS_DIR", str(tmp_path / "published"))
    monkeypatch.setenv("NM_MATTER_KEY", KEY)
    for name in ("NM_AUTHORITY_INDEX", "NM_IDENTITY_INDEX", "NM_EVIDENCE_TRUST"):
        monkeypatch.delenv(name, raising=False)
    return Application(root=Path(__file__).resolve().parents[1],
        store=FileMatterStore(tmp_path / "matters", key=KEY),
        directory=FileDirectory(tmp_path / "matters", key=KEY), model=_scripted_model())


def test_application_missing_registry_is_not_established_not_a_legal_pass(
        tmp_path, monkeypatch, scripted_application_environment):
    published = _runtime_publication(tmp_path)
    app = _app(tmp_path, monkeypatch)
    assert app.provision_registry.state is RegistryLoadState.NOT_ESTABLISHED
    assert app.evidence._source_registry is None
    assert app.evidence.published_snapshot_id == published.snapshot_id


def test_application_installs_actual_published_registry_but_no_unsigned_qualified_approval(
        tmp_path, monkeypatch, scripted_application_environment):
    published, version, revision, payload = _candidate_publication(tmp_path)
    app = _app(tmp_path, monkeypatch)
    assert app.provision_registry.state is RegistryLoadState.LOADED
    assert app.evidence._source_registry is app.provision_registry.registry
    assert app.evidence._revision_source_bytes.__self__ is app.evidence._published_snapshot
    assert app.evidence._published_snapshot is app.search._published_snapshot
    assert app.evidence.published_snapshot_id == published.snapshot_id
    assert app.provision_registry.source_bytes(version.version_id) == payload
    selected = app.evidence._source_registry.select_provision_revision(
        version.source.source_id, "1", NOW.date(),
        checked_at=app.evidence._revision_checked_at(),
        source_bytes=app.evidence._revision_source_bytes,
        review_owner=app.evidence._revision_review_owner)
    assert selected.state is SelectionState.NOT_ASSESSED and selected.approval is None
    assert revision.subject_id in selected.candidate_ids
    assert "review" in selected.reason


def test_application_cannot_use_retained_registry_after_actual_pointer_changes(
        tmp_path, monkeypatch, scripted_application_environment):
    _published, version, _revision, _payload = _candidate_publication(tmp_path)
    app = _app(tmp_path, monkeypatch)
    (tmp_path / "published" / "current.json").write_text("{}")
    assert app.provision_registry.source_bytes(version.version_id) is None
    selected = app.evidence._source_registry.select_provision_revision(
        version.source.source_id, "1", NOW.date(),
        checked_at=app.evidence._revision_checked_at(),
        source_bytes=app.evidence._revision_source_bytes,
        review_owner=app.evidence._revision_review_owner)
    assert selected.state is SelectionState.REFUSED and selected.approval is None


def test_application_refused_metadata_never_installs_a_partial_registry(
        tmp_path, monkeypatch, scripted_application_environment):
    _candidate_publication(tmp_path, malformed=True)
    app = _app(tmp_path, monkeypatch)
    assert app.provision_registry.state is RegistryLoadState.REFUSED
    assert app.evidence._source_registry is None
    assert app.provision_registry.source_bytes is None
