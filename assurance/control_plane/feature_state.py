"""Project the authored current feature register without rewriting its facts.

``docs/backlog/status.yaml::features[].implementation`` is the sole authority
for present implementation. A production ``@implements`` declaration says
where code claims a contract; an item ``delivers`` declaration says which
criterion is intended to prove it. Both are useful reconciliation signals,
but neither is permission to change the authored implementation value.

The exporter calls :func:`reconcile` before constructing any payload. That
check deliberately sees the raw rows from every identity-bearing source so a
dict comprehension cannot erase the duplicate it was meant to detect.
"""
from __future__ import annotations

import collections
import pathlib
import sys
from dataclasses import dataclass
from typing import Iterable

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Keep this in the same order as assurance.control_plane.backlog.proof_state: the earliest value
# is the least favourable effective evidence and therefore wins a roll-up.
PROOF_ORDER = ["FAIL", "BLOCKED", "STALE", "NOT_RUN", "PASS", "NOT_APPLICABLE"]
IMPLEMENTATION = ("none", "partial", "complete")
BASIS = ("registry",)


@dataclass(frozen=True)
class FeatureState:
    """One current authored fact plus its independent observed signals."""

    feature: str
    implementation: str
    implementation_basis: str
    proof: str
    status: str
    delivered_by: tuple[str, ...]
    declared_in: tuple[str, ...]

    @property
    def delivery_gap(self) -> bool:
        """Production claims the feature but no genuine delivery row names it."""
        return bool(self.declared_in) and not self.delivered_by

    @property
    def implementation_contradicted(self) -> bool:
        """Production claims a feature whose authored implementation is ``none``."""
        return bool(self.declared_in) and self.implementation == "none"

    @property
    def recorded_only_in_code(self) -> bool:
        """Compatibility spelling for the independently reported delivery gap."""
        return self.delivery_gap


def implements_map(root: pathlib.Path | None = None) -> dict[str, list[str]]:
    """Return feature id -> source files carrying ``@implements``.

    The scanner is shared with trace. ``display_root`` matters for restored
    test trees: a real copy outside this checkout must still produce stable
    repository-relative locations rather than raising ``ValueError``.
    """
    from assurance.gate.trace import SRC, scan_tree

    display_root = root or ROOT
    base = SRC if root is None else root / "backend" / "nm"
    out: dict[str, list[str]] = {}
    for args, files in scan_tree(base, "implements", display_root=display_root).items():
        if not args:
            out.setdefault("", []).extend(files)
        for fid in args:
            out.setdefault(str(fid), []).extend(files)
    return {key: sorted(set(files)) for key, files in out.items()}


def genuine_delivery_items(items: Iterable[dict]) -> list[dict]:
    """Rows allowed to supply delivery provenance and acceptance proof.

    ``delivers`` is part of the journey-row schema. A reconciliation/control
    row can inspect that relation, but letting it also *be* the relation makes
    its own acceptance evidence prove the product behaviour it is checking.
    """
    return [item for item in items
            if item.get("kind") == "journey" and item.get("delivers")]


def _duplicate_problems(values: Iterable[object], label: str) -> list[str]:
    counted = collections.Counter(str(value) for value in values if value not in (None, ""))
    return [f"{label} {value!r} appears {count} times"
            for value, count in sorted(counted.items()) if count > 1]


def reconcile(
        feature_ids: list[str],
        authored_features: list[dict],
        steps: list[dict],
        items: list[dict],
        workbook_rows: list[dict],
        declared_ids: Iterable[str],
        anchor_ids: Iterable[str],
        historical_ids: list[dict],
) -> list[str]:
    """Return every exact identity mismatch across the projection inputs.

    Missing implementation or delivery evidence is not an identity error: T3,
    T3b and T4 report those facts. Missing, duplicate, unknown, malformed or
    conflicting ids *are* identity errors, because publishing after one makes
    the generated population depend on which dict happened to win.
    """
    bad: list[str] = []

    prd_counts = collections.Counter(feature_ids)
    for fid, count in sorted(prd_counts.items()):
        if count > 1:
            bad.append(f"{fid} is defined {count} times in the PRD contracts")
    current = set(prd_counts)

    # The authored current register is exact, not a partial overlay.
    for index, row in enumerate(authored_features, 1):
        if not row.get("id"):
            bad.append(f"status.yaml feature row {index} has no id")
    bad.extend(_duplicate_problems((row.get("id") for row in authored_features),
                                   "status.yaml feature id"))
    authored_ids = {str(row.get("id")) for row in authored_features if row.get("id")}
    for fid in sorted(current - authored_ids):
        bad.append(f"{fid} is a PRD feature missing from status.yaml features")
    for fid in sorted(authored_ids - current):
        bad.append(f"status.yaml authors unknown current feature {fid!r}")

    for row in authored_features:
        fid = str(row.get("id") or "")
        implementation = row.get("implementation")
        if fid and implementation not in IMPLEMENTATION:
            bad.append(f"status.yaml feature {fid} has invalid implementation "
                       f"{implementation!r}")
        phase = row.get("phase")
        if fid in current and phase != fid[:1]:
            bad.append(f"status.yaml feature {fid} has conflicting phase {phase!r}")

    # Item and journey ids are checked before their links, so an unknown link
    # cannot be mistaken for an absent feature mapping.
    for index, item in enumerate(items, 1):
        if not item.get("id"):
            bad.append(f"status.yaml item row {index} has no id")
    bad.extend(_duplicate_problems((item.get("id") for item in items),
                                   "status.yaml item id"))
    item_ids = {str(item.get("id")) for item in items if item.get("id")}
    for row in authored_features:
        fid = str(row.get("id") or "")
        links = list(row.get("delivery_items") or [])
        bad.extend(_duplicate_problems(links, f"status.yaml feature {fid} delivery item"))
        for item_id in sorted(set(map(str, links)) - item_ids):
            bad.append(f"status.yaml feature {fid} links unknown item {item_id!r}")

    bad.extend(_duplicate_problems((step.get("id") for step in steps),
                                   "steps.yaml step id"))
    named_by_steps: set[str] = set()
    for index, step in enumerate(steps, 1):
        if not step.get("id"):
            bad.append(f"steps.yaml row {index} has no id")
        step_id = str(step.get("id") or "<unnamed>")
        names = [str(fid) for fid in step.get("features") or []]
        bad.extend(_duplicate_problems(names, f"steps.yaml {step_id} feature"))
        named_by_steps.update(names)
        for fid in sorted(set(names) - current):
            bad.append(f"steps.yaml names {fid!r}, which is not a PRD feature")
        item_links = [str(item_id) for item_id in step.get("items") or []]
        bad.extend(_duplicate_problems(item_links, f"steps.yaml {step_id} item"))
        for item_id in sorted(set(item_links) - item_ids):
            bad.append(f"steps.yaml {step_id} links unknown item {item_id!r}")
    for fid in sorted(current - named_by_steps):
        bad.append(f"{fid} is a PRD feature that no journey step reaches")

    for item in items:
        item_id = str(item.get("id") or "<unnamed>")
        delivers = [str(fid) for fid in item.get("delivers") or []]
        bad.extend(_duplicate_problems(delivers, f"{item_id} delivery feature"))
        if delivers and item.get("kind") != "journey":
            bad.append(f"{item_id} declares delivers but is {item.get('kind')!r}, "
                       "not a genuine journey delivery row")
        for fid in sorted(set(delivers) - current):
            bad.append(f"{item_id} delivers {fid!r}, which is not a PRD feature")

    # Historical ids are explicit data, never a D5.1-shaped exception in code.
    for index, row in enumerate(historical_ids, 1):
        if not row.get("id"):
            bad.append(f"historical feature row {index} has no id")
    bad.extend(_duplicate_problems((row.get("id") for row in historical_ids),
                                   "historical feature id"))
    history: dict[str, dict] = {
        str(row.get("id")): row for row in historical_ids if row.get("id")}
    for old_id, row in sorted(history.items()):
        disposition = row.get("disposition")
        canonical = row.get("canonical_id")
        if old_id in current:
            bad.append(f"historical feature id {old_id!r} conflicts with a current PRD id")
        if disposition not in ("alias", "tombstone"):
            bad.append(f"historical feature id {old_id!r} has invalid disposition "
                       f"{disposition!r}")
        if disposition == "alias" and not canonical:
            bad.append(f"historical alias {old_id!r} has no canonical_id")
        if canonical and canonical not in current:
            bad.append(f"historical feature id {old_id!r} resolves to unknown current id "
                       f"{canonical!r}")

    bad.extend(_duplicate_problems((row.get("Feature") for row in workbook_rows),
                                   "Feature Map id"))
    for index, row in enumerate(workbook_rows, 1):
        if not row.get("Feature"):
            bad.append(f"Feature Map data row {index} has no feature id")
    workbook_ids = {str(row.get("Feature")) for row in workbook_rows
                    if row.get("Feature")}
    allowed_workbook = current | set(history)
    for fid in sorted(workbook_ids - allowed_workbook):
        bad.append(f"Feature Map names unknown feature {fid!r}")
    for fid in sorted(current - workbook_ids):
        bad.append(f"{fid} is a PRD feature with no Feature Map row")
    for fid in sorted(set(history) - workbook_ids):
        bad.append(f"historical feature id {fid!r} has no Feature Map row")
    authored_by_id = {str(row.get("id")): row for row in authored_features if row.get("id")}
    for row in workbook_rows:
        fid = str(row.get("Feature") or "")
        if fid not in current:
            continue
        phase = row.get("Phase")
        authored_phase = authored_by_id.get(fid, {}).get("phase")
        if phase != authored_phase:
            bad.append(f"Feature Map {fid} phase {phase!r} conflicts with authored "
                       f"phase {authored_phase!r}")

    declared = {str(fid) for fid in declared_ids}
    allowed_code = current | {str(fid) for fid in anchor_ids}
    for fid in sorted(declared - allowed_code):
        bad.append(f"@implements({fid!r}) names no current feature, control or principle")

    return bad


def _proof(delivering: list[dict], proof_state) -> str:
    """Worst effective evidence from genuine delivering criteria only."""
    worst = "NOT_APPLICABLE"
    saw_any = False
    for item in delivering:
        if item.get("legacy"):
            saw_any = True
            worst = min(worst, "NOT_RUN", key=PROOF_ORDER.index)
            continue
        for criterion in item.get("acceptance") or []:
            saw_any = True
            worst = min(worst, proof_state(criterion), key=PROOF_ORDER.index)
    return worst if saw_any else "NOT_RUN"


def project(feature_ids: list[str], *, root: pathlib.Path | None = None,
            bind_execution: bool = True) -> dict[str, FeatureState]:
    """Project current status while preserving the authored implementation."""
    import yaml

    from assurance.control_plane.backlog import bind_execution_evidence, proof_state

    base = root or ROOT
    document = yaml.safe_load(
        (base / "docs" / "backlog" / "status.yaml").read_text(encoding="utf8")) or {}
    if bind_execution:
        bind_execution_evidence(document)
    authored_rows = document.get("features") or []
    counts = collections.Counter(row.get("id") for row in authored_rows)
    requested = set(feature_ids)
    malformed = sorted(str(fid) for fid, count in counts.items()
                       if fid in requested and count != 1)
    missing = sorted(requested - set(counts))
    if malformed or missing:
        detail = [*(f"duplicate authored feature {fid}" for fid in malformed),
                  *(f"missing authored feature {fid}" for fid in missing)]
        raise ValueError("; ".join(detail))
    authored = {row["id"]: row for row in authored_rows}

    items = document.get("items") or []
    delivers: dict[str, list[dict]] = collections.defaultdict(list)
    for item in genuine_delivery_items(items):
        for fid in item.get("delivers") or []:
            delivers[str(fid)].append(item)

    declared = implements_map(root)

    def state(criterion: dict) -> str:
        return proof_state(criterion, bind_execution=bind_execution)

    out: dict[str, FeatureState] = {}
    for fid in feature_ids:
        record = authored[fid]
        implementation = record.get("implementation")
        if implementation not in IMPLEMENTATION:
            raise ValueError(f"{fid} has invalid authored implementation {implementation!r}")
        delivering = delivers.get(fid, [])
        sites = declared.get(fid, [])
        proof = _proof(delivering, state)
        if implementation == "complete" and proof == "PASS":
            status = "tested"
        elif implementation in ("partial", "complete"):
            status = "built"
        else:
            status = "decided"
        out[fid] = FeatureState(
            feature=fid,
            implementation=implementation,
            implementation_basis="registry",
            proof=proof,
            status=status,
            delivered_by=tuple(sorted(str(item["id"]) for item in delivering)),
            declared_in=tuple(sites),
        )
    return out
