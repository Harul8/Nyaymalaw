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
CONTRACT_FILES = (
    "docs/backlog/steps.yaml",
    "docs/backlog/plan.json",
    "docs/backlog/professional.json",
    "docs/backlog/build_rules.json",
    "docs/backlog/SCHEMA.md",
    "pyproject.toml",
)


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


def verification_fingerprint(root: pathlib.Path | None = None) -> str:
    """Identity of product, tests, runners, browser assets and plan contract."""
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
