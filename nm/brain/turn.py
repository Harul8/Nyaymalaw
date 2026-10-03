"""The authenticated chat turn, saved atomically with its conversation."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import Lock
from time import perf_counter

from nm.brain.continuation import continuation_indexes, continue_conversation
from nm.brain.conversation import (
    Conversation,
    IncompleteConversation,
    Message,
    OpeningCandidate,
    interpret,
    repair_opening,
)
from nm.brain.dispute_state import proposed_disputes
from nm.brain.dispute_verification import verify_disputes
from nm.brain.disputes import extract_disputes
from nm.brain.history import from_turns, released_older_turns
from nm.brain.legal_requirements import (
    decompose,
    read_requirements,
    verify_requirements,
)
from nm.brain.material import extract_details
from nm.brain.material_state import material_record, sourced_detail_for_display
from nm.brain.material_verification import verify_material_grounding
from nm.brain.requirements_state import requirements_record
from nm.brain.source_snapshots import source_snapshots
from nm.brain.work_state import project_work, seal_progress
from nm.shared.model_port import (
    ConfigurationError,
    ContextOverflow,
    ModelError,
    OutputTruncated,
    ProviderUnavailable,
    SchemaViolation,
)
from nm.shared.store_port import StaleWrite, StorePort
from nm.work_the_file.matter_contracts import Matter, MatterId


class BrainRefused(Exception):
    def __init__(self, status: int, why: str, *, committed: str = "not_committed",
                 retryable: bool = True, code: str = "brain_refused") -> None:
        super().__init__(why)
        self.status = status
        self.why = why
        self.committed = committed
        self.retryable = retryable
        self.code = code


@dataclass(frozen=True)
class BrainTurn:
    advocate_id: str
    message: str
    turn_id: str
    matter_id: str | None = None
    chat_id: str | None = None
    expected_version: int | None = None
    offer: dict | None = None


@dataclass(frozen=True)
class BrainOutput:
    response: dict

    def as_dict(self) -> dict:
        return dict(self.response)


class _CountedModel:
    """Count actual calls, including a conditional correction in either reader."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.calls = 0
        self.provider_retries = 0
        self.receipts = []
        self.lock = Lock()

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        started = perf_counter()
        logger = logging.getLogger(__name__)
        with self.lock:
            self.calls += 1
            ordinal = self.calls
        logger.info("Model call %s started: %s", ordinal, prompt.operation)
        result = None
        failure = None
        try:
            result = self.inner.structured(prompt, schema, tier,
                                           max_tokens=max_tokens)
        except ModelError as exc:
            failure = type(exc).__name__
            with self.lock:
                self.provider_retries += exc.retries
            raise
        finally:
            elapsed = int((perf_counter() - started) * 1000)
            receipt = {"operation": prompt.operation, "latency_ms": elapsed,
                       "tier": tier.value,
                       "model": result.model if result else "",
                       "state": failure or "ok",
                       "tokens_in": result.usage.tokens_in if result else 0,
                       "tokens_out": result.usage.tokens_out if result else 0}
            with self.lock:
                self.receipts.append(receipt)
                if result is not None:
                    self.provider_retries += result.retries
            logger.info("Model call %s finished: %s, %sms, %s", ordinal,
                        prompt.operation, elapsed, failure or "ok")
        return result

    def metrics(self) -> dict:
        return {"llm_calls": self.calls, "provider_retries": self.provider_retries,
                "model_calls": list(self.receipts)}


def _digest(value: dict) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def chat_matter_id(advocate_id: str, chat_id: str) -> MatterId:
    return MatterId("mat_" + _digest({"advocate": advocate_id, "chat": chat_id})[:32])


def _saved_reply(matter: Matter, turn_id: str, offer_digest: str) -> dict | None:
    matches = [row for row in matter.brain_chat if row.get("turn_id") == turn_id]
    if not matches:
        return None
    if len(matches) != 1 or matches[0].get("offer_digest") != offer_digest:
        raise BrainRefused(409, "This turn ID already names different instructions")
    response = matches[0].get("response")
    if not isinstance(response, dict) or response.get("turn_id") != turn_id:
        raise BrainRefused(409, "The saved reply could not be verified")
    metrics = dict(response.get("metrics") or {})
    metrics["llm_calls"] = 0
    metrics["provider_retries"] = 0
    metrics["model_calls"] = []
    message = matches[0].get("message")
    if not isinstance(message, str):
        raise BrainRefused(409, "The saved message could not be verified")
    saved_material = response.get("material", [])
    if not isinstance(saved_material, list):
        raise BrainRefused(409, "The saved material could not be verified")
    material = []
    for proposal in saved_material:
        if not isinstance(proposal, dict):
            raise BrainRefused(409, "The saved material could not be verified")
        if proposal.get("kind") == "dispute":
            material.append(proposal)
        else:
            safe = sourced_detail_for_display(proposal, message)
            if safe is None:
                raise BrainRefused(409, "The saved material source could not be verified")
            material.append(safe)
    return {**response, "replayed": True, "committed": "replayed",
            "material": material,
            "metrics": metrics,
            "matter_id": str(matter.id) if matter.brain_ready else None,
            "matter_version": matter.version if matter.brain_ready else None}


def _current_records(store: StorePort, matter: Matter) -> tuple[Conversation, dict, dict]:
    older = released_older_turns(store, matter)
    rows = [*older, *matter.brain_chat]
    conversation = from_turns(
        rows, state="ok", matter_id=str(matter.id) if matter.brain_ready else None,
        current_work=(matter.brain_chat[-1].get("active_work_after", "")
                      if matter.brain_chat else ""))
    older_context = from_turns(older, state="ok").messages
    progress = project_work(matter, prior_conversation=older_context)
    if progress["state"] != "ok":
        raise IncompleteConversation("The saved work progress is incomplete")
    disputes = proposed_disputes(matter, prior_conversation=older_context)
    if disputes["state"] != "ok":
        raise IncompleteConversation("The saved dispute context is incomplete")
    details = material_record(matter, disputes=disputes,
                              prior_conversation=older_context)
    if details["state"] != "ok":
        raise IncompleteConversation("The saved material context is incomplete")
    return (replace(conversation, open_disputes=tuple(disputes["rows"]),
                    open_material=tuple(details["rows"]), progress=progress,
                    current_work=progress["active_work"]), disputes, details)


def _history(store: StorePort, matter: Matter) -> Conversation:
    return _current_records(store, matter)[0]


def _reply(plan) -> tuple[str, bool, bool]:
    needs_work = any(item.next_step == "legal_work" for item in plan.items)
    parts = []
    asked = False
    for item in sorted(plan.items, key=lambda row: row.priority != "urgent"):
        if item.next_step == "legal_work":
            parts.append(item.reply.strip())
        elif (item.next_step == "answer" and
                (not needs_work
                 or (item.relation == "aside" and item.matter_scope == "none"))):
            parts.append(item.reply.strip())
        elif item.next_step == "clarify":
            parts.append(item.clarification.strip())
            asked = True
    return "\n\n".join(parts), needs_work, asked


def _continuation_elements(plan, continuation: dict) -> list[dict]:
    units = {unit["request_index"]: unit for unit in continuation["units"]}
    expected = set(continuation_indexes(plan))
    elements = []
    for index, item in sorted(enumerate(plan.items),
                              key=lambda pair: pair[1].priority != "urgent"):
        unit = units.get(index)
        if unit is not None:
            question_blocks = {row["block_id"] for row in unit["questions"]}
            for block in unit["blocks"]:
                sources = source_snapshots(block["references"])
                elements.append({
                    "kind": "question" if block["id"] in question_blocks else "finding",
                    "text": block["text"], "thread": None, "by_when": None,
                    "no_deadline_reason": None, "signal": "none",
                    "collapsible": False, "disclosure": False,
                    "refs": [source["locator"] for source in sources],
                    "source": sources[0] if sources else None, "sources": sources,
                    "section": "needed" if block["id"] in question_blocks else "answer",
                    "continuation_request_index": index,
                    "continuation_block_id": block["id"]})
        else:
            text = ("I could not finish a checked response to this part of your "
                    "request. Your message is saved; ask me to continue this "
                    "work without resending the account."
                    if index in expected else item.reply.strip())
            elements.append({"kind": "finding", "text": text, "refs": [],
                             "source": None, "section": "answer",
                             "collapsible": False, "disclosure": index in expected})
    return elements


def _read_material(model, conversation: Conversation, latest: str, turn_id: str):
    """Read disputes, then details that can link to newly identified issues."""
    arguments = {"earlier": conversation.messages, "latest": latest,
                 "current_matter_id": conversation.current_matter_id}
    disputes = verify_disputes(
        model,
        candidates=extract_disputes(
            model, prior_disputes=conversation.open_disputes, **arguments),
        earlier=conversation.messages, latest=latest,
        active_disputes=conversation.open_disputes)
    active = {row["id"]: row for row in conversation.open_disputes}
    for index, candidate in enumerate(disputes, start=1):
        if not (candidate.matter_scope == "current" or
                (candidate.matter_scope == "proposed" and
                 conversation.current_matter_id is None)):
            continue
        for prior_id in candidate.related_dispute_ids:
            active.pop(prior_id, None)
        if candidate.relation != "withdraws":
            row = candidate.recorded(turn_id, index)
            active[row["id"]] = row
    details = extract_details(
        model, disputes=tuple(active.values()),
        prior_material=conversation.open_material, **arguments)
    return (*disputes, *details)


def _legal_reads(model, search, *, conversation: Conversation,
                 disputes: dict, material: dict, current: dict) -> list[dict]:
    """Research changed identified disputes, keeping model and corpus failures visible."""
    due = tuple(row for row in disputes["rows"]
                if current["status_by_dispute"].get(row["id"]) != "ok"
                and row.get("identification") == "identified")
    if not due:
        return []
    material_by_dispute = {
        row["id"]: [*material["by_dispute"].get(row["id"], []),
                    *material["matter"]]
        for row in due
    }
    fingerprints = current["fingerprints"]

    def unavailable(row: dict, reason: str,
                    queries: tuple[str, ...] = ()) -> dict:
        return {"dispute_id": row["id"],
                "fingerprint": fingerprints[row["id"]],
                "state": "unavailable", "rows": [],
                "queries": list(queries), "diagnostics": [reason]}

    local_errors = (SchemaViolation, ContextOverflow, OutputTruncated)
    planning_errors: dict[str, str] = {}
    try:
        queries = decompose(
            model, disputes=due, material_by_dispute=material_by_dispute,
            conversation=conversation.messages)
    except ModelError as exc:
        reason = f"Legal search planning did not finish ({type(exc).__name__})"
        if not isinstance(exc, local_errors) or len(due) == 1:
            return [unavailable(row, reason) for row in due]
        queries = {}
        for index, row in enumerate(due):
            dispute_id = row["id"]
            try:
                queries.update(decompose(
                    model, disputes=(row,),
                    material_by_dispute={dispute_id: material_by_dispute[dispute_id]},
                    conversation=conversation.messages))
            except ModelError as isolated:
                reason = ("Legal search planning did not finish "
                          f"({type(isolated).__name__})")
                planning_errors[dispute_id] = reason
                if not isinstance(isolated, local_errors):
                    planning_errors.update(
                        (remaining["id"], reason) for remaining in due[index + 1:])
                    break

    results = {}
    for row in due:
        dispute_id = row["id"]
        if dispute_id not in queries:
            continue
        try:
            started = perf_counter()
            result = search.search_dispute(row, queries[dispute_id])
            logging.getLogger(__name__).info("Legal corpus search finished: %sms",
                                            int((perf_counter() - started) * 1000))
            if (not isinstance(result, dict)
                    or result.get("state") not in ("ok", "partial", "unavailable")
                    or not isinstance(result.get("candidates"), list)):
                raise ValueError("search returned no reliable state")
            results[dispute_id] = result
        except Exception:  # noqa: BLE001 -- search is a fallible local adapter
            results[dispute_id] = {
                "state": "unavailable", "candidates": [],
                "diagnostics": ["Legal corpus search did not finish"]}
    planned = tuple(row for row in due if row["id"] in queries)
    reading_errors: dict[str, str] = {}
    found = {}
    if planned:
        try:
            found = read_requirements(
                model, disputes=planned,
                material_by_dispute={row["id"]: material_by_dispute[row["id"]]
                                     for row in planned},
                search_results=results, conversation=conversation.messages)
        except ModelError as exc:
            reason = f"Legal passage reading did not finish ({type(exc).__name__})"
            if not isinstance(exc, local_errors) or len(planned) == 1:
                reading_errors.update((row["id"], reason) for row in planned)
            else:
                for index, row in enumerate(planned):
                    dispute_id = row["id"]
                    try:
                        found.update(read_requirements(
                            model, disputes=(row,),
                            material_by_dispute={
                                dispute_id: material_by_dispute[dispute_id]},
                            search_results={dispute_id: results[dispute_id]},
                            conversation=conversation.messages))
                    except ModelError as isolated:
                        reason = ("Legal passage reading did not finish "
                                  f"({type(isolated).__name__})")
                        reading_errors[dispute_id] = reason
                        if not isinstance(isolated, local_errors):
                            reading_errors.update(
                                (remaining["id"], reason)
                                for remaining in planned[index + 1:])
                            break
    reads = []
    verification_outage = None
    for row in due:
        dispute_id = row["id"]
        if dispute_id not in queries:
            reads.append(unavailable(
                row, planning_errors.get(dispute_id, "Legal search planning did not finish")))
            continue
        if dispute_id not in found:
            reads.append(unavailable(
                row, reading_errors.get(dispute_id, "Legal passage reading did not finish"),
                queries[dispute_id]))
            continue
        if verification_outage is not None:
            reads.append(unavailable(row, verification_outage, queries[dispute_id]))
            continue
        try:
            verification = verify_requirements(
                model, disputes=(row,),
                material_by_dispute={dispute_id: material_by_dispute[dispute_id]},
                proposed={dispute_id: found[dispute_id]},
                conversation=conversation.messages)
        except ModelError as exc:
            logging.getLogger(__name__).warning(
                "Legal source verification rejected dispute %s: %s",
                dispute_id, exc)
            reason = ("Legal source verification did not finish "
                      f"({type(exc).__name__})")
            reads.append(unavailable(row, reason, queries[dispute_id]))
            if isinstance(exc, (ProviderUnavailable, ConfigurationError)):
                verification_outage = reason
            continue
        verified = verification.rows[dispute_id]
        coverage = verification.coverage[dispute_id]
        if verification.outage:
            verification_outage = "Legal source verification could not be completed"
        reads.append({"dispute_id": dispute_id,
                      "fingerprint": fingerprints[dispute_id],
                      "state": ("partial" if coverage["state"] != "ok"
                                and results[dispute_id]["state"] == "ok"
                                else results[dispute_id]["state"]),
                      "rows": verified,
                      "verification": "source_support_v4",
                      "coverage": coverage,
                      "queries": list(queries[dispute_id]),
                      "diagnostics": [
                          *results[dispute_id].get("diagnostics", []),
                          *coverage["diagnostics"],
                          *(["Unsupported legal items or citations were withheld"]
                            if verified != found[dispute_id] else [])]})
    return reads


class BrainService:
    def __init__(self, store: StorePort, model, legal_search=None, *,
                 session_current=None) -> None:
        self.store = store
        self.model = model
        self.legal_search = legal_search
        self.session_current = session_current

    def run(self, turn: BrainTurn) -> BrainOutput:
        if not turn.advocate_id.strip() or not turn.message.strip() or not turn.turn_id.strip():
            raise BrainRefused(
                422, "An attributed, nonempty turn with a stable turn ID is required")
        if turn.chat_id is not None and not turn.chat_id.strip():
            raise BrainRefused(422, "Chat ID must not be empty")
        chat_id = turn.chat_id or (turn.turn_id if turn.matter_id is None else None)
        expected_id = chat_matter_id(turn.advocate_id, chat_id) if chat_id else None
        if turn.matter_id and turn.chat_id and turn.matter_id != expected_id:
            raise BrainRefused(409, "The chat and matter identities disagree")
        matter_id = MatterId(turn.matter_id) if turn.matter_id else expected_id
        offer_digest = _digest(turn.offer or {"message": turn.message,
                                               "matter_id": turn.matter_id,
                                               "chat_id": turn.chat_id})
        matter = self.store.load(matter_id)
        persisted = matter is not None
        if matter is not None and matter.advocate_id != turn.advocate_id:
            raise BrainRefused(404, "No such conversation")
        if matter is None:
            if turn.matter_id or turn.chat_id:
                raise BrainRefused(404, "No such conversation")
            matter = Matter(id=matter_id, advocate_id=turn.advocate_id,
                            title="Pending conversation", brain_ready=False)
        else:
            prior = _saved_reply(matter, turn.turn_id, offer_digest)
            if prior is not None:
                return BrainOutput(prior)
        if (turn.expected_version is not None and matter.brain_ready
                and turn.expected_version != matter.version):
            raise BrainRefused(409, "The matter changed; reload it before sending another message",
                               code="stale_version")
        if turn.turn_id in matter.turns_applied:
            raise BrainRefused(409, "This turn already belongs to an earlier response")
        counted_model = _CountedModel(self.model)
        try:
            conversation = (_history(self.store, matter) if persisted else
                            Conversation((), progress=project_work(matter)))
            plan = interpret(counted_model, conversation, turn.message)
            candidates = (_read_material(counted_model, conversation,
                                         turn.message, turn.turn_id)
                if plan.material_review or plan.opening.ready
                else ())
            grounded = verify_material_grounding(
                counted_model, candidates=candidates, opening=plan.opening,
                earlier=conversation.messages, latest=turn.message)
            candidates = (tuple(candidate for candidate in candidates
                                if candidate.kind == "dispute") + grounded.details)
        except IncompleteConversation as exc:
            logging.getLogger(__name__).warning("Saved conversation validation failed: %s", exc)
            raise BrainRefused(
                409, "The saved conversation or its sources could not be verified. "
                "Reload this conversation; if this continues, contact the administrator."
            ) from exc
        except ContextOverflow as exc:
            raise BrainRefused(
                413, "This conversation exceeds the configured model's context "
                "limit. Start a new chat with a shorter self-contained brief; "
                "retrying this unchanged turn will not help.",
                retryable=False) from exc
        except ModelError as exc:
            logging.getLogger(__name__).warning(
                "Conversation analysis was rejected before saving: %s", exc)
            if isinstance(exc, ConfigurationError):
                why = ("The AI service is not configured for this analysis. "
                       "Please contact the application administrator.")
                retryable = False
            elif isinstance(exc, ProviderUnavailable):
                why = ("The AI service could not be reached. Please try again "
                       "later; if this persists, contact the administrator.")
                retryable = True
            elif isinstance(exc, SchemaViolation):
                why = ("NM could not validate the analysis returned by the AI "
                       "service. Please try again later.")
                retryable = True
            elif isinstance(exc, OutputTruncated):
                why = ("The AI service stopped before finishing its analysis. "
                       "Please contact the application administrator.")
                retryable = False
            else:
                why = "Analysis did not finish. Please try again later."
                retryable = True
            raise BrainRefused(503, why, retryable=retryable) from exc
        reply, needs_work, asked = _reply(plan)
        if not reply.strip():
            raise BrainRefused(503, "The message produced no usable response")
        material = [candidate.recorded(turn.turn_id, index)
                    for index, candidate in enumerate(candidates, start=1)]
        for item in material:
            if item["kind"] != "dispute":
                item["grounding"] = "advocate_semantic_v1"
        opening_supported = grounded.opening_supported
        opening = plan.opening
        if opening.ready and not opening_supported:
            alternatives = []
            try:
                alternatives.append(repair_opening(
                    counted_model, conversation, turn.message, opening,
                    grounded.opening_reason))
            except (ModelError, ContextOverflow) as exc:
                logging.getLogger(__name__).warning(
                    "Opening repair was unavailable: %s", exc)
            # A malformed party prefix must not force a generic heading if
            # its subject can still be checked independently.
            subject = opening.title_parts()[1].strip()
            if subject and subject != opening.title:
                alternatives.append(OpeningCandidate(
                    True, subject, opening.summary, "", subject))
            for proposal in alternatives:
                try:
                    checked = verify_material_grounding(
                        counted_model, candidates=(), opening=proposal,
                        earlier=conversation.messages, latest=turn.message)
                except (ModelError, ContextOverflow) as exc:
                    logging.getLogger(__name__).warning(
                        "Opening correction could not be checked: %s", exc)
                    continue
                if checked.opening_supported:
                    opening = proposal
                    opening_supported = True
                    break
        if not opening_supported:
            opening = OpeningCandidate(True, "Matter",
                                       "Matter opened from the advocate's account.")
        ready = matter.brain_ready or opening.ready
        title = matter.title if matter.brain_ready or not opening.ready else opening.title
        summary = (matter.brain_opening_summary if matter.brain_ready or not opening.ready
                   else opening.summary)
        now = datetime.now(timezone.utc).isoformat()
        element = {"kind": "question" if asked and not needs_work else
                   "ground" if needs_work else "finding",
                   "text": reply, "thread": None, "by_when": None,
                   "no_deadline_reason": None, "signal": "none", "collapsible": False,
                   "disclosure": needs_work, "refs": [], "source": None,
                   "section": "needed" if needs_work or asked else "answer"}
        response = {"turn_id": turn.turn_id, "chat_id": chat_id,
                    "matter_id": str(matter.id) if ready else None,
                    "route": "matter" if ready else "non_matter",
                    "mode": "short_question" if asked else "explanation",
                    "mode_statement": "conversation response", "blocked": needs_work,
                    "blocked_reason": "Legal work needs checked support" if needs_work else None,
                    "elements": [element], "material": material,
                    "material_coverage": {
                        "state": "partial" if grounded.rejected_details else "ok",
                        "withheld_details": grounded.rejected_details,
                        "opening_fallback": not opening_supported},
                    "requirements_read": [],
                    "metrics": counted_model.metrics(),
                    "replayed": False, "committed": "committed", "input_admitted": False,
                    "matter_version": matter.version + 1 if ready else None,
                    "briefing": {}, "board_changes": [], "at": now, "composed": []}
        row = {"turn_id": turn.turn_id, "advocate_id": turn.advocate_id,
               "message": turn.message, "response": response,
               "offer_digest": offer_digest, "at": now,
               "active_work_after": plan.active_work_after,
               "elements": response["elements"], "committed": True,
               "release_state": "released", "matter_id": str(matter.id)}
        updated = replace(matter, title=title, brain_ready=ready,
                          brain_opening_summary=summary,
                          brain_chat=(*matter.brain_chat, row),
                          last_activity=now[:10], version=matter.version + 1)
        disputes = None
        details = None
        try:
            if candidates or ready or continuation_indexes(plan):
                current_conversation, disputes, details = _current_records(
                    self.store, updated)
                if self.legal_search is not None and ready and (
                        candidates or plan.material_review or needs_work):
                    current = requirements_record(
                        updated, disputes=disputes, material=details)
                    reads = _legal_reads(
                        counted_model, self.legal_search,
                        conversation=replace(
                            current_conversation,
                            messages=(*conversation.messages,
                                      Message(turn.turn_id, "advocate", turn.message))),
                        disputes=disputes, material=details, current=current)
                    accepted = []
                    isolated_turn = replace(updated, brain_chat=(row,))
                    for read in reads:
                        response["requirements_read"] = [read]
                        checked = requirements_record(
                            isolated_turn, disputes=disputes, material=details)
                        dispute_id = read["dispute_id"]
                        if (checked["state"] == "ok"
                                and checked["status_by_dispute"].get(dispute_id)
                                == read["state"]
                                and checked["by_dispute"].get(dispute_id)
                                == read["rows"]):
                            accepted.append(read)
                        else:
                            logging.getLogger(__name__).warning(
                                "Legal read projection rejected dispute %s", dispute_id)
                    response["requirements_read"] = accepted
                    response["metrics"] = counted_model.metrics()
            if continuation_indexes(plan):
                checked = requirements_record(
                    updated, disputes=disputes, material=details)
                continuation = continue_conversation(
                    counted_model, conversation=conversation, latest=turn.message,
                    latest_turn_id=turn.turn_id, plan=plan, disputes=disputes,
                    material=details, requirements=checked,
                    progress=conversation.progress).as_dict()
                continuation = seal_progress(
                    continuation, matter_id=str(matter.id), turn_id=turn.turn_id,
                    plan=plan, prior_progress=conversation.progress)
                elements = _continuation_elements(plan, continuation)
                response["continuation"] = continuation
                response["elements"] = row["elements"] = elements
                response["blocked"] = any(
                    item["state"] != "ok" for item in continuation["coverage"])
                response["blocked_reason"] = (
                    "Part of the requested response could not be checked"
                    if response["blocked"] else None)
                response["mode"] = ("short_question" if any(
                    unit["questions"] for unit in continuation["units"])
                    else "explanation")
            if grounded.rejected_details:
                response["elements"].append({"kind": "finding", "text": (
                    "Some proposed details could not be confirmed against "
                    "your words, so they were not added to the matter record. "
                    "Your message is saved; the missing coverage remains visible."),
                    "refs": [], "source": None, "section": "answer",
                    "collapsible": False, "disclosure": True})
            # Release one final reply snapshot. Notices are part of the visible
            # transcript, so validate after composing them, before committing.
            row["elements"] = response["elements"]
            progress = project_work(updated, prior_conversation=conversation.messages)
            if progress["state"] != "ok":
                raise IncompleteConversation("The new work progress cannot be verified")
            # This compatibility field is a projection, never a second owner.
            row["active_work_after"] = progress["active_work"]
            response["metrics"] = counted_model.metrics()
        except IncompleteConversation as exc:
            raise BrainRefused(
                409, "The saved context or its sources could not be verified. "
                "Reload this conversation before continuing."
            ) from exc
        except ContextOverflow as exc:
            raise BrainRefused(
                413, "The complete conversation does not fit the configured "
                "model. Please contact the administrator to increase its "
                "context capacity.", retryable=False) from exc
        if self.session_current is not None and not self.session_current():
            raise BrainRefused(401, "Your session ended before the response "
                               "was saved. Sign in again to continue.",
                               retryable=False)
        try:
            self.store.commit(updated, expected_version=matter.version)
        except StaleWrite:
            current = self.store.load(matter_id)
            if current is not None and current.advocate_id == turn.advocate_id:
                prior = _saved_reply(current, turn.turn_id, offer_digest)
                if prior is not None:
                    return BrainOutput(prior)
            raise
        return BrainOutput(response)
