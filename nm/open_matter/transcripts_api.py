"""Browser readback is an authorised projection, never the raw diagnostic archive."""
from __future__ import annotations

from nm.advise.turn_receipt_contracts import (
    TurnReceipt,
    answer_payload,
    legacy_answer_from_archive,
    release_index,
)


def _with_own_words(row: dict, archive: dict | None) -> dict:
    """THE ADVOCATE'S OWN WORDS COME BACK WITH THE CONVERSATION.

    Owner, 28 September 2026: a reopened or reloaded matter shows the whole
    conversation as it was. A turn whose checks had not cleared is released
    without admitting its message to the file, so its receipt deliberately
    keeps no narrative -- and the reopened chat showed the answer with the
    advocate's own message missing. The conversation record still holds what
    they typed. Reading it back to them is display, never admission: the
    receipt, the facts and the model's context are unchanged. Where no record
    holds the words, the row says so rather than showing a turn nobody asked.
    """
    if row.get("input_admitted") or row.get("message"):
        return row
    words = (archive.get("message") if isinstance(archive, dict)
             and not archive.get("unreadable") else None)
    if type(words) is str and words.strip():
        return {**row, "message": words, "message_source": "conversation_record"}
    return {**row, "message_source": "not_held"}


#: What a reply's rating can be. `none` is a withdrawn rating, recorded like
#: the others; `unknown` is a latest entry the store could not read back, and
#: is NEVER shown as no rating (LB-56, LB-83).
RATINGS = ("up", "down", "none")
RELEASED = ("released", "legacy_released")


def ratings(entries: tuple[dict, ...]) -> dict[str, str]:
    """Each reply's CURRENT rating: its latest entry. Entries come oldest first."""
    current: dict[str, str] = {}
    for entry in entries:
        rating = entry.get("rating")
        current[str(entry.get("turn_id"))] = (
            rating if not entry.get("unreadable") and rating in RATINGS else "unknown")
    return current


def is_released(rows: list[dict], turn_id: str) -> bool:
    """Whether this reply is a released answer on the file -- the only kind
    that is shown with a footer, and so the only kind that can be rated."""
    return any(row.get("turn_id") == turn_id and row.get("committed") is True
               and row.get("release_state") in RELEASED for row in rows)


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
            rows.append(_with_own_words(approved[turn_id], archive))
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
    rows.extend(_with_own_words(row, None)
                for turn_id, row in approved.items() if turn_id not in seen)
    return sorted(rows, key=lambda row: (str(row.get("at") or ""), str(row["turn_id"]))), problems
