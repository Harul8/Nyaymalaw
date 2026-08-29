"""The one command. Run it after every task, before claiming anything is done.

    python tools/check.py            # the per-task gate
    python tools/check.py --slice 1  # add the golden suite runnable at slice N

WHAT IT RUNS, AND WHY IN THIS ORDER
-----------------------------------
 1. layercheck  -- the dependency direction. Fails first because everything
                   after it is worthless if the core has acquired I/O.
 2. export_spec -- regenerate the machine-readable spec from the generators.
 3. trace       -- spec <-> code <-> eval results. Catches status inflation.
 4. pytest -m class_a  -- the invariants. No corpus, no model, seconds.
 5. pytest (rest)      -- everything else that does not need approval.

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
                    help="also run the golden scenarios runnable at this slice")
    args = ap.parse_args()

    py = sys.executable
    print("=" * 74)
    print("CHECK  the per-task gate")
    print("=" * 74)

    results = []
    ok, _ = step("layercheck", [py, "tools/layercheck.py"]); results.append(("layercheck", ok))
    ok, _ = step("export_spec", [py, "tools/export_spec.py"]); results.append(("export_spec", ok))
    ok, _ = step("trace", [py, "tools/trace.py", "--skip-regen"]); results.append(("trace", ok))
    ok, _ = step("pytest -m class_a", [py, "-m", "pytest", "-m", "class_a", "-q"],
                 allow_warn=True); results.append(("class_a", ok))
    ok, _ = step("pytest (all local)", [py, "-m", "pytest", "-q", "-m", "not class_d"])
    results.append(("pytest", ok))

    if args.slice is not None:
        runner = ROOT / "tools" / "run_goldens.py"
        if runner.exists():
            ok, _ = step(f"goldens slice-{args.slice}",
                         [py, str(runner), "--suite", f"slice-{args.slice}"])
            results.append(("goldens", ok))
        else:
            print(f"  [SKIP] goldens slice-{args.slice:<24} not built yet (S0/T-005b)")

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
