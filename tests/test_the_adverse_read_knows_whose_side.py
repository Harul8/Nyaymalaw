"""ADVERSE TO WHOM? The read was asked, and never told. J-3.

MEASURED ON A SERVED TURN. A plaintiff suing on unpaid invoices was told:

    1 adverse fact(s) on this thread are neither explained nor conceded by
    the theory: The buyer wrote acknowledging the debt in writing.

That acknowledgment is the most helpful fact he has. It restarts limitation
under section 18 -- which the same turn retrieved and read back. It was
returned as running against him.

THE ASYMMETRY THAT CAUSED IT
------------------------------
`build_theory_prompt(account, adverse_lines, acting_for, standing)` has taken
the side since it was written. `build_adverse_prompt(account, chronology)` did
not. Both prompts say "the client", so the two read alike and the gap was
invisible: one of them knows who that is and the other was guessing.

Read with no side, an acknowledgment is adverse to whoever gave it. The read
had no way to know we were not that party.

WHAT THIS FILE CHECKS
-----------------------
That the side REACHES the prompt, and that an unresolved posture produces a
different instruction rather than a default. It does not check the model's
answer -- that costs calls and belongs in an eval run deliberately.

Measured after the change, on the chronology that produced the defect: acting
for the plaintiff, the acknowledgment is no longer listed and the year's delay
is, which is the right answer.
"""
from __future__ import annotations

import datetime
import inspect
from types import SimpleNamespace

import pytest
from nm.core import theory as theory_reader
from nm.core.theory import build_adverse_prompt, build_theory_prompt

pytestmark = pytest.mark.class_a


def _chart():
    return [SimpleNamespace(
        id="fact_1", date=datetime.date(2024, 8, 2),
        statement="The buyer wrote acknowledging the debt in writing.")]


def test_the_adverse_read_is_told_which_side_we_act_for():
    """THE INVARIANT. The side is in the prompt, in words the model can act
    on -- not merely accepted as an argument and dropped."""
    prompt = build_adverse_prompt("the file", _chart(), "moving")
    assert "MOVING" in prompt.user, (
        "the side was passed and does not appear in the prompt, so the read "
        "is still deciding `adverse to the client` without knowing who that "
        f"is:\n{prompt.user[:200]}")


def test_an_unresolved_posture_is_stated_and_not_defaulted():
    """AN EMPTY SIDE IS NOT A SIDE.

    Falling back to a default would be the same defect wearing a default's
    clothes: the read would answer confidently for a party nobody established.
    """
    prompt = build_adverse_prompt("the file", _chart(), "")
    assert "NOT SETTLED" in prompt.user, (
        "an unresolved posture produced no instruction about it, so the read "
        "is left to assume a side")
    assert "MOVING" not in prompt.user and "DEFENDING" not in prompt.user, (
        "an unresolved posture still named a side")


def test_both_reads_that_speak_of_the_client_take_the_side():
    """THE POPULATION, and it is why this was invisible for so long.

    Two prompts in this module say `the client`. One took the side and the
    other did not, and nothing compared them. A third prompt added tomorrow
    with the same phrase and no side would be the same defect again.
    """
    speaks_of_client = []
    for name, fn in vars(theory_reader).items():
        if not name.startswith("build_") or not callable(fn):
            continue
        try:
            src = inspect.getsource(fn)
        except (OSError, TypeError):  # pragma: no cover
            continue
        if "client" in src.lower() or "acting_for" in src:
            speaks_of_client.append((name, fn))

    assert len(speaks_of_client) >= 2, (
        f"only {len(speaks_of_client)} prompt builder(s) found -- the scan is "
        f"broken, and a scan that sees nothing passes everything")

    blind = [name for name, fn in speaks_of_client
             if "acting_for" not in inspect.signature(fn).parameters]
    assert not blind, (
        "these prompts reason about `the client` and are not told which side "
        f"that is: {blind}. `adverse to the client` is unanswerable without "
        f"it, and the answer it produced was the plaintiff's best fact filed "
        f"against him.")


def test_the_theory_read_still_takes_the_side():
    """The half that was already right, asserted so a refactor cannot quietly
    make both of them wrong in the same direction."""
    assert "acting_for" in inspect.signature(build_theory_prompt).parameters
