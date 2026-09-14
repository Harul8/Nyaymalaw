"""Check blueprint ownership, not implementation or legal conformance.

The source registries determine the population. Module labels organise that
population and must never become a second authored status layer.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from assurance.common._console import utf8_console  # noqa: E402
from assurance.common._documents import safe_load  # noqa: E402

utf8_console()
GUIDES = (
    "README.md",
    "EXECUTION.md",
    "EXPERIENCE.md",
    "DATA_ARCHITECTURE.md",
    "LEGAL_DATABASE.md",
    "LEGAL_BRAIN.md",
    "SECURITY_PRIVACY.md",
    "QUALITY_PERFORMANCE.md",
)
MODULE_IDS = frozenset(f"M{i:02}" for i in range(13))
MODULE_FIELDS = frozenset({"id", "title", "requires", "guide", "features", "steps", "items"})


def load(root: Path = ROOT) -> tuple[dict, dict]:
    """Read only; don't bind or promote execution evidence."""
    status = safe_load((root / "docs/backlog/status.yaml").read_text(encoding="utf-8"))
    status["steps"] = safe_load(
        (root / "docs/backlog/steps.yaml").read_text(encoding="utf-8")
    )["steps"]
    manifest = json.loads((root / "docs/blueprint/modules.json").read_text(encoding="utf-8"))
    return manifest, status


def check(manifest: dict, registry: dict, root: Path = ROOT) -> list[str]:
    """Exact ownership + finite DAG + file/reference integrity. No semantic PASS."""
    errors: list[str] = []
    if set(manifest) != {"schema", "purpose", "modules"} or manifest.get("schema") != 1:
        errors.append("manifest: unsupported schema or fields")
    if not isinstance(manifest.get("purpose"), str) or not manifest["purpose"].strip():
        errors.append("manifest: missing purpose")
    modules = manifest.get("modules")
    if not isinstance(modules, list) or not modules:
        return errors + ["modules: empty or malformed population"]
    if any(not isinstance(row, dict) for row in modules):
        return errors + ["modules: each row must be an object"]
    ids = [row.get("id") for row in modules]
    if any(not isinstance(value, str) for value in ids):
        return errors + ["modules: non-string id"]
    if set(ids) != MODULE_IDS or len(ids) != len(MODULE_IDS):
        errors.append("modules: expected exactly M00 through M12 once each")
    populations: dict[str, set[str]] = {}
    for kind in ("items", "features", "steps"):
        source = registry.get(kind)
        if not isinstance(source, list) or not source:
            errors.append(f"{kind}: registry population empty or malformed")
            populations[kind] = set()
            continue
        values = [row.get("id") for row in source if isinstance(row, dict)]
        if len(values) != len(source) or any(not isinstance(value, str) for value in values):
            errors.append(f"{kind}: registry id malformed")
            populations[kind] = set()
            continue
        populations[kind] = set(values)
        if len(values) != len(set(values)):
            errors.append(f"{kind}: duplicate registry id")
    owners: dict[str, list[str]] = {kind: [] for kind in populations}
    edges: dict[str, list[str]] = {}
    for row in modules:
        mid = row["id"]
        if set(row) != MODULE_FIELDS:
            errors.append(f"{mid}: unsupported or missing fields (authored status is forbidden)")
        if not isinstance(row.get("title"), str) or not row["title"].strip():
            errors.append(f"{mid}: missing title")
        guide = row.get("guide")
        if guide not in GUIDES or not (root / "docs/blueprint" / str(guide)).is_file():
            errors.append(f"{mid}: guide missing or unknown")
        requires = row.get("requires")
        if not isinstance(requires, list) or any(not isinstance(x, str) for x in requires):
            errors.append(f"{mid}: malformed requires")
            requires = []
        if len(requires) != len(set(requires)):
            errors.append(f"{mid}: duplicate prerequisite")
        for dep in requires:
            if dep not in ids or dep == mid:
                errors.append(f"{mid}: invalid prerequisite {dep}")
        edges[mid] = requires
        for kind in populations:
            values = row.get(kind)
            if not isinstance(values, list) or any(not isinstance(x, str) for x in values):
                errors.append(f"{mid}: malformed {kind} mapping")
                continue
            owners[kind].extend(values)
    for kind, population in populations.items():
        counts = Counter(owners[kind])
        for missing in sorted(population - counts.keys()):
            errors.append(f"{kind}: unmapped {missing}")
        for unknown in sorted(counts.keys() - population):
            errors.append(f"{kind}: unknown {unknown}")
        for value, count in sorted(counts.items()):
            if count != 1:
                errors.append(f"{kind}: duplicate owner {value} ({count})")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(mid: str) -> None:
        if mid in visiting:
            errors.append(f"modules: dependency cycle at {mid}")
            return
        if mid in visited:
            return
        visiting.add(mid)
        for dep in edges.get(mid, []):
            visit(dep)
        visiting.remove(mid)
        visited.add(mid)

    for mid in ids:
        visit(mid)
    for guide in GUIDES:
        path = root / "docs/blueprint" / guide
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            errors.append(f"guides: missing or empty {guide}")
    # Scan every current Markdown chapter, not merely the files that happen to
    # be named by module rows. IDs in future chapters must resolve as well.
    for path in sorted((root / "docs/blueprint").glob("*.md")):
        content = path.read_text(encoding="utf-8")
        for ref in set(re.findall(r"\b(?:BK-\d+|J-\d+)\b", content)):
            if ref not in populations["items"]:
                errors.append(f"{path.name}: unknown work reference {ref}")
        for ref in set(re.findall(r"\bSTEP-[A-I]-\d{2}\b", content)):
            if ref not in populations["steps"]:
                errors.append(f"{path.name}: unknown step reference {ref}")
        for target in re.findall(r"\]\(([^)]+)\)", content):
            if target.startswith(("https://", "http://", "#")):
                continue
            local = (path.parent / target.split("#", 1)[0]).resolve()
            if not local.exists():
                errors.append(f"{path.name}: missing local link {target}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "readiness"])
    args = parser.parse_args()
    manifest, registry = load()
    contracts = load_contracts()
    errors = check_all(manifest, registry, contracts)
    print(
        "Blueprint: "
        + ", ".join(
            [f"{len(manifest['modules'])} modules"]
            + [f"{len(registry[kind])} {kind}" for kind in ("items", "features", "steps")]
        )
    )
    for error in errors:
        print(f"  FAIL: {error}")
    print(
        "Execution contracts: "
        + ", ".join(
            [
                f"{len(contracts['packets']['packets'])} packets",
                f"{len(contracts['commands']['x-commands'])} commands",
                f"{len(contracts['decisions']['choices'])} choices",
                (f"{len(contracts['applicability']['legal_sources'])} India legal "
                 f"sources / {len(contracts['applicability']['approval_packets'])} "
                 "prepared approval packets"),
                f"{len(contracts['evaluations']['synthetic_cases'])} synthetic specifications",
            ]
        )
    )
    print(f"Specification problems: {len(errors)}. Not implementation or release proof.")
    blockers = readiness_blockers(contracts) if args.command == "readiness" else []
    for blocker in blockers:
        print(f"  NOT READY: {blocker}")
    return int(bool(errors or blockers))


class DuplicateJSONKeyError(ValueError):
    """An authored JSON record is ambiguous, not an implementation exception."""


def _unique_keys(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_contracts(root: Path = ROOT) -> dict:
    contracts = {}
    for name, path in {
        "packets": "packets.json",
        "decisions": "decisions.json",
        "evaluations": "evaluations.json",
        "autonomy": "autonomy.json",
        "applicability": "india_applicability_review.json",
        "approvals": "approvals.json",
        "approval_schema": "approvals.schema.json",
        "commands": "contracts/commands.json",
    }.items():
        try:
            contracts[name] = json.loads(
                (root / "docs/blueprint" / path).read_text(encoding="utf-8"),
                object_pairs_hook=_unique_keys,
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, DuplicateJSONKeyError):
            if name != "approvals":
                raise
            # Unavailable is deliberately NOT an empty, valid adoption register.
            # Structural checking stays nonzero; readiness can now explain the
            # actual unavailable boundary instead of crashing before its report.
            contracts[name] = None
    return contracts


def check_all(manifest: dict, registry: dict, contracts: dict, root: Path = ROOT) -> list[str]:
    from assurance.control_plane.blueprint_approvals import check_approvals
    from assurance.control_plane.blueprint_autonomy import check_contract
    from assurance.control_plane.blueprint_commands import check_commands
    from assurance.control_plane.blueprint_evaluations import check_evaluations
    from assurance.control_plane.blueprint_execution import check_decisions, check_packets
    from assurance.control_plane.india_applicability import check as check_india_applicability

    errors = check(manifest, registry, root)
    if errors:
        return errors
    criteria = {ac["id"] for row in registry["items"] for ac in row.get("acceptance") or []}
    if set(contracts) != {
        "packets",
        "decisions",
        "evaluations",
        "commands",
        "approvals",
        "approval_schema",
        "autonomy",
        "applicability",
    }:
        return ["execution contracts: unknown or missing population"]
    errors.extend(check_commands(contracts["commands"], criteria))
    errors.extend(check_evaluations(contracts["evaluations"], criteria))
    errors.extend(check_decisions(contracts["decisions"], criteria))
    errors.extend(
        check_india_applicability(
            contracts["applicability"], contracts["decisions"], contracts["approvals"]
        )
    )
    errors.extend(
        check_contract(
            contracts["autonomy"],
            known_items={r["id"] for r in registry["items"]},
            known_criteria=criteria,
            known_packets={p["id"] for p in contracts["packets"]["packets"]},
        )
    )
    if errors:
        return errors
    errors.extend(
        check_packets(
            contracts["packets"],
            registry,
            manifest,
            {row["id"] for row in contracts["commands"]["x-commands"]},
            {row["id"] for row in contracts["decisions"]["choices"]},
            {row["id"] for row in contracts["evaluations"]["synthetic_cases"]},
            root,
        )
    )
    items = {r["id"]: r for r in registry["items"]}
    packets = contracts["packets"]["packets"]
    for obligation in contracts["autonomy"]["obligations"]:
        criterion = obligation["criterion"]
        if criterion not in {a["id"] for a in items[obligation["item"]].get("acceptance", [])}:
            errors.append(
                f"autonomy {obligation['id']} {criterion}: criterion is not owned by its item"
            )
        if [p["id"] for p in packets if criterion in p.get("final_criteria", [])] != [
            obligation["packet"]
        ]:
            errors.append(
                f"autonomy {obligation['id']} {criterion}: exact final packet owner differs"
            )
    if not errors:
        errors.extend(
            check_approvals(
                contracts["approvals"],
                contracts["approval_schema"],
                contracts["decisions"],
                contracts["packets"],
            )
        )
    return errors


def readiness_blockers(contracts: dict) -> list[str]:
    from assurance.control_plane.blueprint_approvals import adoption_blockers
    from assurance.control_plane.blueprint_evaluations import deployment_blockers

    blockers = adoption_blockers(
        contracts.get("approvals"), contracts["decisions"], contracts.get("packets")
    )
    blockers.extend(deployment_blockers(contracts["evaluations"]))
    blockers.append(
        "Actual current backlog evidence and scope-specific deployment review "
        "remain mandatory; this planning checker cannot authorise deployment."
    )
    return blockers


if __name__ == "__main__":
    raise SystemExit(main())
