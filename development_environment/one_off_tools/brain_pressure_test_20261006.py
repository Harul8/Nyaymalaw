"""Repeat paired fabricated-output tests; preserve every observed case.

Only scripted model ports are used by the selected tests. Reordering tests
checks isolation; repeating them does not enlarge the distinct scenario set
or measure a real model's semantic error rate.
"""

import argparse
import hashlib
import json
import os
import random
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = [f"tests/test_brain_pressure_{name}.py" for name in
         ("sources", "extractor", "verification", "release")]



# Loaded before test collection so each imported recorder keeps its owning node.
# The report remains produced by the original fixture; this only records which
# executed test produced it, rather than inferring ownership from case names.
EVIDENCE_PLUGIN = r"""import json
import os
from pathlib import Path


def pytest_configure(config):
    from tests import brain_pressure_support as support
    original = support.record_case

    def owned_record_case(case_id, **kwargs):
        report = original(case_id, **kwargs)
        current = os.environ.get("PYTEST_CURRENT_TEST", "")
        if not current.endswith(" (call)"):
            raise ValueError("Paired evidence must belong to an executing test")
        report["test_nodeid"] = current[:-len(" (call)")]
        target = Path(os.environ["NM_PRESSURE_EVIDENCE_DIR"]) / (case_id + ".json")
        persisted = json.loads(target.read_text())
        persisted["test_nodeid"] = report["test_nodeid"]
        target.write_text(json.dumps(persisted, ensure_ascii=False, indent=2) + "\n")
        return report

    support.record_case = owned_record_case
"""


def selected_test_files(additional_tests):
    """Preserve the four defaults; add distinct existing repository modules."""
    selected = []
    for supplied in [*TESTS, *additional_tests]:
        path = (ROOT / supplied).resolve()
        if not path.is_relative_to(ROOT) or path.suffix != ".py" or not path.is_file():
            raise ValueError("Pressure test files must be existing repository Python modules")
        relative = path.relative_to(ROOT).as_posix()
        if relative not in selected:
            selected.append(relative)
    return selected


def source_hashes():
    paths = sorted((ROOT / "nm/brain").glob("*.py"))
    paths += sorted((ROOT / "nm/shared").glob("*.py"))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths}


def selected_source_files(supplied_files):
    """Pin extra input packets and helpers without opening files outside the repo."""
    selected = []
    for supplied in supplied_files:
        path = (ROOT / supplied).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError("Pressure sources must be existing repository files")
        relative = path.relative_to(ROOT).as_posix()
        if relative not in selected:
            selected.append(relative)
    return selected


def test_source_hashes(tests, extra_sources=()):
    paths = [ROOT / path for path in tests]
    paths += [ROOT / path for path in extra_sources]
    paths += [ROOT / "tests" / path for path in (
        "brain_pressure_support.py", "conftest.py", "test_brain_material.py",
        "brain_reader_fixture.py", "brain_continuation_fixture.py")]
    paths.append(Path(__file__).resolve())
    return {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):
            hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def run_command(command, env, log):
    result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                            capture_output=True, timeout=240, check=False)
    log.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); inspect {log}")
    return result.stdout


def run(output, rounds, additional_tests=(), additional_sources=()):
    if output.exists():
        raise ValueError("Use a fresh evidence directory; prior observations are preserved")
    tests = selected_test_files(additional_tests)
    extra_sources = selected_source_files(additional_sources)
    output.mkdir(parents=True)
    start = datetime.now(timezone.utc).isoformat()
    initial_hashes = source_hashes()
    initial_test_hashes = test_source_hashes(tests, extra_sources)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                   text=True).strip()
    env = dict(os.environ, NM_PARTIAL_RUN="1")
    python = str(ROOT / ".venv/bin/python")
    base = [python, "-m", "pytest", "-o", "addopts=", "--tb=short"]
    collected = run_command(base + tests + ["--collect-only", "-q"], env,
                            output / "collection.log")
    nodes = [line for line in collected.splitlines()
             if any(line.startswith(path + "::") for path in tests)]
    if not nodes or len(nodes) != len(set(nodes)):
        raise ValueError("A nonempty distinct test selection is required")
    evidence_plugin = output / "nm_pressure_evidence_owner.py"
    evidence_plugin.write_text(EVIDENCE_PLUGIN)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(output), str(ROOT), *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])])
    results = []
    for index in range(rounds):
        label = f"round-{index + 1}"
        folder = output / label
        folder.mkdir()
        selected = list(nodes)
        if index == 1:
            selected.reverse()
            order = "reverse"
        elif index >= 2:
            random.Random(20261006 + index).shuffle(selected)
            order = f"shuffled-seed-{20261006 + index}"
        else:
            order = "forward"
        env["NM_PRESSURE_EVIDENCE_DIR"] = str(folder / "cases")
        command = base + ["-p", "nm_pressure_evidence_owner"] + selected + [
            "-q", f"--junitxml={folder / 'results.xml'}"]
        print(f"{label}: {len(selected)} tests, {order}", flush=True)
        run_command(command, env, folder / "pytest.log")
        suites = ET.parse(folder / "results.xml").getroot()
        testcases = list(suites.iter("testcase"))
        if len(testcases) != len(nodes) or any(
                list(case.iter(tag)) for case in testcases
                for tag in ("failure", "error", "skipped")):
            raise ValueError("Every selected test must execute and pass")
        cases = [json.loads(p.read_text()) for p in sorted((folder / "cases").glob("*.json"))]
        owners = Counter(row.get("test_nodeid") for row in cases)
        if set(owners) != set(nodes) or any(count != 1 for count in owners.values()):
            raise ValueError("Every collected test must own exactly one paired evidence record")
        if len(cases) != len(nodes) or any(not row["expectation_met"] for row in cases):
            raise ValueError("Missing or failed case-level observations")
        if any(not row["user_passage"] or not row["fabricated_model_outputs"]
               for row in cases):
            raise ValueError("Every case needs both actual user words and fabricated outputs")
        if source_hashes() != initial_hashes:
            raise ValueError("Production source changed during pressure testing")
        if test_source_hashes(tests, extra_sources) != initial_test_hashes:
            raise ValueError("Pressure test source changed during execution")
        results.append({"round": label, "order": order, "test_count": len(testcases),
                        "case_count": len(cases), "cases": cases})
    identities = [{row["case_id"] for row in result["cases"]} for result in results]
    if any(ids != identities[0] for ids in identities):
        raise ValueError("The repeated runs must exercise the same distinct cases")
    original = {row["case_id"]: row for row in results[0]["cases"]}
    for result in results[1:]:
        for row in result["cases"]:
            previous = original[row["case_id"]]
            for field in ("test_nodeid", "user_passage", "fabricated_model_outputs",
                          "expected", "observed"):
                if row[field] != previous[field]:
                    raise ValueError(f"Order-dependent {field} for {row['case_id']}")
    cases = list(original.values())
    round_summaries = []
    for result in results:
        folder = output / result["round"]
        round_summaries.append({
            **{key: value for key, value in result.items() if key != "cases"},
            "observed_cases": [{"case_id": row["case_id"], "observed": row["observed"],
                                "fabricated_dispatches": len(row["calls"])}
                               for row in result["cases"]],
            "junit_sha256": hashlib.sha256((folder / "results.xml").read_bytes()).hexdigest(),
            "log_sha256": hashlib.sha256((folder / "pytest.log").read_bytes()).hexdigest(),
        })
    report = {
        "started_utc": start,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "tested_head": head,
        "production_source_hashes": initial_hashes,
        "test_source_hashes": initial_test_hashes,
        "selected_test_files": tests,
        "additional_source_files": extra_sources,
        "evidence_owner_sha256": hashlib.sha256(evidence_plugin.read_bytes()).hexdigest(),
        "distinct_tests": len(nodes),
        "distinct_cases": len(cases),
        "total_test_executions": sum(r["test_count"] for r in results),
        "scenario_counts": dict(Counter(row["scenario"] for row in cases)),
        "claim_scope_counts": dict(Counter(row["claim_scope"] for row in cases)),
        "protection_status_counts": dict(Counter(row["protection_status"] for row in cases)),
        "cases": cases,
        "rounds": round_summaries,
        "fabricated_dispatches_first_round": sum(len(row["calls"]) for row in cases),
        "live_model_calls": 0,
        "browser_calls": 0,
        "transport_qualification": (
            "Selected cases declare their scripted transport individually, including "
            "permissive Brain-owned validation, strict require_schema rejection and "
            "completed-output quarantine. Public tests may use legacy/permissive "
            "ports or strict raw fabricated ports. These contracts exercise shipped "
            "checks, not actual provider behavior or semantic quality."),
        "qualification": (
            "Scripted passages and outputs exercise shipped mechanical boundaries. "
            "Demonstrated gaps remain unprevented even when their characterization "
            "assertions pass; scripted semantic judgments prove wiring, not reviewer "
            "accuracy. Repeated runs "
            "test deterministic behavior and isolation, not unfamiliar-model quality. "
            "No population false-positive rate, semantic accuracy, token cost or "
            "production latency is established."),
    }
    (output / "observations.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items()
                      if key.endswith("counts") or key in
                      ("distinct_tests", "distinct_cases", "total_test_executions")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--test-file", type=Path, action="append", default=[],
                        help=("Add a repository test module whose every test "
                              "records paired evidence"))
    parser.add_argument("--source-file", type=Path, action="append", default=[],
                        help="Pin an additional repository input or helper across all rounds")
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("rounds must be positive")
    run(args.output.resolve(), args.rounds, args.test_file, args.source_file)
