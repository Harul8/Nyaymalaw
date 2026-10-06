"""Keep source-purpose admission gates while removing classifier-led feedback.

Judge outputs are explicitly scripted. These tests qualify ownership, feedback,
recovery and persistence mechanics, not a live model's semantic accuracy.
"""

from copy import deepcopy

import pytest

from nm.brain import record_review as record
from nm.shared.model_port import SchemaViolation, require_schema
from tests.brain_reader_fixture import (
    fixture_coverage,
    fixture_disposition,
    fixture_representation_choices,
)
from tests.test_brain_semantic_recovery import (
    FIRST,
    MESSAGE,
    SECOND,
    RecoveryModel,
    detail,
    release,
)
from tests.test_brain_source_support_coverage import (
    check_review,
    ranges,
    review_row,
    review_schema,
    source,
    treatment,
)
from tests.test_brain_source_support_verifiers import (
    RawJudge,
    candidate_id,
    coverage,
    disposition,
    proposal,
    review,
    source_catalogue,
    verdict,
)


@pytest.mark.parametrize("role", ["examination_material", "work_instruction"])
@pytest.mark.parametrize("supports", [False, True])
def test_conflicting_source_purpose_still_blocks_accept_and_keeps_typed_diagnostic(
        role, supports):
    original = source()
    row = review_row(portions=ranges((0, len(original["quoted"]))), supports=supports)
    treatments = {"L1": treatment(original, role=role)}
    before = deepcopy((row, treatments))
    issues = []

    assert not check_review(row, original, role=role, issues=issues)
    assert issues
    assert record.source_role_disagreements(
        row, {"L1"}, treatments, schema=review_schema({"L1": original})) == ({
            "source_id": "L1", "content_role": role, "supplies_account_content": True,
        },)
    assert (row, treatments) == before


@pytest.mark.parametrize("role", [
    "reported_matter_account", "reported_party_position", "mixed",
])
def test_exact_checked_account_support_remains_admissible_without_reclassification(role):
    original = source()
    row = review_row(portions=ranges((0, len(original["quoted"]))))
    issues = []
    assert check_review(row, original, role=role, issues=issues)
    assert issues == []
    assert record.source_role_disagreements(
        row, {"L1"}, {"L1": treatment(original, role=role)},
        schema=review_schema({"L1": original})) == ()


@pytest.mark.parametrize("portions,supplies", [([], True), (ranges((0, 11)), False)])
def test_neutral_feedback_does_not_weaken_exact_original_support_consistency(portions, supplies):
    with pytest.raises(SchemaViolation, match="exact support portions"):
        check_review(review_row(portions=portions, supplies=supplies), source())


@pytest.mark.parametrize("kind", ["material", "dispute"])
def test_real_verifier_correction_is_source_bound_without_inherited_classifier_label(kind):
    latest = "The witness remained uncertain and did not identify the sender."
    role = "examination_material"
    references, treatments = source_catalogue(latest, roles={"L1": role})
    candidate = proposal(kind, latest)
    output = {"verdicts": [verdict(kind, references["L1"])],
              "coverage": coverage(references, state="partial", dispositions=[
                  disposition("L1", references["L1"])])}
    before = deepcopy((candidate, treatments, output))
    model = RawJudge([output, output])

    retained, _, disagreements, _ = review(
        kind, model, latest, candidates=(candidate,), treatments=treatments)

    assert retained == ()
    assert len(model.calls) == 2
    assert any(row["source_id"] == "L1" and row["content_role"] == role
               and row["supplies_account_content"] is True for row in disagreements)
    correction = model.calls[1]["payload"]
    assert correction["source_treatments"] == references
    assert correction["latest_message_spans"] == model.calls[0]["payload"][
        "latest_message_spans"]
    assert [row["candidate_id"] for row in correction["candidates"]] == [candidate_id(kind)]
    feedback = correction["validation_issue"]
    assert candidate_id(kind) in feedback and "source L1" in feedback
    assert role not in feedback
    assert "independent content_role=" not in feedback
    assert (candidate, treatments, output) == before
    for call in model.calls:
        require_schema(call["output"], call["schema"])


class SourcePurposeRecoveryModel(RecoveryModel):
    """Script detail coverage directly in its current owned domain.

    The opening has its own independent review and may not stand in for the
    two requested detail records. Both original reports are declared account.
    """

    def coverage_judgment(self, operation, payload, reviewed):
        choices = fixture_representation_choices(payload, reviewed)
        dispositions = []
        state = "complete"
        for identity, reference in payload["source_treatments"].items():
            assert reference["quoted"] in (FIRST, SECOND)
            if operation == "verify_disputes":
                dispositions.append(fixture_disposition(payload, identity, status="outside_scope"))
                continue
            selected = choices.get(identity, {"record_ids": [], "candidate_ids": []})
            if selected["record_ids"] or selected["candidate_ids"]:
                dispositions.append(fixture_disposition(
                    payload, identity, status="represented", **selected))
            else:
                state = "partial"
                dispositions.append(fixture_disposition(payload, identity, status="missing"))
        return fixture_coverage(
            payload, state=state,
            source_decisions={identity: "account" for identity in payload["source_treatments"]},
            dispositions=dispositions,
            reason="The two original reports require their independently checked detail records.")


@pytest.mark.parametrize("changed", [False, True])
def test_legitimate_source_disagreement_reaches_candidate_free_owner_and_checked_save(
        client, wired, monkeypatch, changed):
    model = SourcePurposeRecoveryModel(
        candidates=[detail(FIRST), detail(SECOND)], roles={"L2": "examination_material"},
        reconsidered={"L2": "reported_matter_account"} if changed else {})
    data, saved, conversation = release(
        client, wired, monkeypatch, model, "neutral-purpose-" + str(changed).lower())
    owners = [row for row in model.seen if row["operation"] == "reconsider_account_sources"]

    assert len(owners) == 1
    assert owners[0]["tier"] == "judge"
    owner_input = owners[0]["input"]
    assert set(owner_input) == {"earlier_conversation", "latest_message_spans",
                               "original_source_catalogue", "source_ids",
                               "source_selection_contract"}
    assert owner_input["source_ids"] == ["L2"]
    assert owner_input["original_source_catalogue"] == {
        "L2": {"turn_id": "neutral-purpose-" + str(changed).lower(),
               "role": "advocate", "quoted": SECOND},
    }
    assert "".join(row["text"] for row in owner_input["latest_message_spans"]) == MESSAGE
    expected = [FIRST, SECOND] if changed else [FIRST]
    assert [row["statement"] for row in conversation.open_material] == expected
    assert [row["quoted"] for row in conversation.open_material] == expected
    turn = saved.brain_chat[-1]["response"]
    assert turn["material_coverage"]["source_treatments"]["L2"]["content_role"] == (
        "reported_matter_account" if changed else "examination_material")
    events = data["metrics"]["recovery"]["events"]
    assert sum(row["phase"] == "source_reconsideration:source_owner" and "call" in row
               for row in events) == 1
    assert sum(row["phase"] == "source_reconsideration:detail_review" and "call" in row
               for row in events) == int(changed)
    assert data["metrics"]["recovery"]["reserved_calls"] <= 8
