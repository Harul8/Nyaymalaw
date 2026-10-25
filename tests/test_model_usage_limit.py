"""An exhausted provider account is named, never retried and kept in the record (owner decision
P51, 25 Oct 2026; plan AN.11 piece 1).

The provider answered the owner's own run with a 429 saying the account had no credits left; NM
took it for a rate limit, retried it for about a second and a half and then said the AI service
did not respond. These tests shape that answer as the installed SDK does and as the other
providers and streams may, offline and free. They do not call a provider; the one real call is
the live check recorded on AN.11.
"""
import json
import re

import httpx
import openai
import pytest

from nm.core_engine.calls import TurnCalls
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import (
    USAGE_LIMIT_MESSAGE, USAGE_LIMIT_WORDS, ModelError, Prompt, RateLimited, Tier, UsageLimitReached,
)
from nm.shared.model_transport import normalise_error, request_with_retries
from tests.test_model_port_contract import SCHEMA, _config, _FakeOpenAI

pytestmark = pytest.mark.class_a

#: The body the provider sent on 25 Oct 2026, word for word.
NO_CREDIT = {"message": "You have no credits remaining. Add credits to continue using the API at "
                        "https://platform.openai.com/settings/organization/billing/.",
             "type": "insufficient_quota", "param": None, "code": "credit_balance_exhausted"}


def sdk_error(cls, status, body):
    """An error built as the installed SDK builds one from a provider's answer."""
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                              json={"error": body})
    return cls(f"Error code: {status} - {json.dumps({'error': body})}", response=response, body=body)


def shaped(name, **attributes):
    return type(name, (Exception,), attributes)("the provider said no")


#: Every way a provider or a stream is known or likely to say it, each a different place to look.
NO_CREDIT_SHAPES = {
    "the SDK's own 429, as the provider sent it": sdk_error(openai.RateLimitError, 429, NO_CREDIT),
    "the SDK's bad request for a monthly limit": sdk_error(openai.BadRequestError, 400, {
        "message": "Billing hard limit has been reached", "type": "invalid_request_error",
        "code": "billing_hard_limit_reached"}),
    "a rate limit that carries the code": shaped("RateLimitError", status_code=429, code="credit_balance_exhausted"),
    "a rate limit that carries the type": shaped("RateLimitError", status_code=429, type="insufficient_quota"),
    "a rate limit with the code only in its body": shaped("RateLimitError", status_code=429,
                                                          body={"error": {"code": "insufficient_quota"}}),
    "a server error that carries the code": shaped("APIStatusError", status_code=503, code="insufficient_quota"),
    "a stream's error as text": RuntimeError("429 rate limit: You exceeded your current quota (insufficient_quota)"),
}


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr("nm.shared.model_transport.time.sleep", lambda seconds: None)


@pytest.mark.parametrize("failure", NO_CREDIT_SHAPES.values(), ids=NO_CREDIT_SHAPES.keys())
def test_a_provider_with_no_credit_left_is_named_and_not_called_again(failure):
    calls = []

    def answered():
        calls.append(1)
        raise failure
    with pytest.raises(UsageLimitReached) as caught:
        request_with_retries(answered)
    assert calls == [1] and caught.value.retries == 0
    assert not isinstance(caught.value, RateLimited)


def test_the_openai_adapter_gives_the_providers_real_answer_one_call_and_its_own_name():
    client = _FakeOpenAI(fail_times=99, exc=sdk_error(openai.RateLimitError, 429, NO_CREDIT))
    with pytest.raises(UsageLimitReached):
        OpenAIModelAdapter(_config(), client=client).structured(Prompt(user="q"), SCHEMA, Tier.ROUTINE)
    assert len(client.calls) == 1


def test_a_rate_limit_that_is_only_that_is_still_retried_as_before():
    limited = sdk_error(openai.RateLimitError, 429, {
        "message": "Rate limit reached for the model on tokens per min (TPM)", "type": "tokens",
        "code": "rate_limit_exceeded"})
    assert isinstance(normalise_error(limited), RateLimited)
    calls = []

    def answered():
        calls.append(1)
        raise limited
    with pytest.raises(RateLimited):
        request_with_retries(answered)
    assert len(calls) == 3


def test_a_programming_fault_is_never_taken_for_an_account_with_no_credit():
    fault = ValueError("insufficient_quota is only a word here")
    assert normalise_error(fault) is fault


def test_a_turns_call_record_names_the_failure():
    """The record keeps the cause by name, with no message and no private data."""
    class Exhausted:
        def context_budget(self, tier):
            return 100_000

        def structured(self, prompt, schema, tier, **kwargs):
            raise UsageLimitReached("You have no credits remaining.")
    calls = TurnCalls(Exhausted())
    with pytest.raises(ModelError):
        calls.structured(Prompt(user="q", operation="core_response_writer"), SCHEMA, Tier.ROUTINE, max_tokens=100)
    assert [(call["operation"], call["error"]) for call in calls.calls] == [
        ("core_response_writer", "UsageLimitReached")]


def test_the_words_an_advocate_is_told_are_one_message_in_two_forms():
    plain = lambda text: re.sub(r"[^a-z]+", " ", text.lower()).split()  # noqa: E731
    assert plain(USAGE_LIMIT_MESSAGE) == plain(USAGE_LIMIT_WORDS)
    assert USAGE_LIMIT_MESSAGE == ("You have run out of your usage limits. "
                                   "Please upgrade to continue accessing NM.")
