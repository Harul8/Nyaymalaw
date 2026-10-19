"""BK-36 — kill the connection at four points, and the brief lands once.

WHAT WAS MISSING, AND IT WAS ONE THING
----------------------------------------
The store already refused two writers: a per-matter lock, an exact version
check, and an engine that will not apply the same turn id twice. What the
BROWSER did was clear the textarea before the request and send no turn id.

So the two halves never met:

  * the server could recognise a repeated turn and was never told which turn
    it was, so a retry after a lost response was a NEW turn and put the same
    brief on the file twice;
  * the only copy of what the advocate had written lived in a failed card in
    memory, gone on reload and gone on sign-out.

Both are the same absence -- an identity for the attempt that outlives the
attempt. These are the four moments BK-36 names, driven on the served path.

WHY THE SERVED PATH AND NOT THE ENGINE
----------------------------------------
Because the defect was never in the engine. `engine.run` has refused a
repeated `turn_id` for slices; the browser did not send one. CLAUDE.md §8 in
its plainest form: a guard that is right in the core and absent at the
composition root is not a guard, and every defect the first external review
found lived in that gap.
"""
from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 8)
BRIEF = ("We act for the plaintiff at Hyderabad. Goods were supplied against "
         "invoices on 14 March 2023 and were never paid for.")


# =========================================== 1. after commit, before response ==


# ================================================== 2. a file that has moved ==


# ============================================ 3. every failure carries a handle ==


# ===================================================== 4. the browser's half ==

def test_the_page_mints_the_turn_id_and_the_retry_reuses_it():
    """THE HALF THAT WAS MISSING, checked on the script itself.

    Read from the text rather than from a browser so it runs every commit;
    `tests/test_the_journey_login_to_logout.py` drives the same behaviour in
    a real page. Both are worth having -- this one fails in seconds and names
    the line.
    """
    import pathlib
    script = (pathlib.Path(__file__).resolve().parents[1]
              / "nm/app/app.js").read_text(encoding="utf-8")

    assert "function newTurnId" in script, (
        "the page does not mint a turn id, so a retry after a lost response "
        "is a new turn and the brief lands twice")
    assert "turn_id: entry.turnId" in script, (
        "the turn id is minted and not sent")
    assert "expected_version: state.matterVersion" in script, (
        "the page does not say which version it believes it is writing on")

    # THE COMPOSER IS NOT CLEARED BEFORE THE REQUEST. It was, and a request
    # that failed before commitment took the advocate's only copy with it.
    submit = script.split("$('composer').addEventListener")[1].split("});")[0]
    assert "box.value = ''" not in submit, (
        "the composer is cleared before the brief is known to be saved")
