"""The model proposes what to ask the advocate once the plan is known (plan AN.37, piece 37d), code admits it, and the served
turn asks it. Scripted models; what a real model asks is measured in a paid run, not here."""
from __future__ import annotations

import json
import pytest

from nm.core_engine import questions
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, ProviderUnavailable, Tier, Usage, UsageLimitReached
from tests.test_core_served import OWNER, served  # noqa: F401 -- the fixture

pytestmark = pytest.mark.class_a

ASKED = {"header": "Your client", "question": "Whom do you act for?", "why": "It decides who is adverse to your client.",
         "choices": [{"label": "The buyer", "description": ""}, {"label": "The seller", "description": ""}],
         "multiple": False, "default": ["The buyer"], "depends": []}
PLAN = {"proposal": {"understanding": {"disputes": [{"id": "D1", "name": "Recovery of the price", "between": "A and B",
                                                     "legal_questions": ["Is the price due?"], "rights_at_stake": "",
                                                     "relief_sought": "", "missing_facts": ["Whom the advocate acts for"]}]}}}
CONTEXT = {"conversation": [{"record_role": "original_account", "text": "Earlier words."},
                            {"record_role": "nm_interpretation", "text": "NM's earlier reply."}],
           "latest": {"text": "Advise on the recovery."}}


class Calls:
    def __init__(self, outcome):
        self.outcome, self.asked = outcome, []

    def context_budget(self, tier):
        return 1_000_000

    def structured(self, prompt, schema, tier, *, max_tokens):
        self.asked.append((prompt, schema, tier))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return ModelResult(None, self.outcome, tier, "openai", "gpt-6-luna", Usage(10, 10, 0.0), 1,
                           completion=Completion.COMPLETE)


def test_the_model_is_shown_the_advocates_words_the_disputes_and_what_was_asked_before():
    calls = Calls({"questions": [ASKED]})
    proposed = questions.propose(calls, CONTEXT, {}, PLAN, ["Which court?"])
    assert proposed == [{**ASKED, "asked_by": "model"}]
    prompt, schema, tier = calls.asked[0]
    assert prompt.operation == "core_questions" and prompt.effort == "medium" and tier is Tier.ROUTINE
    shown = json.loads(prompt.user)
    assert shown["advocate_messages"] == ["Earlier words.", "Advise on the recovery."]  # NM's own words are not theirs
    assert shown["disputes"][0]["id"] == "D1" and shown["asked_before"] == ["Which court?"]
    # And code admits what the model proposed.
    admitted, refused = questions.admit(proposed, disputes=["D1"])
    assert [q["question"] for q in admitted] == ["Whom do you act for?"] and refused == []


def test_nothing_is_asked_without_a_dispute_and_a_failed_step_asks_nothing_but_a_usage_limit_stops_the_turn():
    calls = Calls({"questions": [ASKED]})
    assert questions.propose(calls, CONTEXT, {}, {"proposal": {"understanding": {"disputes": []}}}, []) == []
    assert calls.asked == []
    assert questions.propose(Calls(ProviderUnavailable("outage")), CONTEXT, {}, PLAN, []) == []
    with pytest.raises(UsageLimitReached):
        questions.propose(Calls(UsageLimitReached("used up")), CONTEXT, {}, PLAN, [])


def test_the_served_turn_proposes_with_this_step_and_a_message_that_needs_no_question_opens_no_window(served):
    """The composition's own proposer is this step; a model that proposes nothing (most messages) leaves the turn as before,
    the step's one call made and counted. Asking and answering through the page is tests/test_the_page_answers_what_nm_asks."""
    assert served.app.propose_questions is questions.propose
    reply = served.client.post("/api/turn", json={"message": "Inspect this reported account.", "turn_id": "turn-1"})
    assert reply.status_code == 200 and reply.json()["questions_asked"] is None
    operations = [call["operation"] for call in reply.json()["metrics"]["calls"]]
    assert operations.count("core_questions") == 1
    assert served.app.questions.window(OWNER, "turn-1") is None
