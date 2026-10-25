"""A turn when the provider's account has no credit left (owner decision P51, 25 Oct 2026; plan
AN.11). The scripted model's failure is the provider's 'no credit' answer instead of an outage;
what the turn does with it is wiring evidence, as the scripted turns are.
"""
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
