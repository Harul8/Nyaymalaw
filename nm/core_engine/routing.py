"""Which model a call of a turn runs on when the advocate chooses Auto (plan AN.38, D47-D49; owner, 3 Nov 2026: "for simpler
things we should use lower model only, and use higher models as required for reviews and complex tasks").

CODE'S TABLE, SET BY MEASUREMENT (D48). Under Auto every step runs on 6 Luna, the default, as it does when 6 Luna is chosen. A call
moves to the stronger model only on evidence code can see in the turn itself, never on a forecast and never because a model says
the work is hard:
  - a piece of the answer whose statements were found wrong or misleading twice - its later tries, and the reviews of them
    (D51: a take-up of what the review found missing, and a rewrite for form, are not faults);
  - an understanding its check still faults after it was revised - the second revision and any after it;
  - a turn whose papers record one act or matter differently - the working out of its time limits.
Luna does not decide call by call (D48): a model rarely sees its own blind spots, and every call would carry a duty or a call more.
6.1 Sol is not in Auto until it is measured on the current build (D49). The 1 Nov 2026 trials found no step where 6.1 Terra earned
its cost outright; these are the places where a second, stronger look is worth paying for, and they are measured before Auto is
made anything but a choice (D47).
"""
from __future__ import annotations

#: The choice, as the request and the saved turn name it, and the model Auto moves a call to.
AUTO = "auto"
STRONGER = "gpt-6.1-terra"
#: The corrections a piece of the answer makes before its later tries, and their reviews, move to the stronger model.
AFTER_CORRECTIONS = 2
#: The corrections that count (D51, owner 4 Nov 2026): a second look at statements the review or code's checks found wrong or
#: misleading, and the mend around what was cut. A take-up of what the review found missing, and a rewrite for form, do not.
FAULTED = frozenset({"core_response_repair"})
#: The calls that move once the same step has been called this many times before in the turn.
AGAIN = {"core_research_revise": 1}
#: What the turn has found that moves a step, and the steps it moves.
ON_EVIDENCE = {"papers_differ": frozenset({"core_calculation"})}


def escalated(operation, *, corrections, earlier, evidence=frozenset()):
    """Whether a call of operation moves to the stronger model under Auto: corrections, those its piece of the answer has made
    that count (FAULTED);
    earlier, the calls of the same step before it in the turn; evidence, what the turn has found (ON_EVIDENCE's names)."""
    if corrections >= AFTER_CORRECTIONS:
        return True
    if operation in AGAIN and earlier >= AGAIN[operation]:
        return True
    return any(operation in steps for found, steps in ON_EVIDENCE.items() if found in evidence)
