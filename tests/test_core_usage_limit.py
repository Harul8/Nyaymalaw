"""A turn when the provider's account has no credit left (owner decision P51, 25 Oct 2026; plan
AN.11). The scripted model's failure is the provider's 'no credit' answer instead of an outage;
what the turn does with it is wiring evidence, as the scripted turns are.
"""
import json

import pytest

from nm.core_engine.conversation import ConversationRefused
from nm.shared.model_port import USAGE_LIMIT_MESSAGE, ProviderUnavailable, UsageLimitReached
from tests.test_core_served import OWNER, send, served  # noqa: F401 - the served fixture
from tests.test_core_turn import ScriptedModel, run, store  # noqa: F401 - the store fixture

pytestmark = pytest.mark.class_a

SAID = USAGE_LIMIT_MESSAGE + " Your saved conversation is unchanged."


class NoCredit(ScriptedModel):
    """The scripted model whose failure is the provider's 'no credit' answer, not an outage."""

    def structured(self, prompt, schema, tier, **kwargs):
        try:
            return super().structured(prompt, schema, tier, **kwargs)
        except ProviderUnavailable as exc:
            raise UsageLimitReached("You have no credits remaining.") from exc


# --- the turn that cannot be answered (piece 2) ---------------------------------------------

@pytest.mark.parametrize("failing", ["core_understanding", "core_response_writer", "core_response_review"])
def test_a_turn_the_account_cannot_answer_is_refused_in_the_owners_words(store, caplog, failing):
    with pytest.raises(ConversationRefused) as refused:
        run(store, NoCredit(failure=failing))
    error = refused.value
    assert (error.code, error.status, error.committed, error.retryable) == ("usage_limit", 402, "not_committed", True)
    assert error.why == SAID
    # Kept for whoever runs the service: the failure's own name and the stage, no words of the matter.
    assert error.diagnosis.startswith("usage_limit-UsageLimitReached-")
    assert not store.list_for("owner").matters
    logged, = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Message not answered")]
    assert "UsageLimitReached" in logged and "Hello." not in logged


def test_the_same_message_is_answered_once_the_account_is_topped_up(store):
    model = NoCredit(failure="core_response_review")
    with pytest.raises(ConversationRefused):
        run(store, model)
    model.failure = None
    assert run(store, model)["committed"] == "committed"


def test_the_served_turn_says_it_in_the_owners_words_and_saves_nothing(served):  # noqa: F811
    original = served.model.structured

    def exhausted(prompt, schema, tier, **kwargs):
        try:
            return original(prompt, schema, tier, **kwargs)
        except ProviderUnavailable as exc:
            raise UsageLimitReached("You have no credits remaining.") from exc
    served.model.structured, served.model.failure = exhausted, "core_response_review"
    response = send(served)
    assert response.status_code == 402
    detail = response.json()["detail"]
    assert (detail["code"], detail["why"], detail["committed"], detail["retryable"]) == (
        "usage_limit", SAID, "not_committed", True)
    assert not served.store.list_for(OWNER).matters


# --- the answer that lost a step to it (piece 3) ----------------------------------------------

from nm.core_engine import response_review, turn  # noqa: E402
from nm.shared.model_port import USAGE_LIMIT_WORDS  # noqa: E402
from tests.test_core_answer_sections import Scripted, answered, kinds, refused  # noqa: E402


class NoCreditAnswering(Scripted):
    """The scripted answering whose failures are the provider's 'no credit' answer, not an outage."""

    def structured(self, prompt, schema, tier, **kwargs):
        try:
            return super().structured(prompt, schema, tier, **kwargs)
        except ProviderUnavailable as exc:
            raise UsageLimitReached("You have no credits remaining.") from exc


class ReviewLostForTheSecond(NoCreditAnswering):
    """Only the second dispute's review meets it."""

    def structured(self, prompt, schema, tier, **kwargs):
        if prompt.operation == "core_response_review" and (
                json.loads(prompt.user).get("what_you_review") or {}).get("dispute") == "Dispute 2":
            raise UsageLimitReached("You have no credits remaining.")
        return super().structured(prompt, schema, tier, **kwargs)


CROSS_CHECK_LOST = ("NM could not check the sections against each other this time (" + USAGE_LIMIT_WORDS
                    + "), so a conflict between them may not have been caught. Each section was checked on its own.")
OVERVIEW_LOST = ("NM's line on what to do first is left out: " + USAGE_LIMIT_WORDS
                 + ". Each dispute's section below was checked on its own.")


def test_a_check_across_the_sections_lost_to_it_is_said_atop_the_answer_in_the_owners_words():
    ctx, elements, activity, _ = answered(NoCreditAnswering(fail={"core_response_cross_check"}))
    assert activity["cross_check"] == {"unavailable": "usage"}
    assert elements[0]["kind"] == "NOTICE" and elements[0]["text"] == CROSS_CHECK_LOST
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_an_overview_lost_to_it_is_left_out_and_said_in_the_owners_words():
    ctx, elements, activity, _ = answered(NoCreditAnswering(fail={"core_response_overview"}))
    assert activity["overview"]["fallback"] == {"reason": "usage"}
    assert next(e for e in elements if e["kind"] == "NOTE")["text"] == OVERVIEW_LOST
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_the_owners_own_run_both_last_steps_lost_is_saved_with_both_notices_and_reopens_as_saved():
    ctx, elements, activity, _ = answered(NoCreditAnswering(
        fail={"core_response_cross_check", "core_response_overview"}))
    assert [e["text"] for e in elements if e["kind"] in ("NOTICE", "NOTE")] == [CROSS_CHECK_LOST, OVERVIEW_LOST]
    assert "DO_FIRST" not in kinds(elements)
    assert turn.validate_activity(activity, ctx, elements) == activity
    assert turn.known_activity(activity)


def test_a_section_lost_to_it_is_a_note_in_its_place_and_the_other_is_answered():
    model = NoCreditAnswering(fail={("D2", 1)})
    ctx, elements, activity, _ = answered(model)
    assert activity["sections"][1]["fallback"] == {"reason": "usage"}
    note = next(e for e in elements if e["kind"] == "FALLBACK")
    assert note["text"].startswith("Not a full answer on Dispute 2: " + USAGE_LIMIT_WORDS + ".")
    row = next(e for e in elements if e["kind"] == "ROW" and e["text"] == "Dispute 2")
    assert row["row"] == {"status": "note", "why": USAGE_LIMIT_WORDS}
    # The overview's writer is told, in the port's neutral words, that the section was not written.
    shown = model.payloads("core_response_overview")[0]["sections_shown"]
    assert {"dispute": "Dispute 2", "not_written_in_full": response_review.UNWRITTEN["usage"]} in shown
    assert turn.validate_activity(activity, ctx, elements) == activity


def test_a_section_whose_review_was_lost_to_it_is_noted_and_says_why_it_was_never_checked():
    ctx, elements, activity, _ = answered(ReviewLostForTheSecond())
    lost = activity["sections"][1]
    assert lost["fallback"] == {"reason": "usage"}
    assert [(entry["step"], entry["why"]) for entry in lost["refused"]] == [("unreviewed", USAGE_LIMIT_WORDS)]
    assert turn.validate_activity(activity, ctx, elements) == activity


@pytest.mark.parametrize("operation", ["core_response_writer", "core_response_review"])
def test_every_section_lost_to_it_saves_nothing_and_raises_it(operation):
    with pytest.raises(UsageLimitReached):
        answered(NoCreditAnswering(fail={operation}))


def test_a_record_cannot_claim_a_loss_that_did_not_happen_or_one_that_is_not_known():
    ctx, elements, activity, _ = answered(Scripted())
    refused(activity, ctx, elements, lambda forged: forged["sections"][1].update(fallback={"reason": "usage"}))
    refused(activity, ctx, elements, lambda forged: forged["sections"][1].update(fallback={"reason": "credit"}))
    refused(activity, ctx, elements, lambda forged: forged.update(cross_check={"unavailable": "credit"}))
