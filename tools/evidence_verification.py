"""One trust boundary for evidence whose truth is not derivable from source.

The planning registry stores references and digests.  Those are claims, not
proof.  This module deliberately separates three questions which earlier
readers collapsed:

* can the referenced bytes be obtained;
* do those exact bytes match the recorded digest; and
* does a maintained trust mechanism authenticate the claimed payload/actor.

The concrete verifier uses Ed25519 and caller-supplied trust anchors.  It never
ships a repository-wide key, accepts a hash as a signature, or invents a trust
root.  A caller with no configured trust material must use
``UnavailableVerifier`` and receives an explicit unavailable assessment.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import pathlib
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def canonical_json(value: object) -> bytes:
    """The signed representation used by approval and evidence envelopes."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def instant(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


@dataclass(frozen=True)
class Verification:
    """A verification result; unavailable is distinct from a failed check."""

    available: bool
    verified: bool
    reasons: tuple[str, ...] = ()
    signers: frozenset[str] = frozenset()
    payload: object | None = None

    @classmethod
    def unavailable(cls, reason: str) -> "Verification":
        return cls(False, False, (reason,))

    @classmethod
    def refused(cls, reason: str, *, payload: object | None = None) -> "Verification":
        return cls(True, False, (reason,), payload=payload)


class EvidenceVerifier(Protocol):
    """Capability injected into readers; no implicit global trust service."""

    configuration_identity: str | None

    def integrity(self, claim: object, *, purpose: str) -> Verification: ...

    def signed_payload(
        self,
        claim: object,
        *,
        purpose: str,
        expected_payload: object,
        required_signers: frozenset[str] = frozenset(),
    ) -> Verification: ...

    def authority(
        self,
        claim: object,
        *,
        person_id: str,
        role: str,
        basis: str,
        scope: str,
        at: datetime,
    ) -> Verification: ...

    def condition(
        self,
        claim: object,
        *,
        approval_id: str,
        condition_id: str,
        requirement: str,
        at: datetime,
    ) -> Verification: ...


class UnavailableVerifier:
    """Safe default when no maintained trust mechanism has been configured."""

    configuration_identity = None

    def __init__(self, reason: str = "no evidence verifier is configured") -> None:
        self.reason = reason

    def integrity(self, claim: object, *, purpose: str) -> Verification:
        return Verification.unavailable(f"{purpose}: {self.reason}")

    def signed_payload(
        self,
        claim: object,
        *,
        purpose: str,
        expected_payload: object,
        required_signers: frozenset[str] = frozenset(),
    ) -> Verification:
        return Verification.unavailable(f"{purpose}: {self.reason}")

    def authority(
        self,
        claim: object,
        *,
        person_id: str,
        role: str,
        basis: str,
        scope: str,
        at: datetime,
    ) -> Verification:
        return Verification.unavailable(f"authority for {person_id}: {self.reason}")

    def condition(
        self,
        claim: object,
        *,
        approval_id: str,
        condition_id: str,
        requirement: str,
        at: datetime,
    ) -> Verification:
        return Verification.unavailable(f"condition {condition_id}: {self.reason}")


class SignedArtifactVerifier:
    """Verify local original bytes and Ed25519-signed JSON envelopes.

    ``trusted_keys`` is keyed by ``(person_id, key_id)``.  Authority grants are
    themselves signed envelopes and must be signed by an identity in
    ``authority_issuers``.  The caller owns trust-anchor provisioning and key
    rotation; this class owns deterministic verification and path containment.
    """

    def __init__(
        self,
        *,
        base: pathlib.Path,
        allowed_roots: tuple[pathlib.Path, ...],
        trusted_keys: Mapping[tuple[str, str], Ed25519PublicKey],
        authority_issuers: frozenset[str],
        configuration_identity: str | None = None,
    ) -> None:
        self.base = base.resolve()
        self.allowed_roots = tuple(root.resolve() for root in allowed_roots)
        self.trusted_keys = dict(trusted_keys)
        self.authority_issuers = authority_issuers
        self.configuration_identity = configuration_identity

    def _bytes(self, claim: object, purpose: str) -> tuple[bytes | None, Verification | None]:
        if not isinstance(claim, dict):
            return None, Verification.refused(f"{purpose}: artifact claim is not an object")
        ref, digest = claim.get("ref"), claim.get("sha256")
        if not isinstance(ref, str) or not ref.strip():
            return None, Verification.refused(f"{purpose}: artifact has no reference")
        if (not isinstance(digest, str) or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)):
            return None, Verification.refused(f"{purpose}: artifact has no valid SHA-256")
        candidate = pathlib.Path(ref)
        path = (candidate if candidate.is_absolute() else self.base / candidate).resolve()
        try:
            if not any(path == root or path.is_relative_to(root)
                       for root in self.allowed_roots):
                return None, Verification.refused(
                    f"{purpose}: artifact reference is outside the configured evidence roots")
        except (OSError, ValueError):
            return None, Verification.refused(f"{purpose}: artifact reference is invalid")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            return None, Verification.unavailable(
                f"{purpose}: artifact bytes cannot be read ({exc.__class__.__name__})")
        actual = sha256_bytes(raw)
        if actual != digest:
            return None, Verification.refused(
                f"{purpose}: artifact digest is {actual}, expected {digest}")
        return raw, None

    def integrity(self, claim: object, *, purpose: str) -> Verification:
        raw, failure = self._bytes(claim, purpose)
        if failure:
            return failure
        return Verification(True, True, payload=raw)

    def signed_payload(
        self,
        claim: object,
        *,
        purpose: str,
        expected_payload: object,
        required_signers: frozenset[str] = frozenset(),
    ) -> Verification:
        raw, failure = self._bytes(claim, purpose)
        if failure:
            return failure
        try:
            envelope = json.loads((raw or b"").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return Verification.refused(f"{purpose}: signed artifact is not UTF-8 JSON")
        if not isinstance(envelope, dict) or set(envelope) != {
                "schema", "payload", "signatures"} or envelope.get("schema") != 1:
            return Verification.refused(
                f"{purpose}: signed artifact is not a closed schema-1 envelope")
        payload = envelope.get("payload")
        if canonical_json(payload) != canonical_json(expected_payload):
            return Verification.refused(
                f"{purpose}: authenticated payload does not match the indexed claim",
                payload=payload)
        signatures = envelope.get("signatures")
        if not isinstance(signatures, list) or not signatures:
            return Verification.refused(f"{purpose}: envelope has no signatures")
        signed = canonical_json(payload)
        valid: set[str] = set()
        malformed = False
        for signature in signatures:
            if not isinstance(signature, dict):
                malformed = True
                continue
            person_id, key_id, value = (
                signature.get("person_id"), signature.get("key_id"),
                signature.get("signature"),
            )
            key = self.trusted_keys.get((str(person_id), str(key_id)))
            if key is None or not isinstance(value, str):
                malformed = True
                continue
            try:
                decoded = base64.b64decode(value, validate=True)
                key.verify(decoded, signed)
            except (binascii.Error, InvalidSignature, ValueError):
                malformed = True
                continue
            valid.add(str(person_id))
        missing = sorted(required_signers - valid)
        if missing:
            return Verification.refused(
                f"{purpose}: required signer(s) did not authenticate: {', '.join(missing)}",
                payload=payload)
        if malformed:
            return Verification.refused(
                f"{purpose}: envelope contains an unknown or invalid signature",
                payload=payload)
        return Verification(True, True, signers=frozenset(valid), payload=payload)
    def authority(
        self,
        claim: object,
        *,
        person_id: str,
        role: str,
        basis: str,
        scope: str,
        at: datetime,
    ) -> Verification:
        raw, failure = self._bytes(claim, f"authority for {person_id}")
        if failure:
            return failure
        try:
            envelope = json.loads((raw or b"").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return Verification.refused(
                f"authority for {person_id}: evidence is not UTF-8 JSON")
        if not isinstance(envelope, dict) or envelope.get("schema") != 1:
            return Verification.refused(
                f"authority for {person_id}: unsupported signed envelope")
        payload = envelope.get("payload")
        signatures = envelope.get("signatures")
        if not isinstance(payload, dict) or not isinstance(signatures, list):
            return Verification.refused(
                f"authority for {person_id}: malformed signed grant")
        wanted = {
            "kind": "authority_grant", "person_id": person_id,
            "role": role, "basis": basis,
        }
        for key, value in wanted.items():
            if payload.get(key) != value:
                return Verification.refused(
                    f"authority for {person_id}: grant does not bind {key}")
        scopes = payload.get("scopes")
        if not isinstance(scopes, list) or scope not in scopes:
            return Verification.refused(
                f"authority for {person_id}: grant does not cover {scope}")
        start, end = instant(payload.get("valid_from")), instant(payload.get("valid_until"))
        if start is None or end is None or not (start <= at < end):
            return Verification.refused(
                f"authority for {person_id}: grant is not current at the decision time")

        signed = canonical_json(payload)
        valid_issuers: set[str] = set()
        for signature in signatures:
            if not isinstance(signature, dict):
                continue
            issuer, key_id, value = (
                str(signature.get("person_id")), str(signature.get("key_id")),
                signature.get("signature"),
            )
            if issuer not in self.authority_issuers or not isinstance(value, str):
                continue
            key = self.trusted_keys.get((issuer, key_id))
            if key is None:
                continue
            try:
                key.verify(base64.b64decode(value, validate=True), signed)
            except (binascii.Error, InvalidSignature, ValueError):
                continue
            valid_issuers.add(issuer)
        if not valid_issuers:
            return Verification.refused(
                f"authority for {person_id}: no configured authority issuer "
                "authenticated the grant",
                payload=payload)
        return Verification(
            True, True, signers=frozenset(valid_issuers), payload=payload)

    def condition(
        self,
        claim: object,
        *,
        approval_id: str,
        condition_id: str,
        requirement: str,
        at: datetime,
    ) -> Verification:
        raw, failure = self._bytes(claim, f"condition {condition_id}")
        if failure:
            return failure
        try:
            envelope = json.loads((raw or b"").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return Verification.refused(
                f"condition {condition_id}: evidence is not UTF-8 JSON")
        if not isinstance(envelope, dict) or envelope.get("schema") != 1:
            return Verification.refused(
                f"condition {condition_id}: unsupported signed envelope")
        payload = envelope.get("payload")
        signatures = envelope.get("signatures")
        wanted = {
            "kind": "condition_evidence", "approval_id": approval_id,
            "condition_id": condition_id, "requirement": requirement,
        }
        if not isinstance(payload, dict) or any(
                payload.get(key) != value for key, value in wanted.items()):
            return Verification.refused(
                f"condition {condition_id}: evidence does not bind the indexed condition")
        until = instant(payload.get("valid_until"))
        if until is None or at >= until:
            return Verification.refused(
                f"condition {condition_id}: evidence is expired or unbounded")
        if not isinstance(signatures, list) or not signatures:
            return Verification.refused(
                f"condition {condition_id}: evidence has no signatures")
        signed = canonical_json(payload)
        valid: set[str] = set()
        for signature in signatures:
            if not isinstance(signature, dict):
                continue
            person_id, key_id, value = (
                str(signature.get("person_id")), str(signature.get("key_id")),
                signature.get("signature"),
            )
            key = self.trusted_keys.get((person_id, key_id))
            if key is None or not isinstance(value, str):
                continue
            try:
                key.verify(base64.b64decode(value, validate=True), signed)
            except (binascii.Error, InvalidSignature, ValueError):
                continue
            valid.add(person_id)
        if not valid:
            return Verification.refused(
                f"condition {condition_id}: no trusted signer authenticated the evidence",
                payload=payload)
        return Verification(True, True, signers=frozenset(valid), payload=payload)


def configured_verifier(*, base: pathlib.Path,
                        environment: Mapping[str, str] | None = None) -> EvidenceVerifier:
    """Load public trust material from an operator-owned configuration.

    The repository intentionally contains no universal trust root. Operators
    opt in with ``NM_EVIDENCE_TRUST`` pointing to a closed JSON document:
    ``schema``, ``configuration_identity``, nonempty ``allowed_roots``,
    ``authority_issuers`` and ``keys`` (person_id, key_id, PEM public_key).
    Any omission or unreadable key makes verification unavailable; it never
    falls back to digest-only acceptance.  The configuration identity is the
    operator's versioned identity for the evidence policy/configuration under
    which a review is being consumed; it is deliberately not inferred from a
    review record that is itself making the claim.
    """
    env = os.environ if environment is None else environment
    configured = str(env.get("NM_EVIDENCE_TRUST") or "").strip()
    if not configured:
        return UnavailableVerifier("NM_EVIDENCE_TRUST is not configured")
    path = pathlib.Path(configured)
    path = (path if path.is_absolute() else base / path).resolve()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return UnavailableVerifier(
            f"trust configuration cannot be read ({exc.__class__.__name__})")
    if not isinstance(doc, dict) or set(doc) != {
            "schema", "configuration_identity", "allowed_roots",
            "authority_issuers", "keys"}:
        return UnavailableVerifier("trust configuration has unknown or missing fields")
    roots, issuers, rows, configuration_identity = (
        doc.get("allowed_roots"), doc.get("authority_issuers"), doc.get("keys"),
        doc.get("configuration_identity"))
    if doc.get("schema") != 1 or not isinstance(roots, list) or not roots \
            or not isinstance(issuers, list) or not issuers \
            or not isinstance(rows, list) or not rows \
            or not isinstance(configuration_identity, str) \
            or not configuration_identity.strip():
        return UnavailableVerifier("trust configuration has an empty required population")
    keys: dict[tuple[str, str], Ed25519PublicKey] = {}
    try:
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                    "person_id", "key_id", "public_key"}:
                raise ValueError("malformed key row")
            loaded = serialization.load_pem_public_key(
                str(row["public_key"]).encode("ascii"))
            if not isinstance(loaded, Ed25519PublicKey):
                raise ValueError("key is not Ed25519")
            key_identity = (str(row["person_id"]), str(row["key_id"]))
            if key_identity in keys:
                raise ValueError("duplicate key identity")
            keys[key_identity] = loaded
        allowed = tuple((pathlib.Path(root) if pathlib.Path(root).is_absolute()
                         else base / pathlib.Path(root)).resolve() for root in roots)
    except (KeyError, TypeError, ValueError, UnicodeEncodeError) as exc:
        return UnavailableVerifier(f"trust configuration is invalid ({exc})")
    if not set(map(str, issuers)) <= {person for person, _ in keys}:
        return UnavailableVerifier("an authority issuer has no configured key")
    return SignedArtifactVerifier(
        base=base, allowed_roots=allowed, trusted_keys=keys,
        authority_issuers=frozenset(map(str, issuers)),
        configuration_identity=configuration_identity.strip(),
    )
