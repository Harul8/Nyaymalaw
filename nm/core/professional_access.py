"""One failure boundary for reading professional approval through a supplied port."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from nm.domain.professional_access import professional_status


def read_professional_status(reader: Callable[[str], object] | None,
                             account_id: str, now: datetime) -> dict:
    """Unavailable review denies an exception, never the ordinary account.

    This handles adapter and dispatch failures alike. The status is always
    computed from the supplied current record and clock; it is not cached.
    """
    try:
        record = reader(account_id) if reader is not None else None
    except Exception:  # noqa: BLE001 — an unavailable authority grants no privilege
        record = None
    return professional_status(record, account_id, now)
