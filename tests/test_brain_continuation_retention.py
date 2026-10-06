"""Failed legal content cannot erase independently checked attributed progress."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from nm.brain.continuation_verification import verify_continuation
from nm.brain.work_state import project_work
from tests.brain_continuation_fixture import citation_units, reviewed_verdicts
from tests.test_brain_continuation import (
    ContinuationModel,
    _continue,
    _operation_names,
    checked_finding,
    supplied_law,
    unit,
    verdict,
)
from tests.test_brain_continuation_service import PublicContinuationModel, opening_route, send
from tests.test_brain_turn import plan

DISCLOSURE = (
    "I omitted an earlier instruction from my account. "
    "I now report a note describing that instruction, but its contents have not been inspected. "
    "I am worried about explaining the correction.")


def block(identity, kind, text, *, source="L1"):
    return {"id": identity, "kind": kind, "text": text,
            "span_ids": [source] if source else [], "record_ids": [],
            "legal_source_ids": [], "inline_citations": [], "uncertainty": "reported"}


def mixed(*, structural=False, contribution=False):
    result = unit()
    result.update(blocks=[
        block("ack", "acknowledgment", "Thank you for explaining the correction.", source="L3"),
        block("facts", "account", "You now report an earlier instruction you had omitted."),
        block("law", "assessment" if structural else "account",
              "The earlier instruction defeats all opposing claims."),
        block("limit", "limitation",
              "The reported note has not been inspected, and the legal effect remains "
              "unassessed because no supporting authority has been supplied.", source="L2")],
        questions=[], next_work=[],
        sufficiency={"status": "complete", "block_id": "law"},
        work={"existing_id": "", "create": not contribution},
        progress_updates=[] if contribution else [{
            "target_id": "$work", "status": "complete", "block_id": "law",
            "reason": "The entire requested review is complete.", "span_ids": ["L1"]}])
    return result


def retain_facts(payload):
    data = reviewed_verdicts(payload, verdict(0))
    row = data["verdicts"][0]
    for check in row["block_checks"]:
        if check["block_id"] == "law":
            check.update(requires_legal_support=True, verdict="reject",
                         reason="The attributed words do not establish this legal consequence.")
        elif check["block_id"] == "proof":
            check.update(verdict="reject",
                         reason="A reported uninspected note is not an established fact.")
        elif check["block_id"] == "next":
            check.update(requires_legal_support=True, verdict="reject",
                         reason="The proposed legal course exceeds the supplied support.")
    row.update(retained_block_ids=["ack", "facts", "limit"],
               retained_reason="These attributed blocks and their explicit limitation "
               "remain coherent without the rejected claims or any progress changes.")
    return data


def assert_limited(result):
    assert result.coverage[0]["state"] == "partial"
    saved = result.units[0]
    assert [row["id"] for row in saved["blocks"]] == ["ack", "facts", "limit"]
    assert saved["sufficiency"] == {"status": "partial", "block_id": "limit"}
    assert saved["questions"] == saved["next_work"] == saved["progress_updates"] == []
    assert "defeats all opposing claims" not in json.dumps(saved)
    assert "uninspected note proves" not in json.dumps(saved)


def test_semantic_rejection_keeps_only_a_certified_coherent_subset_after_bounded_repair():
    proposed = mixed()
    proposed["blocks"].insert(3, block(
        "proof", "account", "The uninspected note proves the instruction's contents.", source="L2"))
    proposed["blocks"].insert(4, block(
        "next", "next_step", "You may pursue every remedy on this record."))
    proposed["next_work"] = [{"id": "all-remedies", "block_id": "next",
                              "purpose": "Pursue every legal remedy.",
                              "target_ids": [], "existing_id": ""}]
    original = deepcopy(proposed)
    model = ContinuationModel([
        {"units": [proposed]}, retain_facts, {"units": [proposed]}, retain_facts])

    result = _continue(model, latest=DISCLOSURE)

    assert_limited(result)
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"] * 2
    repair = model.calls[2][1]
    assert repair["correction"]["rejected_units"] == citation_units(
        repair, {"units": [original]})["units"]
    assert result.units[0]["blocks"][1]["references"][0]["text"] == (
        "I omitted an earlier instruction from my account.")
    assert "legal consequence" in result.coverage[0]["diagnostics"][0]


def test_persistent_local_support_failure_gets_one_final_independent_narrowed_review():
    proposed = mixed(structural=True)

    def check_subset(payload):
        assert [row["id"] for row in payload["units"][0]["blocks"]] == ["ack", "facts", "limit"]
        held = payload["input"]["partial_response_review"][0]
        assert held["unreleased_unit"] == proposed
        assert "actual supporting checked passage" in held["content_issues"]["law"]
        return verdict(0)

    model = ContinuationModel([{"units": [proposed]}, {"units": [proposed]}, check_subset])
    result = _continue(model, latest=DISCLOSURE)

    assert_limited(result)
    assert _operation_names(model) == [
        "continue_conversation", "continue_conversation", "verify_continuation"]


def test_valid_factual_coverage_is_not_lost_when_the_conditional_rewrite_is_unavailable():
    from nm.shared.model_port import ProviderUnavailable

    model = ContinuationModel([
        {"units": [mixed()]}, retain_facts, ProviderUnavailable("Offline provider unavailable")])
    result = _continue(model, latest=DISCLOSURE)

    assert_limited(result)
    assert len(model.calls) == 3


def test_a_thin_selected_passage_does_not_legitimise_broader_advice():
    def propose(payload):
        result = mixed()
        law = result["blocks"][2]
        key = next(iter(payload["legal_sources"]))
        law.update(kind="assessment", legal_source_ids=[key], inline_citations=[{
            "text": "defeats all opposing claims", "legal_source_id": key}])
        return {"units": [result]}

    model = ContinuationModel([propose, retain_facts, propose, retain_facts])
    result = _continue(model, latest=DISCLOSURE, checked_sources=supplied_law())

    assert_limited(result)
    assert all(not row["legal_source_ids"] for row in result.units[0]["blocks"])
    assert len(model.calls) == 4


def test_a_supported_quote_does_not_validate_other_claims_in_its_block():
    passage = supplied_law()[0]["text"]

    def propose(payload):
        result = mixed()
        key = next(iter(payload["legal_sources"]))
        result["blocks"][2].update(
            kind="assessment", text=f"{passage} Every available remedy is therefore guaranteed.",
            legal_source_ids=[key], inline_citations=[{
                "text": passage, "legal_source_id": key}])
        return {"units": [result]}

    def check_entire_block(payload):
        proposed = payload["units"][0]["blocks"][2]
        source = payload["input"]["legal_sources"][proposed["legal_source_ids"][0]]
        assert proposed["inline_citations"][0]["text"] == source["text"] == passage
        data = retain_facts(payload)
        check = next(check for check in data["verdicts"][0]["block_checks"]
                     if check["block_id"] == "law")
        check.update(reason="The quote is supported, but the separate guarantee of every "
                     "remedy is not entailed by the selected passage.")
        return data

    model = ContinuationModel([propose, check_entire_block, propose, check_entire_block])
    result = _continue(model, latest=DISCLOSURE, checked_sources=supplied_law())

    assert_limited(result)
    assert "guaranteed" not in json.dumps(result.units)
    assert "not entailed" in result.coverage[0]["diagnostics"][0]
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"] * 2


def test_public_ambiguous_reference_is_clarified_without_repeating_supported_peer(
        client, wired, monkeypatch):
    first_words = ("My colleague has a storage key and an appointment token. "
                   "Please retain these two reported items.")
    latest = "She agreed to return it tomorrow. Also repeat the two items I mentioned."
    first_route = plan(first_words, step="legal_work")
    second_route = plan("Clarify which item the planned return concerns.", step="clarify",
                        relation="continues")
    second_route["items"][0]["clarification"] = "Which item does the planned return concern?"
    second_route["items"].append({
        **second_route["items"][0], "request": "Repeat the two reported items.",
        "next_step": "legal_work", "clarification": "",
        "reply": "I will repeat the two attributed items.",
        "record_requirement": {"kind": "none", "target_ids": [],
                               "operation": "none", "success_condition": ""}})
    initial = unit(text="You report that your colleague has a storage key and appointment token.")
    initial["blocks"] = [initial["blocks"][0]]
    initial.update(questions=[], sufficiency={"status": "complete", "block_id": "account-0"})
    bad = unit(text="Your colleague will return the storage key tomorrow.")
    bad["blocks"] = [bad["blocks"][0]]
    bad.update(questions=[], sufficiency={"status": "complete", "block_id": "account-0"})
    peer = unit(1, text="You mentioned a storage key and an appointment token.",
                span_ids=("P1S1",))
    peer["blocks"] = [peer["blocks"][0]]
    peer.update(questions=[], sufficiency={"status": "complete", "block_id": "account-1"})
    repaired = unit(text="You report a planned return tomorrow, but the item remains unclear.",
                    question="Does the planned return concern the storage key or "
                    "appointment token?")
    repaired["blocks"][1]["span_ids"] = ["L1", "P1S1"]
    repaired["blocks"][2]["text"] = (
        "The item must be identified before I can say what the planned return resolves.")
    repaired["questions"][0]["purpose"] = "Identify which of the two reported items is meant."

    def check_ambiguity(payload):
        assert [unit["request_index"] for unit in payload["units"]] == [0, 1]
        data = reviewed_verdicts(payload, verdict(0, 1))
        data["verdicts"][0]["block_checks"][0].update(
            verdict="reject", reason="The latest reference could mean either reported item; "
            "the storage key was silently selected without attributable clarification.")
        return data

    def clarify_pending(payload):
        assert [item["request_index"] for item in payload["work_items"]] == [0]
        assert payload["correction"]["rejected_units"] == citation_units(
            payload, {"units": [bad]})["units"]
        assert "".join(span["text"] for span in
                       payload["earlier_conversation"][0]["source_spans"]) == first_words
        assert payload["latest_message_spans"][0]["text"] == (
            "She agreed to return it tomorrow.")
        return {"units": [repaired]}

    model = PublicContinuationModel(
        [first_route, second_route],
        [{"units": [initial]}, {"units": [bad, peer]}, clarify_pending],
        checks=[verdict(0), check_ambiguity, verdict(0)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    first = send(client, first_words, "ambiguous-reference-start")
    answer = send(client, latest, "ambiguous-reference-return", opened=first)
    replay = send(client, latest, "ambiguous-reference-return", opened=first)

    assert first["metrics"]["llm_calls"] == 3
    assert answer["metrics"]["llm_calls"] == 5
    assert replay["metrics"]["llm_calls"] == 0
    visible = "\n".join(row["text"] for row in answer["elements"])
    assert "will return the storage key" not in visible
    assert "Does the planned return concern" in visible
    assert visible.count("You mentioned a storage key and an appointment token.") == 1
    units = {unit["request_index"]: unit for unit in answer["continuation"]["units"]}
    assert units[0]["sufficiency"]["status"] == "needs_input"
    assert units[1]["sufficiency"]["status"] == "complete"
    assert units[0]["progress_updates"] == units[1]["progress_updates"] == []
    from nm.brain.turn import chat_matter_id

    saved = wired.store.load(chat_matter_id("adv_demo", answer["chat_id"]))
    assert [row["message"] for row in saved.brain_chat] == [first_words, latest]
    assert saved.brain_chat[-1]["elements"] == answer["elements"]


@pytest.mark.parametrize("kind", ["gathering", "requested_work"])
def test_current_passages_cannot_bypass_missing_finding_use_verification(kind):
    from nm.brain.history import IncompleteConversation

    source = supplied_law()[0]
    finding = {"label": "Checked condition", "need": "The condition remains conditional.",
               "sources": [source], "source_ids": [source["id"]], "material_ids": []}
    coverage = {"source_freshness": "current", "verification_current": True}
    arguments = {}
    if kind == "gathering":
        arguments["disputes"] = {"state": "ok", "rows": [{"id": "dispute-one"}]}
        arguments["requirements"] = {
            "state": "ok", "by_dispute": {"dispute-one": [finding]},
            "coverage_by_dispute": {"dispute-one": coverage}}
    else:
        subject = {"id": "request-one", "kind": "request", "scope": "proposed",
                   "question": "Explain the condition.", "purpose": "requested_work"}
        arguments["research"] = {
            "state": "ok", "subjects": {"request-one": subject},
            "by_subject": {"request-one": [finding]},
            "coverage_by_subject": {"request-one": coverage},
            "source_turn_id_by_subject": {"request-one": "earlier"}}
    model = ContinuationModel([])

    with pytest.raises(IncompleteConversation, match="no checked legal use"):
        _continue(model, **arguments)

    assert model.calls == []


@pytest.mark.parametrize("kind", ["gathering", "requested_work"])
def test_checked_use_refs_share_canonical_catalogue_ids_without_changing_saved_finding(kind):
    sources = list(supplied_law())
    finding = checked_finding({"label": "Checked condition", "need": "The condition is limited.",
                               "sources": sources})
    original = deepcopy(finding)
    coverage = {"source_freshness": "current", "verification_current": True}
    if kind == "gathering":
        arguments = {"disputes": {"state": "ok", "rows": [{"id": "dispute-one"}]},
                     "requirements": {
                         "state": "ok", "by_dispute": {"dispute-one": [finding]},
                         "coverage_by_dispute": {"dispute-one": coverage}}}
    else:
        subject = {"id": "request-one", "kind": "request", "scope": "proposed",
                   "question": "Explain the condition.", "purpose": "requested_work"}
        arguments = {"research": {
            "state": "ok", "subjects": {"request-one": subject},
            "by_subject": {"request-one": [finding]},
            "coverage_by_subject": {"request-one": coverage},
            "source_turn_id_by_subject": {"request-one": "earlier"}}}

    def inspect(payload):
        row = next(row["record"] for row in payload["record_catalogue"].values()
                   if row["type"] in ("requirement", "research"))
        legal_ids = set(payload["legal_sources"])
        assert set(row["source_ids"]) == legal_ids
        for check in row["use_verification"]["checks"].values():
            assert set(check["source_ids"]) == legal_ids
            assert source["id"] not in check["source_ids"]
        return {"units": [unit()]}

    source = sources[0]
    model = ContinuationModel([inspect, verdict(0)])
    result = _continue(model, **arguments)

    assert result.coverage[0]["state"] == "ok"
    assert finding == original
    assert len(model.calls) == 2


@pytest.mark.parametrize("fault", ["unknown_span", "unknown_record", "unknown_work",
                                  "missing_owner", "duplicate_block", "missing_graph"])
def test_structural_integrity_failure_never_enters_partial_review(fault):
    proposed = mixed(structural=True)
    if fault == "unknown_span":
        proposed["blocks"][0]["span_ids"] = ["another-source"]
    elif fault == "unknown_record":
        proposed["blocks"][1]["record_ids"] = ["another-record"]
    elif fault == "unknown_work":
        proposed["work"] = {"existing_id": "another-task", "create": False}
    elif fault == "missing_owner":
        proposed["questions"] = [{"id": "q", "block_id": "absent",
                                  "purpose": "Resolve the account.",
                                  "target_ids": [], "existing_id": ""}]
    elif fault == "duplicate_block":
        proposed["blocks"][0]["id"] = "facts"
    else:
        proposed.pop("sufficiency")
    model = ContinuationModel([{"units": [proposed]}, {"units": [proposed]}])

    result = _continue(model, latest=DISCLOSURE)

    assert result.units == () and result.coverage[0]["state"] == "unavailable"
    assert _operation_names(model) == ["continue_conversation", "continue_conversation"]


@pytest.mark.parametrize("fault", ["no_limit", "rejected_block", "legal_block", "duplicate",
                                  "unknown", "proposal_owner"])
def test_retention_approval_with_bad_coverage_is_unread_and_cannot_override_rejection(fault):
    proposed = mixed()
    if fault == "proposal_owner":
        proposed["questions"] = [{"id": "q", "block_id": "facts",
                                  "purpose": "Resolve the reported instruction.",
                                  "target_ids": [], "existing_id": ""}]

    def invalid(payload):
        data = retain_facts(payload)
        row = data["verdicts"][0]
        if fault == "no_limit":
            row["retained_block_ids"].remove("limit")
        elif fault in ("rejected_block", "legal_block"):
            row["retained_block_ids"].append("law")
            if fault == "legal_block":
                next(c for c in row["block_checks"] if c["block_id"] == "law")[
                    "verdict"] = "accept"
        elif fault == "duplicate":
            row["retained_block_ids"].append("facts")
        elif fault == "unknown":
            row["retained_block_ids"].append("absent")
        return data

    model = ContinuationModel([invalid, invalid])
    checked = verify_continuation(model, input_payload={
        "legal_sources": {}, "progress": {"state": "ok", "rows": []}}, units=(proposed,))

    assert checked.decisions == {} and checked.retained == {} and checked.unavailable == (0,)
    assert len(model.calls) == 2


def test_public_adverse_disclosure_retains_supported_response_context_and_pending_work(
        client, wired, monkeypatch):
    first_words = "I have a signed receipt for the disputed transaction. Please review it."
    follow = plan(DISCLOSURE, scope="current", relation="continues", step="legal_work",
                  reply="I will examine the corrected account.")
    follow["items"][0]["intent"] = "contribution"
    follow["items"][0]["material_purposes"] = ["account_contribution"]
    proposed = mixed(contribution=True)
    model = PublicContinuationModel([
        opening_route(first_words), follow],
        [{"units": [unit()]}, {"units": [proposed]}, {"units": [proposed]}],
        checks=[verdict(0), retain_facts, retain_facts])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    first = send(client, first_words, "retained-before")
    before = project_work(wired.store.load(first["matter_id"]))

    answer = send(client, DISCLOSURE, "retained-disclosure", opened=first)
    replay = send(client, DISCLOSURE, "retained-disclosure", opened=first)

    assert answer["metrics"]["llm_calls"] == 8
    assert replay["metrics"]["llm_calls"] == 0
    assert answer["blocked"] is True
    assert answer["continuation"]["coverage"][0]["state"] == "partial"
    released = answer["continuation"]["units"][0]
    assert released["sufficiency"]["status"] == "partial"
    assert released["questions"] == released["next_work"] == released["progress_updates"] == []
    visible = "\n".join(row["text"] for row in answer["elements"])
    assert "Thank you for explaining the correction." in visible
    assert "You now report an earlier instruction" in visible
    assert "legal effect remains unassessed" in visible
    assert "defeats all opposing claims" not in visible
    assert "I could not finish a checked response" not in visible
    saved = wired.store.load(first["matter_id"])
    assert [row["message"] for row in saved.brain_chat] == [first_words, DISCLOSURE]
    assert project_work(saved) == before
    writer = [payload for op, payload in model.calls if op == "continue_conversation"][-1]
    assert writer["latest_message_spans"][0]["text"] in DISCLOSURE
    assert "".join(row["text"] for row in writer["earlier_conversation"][0][
        "source_spans"]) == first_words
    assert any(row["role"] == "nm" for row in writer["earlier_conversation"])


@pytest.mark.parametrize("fault", ["unknown_source", "dangling_owner"])
def test_public_untrusted_source_or_owner_withholds_instead_of_salvaging(
        client, wired, monkeypatch, fault):
    routed = plan(DISCLOSURE, scope="none", step="legal_work",
                  reply="I will examine the attributed correction.")
    proposed = mixed(structural=True)
    if fault == "unknown_source":
        proposed["blocks"][0]["span_ids"] = ["unowned-source"]
    else:
        proposed["questions"] = [{"id": "q", "block_id": "unowned-block",
                                  "purpose": "Clarify the correction.",
                                  "target_ids": [], "existing_id": ""}]
    model = PublicContinuationModel([routed],
                                    [{"units": [proposed]}, {"units": [proposed]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    answer = send(client, DISCLOSURE, f"retention-integrity-{fault}")

    assert answer["metrics"]["llm_calls"] == 3
    assert answer["continuation"]["units"] == []
    assert answer["continuation"]["coverage"][0]["state"] == "unavailable"
    assert [op for op, _ in model.calls] == [
        "interpret_conversation", "continue_conversation", "continue_conversation"]


def test_public_persistent_local_support_failure_releases_checked_partial_content(
        client, wired, monkeypatch):
    routed = plan(DISCLOSURE, scope="none", step="legal_work",
                  reply="I will examine the attributed correction.")
    proposed = mixed(structural=True)
    model = PublicContinuationModel([routed],
                                    [{"units": [proposed]}, {"units": [proposed]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    answer = send(client, DISCLOSURE, "retention-final-local-check")

    assert answer["metrics"]["llm_calls"] == 4
    assert answer["continuation"]["coverage"][0]["state"] == "partial"
    assert answer["continuation"]["units"][0]["progress_updates"] == []
    visible = "\n".join(row["text"] for row in answer["elements"])
    assert "Thank you for explaining the correction." in visible
    assert "defeats all opposing claims" not in visible
    assert [op for op, _ in model.calls] == [
        "interpret_conversation", "continue_conversation", "continue_conversation",
        "verify_continuation"]
