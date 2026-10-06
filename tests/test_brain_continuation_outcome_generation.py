"""Fresh outcome choices match each request and its selected status.

These offline checks exercise the native generation contract and its strict
transport, not semantic review, actual execution or saved/browser delivery.
Canonical outcome validation and historical reconstruction remain separate.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from nm.brain import continuation as writer
from nm.brain.execution_contracts import RECORD_OUTCOME_SCHEMA
from nm.shared.model_port import SchemaViolation, on_the_wire, require_schema

EFFECTS = ("owned-effect-1", "owned-effect-2")
CURRENT = ("owned-material-1", "owned-material-2")
SPANS = {"L1": {"role": "advocate", "text": "I handed over the original file."}}
RECORDS = {identity: {"type": "material"} for identity in CURRENT}


def generation_schema(*, indexes=(0,), required=frozenset(), modes=None, progress=None):
    return writer._schema(
        indexes, SPANS, RECORDS, {}, progress,
        {index: "request" for index in indexes},
        effect_ids=EFFECTS, current_record_ids=CURRENT,
        response_modes=modes, record_outcome_requests=required,
    )


def proposed(status="none", *, index=0, effects=(), current=()):
    block_id = f"account-{index}"
    return {
        "request_index": index,
        "blocks": [{
            "id": block_id, "kind": "account", "uncertainty": "reported",
            "evidence_expression": {
                "operator": "source_account", "source_ids": ["L1"],
                "record_ids": [CURRENT[0]], "focus": "none",
            },
        }],
        "questions": [], "next_work": [], "progress_updates": [],
        "sufficiency": {"status": "partial", "block_id": block_id},
        "work_selector": "$new_task",
        "record_outcome": {
            "status": status, "block_id": block_id,
            "effect_ids": list(effects), "current_record_ids": list(current),
            "reason": "The selected evidence addresses this request.",
        },
    }


def assert_admitted(data, schema):
    original = deepcopy(data)
    require_schema(data, schema)
    assert data == original


VALID_SHAPES = (
    ("none", (), ()),
    ("performed", EFFECTS[:1], ()),
    ("already_current", (), CURRENT[:1]),
    ("review_no_change", (), ()),
    ("review_no_change", (), CURRENT[:1]),
    ("unresolved", (), ()),
    ("unresolved", EFFECTS[:1], CURRENT[:1]),
)


@pytest.mark.parametrize("status,effects,current", VALID_SHAPES)
def test_generation_admits_applicable_status_shape_without_rewriting(status, effects, current):
    assert_admitted({"units": [proposed(status, effects=effects, current=current)]},
                    generation_schema())


@pytest.mark.parametrize("status,effects,current", (
    ("none", EFFECTS[:1], ()),
    ("none", (), CURRENT[:1]),
    ("none", EFFECTS[:1], CURRENT[:1]),
    ("performed", (), ()),
    ("performed", EFFECTS[:1], CURRENT[:1]),
    ("already_current", (), ()),
    ("already_current", EFFECTS[:1], CURRENT[:1]),
    ("review_no_change", EFFECTS[:1], ()),
    ("review_no_change", EFFECTS[:1], CURRENT[:1]),
))
def test_generation_excludes_contradictory_status_metadata(status, effects, current):
    data = {"units": [proposed(status, effects=effects, current=current)]}
    with pytest.raises(SchemaViolation):
        require_schema(data, generation_schema())


@pytest.mark.parametrize("required,modes", (
    (frozenset({0}), {0: "substantive", 1: "substantive"}),
    (frozenset(), {0: "record_acknowledgement", 1: "substantive"}),
))
def test_mixed_requests_bind_none_to_its_own_requirement(required, modes):
    schema = generation_schema(indexes=(0, 1), required=required, modes=modes)
    recorded = proposed("performed", index=0, effects=EFFECTS)
    recap = proposed(index=1)
    assert_admitted({"units": [recorded, recap]}, schema)

    missing_record_result = {"units": [proposed(index=0), recap]}
    with pytest.raises(SchemaViolation):
        require_schema(missing_record_result, schema)

    recap_claims_state = {"units": [recorded, proposed(index=1, current=CURRENT)]}
    with pytest.raises(SchemaViolation):
        require_schema(recap_claims_state, schema)


def test_each_native_unit_branch_binds_a_single_request_index():
    schema = generation_schema(indexes=(0, 1), required=frozenset({0}))
    branches = schema["properties"]["units"]["items"]["anyOf"]
    observed = []
    for branch in branches:
        index, = branch["properties"]["request_index"]["enum"]
        observed.append(index)
        assert branch["additionalProperties"] is False
        assert set(branch["required"]) == set(branch["properties"])
    assert sorted(observed) == [0, 1]


def test_none_retains_harmless_display_owner_reason_and_substantive_selectors():
    recap = proposed()
    assert recap["record_outcome"]["block_id"] == recap["blocks"][0]["id"]
    assert recap["record_outcome"]["reason"]
    assert recap["blocks"][0]["evidence_expression"]["record_ids"] == [CURRENT[0]]
    assert_admitted({"units": [recap]}, generation_schema())


@pytest.mark.parametrize("status,effects,current", (
    ("performed", EFFECTS[:1], ()),
    ("already_current", (), CURRENT[:1]),
    ("review_no_change", (), CURRENT[:1]),
    ("unresolved", EFFECTS[:1], CURRENT[:1]),
))
def test_optional_current_requirement_does_not_erase_inherited_review_choices(
    status, effects, current,
):
    progress = {"state": "ok", "rows": [{
        "id": "saved-review", "kind": "task", "status": "pending",
        "text": "Review the earlier account against the original conversation.",
        "record_requirement": {
            "kind": "review", "target_ids": list(CURRENT), "operation": "none",
            "success_condition": "The earlier account has complete checked coverage.",
        },
    }]}
    row = proposed(status, effects=effects, current=current)
    row["work_selector"] = "saved-review"
    row["progress_updates"] = [{
        "target_id": "$work", "status": "pending" if status == "unresolved" else "complete",
        "block_id": "account-0",
        "reason": "Checked narrower results leave the inherited task pending."
                  if status == "unresolved" else "The checked inherited task scope is addressed.",
        "span_ids": ["L1"],
    }]
    # This is generation-only admission; actual effects and complete review
    # coverage still require the existing execution and independent checks.
    assert_admitted({"units": [row]}, generation_schema(progress=progress))


@pytest.mark.parametrize("status,field", (
    ("performed", "effect_ids"),
    ("already_current", "current_record_ids"),
    ("review_no_change", "current_record_ids"),
    ("unresolved", "effect_ids"),
    ("unresolved", "current_record_ids"),
))
def test_status_shapes_preserve_owned_selector_constraints(status, field):
    row = proposed(
        status, effects=EFFECTS[:1] if status in ("performed", "unresolved") else (),
        current=CURRENT[:1] if status != "performed" else (),
    )
    row["record_outcome"][field] = ["foreign-owner-id"]
    with pytest.raises(SchemaViolation):
        require_schema({"units": [row]}, generation_schema())


def test_nested_generation_shapes_use_strict_wire_and_preserve_canonical_contracts():
    snapshots = deepcopy((writer._MODEL_UNIT, writer._UNIT, RECORD_OUTCOME_SCHEMA))
    schema = generation_schema(indexes=(0, 1), required=frozenset({0}))
    wire = on_the_wire(schema)
    recorded = proposed("performed", index=0, effects=EFFECTS)
    recap = proposed(index=1)
    assert_admitted({"units": [recorded, recap]}, wire)
    for status, effects, current in VALID_SHAPES:
        row = proposed(status, index=1, effects=effects, current=current)
        assert_admitted({"units": [recorded, row]}, wire)

    wrong = deepcopy(recorded)
    wrong["record_outcome"]["effect_ids"] = []
    with pytest.raises(SchemaViolation):
        require_schema({"units": [wrong, recap]}, wire)

    assert (writer._MODEL_UNIT, writer._UNIT, RECORD_OUTCOME_SCHEMA) == snapshots


def test_generation_does_not_change_canonical_or_historical_outcome_grammar():
    snapshots = deepcopy((writer._MODEL_UNIT, writer._UNIT, RECORD_OUTCOME_SCHEMA))
    generation_schema(indexes=(0, 1), required=frozenset({0}))
    assert (writer._MODEL_UNIT, writer._UNIT, RECORD_OUTCOME_SCHEMA) == snapshots
    assert RECORD_OUTCOME_SCHEMA["properties"]["status"]["enum"] == [
        "none", "performed", "already_current", "review_no_change", "unresolved",
    ]
    # The historical/canonical grammar stays broad; its existing owner checks
    # retain responsibility for rejecting consequential metadata combinations.
    canonical = proposed("none", current=CURRENT)["record_outcome"]
    assert_admitted(canonical, RECORD_OUTCOME_SCHEMA)


def test_empty_result_catalogues_keep_truthful_unresolved_without_impossible_shapes():
    schema = writer._schema((0,), SPANS, {}, {}, record_outcome_requests=frozenset({0}))
    value = proposed("unresolved")
    value["blocks"][0]["evidence_expression"]["record_ids"] = []
    assert_admitted({"units": [value]}, on_the_wire(schema))
    for status in ("none", "performed", "already_current"):
        wrong = deepcopy(value)
        wrong["record_outcome"]["status"] = status
        with pytest.raises(SchemaViolation):
            require_schema({"units": [wrong]}, schema)


def test_no_pending_request_offers_only_empty_units_in_strict_transport():
    schema = on_the_wire(writer._schema((), SPANS, RECORDS, {}))
    assert_admitted({"units": []}, schema)
    with pytest.raises(SchemaViolation):
        require_schema({"units": [proposed()]}, schema)
