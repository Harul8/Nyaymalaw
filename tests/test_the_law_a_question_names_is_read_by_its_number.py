"""The law a question names is read by its number, beside what the search finds (plan AN.35, D30 A1; search v11, research v15;
piece 35b).

The owner, 2 Nov 2026: research should get "all the required sections". A section the papers or the advocate cite was found only
where a search phrase happened to rank it. Now the understanding lists, in each question's law to check, every provision the
messages or the papers cite for it; the phrases step names the sections to read first; and each is read by its number from the
held Act its name is - the Act by the instrument register's own key for the name, never a near title chosen for it - whole, with
the provisions its Act links to it, and offered to the pick. What is named and not held is said: to the pick, and to the writer as
research that could not establish it. The Act and its sections are invented.
"""
from copy import deepcopy

import pytest

from nm.core_engine import answer_sources, research, response_writer, retrieval
from nm.core_engine.retrieval import HybridSearcher, offered, validate_search
from tests.test_core_research import Model, proposal
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection, row

pytestmark = pytest.mark.class_a
ACT = "Imagined Relief Act, 1907"
KEY = "imagined relief act 1907"


class Named(Collection):
    """The test library, also holding one invented Act whose section 6 is read by its number."""

    def __init__(self):
        super().__init__()
        self.rows[7] = {**row(text="6. Recovery of a thing possessed: a person dispossessed may recover it within six months."),
                        "chunk_id": "named-6", "act_id": "IRA_1907", "act_name": ACT, "section_number": "6"}

    def instrument_keys(self):
        return frozenset({KEY})

    def kept_acts(self, keys):
        return ("IRA_1907",) if KEY in keys else ()

    def instrument_positions(self, keys):
        return frozenset()

    def read_provision(self, act_id, reference):
        if act_id == "IRA_1907" and reference == "6":
            context = {"scope": "indexed_section_segments", "bounded": False, "unread_positions": [],
                       "segments": [{"position": 7, "row": deepcopy(self.rows[7])}]}
            return {"state": "found", "sources": [retrieval._candidate("provision", 7, self.rows[7], self.revision(), None, [],
                                                                       context)], "reason": None}
        return {"state": "not_held", "sources": [], "reason": "No such provision"}


NAMED = [{"act": ACT, "section": "6"}, {"act": ACT, "section": "99"}, {"act": "An Act Nobody Holds, 1999", "section": "1"}]
QUERIES = [{"query_id": "t1:w1:q1", "text": "recovery of possession", "context": "May the client recover the land?"}]


def searched(named=NAMED):
    return HybridSearcher({"provision": Named(), "judgment": Collection("judgment")}).search(
        QUERIES, [ACT], results=research.FOR_PICK, named=named)


def test_each_named_section_is_read_by_its_number_and_what_is_not_held_is_said():
    record = searched()
    assert record["contract"] == retrieval.CONTRACT == "hybrid_retrieval_v11"
    states = [(entry["section"], entry["state"]) for entry in record["named"]]
    assert states == [("6", "read"), ("99", "not_held"), ("1", "not_held")]
    (six,) = record["named_found"]
    assert six["position"] == 7 and record["named"][0]["found"] == [six["id"]] and six in offered(record)
    assert record["named"][2]["reason"] == "No Act we hold is this name"
    assert validate_search(record, QUERIES, [ACT], NAMED) == record
    broken = deepcopy(record)
    broken["named"][0]["found"] = []
    with pytest.raises(ValueError, match="what became of it"):
        validate_search(broken, QUERIES, [ACT], NAMED)
    with pytest.raises(ValueError, match="its plan named"):
        validate_search(record, QUERIES, [ACT], NAMED[:1])
    before = {key: value for key, value in record.items() if key not in ("named", "named_found")}
    before["contract"] = retrieval.ONE_READING_CONTRACT
    validate_search(before, QUERIES, [ACT])                   # a v10 record replays unchanged
    with pytest.raises(ValueError, match="before v11"):
        validate_search(before, QUERIES, [ACT], NAMED)


def test_a_library_that_cannot_read_by_name_says_so_and_a_search_naming_nothing_reads_nothing():
    plain = HybridSearcher({"provision": Collection(), "judgment": Collection("judgment")}).search(
        QUERIES, [ACT], named=NAMED[:1])
    assert [entry["state"] for entry in plain["named"]] == ["unavailable"] and plain["named_found"] == []
    assert searched([])["named"] == [] and searched([])["named_found"] == []


def naming_plan():
    ctx = context("Find the applicable law.")
    proposed = proposal()
    proposed["statute_phrases"][0]["questions"][0]["sections"] = [
        {"act": ACT, "section": " 6 "}, {"act": f"{ACT} ", "section": "6"}, {"act": ACT, "section": "99"}]
    return ctx, research.accept(proposed, ctx)


def test_the_plan_names_each_section_once_and_the_pick_is_shown_what_became_of_each():
    ctx, plan = naming_plan()
    (work,) = plan["work"]
    assert work["named"] == [{"act": ACT, "section": "6"}, {"act": ACT, "section": "99"}] == research.search_named(work)
    assert research.search_named(work, contract=research.SETTLED_CONTRACT) is None
    model = Model()
    record = research.retrieve(plan, HybridSearcher({"provision": Named(), "judgment": Collection("judgment")}), ctx, model=model)
    shown = next(p.user for p in model.calls if p.operation == "core_research_pick")
    assert "Named for this question, read by their number:" in shown and "Recovery of a thing possessed" in shown
    assert f"Named: {ACT}, 99 - not held in our library." in shown
    assert research.validate(record, plan, ctx) == record
    sources = answer_sources.build(ctx, record)
    assert any(source["kind"] == "provision" and source["source_identity"]["act_id"] == "IRA_1907" for source in sources.values())
    told = response_writer._research_context(record, None)["searches"][0]["named"]
    assert told == [{"act": ACT, "section": "6", "state": "read", "reason": ""},
                    {"act": ACT, "section": "99", "state": "not_held", "reason": "The Act we hold under this name has no such provision"}]


def test_the_understanding_and_the_phrases_are_asked_for_the_law_the_papers_cite():
    understand = " ".join(research.UNDERSTAND.split())
    assert "every provision the advocate's messages or the papers cite that bears on it, as they cite it" in understand
    phrases = " ".join(research.PHRASES.split())
    assert "And name the sections to read first" in phrases and "one we do not hold is said, never replaced by another" in phrases
    assert "sections" in research.STATUTE_PHRASES_V15["properties"]["questions"]["items"]["required"]


@pytest.mark.parametrize("said, read", [
    ("Sections 3, 5 and 9", ("3", "5", "9")), ("Section 5(5)", ("5",)), ("Sections 6 and 6-A", ("6", "6A")),
    ("Articles 226 and 227", ("Article 226", "Article 227")), ("Rules 5, 19 and 21", ("Rule 5", "Rule 19", "Rule 21")),
    ("Order VII, rules 1 and 3", ("Order VII Rule 1", "Order VII Rule 3")), ("Order XXXIX", ("Order XXXIX",)),
    ("sections 3 to 5", ("3", "4", "5")), ("Section 53A", ("53A",)), ("Rules governing the record", ())])
def test_a_reference_naming_several_provisions_is_read_as_each_it_names(said, read):
    # Found by the first small run (2 Nov 2026): 29 of 35 sections named were "not held", most of them lists like these.
    from nm.shared.citation_contracts import provision_references
    assert provision_references(said) == read


def test_the_plan_reads_a_list_as_each_provision_and_a_reference_without_a_number_is_said_so():
    ctx = context("Find the applicable law.")
    proposed = proposal()
    proposed["statute_phrases"][0]["questions"][0]["sections"] = [
        {"act": ACT, "section": "Sections 6 and 99"}, {"act": ACT, "section": "the rules on notice"}]
    (work,) = research.accept(proposed, ctx)["work"]
    assert work["named"] == [{"act": ACT, "section": "6"}, {"act": ACT, "section": "99"},
                             {"act": ACT, "section": "the rules on notice"}]
    record = searched(work["named"])
    assert [(e["section"], e["state"]) for e in record["named"]] == [("6", "read"), ("99", "not_held"),
                                                                      ("the rules on notice", "not_held")]
    assert record["named"][2]["reason"] == "It names no provision by its number"


def test_a_link_the_act_gives_a_section_read_by_its_number_is_kept_with_it():
    # Found by the first small run: 14 of 24 searches were refused, their named sections' links counted as joined to nothing.
    record = searched(NAMED[:1])
    (six,) = record["named_found"]
    beside = {**row(text="7. The provision printed after it."), "chunk_id": "named-7", "act_id": "IRA_1907", "act_name": ACT,
              "section_number": "7"}
    context_7 = {"scope": "indexed_section_segments", "bounded": False, "unread_positions": [],
                 "segments": [{"position": 8, "row": beside}]}
    linked = retrieval._candidate("provision", 8, beside, "checked-corpus", None, [], context_7)
    record["connected"].append(linked)
    record["connections"].append({"from": six["id"], "to": linked["id"], "how": "beside", "words": None})
    record["links"][six["id"]] = {"names": 0, "named_by": 0, "unbound": 0}
    assert validate_search(record, QUERIES, [ACT], NAMED[:1]) == record
