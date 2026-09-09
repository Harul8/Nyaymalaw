"""BK-30 — the login-to-logout journey, as ONE COMMAND.

    python tools/journey.py

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
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# THE REPO ROOT ON THE PATH FIRST. `python tools/journey.py` puts `tools/` on
# `sys.path`, not the root, so `from tools._console import ...` raises
# `ModuleNotFoundError` -- which is how this tool crashed on its first run
# after the console fix. `trace.py` does the same thing for the same reason.
sys.path.insert(0, str(ROOT))
from nm.domain.identity import source_fingerprint  # noqa: E402
from tools._console import utf8_console  # noqa: E402

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
    """The SOURCE identity, which is the one that survives a dirty tree."""
    try:
        return source_fingerprint()
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

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_the_journey_login_to_logout.py",
         "-m", "journey", "-p", "no:randomly", "-q",
         # One line per phase, machine readable, so this runner reports what
         # actually happened rather than parsing prose.
         "--tb=short", "-rA", *extra],
        cwd=ROOT, capture_output=True, text=True)

    rows = _parse(proc.stdout)
    if not rows:
        print("NOT RUN  the journey suite produced no phases at all.")
        print("         This is not a pass. The browser may be missing:")
        print("           pip install -e .[journey]")
        print("           python -m playwright install chromium")
        print()
        print(proc.stdout[-4000:])
        print(proc.stderr[-2000:], file=sys.stderr)
        return 2

    width = max(len(r["phase"]) for r in rows) + 2
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
            print(f"    {p.relative_to(ROOT)}")

    failed = [r for r in rows if r["state"] in ("FAILED", "NOT RUN")]
    reproduced = [r for r in rows if r["state"] == "REPRODUCED"]

    # THE PHASES THAT DID NOT REPORT AT ALL. BK-51.
    seen = {r["nodeid"].split("::")[-1] for r in rows}
    absent = [p for p in EXPECTED if p not in seen]
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
    REPORT.write_text(json.dumps({
        "ran_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "commit": _commit(),
        "fingerprint": _fingerprint(),
        "argv": ["pytest", *extra],
        "pytest_returncode": proc.returncode,
        "expected": len(EXPECTED),
        "counts": {"pass": len(rows) - len(failed) - len(reproduced),
                   "reproduced": len(reproduced), "unexplained": len(failed),
                   "missing": len(absent)},
        "missing": absent,
        "artifacts": sorted(p.name for p in ARTIFACTS.glob("*.png")),
        "rows": rows,
    }, indent=2), encoding="utf8")
    print(f"  {REPORT.relative_to(ROOT)}")
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
    return 1 if (failed or absent or broke) else 0


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
