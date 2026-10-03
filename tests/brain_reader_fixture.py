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
        if link_field == "related_material_ids":
            scope = row.pop("matter_scope", "uncertain")
            dispute_ids = row.pop("dispute_ids", [])
            placement = row.pop("placement", None)
            owned = "matter:discussion" if placement == "matter" else "matter:unlinked"
            if "assignment_ids" not in row:
                row["assignment_ids"] = list(dispute_ids) if dispute_ids else [{
                    "current": owned,
                    "proposed": "matter:other" if sources.get("current_matter_id")
                    else owned,
                    "other": "matter:other", "none": "matter:none",
                    "uncertain": "matter:uncertain",
                }.get(scope, f"matter:{scope}")]
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
