"""Express scripted reader proposals through the shipped operation contract."""
from __future__ import annotations

from copy import deepcopy
from functools import wraps


def reader_repairs(data, schema):
    """Express scripted operation rows under the selected correction schema.

    This is fixture transport only: it does not validate sources or improve
    the supplied proposals. The scripted row order owns each failed field.
    """
    if "repairs" not in schema.get("properties", {}):
        return data
    units = schema["properties"]["repairs"]["properties"]
    cursors = {}
    repaired = {}
    for identity in units:
        field = identity.split(":", 1)[0]
        index = cursors.get(field, 0)
        cursors[field] = index + 1
        rows = data.get(field, [])
        repaired[identity] = {"proposals": rows[index:index + 1]}
    return {"repairs": repaired}


def source_treatment_reply(operation, payload):
    """Script the separately owned source treatment, without keyword inference."""
    if operation != "classify_account_sources":
        return None
    return {"source_treatments": {identity: {
        "content_role": "reported_matter_account",
        "reason": "The scripted source-treatment decision reports account content.",
    } for identity in payload["source_ids"]}}


def classified_verifier(function):
    """Supply explicit scripted provenance for direct owning-boundary tests."""
    @wraps(function)
    def called(model, **kwargs):
        if "source_treatments" not in kwargs:
            kwargs["source_treatments"] = scripted_source_treatments(
                kwargs["earlier"], kwargs["latest"])
        return function(model, **kwargs)

    return called


def scripted_source_treatments(earlier, latest, *, roles=None, turn_id="current"):
    """Explicit canonical provenance decisions for offline fixtures."""
    from nm.brain.material import addressed_sources

    _, current, prior = addressed_sources(earlier, latest)
    roles = roles or {}
    rows = {key: {"turn_id": ref.turn_id, "role": ref.role, "quoted": ref.quoted,
                  "content_role": roles.get(key, "reported_matter_account"),
                  "reason": "Scripted treatment"}
            for key, ref in prior.items() if ref.role == "advocate"}
    rows.update({key: {"turn_id": turn_id, "role": "advocate", "quoted": text,
                       "content_role": roles.get(key, "reported_matter_account"),
                       "reason": "Scripted treatment"} for key, text in current.items()})
    return rows


def reviewed_record_verdicts(payload, data, *, scripted_full_scope=False):
    """Carry explicit offline judgments through the shipped record checks.

    Normal public provider fixtures explicitly opt into full authorised
    coverage independently of candidate count or execution receipts. Direct
    omission/correction fixtures do not opt in; every supplied coverage value,
    including invalid values, is kept. This supplies a scripted judgment,
    never an assessment by production code.
    """
    result = deepcopy(data)
    if not isinstance(result, dict) or not isinstance(result.get("verdicts"), list):
        return result
    if (scripted_full_scope and payload.get("review_scope") is not None
            and "coverage_source_ids" in payload):
        result.setdefault("coverage", {
            "state": "complete", "missing_source_ids": [],
            "reason": ("The normal offline fixture declares the complete authorised "
                       "account scope represented by the supplied records and proposals."),
        })
    candidates = {row["candidate_id"]: row for row in payload.get("candidates", [])}
    for row in result.get("verdicts", []):
        if not isinstance(row, dict) or not isinstance(row.get("candidate_id"), str):
            continue
        candidate = candidates.get(row.get("candidate_id"))
        if candidate is None:
            continue
        accepted = row.get("verdict") == "accept"
        sources = candidate.get("allowed_account_source_ids", [])
        row.setdefault("account_check", {
            "content_role": "reported_matter_account" if accepted else "uncertain",
            "supported": accepted, "introduces_legal_analysis": False,
            "source_ids": sources[:1] if accepted else [],
            "reason": "The scripted record decision checks the attributed account layer.",
        })
        account = row.get("account_check")
        if isinstance(account, dict) and isinstance(account.get("source_ids"), list):
            account.setdefault("source_checks", [{
                "source_id": source_id,
                "supplies_account_content": True, "supports_proposal": True,
                "reason": "The scripted source decision supplies attributed account content.",
            } for source_id in account["source_ids"]])
        row.setdefault("target_checks", [{
            "target_id": target, "identity_relation": "same_underlying_account",
            "account_preserved": accepted, "required_peer_ids": [],
            "reason": "The scripted operation retains the selected account's identity.",
        } for target in candidate.get("related_dispute_ids",
                                      candidate.get("related_material_ids", []))])
    return result


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
