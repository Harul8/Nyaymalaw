"""Validate structured brain reads and offer one feedback-guided correction."""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Callable, TypeVar

from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ContentRefused,
    ContextOverflow,
    ModelPort,
    ModelResult,
    OutputTruncated,
    Prompt,
    ProviderUnavailable,
    RateLimited,
    SchemaViolation,
    Tier,
    TierUnavailable,
    estimate_tokens,
    require_schema,
)

_T = TypeVar("_T")


def require_independent_result(result) -> None:
    if result.was_downgraded or result.tier != Tier.JUDGE:
        raise TierUnavailable("The configured independent review was unavailable")


def quarantined_independent_result(error: SchemaViolation) -> ModelResult | None:
    """Expose only a completed independent object with the rejection's receipt."""
    result = getattr(error, "rejected_result", None)
    if (not isinstance(result, ModelResult) or result.completion is not Completion.COMPLETE
            or result.text is not None or not isinstance(result.data, dict)
            or (result.usage, result.latency_ms, result.retries)
            != (error.usage, error.latency_ms, error.retries)):
        return None
    require_independent_result(result)
    return result


def verdict_envelope_issue(data: object, ids: tuple[str, ...], *, coverage: bool) -> str:
    """Keep unknown shell content unread without discarding addressable peers."""
    allowed = {"verdicts", "coverage"} if coverage else {"verdicts"}
    if not isinstance(data, dict) or set(data) - allowed:
        return "The review envelope has unknown or ambiguous fields"
    rows = data.get("verdicts")
    if not isinstance(rows, list):
        return "verdicts must be an array"
    if any(not isinstance(row, dict) or row.get("candidate_id") not in ids for row in rows):
        return "The review envelope includes an unaddressable or unowned verdict"
    return ""


def checked_read(model: ModelPort, prompt: Prompt, schema: dict,
                 output_limit: int, accept: Callable[[dict], _T], *,
                 tier: Tier = Tier.ROUTINE) -> _T:
    """Return one validated read; correct one rejected response in context."""
    current = prompt
    for attempt in range(2):
        result = None
        try:
            result = model.structured(current, schema, tier,
                                      max_tokens=output_limit)
            if tier == Tier.JUDGE:
                require_independent_result(result)
            if not result.usable or not isinstance(result.data, dict):
                raise SchemaViolation("The response was incomplete or not a JSON object")
            require_schema(result.data, schema)
            return accept(result.data)
        except SchemaViolation as exc:
            if attempt:
                raise
            phase = f"{prompt.operation or 'structured_read'}:correction"
            if not claim_recovery(model, phase):
                raise SchemaViolation(
                    f"The shared recovery budget is exhausted for {phase}: {exc}") from exc
            correction = {
                "original_input": json.loads(prompt.user),
                "validation_issue": str(exc),
                "how_to_correct": (
                    "Return the complete declared JSON object. Correct missing "
                    "or invalid fields under the same schema. Use only source "
                    "references and classifications allowed by the input; omit "
                    "unsupported proposals rather than inventing facts, "
                    "citations, or earlier context. If the issue names a saved "
                    "item and required source IDs, include one of those IDs "
                    "only when that item is the intended link; otherwise "
                    "remove or correct the link."),
                "rejected_output": result.data if result is not None else None,
            }
            repair_system = prompt.system + (
                "\n\nMessage: This is a correction of the same read; the prior "
                "response was rejected and was not saved.\n"
                "Purpose: Repair the stated validation failure.\n"
                "Look for: The validation issue and the original attributed "
                "source words.\n"
                "Outcome: Return a complete replacement object under the "
                "same schema, with only supported proposals.")
            repair_user = json.dumps(correction, ensure_ascii=False,
                                     separators=(",", ":"))
            if (estimate_tokens(repair_system + repair_user) + output_limit
                    > model.context_budget(tier)):
                correction.pop("rejected_output")
                repair_user = json.dumps(correction, ensure_ascii=False,
                                         separators=(",", ":"))
            if (estimate_tokens(repair_system + repair_user) + output_limit
                    > model.context_budget(tier)):
                abandon_recovery(model, phase)
                raise ContextOverflow(
                    "The full conversation exceeds the correction context budget") from exc
            current = Prompt(system=repair_system, user=repair_user,
                             operation=prompt.operation)
    raise AssertionError("The correction loop did not return or raise")


def claim_recovery(model: ModelPort, phase: str) -> bool:
    """Reserve one conditional recovery dispatch in its owning turn ledger.

    Ports without a turn ledger retain the reader's local correction bound.
    Labels come from internal operations, never from advocate words or prose.
    """
    if not isinstance(phase, str) or not phase.strip():
        raise ValueError("A recovery reservation needs an internal phase")
    owner = getattr(model, "claim_recovery", None)
    if owner is None:
        return True
    result = owner(phase)
    if not isinstance(result, bool):
        raise TypeError("The owning recovery ledger must return a boolean decision")
    return result


def abandon_recovery(model: ModelPort, phase: str) -> None:
    """Clear a reservation's pending dispatch association without refunding it."""
    owner = getattr(model, "abandon_recovery", None)
    if owner is not None:
        owner(phase)


def _unread_recovery_units(failed: list[dict], issue: str) -> list[dict]:
    return [{"unit_id": unit["unit_id"], "field": unit["field"],
             "validation_issue": unit["validation_issue"] + "; " + issue}
            for unit in failed]


def _unit_specs(schema: dict, unit_fields: tuple[str, ...]) -> dict[str, dict]:
    properties = schema.get("properties", {})
    if (schema.get("type") != "object" or schema.get("additionalProperties") is not False
            or not unit_fields
            or len(unit_fields) != len(set(unit_fields))
            or any(field not in properties
                   or properties[field].get("type") != "array"
                   or not isinstance(properties[field].get("items"), dict)
                   for field in unit_fields)):
        raise ValueError("Independent unit fields must name declared array schemas")
    return {field: properties[field]["items"] for field in unit_fields}


def _object_schema(schema: dict, unit_fields: tuple[str, ...], *,
                   singleton: bool = False) -> dict:
    result = deepcopy(schema)
    for field in unit_fields:
        spec = result["properties"][field]
        if singleton:
            spec.pop("minItems", None)
            spec["maxItems"] = min(spec.get("maxItems", 1), 1)
        else:
            spec.pop("items", None)
            spec.pop("minItems", None)
            spec.pop("maxItems", None)
    return result


def _completed_object(model: ModelPort, prompt: Prompt, schema: dict,
                      output_limit: int, tier: Tier) -> tuple[dict | None, str]:
    """A rejected completed object is evidence, never an accepted model result."""
    rejection = ""
    try:
        result = model.structured(prompt, schema, tier, max_tokens=output_limit)
    except SchemaViolation as exc:
        rejection = str(exc)
        result = getattr(exc, "rejected_result", None)
    if result is None:
        return None, rejection or "No completed structured response was received"
    if not isinstance(result, ModelResult):
        raise SchemaViolation("A structured response has no normalized model receipt")
    if tier == Tier.JUDGE:
        require_independent_result(result)
    if not result.usable or not isinstance(result.data, dict):
        return None, "The response was incomplete or not a JSON object"
    return deepcopy(result.data), rejection


def _accepted_row(data: dict, field: str, row: dict, schema: dict,
                  unit_fields: tuple[str, ...], accept: Callable[[dict], tuple[_T, ...]]
                  ) -> _T:
    """Validate and interpret one row without mutating quarantined wire data."""
    require_schema(row, schema["properties"][field]["items"])
    envelope = {key: deepcopy(value) for key, value in data.items()
                if key in schema["properties"] and key not in unit_fields}
    envelope.update({name: [] for name in unit_fields})
    envelope[field] = [deepcopy(row)]
    require_schema(envelope, _object_schema(schema, unit_fields, singleton=True))
    accepted = accept(envelope)
    if not isinstance(accepted, tuple) or len(accepted) != 1:
        raise SchemaViolation("An independent row must yield exactly one proposal")
    return accepted[0]


def _read_units(data: dict | None, schema: dict, unit_fields: tuple[str, ...],
                accept: Callable[[dict], tuple[_T, ...]], *, prefix: str = ""
                ) -> tuple[list[dict], list[dict], str]:
    if data is None:
        return [], [], "The extraction envelope was not read"
    shell_issue = ""
    try:
        require_schema(data, _object_schema(schema, unit_fields))
    except SchemaViolation as exc:
        shell_issue = str(exc)
    valid, failed = [], []
    for field in unit_fields:
        rows = data.get(field)
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows, 1):
            unit = {"unit_id": f"{prefix}{field}:{index}", "field": field,
                    "proposal": deepcopy(row)}
            try:
                unit["accepted"] = _accepted_row(
                    data, field, row, schema, unit_fields, accept)
            except SchemaViolation as exc:
                unit["validation_issue"] = str(exc)
                failed.append(unit)
            else:
                valid.append(unit)
    if not shell_issue and not failed:
        try:
            require_schema(data, schema)
        except SchemaViolation as exc:
            shell_issue = str(exc)
    return valid, failed, shell_issue


def _repair_prompt(model: ModelPort, prompt: Prompt, output_limit: int,
                   tier: Tier, retained: list[dict], failed: list[dict],
                   issue: str, *, keyed: bool) -> Prompt:
    instruction = (
        "Return repairs keyed by the exact supplied unit IDs. A proposals "
        "array contains one corrected proposal, or is empty to explicitly omit "
        "an unsupported proposal. Without a field selector, use the original "
        "unit's declared operation and row schema. To change operation, select "
        "an exact offered field and use that field's declared row schema. "
        "Changing operation supplies no facts, source status or action authority. "
        "Do not restate, replace, or remove retained proposals."
        if keyed else
        "Repair the extraction envelope under the original schema. Independently "
        "retained proposals remain proposals awaiting review and cannot be "
        "overwritten by this replacement. Return the complete declared object.")
    system = (prompt.system or "") + (
        "\n\nMessage: This is a bounded correction of the same original read.\n"
        "Purpose: Repair only the stated structural or owned-reference failures.\n"
        "Look for: The complete original evidence, failed units and retained "
        "proposal context. Retention is not independent grounding approval.\n"
        "Outcome: " + instruction)
    payload = {
        "original_input": json.loads(prompt.user),
        "validation_issue": issue,
        "failed_units": [{key: deepcopy(value) for key, value in unit.items()
                          if key != "accepted"} for unit in failed],
        "retained_proposal_context": [
            {key: deepcopy(value) for key, value in unit.items() if key != "accepted"}
            for unit in retained],
    }
    user = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if estimate_tokens(system + user) + output_limit > model.context_budget(tier):
        # Retained content already lives in code and cannot be changed by the
        # repair. Drop only this duplicate; keep exact original input and all
        # failed units needed to repair an owned ID.
        payload["retained_proposal_context"] = [
            {"unit_id": unit["unit_id"], "field": unit["field"]}
            for unit in retained]
        user = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if estimate_tokens(system + user) + output_limit > model.context_budget(tier):
        raise ContextOverflow("The full conversation exceeds the correction context budget")
    return Prompt(system=system, user=user, operation=prompt.operation)


def _repair_shape(spec: dict, maximum: int, *, field: str | None = None) -> dict:
    properties = {"proposals": {"type": "array", "maxItems": min(maximum, 1),
                                 "items": deepcopy(spec)}}
    if field is not None:
        properties["field"] = {"type": "string", "enum": [field]}
    return {"type": "object", "additionalProperties": False,
            "required": list(properties), "properties": properties}


def _repair_schema(failed: list[dict], specs: dict[str, dict],
                   arrays: dict[str, dict]) -> dict:
    """Offer closed declared operation choices for each server-owned unit."""
    properties = {}
    for unit in failed:
        field = unit["field"]
        properties[unit["unit_id"]] = {"anyOf": [
            _repair_shape(specs[field], arrays[field].get("maxItems", 1)),
            *[_repair_shape(spec, arrays[selected].get("maxItems", 1), field=selected)
              for selected, spec in specs.items()]]}
    return {"type": "object", "additionalProperties": False,
            "required": ["repairs"], "properties": {
                "repairs": {"type": "object", "additionalProperties": False,
                            "required": list(properties), "properties": properties}}}


def _repair_units(data: dict | None, original: dict, schema: dict,
                  unit_fields: tuple[str, ...], failed: list[dict],
                  accept: Callable[[dict], tuple[_T, ...]], repair_schema: dict
                  ) -> tuple[list[dict], list[str], list[dict], str]:
    expected = {unit["unit_id"]: unit for unit in failed}
    repair_values = data.get("repairs") if isinstance(data, dict) else None
    shell_issue = ""
    if (not isinstance(data, dict) or set(data) != {"repairs"}
            or not isinstance(repair_values, dict)):
        shell_issue = "The correction did not return its declared repair envelope"
        repair_values = {}
    elif set(repair_values) - set(expected):
        shell_issue = "The correction names unowned repair unit IDs"
    valid, omitted, unread = [], [], []
    for identity, unit in expected.items():
        repaired = repair_values.get(identity)
        try:
            if repaired is None:
                raise SchemaViolation("The correction omitted a required unit ID")
            if not isinstance(repaired, dict):
                raise SchemaViolation("A correction unit must be a declared JSON object")
            selected = repaired.get("field", unit["field"])
            if not isinstance(selected, str) or selected not in unit_fields:
                raise SchemaViolation("A correction selects an unowned operation field")
            choices = repair_schema["properties"]["repairs"]["properties"][identity]["anyOf"]
            branch = next((choice for choice in choices
                           if (("field" not in repaired
                                and "field" not in choice["properties"])
                               or ("field" in repaired
                                   and choice["properties"].get("field", {}).get("enum")
                                   == [selected]))), None)
            if branch is None:
                raise SchemaViolation("A correction has no applicable declared operation shape")
            # Explicit branch validation remains the owning check even when
            # the provider has already enforced the portable alternatives.
            require_schema(repaired, branch)
            if not repaired["proposals"]:
                omitted.append(identity)
                continue
            row = repaired["proposals"][0]
            accepted = _accepted_row(
                original, selected, row, schema, unit_fields, accept)
        except SchemaViolation as exc:
            unread.append({"unit_id": identity, "field": unit["field"],
                           "validation_issue": str(exc)})
        else:
            valid.append({"unit_id": identity, "field": selected,
                          "proposal": deepcopy(row), "accepted": accepted})
    return valid, omitted, unread, shell_issue


def checked_unit_read(model: ModelPort, prompt: Prompt, schema: dict,
                      output_limit: int,
                      accept: Callable[[dict], tuple[_T, ...]], *,
                      unit_fields: tuple[str, ...], tier: Tier = Tier.ROUTINE,
                      diagnostics: dict | None = None,
                      allow_complete_replacement: bool = False) -> tuple[_T, ...]:
    """Retain admissible proposals and conditionally correct one failed batch.

    This opt-in is for independent array rows only. Neither retention nor an
    explicit omission establishes semantic completeness; independent original
    account review owns that decision. Unread units require a diagnostics owner.
    A strict adapter may expose a rejected COMPLETE object solely as quarantine.
    """
    specs = _unit_specs(schema, unit_fields)
    original, first_rejection = _completed_object(
        model, prompt, schema, output_limit, tier)
    retained, failed, shell_issue = _read_units(
        original, schema, unit_fields, accept)
    attempts, repaired, omitted, unread = 1, [], [], []
    final_shell_issue = shell_issue
    final_data = original
    recovery_exhausted = False
    conditional_failure = None
    if failed or shell_issue or first_rejection:
        keyed = not shell_issue and original is not None and bool(failed)
        arrays = {field: schema["properties"][field] for field in unit_fields}
        correction_schema = _repair_schema(failed, specs, arrays) if keyed else schema
        phase = f"{prompt.operation or 'structured_read'}:correction"
        if not claim_recovery(model, phase):
            recovery_exhausted = True
            unread = _unread_recovery_units(failed, "the shared recovery budget is exhausted")
            if not unread:
                final_shell_issue = (shell_issue or first_rejection
                                     or "The shared recovery budget is exhausted")
        else:
            dispatch_attempted = False
            try:
                repair_prompt = _repair_prompt(
                    model, prompt, output_limit, tier, retained, failed,
                    shell_issue or first_rejection
                    or "Independent proposal units failed validation", keyed=keyed)
                attempts = 2
                dispatch_attempted = True
                corrected, correction_rejection = _completed_object(
                    model, repair_prompt, correction_schema, output_limit, tier)
            except (ContextOverflow, ProviderUnavailable, OutputTruncated,
                    ContentRefused, RateLimited) as exc:
                if not dispatch_attempted:
                    abandon_recovery(model, phase)
                conditional_failure = {"kind": type(exc).__name__, "phase": phase,
                                       "dispatch_attempted": dispatch_attempted}
                issue = "The conditional correction did not finish: " + str(exc)
                unread = _unread_recovery_units(failed, issue)
                if not unread:
                    final_shell_issue = shell_issue or first_rejection or issue
            else:
                if keyed and not (allow_complete_replacement and isinstance(corrected, dict)
                                  and "repairs" not in corrected
                                  and all(field in corrected for field in unit_fields)):
                    repaired, omitted, unread, final_shell_issue = _repair_units(
                        corrected, original, schema, unit_fields, failed, accept,
                        correction_schema)
                else:
                    final_data = corrected
                    repaired, correction_failed, final_shell_issue = _read_units(
                        corrected, schema, unit_fields, accept, prefix="correction:")
                    # A complete replacement has no correspondence to prior failed IDs.
                    # Preserve its checked proposals without pretending absent original
                    # identities were corrected or explicitly omitted.
                    unread = [{"unit_id": unit["unit_id"], "field": unit["field"],
                               "validation_issue": "Replacement did not identify this failed unit"}
                              for unit in failed]
                    unread.extend({key: value for key, value in unit.items()
                                   if key not in ("proposal", "accepted")}
                                  for unit in correction_failed)
                if correction_rejection and corrected is None:
                    final_shell_issue = correction_rejection
    values, kept = [], []
    for unit in [*retained, *repaired]:
        if not any(unit["accepted"] == previous for previous in values):
            values.append(unit["accepted"])
            kept.append(unit)
    if final_data is not None:
        aggregate = {key: deepcopy(value) for key, value in final_data.items()
                     if key in schema["properties"] and key not in unit_fields}
        aggregate.update({field: [] for field in unit_fields})
        for unit in kept:
            aggregate[unit["field"]].append(deepcopy(unit["proposal"]))
        try:
            require_schema(aggregate, schema)
        except SchemaViolation as exc:
            final_shell_issue = final_shell_issue or str(exc)
    partial = bool(unread or final_shell_issue)
    if diagnostics is not None:
        diagnostics.clear()
        diagnostics.update({
            "state": "partial" if partial else "returned", "attempts": attempts,
            "recovery_exhausted": recovery_exhausted,
            "conditional_failure": conditional_failure,
            "proposal_count": len(values),
            "retained_unit_ids": [unit["unit_id"] for unit in retained],
            "repaired_unit_ids": [unit["unit_id"] for unit in repaired],
            "omitted_unit_ids": omitted, "unread_units": deepcopy(unread),
            "envelope_state": "unread" if final_shell_issue else "checked",
            "envelope_issue": final_shell_issue})
    if partial and (diagnostics is None or not values):
        raise SchemaViolation(final_shell_issue or unread[0]["validation_issue"])
    return tuple(values)
