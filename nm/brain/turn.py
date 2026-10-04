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
    decompose_subjects,
    read_findings,
    verify_findings,
)
from nm.brain.material import addressed_sources, extract_details
from nm.brain.material_state import material_record, sourced_detail_for_display
from nm.brain.material_verification import verify_material_grounding
from nm.brain.record_review import (
    SOURCE_TREATMENT_CONTRACT,
    classify_account_sources,
    owned_source_treatments,
    source_treatment_reference_valid,
)
from nm.brain.requirements_state import (
    RESEARCH_VERIFICATION,
    dispute_research_subjects,
    requirements_record,
    research_owner_id,
    research_record,
)
from nm.brain.source_snapshots import inline_source_links, source_snapshots
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
        measured_usage = None
        try:
            result = self.inner.structured(prompt, schema, tier,
                                           max_tokens=max_tokens)
            measured_usage = result.usage
        except ModelError as exc:
            failure = type(exc).__name__
            measured_usage = exc.usage
            with self.lock:
                self.provider_retries += exc.retries
            raise
        finally:
            elapsed = int((perf_counter() - started) * 1000)
            receipt = {"operation": prompt.operation, "latency_ms": elapsed,
                       "tier": tier.value,
                       "model": result.model if result else "",
                       "state": failure or "ok",
                       "tokens_in": measured_usage.tokens_in if measured_usage else 0,
                       "tokens_out": measured_usage.tokens_out if measured_usage else 0,
                       "usage_recorded": measured_usage is not None,
                       "cost_usd": measured_usage.cost_usd if measured_usage else None}
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


def _research_subjects(matter: Matter, disputes: dict, material: dict,
                       plan=None, prior_conversation=()) -> tuple[tuple[dict, ...], dict]:
    subjects, contexts = dispute_research_subjects(
        matter, disputes=disputes, material=material)
    active = {subject["id"]: subject for subject in subjects}
    # Validate the saved owner before inspecting even inactive request metadata.
    checked = research_record(matter, subjects=(), material_by_subject={},
                              prior_conversation=prior_conversation)
    if checked["state"] != "ok":
        raise IncompleteConversation("The saved research ownership is incomplete")
    requested = {}
    for turn in matter.brain_chat:
        for read in turn["response"].get("research_reads", []):
            subject = read["subject"]
            if subject["kind"] == "request":
                requested[subject["id"]] = dict(subject)
    if plan is not None:
        for item in plan.items:
            if item.next_step != "legal_work" or not item.research_question:
                continue
            scope = ("current" if item.matter_scope == "proposed" and matter.brain_ready
                     else item.matter_scope)
            subject = dict(kind="request", owner_id=research_owner_id(matter),
                           scope=scope, purpose="requested_work",
                           question=item.research_question, record_ids=[])
            subject["id"] = "rq_" + _digest(subject)[:32]
            requested[subject["id"]] = subject
    record_context = [*disputes["rows"], *material["rows"]]
    for identity, subject in requested.items():
        context = record_context if subject["scope"] in ("current", "proposed") else []
        subject["record_ids"] = [row["id"] for row in context]
        contexts[identity] = context
        active[identity] = subject
    return tuple(active.values()), contexts


def _project_research(matter, disputes, material, corpus_revision, plan=None,
                      prior_conversation=()):
    subjects, contexts = _research_subjects(
        matter, disputes, material, plan, prior_conversation)
    current = research_record(matter, subjects=subjects,
                              material_by_subject=contexts,
                              corpus_revision=corpus_revision,
                              prior_conversation=prior_conversation)
    if current["state"] != "ok":
        raise IncompleteConversation("The saved research record is incomplete")
    return current, contexts


def _current_records(store: StorePort, matter: Matter,
                     corpus_revision: str | None = None) -> tuple[Conversation, dict, dict]:
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
    research, _ = _project_research(matter, disputes, details, corpus_revision,
                                    prior_conversation=older_context)
    coverage = tuple({**subject,
                      "coverage": research["coverage_by_subject"][identity],
                      "finding_kinds": sorted({row["kind"] for row in
                                               research["by_subject"][identity]})}
                     for identity, subject in research["subjects"].items())
    return (replace(conversation, open_disputes=tuple(disputes["rows"]),
                    open_material=tuple([*details["rows"],
                                         *details.get("excluded_scope", [])]),
                    progress=progress,
                    research_coverage=coverage,
                    current_work=progress["active_work"]), disputes, details)


def _history(store: StorePort, matter: Matter, corpus_revision=None) -> Conversation:
    return _current_records(store, matter, corpus_revision)[0]


def _saved_source_treatments(matter: Matter, conversation: Conversation) -> dict[str, dict]:
    """Reuse only complete focused reads with their original chronological owners."""
    positions = {(message.turn_id, message.role): index
                 for index, message in enumerate(conversation.messages)}
    catalogue = {}
    for saved in matter.brain_chat:
        coverage = saved["response"].get("material_coverage", {})
        if (not isinstance(coverage, dict)
                or coverage.get("source_treatment_contract") != SOURCE_TREATMENT_CONTRACT):
            continue
        index = positions.get((saved["turn_id"], "advocate"))
        if index is None or conversation.messages[index].text != saved["message"]:
            raise IncompleteConversation("A saved source-treatment read has no source turn")
        _, latest, prior = addressed_sources(conversation.messages[:index], saved["message"])
        expected = {key: (ref.turn_id, ref.role, ref.quoted)
                    for key, ref in prior.items() if ref.role == "advocate"}
        expected.update({key: (saved["turn_id"], "advocate", text)
                         for key, text in latest.items()})
        try:
            current = owned_source_treatments(coverage.get("source_treatments"), latest, prior)
        except SchemaViolation as exc:
            raise IncompleteConversation(
                "A saved source-treatment catalogue is incomplete") from exc
        if any(not source_treatment_reference_valid(row, {expected[key]})
               for key, row in current.items()):
            raise IncompleteConversation("A saved source-treatment reference has another owner")
        # Every focused read covers all advocate spans available at its turn.
        # The latest complete read can replace earlier role proposals without
        # rewriting their saved history or treating future words as evidence.
        catalogue = {key: dict(row) for key, row in current.items()}
    return catalogue


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
                element = {
                    "kind": "question" if block["id"] in question_blocks else "finding",
                    "text": block["text"], "thread": None, "by_when": None,
                    "no_deadline_reason": None, "signal": "none",
                    "collapsible": False, "disclosure": False,
                    "refs": [source["locator"] for source in sources],
                    "source": sources[0] if sources else None, "sources": sources,
                    "section": "needed" if block["id"] in question_blocks else "answer",
                    "continuation_request_index": index,
                    "continuation_block_id": block["id"]}
                links = inline_source_links(block, sources)
                if links is not None:
                    element["inline_citations"] = links
                elements.append(element)
        else:
            text = ("I could not finish a checked response to this part of your "
                    "request. Your message is saved; ask me to continue this "
                    "work without resending the account."
                    if index in expected else item.reply.strip())
            elements.append({"kind": "finding", "text": text, "refs": [],
                             "source": None, "section": "answer",
                             "collapsible": False, "disclosure": index in expected})
    return elements


def _read_material(model, conversation: Conversation, latest: str, turn_id: str,
                   audit: list[dict] | None = None, *, source_treatments=None):
    """Read disputes, then details that can link to newly identified issues."""
    arguments = {"earlier": conversation.messages, "latest": latest,
                 "current_matter_id": conversation.current_matter_id}
    disputes = verify_disputes(
        model,
        candidates=extract_disputes(
            model, prior_disputes=conversation.open_disputes,
            source_treatments=source_treatments, **arguments),
        earlier=conversation.messages, latest=latest,
        active_disputes=conversation.open_disputes, audit=audit,
        source_treatments=source_treatments)
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
        prior_material=conversation.open_material,
        source_treatments=source_treatments, **arguments)
    return (*disputes, *details), tuple(active.values())


def _legal_reads(model, search, *, conversation: Conversation,
                 subjects: tuple[dict, ...], material_by_subject: dict,
                 current: dict, corpus_revision: str | None,
                 source_treatments=None) -> list[dict]:
    """Research due independent subjects; bounded correction belongs to each reader."""
    due = tuple(subject for subject in subjects
                if not current["reuse_allowed"].get(subject["id"], False))
    if not due:
        return []
    contexts = {subject["id"]: material_by_subject[subject["id"]] for subject in due}
    planned = decompose_subjects(model, subjects=due, material_by_subject=contexts,
                                 conversation=conversation.messages)
    results = {}
    for subject in due:
        identity = subject["id"]
        if identity not in planned.rows:
            continue
        try:
            started = perf_counter()
            result = search.search_subject(subject, planned.rows[identity])
            logging.getLogger(__name__).info("Legal corpus search finished: %sms",
                                            int((perf_counter() - started) * 1000))
            if (not isinstance(result, dict)
                    or result.get("state") not in ("ok", "partial", "unavailable")
                    or not isinstance(result.get("candidates"), list)):
                raise ValueError("search returned no reliable state")
            results[identity] = result
        except Exception:  # noqa: BLE001 -- local adapter failure has a subject owner
            results[identity] = dict(state="unavailable", candidates=[],
                                     diagnostics=["Legal corpus search did not finish"])
    readable = tuple(subject for subject in due if subject["id"] in results
                     and results[subject["id"]]["state"] != "unavailable")
    found = read_findings(model, subjects=readable,
                         material_by_subject={row["id"]: contexts[row["id"]]
                                              for row in readable},
                         search_results={row["id"]: results[row["id"]]
                                         for row in readable},
                         conversation=conversation.messages)
    verifiable = tuple(subject for subject in readable if subject["id"] in found.rows)
    checked = verify_findings(model, subjects=verifiable,
                              material_by_subject={row["id"]: contexts[row["id"]]
                                                   for row in verifiable},
                              proposed={row["id"]: found.rows[row["id"]]
                                        for row in verifiable},
                              conversation=conversation.messages,
                              source_treatments=source_treatments)
    reads = []
    for subject in due:
        identity = subject["id"]
        diagnostics, stages = [], []
        for stage in (planned, found, checked):
            coverage = stage.coverage.get(identity)
            if coverage is not None:
                stages.append(coverage)
                diagnostics.extend(coverage.get("diagnostics", []))
        result = results.get(identity, {})
        diagnostics.extend(result.get("diagnostics", []))
        verified = checked.rows.get(identity, [])
        completed = identity in checked.rows
        stage_ok = all(stage.get("state") == "ok" for stage in stages)
        state = ("ok" if completed and stage_ok and result.get("state") == "ok"
                 else "partial" if completed or verified else "unavailable")
        coverage = dict(checked.coverage.get(identity) or {
            "checked_items": 0, "unread_items": 1, "withheld_items": 0})
        coverage["unread_items"] = max(
            (stage.get("unread_items", 0) for stage in stages), default=1)
        if not completed:
            coverage["unread_items"] = max(1, coverage["unread_items"])
        coverage["withheld_items"] = sum(stage.get("withheld_items", 0) for stage in stages)
        coverage.update(state=state, diagnostics=list(dict.fromkeys(diagnostics)))
        reads.append(dict(subject=subject, fingerprint=current["fingerprints"][identity],
                          corpus_revision=corpus_revision, state=state, rows=verified,
                          verification=RESEARCH_VERIFICATION, coverage=coverage,
                          queries=list(planned.rows.get(identity, ())),
                          diagnostics=coverage["diagnostics"]))
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
        revision_reader = getattr(self.legal_search, "revision", None)
        try:
            corpus_revision = revision_reader() if callable(revision_reader) else None
        except Exception:  # noqa: BLE001 -- unknown freshness disables research reuse
            corpus_revision = None
        try:
            conversation = (_history(self.store, matter, corpus_revision) if persisted else
                            Conversation((), progress=project_work(matter)))
            source_treatments = _saved_source_treatments(matter, conversation)
            plan = interpret(counted_model, conversation, turn.message)
            dispute_audit: list[dict] = []
            source_reviewed = False
            if plan.material_review or plan.opening.ready:
                source_payload, _, _ = addressed_sources(conversation.messages, turn.message)
                source_treatments = classify_account_sources(
                    counted_model, payload=source_payload, latest_turn_id=turn.turn_id)
                source_reviewed = True
                candidates, active_disputes = _read_material(
                    counted_model, conversation, turn.message, turn.turn_id, dispute_audit,
                    source_treatments=source_treatments)
            else:
                candidates, active_disputes = (), conversation.open_disputes
            grounded = verify_material_grounding(
                counted_model, candidates=candidates, opening=plan.opening,
                earlier=conversation.messages, latest=turn.message,
                active_disputes=active_disputes,
                prior_material=conversation.open_material,
                current_matter_id=conversation.current_matter_id,
                source_treatments=source_treatments)
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
                        earlier=conversation.messages, latest=turn.message,
                        source_treatments=source_treatments)
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
                        "rejected_proposals": list(grounded.rejected_proposals),
                        "dispute_review": dispute_audit,
                        "source_treatments": source_treatments if source_reviewed else {},
                        "source_treatment_contract": SOURCE_TREATMENT_CONTRACT
                        if source_reviewed else "",
                        "opening_fallback": not opening_supported},
                    "research_reads": [],
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
                    self.store, updated, corpus_revision)
                current, contexts = _project_research(
                    updated, disputes, details, corpus_revision, plan,
                    prior_conversation=conversation.messages)
                questions = {item.research_question for item in plan.items
                             if item.next_step == "legal_work" and item.research_question}
                current_enquiry = any(item.next_step == "legal_work" and
                                      item.matter_scope in ("current", "proposed") and
                                      item.research_question for item in plan.items)
                subjects = tuple(subject for subject in current["subjects"].values()
                    if (subject["kind"] == "request" and subject["question"] in questions)
                    or (subject["kind"] == "dispute" and
                        (candidates or plan.material_review or current_enquiry)))
                if self.legal_search is not None and subjects:
                    reads = _legal_reads(
                        counted_model, self.legal_search,
                        conversation=replace(
                            current_conversation,
                            messages=(*conversation.messages,
                                      Message(turn.turn_id, "advocate", turn.message))),
                        subjects=subjects, material_by_subject=contexts,
                        current=current, corpus_revision=corpus_revision,
                        source_treatments=source_treatments)
                    response["research_reads"] = reads
                    # Persist only a fully attributable canonical projection;
                    # ordinary rejected proposals already have local coverage.
                    current, _ = _project_research(
                        updated, disputes, details, corpus_revision, plan,
                        prior_conversation=conversation.messages)
                    response["metrics"] = counted_model.metrics()
            if continuation_indexes(plan):
                checked = requirements_record(
                    updated, disputes=disputes, material=details,
                    corpus_revision=corpus_revision,
                    prior_conversation=conversation.messages)
                current, _ = _project_research(
                    updated, disputes, details, corpus_revision, plan,
                    prior_conversation=conversation.messages)
                continuation = continue_conversation(
                    counted_model, conversation=conversation, latest=turn.message,
                    latest_turn_id=turn.turn_id, plan=plan, disputes=disputes,
                    material=details, requirements=checked, research=current,
                    progress=conversation.progress,
                    source_treatments=source_treatments).as_dict()
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
        except (IncompleteConversation, SchemaViolation) as exc:
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
