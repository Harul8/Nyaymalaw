"""Turn-linked permission admits neighbouring support without losing identity.

These are pure contract tests. The authority owner supplies the target and
operation; a fabricated accepting reviewer cannot enlarge either choice.
Historical unstamped ledgers retain their original exact-span semantics.
"""
from copy import deepcopy

import pytest

from nm.brain import mutation_contracts as contracts
from nm.shared.model_port import SchemaViolation

SAME_TURN = "same_original_advocate_turn_v1"
OWNER = {"matter_id": "matter", "advocate_id": "advocate", "turn_id": "current",
         "offer_digest": "exact-original-offer"}
VERSION = 2
TARGETS = {
    "date": {"id": "date", "statement": "The cartons arrived on 17 April.",
             "source_turn_id": "prior", "quoted": "The cartons arrived on 17 April."},
    "custody": {"id": "custody", "statement": "The tablet remains with the client.",
                "source_turn_id": "prior", "quoted": "The tablet remains with the client."},
}
SOURCES = {
    "L1": {"turn_id": "current", "role": "advocate",
           "quoted": "Correct the arrival entry.", "content_role": "work_instruction"},
    "L2": {"turn_id": "current", "role": "advocate",
           "quoted": "The cartons arrived on 19 April.",
           "content_role": "reported_matter_account"},
    "P1S1": {"turn_id": "prior", "role": "advocate",
             "quoted": "The cartons arrived on 17 April.",
             "content_role": "reported_matter_account"},
}


def ledger(*, policy=SAME_TURN, sources=SOURCES, permission="L1"):
    return contracts.build_mutation_authorities(
        owner=OWNER, expected_version=VERSION, target_catalogue=TARGETS,
        source_catalogue=sources, request_indices=[0], source_match_contract=policy,
        proposals=[{"request_index": 0, "authority_kind": "account_contribution",
                    "authority_source_ids": [permission], "target_scope": "exact",
                    "target_ids": ["date"], "permitted_relations": ["corrects"]}])


def reference(identity="L2", *, sources=SOURCES, explicit=True):
    result = {key: sources[identity][key] for key in ("turn_id", "role", "quoted")}
    if explicit:
        result["source_id"] = identity
    return result


def select(grant, *, current=None, relation="corrects", targets=("date",),
           owner=OWNER, version=VERSION):
    return contracts.candidate_authority_ids(
        ledger=grant, owner=owner, snapshot_version=version, relation=relation,
        target_ids=list(targets), current_source_reference=current or reference())


def bind(grant, *, current=None, relation="corrects", targets=("date",),
         support=("L2",), context=("P1S1",), owner=OWNER, version=VERSION):
    current = current or reference()
    authority_ids = select(grant, current=current, relation=relation, targets=targets,
                           owner=owner, version=version)
    return contracts.authorize_mutation(
        ledger=grant, owner=owner, snapshot_version=version,
        authority_ids=authority_ids, relation=relation, target_ids=list(targets),
        current_source_reference=current, supporting_source_ids=list(support),
        attached_context_source_ids=list(context))


def replay(grant, certificate):
    return contracts.validate_saved_mutation_authority(
        certificate=certificate, ledger=grant, owner=OWNER, snapshot_version=VERSION,
        relation=certificate["relation"], target_ids=certificate["target_ids"],
        current_source_reference=certificate["current_source_reference"],
        supporting_source_ids=certificate["supporting_source_ids"],
        attached_context_source_ids=certificate["attached_context_source_ids"])


def test_same_original_turn_links_instruction_permission_to_separate_fact_support():
    assert contracts.SAME_TURN_SOURCE_MATCH == SAME_TURN
    grant = ledger()
    certificate = bind(grant)
    assert grant["source_match_contract"] == SAME_TURN
    assert certificate["current_source_reference"] == reference("L2")
    assert certificate["supporting_source_ids"] == ["L2"]
    assert certificate["attached_context_source_ids"] == ["P1S1"]
    selected, = [row for row in grant["authorities"]
                 if row["id"] in certificate["authority_ids"]]
    assert selected["authority_source_ids"] == ["L1"]
    assert selected["target_ids"] == certificate["target_ids"] == ["date"]
    assert replay(grant, certificate) == certificate


def test_unstamped_legacy_scope_retains_exact_span_and_saved_proof():
    old = ledger(policy=None)
    assert "source_match_contract" not in old
    with pytest.raises(SchemaViolation):
        bind(old)
    certificate = bind(old, current=reference("L1"))
    before = deepcopy((old, certificate))
    assert replay(old, certificate) == certificate
    assert (old, certificate) == before
    explicit = contracts.build_mutation_authorities(
        owner=OWNER, expected_version=VERSION, target_catalogue=TARGETS,
        source_catalogue=SOURCES, request_indices=[0], proposals=[
            {key: value for key, value in old["authorities"][0].items() if key != "id"}])
    assert explicit == old


def test_source_match_policy_is_sealed_and_cannot_replace_a_saved_binding():
    old, fresh = ledger(policy=None), ledger()
    assert old["seal"] != fresh["seal"]
    certificate = bind(old, current=reference("L1"))
    with pytest.raises(SchemaViolation):
        replay(fresh, certificate)
    changed = deepcopy(fresh)
    changed.pop("source_match_contract")
    with pytest.raises(SchemaViolation):
        select(changed)


@pytest.mark.parametrize("policy", ["unowned_source_policy", "", False, [], {}])
def test_unknown_source_match_policy_cannot_be_admitted(policy):
    with pytest.raises(SchemaViolation):
        ledger(policy=policy)


@pytest.mark.parametrize("change", [
    {"source_id": "foreign-source"},
    {"source_id": "L1"},
    {"quoted": "The cartons arrived on 23 April."},
    {"turn_id": "prior"},
    {"role": "nm"},
])
def test_neighbour_match_still_requires_exact_owned_current_source(change):
    current = {**reference(), **change}
    with pytest.raises(SchemaViolation):
        bind(ledger(), current=current)


def test_same_words_in_a_different_turn_cannot_supply_the_current_permission():
    sources = {**SOURCES, "earlier-instruction": {**SOURCES["L1"], "turn_id": "prior"}}
    with pytest.raises(SchemaViolation):
        bind(ledger(sources=sources, permission="earlier-instruction"))


@pytest.mark.parametrize("relation,targets", [
    ("corrects", ("custody",)), ("withdraws", ("date",)),
    ("adds", ("date",)), ("corrects", ("date", "custody")),
    ("corrects", ("foreign-target",)),
])
def test_same_turn_does_not_widen_owned_target_or_operation(relation, targets):
    with pytest.raises(SchemaViolation):
        bind(ledger(), relation=relation, targets=targets)


@pytest.mark.parametrize("change", [
    {"matter_id": "other-matter"}, {"advocate_id": "other-advocate"},
    {"turn_id": "other-turn"}, {"offer_digest": "different-offer"},
])
def test_neighbour_policy_preserves_complete_owner_identity(change):
    with pytest.raises(SchemaViolation):
        bind(ledger(), owner={**OWNER, **change})


def test_neighbour_policy_preserves_original_snapshot_version():
    with pytest.raises(SchemaViolation):
        bind(ledger(), version=VERSION + 1)


def test_repeated_words_need_identity_and_keep_the_selected_original_span():
    sources = {**SOURCES, "L3": deepcopy(SOURCES["L2"])}
    grant = ledger(sources=sources)
    with pytest.raises(SchemaViolation, match="ambiguous"):
        bind(grant, current=reference("L3", sources=sources, explicit=False))
    certificate = bind(grant, current=reference("L3", sources=sources), support=("L3",))
    assert certificate["current_source_reference"]["source_id"] == "L3"
    assert certificate["supporting_source_ids"] == ["L3"]
    assert replay(grant, certificate) == certificate
    assert grant["authorities"][0]["authority_source_ids"] == ["L1"]


def candidate(*, target="date", relation="corrects", source_id="L2"):
    return {"relation": relation, "source_id": source_id,
            "source_turn_id": "current", "quoted": SOURCES["L2"]["quoted"],
            "related_material_ids": [target], "related_dispute_ids": [],
            "prior_references": [{key: SOURCES["P1S1"][key]
                                  for key in ("turn_id", "role", "quoted")} ]}


def review():
    return {"candidate_id": "candidate", "verdict": "accept", "operation_supported": True,
            "reason": "The deliberately accepting reviewer is not a scope owner.",
            "account_check": {"source_ids": ["L1", "L2"], "source_checks": [
                {"source_id": "L1", "supplies_account_content": False,
                 "supports_proposal": False, "reason": "Permission is an instruction."},
                {"source_id": "L2", "supplies_account_content": True,
                 "supports_proposal": True,
                 "reason": "The original dated account supplies support."}
            ]}}


def test_admission_keeps_permission_and_positive_support_separate():
    grant, sink = ledger(), {}
    original = {"candidate": review()}
    checked = contracts.scoped_record_decisions(
        original, {"candidate": candidate()}, {"owner": OWNER, "mutation_authorities": grant},
        binding_sink=sink)
    assert checked["candidate"]["verdict"] == "accept"
    assert sink["candidate"]["current_source_reference"]["source_id"] == "L2"
    assert sink["candidate"]["supporting_source_ids"] == ["L2"]
    assert "mutation_authority" not in original["candidate"]
    assert contracts.bind_record_mutation(candidate(), grant, binding=sink["candidate"]) == (
        sink["candidate"])


@pytest.mark.parametrize("change", [
    {"target": "custody"}, {"relation": "withdraws"}, {"source_id": "foreign-source"},
])
def test_accepting_reviewer_cannot_override_a_neighbour_scope_failure(change):
    grant = ledger()
    before, sink = {"candidate": review()}, {}
    checked = contracts.scoped_record_decisions(
        before, {"candidate": candidate(**change)},
        {"owner": OWNER, "mutation_authorities": grant}, binding_sink=sink)
    assert checked["candidate"]["verdict"] == "reject"
    assert checked["candidate"]["admission_issue"] == "mutation_scope"
    assert checked["candidate"]["model_decision"] == before["candidate"]
    assert sink == {}
