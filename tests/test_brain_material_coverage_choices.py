"""Material coverage choices use owned support without exposing durable proof.

Scripted independent judgments test generation, admission and bounded reuse.
They do not establish pinned-model semantic quality or public producer wiring.
"""

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import material_verification as owner
from nm.brain import record_review as record
from nm.brain.conversation import Message, OpeningCandidate
from nm.shared.model_port import ContextOverflow, SchemaViolation, estimate_tokens, require_schema
from tests.test_brain_coverage_record_support import review as positive_review
from tests.test_brain_source_support_verifiers import (
    SCOPE,
    RawJudge,
    coverage,
    disposition,
    proposal,
    source_catalogue,
    verdict,
)

OMITTED = object()
ACCOUNT = "The custodian cannot identify when the cylinder arrived."
REQUEST = "Review the earlier account in its original context."
EARLIER = (Message("earlier-account", "advocate", ACCOUNT),
           Message("earlier-answer", "nm", "Receipt time remains unconfirmed."))


def extent_coverage(value, references):
    """Transport exact fixture endpoints, preserving every authored judgment."""
    result = deepcopy(value)

    def extent(portion, source):
        if (portion["start"], portion["end"]) == (0, len(references[source]["quoted"])):
            return {"extent": "whole_source"}
        return {"extent": "exact_subrange", "start": portion["start"], "end": portion["end"]}

    for check in result["source_checks"]:
        check["substantive_spans"] = [extent(part, check["source_id"])
                                      for part in check["substantive_spans"]]
    for portion in result["dispositions"]:
        selected = extent(portion, portion["source_id"])
        portion.pop("start")
        portion.pop("end")
        portion.update(selected)
    return result


class ChoicesJudge(RawJudge):
    """Use the fresh native extent wire only when the owning input offers it."""

    def __init__(self, outputs, *, budget=100_000):
        super().__init__(outputs)
        self.budget = budget

    def context_budget(self, tier):
        super().context_budget(tier)
        return self.budget

    def structured(self, prompt, schema, tier, *, max_tokens):
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        call = self.calls[-1]
        if (call["payload"].get("coverage_extent_contract") == record.COVERAGE_EXTENT_CONTRACT
                and "coverage" in result.data):
            data = deepcopy(result.data)
            data["coverage"] = extent_coverage(
                data["coverage"], call["payload"]["source_treatments"])
            call["output"] = deepcopy(data)
            result = replace(result, data=data)
        return result


def record_row(identity="saved-detail", *, words=ACCOUNT, turn="earlier-account"):
    return {"id": identity, "kind": "event", "statement": words, "quoted": words,
            "source_turn_id": turn, "matter_scope": "current", "basis": "stated",
            "placement": "matter", "relation": "new"}


def proof(reference, *, portions=None):
    original = {"original-local-source": deepcopy(reference)}
    return {"review": positive_review("original-proposal", "original-local-source", original,
                                     portions=portions),
            "source_references": original}


def check(model, *, latest=REQUEST, earlier=EARLIER, candidates=(), records=(), history=(),
          support=OMITTED, treatments=None, prior_material=None, opening=None,
          state=None, scope=SCOPE):
    references, default_treatments = source_catalogue(
        latest, earlier=earlier, roles={"L1": "work_instruction"} if latest == REQUEST else None)
    treatments = default_treatments if treatments is None else treatments
    assessed, disagreements = {}, []
    kwargs = {"coverage_record_support": support} if support is not OMITTED else {}
    if history:
        kwargs["historical_material"] = history
    result = owner.verify_material_grounding(
        model, candidates=candidates, opening=opening or OpeningCandidate(False, "", ""),
        earlier=earlier, latest=latest, current_matter_id="owned-matter",
        source_treatments=treatments, review_scope=deepcopy(scope), active_material=records,
        prior_material=records if prior_material is None else prior_material,
        coverage=assessed, source_disagreements=disagreements, review_state=state, **kwargs)
    return result, assessed, disagreements, references


def saved_coverage(references, *, identity="saved-detail", status="represented", state="complete"):
    return coverage(references, state=state, purposes={"L1": "non_account"}, dispositions=[
        disposition("P1S1", references["P1S1"], status=status,
                    record_ids=(identity,) if status == "represented" else ())])


@pytest.mark.parametrize("support", (OMITTED, None), ids=("default", "explicit-none"))
def test_default_and_none_preserve_existing_generation_and_single_call(support):
    latest = "The recipient cannot identify the final custodian."
    references, _ = source_catalogue(latest)
    candidate = proposal("material", latest)
    authored = {"verdicts": [verdict("material", references["L1"])], "coverage": coverage(
        references, dispositions=[disposition("L1", references["L1"], status="represented",
                                              candidate_ids=("D1",))])}
    model = ChoicesJudge([authored])
    result, assessed, _, _ = check(
        model, latest=latest, earlier=(), candidates=(candidate,), support=support)
    assert result.details == (candidate,) and assessed["state"] == "complete"
    assert len(model.calls) == 1
    call = model.calls[0]
    assert "coverage_extent_contract" not in call["payload"]
    assert "coverage_representation_options" not in call["payload"]
    assert "historical_material" not in call["payload"]
    assert call["schema"]["properties"]["coverage"] == record.coverage_schema(
        tuple(references), source_references=references, candidate_ids=("D1",))
    require_schema(call["output"], call["schema"])


@pytest.mark.parametrize("historical", (False, True), ids=("active", "historical"))
def test_original_proof_remaps_exact_alias_without_a_new_detail_or_model_stage(historical):
    references, _ = source_catalogue(REQUEST, earlier=EARLIER)
    row = record_row()
    support = {row["id"]: proof(references["P1S1"])}
    model = ChoicesJudge([{"verdicts": [], "coverage": saved_coverage(references)}])
    before = deepcopy((row, support, EARLIER))
    result, assessed, disagreements, _ = check(
        model, records=() if historical else (row,), history=(row,) if historical else (),
        support=support)
    assert result.details == () and assessed["state"] == "complete"
    assert assessed["missing_source_ids"] == [] and disagreements == []
    assert len(model.calls) == 1 and (row, support, EARLIER) == before
    call = model.calls[0]
    assert call["payload"]["coverage_extent_contract"] == record.COVERAGE_EXTENT_CONTRACT
    assert call["payload"]["coverage_representation_options"] == {
        "P1S1": {"record_ids": [row["id"]], "candidate_ids": []},
        "L1": {"record_ids": [], "candidate_ids": []}}
    assert call["payload"]["coverage_record_ids"] == [row["id"]]
    assert call["payload"]["source_treatments"] == references
    assert call["payload"]["linked_records"] == []
    assert call["payload"]["active_material"] == (
        [] if historical else [record.derived_record(row)])
    if historical:
        assert call["payload"]["historical_material"] == [record.derived_record(row)]
    assert call["output"]["coverage"]["dispositions"][0]["extent"] == "whole_source"
    assert "extent" not in repr(assessed)
    assert assessed["dispositions"][0]["quoted"] == ACCOUNT
    require_schema(call["output"], call["schema"])


@pytest.mark.parametrize("field,value", (
    ("turn_id", "different-original-turn"),
    ("quoted", "The cylinder's delivery time was confirmed."),
))
def test_matching_display_words_cannot_substitute_different_original_proof(field, value):
    references, _ = source_catalogue(REQUEST, earlier=EARLIER)
    original = {**references["P1S1"], field: value}
    support = {"saved-detail": proof(original)}
    model = ChoicesJudge([
        {"verdicts": [], "coverage": saved_coverage(references)},
        {"verdicts": [], "coverage": saved_coverage(references, status="missing", state="partial")},
    ])
    result, assessed, _, _ = check(model, records=(record_row(),), support=support)
    assert result.details == () and assessed["state"] == "partial"
    assert assessed["missing_source_ids"] == ["P1S1"] and len(model.calls) == 2
    for call in model.calls:
        assert all(not row["record_ids"] for row in
                   call["payload"]["coverage_representation_options"].values())
    with pytest.raises(SchemaViolation):
        require_schema(model.calls[0]["output"], model.calls[0]["schema"])
    assert "$coverage" in model.calls[1]["payload"]["validation_issue"]
    require_schema(model.calls[1]["output"], model.calls[1]["schema"])


@pytest.mark.parametrize("historical", (False, True))
def test_explicit_empty_proof_offers_no_record_choices_but_preserves_missing_work(historical):
    references, _ = source_catalogue(REQUEST, earlier=EARLIER)
    row = record_row()
    model = ChoicesJudge([{"verdicts": [], "coverage": saved_coverage(
        references, status="missing", state="partial")}])
    _, assessed, _, _ = check(
        model, records=() if historical else (row,),
        history=(row,) if historical else (), support={})
    assert assessed["state"] == "partial" and assessed["missing_source_ids"] == ["P1S1"]
    assert len(model.calls) == 1
    assert model.calls[0]["payload"]["coverage_extent_contract"] == record.COVERAGE_EXTENT_CONTRACT
    assert all(row == {"record_ids": [], "candidate_ids": []} for row in
               model.calls[0]["payload"]["coverage_representation_options"].values())


def test_native_source_choice_does_not_certify_a_disjoint_record_support_portion():
    latest = "The north crate was sealed and its delivery time remains uncertain."
    references, _ = source_catalogue(latest)
    split = latest.index("its delivery")
    support = {"saved-detail": proof(references["L1"], portions=[{"start": 0, "end": split}])}
    bad = coverage(references, dispositions=[
        disposition("L1", references["L1"], status="outside_scope", bounds=(0, split)),
        disposition("L1", references["L1"], status="represented", bounds=(split, len(latest)),
                    record_ids=("saved-detail",))])
    good = deepcopy(bad)
    good.update(state="partial")
    good["dispositions"][1].update(status="missing", record_ids=[])
    model = ChoicesJudge([{"verdicts": [], "coverage": bad}, {"verdicts": [], "coverage": good}])
    row = record_row(words=latest[:split], turn="current")
    _, assessed, _, _ = check(model, latest=latest, earlier=(), records=(row,), support=support)
    assert assessed["state"] == "partial" and assessed["missing_source_ids"] == ["L1"]
    assert len(model.calls) == 2
    assert model.calls[0]["payload"]["coverage_representation_options"]["L1"]["record_ids"] == (
        ["saved-detail"])
    require_schema(model.calls[0]["output"], model.calls[0]["schema"])
    assert assessed["dispositions"][1]["quoted"] == latest[split:]
    assert "validation_issue" not in assessed


def test_correction_choices_follow_retained_positive_support_and_pending_account_domain():
    first = "The receiver says the north crate arrived sealed."
    second = "The receiver cannot identify the south crate's custodian."
    latest = first + " " + second
    references, _ = source_catalogue(latest)
    candidates = (proposal("material", first), proposal("material", second),
                  proposal("material", first))
    malformed = verdict("material", references["L1"])
    malformed["account_check"]["source_checks"][0]["support_spans"][0]["end"] += 1
    peer = verdict("material", references["L2"], index=2, source_id="L2")
    negative = verdict("material", references["L1"], index=3, accept=False)
    opening = OpeningCandidate(True, "Reported crate account", first, "", "Reported crate account")
    opening_verdict = verdict("material", references["L1"])
    opening_verdict["candidate_id"] = "O1"
    initial = coverage(references, state="partial", dispositions=[
        disposition("L1", references["L1"]),
        disposition("L2", references["L2"], status="represented", candidate_ids=("D2",))])
    final = coverage(references, dispositions=[
        disposition("L1", references["L1"], status="represented", candidate_ids=("D1",)),
        disposition("L2", references["L2"], status="represented", candidate_ids=("D2",))])
    model = ChoicesJudge([
        {"verdicts": [malformed, peer, negative, opening_verdict], "coverage": initial},
        {"verdicts": [verdict("material", references["L1"])], "coverage": final},
    ])
    result, assessed, _, _ = check(model, latest=latest, earlier=(), candidates=candidates,
                                 support={}, opening=opening)
    assert result.details == candidates[:2] and result.opening_supported is True
    assert assessed["state"] == "complete" and len(model.calls) == 2
    first_call, correction = (call["payload"] for call in model.calls)
    assert first_call["coverage_candidate_ids"] == ["D1", "D2", "D3"]
    assert all(row["candidate_ids"] == ["D1", "D2", "D3"] for row in
               first_call["coverage_representation_options"].values())
    assert correction["coverage_representation_options"] == {
        "L1": {"record_ids": [], "candidate_ids": ["D1"]},
        "L2": {"record_ids": [], "candidate_ids": ["D1", "D2"]}}
    assert [row["candidate_id"] for row in correction["candidates"]] == ["D1"]
    retained = {row["candidate_id"]: row["decision"] for row in
                correction["retained_candidate_context"]}
    assert retained == {"D2": peer, "D3": negative, "O1": opening_verdict}
    assert correction["source_treatments"] == references
    assert correction["earlier_conversation"] == first_call["earlier_conversation"]
    require_schema(model.calls[1]["output"], model.calls[1]["schema"])


def test_pending_coarse_choice_still_requires_actual_positive_source_support_at_admission():
    first = "The receiver reports that the north crate arrived sealed."
    latest = first + " The receiver cannot identify the south crate's custodian."
    references, _ = source_catalogue(latest)
    candidate = proposal("material", first)
    invalid = coverage(references, dispositions=[
        disposition("L1", references["L1"], status="outside_scope"),
        disposition("L2", references["L2"], status="represented", candidate_ids=("D1",))])
    repaired = deepcopy(invalid)
    repaired.update(state="partial")
    repaired["dispositions"][1].update(status="missing", candidate_ids=[])
    model = ChoicesJudge([
        {"verdicts": [verdict("material", references["L1"])], "coverage": invalid},
        {"verdicts": [], "coverage": repaired},
    ])
    result, assessed, _, _ = check(
        model, latest=latest, earlier=(), candidates=(candidate,), support={})
    assert result.details == (candidate,) and assessed["state"] == "partial"
    assert assessed["missing_source_ids"] == ["L2"] and len(model.calls) == 2
    assert model.calls[0]["payload"]["coverage_representation_options"]["L2"]["candidate_ids"] == (
        ["D1"])
    assert model.calls[1]["payload"]["coverage_representation_options"]["L2"]["candidate_ids"] == []
    assert model.calls[1]["payload"]["candidates"] == []
    require_schema(model.calls[0]["output"], model.calls[0]["schema"])


def test_historical_presentation_omits_durable_review_authority_and_locator_metadata():
    references, _ = source_catalogue(REQUEST, earlier=EARLIER)
    row = record_row()
    row.update(grounding={"review": "private-saved-review", "seal": "private-review-seal"},
               mutation_authority={"selector": "private-locator", "proof_digest": "private-digest"})
    support = {row["id"]: proof(references["P1S1"])}
    model = ChoicesJudge([{"verdicts": [], "coverage": saved_coverage(references)}])
    before = deepcopy((row, support))
    _, assessed, _, _ = check(model, history=(row,), support=support)
    assert assessed["state"] == "complete" and len(model.calls) == 1
    payload = model.calls[0]["payload"]
    expected = record.derived_record({key: value for key, value in row.items()
                                      if key not in ("grounding", "mutation_authority")})
    assert payload["historical_material"] == [expected]
    assert payload["active_material"] == [] and payload["linked_records"] == []
    assert payload["source_treatments"] == references
    serialized = json.dumps(payload)
    assert "private-" not in serialized and "original-local-source" not in serialized
    assert "original-proposal" not in serialized and "coverage_record_support" not in payload
    assert (row, support) == before


@pytest.mark.parametrize("fault", (
    "active_history_collision", "active_conflict", "historical_conflict", "foreign_proof",
    "open_proof", "missing_positive_review", "non_advocate_proof",
))
def test_conflicting_catalogues_and_malformed_owned_proofs_fail_before_model_dispatch(fault):
    references, _ = source_catalogue(REQUEST, earlier=EARLIER)
    row = record_row()
    records, history = (row,), ()
    support = {row["id"]: proof(references["P1S1"])}
    if fault == "active_history_collision":
        history = (deepcopy(row),)
    elif fault == "active_conflict":
        records += ({**row, "statement": "Receipt was confirmed."},)
    elif fault == "historical_conflict":
        records, history = (), (row, {**row, "statement": "Receipt was confirmed."})
    elif fault == "foreign_proof":
        support["foreign-record"] = support.pop(row["id"])
    elif fault == "open_proof":
        support[row["id"]]["selector"] = "unowned-locator"
    elif fault == "non_advocate_proof":
        support[row["id"]]["source_references"]["original-local-source"]["role"] = "nm"
    else:
        support[row["id"]]["review"].update(verdict="reject", operation_supported=False)
    model = ChoicesJudge([])
    before = deepcopy((records, history, support))
    with pytest.raises(SchemaViolation):
        check(model, records=records, history=history, support=support)
    assert model.calls == [] and (records, history, support) == before


def test_supplied_support_requires_modern_exact_source_references():
    _, treatments = source_catalogue(REQUEST, earlier=EARLIER, versioned=False)
    model = ChoicesJudge([])
    with pytest.raises(SchemaViolation):
        check(model, records=(record_row(),), support={}, treatments=treatments)
    assert model.calls == []


@pytest.mark.parametrize("support", (OMITTED, None), ids=("default", "explicit-none"))
def test_history_without_modern_proof_cannot_reopen_legacy_global_record_admission(support):
    model = ChoicesJudge([])
    with pytest.raises(SchemaViolation):
        check(model, history=(record_row(),), support=support)
    assert model.calls == []


def test_retired_coverage_row_cannot_become_a_revision_target_from_history():
    references, _ = source_catalogue(REQUEST, earlier=EARLIER)
    row = record_row()
    candidate = replace(proposal("material", REQUEST), relation="corrects",
                        related_material_ids=(row["id"],))
    model = ChoicesJudge([])
    with pytest.raises(SchemaViolation):
        check(model, candidates=(candidate,), history=(row,), prior_material=(row,),
              support={row["id"]: proof(references["P1S1"])})
    assert model.calls == []


def test_unrequested_coverage_does_not_add_native_shape_or_an_additional_call():
    latest = "The recipient cannot identify the final custodian."
    references, _ = source_catalogue(latest)
    candidate = proposal("material", latest)
    model = ChoicesJudge([{"verdicts": [verdict("material", references["L1"])]}])
    result, assessed, _, _ = check(
        model, latest=latest, earlier=(), candidates=(candidate,), support={}, scope=None)
    assert result.details == (candidate,) and assessed == {} and len(model.calls) == 1
    assert "coverage" not in model.calls[0]["schema"]["properties"]
    assert "coverage_extent_contract" not in model.calls[0]["payload"]
    assert "coverage_representation_options" not in model.calls[0]["payload"]


def test_actual_offered_native_schema_is_counted_before_structured_dispatch():
    latest = "The recipient cannot identify the final custodian."
    references, _ = source_catalogue(latest)
    candidate = proposal("material", latest)
    authored = {"verdicts": [verdict("material", references["L1"])], "coverage": coverage(
        references, dispositions=[disposition("L1", references["L1"], status="represented",
                                              candidate_ids=("D1",))])}
    probe = ChoicesJudge([authored])
    result, assessed, _, _ = check(
        probe, latest=latest, earlier=(), candidates=(candidate,), support={})
    assert result.details == (candidate,) and assessed["state"] == "complete"
    call = probe.calls[0]
    prompt_only_budget = estimate_tokens(call["prompt"].system + call["prompt"].user) + (
        call["max_tokens"])
    bounded = ChoicesJudge([authored], budget=prompt_only_budget)
    with pytest.raises(ContextOverflow):
        check(bounded, latest=latest, earlier=(), candidates=(candidate,), support={})
    assert bounded.calls == []


@pytest.mark.parametrize("wrong_kind", ("record", "candidate"))
def test_material_schema_forwards_source_specific_options_and_native_extent_shape(wrong_kind):
    references, _ = source_catalogue(
        "The receiver denies receipt. The sender cannot identify custody.")
    options = {"L1": {"record_ids": ["record-one"], "candidate_ids": ["D1"]},
               "L2": {"record_ids": ["record-two"], "candidate_ids": ["D2"]}}
    schema = owner._schema(
        (), tuple(references), coverage_ids=tuple(references), source_references=references,
        coverage_record_ids=("record-one", "record-two"), coverage_candidate_ids=("D1", "D2"),
        coverage_representation_options=options, native_coverage_extents=True, wire=True)
    raw = coverage(references, dispositions=[
        disposition(identity, reference, status="represented",
                    record_ids=("record-one",) if identity == "L1" else ("record-two",))
        for identity, reference in references.items()])
    output = {"source_readings": {identity: {"content_role": "reported_matter_account",
                                            "reason": "Declared attributed original account."}
                                  for identity in references},
              "verdicts": [], "coverage": extent_coverage(raw, references)}
    require_schema(output, schema)
    malicious = deepcopy(output)
    selected = malicious["coverage"]["dispositions"][0]
    if wrong_kind == "record":
        selected["record_ids"] = ["record-two"]
    else:
        selected.update(record_ids=[], candidate_ids=["D2"])
    with pytest.raises(SchemaViolation):
        require_schema(malicious, schema)


def test_raw_proof_reasons_are_not_cache_context_and_historical_formulations_are():
    latest = "The recipient cannot identify the current custodian."
    references, _ = source_catalogue(latest, earlier=EARLIER)
    candidate, row = proposal("material", latest), record_row()
    support = {row["id"]: proof(references["P1S1"])}
    authored = coverage(references, dispositions=[
        disposition("P1S1", references["P1S1"], status="outside_scope"),
        disposition("L1", references["L1"], status="represented", candidate_ids=("D1",))])
    state = {}
    first = ChoicesJudge([{"verdicts": [verdict("material", references["L1"])],
                           "coverage": authored}])
    check(first, latest=latest, candidates=(candidate,),
          history=(row,), support=support, state=state)
    before = deepcopy(state)
    changed_proof = deepcopy(support)
    changed_proof[row["id"]]["review"]["reason"] = "Equivalent owned proof presentation."
    second = ChoicesJudge([{"verdicts": [], "coverage": authored}])
    result, assessed, _, _ = check(
        second, latest=latest, candidates=(candidate,),
        history=(row,), support=changed_proof, state=state)
    assert result.details == (candidate,) and assessed["state"] == "complete"
    assert second.calls[0]["payload"]["candidates"] == []
    assert second.calls[0]["payload"]["retained_candidate_context"][0]["decision"] == (
        before["cache"].decisions["D1"])
    assert "coverage_representation_options" not in state["cache"].context
    assert "coverage_record_support" not in state["cache"].context
    unchanged = deepcopy(state)
    no_dispatch = ChoicesJudge([])
    with pytest.raises(SchemaViolation):
        check(no_dispatch, latest=latest, candidates=(candidate,),
              history=({**row, "statement": "Receipt is now confirmed."},),
              support=support, state=state)
    assert no_dispatch.calls == [] and state == unchanged


def test_equal_active_duplicates_normalize_before_cached_review_reuse():
    latest = "The recipient cannot identify the current custodian."
    references, _ = source_catalogue(latest, earlier=EARLIER)
    candidate, row = proposal("material", latest), record_row()
    records = (row, deepcopy(row))
    support = {row["id"]: proof(references["P1S1"])}
    authored = coverage(references, dispositions=[
        disposition("P1S1", references["P1S1"], status="outside_scope"),
        disposition("L1", references["L1"], status="represented", candidate_ids=("D1",))])
    model = ChoicesJudge([{"verdicts": [verdict("material", references["L1"])],
                           "coverage": authored}])
    state = {}
    first, assessed, _, _ = check(
        model, latest=latest, candidates=(candidate,),
        records=records, support=support, state=state)
    assert first.details == (candidate,) and assessed["state"] == "complete"
    cached = deepcopy(state["cache"].decisions["D1"])
    second_model = ChoicesJudge([{"verdicts": [], "coverage": authored}])
    second, checked, _, _ = check(
        second_model, latest=latest, candidates=(candidate,), records=records,
        support=support, state=state)
    assert second == first and checked == assessed and len(second_model.calls) == 1
    assert model.calls[0]["payload"]["active_material"] == [record.derived_record(row)]
    assert state["cache"].context["active_material"] == [record.derived_record(row)]
    assert second_model.calls[0]["payload"]["candidates"] == []
    assert second_model.calls[0]["payload"]["retained_candidate_context"][0]["decision"] == cached
    assert records == (row, row)
