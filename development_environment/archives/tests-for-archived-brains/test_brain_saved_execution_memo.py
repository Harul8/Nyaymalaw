"""Replay memo reuse is confined to exact owned saved evidence.

Public fixtures declare semantic decisions. These tests exercise checked replay,
prefix/version binding and detached memo results; inherited v2 receipt routing
remains a separate prerequisite.
"""

from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import turn as owner
from nm.brain.conversation import IncompleteConversation, Message
from tests.test_brain_material import send
from tests.test_brain_post_application_coverage_public import (
    TARGET,
    saved_revision,
)
from tests.test_brain_saved_record_support import altered, current, open_seed


def checked(matter, row, memo, *, older=()):
    return owner._validate_execution_replay(
        matter, row, prior_conversation=older, _memo=memo)


def supported(matter, context, memo, *, historical=False):
    conversation, disputes, details = context
    helper = owner._saved_historical_support if historical else owner._saved_record_support
    return helper(matter, conversation, disputes=disputes, details=details, _memo=memo)


def observe_body(monkeypatch):
    body, calls = owner._validate_execution_replay_body, []

    def observed(matter, row, *, prior_conversation, _memo):
        result = body(matter, row, prior_conversation=prior_conversation, _memo=_memo)
        calls.append((row["turn_id"], result))
        return result

    monkeypatch.setattr(owner, "_validate_execution_replay_body", observed)
    return calls


def prefix(matter, size):
    rows = matter.brain_chat[:size]
    if rows:
        version = rows[-1]["response"]["material_coverage"]["execution"]["resulting_version"]
    else:
        version = matter.brain_chat[0]["response"]["material_coverage"]["execution"][
            "expected_version"]
    return replace(matter, brain_chat=deepcopy(rows), version=version)


def test_one_memo_reuses_full_checked_rows_across_admission_current_and_history_helpers(
        client, wired, monkeypatch):
    model, _, _, _, saved = saved_revision(client, wired, monkeypatch, "corrects")
    context, before = current(wired, saved), deepcopy(saved)
    model_count = len(model.seen)
    memo = owner._SavedExecutionMemo(saved)
    calls = observe_body(monkeypatch)
    for _ in range(2):
        for row in saved.brain_chat:
            assert checked(saved, row, memo) is None
        admissions, locators = owner._saved_record_admissions(saved, context[0], _memo=memo)
        assert TARGET in admissions["detail_review"] and TARGET in locators
        assert supported(saved, context, memo)["detail_review"]
        assert set(supported(saved, context, memo, historical=True)["detail_review"]) == {TARGET}
    assert calls == [(row["turn_id"], True) for row in saved.brain_chat]
    assert saved == before and len(model.seen) == model_count
    assert wired.store.load(saved.id) == saved


def test_exact_committed_prefixes_share_validation_without_sharing_catalogue_scope(
        client, wired, monkeypatch):
    _, _, _, _, saved = saved_revision(client, wired, monkeypatch, "corrects")
    memo, first = owner._SavedExecutionMemo(saved), prefix(saved, 1)
    calls = observe_body(monkeypatch)
    first_context = current(wired, first)
    assert set(supported(first, first_context, memo)["detail_review"]) == {TARGET}
    assert supported(first, first_context, memo, historical=True) == {
        "dispute_review": {}, "detail_review": {}}
    context = current(wired, saved)
    assert TARGET not in supported(saved, context, memo)["detail_review"]
    assert set(supported(saved, context, memo, historical=True)["detail_review"]) == {TARGET}
    assert set(supported(first, first_context, memo)["detail_review"]) == {TARGET}
    assert calls == [(row["turn_id"], True) for row in saved.brain_chat]
    empty = prefix(saved, 0)
    empty_context = current(wired, empty)
    assert supported(empty, empty_context, memo) == {"dispute_review": {}, "detail_review": {}}


def test_equal_detached_matter_and_row_are_reusable_owned_evidence(client, wired, monkeypatch):
    _, saved, _ = open_seed(client, wired, monkeypatch)
    memo, calls = owner._SavedExecutionMemo(saved), observe_body(monkeypatch)
    assert checked(saved, saved.brain_chat[0], memo) is None
    detached = deepcopy(saved)
    assert checked(detached, deepcopy(detached.brain_chat[0]), memo) is None
    assert calls == [(saved.brain_chat[0]["turn_id"], True)]


def test_later_committed_metadata_version_cannot_use_last_receipt_as_full_snapshot_version(
        client, wired, monkeypatch):
    _, _, _, _, saved = saved_revision(client, wired, monkeypatch, "corrects")
    advanced = replace(saved, title=saved.title + " amended", version=saved.version + 1)
    wired.store.commit(advanced, expected_version=saved.version)
    committed = wired.store.load(saved.id)
    memo, calls = owner._SavedExecutionMemo(committed), observe_body(monkeypatch)
    row = committed.brain_chat[-1]
    last_result_version = row["response"]["material_coverage"]["execution"]["resulting_version"]
    assert last_result_version < committed.version
    assert checked(committed, row, memo) is None
    stale = replace(committed, version=last_result_version)
    with pytest.raises(IncompleteConversation):
        checked(stale, stale.brain_chat[-1], memo)
    assert calls == [(saved_row["turn_id"], True) for saved_row in saved.brain_chat]
    assert wired.store.load(saved.id) == committed


@pytest.mark.parametrize("fault", (
    "matter_owner", "advocate_owner", "title", "metadata", "version", "original_words",
    "latest_words", "saved_response", "reordered_prefix", "wrong_prefix_version", "older_added",
))
def test_changed_owner_prefix_metadata_or_older_words_reject_before_a_cached_success(
        client, wired, monkeypatch, fault):
    _, _, _, _, saved = saved_revision(client, wired, monkeypatch, "corrects")
    memo, calls = owner._SavedExecutionMemo(saved), observe_body(monkeypatch)
    assert checked(saved, saved.brain_chat[0], memo) is None
    changed, older = altered(saved), ()
    if fault == "matter_owner":
        for row in changed.brain_chat:
            row["matter_id"] = "foreign-matter"
        changed = replace(changed, id="foreign-matter")
    elif fault == "advocate_owner":
        for row in changed.brain_chat:
            row["advocate_id"] = "foreign-advocate"
        changed = replace(changed, advocate_id="foreign-advocate")
    elif fault == "title":
        changed = replace(changed, title=changed.title + " revised")
    elif fault == "metadata":
        changed = replace(changed, intake_opening_offer={"changed_owned_metadata": True})
    elif fault == "version":
        changed = replace(changed, version=changed.version + 1)
    elif fault == "original_words":
        changed.brain_chat[0]["message"] += " Additional original account."
    elif fault == "latest_words":
        changed.brain_chat[-1]["message"] += " Additional current account."
    elif fault == "saved_response":
        changed.brain_chat[0]["response"]["material_coverage"]["state"] = "partial"
    elif fault == "reordered_prefix":
        changed = replace(changed, brain_chat=tuple(reversed(changed.brain_chat)))
    elif fault == "wrong_prefix_version":
        changed = replace(prefix(changed, 1), version=changed.version + 10)
    else:
        older = (Message("earlier-account", "advocate", "An additional older account."),)
    before = deepcopy(changed)
    with pytest.raises(IncompleteConversation):
        checked(changed, changed.brain_chat[0], memo, older=older)
    assert calls == [(saved.brain_chat[0]["turn_id"], True)]
    assert changed == before


def test_memo_deep_snapshot_does_not_follow_mutation_of_the_original_matter_object(
        client, wired, monkeypatch):
    _, saved, _ = open_seed(client, wired, monkeypatch)
    memo, calls = owner._SavedExecutionMemo(saved), observe_body(monkeypatch)
    assert checked(saved, saved.brain_chat[0], memo) is None
    original = deepcopy(saved)
    saved.brain_chat[0]["message"] += " An in-memory changed account."
    with pytest.raises(IncompleteConversation):
        checked(saved, saved.brain_chat[0], memo)
    assert calls == [(original.brain_chat[0]["turn_id"], True)]
    assert wired.store.load(original.id) == original


@pytest.mark.parametrize("difference", ("words", "turn", "speaker", "omitted"))
def test_older_message_tuple_is_bound_before_body_validation(
        client, wired, monkeypatch, difference):
    _, saved, _ = open_seed(client, wired, monkeypatch)
    older = (Message("earlier-account", "advocate", "The original older account."),)
    memo = owner._SavedExecutionMemo(saved, prior_conversation=older)
    calls = observe_body(monkeypatch)
    if difference == "words":
        changed = (replace(older[0], text="A different older account."),)
    elif difference == "turn":
        changed = (replace(older[0], turn_id="foreign-turn"),)
    elif difference == "speaker":
        changed = (replace(older[0], role="nm"),)
    else:
        changed = ()
    with pytest.raises(IncompleteConversation):
        checked(saved, saved.brain_chat[0], memo, older=changed)
    assert calls == []


def test_mutating_returned_admission_or_history_catalogues_does_not_poison_the_memo(
        client, wired, monkeypatch):
    _, _, _, _, saved = saved_revision(client, wired, monkeypatch, "corrects")
    context = current(wired, saved)
    memo, calls = owner._SavedExecutionMemo(saved), observe_body(monkeypatch)
    admissions, locators = owner._saved_record_admissions(saved, context[0], _memo=memo)
    history = supported(saved, context, memo, historical=True)
    active = supported(saved, context, memo)
    before = deepcopy((admissions, locators, history, active, saved))
    admissions["detail_review"][TARGET]["review"]["reason"] = "Mutated output"
    locators[TARGET]["admission_turn_id"] = "foreign-output-turn"
    history["detail_review"][TARGET]["selector"]["proof_digest"] = "foreign-output-digest"
    next(iter(active["detail_review"].values()))["source_references"].clear()
    fresh_admissions, fresh_locators = owner._saved_record_admissions(saved, context[0], _memo=memo)
    fresh = (fresh_admissions, fresh_locators, supported(saved, context, memo, historical=True),
             supported(saved, context, memo), saved)
    assert fresh == before
    assert calls == [(row["turn_id"], True) for row in saved.brain_chat]


def test_failed_body_is_not_cached_and_keeps_an_independent_completed_peer(
        client, wired, monkeypatch):
    _, _, _, _, saved = saved_revision(client, wired, monkeypatch, "corrects")
    memo, body, calls = owner._SavedExecutionMemo(saved), owner._validate_execution_replay_body, []

    def failing_once(matter, row, *, prior_conversation, _memo):
        calls.append(row["turn_id"])
        if row["turn_id"] == saved.brain_chat[-1]["turn_id"] and calls.count(row["turn_id"]) == 1:
            raise IncompleteConversation("Injected owned replay failure")
        return body(matter, row, prior_conversation=prior_conversation, _memo=_memo)

    monkeypatch.setattr(owner, "_validate_execution_replay_body", failing_once)
    assert checked(saved, saved.brain_chat[0], memo) is None
    with pytest.raises(IncompleteConversation):
        checked(saved, saved.brain_chat[-1], memo)
    assert checked(saved, saved.brain_chat[0], memo) is None
    assert checked(saved, saved.brain_chat[-1], memo) is None
    assert checked(saved, saved.brain_chat[-1], memo) is None
    assert calls == [saved.brain_chat[0]["turn_id"], *[saved.brain_chat[-1]["turn_id"]] * 2]


def test_in_progress_cycle_is_rejected_and_does_not_leave_cached_or_pending_success(
        client, wired, monkeypatch):
    _, saved, _ = open_seed(client, wired, monkeypatch)
    memo, body, calls = owner._SavedExecutionMemo(saved), owner._validate_execution_replay_body, []
    row = saved.brain_chat[0]

    def cycling_once(matter, row, *, prior_conversation, _memo):
        calls.append(row["turn_id"])
        if len(calls) == 1:
            return checked(matter, row, _memo, older=prior_conversation)
        return body(matter, row, prior_conversation=prior_conversation, _memo=_memo)

    monkeypatch.setattr(owner, "_validate_execution_replay_body", cycling_once)
    with pytest.raises(IncompleteConversation):
        checked(saved, row, memo)
    assert checked(saved, row, memo) is None
    assert checked(saved, row, memo) is None
    assert calls == [row["turn_id"], row["turn_id"]]


@pytest.mark.parametrize("legacy", ("no_execution", "snapshotless_receipt"))
def test_legacy_compatible_body_completion_is_not_certified_or_memoized(
        client, wired, monkeypatch, legacy):
    _, saved, _ = open_seed(client, wired, monkeypatch)
    changed = altered(saved)
    response = changed.brain_chat[0]["response"]
    coverage = response["material_coverage"]
    if legacy == "no_execution":
        coverage.pop("execution")
    else:
        execution = coverage["execution"]
        for field in ("display", "mutation_authority_contract", "mutation_authorities",
                      "coverage_application", "coverage_application_contract"):
            execution.pop(field, None)
        response["continuation"].pop("record_snapshot")
    memo, calls = owner._SavedExecutionMemo(changed), observe_body(monkeypatch)
    for _ in range(2):
        assert checked(changed, changed.brain_chat[0], memo) is None
    assert calls == [(changed.brain_chat[0]["turn_id"], False)] * 2


@pytest.mark.parametrize("completion", (1, "partial", {"checked": True}))
def test_truthy_internal_return_is_not_full_true_completion(client, wired, monkeypatch, completion):
    _, saved, _ = open_seed(client, wired, monkeypatch)
    memo, calls = owner._SavedExecutionMemo(saved), []

    def incomplete(matter, row, *, prior_conversation, _memo):
        calls.append(row["turn_id"])
        return completion

    monkeypatch.setattr(owner, "_validate_execution_replay_body", incomplete)
    for _ in range(2):
        assert checked(saved, saved.brain_chat[0], memo) is None
    assert calls == [saved.brain_chat[0]["turn_id"]] * 2


@pytest.mark.parametrize("fault", ("owner", "unknown_contract"))
def test_actual_owner_or_contract_failures_cannot_become_cached_success(
        client, wired, monkeypatch, fault):
    _, saved, _ = open_seed(client, wired, monkeypatch)
    changed = altered(saved)
    execution = changed.brain_chat[0]["response"]["material_coverage"]["execution"]
    if fault == "owner":
        execution["owner"]["matter_id"] = "foreign-owner"
    else:
        execution["coverage_application_contract"] = "unsupported_contract"
    memo = owner._SavedExecutionMemo(changed)
    body, calls = owner._validate_execution_replay_body, []

    def observed(matter, row, *, prior_conversation, _memo):
        calls.append(row["turn_id"])
        return body(matter, row, prior_conversation=prior_conversation, _memo=_memo)

    monkeypatch.setattr(owner, "_validate_execution_replay_body", observed)
    failure = owner.BrainRefused if fault == "owner" else IncompleteConversation
    for _ in range(2):
        with pytest.raises(failure):
            checked(changed, changed.brain_chat[0], memo)
    assert calls == ([] if fault == "owner" else [changed.brain_chat[0]["turn_id"]] * 2)


def test_existing_v1_public_replay_preserves_exact_saved_receipt_and_zero_model_calls(
        client, wired, monkeypatch):
    model, opened, latest, original, saved = saved_revision(client, wired, monkeypatch, "corrects")
    calls = len(model.seen)
    reply = send(client, latest, "application-revision", opened=opened)
    assert reply.status_code == 200, reply.text
    result = reply.json()
    assert result["replayed"] and result["metrics"]["llm_calls"] == 0
    assert result["material_coverage"]["execution"] == original["material_coverage"]["execution"]
    assert result["continuation"] == original["continuation"]
    assert result["elements"] == original["elements"]
    assert wired.store.load(saved.id) == saved and len(model.seen) == calls
