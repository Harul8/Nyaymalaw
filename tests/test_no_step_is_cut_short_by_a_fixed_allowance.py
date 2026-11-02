"""No step's work is cut short by a fixed allowance (plan AN.33, D27; piece 33p).

The owner, 2 Nov 2026: "we should not put any hard limits, unless it may create never ending loop, we never know how complex future
cases can be". Every model call may write as much as its model can - the most the models an advocate may choose write (128,000
tokens), which the adapter lowers for a model that writes less - within the room its whole input leaves of the context the model is
given; a call whose input leaves less than 4,000 tokens is not made. No list a model is asked about is cut to a number. What bounds a
loop stays: the rounds of repair, the trims, the corrections of a turn, the reading again in halves. The papers are invented.
"""
import json

import pytest

from nm.core_engine import reasoning, research
from nm.core_engine.calls import TurnCalls
from nm.shared.model_config import MAX_OUTPUT
from nm.shared.model_port import ContextOverflow, Prompt, Tier, estimate_tokens
from tests.test_core_understanding import Model, unit
from tests.test_model_openai_responses import SCHEMA, FakeSession, adapter

pytestmark = pytest.mark.class_a


def asked(model, user, max_tokens=reasoning.MOST_OUTPUT):
    prompt = Prompt(user=user, system="Stable instruction", operation="core_x")
    TurnCalls(model).structured(prompt, {"type": "object"}, Tier.ROUTINE, max_tokens=max_tokens)
    return model.calls[-1][3]["max_tokens"], estimate_tokens(prompt.system + prompt.user + json.dumps({"type": "object"}))


def test_a_turns_call_may_write_what_its_whole_input_leaves_of_the_context_up_to_the_most_its_model_writes():
    roomy = Model({"units": [unit()]}, budget=1_000_000)
    assert asked(roomy, "Read this.")[0] == reasoning.MOST_OUTPUT
    tight = Model({"units": [unit()]}, budget=60_000)
    written, used = asked(tight, "word " * 40_000)
    assert written == 60_000 - used < reasoning.MOST_OUTPUT, "the room the input leaves"
    assert asked(tight, "Read this.", max_tokens=1_000)[0] == 1_000, "a call that asks for less is given what it asks"
    small, flood = Model({"units": [unit()]}, budget=60_000), "word " * 225_000
    with pytest.raises(ContextOverflow):
        asked(small, flood)
    assert small.calls == [], "a call whose input leaves less than LEAST_ROOM is not made"


def sent(client):
    return client.calls[0].get("max_output_tokens", client.calls[0].get("max_completion_tokens"))


@pytest.mark.parametrize("model, most", [("gpt-6-luna", 128_000), ("gpt-6.1-sol", 128_000), ("gpt-6.1-terra", 128_000),
                                         ("gpt-4.1-mini-2025-04-14", 32_768)])
def test_the_adapter_never_asks_a_model_for_more_than_it_writes_and_a_bounded_session_reserves_that(model, most):
    assert MAX_OUTPUT[model] == most <= reasoning.MOST_OUTPUT
    session = FakeSession()
    port, client = adapter(model=model, budget=session)
    port.structured(Prompt(user="Read this.", system="Stable instruction"), SCHEMA, Tier.ROUTINE, max_tokens=reasoning.MOST_OUTPUT)
    assert sent(client) == most and session.requests[0][1] == most
    plain, client = adapter(model=model)
    plain.structured(Prompt(user="Read this.", system="Stable instruction"), SCHEMA, Tier.ROUTINE, max_tokens=2_000)
    assert sent(client) == 2_000, "a call that asks for less is asked for what it asks"


def test_a_papers_settling_is_asked_about_every_identifier_and_page_no_point_carries():
    # Before D27 at most 20 identifiers and 10 pages were asked about (piece 33e); now every one is.
    pages = [{"page": n, "text": f"Suit No. {7300 + 2 * n} of 1907 and Reference No. {7301 + 2 * n} of 1913. " + "word " * 60}
             for n in range(1, 16)]
    uncovered = research._uncovered({"source": "t1:d1", "name": "papers.pdf", "pages": pages}, [])
    assert len(uncovered["identifiers"]) == 30 and uncovered["pages"] == list(range(1, 16))
    assert uncovered["identifiers"][:2] == [{"identifier": "No. 7302 of 1907", "page": 1}, {"identifier": "No. 7303 of 1913", "page": 1}]
