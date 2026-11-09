"""Plan AN.48, piece 48a: a matter worked step by step, as a junior works with a senior (owner decisions D134-D166, 9 Nov 2026).

A message sent step by step runs one step at a time and stops for the advocate's go-ahead after each: (1) understand - the papers
read and the matter understood, with its disputes and their legal questions, which today's understanding makes together (D134's
steps 1-3, D152); (2) research; (3) write - each dispute's case, its analysis, review and repairs; (4) finish - the check across the
analyses, the overview and the save as one answer (D147). End to end runs every remaining step without stopping (D135); Done
finishes with what is written. This module holds the step runner's own rules: which step may run, where the turn stops, the record
of a turn waiting for the advocate, and what its stop says. The orchestration lives in turn.process; the research, the citations,
the checks, the board and the reading pane are unchanged (D143).

A message sent without asking for steps runs end to end exactly as before 48a: the recorded replay (D151) and every earlier test run
so. The record of a turn being worked on gains one addition, "go" (48a2); a record without it is read as before.
"""
from __future__ import annotations

from datetime import datetime, timezone

MODE = "steps"
#: The steps of a matter, in order.
STEPS = ("understand", "research", "write", "finish")
#: What is done when the turn stops after each step that stops.
AFTER = {"understand": "understood", "research": "researched", "write": "written"}
#: The step a stop after each leads to.
NEXT = {"understood": "research", "researched": "write", "written": "finish"}
#: The first calls of the finish step: while finishing is not allowed they are not sent - the turn stops before the check across the
#: analyses (48a contract).
FINISHING = frozenset({"core_response_cross_check", "core_response_overview"})
#: What the advocate may give at a stop (48a3): the next step's go-ahead, end to end, or done.
GOS = ("next", "end_to_end", "done")
_FIELDS = {"mode", "allowed", "n", "waiting"}
_MOST_STEPS = 10_000

#: What a stop says was done, and what comes next, in plain words (48a4).
DONE_SAID = {
    "understood": "NM has read your papers and understood the matter: its disputes and their legal questions are on the board.",
    "researched": "NM has researched the law for each dispute; what it found is listed under each dispute.",
    "written": "NM has written and checked the analysis of each dispute; it is shown below.",
}
NEXT_SAID = {
    "research": "Next: research the law for each dispute.",
    "write": "Next: write and check the analysis of each dispute.",
    "finish": "Next: check the analyses against each other, write the overview and save the answer.",
}
GO_SAID = {"research": "Go ahead: research", "write": "Go ahead: write the analyses", "finish": "Done: finish and save"}
#: The history's line for a conversation waiting for the advocate (D164).
WAITING_SAID = {"understood": "Waiting for you: research", "researched": "Waiting for you: the analyses",
                "written": "Waiting for you: finish"}


class Waiting(Exception):
    """The step the advocate allowed is done; the turn stops for their go-ahead (D134). Not a failure: what was done is saved."""

    def __init__(self, after):
        if after not in NEXT:
            raise ValueError("A turn waits only after a step that stops")
        super().__init__(f"Waiting for the advocate after the matter was {after}")
        self.after = after


def first():
    """The go-ahead a message sent step by step starts with: its first step only."""
    return {"mode": MODE, "allowed": ["understand"], "n": 1, "waiting": None}


def valid(go):
    """Whether a turn's go-ahead record has the form 48a2 saves (conversation.shown_of reads it so)."""
    try:
        waiting = go["waiting"]
        return (isinstance(go, dict) and set(go) == _FIELDS and go["mode"] == MODE
                and isinstance(go["allowed"], list) and go["allowed"] and all(step in STEPS for step in go["allowed"])
                and len(set(go["allowed"])) == len(go["allowed"])
                and type(go["n"]) is int and 1 <= go["n"] <= _MOST_STEPS
                and (waiting is None or isinstance(waiting, dict) and set(waiting) == {"after", "at"}
                     and waiting["after"] in NEXT and isinstance(waiting["at"], str) and bool(waiting["at"].strip())))
    except (KeyError, TypeError):
        return False


def waiting_of(held):
    """After which step a turn being worked on waits for the advocate, or None where it does not wait."""
    go = (held or {}).get("go")
    stopped = (held or {}).get("stopped") or {}
    if not go or stopped.get("code") != "waiting" or not go.get("waiting"):
        return None
    return go["waiting"]["after"]


def waited(go, after):
    """The go-ahead record of a turn that has stopped to wait after a step."""
    return {**go, "waiting": {"after": after, "at": datetime.now(timezone.utc).isoformat()}}


def given(go, choice, *, written):
    """The go-ahead the advocate gives a waiting turn (48a3): "next" (the step after the one it waits after), "end_to_end" (every
    remaining step without stopping, D135) or "done" (finish with what is written, D147). Returns the go-ahead for the next run, or
    None for Done before any analysis is written - the matter is then saved as it stands, with no step run. ValueError where the
    turn does not wait or the choice is not one it offers."""
    waiting = go.get("waiting") if isinstance(go, dict) else None
    after = waiting.get("after") if isinstance(waiting, dict) else None
    if not valid(go) or after not in NEXT or choice not in GOS:
        raise ValueError("This conversation is not waiting for that")
    step = NEXT[after]
    if choice == "next":
        allowed = [step]
    elif choice == "end_to_end":
        allowed = list(STEPS[STEPS.index(step):])
    elif written:
        allowed = ["finish"]
    else:
        return None
    return {"mode": MODE, "allowed": allowed, "n": go["n"] + 1, "waiting": None}


class Gate:
    """Where a run of a turn stops (48a1). None: no go-ahead was asked for - the run goes end to end, as before 48a."""

    def __init__(self, go):
        self.go = go
        self.allowed = None if go is None else frozenset(go["allowed"])

    @property
    def stepwise(self):
        return self.allowed is not None

    def allows(self, step):
        return self.allowed is None or step in self.allowed

    def after(self, step):
        """Called once a step is done: the turn stops here unless a later step is allowed. A step the go-ahead passes through was
        done before it (the advocate is offered a step only once the steps before it are done), so it has nothing left to do."""
        if self.allowed is None or step not in AFTER:
            return
        if not any(STEPS.index(allowed) > STEPS.index(step) for allowed in self.allowed):
            raise Waiting(AFTER[step])

    def call(self, operation):
        """Asked before each model call is sent (calls.TurnCalls): the finish step's first call waits for the go-ahead to finish."""
        if operation in FINISHING and not self.allows("finish"):
            raise Waiting("written")


def card(held):
    """What the stop says (48a4), from the saved record alone: after which step it waits, what was done and what comes next, the
    go-ahead it offers and what NM noticed that the advocate did not ask about - offered, never done (D164). None where the turn
    does not wait."""
    after = waiting_of(held)
    if after is None:
        return None
    step = NEXT[after]
    steps = held.get("steps") or {}
    written = bool(((steps.get("answered") or {}).get("sections")) or ())
    gos = [{"choice": "next", "said": GO_SAID[step]}]
    if step != "finish":
        gos.append({"choice": "end_to_end", "said": "End to end"})
        gos.append({"choice": "done", "said": "Done: save as it stands" if not written else "Done: finish with what is written"})
    return {"after": after, "next": step, "done_said": DONE_SAID[after], "next_said": NEXT_SAID[step], "gos": gos,
            "noticed": noticed(steps), "at": held["go"]["waiting"]["at"]}


#: The points the papers show that matter beyond what was asked (research connections, AN.33), offered at a stop (D164).
_NOTICED_KINDS = ("after_time_limit", "against_client", "after_death", "papers_differ", "further_subject")


def noticed(steps):
    """What NM noticed that the advocate did not ask about, in code's words from what the steps saved: a time limit worked out that
    may have run, and the points the papers show together (D164). Read only; an unreadable record notices nothing."""
    said = []
    try:
        limits = steps.get("limits") or {}
        for entry in limits.get("calculations") or ():
            standing = entry.get("standing") or {}
            if standing.get("state") == "expired":
                said.append(f"A time limit may have run: {entry.get('what')} - the last day was "
                            f"{(entry.get('working') or {}).get('last_day')}, {standing.get('days')} days ago.")
        plan = (steps.get("understood") or {}).get("plan") or {}
        for item in (plan.get("proposal") or {}).get("connections") or ():
            if item.get("kind") in _NOTICED_KINDS and isinstance(item.get("point"), str) and item["point"].strip():
                why = item.get("why_it_matters")
                said.append(item["point"].strip() + (f" ({why.strip()})" if isinstance(why, str) and why.strip() else ""))
    except (AttributeError, TypeError):
        return []
    return said[:8]


def waiting_said(held):
    """The history's words for a conversation waiting for the advocate (D164), or None."""
    after = waiting_of(held)
    return WAITING_SAID.get(after) if after else None


def attempt_part(go):
    """What a step adds to its turn's attempt identity (D150): each step claims an attempt of its own, with its own allowance of
    corrections; a run end to end, as before 48a, adds nothing."""
    return () if go is None else ("step", go["n"])
