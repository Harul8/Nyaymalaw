"""Read-only, evidence-bound input for the current plan workbook.

Use the project's Python environment: the spreadsheet renderer is a separate
runtime. This exporter does not run tests, publish evidence or alter the board.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import backlog, blueprint, evidence  # noqa: E402
from tools.blueprint_approvals import adoption_labels  # noqa: E402


def main() -> int:
    paths = [
        "docs/backlog/status.yaml", "docs/backlog/steps.yaml",
        "docs/backlog/plan.json", "docs/backlog/professional.json",
        "docs/backlog/build_rules.json", "docs/backlog/SCHEMA.md",
        "docs/backlog/evidence/class_a.json", "docs/BUILD_GUIDE.md",
        "docs/playbooks/START_A_CHANGE.md", "docs/playbooks/BUILD_A_CHANGE.md",
        "docs/playbooks/TEST_A_CHANGE.md", "docs/playbooks/SIGN_OFF_A_CHANGE.md",
        "spec/prd/part_a.js", "spec/prd/part_b.js", "spec/prd/part_c.js",
        "spec/prd/build.js", "spec/prd/helpers.js", "spec/prd/schemas.js",
        "spec/prd/gates.json", "spec/features.yaml", "docs/Nyaymalaw_PRD.docx",
        "spec/plan/view_content.json", "spec/plan/build_current_plan.mjs",
        "spec/plan/export_current_plan.py", "spec/plan/README.md",
    ]
    paths += [p.relative_to(ROOT).as_posix()
              for p in sorted((ROOT / "docs/blueprint").rglob("*"))
              if p.is_file() and p.suffix in {".md", ".json"}]
    def hashes() -> dict[str, str]:
        def content(name: str) -> bytes:
            path = ROOT / name
            if path.suffix in {".md", ".json", ".yaml", ".js", ".mjs", ".py"}:
                return path.read_text(encoding="utf-8").replace("\r\n", "\n").encode()
            return path.read_bytes()
        return {name: hashlib.sha256(content(name)).hexdigest()
                for name in paths if (ROOT / name).exists()}

    before = hashes()
    doc = backlog.load()
    issues = backlog.lint(doc)
    modules, registry = blueprint.load()
    contracts = blueprint.load_contracts()
    issues += blueprint.check_all(modules, registry, contracts)
    if issues:
        raise ValueError("Cannot publish a structurally inconsistent plan: "
                         + "; ".join(issues))
    items = {item["id"]: item for item in doc["items"]}
    for item in items.values():
        if item.get("delivery_status") == "deferred":
            item["review_on"] = backlog.calendar_date(item["review_on"]).isoformat()
        item["_plan_view"] = {
            "effective_evidence": backlog.item_result(item),
            "done": backlog.derive_done(item, items),
            "item_readiness": backlog.readiness(item, items),
            "criteria": {
                ac["id"]: backlog.proof_state(ac)
                for ac in item.get("acceptance") or []
            },
        }
    for kind in ("advocate_standards", "workflow_states", "advice_maturity",
                 "roles"):
        for row in doc["professional"][kind]:
            row["_linked_work_state"] = backlog.gap_state(
                {"links": [{"item": item} for item in row["work_items"]]},
                items,
            )
    for gap in doc["professional"]["gap_closures"]:
        gap["_linked_work_state"] = backlog.gap_state(gap, items)
    after = hashes()
    if before != after:
        raise ValueError("Plan sources changed during snapshot. Retry after edits settle.")
    doc["_snapshot"] = {
        "source_sha256": after,
        "git_head": evidence.git_identity(),
        "verification_fingerprint": evidence.verification_fingerprint(),
        "structural_lint_problems": len(issues),
        "status_semantics": (
            "Authored fields are preserved; effective proof and done use "
            "tools.backlog with current execution binding."
        ),
        "hash_semantics": "UTF-8 text .md/.json/.yaml/.js/.mjs/.py normalises CRLF to LF; other files hash exact bytes.",
    }
    doc["_blueprint"] = {"modules": modules["modules"], **contracts,
                         "adoption_labels": adoption_labels(contracts["approvals"], contracts["decisions"]),
                         "deployment_blockers": blueprint.readiness_blockers(contracts)}
    print(json.dumps(doc, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
