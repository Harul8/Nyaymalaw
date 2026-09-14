"""Browser readback is an authorised projection, never the raw diagnostic archive."""
from __future__ import annotations

from nm.domain.turn_receipt import (
    TurnReceipt,
    answer_payload,
    legacy_answer_from_archive,
    release_index,
)


def project(matter, archives: tuple[dict, ...]) -> tuple[list[dict], list[str]]:
    """Prefer atomic receipts; legacy release needs both applied and ungated evidence."""
    entries = matter.turn_receipts if isinstance(matter.turn_receipts, (tuple, list)) else ()
    claimed = {receipt.turn_id for receipt in entries if isinstance(receipt, TurnReceipt)
               and type(receipt.turn_id) is str}
    valid, problems = release_index(matter)
    legacy_evidence_available = not problems
    approved = {turn_id: receipt.projected(matter.id) for turn_id, receipt in valid.items()}

    rows = []
    seen = set()
    for archive in archives:
        turn_id = archive.get("turn_id")
        if turn_id in seen:
            problems.append(f"{turn_id}: duplicate archive identity")
            continue
        seen.add(turn_id)
        if turn_id in approved:
            rows.append(approved[turn_id])
            continue
        withheld = archive.get("withheld_by")
        # Retain only explicitly supplied disclosures, never the withheld
        # recommendation, citations, model trace or a raw-json escape hatch.
        elements = archive.get("elements")
        disclosures = [row["text"] for row in elements
                       if isinstance(row, dict) and row.get("disclosure") is True
                       and type(row.get("text")) is str] if isinstance(elements, list) else []
        legacy_released = (legacy_evidence_available and turn_id not in claimed
                           and matter.has_applied(turn_id)
                           and "withheld_by" in archive and withheld == []
                           and not archive.get("unreadable"))
        if legacy_released:
            # This is evidence of a released legacy answer, not enough to
            # reconstruct the exact original offer for automatic replay.
            try:
                answer = legacy_answer_from_archive(archive)
                rows.append({**answer_payload(answer), "turn_id": turn_id,
                             "message": archive["message"], "at": archive["at"],
                             "withheld_by": [], "matter_id": matter.id,
                             "release_state": "legacy_released", "committed": True,
                             "exact_replay_available": False})
                continue
            except (KeyError, TypeError, ValueError):
                problems.append(f"{turn_id}: legacy answer does not satisfy its saved schema")
        state = "withheld" if isinstance(withheld, list) and withheld else "not_established"
        rows.append({"turn_id": turn_id, "matter_id": matter.id,
                     "message": archive.get("message", ""), "at": archive.get("at", ""),
                     "elements": [], "blocked": True, "committed": False,
                     "release_state": state,
                     "withheld_by": withheld if state == "withheld" else [],
                     "not_established": disclosures,
                     "blocked_reason": ("The archived answer was withheld; it is not advice."
                                        if state == "withheld" else
                                        "Release and successful commitment could not "
                                        "be established.")})
        if state == "not_established":
            problems.append(f"{turn_id}: release not established")
    rows.extend(row for turn_id, row in approved.items() if turn_id not in seen)
    return sorted(rows, key=lambda row: (str(row.get("at") or ""), str(row["turn_id"]))), problems
