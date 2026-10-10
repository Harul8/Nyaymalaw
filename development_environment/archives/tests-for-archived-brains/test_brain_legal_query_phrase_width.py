"""Offline owned-query formatting boundaries; no live retrieval or model calls."""

import json

import pytest

from tests.test_brain_legal_requirements import (
    CONVERSATION,
    REQUEST_SUBJECT,
    Model,
    decompose_subjects,
)

QUERY = (
    "Written notice under an agreement requiring notice: identify the governing statutory "
    "condition, the person obliged to notify, the relevant time and method, any exception "
    "that removes the notice requirement, contrary authority limiting the proposed route, "
    "and the distinction between a legal notice obligation and unverified factual compliance "
    "with that condition in the reported transaction"
)
assert len(QUERY) > 300


def query_reply(text=QUERY, identity="q1"):
    return {"plans": [{"subject_id": identity, "queries": [{"text": text}]}]}


def planning(model):
    return decompose_subjects(
        model,
        subjects=(REQUEST_SUBJECT,),
        material_by_subject={"q1": []},
        conversation=CONVERSATION,
    )


def test_long_qualified_owned_search_query_is_accepted_once_without_trimming():
    model = Model([query_reply()])
    result = planning(model)
    assert len(model.calls) == 1
    assert result.rows["q1"] == (QUERY,)
    assert result.coverage["q1"]["checked_items"] == 1
    assert model.calls[0][3] > 0
    queries = model.calls[0][1]["properties"]["plans"]["items"]["properties"]["queries"]
    assert queries["maxItems"] == 4


@pytest.mark.parametrize("text", ["", "   "])
def test_blank_query_still_gets_one_owned_correction_and_remains_unread(text):
    model = Model([query_reply(text)])
    result = planning(model)
    assert len(model.calls) == 2
    assert "q1" not in result.rows
    assert result.coverage["q1"]["checked_items"] == 0
    assert result.coverage["q1"]["unread_items"] == 1
    repair = json.loads(model.calls[1][0].user)
    assert list(repair["validation_issues"]) == ["q1"]


def test_long_query_cannot_substitute_a_foreign_subject_owner():
    model = Model([query_reply(identity="foreign-question")])
    result = planning(model)
    assert len(model.calls) == 2
    assert "q1" not in result.rows and "foreign-question" not in result.rows
    assert result.coverage["q1"]["unread_items"] == 1
