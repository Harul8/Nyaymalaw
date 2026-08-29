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

T6 and T7 are the ones that catch a green suite that proves nothing.
"""
from __future__ import annotations

import argparse
import ast
import json
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

    # T2 -- code claims a feature that does not exist
    for fid, files in sorted(impl_by_feature.items()):
        if fid not in by_id:
            rep.fail("T2", f"@implements({fid!r}) names no feature in the spec  [{files[0]}]")

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
