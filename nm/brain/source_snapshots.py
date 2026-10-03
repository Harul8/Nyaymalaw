"""Exact reading snapshots resolved from checked continuation references."""
from __future__ import annotations

from hashlib import sha256


def source_snapshots(references: list[dict]) -> list[dict]:
    if not isinstance(references, list):
        raise ValueError("Saved references must be a list")
    snapshots = []
    seen = set()
    for reference in references:
        if not isinstance(reference, dict):
            raise ValueError("A saved reference is invalid")
        identity = reference.get("id")
        if not isinstance(identity, str) or not identity.strip() or identity in seen:
            raise ValueError("Saved references need distinct identities")
        seen.add(identity)
        kind = reference.get("type")
        if kind == "legal":
            label = reference.get("title")
            locator = reference.get("locator")
            text = reference.get("text")
            source_kind = reference.get("kind")
            if source_kind not in ("provision", "judgment"):
                raise ValueError("A legal reference needs its source kind")
            qualification = (
                "Exact retrieved passage saved with this response. Its presence "
                "does not establish applicability, binding force, or the complete source.")
        elif kind == "conversation":
            role = reference.get("role")
            turn_id = reference.get("turn_id")
            if role not in ("advocate", "nm") or not isinstance(turn_id, str) or not turn_id:
                raise ValueError("A conversation reference needs its speaker and turn")
            label = "Your saved words" if role == "advocate" else "NM's saved words"
            locator, text, source_kind = turn_id, reference.get("text"), "conversation"
            qualification = (
                "Exact saved conversation passage. A reported account is not proof; "
                "an earlier NM response is not an independent legal source.")
        elif kind in ("dispute", "material", "requirement"):
            record = reference.get("record")
            if not isinstance(record, dict):
                raise ValueError("A record reference needs its saved record")
            label = {"dispute": "Saved dispute account",
                     "material": "Saved material account",
                     "requirement": "Saved gathering item"}[kind]
            locator, source_kind = identity, "record"
            text = record.get("need") if kind == "requirement" else record.get("quoted")
            qualification = (
                "Saved gathering item, not the words of an Act or judgment. "
                "Read its cited legal passage separately."
                if kind == "requirement" else
                "Exact attributed account saved with this record. It is reported, not proved.")
        else:
            raise ValueError("The saved reference kind is unsupported")
        if any(not isinstance(value, str) or not value.strip()
               for value in (label, locator, text)):
            raise ValueError("A saved reference lacks attributable reading content")
        snapshots.append({"brain": True, "id": identity, "kind": source_kind,
                          "label": label, "locator": locator, "text": text,
                          "digest": sha256(text.encode("utf-8")).hexdigest(),
                          "qualification": qualification})
    return snapshots
