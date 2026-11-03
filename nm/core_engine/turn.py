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

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

from concurrent.futures import ThreadPoolExecutor

from nm.core_engine import answer_sections, answer_sources, calculation, checklist, estimates, questions, research
from nm.core_engine import reasoning, replay_scope, response_rendering, response_writer
from nm.core_engine import understanding
from nm.core_engine.calls import CorrectionUnavailable, ReleaseWithheld, TurnCalls
from nm.core_engine.conversation import (
    ConversationRefused, TurnContext, asking_of, chat_matter_id, checked_rows, commit_turn, committed_version, digest,
    drop_asking, drop_shown, hold_asking, hold_shown, open_turn, shown_of, stored_chat,
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
    with ThreadPoolExecutor(max_workers=1) as pool:
        working = (pool.submit(calculation.work_out, calls, context, held_acts)
                   if held_acts is not None and _needs_research(plan) else None)
        record = research.retrieve(plan, searcher, context, model=calls, progress=report)
        limits = working.result() if working is not None else calculation.skipped()
    return interpreted, record, limits


def _interpreted(calls, context, report, early=None):
    """The message's interpretation and the matter's understanding, side by side, and the
    research plan; returns the interpretation and the plan."""
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

    with ThreadPoolExecutor(max_workers=1) as beside:
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
    stand, and, after its sections, what changed since they began and which disputes that touches (None: the whole answer)."""

    def __init__(self, asking, base):
        self.asking, self.base = asking, base

    def context(self):
        return {**self.base, "answers": questions.context_answers(self.asking.questions,
                                                                  list(self.asking.answers().values()))}

    def version(self):
        return self.asking.version

    def since(self, version):
        changed = self.asking.changed_since(version)
        if not changed:
            return None, None
        depends = [question["depends"] for question in self.asking.questions if question["id"] in changed]
        return self.context(), None if any(not names for names in depends) else {name for names in depends for name in names}


def prepare(model, context, searcher, *, case_index=None, provision_reader=None, progress=None,
            held_acts=None, shown=None, ask=None):
    """Prepare and admit one response, dispute by dispute (turn v7, owner decisions P25-P27, P29).
    No persistence or external action occurs here. shown (P26): told, each time the answer
    shows more, its elements so far and the activity they come from (its sections done, the
    parts still being written under "waiting"). ask (plan AN.37): given the interpretation, the plan
    and the context, asks the advocate what only they can settle and returns its questions.Asking once
    the answers or the defaults stand, or None where nothing is asked."""
    report = _reporter(progress)
    calls = model if isinstance(model, TurnCalls) else TurnCalls(model)
    report("understanding")
    # Plan AN.37 (D41, D45): what the turn is expected to cost - roughly now, from the papers sent, and again once its plan is
    # known - kept beside what it spends, for diagnostics only.
    priced = calls.model_for(Tier.HARD)
    if priced is not None:
        calls.expect("start", estimates.turn_start_usd(priced, _papers(context), calls.effort))
    # Plan AN.33 (D28; piece 33q): the held law is searched as soon as the understanding and its search phrases are final, beside
    # the papers' side-by-side reading and the weighing; each search begun so is used once, as it would have been made.
    started = {}
    interpreted, plan = _interpreted(calls, context, report,
                                     early=lambda work: started.update(research.start_search(searcher, work)))
    if priced is not None:
        disputes = len(response_writer.parts({"contract": research.CONTRACT, "plan": plan}))
        calls.expect("planned", estimates.turn_planned_usd(priced, calls.estimate()["spent_usd"], max(1, disputes - 1),
                                                           calls.effort))
    # Step 4 (owner, 21 Oct 2026; P26 as first decided): each dispute is researched as its own
    # part, and its section is written as soon as that part is ready; the time limits are
    # worked out beside the search, only where research is needed.
    with ThreadPoolExecutor(max_workers=1) as pool:
        working = (pool.submit(calculation.work_out, calls, context, held_acts)
                   if held_acts is not None and _needs_research(plan) else None)
        parts = research.retrieve_parts(plan, searcher, context, model=calls, progress=report, started=started,
                                        case_index=case_index)
        # Plan AN.37 (D39): what only the advocate can settle is asked once the plan is known. The research and the time
        # limits go on meanwhile; the writing, which depends on the answers, waits for them or, after WAIT, the defaults.
        asking = ask(interpreted, plan, context) if ask is not None else None
        limits = working.result() if working is not None else calculation.skipped()
    later = _Later(asking, context) if asking is not None else None
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
        shown(elements, {**base(record, sources, execution), **state}, calls.metrics())
    # Turn v9 (AN.28): each section written for the advocate and placed, its failing pieces given a second
    # look and then blocked one by one (writer v14), reviewed by review v12, and laid out as rendering v19.
    sections, crossed, overview = answer_sections.answer(
        calls, context, None, None, interpretation=interpreted, execution=None, worked=limits,
        case_index=case_index, provision_reader=provision_reader, report=report, released=released,
        researched=researched, contract=response_writer.CASED_CONTRACT, later=later)
    if later is not None:
        context = later.context()
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
                              asked=asking["state"] if asking is not None else None)
        if context.request != held["request"] or any(row["turn_id"] == held["turn_id"] for row in rows):
            raise ValueError("What was shown belongs to another request")
        activity = interrupted(held["activity"])
        original = context.payload()
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
    except (ValueError, KeyError, TypeError, SchemaViolation) as exc:
        log.warning("The unfinished parts of an answer could not be read reliably and were withdrawn: %s",
                    type(exc).__name__)
        drop_shown(store, TurnContext(matter, rows[0]["chat_id"] if rows else "", "", "", tuple(rows)))
        return None
    return commit_turn(store, context, elements=elements, activities=activity,
                       records=checklist.records(original, activity),
                       metrics=held["metrics"] if metrics is None else metrics, service_status=service_status,
                       session_current=session_current)


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
            chosen_model=None, effort=None, propose=None, desk=None):
    """One turn. chosen_model and effort: what the advocate chose for it (plan AN.33, D23) - the model, which the caller's model
    port already runs every call on, and the effort, which moves every call of the turn (calls.TurnCalls); both recorded with the
    turn's metrics, and in its request where they are not the defaults. None: not chosen (the defaults, unrecorded).
    propose and desk (plan AN.37, D37-D40): propose(calls, context, interpretation, plan, asked_before) gives the questions the
    model would ask the advocate once the plan is known, which code admits (questions.admit); desk.open(turn_id, asking) lets the
    page's answers reach the window while the turn runs (its owner closes it when the turn stops). None: nothing asked."""
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
            if held is not None and held["turn_id"] != turn_id:
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
    identity = digest([advocate_id, context.chat_id, turn_id])
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
                      effort=effort, chosen=chosen)
    # What the answer shows as each part passes is saved beside the conversation then (P27),
    # and the page told how much there is to show (P26).
    holder, report = {"context": context, "shown": 0, "asking": None}, _reporter(progress)
    # The writes beside the conversation - what is shown, what is asked and answered - come from several threads (P26; plan
    # AN.37): one at a time, each on the version the last left.
    beside = threading.Lock()
    try:
        before = shown_of(context.matter)
    except ValueError:
        before = None
    base = before["base_version"] if before and before["turn_id"] == turn_id else context.matter.version

    def shown(elements, activity, metrics):
        held = {"turn_id": turn_id, "request": context.request, "message": context.message,
                "documents": deepcopy(list(context.documents)), "activity": activity, "elements": elements,
                "metrics": metrics, "at": datetime.now(timezone.utc).isoformat(), "base_version": base}
        try:
            with beside:
                holder["context"] = hold_shown(store, holder["context"], held)
        except (OSError, StaleWrite, ConversationRefused, ValueError):
            # The answer goes on; its commit decides what is saved.
            log.warning("What the answer showed could not be saved beside the conversation", exc_info=True)
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

    def ask(interpreted, plan, payload):
        """Plan AN.37: the questions - the model's as code admits them, or those this same message asked before - shown to the
        advocate; returns the window once the answers or the defaults stand, or None where nothing is asked."""
        if again is not None:
            state = again["state"]
        elif propose is None:
            return None
        else:
            understanding = (plan.get("proposal") or {}).get("understanding") or {}
            disputes = [dispute["id"] for dispute in understanding.get("disputes") or []]
            admitted, refused = questions.admit(propose(calls, payload, interpreted, plan, asked_before),
                                                asked_before=asked_before, disputes=disputes)
            if refused:
                log.info("Questions code did not show: %s", "; ".join(item["why"] for item in refused))
            if not admitted:
                return None
            state = {"questions": admitted, "answers": []}
        asking = questions.Asking(state["questions"], hold=sealed, report=report)
        given = {entry["id"]: {"chosen": entry["chosen"], "other": entry["other"]} for entry in state["answers"]
                 if entry["how"] != "assumed"}
        holder["asking"] = asking
        if desk is not None:
            desk.open(turn_id, asking)
        asking.ask(given=given)
        return asking

    def withdraw():
        """A turn withheld whole, or not answered at all, keeps nothing it showed. What an
        earlier run of this same message showed is left as it was saved."""
        if not holder["shown"]:
            return
        try:
            holder["context"] = drop_shown(store, holder["context"])
        except (OSError, StaleWrite):
            log.warning("What an unanswered turn showed could not be withdrawn", exc_info=True)
    try:
        elements, activity, metrics = prepare(calls, context.payload(), searcher,
            case_index=case_index, provision_reader=provision_reader, progress=progress,
            held_acts=held_acts, shown=shown, ask=ask)
        if holder["asking"] is not None:
            # Plan AN.37: what was asked, and the answers as they stand now, are saved with the turn.
            context = replace(context, asked=holder["asking"].state())
            holder["context"] = replace(holder["context"], asked=context.asked)
        # The one check of the answer, as it is saved (P46): what its checks share is derived
        # once (P35).
        with replay_scope.replaying():
            validate_activity(activity, context.payload(), elements)
    except AttemptRefused as exc:
        raise _attempt_refusal(exc) from exc
    except ModelPermissionRefused:
        # Never turned into an answer here; what was shown stays saved beside the
        # conversation, and is saved with it unless this same message is sent again.
        finish("retryable", "model_permission_required")
        raise
    except ModelError as exc:
        if isinstance(exc, UsageLimitReached) and holder["shown"]:
            # Plan AN.37 (D46; owner, 3 Nov 2026): the usage ran out part-way through the answer. What it had shown is kept -
            # saved now as a turn that stopped part-way (P27), with P51's words above it - rather than withdrawn.
            _reporter(progress)("saving")
            try:
                held = shown_of(holder["context"].matter)
            except ValueError:
                held = None
            try:
                response = (save_shown(store, holder["context"].matter, advocate_id, held, session_current=session_current,
                                       service_status=STOPPED_FOR_USAGE, metrics=calls.metrics())
                            if held is not None and held["turn_id"] == turn_id else None)
            except ConversationRefused as refused:
                finish({"committed": "finished", "not_committed": "retryable"}.get(refused.committed, "unconfirmed"),
                       refused.code)
                raise
            if response is not None:
                try:
                    finish("finished")
                except (ConversationRefused, EgressRefused):
                    pass  # the saved response is authoritative, as for any answer saved
                return response
        withdraw()
        if isinstance(exc, ContextOverflow):
            why = "This conversation exceeds the current processing capacity. Your saved conversation is unchanged."
            code = "context_capacity"
        elif isinstance(exc, UsageLimitReached):
            # The provider's account has no credit left (owner decision P51, 25 Oct 2026): said in
            # the owner's words, status 402 for it, and the message can be sent again once that is
            # put right; nothing waits on a retry that cannot succeed.
            why = USAGE_LIMIT_MESSAGE + " Your saved conversation is unchanged."
            code = "usage_limit"
        elif isinstance(exc, (ReleaseWithheld, CorrectionUnavailable, SchemaViolation)):
            # What the check still found, and what the advocate can do (owner decision,
            # 17 Oct 2026), where the release boundary itself withheld the answer.
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
        refusal.diagnosis = _diagnosis(code, exc, calls)
        # A gate's fixed names, or a provider failure's own kind and message (17 Oct 2026:
        # a failed call's reason was lost); never the message, a draft or the review's words.
        log.warning("Message not answered: %s%s", refusal.diagnosis,
                    f" ({exc})" if isinstance(exc, ReleaseWithheld) and str(exc).startswith("G-")
                    else f" ({type(exc).__name__}: {str(exc)[:300]})" if code != "answer_withheld" else "")
        finish("retryable" if refusal.retryable else "terminal", refusal.diagnosis)
        refusal.metrics = calls.metrics()
        raise refusal from exc
    _reporter(progress)("saving")
    try:
        response = commit_turn(store, holder["context"], elements=elements, activities=activity,
                               records=checklist.records(context.payload(), activity),
                               metrics=metrics, session_current=session_current)
    except ConversationRefused as exc:
        # A subsequent request checks the durable response before the attempt.
        # Unconfirmed ownership never permits repeating the effect.
        state = {"committed": "finished", "not_committed": "retryable"}.get(exc.committed, "unconfirmed")
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
