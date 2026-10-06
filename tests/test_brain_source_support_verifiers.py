"""Raw fabricated Judge objects exercise fresh source support and coverage owners."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import dispute_verification as dispute_owner
from nm.brain import material_verification as material_owner
from nm.brain import record_review as record
from nm.brain.conversation import Message, OpeningCandidate
from nm.brain.material import MaterialCandidate, addressed_sources
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Tier, Usage, require_schema

SCOPE = {"requests": [{"request_index": 0, "material_purposes": ["interpretation_review"]}]}


@pytest.fixture(params=["material", "dispute"])
def kind(request):
    return request.param


class RawJudge:
    """Return exactly authored objects; no fixture adapter invents evidence fields."""

    def __init__(self, outputs):
        self.outputs = iter(deepcopy(outputs))
        self.calls = []

    def context_budget(self, tier):
        assert tier == Tier.JUDGE
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens):
        assert tier == Tier.JUDGE
        output = next(self.outputs)
        self.calls.append({"prompt": prompt, "payload": json.loads(prompt.user),
                           "schema": deepcopy(schema), "output": deepcopy(output),
                           "max_tokens": max_tokens})
        return ModelResult(
            text=None, data=output, tier=tier, provider="offline-raw",
            model="fabricated-independent-Judge", usage=Usage(0, 0, 0), latency_ms=0,
            completion=Completion.COMPLETE)


def source_catalogue(latest, *, earlier=(), roles=None, versioned=True):
    _, current, prior = addressed_sources(earlier, latest)
    references = {identity: {"turn_id": ref.turn_id, "role": ref.role, "quoted": ref.quoted}
                  for identity, ref in prior.items() if ref.role == "advocate"}
    references.update({identity: {"turn_id": "current", "role": "advocate", "quoted": words}
                       for identity, words in current.items()})
    treatments = {}
    for identity, reference in references.items():
        role = (roles or {}).get(identity, "reported_matter_account")
        row = {**reference, "content_role": role,
               "reason": "Private source-owner decision; not a verdict to echo."}
        if versioned:
            positive = role in {"reported_matter_account", "reported_party_position", "mixed"}
            portions = [{"start": 0, "end": len(reference["quoted"])}] if positive else []
            row.update(selection_contract=record.SOURCE_SELECTION_CONTRACT,
                       substantive_spans=record.owned_source_portions(reference, portions))
        treatments[identity] = row
    return references, treatments


def proposal(kind, words):
    result = MaterialCandidate(
        kind="event", statement=words, quoted=words, relation="new", prior_references=(),
        matter_scope="current", basis="stated", importance="relevant", placement="matter",
        why_material="This attributed event bears on the requested account.")
    if kind == "dispute":
        result = replace(result, kind="dispute", label="Disputed reported account",
                         identification="identified", placement="")
    return result


def candidate_id(kind, index=1):
    return ("D" if kind == "material" else "C") + str(index)


def verdict(kind, reference, *, index=1, source_id="L1", accept=True, supplies=True,
            supports=True, bounds=None, select_source=True):
    selected = [{"start": 0, "end": len(reference["quoted"])}] if supplies else []
    if bounds is not None:
        selected = [{"start": bounds[0], "end": bounds[1]}]
    result = {
        "candidate_id": candidate_id(kind, index), "verdict": "accept" if accept else "reject",
        "operation_supported": accept,
        "reason": "The original complete proposition determines this independent decision.",
        "account_check": {
            "content_role": "reported_matter_account" if supplies else "examination_material",
            "supported": supplies, "introduces_legal_analysis": False,
            "source_ids": [source_id] if select_source else [],
            "source_checks": [{"source_id": source_id, "supplies_account_content": supplies,
                               "supports_proposal": supports, "support_spans": selected,
                               "reason": "Read original framing and limiting context."}]
            if select_source else [],
            "reason": "The whole attributed account was independently examined.",
        }, "target_checks": [],
    }
    if kind == "dispute":
        result["candidate_role"] = "independent_dispute"
    return result


def source_check(identity, reference, *, purpose="account"):
    return {"source_id": identity, "content_purpose": purpose,
            "substantive_spans": [{"start": 0, "end": len(reference["quoted"])}]
            if purpose == "account" else [],
            "reason": "Original source purpose was judged without earlier classification labels."}


def disposition(identity, reference, *, status="missing", candidate_ids=(), record_ids=(),
                bounds=None):
    start, end = bounds if bounds is not None else (0, len(reference["quoted"]))
    return {"source_id": identity, "start": start, "end": end, "status": status,
            "candidate_ids": list(candidate_ids), "record_ids": list(record_ids),
            "reason": "The exact original portion has this scoped represented or remaining status."}


def coverage(references, *, state="complete", purposes=None, dispositions=()):
    return {"state": state, "reason": "Original content and represented state were compared.",
            "source_checks": [source_check(identity, reference,
                                           purpose=(purposes or {}).get(identity, "account"))
                              for identity, reference in references.items()],
            "dispositions": list(dispositions)}


def review(kind, model, latest, *, candidates=(), earlier=(), treatments=None, records=(),
           scope=SCOPE, review_state=None):
    _, treatments = source_catalogue(latest, earlier=earlier) if treatments is None else (
        None, treatments)
    checked_coverage, disagreements = {}, []
    arguments = dict(model=model, candidates=candidates, earlier=earlier, latest=latest,
                     source_treatments=treatments, review_scope=deepcopy(scope),
                     coverage=checked_coverage, source_disagreements=disagreements,
                     review_state=review_state)
    if kind == "material":
        result = material_owner.verify_material_grounding(
            **arguments, opening=OpeningCandidate(False, "", ""),
            current_matter_id="matter", active_material=records, prior_material=records)
        retained = result.details
    else:
        audit = []
        retained = dispute_owner.verify_disputes(**arguments, active_disputes=records, audit=audit)
        result = audit
    return retained, checked_coverage, disagreements, result


def test_checked_current_record_can_establish_no_change_without_new_candidate(kind):
    account = "The keeper did not identify the sender."
    earlier = (Message("original", "advocate", account),
               Message("answer", "nm", "The reported identification remains uncertain."))
    latest = "Please review the saved account."
    references, treatments = source_catalogue(latest, earlier=earlier,
                                             roles={"L1": "work_instruction"})
    records = ({"id": "current-record", "statement": account, "quoted": account,
                "source_turn_id": "original"},)
    output = {"verdicts": [], "coverage": coverage(
        references, purposes={"L1": "non_account"}, dispositions=[
            disposition("P1S1", references["P1S1"], status="represented",
                        record_ids=("current-record",))])}
    before = deepcopy(treatments)
    model = RawJudge([output])
    retained, assessed, disagreements, _ = review(
        kind, model, latest, earlier=earlier, treatments=treatments, records=records)
    assert retained == () and assessed["state"] == "complete"
    assert assessed["missing_source_ids"] == [] and disagreements == []
    assert treatments == before and len(model.calls) == 1
    payload = model.calls[0]["payload"]
    assert payload["source_support_contract"] == record.SOURCE_SUPPORT_CONTRACT
    assert payload["coverage_selection_contract"] == record.COVERAGE_SELECTION_CONTRACT
    assert payload["source_treatments"] == references
    assert payload["coverage_record_ids"] == ["current-record"]
    assert payload["coverage_candidate_ids"] == []
    assert "".join(row["text"] for row in payload["earlier_conversation"][0][
        "source_spans"]) == account
    assert "".join(row["text"] for row in payload["earlier_conversation"][1][
        "source_spans"]) == earlier[1].text
    assert assessed["dispositions"][0]["quoted"] == account
    require_schema(output, model.calls[0]["schema"])


def test_exact_independently_checked_whole_account_is_admitted_in_one_call(kind):
    latest = "The witness was uncertain and did not identify the sender."
    references, treatments = source_catalogue(latest)
    candidate = proposal(kind, latest)
    identity = candidate_id(kind)
    output = {"verdicts": [verdict(kind, references["L1"])], "coverage": coverage(
        references, dispositions=[disposition("L1", references["L1"], status="represented",
                                              candidate_ids=(identity,))])}
    model = RawJudge([output])
    retained, assessed, disagreements, _ = review(
        kind, model, latest, candidates=(candidate,), treatments=treatments)
    assert retained == (candidate,) and assessed["state"] == "complete"
    assert assessed["selection_contract"] == record.COVERAGE_SELECTION_CONTRACT
    assert disagreements == [] and len(model.calls) == 1
    assert model.calls[0]["output"] == output
    assert model.calls[0]["payload"]["source_treatments"] == references
    require_schema(output, model.calls[0]["schema"])


def test_partial_multi_clause_coverage_keeps_admitted_work_and_localises_remaining_content(kind):
    first = "The north parcel arrived late,"
    latest = first + " the south parcel remained undelivered and its dispatch date was uncertain."
    references, treatments = source_catalogue(latest)
    candidate = proposal(kind, first)
    split = len(first)
    output = {"verdicts": [verdict(kind, references["L1"], bounds=(0, split))],
              "coverage": coverage(references, state="partial", dispositions=[
                  disposition("L1", references["L1"], status="represented", bounds=(0, split),
                              candidate_ids=(candidate_id(kind),)),
                  disposition("L1", references["L1"], bounds=(split, len(latest))),
              ])}
    model = RawJudge([output])
    retained, assessed, _, _ = review(kind, model, latest, candidates=(candidate,),
                                     treatments=treatments)
    assert retained == (candidate,) and assessed["state"] == "partial"
    assert assessed["missing_source_ids"] == ["L1"] and len(model.calls) == 1
    assert assessed["dispositions"][1]["quoted"] == latest[split:]
    assert "validation_issue" not in assessed


@pytest.mark.parametrize("purpose,state,role", [
    ("non_account", "complete", "work_instruction"),
    ("unresolved", "unassessed", "uncertain"),
])
def test_empty_extraction_distinguishes_genuine_no_account_from_unresolved_purpose(
        kind, purpose, state, role):
    latest = "Review the framed passage in its original context."
    references, treatments = source_catalogue(latest, roles={"L1": role})
    model = RawJudge([{"verdicts": [], "coverage": coverage(
        references, state=state, purposes={"L1": purpose})}])
    retained, assessed, _, _ = review(kind, model, latest, treatments=treatments)
    assert retained == () and assessed["state"] == state
    assert assessed["missing_source_ids"] == ([] if purpose == "non_account" else ["L1"])
    assert len(model.calls) == 1 and "validation_issue" not in assessed


@pytest.mark.parametrize("mutation", ["boolean", "beyond_source", "foreign_quote"])
def test_malformed_support_gets_one_narrow_correction_with_complete_original_context(
        kind, mutation):
    latest = "The witness did not identify the sender."
    references, treatments = source_catalogue(latest)
    candidate = proposal(kind, latest)
    good = verdict(kind, references["L1"])
    bad = deepcopy(good)
    selected = bad["account_check"]["source_checks"][0]["support_spans"][0]
    if mutation == "boolean":
        selected["start"] = False
    elif mutation == "beyond_source":
        selected["end"] = len(latest) + 1
    else:
        selected["quoted"] = "An invented self-authored account."
    first = {"verdicts": [bad], "coverage": coverage(references, state="partial", dispositions=[
        disposition("L1", references["L1"])])}
    second = {"verdicts": [good], "coverage": coverage(references, dispositions=[
        disposition("L1", references["L1"], status="represented",
                    candidate_ids=(candidate_id(kind),))])}
    model = RawJudge([first, second])
    retained, assessed, _, _ = review(kind, model, latest, candidates=(candidate,),
                                     treatments=treatments)
    assert retained == (candidate,) and assessed["state"] == "complete"
    assert len(model.calls) == 2
    correction = model.calls[1]["payload"]
    assert [row["candidate_id"] for row in correction["candidates"]] == [candidate_id(kind)]
    assert correction["source_treatments"] == references
    assert correction["latest_message_spans"] == model.calls[0]["payload"]["latest_message_spans"]
    assert "support_spans" in correction["validation_issue"] or "source" in correction[
        "validation_issue"].lower()


def test_invalid_sibling_support_does_not_discard_independently_valid_peer(kind):
    first = "The north parcel arrived late."
    second = "The south parcel remained undelivered."
    latest = first + " " + second
    references, treatments = source_catalogue(latest)
    candidates = (proposal(kind, first), proposal(kind, second))
    bad = verdict(kind, references["L1"])
    bad["account_check"]["source_checks"][0]["support_spans"][0]["end"] += 1
    peer = verdict(kind, references["L2"], index=2, source_id="L2")
    initial = {"verdicts": [bad, peer], "coverage": coverage(
        references, state="partial", dispositions=[
            disposition("L1", references["L1"]),
            disposition("L2", references["L2"], status="represented",
                        candidate_ids=(candidate_id(kind, 2),)),
        ])}
    corrected = {"verdicts": [verdict(kind, references["L1"])], "coverage": coverage(
        references, dispositions=[
            disposition(identity, reference, status="represented",
                        candidate_ids=(candidate_id(kind, index),))
            for index, (identity, reference) in enumerate(references.items(), 1)])}
    model = RawJudge([initial, corrected])
    retained, assessed, _, _ = review(kind, model, latest, candidates=candidates,
                                     treatments=treatments)
    assert retained == candidates and assessed["state"] == "complete"
    correction = model.calls[1]["payload"]
    assert [row["candidate_id"] for row in correction["candidates"]] == [candidate_id(kind)]
    assert [row["candidate_id"] for row in correction["retained_candidate_context"]] == [
        candidate_id(kind, 2)]
    assert len(model.calls) == 2


@pytest.mark.parametrize("corrects", [False, True])
def test_false_empty_complete_coverage_is_corrected_or_explicitly_unassessed(kind, corrects):
    latest = "The witness did not identify the sender."
    references, treatments = source_catalogue(latest)
    invalid = {"verdicts": [], "coverage": {
        "state": "complete", "reason": "An unsupported empty coverage claim.",
        "source_checks": [], "dispositions": []}}
    repaired = {"verdicts": [], "coverage": coverage(references, state="partial", dispositions=[
        disposition("L1", references["L1"])])}
    model = RawJudge([invalid, repaired if corrects else invalid])
    retained, assessed, _, _ = review(kind, model, latest, treatments=treatments)
    assert retained == () and assessed["state"] == ("partial" if corrects else "unassessed")
    assert len(model.calls) == 2
    assert bool(assessed.get("validation_issue")) is not corrects
    if corrects:
        assert assessed["missing_source_ids"] == ["L1"]


def test_rejected_candidate_cannot_be_used_to_claim_its_original_account_is_represented(kind):
    latest = "The witness did not identify the sender."
    references, treatments = source_catalogue(latest)
    rejected = verdict(kind, references["L1"], accept=False, select_source=False)
    initial = {"verdicts": [rejected], "coverage": coverage(references, dispositions=[
        disposition("L1", references["L1"], status="represented",
                    candidate_ids=(candidate_id(kind),))])}
    corrected = {"verdicts": [], "coverage": coverage(references, state="partial", dispositions=[
        disposition("L1", references["L1"])])}
    model = RawJudge([initial, corrected])
    retained, assessed, _, _ = review(kind, model, latest,
                                     candidates=(proposal(kind, latest),), treatments=treatments)
    assert retained == () and assessed["state"] == "partial"
    assert assessed["missing_source_ids"] == ["L1"] and len(model.calls) == 2
    assert model.calls[1]["payload"]["candidates"] == []
    assert model.calls[1]["payload"]["retained_candidate_context"][0]["decision"][
        "verdict"] == "reject"


@pytest.mark.parametrize("owner_role,supplies", [
    ("examination_material", True), ("reported_matter_account", False),
], ids=["nonaccount-owner", "account-owner"])
def test_original_source_purpose_conflict_keeps_rejected_proposal_and_both_directions_visible(
        kind, owner_role, supplies):
    latest = "The supplied passage needs examination in its original framing."
    references, treatments = source_catalogue(latest, roles={"L1": owner_role})
    assessed = coverage(references, state="partial" if supplies else "complete",
                        purposes={"L1": "account" if supplies else "non_account"},
                        dispositions=[disposition("L1", references["L1"])] if supplies else [])
    model = RawJudge([{"verdicts": [verdict(
        kind, references["L1"], accept=False, supplies=supplies, supports=supplies)],
        "coverage": assessed}])
    retained, _, diagnostics, _ = review(kind, model, latest,
                                        candidates=(proposal(kind, latest),), treatments=treatments)
    assert retained == () and len(model.calls) == 1
    candidate_diagnostic = next(row for row in diagnostics if "candidate_id" in row)
    assert candidate_diagnostic["source_id"] == "L1"
    assert candidate_diagnostic["content_role"] == owner_role
    assert candidate_diagnostic["supplies_account_content"] is supplies


@pytest.mark.parametrize("owner_role,purpose", [
    ("examination_material", "account"), ("reported_matter_account", "non_account"),
], ids=["nonaccount-owner", "account-owner"])
def test_coverage_can_report_owned_source_purpose_conflict_when_extractor_supplied_no_candidate(
        kind, owner_role, purpose):
    latest = "The original framed passage needs its source purpose reconsidered."
    references, treatments = source_catalogue(latest, roles={"L1": owner_role})
    account = purpose == "account"
    output = {"verdicts": [], "coverage": coverage(
        references, state="partial" if account else "complete", purposes={"L1": purpose},
        dispositions=[disposition("L1", references["L1"])] if account else [])}
    model = RawJudge([output])
    retained, assessed, diagnostics, _ = review(kind, model, latest, treatments=treatments)
    assert retained == () and len(model.calls) == 1
    owned = next(row for row in diagnostics
                 if row.get("diagnostic_kind") == "coverage_source_purpose")
    assert owned["source_id"] == "L1" and owned["content_role"] == owner_role
    assert owned["supplies_account_content"] is account
    assert owned["coverage_source_check"] == assessed["source_checks"][0]
    assert owned["review_scope"] == SCOPE
    assert "candidate_id" not in owned and "proposal" not in owned


def test_explicit_legacy_rows_keep_the_existing_schema_without_silent_version_upgrade(kind):
    latest = "The witness did not identify the sender."
    references, treatments = source_catalogue(latest, versioned=False)
    decision = verdict(kind, references["L1"])
    del decision["account_check"]["source_checks"][0]["support_spans"]
    output = {"verdicts": [decision], "coverage": {
        "state": "complete", "reason": "The historical proposition represents this account.",
        "missing_source_ids": []}}
    model = RawJudge([output])
    candidate = proposal(kind, latest)
    retained, assessed, _, _ = review(kind, model, latest, candidates=(candidate,),
                                     treatments=treatments)
    assert retained == (candidate,) and assessed["state"] == "complete"
    assert "selection_contract" not in assessed
    assert "source_support_contract" not in model.calls[0]["payload"]
    assert "coverage_selection_contract" not in model.calls[0]["payload"]
    require_schema(output, model.calls[0]["schema"])


def test_fresh_cached_peer_survives_added_owned_candidate_choices(kind):
    first = "The north parcel arrived late."
    second = "The south parcel remained undelivered."
    latest = first + " " + second
    references, treatments = source_catalogue(latest)
    proposed = (proposal(kind, first), proposal(kind, second))
    first_id, second_id = candidate_id(kind), candidate_id(kind, 2)
    state = {}
    first_model = RawJudge([{
        "verdicts": [verdict(kind, references["L1"])],
        "coverage": coverage(references, state="partial", dispositions=[
            disposition("L1", references["L1"], status="represented", candidate_ids=(first_id,)),
            disposition("L2", references["L2"]),
        ]),
    }])
    retained, assessed, _, _ = review(
        kind, first_model, latest, candidates=proposed[:1], treatments=treatments,
        review_state=state)
    assert retained == proposed[:1] and assessed["state"] == "partial"
    second_model = RawJudge([{
        "verdicts": [verdict(kind, references["L2"], index=2, source_id="L2")],
        "coverage": coverage(references, dispositions=[
            disposition("L1", references["L1"], status="represented", candidate_ids=(first_id,)),
            disposition("L2", references["L2"], status="represented", candidate_ids=(second_id,)),
        ]),
    }])
    retained, assessed, _, _ = review(
        kind, second_model, latest, candidates=proposed, treatments=treatments, review_state=state)
    assert retained == proposed and assessed["state"] == "complete"
    assert len(first_model.calls) == len(second_model.calls) == 1
    assert [row["candidate_id"] for row in second_model.calls[0]["payload"]["candidates"]] == [
        second_id]
    retained_context = second_model.calls[0]["payload"]["retained_candidate_context"]
    assert retained_context[0]["candidate_id"] == first_id


@pytest.mark.parametrize("candidate_representation", [False, True])
def test_fresh_scope_hold_preserves_source_reading_and_names_exact_held_target(
    kind, candidate_representation
):
    from nm.brain.mutation_contracts import AUTHORITY_CONTRACT, build_mutation_authorities
    from tests import test_brain_dispute_mutation_scope as fixture

    latest = fixture.REVIEW + " " + fixture.NOTICE
    references, treatments = source_catalogue(
        latest, earlier=fixture.EARLIER, roles={"L1": "work_instruction"})
    ledger = build_mutation_authorities(
        owner=fixture.OWNER, expected_version=4,
        target_catalogue={row["id"]: row for row in fixture.ACTIVE},
        source_catalogue=treatments, proposals=[{
            "request_index": 0, "authority_kind": "interpretation_review",
            "authority_source_ids": ["L1"], "target_scope": "exact",
            "target_ids": ["dispute-a"], "permitted_relations": ["corrects"],
        }], request_indices=(0,))
    scope = {"owner": fixture.OWNER, "mutation_authority_contract": AUTHORITY_CONTRACT,
             "mutation_authorities": ledger, "requests": SCOPE["requests"]}
    wrong = fixture.candidate(fixture.REVIEW, target="dispute-b")
    if kind == "material":
        wrong = replace(wrong, kind="event", placement="matter", related_dispute_ids=(),
                        related_material_ids=("dispute-b",))
    peer = proposal(kind, fixture.NOTICE)
    wrong_id, peer_id = candidate_id(kind), candidate_id(kind, 2)
    decisions = [fixture.verdict(wrong_id, target="dispute-b"),
                 fixture.verdict(peer_id, support="L2")]
    for row in decisions:
        if kind == "material":
            row.pop("candidate_role")
        for check in row["account_check"]["source_checks"]:
            check["support_spans"] = [{
                "start": 0, "end": len(references[check["source_id"]]["quoted"])}]
    original_representation = disposition(
        "P1S1", references["P1S1"], status="represented",
        candidate_ids=(wrong_id,) if candidate_representation else (),
        record_ids=() if candidate_representation else ("dispute-a",))
    output = {"verdicts": decisions, "coverage": coverage(
        references, purposes={"L1": "non_account"}, dispositions=[
            original_representation,
            disposition("P1S2", references["P1S2"], status="represented",
                        record_ids=("dispute-b",)),
            disposition("L2", references["L2"], status="represented", candidate_ids=(peer_id,)),
        ])}
    model = RawJudge([output])
    retained, assessed, _, _ = review(
        kind, model, latest, candidates=(wrong, peer), earlier=fixture.EARLIER,
        records=fixture.ACTIVE, treatments=treatments, scope=scope)
    assert retained == (peer,) and len(model.calls) == 1
    assert assessed["state"] == "partial" and "validation_issue" not in assessed
    hold = assessed["admission_holds"][0]
    assert hold["candidate_id"] == wrong_id and hold["target_ids"] == ["dispute-b"]
    assert hold["relation"] == "corrects" and hold["quoted"] == fixture.REVIEW
    assert hold["admission_issue"] == "mutation_scope"
    assert len(assessed["source_checks"]) == len(references)
    represented = next(row for row in assessed["dispositions"] if row["source_id"] == "L2")
    assert represented["status"] == "represented" and represented["candidate_ids"] == [peer_id]
    held = next(row for row in assessed["dispositions"] if row["source_id"] == "P1S1")
    assert held["status"] == ("unresolved" if candidate_representation else "represented")
    assert assessed["missing_source_ids"] == (["P1S1"] if candidate_representation else [])
