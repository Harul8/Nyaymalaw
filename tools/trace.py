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
import subprocess
import sys
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

BUILT_OR_BEYOND = ("built", "tested", "verified live")
NEEDS_EVAL_RUN = ("tested", "verified live")


class Report:
    def __init__(self) -> None:
        self.failures: list[tuple[str, str]] = []
        self.warnings: list[tuple[str, str]] = []
        self.notes: list[str] = []
        self.populations: list[tuple[str, int, str]] = []

    def fail(self, check: str, msg: str) -> None:
        self.failures.append((check, msg))

    def warn(self, check: str, msg: str) -> None:
        self.warnings.append((check, msg))

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def population(self, check: str, size: int, what: str) -> None:
        """How many rows a check actually examined. §9, applied to trace.

        A CHECK THAT EXAMINED NOTHING PASSED NOTHING, and until BK-80-AC5 moved
        status to the current registry, nothing here said so. T4 fires only on
        a feature claiming `tested`; the registry now derives that from
        delivering rows and passing evidence, and no feature reaches it today.
        T4 therefore examines an empty population and reports no failure --
        which is correct, and reads exactly like a check that passed.

        Four call sites had the same shape: T3, T4, the AWAITING expiry and the
        release gate's inflation check. So this is one mechanism rather than
        four notes: every status-gated check states its population, and a zero
        prints as NOT ASSESSED rather than as silence.
        """
        self.populations.append((check, size, what))


def load_spec() -> tuple[list[dict], list[dict]]:
    fpath, epath = SPEC / "features.yaml", SPEC / "evals.yaml"
    if not fpath.exists() or not epath.exists():
        sys.exit("spec not generated -- run: python tools/export_spec.py")
    features = yaml.safe_load(fpath.read_text(encoding="utf8"))["features"]
    evals = yaml.safe_load(epath.read_text(encoding="utf8"))["evals"]
    return features, evals


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


def scan_tree(root: Path, decorator: str) -> dict[tuple, list[str]]:
    """Map decorator-arguments -> the files that declared them."""
    out: dict[tuple, list[str]] = {}
    if not root.exists():
        return out
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf8"), filename=str(path))
        except SyntaxError as exc:
            print(f"  ! could not parse {path.relative_to(ROOT)}: {exc}")
            continue
        for args in scan_decorator(tree, decorator):
            out.setdefault(args, []).append(str(path.relative_to(ROOT)))
    return out


def spec_is_current(rep: Report) -> None:
    """T1 -- regenerating the spec must produce no diff."""
    before = {p: p.read_bytes() for p in (SPEC / "features.yaml", SPEC / "evals.yaml")}
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "export_spec.py")],
                          capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        rep.fail("T1", "export_spec.py failed: "
                       f"{proc.stdout.strip()[-300:]} {proc.stderr.strip()[-300:]}")
        return
    for path, old in before.items():
        if path.read_bytes() != old:
            rep.fail("T1", f"{path.relative_to(ROOT)} was stale -- a generator "
                           "changed and the spec was not regenerated. It has "
                           "been rewritten; re-run trace.")



#: NEVER clauses that cannot be tested until a named feature exists. Each is a
#: DECLARED dependency, not an excuse: `tools/trace.py` refuses an entry whose
#: blocking feature has already reached `tested`, so the exemption expires by
#: itself the day the thing it waits for lands.
#:
#: A2.5 -- "never drop a passed deadline" -- is a rule about the BOARD, and the
#: board has no deadlines to render until D3 builds the register. Writing the
#: test now would assert a rule against an empty field, which is the vacuous
#: check this project has already paid for three times.
AWAITING: dict[tuple[str, int], str] = {
    # A2.5 was here, awaiting D3. D3 landed and the clause is tested, so the
    # declaration was retired rather than left to stand. An exemption nobody
    # removes is an exemption nobody reads.
    #
    # WHAT FOLLOWS WAS DECLARED ON 31 AUGUST 2026, when marking A3 `tested`
    # moved the frontier to S9 and T7 stopped warning about these and started
    # failing on them. Each is a clause whose FEATURE has landed and whose
    # rule has nothing yet to bite on -- the alternative was tagging a test
    # that does not really refuse the clause, which is the "test pinned to
    # behaviour" defect S7's own retrospective names.
    #
    # A3 re-orientation: the trigger is a computed CATEGORY CHANGE across a
    # session boundary, and nothing yet computes one -- `cascade.py` handles a
    # corrected fact within a session, which is a different event.
    ("A3", 0): "A3's re-entry trigger, which nothing computes yet",
    ("A3", 1): "A3's re-entry trigger, which nothing computes yet",
    # C7: obtaining material and witness contact are ACTIONS the product does
    # not yet take. `EvidenceItem.lawful_source` records the question; the
    # route that would breach it does not exist to be refused.
    ("C7", 1): "F-phase conduct, where a route to obtain material is proposed",
    ("C7", 2): "F5, witnesses -- there is no witness contact to contaminate",
    # D4: the resolution layer satisfies D4's EVALS (E-050/051/054) and none
    # of its NEVER clauses, which are about RESEARCH EXECUTION -- browsing
    # with a stop condition, disclosing adverse authority. That work is not
    # built, and saying so here is more honest than the status alone.
    ("D4", 0): "D4's research executor, which does not exist yet",
    ("D4", 1): "D4's research executor, which does not exist yet",
    ("D4", 3): "D4's research executor, which does not exist yet",
    # D6: revising a theory needs a theory that has been REVISED, which needs
    # the turn engine to hold one across turns. It holds none yet.
    ("D6", 3): "D6 wired into the turn, so a theory can change between turns",
    # D7: weakening a point before answering it is a property of PROSE the
    # model writes, and nothing yet composes an adversarial pass to inspect.
    ("D7", 1): "D7 wired into the turn, so there is composed prose to check",
}


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
    anchors = load_anchors()
    gates = load_gates()
    by_id = {f["id"]: f for f in features}
    eval_ids = {e["id"] for e in evals}

    impl = scan_tree(SRC, "implements")
    impl_by_feature: dict[str, list[str]] = {}
    for arg_tuple, files in impl.items():
        for fid in arg_tuple:
            impl_by_feature.setdefault(str(fid), []).extend(files)

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

    # T3 / T4 -- status must be supported
    for f in features:
        fid, status = f["id"], (f.get("status") or "decided").strip()
        if status in BUILT_OR_BEYOND and fid not in impl_by_feature:
            rep.fail("T3", f"{fid} is marked {status!r} with no @implements anywhere")
        if status in NEEDS_EVAL_RUN:
            declared = set(f.get("historical_eval_ids") or [])
            if not declared:
                rep.fail("T4", f"{fid} is marked {status!r} but declares no eval ids")
            elif not (declared & ran):
                rep.fail("T4", f"{fid} is marked {status!r} but none of its evals "
                               f"({', '.join(sorted(declared))}) has ever run")
    rep.population("T3", sum(1 for f in features
                             if (f.get("status") or "decided") in BUILT_OR_BEYOND),
                   "feature(s) the current registry reports as built or beyond")
    rep.population("T4", sum(1 for f in features
                             if (f.get("status") or "decided") in NEEDS_EVAL_RUN),
                   "feature(s) claiming tested or verified live")

    # T3b -- THE OTHER DIRECTION, and the one nothing checked. BK-48-AC2.
    #
    # T3 asks whether a feature the registry calls built has code. It cannot
    # see the opposite mismatch: code that declares @implements for a feature
    # the current registry does not record as delivered by anything. That is
    # BK-48's title -- *Phase B is built and the register says it is not* --
    # and until now the only thing that "knew" it was a spreadsheet column.
    #
    # It is ONE line carrying an EXACT count, not one line per feature. The
    # count is the fact worth blocking on: it must fall as delivery rows gain
    # `delivers:`, and it moves the moment a new module claims a feature the
    # register has not caught up with. A per-feature list would be 25 rows
    # nobody reads, which is how T7 was ignored for weeks.
    #
    # THE DECORATOR DOES NOT PROMOTE THE REGISTRY AND THE REGISTRY DOES NOT
    # SILENCE THE DECORATOR. BK-48-AC1 requires the mismatch be reported, and
    # reporting it is all this does.
    unrecorded = sorted(f["id"] for f in features
                        if f["id"] in impl_by_feature
                        and f.get("implementation_basis") != "registry")
    if unrecorded:
        rep.fail("T3b", f"{len(unrecorded)} of {len(features)} features are "
                        f"implemented in code and not recorded as delivered by "
                        f"any row in docs/backlog/status.yaml")
        for fid in unrecorded:
            rep.note(f"[T3b] {fid} declares @implements in "
                     f"{', '.join(impl_by_feature[fid][:2])}")

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
    for f in features:
        nevers = f.get("never") or []
        covered = refuses_by_feature.get(f["id"], set())
        missing = [i for i in range(len(nevers)) if i not in covered]
        if not ((f.get("status") or "decided") in BUILT_OR_BEYOND and missing):
            continue
        blocked = [i for i in missing if (f["id"], i) in AWAITING]
        missing = [i for i in missing if i not in blocked]
        for i in blocked:
            rep.warn("T7", f"{f['id']}.{i} awaits {AWAITING[(f['id'], i)]}")
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
    by_id = {f["id"]: f for f in features}
    expiring = 0
    for (fid, idx), blocker in AWAITING.items():
        dep = blocker.split(",")[0].strip()
        landed = by_id.get(dep, {}).get("implementation") == "complete"
        expiring += 1 if dep in by_id else 0
        if landed:
            rep.fail("T7", f"{fid}.{idx} is exempted pending {dep}, and {dep} "
                           f"is now implemented. Write the clause's test.")
    rep.population("T7-exempt", expiring,
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
        empty = [row for row in rep.populations if row[1] == 0]
        if empty:
            print("\nNOT ASSESSED  -- these checks examined nothing")
            for check, _size, what in empty:
                print(f"  [{check}] 0 {what}")
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
