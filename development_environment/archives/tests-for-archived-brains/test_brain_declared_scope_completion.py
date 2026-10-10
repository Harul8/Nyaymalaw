"""Declared mutation work cannot vanish through a none goal or completed reply.

Fresh writers return raw expressions. Accepting reviewers are deliberately
fabricated; these tests qualify mechanical scope and lifecycle checks only.
"""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import turn as boundary
from nm.brain.work_state import project_work
from tests.brain_reader_fixture import fixture_scoped_coverage, scripted_support_spans
from tests.test_brain_continuation_service import send
from tests.test_brain_evidence_rendering_public import (
    RawExpressionModel,
    expression,
    raw_unit,
    reopened,
    visible,
)
from tests.test_brain_scope_span_public import (
    CUSTODY,
    INSTRUCTION,
    ORIGINAL,
    REVISED,
    SpanNeighbourModel,
    correction,
    saved_and_replayed,
    seed,
)
from tests.test_brain_turn import plan

LIE = "The correction was saved and the requested record work is complete."
MESSAGE = INSTRUCTION + " " + REVISED
QUESTION_MESSAGE = "Which part of the reported chronology should be examined?"
REVIEW_MESSAGE = "Examine the arrival entry against the original reported account."


class ScopeJudgments:
    """The scenario independently declares these original passages' purposes."""

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        checked = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        payload = json.loads(prompt.user)
        payload = payload.get("original_input", payload)
        purposes = {ORIGINAL: "account", CUSTODY: "account", REVISED: "account",
                    INSTRUCTION: "non_account", QUESTION_MESSAGE: "non_account",
                    REVIEW_MESSAGE: "non_account"}
        data = deepcopy(checked.data)
        if prompt.operation == "classify_account_sources":
            for identity, row in data["source_treatments"].items():
                reference = payload["original_source_catalogue"][identity]
                if purposes[reference["quoted"]] == "non_account":
                    row.update(content_role="work_instruction", substantive_spans=[])
            return replace(checked, data=data)
        if prompt.operation in ("verify_disputes", "verify_material_grounding"):
            data = scripted_support_spans(payload, data, scripted_source_account=True)
            coverage_purposes = dict(purposes)
            if prompt.operation == "verify_disputes":
                # These dated-arrival and custody passages supply material facts,
                # without declaring a disputed position for the dispute reader.
                coverage_purposes.update({ORIGINAL: "outside_scope", CUSTODY: "outside_scope",
                                          REVISED: "outside_scope"})
            data["coverage"] = fixture_scoped_coverage(payload, data, source_decisions={
                identity: coverage_purposes[payload["source_treatments"][identity]["quoted"]]
                for identity in payload["coverage_source_ids"]})
            return replace(checked, data=data)
        return checked


class ScopedRawModel(ScopeJudgments, RawExpressionModel):
    pass


class SupportedSpanModel(ScopeJudgments, RawExpressionModel):
    """Use the extractor transport without borrowing another scenario's judgments."""

    def __init__(self, routes, writers, *, records, selected_source, fulfilled=False):
        super().__init__(routes, writers)
        self.records = records
        self.selected_source = selected_source
        self.fulfilled = fulfilled
        self.omit_failed_units = False

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        if prompt.operation == "extract_legal_details":
            return SpanNeighbourModel.structured(self, prompt, schema, tier,
                                                max_tokens=max_tokens)
        checked = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        if prompt.operation == "verify_continuation" and self.fulfilled:
            data = deepcopy(checked.data)
            for row in data["verdicts"]:
                row["record_check"] = {
                    "outcome": "fulfilled",
                    "reason": "The independent judgment confirms this task's actual correction.",
                }
            return replace(checked, data=data)
        return checked


def pending_work(client, wired, monkeypatch, identity):
    opened, records, target, custody = seed(client, wired, monkeypatch, identity)
    first = project_work(reopened(wired, opened))
    task, = [row for row in first["rows"] if row["kind"] == "task"]

    def propose(payload):
        return {"units": [raw_unit(
            payload, operator="question", kind="question", focus="chronology", questions=True)]}

    model = RawExpressionModel([plan(QUESTION_MESSAGE, scope="current")], [propose])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    send(client, QUESTION_MESSAGE, identity + "-other-work", opened=opened)
    before = project_work(reopened(wired, opened))
    unrelated, = [row for row in before["rows"]
                  if row["kind"] == "task" and row["id"] != task["id"]]
    question, = [row for row in before["rows"] if row["kind"] == "question"]
    assert task["record_requirement"]["kind"] == unrelated["record_requirement"]["kind"] == "none"
    return opened, records, target, custody, before, task["id"], unrelated["id"], question["id"]


def scope_route(target, *, mode="substantive", kind="account_contribution", message=MESSAGE):
    routed = plan(message, scope="current", relation="continues", material_purposes=(kind,))
    routed["items"][0].update(response_mode=mode, mutation_scopes=[{
        "authority_kind": kind, "authority_source_ids": ["L1"], "target_scope": "exact",
        "target_ids": [target], "permitted_relations": ["corrects"],
    }])
    assert routed["items"][0]["record_requirement"]["kind"] == "none"
    return routed


def scoped_unit(payload, task, *, status="none", links="none", complete=False,
                question_id=None, current_ids=(), progress_reason=LIE):
    unit = raw_unit(payload, record_status=status)
    unit["work_selector"] = task
    if links != "none":
        operator = "question" if links == "questions" else "next_work"
        selected = [span["id"] for span in payload["latest_message_spans"]]
        unit["blocks"].append({
            "id": "linked-followup", "kind": "completion", "uncertainty": "reported",
            "evidence_expression": expression(operator, sources=selected, focus="chronology"),
        })
        unit[links] = [{
            "id": "followup", "block_id": "linked-followup",
            "purpose": "Clarify the chronology of the supplied account before proceeding.",
            "target_ids": [], "existing_id": "",
        }]
    if status != "none":
        unit["blocks"].append({
            "id": "record-status", "kind": "completion", "uncertainty": "none",
            "evidence_expression": expression("record_result"),
        })
        unit["record_outcome"].update(
            block_id="record-status", current_record_ids=list(current_ids),
            effect_ids=[identity for identity, effect in payload["record_effect_catalogue"].items()
                        if effect["performed"]] if status == "performed" else [],
            reason="The requested mutation scope has the stated result.")
    unit["sufficiency"] = {"status": "complete" if complete else "partial", "block_id": "main"}
    selected = [row["id"] for row in payload["latest_message_spans"]]
    unit["progress_updates"] = [{
        "target_id": "$work", "status": "complete", "block_id": "main",
        "reason": progress_reason, "span_ids": selected,
    }] if complete else []
    if question_id is not None:
        unit["progress_updates"].append({
            "target_id": question_id, "status": "complete", "block_id": "main",
            "reason": "The supplied dated words answer the independent chronology question.",
            "span_ids": selected,
        })
    return unit


def assert_preserved_work(wired, answer, before, task, unrelated, question, *, answered):
    after = {row["id"]: row for row in project_work(reopened(wired, answer))["rows"]}
    original = {row["id"]: row for row in before["rows"]}
    assert after[task] == original[task]
    assert after[unrelated] == original[unrelated]
    assert after[question]["status"] == ("complete" if answered else original[question]["status"])


@pytest.mark.parametrize("links", ["none", "questions", "next_work"])
@pytest.mark.parametrize("complete", [False, True])
def test_declared_non_new_scope_cannot_use_none_even_when_requirement_metadata_says_none(
        client, wired, monkeypatch, links, complete):
    identity = "scope-completion-none-" + links + "-" + str(complete)
    opened, records, target, _custody, before, task, unrelated, question = pending_work(
        client, wired, monkeypatch, identity)

    def first(payload):
        request, = payload["material_coverage"]["execution"]["requests"]
        assert request["record_requirement"]["kind"] == "none"
        return {"units": [scoped_unit(payload, task, links=links, complete=complete)]}

    def recover(payload):
        bad, = payload["correction"]["rejected_units"]
        assert bad["record_outcome"]["status"] == "none"
        return {"units": [scoped_unit(
            payload, task, status="unresolved", links=links, question_id=question)]}

    model = ScopedRawModel([scope_route(target)], [first, recover])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, MESSAGE, identity, opened=opened)
    assert answer["blocked"] is False
    assert len(model.writer_outputs) == 2
    assert "requested record work remains unfinished" in visible(answer)
    assert LIE not in visible(answer)
    unit, = answer["continuation"]["units"]
    assert unit["record_outcome"]["status"] == "unresolved"
    assert unit["sufficiency"]["status"] != "complete"
    assert all(update["target_id"] == question for update in unit["progress_updates"])
    execution = answer["material_coverage"]["execution"]
    assert execution["record_changes"] == []
    assert execution["requests"][0]["fulfillment"] == "unfinished"
    saved = saved_and_replayed(client, wired, model, answer, opened, identity, MESSAGE)
    assert boundary._current_records(wired.store, saved)[0].open_material == records
    assert_preserved_work(wired, answer, before, task, unrelated, question, answered=True)
    review_inputs = [payload for operation, payload in model.calls
                     if operation == "verify_continuation"]
    assert len(review_inputs) == 1
    assert all(unit["record_outcome"]["status"] != "none"
               for payload in review_inputs for unit in payload["units"])


@pytest.mark.parametrize("links", ["none", "questions", "next_work"])
def test_unfinished_scoped_work_cannot_complete_task_from_an_answer_or_followup(
        client, wired, monkeypatch, links):
    identity = "scope-completion-unresolved-" + links
    opened, records, target, _custody, before, task, unrelated, question = pending_work(
        client, wired, monkeypatch, identity)
    model = ScopedRawModel([scope_route(target)], [
        lambda payload: {"units": [scoped_unit(
            payload, task, status="unresolved", links=links, complete=True)]},
        lambda payload: {"units": [scoped_unit(
            payload, task, status="unresolved", links=links, question_id=question)]},
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, MESSAGE, identity, opened=opened)
    assert answer["blocked"] is False
    assert len(model.writer_outputs) == 2
    assert "requested record work remains unfinished" in visible(answer)
    assert_preserved_work(wired, answer, before, task, unrelated, question, answered=True)
    saved = saved_and_replayed(client, wired, model, answer, opened, identity, MESSAGE)
    assert boundary._current_records(wired.store, saved)[0].open_material == records


def test_matching_actual_scoped_effect_can_complete_task_with_no_extra_retry(
        client, wired, monkeypatch):
    identity = "scope-completion-performed"
    opened, _records, target, custody, before, task, unrelated, question = pending_work(
        client, wired, monkeypatch, identity)
    model = SupportedSpanModel(
        [scope_route(target)],
        [lambda payload: {"units": [scoped_unit(
            payload, task, status="performed", complete=True,
            progress_reason="The matching saved record result completes this task.")]}],
        records=[correction(identity, target)], selected_source="L2", fulfilled=True)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, MESSAGE, identity, opened=opened)
    assert answer["blocked"] is False
    assert len(model.writer_outputs) == 1
    assert answer["material_coverage"]["execution"]["requests"][0]["fulfillment"] == "fulfilled"
    saved = saved_and_replayed(client, wired, model, answer, opened, identity, MESSAGE)
    current = boundary._current_records(wired.store, saved)[0].open_material
    assert target not in {row["id"] for row in current}
    assert custody in {row["id"] for row in current}
    assert REVISED in {row["statement"] for row in current}
    after = {row["id"]: row for row in project_work(saved)["rows"]}
    old = {row["id"]: row for row in before["rows"]}
    assert after[task]["status"] == "complete"
    assert after[unrelated] == old[unrelated]
    assert after[question] == old[question]


class NoChangeReviewModel(ScopedRawModel):
    def structured(self, prompt, schema, tier, *, max_tokens=None):
        checked = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        if prompt.operation == "verify_continuation":
            data = deepcopy(checked.data)
            for reviewed in data["verdicts"]:
                reviewed["record_check"] = {
                    "outcome": ("no_change_justified" if self.writer_outputs[-1]["units"][0][
                        "record_outcome"]["status"] == "review_no_change" else "unfinished"),
                    "reason": "The independently scripted full review retains the account.",
                }
            return replace(checked, data=data)
        return checked


def test_actual_declared_interpretation_review_can_complete_without_a_change_or_retry(
        client, wired, monkeypatch):
    identity = "scope-completion-reviewed-no-change"
    opened, records, target, _custody, before, task, unrelated, question = pending_work(
        client, wired, monkeypatch, identity)
    message = REVIEW_MESSAGE
    model = NoChangeReviewModel(
        [scope_route(target, kind="interpretation_review", message=message)],
        [lambda payload: {"units": [scoped_unit(
            payload, task, status="review_no_change", complete=True, current_ids=[target],
            progress_reason="The checked original account requires no change.")]},
         lambda payload: {"units": [scoped_unit(payload, task, status="unresolved")]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, message, identity, opened=opened)
    assert answer["blocked"] is False
    assert len(model.writer_outputs) == 1, json.dumps([
        payload.get("correction") for operation, payload in model.calls
        if operation == "continue_conversation"], indent=2)
    assert "record review completed without a selected change" in visible(answer)
    assert answer["material_coverage"]["execution"]["requests"][0]["fulfillment"] == (
        "no_change_justified")
    saved = saved_and_replayed(client, wired, model, answer, opened, identity, message)
    assert boundary._current_records(wired.store, saved)[0].open_material == records
    after = {row["id"]: row for row in project_work(saved)["rows"]}
    old = {row["id"]: row for row in before["rows"]}
    assert after[task]["status"] == "complete"
    assert after[unrelated] == old[unrelated]
    assert after[question] == old[question]


def test_ordinary_quoted_answer_without_record_scope_keeps_none_without_retry(
        client, wired, monkeypatch):
    message = "The client reports uncertainty about the arrival date."
    model = RawExpressionModel([plan(message)], [
        lambda payload: {"units": [raw_unit(payload)]},
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, message, "scope-completion-ordinary")
    assert answer["blocked"] is False
    assert len(model.writer_outputs) == 1
    assert answer["continuation"]["units"][0]["record_outcome"]["status"] == "none"
    assert "requested record work remains unfinished" not in visible(answer)
    assert answer["material_coverage"]["execution"]["mutation_authorities"]["authorities"] == []
    assert reopened(wired, answer).brain_chat[-1]["response"]["elements"] == answer["elements"]
