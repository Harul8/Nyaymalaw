"""The one command. Run it after every task, before claiming anything is done.

    python tools/check.py            # the per-task gate
    python tools/check.py --slice 1  # add the golden suite runnable at slice N

WHAT IT RUNS, AND WHY IN THIS ORDER
-----------------------------------
 1. layercheck  -- the dependency direction. Fails first because everything
                   after it is worthless if the core has acquired I/O.
 2. export_spec -- regenerate the machine-readable spec from the generators.
 3. trace       -- spec <-> code <-> eval results. Catches status inflation.
 4. speccheck   -- the PRD against ITSELF: counts, references, required
                   fields, unique ids, status vocabulary. trace.py checks
                   spec-against-code; this checks spec-against-spec.
 5. ruff        -- style and obvious defects.
 5. pylint E0601/E0606 -- the rename sweep. pyflakes does not find these, and
                   a stale call site after a rename raised NameError on every
                   matter for weeks in the previous build.
 6. pytest -m class_a  -- the invariants. No corpus, no model, seconds.
 7. pytest (rest)      -- everything else that does not need approval.

Class-D judged runs are NOT here and never will be: they cost money and need
explicit per-run approval. `tools/check.py` must stay cheap enough that there is
no excuse for skipping it.

A red result blocks the claim. Not the work -- the claim.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def step(label: str, cmd: list[str], allow_warn: bool = False) -> tuple[bool, str]:
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf8")
    dt = time.time() - t0
    ok = proc.returncode == 0
    mark = "PASS" if ok else ("WARN" if allow_warn else "FAIL")
    print(f"  [{mark}] {label:<34} {dt:5.1f}s")
    out = (proc.stdout or "") + (proc.stderr or "")
    if not ok:
        tail = "\n".join(line for line in out.splitlines() if line.strip())[-2500:]
        print("\n" + "\n".join("      " + ln for ln in tail.splitlines()) + "\n")
    return ok or allow_warn, out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", type=int, default=None,
                    help="close a slice: adds the golden checks, the slice gate "
                         "and a REQUIRED scenario run")
    ap.add_argument("--scenarios", nargs="*", default=None,
                    help="scenario ids to drive end to end (required with "
                         "--slice; they make live model calls)")
    args = ap.parse_args()

    py = sys.executable
    print("=" * 74)
    print("CHECK  the per-task gate")
    print("=" * 74)

    results = []
    ok, _ = step("layercheck", [py, "tools/layercheck.py"])
    results.append(("layercheck", ok))
    ok, _ = step("export_spec", [py, "tools/export_spec.py"])
    results.append(("export_spec", ok))
    ok, _ = step("trace", [py, "tools/trace.py", "--skip-regen"])
    results.append(("trace", ok))
    ok, _ = step("speccheck", [py, "tools/speccheck.py"])
    results.append(("speccheck", ok))
    ok, _ = step("ruff", [py, "-m", "ruff", "check", "nm", "tools", "tests"])
    results.append(("ruff", ok))
    # The rename sweep. pyflakes does not find these, and a stale call site
    # after a rename raised NameError on every matter for weeks.
    ok, _ = step("pylint E0601,E0606",
                 [py, "-m", "pylint", "--disable=all", "--enable=E0601,E0606",
                  "--score=n", "nm"])
    results.append(("pylint", ok))
    ok, _ = step("pytest -m class_a", [py, "-m", "pytest", "-m", "class_a", "-q"],
                 allow_warn=True)
    results.append(("class_a", ok))
    ok, _ = step("pytest (all local)", [py, "-m", "pytest", "-q", "-m", "not class_d"])
    results.append(("pytest", ok))

    if args.slice is not None:
        # A SLICE DOES NOT CLOSE ON UNIT EVALS ALONE.
        #
        # S0-S3 were all DONE, every eval green, and six realistic scenarios
        # then found three defects in twenty minutes: a posture reader that
        # asked the same question forever, six persisted fields dropped on
        # every restart, and an extraction that read the last line instead of
        # the file. The unit tests were checking the parts; nothing was
        # checking a conversation.
        ok, _ = step("goldens structure + authority",
                     [py, "tools/run_goldens.py"])
        results.append(("goldens", ok))

        ok, _ = step(f"slice gate S{args.slice}",
                     [py, "tools/slicegate.py", "--slice", str(args.slice)])
        results.append(("slicegate", ok))

        if args.scenarios:
            ok, _ = step(f"scenarios slice-{args.slice}",
                         [py, "tools/run_scenario.py", "--approve",
                          "--scenario", *args.scenarios])
            results.append(("scenarios", ok))
        else:
            print("  [FAIL] scenarios                          none named")
            print()
            print("      A slice close requires a SCENARIO RUN, not only its")
            print("      evals. Pass --scenarios GS-xx GS-yy. They make live")
            print("      model calls, which is why they must be named")
            print("      explicitly rather than run by default.")
            print()
            results.append(("scenarios", False))

    failed = [n for n, ok in results if not ok]
    print()
    if failed:
        print(f"CHECK FAILED  -- {', '.join(failed)}")
        print("Do not claim the task is done.")
        return 1
    print("CHECK OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
