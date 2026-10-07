"""Minted v2 receipts survive public save and exact-prefix replay.

The fixture explicitly authors source purposes and coverage selections at the
fresh receipt handoff. This tests durable receipt integration, not historical
representation choices by the material producer or a real model's meaning.
Saved rows and seals are never rewritten to create the inherited chain.
"""

import json
from collections import Counter
from copy import deepcopy

import pytest

from nm.brain import record_review
from nm.brain import turn as owner
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage, require_schema
from tests.brain_reader_fixture import fresh_review_reply
from tests.test_brain_material import material, mutation_scope, send
from tests.test_brain_material_purpose import PurposeModel, item, public_record, routed
from tests.test_brain_post_application_coverage_public import (
    CHANGED,
    ORIGINAL,
    TARGET,
    saved_revision,
)
from tests.test_brain_saved_execution_memo import observe_body, prefix
from tests.test_brain_saved_record_support import current
from tests.test_brain_source_support_verifiers import coverage, disposition, verdict

V1 = "owned_coverage_application_v1"
V2 = "owned_coverage_application_v2"
REVISION = "application-revision:material:1"
REPAIR_ID = "inherited-original-repair"
REPAIRED = f"{REPAIR_ID}:material:1"
REPAIR = "Restore the original custody wording in the saved description."
READINGS = (
    ("inherited-first-reading", "Check the saved custody description against my earlier account."),
    ("inherited-next-reading", "Review that custody description again against the original words."),
)


def review_plan(message, *, target=REVISION):
    """Declare no-change meaning before any extraction or receipt exists."""
    result = routed(
        message,
        source_purposes={message: "non_account"},
        record_disposition="review_no_change",
        items=[item(
            message,
            ORIGINAL,
            purposes=("interpretation_review",),
            record_requirement={
                "kind": "review",
                "target_ids": [target],
                "operation": "none",
                "success_condition": "The saved description retains the reported custody account.",
            },
        )],
    )
    # The current producer is given a separately authored active representation.
    # Historical selection is exercised only at the fresh receipt handoff below.
    result["_coverage_links"] = {
        words: {"record_ids": [target], "candidate_ids": []}
        for words in (ORIGINAL, CHANGED)
    }
    return result


def receipt_handoff(wired, monkeypatch, matter_id, *, original_records=(TARGET,)):
    capture = owner._capture_coverage_application
    apply = owner._apply_coverage_application
    fresh_contexts = {}

    def authored_capture(execution, **kwargs):
        before = wired.store.load(matter_id)
        conversation, disputes, details = current(wired, before)
        memo = owner._SavedExecutionMemo(before)
        active = owner._saved_record_support(
            before, conversation, disputes=disputes, details=details, _memo=memo)
        history = owner._saved_historical_support(
            before, conversation, disputes=disputes, details=details, _memo=memo)
        source_references = {
            identity: {key: source[key] for key in ("turn_id", "role", "quoted")}
            for identity, source in kwargs["sources"].items()
        }
        purposes = {
            identity: "account" if source["quoted"] in (ORIGINAL, CHANGED) else "non_account"
            for identity, source in source_references.items()
        }
        selected = {ORIGINAL: original_records, CHANGED: (REVISION,)}
        detail_raw = coverage(
            source_references,
            purposes=purposes,
            dispositions=[
                disposition(
                    identity,
                    source,
                    status="represented" if purposes[identity] == "account" else "non_account",
                    record_ids=selected.get(source["quoted"], ()),
                )
                for identity, source in source_references.items()
            ],
        )
        support = {
            **active["detail_review"],
            **{identity: entry["record_support"]
               for identity, entry in history["detail_review"].items()},
        }
        # The distinct-dispute stage is expressly out of scope for these
        # custody accounts; instructions remain independently non-account.
        dispute_raw = coverage(
            source_references,
            purposes=purposes,
            dispositions=[
                disposition(
                    identity,
                    source,
                    status="outside_scope" if purposes[identity] == "account" else "non_account",
                )
                for identity, source in source_references.items()
            ],
        )
        for stage, raw in (("detail_review", detail_raw), ("dispute_review", dispute_raw)):
            assessment = record_review.checked_coverage(
                raw,
                tuple(source_references),
                source_references=source_references,
                record_ids=tuple(support) if stage == "detail_review" else (),
                record_support=support if stage == "detail_review" else None,
            )
            assessment.update(
                contract=record_review.ACCOUNT_COVERAGE_CONTRACT,
                review_scope=deepcopy(execution["review_scope"]),
                missing_sources=[],
            )
            execution["stages"][stage]["account_coverage"] = assessment
        fresh_contexts[execution["owner"]["turn_id"]] = before, memo
        return capture(
            execution, **kwargs, inherited_history=history, prefix_matter=before, _memo=memo)

    def fresh_apply(execution, receipt, **kwargs):
        if receipt["contract"] == V2 and "prefix_matter" not in kwargs:
            # Saved replay already supplies its own exact prefix and shared memo.
            before, memo = fresh_contexts[execution["owner"]["turn_id"]]
            kwargs.update(prefix_matter=before, _memo=memo)
        return apply(execution, receipt, **kwargs)

    monkeypatch.setattr(owner, "_capture_coverage_application", authored_capture)
    monkeypatch.setattr(owner, "_apply_coverage_application", fresh_apply)


def saved_chain(client, wired, monkeypatch, readings):
    model, opened, _, _, initial = saved_revision(client, wired, monkeypatch, "corrects")
    original_rows = deepcopy(initial.brain_chat)
    receipt_handoff(wired, monkeypatch, initial.id)
    model.plans = iter(review_plan(message) for _, message in READINGS[:readings])
    replies = []
    for identity, message in READINGS[:readings]:
        response = send(client, message, identity, opened=opened)
        assert response.status_code == 200, response.text
        replies.append(response.json())
    saved = wired.store.load(initial.id)
    assert saved.brain_chat[:2] == original_rows
    return model, opened, initial, saved, replies


class OriginalRepairModel(PurposeModel):
    """Author an earlier-account repair and its independent positive review."""

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        if prompt.operation != "verify_material_grounding" or not payload["candidates"]:
            return super().structured(prompt, schema, tier, max_tokens=max_tokens)
        self.seen.append((prompt.operation, deepcopy(payload)))
        references = payload["source_treatments"]
        (candidate,) = payload["candidates"]
        assert candidate["related_material_ids"] == [REVISION]
        sources = {identity: source for identity, source in references.items()
                   if source["quoted"] in (ORIGINAL, CHANGED, REPAIR)}
        row = verdict("material", references["L1"])
        row["account_check"]["source_ids"] = list(sources)
        row["account_check"]["source_checks"] = [{
            "source_id": identity,
            "supplies_account_content": source["quoted"] != REPAIR,
            "supports_proposal": source["quoted"] == ORIGINAL,
            "support_spans": [] if source["quoted"] == REPAIR else [
                {"start": 0, "end": len(source["quoted"])}],
            "reason": ("The earlier original account supplies the restored content; "
                       "the later instruction supplies repair authority only."),
        } for identity, source in sources.items()]
        row["target_checks"] = [{
            "target_id": REVISION,
            "identity_relation": "same_underlying_account",
            "account_preserved": True,
            "required_peer_ids": [],
            "reason": "The declared repair retains the original attributed custody account.",
        }]
        purposes = {identity: "non_account" if source["quoted"] == REPAIR else "account"
                    for identity, source in references.items()}
        data = fresh_review_reply(payload, {
            "verdicts": [row],
            "coverage": coverage(
                references,
                purposes=purposes,
                dispositions=[disposition(
                    identity, source,
                    status="non_account" if purposes[identity] == "non_account" else "represented",
                    record_ids=() if purposes[identity] == "non_account" else (REVISION,),
                ) for identity, source in references.items()],
            ),
        })
        require_schema(data, schema)
        return ModelResult(
            text=None, data=data, tier=tier, provider="offline-raw",
            model="fabricated-original-repair", usage=Usage(0, 0, 0), latency_ms=0,
            completion=Completion.COMPLETE)


def saved_local_retirement(client, wired, monkeypatch):
    _, opened, _, _, initial = saved_revision(client, wired, monkeypatch, "corrects")
    restored = material(
        "circumstance", ORIGINAL, REPAIR, relation="corrects", scope="current", placement="matter",
        references=(
            {"turn_id": "application-original", "role": "advocate", "quoted": ORIGINAL},
            {"turn_id": "application-revision", "role": "advocate", "quoted": CHANGED},
        ),
        related_material_ids=(REVISION,),
    )
    repair = routed(
        REPAIR, candidates=[restored], source_purposes={REPAIR: "non_account"},
        record_disposition="performed", items=[{
            **item(
                REPAIR, ORIGINAL, purposes=("interpretation_review",),
                record_requirement={
                    "kind": "change", "target_ids": [REVISION], "operation": "corrects",
                    "success_condition": (
                        "The saved description restores the original custody words."),
                },
            ),
            "mutation_scopes": [mutation_scope(
                REVISION, authority_kind="interpretation_review")],
        }],
    )
    reading = review_plan(READINGS[1][1], target=REPAIRED)
    # This fixture explicitly declares that the correction instruction is not
    # substantive account, even when it appears as an earlier source later.
    model = OriginalRepairModel([repair, reading])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    receipt_handoff(wired, monkeypatch, initial.id, original_records=(TARGET, REVISION))
    responses = []
    for identity, message in ((REPAIR_ID, REPAIR), READINGS[1]):
        response = send(client, message, identity, opened=opened)
        assert response.status_code == 200, response.text
        responses.append(response.json())
    saved = wired.store.load(initial.id)
    assert saved.brain_chat[:2] == initial.brain_chat
    return model, opened, initial, saved, responses


@pytest.mark.parametrize("readings", (1, 2))
def test_minted_v2_no_write_receipts_save_and_public_replay_without_models(
    client, wired, monkeypatch, readings
):
    model, opened, initial, saved, replies = saved_chain(client, wired, monkeypatch, readings)
    assert len(saved.brain_chat) == 2 + readings
    assert [row["message"] for row in saved.brain_chat] == [
        ORIGINAL, CHANGED, *(message for _, message in READINGS[:readings])]
    assert current(wired, saved)[1:] == current(wired, initial)[1:]
    for row, reply in zip(saved.brain_chat[2:], replies, strict=True):
        assert reply["metrics"]["llm_calls"] == 8
        execution = reply["material_coverage"]["execution"]
        receipt = execution["coverage_application"]
        assert receipt["contract"] == execution["coverage_application_contract"] == V2
        assert set(receipt["inherited_history"]) == {"detail_review"}
        assert set(receipt["inherited_history"]["detail_review"]) == {TARGET}
        assert receipt["bindings"] == [] and reply["material"] == []
        assert execution["semantic_coverage"] == "complete"
        assert all(effect["operations"] == [] for effect in execution["effects"].values())
        details = execution["stages"]["detail_review"]["account_coverage"]
        represented = [portion for portion in details["dispositions"]
                       if portion["quoted"] == ORIGINAL]
        assert represented and all(portion["record_ids"] == [] for portion in represented)
        assert all(portion["historical_representations"][0]["record_id"] == TARGET
                   for portion in represented)
        assert row["response"]["material_coverage"]["execution"] == execution
        latest = next(source for source in details["source_checks"] if source["source_id"] == "L1")
        assert latest["content_purpose"] == "non_account" and latest["substantive_spans"] == []
    calls = len(model.seen)
    replay_bodies = observe_body(monkeypatch)
    identity, message = READINGS[readings - 1]
    replay = send(client, message, identity, opened=opened)
    assert replay.status_code == 200, replay.text
    result = replay.json()
    assert result["replayed"] and result["metrics"]["llm_calls"] == 0
    assert result["material_coverage"]["execution"] == replies[-1]["material_coverage"]["execution"]
    assert result["continuation"] == replies[-1]["continuation"]
    assert Counter(identity for identity, _ in replay_bodies) == {
        row["turn_id"]: 1 for row in saved.brain_chat}
    assert all(accepted is True for _, accepted in replay_bodies)
    assert len(model.seen) == calls and wired.store.load(saved.id) == saved


@pytest.mark.parametrize("readings", (1, 2))
def test_one_exact_snapshot_memo_checks_each_v1_v2_ancestor_body_once(
    client, wired, monkeypatch, readings
):
    model, _, _, saved, _ = saved_chain(client, wired, monkeypatch, readings)
    context, before = current(wired, saved), deepcopy(saved)
    calls, model_calls = observe_body(monkeypatch), len(model.seen)
    memo = owner._SavedExecutionMemo(saved)
    owner._validate_execution_replay(saved, saved.brain_chat[-1], prior_conversation=(), _memo=memo)
    for _ in range(2):
        for size in range(1, len(saved.brain_chat) + 1):
            earlier = prefix(saved, size)
            owner._validate_execution_replay(
                earlier, earlier.brain_chat[-1], prior_conversation=(), _memo=memo)
        admissions, _ = owner._saved_record_admissions(saved, context[0], _memo=memo)
        assert set(admissions["detail_review"]) == {TARGET, REVISION}
        history = owner._saved_historical_support(
            saved, context[0], disputes=context[1], details=context[2], _memo=memo)
        assert set(history["detail_review"]) == {TARGET}
    assert Counter(identity for identity, _ in calls) == {
        row["turn_id"]: 1 for row in saved.brain_chat}
    assert all(result is True for _, result in calls)
    assert memo.validated == set(range(len(saved.brain_chat))) and memo.in_progress == set()
    assert saved == before and wired.store.load(saved.id) == saved
    assert len(model.seen) == model_calls


def test_earlier_v1_reply_remains_exact_after_two_new_v2_receipts(client, wired, monkeypatch):
    model, opened, initial, saved, _ = saved_chain(client, wired, monkeypatch, 2)
    calls = len(model.seen)
    for row in initial.brain_chat:
        original = row["response"]
        assert original["material_coverage"]["execution"]["coverage_application"]["contract"] == V1
        replay = send(
            client, row["message"], row["turn_id"],
            opened=None if row["turn_id"] == "application-original" else opened)
        assert replay.status_code == 200, replay.text
        result = replay.json()
        assert result["replayed"] and result["metrics"]["llm_calls"] == 0
        assert result["material_coverage"]["execution"] == original["material_coverage"][
            "execution"]
        assert result["continuation"] == original["continuation"]
    assert saved.brain_chat[:2] == initial.brain_chat
    assert len(model.seen) == calls and wired.store.load(saved.id) == saved


def test_local_and_inherited_history_use_independent_original_admissions_on_the_same_words(
    client, wired, monkeypatch
):
    model, opened, initial, saved, replies = saved_local_retirement(client, wired, monkeypatch)
    assert [row["id"] for row in current(wired, saved)[2]["rows"]] == [REPAIRED]
    reopened = public_record(client, saved.id)
    assert [(row["id"], row["statement"]) for row in reopened["rows"]] == [(REPAIRED, ORIGINAL)]
    assert {row["id"] for row in reopened["history"]} == {TARGET, REVISION, REPAIRED}
    for index, reply in enumerate(replies):
        assert reply["metrics"]["llm_calls"] == 8
        execution = reply["material_coverage"]["execution"]
        receipt = execution["coverage_application"]
        inherited = receipt["inherited_history"]["detail_review"]
        assert set(inherited) == ({TARGET} if index == 0 else {TARGET, REVISION})
        assert receipt["contract"] == V2 and execution["semantic_coverage"] == "complete"
        selected = [portion for portion in execution["stages"]["detail_review"][
            "account_coverage"]["dispositions"] if portion["quoted"] == ORIGINAL]
        assert selected and all(portion["record_ids"] == [] for portion in selected)
        assert all({proof["record_id"] for proof in portion["historical_representations"]}
                   == {TARGET, REVISION} for portion in selected)
        assert all(proof["original_source"]["turn_id"] == "application-original"
                   for portion in selected for proof in portion["historical_representations"])
    first = replies[0]["material_coverage"]["execution"]["coverage_application"]
    assert len(first["bindings"]) == 1 and first["bindings"][0]["result_id"] == REPAIRED
    assert replies[0]["material"][0]["quoted"] == REPAIR
    assert replies[1]["material"] == []
    context, memo = current(wired, saved), owner._SavedExecutionMemo(saved)
    calls = observe_body(monkeypatch)
    owner._validate_execution_replay(saved, saved.brain_chat[-1], prior_conversation=(), _memo=memo)
    history = owner._saved_historical_support(
        saved, context[0], disputes=context[1], details=context[2], _memo=memo)["detail_review"]
    assert set(history) == {TARGET, REVISION}
    assert history[TARGET]["selector"]["admission_turn_id"] == "application-original"
    assert history[REVISION]["selector"]["admission_turn_id"] == "application-revision"
    assert history[REVISION]["selector"]["retirement_turn_id"] == REPAIR_ID
    for entry in history.values():
        original = entry["record_support"]
        positive = [original["source_references"][check["source_id"]]
                    for check in original["review"]["account_check"]["source_checks"]
                    if check["supplies_account_content"] and check["supports_proposal"]]
        assert {source["turn_id"] for source in positive if source["quoted"] == ORIGINAL} == {
            "application-original"}
        assert entry["historical_result"]["original_record_support"] == original
    assert Counter(identity for identity, _ in calls) == {
        row["turn_id"]: 1 for row in saved.brain_chat}
    calls_before = len(model.seen)
    replay = send(client, READINGS[1][1], READINGS[1][0], opened=opened)
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] and replay.json()["metrics"]["llm_calls"] == 0
    assert replay.json()["material_coverage"]["execution"] == replies[1]["material_coverage"][
        "execution"]
    assert saved.brain_chat[:2] == initial.brain_chat
    assert len(model.seen) == calls_before and wired.store.load(saved.id) == saved
