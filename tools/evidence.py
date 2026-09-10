"""Execution evidence for the backlog control plane.

``status.yaml`` states the claim and the evidence level it requires.  It does
not get to state that a test passed.  That verdict comes from a pytest result
whose source fingerprint still matches this tree.

    python tools/evidence.py run       run the complete Class-A selection
    python tools/evidence.py promote   publish that local result in the repo
    python tools/evidence.py verify    verify the published result is current
    python tools/evidence.py ci        run, verify the run and check the backlog
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from typing import Any

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools._console import utf8_console  # noqa: E402

utf8_console()

LOCAL_CLASS_A = ROOT / ".nm" / "class_a_results.json"
PUBLISHED_CLASS_A = ROOT / "docs" / "backlog" / "evidence" / "class_a.json"

SOURCE_TREES = ("nm", "tests", "tools", "web")
SOURCE_SUFFIXES = {".py", ".js", ".css", ".html"}
# Planning contracts are inputs, never generated execution verdicts. Enumerate
# this tree rather than maintaining a second, inevitably incomplete file list.
CONTRACT_TREES = ("docs/blueprint",)
CONTRACT_SUFFIXES = {".json", ".md"}
CONTRACT_FILES = (
    "docs/backlog/steps.yaml",
    "docs/backlog/plan.json",
    "docs/backlog/professional.json",
    "docs/backlog/build_rules.json",
    "docs/backlog/SCHEMA.md",
    "pyproject.toml",
    # THE PROMISES THEMSELVES. BK-80-AC3.
    #
    # Until 10 September 2026 this fingerprint covered nm, tests, tools, web and
    # the plan contracts -- and NOT the PRD, the generated specification, or the
    # rules the build says it follows. So changing a PRD requirement, a release
    # threshold or a playbook obligation left every existing PASS reading as
    # current, when the claim those records were about had just changed
    # underneath them. Evidence names its subject or it is not evidence.
    #
    # `spec/release.yaml` is the authored thresholds with owners and cadence.
    # `spec/coverage.yaml` is deliberately ABSENT: it is what releasegate
    # MEASURED, and folding a verdict into the identity of the thing it judges
    # makes every measurement invalidate itself.
    #
    # WHAT IS NOT COVERED, STATED RATHER THAN LEFT TO BE NOTICED. BK-80-AC3
    # names three populations -- authoritative PRD, generated specification,
    # applicable guide rules -- and this is exactly those three. It does NOT
    # cover `spec/manifest.yaml` (which Acts the corpus reconciles) or
    # `docs/BASELINE.md` (what the corpus measurably holds). Both are claims
    # about KNOWLEDGE rather than about behaviour, a change to either is a
    # corpus event with its own controls, and widening this digest to them
    # would make every corpus refresh restale every behavioural proof. That is
    # an admitted gap with a reason, not an oversight; if a promise is ever
    # written into the manifest, it belongs here and this comment is wrong.
    "docs/BUILD_GUIDE.md",
    "spec/release.yaml",
    "spec/evals.yaml",
    "spec/anchors.yaml",
    "spec/schemas.yaml",
    "spec/gates.yaml",
)

#: The PRD's editable source, and the playbooks that bind the build method.
#: Enumerated as trees so a new chapter or a fifth playbook is covered the day
#: it is written rather than the day somebody remembers to list it.
PROMISE_TREES = {
    "spec/prd": {".js"},
    "docs/playbooks": {".md"},
}

#: The generated specification carries both halves: the PROMISE (what the
#: product must do, never do, produce and evaluate) and the VERDICT (what the
#: registry currently says about it). Only the promise belongs in an identity.
#:
#: Fold in the verdict and the fingerprint moves every time evidence is
#: recorded -- which restales the evidence that just moved it. That is not a
#: strict check, it is a check that can never be satisfied.
FEATURE_SPEC = "spec/features.yaml"
DERIVED_FEATURE_FIELDS = frozenset({
    "status", "implementation", "implementation_basis", "proof",
    "delivered_by",
})


def _bytes(path: pathlib.Path) -> bytes:
    """Hash text identically on CRLF and LF checkouts."""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").encode()


def _status_contract(root: pathlib.Path) -> bytes:
    """The claim being tested, without its mutable verdict or workflow state."""
    path = root / "docs" / "backlog" / "status.yaml"
    if not path.exists():
        return b"<absent:docs/backlog/status.yaml>"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = []
    for item in doc.get("items") or []:
        rows.append({
            "id": item.get("id"),
            "kind": item.get("kind"),
            "priority": item.get("priority"),
            "depends_on": item.get("depends_on") or [],
            "acceptance": [{
                "id": ac.get("id"),
                "requirement": ac.get("requirement"),
                "required_evidence": ac.get("required_evidence") or [],
                "negative_control": ac.get("negative_control"),
            } for ac in item.get("acceptance") or []],
        })
    return json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()


def _feature_promises(root: pathlib.Path) -> bytes:
    """The generated spec's promises, without the registry's verdict on them.

    THE DENY LIST IS THE SAFE DIRECTION. A promise field added to the exporter
    tomorrow is covered automatically; only the five fields named as derived
    are dropped. An allow-list would silently exclude the new promise, and a
    fingerprint that quietly stops covering something is worse than one that
    churns -- churn is visible, a gap is not.
    """
    path = root / FEATURE_SPEC
    if not path.exists():
        return f"<absent:{FEATURE_SPEC}>".encode()
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = [{k: v for k, v in (row or {}).items()
             if k not in DERIVED_FEATURE_FIELDS}
            for row in doc.get("features") or []]
    return json.dumps(rows, sort_keys=True, separators=(",", ":"),
                      default=str).encode()


def verification_fingerprint(root: pathlib.Path | None = None) -> str:
    """Identity of the product, its tests, its runners AND ITS PROMISES.

    Covers, in one digest: `nm`, `tests`, `tools` and `web`; the plan
    contracts; the authoritative PRD source and the playbooks; the generated
    specification's promise half; and the backlog's claim without its verdict.

    A change to any of those makes prior conformance evidence STALE, which is
    the point -- proof is about a claim, and a claim that moved is a different
    claim. What is deliberately excluded is every generated verdict:
    `spec/coverage.yaml`, the derived feature status fields, and the recorded
    evidence files themselves.
    """
    root = root or ROOT
    digest = hashlib.sha256()
    for top in SOURCE_TREES:
        base = root / top
        if not base.exists():
            digest.update(f"<absent:{top}>".encode())
            continue
        for path in sorted(p for p in base.rglob("*")
                           if p.is_file() and p.suffix in SOURCE_SUFFIXES
                           and "__pycache__" not in p.parts):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(_bytes(path))
    for relative in CONTRACT_FILES:
        path = root / relative
        digest.update(relative.encode())
        digest.update(_bytes(path) if path.exists()
                      else f"<absent:{relative}>".encode())
    for relative in CONTRACT_TREES:
        base = root / relative
        digest.update(relative.encode())
        if not base.exists():
            digest.update(b"<absent>")
        else:
            for path in sorted(p for p in base.rglob("*")
                               if p.is_file() and p.suffix in CONTRACT_SUFFIXES):
                digest.update(path.relative_to(root).as_posix().encode())
                digest.update(_bytes(path))
    for relative, suffixes in sorted(PROMISE_TREES.items()):
        base = root / relative
        digest.update(relative.encode())
        if not base.exists():
            digest.update(b"<absent>")
            continue
        for path in sorted(p for p in base.rglob("*")
                           if p.is_file() and p.suffix in suffixes
                           and "node_modules" not in p.parts):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(_bytes(path))
    digest.update(b"spec/features.promises")
    digest.update(_feature_promises(root))
    digest.update(b"docs/backlog/status.contract")
    digest.update(_status_contract(root))
    return digest.hexdigest()[:20]


def git_identity() -> str:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
            text=True, timeout=10, check=False).stdout.strip() or "unknown"
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT,
            capture_output=True, text=True, timeout=10, check=False)
        return head + ("+dirty" if dirty.stdout.strip() else "")
    except Exception:  # noqa: BLE001 -- identity remains explicit as unknown
        return "unknown"


def load_result(path: pathlib.Path = PUBLISHED_CLASS_A) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def validate_class_a(result: dict[str, Any], *,
                     root: pathlib.Path | None = None) -> list[str]:
    root = root or ROOT
    bad: list[str] = []
    if result.get("schema") != 1 or result.get("kind") != "class_a":
        bad.append("Class-A evidence is absent or has an unsupported schema")
    if result.get("source_fingerprint") != verification_fingerprint(root):
        bad.append("Class-A evidence is STALE for the current source fingerprint")
    if result.get("finished_fingerprint") != result.get("source_fingerprint"):
        bad.append("the source tree moved while Class-A evidence was running")
    if result.get("exit_code") != 0 or not result.get("complete"):
        bad.append("the recorded Class-A execution did not complete successfully")
    if result.get("selection") != "full_class_a":
        bad.append("the recorded Class-A execution was a narrowed selection")
    tests = result.get("tests")
    if not isinstance(tests, dict) or not tests:
        bad.append("the recorded Class-A execution has an empty test population")
    for field in ("started_at", "finished_at", "runner", "command"):
        if not result.get(field):
            bad.append(f"Class-A evidence has no {field}")
    return bad


def exact_outcome(result: dict[str, Any], nodeid: str) -> str | None:
    row = (result.get("tests") or {}).get(nodeid)
    return row.get("outcome") if isinstance(row, dict) else None


def run_class_a() -> int:
    LOCAL_CLASS_A.parent.mkdir(parents=True, exist_ok=True)
    if LOCAL_CLASS_A.exists():
        LOCAL_CLASS_A.unlink()
    env = os.environ.copy()
    env["NM_CLASS_A_EVIDENCE_FILE"] = str(LOCAL_CLASS_A)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "class_a", "-q"],
        cwd=ROOT, env=env, check=False).returncode


def promote() -> int:
    result = load_result(LOCAL_CLASS_A)
    bad = validate_class_a(result)
    if bad:
        for problem in bad:
            print(f"  {problem}")
        print("EVIDENCE NOT PROMOTED")
        return 1
    PUBLISHED_CLASS_A.parent.mkdir(parents=True, exist_ok=True)
    PUBLISHED_CLASS_A.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"EVIDENCE PROMOTED  {result['source_fingerprint']}  "
          f"{len(result['tests'])} recorded nodes")
    return 0


def verify(path: pathlib.Path = PUBLISHED_CLASS_A) -> int:
    result = load_result(path)
    bad = validate_class_a(result)
    for problem in bad:
        print(f"  {problem}")
    if bad:
        print("EVIDENCE FAILED")
        return 1
    print(f"EVIDENCE OK  {result['source_fingerprint']}  "
          f"{len(result['tests'])} recorded nodes")
    return 0


def ci() -> int:
    code = run_class_a()
    if code:
        return code
    if verify(LOCAL_CLASS_A):
        return 1
    if verify(PUBLISHED_CLASS_A):
        return 1
    return subprocess.run(
        [sys.executable, "tools/backlog.py", "check"], cwd=ROOT,
        check=False).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "promote", "verify", "ci"))
    args = parser.parse_args(argv)
    if args.command == "run":
        return run_class_a()
    if args.command == "promote":
        return promote()
    if args.command == "verify":
        return verify()
    return ci()


if __name__ == "__main__":
    raise SystemExit(main())
