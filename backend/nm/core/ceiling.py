"""BK-29 — how much a read is allowed to say, DERIVED and not hand-picked.

THE DEFECT, MEASURED
----------------------
The dispute read ran at `max_tokens=200`. Once it began returning three
verbatim spans the JSON was truncated mid-string at character 827, the read
was lost, and the turn fell back to one thread. Nothing was wrong with the
model or the prompt.

THE SHAPE, WITHOUT THE READ THAT EXPOSED IT
---------------------------------------------
A read that must QUOTE to be believed has an output roughly the size of its
input. A CONSTANT CEILING on such a read is a length limit on the advocate,
disguised as a cost control — and it fails by TRUNCATION, which is a parse
error rather than a short answer, so the whole read is lost rather than
degraded.

That is the worst available failure mode. A short answer is visible and can
be disclosed; a lost read falls back to whatever the call site's `except`
returns, and on the dispute read that fallback was "one thread" — a finding
about the advocate's file produced by a truncated string.

WHY NOT SIMPLY RAISE THEM
---------------------------
Because it moves the cliff without removing it, and it leaves the real
problem: SIXTEEN CALL SITES EACH CHOOSING A NUMBER, every one hand-picked
against briefs nobody recorded. That is the question CLAUDE.md §4 asks — not
*where is the other copy* but *what makes a second copy impossible* — and the
answer has to be one owner, not sixteen better guesses.

WHAT IS DERIVED AND WHAT IS NOT
---------------------------------
Only reads that ECHO. A read whose answer is a fixed shape — a route, a
posture, a cause, a side — has an output size that genuinely does not depend
on how long the brief was, and deriving one from the input would buy nothing
and cost tokens on every long file. Those keep a stated ceiling, and the
stating is now in one table with a reason rather than at a call site.

    ECHOING    the answer contains the advocate's own words, so its size
               follows theirs. The ceiling is derived.
    FIXED      the answer is a verdict, an id, or a short clause. The
               ceiling is stated, once, here.

THE FLOOR AND THE CAP ARE BOTH REAL
-------------------------------------
The floor stops a one-line brief producing a ceiling too small for the JSON
scaffolding around an empty answer. The cap stops a pasted judgment producing
a request the provider refuses — and it is the one place a long input is
allowed to cost the read something, because at that point the read cannot
succeed anyway and the honest outcome is a disclosed failure rather than a
silent truncation.
"""
from __future__ import annotations

from nm.ports.model import estimate_tokens

#: Below this, the scaffolding costs more than the answer. Measured against
#: the smallest real answer any echoing read gives: a JSON object with two
#: keys and a one-clause `why`.
FLOOR = 300

#: Above this, a read is not going to succeed and a bigger request only makes
#: the failure slower and dearer. It is deliberately generous: the point is to
#: stop a runaway, not to ration.
CAP = 4000

#: How much room an echoed answer needs per token of input.
#:
#: THE ANSWER IS NOT THE INPUT. A read that quotes returns a few spans out of
#: the account plus its own scaffolding -- it does not return the account. The
#: multiplier is what an echoing answer costs RELATIVE to what it was shown,
#: and it is above 1 because the JSON keys, the `why` clauses and the span
#: repetition all sit on top of the quoted words.
#:
#: 1.6 IS A STARTING POINT AND IT IS WRITTEN DOWN SO IT CAN BE MEASURED. The
#: numbers it replaces were sixteen separate guesses at call sites, none of
#: them written down and none of them checked against a brief. One number with
#: a stated basis can be moved by evidence; sixteen cannot.
PER_INPUT_TOKEN = 1.6


def for_echo(prompt) -> int:
    """The ceiling for a read whose answer contains the advocate's words.

    DERIVED FROM WHAT THE READ WAS SHOWN, which is the only thing that
    predicts how much it has to say. Passing the prompt rather than a number
    is what makes this impossible to get wrong at a call site: there is no
    number to choose.
    """
    shown = estimate_tokens((prompt.system or "") + (prompt.user or ""))
    return max(FLOOR, min(CAP, int(shown * PER_INPUT_TOKEN)))


#: Reads whose answer is a FIXED shape, and what each is allowed.
#:
#: STATED IN ONE PLACE, WITH THE REASON. These were sixteen literals at
#: sixteen call sites; the numbers are the same, and what changes is that a
#: reader can now see them together and ask why one is 120 and another 900.
#:
#: A READ NOT IN THIS TABLE AND NOT ECHOING IS A BUG, and
#: `tests/test_no_read_picks_its_own_ceiling.py` fails the build on one --
#: which is the mechanism that stops the seventeenth call site inventing a
#: number.
FIXED: dict[str, int] = {
    # A verdict and a quoted trigger. Short by construction.
    "route": 120,
    "role": 150,
    "cause": 300,
    "duty": 250,
    "accrual": 300,
    "consistency": 300,
    # A binding decision plus its reason.
    "binding": 120,
    "correction": 120,
}


def for_read(key: str, prompt, *, echoes: bool) -> int:
    """The ceiling for this read. ONE OWNER, and the call site chooses nothing.

    `echoes` IS THE READ'S OWN PROPERTY and is declared beside the schema, not
    guessed here: whether an answer contains the advocate's words is a fact
    about what was asked for, and a table in this module would be a second
    place to record it.
    """
    if echoes:
        return for_echo(prompt)
    stated = FIXED.get(key)
    if stated is not None:
        return stated
    # NOT A DEFAULT -- A FLOOR THAT IS SAFE AND VISIBLE. An unlisted read gets
    # the same room as the smallest listed one rather than an invented number,
    # and the sweep fails the build so it does not stay unlisted.
    return FLOOR
