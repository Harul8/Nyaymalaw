"""Dispute search plans and gathering needs retain attribution and passage links."""
import json

import pytest

from nm.brain.conversation import Message
from nm.brain.legal_requirements import (
    decompose,
    read_requirements,
    verify_requirements,
)
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ContextOverflow,
    ModelResult,
    SchemaViolation,
    Tier,
    Usage,
    estimate_tokens,
)


class Model:
    def __init__(self, outputs, budget=100_000):
        self.outputs = outputs
        self.budget = budget
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.ROUTINE
        return self.budget

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema, tier, max_tokens))
        value = self.outputs[min(len(self.calls) - 1, len(self.outputs) - 1)]
        if prompt.operation == "verify_legal_requirements":
            original = json.loads(prompt.user)
            original = original.get("original_input", original)
            candidates = {row["candidate_id"]: row for row in
                          original["candidates"]}
            value = {**value, "decisions": [{
                **decision,
                "label_verdict": decision.get("label_verdict", "faithful"),
                "label_reason": decision.get(
                    "label_reason", "The short label restates the need."),
                "material_checks": decision.get("material_checks", [{
                    "material_id": material_id,
                    "verdict": "addresses",
                    "reason": "The reported material concerns this need.",
                } for material_id in candidates.get(
                    decision.get("candidate_id"), {}).get("material_ids", [])]),
            } for decision in value.get("decisions", [])]}
        return ModelResult(
            text=None, data=value, tier=tier, provider="offline",
            model="offline", usage=Usage(0, 0, 0), latency_ms=0,
            completion=Completion.COMPLETE,
        )


DISPUTES = (
    {"id": "d1", "label": "Supplier retained tools",
     "statement": "Whether the supplier must return the tools",
     "quoted": "The supplier kept our tools.", "identification": "identified",
     "source_turn_id": "first"},
    {"id": "d2", "label": "Customer withheld payment",
     "statement": "Whether payment is owed",
     "quoted": "The customer has not paid the invoice.",
     "identification": "identified", "source_turn_id": "first"},
)
MATERIAL = {
    "d1": [{"id": "m1", "kind": "evidence", "statement": "The signed receipt is held",
            "quoted": "I have the signed receipt.", "basis": "stated",
            "source_turn_id": "first"}],
    "d2": [{"id": "m2", "kind": "event", "statement": "Invoice remains unpaid",
            "quoted": "The customer has not paid the invoice.",
            "basis": "stated", "source_turn_id": "first"}],
}
CONVERSATION = (
    Message("first", "advocate", "The supplier kept our tools. "
            "The customer has not paid the invoice. I have the signed receipt."),
    Message("first", "nm", "Which transaction does the receipt concern?"),
    Message("second", "advocate", "The receipt concerns the tools."),
)
THIRD_DISPUTE = {
    "id": "d3", "label": "Carrier delayed delivery",
    "statement": "Whether delivery was late",
    "quoted": "The carrier delayed delivery.", "identification": "identified",
    "source_turn_id": "third",
}
THREE_DISPUTES = (*DISPUTES, THIRD_DISPUTE)
THREE_MATERIAL = {**MATERIAL, "d3": [
    {"id": "m3", "kind": "event", "statement": "Delivery was delayed",
     "quoted": "The carrier delayed delivery.", "basis": "stated",
     "source_turn_id": "third"},
]}
THREE_CONVERSATION = (*CONVERSATION,
                      Message("third", "advocate", "The carrier delayed delivery."))


def plan(dispute_id, *phrases):
    return {"dispute_id": dispute_id,
            "queries": [{"text": phrase} for phrase in phrases]}


def hits():
    return {
        "d1": {"state": "ok", "diagnostics": [], "candidates": [
            {"id": "s1", "kind": "provision", "title": "Applicable Act",
             "locator": "section 5", "text": "A person must give written notice."},
            {"id": "s2", "kind": "judgment", "title": "Decision A",
             "locator": "paragraph 12", "text": "A signed receipt assisted proof."},
        ]},
        "d2": {"state": "ok", "diagnostics": [], "candidates": [
            {"id": "s3", "kind": "provision", "title": "Another Act",
             "locator": "section 8", "text": "Payment is due after demand."},
        ]},
    }


def requirement(dispute_id, source_ids, material_ids, *, force="required",
                label="Obtain written notice"):
    return {"dispute_id": dispute_id, "label": label,
            "need": "Obtain the written notice if this provision applies.",
            "why": "The cited provision makes written notice a condition.",
            "force": force, "source_ids": source_ids,
            "material_ids": material_ids}


def call_budget(call):
    prompt, schema, _, output_limit = call
    return (estimate_tokens(prompt.user + (prompt.system or "") +
                            json.dumps(schema, ensure_ascii=False,
                                       separators=(",", ":"))) + output_limit)


def test_decomposition_batches_disputes_with_complete_attributed_conversation():
    model = Model([{"plans": [
        plan("d1", "supplier retained tools return duty",
             "return of property legal remedy", "receipt proof of delivery"),
        plan("d2", "unpaid invoice payment duty", "demand for payment",
             "invoice nonpayment defenses"),
    ]}])

    output = decompose(model, disputes=DISPUTES,
                       material_by_dispute=MATERIAL, conversation=CONVERSATION)

    assert len(model.calls) == 1
    assert len(output["d1"]) == 3 and len(output["d2"]) == 3
    prompt, schema, tier, _ = model.calls[0]
    assert prompt.operation == "decompose_disputes" and tier is Tier.ROUTINE
    assert all(marker in prompt.system for marker in (
        "Message:", "Purpose:", "Look for:", "Outcome:"))
    data = json.loads(prompt.user)
    assert data["conversation"] == [
        {"turn_id": row.turn_id, "role": row.role, "text": row.text}
        for row in CONVERSATION]
    assert [row["dispute"]["id"] for row in data["disputes"]] == ["d1", "d2"]
    assert schema["properties"]["plans"]["items"]["properties"][
        "queries"]["maxItems"] == 4


def test_duplicate_query_gets_one_feedback_guided_correction():
    wrong = {"plans": [plan("d1", "supplier tools", "supplier tools"),
                       plan("d2", "invoice payment")]}
    fixed = {"plans": [plan("d1", "supplier tools", "return of property"),
                       plan("d2", "invoice payment")]}
    model = Model([wrong, fixed])

    output = decompose(model, disputes=DISPUTES,
                       material_by_dispute=MATERIAL, conversation=CONVERSATION)

    assert output["d1"] == ("supplier tools", "return of property")
    assert len(model.calls) == 2
    feedback = json.loads(model.calls[1][0].user)
    assert "duplicate" in feedback["validation_issue"]
    assert feedback["original_input"] == json.loads(model.calls[0][0].user)


def test_requirements_attach_exact_passages_and_do_not_mark_reported_record_verified():
    model = Model([{"requirements": [
        requirement("d1", ["s1"], []),
        requirement("d1", ["s2"], ["m1"], force="strengthening",
                    label="Keep signed receipt"),
    ]}])

    output = read_requirements(
        model, disputes=DISPUTES, material_by_dispute=MATERIAL,
        search_results=hits(), conversation=CONVERSATION)

    assert len(model.calls) == 1
    assert [row["label"] for row in output["d1"]] == [
        "Obtain written notice", "Keep signed receipt"]
    assert output["d1"][0]["record_status"] == "not_mentioned"
    assert output["d1"][1]["record_status"] == "mentioned"
    assert output["d1"][1]["sources"] == hits()["d1"]["candidates"][1:]
    assert output["d2"] == []
    prompt = model.calls[0][0]
    assert prompt.operation == "read_legal_requirements"
    assert all(marker in prompt.system for marker in (
        "Message:", "Purpose:", "Look for:", "Outcome:"))
    assert json.loads(prompt.user)["conversation"][-1]["text"] == \
        "The receipt concerns the tools."


def test_requirement_cannot_cite_a_different_dispute_or_link_unrelated_material():
    wrong = requirement("d1", ["s3"], ["m2"])
    fixed = requirement("d1", ["s1"], ["m1"])
    model = Model([{"requirements": [wrong]}, {"requirements": [fixed]}])

    output = read_requirements(model, disputes=DISPUTES,
                               material_by_dispute=MATERIAL,
                               search_results=hits(), conversation=CONVERSATION)

    assert output["d1"][0]["source_ids"] == ["s1"]
    assert len(model.calls) == 2
    assert "another dispute" in json.loads(model.calls[1][0].user)[
        "validation_issue"]

    persistent = Model([{"requirements": [wrong]}])
    with pytest.raises(SchemaViolation, match="another dispute"):
        read_requirements(persistent, disputes=DISPUTES,
                          material_by_dispute=MATERIAL,
                          search_results=hits(), conversation=CONVERSATION)
    assert len(persistent.calls) == 2


def test_no_retrieved_passages_means_no_analysis_call_or_invented_requirement():
    model = Model([])
    unavailable = {dispute["id"]: {"state": "unavailable", "candidates": []}
                   for dispute in DISPUTES}

    result = read_requirements(model, disputes=DISPUTES,
                               material_by_dispute=MATERIAL,
                               search_results=unavailable,
                               conversation=CONVERSATION)

    assert result == {"d1": [], "d2": []}
    assert model.calls == []


def test_partial_search_keeps_passages_from_available_corpus():
    partial = hits()
    partial["d1"]["state"] = "partial"
    partial["d1"]["diagnostics"] = ["judgment search unavailable"]
    partial["d1"]["candidates"] = partial["d1"]["candidates"][:1]
    partial["d2"] = {"state": "unavailable", "candidates": []}
    model = Model([{"requirements": [requirement("d1", ["s1"], [])]}])

    checked = read_requirements(
        model, disputes=DISPUTES, material_by_dispute=MATERIAL,
        search_results=partial, conversation=CONVERSATION)

    assert len(model.calls) == 1
    assert checked["d1"][0]["sources"] == partial["d1"]["candidates"]
    assert checked["d2"] == []


def test_independent_read_prunes_unsupported_citations_and_items_in_one_call():
    proposed = read_requirements(Model([{"requirements": [
        requirement("d1", ["s1", "s2"], []),
        requirement("d2", ["s3"], ["m2"], label="Check payment demand"),
    ]}]), disputes=DISPUTES, material_by_dispute=MATERIAL,
        search_results=hits(), conversation=CONVERSATION)
    verifier = Model([
        {"decisions": [{
            "candidate_id": "r1", "verdict": "supported",
            "source_checks": [
                {"source_id": "s1", "verdict": "supported",
                 "scope_status": "no_special_condition",
                 "support_fragment_id": "f1",
                 "scope_fragment_id": "",
                 "reason": "The provision states the notice condition."},
                {"source_id": "s2", "verdict": "unsupported",
                 "scope_status": "different_legal_setting",
                 "support_fragment_id": "", "scope_fragment_id": "",
                 "reason": "The receipt passage does not establish notice."},
            ], "reason": "The provision supports the complete item."}]},
        {"decisions": [{
            "candidate_id": "r2", "verdict": "unsupported",
            "source_checks": [{
                "source_id": "s3", "verdict": "unsupported",
                "scope_status": "cannot_determine",
                "support_fragment_id": "", "scope_fragment_id": "",
                "reason": "The passage does not establish this notice need."}],
            "reason": "The cited passage does not support the item."}]},
    ])

    checked = verify_requirements(
        verifier, disputes=DISPUTES, material_by_dispute=MATERIAL,
        proposed=proposed, conversation=CONVERSATION)

    assert len(verifier.calls) == 2
    assert checked["d1"][0]["source_ids"] == ["s1"]
    assert checked["d1"][0]["sources"] == [{
        **hits()["d1"]["candidates"][0],
        "verification": {
            "support_excerpt": "A person must give written notice.",
            "scope_excerpt": "",
            "scope_status": "no_special_condition",
            "reason": "The provision states the notice condition.",
        },
    }]
    assert checked["d2"] == []
    prompt = verifier.calls[0][0]
    assert prompt.operation == "verify_legal_requirements"
    assert all(marker in prompt.system for marker in (
        "Message:", "Purpose:", "Look for:", "Outcome:"))
    payload = json.loads(prompt.user)
    assert payload["conversation"] == [
        {"turn_id": row.turn_id, "role": row.role, "text": row.text}
        for row in CONVERSATION]
    assert payload["candidates"][0]["sources"][0]["fragments"] == [{
        "id": "f1", "text": "A person must give written notice."}]
    assert [json.loads(call[0].user)["dispute"]["id"]
            for call in verifier.calls] == ["d1", "d2"]


def test_display_label_and_reported_material_are_checked_independently():
    proposed = read_requirements(Model([{"requirements": [
        requirement("d1", ["s1"], [], label="Unsupported board heading"),
        requirement("d1", ["s2"], ["m1"], force="strengthening",
                    label="Check signed receipt"),
    ]}]), disputes=DISPUTES, material_by_dispute=MATERIAL,
        search_results=hits(), conversation=CONVERSATION)
    model = Model([{"decisions": [
        {"candidate_id": "r1", "verdict": "supported",
         "label_verdict": "unsupported",
         "label_reason": "The heading adds a proposition not in the need.",
         "source_checks": [{
             "source_id": "s1", "verdict": "supported",
             "scope_status": "no_special_condition",
             "support_fragment_id": "f1", "scope_fragment_id": "",
             "reason": "The passage supports the longer item."}],
         "reason": "Only the longer item is supported."},
        {"candidate_id": "r2", "verdict": "supported",
         "material_checks": [{
             "material_id": "m1", "verdict": "does_not_address",
             "reason": "This reported record does not establish the item."}],
         "source_checks": [{
             "source_id": "s2", "verdict": "supported",
             "scope_status": "no_special_condition",
             "support_fragment_id": "f1", "scope_fragment_id": "",
             "reason": "The passage supports this need."}],
         "reason": "The legal item survives without that material link."},
    ]}])

    checked = verify_requirements(
        model, disputes=DISPUTES, material_by_dispute=MATERIAL,
        proposed=proposed, conversation=CONVERSATION)

    assert [item["label"] for item in checked["d1"]] == ["Check signed receipt"]
    assert checked["d1"][0]["material_ids"] == []
    assert checked["d1"][0]["record_status"] == "not_mentioned"
    assert len(model.calls) == 1


def test_verifier_refuses_cross_item_support_after_one_correction():
    proposed = read_requirements(Model([{"requirements": [
        requirement("d1", ["s1"], []),
        requirement("d1", ["s2"], ["m1"], force="strengthening",
                    label="Keep signed receipt"),
    ]}]), disputes=DISPUTES, material_by_dispute=MATERIAL,
        search_results=hits(), conversation=CONVERSATION)
    wrong = {"decisions": [
        {"candidate_id": "r1", "verdict": "supported",
         "source_checks": [{
             "source_id": "s2", "verdict": "supported",
             "scope_status": "no_special_condition",
             "support_fragment_id": "f1",
             "scope_fragment_id": "", "reason": "Wrong source for item."}],
         "reason": "Unrelated passage."},
        {"candidate_id": "r2", "verdict": "supported",
         "source_checks": [{
             "source_id": "s2", "verdict": "supported",
             "scope_status": "no_special_condition",
             "support_fragment_id": "f1",
             "scope_fragment_id": "", "reason": "The receipt passage."}],
         "reason": "The receipt passage."},
    ]}
    model = Model([wrong])

    checked = verify_requirements(model, disputes=DISPUTES,
                                  material_by_dispute=MATERIAL,
                                  proposed=proposed,
                                  conversation=CONVERSATION)

    assert checked == {"d1": [], "d2": []}
    assert len(model.calls) == 6
    assert "another or duplicate source" in json.loads(
        model.calls[1][0].user)["validation_issue"]


def test_failed_verification_batch_recovers_only_valid_individual_items():
    proposed = read_requirements(Model([{"requirements": [
        requirement("d1", ["s1"], []),
        requirement("d1", ["s2"], ["m1"], force="strengthening",
                    label="Keep signed receipt"),
    ]}]), disputes=DISPUTES, material_by_dispute=MATERIAL,
        search_results=hits(), conversation=CONVERSATION)
    valid_first = {"decisions": [{
        "candidate_id": "r1", "verdict": "supported",
        "source_checks": [{
            "source_id": "s1", "verdict": "supported",
            "scope_status": "no_special_condition",
            "support_fragment_id": "f1",
            "scope_fragment_id": "", "reason": "The passage states the condition.",
        }], "reason": "The first item is supported.",
    }]}
    invalid = {"decisions": []}
    model = Model([invalid, invalid, valid_first, invalid, invalid])

    checked = verify_requirements(
        model, disputes=DISPUTES, material_by_dispute=MATERIAL,
        proposed=proposed, conversation=CONVERSATION)

    assert len(model.calls) == 5
    assert checked["d1"][0]["label"] == "Obtain written notice"
    assert len(checked["d1"]) == 1
    assert checked["d2"] == []
    assert [len(json.loads(call[0].user).get("candidates", []))
            for call in (model.calls[0], model.calls[2], model.calls[3])] == [
                2, 1, 1]


def test_verification_skips_model_when_no_items_were_proposed():
    model = Model([])
    checked = verify_requirements(
        model, disputes=DISPUTES, material_by_dispute=MATERIAL,
        proposed={"d1": [], "d2": []}, conversation=CONVERSATION)
    assert checked == {"d1": [], "d2": []}
    assert model.calls == []


@pytest.mark.parametrize(("fragment_id", "scope_status", "issue"), [
    ("f999", "no_special_condition", "outside the permitted vocabulary"),
    ("f1", "not_established", "exact, applicable support"),
])
def test_verification_requires_valid_fragment_and_applicable_scope(
        fragment_id, scope_status, issue):
    proposed = read_requirements(Model([{"requirements": [
        requirement("d1", ["s1"], []),
    ]}]), disputes=DISPUTES, material_by_dispute=MATERIAL,
        search_results=hits(), conversation=CONVERSATION)
    verdict = {"decisions": [{
        "candidate_id": "r1", "verdict": "supported",
        "source_checks": [{
            "source_id": "s1", "verdict": "supported",
            "scope_status": scope_status,
            "support_fragment_id": fragment_id, "scope_fragment_id": "",
            "reason": "Purported support."}],
        "reason": "Purported support.",
    }]}
    model = Model([verdict])

    with pytest.raises(SchemaViolation, match=issue):
        verify_requirements(model, disputes=DISPUTES,
                            material_by_dispute=MATERIAL, proposed=proposed,
                            conversation=CONVERSATION)
    assert len(model.calls) == 2


def test_verifier_reconstructs_exact_overlapping_fragments_from_saved_passage():
    long_passage = "Context about procedure. " * 32 + (
        "For a signed request, the recipient must give notice. ")
    candidate_hits = hits()
    candidate_hits["d1"]["candidates"][0]["text"] = long_passage
    proposed = read_requirements(Model([{"requirements": [
        requirement("d1", ["s1"], []),
    ]}]), disputes=DISPUTES, material_by_dispute=MATERIAL,
        search_results=candidate_hits, conversation=CONVERSATION)
    model = Model([{"decisions": [{
        "candidate_id": "r1", "verdict": "supported",
        "source_checks": [{
            "source_id": "s1", "verdict": "supported",
            "scope_status": "asked_to_establish",
            "support_fragment_id": "f2", "scope_fragment_id": "f2",
            "reason": "The item asks whether this condition applies."}],
        "reason": "The operative words and condition are in the selected span.",
    }]}])

    checked = verify_requirements(model, disputes=DISPUTES,
                                  material_by_dispute=MATERIAL,
                                  proposed=proposed,
                                  conversation=CONVERSATION)

    fragments = json.loads(model.calls[0][0].user)["candidates"][0][
        "sources"][0]["fragments"]
    assert fragments[1]["id"] == "f2"
    assert fragments[1]["text"] in long_passage
    assert checked["d1"][0]["sources"][0]["verification"] == {
        "support_excerpt": fragments[1]["text"],
        "scope_excerpt": fragments[1]["text"],
        "scope_status": "asked_to_establish",
        "reason": "The item asks whether this condition applies.",
    }
    assert len(model.calls) == 1


def test_verifier_rejects_fragment_id_from_another_cited_source():
    candidate_hits = hits()
    candidate_hits["d1"]["candidates"][1]["text"] = "Other passage. " * 60
    proposed = read_requirements(Model([{"requirements": [
        requirement("d1", ["s1", "s2"], []),
    ]}]), disputes=DISPUTES, material_by_dispute=MATERIAL,
        search_results=candidate_hits, conversation=CONVERSATION)
    wrong = {"decisions": [{
        "candidate_id": "r1", "verdict": "supported",
        "source_checks": [
            {"source_id": "s1", "verdict": "supported",
             "scope_status": "no_special_condition",
             "support_fragment_id": "f2", "scope_fragment_id": "",
             "reason": "Selected from the other source."},
            {"source_id": "s2", "verdict": "unsupported",
             "scope_status": "cannot_determine",
             "support_fragment_id": "", "scope_fragment_id": "",
             "reason": "This source does not support the item."}],
        "reason": "Purported support.",
    }]}
    good = {"decisions": [{
        "candidate_id": "r1", "verdict": "supported",
        "source_checks": [{
            "source_id": "s1", "verdict": "supported",
            "scope_status": "no_special_condition",
            "support_fragment_id": "f1", "scope_fragment_id": "",
            "reason": "This exact passage supports the full item."}],
        "reason": "Source s1 alone supports the item.",
    }]}
    model = Model([wrong, wrong, good, wrong, wrong])

    checked = verify_requirements(model, disputes=DISPUTES,
                                  material_by_dispute=MATERIAL,
                                  proposed=proposed,
                                  conversation=CONVERSATION)

    assert checked["d1"][0]["source_ids"] == ["s1"]
    assert len(model.calls) == 5
    assert [len(json.loads(call[0].user)["candidates"][0]["sources"])
            for call in (model.calls[0], model.calls[2], model.calls[3])
            ] == [2, 1, 1]


def test_missing_one_source_verdict_rechecks_sources_independently():
    proposed = read_requirements(Model([{"requirements": [
        requirement("d1", ["s1", "s2"], []),
    ]}]), disputes=DISPUTES, material_by_dispute=MATERIAL,
        search_results=hits(), conversation=CONVERSATION)
    incomplete = {"decisions": [{
        "candidate_id": "r1", "verdict": "supported",
        "source_checks": [{
            "source_id": "s1", "verdict": "supported",
            "scope_status": "no_special_condition",
            "support_fragment_id": "f1", "scope_fragment_id": "",
            "reason": "This passage establishes the condition."}],
        "reason": "Source s1 supports the item.",
    }]}
    no_support = {"decisions": [{
        "candidate_id": "r1", "verdict": "unsupported",
        "source_checks": [{
            "source_id": "s2", "verdict": "unsupported",
            "scope_status": "different_legal_setting",
            "support_fragment_id": "", "scope_fragment_id": "",
            "reason": "This passage concerns another issue."}],
        "reason": "The passage does not support the item.",
    }]}
    model = Model([incomplete, incomplete, incomplete, no_support])

    checked = verify_requirements(model, disputes=DISPUTES,
                                  material_by_dispute=MATERIAL,
                                  proposed=proposed,
                                  conversation=CONVERSATION)

    assert checked["d1"][0]["source_ids"] == ["s1"]
    assert len(model.calls) == 4
    assert "every cited passage" in json.loads(model.calls[1][0].user)[
        "validation_issue"]
    assert [len(json.loads(call[0].user)["candidates"][0]["sources"])
            for call in (model.calls[2], model.calls[3])] == [1, 1]


def test_full_conversation_must_fit_before_model_call():
    model = Model([{"plans": []}], budget=100)
    with pytest.raises(ContextOverflow):
        decompose(model, disputes=DISPUTES,
                  material_by_dispute=MATERIAL, conversation=CONVERSATION)
    assert model.calls == []


def test_decomposition_splits_into_fewest_complete_groups_when_needed():
    first_two = Model([{"plans": [plan("d1", "return tools"),
                                   plan("d2", "invoice payment")]}])
    decompose(first_two, disputes=DISPUTES, material_by_dispute=MATERIAL,
              conversation=THREE_CONVERSATION)
    budget = call_budget(first_two.calls[0])
    model = Model([
        {"plans": [plan("d1", "return tools"),
                   plan("d2", "invoice payment")]},
        {"plans": [plan("d3", "late delivery")]},
    ], budget=budget)

    output = decompose(model, disputes=THREE_DISPUTES,
                       material_by_dispute=THREE_MATERIAL,
                       conversation=THREE_CONVERSATION)

    assert output == {"d1": ("return tools",),
                      "d2": ("invoice payment",),
                      "d3": ("late delivery",)}
    assert len(model.calls) == 2
    assert [[row["dispute"]["id"] for row in json.loads(call[0].user)[
        "disputes"]] for call in model.calls] == [["d1", "d2"], ["d3"]]
    for call in model.calls:
        assert json.loads(call[0].user)["conversation"] == [
            {"turn_id": row.turn_id, "role": row.role, "text": row.text}
            for row in THREE_CONVERSATION]


def test_oversized_single_dispute_refuses_before_any_partial_model_call():
    calibration = Model([{"plans": [plan("d1", "return tools")]}])
    decompose(calibration, disputes=DISPUTES[:1],
              material_by_dispute={"d1": MATERIAL["d1"]},
              conversation=CONVERSATION)
    model = Model([], budget=call_budget(calibration.calls[0]))
    oversized = {**DISPUTES[1], "statement": "x" * 30000}

    with pytest.raises(ContextOverflow):
        decompose(model, disputes=(DISPUTES[0], oversized),
                  material_by_dispute=MATERIAL, conversation=CONVERSATION)

    assert model.calls == []


def test_requirement_batches_keep_exact_passages_with_their_disputes():
    third_hits = {**hits(), "d3": {
        "state": "ok", "diagnostics": [], "candidates": [
            {"id": "s4", "kind": "judgment", "title": "Decision B",
             "locator": "paragraph 9", "text": "Delivery time affected remedy."},
        ],
    }}
    first_two = Model([{"requirements": []}])
    read_requirements(first_two, disputes=DISPUTES,
                      material_by_dispute=MATERIAL,
                      search_results=hits(), conversation=THREE_CONVERSATION)
    budget = call_budget(first_two.calls[0])
    model = Model([
        {"requirements": [requirement("d1", ["s1"], ["m1"])]},
        {"requirements": [requirement("d3", ["s4"], ["m3"],
                                      label="Check delivery timing")]},
    ], budget=budget)

    output = read_requirements(
        model, disputes=THREE_DISPUTES,
        material_by_dispute=THREE_MATERIAL,
        search_results=third_hits, conversation=THREE_CONVERSATION)

    assert len(model.calls) == 2
    assert [[row["dispute"]["id"] for row in json.loads(call[0].user)[
        "disputes"]] for call in model.calls] == [["d1", "d2"], ["d3"]]
    assert output["d1"][0]["sources"] == third_hits["d1"]["candidates"][:1]
    assert output["d3"][0]["sources"] == third_hits["d3"]["candidates"]
    assert output["d2"] == []
    for call in model.calls:
        assert json.loads(call[0].user)["conversation"] == [
            {"turn_id": row.turn_id, "role": row.role, "text": row.text}
            for row in THREE_CONVERSATION]
    first_schema = model.calls[0][1]
    second_schema = model.calls[1][1]
    def source_enum(schema):
        return schema["properties"]["requirements"]["items"][
            "properties"]["source_ids"]["items"]["enum"]
    assert set(source_enum(first_schema)) == {"s1", "s2", "s3"}
    assert source_enum(second_schema) == ["s4"]
