"""Attributed permission to process matter text, not legal/compliance clearance.

Owner authorised global OpenAI text processing on 21 September 2026. Each
advocate must still accept the disclosed purpose. Neither an API key nor an
editable inventory row supplies that acceptance. Raw media is outside scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from nm.domain.egress import EgressRefused

NOTICE_VERSION = "openai-text-2026-09-21"
PURPOSE = "matter_text"


class ModelPermissionRefused(EgressRefused):
    """No authenticated permission for this dispatch; not an empty model result."""


@dataclass(frozen=True)
class ModelPermission:
    account_id: str
    notice_version: str
    accepted: bool
    recorded_at: datetime
    version: int

    def __post_init__(self):
        if (not isinstance(self.account_id, str) or not self.account_id.strip()
                or not isinstance(self.notice_version, str) or not self.notice_version.strip()
                or type(self.accepted) is not bool
                or type(self.version) is not int or self.version < 1
                or not isinstance(self.recorded_at, datetime)
                or self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None):
            raise ValueError("model permission needs attributed, dated, typed acceptance")

    def permits(self, account_id: str, now: datetime) -> bool:
        return (self.account_id == account_id and self.accepted
                and self.notice_version == NOTICE_VERSION and self.recorded_at <= now)

    def as_dict(self) -> dict:
        return {"account_id": self.account_id, "notice_version": self.notice_version,
                "accepted": self.accepted, "recorded_at": self.recorded_at.isoformat(),
                "version": self.version}

    @classmethod
    def from_record(cls, row: dict) -> ModelPermission:
        if not isinstance(row, dict) or set(row) != {
                "account_id", "notice_version", "accepted", "recorded_at", "version"}:
            raise ValueError("model permission record is invalid")
        return cls(**{**row, "recorded_at": datetime.fromisoformat(row["recorded_at"])})
