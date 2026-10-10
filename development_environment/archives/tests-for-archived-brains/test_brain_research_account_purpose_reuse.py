"""Only used immutable account-source purposes govern factual-application reuse."""

from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.record_review import SOURCE_TREATMENT_CONTRACT
from nm.brain.requirements_state import research_record
from tests.test_brain_research_semantic_reuse import _covered_read
from tests.test_brain_research_state import (
    REVISION,
    account_finding,
    append,
    matter,
    subject,
)

REPORT = "We agreed that the stated condition applies."


def _treatment(
    turn_id, quote=REPORT, role="reported_matter_account", reason="Original reported account."
):
    return {
        "turn_id": turn_id,
        "role": "advocate",
        "quoted": quote,
        "content_role": role,
        "reason": reason,
    }


def _edit_last(file, *, message=None, catalogue=None):
    turns = deepcopy(file.brain_chat)
    if message is not None:
        turns[-1]["message"] = message
    if catalogue is not None:
        turns[-1]["response"]["material_coverage"] = {
            "source_treatment_contract": SOURCE_TREATMENT_CONTRACT,
            "source_treatments": deepcopy(catalogue),
        }
    return replace(file, brain_chat=turns)


def _history(*, source_at_read=False, baseline=True, role="reported_matter_account", peer=False):
    file = matter()
    selected = subject(file)
    source_turn = "legal-read" if source_at_read else "account-source"
    original = {"old-span": _treatment(source_turn, role=role)}
    if not source_at_read:
        file = _edit_last(
            append(file, [], identity=source_turn),
            message=REPORT,
            catalogue=original if baseline else None,
        )
    factual = account_finding(source_turn, REPORT)
    factual["use_verification"]["application_premises"][0]["preserved_condition"] = ""
    saved_read = _covered_read(selected, rows=[factual])
    reads = [saved_read]
    subjects = [selected]
    if peer:
        other = subject(file, identity="peer", question="A separate general legal enquiry")
        subjects.append(other)
        reads.append(_covered_read(other))
    file = append(file, reads, identity="legal-read")
    if source_at_read:
        file = _edit_last(file, message=REPORT, catalogue=original if baseline else None)
    return file, tuple(subjects), original, saved_read


def _project(file, subjects, current):
    return research_record(
        file,
        subjects=subjects,
        material_by_subject={row["id"]: [] for row in subjects},
        corpus_revision=REVISION,
        source_treatments=current,
    )


@pytest.mark.parametrize("source_at_read", [False, True])
def test_same_exact_source_purpose_permits_reuse_from_prior_or_current_saved_classifier(
    source_at_read,
):
    file, subjects, original, saved_read = _history(source_at_read=source_at_read)
    untouched = deepcopy(file.brain_chat)
    current = {
        "remapped-address": {**original["old-span"], "reason": "A changed explanatory reason."}
    }
    projected = _project(file, subjects, current)
    selected = subjects[0]["id"]
    assert projected["reuse_allowed"][selected] is True
    assert projected["coverage_by_subject"][selected]["account_purpose_freshness"] == "current"
    assert projected["by_subject"][selected] == saved_read["rows"]
    assert file.brain_chat == untouched


@pytest.mark.parametrize(
    "changed_role",
    ["examination_material", "work_instruction", "reported_party_position", "uncertain"],
)
def test_changed_used_source_purpose_invalidates_cache_at_fixed_question_records_and_corpus(
    changed_role,
):
    file, subjects, original, saved_read = _history(peer=True)
    untouched = deepcopy(file.brain_chat)
    current = {"current-address": {**original["old-span"], "content_role": changed_role}}
    projected = _project(file, subjects, current)
    selected, peer = (row["id"] for row in subjects)
    assert projected["state"] == "ok"
    assert projected["reuse_allowed"][selected] is False
    assert projected["coverage_by_subject"][selected]["account_purpose_freshness"] == "changed"
    assert projected["by_subject"][selected] == saved_read["rows"]
    assert projected["fingerprints"][selected] == saved_read["fingerprint"]
    assert projected["reuse_allowed"][peer] is True and projected["by_subject"][peer]
    assert file.brain_chat == untouched


@pytest.mark.parametrize("unknown", [None, {}, "wrong_quote", "conflicting_roles", "unknown_role"])
def test_unknown_current_purpose_cannot_assert_mismatch_or_complete_reuse_and_keeps_checked_history(
    unknown,
):
    file, subjects, original, saved_read = _history()
    if unknown == "wrong_quote":
        current = {"new": {**original["old-span"], "quoted": "Different source words."}}
    elif unknown == "conflicting_roles":
        current = {
            "first": original["old-span"],
            "second": {**original["old-span"], "content_role": "reported_party_position"},
        }
    elif unknown == "unknown_role":
        current = {"new": {**original["old-span"], "content_role": "unsupported-new-purpose"}}
    else:
        current = unknown
    projected = _project(file, subjects, current)
    selected = subjects[0]["id"]
    assert projected["state"] == "ok" and projected["by_subject"][selected] == saved_read["rows"]
    assert projected["reuse_allowed"][selected] is False
    assert projected["coverage_by_subject"][selected]["account_purpose_freshness"] == "unknown"


def test_missing_original_classification_does_not_invent_a_matching_historical_source_purpose():
    file, subjects, original, saved_read = _history(baseline=False)
    projected = _project(file, subjects, {"current": original["old-span"]})
    selected = subjects[0]["id"]
    assert projected["reuse_allowed"][selected] is False
    assert projected["coverage_by_subject"][selected]["account_purpose_freshness"] == "unknown"
    assert projected["by_subject"][selected] == saved_read["rows"]


def test_unrelated_new_turn_source_changes_and_reason_edits_do_not_hash_or_invalidate_the_chat():
    file, subjects, original, saved_read = _history()
    file = append(file, [], identity="unrelated-new-turn")
    current = {
        "remapped": {
            **original["old-span"],
            "reason": "Same original purpose, different explanation.",
        },
        "new-unrelated-span": _treatment(
            "unrelated-new-turn", quote="An attributed request.", role="work_instruction"
        ),
        "other-unrelated-span": _treatment(
            "foreign-unreferenced-turn",
            quote="Another unrelated instruction.",
            role="examination_material",
        ),
    }
    untouched = deepcopy(file.brain_chat)
    projected = _project(file, subjects, current)
    selected = subjects[0]["id"]
    assert projected["reuse_allowed"][selected] is True
    assert projected["fingerprints"][selected] == saved_read["fingerprint"]
    assert projected["coverage_by_subject"][selected]["account_purpose_freshness"] == "current"
    assert file.brain_chat == untouched


def test_equal_duplicate_source_purposes_do_not_create_a_false_conflict():
    file, subjects, original, _ = _history()
    same = original["old-span"]
    projected = _project(
        file, subjects, {"first": same, "second": {**same, "reason": "Same purpose."}}
    )
    assert projected["reuse_allowed"][subjects[0]["id"]] is True


def test_general_conditional_law_with_no_used_account_refs_needs_no_purpose_catalogue():
    file = matter()
    selected = subject(file)
    saved = append(file, [_covered_read(selected)])
    projected = _project(saved, (selected,), None)
    assert projected["reuse_allowed"][selected["id"]] is True
    assert (
        projected["coverage_by_subject"][selected["id"]]["account_purpose_freshness"]
        == "not_required"
    )


def test_known_non_substantive_original_and_current_purpose_cannot_validate_a_factual_application():
    file, subjects, original, saved_read = _history(role="work_instruction")
    projected = _project(file, subjects, original)
    selected = subjects[0]["id"]
    assert projected["reuse_allowed"][selected] is False
    assert projected["coverage_by_subject"][selected]["account_purpose_freshness"] == "incompatible"
    assert projected["by_subject"][selected] == saved_read["rows"]
