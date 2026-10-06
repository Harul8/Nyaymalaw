"""Unfamiliar passage/output pairs exercise the real source-purpose boundary.

These are fabricated routine/Judge outputs, not semantic-model evaluations.
Three cases deliberately show consequences of schema-valid mistaken
source roles: passing a characterization does not mean that gap is prevented.
"""

import json
from copy import deepcopy

import pytest

from nm.brain.conversation import Message
from nm.brain.material import addressed_sources
from nm.brain.material_verification import _schema as material_review_schema
from nm.brain.record_review import classify_account_sources, validate_record_checks
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage, require_schema
from tests.brain_pressure_support import record_case


class PassageModel:
    """Return each supplied output once and capture the actual production call."""

    def __init__(self, outputs, *, strict=False):
        self.outputs = deepcopy(outputs)
        self.calls = []
        self.strict = strict

    def context_budget(self, tier):
        assert tier is Tier.ROUTINE
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        index = len(self.calls)
        assert index < len(self.outputs), "Unexpected additional source-classification call"
        output = deepcopy(self.outputs[index])
        self.calls.append(
            {
                "operation": prompt.operation,
                "tier": tier.value,
                "system": prompt.system,
                "input": json.loads(prompt.user),
                "schema": deepcopy(schema),
                "output": output,
                "max_tokens": max_tokens,
            }
        )
        if self.strict:
            try:
                require_schema(output, schema)
            except SchemaViolation as exc:
                self.calls[-1]["adapter_error"] = str(exc)
                raise
        return ModelResult(
            text=None,
            data=output,
            tier=tier,
            provider="offline",
            model="fabricated-pressure-source",
            usage=Usage(0, 0, 0),
            latency_ms=0,
            completion=Completion.COMPLETE,
        )


def treatments(roles, reason="The supplied framing determines this source purpose."):
    return {
        "source_treatments": {
            identity: {"content_role": role, "reason": reason} for identity, role in roles.items()
        }
    }


def supporting_review(source_ids):
    """A fabricated positive Judge attestation, passed to the production gate."""
    return {
        "candidate_id": "D1",
        "verdict": "accept",
        "operation_supported": True,
        "reason": "The attributed original account supports the proposed new detail.",
        "account_check": {
            "content_role": "reported_matter_account",
            "supported": True,
            "introduces_legal_analysis": False,
            "source_ids": list(source_ids),
            "source_checks": [
                {
                    "source_id": identity,
                    "supplies_account_content": True,
                    "supports_proposal": True,
                    "reason": "I judge this selected original passage to support the proposal.",
                }
                for identity in source_ids
            ],
            "reason": "The proposal is attributed to the selected original passage.",
        },
        "target_checks": [],
    }


def case(
    identity,
    latest,
    roles,
    *,
    earlier=(),
    selected=("L1",),
    expected_grounding=True,
    outputs=None,
    calls=1,
    error=False,
    feedback_fragment="",
    scenario="legitimate",
    status="admitted",
    claim_scope="mechanical",
    strict=False,
    notes="",
):
    return {
        "id": identity,
        "latest": latest,
        "earlier": earlier,
        "outputs": outputs if outputs is not None else [treatments(roles)],
        "selected": selected,
        "expected_grounding": expected_grounding,
        "expected_calls": calls,
        "error": error,
        "feedback_fragment": feedback_fragment,
        "scenario": scenario,
        "status": status,
        "claim_scope": claim_scope,
        "strict": strict,
        "notes": notes,
    }


def passage_cases():
    result = [
        case(
            "source-pressure-01-mixed-account-and-work",
            "Please review the tenancy record and note that the caretaker kept our only key.",
            {"L1": "mixed"},
            notes="A real factual contribution in the same span as work authority remains usable.",
        ),
        case(
            "source-pressure-02-tentative-account",
            "I think the inspection occurred on 18 August although the receipt may show 19 August.",
            {"L1": "reported_matter_account"},
            notes="Tentative certainty is distinct from examination-only source purpose.",
        ),
        case(
            "source-pressure-03-disputed-party-position",
            "The lessor alleges an oral renewal and demands a premium which our client disputes.",
            {"L1": "reported_party_position"},
            notes="Reporting an opposing position does not require adopting it as proven fact.",
        ),
        case(
            "source-pressure-04-unadopted-quoted-draft",
            "Examine this unadopted draft saying ‘the caretaker stole the key’ "
            "without treating it as my account.",
            {"L1": "examination_material"},
            expected_grounding=False,
            scenario="mixed",
            status="blocked",
            notes=(
                "The source read is valid but the fabricated positive candidate Judge is "
                "contradicted by its examination-only role."
            ),
        ),
        case(
            "source-pressure-05-earlier-nm-is-context",
            "NM previously called the voucher forged but I am only asking you "
            "to scrutinise that interpretation.",
            {"P1S1": "reported_matter_account", "L1": "nm_interpretation"},
            earlier=(
                Message("original-voucher", "advocate", "The clerk handed us an unsigned voucher."),
                Message("nm-voucher", "nm", "The voucher was forged."),
            ),
            expected_grounding=False,
            scenario="mixed",
            status="blocked",
            notes="Earlier NM words stay in the exact transcript but get no advocate source key.",
        ),
        case(
            "source-pressure-06-authorised-earlier-account-repair",
            "Restore the derived description from my original account without adding fresh facts.",
            {"P1S1": "reported_matter_account", "L1": "work_instruction"},
            earlier=(
                Message(
                    "earlier-key",
                    "advocate",
                    "The caretaker retained the key after the inspection.",
                ),
            ),
            selected=("P1S1",),
            notes=(
                "An instruction can authorise repair grounded by earlier substantive account "
                "without becoming the supporting fact."
            ),
        ),
        case(
            "source-pressure-07-explicit-uncertain-purpose",
            "I cannot tell whether these handwritten lines are witness notes "
            "or a proposed fictional reconstruction.",
            {"L1": "uncertain"},
            expected_grounding=False,
            scenario="mixed",
            status="blocked",
            notes=(
                "Uncertain classification is a valid completed read and is not silently "
                "promoted into substantive account."
            ),
        ),
    ]
    long_reason = (
        "The advocate is reporting receipt of the inventory, while preserving that no one has yet "
        "authenticated its signatures and that inspection of its physical contents "
        "remains outstanding. "
    ) * 12
    result.append(
        case(
            "source-pressure-08-supported-long-reason",
            "We received an inventory bearing unfamiliar signatures "
            "and have not authenticated them.",
            {"L1": "reported_matter_account"},
            outputs=[treatments({"L1": "reported_matter_account"}, long_reason)],
            notes=(
                "A substantive reason over 2,000 characters is accepted "
                "without arbitrary length rejection."
            ),
        )
    )
    result.append(
        case(
            "source-pressure-09-reason-surrounding-whitespace",
            "The receptionist told us the file remained in a locked cabinet.",
            {"L1": "reported_matter_account"},
            outputs=[
                treatments(
                    {"L1": "reported_matter_account"},
                    " \n  The advocate attributes the statement to the receptionist.\t ",
                )
            ],
            notes="Nonempty meaning survives surrounding whitespace and requires no correction.",
        )
    )

    earlier = (
        Message("prior-elevator", "advocate", "The lift stopped twice during the delivery."),
    )
    latest = (
        "Compare the delivery account with the earlier lift report. "
        "The unloading team retained our crate."
    )
    roles = {
        "P1S1": "reported_matter_account",
        "L1": "work_instruction",
        "L2": "reported_matter_account",
    }
    good = treatments(roles)
    missing = deepcopy(good)
    missing["source_treatments"].pop("P1S1")
    result.append(
        case(
            "source-pressure-10-missing-earlier-source-recovery",
            latest,
            roles,
            earlier=earlier,
            selected=("L2",),
            outputs=[missing, good],
            calls=2,
            feedback_fragment="source_treatments.P1S1",
            scenario="faulty",
            status="recovered",
            notes="A correct new-account role cannot conceal omission of an earlier owned source.",
        )
    )

    latest = "The watchman reported an unsealed parcel at the counter."
    earlier_nm = (Message("prior-nm-parcel", "nm", "The sender must have tampered with the seal."),)
    roles = {"L1": "reported_matter_account"}
    good = treatments(roles)
    forged = deepcopy(good)
    forged["source_treatments"]["P1S1"] = {
        "content_role": "reported_matter_account",
        "reason": "NM said so previously.",
    }
    result.append(
        case(
            "source-pressure-11-foreign-nm-source-recovery",
            latest,
            roles,
            earlier=earlier_nm,
            outputs=[forged, good],
            calls=2,
            feedback_fragment="source_treatments",
            scenario="faulty",
            status="recovered",
            notes="A prior NM sentence cannot be smuggled into the advocate source catalogue.",
        )
    )

    latest = "The bank displayed two incompatible closing balances for our account."
    good = treatments({"L1": "reported_matter_account"})
    duplicate = {
        "source_treatments": [
            {"source_id": "L1", "content_role": "reported_matter_account", "reason": "First copy."},
            {
                "source_id": "L1",
                "content_role": "examination_material",
                "reason": "Contradictory duplicate.",
            },
        ]
    }
    result.append(
        case(
            "source-pressure-12-duplicate-array-catalogue-recovery",
            latest,
            {"L1": "reported_matter_account"},
            outputs=[duplicate, good],
            calls=2,
            feedback_fragment="source_treatments",
            scenario="faulty",
            status="recovered",
            notes=(
                "The owned keyed shape refuses duplicated contradictory array entries "
                "rather than picking a winner."
            ),
        )
    )

    latest = "Our client received the notice after the advertised objection deadline."
    good = treatments({"L1": "reported_matter_account"})
    forged = deepcopy(good)
    forged["source_treatments"]["L1"].update(
        source_id="foreign-matter-source", turn_id="invented-owner", quoted="It was served in time."
    )
    result.append(
        case(
            "source-pressure-13-forged-provenance-fields-recovery",
            latest,
            {"L1": "reported_matter_account"},
            outputs=[forged, good],
            calls=2,
            feedback_fragment="source_treatments.L1",
            scenario="faulty",
            status="recovered",
            notes=(
                "The model may select purpose but cannot replace canonical turn, "
                "speaker or quotation."
            ),
        )
    )

    latest = "The technician declined to issue a calibration report."
    blank = treatments({"L1": "reported_matter_account"}, " \n\t ")
    empty = treatments({"L1": "reported_matter_account"}, "")
    result.append(
        case(
            "source-pressure-14-whitespace-then-empty-reason-terminal",
            latest,
            {"L1": "reported_matter_account"},
            outputs=[blank, empty],
            calls=2,
            error=True,
            feedback_fragment="reason",
            scenario="faulty",
            status="blocked",
            notes=(
                "Whitespace fails the substantive reason check and an empty replacement "
                "exhausts the single correction."
            ),
        )
    )

    latest = "The registry declined our bundle. Please verify the filing sequence."
    roles = {"L1": "reported_matter_account", "L2": "work_instruction"}
    omitted = treatments({"L1": "reported_matter_account"})
    result.append(
        case(
            "source-pressure-15-repeat-omission-bounded",
            latest,
            roles,
            outputs=[omitted, deepcopy(omitted)],
            calls=2,
            error=True,
            feedback_fragment="source_treatments.L2",
            scenario="faulty",
            status="blocked",
            notes=(
                "Repeated missing coverage produces a terminal contract error with exactly "
                "two calls, never an unbounded retry."
            ),
        )
    )

    result.extend(
        [
            case(
                "source-pressure-16-semantic-mislabel-false-rejection",
                "I personally saw the caretaker retain our key after the final inspection.",
                {"L1": "examination_material"},
                expected_grounding=False,
                scenario="faulty",
                status="gap_demonstrated",
                claim_scope="known_gap",
                notes=(
                    "Known substantive account is mislabeled by a schema-valid source read: "
                    "code admits that read without retry and the downstream gate rejects "
                    "a genuine account proposal. No semantic reconsideration exists."
                ),
            ),
            case(
                "source-pressure-17-semantic-mislabel-false-admission",
                "Review this unadopted draft alleging an undocumented cash payment "
                "without treating its allegation as my account.",
                {"L1": "reported_matter_account"},
                expected_grounding=True,
                scenario="faulty",
                status="gap_demonstrated",
                claim_scope="semantic_dependency",
                notes=(
                    "Source classifier and fabricated candidate Judge both make the same "
                    "substantive error. Mechanical contracts admit it; this measures the "
                    "dependency, not the live Judge's error rate or an actual released turn."
                ),
            ),
            case(
                "source-pressure-18-instruction-only-mixed-false-admission",
                "Re-examine whether your derived account implies a missing inventory "
                "and preserve the original sources.",
                {"L1": "mixed"},
                expected_grounding=True,
                scenario="faulty",
                status="gap_demonstrated",
                claim_scope="semantic_dependency",
                notes=(
                    "A pure work instruction mislabeled mixed can support a false positive "
                    "Judge attestation. Code cannot infer whether genuinely substantive "
                    "content exists inside a declared mixed span."
                ),
            ),
        ]
    )
    latest = (
        "Please audit the delivery chronology. "
        "I received the signed receipt after the depot closed."
    )
    roles = {"L1": "work_instruction", "L2": "reported_matter_account"}
    good = treatments(roles)
    missing = deepcopy(good)
    missing["source_treatments"].pop("L1")
    result.append(
        case(
            "source-pressure-19-strict-adapter-hidden-missing-recovery",
            latest,
            roles,
            selected=("L2",),
            outputs=[missing, good],
            calls=2,
            feedback_fragment="source_treatments.L1",
            strict=True,
            scenario="faulty",
            status="recovered",
            notes=(
                "The strict adapter invokes production require_schema and rejects before "
                "returning ModelResult. Correction retains the complete original input and "
                "exact schema path but rejected_output is None; hidden response words "
                "are not claimed to be visible to the Brain."
            ),
        )
    )
    foreign = deepcopy(good)
    foreign["source_treatments"]["other-matter-source"] = {
        "content_role": "reported_matter_account",
        "reason": "An unrelated matter also has a receipt.",
    }
    result.append(
        case(
            "source-pressure-20-strict-adapter-repeat-foreign-terminal",
            latest,
            roles,
            selected=("L2",),
            outputs=[foreign, deepcopy(foreign)],
            calls=2,
            error=True,
            feedback_fragment="source_treatments",
            strict=True,
            scenario="faulty",
            status="blocked",
            notes=(
                "Both foreign-key catalogues fail inside the strict adapter. The Brain "
                "gets no rejected response object, preserves the whole original input, "
                "and terminates after the one allowed correction."
            ),
        )
    )
    return result


@pytest.mark.parametrize("spec", passage_cases(), ids=lambda spec: spec["id"])
def test_paired_passage_source_classification_pressure(spec):
    payload, _, _ = addressed_sources(spec["earlier"], spec["latest"])
    model = PassageModel(spec["outputs"], strict=spec["strict"])
    catalogue = None
    failure = None
    try:
        catalogue = classify_account_sources(
            model, payload=payload, latest_turn_id="pressure-latest"
        )
    except SchemaViolation as exc:
        failure = exc

    review = supporting_review(spec["selected"])
    grounding = None
    issues = []
    if catalogue is not None:
        require_schema(
            {"verdicts": [review]},
            material_review_schema(("D1",), source_ids=tuple(catalogue)),
        )
        grounding = validate_record_checks(
            review,
            source_ids=set(catalogue),
            target_ids=set(),
            candidate_id="D1",
            candidates={"D1": set()},
            source_treatments=catalogue,
            issues=issues,
        )

    corrections = model.calls[1:]
    original_input = model.calls[0]["input"]
    feedback_exact = all(
        entry["input"].get("original_input") == original_input
        and entry["input"].get("rejected_output")
        == (None if spec["strict"] else spec["outputs"][0])
        and spec["feedback_fragment"] in entry["input"].get("validation_issue", "")
        for entry in corrections
    )
    canonical = catalogue is None or all(
        row["role"] == "advocate"
        and (row["turn_id"], row["quoted"])
        in {
            (message["turn_id"], span["text"].strip())
            for message in payload["earlier_conversation"]
            if message["role"] == "advocate"
            for span in message["source_spans"]
            if span["text"].strip()
        }
        | {
            ("pressure-latest", span["text"].strip())
            for span in payload["latest_message_spans"]
            if span["text"].strip()
        }
        for row in catalogue.values()
    )
    expected = {
        "source_read": "blocked" if spec["error"] else "admitted",
        "calls": spec["expected_calls"],
        "retries": spec["expected_calls"] - 1,
        "grounding_admitted": None if spec["error"] else spec["expected_grounding"],
        "correction_preserves_input_and_names_mismatch": True,
        "canonical_attribution_preserved": True,
        "strict_adapter_rejections": spec["expected_calls"]
        if spec["strict"] and spec["error"]
        else int(spec["strict"]),
        "grounding_has_precise_conflict": bool(
            not spec["error"] and not spec["expected_grounding"]
        ),
    }
    observed = {
        "source_read": "blocked" if failure is not None else "admitted",
        "calls": len(model.calls),
        "retries": max(0, len(model.calls) - 1),
        "grounding_admitted": grounding,
        "correction_preserves_input_and_names_mismatch": feedback_exact,
        "canonical_attribution_preserved": canonical,
        "strict_adapter_rejections": sum("adapter_error" in entry for entry in model.calls),
        "grounding_has_precise_conflict": bool(issues),
    }
    user_passage = {
        "earlier_conversation": [
            {"turn_id": message.turn_id, "role": message.role, "text": message.text}
            for message in spec["earlier"]
        ],
        "latest": spec["latest"],
    }
    outputs = [
        *spec["outputs"],
        {"fabricated_candidate_judge": review, "submitted_to_gate": catalogue is not None},
    ]
    record_case(
        spec["id"],
        boundary="classify_account_sources -> validate_record_checks",
        user_passage=user_passage,
        model_outputs=outputs,
        expected=expected,
        observed=observed,
        calls=model.calls,
        scenario=spec["scenario"],
        claim_scope=spec["claim_scope"],
        protection_status=spec["status"],
        notes=spec["notes"]
        + (" Grounding conflicts: " + "; ".join(issues) if issues else "")
        + (" Terminal error: " + str(failure) if failure is not None else ""),
    )
