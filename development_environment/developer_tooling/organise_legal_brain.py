"""One-off checked substage migration; not an application entry point.

Every existing file has an explicit destination. Preserve original bytes before
moving, rewrite exact imports/current paths, and leave historical records alone.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from assurance.common._console import utf8_console  # noqa: E402

utf8_console()
WORK = ROOT / ".nm/reorganisation/legal-brain-substages"
MANIFEST = ROOT / "assurance/common/legal_brain_layout.json"
SOURCE = ROOT / "nm/legal_brain"
GROUPS = {
    "understand": """
        route brain_context briefing conversational_proposal advocate_memory
        advocate_memory_contracts advocate_memory_routes_api parties posture dispute
        threading tool_ask_advocate tool_propose_conversation tool_read_facts
        tool_read_matter tool_read_thread tool_read_turn tool_quote_matter tool_search_matter
    """,
    "retrieve": """
        acquisition_sources artefact_sources authority_weight_adapter authority_weight_port
        authority_weight_sources citator_sources corpus_evidence coverage_contracts
        coverage_port coverage_sources evidence_port identity_sources investigation
        jurisdiction_sources manifest_sources practice_playbooks practice_playbooks_adapter
        practice_playbooks_port provenance_sources resolution_sources research research_context
        search_authority search_policed search_port source_excerpt source_excerpt_contracts
        source_registry_sources checklist_sources dated_provisions
        provision_registry_composition provision_review
        provision_revision_sources tool_sources tool_identify_act tool_rank_authorities
        tool_read_judgment tool_read_paragraph tool_read_provision tool_read_source_document
        tool_resolve_citation tool_search_authorities tool_search_authority tool_treatment
        tool_read_playbook_catalogue tool_read_practice_playbook tool_research tool_finish_research
    """,
    "reason": """
        accrual adversarial cause elements_adapter elements_port elements_sources factors
        gaps grounded_file_tools issue_contracts issues matter_support opposition_work
        premise proof proof_contracts proof_read requirements requirements_contracts
        source_writes theory thresholds working_record working_record_contracts
        tool_elements_of tool_oppose tool_oppose_early tool_oppose_full tool_oppose_matter
        tool_read_opposition_status tool_finish_opposition tool_record_grounded_file_reading
        tool_record_requirements tool_read_working_inventory tool_propose_working_record
    """,
    "procedure": """
        calculation_tools event_limitation_calculation fee_calculation_contracts
        filing_requirement_adapter filing_requirement_port filing_requirement_sources
        governing_law_adapter governing_law_port governing_law_sources institution_adapter
        institution_port institution_sources interest_calculation_contracts interim_relief_adapter
        interim_relief_port interim_relief_sources limitation procedural_calculation
        procedural_period_adapter procedural_period_port procedural_period_sources
        reviewed_fee_selection reviewed_interest_selection reviewed_limitation_selection
        tool_compute_interest tool_compute_limitation tool_compute_procedural_period tool_court_fee
        tool_date_arithmetic tool_filing_requirements tool_governing_code tool_interim_test
        tool_list_deadlines tool_pre_institution_steps tool_procedural_periods
        tool_propose_fee_selection tool_propose_interest_selection tool_propose_limitation_selection
        tool_read_fee_inventory tool_read_interest_inventory tool_read_limitation_candidates
        tool_read_procedural_calculation_inputs
    """,
    "verify": """
        brain_assessment brain_finalization brain_publication brain_release checklist_review
        consistency duty early_independent_review grounding interaction_review interaction_subject
        output_checks recorded_package_subject step_dependency verifier working_scope
        tool_check_candidate_independently
    """,
    "communicate": """
        register_contracts working_explanation preview_display preview_seen preview_seen_api
        reviewed_preview reviewed_preview_api loop_progress loop_progress_api tool_submit_answer
    """,
    "orchestrate": """
        controlled_brain controlled_generations controlled_registry_composition lead lead_contracts
        loop loop_contracts loop_log_port delegation delegation_contracts nested_research
        tools tool_catalogue tool_discovery tool_offers tool_discover_tools tool_inspect_tool
        checked_input_continuation work_receipts
        generations_port turn
    """,
    "evaluate": """
        brain_evaluation brain_preview_api evaluation_history evaluation_models
        controlled_evaluations_composition runtime_capture runtime_model_tape runtime_port_tape
        replay_context strict_replay replay_capture_contracts
    """,
    "common": """
        principles_generated principles_port principles_file_adapter conversation ceiling
        reads_contracts tiers_contracts quotable_contracts curation_contracts citation_contracts
        tool_read_owner_guide
    """,
}
ASSETS = {
    "advocate-preferences.js": "understand",
    "brain-preview.html": "evaluate",
    "brain-preview.js": "evaluate",
    "matter-workspace.css": "communicate",
    "matter-workspace.js": "communicate",
    "source-reader.js": "communicate",
    "loop-progress.js": "communicate",
}
TEXT_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".css", ".html", ".ps1", ".cmd",
                 ".toml", ".yaml", ".yml", ".json", ".md", ".sh"}
TOP_FILES = ("README.md", "CLAUDE.md", "pyproject.toml", "start.ps1", "start.cmd")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def active_files() -> tuple[Path, ...]:
    files = []
    for home in ("nm", "tests", "assurance", "pipeline", "operations", "docs",
                 "development_environment/developer_tooling"):
        for path in (ROOT / home).rglob("*"):
            relative = path.relative_to(ROOT).as_posix()
            if (not path.is_file() or path.suffix not in TEXT_SUFFIXES
                    or any(part in {"__pycache__", "node_modules"} for part in path.parts)
                    or "/evidence/" in relative or "/archives/" in relative
                    or path in {MANIFEST, ROOT / "assurance/common/journey_layout.json"}
                    or path.name in {"reorganise_journey.py", "move_journey_files.ps1"}
                    or path == Path(__file__).resolve()):
                continue
            files.append(path)
    files.extend(ROOT / name for name in TOP_FILES)
    return tuple(sorted(set(path for path in files if path.is_file())))


def plan() -> None:
    if MANIFEST.exists() or (WORK / "checkpoint.json").exists():
        raise SystemExit("A recorded substage migration already exists; do not overwrite it")
    assignments: dict[str, str] = {}
    for group, members in GROUPS.items():
        for stem in members.split():
            name = stem + ".py"
            if name in assignments:
                raise SystemExit(f"Two groups own {name}")
            assignments[name] = group
    actual = {path.name for path in SOURCE.glob("*.py") if path.name != "__init__.py"}
    if actual != set(assignments):
        raise SystemExit(f"Allocation mismatch; missing={sorted(actual-set(assignments))}; "
                         f"extra={sorted(set(assignments)-actual)}")
    layout = read_json(ROOT / "nm/source_layout.json")
    rows = []
    for name, group in sorted(assignments.items()):
        old_path = "nm/legal_brain/" + name
        path = f"nm/legal_brain/{group}/{name}"
        before = old_path.removesuffix(".py").replace("/", ".")
        rows.append({"old_path": old_path, "path": path, "old_module": before,
                     "module": path.removesuffix(".py").replace("/", "."),
                     "role": layout["modules"][before],
                     "sha256_before": digest(ROOT / old_path)})
    assets = {}
    for name, group in ASSETS.items():
        old_path = "nm/legal_brain/" + name
        if layout["browser_assets"].get(name) != old_path:
            raise SystemExit(f"Unrecorded browser owner: {name}")
        assets[name] = {"old_path": old_path,
                        "path": f"nm/legal_brain/{group}/{name}",
                        "sha256_before": digest(ROOT / old_path)}
    WORK.mkdir(parents=True)
    preserved = {"schema": 1, "modules": rows,
                 "expected_roles": dict(sorted(Counter(row["role"] for row in rows).items())),
                 "browser_assets": assets}
    manifest_path = WORK / "planned-layout.json"
    manifest_path.write_text(json.dumps(preserved, indent=2) + "\n", encoding="utf-8")
    candidates = set(active_files()) | {ROOT / row["old_path"] for row in rows}
    candidates |= {ROOT / row["old_path"] for row in assets.values()}
    candidates |= {ROOT / "assurance/common/journey_layout.json"}
    workbook = ROOT / "docs/Nyaymalaw_Implementation_Plan.xlsx"
    candidates.add(workbook)
    candidates.add(ROOT / "development_environment/reviews/LEGAL_BRAIN_STATUS_20260927.md")
    checkpoint = {}
    for path in sorted(candidates):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        destination = WORK / "originals" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        checkpoint[relative] = digest(path)
    (WORK / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2) + "\n")
    result = subprocess.run(["git", "status", "--short"], cwd=ROOT, capture_output=True,
                            text=True, check=True)
    (WORK / "git-status-before.txt").write_text(result.stdout, encoding="utf-8")
    print(f"Planned {len(rows)} exact modules, {len(assets)} browser assets; "
          f"captured {len(checkpoint)} original files")


def move_and_rewrite() -> None:
    if MANIFEST.exists():
        raise SystemExit("Migration already published; refuse another move")
    planned = read_json(WORK / "planned-layout.json")
    before_layout = read_json(ROOT / "nm/source_layout.json")
    movements = planned["modules"] + list(planned["browser_assets"].values())
    for row in movements:
        before, after = ROOT / row["old_path"], ROOT / row["path"]
        if (digest(before) != row["sha256_before"] or after.exists()
                or before.is_symlink() or after.is_symlink()
                or ROOT.resolve() not in after.resolve().parents):
            raise SystemExit(f"Move custody refused: {row['old_path']}")
    for row in movements:
        before, after = ROOT / row["old_path"], ROOT / row["path"]
        after.parent.mkdir(parents=True, exist_ok=True)
        before.rename(after)
        if digest(after) != row["sha256_before"]:
            raise SystemExit(f"Move changed bytes: {row['path']}")
    mappings = {row["old_module"]: row["module"] for row in planned["modules"]}
    paths = {row["old_path"]: row["path"] for row in movements}
    module_pattern = re.compile(r"\b(?:" + "|".join(
        re.escape(name) for name in sorted(mappings, key=len, reverse=True)) + r")(?!\w)")
    path_pattern = re.compile("|".join(re.escape(name) for name in sorted(paths, key=len,
                                                                            reverse=True)))
    changed = []
    for path in active_files():
        original = path.read_bytes()
        try:
            text = original.decode("utf-8")
        except UnicodeDecodeError:
            continue
        text = path_pattern.sub(lambda match: paths[match.group()], text)
        text = module_pattern.sub(lambda match: mappings[match.group()], text)
        # Only two existing files derive the checkout from their own file depth.
        if path.name in {"practice_playbooks_adapter.py", "principles_file_adapter.py"}:
            text = text.replace("Path(__file__).resolve().parents[2]",
                                "Path(__file__).resolve().parents[3]")
        updated = text.encode("utf-8")
        if updated != original:
            path.write_bytes(updated)
            changed.append(path.relative_to(ROOT).as_posix())
    for row in planned["modules"]:
        role = before_layout["modules"].pop(row["old_module"])
        if role != row["role"]:
            raise SystemExit("The original architectural role changed")
        before_layout["modules"][row["module"]] = role
    for group in GROUPS:
        init = SOURCE / group / "__init__.py"
        if init.exists():
            raise SystemExit(f"Unexpected existing initializer {init}")
        init.write_text(f'"""Legal-brain {group} capability; no runtime exports."""\n',
                        encoding="utf-8")
        before_layout["modules"]["nm.legal_brain." + group] = "domain"
    before_layout["modules"] = dict(sorted(before_layout["modules"].items()))
    before_layout["expected_roles"] = dict(sorted(Counter(
        before_layout["modules"].values()).items()))
    for name, row in planned["browser_assets"].items():
        before_layout["browser_assets"][name] = row["path"]
    (ROOT / "nm/source_layout.json").write_text(json.dumps(before_layout, indent=2) + "\n",
                                               encoding="utf-8")
    MANIFEST.write_text(json.dumps(planned, indent=2) + "\n", encoding="utf-8")
    (WORK / "rewritten.json").write_text(json.dumps(changed, indent=2) + "\n")
    print(f"Moved {len(movements)} files, rewrote {len(changed)} current text files; "
          f"published {len(before_layout['modules'])} explicit identities")


def verify() -> None:
    planned = read_json(MANIFEST)
    for row in planned["modules"] + list(planned["browser_assets"].values()):
        if (ROOT / row["old_path"]).exists() or not (ROOT / row["path"]).is_file():
            raise SystemExit(f"Destination mismatch: {row['path']}")
    preserved = read_json(WORK / "checkpoint.json")
    for relative in ("docs/Nyaymalaw_Implementation_Plan.xlsx",
                     "assurance/common/journey_layout.json",
                     "development_environment/reviews/LEGAL_BRAIN_STATUS_20260927.md"):
        if digest(ROOT / relative) != preserved[relative]:
            raise SystemExit(f"Unrelated preserved record changed: {relative}")
    def tests(directory):
        population = set()
        for path in directory.rglob("test*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("test_"):
                        population.add((path.relative_to(directory).as_posix(), node.name))
        return population
    before, after = tests(WORK / "originals/tests"), tests(ROOT / "tests")
    if before - after:
        raise SystemExit(f"Original test functions missing: {sorted(before-after)}")
    print(f"Verified 221 destinations, unchanged workbook/historical manifest/review; "
          f"all {len(before)} original test identities retained ({len(after-before)} added)")


def repair_imports() -> None:
    """Split package-import lists by their explicit new owners, preserving aliases."""
    planned = read_json(MANIFEST)
    owners = {row["old_module"]: row["module"] for row in planned["modules"]}
    changed = []
    for path in active_files():
        if path.suffix != ".py":
            continue
        original = path.read_bytes()
        before = original
        tree = ast.parse(original.decode("utf-8"), filename=str(path))
        lines = original.splitlines(keepends=True)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        replacements = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module != "nm.legal_brain":
                continue
            grouped = {}
            for name in node.names:
                old = node.module + "." + name.name
                if old not in owners or node.level:
                    raise SystemExit(f"Unresolved package import: {path}: {old}")
                parent = owners[old].rsplit(".", 1)[0]
                grouped.setdefault(parent, []).append(
                    name.name + (" as " + name.asname if name.asname else ""))
            indent = lines[node.lineno - 1][:node.col_offset].decode("utf-8")
            rendered = ("\n" + indent).join(
                "from " + parent + " import " + ", ".join(names)
                for parent, names in grouped.items())
            start = offsets[node.lineno - 1] + node.col_offset
            end = offsets[node.end_lineno - 1] + node.end_col_offset
            replacements.append((start, end, rendered.encode("utf-8")))
        if replacements:
            for start, end, replacement in sorted(replacements, reverse=True):
                original = original[:start] + replacement + original[end:]
            ast.parse(original.decode("utf-8"), filename=str(path))
            pending = WORK / (".pending-" + uuid.uuid4().hex)
            pending.write_bytes(original)
            if path.read_bytes() != before:
                raise SystemExit(f"Concurrent edit refused: {path}; candidate at {pending}")
            os.replace(pending, path)
            changed.append(path.relative_to(ROOT).as_posix())
    (WORK / "import-repairs.json").write_text(json.dumps(changed, indent=2) + "\n")
    print(f"Rebound package imports in {len(changed)} sources; aliases preserved")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("operation", choices=("plan", "move", "verify", "repair-imports"))
    operation = cli.parse_args().operation
    {"plan": plan, "move": move_and_rewrite, "verify": verify,
     "repair-imports": repair_imports}[operation]()
