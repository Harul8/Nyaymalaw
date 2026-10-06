"""Code-owned record execution evidence, separate from semantic fulfillment.

This module validates selected declared outcomes. It cannot infer an operation
claim from prose, decide whether a result satisfies a legal/requested meaning,
or certify a save from a prepared receipt. The caller owns those boundaries.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from copy import deepcopy

from nm.brain.evidence_rendering import EVIDENCE_EXPRESSION_CONTRACT
from nm.brain.mutation_contracts import AUTHORITY_CONTRACT, _checked_ledger
from nm.shared.model_port import SchemaViolation, require_schema

RECORD_OUTCOME_CONTRACT = "checked_record_outcome_v1"
SCOPED_RECORD_OUTCOME_CONTRACT = "scoped_record_outcome_v2"
RECORD_ACKNOWLEDGEMENT_CONTRACT = "record_acknowledgement_v3"
_LEGACY_ACKNOWLEDGEMENT_CONTRACT = "record_acknowledgement_v2"
RECORD_OUTCOME_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "block_id", "effect_ids", "current_record_ids", "reason"],
    "properties": {
        "status": {
            "type": "string",
            "enum": ["none", "performed", "already_current", "review_no_change", "unresolved"],
        },
        "block_id": {"type": "string"},
        "effect_ids": {"type": "array", "items": {"type": "string"}},
        "current_record_ids": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
}
_RELATIONS = frozenset({"new", "adds", "corrects", "contradicts", "withdraws"})
_KINDS = {
    "disputes": ("dispute_extraction", "dispute_review"),
    "details": ("detail_extraction", "detail_review"),
}


class ExecutionEvidenceInvalid(ValueError):
    """Malformed code-owned evidence; a caller must refuse core integrity."""


def _owned_ids(value: object, field: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        raise ExecutionEvidenceInvalid(f"{field} needs unique nonempty owned IDs")
    return value


def _selected_ids(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise SchemaViolation(f"record_outcome.{field} needs nonempty selected IDs")
    return value


def _stage(receipt: dict, name: str) -> str:
    stages = receipt.get("stages")
    row = stages.get(name) if isinstance(stages, dict) else None
    if not isinstance(row, dict) or not isinstance(row.get("state"), str):
        raise ExecutionEvidenceInvalid(f"The execution stage {name!r} is unreadable")
    return row["state"]


def _receipt(receipt: object) -> dict | None:
    if receipt is None:
        return None
    if (
        not isinstance(receipt, dict)
        or receipt.get("contract") != "material_execution_v1"
        or not isinstance(receipt.get("id"), str)
        or not receipt["id"].strip()
        or receipt.get("persistence") not in ("prepared_for_commit", "committed")
        or not isinstance(receipt.get("effects"), dict)
        or not isinstance(receipt.get("requests"), list)
    ):
        raise ExecutionEvidenceInvalid("The material execution receipt is unreadable")
    owner = receipt.get("owner")
    if (
        not isinstance(owner, dict)
        or any(
            not isinstance(owner.get(field), str) or not owner[field].strip()
            for field in ("matter_id", "advocate_id", "turn_id", "offer_digest")
        )
        or type(receipt.get("expected_version")) is not int
        or receipt["expected_version"] < 0
        or type(receipt.get("resulting_version")) is not int
        or receipt["resulting_version"] != receipt["expected_version"] + 1
    ):
        raise ExecutionEvidenceInvalid("The material execution owner/version is unreadable")
    # Equality with the real authenticated owner, original offer and store
    # version belongs to the caller, which has those authoritative inputs.
    return receipt



def _scoped_outcome_contract(receipt: dict | None) -> bool:
    if receipt is None:
        return False
    version = receipt.get("scope_outcome_contract")
    if version not in (None, SCOPED_RECORD_OUTCOME_CONTRACT):
        raise ExecutionEvidenceInvalid("The scoped record outcome contract is unsupported")
    return version == SCOPED_RECORD_OUTCOME_CONTRACT


def _owned_mutation_scopes(request: dict, receipt: dict | None) -> list[dict]:
    """Select permission from the intact turn ledger, never writer metadata."""
    if receipt is None:
        return []
    ledger = receipt.get("mutation_authorities")
    version = receipt.get("mutation_authority_contract")
    if ledger is None and version is None:
        return []
    if version != AUTHORITY_CONTRACT:
        raise ExecutionEvidenceInvalid("The requested mutation authority is unreadable")
    try:
        _checked_ledger(ledger)
    except SchemaViolation as exc:
        raise ExecutionEvidenceInvalid(str(exc)) from exc
    if (ledger["owner"] != receipt["owner"]
            or ledger["expected_version"] != receipt["expected_version"]):
        raise ExecutionEvidenceInvalid("The mutation scope has a different turn owner or snapshot")
    index = request.get("request_index")
    if type(index) is not int or len([
            row for row in receipt["requests"]
            if isinstance(row, dict) and row.get("request_index") == index]) != 1:
        raise ExecutionEvidenceInvalid("The mutation scope has no exact execution request owner")
    return [row for row in ledger["authorities"]
            if row["request_index"] == index
            and any(relation != "new" for relation in row["permitted_relations"])]


def request_requires_record_outcome(request: dict, receipt: dict | None = None) -> bool:
    """An owned non-new scope cannot disappear through redundant goal metadata.

    Fresh writer choices may derive this fact from any intact owned ledger.
    Saved validation separately branches on scope_outcome_contract so historical
    unstamped none outcomes retain their original untracked meaning.
    """
    requirement = request.get("record_requirement")
    return (request.get("response_mode") == "record_acknowledgement"
            or isinstance(requirement, dict)
            and requirement.get("kind") in ("review", "change")
            or bool(_owned_mutation_scopes(request, receipt)))


def _unit_execution_request(unit: dict, receipt: dict | None) -> dict | None:
    if receipt is None:
        return None
    requests = [row for row in receipt["requests"] if isinstance(row, dict)
                and row.get("request_index") == unit["request_index"]]
    if len(requests) != 1 and _scoped_outcome_contract(receipt):
        raise ExecutionEvidenceInvalid("The declared result has no exact execution request owner")
    return requests[0] if len(requests) == 1 else None


def _matches_mutation_scope(effect: dict, scopes: list[dict]) -> bool:
    targets = set(effect["target_record_ids"])
    permitted = {target for scope in scopes
                 if effect["relation"] in scope["permitted_relations"]
                 for target in scope["target_ids"]}
    return (effect["relation"] != "new" and bool(targets) and targets <= permitted)


def _scoped_work_complete(unit: dict) -> bool:
    work = unit.get("work", {})
    aliases = {"$work", work.get("existing_id"), work.get("progress_id")} - {None, ""}
    return unit.get("sufficiency", {}).get("status") == "complete" or any(
        row.get("status") == "complete" and row.get("target_id") in aliases
        for row in unit.get("progress_updates", []))


def _complete_account_scope_targets(scopes: list[dict]) -> set[str]:
    return {target for scope in scopes
            if scope["authority_kind"] == "account_contribution"
            and scope["target_scope"] == "exact"
            for target in scope["target_ids"]}


def _represented_scope_targets(effects: list[dict], scopes: list[dict]) -> set[str]:
    return {target for scope in scopes for effect in effects
            if effect["relation"] in scope["permitted_relations"]
            for target in effect["target_record_ids"] if target in scope["target_ids"]}


def reader_admission_checked(stage: object) -> bool:
    """Recognize validated reader output without inferring complete coverage.

    Historical returned readers retain their original receipt contract. A
    partial reader certifies only its positively admitted proposals when the
    code-owned counts and read disposition agree. This does not certify that
    every requested source or the complete account was read.
    """
    if not isinstance(stage, dict):
        return False
    if stage.get("state") == "returned":
        return True
    count = stage.get("admissible_proposals")
    status = stage.get("read_status")
    return (stage.get("state") == "partial"
            and stage.get("proposal_validation") == "owned_extraction_proposals_v1"
            and type(count) is int and count > 0
            and type(stage.get("proposals")) is int and stage["proposals"] == count
            and isinstance(status, dict) and status.get("state") == "partial"
            and type(status.get("proposal_count")) is int and status["proposal_count"] == count)


def effect_catalogue(receipt: dict | None) -> dict[str, dict]:
    """Derive deterministic choices from actual owned projections and stages.

    An operation in a receipt is not automatically a performed active effect.
    Held, outside-owner, unchanged, unread and rejected outcomes are explicit.
    Kind-specific owning projection behavior controls target retirement:
    material contradictions preserve the target; a revised dispute formulation
    can replace its active predecessor while preserving its attributed history.
    """
    receipt = _receipt(receipt)
    if receipt is None:
        return {}
    result = {}
    for kind, (reader_name, review_name) in _KINDS.items():
        owned = receipt["effects"].get(kind)
        if not isinstance(owned, dict) or not isinstance(owned.get("operations"), list):
            raise ExecutionEvidenceInvalid(f"The owned {kind} effects are unreadable")
        activated = set(_owned_ids(owned.get("activated_record_ids"), f"{kind}.activated"))
        retired = set(_owned_ids(owned.get("retired_record_ids"), f"{kind}.retired"))
        held = set(_owned_ids(owned.get("held_record_ids"), f"{kind}.held"))
        outside = set(_owned_ids(owned.get("outside_owned_record_ids"), f"{kind}.outside"))
        if activated & retired or activated & held or activated & outside:
            raise ExecutionEvidenceInvalid("Active/retired/held effect identities conflict")
        reader_state = _stage(receipt, reader_name)
        reader_stage = receipt["stages"][reader_name]
        admitted = reader_admission_checked(reader_stage)
        if (reader_state == "partial" and admitted
                and len(owned["operations"]) > reader_stage["admissible_proposals"]):
            raise ExecutionEvidenceInvalid("Owned effects exceed admitted reader proposals")
        stages_checked = admitted and _stage(receipt, review_name) == "checked"
        domain_fields = (
            "before_record_ids",
            "after_record_ids",
            "before_held_record_ids",
            "after_held_record_ids",
        )
        domains = None
        if any(field in owned for field in domain_fields):
            if not all(field in owned for field in domain_fields):
                raise ExecutionEvidenceInvalid("Before/after ownership domains are incomplete")
            domains = {
                field: set(_owned_ids(owned[field], f"{kind}.{field}")) for field in domain_fields
            }
            before, after = domains["before_record_ids"], domains["after_record_ids"]
            before_held, after_held = (
                domains["before_held_record_ids"],
                domains["after_held_record_ids"],
            )
            if (
                before & before_held
                or after & after_held
                or activated != after - before
                or retired != before - after
            ):
                raise ExecutionEvidenceInvalid(
                    "Effects disagree with before/after ownership domains"
                )
            removed_from_domain = (before - after) | (before_held - after_held)
        else:
            # Old evidence can certify an owned retirement. It cannot invent
            # removal from an unrecorded held domain.
            removed_from_domain = retired
        seen = set()
        for operation in owned["operations"]:
            if not isinstance(operation, dict):
                raise ExecutionEvidenceInvalid("An owned effect operation is unreadable")
            record_id, relation = operation.get("result_id"), operation.get("relation")
            if (
                not isinstance(record_id, str)
                or not record_id.strip()
                or record_id in seen
                or relation not in _RELATIONS
            ):
                raise ExecutionEvidenceInvalid("Owned effect operation identities conflict")
            seen.add(record_id)
            targets = _owned_ids(operation.get("target_record_ids"), "effect.targets")
            retired_targets = _owned_ids(operation.get("retired_target_ids"), "effect.retired")
            if (
                not set(retired_targets) <= set(targets) & retired
                or (relation == "new" and targets)
                or (relation != "new" and not targets)
            ):
                raise ExecutionEvidenceInvalid("An effect's targets disagree with its projection")
            removed_targets = set(targets) & removed_from_domain
            references = operation.get("source_references")
            if (
                not isinstance(references, list)
                or not references
                or any(
                    not isinstance(row, dict)
                    or row.get("role") not in ("advocate", "nm")
                    or any(
                        not isinstance(row.get(field), str) or not row[field].strip()
                        for field in ("turn_id", "quoted")
                    )
                    for row in references
                )
            ):
                raise ExecutionEvidenceInvalid("An effect lacks attributable source references")
            actual = record_id in activated
            if relation == "withdraws":
                actual = bool(removed_targets) and record_id not in activated
            elif relation == "corrects":
                actual = actual and bool(removed_targets)
            elif relation == "contradicts" and kind == "details":
                actual = actual and not removed_targets
            # Dispute successor identity differs from material contradiction;
            # a generic retirement expectation would falsely reject valid work.
            performed = stages_checked and actual and record_id not in held | outside
            identity = {"receipt_id": receipt["id"], "kind": kind, "result_id": record_id}
            digest = hashlib.sha256(
                json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            effect_id = "rfx_" + digest[:32]
            if effect_id in result:
                raise ExecutionEvidenceInvalid("Code-owned effect identities conflict")
            result[effect_id] = {
                "id": effect_id,
                "receipt_id": receipt["id"],
                "kind": kind,
                "result_id": record_id,
                "relation": relation,
                "target_record_ids": list(targets),
                "retired_target_ids": list(retired_targets),
                "removed_target_ids": sorted(removed_targets),
                "activated": record_id in activated,
                "performed": performed,
                "reader_returned": _stage(receipt, reader_name) == "returned",
                "review_checked": _stage(receipt, review_name) == "checked",
                "source_references": deepcopy(references),
            }
            if reader_state == "partial":
                result[effect_id]["reader_admission_checked"] = admitted
    return result


class ReviewCompletionIncomplete(SchemaViolation):
    """Unsupported full-review completion, distinct from a false owned effect."""

    def __init__(self, reason: str, *, state: str = "unassessed") -> None:
        self.state = state
        super().__init__(reason)


def _owned_inherited_review_scope(unit: dict, receipt: dict | None) -> list[tuple[dict, str]]:
    """Only explicitly completed owned goals can supply inherited review evidence."""
    if receipt is None:
        return []
    scope = receipt.get("review_scope")
    if scope is None:
        return []
    if not isinstance(scope, dict) or not isinstance(scope.get("requests"), list):
        raise ExecutionEvidenceInvalid("The owned inherited review scope is unreadable")
    work = unit.get("work", {})
    completed = set()
    for update in unit.get("progress_updates", []):
        if update.get("status") != "complete":
            continue
        target = update.get("target_id")
        if target == "$work":
            target = work.get("existing_id") or work.get("progress_id")
        if isinstance(target, str) and target:
            completed.add(target)
    inherited = []
    for request in scope["requests"]:
        if not isinstance(request, dict):
            raise ExecutionEvidenceInvalid("An owned inherited review request is unreadable")
        requirement = request.get("record_requirement")
        task_id = request.get("task_id")
        if (request.get("request_index") == unit["request_index"] and task_id in completed
                and isinstance(requirement, dict) and requirement.get("kind") == "review"):
            inherited.append((requirement, task_id))
    return inherited


def validate_review_completion(
    unit: dict, receipt: dict | None, *, requirement: dict | None = None, task_id: str | None = None
) -> None:
    """Full requested review needs independently assessed omission coverage.

    This does not withhold an independently checked performed peer or a
    truthful partial response when wider review coverage is partial/unassessed.
    The caller may supply an inherited selected task's retained requirement;
    its complete requested scope must appear in the current owned assessment.
    """
    receipt = _receipt(receipt)
    if requirement is None and isinstance(receipt, dict):
        requests = [
            row
            for row in receipt.get("requests", [])
            if isinstance(row, dict) and row.get("request_index") == unit["request_index"]
        ]
        if len(requests) == 1:
            requirement = requests[0].get("record_requirement")
    request = _unit_execution_request(unit, receipt)
    scopes = (_owned_mutation_scopes(request, receipt)
              if request is not None and _scoped_outcome_contract(receipt) else [])
    scoped_review = task_id is None and bool(scopes) and (
        any(scope["authority_kind"] == "interpretation_review" for scope in scopes)
        or unit.get("record_outcome", {}).get("status") == "already_current")
    if ((not isinstance(requirement, dict) or requirement.get("kind") != "review")
            and not scoped_review):
        return
    work = unit.get("work", {})
    selected = (
        {task_id}
        if task_id is not None
        else {"$work", work.get("existing_id"), work.get("progress_id")} - {None, ""}
    )
    completing = (
        task_id is None
        and unit.get("record_outcome", {}).get("status")
        in ("performed", "already_current", "review_no_change")
    ) or (
        task_id is None and unit.get("sufficiency", {}).get("status") == "complete"
    ) or any(
        row.get("status") == "complete" and row.get("target_id") in selected
        for row in unit.get("progress_updates", [])
    )
    # A positive declared result certifies the requested review even when
    # prose sufficiency is partial. Narrower checked effects remain available
    # under unresolved, without turning them into whole-review fulfillment.
    if not completing:
        return
    receipt = _receipt(receipt)
    if receipt is None:
        raise ReviewCompletionIncomplete(
            "Full requested review completion needs owned independent account coverage"
        )
    for reader, review in _KINDS.values():
        if _stage(receipt, reader) != "returned" or _stage(receipt, review) not in (
            "checked",
            "no_candidates",
        ):
            raise ReviewCompletionIncomplete(
                "Full requested review completion needs actual reading and review"
            )
        stage = receipt["stages"][review]
        assessment = stage.get("account_coverage")
        if assessment is None:
            raise ReviewCompletionIncomplete(
                "Full requested review completion lacks independent account coverage"
            )
        if (
            not isinstance(assessment, dict)
            or assessment.get("contract") != "independent_account_coverage_v1"
            or assessment.get("state") not in ("complete", "partial", "unassessed")
        ):
            raise ExecutionEvidenceInvalid("Independent account coverage is unreadable")
        if assessment["state"] != "complete":
            raise ReviewCompletionIncomplete(
                "Full requested review completion has partial/unassessed account coverage",
                state=assessment["state"],
            )
        missing = assessment.get("missing_source_ids")
        if (
            not isinstance(missing, list)
            or missing
            or not isinstance(assessment.get("reason"), str)
            or not assessment["reason"].strip()
        ):
            raise ExecutionEvidenceInvalid(
                "Complete account coverage contradicts its checked assessment"
            )
        scope = assessment.get("review_scope")
        requests = scope.get("requests") if isinstance(scope, dict) else None
        covered = (
            [
                row
                for row in requests
                if isinstance(row, dict)
                and row.get("request_index") == unit["request_index"]
                and row.get("record_requirement") == requirement
                and ((not row.get("task_id")) if task_id is None else row.get("task_id") == task_id)
            ]
            if isinstance(requests, list)
            else []
        )
        if (not covered or scoped_review and (
                scope.get("mutation_authority_contract") != AUTHORITY_CONTRACT
                or scope.get("mutation_authorities") != receipt["mutation_authorities"])):
            raise ReviewCompletionIncomplete(
                "Full requested review completion lacks the exact requested account scope"
            )


def validate_record_outcome(
    unit: dict, receipt: dict | None, current_record_ids: Iterable[str]
) -> None:
    """Validate a declared outcome, normalizing only fully checked repetitions.

    Fresh writer schema must require record_outcome. Its absence here is an
    explicit historical/in-process compatibility path, not verified completion.
    current_record_ids must describe the checked result at THIS turn's snapshot.
    Replay of old performed work must not reconstruct it from today's state.
    Requested-effect and inherited-task matching are separate required gates.
    """
    if "record_outcome" not in unit:
        return
    outcome = unit["record_outcome"]
    require_schema(outcome, RECORD_OUTCOME_SCHEMA)
    status = outcome["status"]
    receipt = _receipt(receipt)
    stamped_scope = _scoped_outcome_contract(receipt)
    request = _unit_execution_request(unit, receipt)
    scopes = (_owned_mutation_scopes(request, receipt)
              if stamped_scope and request is not None else [])
    if (status == "none" and scopes
            and request_requires_record_outcome(request, receipt)):
        raise SchemaViolation(
            "The owned non-new mutation scope needs a declared record outcome, not none")
    blocks = {block["id"]: block for block in unit["blocks"]}
    if outcome["block_id"] not in blocks and (status != "none" or outcome["block_id"]):
        raise SchemaViolation("record_outcome.block_id must select its exact displayed owner")
    if status != "none" and not outcome["reason"].strip():
        raise SchemaViolation("record_outcome.reason must explain this requested result")
    selected = _selected_ids(outcome["effect_ids"], "effect_ids")
    current = _selected_ids(outcome["current_record_ids"], "current_record_ids")
    if isinstance(current_record_ids, (str, bytes)):
        raise ExecutionEvidenceInvalid("Current record ownership is unreadable")
    current_ids = set(current_record_ids)
    if any(not isinstance(identity, str) or not identity.strip() for identity in current_ids):
        raise ExecutionEvidenceInvalid("Current record ownership is unreadable")
    if not set(current) <= current_ids:
        raise SchemaViolation("record_outcome.current_record_ids must select active owned records")
    catalogue = effect_catalogue(receipt)
    if not set(selected) <= catalogue.keys():
        raise SchemaViolation(
            "record_outcome.effect_ids must select this turn's code-owned effects"
        )
    if any(not catalogue[identity]["performed"] for identity in selected):
        raise SchemaViolation("record_outcome selects an unread, unchanged or unadmitted effect")
    validate_review_completion(unit, receipt)
    inherited_reviews = _owned_inherited_review_scope(unit, receipt)
    for requirement, task_id in inherited_reviews:
        validate_review_completion(unit, receipt, requirement=requirement, task_id=task_id)
    # Both complete selections were checked before normalizing repetitions.
    # Owned receipt identities are never repaired; only model set-like choices
    # can repeat without adding or changing their meaning.
    selected = outcome["effect_ids"] = list(dict.fromkeys(selected))
    current = outcome["current_record_ids"] = list(dict.fromkeys(current))
    if status == "none":
        if selected or current:
            raise SchemaViolation("record_outcome none cannot carry operation/current-state claims")
        return
    if status == "performed":
        if not selected:
            raise SchemaViolation(
                "record_outcome performed needs effects, not current-state substitutes"
            )
        if scopes and not any(_matches_mutation_scope(catalogue[identity], scopes)
                              for identity in selected):
            raise SchemaViolation(
                "The selected effect does not match the owned mutation target and operation")
        if (scopes and _scoped_work_complete(unit)
                and not _complete_account_scope_targets(scopes) <= _represented_scope_targets(
                    [catalogue[identity] for identity in selected], scopes)):
            raise SchemaViolation(
                "Completed account mutation work lacks effects for every exact scoped target")
        # Every supplied current identity was checked above. Performed wording
        # derives from actual effects; redundant owned current selections add no
        # meaning and can be dropped without replacing or inventing an effect.
        outcome["current_record_ids"] = []
        for identity in selected:
            effect = catalogue[identity]
            if effect["activated"] and effect["result_id"] not in current_ids:
                raise SchemaViolation(
                    "The selected performed result is not in the checked active state"
                )
            if set(effect["removed_target_ids"]) & current_ids:
                raise SchemaViolation(
                    "The selected replacement/withdrawal did not retire its target"
                )
        return
    if status == "already_current":
        if selected or not current:
            raise SchemaViolation(
                "already_current needs current owned state, not a past operation claim"
            )
        if scopes and not set(current).intersection(
                target for scope in scopes for target in scope["target_ids"]):
            raise SchemaViolation("The already-current selection has no owned mutation target")
        if (scopes and _scoped_work_complete(unit)
                and not _complete_account_scope_targets(scopes) <= set(current)):
            raise SchemaViolation(
                "Completed account mutation work lacks current state for every exact scoped target")
        return
    if status == "review_no_change":
        if selected:
            raise SchemaViolation("review_no_change cannot also declare performed effects")
        receipt = _receipt(receipt)
        index = unit["request_index"]
        requests = (
            []
            if receipt is None
            else [
                row
                for row in receipt["requests"]
                if isinstance(row, dict) and row.get("request_index") == index
            ]
        )
        if len(requests) != 1:
            raise SchemaViolation("review_no_change needs the exact requested review owner")
        requested = requests[0]
        requirement = requested.get("record_requirement")
        review_requested = (
            isinstance(requirement, dict) and requirement.get("kind") == "review"
        ) or bool(inherited_reviews) or any(
            scope["authority_kind"] == "interpretation_review" for scope in scopes)
        if not review_requested or any(
            _stage(receipt, reader) != "returned"
            or _stage(receipt, review) not in ("checked", "no_candidates")
            for reader, review in _KINDS.values()
        ):
            raise SchemaViolation("review_no_change needs actual requested reading and review")
        if any(
            effect["performed"]
            and (effect["result_id"] in current or set(effect["removed_target_ids"]) & set(current))
            for effect in catalogue.values()
        ):
            raise SchemaViolation("The selected reviewed records also have performed changes")
        return
    work = unit.get("work", {})
    selected_task_ids = {"$work", work.get("existing_id"), work.get("progress_id")} - {None, ""}
    if unit["sufficiency"]["status"] == "complete" or any(
        update["status"] == "complete" and update["target_id"] in selected_task_ids
        for update in unit["progress_updates"]
    ):
        raise SchemaViolation(
            "An unresolved declared result cannot complete reply sufficiency or its task"
        )


def record_change_lines(changes: list[dict]) -> list[str]:
    """Describe canonical entry deltas without interpreting requested success."""
    parts = []
    for change in changes:
        before = [row["statement"] for row in change["before_records"]]
        after = change["after_record"]
        if change["relation"] == "withdraws":
            parts.extend("Withdrawn entry: " + text for text in before)
        elif change["relation"] == "contradicts" and change["kind"] == "details":
            parts.append("Opposing entry added: " + after["statement"])
            parts.extend("Earlier entry retained: " + text for text in before)
        elif change["relation"] == "corrects" or (
                change["kind"] == "disputes" and before):
            parts.append("Revised entry: " + " ; ".join(before) + " → " + after["statement"])
        else:
            parts.append("New entry: " + after["statement"])
    return parts


def _record_outcome_text(unit: dict, effects: dict, changes: dict,
                         record_catalogue: dict, *, require_checked: bool) -> tuple[str, str]:
    """Render selected facts, never infer requested meaning or read free prose."""
    expected_check = {"performed": "fulfilled", "already_current": "fulfilled",
                      "review_no_change": "no_change_justified", "unresolved": "unfinished"}
    outcome = unit.get("record_outcome", {})
    status = outcome.get("status")
    if (status not in expected_check or require_checked
            and unit.get("record_check", {}).get("outcome") != expected_check[status]):
        raise ExecutionEvidenceInvalid("The code acknowledgement has no checked record outcome")
    selected = list(dict.fromkeys(outcome["effect_ids"]))
    if any(identity not in effects or not effects[identity]["performed"]
           or identity not in changes for identity in selected):
        raise ExecutionEvidenceInvalid("The code acknowledgement selects an unperformed change")
    current = list(dict.fromkeys(outcome["current_record_ids"]))
    if any(identity not in record_catalogue for identity in current):
        raise ExecutionEvidenceInvalid(
            "The code acknowledgement selects an unowned current entry")
    lines = record_change_lines([changes[identity] for identity in selected])
    entries = [record_catalogue[identity]["record"]["statement"] for identity in current]
    if status == "performed":
        if not lines:
            raise ExecutionEvidenceInvalid(
                "The code acknowledgement has no actual changed entry")
        text = "Saved record changes:\n" + "\n".join(lines)
    elif status == "already_current":
        if not entries:
            raise ExecutionEvidenceInvalid("The code acknowledgement has no current entry")
        # Current state does not establish that NM changed it previously.
        text = "Current record entries:\n" + "\n".join(entries)
    elif status == "review_no_change":
        text = "The requested record review completed without a selected change."
        if entries:
            text += "\nCurrent entries:\n" + "\n".join(entries)
    else:
        text = "The requested record work remains unfinished."
        if lines:
            text += "\nSaved record changes:\n" + "\n".join(lines)
        if entries:
            text += "\nCurrent entries:\n" + "\n".join(entries)
    return text, status


def _legacy_record_acknowledgements(
        continuation: dict, execution: dict, *, record_catalogue: dict,
        require_checked: bool = True, replay: bool = False) -> dict:
    """Render checked record-only outcomes before progress and commit sealing.

    The delivery mode is an interpreted proposal, not proof of completion.
    Fresh receipts stamp the explicit rendering contract. Replay preserves
    the earlier text-only rendering for unstamped saved acknowledgements;
    unknown contracts are refused rather than rewriting historical replies.
    Before response review, require_checked=False permits only a mechanically
    admissible proposed outcome. Independent requested-result and progress
    review still runs. Final rendering and replay require its checked verdict.
    Outcome, source, target, inherited-goal and persistence checks still own
    their existing decisions. A reviewed substantive follow-up remains under
    semantic review instead of being silently removed to force code-only text.
    """
    result = deepcopy(continuation)
    units = {unit["request_index"]: unit for unit in result["units"]}
    if not any(request.get("response_mode", "substantive") == "record_acknowledgement"
               or "acknowledgement_delivery" in request or "acknowledgement_contract" in request
               for request in execution["requests"]):
        return result
    effects = effect_catalogue(execution)
    changes = {change["effect_id"]: change for change in execution["record_changes"]}
    for request in execution["requests"]:
        if request.get("response_mode", "substantive") != "record_acknowledgement":
            if "acknowledgement_delivery" in request or "acknowledgement_contract" in request:
                raise ExecutionEvidenceInvalid(
                    "A code acknowledgement has no declared delivery owner")
            continue
        version = request.get("acknowledgement_contract")
        if version is not None and version != _LEGACY_ACKNOWLEDGEMENT_CONTRACT:
            raise ExecutionEvidenceInvalid("The acknowledgement rendering contract is unsupported")
        legacy = replay and version is None
        if not replay:
            request["acknowledgement_contract"] = _LEGACY_ACKNOWLEDGEMENT_CONTRACT
        index = request["request_index"]
        unit = units.get(index)
        if unit is None:
            # The existing content-free unavailable notice is code-authored;
            # it does not certify a requested effect or a completed task.
            request["acknowledgement_delivery"] = "code_only"
            continue
        if unit["questions"] or unit["next_work"]:
            request["acknowledgement_delivery"] = "substantive_followup"
            continue
        text, status = _record_outcome_text(
            unit, effects, changes, record_catalogue, require_checked=require_checked)
        for block in unit["blocks"]:
            block["text"] = text
            # These anchors described the replaced model prose. The fixed
            # acknowledgement contains no legal proposition; its retained
            # checked references remain available as context source controls.
            if legacy:
                block.pop("inline_citations", None)
            else:
                block["kind"] = "limitation" if status == "unresolved" else "acknowledgment"
                block["uncertainty"] = "none"
                # Legal assertions and their anchors belonged to the discarded
                # prose. Preserve attributable account context and lifecycle IDs,
                # not citations suggesting the fixed acknowledgement states law.
                block["legal_source_ids"] = []
                block["record_ids"] = [identity for identity in block["record_ids"]
                                       if identity in record_catalogue]
                if "references" in block:
                    selected_references = set(block["span_ids"] + block["record_ids"])
                    block["references"] = [reference for reference in block["references"]
                                           if reference["id"] in selected_references]
                if require_checked:
                    block.pop("inline_citations", None)
                else:
                    block["inline_citations"] = []
        request["acknowledgement_delivery"] = "code_only"
    return result


def canonical_record_acknowledgements(
        continuation: dict, execution: dict, *, record_catalogue: dict,
        require_checked: bool = True, replay: bool = False) -> dict:
    """Render declared record-result nodes in every delivery mode.

    Fresh outcomes use a versioned renderer even when explanatory paragraphs or
    follow-ups are present. Explicit completion/status nodes are application
    text. Separately requested substantive work and linked follow-ups keep their
    own independently reviewed blocks. If an outcome shares their owner, append
    a separate code-owned status node rather than erase that deliverable.

    This does not classify arbitrary prose: an operation claim disguised inside
    account/assessment/question text remains an independent semantic judgment.
    Historical unstamped and v2 receipts retain their original renderer. Unknown
    contracts fail rather than silently reinterpreting historical responses.
    """
    result = deepcopy(continuation)
    units = {unit["request_index"]: unit for unit in result["units"]}
    effects = None
    changes = None
    for request in execution["requests"]:
        version = request.get("acknowledgement_contract")
        if version not in (None, _LEGACY_ACKNOWLEDGEMENT_CONTRACT,
                           RECORD_ACKNOWLEDGEMENT_CONTRACT):
            raise ExecutionEvidenceInvalid("The acknowledgement rendering contract is unsupported")
        scoped_contract = _scoped_outcome_contract(execution)
        if replay and version != RECORD_ACKNOWLEDGEMENT_CONTRACT:
            result = _legacy_record_acknowledgements(
                result, {**execution, "requests": [request]},
                record_catalogue=record_catalogue, require_checked=require_checked,
                replay=True)
            units = {unit["request_index"]: unit for unit in result["units"]}
            continue
        index = request["request_index"]
        unit = units.get(index)
        if unit is None:
            if (request.get("response_mode") == "record_acknowledgement"
                    or isinstance(request.get("record_requirement"), dict)
                    and request["record_requirement"].get("kind") != "none"):
                request["acknowledgement_contract"] = RECORD_ACKNOWLEDGEMENT_CONTRACT
                request["acknowledgement_delivery"] = "code_only"
            continue
        outcome = unit.get("record_outcome", {})
        if outcome.get("status", "none") == "none":
            if not replay and any(block["kind"] == "completion" for block in unit["blocks"]):
                raise SchemaViolation(
                    "A completion block needs a confirmed record outcome; "
                    "use an ordinary evidence block for a non-record answer")
            if ((not replay or scoped_contract)
                    and request_requires_record_outcome(request, execution)):
                raise ExecutionEvidenceInvalid(
                    "A scoped record result has no declared record outcome")
            # A non-record answer remains semantic work. This renderer cannot
            # infer an operation claim or repair a wrongly classified request.
            if version == RECORD_ACKNOWLEDGEMENT_CONTRACT:
                raise ExecutionEvidenceInvalid(
                    "A code record result has no declared record outcome")
            continue
        requirement = request.get("record_requirement")
        ordinary_partial = (outcome.get("status") == "unresolved"
                            and isinstance(requirement, dict)
                            and requirement.get("kind") == "none"
                            and request.get("response_mode") != "record_acknowledgement"
                            and not ((not replay or scoped_contract)
                                     and request_requires_record_outcome(request, execution)))
        if ordinary_partial:
            # Retained factual subsets use unresolved without inventing a
            # separate requested record task. Their actual limitation remains
            # independently checked substantive content.
            if version == RECORD_ACKNOWLEDGEMENT_CONTRACT:
                raise ExecutionEvidenceInvalid(
                    "A code record result has no requested record scope")
            continue
        if effects is None:
            effects = effect_catalogue(execution)
            changes = {change["effect_id"]: change for change in execution["record_changes"]}
        text, status = _record_outcome_text(
            unit, effects, changes, record_catalogue, require_checked=require_checked)
        owners = {block["id"]: block for block in unit["blocks"]}
        owner = owners.get(outcome.get("block_id"))
        if owner is None:
            raise ExecutionEvidenceInvalid("The code record result has no displayed outcome owner")
        linked = {link["block_id"] for field in ("questions", "next_work")
                  for link in unit[field]}
        pure = (request.get("response_mode") == "record_acknowledgement"
                and not linked)
        selected = [block for block in unit["blocks"]
                    if pure or block["kind"] == "completion"
                    and (not replay or scoped_contract or block["id"] not in linked)
                    or block["id"] not in linked and block["id"] == owner["id"]
                    and block["kind"] in ("acknowledgment", "limitation")]
        if owner not in selected:
            if selected:
                outcome["block_id"] = selected[0]["id"]
            else:
                node = deepcopy(owner)
                base = "nm_record_outcome_" + hashlib.sha256(
                    json.dumps([execution["id"], index], separators=(",", ":")).encode()
                ).hexdigest()[:16]
                identity = base
                suffix = 0
                while identity in owners:
                    suffix += 1
                    identity = base + "_" + str(suffix)
                node["id"] = identity
                unit["blocks"].append(node)
                outcome["block_id"] = identity
                selected = [node]
        for block in selected:
            if "evidence_expression" in block or "expression_contract" in block:
                if block.get("expression_contract") != EVIDENCE_EXPRESSION_CONTRACT:
                    raise ExecutionEvidenceInvalid(
                        "The record expression has an unsupported rendering contract")
                # An appended status node may inherit its substantive owner's
                # expression. Replace that dependency as well as its wording;
                # the original substantive block keeps its own expression.
                block["evidence_expression"] = {
                    "operator": "record_result", "source_ids": [],
                    "record_ids": [], "focus": "none"}
            block["text"] = text
            block["kind"] = "limitation" if status == "unresolved" else "acknowledgment"
            block["uncertainty"] = "none"
            block["legal_source_ids"] = []
            block["record_ids"] = [identity for identity in block["record_ids"]
                                   if identity in record_catalogue]
            if "references" in block:
                references = set(block["span_ids"] + block["record_ids"])
                block["references"] = [reference for reference in block["references"]
                                       if reference["id"] in references]
            if require_checked:
                block.pop("inline_citations", None)
            else:
                block["inline_citations"] = []
        request["acknowledgement_contract"] = RECORD_ACKNOWLEDGEMENT_CONTRACT
        request["acknowledgement_delivery"] = (
            "code_only" if len(selected) == len(unit["blocks"]) else "substantive_followup")
    return result
