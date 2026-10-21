"""One authenticated turn owns preparation, bounded repair, release and replay.

Drafts and reviewer judgments cannot write matter facts or announce execution.
The sealed conversation owner commits the exact checked answer and its evidence
together. This initial flow performs read-only research; record editing is separate.
"""
from __future__ import annotations

import logging
import re
import threading

from copy import deepcopy
from datetime import datetime, timezone

from concurrent.futures import ThreadPoolExecutor

from nm.core_engine import answer_sections, answer_sources, calculation, checklist, research
from nm.core_engine import response_rendering
from nm.core_engine import understanding
from nm.core_engine.calls import CorrectionUnavailable, ReleaseWithheld, TurnCalls
from nm.core_engine.conversation import (
    ConversationRefused, TurnContext, chat_matter_id, checked_rows, commit_turn, committed_version, digest,
    drop_shown, hold_shown, open_turn, shown_of, stored_chat,
)
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.egress_contracts import EgressRefused
from nm.shared.model_port import ContextOverflow, ModelError, SchemaViolation
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
CONTRACT = "core_turn_v7"
#: The turns answered dispute by dispute.
SECTIONED = (BY_DISPUTE_CONTRACT, CONTRACT)
_RELEASED = (RELEASE_CONTRACT, RECORDS_CONTRACT)
EXECUTION = research.EXECUTION
_ACTIVITY_FIELDS = {"contract", "interpretation", "research", "sources", "draft",
                    "review", "execution", "rendering_contract"}
_SECTIONED_FIELDS = {"contract", "interpretation", "research", "sources", "execution", "calculation",
                     "rendering_contract", "sections", "cross_check", "overview"}


#: Receipts describe what this code did, never whether the request is fulfilled (research owns them).
execution_record = research.execution


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


def _interpreted(calls, context, report):
    """The message's interpretation and the matter's understanding, side by side, and the
    research plan; returns the interpretation and the plan."""
    # The matter's first understanding reads the conversation itself, so it is written
    # beside the message's interpretation (owner, 18 Oct 2026, for speed); its next step
    # waits for the interpretation, which says whether there is a matter to research at all.
    decided, verdict = threading.Event(), {"carries": True}

    def wanted():
        decided.wait()
        return verdict["carries"]

    with ThreadPoolExecutor(max_workers=1) as beside:
        planning = beside.submit(calls.checked, "core_research_plan",
                                 lambda: research.plan(calls, context, progress=report, wanted=wanted))
        try:
            interpreted = calls.checked("core_understanding", lambda: understanding.understand(calls, context))
            verdict["carries"] = research.carries_matter(interpreted)
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


def prepare(model, context, searcher, *, case_index=None, provision_reader=None, progress=None,
            held_acts=None, shown=None):
    """Prepare and admit one response, dispute by dispute (turn v7, owner decisions P25-P27, P29).
    No persistence or external action occurs here. shown (P26): told, each time the answer
    shows more, its elements so far and the activity they come from (its sections done, the
    parts still being written under "waiting")."""
    report = _reporter(progress)
    calls = model if isinstance(model, TurnCalls) else TurnCalls(model)
    report("understanding")
    interpreted, plan = _interpreted(calls, context, report)
    # Step 4 (owner, 21 Oct 2026; P26 as first decided): each dispute is researched as its own
    # part, and its section is written as soon as that part is ready; the time limits are
    # worked out beside the search, only where research is needed.
    with ThreadPoolExecutor(max_workers=1) as pool:
        working = (pool.submit(calculation.work_out, calls, context, held_acts)
                   if held_acts is not None and _needs_research(plan) else None)
        parts = research.retrieve_parts(plan, searcher, context, model=calls, progress=report)
        limits = working.result() if working is not None else calculation.skipped()
    researched = answer_sections.Researched(context, plan, parts)

    def base(record, sources, execution):
        return {"contract": CONTRACT, "interpretation": interpreted, "research": record, "sources": sources,
                "execution": execution, "calculation": limits,
                "rendering_contract": response_rendering.BY_DISPUTE_CONTRACT}

    def released(state):
        if shown is None:
            return
        # What would be saved should the turn stop here (P27): the disputes not yet researched
        # are recorded so.
        record, sources, execution = researched.provisional()
        elements = response_rendering.render_sections(
            context, record, sources, sections=state["sections"], cross_check=state["cross_check"],
            overview=state["overview"], time_limits=limits, waiting=state["waiting"])
        shown(elements, {**base(record, sources, execution), **state}, calls.metrics())
    sections, crossed, overview = answer_sections.answer(
        calls, context, None, None, interpretation=interpreted, execution=None, worked=limits,
        case_index=case_index, provision_reader=provision_reader, report=report, released=released,
        researched=researched)
    record, sources, execution = researched.whole()
    elements = response_rendering.render_sections(context, record, sources, sections=sections, cross_check=crossed,
                                                  overview=overview, time_limits=limits)
    activity = {**base(record, sources, execution), "sections": sections, "cross_check": crossed, "overview": overview}
    return elements, activity, calls.metrics()


def interrupted(held):
    """A turn that stopped after showing part of its answer, as it is saved (P27): its
    activity with the parts not finished marked so, and the answer rendered from it."""
    activity = {key: deepcopy(value) for key, value in held.items() if key != "waiting"}
    activity["sections"], activity["cross_check"], activity["overview"] = answer_sections.interrupted(
        {"sections": held["sections"], "cross_check": held["cross_check"], "overview": held["overview"]},
        held["research"], kept=held["contract"] == CONTRACT)
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
    rows = checked_rows(matter, advocate_id)
    try:
        context = TurnContext(matter, held["request"]["chat_id"], held["turn_id"], held["message"], tuple(rows),
                              documents=tuple(held["documents"]))
        if context.request != held["request"] or any(row["turn_id"] == held["turn_id"] for row in rows):
            raise ValueError("What was shown belongs to another request")
        activity = interrupted(held["activity"])
        original = context.payload()
        record = research.validate(activity["research"], activity["research"]["plan"], original)
        sources = answer_sources.build(original, record)
        elements = response_rendering.render_sections(
            original, record, sources, sections=activity["sections"], cross_check=activity["cross_check"],
            overview=activity["overview"], time_limits=calculation.validate(activity["calculation"], original))
        validate_activity(activity, original, elements)
    except (ValueError, KeyError, TypeError, SchemaViolation) as exc:
        log.warning("The unfinished parts of an answer could not be read reliably and were withdrawn: %s",
                    type(exc).__name__)
        drop_shown(store, TurnContext(matter, rows[0]["chat_id"] if rows else "", "", "", tuple(rows)))
        return store.load(matter.id)
    commit_turn(store, context, elements=elements, activities=activity,
                records=checklist.records(original, activity), metrics=held["metrics"],
                session_current=session_current)
    return store.load(matter.id)


def _validate_sections(activity, context, elements):
    """Replay of a v6 or v7 turn: its understanding, research and time limits as saved, every
    section, trim, correction, cross-check and overview bound again (answer_sections), and
    the answer rendered again exactly as it was shown."""
    if (set(activity) != _SECTIONED_FIELDS
            or activity.get("rendering_contract") != response_rendering.BY_DISPUTE_CONTRACT):
        raise ValueError("Unknown saved turn or rendering contract")
    limits = calculation.validate(activity["calculation"], context)
    record = research.validate(activity["research"], activity["research"]["plan"], context)
    sources = answer_sources.build(context, record)
    if sources != activity["sources"] or execution_record(record) != activity["execution"]:
        raise ValueError("Saved sources or operation evidence changed")
    answer_sections.validate(activity, context, record, sources, limits, kept=activity["contract"] == CONTRACT)
    rebuilt = response_rendering.render_sections(context, record, sources, sections=activity["sections"],
                                                 cross_check=activity["cross_check"], overview=activity["overview"],
                                                 time_limits=limits)
    if rebuilt != elements:
        raise ValueError("Saved response differs from its admitted rendering")
    return deepcopy(activity)


def validate_activity(activity, context, elements):
    """Replay uses the saved contract and snapshots; it never fetches newer law."""
    version = activity.get("contract") if isinstance(activity, dict) else None
    if version in SECTIONED:
        return _validate_sections(activity, context, elements)
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
    rendering = activity.get("rendering_contract") if isinstance(activity, dict) else None
    if (version not in {LEGACY_CONTRACT, AUTHORITY_CONTRACT, CALCULATION_CONTRACT, *_RELEASED}
            or set(activity) != expected_fields or rendering not in renderings):
        raise ValueError("Unknown saved turn or rendering contract")
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
    rows = checked_rows(matter, advocate_id)
    try:
        for index, row in enumerate(rows):
            original = TurnContext(matter, row["chat_id"], row["turn_id"], row["message"], rows[:index],
                                   documents=tuple(row.get("documents", ())))
            validate_activity(row["activities"], original.payload(), row["response"]["elements"])
            # From v5 the records a turn saved are exactly what its own activity gives, under
            # the checklist version they were saved under.
            if (row["activities"].get("contract") in (RECORDS_CONTRACT, *SECTIONED)
                    and row["records"] != checklist.records(original.payload(), row["activities"], contract=(
                        row["records"].get("checklist") or {}).get("contract", checklist.CONTRACT))):
                raise ValueError("Saved records differ from what the turn admitted")
    except (ValueError, KeyError, TypeError, SchemaViolation) as exc:
        raise ConversationRefused("This saved conversation could not be read reliably. "
            "Its records are unchanged.", code="saved_response_unavailable",
            committed="previously_committed") from exc
    return rows


def process(model, store, searcher, *, advocate_id, message, turn_id, chat_id=None,
            matter_id=None, expected_version=None, session_current=lambda: False,
            attempts: TurnAttemptPort | None = None, case_index=None, provision_reader=None,
            progress=None, documents=(), held_acts=None, running=lambda turn_id: False):
    if not session_current():
        raise ConversationRefused("Sign in again before continuing.", status=401)
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
    context = open_turn(store, advocate_id=advocate_id, message=message, turn_id=turn_id,
                        chat_id=chat_id, matter_id=matter_id, expected_version=expected_version,
                        documents=documents)
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
                      reserve_correction=lambda: attempts.consume_correction(identity, token))
    # What the answer shows as each part passes is saved beside the conversation then (P27),
    # and the page told how much there is to show (P26).
    holder, report = {"context": context, "shown": 0}, _reporter(progress)
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
            holder["context"] = hold_shown(store, holder["context"], held)
        except (OSError, StaleWrite, ConversationRefused, ValueError):
            # The answer goes on; its commit decides what is saved.
            log.warning("What the answer showed could not be saved beside the conversation", exc_info=True)
            return
        holder["shown"] += 1
        report("shown", shown=holder["shown"], chat_id=context.chat_id)

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
            held_acts=held_acts, shown=shown)
        validate_activity(activity, context.payload(), elements)
    except AttemptRefused as exc:
        raise _attempt_refusal(exc) from exc
    except ModelPermissionRefused:
        # Never turned into an answer here; what was shown stays saved beside the
        # conversation, and is saved with it unless this same message is sent again.
        finish("retryable", "model_permission_required")
        raise
    except ModelError as exc:
        withdraw()
        if isinstance(exc, ContextOverflow):
            why = "This conversation exceeds the current processing capacity. Your saved conversation is unchanged."
            code = "context_capacity"
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
        refusal = ConversationRefused(why, status=503, code=code,
                                     retryable=code == "response_unavailable")
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
