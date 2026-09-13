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
 7. pytest (local)     -- ordinary unmarked/local tests; excludes Class-A,
                          corpus, browser and judged populations, which have
                          already run or have separate authority.

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

sys.path.insert(0, str(ROOT))
from tools._console import utf8_console  # noqa: E402
from tools.evidence import (  # noqa: E402
    CLASS_A_PYTEST_ARGS,
    LOCAL_CLASS_A,
    ORDINARY_PYTEST_ARGS,
    child_environment,
    load_result,
    validate_class_a,
    verification_fingerprint,
)

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
def _child_env(*, record_class_a: bool = False) -> dict:
    return child_environment(class_a_output=LOCAL_CLASS_A if record_class_a else None)


def step(label: str, cmd: list[str], allow_warn: bool = False) -> tuple[bool, str]:
    t0 = time.time()
    canonical_class_a = cmd == [sys.executable, "-m", "pytest", *CLASS_A_PYTEST_ARGS]
    if canonical_class_a:
        LOCAL_CLASS_A.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_CLASS_A.unlink(missing_ok=True)
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf8", errors="replace",
                          env=_child_env(record_class_a=canonical_class_a))
    dt = time.time() - t0
    ok = proc.returncode == 0
    evidence_problems = (validate_class_a(load_result(LOCAL_CLASS_A))
                         if canonical_class_a and ok else [])
    if evidence_problems:
        ok = False
    mark = "PASS" if ok else ("WARN" if allow_warn else "FAIL")
    print(f"  [{mark}] {label:<34} {dt:5.1f}s")
    out = (proc.stdout or "") + (proc.stderr or "")
    if evidence_problems:
        report = "\n".join("ERROR: Class-A evidence: " + p for p in evidence_problems)
        out += "\n" + report
        print("\n" + report + "\n")
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


def _scoped_verdict(failed: list[str], captured: dict[str, str],
                    checked_digest: str) -> int | None:
    """A scoped build pass, or None to fall through to CHECK FAILED. BK-80-AC7.

    Returns 0 ONLY when every failing step failed for reasons this repository
    has already declared and assigned an owner. Everything else -- a new
    failure, a declared one that started passing, a failing step with no
    captured output, a registry that will not load -- returns None so the
    caller reports CHECK FAILED.

    IT NEVER PRINTS A GREEN. The line is `SCOPED BUILD PASS -- FULL GATE RED`,
    followed by every waived id and its owner, so the red stays in front of
    whoever runs the gate rather than becoming a fact about the repository that
    nobody sees again.
    """
    try:
        from tools.known_failures import (
            compare,
            load,
            observed,
            registry_digest,
        )
        rows = load()
    except Exception as exc:  # noqa: BLE001 -- a broken registry is not a pass
        print(f"  (known-failure registry unusable: {type(exc).__name__}: {exc})")
        return None

    # A FAILING STEP WITH NO CAPTURED OUTPUT CANNOT BE EXPLAINED.
    # Only steps whose output is captured can be reasoned about. Any other
    # failing step means the gate failed somewhere this control cannot see.
    blind = [name for name in failed if name not in captured]
    if blind:
        print(f"  (failing step(s) with no captured output: {', '.join(blind)})")
        return None

    seen = {
        name: observed(name, text, failed=name in failed)
        for name, text in captured.items()
    }
    ran = set(captured)
    verdict = compare(rows, seen, ran)

    if not verdict.ok:
        for step_name, node in verdict.new:
            print(f"  NEW FAILURE in {step_name}: {node}")
        for rid in verdict.fixed:
            print(f"  DECLARED FAILURE NOW PASSING: {rid} -- "
                  f"docs/backlog/known_failures.yaml is stale and must shrink")
        return None

    by_id = {r.id: r for r in rows}
    print("SCOPED BUILD PASS -- FULL GATE RED")
    print(f"  {len(verdict.matched)} declared failure(s), each owned:")
    for rid in verdict.matched:
        print(f"    {rid:24} {', '.join(by_id[rid].owner)}")
    print("  This permits a commit. It is NOT a release, NOT a sign-off, and")
    print("  no acceptance criterion derives done from it.")
    try:
        from tools.gatestamp import record

        record(checked_digest, kind="scoped", waived=verdict.matched,
               baseline=registry_digest())
    except Exception as exc:  # noqa: BLE001
        print(f"  (gate stamp not recorded: {type(exc).__name__}: {exc})")
    return 0


def _known_failure_registry_is_empty() -> bool:
    """Whether a cheap failure is necessarily new and can stop the run.

    With an empty registry, any preflight failure already makes the final
    verdict red; spending thirteen minutes on Class-A and ordinary pytest
    cannot change it. When failures are declared, or the registry cannot be
    read, the later populations still have to run so the scoped comparison
    can prove that no additional failure appeared or disappeared.
    """
    try:
        from tools.known_failures import load

        return not load()
    except Exception:  # noqa: BLE001 -- an unreadable control never narrows work
        return False


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
    prints: list[tuple[str, str]] = [("start", verification_fingerprint())]

    #: Each step's output, so a failing gate can be asked WHICH failures
    #: occurred rather than only that some did. BK-80-AC7.
    captured: dict[str, str] = {}
    results = []
    ok, _ = step("layercheck", [py, "tools/layercheck.py"])
    results.append(("layercheck", ok))
    prints.append(("layercheck", verification_fingerprint()))
    ok, _ = step("export_spec", [py, "tools/export_spec.py"])
    results.append(("export_spec", ok))
    prints.append(("export_spec", verification_fingerprint()))
    ok, out = step("trace", [py, "tools/trace.py", "--skip-regen"])
    captured["trace"] = out
    results.append(("trace", ok))
    prints.append(("trace", verification_fingerprint()))
    ok, _ = step("speccheck", [py, "tools/speccheck.py"])
    results.append(("speccheck", ok))
    prints.append(("speccheck", verification_fingerprint()))
    ok, out = step("ruff", [py, "-m", "ruff", "check", "nm", "tools", "tests"])
    captured["ruff"] = out
    results.append(("ruff", ok))
    prints.append(("ruff", verification_fingerprint()))
    # The rename sweep. pyflakes does not find these, and a stale call site
    # after a rename raised NameError on every matter for weeks.
    ok, out = step(
        "pylint E0601,E0606",
        [py, "-m", "pylint", "--disable=all", "--enable=E0601,E0606",
         "--score=n", "nm"],
    )
    captured["pylint"] = out
    results.append(("pylint", ok))
    prints.append(("pylint", verification_fingerprint()))

    # FAST-FAIL ONLY WHEN THERE IS NOTHING TO RECONCILE. The previous runner
    # found Ruff red in 0.8 seconds and nevertheless spent 805.7 seconds on a
    # Class-A population whose result could not make the gate green. A
    # nonempty known-failure registry is different: every declared failure
    # must still be observed exactly, so that path deliberately continues.
    preflight_failed = [name for name, passed in results if not passed]
    if preflight_failed and _known_failure_registry_is_empty():
        prints.append(("preflight end", verification_fingerprint()))
        moved = [(a[0], b[0]) for a, b in zip(prints, prints[1:], strict=False)
                 if a[1] != b[1]]
        if moved:
            print("\nCHECK VOID  -- the tree changed during preflight")
            for was_after, before_next in moved:
                print(f"    it moved between {was_after!r} and {before_next!r}")
        else:
            print(f"\nCHECK FAILED  -- {', '.join(preflight_failed)}")
        print("  pytest Class-A and ordinary local: NOT RUN -- preflight is "
              "already red and no declared failure requires reconciliation")
        print("Do not claim the task is done.")
        return 1

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
    ok, out = step(
        "pytest Class-A (offline every-commit)",
        [py, "-m", "pytest", *CLASS_A_PYTEST_ARGS],
    )
    captured["class_a"] = out
    results.append(("class_a", ok))
    prints.append(("class_a", verification_fingerprint()))
    # `journey` IS EXCLUDED, AND THIS IS AN ADMITTED GAP RATHER THAN A TIDY
    # ONE. BK-30's browser suite needs a Chromium binary that `.[dev]` does
    # not install, and it starts a real HTTP server and a real browser for
    # every phase -- two minutes on top of a gate that already takes seven,
    # on a machine that may not have the extra installed at all.
    #
    # WHAT THAT COSTS: a regression in `web/` -- the stylesheet, the page or
    # the script -- does not fail this gate. It failed nothing before either,
    # which is how `.gate` came to have two owners and paint the whole
    # application white after every turn. The difference is that there is now
    # a command that finds it:
    #
    #     python tools/journey.py
    #
    # Run it after any change under `web/`. `tests/test_no_css_class_has_two
    # _owners.py` and `tests/test_the_page_and_the_script_agree.py` are class_a
    # and DO run here -- they catch the two failure shapes that have actually
    # bitten, from the text alone.
    # CLASS C IS NOT AN ORDINARY LOCAL TEST. It can read the legal corpus or a
    # live provider and its own marker says it runs on an ingest/index change.
    # `not class_d and not journey` accidentally selected it on every build;
    # a missing credential commonly made that look harmless by skipping. A
    # skip caused by absent authority is not permission to enter the class.
    ok, out = step("pytest (ordinary local)",
                   [py, "-m", "pytest", *ORDINARY_PYTEST_ARGS])
    captured["pytest"] = out
    results.append(("pytest", ok))
    prints.append(("pytest", verification_fingerprint()))

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

    prints.append(("end", verification_fingerprint()))
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
        # IS THIS THE RED WE ALREADY KNOW ABOUT, OR A NEW ONE? BK-80-AC7.
        #
        # Three unbuilt PRD obligations report honestly here, so this gate
        # returned 1 forever and the pre-commit hook refused every commit --
        # including the work that would close them. The ways out were to
        # bypass the hook, weaken the failing tests, or stop committing.
        #
        # So it compares instead. A run whose failures are EXACTLY the
        # declared, owned set is a scoped build pass: commit permitted, this
        # gate still prints FULL GATE RED, and the stamp records that it was
        # scoped. A new failure blocks. A declared failure that has started
        # PASSING also blocks, because a waiver that outlives its defect
        # silently covers the next one -- the non-strict xfail hole, one level
        # up. See docs/backlog/known_failures.yaml.
        scoped = _scoped_verdict(failed, captured, prints[-1][1])
        if scoped is not None:
            return scoped
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

        record(prints[-1][1])
    except Exception as exc:  # noqa: BLE001 -- never fail a green gate on this
        # SAID, NOT SWALLOWED. A stamp that silently did not get written would
        # make every later check report `not_assessed` with no reason, which is
        # the absent-input shape on the tool built to catch a stale result.
        print(f"  (gate stamp not recorded: {type(exc).__name__}: {exc})")

    print("CHECK OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
