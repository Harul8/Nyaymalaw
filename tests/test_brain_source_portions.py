"""Owned exact source portions and semantic dependency reuse without model calls."""

from copy import deepcopy

import pytest

from nm.brain import record_review as record
from nm.brain.conversation import Message
from nm.brain.material import addressed_sources
from nm.shared.model_port import SchemaViolation


def reference(words="The witness did not identify the sender.", *, turn="original"):
    return {"turn_id": turn, "role": "advocate", "quoted": words}


def selections(*ranges):
    return [{"start": start, "end": end} for start, end in ranges]


def legacy_row(source=None, *, role="reported_matter_account"):
    return {
        **(source or reference()),
        "content_role": role,
        "reason": "Original framing reports this attributed account.",
    }


def versioned_row(source=None, *, role="reported_matter_account", portions=None):
    source = source or reference()
    if portions is None:
        portions = selections((0, len(source["quoted"]))) if role in {
            "reported_matter_account", "reported_party_position", "mixed"
        } else []
    return {
        **legacy_row(source, role=role),
        "selection_contract": record.SOURCE_SELECTION_CONTRACT,
        "substantive_spans": record.owned_source_portions(source, portions),
    }


def canonical(source):
    return {(source["turn_id"], source["role"], source["quoted"])}


@pytest.mark.parametrize("words,bounds", [
    ("No.", (0, 3)),
    ("Ω", (0, 1)),
    ("  Ω\twas uncertain.\n", (2, 19)),
    ("The date was not 3 May; the witness reported 4 May.", (0, 51)),
    ("The witness's quoted words were ‘perhaps’.", (31, 40)),
])
def test_owned_portion_preserves_exact_unicode_boundaries_and_context(words, bounds):
    source = reference(words)
    before = deepcopy(source)
    selected = selections(bounds)
    selected_before = deepcopy(selected)

    result = record.owned_source_portions(source, selected)

    assert len(result) == 1
    assert set(result[0]) == {"anchor_id", "start", "end", "quoted"}
    assert result[0]["start"] == bounds[0] and result[0]["end"] == bounds[1]
    assert result[0]["quoted"] == words[slice(*bounds)]
    assert isinstance(result[0]["anchor_id"], str) and result[0]["anchor_id"]
    assert source == before and selected == selected_before


def test_owned_portion_allows_overlap_and_normalizes_identical_selections():
    source = reference("The account is uncertain and the identification remains disputed.")
    result = record.owned_source_portions(source, selections((0, 24), (15, 64), (0, 24)))

    assert len(result) == 2
    assert {(row["start"], row["end"], row["quoted"]) for row in result} == {
        (0, 24, source["quoted"][:24]),
        (15, 64, source["quoted"][15:64]),
    }
    assert len({row["anchor_id"] for row in result}) == 2


def test_empty_portion_selection_is_available_for_nonaccount_sources():
    assert record.owned_source_portions(reference("Review this passage."), []) == []


@pytest.mark.parametrize("selected", [
    None,
    {"start": 0, "end": 3},
    [None],
    [{"start": 0}],
    [{"end": 3}],
    [{"start": 0, "end": 3, "quoted": "invented"}],
    [{"start": 0, "end": 3, "anchor_id": "model-assigned"}],
    [{"start": True, "end": 3}],
    [{"start": 0, "end": False}],
    [{"start": 0.0, "end": 3}],
    [{"start": 0, "end": "3"}],
    [{"start": -1, "end": 3}],
    [{"start": 0, "end": 0}],
    [{"start": 3, "end": 2}],
    [{"start": 0, "end": 1000}],
])
def test_owned_portion_rejects_unowned_shape_and_invalid_endpoints(selected):
    with pytest.raises(SchemaViolation):
        record.owned_source_portions(reference(), selected)


@pytest.mark.parametrize("source", [
    None,
    {},
    {"turn_id": "original", "role": "advocate"},
    {"turn_id": "", "role": "advocate", "quoted": "Original words."},
    {"turn_id": "original", "role": "nm", "quoted": "Original words."},
    {"turn_id": "original", "role": "advocate", "quoted": "   "},
    {"turn_id": "original", "role": "advocate", "quoted": 123},
])
def test_owned_portion_requires_canonical_original_advocate_reference(source):
    with pytest.raises(SchemaViolation):
        record.owned_source_portions(source, selections((0, 1)))


def test_anchor_identity_uses_canonical_owner_and_complete_source_not_local_ids():
    source = reference("The receipt was uncertain.")
    chosen = selections((4, 11))
    first = record.owned_source_portions(source, chosen)
    assert first == record.owned_source_portions(deepcopy(source), deepcopy(chosen))
    assert first != record.owned_source_portions({**source, "turn_id": "another-turn"}, chosen)
    changed_context = {**source, "quoted": "The receipt was confirmed."}
    assert first[0]["quoted"] == record.owned_source_portions(changed_context, chosen)[0]["quoted"]
    assert first[0]["anchor_id"] != record.owned_source_portions(changed_context, chosen)[0][
        "anchor_id"]
    different_bounds = record.owned_source_portions(source, selections((0, 11)))
    assert first[0]["anchor_id"] != different_bounds[0]["anchor_id"]


@pytest.mark.parametrize("role", ["reported_matter_account", "reported_party_position", "mixed"])
def test_versioned_account_rows_require_owned_positive_substantive_portions(role):
    source = reference()
    row = versioned_row(source, role=role)
    assert record.source_treatment_reference_valid(row, canonical(source))
    empty = versioned_row(source, role=role, portions=[])
    assert not record.source_treatment_reference_valid(empty, canonical(source))


@pytest.mark.parametrize("role", [
    "examination_material", "work_instruction", "nm_interpretation", "uncertain"
])
def test_versioned_nonaccount_rows_need_no_substantive_portions_and_cannot_claim_them(role):
    source = reference()
    row = versioned_row(source, role=role)
    assert record.source_treatment_reference_valid(row, canonical(source))
    positive = versioned_row(source, role=role, portions=selections((0, len(source["quoted"]))))
    assert not record.source_treatment_reference_valid(positive, canonical(source))


@pytest.mark.parametrize("mutation", [
    "unknown_contract", "missing_contract", "missing_portions", "extra_field",
    "wrong_words", "wrong_anchor", "wrong_bounds", "boolean_endpoint", "extra_anchor_field",
    "foreign_owner", "blank_reason",
])
def test_versioned_row_tampering_cannot_pass_canonical_reference_admission(mutation):
    source = reference()
    row = versioned_row(source)
    if mutation == "unknown_contract":
        row["selection_contract"] = "unknown-selection-version"
    elif mutation == "missing_contract":
        del row["selection_contract"]
    elif mutation == "missing_portions":
        del row["substantive_spans"]
    elif mutation == "extra_field":
        row["approved"] = True
    elif mutation == "foreign_owner":
        row["turn_id"] = "foreign"
    elif mutation == "blank_reason":
        row["reason"] = " \n "
    else:
        span = row["substantive_spans"][0]
        if mutation == "wrong_words":
            span["quoted"] = "The witness identified the sender."
        elif mutation == "wrong_anchor":
            span["anchor_id"] = "writer-chosen"
        elif mutation == "wrong_bounds":
            span["end"] -= 1
        elif mutation == "boolean_endpoint":
            span["start"] = False
        else:
            span["approved"] = True
    assert not record.source_treatment_reference_valid(row, canonical(source))


@pytest.mark.parametrize("role", [
    "reported_matter_account", "reported_party_position", "mixed", "examination_material",
    "work_instruction", "nm_interpretation", "uncertain"
])
def test_historical_exact_five_field_source_rows_remain_readable(role):
    source = reference()
    row = legacy_row(source, role=role)
    assert record.source_treatment_reference_valid(row, canonical(source))
    row["substantive_spans"] = []
    assert not record.source_treatment_reference_valid(row, canonical(source))


def test_versioned_catalogue_remaps_owned_portions_by_canonical_reference():
    words = "The witness did not identify the sender."
    source = reference(words)
    row = versioned_row(source, portions=selections((0, len(words))))
    _, _, prior = addressed_sources((Message("original", "advocate", words),), "")
    before = deepcopy(row)
    result = record.substantive_source_treatments({"temporary-L1": row}, prior)
    assert result == {"P1S1": row}
    assert row == before
    assert record.owned_source_treatments({"P1S1": row}, {}, prior) == {"P1S1": row}


def test_conflicting_portion_selection_for_same_canonical_source_stays_unresolved():
    words = "The witness did not identify the sender."
    source = reference(words)
    first = versioned_row(source, portions=selections((0, 11)))
    second = versioned_row(source, portions=selections((12, len(words))))
    _, _, prior = addressed_sources((Message("original", "advocate", words),), "")
    assert record.substantive_source_treatments({"first": first, "second": second}, prior) == {}


def test_source_dependency_ignores_reason_and_portion_order_but_retains_semantic_evidence():
    source = reference()
    first = versioned_row(source, portions=selections((0, 11), (12, len(source["quoted"]))))
    harmless = deepcopy(first)
    harmless["reason"] = "A different concise reason for the unchanged original source purpose."
    harmless["substantive_spans"].reverse()
    assert record.source_dependency(first) == record.source_dependency(harmless)
    changed = versioned_row(source)
    assert record.source_dependency(first) != record.source_dependency(changed)
    changed_role = {**first, "content_role": "mixed"}
    assert record.source_dependency(first) != record.source_dependency(changed_role)
    assert record.source_dependency(legacy_row(source)) != record.source_dependency(first)


def review_cache_fixture():
    sources = {f"L{index}": versioned_row(reference(words, turn=f"turn-{index}"))
               for index, words in enumerate((
                   "The account remained uncertain.",
                   "The separate record was disputed.",
                   "The other contribution remained reported.",
               ), 1)}
    context = {
        "earlier_conversation": [],
        "latest_message_spans": [],
        "source_treatments": deepcopy(sources),
        "candidates": [{"candidate_id": f"D{index}", "statement": f"Proposal {index}"}
                       for index in range(1, 5)],
    }
    targets = {"D1": {"shared"}, "D2": {"shared"}, "D3": set(), "D4": {"other"}}
    decisions = {identity: {
        "candidate_id": identity, "verdict": "accept",
        "target_checks": [{"target_id": target,
                           "required_peer_ids": ["D1"] if identity == "D4" else []}
                          for target in selected],
    } for identity, selected in targets.items()}
    account_ids = {"D1": {"L1"}, "D2": {"L2"}, "D3": {"L3"}, "D4": {"L3"}}
    state = {}
    record.remember_independent_review(
        state, context=context, source_treatments=sources, decisions=decisions)
    return state, context, sources, decisions, account_ids, targets


def test_portion_dependency_change_invalidates_only_source_target_and_required_peer_dependents():
    state, context, sources, decisions, account_ids, targets = review_cache_fixture()
    before = deepcopy(decisions)
    changed = deepcopy(sources)
    source = {key: changed["L1"][key] for key in ("turn_id", "role", "quoted")}
    changed["L1"] = versioned_row(source, portions=selections((0, 11)))
    result = record.retained_independent_review(
        state, context=context, source_treatments=changed, account_ids=account_ids,
        targets=targets, recheck_source_ids=("L1",))
    assert result == {"D3": before["D3"]}
    assert decisions == before


def test_undeclared_portion_change_cannot_reuse_a_positive_independent_decision():
    state, context, sources, _, account_ids, targets = review_cache_fixture()
    source = {key: sources["L1"][key] for key in ("turn_id", "role", "quoted")}
    changed = deepcopy(sources)
    changed["L1"] = versioned_row(source, portions=selections((0, 11)))
    with pytest.raises(SchemaViolation):
        record.retained_independent_review(
            state, context=context, source_treatments=changed,
            account_ids=account_ids, targets=targets)


def test_harmless_reason_and_selection_order_preserve_independent_decisions():
    state, context, sources, decisions, account_ids, targets = review_cache_fixture()
    harmless = deepcopy(sources)
    for row in harmless.values():
        row["reason"] = "An unchanged purpose expressed with different wording."
    result = record.retained_independent_review(
        state, context=context, source_treatments=harmless,
        account_ids=account_ids, targets=targets)
    assert result == decisions


def test_mutated_cached_portion_proof_is_not_reusable():
    state, context, sources, _, account_ids, targets = review_cache_fixture()
    state["cache"].source_treatments["L1"]["substantive_spans"][0]["quoted"] = "Changed."
    with pytest.raises(SchemaViolation):
        record.retained_independent_review(
            state, context=context, source_treatments=sources,
            account_ids=account_ids, targets=targets)
