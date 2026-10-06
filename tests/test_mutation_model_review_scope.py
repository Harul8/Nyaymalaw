"""Model presentation retains all permissions and removes durable duplication."""
import json
from copy import deepcopy

import pytest

from nm.brain.mutation_contracts import (
    AUTHORITY_CONTRACT,
    model_review_scope,
    scoped_record_decisions,
)
from nm.shared.model_port import SchemaViolation, estimate_tokens
from tests.test_mutation_admission_adapters import OWNER, ledger


def scope(*, grant=None):
    return {
        "owner": OWNER,
        "requests": [{"request_index": 0, "record_requirement": {
            "kind": "change", "operation": "corrects", "target_ids": ["date"],
            "success_condition": "Correct the selected account while preserving attribution.",
        }, "task_id": "owned-inherited-task"}],
        "mutation_authority_contract": AUTHORITY_CONTRACT,
        "mutation_authorities": grant or ledger(),
    }


def test_lean_scope_preserves_exact_requests_and_each_declared_permission():
    original = scope()
    before = deepcopy(original)
    shown = model_review_scope(original)
    assert shown["owner"] == original["owner"]
    assert shown["requests"] == original["requests"]
    assert shown["mutation_authority_contract"] == AUTHORITY_CONTRACT
    assert shown["mutation_scopes"] == original["mutation_authorities"]["authorities"]
    assert "mutation_authorities" not in shown
    assert all(name not in shown for name in (
        "seal", "snapshot_digest", "source_digest", "source_catalogue", "target_catalogue"))
    shown["mutation_scopes"][0]["target_ids"].append("cannot-mutate-original")
    shown["requests"][0]["task_id"] = "cannot-mutate-original"
    assert original == before


def test_legacy_scope_retains_every_meaningful_field_without_aliasing():
    original = {"owner": OWNER, "requests": [], "additional_scope": {
        "source_linked_limit": "Use the full original attribution.",
    }}
    shown = model_review_scope(original)
    assert shown == original and shown is not original
    shown["additional_scope"]["source_linked_limit"] = "Changed locally"
    assert original["additional_scope"]["source_linked_limit"] != "Changed locally"
    assert model_review_scope(None) is None


@pytest.mark.parametrize("failure", ["missing", "corrupt", "unknown", "foreign_owner"])
def test_lean_model_presentation_cannot_hide_a_failed_integrity_dependency(failure):
    original = scope()
    if failure == "missing":
        original.pop("mutation_authorities")
    elif failure == "corrupt":
        original["mutation_authorities"]["source_catalogue"]["L1"]["quoted"] = "Forged source"
    elif failure == "unknown":
        original["mutation_authority_contract"] = "unknown"
    else:
        original["owner"] = {**OWNER, "matter_id": "different-matter"}
    with pytest.raises(SchemaViolation):
        model_review_scope(original)


def test_presentation_is_not_reusable_as_an_admission_ledger():
    shown = model_review_scope(scope())
    with pytest.raises(SchemaViolation, match="no authority ledger"):
        scoped_record_decisions({}, {}, shown)


def test_stable_lean_choices_reduce_tokens_without_changing_permission_equality():
    original = scope()
    original_tokens = estimate_tokens(json.dumps(original, ensure_ascii=False))
    shown = model_review_scope(original)
    shown_tokens = estimate_tokens(json.dumps(shown, ensure_ascii=False))
    assert shown_tokens < original_tokens
    assert shown["mutation_scopes"] == original["mutation_authorities"]["authorities"]
    assert shown["requests"] == original["requests"]
