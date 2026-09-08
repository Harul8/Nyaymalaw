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
from tools._console import utf8_console  # noqa: E402

# THE CONSOLE BEFORE THE PROSE. This table prints em-dashes and `·`, and a
# Windows console defaulting to cp1252 raises `UnicodeEncodeError` half way
# through the report -- which reads as the journey crashing rather than as the
# terminal being unable to spell what it found.
utf8_console()

ARTIFACTS = ROOT / ".nm" / "journey"
REPORT = ARTIFACTS / "report.json"

STATE_ORDER = {"FAILED": 0, "NOT RUN": 1, "REPRODUCED": 2, "PASS": 3}


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
    if REPORT.exists():
        REPORT.unlink()

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
    print()
    print(f"  {len(rows) - len(failed) - len(reproduced)} pass, "
          f"{len(reproduced)} reproduced defect(s), {len(failed)} unexplained")
    REPORT.write_text(json.dumps(rows, indent=2), encoding="utf8")
    print(f"  {REPORT.relative_to(ROOT)}")
    print()

    # AN UNEXPLAINED FAILURE IS THE ONLY NON-ZERO EXIT. A reproduced defect is
    # what this suite is FOR at wave 0 -- exiting non-zero on it would make the
    # command useless until every row it documents is closed, and a command
    # nobody can run is R-6's failure, which this plan already names.
    return 1 if failed else 0


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
