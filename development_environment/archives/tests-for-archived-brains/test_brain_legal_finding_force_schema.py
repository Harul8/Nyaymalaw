"""Offered finding shapes only; fabricated passages establish no legal accuracy."""
import json
from copy import deepcopy

import pytest

from nm.brain import legal_requirements as owner
from nm.brain.conversation import Message
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ModelResult,
    SchemaViolation,
    Tier,
    Usage,
    on_the_wire,
    require_schema,
)

SUBJECT_IDS = ("register-enquiry", "sample-provenance")
SOURCE_IDS = ("register-passage", "sample-passage")
MATERIAL_IDS = ("reported-register", "reported-sample")
FIELDS = {"kind", "label", "need", "why", "force", "source_ids", "material_ids"}
VALID_PAIRS = [("gathering", "required"), ("gathering", "strengthening"),
               *[(kind, "none") for kind in owner.RESEARCH_KINDS if kind != "gathering"]]
INVALID_PAIRS = [("gathering", "none"), *[
    (kind, force) for kind in owner.RESEARCH_KINDS if kind != "gathering"
    for force in ("required", "strengthening")]]
CONVERSATION = (Message(
    "original-account", "advocate",
    "The laboratory register may have been revised. The sample's origin remains uncertain."),)


def finding(kind="gathering", force="strengthening", *, index=0):
    return {
        "kind": kind, "label": "Provenance enquiry with the reported uncertainty preserved",
        "need": "Consider obtaining the attributed register and its certification history.",
        "why": "The supplied test passage addresses a limited enquiry into provenance.",
        "force": force, "source_ids": [SOURCE_IDS[index]], "material_ids": [MATERIAL_IDS[index]],
    }


def reading(row, *, index=0):
    return {"subject_id": SUBJECT_IDS[index], "findings": [row]}


def schema():
    return owner._findings_schema(SUBJECT_IDS, SOURCE_IDS, MATERIAL_IDS)


def context():
    subjects = tuple({
        "id": identity, "kind": "request", "owner_id": f"request-{index}", "scope": "current",
        "purpose": "requested_work",
        "question": "Which enquiries address this reported provenance?",
        "record_ids": [MATERIAL_IDS[index]],
    } for index, identity in enumerate(SUBJECT_IDS))
    material = {identity: [{"id": MATERIAL_IDS[index], "source_turn_id": "original-account",
                           "statement": "The reported provenance remains uncertain."}]
                for index, identity in enumerate(SUBJECT_IDS)}
    searches = {identity: {"state": "ok", "candidates": [{
        "id": SOURCE_IDS[index], "kind": "provision", "title": "Fabricated provenance passage",
        "locator": f"test section {index + 1}",
        "text": "Where provenance is disputed, a reviewer may seek the certified register.",
    }]} for index, identity in enumerate(SUBJECT_IDS)}
    return subjects, material, searches


class RawReader:
    """Retain raw provider objects; strict mode enforces the offered whole shape."""
    def __init__(self, outputs, *, strict=True):
        self.outputs = iter(deepcopy(outputs))
        self.strict = strict
        self.calls = []
        self.provider_rejections = []

    def context_budget(self, tier):
        assert tier is Tier.ROUTINE
        return 100_000

    def structured(self, prompt, offered, tier, *, max_tokens):
        assert tier is Tier.ROUTINE and prompt.operation == "read_legal_requirements"
        data = next(self.outputs)
        self.calls.append({"payload": json.loads(prompt.user), "schema": deepcopy(offered),
                           "output": deepcopy(data)})
        if self.strict:
            try:
                require_schema(data, offered)
            except SchemaViolation as exc:
                self.provider_rejections.append(str(exc))
                raise
        return ModelResult(text=None, data=data, tier=tier, provider="offline-raw",
                           model="fabricated-legal-reader", usage=Usage(0, 0, 0), latency_ms=0,
                           completion=Completion.COMPLETE)


def read(model, *, first_only=False):
    subjects, material, searches = context()
    if first_only:
        subjects = subjects[:1]
        material = {SUBJECT_IDS[0]: material[SUBJECT_IDS[0]]}
        searches = {SUBJECT_IDS[0]: searches[SUBJECT_IDS[0]]}
    return owner.read_findings(model, subjects=subjects, material_by_subject=material,
                               search_results=searches, conversation=CONVERSATION)


def test_finding_items_offer_two_closed_force_specific_alternatives():
    item = schema()["properties"]["readings"]["items"]["properties"]["findings"]["items"]
    assert set(item) == {"anyOf"} and len(item["anyOf"]) == 2
    gathering, other = item["anyOf"]
    for alternative in (gathering, other):
        assert alternative["type"] == "object" and alternative["additionalProperties"] is False
        assert set(alternative["required"]) == set(alternative["properties"]) == FIELDS
        assert len(alternative["required"]) == len(FIELDS)
    assert gathering["properties"]["kind"]["enum"] == ["gathering"]
    assert gathering["properties"]["force"]["enum"] == ["required", "strengthening"]
    assert other["properties"]["kind"]["enum"] == [
        kind for kind in owner.RESEARCH_KINDS if kind != "gathering"]
    assert other["properties"]["force"]["enum"] == ["none"]
    common = FIELDS - {"kind", "force"}
    assert {key: gathering["properties"][key] for key in common} == {
        key: other["properties"][key] for key in common}
    assert gathering["properties"]["source_ids"] == {
        "type": "array", "minItems": 1, "items": {"type": "string", "enum": list(SOURCE_IDS)}}
    assert gathering["properties"]["material_ids"] == {
        "type": "array", "items": {"type": "string", "enum": list(MATERIAL_IDS)}}


@pytest.mark.parametrize("kind,force", VALID_PAIRS)
def test_valid_force_neighbours_preserve_fields_sources_and_canonical_admission(kind, force):
    row = finding(kind, force)
    before = deepcopy(row)
    require_schema({"readings": [reading(row)]}, schema())
    _, _, searches = context()
    hit = searches[SUBJECT_IDS[0]]["candidates"][0]
    admitted = owner._finding(row, SUBJECT_IDS[0], {SUBJECT_IDS[0]: {SOURCE_IDS[0]: hit}},
                              {SUBJECT_IDS[0]: {MATERIAL_IDS[0]}})
    assert {key: admitted[key] for key in FIELDS} == before
    assert admitted["sources"] == [hit] and admitted["record_status"] == "mentioned"
    assert row == before


@pytest.mark.parametrize("kind,force", INVALID_PAIRS)
def test_cross_kind_force_is_rejected_by_the_offered_shape(kind, force):
    row = finding(kind, force)
    before = deepcopy(row)
    with pytest.raises(SchemaViolation):
        require_schema({"readings": [reading(row)]}, schema())
    assert row == before


def test_canonical_force_admission_still_rejects_every_cross_kind_pair():
    for kind, force in INVALID_PAIRS:
        with pytest.raises(SchemaViolation, match="Gathering force is required or strengthening"):
            owner._finding(finding(kind, force), SUBJECT_IDS[0], {}, {})


@pytest.mark.parametrize("kind,force", [("gathering", "required"), ("adverse", "none")])
def test_both_alternatives_retain_owned_references_required_fields_and_closed_objects(kind, force):
    original = finding(kind, force)
    defects = []
    for field in ("label", "need", "why", "source_ids", "material_ids"):
        missing = deepcopy(original)
        del missing[field]
        defects.append(missing)
    defects.extend([
        {**original, "extra_assertion": "This finding is checked."},
        {**original, "source_ids": []},
        {**original, "source_ids": ["unowned-source"]},
        {**original, "material_ids": ["unowned-record"]},
        {**original, "label": ""},
    ])
    for defective in defects:
        with pytest.raises(SchemaViolation):
            require_schema({"readings": [reading(defective)]}, schema())
    require_schema({"readings": [reading({**original, "material_ids": []})]}, schema())


def test_valid_empty_reading_remains_explicit_and_needs_only_one_reader_call():
    output = {"readings": [{"subject_id": SUBJECT_IDS[0], "findings": []}]}
    require_schema(output, schema())
    model = RawReader([output])
    result = read(model, first_only=True)
    assert result.rows == {SUBJECT_IDS[0]: []} and len(model.calls) == 1
    assert result.coverage[SUBJECT_IDS[0]]["checked_items"] == 1
    assert result.coverage[SUBJECT_IDS[0]]["unread_items"] == 0


def test_provider_wire_preserves_nested_alternatives_and_does_not_mutate_the_owner_schema():
    original = schema()
    before = deepcopy(original)
    offered = on_the_wire(original)
    branches = offered["properties"]["readings"]["items"]["properties"]["findings"][
        "items"]["anyOf"]
    assert len(branches) == 2
    for branch in branches:
        assert branch["additionalProperties"] is False
        assert set(branch["required"]) == set(branch["properties"]) == FIELDS
    assert original == before
    branches[0]["properties"]["source_ids"]["items"]["enum"].append("foreign")
    assert original == before and schema() == before


def test_bad_force_fails_offered_provider_shape_before_bounded_reader_correction():
    bad, good = finding(force="none"), finding(force="strengthening")
    model = RawReader([{"readings": [reading(bad)]}, {"readings": [reading(good)]}])
    result = read(model, first_only=True)
    assert len(model.provider_rejections) == 1 and len(model.calls) == 2
    assert result.rows[SUBJECT_IDS[0]][0]["force"] == "strengthening"
    correction = model.calls[1]["payload"]
    assert set(correction["validation_issues"]) == {SUBJECT_IDS[0]}
    assert [row["subject"]["id"] for row in correction["subjects"]] == [SUBJECT_IDS[0]]


def test_existing_per_subject_correction_preserves_admitted_peer_without_partial_finding_salvage():
    bad, fixed = finding(force="none"), finding(force="required")
    peer = finding("condition", "none", index=1)
    # The explicit permissive adapter lets the owner check each complete subject.
    # This asserts existing unit recovery, not strict whole-object quarantine.
    model = RawReader([{"readings": [reading(bad), reading(peer, index=1)]},
                       {"readings": [reading(fixed)]}], strict=False)
    result = read(model)
    assert set(result.rows) == set(SUBJECT_IDS) and len(model.calls) == 2
    assert result.rows[SUBJECT_IDS[1]][0]["source_ids"] == [SOURCE_IDS[1]]
    assert result.rows[SUBJECT_IDS[0]][0]["force"] == "required"
    correction = model.calls[1]["payload"]
    assert [row["subject"]["id"] for row in correction["subjects"]] == [SUBJECT_IDS[0]]
    assert set(correction["rejected_units"]) == {SUBJECT_IDS[0]}
    assert all(result.coverage[key]["checked_items"] == 1 for key in SUBJECT_IDS)


def test_structurally_valid_required_force_remains_an_unverified_legal_proposal():
    row = finding(force="required")
    model = RawReader([{"readings": [reading(row)]}])
    result = read(model, first_only=True)
    proposed = result.rows[SUBJECT_IDS[0]][0]
    assert proposed["force"] == "required" and len(model.calls) == 1
    assert "use_verification" not in proposed
    assert owner.finding_verification_valid(proposed) is False


def test_batch_reference_vocabulary_cannot_bypass_each_subjects_canonical_ownership():
    row = finding()
    row["source_ids"] = [SOURCE_IDS[1]]
    require_schema({"readings": [reading(row)]}, schema())
    _, _, searches = context()
    hits = {key: {hit["id"]: hit for hit in search["candidates"]}
            for key, search in searches.items()}
    with pytest.raises(SchemaViolation, match="invalid source_ids"):
        owner._finding(row, SUBJECT_IDS[0], hits, {SUBJECT_IDS[0]: {MATERIAL_IDS[0]}})
    row["source_ids"] = [SOURCE_IDS[0], SOURCE_IDS[0]]
    with pytest.raises(SchemaViolation, match="duplicate source_ids"):
        owner._finding(row, SUBJECT_IDS[0], hits, {SUBJECT_IDS[0]: {MATERIAL_IDS[0]}})
