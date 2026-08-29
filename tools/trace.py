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

    def fail(self, check: str, msg: str) -> None:
        self.failures.append((check, msg))

    def warn(self, check: str, msg: str) -> None:
        self.warnings.append((check, msg))


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


def gate_consultations() -> dict[str, list[str]]:
    """Which gate ids appear in the source, and where.

    A string scan, deliberately. An AST walk would have to model every way a
    gate id can reach `metrics.fire` -- a constant, a lookup, a mapping like
    `_GROUNDING_STATE` -- and the ways it cannot see are exactly the ways a
    real call site hides. `nm/domain/gates.py` is excluded because it is the
    registry: it names every gate by definition.
    """
    out: dict[str, list[str]] = {}
    registry = SRC / "domain" / "gates.py"
    for path in sorted(SRC.rglob("*.py")):
        if path == registry:
            continue
        text = path.read_text(encoding="utf8")
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
            declared = set(f.get("eval_ids") or [])
            if not declared:
                rep.fail("T4", f"{fid} is marked {status!r} but declares no eval ids")
            elif not (declared & ran):
                rep.fail("T4", f"{fid} is marked {status!r} but none of its evals "
                               f"({', '.join(sorted(declared))}) has ever run")

    # T5 -- declared eval ids resolve
    for f in features:
        for eid in f.get("eval_ids") or []:
            if eid not in eval_ids:
                rep.fail("T5", f"{f['id']} references eval {eid!r}, which is not defined")

    # T6 -- a check that never rejected anything is an unexercised claim
    for e in evals:
        if e["id"] in ran and e["id"] not in rejected:
            rep.warn("T6", f"{e['id']} has run but has never rejected its counterexample")

    # T7 -- the NEVER half of the contract
    for f in features:
        nevers = f.get("never") or []
        covered = refuses_by_feature.get(f["id"], set())
        missing = [i for i in range(len(nevers)) if i not in covered]
        if (f.get("status") or "decided") in BUILT_OR_BEYOND and missing:
            rep.warn("T7", f"{f['id']}: {len(missing)} of {len(nevers)} NEVER clauses "
                           f"have no test declaring @refuses")

    # T11 -- a feature with EVAL prose but no numbered eval in the plan can
    # never reach `tested`, because T4 has nothing to check it against. It is a
    # WARNING rather than a failure: assigning an eval means writing the
    # counterexample it must reject, and inventing 22 of those to clear a
    # dashboard is how a suite stops biting.
    for f in features:
        if not (f.get("eval_ids") or []):
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

    print()
    if rep.failures:
        print(f"TRACE FAILED  -- {len(rep.failures)} failure(s), {len(rep.warnings)} warning(s)")
        return 1
    print(f"TRACE OK  -- 0 failures, {len(rep.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
