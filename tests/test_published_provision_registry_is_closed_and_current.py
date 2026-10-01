"""Controlled candidate metadata, not published legal/interval approval."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import date

import pytest

import nm.Archives.legal_brain.retrieve.provision_registry_composition as owner
from nm.Archives.legal_brain.common.citation_contracts import ProvisionKeyState
from nm.Archives.legal_brain.retrieve.manifest_sources import CorpusPublicationRefused, PublishedCorpus, _event_id
from nm.Archives.legal_brain.retrieve.provenance_sources import Standing
from nm.Archives.legal_brain.retrieve.provision_registry_composition import (
    REGISTRY_MEMBER,
    ProvisionRegistryRefused,
    RegistryLoadState,
    load_provision_registry,
)
from nm.Archives.legal_brain.retrieve.provision_revision_sources import (
    AuthorityRole,
    AuthoritySpan,
    ProvisionRevision,
    RevisionKind,
    SelectionState,
    TransitionState,
    _wire,
)
from nm.Archives.legal_brain.retrieve.source_registry_sources import (
    BindingState,
    CanonicalSource,
    LegalReview,
    ReviewState,
    RightsReview,
    RightsState,
    SourceKind,
    SourceRegistry,
    SourceVersion,
)

pytestmark = pytest.mark.class_a
TODAY = date.today()


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def population(tmp_path):
    """An actual byte-owning snapshot fixture, with NO legal review approval.

    Construction isolates the loader from publication/signing workflows.  Its
    members are read by the real PublishedCorpus.read/get_source implementation.
    It is not a fabricated counsel signature or evidence of curated law.
    """
    text = "Synthetic wording. Exact enactment. Exact commencement."
    source = CanonicalSource(
        SourceKind.INSTRUMENT,
        "Synthetic jurisdiction",
        "Synthetic legislature",
        "Synthetic instrument",
        "Synthetic instrument",
    )
    version = SourceVersion(
        source,
        hashlib.sha256(text.encode()).hexdigest(),
        "English",
        TODAY,
        RightsReview(RightsState.PERMITTED, "controlled local fixture"),
        LegalReview(ReviewState.UNREVIEWED),
        standing=Standing.ENACTED,
        effective_from=TODAY,
        supported_coverage=("Synthetic jurisdiction",),
    )
    wording = AuthoritySpan(version.version_id, "synthetic clause", 0, 18, AuthorityRole.WORDING)
    enact = AuthoritySpan(
        version.version_id, "synthetic enactment", 19, 35, AuthorityRole.ENACTMENT
    )
    start = AuthoritySpan(
        version.version_id, "synthetic commencement", 36, len(text), AuthorityRole.COMMENCEMENT
    )
    revision = ProvisionRevision(
        source.source_id,
        "7",
        wording,
        RevisionKind.ORIGINAL,
        TODAY,
        None,
        TODAY,
        (enact, start),
        (),
        TransitionState.NOT_APPLICABLE,
        (),
    )
    value = {
        "schema": 1,
        "sources": [_wire(source)],
        "versions": [_wire(version)],
        "aliases": [{"reference": source.display_name, "source_id": source.source_id}],
        "revisions": [revision.as_record()],
        "review_artifacts": ["docs/backlog/evidence/synthetic-revision-review.json"],
    }
    manifest = {
        "snapshot_id": "corpus_" + "a" * 64,
        "expected_versions": [version.version_id],
        "sources": [
            {
                "path": "sources/synthetic.txt",
                "version_id": version.version_id,
                "source_id": source.source_id,
                "sha256": version.content_sha256,
                "bytes": len(text.encode()),
            }
        ],
        "artefacts": [],
    }
    (tmp_path / "withdrawals").mkdir()
    members = tmp_path / "snapshots" / manifest["snapshot_id"] / "members"
    path = members / "sources/synthetic.txt"
    path.parent.mkdir(parents=True)
    path.write_bytes(text.encode())
    current = {"value": True, "checks": []}

    def fence(generation, identity):
        current["checks"].append((generation, identity))
        return current["value"]

    def snapshot(candidate=value, raw=None):
        held = copy.deepcopy(manifest)
        if candidate is not None or raw is not None:
            payload = _bytes(candidate) if raw is None else raw
            artifact = members / REGISTRY_MEMBER
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(payload)
            held["artefacts"] = [
                {
                    "path": REGISTRY_MEMBER,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "bytes": len(payload),
                }
            ]
        return PublishedCorpus(tmp_path, {}, held)

    def load(candidate=value, raw=None):
        selected = snapshot(candidate, raw)
        return selected, load_provision_registry(
            selected, source_generation=selected.snapshot_id, generation_current=fence
        )

    return value, source, version, revision, text, members, current, snapshot, load


def test_actual_published_bytes_load_typed_candidates_but_never_approve_interval(tmp_path):
    value, source, version, revision, text, _members, current, _snapshot, load = population(
        tmp_path
    )
    snapshot, result = load()
    assert result.state is RegistryLoadState.LOADED
    assert result.registry.resolve(source.display_name).source_ids == (source.source_id,)
    assert result.registry.provision_revisions() == (revision,)
    assert result.review_artifact_refs == tuple(value["review_artifacts"])
    assert current["checks"] and all(
        check == (snapshot.snapshot_id, result.metadata_identity) for check in current["checks"]
    )
    assert result.source_bytes(version.version_id) == text.encode()
    assert (
        result.registry.read_revision_authority(
            revision.wording, source_bytes=result.source_bytes
        ).text
        == text[:18]
    )
    assert (
        result.registry.read_revision_source(revision.subject_id, source_bytes=result.source_bytes)[
            2
        ]
        == text
    )
    selected = result.registry.select_provision_revision(
        source.source_id,
        "7",
        TODAY,
        checked_at=TODAY,
        source_bytes=result.source_bytes,
        review_owner=None,
    )
    assert selected.state is SelectionState.NOT_ASSESSED and selected.approval is None
    assert "review" in selected.reason
    assert (
        result.registry.readiness(
            version.version_id, content=text.encode(), as_of=TODAY
        ).state.value
        == "candidate"
    )


def test_optional_absence_or_empty_population_is_not_established_and_never_partial(tmp_path):
    value, _source, _version, _revision, _text, _members, _current, _snapshot, load = population(
        tmp_path
    )
    absent, result = load(candidate=None)
    assert result.state is RegistryLoadState.NOT_ESTABLISHED
    assert (
        result.registry is None and result.source_bytes is None and not result.review_artifact_refs
    )
    empty = copy.deepcopy(value)
    empty.update(sources=[], versions=[], revisions=[], aliases=[], review_artifacts=[])
    assert load(empty)[1].state is RegistryLoadState.NOT_ESTABLISHED
    assert (
        load_provision_registry(
            None, source_generation="generation", generation_current=lambda *_: True
        ).state
        is RegistryLoadState.NOT_ESTABLISHED
    )
    with pytest.raises(ProvisionRegistryRefused):
        result.require_current()


@pytest.mark.parametrize(
    "change",
    [
        "schema_bool",
        "schema_float",
        "unknown_top",
        "source_blank",
        "source_kind",
        "source_extra",
        "source_id_supplied",
        "source_duplicate",
        "version_duplicate",
        "version_source_changed",
        "version_digest",
        "version_date",
        "version_datetime",
        "version_date_number",
        "rights_bool",
        "rights_extra",
        "legal_review_bool",
        "legal_review_extra",
        "legal_review_incomplete",
        "standing",
        "coverage_bool",
        "coverage_duplicate",
        "version_extra",
        "revision_extra",
        "revision_duplicate",
        "revision_unheld_source",
        "revision_unheld_version",
        "span_bool",
        "span_float",
        "span_empty",
        "span_too_large",
        "span_role",
        "revision_kind",
        "reverse_interval",
        "verified_before_start",
        "transition",
        "duplicate_span",
        "aliases_type",
        "alias_extra",
        "alias_unknown_source",
        "alias_duplicate",
        "alias_typography_duplicate",
        "review_refs_type",
        "ref_duplicate",
        "ref_absolute",
        "ref_traversal",
        "ref_backslash",
        "ref_foreign_namespace",
        "ref_url",
        "ref_nonjson",
        "source_population_missing",
        "unreferenced_source",
    ],
)
def test_closed_registry_rejects_every_untyped_unowned_or_unknown_input(tmp_path, change):
    value, _source, _version, _revision, _text, _members, _current, _snapshot, load = population(
        tmp_path
    )
    row = copy.deepcopy(value)
    source, version, revision = row["sources"][0], row["versions"][0], row["revisions"][0]
    changes = {
        "schema_bool": lambda: row.update(schema=True),
        "schema_float": lambda: row.update(schema=1.0),
        "unknown_top": lambda: row.update(approved=True),
        "source_blank": lambda: source.update(display_name=" "),
        "source_kind": lambda: source.update(kind="approved"),
        "source_extra": lambda: source.update(path="source.txt"),
        "source_id_supplied": lambda: source.update(source_id="src_" + "a" * 64),
        "source_duplicate": lambda: row["sources"].append(copy.deepcopy(source)),
        "version_duplicate": lambda: row["versions"].append(copy.deepcopy(version)),
        "version_source_changed": lambda: version["source"].update(display_name="Other title"),
        "version_digest": lambda: version.update(content_sha256="b" * 64),
        "version_date": lambda: version.update(observed_at="2026-9-1"),
        "version_datetime": lambda: version.update(observed_at=TODAY.isoformat() + "T00:00:00Z"),
        "version_date_number": lambda: version.update(observed_at=1),
        "rights_bool": lambda: version["rights"].update(state=True),
        "rights_extra": lambda: version["rights"].update(approved=True),
        "legal_review_bool": lambda: version["legal_review"].update(state=True),
        "legal_review_extra": lambda: version["legal_review"].update(approved=True),
        "legal_review_incomplete": lambda: version["legal_review"].update(state="approved"),
        "standing": lambda: version.update(standing="good_law"),
        "coverage_bool": lambda: version.update(supported_coverage=[True]),
        "coverage_duplicate": lambda: version.update(
            supported_coverage=["Synthetic jurisdiction"] * 2
        ),
        "version_extra": lambda: version.update(version_id="ver_" + "a" * 64),
        "revision_extra": lambda: revision.update(approved=True),
        "revision_duplicate": lambda: row["revisions"].append(copy.deepcopy(revision)),
        "revision_unheld_source": lambda: revision.update(source_id="src_" + "c" * 64),
        "revision_unheld_version": lambda: revision["wording"].update(version_id="ver_" + "c" * 64),
        "span_bool": lambda: revision["wording"].update(start=False),
        "span_float": lambda: revision["wording"].update(end=18.0),
        "span_empty": lambda: revision["wording"].update(end=0),
        "span_too_large": lambda: revision["wording"].update(end=owner.MAX_SOURCE_BYTES + 1),
        "span_role": lambda: revision["wording"].update(role="enactment"),
        "revision_kind": lambda: revision.update(kind="current"),
        "reverse_interval": lambda: revision.update(effective_until=TODAY.isoformat()),
        "verified_before_start": lambda: revision.update(verified_through="1900-01-01"),
        "transition": lambda: revision.update(transition=True),
        "duplicate_span": lambda: revision["commencement"].append(
            copy.deepcopy(revision["commencement"][0])
        ),
        "aliases_type": lambda: row.update(aliases={}),
        "alias_extra": lambda: row["aliases"][0].update(path="x"),
        "alias_unknown_source": lambda: row["aliases"][0].update(source_id="src_" + "f" * 64),
        "alias_duplicate": lambda: row["aliases"].append(copy.deepcopy(row["aliases"][0])),
        "alias_typography_duplicate": lambda: row["aliases"].append(
            {"reference": "Ｓynthetic instrument", "source_id": source_id(row)}
        ),
        "review_refs_type": lambda: row.update(review_artifacts={}),
        "ref_duplicate": lambda: row["review_artifacts"].append(row["review_artifacts"][0]),
        "ref_absolute": lambda: row.update(review_artifacts=["C:/private/review.json"]),
        "ref_traversal": lambda: row.update(
            review_artifacts=["docs/backlog/evidence/../secrets.json"]
        ),
        "ref_backslash": lambda: row.update(
            review_artifacts=["docs/backlog/evidence\\review.json"]
        ),
        "ref_foreign_namespace": lambda: row.update(
            review_artifacts=["docs/blueprint/review.json"]
        ),
        "ref_url": lambda: row.update(review_artifacts=["https://example.com/review.json"]),
        "ref_nonjson": lambda: row.update(review_artifacts=["docs/backlog/evidence/review.py"]),
        "source_population_missing": lambda: row.update(versions=[]),
        "unreferenced_source": lambda: row["sources"].append(
            dict(source, official_identifier="Unheld")
        ),
    }
    changes[change]()
    result = load(row)[1]
    assert result.state is RegistryLoadState.REFUSED
    assert (
        result.registry is None and result.source_bytes is None and not result.review_artifact_refs
    )


def source_id(value):
    return value["aliases"][0]["source_id"]


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema":1,"schema":1}',
        b'{"schema":NaN}',
        b"\xff",
        b"{",
        b"[]",
        b"null",
        b'{"schema":Infinity}',
    ],
)
def test_duplicate_keys_nonfinite_or_unreadable_json_cannot_load(tmp_path, raw):
    load = population(tmp_path)[-1]
    assert load(raw=raw)[1].state is RegistryLoadState.REFUSED


@pytest.mark.parametrize("bound", ["bytes", "sources", "revisions", "refs", "text", "authority"])
def test_metadata_bounds_refuse_instead_of_truncating_population(tmp_path, monkeypatch, bound):
    value, *_rest, load = population(tmp_path)
    constant = {
        "bytes": "MAX_REGISTRY_BYTES",
        "sources": "MAX_POPULATION",
        "revisions": "MAX_REVISIONS",
        "refs": "MAX_REVIEW_ARTIFACTS",
        "text": "MAX_TEXT",
        "authority": "MAX_AUTHORITIES",
    }[bound]
    monkeypatch.setattr(owner, constant, 1 if bound in {"bytes", "text"} else 0)
    assert load(value)[1].state is RegistryLoadState.REFUSED


@pytest.mark.parametrize(
    "field", ["source_id", "version_id", "sha256", "expected_versions", "duplicate"]
)
def test_exact_held_manifest_population_cannot_be_reidentified(tmp_path, field):
    value, *_rest, snapshot, _load = population(tmp_path)
    selected = snapshot(value)
    if field == "expected_versions":
        selected.manifest[field] = ["ver_" + "e" * 64]
    elif field == "duplicate":
        selected.manifest["sources"].append(copy.deepcopy(selected.manifest["sources"][0]))
    else:
        selected.manifest["sources"][0][field] = "f" * 64
    result = load_provision_registry(
        selected, source_generation=selected.snapshot_id, generation_current=lambda *_: True
    )
    assert result.state is RegistryLoadState.REFUSED and result.registry is None


@pytest.mark.parametrize(
    "late",
    [
        "generation",
        "untyped_fence",
        "metadata",
        "registry",
        "artifact",
        "source_bytes",
        "withdrawal",
    ],
)
def test_every_actual_read_rechecks_generation_metadata_bytes_and_withdrawal(
    tmp_path, monkeypatch, late
):
    value, source, version, revision, _text, members, current, _snapshot, load = population(
        tmp_path
    )
    selected, result = load()
    if late == "generation":
        current["value"] = False
    elif late == "untyped_fence":
        current["value"] = 1
    elif late == "metadata":
        selected.manifest["sources"][0]["source_id"] = "changed"
    elif late == "registry":
        result.registry._versions.clear()
    elif late == "artifact":
        (members / REGISTRY_MEMBER).write_bytes(_bytes(dict(value, aliases=[])))
    elif late == "source_bytes":
        (members / "sources/synthetic.txt").write_bytes(b"changed bytes")
    elif late == "withdrawal":

        def withdrawn():
            raise CorpusPublicationRefused("controlled withdrawal")

        monkeypatch.setattr(selected, "require_usable", withdrawn)
    assert result.source_bytes(version.version_id) is None
    assert result.source_bytes("ver_" + "0" * 64) is None
    selection = result.registry.select_provision_revision(
        source.source_id,
        "7",
        TODAY,
        checked_at=TODAY,
        source_bytes=result.source_bytes,
        review_owner=None,
    )
    assert selection.state is not SelectionState.SELECTED and selection.approval is None
    if late != "source_bytes":
        with pytest.raises(ProvisionRegistryRefused):
            result.require_current()
        assert result.registry.resolve(source.display_name).state is BindingState.NOT_FOUND
        with pytest.raises(ProvisionRegistryRefused):
            result.registry.read_revision_source(
                revision.subject_id, source_bytes=result.source_bytes
            )


@pytest.mark.parametrize("operation", ["source", "version", "alias", "legacy", "revision"])
def test_loaded_registry_has_no_mutation_or_approval_door(tmp_path, operation):
    _value, source, version, revision, _text, _members, _current, _snapshot, load = population(
        tmp_path
    )
    result = load()[1]
    action = {
        "source": lambda: result.registry.register_source(source),
        "version": lambda: result.registry.register_version(version),
        "alias": lambda: result.registry.bind_alias("other", source.source_id),
        "legacy": lambda: result.registry.bind_legacy_locator("other", source.source_id),
        "revision": lambda: result.registry.register_provision_revision(revision),
    }[operation]
    with pytest.raises(ProvisionRegistryRefused):
        action()
    assert result.registry.provision_revisions() == (revision,)


def test_source_size_refused_before_original_source_read(tmp_path, monkeypatch):
    _value, _source, version, _revision, _text, _members, _current, _snapshot, load = population(
        tmp_path
    )
    selected, result = load()
    monkeypatch.setattr(owner, "MAX_SOURCE_BYTES", 1)
    calls = []
    monkeypatch.setattr(selected, "get_source", lambda value: calls.append(value))
    assert result.source_bytes(version.version_id) is None and calls == []


def test_owner_fence_changes_during_source_open_cannot_return_the_bytes(tmp_path, monkeypatch):
    _value, _source, version, _revision, _text, _members, current, _snapshot, load = population(
        tmp_path
    )
    selected, result = load()
    actual = selected.get_source

    def revoke(version_id):
        payload = actual(version_id)
        current["value"] = False
        return payload

    monkeypatch.setattr(selected, "get_source", revoke)
    assert result.source_bytes(version.version_id) is None


def test_current_callback_must_be_exact_true_even_at_initial_admission(tmp_path):
    *_prefix, current, _snapshot, load = population(tmp_path)
    current["value"] = 1
    assert load()[1].state is RegistryLoadState.REFUSED


def test_actual_corpus_owned_getter_is_accepted_but_unrelated_transport_is_not(tmp_path):
    _value, source, version, revision, text, _members, _current, _snapshot, load = population(
        tmp_path
    )
    selected, result = load()
    held = result.registry.read_revision_authority(
        revision.wording, source_bytes=selected.get_source
    )
    assert held.text == text[:18]

    def fake(_version):
        return text.encode()

    with pytest.raises(ProvisionRegistryRefused):
        result.registry.read_revision_source(revision.subject_id, source_bytes=fake)
    refused = result.registry.select_provision_revision(
        source.source_id, "7", TODAY, checked_at=TODAY, source_bytes=fake, review_owner=None
    )
    assert refused.state is SelectionState.REFUSED


def test_transport_equality_spoof_cannot_impersonate_published_byte_owner(tmp_path):
    _value, _source, _version, revision, text, _members, _current, _snapshot, load = population(
        tmp_path
    )
    result = load()[1]

    class Spoof:
        def __eq__(self, _other):
            return True

        def __call__(self, _version):
            return text.encode()

    with pytest.raises(ProvisionRegistryRefused):
        result.registry.read_revision_authority(revision.wording, source_bytes=Spoof())


def test_actual_version_global_withdrawal_register_revokes_cached_registry(tmp_path):
    _value, source, version, _revision, _text, _members, _current, _snapshot, load = population(
        tmp_path
    )
    selected, result = load()
    body = {
        "schema": 1,
        "state": "withdrawn",
        "snapshot_id": selected.snapshot_id,
        "source_versions": [version.version_id],
        "reason": "Controlled source withdrawal",
        "observed_at": TODAY.isoformat(),
        "affected_work": [],
        "replacement_snapshot_id": None,
    }
    identity = _event_id("withdrawal", body)
    (tmp_path / "withdrawals" / (identity + ".json")).write_bytes(
        _bytes(dict(body, withdrawal_id=identity))
    )
    with pytest.raises(ProvisionRegistryRefused):
        result.require_current()
    assert result.source_bytes(version.version_id) is None
    assert result.registry.resolve(source.display_name).state is BindingState.NOT_FOUND


def test_missing_candidates_and_malformed_empty_metadata_are_not_green(tmp_path):
    value, _source, _version, _revision, _text, _members, _current, _snapshot, load = population(
        tmp_path
    )
    candidate_empty = copy.deepcopy(value)
    candidate_empty["revisions"] = []
    assert load(candidate_empty)[1].state is RegistryLoadState.NOT_ESTABLISHED
    candidate_empty["review_artifacts"] = ["../foreign.json"]
    assert load(candidate_empty)[1].state is RegistryLoadState.REFUSED


def test_registry_declared_as_source_instead_of_artefact_is_refused(tmp_path):
    value, *_rest, snapshot, _load = population(tmp_path)
    selected = snapshot(value)
    selected.manifest["sources"].append(selected.manifest["artefacts"].pop())
    result = load_provision_registry(
        selected, source_generation=selected.snapshot_id, generation_current=lambda *_: True
    )
    assert result.state is RegistryLoadState.REFUSED and result.registry is None


def test_unrelated_object_is_not_an_alternate_published_transport():
    class Other:
        def read(self, _member):
            pytest.fail("unknown transport must not be called")

    result = load_provision_registry(
        Other(), source_generation="generation", generation_current=lambda *_: True
    )
    assert result.state is RegistryLoadState.REFUSED and result.registry is None


@pytest.mark.parametrize("operation", ["source", "provision"])
@pytest.mark.parametrize("late", [False, True])
def test_before_and_after_binding_fence_returns_no_selection_or_exception(
    tmp_path, monkeypatch, operation, late
):
    _value, source, _version, revision, _text, _members, current, _snapshot, load = population(
        tmp_path
    )
    loaded = load()[1]
    method = "resolve" if operation == "source" else "resolve_provision_key"
    actual = getattr(SourceRegistry, method)

    def revoke(*args):
        result = actual(*args)
        current["value"] = False
        return result

    if late:
        monkeypatch.setattr(SourceRegistry, method, revoke)
    else:
        current["value"] = False
    if operation == "source":
        result = loaded.registry.resolve(source.display_name)
        assert result.state is BindingState.NOT_FOUND and not result.source_ids
    else:
        result = loaded.registry.resolve_provision_key(source.source_id, revision.section)
        assert result.state is ProvisionKeyState.NOT_FOUND and result.key is None
        assert not result.candidate_keys
