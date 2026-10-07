"""Dispute coverage choices consume owned support without exposing durable proof.

Scripted independent judgments prove generation, admission and bounded reuse.
They do not certify dispute meaning, pinned-model quality or public integration.
"""

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import dispute_verification as owner
from nm.brain import record_review as record
from nm.brain.conversation import Message
from nm.shared.model_port import (
    ContextOverflow,
    SchemaViolation,
    estimate_tokens,
    on_the_wire,
    require_schema,
)
from tests.test_brain_material_coverage_choices import ChoicesJudge, extent_coverage, proof
from tests.test_brain_source_support_verifiers import (
    SCOPE,
    coverage,
    disposition,
    proposal,
    source_catalogue,
    verdict,
)

OMITTED = object()
ACCOUNT = "The recipient denies receiving the cylinder retained by the carrier."
REQUEST = "Review the earlier contested account in its original context."
EARLIER = (
    Message("earlier-account", "advocate", ACCOUNT),
    Message("earlier-answer", "nm", "The attributed receipt positions remain disputed."),
)


def record_row(identity="saved-dispute", *, words=ACCOUNT, turn="earlier-account", state="current"):
    return {
        "id": identity, "kind": "dispute", "label": "Reported receipt dispute",
        "statement": words, "quoted": words, "source_turn_id": turn,
        "matter_scope": "current", "basis": "stated", "relation": "new", "state": state,
        "identification": "identified", "related_dispute_ids": [],
    }


def check(model, *, latest=REQUEST, earlier=EARLIER, candidates=(), records=(), history=(),
          support=OMITTED, treatments=None, state=None, scope=SCOPE):
    references, defaults = source_catalogue(
        latest, earlier=earlier, roles={"L1": "work_instruction"} if latest == REQUEST else None)
    assessed, disagreements, audit = {}, [], []
    kwargs = {"coverage_record_support": support} if support is not OMITTED else {}
    if history:
        kwargs["historical_disputes"] = history
    result = owner.verify_disputes(
        model, candidates=candidates, earlier=earlier, latest=latest, active_disputes=records,
        source_treatments=defaults if treatments is None else treatments,
        review_scope=deepcopy(scope), coverage=assessed, source_disagreements=disagreements,
        audit=audit, review_state=state, **kwargs)
    return result, assessed, disagreements, references


def saved_coverage(references, *, identity="saved-dispute", status="represented", state="complete"):
    return coverage(references, state=state, purposes={"L1": "non_account"}, dispositions=[
        disposition("P1S1", references["P1S1"], status=status,
                    record_ids=(identity,) if status == "represented" else ())])


def candidate_coverage(references, identity="C1"):
    return coverage(references, dispositions=[
        disposition(source, reference, status="represented", candidate_ids=(identity,))
        for source, reference in references.items()])


@pytest.mark.parametrize("support", (OMITTED, None), ids=("default", "explicit-none"))
def test_default_and_none_preserve_existing_generation_and_one_dispute_call(support):
    latest = "The recipient denies receiving the cylinder."
    references, _ = source_catalogue(latest)
    candidate = proposal("dispute", latest)
    model = ChoicesJudge([{"verdicts": [verdict("dispute", references["L1"])],
                           "coverage": candidate_coverage(references)}])
    result, assessed, _, _ = check(
        model, latest=latest, earlier=(), candidates=(candidate,), support=support)
    assert result == (candidate,) and assessed["state"] == "complete"
    assert len(model.calls) == 1
    call = model.calls[0]
    assert "coverage_extent_contract" not in call["payload"]
    assert "coverage_representation_options" not in call["payload"]
    assert "historical_disputes" not in call["payload"]
    assert call["schema"]["properties"]["coverage"] == record.coverage_schema(
        tuple(references), source_references=references, candidate_ids=("C1",))
    require_schema(call["output"], call["schema"])


@pytest.mark.parametrize("domain", ("current", "held", "historical"))
def test_original_alias_proof_offers_separate_record_context_without_a_new_proposal(domain):
    references, _ = source_catalogue(REQUEST, earlier=EARLIER)
    row = record_row(state="superseded" if domain == "historical" else domain)
    support = {row["id"]: proof(references["P1S1"])}
    model = ChoicesJudge([{"verdicts": [], "coverage": saved_coverage(references)}])
    before = deepcopy((row, support, EARLIER))
    result, assessed, disagreements, _ = check(
        model, records=() if domain == "historical" else (row,),
        history=(row,) if domain == "historical" else (), support=support)
    assert result == () and assessed["state"] == "complete" and disagreements == []
    assert assessed["missing_source_ids"] == [] and len(model.calls) == 1
    assert (row, support, EARLIER) == before
    call = model.calls[0]
    assert call["payload"]["source_treatments"] == references
    assert call["payload"]["coverage_extent_contract"] == record.COVERAGE_EXTENT_CONTRACT
    assert call["payload"]["coverage_representation_options"] == {
        "P1S1": {"record_ids": [row["id"]], "candidate_ids": []},
        "L1": {"record_ids": [], "candidate_ids": []}}
    assert call["payload"]["coverage_record_ids"] == [row["id"]]
    assert call["payload"]["active_disputes"] == (
        [] if domain == "historical" else [record.derived_record(row)])
    if domain == "historical":
        assert call["payload"]["historical_disputes"] == [record.derived_record(row)]
    assert call["output"]["coverage"]["dispositions"][0]["extent"] == "whole_source"
    assert "extent" not in repr(assessed)
    assert assessed["dispositions"][0]["quoted"] == ACCOUNT
    require_schema(call["output"], on_the_wire(call["schema"]))


@pytest.mark.parametrize("field,value", (
    ("turn_id", "another-original-turn"),
    ("quoted", "The recipient admits receiving the cylinder."),
))
def test_different_original_identity_cannot_be_replaced_by_matching_record_words(field, value):
    references, _ = source_catalogue(REQUEST, earlier=EARLIER)
    support = {"saved-dispute": proof({**references["P1S1"], field: value})}
    model = ChoicesJudge([
        {"verdicts": [], "coverage": saved_coverage(references)},
        {"verdicts": [], "coverage": saved_coverage(references, status="missing", state="partial")},
    ])
    result, assessed, _, _ = check(model, records=(record_row(),), support=support)
    assert result == () and assessed["state"] == "partial"
    assert assessed["missing_source_ids"] == ["P1S1"] and len(model.calls) == 2
    assert all(not option["record_ids"] for call in model.calls
               for option in call["payload"]["coverage_representation_options"].values())
    with pytest.raises(SchemaViolation):
        require_schema(model.calls[0]["output"], model.calls[0]["schema"])
    assert model.calls[1]["payload"]["pending_review_keys"] == ["$coverage"]
    assert model.calls[1]["payload"]["coverage_validation_issue"]
    require_schema(model.calls[1]["output"], model.calls[1]["schema"])


@pytest.mark.parametrize("historical", (False, True))
def test_explicit_empty_support_activates_native_choices_and_preserves_missing_work(historical):
    references, _ = source_catalogue(REQUEST, earlier=EARLIER)
    row = record_row()
    model = ChoicesJudge([{"verdicts": [], "coverage": saved_coverage(
        references, status="missing", state="partial")}])
    _, assessed, _, _ = check(
        model, records=() if historical else (row,),
        history=(row,) if historical else (), support={})
    assert assessed["state"] == "partial" and assessed["missing_source_ids"] == ["P1S1"]
    assert len(model.calls) == 1
    call = model.calls[0]
    assert call["payload"]["coverage_extent_contract"] == record.COVERAGE_EXTENT_CONTRACT
    assert all(option == {"record_ids": [], "candidate_ids": []} for option in
               call["payload"]["coverage_representation_options"].values())


def test_record_generation_option_still_requires_overlap_with_the_selected_original_portion():
    latest = "The recipient denies receipt and contests the carrier's separate storage charge."
    references, _ = source_catalogue(latest)
    split = latest.index("contests")
    support = {"saved-dispute": proof(references["L1"], portions=[{"start": 0, "end": split}])}
    invalid = coverage(references, dispositions=[
        disposition("L1", references["L1"], status="outside_scope", bounds=(0, split)),
        disposition("L1", references["L1"], status="represented", bounds=(split, len(latest)),
                    record_ids=("saved-dispute",))])
    repaired = deepcopy(invalid)
    repaired.update(state="partial")
    repaired["dispositions"][1].update(status="missing", record_ids=[])
    model = ChoicesJudge([{"verdicts": [], "coverage": invalid},
                          {"verdicts": [], "coverage": repaired}])
    row = record_row(words=latest[:split], turn="current")
    _, assessed, _, _ = check(
        model, latest=latest, earlier=(), records=(row,), support=support)
    assert assessed["state"] == "partial" and assessed["missing_source_ids"] == ["L1"]
    assert len(model.calls) == 2
    assert model.calls[0]["payload"]["coverage_representation_options"]["L1"]["record_ids"] == [
        "saved-dispute"]
    require_schema(model.calls[0]["output"], model.calls[0]["schema"])
    assert assessed["dispositions"][1]["quoted"] == latest[split:]
    assert "validation_issue" not in assessed


def test_correction_choices_use_pending_account_domains_and_retained_positive_support():
    first = "The recipient denies receipt of the north cylinder."
    second = "The sender contests the carrier's charge for the south cylinder."
    latest = first + " " + second
    references, _ = source_catalogue(latest)
    candidates = (
        proposal("dispute", first), proposal("dispute", second), proposal("dispute", first))
    malformed = verdict("dispute", references["L1"])
    malformed["account_check"]["source_checks"][0]["support_spans"][0]["end"] += 1
    peer = verdict("dispute", references["L2"], index=2, source_id="L2")
    negative = verdict("dispute", references["L1"], index=3, accept=False)
    initial = coverage(references, state="partial", dispositions=[
        disposition("L1", references["L1"]),
        disposition("L2", references["L2"], status="represented", candidate_ids=("C2",))])
    final = coverage(references, dispositions=[
        disposition("L1", references["L1"], status="represented", candidate_ids=("C1",)),
        disposition("L2", references["L2"], status="represented", candidate_ids=("C2",))])
    model = ChoicesJudge([
        {"verdicts": [malformed, peer, negative], "coverage": initial},
        {"verdicts": [verdict("dispute", references["L1"])], "coverage": final},
    ])
    result, assessed, _, _ = check(
        model, latest=latest, earlier=(), candidates=candidates, support={})
    assert result == candidates[:2] and assessed["state"] == "complete"
    assert len(model.calls) == 2
    first_call, correction = (call["payload"] for call in model.calls)
    assert first_call["coverage_candidate_ids"] == ["C1", "C2", "C3"]
    assert all(option["candidate_ids"] == ["C1", "C2", "C3"] for option in
               first_call["coverage_representation_options"].values())
    assert correction["coverage_representation_options"] == {
        "L1": {"record_ids": [], "candidate_ids": ["C1"]},
        "L2": {"record_ids": [], "candidate_ids": ["C1", "C2"]}}
    assert [row["candidate_id"] for row in correction["candidates"]] == ["C1"]
    assert {row["candidate_id"]: row["decision"] for row in
            correction["retained_candidate_context"]} == {"C2": peer, "C3": negative}
    assert correction["source_treatments"] == references
    assert correction["earlier_conversation"] == first_call["earlier_conversation"]
    require_schema(model.calls[1]["output"], model.calls[1]["schema"])


def test_pending_coarse_candidate_option_does_not_admit_an_unrelated_source():
    first = "The recipient denies receiving the north cylinder."
    latest = first + " The sender contests storage charges for the south cylinder."
    references, _ = source_catalogue(latest)
    candidate = proposal("dispute", first)
    invalid = coverage(references, dispositions=[
        disposition("L1", references["L1"], status="outside_scope"),
        disposition("L2", references["L2"], status="represented", candidate_ids=("C1",))])
    repaired = deepcopy(invalid)
    repaired.update(state="partial")
    repaired["dispositions"][1].update(status="missing", candidate_ids=[])
    model = ChoicesJudge([
        {"verdicts": [verdict("dispute", references["L1"])], "coverage": invalid},
        {"verdicts": [], "coverage": repaired},
    ])
    result, assessed, _, _ = check(
        model, latest=latest, earlier=(), candidates=(candidate,), support={})
    assert result == (candidate,) and assessed["state"] == "partial"
    assert assessed["missing_source_ids"] == ["L2"] and len(model.calls) == 2
    assert model.calls[0]["payload"]["coverage_representation_options"]["L2"]["candidate_ids"] == [
        "C1"]
    assert model.calls[1]["payload"]["coverage_representation_options"]["L2"]["candidate_ids"] == []
    assert model.calls[1]["payload"]["candidates"] == []
    require_schema(model.calls[0]["output"], model.calls[0]["schema"])


def test_historical_presentation_contains_account_formulation_without_durable_private_proof():
    references, _ = source_catalogue(REQUEST, earlier=EARLIER)
    row = record_row()
    row.update(grounding={"review": "private-review", "seal": "private-seal"},
               mutation_authority={"selector": "private-locator", "proof_digest": "private-digest"},
               saved_execution={"owner": "private-owner"}, review_cache="private-cache")
    support = {row["id"]: proof(references["P1S1"])}
    before = deepcopy((row, support))
    model = ChoicesJudge([{"verdicts": [], "coverage": saved_coverage(references)}])
    _, assessed, _, _ = check(model, history=(row,), support=support)
    assert assessed["state"] == "complete" and len(model.calls) == 1
    payload = model.calls[0]["payload"]
    expected = record.derived_record({key: value for key, value in row.items() if key not in (
        "grounding", "mutation_authority", "saved_execution", "review_cache")})
    assert payload["historical_disputes"] == [expected] and payload["active_disputes"] == []
    assert payload["source_treatments"] == references
    serialized = json.dumps(payload)
    assert "private-" not in serialized and "original-local-source" not in serialized
    assert "original-proposal" not in serialized and "coverage_record_support" not in payload
    assert (row, support) == before


@pytest.mark.parametrize("fault", (
    "active_history_collision", "active_conflict", "historical_conflict", "foreign_proof",
    "open_proof", "missing_positive_review", "non_advocate_proof",
))
def test_conflicting_catalogues_or_malformed_proof_fail_before_dispute_dispatch(fault):
    references, _ = source_catalogue(REQUEST, earlier=EARLIER)
    row = record_row()
    records, history = (row,), ()
    support = {row["id"]: proof(references["P1S1"])}
    if fault == "active_history_collision":
        history = (deepcopy(row),)
    elif fault == "active_conflict":
        records += ({**row, "statement": "Receipt was admitted."},)
    elif fault == "historical_conflict":
        records, history = (), (row, {**row, "statement": "Receipt was admitted."})
    elif fault == "foreign_proof":
        support["foreign-record"] = support.pop(row["id"])
    elif fault == "open_proof":
        support[row["id"]]["selector"] = "unowned-locator"
    elif fault == "non_advocate_proof":
        support[row["id"]]["source_references"]["original-local-source"]["role"] = "nm"
    else:
        support[row["id"]]["review"].update(verdict="reject", operation_supported=False)
    model, before = ChoicesJudge([]), deepcopy((records, history, support))
    with pytest.raises(SchemaViolation):
        check(model, records=records, history=history, support=support)
    assert model.calls == [] and (records, history, support) == before


def test_supplied_proof_requires_modern_exact_original_source_references():
    _, treatments = source_catalogue(REQUEST, earlier=EARLIER, versioned=False)
    model = ChoicesJudge([])
    with pytest.raises(SchemaViolation):
        check(model, records=(record_row(),), support={}, treatments=treatments)
    assert model.calls == []


@pytest.mark.parametrize("support", (OMITTED, None), ids=("default", "explicit-none"))
def test_history_requires_opt_in_proof_and_cannot_reopen_legacy_global_choices(support):
    model = ChoicesJudge([])
    with pytest.raises(SchemaViolation):
        check(model, history=(record_row(),), support=support)
    assert model.calls == []


def test_historical_coverage_record_cannot_become_an_active_revision_target():
    references, _ = source_catalogue(REQUEST, earlier=EARLIER)
    row = record_row()
    candidate = replace(proposal("dispute", REQUEST), relation="corrects",
                        related_dispute_ids=(row["id"],))
    model = ChoicesJudge([])
    with pytest.raises(SchemaViolation):
        check(model, candidates=(candidate,), history=(row,),
              support={row["id"]: proof(references["P1S1"])})
    assert model.calls == []


def test_unrequested_coverage_keeps_existing_verdict_shape_and_one_model_call():
    latest = "The recipient denies receiving the cylinder."
    references, _ = source_catalogue(latest)
    candidate = proposal("dispute", latest)
    model = ChoicesJudge([{"verdicts": [verdict("dispute", references["L1"])]}])
    result, assessed, _, _ = check(
        model, latest=latest, earlier=(), candidates=(candidate,), support={}, scope=None)
    assert result == (candidate,) and assessed["state"] == "unassessed" and len(model.calls) == 1
    assert "coverage" not in model.calls[0]["schema"]["properties"]
    assert "coverage_extent_contract" not in model.calls[0]["payload"]
    assert "coverage_representation_options" not in model.calls[0]["payload"]


def test_actual_strict_native_schema_counts_toward_budget_before_dispute_dispatch():
    latest = "The recipient denies receiving the cylinder."
    references, _ = source_catalogue(latest)
    candidate = proposal("dispute", latest)
    authored = {"verdicts": [verdict("dispute", references["L1"])],
                "coverage": candidate_coverage(references)}
    probe = ChoicesJudge([authored])
    result, assessed, _, _ = check(
        probe, latest=latest, earlier=(), candidates=(candidate,), support={})
    assert result == (candidate,) and assessed["state"] == "complete"
    call = probe.calls[0]
    prompt_words = call["prompt"].system + call["prompt"].user
    wire_schema = json.dumps(on_the_wire(call["schema"]), ensure_ascii=False, separators=(",", ":"))
    exact_budget = estimate_tokens(prompt_words + wire_schema) + call["max_tokens"]
    bounded = ChoicesJudge([authored], budget=exact_budget - 1)
    with pytest.raises(ContextOverflow):
        check(bounded, latest=latest, earlier=(), candidates=(candidate,), support={})
    assert bounded.calls == []
    fits = ChoicesJudge([authored], budget=exact_budget)
    result, assessed, _, _ = check(
        fits, latest=latest, earlier=(), candidates=(candidate,), support={})
    assert result == (candidate,) and assessed["state"] == "complete" and len(fits.calls) == 1


@pytest.mark.parametrize("wire", (False, True), ids=("declared", "strict-wire"))
@pytest.mark.parametrize("wrong_kind", ("record", "candidate"))
def test_dispute_schema_forwards_per_source_options_and_native_extent_shape(wire, wrong_kind):
    references, _ = source_catalogue(
        "The recipient denies receipt. The sender contests storage charges.")
    options = {"L1": {"record_ids": ["record-one"], "candidate_ids": ["C1"]},
               "L2": {"record_ids": ["record-two"], "candidate_ids": ["C2"]}}
    schema = owner._schema(
        (), tuple(references), coverage_ids=tuple(references), source_references=references,
        coverage_record_ids=("record-one", "record-two"), coverage_candidate_ids=("C1", "C2"),
        coverage_representation_options=options, native_coverage_extents=True, wire=True)
    schema = on_the_wire(schema) if wire else schema
    raw = coverage(references, dispositions=[
        disposition(identity, reference, status="represented",
                    record_ids=("record-one",) if identity == "L1" else ("record-two",))
        for identity, reference in references.items()])
    output = {"verdicts": [], "coverage": extent_coverage(raw, references)}
    require_schema(output, schema)
    invalid = deepcopy(output)
    selected = invalid["coverage"]["dispositions"][0]
    if wrong_kind == "record":
        selected["record_ids"] = ["record-two"]
    else:
        selected.update(record_ids=[], candidate_ids=["C2"])
    with pytest.raises(SchemaViolation):
        require_schema(invalid, schema)


def test_cache_reuses_positive_verdict_with_equivalent_proof_but_binds_historical_formulation():
    latest = "The sender contests the carrier's storage charge."
    references, _ = source_catalogue(latest, earlier=EARLIER)
    candidate, row = proposal("dispute", latest), record_row()
    support = {row["id"]: proof(references["P1S1"])}
    authored = coverage(references, dispositions=[
        disposition("P1S1", references["P1S1"], status="outside_scope"),
        disposition("L1", references["L1"], status="represented", candidate_ids=("C1",))])
    state = {}
    first = ChoicesJudge([{"verdicts": [verdict("dispute", references["L1"])],
                           "coverage": authored}])
    check(
        first, latest=latest, candidates=(candidate,), history=(row,), support=support, state=state)
    before = deepcopy(state)
    equivalent = deepcopy(support)
    equivalent[row["id"]]["review"]["reason"] = "Equivalent owned proof presentation."
    second = ChoicesJudge([{"verdicts": [], "coverage": authored}])
    result, assessed, _, _ = check(
        second, latest=latest, candidates=(candidate,),
        history=(row,), support=equivalent, state=state)
    assert result == (candidate,) and assessed["state"] == "complete" and len(second.calls) == 1
    assert second.calls[0]["payload"]["candidates"] == []
    assert second.calls[0]["payload"]["retained_candidate_context"][0]["decision"] == (
        before["cache"].decisions["C1"])
    assert "coverage_representation_options" not in state["cache"].context
    assert "coverage_record_support" not in state["cache"].context
    unchanged = deepcopy(state)
    no_dispatch = ChoicesJudge([])
    with pytest.raises(SchemaViolation):
        check(no_dispatch, latest=latest, candidates=(candidate,),
              history=({**row, "statement": "Receipt is now admitted."},),
              support=support, state=state)
    assert no_dispatch.calls == [] and state == unchanged
