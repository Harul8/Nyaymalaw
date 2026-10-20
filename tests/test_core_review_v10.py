"""Review v10 (owner decision P29, 20 Oct 2026): a piece's review says which statements would
mislead the advocate and what could be better; code keeps what it can use of it, sets its slips
aside saying why, and replays its admission from the review's own output."""
import json
from copy import deepcopy

import pytest

from nm.core_engine import answer_sources, response_authorities, response_review, response_writer, turn
from nm.shared.model_port import ModelResult, SchemaViolation, Usage
from nm.shared.budget_contracts import Completion
from tests.test_core_response_writer import two_disputes

pytestmark = pytest.mark.class_a

LIMITS = {"worked_out": [{"what": "File the complaint"}], "not_assessed": [{"what": "Appeal"}]}


def piece():
    """A section of the two-dispute matter, with what its review is bound to."""
    ctx, record, sources = two_disputes()
    draft = response_writer.accept({"units": [{"kind": "summary", "text": "In short.", "uses": []},
                                              {"kind": "next_step", "text": "A step.", "uses": []}],
                                    "checklists": [{"checklist": [], "time_limit_ids": []}]}, ctx, sources,
                                   contract=response_writer.SECTION_CONTRACT, parts=[{"dispute_id": "D1", "units": 2}],
                                   section=1)
    authorities = response_authorities.check(ctx, record, sources, draft)
    return ctx, record, sources, draft, authorities


def admitted(returned):
    ctx, record, sources, draft, authorities = piece()
    deps = response_review._dependencies(ctx, record, sources, draft, turn.execution_record(record),
                                         authority_evidence=authorities, time_limits=LIMITS,
                                         contract=response_review.MISLEADS_CONTRACT)
    return response_review._accept_v10(returned, deps), sources


def misleading(kind="unsupported", where=("U2",), evidence=(), why="It says more than the message."):
    return {"kind": kind, "where": list(where), "evidence": list(evidence), "why": why}


def test_what_misleads_and_what_could_be_better_are_admitted_with_their_places():
    record, sources = admitted({"misleading": [misleading(evidence=[{"source_id": "M1", "quote": "applicable law"}])],
                                "could_be_better": [{"where": ["U1"], "what": "Say which court hears it."}]})
    message = next(identity for identity, row in sources.items() if row["kind"] == "account")
    assert record["contract"] == "core_response_review_v10" and record["accepted"] is False
    assert record["proposal"] == {"findings": [
        {"category": "grounding", "unit_ids": ["t2:s1b2"], "limits": [], "mismatch": "It says more than the message.",
         "sources": [{"source_id": message, "quote": "applicable law"}]},
        {"category": "better", "unit_ids": ["t2:s1b1"], "limits": [], "sources": [],
         "mismatch": "Say which court hears it."}], "set_aside": []}
    assert record["returned"]["could_be_better"][0]["where"] == ["U1"]  # the review's own words, kept
    nothing, _ = admitted({"misleading": [], "could_be_better": []})
    assert nothing["accepted"] is True and nothing["proposal"]["findings"] == []


@pytest.mark.parametrize("kind,category", list(response_review.KINDS.items()))
def test_each_kind_of_misleading_statement_is_owned_by_its_gate(kind, category):
    record, _ = admitted({"misleading": [misleading(kind=kind)], "could_be_better": []})
    assert record["proposal"]["findings"][0]["category"] == category


def test_a_review_s_slips_are_set_aside_saying_why_and_never_refuse_what_it_found():
    """The forensic of 20 Oct 2026: each of these refused a v9 review whole."""
    record, sources = admitted({"misleading": [
        misleading(where=["U9", "U2", "U2", "D2", "P1", "T1", "T9"],
                   evidence=[{"source_id": "M1", "quote": "words the message never used"},
                             {"source_id": "P999", "quote": None}, {"source_id": "U1", "quote": None}]),
        misleading(where=["U1"], why="  ")],
        "could_be_better": [{"where": ["J1"], "what": "Add the court."}, {"where": [], "what": ""}]})
    first, better = record["proposal"]["findings"]
    passage = answer_sources.aliases(sources)["P1"]
    assert first["unit_ids"] == ["t2:s1b2", "t2:s1b1"] and first["limits"] == ["T1"]
    assert {pointer["source_id"] for pointer in first["sources"]} == {passage, answer_sources.aliases(sources)["M1"]}
    assert all(pointer["quote"] is None for pointer in first["sources"])
    assert better == {"category": "better", "unit_ids": [], "limits": [], "sources": [], "mismatch": "Add the court."}
    assert [entry["why"] for entry in record["proposal"]["set_aside"]] == [
        "names nothing in this piece: U9", "names nothing in this piece: D2", "names nothing in this piece: T9",
        "its quotation is not found once, word for word, in M1; the whole source is kept",
        "points to a source not offered: P999", "says nothing", "a source, not a place in this piece: J1",
        "says nothing"]


def test_a_quotation_its_source_holds_twice_keeps_the_whole_source():
    record, sources = admitted({"misleading": [misleading(evidence=[{"source_id": "M1", "quote": "a"}])],
                                "could_be_better": []})
    assert record["proposal"]["findings"][0]["sources"] == [{"source_id": answer_sources.aliases(sources)["M1"],
                                                             "quote": None}]


@pytest.mark.parametrize("returned", [
    {"misleading": []},
    {"misleading": [misleading(kind="framing")], "could_be_better": []},
    {"misleading": "U1 misleads", "could_be_better": []},
    {"misleading": [], "could_be_better": [], "verdict": "accept"},
])
def test_only_output_with_nothing_usable_is_refused(returned):
    with pytest.raises(SchemaViolation):
        admitted(returned)


def test_a_saved_review_replays_from_its_own_output_and_binds_its_evidence():
    ctx, record, sources, draft, authorities = piece()
    returned = {"misleading": [misleading(where=["U9"])], "could_be_better": []}
    deps = response_review._dependencies(ctx, record, sources, draft, turn.execution_record(record),
                                         authority_evidence=authorities, contract=response_review.MISLEADS_CONTRACT)
    saved = response_review._accept_v10(returned, deps)
    again = response_review.validate(saved, ctx, record, sources, draft, turn.execution_record(record),
                                     authority_evidence=authorities)
    assert again == saved
    for change in (lambda r: r["proposal"]["findings"].clear(), lambda r: r.update(accepted=True),
                   lambda r: r["returned"]["misleading"][0].update(why="Something else."), lambda r: r.pop("returned")):
        forged = deepcopy(saved)
        change(forged)
        with pytest.raises(ValueError):
            response_review.validate(forged, ctx, record, sources, draft, turn.execution_record(record),
                                     authority_evidence=authorities)


class Reviewer:
    def __init__(self, returned):
        self.returned, self.seen = returned, []

    def context_budget(self, tier): return 400_000

    def structured(self, prompt, schema, tier, **kwargs):
        self.seen.append((prompt, schema))
        return ModelResult(None, deepcopy(self.returned), tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                           completion=Completion.COMPLETE)


def test_a_piece_is_reviewed_with_the_two_questions_and_no_request_list():
    ctx, record, sources, draft, authorities = piece()
    reviewer = Reviewer({"misleading": [], "could_be_better": []})
    saved = response_review.review(reviewer, ctx, record, sources, draft, turn.execution_record(record),
                                   authority_evidence=authorities, contract=response_review.MISLEADS_CONTRACT)
    (prompt, schema), = reviewer.seen
    assert saved["contract"] == response_review.MISLEADS_CONTRACT and saved["accepted"]
    assert schema == response_review.SCHEMA_V10 and set(schema["properties"]) == {"misleading", "could_be_better"}
    words = " ".join(prompt.system.split())
    assert "Which statements would mislead the advocate as they stand (misleading)?" in words
    assert "What could the piece add or put better (could_be_better)?" in words
    assert "request_coverage" not in json.dumps(schema) and "verdict" not in json.dumps(schema)
    assert json.loads(prompt.user)["what_you_review"]["piece"] == "one dispute's section"
