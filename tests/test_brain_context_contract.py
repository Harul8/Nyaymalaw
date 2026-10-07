"""Context reconstruction versions preserve saved evidence without model calls."""
import json

import pytest

from nm.brain.conversation import Conversation, Message, interpret
from tests.test_new_brain_conversation import Model, interpretation, item


def test_compatibility_metadata_is_not_presented_as_conversation():
    prior = Message("prior", "nm", "The public question.",
                    recorded_at="2026-10-07T09:00:00+05:30",
                    legacy_text="Internal finding.", legacy_order=0)
    model = Model(interpretation([item("Yes", scope="none", step="answer")]))
    interpret(model, Conversation((prior,)), "Yes")
    payload = json.loads(model.calls[0][0].user)
    assert payload["earlier_conversation"][0]["text"] == "The public question."
    assert "Internal finding" not in model.calls[0][0].user
    assert "legacy_order" not in model.calls[0][0].user


@pytest.mark.parametrize("metadata", [dict(legacy_text=""), dict(legacy_order=-1),
                                       dict(legacy_order=True)])
def test_unreadable_reconstruction_metadata_is_rejected(metadata):
    with pytest.raises(ValueError):
        Message("prior", "nm", "Readable", **metadata)

