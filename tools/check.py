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
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))
from nm.domain.identity import source_fingerprint  # noqa: E402
from tools._console import utf8_console  # noqa: E402

utf8_console()


#: THE CHILD MUST WRITE UTF-8, AND WE MUST SURVIVE IT IF IT DOES NOT.
#:
#: Measured on 4 September 2026. A child process on Windows encodes its stdout
#: with the OS locale (cp1252) when piped -- NOT with the `encoding=` this
#: parent decodes by. pytest printed an em-dash from a test name, the parent's
#: utf-8 decoder raised inside subprocess's reader THREAD, the exception was
#: swallowed there, and `proc.stdout` came back as `None`.
#:
#: The gate then reported `CHECK FAILED -- pytest` with nothing under it, twice,
#: and the reason was that the reason could not be decoded. That is defect shape
#: S1 aimed at the tool whose whole job is to find S1 in the product.
#:
#: Both halves are needed. The environment variable makes the child write utf-8;
#: `errors="replace"` means a child that ignores it -- a shell, a wrapper, a
#: tool with its own encoding -- still yields a readable report instead of None.
def _child_env() -> dict:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def step(label: str, cmd: list[str], allow_warn: bool = False) -> tuple[bool, str]:
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf8", errors="replace", env=_child_env())
    dt = time.time() - t0
    ok = proc.returncode == 0
    mark = "PASS" if ok else ("WARN" if allow_warn else "FAIL")
    print(f"  [{mark}] {label:<34} {dt:5.1f}s")
    out = (proc.stdout or "") + (proc.stderr or "")
    if not ok:
        print("\n" + "\n".join("      " + ln for ln in _why(proc).splitlines()) + "\n")
    return ok or allow_warn, out


#: Lines that say WHICH THING FAILED, as opposed to lines that merely appeared.
#: A tail of stdout+stderr showed a urllib3 version warning and nothing else on
#: a run where eight tests were red -- the warning is on stderr, stderr is
#: appended last, and the tail took the end. A gate that reports FAIL without
#: naming the failure is a gate people re-run by hand to find out what happened.
#: NO TRAILING SPACES. `ERROR ` missed `ERROR: not found:`, which is the line
#: that says what happened -- a marker list that is precise about punctuation
#: is a marker list that misses the case it was written for.
_VERDICT = ("FAILED", "ERROR", "error:", "Error:", "E   ", "AssertionError",
            "no tests ran", "short test summary", "exit code", "SyntaxError",
            "Traceback", "INTERNALERROR")

#: Lines that appear on EVERY run and say nothing about this one.
_NOISE = ("RequestsDependencyWarning", "warnings.warn(")


def _why(proc: subprocess.CompletedProcess) -> str:
    """The failing lines first, then context, rather than whatever came last.

    THE FALLBACK REPORTS ITS OWN FAILURE. When no marker matches, the previous
    version printed a blended tail of stdout+stderr -- and since stderr is
    appended last and carries a urllib3 warning on every single run, the
    "explanation" was reliably that warning. A report that cannot explain the
    failure has to say SO, and say enough to be diagnosed next time.
    """
    def useful(text: str | None) -> list[str]:
        return [ln for ln in (text or "").splitlines()
                if ln.strip() and not any(n in ln for n in _NOISE)]

    out, err = useful(proc.stdout or ""), useful(proc.stderr or "")
    verdicts = [ln for ln in out + err if any(k in ln for k in _VERDICT)]
    if verdicts:
        head = "\n".join(verdicts[:40])
        return head if len(head) <= 3000 else head[:3000] + "\n      ... truncated"

    # NOT ASSESSED, and it must not read as "there was nothing to say".
    # The two streams are shown SEPARATELY and labelled: blending them is what
    # let a constant warning stand in for a diagnosis.
    return "\n".join([
        f"(no line matched a known failure marker. exit={proc.returncode}, "
        f"{len(out)} stdout line(s), {len(err)} stderr line(s) after noise)",
        "--- stdout tail ---", *(out[-25:] or ["(empty)"]),
        "--- stderr tail ---", *(err[-15:] or ["(empty)"]),
    ])


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

    # WHAT TREE IS THIS RUN ABOUT? Taken now and checked again at the end.
    #
    # Measured on 6 September 2026, twice in one hour, in OPPOSITE directions.
    # One run edited the register while the gate was going: `class_a` saw the
    # half-edited state and went red, `pytest (all local)` ran ten minutes
    # later against the finished state and went green, and the gate printed
    # CHECK OK over two failures. Another had a pytest running concurrently,
    # which planted `nm/core/_trace_probe.py` and removed it while pylint was
    # parsing it -- so the gate went red on a file that does not exist.
    #
    # A GATE THAT SHARES A WORKING TREE WITH ANYTHING ELSE MEASURES NOTHING,
    # and it fails in both directions, which is worse than failing in one. The
    # fingerprint already exists for exactly this question -- it is what
    # `run_scenario` uses to refuse a run against a server on other code -- so
    # this is the same mechanism asked of the same tree.
    # SAMPLED AFTER EVERY STAGE, not just at the ends. A file planted and
    # removed inside one stage returns the fingerprint to where it started --
    # proved, not assumed -- so a before/after pair is blind to exactly the
    # transient that broke the pylint stage. Sampling between stages catches
    # anything that outlives a stage boundary, which is what an edit made while
    # the gate runs looks like.
    #
    # WHAT IT STILL CANNOT SEE: a change made and undone entirely within one
    # stage. That is a narrower hole than the one it closes, and it is stated
    # here rather than left for someone to find.
    prints: list[tuple[str, str]] = [("start", source_fingerprint())]

    results = []
    ok, _ = step("layercheck", [py, "tools/layercheck.py"])
    results.append(("layercheck", ok))
    prints.append(("layercheck", source_fingerprint()))
    ok, _ = step("export_spec", [py, "tools/export_spec.py"])
    results.append(("export_spec", ok))
    prints.append(("export_spec", source_fingerprint()))
    ok, _ = step("trace", [py, "tools/trace.py", "--skip-regen"])
    results.append(("trace", ok))
    prints.append(("trace", source_fingerprint()))
    ok, _ = step("speccheck", [py, "tools/speccheck.py"])
    results.append(("speccheck", ok))
    prints.append(("speccheck", source_fingerprint()))
    ok, _ = step("ruff", [py, "-m", "ruff", "check", "nm", "tools", "tests"])
    results.append(("ruff", ok))
    prints.append(("ruff", source_fingerprint()))
    # The rename sweep. pyflakes does not find these, and a stale call site
    # after a rename raised NameError on every matter for weeks.
    ok, _ = step("pylint E0601,E0606",
                 [py, "-m", "pylint", "--disable=all", "--enable=E0601,E0606",
                  "--score=n", "nm"])
    results.append(("pylint", ok))
    prints.append(("pylint", source_fingerprint()))
    # NOT allow_warn, AND IT WAS FOR MONTHS WITH NO REASON GIVEN.
    #
    # class_a is the every-commit tier -- the logic checks. Letting it WARN
    # printed a yellow line and a green CHECK OK over two red tests on 6
    # September 2026, and the reader (me) moved on. The gate was not unsound:
    # `pytest (all local)` runs the same tests and cannot warn, so a real
    # failure still failed the build one stage later. What was wrong is that
    # the SUMMARY said something the run did not support, which is the whole
    # shape this project refuses everywhere else.
    #
    # An exemption someone typed is a decision; this one was typed by nobody
    # and explained by nothing.
    ok, _ = step("pytest -m class_a", [py, "-m", "pytest", "-m", "class_a", "-q"])
    results.append(("class_a", ok))
    prints.append(("class_a", source_fingerprint()))
    ok, _ = step("pytest (all local)", [py, "-m", "pytest", "-q", "-m", "not class_d"])
    results.append(("pytest", ok))
    prints.append(("pytest", source_fingerprint()))

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

    prints.append(("end", source_fingerprint()))
    moved = [(a[0], b[0]) for a, b in zip(prints, prints[1:], strict=False)
             if a[1] != b[1]]
    if moved:
        print()
        print("CHECK VOID  -- the tree changed while the gate ran")
        for was_after, before_next in moved:
            print(f"    it moved between {was_after!r} and {before_next!r}")
        print(f"    started on  {prints[0][1]}")
        print(f"    ended on    {prints[-1][1]}")
        print("  Every result above is about some mixture of trees and none "
              "of them is about any one of them. Re-run on a quiet tree.")
        return 1

    failed = [n for n, ok in results if not ok]
    print()
    if failed:
        print(f"CHECK FAILED  -- {', '.join(failed)}")
        print("Do not claim the task is done.")
        return 1
    # THE GREEN IS STAMPED WITH THE TREE IT IS ABOUT.
    #
    # A gate result is a fact about one tree, and on 6 September 2026 a commit
    # relied on one that no longer existed: gate, edit, commit, and a
    # `spec/plan/build_plan.py` that did not parse reached HEAD. Recording the
    # digest here is what lets `tools/gatestamp.py` -- and the pre-commit hook
    # that calls it -- tell a green tree from a green memory.
    try:
        from tools.gatestamp import record

        record()
    except Exception as exc:  # noqa: BLE001 -- never fail a green gate on this
        # SAID, NOT SWALLOWED. A stamp that silently did not get written would
        # make every later check report `not_assessed` with no reason, which is
        # the absent-input shape on the tool built to catch a stale result.
        print(f"  (gate stamp not recorded: {type(exc).__name__}: {exc})")

    print("CHECK OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
