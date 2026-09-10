"""Compare the failures a gate run actually produced against the declared ones.

    from tools.known_failures import load, observed, compare

THE QUESTION THIS ANSWERS is not "did the gate pass" -- it did not, and it says
so. It answers "is this the SAME red we already knew about, or a new one?"

WHY THAT IS A DIFFERENT QUESTION
----------------------------------
`tools/check.py` returns 1 on any failure and writes no stamp, so
`tools/hooks/pre-commit` refuses the commit. With three unbuilt PRD obligations
reporting honestly, that blocked every commit in the repository -- including
the work that would close them. The ways out were to bypass the hook, weaken
the tests, or stop committing, and all three are worse than the problem.

So the build compares. A run whose failures are exactly the declared set is a
SCOPED BUILD PASS: it may commit, the full gate stays visibly red, and the
stamp records that it was scoped. Anything else blocks.

THREE OUTCOMES, AND THE THIRD IS WHY THIS IS A CONTROL
--------------------------------------------------------
    unchanged  -> the declared set, exactly. Commit permitted, full gate red.
    new        -> a failure nobody registered. BLOCKED.
    fixed      -> a declared failure that has started passing. ALSO BLOCKED.

The third is the one people leave out, and leaving it out is how a waiver
outlives the defect it was written for and silently covers the next failure on
the same test. `pytest.xfail` without `strict=True` has exactly that hole, and
`tests/test_a_documented_defect_uses_a_strict_marker.py` already refuses it in
this repository. This is the same rule one level up.

WHAT IT DELIBERATELY DOES NOT DO
----------------------------------
It does not make anything pass, it cannot mark a criterion done, and a scoped
stamp never satisfies a caller asking whether the FULL gate is green. Evidence
bound to a scoped run is labelled scoped and goes stale the moment this
registry changes -- see `tools/evidence.py`.
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import sys
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REGISTRY = ROOT / "docs" / "backlog" / "known_failures.yaml"

#: pytest prints one of these per failing node under `short test summary info`.
#: Anchored at line start so a node id quoted inside an assertion message --
#: which happens constantly in this suite's own controls -- is not read as a
#: failure that occurred.
_PYTEST_NODE = re.compile(r"^(?:FAILED|ERROR)\s+(\S+?)(?:\s+-.*)?$", re.M)


class RegistryError(RuntimeError):
    """The registry itself is wrong. Never treated as 'no known failures'."""


@dataclass(frozen=True)
class Known:
    id: str
    steps: tuple[str, ...]
    match: str
    signature: str
    owner: tuple[str, ...]
    because: str


@dataclass
class Verdict:
    """What the comparison found. `ok` is not 'the gate passed'."""

    new: list[tuple[str, str]] = field(default_factory=list)
    """(step, signature) failures nobody registered."""
    fixed: list[str] = field(default_factory=list)
    """Ids declared here that did not fail. The registry is stale."""
    matched: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """The observed red is exactly the declared red.

        NOT 'the build is green'. Callers must still report the full gate as
        red; `tools/check.py` prints FULL GATE RED on this path.
        """
        return not self.new and not self.fixed


def load(path: pathlib.Path | None = None) -> list[Known]:
    """Read the registry, REFUSING a malformed one rather than reading empty.

    An unreadable registry that returned `[]` would mean every observed failure
    is 'new' -- which blocks, so it fails safe -- but it would report the cause
    as a product regression instead of a broken registry, and somebody would
    go looking in the wrong place. It raises instead.
    """
    import yaml

    path = path or REGISTRY
    if not path.exists():
        raise RegistryError(f"no known-failure registry at {path}")
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf8")) or {}
    except yaml.YAMLError as exc:
        raise RegistryError(f"{path.name} does not parse: {exc}") from exc
    if doc.get("schema") != 1:
        raise RegistryError(f"{path.name} has an unsupported schema")
    rows = doc.get("known_failures")
    if rows is None:
        raise RegistryError(f"{path.name} declares no known_failures key")

    out: list[Known] = []
    seen: set[str] = set()
    for n, row in enumerate(rows):
        where = f"{path.name}[{n}]"
        if not isinstance(row, dict):
            raise RegistryError(f"{where} is not a mapping")
        rid = str(row.get("id") or "").strip()
        if not rid:
            raise RegistryError(f"{where} has no id")
        if rid in seen:
            raise RegistryError(f"{rid} appears twice")
        seen.add(rid)
        step = row.get("step")
        steps = tuple(step) if isinstance(step, list) else (str(step or ""),)
        if not all(s.strip() for s in steps):
            raise RegistryError(f"{rid} does not name the gate step it fails in")
        match = str(row.get("match") or "").strip()
        if match not in ("line", "node"):
            raise RegistryError(f"{rid} has match {match!r}, not 'line' or 'node'")
        signature = str(row.get("signature") or "").strip()
        if not signature:
            raise RegistryError(f"{rid} has no signature")
        owner = row.get("owner") or []
        owner = tuple(owner) if isinstance(owner, list) else (str(owner),)
        if not owner or not all(str(o).strip() for o in owner):
            # A FAILURE WITH NO OWNER IS NOT KNOWN, IT IS FORGOTTEN.
            raise RegistryError(
                f"{rid} names no owning acceptance criterion. A registered "
                f"failure without an owner is a permanent waiver")
        if not str(row.get("because") or "").strip():
            raise RegistryError(f"{rid} does not say why it is expected")
        out.append(Known(rid, steps, match, signature, tuple(owner),
                         str(row["because"])))
    return out


def owners_exist(rows: list[Known], criteria: set[str]) -> list[str]:
    """Every owner must be a real acceptance criterion id.

    Separate from `load` because it needs the backlog, and the registry has to
    be readable by callers that do not have it -- the pre-commit hook among
    them. Reported, never silently skipped.
    """
    return sorted({o for r in rows for o in r.owner if o not in criteria})


@dataclass(frozen=True)
class Observed:
    """What a step's output reports, WITH THE TWO KINDS KEPT APART.

    They were merged into one set for about ten minutes, and the first run
    against real output reported ten new failures -- among them a bare docstring
    delimiter and the word `try:` -- because re-detecting a node id out of a set
    that also held every raw line matched almost anything. Two kinds of identity
    in one set is a second copy of the question 'what kind is this', answered by
    guessing.
    """

    nodes: frozenset[str]
    """pytest node ids, from the summary lines it prints per failing node."""
    lines: frozenset[str]
    """Whole stripped output lines, so a signature cannot half-match a longer
    sentence that merely contains it."""

    def holds(self, match: str, signature: str) -> bool:
        return signature in (self.nodes if match == "node" else self.lines)


def observed(step: str, output: str) -> Observed:
    """The failure identities a step's captured output actually reports."""
    return Observed(
        nodes=frozenset(m.group(1) for m in _PYTEST_NODE.finditer(output)),
        lines=frozenset(ln.strip() for ln in output.splitlines() if ln.strip()))


def compare(rows: list[Known], seen: dict[str, Observed],
            ran: set[str]) -> Verdict:
    """Compare declared against observed, for the steps that actually RAN.

    `ran` matters: a stage that did not execute has produced no evidence
    either way, and treating its declared failures as `fixed` would report the
    registry stale because a step was skipped. That is the absent-input defect
    on the control written to catch absent inputs.
    """
    verdict = Verdict()
    empty = Observed(frozenset(), frozenset())

    for row in rows:
        applicable = [s for s in row.steps if s in ran]
        if not applicable:
            continue
        if any(seen.get(s, empty).holds(row.match, row.signature)
               for s in applicable):
            verdict.matched.append(row.id)
        else:
            verdict.fixed.append(row.id)

    # ANY OTHER FAILING NODE IS NEW.
    #
    # Enumerated from the NODE set only. A tool that merely exits non-zero with
    # prose cannot have its failures enumerated from output -- there is no
    # marker separating a failure line from an ordinary one -- so those steps
    # are settled by `unexplained` instead, which asks whether every declared
    # signature for a failing step was present.
    declared_nodes = {r.signature for r in rows if r.match == "node"}
    for s in sorted(ran):
        for node in sorted(seen.get(s, empty).nodes):
            if node not in declared_nodes:
                verdict.new.append((s, node))
    return verdict


def unexplained(step: str, rows: list[Known], seen: Observed) -> bool:
    """Did a FAILING step fail for a reason this registry does not name?

    For pytest the node list settles it. For a tool that just exits non-zero
    with prose -- `trace` is the one that matters -- the question is whether
    every declared signature for that step was seen. If the step failed and
    they were all present, the failure is accounted for; if it failed and one
    was missing, something else went wrong and the build must stop.
    """
    declared = [r for r in rows if step in r.steps]
    if not declared:
        return True
    return not all(seen.holds(r.match, r.signature) for r in declared)


def registry_digest(path: pathlib.Path | None = None) -> str:
    """Identity of the declared set, for stamps and evidence records.

    Evidence bound to a scoped run names this digest, so amending the registry
    makes that evidence stale rather than silently re-basing it.
    """
    path = path or REGISTRY
    if not path.exists():
        return "absent"
    body = path.read_text(encoding="utf8").replace("\r\n", "\n").encode()
    return hashlib.sha256(body).hexdigest()[:16]
