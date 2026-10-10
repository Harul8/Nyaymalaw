"""Raw source judgments recover scoped omissions through saved public turns.

Semantic outcomes are explicitly authored fixture decisions. These cases prove
owned diagnostics, bounded calls, saved effects and replay, not Judge accuracy.
"""

import json
from copy import deepcopy

import pytest

from nm.brain import record_review as record
from nm.brain import turn as boundary
from nm.brain.conversation import Conversation, OpeningCandidate
from nm.brain.material_verification import GroundingResult
from nm.brain.turn import chat_matter_id
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage, require_schema
from tests.brain_pressure_support import record_case
from tests.brain_reader_fixture import fresh_review_reply
from tests.test_brain_evidence_rendering_public import RawExpressionModel, raw_unit
from tests.test_brain_source_support_verifiers import (
    SCOPE,
    coverage,
    disposition,
    source_catalogue,
    verdict,
)
from tests.test_brain_turn import plan

ACCOUNT = "The keeper did not identify who collected the parcel."
INSTRUCTION = "Re-examine the unadopted draft while preserving its original framing."
PEER = "The east parcel remained undelivered."


class RawSourceRecoveryModel(RawExpressionModel):
    """Author source/grounding judgments; transport only redundant selections."""

    def __init__(self, latest, *, actual_ids, initial_roles, reconsidered_roles,
                 initial_details=(), unchanged=False):
        route = plan(latest, scope="proposed", material_purposes=(
            "account_contribution" if actual_ids else "interpretation_review",))
        super().__init__([plan("Hello."), route], [
            lambda payload: {"units": [raw_unit(payload)]},
            lambda payload: {"units": [raw_unit(payload)]},
        ])
        self.latest = latest
        self.actual_ids = set(actual_ids)
        self.initial_roles = dict(initial_roles)
        self.reconsidered_roles = dict(reconsidered_roles)
        self.initial_details = tuple(initial_details)
        self.unchanged = unchanged
        self.seen = []
        self.fabricated_outputs = []
        self.recovery_reads = 0

    def _source_reply(self, operation, payload):
        assert set(payload) == {
            "earlier_conversation", "latest_message_spans", "source_ids",
            "source_selection_contract", "original_source_catalogue"}
        assert payload["source_selection_contract"] == record.SOURCE_SELECTION_CONTRACT
        references = payload["original_source_catalogue"]
        assert all(set(row) == {"turn_id", "role", "quoted"} for row in references.values())
        roles = self.reconsidered_roles if operation == "reconsider_account_sources" else (
            self.initial_roles)
        rows = {}
        for identity in payload["source_ids"]:
            role = roles.get(identity, "work_instruction")
            positive = role in {"reported_matter_account", "reported_party_position", "mixed"}
            rows[identity] = {
                "content_role": role,
                "reason": "The independently scripted source owner reads original framing.",
                "substantive_spans": [{"start": 0, "end": len(references[identity]["quoted"])}]
                if positive else [],
            }
        return {"source_treatments": rows}

    def _detail_reply(self, payload):
        recovery = "recovery_scope" in payload
        if recovery:
            self.recovery_reads += 1
            assert payload["recovery_scope"]["missing_source_ids"]
        selected = tuple(self.actual_ids) if recovery else self.initial_details
        references = {row["id"]: row["text"].strip() for row in payload["latest_message_spans"]}
        return {"new_items": [{
            "kind": "event", "statement": references[identity], "source_id": identity,
            "prior_source_ids": [], "basis": "stated", "importance": "relevant",
            "why_material": "This exact attributed contribution bears on the requested account.",
            "assignment_ids": ["matter:discussion"],
        } for identity in sorted(selected)], "changes": []}

    def _review_reply(self, operation, payload):
        assert payload["source_support_contract"] == record.SOURCE_SUPPORT_CONTRACT
        assert payload["coverage_selection_contract"] == record.COVERAGE_SELECTION_CONTRACT
        references = payload["source_treatments"]
        assert all(set(row) == {"turn_id", "role", "quoted"} for row in references.values())
        assert "".join(row["text"] for row in payload["latest_message_spans"]) == self.latest
        kind = "material" if operation == "verify_material_grounding" else "dispute"
        assert kind == "material" or payload["candidates"] == []
        decisions = []
        represented = {}
        candidates = [*payload["candidates"], *payload.get("retained_candidate_context", [])]
        for candidate in candidates:
            source_id = candidate["allowed_account_source_ids"][0]
            assert source_id in self.actual_ids
            accepted = not self.unchanged
            if candidate in payload["candidates"]:
                decisions.append(verdict(
                    kind, references[source_id], index=int(candidate["candidate_id"][1:]),
                    source_id=source_id, accept=accepted))
            if accepted:
                represented[source_id] = candidate["candidate_id"]
        purposes = {identity: "account" if identity in self.actual_ids else "non_account"
                    for identity in references}
        dispositions = []
        missing = False
        for identity in sorted(self.actual_ids):
            if kind == "dispute":
                dispositions.append(disposition(
                    identity, references[identity], status="outside_scope"))
            elif identity in represented:
                dispositions.append(disposition(
                    identity, references[identity], status="represented",
                    candidate_ids=(represented[identity],)))
            else:
                missing = True
                dispositions.append(disposition(identity, references[identity]))
        return {"verdicts": decisions, "coverage": coverage(
            references, state="partial" if missing else "complete", purposes=purposes,
            dispositions=dispositions)}

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        critical = {"classify_account_sources", "reconsider_account_sources", "extract_disputes",
                    "extract_legal_details", "verify_disputes", "verify_material_grounding"}
        if prompt.operation not in critical:
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        else:
            payload = json.loads(prompt.user)
            self.calls.append((prompt.operation, deepcopy(payload)))
            self.schemas.append((prompt.operation, deepcopy(schema)))
            self.tiers.append(tier)
            if prompt.operation in {"classify_account_sources", "reconsider_account_sources"}:
                assert tier == (Tier.JUDGE if prompt.operation == "reconsider_account_sources"
                                else Tier.ROUTINE)
                data = self._source_reply(prompt.operation, payload)
            elif prompt.operation == "extract_disputes":
                data = {"new_items": [], "changes": []}
            elif prompt.operation == "extract_legal_details":
                data = self._detail_reply(payload)
            else:
                data = fresh_review_reply(payload, self._review_reply(prompt.operation, payload))
            require_schema(data, schema)
            result = ModelResult(
                text=None, data=data, tier=tier, provider="offline-raw",
                model="fabricated-source-recovery", usage=Usage(0, 0, 0), latency_ms=0,
                completion=Completion.COMPLETE)
        self.seen.append({"operation": prompt.operation, "input": json.loads(prompt.user),
                          "tier": tier.value})
        self.fabricated_outputs.append({"operation": prompt.operation,
                                        "output": deepcopy(result.data)})
        return result


def wire(wired, monkeypatch, model, *, recovery_limit=8):
    from nm.app import api

    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    monkeypatch.setattr(wired, "legal_search", None)
    if recovery_limit != 8:
        class LimitedService(boundary.BrainService):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs, recovery_limit=recovery_limit)
        monkeypatch.setattr(api, "BrainService", LimitedService)


def release_and_replay(client, wired, monkeypatch, model, identity, *, recovery_limit=8):
    from tests.test_brain_continuation_service import send

    wire(wired, monkeypatch, model, recovery_limit=recovery_limit)
    opened = send(client, "Hello.", identity + "-greeting")
    first = send(client, model.latest, identity, opened=opened)
    matter_id = first["matter_id"] or chat_matter_id("adv_demo", first["chat_id"])
    saved = wired.store.load(matter_id)
    conversation, _, _ = boundary._current_records(wired.store, saved)
    response = saved.brain_chat[-1]["response"]
    assert response["elements"] == first["elements"]
    owned = response["material_coverage"]["source_treatments"]
    for row in owned.values():
        assert row["selection_contract"] == record.SOURCE_SELECTION_CONTRACT
        assert record.source_treatment_reference_valid(row, {
            (row["turn_id"], row["role"], row["quoted"])})
    calls_before_replay = len(model.calls)
    replay = send(client, model.latest, identity, opened=opened)
    assert replay["replayed"] is True and replay["metrics"]["llm_calls"] == 0
    assert replay["elements"] == first["elements"] and len(model.calls) == calls_before_replay
    assert wired.store.load(matter_id) == saved
    return first, saved, conversation


def observation(answer, saved, conversation):
    execution = answer["material_coverage"]["execution"]
    owned = saved.brain_chat[-1]["response"]["material_coverage"]["source_treatments"]
    return {
        "saved_material": [row["statement"] for row in conversation.open_material],
        "latest_source_roles": {identity: row["content_role"] for identity, row in owned.items()
                                if identity.startswith("L")},
        "conditional_calls": answer["metrics"]["recovery"]["dispatched_calls"],
        "source_recovery_state": execution["semantic_recovery"]["source_reconsideration"]["state"],
        "detail_coverage": execution["stages"]["detail_review"]["account_coverage"]["state"],
        "record_change_count": len(execution["record_changes"]),
    }


def evidence(identity, model, answer, saved, conversation, expected, *, status="recovered"):
    observed = observation(answer, saved, conversation)
    record_case(identity, boundary="POST /api/turn -> source recovery -> saved reply -> replay",
                user_passage={"earlier": "Hello.", "latest": model.latest},
                model_outputs=model.fabricated_outputs, expected=expected, observed=observed,
                calls=model.seen, scenario="paired", claim_scope="mechanical",
                protection_status=status,
                notes=("Critical source and grounding outputs are authored fresh wire objects. "
                       "Classifier labels are absent from independent source review. Semantic "
                       "judgments are scripted; these observations establish wiring and effects."))


def test_empty_extraction_recovers_account_after_coverage_origin_source_reconsideration(
        client, wired, monkeypatch):
    model = RawSourceRecoveryModel(
        ACCOUNT, actual_ids=("L1",), initial_roles={"L1": "examination_material"},
        reconsidered_roles={"L1": "reported_matter_account"})
    answer, saved, conversation = release_and_replay(
        client, wired, monkeypatch, model, "coverage-origin-account")
    owner_calls = [row for row in model.seen if row["operation"] == "reconsider_account_sources"]
    assert len(owner_calls) == 1 and owner_calls[0]["input"]["source_ids"] == ["L1"]
    assert model.recovery_reads == 1
    assert "candidates" not in owner_calls[0]["input"]
    evidence("COVERAGE-SOURCE-ACCOUNT", model, answer, saved, conversation, {
        "saved_material": [ACCOUNT], "latest_source_roles": {"L1": "reported_matter_account"},
        "conditional_calls": 5, "source_recovery_state": "changed",
        "detail_coverage": "complete", "record_change_count": 1,
    })


def test_instruction_misclassified_as_account_is_reconsidered_without_record_effects(
        client, wired, monkeypatch):
    model = RawSourceRecoveryModel(
        INSTRUCTION, actual_ids=(), initial_roles={"L1": "reported_matter_account"},
        reconsidered_roles={"L1": "work_instruction"})
    answer, saved, conversation = release_and_replay(
        client, wired, monkeypatch, model, "coverage-origin-instruction")
    assert model.recovery_reads == 0
    evidence("COVERAGE-SOURCE-INSTRUCTION", model, answer, saved, conversation, {
        "saved_material": [], "latest_source_roles": {"L1": "work_instruction"},
        "conditional_calls": 3, "source_recovery_state": "changed",
        "detail_coverage": "complete", "record_change_count": 0,
    })


def test_correct_initial_account_keeps_useful_work_without_conditional_calls(
        client, wired, monkeypatch):
    model = RawSourceRecoveryModel(
        ACCOUNT, actual_ids=("L1",), initial_roles={"L1": "reported_matter_account"},
        reconsidered_roles={}, initial_details=("L1",))
    answer, saved, conversation = release_and_replay(
        client, wired, monkeypatch, model, "coverage-initial-account")
    assert not any(row["operation"] == "reconsider_account_sources" for row in model.seen)
    evidence("COVERAGE-INITIAL-ACCOUNT", model, answer, saved, conversation, {
        "saved_material": [ACCOUNT], "latest_source_roles": {"L1": "reported_matter_account"},
        "conditional_calls": 0, "source_recovery_state": "not_needed",
        "detail_coverage": "complete", "record_change_count": 1,
    }, status="admitted")


def test_correct_initial_instruction_accepts_genuine_empty_extraction_without_retries(
        client, wired, monkeypatch):
    model = RawSourceRecoveryModel(
        INSTRUCTION, actual_ids=(), initial_roles={"L1": "work_instruction"}, reconsidered_roles={})
    answer, saved, conversation = release_and_replay(
        client, wired, monkeypatch, model, "coverage-initial-instruction")
    assert not any(row["operation"] == "reconsider_account_sources" for row in model.seen)
    evidence("COVERAGE-INITIAL-INSTRUCTION", model, answer, saved, conversation, {
        "saved_material": [], "latest_source_roles": {"L1": "work_instruction"},
        "conditional_calls": 0, "source_recovery_state": "not_needed",
        "detail_coverage": "complete", "record_change_count": 0,
    }, status="admitted")


def test_unchanged_source_reread_is_bounded_and_does_not_claim_missing_account_was_admitted(
        client, wired, monkeypatch):
    model = RawSourceRecoveryModel(
        ACCOUNT, actual_ids=("L1",), initial_roles={"L1": "examination_material"},
        reconsidered_roles={"L1": "examination_material"}, unchanged=True)
    answer, saved, conversation = release_and_replay(
        client, wired, monkeypatch, model, "coverage-source-unchanged")
    assert sum(row["operation"] == "reconsider_account_sources" for row in model.seen) == 1
    assert "The requested conclusion remains unresolved" in "\n".join(
        row["text"] for row in answer["elements"])
    evidence("COVERAGE-SOURCE-UNCHANGED", model, answer, saved, conversation, {
        "saved_material": [], "latest_source_roles": {"L1": "examination_material"},
        "conditional_calls": 3, "source_recovery_state": "unchanged",
        "detail_coverage": "partial", "record_change_count": 0,
    }, status="partial_preserved")


def test_unchanged_account_owner_and_negative_original_review_remain_truthfully_partial(
        client, wired, monkeypatch):
    model = RawSourceRecoveryModel(
        INSTRUCTION, actual_ids=(), initial_roles={"L1": "reported_matter_account"},
        reconsidered_roles={"L1": "reported_matter_account"})
    answer, saved, conversation = release_and_replay(
        client, wired, monkeypatch, model, "coverage-negative-source-unchanged")
    assert sum(row["operation"] == "reconsider_account_sources" for row in model.seen) == 1
    assert model.recovery_reads == 0
    evidence("COVERAGE-SOURCE-NEGATIVE-UNCHANGED", model, answer, saved, conversation, {
        "saved_material": [], "latest_source_roles": {"L1": "reported_matter_account"},
        "conditional_calls": 1, "source_recovery_state": "unchanged",
        "detail_coverage": "partial", "record_change_count": 0,
    }, status="partial_preserved")
    assert "The record reading remains unfinished." in "\n".join(
        row["text"] for row in answer["elements"])


def test_reverse_unchanged_source_conflict_preserves_independently_represented_peer(
        client, wired, monkeypatch):
    model = RawSourceRecoveryModel(
        PEER + " " + INSTRUCTION, actual_ids=("L1",),
        initial_roles={"L1": "reported_matter_account", "L2": "reported_matter_account"},
        reconsidered_roles={"L2": "reported_matter_account"}, initial_details=("L1",))
    answer, saved, conversation = release_and_replay(
        client, wired, monkeypatch, model, "coverage-negative-unchanged-peer")
    assert model.recovery_reads == 0
    evidence("COVERAGE-SOURCE-NEGATIVE-UNCHANGED-PEER", model, answer, saved, conversation, {
        "saved_material": [PEER], "latest_source_roles": {
            "L1": "reported_matter_account", "L2": "reported_matter_account"},
        "conditional_calls": 1, "source_recovery_state": "unchanged",
        "detail_coverage": "partial", "record_change_count": 1,
    }, status="partial_preserved")
    assessment = answer["material_coverage"]["execution"]["stages"][
        "detail_review"]["account_coverage"]
    represented, = [row for row in assessment["dispositions"] if row["source_id"] == "L1"]
    assert represented["status"] == "represented" and represented["quoted"] == PEER
    assert (represented["start"], represented["end"]) == (0, len(PEER))
    assert assessment["missing_source_ids"] == []
    assert "The record reading remains unfinished." in "\n".join(
        row["text"] for row in answer["elements"])


def test_unchanged_negative_source_hold_allows_unrelated_missing_account_recovery(
        client, wired, monkeypatch):
    model = RawSourceRecoveryModel(
        PEER + " " + INSTRUCTION, actual_ids=("L1",),
        initial_roles={"L1": "reported_matter_account", "L2": "reported_matter_account"},
        reconsidered_roles={"L2": "reported_matter_account"})
    answer, saved, conversation = release_and_replay(
        client, wired, monkeypatch, model, "coverage-negative-hold-peer-omission")
    assert model.recovery_reads == 1
    evidence("COVERAGE-SOURCE-NEGATIVE-HOLD-PEER-RECOVERY", model, answer, saved, conversation, {
        "saved_material": [PEER], "latest_source_roles": {
            "L1": "reported_matter_account", "L2": "reported_matter_account"},
        "conditional_calls": 3, "source_recovery_state": "unchanged",
        "detail_coverage": "partial", "record_change_count": 1,
    }, status="partial_preserved")
    recovery_read = [row for row in model.seen if row["operation"] == "extract_legal_details"
                     and "recovery_scope" in row["input"]]
    assert recovery_read[0]["input"]["recovery_scope"]["missing_source_ids"] == ["L1"]
    assessment = answer["material_coverage"]["execution"]["stages"][
        "detail_review"]["account_coverage"]
    represented, = [row for row in assessment["dispositions"] if row["source_id"] == "L1"]
    assert represented["status"] == "represented" and represented["quoted"] == PEER
    assert (represented["start"], represented["end"]) == (0, len(PEER))
    assert assessment["missing_source_ids"] == []
    assert "The record reading remains unfinished." in "\n".join(
        row["text"] for row in answer["elements"])


def test_source_recovery_budget_exhaustion_preserves_independently_checked_peer(
        client, wired, monkeypatch):
    latest = PEER + " " + ACCOUNT
    model = RawSourceRecoveryModel(
        latest, actual_ids=("L1", "L2"),
        initial_roles={"L1": "reported_matter_account", "L2": "examination_material"},
        reconsidered_roles={"L2": "reported_matter_account"}, initial_details=("L1",))
    answer, saved, conversation = release_and_replay(
        client, wired, monkeypatch, model, "coverage-source-budget", recovery_limit=3)
    # Two slots remain reserved for reply recovery; the one material slot can
    # reread the source, then its dependent reviews exhaust the shared budget.
    assert model.recovery_reads == 0
    evidence("COVERAGE-SOURCE-BUDGET", model, answer, saved, conversation, {
        "saved_material": [PEER], "latest_source_roles": {
            "L1": "reported_matter_account", "L2": "reported_matter_account"},
        "conditional_calls": 1, "source_recovery_state": "partial",
        "detail_coverage": "unassessed", "record_change_count": 1,
    }, status="partial_preserved")


def recovery_owner_inputs(*, owner_account=False, reviewer_account=True):
    """Construct the actual checked owner assessment before diagnostic injection."""
    role = "reported_matter_account" if owner_account else "examination_material"
    references, treatments = source_catalogue(ACCOUNT, roles={"L1": role})
    wire_coverage = coverage(
        references, state="partial" if reviewer_account else "complete",
        purposes={"L1": "account" if reviewer_account else "non_account"},
        dispositions=[disposition("L1", references["L1"])] if reviewer_account else [])
    assessment = record.checked_coverage(
        wire_coverage, tuple(references), source_references=references)
    assessment.update(contract=record.ACCOUNT_COVERAGE_CONTRACT, review_scope=deepcopy(SCOPE))
    check = deepcopy(assessment["source_checks"][0])
    diagnostic = {
        "diagnostic_kind": "coverage_source_purpose", "source_id": "L1",
        "content_role": role, "supplies_account_content": reviewer_account,
        "coverage_source_check": check, "review_scope": deepcopy(SCOPE),
    }
    return {
        "model": object(), "context": {"slots": {}, "dispute_proposals": (),
                                         "detail_proposals": ()},
        "conversation": Conversation(()), "latest": ACCOUNT, "turn_id": "current",
        "opening": OpeningCandidate(False, "", ""), "source_treatments": treatments,
        "source_disagreements": [diagnostic], "detail_review_state": {},
        "detail_coverage": assessment, "grounded": GroundingResult((), True, 0),
        "active_disputes": (), "dispute_audit": [],
        "execution": {"stages": {"dispute_review": {
            "account_coverage": deepcopy(assessment)}}}, "review_scope": deepcopy(SCOPE),
    }, wire_coverage


@pytest.mark.parametrize("owner_account,reviewer_account", [(False, True), (True, False)])
def test_recovery_owner_accepts_both_directions_of_actual_coverage_conflict(
        monkeypatch, owner_account, reviewer_account):
    arguments, wire_coverage = recovery_owner_inputs(
        owner_account=owner_account, reviewer_account=reviewer_account)
    dispatched = []

    def no_budget(model, phase, reader, **payload):
        dispatched.append({"phase": phase, "source_ids": list(payload["source_ids"])})
        return None

    monkeypatch.setattr(boundary, "_conditional_read", no_budget)
    result = boundary._recover_material(**arguments)
    observed = {
        "conditional_dispatches": len(dispatched),
        "selected_sources": dispatched[0]["source_ids"],
        "recovery_state": arguments["execution"]["semantic_recovery"][
            "source_reconsideration"]["state"],
        "admitted_material": len(result[0].details),
        "original_source_purpose_preserved": result[2] == arguments["source_treatments"],
    }
    record_case(
        "COVERAGE-OWNER-CONFLICT-" + ("POSITIVE" if reviewer_account else "NEGATIVE"),
        boundary="_recover_material owned diagnostic -> bounded source-owner dispatch",
        user_passage=ACCOUNT,
        model_outputs={"fresh_coverage": wire_coverage,
                       "owned_diagnostic": arguments["source_disagreements"][0]},
        expected={"conditional_dispatches": 1, "selected_sources": ["L1"],
                  "recovery_state": "budget_exhausted", "admitted_material": 0,
                  "original_source_purpose_preserved": True},
        observed=observed, calls=dispatched, scenario="paired", claim_scope="mechanical",
        protection_status="partial_preserved",
        notes=("Both typed Boolean conflict directions reach the same bounded owner; "
               "no provider runs."))


@pytest.mark.parametrize("defect", [
    "agree_account", "agree_non_account", "unknown_source", "changed_scope",
    "unowned_assessment", "changed_original_quote", "changed_original_turn",
    "changed_original_speaker", "changed_portion_quote", "changed_portion_hash",
    "boolean_offset", "integer_purpose", "unresolved_purpose",
])
def test_recovery_owner_rejects_forged_or_non_conflicting_coverage_diagnostic(
        monkeypatch, defect):
    if defect.startswith("agree_"):
        positive = defect == "agree_account"
        arguments, wire_coverage = recovery_owner_inputs(
            owner_account=positive, reviewer_account=positive)
    else:
        arguments, wire_coverage = recovery_owner_inputs()
    diagnostic = arguments["source_disagreements"][0]
    check = diagnostic["coverage_source_check"]
    if defect == "unknown_source":
        diagnostic["source_id"] = "foreign-source"
    elif defect == "changed_scope":
        diagnostic["review_scope"]["requests"][0]["material_purposes"] = ["account_contribution"]
    elif defect == "unowned_assessment":
        diagnostic["coverage_source_check"] = {**check, "reason": "Unowned alternate source read."}
    elif defect in {"changed_original_quote", "changed_original_turn", "changed_original_speaker"}:
        key, value = {
            "changed_original_quote": ("quoted", "The keeper identified the collector."),
            "changed_original_turn": ("turn_id", "another-turn"),
            "changed_original_speaker": ("role", "nm"),
        }[defect]
        check[key] = value
    elif defect in {"changed_portion_quote", "changed_portion_hash", "boolean_offset"}:
        key, value = {
            "changed_portion_quote": ("quoted", "The keeper identified the collector."),
            "changed_portion_hash": ("anchor_id", "foreign-anchor"),
            "boolean_offset": ("start", False),
        }[defect]
        check["substantive_spans"][0][key] = value
    elif defect == "integer_purpose":
        diagnostic["supplies_account_content"] = 1
    elif defect == "unresolved_purpose":
        check["content_purpose"] = "unresolved"
    if defect.startswith("changed_original_") or defect in {
            "changed_portion_quote", "changed_portion_hash", "boolean_offset",
            "unresolved_purpose"}:
        # Membership alone must not certify a corrupted canonical check.
        for assessment in (arguments["detail_coverage"], arguments["execution"]["stages"][
                "dispute_review"]["account_coverage"]):
            assessment["source_checks"] = [deepcopy(check)]
    dispatched = []

    def capture(model, phase, reader, **payload):
        dispatched.append(phase)
        return None

    monkeypatch.setattr(boundary, "_conditional_read", capture)
    original_treatments = deepcopy(arguments["source_treatments"])
    with pytest.raises(SchemaViolation):
        boundary._recover_material(**arguments)
    record_case(
        "COVERAGE-OWNER-REJECT-" + defect.upper(),
        boundary="_recover_material canonical diagnostic ownership before any conditional read",
        user_passage=ACCOUNT,
        model_outputs={"fresh_coverage": wire_coverage, "injected_diagnostic": diagnostic},
        expected={"dispatches": 0, "source_unchanged": True, "admitted_material": 0},
        observed={"dispatches": len(dispatched),
                  "source_unchanged": arguments["source_treatments"] == original_treatments,
                  "admitted_material": len(arguments["grounded"].details)},
        calls=dispatched, scenario="paired", claim_scope="mechanical", protection_status="blocked",
        notes=("This is a defensive injection at the code-owned diagnostic boundary; "
               "ordinary model replies cannot directly author this diagnostic."))


@pytest.mark.parametrize("purpose,expected_ids", [
    ("account", ["L1"]), ("unresolved", ["L1"]), ("non_account", []),
])
def test_localized_omission_keeps_unresolved_recovery_and_excludes_negative_source_purpose(
        purpose, expected_ids):
    references, treatments = source_catalogue(ACCOUNT)
    wire_coverage = coverage(
        references, state="partial", purposes={"L1": purpose},
        dispositions=[disposition("L1", references["L1"])])
    assessed = record.checked_coverage(
        wire_coverage, tuple(references), source_references=references)
    assessed.update(contract=record.ACCOUNT_COVERAGE_CONTRACT, review_scope=deepcopy(SCOPE))
    localized = boundary._localized_omission(assessed, SCOPE, treatments)
    record_case(
        "COVERAGE-OMISSION-PURPOSE-" + purpose.upper(),
        boundary="checked independent coverage -> localized bounded omission selection",
        user_passage=ACCOUNT, model_outputs={"fresh_coverage": wire_coverage},
        expected={"selected_source_ids": expected_ids},
        observed={"selected_source_ids": list(localized)}, calls=[], scenario="paired",
        claim_scope="mechanical", protection_status="admitted" if expected_ids else "blocked",
        notes=("A negative original-purpose read is not an extraction gap; genuine account and "
               "explicit unresolved missing portions remain eligible for bounded recovery."))
