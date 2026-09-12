"""Governed identities for legal sources and bounded source inventory.

This module owns source-publication identity.  The existing ``Manifest`` owns
the runtime's intended Act coverage until P20 performs a controlled cutover;
neither is inferred from search results or file names.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Iterable

from nm.domain.text import refuses_blank_text
from nm.knowledge.provenance import Standing, Treatment


class AssetKind(str, Enum):
    ORIGINAL = "original"
    RENDITION = "rendition"
    PROJECTION = "projection"
    BACKUP = "backup"
    PRIVATE = "private"
    UNKNOWN = "unknown"


class Assessment(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NOT_ASSESSED = "not_assessed"


class DigestState(str, Enum):
    VERIFIED = "verified"
    NOT_ASSESSED = "not_assessed"
    UNREADABLE = "unreadable"
    EXCLUDED = "excluded"


@refuses_blank_text()
@dataclass(frozen=True)
class AssetRecord:
    path: str
    kind: AssetKind
    size: int | None
    sha256: str | None
    digest_state: DigestState
    duplicate_of: str | None = None
    note: str = ""


@refuses_blank_text()
@dataclass(frozen=True)
class ConsumerRecord:
    path: str
    line: int
    reference: str


@refuses_blank_text()
@dataclass(frozen=True)
class InventoryReport:
    requested_root: str
    resolved_root: str | None
    observed_at: str
    status: Assessment
    entries_seen: int
    files_reported: int
    private_exclusions: int
    unreadable: int
    unhashed: int
    assets: tuple[AssetRecord, ...] = ()
    consumers: tuple[ConsumerRecord, ...] = ()
    reservations: tuple[str, ...] = ()
    schema: int = 1

    def as_dict(self) -> dict:
        def value(item):
            if isinstance(item, Enum):
                return item.value
            if isinstance(item, tuple):
                return [value(member) for member in item]
            if hasattr(item, "__dataclass_fields__"):
                return {key: value(member) for key, member in asdict(item).items()}
            if isinstance(item, dict):
                return {key: value(member) for key, member in item.items()}
            return item

        return value(self)


_PRIVATE_PARTS = {"chat_history", "matter_data", "client_data"}
_BACKUP_PARTS = {"backup", "backups", "_duplicates_archived"}
_PROJECTION_SUFFIXES = {
    ".db", ".sqlite", ".sqlite3", ".index", ".faiss", ".npy", ".npz"
}
_CONSUMER_SUFFIXES = {".py", ".js", ".mjs", ".ts"}


def classify_asset(relative: Path) -> AssetKind:
    """Classify by declared storage role, never by inferred legal authority."""
    parts = {part.casefold() for part in relative.parts}
    name = relative.name.casefold()
    if parts & _PRIVATE_PARTS:
        return AssetKind.PRIVATE
    if parts & _BACKUP_PARTS or name.endswith((".bak", ".backup", ".pre_dedup")):
        return AssetKind.BACKUP
    if "originals" in parts:
        return AssetKind.ORIGINAL
    if "raw_data" in parts:
        # The inspected collection includes third-party navigation text.  Raw
        # means upstream input here; it does not establish an official original.
        return AssetKind.RENDITION
    if "vector_store" in parts or relative.suffix.casefold() in _PROJECTION_SUFFIXES:
        return AssetKind.PROJECTION
    return AssetKind.UNKNOWN


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_entries(root: Path) -> Iterable[tuple[Path, bool]]:
    """Yield deterministically without following links below the selected root."""
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories.sort(key=str.casefold)
        files.sort(key=str.casefold)
        for name in tuple(directories):
            path = Path(current, name)
            yield path, True
            if classify_asset(path.relative_to(root)) is AssetKind.PRIVATE:
                directories.remove(name)
        for name in files:
            yield Path(current, name), False


def find_consumers(root: Path, terms: Iterable[str]) -> tuple[ConsumerRecord, ...]:
    """Report code references to storage names; the report is not call-graph proof."""
    wanted = tuple(sorted({term for term in terms if term.strip()}))
    found: list[ConsumerRecord] = []
    if not root.is_dir() or not wanted:
        return ()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.casefold() not in _CONSUMER_SUFFIXES:
            continue
        try:
            lines = path.read_text(encoding="utf8").splitlines()
        except (OSError, UnicodeError):
            continue
        for number, line in enumerate(lines, 1):
            for term in wanted:
                if term in line:
                    found.append(ConsumerRecord(
                        path=path.relative_to(root).as_posix(),
                        line=number,
                        reference=term,
                    ))
    return tuple(found)


def inventory_sources(
    root: str | Path,
    *,
    observed_at: datetime,
    max_entries: int = 10_000,
    max_hash_bytes: int = 16 * 1024 * 1024,
    consumer_root: str | Path | None = None,
    consumer_terms: Iterable[str] = (),
    cancel_after: int | None = None,
) -> InventoryReport:
    """Inspect a bounded file population and make every unassessed state visible."""
    requested = Path(root)
    try:
        resolved = requested.resolve(strict=True)
    except OSError as exc:
        return InventoryReport(
            requested_root=str(requested), resolved_root=None,
            observed_at=observed_at.isoformat(), status=Assessment.NOT_ASSESSED,
            entries_seen=0, files_reported=0, private_exclusions=0,
            unreadable=0, unhashed=0,
            reservations=(f"root unavailable: {type(exc).__name__}",),
        )
    if not resolved.is_dir():
        return InventoryReport(
            requested_root=str(requested), resolved_root=str(resolved),
            observed_at=observed_at.isoformat(), status=Assessment.NOT_ASSESSED,
            entries_seen=0, files_reported=0, private_exclusions=0,
            unreadable=0, unhashed=0,
            reservations=("selected root is not a directory",),
        )
    if max_entries < 1 or max_hash_bytes < 0 or (
            cancel_after is not None and cancel_after < 0):
        raise ValueError("inventory bounds must be non-negative and max_entries positive")

    records: list[AssetRecord] = []
    reservations: list[str] = []
    seen = private = unreadable = unhashed = 0
    status = Assessment.COMPLETE
    digests: dict[str, str] = {}
    try:
        for path, is_directory in _iter_entries(resolved):
            seen += 1
            relative = path.relative_to(resolved)
            if cancel_after is not None and seen > cancel_after:
                status = Assessment.PARTIAL
                reservations.append(f"scan cancelled after {seen - 1} entries")
                break
            if seen > max_entries:
                status = Assessment.PARTIAL
                reservations.append(f"entry limit {max_entries} reached")
                break
            kind = classify_asset(relative)
            if is_directory:
                if kind is AssetKind.PRIVATE:
                    private += 1
                    records.append(AssetRecord(
                        relative.as_posix(), kind, None, None,
                        DigestState.EXCLUDED, note="contents deliberately not inspected",
                    ))
                continue
            if kind is AssetKind.PRIVATE:
                private += 1
                records.append(AssetRecord(
                    relative.as_posix(), kind, None, None,
                    DigestState.EXCLUDED, note="private content deliberately not opened",
                ))
                continue
            try:
                size = path.stat().st_size
                if size > max_hash_bytes:
                    unhashed += 1
                    records.append(AssetRecord(
                        relative.as_posix(), kind, size, None,
                        DigestState.NOT_ASSESSED,
                        note=f"larger than hash bound {max_hash_bytes}",
                    ))
                    continue
                digest = _sha256(path)
            except OSError as exc:
                unreadable += 1
                status = Assessment.PARTIAL
                records.append(AssetRecord(
                    relative.as_posix(), kind, None, None,
                    DigestState.UNREADABLE, note=type(exc).__name__,
                ))
                continue
            duplicate = digests.setdefault(digest, relative.as_posix())
            records.append(AssetRecord(
                relative.as_posix(), kind, size, digest, DigestState.VERIFIED,
                duplicate_of=(duplicate if duplicate != relative.as_posix() else None),
            ))
    except OSError as exc:
        status = Assessment.PARTIAL
        reservations.append(f"directory traversal failed: {type(exc).__name__}")

    if not records and status is Assessment.COMPLETE:
        status = Assessment.NOT_ASSESSED
        reservations.append("selected root contained no assessable entries")
    consumers = find_consumers(Path(consumer_root), consumer_terms) if consumer_root else ()
    return InventoryReport(
        requested_root=str(requested), resolved_root=str(resolved),
        observed_at=observed_at.isoformat(), status=status,
        entries_seen=seen,
        files_reported=sum(
            row.size is not None or row.digest_state is DigestState.UNREADABLE
            for row in records
        ),
        private_exclusions=private, unreadable=unreadable, unhashed=unhashed,
        assets=tuple(records), consumers=consumers,
        reservations=tuple(reservations),
    )
class SourceKind(str, Enum):
    INSTRUMENT = "instrument"
    JUDGMENT = "judgment"


class RightsState(str, Enum):
    PERMITTED = "permitted"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


class ReviewState(str, Enum):
    APPROVED = "approved"
    UNREVIEWED = "unreviewed"
    STALE = "stale"
    REFUSED = "refused"

    @classmethod
    def not_established(cls) -> "ReviewState":
        """No qualified review has reached a conclusion."""
        return cls.UNREVIEWED


class BindingState(str, Enum):
    BOUND = "bound"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


class PublicationState(str, Enum):
    READY = "ready"
    CANDIDATE = "candidate"
    NOT_ASSESSED = "not_assessed"
    REFUSED = "refused"


_DIGEST = re.compile(r"[0-9a-f]{64}")


def _identity_part(value: str) -> str:
    """Normalise typography without fuzzy or punctuation-erasing identity."""
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _stable_id(prefix: str, payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()}"


@refuses_blank_text()
@dataclass(frozen=True)
class CanonicalSource:
    """A legal source identity, separate from every downloaded version."""

    kind: SourceKind
    jurisdiction: str
    issuing_body: str
    official_identifier: str
    display_name: str

    @property
    def source_id(self) -> str:
        return _stable_id("src", {
            "kind": self.kind.value,
            "jurisdiction": _identity_part(self.jurisdiction),
            "issuing_body": _identity_part(self.issuing_body),
            "official_identifier": _identity_part(self.official_identifier),
        })


@refuses_blank_text("basis")
@dataclass(frozen=True)
class RightsReview:
    state: RightsState
    basis: str = ""
    reviewed_at: date | None = None

    def __post_init__(self) -> None:
        if self.state is not RightsState.UNKNOWN and not self.basis.strip():
            raise ValueError("a determined rights state requires its basis")


@refuses_blank_text("reason")
@dataclass(frozen=True)
class LegalReview:
    state: ReviewState
    reviewed_at: date | None = None
    valid_until: date | None = None
    authority_digest: str | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.authority_digest is not None and not _DIGEST.fullmatch(
                self.authority_digest):
            raise ValueError("authority_digest must be a full lowercase sha256")
        if self.state is ReviewState.APPROVED:
            missing = [
                name for name, value in (
                    ("reviewed_at", self.reviewed_at),
                    ("valid_until", self.valid_until),
                    ("authority_digest", self.authority_digest),
                ) if value is None
            ]
            if missing:
                raise ValueError(
                    "an approved legal review requires " + ", ".join(missing)
                )
            if self.valid_until < self.reviewed_at:  # type: ignore[operator]
                raise ValueError("legal review cannot expire before it was made")
        if self.state is ReviewState.REFUSED and not self.reason.strip():
            raise ValueError("a refused legal review requires its reason")


@refuses_blank_text()
@dataclass(frozen=True)
class SourceVersion:
    """One byte-exact version plus the legal metadata needed to assess it."""

    source: CanonicalSource
    content_sha256: str
    language: str
    observed_at: date
    rights: RightsReview
    legal_review: LegalReview
    standing: Standing = Standing.UNDETERMINED
    treatment: Treatment = Treatment.UNDETERMINED
    effective_from: date | None = None
    source_date: date | None = None
    amended_by: tuple[str, ...] = ()
    supported_coverage: tuple[str, ...] = ()
    reservations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _DIGEST.fullmatch(self.content_sha256):
            raise ValueError("content_sha256 must be a full lowercase sha256")

    @property
    def version_id(self) -> str:
        return _stable_id("ver", {
            "source_id": self.source.source_id,
            "content_sha256": self.content_sha256,
            "language": _identity_part(self.language),
            "observed_at": self.observed_at.isoformat(),
            "effective_from": (
                self.effective_from.isoformat() if self.effective_from else None
            ),
            "source_date": self.source_date.isoformat() if self.source_date else None,
            "standing": self.standing.value,
            "treatment": self.treatment.value,
        })


@refuses_blank_text()
@dataclass(frozen=True)
class BindingResult:
    reference: str
    state: BindingState
    source_ids: tuple[str, ...]
    reason: str


@refuses_blank_text()
@dataclass(frozen=True)
class ReadinessReport:
    source_id: str
    version_id: str
    state: PublicationState
    reasons: tuple[str, ...]
    checked_sha256: str | None


class SourceRegistry:
    """Canonical sources, versions and explicit non-authoritative locators."""

    def __init__(self) -> None:
        self._sources: dict[str, CanonicalSource] = {}
        self._versions: dict[str, SourceVersion] = {}
        self._aliases: dict[str, set[str]] = {}
        self._legacy: dict[str, set[str]] = {}

    def register_source(self, source: CanonicalSource) -> str:
        source_id = source.source_id
        existing = self._sources.get(source_id)
        if existing is not None and existing != source:
            raise ValueError("canonical source id collision")
        self._sources[source_id] = source
        return source_id

    def register_version(self, version: SourceVersion) -> str:
        source_id = self.register_source(version.source)
        if source_id != version.source.source_id:
            raise AssertionError("registered source identity changed")
        version_id = version.version_id
        existing = self._versions.get(version_id)
        if existing is not None and existing != version:
            raise ValueError("source version id collision")
        self._versions[version_id] = version
        return version_id

    def bind_alias(self, alias: str, source_id: str) -> BindingResult:
        return self._bind(self._aliases, alias, source_id, "alias")

    def bind_legacy_locator(self, locator: str, source_id: str) -> BindingResult:
        return self._bind(self._legacy, locator, source_id, "legacy locator")

    def _bind(
        self,
        bindings: dict[str, set[str]],
        reference: str,
        source_id: str,
        label: str,
    ) -> BindingResult:
        if not reference.strip():
            raise ValueError(f"{label} carries nothing")
        if source_id not in self._sources:
            return BindingResult(
                reference, BindingState.NOT_FOUND, (),
                f"{label} target is not a registered canonical source",
            )
        key = _identity_part(reference)
        targets = bindings.setdefault(key, set())
        targets.add(source_id)
        ordered = tuple(sorted(targets))
        if len(ordered) > 1:
            return BindingResult(
                reference, BindingState.AMBIGUOUS, ordered,
                f"{label} maps to more than one canonical source; no target selected",
            )
        return BindingResult(
            reference, BindingState.BOUND, ordered,
            f"{label} resolves to one canonical source",
        )

    def resolve(self, reference: str) -> BindingResult:
        if not reference.strip():
            raise ValueError("source reference carries nothing")
        if reference in self._sources:
            return BindingResult(
                reference, BindingState.BOUND, (reference,),
                "reference is an exact canonical source id",
            )
        key = _identity_part(reference)
        targets = set(self._aliases.get(key, ())) | set(self._legacy.get(key, ()))
        ordered = tuple(sorted(targets))
        if not ordered:
            return BindingResult(
                reference, BindingState.NOT_FOUND, (),
                "reference is not a canonical id, alias or registered legacy locator",
            )
        if len(ordered) > 1:
            return BindingResult(
                reference, BindingState.AMBIGUOUS, ordered,
                "reference has conflicting bindings; no target selected",
            )
        return BindingResult(
            reference, BindingState.BOUND, ordered,
            "reference resolves through an explicit registered binding",
        )

    def readiness(
        self,
        version_id: str,
        *,
        content: bytes | None,
        as_of: date,
        binding_on: str | None = None,
    ) -> ReadinessReport:
        version = self._versions.get(version_id)
        if version is None:
            return ReadinessReport(
                "unknown", version_id, PublicationState.NOT_ASSESSED,
                ("version is not registered",), None,
            )
        checked = hashlib.sha256(content).hexdigest() if content is not None else None
        reasons: list[str] = []
        refused: list[str] = []
        not_assessed: list[str] = []

        if checked is None:
            not_assessed.append("source bytes were not supplied for digest verification")
        elif checked != version.content_sha256:
            refused.append(
                "supplied bytes do not match the registered source version digest"
            )
        if version.rights.state is RightsState.RESTRICTED:
            refused.append(f"source rights prohibit publication: {version.rights.basis}")
        elif version.rights.state is RightsState.UNKNOWN:
            reasons.append("source publication rights have not been established")

        review = version.legal_review
        if review.state is ReviewState.REFUSED:
            refused.append(f"legal review refused this version: {review.reason}")
        elif review.state is ReviewState.UNREVIEWED:
            reasons.append("qualified legal review has not been completed")
        elif review.state is ReviewState.STALE:
            not_assessed.append("the recorded legal review is stale")
        elif review.valid_until is not None and review.valid_until < as_of:
            not_assessed.append(
                f"legal review expired on {review.valid_until.isoformat()}"
            )

        if version.source.kind is SourceKind.INSTRUMENT:
            if version.effective_from is None:
                reasons.append("instrument effective date is not recorded")
            elif version.effective_from > as_of:
                refused.append(
                    f"instrument takes effect on {version.effective_from.isoformat()}, "
                    f"after {as_of.isoformat()}"
                )
            if version.standing in {Standing.DRAFT, Standing.REPEALED}:
                refused.append(f"instrument standing is {version.standing.value}")
            elif version.standing is Standing.UNDETERMINED:
                reasons.append("instrument standing has not been established")
        elif version.source_date is None:
            reasons.append("judgment source date is not recorded")

        if binding_on is not None:
            if not version.supported_coverage:
                reasons.append("source declares no supported coverage")
            elif binding_on not in version.supported_coverage:
                refused.append(
                    f"source is not declared to support {binding_on!r}"
                )
        reasons.extend(version.reservations)

        if refused:
            state = PublicationState.REFUSED
            all_reasons = refused + not_assessed + reasons
        elif not_assessed:
            state = PublicationState.NOT_ASSESSED
            all_reasons = not_assessed + reasons
        elif reasons:
            state = PublicationState.CANDIDATE
            all_reasons = reasons
        else:
            state = PublicationState.READY
            all_reasons = []
        return ReadinessReport(
            version.source.source_id, version_id, state,
            tuple(all_reasons), checked,
        )

    def as_dict(self, *, as_of: date) -> dict:
        """Inspectable deterministic projection; it does not publish anything."""
        sources = [
            {
                **asdict(source),
                "kind": source.kind.value,
                "source_id": source_id,
            }
            for source_id, source in sorted(self._sources.items())
        ]
        versions = []
        for version_id, version in sorted(self._versions.items()):
            report = self.readiness(version_id, content=None, as_of=as_of)
            versions.append({
                "version_id": version_id,
                "source_id": version.source.source_id,
                "content_sha256": version.content_sha256,
                "language": version.language,
                "observed_at": version.observed_at.isoformat(),
                "effective_from": (
                    version.effective_from.isoformat()
                    if version.effective_from else None
                ),
                "source_date": (
                    version.source_date.isoformat() if version.source_date else None
                ),
                "rights": version.rights.state.value,
                "legal_review": version.legal_review.state.value,
                "readiness_without_bytes": report.state.value,
                "reservations": list(version.reservations),
            })
        def projected(bindings: dict[str, set[str]]) -> dict[str, list[str]]:
            return {
                key: sorted(targets) for key, targets in sorted(bindings.items())
            }
        return {
            "schema": 1,
            "sources": sources,
            "versions": versions,
            "aliases": projected(self._aliases),
            "legacy_locators": projected(self._legacy),
        }
