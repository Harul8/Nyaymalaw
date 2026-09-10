"""BK-73 -- a path to a test is not evidence that the test passed."""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location(
        "_backlog_evidence_tool", ROOT / "tools" / "backlog.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _passing_run(tool, doc: dict) -> dict:
    tests = {}
    for item in doc["items"]:
        for acceptance in item.get("acceptance") or []:
            for level, evidence in (acceptance.get("evidence") or {}).items():
                if (level in tool.AUTOMATED_EVIDENCE
                        and evidence.get("result") == "PASS"):
                    tests[evidence["ref"]] = {"outcome": "passed"}
    fingerprint = tool.verification_fingerprint()
    return {
        "schema": 1,
        "kind": "class_a",
        "source_fingerprint": fingerprint,
        "finished_fingerprint": fingerprint,
        "started_at": "2026-09-10T00:00:00+00:00",
        "finished_at": "2026-09-10T00:01:00+00:00",
        "runner": "pytest test fixture",
        "command": "python -m pytest -m class_a -q",
        "exit_code": 0,
        "selection": "full_class_a",
        "complete": True,
        "tests": tests,
    }


def test_an_authored_pass_requires_the_exact_machine_result():
    """BK-73-AC1. Existing test, absent result: NOT RUN and not done."""
    tool = _tool()
    doc = tool.load()
    result = _passing_run(tool, doc)
    item = next(i for i in doc["items"] if i["id"] == "BK-74")
    ref = item["acceptance"][0]["evidence"]["domain_test"]["ref"]
    result["tests"].pop(ref)

    problems = tool.bind_execution_evidence(doc, result)

    assert any(ref in problem and "did not PASS" in problem
               for problem in problems)
    assert not tool.derive_done(item, {i["id"]: i for i in doc["items"]})


def test_a_source_change_makes_the_machine_result_stale():
    """BK-73-AC2. A result for another source identity proves nothing here."""
    tool = _tool()
    doc = tool.load()
    result = _passing_run(tool, doc)
    result["source_fingerprint"] = "source-before-the-change"
    problems = tool.bind_execution_evidence(doc, result)

    assert any("STALE" in problem for problem in problems)
    automated = [
        evidence for item in doc["items"]
        for acceptance in item.get("acceptance") or []
        for level, evidence in (acceptance.get("evidence") or {}).items()
        if level in tool.AUTOMATED_EVIDENCE and evidence.get("result") == "PASS"
    ]
    assert automated and all(e["_effective_result"] == "STALE"
                             for e in automated)


def test_non_automated_pass_needs_a_structured_dated_record():
    """BK-73-AC3. Prose in ``ref`` cannot certify a production action."""
    tool = _tool()
    doc = tool.load()
    result = _passing_run(tool, doc)
    measured = next(i for i in doc["items"] if i["id"] == "BK-21")
    evidence = measured["acceptance"][3]["evidence"]["production_measure"]
    evidence["ref"] = "measured on somebody's machine"

    problems = tool.bind_execution_evidence(doc, result)

    assert any("structured evidence record" in problem for problem in problems)
    assert evidence["_effective_result"] == "NOT_RUN"


def test_pushes_and_pull_requests_run_the_repository_class_a_gate():
    """BK-73-AC4. Independent CI executes the canonical evidence command."""
    workflow = ROOT / ".github" / "workflows" / "class-a.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "push:" in text and "pull_request:" in text
    assert "python tools/evidence.py ci" in text
    assert "pip install -e .[dev]" in text
