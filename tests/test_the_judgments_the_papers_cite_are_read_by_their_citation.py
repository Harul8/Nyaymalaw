"""The judgments the papers and the advocate's messages cite are read by their citation (plan AN.35, D30 A1 and D33; research v16;
piece 35e).

The owner, 2 Nov 2026: the research should pull "the relevant sections as well as relevant passages from the judgments" for each
dispute, with completeness and relevance; agreed (D30 A1): a judgment the papers cite is looked up by name in the held law, and
what is named and not held is said. Code finds each citation (citation_contracts) and looks it up once in the held case index by
its exact keys only; each dispute's further call is shown them, with where each is cited and how our library stands on it, and
chooses for each question the held ones a lawyer must read; code reads each chosen judgment once. A near name never stands for
the judgment cited; the lookup is kept and never made again on reopening. The citations and judgments are invented.
"""
import re
from copy import deepcopy

import pytest

from nm.core_engine import answer_sources, citations, research, response_writer
from nm.core_engine.retrieval import HybridSearcher
from tests.test_core_research import Model, operations, proposal
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection

pytestmark = pytest.mark.class_a

MESSAGE = ("Find the applicable law. The other side relies on (1996) 8 SCC 417 and on AIR 1958 SC 913; "
           "I rely on (1996) 8 SCC 417 too.")


class Index:
    """The held case index: the first citation leads to one held judgment, the second to none."""

    def __init__(self, broken=False):
        self.broken, self.asked = broken, []

    def judgments_for(self, keys):
        self.asked.append(keys)
        if self.broken:
            raise citations.IndexUnavailable("the case index is absent (identity.db)")
        if "19968SCC417" not in keys:
            return {}
        return {"cited case": {"case_id": "cited case", "source_file": "x.txt", "court": "Supreme Court of India", "year": 1996,
                               "title": "Imagined Traders v Imagined Mills", "decided_on": None, "bench": None,
                               "petitioner": None, "respondent": None, "held_keys": ["19968SCC417"],
                               "matched_keys": ["19968SCC417"]}}


def library():
    provisions = Collection()
    provisions.rerank = lambda pairs, *, anchors=None: [1.0] * len(pairs)
    held = Collection("judgment")
    held.rows = {p: {"chunk_id": f"j{p}", "full_text": f"Paragraph {p}:\n the court holds rule {p}.", "case_id": case,
                     "case_name": case.title(), "paragraph_num": str(p + 1), "court": "Supreme Court of India",
                     "year": "1996", "cited_by_count": 10, "paragraph_type": "reasoning"}
                 for p, case in enumerate(["found case", "cited case", "cited case"])}
    held.lexical = held.semantic = lambda query, depth: [0]
    held.rerank = lambda pairs, *, anchors=None: [1.0] * len(pairs)
    held.judgment_paragraphs = lambda case_id: [(p, deepcopy(row)) for p, row in held.rows.items() if row["case_id"] == case_id]
    return HybridSearcher({"provision": provisions, "judgment": held})


def read_the_cited(user):
    label = re.search(r"^(Q\d+): ", user, re.M).group(1)
    named = re.findall(r"^  (CJ\d+) ", user, re.M)
    return {"questions": [{"question_id": label, "missing": "", "sections": [], "phrases": [], "cited": named}]}


def researched(model, index):
    ctx = context(MESSAGE)
    plan = research.accept(proposal(1, 1), ctx)
    return ctx, plan, research.retrieve(plan, library(), ctx, model=model, case_index=index)


def test_each_citation_is_found_once_with_where_it_is_made_and_looked_up_by_its_exact_keys():
    ctx = context(MESSAGE)
    made = research._citations_in(ctx)
    assert [(entry["id"], entry["citation"], entry["keys"]) for entry in made] == [
        ("CJ1", "(1996) 8 SCC 417", ["19968SCC417"]), ("CJ2", "AIR 1958 SC 913", ["AIR1958SC913", "AIR1958SUPREMECOURT913"])]
    assert made[0]["where"] == [ctx["latest"]["source_id"]], "cited twice in one message, it is one citation"
    index = Index()
    cited = research.cited_judgments(ctx, index)
    assert [(entry["state"], entry["judgment"]) for entry in cited] == [
        ("found", {"case_id": "cited case", "title": "Imagined Traders v Imagined Mills", "court": "Supreme Court of India",
                   "year": 1996}),
        ("not_held", None)]
    assert index.asked == [("19968SCC417",), ("AIR1958SC913", "AIR1958SUPREMECOURT913")]
    unread = research.cited_judgments(ctx, Index(broken=True))
    assert {entry["state"] for entry in unread} == {"unavailable"} and all(entry["reason"] for entry in unread)
    assert {entry["state"] for entry in research.cited_judgments(ctx, None)} == {"unavailable"}


def test_the_further_call_is_shown_the_cited_judgments_and_the_held_ones_it_names_are_read_once():
    model = Model(further=read_the_cited)
    ctx, plan, record = researched(model, Index())
    shown = next(prompt.user for prompt in model.calls if prompt.operation == "core_research_further")
    assert ("CJ1 (1996) 8 SCC 417 - Imagined Traders v Imagined Mills (Supreme Court of India, 1996): held; cited in the "
            "advocate's message.") in shown
    assert "CJ2 AIR 1958 SC 913: not held in our library; cited in the advocate's message." in shown
    further = record["further"]["D1"]
    assert [entry["state"] for entry in further["cited"]] == ["found", "not_held"]
    # The held one is read, whole; the one not held is never read, nor is any judgment twice.
    assert [entry["case_id"] for entry in further["cited_read"]] == ["cited case"]
    assert further["cited_read"][0]["whole"] is True and len(further["cited_read"][0]["read"]) == 2
    assert [entry["case_id"] for entry in research.judgments_read(record)["D1"]] == ["found case", "cited case"]
    sources = answer_sources.build(ctx, record)
    assert sum(row["kind"] == "judgment" and row["source_identity"]["case_id"] == "cited case" for row in sources.values()) == 2
    # The writer is told how the library stands on each citation.
    told = response_writer._research_context(record, None)["cited_in_the_papers"]
    assert told == [{"citation": "(1996) 8 SCC 417", "held": "held",
                     "judgment": "Imagined Traders v Imagined Mills (Supreme Court of India, 1996)"},
                    {"citation": "AIR 1958 SC 913", "held": "not held in our library"}]
    assert "never that the judgment does not exist" in " ".join(response_writer.SYSTEM_V15.split())
    # Replayed exactly, without the index; a changed lookup or a judgment not chosen is refused.
    assert research.validate(record, plan, ctx) == record
    for change in (lambda f: f["cited"][0].update(where=["somewhere else"]),
                   lambda f: f["cited"][1].update(state="found", judgment={"case_id": "x", "title": "", "court": "", "year": 1}),
                   lambda f: f["cited_read"].clear(),
                   lambda f: f["proposal"]["questions"][0].update(cited=[])):
        changed = deepcopy(record)
        change(changed["further"]["D1"])
        with pytest.raises(ValueError):
            research.validate(changed, plan, ctx)


def test_a_judgment_the_dispute_already_reads_is_not_read_again_and_one_not_named_is_not_read():
    def name_none(user):
        return {"questions": [{"question_id": re.search(r"^(Q\d+): ", user, re.M).group(1), "missing": "", "sections": [],
                               "phrases": [], "cited": []}]}
    ctx, plan, record = researched(Model(further=name_none), Index())
    assert record["further"]["D1"]["cited_read"] == [] and len(record["further"]["D1"]["cited"]) == 2
    assert research.validate(record, plan, ctx) == record
    cases = research._cited_cases({"questions": [{"question_id": "Q1", "cited": ["CJ1", "CJ1", "CJ2", "CJ9"]}]}, {"w": "Q1"},
                                  record["further"]["D1"]["cited"], skip=set())
    assert cases == ["cited case"], "named twice, read once; one not held, or no such number, never read"
    assert research._cited_cases({"questions": [{"question_id": "Q1", "cited": ["CJ1"]}]}, {"w": "Q1"},
                                 record["further"]["D1"]["cited"], skip={"cited case"}) == []


def test_a_further_call_shown_no_citation_is_told_of_none_and_keeps_none():
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(1, 1), ctx)
    model = Model()
    record = research.retrieve(plan, library(), ctx, model=model)
    assert record["further"]["D1"]["cited"] == [] and record["further"]["D1"]["cited_read"] == []
    shown = next(prompt.user for prompt in model.calls if prompt.operation == "core_research_further")
    assert "Judgments the papers" not in shown
    assert "cited_in_the_papers" not in response_writer._research_context(record, None)
    assert operations(model).count("core_research_further") == 1 and research.validate(record, plan, ctx) == record
