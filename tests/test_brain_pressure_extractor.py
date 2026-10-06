"""Unfamiliar passages and fabricated replies through the shipped detail reader.

These cases exercise mechanical admission and bounded correction, without a
provider. An admitted false statement is recorded as a semantic dependency;
an omitted valid sibling is recorded as an unprotected extraction repair gap.
Neither is presented as a successful protection merely because pytest passes.
"""

import json
from copy import deepcopy

import pytest

from nm.brain.conversation import Message
from nm.brain.material import extract_details
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ModelResult,
    SchemaViolation,
    Tier,
    Usage,
    require_schema,
)
from tests.brain_pressure_support import record_case

LATEST = (
    "For this file, correct only the packing-line handover to 17 November, "
    "not 18 November. The warehouse delivery may have occurred on 21 November, "
    "but the guard has not checked the register. The supplier's letter says "
    "the test run was offered for 22 November, which we dispute. On another "
    "client's file, the machinery was seized on 8 December."
)
EARLIER = (
    Message("packing-original", "advocate", "The packing line was handed over on "
            "18 November. The warehouse delivery was on 21 November."),
    Message("packing-original", "nm", "I treated the packing-line date as final "
            "and assumed the warehouse delivery was verified."),
    Message("packing-review", "advocate", "The warehouse guard still needs to "
            "check the register. Please keep the two events separate."),
)
SAVED = {
    "id": "packing-original:material:1", "kind": "event",
    "statement": "The advocate reports packing-line handover on 18 November.",
    "quoted": "The packing line was handed over on 18 November.",
    "source_turn_id": "packing-original", "matter_scope": "current",
    "placement": "matter", "dispute_ids": [], "relation": "new",
    "related_material_ids": [], "basis": "stated", "importance": "central",
    "why_material": "The handover chronology affects the reported performance.",
    "prior_references": [],
}
DISPUTE = {
    "id": "packing-performance", "label": "Contested equipment performance",
    "statement": "The parties dispute packing-line performance and handover.",
    "source_turn_id": "packing-original", "quoted": SAVED["quoted"],
    "matter_scope": "current",
}


class ScriptedExtractor:
    """Submit exact fabricated wire objects, with no test-side repair/inference."""

    def __init__(self, outputs, *, completion=Completion.COMPLETE, strict=False):
        self.outputs = deepcopy(outputs)
        self.completion = completion
        self.strict = strict
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.ROUTINE
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        index = len(self.calls)
        assert index < len(self.outputs), "Unexpected additional extractor call"
        data = deepcopy(self.outputs[index])
        self.calls.append({
            "operation": prompt.operation, "tier": tier.value,
            "input": json.loads(prompt.user), "max_tokens": max_tokens,
            "fabricated_output": deepcopy(data),
            "schema_boundary": "strict_adapter_then_brain" if self.strict
            else "permissive_transport_then_brain",
        })
        if self.strict:
            try:
                require_schema(data, schema)
            except SchemaViolation as exc:
                self.calls[-1]["adapter_schema_error"] = str(exc)
                raise
        return ModelResult(text=None, data=data, tier=tier, provider="offline",
                           model="fabricated-pressure-extractor",
                           usage=Usage(0, 0, 0), latency_ms=0,
                           completion=self.completion)


def row(source="L1", statement=None, *, assignment="matter:discussion",
        basis="stated", kind="event"):
    return {
        "kind": kind,
        "statement": statement or "The advocate corrects packing-line handover "
        "to 17 November, not 18 November.",
        "source_id": source, "prior_source_ids": [],
        "assignment_ids": [assignment], "basis": basis,
        "importance": "relevant",
        "why_material": "The independently reported chronology affects "
        "performance and the next evidence review.",
    }


def output(*new_rows, changes=()):
    return {"new_items": list(new_rows), "changes": list(changes)}


def change(**overrides):
    return {**row(), "relation": "corrects",
            "related_material_ids": [SAVED["id"]], **overrides}


def run(outputs, *, latest=LATEST, earlier=EARLIER, saved=(SAVED,),
        disputes=(DISPUTE,), completion=Completion.COMPLETE, strict=False):
    model = ScriptedExtractor(outputs, completion=completion, strict=strict)
    try:
        candidates = extract_details(
            model, earlier=earlier, latest=latest,
            current_matter_id="pressure-packing", disputes=disputes,
            prior_material=saved)
        return model, candidates, None
    except SchemaViolation as exc:
        return model, (), exc


def evidence(case_id, passage, outputs, model, expected, observed, *,
             scenario="faulty", claim_scope="mechanical",
             protection_status="blocked", notes=""):
    return record_case(
        case_id, boundary="nm.brain.material.extract_details / checked_read",
        user_passage=passage, model_outputs=outputs,
        expected=expected, observed=observed, calls=model.calls,
        scenario=scenario, claim_scope=claim_scope,
        protection_status=protection_status, notes=notes)


def test_pressure_extractor_mixed_correction_uncertainty_and_other_file():
    outputs = [output(
        row("L2", "Warehouse delivery may have occurred on 21 November; "
            "the guard has not checked the register.", basis="uncertain"),
        row("L3", "The supplier's letter reportedly offers a test run for "
            "22 November; the advocate disputes that account.",
            basis="described_record", kind="evidence"),
        row("L4", "Another client's machinery was seized on 8 December.",
            assignment="matter:other"), changes=[change()])]
    model, candidates, exc = run(outputs)
    observed = {
        "admitted": exc is None, "calls": len(model.calls),
        "count": len(candidates),
        "scope_basis": [(c.matter_scope, c.basis) for c in candidates],
        "changed_owned_id": list(candidates[-1].related_material_ids),
        "exact_quotes": all(c.quoted in LATEST for c in candidates),
    }
    evidence("extractor-01-mixed-owned-uncertain-other", LATEST, outputs, model,
             {"admitted": True, "calls": 1, "count": 4,
              "scope_basis": [("current", "uncertain"),
                              ("current", "described_record"),
                              ("other", "stated"), ("current", "stated")],
              "changed_owned_id": [SAVED["id"]], "exact_quotes": True},
             observed, scenario="legitimate", protection_status="admitted",
             notes="Other-file attribution is held as other scope, not silently "
             "reassigned. This boundary returns proposals, not saved effects.")


def test_pressure_extractor_repeated_exact_owned_assignment_is_harmless():
    proposed = row(assignment=DISPUTE["id"])
    proposed["assignment_ids"] *= 3
    outputs = [output(proposed)]
    model, candidates, exc = run(outputs)
    evidence("extractor-02-duplicate-owned-assignment", LATEST, outputs, model,
             {"admitted": True, "calls": 1, "dispute_ids": [DISPUTE["id"]]},
             {"admitted": exc is None, "calls": len(model.calls),
              "dispute_ids": list(candidates[0].dispute_ids)},
             scenario="legitimate", protection_status="admitted",
             notes="Exact repeated owned IDs are normalized without a retry.")


def test_pressure_extractor_repeated_prior_source_is_losslessly_normalized():
    proposed = change(prior_source_ids=["P1S1", "P1S1", "P1S1"])
    outputs = [output(changes=[proposed])]
    model, candidates, exc = run(outputs)
    evidence("extractor-03-duplicate-prior-source", LATEST, outputs, model,
             {"admitted": True, "calls": 1, "prior_count": 1,
              "prior_quote": SAVED["quoted"]},
             {"admitted": exc is None, "calls": len(model.calls),
              "prior_count": len(candidates[0].prior_references),
              "prior_quote": candidates[0].prior_references[0].quoted},
             scenario="legitimate", protection_status="admitted")


def test_pressure_extractor_preserves_long_meaningful_output():
    conditions = " ".join(
        f"Batch {index} remains subject to the reported calibration condition "
        f"for station {index}, with its inspection record still unavailable."
        for index in range(1, 25))
    passage = "The advocate reports one combined acceptance condition: " + conditions
    statement = "The combined acceptance condition remains qualified as follows: " + conditions
    proposed = row(statement=statement, basis="uncertain", kind="circumstance")
    outputs = [output(proposed)]
    model, candidates, exc = run(outputs, latest=passage)
    evidence("extractor-04-long-qualified-statement", passage, outputs, model,
             {"admitted": True, "calls": 1, "statement_preserved": True,
              "over_2000_characters": True, "full_input_preserved": True},
             {"admitted": exc is None, "calls": len(model.calls),
              "statement_preserved": candidates[0].statement == statement,
              "over_2000_characters": len(candidates[0].statement) > 2000,
              "full_input_preserved": "".join(
                  s["text"] for s in model.calls[0]["input"]["latest_message_spans"])
              == passage}, scenario="legitimate", protection_status="admitted",
             notes="No arbitrary statement-length rejection. Exact citations "
             "still address only selected server windows; semantic support "
             "across multiple windows belongs to independent review.")


@pytest.mark.parametrize("case_id,mutate,issue_fragment", [
    ("extractor-05-empty-materiality-reason", lambda r: r.update(why_material=" \t "),
     "materiality reason"),
    ("extractor-06-empty-statement", lambda r: r.update(statement=" \n "),
     "nonempty statement"),
    ("extractor-07-mixed-assignment", lambda r: r.update(
        assignment_ids=[DISPUTE["id"], "matter:other"]), "not mixed targets"),
])
def test_pressure_extractor_precise_fault_then_valid_neighbour_recovers(
        case_id, mutate, issue_fragment):
    good = row()
    bad = deepcopy(good)
    mutate(bad)
    outputs = [output(bad), output(good)]
    model, candidates, exc = run(outputs)
    repair = model.calls[1]["input"]
    evidence(case_id, LATEST, outputs, model,
             {"admitted": True, "calls": 2, "corrected_statement": good["statement"],
              "precise_issue": True, "rejected_output_preserved": True,
              "original_input_preserved": True},
             {"admitted": exc is None, "calls": len(model.calls),
              "corrected_statement": candidates[0].statement,
              "precise_issue": issue_fragment in repair["validation_issue"],
              "rejected_output_preserved": repair["rejected_output"] == outputs[0],
              "original_input_preserved": repair["original_input"]
              == model.calls[0]["input"]}, protection_status="recovered")


@pytest.mark.parametrize("case_id,mutate", [
    ("extractor-08-foreign-latest-source", lambda r: r.update(source_id="L999")),
    ("extractor-09-foreign-dispute-target", lambda r: r.update(
        assignment_ids=["other-owner:dispute:7"])),
    ("extractor-10-foreign-prior-source", lambda r: r.update(
        prior_source_ids=["P999S1"])),
    ("extractor-11-injected-placement-field", lambda r: r.update(
        placement="disputes")),
])
def test_pressure_extractor_foreign_reference_or_redundant_assignment_never_admits(
        case_id, mutate):
    bad = row()
    mutate(bad)
    outputs = [output(bad), output(bad)]
    model, candidates, exc = run(outputs)
    evidence(case_id, LATEST, outputs, model,
             {"blocked": True, "calls": 2, "admitted_count": 0,
              "original_input_preserved": True},
             {"blocked": isinstance(exc, SchemaViolation),
              "calls": len(model.calls), "admitted_count": len(candidates),
              "original_input_preserved": model.calls[1]["input"]["original_input"]
              == model.calls[0]["input"]},
             notes="Ownership and assignment are decided from declared IDs. "
             "Placement is code-derived; this test does not label any arbitrary "
             "format variation as a factual error.")


def test_pressure_extractor_new_cannot_masquerade_as_change():
    bad = change(relation="new")
    good = change()
    outputs = [output(changes=[bad]), output(changes=[good])]
    model, candidates, exc = run(outputs)
    evidence("extractor-12-new-in-change-recovered", LATEST, outputs, model,
             {"admitted": True, "calls": 2, "relation": "corrects",
              "target": [SAVED["id"]]},
             {"admitted": exc is None, "calls": len(model.calls),
              "relation": candidates[0].relation,
              "target": list(candidates[0].related_material_ids)},
             protection_status="recovered",
             notes="The explicit creation/revision contract prevents a new "
             "proposition from retiring an earlier saved detail.")


def test_pressure_extractor_owned_link_attaches_missing_original_words():
    outputs = [output(changes=[change(prior_source_ids=[])])]
    model, candidates, exc = run(outputs)
    evidence("extractor-13-owned-link-derived-source", LATEST, outputs, model,
             {"admitted": True, "calls": 1,
              "source_turn_id": "packing-original", "role": "advocate",
              "quoted": SAVED["quoted"]},
             {"admitted": exc is None, "calls": len(model.calls),
              "source_turn_id": candidates[0].prior_references[0].turn_id,
              "role": candidates[0].prior_references[0].role,
              "quoted": candidates[0].prior_references[0].quoted},
             scenario="legitimate", protection_status="admitted",
             notes="Original-source transport is derived from the selected "
             "owned saved record, not fabricated or demanded redundantly.")


def test_pressure_extractor_false_fact_with_exact_quote_is_semantic_dependency():
    false_statement = "Packing-line handover was conclusively verified on "
    false_statement += "30 November, and the supplier admitted breach."
    outputs = [output(row(statement=false_statement))]
    model, candidates, exc = run(outputs)
    evidence("extractor-14-wrong-fact-exact-source", LATEST, outputs, model,
             {"proposal_admitted": True, "calls": 1,
              "false_statement_preserved": True, "exact_quote": True},
             {"proposal_admitted": exc is None, "calls": len(model.calls),
              "false_statement_preserved": candidates[0].statement == false_statement,
              "exact_quote": candidates[0].quoted
              == "For this file, correct only the packing-line handover to "
              "17 November, not 18 November."},
             claim_scope="semantic_dependency", protection_status="gap_demonstrated",
             notes="Exact citation ownership does not prove statement truth. "
             "The extractor mechanically admits this proposal; independent "
             "grounding review must reject it. This is not a released reply.")


def test_pressure_extractor_whole_repair_can_drop_previous_valid_sibling():
    good = row("L2", "Warehouse delivery may have occurred on 21 November; "
               "the register remains unchecked.", basis="uncertain")
    faulty = row("L3", "The letter is disputed.")
    faulty["why_material"] = ""
    repaired = {**faulty, "why_material": "The disputed offered test date "
                "bears on performance chronology."}
    outputs = [output(good, faulty), output(repaired)]
    model, candidates, exc = run(outputs)
    evidence("extractor-15-repair-drops-valid-sibling", LATEST, outputs, model,
             {"admitted": True, "calls": 2, "count": 1,
              "previous_valid_sibling_retained": False,
              "previous_valid_sibling_in_repair_context": True},
             {"admitted": exc is None, "calls": len(model.calls),
              "count": len(candidates),
              "previous_valid_sibling_retained": any(
                  c.statement == good["statement"] for c in candidates),
              "previous_valid_sibling_in_repair_context": good in
              model.calls[1]["input"]["rejected_output"]["new_items"]},
             scenario="mixed", claim_scope="known_gap",
             protection_status="gap_demonstrated",
             notes="Extractor correction replaces the full batch. The prior "
             "valid proposal is supplied in correction context but is not "
             "mechanically retained. Later coverage can report the omission; "
             "this boundary does not restore it.")


def test_pressure_extractor_repeat_bad_reason_stops_after_one_correction():
    bad = row()
    bad["why_material"] = ""
    outputs = [output(bad), output(bad)]
    model, candidates, exc = run(outputs)
    evidence("extractor-16-repeat-bad-bounded", LATEST, outputs, model,
             {"blocked": True, "calls": 2, "count": 0,
              "whole_history_and_current_retained": True},
             {"blocked": isinstance(exc, SchemaViolation),
              "calls": len(model.calls), "count": len(candidates),
              "whole_history_and_current_retained":
              model.calls[1]["input"]["original_input"]
              == model.calls[0]["input"]},
             notes="One repair only; no silent success or unbounded retry.")


def test_pressure_extractor_empty_envelope_is_not_completeness_proof():
    outputs = [output()]
    model, candidates, exc = run(outputs)
    evidence("extractor-17-empty-is-proposal-only", LATEST, outputs, model,
             {"empty_proposals_admitted": True, "calls": 1, "count": 0},
             {"empty_proposals_admitted": exc is None,
              "calls": len(model.calls), "count": len(candidates)},
             claim_scope="semantic_dependency", protection_status="gap_demonstrated",
             notes="Empty JSON is structurally valid. Independent whole-account "
             "coverage owns whether this substantial passage was actually "
             "covered; extract_details alone cannot establish completeness.")


def test_pressure_extractor_correction_preserves_complete_input_and_provenance():
    bad = row()
    bad["why_material"] = ""
    good = row()
    outputs = [output(bad), output(good)]
    model, candidates, exc = run(outputs)
    original = model.calls[1]["input"]["original_input"]
    active = original["active_material"][0]
    observed = {
        "admitted": exc is None, "calls": len(model.calls),
        "latest_preserved": "".join(s["text"] for s in
                                    original["latest_message_spans"]) == LATEST,
        "history_preserved": [
            (m["turn_id"], m["role"], "".join(s["text"] for s in m["source_spans"]))
            for m in original["earlier_conversation"]]
        == [(m.turn_id, m.role, m.text) for m in EARLIER],
        "provenance_preserved": all(active[key] == SAVED[key] for key in
                                    ("basis", "importance", "why_material",
                                     "prior_references")),
        "model_record_labelled_derived": active["record_role"] == "nm_interpretation",
        "count": len(candidates),
    }
    evidence("extractor-18-repair-complete-context-provenance", LATEST, outputs,
             model, {"admitted": True, "calls": 2, "latest_preserved": True,
                     "history_preserved": True, "provenance_preserved": True,
                     "model_record_labelled_derived": True, "count": 1},
             observed, scenario="mixed", protection_status="recovered")


def test_pressure_extractor_strict_adapter_rejection_preserves_original_not_output():
    bad = row(source="L999")
    good = row()
    outputs = [output(bad), output(good)]
    model, candidates, exc = run(outputs, strict=True)
    repair = model.calls[1]["input"]
    evidence("extractor-19-strict-source-rejection-recovered", LATEST, outputs,
             model,
             {"admitted": True, "calls": 2, "adapter_rejected_first_output": True,
              "rejected_output_unavailable_to_brain": True,
              "complete_original_input_preserved": True,
              "corrected_statement": good["statement"]},
             {"admitted": exc is None, "calls": len(model.calls),
              "adapter_rejected_first_output": "adapter_schema_error"
              in model.calls[0],
              "rejected_output_unavailable_to_brain": repair["rejected_output"] is None,
              "complete_original_input_preserved": repair["original_input"]
              == model.calls[0]["input"],
              "corrected_statement": candidates[0].statement},
             protection_status="recovered",
             notes="The strict transport invokes actual require_schema before "
             "returning ModelResult. Brain correction receives the adapter "
             "issue and original input, but no rejected structured object. "
             "Earlier permissive-transport cases explicitly exercise schema "
             "validation at the Brain owning boundary instead.")


def test_pressure_extractor_strict_envelope_hides_valid_sibling_before_correction():
    good = row("L2", "Warehouse delivery may have occurred on 21 November; "
               "the register remains unchecked.", basis="uncertain")
    bad = row("L999", "The supplier's letter is disputed.", kind="evidence")
    repaired = {**bad, "source_id": "L3"}
    outputs = [output(good, bad), output(repaired)]
    model, candidates, exc = run(outputs, strict=True)
    repair = model.calls[1]["input"]
    evidence("extractor-20-strict-hidden-sibling-gap", LATEST, outputs, model,
             {"admitted": True, "calls": 2, "count": 1,
              "adapter_rejected_first_envelope": True,
              "previous_valid_sibling_retained": False,
              "first_envelope_available_in_repair_context": False,
              "complete_original_input_preserved": True},
             {"admitted": exc is None, "calls": len(model.calls),
              "count": len(candidates),
              "adapter_rejected_first_envelope": "adapter_schema_error"
              in model.calls[0],
              "previous_valid_sibling_retained": any(
                  c.statement == good["statement"] for c in candidates),
              "first_envelope_available_in_repair_context":
              repair["rejected_output"] is not None,
              "complete_original_input_preserved": repair["original_input"]
              == model.calls[0]["input"]},
             scenario="mixed", claim_scope="known_gap",
             protection_status="gap_demonstrated",
             notes="Whole-envelope adapter rejection happens before Brain sees "
             "either sibling. The accepted correction omits the sound first "
             "proposal. This characterizes hidden-peer loss, not proof of "
             "first-attempt retention or extraction completeness.")
