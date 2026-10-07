"""Exact category selections and source ownership, independently of model meaning."""
from copy import deepcopy
import json

import pytest

from nm.brain.conversation import (
    Conversation, IncompleteConversation, Message, checked_message_parts, interpret,
)
from nm.shared.model_port import SchemaViolation
from tests.test_new_brain_conversation import Model, interpretation, item


MIXED = "Hello. I found the signed report. Please list the dates, then wait."
PARTS = [
    {"category": "social", "selections": [{"source_id": "L1", "whole_source": True}]},
    {"category": "information", "selections": [{"source_id": "L2", "whole_source": True}]},
    {"category": "work_request", "selections": [{"source_id": "L3", "start": 0, "end": 22}]},
    {"category": "conversation_direction", "selections": [{"source_id": "L3", "start": 23, "end": 33}]},
]


def test_mixed_message_labels_resolve_exact_original_words_and_whitespace_gaps():
    result = checked_message_parts(PARTS, MIXED)
    assert [row["category"] for row in result] == [
        "social", "information", "work_request", "conversation_direction"]
    assert [row["sources"][0]["text"] for row in result] == [
        "Hello.", "I found the signed report.", "Please list the dates,", "then wait."]
    assert all(source["text"] == MIXED[source["start"]:source["end"]]
               for row in result for source in row["sources"])


@pytest.mark.parametrize("change", ["missing", "foreign", "overrun", "unknown_category", "changed_text"])
def test_parts_reject_missing_content_foreign_sources_and_authored_words(change):
    parts = deepcopy(PARTS)
    if change == "missing":
        parts.pop(1)
    elif change == "foreign":
        parts[0]["selections"][0]["source_id"] = "P1S1"
    elif change == "overrun":
        parts[-1]["selections"][0]["end"] = 1000
    elif change == "unknown_category":
        parts[0]["category"] = "proven"
    else:
        parts[0]["text"] = "Invented replacement"
    with pytest.raises(SchemaViolation):
        checked_message_parts(parts, MIXED)


def test_repeated_words_keep_their_original_positions_and_can_serve_two_purposes():
    text = "Yes. Yes."
    parts = [{"category": category, "selections": [{"source_id": identity, "whole_source": True}]}
             for identity, category in [("L1", "answer_to_question"), ("L2", "social"),
                                        ("L1", "information")]]
    checked = checked_message_parts(parts, text)
    assert [row["sources"][0]["start"] for row in checked] == [0, 5, 0]


def test_meaningful_phrases_need_no_model_character_counting():
    text = "Hello, please wait until I send the document."
    parts = [
        {"category": "social", "selections": [{"source_id": "L1", "exact_text": "Hello,"}]},
        {"category": "conversation_direction", "selections": [{
            "source_id": "L1", "exact_text": "please wait until I send the document."}]},
    ]
    result = checked_message_parts(parts, text)
    assert [row["sources"][0]["start"] for row in result] == [0, 7]
    assert result[1]["sources"][0]["text"].endswith("until I send the document.")


@pytest.mark.parametrize("text,selection", [
    ("Please wait, please wait.", "lease wait"),
    ("The payment has not arrived.", "The payment has arrived."),
])
def test_quoted_portion_cannot_silently_choose_an_occurrence_or_change_meaning(text, selection):
    with pytest.raises(SchemaViolation, match="one exact portion"):
        checked_message_parts([{"category": "information", "selections": [
            {"source_id": "L1", "exact_text": selection}]}], text)


def test_blank_lines_are_not_offered_as_impossible_selections():
    from nm.brain.conversation import _message_sources
    text = "\nHello.\n"
    sources = _message_sources(text)
    assert all(row["text"].strip() for row in sources.values())
    result = checked_message_parts([{"category": "social", "selections": [
        {"source_id": key, "whole_source": True} for key in sources if key != "$message"]}], text)
    assert result[0]["sources"][0]["text"] == "Hello."


def test_position_comes_from_complete_history_in_a_separate_classification_call():
    for messages, expected in [((), "first"), ((Message("old", "advocate", "Earlier words."),), "follow_up")]:
        data = interpretation([item("Hello.", relation="new", scope="none", step="answer")])
        data["message_parts"] = [{"category": "social", "selections": [
            {"source_id": "$message", "whole_source": True}]}]
        model = Model(data)
        result = interpret(model, Conversation(messages), "Hello.")
        assert json.loads(model.calls[0][0].user)["message_position"] == expected
        assert result.message_parts[0]["category"] == "social"
        assert [call[0].operation for call in model.calls] == ["label_message", "interpret_conversation"]
    model = Model(data)
    with pytest.raises(IncompleteConversation):
        interpret(model, Conversation((), complete=False), "Hello.")
    assert model.calls == []


@pytest.mark.parametrize("messages,matter_id,latest,expected", [
    ((), "already-open", "Following up on my request.", "first"),
    ((Message("earlier", "advocate", "Please wait."),), None,
     "This is my first message about this subject.", "follow_up"),
])
def test_position_is_not_inferred_from_topic_words_or_matter_existence(
        messages, matter_id, latest, expected):
    data = interpretation([item(latest, relation="new", scope="none", step="answer")])
    model = Model(data)
    interpret(model, Conversation(messages, current_matter_id=matter_id), latest)
    assert len(model.calls) == 2
    prompt = model.calls[0][0]
    supplied = json.loads(prompt.user)
    assert supplied["message_position"] == expected
    assert supplied["latest_message"] == latest
    assert len(supplied["earlier_conversation"]) == len(messages)
    # Position is owned input, not a field the model may choose or override.
    assert "message_position" not in model.calls[0][1]["properties"]

