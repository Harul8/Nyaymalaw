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

_PYTEST_SUMMARY = re.compile(r"^(FAILED|ERROR)\s+(.+?)\s*$", re.M)
_PYTEST_SECTION = re.compile(r"^_{3,}\s+(.+?)\s+_{3,}\s*$")
_PYTEST_EVIDENCE = re.compile(r"^E\s+(.*)$")
_PYTEST_EXCEPTION = re.compile(
    r"^(?:AssertionError|[A-Za-z_][\w.]*(?:Error|Exception))(?::.*)?$")
_TRACE_FACT = re.compile(r"^\s*\[([^]]+)]\s+(.+?)\s*$")
_TRACE_TOTAL = re.compile(r"TRACE FAILED\s+--\s+(\d+) failure\(s\)")
_RUFF_HEADER = re.compile(r"^([A-Z]+\d+)\s+(.+?)\s*$")
_RUFF_LOCATION = re.compile(r"^\s*-->\s+(.+?):(\d+):(\d+)\s*$")
_RUFF_TOTAL = re.compile(r"^Found (\d+) errors?\.?$", re.M)
_PYLINT_FACT = re.compile(
    r"^(.+?):(\d+):(\d+):\s+([A-Z]\d{4}):\s+(.+?)\s*$")
#: `tools/backlog.py population`: `  [group] member  optional note`. The member
#: is ONE token -- the note after it is for people and is never part of a fact.
_BACKLOG_MEMBER = re.compile(r"^\s+\[([^\]\s]+)\]\s+(\S+)")
_BACKLOG_TOTAL = re.compile(r"^POPULATION FAILED -- (\d+) member\(s\)", re.M)
_BACKLOG_OK = re.compile(r"^POPULATION OK\b", re.M)
#: A group identity is `rule` or `rule:packet`. Anything else is not a group
#: the population check produces, and registering it would be debt nothing
#: could ever match.
_BACKLOG_GROUP = re.compile(r"^[a-z][a-z-]*[a-z](?::[A-Z0-9]+)?$")
_FEATURE_DETAIL = re.compile(r"^[A-Z]\d+(?:\.\d+)?:\s+\S")


class RegistryError(RuntimeError):
    """The registry itself is wrong. Never treated as 'no known failures'."""


@dataclass(frozen=True)
class Known:
    id: str
    steps: tuple[str, ...]
    fact: "FailureFact"
    owner: tuple[str, ...]
    because: str


@dataclass(frozen=True, order=True)
class FailureFact:
    """One structured reason a named gate step is red."""

    kind: str
    identity: str
    reason: str
    details: tuple[str, ...] = ()

    def render(self) -> str:
        detail = f" [{'; '.join(self.details)}]" if self.details else ""
        return f"{self.kind} {self.identity}: {self.reason}{detail}"


@dataclass
class Verdict:
    """What the comparison found. `ok` is not 'the gate passed'."""

    new: list[tuple[str, str]] = field(default_factory=list)
    """(step, rendered structured fact) failures nobody registered."""
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


def _text(value: object) -> str:
    return str(value or "").strip()


def _only(fact: dict, allowed: set[str], where: str) -> None:
    extra = sorted(set(fact) - allowed)
    if extra:
        raise RegistryError(f"{where} has unknown fact field(s): {', '.join(extra)}")


def _declared_fact(raw: object, where: str) -> FailureFact:
    if not isinstance(raw, dict):
        raise RegistryError(f"{where} has no structured fact")
    kind = _text(raw.get("kind"))
    if kind == "trace":
        _only(raw, {"kind", "check", "reason"}, where)
        check, reason = _text(raw.get("check")), _text(raw.get("reason"))
        if not check or not reason:
            raise RegistryError(f"{where} trace fact needs check and reason")
        return FailureFact("trace", check, reason)
    if kind == "pytest":
        _only(raw, {"kind", "node", "outcome", "reason", "details"}, where)
        node = _text(raw.get("node"))
        outcome = _text(raw.get("outcome")).upper()
        reason = _text(raw.get("reason"))
        details = raw.get("details") or []
        if outcome not in {"FAILED", "ERROR"}:
            raise RegistryError(f"{where} pytest fact has invalid outcome {outcome!r}")
        if not node or not reason:
            raise RegistryError(f"{where} pytest fact needs node and reason")
        if not isinstance(details, list) or not all(_text(v) for v in details):
            raise RegistryError(f"{where} pytest details must be non-empty strings")
        return FailureFact(f"pytest-{outcome.lower()}", node, reason,
                           tuple(sorted(str(v).strip() for v in details)))
    if kind == "ruff":
        _only(raw, {"kind", "count", "digest"}, where)
        count, digest = raw.get("count"), _text(raw.get("digest")).lower()
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise RegistryError(f"{where} ruff fact needs a positive integer count")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RegistryError(f"{where} ruff fact needs a sha256 digest")
        return FailureFact("ruff", "diagnostic-set", f"{count} diagnostic(s)",
                           (f"sha256:{digest}",))
    if kind == "pylint":
        allowed = {"kind", "path", "line", "column", "code", "reason"}
        _only(raw, allowed, where)
        path, code, reason = (_text(raw.get(k)) for k in ("path", "code", "reason"))
        line, column = raw.get("line"), raw.get("column")
        if (not path or not code or not reason or
                not isinstance(line, int) or not isinstance(column, int)):
            raise RegistryError(
                f"{where} pylint fact needs path, line, column, code and reason")
        ident = f"{path.replace(chr(92), '/')}:{line}:{column}:{code}"
        return FailureFact("pylint", ident, reason)
    if kind == "backlog":
        # THE MEMBERS ARE THE FACT, listed rather than digested. A ruff debt is
        # a digest because its diagnostics carry line numbers that move with
        # every unrelated edit; a population member is `BK-65-AC1/domain_test`
        # and does not move. Listing them is what makes this row the work
        # queue the sweep reads, rather than a hash somebody has to reverse.
        _only(raw, {"kind", "rule", "members"}, where)
        rule = _text(raw.get("rule"))
        members = raw.get("members")
        if not _BACKLOG_GROUP.fullmatch(rule):
            raise RegistryError(
                f"{where} backlog fact needs a rule such as "
                f"'absent-required-level:P23', got {rule!r}")
        if not isinstance(members, list) or not members \
                or not all(_text(m) and len(_text(m).split()) == 1 for m in members):
            raise RegistryError(
                f"{where} backlog fact needs a non-empty list of single-token "
                f"members")
        clean = [_text(m) for m in members]
        if len(set(clean)) != len(clean):
            raise RegistryError(f"{where} backlog fact lists a member twice")
        return FailureFact("backlog", rule, f"{len(clean)} member(s)",
                           tuple(sorted(clean)))
    raise RegistryError(f"{where} has unsupported fact kind {kind!r}")


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
    if doc.get("schema") != 2:
        raise RegistryError(f"{path.name} has an unsupported schema")
    rows = doc.get("known_failures")
    if rows is None:
        raise RegistryError(f"{path.name} declares no known_failures key")

    out: list[Known] = []
    seen: set[str] = set()
    claims: dict[tuple[str, FailureFact], str] = {}
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
        steps = tuple(str(s).strip() for s in step) if isinstance(step, list) \
            else (_text(step),)
        if not all(s.strip() for s in steps):
            raise RegistryError(f"{rid} does not name the gate step it fails in")
        if len(set(steps)) != len(steps):
            raise RegistryError(f"{rid} names the same gate step twice")
        fact = _declared_fact(row.get("fact"), rid)
        allowed_steps = {
            "trace": {"trace"},
            "ruff": {"ruff"},
            "pylint": {"pylint"},
            "pytest-failed": {"class_a", "pytest"},
            "pytest-error": {"class_a", "pytest"},
            "backlog": {"backlog"},
        }[fact.kind]
        wrong = sorted(set(steps) - allowed_steps)
        if wrong:
            raise RegistryError(
                f"{rid} declares {fact.kind} for wrong step(s): {', '.join(wrong)}")
        owner = row.get("owner") or []
        owner = tuple(owner) if isinstance(owner, list) else (str(owner),)
        if not owner or not all(str(o).strip() for o in owner):
            # A FAILURE WITH NO OWNER IS NOT KNOWN, IT IS FORGOTTEN.
            raise RegistryError(
                f"{rid} names no owning acceptance criterion. A registered "
                f"failure without an owner is a permanent waiver")
        if not str(row.get("because") or "").strip():
            raise RegistryError(f"{rid} does not say why it is expected")
        for named_step in steps:
            claim = (named_step, fact)
            if claim in claims:
                raise RegistryError(
                    f"{rid} and {claims[claim]} declare the same failure fact")
            claims[claim] = rid
        out.append(Known(rid, steps, fact, tuple(owner), str(row["because"])))
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
    """The complete structured failure set reported by one gate step."""

    facts: frozenset[FailureFact]


def _observer_gap(step: str, reason: str) -> FailureFact:
    # This kind is intentionally not accepted by `_declared_fact`: an opaque
    # parser failure can block a gate, but can never be registered as debt.
    return FailureFact("observer-gap", step, reason)


def _trace_facts(output: str) -> set[FailureFact]:
    facts: set[FailureFact] = set()
    inside = False
    for line in output.splitlines():
        heading = line.strip()
        if heading == "FAILURES":
            inside = True
            continue
        if inside and heading in {"WARNINGS", "NOT ASSESSED", "NOTES"}:
            inside = False
        if inside and (match := _TRACE_FACT.match(line)):
            facts.add(FailureFact("trace", match.group(1), match.group(2)))
    totals = [int(m.group(1)) for m in _TRACE_TOTAL.finditer(output)]
    if facts and not totals:
        facts.add(_observer_gap("trace", "failure total is absent"))
    elif totals and (len(totals) != 1 or totals[0] != len(facts)):
        facts.add(_observer_gap(
            "trace", f"reported {totals!r} but parsed {len(facts)} failure fact(s)"))
    return facts


def _diagnostic_set(tool: str, diagnostics: list[str]) -> FailureFact:
    canonical = "\n".join(sorted(diagnostics)).encode("utf8")
    digest = hashlib.sha256(canonical).hexdigest()
    return FailureFact(tool, "diagnostic-set",
                       f"{len(diagnostics)} diagnostic(s)",
                       (f"sha256:{digest}",))


def _ruff_facts(output: str) -> set[FailureFact]:
    diagnostics = []
    pending: tuple[str, str] | None = None
    for line in output.splitlines():
        if match := _RUFF_HEADER.match(line):
            pending = (match.group(1), match.group(2))
            continue
        if pending and (match := _RUFF_LOCATION.match(line)):
            path, row, col = match.groups()
            code, reason = pending
            diagnostics.append(
                f"{path.replace(chr(92), '/')}:{row}:{col}:{code}:{reason}")
            pending = None
    totals = [int(m.group(1)) for m in _RUFF_TOTAL.finditer(output)]
    facts = {_diagnostic_set("ruff", diagnostics)} if diagnostics else set()
    if totals and (len(totals) != 1 or totals[0] != len(diagnostics)):
        facts.add(_observer_gap(
            "ruff", f"reported {totals!r} but parsed {len(diagnostics)} diagnostic(s)"))
    elif diagnostics and not totals:
        facts.add(_observer_gap("ruff", "diagnostic total is absent"))
    return facts


def _pylint_facts(output: str) -> set[FailureFact]:
    facts = set()
    for line in output.splitlines():
        if match := _PYLINT_FACT.match(line):
            path, row, col, code, reason = match.groups()
            ident = f"{path.replace(chr(92), '/')}:{row}:{col}:{code}"
            facts.add(FailureFact("pylint", ident, reason))
    return facts


def _pytest_sections(output: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    title = ""
    body: list[str] = []
    for line in output.splitlines():
        if "short test summary info" in line:
            if title:
                sections.append((title, body))
            break
        if match := _PYTEST_SECTION.match(line):
            if title:
                sections.append((title, body))
            title, body = match.group(1), []
        elif title:
            body.append(line)
    else:
        if title:
            sections.append((title, body))
    return sections


def _section_for(node: str, sections: list[tuple[str, list[str]]]) -> list[str]:
    terminal = node.rsplit("::", 1)[-1]
    for title, body in sections:
        clean = re.sub(r"^(?:ERROR at (?:setup|teardown) of|ERROR collecting)\s+",
                       "", title)
        if clean == terminal or terminal in clean or node in title:
            return body
    return []


def _pytest_facts(output: str) -> set[FailureFact]:
    sections = _pytest_sections(output)
    facts: set[FailureFact] = set()
    marker = "short test summary info"
    summary = output[output.find(marker):] if marker in output else ""
    for match in _PYTEST_SUMMARY.finditer(summary):
        outcome, report = match.groups()
        if " - " in report:
            node, summary_reason = report.split(" - ", 1)
        else:
            node, summary_reason = report, ""
        evidence = []
        for line in _section_for(node, sections):
            if found := _PYTEST_EVIDENCE.match(line):
                evidence.append(found.group(1).strip())
        reason = next((line for line in evidence
                       if _PYTEST_EXCEPTION.match(line)), summary_reason.strip())
        reason = reason or "<no structured reason reported>"

        details: list[str] = []
        nested = "\n".join(evidence)
        for item in _trace_facts(nested):
            if item.kind == "trace":
                details.append(f"trace:{item.identity}:{item.reason}")
        for line in evidence:
            if _FEATURE_DETAIL.match(line):
                details.append(f"contract:{line}")
        fact = FailureFact(f"pytest-{outcome.lower()}", node.strip(), reason,
                           tuple(sorted(details)))
        if fact in facts:
            facts.add(_observer_gap(
                "pytest", f"duplicate summary fact for {node.strip()}"))
        facts.add(fact)
    return facts


def _backlog_facts(output: str) -> set[FailureFact]:
    """One fact per population group, holding exactly its members.

    THE TOTAL IS CROSS-CHECKED, as `_trace_facts` does, and the check runs in
    BOTH directions: printed members with no total, a total that disagrees with
    the members parsed, a member printed twice, and a report that says OK while
    printing members are each an observer gap. An observer gap can never be
    registered, so a truncated or garbled report blocks rather than matching a
    smaller debt than the one that exists.
    """
    groups: dict[str, list[str]] = {}
    parsed = 0
    for line in output.splitlines():
        if match := _BACKLOG_MEMBER.match(line):
            group, member = match.groups()
            groups.setdefault(group, []).append(member)
            parsed += 1
    facts: set[FailureFact] = set()
    for group, members in groups.items():
        if len(set(members)) != len(members):
            facts.add(_observer_gap("backlog", f"{group} printed a member twice"))
        unique = sorted(set(members))
        facts.add(FailureFact("backlog", group, f"{len(unique)} member(s)",
                              tuple(unique)))
    totals = [int(m.group(1)) for m in _BACKLOG_TOTAL.finditer(output)]
    said_ok = bool(_BACKLOG_OK.search(output))
    if parsed and said_ok:
        facts.add(_observer_gap("backlog", "reported OK while printing members"))
    if parsed and not totals:
        facts.add(_observer_gap("backlog", "member total is absent"))
    elif totals and (len(totals) != 1 or totals[0] != parsed):
        facts.add(_observer_gap(
            "backlog", f"reported {totals!r} but parsed {parsed} member(s)"))
    return facts


def observed(step: str, output: str, *, failed: bool = False) -> Observed:
    """Parse one step's output; an unparseable red can never be waived."""
    if step == "backlog":
        facts = _backlog_facts(output)
    elif step == "trace":
        facts = _trace_facts(output)
    elif step == "ruff":
        facts = _ruff_facts(output)
    elif step == "pylint":
        facts = _pylint_facts(output)
    elif step in {"class_a", "pytest"}:
        facts = _pytest_facts(output)
    else:
        facts = set()
    if failed and not facts:
        digest = hashlib.sha256(output.replace("\r\n", "\n").encode()).hexdigest()
        facts.add(_observer_gap(step, f"non-zero exit with no parsed fact; sha256:{digest}"))
    return Observed(frozenset(facts))


def compare(rows: list[Known], seen: dict[str, Observed],
            ran: set[str]) -> Verdict:
    """Compare declared against observed, for the steps that actually RAN.

    `ran` matters: a stage that did not execute has produced no evidence
    either way, and treating its declared failures as `fixed` would report the
    registry stale because a step was skipped. That is the absent-input defect
    on the control written to catch absent inputs.
    """
    verdict = Verdict()
    empty = Observed(frozenset())
    expected = {(step, row.fact): row.id for row in rows
                for step in row.steps if step in ran}
    actual = {(step, fact) for step in ran
              for fact in seen.get(step, empty).facts}

    for step, fact in sorted(actual - set(expected)):
        verdict.new.append((step, fact.render()))
    missing = set(expected) - actual
    verdict.fixed = [row.id for row in rows
                     if any((step, row.fact) in missing
                            for step in row.steps if step in ran)]
    verdict.matched = [row.id for row in rows
                       if any(step in ran for step in row.steps)
                       and all((step, row.fact) in actual
                               for step in row.steps if step in ran)]
    return verdict


def unexplained(step: str, rows: list[Known], seen: Observed) -> bool:
    """Whether one step's observed and declared structured sets differ."""
    declared = {r.fact for r in rows if step in r.steps}
    return seen.facts != declared


def registry_digest(path: pathlib.Path | None = None) -> str:
    """Identity of the declared set, for stamps and evidence records.

    Evidence bound to a scoped run names this digest, so amending the registry
    makes that evidence stale rather than silently re-basing it.
    """
    path = path or REGISTRY
    if not path.exists():
        return "absent"
    body = path.read_text(encoding="utf8").replace("\r\n", "\n").encode()
    return hashlib.sha256(body).hexdigest()
