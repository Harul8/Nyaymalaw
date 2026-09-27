"""Date-qualified provision identities, distinct from Act lifetime metadata.

S11: a selected revision is bound to every held source digest and exact span.
S4: no qualified review is inferred from an author's metadata or from absence.
The trusted review lookup is a host-owned read of an authenticated artifact;
this module cannot produce, approve, persist or authenticate that artifact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from nm.legal_brain.retrieve.source_registry_sources import CanonicalSource, SourceVersion


def _wire(value):
    if isinstance(value, Enum):
        return value.value
    if type(value) is date:
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return _wire(asdict(value))
    if isinstance(value, dict):
        return {key: _wire(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_wire(item) for item in value]
    return value


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(_wire(value), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf8"
        )
    ).hexdigest()


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise ValueError(f"{label} must be nonblank text")


def _day(value, label, *, nullable=False):
    if nullable and value is None:
        return
    if type(value) is not date:
        raise ValueError(f"{label} must be a calendar date, without coercion")


class AuthorityRole(str, Enum):
    WORDING = "wording"
    ENACTMENT = "enactment"
    AMENDMENT = "amendment"
    COMMENCEMENT = "commencement"
    REPEAL = "repeal"
    TRANSITION = "transition"


class RevisionKind(str, Enum):
    ORIGINAL = "original"
    AMENDED = "amended"


class TransitionState(str, Enum):
    RESOLVED = "resolved"
    NOT_APPLICABLE = "not_applicable"
    NOT_ASSESSED = "not_assessed"


class SelectionState(str, Enum):
    SELECTED = "selected"
    NOT_ASSESSED = "not_assessed"
    REFUSED = "refused"


@dataclass(frozen=True)
class AuthoritySpan:
    version_id: str
    locator: str
    start: int
    end: int
    role: AuthorityRole

    def __post_init__(self):
        _text(self.version_id, "source version identity")
        _text(self.locator, "source locator")
        if (
            type(self.start) is not int
            or type(self.end) is not int
            or self.start < 0
            or self.end <= self.start
        ):
            raise ValueError("authority spans require exact nonempty integer offsets")
        if type(self.role) is not AuthorityRole:
            raise ValueError("authority span role is typed")


@dataclass(frozen=True)
class ProvisionRevision:
    source_id: str
    section: str
    wording: AuthoritySpan
    kind: RevisionKind
    effective_from: date
    effective_until: date | None
    verified_through: date
    commencement: tuple[AuthoritySpan, ...]
    ending: tuple[AuthoritySpan, ...]
    transition: TransitionState
    transition_authorities: tuple[AuthoritySpan, ...]
    reservation: str = ""

    def __post_init__(self):
        _text(self.source_id, "canonical source identity")
        _text(self.section, "exact provision key")
        if (
            type(self.wording) is not AuthoritySpan
            or self.wording.role is not AuthorityRole.WORDING
        ):
            raise ValueError("a revision requires one owned wording span")
        if type(self.kind) is not RevisionKind or type(self.transition) is not TransitionState:
            raise ValueError("revision and transition states are typed")
        for key in ("effective_from", "verified_through"):
            _day(getattr(self, key), key)
        _day(self.effective_until, "effective_until", nullable=True)
        if self.effective_until is not None and self.effective_until <= self.effective_from:
            raise ValueError("revision intervals are nonempty and half-open")
        if self.verified_through < self.effective_from:
            raise ValueError("verified coverage cannot end before commencement")
        for key in ("commencement", "ending", "transition_authorities"):
            values = getattr(self, key)
            if type(values) is not tuple or any(type(span) is not AuthoritySpan for span in values):
                raise ValueError("revision authorities are exact typed tuples")
            if len(set(values)) != len(values):
                raise ValueError("duplicate authority spans are ambiguous")
        if type(self.reservation) is not str:
            raise ValueError("revision reservation is text, not a coerced value")

    @property
    def spans(self) -> tuple[AuthoritySpan, ...]:
        return (self.wording,) + self.commencement + self.ending + self.transition_authorities

    @property
    def subject_id(self) -> str:
        return "provision_revision_" + _digest(self)

    def as_record(self) -> dict:
        return _wire(self)


@dataclass(frozen=True)
class HeldAuthoritySpan:
    authority: AuthoritySpan
    source_id: str
    content_sha256: str
    text: str
    source: CanonicalSource
    observed_at: date
    source_date: date | None

    def as_record(self) -> dict:
        return _wire(self)


@dataclass(frozen=True)
class RevisionReviewRequest:
    subject_id: str
    authority_digest: str
    version_ids: tuple[str, ...]
    checked_at: date


@dataclass(frozen=True)
class RevisionQualification:
    """Read-only provenance of the actual signed review and issuer grant.

    This is an adapted receipt, never a signing or qualification mechanism.
    The bootstrap owner must authenticate the original artifacts each lookup.
    """

    person_id: str
    display_name: str
    role: str
    basis: str
    configuration_identity: str
    record_ref: str
    record_sha256: str
    attestation_ref: str
    attestation_sha256: str
    authority_ref: str
    authority_sha256: str
    issuer_ids: tuple[str, ...]
    grant_payload_json: str
    observed_at: str
    valid_until: str

    def __post_init__(self):
        for key in self.__dataclass_fields__:
            if key != "issuer_ids":
                _text(getattr(self, key), key)
        for key in ("record_sha256", "attestation_sha256", "authority_sha256"):
            value = getattr(self, key)
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError("qualified artifact digests must be lowercase sha256")
        if (
            type(self.issuer_ids) is not tuple
            or not self.issuer_ids
            or any(type(value) is not str or not value.strip() for value in self.issuer_ids)
            or tuple(sorted(set(self.issuer_ids))) != self.issuer_ids
        ):
            raise ValueError("qualification requires the exact authenticated issuer population")


@dataclass(frozen=True)
class RevisionApproval:
    """Receipt returned only by the trusted authenticated review-artifact owner.

    Having this type alone grants nothing. Selection also requires a host
    lookup and exact equality with the reconstructed subject and proof set.
    Withdrawal must cause that owner to return None on the next lookup.
    """

    receipt_id: str
    owner_id: str
    subject_id: str
    authority_digest: str
    version_ids: tuple[str, ...]
    reviewed_at: date
    valid_until: date
    qualification: RevisionQualification | None = None

    def __post_init__(self):
        for key in ("receipt_id", "owner_id", "subject_id", "authority_digest"):
            _text(getattr(self, key), key)
        if len(self.authority_digest) != 64 or any(
            char not in "0123456789abcdef" for char in self.authority_digest
        ):
            raise ValueError("review authority digest must be lowercase sha256")
        if (
            type(self.version_ids) is not tuple
            or not self.version_ids
            or any(type(value) is not str or not value.strip() for value in self.version_ids)
            or tuple(sorted(set(self.version_ids))) != self.version_ids
        ):
            raise ValueError("review versions are the exact sorted distinct population")
        _day(self.reviewed_at, "reviewed_at")
        _day(self.valid_until, "valid_until")
        if self.valid_until < self.reviewed_at:
            raise ValueError("review expiry precedes its issue date")
        if self.qualification is not None and type(self.qualification) is not RevisionQualification:
            raise ValueError("qualification provenance uses its exact typed receipt")


@dataclass(frozen=True)
class RevisionSelection:
    state: SelectionState
    source_id: str | None
    section: str
    as_of: date | None
    reason: str
    candidate_ids: tuple[str, ...] = ()
    revision: ProvisionRevision | None = None
    authorities: tuple[HeldAuthoritySpan, ...] = ()
    approval: RevisionApproval | None = None

    @property
    def wording(self) -> HeldAuthoritySpan | None:
        return self.authorities[0] if self.state is SelectionState.SELECTED else None

    def as_record(self) -> dict:
        return _wire(self)


SourceBytes = Callable[[str], bytes | None]
ReviewOwner = Callable[[RevisionReviewRequest], RevisionApproval | None]


def read_authority_span(
    span: AuthoritySpan, versions: dict[str, SourceVersion], source_bytes: SourceBytes
) -> HeldAuthoritySpan:
    """Read back the exact held version, not caller-supplied quotation text."""
    from nm.legal_brain.retrieve.source_registry_sources import RightsState, SourceKind

    version = versions.get(span.version_id)
    if version is None:
        raise ValueError("an authority source version is not registered")
    if version.source.kind is not SourceKind.INSTRUMENT:
        raise ValueError("revision proof must identify a primary instrument")
    if version.rights.state is not RightsState.PERMITTED:
        raise ValueError("authority source publication rights are not established")
    content = source_bytes(span.version_id)
    if type(content) is not bytes:
        raise ValueError("exact authority source bytes are not held")
    if hashlib.sha256(content).hexdigest() != version.content_sha256:
        raise ValueError("authority source bytes changed from their registered digest")
    text = content.decode("utf8")
    if span.end > len(text) or not text[span.start : span.end].strip():
        raise ValueError("authority span is outside the held source text or blank")
    return HeldAuthoritySpan(
        span,
        version.source.source_id,
        version.content_sha256,
        text[span.start : span.end],
        version.source,
        version.observed_at,
        version.source_date,
    )


def select_revision(
    source_id: str,
    section: str,
    as_of: date | None,
    revisions: tuple[ProvisionRevision, ...],
    versions: dict[str, SourceVersion],
    *,
    checked_at: date,
    source_bytes: SourceBytes | None,
    review_owner: ReviewOwner | None,
) -> RevisionSelection:
    """Select only a unique dated identity with owned proof and current review.

    No sorting by recency, fullest wording, Act dates, or law names chooses
    between revisions. Open intervals do not extend the verified horizon.
    """
    _text(source_id, "canonical source identity")
    _text(section, "exact provision key")
    _day(as_of, "as_of", nullable=True)
    _day(checked_at, "checked_at")
    all_for_key = tuple(
        row for row in revisions if row.source_id == source_id and row.section == section
    )
    candidates = tuple(
        row
        for row in all_for_key
        if as_of is not None
        and row.effective_from <= as_of
        and (row.effective_until is None or as_of < row.effective_until)
    )
    ids = tuple(sorted(row.subject_id for row in candidates))

    def result(state, reason, revision=None, authorities=(), approval=None):
        return RevisionSelection(
            state, source_id, section, as_of, reason, ids, revision, authorities, approval
        )

    if as_of is None:
        return result(SelectionState.NOT_ASSESSED, "the provision's governing date is missing")
    if not candidates:
        return result(
            SelectionState.NOT_ASSESSED,
            "no held provision revision establishes wording for this exact date; "
            "historical wording and commencement/amendment evidence are missing",
        )
    if len(candidates) != 1:
        return result(
            SelectionState.NOT_ASSESSED,
            "overlapping provision revision identities are ambiguous; none selected",
        )
    revision = candidates[0]
    if as_of > revision.verified_through:
        return result(
            SelectionState.NOT_ASSESSED,
            "the requested date exceeds verified provision-version coverage",
            revision,
        )
    if revision.transition is TransitionState.NOT_ASSESSED or revision.reservation.strip():
        return result(
            SelectionState.NOT_ASSESSED,
            "provision transition/savings or a material reservation is unresolved",
            revision,
        )
    roles = {span.role for span in revision.commencement}
    change = (
        AuthorityRole.ENACTMENT
        if revision.kind is RevisionKind.ORIGINAL
        else AuthorityRole.AMENDMENT
    )
    if not {change, AuthorityRole.COMMENCEMENT} <= roles:
        return result(
            SelectionState.NOT_ASSESSED,
            "exact enactment/amendment and commencement proof is missing",
            revision,
        )
    if revision.effective_until is not None and not (
        AuthorityRole.COMMENCEMENT in {span.role for span in revision.ending}
        and {AuthorityRole.AMENDMENT, AuthorityRole.REPEAL}
        & {span.role for span in revision.ending}
    ):
        return result(
            SelectionState.NOT_ASSESSED,
            "the ending boundary lacks exact change and commencement proof",
            revision,
        )
    if revision.transition is TransitionState.RESOLVED and not any(
        span.role is AuthorityRole.TRANSITION for span in revision.transition_authorities
    ):
        return result(
            SelectionState.NOT_ASSESSED,
            "resolved transition has no exact transition authority",
            revision,
        )
    if source_bytes is None or review_owner is None:
        return result(
            SelectionState.NOT_ASSESSED,
            "held source bytes or authenticated qualified-review owner is missing",
            revision,
        )
    try:
        authorities = tuple(
            read_authority_span(span, versions, source_bytes) for span in revision.spans
        )
    except (ValueError, OSError, UnicodeError) as exc:
        return result(SelectionState.REFUSED, f"provision authority read refused: {exc}", revision)
    if authorities[0].source_id != source_id:
        return result(
            SelectionState.REFUSED, "wording belongs to a different canonical instrument", revision
        )
    request = RevisionReviewRequest(
        revision.subject_id,
        _digest(authorities),
        tuple(sorted({span.authority.version_id for span in authorities})),
        checked_at,
    )
    approval = review_owner(request)
    if (
        type(approval) is not RevisionApproval
        or approval.subject_id != request.subject_id
        or approval.authority_digest != request.authority_digest
        or approval.version_ids != request.version_ids
        or not approval.reviewed_at <= checked_at <= approval.valid_until
    ):
        return result(
            SelectionState.NOT_ASSESSED,
            "no exact current authenticated qualified-review receipt matches this revision",
            revision,
        )
    try:
        current = tuple(
            read_authority_span(span, versions, source_bytes) for span in revision.spans
        )
    except (ValueError, OSError, UnicodeError) as exc:
        return result(
            SelectionState.REFUSED,
            f"provision authority changed during review lookup: {exc}",
            revision,
        )
    if current != authorities or review_owner(request) != approval:
        return result(
            SelectionState.REFUSED,
            "source or qualified-review ownership changed during selection",
            revision,
        )
    return result(
        SelectionState.SELECTED,
        "one exact dated provision revision has held authority and current owned review; "
        "applicability to the matter is not decided",
        revision,
        authorities,
        approval,
    )
