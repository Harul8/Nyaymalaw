"""What a browser run must have produced before it can prove anything.

BK-80-AC2 (the reader) and BK-51-AC1 (the runner's own reconciliation).

    from tools.browser_evidence import problems, row_for

THE TWO HALVES OF ONE FACT, IN ONE FILE ON PURPOSE. A writer that emits less
than the reader demands produces evidence nobody can use; a reader that demands
less than the writer emits accepts runs that did not happen. Splitting them
across `tools/journey.py` and `tools/backlog.py` is how they would drift, and
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

import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]

SCHEMA = 1

#: A row's state, worst first. `NOT RUN` is a state and not an absence: a phase
#: that errored in collection reported something, and a phase nobody asked for
#: reported nothing at all. The second is `missing` and is checked separately.
STATES = ("FAILED", "NOT RUN", "REPRODUCED", "PASS")
PASSING = ("PASS", "REPRODUCED")

REQUIRED_FIELDS = (
    "schema", "ran_at", "commit", "fingerprint", "finished_fingerprint",
    "pytest_returncode", "expected", "rows", "artifacts",
)


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
             fingerprint: str | None = None) -> list[str]:
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
        if report.get(field) in (None, ""):
            bad.append(f"the browser report has no {field}")

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
    if not isinstance(rows, list) or not rows:
        bad.append("the browser report has an empty row population, and a run "
                   "that reported nothing must not read as a run that passed")
        return bad

    # UNIQUE ROWS. A duplicated row inflates the count and hides the phase it
    # was duplicated over.
    seen: dict[str, int] = {}
    for row in rows:
        nodeid = (row or {}).get("nodeid") if isinstance(row, dict) else None
        if not nodeid:
            bad.append("a report row names no scenario")
            continue
        seen[nodeid] = seen.get(nodeid, 0) + 1
    for nodeid, count in sorted(seen.items()):
        if count > 1:
            bad.append(f"{nodeid} appears {count} times in the report")

    # AN EXPLICIT OUTCOME FOR EVERY REQUIRED SCENARIO. A phase that produced no
    # row is a question nobody asked, and its silence is not a pass.
    reported = {n.rsplit("::", 1)[-1] for n in seen}
    for name in expected:
        if name not in reported and not any(n.endswith(name) for n in seen):
            bad.append(f"{name} produced no row at all; a scenario that did "
                       f"not report is not a scenario that passed")
    for row in rows:
        if isinstance(row, dict) and row.get("state") not in STATES:
            bad.append(f"{row.get('nodeid')} has state {row.get('state')!r}, "
                       f"which is not one of {list(STATES)}")

    # ONLY CURRENT ARTIFACTS. A screenshot from last week is a picture of a
    # product that is not this one, and a reader cannot tell by looking.
    artifacts = report.get("artifacts")
    if isinstance(artifacts, dict):
        stale = [name for name, owner in artifacts.items() if owner != started]
        for name in sorted(stale):
            bad.append(f"artifact {name} was produced by a different run "
                       f"({artifacts.get(name)!r}) and is retained in this report")
    elif artifacts is not None and not isinstance(artifacts, list):
        bad.append("the artifact list is neither a list nor a run-tagged map")
    return bad


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
