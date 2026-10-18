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

from concurrent.futures import ThreadPoolExecutor

from nm.core_engine import answer_sources, calculation, checklist, research, response_authorities
from nm.core_engine import response_rendering
from nm.core_engine import response_review
from nm.core_engine import response_writer, understanding
from nm.core_engine.calls import CorrectionUnavailable, ReleaseWithheld, TurnCalls
from nm.core_engine.conversation import (
    ConversationRefused, TurnContext, checked_rows, commit_turn, open_turn,
    digest,
)
from nm.shared.gates_contracts import Recovery, Response, Scope, gate
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.egress_contracts import EgressRefused
from nm.shared.model_port import ContextOverflow, ModelError, SchemaViolation
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
CONTRACT = "core_turn_v5"
_RELEASED = (RELEASE_CONTRACT, CONTRACT)
EXECUTION = "core_read_only_execution_v1"
_ACTIVITY_FIELDS = {"contract", "interpretation", "research", "sources", "draft",
                    "review", "execution", "rendering_contract"}


def execution_record(record):
    """Receipts describe what this code did, never whether the request is fulfilled."""
    searches = []
    for work in record["plan"]["work"]:
        identity = work["id"]
        if identity in record["failures"]:
            state = "failed"
        elif identity in record["searches"]:
            state = "partial" if record["searches"][identity]["issues"] else "evaluated"
        else:
            state = "not_requested"
        searches.append({"work_id": identity, "state": state})
    return {"contract": EXECUTION, "operations": [], "record_changes": [],
            "external_actions": [], "searches": searches, "persistence": "not_yet_committed"}


def _withhold(calls, findings, dated=()):
    categories = {finding["category"] for finding in findings}
    identity = ("G-QUOTE" if "quotation" in categories else
                "G-ATTRIB" if "attribution" in categories else "G-GROUND")
    owned = gate(identity)
    if (owned.response, owned.scope, owned.recovery) != (
            Response.WITHHOLD, Scope.TURN, Recovery.NONE):
        raise RuntimeError("The release boundary no longer matches its gate contract")
    # The categories are the review's fixed names, never its words about the draft.
    try:
        calls.withhold(f"{identity}: {', '.join(sorted(categories))}")
    except ReleaseWithheld as exc:
        # What the check found, for the advocate alone (owner decision, 17 Oct 2026);
        # the attempt's diagnosis and the log keep only the fixed names.
        exc.found = response_rendering.found_words(
            [f for f in findings if not any(f is d for d in dated)], dated, where="the answer")
        raise


def _hold(calls, draft, reviewed, undated, findings):
    """After the rewrites (owner decision, 17 Oct 2026): what is still found inside the
    sections of a several-dispute answer holds back those sections under G-SECTION, and
    the rest is released; anything else withholds the turn. The date findings are kept
    with the release, as the date check reads today's date."""
    parts = response_rendering.held_sections(draft, reviewed, undated)
    if not parts:
        _withhold(calls, findings, dated=undated)
    owned = gate("G-SECTION")
    if (owned.response, owned.scope, owned.recovery) != (Response.WITHHOLD, Scope.NEED, Recovery.ADVOCATE):
        raise RuntimeError("The section boundary no longer matches its gate contract")
    return {"parts": parts, "date_findings": deepcopy(undated)}


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


def prepare(model, context, searcher, *, case_index=None, provision_reader=None, progress=None,
            held_acts=None):
    """Prepare and admit one response. No persistence or external action occurs here."""
    report = _reporter(progress)
    calls = model if isinstance(model, TurnCalls) else TurnCalls(model)
    report("understanding")
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
    # Time limits are worked out beside the search, only where research is needed.
    with ThreadPoolExecutor(max_workers=1) as pool:
        working = (pool.submit(calculation.work_out, calls, context, held_acts)
                   if held_acts is not None and _needs_research(plan) else None)
        record = research.retrieve(plan, searcher, context, model=calls, progress=report)
        limits = working.result() if working is not None else calculation.skipped()
    time_limits = calculation.for_answer(limits)
    sources = answer_sources.build(context, record)
    execution = execution_record(record)

    # Sections that passed code's checks when a draft's shape was refused, and what code
    # found in the others: the shape correction keeps the first as written and rewrites
    # only the rest (owner, 18 Oct 2026). Parts are numbered as the writer lays them out.
    layout = response_writer.parts(record)
    passed, found, held_back = {}, {}, {}

    def write(keep=None):
        try:
            return response_writer.write(calls, context, record, sources,
                                         interpretation=interpreted, execution=execution,
                                         keep=keep if keep is not None else passed or None,
                                         time_limits=time_limits, skip=held_back)
        except SchemaViolation as exc:
            passed.clear()
            passed.update(getattr(exc, "kept", None) or {})
            found.clear()
            found.update(getattr(exc, "found", None) or {})
            raise

    report("writing")
    try:
        draft = calls.checked("core_response_writer", write)
    except (CorrectionUnavailable, SchemaViolation):
        # G-SECTION for code's own checks (owner, 18 Oct 2026: "withhold only the failed
        # part and pass the remaining part"): a section still refused after the rewrites NM
        # may make is held back for this turn, and the sections that passed go on. With no
        # dispute's section passing, nothing is released.
        if not any(layout[index]["dispute_id"] is not None for index in passed):
            raise
        held_back.update({index: found.get(index, "checks") for index in range(len(layout))
                          if index not in passed})
        draft = write(dict(passed))  # every section left is one already checked
    report("checking_authorities")
    authorities = response_authorities.check(context, record, sources, draft,
        case_index=case_index, provision_reader=provision_reader)
    unwritten = [{"dispute_id": layout[index]["dispute_id"], "found": held_back[index]}
                 for index in sorted(held_back)]

    def review():
        return response_review.review(calls, context, record, sources, draft, execution=execution,
                                      authority_evidence=authorities, time_limits=time_limits,
                                      held_back=[entry["dispute_id"] for entry in unwritten] or None)

    report("reviewing")
    reviewed = calls.checked("core_response_review", review)
    # Code's own check: the answer states no date it worked out itself (owner, 15 Oct 2026).
    undated = response_writer.dates_not_given(draft, context, sources, time_limits)
    # What the review or the date check finds is rewritten and the whole answer reviewed
    # again; when that review still finds a problem, once more (owner decision, 17 Oct
    # 2026). What is still found after that holds back its sections, or the turn.
    release = None
    # The last draft a review saw, with its authority checks, that review and the date
    # findings: what is held back or withheld is always judged on a draft and its own review.
    checked = (draft, authorities, reviewed, undated)
    while not reviewed["accepted"] or undated:
        findings = ([] if reviewed["accepted"] else reviewed["proposal"]["findings"]) + undated
        try:
            report("revising")
            # Parts with no finding are kept as written; the rest are rewritten. A section
            # held back by code's checks is not written again in this turn.
            position = {part["dispute_id"]: index for index, part in enumerate(layout)}
            keep = {position[part["dispute_id"]]: part
                    for part in response_writer.kept_parts(draft, findings).values()}
            draft = calls.correct("core_response_writer", lambda: write(keep),
                                  mismatch=findings, rejected=draft["proposal"], asked_by_review=True)
            authorities = response_authorities.check(context, record, sources, draft,
                case_index=case_index, provision_reader=provision_reader)
            report("reviewing")
            reviewed = calls.checked("core_response_review", review)
        except (CorrectionUnavailable, SchemaViolation):
            draft, authorities, reviewed, undated = checked
            release = _hold(calls, draft, reviewed, undated, findings)
            break
        undated = response_writer.dates_not_given(draft, context, sources, time_limits)
        checked = (draft, authorities, reviewed, undated)
    if unwritten:
        # The release names the sections code's checks held back (rendering v13).
        release = {**(release or {"parts": [], "date_findings": []}), "unwritten": unwritten}
    elements = response_rendering.render(context, record, sources, draft, reviewed,
        execution=execution, authority_evidence=authorities, time_limits=limits, held=release)
    activity = {"contract": CONTRACT, "interpretation": interpreted, "research": record,
                "sources": sources, "draft": draft, "review": reviewed, "execution": execution,
                "rendering_contract": response_rendering.CONTRACT,
                "authority_evidence": authorities, "calculation": limits, "release": release}
    return elements, activity, calls.metrics()


def validate_activity(activity, context, elements):
    """Replay uses the saved contract and snapshots; it never fetches newer law."""
    version = activity.get("contract")
    expected_fields = (_ACTIVITY_FIELDS if version == LEGACY_CONTRACT else
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
                   response_rendering.CONTRACT})
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
            # From v5 the records a turn saved are exactly what its own activity gives.
            if (row["activities"].get("contract") == CONTRACT
                    and row["records"] != checklist.records(original.payload(), row["activities"])):
                raise ValueError("Saved records differ from what the turn admitted")
    except (ValueError, KeyError, TypeError, SchemaViolation) as exc:
        raise ConversationRefused("This saved conversation could not be read reliably. "
            "Its records are unchanged.", code="saved_response_unavailable",
            committed="previously_committed") from exc
    return rows


def process(model, store, searcher, *, advocate_id, message, turn_id, chat_id=None,
            matter_id=None, expected_version=None, session_current=lambda: False,
            attempts: TurnAttemptPort | None = None, case_index=None, provision_reader=None,
            progress=None, documents=(), held_acts=None):
    if not session_current():
        raise ConversationRefused("Sign in again before continuing.", status=401)
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
    binding = digest({"request": context.request, "version": context.matter.version,
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
    try:
        elements, activity, metrics = prepare(calls, context.payload(), searcher,
            case_index=case_index, provision_reader=provision_reader, progress=progress,
            held_acts=held_acts)
        validate_activity(activity, context.payload(), elements)
    except AttemptRefused as exc:
        raise _attempt_refusal(exc) from exc
    except ModelPermissionRefused:
        finish("retryable", "model_permission_required")
        raise
    except ModelError as exc:
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
        response = commit_turn(store, context, elements=elements, activities=activity,
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
