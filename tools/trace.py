"""The three-way diff: spec <-> code <-> eval results.

    python tools/trace.py            # report and exit non-zero on any failure
    python tools/trace.py --summary  # counts only

This is the mechanism that answers "are we building what the PRD says". It does
not depend on anyone remembering anything: it reads the generated spec, scans
the source for @implements declarations, reads the recorded eval results, and
fails on a mismatch.

The checks, and why each exists
------------------------------
T1  spec is current          A generator changed and the spec was not regenerated.
T2  no orphan implements     Code claims a feature id that does not exist.
T3  no unbuilt claims        A feature above `decided` with no implementing code.
T4  no status inflation      A feature at `tested` whose evals have never run.
T5  evals resolve            A feature references an eval id that is not defined.
T6  counterexamples bite     An eval whose counterexample has never been rejected.
T7  NEVER clauses covered    A `never` clause with no test declaring it (reported).
T8  built gates are wired    A gate declared built that no code path consults.
T9  unbuilt gates are not    A gate declared UNBUILT that code consults anyway.
T10 no stale evidence        A recorded eval id the spec no longer defines.

T6 and T7 are the ones that catch a green suite that proves nothing. T8 and T9
are the ones that keep the gate matrix from becoming a description.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pyyaml is required: pip install pyyaml")

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))
from tools._console import utf8_console  # noqa: E402

utf8_console()
SPEC = ROOT / "spec"
SRC = ROOT / "nm"
TESTS = ROOT / "tests"
RESULTS = ROOT / ".nm" / "eval_results.json"
CURRENT_STATUS = ROOT / "docs" / "backlog" / "status.yaml"

BUILT_OR_BEYOND = ("built", "tested", "verified live")
NEEDS_EVAL_RUN = ("tested", "verified live")


class AssessmentState(str, Enum):
    """The three possible outcomes of a population-based check."""

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_ASSESSED = "NOT_ASSESSED"


@dataclass(frozen=True)
class PopulationAssessment:
    """A verdict that cannot lose the size of the population it judged."""

    check: str
    state: AssessmentState
    population: int
    what: str
    issues: tuple[str, ...] = ()


def assess_population(check: str, population: int, what: str,
                      issues: tuple[str, ...] | list[str] = ()) -> PopulationAssessment:
    """Return FAIL, NOT_ASSESSED or PASS in that precedence order."""
    issue_tuple = tuple(issues)
    if issue_tuple:
        state = AssessmentState.FAIL
    elif population == 0:
        state = AssessmentState.NOT_ASSESSED
    else:
        state = AssessmentState.PASS
    return PopulationAssessment(check, state, population, what, issue_tuple)


class Report:
    def __init__(self) -> None:
        self.failures: list[tuple[str, str]] = []
        self.warnings: list[tuple[str, str]] = []
        self.notes: list[str] = []
        self.assessments: list[PopulationAssessment] = []

    def fail(self, check: str, msg: str) -> None:
        self.failures.append((check, msg))

    def warn(self, check: str, msg: str) -> None:
        self.warnings.append((check, msg))

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def population(self, check: str, size: int, what: str,
                   issues: tuple[str, ...] | list[str] | None = None
                   ) -> PopulationAssessment:
        """Record the typed outcome of a check over an explicit population."""
        if issues is None:
            issues = [msg for failed_check, msg in self.failures
                      if failed_check == check]
        result = assess_population(check, size, what, issues)
        self.assessments.append(result)
        return result


def load_spec() -> tuple[list[dict], list[dict]]:
    fpath, epath = SPEC / "features.yaml", SPEC / "evals.yaml"
    if not fpath.exists() or not epath.exists():
        sys.exit("spec not generated -- run: python tools/export_spec.py")
    features = yaml.safe_load(fpath.read_text(encoding="utf8"))["features"]
    evals = yaml.safe_load(epath.read_text(encoding="utf8"))["evals"]
    return features, evals


def load_current_items() -> list[dict]:
    """Rows available to typed AWAITING references."""
    document = yaml.safe_load(CURRENT_STATUS.read_text(encoding="utf8")) or {}
    return document.get("items") or []


def load_anchors() -> dict[str, dict]:
    """The document ids that are NOT feature contracts -- controls and
    principles. Code declares `@implements("P1")` against these, and without
    the registry T2 would have to either reject them or stop checking."""
    path = SPEC / "anchors.yaml"
    if not path.exists():
        return {}
    return {a["id"]: a for a in yaml.safe_load(path.read_text(encoding="utf8"))["anchors"]}


def load_gates() -> list[dict]:
    path = SPEC / "gates.yaml"
    if not path.exists():
        return []
    return yaml.safe_load(path.read_text(encoding="utf8"))["gates"]



def _without_prose(text: str) -> str:
    """The source with comments and docstrings blanked, lines preserved.

    Blanked rather than deleted so a future line number still means what
    it says -- a scan that reports the wrong line is one nobody trusts the
    second time.

    A FILE THAT DOES NOT PARSE IS RETURNED UNCHANGED. Failing open here is
    right: this is one input to a check that reports, and a syntax error
    is caught by the build long before it reaches this. Failing closed
    would turn every mid-edit file into a spurious gate report.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text

    lines = text.splitlines()
    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            spans.append((first.lineno, first.end_lineno or first.lineno))

    blanked = set()
    for start, end in spans:
        blanked.update(range(start, end + 1))

    out = []
    for n, line in enumerate(lines, 1):
        if n in blanked:
            out.append("")
            continue
        # A COMMENT, and `#` inside a string literal is not one. Splitting
        # on a bare `#` would blind the scan to a fire() call that
        # happened to sit on a line holding a hash in a URL.
        out.append(_strip_comment(line))
    return "\n".join(out)


def _strip_comment(line: str) -> str:
    """Everything before an unquoted `#`."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote and line[i - 1:i] != "\\":
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#":
            return line[:i]
    return line

def gate_consultations() -> dict[str, list[str]]:
    """Which gate ids appear in the source, and where.

    A string scan, deliberately. An AST walk would have to model every way a
    gate id can reach `metrics.fire` -- a constant, a lookup, a mapping like
    `_GROUNDING_STATE` -- and the ways it cannot see are exactly the ways a
    real call site hides. `nm/domain/gates.py` is excluded because it is the
    registry: it names every gate by definition.

    OVER THE CODE AND NOT THE PROSE. Comments and docstrings are stripped
    first, because a module that EXPLAINS why it is not a gate was being
    read as consulting one -- `nm/domain/engagement.py` opens by saying it
    is not `G-SCOPE`, and T9 failed on the sentence that makes the file
    comprehensible. A check that makes it illegal to write about a gate is
    a check people route around.

    EVERY OTHER STRING STAYS. `metrics.fire("G-GROUND", ...)` is a string
    literal and is precisely what this must keep seeing, so only the two
    forms that are definitionally prose come out.
    """
    out: dict[str, list[str]] = {}
    registry = SRC / "domain" / "gates.py"
    for path in sorted(SRC.rglob("*.py")):
        if path == registry:
            continue
        text = _without_prose(path.read_text(encoding="utf8"))
        for line in text.splitlines():
            for token in re.findall(r"\bG-[A-Z]+\b", line):
                files = out.setdefault(token, [])
                rel = str(path.relative_to(ROOT))
                if rel not in files:
                    files.append(rel)
    return out


def scan_decorator(tree: ast.AST, name: str) -> list[tuple]:
    """Collect the literal arguments of every @name(...) decorator in a tree."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            fn = dec.func
            fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if fname != name:
                continue
            args = []
            for a in dec.args:
                if isinstance(a, ast.Constant):
                    args.append(a.value)
            found.append(tuple(args))
    return found


def scan_tree(root: Path, decorator: str, *,
              display_root: Path | None = None) -> dict[tuple, list[str]]:
    """Map decorator arguments to stable paths relative to ``display_root``."""
    relative_to = display_root or ROOT
    out: dict[tuple, list[str]] = {}
    if not root.exists():
        return out
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf8"), filename=str(path))
        except SyntaxError as exc:
            print(f"  ! could not parse {path.relative_to(relative_to)}: {exc}")
            continue
        for args in scan_decorator(tree, decorator):
            out.setdefault(args, []).append(path.relative_to(relative_to).as_posix())
    return out


def spec_is_current(rep: Report) -> None:
    """T1 -- compare all six payloads in memory and never repair the tree."""
    try:
        from tools.export_spec import build, compare_payloads

        payloads, _built = build()
        stale = compare_payloads(payloads)
    except BaseException as exc:  # noqa: BLE001 -- the failure is the report
        rep.fail("T1", f"export_spec.py could not build the candidate spec: {exc}")
        return
    for path, condition in stale:
        rep.fail("T1", f"{path.relative_to(ROOT)} is {condition} -- nothing was "
                       "rewritten. Run `python tools/export_spec.py --write` "
                       "explicitly, then re-run trace.")



@dataclass(frozen=True)
class AwaitingRef:
    """A typed registry dependency for one temporarily untestable clause."""

    kind: str
    ref: str
    reason: str

    @property
    def label(self) -> str:
        return f"{self.kind} {self.ref}"


# AWAITING is structured data. Prose explains the dependency but never supplies
# its id: parsing text before a comma made eight of nine declarations impossible
# to expire while still looking like ordinary English.
AWAITING: dict[tuple[str, int], AwaitingRef] = {
    ("A3", 0): AwaitingRef(
        "item", "BK-33", "real reopen is partial; the re-entry trigger is not computed yet"),
    ("A3", 1): AwaitingRef(
        "item", "BK-33", "real reopen is partial; the re-entry trigger is not computed yet"),
    ("C7", 1): AwaitingRef(
        "feature", "F1", "the route for obtaining material is F-phase work"),
    ("C7", 2): AwaitingRef(
        "feature", "F5", "there is no witness contact to contaminate yet"),
    ("D4", 1): AwaitingRef(
        "item", "BK-38", "the search-to-authority research journey is still partial"),
    ("D4", 3): AwaitingRef(
        "item", "BK-38", "the search-to-authority research journey is still partial"),
    ("D7", 1): AwaitingRef(
        "feature", "D7", "there is no composed prose to inspect yet"),
}


def _registry_by_id(rows: list[dict]) -> dict[str, dict]:
    return {str(row["id"]): row for row in rows if row.get("id")}


def _blocker(reference: AwaitingRef, features: list[dict], items: list[dict]
             ) -> dict | None:
    registry = {"feature": _registry_by_id(features), "item": _registry_by_id(items)}
    return registry.get(reference.kind, {}).get(reference.ref)


def awaiting_problems(features: list[dict], items: list[dict],
                      declarations: dict[tuple[str, int], AwaitingRef] | None = None
                      ) -> list[str]:
    """Reject every exemption whose target or blocker cannot be resolved."""
    declared = AWAITING if declarations is None else declarations
    by_id = {feature["id"]: feature for feature in features}
    problems: list[str] = []
    for (fid, index), reference in declared.items():
        if fid not in by_id:
            problems.append(f"AWAITING target {fid!r} is not a current feature")
            continue
        nevers = by_id[fid].get("never") or []
        if not isinstance(index, int) or index < 0 or index >= len(nevers):
            problems.append(f"AWAITING target {fid}.{index} names no NEVER clause")
        if reference.kind not in ("feature", "item"):
            problems.append(f"AWAITING blocker kind {reference.kind!r} for "
                            f"{fid}.{index} is not supported")
        elif _blocker(reference, features, items) is None:
            problems.append(f"AWAITING blocker {reference.label!r} for {fid}.{index} "
                            "does not resolve in the current registry")
    return problems


def expired_awaiting(features: list[dict], items: list[dict],
                     declarations: dict[tuple[str, int], AwaitingRef] | None = None
                     ) -> tuple[tuple[str, int], ...]:
    """Return declarations whose typed blocker is already complete."""
    declared = AWAITING if declarations is None else declarations
    return tuple(sorted(key for key, reference in declared.items()
                        if (_blocker(reference, features, items) or {}).get(
                            "implementation") == "complete"))


def _within_frontier(slice_id: str | None, features: list[dict]) -> bool:
    """Is this feature in a slice at or below the one the build reached?

    THE FRONTIER is the highest slice the PLAN OF RECORD reached. Inside it, an
    untested NEVER clause is a hole in something that ships. Outside it, it is
    work not started, and demanding refusal tests for unbuilt features fills
    the suite with tests nobody can run.

    IT READS THE HISTORICAL FIELDS, AND THAT IS DELIBERATE. BK-80-AC5 moved
    `status` to the current registry, where no feature is `tested` today
    because no delivering row is complete with passing evidence. Deriving the
    frontier from that field would collapse it to -1 -- and the whole of T7
    would drop from FAILURE to WARNING. Measured on 10 September 2026: the two
    substantive failures this build is carrying, C1 and D2, both vanish.

    A control that stops firing because a registry started telling the truth
    is not a control. The frontier is a question about how far the plan got,
    the plan of record answers it, and the current registry answers a different
    question -- which feature is built -- in the eligibility test above.

    THREE STATES, AND `None` IS THE ONE THAT MATTERS. An unparseable slice used
    to fall through `num()` to -1, which compares less than every frontier and
    so read as INSIDE it. That is an absent input reading as a decision, and it
    bit within the hour: renaming `slice` to `historical_slice` left this call
    site reading the old key, every feature returned -1, and four features in
    slices beyond the frontier turned from warnings into failures. The rename
    was the mistake; a field that answers `-1` for "I do not know" is what let
    the mistake look like a result.
    """
    def num(sid: str | None) -> int | None:
        if isinstance(sid, str) and sid[:1] == "S" and sid[1:].isdigit():
            return int(sid[1:])
        return None

    frontier = max((n for f in features
                    if (f.get("historical_status") or "decided") == "tested"
                    and (n := num(f.get("historical_slice"))) is not None),
                   default=-1)
    mine = num(slice_id)
    return None if mine is None else mine <= frontier


def implementation_discrepancies(
        features: list[dict], impl_by_feature: dict[str, list[str]]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return exact delivery gaps and authored implementation contradictions.

    These are independent sets. If a delivering link is removed from C6, C6
    must enter the first set without disappearing from the second; collapsing
    both into one count lets one changed fact hide another.
    """
    trace_only = tuple(sorted(
        feature["id"] for feature in features
        if feature["id"] in impl_by_feature and not feature.get("delivered_by")))
    contradicted = tuple(sorted(
        feature["id"] for feature in features
        if feature["id"] in impl_by_feature
        and feature.get("implementation") == "none"))
    return trace_only, contradicted


def assess_status_support(
        features: list[dict], impl_by_feature: dict[str, list[str]], ran: set[str]
) -> tuple[PopulationAssessment, PopulationAssessment]:
    """The shared T3/T4 measurement used by trace and the release gate."""
    built = [feature for feature in features
             if (feature.get("status") or "decided").strip() in BUILT_OR_BEYOND]
    tested = [feature for feature in features
              if (feature.get("status") or "decided").strip() in NEEDS_EVAL_RUN]

    t3_issues = [
        f"{feature['id']} is marked {(feature.get('status') or 'decided')!r} "
        "with no @implements anywhere"
        for feature in built if feature["id"] not in impl_by_feature
    ]
    t4_issues: list[str] = []
    for feature in tested:
        status = (feature.get("status") or "decided").strip()
        declared = set(feature.get("historical_eval_ids") or [])
        if not declared:
            t4_issues.append(
                f"{feature['id']} is marked {status!r} but declares no eval ids")
        elif not (declared & ran):
            t4_issues.append(
                f"{feature['id']} is marked {status!r} but none of its evals "
                f"({', '.join(sorted(declared))}) has ever run")

    return (
        assess_population(
            "T3", len(built),
            "feature(s) the current registry reports as built or beyond",
            t3_issues,
        ),
        assess_population(
            "T4", len(tested),
            "feature(s) claiming tested or verified live",
            t4_issues,
        ),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--skip-regen", action="store_true",
                    help="skip T1 (useful inside a loop that already regenerated)")
    args = ap.parse_args()

    rep = Report()
    if not args.skip_regen:
        spec_is_current(rep)

    features, evals = load_spec()
    current_items = load_current_items()
    anchors = load_anchors()
    gates = load_gates()
    by_id = {f["id"]: f for f in features}
    eval_ids = {e["id"] for e in evals}

    impl = scan_tree(SRC, "implements")
    impl_by_feature: dict[str, list[str]] = {}
    for arg_tuple, files in impl.items():
        for fid in arg_tuple:
            impl_by_feature.setdefault(str(fid), []).extend(files)
    impl_by_feature = {fid: sorted(set(files))
                       for fid, files in impl_by_feature.items()}

    refuses = scan_tree(TESTS, "refuses")
    refuses_by_feature: dict[str, set[int]] = {}
    for arg_tuple, _files in refuses.items():
        if len(arg_tuple) == 2:
            refuses_by_feature.setdefault(str(arg_tuple[0]), set()).add(int(arg_tuple[1]))

    results = {}
    if RESULTS.exists():
        results = json.loads(RESULTS.read_text(encoding="utf8"))
    ran = set(results.get("evals_run", []))
    rejected = set(results.get("counterexamples_rejected", []))

    # T2 -- code claims an id the document does not define. A control or a
    # principle is a legitimate target: H8 and P1 are specified, they are simply
    # not four-field feature contracts.
    for fid, files in sorted(impl_by_feature.items()):
        if fid not in by_id and fid not in anchors:
            rep.fail("T2", f"@implements({fid!r}) names no feature, control or "
                           f"principle in the spec  [{files[0]}]")

    # T3 / T4 -- status must be supported. The typed population result is also
    # what releasegate consumes; the two gates cannot disagree on an empty set.
    t3, t4 = assess_status_support(features, impl_by_feature, ran)
    for issue in t3.issues:
        rep.fail("T3", issue)
    for issue in t4.issues:
        rep.fail("T4", issue)
    rep.assessments.extend((t3, t4))

    # T3b/T3c -- the other direction, as two exact membership signatures.
    # Implementation remains authored. These observations report disagreement;
    # neither is an alternate value source for the feature.
    trace_only, contradicted = implementation_discrepancies(features, impl_by_feature)
    if trace_only:
        rep.fail("T3b", f"trace-only {len(trace_only)} of {len(features)}: "
                        f"{', '.join(trace_only)}")
        for fid in trace_only:
            rep.note(f"[T3b] {fid} declares @implements in "
                     f"{', '.join(impl_by_feature[fid][:2])}")
    if contradicted:
        rep.fail("T3c", f"authored-none/code-present {len(contradicted)} of "
                        f"{len(features)}: {', '.join(contradicted)}")
        for fid in contradicted:
            rep.note(f"[T3c] {fid} is authored implementation:none and declares "
                     f"@implements in {', '.join(impl_by_feature[fid][:2])}")

    # T5 -- declared eval ids resolve
    for f in features:
        for eid in f.get("historical_eval_ids") or []:
            if eid not in eval_ids:
                rep.fail("T5", f"{f['id']} references eval {eid!r}, which is not defined")

    # T6 -- a check that never rejected anything is an unexercised claim
    for e in evals:
        if e["id"] in ran and e["id"] not in rejected:
            rep.warn("T6", f"{e['id']} has run but has never rejected its counterexample")

    # T7 -- the NEVER half of the contract, and it FAILS inside the frontier.
    #
    # It warned for weeks while seventeen clauses sat untested across five
    # features in slices already marked DONE. Nobody reads the 60th
    # warning. They were untested because tests were derived from the DOES
    # clauses -- the happy path -- and NEVER was treated as prose; writing
    # them found an anonymous session able to open a matter (B-046) within
    # the hour.
    #
    # Beyond the frontier it stays a warning: inventing refusal tests for
    # features nobody has built is how a suite fills with tests that cannot
    # run.
    for problem in awaiting_problems(features, current_items):
        rep.fail("T7-config", problem)

    for f in features:
        nevers = f.get("never") or []
        covered = refuses_by_feature.get(f["id"], set())
        missing = [i for i in range(len(nevers)) if i not in covered]
        if not ((f.get("status") or "decided") in BUILT_OR_BEYOND and missing):
            continue
        blocked = [i for i in missing if (f["id"], i) in AWAITING]
        missing = [i for i in missing if i not in blocked]
        for i in blocked:
            reference = AWAITING[(f["id"], i)]
            blocker = _blocker(reference, features, current_items) or {}
            if blocker.get("implementation") != "complete":
                rep.warn("T7", f"{f['id']}.{i} awaits {reference.label}: "
                                f"{reference.reason}")
        if not missing:
            continue
        note = (f"{f['id']}: {len(missing)} of {len(nevers)} NEVER clauses "
                f"have no test declaring @refuses")
        inside = _within_frontier(f.get("historical_slice"), features)
        if inside is None:
            rep.fail("T7", f"{note} -- and its slice is unreadable, so whether "
                           f"that is a hole in shipped work cannot be decided")
        elif inside:
            rep.fail("T7", note)
        else:
            rep.warn("T7", note)

    # An AWAITING entry whose blocking feature has landed is an exemption
    # nobody re-examined. It expires here rather than in someone's memory.
    #
    # THE TRIGGER IS `implementation: complete`, NOT `tested`. It asked for
    # `tested` while status came from the August spreadsheet, where eighteen
    # features carried that label. The current registry derives `tested` from a
    # complete delivering row with currently passing evidence, and no feature
    # reaches it -- so the old trigger could no longer fire at all, and an
    # exemption that can never expire is a permanent waiver.
    expired = set(expired_awaiting(features, current_items))
    resolvable = 0
    for (fid, idx), reference in AWAITING.items():
        resolved = _blocker(reference, features, current_items) is not None
        resolvable += 1 if resolved and fid in by_id else 0
        if (fid, idx) in expired:
            rep.fail("T7-exempt", f"{fid}.{idx} is exempted pending "
                                  f"{reference.label}, which is now implemented. "
                                  "Write the clause's test.")
    rep.population("T7-exempt", resolvable,
                   "AWAITING exemption(s) naming a resolvable feature id "
                   f"(of {len(AWAITING)} declared)")

    # T11 -- a feature with EVAL prose but no numbered eval in the plan can
    # never reach `tested`, because T4 has nothing to check it against. It is a
    # WARNING rather than a failure: assigning an eval means writing the
    # counterexample it must reject, and inventing 22 of those to clear a
    # dashboard is how a suite stops biting.
    for f in features:
        if not (f.get("historical_eval_ids") or []):
            rep.warn("T11", f"{f['id']} carries EVAL prose but no numbered eval "
                            f"in the plan -- it cannot advance past `decided`")

    # T10 -- the eval record can only GROW (conftest merges rather than
    # replaces, so a narrowed run cannot delete evidence). The price of that is
    # that a renamed or deleted eval id would vouch for something gone, so it
    # is checked here rather than assumed away.
    for eid in sorted(ran - eval_ids):
        rep.fail("T10", f"{eid} is recorded as having run and is not defined in "
                        f"the spec -- stale evidence. Clear .nm/eval_results.json "
                        f"and re-run, or restore the eval.")

    # T8 / T9 -- the gate matrix against the code, in both directions
    consulted = gate_consultations()
    for g in gates:
        seen = consulted.get(g["id"])
        if g["built"] and not seen:
            rep.fail("T8", f"{g['id']} is declared built and no code path "
                           f"consults it -- the matrix promises a gate the "
                           f"product does not run")
        if not g["built"] and seen:
            rep.fail("T9", f"{g['id']} is declared NOT built and is consulted in "
                           f"{', '.join(seen)} -- the matrix tells the advocate "
                           f"nothing evaluates this while something quietly does")
    for gid, files in sorted(consulted.items()):
        if gid not in {g["id"] for g in gates}:
            rep.fail("T8", f"{gid} is used in {files[0]} and is not in the gate "
                           f"matrix")

    # ---- report ----
    total_never = sum(len(f.get("never") or []) for f in features)
    covered_never = sum(len(v) for v in refuses_by_feature.values())
    print("=" * 74)
    print("TRACE  spec <-> code <-> evals")
    print("=" * 74)
    print(f"  features          {len(features):>4}")
    for st in ("decided", "built", "tested", "verified live"):
        n = sum(1 for f in features if (f.get('status') or 'decided') == st)
        if n:
            print(f"    {st:<16}{n:>4}")
    # WHERE THAT ANSWER CAME FROM. `trace` used to read one status field and
    # could not say whether it rested on a delivery row or on a decorator.
    for basis in ("registry", "trace", "absent"):
        n = sum(1 for f in features if f.get("implementation_basis") == basis)
        if n:
            print(f"    via {basis:<12}{n:>4}")
    print(f"  implemented       {len(impl_by_feature):>4}  (features with @implements)")
    print(f"  evals defined     {len(evals):>4}")
    print(f"  evals ever run    {len(ran):>4}")
    print(f"  counterex. bit    {len(rejected):>4}  (rejected at least once)")
    print(f"  NEVER clauses     {covered_never:>4} / {total_never} covered by @refuses")
    print(f"  gates             {len(gates):>4}  "
          f"({sum(1 for g in gates if g['built'])} built, "
          f"{sum(1 for g in gates if g['response'] == 'withhold')} withholding)")

    if not args.summary:
        if rep.failures:
            print("\nFAILURES")
            for check, msg in rep.failures:
                print(f"  [{check}] {msg}")
        if rep.warnings:
            print("\nWARNINGS")
            for check, msg in rep.warnings:
                print(f"  [{check}] {msg}")
        # NOT ASSESSED is the third state, and it prints whether or not
        # anything failed. A check with an empty population is not a check
        # that passed -- it is a check nobody could run.
        empty = [row for row in rep.assessments
                 if row.state == AssessmentState.NOT_ASSESSED]
        if empty:
            print("\nNOT ASSESSED  -- these checks examined nothing")
            for result in empty:
                print(f"  [{result.check}] 0 {result.what}")
        if rep.notes:
            print("\nNOTES")
            for msg in rep.notes:
                print(f"  {msg}")

    print()
    if rep.failures:
        print(f"TRACE FAILED  -- {len(rep.failures)} failure(s), {len(rep.warnings)} warning(s)")
        return 1
    print(f"TRACE OK  -- 0 failures, {len(rep.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
