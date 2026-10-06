"""The authenticated chat turn, saved atomically with its conversation."""
from __future__ import annotations

import hashlib
import json
import logging
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from threading import Lock, local
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
from nm.brain.execution_contracts import (
    RECORD_ACKNOWLEDGEMENT_CONTRACT,
    ExecutionEvidenceInvalid,
    canonical_record_acknowledgements,
    effect_catalogue,
    reader_admission_checked,
    record_change_lines,
)
from nm.brain.history import from_turns, released_older_turns
from nm.brain.legal_requirements import (
    decompose_subjects,
    read_findings,
    verify_findings,
)
from nm.brain.material import addressed_sources, extract_details
from nm.brain.material_state import material_record, sourced_detail_for_display
from nm.brain.material_verification import verify_material_grounding
from nm.brain.mutation_contracts import (
    AUTHORITY_CONTRACT,
    bind_record_mutation,
    build_mutation_authorities,
    validate_record_mutation,
)
from nm.brain.record_review import (
    ACCOUNT_COVERAGE_CONTRACT,
    SOURCE_TREATMENT_CONTRACT,
    candidate_account_ids,
    classify_account_sources,
    owned_source_treatments,
    reconsider_account_sources,
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
from nm.brain.work_state import (
    project_work,
    record_result_snapshot,
    seal_progress,
    validate_record_result_snapshot,
)
from nm.shared.gates_contracts import gate_diagnostic
from nm.shared.model_port import (
    ConfigurationError,
    ContextOverflow,
    ModelError,
    OutputTruncated,
    ProviderUnavailable,
    SchemaViolation,
    TierUnavailable,
)
from nm.shared.store_port import StaleWrite, StorePort
from nm.work_the_file.matter_contracts import Matter, MatterId


class BrainRefused(Exception):
    def __init__(self, status: int, why: str, *, committed: str = "not_committed",
                 retryable: bool = True, code: str = "brain_refused",
                 gate_id: str | None = None, gate_state: str | None = None) -> None:
        super().__init__(why)
        self.status = status
        self.why = why
        self.committed = committed
        self.retryable = retryable
        self.code = code
        self.gate_diagnostic = (gate_diagnostic(gate_id, gate_state)
                                if gate_id is not None and gate_state is not None else None)


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

    def __init__(self, inner, *, recovery_limit: int = 8) -> None:
        if type(recovery_limit) is not int or recovery_limit < 0:
            raise ValueError("Recovery call ceiling must be a nonnegative integer")
        self.inner = inner
        self.calls = 0
        self.provider_retries = 0
        self.receipts = []
        self.lock = Lock()
        self.recovery_limit = recovery_limit
        self.recovery_events: list[dict] = []
        self.recovery_reserved = 0
        self.recovery_local = local()

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def claim_recovery(self, phase: str) -> bool:
        """Reserve one explicitly owned conditional call without resetting its bound."""
        if not isinstance(phase, str) or not phase.strip():
            raise ValueError("A recovery call requires an explicit phase identity")
        self.cancel_pending_recovery()
        with self.lock:
            used = self.recovery_reserved
            permitted = used < self.recovery_limit
            event = {"phase": phase, "state": "reserved" if permitted else
                     "budget_exhausted", "scope": getattr(self.recovery_local, "scope", "initial")}
            self.recovery_events.append(event)
            if permitted:
                self.recovery_reserved += 1
                event["reservation"] = self.recovery_reserved
                self.recovery_local.pending = len(self.recovery_events) - 1
            return permitted

    def cancel_pending_recovery(self) -> None:
        """A refused context may consume a reservation without dispatching a call."""
        pending = getattr(self.recovery_local, "pending", None)
        if pending is not None:
            with self.lock:
                self.recovery_events[pending]["state"] = "not_dispatched"
            self.recovery_local.pending = None

    def abandon_recovery(self, phase: str) -> None:
        """Retain a spent reservation while abandoning only its undispatched permit."""
        pending = getattr(self.recovery_local, "pending", None)
        if pending is not None and self.recovery_events[pending]["phase"] == phase:
            self.cancel_pending_recovery()

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        started = perf_counter()
        logger = logging.getLogger(__name__)
        with self.lock:
            self.calls += 1
            ordinal = self.calls
            recovery_index = getattr(self.recovery_local, "pending", None)
            self.recovery_local.pending = None
            recovery_phase = ""
            if recovery_index is not None:
                event = self.recovery_events[recovery_index]
                event.update(state="started", call=ordinal)
                recovery_phase = event["phase"]
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
        except Exception as exc:  # noqa: BLE001 -- programming failures are observed, never recovered
            failure = type(exc).__name__
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
            if recovery_phase:
                receipt["recovery_phase"] = recovery_phase
            with self.lock:
                self.receipts.append(receipt)
                if recovery_index is not None:
                    self.recovery_events[recovery_index]["state"] = failure or "completed"
                if result is not None:
                    self.provider_retries += result.retries
            logger.info("Model call %s finished: %s, %sms, %s", ordinal,
                        prompt.operation, elapsed, failure or "ok")
        return result

    def metrics(self) -> dict:
        return {"llm_calls": self.calls, "provider_retries": self.provider_retries,
                "model_calls": list(self.receipts), "recovery": {
                    "limit": self.recovery_limit,
                    "reserved_calls": self.recovery_reserved,
                    "dispatched_calls": sum("call" in event for event in self.recovery_events),
                    "events": deepcopy(self.recovery_events)}}


def _digest(value: dict) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


MATERIAL_EXECUTION_CONTRACT = "material_execution_v1"


def _material_execution(turn: BrainTurn, matter: Matter, offer_digest: str,
                        plan) -> dict:
    """Code-owned observations, distinct from requested outcome fulfillment."""
    owner = {"matter_id": str(matter.id), "advocate_id": turn.advocate_id,
             "turn_id": turn.turn_id, "offer_digest": offer_digest}
    return {
        "contract": MATERIAL_EXECUTION_CONTRACT,
        "id": "mex_" + _digest(owner)[:32], "owner": owner,
        "expected_version": matter.version, "resulting_version": matter.version + 1,
        "persistence": "prepared_for_commit", "semantic_coverage": "unassessed",
        "material_selected": bool(plan.material_review or plan.opening.ready),
        "requests": [{"request_index": index, "request": item.request,
                      "material_purposes": (list(item.material_purposes)
                                            if item.material_purposes is not None else None),
                      "relation": item.relation, "matter_scope": item.matter_scope,
                      "intent": item.intent,
                      "response_mode": getattr(item, "response_mode", "substantive"),
                      **({"acknowledgement_contract": RECORD_ACKNOWLEDGEMENT_CONTRACT}
                         if getattr(item, "response_mode", "substantive")
                         == "record_acknowledgement" else {}),
                      "record_requirement": deepcopy(item.record_requirement),
                      "fulfillment": "unassessed"}
                     for index, item in enumerate(plan.items)],
        "stages": {name: {"state": "not_run"} for name in (
            "source_classification", "dispute_extraction", "dispute_review",
            "detail_extraction", "detail_review")},
    }



def _mutation_catalogues(conversation, latest, turn_id):
    """Resolve code-owned dependencies without interpreting source meaning."""
    _, current, prior = addressed_sources(conversation.messages, latest)
    sources = {identity: {"turn_id": ref.turn_id, "role": ref.role, "quoted": ref.quoted}
               for identity, ref in prior.items() if ref.role == "advocate"}
    sources.update({identity: {"turn_id": turn_id, "role": "advocate", "quoted": quoted}
                    for identity, quoted in current.items()})
    targets = {row["id"]: deepcopy(row) for row in
               (*conversation.open_disputes, *conversation.open_material)}
    return targets, sources


def _mutation_authorities(execution, conversation, plan, latest):
    """Freeze original source-linked scope before any record reader runs."""
    scopes = [getattr(item, "mutation_scopes", None) for item in plan.items]
    if any(scope is None for scope in scopes):
        # Fresh interpreter wire output cannot take this historical branch.
        return
    targets, sources = _mutation_catalogues(conversation, latest, execution["owner"]["turn_id"])
    ledger = build_mutation_authorities(
        owner=execution["owner"], expected_version=execution["expected_version"],
        target_catalogue=targets, source_catalogue=sources,
        proposals=[{"request_index": index, **deepcopy(scope)}
                   for index, declarations in enumerate(scopes) for scope in declarations],
        request_indices=list(range(len(plan.items))))
    execution.update(mutation_authority_contract=AUTHORITY_CONTRACT,
                     mutation_authorities=ledger)


def _material_effects(before: dict, after: dict, proposals: list[dict], *,
                      kind: str, turn_id: str) -> dict:
    """Derive deltas across both active-owned and ownership-held domains."""
    old = {row["id"] for row in before["rows"]}
    current = {row["id"] for row in after["rows"]}
    old_held = {row["id"] for row in before.get("excluded_scope", [])}
    current_held = {row["id"] for row in after.get("excluded_scope", [])}
    retired = old - current
    owned = [row for row in after["history"] if row["source_turn_id"] == turn_id]
    held = {row["id"] for row in after.get("excluded_scope", [])
            if row["source_turn_id"] == turn_id}
    recorded = {row["id"] for row in owned} | held
    target_field = "related_dispute_ids" if kind == "disputes" else "related_material_ids"
    return {
        "before_record_ids": sorted(old), "after_record_ids": sorted(current),
        "before_held_record_ids": sorted(old_held),
        "after_held_record_ids": sorted(current_held),
        "activated_record_ids": sorted(current - old),
        "retired_record_ids": sorted(retired),
        "operations": [{
            "result_id": row["id"], "relation": row["relation"],
            "target_record_ids": list(row.get(target_field, [])),
            "retired_target_ids": sorted(retired.intersection(row.get(target_field, []))),
            "source_references": [
                {"turn_id": row["source_turn_id"], "role": "advocate",
                 "quoted": row["quoted"]}, *deepcopy(row["prior_references"])],
        } for row in owned],
        "held_record_ids": sorted(held),
        "outside_owned_record_ids": [row["id"] for row in proposals
            if (row["kind"] == "dispute") == (kind == "disputes")
            and row["id"] not in recorded],
    }


def _execution_review_scope(execution: dict, progress: dict) -> dict:
    """Copy the exact interpreted record requirements for independent coverage."""
    requests = [{"request_index": row["request_index"],
                 "record_requirement": deepcopy(row["record_requirement"])}
                for row in execution["requests"]]
    for request in execution["requests"]:
        requirement = request["record_requirement"]
        if (not isinstance(requirement, dict) or requirement.get("kind") != "review"
                or request["relation"] != "continues" or request["intent"] != "request"):
            continue
        # Exact owned requirement equality can add an identity alias for this
        # already-authorised review; it cannot widen the semantic scope.
        for task in progress["rows"]:
            same_scope = (task["matter_scope"] == request["matter_scope"] or
                          task["matter_scope"] == "proposed"
                          and request["matter_scope"] == "current")
            if (task["kind"] == "task" and same_scope
                    and task.get("record_requirement") == requirement):
                requests.append({"request_index": request["request_index"],
                                 "task_id": task["id"],
                                 "request": task["text"], "matter_scope": task["matter_scope"],
                                 "record_requirement": deepcopy(requirement)})
    return {"owner": deepcopy(execution["owner"]), "requests": requests,
            **({"mutation_authorities": deepcopy(execution["mutation_authorities"]),
                "mutation_authority_contract": execution["mutation_authority_contract"]}
               if "mutation_authorities" in execution else {})}


def _record_catalogue(disputes: dict, details: dict) -> dict:
    return {row["id"]: {"id": row["id"], "type": kind, "record": deepcopy(row)}
            for kind, projection in (("dispute", disputes), ("material", details))
            for row in projection["rows"]}


def _record_projections(matter: Matter, prior_conversation) -> tuple[dict, dict]:
    disputes = proposed_disputes(matter, prior_conversation=prior_conversation)
    details = material_record(matter, disputes=disputes,
                              prior_conversation=prior_conversation)
    if disputes["state"] != "ok" or details["state"] != "ok":
        raise IncompleteConversation("The saved record result is incomplete")
    return disputes, details


def _request_fulfillment(execution: dict, continuation: dict) -> None:
    """Retain the independent typed disposition, never infer it from effects."""
    units = {unit["request_index"]: unit for unit in continuation["units"]}
    for request in execution["requests"]:
        unit = units.get(request["request_index"])
        if unit is None:
            request["fulfillment"] = "unfinished"
            continue
        check = unit.get("record_check")
        if (not isinstance(check, dict) or set(check) != {"outcome", "reason"}
                or check["outcome"] not in (
                    "fulfilled", "no_change_justified", "unfinished", "not_requested")
                or not isinstance(check["reason"], str) or not check["reason"].strip()):
            raise IncompleteConversation("The independent record-result check is absent")
        outcome = unit.get("record_outcome")
        if not isinstance(outcome, dict):
            raise IncompleteConversation("The checked record-result owner is absent")
        request["fulfillment"] = check["outcome"]
        request["fulfillment_check"] = {
            **deepcopy(check), "receipt_id": execution["id"],
            "request_index": request["request_index"],
            "block_id": outcome["block_id"],
            "effect_ids": list(outcome["effect_ids"]),
            "current_record_ids": list(outcome["current_record_ids"])}



def _execution_diagnostics(execution: dict) -> list[dict]:
    diagnostics = []
    required = execution.get("material_selected") or any(
        isinstance(row.get("record_requirement"), dict)
        and row["record_requirement"]["kind"] != "none" for row in execution["requests"])
    states = [execution["stages"][name].get("account_coverage", {}).get("state")
              for name in ("dispute_review", "detail_review")]
    if required and any(state != "complete" for state in states):
        state = ("partial" if any(value in ("partial", "complete") for value in states)
                 else "unassessed")
        diagnostics.append(gate_diagnostic("G-INCOMPLETE", state))
    for name in ("dispute_extraction", "detail_extraction"):
        if execution["stages"][name].get("state") == "partial":
            diagnostics.append({**gate_diagnostic("G-MODEL", "degraded"),
                                "stage": name})
    for request in execution["requests"]:
        if (request["record_requirement"]["kind"] != "none"
                and request.get("fulfillment") == "unfinished"):
            diagnostics.append({**gate_diagnostic("G-EFFECT", "unassessed"),
                                "request_index": request["request_index"]})
    return diagnostics


def _record_changes(before_disputes: dict, before_details: dict,
                    disputes: dict, details: dict, execution: dict) -> list[dict]:
    before = {"disputes": before_disputes, "details": before_details}
    after = {"disputes": disputes, "details": details}
    changes = []
    for effect in effect_catalogue(execution).values():
        if not effect["performed"]:
            continue
        prior = {row["id"]: row for row in [*before[effect["kind"]]["rows"],
                    *before[effect["kind"]].get("excluded_scope", [])]}
        current = {row["id"]: row for row in after[effect["kind"]]["rows"]}
        if any(identity not in prior for identity in effect["target_record_ids"]):
            raise IncompleteConversation("The performed change has no canonical prior entry")
        result = current.get(effect["result_id"])
        if effect["relation"] != "withdraws" and result is None:
            raise IncompleteConversation("The performed change has no canonical resulting entry")
        changes.append({"effect_id": effect["id"], "kind": effect["kind"],
                        "relation": effect["relation"],
                        "before_records": [deepcopy(prior[identity])
                                           for identity in effect["target_record_ids"]],
                        "after_record": deepcopy(result)})
    return changes


def _record_change_lines(changes: list[dict]) -> list[str]:
    return record_change_lines(changes)


def _execution_display(execution: dict) -> dict:
    """Render exact observed entry changes without claiming requested completion."""
    parts = _record_change_lines(execution["record_changes"])
    if not parts:
        parts.append("No changes were made to the saved record.")
    held = {identity for domain in execution["effects"].values()
            for identity in domain["after_held_record_ids"]}
    if held:
        parts.append(str(len(held)) + " items remain separate while their matter ownership "
                     "is clarified.")
    required = execution.get("material_selected") or any(
        isinstance(row.get("record_requirement"), dict)
        and row["record_requirement"]["kind"] != "none" for row in execution["requests"])
    reviews = [execution["stages"][name] for name in ("dispute_review", "detail_review")]
    reader_partial = any(execution["stages"][name].get("state") == "partial"
                         for name in ("dispute_extraction", "detail_extraction"))
    if required and (reader_partial or any(
            row.get("account_coverage", {}).get("state") != "complete" for row in reviews)):
        parts.append("The record reading remains unfinished.")
    element = {"kind": "finding", "text": "\n".join(parts), "refs": [],
               "source": None, "section": "answer", "collapsible": False,
               "disclosure": bool(required), "material_execution_id": execution["id"]}
    return {"contract": "material_result_display_v1", "receipt_id": execution["id"],
            "element": element}


def _canonical_record_acknowledgements(
        continuation: dict, execution: dict, *, record_catalogue: dict,
        replay: bool = False) -> dict:
    """Use the shared code-owned acknowledgement contract after review."""
    return canonical_record_acknowledgements(
        continuation, execution, record_catalogue=record_catalogue, replay=replay)


def _validate_execution_replay(matter: Matter, row: dict, *, prior_conversation) -> None:
    """Compare the receipt with its original prefix, never today's superseded state."""
    response = row["response"]
    execution = response.get("material_coverage", {}).get("execution")
    if not isinstance(execution, dict):
        return
    _check_execution_owner(execution, matter, row["turn_id"], row["offer_digest"])
    requests = _checked_execution_requests(execution)
    snapshot = response.get("continuation", {}).get("record_snapshot")
    if snapshot is None and "display" not in execution:
        if execution.get("mutation_authority_contract") is not None:
            raise IncompleteConversation("A scoped record result has no saved snapshot")
        # Older receipts have no result snapshot/display binding. They remain
        # readable compatibility evidence, never new certified result proof.
        return
    if snapshot is None:
        raise IncompleteConversation("The saved record-result snapshot is missing")
    index = next(index for index, item in enumerate(matter.brain_chat)
                 if item["turn_id"] == row["turn_id"])
    before = replace(matter, brain_chat=matter.brain_chat[:index],
                     version=execution["expected_version"])
    after = replace(matter, brain_chat=matter.brain_chat[:index + 1],
                    version=execution["resulting_version"])
    before_disputes, before_details = _record_projections(before, prior_conversation)
    disputes, details = _record_projections(after, prior_conversation)
    if "review_scope" in execution:
        expected_scope = _execution_review_scope(
            execution, project_work(before, prior_conversation=prior_conversation))
        if execution["review_scope"] != expected_scope:
            raise IncompleteConversation(
                "The saved record review scope differs from its original requests and work")
    contract = execution.get("mutation_authority_contract")
    ledger = execution.get("mutation_authorities")
    if contract is not None or ledger is not None:
        if contract != AUTHORITY_CONTRACT or not isinstance(ledger, dict):
            raise IncompleteConversation("The saved mutation scope is absent or unsupported")
        original_messages = (*prior_conversation,
                             *from_turns(before.brain_chat, state="ok").messages)
        original = Conversation(original_messages,
                                open_disputes=tuple(before_disputes["rows"]),
                                open_material=tuple([*before_details["rows"],
                                                     *before_details.get("excluded_scope", [])]))
        grants = ledger.get("authorities")
        if (not isinstance(grants, list) or any(not isinstance(grant, dict) for grant in grants)):
            raise IncompleteConversation("The saved mutation grants could not be read")
        proposals = []
        for grant in grants:
            declaration = {key: deepcopy(value) for key, value in grant.items() if key != "id"}
            if declaration.get("target_scope") == "reviewed_whole":
                declaration["target_ids"] = []
            proposals.append(declaration)
        try:
            targets, sources = _mutation_catalogues(original, row["message"], row["turn_id"])
            rebuilt = build_mutation_authorities(
                owner=execution["owner"], expected_version=execution["expected_version"],
                target_catalogue=targets, source_catalogue=sources, proposals=proposals,
                request_indices=[request["request_index"] for request in requests])
            if (rebuilt != ledger
                    or execution.get("review_scope", {}).get("mutation_authorities") != ledger
                    or execution.get("review_scope", {}).get("mutation_authority_contract")
                    != AUTHORITY_CONTRACT):
                raise SchemaViolation("Saved scope disagrees with its original dependencies")
            for proposal in response["material"]:
                validate_record_mutation(proposal, turn=row, execution=execution,
                                         source_catalogue=ledger["source_catalogue"],
                                         prior_words={(message.turn_id, message.role): message.text
                                                      for message in original_messages},
                                         target_catalogue=ledger["target_catalogue"])
        except SchemaViolation as exc:
            raise IncompleteConversation("The saved mutation proof could not be verified") from exc
    elif any("mutation_authority" in proposal for proposal in response["material"]):
        raise IncompleteConversation("An unversioned record has unexpected mutation proof")
    effects = {
        "disputes": _material_effects(before_disputes, disputes, response["material"],
                                      kind="disputes", turn_id=row["turn_id"]),
        "details": _material_effects(before_details, details, response["material"],
                                    kind="details", turn_id=row["turn_id"])}
    if execution.get("effects") != effects:
        raise IncompleteConversation("The saved material effects disagree with their record")
    changes = _record_changes(before_disputes, before_details, disputes, details, execution)
    if execution.get("record_changes") != changes:
        raise IncompleteConversation(
            "The displayed entry changes disagree with the original record")
    expected = record_result_snapshot(
        execution_receipt=execution, record_catalogue=_record_catalogue(disputes, details))
    validate_record_result_snapshot(snapshot, execution, matter_id=str(matter.id),
                                    advocate_id=matter.advocate_id,
                                    turn_id=row["turn_id"], committed=True)
    if snapshot != expected:
        raise IncompleteConversation("The saved record result disagrees with its original record")
    checked_execution = deepcopy(execution)
    canonical = _canonical_record_acknowledgements(
        response["continuation"], checked_execution,
        record_catalogue=snapshot["record_catalogue"], replay=True)
    if canonical != response["continuation"] or checked_execution != execution:
        raise IncompleteConversation(
            "The saved code acknowledgement differs from its checked result")
    if execution.get("gate_diagnostics") != _execution_diagnostics(execution):
        raise IncompleteConversation("The saved execution gates could not be verified")
    display = _execution_display(execution)
    expected_display = display if display is not None else None
    if execution.get("display") != expected_display:
        raise IncompleteConversation("The saved execution display could not be verified")
    bound = [item for item in response["elements"]
             if item.get("material_execution_id") == execution["id"]]
    if bound != ([display["element"]] if display is not None else []):
        raise IncompleteConversation("The execution receipt and displayed result disagree")


def _checked_execution_requests(execution: dict) -> list[dict]:
    """Read code-owned request identities before any saved evidence consumer.

    The execution list owns contiguous identities. Review scope additionally
    carries inherited task aliases, so its indices may legitimately repeat.
    Missing legacy scope remains untracked; a present scope must be readable.
    """
    requests = execution.get("requests")
    if not isinstance(requests, list):
        raise IncompleteConversation("The saved execution requests could not be read")
    scoped = any(field in execution for field in (
        "mutation_authority_contract", "mutation_authorities", "review_scope"))
    for index, request in enumerate(requests):
        if (not isinstance(request, dict)
                or type(request.get("request_index")) is not int
                or request["request_index"] != index):
            raise IncompleteConversation(
                "The saved execution request identities are not the code-owned sequence")
        if "record_requirement" not in request:
            if scoped:
                raise IncompleteConversation(
                    "The saved execution record requirement is unreadable")
            # Early material_execution_v1 receipts predate typed requirements
            # and review scope. Preserve their original untracked evidence.
            continue
        requirement = request["record_requirement"]
        if requirement is not None and (
                not isinstance(requirement, dict)
                or requirement.get("kind") not in ("none", "review", "change")):
            raise IncompleteConversation("The saved execution record requirement is unreadable")
        if isinstance(requirement, dict) and requirement["kind"] == "review" and any(
                not isinstance(request.get(field), str)
                for field in ("relation", "intent", "matter_scope")):
            raise IncompleteConversation("The saved execution review association is unreadable")
    scope = execution.get("review_scope")
    if "review_scope" not in execution:
        if any(field in execution for field in (
                "mutation_authority_contract", "mutation_authorities")):
            raise IncompleteConversation("A scoped execution has no saved record review scope")
        return requests
    if (not isinstance(scope, dict) or scope.get("owner") != execution.get("owner")
            or not isinstance(scope.get("requests"), list)):
        raise IncompleteConversation(
            "The saved record review scope owner or requests are unreadable")
    bases = [{"request_index": request["request_index"],
              "record_requirement": deepcopy(request["record_requirement"])}
             for request in requests]
    if scope["requests"][:len(requests)] != bases:
        raise IncompleteConversation(
            "The saved record review scope differs from its owned requests")
    for alias in scope["requests"][len(requests):]:
        index = alias.get("request_index") if isinstance(alias, dict) else None
        if (type(index) is not int or not 0 <= index < len(requests)
                or any(not isinstance(alias.get(field), str) or not alias[field].strip()
                       for field in ("task_id", "request", "matter_scope"))
                or alias.get("record_requirement") != requests[index]["record_requirement"]):
            raise IncompleteConversation("The saved inherited record review alias is unreadable")
    return requests


def _check_execution_owner(receipt: dict, matter: Matter, turn_id: str,
                           offer_digest: str) -> None:
    owner = {"matter_id": str(matter.id), "advocate_id": matter.advocate_id,
             "turn_id": turn_id, "offer_digest": offer_digest}
    if (not isinstance(receipt, dict)
            or receipt.get("contract") != MATERIAL_EXECUTION_CONTRACT
            or receipt.get("owner") != owner
            or receipt.get("id") != "mex_" + _digest(owner)[:32]
            or receipt.get("persistence") != "committed"
            or type(receipt.get("expected_version")) is not int
            or type(receipt.get("resulting_version")) is not int
            or not 0 <= receipt["expected_version"] < matter.version
            or receipt["resulting_version"] != receipt["expected_version"] + 1):
        raise BrainRefused(409, "The saved material execution owner could not be verified",
                           gate_id="G-CORE", gate_state="invalid")


def chat_matter_id(advocate_id: str, chat_id: str) -> MatterId:
    return MatterId("mat_" + _digest({"advocate": advocate_id, "chat": chat_id})[:32])


def _saved_reply(matter: Matter, turn_id: str, offer_digest: str, *,
                 store: StorePort) -> dict | None:
    matches = [row for row in matter.brain_chat if row.get("turn_id") == turn_id]
    if not matches:
        return None
    if len(matches) != 1 or matches[0].get("offer_digest") != offer_digest:
        raise BrainRefused(409, "This turn ID already names different instructions")
    response = matches[0].get("response")
    if not isinstance(response, dict) or response.get("turn_id") != turn_id:
        raise BrainRefused(409, "The saved reply could not be verified")
    # Replay releases saved user-visible content. It must pass the same
    # ownership, transcript and displayed-work checks as a newly saved reply.
    try:
        older = released_older_turns(store, matter)
        from_turns([*older, *matter.brain_chat], state="ok")
        older_context = from_turns(older, state="ok").messages
        coverage = response.get("material_coverage")
        execution = coverage.get("execution") if isinstance(coverage, dict) else None
        if isinstance(execution, dict):
            _checked_execution_requests(execution)
        project_work(matter, prior_conversation=older_context)
        _validate_execution_replay(matter, matches[0], prior_conversation=older_context)
    except (IncompleteConversation, ExecutionEvidenceInvalid, ValueError) as exc:
        raise BrainRefused(409, "The saved reply or its sources could not be verified",
                           gate_id="G-CORE", gate_state="invalid") from exc
    coverage = response.get("material_coverage")
    if isinstance(coverage, dict) and "execution" in coverage:
        _check_execution_owner(coverage["execution"], matter, turn_id, offer_digest)
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
                       plan=None, prior_conversation=(),
                       source_treatments=None) -> tuple[tuple[dict, ...], dict]:
    subjects, contexts = dispute_research_subjects(
        matter, disputes=disputes, material=material)
    active = {subject["id"]: subject for subject in subjects}
    # Validate the saved owner before inspecting even inactive request metadata.
    checked = research_record(matter, subjects=(), material_by_subject={},
                              prior_conversation=prior_conversation,
                              source_treatments=source_treatments)
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
                      prior_conversation=(), source_treatments=None):
    subjects, contexts = _research_subjects(
        matter, disputes, material, plan, prior_conversation,
        source_treatments=source_treatments)
    current = research_record(matter, subjects=subjects,
                              material_by_subject=contexts,
                              corpus_revision=corpus_revision,
                              prior_conversation=prior_conversation,
                              source_treatments=source_treatments)
    if current["state"] != "ok":
        raise IncompleteConversation("The saved research record is incomplete")
    return current, contexts


def _current_records(store: StorePort, matter: Matter,
                     corpus_revision: str | None = None, *,
                     source_treatments=None) -> tuple[Conversation, dict, dict]:
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
    if source_treatments is None:
        source_treatments = _saved_source_treatments(matter, conversation)
    research, _ = _project_research(matter, disputes, details, corpus_revision,
                                    prior_conversation=older_context,
                                    source_treatments=source_treatments)
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



def _response_mode(plan) -> tuple[bool, bool]:
    return (any(item.next_step == "legal_work" for item in plan.items),
            any(item.next_step == "clarify" for item in plan.items))


def _continuation_elements(plan, continuation: dict) -> list[dict]:
    units = {unit["request_index"]: unit for unit in continuation["units"]}
    elements = []
    for index, _item in sorted(enumerate(plan.items),
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
            text = ("Your message is saved. This part of the requested work "
                    "remains unfinished.")
            elements.append({"kind": "status", "text": text, "refs": [],
                             "source": None, "section": "answer",
                             "collapsible": False, "disclosure": True})
    return elements



def _record_slots(slots: dict, candidates) -> None:
    """Assign monotonic owned result slots when a proposal is first admitted."""
    for candidate in candidates:
        if candidate not in slots:
            slots[candidate] = max(slots.values(), default=0) + 1


def _preview_disputes(conversation, candidates, turn_id, slots) -> tuple[dict, ...]:
    _record_slots(slots, candidates)
    active = {row["id"]: row for row in conversation.open_disputes}
    for candidate in candidates:
        if not (candidate.matter_scope == "current" or
                (candidate.matter_scope == "proposed" and
                 conversation.current_matter_id is None)):
            continue
        for prior_id in candidate.related_dispute_ids:
            active.pop(prior_id, None)
        if candidate.relation != "withdraws":
            row = candidate.recorded(turn_id, slots[candidate])
            active[row["id"]] = row
    return tuple(active.values())


def _reader_execution(proposals, diagnostics) -> dict:
    return {"state": "partial" if diagnostics.get("state") == "partial" else "returned",
            "proposals": len(proposals), "admissible_proposals": len(proposals),
            "proposal_validation": "owned_extraction_proposals_v1",
            "read_status": deepcopy(diagnostics)}


def _extend_reader_execution(stage, proposals, diagnostics) -> None:
    """Bind aggregate admission counts while retaining each raw read receipt."""
    stage.setdefault("initial_read_status", deepcopy(stage.get("read_status", {})))
    stage.setdefault("reads", [{"phase": "initial", "status": deepcopy(
        stage["initial_read_status"])}])
    stage["reads"].append({"phase": "omission_recovery", "status": deepcopy(diagnostics)})
    stage["recovery_read_status"] = deepcopy(diagnostics)
    partial = stage.get("state") == "partial" or diagnostics.get("state") == "partial"
    aggregate = deepcopy(stage.get("read_status", {}))
    aggregate.update(state="partial" if partial else "returned", proposal_count=len(proposals))
    aggregate["unread_units"] = [
        {**row, "read_batch": index}
        for index, batch in enumerate(stage["reads"], 1)
        for row in batch["status"].get("unread_units", [])]
    stage.update(state="partial" if partial else "returned", proposals=len(proposals),
                 admissible_proposals=len(proposals), read_status=aggregate)


def _dispute_review_execution(disputes, status, coverage) -> dict:
    return {
        "state": "checked" if (status.get("checked_items", 0)
                                 or status.get("state") == "checked") else "partial",
        "accepted": len(disputes), "rejected": status.get("rejected_items", 0),
        "held": status.get("withheld_items", 0), "unread": status.get("unread_items", 0),
        "review_status": deepcopy(status), "account_coverage": deepcopy(coverage),
    }


def _read_material(model, conversation: Conversation, latest: str, turn_id: str,
                   audit: list[dict] | None = None, *, source_treatments=None,
                   execution: dict | None = None, review_scope: dict | None = None,
                   recovery_context: dict | None = None,
                   source_disagreements: list[dict] | None = None):
    """Read ordered proposals and independently assess the original account."""
    arguments = {"earlier": conversation.messages, "latest": latest,
                 "current_matter_id": conversation.current_matter_id}
    dispute_read = {}
    proposed = extract_disputes(
        model, prior_disputes=conversation.open_disputes,
        source_treatments=source_treatments, diagnostics=dispute_read, **arguments)
    if execution is not None:
        execution["dispute_extraction"] = _reader_execution(proposed, dispute_read)
    account_coverage, review_status = {}, {}
    dispute_review_state = {}
    disputes = verify_disputes(
        model, candidates=proposed,
        earlier=conversation.messages, latest=latest,
        active_disputes=conversation.open_disputes, audit=audit,
        source_treatments=source_treatments, review_scope=review_scope,
        coverage=account_coverage, review_status=review_status,
        source_disagreements=source_disagreements, review_state=dispute_review_state)
    if execution is not None:
        # A checked admitted peer keeps its execution evidence even when the
        # broader reading has unread/held peers. Full coverage is separate.
        execution["dispute_review"] = _dispute_review_execution(
            disputes, review_status, account_coverage)
    slots = {}
    active = _preview_disputes(conversation, disputes, turn_id, slots)
    detail_read = {}
    details = extract_details(
        model, disputes=active, prior_material=conversation.open_material,
        source_treatments=source_treatments, diagnostics=detail_read, **arguments)
    if execution is not None:
        execution["detail_extraction"] = _reader_execution(details, detail_read)
    if recovery_context is not None:
        recovery_context.update(dispute_proposals=proposed, detail_proposals=details,
                                accepted_disputes=disputes, slots=slots,
                                dispute_review_state=dispute_review_state)
    return (*disputes, *details), active


def _conditional_read(model, phase, reader, **arguments):
    """A conditional dispatch carries an explicit scope and spends the shared limit."""
    previous_scope = getattr(model.recovery_local, "scope", "initial")
    model.recovery_local.scope = phase
    try:
        if not model.claim_recovery(phase):
            return None
        return reader(model, **arguments)
    finally:
        model.cancel_pending_recovery()
        model.recovery_local.scope = previous_scope


def _partial_coverage(coverage, reason) -> None:
    previous = deepcopy(coverage)
    coverage.update(state="unassessed", missing_source_ids=[], missing_sources=[],
                    reason=reason, validation_issue=reason)
    if previous:
        coverage["previous_assessment"] = previous


def _affected_proposals(proposals, changed_sources, latest_sources, prior_sources,
                        unavailable_assignments=()) -> set:
    affected = {
        candidate for candidate in proposals
        if candidate_account_ids(candidate, latest_sources, prior_sources).intersection(
            changed_sources)
        or set(candidate.dispute_ids).intersection(unavailable_assignments)}
    while True:
        targets = {identity for candidate in affected
                   for identity in (*candidate.related_dispute_ids,
                                    *candidate.related_material_ids)}
        expanded = affected | {
            candidate for candidate in proposals
            if targets.intersection((*candidate.related_dispute_ids,
                                     *candidate.related_material_ids))}
        if expanded == affected:
            return affected
        affected = expanded


def _unread_proposal(candidate, identity, reason, *, kind="detail") -> dict:
    return {"candidate_id": identity, "candidate_type": kind, "verdict": "unassessed",
            "admission_issue": "review_unavailable", "reason": reason,
            "validation_issues": [reason], "proposal": asdict(candidate)}


def _hold_affected_grounding(grounded, proposals, affected, opening, reason,
                            *, opening_affected=False):
    ids = {f"D{index}" for index, candidate in enumerate(proposals, 1) if candidate in affected}
    rejected = tuple(row for row in grounded.rejected_proposals if row["candidate_id"] not in ids)
    withheld = tuple(row for row in grounded.withheld_proposals if row["candidate_id"] not in ids)
    unread = tuple(row for row in grounded.unread_proposals
                   if row["candidate_id"] not in ids and not (
                       opening_affected and row["candidate_id"] == "O1"))
    unread += tuple(_unread_proposal(candidate, f"D{index}", reason)
                    for index, candidate in enumerate(proposals, 1) if candidate in affected)
    if opening_affected and opening.ready:
        unread += (_unread_proposal(opening, "O1", reason, kind="opening"),)
    return replace(
        grounded, details=tuple(row for row in grounded.details if row not in affected),
        rejected_proposals=rejected, rejected_details=len(rejected),
        withheld_proposals=withheld, unread_proposals=unread,
        mutation_bindings=tuple((candidate, binding) for candidate, binding in
                               grounded.mutation_bindings if candidate not in affected),
        opening_supported=(False if opening_affected and opening.ready
                           else grounded.opening_supported),
        opening_reason=reason if opening_affected and opening.ready else grounded.opening_reason)


def _localized_omission(coverage, review_scope, source_treatments) -> tuple[str, ...]:
    if (coverage.get("contract") != ACCOUNT_COVERAGE_CONTRACT
            or coverage.get("review_scope") != review_scope
            or coverage.get("state") != "partial" or "validation_issue" in coverage
            or not isinstance(coverage.get("reason"), str) or not coverage["reason"].strip()):
        return ()
    ids = coverage.get("missing_source_ids")
    if not isinstance(ids, list) or not ids or any(
            not isinstance(identity, str) or identity not in source_treatments for identity in ids):
        return ()
    return tuple(dict.fromkeys(ids))


def _recover_material(model, *, conversation, latest, turn_id, opening, context,
                      source_treatments, source_disagreements, detail_review_state,
                      detail_coverage, grounded, active_disputes, dispute_audit,
                      execution, review_scope):
    """Recover owned source conflicts and localized omissions once before any effects."""
    if not context:
        return grounded, active_disputes, source_treatments
    slots = context["slots"]
    _record_slots(slots, grounded.details)
    stages = execution["stages"]
    events = execution["semantic_recovery"] = {
        "contract": "bounded_material_recovery_v1",
        "source_reconsideration": {"state": "not_needed"},
        "omission_recovery": {"state": "not_needed"},
    }
    original_payload, latest_sources, prior_sources = addressed_sources(
        conversation.messages, latest)
    initial_assignment_ids = {row["id"] for row in active_disputes}
    changed_sources = ()
    disputes_rechecked = False

    def check_disputes(phase, *, changed=()):
        assessed, status, audit = {}, {}, []
        checked = _conditional_read(
            model, phase, verify_disputes,
            candidates=context["dispute_proposals"], earlier=conversation.messages,
            latest=latest, active_disputes=conversation.open_disputes,
            audit=audit, source_treatments=source_treatments, review_scope=review_scope,
            coverage=assessed, review_status=status, review_state=context["dispute_review_state"],
            recheck_source_ids=changed if context["dispute_review_state"] else ())
        if checked is not None:
            context["accepted_disputes"] = checked
            dispute_audit[:] = audit
            stages["dispute_review"] = _dispute_review_execution(checked, status, assessed)
        return checked

    def check_details(phase, *, changed=()):
        return _conditional_read(
            model, phase, verify_material_grounding,
            candidates=context["detail_proposals"], opening=opening,
            earlier=conversation.messages, latest=latest, active_disputes=active_disputes,
            prior_material=conversation.open_material,
            current_matter_id=conversation.current_matter_id,
            source_treatments=source_treatments, review_scope=review_scope,
            active_material=conversation.open_material, coverage=detail_coverage,
            review_state=detail_review_state,
            recheck_source_ids=changed if detail_review_state else ())

    def hold_changed(reason, *, hold_disputes):
        nonlocal grounded, active_disputes
        if hold_disputes:
            affected = _affected_proposals(
                context["dispute_proposals"], changed_sources, latest_sources, prior_sources)
            context["accepted_disputes"] = tuple(
                candidate for candidate in context["accepted_disputes"]
                if candidate not in affected)
            affected_ids = {f"C{index}" for index, candidate in enumerate(
                context["dispute_proposals"], 1) if candidate in affected}
            dispute_audit[:] = [row for row in dispute_audit
                                if row["candidate_id"] not in affected_ids]
            dispute_audit.extend(_unread_proposal(candidate, f"C{index}", reason, kind="dispute")
                                 for index, candidate in enumerate(context["dispute_proposals"], 1)
                                 if candidate in affected)
            stage = stages["dispute_review"]
            _partial_coverage(stage["account_coverage"], reason)
            stage.update(accepted=len(context["accepted_disputes"]),
                         unread=len(affected_ids))
            if not context["accepted_disputes"]:
                stage["state"] = "partial"
        previous_ids = initial_assignment_ids | {row["id"] for row in active_disputes}
        active_disputes = _preview_disputes(
            conversation, context["accepted_disputes"], turn_id, slots)
        affected = _affected_proposals(
            context["detail_proposals"], changed_sources, latest_sources, prior_sources,
            previous_ids - {row["id"] for row in active_disputes})
        grounded = _hold_affected_grounding(
            grounded, context["detail_proposals"], affected, opening, reason,
            opening_affected=bool(changed_sources))
        _partial_coverage(detail_coverage, reason)

    if source_disagreements:
        by_id = {f"C{index}": candidate for index, candidate in enumerate(
            context["dispute_proposals"], 1)}
        by_id.update({f"D{index}": candidate for index, candidate in enumerate(
            context["detail_proposals"], 1)})
        selected = []
        for diagnostic in source_disagreements:
            identity = diagnostic.get("source_id")
            candidate_id = diagnostic.get("candidate_id")
            candidate = by_id.get(candidate_id)
            expected = asdict(opening) if candidate_id == "O1" else (
                asdict(candidate) if candidate is not None else None)
            if (identity not in source_treatments
                    or diagnostic.get("supplies_account_content") is not True
                    or diagnostic.get("content_role") != source_treatments[identity]["content_role"]
                    or diagnostic.get("proposal") != expected
                    or identity not in candidate_account_ids(
                        candidate, latest_sources, prior_sources)):
                raise SchemaViolation(
                    "Source reconsideration has no owned typed review disagreement")
            selected.append(identity)
        selected = tuple(dict.fromkeys(selected))
        event = events["source_reconsideration"]
        event["source_ids"] = list(selected)
        try:
            result = _conditional_read(
                model, "source_reconsideration:source_owner", reconsider_account_sources,
                payload=original_payload, latest_turn_id=turn_id,
                source_treatments=source_treatments, source_ids=selected)
            if result is None:
                event["state"] = "budget_exhausted"
                _partial_coverage(stages["dispute_review"]["account_coverage"],
                                  "Source-purpose reconsideration remains unfinished.")
                _partial_coverage(
                    detail_coverage, "Source-purpose reconsideration remains unfinished.")
                return grounded, active_disputes, source_treatments
            source_treatments, changed_sources = result
            event.update(state="changed" if changed_sources else "unchanged",
                         changed_source_ids=list(changed_sources))
            if changed_sources:
                checked = check_disputes(
                    "source_reconsideration:dispute_review", changed=changed_sources)
                if checked is None:
                    hold_changed(
                        "Source-dependent record review remains unfinished.", hold_disputes=True)
                    event["state"] = "partial"
                    return grounded, active_disputes, source_treatments
                disputes_rechecked = True
                previous = active_disputes
                active_disputes = _preview_disputes(conversation, checked, turn_id, slots)
                if any(row not in active_disputes for row in previous):
                    detail_review_state.clear()
                checked_details = check_details(
                    "source_reconsideration:detail_review", changed=changed_sources)
                if checked_details is None:
                    hold_changed(
                        "Source-dependent material review remains unfinished.", hold_disputes=False)
                    event["state"] = "partial"
                    return grounded, active_disputes, source_treatments
                grounded = checked_details
                _record_slots(slots, grounded.details)
                # Both owners now cache the revised purpose catalogue. A later
                # omission review should only revisit its additional dependencies.
                changed_sources = ()
        except (ConfigurationError, TierUnavailable):
            raise
        except ModelError as exc:
            event.update(state="partial", failure=type(exc).__name__)
            hold_changed(
                "Source-dependent record review could not be confirmed.",
                hold_disputes=not disputes_rechecked)
            return grounded, active_disputes, source_treatments

    gaps = {
        "dispute": _localized_omission(
            stages["dispute_review"]["account_coverage"], review_scope, source_treatments),
        "detail": _localized_omission(detail_coverage, review_scope, source_treatments),
    }
    if not any(gaps.values()):
        return grounded, active_disputes, source_treatments
    event = events["omission_recovery"]
    event.update(state="started", source_ids={
        key: list(value) for key, value in gaps.items() if value})
    arguments = {"earlier": conversation.messages, "latest": latest,
                 "current_matter_id": conversation.current_matter_id,
                 "source_treatments": source_treatments}
    before_omission_disputes = active_disputes
    for kind in ("dispute", "detail"):
        if not gaps[kind]:
            continue
        coverage = (stages["dispute_review"]["account_coverage"]
                    if kind == "dispute" else detail_coverage)
        retained = context["accepted_disputes"] if kind == "dispute" else grounded.details
        recovery_scope = {"review_scope": deepcopy(review_scope),
                          "missing_source_ids": list(gaps[kind]), "reason": coverage["reason"],
                          "retained_proposals": [asdict(row) for row in retained]}
        diagnostics = {}
        additions = ()
        try:
            reader_arguments = dict(
                arguments, diagnostics=diagnostics, recovery_scope=recovery_scope)
            if kind == "dispute":
                reader_arguments["prior_disputes"] = conversation.open_disputes
                reader = extract_disputes
            else:
                reader_arguments.update(
                    disputes=active_disputes, prior_material=conversation.open_material)
                reader = extract_details
            additions = _conditional_read(
                model, f"omission_recovery:{kind}_reader", reader, **reader_arguments)
            if additions is None:
                event[kind] = "budget_exhausted"
                continue
            key = f"{kind}_proposals"
            prior = context[key]
            context[key] = (*prior, *(row for row in additions if row not in prior))
            stage = stages[f"{kind}_extraction"]
            _extend_reader_execution(stage, context[key], diagnostics)
            if kind == "dispute":
                checked = check_disputes(
                    "omission_recovery:dispute_review", changed=changed_sources)
                if checked is not None:
                    previous = active_disputes
                    active_disputes = _preview_disputes(conversation, checked, turn_id, slots)
                    if any(row not in active_disputes for row in previous):
                        detail_review_state.clear()
            else:
                checked = check_details("omission_recovery:detail_review", changed=changed_sources)
                if checked is not None:
                    grounded = checked
                    _record_slots(slots, grounded.details)
            event[kind] = "reviewed" if checked is not None else "review_budget_exhausted"
            if checked is None:
                reason = "The additional proposal's independent review remains unfinished."
                pending = set(context[key]) - set(prior)
                if kind == "dispute":
                    dispute_audit.extend(
                        _unread_proposal(row, f"C{index}", reason, kind="dispute")
                        for index, row in enumerate(context[key], 1) if row in pending)
                    stages["dispute_review"]["unread"] += len(pending)
                else:
                    grounded = _hold_affected_grounding(
                        grounded, context[key], pending, opening, reason)
        except (ConfigurationError, TierUnavailable):
            raise
        except ModelError as exc:
            event[kind] = type(exc).__name__
            _partial_coverage(coverage, "Recovery of missing material could not be confirmed.")
            if additions:
                key = f"{kind}_proposals"
                pending = set(context[key]) - set(prior)
                reason = "The additional proposal's independent review could not be confirmed."
                if kind == "dispute":
                    dispute_audit.extend(
                        _unread_proposal(row, f"C{index}", reason, kind="dispute")
                        for index, row in enumerate(context[key], 1) if row in pending)
                    stages["dispute_review"]["unread"] += len(pending)
                else:
                    grounded = _hold_affected_grounding(
                        grounded, context[key], pending, opening, reason)
    if active_disputes != before_omission_disputes and not gaps["detail"]:
        try:
            checked = check_details("omission_recovery:detail_review", changed=changed_sources)
            if checked is not None:
                grounded = checked
                _record_slots(slots, grounded.details)
                event["detail"] = "reviewed"
            else:
                event["detail"] = "review_budget_exhausted"
                _partial_coverage(detail_coverage, "Final material coverage remains unfinished.")
        except (ConfigurationError, TierUnavailable):
            raise
        except ModelError as exc:
            event["detail"] = type(exc).__name__
            unavailable = {row["id"] for row in before_omission_disputes} - {
                row["id"] for row in active_disputes}
            affected = _affected_proposals(
                context["detail_proposals"], (), latest_sources, prior_sources, unavailable)
            grounded = _hold_affected_grounding(
                grounded, context["detail_proposals"], affected, opening,
                "Final material assignment review could not be confirmed.")
            _partial_coverage(detail_coverage, "Final material coverage could not be confirmed.")
    if active_disputes != before_omission_disputes and event.get("detail") != "reviewed":
        unavailable = {row["id"] for row in before_omission_disputes} - {
            row["id"] for row in active_disputes}
        affected = _affected_proposals(
            context["detail_proposals"], (), latest_sources, prior_sources, unavailable)
        grounded = _hold_affected_grounding(
            grounded, context["detail_proposals"], affected, opening,
            "Final material assignment review remains unfinished.")
        _partial_coverage(detail_coverage, "Final material coverage remains unfinished.")
    completed = all(event.get(kind) == "reviewed"
                    for kind in ("dispute", "detail") if kind in event)
    event["state"] = "reviewed" if completed else "partial"
    return grounded, active_disputes, source_treatments


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
                              search_results={row["id"]: results[row["id"]]
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
                 session_current=None, recovery_limit: int = 8) -> None:
        self.store = store
        self.model = model
        self.legal_search = legal_search
        self.session_current = session_current
        self.recovery_limit = recovery_limit

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
            prior = _saved_reply(matter, turn.turn_id, offer_digest, store=self.store)
            if prior is not None:
                return BrainOutput(prior)
        if (turn.expected_version is not None and matter.brain_ready
                and turn.expected_version != matter.version):
            raise BrainRefused(409, "The matter changed; reload it before sending another message",
                               code="stale_version")
        if turn.turn_id in matter.turns_applied:
            raise BrainRefused(409, "This turn already belongs to an earlier response")
        counted_model = _CountedModel(self.model, recovery_limit=self.recovery_limit)
        revision_reader = getattr(self.legal_search, "revision", None)
        try:
            corpus_revision = revision_reader() if callable(revision_reader) else None
        except Exception:  # noqa: BLE001 -- unknown freshness disables research reuse
            corpus_revision = None
        try:
            if persisted:
                conversation, before_disputes, before_details = _current_records(
                    self.store, matter, corpus_revision)
            else:
                conversation = Conversation((), progress=project_work(matter))
                before_disputes, before_details = _record_projections(matter, ())
            source_treatments = _saved_source_treatments(matter, conversation)
            plan = interpret(counted_model, conversation, turn.message)
            execution = _material_execution(turn, matter, offer_digest, plan)
            _mutation_authorities(execution, conversation, plan, turn.message)
            dispute_audit: list[dict] = []
            review_scope = _execution_review_scope(execution, conversation.progress)
            execution["review_scope"] = deepcopy(review_scope)
            detail_account_coverage: dict = {}
            detail_review_state: dict = {}
            recovery_context: dict = {}
            source_disagreements: list[dict] = []
            source_reviewed = False
            if plan.material_review or plan.opening.ready:
                source_payload, _, _ = addressed_sources(conversation.messages, turn.message)
                source_treatments = classify_account_sources(
                    counted_model, payload=source_payload, latest_turn_id=turn.turn_id)
                source_reviewed = True
                execution["stages"]["source_classification"] = {"state": "returned"}
                candidates, active_disputes = _read_material(
                    counted_model, conversation, turn.message, turn.turn_id, dispute_audit,
                    source_treatments=source_treatments, execution=execution["stages"],
                    review_scope=review_scope, recovery_context=recovery_context,
                    source_disagreements=source_disagreements)
                if any(not reader_admission_checked(execution["stages"][stage]) for stage in (
                        "dispute_extraction", "detail_extraction")):
                    raise BrainRefused(
                        503, "NM could not confirm that the required material reading "
                        "finished. Please try again later.", code="material_execution_unconfirmed")
            else:
                candidates, active_disputes = (), conversation.open_disputes
            grounded = verify_material_grounding(
                counted_model, candidates=candidates, opening=plan.opening,
                earlier=conversation.messages, latest=turn.message,
                active_disputes=active_disputes,
                prior_material=conversation.open_material,
                current_matter_id=conversation.current_matter_id,
                source_treatments=source_treatments,
                review_scope=review_scope if source_reviewed else None,
                active_material=conversation.open_material, coverage=detail_account_coverage,
                source_disagreements=source_disagreements, review_state=detail_review_state)
            if source_reviewed:
                grounded, active_disputes, source_treatments = _recover_material(
                    counted_model, conversation=conversation, latest=turn.message,
                    turn_id=turn.turn_id, opening=plan.opening, context=recovery_context,
                    source_treatments=source_treatments, source_disagreements=source_disagreements,
                    detail_review_state=detail_review_state,
                    detail_coverage=detail_account_coverage,
                    grounded=grounded, active_disputes=active_disputes,
                    dispute_audit=dispute_audit, execution=execution, review_scope=review_scope)
            requested_review = source_reviewed
            # The coverage owner adds validation_issue only when no valid
            # independent assessment survives. A valid unassessed judgment
            # still proves review ran, while an empty envelope does not.
            coverage_reviewed = (
                detail_account_coverage.get("contract") == ACCOUNT_COVERAGE_CONTRACT
                and detail_account_coverage.get("review_scope") == review_scope
                and "validation_issue" not in detail_account_coverage)
            rejected = list(grounded.rejected_proposals)
            held = list(grounded.withheld_proposals)
            unread = list(grounded.unread_proposals)
            checked_items = len(grounded.details) + len(rejected) + len(held)
            if plan.opening.ready and grounded.opening_supported:
                checked_items += 1
            detail_status = {
                "state": ("partial" if unread or held else
                          "checked" if coverage_reviewed or checked_items else
                          "partial" if requested_review else "not_requested"),
                "checked_items": checked_items, "accepted_items": len(grounded.details),
                "rejected_items": len(rejected), "withheld_items": len(held),
                "unread_items": len(unread),
                "unread_candidate_ids": [item["candidate_id"] for item in unread]}
            execution["stages"]["detail_review"] = {
                "state": ("checked" if checked_items or coverage_reviewed else
                          "partial" if requested_review else "not_run"),
                "accepted": len(grounded.details), "rejected": grounded.rejected_details,
                "held": grounded.withheld_details, "unread": grounded.unread_details,
                "review_status": detail_status,
                "account_coverage": deepcopy(detail_account_coverage),
                "opening_proposed": plan.opening.ready,
                "opening_unread": grounded.opening_unread}
            coverage_states = [execution["stages"][name].get("account_coverage", {}).get("state")
                               for name in ("dispute_review", "detail_review")]
            execution["semantic_coverage"] = ("complete" if all(
                state == "complete" for state in coverage_states) else
                "partial" if any(state in ("complete", "partial") for state in coverage_states)
                else "unassessed")
            candidates = (recovery_context.get("accepted_disputes", tuple(
                candidate for candidate in candidates if candidate.kind == "dispute"))
                + grounded.details)
        except IncompleteConversation as exc:
            logging.getLogger(__name__).warning("Saved conversation validation failed: %s", exc)
            raise BrainRefused(
                409, "The saved conversation or its sources could not be verified. "
                "Reload this conversation; if this continues, contact the administrator.",
                gate_id="G-CORE", gate_state="invalid") from exc
        except ContextOverflow as exc:
            raise BrainRefused(
                413, "The complete conversation does not fit the configured "
                "model. Please contact the administrator to increase its "
                "context capacity.",
                retryable=False) from exc
        except ModelError as exc:
            logging.getLogger(__name__).warning(
                "Conversation analysis was rejected before saving: %s", exc)
            if isinstance(exc, ConfigurationError):
                why = ("The AI service is not configured for this analysis. "
                       "Please contact the application administrator.")
                retryable = False
            elif isinstance(exc, ProviderUnavailable):
                why = ("The AI analysis is temporarily unavailable. Please try "
                       "again later; if this persists, contact the administrator.")
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
        needs_work, asked = _response_mode(plan)
        material = [candidate.recorded(
            turn.turn_id, recovery_context.get("slots", {}).get(candidate, index))
                    for index, candidate in enumerate(candidates, start=1)]
        if "mutation_authorities" in execution:
            bindings = dict(grounded.mutation_bindings)
            for candidate in candidates:
                if candidate.kind == "dispute" and candidate.relation != "new":
                    matches = [decision.get("mutation_authority") for decision in dispute_audit
                               if decision.get("verdict") == "accept"
                               and decision.get("proposal") == asdict(candidate)]
                    if len(matches) != 1:
                        raise BrainRefused(409, "The admitted revision proof is missing",
                                           gate_id="G-CORE", gate_state="invalid")
                    bindings[candidate] = matches[0]
            try:
                for candidate, proposal in zip(candidates, material, strict=True):
                    if candidate.relation == "new":
                        continue
                    if candidate not in bindings:
                        raise SchemaViolation("The admitted revision proof is missing")
                    proposal["mutation_authority"] = bind_record_mutation(
                        proposal, execution["mutation_authorities"], binding=bindings[candidate])
            except SchemaViolation as exc:
                raise BrainRefused(409, "The admitted revision proof could not be verified",
                                   gate_id="G-CORE", gate_state="invalid") from exc
        for item in material:
            if item["kind"] != "dispute":
                item["grounding"] = "advocate_semantic_v1"
        opening_supported = grounded.opening_supported
        opening = plan.opening
        if opening.ready and not opening_supported and not grounded.opening_unread:
            alternatives = []
            try:
                repaired = _conditional_read(
                    counted_model, "opening_recovery:reader", repair_opening,
                    conversation=conversation, latest=turn.message, rejected=opening,
                    rejection_reason=grounded.opening_reason)
                if repaired is not None:
                    alternatives.append(repaired)
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
                    checked = _conditional_read(
                        counted_model, "opening_recovery:review", verify_material_grounding,
                        candidates=(), opening=proposal,
                        earlier=conversation.messages, latest=turn.message,
                        source_treatments=source_treatments)
                except (ModelError, ContextOverflow) as exc:
                    logging.getLogger(__name__).warning(
                        "Opening correction could not be checked: %s", exc)
                    continue
                if checked is not None and checked.opening_supported:
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
                   "text": "Your message is being worked on.", "thread": None, "by_when": None,
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
                        "state": "partial" if (grounded.withheld_details
                            or grounded.unread_details or source_reviewed
                            and (execution["semantic_coverage"] != "complete" or any(
                                execution["stages"][name].get("state") == "partial"
                                for name in ("dispute_extraction", "detail_extraction"))))
                            else "ok",
                        "rejected_details": grounded.rejected_details,
                        "withheld_details": grounded.withheld_details,
                        "unread_details": grounded.unread_details,
                        "rejected_proposals": list(grounded.rejected_proposals),
                        "withheld_proposals": list(grounded.withheld_proposals),
                        "unread_proposals": list(grounded.unread_proposals),
                        "dispute_review": dispute_audit,
                        "source_treatments": source_treatments if source_reviewed else {},
                        "source_treatment_contract": SOURCE_TREATMENT_CONTRACT
                        if source_reviewed else "",
                        "execution": execution,
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
                    self.store, updated, corpus_revision,
                    source_treatments=source_treatments)
                execution["effects"] = {
                    "disputes": _material_effects(
                        before_disputes, disputes, material, kind="disputes", turn_id=turn.turn_id),
                    "details": _material_effects(
                        before_details, details, material, kind="details", turn_id=turn.turn_id),
                }
                # Canonical operations require both their returned reader and
                # independent admission review. Wider coverage may remain partial.
                for kind, reader, reviewer in (
                        ("disputes", "dispute_extraction", "dispute_review"),
                        ("details", "detail_extraction", "detail_review")):
                    if (execution["effects"][kind]["operations"]
                            and (not reader_admission_checked(execution["stages"][reader])
                                 or execution["stages"][reviewer]["state"] != "checked")):
                        raise BrainRefused(
                            503, "NM could not verify execution evidence for the proposed "
                            "record changes. Please try again later.",
                            code="material_execution_unconfirmed",
                            gate_id="G-CORE", gate_state="unconfirmed")
                execution["rejected_proposals"] = {
                    "disputes": [entry["candidate_id"] for entry in dispute_audit
                                 if entry["verdict"] == "reject"
                                 and "admission_issue" not in entry],
                    "details": [entry["candidate_id"] for entry in grounded.rejected_proposals],
                }
                execution["withheld_proposals"] = {
                    "disputes": [entry["candidate_id"] for entry in dispute_audit
                                 if entry.get("admission_issue")
                                 in ("mutation_scope", "required_restoration_peer_unavailable")],
                    "details": [entry["candidate_id"] for entry in grounded.withheld_proposals]}
                execution["unread_proposals"] = {
                    "disputes": [entry["candidate_id"] for entry in dispute_audit
                                 if entry.get("admission_issue") == "review_unavailable"],
                    "details": [entry["candidate_id"] for entry in grounded.unread_proposals]}
                execution["record_changes"] = _record_changes(
                    before_disputes, before_details, disputes, details, execution)
                execution["display"] = _execution_display(execution)
                execution["gate_diagnostics"] = _execution_diagnostics(execution)
                # This is evidence of the checked proposed state while writing;
                # the same receipt is persisted with the final reply below.
                details["coverage"]["execution"] = execution
                current, contexts = _project_research(
                    updated, disputes, details, corpus_revision, plan,
                    prior_conversation=conversation.messages,
                    source_treatments=source_treatments)
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
                        prior_conversation=conversation.messages,
                        source_treatments=source_treatments)
                    response["metrics"] = counted_model.metrics()
            if continuation_indexes(plan):
                checked = requirements_record(
                    updated, disputes=disputes, material=details,
                    corpus_revision=corpus_revision,
                    prior_conversation=conversation.messages,
                    source_treatments=source_treatments)
                current, _ = _project_research(
                    updated, disputes, details, corpus_revision, plan,
                    prior_conversation=conversation.messages,
                    source_treatments=source_treatments)
                continuation = continue_conversation(
                    counted_model, conversation=conversation, latest=turn.message,
                    latest_turn_id=turn.turn_id, plan=plan, disputes=disputes,
                    material=details, requirements=checked, research=current,
                    progress=conversation.progress,
                    source_treatments=source_treatments,
                    execution_receipt=execution).as_dict()
                _request_fulfillment(execution, continuation)
                execution["gate_diagnostics"] = _execution_diagnostics(execution)
                display = _execution_display(execution)
                execution["display"] = display
                snapshot = record_result_snapshot(
                    execution_receipt=execution,
                    record_catalogue=_record_catalogue(disputes, details))
                continuation = _canonical_record_acknowledgements(
                    continuation, execution, record_catalogue=snapshot["record_catalogue"])
                continuation = seal_progress(
                    continuation, matter_id=str(matter.id), turn_id=turn.turn_id,
                    plan=plan, prior_progress=conversation.progress,
                    execution_receipt=execution, record_snapshot=snapshot)
                elements = _continuation_elements(plan, continuation)
                if display is not None:
                    elements.append(deepcopy(display["element"]))
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
            # Release one final reply snapshot. Notices are part of the visible
            # transcript, so validate after composing them, before committing.
            row["elements"] = response["elements"]
            progress = project_work(
                replace(updated, version=matter.version),
                prior_conversation=conversation.messages, allow_prepared_turn_id=turn.turn_id)
            if progress["state"] != "ok":
                raise IncompleteConversation("The new work progress cannot be verified")
            # This compatibility field is a projection, never a second owner.
            row["active_work_after"] = progress["active_work"]
            response["metrics"] = counted_model.metrics()
        except (IncompleteConversation, SchemaViolation, ExecutionEvidenceInvalid) as exc:
            raise BrainRefused(
                409, "The saved context or its sources could not be verified. "
                "Reload this conversation before continuing.",
                gate_id=("G-EFFECT" if isinstance(exc, SchemaViolation) else "G-CORE"),
                gate_state=("unsupported" if isinstance(exc, SchemaViolation) else "invalid"),
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
            # No committed receipt is released unless this version-checked
            # atomic save returns, or durable lookup confirms the exact turn.
            execution["persistence"] = "committed"
            self.store.commit(updated, expected_version=matter.version)
        except Exception as exc:  # noqa: BLE001 -- durable lookup resolves a lost save acknowledgement
            try:
                current = self.store.load(matter_id)
            except Exception:  # noqa: BLE001 -- inability to confirm a save is not success
                raise BrainRefused(
                    503, "NM could not confirm that this turn was saved. Please try again later.",
                    committed="unconfirmed", code="brain_commit_unconfirmed",
                    gate_id="G-COMMIT", gate_state="unconfirmed") from exc
            if current is not None and current.advocate_id == turn.advocate_id:
                prior = _saved_reply(current, turn.turn_id, offer_digest, store=self.store)
                if prior is not None:
                    # Delivery reuses the saved reply, but this attempt already
                    # ran its models. A replay found before analysis runs none.
                    prior["metrics"] = counted_model.metrics()
                    return BrainOutput(prior)
            if isinstance(exc, StaleWrite):
                exc.gate_diagnostic = gate_diagnostic("G-COMMIT", "failed")
                raise
            raise BrainRefused(
                503, "NM could not confirm that this turn was saved. Please try again later.",
                committed="unconfirmed", code="brain_commit_unconfirmed",
                gate_id="G-COMMIT", gate_state="unconfirmed") from exc
        return BrainOutput(response)
