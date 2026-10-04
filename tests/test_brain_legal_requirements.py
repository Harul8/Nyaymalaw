"""Dispute search plans and gathering needs retain attribution and passage links."""
import json

import pytest

from nm.brain.conversation import Message
from nm.brain.legal_requirements import (
    FINDING_USE_CHECKS,
    RESEARCH_VERIFICATION,
    decompose,
    decompose_subjects,
    finding_verification_valid,
    read_findings,
    read_requirements,
    verify_findings,
    verify_requirements,
)
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ModelResult,
    ProviderUnavailable,
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
        assert tier in (Tier.ROUTINE, Tier.JUDGE)
        return self.budget

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema, tier, max_tokens))
        value = self.outputs[min(len(self.calls) - 1, len(self.outputs) - 1)]
        if isinstance(value, Exception):
            raise value
        original = json.loads(prompt.user)
        subjects = original["subjects"]
        if prompt.operation == "decompose_disputes":
            value = {"plans": [{"subject_id": row.get("subject_id", row.get("dispute_id")),
                                "queries": row["queries"]}
                               for row in value.get("plans", [])]}
        if prompt.operation == "read_legal_requirements" and "requirements" in value:
            value = {"readings": [{"subject_id": row["subject"]["id"],
                                  "findings": [
                                      {"kind": "gathering", **{
                                          key: item for key, item in finding.items()
                                          if key != "dispute_id"}}
                                      for finding in value["requirements"]
                                      if finding["dispute_id"] == row["subject"]["id"]]}
                                 for row in subjects]}
        if prompt.operation == "verify_legal_requirements":
            candidates = {row["candidate_id"]: row for row in
                          [candidate for subject in subjects
                           for candidate in subject["candidates"]]}
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
                "use_checks": decision.get("use_checks", {
                    aspect: {
                        "verdict": decision["verdict"],
                        "reason": "This scripted use is supported by its own evidence.",
                        "source_ids": [row["source_id"] for row in decision.get("source_checks", [])
                                       if row["verdict"] == "supported"],
                        "material_ids": [row["material_id"] for row in decision.get(
                            "material_checks", [{"material_id": key, "verdict": "addresses"}
                                                for key in candidates.get(
                                                    decision.get("candidate_id"), {}).get(
                                                        "material_ids", [])])
                                         if row["verdict"] == "addresses"],
                    } for aspect in FINDING_USE_CHECKS}),
                "source_checks": [self._source_check(check, candidates.get(
                    decision.get("candidate_id"), {}))
                    for check in decision.get("source_checks", [])],
                "application_premises": decision.get("application_premises", [{
                    "source_id": check["source_id"],
                    "predicate_fragment_id": check["scope_fragment_id"],
                    "status": "unresolved", "account_source_ids": [],
                    "preserved_condition": candidates.get(
                        decision.get("candidate_id"), {}).get("need", ""),
                    "reason": "The proposed need retains the source condition without applying it.",
                } for check in decision.get("source_checks", [])
                    if check["verdict"] == "supported" and check.get("scope_fragment_id")]),
            } for decision in value.get("decisions", [])]}
        return ModelResult(
            text=None, data=value, tier=tier, provider="offline",
            model="offline", usage=Usage(0, 0, 0), latency_ms=0,
            completion=Completion.COMPLETE,
        )

    @staticmethod
    def _source_check(check, candidate):
        sources = {source["id"]: source for source in candidate.get("sources", [])}
        source = sources.get(check.get("source_id"), {})
        supported = check.get("verdict") == "supported"
        fragment = check.get("support_fragment_id", "") if supported else ""
        owner = check.get("assertion_owner", "legislative_text"
                          if source.get("kind") == "provision" else "deciding_court")
        statement = next((row["text"] for row in source.get("fragments", [])
                          if row["id"] == fragment), "")[:500]
        return {
            "assertion_owner": owner,
            "assertion_role": {"legislative_text": "legislative_text",
                               "deciding_court": "court_reasoning", "party": "party_submission",
                               "quoted_authority": "quoted_authority"}.get(owner, "unclear"),
            "assertion_statement": statement,
            "owner_label": "The issuing source",
            "owner_fragment_id": fragment,
            "source_treatment": "adopted" if supported else "unclear",
            "treatment_fragment_id": fragment,
            "context_statements": [],
            **check,
        }


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


SUBJECTS = tuple({
    "id": row["id"], "kind": "dispute", "owner_id": row["id"], "scope": "current",
    "purpose": "gathering", "question": row["statement"],
    "record_ids": [row["id"], *[item["id"] for item in MATERIAL[row["id"]]]],
} for row in DISPUTES)
SUBJECT_MATERIAL = {row["id"]: [row, *MATERIAL[row["id"]]] for row in DISPUTES}


def _candidate_rows(payload):
    return [candidate for subject in payload["subjects"] for candidate in subject["candidates"]]


def conversation_words(payload):
    return [{"turn_id": row["turn_id"], "role": row["role"],
             "text": row.get("text", "".join(span["text"]
                                              for span in row.get("source_spans", [])))}
            for row in payload["conversation"]]


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


def supported_verdict(candidate_id, source_id, *, material_checks=None):
    decision = {
        "candidate_id": candidate_id, "verdict": "supported",
        "source_checks": [{
            "source_id": source_id, "verdict": "supported",
            "scope_status": "no_special_condition", "support_fragment_id": "f1",
            "scope_fragment_id": "", "reason": "This exact passage supports the item.",
        }], "reason": "The complete item follows from its cited passage.",
    }
    if material_checks is not None:
        decision["material_checks"] = material_checks
    return decision


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
    assert conversation_words(data) == [
        {"turn_id": row.turn_id, "role": row.role, "text": row.text}
        for row in CONVERSATION]
    assert [row["subject"]["id"] for row in data["subjects"]] == ["d1", "d2"]
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
    assert "duplicate" in feedback["validation_issues"]["d1"]
    assert [row["subject"]["id"] for row in feedback["subjects"]] == ["d1"]
    assert feedback["conversation"] == json.loads(model.calls[0][0].user)["conversation"]


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
    assert model.calls[0][2] is Tier.ROUTINE
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
    feedback = json.loads(model.calls[1][0].user)["validation_issues"]["d1"]
    assert "invalid source_ids ['s3']" in feedback
    assert "allowed_source_ids ['s1', 's2']" in feedback
    first_payload = json.loads(model.calls[0][0].user)
    first_subject = next(row for row in first_payload["subjects"]
                         if row["subject"]["id"] == "d1")
    assert first_subject["allowed_source_ids"] == ["s1", "s2"]
    assert first_subject["allowed_material_ids"] == ["d1", "m1"]

    persistent = Model([{"requirements": [wrong]}])
    failed = read_findings(persistent, subjects=SUBJECTS,
                           material_by_subject=SUBJECT_MATERIAL,
                           search_results=hits(), conversation=CONVERSATION)
    assert failed.rows == {"d2": []}
    assert failed.coverage["d1"]["unread_items"] == 1
    assert failed.coverage["d2"]["checked_items"] == 1
    assert len(persistent.calls) == 2


def test_no_retrieved_passages_means_no_analysis_call_or_invented_requirement():
    model = Model([])
    unavailable = {dispute["id"]: {"state": "unavailable", "candidates": []}
                   for dispute in DISPUTES}

    result = read_requirements(model, disputes=DISPUTES,
                               material_by_dispute=MATERIAL,
                               search_results=unavailable,
                               conversation=CONVERSATION)

    assert result == {}
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
    assert "d2" not in checked


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
            ], "reason": "The provision supports the complete item."}, {
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

    assert len(verifier.calls) == 1
    assert all(call[2] is Tier.JUDGE and call[3] >= 4096 for call in verifier.calls)
    assert checked.rows["d1"][0]["source_ids"] == ["s1"]
    assert checked.rows["d1"][0]["sources"] == [{
        **hits()["d1"]["candidates"][0],
        "verification": {
            "contract": RESEARCH_VERIFICATION,
            "assertion_owner": "legislative_text",
            "assertion_role": "legislative_text",
            "assertion_statement": "A person must give written notice.",
            "context_statements": [],
            "owner_label": "The issuing source",
            "owner_excerpt": "A person must give written notice.",
            "source_treatment": "adopted",
            "treatment_excerpt": "A person must give written notice.",
            "support_excerpt": "A person must give written notice.",
            "scope_excerpt": "",
            "scope_status": "no_special_condition",
            "reason": "The provision states the notice condition.",
        },
    }]
    assert checked.rows["d2"] == []
    assert checked.coverage["d1"]["checked_items"] == 1
    assert checked.coverage["d2"]["withheld_items"] == 1
    assert all(row["state"] == "ok" for row in checked.coverage.values())
    prompt = verifier.calls[0][0]
    assert prompt.operation == "verify_legal_requirements"
    assert all(marker in prompt.system for marker in (
        "Message:", "Purpose:", "Look for:", "Outcome:"))
    payload = json.loads(prompt.user)
    assert conversation_words(payload) == [
        {"turn_id": row.turn_id, "role": row.role, "text": row.text}
        for row in CONVERSATION]
    assert _candidate_rows(payload)[0]["sources"][0]["fragments"] == [{
        "id": "f1", "text": "A person must give written notice."}]
    assert [[row["subject"]["id"] for row in json.loads(call[0].user)["subjects"]]
            for call in verifier.calls] == [["d1", "d2"]]


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

    assert [item["label"] for item in checked.rows["d1"]] == ["Check signed receipt"]
    assert checked.rows["d1"][0]["material_ids"] == []
    assert checked.rows["d1"][0]["record_status"] == "not_mentioned"
    assert checked.coverage["d1"]["checked_items"] == 2
    assert checked.coverage["d1"]["withheld_items"] == 1
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

    assert [row["label"] for row in checked.rows["d1"]] == ["Keep signed receipt"]
    assert checked.rows["d2"] == []
    assert checked.coverage["d1"]["state"] == "partial"
    assert checked.coverage["d1"]["checked_items"] == 1
    assert checked.coverage["d1"]["unread_items"] == 1
    assert len(model.calls) == 2
    repair = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in _candidate_rows(repair)] == ["r1"]
    assert "source" in json.dumps(repair["validation_issues"])


def test_one_repair_salvages_readable_items_without_individual_fanout():
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
    model = Model([invalid, valid_first])

    checked = verify_requirements(
        model, disputes=DISPUTES, material_by_dispute=MATERIAL,
        proposed=proposed, conversation=CONVERSATION)

    assert len(model.calls) == 2
    assert checked.rows["d1"][0]["label"] == "Obtain written notice"
    assert len(checked.rows["d1"]) == 1
    assert checked.rows["d2"] == []
    assert checked.coverage["d1"]["state"] == "partial"
    assert checked.coverage["d1"]["checked_items"] == 1
    assert checked.coverage["d1"]["unread_items"] == 1
    assert [len(_candidate_rows(json.loads(call[0].user))) for call in model.calls] == [2, 2]


def test_verification_skips_model_when_no_items_were_proposed():
    model = Model([])
    checked = verify_requirements(
        model, disputes=DISPUTES, material_by_dispute=MATERIAL,
        proposed={"d1": [], "d2": []}, conversation=CONVERSATION)
    assert checked.rows == {"d1": [], "d2": []}
    assert all(row["state"] == "ok" for row in checked.coverage.values())
    assert model.calls == []


@pytest.mark.parametrize(("fragment_id", "scope_status", "issue"), [
    ("f999", "no_special_condition", "outside the permitted vocabulary"),
    ("f1", "not_established", "supported passage needs"),
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

    checked = verify_requirements(model, disputes=DISPUTES,
                                  material_by_dispute=MATERIAL, proposed=proposed,
                                  conversation=CONVERSATION)
    assert checked.rows == {"d1": [], "d2": []}
    assert checked.coverage["d1"]["state"] == "partial"
    assert checked.coverage["d1"]["unread_items"] == 1
    feedback = json.loads(model.calls[1][0].user)
    assert issue in json.dumps(feedback["validation_issues"]).lower()
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

    fragments = _candidate_rows(json.loads(model.calls[0][0].user))[0][
        "sources"][0]["fragments"]
    assert fragments[1]["id"] == "f2"
    assert fragments[1]["text"] in long_passage
    assert checked.rows["d1"][0]["sources"][0]["verification"] == {
        "contract": RESEARCH_VERIFICATION,
        "assertion_owner": "legislative_text",
        "assertion_role": "legislative_text",
        "assertion_statement": fragments[1]["text"][:500],
        "context_statements": [],
        "owner_label": "The issuing source",
        "owner_excerpt": fragments[1]["text"],
        "source_treatment": "adopted",
        "treatment_excerpt": fragments[1]["text"],
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
        "source_checks": [
            {"source_id": "s1", "verdict": "supported",
             "scope_status": "no_special_condition",
             "support_fragment_id": "f1", "scope_fragment_id": "",
             "reason": "This exact passage supports the full item."},
            {"source_id": "s2", "verdict": "unsupported",
             "scope_status": "cannot_determine",
             "support_fragment_id": "", "scope_fragment_id": "",
             "reason": "This source does not support the item."}],
        "reason": "Source s1 alone supports the item.",
    }]}
    model = Model([wrong, good])

    checked = verify_requirements(model, disputes=DISPUTES,
                                  material_by_dispute=MATERIAL,
                                  proposed=proposed,
                                  conversation=CONVERSATION)

    assert checked.rows["d1"][0]["source_ids"] == ["s1"]
    assert checked.coverage["d1"]["state"] == "ok"
    assert len(model.calls) == 2
    assert [len(_candidate_rows(json.loads(call[0].user))[0]["sources"])
            for call in model.calls] == [2, 2]


def test_missing_one_source_verdict_gets_one_complete_candidate_correction():
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
    corrected = {"decisions": [{
        **incomplete["decisions"][0],
        "source_checks": [*incomplete["decisions"][0]["source_checks"],
                          *no_support["decisions"][0]["source_checks"]],
    }]}
    model = Model([incomplete, corrected])

    checked = verify_requirements(model, disputes=DISPUTES,
                                  material_by_dispute=MATERIAL,
                                  proposed=proposed,
                                  conversation=CONVERSATION)

    assert checked.rows["d1"][0]["source_ids"] == ["s1"]
    assert checked.coverage["d1"]["state"] == "ok"
    assert len(model.calls) == 2
    assert "every cited passage" in json.dumps(json.loads(model.calls[1][0].user)[
        "validation_issues"])
    assert [len(_candidate_rows(json.loads(call[0].user))[0]["sources"])
            for call in model.calls] == [2, 2]


@pytest.mark.parametrize(("verdict", "label_verdict"), [
    ("unsupported", "faithful"),
    ("uncertain", "faithful"),
    ("supported", "unsupported"),
    ("supported", "uncertain"),
])
def test_explicit_withholding_is_a_checked_decision_without_unnecessary_source_checks(
        verdict, label_verdict):
    proposed = read_requirements(Model([{"requirements": [
        requirement("d1", ["s1"], ["m1"]),
    ]}]), disputes=DISPUTES, material_by_dispute=MATERIAL,
        search_results=hits(), conversation=CONVERSATION)
    decision = {
        "candidate_id": "r1", "verdict": verdict,
        "label_verdict": label_verdict,
        "label_reason": "The display heading must preserve the item's support limits.",
        "source_checks": [], "material_checks": [],
        "reason": "The complete proposal should be withheld in its current formulation.",
    }
    model = Model([{"decisions": [decision]}])

    checked = verify_requirements(
        model, disputes=DISPUTES, material_by_dispute=MATERIAL,
        proposed=proposed, conversation=CONVERSATION)

    assert checked.rows == {"d1": [], "d2": []}
    assert checked.coverage["d1"]["state"] == "ok"
    assert checked.coverage["d1"]["checked_items"] == 1
    assert checked.coverage["d1"]["withheld_items"] == 1
    assert checked.coverage["d1"]["unread_items"] == 0
    assert len(model.calls) == 1


def test_twice_unread_source_coverage_does_not_fan_out_into_item_or_source_calls():
    proposed = read_requirements(Model([{"requirements": [
        requirement("d1", ["s1", "s2"], []),
    ]}]), disputes=DISPUTES, material_by_dispute=MATERIAL,
        search_results=hits(), conversation=CONVERSATION)
    model = Model([{"decisions": [supported_verdict("r1", "s1")]}])

    checked = verify_requirements(
        model, disputes=DISPUTES, material_by_dispute=MATERIAL,
        proposed=proposed, conversation=CONVERSATION)

    assert checked.rows == {"d1": [], "d2": []}
    assert checked.coverage["d1"]["state"] == "partial"
    assert checked.coverage["d1"]["checked_items"] == 0
    assert checked.coverage["d1"]["unread_items"] == 1
    assert len(model.calls) == 2
    for prompt, _, _, _ in model.calls:
        candidates = _candidate_rows(json.loads(prompt.user))
        assert len(candidates) == 1
        assert [source["id"] for source in candidates[0]["sources"]] == ["s1", "s2"]


def test_supported_item_cannot_promote_a_material_link_without_its_check():
    proposed = read_requirements(Model([{"requirements": [
        requirement("d1", ["s1"], ["m1"]),
    ]}]), disputes=DISPUTES, material_by_dispute=MATERIAL,
        search_results=hits(), conversation=CONVERSATION)
    model = Model([{"decisions": [supported_verdict("r1", "s1", material_checks=[])]}])

    checked = verify_requirements(
        model, disputes=DISPUTES, material_by_dispute=MATERIAL,
        proposed=proposed, conversation=CONVERSATION)

    assert checked.rows == {"d1": [], "d2": []}
    assert checked.coverage["d1"]["state"] == "partial"
    assert checked.coverage["d1"]["unread_items"] == 1
    assert len(model.calls) == 2
    correction = json.loads(model.calls[1][0].user)
    assert "every linked material" in json.dumps(correction["validation_issues"])
    assert _candidate_rows(correction)[0]["material_ids"] == ["m1"]


@pytest.mark.parametrize("outage_after", [0, 1])
def test_verifier_outage_stops_dispatch_and_preserves_already_checked_disputes(outage_after):
    proposed = read_requirements(Model([{"requirements": [
        requirement("d1", ["s1"], []),
        requirement("d2", ["s3"], ["m2"], label="Check payment demand"),
    ]}]), disputes=DISPUTES, material_by_dispute=MATERIAL,
        search_results=hits(), conversation=CONVERSATION)
    replies = ([{"decisions": [supported_verdict("r1", "s1")]}]
               if outage_after else [])
    model = Model([*replies, ProviderUnavailable("Synthetic provider outage")])

    checked = verify_requirements(
        model, disputes=DISPUTES, material_by_dispute=MATERIAL,
        proposed=proposed, conversation=CONVERSATION)

    assert len(model.calls) == outage_after + 1
    assert checked.outage == "ProviderUnavailable"
    assert checked.rows["d2"] == []
    assert checked.coverage["d2"]["state"] == "unavailable"
    assert checked.coverage["d2"]["unread_items"] == 1
    if outage_after:
        assert checked.rows["d1"][0]["label"] == "Obtain written notice"
        assert checked.coverage["d1"]["state"] == "ok"
        assert checked.coverage["d1"]["checked_items"] == 1
    else:
        assert checked.rows["d1"] == []
        assert checked.coverage["d1"]["state"] == "unavailable"
        assert checked.coverage["d1"]["unread_items"] == 1


def test_research_does_not_trim_full_conversation_when_no_unit_fits():
    model = Model([{"plans": []}], budget=100)
    result = decompose_subjects(model, subjects=SUBJECTS,
                                material_by_subject=SUBJECT_MATERIAL, conversation=CONVERSATION)
    assert result.rows == {}
    assert all(row["unread_items"] == 1 for row in result.coverage.values())
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
    assert [[row["subject"]["id"] for row in json.loads(call[0].user)[
        "subjects"]] for call in model.calls] == [["d1", "d2"], ["d3"]]
    for call in model.calls:
        assert conversation_words(json.loads(call[0].user)) == [
            {"turn_id": row.turn_id, "role": row.role, "text": row.text}
            for row in THREE_CONVERSATION]


def test_oversized_subject_remains_unread_without_hiding_a_complete_peer():
    calibration = Model([{"plans": [plan("d1", "return tools")]}])
    decompose(calibration, disputes=DISPUTES[:1],
              material_by_dispute={"d1": MATERIAL["d1"]},
              conversation=CONVERSATION)
    model = Model([{"plans": [plan("d1", "return tools")]}],
                  budget=call_budget(calibration.calls[0]))
    oversized = {**SUBJECTS[1], "question": "x" * 30000}
    result = decompose_subjects(model, subjects=(SUBJECTS[0], oversized),
                                material_by_subject=SUBJECT_MATERIAL, conversation=CONVERSATION)
    assert result.rows == {"d1": ("return tools",)}
    assert result.coverage["d2"]["unread_items"] == 1
    assert len(model.calls) == 1


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
    assert [[row["subject"]["id"] for row in json.loads(call[0].user)[
        "subjects"]] for call in model.calls] == [["d1", "d2"], ["d3"]]
    assert output["d1"][0]["sources"] == third_hits["d1"]["candidates"][:1]
    assert output["d3"][0]["sources"] == third_hits["d3"]["candidates"]
    assert output["d2"] == []
    for call in model.calls:
        assert conversation_words(json.loads(call[0].user)) == [
            {"turn_id": row.turn_id, "role": row.role, "text": row.text}
            for row in THREE_CONVERSATION]
    first_schema = model.calls[0][1]
    second_schema = model.calls[1][1]
    def source_enum(schema):
        return schema["properties"]["readings"]["items"]["properties"][
            "findings"]["items"]["properties"]["source_ids"]["items"]["enum"]
    assert set(source_enum(first_schema)) == {"s1", "s2", "s3"}
    assert source_enum(second_schema) == ["s4"]


REQUEST_SUBJECT = {
    "id": "q1", "kind": "request", "owner_id": "requested-1", "scope": "none",
    "purpose": "requested_work", "question": "Explain the supplied rule and its limits",
    "record_ids": [],
}


def finding(kind="principle", **changes):
    return {"kind": kind, "label": "Notice under the stated condition",
            "need": "If an agreement requires notice, written notice must be given.",
            "why": "The supplied provision makes notice conditional on the agreement.",
            "force": "none", "source_ids": ["s1"], "material_ids": [], **changes}


def request_hits():
    return {"q1": {"state": "ok", "candidates": [{
        "id": "s1", "kind": "provision", "title": "Supplied provision",
        "locator": "section 1", "text": "If the agreement requires notice, give written notice.",
    }]}}


def request_read(model):
    return read_findings(model, subjects=(REQUEST_SUBJECT,), material_by_subject={"q1": []},
                         search_results=request_hits(), conversation=CONVERSATION)


@pytest.mark.parametrize("kind", ["principle", "condition", "support", "adverse"])
def test_request_findings_use_passages_without_creating_a_dispute_or_gathering_item(kind):
    model = Model([{"readings": [{"subject_id": "q1", "findings": [finding(kind)]}]}])
    read = request_read(model)
    assert read.rows["q1"][0]["kind"] == kind
    assert read.rows["q1"][0]["force"] == "none"
    assert read.rows["q1"][0]["sources"] == request_hits()["q1"]["candidates"]
    assert read.coverage["q1"]["state"] == "ok"
    payload = json.loads(model.calls[0][0].user)
    assert payload["subjects"][0]["subject"] == REQUEST_SUBJECT
    assert payload["subjects"][0]["material"] == []
    assert conversation_words(payload)[-1]["text"] == CONVERSATION[-1].text


def test_conditional_scope_needs_exact_predicate_and_an_independent_faithfulness_check():
    read = request_read(Model([{"readings": [{"subject_id": "q1", "findings": [finding()]}]}]))
    decision = supported_verdict("r1", "s1")
    decision["source_checks"][0].update(scope_status="conditional", scope_fragment_id="f1")
    verifier = Model([{"decisions": [decision]}])
    checked = verify_findings(verifier, subjects=(REQUEST_SUBJECT,),
                              material_by_subject={"q1": []}, proposed=read.rows,
                              conversation=CONVERSATION)
    source = checked.rows["q1"][0]["sources"][0]
    assert source["verification"]["scope_status"] == "conditional"
    assert source["verification"]["scope_excerpt"] == source["text"]
    assert source["verification"]["support_excerpt"] == source["text"]
    assert len(verifier.calls) == 1 and verifier.calls[0][2] is Tier.JUDGE
    rejected = {**decision, "label_verdict": "unsupported",
                "label_reason": "The unconditional label removes the limiting predicate.",
                "source_checks": []}
    rejection = verify_findings(Model([{"decisions": [rejected]}]),
                                 subjects=(REQUEST_SUBJECT,), material_by_subject={"q1": []},
                                 proposed=read.rows, conversation=CONVERSATION)
    assert rejection.rows["q1"] == []
    assert rejection.coverage["q1"]["withheld_items"] == 1


def test_conditional_scope_without_its_exact_limiting_fragment_stays_unread_after_one_repair():
    read = request_read(Model([{"readings": [{"subject_id": "q1", "findings": [finding()]}]}]))
    decision = supported_verdict("r1", "s1")
    decision["source_checks"][0].update(scope_status="conditional")
    model = Model([{"decisions": [decision]}])
    checked = verify_findings(model, subjects=(REQUEST_SUBJECT,), material_by_subject={"q1": []},
                              proposed=read.rows, conversation=CONVERSATION)
    assert checked.rows["q1"] == [] and checked.coverage["q1"]["unread_items"] == 1
    assert len(model.calls) == 2


def test_planning_and_reading_repair_only_unresolved_subjects_and_keep_empty_coverage_explicit():
    model = Model([{"plans": [plan("d1", "same", "same"), plan("d2", "payment rule")]},
                   {"plans": [plan("d1", "property return rule")]}])
    planning = decompose_subjects(model, subjects=SUBJECTS,
                                  material_by_subject=SUBJECT_MATERIAL, conversation=CONVERSATION)
    assert planning.rows == {"d2": ("payment rule",), "d1": ("property return rule",)}
    assert [row["subject"]["id"] for row in json.loads(
        model.calls[1][0].user)["subjects"]] == ["d1"]
    reader = Model([{"readings": [
        {"subject_id": "d1", "findings": [
            finding("gathering", force="required", source_ids=["s3"])]},
        {"subject_id": "d2", "findings": []},
    ]}, {"readings": [{"subject_id": "d1", "findings": [
        finding("gathering", force="required")]}]}])
    read = read_findings(reader, subjects=SUBJECTS, material_by_subject=SUBJECT_MATERIAL,
                         search_results=hits(), conversation=CONVERSATION)
    assert len(read.rows["d1"]) == 1 and read.rows["d2"] == []
    assert read.coverage["d2"]["checked_items"] == 1
    assert [row["subject"]["id"] for row in json.loads(
        reader.calls[1][0].user)["subjects"]] == ["d1"]


@pytest.mark.parametrize("stage", ["plan", "read"])
def test_research_provider_outage_preserves_valid_peer_work(stage):
    if stage == "plan":
        model = Model([{"plans": [plan("d1", "property return")]}, ProviderUnavailable("offline")])
        result = decompose_subjects(model, subjects=SUBJECTS,
                                    material_by_subject=SUBJECT_MATERIAL, conversation=CONVERSATION)
    else:
        model = Model([{"readings": [{"subject_id": "d1", "findings": [
            finding("gathering", force="required")]}]}, ProviderUnavailable("offline")])
        result = read_findings(model, subjects=SUBJECTS, material_by_subject=SUBJECT_MATERIAL,
                               search_results=hits(), conversation=CONVERSATION)
    assert result.rows["d1"]
    assert result.coverage["d1"]["checked_items"] == 1
    assert result.coverage["d2"]["unread_items"] == 1
    assert result.outage == "ProviderUnavailable" and len(model.calls) == 2


def test_unknown_or_general_subject_record_ownership_fails_before_dispatch():
    model = Model([])
    with pytest.raises(SchemaViolation, match="cannot import"):
        decompose_subjects(model, subjects=(REQUEST_SUBJECT,),
                           material_by_subject={"q1": MATERIAL["d1"]}, conversation=CONVERSATION)
    with pytest.raises(SchemaViolation, match="unavailable attributed material"):
        decompose_subjects(model, subjects=({**REQUEST_SUBJECT, "record_ids": ["missing"]},),
                           material_by_subject={"q1": []}, conversation=CONVERSATION)
    assert model.calls == []


def test_malformed_passage_is_local_to_its_subject_and_cannot_hide_readable_peers():
    search = hits()
    search["d1"]["candidates"][0]["text"] = None
    model = Model([{"readings": [{"subject_id": "d2", "findings": [
        finding("gathering", force="required", source_ids=["s3"], material_ids=["m2"])]}]}])
    read = read_findings(model, subjects=SUBJECTS, material_by_subject=SUBJECT_MATERIAL,
                         search_results=search, conversation=CONVERSATION)
    assert "d1" not in read.rows and read.coverage["d1"]["unread_items"] == 1
    assert read.rows["d2"][0]["source_ids"] == ["s3"]
    assert read.coverage["d2"]["state"] == "ok"
    assert len(model.calls) == 1


def test_context_fitting_research_group_uses_three_calls_with_an_independent_check():
    model = Model([
        {"plans": [plan("d1", "return tools"), plan("d2", "payment obligation")]},
        {"readings": [
            {"subject_id": "d1", "findings": [finding("gathering", force="required")]},
            {"subject_id": "d2", "findings": [finding("support", source_ids=["s3"])]},
        ]},
        {"decisions": [supported_verdict("r1", "s1"), supported_verdict("r2", "s3")]},
    ])
    planning = decompose_subjects(model, subjects=SUBJECTS,
                                  material_by_subject=SUBJECT_MATERIAL, conversation=CONVERSATION)
    reading = read_findings(model, subjects=SUBJECTS, material_by_subject=SUBJECT_MATERIAL,
                            search_results=hits(), conversation=CONVERSATION)
    checked = verify_findings(model, subjects=SUBJECTS, material_by_subject=SUBJECT_MATERIAL,
                              proposed=reading.rows, conversation=CONVERSATION)
    assert set(planning.rows) == set(checked.rows) == {"d1", "d2"}
    assert all(checked.rows.values())
    assert [call[2] for call in model.calls] == [Tier.ROUTINE, Tier.ROUTINE, Tier.JUDGE]
    assert len(model.calls) == 3


def test_oversized_reading_subject_does_not_hide_another_subjects_passages():
    calibration = Model([{"readings": [{"subject_id": "d2", "findings": []}]}])
    read_findings(calibration, subjects=SUBJECTS[1:],
                   material_by_subject={"d2": SUBJECT_MATERIAL["d2"]},
                   search_results={"d2": hits()["d2"]}, conversation=CONVERSATION)
    model = Model([{"readings": [{"subject_id": "d2", "findings": [
        finding("support", source_ids=["s3"])]}]}], budget=call_budget(calibration.calls[0]))
    oversized = hits()
    oversized["d1"]["candidates"][0]["text"] = "Complete supplied passage. " * 3000
    reading = read_findings(model, subjects=SUBJECTS, material_by_subject=SUBJECT_MATERIAL,
                            search_results=oversized, conversation=CONVERSATION)
    assert "d1" not in reading.rows and reading.coverage["d1"]["unread_items"] == 1
    assert reading.rows["d2"][0]["sources"] == hits()["d2"]["candidates"]
    assert len(model.calls) == 1
    assert conversation_words(json.loads(model.calls[0][0].user)) == [
        {"turn_id": row.turn_id, "role": row.role, "text": row.text} for row in CONVERSATION]


def test_oversized_source_check_stays_unread_while_another_candidate_is_checked():
    reading = read_findings(Model([{"readings": [
        {"subject_id": "d1", "findings": [finding("gathering", force="required")]},
        {"subject_id": "d2", "findings": [finding("support", source_ids=["s3"])]},
    ]}]), subjects=SUBJECTS, material_by_subject=SUBJECT_MATERIAL,
        search_results=hits(), conversation=CONVERSATION)
    calibration = Model([{"decisions": [supported_verdict("r1", "s3")]}])
    verify_findings(calibration, subjects=SUBJECTS[1:],
                     material_by_subject={"d2": SUBJECT_MATERIAL["d2"]},
                     proposed={"d2": reading.rows["d2"]}, conversation=CONVERSATION)
    reading.rows["d1"][0]["sources"][0]["text"] = "Complete source passage. " * 3000
    model = Model([{"decisions": [supported_verdict("r2", "s3")]}],
                  budget=call_budget(calibration.calls[0]) + 100)
    checked = verify_findings(model, subjects=SUBJECTS, material_by_subject=SUBJECT_MATERIAL,
                              proposed=reading.rows, conversation=CONVERSATION)
    assert checked.rows["d1"] == [] and checked.coverage["d1"]["unread_items"] == 1
    assert checked.rows["d2"][0]["source_ids"] == ["s3"]
    assert checked.coverage["d2"]["checked_items"] == 1 and len(model.calls) == 1


def test_provider_schema_rejection_gets_one_same_contract_correction():
    model = Model([SchemaViolation("queries require text"),
                   {"plans": [plan("q1", "notice condition")]}])
    planning = decompose_subjects(model, subjects=(REQUEST_SUBJECT,),
                                  material_by_subject={"q1": []}, conversation=CONVERSATION)
    assert planning.rows == {"q1": ("notice condition",)}
    assert len(model.calls) == 2
    repair = json.loads(model.calls[1][0].user)
    assert repair["validation_issues"] == {"q1": "queries require text"}
    assert repair["conversation"] == json.loads(model.calls[0][0].user)["conversation"]


@pytest.mark.parametrize("treatment", ["reported", "rejected", "unclear"])
def test_nonadopted_position_cannot_be_checked_law_and_only_its_unit_is_corrected(treatment):
    source = {"id": "argument", "kind": "judgment", "title": "Supplied judgment",
              "locator": "paragraph 3", "text": (
                  "The applicant contends prior consent is always necessary. "
                  "We reject that contention; the stated exception permits later consent.")}
    proposed = {"q1": [
        {**finding(source_ids=["argument"], label="Prior consent is necessary",
                   need="Prior consent must always precede the act.",
                   why="The proposed rule treats prior consent as mandatory."),
         "sources": [source]},
        {**finding(label="Notice when required by agreement"),
         "sources": request_hits()["q1"]["candidates"]},
    ]}
    wrong = supported_verdict("r1", "argument")
    wrong["source_checks"][0].update(
        assertion_owner="party", owner_label="Applicant", owner_fragment_id="f1",
        source_treatment=treatment, treatment_fragment_id="f1")
    withheld = {"candidate_id": "r1", "verdict": "unsupported",
                "label_verdict": "unsupported", "label_reason": "The court rejects the position.",
                "material_checks": [], "source_checks": [],
                "reason": "The proposed rule is the rejected contention, not the court's rule."}
    model = Model([{"decisions": [wrong, supported_verdict("r2", "s1")]},
                   {"decisions": [withheld]}])

    checked = verify_findings(model, subjects=(REQUEST_SUBJECT,),
                              material_by_subject={"q1": []}, proposed=proposed,
                              conversation=CONVERSATION)

    assert [row["source_ids"] for row in checked.rows["q1"]] == [["s1"]]
    assert checked.coverage["q1"]["checked_items"] == 2
    assert checked.coverage["q1"]["withheld_items"] == 1
    assert checked.coverage["q1"]["unread_items"] == 0
    assert len(model.calls) == 2
    repair = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in _candidate_rows(repair)] == ["r1"]
    assert "adopted-treatment" in repair["validation_issues"]["r1"]
    assert source["text"] == _candidate_rows(repair)[0]["sources"][0]["fragments"][0]["text"]


@pytest.mark.parametrize("owner,kind", [("party", "principle"),
                                         ("quoted_authority", "support"),
                                         ("deciding_court", "adverse")])
def test_actual_source_adoption_can_support_quoted_or_adverse_reasoning_without_extra_call(
        owner, kind):
    passage = ("The earlier position is that consent must precede the act. "
               "We reject it and adopt the respondent's submission that later consent suffices.")
    source = {"id": "reasoning", "kind": "judgment", "title": "Supplied judgment",
              "locator": "paragraph 4", "text": passage}
    item = {**finding(kind, source_ids=[source["id"]],
                     label="Later consent may suffice", need="The court permits later consent.",
                     why="The court rejects mandatory prior consent and adopts the contrary rule."),
            "sources": [source]}
    decision = supported_verdict("r1", source["id"])
    decision["source_checks"][0].update(
        assertion_owner=owner, owner_label="The identified proposition owner",
        owner_fragment_id="f1", source_treatment="adopted", treatment_fragment_id="f1")
    model = Model([{"decisions": [decision]}])

    checked = verify_findings(model, subjects=(REQUEST_SUBJECT,),
                              material_by_subject={"q1": []}, proposed={"q1": [item]},
                              conversation=CONVERSATION)

    verification = checked.rows["q1"][0]["sources"][0]["verification"]
    assert verification["contract"] == RESEARCH_VERIFICATION
    assert verification["assertion_owner"] == owner
    assert verification["owner_excerpt"] == verification["treatment_excerpt"] == passage
    assert "verification" not in source
    assert len(model.calls) == 1 and model.calls[0][2] is Tier.JUDGE


def test_adopted_role_does_not_override_independent_full_finding_rejection():
    reading = request_read(Model([{"readings": [{"subject_id": "q1",
        "findings": [finding(label="Recipient must compensate the sender",
                             need="The recipient must always compensate the sender.",
                             why="The proposed remedy is said to follow from notice law.")]}]}]))
    decision = supported_verdict("r1", "s1")
    decision.update(verdict="unsupported", reason=(
        "The source does not support the proposed actor, remedy or full limiting predicate."))
    model = Model([{"decisions": [decision]}])

    checked = verify_findings(model, subjects=(REQUEST_SUBJECT,),
                              material_by_subject={"q1": []}, proposed=reading.rows,
                              conversation=CONVERSATION)

    assert checked.rows["q1"] == []
    assert checked.coverage["q1"]["withheld_items"] == 1
    assert len(model.calls) == 1


@pytest.mark.parametrize("field", ["owner_fragment_id", "treatment_fragment_id"])
def test_role_and_treatment_fragment_ids_cannot_resolve_against_a_peer_source(field):
    source = request_hits()["q1"]["candidates"][0]
    peer = {"id": "peer", "kind": "judgment", "title": "Supplied judgment",
            "locator": "paragraph 2", "text": source["text"] * 20}
    proposed = {"q1": [
        {**finding(), "sources": [source]},
        {**finding("support", label="Judgment confirms the conditional notice rule",
                   source_ids=["peer"]), "sources": [peer]},
    ]}
    wrong = supported_verdict("r1", "s1")
    wrong["source_checks"][0][field] = "f2"
    model = Model([{"decisions": [wrong, supported_verdict("r2", "peer")]},
                   {"decisions": [supported_verdict("r1", "s1")]}])
    checked = verify_findings(model, subjects=(REQUEST_SUBJECT,),
                              material_by_subject={"q1": []}, proposed=proposed,
                              conversation=CONVERSATION)
    assert len(checked.rows["q1"]) == 2
    assert len(model.calls) == 2
    repair = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in _candidate_rows(repair)] == ["r1"]
    assert field in repair["validation_issues"]["r1"]
    assert "f2" in repair["validation_issues"]["r1"]


@pytest.mark.parametrize("role,owner", [
    ("court_conclusion", "party"),
    ("court_reasoning", "quoted_authority"),
    ("party_submission", "deciding_court"),
    ("quoted_authority", "deciding_court"),
    ("legislative_text", "deciding_court"),
    ("case_background", "deciding_court"),
    ("unclear", "deciding_court"),
])
def test_used_assertion_role_cannot_change_its_speaker_or_promote_background(role, owner):
    source = dict(id="mixed", kind="judgment", title="Supplied decision", locator="paragraph 4",
                  text="The respondent submits later consent suffices. We adopt that submission.")
    proposed = {"q1": [
        {**finding(source_ids=["mixed"], label="Later consent can suffice"), "sources": [source]},
        {**finding(label="Notice when required by agreement"),
         "sources": request_hits()["q1"]["candidates"]},
    ]}
    wrong = supported_verdict("r1", "mixed")
    wrong["source_checks"][0].update(
        assertion_owner=owner, assertion_role=role,
        assertion_statement="Later consent suffices.", owner_label="The respondent")
    corrected = supported_verdict("r1", "mixed")
    corrected["source_checks"][0].update(
        assertion_owner="party", assertion_role="party_submission",
        assertion_statement="Later consent suffices.", owner_label="The respondent")
    model = Model([{"decisions": [wrong, supported_verdict("r2", "s1")]},
                   {"decisions": [corrected]}])

    checked = verify_findings(model, subjects=(REQUEST_SUBJECT,),
                              material_by_subject={"q1": []}, proposed=proposed,
                              conversation=CONVERSATION)

    assert len(checked.rows["q1"]) == 2
    verification = checked.rows["q1"][0]["sources"][0]["verification"]
    assert verification["assertion_role"] == "party_submission"
    assert verification["assertion_statement"] == "Later consent suffices."
    assert verification["owner_label"] == "The respondent"
    assert verification["source_treatment"] == "adopted"
    assert verification["owner_excerpt"] == verification["treatment_excerpt"] == source["text"]
    assert len(model.calls) == 2
    repair = json.loads(model.calls[1][0].user)
    assert [candidate["candidate_id"] for candidate in _candidate_rows(repair)] == ["r1"]
    assert "assertion_role" in repair["validation_issues"]["r1"]


@pytest.mark.parametrize("statement", ["", "  ", "x" * 501])
def test_used_assertion_requires_a_concise_statement_without_repeating_checked_peers(statement):
    source = request_hits()["q1"]["candidates"][0]
    proposed = {"q1": [{**finding(), "sources": [source]}]}
    wrong = supported_verdict("r1", "s1")
    wrong["source_checks"][0]["assertion_statement"] = statement
    model = Model([{"decisions": [wrong]}, {"decisions": [supported_verdict("r1", "s1")]}])

    checked = verify_findings(model, subjects=(REQUEST_SUBJECT,),
                              material_by_subject={"q1": []}, proposed=proposed,
                              conversation=CONVERSATION)

    assert checked.rows["q1"][0]["sources"][0]["verification"]["assertion_statement"] == source[
        "text"]
    assert len(model.calls) == 2
    fields = model.calls[0][1]["properties"]["decisions"]["items"]["properties"][
        "source_checks"]["items"]["properties"]
    assert "assertion_role" in fields and "assertion_statement" in fields
    assert "binding_status" not in fields and "speaker_label" not in fields


def test_adopted_source_does_not_override_rejection_of_the_used_statement_meaning():
    source = request_hits()["q1"]["candidates"][0]
    proposed = {"q1": [{**finding(), "sources": [source]}]}
    rejected = supported_verdict("r1", "s1")
    rejected.update(verdict="unsupported", reason="The asserted remedy does not follow.")
    rejected["source_checks"][0]["assertion_statement"] = "The recipient must pay damages."
    model = Model([{"decisions": [rejected]}])

    checked = verify_findings(model, subjects=(REQUEST_SUBJECT,),
                              material_by_subject={"q1": []}, proposed=proposed,
                              conversation=CONVERSATION)

    assert checked.rows["q1"] == []
    assert checked.coverage["q1"]["withheld_items"] == 1
    assert len(model.calls) == 1


def use_checks(source_ids, material_ids=(), **failures):
    return {aspect: {
        "verdict": "unsupported" if aspect in failures else "supported",
        "reason": failures.get(aspect, "The selected evidence supports this use decision."),
        "source_ids": list(source_ids), "material_ids": list(material_ids),
    } for aspect in FINDING_USE_CHECKS}


@pytest.mark.parametrize(("aspect", "passage", "need", "reason"), [
    ("application", "Authorized use starts when permission is granted.",
     "Use from the earlier date was authorized by the later permission.",
     "The later permission does not establish authorization for the earlier period."),
    ("application", "Where the specified relationship exists, the actor owes the stated duty.",
     "The actor owes this duty even though the relationship has not been established.",
     "The finding discards the expressed relationship predicate."),
    ("entailment", "Recovery of one remedy and the consequential account were distinct claims.",
     "Two other reported acts cannot be considered together in this matter.",
     "An analogy to different claims does not establish this proposed treatment."),
    ("force", "The claimant in that case supplied a formal record during the hearing.",
     "This party must obtain that formal record before any assessment can proceed.",
     "A case's procedural history does not mandate a prerequisite in another matter."),
    ("force", "A contemporaneous record can help assess the stated event.",
     "A contemporaneous record is a mandatory prerequisite for this claim.",
     "Helpful evidence is not a mandatory legal condition."),
    ("entailment", "The recipient must account for funds received under the stated relationship.",
     "The person asking for an account must establish that they received the funds.",
     "The finding shifts the stated duty from the recipient to another actor."),
])
def test_source_adoption_cannot_override_a_failed_whole_finding_use_check(
        aspect, passage, need, reason):
    source = dict(id="assertion", kind="judgment", title="Synthetic decision",
                  locator="paragraph 3", text=passage)
    earlier = Message("earlier", "advocate", "Use was reported from 2017.")
    later = Message("later", "advocate",
                    "Permission was given in 2022. The relationship is unknown.")
    proposed = {"q1": [
        {**finding("gathering", label="Proposed application", need=need, why=need,
                   source_ids=["assertion"], force="required"), "sources": [source]},
        {**finding(label="Notice remains conditional"),
         "sources": request_hits()["q1"]["candidates"]},
    ]}
    rejected = supported_verdict("r1", "assertion")
    rejected["use_checks"] = use_checks(["assertion"], **{aspect: reason})
    model = Model([{"decisions": [rejected, supported_verdict("r2", "s1")]}])

    checked = verify_findings(model, subjects=(REQUEST_SUBJECT,), material_by_subject={"q1": []},
                              proposed=proposed, conversation=(earlier, later))

    assert [row["label"] for row in checked.rows["q1"]] == ["Notice remains conditional"]
    assert checked.coverage["q1"]["checked_items"] == 2
    assert checked.coverage["q1"]["withheld_items"] == 1
    assert checked.coverage["q1"]["unread_items"] == 0
    audit = checked.coverage["q1"]["rejected_findings"][0]
    assert audit["candidate_id"] == "r1" and audit["reason"] == reason
    assert audit["use_checks"][aspect]["verdict"] == "unsupported"
    assert "sources" not in audit and "use_verification" not in audit
    assert len(model.calls) == 1
    assert conversation_words(json.loads(model.calls[0][0].user)) == [
        {"turn_id": row.turn_id, "role": row.role, "text": row.text} for row in (earlier, later)]
    assert checked.rows["q1"][0]["use_verification"]["contract"] == RESEARCH_VERIFICATION


@pytest.mark.parametrize(("aspect", "field", "ids"), [
    ("entailment", "source_ids", ["peer"]),
    ("application", "material_ids", ["foreign-material"]),
    ("force", "source_ids", ["s1", "s1"]),
    ("entailment", "source_ids", []),
])
def test_use_check_reference_drift_repairs_only_its_candidate(aspect, field, ids):
    source = request_hits()["q1"]["candidates"][0]
    peer = dict(id="peer", kind="provision", title="Synthetic peer rule",
                locator="section 2", text="The identified condition limits the stated obligation.")
    proposed = {"q1": [
        {**finding(), "sources": [source]},
        {**finding(label="A separate conditional proposition", source_ids=["peer"]),
         "sources": [peer]},
    ]}
    wrong = supported_verdict("r1", "s1")
    wrong["use_checks"] = use_checks(["s1"])
    wrong["use_checks"][aspect][field] = ids
    model = Model([{"decisions": [wrong, supported_verdict("r2", "peer")]},
                   {"decisions": [supported_verdict("r1", "s1")]}])

    checked = verify_findings(model, subjects=(REQUEST_SUBJECT,), material_by_subject={"q1": []},
                              proposed=proposed, conversation=CONVERSATION)

    assert len(checked.rows["q1"]) == 2 and len(model.calls) == 2
    repair = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in _candidate_rows(repair)] == ["r1"]
    assert "use_checks" in repair["validation_issues"]["r1"]


def test_established_application_needs_attributed_material_not_only_a_legal_passage():
    source = request_hits()["q1"]["candidates"][0]
    proposed = {"q1": [{**finding(), "sources": [source]}]}
    wrong = supported_verdict("r1", "s1")
    wrong["source_checks"][0].update(scope_status="established", scope_fragment_id="f1")
    corrected = supported_verdict("r1", "s1")
    corrected["source_checks"][0].update(scope_status="conditional", scope_fragment_id="f1")
    model = Model([{"decisions": [wrong]}, {"decisions": [corrected]}])

    checked = verify_findings(model, subjects=(REQUEST_SUBJECT,), material_by_subject={"q1": []},
                              proposed=proposed, conversation=CONVERSATION)

    assert len(model.calls) == 2
    assert checked.rows["q1"][0]["sources"][0]["verification"]["scope_status"] == "conditional"
    assert checked.rows["q1"][0]["use_verification"]["checks"]["application"]["material_ids"] == []
    feedback = json.loads(model.calls[1][0].user)["validation_issues"]["r1"]
    assert "application.material_ids" in feedback and "legal source words" in feedback


@pytest.mark.parametrize("treatment", ["rejected", "adopted", "reported", "unclear"])
def test_party_position_and_court_response_remain_separate_from_operative_support(treatment):
    party_words = "The applicant submits that prior consent is always necessary. "
    court_words = {
        "rejected": "We reject the applicant's submission. ",
        "adopted": "We adopt the applicant's submission. ",
        "reported": "We merely record the applicant's submission without deciding it. ",
        "unclear": "",
    }[treatment] + "The court concludes that the stated exception governs this request."
    source = dict(id="mixed", kind="judgment", title="Supplied decision", locator="paragraph 5",
                  text=party_words + "The background remains disputed. " * 23 + court_words)
    item = {**finding(source_ids=["mixed"], need="The stated exception governs the request.",
                     label="The governing exception", why="The court applies the exception."),
            "sources": [source]}
    verdict = supported_verdict("r1", "mixed")
    verdict["source_checks"][0].update(
        assertion_owner="deciding_court", assertion_role="court_conclusion",
        assertion_statement="The stated exception governs this request.",
        owner_label="The deciding court", support_fragment_id="f2",
        owner_fragment_id="f2", treatment_fragment_id="f2",
        context_statements=[dict(
            assertion_owner="party", assertion_role="party_submission",
            assertion_statement="Prior consent is always necessary.", owner_label="The applicant",
            source_treatment=treatment, support_fragment_id="f1", owner_fragment_id="f1",
            treatment_fragment_id="f2")])
    model = Model([{"decisions": [verdict]}])

    checked = verify_findings(model, subjects=(REQUEST_SUBJECT,),
                              material_by_subject={"q1": []}, proposed={"q1": [item]},
                              conversation=CONVERSATION)

    kept = checked.rows["q1"][0]
    verification = kept["sources"][0]["verification"]
    assert kept["source_ids"] == ["mixed"]
    assert verification["assertion_role"] == "court_conclusion"
    assert verification["assertion_statement"] == "The stated exception governs this request."
    assert verification["source_treatment"] == "adopted"
    context = verification["context_statements"][0]
    assert context["assertion_role"] == "party_submission"
    assert context["owner_label"] == "The applicant"
    assert context["source_treatment"] == treatment
    assert party_words.strip() in context["support_excerpt"]
    assert court_words in context["treatment_excerpt"]
    assert not {"source_id", "scope_status", "force"} & context.keys()
    assert len(model.calls) == 1 and model.calls[0][2] is Tier.JUDGE


def test_context_cannot_promote_a_rejected_party_position_to_primary_law():
    source = dict(id="mixed", kind="judgment", title="Supplied decision", locator="paragraph 5",
                  text="The applicant submits prior consent is mandatory. We reject that position.")
    proposed = {"q1": [{**finding(source_ids=["mixed"]), "sources": [source]}]}
    wrong = supported_verdict("r1", "mixed")
    wrong["source_checks"][0].update(
        assertion_role="party_submission", assertion_owner="party", owner_label="The applicant",
        source_treatment="rejected", assertion_statement="Prior consent is mandatory.",
        context_statements=[])
    model = Model([{"decisions": [wrong]}])

    checked = verify_findings(model, subjects=(REQUEST_SUBJECT,),
                              material_by_subject={"q1": []}, proposed=proposed,
                              conversation=CONVERSATION)

    assert checked.rows["q1"] == []
    assert checked.coverage["q1"]["unread_items"] == 1
    assert len(model.calls) == 2


def test_context_fragment_cannot_borrow_another_sources_words_or_repeat_valid_peers():
    source = request_hits()["q1"]["candidates"][0]
    peer = dict(id="peer", kind="judgment", title="Supplied decision", locator="paragraph 6",
                text="The applicant submits that notice is unnecessary. " * 30)
    proposed = {"q1": [
        {**finding(), "sources": [source]},
        {**finding("support", source_ids=["peer"], label="Related reasoning"), "sources": [peer]},
    ]}
    wrong = supported_verdict("r1", "s1")
    wrong["source_checks"][0]["context_statements"] = [dict(
        assertion_owner="legislative_text", assertion_role="legislative_text",
        assertion_statement="Notice is required.", owner_label="The issuing source",
        source_treatment="reported", support_fragment_id="f1", owner_fragment_id="f2",
        treatment_fragment_id="f1")]
    model = Model([{"decisions": [wrong, supported_verdict("r2", "peer")]},
                   {"decisions": [supported_verdict("r1", "s1")]}])

    checked = verify_findings(model, subjects=(REQUEST_SUBJECT,),
                              material_by_subject={"q1": []}, proposed=proposed,
                              conversation=CONVERSATION)

    assert len(checked.rows["q1"]) == 2
    assert len(model.calls) == 2
    repair = json.loads(model.calls[1][0].user)
    assert [candidate["candidate_id"] for candidate in _candidate_rows(repair)] == ["r1"]
    assert "context_statements[0].owner_fragment_id" in repair["validation_issues"]["r1"]


def application_premise(source_id="condition", *, status="unresolved", ids=(),
                        condition="If consent covered the relevant period, check its terms."):
    return {"source_id": source_id, "predicate_fragment_id": "f1", "status": status,
            "account_source_ids": list(ids), "preserved_condition": condition,
            "reason": "The reported dates do not establish the condition throughout the period."}


def application_case():
    source = dict(id="condition", kind="provision", title="Synthetic rule", locator="section 4",
                  text="Where consent covers the relevant period, its terms govern that use.")
    candidate = {**finding(source_ids=["condition"], label="Check the scope of consent",
                          need="If consent covered the relevant period, check its terms."),
                 "sources": [source]}
    conversation = (
        Message("early", "advocate", "Use began in 2016."),
        Message("early", "nm", "The use was authorised from the outset."),
        Message("later", "advocate",
                "Consent was first given in 2021. Its earlier reach is unknown."),
    )
    return candidate, conversation


def conditional_application_decision(candidate_id="r1"):
    decision = supported_verdict(candidate_id, "condition")
    decision["source_checks"][0].update(scope_status="conditional", scope_fragment_id="f1")
    decision["application_premises"] = [application_premise(ids=("P1S1", "P3S1", "P3S2"))]
    return decision


def test_application_preserves_exact_account_chronology_without_repeating_transcript_text():
    candidate, conversation = application_case()
    model = Model([{"decisions": [conditional_application_decision()]}])

    result = verify_findings(model, subjects=(REQUEST_SUBJECT,), material_by_subject={"q1": []},
                             proposed={"q1": [candidate]}, conversation=conversation)

    premise = result.rows["q1"][0]["use_verification"]["application_premises"][0]
    assert premise["status"] == "unresolved"
    assert premise["preserved_condition"] in candidate["need"]
    assert premise["predicate_excerpt"] == candidate["sources"][0]["text"]
    assert premise["account_references"] == [
        {"turn_id": "early", "role": "advocate", "quoted": "Use began in 2016."},
        {"turn_id": "later", "role": "advocate", "quoted": "Consent was first given in 2021."},
        {"turn_id": "later", "role": "advocate", "quoted": "Its earlier reach is unknown."},
    ]
    payload = json.loads(model.calls[0][0].user)
    assert conversation_words(payload) == [vars(message) for message in conversation]
    assert all("text" not in row and row["source_spans"] for row in payload["conversation"])
    assert len(model.calls) == 1


@pytest.mark.parametrize("damage", [
    "missing_predicate", "nm_only_account", "unknown_account", "unpreserved_condition",
    "condition_outside_proposal", "foreign_source", "foreign_fragment",
    "reported_without_account", "contradicted_without_account", "duplicate_predicate",
])
def test_application_contract_failure_repairs_only_its_candidate_and_preserves_valid_peer(damage):
    candidate, conversation = application_case()
    peer = {**finding(label="Independent supported point"),
            "sources": request_hits()["q1"]["candidates"]}
    wrong = conditional_application_decision()
    premise = wrong["application_premises"][0]
    if damage == "missing_predicate":
        wrong["application_premises"] = []
    elif damage == "nm_only_account":
        premise.update(status="reported_satisfied", account_source_ids=["P2S1"],
                       preserved_condition="")
    elif damage == "unknown_account":
        premise["account_source_ids"] = ["unavailable"]
    elif damage == "unpreserved_condition":
        premise["preserved_condition"] = ""
    elif damage == "condition_outside_proposal":
        premise["preserved_condition"] = "An invented qualifier absent from the proposed finding."
    elif damage == "foreign_source":
        premise["source_id"] = "s1"
    elif damage == "foreign_fragment":
        premise["predicate_fragment_id"] = "f90"
    elif damage == "reported_without_account":
        premise.update(status="reported_satisfied", account_source_ids=[], preserved_condition="")
    elif damage == "contradicted_without_account":
        premise.update(status="reported_contradicted", account_source_ids=[])
    else:
        wrong["application_premises"] *= 2
    model = Model([{"decisions": [wrong, supported_verdict("r2", "s1")]},
                   {"decisions": [conditional_application_decision()]}])

    result = verify_findings(model, subjects=(REQUEST_SUBJECT,), material_by_subject={"q1": []},
                             proposed={"q1": [candidate, peer]}, conversation=conversation)

    assert len(result.rows["q1"]) == 2
    assert result.coverage["q1"]["checked_items"] == 2
    assert len(model.calls) == 2
    repair = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in _candidate_rows(repair)] == ["r1"]
    assert "r1" in repair["validation_issues"] and "r2" not in repair["validation_issues"]


def test_unconditional_application_cannot_retain_unresolved_predicate_as_established():
    candidate, conversation = application_case()
    candidate["material_ids"] = ["reported"]
    material = {"q1": [{"id": "reported", "quoted": "Use began in 2016.",
                        "source_turn_id": "early", "basis": "stated"}]}
    subject = {**REQUEST_SUBJECT, "scope": "current", "record_ids": ["reported"]}
    wrong = conditional_application_decision()
    wrong["source_checks"][0]["scope_status"] = "established"
    wrong["use_checks"] = use_checks(["condition"], ["reported"])
    fixed = conditional_application_decision()
    model = Model([{"decisions": [wrong]}, {"decisions": [fixed]}])

    result = verify_findings(model, subjects=(subject,), material_by_subject=material,
                             proposed={"q1": [candidate]}, conversation=conversation)

    assert result.rows["q1"][0]["sources"][0]["verification"]["scope_status"] == "conditional"
    assert len(model.calls) == 2


def test_repeated_exact_account_reference_is_normalised_after_every_id_is_validated():
    candidate, conversation = application_case()
    decision = conditional_application_decision()
    decision["application_premises"][0]["account_source_ids"] *= 2
    model = Model([{"decisions": [decision]}])

    result = verify_findings(model, subjects=(REQUEST_SUBJECT,), material_by_subject={"q1": []},
                             proposed={"q1": [candidate]}, conversation=conversation)

    assert len(result.rows["q1"][0]["use_verification"]["application_premises"][0][
        "account_references"]) == 3
    assert len(model.calls) == 1


def test_attributed_contradiction_can_support_only_an_explicitly_conditional_enquiry():
    candidate, conversation = application_case()
    decision = conditional_application_decision()
    decision["application_premises"][0]["status"] = "reported_contradicted"
    model = Model([{"decisions": [decision]}])

    result = verify_findings(model, subjects=(REQUEST_SUBJECT,), material_by_subject={"q1": []},
                             proposed={"q1": [candidate]}, conversation=conversation)

    assert result.rows["q1"][0]["use_verification"]["application_premises"][0]["status"] == (
        "reported_contradicted")
    assert result.rows["q1"][0]["need"] == candidate["need"]
    assert len(model.calls) == 1


@pytest.mark.parametrize("damage", ["missing_need", "nonstring_need", "missing_why",
                                    "wrong_predicate", "wrong_source_shape"])
def test_current_application_readback_rejects_corrupt_contract_without_throwing(damage):
    candidate, conversation = application_case()
    result = verify_findings(Model([{"decisions": [conditional_application_decision()]}]),
                             subjects=(REQUEST_SUBJECT,), material_by_subject={"q1": []},
                             proposed={"q1": [candidate]}, conversation=conversation)
    row = result.rows["q1"][0]
    if damage == "missing_need":
        row.pop("need")
    elif damage == "nonstring_need":
        row["need"] = None
    elif damage == "missing_why":
        row.pop("why")
    elif damage == "wrong_predicate":
        row["use_verification"]["application_premises"][0]["predicate_excerpt"] = (
            "its terms govern that use.")
    else:
        row["sources"][0].pop("id")

    assert finding_verification_valid(row) is False


def test_historical_v4_use_remains_checked_history_without_inventing_application_premises():
    candidate, conversation = application_case()
    result = verify_findings(Model([{"decisions": [conditional_application_decision()]}]),
                             subjects=(REQUEST_SUBJECT,), material_by_subject={"q1": []},
                             proposed={"q1": [candidate]}, conversation=conversation)
    row = result.rows["q1"][0]
    row["sources"][0]["verification"]["contract"] = "research_support_v4"
    row["use_verification"]["contract"] = "research_support_v4"
    row["use_verification"].pop("application_premises")

    assert finding_verification_valid(row, contract="research_support_v4") is True
    assert finding_verification_valid(row) is False
    assert "application_premises" not in row["use_verification"]
    row["use_verification"]["checks"]["application"]["verdict"] = "unsupported"
    assert finding_verification_valid(row, contract="research_support_v4") is False
