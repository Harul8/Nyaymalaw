"""Manually recorded dangers, never permission and never inferred legal advice.

B2/P14 foundation only. The ten choices below are the explicit semicolon
groups in assurance/specification/prd/part_b.js B2 DOES. Its 'five of eleven' counterexample is
an unresolved taxonomy discrepancy, not an eleventh class invented here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum


class UrgencyClass(str, Enum):
    LIMITATION_FILING = "limitation_and_filing_dates"
    HEARINGS_ORDERS = "hearings_and_orders"
    ARREST_LIBERTY = "arrest_or_liberty_risk"
    PERSONAL_SAFETY = "personal_safety"
    CHILD_SAFETY = "child_safety"
    INJUNCTION = "injunction_or_status_quo_need"
    ASSETS = "asset_dissipation"
    EVIDENCE = "evidence_destruction"
    SERVICE = "service_deadlines"
    IRREVERSIBLE = "irreversible_delay"


class UrgencyState(str, Enum):
    LIVE = "live"
    CLEARED = "cleared"
    NOT_ASSESSED = "not_assessed"
    RESOLVED = "resolved"


def _text(value, name: str, maximum: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be supplied explicitly within {maximum} characters")
    return value.strip()


def _time(value, name: str) -> str:
    value = _text(value, name, 100)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} requires an explicit time zone; no deadline is inferred")
    return parsed.astimezone(timezone.utc).isoformat()


def normalise_instruction(value) -> dict:
    """A closed user offer. Unknown is explicit, with its missing-information reason."""
    allowed = {"class", "basis", "action", "owner", "due", "unknowns"}
    if not isinstance(value, dict) or set(value) != allowed:
        raise ValueError("supply exactly class, basis, action, owner, due and unknowns")
    unknowns = value["unknowns"]
    if not isinstance(unknowns, dict) or set(unknowns) - {"action", "owner", "due"}:
        raise ValueError("unknowns must name only missing action, owner or due")
    result = {"class": UrgencyClass(value["class"]).value,
              "basis": _text(value["basis"], "the stated danger"), "unknowns": {}}
    for name in ("action", "owner", "due"):
        supplied = value[name]
        if supplied is None:
            result[name] = None
            result["unknowns"][name] = _text(unknowns.get(name), f"why {name} is unknown")
        else:
            if name in unknowns:
                raise ValueError(f"{name} cannot be both supplied and unknown")
            result[name] = _time(supplied, name) if name == "due" else _text(supplied, name)
    return result


@dataclass(frozen=True)
class UrgencyRegister:
    """One attributable urgency, with stable identity and explicit resolution.

    class_ serializes as 'class' at the API boundary (class is a Python keyword).
    Timestamps are canonical strings so the existing generic matter JSON codec
    does not need a second timestamp decoder.
    """

    urgency_id: str
    class_: UrgencyClass
    state: UrgencyState
    basis: str
    raised_by: str
    raised_at: str
    action: str | None
    owner: str | None
    due: str | None
    unknowns: dict[str, str]
    resolver: str | None = None
    resolved_at: str | None = None
    resolution_basis: str | None = None

    @classmethod
    def raise_manual(cls, urgency_id: str, instruction: dict, actor: str,
                     now: datetime) -> "UrgencyRegister":
        offered = normalise_instruction(instruction)
        return cls(_text(urgency_id, "urgency identity", 100),
                   UrgencyClass(offered["class"]), UrgencyState.LIVE, offered["basis"],
                   _text(actor, "recording advocate", 200), _time(now.isoformat(), "raised at"),
                   offered["action"], offered["owner"], offered["due"], offered["unknowns"])

    def resolve(self, actor: str, basis: str, now: datetime) -> "UrgencyRegister":
        if self.state is not UrgencyState.LIVE:
            raise ValueError("only the named live urgency can be resolved")
        observed = _time(now.isoformat(), "resolved at")
        if datetime.fromisoformat(observed) < datetime.fromisoformat(self.raised_at):
            raise ValueError("resolution cannot precede the recorded danger")
        return replace(self, state=UrgencyState.RESOLVED,
                       resolver=_text(actor, "resolving advocate", 200),
                       resolution_basis=_text(basis, "resolution basis"), resolved_at=observed)

    def as_dict(self) -> dict:
        return {"urgency_id": self.urgency_id, "class": self.class_.value,
                "state": self.state.value, "basis": self.basis, "raised_by": self.raised_by,
                "raised_at": self.raised_at, "action": self.action, "owner": self.owner,
                "due": self.due, "unknowns": dict(self.unknowns), "resolver": self.resolver,
                "resolved_at": self.resolved_at, "resolution_basis": self.resolution_basis,
                "assessment": "user_supplied_not_independently_verified",
                "action_performed": False}

    @classmethod
    def from_stored(cls, value) -> "UrgencyRegister":
        if isinstance(value, cls):
            value = value.as_dict()
        if not isinstance(value, dict):
            raise ValueError("the saved urgency is unreadable")
        offered = normalise_instruction({key: value.get(key)
                                         for key in ("class", "basis", "action", "owner",
                                                     "due", "unknowns")})
        state = UrgencyState(value.get("state"))
        if state not in (UrgencyState.LIVE, UrgencyState.RESOLVED):
            raise ValueError("a manual danger can be live or explicitly resolved, never cleared")
        raised_at = _time(value.get("raised_at"), "raised at")
        row = cls(_text(value.get("urgency_id"), "urgency identity", 100),
                  UrgencyClass(offered["class"]), UrgencyState.LIVE, offered["basis"],
                  _text(value.get("raised_by"), "recording advocate", 200), raised_at,
                  offered["action"], offered["owner"], offered["due"], offered["unknowns"])
        if state is UrgencyState.RESOLVED:
            return row.resolve(value.get("resolver"), value.get("resolution_basis"),
                               datetime.fromisoformat(_time(value.get("resolved_at"),
                                                           "resolved at")))
        if any(value.get(key) is not None
               for key in ("resolver", "resolved_at", "resolution_basis")):
            raise ValueError("a live urgency cannot hide a partial resolution")
        return row


def read_register(values) -> tuple[tuple[UrgencyRegister, ...], int]:
    if not isinstance(values, (tuple, list)):
        return (), 1
    rows: list[UrgencyRegister] = []
    unreadable = 0
    seen: set[str] = set()
    for value in values:
        try:
            row = UrgencyRegister.from_stored(value)
            if row.urgency_id in seen:
                raise ValueError("duplicate urgency identity")
            seen.add(row.urgency_id)
            rows.append(row)
        except (TypeError, ValueError, KeyError):
            unreadable += 1
    # Known nearest windows lead. Unknown-time dangers remain visible, with
    # explicit uncertainty; their position is not a determination of safety.
    rows.sort(key=lambda row: (row.state is not UrgencyState.LIVE, row.due is None,
                              row.due or "", row.raised_at, row.urgency_id))
    return tuple(rows), unreadable


@dataclass(frozen=True)
class UrgencyReceipt:
    """An accepted manual command, not its current danger state or an action taken."""

    request_key: str
    offer: dict
    matter_id: str
    urgency_id: str
    version: int

    def projected(self, *, replayed: bool = False) -> dict:
        return {"state": "urgency_recorded" if self.offer["command"] == "raise"
                else "urgency_resolved", "matter_id": self.matter_id,
                "request_key": self.request_key, "urgency_id": self.urgency_id,
                "version": self.version, "replayed": replayed,
                "assessment": "user_supplied_not_independently_verified",
                "action_performed": False}

    def as_dict(self) -> dict:
        return {"request_key": self.request_key, "offer": dict(self.offer),
                "result": self.projected()}

    @classmethod
    def from_stored(cls, value, rows: tuple[UrgencyRegister, ...],
                    matter_id: str, current_version: int) -> "UrgencyReceipt":
        """Close both nested schemas and reconcile against the surviving register.

        A raise receipt binds the immutable supplied danger, not a demand that
        it remain live. Its later explicit resolution therefore cannot erase
        the receipt or turn a successful historical retry into a fresh raise.
        """
        if not isinstance(value, dict) or set(value) != {"request_key", "offer", "result"}:
            raise ValueError("the urgency receipt envelope is unreadable")
        key, offer, result = value["request_key"], value["offer"], value["result"]
        if (type(key) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", key)
                or not isinstance(offer, dict) or not isinstance(result, dict)):
            raise ValueError("the urgency receipt identity is unreadable")
        command = offer.get("command")
        fields = {"actor_id", "command", "expected_version"}
        fields |= {"urgency"} if command == "raise" else {"urgency_id", "resolution_basis"}
        if command not in ("raise", "resolve") or set(offer) != fields:
            raise ValueError("the urgency receipt offer is not a closed command")
        actor = _text(offer["actor_id"], "recording advocate", 200)
        expected = offer["expected_version"]
        if (actor != offer["actor_id"] or type(expected) is not int or expected < 0
                or type(current_version) is not int or current_version < expected + 1):
            raise ValueError("the urgency receipt version or actor cannot be reconciled")
        normalised = {"actor_id": actor, "command": command, "expected_version": expected}
        if command == "raise":
            normalised["urgency"] = normalise_instruction(offer["urgency"])
        else:
            normalised["urgency_id"] = _text(offer["urgency_id"], "urgency identity", 100)
            normalised["resolution_basis"] = _text(offer["resolution_basis"], "resolution basis")
        if normalised != offer:
            raise ValueError("the saved urgency offer is not its normalised original")
        selected = [row for row in rows if row.urgency_id == result.get("urgency_id")]
        if len(selected) != 1:
            raise ValueError("the receipt does not name one saved danger")
        row = selected[0]
        parsed = cls(key, normalised, matter_id, row.urgency_id, expected + 1)
        projection = parsed.projected()
        if (set(result) != set(projection)
                or any(type(result[name]) is not type(actual) or result[name] != actual
                       for name, actual in projection.items())):
            raise ValueError("the saved urgency result is not a valid acceptance")
        if command == "raise":
            instruction = {name: row.as_dict()[name] for name in normalised["urgency"]}
            if row.raised_by != actor or instruction != normalised["urgency"]:
                raise ValueError("the acceptance does not match the recorded danger")
        elif (row.urgency_id != normalised["urgency_id"] or row.state is not UrgencyState.RESOLVED
              or row.resolver != actor or row.resolution_basis != normalised["resolution_basis"]):
            raise ValueError("the acceptance does not match the recorded resolution")
        return parsed


def read_receipts(values, rows: tuple[UrgencyRegister, ...],
                  matter_id: str, current_version: int) -> dict[str, UrgencyReceipt]:
    """Any malformed or ambiguous acceptance refuses mutation, never disappears."""
    if not isinstance(values, (tuple, list)):
        raise ValueError("the urgency receipt collection is unreadable")
    receipts: dict[str, UrgencyReceipt] = {}
    commands: set[tuple[str, str]] = set()
    for value in values:
        receipt = UrgencyReceipt.from_stored(value, rows, matter_id, current_version)
        identity = (receipt.urgency_id, receipt.offer["command"])
        if receipt.request_key in receipts or identity in commands:
            raise ValueError("the urgency command identity is ambiguous")
        receipts[receipt.request_key] = receipt
        commands.add(identity)
    return receipts


def project(values) -> dict:
    rows, unreadable = read_register(values)
    return {
        "state": "incomplete" if unreadable else "ok", "unreadable_records": unreadable,
        "entries": [row.as_dict() for row in rows],
        "classes": [{"class": kind.value, "label": kind.value.replace("_", " "),
                     "assessment": UrgencyState.NOT_ASSESSED.value,
                     "live_entries": sum(row.class_ is kind and row.state is UrgencyState.LIVE
                                         for row in rows)} for kind in UrgencyClass],
        "assessment": "manual_records_only_no_automatic_class_assessment",
        "taxonomy_basis": "Ten explicitly named groups in PRD B2 DOES; its eleven-class "
                          "counterexample count remains unresolved. No complete taxonomy claim.",
        "unknown_due_is_safe": False,
    }


def protective_texts(values) -> tuple[str, ...]:
    rows, unreadable = read_register(values)
    lines = []
    for row in rows:
        if row.state is not UrgencyState.LIVE:
            continue
        def supplied(name, current=row):
            value = getattr(current, name)
            return value if value is not None else f"UNKNOWN — {current.unknowns[name]}"
        lines.append(
            f"RECORDED LIVE URGENCY — {row.class_.value.replace('_', ' ')}: {row.basis}. "
            f"Supplied protective action (not performed): {supplied('action')}. "
            f"Responsible person: {supplied('owner')}. Due: {supplied('due')}. "
            "User supplied; not independently verified or assessed legal advice. "
            "An unknown time is not a safe delay.")
    if unreadable:
        lines.append("The urgency register is incomplete or unreadable; no danger is cleared.")
    lines.append("Applicable urgency classes have not been automatically assessed. "
                 "Absence of recorded danger is not an all-clear.")
    return tuple(lines)
