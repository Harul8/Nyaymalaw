"""Paired curated golden composites and diverse fabricated raw responses."""

import pytest

from tests.brain_golden_pressure_fixture import (
    GoldenModel,
    ThreadGoldenModel,
    composite,
    evidence,
    release,
)

pytestmark = pytest.mark.class_a

VARIANTS = (
    "good",
    "average_partial",
    "malformed_sibling",
    "persistent_bad",
    "hallucinated",
    "foreign_source",
    "empty_extract",
    "source_conflict",
)


@pytest.mark.parametrize("index", range(8))
@pytest.mark.parametrize("variant", VARIANTS)
def test_golden_composite_public_pressure(client, wired, monkeypatch, index, variant):
    dossier = composite(index)
    model = GoldenModel(dossier, variant)
    identity = f"GOLDEN-{index + 1:02}-{variant.upper().replace('_', '-')}"
    data, saved, conversation = release(client, wired, monkeypatch, model, identity)
    statements = [row["statement"] for row in conversation.open_material]
    expected_statements = [row["statement"] for row in dossier.details]
    if variant in ("persistent_bad", "foreign_source", "hallucinated"):
        expected_statements = expected_statements[:-1]
    conditional = data["metrics"]["recovery"]
    owner_reads = [row["input"] for row in model.seen
                   if row["operation"] == "reconsider_account_sources"]
    omission_reads = [row["input"] for row in model.seen
                      if row["operation"] == "extract_legal_details"
                      and "recovery_scope" in row["input"]]
    expected_missing = ({row["source_id"] for row in dossier.details}
                        if variant == "empty_extract" else {model.selected_gap})
    observed = {
        "saved_statements": statements,
        "saved_exact_reply_equals_released": saved.brain_chat[-1]["response"]["elements"]
        == data["elements"],
        "all_sources_owned": all(
            row["quoted"] in dossier.message and row["source_turn_id"] == identity
            for row in conversation.open_material
        ),
        "unverified_hallucination_absent": all(
            row["statement"] != model.hallucinated_statement for row in conversation.open_material
        ),
        "recovery_bounded": conditional["dispatched_calls"] <= conditional["reserved_calls"] <= 8,
        "conditional_calls": conditional["dispatched_calls"],
        "targeted_reads": sum(
            row["operation"] == "extract_legal_details" and "recovery_scope" in row["input"]
            for row in model.seen
        ),
        "source_owner_calls": sum(
            row["operation"] == "reconsider_account_sources" for row in model.seen
        ),
        "source_owner_candidate_free_and_complete": all(
            set(payload) == {"earlier_conversation", "latest_message_spans", "source_ids"}
            and payload["earlier_conversation"] == []
            and "".join(span["text"] for span in payload["latest_message_spans"]) == dossier.message
            and payload["source_ids"] == [model.selected_gap] for payload in owner_reads),
        "omission_read_exact_owned_gap_and_complete_input": all(
            set(payload["recovery_scope"]["missing_source_ids"]) == expected_missing
            and "".join(span["text"] for span in payload["latest_message_spans"]) == dossier.message
            for payload in omission_reads),
    }
    expected_calls = {
        "good": 0,
        "average_partial": 2,
        "malformed_sibling": 1,
        "persistent_bad": 3,
        "hallucinated": 2,
        "foreign_source": 3,
        "empty_extract": 2,
        "source_conflict": 3,
    }
    expected = {
        "saved_statements": expected_statements,
        "saved_exact_reply_equals_released": True,
        "all_sources_owned": True,
        "unverified_hallucination_absent": True,
        "recovery_bounded": True,
        "conditional_calls": expected_calls[variant],
        "targeted_reads": 1
        if variant
        in ("average_partial", "persistent_bad", "hallucinated", "foreign_source", "empty_extract")
        else 0,
        "source_owner_calls": 1 if variant == "source_conflict" else 0,
        "source_owner_candidate_free_and_complete": True,
        "omission_read_exact_owned_gap_and_complete_input": True,
    }
    evidence(
        identity,
        model,
        data,
        saved,
        expected,
        observed,
        scenario=(
            "legitimate"
            if variant == "good"
            else "faulty"
            if variant in ("hallucinated", "foreign_source")
            else "mixed"
        ),
        protection_status=(
            "admitted"
            if variant == "good"
            else "partial_preserved"
            if variant in ("persistent_bad", "foreign_source", "hallucinated")
            else "recovered"
        ),
        claim_scope="semantic_dependency" if variant == "hallucinated" else "mechanical",
        notes="The literal fabricated outputs are logged before strict schema validation.",
    )


@pytest.mark.parametrize("index", range(8))
def test_golden_thread_assignment_preserves_owned_issues_and_valid_neighbours(
    client, wired, monkeypatch, index
):
    dossier = composite(index)
    model = ThreadGoldenModel(dossier)
    identity = f"GOLDEN-{index + 1:02}-OWNED-THREADS"
    data, saved, conversation = release(client, wired, monkeypatch, model, identity)
    expected_disputes = [spec[2] for spec in model.issue_specs if spec[4]]
    actual_assignments = {
        row["statement"]: row["dispute_ids"] for row in conversation.open_material
    }
    owned_labels = {row["id"]: row["label"] for row in conversation.open_disputes}
    observed = {
        "assignment_labels": {
            row["statement"]: [owned_labels[identity] for identity in row["dispute_ids"]]
            for row in conversation.open_material
        },
        "saved_dispute_labels": [row["label"] for row in conversation.open_disputes],
        "saved_statements": [row["statement"] for row in conversation.open_material],
        "actual_assignments": actual_assignments,
        "foreign_assignment_retained": any(
            "FOREIGN-UNOWNED-DISPUTE" in row["dispute_ids"] for row in conversation.open_material
        ),
        "conditional_calls": data["metrics"]["recovery"]["dispatched_calls"],
        "rejected_invented_disputes": len(
            data["material_coverage"]["execution"]["rejected_proposals"]["disputes"]
        ),
        "saved_exact_reply_equals_released": saved.brain_chat[-1]["response"]["elements"]
        == data["elements"],
    }
    expected = {
        "assignment_labels": model.assignment_labels,
        "saved_dispute_labels": expected_disputes,
        "saved_statements": [row["statement"] for row in dossier.details],
        "actual_assignments": model.selected_assignment_ids,
        "foreign_assignment_retained": False,
        "conditional_calls": 1,
        "rejected_invented_disputes": sum(not spec[4] for spec in model.issue_specs),
        "saved_exact_reply_equals_released": True,
    }
    evidence(
        identity,
        model,
        data,
        saved,
        expected,
        observed,
        scenario="mixed",
        protection_status="recovered",
        notes=(
            "The fixture declares each independent issue and exact source/thread relation; "
            "foreign assignment rejection is mechanical. Invented disputes receive explicitly "
            "scripted independent rejections, proving rejection wiring rather than detection."
        ),
    )
