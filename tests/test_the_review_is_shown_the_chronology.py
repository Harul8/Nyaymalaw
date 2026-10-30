"""The independent review is shown the papers' chronology (plan AN.27, P12).

The writer of a section is shown what the papers record, event by event (P11); the independent review of that section now sees the
same events, with their papers, pages and whether their words were located, and is told to judge the piece against them: whether it
leaves out an order, direction or proceeding still pending that bears on it, states a date or event neither the chronology nor the
pages bear out, or gives a party's allegation as established. Only the review that judges a piece written for the advocate (v11) is
shown them, and not the overview, which rests on the sections. The papers are synthetic.
"""
import json

import pytest

from nm.core_engine import research, response_authorities, response_review, response_writer
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage
from tests.test_the_writer_is_shown_the_chronology import Writer, papers, section

pytestmark = pytest.mark.class_a


class Reviewer:
    """A review that finds nothing and keeps what it was shown."""

    def __init__(self):
        self.seen = []

    def context_budget(self, tier):
        return 1_000_000

    def structured(self, prompt, schema, tier, **kwargs):
        self.seen.append((prompt, json.loads(prompt.user)))
        found = {"misleading": [], "could_be_better": [], **({"keep_shown": []} if "keep_shown" in schema["properties"] else {})}
        return ModelResult(None, found, tier, "synthetic", "fixture", Usage(1, 1, 0), 0, completion=Completion.COMPLETE)


def earlier(payload):
    return {"units": [{"kind": "summary", "text": "In short.", "uses": []}], "checklist": [], "time_limit_ids": []}


def reviewed(contract, written=response_writer.PRESENTED_CONTRACT):
    ctx, record, sources = papers()
    draft = response_writer.write_section(Writer(section if written == response_writer.PRESENTED_CONTRACT else earlier),
                                          ctx, record, sources, index=0, contract=written)
    model = Reviewer()
    response_review.review(model, ctx, record, sources, draft, research.execution(record),
                           authority_evidence=response_authorities.check(ctx, record, sources, draft), contract=contract)
    return model.seen[0], record


def test_the_review_of_a_section_is_shown_the_events_the_writer_was_shown():
    (prompt, payload), record = reviewed(response_review.PRESENTED_CONTRACT)
    shown = payload["papers_chronology"]
    assert [e["id"] for e in shown] == [e["id"] for e in record["plan"]["proposal"]["chronology"]]
    assert set(shown[0]) == {"id", "date", "kind", "what", "said_by", "paper", "pages", "cite", "located"}
    assert payload["original_context"]["documents"]
    assert all(e["cite"] and all(c.startswith("DOC") for c in e["cite"]) for e in shown if e["located"])
    assert any(not e["located"] and e["cite"] == [] for e in shown)
    assert prompt.system == response_review.SYSTEM_V11


def test_the_earlier_review_is_shown_what_it_always_was():
    (prompt, payload), _ = reviewed(response_review.MISLEADS_CONTRACT, written=response_writer.SECTION_CONTRACT)
    assert "papers_chronology" not in payload and prompt.system == response_review.SYSTEM_V10
    assert "papers_chronology" not in response_review.SYSTEM_V10


def test_the_prompt_says_how_to_judge_against_the_chronology():
    prompt = " ".join(response_review.SYSTEM_V11.split())
    for part in ("When papers_chronology is given", "leave out an order, direction, transaction or proceeding still pending",
                 "naming the events by their IDs", "states a date or event that neither the chronology nor the pages bear out",
                 "gives what a party alleges as established", "An event whose located is false could not be found on its page and supports nothing",
                 "List only what you find"):
        assert part in prompt, part
