"""Class-A checks of media design obligations, never runtime compliance proof."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from tools.blueprint_evaluations import check_evaluations, deployment_blockers

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    catalog = json.loads((ROOT / "docs/blueprint/evaluations.json").read_text(encoding="utf-8"))
    registry = yaml.safe_load((ROOT / "docs/backlog/status.yaml").read_text(encoding="utf-8"))
    criteria = {criterion["id"] for item in registry["items"] for criterion in item.get("acceptance", [])}
    return catalog, criteria


def _case(catalog, case_id):
    matches = [case for case in catalog["synthetic_cases"] if case["id"] == case_id]
    assert len(matches) == 1
    return matches[0]


def _target(root, path):
    """Resolve only existing containers; a typo cannot invent a successful probe."""
    node = root
    for key in path[:-1]:
        assert key in node if isinstance(node, dict) else isinstance(key, int) and 0 <= key < len(node)
        node = node[key]
    key = path[-1]
    assert key in node if isinstance(node, dict) else isinstance(key, int) and 0 <= key < len(node)
    return node, key


def test_media_contract_is_registered_and_preserves_both_permission_and_refusal():
    catalog, criteria = _inputs()
    assert check_evaluations(catalog, criteria) == []
    contract = catalog["media_contract"]
    assert set(contract["owner_criteria"]) == {"BK-69-AC3", "BK-79-AC3", "BK-88-AC4"}
    assert len(contract["prohibited_operations"]) == 5
    assert len(contract["allowed_operations"]) == 5
    assert {f"EVAL-{n:03d}" for n in range(1, 31)} <= {c["id"] for c in catalog["synthetic_cases"]}
    assert len(catalog["synthetic_cases"]) == 34
    for case_id in ("EVAL-007", "EVAL-008", "EVAL-027"):
        case = _case(catalog, case_id)
        assert case["execution_status"] == "NOT_RUN" and case["evidence"] == []
    assert deployment_blockers(catalog), "design guards cannot authorise deployment"


@pytest.mark.parametrize("path, replacement, complaint", [
    (("media_contract",), None, "media contract: missing or malformed"),
    (("media_contract", "owner_criteria"), [], "media contract.owner_criteria"),
    (("media_contract", "prohibited_operations"), [], "media contract.prohibited_operations"),
    (("media_contract", "allowed_operations"), [], "media contract.allowed_operations"),
    (("media_contract", "attribution_is_authentication"), True, "media contract.attribution_is_authentication"),
    (("media_contract", "procurement", "scope"), "entire_vendor", "media contract.procurement.scope"),
    (("media_contract", "procurement", "hidden_processing"), "ignore", "media contract.procurement.hidden_processing"),
    (("media_contract", "procurement", "unavoidable_prohibited_processing"), "allow", "media contract.procurement.unavoidable_prohibited_processing"),
    (("media_contract", "procurement", "unrelated_optional_vendor_services"), "reject_vendor", "media contract.procurement.unrelated_optional_vendor_services"),
    (("media_contract", "request", "check_before_bytes"), False, "media contract.request.check_before_bytes"),
    (("media_contract", "request", "unknown_configuration"), "allow", "media contract.request.unknown_configuration"),
    (("media_contract", "request", "consent_override"), True, "media contract.request.consent_override"),
    (("media_contract", "response", "validation"), "top_level_only", "media contract.response.validation"),
    (("media_contract", "response", "unknown_or_forbidden_fields"), "log_then_drop", "media contract.response.unknown_or_forbidden_fields"),
    (("media_contract", "response", "raw_rejected_response_persistence"), True, "media contract.response.raw_rejected_response_persistence"),
    (("media_contract", "response", "protected_sinks"), ["ui"], "media contract.response.protected_sinks"),
    (("media_contract", "evidence", "originals"), "rewrite", "media contract.evidence.originals"),
    (("media_contract", "evidence", "legal_assessment"), "ban", "media contract.evidence.legal_assessment"),
    (("media_contract", "observations", "missing"), "PASS", "media contract.observations.missing"),
    (("media_contract", "observations", "equality"), "coerce", "media contract.observations.equality"),
    (("media_contract", "observations", "derive_from_expected"), True, "media contract.observations.derive_from_expected"),
    (("media_contract", "observations", "allowed_transcription"), "no_observation_needed", "media contract.observations.allowed_transcription"),
    (("media_contract", "observations", "denied_request"), "hidden_ui", "media contract.observations.denied_request"),
])
def test_media_policy_rejects_actual_changed_input(path, replacement, complaint):
    catalog, criteria = _inputs()
    assert check_evaluations(catalog, criteria) == []
    original = deepcopy(catalog)
    node, key = _target(catalog, path)
    assert node[key] != replacement
    node[key] = replacement
    assert catalog != original
    errors = check_evaluations(catalog, criteria)
    assert any(complaint in error for error in errors), errors
    assert check_evaluations(original, criteria) == []


@pytest.mark.parametrize("case_id, path, replacement, complaint", [
    ("EVAL-007", ("owner_criteria",), [], "EVAL-007: media acceptance ownership incomplete"),
    ("EVAL-007", ("inputs", "requested_operation"), "voice_identity", "EVAL-007 allowed request"),
    ("EVAL-007", ("inputs", "prohibited_request_variants"), [], "EVAL-007 prohibited requests"),
    ("EVAL-008", ("inputs", "forbidden_response_fields"), ["emotion"], "EVAL-008 response field population"),
    ("EVAL-008", ("inputs", "response_mutation_paths"), ["metadata"], "EVAL-008 response mutation paths"),
    ("EVAL-008", ("inputs", "provider_response", "segments"), [], "EVAL-008: response mutation containers must exist"),
    ("EVAL-008", ("inputs", "provider_response", "metadata", "operation"), "voice_identity", "EVAL-008: allowed provider transcript fixture missing"),
    ("EVAL-008", ("inputs", "frames"), [], "EVAL-008: original media and transcript fixtures must be nonempty"),
    ("EVAL-008", ("inputs", "transcript"), [], "EVAL-008: original media and transcript fixtures must be nonempty"),
    ("EVAL-008", ("inputs", "transcript", 0, "text"), "Different unobserved text", "EVAL-008: provider response and ordinary transcript disagree"),
    ("EVAL-008", ("inputs", "response_mutation_value"), "", "EVAL-008: forbidden response canary missing"),
    ("EVAL-008", ("inputs", "observation_mutations"), [], "EVAL-008: missing-observation controls absent"),
    ("EVAL-008", ("inputs", "observation_mutations", 0, "path"), "nonexistent", "EVAL-008: missing-observation control population changed"),
    ("EVAL-008", ("inputs", "observation_mutations", 3, "path"), "nonexistent", "EVAL-008: missing-observation control population changed"),
    ("EVAL-008", ("inputs", "observation_mutations", 4, "action"), "ignore", "EVAL-008: missing-observation control population changed"),
    ("EVAL-027", ("inputs", "processor_configuration", "hidden_prohibited_processing"), True, "EVAL-027 selected configuration.hidden_prohibited_processing"),
    ("EVAL-027", ("inputs", "processor_configuration", "vendor_offers_unrelated_optional_biometrics"), False, "EVAL-027 selected configuration.vendor_offers_unrelated_optional_biometrics"),
    ("EVAL-027", ("inputs", "configuration_mutations"), [], "EVAL-027: configuration controls absent"),
    ("EVAL-027", ("inputs", "configuration_mutations", 0, "field"), "nonexistent", "EVAL-027: configuration control population changed"),
])
def test_media_scenarios_reject_disappearing_counterexamples(case_id, path, replacement, complaint):
    catalog, criteria = _inputs()
    assert check_evaluations(catalog, criteria) == []
    original = deepcopy(catalog)
    node, key = _target(_case(catalog, case_id), path)
    assert node[key] != replacement
    node[key] = replacement
    assert catalog != original
    errors = check_evaluations(catalog, criteria)
    assert any(complaint in error for error in errors), errors


@pytest.mark.parametrize("case_id, path", [
    ("EVAL-007", "prohibited_requests.outbound_calls"),
    ("EVAL-008", "transcript.speaker_authenticated"),
    ("EVAL-008", "transcript.original_preserved"),
    ("EVAL-008", "provider.allowed_calls"),
    ("EVAL-008", "provider.successful_results"),
    ("EVAL-008", "after_restart.transcript_versions"),
    ("EVAL-008", "after_restart.original_hash_matches"),
    ("EVAL-008", "forbidden_response.downstream_occurrences"),
    ("EVAL-008", "forbidden_response.uninspected_sinks"),
    ("EVAL-008", "forbidden_response.inspected_sink_categories"),
    ("EVAL-008", "forbidden_response.sink_inventory_reconciled"),
    ("EVAL-027", "compliant_configuration.allowed_calls"),
    ("EVAL-027", "disallowed_configurations.outbound_calls"),
    ("EVAL-027", "disallowed_configurations.outbound_bytes"),
])
def test_media_success_and_denial_observations_cannot_disappear(case_id, path):
    catalog, criteria = _inputs()
    assert check_evaluations(catalog, criteria) == []
    case = _case(catalog, case_id)
    original = deepcopy(case)
    matches = [row for row in case["expected"] if row["path"] == path]
    assert len(matches) == 1
    case["expected"].remove(matches[0])
    assert case != original
    errors = check_evaluations(catalog, criteria)
    assert f"{case_id} media observation {path}: required observation missing or duplicated" in errors


@pytest.mark.parametrize("replacement", [None, 0, "false", True])
def test_false_observation_is_not_missing_zero_string_or_true(replacement):
    catalog, criteria = _inputs()
    assert check_evaluations(catalog, criteria) == []
    expected = next(row for row in _case(catalog, "EVAL-008")["expected"]
                    if row["path"] == "transcript.speaker_authenticated")
    assert expected["value"] is False
    expected["value"] = replacement
    assert type(expected["value"]) is not bool or expected["value"] is True
    errors = check_evaluations(catalog, criteria)
    assert "EVAL-008 media observation transcript.speaker_authenticated: required typed policy changed" in errors


@pytest.mark.parametrize("inspected", [[], ["ui"], ["storage", "logs", "traces", "caches", "ui"]])
def test_zero_leaks_do_not_hide_empty_or_incomplete_sink_inspection(inspected):
    catalog, criteria = _inputs()
    assert check_evaluations(catalog, criteria) == []
    case = _case(catalog, "EVAL-008")
    observations = {row["path"]: row for row in case["expected"]}
    for path in ("forbidden_response.downstream_occurrences", "forbidden_response.uninspected_sinks"):
        assert observations[path]["value"] == 0
    target = observations["forbidden_response.inspected_sink_categories"]
    assert set(target["value"]) == {"storage", "logs", "traces", "caches", "ui", "reasoning"}
    original = deepcopy(target["value"])
    target["value"] = inspected
    assert target["value"] != original
    errors = check_evaluations(catalog, criteria)
    assert "EVAL-008 media observation forbidden_response.inspected_sink_categories: required policy population changed" in errors


def test_unobserved_media_is_not_promoted_by_passing_design_checks():
    catalog, criteria = _inputs()
    assert check_evaluations(catalog, criteria) == []
    case = _case(catalog, "EVAL-008")
    assert case["execution_status"] == "NOT_RUN"
    case["execution_status"] = "PASS"
    errors = check_evaluations(catalog, criteria)
    assert "EVAL-008: specification cannot claim executed proof" in errors
