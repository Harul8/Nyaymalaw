"""Import one optional, published candidate registry; never issue a review.

Publication owns the bytes.  This loader owns a closed metadata contract and
reconciles it to that exact held generation, not to retrieval summaries.  A
loaded candidate still needs the separate authenticated revision-review owner.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, fields
from datetime import date
from enum import Enum
from typing import Callable

from nm.legal_brain.common.citation_contracts import ProvisionKeyBinding, ProvisionKeyState
from nm.legal_brain.retrieve.manifest_sources import CorpusPublicationRefused, PublishedCorpus
from nm.legal_brain.retrieve.provenance_sources import Standing, Treatment
from nm.legal_brain.retrieve.provision_revision_sources import (
    AuthorityRole,
    AuthoritySpan,
    ProvisionRevision,
    RevisionKind,
    RevisionSelection,
    SelectionState,
    SourceBytes,
    TransitionState,
    _digest,
    _wire,
)
from nm.legal_brain.retrieve.source_registry_sources import (
    BindingResult,
    BindingState,
    CanonicalSource,
    LegalReview,
    ReviewState,
    RightsReview,
    RightsState,
    SourceKind,
    SourceRegistry,
    SourceVersion,
    _identity_part,
)
from nm.shared.json_values import same_json_value

REGISTRY_MEMBER = "registry/provision-revisions.json"
MAX_REGISTRY_BYTES = 16 * 1024 * 1024
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_POPULATION = 50_000
MAX_REVISIONS = 20_000
MAX_REVIEW_ARTIFACTS = 256
MAX_TEXT = 4096
MAX_AUTHORITIES = 64
GenerationCurrent = Callable[[str, str], bool]


class RegistryLoadState(str, Enum):
    LOADED = "loaded"
    NOT_ESTABLISHED = "not_established"
    REFUSED = "refused"


class ProvisionRegistryRefused(ValueError):
    """Expected absent, changed or malformed metadata, never legal approval."""


@dataclass(frozen=True)
class ProvisionRegistryLoad:
    state: RegistryLoadState
    reason: str
    registry: SourceRegistry | None = None
    review_artifact_refs: tuple[str, ...] = ()
    metadata_identity: str = ""
    source_bytes: SourceBytes | None = None
    current: Callable[[], None] | None = None

    def require_current(self) -> None:
        if self.state is not RegistryLoadState.LOADED or self.current is None:
            raise ProvisionRegistryRefused("provision registry metadata is not established")
        self.current()


def _object(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ProvisionRegistryRefused("registry object has missing or unknown fields")
    return value


def _text(value, *, blank=False):
    if type(value) is not str or len(value) > MAX_TEXT or (not blank and not value.strip()):
        raise ProvisionRegistryRefused("registry text is untyped, blank or unbounded")
    return value


def _day(value, *, nullable=False):
    if nullable and value is None:
        return None
    if type(value) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ProvisionRegistryRefused("registry date must be exact ISO calendar text")
    result = date.fromisoformat(value)
    if result.isoformat() != value:
        raise ProvisionRegistryRefused("registry date is not canonical")
    return result


def _enum(kind, value):
    return kind(_text(value))


def _array(value, maximum=None):
    maximum = MAX_POPULATION if maximum is None else maximum
    if type(value) is not list or len(value) > maximum:
        raise ProvisionRegistryRefused("registry population is untyped or unbounded")
    return value


def _texts(value):
    result = tuple(_text(item) for item in _array(value, MAX_AUTHORITIES))
    if len(result) != len(set(result)):
        raise ProvisionRegistryRefused("registry text population is duplicated")
    return result


def _source(value):
    row = _object(value, (field.name for field in fields(CanonicalSource)))
    return CanonicalSource(
        _enum(SourceKind, row["kind"]),
        *(
            _text(row[key])
            for key in ("jurisdiction", "issuing_body", "official_identifier", "display_name")
        ),
    )


def _version(value, sources):
    row = _object(value, (field.name for field in fields(SourceVersion)))
    source = _source(row["source"])
    if sources.get(source.source_id) != source:
        raise ProvisionRegistryRefused(
            "version source differs from the complete canonical population"
        )
    rights = _object(row["rights"], (field.name for field in fields(RightsReview)))
    legal = _object(row["legal_review"], (field.name for field in fields(LegalReview)))
    digest = legal["authority_digest"]
    if digest is not None:
        digest = _text(digest)
    return SourceVersion(
        source,
        _text(row["content_sha256"]),
        _text(row["language"]),
        _day(row["observed_at"]),
        RightsReview(
            _enum(RightsState, rights["state"]),
            _text(rights["basis"], blank=True),
            _day(rights["reviewed_at"], nullable=True),
        ),
        LegalReview(
            _enum(ReviewState, legal["state"]),
            _day(legal["reviewed_at"], nullable=True),
            _day(legal["valid_until"], nullable=True),
            digest,
            _text(legal["reason"], blank=True),
        ),
        _enum(Standing, row["standing"]),
        _enum(Treatment, row["treatment"]),
        _day(row["effective_from"], nullable=True),
        _day(row["source_date"], nullable=True),
        _texts(row["amended_by"]),
        _texts(row["supported_coverage"]),
        _texts(row["reservations"]),
    )


def _span(value):
    row = _object(value, (field.name for field in fields(AuthoritySpan)))
    if (
        type(row["start"]) is not int
        or type(row["end"]) is not int
        or row["end"] > MAX_SOURCE_BYTES
    ):
        raise ProvisionRegistryRefused("authority offsets are untyped or unbounded")
    return AuthoritySpan(
        _text(row["version_id"]),
        _text(row["locator"]),
        row["start"],
        row["end"],
        _enum(AuthorityRole, row["role"]),
    )


def _revision(value):
    row = _object(value, (field.name for field in fields(ProvisionRevision)))
    revision = ProvisionRevision(
        _text(row["source_id"]),
        _text(row["section"]),
        _span(row["wording"]),
        _enum(RevisionKind, row["kind"]),
        _day(row["effective_from"]),
        _day(row["effective_until"], nullable=True),
        _day(row["verified_through"]),
        tuple(_span(item) for item in _array(row["commencement"], MAX_AUTHORITIES)),
        tuple(_span(item) for item in _array(row["ending"], MAX_AUTHORITIES)),
        _enum(TransitionState, row["transition"]),
        tuple(_span(item) for item in _array(row["transition_authorities"], MAX_AUTHORITIES)),
        _text(row["reservation"], blank=True),
    )
    if not same_json_value(revision.as_record(), value):
        raise ProvisionRegistryRefused("revision record cannot round-trip exactly")
    return revision


def _review_ref(value):
    value = _text(value)
    # This is the sole bootstrap-owned namespace, not an arbitrary model path.
    if not value.startswith("docs/backlog/evidence/") or "\\" in value:
        raise ProvisionRegistryRefused("review reference is outside its fixed owner namespace")
    parts = value.split("/")
    if (
        len(parts) < 4
        or any(part in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts)
        or not parts[-1].endswith(".json")
    ):
        raise ProvisionRegistryRefused("review reference is not a bounded relative JSON identity")
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProvisionRegistryRefused("registry JSON keys are duplicated")
        result[key] = value
    return result


def _constant(_value):
    raise ProvisionRegistryRefused("registry JSON contains a non-finite constant")


def _fingerprint(registry):
    return _digest(
        {
            "sources": registry._sources,
            "versions": registry._versions,
            "aliases": {key: sorted(value) for key, value in registry._aliases.items()},
            "legacy": {key: sorted(value) for key, value in registry._legacy.items()},
            "revisions": registry._provision_revisions,
        }
    )


class _PublishedRegistry(SourceRegistry):
    """Actual registry owners, frozen after import and fenced on consumption."""

    def __init__(self):
        super().__init__()
        self._fence = None
        self._source_owner = None
        self._source_reader = None

    def _mutable(self):
        if self._fence is not None:
            raise ProvisionRegistryRefused("published registry metadata is immutable")

    def register_source(self, source):
        self._mutable()
        return super().register_source(source)

    def register_version(self, version):
        self._mutable()
        return super().register_version(version)

    def bind_alias(self, alias, source_id):
        self._mutable()
        return super().bind_alias(alias, source_id)

    def bind_legacy_locator(self, locator, source_id):
        self._mutable()
        return super().bind_legacy_locator(locator, source_id)

    def register_provision_revision(self, revision):
        self._mutable()
        return super().register_provision_revision(revision)

    def resolve(self, reference):
        try:
            self._fence()
            result = super().resolve(reference)
            self._fence()
            return result
        except ProvisionRegistryRefused:
            return BindingResult(
                reference,
                BindingState.NOT_FOUND,
                (),
                "published provision registry is no longer current",
            )

    def resolve_provision_key(self, source_id, reference):
        try:
            self._fence()
            result = super().resolve_provision_key(source_id, reference)
            self._fence()
            return result
        except ProvisionRegistryRefused:
            return ProvisionKeyBinding(
                reference,
                ProvisionKeyState.NOT_FOUND,
                None,
                (),
                "published provision registry is no longer current",
            )

    def provision_revisions(self):
        self._fence()
        return super().provision_revisions()

    def _bound_reader(self, supplied):
        if (
            supplied is not None
            and supplied is not self._source_reader
            and not (type(supplied) is type(self._source_owner) and supplied == self._source_owner)
        ):
            raise ProvisionRegistryRefused("revision source transport is not the published owner")
        return self._source_reader

    def select_provision_revision(self, source_id, section, as_of, **kwargs):
        try:
            self._fence()
            kwargs["source_bytes"] = self._bound_reader(kwargs.get("source_bytes"))
            result = super().select_provision_revision(source_id, section, as_of, **kwargs)
            self._fence()
            return result
        except ProvisionRegistryRefused:
            return RevisionSelection(
                SelectionState.REFUSED,
                source_id,
                section,
                as_of,
                "published provision registry is no longer current",
            )

    def read_revision_authority(self, span, *, source_bytes):
        self._fence()
        result = super().read_revision_authority(
            span, source_bytes=self._bound_reader(source_bytes)
        )
        self._fence()
        return result

    def read_revision_source(self, subject_id, *, source_bytes):
        self._fence()
        result = super().read_revision_source(
            subject_id, source_bytes=self._bound_reader(source_bytes)
        )
        self._fence()
        return result

    def readiness(self, *args, **kwargs):
        self._fence()
        return super().readiness(*args, **kwargs)

    def as_dict(self, *, as_of):
        self._fence()
        result = super().as_dict(as_of=as_of)
        self._fence()
        return result


def load_provision_registry(
    snapshot: PublishedCorpus | None,
    *,
    source_generation: str,
    generation_current: GenerationCurrent,
) -> ProvisionRegistryLoad:
    """Read a fixed optional published artefact, without writing any authority.

    The host callback compares the captured generation/metadata identity with
    its current owner.  Independent publication withdrawal and byte checks run
    here even when that callback still returns True.  No source path is input.
    """
    if snapshot is None:
        return ProvisionRegistryLoad(
            RegistryLoadState.NOT_ESTABLISHED, "published provision registry is unavailable"
        )
    try:
        if type(snapshot) is not PublishedCorpus or not callable(generation_current):
            raise ProvisionRegistryRefused("registry requires its actual published snapshot owner")
        _text(source_generation)
        snapshot.require_usable()
        if not snapshot.has_member(REGISTRY_MEMBER):
            return ProvisionRegistryLoad(
                RegistryLoadState.NOT_ESTABLISHED, "optional published provision registry is absent"
            )
        artefacts = snapshot.manifest["artefacts"]
        matches = [
            row for row in artefacts if type(row) is dict and row.get("path") == REGISTRY_MEMBER
        ]
        if (
            len(matches) != 1
            or type(matches[0].get("bytes")) is not int
            or not 0 < matches[0]["bytes"] <= MAX_REGISTRY_BYTES
        ):
            raise ProvisionRegistryRefused("registry is not one bounded published artefact")
        raw = snapshot.read(REGISTRY_MEMBER)
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_REGISTRY_BYTES:
            raise ProvisionRegistryRefused("registry bytes are untyped, empty or unbounded")
        value = json.loads(raw.decode("utf8"), object_pairs_hook=_pairs, parse_constant=_constant)
        _object(
            value, {"schema", "sources", "versions", "aliases", "revisions", "review_artifacts"}
        )
        if type(value["schema"]) is not int or value["schema"] != 1:
            raise ProvisionRegistryRefused("registry schema is not exact version one")
        source_rows = _array(value["sources"])
        version_rows = _array(value["versions"])
        revision_rows = _array(value["revisions"], MAX_REVISIONS)
        alias_rows = _array(value["aliases"])
        review_rows = _array(value["review_artifacts"], MAX_REVIEW_ARTIFACTS)
        if not any((source_rows, version_rows, revision_rows, alias_rows, review_rows)):
            return ProvisionRegistryLoad(
                RegistryLoadState.NOT_ESTABLISHED,
                "published provision registry candidate population is empty",
            )
        if not source_rows or not version_rows:
            raise ProvisionRegistryRefused("registry has incomplete source/version populations")
        registry = _PublishedRegistry()
        sources = {}
        for row in source_rows:
            source = _source(row)
            if source.source_id in sources:
                raise ProvisionRegistryRefused("canonical source population is duplicated")
            sources[registry.register_source(source)] = source
        versions = {}
        for row in version_rows:
            version = _version(row, sources)
            if not same_json_value(_wire(version), row) or version.version_id in versions:
                raise ProvisionRegistryRefused(
                    "version population is duplicated or not exactly typed"
                )
            versions[registry.register_version(version)] = version
        if {version.source.source_id for version in versions.values()} != set(sources):
            raise ProvisionRegistryRefused(
                "canonical source and version populations do not reconcile"
            )
        held = _array(snapshot.manifest["sources"])
        expected = _array(snapshot.manifest["expected_versions"])
        held_ids = [row.get("version_id") for row in held if type(row) is dict]
        if (
            len(held_ids) != len(held)
            or len(set(held_ids)) != len(held)
            or len(expected) != len(set(expected))
            or set(held_ids) != set(expected)
            or set(versions) != set(held_ids)
        ):
            raise ProvisionRegistryRefused(
                "registry versions do not reconcile exact held published population"
            )
        for row in held:
            version = versions[row["version_id"]]
            if (
                row.get("source_id") != version.source.source_id
                or row.get("sha256") != version.content_sha256
            ):
                raise ProvisionRegistryRefused(
                    "registry source identity or digest differs from publication"
                )
        seen_aliases = set()
        for row in alias_rows:
            _object(row, {"reference", "source_id"})
            reference, source_id = _text(row["reference"]), _text(row["source_id"])
            alias = (_identity_part(reference), source_id)
            if alias in seen_aliases or source_id not in sources:
                raise ProvisionRegistryRefused("alias is duplicated or targets an unheld source")
            seen_aliases.add(alias)
            registry.bind_alias(reference, source_id)
        seen_revisions = set()
        for row in revision_rows:
            revision = _revision(row)
            if revision.subject_id in seen_revisions:
                raise ProvisionRegistryRefused("revision candidate population is duplicated")
            seen_revisions.add(revision.subject_id)
            registry.register_provision_revision(revision)
        refs = tuple(_review_ref(item) for item in review_rows)
        if len(refs) != len(set(refs)):
            raise ProvisionRegistryRefused("review artifact references are duplicated")
        manifest_identity = _digest(snapshot.manifest)
        metadata_identity = _digest(
            {
                "snapshot": snapshot.snapshot_id,
                "manifest": manifest_identity,
                "registry_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        registry_identity = _fingerprint(registry)

        def require_current():
            try:
                if (
                    generation_current(source_generation, metadata_identity) is not True
                    or _digest(snapshot.manifest) != manifest_identity
                    or _fingerprint(registry) != registry_identity
                ):
                    raise ProvisionRegistryRefused(
                        "published registry generation or metadata changed"
                    )
                snapshot.require_usable()
                if snapshot.read(REGISTRY_MEMBER) != raw:
                    raise ProvisionRegistryRefused("published registry bytes changed")
                if generation_current(source_generation, metadata_identity) is not True:
                    raise ProvisionRegistryRefused(
                        "published registry generation changed during read"
                    )
            except (CorpusPublicationRefused, OSError) as exc:
                raise ProvisionRegistryRefused("published registry is no longer usable") from exc

        def source_bytes(version_id):
            try:
                require_current()
                if type(version_id) is not str or version_id not in versions:
                    return None
                matching = [row for row in held if row["version_id"] == version_id]
                if (
                    len(matching) != 1
                    or type(matching[0].get("bytes")) is not int
                    or not 0 <= matching[0]["bytes"] <= MAX_SOURCE_BYTES
                ):
                    raise ProvisionRegistryRefused(
                        "revision source is outside the bounded held population"
                    )
                payload = snapshot.get_source(version_id)
                if (
                    type(payload) is not bytes
                    or len(payload) > MAX_SOURCE_BYTES
                    or hashlib.sha256(payload).hexdigest() != versions[version_id].content_sha256
                ):
                    raise ProvisionRegistryRefused(
                        "revision source bytes differ from their exact version"
                    )
                require_current()
                return payload
            except (ProvisionRegistryRefused, CorpusPublicationRefused, OSError):
                return None

        registry._source_owner = snapshot.get_source
        registry._source_reader = source_bytes
        registry._fence = require_current
        require_current()
        if not revision_rows:
            return ProvisionRegistryLoad(
                RegistryLoadState.NOT_ESTABLISHED,
                "published source metadata holds no provision revision candidates",
            )
        return ProvisionRegistryLoad(
            RegistryLoadState.LOADED,
            "candidate metadata loaded; qualified interval review "
            "and matter applicability are separate",
            registry,
            refs,
            metadata_identity,
            source_bytes,
            require_current,
        )
    except (
        ProvisionRegistryRefused,
        CorpusPublicationRefused,
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        RecursionError,
        OSError,
    ):
        return ProvisionRegistryLoad(
            RegistryLoadState.REFUSED,
            "published provision registry metadata is malformed, changed or unusable",
        )
