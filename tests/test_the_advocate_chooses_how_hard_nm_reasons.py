"""The advocate chooses how hard NM reasons for a turn, and the turn records the model and the effort it ran with (plan AN.33, D23;
piece 33n).

The owner, 1 Nov 2026: "You can have some 3-4 categories like low, medium, high, max. So this category should be used to tune the
reasoning effort", and "Reset for new conversations". Medium is the table of plan AN.30 as it stands; Low and High move every call of
the turn a level down or up, never below low or above high; Max puts every call at max, the highest level that 6 Luna, 6.1 Terra and
6.1 Sol each accept (their model pages, read 1 Nov 2026). From D27 (2 Nov 2026, piece 33p) every call may write its room at every
choice - what its input leaves of its model's context, up to the most the models write - so the choice moves only how hard it reasons.
The turn records the model and the effort with its metrics, and in its request where they are not the defaults - so that a turn sent
with the defaults is the request it was before.
"""
import json

import pytest

from nm.core_engine import reasoning
from nm.core_engine.calls import TurnCalls
from nm.core_engine.conversation import ConversationRefused, chat_matter_id
from nm.core_engine.turn import saved_rows
from nm.shared.model_port import EFFORTS, Prompt, Tier, estimate_tokens
from tests.test_core_turn import ScriptedModel, run, store  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a


def test_the_choices_move_every_level_as_the_plan_says():
    assert reasoning.CHOICES == ("low", "medium", "high", "max") and reasoning.DEFAULT_CHOICE == "medium"
    assert reasoning.LEVELS == ("low", "medium", "high") and set(reasoning.CHOICES) <= set(EFFORTS) == {*reasoning.LEVELS, "max"}
    table = {choice: [reasoning.chosen(level, choice) for level in (None, "low", "medium", "high")] for choice in reasoning.CHOICES}
    assert table == {"low": ["low", "low", "low", "medium"], "medium": [None, "low", "medium", "high"],
                     "high": ["medium", "medium", "high", "high"], "max": ["max", "max", "max", "max"]}
    with pytest.raises(ValueError):
        reasoning.chosen("medium", "extreme")


class Seen:
    """A model that answers nothing and keeps what it was asked."""

    def __init__(self):
        self.asked = []

    def context_budget(self, tier):
        return 1_000_000

    def structured(self, prompt, schema, tier, *, max_tokens):
        from nm.shared.model_port import ModelResult, Usage
        from nm.shared.budget_contracts import Completion
        self.asked.append((prompt.effort, max_tokens))
        return ModelResult(None, {}, tier, "synthetic", "fixture", Usage(1, 1, 0), 0, completion=Completion.COMPLETE)


@pytest.mark.parametrize("choice, expected", [
    ("medium", [(None, 8000), ("medium", 8000), ("high", 8000)]),
    ("low", [("low", 8000), ("low", 8000), ("medium", 8000)]),
    ("high", [("medium", 8000), ("high", 8000), ("high", 8000)]),
    ("max", [("max", 8000), ("max", 8000), ("max", 8000)]),
])
def test_the_turns_ledger_moves_each_call_by_the_effort_chosen_and_keeps_what_it_may_write(choice, expected):
    model = Seen()
    calls = TurnCalls(model, effort=choice, chosen={"model": "gpt-6-luna", "effort": choice})
    for level in (None, "medium", "high"):
        calls.structured(Prompt(user="Read this.", operation="core_x", effort=level), {"type": "object"}, Tier.ROUTINE,
                         max_tokens=8000)
    assert model.asked == expected
    assert calls.metrics()["chosen"] == {"model": "gpt-6-luna", "effort": choice}
    assert "chosen" not in TurnCalls(Seen()).metrics(), "a turn nobody chose for records no choice"
    with pytest.raises(ValueError):
        TurnCalls(Seen(), effort="extreme")


class Recording(ScriptedModel):
    """The scripted turn's model, keeping the effort and the allowance of every call it is asked."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.efforts = []

    def structured(self, prompt, schema, tier, **kwargs):
        room = self.context_budget(tier) - estimate_tokens((prompt.system or "") + prompt.user + json.dumps(schema))
        self.efforts.append((prompt.operation, prompt.effort, kwargs.get("max_tokens"), min(reasoning.MOST_OUTPUT, room)))
        return super().structured(prompt, schema, tier, **kwargs)


def test_a_turn_runs_at_the_effort_chosen_and_records_the_model_and_the_effort(store):
    plain, high = Recording(legal=True), Recording(legal=True)
    first = run(store, plain)
    second = run(store, high, turn_id="t2", chat_id=first["chat_id"], chosen_model="gpt-6-luna", effort="high")
    assert second["committed"] == "committed" and second["metrics"]["chosen"] == {"model": "gpt-6-luna", "effort": "high"}
    assert "chosen" not in first["metrics"]
    asked = {operation: effort for operation, effort, _, _ in high.efforts}
    usual = {operation: effort for operation, effort, _, _ in plain.efforts}
    for operation, effort in usual.items():
        if operation in asked:
            assert asked[operation] == reasoning.chosen(effort, "high"), operation
    assert all(tokens == room for _, _, tokens, room in plain.efforts + high.efforts), "every call writes its room, at either effort"
    rows = saved_rows(store.load(chat_matter_id("owner", first["chat_id"])), "owner")
    assert "effort" not in rows[0]["request"] and "model" not in rows[0]["request"], "the defaults leave the request as it was"
    assert rows[1]["request"]["effort"] == "high" and "model" not in rows[1]["request"], "a choice other than the default is kept"


def test_an_effort_not_offered_is_refused_before_any_call(store):
    model = Recording(legal=True)
    with pytest.raises(ConversationRefused) as refused:
        run(store, model, effort="extreme")
    assert refused.value.status == 422 and model.efforts == []
