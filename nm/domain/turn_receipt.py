"""An approved answer committed with its original instruction, not an archive."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from functools import cache
from types import UnionType
from typing import ClassVar, Union, get_args, get_origin, get_type_hints

from nm.domain.text import blank


def _json_value(value):
    if isinstance(value, (date, Enum)):
        return value.isoformat() if isinstance(value, date) else value.value
    raise TypeError(f"unsupported instruction value: {type(value).__name__}")


def fingerprint(offer: dict) -> str:
    encoded = json.dumps(offer, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, default=_json_value, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def opening_id(advocate_id: str, turn_id: str) -> str:
    """Stable lookup for an opening whose response (including file id) was lost."""
    return "mat_" + fingerprint({"advocate": advocate_id, "opening_turn": turn_id})[:32]


def answer_payload(answer) -> dict:
    """The same approved answer representation for live, replay and readback."""
    from nm.domain import brief

    value = json.loads(json.dumps(asdict(answer), default=_json_value))
    for encoded, element in zip(value["elements"], answer.elements, strict=True):
        encoded["section"] = brief.section_of(element).value
    return value


@cache
def _answer_shape(kind):
    return fields(kind), get_type_hints(kind)


def _answer_value(kind, value):
    """Closed wire values derived from the real Answer/Element field types."""
    from nm.domain.answer import Element

    origin = get_origin(kind)
    if origin in (Union, UnionType):
        for option in get_args(kind):
            try:
                return _answer_value(option, value)
            except (TypeError, ValueError):
                continue
        raise ValueError("answer value does not match its declared union")
    if kind is type(None):
        if value is not None:
            raise ValueError("answer value must be null")
        return None
    if origin is tuple:
        if not isinstance(value, list):
            raise ValueError("answer tuple must be a JSON list")
        return tuple(_answer_value(get_args(kind)[0], item) for item in value)
    if kind is date:
        if type(value) is not str:
            raise ValueError("answer date must be an ISO string")
        return date.fromisoformat(value)
    if isinstance(kind, type) and issubclass(kind, Enum):
        if type(value) is not str:
            raise ValueError("answer enum must be a string")
        return kind(value)
    if is_dataclass(kind):
        declared, hints = _answer_shape(kind)
        expected = {field.name for field in declared}
        if kind is Element:
            expected.add("section")
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("answer fields do not match its closed schema")
        return kind(**{field.name: _answer_value(hints[field.name], value[field.name])
                       for field in declared})
    if kind not in (str, bool, int, float) or type(value) is not kind:
        raise ValueError("answer value does not match its declared primitive")
    return value


def answer_from_payload(value: dict):
    from nm.domain.answer import Answer

    answer = _answer_value(Answer, value)
    # Section is a domain projection, not caller-authored authority. Comparing
    # the canonical round-trip also refuses representations the decoder ignored.
    if answer_payload(answer) != value:
        raise ValueError("answer payload differs from its canonical representation")
    return answer


def legacy_answer_from_archive(archive: dict):
    """Decode the actual historical archive schema, never arbitrary raw elements.

    Historical _record_turn did not persist the optional feature attribution
    tag. Its absence means no feature attribution, not a default case fact.
    Every other Answer/Element field must satisfy the current strict contract.
    """
    from nm.domain.answer import Answer, Element

    if type(archive.get("message")) is not str or type(archive.get("at")) is not str:
        raise ValueError("legacy conversation identity has invalid fields")
    payload = {field.name: archive[field.name] for field in fields(Answer)}
    if not isinstance(payload["elements"], list):
        raise ValueError("legacy answer elements must be a list")
    feature_default = next(field.default for field in fields(Element) if field.name == "feature")
    payload["elements"] = [
        ({"feature": feature_default, **row} if isinstance(row, dict) else row)
        for row in payload["elements"]]
    return answer_from_payload(payload)


@dataclass(frozen=True)
class TurnReceipt:
    # The generic store decoder enforces this opt-in before it discards fields.
    __stored_fields_closed__: ClassVar[bool] = True

    turn_id: str
    offer_fingerprint: str
    recorded_at: str
    answer: dict
    message: str = ""
    input_admitted: bool = False

    def __post_init__(self) -> None:
        self.validated_answer()

    def validated_answer(self):
        if type(self.turn_id) is not str or blank(self.turn_id):
            raise ValueError("receipt needs a nonblank turn identity")
        if type(self.offer_fingerprint) is not str or not re.fullmatch(
                r"[0-9a-f]{64}", self.offer_fingerprint):
            raise ValueError("receipt needs an exact original-offer digest")
        if type(self.recorded_at) is not str:
            raise ValueError("receipt needs a dated recording")
        observed = datetime.fromisoformat(self.recorded_at)
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError("receipt time must carry its timezone")
        if type(self.input_admitted) is not bool or type(self.message) is not str:
            raise ValueError("receipt admission flag and message have invalid types")
        if not self.input_admitted and self.message != "":
            raise ValueError("an unadmitted receipt must not retain the narrative")
        return answer_from_payload(self.answer)

    def projected(self, matter_id: str) -> dict:
        return {**answer_payload(self.validated_answer()),
                "turn_id": self.turn_id, "matter_id": matter_id,
                "message": self.message, "at": self.recorded_at,
                "release_state": "released", "committed": True,
                "input_admitted": self.input_admitted, "withheld_by": []}


def release_index(matter) -> tuple[dict[str, TurnReceipt], list[str]]:
    """One release boundary: strict receipt plus exactly one applied ledger entry."""
    if not isinstance(matter.turn_receipts, (tuple, list)) or not isinstance(
            matter.turns_applied, (tuple, list)):
        return {}, ["recorded release evidence is malformed or inconsistent"]
    receipts = tuple(matter.turn_receipts)
    counts = Counter(row.turn_id for row in receipts if isinstance(row, TurnReceipt)
                     and type(row.turn_id) is str)
    applied = Counter(row for row in matter.turns_applied if type(row) is str)
    approved = {}
    problems = []
    for row in receipts:
        try:
            if not isinstance(row, TurnReceipt):
                raise ValueError("unknown receipt type")
            row.validated_answer()
            if counts[row.turn_id] != 1 or applied[row.turn_id] != 1:
                raise ValueError("receipt and applied-turn ledger are inconsistent")
            approved[row.turn_id] = row
        except (KeyError, TypeError, ValueError):
            problems.append("recorded release evidence is malformed or inconsistent")
    return approved, problems
