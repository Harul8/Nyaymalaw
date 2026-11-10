"""One authenticated turn owns preparation, bounded repair, release and the check of what it saves.

Drafts and reviewer judgments cannot write matter facts or announce execution.
The sealed conversation owner commits the exact checked answer and its evidence
together. This initial flow performs read-only research; record editing is separate.
A saved answer is checked once, when it is saved, and read back exactly as saved: reopening
never rebuilds it (owner decision P46, 24 Oct 2026).
"""
from __future__ import annotations

import logging
import re
import threading
import time

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

from nm.core_engine import answer_sections, answer_sources, calculation, case_strength, checklist, estimates, follow_up, questions
from nm.core_engine import reasoning, replay_scope, research, response_rendering, response_writer
from nm.core_engine import steps as stepwise, tentative, titles, understanding
from nm.core_engine.calls import CorrectionUnavailable, ReleaseWithheld, StopRequested, TurnCalls
from nm.core_engine.conversation import (
    ConversationRefused, TurnContext, asking_of, chat_matter_id, checked_rows, commit_turn, committed_version, digest,
    drop_asking, drop_shown, hold_asking, hold_shown, hold_title, open_turn, sent, shown_of, stored_chat, title_of,
)
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.model_config import DEFAULT_TURN_MODEL
from nm.shared.egress_contracts import EgressRefused
from nm.shared.model_port import USAGE_LIMIT_MESSAGE, ContextOverflow, ModelError, SchemaViolation, Tier, UsageLimitReached
from nm.shared.store_port import StaleWrite
from nm.shared.turn_attempt_port import AttemptRefused, TurnAttemptPort

LEGACY_CONTRACT = "core_turn_v1"
log = logging.getLogger(__name__)
#: v2 with authority evidence; v3 adds the time limits worked out (item 9, 15 Oct 2026).
AUTHORITY_CONTRACT = "core_turn_v2"
CALCULATION_CONTRACT = "core_turn_v3"
#: v4 records what was released (owner decision, 17 Oct 2026; gate G-SECTION): the
#: sections held back after the rewrites, with the date findings that held them, or None.
RELEASE_CONTRACT = "core_turn_v4"
#: v4 saving the matter's checklist with the turn as its current records, re-derived
#: exactly from the turn's own activity when it is reopened (owner decisions, 17 Oct 2026).
RECORDS_CONTRACT = "core_turn_v5"
#: v6 (owner decisions P25-P27, 19 Oct 2026; plan AN.2): answered dispute by dispute. The
#: activity keeps each section's last reviewed draft, its trimmed versions with their own
#: reviews, why a note stands in its place where nothing of it survived, any correction
#: after the check across the sections, that check, and the overview; reopening re-derives
#: each from them (answer_sections.validate). Nothing is withheld whole for what a review
#: finds.
BY_DISPUTE_CONTRACT = "core_turn_v6"
#: v7 (owner decision P29, 20 Oct 2026): v6 reviewed under review v10, each section, correction
#: and overview also keeping what code refused of what the writer or the review returned, and a
#: draft code admitted that no review could be completed for, each with why (answer_sections.KEPT).
KEPT_CONTRACT = "core_turn_v7"
#: v8 (owner decisions P39-P45, 24 Oct 2026; plan AN.6): v7 written for the advocate and laid
#: out as they read it - each section by writer v13 and reviewed by review v11, the overview by
#: writer v13 - and rendered as v18.
PRESENTED_CONTRACT = "core_turn_v8"
#: v9 (plan AN.28, D2, 31 Oct 2026): v8 whose sections and overview are written by writer v14 and
#: reviewed by review v12 - only the paragraphs at fault go back to the writer for a second look, and
#: what still fails is blocked sentence by sentence, never with its paragraph or section - each part
#: keeping its second looks (answer_sections.LOOKS), and rendered as v19.
LOOKED_CONTRACT = "core_turn_v9"
#: v10 (plan AN.35, D31; pieces 35c2-35c3b): v9 whose dispute sections each keep what makes their case stronger
#: (answer_sections.CASE), set out beside the section's writing from research v15; its sections are written by writer v15, which
#: writes no checklist, and the answer is rendered as v20, the case beside each section.
CONTRACT = "core_turn_v10"
#: The turns answered dispute by dispute.
SECTIONED = (BY_DISPUTE_CONTRACT, KEPT_CONTRACT, PRESENTED_CONTRACT, LOOKED_CONTRACT, CONTRACT)
#: The turns that keep what code refused (P29): v7 on.
_KEEPS = (KEPT_CONTRACT, PRESENTED_CONTRACT, LOOKED_CONTRACT, CONTRACT)
#: The turns whose parts keep their second looks (AN.28): v9 on.
_LOOKS = (LOOKED_CONTRACT, CONTRACT)
#: The rendering each turn answered dispute by dispute was saved with.
_RENDERINGS = {BY_DISPUTE_CONTRACT: "core_response_rendering_v17", KEPT_CONTRACT: "core_response_rendering_v17",
               PRESENTED_CONTRACT: "core_response_rendering_v18", LOOKED_CONTRACT: "core_response_rendering_v19",
               CONTRACT: "core_response_rendering_v20"}
_RELEASED = (RELEASE_CONTRACT, RECORDS_CONTRACT)
EXECUTION = research.EXECUTION
_ACTIVITY_FIELDS = {"contract", "interpretation", "research", "sources", "draft",
                    "review", "execution", "rendering_contract"}
_SECTIONED_FIELDS = {"contract", "interpretation", "research", "sources", "execution", "calculation",
                     "rendering_contract", "sections", "cross_check", "overview"}


#: Receipts describe what this code did, never whether the request is fulfilled (research owns them).
execution_record = research.execution
#: Said above an answer the usage ran out part-way through (plan AN.37, D46): the owner's words of P51, then what was kept.
STOPPED_FOR_USAGE = (USAGE_LIMIT_MESSAGE + " NM stopped part-way through this answer: the parts it had finished and checked "
                     "are below, and the rest are marked as not finished.")
#: Why an answer stopped part-way, in code's own words, by the code the turn keeps with what it finished (plan AN.41, D69). Said in
#: red in the conversation with Continue and Discard; said above the answer once it is saved as it stopped (D71).
STOPS = {
    "interrupted": "NM was restarted while it worked on this message.",
    "signed_out": "Your sign-in ended while NM was working on this message.",
    "model_permission_required": "AI data sharing is turned off for your account, so NM could not go on with this message.",
    "usage_limit": USAGE_LIMIT_MESSAGE,
    "response_unavailable": "The AI service could not be reached reliably part-way through this message.",
    "stopped": "You stopped NM part-way through this answer.",
    "not_saved": "NM finished this answer but could not save it.",
    "failed": "Something went wrong on NM's side part-way through this message.",
    # Plan AN.48 (D134): a matter worked step by step stops for the advocate's go-ahead after each step; Done before any analysis
    # was written saves it as it stands (48a3).
    "waiting": "NM is waiting for your go-ahead on this matter.",
    "done": "You finished this matter here.",
}
#: What each cause needs before Continue can work (D70): put right first, said with the red message.
STOP_NEEDS = {
    "signed_out": "Sign in again, then press Continue.",
    "model_permission_required": "Turn AI data sharing back on, then press Continue.",
    "usage_limit": "Continue works once more usage is available.",
}
#: Plan AN.41 (D66, D71): a turn saved as it stopped before NM had finished any part of it - the advocate's message and files,
#: and code's words on why it stopped, with nothing of an answer.
UNANSWERED_CONTRACT = "core_turn_unanswered_v1"
#: How long a finished answer waits, at most, for the conversation's title still being written beside it (plan AN.43), in seconds.
TITLE_WAIT = 60
#: What a stopped answer says of the time limits when it stopped before they were worked out.
LIMITS_UNFINISHED = "The answer stopped before the time limits were worked out"


def stopped_said(held):
    """Code's words above an answer saved as it stopped (D71): why it stopped, and that what it finished is below."""
    why = STOPS.get((held.get("stopped") or {}).get("code") or "interrupted", STOPS["failed"])
    if "steps" in held and held["steps"]["understood"] is None:
        return why + " NM stopped before it had finished any part of an answer: your message and files are saved."
    return (why + " NM stopped part-way through this answer: the parts it had finished and checked are below, and the rest "
            "are marked as not finished.")


def _diagnosis(code, exc, calls):
    """Why a message was not answered, content-free, kept with the attempt and logged:
    the outcome, the gate or failure kind, and the stage that ended the turn. Never the
    message, a draft or the review's words (open items round, 15 Oct 2026)."""
    message = str(exc)
    kind = (message.split(":", 1)[0] if isinstance(exc, ReleaseWithheld) and message.startswith("G-")
            else "release" if isinstance(exc, ReleaseWithheld) else type(exc).__name__)
    stage = calls.calls[-1]["operation"].removeprefix("core_") if calls.calls else "none"
    return re.sub(r"[^A-Za-z0-9_-]", "_", f"{code}-{kind}-{stage}")[:80]


def _reporter(progress):
    """Stage reports for the waiting advocate; a reporting failure never fails the turn."""
    def report(stage, **detail):
        if progress is None:
            return
        try:
            progress(stage, **detail)
        except Exception:  # noqa: BLE001 - the progress display is auxiliary to the turn
            log.warning("Turn progress could not be recorded", exc_info=True)
    return report


def _needs_research(plan):
    understanding = (plan.get("proposal") or {}).get("understanding") or {}
    return understanding.get("needs_research") is True


def _restrictions(interpretation):
    """The exact words of what the advocate restricted in their latest message, as the interpretation found them (plan AN.27,
    P5); None where the interpretation did not complete cleanly - what was not established is never 'none'."""
    if (not isinstance(interpretation, dict) or interpretation.get("issues")
            or not isinstance(interpretation.get("units"), list)):
        return None
    return [unit["source"]["text"] for unit in interpretation["units"] if unit.get("kind") == "restriction"]


def understood(calls, context, searcher, report, held_acts=None):
    """The steps every answer shares: the message's interpretation and the matter's
    understanding, side by side; the research; and the time limits, worked out beside the
    search where research is needed. Returns the interpretation, the research record and
    the calculation record."""
    interpreted, plan = _interpreted(calls, context, report)
    # Time limits are worked out beside the search, only where research is needed.
    with replay_scope.Pool(max_workers=1) as pool:
        working = (pool.submit(calculation.work_out, calls, context, held_acts)
                   if held_acts is not None and _needs_research(plan) else None)
        record = research.retrieve(plan, searcher, context, model=calls, progress=report)
        limits = working.result() if working is not None else calculation.skipped()
    return interpreted, record, limits


def _interpreted(calls, context, report, early=None, interpreted=None):
    """The message's interpretation and the matter's understanding, side by side, and the
    research plan; returns the interpretation and the plan. interpreted (plan AN.48, D175): the message's interpretation where it
    was made already, beside NM's follow-up reader - the matter is then understood from the whole conversation with it, as
    beside it, and the message is not read twice."""
    if interpreted is not None:
        if not research.carries_matter(interpreted):
            return interpreted, research.plan(calls, context, interpreted)  # the plan for no matter, without a call
        return interpreted, calls.checked("core_research_plan", lambda: research.plan(
            calls, context, progress=report, restrictions=lambda: _restrictions(interpreted), early=early))
    # The matter's first understanding reads the conversation itself, so it is written
    # beside the message's interpretation (owner, 18 Oct 2026, for speed); its next step
    # waits for the interpretation, which says whether there is a matter to research at all.
    decided, verdict = threading.Event(), {"carries": True}

    def wanted():
        decided.wait()
        return verdict["carries"]

    def restricted():
        decided.wait()
        return verdict.get("restrictions")

    with replay_scope.Pool(max_workers=1) as beside:
        planning = beside.submit(calls.checked, "core_research_plan",
                                 lambda: research.plan(calls, context, progress=report, wanted=wanted,
                                                       restrictions=restricted, early=early))
        try:
            interpreted = calls.checked("core_understanding", lambda: understanding.understand(calls, context))
            verdict["carries"] = research.carries_matter(interpreted)
            verdict["restrictions"] = _restrictions(interpreted)
        except BaseException:
            verdict["carries"] = False
            raise
        finally:
            decided.set()
        try:
            plan = planning.result()
        except Exception:
            if verdict["carries"]:
                raise
    if not verdict["carries"]:
        plan = research.plan(calls, context, interpreted)  # the plan for no matter, without a call
    return interpreted, plan


def _papers(context):
    """How many papers the conversation has sent, by their names in each turn."""
    pages = context.get("documents") if isinstance(context, dict) else None
    return len({(page.get("turn_id"), (page.get("document") or {}).get("name")) for page in pages or ()})


class _Later:
    """What the writing reads of a window still open while it writes (plan AN.37, D44): the context with the answers as they
    stand, and, after its sections, what changed since they began and which disputes that touches (None: the whole answer).
    The writing waits only on the questions the model asked: those code asks (D87) are waited on by the research that asks them."""

    def __init__(self, asking, base, gate=None):
        self.asking, self.base, self.gate = asking, base, gate

    def _waited_on(self):
        return [question for question in self.asking.questions if question.get("asked_by", "model") != "code"]

    def context(self):
        return {**self.base, "answers": questions.context_answers(self.asking.questions,
                                                                  list(self.asking.answers().values()))}

    def version(self):
        return self.asking.version

    def touches(self, dispute_id):
        """Whether a question names the dispute, or names none and so touches the whole answer (D50)."""
        return any(not question["depends"] or dispute_id in question["depends"] for question in self._waited_on())

    def wait(self):
        """Until the answers, or after WAIT the defaults, stand (D39). Plan AN.48 (48d; D142, D154): step by step, a section whose
        dispute a question names is not written on a default - while an answer is still to come, the step ends here, and resumes
        once every question is answered."""
        if self.gate is not None and self.gate.asks():
            given = self.asking.answers()
            if any(given.get(question["id"], {}).get("how") not in ("answered", "late") for question in self._waited_on()):
                raise stepwise.Waiting(stepwise.ASKED)
            return
        self.asking.wait_for([question["id"] for question in self._waited_on()])

    def since(self, version):
        changed = self.asking.changed_since(version)
        if not changed:
            return None, None
        depends = [question["depends"] for question in self.asking.questions if question["id"] in changed]
        return self.context(), None if any(not names for names in depends) else {name for names in depends for name in names}


#: What an answer starting afresh keeps of earlier work: nothing.
_NOTHING_KEPT = {"understood": None, "limits": None, "parts": {}, "cases": {}, "answered": None}
_UNREADABLE = (ValueError, KeyError, TypeError, IndexError, SchemaViolation)


def _kept(steps, context, report, *, plan=None, steered=False):
    """What an answer continuing where it stopped keeps of the steps it saved (plan AN.41, D70): each checked as a saved answer is
    checked - the plan against the conversation, each dispute's research against the plan, the time limits, each case against its
    dispute's research, and what the answer had shown as it would be saved - and kept where it passes. What does not pass, or rests
    on what did not, is done again. plan (plan AN.42, D79): the plan made again after a steer, which the research must still
    answer; the time limits and the cases are then made again, and what the answer had shown is only the words each section is
    reviewed again from."""
    kept = deepcopy(_NOTHING_KEPT)
    understood = (steps or {}).get("understood")
    if understood is None:
        return kept
    report("continuing")
    if plan is None:
        plan = understood["plan"]
        try:
            if research.accept(plan["proposal"], context) != plan:
                raise ValueError("The saved research plan differs from its original sources")
        except _UNREADABLE as exc:
            log.warning("A saved understanding was not kept and is made again: %s", type(exc).__name__)
            return kept
        kept["understood"] = (understood["interpretation"], plan)
    for dispute_id, part in steps["parts"].items():
        try:
            research.validate(part, plan, context)
        except _UNREADABLE as exc:
            log.warning("A dispute's saved research was not kept and is made again: %s", type(exc).__name__)
            continue
        kept["parts"][dispute_id] = part
    if steered:
        kept["answered"] = steps["answered"]
        return kept
    if steps["limits"] is not None:
        try:
            calculation.validate(steps["limits"], context)
            kept["limits"] = steps["limits"]
        except _UNREADABLE as exc:
            log.warning("The saved time limits were not kept and are worked out again: %s", type(exc).__name__)
    layout = response_writer.parts({"contract": research.CONTRACT, "plan": plan})
    disputes = {dispute["id"]: dispute for dispute in ((plan.get("proposal") or {}).get("understanding") or {}).get("disputes", ())}
    for key, case in steps["cases"].items():
        index = int(key)
        dispute_id = layout[index]["dispute_id"] if index < len(layout) else None
        part = kept["parts"].get(dispute_id)
        if part is None or dispute_id not in disputes:
            continue
        try:
            case_strength.validate(case, context, part, answer_sources.build(context, part), disputes[dispute_id])
            kept["cases"][key] = case
        except _UNREADABLE as exc:
            log.warning("A dispute's saved case was not kept and is set out again: %s", type(exc).__name__)
    answered = steps["answered"]
    # A section answering one of several disputes is written from that dispute's research; any other, from all of it.
    complete = set(research.dispute_work(plan)) <= set(kept["parts"])

    def researched(saved):
        return saved["dispute_id"] in kept["parts"] if len(layout) > 1 else complete
    if answered is not None and not all(researched(saved) for saved in answered["sections"]):
        # A section written from research no longer kept is written again, and so are the check across the sections and the
        # overview, which read every section, and the corrections that check asked for.
        answered = {"sections": [{**saved, "edit": None} for saved in answered["sections"] if researched(saved)],
                    "cross_check": None, "overview": None}
    if answered is not None and kept["limits"] is not None:
        held = {"steps": {**steps, "parts": kept["parts"], "limits": kept["limits"], "answered": answered}}
        try:
            activity = interrupted(activity_of(held, context))
            with replay_scope.replaying():
                record = research.validate(activity["research"], activity["research"]["plan"], context)
                elements = response_rendering.render_sections(
                    context, record, answer_sources.build(context, record), sections=activity["sections"],
                    cross_check=activity["cross_check"], overview=activity["overview"],
                    time_limits=calculation.validate(activity["calculation"], context), contract=activity["rendering_contract"])
                validate_activity(activity, context, elements)
            kept["answered"] = answered
        except _UNREADABLE as exc:
            log.warning("What a stopped answer had shown was not kept and is written again: %s", type(exc).__name__)
    return kept


def steps_from(held):
    """The steps of a turn saved in the earlier form - what it had shown and the activity it came from (P27) - so that Continue
    keeps them too (plan AN.41, D70): its understanding and plan, each dispute's research it had finished, its time limits and what
    its answer had shown. Each is checked at Continue as any saved step is. None where that activity cannot be read so."""
    try:
        activity = held["activity"]
        record, plan = activity["research"], activity["research"]["plan"]
        parts = {}
        for dispute_id in research.dispute_work(plan):
            if (record.get("picks") or {}).get(dispute_id, {}).get("reason") == research.UNFINISHED:
                continue  # recorded as not yet researched when it stopped
            parts[dispute_id] = research.part_of(record, dispute_id)
        return {"understood": {"interpretation": activity["interpretation"], "plan": plan}, "limits": activity["calculation"],
                "parts": parts, "cases": {}, "answered": {key: activity[key] for key in ("sections", "cross_check", "overview")}}
    except _UNREADABLE as exc:
        log.warning("What an earlier stopped answer had shown could not be read for Continue: %s", type(exc).__name__)
        return None


def activity_of(held, context):
    """The activity of a turn being worked on, derived from its saved steps (plan AN.41, D67) exactly as the turn shows it: its
    understanding, each dispute's research done so far (the rest recorded as not finished), the time limits (or that they were
    not worked out) and what the answer had shown. None where the matter was not yet understood. A record of the earlier form
    keeps the activity it was saved with."""
    if "steps" not in held:
        return held["activity"]
    steps = held["steps"]
    if steps["understood"] is None:
        return None
    plan = steps["understood"]["plan"]
    record = research.assemble(plan, list(steps["parts"].values()), unfinished=research.UNFINISHED)
    sources = answer_sources.build(context, record)
    answered = steps["answered"] or {"sections": [], "cross_check": None, "overview": None}
    return {"contract": CONTRACT, "interpretation": steps["understood"]["interpretation"], "research": record,
            "sources": sources, "execution": execution_record(record),
            "calculation": steps["limits"] if steps["limits"] is not None else calculation.unavailable(LIMITS_UNFINISHED),
            "rendering_contract": response_rendering.CASED_CONTRACT, **deepcopy(answered)}


class _Keeper:
    """The record of the turn being worked on, kept beside its conversation (plan AN.41, D66-D67): written at once when Send is
    pressed and whenever the answer shows more (P26-P27), and as each other step finishes by one writer of its own, which takes
    every change made while it waited, so that a run of quick steps costs one write and the turn's own work never waits for it.
    Every write is of the record as it then stands, on the version the last write left (one at a time); a write never puts back
    an older record than one already written."""

    #: The least time between two writes the writer makes by itself, in seconds: a long conversation takes seconds to write.
    GAP = 5.0

    def __init__(self, store, holder, beside, held, report):
        self.store, self.holder, self.beside, self.held, self.report = store, holder, beside, held, report
        self._cond, self._dirty, self._closed, self._thread = threading.Condition(), 0, False, None
        self._made, self._written, self.saved = 0, 0, 0

    def _snapshot(self):
        """The record as it stands, under the condition: a copy of its own structure, sharing the step results, which nothing
        changes once made."""
        held = dict(self.held)
        held["steps"] = {**held["steps"], "parts": dict(held["steps"]["parts"]), "cases": dict(held["steps"]["cases"])}
        held["steers"], held["elements"] = list(held["steers"]), list(held["elements"])
        self._made += 1
        return self._made, held

    def _write(self, number, held):
        """Write one record; False where it could not be written (the turn goes on; a later write or its commit decides)."""
        with self.beside:
            if number <= self._written:
                return True
            try:
                self.holder["context"] = hold_shown(self.store, self.holder["context"], held, private=True)
            except (OSError, StaleWrite, ConversationRefused, ValueError):
                log.warning("The turn's work so far could not be saved beside the conversation", exc_info=True)
                return False
            self._written = number
        return True

    def write(self):
        """Write the record as it stands now, in the caller's thread. Raises where it cannot be written."""
        with self._cond:
            number, held = self._snapshot()
            self._dirty = 0
        with self.beside:
            self.holder["context"] = hold_shown(self.store, self.holder["context"], held, private=True)
            self._written = max(self._written, number)

    def now(self, change):
        """Change the record and write it at once (what the answer shows, P26). True where it was written."""
        with self._cond:
            change(self.held)
            number, held = self._snapshot()
            self._dirty = 0
        return self._write(number, held)

    def later(self, change):
        """Change the record; the writer writes it soon, with whatever else changes meanwhile."""
        with self._cond:
            if self._closed:
                return
            change(self.held)
            self._dirty += 1
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="turn-keeper", daemon=True)
                self._thread.start()
            self._cond.notify_all()

    def _run(self):
        while True:
            with self._cond:
                while not self._dirty and not self._closed:
                    self._cond.wait()
                if self._closed:
                    return
                number, held = self._snapshot()
                self._dirty = 0
            if self._write(number, held):
                self.saved += 1
                self.report("saved", saved=self.saved, chat_id=self.holder["context"].chat_id)
            with self._cond:
                if not self._closed:
                    self._cond.wait(self.GAP)

    def close(self):
        """No further write by the writer; one under way is finished first."""
        with self._cond:
            self._closed = True
            self._cond.notify_all()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join()

    def stop(self, code, *, answered=None, waiting=None, timed=None, rechecked=False):
        """The turn stopped part-way (D69): why, saved with everything it finished, at once. answered: the whole answer, where it
        was finished but not saved. waiting (plan AN.48, 48a2): the step after which a matter worked step by step waits for the
        advocate's go-ahead. Raises nothing; False where it could not be written."""
        self.close()

        def stopped(held):
            held["stopped"] = {"code": code, "at": datetime.now(timezone.utc).isoformat()}
            if answered is not None:
                held["elements"], held["steps"] = answered[0], {**held["steps"], "answered": answered[1]}
            if waiting is not None:
                # Plan AN.48 (48e, D140): the step's tentative time kept beside the time it took.
                go = stepwise.timed(held["go"], *timed) if timed is not None else held["go"]
                held["go"] = stepwise.waited(stepwise.rechecked(go) if rechecked else go, waiting)
        return self.now(stopped)

    # The steps, as each finishes (D67).
    def understood(self, interpretation, plan):
        self.later(lambda held: held.update(steps={**held["steps"], "understood": {"interpretation": interpretation,
                                                                                    "plan": plan}}))

    def limits(self, record):
        self.later(lambda held: held.update(steps={**held["steps"], "limits": record}))

    def part(self, dispute_id, part):
        self.later(lambda held: held.update(steps={**held["steps"], "parts": {**held["steps"]["parts"], dispute_id: part}}))

    def parts_kept(self, parts):
        """After a steer (D79): only the research still answering the new plan is kept."""
        self.later(lambda held: held.update(steps={**held["steps"], "parts": dict(parts)}))

    def case(self, index, case):
        self.later(lambda held: held.update(steps={**held["steps"], "cases": {**held["steps"]["cases"], str(index): case}}))

    def taken(self, route, said):
        """Plan AN.48 (D175): how a follow-up's turn started - from NM's earlier understanding of the matter, or with the whole
        matter read again - in code's words, kept on the go-ahead record for its stops to say."""
        self.later(lambda held: held.update(go=stepwise.taking(held["go"], route, said)) if held.get("go") else None)

    def grown(self, steps, disputes):
        """Plan AN.48 (48i): the plan grown by questions added for what is new, the research kept moved onto it, the grown
        disputes' research, cases and analyses dropped to be made again, and their questions taken off the go-ahead's proposals."""
        def grow(held):
            held["steps"] = {**held["steps"], **{key: steps[key] for key in ("understood", "parts", "cases", "answered")}}
            held["go"] = stepwise.unproposed(held["go"], disputes)
        self.later(grow)


def prepare(model, context, searcher, *, case_index=None, provision_reader=None, progress=None,
            held_acts=None, shown=None, ask=None, keep=None, resume=None, steered=False, on_understood=None, settle=None,
            gate=None, follow=None):
    """Prepare and admit one response, dispute by dispute (turn v7, owner decisions P25-P27, P29).
    No persistence or external action occurs here. shown (P26): told, each time the answer
    shows more, its elements so far and the answering's state they come from (its sections done,
    the check across them and the overview). ask (plan AN.37): given the interpretation, the plan
    and the context, asks the advocate what only they can settle and returns its questions.Asking once
    the answers or the defaults stand, or None where nothing is asked. settle (plan AN.37, D87): asks the advocate the
    questions code puts while the research runs - which Act or judgment a name means - and gives their answers.

    The whole preparation is one turn's scope (plan AN.41, step 1): what is derived from its
    research is derived once, by every section, check and drawing of what is shown.

    keep (plan AN.41, D67): told each step's result as the step finishes - understood(interpretation, plan), limits(record),
    part(dispute_id, part), case(index, case) - so that it is saved then. resume (D70): the steps an answer that stopped had
    saved (conversation.STEPS); each is checked as a saved answer is checked and kept where it passes, and only what is missing
    is done. steered (plan AN.42, D79): the conversation carries what the advocate steered the answer with since those steps were
    saved - the understanding is made again from it, each dispute's research kept where the new plan asks exactly what it
    answered, and each section shown reviewed again against it from its own words. on_understood (plan AN.43): told the context and the
    plan as soon as the matter is understood (or was, before it stopped), for what is made from them beside the answer.
    gate (plan AN.48, 48a1): where a matter worked step by step stops for the advocate's go-ahead (steps.Gate) - after the
    understanding, after the research (every dispute's research waited for and saved first) and before the check across the
    analyses - raising steps.Waiting. None: end to end, as before. follow (plan AN.48, D175): the last saved answer's understanding
    of the matter (follow_up.earlier), where the message is a follow-up worked step by step - the turn then starts from it unless
    the message changes the matter (follow_up.continued); None: understood from the whole conversation, as before."""
    with replay_scope.turn():
        return _prepare(model, context, searcher, case_index=case_index, provision_reader=provision_reader,
                        progress=progress, held_acts=held_acts, shown=shown, ask=ask, keep=keep, resume=resume,
                        steered=steered, on_understood=on_understood, settle=settle, gate=gate, follow=follow)


def _all_researched(parts, kept, keep):
    """Plan AN.48 (48a1): the research step ends only when every dispute's research has finished, each saved as it finished; a
    dispute whose research failed fails the step as today, after what did finish is saved."""
    failed = None
    for dispute_id, future in parts.items():
        if dispute_id in kept["parts"]:
            continue
        try:
            part = future.result()
        except Exception as exc:  # noqa: BLE001 -- the first failure is raised to its owner below, once the rest is saved
            failed = failed or exc
            continue
        if keep is not None:
            keep.part(dispute_id, part)  # saved now, whether or not the dispute's own callback has run yet
    if failed is not None:
        raise failed


def _grown(calls, context, resume, adding, report, keep):
    """Plan AN.48 (48i; D156): the questions a later message raised, researched now. Each joins the plan after its own questions
    (research v19), so that every other question keeps its identity; every other dispute's research is moved onto the grown plan, to
    be checked as saved research is checked; the grown disputes' research, cases and analyses are dropped, to be made again - their
    earlier searches given back to the search, so that only the new questions are searched. Returns the steps to resume from and
    those searches, or what it was given where nothing could be added."""
    understood = resume["understood"]
    plan = understood["plan"]
    proposal = research.with_questions(calls, plan, adding, report)
    if proposal is plan["proposal"]:
        return resume, {}
    grown = research.accept(proposal, context)
    layout = response_writer.parts({"contract": research.CONTRACT, "plan": grown})
    whole = len(layout) <= 1
    disputes = {entry["dispute_id"] for entry in adding}
    started = {}
    for dispute_id in disputes:
        if dispute_id in resume["parts"]:
            started.update(research.searched_before(grown, resume["parts"][dispute_id]))
    parts = {dispute_id: research.rebased(part, grown) for dispute_id, part in resume["parts"].items() if dispute_id not in disputes}
    cases = {key: case for key, case in (resume.get("cases") or {}).items()
             if not whole and int(key) < len(layout) and layout[int(key)]["dispute_id"] not in disputes}
    answered = resume.get("answered")
    if answered is not None:
        kept_sections = [saved for saved in answered["sections"] if not whole and saved.get("dispute_id") not in disputes]
        if len(kept_sections) != len(answered["sections"]):
            answered = {"sections": kept_sections, "cross_check": None, "overview": None}
    steps = {**resume, "understood": {**understood, "plan": grown}, "parts": parts, "cases": cases, "answered": answered}
    if keep is not None:
        keep.grown(steps, disputes)
    return steps, started


def _prepare(model, context, searcher, *, case_index, provision_reader, progress, held_acts, shown, ask, keep, resume,
             steered, on_understood, settle=None, gate=None, follow=None):
    report = _reporter(progress)
    calls = model if isinstance(model, TurnCalls) else TurnCalls(model)
    gate = gate if gate is not None else stepwise.Gate(None)
    # Plan AN.48 (48i; D156): the questions proposed for what is new, added to the plan in a run that researches their disputes.
    started = {}
    adding = gate.adding() if resume and not steered and resume.get("understood") else []
    if adding:
        resume, started = _grown(calls, context, resume, adding, report, keep)
    kept = _kept(resume, context, report) if resume and not steered else _NOTHING_KEPT
    # Plan AN.48 (48h; D161-D162): the analyses written before the advocate's later messages are reviewed again from their own words
    # against everything said, and written again only where the review finds them wanting - in the next run that writes or
    # finishes; until then they stay as they were checked.
    rechecking = bool(gate.recheck and not steered and resume and ((resume.get("answered") or {}).get("sections"))
                      and (gate.allows("write") or gate.allows("finish")))
    if rechecking:
        kept["answered"] = resume["answered"]
        gate.rechecked = True
    report("understanding")
    # Plan AN.37 (D41, D45): what the turn is expected to cost - roughly now, from the papers sent, and again once its plan is
    # known - kept beside what it spends, for diagnostics only.
    priced = calls.model_for(Tier.HARD)
    if priced is not None:
        calls.expect("start", estimates.turn_start_usd(priced, _papers(context), calls.effort))
    # Plan AN.33 (D28; piece 33q): the held law is searched as soon as the understanding and its search phrases are final, beside
    # the papers' side-by-side reading and the weighing; each search begun so is used once, as it would have been made.
    if kept["understood"] is not None:
        interpreted, plan = kept["understood"]
    else:
        # Plan AN.48 (D175): a follow-up starts from NM's last understanding of the matter unless the message changes the matter.
        taken = follow_up.continued(calls, context, follow, report) if follow is not None and not steered else None
        if taken is not None and taken["route"] == follow_up.KEPT:
            interpreted, plan = taken["interpretation"], taken["plan"]
            # Each dispute the follow-up adds nothing to keeps its research, checked as saved research is checked.
            kept = {**kept, "parts": dict(taken["parts"])}
            if keep is not None:
                keep.understood(interpreted, plan)
                keep.parts_kept(kept["parts"])
        else:
            # Plan AN.48 (D141): a step that may not research begins no search either.
            interpreted, plan = _interpreted(calls, context, report,
                                             early=(lambda work: started.update(research.start_search(searcher, work)))
                                             if gate.allows("research") else None,
                                             interpreted=(taken or {}).get("interpretation"))
            if keep is not None:
                keep.understood(interpreted, plan)
        if taken is not None and taken.get("said") and keep is not None:
            keep.taken(taken["route"], taken["said"])
        if steered and resume:
            # D79: what was finished before the steer is kept only where it still answers what the new plan asks.
            kept = _kept(resume, context, report, plan=plan, steered=True)
            if keep is not None:
                keep.parts_kept(kept["parts"])
    if on_understood is not None:
        on_understood(context, plan)
    # Plan AN.38 (D48): papers that record one act or matter differently move the working out of the time limits under Auto.
    if any(item.get("kind") == "papers_differ" for item in (plan.get("proposal") or {}).get("connections") or ()):
        calls.found("papers_differ")
    if priced is not None:
        disputes = len(response_writer.parts({"contract": research.CONTRACT, "plan": plan}))
        calls.expect("planned", estimates.turn_planned_usd(priced, calls.estimate()["spent_usd"], max(1, disputes - 1),
                                                           calls.effort))
    # Plan AN.48 (D134, 48a1): understood - a matter worked step by step stops here for the advocate's go-ahead to research.
    gate.after("understand")
    # Step 4 (owner, 21 Oct 2026; P26 as first decided): each dispute is researched as its own
    # part, and its section is written as soon as that part is ready; the time limits are
    # worked out beside the search, only where research is needed.
    with replay_scope.Pool(max_workers=1) as pool:
        working = (pool.submit(calculation.work_out, calls, context, held_acts)
                   if held_acts is not None and _needs_research(plan) and kept["limits"] is None else None)
        # Plan AN.48 (48b): only the disputes the advocate named are researched now; None - every dispute, as before.
        parts = research.retrieve_parts(plan, searcher, context, model=calls, progress=report, started=started,
                                        case_index=case_index, done=kept["parts"], settle=settle,
                                        only=gate.research_only(kept["parts"]))
        if keep is not None:
            # D67: each dispute's research saved as it finishes.
            for dispute_id, future in parts.items():
                if dispute_id not in kept["parts"]:
                    future.add_done_callback(lambda done, dispute_id=dispute_id: (
                        keep.part(dispute_id, done.result()) if not done.cancelled() and done.exception() is None else None))
        # Plan AN.37 (D39, D50): what only the advocate can settle is asked once the plan is known. The research and the time
        # limits go on meanwhile, and the writing of each dispute no question names; the writing of those it names waits for the
        # answers or, after WAIT, the defaults (answer_sections.answer).
        asking = ask(interpreted, plan, context) if ask is not None else None
        limits = (kept["limits"] if kept["limits"] is not None else
                  working.result() if working is not None else calculation.skipped())
    if keep is not None and kept["limits"] is None:
        keep.limits(limits)
    if not gate.allows("write"):
        # Plan AN.48 (48a1): researched - every dispute's research waited for and saved, then the turn stops for the go-ahead.
        _all_researched(parts, kept, keep)
        gate.after("research")
    later = _Later(asking, context, gate=gate) if asking is not None else None
    if later is not None:
        context = later.context()
    researched = answer_sections.Researched(context, plan, parts)

    def base(record, sources, execution):
        return {"contract": CONTRACT, "interpretation": interpreted, "research": record, "sources": sources,
                "execution": execution, "calculation": limits,
                "rendering_contract": response_rendering.CASED_CONTRACT}

    def released(state):
        if shown is None:
            return
        # What would be saved should the turn stop here (P27): the disputes not yet researched
        # are recorded so.
        record, sources, execution = researched.provisional()
        elements = response_rendering.render_sections(
            context, record, sources, sections=state["sections"], cross_check=state["cross_check"],
            overview=state["overview"], time_limits=limits, waiting=state["waiting"],
            contract=response_rendering.CASED_CONTRACT)
        # D79: a section shown only until its review against a steer replaces it is shown, never kept as finished.
        before = set(state.get("before") or ())
        shown(elements, {"sections": [saved for saved in state["sections"] if saved["part"] not in before],
                         "cross_check": state["cross_check"], "overview": state["overview"]}, calls.metrics())
    # Plan AN.48 (48b): only the analyses of the disputes named are written now, with those written before; None - every one.
    written_before = {saved["dispute_id"] for saved in (kept["answered"] or {}).get("sections") or ()
                      if (saved["fallback"] or {}).get("reason") != "interrupted"}
    write_only = gate.write_only(set(parts), written_before)
    # Turn v9 (AN.28): each section written for the advocate and placed, its failing pieces given a second
    # look and then blocked one by one (writer v14), reviewed by review v12, and laid out as rendering v19.
    sections, crossed, overview = answer_sections.answer(
        calls, context, None, None, interpretation=interpreted, execution=None, worked=limits,
        case_index=case_index, provision_reader=provision_reader, report=report, released=released,
        researched=researched, contract=response_writer.CASED_CONTRACT, later=later, done=kept["answered"],
        cases=kept["cases"], case_done=keep.case if keep is not None else None,
        steered=(steered and bool(kept["answered"])) or rechecking, only=write_only)
    # Plan AN.48 (48a1): written - an answer with several analyses stopped before the check across them (steps.Gate.call); one
    # with a single analysis stops here, before it is saved. An answer of several saves each analysis as it passes
    # (answer_sections.answer's released); one of a single part is released only whole, at its end - so where the turn stops
    # here, that part is saved first, as the others are, and the stop shows it and offers Done (found by the pilot's browser test,
    # D171, 10 Nov 2026: the stop said "written", kept nothing of it and offered to write it again).
    if not gate.allows("finish") and [saved["part"] for saved in sections] == [0]:
        released({"sections": sections, "waiting": [], "cross_check": crossed, "overview": overview})
    gate.after("write")
    if later is not None:
        context = later.context()
    # Plan AN.48 (48b): finished with the analyses of some disputes, the others stand as not finished (answer_sections.answer),
    # and code's words above the answer say so (process).
    record, sources, execution = researched.whole()
    elements = response_rendering.render_sections(context, record, sources, sections=sections, cross_check=crossed,
                                                  overview=overview, time_limits=limits,
                                                  contract=response_rendering.CASED_CONTRACT)
    activity = {**base(record, sources, execution), "sections": sections, "cross_check": crossed, "overview": overview}
    kept = calls.estimate()
    if kept["passed"]:
        # D45: recorded for diagnostics; the answer is saved as it would be.
        log.warning("A turn spent %.4f, more than %s times its estimate (%s)", kept["spent_usd"], estimates.OVER_TURN,
                    ", ".join(kept["passed"]))
    return elements, activity, calls.metrics()


def interrupted(held):
    """A turn that stopped after showing part of its answer, as it is saved (P27): its
    activity with the parts not finished marked so, and the answer rendered from it."""
    activity = {key: deepcopy(value) for key, value in held.items() if key != "waiting"}
    activity["sections"], activity["cross_check"], activity["overview"] = answer_sections.interrupted(
        {"sections": held["sections"], "cross_check": held["cross_check"], "overview": held["overview"]},
        held["research"], kept=held["contract"] in _KEEPS, looked=held["contract"] in _LOOKS)
    return activity


def recover(store, matter, advocate_id, *, running=lambda turn_id: False, session_current):
    """Save a turn that stopped after showing part of its answer with what it showed (owner
    decision P27, 19 Oct 2026: each section is saved when it is shown), unless that turn is
    still running. What cannot be read reliably is withdrawn, never saved as shown. Returns
    the conversation as it now stands."""
    try:
        held = shown_of(matter)
    except ValueError:
        held = {"turn_id": None}
    if held is None or held["turn_id"] is not None and running(held["turn_id"]):
        return matter
    save_shown(store, matter, advocate_id, held, session_current=session_current)
    return store.load(matter.id)


def save_shown(store, matter, advocate_id, held, *, session_current, service_status=None, metrics=None):
    """Save what a turn showed of its answer before it stopped (held, as conversation.shown_of reads it), as a turn that stopped
    part-way (P27): its activity with the parts not finished marked so, checked as it is saved (P46). Returns the saved
    response, or None where what was shown could not be read reliably and was withdrawn. service_status: code's own words on
    why the turn stopped, kept with it and shown above the answer (plan AN.37, D46); metrics: the turn's own, where the run
    that made it saves it, otherwise those kept with what was shown."""
    rows = checked_rows(matter, advocate_id)
    try:
        # The model and the effort chosen for the turn are part of its request (plan AN.33, D23): without them a turn run on
        # a choice was never recognised as the request that showed its parts, and what it showed was withdrawn.
        choice = tuple((name, held["request"][name]) for name in ("model", "effort") if name in held["request"])
        # Plan AN.37: what the turn asked, and the answers as they stood, are saved with what it showed.
        asking = asking_of(matter, held["turn_id"])
        context = TurnContext(matter, held["request"]["chat_id"], held["turn_id"], held["message"], tuple(rows),
                              documents=tuple(held["documents"]), choice=choice,
                              asked=asking["state"] if asking is not None else None,
                              steers=tuple(held.get("steers", ())), added=tuple(held.get("added", ())))
        if context.request != held["request"] or any(row["turn_id"] == held["turn_id"] for row in rows):
            raise ValueError("What was shown belongs to another request")
    except (ValueError, KeyError, TypeError, SchemaViolation) as exc:
        log.warning("The unfinished parts of an answer could not be read reliably and were withdrawn: %s",
                    type(exc).__name__)
        drop_shown(store, TurnContext(matter, rows[0]["chat_id"] if rows else "", "", "", tuple(rows)))
        return None
    original = context.payload()
    if service_status is None and "steps" in held:
        service_status = stopped_said(held)
    try:
        derived = activity_of(held, original)
        if derived is None:
            raise LookupError("nothing finished")
        activity = interrupted(derived)
        # Saving what an unfinished turn showed is when it is checked (P46): what its checks
        # share is derived once (P35).
        with replay_scope.replaying():
            record = research.validate(activity["research"], activity["research"]["plan"], original)
            sources = answer_sources.build(original, record)
            elements = response_rendering.render_sections(
                original, record, sources, sections=activity["sections"], cross_check=activity["cross_check"],
                overview=activity["overview"], time_limits=calculation.validate(activity["calculation"], original),
                contract=activity["rendering_contract"])
            validate_activity(activity, original, elements)
        records = checklist.records(original, activity)
    except (ValueError, TypeError, SchemaViolation, LookupError) as exc:
        if "steps" not in held:
            log.warning("The unfinished parts of an answer could not be read reliably and were withdrawn: %s",
                        type(exc).__name__)
            drop_shown(store, TurnContext(matter, rows[0]["chat_id"] if rows else "", "", "", tuple(rows)))
            return None
        # Plan AN.41 (D66): the advocate's message and files are never lost. What could not be read reliably is not shown; the
        # message is saved with code's words on why it stopped, and nothing of an answer.
        if not isinstance(exc, LookupError):
            log.warning("What a stopped answer finished could not be read reliably; its message is saved alone: %s",
                        type(exc).__name__)
            service_status = (STOPS.get((held.get("stopped") or {}).get("code") or "interrupted", STOPS["failed"])
                              + " What NM had finished could not be read reliably, so none of it is shown; your message and "
                              "files are saved.")
        activity, elements, records = {"contract": UNANSWERED_CONTRACT}, [], None
    return commit_turn(store, context, elements=elements, activities=activity, records=records,
                       metrics=held["metrics"] if metrics is None else metrics, service_status=service_status,
                       session_current=session_current)


def discard(store, matter, advocate_id, turn_id, *, running=lambda turn_id: False, session_current):
    """Discard (plan AN.41, D71): the red message and its buttons go, and the answer that stopped is saved as it stopped - the
    parts it finished below code's words on why it stopped - never reworked after (P46). Returns the saved response, or None where
    that turn is not stopped here (it finished, is still being worked on, or is another turn)."""
    try:
        held = shown_of(matter)
    except ValueError:
        return None
    if held is None or held["turn_id"] != turn_id or running(turn_id):
        return None
    return save_shown(store, matter, advocate_id, held, session_current=session_current)


#: Said above a matter worked step by step that the advocate finished with the analyses of some of its disputes (plan AN.48, 48b).
PARTLY_SAID = (STOPS["done"] + " NM wrote the analyses you asked for - {written} of {of} disputes; the others are marked below as "
               "not finished, and NM can take them up if you ask.")
#: Said above a matter worked step by step that the advocate finished before any analysis was written (plan AN.48, 48a3).
DONE_SAID = (STOPS["done"] + " What NM did before you finished is below; what it was not asked to do is marked as not "
             "finished.")


def done(store, matter, advocate_id, turn_id, *, running=lambda turn_id: False, session_current):
    """Done (plan AN.48, 48a3; D147) before any analysis is written: the matter waiting for the advocate is saved as it stands,
    as Discard saves (D71), with code's words that the advocate finished it here; no step runs. Returns the saved response, or None
    where that turn does not wait for the advocate here."""
    try:
        held = shown_of(matter)
    except ValueError:
        return None
    if held is None or held["turn_id"] != turn_id or running(turn_id) or stepwise.waiting_of(held) is None:
        return None
    return save_shown(store, matter, advocate_id, held, session_current=session_current, service_status=DONE_SAID)


def _validate_sections(activity, context, elements):
    """The check of a v6 or v7 turn as it is saved: its understanding, research and time limits,
    every section, trim, correction, cross-check and overview bound to their evidence
    (answer_sections), and the answer rendered from them exactly as it is to be shown."""
    if not known_activity(activity):
        raise ValueError("Unknown saved turn or rendering contract")
    limits = calculation.validate(activity["calculation"], context)
    record = research.validate(activity["research"], activity["research"]["plan"], context)
    sources = answer_sources.build(context, record)
    if sources != activity["sources"] or execution_record(record) != activity["execution"]:
        raise ValueError("Saved sources or operation evidence changed")
    answer_sections.validate(activity, context, record, sources, limits, kept=activity["contract"] in _KEEPS,
                             looked=activity["contract"] in _LOOKS)
    rebuilt = response_rendering.render_sections(context, record, sources, sections=activity["sections"],
                                                 cross_check=activity["cross_check"], overview=activity["overview"],
                                                 time_limits=limits, contract=activity["rendering_contract"])
    if rebuilt != elements:
        raise ValueError("Saved response differs from its admitted rendering")
    return deepcopy(activity)


def known_activity(activity):
    """Whether a saved turn's activity is of a turn version this code reads, with the fields and
    the rendering version that turn version was saved with: a check of the record's form, which
    rebuilds nothing. A record a later version wrote is never shown or upgraded by this code."""
    version = activity.get("contract") if isinstance(activity, dict) else None
    rendering = activity.get("rendering_contract") if isinstance(activity, dict) else None
    if version == UNANSWERED_CONTRACT:
        return set(activity) == {"contract"}
    if version in SECTIONED:
        return set(activity) == _SECTIONED_FIELDS and rendering == _RENDERINGS[version]
    expected_fields =(_ACTIVITY_FIELDS if version == LEGACY_CONTRACT else
                       _ACTIVITY_FIELDS | {"authority_evidence"} if version == AUTHORITY_CONTRACT else
                       _ACTIVITY_FIELDS | {"authority_evidence", "calculation"} if version == CALCULATION_CONTRACT
                       else _ACTIVITY_FIELDS | {"authority_evidence", "calculation", "release"})
    # A saved response re-renders under the version it was admitted with: names a
    # later rendering shows differently never rewrite an earlier turn.
    renderings = ({response_rendering.LEGACY_CONTRACT} if version == LEGACY_CONTRACT else
                  {response_rendering.STORED_TITLE_CONTRACT, response_rendering.SHOWN_NAME_CONTRACT,
                   response_rendering.CITED_WORDS_CONTRACT, response_rendering.HEADINGS_CONTRACT,
                   response_rendering.SHORT_NAME_CONTRACT, response_rendering.DOCUMENT_PAGES_CONTRACT}
                  if version == AUTHORITY_CONTRACT else
                  {response_rendering.WORKING_CONTRACT, response_rendering.AS_OF_CONTRACT}
                  if version == CALCULATION_CONTRACT else
                  {response_rendering.HELD_CONTRACT, response_rendering.WORDS_CONTRACT}
                  if version == RELEASE_CONTRACT else
                  {response_rendering.WORDS_CONTRACT, response_rendering.LISTED_CONTRACT,
                   response_rendering.SECTIONS_CONTRACT, response_rendering.LAID_OUT_CONTRACT,
                   response_rendering.CONFINED_CONTRACT, response_rendering.CONTRACT})
    return (version in {LEGACY_CONTRACT, AUTHORITY_CONTRACT, CALCULATION_CONTRACT, *_RELEASED}
            and set(activity) == expected_fields and rendering in renderings)


def validate_activity(activity, context, elements):
    """The check of a turn as it is saved: rebuilt from its saved contract and snapshots,
    never fetching newer law, it must give exactly the answer to be saved."""
    version = activity.get("contract") if isinstance(activity, dict) else None
    if version == UNANSWERED_CONTRACT:
        # Plan AN.41 (D66): the message saved with nothing of an answer.
        if not known_activity(activity) or elements != []:
            raise ValueError("A turn saved unanswered shows nothing of an answer")
        return deepcopy(activity)
    if version in SECTIONED:
        return _validate_sections(activity, context, elements)
    if not known_activity(activity):
        raise ValueError("Unknown saved turn or rendering contract")
    rendering = activity["rendering_contract"]
    limits = (calculation.validate(activity["calculation"], context)
              if version in (CALCULATION_CONTRACT, *_RELEASED) else None)
    record = research.validate(activity["research"], activity["research"]["plan"], context)
    sources = answer_sources.build(context, record)
    if sources != activity["sources"] or execution_record(record) != activity["execution"]:
        raise ValueError("Saved sources or operation evidence changed")
    rebuilt = response_rendering.render(context, record, sources, activity["draft"],
        activity["review"], execution=activity["execution"],
        authority_evidence=activity.get("authority_evidence"), contract=rendering, time_limits=limits,
        held=activity["release"] if version in _RELEASED else None)
    if rebuilt != elements:
        raise ValueError("Saved response differs from its admitted rendering")
    return deepcopy(activity)


def saved_rows(matter, advocate_id):
    """A saved conversation's turns exactly as saved (owner decision P46, 24 Oct 2026: reopening
    from history shows what is saved and never rebuilds it). What is checked is the record
    itself: the matter file's seal, which the store opens, each turn's receipt, the chain of
    digests and the owner (conversation.checked_rows), and that each turn is of a version this
    code reads. Each answer and the records it saved were checked once, when the turn was saved
    (validate_activity, commit). Read only."""
    rows = checked_rows(matter, advocate_id, copied=False)
    if not all(known_activity(row["activities"]) for row in rows):
        raise ConversationRefused("This saved conversation could not be read reliably. "
            "Its records are unchanged.", code="saved_response_unavailable",
            committed="previously_committed")
    return rows


def process(model, store, searcher, *, advocate_id, message, turn_id, chat_id=None,
            matter_id=None, expected_version=None, session_current=lambda: False,
            attempts: TurnAttemptPort | None = None, case_index=None, provision_reader=None,
            progress=None, documents=(), held_acts=None, running=lambda turn_id: False,
            chosen_model=None, effort=None, propose=None, desk=None, stronger=None, stopping=None, steers=None,
            attach=None, entitle=None, go=None, steered_with=None, appended=None):
    """One turn. chosen_model and effort: what the advocate chose for it (plan AN.33, D23) - the model, which the caller's model
    port already runs every call on, and the effort, which moves every call of the turn (calls.TurnCalls); both recorded with the
    turn's metrics, and in its request where they are not the defaults. None: not chosen (the defaults, unrecorded).
    propose and desk (plan AN.37, D37-D40): propose(calls, context, interpretation, plan, asked_before) gives the questions the
    model would ask the advocate once the plan is known, which code admits (questions.admit); desk.open(turn_id, asking) lets the
    page's answers reach the window while the turn runs (its owner closes it when the turn stops). None: nothing asked.
    stronger (plan AN.38, D47-D49): under Auto, the model port a call moves to on the turn's own evidence (routing); None: every
    call runs on model.

    Plan AN.41 (D66-D73): the message and its files are saved with the conversation before any AI work, and each step's result as
    it finishes; an answer that stops part-way keeps all it finished, with why it stopped, for Continue or Discard; the same message
    sent again continues where it stopped. stopping (plan AN.42, D78): whether the advocate has stopped the answer, asked before
    every call. steers (D79): takes what the advocate has steered the answer with since it was last asked - each {"text",
    "documents", "at"} - and clears the stop it came with; the answer then continues with it. attach(advocate_id, chat_id, write)
    (D77): told, once the message is saved, how a write from outside the turn beside its conversation is made on the turn's own
    versions - write(change) runs change(context) under the turn's lock of writes and keeps the context it returns.
    entitle (plan AN.43, D82, D84): given what is known of the matter (titles.material), the title the model writes for the
    conversation, as code admits it, or None; asked once the matter is understood, beside the answer, where the conversation has no
    title yet - once named, it stays as named.

    go (plan AN.48, piece 48a): the go-ahead of a matter worked step by step (steps.first, steps.given) - which steps this run may
    take. The run stops when they are done, with the code 'waiting' and everything it finished kept (as a stop keeps it, D69), for
    the advocate's next go-ahead; each step claims an attempt of its own (D150). None: end to end, exactly as before.
    steered_with (plan AN.48, 48c): the advocate's words that make the matter be thought again while it waited - each {"text",
    "documents", "at"}, as a steer is - joining it as their words; the matter is understood again with them (D149's rethink).
    appended (48h, D159): what the advocate added while the matter waited, kept as their own messages after the latest one;
    the research stays as it is."""
    if not session_current():
        raise ConversationRefused("Sign in again before continuing.", status=401)
    effort = reasoning.DEFAULT_CHOICE if effort is None else effort
    if effort not in reasoning.CHOICES:
        raise ConversationRefused("Choose how hard NM reasons from the list it offers.", status=422)
    chosen = None if chosen_model is None and effort == reasoning.DEFAULT_CHOICE else {
        "model": chosen_model, "effort": effort}
    choice = tuple((name, value) for name, value, default in (
        ("model", chosen_model, DEFAULT_TURN_MODEL), ("effort", effort, reasoning.DEFAULT_CHOICE))
        if value is not None and value != default)
    if matter_id is None:
        # Another turn of this conversation that stopped after showing part of its answer
        # is saved first, with what it showed (P27); this same turn sent again starts afresh.
        try:
            stored = store.load(chat_matter_id(advocate_id, stored_chat(advocate_id, chat_id, turn_id)))
        except (OSError, ValueError) as exc:
            raise ConversationRefused("The conversation could not be loaded reliably.") from exc
        if stored is not None and stored.advocate_id == advocate_id:
            try:
                held = shown_of(stored)
            except ValueError:
                held = {"turn_id": None}
            if held is not None and held["turn_id"] is not None and held["turn_id"] != turn_id and running(held["turn_id"]):
                # Plan AN.42 (D77): one answer at a time in a conversation; what is written meanwhile waits in the queue.
                raise ConversationRefused("NM is still working on your earlier message in this conversation. Your new message "
                                          "can wait above the message box until that answer is ready.", code="turn_in_progress")
            if held is not None and held["turn_id"] != turn_id:
                # Plan AN.41 (D71): a new message sent instead of Continue or Discard saves the answer that stopped as it is.
                recover(store, stored, advocate_id, running=running, session_current=session_current)
            # What another message asked and was never saved with (its turn stopped before showing anything) is withdrawn;
            # this same message sent again reuses it (plan AN.37, D40).
            try:
                current = store.load(stored.id)
                waiting = asking_of(current)
            except (OSError, ValueError):
                current, waiting = None, None
            if waiting is not None and waiting["turn_id"] != turn_id and not running(waiting["turn_id"]):
                try:
                    drop_asking(store, current)
                except (OSError, StaleWrite, ValueError):
                    log.warning("What an earlier message asked could not be withdrawn", exc_info=True)
    context = open_turn(store, advocate_id=advocate_id, message=message, turn_id=turn_id,
                        chat_id=chat_id, matter_id=matter_id, expected_version=expected_version,
                        documents=documents, choice=choice)
    if context.rows:
        saved_rows(context.matter, advocate_id)
    if context.replay is not None:
        return commit_turn(store, context, elements=[], activities={}, session_current=session_current)
    if attempts is None:
        raise ConversationRefused("Conversation processing is not configured.", status=503,
                                  code="attempt_storage_unavailable")
    gate = stepwise.Gate(go)
    identity = digest([advocate_id, context.chat_id, turn_id, *stepwise.attempt_part(go)])
    # The committed conversation the request was made on: what a turn shows while it works
    # is saved beside it, and a same request sent again still matches (P27).
    binding = digest({"request": context.request, "version": committed_version(context.rows),
                      "previous": context.rows[-1]["digest"] if context.rows else None})
    try:
        claim = attempts.claim(identity, binding)
    except AttemptRefused as exc:
        raise _attempt_refusal(exc) from exc
    token = claim["token"]

    def finish(state, code=None):
        try:
            attempts.finish(identity, token, state, code)
        except AttemptRefused as exc:
            raise _attempt_refusal(exc) from exc

    calls = TurnCalls(model, corrections_used=claim["corrections_used"],
                      reserve_correction=lambda: attempts.consume_correction(identity, token),
                      effort=effort, chosen=chosen, stronger=stronger, stopping=stopping,
                      gate=gate.call if gate.stepwise else None)
    # What the answer shows as each part passes is saved beside the conversation then (P27),
    # and the page told how much there is to show (P26).
    holder, report = {"context": context, "shown": 0, "asking": None, "model": None}, _reporter(progress)
    # The writes beside the conversation - what is shown, what is asked and answered - come from several threads (P26; plan
    # AN.37): one at a time, each on the version the last left.
    beside = threading.Lock()
    try:
        before = shown_of(context.matter)
    except ValueError:
        before = None
    same = before if before and before["turn_id"] == turn_id else None
    base = same["base_version"] if same else context.matter.version
    # Plan AN.41 (D66): the message and its files are saved with the conversation before any AI work begins. The same message
    # sent again - Continue - starts from what it saved (D70), with what steered it (D79).
    resume = (None if same is None else same["steps"] if "steps" in same else steps_from(same))
    rethought = bool(steered_with) and resume is not None
    if rethought:
        # Plan AN.48 (48c; D149's rethink, today's Steer): what the advocate added while the matter waited joins it as their words;
        # the matter is understood again with them, each dispute's research kept where the new plan asks what it answered, and
        # the analyses written before are written again once asked for.
        resume = {**resume, "answered": None, "cases": {}}
    held = sent(turn_id, context.request, context.message, context.documents, base,
                at=datetime.now(timezone.utc).isoformat(), steps=resume,
                steers=[*(same.get("steers", ()) if same is not None and resume is not None else ()), *(steered_with or ())],
                go=go, added=[*(same.get("added", ()) if same is not None and resume is not None else ()), *(appended or ())])
    if resume is not None:
        held["elements"], held["metrics"] = ([] if rethought else same["elements"]), same["metrics"]
    if held["steers"]:
        context = replace(context, steers=tuple(held["steers"]))
        holder["context"] = context
    if held.get("added"):
        # Plan AN.48 (48h, D159): the advocate's added messages, in every step still to come.
        context = replace(context, added=tuple(held["added"]))
        holder["context"] = context
    keeper = _Keeper(store, holder, beside, held, report)
    try:
        keeper.write()
    except (OSError, StaleWrite, ConversationRefused, ValueError) as exc:
        finish("retryable", "not_saved")
        raise ConversationRefused("Your message could not be saved, so NM has not started on it. Sending it again is safe.",
                                  status=503, code="message_not_saved", retryable=True) from exc
    report("sent", chat_id=context.chat_id)
    # Plan AN.48 (48e, D140): a step's tentative time, said while it runs and kept beside the time it took.
    began = time.monotonic()
    estimated = (stepwise.estimate(go, None if rethought else resume, tentative.pages_of(context.documents))
                 if gate.stepwise else None)
    if estimated is not None:
        report("tentative", seconds=estimated)

    def write_beside(change):
        with beside:
            holder["context"] = change(holder["context"])
    if attach is not None:
        attach(advocate_id, context.chat_id, write_beside)
    try:
        titled = title_of(context.matter)
    except ValueError:
        titled = None
    titling = {}

    def entitled(payload, plan):
        """Plan AN.43 (D82, D84): the conversation's title, written once the matter is understood - beside the research, never
        holding the answer up - where it has none yet. Once NM has named it, it stays as named."""
        if entitle is None or titling or titled is not None:
            return

        def write():
            try:
                text = entitle(titles.material(payload, plan))
            except (ModelError, ModelPermissionRefused, EgressRefused) as exc:
                log.warning("No title was written for the conversation: %s", type(exc).__name__)
                return
            if text is None:
                return
            try:
                write_beside(lambda current: hold_title(store, current, {"text": text,
                                                                          "from_matter": titles.understood(plan)}))
            except (OSError, StaleWrite, ConversationRefused, ValueError):
                log.warning("The conversation's title could not be saved", exc_info=True)
                return
            # D84: the page reads the conversation again when its saved work moves on, and finds the title there.
            keeper.saved += 1
            report("saved", saved=keeper.saved, chat_id=context.chat_id)
        titling["thread"] = threading.Thread(target=write, name="turn-title", daemon=True)
        titling["thread"].start()

    def shown(elements, state, metrics):
        def change(held):
            held["elements"], held["metrics"] = elements, metrics
            held["steps"] = {**held["steps"], "answered": state}
        if not keeper.now(change):
            # The answer goes on; its commit decides what is saved.
            return
        holder["shown"] += 1
        report("shown", shown=holder["shown"], chat_id=context.chat_id)

    def sealed(state):
        """What the turn asked and the answers as they stand, sealed beside the conversation (plan AN.37, D40)."""
        try:
            with beside:
                holder["context"] = hold_asking(store, holder["context"], state)
        except (OSError, StaleWrite, ConversationRefused, ValueError):
            # The window goes on; the turn's commit saves what was asked and answered.
            log.warning("What the turn asked could not be saved beside the conversation", exc_info=True)

    asked_before = [question["question"] for row in context.rows if "asked" in row for question in row["asked"]["questions"]]
    try:
        again = asking_of(context.matter, turn_id)
    except ValueError:
        again = None

    window_lock = threading.Lock()

    def opened(admitted):
        """Plan AN.37 (D87): the turn's one window - opened by the first questions put to the advocate, the model's or code's,
        with what this same message asked before (a retry, D40) - with the questions given added to it. Returns their IDs (None
        for one the window has no room for), and the window."""
        with window_lock:
            asking, fresh = holder["asking"], holder["asking"] is None
            if fresh:
                state = again["state"] if again is not None else {"questions": [], "answers": []}
                # Plan AN.48 (48d): end to end step by step, the defaults stand at once (D135, D142); otherwise as before.
                asking = questions.Asking(state["questions"], hold=sealed, report=report,
                                          **({"wait": gate.question_wait()} if gate.question_wait() is not None else {}))
                if asking.questions:
                    asking.start(given={entry["id"]: {"chosen": entry["chosen"], "other": entry["other"]}
                                        for entry in state["answers"] if entry["how"] != "assumed"})
            ids = asking.add(admitted) if admitted else []
            if fresh and asking.questions:
                holder["asking"] = asking
                if desk is not None:
                    desk.open(turn_id, asking)
            return ids, holder["asking"]

    def ask(interpreted, plan, payload):
        """Plan AN.37: the questions - the model's as code admits them, or those this same message asked before - shown to the
        advocate; returns the window, or None where nothing is asked. The model is asked once in a run (a steer keeps them)."""
        if holder["model"] is None:
            if again is not None:
                holder["model"] = [question for question in again["state"]["questions"]
                                   if question.get("asked_by", "model") != "code"]
            elif propose is None:
                holder["model"] = []
            elif gate.stepwise and resume is not None and resume.get("limits") is not None:
                # Plan AN.48 (48a1): a matter worked step by step is asked its questions once, in the step that researched it (its
                # time limits are saved after them); where that step asked nothing, a later step does not ask again.
                holder["model"] = []
            else:
                understanding = (plan.get("proposal") or {}).get("understanding") or {}
                disputes = [dispute["id"] for dispute in understanding.get("disputes") or []]
                admitted, refused = questions.admit(propose(calls, payload, interpreted, plan, asked_before),
                                                    asked_before=asked_before, disputes=disputes)
                if refused:
                    log.info("Questions code did not show: %s", "; ".join(item["why"] for item in refused))
                holder["model"] = admitted
        if not holder["model"]:
            return None
        return opened(holder["model"])[1]

    def settle(asked):
        """Plan AN.37 (D87): code's questions - which Act or judgment a name means - put in the window and waited for, each its
        own WAIT; one asked before in this conversation, or past the window's room, goes on with its default. Returns each
        question as asked with its answer (None: the default)."""
        admitted, refused = questions.admit(asked, asked_before=asked_before,
                                            disputes={name for question in asked for name in question["depends"]})
        if refused:
            log.info("Questions code did not show: %s", "; ".join(item["why"] for item in refused))
        shown = {position - 1 for position in range(1, len(asked) + 1)} - {item["position"] - 1 for item in refused}
        ids, asking = opened(admitted) if admitted else ([], holder["asking"])
        if gate.asks() and asking is not None and ids:
            # Plan AN.48 (48d; D154): step by step, code's question ends the research step until it is answered.
            given = asking.answers()
            if any(identity is not None and given.get(identity, {}).get("how") not in ("answered", "late") for identity in ids):
                raise stepwise.Waiting(stepwise.ASKED)
        answers = asking.wait_for(ids) if asking is not None and ids else {}
        by_place = dict(zip(sorted(shown), ids))
        out = []
        for place, question in enumerate(asked):
            identity = by_place.get(place)
            given = answers.get(identity) if identity is not None else None
            out.append((question, given if given is not None and given["how"] != "assumed" else None))
        return out

    def withdraw():
        """A turn withheld whole keeps nothing it showed (G-CORE), nor anything it saved as it worked."""
        keeper.close()
        try:
            holder["context"] = drop_shown(store, holder["context"])
        except (OSError, StaleWrite):
            log.warning("What an unanswered turn showed could not be withdrawn", exc_info=True)

    def stopped(code, exc, *, answered=None):
        """Plan AN.41 (D69): the turn stopped part-way; all it finished is kept with why, for Continue or Discard."""
        keeper.stop(code, answered=answered)
        exc.kept = True
    # Plan AN.48 (48c): a matter given words while it waited is understood again with them, as a steer is (D79).
    steered = rethought
    # Plan AN.48 (D175): a follow-up worked step by step, not yet understood, may start from the last saved answer's understanding.
    follow = (follow_up.earlier(context.rows)
              if gate.stepwise and not rethought and not (resume or {}).get("understood") else None)
    try:
        while True:
            try:
                elements, activity, metrics = prepare(calls, context.payload(), searcher,
                    case_index=case_index, provision_reader=provision_reader, progress=progress,
                    held_acts=held_acts, shown=shown, ask=ask, keep=keeper, resume=resume, steered=steered,
                    on_understood=entitled, settle=settle, gate=gate, follow=follow)
                break
            except StopRequested:
                taken = steers() if steers is not None else []
                if not taken:
                    raise
                # Plan AN.42 (D79): the answer continues with the steer - from the steps finished so far, each kept where it still
                # answers what the steered conversation asks. What was shown before it is only the words each section is reviewed
                # again from: it is no longer kept as finished, so that no Continue after this could pass the steer over.
                resume, steered = deepcopy(keeper.held["steps"]), True

                def steering(held):
                    held["steers"] = [*held["steers"], *taken]
                    held["steps"] = {**held["steps"], "answered": None, "cases": {}}
                keeper.now(steering)
                context = replace(context, steers=(*context.steers, *taken))
                with beside:  # a write beside the conversation may be under way: the turn's context changes between writes
                    holder["context"] = replace(holder["context"], steers=context.steers)
                # Whatever of the earlier work is still under way stops at its next call; the steered answer goes on.
                calls = calls.successor()
                report("steering")
        # Nothing more is saved as the turn works: what it made is saved with it, below - the title first, where it is still
        # being written (a short call; the answer is not held up for longer than TITLE_WAIT).
        if titling:
            titling["thread"].join(TITLE_WAIT)
        keeper.close()
        if holder["asking"] is not None:
            # Plan AN.37: what was asked, and the answers as they stand now, are saved with the turn - a question no writing
            # waited on with its default, as assumed.
            holder["asking"].settle()
            context = replace(context, asked=holder["asking"].state())
            with beside:
                holder["context"] = replace(holder["context"], asked=context.asked)
        # The one check of the answer, as it is saved (P46): what its checks share is derived
        # once (P35).
        with replay_scope.replaying():
            validate_activity(activity, context.payload(), elements)
    except AttemptRefused as exc:
        keeper.close()
        raise _attempt_refusal(exc) from exc
    except stepwise.Waiting as exc:
        # Plan AN.48 (D134, 48a1-48a2): the step the advocate allowed is done; the matter waits for their go-ahead, with all it
        # finished kept - the title first, where it is still being written. Not a failure: the step's attempt is retryable, so
        # that the go-ahead (or Continue) goes on from here.
        if titling:
            titling["thread"].join(TITLE_WAIT)
        refusal = ConversationRefused(STOPS["waiting"], status=409, code="waiting", retryable=True)
        keeper.stop("waiting", waiting=exc.after, timed=(estimated, time.monotonic() - began), rechecked=gate.rechecked)
        refusal.kept = True
        finish("retryable", "waiting")
        refusal.metrics = calls.metrics()
        raise refusal from exc
    except StopRequested as exc:
        # Plan AN.42 (D78): stopped by the advocate after the step in progress; every piece finished is kept.
        refusal = ConversationRefused(STOPS["stopped"] + " What NM had finished is kept.", status=409, code="stopped",
                                      retryable=True)
        stopped("stopped", refusal)
        finish("retryable", "stopped")
        refusal.metrics = calls.metrics()
        raise refusal from exc
    except ModelPermissionRefused as exc:
        # Never turned into an answer here; what was finished stays saved beside the conversation for Continue (D69).
        stopped("model_permission_required" if session_current() else "signed_out", exc)
        finish("retryable", "model_permission_required")
        raise
    except ModelError as exc:
        if isinstance(exc, ContextOverflow):
            withdraw()
            why = "This conversation exceeds the current processing capacity. Your saved conversation is unchanged."
            code = "context_capacity"
        elif isinstance(exc, UsageLimitReached):
            # The provider's account has no credit left (owner decision P51, 25 Oct 2026): said in the owner's words, status
            # 402 for it. Plan AN.41 (D69): what NM finished is kept beside the conversation (kept), and Continue works once that
            # is put right; the saved conversation itself is unchanged.
            why = USAGE_LIMIT_MESSAGE + " Your saved conversation is unchanged."
            code = "usage_limit"
        elif isinstance(exc, (ReleaseWithheld, CorrectionUnavailable, SchemaViolation)):
            # What the check still found, and what the advocate can do (owner decision,
            # 17 Oct 2026), where the release boundary itself withheld the answer (G-CORE: nothing of it is kept).
            withdraw()
            found = getattr(exc, "found", None)
            why = ("I could not provide a sufficiently reliable answer to this message. "
                   + (f"After the rewrites NM may make, the independent check still found: {found} You can "
                      "send the message again, narrow it, or add a fact or document it may need. " if found else "")
                   + "Your saved conversation is unchanged.")
            code = "answer_withheld"
        else:
            why = "The response could not be completed at present. Your saved conversation is unchanged."
            code = "response_unavailable"
        refusal = ConversationRefused(why, status=402 if code == "usage_limit" else 503, code=code,
                                     retryable=code in ("response_unavailable", "usage_limit"))
        if code in ("usage_limit", "response_unavailable"):
            stopped(code, refusal)
        refusal.diagnosis = _diagnosis(code, exc, calls)
        # A gate's fixed names, or a provider failure's own kind and message (17 Oct 2026:
        # a failed call's reason was lost); never the message, a draft or the review's words.
        log.warning("Message not answered: %s%s", refusal.diagnosis,
                    f" ({exc})" if isinstance(exc, ReleaseWithheld) and str(exc).startswith("G-")
                    else f" ({type(exc).__name__}: {str(exc)[:300]})" if code != "answer_withheld" else "")
        finish("retryable" if refusal.retryable else "terminal", refusal.diagnosis)
        refusal.metrics = calls.metrics()
        raise refusal from exc
    except Exception:
        # Not a model failure and not disguised as one: what was finished is kept, the failure goes on to its owner.
        keeper.stop("failed")
        finish("retryable", "failed")
        raise
    keeper.close()
    _reporter(progress)("saving")
    # Plan AN.48 (48b): a matter finished with the analyses of some of its disputes says so above the answer.
    partly = stepwise.unasked(activity["sections"]) if gate.stepwise and "sections" in activity else None
    if gate.stepwise:
        # 48e (D140): each step's tentative time beside the time it took, kept with the answer's own record.
        metrics = {**metrics, "steps_timed": stepwise.timed(go, estimated, time.monotonic() - began)["times"]}
    try:
        response = commit_turn(store, holder["context"], elements=elements, activities=activity,
                               records=checklist.records(context.payload(), activity),
                               metrics=metrics, session_current=session_current,
                               **({"service_status": PARTLY_SAID.format(written=partly[0], of=partly[1])} if partly else {}))
    except ConversationRefused as exc:
        # A subsequent request checks the durable response before the attempt.
        # Unconfirmed ownership never permits repeating the effect.
        state = {"committed": "finished", "not_committed": "retryable"}.get(exc.committed, "unconfirmed")
        if state == "retryable":
            # Plan AN.41: the finished answer is kept for Continue, which saves it.
            stopped("signed_out" if exc.status == 401 else "not_saved", exc,
                    answered=(elements, {key: activity[key] for key in ("sections", "cross_check", "overview")}))
        finish(state, exc.code)
        raise
    try:
        finish("finished")
    except (ConversationRefused, EgressRefused):
        # The committed response is authoritative. Failure to close auxiliary
        # bookkeeping cannot erase it or induce the caller to repeat its effect.
        pass
    return response


def _attempt_refusal(exc):
    if exc.code == "terminal":
        return ConversationRefused("This message could not be answered reliably. "
            "Its previous outcome has been retained.", status=409, code="answer_withheld")
    if exc.code == "conflict":
        return ConversationRefused("This request identity no longer matches its original conversation.",
                                   status=409, code="request_conflict")
    return ConversationRefused("The previous processing attempt could not be confirmed. "
        "Your saved conversation is available to reopen.", status=503,
        code="attempt_unconfirmed", committed="unconfirmed")
