"""Check the bounded-autonomy design contract, never runtime or legal quality.

Independent requirement floors refuse deletion/weakening. They are deliberately
not learned from authored counts, expected results or the contract under test.
Actual agent execution, approvals and professional evidence belong to BK-91/92.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNERS = {
    "AUTO-01": ("BK-91", "BK-91-AC1", "P46"),
    "AUTO-02": ("BK-91", "BK-91-AC2", "P46"),
    "AUTO-03": ("BK-91", "BK-91-AC3", "P24"),
    "AUTO-04": ("BK-91", "BK-91-AC4", "P35"),
    "AUTO-05": ("BK-92", "BK-92-AC1", "P47"),
    "AUTO-06": ("BK-92", "BK-92-AC2", "P47"),
    "AUTO-07": ("BK-92", "BK-92-AC3", "P29"),
    "AUTO-08": ("BK-92", "BK-92-AC4", "P37"),
}
ROLES = {"lead": False, "research": True, "draft_document": True}
FIELD_TYPES = {
    "task_fields": {
        "task_id": "opaque_id",
        "parent_task_id": "opaque_id_or_explicit_root",
        "actor_scope": "server_authorised_scope",
        "mandate_version": "version_reference",
        "objective": "nonempty_text",
        "acceptance_and_stop_conditions": "nonempty_typed_list",
        "source_snapshot": "versioned_manifest",
        "context_manifest": "included_and_omitted_source_references",
        "known_gaps": "typed_list",
        "role": "registered_role",
        "permitted_tools": "server_capabilities",
        "permitted_data_processors": "policy_bound_allowlist",
        "budget_reservation": "shared_ledger_reference",
        "deadline": "timezone_aware_timestamp",
        "permission_epoch": "nonnegative_integer",
        "cancellation_epoch": "nonnegative_integer",
        "idempotency_key": "scoped_request_identity",
        "result_contract_version": "version_reference",
    },
    "result_fields": {
        "task_id": "opaque_id",
        "attempt_id": "opaque_id",
        "source_snapshot": "versioned_manifest",
        "mandate_version": "version_reference",
        "status": "explicit_terminal_or_partial_state",
        "findings": "typed_candidate_claims",
        "contrary_material": "versioned_source_references",
        "open_gaps": "typed_list",
        "proposed_deltas": "version_conditional_candidates",
        "rationale": "concise_professional_reasons_not_chain_of_thought",
        "stop_reason": "nonempty_typed_reason",
        "budget_used": "shared_ledger_receipt",
        "producer_identity": "model_prompt_tool_configuration_versions",
    },
    "claim_fields": {
        "claim_id": "opaque_id",
        "text": "nonempty_text",
        "claim_kind": "assertion_extracted_inference_legal_or_unknown",
        "speaker": "attributed_identity_or_explicit_unknown",
        "factual_state": "independent_asserted_disputed_evidenced_found_or_unknown",
        "source_refs": "versioned_original_locators_or_explicit_unresolved_basis",
        "support_assessment": "supported_unsupported_partial_or_not_assessed",
        "applicability": "reasoned_scope_or_not_assessed_or_not_applicable",
        "contrary_refs": "versioned_source_references",
        "dependencies": "versioned_claim_source_mandate_policy_references",
        "limitations": "typed_list",
    },
}
POLICIES = {
    "grounding": {
        "model_knowledge": "investigation_hypothesis_not_evidence",
        "material_fact": "attributed_source_or_explicit_gap_never_invention",
        "legal_conclusion": "retrieved_authority_and_applicability_required",
        "source_instructions": "untrusted_evidence_never_authority",
        "semantic_support": "assessed_not_proved_by_schema_or_citation_presence",
        "agreement": "not_independent_evidence",
        "uncertainty": "preserve_independent_dimensions",
        "handoff_and_artifact_lineage": "original_version_locator_through_final_bytes",
        "rendering": "one_accepted_semantic_version_no_added_facts",
    },
    "lifecycle": {
        "canonical_writes": "single_acceptance_service_not_agents",
        "permission_inheritance": "child_subset_of_current_parent",
        "budget_accounting": "atomic_task_wide_reservation_includes_retries_and_children",
        "stale_or_revoked_result": "refuse_before_commit_or_release",
        "cancellation": "propagate_no_new_dispatch_or_late_publication",
        "retry": "bounded_classified_idempotent_not_blind_external_repeat",
        "specialist_failure": "visible_incomplete_not_clean",
        "merge_conflict": "contested_not_last_writer_wins",
        "monitoring": "separate_recorded_service_authority",
        "audit": "restricted_concise_rationale_no_raw_chain_of_thought",
        "scratch_and_caches": "inherit_scope_lineage_retention_and_erasure",
    },
}
BOUNDARIES = {
    "dynamic_actions": frozenset(
        {
            "read",
            "retrieve",
            "compare_hypotheses",
            "ask",
            "delegate",
            "assess",
            "challenge",
            "draft",
            "revise",
            "stop",
        }
    ),
    "application_owned": frozenset(
        {
            "admission",
            "identity",
            "permissions",
            "tool_capabilities",
            "processor_egress",
            "budget_reservations",
            "job_lifecycle",
            "version_checks",
            "required_release_checks",
            "arithmetic_on_reviewed_premises",
            "conditional_commit",
            "publication",
        }
    ),
    "human_owned": frozenset(
        {
            "client_objective_and_mandate",
            "professional_review_required_by_profile",
            "consequential_action_approval",
            "capability_and_budget_expansion",
            "release_decision",
        }
    ),
}
BUDGETS = frozenset(
    {
        "elapsed_time",
        "tokens_and_cost",
        "retrieval_calls",
        "tool_calls",
        "retries",
        "concurrency",
        "delegation_depth",
    }
)
COMPARISON_SETS = {
    "modes": frozenset({"existing_orchestration", "autonomous_lead", "selective_delegation"}),
    "fixed_dimensions": frozenset(
        {
            "task_families",
            "source_corpus",
            "permissions",
            "models_and_configuration_except_tested_factor",
            "rubric",
            "matched_total_budget",
        }
    ),
    "metrics": frozenset(
        {
            "professional_usefulness",
            "unsupported_material_claims",
            "adverse_omissions",
            "source_readback",
            "advocate_review_time",
            "unnecessary_questions",
            "task_completion",
            "boundary_violations",
            "latency_percentiles",
            "total_cost_per_quality_approved_task",
        }
    ),
    "required_paths": frozenset(
        {
            "contrary_evidence",
            "changed_objective",
            "correction_during_delegation",
            "irrelevant_authentic_authority",
            "unavailable_material",
            "source_prompt_injection",
            "revoked_access",
            "provider_failure",
            "shared_budget_exhaustion",
            "meaning_preserving_variants",
            "meaning_changing_variants",
        }
    ),
}
COMPARISON_POLICIES = {
    "review": "independent_qualified_counsel_not_same_model_self_certification",
    "repeat_policy": "predeclare_repeats_retain_all_runs_report_variability",
    "population_policy": "nonempty_independently_enumerated_strata_no_missing_result_success",
    "decision_rule": "retain_delegation_only_for_measured_benefit_without_safety_waiver",
}
TOP_FIELDS = frozenset(
    {
        "schema_version",
        "purpose",
        "proof_level",
        "execution_status",
        "evidence",
        "roles",
        "task_fields",
        "result_fields",
        "claim_fields",
        "control_boundary",
        "grounding",
        "lifecycle",
        "initial_profile",
        "comparison",
        "obligations",
    }
)


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _same(actual: object, expected: object) -> bool:
    return type(actual) is type(expected) and actual == expected


def _set_is(actual: object, expected: frozenset[str]) -> bool:
    return (
        isinstance(actual, list)
        and bool(actual)
        and all(_text(x) for x in actual)
        and len(actual) == len(set(actual))
        and set(actual) == expected
    )


def _closed(
    value: object, fields: set[str] | frozenset[str], path: str, problems: list[str]
) -> bool:
    if not isinstance(value, dict):
        problems.append(f"autonomy {path}: expected object")
        return False
    if set(value) != fields:
        problems.append(f"autonomy {path}: missing or unexpected fields")
    return True


def load_contract(root: Path = ROOT) -> dict:
    """Reuse the planning loader's duplicate-key refusal, with no network or writes."""
    from tools.blueprint import _unique_keys

    return json.loads(
        (root / "docs/blueprint/autonomy.json").read_text(encoding="utf-8"),
        object_pairs_hook=_unique_keys,
    )


def check_contract(
    contract: dict,
    *,
    known_items: set[str] | None = None,
    known_criteria: set[str] | None = None,
    known_packets: set[str] | None = None,
) -> list[str]:
    """Return design defects; an empty result grants no runtime/release authority."""
    problems: list[str] = []
    if not _closed(contract, TOP_FIELDS, "contract", problems):
        return problems
    for key, expected in {
        "schema_version": 1,
        "proof_level": "design_contract",
        "execution_status": "NOT_RUN",
        "evidence": [],
    }.items():
        if not _same(contract.get(key), expected):
            problems.append(f"autonomy {key}: must retain design-only/unexecuted state")
    if not _text(contract.get("purpose")):
        problems.append("autonomy purpose: nonempty explanation required")

    roles = contract.get("roles")
    seen_roles = []
    if not isinstance(roles, list) or not roles:
        problems.append("autonomy roles: nonempty role population required")
    else:
        for row in roles:
            if not _closed(row, {"id", "purpose", "optional"}, "roles", problems):
                continue
            role = row.get("id")
            if not isinstance(role, str) or role not in ROLES:
                problems.append("autonomy roles: unsupported role")
                continue
            seen_roles.append(role)
            if not _text(row.get("purpose")) or not _same(row.get("optional"), ROLES[role]):
                problems.append(f"autonomy roles.{role}: purpose/optional contract invalid")
        if len(seen_roles) != len(ROLES) or set(seen_roles) != set(ROLES):
            problems.append("autonomy roles: missing or duplicate roles")

    for group, expected_fields in FIELD_TYPES.items():
        fields = contract.get(group)
        if not isinstance(fields, dict) or not fields:
            problems.append(f"autonomy {group}: nonempty typed field population required")
            continue
        for key, expected in expected_fields.items():
            if fields.get(key) != expected:
                problems.append(
                    f"autonomy {group}.{key}: required type contract missing or weakened"
                )
        for key, value in fields.items():
            if not _text(key) or not _text(value):
                problems.append(f"autonomy {group}: every extension needs a named type")

    boundary = contract.get("control_boundary")
    if _closed(boundary, set(BOUNDARIES), "control_boundary", problems):
        for key, expected in BOUNDARIES.items():
            if not _set_is(boundary.get(key), expected):
                problems.append(f"autonomy control_boundary.{key}: boundary population changed")
    for group, expected in POLICIES.items():
        policy = contract.get(group)
        if _closed(policy, set(expected), group, problems):
            for key, value in expected.items():
                if not _same(policy.get(key), value):
                    problems.append(f"autonomy {group}.{key}: required policy missing or weakened")

    profile = contract.get("initial_profile")
    initial = {
        "status": "proposed_unmeasured",
        "max_concurrent_specialists": 2,
        "max_delegation_depth": 1,
        "specialists_may_delegate": False,
    }
    if _closed(profile, {*initial, "budget_dimensions"}, "initial_profile", problems):
        for key, expected in initial.items():
            if not _same(profile.get(key), expected):
                problems.append(
                    f"autonomy initial_profile.{key}: change needs explicit design review"
                )
        if not _set_is(profile.get("budget_dimensions"), BUDGETS):
            problems.append("autonomy initial_profile.budget_dimensions: incomplete shared limits")

    comparison = contract.get("comparison")
    if _closed(comparison, {*COMPARISON_SETS, *COMPARISON_POLICIES}, "comparison", problems):
        for key, values in COMPARISON_SETS.items():
            if not _set_is(comparison.get(key), values):
                problems.append(
                    f"autonomy comparison.{key}: missing or duplicate comparison obligations"
                )
        for key, value in COMPARISON_POLICIES.items():
            if not _same(comparison.get(key), value):
                problems.append(f"autonomy comparison.{key}: required policy missing or weakened")

    rows = contract.get("obligations")
    seen = []
    if not isinstance(rows, list) or not rows:
        problems.append("autonomy obligations: nonempty independently fixed population required")
    else:
        for row in rows:
            if not _closed(
                row,
                {"id", "title", "item", "criterion", "packet", "requirement"},
                "obligations",
                problems,
            ):
                continue
            identity = row.get("id")
            if not isinstance(identity, str) or identity not in OWNERS:
                problems.append("autonomy obligations: unknown ID")
                continue
            seen.append(identity)
            if any(not _text(row.get(key)) for key in ("title", "requirement")):
                problems.append(f"autonomy {identity}: substantive title/requirement required")
            actual = tuple(row.get(key) for key in ("item", "criterion", "packet"))
            if actual != OWNERS[identity]:
                problems.append(f"autonomy {identity}: exact acceptance/packet owner mismatch")
            for key, population in (
                ("item", known_items),
                ("criterion", known_criteria),
                ("packet", known_packets),
            ):
                value = row.get(key)
                if population is not None and (
                    not isinstance(value, str) or value not in population
                ):
                    problems.append(f"autonomy {identity}: {key} is not registered")
        if len(seen) != len(OWNERS) or set(seen) != set(OWNERS):
            problems.append("autonomy obligations: required population missing or duplicated")
    return problems
