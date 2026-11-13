"""NM's own rejected request is not an outage (plan AN.52, 52i; D215; the review's F-31; defect shape S10).

A provider that answers 'your request is malformed', 'you are not authorised' or 'no such model' is describing a fault in this
installation's settings or in NM's own code. It reached the engine as an ordinary model error, and the engine's handlers are
written for a service that may be back in a moment. Measured on the code before this piece, through the served application:
rejected at the choice of authorities, or at the overview, the turn answered 200 and saved an answer made without that step;
rejected anywhere else it said 'the AI service could not be reached' and offered a Continue that could never work; and the
rejected request was sent a second time.

Two things, each behind its own line below. (1) The transport gives the rejection its own name; it is still a model error, so
nothing outside a turn changes. (2) At the one door every call of a turn goes through, that name becomes a stop of the turn -
as the advocate's own Stop is - which the engine's handlers for a model error do not catch: the turn stops with a service
notice in code's words, what NM had finished is kept, and Continue works once the installation is put right.

Offline: the served application with stand-in models; no browser; no model call.
"""
from __future__ import annotations

import pytest

from nm.core_engine import turn
from nm.core_engine.calls import OwnRequestRejected, TurnCalls
from nm.core_engine.conversation import stored_chat
from nm.shared import model_transport
from nm.shared.model_port import (ConfigurationError, ContentRefused, ContextOverflow, ModelError, Prompt, ProviderUnavailable,
                                  RateLimited, RequestRejected, Tier, UsageLimitReached)
from tests.test_core_answer_sections import Scripted, scripted_answers
from tests.test_core_served import OWNER, served  # noqa: F401 - served is a fixture

pytestmark = pytest.mark.class_a
SENT = {"message": "Inspect this reported account.", "turn_id": "turn-1"}
SAID_BY_THE_PROVIDER = "Error code: 400 - {'error': {'message': 'Invalid schema for response_format', 'type': 'invalid_request_error'}}"


# ------------------------------------------------------------- (1) the transport names it ---

def _sdk_error(name, message="the provider's own words"):
    """An error as a provider's SDK raises it: told apart by the name of its class."""
    return type(name, (Exception,), {})(message)


@pytest.mark.parametrize("name", ["AuthenticationError", "PermissionDeniedError", "NotFoundError", "BadRequestError",
                                  "UnprocessableEntityError"])
def test_a_request_the_provider_rejects_has_its_own_name_and_is_still_a_model_error(name):
    said = model_transport.normalise_error(_sdk_error(name))
    assert type(said) is RequestRejected
    assert isinstance(said, ConfigurationError) and isinstance(said, ModelError), "so every handler outside a turn is as it was"


@pytest.mark.parametrize("error, kind", [
    (_sdk_error("BadRequestError", "context_length_exceeded: too long"), ContextOverflow),
    (_sdk_error("BadRequestError", "blocked by the content policy"), ContentRefused),
    (_sdk_error("BadRequestError", "insufficient_quota"), UsageLimitReached),
    (_sdk_error("RateLimitError"), RateLimited),
    (_sdk_error("APIConnectionError"), ProviderUnavailable),
    (_sdk_error("InternalServerError"), ProviderUnavailable),
])
def test_what_is_not_a_rejection_of_nms_request_keeps_its_own_name(error, kind):
    assert type(model_transport.normalise_error(error)) is kind


def test_a_fault_in_nms_own_settings_found_before_any_request_is_not_called_a_rejection():
    settings = ConfigurationError("NM_MODEL_PROVIDER is not set")
    assert model_transport.normalise_error(settings) is settings and not isinstance(settings, RequestRejected)


# ------------------------------------------------------------- (2) the turn's door, and the turn ---

class _Model:
    def __init__(self, error):
        self.error, self.asked = error, 0

    def context_budget(self, tier):
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens):
        self.asked += 1
        raise self.error


def _asked_through_the_door(error):
    model = _Model(error)
    calls = TurnCalls(model)
    with pytest.raises(BaseException) as raised:
        calls.structured(Prompt(system="s", user="{}", operation="core_research_pick"), {"type": "object"}, Tier.ROUTINE,
                         max_tokens=100)
    return raised.value, calls, model


def test_at_the_turns_door_a_rejection_becomes_a_stop_that_no_handler_of_a_model_error_catches():
    raised, calls, model = _asked_through_the_door(RequestRejected(SAID_BY_THE_PROVIDER))
    assert type(raised) is OwnRequestRejected and not isinstance(raised, ModelError)
    assert isinstance(raised.__cause__, RequestRejected), "what the provider said is kept as its cause, for the operator"
    assert model.asked == 1
    assert [(call["operation"], call["error"]) for call in calls.calls] == [("core_research_pick", "RequestRejected")], (
        "the rejected call is in the turn's record, by its own name")


@pytest.mark.parametrize("error", [ProviderUnavailable("the service is down"), ConfigurationError("no such tier"),
                                   RateLimited("slow down")])
def test_at_the_turns_door_every_other_model_error_is_itself_as_before(error):
    raised, _calls, _model = _asked_through_the_door(error)
    assert raised is error


def _rejected_at(served, operation):
    scripted = Scripted()
    scripted_answers(served, scripted)
    answering, asked, lifted = served.model.structured, [], []

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == operation and not lifted:
            asked.append(prompt.user)
            raise RequestRejected(SAID_BY_THE_PROVIDER)
        return answering(prompt, schema, tier, **kwargs)
    served.model.structured = structured
    return scripted, asked, lambda: lifted.append(True)


@pytest.mark.parametrize("operation", ["core_research_understand", "core_research_pick", "core_response_writer",
                                       "core_response_review", "core_response_overview"])
def test_wherever_in_a_turn_it_is_rejected_the_turn_stops_with_a_notice_and_never_answers_without_the_step(served, operation):
    _scripted, asked, _lift = _rejected_at(served, operation)
    reply = served.client.post("/api/turn", json=SENT)
    assert reply.status_code == 503, f"rejected at {operation}: {reply.status_code} {reply.text[:300]}"
    detail = reply.json()["detail"]
    assert detail["code"] == "request_rejected" and turn.STOPS["request_rejected"] in detail["why"]
    assert "Invalid schema" not in reply.text and "invalid_request_error" not in reply.text, "the provider's words are the operator's"
    # Two disputes are worked side by side, so two requests of one step may both be out; no one of them is sent twice.
    assert asked and len(asked) == len(set(asked)), "a request the provider rejected is not sent again by the turn"
    assert not served.store.list_for(OWNER).matters or "turns" not in reply.text, "no answer is saved as if the step had been done"


def test_the_stop_is_kept_with_its_words_and_continue_finishes_once_it_is_put_right(served):
    scripted, asked, lift = _rejected_at(served, "core_response_overview")
    reply = served.client.post("/api/turn", json=SENT)
    assert reply.status_code == 503 and reply.json()["detail"]["kept"] is True
    served.app.turn_progress.end(OWNER, "turn-1", "stopped")
    chat_id = stored_chat(OWNER, None, "turn-1")
    pending = served.client.get(f"/api/chats/{chat_id}").json()["pending"]
    assert pending["stopped"]["code"] == "request_rejected"
    assert pending["stopped"]["why"] == turn.STOPS["request_rejected"]
    assert pending["stopped"]["needs"] == turn.STOP_NEEDS["request_rejected"]
    written = len(scripted.payloads("core_response_writer"))
    again = served.client.post("/api/turn/continue", json={"chat_id": chat_id, "turn_id": "turn-1"})
    assert again.status_code == 503 and again.json()["detail"]["code"] == "request_rejected", "the same while it stands"
    served.app.turn_progress.end(OWNER, "turn-1", "stopped")
    lift()
    done = served.client.post("/api/turn/continue", json={"chat_id": chat_id, "turn_id": "turn-1"})
    assert done.status_code == 200 and done.json()["committed"] == "committed", done.text
    assert len(scripted.payloads("core_response_writer")) == written, "the sections finished are not written again"
    assert len(asked) == 2, "asked once at first, and once by the Continue pressed while the rejection stood"


def test_an_outage_is_still_an_outage(served):
    """The neighbour: a service that could not be reached is said as that, with its own Continue, as before."""
    scripted = Scripted()
    scripted_answers(served, scripted)
    answering = served.model.structured

    def structured(prompt, schema, tier, **kwargs):
        if prompt.operation == "core_response_writer":
            raise ProviderUnavailable("connection reset")
        return answering(prompt, schema, tier, **kwargs)
    served.model.structured = structured
    reply = served.client.post("/api/turn", json=SENT)
    assert reply.status_code == 503 and reply.json()["detail"]["code"] == "response_unavailable"
