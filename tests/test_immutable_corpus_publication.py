"""P20 / BK-84-AC2 — immutable publication, cutover and invalidation."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from nm.adapters.evidence.corpus import CorpusEvidenceAdapter
from nm.adapters.model.config import ModelConfig, TierConfig
from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.search.authority import AuthorityIndexSearch
from nm.adapters.store.directory import FileDirectory
from nm.adapters.store.file_store import FileMatterStore
from nm.bootstrap.composition import INDEX_PROCESSOR, Application
from nm.knowledge.acquisition import (
    AcquiredArtifact,
    AcquisitionRoute,
    AcquisitionScope,
    JudgmentCandidate,
    select_candidates,
    stage_acquisition,
)
from nm.knowledge.artefact import ArtefactLineage
from nm.knowledge.manifest import (
    CorpusArtefactInput,
    CorpusDependency,
    CorpusPublicationRefused,
    CorpusSourceInput,
    PublishedCorpus,
    get_corpus,
    get_source,
    publish_corpus,
    record_corpus_dependency,
    rollback_corpus,
    withdraw_corpus,
)
from nm.knowledge.provenance import Standing, Treatment
from nm.knowledge.source_registry import (
    CanonicalSource,
    LegalReview,
    ReviewState,
    RightsReview,
    RightsState,
    SourceKind,
    SourceRegistry,
    SourceVersion,
)
from nm.ports.evidence import Coverage
from nm.ports.model import Tier

pytestmark = pytest.mark.class_a

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
AUTHORITY = "a" * 64
KEY = "p20-test-key-not-a-secret"


def _source(identifier: str = "SYN-1") -> CanonicalSource:
    return CanonicalSource(
        kind=SourceKind.INSTRUMENT,
        jurisdiction="Union of India",
        issuing_body="Synthetic Legislature",
        official_identifier=identifier,
        display_name=f"Synthetic Act {identifier}",
    )


def _version(
    payload: bytes,
    *,
    identifier: str = "SYN-1",
    rights: RightsReview | None = None,
    review: LegalReview | None = None,
) -> SourceVersion:
    return SourceVersion(
        source=_source(identifier),
        content_sha256=hashlib.sha256(payload).hexdigest(),
        language="English",
        observed_at=NOW.date(),
        rights=rights or RightsReview(
            RightsState.PERMITTED,
            basis="synthetic fixture permits test publication",
            reviewed_at=NOW.date(),
        ),
        legal_review=review or LegalReview(
            ReviewState.APPROVED,
            reviewed_at=NOW.date(),
            valid_until=NOW.date() + timedelta(days=30),
            authority_digest=AUTHORITY,
        ),
        standing=Standing.ENACTED,
        treatment=Treatment.UNTREATED,
        effective_from=date(2020, 1, 1),
        supported_coverage=("union_of_india",),
    )


def _registered(
    payload: bytes,
    *,
    identifier: str = "SYN-1",
    rights: RightsReview | None = None,
    review: LegalReview | None = None,
) -> tuple[SourceRegistry, SourceVersion]:
    registry = SourceRegistry()
    version = _version(
        payload, identifier=identifier, rights=rights, review=review,
    )
    registry.register_version(version)
    return registry, version


def _artefact(
    path: str,
    payload: bytes,
    version_id: str,
    *,
    digest: str | None = None,
    expected_population: int = 1,
    observed_population: int = 1,
) -> CorpusArtefactInput:
    return CorpusArtefactInput(
        path,
        payload,
        ArtefactLineage(
            artefact=path,
            builder="synthetic deterministic builder v1",
            source_versions=(version_id,),
            content_sha256=digest or hashlib.sha256(payload).hexdigest(),
            model="not_applicable: deterministic fixture",
            tokenizer="not_applicable: byte-preserving fixture",
            dimension_basis="not_applicable: non-vector artefact",
            population_basis="synthetic fixture records",
            expected_population=expected_population,
            observed_population=observed_population,
        ),
    )


def _staged_input(
    publication_root: Path,
    payload: bytes,
    version: SourceVersion,
    *,
    relative_path: str,
) -> CorpusSourceInput:
    candidate_id = f"candidate-{uuid.uuid4().hex}"
    source_url = f"https://example.invalid/{candidate_id}"
    scope = AcquisitionScope(
        route=AcquisitionRoute.API,
        source="synthetic official source",
        jurisdiction="Union of India",
        document_types=("instrument",),
        from_date=date(2020, 1, 1),
        to_date=NOW.date(),
        discovery_budget=1,
        selection_budget=1,
        authorization_id=f"auth-{uuid.uuid4().hex}",
    )
    selection = select_candidates(scope, (
        JudgmentCandidate(
            candidate_id=candidate_id,
            source=scope.source,
            jurisdiction=scope.jurisdiction,
            issuing_body=version.source.issuing_body,
            document_type="instrument",
            source_url=source_url,
            source_date=NOW.date(),
            citation_count=None,
        ),
    ))
    staging_root = publication_root.parent \
        / f".{publication_root.name}-staging-{uuid.uuid4().hex}"
    run_id = f"run-{uuid.uuid4().hex}"
    run = stage_acquisition(
        staging_root,
        run_id=run_id,
        scope=scope,
        selection=selection,
        artifacts=(AcquiredArtifact(
            candidate_id,
            version.source.source_id,
            source_url,
            payload,
        ),),
        observed_at=NOW,
    )
    return CorpusSourceInput(
        version.version_id,
        relative_path,
        run,
        candidate_id,
        binding_on="union_of_india",
    )


def _publish(
    root: Path,
    payload: bytes = b"law-v1",
    *,
    release: str = "r1",
    identifier: str = "SYN-1",
    registry: SourceRegistry | None = None,
    version: SourceVersion | None = None,
    artefacts: tuple[CorpusArtefactInput, ...] | None = None,
    fault=None,
) -> PublishedCorpus:
    if registry is None or version is None:
        registry, version = _registered(payload, identifier=identifier)
    staged = _staged_input(
        root,
        payload,
        version,
        relative_path=f"sources/{identifier}.txt",
    )
    return publish_corpus(
        root,
        release_id=release,
        registry=registry,
        expected_version_ids=(version.version_id,),
        sources=(staged,),
        artefacts=artefacts or (
            _artefact("indexes/probe.bin", b"derived", version.version_id),
        ),
        observed_at=NOW,
        fault=fault,
    )


def test_publish_reconciles_and_exposes_only_one_complete_snapshot(tmp_path):
    corpus = _publish(tmp_path)

    assert corpus.snapshot_id.startswith("corpus_")
    assert get_corpus(tmp_path).snapshot_id == corpus.snapshot_id
    version_id = corpus.manifest["expected_versions"][0]
    assert get_source(tmp_path, version_id) == b"law-v1"
    assert (tmp_path / "snapshots" / corpus.snapshot_id / "candidate.json").is_file()
    assert (tmp_path / "manifests" / f"{corpus.snapshot_id}.published.json").is_file()
    assert json.loads((tmp_path / "current.json").read_text())["snapshot_id"] \
        == corpus.snapshot_id


@pytest.mark.parametrize(
    ("phase", "expected_release"),
    [
        ("candidate_prepared", "r1"),
        ("candidate_committed", "r1"),
        ("published_manifest_committed", "r1"),
        ("before_pointer_replace", "r1"),
        ("pointer_committed", "r2"),
    ],
)
def test_interruption_exposes_old_or_new_complete_generation_only(
    tmp_path, phase, expected_release,
):
    old = _publish(tmp_path)
    registry, version = _registered(b"law-v2", identifier="SYN-2")

    def stop(at: str) -> None:
        if at == phase:
            raise InterruptedError(at)

    with pytest.raises(InterruptedError, match=phase):
        _publish(
            tmp_path,
            b"law-v2",
            release="r2",
            identifier="SYN-2",
            registry=registry,
            version=version,
            fault=stop,
        )

    visible = PublishedCorpus.open(tmp_path, verify_all=True)
    assert visible.manifest["release_id"] == expected_release
    if expected_release == "r1":
        assert visible.snapshot_id == old.snapshot_id


@pytest.mark.parametrize(
    "expected,sources",
    [
        (("missing",), ()),
        (("duplicate", "duplicate"), ()),
    ],
)
def test_empty_duplicate_or_missing_population_is_refused(tmp_path, expected, sources):
    registry, version = _registered(b"law")
    with pytest.raises(CorpusPublicationRefused, match="population|versions"):
        publish_corpus(
            tmp_path,
            release_id="bad-population",
            registry=registry,
            expected_version_ids=expected,
            sources=sources,
            artefacts=(),
            observed_at=NOW,
        )

    # The real registered version but no staged source is also a mismatch.
    with pytest.raises(CorpusPublicationRefused, match="exactly match"):
        publish_corpus(
            tmp_path,
            release_id="missing-source",
            registry=registry,
            expected_version_ids=(version.version_id,),
            sources=(),
            artefacts=(),
            observed_at=NOW,
        )


def test_unexpected_or_duplicate_staged_sources_are_refused(tmp_path):
    registry, first = _registered(b"one")
    second = _version(b"two", identifier="SYN-2")
    registry.register_version(second)
    one = _staged_input(
        tmp_path / "publication", b"one", first, relative_path="sources/one",
    )
    two = _staged_input(
        tmp_path / "publication", b"two", second, relative_path="sources/two",
    )

    with pytest.raises(CorpusPublicationRefused, match="exactly match"):
        publish_corpus(
            tmp_path / "publication",
            release_id="unexpected",
            registry=registry,
            expected_version_ids=(first.version_id,),
            sources=(one, two),
            artefacts=(),
            observed_at=NOW,
        )
    with pytest.raises(CorpusPublicationRefused, match="exactly match"):
        publish_corpus(
            tmp_path / "publication",
            release_id="duplicate",
            registry=registry,
            expected_version_ids=(first.version_id,),
            sources=(one, one),
            artefacts=(),
            observed_at=NOW,
        )


@pytest.mark.parametrize(
    "rights,review,reason",
    [
        (RightsReview(RightsState.UNKNOWN), None, "rights"),
        (RightsReview(RightsState.RESTRICTED, basis="licence"), None, "rights"),
        (None, LegalReview(ReviewState.STALE), "stale"),
        (None, LegalReview(ReviewState.REFUSED, reason="wrong law"), "refused"),
    ],
)
def test_rights_and_legal_review_states_cannot_be_published(
    tmp_path, rights, review, reason,
):
    registry, version = _registered(b"law", rights=rights, review=review)
    with pytest.raises(CorpusPublicationRefused, match=reason):
        _publish(tmp_path, registry=registry, version=version)


def test_changed_source_or_derived_bytes_are_refused(tmp_path):
    registry, version = _registered(b"reviewed")
    with pytest.raises(CorpusPublicationRefused, match="do not match"):
        _publish(
            tmp_path / "source",
            payload=b"changed",
            registry=registry,
            version=version,
        )

    unreconciled = _artefact(
        "indexes/index.bin",
        b"derived",
        version.version_id,
        expected_population=2,
        observed_population=1,
    )
    with pytest.raises(CorpusPublicationRefused, match="expected 2 records"):
        _publish(
            tmp_path / "population",
            payload=b"reviewed",
            registry=registry,
            version=version,
            artefacts=(unreconciled,),
        )

    changed = _artefact(
        "indexes/index.bin",
        b"changed",
        version.version_id,
        digest=hashlib.sha256(b"reviewed").hexdigest(),
    )
    with pytest.raises(CorpusPublicationRefused, match="lineage records"):
        _publish(
            tmp_path / "artefact",
            payload=b"reviewed",
            registry=registry,
            version=version,
            artefacts=(changed,),
        )


def test_changed_quarantine_bytes_and_wrong_staged_identity_are_refused(tmp_path):
    registry, version = _registered(b"law")
    staged = _staged_input(
        tmp_path / "publication",
        b"law",
        version,
        relative_path="sources/law",
    )
    receipt = json.loads((Path(staged.acquisition_run) / "receipt.json").read_text())
    staged_file = Path(staged.acquisition_run) / receipt["artifacts"][0]["file"]
    staged_file.write_bytes(b"changed")
    with pytest.raises(CorpusPublicationRefused, match="acquisition receipt"):
        publish_corpus(
            tmp_path / "publication",
            release_id="changed-quarantine",
            registry=registry,
            expected_version_ids=(version.version_id,),
            sources=(staged,),
            artefacts=(),
            observed_at=NOW,
        )

    wrong_version = _version(b"law", identifier="OTHER-LAW")
    wrong_source = _staged_input(
        tmp_path / "other-publication",
        b"law",
        wrong_version,
        relative_path="sources/law",
    )
    with pytest.raises(CorpusPublicationRefused, match="source identity"):
        publish_corpus(
            tmp_path / "other-publication",
            release_id="wrong-identity",
            registry=registry,
            expected_version_ids=(version.version_id,),
            sources=(replace(wrong_source, version_id=version.version_id),),
            artefacts=(),
            observed_at=NOW,
        )


@pytest.mark.parametrize(
    "path",
    ["../escape", "/absolute", "nested\\windows", "./alias", "candidate.json"],
)
def test_every_member_path_escape_spelling_is_refused(tmp_path, path):
    registry, version = _registered(b"law")
    staged = _staged_input(
        tmp_path,
        b"law",
        version,
        relative_path="sources/safe",
    )
    with pytest.raises(CorpusPublicationRefused, match="path"):
        publish_corpus(
            tmp_path,
            release_id="escape",
            registry=registry,
            expected_version_ids=(version.version_id,),
            sources=(replace(staged, relative_path=path),),
            artefacts=(),
            observed_at=NOW,
        )


def test_snapshot_identity_cannot_be_reused_or_overwritten(tmp_path):
    _publish(tmp_path)
    with pytest.raises(CorpusPublicationRefused, match="already exists"):
        _publish(tmp_path)
    assert get_corpus(tmp_path).manifest["release_id"] == "r1"


@pytest.mark.parametrize("target", ["pointer", "manifest", "member"])
def test_corrupt_active_state_fails_closed(tmp_path, target):
    corpus = _publish(tmp_path)
    if target == "pointer":
        pointer = json.loads((tmp_path / "current.json").read_text())
        pointer["snapshot_id"] = "corpus_" + "0" * 64
        (tmp_path / "current.json").write_text(json.dumps(pointer))
    elif target == "manifest":
        path = tmp_path / "manifests" / f"{corpus.snapshot_id}.published.json"
        value = json.loads(path.read_text())
        value["release_id"] = "tampered"
        path.write_text(json.dumps(value))
    else:
        path = corpus.member_path("indexes/probe.bin")
        path.write_bytes(b"tampered")

    with pytest.raises(CorpusPublicationRefused):
        PublishedCorpus.open(tmp_path, verify_all=True)


def test_snapshot_id_is_recomputed_even_if_all_outer_digests_are_rewritten(tmp_path):
    corpus = _publish(tmp_path)
    candidate_path = tmp_path / "snapshots" / corpus.snapshot_id / "candidate.json"
    published_path = tmp_path / "manifests" / f"{corpus.snapshot_id}.published.json"
    pointer_path = tmp_path / "current.json"
    candidate = json.loads(candidate_path.read_text())
    published = json.loads(published_path.read_text())
    candidate["release_id"] = published["release_id"] = "rewritten"
    def canonical(value):
        return (json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ) + "\n").encode()
    candidate_bytes = canonical(candidate)
    candidate_path.write_bytes(candidate_bytes)
    published["candidate_manifest_sha256"] = hashlib.sha256(candidate_bytes).hexdigest()
    published_bytes = canonical(published)
    published_path.write_bytes(published_bytes)
    pointer = json.loads(pointer_path.read_text())
    pointer["manifest_sha256"] = hashlib.sha256(published_bytes).hexdigest()
    pointer_path.write_bytes(canonical(pointer))

    with pytest.raises(CorpusPublicationRefused, match="content identity"):
        PublishedCorpus.open(tmp_path)


def test_pointer_snapshot_identity_cannot_escape_the_manifest_directory(tmp_path):
    _publish(tmp_path)
    pointer_path = tmp_path / "current.json"
    pointer = json.loads(pointer_path.read_text())
    pointer["snapshot_id"] = "corpus_../../outside"
    pointer["manifest"] = "manifests/corpus_../../outside.published.json"
    pointer_path.write_text(json.dumps(pointer))

    with pytest.raises(CorpusPublicationRefused, match="snapshot id"):
        PublishedCorpus.open(tmp_path)


def test_active_pointer_requires_its_content_addressed_transition(tmp_path):
    _publish(tmp_path)
    pointer = json.loads((tmp_path / "current.json").read_text())
    transition = tmp_path / "transitions" / f"{pointer['transition_id']}.json"
    transition.unlink()

    with pytest.raises(CorpusPublicationRefused, match="transition"):
        PublishedCorpus.open(tmp_path)


def test_concurrent_publisher_is_refused_while_first_writer_holds_lock(tmp_path):
    reached = threading.Event()
    release = threading.Event()
    failure: list[BaseException] = []

    def pause(phase: str) -> None:
        if phase == "candidate_prepared":
            reached.set()
            assert release.wait(5)

    def first() -> None:
        try:
            _publish(tmp_path, fault=pause)
        except BaseException as exc:  # surfaced in the test thread
            failure.append(exc)

    thread = threading.Thread(target=first)
    thread.start()
    assert reached.wait(5)
    with pytest.raises(CorpusPublicationRefused, match="publication is active"):
        _publish(tmp_path, release="r2")
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    assert not failure
    assert PublishedCorpus.open(tmp_path, verify_all=True)


def test_rollback_changes_only_the_pointer_and_preserves_both_snapshots(tmp_path):
    first = _publish(tmp_path)
    second = _publish(tmp_path, b"law-v2", release="r2", identifier="SYN-2")

    restored = rollback_corpus(
        tmp_path,
        target_snapshot_id=first.snapshot_id,
        reason="measured regression",
        observed_at=NOW + timedelta(minutes=1),
    )

    assert restored.snapshot_id == first.snapshot_id
    assert PublishedCorpus._from_snapshot(
        tmp_path.resolve(), second.snapshot_id, verify_all=True,
    ).snapshot_id == second.snapshot_id
    assert len(list((tmp_path / "transitions").glob("*.json"))) == 3


def test_withdrawal_rolls_back_and_flags_exact_dependent_work(tmp_path):
    first = _publish(tmp_path)
    second = _publish(tmp_path, b"law-v2", release="r2", identifier="SYN-2")
    second_version = second.manifest["expected_versions"][0]
    record_corpus_dependency(
        tmp_path,
        CorpusDependency(
            "matter-17-advice-3",
            second.snapshot_id,
            (second_version,),
            NOW,
        ),
    )

    result = withdraw_corpus(
        tmp_path,
        snapshot_id=second.snapshot_id,
        source_version_ids=(second_version,),
        reason="authority amended",
        observed_at=NOW + timedelta(minutes=2),
    )

    assert result.affected_work == ("matter-17-advice-3",)
    assert result.active_snapshot_id == first.snapshot_id
    assert get_corpus(tmp_path).snapshot_id == first.snapshot_id
    with pytest.raises(CorpusPublicationRefused, match="withdrawn"):
        PublishedCorpus._from_snapshot(tmp_path.resolve(), second.snapshot_id)
    invalidation = json.loads(next(
        (tmp_path / "withdrawals").glob("*.json")
    ).read_text())
    assert invalidation["affected_work"] == ["matter-17-advice-3"]


def test_withdrawal_without_fallback_fails_closed_instead_of_serving_bad_law(tmp_path):
    only = _publish(tmp_path)
    version_id = only.manifest["expected_versions"][0]
    result = withdraw_corpus(
        tmp_path,
        snapshot_id=only.snapshot_id,
        source_version_ids=(version_id,),
        reason="source withdrawn",
        observed_at=NOW,
    )
    assert result.active_snapshot_id is None
    with pytest.raises(CorpusPublicationRefused, match="withdrawn"):
        get_corpus(tmp_path)


def test_withdrawn_version_invalidates_all_snapshots_and_work_that_used_it(tmp_path):
    registry, version = _registered(b"law")
    first = _publish(
        tmp_path,
        payload=b"law",
        release="r1",
        registry=registry,
        version=version,
    )
    second = _publish(
        tmp_path,
        payload=b"law",
        release="r2",
        registry=registry,
        version=version,
    )
    record_corpus_dependency(
        tmp_path,
        CorpusDependency(
            "matter-old", first.snapshot_id, (version.version_id,), NOW,
        ),
    )
    record_corpus_dependency(
        tmp_path,
        CorpusDependency(
            "matter-new", second.snapshot_id, (version.version_id,), NOW,
        ),
    )

    result = withdraw_corpus(
        tmp_path,
        snapshot_id=second.snapshot_id,
        source_version_ids=(version.version_id,),
        reason="legal status changed",
        observed_at=NOW,
    )

    assert result.active_snapshot_id is None
    assert result.affected_work == ("matter-new", "matter-old")
    with pytest.raises(CorpusPublicationRefused, match="withdrawn"):
        PublishedCorpus._from_snapshot(tmp_path.resolve(), first.snapshot_id)
    with pytest.raises(CorpusPublicationRefused, match="withdrawn"):
        PublishedCorpus._from_snapshot(tmp_path.resolve(), second.snapshot_id)


def test_withdrawing_historical_snapshot_cannot_leave_same_version_active(tmp_path):
    registry, version = _registered(b"law")
    historical = _publish(
        tmp_path,
        payload=b"law",
        release="r1",
        registry=registry,
        version=version,
    )
    _publish(
        tmp_path,
        payload=b"law",
        release="r2",
        registry=registry,
        version=version,
    )

    result = withdraw_corpus(
        tmp_path,
        snapshot_id=historical.snapshot_id,
        source_version_ids=(version.version_id,),
        reason="the shared legal version was withdrawn",
        observed_at=NOW,
    )

    assert result.active_snapshot_id is None
    with pytest.raises(CorpusPublicationRefused, match="withdrawn"):
        get_corpus(tmp_path)


def test_changed_dependency_record_cannot_hide_affected_work(tmp_path):
    active = _publish(tmp_path)
    version_id = active.manifest["expected_versions"][0]
    record_corpus_dependency(
        tmp_path,
        CorpusDependency(
            "matter-relied-on-law", active.snapshot_id, (version_id,), NOW,
        ),
    )
    path = next((tmp_path / "dependencies").glob("*.json"))
    value = json.loads(path.read_text())
    value["source_versions"] = []
    path.write_text(json.dumps(value))

    with pytest.raises(CorpusPublicationRefused, match="dependency identity"):
        withdraw_corpus(
            tmp_path,
            snapshot_id=active.snapshot_id,
            source_version_ids=(version_id,),
            reason="authority withdrawn",
            observed_at=NOW,
        )
    assert not list((tmp_path / "withdrawals").glob("*.json"))


def test_changed_withdrawal_record_cannot_revive_invalidated_law(tmp_path):
    active = _publish(tmp_path)
    version_id = active.manifest["expected_versions"][0]
    withdraw_corpus(
        tmp_path,
        snapshot_id=active.snapshot_id,
        source_version_ids=(version_id,),
        reason="authority withdrawn",
        observed_at=NOW,
    )
    path = next((tmp_path / "withdrawals").glob("*.json"))
    value = json.loads(path.read_text())
    value["source_versions"] = []
    path.write_text(json.dumps(value))

    with pytest.raises(CorpusPublicationRefused, match="withdrawal identity"):
        get_corpus(tmp_path)


def _sqlite_payload(path: Path, *, authority: bool) -> bytes:
    connection = sqlite3.connect(path)
    if authority:
        connection.execute(
            "create virtual table paras using fts5(case_id, case_name, court, "
            "year, para_type, chunk_id, text)"
        )
        connection.execute(
            "insert into paras values "
            "('c1','A v B','Supreme Court of India','2025','ratio','p1',"
            "'possession follows the proved title')"
        )
        connection.execute("create table identity(key text primary key, value text)")
        connection.executemany(
            "insert into identity values (?, ?)",
            [
                ("built_at", NOW.isoformat()),
                ("source", "synthetic authority fixture"),
                ("corpus_version", "r1"),
                ("indexed_paragraphs", "1"),
                ("source_paragraphs", "1"),
                ("scope", "Union of India"),
            ],
        )
    else:
        connection.execute("create table chunks(id text primary key, text text)")
    connection.commit()
    connection.close()
    return path.read_bytes()


def _runtime_publication(tmp_path: Path) -> PublishedCorpus:
    registry, version = _registered(b"law")
    chunks = _sqlite_payload(tmp_path / "chunks.fixture", authority=False)
    authority = _sqlite_payload(tmp_path / "authority.fixture", authority=True)
    coverage = (
        b"corpus_version: r1\nreconciled_at: '2026-09-11'\nacts:\n"
        b"  - act_name: Synthetic Act SYN-1\n"
        b"    act_patterns: ['%SYNTHETIC ACT%']\n"
        b"    intended_sections: ['1']\n"
    )
    artefacts = tuple(
        _artefact(path, payload, version.version_id)
        for path, payload in (
            ("corpus/chunks.db", chunks),
            ("corpus/manifest.yaml", coverage),
            ("indexes/authority.db", authority),
        )
    )
    return _publish(
        tmp_path / "published",
        payload=b"law",
        registry=registry,
        version=version,
        artefacts=artefacts,
    )


def test_existing_evidence_and_search_adapters_open_only_published_members(tmp_path):
    published = _runtime_publication(tmp_path)

    evidence = CorpusEvidenceAdapter.from_published_corpus(tmp_path / "published")
    search = AuthorityIndexSearch.from_published_corpus(tmp_path / "published")

    assert evidence.available
    result = search.search("possession")
    assert result.coverage is Coverage.ANSWERED
    assert [hit.case_id for hit in result.hits] == ["c1"]
    assert evidence._published_snapshot.snapshot_id == published.snapshot_id
    assert search._published_snapshot.snapshot_id == published.snapshot_id


def _scripted_model() -> ScriptedModelAdapter:
    config = ModelConfig(tiers={
        Tier.ROUTINE: TierConfig(
            Tier.ROUTINE, "scripted", "scripted-1", None, None,
        ),
        Tier.EMBED: TierConfig(
            Tier.EMBED, "scripted", "text-embedding-3-large", None, None,
        ),
    })
    return ScriptedModelAdapter(config, responses={"__default__": "synthetic"})


def test_application_composition_serves_one_published_generation(
    tmp_path, monkeypatch, scripted_application_environment,
):
    published = _runtime_publication(tmp_path)
    publication_root = tmp_path / "published"
    monkeypatch.setenv("NM_CORPUS_DIR", str(publication_root))
    monkeypatch.setenv("NM_MATTER_KEY", KEY)
    monkeypatch.delenv("NM_AUTHORITY_INDEX", raising=False)
    monkeypatch.delenv("NM_IDENTITY_INDEX", raising=False)
    matter_root = tmp_path / "matters"
    application = Application(
        root=Path(__file__).resolve().parents[1],
        store=FileMatterStore(matter_root, key=KEY),
        directory=FileDirectory(matter_root, key=KEY),
        model=_scripted_model(),
    )

    assert application.evidence.published_snapshot_id == published.snapshot_id
    assert application.search._published_snapshot.snapshot_id == published.snapshot_id
    assert application.evidence._published_snapshot is application.search._published_snapshot
    assert application.manifest.corpus_version == "r1"
    assert application.search.search("possession").coverage is Coverage.ANSWERED


def test_application_refuses_index_overrides_that_mix_published_generations(
    tmp_path, monkeypatch, scripted_application_environment,
):
    _runtime_publication(tmp_path)
    monkeypatch.setenv("NM_CORPUS_DIR", str(tmp_path / "published"))
    monkeypatch.setenv("NM_AUTHORITY_INDEX", str(tmp_path / "other.db"))
    monkeypatch.setenv("NM_MATTER_KEY", KEY)

    with pytest.raises(RuntimeError, match="mix generations"):
        Application(
            root=Path(__file__).resolve().parents[1],
            store=FileMatterStore(tmp_path / "matters", key=KEY),
            directory=FileDirectory(tmp_path / "matters", key=KEY),
            model=_scripted_model(),
        )


@pytest.mark.parametrize("selection", ["published", "legacy", "injected"])
def test_every_selected_search_refuses_dispatch_after_index_approval_is_removed(
    tmp_path, monkeypatch, scripted_application_environment, selection,
):
    """Corpus selection cannot bypass the shared pre-dispatch policy."""
    published = _runtime_publication(tmp_path)
    monkeypatch.setenv("NM_MATTER_KEY", KEY)
    monkeypatch.delenv("NM_AUTHORITY_INDEX", raising=False)
    monkeypatch.delenv("NM_IDENTITY_INDEX", raising=False)
    monkeypatch.setenv("NM_CORPUS_DIR", str(tmp_path / "published"))
    supplied_search = None
    if selection == "legacy":
        monkeypatch.setenv("NM_CORPUS_DIR", str(tmp_path / "legacy"))
        monkeypatch.setenv(
            "NM_AUTHORITY_INDEX", str(published.member_path("indexes/authority.db")),
        )
    elif selection == "injected":
        supplied_search = AuthorityIndexSearch.from_published_snapshot(published)

    calls: list[str] = []
    audit: list[str] = []
    original_search = AuthorityIndexSearch.search

    def observe_search(adapter, query, **filters):
        calls.append(query)
        return original_search(adapter, query, **filters)

    monkeypatch.setattr(AuthorityIndexSearch, "search", observe_search)
    monkeypatch.setattr(Application, "_egress_audit", lambda self, line: audit.append(line))
    matter_root = tmp_path / "matters"
    application = Application(
        root=Path(__file__).resolve().parents[1],
        store=FileMatterStore(matter_root, key=KEY),
        directory=FileDirectory(matter_root, key=KEY),
        model=_scripted_model(),
        search=supplied_search,
    )

    allowed = application.search.search("possession")
    assert allowed.coverage is Coverage.ANSWERED
    assert [hit.case_id for hit in allowed.hits] == ["c1"]
    assert calls == ["possession"]

    # Change the one real policy after the successful read. A wrapper added
    # only to a constructor branch, or a cached admission, cannot pass this.
    application._gate.policy = replace(
        application._gate.policy,
        processors=tuple(
            processor for processor in application._gate.policy.processors
            if processor.processor_id != INDEX_PROCESSOR
        ),
    )
    secret = "synthetic confidential instruction about possession"
    refused = application.search.search(secret)
    assert refused.coverage is Coverage.NOT_ASSESSED
    assert refused.hits == ()
    assert INDEX_PROCESSOR in refused.why
    assert secret not in refused.why
    assert calls == ["possession"]
    assert any("REFUSED sink=index" in line for line in audit)
    assert all(secret not in line for line in audit)


def test_p20_adversarial_witness_rejects_partial_changed_and_withdrawn_law(
    tmp_path,
):
    old = _publish(tmp_path / "cutover")
    registry, changed = _registered(b"law-v2", identifier="SYN-2")

    def interrupt(phase: str) -> None:
        if phase == "before_pointer_replace":
            raise InterruptedError(phase)

    with pytest.raises(InterruptedError):
        _publish(
            tmp_path / "cutover",
            b"law-v2",
            release="r2",
            identifier="SYN-2",
            registry=registry,
            version=changed,
            fault=interrupt,
        )
    assert get_corpus(tmp_path / "cutover").snapshot_id == old.snapshot_id

    reviewed_registry, reviewed = _registered(b"reviewed", identifier="SYN-3")
    with pytest.raises(CorpusPublicationRefused, match="do not match"):
        _publish(
            tmp_path / "changed",
            b"substituted",
            registry=reviewed_registry,
            version=reviewed,
        )

    active = _publish(tmp_path / "withdrawn")
    version_id = active.manifest["expected_versions"][0]
    record_corpus_dependency(
        tmp_path / "withdrawn",
        CorpusDependency(
            "matter-advice", active.snapshot_id, (version_id,), NOW,
        ),
    )
    result = withdraw_corpus(
        tmp_path / "withdrawn",
        snapshot_id=active.snapshot_id,
        source_version_ids=(version_id,),
        reason="authority withdrawn",
        observed_at=NOW,
    )
    assert result.affected_work == ("matter-advice",)
    with pytest.raises(CorpusPublicationRefused, match="withdrawn"):
        get_corpus(tmp_path / "withdrawn")


def test_adapter_construction_refuses_a_tampered_published_index(tmp_path):
    registry, version = _registered(b"law")
    authority = _sqlite_payload(tmp_path / "authority.fixture", authority=True)
    published = _publish(
        tmp_path / "published",
        payload=b"law",
        registry=registry,
        version=version,
        artefacts=(
            _artefact("indexes/authority.db", authority, version.version_id),
        ),
    )
    published.member_path("indexes/authority.db").write_bytes(b"changed")

    with pytest.raises(CorpusPublicationRefused, match="changed after publication"):
        AuthorityIndexSearch.from_published_corpus(tmp_path / "published")
