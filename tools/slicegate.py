"""Is slice N done? The plan's own rule, made runnable.

    python tools/slicegate.py            # every slice
    python tools/slicegate.py --slice 2  # one

WHY THIS EXISTS
---------------
The project plan states the rule in a sentence at the top of the Slices sheet:

    A slice is DONE only when its own evals pass AND every earlier slice's
    evals still pass in the same run AND the golden suite for that slice
    passes.

Nothing ran it. Asked how many slices were complete, the honest answer was that
nobody could say without reading three files and counting by hand — and a rule
that has to be evaluated by hand is evaluated optimistically. This project's
own standard is that **a rule you cannot run is not a requirement**, and that
applied to the plan's central rule as much as to anything in the PRD.

WHAT IT REFUSES TO DO
---------------------
It does not mark a slice done because its features say `tested`. Status is a
claim; `trace` already checks that claim against @implements and the eval
record, and this reads the same record rather than a second one.

It does not treat an UNRUN eval as a pass. The three states are DONE, NOT DONE
and CANNOT TELL — the last for class-C evals with no corpus attached and
class-D evals that need per-run approval, which are genuinely unknown rather
than failing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pyyaml is required: pip install pyyaml")

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / ".nm" / "eval_results.json"
GOLDEN_RUNNER = ROOT / "tools" / "run_goldens.py"

DONE, NOT_DONE, UNKNOWN = "DONE", "NOT DONE", "CANNOT TELL"


def load() -> tuple[list[dict], list[dict], set[str], set[str]]:
    ev = yaml.safe_load((ROOT / "spec" / "evals.yaml").read_text(encoding="utf8"))["evals"]
    fs = yaml.safe_load((ROOT / "spec" / "features.yaml").read_text(encoding="utf8"))["features"]
    res = json.loads(RESULTS.read_text(encoding="utf8")) if RESULTS.exists() else {}
    return ev, fs, set(res.get("evals_run", [])), set(res.get("counterexamples_rejected", []))


def slice_order(name: str) -> int:
    """S0, S1 ... S12. Anything else sorts last and is reported, not guessed."""
    if isinstance(name, str) and name.startswith("S") and name[1:].isdigit():
        return int(name[1:])
    return 99


def assess(target: str, ev: list[dict], ran: set[str], bit: set[str]) -> dict:
    """One slice, against the plan's rule.

    CUMULATIVE. A slice is not done on its own evidence alone -- every earlier
    slice must still pass in the same run, which is the regression rule the
    plan puts above every other. A slice that passes while an earlier one
    breaks has not moved the build forward.
    """
    n = slice_order(target)
    own = [e for e in ev if str(e.get("slice")) == target]
    earlier = [e for e in ev if slice_order(str(e.get("slice"))) < n]

    def split(rows):
        run = [e for e in rows if e["id"] in ran]
        blocked = [e for e in rows if e["id"] not in ran
                   and str(e.get("class", "")).upper() in ("C", "D")]
        missing = [e for e in rows if e["id"] not in ran and e not in blocked]
        return run, missing, blocked

    own_run, own_missing, own_blocked = split(own)
    prior_run, prior_missing, prior_blocked = split(earlier)

    reasons = []
    state = DONE
    if not own:
        state, reasons = UNKNOWN, ["the plan defines no evals for this slice"]
    if own_missing:
        state = NOT_DONE
        reasons.append(f"{len(own_missing)} of {len(own)} own evals have never run")
    if prior_missing:
        state = NOT_DONE
        reasons.append(f"{len(prior_missing)} eval(s) in earlier slices have "
                       f"never run — the cumulative rule is not satisfied")
    if not GOLDEN_RUNNER.exists():
        state = NOT_DONE
        reasons.append("the golden runner does not exist, so no slice can pass "
                       "its golden suite (S0/T-005b)")
    if state is DONE and (own_blocked or prior_blocked):
        state = UNKNOWN
        reasons.append(f"{len(own_blocked) + len(prior_blocked)} class-C/D eval(s) "
                       f"need a corpus or explicit approval")

    return {
        "slice": target, "state": state, "reasons": reasons,
        "own": len(own), "own_run": len(own_run), "own_missing": own_missing,
        "own_bit": len([e for e in own if e["id"] in bit]),
        "prior_missing": len(prior_missing),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", type=int, default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    ev, fs, ran, bit = load()
    names = sorted({str(e.get("slice")) for e in ev if str(e.get("slice")).startswith("S")},
                   key=slice_order)
    if args.slice is not None:
        names = [f"S{args.slice}"]

    print("=" * 78)
    print("SLICE GATE   the plan's own rule, run")
    print("=" * 78)
    print("  A slice is DONE only when its own evals pass, every earlier slice")
    print("  still passes in the same run, and its golden suite passes.")
    print()

    done = 0
    rows = []
    for name in names:
        r = assess(name, ev, ran, bit)
        rows.append(r)
        mark = {DONE: "DONE ", NOT_DONE: "  -  ", UNKNOWN: "  ?  "}[r["state"]]
        print(f"  [{mark}] {name:<4} evals {r['own_run']:>2}/{r['own']:<3} "
              f"bit {r['own_bit']:<3} {r['state']}")
        for why in r["reasons"]:
            print(f"           {why}")
        if args.verbose:
            for e in r["own_missing"]:
                print(f"             NOT RUN {e['id']} [{e.get('class')}] "
                      f"{str(e.get('asserts'))[:60]}")
        if r["state"] == DONE:
            done += 1

    print()
    print(f"  {done} of {len(rows)} slices DONE")
    blocked = sum(len(r["own_missing"]) for r in rows)
    print(f"  {blocked} eval(s) across all slices have never run")
    if not GOLDEN_RUNNER.exists():
        print()
        print("  THE BLOCKER: tools/run_goldens.py does not exist. Every slice's")
        print("  exit criteria name the golden suite, so no slice can close")
        print("  until it does. It is task T-005b in slice 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
