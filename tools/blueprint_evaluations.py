"""Validate evaluation specifications without certifying their execution.

The baseline populations are deliberately independent of authored counts. Dataset
members can be populated later, but approvals and execution proof belong to the
existing evidence registry, never to this planning catalog.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping

from tools.blueprint_autonomy import COMPARISON_SETS

MODULES = frozenset(f"M{i:02}" for i in range(13))
BASE_CASES = frozenset(f"EVAL-{i:03}" for i in range(1, 35))
PATHS = frozenset({"ordinary", "correction_restart", "denial", "failure_recovery"})
PORTFOLIO_MINIMA = {
    "PORT-JOURNEY": 60,
    "PORT-RETRIEVAL": 300,
    "PORT-PASSAGES": 200,
    "PORT-EXTRACTION": 200,
    "PORT-SECURITY": 100,
    "PORT-USABILITY": 8,
}
PRIMARY_MINIMA = {
    "PORT-JOURNEY": dict.fromkeys(
        (
            "orientation_research",
            "document_rich_brief",
            "contested_proof",
            "urgent_procedure_timing",
            "remedy_practical_choice",
            "continuity_handover",
        ),
        10,
    ),
    "PORT-RETRIEVAL": dict.fromkeys(
        ("exact_identity_locator", "conceptual", "adverse_exception_treatment"), 100
    ),
    "PORT-PASSAGES": dict.fromkeys(
        (
            "supported_attribution_application",
            "unsupported_attribution",
            "applicability_or_version_trap",
            "partial_context_or_treatment_trap",
        ),
        50,
    ),
    "PORT-EXTRACTION": {
        "names_roles": 30,
        "dates": 40,
        "amounts": 40,
        "negations": 40,
        "speaker": 25,
        "legal_markings": 25,
    },
    "PORT-SECURITY": {
        "cross_tenant_matter": 20,
        "auth_recovery_revocation": 15,
        "media_parser_injection": 15,
        "processor_secret_egress": 15,
        "retry_race_cancellation": 15,
        "retention_restore": 10,
        "supply_chain_incident": 10,
    },
    "PORT-USABILITY": {"senior_advocate": 4, "junior_or_assisting_advocate": 4},
}
PROTOCOLS = frozenset(
    {"REVIEW-LEGAL", "REVIEW-PRIVACY", "REVIEW-SECURITY", "REVIEW-OPERATIONS", "REVIEW-USABILITY"}
)
OPERATORS = frozenset({"equals", "contains", "excludes", "set_equals", "greater_than_or_equal"})
MEDIA_PROHIBITED = frozenset(
    {
        "voice_identity",
        "appearance_identity",
        "voiceprint_creation_or_matching",
        "affect_emotion",
        "credibility_from_voice_or_appearance",
    }
)
MEDIA_ALLOWED = frozenset(
    {
        "transcription",
        "translation",
        "recording_local_diarisation",
        "user_confirmed_attribution",
        "evidence_based_legal_assessment",
    }
)
MEDIA_CRITERIA = frozenset({"BK-69-AC3", "BK-79-AC3", "BK-88-AC4"})
AUTONOMY_CASE_OWNERS = {
    "EVAL-031": frozenset({"BK-91-AC1", "BK-91-AC2", "BK-91-AC3"}),
    "EVAL-032": frozenset({"BK-92-AC1", "BK-92-AC2"}),
    "EVAL-033": frozenset({"BK-92-AC3"}),
    "EVAL-034": frozenset({"BK-91-AC4", "BK-92-AC4"}),
}
AUTONOMY_ZERO_OBSERVATIONS = {
    "EVAL-031": (
        "served.unsupported_material_claims",
        "served.held_answer_repeated_questions",
        "persistence.stale_results_accepted",
    ),
    "EVAL-032": (
        "budget.over_cap_dispatches",
        "observed.delegated_paths_untested",
        "security.canary_egress",
        "security.authority_expansions",
        "persistence.stale_or_forged_acceptances",
        "persistence.duplicate_effects",
    ),
    "EVAL-033": (
        "artifacts.uninspected_pages",
        "artifacts.material_parity_mismatches",
        "artifacts.unsupported_material_claims",
        "artifacts.fabricated_unknown_fields",
        "actions.unapproved_dispatches",
    ),
    "EVAL-034": (
        "comparison.missing_or_duplicate_results",
        "comparison.omitted_child_or_retry_costs",
        "comparison.unexplained_input_mismatches",
    ),
}
# Typed design floors, not an implementation of the future processor/harness.
# A changed product policy must change this independent control explicitly too.
MEDIA_POLICY = {
    "attribution_is_authentication": False,
    "procurement": {
        "scope": "selected_operation_and_configuration",
        "hidden_processing": "verify_absent",
        "unavoidable_prohibited_processing": "reject_route",
        "unrelated_optional_vendor_services": "not_disqualifying",
    },
    "request": {
        "default": "deny",
        "check_before_bytes": True,
        "unknown_configuration": "deny",
        "consent_override": False,
    },
    "response": {
        "validation": "recursive_closed_allowlist",
        "unknown_or_forbidden_fields": "reject_before_downstream",
        "raw_rejected_response_persistence": False,
        "protected_sinks": frozenset({"storage", "logs", "traces", "caches", "ui", "reasoning"}),
    },
    "evidence": {
        "originals": "preserve_under_custody_policy",
        "legal_assessment": "retain_source_based_assessment",
        "attribution": "recording_local_or_user_claim_not_identity_proof",
    },
    "observations": {
        "missing": "NOT_RUN",
        "equality": "strict_type_and_value",
        "derive_from_expected": False,
        "allowed_transcription": "observed_call_and_result",
        "denied_request": "observed_zero_outbound_calls",
    },
}
TOP_FIELDS = frozenset(
    {
        "schema_version",
        "purpose",
        "proof_level",
        "execution_status",
        "evidence",
        "synthetic_case_count",
        "required_modules",
        "required_paths_per_module",
        "observation_contract",
        "local_mode",
        "synthetic_cases",
        "release_portfolios",
        "portfolio_validation",
        "manual_review_protocols",
        "media_contract",
    }
)
CASE_FIELDS = frozenset(
    {
        "id",
        "module",
        "title",
        "owner_criteria",
        "required_paths",
        "method",
        "inputs",
        "sequence",
        "expected",
        "planted_negative",
        "live_observation",
        "proof_level",
        "execution_status",
        "evidence",
    }
)
PORT_FIELDS = frozenset(
    {
        "id",
        "owner_criteria",
        "minimum_count",
        "unit",
        "members",
        "evidence",
        "primary_strata",
        "overlay_minima",
        "required_dimensions",
        "membership_rule",
        "required_member_fields",
        "required_review",
        "blocking_reason",
    }
)
REVIEW_FIELDS = frozenset(
    {
        "id",
        "owner_criteria",
        "reviewer_role",
        "required_inputs",
        "tasks",
        "failure_conditions",
        "required_output_fields",
        "approvals",
        "evidence",
    }
)


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _strings(value: object, *, unique: bool = True) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_text(x) for x in value)
        and (not unique or len(value) == len(set(value)))
    )


def _rows(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(x, dict) for x in value)


def _keys(row: Mapping, fields: Iterable[str], label: str, errors: list[str]) -> None:
    if set(row) != set(fields):
        errors.append(f"{label}: unsupported or missing fields")


def _refs(row: Mapping, criteria: set[str], label: str, errors: list[str]) -> None:
    refs = row.get("owner_criteria")
    if not _strings(refs):
        errors.append(f"{label}: empty, duplicate or malformed owner criteria")
    else:
        for ref in refs:
            if ref not in criteria:
                errors.append(f"{label}: unknown owner criterion {ref}")


def _spec_only(row: Mapping, label: str, errors: list[str]) -> None:
    if (
        row.get("proof_level") != "specification"
        or row.get("execution_status") != "NOT_RUN"
        or row.get("evidence") != []
    ):
        errors.append(f"{label}: specification cannot claim executed proof")


def _typed_policy(actual: object, expected: object, label: str, errors: list[str]) -> None:
    """Check closed specification values without equating false, zero and absence."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            errors.append(f"{label}: missing or malformed policy")
            return
        _keys(actual, expected, label, errors)
        for key, value in expected.items():
            _typed_policy(actual.get(key), value, f"{label}.{key}", errors)
    elif isinstance(expected, frozenset):
        if not _strings(actual) or set(actual) != expected:
            errors.append(f"{label}: required policy population changed")
    elif type(actual) is not type(expected) or actual != expected:
        errors.append(f"{label}: required typed policy changed")


def _check_media_contract(catalog: Mapping, criteria: set[str], errors: list[str]) -> None:
    policy = catalog.get("media_contract")
    if not isinstance(policy, dict):
        errors.append("media contract: missing or malformed")
        return
    _keys(
        policy,
        set(MEDIA_POLICY) | {"owner_criteria", "prohibited_operations", "allowed_operations"},
        "media contract",
        errors,
    )
    _refs(policy, criteria, "media contract", errors)
    _typed_policy(
        policy.get("owner_criteria"), MEDIA_CRITERIA, "media contract.owner_criteria", errors
    )
    _typed_policy(
        policy.get("prohibited_operations"),
        MEDIA_PROHIBITED,
        "media contract.prohibited_operations",
        errors,
    )
    _typed_policy(
        policy.get("allowed_operations"), MEDIA_ALLOWED, "media contract.allowed_operations", errors
    )
    for key, value in MEDIA_POLICY.items():
        _typed_policy(policy.get(key), value, f"media contract.{key}", errors)


def _required_assertions(
    case: Mapping, requirements: Mapping, errors: list[str], *, kind: str
) -> None:
    """One mechanism for typed required observation operators and values."""
    assertions = case.get("expected")
    if not _rows(assertions):
        return  # The general case checker reports the invalid population.
    for path, (operator, required) in requirements.items():
        matches = [row for row in assertions if row.get("path") == path]
        label = f"{case['id']} {kind} observation {path}"
        if len(matches) != 1:
            errors.append(f"{label}: required observation missing or duplicated")
            continue
        assertion = matches[0]
        if assertion.get("operator") != operator:
            errors.append(f"{label}: required operator changed")
        _typed_policy(assertion.get("value"), required, label, errors)


def _media_assertions(case: Mapping, requirements: Mapping, errors: list[str]) -> None:
    _required_assertions(
        case,
        {
            path: ("set_equals" if isinstance(value, frozenset) else "equals", value)
            for path, value in requirements.items()
        },
        errors,
        kind="media",
    )


def _check_media_case(case: Mapping, errors: list[str]) -> None:
    """Retain both useful media success and material denial/capture counterexamples."""
    case_id, fixture = case.get("id"), case.get("inputs")
    if (
        not isinstance(case_id, str)
        or case_id not in {"EVAL-007", "EVAL-008", "EVAL-027"}
        or not isinstance(fixture, dict)
    ):
        return
    required_owners = (
        {"BK-69-AC3", "BK-79-AC3"}
        if case_id == "EVAL-007"
        else {"BK-79-AC3", "BK-88-AC4"}
        if case_id == "EVAL-008"
        else MEDIA_CRITERIA
    )
    owners = case.get("owner_criteria")
    if not _strings(owners) or not required_owners <= set(owners):
        errors.append(f"{case_id}: media acceptance ownership incomplete")
    if case_id == "EVAL-007":
        _typed_policy(
            fixture.get("requested_operation"), "transcription", "EVAL-007 allowed request", errors
        )
        _typed_policy(
            fixture.get("prohibited_request_variants"),
            MEDIA_PROHIBITED,
            "EVAL-007 prohibited requests",
            errors,
        )
        _media_assertions(
            case,
            {
                "prohibited_requests.covered_operations": MEDIA_PROHIBITED,
                "prohibited_requests.outbound_calls": 0,
                "prohibited_requests.refusal": "media_operation_prohibited",
            },
            errors,
        )
    elif case_id == "EVAL-008":
        if not _rows(fixture.get("frames")) or not _rows(fixture.get("transcript")):
            errors.append("EVAL-008: original media and transcript fixtures must be nonempty")
        if not _text(fixture.get("response_mutation_value")):
            errors.append("EVAL-008: forbidden response canary missing")
        fields = frozenset(
            {"voice_identity", "appearance_identity", "voiceprint", "emotion", "credibility"}
        )
        _typed_policy(
            fixture.get("forbidden_response_fields"),
            fields,
            "EVAL-008 response field population",
            errors,
        )
        _typed_policy(
            fixture.get("response_mutation_paths"),
            frozenset({"metadata", "segments[0]"}),
            "EVAL-008 response mutation paths",
            errors,
        )
        response = fixture.get("provider_response")
        if (
            not isinstance(response, dict)
            or not isinstance(response.get("metadata"), dict)
            or not _rows(response.get("segments"))
        ):
            errors.append("EVAL-008: response mutation containers must exist")
        elif (
            not _text(response["segments"][0].get("text"))
            or response["metadata"].get("operation") != "transcription"
        ):
            errors.append("EVAL-008: allowed provider transcript fixture missing")
        elif _rows(fixture.get("transcript")) and response["segments"][0]["text"] != fixture[
            "transcript"
        ][0].get("text"):
            errors.append("EVAL-008: provider response and ordinary transcript disagree")
        controls = fixture.get("observation_mutations")
        expected_controls = {
            ("transcript.speaker_authenticated", "remove", "observation_missing"),
            (
                "transcript.speaker_authenticated",
                "replace_with_string_false",
                "observation_type_mismatch",
            ),
            ("provider.successful_results", "remove", "observation_missing"),
            ("forbidden_response.inspected_sink_categories", "remove", "observation_missing"),
            (
                "forbidden_response.inspected_sink_categories",
                "empty",
                "media_sink_inventory_incomplete",
            ),
        }
        if not _rows(controls):
            errors.append("EVAL-008: missing-observation controls absent")
        else:
            actual = []
            for control in controls:
                _keys(
                    control, {"path", "action", "refusal"}, "EVAL-008 observation mutation", errors
                )
                values = tuple(control.get(key) for key in ("path", "action", "refusal"))
                if not all(_text(value) for value in values):
                    errors.append("EVAL-008: malformed observation mutation")
                else:
                    actual.append(values)
            if Counter(actual) != Counter(expected_controls):
                errors.append("EVAL-008: missing-observation control population changed")
        _media_assertions(
            case,
            {
                "after_stop.live_tracks": 0,
                "after_logout.live_tracks": 0,
                "transcript.original_preserved": True,
                "transcript.speaker_authenticated": False,
                "provider.allowed_calls": 2,
                "provider.successful_results": 1,
                "after_restart.transcript_versions": 2,
                "after_restart.original_hash_matches": True,
                "forbidden_response.rejected_variants": 10,
                "forbidden_response.downstream_occurrences": 0,
                "forbidden_response.uninspected_sinks": 0,
                "forbidden_response.inspected_sink_categories": MEDIA_POLICY["response"][
                    "protected_sinks"
                ],
                "forbidden_response.sink_inventory_reconciled": True,
                "observation_controls.refusals": frozenset(
                    {
                        "observation_missing",
                        "observation_type_mismatch",
                        "media_sink_inventory_incomplete",
                    }
                ),
            },
            errors,
        )
        correction = fixture.get("correction")
        if not _text(correction):
            errors.append("EVAL-008: correction fixture missing")
        else:
            _media_assertions(case, {"transcript.corrected_text": correction}, errors)
    else:
        configuration = {
            "operation": "transcription",
            "hidden_prohibited_processing": False,
            "unavoidable_prohibited_processing": False,
            "processing_known": True,
            "vendor_offers_unrelated_optional_biometrics": True,
        }
        _typed_policy(
            fixture.get("processor_configuration"),
            configuration,
            "EVAL-027 selected configuration",
            errors,
        )
        controls = fixture.get("configuration_mutations")
        required = {
            "hidden_prohibited_processing": True,
            "unavoidable_prohibited_processing": True,
            "processing_known": False,
        }
        if not _rows(controls):
            errors.append("EVAL-027: configuration controls absent")
        else:
            fields = [control.get("field") for control in controls]
            if not all(_text(field) for field in fields) or Counter(fields) != Counter(
                required.keys()
            ):
                errors.append("EVAL-027: configuration control population changed")
            for control in controls:
                _keys(control, {"field", "value"}, "EVAL-027 configuration mutation", errors)
                field = control.get("field")
                if isinstance(field, str) and field in required:
                    _typed_policy(
                        control.get("value"), required[field], f"EVAL-027 mutation {field}", errors
                    )
        _media_assertions(
            case,
            {
                "compliant_configuration.allowed_calls": 1,
                "disallowed_configurations.rejected_count": 3,
                "disallowed_configurations.outbound_calls": 0,
                "disallowed_configurations.outbound_bytes": 0,
            },
            errors,
        )


def _check_autonomy_case(case: Mapping, errors: list[str]) -> None:
    """Protect substantive fixture populations without recognising legal scenarios.

    Names, source text and candidate action order are deliberately not matched.
    This checks declared evidence obligations, not whether a model follows them.
    """
    identity, fixture = case.get("id"), case.get("inputs")
    if not isinstance(identity, str) or identity not in AUTONOMY_CASE_OWNERS:
        return
    label = f"{identity} autonomy"
    _typed_policy(
        case.get("owner_criteria"),
        AUTONOMY_CASE_OWNERS[identity],
        label + " owner criteria",
        errors,
    )
    if not isinstance(fixture, dict) or not fixture:
        errors.append(f"{label}: substantive fixture population absent")
        return
    requirements = {path: ("equals", 0) for path in AUTONOMY_ZERO_OBSERVATIONS[identity]}
    requirements["observed.missing_required_fields"] = ("equals", 0)
    if identity == "EVAL-031":
        sources = fixture.get("sources")
        valid_sources = (
            _rows(sources)
            and len(sources) >= 2
            and all(
                _text(row.get("id"))
                and _positive_int(row.get("version"))
                and _text(row.get("locator"))
                and _text(row.get("text"))
                for row in sources
            )
        )
        if not valid_sources or len({row["id"] for row in sources}) != len(sources):
            errors.append(f"{label}: nonempty distinct versioned sources required")
        later = fixture.get("later_input")
        if (
            not isinstance(later, dict)
            or not all(_text(later.get(k)) for k in ("id", "locator", "text"))
            or not _positive_int(later.get("version"))
        ):
            errors.append(f"{label}: typed later evidence required")
        commission = fixture.get("commission")
        if not isinstance(commission, dict) or not all(
            _text(commission.get(k)) for k in ("matter", "objective", "authority")
        ):
            errors.append(f"{label}: nonempty scoped commission required")
        if not _text(fixture.get("unavailable")):
            errors.append(f"{label}: unavailable-material fixture required")
        variants = fixture.get("transformations")
        if not _strings(variants) or len(variants) < 3:
            errors.append(f"{label}: nonempty semantic-variant population required")
        else:
            requirements["observed.case_family_variants"] = ("equals", len(variants))
        requirements.update(
            {
                "observed.lead_steps": ("greater_than_or_equal", 1),
                "observed.material_reassessments": ("greater_than_or_equal", 1),
                "served.unavailable_receipt_status": ("equals", "unavailable"),
            }
        )
    elif identity == "EVAL-032":
        parent, attempts = fixture.get("parent"), fixture.get("attempts")
        valid_parent = (
            isinstance(parent, dict)
            and _text(parent.get("matter"))
            and all(
                _positive_int(parent.get(k))
                for k in (
                    "revision",
                    "total_units",
                    "max_concurrent_specialists",
                    "max_delegation_depth",
                )
            )
            and _strings(parent.get("roles"))
            and set(parent["roles"]) == {"research", "draft_document"}
        )
        valid_attempts = (
            _rows(attempts)
            and len(attempts) >= 2
            and all(_text(row.get("child")) and _positive_int(row.get("units")) for row in attempts)
        )
        if not valid_parent or not valid_attempts:
            errors.append(f"{label}: nonempty typed parent/budget-race population required")
        elif (
            parent["max_concurrent_specialists"] < len(attempts)
            or parent["max_delegation_depth"] != 1
        ):
            errors.append(
                f"{label}: concurrency must not mask the budget race; depth must test one edge"
            )
        elif (
            len({row["child"] for row in attempts}) != len(attempts)
            or any(row["units"] > parent["total_units"] for row in attempts)
            or sum(row["units"] for row in attempts) <= parent["total_units"]
            or len({row["units"] for row in attempts}) != 1
        ):
            errors.append(
                f"{label}: independently admissible equal reservations "
                "must race beyond the shared cap"
            )
        else:
            admitted = parent["total_units"] // attempts[0]["units"]
            requirements["budget.race_admitted_children"] = ("equals", admitted)
            requirements["budget.race_rejected_children"] = ("equals", len(attempts) - admitted)
        faults = fixture.get("faults")
        required_faults = {
            "child_failed",
            "crash_after_result_commit",
            "grant_revoked_during_lease",
            "parent_cancelled",
            "forged_child_result",
            "source_changed",
        }
        if not _strings(faults) or not required_faults <= set(faults):
            errors.append(f"{label}: fault population missing, duplicate or malformed")
        else:
            requirements["observed.fault_variants"] = ("equals", len(faults))
        if not _text(fixture.get("canary")) or not _text(fixture.get("source_instruction")):
            errors.append(f"{label}: nonempty injection and egress canaries required")
        requirements.update(
            {
                "observed.ordinary_children_completed": ("greater_than_or_equal", 1),
                "observed.delegated_paths_inspected": ("greater_than_or_equal", 1),
                "served.failed_child_reported_clean": ("equals", False),
            }
        )
    elif identity == "EVAL-033":
        package = fixture.get("accepted_package")
        if not isinstance(package, dict):
            errors.append(f"{label}: typed accepted package required")
        else:
            claims = package.get("claims")
            valid_claims = (
                _rows(claims)
                and len(claims) >= 2
                and all(
                    all(_text(row.get(k)) for k in ("id", "status", "source", "locator", "text"))
                    and _positive_int(row.get("source_version"))
                    for row in claims
                )
            )
            if not valid_claims or len({row["id"] for row in claims}) != len(claims):
                errors.append(f"{label}: nonempty distinct source-linked claims required")
            if not _strings(package.get("unknown_fields")) or not _text(package.get("reservation")):
                errors.append(f"{label}: unresolved fields and material reservation required")
            if not _positive_int(package.get("revision")):
                errors.append(f"{label}: positive accepted package revision required")
            else:
                requirements["artifacts.accepted_content_version"] = ("equals", package["revision"])
        _typed_policy(
            fixture.get("formats"), frozenset({"docx", "pdf"}), label + " formats", errors
        )
        _typed_policy(
            fixture.get("actions_permitted"),
            frozenset({"prepare", "preview"}),
            label + " actions",
            errors,
        )
        if not _text(fixture.get("variant")):
            errors.append(f"{label}: changed-source fixture required")
        requirements.update(
            {
                "artifacts.formats_created": ("equals", ["docx", "pdf"]),
                "artifacts.pages_inspected": ("greater_than_or_equal", 1),
                "persistence.stale_draft_issued_as_current": ("equals", False),
            }
        )
    else:
        _typed_policy(fixture.get("modes"), COMPARISON_SETS["modes"], label + " modes", errors)
        families, repeats = fixture.get("task_families"), fixture.get("repeats_per_family")
        if not _strings(families) or len(families) < 3 or not _positive_int(repeats) or repeats < 2:
            errors.append(f"{label}: nonempty repeated comparison population required")
        else:
            count = len(COMPARISON_SETS["modes"]) * len(families) * repeats
            if (
                type(fixture.get("expected_run_records")) is not int
                or fixture["expected_run_records"] != count
            ):
                errors.append(f"{label}: comparison population arithmetic mismatch")
            requirements.update(
                {
                    "comparison.expected_run_records": ("equals", count),
                    "comparison.observed_run_records": ("equals", count),
                    "comparison.unique_task_families": ("equals", len(families)),
                }
            )
        dimensions = {
            "source_and_matter_versions",
            "tool_permissions",
            "model_configuration",
            "rubric",
            "budget_envelope",
        }
        metrics = {
            "material_support",
            "adverse_omissions",
            "question_usefulness",
            "reviewer_editing_effort",
            "time_to_accepted_result",
            "whole_task_cost",
            "failed_cancelled_child_cost",
            "critical_failures",
        }
        for field, needed in (("frozen_dimensions", dimensions), ("metrics", metrics)):
            value = fixture.get(field)
            if not _strings(value) or not needed <= set(value):
                errors.append(f"{label}: {field} population incomplete")
        requirements.update(
            {
                "comparison.scripted_fixture_claims_professional_approval": ("equals", False),
                "comparison.critical_failure_can_be_averaged_away": ("equals", False),
            }
        )
    _required_assertions(case, requirements, errors, kind="autonomy")


def check_evaluations(catalog: object, criteria: Iterable[str]) -> list[str]:
    """Check real specification populations/refs; empty release members are pending."""
    errors: list[str] = []
    known = set(criteria)
    if not known or not all(_text(x) for x in known):
        errors.append("evaluations: criterion population empty or malformed")
    if not isinstance(catalog, dict):
        return errors + ["evaluations: catalog must be an object"]
    _keys(catalog, TOP_FIELDS, "evaluations", errors)
    if type(catalog.get("schema_version")) is not int or catalog.get("schema_version") != 1:
        errors.append("evaluations: unsupported schema version")
    if not _text(catalog.get("purpose")):
        errors.append("evaluations: missing purpose")
    _spec_only(catalog, "evaluations", errors)
    _check_media_contract(catalog, known, errors)
    for field, expected in (("required_modules", MODULES), ("required_paths_per_module", PATHS)):
        values = catalog.get(field)
        if not _strings(values) or set(values) != expected:
            errors.append(f"evaluations: {field} must retain the independent baseline")

    contract = catalog.get("observation_contract")
    contract_fields = {
        "meaning",
        "operators",
        "required_run_fields",
        "completion_rule",
        "mutation_rule",
        "promotion_rule",
    }
    if not isinstance(contract, dict):
        errors.append("observations: missing contract")
    else:
        _keys(contract, contract_fields, "observations", errors)
        for field in contract_fields - {"operators", "required_run_fields"}:
            if not _text(contract.get(field)):
                errors.append(f"observations: missing {field}")
        if not _strings(contract.get("operators")) or set(contract["operators"]) != OPERATORS:
            errors.append("observations: invalid operators")
        required = {
            "case_id",
            "case_sha256",
            "mode",
            "code_identity_start",
            "code_identity_end",
            "observations",
            "assertion_results",
            "negative_control_results",
            "artifact_refs",
        }
        if not _strings(contract.get("required_run_fields")) or not required <= set(
            contract["required_run_fields"]
        ):
            errors.append("observations: missing execution identity or proof fields")
    local = catalog.get("local_mode")
    local_fields = {
        "name",
        "default_network",
        "allowed_data",
        "forbidden_data",
        "providers",
        "capture",
        "approval",
    }
    if not isinstance(local, dict):
        errors.append("local mode: missing")
    else:
        _keys(local, local_fields, "local mode", errors)
        if local.get("name") != "scripted_local" or local.get("default_network") != "deny":
            errors.append("local mode: scripted network-denied boundary required")
        for field in ("allowed_data", "forbidden_data"):
            if not _strings(local.get(field)):
                errors.append(f"local mode: missing {field}")
        for field in ("providers", "capture", "approval"):
            if not _text(local.get(field)):
                errors.append(f"local mode: missing {field}")

    cases = catalog.get("synthetic_cases")
    coverage = {module: set() for module in MODULES}
    if not _rows(cases):
        errors.append("synthetic cases: empty or malformed population")
    else:
        ids = [case.get("id") for case in cases]
        if not all(isinstance(x, str) and re.fullmatch(r"EVAL-\d{3}", x) for x in ids):
            errors.append("synthetic cases: malformed id")
        elif len(ids) != len(set(ids)) or not BASE_CASES <= set(ids):
            errors.append("synthetic cases: duplicate or missing baseline case")
        if type(catalog.get("synthetic_case_count")) is not int or catalog.get(
            "synthetic_case_count"
        ) != len(cases):
            errors.append("synthetic cases: declared count does not match discovered population")
        for index, case in enumerate(cases):
            label = str(case.get("id", f"case[{index}]"))
            _keys(case, CASE_FIELDS, label, errors)
            _refs(case, known, label, errors)
            _spec_only(case, label, errors)
            _check_media_case(case, errors)
            _check_autonomy_case(case, errors)
            for field in ("title", "method"):
                if not _text(case.get(field)):
                    errors.append(f"{label}: missing {field}")
            module, paths = case.get("module"), case.get("required_paths")
            if not isinstance(module, str) or module not in MODULES:
                errors.append(f"{label}: unknown module")
            if not _strings(paths) or not set(paths) <= PATHS:
                errors.append(f"{label}: malformed required paths")
            elif isinstance(module, str) and module in coverage:
                coverage[module].update(paths)
            if not isinstance(case.get("inputs"), dict) or not case["inputs"]:
                errors.append(f"{label}: empty or malformed fixture inputs")
            for field in ("sequence", "live_observation"):
                if not _strings(case.get(field)):
                    errors.append(f"{label}: empty or malformed {field}")
            assertions = case.get("expected")
            if not _rows(assertions):
                errors.append(f"{label}: empty or malformed exact observations")
            else:
                observed_paths = []
                for assertion in assertions:
                    _keys(assertion, {"path", "operator", "value"}, label + " observation", errors)
                    operator = assertion.get("operator")
                    if (
                        not _text(assertion.get("path"))
                        or not isinstance(operator, str)
                        or operator not in OPERATORS
                    ):
                        errors.append(f"{label}: invalid observation path or operator")
                    elif assertion["path"] in observed_paths:
                        errors.append(f"{label}: duplicate observation path")
                    else:
                        observed_paths.append(assertion.get("path"))
                    if assertion.get("operator") == "set_equals":
                        value = assertion.get("value")
                        if not isinstance(value, list) or any(
                            x == y for i, x in enumerate(value) for y in value[i + 1 :]
                        ):
                            errors.append(f"{label}: invalid set_equals value")
                # Values may be false, zero or null: they are legitimate explicit expected outcomes.
            negative = case.get("planted_negative")
            if not isinstance(negative, dict):
                errors.append(f"{label}: missing planted negative")
            else:
                _keys(negative, {"mutation", "expected_refusal"}, label + " negative", errors)
                if not all(
                    _text(negative.get(field)) for field in ("mutation", "expected_refusal")
                ):
                    errors.append(f"{label}: empty mutation or intended refusal")
    for module, present in sorted(coverage.items()):
        if present != PATHS:
            errors.append(f"{module}: missing required scenario paths {sorted(PATHS - present)}")

    portfolios = catalog.get("release_portfolios")
    if not _rows(portfolios):
        errors.append("release portfolios: empty or malformed definitions")
    else:
        ids = [row.get("id") for row in portfolios]
        if not all(isinstance(x, str) for x in ids) or Counter(ids) != Counter(
            PORTFOLIO_MINIMA.keys()
        ):
            errors.append("release portfolios: missing, duplicate or unknown baseline portfolio")
        for row in portfolios:
            label = str(row.get("id", "portfolio"))
            allowed = PORT_FIELDS | (
                {"target_maximum_count"} if label == "PORT-USABILITY" else set()
            )
            _keys(row, allowed, label, errors)
            _refs(row, known, label, errors)
            minimum = row.get("minimum_count")
            if not _positive_int(minimum) or minimum < PORTFOLIO_MINIMA.get(label, 1):
                errors.append(f"{label}: minimum cannot shrink below the approved design baseline")
            maximum = row.get("target_maximum_count")
            if "target_maximum_count" in row and (
                not _positive_int(maximum) or not _positive_int(minimum) or maximum < minimum
            ):
                errors.append(f"{label}: invalid target maximum")
            for field in ("unit", "membership_rule", "required_review", "blocking_reason"):
                if not _text(row.get(field)):
                    errors.append(f"{label}: missing {field}")
            for field in ("required_dimensions", "required_member_fields"):
                if not _strings(row.get(field)):
                    errors.append(f"{label}: missing or duplicate {field}")
            strata = row.get("primary_strata")
            if not _rows(strata):
                errors.append(f"{label}: empty primary strata")
            else:
                stratum_ids = []
                total = 0
                for stratum in strata:
                    _keys(stratum, {"id", "minimum"}, label + " stratum", errors)
                    if not _text(stratum.get("id")) or stratum.get("id") in stratum_ids:
                        errors.append(f"{label}: duplicate or malformed stratum")
                    stratum_ids.append(stratum.get("id"))
                    if not _positive_int(stratum.get("minimum")):
                        errors.append(f"{label}: invalid stratum minimum")
                    else:
                        total += stratum["minimum"]
                if total != minimum:
                    errors.append(f"{label}: primary strata do not reconcile to minimum")
                actual_strata = {
                    stratum["id"]: stratum.get("minimum")
                    for stratum in strata
                    if isinstance(stratum.get("id"), str)
                }
                for sid, floor in PRIMARY_MINIMA.get(label, {}).items():
                    actual_minimum = actual_strata.get(sid)
                    if not _positive_int(actual_minimum) or actual_minimum < floor:
                        errors.append(f"{label}: required primary stratum {sid} missing or reduced")
            overlay = row.get("overlay_minima")
            if (
                not isinstance(overlay, dict)
                or not overlay
                or not all(_text(k) and _positive_int(v) for k, v in overlay.items())
            ):
                errors.append(f"{label}: missing or malformed overlay minima")
            members = row.get("members")
            if not isinstance(members, list) or any(
                not isinstance(member, dict) for member in members
            ):
                errors.append(f"{label}: malformed member population")
            elif members:
                member_ids = [member.get("id") for member in members]
                if not all(_text(x) for x in member_ids) or len(member_ids) != len(set(member_ids)):
                    errors.append(f"{label}: duplicate or malformed member id")
                for member in members:
                    required_fields = row.get("required_member_fields")
                    if _strings(required_fields) and not set(required_fields) <= set(member):
                        errors.append(f"{label}: member missing required fields")
            if row.get("evidence") != []:
                errors.append(f"{label}: planning catalog cannot self-certify execution evidence")
    policy = catalog.get("portfolio_validation")
    policy_fields = {"specification_check", "release_check", "actual_member_rule", "change_control"}
    if not isinstance(policy, dict):
        errors.append("portfolio validation: missing policy")
    else:
        _keys(policy, policy_fields, "portfolio validation", errors)
        if not all(_text(policy.get(field)) for field in policy_fields):
            errors.append(
                "portfolio validation: missing distinction between specification and release"
            )
    protocols = catalog.get("manual_review_protocols")
    if not _rows(protocols):
        errors.append("manual review: empty or malformed protocols")
    else:
        ids = [row.get("id") for row in protocols]
        if not all(isinstance(x, str) for x in ids) or Counter(ids) != Counter(PROTOCOLS):
            errors.append("manual review: missing, duplicate or unknown protocol")
        for row in protocols:
            label = str(row.get("id", "review"))
            _keys(row, REVIEW_FIELDS, label, errors)
            _refs(row, known, label, errors)
            if not _text(row.get("reviewer_role")):
                errors.append(f"{label}: missing qualified reviewer role")
            for field in (
                "required_inputs",
                "tasks",
                "failure_conditions",
                "required_output_fields",
            ):
                if not _strings(row.get(field)):
                    errors.append(f"{label}: empty or malformed {field}")
            if row.get("approvals") != [] or row.get("evidence") != []:
                errors.append(f"{label}: manual protocol cannot self-certify approval or execution")
    return errors


def deployment_blockers(catalog: object) -> list[str]:
    """Explain unmet populations; NEVER issue release authorization from this file.

    This is a planning diagnostic, not a replacement for the profile's actual
    evidence evaluator. Filled member records alone cannot make it return green.
    """
    blockers = [
        "release authority: specification catalog cannot grant deployment; "
        "current registry-bound execution and accountable sign-off are required"
    ]
    if not isinstance(catalog, dict):
        return blockers + ["evaluations: catalog missing or malformed"]
    portfolios = catalog.get("release_portfolios")
    if not _rows(portfolios):
        return blockers + ["release portfolios: definitions missing"]
    for row in portfolios:
        label = str(row.get("id", "portfolio"))
        members = row.get("members")
        actual = len(members) if isinstance(members, list) else 0
        minimum = row.get("minimum_count")
        if not _positive_int(minimum):
            blockers.append(f"{label}: minimum invalid")
        elif actual < minimum:
            blockers.append(f"{label}: {actual}/{minimum} actual members; population not ready")
        blockers.append(
            f"{label}: independent labels, scoped execution, reservations and freshness "
            "must be verified outside this specification"
        )
    for protocol in sorted(PROTOCOLS):
        blockers.append(
            f"{protocol}: a protocol is not qualified independent sign-off; "
            "verify the actual review artifact"
        )
    return blockers
