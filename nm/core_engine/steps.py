"""Plan AN.48, pieces 48a-48b: a matter worked step by step, dispute by dispute, as a junior works with a senior (owner decisions
D134-D166, 9 Nov 2026).

A message sent step by step runs one step at a time and stops for the advocate's go-ahead after each: (1) understand - the papers
read and the matter understood, with its disputes and their legal questions, which today's understanding makes together (D134's
steps 1-3, D152); (2) research; (3) write - each dispute's case, its analysis, review and repairs; (4) finish - the check across the
analyses, the overview and the save as one answer (D147). Research and the analyses run for the disputes the advocate names - one,
several or all (48b; D144, D163); the others wait. End to end runs every remaining step for every dispute without stopping (D135);
Done finishes with what is written. This module holds the step runner's own rules: which step may run and for which disputes, where
the turn stops, the record of a turn waiting for the advocate, and what its stop says and offers. The orchestration lives in
turn.process; the research, the citations, the checks, the board and the reading pane are unchanged (D143), but for the one switch
of 48b (register item 1): research.retrieve_parts and answer_sections.answer each take which disputes run.

A message sent without asking for steps runs end to end exactly as before 48a: the recorded replay (D151) and every earlier test run
so. The record of a turn being worked on gains one addition, "go" (48a2); a record without it is read as before.
"""
from __future__ import annotations

from datetime import datetime, timezone

from nm.core_engine import tentative

MODE = "steps"
#: The steps of a matter, in order.
STEPS = ("understand", "research", "write", "finish")
#: What is done when the turn stops after each step that stops.
AFTER = {"understand": "understood", "research": "researched", "write": "written"}
#: The step a stop after each leads to, where every dispute is taken together (48a).
NEXT = {"understood": "research", "researched": "write", "written": "finish"}
#: 48d (D142, D154): a step that needs the advocate's answer to NM's questions stops for it, and resumes once they are answered.
ASKED = "asked"
#: Every stop a matter may wait at.
WAITS = (*NEXT, ASKED)
#: The first calls of the finish step: while finishing is not allowed they are not sent - the turn stops before the check across the
#: analyses, or before the overview where there is nothing to check across (48a contract).
FINISHING = frozenset({"core_response_cross_check", "core_response_overview"})
#: What the advocate may give at a stop (48a3, 48b): the next step for every dispute, research or the analyses for the disputes
#: named, end to end, or done.
GOS = ("next", "research", "write", "end_to_end", "done")
_FIELDS = {"mode", "allowed", "n", "waiting"}
#: What a go-ahead record may add (48b: the disputes named; 48c: the messages heard while the matter waited; 48e: each step's
#: tentative time beside the time it took; D175: how a follow-up's turn started).
_ADDED = ({"disputes"}, {"heard"}, {"times"}, {"recheck"}, {"proposed"}, {"taken"})
#: D175: how a follow-up's turn started - from NM's earlier understanding of the matter, or with the whole matter read again.
TAKEN_ROUTES = ("kept", "afresh")
#: 48i (D156): at most this many legal questions proposed for what is new wait on a go-ahead record.
MOST_PROPOSED = 20
_PROPOSED = {"dispute_id", "question", "why_needed", "law_to_check", "source"}
#: The steps timed, kept with the matter while it is worked on (48e): the most recent, at most so many.
MOST_TIMED = 100
_TIMED = {"n", "steps", "estimate_s", "actual_s"}
_MOST_STEPS = 10_000
_MOST_DISPUTES = 50
#: The messages heard while a matter waited, kept with it while it is worked on (48c): the most recent, at most so many.
MOST_HEARD = 30
_HEARD = {"text", "taken", "said", "at"}

#: What a stop says comes next where every dispute is taken together, in plain words (48a4).
NEXT_SAID = {
    "research": "Next: research the law - for one dispute, several or all of them.",
    "write": "Next: write and check the analysis - for one dispute, several or all of those researched.",
    "finish": "Next: check the analyses against each other, write the overview and save the answer.",
}
#: The history's line for a conversation waiting for the advocate (D164).
WAITING_SAID = {"understood": "Waiting for you: research", "researched": "Waiting for you: the analyses",
                "written": "Waiting for you: finish", ASKED: "Waiting for your answers"}


class Waiting(Exception):
    """The step the advocate allowed is done; the turn stops for their go-ahead (D134). Not a failure: what was done is saved."""

    def __init__(self, after):
        if after not in WAITS:
            raise ValueError("A turn waits only after a step that stops")
        super().__init__(f"Waiting for the advocate after the matter was {after}")
        self.after = after


def first():
    """The go-ahead a message sent step by step starts with: its first step only."""
    return {"mode": MODE, "allowed": ["understand"], "n": 1, "waiting": None}


def valid(go):
    """Whether a turn's go-ahead record has the form 48a2 saves (conversation.shown_of reads it so): 48b adds the disputes named,
    a record of 48a's form, without them, meaning every dispute."""
    try:
        waiting, disputes, heard, times = go["waiting"], go.get("disputes"), go.get("heard", []), go.get("times", [])
        return (isinstance(go, dict) and _FIELDS <= set(go) <= _FIELDS.union(*_ADDED) and go["mode"] == MODE
                and go.get("recheck", True) is True
                and isinstance(times, list) and len(times) <= MOST_TIMED
                and all(isinstance(entry, dict) and set(entry) == _TIMED and type(entry["n"]) is int
                        and isinstance(entry["steps"], list) and all(step in STEPS for step in entry["steps"])
                        and type(entry["estimate_s"]) is int and type(entry["actual_s"]) is int for entry in times)
                and isinstance(go.get("proposed", []), list) and len(go.get("proposed", [])) <= MOST_PROPOSED
                and all(isinstance(entry, dict) and set(entry) == _PROPOSED and isinstance(entry["why_needed"], str)
                        and all(isinstance(entry[key], str) and entry[key].strip() for key in ("dispute_id", "question", "source"))
                        and isinstance(entry["law_to_check"], list) and all(isinstance(law, str) for law in entry["law_to_check"])
                        for entry in go.get("proposed", []))
                and _taken_valid(go.get("taken"))
                and isinstance(heard, list) and len(heard) <= MOST_HEARD
                and all(isinstance(entry, dict) and set(entry) == _HEARD and all(isinstance(entry[key], str) for key in _HEARD)
                        and entry["text"].strip() for entry in heard)
                and isinstance(go["allowed"], list) and go["allowed"] and all(step in STEPS for step in go["allowed"])
                and len(set(go["allowed"])) == len(go["allowed"])
                and type(go["n"]) is int and 1 <= go["n"] <= _MOST_STEPS
                and (disputes is None or isinstance(disputes, list) and 0 < len(disputes) <= _MOST_DISPUTES
                     and all(isinstance(name, str) and name.strip() for name in disputes)
                     and len(set(disputes)) == len(disputes))
                and (waiting is None or isinstance(waiting, dict) and set(waiting) == {"after", "at"}
                     and waiting["after"] in WAITS and isinstance(waiting["at"], str) and bool(waiting["at"].strip())))
    except (KeyError, TypeError, AttributeError):
        return False


def _taken_valid(taken):
    """D175: none, or how a follow-up's turn started - its route and code's words."""
    return taken is None or (isinstance(taken, dict) and set(taken) == {"route", "said"} and taken["route"] in TAKEN_ROUTES
                             and isinstance(taken["said"], str) and bool(taken["said"].strip()))


def taking(go, route, said):
    """The go-ahead record with how a follow-up's turn started (D175): from NM's earlier understanding ("kept") or with the whole
    matter read again ("afresh"), in code's words."""
    return {**go, "taken": {"route": route, "said": said}}


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


def heard(go, text, taken, said):
    """The go-ahead record with a message heard while the matter waited, and how NM took it (48c, D146): the latest MOST_HEARD."""
    entry = {"text": text, "taken": taken, "said": said, "at": datetime.now(timezone.utc).isoformat()}
    return {**go, "heard": [*(go.get("heard") or ()), entry][-MOST_HEARD:]}


def _carried(go):
    """What a go-ahead carries on to the next step's: the messages heard (48c), the steps timed (48e), the re-check owed (48h),
    the questions proposed for what is new (48i) and how a follow-up's turn started (D175)."""
    return {**({"heard": list(go["heard"])} if go.get("heard") else {}),
            **({"times": list(go["times"])} if go.get("times") else {}),
            **({"recheck": True} if go.get("recheck") else {}),
            **({"proposed": list(go["proposed"])} if go.get("proposed") else {}),
            **({"taken": dict(go["taken"])} if go.get("taken") else {})}


def proposing(go, entries):
    """The go-ahead record with the legal questions a message raised for what is new (48i, D156), each {"dispute_id", "question",
    "why_needed", "law_to_check", "source"}: offered for research, run only on the advocate's go-ahead."""
    return {**go, "proposed": [*(go.get("proposed") or ()), *entries][-MOST_PROPOSED:]}


def unproposed(go, disputes):
    """The go-ahead record without the questions proposed for those disputes, once they are added to the plan (48i)."""
    left = [entry for entry in go.get("proposed") or () if entry["dispute_id"] not in disputes]
    return {**{key: value for key, value in go.items() if key != "proposed"}, **({"proposed": left} if left else {})}


def rechecked(go):
    """The go-ahead record once the analyses written before the advocate's later messages are checked again (48h, D162)."""
    return {key: value for key, value in go.items() if key != "recheck"}


def timed(go, estimate, actual):
    """The go-ahead record with this step's tentative time kept beside the time it took (48e, D140), in seconds."""
    entry = {"n": go["n"], "steps": list(go["allowed"]), "estimate_s": int(estimate), "actual_s": int(actual)}
    return {**go, "times": [*(go.get("times") or ()), entry][-MOST_TIMED:]}


def estimate(go, steps, pages=0):
    """A run's tentative time in seconds (48e, D140): its steps, for the disputes it takes - the understanding for the pages read,
    the research and the analyses for the disputes named (or every one the step can take), the finish for the analyses checked
    across."""
    state = state_of(steps) if (steps or {}).get("understood") else None
    allowed, named = set(go["allowed"]), go.get("disputes")
    unresearched, unwritten = _open(state, go) if state else ([], [])
    total, to_write = 0, 0
    if "understand" in allowed:
        total += tentative.seconds("understand", pages)
    if "research" in allowed and state:
        total += tentative.seconds("research", len(named) if named else len(unresearched))
    if "write" in allowed and state:
        to_write = len(named) if named and "research" not in allowed else (
            len(named) if named else len(unwritten) + (len(unresearched) if "research" in allowed else 0))
        total += tentative.seconds("write", to_write)
    if "finish" in allowed and state:
        total += tentative.seconds("finish", len(state["written"]) + to_write)
    return total


def rethink(go):
    """The go-ahead of a matter to be understood again with what the advocate added (48c; D149's rethink, today's Steer): the
    understanding only, then a stop. Questions proposed for what is new before it are dropped (48i): the matter is understood again
    with everything said - and so is how a follow-up's turn started (D175): the whole matter is read again."""
    return {"mode": MODE, "allowed": ["understand"], "n": go["n"] + 1, "waiting": None, "disputes": None,
            **{key: value for key, value in _carried(go).items() if key not in ("proposed", "taken")}}


#: The one unit of an answer written as a whole - a message with at most one dispute to research (response_writer.parts).
WHOLE = "whole"


def state_of(steps):
    """Where each of a matter's disputes stands, from the steps saved (48b): the disputes the answer is written dispute by dispute
    for - those with questions to research, in the understanding's order, exactly as the answer's parts are laid out
    (response_writer.parts) - with their names, those researched and those whose analysis is written. An answer with at most one
    such dispute is one unit, WHOLE. Known only once the matter is understood."""
    from nm.core_engine import research  # imported here: the research imports what reads this module's records
    understood = (steps or {}).get("understood") or {}
    plan = understood.get("plan") or {}
    disputes = ((plan.get("proposal") or {}).get("understanding") or {}).get("disputes") or []
    names = {dispute["id"]: dispute.get("name") or dispute["id"] for dispute in disputes}
    try:
        groups = list(research.dispute_work(plan)) if plan else []
    except (KeyError, TypeError, AttributeError):
        groups = []
    kept = set((steps or {}).get("parts") or {})
    shown = [saved for saved in ((steps or {}).get("answered") or {}).get("sections") or ()
             if not (saved.get("fallback") or {}).get("reason") == "interrupted"]
    if len(groups) > 1:
        return {"order": groups, "names": {name: names.get(name, name) for name in groups}, "whole": False,
                "researched": kept & set(groups), "written": {saved.get("dispute_id") for saved in shown} & set(groups)}
    return {"order": [WHOLE], "names": {WHOLE: names.get(groups[0], "the answer") if groups else "the answer"}, "whole": True,
            "researched": {WHOLE} if understood and set(groups) <= kept else set(), "written": {WHOLE} if shown else set()}


def _left(state):
    """The disputes still to research, and those researched still to write, in the matter's order."""
    unresearched = [name for name in state["order"] if name not in state["researched"]]
    unwritten = [name for name in state["order"] if name in state["researched"] and name not in state["written"]]
    return unresearched, unwritten


def _open(state, go):
    """_left, with the disputes whose research a later message asks to extend for what is new (48i) open to research again."""
    unresearched, unwritten = _left(state)
    return unresearched + [name for name in _newly(state, go) if name not in unresearched], unwritten


def _newly(state, go):
    """The disputes researched before whose research the questions proposed for what is new would extend (48i), in order."""
    wanted = {entry["dispute_id"] for entry in (go or {}).get("proposed") or ()}
    if not wanted:
        return []
    if state["whole"]:
        return [WHOLE] if WHOLE in state["researched"] else []
    return [name for name in state["order"] if name in wanted and name in state["researched"]]


def given(go, choice, *, held, disputes=None):
    """The go-ahead the advocate gives a waiting turn (48a3, 48b): "research" or "write" for the disputes named (None: every
    dispute that step can now take), "next" (the next step for every dispute), "end_to_end" (every remaining step for every dispute,
    without stopping, D135) or "done" (finish with what is written, D147). Returns the go-ahead for the next run, or None for Done
    before any analysis is written - the matter is then saved as it stands, with no step run. ValueError where the turn does not
    wait, the choice is not one its stop offers, or a dispute named is not one it can take that step for."""
    waiting = go.get("waiting") if isinstance(go, dict) else None
    after = waiting.get("after") if isinstance(waiting, dict) else None
    if not valid(go) or after not in WAITS or choice not in GOS:
        raise ValueError("This conversation is not waiting for that")
    if after == ASKED and choice not in ("end_to_end", "done"):
        # 48d (D154): a step stopped for answers resumes once they are given; meanwhile only end to end or done.
        raise ValueError("Answer NM's questions first, or go on end to end on NM's own understanding")
    state = state_of(held.get("steps"))
    unresearched, unwritten = _open(state, go)
    if disputes is not None and (not isinstance(disputes, list) or not disputes or len(set(disputes)) != len(disputes)):
        raise ValueError("Name each dispute once")
    if choice == "next":
        choice = "research" if unresearched else "write" if unwritten else "done"
    if choice in ("research", "write"):
        open_now = unresearched if choice == "research" else unwritten
        if not open_now or disputes is not None and (state["whole"] or not set(disputes) <= set(open_now)):
            raise ValueError("That step is not open for those disputes")
        named = None if disputes is None or set(disputes) == set(open_now) else [name for name in state["order"] if name in disputes]
        return {"mode": MODE, "allowed": [choice], "n": go["n"] + 1, "waiting": None, "disputes": named, **_carried(go)}
    if disputes is not None:
        raise ValueError("End to end and Done are for the whole matter")
    if choice == "end_to_end":
        start = "research" if unresearched else "write" if unwritten else "finish"
        return {"mode": MODE, "allowed": list(STEPS[STEPS.index(start):]), "n": go["n"] + 1, "waiting": None, "disputes": None,
                **_carried(go)}
    if state["written"]:
        return {"mode": MODE, "allowed": ["finish"], "n": go["n"] + 1, "waiting": None, "disputes": None, **_carried(go)}
    return None


class Gate:
    """Where a run of a turn stops, and which disputes it runs (48a1, 48b). None: no go-ahead was asked for - the run goes end to
    end for every dispute, as before 48a."""

    def __init__(self, go):
        self.go = go
        self.allowed = None if go is None else frozenset(go["allowed"])
        self.disputes = None if go is None or go.get("disputes") is None else frozenset(go["disputes"])
        #: 48h (D161-D162): the analyses written before the advocate's later messages are to be checked again against them, in
        #: the next run that writes or finishes; set once that run has checked them.
        self.recheck, self.rechecked = go is not None and go.get("recheck") is True, False
        #: 48i (D156): the questions proposed for what is new; a run that researches their disputes adds them to the plan.
        self.proposed = [] if go is None else list(go.get("proposed") or ())

    @property
    def stepwise(self):
        return self.allowed is not None

    @property
    def end_to_end(self):
        """Whether this run goes on to the end without stopping (D135): it may both write and finish."""
        return self.allowed is not None and {"write", "finish"} <= self.allowed

    def asks(self):
        """48d (D142, D154): whether a question not yet answered ends this run's step - step by step, short of end to end. End
        to end goes on at once on NM's own understanding (question_wait); a run without steps waits as before."""
        return self.stepwise and not self.end_to_end

    def question_wait(self):
        """How long the window waits for an answer before its default stands (questions.Asking's wait): none, end to end step by
        step (D135, D142); the window's own WAIT otherwise, as before (None)."""
        return 0 if self.end_to_end else None

    def allows(self, step):
        return self.allowed is None or step in self.allowed

    def adding(self):
        """48i (D156): the questions proposed for what is new that this run researches - those of the disputes it researches."""
        if not self.proposed or self.allowed is None or "research" not in self.allowed:
            return []
        return [entry for entry in self.proposed if self.disputes is None or entry["dispute_id"] in self.disputes]

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

    def research_only(self, researched):
        """The disputes this run's research covers (research.retrieve_parts' only, 48b): None for every dispute, as before; where
        research is not allowed, only those already researched, which are kept and not searched again."""
        if self.allowed is None or "research" in self.allowed and self.disputes is None:
            return None
        if "research" not in self.allowed:
            return frozenset(researched)
        return frozenset(researched) | self.disputes

    def write_only(self, researched, written):
        """The disputes whose analyses this run writes or keeps (answer_sections.answer's only, 48b): None for every dispute, as
        before; where writing is not allowed, only those already written; where it is, those named that are researched, or every
        dispute researched."""
        if self.allowed is None or "write" in self.allowed and self.disputes is None and "research" in self.allowed:
            return None
        if "write" not in self.allowed:
            return frozenset(written)
        if self.disputes is None:
            return frozenset(researched) | frozenset(written)
        return frozenset(written) | (self.disputes & frozenset(researched))


def card(held, asked=None):
    """What the stop says (48a4, 48b, 48d), from the saved record alone: after which step it waits, what was done and what comes
    next, the go-aheads it offers - each dispute's next step, the same for all of them at once, End to end and Done - what NM
    noticed that the advocate did not ask about, offered, never done (D164), and NM's questions with the answers given so far
    (asked: the window's sealed state, questions.Asking.state). None where the turn does not wait."""
    after = waiting_of(held)
    if after is None:
        return None
    questions = _questions(asked)
    if after == ASKED:
        open_now = [question for question in questions if question["answer"] is None]
        gos = _timed_gos(held, [{"choice": "end_to_end", "disputes": None, "said": "End to end, on NM's own understanding"},
                                {"choice": "done", "disputes": None, "said": "Done: save as it stands"}])
        return {"after": after, "done_said": "NM needs your answers before it goes on.",
                "next_said": (f"Answer NM's question{'s' if len(open_now) != 1 else ''} below; NM goes on by itself once "
                              "they are answered."),
                "gos": gos, "disputes": [], "noticed": noticed(held.get("steps") or {}), "questions": questions,
                "at": held["go"]["waiting"]["at"], "heard": _heard(held), "taken": _taken(held)}
    steps = held.get("steps") or {}
    state = state_of(steps)
    unresearched, unwritten = _open(state, held["go"])
    newly = set(_newly(state, held["go"]))
    total, names = len(state["order"]), state["names"]
    written = [name for name in state["order"] if name in state["written"]]
    done_said = {
        "understood": KEPT_SAID if (held["go"].get("taken") or {}).get("route") == "kept" else
                      "NM has read your papers and understood the matter: its disputes and their legal questions are on the board.",
        "researched": ("NM has researched the law; what it found is on the board." if state["whole"] else
                       f"NM has researched the law for {len(state['researched'])} of {total} dispute{'s' if total != 1 else ''}; "
                       "what it found is listed under each dispute."),
        "written": ("NM has written and checked the answer; it is shown below." if state["whole"] else
                    f"NM has written and checked the analysis of {len(written)} of {total} dispute{'s' if total != 1 else ''}; "
                    "it is shown below."),
    }[after]
    gos = []
    if state["whole"]:
        # An answer written as a whole: its steps, without disputes to name.
        if unresearched:
            gos.append({"choice": "research", "disputes": None,
                        "said": "Go ahead: research what is new" if newly else "Go ahead: research the law"})
        if unwritten:
            gos.append({"choice": "write", "disputes": None, "said": "Go ahead: write the answer"})
    else:
        if len(unresearched) > 1:
            gos.append({"choice": "research", "disputes": None, "said": "Research all"})
        gos += [{"choice": "research", "disputes": [name],
                 "said": f"Research what is new: {names[name]}" if name in newly else f"Research: {names[name]}"}
                for name in unresearched]
        if len(unwritten) > 1:
            gos.append({"choice": "write", "disputes": None, "said": "Write all researched"})
        gos += [{"choice": "write", "disputes": [name], "said": f"Write the analysis: {names[name]}"} for name in unwritten]
    if unresearched or unwritten:
        gos.append({"choice": "end_to_end", "disputes": None, "said": "End to end"})
    gos.append({"choice": "done", "disputes": None, "said": (
        "Done: check the analyses against each other and save" if len(written) > 1 else
        "Done: finish and save" if written else "Done: save as it stands")})
    gos = _timed_gos(held, gos)
    if state["whole"]:
        next_said = ("Next: research the law." if unresearched else "Next: write and check the answer." if unwritten
                     else "Next: save the answer.")
    elif after == "written" and not unresearched and not unwritten:
        next_said = NEXT_SAID["finish"]
    elif unresearched and not state["researched"]:
        next_said = NEXT_SAID["research"]
    else:
        parts = ([f"research {len(unresearched)} more" ] if unresearched else []) + (
            [f"write {len(unwritten)} analys{'es' if len(unwritten) != 1 else 'is'}"] if unwritten else [])
        next_said = ("Next, as you choose: " + " or ".join(parts) + "; or finish with what is written."
                     if parts else NEXT_SAID["finish"])
    return {"after": after, "done_said": done_said, "next_said": next_said, "gos": gos,
            "disputes": [] if state["whole"] else [
                {"id": name, "name": names[name], "researched": name in state["researched"],
                 "written": name in state["written"]} for name in state["order"]],
            "noticed": noticed(steps), "at": held["go"]["waiting"]["at"], "questions": questions, "heard": _heard(held),
            "taken": _taken(held)}


#: What the stop after a follow-up's first step says was done where it started from NM's earlier understanding (D175).
KEPT_SAID = "NM has taken up your message on the matter as it understood it: its disputes and their legal questions are on the board."


def _taken(held):
    """D175: code's words on how a follow-up's turn started, or None."""
    return (held["go"].get("taken") or {}).get("said")


def _timed_gos(held, gos):
    """48e (D140): each go-ahead a stop offers, with its tentative time - none for Done before any analysis, which runs no step."""
    out = []
    for option in gos:
        try:
            go = given(held["go"], option["choice"], held=held, disputes=option.get("disputes"))
        except ValueError:
            go = None
        out.append({**option, "tentative": tentative.said(estimate(go, held.get("steps"))) if go is not None else None})
    return out


def _heard(held):
    """48c (D146): the messages heard while the matter waited, and how NM took each - the latest five."""
    return [{"text": entry["text"], "said": entry["said"], "taken": entry["taken"]}
            for entry in (held["go"].get("heard") or ())][-5:]


def _questions(asked):
    """48d: NM's questions as the stop shows them - each with its choices and default, and the answer given (None where it waits
    for one; an assumption NM went on with is no answer)."""
    if not isinstance(asked, dict):
        return []
    answers = {entry.get("id"): entry for entry in asked.get("answers") or () if entry.get("how") in ("answered", "late")}
    return [{"id": question["id"], "header": question.get("header", ""), "question": question["question"],
             "why": question.get("why", ""), "choices": question.get("choices") or [],
             "multiple": bool(question.get("multiple")), "default": question.get("default") or [],
             "answer": ({"chosen": answers[question["id"]]["chosen"], "other": answers[question["id"]]["other"]}
                        if question["id"] in answers else None)}
            for question in asked.get("questions") or ()]


def unanswered(asked):
    """48d: the questions of the window's sealed state not yet answered by the advocate."""
    return [question["id"] for question in _questions(asked) if question["answer"] is None]


#: The points the papers show that matter beyond what was asked (research connections, AN.33), offered at a stop (D164).
_NOTICED_KINDS = ("after_time_limit", "against_client", "after_death", "papers_differ", "further_subject")


def noticed(steps):
    """What NM noticed that the advocate did not ask about, in code's words from what the steps saved: a time limit worked out that
    may have run, and the points the papers show together (D164). Read only; an unreadable record notices nothing."""
    points = []
    try:
        limits = steps.get("limits") or {}
        for entry in limits.get("calculations") or ():
            standing = entry.get("standing") or {}
            if standing.get("state") == "expired":
                points.append(f"A time limit may have run: {entry.get('what')} - the last day was "
                            f"{(entry.get('working') or {}).get('last_day')}, {standing.get('days')} days ago.")
        plan = (steps.get("understood") or {}).get("plan") or {}
        for item in (plan.get("proposal") or {}).get("connections") or ():
            if item.get("kind") in _NOTICED_KINDS and isinstance(item.get("point"), str) and item["point"].strip():
                why = item.get("why_it_matters")
                points.append(item["point"].strip() + (f" ({why.strip()})" if isinstance(why, str) and why.strip() else ""))
    except (AttributeError, TypeError):
        return []
    return points[:8]  # at most eight points, each whole


def limit_rests_on(steps, item):
    """48g (D161): whether a worked-out time limit runs from the date of the event the item is - the event's date, as the papers'
    timeline sorts it, is a limit's starting day."""
    plan = (((steps or {}).get("understood") or {}).get("plan") or {})
    events = {event.get("id"): event for event in (plan.get("proposal") or {}).get("chronology") or () if isinstance(event, dict)}
    event = events.get(item)
    if not event or not event.get("sort"):
        return False
    starts = {((entry.get("start") or {}).get("date") or "") for entry in ((steps or {}).get("limits") or {}).get("calculations") or ()}
    return event["sort"] in starts


def unasked(sections):
    """The analyses a matter finished step by step was saved without (48b): (written, of how many), or None where every dispute's
    analysis is written."""
    left = sum(1 for saved in sections if ((saved.get("fallback") or {}).get("reason")) == "interrupted")
    return None if not left else (len(sections) - left, len(sections))


def waiting_said(held):
    """The history's words for a conversation waiting for the advocate (D164), or None."""
    after = waiting_of(held)
    return WAITING_SAID.get(after) if after else None


def attempt_part(go):
    """What a step adds to its turn's attempt identity (D150): each step claims an attempt of its own, with its own allowance of
    corrections; a run end to end, as before 48a, adds nothing."""
    return () if go is None else ("step", go["n"])
