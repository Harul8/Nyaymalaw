"""Owned preference changes and a typed presentation-only prefix input. LB-151."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from nm.arrive.directory_port import DirectoryPort, MemoryUnavailable
from nm.legal_brain.understand.advocate_memory_contracts import (
    CHOICES,
    COURTS,
    LIMITS,
    AdvocateMemory,
    PreferenceKey,
    Preferences,
)
from nm.shared.json_values import same_json_value

MAX_RECORD_BYTES = 4096


def decode_memory(raw: bytes, account_id: str) -> AdvocateMemory:
    """Bounded exact JSON; duplicate fields and coercive equality cannot pass."""
    if type(raw) is not bytes or len(raw) > MAX_RECORD_BYTES:
        raise ValueError("memory record exceeds its bounded schema")

    def pairs(rows):
        out = {}
        for key, value in rows:
            if key in out:
                raise ValueError("memory JSON has duplicate fields")
            out[key] = value
        return out

    value = json.loads(
        raw.decode("utf8"),
        object_pairs_hook=pairs,
        parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite memory value")),
    )
    record = AdvocateMemory.from_record(value)
    if record.account_id != account_id or not same_json_value(value, record.as_dict()):
        raise ValueError("memory differs from its exact account-owned record")
    return record


def _current(directory: DirectoryPort, account_id: str) -> AdvocateMemory | None:
    current = directory.advocate_memory(account_id)
    if current is not None and (
        type(current) is not AdvocateMemory or current.account_id != account_id
    ):
        raise MemoryUnavailable("Preference memory could not be verified.")
    return current


def memory_view(directory: DirectoryPort, account_id: str) -> dict:
    current = _current(directory, account_id)
    return {
        "state": "saved" if current and current.preferences.entries else "empty",
        "version": current.version if current else 0,
        "settings": current.preferences.as_dict() if current else {},
        "approved_at": current.approved_at.isoformat() if current else None,
        "supported": {key.value: list(choices) for key, choices in CHOICES.items()},
        "courts": dict(COURTS),
        "limits": LIMITS,
    }


def save_memory(
    directory: DirectoryPort,
    account_id: str,
    settings: object,
    *,
    approved: bool,
    expected_version: int,
    now: datetime,
) -> AdvocateMemory:
    if approved is not True:
        raise ValueError("Only explicitly approved preferences can be saved.")
    if type(expected_version) is not int or expected_version < 0:
        raise ValueError("Read the current preference version before changing it.")
    preferences = Preferences.from_values(settings)
    record = AdvocateMemory(account_id, expected_version + 1, preferences, account_id, now)
    return directory.record_advocate_memory(record, expected_version=expected_version)


def delete_memory(
    directory: DirectoryPort,
    account_id: str,
    key: PreferenceKey | None,
    *,
    approved: bool,
    expected_version: int,
    now: datetime,
) -> AdvocateMemory:
    if approved is not True:
        raise ValueError("Preference deletion needs your explicit approval.")
    current = _current(directory, account_id)
    preferences = current.preferences if current else Preferences()
    return save_memory(
        directory,
        account_id,
        preferences.without(key).as_dict(),
        approved=approved,
        expected_version=expected_version,
        now=now,
    )


@dataclass(frozen=True)
class PreferenceContext:
    """Root supplies this once per conversation, outside the matter/source file."""

    account_id: str
    version: int | None
    preferences: Preferences
    notice: str = ""

    def __post_init__(self):
        if (
            type(self.account_id) is not str
            or not self.account_id
            or type(self.preferences) is not Preferences
            or self.version is not None
            and (type(self.version) is not int or self.version < 0)
            or type(self.notice) is not str
            or self.notice
            not in ("", "Preference memory is unavailable; this conversation uses defaults.")
        ):
            raise ValueError("preference context must have a typed account-owned basis")
        if self.version is None and (self.preferences.entries or not self.notice):
            raise ValueError("unavailable memory cannot supply preferences")

    @property
    def prefix_input(self) -> str:
        return json.dumps(
            {
                "kind": "approved_advocate_working_preferences",
                "scope": "presentation_and_practice_only_not_facts_law_forum_or_authority",
                "version": self.version,
                "settings": self.preferences.as_dict(),
                "notice": self.notice,
                "limits": LIMITS,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )


def preference_context(directory: DirectoryPort, account_id: str) -> PreferenceContext:
    try:
        current = _current(directory, account_id)
        return PreferenceContext(
            account_id,
            current.version if current else 0,
            current.preferences if current else Preferences(),
        )
    except Exception:  # noqa: BLE001 -- memory cannot prevent an ordinary matter proceeding
        return PreferenceContext(
            account_id,
            None,
            Preferences(),
            "Preference memory is unavailable; this conversation uses defaults.",
        )
