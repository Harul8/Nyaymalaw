"""Candidate source-owner recovery contracts, using fabricated Judge decisions."""

import json
from copy import deepcopy

import pytest

from nm.brain import record_review as candidate
from nm.brain.conversation import Message
from nm.brain.material import addressed_sources
from nm.brain.material_verification import _schema as review_schema
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ContextOverflow,
    ModelResult,
    SchemaViolation,
    Tier,
    TierUnavailable,
    Usage,
    require_schema,
)


class Model:
    def __init__(self, outputs, *, downgrade=False, budget=100_000):
        self.outputs = iter(deepcopy(outputs))
        self.calls = []
        self.downgrade = downgrade
        self.budget = budget

    def context_budget(self, tier):
        assert tier == Tier.JUDGE
        return self.budget

    def structured(self, prompt, schema, tier, *, max_tokens):
        assert tier == Tier.JUDGE
        output = next(self.outputs)
        self.calls.append((prompt, schema, output))
        require_schema(output, schema)
        return ModelResult(
            text=None, data=output,
            tier=Tier.ROUTINE if self.downgrade else Tier.JUDGE,
            provider="offline", model="fabricated-independent-read",
            usage=Usage(0, 0, 0), latency_ms=0,
            completion=Completion.COMPLETE,
        )


def context():
    earlier = (
        Message("earlier-account", "advocate", "Our records show receipt on Thursday."),
        Message("earlier-analysis", "nm", "The previous formulation should be checked."),
    )
    latest = "The supplier retained the signed original. Recheck your interpretation."
    payload, current, prior = addressed_sources(earlier, latest)
    catalogue = {
        key: {"turn_id": ref.turn_id, "role": ref.role, "quoted": ref.quoted,
              "content_role": "reported_matter_account",
              "reason": "Original supplied account."}
        for key, ref in prior.items() if ref.role == "advocate"
    }
    catalogue.update({key: {
        "turn_id": "latest", "role": "advocate", "quoted": words,
        "content_role": "examination_material" if key == "L1" else "work_instruction",
        "reason": "First candidate-free purpose proposal.",
    } for key, words in current.items()})
    return payload, catalogue


def output(role="reported_matter_account", *,
           reason="Original framing reports substantive account."):
    return {"source_treatments": {"L1": {"content_role": role, "reason": reason}}}


def reconsider(model, *, payload=None, catalogue=None, selected=("L1",)):
    original_payload, original_catalogue = context()
    return candidate.reconsider_account_sources(
        model, payload=payload if payload is not None else original_payload,
        latest_turn_id="latest",
        source_treatments=catalogue if catalogue is not None else original_catalogue,
        source_ids=selected,
    )


def test_reconsideration_is_candidate_free_full_context_owned_subset_and_immutable_merge():
    payload, catalogue = context()
    original = deepcopy(catalogue)
    model = Model([output()])
    merged, changed = reconsider(model, payload=payload, catalogue=catalogue)
    assert changed == ("L1",)
    assert merged["L1"]["content_role"] == "reported_matter_account"
    assert merged["L1"]["quoted"] == catalogue["L1"]["quoted"]
    assert merged["L1"]["turn_id"] == "latest"
    assert merged["L1"]["role"] == "advocate"
    assert {key: row for key, row in merged.items() if key != "L1"} == {
        key: row for key, row in catalogue.items() if key != "L1"
    }
    assert catalogue == original
    prompt, schema, _ = model.calls[0]
    assert prompt.operation == "reconsider_account_sources"
    assert json.loads(prompt.user) == {**payload, "source_ids": ["L1"]}
    assert schema["properties"]["source_treatments"]["required"] == ["L1"]
    assert len(model.calls) == 1


@pytest.mark.parametrize("role", ["examination_material", "uncertain", "mixed", "work_instruction"])
def test_changed_roles_and_uncertainty_are_decisions_not_forced_promotion(role):
    model = Model([output(role)])
    merged, changed = reconsider(model)
    assert merged["L1"]["content_role"] == role
    assert changed == (() if role == "examination_material" else ("L1",))
    assert len(model.calls) == 1


def test_explanation_change_alone_is_not_role_change():
    _, catalogue = context()
    model = Model([output(
        "examination_material", reason="A different explanation of the same purpose.")])
    merged, changed = reconsider(model, catalogue=catalogue)
    assert changed == ()
    assert merged["L1"]["reason"] != catalogue["L1"]["reason"]


def test_duplicate_exact_selection_ids_normalize_without_another_call():
    model = Model([output()])
    _, changed = reconsider(model, selected=("L1", "L1"))
    assert changed == ("L1",)
    assert json.loads(model.calls[0][0].user)["source_ids"] == ["L1"]


@pytest.mark.parametrize("selected", [(), ("foreign-source",), (1,), "L1"])
def test_unowned_or_empty_selection_fails_before_dispatch(selected):
    model = Model([])
    with pytest.raises(SchemaViolation):
        reconsider(model, selected=selected)
    assert model.calls == []


@pytest.mark.parametrize("field,value", [
    ("turn_id", "other-turn"), ("role", "nm"),
    ("quoted", "Fabricated replacement words."),
    ("content_role", "unsupported-vocabulary"), ("reason", "  "),
])
def test_catalogue_canonical_identity_and_roles_are_checked_before_dispatch(field, value):
    _, catalogue = context()
    catalogue["L1"][field] = value
    model = Model([])
    with pytest.raises(SchemaViolation):
        reconsider(model, catalogue=catalogue)
    assert model.calls == []


def test_missing_unselected_catalogue_member_blocks_before_dispatch():
    _, catalogue = context()
    del catalogue["L2"]
    model = Model([])
    with pytest.raises(SchemaViolation):
        reconsider(model, catalogue=catalogue)
    assert model.calls == []


def test_caller_cannot_supply_candidates_or_review_reasons_as_source_input():
    payload, _ = context()
    payload["candidates"] = [{"statement": "Desired formulation"}]
    model = Model([])
    with pytest.raises(SchemaViolation):
        reconsider(model, payload=payload)
    assert model.calls == []


def test_malformed_subset_gets_one_structural_correction_and_no_silent_peer_change():
    wrong = output()
    wrong["source_treatments"]["L2"] = {"content_role": "mixed", "reason": "Extra decision."}
    model = Model([wrong, output()])
    merged, changed = reconsider(model)
    assert changed == ("L1",)
    assert merged["L2"]["content_role"] == "work_instruction"
    assert len(model.calls) == 2
    correction = json.loads(model.calls[1][0].user)
    assert correction["original_input"]["source_ids"] == ["L1"]
    assert "validation_issue" in correction


def test_whitespace_reason_gets_bounded_correction_then_can_remain_uncertain():
    model = Model([output(reason=" \n\t "), output("uncertain")])
    merged, changed = reconsider(model)
    assert merged["L1"]["content_role"] == "uncertain"
    assert changed == ("L1",)
    assert len(model.calls) == 2


def test_exhausted_structural_correction_does_not_mutate_original_catalogue():
    _, catalogue = context()
    original = deepcopy(catalogue)
    model = Model([output(reason="  "), output(reason="  ")])
    with pytest.raises(SchemaViolation):
        reconsider(model, catalogue=catalogue)
    assert catalogue == original
    assert len(model.calls) == 2


def test_independent_tier_cannot_be_downgraded_into_source_reconsideration():
    model = Model([output()], downgrade=True)
    with pytest.raises(TierUnavailable):
        reconsider(model)
    assert len(model.calls) == 1


def test_complete_original_context_must_fit_without_trim_or_dispatch():
    model = Model([], budget=1)
    with pytest.raises(ContextOverflow):
        reconsider(model)
    assert model.calls == []


def verdict(*, supplies=True, supports=True):
    return {
        "candidate_id": "D1", "operation_supported": True,
        "verdict": "accept", "reason": "Explicit original-account comparison.",
        "account_check": {
            "content_role": "reported_matter_account", "supported": True,
            "introduces_legal_analysis": False, "source_ids": ["L1"],
            "source_checks": [{
                "source_id": "L1", "supplies_account_content": supplies,
                "supports_proposal": supports, "reason": "Original framing judged independently.",
            }], "reason": "Full proposed assertion was compared.",
        }, "target_checks": [],
    }


def diagnostics(row, catalogue):
    schema = review_schema(("D1",), ("L1",))["properties"]["verdicts"]["items"]
    return candidate.source_role_disagreements(row, {"L1"}, catalogue, schema=schema)


@pytest.mark.parametrize("role", [
    "examination_material", "work_instruction", "nm_interpretation", "uncertain"])
def test_typed_disagreement_selects_original_nonaccount_source_without_reason_matching(role):
    _, catalogue = context()
    catalogue["L1"]["content_role"] = role
    row = verdict()
    row["reason"] = "There are no machine diagnostic phrases in this explanation."
    assert diagnostics(row, catalogue) == ({
        "source_id": "L1", "content_role": role, "supplies_account_content": True,
    },)


@pytest.mark.parametrize("role", ["reported_matter_account", "reported_party_position", "mixed"])
def test_legitimate_account_roles_do_not_trigger_reconsideration(role):
    _, catalogue = context()
    catalogue["L1"]["content_role"] = role
    assert diagnostics(verdict(), catalogue) == ()


@pytest.mark.parametrize("supplies,supports", [(False, False), (False, True)])
def test_nonaccount_source_check_does_not_become_recovery_from_other_attestations(
    supplies, supports
):
    _, catalogue = context()
    assert diagnostics(verdict(supplies=supplies, supports=supports), catalogue) == ()


def test_role_disagreement_can_be_reported_with_rejected_proposal_and_without_support():
    _, catalogue = context()
    row = verdict(supports=False)
    row.update(verdict="reject", operation_supported=False)
    assert diagnostics(row, catalogue)[0]["source_id"] == "L1"


@pytest.mark.parametrize("mutation", [
    "foreign", "duplicate", "missing_check", "wrong_bool", "unexpected_field", "empty_reason"])
def test_malformed_or_unowned_verdict_cannot_trigger_source_recovery(mutation):
    _, catalogue = context()
    row = verdict()
    account = row["account_check"]
    if mutation == "foreign":
        account["source_ids"] = ["foreign"]
        account["source_checks"][0]["source_id"] = "foreign"
    elif mutation == "duplicate":
        account["source_checks"].append(deepcopy(account["source_checks"][0]))
    elif mutation == "missing_check":
        account["source_checks"] = []
    elif mutation == "wrong_bool":
        account["source_checks"][0]["supplies_account_content"] = "true"
    elif mutation == "unexpected_field":
        row["source_reconsideration"] = True
    else:
        account["source_checks"][0]["reason"] = " \t "
    with pytest.raises(SchemaViolation):
        diagnostics(row, catalogue)


def test_diagnostic_cannot_use_malformed_catalogue_role():
    _, catalogue = context()
    catalogue["L1"]["content_role"] = "bogus"
    with pytest.raises(SchemaViolation):
        diagnostics(verdict(), catalogue)


def review_cache():
    _, sources = context()
    ids = ("D1", "D2", "D3", "D4")
    original = {"original_transcript": "complete original words", "owned_targets": ["a", "b", "c"],
                "review_scope": {"requests": [0]},
                "candidates": [{"candidate_id": identity, "statement": identity}
                               for identity in ids]}
    decisions = {identity: {**verdict(), "candidate_id": identity} for identity in ids}
    accounts = {"D1": {"L1"}, "D2": {"L2"}, "D3": {"P1S1"}, "D4": {"L2"}}
    targets = {"D1": {"a"}, "D2": {"a", "b"}, "D3": {"b"}, "D4": {"c"}}
    state = {}
    candidate.remember_independent_review(
        state, context=original, source_treatments=sources, decisions=decisions)
    return state, original, sources, decisions, accounts, targets


def resume_cache(state, original, sources, accounts, targets, *, selected=()):
    return candidate.retained_independent_review(
        state, context=original, source_treatments=sources,
        account_ids=accounts, targets=targets, recheck_source_ids=selected)


def test_cache_retains_unchanged_checked_decisions_and_does_not_share_mutable_rows():
    state, original, sources, decisions, accounts, targets = review_cache()
    retained = resume_cache(state, original, sources, accounts, targets)
    assert retained == decisions
    retained["D1"]["reason"] = "Modified caller copy."
    assert resume_cache(state, original, sources, accounts, targets) == decisions


def test_changed_source_invalidates_transitive_atomic_target_dependencies_only():
    state, original, sources, _, accounts, targets = review_cache()
    sources["L1"]["content_role"] = "reported_matter_account"
    retained = resume_cache(state, original, sources, accounts, targets, selected=("L1",))
    assert set(retained) == {"D4"}


def test_changed_source_without_target_dependencies_retains_unaffected_peers():
    state, original, sources, _, accounts, targets = review_cache()
    targets = {identity: set() for identity in targets}
    sources["L1"]["content_role"] = "reported_matter_account"
    retained = resume_cache(state, original, sources, accounts, targets, selected=("L1",))
    assert set(retained) == {"D2", "D3", "D4"}


def test_new_successor_invalidates_prior_shared_target_restoration_without_renumbering():
    state, original, sources, _, accounts, targets = review_cache()
    original["candidates"].append({
        "candidate_id": "D5", "statement": "Additional supported account."})
    accounts["D5"] = {"L2"}
    targets["D5"] = {"b"}
    retained = resume_cache(state, original, sources, accounts, targets)
    assert set(retained) == {"D4"}


def test_new_independent_proposal_preserves_prior_decisions_and_original_ids():
    state, original, sources, decisions, accounts, targets = review_cache()
    original["candidates"].append({
        "candidate_id": "D5", "statement": "Additional supported account."})
    accounts["D5"] = {"L2"}
    targets["D5"] = set()
    assert resume_cache(state, original, sources, accounts, targets) == decisions


def test_reason_only_source_change_does_not_require_semantic_reapproval():
    state, original, sources, decisions, accounts, targets = review_cache()
    sources["L1"]["reason"] = "Another substantive explanation of the same original purpose."
    assert resume_cache(state, original, sources, accounts, targets) == decisions


@pytest.mark.parametrize("field", ["original_transcript", "review_scope", "owned_targets"])
def test_cache_rejects_changed_original_context_scope_and_owned_target_catalogue(field):
    state, original, sources, _, accounts, targets = review_cache()
    original[field] = "Changed owning context."
    with pytest.raises(SchemaViolation):
        resume_cache(state, original, sources, accounts, targets)


@pytest.mark.parametrize("field", ["turn_id", "role", "quoted"])
def test_cache_rejects_canonical_source_provenance_change(field):
    state, original, sources, _, accounts, targets = review_cache()
    sources["L1"][field] = "Different owner or evidence."
    with pytest.raises(SchemaViolation):
        resume_cache(state, original, sources, accounts, targets, selected=("L1",))


def test_cache_rejects_undeclared_source_role_change():
    state, original, sources, _, accounts, targets = review_cache()
    sources["L1"]["content_role"] = "reported_matter_account"
    with pytest.raises(SchemaViolation):
        resume_cache(state, original, sources, accounts, targets)


def test_cache_rejects_unowned_source_recheck_id():
    state, original, sources, _, accounts, targets = review_cache()
    with pytest.raises(SchemaViolation):
        resume_cache(state, original, sources, accounts, targets, selected=("foreign-source",))


@pytest.mark.parametrize("mutation", ["remove", "reorder", "rewrite", "renumber"])
def test_cache_original_proposals_cannot_be_removed_reordered_rewritten_or_renumbered(mutation):
    state, original, sources, _, accounts, targets = review_cache()
    if mutation == "remove":
        original["candidates"].pop()
    elif mutation == "reorder":
        original["candidates"].reverse()
    elif mutation == "rewrite":
        original["candidates"][0]["statement"] = "Altered assertion."
    else:
        original["candidates"][0]["candidate_id"] = "renumbered"
    with pytest.raises(SchemaViolation):
        resume_cache(state, original, sources, accounts, targets)


def test_cache_rejects_nested_checked_decision_mutation():
    state, original, sources, _, accounts, targets = review_cache()
    state["cache"].decisions["D1"]["reason"] = "Mutated cached evidence."
    with pytest.raises(SchemaViolation):
        resume_cache(state, original, sources, accounts, targets)


def test_plain_model_shaped_dictionary_cannot_impersonate_code_issued_review_cache():
    _, original, sources, decisions, accounts, targets = review_cache()
    state = {"cache": {"context": original, "source_treatments": sources, "decisions": decisions}}
    with pytest.raises(SchemaViolation):
        resume_cache(state, original, sources, accounts, targets)


@pytest.mark.parametrize("field", ["linked_records", "active_disputes", "active_material"])
def test_additional_owned_record_context_preserves_unchanged_checked_decisions(field):
    state, original, sources, decisions, accounts, targets = review_cache()
    original[field] = [{"id": "old", "statement": "Exact canonical original record."}]
    candidate.remember_independent_review(
        state, context=original, source_treatments=sources, decisions=decisions)
    original[field].append({"id": "additional", "statement": "Additional owned canonical record."})
    assert resume_cache(state, original, sources, accounts, targets) == decisions


@pytest.mark.parametrize("field", ["linked_records", "active_disputes", "active_material"])
@pytest.mark.parametrize("mutation", ["removed", "rewritten", "duplicate", "missing_identity"])
def test_prior_owned_record_context_cannot_be_removed_rewritten_or_duplicated(field, mutation):
    state, original, sources, decisions, accounts, targets = review_cache()
    original[field] = [{"id": "old", "statement": "Exact canonical original record."}]
    candidate.remember_independent_review(
        state, context=original, source_treatments=sources, decisions=decisions)
    if mutation == "removed":
        original[field] = []
    elif mutation == "rewritten":
        original[field][0]["statement"] = "Rewritten evidence."
    elif mutation == "duplicate":
        original[field].append(deepcopy(original[field][0]))
    else:
        original[field].append({"statement": "Record without owner."})
    with pytest.raises(SchemaViolation):
        resume_cache(state, original, sources, accounts, targets)
