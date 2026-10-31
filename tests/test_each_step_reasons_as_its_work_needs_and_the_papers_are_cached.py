"""Each step reasons as its work needs, and the papers every call of a kind carries are marked for the cache (plan AN.28, stage 6).

Every call reasoned at one setting, and 1.5% of the reviewed turn's input was read from the cache: only each call's instructions
were marked for reuse, never the conversation with its papers that every writer, review and second look carries alike. The port
now carries a call's effort and where its shared material ends; the OpenAI transport sends both; each step asks the effort its work
needs - judgement at medium, a second look a level above, a large file a level higher. Fakes stand in for the provider.
"""
import json

import pytest

from nm.core_engine import page_reading, research, response_writer
from nm.core_engine.calls import TurnCalls
from nm.shared.model_port import EFFORTS, Prompt, Tier
from tests.test_model_openai_responses import SCHEMA, adapter

pytestmark = pytest.mark.class_a


def test_a_prompt_carries_an_effort_and_a_shared_prefix_or_neither():
    assert EFFORTS == ("low", "medium", "high")
    prompt = Prompt(user="papers then task", effort="high", cache_through=6)
    assert (prompt.effort, prompt.cache_through) == ("high", 6)
    assert (Prompt(user="words").effort, Prompt(user="words").cache_through) == (None, 0)
    for bad in ({"effort": "extreme"}, {"cache_through": 99}, {"cache_through": -1}):
        with pytest.raises(ValueError):
            Prompt(user="words", **bad)


def test_the_transport_sends_a_calls_effort_and_marks_its_shared_material_for_the_cache():
    port, client = adapter()
    shared = '{"original_context":{"pages":"…"}'
    port.structured(Prompt(user=shared + ',"task":"write"}', system="Stable instructions", effort="high",
                           cache_through=len(shared)), SCHEMA, Tier.ROUTINE, max_tokens=200)
    port.structured(Prompt(user="plain words", system="Stable instructions"), SCHEMA, Tier.ROUTINE, max_tokens=200)
    marked, plain = client.calls
    assert marked["reasoning"] == {"effort": "high"} and plain["reasoning"] == {"effort": "low"}, "else the release's own"
    assert marked["input"][1]["content"] == [
        {"type": "input_text", "text": '{"original_context":{"pages":"…"}', "prompt_cache_breakpoint": {"mode": "explicit"}},
        {"type": "input_text", "text": ',"task":"write"}'}]
    assert plain["input"][1]["content"] == "plain words", "nothing marked, the words as before"


class Echo:
    def __init__(self):
        self.prompts = []

    def context_budget(self, tier):
        return 1_000_000

    def structured(self, prompt, schema, tier, *, max_tokens):
        from nm.shared.model_port import ModelResult, Usage
        self.prompts.append(prompt)
        return ModelResult(None, {"answer": "supported"}, tier, "synthetic", "fixture", Usage(1, 1, 0), 0)


def test_a_correction_keeps_the_calls_effort_and_its_shared_material_where_that_still_leads():
    inner = Echo()
    calls = TurnCalls(inner)
    user = json.dumps({"original_context": {"pages": "the papers"}, "task": "write"})
    shared = response_writer.shared_material(user, json.loads(user))
    assert user[:shared] == '{"original_context": {"pages": "the papers"}'
    calls.correction = {"operation": "core_response_writer", "mismatch": "fix it"}
    calls.structured(Prompt(user=user, operation="core_response_writer", effort="medium", cache_through=shared), SCHEMA,
                     Tier.ROUTINE, max_tokens=10)
    sent, = inner.prompts
    assert (sent.effort, sent.cache_through) == ("medium", shared) and '"correction"' in sent.user
    assert response_writer.shared_material('{"task": 1}', {"task": 1}) == 0, "a payload that does not open with them marks none"


def test_each_step_asks_the_effort_its_work_needs_and_a_large_file_a_level_more():
    assert [research._effort(step, "short") for step in ("understand", "check", "revise", "chronology", "transfers", "connections",
                                                           "chronology_check", "transfers_check", "connections_check", "phrases",
                                                           "pick")] == [
        "medium", "medium", "medium", "medium", "medium", "medium", "high", "high", "high", None, None]
    large = "word " * (research.LARGE_FILE_TOKENS * 2)
    assert (research._effort("chronology", large), research._effort("chronology_check", large),
            research._effort("pick", large)) == ("high", "high", None), "never above high; the measured steps stay as they were"
    assert (response_writer.WRITING_EFFORT, response_writer.SECOND_LOOK_EFFORT) == ("medium", "high")


def test_the_second_reading_of_a_page_and_the_look_again_at_copies_reason_at_medium():
    seen = []

    class Pages:
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            from nm.shared.model_port import ModelResult, Usage
            seen.append(prompt)
            data = ({"figures": []} if prompt.operation == page_reading.RELOOK_OPERATION else
                    {"text": "A clear page." if "Your first reading:" in prompt.user else "[illegible] [illegible] [illegible]",
                     "readable": "all", "note": ""})
            return ModelResult(None, data, tier, "synthetic", "page-model-1", Usage(1, 1, 0), 0)
    page_reading.read_page(Pages(), "deed.pdf", 1, b"\xff\xd8\xff")
    page_reading.relook(Pages(), {"name": "a.pdf", "number": 1, "image": b"\xff\xd8\xff", "text": "6.06"},
                        {"name": "b.pdf", "number": 1, "image": b"\xff\xd8\xff", "text": "6.16"}, [])
    assert [prompt.effort for prompt in seen] == [None, "medium", "medium"]


def test_the_shared_material_reaches_as_far_as_the_payload_leads_with_what_every_call_carries_alike():
    payload = {"original_context": {"pages": "p"}, "setting": {"today": "d"}, "papers_chronology": [1], "coverage": [2],
               "this_part": {"part": 1}}
    user = json.dumps(payload, ensure_ascii=False)
    shared = response_writer.shared_material(user, payload)
    assert user[:shared] == json.dumps({key: payload[key] for key in list(payload)[:4]}, ensure_ascii=False)[:-1]
    assert response_writer.shared_material(json.dumps({"setting": 1}), {"setting": 1}) == 0, "it must lead with the conversation"
