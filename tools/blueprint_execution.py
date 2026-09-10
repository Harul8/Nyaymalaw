"""Static execution contracts. These checks neither run NM nor approve a release."""
from __future__ import annotations

from collections import Counter
from pathlib import Path


def strings(value: object, *, nonempty: bool = True) -> bool:
    return (isinstance(value, list) and (bool(value) or not nonempty)
            and all(isinstance(x, str) and x.strip() for x in value)
            and len(value) == len(set(value)))


def nonblank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def cycles(edges: dict[str, list[str]]) -> list[str]:
    """Return concrete cycle paths, not just a green independent module DAG."""
    seen, stack, errors = set(), [], []

    def visit(node: str) -> None:
        if node in stack:
            errors.append("combined dependency cycle: "
                          + " -> ".join(stack[stack.index(node):] + [node]))
            return
        if node in seen:
            return
        stack.append(node)
        for dependency in edges.get(node, []):
            visit(dependency)
        stack.pop()
        seen.add(node)

    for node in edges:
        visit(node)
    return errors


CHOICE_FIELDS = {
    "id", "title", "owner_criteria", "recommendation", "rationale", "fallback",
    "approver", "local_synthetic", "approval_required_for", "approval", "sources",
}
APPROVAL_SCOPES = {
    "confidential_pilot", "production", "approved_real_model", "paid_or_long_load",
    "procurement", "new_coverage_pack", "external_action_activation",
}
EXECUTION_POLICY_FIELDS = {
    "order", "module_semantics", "criterion_semantics", "evidence_semantics",
    "path_semantics", "final_criteria", "proof_semantics", "completion_edges",
}


def check_decisions(catalog: dict, criteria: set[str]) -> list[str]:
    errors = []
    if (not isinstance(catalog, dict)
            or set(catalog) != {"schema", "note", "choices"}
            or catalog.get("schema") != 1):
        return ["decisions: malformed schema or fields"]
    rows = catalog.get("choices")
    if not isinstance(rows, list) or not rows:
        return ["decisions: empty population"]
    ids = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != CHOICE_FIELDS:
            errors.append("decision: unknown or missing fields")
            continue
        label = row["id"]
        if not nonblank(label):
            errors.append("decision: invalid id")
            continue
        ids.append(label)
        for field in ("title", "recommendation", "rationale", "fallback", "approver"):
            if not nonblank(row[field]):
                errors.append(f"{label}: missing {field}")
        owners = row["owner_criteria"]
        if not strings(owners) or not set(owners) <= criteria:
            errors.append(f"{label}: invalid owner criteria")
        if row["local_synthetic"] != "permitted_with_stated_fallback":
            errors.append(f"{label}: unknown local permission policy")
        scopes = row["approval_required_for"]
        if (not strings(scopes)
                or not {"confidential_pilot", "production"} <= set(scopes)
                or not set(scopes) <= APPROVAL_SCOPES):
            errors.append(f"{label}: confidential approval boundary missing")
        elif (label in {"CHOICE-05", "CHOICE-06"}
                and "approved_real_model" not in scopes):
            errors.append(f"{label}: real-model approval boundary missing")
        elif label == "CHOICE-06" and "paid_or_long_load" not in scopes:
            errors.append(f"{label}: paid/load approval boundary missing")
        elif label == "CHOICE-05" and "procurement" not in scopes:
            errors.append(f"{label}: procurement approval boundary missing")
        # This file owns proposed decisions only. Signed decisions belong in the
        # separately reviewed release record, never a self-authored ready flag.
        if row["approval"] is not None:
            errors.append(f"{label}: approval is not a verified release record")
        if not strings(row["sources"], nonempty=False):
            errors.append(f"{label}: malformed sources")
    if set(ids) != {f"CHOICE-{n:02}" for n in range(1, 11)} or len(ids) != 10:
        errors.append("decisions: expected ten unique CHOICE-01 through CHOICE-10")
    return errors


PACKET_FIELDS = {
    "id", "module", "title", "kind", "criteria", "prerequisites", "decisions",
    "commands", "boundaries", "inputs", "outputs", "steps", "proof", "expected",
    "rollback", "final_criteria", "requires_completed_items",
}


def check_packets(catalog: dict, registry: dict, modules: dict, commands: set[str],
                  decisions: set[str], scenarios: set[str], root: Path) -> list[str]:
    errors: list[str] = []
    expected_fields = {"schema", "purpose", "readiness_rule", "execution_policy",
                       "packets", "planning_delivery_exclusions"}
    if (not isinstance(catalog, dict) or set(catalog) != expected_fields
            or catalog.get("schema") != 1):
        return ["packets: malformed schema or fields"]
    for field in ("purpose", "readiness_rule"):
        if not nonblank(catalog[field]):
            errors.append(f"packets: missing {field}")
    policy = catalog["execution_policy"]
    if (not isinstance(policy, dict) or set(policy) != EXECUTION_POLICY_FIELDS
            or any(not nonblank(value) for value in policy.values())):
        errors.append("packets: execution policy missing, unknown or blank")
    rows = catalog.get("packets")
    if not isinstance(rows, list) or not rows:
        return ["packets: empty population"]
    if any(not isinstance(r, dict) or set(r) != PACKET_FIELDS for r in rows):
        return ["packets: unknown or missing fields; authored status forbidden"]
    ids = [r["id"] for r in rows]
    if not strings(ids):
        return ["packets: invalid or duplicate IDs"]
    items = {r["id"]: r for r in registry["items"]}
    if set(ids) & set(items):
        return ["packets: IDs collide with work-item namespace"]
    criteria = {ac["id"]: ac for r in items.values() for ac in r.get("acceptance") or []}
    module_ids = {r["id"] for r in modules["modules"]}
    exclusions = catalog["planning_delivery_exclusions"]
    planning_items = {"BK-87", "BK-89", "BK-90"}
    if (not isinstance(exclusions, list) or len(exclusions) != len(planning_items)
            or any(not isinstance(row, dict) or set(row) != {"item", "reason"}
                   or not nonblank(row.get("reason")) for row in exclusions)
            or {row.get("item") for row in exclusions if isinstance(row, dict)} != planning_items):
        errors.append("packets: only the explained BK-87, BK-89 and BK-90 planning deliveries are excluded")
    required = set()
    for iid, item in items.items():
        if item.get("legacy") or item["delivery_status"] in {"deferred", "superseded"}:
            continue
        if iid in planning_items:
            continue
        acceptance = item.get("acceptance") or []
        if not acceptance:
            errors.append(f"{iid}: active item has no acceptance criteria")
        required.update(ac["id"] for ac in acceptance)
    contributors: dict[str, list[str]] = {}
    final: dict[str, str] = {}
    counts: Counter = Counter()
    edges: dict[str, list[str]] = {}
    mapped_commands: set[str] = set()
    for row in rows:
        pid = row["id"]
        if (not nonblank(row["module"]) or row["module"] not in module_ids
                or not nonblank(row["kind"])
                or row["kind"] not in {"implementation", "verification", "review", "release"}):
            errors.append(f"{pid}: unknown module or kind")
        for field in ("title", "rollback"):
            if not nonblank(row[field]):
                errors.append(f"{pid}: missing {field}")
        for field in ("criteria", "inputs", "outputs", "steps", "expected", "decisions"):
            if not strings(row[field]):
                errors.append(f"{pid}: empty or malformed {field}")
        for field in ("prerequisites", "commands", "final_criteria", "requires_completed_items"):
            if not strings(row[field], nonempty=False):
                errors.append(f"{pid}: malformed {field}")
        # Stop this row after a shape error instead of crashing on unhashable IDs.
        if any(not strings(row[f], nonempty=False) for f in (
                "criteria", "prerequisites", "commands", "final_criteria", "decisions",
                "requires_completed_items")):
            continue
        for field, population in (("criteria", criteria), ("prerequisites", ids),
                                  ("decisions", decisions), ("commands", commands),
                                  ("requires_completed_items", items)):
            for ref in row[field]:
                if ref not in population:
                    errors.append(f"{pid}: unknown {field} reference {ref}")
        edges[pid] = row["prerequisites"] + row["requires_completed_items"]
        mapped_commands.update(row["commands"])
        for ac in row["criteria"]:
            contributors.setdefault(ac, []).append(pid)
            spec = criteria.get(ac, {})
            control = spec.get("negative_control") or {}
            if (not nonblank(spec.get("requirement"))
                    or not strings(spec.get("required_evidence"))
                    or not nonblank(control.get("mutation"))
                    or not nonblank(control.get("expected_failure"))):
                errors.append(f"{pid}: {ac} lacks criterion-specific proof specification")
        for ac in row["final_criteria"]:
            counts[ac] += 1
            final[ac] = pid
            if ac not in row["criteria"]:
                errors.append(f"{pid}: final criterion {ac} is not a contribution")
        proof = row["proof"]
        if not isinstance(proof, dict) or set(proof) != {"positive", "negative", "live"}:
            errors.append(f"{pid}: proof fields missing or unknown")
        else:
            for kind, refs in proof.items():
                if not strings(refs) or not set(refs) <= scenarios:
                    errors.append(f"{pid}: {kind} proof empty or unknown scenario")
        boundaries = row["boundaries"]
        if not isinstance(boundaries, list) or not boundaries:
            errors.append(f"{pid}: missing source boundaries")
            continue
        for boundary in boundaries:
            if (not isinstance(boundary, dict) or set(boundary) != {"path", "kind"}
                    or not nonblank(boundary.get("path"))
                    or boundary.get("kind") not in {"existing", "planned"}):
                errors.append(f"{pid}: malformed source boundary")
                continue
            path = (root / boundary["path"]).resolve()
            if not path.is_relative_to(root.resolve()):
                errors.append(f"{pid}: boundary escapes workspace {boundary['path']}")
            elif boundary["kind"] == "existing" and not path.exists():
                errors.append(f"{pid}: missing existing boundary {boundary['path']}")
    for command in sorted(commands - mapped_commands):
        errors.append(f"packets: command has no execution owner {command}")
    for ac in sorted(required - counts.keys()):
        errors.append(f"packets: no final owner for {ac}")
    for ac, count in counts.items():
        if count != 1 or ac not in required:
            errors.append(f"packets: invalid final owner population {ac} ({count})")
    # Completion is distinct from starting a scoped contribution. An item closes
    # only after its final packets AND its registered dependencies. A packet that
    # needs full item closure states that edge explicitly (e.g. release P41).
    for iid, item in items.items():
        dependencies = list(item.get("depends_on") or [])
        if any(dep not in items for dep in dependencies):
            errors.append(f"{iid}: unknown completion dependency")
        edges[iid] = dependencies + sorted({final[ac["id"]]
                        for ac in item.get("acceptance") or [] if ac["id"] in final})
    errors.extend(cycles(edges))
    packet_edges = {r["id"]: r["prerequisites"] for r in rows
                    if strings(r["prerequisites"], nonempty=False)}

    def ancestors(pid: str) -> set[str]:
        found, todo = set(), list(packet_edges.get(pid, []))
        while todo:
            value = todo.pop()
            if value not in found:
                found.add(value)
                todo.extend(packet_edges.get(value, []))
        return found

    for ac, pid in final.items():
        for contributor in contributors.get(ac, []):
            if contributor != pid and contributor not in ancestors(pid):
                errors.append(f"{pid}: reversed/missing contribution {contributor} for {ac}")
    return errors
