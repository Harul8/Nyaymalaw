"""How hard each model step reasons (plan AN.30; owner, 1 Nov 2026: "review and update where and how more reasoning should be used to
optimize costs"; AN.28, D4).

Input, not thought, drives what a turn costs. Three paid replays (31 Oct 2026) fitted $0.10 per million fresh input tokens, $0.01 cached
and $0.50 output; a turn's spend was 71% fresh input, 4% cached input and 25% output, the reasoning included. A big pass - a section
written, a review, a take-up - carries 100,000 to 200,000 tokens and costs about a cent and a half, while 4,000 more tokens of reasoning
cost a fifth of a cent. So reasoning is given where it can prevent a repeated pass or a wrong answer and costs little, and withheld where
thought cannot change the result or costs more than it can save:

  - the search steps (phrases, picks) run at the release's own setting (owner decision, 14 Oct 2026): thought does not change what they find;
  - the steps that read the papers or understand the matter run at medium, and a step that reads a large file runs a level higher (AN.28);
  - the steps whose miss reaches the advocate and that ran at the release's own setting - the reading of the advocate's message, the check
    across the sections, the time limits - run at medium, for they are small;
  - a call that looks again at work already done runs a level above its step where its answer is small: the revising of an understanding,
    the re-check of a revision, the looks again at papers, the repair of a paragraph, the take-up, the correction of a time limit;
  - writing and reviewing stay at medium. Their answers are large, and the first paid run of the new build (1 Nov 2026) measured them at
    high: a writing came to 27,600 tokens against about nine thousand at medium and took 194 seconds against about 90, a review 12,600 against
    6,100 and 137 seconds against 66, the answer stage took twice as long (32 minutes against 16), and one writing in six was lost to the
    service after more than four minutes. Nothing shows that so much thought prevents a repeated pass.

Never above high: nothing measured has earned more. Every call's reasoning tokens are recorded in its usage (the adapter), so that a run
shows what each level cost, step by step, and this table can be tuned by measurement and not by belief.
"""
from __future__ import annotations

from nm.shared.model_port import EFFORTS, ContextOverflow, estimate_tokens

#: The levels this table sets, low to high; max is only ever the advocate's choice for a turn (CHOICES).
LEVELS = ("low", "medium", "high")
if not set(LEVELS) <= set(EFFORTS):
    raise RuntimeError("Each level the table sets is an effort the models accept")
#: A step that reads more than this many tokens runs a level higher (plan AN.28, D4).
LARGE_FILE_TOKENS = 60_000

#: step -> (its level, or None for the release's own setting; whether reading a large input raises it a level). The steps are the research
#: steps by their names there, and the answer's, the message's, the time limits' and the pages' by theirs.
STEPS = {
    # The advocate's latest message, read before anything else.
    "message": ("medium", False),
    # Research: the understanding and its checking, the papers read for what they record, and the looks again.
    "understand": ("medium", True), "check": ("medium", True), "revise": ("high", True),
    "chronology": ("medium", True), "transfers": ("medium", True), "connections": ("medium", True),
    "chronology_check": ("high", True), "transfers_check": ("high", True), "connections_check": ("high", True),
    # v14 (AN.33, piece 33g): the second pass over a paper for what its reading left out reads it again with care.
    "chronology_second": ("high", True),
    # v14 (AN.33, piece 33h): the weighing of the points read is a judgement; its check looks again at it.
    "weigh": ("medium", True), "weigh_check": ("high", True),
    # Plan AN.35 (piece 35c1): what makes a dispute's case stronger, and its check.
    "case": ("medium", True), "case_check": ("high", True),
    # Research: the measured search steps stay at the release's own setting (owner decision, 14 Oct 2026).
    "phrases": (None, False), "judgment_phrases": (None, False), "pick": (None, False), "judgment_pick": (None, False),
    # The answer: a section and the overview, the review, the check across the sections, and the second looks.
    "write": ("medium", False), "overview": ("medium", False), "review": ("medium", False), "cross_check": ("medium", False),
    "repair": ("high", False), "take_up": ("high", False),
    # The time limits and their correction.
    "calculate": ("medium", False), "calculate_correct": ("high", False),
    # Pages read from scans: the first reading, a reading made again, and the look at a figure two copies read differently.
    "read_page": (None, False), "read_again": ("medium", False), "relook": ("medium", False),
}


def raised(level):
    """A level one above, never above high; the release's own setting (None) stays its own."""
    return None if level is None else LEVELS[min(LEVELS.index(level) + 1, len(LEVELS) - 1)]


#: The effort an advocate may choose for a turn (plan AN.33, D23; owner, 1 Nov 2026: "You can have some 3-4 categories like low,
#: medium, high, max. So this category should be used to tune the reasoning effort"): medium is this table as it stands; low and high
#: move every call a level down or up, never below low or above high; max puts every call at max, the highest level that 6 Luna, 6.1
#: Terra and 6.1 Sol each accept (their model pages, read 1 Nov 2026). A call at the release's own setting moves from low, the
#: setting of those releases (the adapter's). The choice resets to medium for each new conversation (the page).
CHOICES = ("low", "medium", "high", "max")
DEFAULT_CHOICE = "medium"
#: The most any model an advocate may choose writes in one answer, its reasoning included. From D27 every call may write it, within
#: its room, at every effort; what a call may write no longer grows with the choice (D23, contract (4), subsumed).
MOST_OUTPUT = 128_000
#: D27 (owner, 2 Nov 2026: "we should not put any hard limits, unless it may create never ending loop, we never know how complex
#: future cases can be"): no step's work is cut short by a fixed allowance - a call may write as much as its model can (MOST_OUTPUT,
#: which the adapter lowers for a model that writes less), within the room its input leaves in the context the model is given. A
#: call whose input leaves less than LEAST_ROOM is not made: its context is exceeded.
LEAST_ROOM = 4_000


def room(model, tier, *texts):
    """What a call may write (D27): MOST_OUTPUT, or what its input - texts, all it sends - leaves of the context the model is given
    where that is less; ContextOverflow where it leaves less than LEAST_ROOM. A model that says no context leaves MOST_OUTPUT."""
    budget = model.context_budget(tier) if hasattr(model, "context_budget") else None
    if budget is None:
        return MOST_OUTPUT
    left = budget - estimate_tokens("".join(texts))
    if left < LEAST_ROOM:
        raise ContextOverflow("The complete input of this step exceeds the context the model is given")
    return min(MOST_OUTPUT, left)


def chosen(level, choice):
    """A call's level under the effort the advocate chose for its turn (plan AN.33, D23): level, the step's own (None: the release's
    own setting, which is low for the models an advocate may choose)."""
    if choice not in CHOICES:
        raise ValueError(f"An effort an advocate may choose is one of {CHOICES}")
    if choice == DEFAULT_CHOICE:
        return level
    if choice == "max":
        return "max"
    at = LEVELS.index(level or "low")
    return LEVELS[max(at - 1, 0)] if choice == "low" else LEVELS[min(at + 1, len(LEVELS) - 1)]


def effort(step, *, tokens=0, again=False):
    """How hard a step reasons: its level in STEPS, a level higher where it reads more than LARGE_FILE_TOKENS (tokens: what it reads)
    and where it looks again at work already done (again), never above high; None where the step runs at the release's own setting."""
    level, sized = STEPS[step]
    if level is None:
        return None
    if sized and tokens > LARGE_FILE_TOKENS:
        level = raised(level)
    return raised(level) if again else level
