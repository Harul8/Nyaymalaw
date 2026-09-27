"""Read a host-allowlisted dated provision review through existing trust owners.

No approval, signature, key or legal metadata is created here. Schema-2 counsel
evidence and its separately issuer-signed qualification grant must already
exist. Candidate revision metadata, hashes alone and account approval cannot
substitute for these artifacts. An absent/unusable owner returns no receipt.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

from assurance.control_plane.evidence_verification import (
    canonical_json,
    configured_verifier,
    instant,
    sha256_bytes,
)
from assurance.control_plane.structured_evidence import REQUIRED, SCHEMA, problems_for_record
from nm.legal_brain.retrieve.provision_revision_sources import (
    ReviewOwner,
    RevisionApproval,
    RevisionQualification,
    RevisionReviewRequest,
)
from nm.shared.json_values import same_json_value

CRITERION = "LB-156"
RUBRIC = "provision-revision-v1"
FINDINGS = frozenset({"wording", "effective_interval", "commencement", "change", "transition"})


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field in reviewed artifact")
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError("nonfinite value in reviewed artifact")


def _path(base: Path, ref: str) -> Path:
    # These references are supplied by the configured bootstrap owner. Neither
    # the tool author nor an HTTP request can choose a path or an evidence root.
    if type(ref) is not str or not ref.strip() or "#" in ref or "://" in ref:
        raise ValueError("a fixed local evidence record must be named")
    relative = Path(ref)
    if relative.is_absolute():
        raise ValueError("review references are repository-relative evidence paths")
    path = (base / relative).resolve()
    path.relative_to((base / "docs" / "backlog" / "evidence").resolve())
    return path


def _claim_path(base: Path, claim: object) -> Path:
    if type(claim) is not dict or set(claim) != {"ref", "sha256"}:
        raise ValueError("review evidence must bind one exact local original artifact")
    digest = claim["sha256"]
    if type(digest) is not str or len(digest) != 64 or any(
        char not in "0123456789abcdef" for char in digest
    ):
        raise ValueError("review evidence has no exact sha256")
    return _path(base, claim["ref"])


def _text(value):
    return type(value) is str and bool(value.strip())


def _request_is_exact(request: object, moment: datetime) -> bool:
    return (
        type(request) is RevisionReviewRequest
        and _text(request.subject_id)
        and _text(request.authority_digest)
        and len(request.authority_digest) == 64
        and all(char in "0123456789abcdef" for char in request.authority_digest)
        and type(request.version_ids) is tuple
        and bool(request.version_ids)
        and all(_text(value) for value in request.version_ids)
        and tuple(sorted(set(request.version_ids))) == request.version_ids
        and request.checked_at == moment.date()
    )


def _bound_shape(record, request, qualified_roles):
    if type(record) is not dict or set(record) != set(REQUIRED):
        return False
    wanted = {
        "kind": "provision_revision",
        "subject_id": request.subject_id,
        "authority_digest": request.authority_digest,
        "version_ids": list(request.version_ids),
    }
    actor, authority, identity, rubric, population = (
        record.get(key)
        for key in ("actor", "authority", "subject_identity", "rubric", "population")
    )
    return (
        type(record["schema"]) is int
        and record["schema"] == SCHEMA
        and same_json_value(record["subject"], wanted)
        and type(actor) is dict
        and set(actor) == {"person_id", "name"}
        and all(_text(value) for value in actor.values())
        and type(authority) is dict
        and set(authority) == {"role", "basis", "evidence"}
        and authority["role"] in qualified_roles
        and _text(authority["basis"])
        and type(identity) is dict
        and set(identity) <= {"kind", "value", "valid_from", "valid_until"}
        and identity.get("kind") == "source"
        and identity.get("value") == request.subject_id
        and type(rubric) is dict
        and rubric.get("identity") == RUBRIC
        and type(rubric.get("findings")) is list
        and len(rubric["findings"]) == len(FINDINGS)
        and all(type(row) is dict and _text(row.get("id")) for row in rubric["findings"])
        and {row["id"] for row in rubric["findings"]} == FINDINGS
        and type(population) is dict
        and set(population) == {"count", "described"}
        and type(population["count"]) is int
        and population["count"] == len(request.version_ids)
        and record["reservations"] == []
    )


def build_revision_review_owner(
    *,
    base: Path,
    artifact_refs: tuple[str, ...],
    now: Callable[[], datetime],
    environment: Mapping[str, str] | None = None,
    qualified_roles: frozenset[str] = frozenset({"Advocate"}),
) -> ReviewOwner:
    """Adapt existing signed schema-2 evidence into an exact current receipt.

    ``artifact_refs`` is a finite operator-owned allowlist, not discovered or
    taken from a caller. Empty means no qualified review exists. Fixed records
    are read afresh, including trust/key rotation and issuer-grant withdrawal.
    The host clock must use the same date zone as ``request.checked_at``.
    """
    base = base.resolve()
    if (
        type(artifact_refs) is not tuple
        or any(not _text(ref) for ref in artifact_refs)
        or len(set(artifact_refs)) != len(artifact_refs)
    ):
        raise ValueError("review artifact references are one exact distinct tuple")
    paths = tuple(_path(base, ref) for ref in artifact_refs)
    if len(set(paths)) != len(paths):
        raise ValueError("aliases cannot duplicate one review artifact")
    if not callable(now) or type(qualified_roles) is not frozenset or not qualified_roles or any(
        not _text(role) for role in qualified_roles
    ):
        raise ValueError("review needs the host clock and explicit qualified-role policy")

    def read(request):
        try:
            moment = now()
            if type(moment) is not datetime or moment.tzinfo is None or not _request_is_exact(
                request, moment
            ):
                return None
            verifier = configured_verifier(base=base, environment=environment)
            if not verifier.configuration_identity:
                return None
            matches = []
            held_records = []
            for ref, path in zip(artifact_refs, paths, strict=True):
                # Re-resolve even fixed paths: a newly substituted link cannot
                # move the reader outside its original bounded evidence root.
                if _path(base, ref) != path:
                    return None
                raw = path.read_bytes()
                held_records.append((path, raw))
                record = json.loads(
                    raw.decode("utf8"), object_pairs_hook=_unique_keys, parse_constant=_nonfinite
                )
                subject = record.get("subject") if type(record) is dict else None
                if type(subject) is not dict or subject.get("subject_id") != request.subject_id:
                    continue
                # Any ambiguous, withdrawn, stale or incomplete matching row
                # blocks reuse. Never pick a newer/fuller/positive-looking row.
                if not _bound_shape(record, request, qualified_roles):
                    return None
                attestation_path = _claim_path(base, record["attestation"])
                grant_path = _claim_path(base, record["authority"]["evidence"])
                attestation_raw, grant_raw = attestation_path.read_bytes(), grant_path.read_bytes()
                if problems_for_record(
                    CRITERION,
                    "counsel_review",
                    record,
                    now=moment,
                    source_fingerprint=request.subject_id,
                    configuration_identity=verifier.configuration_identity,
                    verifier=verifier,
                ):
                    return None
                authority = record["authority"]
                grant = verifier.authority(
                    authority["evidence"],
                    person_id=record["actor"]["person_id"],
                    role=authority["role"],
                    basis=authority["basis"],
                    scope="evidence:counsel_review",
                    at=moment,
                )
                if not grant.verified or type(grant.payload) is not dict or not grant.signers:
                    return None
                until, observed = (
                    instant(record["subject_identity"].get("valid_until")),
                    instant(record["observed_at"]),
                )
                if until is None or observed is None:
                    return None
                proof = RevisionQualification(
                    record["actor"]["person_id"], record["actor"]["name"],
                    authority["role"], authority["basis"], verifier.configuration_identity,
                    ref, sha256_bytes(raw), record["attestation"]["ref"],
                    record["attestation"]["sha256"], authority["evidence"]["ref"],
                    authority["evidence"]["sha256"], tuple(sorted(grant.signers)),
                    canonical_json(grant.payload).decode("utf8"), observed.isoformat(),
                    until.isoformat(),
                )
                # A date-only consumer must not widen an intraday expiry: this
                # owner revalidates the actual instant at every lookup.
                approval = RevisionApproval(
                    "revision_review_" + sha256_bytes(raw), record["actor"]["person_id"],
                    request.subject_id, request.authority_digest, request.version_ids,
                    observed.astimezone(moment.tzinfo).date(),
                    until.astimezone(moment.tzinfo).date(), proof,
                )
                matches.append(approval)
                held_records.extend(((attestation_path, attestation_raw), (grant_path, grant_raw)))
                # The generic owner verifies the exact signed subject and the
                # current issuer grant again under reloaded trust configuration.
                current = configured_verifier(base=base, environment=environment)
                if (
                    current.configuration_identity != verifier.configuration_identity
                    or problems_for_record(
                        CRITERION, "counsel_review", record, now=moment,
                        source_fingerprint=request.subject_id,
                        configuration_identity=current.configuration_identity, verifier=current,
                    )
                ):
                    return None
            if len(matches) != 1 or any(path.read_bytes() != raw for path, raw in held_records):
                return None
            return matches[0]
        except (OSError, ValueError, TypeError, KeyError, UnicodeError):
            return None

    return read
