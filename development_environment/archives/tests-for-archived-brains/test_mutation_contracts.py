"""Generic mechanical scope tests; no live model or shipped flow is claimed."""
from copy import deepcopy

import pytest

from nm.brain import mutation_contracts as contracts
from nm.shared.model_port import SchemaViolation

OWNER = {"matter_id": "matter-1", "advocate_id": "advocate-1", "turn_id": "turn-2",
         "offer_digest": "offered-exact-message"}
TARGETS = {
    "record-a": {"id": "record-a", "statement": "Original account A.",
                 "source_turn_id": "turn-1", "quoted": "Original account A."},
    "record-b": {"id": "record-b", "statement": "Original account B.",
                 "source_turn_id": "turn-1", "quoted": "Original account B."},
}
SOURCES = {
    "latest-review": {"turn_id": "turn-2", "role": "advocate",
                      "quoted": "Please repair the first account interpretation.",
                      "content_role": "work_instruction"},
    "latest-contribution": {"turn_id": "turn-2", "role": "advocate",
                            "quoted": "The second account now has a different value.",
                            "content_role": "reported_matter_account"},
    "prior-a": {"turn_id": "turn-1", "role": "advocate", "quoted": "Original account A.",
                "content_role": "reported_matter_account"},
    "prior-b": {"turn_id": "turn-1", "role": "advocate", "quoted": "Original account B.",
                "content_role": "reported_matter_account"},
}


def proposal(*, index=0, kind="interpretation_review", sources=("latest-review",),
             scope="exact", targets=("record-a",), relations=("corrects",)):
    return {"request_index": index, "authority_kind": kind,
            "authority_source_ids": list(sources), "target_scope": scope,
            "target_ids": list(targets), "permitted_relations": list(relations)}


def ledger(*proposals, targets=TARGETS, sources=SOURCES):
    return contracts.build_mutation_authorities(
        owner=OWNER, expected_version=7, target_catalogue=targets,
        source_catalogue=sources, proposals=list(proposals), request_indices=(0, 1, 2))


def bind(scope, *, authority=None, relation="corrects", targets=("record-a",),
         support=("prior-a",), context=("prior-a",), source="latest-review",
         owner=OWNER, version=7):
    return contracts.authorize_mutation(
        ledger=scope, owner=owner, snapshot_version=version,
        authority_ids=authority or [scope["authorities"][0]["id"]],
        relation=relation, target_ids=list(targets), supporting_source_ids=list(support),
        current_source_reference=current_reference(source),
        attached_context_source_ids=list(context))


def current_reference(identity):
    return {key: SOURCES[identity][key] for key in ("turn_id", "role", "quoted")}


def select(scope, *, source="latest-review", relation="corrects", targets=("record-a",)):
    return contracts.candidate_authority_ids(
        ledger=scope, owner=OWNER, snapshot_version=7, relation=relation,
        target_ids=list(targets), current_source_reference=current_reference(source))


def test_wrong_owned_target_cannot_be_admitted_even_when_reviewer_accepts():
    scope = ledger(proposal())
    fabricated_review = {"verdict": "accept", "identity_relation": "same_underlying_account"}
    assert fabricated_review["verdict"] == "accept"
    with pytest.raises(SchemaViolation, match="exceeds"):
        bind(scope, targets=("record-b",), support=("prior-b",), context=("prior-b",))
    with pytest.raises(SchemaViolation, match="exceeds"):
        select(scope, targets=("record-b",))
    assert bind(scope)["target_ids"] == ["record-a"]


def test_implicit_account_contribution_can_authorize_its_own_correction():
    scope = ledger(proposal(kind="account_contribution", sources=("latest-contribution",),
                            targets=("record-b",)))
    chosen = select(scope, source="latest-contribution", targets=("record-b",))
    certificate = bind(scope, authority=chosen, targets=("record-b",),
                       source="latest-contribution",
                       support=("latest-contribution",), context=("prior-b",))
    assert certificate["target_ids"] == ["record-b"]
    assert certificate["supporting_source_ids"] == ["latest-contribution"]


def test_review_can_repair_from_earlier_content_without_new_fact():
    scope = ledger(proposal())
    assert SOURCES["latest-review"]["content_role"] == "work_instruction"
    certificate = bind(scope, authority=select(scope), support=("prior-a",))
    assert certificate["supporting_source_ids"] == ["prior-a"]


def test_target_context_cannot_fill_an_empty_support_selection():
    scope = ledger(proposal())
    with pytest.raises(SchemaViolation, match="supporting_source_ids"):
        bind(scope, support=(), context=("prior-a", "prior-b"))


def test_mixed_selected_review_and_independent_contribution_get_separate_scopes():
    scope = ledger(
        proposal(),
        proposal(index=1, kind="account_contribution", sources=("latest-contribution",),
                 targets=("record-b",)))
    first = select(scope)
    second = select(scope, source="latest-contribution", targets=("record-b",))
    assert first != second
    assert bind(scope, authority=first)["request_indices"] == [0]
    assert bind(scope, authority=second, targets=("record-b",),
                source="latest-contribution",
                support=("latest-contribution",), context=("prior-b",))["request_indices"] == [1]


def test_multiple_authorities_cannot_launder_a_relation_for_another_target():
    scope = ledger(proposal(), proposal(index=1, targets=("record-b",), relations=("withdraws",)))
    with pytest.raises(SchemaViolation, match="exceeds"):
        bind(scope, authority=[row["id"] for row in scope["authorities"]],
             targets=("record-a", "record-b"))


def test_duplicate_restoration_may_have_one_explicit_multi_target_scope():
    scope = ledger(proposal(targets=("record-a", "record-b")))
    chosen = select(scope, targets=("record-a", "record-b"))
    certificate = bind(scope, authority=chosen, targets=("record-a", "record-b"),
                       support=("prior-a", "prior-b"), context=("prior-a", "prior-b"))
    assert certificate["target_ids"] == ["record-a", "record-b"]


def test_whole_review_uses_only_the_original_snapshot():
    scope = ledger(proposal(scope="reviewed_whole", targets=()))
    assert scope["authorities"][0]["target_ids"] == ["record-a", "record-b"]
    assert bind(scope, targets=("record-b",), support=("prior-b",))["target_ids"] == ["record-b"]
    with pytest.raises(SchemaViolation, match="snapshot"):
        bind(scope, version=8)
    with pytest.raises(SchemaViolation, match="unowned"):
        bind(scope, targets=("post-snapshot-record",))


def test_whole_review_is_not_implicitly_granted_to_an_account_contribution():
    with pytest.raises(SchemaViolation, match="Whole-record"):
        ledger(proposal(kind="account_contribution", scope="reviewed_whole", targets=()))


def test_empty_whole_record_review_is_legitimate_without_inventing_effects():
    scope = ledger(proposal(scope="reviewed_whole", targets=()), targets={})
    assert scope["authorities"][0]["target_ids"] == []
    with pytest.raises(SchemaViolation, match="incompatible"):
        bind(scope)


def test_broad_review_does_not_mechanically_certify_semantic_identity():
    scope = ledger(proposal(scope="reviewed_whole", targets=()))
    # The target is within authority, but a Judge can still misunderstand which
    # proposition this source supports. This test documents that residual.
    certificate = bind(scope, targets=("record-b",), support=("prior-a",))
    assert certificate["target_ids"] == ["record-b"]
    assert certificate["supporting_source_ids"] == ["prior-a"]


def test_source_identity_is_not_a_semantic_authorization_guarantee():
    # A wrongly interpreted scope can still bind mechanically. Preventing that
    # error needs independent interpretation of original request/target meaning.
    mistaken_scope = ledger(proposal(targets=("record-b",)))
    assert bind(mistaken_scope, targets=("record-b",))["target_ids"] == ["record-b"]


def test_new_items_need_creation_authority_without_an_existing_target():
    scope = ledger(proposal(kind="account_contribution", sources=("latest-contribution",),
                            targets=(), relations=("new",)))
    chosen = select(scope, source="latest-contribution", relation="new", targets=())
    assert bind(scope, authority=chosen, relation="new", targets=(),
                source="latest-contribution",
                support=("latest-contribution",), context=())["target_ids"] == []
    with pytest.raises(SchemaViolation, match="incompatible"):
        bind(scope, relation="new", targets=("record-a",))


def test_appended_prior_target_context_cannot_select_current_authority():
    scope = ledger(proposal())
    with pytest.raises(SchemaViolation, match="exceeds"):
        select(scope, source="latest-contribution")
    with pytest.raises(SchemaViolation, match="current advocate"):
        contracts.candidate_authority_ids(
            ledger=scope, owner=OWNER, snapshot_version=7, relation="corrects",
            target_ids=["record-a"], current_source_reference=current_reference("prior-a"))


def test_multiple_independent_grants_cover_all_targets_without_first_match():
    scope = ledger(proposal(index=0), proposal(index=1, targets=("record-b",)))
    selected = select(scope, targets=("record-a", "record-b"))
    assert len(selected) == 2
    certificate = bind(scope, authority=selected, targets=("record-a", "record-b"),
                       support=("prior-a", "prior-b"), context=("prior-a", "prior-b"))
    assert certificate["request_indices"] == [0, 1]


def test_overlapping_permissions_are_not_falsely_rejected_as_ambiguous():
    scope = ledger(proposal(index=0), proposal(index=1))
    assert len(select(scope)) == 2


def test_ambiguous_owned_source_identity_requires_resolution_not_first_match():
    sources = {**SOURCES, "repeated-current-passage": deepcopy(SOURCES["latest-review"])}
    scope = ledger(proposal(), sources=sources)
    with pytest.raises(SchemaViolation, match="ambiguous"):
        select(scope)


def test_owned_turn_scope_cannot_be_reused_for_another_owner():
    scope = ledger(proposal())
    changed_owner = {**OWNER, "turn_id": "turn-3"}
    with pytest.raises(SchemaViolation, match="different turn"):
        bind(scope, owner=changed_owner)


def test_harmless_order_and_duplicate_reference_changes_keep_stable_code_ids():
    first = ledger(proposal(targets=("record-a", "record-b"),
                            sources=("latest-review", "prior-a"),
                            relations=("corrects", "withdraws")))
    second = ledger(proposal(targets=("record-b", "record-a", "record-a"),
                             sources=("prior-a", "latest-review", "latest-review"),
                             relations=("withdraws", "corrects", "corrects")))
    assert first == second
    assert first["authorities"][0]["id"].startswith("mau_")


def test_catalogue_or_scope_drift_cannot_widen_prepared_authority():
    scope = ledger(proposal())
    for tamper in ("scope", "source", "target"):
        changed = deepcopy(scope)
        if tamper == "scope":
            changed["authorities"][0]["target_ids"].append("record-b")
        elif tamper == "source":
            changed["source_catalogue"]["latest-review"]["quoted"] = "Different instruction."
        else:
            changed["target_catalogue"]["record-a"]["statement"] = "Different account."
        with pytest.raises(SchemaViolation, match="changed"):
            bind(changed)


def test_saved_binding_replays_exact_historical_scope_but_cannot_change_targets():
    scope = ledger(proposal())
    certificate = bind(scope)
    replay = contracts.validate_saved_mutation_authority(
        certificate=certificate, ledger=scope, owner=OWNER, snapshot_version=7,
        relation="corrects", target_ids=["record-a"], supporting_source_ids=["prior-a"],
        current_source_reference=current_reference("latest-review"),
        attached_context_source_ids=["prior-a"])
    assert replay == certificate
    with pytest.raises(SchemaViolation, match="exceeds"):
        contracts.validate_saved_mutation_authority(
            certificate=certificate, ledger=scope, owner=OWNER, snapshot_version=7,
            relation="corrects", target_ids=["record-b"], supporting_source_ids=["prior-b"],
            current_source_reference=current_reference("latest-review"),
            attached_context_source_ids=["prior-b"])


def test_legacy_mode_does_not_certify_or_downgrade_missing_fresh_binding():
    assert contracts.mutation_authority_mode(
        saved_contract=None, binding_present=False) == "legacy_untracked"
    with pytest.raises(SchemaViolation, match="requires"):
        contracts.mutation_authority_mode(
            saved_contract=contracts.AUTHORITY_CONTRACT, binding_present=False)
    with pytest.raises(SchemaViolation, match="unexpected"):
        contracts.mutation_authority_mode(saved_contract=None, binding_present=True)


@pytest.mark.parametrize("fault", ("target", "source", "request", "operation", "nm-source"))
def test_unknown_scope_inputs_are_rejected_without_inventing_permissions(fault):
    item = proposal()
    sources = deepcopy(SOURCES)
    if fault == "target":
        item["target_ids"] = ["unknown"]
    elif fault == "source":
        item["authority_source_ids"] = ["unknown"]
    elif fault == "request":
        item["request_index"] = 90
    elif fault == "operation":
        item["permitted_relations"] = ["anything"]
    else:
        sources["latest-review"]["role"] = "nm"
    with pytest.raises(SchemaViolation):
        ledger(item, sources=sources)
