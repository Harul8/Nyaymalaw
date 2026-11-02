"""The research calls that are shown the file open alike, so that the cache keeps the file once (plan AN.34, D29; piece 34b).

The owner, 2 Nov 2026, of a run whose cost was mostly input: "why is this not cached?" Each paper's reading showed the rest of the
file without its own pages, so no two readings opened alike, and research's calls carried no cache marks. Now every call shown the
file opens with the same text - the advocate's messages and the whole file - marked where it ends, before the pages it reads for. A
call reads a cached opening only where its effort, its answer's schema and its instructions are those of the call that wrote it (the
second probe of that day), so the calls of one step read it: the readings, the second passes among themselves, the settling calls,
the transactions' readings. A second pass cannot read its reading's prompt from the cache - it reasons harder than its reading - so
nothing marks it for that (34a, dropped). The papers are invented.
"""
import threading

import pytest

from nm.core_engine import research
from tests.test_the_chronology_of_each_document import SCRIPT, Reading, papers
from tests.test_the_plan_records_the_chronology import Beside, bundle

pytestmark = pytest.mark.class_a


class Kept:
    """Any model, keeping every prompt it is asked."""

    def __init__(self, inner):
        self.inner, self.prompts, self.lock = inner, [], threading.Lock()

    def context_budget(self, tier):
        return self.inner.context_budget(tier)

    def structured(self, prompt, schema, tier, **kwargs):
        with self.lock:
            self.prompts.append(prompt)
        return self.inner.structured(prompt, schema, tier, **kwargs)


def opened(prompt):
    return prompt.user[:prompt.cache_through]


def test_every_reading_and_second_pass_opens_with_the_whole_file_marked_where_it_ends():
    kept = Kept(Reading(SCRIPT))
    research.chronology_of(kept, papers())
    readings = [p for p in kept.prompts if p.system == research.CHRONOLOGY_V14 and research.SECOND_PASS[:40] not in p.user]
    second = [p for p in kept.prompts if research.SECOND_PASS[:40] in p.user]
    settling = [p for p in kept.prompts if p.system == research.SETTLE_EVENTS]
    assert len(readings) == len(second) == 2 and len(settling) == 1
    shared = opened(readings[0])
    assert shared and all(opened(p) == shared for p in readings), "every reading opens with the same text"
    assert shared.endswith("The pages you read for:\n") and all(
        f'Paper "{name}", page {number}:' in shared for name in ("deed.pdf", "order.pdf") for number in (1, 2)), "the whole file"
    assert all(p.cache_also == () for p in readings + second), "only the opening is kept"
    assert all(any(again.user.startswith(p.user) for p in readings) and opened(again) == shared for again in second), (
        "a second pass repeats its reading, and opens as every reading does")
    file_part = shared[:shared.index("\n\nThe pages you read for:")]
    (settle,) = settling
    assert opened(settle) == file_part + "\n\nThe pages of the paper being checked:\n" and settle.cache_also == ()


def test_the_transactions_readings_open_alike_and_keep_no_more_than_the_opening():
    kept = Kept(Beside())
    research.transfers_of(kept, bundle())
    readings = [p for p in kept.prompts if p.system == research.TRANSACTIONS_V13]
    assert len(readings) == 2 and opened(readings[0]) == opened(readings[1]) != ""
    assert all(p.cache_also == () for p in readings)


def test_a_file_too_large_to_show_marks_nothing(monkeypatch):
    monkeypatch.setattr(research, "WHOLE_FILE_TOKENS", 1)
    kept = Kept(Reading(SCRIPT))
    research.chronology_of(kept, papers())
    readings = [p for p in kept.prompts if p.system == research.CHRONOLOGY_V14 and research.SECOND_PASS[:40] not in p.user]
    second = [p for p in kept.prompts if research.SECOND_PASS[:40] in p.user]
    assert readings and second and all("The whole file" not in p.user and (p.cache_through, p.cache_also) == (0, ())
                                        for p in readings + second), "a call shown only its own pages shares nothing to keep"


def test_the_readings_are_told_the_whole_file_comes_first_with_their_own_pages_among_it():
    for prompt in (research.CHRONOLOGY_V14, research.TRANSACTIONS_V13):
        assert ("the whole file comes first, page by page under each paper's name - the pages you read for among them - and the pages "
                "you read for again last") in prompt
        assert "The file is there so that you know what the matter is about" in prompt and "rest of the file" not in prompt
