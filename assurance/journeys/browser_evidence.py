"""What a browser run must have produced before it can prove anything.

BK-80-AC2 (the reader) and BK-51-AC1 (the runner's own reconciliation).

    from assurance.journeys.browser_evidence import problems, row_for

THE TWO HALVES OF ONE FACT, IN ONE FILE ON PURPOSE. A writer that emits less
than the reader demands produces evidence nobody can use; a reader that demands
less than the writer emits accepts runs that did not happen. Splitting them
across `assurance/journeys/journey.py` and `assurance/control_plane/backlog.py` is how they would
drift, and
CLAUDE.md §4 asks what refuses the second copy — the answer is that the
manifest, the required fields and the completeness rule are all defined here
and imported by both.

WHAT A BROWSER REPORT CAN LOOK LIKE WHILE PROVING NOTHING
-----------------------------------------------------------
    the run crashed at phase 3    -- rows exist, and they are green
    a phase was renamed away      -- nothing asks for it, so nothing is missing
    a row appears twice           -- the count says 24 and the population is 23
    the tree moved mid-run        -- half the rows are about different code
    last week's screenshots       -- the artifacts list is evidence of nothing

Every one of those is a report whose `rows` are all `PASS`. `bind_execution_
evidence` checked the fingerprint and one row's state, so every one of them
would have conferred a PASS on the criterion that named it.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]

SCHEMA = 2

#: A row's state, worst first. `NOT RUN` is a state and not an absence: a phase
#: that errored in collection reported something, and a phase nobody asked for
#: reported nothing at all. The second is `missing` and is checked separately.
STATES = ("FAILED", "NOT RUN", "REPRODUCED", "PASS")
PASSING = ("PASS", "REPRODUCED")

REQUIRED_FIELDS = (
    "schema", "run_id", "ran_at", "commit", "fingerprint",
    "finished_fingerprint", "configuration_identity", "argv", "python",
    "pytest_returncode", "expected", "counts", "rows", "artifacts",
)


def scenario_id(nodeid: object) -> str:
    return str(nodeid or "").rsplit("::", 1)[-1]


def execution_identity(*, argv: object, expected: object,
                       python: object) -> str:
    material = json.dumps(
        {"argv": argv, "expected": expected, "python": python},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def manifest_problems(expected: tuple[str, ...]) -> list[str]:
    """BK-51-AC1: the expected scenario manifest must be unique and nonempty.

    A DUPLICATE IN THE MANIFEST IS NOT HARMLESS. `expected: len(EXPECTED)` is
    written into the report as the population size, so one duplicated entry
    makes a complete run report one phase short forever — and the obvious fix
    is to relax the completeness check, which is how the check dies.
    """
    bad: list[str] = []
    if not expected:
        bad.append("the expected scenario manifest is empty, so a run that "
                   "produced nothing would reconcile perfectly")
    seen: dict[str, int] = {}
    for name in expected:
        seen[name] = seen.get(name, 0) + 1
    for name, count in sorted(seen.items()):
        if count > 1:
            bad.append(f"the expected scenario manifest names {name} {count} "
                       f"times; the population size it declares is wrong")
    return bad


def problems(report: dict | None, *, expected: tuple[str, ...],
             fingerprint: str | None = None,
             configuration_identity: str | None = None,
             artifact_root: pathlib.Path | None = None) -> list[str]:
    """Everything that stops this report proving anything, or an empty list.

    `fingerprint` is the tree the CALLER is asking about. Passing None asks the
    narrower question -- is this report internally complete -- which is what
    the runner asks of its own output before printing a verdict.
    """
    if not isinstance(report, dict):
        return ["the browser report is absent or unreadable, which is not the "
                "same as a run that failed and must never read as one"]

    bad = list(manifest_problems(expected))

    if report.get("schema") != SCHEMA:
        return [*bad, f"the browser report has an unsupported schema "
                      f"({report.get('schema')!r}) and cannot be read"]

    for field in REQUIRED_FIELDS:
        if field not in report or report.get(field) in (None, ""):
            bad.append(f"the browser report has no {field}")

    run_id = report.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
            run_id):
        bad.append("the browser report has no UUIDv4 run identity")

    declared = report.get("expected")
    if not isinstance(declared, list) or not declared:
        bad.append("the browser report does not retain its nonempty expected manifest")
    elif tuple(declared) != expected:
        bad.append("the browser report's expected manifest differs from the current "
                   "declared manifest")

    if (configuration_identity is not None
            and report.get("configuration_identity") != configuration_identity):
        bad.append("the browser report was produced under a different execution "
                   "configuration")
    recomputed_configuration = execution_identity(
        argv=report.get("argv"), expected=report.get("expected"),
        python=report.get("python"),
    )
    if report.get("configuration_identity") != recomputed_configuration:
        bad.append("the browser report's execution configuration identity does "
                   "not match its manifest, arguments and Python runtime")

    # THE RUN COMPLETED. A crash at phase 3 leaves three green rows behind it.
    code = report.get("pytest_returncode")
    if code != 0:
        bad.append(f"the run exited {code!r}; a report from a run that did not "
                   f"complete describes the phases it reached and nothing "
                   f"about the ones it did not")

    # START AND END IDENTITY, both present and equal. One fingerprint cannot
    # tell a stable tree from one that moved between phase 1 and phase 14.
    started, finished = report.get("fingerprint"), report.get("finished_fingerprint")
    if started and finished and started != finished:
        bad.append(f"the tree moved during the run: it started {started} and "
                   f"finished {finished}, so the rows are about two products")
    if fingerprint is not None and started and started != fingerprint:
        bad.append(f"the report is about {started} and this tree is "
                   f"{fingerprint}, so it is stale")

    rows = report.get("rows")
    if not isinstance(rows, list):
        bad.append("the browser report row population is not a list")
        rows = []
    if not rows:
        bad.append("the browser report has an empty row population, and a run "
                   "that reported nothing must not read as a run that passed")

    # UNIQUE ROWS. A duplicated row inflates the count and hides the phase it
    # was duplicated over.
    seen: dict[str, int] = {}
    for row in rows:
        nodeid = (row or {}).get("nodeid") if isinstance(row, dict) else None
        if not nodeid:
            bad.append("a report row names no scenario")
            continue
        sid = scenario_id(nodeid)
        if row.get("scenario") != sid:
            bad.append(f"{nodeid} does not carry its exact scenario identity")
        seen[sid] = seen.get(sid, 0) + 1
    for sid, count in sorted(seen.items()):
        if count > 1:
            bad.append(f"{sid} appears {count} times in the report")

    # AN EXPLICIT OUTCOME FOR EVERY REQUIRED SCENARIO. A phase that produced no
    # row is a question nobody asked, and its silence is not a pass.
    for name in expected:
        if name not in seen:
            bad.append(f"{name} produced no row at all; a scenario that did "
                       f"not report is not a scenario that passed")
    for name in sorted(set(seen) - set(expected)):
        bad.append(f"{name} is an unexpected row; it cannot replace a required scenario")
    for row in rows:
        if isinstance(row, dict) and row.get("state") not in STATES:
            bad.append(f"{row.get('nodeid')} has state {row.get('state')!r}, "
                       f"which is not one of {list(STATES)}")

    # ONLY CURRENT ARTIFACTS. A screenshot from last week is a picture of a
    # product that is not this one, and a reader cannot tell by looking.
    bad += _artifact_problems(
        report.get("artifacts"), run_id=run_id, root=artifact_root,
    )

    counts = report.get("counts")
    if isinstance(counts, dict):
        actual = {
            "pass": sum(row.get("state") == "PASS" for row in rows if isinstance(row, dict)),
            "reproduced": sum(row.get("state") == "REPRODUCED" for row in rows
                              if isinstance(row, dict)),
            "unexplained": sum(row.get("state") in ("FAILED", "NOT RUN") for row in rows
                               if isinstance(row, dict)),
            "missing": len(set(expected) - set(seen)),
            "unexpected": len(set(seen) - set(expected)),
        }
        if counts != actual:
            bad.append(f"the browser report counts do not reconcile: recorded "
                       f"{counts!r}, actual {actual!r}")
    else:
        bad.append("the browser report has no outcome counts object")
    return bad


def _artifact_problems(artifacts: object, *, run_id: object,
                       root: pathlib.Path | None) -> list[str]:
    if not isinstance(artifacts, list):
        return ["the artifact inventory is not a list"]
    bad: list[str] = []
    seen: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            bad.append("an artifact inventory row is not an object")
            continue
        name = artifact.get("path")
        if not isinstance(name, str) or not name or pathlib.Path(name).name != name:
            bad.append(f"artifact path {name!r} is not one contained file name")
            continue
        if name in seen:
            bad.append(f"artifact {name} appears more than once")
        seen.add(name)
        if artifact.get("run_id") != run_id:
            bad.append(f"artifact {name} belongs to a different run")
        digest = artifact.get("sha256")
        size = artifact.get("bytes")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            bad.append(f"artifact {name} has no valid SHA-256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            bad.append(f"artifact {name} has no valid byte count")
        if root is None:
            bad.append(f"artifact {name} bytes were not available for verification")
            continue
        path = (root / name).resolve()
        try:
            path.relative_to(root.resolve())
            raw = path.read_bytes()
        except (OSError, ValueError):
            bad.append(f"artifact {name} is absent or outside the run directory")
            continue
        if len(raw) != size:
            bad.append(f"artifact {name} byte count changed")
        if hashlib.sha256(raw).hexdigest() != digest:
            bad.append(f"artifact {name} bytes changed after the run")
    return bad


def artifact_inventory(paths: list[pathlib.Path], *, root: pathlib.Path,
                       run_id: str) -> list[dict]:
    """Bind every artifact to this run and its exact original bytes."""
    rows: list[dict] = []
    for path in sorted(paths):
        resolved = path.resolve()
        resolved.relative_to(root.resolve())
        raw = resolved.read_bytes()
        rows.append({"path": resolved.name, "run_id": run_id,
                     "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    return rows


def publish(path: pathlib.Path, report: dict) -> None:
    """Atomically publish one complete report and never retain a temp claim."""
    path.parent.mkdir(parents=True, exist_ok=True)
    run_id = str(report.get("run_id") or "unknown")
    temporary = path.with_name(f".{path.name}.{run_id}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def row_for(report: dict | None, nodeid: str) -> str | None:
    """The recorded state of one scenario, or None when it is not there."""
    for row in (report or {}).get("rows") or []:
        if isinstance(row, dict) and row.get("nodeid") == nodeid:
            return row.get("state")
    return None


def load(path: pathlib.Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def stamp(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
