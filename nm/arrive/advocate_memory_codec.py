"""Exact bounded decoder for the existing account preference record."""
from __future__ import annotations

import json

from nm.arrive.advocate_memory_contracts import AdvocateMemory
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
