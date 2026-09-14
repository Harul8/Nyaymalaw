"""BK-30 — the login-to-logout journey, as ONE COMMAND.

    python assurance/journeys/journey.py

Prints a phase-by-phase result and, for anything that did not pass, the path
to a screenshot and the page's HTML at the moment it stopped.

WHY A RUNNER AND NOT JUST `pytest -m journey`
-----------------------------------------------
Because of what the output has to say. `pytest` reports pass, fail and xfail,
and the middle one of those is the wrong word for what this suite finds: a
phase marked `xfail` here is a REPRODUCED DEFECT with a backlog row attached,
and wave 0's release gate is precisely *"current browser counterexamples fail
for the stated reasons; harness artifacts are reviewable"*.

So the states are named for what they mean to somebody reading the result:

    PASS         the journey works here
    REPRODUCED   a known defect, with the row that closes it
    FAILED       something nobody has recorded -- read the artifact
    NOT RUN      the phase could not execute at all

NOT RUN IS NOT A PASS, and it is the state this repository has been bitten by
most (defect shape S1, in four separate controls). A missing browser, a server
that would not start or a collection error must never leave a green line.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import pathlib
import subprocess
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]

# THE REPO ROOT ON THE PATH FIRST. `python assurance/journeys/journey.py` puts
# `assurance/journeys/` on `sys.path`, not the root, so
# `from assurance.common._console import ...` raises `ModuleNotFoundError` --
# which is how this tool crashed on its first run after the console fix.
# `trace.py` does the same thing for the same reason.
sys.path.insert(0, str(ROOT))
from assurance.common._console import utf8_console  # noqa: E402
from assurance.control_plane.evidence import verification_fingerprint  # noqa: E402
from assurance.journeys import browser_evidence as _browser_evidence  # noqa: E402
from assurance.journeys.journey_verdict import regressions  # noqa: E402

BROWSER_SCHEMA = _browser_evidence.SCHEMA
artifact_inventory = _browser_evidence.artifact_inventory
execution_identity = _browser_evidence.execution_identity
manifest_problems = _browser_evidence.manifest_problems
report_problems = _browser_evidence.problems
publish = _browser_evidence.publish

# THE CONSOLE BEFORE THE PROSE. This table prints em-dashes and `·`, and a
# Windows console defaulting to cp1252 raises `UnicodeEncodeError` half way
# through the report -- which reads as the journey crashing rather than as the
# terminal being unable to spell what it found.
utf8_console()

ARTIFACTS = ROOT / ".nm" / "journey"
REPORT = ARTIFACTS / "report.json"

STATE_ORDER = {"FAILED": 0, "NOT RUN": 1, "REPRODUCED": 2, "PASS": 3}

#: EVERY PHASE THIS COMMAND EXPECTS TO SEE, by node id. BK-51.
#:
#: The runner used to reject only a run that produced ZERO rows. Deleting half
#: the phases -- by a bad marker, a collection error in one class, a rename, or
#: a hand -- left the rest passing and the command green, and the report said
#: nothing about what was no longer being asked.
#:
#: THIS LIST IS DECLARED AND NOT DERIVED. Reading the expected phases out of
#: the test file at run time would make a deleted phase delete its own
#: expectation, which is the same silence with more machinery. Removing a
#: phase is a deliberate act and it edits this tuple.
#: PHASES PERMITTED TO REPRODUCE A DEFECT, each with the reason. BK-44-AC1.
#:
#: Empty today, and that is a claim rather than an oversight: no journey phase
#: currently documents a defect by reproducing it. Any phase that starts to
#: fails the command until somebody either fixes it or writes the reason here.
#:
#: DECLARED AND NOT DERIVED, for the same reason EXPECTED is: reading the
#: permitted set out of the markers at run time would let a marker permit
#: itself, which is the whole of what a non-strict xfail already does wrong.
REPRODUCING: dict[str, str] = {}

EXPECTED = (
    "test_phase_1_an_advocate_signs_in_and_the_gate_gives_way",
    "test_phase_2_the_landing_is_not_blank_but_authenticated",
    "test_phase_3_the_matter_navigator_is_reachable_at_every_width[1280px]",
    "test_phase_3_the_matter_navigator_is_reachable_at_every_width[390px]",
    "test_phase_3_the_matter_navigator_is_reachable_at_every_width[768px]",
    "test_phase_4_a_brief_can_be_filed_without_a_mouse",
    "test_phase_5_no_internal_identifier_or_raw_trace_reaches_the_screen",
    "test_phase_5b_the_answer_does_not_speak_engineering",
    "test_phase_5c_the_answer_reads_as_a_brief_and_not_a_log",
    "test_phase_5d_the_masthead_is_not_a_configuration_dump",
    "test_phase_6b_an_expired_period_is_never_a_window_to_act_within",
    "test_phase_7_search_answers_or_says_why",
    "test_phase_8_history_shows_the_turn_that_was_served",
    "test_phase_8b_history_is_a_record_and_not_a_json_dump",
    "test_phase_9_reload_restores_the_matter",
    "test_phase_10_an_expired_session_does_not_leave_a_signed_in_masthead",
    "test_phase_11_a_logout_the_server_refuses_is_not_shown_as_done",
    "test_phase_12_a_confirmed_logout_cannot_be_undone_by_reload",
    "test_phase_13_a_send_that_fails_keeps_the_brief_and_offers_one_retry",
    "test_phase_13b_a_cancelled_turn_does_not_claim_it_was_not_saved",
    "test_phase_14_every_control_has_a_name_and_the_page_does_not_scroll_"
    "sideways[1280px]",
    "test_phase_14_every_control_has_a_name_and_the_page_does_not_scroll_"
    "sideways[390px]",
    "test_phase_14_every_control_has_a_name_and_the_page_does_not_scroll_"
    "sideways[768px]",
    "test_the_journey_is_actually_driving_a_browser",
    "test_email_registration_opens_own_workspace_and_matter[390]",
    "test_email_registration_opens_own_workspace_and_matter[1280]",
    "test_registration_mismatch_clears_both_passwords",
    "test_pending_registration_owns_its_one_time_result",
    "test_unconfirmed_registration_does_not_claim_no_account_was_created",
    "test_full_length_email_stays_readable_on_a_phone",
    # P18 -- BK-65-AC1 in the browser: `tests/test_the_journey_of_a_correction.py`.
    # SAME REPORT, SAME FINGERPRINT, SAME COMPLETENESS RULE. A second runner for
    # a second suite would be a second place for a phase to go missing quietly;
    # the population is one manifest, and a phase absent from the run is MISSING
    # whichever file it lives in. Names are keyed on the test function, so they
    # must stay unique across the modules this command drives.
    "test_phase_1_a_brief_puts_a_current_deadline_on_the_board",
    "test_phase_2_the_case_file_shows_the_entries_and_says_current",
    "test_phase_3_a_correction_without_a_reason_does_not_submit",
    "test_phase_3b_correcting_the_date_marks_exactly_the_dependents_stale",
    "test_phase_4_the_board_shows_the_window_as_stale_not_as_the_deadline",
    "test_phase_5_a_reload_reads_the_same_currency_from_the_file",
    "test_phase_6_the_next_brief_reworks_the_stale_values",
    # P21 -- research in the browser: `tests/test_the_journey_of_a_search.py`.
    "test_phase_1_a_matter_is_open_and_research_is_offered_for_it",
    "test_phase_2_a_submission_produces_cases_not_labels",
    "test_phase_3_the_case_opens_to_its_paragraphs_by_locator",
    "test_phase_4_attaching_a_paragraph_shows_five_verdicts_not_one",
    "test_phase_5_no_results_is_said_as_searched_not_as_absence_of_law",
    "test_phase_6_an_unsupported_court_is_not_a_zero",
    "test_phase_7_a_reload_shows_the_research_record_from_the_file",
    # P36 -- the whole product at every supported width, including the P29 to
    # P32 preparation flows: `tests/test_the_journey_of_preparation.py`.
    #
    # THE THREE WIDTH ROWS ARE THE CROSS-WIDTH POPULATION CONTROL. BK-47's
    # defect was a phase that returned early and left no row, so a runner
    # counting green rows saw three of three; a manifest that names all three
    # by node id turns that into MISSING, which is what this list is for.
    "test_the_whole_product_is_navigable_at_every_width[390px]",
    "test_the_whole_product_is_navigable_at_every_width[768px]",
    "test_the_whole_product_is_navigable_at_every_width[1280px]",
    "test_the_preparation_surface_is_keyboard_only",
    "test_a_long_email_and_a_long_citation_stay_on_the_phone",
    "test_no_engineering_vocabulary_reaches_the_preparation_screen",
    # P34 -- what the SCREEN offers, which is not whether anybody understood
    # it: `tests/test_the_journey_of_comprehension.py`. BK-66-AC1's list as a
    # property of the surface, so that a comprehension study is not measuring
    # a thing that was never rendered. It closes the `browser_journey` half
    # and nothing else; the study itself is NOT RUN.
    "test_the_answer_says_each_thing_an_advocate_must_identify[390px]",
    "test_the_answer_says_each_thing_an_advocate_must_identify[768px]",
    "test_the_answer_says_each_thing_an_advocate_must_identify[1280px]",
    "test_a_corrected_fact_changes_what_the_screen_says",
    "test_the_source_behind_a_statement_is_reachable_from_the_screen",
    "test_correcting_pausing_and_returning_need_no_retyping",
    "test_no_engineering_state_is_what_the_advocate_has_to_read",
)

#: The modules one `journey` run drives. Listed here beside EXPECTED so that
#: adding a suite is one edit in one file, and the manifest above is the
#: population of both.
SUITES = (
    "tests/test_the_journey_login_to_logout.py",
    "tests/test_email_registration_reaches_a_private_workspace.py",
    "tests/test_the_journey_of_a_correction.py",
    "tests/test_the_journey_of_a_search.py",
    "tests/test_the_journey_of_preparation.py",
    "tests/test_the_journey_of_comprehension.py",
)


def _commit() -> str:
    """The tree this run measured. Never fatal -- a report without a commit is
    worth less than one with, and worth much more than no report at all."""
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=10)
        head = out.stdout.strip() if out.returncode == 0 else "unknown"
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                               capture_output=True, text=True, timeout=10)
        return head + ("+dirty" if dirty.stdout.strip() else "")
    except Exception:                       # noqa: BLE001 -- see docstring
        return "unknown"


def _fingerprint() -> str:
    """The product, browser, test, runner and plan identity this exercised."""
    try:
        return verification_fingerprint()
    except Exception:                       # noqa: BLE001
        return "unknown"


def _phase_name(nodeid: str) -> str:
    """`test_phase_3_the_matter_navigator...[390px]` -> a readable line."""
    name = nodeid.split("::")[-1]
    param = ""
    if name.endswith("]"):
        name, _, param = name[:-1].partition("[")
    words = name.removeprefix("test_").replace("_", " ")
    return f"{words}{f' [{param}]' if param else ''}"


def _display_path(path: pathlib.Path) -> str:
    """Prefer a repository-relative label without rejecting isolated outputs."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def run(extra: list[str]) -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    # THE WHOLE DIRECTORY, NOT JUST THE REPORT. BK-51. Only `report.json` was
    # deleted, and the listing below then printed every PNG left over from an
    # earlier run as though it belonged to this one -- so a clean run could
    # hand you the screenshot of a failure that had already been fixed.
    if REPORT.exists():
        REPORT.unlink()
    for stale in list(ARTIFACTS.glob("*.png")) + list(ARTIFACTS.glob("*.html")):
        stale.unlink()

    # THE MANIFEST IS CHECKED BEFORE THE RUN, NOT AFTER. BK-51-AC1. `expected:
    # len(EXPECTED)` is written into the report as the population size, so a
    # duplicated entry makes a complete run report one phase short forever --
    # and the obvious fix for that is to relax the completeness check, which is
    # how a completeness check dies.
    broken = manifest_problems(EXPECTED)
    if broken:
        for problem in broken:
            print(f"  ! {problem}")
        return 1

    run_id = str(uuid.uuid4())
    started = _fingerprint()

    pytest_argv = [
        "pytest", *SUITES,
        "-m", "journey", "-p", "no:randomly", "-q",
        "--tb=short", "-rA", *extra,
    ]
    proc = subprocess.run(
        [sys.executable, "-m", *pytest_argv],
        cwd=ROOT, capture_output=True, text=True)

    rows = _parse(proc.stdout)
    no_rows = not rows
    if not rows:
        print("NOT RUN  the journey suite produced no phases at all.")
        print("         This is not a pass. The browser may be missing:")
        print("           pip install -e .[journey]")
        print("           python -m playwright install chromium")
        print()
        print(proc.stdout[-4000:])
        print(proc.stderr[-2000:], file=sys.stderr)

    width = max((len(r["phase"]) for r in rows), default=24) + 2
    print()
    print("=" * (width + 40))
    print("  THE JOURNEY  login to confirmed logout")
    print("=" * (width + 40))
    for row in sorted(rows, key=lambda r: (STATE_ORDER[r["state"]], r["phase"])):
        print(f"  [{row['state']:<10}] {row['phase']:<{width}} {row['note']}")

    art = sorted(ARTIFACTS.glob("*.png"))
    if art:
        print()
        print(f"  artifacts for every phase that did not pass ({len(art)}):")
        for p in art:
            print(f"    {_display_path(p)}")

    verdict = regressions(rows, expected=EXPECTED, declared=REPRODUCING)
    failed = verdict.failed
    reproduced = verdict.reproduced
    absent = verdict.absent
    if absent:
        print()
        print(f"  MISSING  {len(absent)} declared phase(s) produced no result:")
        for p in absent:
            print(f"    {_phase_name(p)}")
        print("           A phase that does not run is not a phase that "
              "passed. If it was")
        print("           removed on purpose, remove it from EXPECTED in "
              "this file.")

    # PYTEST'S OWN VERDICT. BK-51. `returncode` was captured and never read,
    # so a run that emitted passing rows and then died in teardown -- or hit
    # an internal error the summary parser does not model -- reported those
    # rows and exited 0.
    # BK-44-AC1. A CLOSED SCENARIO THAT STARTS REPRODUCING IS A REGRESSION.
    #
    # `reproduced` did not fail the command, deliberately: at wave 0 this suite
    # documents defects, and exiting non-zero on every one would make it
    # unrunnable until all of them closed. The hole that leaves is exactly the
    # criterion's mutation -- TURN A CLOSED PASSING SCENARIO INTO A CONDITIONAL
    # EXPECTED FAILURE and the verdict swallows it, because the runner cannot
    # tell a defect somebody wrote down from one that just appeared.
    #
    # So the same three outcomes as the build gate, one level up: a declared
    # reproduction is permitted, an undeclared one blocks, and a DECLARED ONE
    # THAT HAS STARTED PASSING also blocks -- otherwise the list outlives the
    # defects and quietly covers the next regression on the same phase.
    # KEYED ON THE TEST FUNCTION NAME, which is what `EXPECTED` and `seen`
    # hold. The first version keyed on `_phase_name`, which returns the
    # human-readable label -- so no declaration could ever match and every
    # reproduction read as undeclared. A key that never matches is a
    # permission that can never be granted.
    undeclared = verdict.undeclared
    if undeclared:
        print(f"  REGRESSION  {len(undeclared)} scenario(s) reproduced a defect "
              f"nobody declared:")
        for row in undeclared:
            print(f"    {row['nodeid'].split('::')[-1]}  {row.get('note', '')[:70]}")
        print("    A closed scenario that starts reproducing is a regression, "
              "not a documented defect. Declare it in REPRODUCING with the "
              "reason, or fix it.")
    closed = verdict.closed
    if closed:
        print(f"  STALE  {len(closed)} declared reproduction(s) now pass:")
        for name in closed:
            print(f"    {name}")
        print("    Remove them from REPRODUCING. A declaration that outlives "
              "its defect covers the next one silently.")

    broke = proc.returncode not in (0, 1)
    if broke:
        print()
        print(f"  PYTEST EXITED {proc.returncode}, which is neither pass nor "
              f"test failure.")
        print(proc.stdout[-2000:])
        print(proc.stderr[-1000:], file=sys.stderr)

    print()
    print(f"  {len(rows) - len(failed) - len(reproduced)} pass, "
          f"{len(reproduced)} reproduced defect(s), {len(failed)} unexplained"
          + (f", {len(absent)} MISSING" if absent else ""))

    # AN AUDIT RECORD, NOT A LIST OF ROWS. BK-51. The rows alone cannot say
    # which tree they were measured on, so a report file outlived its commit
    # and there was no way to tell.
    # BOTH ENDS OF THE RUN. BK-80-AC2. One fingerprint cannot tell a stable
    # tree from one that moved between phase 1 and phase 14 -- and a run whose
    # tree moved has rows about two different products with no way to say
    # which row is about which.
    finished = _fingerprint()
    # ONLY THIS RUN'S ARTIFACTS. BK-51-AC1. The glob returned every PNG in the
    # directory, so a screenshot from last week's failure was listed as
    # evidence of today's pass. Tagging each with the run identity makes a
    # retained one visible instead of merely present.
    artifact_paths = [
        path for pattern in ("*.png", "*.html")
        for path in sorted(ARTIFACTS.glob(pattern))
    ]
    artifacts = artifact_inventory(artifact_paths, root=ARTIFACTS, run_id=run_id)
    python_runtime = {
        "implementation": sys.implementation.name,
        "version": list(sys.version_info[:3]),
        "executable": pathlib.Path(sys.executable).name,
    }
    configuration = execution_identity(
        argv=pytest_argv, expected=list(EXPECTED), python=python_runtime,
    )
    unexpected = verdict.unexpected
    report = {
        "schema": BROWSER_SCHEMA,
        "run_id": run_id,
        "ran_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "commit": _commit(),
        "fingerprint": started,
        "finished_fingerprint": finished,
        "configuration_identity": configuration,
        "argv": pytest_argv,
        "python": python_runtime,
        "pytest_returncode": proc.returncode,
        "expected": list(EXPECTED),
        "counts": {"pass": len(rows) - len(failed) - len(reproduced),
                   "reproduced": len(reproduced), "unexplained": len(failed),
                   "missing": len(absent), "unexpected": len(unexpected)},
        "missing": absent,
        "artifacts": artifacts,
        "rows": rows,
    }
    publish(REPORT, report)
    print(f"  {_display_path(REPORT)}")

    incompatible = report_problems(
        report, expected=EXPECTED, fingerprint=started,
        configuration_identity=configuration, artifact_root=ARTIFACTS,
    )
    if incompatible:
        print("  REPORT REFUSED")
        for problem in incompatible:
            print(f"    {problem}")
    print()

    # AN UNEXPLAINED FAILURE IS THE ONLY NON-ZERO EXIT -- and a phase that
    # never reported, or a pytest that did not survive, are both unexplained.
    # A reproduced defect is what this suite is FOR at wave 0: exiting non-zero
    # on it would make the command useless until every row it documents is
    # closed, and a command nobody can run is R-6's failure, which this plan
    # already names.
    #
    # BK-51 ADDED THE OTHER TWO. `REPRODUCED` is a defect somebody wrote down.
    # A missing phase is a question nobody asked, and a pytest that exited 4 is
    # a run that did not happen -- neither has a row, so neither may be green.
    if no_rows:
        return 2
    return 1 if (failed or absent or broke or undeclared or closed
                 or unexpected or incompatible) else 0


def _parse(stdout: str) -> list[dict]:
    rows: list[dict] = []
    for line in stdout.splitlines():
        line = line.strip()
        for token, state in (("PASSED ", "PASS"), ("XFAIL ", "REPRODUCED"),
                             ("FAILED ", "FAILED"), ("ERROR ", "NOT RUN"),
                             ("XPASS ", "FAILED"), ("SKIPPED ", "NOT RUN")):
            if not line.startswith(token):
                continue
            rest = line[len(token):]
            nodeid, _, note = rest.partition(" - ")
            if state == "FAILED" and token == "XPASS ":
                note = ("this defect no longer reproduces -- remove the xfail "
                        "marker; " + note)
            rows.append({"phase": _phase_name(nodeid.strip()),
                         "state": state, "note": note.strip()[:120],
                         "scenario": nodeid.strip().rsplit("::", 1)[-1],
                         "nodeid": nodeid.strip()})
            break
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="journey", description=__doc__)
    ap.add_argument("pytest_args", nargs="*",
                    help="passed through to pytest, e.g. -k logout")
    args = ap.parse_args(argv)
    return run(args.pytest_args)


if __name__ == "__main__":
    raise SystemExit(main())
