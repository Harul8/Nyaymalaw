"""Express scripted reader proposals through the shipped operation contract."""
from __future__ import annotations


def reader_operations(rows, payload, *, link_field, infer_targets=True):
    sources = payload.get("original_input", payload)
    known = sources.get("prior_disputes" if link_field == "related_dispute_ids"
                        else "active_material", [])
    new_items = []
    changes = []
    for scripted in rows:
        row = dict(scripted)
        relation = row.pop("relation", "new")
        target_ids = row.pop(link_field, [])
        if relation == "new" and not target_ids:
            new_items.append(row)
            continue
        if not target_ids and infer_targets:
            selected = set(row.get("prior_source_ids", []))
            target_ids = [item["id"] for item in known
                          if selected.intersection(item.get("source_ids", []))]
        changes.append({**row, "relation": relation, link_field: target_ids})
    return {"new_items": new_items, "changes": changes}
