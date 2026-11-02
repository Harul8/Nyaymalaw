"""A call that shares a cached opening another call began writing gives it a head start (plan AN.34, D29; piece 34d).

The probes of 2 Nov 2026 (invented text): of four calls started together on one fresh opening, two wrote it and two read it; started
two seconds after the first, every one read it - and a call read an opening only where its effort, its answer's schema and its
instructions were those of the call that wrote it. A request whose opening another request began writing less than two seconds
before - the same model, effort, answer, instructions and first marked part - waits the rest of them, or until that request is
answered, whichever comes sooner; any other request is not held.
"""
import threading
import time

import pytest

from nm.shared import model_openai_adapter
from nm.shared.model_port import Prompt, Tier
from tests.test_model_openai_responses import SCHEMA, adapter

pytestmark = pytest.mark.class_a
OTHER = {"type": "object", "additionalProperties": False, "required": ["rent"], "properties": {"rent": {"type": "string"}}}


@pytest.fixture
def leads(monkeypatch):
    monkeypatch.setattr(model_openai_adapter, "LEAD_SECONDS", 1.0)
    monkeypatch.setattr(model_openai_adapter, "_LEADS", {})


def sent_times(client, answering=0.0):
    """When each request is sent; each is answered `answering` seconds after."""
    times, create = [], client.responses.create

    def timed(**kwargs):
        times.append(time.monotonic())
        time.sleep(answering)
        return create(**kwargs)
    client.responses.create = timed
    return times


def ask(port, opening, question="Question?", effort=None, schema=SCHEMA):
    port.structured(Prompt(user=opening + question, system="Stable instruction", cache_through=len(opening), effort=effort), schema,
                    Tier.ROUTINE, max_tokens=200)


def together(*asks):
    threads = [threading.Thread(target=one) for one in asks]
    for thread in threads:
        thread.start()
        time.sleep(0.05)
    for thread in threads:
        thread.join()


def test_a_request_that_shares_an_opening_another_began_writing_waits_until_that_one_is_answered(leads):
    port, client = adapter(model="gpt-6-luna")
    times = sent_times(client, answering=0.3)
    opening = "The same opening. " * 20
    together(lambda: ask(port, opening), lambda: ask(port, opening))
    assert len(times) == 2 and 0.25 <= times[1] - times[0] < 0.9, "the second is sent once the first is answered, not before"
    slow, client = adapter(model="gpt-6-luna")
    times = sent_times(client, answering=1.5)
    opening = "Another shared opening. " * 20
    together(lambda: ask(slow, opening), lambda: ask(slow, opening))
    assert 0.9 <= times[1] - times[0] < 1.4, "and never waits longer than the head start"


def test_a_request_with_another_opening_no_mark_or_a_late_start_is_not_held(leads):
    port, client = adapter(model="gpt-6-luna")
    times = sent_times(client)
    started = time.monotonic()
    ask(port, "One opening. " * 20)
    ask(port, "Another opening. " * 20)
    port.structured(Prompt(user="Nothing marked.", system="Stable instruction"), SCHEMA, Tier.ROUTINE, max_tokens=200)
    ask(port, "One opening. " * 20, "Asked again once the first was answered?")
    assert len(times) == 4 and times[-1] - started < 0.3, "none waits: another opening, no mark, or the first already answered"


def test_a_request_at_another_effort_or_with_another_answer_does_not_wait_for_an_opening_it_could_not_read(leads):
    port, client = adapter(model="gpt-6-luna")
    times = sent_times(client, answering=0.3)
    opening = "An opening sent three ways. " * 20
    together(lambda: ask(port, opening, effort="medium"), lambda: ask(port, opening, effort="high"),
             lambda: ask(port, opening, effort="medium", schema=OTHER))
    assert len(times) == 3 and max(times) - min(times) < 0.25, "each is the first to write the opening it can read"
