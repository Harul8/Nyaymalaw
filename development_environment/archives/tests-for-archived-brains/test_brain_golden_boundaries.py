"""Golden composite passages at saved delivery and exact reference boundaries.

Fabricated independent meanings qualify mechanical wiring. They never measure
real-model accuracy or establish the source rubric as verified legal authority.
"""

import json
import os
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from nm.brain.continuation import _validate_unit
from nm.brain.history import IncompleteConversation
from nm.brain.material import addressed_sources
from nm.shared.model_port import SchemaViolation
from tests.brain_golden_pressure_fixture import (
    GoldenModel,
    composite,
    evidence,
    release,
    wire,
)
from tests.brain_pressure_support import record_case

pytestmark = pytest.mark.class_a


def reference_unit(dossier):
    """An explicitly attributed factual block, with literal fixture-owned IDs."""
    proposal = next(row for row in dossier.details)
    source_id = proposal["source_id"]
    return {
        "request_index": 0,
        "blocks": [
            {
                "id": "attributed-account",
                "kind": "account",
                "text": proposal["statement"],
                "span_ids": [source_id],
                "record_ids": [],
                "legal_source_ids": [],
                "inline_citations": [],
                "uncertainty": "reported",
            }
        ],
        "questions": [],
        "next_work": [],
        "sufficiency": {"status": "partial", "block_id": "attributed-account"},
        "work": {"existing_id": "", "create": True},
        "progress_updates": [],
        "record_outcome": {
            "status": "none",
            "block_id": "",
            "effect_ids": [],
            "current_record_ids": [],
            "reason": "",
        },
    }


@pytest.mark.parametrize(
    "fault,expected_error",
    [
        ("foreign_record", "SchemaViolation"),
        ("foreign_legal_source", "SchemaViolation"),
        ("assessment_without_law", "SchemaViolation"),
        ("lost_legal_use_owner", "IncompleteConversation"),
        ("correct_attributed_neighbour", None),
    ],
)
def test_golden_owned_reference_boundary(fault, expected_error):
    dossier = composite(4)
    proposal = reference_unit(dossier)
    records = {}
    legal = {}
    expected_issue = ""
    if fault == "foreign_record":
        proposal["blocks"][0]["record_ids"] = ["another-matter:material:1"]
        expected_issue = "record_ids"
    elif fault == "foreign_legal_source":
        proposal["blocks"][0]["legal_source_ids"] = ["invented-judgment:paragraph:999"]
        proposal["blocks"][0]["inline_citations"] = [
            {
                "text": proposal["blocks"][0]["text"],
                "legal_source_id": "invented-judgment:paragraph:999",
            }
        ]
        expected_issue = "legal_source_ids"
    elif fault == "assessment_without_law":
        proposal["blocks"][0].update(
            kind="assessment", text="Every requested remedy follows automatically."
        )
        expected_issue = "actual supporting checked passage"
    elif fault == "lost_legal_use_owner":
        proposal["blocks"][0]["legal_source_ids"] = ["checked-passage"]
        proposal["blocks"][0]["inline_citations"] = [
            {
                "text": proposal["blocks"][0]["text"],
                "legal_source_id": "checked-passage",
            }
        ]
        legal = {
            "checked-passage": {
                "id": "checked-passage",
                "use_record_id": "missing-checked-use-owner",
            }
        }
        expected_issue = "lost its use owner"
    payload, _, _ = addressed_sources((), dossier.message)
    spans = {
        row["id"]: {**row, "role": "advocate", "turn_id": "latest"}
        for row in payload["latest_message_spans"]
    }
    raw = deepcopy(proposal)
    failure = None
    issue = ""
    try:
        _validate_unit(proposal, (0,), spans, records, legal)
    except (SchemaViolation, IncompleteConversation) as exc:
        # _ContentFailure is the owner's typed SchemaViolation subtype.
        failure = (
            "IncompleteConversation"
            if isinstance(exc, IncompleteConversation)
            else "SchemaViolation"
        )
        issue = str(exc)
    expected = {
        "failure": expected_error,
        "precise_issue": bool(expected_issue),
        "legal_authority_accepted": False,
        "production_model_calls": 0,
    }
    observed = {
        "failure": failure,
        "precise_issue": bool(expected_issue and expected_issue in issue),
        "legal_authority_accepted": failure is None
        and any(row["legal_source_ids"] for row in proposal["blocks"]),
        "production_model_calls": 0,
    }
    report = record_case(
        "golden-boundary-reference-" + fault,
        boundary="nm.brain.continuation._validate_unit",
        user_passage=dossier.message,
        model_outputs=[{"fabricated_continuation_unit": raw}],
        expected=expected,
        observed=observed,
        calls=[
            {
                "operation": "_validate_unit",
                "input": {"spans": spans, "record_catalogue": records, "legal_sources": legal},
                "failure": failure,
                "issue": issue,
            }
        ],
        scenario="legitimate" if expected_error is None else "faulty",
        claim_scope="mechanical",
        protection_status="admitted" if expected_error is None else "blocked",
        notes=(
            "Direct exact-reference boundary only: no save or legal truth claim. "
            "Golden scenarios: " + ", ".join(dossier.golden_ids) + ". "
            "The legitimate neighbour is attributed factual engagement, not legal advice."
        ),
    )
    report["source_qualification"] = {
        "golden_case_ids": dossier.golden_ids,
        "source_entries": dossier.source_entries,
        "source_file_sha256": dossier.source_entries[0]["source_file_sha256"],
    }
    if directory := os.environ.get("NM_PRESSURE_EVIDENCE_DIR"):
        (Path(directory) / (report["case_id"] + ".json")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
    assert observed == expected


def requirement(kind="change", *, targets=(), operation="new", condition=None):
    return {
        "kind": kind,
        "target_ids": list(targets),
        "operation": "none" if kind == "review" else operation,
        "success_condition": condition or "Preserve the complete attributed supplied account.",
    }


def owned_outcome(status, *, empty=False, linked=False, metadata=None):
    """Literal case-owned outcomes; effects supply identity, never semantics."""

    def hook(operation, payload, schema, data, model):
        original = payload.get("original_input", payload)
        if operation == "interpret_conversation" and linked:
            for item in data["items"]:
                item.update(relation="continues", matter_scope="current")
            data["opening"] = {"ready": False, "party_name": "", "subject": "", "summary": ""}
        elif operation in ("extract_disputes", "extract_legal_details"):
            if empty:
                data = {"new_items": [], "changes": []}
            elif original.get("earlier_conversation") and "new_items" in data:
                for row in data["new_items"]:
                    row["prior_source_ids"] = []
        elif operation == "continue_conversation":
            requests = {row["request_index"]: row for row in payload["work_items"]}
            for unit in data["units"]:
                owner = unit["blocks"][0]["id"]
                target_ids = requests[unit["request_index"]]["record_requirement"]["target_ids"]
                unit["record_outcome"] = {
                    "status": status,
                    "block_id": "" if status == "none" else owner,
                    "effect_ids": [
                        identity
                        for identity, effect in payload["record_effect_catalogue"].items()
                        if effect["performed"]
                    ]
                    if status == "performed"
                    else [],
                    "current_record_ids": list(target_ids)
                    if status in ("already_current", "review_no_change")
                    else [],
                    "reason": "The independent fixture declares the sourced record result."
                    if status != "none"
                    else "",
                }
                unit["sufficiency"] = {
                    "status": "partial" if status == "unresolved" else "complete",
                    "block_id": owner,
                }
                unit["progress_updates"] = []
        elif operation == "verify_continuation":
            rows = data.get("accepted_units", data.get("verdicts", []))
            for row in rows:
                row["record_check"] = {
                    "outcome": {
                        "none": "not_requested",
                        "performed": "fulfilled",
                        "already_current": "fulfilled",
                        "review_no_change": "no_change_justified",
                        "unresolved": "unfinished",
                    }[status],
                    "reason": "The scripted owner declares this typed result and scope.",
                }
            if metadata and model.operation_counts[operation] == 1:
                for row in rows:
                    row["retained_block_ids"] = (
                        [] if metadata == "empty" else [row["block_checks"][0]["block_id"]]
                    )
                    row["retained_reason"] = (
                        "  "
                        if metadata == "empty"
                        else "Keep a partial unit despite declaring complete acceptance."
                    )
            if "verdicts" in data:
                data = {
                    "accepted_units": [
                        {
                            key: value
                            for key, value in row.items()
                            if key != "verdict"
                            and (
                                metadata is not None
                                or key not in ("retained_block_ids", "retained_reason")
                            )
                        }
                        for row in rows
                    ],
                    "rejected_units": [],
                }
        return data

    return hook


def seed(client, wired, monkeypatch, dossier, identity):
    return release(client, wired, monkeypatch, GoldenModel(dossier), identity)


@pytest.mark.parametrize("mode", ["record_acknowledgement", "substantive"])
def test_golden_false_prose_vs_owned_pending_outcome(client, wired, monkeypatch, mode):
    dossier = composite(5)
    baseline, _, previous = seed(client, wired, monkeypatch, dossier, "golden-pending-seed")
    target = previous.open_material[0]["id"]
    lie = "I corrected the selected date, saved the revision and completed every requested task."
    requested = requirement(targets=(target,), operation="corrects")
    model = GoldenModel(
        dossier,
        response_mode=mode,
        requirement=requested,
        reply=lie,
        hook=owned_outcome("unresolved", empty=True, linked=True),
    )
    data, saved, conversation = release(
        client, wired, monkeypatch, model, "golden-pending-" + mode, opened=baseline
    )
    receipt = data["material_coverage"]["execution"]
    text = json.dumps(data["elements"])
    expected = {
        "changes": [],
        "fulfillment": "unfinished",
        "false_prose_released": False,
        "unchanged_record": True,
        "saved_turns": 2,
        "acknowledgement_delivery": "code_only",
    }
    observed = {
        "changes": receipt["record_changes"],
        "fulfillment": receipt["requests"][0]["fulfillment"],
        "false_prose_released": lie in text,
        "unchanged_record": conversation.open_material == previous.open_material,
        "saved_turns": len(saved.brain_chat),
        "acknowledgement_delivery": receipt["requests"][0].get("acknowledgement_delivery"),
    }
    evidence(
        "golden-boundary-pending-" + mode,
        model,
        data,
        saved,
        expected,
        observed,
        claim_scope="mechanical",
        protection_status="blocked",
        notes=(
            "Every declared operation completion block is code-rendered before review; "
            "a forced wrong semantic ACCEPT cannot override the typed pending result. "
            "This checks declared outcome nodes, not arbitrary mislabeled free prose."
        ),
    )
    assert observed == expected


def test_golden_code_acknowledgement_uses_actual_saved_effects(client, wired, monkeypatch):
    dossier = composite(0)
    lie = "I deleted every original assertion and discarded the full account."
    model = GoldenModel(
        dossier,
        response_mode="record_acknowledgement",
        requirement=requirement(),
        reply=lie,
        hook=owned_outcome("performed"),
    )
    data, saved, conversation = release(client, wired, monkeypatch, model, "golden-code-effects")
    receipt = data["material_coverage"]["execution"]
    expected = {
        "false_prose_released": False,
        "source_statements_saved": True,
        "fulfillment": "fulfilled",
        "persistence": "committed",
        "saved_exact_reply": True,
        "conditional_calls": 0,
    }
    observed = {
        "false_prose_released": lie in json.dumps(data["elements"]),
        "source_statements_saved": {row["statement"] for row in conversation.open_material}
        == {row["statement"] for row in dossier.details},
        "fulfillment": receipt["requests"][0]["fulfillment"],
        "persistence": receipt["persistence"],
        "saved_exact_reply": saved.brain_chat[-1]["response"]["elements"] == data["elements"],
        "conditional_calls": data["metrics"]["recovery"]["dispatched_calls"],
    }
    evidence(
        "golden-boundary-code-effects",
        model,
        data,
        saved,
        expected,
        observed,
        scenario="legitimate",
        protection_status="admitted",
    )
    assert observed == expected


@pytest.mark.parametrize("status", ["already_current", "review_no_change"])
def test_golden_current_or_no_change_does_not_require_a_new_write(
    client, wired, monkeypatch, status
):
    dossier = composite(4)
    baseline, _, previous = seed(client, wired, monkeypatch, dossier, "golden-current-seed")
    targets = [row["id"] for row in previous.open_material]
    requested = requirement(
        "review" if status == "review_no_change" else "change",
        targets=targets,
        operation="corrects",
    )
    model = GoldenModel(
        dossier,
        response_mode="record_acknowledgement",
        requirement=requested,
        hook=owned_outcome(status, empty=True, linked=True),
    )
    data, saved, conversation = release(
        client, wired, monkeypatch, model, "golden-current-" + status, opened=baseline
    )
    receipt = data["material_coverage"]["execution"]
    expected = {
        "changes": [],
        "unchanged_record": True,
        "blocked": False,
        "fulfillment": "no_change_justified" if status == "review_no_change" else "fulfilled",
        "conditional_calls": 0,
        "saved_turns": 2,
    }
    observed = {
        "changes": receipt["record_changes"],
        "unchanged_record": conversation.open_material == previous.open_material,
        "blocked": data["blocked"],
        "fulfillment": receipt["requests"][0]["fulfillment"],
        "conditional_calls": data["metrics"]["recovery"]["dispatched_calls"],
        "saved_turns": len(saved.brain_chat),
    }
    evidence(
        "golden-boundary-current-" + status,
        model,
        data,
        saved,
        expected,
        observed,
        scenario="legitimate",
        protection_status="admitted",
        notes="The original full account is already represented in reopened saved records; "
        "empty fresh proposals are not evidence of an unread stage.",
    )
    assert observed == expected


@pytest.mark.parametrize("metadata,review_calls", [("empty", 1), ("populated", 2)])
def test_golden_acceptance_metadata_has_precise_false_positive_boundary(
    client, wired, monkeypatch, metadata, review_calls
):
    dossier = composite(1)
    model = GoldenModel(dossier, hook=owned_outcome("none", metadata=metadata))
    data, saved, conversation = release(
        client, wired, monkeypatch, model, "golden-metadata-" + metadata
    )
    expected = {
        "blocked": False,
        "review_calls": review_calls,
        "source_statements_saved": True,
        "reply_released": True,
    }
    observed = {
        "blocked": data["blocked"],
        "review_calls": model.operation_counts["verify_continuation"],
        "source_statements_saved": {row["statement"] for row in conversation.open_material}
        == {row["statement"] for row in dossier.details},
        "reply_released": (
            f'Your message includes: “{dossier.source_quotes[dossier.details[0]["source_id"]]}”'
            in " ".join(row["text"] for row in data["elements"])
        ),
    }
    evidence(
        "golden-boundary-metadata-" + metadata,
        model,
        data,
        saved,
        expected,
        observed,
        scenario="legitimate" if metadata == "empty" else "mixed",
        protection_status="admitted" if metadata == "empty" else "recovered",
        notes="Only declared inapplicable empty metadata may normalize; "
        "populated contradictory retention instructions require explicit repair.",
    )
    assert observed == expected


def test_golden_performed_cannot_use_an_absent_effect(client, wired, monkeypatch):
    dossier = composite(6)
    baseline, _, previous = seed(client, wired, monkeypatch, dossier, "golden-absent-seed")
    target = previous.open_material[0]["id"]
    lie = "I performed the requested revision and saved the replacement."
    model = GoldenModel(
        dossier,
        requirement=requirement(targets=(target,), operation="corrects"),
        reply=lie,
        hook=owned_outcome("performed", empty=True, linked=True),
    )
    data, saved, conversation = release(
        client, wired, monkeypatch, model, "golden-performed-without-effect", opened=baseline
    )
    receipt = data["material_coverage"]["execution"]
    expected = {
        "blocked": True,
        "changes": [],
        "false_prose_released": False,
        "fulfillment": "unfinished",
        "writer_calls": 2,
        "unchanged_record": True,
    }
    observed = {
        "blocked": data["blocked"],
        "changes": receipt["record_changes"],
        "false_prose_released": lie in json.dumps(data["elements"]),
        "fulfillment": receipt["requests"][0]["fulfillment"],
        "writer_calls": model.operation_counts["continue_conversation"],
        "unchanged_record": conversation.open_material == previous.open_material,
    }
    evidence(
        "golden-boundary-performed-without-effect",
        model,
        data,
        saved,
        expected,
        observed,
        protection_status="blocked",
        notes="A positive scripted semantic judgment cannot invent an operation receipt.",
    )
    assert observed == expected


def test_golden_another_owned_target_cannot_complete_the_selected_target(
    client, wired, monkeypatch
):
    dossier = composite(4)
    baseline, _, previous = seed(client, wired, monkeypatch, dossier, "golden-target-seed")
    requested_target, other_target = [row["id"] for row in previous.open_material[:2]]
    other_statement = previous.open_material[1]["statement"]
    standard = owned_outcome("performed", empty=True, linked=True)

    def wrong_target(operation, payload, schema, data, model):
        data = standard(operation, payload, schema, data, model)
        if operation == "extract_legal_details":
            changed = {
                **deepcopy(dossier.details[1]),
                "prior_source_ids": [],
                "relation": "corrects",
                "related_material_ids": [other_target],
            }
            return {"new_items": [], "changes": [changed]}
        if operation == "verify_material_grounding":
            original = payload.get("original_input", payload)
            candidates = {row["candidate_id"]: row for row in original["candidates"]}
            for row in data["verdicts"]:
                row["target_checks"] = [
                    {
                        "target_id": target,
                        "identity_relation": "same_underlying_account",
                        "account_preserved": True,
                        "required_peer_ids": [],
                        "reason": "This formulation belongs only to its selected original account.",
                    }
                    for target in candidates[row["candidate_id"]]["related_material_ids"]
                ]
        return data

    lie = "The requested first record has now been revised."
    model = GoldenModel(
        dossier,
        requirement=requirement(targets=(requested_target,), operation="corrects"),
        mutation_scopes=[{
            "authority_kind": "account_contribution",
            "authority_source_ids": [dossier.details[0]["source_id"]],
            "target_scope": "exact",
            "target_ids": [requested_target],
            "permitted_relations": ["corrects"],
        }],
        reply=lie,
        hook=wrong_target,
    )
    for attributes in model.semantic_attributes.values():
        attributes["matter_scope"] = "current"
    data, saved, conversation = release(
        client, wired, monkeypatch, model, "golden-another-owned-target", opened=baseline
    )
    receipt = data["material_coverage"]["execution"]
    expected = {
        "blocked": True,
        "false_prose_released": False,
        "fulfillment": "unfinished",
        "requested_target_retained": True,
        "other_owned_target_retained": True,
        "other_owned_target_revised": False,
        "original_meaning_preserved": True,
    }
    observed = {
        "blocked": data["blocked"],
        "false_prose_released": lie in json.dumps(data["elements"]),
        "fulfillment": receipt["requests"][0]["fulfillment"],
        "requested_target_retained": requested_target
        in {row["id"] for row in conversation.open_material},
        "other_owned_target_retained": other_target
        in {row["id"] for row in conversation.open_material},
        "other_owned_target_revised": any(
            other_target in row["target_record_ids"]
            for row in receipt["effects"]["details"]["operations"]
        ),
        "original_meaning_preserved": other_statement
        in {row["statement"] for row in conversation.open_material},
    }
    evidence(
        "golden-boundary-another-owned-target",
        model,
        data,
        saved,
        expected,
        observed,
        protection_status="blocked",
        notes="Both records are genuinely owned. The scope decision binds the first target "
        "and its independent original source before extraction. A reviewer cannot expand "
        "that permission to the second target; both predecessors remain intact.",
    )
    assert observed == expected


def test_golden_failed_atomic_save_cannot_release_prepared_success(client, wired, monkeypatch):
    dossier = composite(2)
    baseline, _, previous = seed(client, wired, monkeypatch, dossier, "golden-save-seed")
    model = GoldenModel(
        dossier,
        response_mode="record_acknowledgement",
        requirement=requirement(),
        hook=owned_outcome("performed", linked=True),
    )
    for attributes in model.semantic_attributes.values():
        attributes["matter_scope"] = "current"
    wire(wired, monkeypatch, model)

    def failure(*args, **kwargs):
        raise OSError("Injected failure before atomic persistence")

    monkeypatch.setattr(wired.store, "commit", failure)
    response = client.post(
        "/api/turn",
        json={
            "message": dossier.message,
            "turn_id": "golden-save-failure",
            "matter_id": baseline["matter_id"],
            "chat_id": baseline["chat_id"],
        },
    )
    data = response.json()
    saved = wired.store.load(baseline["matter_id"])
    from nm.brain import turn as boundary

    current, _, _ = boundary._current_records(wired.store, saved)
    expected = {
        "http": 503,
        "matter_reply_released": False,
        "saved_turns": 1,
        "unchanged_record": True,
        "persistence": "unconfirmed",
    }
    observed = {
        "http": response.status_code,
        "matter_reply_released": "elements" in data,
        "saved_turns": len(saved.brain_chat),
        "unchanged_record": current.open_material == previous.open_material,
        "persistence": data.get("detail", {}).get("committed"),
    }
    evidence(
        "golden-boundary-save-failure",
        model,
        data,
        saved,
        expected,
        observed,
        protection_status="blocked",
        notes="The semantic checks ran; the durable commit did not.",
    )
    assert observed == expected


def dated_dossier(*, corrected):
    """Two authored turns, copied only from existing GS-15/17/18 input words."""
    date_source = composite(5)
    custody_source = composite(6)
    chosen_date = "sorry, 15-4-2024" if corrected else "it is dated 15-4-1984"
    selected_lines = [
        line
        for line in date_source.message.splitlines()[1:]
        if chosen_date in line or line.startswith("GS-17 ")
    ]
    selected_lines.extend(
        line
        for line in custody_source.message.splitlines()[1:]
        if "the original is with the seller's brother" in line
    )
    message = "\n".join([date_source.message.splitlines()[0], *selected_lines])
    _, quotes, _ = addressed_sources((), message)
    roles = {}
    details = []
    for identity, words in quotes.items():
        owners = [
            (owner, key)
            for owner in (date_source, custody_source)
            for key, exact in owner.source_quotes.items()
            if exact == words
        ]
        if identity == "L1":
            roles[identity] = "work_instruction"
            continue
        assert len(owners) == 1, (words, owners)
        owner, key = owners[0]
        roles[identity] = owner.source_roles[key]
        for row in owner.details:
            if row["source_id"] == key:
                details.append({**deepcopy(row), "source_id": identity})
    entries = {
        row["case_id"]: row
        for row in [*date_source.source_entries, *custody_source.source_entries]
        if row["case_id"] in ("GS-15", "GS-17", "GS-18")
    }
    return replace(
        date_source,
        id="GS15-DATE-" + ("2024" if corrected else "1984"),
        golden_ids=("GS-15", "GS-17", "GS-18"),
        message=message,
        details=details,
        source_roles=roles,
        source_quotes=quotes,
        source_entries=list(entries.values()),
    )


@pytest.mark.parametrize(
    "wrong_target", [False, True], ids=["correct_owned_target", "wrong_owned_target"]
)
def test_golden_actual_two_turn_date_correction(client, wired, monkeypatch, wrong_target):
    original = dated_dossier(corrected=False)
    corrected = dated_dossier(corrected=True)
    baseline, _, previous = seed(client, wired, monkeypatch, original, "golden-date-origin")
    date_target = previous.open_material[0]["id"]
    custody_target = previous.open_material[1]["id"]
    old_statement = original.details[0]["statement"]
    new_statement = corrected.details[0]["statement"]
    for identity, words in original.source_quotes.items():
        if words not in corrected.source_quotes.values():
            corrected.source_quotes["earlier-" + identity] = words
            corrected.source_roles["earlier-" + identity] = original.source_roles[identity]
    selected_target = custody_target if wrong_target else date_target
    standard = owned_outcome("performed", linked=True)

    def date_correction(operation, payload, schema, data, model):
        data = standard(operation, payload, schema, data, model)
        if operation == "extract_legal_details":
            original_input = payload.get("original_input", payload)
            prior = [
                span["id"]
                for message in original_input["earlier_conversation"]
                if message["role"] == "advocate"
                for span in message["source_spans"]
                if original.source_quotes[original.details[0]["source_id"]] == span["text"].strip()
            ]
            assert len(prior) == 1
            row = {
                **deepcopy(corrected.details[0]),
                "prior_source_ids": prior,
                "relation": "corrects",
                "related_material_ids": [selected_target],
            }
            return {"new_items": [], "changes": [row]}
        if operation == "verify_material_grounding":
            original_input = payload.get("original_input", payload)
            candidates = {row["candidate_id"]: row for row in original_input["candidates"]}
            for row in data["verdicts"]:
                row["target_checks"] = [
                    {
                        "target_id": target,
                        "identity_relation": "same_underlying_account",
                        "account_preserved": True,
                        "required_peer_ids": [],
                        "reason": (
                            "Intentionally wrong identity ACCEPT of custody versus date accounts."
                            if wrong_target
                            else "The new original date statement corrects this same dated account."
                        ),
                    }
                    for target in candidates[row["candidate_id"]]["related_material_ids"]
                ]
        return data

    model = GoldenModel(
        corrected,
        response_mode="record_acknowledgement",
        requirement=requirement(
            targets=(date_target,),
            operation="corrects",
            condition="The original dated account now records 15-4-2024.",
        ),
        mutation_scopes=[{
            "authority_kind": "account_contribution",
            "authority_source_ids": [corrected.details[0]["source_id"]],
            "target_scope": "exact",
            "target_ids": [date_target],
            "permitted_relations": ["corrects"],
        }],
        hook=date_correction,
    )
    for attributes in model.semantic_attributes.values():
        attributes["matter_scope"] = "current"
    identity = "golden-two-turn-date-" + ("wrong" if wrong_target else "correct")
    data, saved, conversation = release(
        client, wired, monkeypatch, model, identity, opened=baseline
    )
    receipt = data["material_coverage"]["execution"]
    active = {row["id"]: row for row in conversation.open_material}
    expected = {
        "old_date_target_active": wrong_target,
        "old_date_meaning_active": wrong_target,
        "new_date_meaning_saved": not wrong_target,
        "fulfillment": "unfinished" if wrong_target else "fulfilled",
        "blocked": wrong_target,
        "original_custody_target_active": True,
        "actual_selected_target": [] if wrong_target else [date_target],
        "saved_turns": 2,
    }
    observed = {
        "old_date_target_active": date_target in active,
        "old_date_meaning_active": old_statement in {row["statement"] for row in active.values()},
        "new_date_meaning_saved": new_statement in {row["statement"] for row in active.values()},
        "fulfillment": receipt["requests"][0]["fulfillment"],
        "blocked": data["blocked"],
        "original_custody_target_active": custody_target in active,
        "actual_selected_target": [
            target for operation in receipt["effects"]["details"]["operations"]
            for target in operation["target_record_ids"]
        ],
        "saved_turns": len(saved.brain_chat),
    }
    evidence(
        "golden-boundary-two-turn-date-" + ("wrong" if wrong_target else "correct"),
        model,
        data,
        saved,
        expected,
        observed,
        scenario="faulty" if wrong_target else "legitimate",
        protection_status="blocked" if wrong_target else "admitted",
        claim_scope="mechanical",
        notes=(
            "The independently authored scope permits only the dated predecessor. "
            "A deliberately wrong identity ACCEPT cannot admit retirement of custody. "
            "No revision is saved; both originals remain active and work is pending."
            if wrong_target
            else "The first saved account contains only the exact 1984 statement; "
            "the later exact 2024 correction retires its owned predecessor and preserves custody. "
            "GS-17 remains examination material and supplies no invented legal authority."
        ),
    )
    assert observed == expected


def test_golden_wholly_unread_required_reader_saves_no_new_turn(client, wired, monkeypatch):
    dossier = composite(7)
    baseline, _, previous = seed(client, wired, monkeypatch, dossier, "golden-unread-seed")
    standard = owned_outcome("unresolved", linked=True)

    def unread(operation, payload, schema, data, model):
        data = standard(operation, payload, schema, data, model)
        if operation == "extract_legal_details":
            if "repairs" in schema.get("properties", {}):
                return {
                    "repairs": {
                        identity: {"proposals": [{"foreign": "Still unread"}]}
                        for identity in schema["properties"]["repairs"]["properties"]
                    }
                }
            return {"new_items": [{"foreign": "No admissible required-reader unit"}], "changes": []}
        return data

    model = GoldenModel(dossier, requirement=requirement("review"), hook=unread)
    wire(wired, monkeypatch, model)
    response = client.post(
        "/api/turn",
        json={
            "message": dossier.message,
            "turn_id": "golden-wholly-unread",
            "matter_id": baseline["matter_id"],
            "chat_id": baseline["chat_id"],
        },
    )
    data = response.json()
    saved = wired.store.load(baseline["matter_id"])
    from nm.brain import turn as boundary

    current, _, _ = boundary._current_records(wired.store, saved)
    expected = {
        "http": 503,
        "new_turn_saved": False,
        "saved_turns": 1,
        "unchanged_record": True,
        "matter_reply_released": False,
        "reader_calls": 2,
    }
    observed = {
        "http": response.status_code,
        "new_turn_saved": any(row["turn_id"] == "golden-wholly-unread" for row in saved.brain_chat),
        "saved_turns": len(saved.brain_chat),
        "unchanged_record": current.open_material == previous.open_material,
        "matter_reply_released": "elements" in data,
        "reader_calls": model.operation_counts["extract_legal_details"],
    }
    evidence(
        "golden-boundary-wholly-unread",
        model,
        data,
        saved,
        expected,
        observed,
        protection_status="blocked",
        notes="Every required reader unit remains unread after "
        "the one keyed correction. Original input is not silently saved as examined empty output.",
    )
    assert observed == expected


def test_golden_lost_ack_replay_has_no_calls_or_duplicate_effects(client, wired, monkeypatch):
    dossier = composite(7)
    model = GoldenModel(
        dossier,
        response_mode="record_acknowledgement",
        requirement=requirement(),
        hook=owned_outcome("performed"),
    )
    commit = wired.store.commit

    def lost_ack(matter, *, expected_version):
        commit(matter, expected_version=expected_version)
        raise OSError("Injected lost acknowledgement after atomic persistence")

    monkeypatch.setattr(wired.store, "commit", lost_ack)
    first, _, _ = release(client, wired, monkeypatch, model, "golden-lost-ack")
    before = len(model.seen)
    # An idempotent replay repeats the exact original offer. Adding the newly
    # returned matter ID changes that offer and correctly triggers identity refusal.
    repeated, saved, conversation = release(client, wired, monkeypatch, model, "golden-lost-ack")
    expected = {
        "first_recovered": True,
        "replay_calls": 0,
        "additional_calls": 0,
        "same_reply": True,
        "same_receipt": True,
        "saved_turns": 1,
        "unique_saved_source_statements": True,
    }
    observed = {
        "first_recovered": first["replayed"],
        "replay_calls": repeated["metrics"]["llm_calls"],
        "additional_calls": len(model.seen) - before,
        "same_reply": first["elements"] == repeated["elements"],
        "same_receipt": first["material_coverage"]["execution"]
        == repeated["material_coverage"]["execution"],
        "saved_turns": len(saved.brain_chat),
        "unique_saved_source_statements": len(conversation.open_material) == len(dossier.details)
        and {row["statement"] for row in conversation.open_material}
        == {row["statement"] for row in dossier.details},
    }
    evidence(
        "golden-boundary-lost-ack",
        model,
        repeated,
        saved,
        expected,
        observed,
        scenario="mixed",
        protection_status="recovered",
        notes="Committed receipt lookup releases the saved reply; replay makes no model calls.",
    )
    assert observed == expected
