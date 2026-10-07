"""Public regressions for scope and code-owned mixed outcomes.

All meanings are declared offline; a scripted ACCEPT is never evidence
that a real reviewer would identify identity or an operational false claim.
"""

from copy import deepcopy

import pytest

from tests.brain_golden_pressure_fixture import GoldenModel, evidence, release
from tests.test_brain_golden_boundaries import (
    dated_dossier,
    owned_outcome,
    requirement,
    seed,
)

pytestmark = pytest.mark.class_a


def correction_fixture(client, wired, monkeypatch, *, identity, declared_requirement):
    """The actual original GS date/custody predecessor and implicit contribution."""
    original = dated_dossier(corrected=False)
    corrected = dated_dossier(corrected=True)
    baseline, _, previous = seed(client, wired, monkeypatch, original, identity + "-seed")
    date_target = previous.open_material[0]["id"]
    custody_target = previous.open_material[1]["id"]
    for source_id, words in original.source_quotes.items():
        if words not in corrected.source_quotes.values():
            corrected.source_quotes["earlier-" + source_id] = words
            corrected.source_roles["earlier-" + source_id] = original.source_roles[source_id]
    # A declared non-new scope requires its actual outcome even when the
    # interpreter's redundant requirement field says none.
    standard = owned_outcome("performed", linked=True)
    # Author this scope independently of reader output, including the implicit
    # contribution path. Old baseline transport lacks the field; fresh transport
    # carries this same author decision rather than deriving it from a proposal.
    mutation_scope = {
        "authority_kind": "account_contribution",
        "authority_source_ids": [corrected.details[0]["source_id"]],
        "target_scope": "exact",
        "target_ids": [date_target],
        "permitted_relations": ["corrects"],
    }

    def script(operation, payload, schema, data, model):
        data = standard(operation, payload, schema, data, model)
        if operation == "interpret_conversation":
            data["items"][0].update(
                intent="contribution", material_purposes=["account_contribution"]
            )
            item_fields = schema["properties"]["items"]["items"]["anyOf"][0]["properties"]
            if "mutation_scopes" in item_fields:
                data["items"][0]["mutation_scopes"] = [deepcopy(mutation_scope)]
        if operation == "extract_legal_details":
            original_input = payload.get("original_input", payload)
            earlier_ids = [
                span["id"]
                for message in original_input["earlier_conversation"]
                if message["role"] == "advocate"
                for span in message["source_spans"]
                if original.source_quotes[original.details[0]["source_id"]]
                == span["text"].strip()
            ]
            assert len(earlier_ids) == 1
            return {
                "new_items": [],
                "changes": [
                    {
                        **deepcopy(corrected.details[0]),
                        "prior_source_ids": earlier_ids,
                        "relation": "corrects",
                        "related_material_ids": [date_target],
                    }
                ],
            }
        if operation == "verify_material_grounding":
            original_input = payload.get("original_input", payload)
            candidates = {row["candidate_id"]: row for row in original_input["candidates"]}
            for verdict in data["verdicts"]:
                verdict["target_checks"] = [
                    {
                        "target_id": target,
                        "identity_relation": "same_underlying_account",
                        "account_preserved": True,
                        "required_peer_ids": [],
                        "reason": "The original date statement corrects its dated predecessor.",
                    }
                    for target in candidates[verdict["candidate_id"]]["related_material_ids"]
                ]
        if operation == "continue_conversation":
            for unit in data["units"]:
                unit["work_selector"] = "$no_task"
        return data

    model = GoldenModel(
        corrected,
        response_mode="substantive",
        requirement=(
            requirement(
                targets=(date_target,),
                operation="corrects",
                condition="The original dated account now records 15-4-2024.",
            )
            if declared_requirement
            else None
        ),
        reply="Your later account supplies 15-4-2024; the custody account is separate.",
        hook=script,
    )
    for attributes in model.semantic_attributes.values():
        attributes["matter_scope"] = "current"
    return model, baseline, previous, date_target, custody_target


@pytest.mark.parametrize("declared_requirement", [False, True])
def test_original_implicit_contribution_and_explicit_correction_both_remain_admissible(
    client, wired, monkeypatch, declared_requirement
):
    identity = "scope-neighbor-date-" + str(declared_requirement).lower()
    model, baseline, previous, date_target, custody_target = correction_fixture(
        client,
        wired,
        monkeypatch,
        identity=identity,
        declared_requirement=declared_requirement,
    )
    data, saved, conversation = release(
        client, wired, monkeypatch, model, identity, opened=baseline
    )
    active = {row["id"]: row for row in conversation.open_material}
    receipt = data["material_coverage"]["execution"]
    expected = {
        "blocked": False,
        "date_predecessor_retired": True,
        "independent_custody_preserved": True,
        "corrected_date_saved": True,
        "saved_exact_reply": True,
        "conditional_calls": 0,
        "fulfillment": "fulfilled",
    }
    observed = {
        "blocked": data["blocked"],
        "date_predecessor_retired": date_target not in active,
        "independent_custody_preserved": active.get(custody_target)
        == previous.open_material[1],
        "corrected_date_saved": model.dossier.details[0]["statement"]
        in {row["statement"] for row in active.values()},
        "saved_exact_reply": saved.brain_chat[-1]["response"]["elements"] == data["elements"],
        "conditional_calls": data["metrics"]["recovery"]["dispatched_calls"],
        "fulfillment": receipt["requests"][0]["fulfillment"],
    }
    evidence(
        identity,
        model,
        data,
        saved,
        expected,
        observed,
        scenario="legitimate",
        protection_status="admitted",
        notes="The exact GS-15 later source says 'sorry, 15-4-2024'; "
        "the author explicitly labels correction identity. No imperative is required.",
    )
    assert observed == expected


@pytest.mark.parametrize("outcome_owner", ["completion", "question"])
def test_mixed_pending_correction_keeps_independent_account_and_question(
    client, wired, monkeypatch, outcome_owner
):
    """A question must not disable outcome rendering or be erased to enable it."""
    identity = "scope-neighbor-mixed-" + outcome_owner
    model, baseline, previous, date_target, custody_target = correction_fixture(
        client, wired, monkeypatch, identity=identity, declared_requirement=True
    )
    core = model.hook
    lie = "The correction was applied, saved, and all of this matter's work is complete."
    question = "What needs clarification about the event of the following account?"
    independent_account = previous.open_material[1]["quoted"]

    def mixed(operation, payload, schema, data, current_model):
        data = core(operation, payload, schema, data, current_model)
        if operation == "extract_legal_details":
            return {"new_items": [], "changes": []}
        if operation == "continue_conversation":
            for unit in data["units"]:
                source = current_model.dossier.details[0]["source_id"]
                unit["blocks"] = [
                    {
                        "id": "claimed-completion",
                        "kind": "completion",
                        "evidence_expression": {"operator": "record_result"
                                                if outcome_owner == "completion"
                                                else "source_account",
                                                "source_ids": []
                                                if outcome_owner == "completion" else [source],
                                                "record_ids": [],
                                                "focus": "none"},
                        "uncertainty": "reported",
                    },
                    {
                        "id": "independent-account",
                        "kind": "account",
                        "evidence_expression": {"operator": "source_account",
                                                "source_ids": [],
                                                "record_ids": [custody_target],
                                                "focus": "none"},
                        "uncertainty": "reported",
                    },
                    {
                        "id": "instrument-question",
                        "kind": "question",
                        "evidence_expression": {"operator": "question",
                                                "source_ids": [source], "record_ids": [],
                                                "focus": "event"},
                        "uncertainty": "uncertain",
                    },
                ]
                # Fabricate the forbidden success prose on the first attempt;
                # the bounded repair supplies only fresh owned expressions.
                if "correction" not in payload:
                    unit["blocks"][0]["text"] = lie
                unit["questions"] = [
                    {
                        "id": "instrument-identity",
                        "block_id": "instrument-question",
                        "purpose": "Identify the instrument associated with the correction.",
                        "target_ids": [date_target],
                        "existing_id": "",
                    }
                ]
                unit["sufficiency"] = {"status": "needs_input", "block_id": "instrument-question"}
                unit["record_outcome"] = {
                    "status": "unresolved",
                    "block_id": "claimed-completion"
                    if outcome_owner == "completion"
                    else "instrument-question",
                    "effect_ids": [],
                    "current_record_ids": [],
                    "reason": "The scripted result owner leaves the correction unfinished.",
                }
        if operation == "verify_continuation":
            for verdict in data["accepted_units"]:
                verdict["record_check"] = {
                    "outcome": "unfinished",
                    "reason": "No operation changed the dated predecessor.",
                }
                verdict["proposal_checks"] = [
                    {
                        "section": "questions",
                        "proposal_id": "instrument-identity",
                        "block_id": "instrument-question",
                        "purpose_expressed": True,
                        "identity_preserved": True,
                        "verdict": "accept",
                        "reason": "The instrument identity is missing from the exact account.",
                    }
                ]
        return data

    model.hook = mixed
    model.reply = lie
    data, saved, conversation = release(
        client, wired, monkeypatch, model, identity, opened=baseline
    )
    public_text = "\n".join(element["text"] for element in data["elements"])
    expected = {
        "false_operational_prose_released": False,
        "independent_account_preserved": True,
        "question_preserved": True,
        "typed_unfinished_status_visible": True,
        "predecessors_preserved": True,
        "fulfillment": "unfinished",
        "saved_exact_reply": True,
    }
    observed = {
        "false_operational_prose_released": lie in public_text,
        "independent_account_preserved": independent_account in public_text,
        "question_preserved": question in public_text,
        "typed_unfinished_status_visible": (
            "requested record work remains unfinished" in public_text
        ),
        "predecessors_preserved": conversation.open_material == previous.open_material,
        "fulfillment": data["material_coverage"]["execution"]["requests"][0]["fulfillment"],
        "saved_exact_reply": saved.brain_chat[-1]["response"]["elements"] == data["elements"],
    }
    evidence(
        identity,
        model,
        data,
        saved,
        expected,
        observed,
        scenario="mixed",
        protection_status="blocked",
        notes="The fabricated reviewer intentionally accepts all supplied text; "
        "the operation claim must nevertheless be rendered from the typed unfinished result. "
        "An independent sourced account and purposeful question must survive.",
    )
    assert observed == expected
