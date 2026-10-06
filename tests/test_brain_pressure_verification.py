"""Offline paired passages through the shipped material-verification boundary.

Scripted semantic judgments demonstrate dependency/wiring, not reviewer accuracy.
Every provider response is checked using the real adapter schema contract before
the real verifier receives it. Evidence distinguishes characterized gaps from
protections that actually worked.
"""

import json
from copy import deepcopy
from dataclasses import asdict

from nm.brain.conversation import OpeningCandidate
from nm.brain.material import MaterialCandidate, addressed_sources
from nm.brain.material_verification import verify_material_grounding
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage, require_schema
from tests.brain_pressure_support import record_case


class PassageJudge:
    """Fabricated provider transport; validation belongs to production code."""

    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []
        self.emitted = []

    def context_budget(self, tier):
        assert tier is Tier.JUDGE
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        output = next(self.outputs)
        data = output(payload) if callable(output) else deepcopy(output)
        self.emitted.append(deepcopy(data))
        call = {
            "operation": prompt.operation,
            "tier": tier.value,
            "input": payload,
            "output": deepcopy(data),
            "max_tokens": max_tokens,
            "transport": "received",
        }
        self.calls.append(call)
        try:
            require_schema(data, schema)
        except SchemaViolation as exc:
            call["transport"] = "whole_envelope_rejected"
            call["adapter_issue"] = str(exc)
            raise
        return ModelResult(
            text=None,
            data=data,
            tier=tier,
            provider="offline",
            model="fabricated-passage-judge",
            usage=Usage(0, 0, 0),
            latency_ms=0,
            completion=Completion.COMPLETE,
        )


def proposed(words, *, statement=None, targets=()):
    return MaterialCandidate(
        kind="event",
        statement=statement or words,
        quoted=words,
        relation="corrects" if targets else "new",
        prior_references=(),
        matter_scope="current",
        basis="stated",
        importance="relevant",
        why_material="The reported event affects the matter's chronology.",
        placement="matter",
        related_material_ids=tuple(targets),
    )


def source_roles(latest):
    _, sources, _ = addressed_sources((), latest)
    return {
        identity: {
            "turn_id": "latest",
            "role": "advocate",
            "quoted": words,
            "content_role": "reported_matter_account",
            "reason": "Fabricated source-owner judgment of original account.",
        }
        for identity, words in sources.items()
    }


def coverage(state="complete", missing=(), reason="Original account is faithfully represented."):
    return {"state": state, "missing_source_ids": list(missing), "reason": reason}


def decision(payload, candidate_id, *, accept=True, peers=(), reason=None):
    item = next(row for row in payload["candidates"] if row["candidate_id"] == candidate_id)
    sources = item["allowed_account_source_ids"][:1] if accept else []
    return {
        "candidate_id": candidate_id,
        "verdict": "accept" if accept else "reject",
        "operation_supported": accept,
        "reason": reason or "Scripted judgment of whole attributed proposal and operation.",
        "account_check": {
            "content_role": "reported_matter_account" if accept else "uncertain",
            "supported": accept,
            "introduces_legal_analysis": False,
            "source_ids": sources,
            "source_checks": [
                {
                    "source_id": identity,
                    "supplies_account_content": True,
                    "supports_proposal": True,
                    "reason": "Selected original advocate account supports the proposal.",
                }
                for identity in sources
            ],
            "reason": "Whole proposition was assessed against the original account.",
        },
        "target_checks": [
            {
                "target_id": target,
                "identity_relation": "restore_invalid_interpretation",
                "account_preserved": accept,
                "required_peer_ids": list(peers),
                "reason": "Scripted restoration preserves the attributed underlying account.",
            }
            for target in item["related_material_ids"]
        ],
    }


def envelope(payload, *, assessment=None):
    return {
        "verdicts": [decision(payload, row["candidate_id"]) for row in payload["candidates"]],
        "coverage": coverage() if assessment is None else deepcopy(assessment),
    }


def observed_summary(result, sink, model):
    return {
        "accepted": len(result.details),
        "rejected": result.rejected_details,
        "unread": result.unread_details,
        "withheld": result.withheld_details,
        "coverage": sink["state"],
        "missing_ids": sink["missing_source_ids"],
        "attempts": len(model.calls),
        "retry_candidates": (
            [r["candidate_id"] for r in model.calls[1]["input"]["candidates"]]
            if len(model.calls) > 1
            else []
        ),
        "retained_candidates": (
            [
                r["candidate_id"]
                for r in model.calls[1]["input"].get("retained_candidate_context", [])
            ]
            if len(model.calls) > 1
            else []
        ),
    }


def expected(
    *,
    accepted=0,
    rejected=0,
    unread=0,
    withheld=0,
    state="complete",
    missing=(),
    attempts=1,
    retry=(),
    retained=(),
):
    return {
        "accepted": accepted,
        "rejected": rejected,
        "unread": unread,
        "withheld": withheld,
        "coverage": state,
        "missing_ids": list(missing),
        "attempts": attempts,
        "retry_candidates": list(retry),
        "retained_candidates": list(retained),
    }


def run_case(
    case_id,
    latest,
    candidates,
    outputs,
    expectation,
    *,
    targets=(),
    scenario="faulty",
    claim_scope="mechanical",
    status="blocked",
    notes="",
):
    model = PassageJudge(outputs)
    sink = {}
    before = deepcopy(targets)
    result = verify_material_grounding(
        model,
        candidates=candidates,
        opening=OpeningCandidate(False, "", ""),
        earlier=(),
        latest=latest,
        source_treatments=source_roles(latest),
        review_scope={"purpose": "Review the complete original material account."},
        prior_material=targets,
        active_material=targets,
        coverage=sink,
    )
    assert targets == before, "Read-only verification must not mutate canonical targets"
    model.calls[-1]["final_verifier_result"] = {
        "result": asdict(result),
        "coverage": deepcopy(sink),
        "canonical_targets_unchanged": targets == before,
    }
    record_case(
        case_id,
        boundary="nm.brain.material_verification.verify_material_grounding",
        user_passage=latest,
        model_outputs=[{"extractor_proposals": [asdict(c) for c in candidates]}, *model.emitted],
        expected=expectation,
        observed=observed_summary(result, sink, model),
        calls=model.calls,
        scenario=scenario,
        claim_scope=claim_scope,
        protection_status=status,
        notes=notes + " Source-owner semantic treatments are scripted, not measured.",
    )
    return result, sink, model


def test_accurate_uncertain_attributed_complex_account_is_admitted():
    first = (
        "The engineer reports that handover was probably on 8 June, but has not checked the diary."
    )
    second = "The client says the signed inventory stayed with the warehouse manager."
    candidates = (proposed(first), proposed(second))
    run_case(
        "material-01-accurate-complex",
        first + " " + second,
        candidates,
        [envelope],
        expected(accepted=2),
        scenario="legitimate",
        status="admitted",
        notes=(
            "Uncertainty and attribution remain in the candidate statements; acceptance "
            "wiring works."
        ),
    )


def test_empty_review_can_legitimately_be_complete_without_new_rows():
    latest = (
        "The signed inventory is already recorded accurately; I am adding no factual correction."
    )
    targets = ({"id": "inventory", "statement": latest, "quoted": latest},)
    run_case(
        "material-02-valid-empty-no-change",
        latest,
        (),
        [{"verdicts": [], "coverage": coverage()}],
        expected(),
        targets=targets,
        scenario="legitimate",
        status="admitted",
        notes="An independently declared complete review does not require a new material row.",
    )


def test_empty_extraction_with_omitted_date_is_reported_but_not_reextracted():
    latest = "Please correct the handover date: the handover took place on 8 June, not 7 June."
    run_case(
        "material-03-empty-date-omission-no-recovery",
        latest,
        (),
        [
            {
                "verdicts": [],
                "coverage": coverage(
                    "partial", ["L1"], "L1 contains an unrepresented date correction to 8 June."
                ),
            }
        ],
        expected(state="partial", missing=["L1"]),
        claim_scope="known_gap",
        status="gap_demonstrated",
        notes=(
            "Coverage flags the omitted date without calling an extractor or recovering "
            "it; one Judge attempt only."
        ),
    )


def test_valid_unlocalised_partial_scope_is_not_retried_as_metadata_error():
    latest = "The storage records conflict, and I cannot tell which belongs to this matter."
    run_case(
        "material-04-unlocalised-partial",
        latest,
        (),
        [
            {
                "verdicts": [],
                "coverage": coverage(
                    "partial",
                    [],
                    "Matter association remains unresolved across the described records.",
                ),
            }
        ],
        expected(state="partial"),
        scenario="legitimate",
        status="admitted",
        notes=(
            "A consequential unresolved scope can be partial without a selected missing source ID."
        ),
    )


def test_conflicting_complete_coverage_is_repaired_without_repeating_valid_candidate():
    latest = "The handover occurred on 8 June."
    run_case(
        "material-05-complete-missing-conflict",
        latest,
        (proposed(latest),),
        [
            lambda p: envelope(p, assessment=coverage("complete", ["L1"])),
            {"verdicts": [], "coverage": coverage()},
        ],
        expected(accepted=1, attempts=2, retained=["D1"]),
        scenario="mixed",
        status="recovered",
        notes=(
            "Contradictory complete+missing metadata gets one coverage-only correction; "
            "checked proposal survives."
        ),
    )


def test_exact_duplicate_missing_ids_and_reason_whitespace_are_losslessly_normalised():
    latest = "The handover date is missing from the chronology."
    run_case(
        "material-06-harmless-coverage-normalisation",
        latest,
        (),
        [
            {
                "verdicts": [],
                "coverage": coverage(
                    "partial", ["L1", "L1"], "  L1 chronology is still omitted.  "
                ),
            }
        ],
        expected(state="partial", missing=["L1"]),
        scenario="legitimate",
        status="admitted",
        notes=(
            "Duplicate owned coverage IDs and surrounding reason whitespace do not cause a retry."
        ),
    )


def test_foreign_missing_source_cannot_enter_coverage_after_exhausted_correction():
    latest = "The handover occurred on 8 June."
    wrong = {"verdicts": [], "coverage": coverage("partial", ["other-client-private-source"])}
    run_case(
        "material-07-foreign-coverage-source",
        latest,
        (),
        [wrong, wrong],
        expected(state="unassessed", attempts=2),
        notes=(
            "Strict transport rejects the unowned source on both attempts; no foreign "
            "source is bound."
        ),
    )


def test_other_candidates_owned_source_is_not_this_candidates_source():
    first, second = "The keys were delivered on 8 June.", "The inventory was signed on 9 June."

    def wrong(payload):
        data = envelope(payload)
        row = data["verdicts"][0]
        row["account_check"]["source_ids"] = ["L2"]
        row["account_check"]["source_checks"][0]["source_id"] = "L2"
        return data

    run_case(
        "material-08-cross-candidate-source",
        first + " " + second,
        (proposed(first), proposed(second)),
        [wrong, envelope],
        expected(accepted=2, attempts=2, retry=["D1"], retained=["D2"]),
        scenario="mixed",
        status="recovered",
        notes=(
            "A source in the shared envelope vocabulary is still checked against its "
            "candidate's exact owned sources."
        ),
    )


def test_missing_selected_source_check_requires_one_bounded_correction():
    latest = "The keys were delivered on 8 June."

    def wrong(payload):
        data = envelope(payload)
        data["verdicts"][0]["account_check"]["source_checks"] = []
        return data

    run_case(
        "material-09-missing-source-check",
        latest,
        (proposed(latest),),
        [wrong, envelope],
        expected(accepted=1, attempts=2, retry=["D1"]),
        status="recovered",
        notes=(
            "Selected source IDs must have exactly corresponding source checks; no "
            "acceptance on the first attempt."
        ),
    )


def test_overall_accept_cannot_override_explicit_unsupported_account():
    latest = "The keys were delivered on 8 June."

    def wrong(payload):
        data = envelope(payload)
        data["verdicts"][0]["account_check"]["supported"] = False
        return data

    run_case(
        "material-10-accept-unsupported",
        latest,
        (proposed(latest),),
        [wrong, wrong],
        expected(unread=1, state="unassessed", attempts=2, retry=["D1"]),
        notes=(
            "An internally contradictory positive decision remains unread after its "
            "correction bound."
        ),
    )


def test_overall_accept_cannot_override_explicit_added_legal_analysis():
    latest = "The manager kept the inventory overnight."

    def wrong(payload):
        data = envelope(payload)
        data["verdicts"][0]["account_check"]["introduces_legal_analysis"] = True
        return data

    run_case(
        "material-11-added-legal-analysis",
        latest,
        (proposed(latest),),
        [wrong, wrong],
        expected(unread=1, state="unassessed", attempts=2, retry=["D1"]),
        notes=(
            "Code catches explicit conflicting attestations, not legal meaning in the "
            "candidate prose."
        ),
    )


def test_replacement_cannot_accept_different_target_identity():
    latest = "The keys were delivered on 8 June."
    target = ({"id": "keys", "statement": "The keys were delivered on 7 June."},)

    def wrong(payload):
        data = envelope(payload)
        data["verdicts"][0]["target_checks"][0]["identity_relation"] = "different"
        return data

    run_case(
        "material-12-different-target",
        latest,
        (proposed(latest, targets=["keys"]),),
        [wrong, wrong],
        expected(unread=1, state="unassessed", attempts=2, retry=["D1"]),
        targets=target,
        notes="Owned target identity does not override an explicitly unrelated target check.",
    )


def test_missing_target_check_is_not_accepted_as_completed_replacement():
    latest = "The keys were delivered on 8 June."
    target = ({"id": "keys", "statement": "The keys were delivered on 7 June."},)

    def wrong(payload):
        data = envelope(payload)
        data["verdicts"][0]["target_checks"] = []
        return data

    run_case(
        "material-13-missing-target-check",
        latest,
        (proposed(latest, targets=["keys"]),),
        [wrong, envelope],
        expected(accepted=1, attempts=2, retry=["D1"]),
        targets=target,
        status="recovered",
        notes="The entire selected target set must be checked before replacement can be admitted.",
    )


def test_foreign_required_restoration_peer_cannot_be_used():
    latest = "The keys were delivered on 8 June."
    target = ({"id": "keys", "statement": "The keys were delivered on 7 June."},)

    def wrong(payload):
        data = envelope(payload)
        data["verdicts"][0]["target_checks"][0]["required_peer_ids"] = ["FOREIGN-PEER"]
        return data

    run_case(
        "material-14-foreign-peer",
        latest,
        (proposed(latest, targets=["keys"]),),
        [wrong, wrong],
        expected(unread=1, state="unassessed", attempts=2, retry=["D1"]),
        targets=target,
        notes="The owned same-target peer vocabulary prevents invented restoration dependencies.",
    )


def test_long_substantive_reason_is_not_rejected_for_arbitrary_width():
    latest = "The manager says the inventory remained sealed, although the receipt was unsigned."
    long_reason = (
        "The proposal preserves the manager's attribution, the limited reported seal status, "
        "and the separate uncertainty about the unsigned receipt. "
    ) * 18

    def valid(payload):
        data = envelope(payload)
        data["verdicts"][0]["reason"] = long_reason
        data["verdicts"][0]["account_check"]["reason"] = long_reason
        data["coverage"]["reason"] = long_reason
        return data

    run_case(
        "material-15-long-valid-reasons",
        latest,
        (proposed(latest),),
        [valid],
        expected(accepted=1),
        scenario="legitimate",
        status="admitted",
        notes=(
            "A >2,000-character reason is admitted within the actual resource budget; no"
            " artificial width rejection."
        ),
    )


def test_valid_peer_survives_schema_valid_malformed_sibling_exhaustion():
    first, second = "The keys arrived on 8 June.", "The inventory arrived on 9 June."

    def wrong(payload):
        data = envelope(payload)
        next(row for row in data["verdicts"] if row["candidate_id"] == "D2")["reason"] = "  "
        return data

    run_case(
        "material-16-retained-peer-unread-sibling",
        first + " " + second,
        (proposed(first), proposed(second)),
        [wrong, wrong],
        expected(
            accepted=1, unread=1, state="unassessed", attempts=2, retry=["D2"], retained=["D1"]
        ),
        scenario="mixed",
        status="blocked",
        notes=(
            "Only the malformed sibling is retried; the independently checked first "
            "proposal is retained."
        ),
    )


def test_strict_adapter_rejection_hides_valid_first_attempt_sibling():
    first, second = "The keys arrived on 8 June.", "The inventory arrived on 9 June."

    def wrong(payload):
        data = envelope(payload)
        del data["verdicts"][1]["account_check"]
        return data

    run_case(
        "material-17-hidden-peer-whole-envelope-gap",
        first + " " + second,
        (proposed(first), proposed(second)),
        [wrong, {"verdicts": [], "coverage": coverage()}],
        expected(unread=2, state="unassessed", attempts=2, retry=["D1", "D2"]),
        scenario="mixed",
        claim_scope="known_gap",
        status="gap_demonstrated",
        notes=(
            "A valid first-attempt sibling cannot be retained when strict provider "
            "validation hides the entire envelope."
        ),
    )


def test_required_restoration_failure_withholds_retirement_but_preserves_independent_peer():
    first, second, third = (
        "The keys arrived on 8 June.",
        "The inventory arrived on 9 June.",
        "The gate remained open.",
    )
    target = ({"id": "merged", "statement": "Both deliveries occurred together on 7 June."},)

    def mixed(payload):
        return {
            "verdicts": [
                decision(payload, "D1", peers=["D2"]),
                decision(payload, "D2", accept=False),
                decision(payload, "D3"),
            ],
            "coverage": coverage(),
        }

    run_case(
        "material-18-restoration-dependency-closure",
        " ".join((first, second, third)),
        (
            proposed(first, targets=["merged"]),
            proposed(second, targets=["merged"]),
            proposed(third),
        ),
        [mixed],
        expected(accepted=1, rejected=1, withheld=1, state="unassessed"),
        targets=target,
        scenario="mixed",
        status="blocked",
        notes=(
            "An accepted replacement depending on a rejected successor is withheld; the "
            "canonical old target is untouched."
        ),
    )


def test_fabricated_wrong_date_is_rejected_when_semantic_judge_rejects_it():
    latest = "The handover took place on 8 June, and I have never said it took place on 18 June."
    candidate = proposed(latest, statement="The handover took place on 18 June.")

    def reject(payload):
        return {
            "verdicts": [
                decision(
                    payload,
                    "D1",
                    accept=False,
                    reason="The candidate invents 18 June, contrary to the selected account.",
                )
            ],
            "coverage": coverage(
                "partial",
                ["L1"],
                "The rejected candidate leaves the actual 8 June event unrepresented.",
            ),
        }

    run_case(
        "material-19-wrong-date-semantic-reject-wiring",
        latest,
        (candidate,),
        [reject],
        expected(rejected=1, state="partial", missing=["L1"]),
        claim_scope="semantic_dependency",
        status="blocked",
        notes=(
            "A fabricated correct rejection proves rejection wiring only; it does not "
            "measure real-model date-error detection."
        ),
    )


def test_mechanical_contract_cannot_detect_wrong_date_if_semantic_judge_falsely_accepts():
    latest = "The handover took place on 8 June, and I have never said it took place on 18 June."
    candidate = proposed(latest, statement="The handover took place on 18 June.")
    run_case(
        "material-20-wrong-date-false-judge-acceptance",
        latest,
        (candidate,),
        [envelope],
        expected(accepted=1),
        claim_scope="semantic_dependency",
        status="gap_demonstrated",
        notes=(
            "A structurally consistent but semantically wrong positive review admits the"
            " false statement at this boundary. This is an observed semantic dependency,"
            " not a prevented error or a measured model error rate."
        ),
    )
