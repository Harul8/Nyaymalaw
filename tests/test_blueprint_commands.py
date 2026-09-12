"""Class-A design controls must reject planted contract drift, not certify API work."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools._documents import safe_load
from tools.blueprint_commands import check_commands

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def population():
    catalogue = json.loads(
        (ROOT / "docs/blueprint/contracts/commands.json").read_text(encoding="utf-8")
    )
    registry = safe_load((ROOT / "docs/backlog/status.yaml").read_text(encoding="utf-8"))
    criteria = {a["id"] for row in registry["items"] for a in row.get("acceptance", [])}
    assert catalogue["x-commands"] and criteria
    assert check_commands(catalogue, criteria) == []
    return catalogue, criteria


def test_every_proposed_command_has_four_schema_witnesses(population):
    catalogue, criteria = population
    commands = catalogue["x-commands"]
    assert len(commands) == len({row["id"] for row in commands})
    assert sum(
        len(
            [
                key
                for key in row["examples"]
                if key in {"valid_request", "invalid_request", "valid_response", "invalid_response"}
            ]
        )
        for row in commands
    ) == 4 * len(commands)
    assert check_commands(catalogue, criteria) == []


def _command(doc, cid="create-matter"):
    return next(row for row in doc["x-commands"] if row["id"] == cid)


def _plant(doc, kind):
    row = _command(doc)
    if kind == "empty_population":
        doc["x-commands"] = []
    elif kind == "duplicate_command":
        doc["x-commands"].append(copy.deepcopy(row))
    elif kind == "missing_command":
        doc["x-commands"].remove(row)
    elif kind == "orphan_definition":
        doc["$defs"]["unregistered_request"] = copy.deepcopy(doc["$defs"]["create-matter_request"])
    elif kind == "missing_definition":
        del doc["$defs"]["create-matter_request"]
    elif kind == "dangling_criterion":
        row["owner_ac"] = ["BK-9999-AC1"]
    elif kind == "empty_owner":
        row["owner_ac"] = []
    elif kind == "authored_live_claim":
        doc["x-implementation-state"] = "implemented"
    elif kind == "unknown_catalogue_field":
        doc["done"] = True
    elif kind == "unknown_command_field":
        row["verified"] = True
    elif kind == "unknown_example_field":
        row["examples"]["passed"] = True
    elif kind == "empty_auth_rule":
        row["authorization"] = " "
    elif kind == "empty_records":
        row["authoritative_records"] = []
    elif kind == "empty_retry":
        row["retry"] = ""
    elif kind == "invalid_current_route":
        row["current_route"] = "POST /made-up-route"
    elif kind == "nonlocal_ref":
        row["request_schema"]["$ref"] = "https://example.invalid/must-never-fetch"
    elif kind == "dynamic_ref":
        doc["$defs"]["Id"]["$dynamicRef"] = "https://example.invalid/must-never-fetch"
    elif kind == "nested_schema_id":
        doc["$defs"]["VersionRef"]["$id"] = "https://example.invalid/rebase-local-refs"
    elif kind == "open_object":
        doc["$defs"]["Commission"]["additionalProperties"] = True
    elif kind == "unconstrained_response":
        doc["$defs"]["create-matter_response"]["properties"]["data"] = True
    elif kind == "bad_required":
        doc["$defs"]["Commission"]["required"].append("undefined_field")
    elif kind == "positive_rejected":
        del row["examples"]["valid_request"]["body"]["title"]
    elif kind == "negative_unchanged":
        row["examples"]["invalid_request"] = copy.deepcopy(row["examples"]["valid_request"])
    elif kind == "negative_still_valid":
        row["examples"]["invalid_request"] = copy.deepcopy(row["examples"]["valid_request"])
        row["examples"]["invalid_request"]["body"]["title"] = "Different synthetic title"
    elif kind == "invalid_date":
        row["examples"]["valid_response"]["observed_at"] = "2026-02-30T12:00:00Z"
    elif kind == "invalid_uri":
        _command(doc, "begin-factor")["examples"]["valid_response"]["data"][
            "provider_challenge_url"
        ] = "https://has a space.invalid/"
    elif kind == "missing_csrf":
        doc["$defs"]["create-matter_request"]["properties"]["headers"]["required"].remove(
            "X-CSRF-Token"
        )
    elif kind == "route_param_mismatch":
        _command(doc, "get-matter")["path"] = "/v1/matters/{other_id}"
    elif kind == "unknown_error":
        row["errors"].append("MADE_UP_SUCCESS")
    elif kind == "error_status_drift":
        doc["x-error-catalog"][0]["http_status"] = 500
    elif kind == "binary_proof_missing":
        del _command(doc, "get-asset-content")["binary_contract"]["verification"]
    elif kind == "boolean_status":
        row["success_status"] = True
    elif kind == "schema_alias":
        row["request_schema"] = copy.deepcopy(_command(doc, "close-matter")["request_schema"])
    else:
        raise AssertionError(f"unrecognised planted mutation {kind}")


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("empty_population", "empty or malformed command population"),
        ("duplicate_command", "duplicate command"),
        ("missing_command", "definitions and command population differ"),
        ("orphan_definition", "definitions and command population differ"),
        ("missing_definition", "unresolved/nonlocal"),
        ("dangling_criterion", "unregistered acceptance"),
        ("empty_owner", "owner_ac"),
        ("authored_live_claim", "non-design claim"),
        ("unknown_catalogue_field", "catalogue fields"),
        ("unknown_command_field", "command fields"),
        ("unknown_example_field", "example fields"),
        ("empty_auth_rule", "missing authorization"),
        ("empty_records", "authoritative_records"),
        ("empty_retry", "missing retry"),
        ("invalid_current_route", "compatibility route"),
        ("nonlocal_ref", "unresolved/nonlocal"),
        ("dynamic_ref", "dynamic/recursive"),
        ("nested_schema_id", "nested schema identity/rebasing"),
        ("open_object", "object must be closed"),
        ("unconstrained_response", "unconstrained field schema"),
        ("bad_required", "required/properties"),
        ("positive_rejected", "positive request witness rejected"),
        ("negative_unchanged", "mutation changed nothing"),
        ("negative_still_valid", "negative request witness was not rejected"),
        ("invalid_date", "positive response witness rejected"),
        ("invalid_uri", "positive response witness rejected"),
        ("missing_csrf", "mutation missing idempotency/CSRF"),
        ("route_param_mismatch", "route and required path parameters differ"),
        ("unknown_error", "unknown error code"),
        ("error_status_drift", "error-catalogue combinations differ"),
        ("binary_proof_missing", "binary byte-verification"),
        ("boolean_status", "invalid success status"),
        ("schema_alias", "own its named definition"),
    ],
)
def test_contract_control_rejects_its_planted_failure(population, kind, expected):
    original, criteria = population
    mutated = copy.deepcopy(original)
    _plant(mutated, kind)
    assert mutated != original, f"{kind} did not change the population"
    errors = check_commands(mutated, criteria)
    assert any(expected in error for error in errors), (kind, expected, errors)


@pytest.mark.parametrize("bad", [None, [], {}, {"x-commands": []}])
def test_missing_catalogue_is_not_success(bad):
    assert check_commands(bad, set())
