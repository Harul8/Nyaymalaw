"""Review ownership/coverage wiring with offline fixtures, not semantic accuracy."""
from copy import deepcopy
import json

import pytest

from nm.core_engine import response_authorities
from nm.core_engine.answer_sources import build, select
from nm.core_engine.research import accept as accept_plan, retrieve
from nm.core_engine.response_review import (
    CONTRACT, LEGACY_CONTRACT, MAX_OUTPUT, SCHEMA, _digest,
    review as review_checked, validate as validate_checked,
)
from nm.core_engine.response_writer import LEGACY_CONTRACT as WRITER_LEGACY_CONTRACT, accept as accept_draft
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ContextOverflow, ModelError, ModelResult, SchemaViolation, Tier, Usage
from tests.test_core_answer_sources import fixture as legal_fixture
from tests.test_core_understanding import context

pytestmark = pytest.mark.class_a


class Model:
    def __init__(self, proposal, *, budget=100_000, completion=Completion.COMPLETE):
        self.proposal, self.budget, self.completion = proposal, budget, completion
        self.calls = []

    def context_budget(self, tier): return self.budget

    def structured(self, prompt, schema, tier, **kwargs):
        self.calls.append((prompt, schema, tier, kwargs))
        return ModelResult(None, deepcopy(self.proposal), tier, "synthetic", "fixture",
                           Usage(1, 1, 0), 0, completion=self.completion)


def review(model, context, research_record, sources, draft, execution=None):
    # Existing fixture tests exercise the current public boundary with owned,
    # offline authority evidence; no provider or corpus lookup is configured.
    authority = response_authorities.check(context, research_record, sources, draft)
    return review_checked(model, context, research_record, sources, draft, execution,
                          authority_evidence=authority)


def validate(record, context, research_record, sources, draft, execution=None):
    authority = response_authorities.check(context, research_record, sources, draft)
    return validate_checked(record, context, research_record, sources, draft, execution,
                            authority_evidence=authority)


def ref(row):
    return {"source_id": row.get("id", row.get("source_id")), "quote": row["text"]}


def setup(*, legal=False, text="Hello.", history=None, count=1):
    if legal:
        ctx, record = legal_fixture(history=history)
    else:
        ctx = context(text, history)
        record = retrieve(accept_plan({"work": []}, ctx), None, ctx)
    sources = build(ctx, record)
    proposal = {"units": [{"kind": "greeting", "text": "Hello. How can I help?",
        "addresses": [{"source_id": ctx["latest"]["source_id"]}], "uses": []} for _ in range(count)]}
    return ctx, record, sources, accept_draft(proposal, ctx, sources)


def positive(draft, *, requests=None):
    return {"verdict": "accept", "units": [{"unit_id": unit["id"],
        "verdict": "supported", "reason": "Fixture verdict for review wiring."}
        for unit in draft["units"]], "request_coverage": requests or [], "findings": []}


def request(ctx, draft, **changes):
    return {"request": ref(ctx["latest"]), "disposition": "addressed",
        "unit_ids": [draft["units"][0]["id"]], "reason": "Fixture coverage judgment.", **changes}


def negative(draft, ctx, *, category="effect", sources=None):
    data = positive(draft)
    data["verdict"] = "reject"
    data["units"][0]["verdict"] = "rejected"
    data["findings"] = [{"category": category, "unit_ids": [draft["units"][0]["id"]],
        "sources": sources if sources is not None else [ref(ctx["latest"])],
        "mismatch": "The model states an executed effect; no model-authored effect claim is permitted."}]
    return data


def test_greeting_accepts_without_inventing_request_or_effect():
    args = setup()
    model = Model(positive(args[-1]))
    result = review(model, *args)
    assert result["contract"] == CONTRACT and result["accepted"] is True
    assert result["proposal"]["request_coverage"] == []
    assert validate(result, *args) == result and len(model.calls) == 1


def test_supported_attributed_summary_needs_no_fresh_write_receipt():
    ctx, record, sources, _ = setup(text="The meeting was on Tuesday. Summarise that.")
    original = {"source_id": ctx["latest"]["source_id"], "source_kind": "account"}
    draft = accept_draft({"units": [{"kind": "account",
        "text": "You report that the meeting was on Tuesday.",
        "addresses": [{"source_id": ctx["latest"]["source_id"]}],
        "uses": [original]}]}, ctx, sources)
    data = positive(draft, requests=[request(ctx, draft,
        request={"source_id": ctx["latest"]["source_id"], "quote": "Summarise that."})])
    result = review(Model(data), ctx, record, sources, draft,
                    {"operations": [], "record_changes": [], "persistence": "not_yet_committed"})
    assert result["accepted"]


def test_whole_originals_adjacent_legal_text_and_execution_are_separate_inputs():
    history = [{"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
        "record_role": "original_account", "text": "The allegation is disputed. No external contact."},
        {"source_id": "t1:nm", "turn_id": "t1", "speaker": "nm",
         "record_role": "nm_interpretation", "text": "Earlier unverified NM interpretation."}]
    ctx, record, sources, draft = setup(legal=True, history=history)
    ctx["current_records"] = {"reported_document": "not supplied"}
    ctx["saved_work"] = [{"id": "earlier", "state": "pending"}]
    execution = {"contract": "core_read_only_execution_v1", "operations": [],
                 "record_changes": [], "external_actions": [], "searches": [],
                 "persistence": "not_yet_committed"}
    model = Model(positive(draft, requests=[request(ctx, draft)]))
    reviewed = review(model, ctx, record, sources, draft, execution)
    prompt, schema, tier, kwargs = model.calls[0]
    payload = json.loads(prompt.user)
    assert payload["original_context"] == ctx
    assert payload["owned_execution_evidence"] == execution
    shown = payload["complete_draft_proposal"]["units"]
    assert [row["text"] for row in shown] == [row["text"] for row in draft["units"]]
    assert [select(ref, sources) for ref in shown[0]["addresses"]] == draft["units"][0]["addresses"]
    assert "proposal" not in payload["complete_draft_proposal"]  # No duplicate draft text.
    assert payload["research_proposal_and_results"]["plan_proposal"] == record["plan"]["proposal"]
    assert {s["id"] for s in payload["legal_sources"]["passages"]} == {
        s["id"] for s in sources.values() if s["kind"] in {"provision", "judgment"}}
    assert any("Court rejected" in s["text"] for s in payload["legal_sources"]["passages"])
    assert all(s["kind"] in {"provision", "judgment"} for s in payload["legal_sources"]["passages"])
    assert tier is Tier.JUDGE and schema == SCHEMA and kwargs == {"max_tokens": MAX_OUTPUT}
    assert prompt.operation == "core_response_review"
    assert validate(reviewed, ctx, record, sources, draft, execution) == reviewed


def test_review_selectors_reconstruct_legacy_full_and_short_sources_without_repeated_proof():
    from nm.core_engine.response_review import _draft_presentation

    ctx, record, sources, _ = setup(legal=True)
    legal = next(row for row in sources.values() if row["kind"] == "judgment")
    proposal = {"units": [{"kind": "analysis", "text": "The reported position remains conditional.",
        "addresses": [{"source_id": ctx["latest"]["source_id"], "quote": None}],
        "uses": [{"source_id": legal["id"], "quote": None, "role": "party_submission",
            "speaker": "the submitting party", "treatment": "qualified",
            "treatment_source": {"source_id": legal["id"], "quote": legal["text"][:12]}}]}]}
    draft = accept_draft(proposal, ctx, sources, contract=WRITER_LEGACY_CONTRACT)
    originals = deepcopy((draft, sources))
    shown = _draft_presentation(draft, sources)
    unit, actual = shown["units"][0], draft["units"][0]
    assert (draft, sources) == originals
    assert (unit["id"], unit["kind"], unit["text"]) == (actual["id"], actual["kind"], actual["text"])
    assert unit["uses"][0]["quote"] is None
    assert unit["uses"][0]["treatment_source"]["quote"] == legal["text"][:12]
    for projected, original in zip(unit["uses"], actual["uses"]):
        resolved = select({k: projected[k] for k in ("source_id", "quote")}, sources)
        assert resolved["text"] == original["text"]
        assert (resolved["start"], resolved["end"]) == (original["start"], original["end"])
        assert all(projected[k] == original[k] for k in ("role", "speaker", "treatment"))
        assert select(projected["treatment_source"], sources) == original["treatment_source"]
    model = Model(positive(draft))
    result = review(model, ctx, record, sources, draft)
    assert json.loads(model.calls[0][0].user)["complete_draft_proposal"] == shown
    assert validate(result, ctx, record, sources, draft) == result


@pytest.mark.parametrize("damage", ["omitted", "duplicate", "unknown"])
def test_every_draft_unit_needs_one_known_review_disposition(damage):
    args = setup(count=2)
    data = positive(args[-1])
    if damage == "omitted": data["units"].pop()
    elif damage == "duplicate": data["units"][1] = deepcopy(data["units"][0])
    else: data["units"][1]["unit_id"] = "another-turn:b1"
    with pytest.raises(SchemaViolation): review(Model(data), *args)


def test_original_request_omitted_from_plan_can_be_explicitly_flagged():
    args = setup(text="Summarise the account and identify what remains unknown.")
    ctx, _, _, draft = args
    omitted = request(ctx, draft, disposition="missing", unit_ids=[])
    data = positive(draft, requests=[omitted])
    data.update(verdict="reject", findings=[{"category": "omission", "unit_ids": [],
        "sources": [{"source_id": ctx["latest"]["source_id"], "quote": "what remains unknown"}],
        "mismatch": "The requested uncertainty assessment is absent from the reply."}])
    result = review(Model(data), *args)
    assert result["accepted"] is False and not args[1]["plan"]["work"]
    assert validate(result, *args) == result


def test_multiple_requests_can_share_original_words_without_false_rejection():
    args = setup(text="Please do both.", count=2)
    ctx, _, _, draft = args
    requests = [request(ctx, draft), request(ctx, draft,
        unit_ids=[draft["units"][1]["id"]], reason="A separate requested result shares this instruction.")]
    assert review(Model(positive(draft, requests=requests)), *args)["accepted"]


def test_independent_omission_does_not_require_rejecting_a_supported_unit():
    args = setup(text="Summarise the account. Identify what remains unknown.")
    ctx, _, _, draft = args
    identity = ctx["latest"]["source_id"]
    answered = {"source_id": identity, "quote": "Summarise the account."}
    omitted = {"source_id": identity, "quote": "Identify what remains unknown."}
    data = positive(draft, requests=[request(ctx, draft, request=answered),
        request(ctx, draft, request=omitted, disposition="missing", unit_ids=[])])
    data.update(verdict="reject", findings=[{"category": "omission", "unit_ids": [],
        "sources": [omitted], "mismatch": "The independent uncertainty assessment is absent."}])
    reviewed = review(Model(data), *args)
    assert not reviewed["accepted"]
    assert reviewed["proposal"]["units"][0]["verdict"] == "supported"
    assert len(reviewed["proposal"]["request_coverage"]) == 2
    assert validate(reviewed, *args) == reviewed
    # These fixture verdicts demonstrate separate accounting, not semantic detection.


def earlier_evidence_rejection(*, count=1):
    earlier = {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
        "record_role": "original_account", "text": "The destination of the transfer is unknown."}
    args = setup(text="Summarise the reported transfer. Assess the remaining uncertainties.",
                 history=[earlier], count=count)
    ctx, _, _, draft = args
    data = negative(draft, ctx, category="grounding", sources=[ref(earlier)])
    data["findings"][0]["mismatch"] = "The unit strengthens the original account's certainty."
    data["request_coverage"] = [request(ctx, draft, disposition="missing")]
    return args, data


def test_missing_request_links_to_rejected_unit_finding_on_earlier_evidence():
    args, data = earlier_evidence_rejection()
    reviewed = review(Model(data), *args)
    assert reviewed["accepted"] is False
    assert reviewed["proposal"]["findings"][0]["sources"][0]["source_id"] == "t1:advocate"
    assert validate(reviewed, *args) == reviewed
    # This admits precise negative feedback for repair, never the rejected answer.


def test_unrelated_rejected_unit_does_not_cover_a_missing_request():
    args, data = earlier_evidence_rejection(count=2)
    data["request_coverage"][0]["unit_ids"] = [args[-1]["units"][1]["id"]]
    with pytest.raises(SchemaViolation):
        review(Model(data), *args)


def test_each_missing_row_needs_its_own_finding_relationship():
    args, data = earlier_evidence_rejection(count=2)
    other = deepcopy(data["request_coverage"][0])
    other.update(unit_ids=[args[-1]["units"][1]["id"]],
                 reason="A separate requested result is not delivered.")
    data["request_coverage"].append(other)
    with pytest.raises(SchemaViolation):
        review(Model(data), *args)


def test_omission_without_a_rejected_unit_still_needs_original_request_evidence():
    args, data = earlier_evidence_rejection()
    data["request_coverage"][0]["unit_ids"] = []
    with pytest.raises(SchemaViolation):
        review(Model(data), *args)
    data["findings"].append({"category": "omission", "unit_ids": [],
        "sources": [ref(args[0]["latest"])], "mismatch": "The requested assessment is missing."})
    reviewed = review(Model(data), *args)
    assert not reviewed["accepted"]
    assert validate(reviewed, *args) == reviewed


@pytest.mark.parametrize("damage", ["unowned_source", "changed_quote", "unowned_unit"])
def test_shared_rejected_unit_does_not_bypass_reference_ownership(damage):
    args, data = earlier_evidence_rejection()
    if damage == "unowned_source":
        data["findings"][0]["sources"][0]["source_id"] = "another-matter:advocate"
    elif damage == "changed_quote":
        data["findings"][0]["sources"][0]["quote"] = "The destination is known."
    else:
        data["request_coverage"][0]["unit_ids"] = ["another-turn:b1"]
    with pytest.raises(SchemaViolation):
        review(Model(data), *args)


def test_request_can_select_complete_original_source_without_copying_its_words():
    args = setup(text="Summarise this account without changing its uncertainty.")
    ctx, _, _, draft = args
    complete = {"source_id": ctx["latest"]["source_id"], "quote": None}
    data = positive(draft, requests=[request(ctx, draft, request=complete)])
    reviewed = review(Model(data), *args)
    assert reviewed["accepted"]
    assert reviewed["proposal"]["request_coverage"][0]["request"] == complete
    assert validate(reviewed, *args) == reviewed


@pytest.mark.parametrize("kind", ["account", "judgment"])
def test_negative_finding_can_select_complete_owned_evidence(kind):
    args = setup(legal=True)
    ctx, _, sources, draft = args
    row = next(row for row in sources.values() if row["kind"] == kind)
    complete = {"source_id": row["id"], "quote": None}
    data = negative(draft, ctx, category="grounding", sources=[complete])
    reviewed = review(Model(data), *args)
    assert not reviewed["accepted"]
    assert reviewed["proposal"]["findings"][0]["sources"] == [complete]
    assert validate(reviewed, *args) == reviewed


def test_whole_source_selection_does_not_admit_an_unowned_source():
    args = setup()
    data = negative(args[-1], args[0], sources=[{"source_id": "unowned", "quote": None}])
    with pytest.raises(SchemaViolation):
        review(Model(data), *args)


def test_earlier_original_request_is_reviewable_without_being_in_latest_plan():
    earlier = {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
               "record_role": "original_account", "text": "Summarise the account."}
    args = setup(text="Continue.", history=[earlier])
    ctx, _, _, draft = args
    requests = [request(ctx, draft, request=ref(earlier))]
    assert review(Model(positive(draft, requests=requests)), *args)["accepted"]


@pytest.mark.parametrize("damage", ["nm_source", "unknown_source", "altered_quote", "unknown_unit"])
def test_request_coverage_cannot_use_model_interpretation_or_unowned_references(damage):
    prior = {"source_id": "t1:nm", "turn_id": "t1", "speaker": "nm",
             "record_role": "nm_interpretation", "text": "Please update the record."}
    args = setup(text="Review that.", history=[prior])
    ctx, _, _, draft = args
    item = request(ctx, draft)
    if damage == "nm_source": item["request"] = ref(prior)
    elif damage == "unknown_source": item["request"]["source_id"] = "other-matter"
    elif damage == "altered_quote": item["request"]["quote"] = "Review  that."
    else: item["unit_ids"] = ["invented"]
    with pytest.raises(SchemaViolation): review(Model(positive(draft, requests=[item])), *args)


@pytest.mark.parametrize("damage", ["positive_with_finding", "negative_without_finding",
    "missing_without_finding", "rejected_without_finding", "finding_supported_unit",
    "finding_no_target", "unknown_finding_unit", "unknown_category", "blank_reason",
    "unsupported_request_limit"])
def test_inconsistent_or_unaccountable_review_is_not_an_admission(damage):
    args = setup()
    ctx, _, _, draft = args
    data = positive(draft)
    if damage == "positive_with_finding":
        data = negative(draft, ctx)
        data["verdict"] = "accept"
    elif damage == "negative_without_finding": data["verdict"] = "reject"
    elif damage == "missing_without_finding":
        data["request_coverage"] = [request(ctx, draft, disposition="missing", unit_ids=[])]
    elif damage == "rejected_without_finding": data["units"][0]["verdict"] = "rejected"
    elif damage == "finding_supported_unit":
        data = negative(draft, ctx)
        data["units"][0]["verdict"] = "supported"
    elif damage == "finding_no_target":
        data = negative(draft, ctx)
        data["findings"][0].update(unit_ids=[], sources=[])
    elif damage == "unknown_finding_unit":
        data = negative(draft, ctx)
        data["findings"][0]["unit_ids"] = ["foreign"]
    elif damage == "unknown_category":
        data = negative(draft, ctx)
        data["findings"][0]["category"] = "style_preference"
    elif damage == "blank_reason": data["units"][0]["reason"] = "  "
    else: data["request_coverage"] = [request(ctx, draft, disposition="justified_limit", unit_ids=[])]
    with pytest.raises(SchemaViolation): review(Model(data), *args)


@pytest.mark.parametrize("category", ["grounding", "attribution", "quotation", "omission", "framing", "effect"])
def test_typed_negative_findings_are_bound_without_a_second_answer_or_local_retry(category):
    args = setup()
    ctx, _, _, draft = args
    model = Model(negative(draft, ctx, category=category, sources=[]))
    reviewed = review(model, *args)
    assert not reviewed["accepted"] and len(model.calls) == 1
    assert reviewed["proposal"]["findings"][0]["category"] == category
    assert validate(reviewed, *args) == reviewed


@pytest.mark.parametrize("damage", ["draft_text", "source_text", "current_records", "saved_work",
                                   "execution", "proposal", "accepted", "contract", "extra_field"])
def test_review_receipt_cannot_be_replayed_on_changed_dependencies(damage):
    args = list(setup())
    execution = {"operations": [], "persistence": "not_yet_committed"}
    reviewed = review(Model(positive(args[-1])), *args, execution)
    if damage == "draft_text":
        proposal = deepcopy(args[-1]["proposal"])
        proposal["units"][0]["text"] = "A different reply."
        args[-1] = accept_draft(proposal, args[0], args[2])
    elif damage == "source_text": args[2][args[0]["latest"]["source_id"]]["text"] = "Changed words"
    elif damage == "current_records": args[0]["current_records"] = {"changed": True}
    elif damage == "saved_work": args[0]["saved_work"] = [{"id": "changed"}]
    elif damage == "execution": execution["operations"] = [{"id": "unexpected"}]
    elif damage == "proposal": reviewed["proposal"]["units"][0]["reason"] = "A changed reviewer decision."
    elif damage == "accepted": reviewed["accepted"] = False
    elif damage == "contract": reviewed["contract"] = "future_unknown_version"
    else: reviewed["fresh_seal"] = "not owned"
    with pytest.raises((ValueError, SchemaViolation)): validate(reviewed, *args, execution)


def test_changed_draft_projection_is_rejected_before_review_model_call():
    args = list(setup())
    args[-1]["units"][0]["text"] = "A changed projection."
    model = Model(positive(args[-1]))
    with pytest.raises(ValueError): review(model, *args)
    assert not model.calls


def test_budget_failure_keeps_complete_context_and_avoids_provider_call():
    args = setup()
    model = Model(positive(args[-1]), budget=1)
    with pytest.raises(ContextOverflow): review(model, *args)
    assert not model.calls


def test_incomplete_model_review_cannot_be_admitted_or_salvaged():
    args = setup()
    model = Model(positive(args[-1]), completion=Completion.LENGTH_LIMITED)
    with pytest.raises(ModelError): review(model, *args)
    assert len(model.calls) == 1


def test_negative_effect_verdict_is_wiring_evidence_not_real_model_detection():
    args = list(setup(text="Correct the date."))
    proposal = deepcopy(args[-1]["proposal"])
    proposal["units"][0].update(kind="limitation", text="I have corrected and saved the date.")
    args[-1] = accept_draft(proposal, args[0], args[2])
    reviewed = review(Model(negative(args[-1], args[0])), *args, {"operations": []})
    assert reviewed["accepted"] is False
    # The fixture deliberately rejects this sentence. Only a real-model evaluation
    # can show whether the reviewer reliably detects it or over-rejects safe prose.



def authority_setup():
    from tests.test_core_response_authorities import Reader
    ctx, research_record, sources, _ = setup(legal=True)
    selected = next(row for row in sources.values() if row["kind"] == "provision")
    draft = accept_draft({"units": [{"kind": "law", "text": "The selected text contains a qualification.",
        "addresses": [{"source_id": ctx["latest"]["source_id"]}],
        "uses": [{"source_id": selected["id"], "source_kind": "provision"}]}]}, ctx, sources)
    args = (ctx, research_record, sources, draft)
    return args, response_authorities.check(*args, provision_reader=Reader(research_record))


def test_fresh_review_requires_authority_evidence_even_when_no_legal_claim_is_made():
    args = setup()
    model = Model(positive(args[-1]))
    with pytest.raises(ValueError, match="requires bound authority"):
        review_checked(model, *args)
    assert model.calls == []


def test_authority_checks_are_separate_compact_model_input_and_full_bound_evidence():
    args, authority = authority_setup()
    execution = {"operations": [], "persistence": "not_yet_committed"}
    model = Model(positive(args[-1]))
    receipt = review_checked(model, *args, execution, authority_evidence=authority)
    payload = json.loads(model.calls[0][0].user)
    assert receipt["contract"] == CONTRACT == "core_response_review_v2"
    assert authority["readbacks"]
    assert payload["owned_authority_checks"] == {
        "contract": authority["contract"], "units": authority["units"]}
    assert "readbacks" not in payload["owned_authority_checks"]
    assert payload["owned_execution_evidence"] == execution
    assert validate_checked(receipt, *args, execution, authority_evidence=authority) == receipt
    assert len(model.calls) == 1


def test_valid_but_different_authority_snapshot_does_not_reuse_positive_review():
    args, authority = authority_setup()
    receipt = review_checked(Model(positive(args[-1])), *args, authority_evidence=authority)
    unavailable = response_authorities.check(*args)
    assert response_authorities.validate(unavailable, *args) == unavailable
    assert unavailable != authority
    with pytest.raises(ValueError, match="exact draft and evidence"):
        validate_checked(receipt, *args, authority_evidence=unavailable)


@pytest.mark.parametrize("damage", ["contract", "source_binding", "check_status"])
def test_altered_authority_evidence_is_refused_before_review_call(damage):
    args, authority = authority_setup()
    if damage == "contract": authority["contract"] = "future_authority_version"
    elif damage == "source_binding": authority["dependency_digest"] = "unowned"
    else: authority["units"][0]["selected_provisions"][0]["state"] = "unavailable"
    model = Model(positive(args[-1]))
    with pytest.raises(ValueError):
        review_checked(model, *args, authority_evidence=authority)
    assert model.calls == []


def test_saved_v1_review_reconstructs_exact_old_shape_without_fresh_authority(monkeypatch):
    args = setup()
    ctx, research_record, sources, draft = args
    proposal = positive(draft)
    execution = {"operations": [], "persistence": "not_yet_committed"}
    original_dependencies = {"original_context": deepcopy(ctx),
        "research_record": deepcopy(research_record), "sources": deepcopy(sources),
        "draft": deepcopy(draft), "execution": deepcopy(execution)}
    saved = {"contract": "core_response_review_v1", "proposal": proposal, "accepted": True,
        "bound_digest": _digest({"evidence": original_dependencies, "review_proposal": proposal})}
    def no_authority(*args, **kwargs):
        raise AssertionError("Legacy replay must not fetch or invent authority checks")
    monkeypatch.setattr(response_authorities, "check", no_authority)
    monkeypatch.setattr(response_authorities, "validate", no_authority)
    assert LEGACY_CONTRACT == saved["contract"]
    assert validate_checked(saved, *args, execution) == saved
    with pytest.raises(ValueError, match="Legacy review"):
        validate_checked(saved, *args, execution, authority_evidence={"contract": "invented"})


def test_v2_review_does_not_fall_back_to_legacy_when_authority_is_missing():
    args, authority = authority_setup()
    saved = review_checked(Model(positive(args[-1])), *args, authority_evidence=authority)
    with pytest.raises(ValueError, match="requires bound authority"):
        validate_checked(saved, *args)
    saved["contract"] = "future_review_version"
    with pytest.raises(ValueError, match="Unknown or malformed"):
        validate_checked(saved, *args, authority_evidence=authority)
