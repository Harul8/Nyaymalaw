"""Fresh material groups preserve owned coverage, admission and public replay.

All meanings and independent judgments are explicitly scripted. Raw group
outputs test the shipped producer/consumer handoff, not model quality. Fixture
transport is separately checked and cannot supply missing support or purpose.
"""

import json
from copy import deepcopy

import pytest

from nm.brain import material_verification as owner
from nm.brain import record_review as record
from nm.brain import turn
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ContextOverflow,
    ModelResult,
    SchemaViolation,
    Usage,
    estimate_tokens,
    on_the_wire,
    require_schema,
)
from tests.brain_reader_fixture import fresh_review_reply
from tests.test_brain_coverage_group_generation import mixed
from tests.test_brain_material import material, send
from tests.test_brain_material_coverage_choices import (
    ACCOUNT,
    EARLIER,
    OMITTED,
    REQUEST,
    check,
    proof,
    record_row,
)
from tests.test_brain_material_purpose import (
    PurposeModel,
    item,
    open_account,
    public_record,
    routed,
)
from tests.test_brain_source_support_verifiers import (
    RawJudge,
    coverage,
    disposition,
    proposal,
    source_catalogue,
    verdict,
)


def portion(*, status="outside_scope", candidates=(), records=(), bounds=None):
    selected = {"extent": "whole_source"} if bounds is None else {
        "extent": "exact_subrange", "start": bounds[0], "end": bounds[1]}
    return {**selected, "status": status, "record_ids": list(records),
            "candidate_ids": list(candidates),
            "reason": "The fixture independently declares this portion's disposition."}


def account_group(*parts, context=()):
    return {"content_purpose": "account", "reason": "Explicit original-account judgment.",
            "account_portions": list(parts), "non_account_portions": list(context)}


def groups(references, *, selected=None, state="complete"):
    return {"state": state, "reason": "Original content and represented scope were compared.",
            "source_groups": {identity: deepcopy((selected or {}).get(identity, account_group(
                portion()))) for identity in references}}


def native_reply(references, rows, judgment, *, roles=None, allowed=None):
    """Author the fresh wire directly, retaining explicit verdicts and exact ranges."""
    native = deepcopy(rows)
    for row in native:
        account = row["account_check"]
        account.pop("source_ids")
        selected = dict.fromkeys((allowed or {}).get(row["candidate_id"], references))
        for source in account.pop("source_checks"):
            identity = source.pop("source_id")
            source.pop("supplies_account_content")
            source["supports_statement"] = source.pop("supports_proposal")
            source["support_spans"] = [{"extent": "exact_subrange", **span}
                                       for span in source["support_spans"]]
            selected[identity] = source
        account["source_selections"] = selected
    return {"source_readings": {identity: {
        "content_role": (roles or {}).get(identity, "reported_matter_account"),
        "reason": "Independent original-source reading explicitly authored by the fixture."}
        for identity in references}, "verdicts": native, "coverage": deepcopy(judgment)}


def raw_judge(*outputs):
    return RawJudge(outputs, transport=False)


def scripted_public_review(payload, *, outcome):
    """Author an explicit whole-unit verdict under the actually offered contract."""
    unit, = payload["units"]
    assert not unit["questions"] and not unit["next_work"]
    return {"accepted_units": [{
        "request_index": unit["request_index"], "block_checks": [{
            "block_id": block["id"], "requires_legal_support": False, "verdict": "accept",
            "reason": "Explicit fixture judgment: the original account and limits are relevant."}
            for block in unit["blocks"]], "proposal_checks": [], "work_check": {
                "existing_id": unit["work"]["existing_id"], "scope_preserved": True,
                "verdict": "accept", "reason": "The scoped review retains its declared identity."},
        "progress_checks": [{
            "target_id": update["target_id"], "status": update["status"],
            "scope_preserved": True, "result_supported": True, "verdict": "accept",
            "reason": "The fixture independently declares this scoped review complete."}
            for update in unit["progress_updates"]], "question_resolutions": [],
        "record_check": {"outcome": outcome,
                         "reason": "The fixture declares this outcome independently of effects."},
        "reason": "Explicit semantic verdict for mechanical save and replay qualification.",
    }], "rejected_units": []}


@pytest.mark.parametrize("support", (OMITTED, None), ids=("default", "explicit-none"))
def test_default_material_generation_stays_flat_without_new_markers_or_calls(support):
    latest = "The consignee cannot identify the final keeper."
    references, _ = source_catalogue(latest)
    candidate = proposal("material", latest)
    judgment = coverage(references, dispositions=[disposition(
        "L1", references["L1"], status="represented", candidate_ids=("D1",))])
    model = RawJudge([{"verdicts": [verdict("material", references["L1"])],
                       "coverage": judgment}])
    result, assessed, _, _ = check(
        model, latest=latest, earlier=(), candidates=(candidate,), support=support)
    assert result.details == (candidate,) and assessed["state"] == "complete"
    assert len(model.calls) == 1
    call = model.calls[0]
    assert "coverage_group_contract" not in call["payload"]
    assert "coverage_extent_contract" not in call["payload"]
    assert "source_groups" not in call["schema"]["properties"]["coverage"]["properties"]
    require_schema(call["output"], on_the_wire(call["schema"]))


@pytest.mark.parametrize("explicit_false", (False, True), ids=("omitted", "explicit-false"))
def test_material_private_schema_keeps_extent_only_mode_available(explicit_false):
    references, _ = source_catalogue(ACCOUNT)
    kwargs = {"native_coverage_groups": False} if explicit_false else {}
    offered = owner._schema(
        (), tuple(references), coverage_ids=tuple(references), source_references=references,
        coverage_candidate_ids=("D1",), native_coverage_extents=True, wire=True, **kwargs)
    assert offered["properties"]["coverage"] == record.coverage_schema(
        tuple(references), source_references=references, candidate_ids=("D1",),
        native_extents=True)
    assert "source_groups" not in offered["properties"]["coverage"]["properties"]


def test_explicit_empty_owned_proof_activates_raw_groups_in_one_existing_review_call():
    references, _ = source_catalogue(ACCOUNT)
    candidate = proposal("material", ACCOUNT)
    judgment = groups(references, selected={"L1": account_group(portion(
        status="represented", candidates=("D1",)))})
    reply = native_reply(references, [verdict("material", references["L1"])], judgment)
    model = raw_judge(reply, reply)
    state = {}
    result, assessed, _, _ = check(
        model, latest=ACCOUNT, earlier=(), candidates=(candidate,), support={}, state=state)
    assert result.details == (candidate,) and assessed["state"] == "complete"
    assert len(model.calls) == 1
    call = model.calls[0]
    assert call["payload"]["coverage_group_contract"] == record.COVERAGE_GROUP_CONTRACT
    assert call["payload"]["coverage_extent_contract"] == record.COVERAGE_EXTENT_CONTRACT
    assert call["payload"]["coverage_representation_options"] == {
        "L1": {"record_ids": [], "candidate_ids": ["D1"]}}
    assert on_the_wire(call["schema"]["properties"]["coverage"]) == on_the_wire(
        record.coverage_schema(
            tuple(references), source_references=references, candidate_ids=("D1",),
            representation_options=call["payload"]["coverage_representation_options"],
            native_extents=True, native_groups=True))
    require_schema(reply, on_the_wire(call["schema"]))
    expected = record.checked_coverage(
        coverage(references, dispositions=[disposition(
            "L1", references["L1"], status="represented", candidate_ids=("D1",))]),
        tuple(references), source_references=references, candidate_ids=("D1",),
        admitted_candidate_ids=("D1",), candidate_support=state["cache"].decisions)
    assert assessed["selection_contract"] == expected["selection_contract"]
    assert assessed["source_checks"][0]["substantive_spans"] == (
        expected["source_checks"][0]["substantive_spans"])
    assert assessed["dispositions"][0]["quoted"] == ACCOUNT
    assert "source_groups" not in assessed and "extent" not in repr(assessed)
    assert "coverage_group_contract" not in state["cache"].context


def test_grouped_strict_wire_schema_is_budgeted_before_material_model_dispatch():
    references, _ = source_catalogue(ACCOUNT)
    candidate = proposal("material", ACCOUNT)
    judgment = groups(references, selected={"L1": account_group(portion(
        status="represented", candidates=("D1",)))})
    reply = native_reply(references, [verdict("material", references["L1"])], judgment)
    probe = raw_judge(reply, reply)
    check(probe, latest=ACCOUNT, earlier=(), candidates=(candidate,), support={})
    call = probe.calls[0]
    assert "source_groups" in call["schema"]["properties"]["coverage"]["properties"]
    prompt_only_budget = estimate_tokens(call["prompt"].system + call["prompt"].user) + (
        call["max_tokens"])
    bounded = raw_judge(reply)
    bounded.context_budget = lambda tier: prompt_only_budget
    with pytest.raises(ContextOverflow):
        check(bounded, latest=ACCOUNT, earlier=(), candidates=(candidate,), support={})
    assert bounded.calls == []


@pytest.mark.parametrize("historical", (False, True), ids=("current", "historical"))
def test_original_saved_support_alias_remains_eligible_without_new_candidates(historical):
    references, _ = source_catalogue(REQUEST, earlier=EARLIER)
    row = record_row()
    support = {row["id"]: proof(references["P1S1"])}
    judgment = groups(references, selected={
        "P1S1": account_group(portion(status="represented", records=(row["id"],))),
        "L1": {"content_purpose": "non_account", "reason": "Explicit review authority."}})
    reply = native_reply(references, [], judgment, roles={"L1": "work_instruction"})
    model = raw_judge(reply, reply)
    before = deepcopy((row, support))
    result, assessed, _, _ = check(
        model, records=() if historical else (row,), history=(row,) if historical else (),
        support=support)
    assert result.details == () and assessed["state"] == "complete"
    assert len(model.calls) == 1 and (row, support) == before
    payload = model.calls[0]["payload"]
    assert payload["coverage_representation_options"] == {
        "P1S1": {"record_ids": [row["id"]], "candidate_ids": []},
        "L1": {"record_ids": [], "candidate_ids": []}}
    assert "coverage_record_support" not in payload and "original-local-source" not in repr(payload)
    require_schema(reply, on_the_wire(model.calls[0]["schema"]))
    assert assessed["dispositions"][0]["quoted"] == ACCOUNT
    assert assessed["dispositions"][1]["status"] == "non_account"


def test_pending_choice_cannot_replace_checked_support_for_different_original_words():
    first = "The consignee reports receipt of the north crate."
    latest = first + " The final keeper of the south crate remains unidentified."
    references, _ = source_catalogue(latest)
    candidate = proposal("material", first)
    bad = groups(references, selected={"L2": account_group(portion(
        status="represented", candidates=("D1",)))})
    good = groups(references, state="partial", selected={"L2": account_group(portion(
        status="missing"))})
    first_reply = native_reply(references, [verdict("material", references["L1"])], bad)
    second_reply = native_reply(references, [], good)
    model = raw_judge(first_reply, second_reply)
    result, assessed, _, _ = check(
        model, latest=latest, earlier=(), candidates=(candidate,), support={})
    assert result.details == (candidate,) and assessed["state"] == "partial"
    assert assessed["missing_source_ids"] == ["L2"] and len(model.calls) == 2
    assert model.calls[0]["payload"]["coverage_representation_options"]["L2"] == {
        "record_ids": [], "candidate_ids": ["D1"]}
    assert model.calls[1]["payload"]["coverage_representation_options"]["L2"] == {
        "record_ids": [], "candidate_ids": []}
    assert model.calls[1]["payload"]["candidates"] == []
    require_schema(first_reply, on_the_wire(model.calls[0]["schema"]))
    require_schema(second_reply, on_the_wire(model.calls[1]["schema"]))


def test_saved_record_choice_still_requires_support_overlapping_selected_account_portion():
    first = "The north crate was sealed,"
    latest = first + " while its receipt date remains uncertain."
    references, _ = source_catalogue(latest)
    split = len(first)
    row = record_row(words=first, turn="current")
    support = {row["id"]: proof(references["L1"], portions=[{"start": 0, "end": split}])}
    bad = groups(references, selected={"L1": account_group(
        portion(bounds=(0, split)), portion(status="represented", records=(row["id"],),
                                           bounds=(split, len(latest))))})
    good = deepcopy(bad)
    good["state"] = "partial"
    good["source_groups"]["L1"]["account_portions"][1].update(status="missing", record_ids=[])
    model = raw_judge(native_reply(references, [], bad), native_reply(references, [], good))
    _, assessed, _, _ = check(model, latest=latest, earlier=(), records=(row,), support=support)
    assert assessed["state"] == "partial" and assessed["missing_source_ids"] == ["L1"]
    assert len(model.calls) == 2
    require_schema(model.calls[0]["output"], on_the_wire(model.calls[0]["schema"]))
    assert assessed["dispositions"][1]["quoted"] == latest[split:]


def test_mixed_framing_and_account_use_exact_subranges_without_purpose_repair():
    latest = "Please review this account: the consignee reports the crate remained sealed."
    start = latest.index("the consignee")
    references, treatments = source_catalogue(latest, roles={"L1": "mixed"})
    assert tuple(references) == ("L1",)
    candidate = proposal("material", latest[start:])
    judgment = groups(references, selected={"L1": account_group(
        portion(status="represented", candidates=("D1",), bounds=(start, len(latest))),
        context=({"extent": "exact_subrange", "start": 0, "end": start,
                  "reason": "The original framing supplies authority only."},))})
    reply = native_reply(references, [verdict(
        "material", references["L1"], bounds=(start, len(latest)))], judgment,
        roles={"L1": "mixed"})
    model = raw_judge(reply, reply)
    result, assessed, _, _ = check(
        model, latest=latest, earlier=(), candidates=(candidate,), support={},
        treatments=treatments)
    assert result.details == (candidate,) and assessed["state"] == "complete"
    assert len(model.calls) == 1
    assert [(row["status"], row["quoted"]) for row in assessed["dispositions"]] == [
        ("represented", latest[start:]), ("non_account", latest[:start])]


@pytest.mark.parametrize("fault", ("foreign_source", "omitted_source", "foreign_record",
                                    "purpose_fields", "account_context_overlap"))
def test_invalid_group_retries_coverage_without_rechecking_valid_candidate_peer(fault):
    references, _ = source_catalogue(ACCOUNT)
    candidate = proposal("material", ACCOUNT)
    good = groups(references, selected={"L1": account_group(portion(
        status="represented", candidates=("D1",)))})
    bad = deepcopy(good)
    if fault == "foreign_source":
        bad["source_groups"]["foreign"] = bad["source_groups"].pop("L1")
    elif fault == "omitted_source":
        bad["source_groups"].clear()
    elif fault == "foreign_record":
        bad["source_groups"]["L1"]["account_portions"][0].update(
            record_ids=["other-matter:record"], candidate_ids=[])
    elif fault == "purpose_fields":
        bad["source_groups"]["L1"]["content_purpose"] = "non_account"
    else:
        bad["source_groups"]["L1"]["non_account_portions"] = [
            {"extent": "whole_source", "reason": "A deliberately contradictory purpose choice."}]
    first = native_reply(references, [verdict("material", references["L1"])], bad)
    second = native_reply(references, [], good)
    model = raw_judge(first, second)
    result, assessed, _, _ = check(
        model, latest=ACCOUNT, earlier=(), candidates=(candidate,), support={})
    assert result.details == (candidate,) and assessed["state"] == "complete"
    assert len(model.calls) == 2
    correction = model.calls[1]["payload"]
    assert correction["candidates"] == []
    assert [row["candidate_id"] for row in correction["retained_candidate_context"]] == ["D1"]
    assert "$coverage" in correction["validation_issue"]
    require_schema(second, on_the_wire(model.calls[1]["schema"]))
    if fault == "account_context_overlap":
        require_schema(first, on_the_wire(model.calls[0]["schema"]))
    else:
        with pytest.raises(SchemaViolation):
            require_schema(first, on_the_wire(model.calls[0]["schema"]))


def transport_payload(references):
    return {"coverage_group_contract": record.COVERAGE_GROUP_CONTRACT,
            "coverage_extent_contract": record.COVERAGE_EXTENT_CONTRACT,
            "coverage_source_ids": list(references), "source_treatments": deepcopy(references)}


def transport_row():
    references, _ = source_catalogue(ACCOUNT + " " + REQUEST)
    flat = coverage(references, purposes={"L2": "non_account"}, dispositions=[
        disposition("L1", references["L1"], status="represented", candidate_ids=("D1",)),
        disposition("L2", references["L2"], status="non_account")])
    return references, {"verdicts": [], "coverage": flat}


def test_fixture_transport_preserves_explicit_ranges_choices_and_both_authored_reasons():
    references, authored = transport_row()
    payload = transport_payload(references)
    before = deepcopy((payload, authored))
    output = fresh_review_reply(payload, authored)
    group = output["coverage"]["source_groups"]["L1"]
    assert group["account_portions"][0]["candidate_ids"] == ["D1"]
    assert group["account_portions"][0]["extent"] == "whole_source"
    expected_reason = (authored["coverage"]["source_checks"][1]["reason"] + "\n"
                       + authored["coverage"]["dispositions"][1]["reason"])
    assert output["coverage"]["source_groups"]["L2"] == {
        "content_purpose": "non_account", "reason": expected_reason}
    require_schema(output["coverage"], record.coverage_schema(
        tuple(references), source_references=references, candidate_ids=("D1",),
        native_extents=True, native_groups=True))
    assert (payload, authored) == before


@pytest.mark.parametrize("marker", ("absent", "unknown", "extent-only"))
def test_fixture_group_transport_requires_exact_marker_and_preserves_extent_only_mode(marker):
    references, authored = transport_row()
    payload = transport_payload(references)
    if marker in {"absent", "extent-only"}:
        payload.pop("coverage_group_contract")
    else:
        payload["coverage_group_contract"] = "coverage_source_groups_future"
    if marker == "absent":
        payload.pop("coverage_extent_contract")
    output = fresh_review_reply(payload, authored)
    if marker == "absent":
        assert output == authored
    else:
        expected = deepcopy(payload)
        expected.pop("coverage_group_contract", None)
        assert output == fresh_review_reply(expected, authored)
    assert "source_groups" not in output["coverage"]


@pytest.mark.parametrize("fault", ("contradictory_purpose", "absent_account_disposition",
                                    "duplicate_check", "foreign_source", "unmatched_range",
                                    "account_context_overlap", "extra_field", "unsupported_ids"))
def test_fixture_transport_leaves_incomplete_or_contradictory_flat_judgments_unrepaired(fault):
    references, authored = transport_row()
    bad = authored["coverage"]
    if fault == "contradictory_purpose":
        bad["dispositions"][0].update(status="non_account", candidate_ids=[])
    elif fault == "absent_account_disposition":
        bad["dispositions"].pop(0)
    elif fault == "duplicate_check":
        bad["source_checks"].append(deepcopy(bad["source_checks"][0]))
    elif fault == "foreign_source":
        bad["dispositions"][0]["source_id"] = "unowned-source"
    elif fault == "unmatched_range":
        bad["source_checks"][0]["substantive_spans"][0]["end"] -= 1
    elif fault == "account_context_overlap":
        overlap = deepcopy(bad["dispositions"][0])
        overlap.update(status="non_account", candidate_ids=[])
        bad["dispositions"].append(overlap)
    elif fault == "extra_field":
        bad["dispositions"][0]["copied_words"] = ACCOUNT
    else:
        bad["dispositions"][1]["record_ids"] = ["unproved-record"]
    payload = transport_payload(references)
    expected_payload = deepcopy(payload)
    expected_payload.pop("coverage_group_contract")
    before = deepcopy((payload, authored))
    assert fresh_review_reply(payload, authored) == fresh_review_reply(expected_payload, authored)
    assert (payload, authored) == before


@pytest.mark.parametrize("purpose", ("non_account", "unresolved"))
def test_fixture_transport_preserves_whole_non_account_purpose_without_redundant_disposition(
        purpose):
    references, authored = transport_row()
    source = authored["coverage"]["source_checks"][1]
    source["content_purpose"] = purpose
    authored["coverage"]["dispositions"].pop()
    if purpose == "unresolved":
        authored["coverage"]["state"] = "partial"
    before = deepcopy(authored)
    output = fresh_review_reply(transport_payload(references), authored)
    assert output["coverage"]["source_groups"]["L2"] == {
        "content_purpose": purpose, "reason": source["reason"]}
    assert output["coverage"]["source_groups"]["L1"]["account_portions"][0][
        "candidate_ids"] == ["D1"]
    require_schema(output["coverage"], record.coverage_schema(
        tuple(references), source_references=references, candidate_ids=("D1",),
        native_extents=True, native_groups=True))
    assert authored == before


def test_fixture_transport_preserves_overlapping_account_ranges_and_authored_duplicates():
    grouped, flat, references = mixed()
    flat["dispositions"].insert(1, deepcopy(flat["dispositions"][0]))
    flat["source_checks"][0]["substantive_spans"].insert(
        1, deepcopy(flat["source_checks"][0]["substantive_spans"][0]))
    grouped["source_groups"]["L1"]["account_portions"].insert(
        1, deepcopy(grouped["source_groups"]["L1"]["account_portions"][0]))
    assert fresh_review_reply(transport_payload(references), {"coverage": flat}) == {
        "coverage": grouped}


def test_fixture_transport_does_not_turn_an_offered_candidate_into_admitted_support():
    references, authored = transport_row()
    output = fresh_review_reply(transport_payload(references), authored)
    assert output["coverage"]["source_groups"]["L1"]["account_portions"][0][
        "candidate_ids"] == ["D1"]
    with pytest.raises(SchemaViolation, match="not actually admitted"):
        record.checked_coverage(
            output["coverage"], tuple(references), source_references=references,
            candidate_ids=("D1",), admitted_candidate_ids=(), record_support={},
            native_extents=True, native_groups=True)


def test_fixture_transport_never_repairs_an_already_authored_invalid_group():
    references, _ = source_catalogue(ACCOUNT)
    authored = {"coverage": groups(references)}
    authored["coverage"]["source_groups"]["L1"]["source_id"] = "foreign-source"
    assert fresh_review_reply(transport_payload(references), authored) == authored


def test_material_fixture_double_transport_keeps_independent_original_readings_and_groups():
    references, authored = transport_row()
    authored["verdicts"] = [verdict("material", references["L1"])]
    payload = {**transport_payload(references),
               "review_selection_contract": record.REVIEW_SELECTION_CONTRACT,
               "material_source_selection_contract": "ordered_original_account_support_v1",
               "candidates": [{"candidate_id": "D1", "allowed_account_source_ids": ["L1", "L2"]}]}
    before = deepcopy((payload, authored))
    first = fresh_review_reply(payload, authored)
    assert first["source_readings"]["L1"]["content_role"] == "reported_matter_account"
    assert first["source_readings"]["L2"]["content_role"] == "work_instruction"
    assert fresh_review_reply(payload, first) == first
    assert (payload, authored) == before


@pytest.mark.parametrize("reading", (None, {}, {"content_role": "work_instruction"}))
def test_material_fixture_preserves_malformed_existing_independent_readings_for_owner_rejection(
        reading):
    references, authored = transport_row()
    authored["verdicts"] = [verdict("material", references["L1"])]
    authored["source_readings"] = deepcopy(reading)
    payload = {**transport_payload(references),
               "review_selection_contract": record.REVIEW_SELECTION_CONTRACT,
               "material_source_selection_contract": "ordered_original_account_support_v1",
               "candidates": [{"candidate_id": "D1", "allowed_account_source_ids": ["L1", "L2"]}]}
    output = fresh_review_reply(payload, authored)
    assert output["source_readings"] == reading
    offered = owner._schema(
        ("D1",), tuple(references), coverage_ids=tuple(references), source_references=references,
        coverage_candidate_ids=("D1",), wire=True,
        native_coverage_extents=True, native_coverage_groups=True)
    with pytest.raises(SchemaViolation):
        require_schema(output, on_the_wire(offered))


class PublicGroupsModel(PurposeModel):
    """Script raw material groups while ordinary fixtures own other stage judgments."""

    def __init__(self):
        seed = routed(ACCOUNT, opening=True,
                      candidates=[material("circumstance", ACCOUNT, ACCOUNT, placement="matter")],
                      items=[item(ACCOUNT, ACCOUNT, purposes=("account_contribution",),
                                  intent="contribution", opening=True)])
        seed["opening"]["summary"] = ACCOUNT
        review = routed(REQUEST, record_disposition="review_no_change",
                        source_purposes={REQUEST: "non_account"}, items=[item(
                            REQUEST, ACCOUNT, purposes=("interpretation_review",),
                            record_requirement={
                                "kind": "review", "operation": "none",
                                "target_ids": ["group-original:material:1"],
                                "success_condition": (
                                    "The saved account retains its uncertainty.")})])
        review["_response_expressions"] = {0: {
            "operator": "source_account", "source_ids": [],
            "record_ids": ["group-original:material:1"], "focus": "none"}}
        super().__init__([seed, review])
        self.group_calls = []

    def context_budget(self, tier):
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        if prompt.operation == "verify_continuation":
            payload = json.loads(prompt.user)
            data = scripted_public_review(
                payload, outcome="no_change_justified"
                if self.current_record_disposition == "review_no_change" else "not_requested")
            require_schema(data, schema)
            self.seen.append((prompt.operation, deepcopy(payload)))
            return ModelResult(text=None, data=data, tier=tier, provider="offline-raw",
                               model="scripted-public-group-review", usage=Usage(0, 0, 0),
                               latency_ms=0, completion=Completion.COMPLETE)
        if prompt.operation != "verify_material_grounding":
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            require_schema(result.data, schema)
            return result
        payload = json.loads(prompt.user)
        references = payload["source_treatments"]
        original = "".join(row["text"] for row in payload["latest_message_spans"]) == ACCOUNT
        rows = []
        for candidate in payload["candidates"]:
            row = verdict("material", references["L1"])
            row["candidate_id"] = candidate["candidate_id"]
            rows.append(row)
        selected = ({"L1": account_group(portion(status="represented", candidates=("D1",)))}
                    if original else {
                        "P1S1": account_group(portion(
                            status="represented", records=("group-original:material:1",))),
                        "L1": {"content_purpose": "non_account",
                               "reason": (
                                   "The review instruction supplies no replacement account.")}})
        data = native_reply(references, rows, groups(references, selected=selected),
                            roles={} if original else {"L1": "work_instruction"},
                            allowed={row["candidate_id"]: row["allowed_account_source_ids"]
                                     for row in payload["candidates"]})
        self.seen.append((prompt.operation, deepcopy(payload)))
        self.group_calls.append({"payload": deepcopy(payload), "schema": deepcopy(schema),
                                 "output": deepcopy(data)})
        return ModelResult(text=None, data=data, tier=tier, provider="offline-raw",
                           model="scripted-material-groups", usage=Usage(0, 0, 0), latency_ms=0,
                           completion=Completion.COMPLETE)


def test_public_raw_groups_capture_original_support_and_no_change_review_replays_without_calls(
        client, wired, monkeypatch):
    model = PublicGroupsModel()
    supplied = []
    original_verify = turn.verify_material_grounding

    def observed_verify(*args, **kwargs):
        supplied.append(deepcopy(kwargs["coverage_record_support"]))
        return original_verify(*args, **kwargs)

    monkeypatch.setattr(turn, "verify_material_grounding", observed_verify)
    opened = open_account(client, wired, monkeypatch, model, ACCOUNT, turn_id="group-original")
    assert opened["metrics"]["llm_calls"] == 8, [
        row["phase"] for row in opened["metrics"]["recovery"]["events"]]
    assert supplied == [{}] and len(model.group_calls) == 1
    first_saved = deepcopy(wired.store.load(opened["matter_id"]))
    before_record = public_record(client, opened["matter_id"])
    assert [row["statement"] for row in before_record["rows"]] == [ACCOUNT]
    first_execution = first_saved.brain_chat[0]["response"]["material_coverage"]["execution"]
    first_binding, = first_execution["coverage_application"]["bindings"]
    assert first_binding["review"]["verdict"] == "accept"
    original_check, = first_binding["review"]["account_check"]["source_checks"]
    assert original_check["source_id"] == "L1"
    assert original_check["support_spans"] == [{"start": 0, "end": len(ACCOUNT)}]
    assert first_saved.brain_chat[0]["response"]["material_coverage"][
        "source_treatments"]["L1"]["quoted"] == ACCOUNT

    response = send(client, REQUEST, "group-review", opened=opened)
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["metrics"]["llm_calls"] == 8
    assert len(model.group_calls) == 2 and len(supplied) == 2
    assert set(supplied[1]) == {"group-original:material:1"}
    assert supplied[1]["group-original:material:1"]["review"] == first_binding["review"]
    assert supplied[1]["group-original:material:1"]["source_references"] == {
        "L1": {"turn_id": "group-original", "role": "advocate", "quoted": ACCOUNT}}
    for call in model.group_calls:
        assert call["payload"]["coverage_group_contract"] == record.COVERAGE_GROUP_CONTRACT
        assert "coverage_record_support" not in call["payload"]
        assert on_the_wire(call["schema"]["properties"]["coverage"]) == on_the_wire(
            record.coverage_schema(
                tuple(call["payload"]["coverage_source_ids"]),
                source_references=call["payload"]["source_treatments"],
                record_ids=tuple(call["payload"]["coverage_record_ids"]),
                candidate_ids=tuple(call["payload"]["coverage_candidate_ids"]),
                representation_options=call["payload"]["coverage_representation_options"],
                native_extents=True, native_groups=True))
        require_schema(call["output"], on_the_wire(call["schema"]))
    assert model.group_calls[1]["payload"]["candidates"] == []
    assert model.group_calls[1]["payload"]["coverage_representation_options"]["P1S1"] == {
        "record_ids": ["group-original:material:1"], "candidate_ids": []}
    saved = wired.store.load(opened["matter_id"])
    assert saved.brain_chat[0] == first_saved.brain_chat[0]
    assert [row["message"] for row in saved.brain_chat] == [ACCOUNT, REQUEST]
    assert public_record(client, saved.id) == before_record
    assert saved.brain_chat[-1]["elements"] == answer["elements"]
    assert answer["continuation"]["units"][0]["record_outcome"]["status"] == "review_no_change"
    execution = answer["material_coverage"]["execution"]
    assert execution["coverage_application_contract"] == "owned_coverage_application_v2"
    assessment = execution["coverage_application"]["pre_application_assessments"]["detail_review"]
    assert assessment["selection_contract"] == record.COVERAGE_SELECTION_CONTRACT
    assert "source_groups" not in assessment and "extent" not in repr(assessment)
    assert answer["metrics"]["recovery"]["dispatched_calls"] == 0
    calls = len(model.seen)

    replay = send(client, REQUEST, "group-review", opened=opened)

    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] and replay.json()["metrics"]["llm_calls"] == 0
    assert replay.json()["elements"] == answer["elements"]
    assert len(model.seen) == calls and wired.store.load(saved.id) == saved
