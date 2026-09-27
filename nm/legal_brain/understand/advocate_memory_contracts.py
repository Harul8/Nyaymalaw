"""Explicit account preferences; no open text and no matter material. LB-151.

This vocabulary deliberately does not implement arbitrary standing instructions
or unnamed courts. A preference is not a case fact, law, jurisdiction, authority
to act, or evidence that an advocate actually appears in a court.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from nm.arrive.advocate_contracts import canonical_id


class PreferenceKey(str, Enum):
    ADVICE_LENGTH = "advice_length"
    AUTHORITIES_POSITION = "authorities_position"
    ADVICE_FORM = "advice_form"
    DRAFT_DATE_FORMAT = "draft_date_format"
    COURT_IDS = "court_ids"
    STANDING_INSTRUCTIONS = "standing_instructions"


# Stable identifiers, not name recognition or a jurisdiction/precedence rule.
COURTS = {
    "supreme_court": "Supreme Court of India",
    "hc_telangana": "High Court for the State of Telangana",
    "hc_andhra_pradesh": "High Court of Andhra Pradesh",
}
CHOICES = {
    PreferenceKey.ADVICE_LENGTH: ("short", "standard", "detailed"),
    PreferenceKey.AUTHORITIES_POSITION: ("inline", "end"),
    PreferenceKey.ADVICE_FORM: ("prose", "bullets"),
    PreferenceKey.DRAFT_DATE_FORMAT: ("iso", "day_month_year"),
    PreferenceKey.COURT_IDS: tuple(COURTS),
    PreferenceKey.STANDING_INSTRUCTIONS: (
        "explain_abbreviations",
        "show_action_owners",
        "include_short_summary",
    ),
}
LIST_KEYS = (PreferenceKey.COURT_IDS, PreferenceKey.STANDING_INSTRUCTIONS)
LIMITS = (
    "Only the listed presentation settings, standing-instruction switches and "
    "three court IDs are supported. Free-text instructions, client names, "
    "facts, documents and legal propositions cannot be saved. Court preferences "
    "do not establish a matter's forum or applicable law. Deletion removes "
    "current saved preferences; prior conversation records and independently "
    "retained backups are not erased."
)


@dataclass(frozen=True)
class Preferences:
    entries: tuple[tuple[PreferenceKey, str | tuple[str, ...]], ...] = ()

    def __post_init__(self):
        if type(self.entries) is not tuple or len(self.entries) > len(PreferenceKey):
            raise ValueError("preferences must use the closed settings vocabulary")
        seen = set()
        for entry in self.entries:
            if type(entry) is not tuple or len(entry) != 2:
                raise ValueError("each preference needs one closed key and value")
            key, value = entry
            if type(key) is not PreferenceKey or key in seen:
                raise ValueError("preference keys must be unique supported settings")
            seen.add(key)
            choices = CHOICES[key]
            if key in LIST_KEYS:
                if (
                    type(value) is not tuple
                    or len(value) > len(choices)
                    or any(type(item) is not str or item not in choices for item in value)
                    or len(set(value)) != len(value)
                ):
                    raise ValueError("list preferences require distinct supported IDs")
            elif type(value) is not str or value not in choices:
                raise ValueError("preference values must use the closed vocabulary")
        if tuple(key.value for key, _ in self.entries) != tuple(
            sorted(key.value for key, _ in self.entries)
        ):
            raise ValueError("preferences must have canonical key order")

    def as_dict(self) -> dict:
        return {
            key.value: list(value) if key in LIST_KEYS else value for key, value in self.entries
        }

    @staticmethod
    def from_values(value: object) -> "Preferences":
        if type(value) is not dict or len(value) > len(PreferenceKey):
            raise ValueError("preferences must be a bounded settings object")
        if any(
            type(key) is not str or key not in {item.value for item in PreferenceKey}
            for key in value
        ):
            raise ValueError("only supported preference keys can be saved")
        entries = []
        for text in sorted(value):
            key = PreferenceKey(text)
            item = value[text]
            if key in LIST_KEYS:
                if type(item) is not list or len(item) > len(CHOICES[key]):
                    raise ValueError("list preferences require bounded supported IDs")
                # IDs form a set. Canonical order keeps the stable prefix stable.
                if any(type(part) is not str for part in item):
                    raise ValueError("preference IDs must be strings")
                item = tuple(sorted(item))
            entries.append((key, item))
        return Preferences(tuple(entries))

    def without(self, key: PreferenceKey | None) -> "Preferences":
        if key is not None and type(key) is not PreferenceKey:
            raise ValueError("deletion requires a supported preference key")
        return Preferences(tuple(row for row in self.entries if key is not None and row[0] != key))


@dataclass(frozen=True)
class AdvocateMemory:
    account_id: str
    version: int
    preferences: Preferences
    approved_by: str
    approved_at: datetime

    def __post_init__(self):
        if (
            type(self.account_id) is not str
            or not self.account_id
            or self.account_id != canonical_id(self.account_id)
            or self.approved_by != self.account_id
        ):
            raise ValueError("memory approval must belong to its canonical account")
        if type(self.version) is not int or self.version < 1:
            raise ValueError("memory version must be a positive integer")
        if type(self.preferences) is not Preferences:
            raise ValueError("memory requires closed typed preferences")
        if not isinstance(self.approved_at, datetime) or self.approved_at.utcoffset() is None:
            raise ValueError("memory approval requires an aware time")

    def as_dict(self) -> dict:
        return {
            "schema": 1,
            "account_id": self.account_id,
            "version": self.version,
            "settings": self.preferences.as_dict(),
            "approved": True,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
        }

    @staticmethod
    def from_record(value: object) -> "AdvocateMemory":
        if type(value) is not dict or set(value) != {
            "schema",
            "account_id",
            "version",
            "settings",
            "approved",
            "approved_by",
            "approved_at",
        }:
            raise ValueError("memory record has unsupported fields")
        if (
            type(value["schema"]) is not int
            or value["schema"] != 1
            or value["approved"] is not True
        ):
            raise ValueError("memory needs its supported schema and explicit approval")
        if type(value["approved_at"]) is not str:
            raise ValueError("memory approval time is unreadable")
        return AdvocateMemory(
            value["account_id"],
            value["version"],
            Preferences.from_values(value["settings"]),
            value["approved_by"],
            datetime.fromisoformat(value["approved_at"]),
        )
