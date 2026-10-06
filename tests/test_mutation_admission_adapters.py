"""Admission and durable replay neighbours for generic record mutation scopes."""
from copy import deepcopy

import pytest

from nm.brain.material import MaterialCandidate, PriorReference
from nm.brain.mutation_contracts import (
    AUTHORITY_CONTRACT,
    bind_record_mutation,
    build_mutation_authorities,
    scoped_record_decisions,
    validate_record_mutation,
)
from nm.shared.model_port import SchemaViolation

OWNER = {"matter_id": "matter", "advocate_id": "advocate", "turn_id": "second",
         "offer_digest": "exact-offer-digest"}
WORDS = {("first", "advocate"): "The event happened on Monday. The document is with the client."}
TARGETS = {
    "date": {"id": "date", "source_turn_id": "first", "quoted": "The event happened on Monday.",
             "statement": "The event happened on Monday."},
    "custody": {"id": "custody", "source_turn_id": "first",
                "quoted": "The document is with the client.",
                "statement": "The document is with the client."},
}
SOURCES = {
    "L1": {"turn_id": "second", "role": "advocate", "quoted": "Sorry, Tuesday.",
           "content_role": "reported_matter_account"},
    "L2": {"turn_id": "second", "role": "advocate", "quoted": "Review the date reading.",
           "content_role": "work_instruction"},
    "P1S1": {"turn_id": "first", "role": "advocate",
              "quoted": "The event happened on Monday.",
              "content_role": "reported_matter_account"},
    "P1S2": {"turn_id": "first", "role": "advocate",
              "quoted": "The document is with the client.",
              "content_role": "reported_matter_account"},
}


def ledger(*, source="L1", kind="account_contribution", relation="corrects", target="date"):
    return build_mutation_authorities(
        owner=OWNER, expected_version=1, target_catalogue=TARGETS,
        source_catalogue=SOURCES, request_indices=[0], proposals=[{
            "request_index": 0, "authority_kind": kind, "authority_source_ids": [source],
            "target_scope": "exact", "target_ids": [target], "permitted_relations": [relation],
        }])


def candidate(*, target="date", quote="Sorry, Tuesday.", relation="corrects", kind="event"):
    reference = TARGETS[target]
    return MaterialCandidate(
        kind=kind, statement="The event happened on Tuesday.", quoted=quote,
        relation=relation, prior_references=(PriorReference(
            "first", "advocate", reference["quoted"]),), matter_scope="current",
        basis="reported", importance="material", why_material="The timing is consequential.",
        placement="matter", related_material_ids=(target,) if kind != "dispute" else (),
        related_dispute_ids=(target,) if kind == "dispute" else (),
    )


def decision(*support, verdict="accept"):
    return {"candidate_id": "D1", "verdict": verdict, "reason": "Independent account check.",
            "account_check": {"source_ids": list(support)}, "target_checks": []}


def scope(grant):
    return {"owner": OWNER, "mutation_authorities": grant}


def saved(candidate_value, grant):
    sink = {}
    reviewed = scoped_record_decisions(
        {"D1": decision("L1")}, {"D1": candidate_value}, scope(grant), binding_sink=sink)
    assert reviewed["D1"]["verdict"] == "accept"
    proposal = candidate_value.recorded("second", 0)
    proposal["mutation_authority"] = bind_record_mutation(proposal, grant, binding=sink["D1"])
    return proposal


def turn_and_execution(grant):
    turn = {**OWNER, "message": "Sorry, Tuesday. Review the date reading."}
    execution = {"owner": OWNER, "expected_version": 1,
                 "mutation_authority_contract": AUTHORITY_CONTRACT,
                 "mutation_authorities": grant}
    return turn, execution


def test_wrong_owned_target_is_withheld_and_independent_new_account_survives():
    grant = ledger()
    wrong = candidate(target="custody")
    new = MaterialCandidate(
        kind="event", statement="A separate event is reported.", quoted="Sorry, Tuesday.",
        relation="new", prior_references=(), matter_scope="current", basis="reported",
        importance="material", why_material="Independent reported account.",
        placement="matter")
    original = {"D1": decision("L1", "P1S2"), "D2": decision("L1")}
    sink = {}
    checked = scoped_record_decisions(original, {"D1": wrong, "D2": new}, scope(grant),
                                      binding_sink=sink)
    assert checked["D1"]["verdict"] == "reject"
    assert checked["D1"]["admission_issue"] == "mutation_scope"
    assert "scope" in checked["D1"]["reason"]
    assert checked["D1"]["model_decision"] == original["D1"]
    assert checked["D2"] == original["D2"]
    assert original["D1"]["verdict"] == "accept"
    assert sink == {}


def test_implicit_contribution_correction_gets_actual_review_selected_support():
    grant = ledger()
    sink = {}
    checked = scoped_record_decisions({"D1": decision("L1")}, {"D1": candidate()},
                                      scope(grant), binding_sink=sink)
    assert checked["D1"]["verdict"] == "accept"
    assert checked["D1"]["mutation_authority"] == sink["D1"]
    assert sink["D1"]["supporting_source_ids"] == ["L1"]
    assert sink["D1"]["attached_context_source_ids"] == ["P1S1"]


def test_instruction_can_authorize_repair_from_earlier_original_account():
    grant = ledger(source="L2", kind="interpretation_review")
    value = candidate(quote="Review the date reading.")
    checked = scoped_record_decisions({"D1": decision("P1S1")}, {"D1": value}, scope(grant))
    assert checked["D1"]["verdict"] == "accept"
    assert checked["D1"]["mutation_authority"]["supporting_source_ids"] == ["P1S1"]


@pytest.mark.parametrize("kind", ["event", "dispute"])
def test_shared_adapter_applies_to_material_and_dispute_targets(kind):
    grant = ledger()
    checked = scoped_record_decisions({"D1": decision("L1")},
                                      {"D1": candidate(target="custody", kind=kind)}, scope(grant))
    assert checked["D1"]["admission_issue"] == "mutation_scope"


def test_unversioned_direct_verifier_preserves_legacy_decisions():
    original = {"D1": decision("L1")}
    for review in (None, {}, {"owner": OWNER, "requests": []}):
        assert scoped_record_decisions(original, {"D1": candidate()}, review) is original


def test_explicit_rejection_is_preserved_without_attempting_a_binding():
    rejected = {"D1": decision(verdict="reject")}
    assert scoped_record_decisions(rejected, {"D1": candidate(target="custody")},
                                   scope(ledger())) == rejected


def test_corrupted_supplied_ledger_is_fatal_instead_of_saved_as_a_unit_rejection():
    grant = ledger()
    grant["target_catalogue"]["date"]["statement"] = "Changed behind the scope owner's back."
    with pytest.raises(SchemaViolation, match="changed after"):
        scoped_record_decisions({"D1": decision("L1")}, {"D1": candidate()}, scope(grant))


def test_review_scope_owner_disagreement_is_fatal():
    review = scope(ledger())
    review["owner"] = {**OWNER, "turn_id": "another"}
    with pytest.raises(SchemaViolation, match="different turn owner"):
        scoped_record_decisions({"D1": decision("L1")}, {"D1": candidate()}, review)


def test_empty_support_cannot_be_filled_from_attached_context():
    checked = scoped_record_decisions({"D1": decision()}, {"D1": candidate()}, scope(ledger()))
    assert checked["D1"]["admission_issue"] == "mutation_scope"
    assert "supporting_source_ids" in checked["D1"]["reason"]


def test_final_binding_and_replay_preserve_source_and_target_scope():
    grant = ledger()
    proposal = saved(candidate(), grant)
    turn, execution = turn_and_execution(grant)
    assert validate_record_mutation(proposal, turn=turn, execution=execution,
                                    prior_words=WORDS, source_catalogue=SOURCES,
                                    target_catalogue={"date": TARGETS["date"]}) == "bound"


def test_final_binding_requires_admitted_certificate_or_explicit_review_support():
    with pytest.raises(SchemaViolation, match="no admitted independent support"):
        bind_record_mutation(candidate().recorded("second", 0), ledger())


def test_final_binding_cannot_change_support_selected_by_review():
    grant = ledger()
    proposal = saved(candidate(), grant)
    with pytest.raises(SchemaViolation, match="changed its independently selected support"):
        bind_record_mutation(proposal, grant, supporting_source_ids=["P1S1"])


def test_fresh_missing_binding_cannot_downgrade_to_legacy():
    grant = ledger()
    proposal = candidate().recorded("second", 0)
    turn, execution = turn_and_execution(grant)
    with pytest.raises(SchemaViolation, match="saved authority binding"):
        validate_record_mutation(proposal, turn=turn, execution=execution)


def test_genuine_untracked_history_remains_readable_without_certifying_it():
    turn, _ = turn_and_execution(ledger())
    assert validate_record_mutation(candidate().recorded("second", 0), turn=turn,
                                    execution={"owner": OWNER}) == "legacy_untracked"


@pytest.mark.parametrize("part", ["actual_turn", "execution", "snapshot"])
def test_replay_rejects_actual_owner_and_snapshot_mismatch(part):
    grant = ledger()
    proposal = saved(candidate(), grant)
    turn, execution = turn_and_execution(grant)
    if part == "actual_turn":
        turn["advocate_id"] = "another-advocate"
    elif part == "execution":
        execution["owner"] = {**OWNER, "matter_id": "another-matter"}
    else:
        execution["expected_version"] = 2
    with pytest.raises(SchemaViolation, match="actual turn owner|execution snapshot"):
        validate_record_mutation(proposal, turn=turn, execution=execution)


@pytest.mark.parametrize("part", ["current_words", "prior_words", "target", "source_catalogue"])
def test_replay_rejects_changed_original_dependencies(part):
    grant = ledger()
    proposal = saved(candidate(), grant)
    turn, execution = turn_and_execution(grant)
    kwargs = {"prior_words": WORDS, "source_catalogue": SOURCES,
              "target_catalogue": TARGETS}
    if part == "current_words":
        turn["message"] = "An unrelated request."
    elif part == "prior_words":
        kwargs["prior_words"] = {("first", "advocate"): "A different earlier account."}
    elif part == "target":
        kwargs["target_catalogue"] = deepcopy(TARGETS)
        kwargs["target_catalogue"]["date"]["statement"] = "A later superseding account."
    else:
        kwargs["source_catalogue"] = {**SOURCES, "unowned": SOURCES["L1"]}
    with pytest.raises(SchemaViolation, match="original|actual prior record"):
        validate_record_mutation(proposal, turn=turn, execution=execution, **kwargs)


def test_new_account_does_not_need_a_revision_binding_but_retains_owner_checks():
    grant = ledger()
    proposal = candidate().recorded("second", 0)
    proposal.update(relation="new", prior_references=[], related_material_ids=[])
    turn, execution = turn_and_execution(grant)
    assert validate_record_mutation(proposal, turn=turn, execution=execution,
                                    prior_words=WORDS) == "new_account"
    assert bind_record_mutation(proposal, grant) is None


def test_typed_catalogue_wrapper_and_actual_projection_row_are_equivalent():
    wrapped = {identity: {"id": identity, "type": "material", "record": row}
               for identity, row in TARGETS.items()}
    grant = build_mutation_authorities(
        owner=OWNER, expected_version=1, target_catalogue=wrapped, source_catalogue=SOURCES,
        proposals=[{"request_index": 0, "authority_kind": "account_contribution",
                    "authority_source_ids": ["L1"], "target_scope": "exact",
                    "target_ids": ["date"], "permitted_relations": ["corrects"]}],
        request_indices=[0])
    proposal = saved(candidate(), grant)
    turn, execution = turn_and_execution(grant)
    assert validate_record_mutation(proposal, turn=turn, execution=execution,
                                    target_catalogue=TARGETS) == "bound"


def test_proposal_cannot_reuse_another_turns_source_identity():
    grant = ledger()
    proposal = candidate().recorded("first", 0)
    with pytest.raises(SchemaViolation, match="different source turn"):
        bind_record_mutation(proposal, grant, supporting_source_ids=["L1"])


def test_unknown_contract_or_unversioned_evidence_is_an_integrity_failure():
    grant = ledger()
    proposal = saved(candidate(), grant)
    turn, execution = turn_and_execution(grant)
    execution["mutation_authority_contract"] = "invented"
    with pytest.raises(SchemaViolation, match="unknown authority contract"):
        validate_record_mutation(proposal, turn=turn, execution=execution)
    execution.pop("mutation_authority_contract")
    with pytest.raises(SchemaViolation, match="unexpected authority evidence"):
        validate_record_mutation(proposal, turn=turn, execution=execution)


def test_fresh_review_scope_cannot_lose_its_ledger_and_fall_back_to_legacy():
    review = {"owner": OWNER, "mutation_authority_contract": AUTHORITY_CONTRACT}
    with pytest.raises(SchemaViolation, match="no authority ledger"):
        scoped_record_decisions({"D1": decision("L1")}, {"D1": candidate()}, review)
    review["mutation_authority_contract"] = "unknown-contract"
    with pytest.raises(SchemaViolation, match="unknown authority contract"):
        scoped_record_decisions({"D1": decision("L1")}, {"D1": candidate()}, review)
