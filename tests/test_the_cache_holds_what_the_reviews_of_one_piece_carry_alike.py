"""The cache holds what the reviews of one piece carry alike (plan AN.31, D15b; owner, 1 Nov 2026: "Yes" to the cache lever).

In the answer stage run of 1 Nov the calls of a wave already read the cache (36% of input): the sections start seconds apart, so only the
first call of each kind wrote the conversation with its papers. What was still read at full price was what the reviews of ONE piece carry
alike beyond that - the research results and the legal passages that lead a review's payload before the draft - 13 of the run's 18 reviews
repeated a piece, each paying again for 35,000 to 130,000 tokens. A further breakpoint after them lets the second and later reviews of a piece
read them cached. The provider allows four breakpoints written in a request; it reads from the first two and the latest fifty. Fakes stand in
for the provider and the models; this pins what the call marks, not what the provider charges.
"""
import json

import pytest

from nm.core_engine import research, response_authorities, response_review, response_writer
from nm.core_engine.calls import TurnCalls
from nm.shared.model_openai_adapter import _user_content
from nm.shared.model_port import Prompt, Tier
from tests.test_core_writer_v13 import unit
from tests.test_each_step_reasons_as_its_work_needs_and_the_papers_are_cached import Echo
from tests.test_model_openai_responses import SCHEMA, adapter
from tests.test_the_answer_takes_up_every_order_and_point_or_says_why import V14, matter
from tests.test_the_review_is_shown_the_chronology import Reviewer
from tests.test_the_writer_is_shown_the_chronology import Writer

pytestmark = pytest.mark.class_a

MARK = {"mode": "explicit"}


def test_a_prompt_marks_longer_and_longer_prefixes_of_its_words_beyond_the_shared_one_or_none():
    user = "x" * 100
    assert Prompt(user=user).cache_also == () and Prompt(user=user, cache_through=10).cache_also == ()
    assert Prompt(user=user, cache_through=10, cache_also=(40,)).cache_also == (40,)
    assert Prompt(user=user, cache_through=10, cache_also=(40, 100)).cache_also == (40, 100)
    for bad in ({"cache_also": (40,)},                                 # nothing shared is marked first
                {"cache_through": 10, "cache_also": (10,)},            # not beyond the shared material
                {"cache_through": 10, "cache_also": (50, 40)},         # not longer and longer
                {"cache_through": 10, "cache_also": (40, 40)},
                {"cache_through": 10, "cache_also": (101,)},           # beyond the words
                {"cache_through": 10, "cache_also": [40]},             # a tuple
                {"cache_through": 10, "cache_also": ("40",)}):
        with pytest.raises(ValueError):
            Prompt(user=user, **bad)


def test_the_transport_marks_each_stretch_and_sends_the_rest_as_it_is():
    marked = lambda text: {"type": "input_text", "text": text, "prompt_cache_breakpoint": MARK}  # noqa: E731
    prompt = Prompt(user="AAAABBBBCC", cache_through=4, cache_also=(8,))
    assert _user_content(prompt, responses=True) == [marked("AAAA"), marked("BBBB"), {"type": "input_text", "text": "CC"}]
    assert _user_content(Prompt(user="AAAABBBB", cache_through=4, cache_also=(8,)), responses=True) == [marked("AAAA"), marked("BBBB")], \
        "nothing left over, no empty part"
    assert _user_content(Prompt(user="AAAABBBB", cache_through=4), responses=True) == [marked("AAAA"), {"type": "input_text", "text": "BBBB"}], \
        "one mark as before"
    assert _user_content(prompt, responses=False) == "AAAABBBBCC", "the chat transport takes no marks"
    port, client = adapter()
    port.structured(Prompt(user='{"a":1,"b":2,"c":3}', system="Stable instructions", cache_through=6, cache_also=(12,)), SCHEMA,
                    Tier.ROUTINE, max_tokens=200)
    (sent,) = client.calls
    assert sent["input"][0]["content"][0]["prompt_cache_breakpoint"] == MARK, "the instructions"
    assert [part.get("prompt_cache_breakpoint") for part in sent["input"][1]["content"]] == [MARK, MARK, None]
    assert "".join(part["text"] for part in sent["input"][1]["content"]) == '{"a":1,"b":2,"c":3}'
    assert sent["prompt_cache_options"] == MARK, "three marks of the four a request may write"


def test_the_stable_material_is_the_shared_material_and_then_the_keys_that_follow_it_in_order():
    payload = {"original_context": {"pages": "p"}, "setting": {"today": "d"}, "papers_chronology": [1], "research": {"a": 1},
               "legal": [2], "draft": {"units": 1}}
    user = json.dumps(payload, ensure_ascii=False)
    shared = response_writer.shared_material(user, payload)
    stable = response_writer.stable_material(user, payload, ("research", "legal"))
    assert 0 < shared < stable < len(user)
    assert user[stable:].startswith(', "draft"') and user[shared:stable].startswith(', "research"')
    assert response_writer.stable_material(user, payload, ("legal", "research")) == 0, "in the order the payload has them"
    assert response_writer.stable_material(user, payload, ("research", "draft")) == 0, "right after one another"
    assert response_writer.stable_material(user, {"setting": 1, "research": 2}, ("research",)) == 0, "it must lead with the conversation"
    assert response_writer.stable_material(user, payload, ("research", "legal")) == stable
    assert response_writer.stable_material(user[:-1] + " ", payload, ("research", "legal")) == stable, "the draft may change"
    assert response_writer.stable_material('{"x": 1}', payload, ("research", "legal")) == 0, "words that do not begin with them"


def draft_of(ctx, record, sources, first_line, contract=V14):
    script = lambda payload: {"units": [unit("summary", first_line, "row_action"),  # noqa: E731
                                        unit("summary", "Have the agreement ready", "row_ready")],
                              "checklist": [], "time_limit_ids": [], "by_when": None}
    return response_writer.write_section(Writer(script), ctx, record, sources, index=0, contract=contract)


def reviewed(ctx, record, sources, draft, contract=response_review.WORDED_CONTRACT):
    reviewer = Reviewer()
    response_review.review(reviewer, ctx, record, sources, draft, research.execution(record),
                           authority_evidence=response_authorities.check(ctx, record, sources, draft), contract=contract)
    return reviewer.seen[0][0]


def test_a_worded_review_marks_the_shared_material_and_then_the_research_and_the_legal_passages_before_the_draft():
    ctx, record, sources = matter()
    first = reviewed(ctx, record, sources, draft_of(ctx, record, sources, "Appeal against the order"))
    second = reviewed(ctx, record, sources, draft_of(ctx, record, sources, "Another line, written after the first was reviewed"))
    (stable,) = first.cache_also
    assert 0 < first.cache_through < stable < len(first.user)
    shared_part, stable_part, changing = first.user[:first.cache_through], first.user[first.cache_through:stable], first.user[stable:]
    assert shared_part.startswith('{"original_context"')
    assert all(f'"{key}"' in stable_part for key in response_review.STABLE_KEYS) and '"complete_draft_proposal"' not in stable_part
    assert changing.startswith(', "complete_draft_proposal"') and "Appeal against the order" in changing
    assert response_review.STABLE_KEYS == ("research_proposal_and_results", "legal_sources")
    # The second review of the piece, of a draft that changed, leads with exactly the same words as far as the mark - which is the point.
    assert first.user != second.user and "Appeal against the order" not in second.user
    assert (second.cache_through, second.cache_also) == (first.cache_through, first.cache_also)
    assert second.user[:second.cache_also[0]] == first.user[:first.cache_also[0]]


def test_an_earlier_review_marks_nothing_and_a_correction_keeps_the_marks_that_still_lead():
    ctx, record, sources = matter()
    earlier = reviewed(ctx, record, sources, draft_of(ctx, record, sources, "Appeal against the order", response_writer.PRESENTED_CONTRACT),
                       response_review.PRESENTED_CONTRACT)
    assert (earlier.cache_through, earlier.cache_also) == (0, ())
    user = json.dumps({"original_context": {"pages": "the papers"}, "research": {"a": 1}, "legal": [1], "draft": {"units": 1}})
    shared = response_writer.shared_material(user, json.loads(user))
    stable = response_writer.stable_material(user, json.loads(user), ("research", "legal"))
    inner = Echo()
    calls = TurnCalls(inner)
    calls.correction = {"operation": "core_response_review", "mismatch": "fix it"}
    calls.structured(Prompt(user=user, operation="core_response_review", cache_through=shared, cache_also=(stable,)), {"type": "object"},
                     Tier.JUDGE, max_tokens=10)
    sent, = inner.prompts
    assert '"correction"' in sent.user and (sent.cache_through, sent.cache_also) == (shared, (stable,)), "the correction joins the end"
