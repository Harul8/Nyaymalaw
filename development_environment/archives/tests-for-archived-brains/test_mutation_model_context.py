"""Model-only mutation proof pruning never trims original words or choices."""
import json
from copy import deepcopy

import pytest

from nm.brain.mutation_contracts import AUTHORITY_CONTRACT, model_mutation_context
from nm.shared.model_port import SchemaViolation, estimate_tokens
from tests.test_mutation_admission_adapters import OWNER, ledger


def fixture():
    grant = ledger()
    scope = {"owner": OWNER, "requests": [{"request_index": 0, "record_requirement": {
        "kind": "change", "operation": "corrects", "target_ids": ["date"],
        "success_condition": "Retain exact attribution and every limiting condition.",
    }}], "mutation_authority_contract": AUTHORITY_CONTRACT, "mutation_authorities": grant}
    original = "Exact advocate words, including uncertainty.\nAnother complete passage."
    return {
        "earlier_conversation": [{"turn_id": "original", "role": "advocate", "text": original}],
        "latest_message": original,
        "material_coverage": {"execution": {
            "owner": OWNER, "mutation_authorities": grant, "review_scope": scope,
            "stages": {"detail_review": {"account_coverage": {"review_scope": scope}}},
        }},
        "unrelated_domain": {"contract": "legal_document", "seal": "An attributed physical seal",
                             "source_catalogue": {"whole_document": original}},
        "tuple_context": (original, {"recovery_scope": {"review_scope": scope}}),
    }


def walk(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from walk(item)


def test_nested_presenter_preserves_exact_original_words_other_domains_and_each_permission():
    original = fixture()
    before = deepcopy(original)
    shown = model_mutation_context(original)
    assert shown["earlier_conversation"] == original["earlier_conversation"]
    assert shown["latest_message"] == original["latest_message"]
    assert shown["unrelated_domain"] == original["unrelated_domain"]
    assert isinstance(shown["tuple_context"], tuple)
    full = [row for row in walk(original) if row.get("contract") == AUTHORITY_CONTRACT]
    lean = [row for row in walk(shown) if row.get("contract") == AUTHORITY_CONTRACT]
    assert len(lean) == len(full) == 4
    for stored, displayed in zip(full, lean, strict=True):
        assert set(displayed) == {"contract", "owner", "expected_version", "authorities"}
        assert all(displayed[name] == stored[name] for name in displayed)
    lean[0]["authorities"][0]["target_ids"].append("cannot-alter-original")
    assert original == before


def test_nested_duplicate_proof_data_reduces_context_tokens_without_changing_complete_transcript():
    original = fixture()
    shown = model_mutation_context(original)
    full_tokens = estimate_tokens(json.dumps(original, ensure_ascii=False))
    lean_tokens = estimate_tokens(json.dumps(shown, ensure_ascii=False))
    assert lean_tokens < full_tokens
    assert shown["earlier_conversation"] == original["earlier_conversation"]
    assert shown["latest_message"] == original["latest_message"]
    assert shown["material_coverage"]["execution"]["review_scope"]["requests"] == original[
        "material_coverage"]["execution"]["review_scope"]["requests"]


@pytest.mark.parametrize("failure", ["missing_seal", "changed_sources", "missing_targets"])
def test_recursive_presentation_does_not_hide_malformed_typed_shared_ledger(failure):
    original = fixture()
    grant = original["material_coverage"]["execution"]["mutation_authorities"]
    if failure == "missing_seal":
        grant.pop("seal")
    elif failure == "changed_sources":
        grant["source_catalogue"]["L1"]["quoted"] = "Altered original words"
    else:
        grant.pop("target_catalogue")
    with pytest.raises(SchemaViolation):
        model_mutation_context(original)


def test_context_without_owned_ledgers_remains_identical_and_independent():
    original = {"words": ["Full advocate words."], "domain": {"id": "record", "value": 7}}
    shown = model_mutation_context(original)
    assert shown == original and shown is not original
    shown["words"].append("Local presentation change")
    assert original["words"] == ["Full advocate words."]
