"""Offline paired boundary tests for the proposed generic proposal reader."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass

import pytest

from nm.brain import checked as _full_helpers
from nm.brain.checked import checked_unit_read
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ContentRefused,
    ContextOverflow,
    ModelResult,
    OutputTruncated,
    Prompt,
    ProviderUnavailable,
    RateLimited,
    SchemaViolation,
    Tier,
    TierUnavailable,
    Usage,
    estimate_tokens,
    require_schema,
)

SOURCES = {"S1": "The handover was reported for Thursday.",
           "S2": "A separate receipt has not yet been checked."}
FIELDS = ("observations", "revisions")
ROW = {"type": "object", "additionalProperties": False,
       "required": ["text", "source_id", "target_ids"], "properties": {
           "text": {"type": "string", "minLength": 1},
           "source_id": {"type": "string", "enum": list(SOURCES)},
           "target_ids": {"type": "array", "items": {
               "type": "string", "enum": ["R1", "R2"]}}}}
SCHEMA = {"type": "object", "additionalProperties": False,
          "required": list(FIELDS), "properties": {
              "observations": {"type": "array", "items": deepcopy(ROW)},
              "revisions": {"type": "array", "items": deepcopy(ROW)}}}
SCHEMA["properties"]["observations"]["items"]["properties"]["target_ids"]["maxItems"] = 0
SCHEMA["properties"]["revisions"]["items"]["properties"]["target_ids"]["minItems"] = 1
PROMPT = Prompt(system="Message: original input. Purpose: propose independent units. "
                "Look for: attributed sources. Outcome: declared proposal arrays.",
                user=json.dumps({"original_account": SOURCES,
                                 "current_instruction": "Review the saved account."}),
                operation="candidate_unit_read")


@dataclass(frozen=True)
class Proposal:
    text: str
    source: str
    targets: tuple[str, ...]


def row(text="The account remains tentative.", source="S1", targets=()):
    return {"text": text, "source_id": source, "target_ids": list(targets)}


def envelope(observations=(), revisions=()):
    return {"observations": list(observations), "revisions": list(revisions)}


def accept(data):
    values = []
    for field in FIELDS:
        for value in data[field]:
            if not value["text"].strip():
                raise SchemaViolation("A proposal requires substantive text")
            if any(target != {"S1": "R1", "S2": "R2"}[value["source_id"]]
                   for target in value["target_ids"]):
                raise SchemaViolation("A revision must cite its owned target's original source")
            values.append(Proposal(value["text"], value["source_id"],
                                   tuple(dict.fromkeys(value["target_ids"]))))
    return tuple(values)


class Model:
    def __init__(self, outputs, *, strict=False, completions=None, budget=100_000,
                 returned_tier=None, downgrade=None):
        self.outputs, self.strict = deepcopy(outputs), strict
        self.completions = completions or [Completion.COMPLETE] * len(outputs)
        self.budget, self.calls = budget, []
        self.returned_tier, self.downgrade = returned_tier, downgrade

    def context_budget(self, tier):
        return self.budget

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        index = len(self.calls)
        assert index < len(self.outputs), "Unexpected extra model call"
        data = deepcopy(self.outputs[index])
        self.calls.append({"input": json.loads(prompt.user), "schema": deepcopy(schema),
                           "tier": tier, "max_tokens": max_tokens,
                           "system": prompt.system})
        if isinstance(data, Exception):
            raise data
        result = ModelResult(None, data, self.returned_tier or tier,
                             "offline", "fabricated-independent-reader", Usage(11, 7, 0), 2,
                             completion=self.completions[index],
                             downgraded_from=self.downgrade)
        if self.strict:
            try:
                require_schema(data, schema)
            except SchemaViolation as exc:
                # The port constructor owns the completed-object quarantine
                # contract; no fixture-side output repair or acceptance occurs.
                raise SchemaViolation(str(exc), rejected_result=result) from exc
        return result


def read(model, *, sink=None, schema=None, owner=accept, **kwargs):
    return checked_unit_read(model, PROMPT, schema or SCHEMA, 1000, owner,
                             unit_fields=FIELDS, diagnostics=sink, **kwargs)


def repairs(**units):
    return {"repairs": {identity: {"proposals": values} for identity, values in units.items()}}


def test_one_valid_read_preserves_meaning_and_adds_no_call():
    text = "A substantive assertion with a limiting condition. " * 80
    model, sink = Model([envelope([row(text)], [row(source="S2", targets=["R2"])])]), {}
    values = read(model, sink=sink)
    assert len(values) == 2 and values[0].text == text
    assert len(model.calls) == 1 and sink["state"] == "returned"
    assert model.calls[0]["input"] == json.loads(PROMPT.user)


def test_valid_empty_is_a_read_not_semantic_coverage_proof():
    model, sink = Model([envelope()]), {}
    assert read(model, sink=sink) == ()
    assert len(model.calls) == 1 and sink["state"] == "returned"
    assert sink["unread_units"] == [] and "coverage" not in sink


@pytest.mark.parametrize("strict", [False, True])
def test_one_fault_gets_keyed_repair_without_repeating_or_losing_sound_peer(strict):
    good, bad, fixed = row(), row(""), row("A separately supported observation.", "S2")
    model, sink = Model([envelope([good, bad]),
                         repairs(**{"observations:2": [fixed]})], strict=strict), {}
    values = read(model, sink=sink)
    assert [value.text for value in values] == [good["text"], fixed["text"]]
    assert len(model.calls) == 2 and sink["state"] == "returned"
    second = model.calls[1]
    assert second["schema"]["properties"]["repairs"]["required"] == ["observations:2"]
    assert second["input"]["original_input"] == json.loads(PROMPT.user)
    assert second["input"]["retained_proposal_context"][0]["unit_id"] == "observations:1"
    assert sink["retained_unit_ids"] == ["observations:1"]
    assert sink["repaired_unit_ids"] == ["observations:2"]


def test_each_repair_uses_its_original_declared_row_schema():
    model, sink = Model([
        envelope([row(" ")], [row(source="S1", targets=["R2"])]),
        repairs(**{"observations:1": [row("A valid contribution.")],
                   "revisions:1": [row("An owned revision.", targets=["R1"])]}),
    ]), {}
    assert len(read(model, sink=sink)) == 2
    choices = model.calls[1]["schema"]["properties"]["repairs"]["properties"]
    assert (choices["observations:1"]["anyOf"][0]["properties"]["proposals"]["items"]
            == SCHEMA["properties"]["observations"]["items"])
    assert (choices["revisions:1"]["anyOf"][0]["properties"]["proposals"]["items"]
            == SCHEMA["properties"]["revisions"]["items"])


def test_explicit_empty_repair_omits_invalid_proposal_without_claiming_coverage():
    model, sink = Model([envelope([row(), row(" ")]),
                         repairs(**{"observations:2": []})]), {}
    assert len(read(model, sink=sink)) == 1
    assert sink["omitted_unit_ids"] == ["observations:2"]
    assert sink["unread_units"] == [] and sink["state"] == "returned"


@pytest.mark.parametrize("correction", [
    {"repairs": {}},
    repairs(**{"observations:2": [row(" ")]}),
    repairs(**{"observations:2": [row(source="FOREIGN")]}),
    repairs(**{"observations:2": [row(), row()]}),
    {"repairs": {"observations:2": {"proposals": None}}},
    {"repairs": {"observations:2": {"proposals": [], "contradictory": "keep"}}},
])
def test_exhausted_malformed_sibling_preserves_sound_peer_and_explicit_unread(correction):
    model, sink = Model([envelope([row(), row(" ")]), correction]), {}
    values = read(model, sink=sink)
    assert len(values) == 1 and len(model.calls) == 2
    assert sink["state"] == "partial"
    assert [unit["unit_id"] for unit in sink["unread_units"]] == ["observations:2"]


def test_missing_diagnostics_owner_cannot_silently_return_partial_batch():
    model = Model([envelope([row(), row(" ")]), {"repairs": {}}])
    with pytest.raises(SchemaViolation, match="required unit ID"):
        read(model)
    assert len(model.calls) == 2


def test_unknown_repair_identity_is_not_new_content_or_admission_authority():
    model, sink = Model([envelope([row(), row(" ")]),
                         repairs(**{"observations:2": [], "FORGED": [row("Invented.")]})]), {}
    assert len(read(model, sink=sink)) == 1
    assert sink["state"] == "partial" and "unowned" in sink["envelope_issue"]


@pytest.mark.parametrize("first", [
    {"observations": [row()]},
    {"observations": [row()], "revisions": "unread container"},
    {**envelope([row()]), "undeclared": "unsupported envelope instruction"},
])
def test_malformed_shell_uses_whole_envelope_repair_and_preserves_sound_peer(first):
    model, sink = Model([first, envelope()]), {}
    assert len(read(model, sink=sink)) == 1
    assert model.calls[1]["schema"] == SCHEMA
    assert sink["state"] == "returned" and len(model.calls) == 2
    assert model.calls[1]["input"]["validation_issue"]


def test_shell_replacement_without_correspondence_keeps_original_failed_unit_unread():
    model, sink = Model([{"observations": [row(), row(" ")]},
                         envelope([row("A legitimate repaired contribution.", "S2")])]), {}
    assert len(read(model, sink=sink)) == 2
    assert sink["state"] == "partial"
    assert sink["unread_units"][0]["unit_id"] == "observations:2"


def test_repeated_bad_shell_cannot_become_successful_empty_result():
    model, sink = Model([{}, {}]), {}
    with pytest.raises(SchemaViolation, match="missing"):
        read(model, sink=sink)
    assert sink["state"] == "partial" and sink["envelope_state"] == "unread"
    assert len(model.calls) == 2


def test_legacy_replacement_is_opt_in_and_does_not_resolve_unmapped_failures():
    outputs = [envelope([row(), row(" ")]),
               envelope([row("A replacement contribution.", "S2")])]
    model, sink = Model(outputs), {}
    assert len(read(model, sink=sink)) == 1
    assert sink["state"] == "partial"
    model, sink = Model(outputs), {}
    assert len(read(model, sink=sink, allow_complete_replacement=True)) == 2
    assert sink["state"] == "partial"
    assert sink["unread_units"][0]["unit_id"] == "observations:2"


def test_semantic_truth_is_still_independent_review_responsibility():
    unsupported = row("The unchecked receipt proves all contested obligations.")
    model = Model([envelope([unsupported])])
    assert read(model)[0].text == unsupported["text"]
    # Owned references and schema cannot prove what the referenced words mean.
    assert len(model.calls) == 1


def test_owner_cannot_mutate_quarantined_rows_or_correction_feedback():
    first = envelope([row(), row(" ")])
    untouched = deepcopy(first)

    def destructive_owner(data):
        values = accept(data)
        data["observations"][0]["text"] = "Owner-local mutation"
        return values

    model = Model([first, repairs(**{"observations:2": []})])
    assert read(model, owner=destructive_owner)[0].text == row()["text"]
    assert first == untouched
    assert model.calls[1]["input"]["retained_proposal_context"][0]["proposal"] == row()


@pytest.mark.parametrize("completion", [Completion.LENGTH_LIMITED, Completion.FILTERED,
                                        Completion.CANCELLED, Completion.NOT_ESTABLISHED])
def test_incomplete_normal_result_is_never_parsed_as_retained_proposals(completion):
    poisoned = envelope([row("UNFINISHED-WIRE-CONTENT")])
    model, sink = Model([poisoned, envelope()], completions=[completion, Completion.COMPLETE]), {}
    assert read(model, sink=sink) == ()
    assert "UNFINISHED-WIRE-CONTENT" not in json.dumps(model.calls[1]["input"])
    assert sink["retained_unit_ids"] == []


@pytest.mark.parametrize("error", [OutputTruncated("unfinished"), ContentRefused("refused")])
def test_provider_incomplete_error_never_creates_quarantine_or_new_attempt(error):
    model = Model([error])
    with pytest.raises(type(error)):
        read(model)
    assert len(model.calls) == 1


def test_unavailable_independent_tier_cannot_be_repaired_into_local_acceptance():
    model = Model([envelope([row()])], returned_tier=Tier.ROUTINE, downgrade=Tier.JUDGE)
    with pytest.raises(TierUnavailable):
        read(model, tier=Tier.JUDGE)
    assert len(model.calls) == 1


def test_context_overflow_preserves_complete_original_input_and_sound_peer_without_dispatch():
    budget = estimate_tokens(PROMPT.user + PROMPT.system) + 1020
    model, sink = Model([envelope([row(), row(" ")])], budget=budget), {}
    assert len(read(model, sink=sink)) == 1
    assert len(model.calls) == 1 and sink["state"] == "partial"
    assert sink["attempts"] == 1 and sink["conditional_failure"]["kind"] == "ContextOverflow"
    assert not sink["conditional_failure"]["dispatch_attempted"]
    assert sink["unread_units"][0]["unit_id"] == "observations:2"
    assert model.calls[0]["input"] == json.loads(PROMPT.user)


def test_batch_minimum_is_not_silently_normalized_away():
    schema = deepcopy(SCHEMA)
    schema["properties"]["observations"]["minItems"] = 1
    model, sink = Model([envelope(), envelope([row()])]), {}
    assert len(read(model, sink=sink, schema=schema)) == 1
    assert len(model.calls) == 2 and sink["state"] == "returned"


def test_forbidden_operation_can_be_explicitly_omitted_without_false_shell_failure():
    schema = deepcopy(SCHEMA)
    schema["properties"]["revisions"]["maxItems"] = 0
    model, sink = Model([envelope([row()], [row(targets=["R1"])]),
                         repairs(**{"revisions:1": []})]), {}
    assert len(read(model, sink=sink, schema=schema)) == 1
    assert sink["state"] == "returned" and sink["omitted_unit_ids"] == ["revisions:1"]


def test_aggregate_array_bound_cannot_be_bypassed_by_retention():
    schema = deepcopy(SCHEMA)
    schema["properties"]["observations"]["maxItems"] = 1
    model, sink = Model([envelope([row(), row("Another original unit.", "S2")]), envelope()]), {}
    assert len(read(model, sink=sink, schema=schema)) == 2
    assert sink["state"] == "partial" and "too many" in sink["envelope_issue"]


def test_exact_duplicate_proposals_are_losslessly_deduplicated():
    model, sink = Model([envelope([row(), row()])]), {}
    assert len(read(model, sink=sink)) == 1
    assert sink["state"] == "returned" and len(model.calls) == 1


def test_atomic_nonunit_flow_is_not_accepted_as_independent_unit_configuration():
    model = Model([{}])
    with pytest.raises(ValueError, match="declared array schemas"):
        checked_unit_read(model, PROMPT, {"type": "object", "properties": {}},
                          1000, accept, unit_fields=FIELDS)
    assert model.calls == []


class RecoveryLedger:
    def __init__(self, remaining):
        self.remaining, self.phases = remaining, []

    def claim(self, phase):
        self.phases.append(phase)
        if not self.remaining:
            return False
        self.remaining -= 1
        return True


class BudgetModel(Model):
    def __init__(self, outputs, ledger):
        super().__init__(outputs)
        self.ledger = ledger

    def claim_recovery(self, phase):
        return self.ledger.claim(phase)


def test_shared_budget_denial_preserves_sound_peer_and_unread_units_without_dispatch():
    ledger = RecoveryLedger(0)
    model, sink = BudgetModel([envelope([row(), row(" ")])], ledger), {}
    assert len(read(model, sink=sink)) == 1
    assert len(model.calls) == 1 and sink["attempts"] == 1
    assert sink["state"] == "partial" and sink["recovery_exhausted"]
    assert sink["unread_units"][0]["unit_id"] == "observations:2"
    assert ledger.phases == ["candidate_unit_read:correction"]


def test_shared_budget_denial_never_turns_all_unread_into_successful_empty():
    ledger = RecoveryLedger(0)
    model, sink = BudgetModel([envelope([row(" ")])], ledger), {}
    with pytest.raises(SchemaViolation, match="budget is exhausted"):
        read(model, sink=sink)
    assert len(model.calls) == 1 and sink["state"] == "partial"
    assert sink["proposal_count"] == 0 and sink["recovery_exhausted"]


def test_shared_budget_denial_preserves_peer_from_unrepaired_declared_container():
    model, sink = BudgetModel([{"observations": [row()]}], RecoveryLedger(0)), {}
    assert len(read(model, sink=sink)) == 1
    assert sink["envelope_state"] == "unread" and sink["recovery_exhausted"]
    assert len(model.calls) == 1


def test_shared_budget_accumulates_across_reader_invocations():
    ledger = RecoveryLedger(1)
    first = BudgetModel([envelope([row(" ")]),
                         repairs(**{"observations:1": [row()]})], ledger)
    assert len(read(first, sink={})) == 1
    second, sink = BudgetModel([envelope([row(), row(" ")])], ledger), {}
    assert len(read(second, sink=sink)) == 1
    assert len(first.calls) + len(second.calls) == 3
    assert len(ledger.phases) == 2 and sink["recovery_exhausted"]


def test_complete_batch_needs_no_recovery_reservation():
    ledger = RecoveryLedger(0)
    model = BudgetModel([envelope([row()])], ledger)
    assert len(read(model)) == 1 and ledger.phases == []


def test_atomic_checked_read_obeys_same_shared_budget_and_keeps_local_bound():
    denied = BudgetModel([envelope([row(" ")])], RecoveryLedger(0))
    with pytest.raises(SchemaViolation, match="shared recovery budget is exhausted"):
        _full_helpers.checked_read(denied, PROMPT, SCHEMA, 1000, accept)
    assert len(denied.calls) == 1
    allowed = BudgetModel([envelope([row(" ")]), envelope([row()])], RecoveryLedger(1))
    assert len(_full_helpers.checked_read(allowed, PROMPT, SCHEMA, 1000, accept)) == 1
    assert len(allowed.calls) == 2


def test_shared_budget_hook_must_return_an_explicit_boolean():
    model = Model([envelope([row(), row(" ")])])
    model.claim_recovery = lambda phase: "unbounded"
    with pytest.raises(TypeError, match="boolean decision"):
        read(model, sink={})
    assert len(model.calls) == 1


_CONDITIONAL_FAILURES = (
    ContextOverflow, ProviderUnavailable, OutputTruncated, ContentRefused, RateLimited)


@pytest.mark.parametrize("error_type", _CONDITIONAL_FAILURES)
def test_conditional_provider_failure_retains_sound_peer_and_explicit_unread(error_type):
    error = error_type("The conditional attempt did not complete")
    model, sink = Model([envelope([row(), row(" ")]), error]), {}
    assert len(read(model, sink=sink)) == 1
    assert len(model.calls) == 2 and sink["state"] == "partial"
    assert sink["attempts"] == 2
    assert sink["unread_units"][0]["unit_id"] == "observations:2"
    assert sink["conditional_failure"] == {
        "kind": error_type.__name__, "phase": "candidate_unit_read:correction",
        "dispatch_attempted": True}
    assert sink["repaired_unit_ids"] == [] and sink["omitted_unit_ids"] == []


@pytest.mark.parametrize("error_type", _CONDITIONAL_FAILURES)
def test_initial_provider_failure_still_raises_before_recovery_admission(error_type):
    ledger = RecoveryLedger(1)
    model, sink = BudgetModel([error_type("The original read did not complete")], ledger), {}
    with pytest.raises(error_type):
        read(model, sink=sink)
    assert len(model.calls) == 1 and ledger.phases == [] and sink == {}


@pytest.mark.parametrize("error_type", _CONDITIONAL_FAILURES)
def test_conditional_failure_with_no_sound_proposals_never_returns_successful_empty(error_type):
    model, sink = Model([envelope([row(" ")]), error_type("No correction result")]), {}
    with pytest.raises(SchemaViolation, match="conditional correction did not finish"):
        read(model, sink=sink)
    assert sink["state"] == "partial" and sink["proposal_count"] == 0
    assert len(model.calls) == 2


@pytest.mark.parametrize("error_type", [TierUnavailable, ValueError, TypeError])
def test_conditional_independence_or_integrity_failure_is_not_masked_by_peer_retention(error_type):
    model = Model([envelope([row(), row(" ")]), error_type("The boundary is untrusted")])
    with pytest.raises(error_type):
        read(model, sink={})
    assert len(model.calls) == 2


def test_conditional_incomplete_bytes_never_enter_retained_proposals():
    error = OutputTruncated("The conditional response stopped early")
    error.rejected_result = ModelResult(
        None, envelope([row("UNFINISHED-WIRE-CONTENT", source="S2")]), Tier.ROUTINE,
        "offline", "unfinished-reader", Usage(2, 3, 0), 0,
        completion=Completion.LENGTH_LIMITED)
    model, sink = Model([envelope([row(), row(" ")]), error]), {}
    values = read(model, sink=sink)
    assert len(values) == 1 and values[0].text == row()["text"]
    assert "UNFINISHED-WIRE-CONTENT" not in json.dumps(sink)
    assert sink["state"] == "partial"


def test_conditional_failure_without_diagnostics_owner_is_not_silent_partial_success():
    model = Model([envelope([row(), row(" ")]), ProviderUnavailable("Correction unavailable")])
    with pytest.raises(SchemaViolation):
        read(model)
    assert len(model.calls) == 2


class PermitModel(BudgetModel):
    def __init__(self, outputs, ledger, *, budget):
        super().__init__(outputs, ledger)
        self.budget, self.pending = budget, None
        self.abandoned, self.dispatch_phases = [], []

    def claim_recovery(self, phase):
        reserved = super().claim_recovery(phase)
        if reserved:
            self.pending = phase
        return reserved

    def abandon_recovery(self, phase):
        assert self.pending == phase
        self.abandoned.append(phase)
        self.pending = None

    def structured(self, *args, **kwargs):
        self.dispatch_phases.append(self.pending)
        self.pending = None
        return super().structured(*args, **kwargs)


def test_predispatch_context_failure_abandons_phase_without_refunding_reservation():
    budget = estimate_tokens(PROMPT.user + PROMPT.system) + 1020
    ledger = RecoveryLedger(1)
    model, sink = PermitModel([envelope([row(), row(" ")]), envelope()], ledger,
                              budget=budget), {}
    assert len(read(model, sink=sink)) == 1
    assert ledger.remaining == 0 and ledger.phases == ["candidate_unit_read:correction"]
    assert model.abandoned == ["candidate_unit_read:correction"] and model.pending is None
    model.structured(PROMPT, SCHEMA, Tier.ROUTINE, max_tokens=1000)
    assert model.dispatch_phases == [None, None]
    assert not sink["conditional_failure"]["dispatch_attempted"]


def test_budget_denial_precedes_feedback_context_work_and_preserves_peer():
    ledger = RecoveryLedger(0)
    model, sink = PermitModel([envelope([row(), row(" ")])], ledger, budget=1), {}
    assert len(read(model, sink=sink)) == 1
    assert sink["recovery_exhausted"] and sink["conditional_failure"] is None
    assert model.abandoned == [] and len(model.calls) == 1


def test_atomic_reader_predispatch_failure_keeps_reserved_not_dispatched_accounting():
    budget = estimate_tokens(PROMPT.user + PROMPT.system) + 1020
    ledger = RecoveryLedger(1)
    model = PermitModel([envelope([row(" ")])], ledger, budget=budget)
    with pytest.raises(ContextOverflow):
        _full_helpers.checked_read(model, PROMPT, SCHEMA, 1000, accept)
    assert ledger.remaining == 0 and model.abandoned == ["candidate_unit_read:correction"]
    assert len(model.calls) == 1 and model.pending is None


def selected_repair(identity, field, *proposals):
    return {"repairs": {identity: {"field": field, "proposals": list(proposals)}}}


@pytest.mark.parametrize("strict", [False, True])
def test_owned_revision_can_be_corrected_to_unlinked_observation(strict):
    original = row("A held account.", targets=["R2"])
    fixed = row("A held account.")
    model, sink = Model([envelope([row("A sound peer.", "S2")], [original]),
                         selected_repair("revisions:1", "observations", fixed)],
                        strict=strict), {}
    values = read(model, sink=sink)
    assert len(values) == 2 and values[1].targets == ()
    assert sink["repaired_unit_ids"] == ["revisions:1"] and sink["state"] == "returned"
    assert model.calls[1]["input"]["failed_units"][0]["proposal"] == original
    assert model.calls[1]["input"]["original_input"] == json.loads(PROMPT.user)


@pytest.mark.parametrize("strict", [False, True])
def test_observation_can_be_corrected_to_revision_only_with_owned_target(strict):
    original = row("A linked account.", targets=["R1"])
    fixed = row("A linked account.", targets=["R1"])
    model, sink = Model([envelope([row("A sound peer.", "S2"), original]),
                         selected_repair("observations:2", "revisions", fixed)],
                        strict=strict), {}
    values = read(model, sink=sink)
    assert len(values) == 2 and values[1].targets == ("R1",)
    assert sink["repaired_unit_ids"] == ["observations:2"] and sink["state"] == "returned"
    assert model.calls[1]["input"]["failed_units"][0]["field"] == "observations"
    assert model.calls[1]["input"]["retained_proposal_context"][0]["unit_id"] == "observations:1"


def test_explicit_same_field_choice_is_harmless_and_accepted():
    model, sink = Model([envelope([row(), row(" ")]),
                         selected_repair("observations:2", "observations",
                                         row("A corrected original operation.", "S2"))]), {}
    assert len(read(model, sink=sink)) == 2
    assert sink["state"] == "returned" and len(model.calls) == 2


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("selected", ["outside", "", None, True, 1, ["observations"]])
def test_foreign_or_ambiguous_operation_selector_never_reclassifies_row(strict, selected):
    model, sink = Model([envelope([row(), row(" ")]),
                         selected_repair("observations:2", selected,
                                         row("A valid-looking repaired account.", "S2"))],
                        strict=strict), {}
    assert len(read(model, sink=sink)) == 1
    assert sink["state"] == "partial" and sink["repaired_unit_ids"] == []
    assert sink["unread_units"][0]["unit_id"] == "observations:2"
    assert len(model.calls) == 2


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("selected,fixed", [
    ("revisions", row("Missing revision target.")),
    ("observations", row("Unexpected observation target.", targets=["R1"])),
    ("revisions", row("Wrong original source.", "S2", targets=["R1"])),
])
def test_operation_selection_binds_exact_row_schema_and_owned_target(strict, selected, fixed):
    model, sink = Model([envelope([row(), row(" ")]),
                         selected_repair("observations:2", selected, fixed)],
                        strict=strict), {}
    assert len(read(model, sink=sink)) == 1
    assert sink["state"] == "partial" and sink["repaired_unit_ids"] == []
    assert sink["unread_units"][0]["unit_id"] == "observations:2"


def test_cross_operation_shape_is_not_inferred_without_explicit_selector():
    model, sink = Model([envelope([row(), row(" ")]),
                         repairs(**{"observations:2": [row("A target is not a selector.",
                                                        targets=["R1"])]})]), {}
    assert len(read(model, sink=sink)) == 1
    assert sink["state"] == "partial" and sink["unread_units"][0]["unit_id"] == "observations:2"


def test_explicit_operation_choice_still_has_one_proposal_per_owned_unit():
    model, sink = Model([envelope([row(), row(" ")]),
                         selected_repair("observations:2", "observations",
                                         row("One correction.", "S2"),
                                         row("An ambiguous second correction.", "S2"))]), {}
    assert len(read(model, sink=sink)) == 1
    assert sink["state"] == "partial" and sink["repaired_unit_ids"] == []


def test_declared_disabled_operation_cannot_be_enabled_by_field_choice():
    schema = deepcopy(SCHEMA)
    schema["properties"]["revisions"]["maxItems"] = 0
    model, sink = Model([envelope([row(), row(" ")]),
                         selected_repair("observations:2", "revisions",
                                         row("No authority to enable this operation.",
                                             targets=["R1"]))]), {}
    assert len(read(model, sink=sink, schema=schema)) == 1
    assert sink["state"] == "partial" and sink["unread_units"][0]["unit_id"] == "observations:2"


def test_empty_operation_choice_is_an_explicit_omission_not_coverage_proof():
    schema = deepcopy(SCHEMA)
    schema["properties"]["revisions"]["maxItems"] = 0
    model, sink = Model([envelope([row(), row(" ")]),
                         selected_repair("observations:2", "revisions")]), {}
    assert len(read(model, sink=sink, schema=schema)) == 1
    assert sink["omitted_unit_ids"] == ["observations:2"]
    assert sink["state"] == "returned" and "coverage" not in sink


def test_operation_choice_cannot_modify_retained_unit_with_unowned_repair_id():
    response = selected_repair("observations:2", "observations", row("A valid correction.", "S2"))
    response["repairs"]["observations:1"] = {
        "field": "revisions", "proposals": [row("A forged replacement.", targets=["R1"])]}
    model, sink = Model([envelope([row(), row(" ")]), response]), {}
    values = read(model, sink=sink)
    assert len(values) == 2 and values[0].text == row()["text"]
    assert all(value.text != "A forged replacement." for value in values)
    assert sink["state"] == "partial" and "unowned" in sink["envelope_issue"]


def test_choices_are_declared_schema_shapes_for_all_original_operations():
    model = Model([envelope([row(" ")], [row(source="S1", targets=["R2"])]),
                   {"repairs": {"observations:1": {"proposals": []},
                                "revisions:1": {"proposals": []}}}])
    assert read(model, sink={}) == ()
    choices = model.calls[1]["schema"]["properties"]["repairs"]["properties"]
    for identity, original in (("observations:1", "observations"), ("revisions:1", "revisions")):
        branches = choices[identity]["anyOf"]
        assert (branches[0]["properties"]["proposals"]["items"]
                == SCHEMA["properties"][original]["items"])
        assert "field" not in branches[0]["properties"]
        for field, branch in zip(FIELDS, branches[1:], strict=True):
            assert branch["properties"]["field"] == {"type": "string", "enum": [field]}
            assert (branch["properties"]["proposals"]["items"]
                    == SCHEMA["properties"][field]["items"])
            assert branch["additionalProperties"] is False
            assert branch["properties"]["proposals"]["maxItems"] == 1


def independent_quarantine(**kwargs):
    options = {"completion": Completion.COMPLETE, "tier": Tier.JUDGE,
               "data": {"verdicts": [{"candidate_id": "C1", "decision": "accept"}]},
               "text": None, "downgraded_from": None}
    options.update(kwargs)
    return ModelResult(options["text"], options["data"], options["tier"],
                       "offline", "fabricated-independent-verifier", Usage(11, 7, 0), 2,
                       retries=1, completion=options["completion"],
                       downgraded_from=options["downgraded_from"])


def test_shared_verifier_quarantine_preserves_completed_independent_error_receipt():
    result = independent_quarantine()
    error = SchemaViolation("Invalid review metadata", rejected_result=result)
    exposed = _full_helpers.quarantined_independent_result(error)
    assert exposed == result and exposed is error.rejected_result
    assert ((error.usage, error.latency_ms, error.retries)
            == (result.usage, result.latency_ms, result.retries))
    assert isinstance(error, SchemaViolation)


@pytest.mark.parametrize("attribute,value", [("usage", Usage(99, 7, 0)),
                                             ("latency_ms", 99), ("retries", 99)])
def test_shared_verifier_quarantine_rejects_mismatched_accounting(attribute, value):
    error = SchemaViolation("Invalid review metadata", rejected_result=independent_quarantine())
    setattr(error, attribute, value)
    assert _full_helpers.quarantined_independent_result(error) is None


@pytest.mark.parametrize("result", [
    None, {"data": {"verdicts": []}},
    independent_quarantine(completion=Completion.LENGTH_LIMITED),
    independent_quarantine(completion=Completion.FILTERED),
    independent_quarantine(completion=Completion.CANCELLED),
    independent_quarantine(completion=Completion.NOT_ESTABLISHED),
    independent_quarantine(data=[]), independent_quarantine(text="Ambiguous free text"),
])
def test_shared_verifier_quarantine_does_not_parse_unsafe_attachment(result):
    # A deliberately malformed nonportable adapter attachment exercises the
    # owning helper in addition to the strict constructor's own safeguards.
    error = SchemaViolation("Unsafe attachment", usage=Usage(11, 7, 0), latency_ms=2, retries=1)
    error.rejected_result = result
    assert _full_helpers.quarantined_independent_result(error) is None


@pytest.mark.parametrize("result", [
    independent_quarantine(tier=Tier.ROUTINE),
    independent_quarantine(tier=Tier.HARD),
    independent_quarantine(downgraded_from=Tier.JUDGE),
])
def test_shared_verifier_quarantine_requires_actual_independent_result(result):
    error = SchemaViolation("Invalid review metadata", rejected_result=result)
    with pytest.raises(TierUnavailable):
        _full_helpers.quarantined_independent_result(error)


@pytest.mark.parametrize("coverage", [False, True])
def test_shared_verdict_envelope_keeps_addressable_peers_and_owner_checks_separate(coverage):
    rows = [{"candidate_id": "C1", "decision": "accept"},
            {"candidate_id": "C1", "decision": "conflicting owner decision"}]
    data = {"verdicts": rows}
    if coverage:
        data["coverage"] = {"status": "Owner validates this separately"}
    assert _full_helpers.verdict_envelope_issue(data, ("C1",), coverage=coverage) == ""
    assert data["verdicts"] == rows


@pytest.mark.parametrize("data,coverage,issue", [
    (None, False, "unknown or ambiguous"),
    ({"verdicts": [], "extra": "uninterpreted"}, True, "unknown or ambiguous"),
    ({"verdicts": [], "coverage": {}}, False, "unknown or ambiguous"),
    ({}, False, "must be an array"),
    ({"verdicts": None}, True, "must be an array"),
    ({"verdicts": [None]}, False, "unaddressable or unowned"),
    ({"verdicts": [{}]}, True, "unaddressable or unowned"),
    ({"verdicts": [{"candidate_id": "outside"}]}, False, "unaddressable or unowned"),
])
def test_shared_verdict_envelope_keeps_unknown_shell_and_foreign_ids_unread(data, coverage, issue):
    assert issue in _full_helpers.verdict_envelope_issue(data, ("C1",), coverage=coverage)
