"""Operator-reviewed professional profile, separate from account and matter access.

This record does not enrol an account, assign a firm, grant matter authority,
resolve a conflict, establish a case fact or approve an external act. Consumers
must ask it only when an operation actually makes a professional approval.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime

from nm.domain.advocate import canonical_id
from nm.domain.text import blank


def _aware(value: object) -> bool:
    return (isinstance(value, datetime) and value.tzinfo is not None
            and value.utcoffset() is not None)


@dataclass(frozen=True)
class ProfessionalApproval:
    account_id: str
    reviewer_id: str
    basis: str
    evidence_ref: str
    evidence_sha256: str
    approved_at: datetime
    valid_until: datetime
    version: int = 1
    revoked_at: datetime | None = None
    revoked_by: str = ""
    revocation_reason: str = ""

    def __post_init__(self) -> None:
        for name in ("account_id", "reviewer_id", "basis", "evidence_ref", "evidence_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or blank(value):
                raise ValueError(f"professional approval needs {name}")
        if self.account_id != canonical_id(self.account_id):
            raise ValueError("professional approval account identity must be canonical")
        if canonical_id(self.reviewer_id) == self.account_id:
            raise ValueError("professional review must be attributable to a different operator")
        if not re.fullmatch(r"[a-f0-9]{64}", self.evidence_sha256):
            raise ValueError("professional approval needs the evidence artifact's SHA256")
        if type(self.version) is not int or self.version < 1:
            raise ValueError("professional approval version must be a positive integer")
        if not _aware(self.approved_at) or not _aware(self.valid_until):
            raise ValueError("professional approval needs aware review and expiry times")
        if self.valid_until <= self.approved_at:
            raise ValueError("professional approval must have a bounded future expiry")
        if not isinstance(self.revoked_by, str) or not isinstance(self.revocation_reason, str):
            raise ValueError("revocation actor and reason must be text")
        if self.revoked_at is None:
            if not blank(self.revoked_by) or not blank(self.revocation_reason):
                raise ValueError("revocation attribution needs a revocation time")
        elif (not _aware(self.revoked_at) or self.revoked_at < self.approved_at
              or blank(self.revoked_by) or blank(self.revocation_reason)):
            raise ValueError("revocation needs an attributable actor, time and reason")

    def permits(self, account_id: str, now: datetime) -> bool:
        return (isinstance(account_id, str) and canonical_id(account_id) == self.account_id
                and _aware(now) and self.revoked_at is None
                and self.approved_at <= now < self.valid_until)

    def revoke(self, operator: str, because: str, now: datetime) -> "ProfessionalApproval":
        if self.revoked_at is not None:
            raise ValueError("professional approval is already revoked")
        return replace(self, version=self.version + 1, revoked_at=now,
                       revoked_by=operator, revocation_reason=because)

    def as_dict(self) -> dict:
        return {
            "schema": 1, "account_id": self.account_id, "reviewer_id": self.reviewer_id,
            "basis": self.basis, "evidence_ref": self.evidence_ref,
            "evidence_sha256": self.evidence_sha256,
            "approved_at": self.approved_at.isoformat(),
            "valid_until": self.valid_until.isoformat(),
            "version": self.version,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "revoked_by": self.revoked_by, "revocation_reason": self.revocation_reason,
        }

    @staticmethod
    def from_record(value: object) -> "ProfessionalApproval | None":
        if not isinstance(value, dict) or set(value) != {
            "schema", "account_id", "reviewer_id", "basis", "evidence_ref", "evidence_sha256",
            "approved_at", "valid_until", "version", "revoked_at", "revoked_by",
            "revocation_reason",
        }:
            return None
        if type(value["schema"]) is not int or value["schema"] != 1:
            return None
        try:
            if (not isinstance(value["approved_at"], str)
                    or not isinstance(value["valid_until"], str)):
                return None
            revoked = value["revoked_at"]
            if revoked is not None and not isinstance(revoked, str):
                return None
            return ProfessionalApproval(
                account_id=value["account_id"], reviewer_id=value["reviewer_id"],
                basis=value["basis"], evidence_ref=value["evidence_ref"],
                evidence_sha256=value["evidence_sha256"], version=value["version"],
                approved_at=datetime.fromisoformat(value["approved_at"]),
                valid_until=datetime.fromisoformat(value["valid_until"]),
                revoked_at=datetime.fromisoformat(revoked) if revoked is not None else None,
                revoked_by=value["revoked_by"], revocation_reason=value["revocation_reason"],
            )
        except (ValueError, TypeError, AttributeError):
            return None


def professional_status(record: object, account_id: str, now: datetime) -> dict:
    """A safe profile summary, never evidence/reviewer details or a workspace gate."""
    approval = ProfessionalApproval.from_record(record)
    approved = approval is not None and approval.permits(account_id, now)
    return {
        "state": "approved" if approved else "unapproved",
        "version": approval.version if approval is not None else None,
        "valid_until": approval.valid_until.isoformat() if approved else None,
        "scope": "professional approvals only; ordinary account and own-file access "
                 "remain available",
    }
