"""One authenticated turn owns preparation, bounded repair, release and replay.

Drafts and reviewer judgments cannot write matter facts or announce execution.
The sealed conversation owner commits the exact checked answer and its evidence
together. This initial flow performs read-only research; record editing is separate.
"""
from __future__ import annotations

from copy import deepcopy

from nm.core_engine import answer_sources, research, response_rendering, response_review
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

CONTRACT = "core_turn_v1"
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


def _withhold(calls, findings):
    categories = {finding["category"] for finding in findings}
    identity = ("G-QUOTE" if "quotation" in categories else
                "G-ATTRIB" if "attribution" in categories else "G-GROUND")
    owned = gate(identity)
    if (owned.response, owned.scope, owned.recovery) != (
            Response.WITHHOLD, Scope.TURN, Recovery.NONE):
        raise RuntimeError("The release boundary no longer matches its gate contract")
    calls.withhold(identity)


def prepare(model, context, searcher):
    """Prepare and admit one response. No persistence or external action occurs here."""
    calls = model if isinstance(model, TurnCalls) else TurnCalls(model)
    interpreted = calls.checked("core_understanding", lambda: understanding.understand(calls, context))
    plan = calls.checked("core_research_plan", lambda: research.plan(calls, context, interpreted))
    record = research.retrieve(plan, searcher, context)
    sources = answer_sources.build(context, record)
    execution = execution_record(record)

    def write():
        return response_writer.write(calls, context, record, sources,
                                     interpretation=interpreted, execution=execution)

    draft = calls.checked("core_response_writer", write)

    def review():
        return response_review.review(calls, context, record, sources, draft, execution=execution)

    reviewed = calls.checked("core_response_review", review)
    if not reviewed["accepted"]:
        try:
            draft = calls.correct("core_response_writer", write,
                                  mismatch=reviewed["proposal"]["findings"],
                                  rejected=draft["proposal"])
            reviewed = calls.checked("core_response_review", review)
        except (CorrectionUnavailable, SchemaViolation):
            _withhold(calls, reviewed["proposal"]["findings"])
        if not reviewed["accepted"]:
            _withhold(calls, reviewed["proposal"]["findings"])
    elements = response_rendering.render(context, record, sources, draft, reviewed, execution=execution)
    activity = {"contract": CONTRACT, "interpretation": interpreted, "research": record,
                "sources": sources, "draft": draft, "review": reviewed, "execution": execution,
                "rendering_contract": response_rendering.CONTRACT}
    return elements, activity, calls.metrics()


def validate_activity(activity, context, elements):
    """Replay uses the saved contract and snapshots; it never fetches newer law."""
    if (set(activity) != _ACTIVITY_FIELDS or activity["contract"] != CONTRACT
            or activity["rendering_contract"] != response_rendering.CONTRACT):
        raise ValueError("Unknown saved turn or rendering contract")
    record = research.validate(activity["research"], activity["research"]["plan"], context)
    sources = answer_sources.build(context, record)
    if sources != activity["sources"] or execution_record(record) != activity["execution"]:
        raise ValueError("Saved sources or operation evidence changed")
    rebuilt = response_rendering.render(context, record, sources, activity["draft"],
        activity["review"], execution=activity["execution"])
    if rebuilt != elements:
        raise ValueError("Saved response differs from its admitted rendering")
    return deepcopy(activity)


def saved_rows(matter, advocate_id):
    rows = checked_rows(matter, advocate_id)
    try:
        for index, row in enumerate(rows):
            original = TurnContext(matter, row["chat_id"], row["turn_id"], row["message"], rows[:index])
            validate_activity(row["activities"], original.payload(), row["response"]["elements"])
    except (ValueError, KeyError, TypeError, SchemaViolation) as exc:
        raise ConversationRefused("This saved conversation could not be read reliably. "
            "Its records are unchanged.", code="saved_response_unavailable",
            committed="previously_committed") from exc
    return rows


def process(model, store, searcher, *, advocate_id, message, turn_id, chat_id=None,
            matter_id=None, expected_version=None, session_current=lambda: False,
            attempts: TurnAttemptPort | None = None):
    if not session_current():
        raise ConversationRefused("Sign in again before continuing.", status=401)
    context = open_turn(store, advocate_id=advocate_id, message=message, turn_id=turn_id,
                        chat_id=chat_id, matter_id=matter_id, expected_version=expected_version)
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

    calls = TurnCalls(model, correction_used=claim["correction_used"],
                      reserve_correction=lambda: attempts.consume_correction(identity, token))
    try:
        elements, activity, metrics = prepare(calls, context.payload(), searcher)
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
            why = "I could not provide a sufficiently reliable answer to this message. Your saved conversation is unchanged."
            code = "answer_withheld"
        else:
            why = "The response could not be completed at present. Your saved conversation is unchanged."
            code = "response_unavailable"
        refusal = ConversationRefused(why, status=503, code=code,
                                     retryable=code == "response_unavailable")
        finish("retryable" if refusal.retryable else "terminal", code)
        refusal.metrics = calls.metrics()
        raise refusal from exc
    try:
        response = commit_turn(store, context, elements=elements, activities=activity,
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
