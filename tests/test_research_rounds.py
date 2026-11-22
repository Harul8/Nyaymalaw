"""A dispute's research comes back while law is still named as missing (plan AN.65 and AN.72, D320 revising D30; the shared runner,
D322).

The owner, 22 Nov 2026: "Yes, revise D30", agreeing that after a dispute's further search the dispute comes back with what was found,
so that law the new provisions or judgments point to can be asked for in turn, the rounds ending when nothing is missing, when only
what was searched before is asked for, when a round chooses nothing new, or at the turn's backstop - never a fixed number of rounds.
The model proposes each round; code admits what is new of it, searches, keeps the round and decides when the rounds stop; each round
is checked again on reading, against everything before it. The matter and its law are invented.
"""
import re
from copy import deepcopy

import pytest

from nm.core_engine import answer_sources, research, rounds
from nm.core_engine.calls import ALLOWANCE, StopRequested, TurnCalls
from nm.core_engine.retrieval import HybridSearcher
from nm.shared.model_port import ModelError, SchemaViolation
from tests.test_core_research import Model, operations, proposal
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection

TIME = "when time runs for the suit"
EXCLUDED = "the period excluded"
#: The words of a provision the further search finds, which point to another provision (D320).
POINTS_ON = "The time runs from the refusal, subject to the period that section 4 excludes."


# --- the shared runner (D322) -------------------------------------------------------------------------------------------------

def run(proposals, *, outcomes=None, spend=None, unavailable=(), before=()):
    """The runner over scripted proposals: each round's outcome is what it carried out, and it progressed while that is truthy."""
    proposals, seen = list(proposals), []

    def ask(earlier):
        seen.append(len(earlier))
        proposal = proposals.pop(0)
        if isinstance(proposal, Exception):
            raise proposal
        return proposal

    def admit(proposal, earlier):
        if proposal == "nothing":
            return None, rounds.NOTHING_MISSING
        if proposal == "again":
            return None, rounds.REPEATED
        return [proposal], None
    done, stopped = rounds.run(ask, admit, lambda actions, earlier: (outcomes or {}).get(actions[0], actions[0]),
                               lambda outcome, earlier: bool(outcome), spend=spend, unavailable=unavailable, before=before)
    return done, stopped, seen


def test_the_rounds_stop_when_nothing_is_missing_or_only_what_was_done_is_asked_for():
    done, stopped, seen = run(["a", "b", "nothing"])
    assert [entry["proposal"] for entry in done] == ["a", "b", "nothing"]
    assert done[-1] == {"proposal": "nothing", "actions": None, "outcome": None}
    assert stopped == {"why": rounds.NOTHING_MISSING, "reason": None}
    assert seen == [0, 1, 2], "each round is asked with the rounds before it"
    done, stopped, _ = run(["a", "again"])
    assert stopped == {"why": rounds.REPEATED, "reason": None} and len(done) == 2


def test_a_round_that_brings_nothing_new_is_the_last():
    done, stopped, _ = run(["a", "b", "c"], outcomes={"b": ""})
    assert [entry["proposal"] for entry in done] == ["a", "b"]
    assert done[-1]["outcome"] == "" and stopped == {"why": rounds.NOTHING_NEW, "reason": None}


def test_the_backstop_is_reached_before_a_round_is_paid_for_and_there_is_no_fixed_number_of_rounds():
    paid = []

    def spend():
        if len(paid) == 3:
            raise rounds.Backstop("The turn's allowance is used")
        paid.append(1)
    done, stopped, _ = run(["a", "b", "c", "d", "e"], spend=spend)
    assert [entry["proposal"] for entry in done] == ["a", "b", "c"]
    assert stopped == {"why": rounds.BACKSTOP, "reason": "The turn's allowance is used"}
    many = [f"r{n}" for n in range(40)] + ["nothing"]
    done, stopped, _ = run(many)
    assert len(done) == 41 and stopped["why"] == rounds.NOTHING_MISSING, "the runner itself sets no number of rounds"


def test_a_call_that_cannot_be_made_ends_the_rounds_and_every_other_error_passes_through():
    done, stopped, _ = run(["a", SchemaViolation("no answer")], unavailable=(ModelError, SchemaViolation))
    assert len(done) == 1 and stopped == {"why": rounds.UNAVAILABLE, "reason": "SchemaViolation"}
    with pytest.raises(StopRequested):
        run(["a", StopRequested("stopped")], unavailable=(ModelError, SchemaViolation))
    with pytest.raises(KeyError):
        run([KeyError("a programming error")], unavailable=(ModelError,))


def test_the_runner_refuses_a_round_it_cannot_keep():
    with pytest.raises(TypeError):
        rounds.run(None, lambda p, e: (None, rounds.NOTHING_MISSING), lambda a, e: a, lambda o, e: True)
    with pytest.raises(ValueError):
        rounds.run(lambda e: "a", lambda p, e: (None, "tired"), lambda a, e: a, lambda o, e: True)
    with pytest.raises(ValueError):
        rounds.run(lambda e: "a", lambda p, e: ([], None), lambda a, e: a, lambda o, e: True)
    assert set(rounds.STOPS) == {"nothing_missing", "repeated", "nothing_new", "complete", "backstop", "unavailable"}


def test_the_rounds_stop_when_what_they_are_for_is_done():
    """D323: drafting's rounds end when the draft has nothing left to correct."""
    done, stopped = rounds.run(lambda e: f"draft {len(e)}", lambda p, e: ([p], None), lambda a, e: {"faults": 2 - len(e)},
                               lambda o, e: True, finished=lambda o, e: o["faults"] == 0)
    assert [entry["outcome"]["faults"] for entry in done] == [2, 1, 0] and stopped == {"why": rounds.COMPLETE, "reason": None}
    with pytest.raises(TypeError):
        rounds.run(lambda e: "a", lambda p, e: ([p], None), lambda a, e: a, lambda o, e: True, finished="yes")


# --- research's later rounds (D320) ---------------------------------------------------------------------------------------------

def library():
    """A first search finds sections 0 and 1 and judgment 0; a search for when time runs finds sections 2 and 3 and judgment 2 -
    section 2 pointing on to the period excluded; a search for the period excluded finds sections 4 and 5 and judgment 3."""
    provisions = Collection()
    provisions.rows = {p: {"chunk_id": f"s{p}", "full_text": f"Section {p}\n" + (POINTS_ON if p == 2 else f"Provision {p} text."),
                           "act_id": "act", "act_name": "Act", "section_number": str(p)} for p in range(6)}

    def found(query, kinds):
        return kinds[0] if "time runs" in query else kinds[1] if "excluded" in query else kinds[2]
    provisions.lexical = provisions.semantic = lambda query, depth: found(query, ([2, 3], [4, 5], [0, 1]))
    provisions.rerank = lambda pairs, *, anchors=None: [1.0] * len(pairs)
    held = Collection("judgment")
    held.rows = {p: {"chunk_id": f"j{p}", "full_text": f"Paragraph {p}:\n the court holds rule {p}.", "case_id": f"case{p}",
                     "case_name": f"Case {p} v State", "paragraph_num": str(p + 1), "court": "Supreme Court of India",
                     "year": "2001", "cited_by_count": 10, "paragraph_type": "reasoning"} for p in range(4)}
    held.lexical = held.semantic = lambda query, depth: found(query, ([2], [3], [0]))
    held.rerank = lambda pairs, *, anchors=None: [1.0] * len(pairs)
    searcher = HybridSearcher({"provision": provisions, "judgment": held})
    asked, many = [], searcher.search_many
    searcher.search_many = lambda searches, **kwargs: asked.append(searches) or many(searches, **kwargs)
    return searcher, asked


def label(user):
    return re.search(r"^(Q\d+): ", user, re.M).group(1)


def three_rounds(user):
    """The further search asks when time runs; the round after it, shown section 2's words, asks for the period they point to; the
    round after that finds nothing missing."""
    if "Search 2 for what was missing:" in user:
        return {"questions": []}
    if "Search 1 for what was missing:" in user:
        return {"questions": [{"question_id": label(user), "missing": "The period section 2 makes the time subject to.",
                               "sections": [], "phrases": [EXCLUDED]}]}
    return {"questions": [{"question_id": label(user), "missing": "When time runs for the suit.", "sections": [],
                           "phrases": [TIME], "cited": []}]}


def researched(model):
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(1, 1), ctx)
    searcher, asked = library()
    return ctx, plan, research.retrieve(plan, searcher, ctx, model=model), asked


def further_calls(model):
    return [prompt for prompt in model.calls if prompt.operation == "core_research_further"]


def test_the_dispute_comes_back_with_what_was_found_and_asks_for_the_law_it_points_to():
    model = Model(further=three_rounds)
    ctx, plan, record, asked = researched(model)
    work_id = plan["work"][0]["id"]
    further = record["further"]["D1"]
    first, second, third = further_calls(model)
    # Each call is shown what was chosen in its own words: the further search the first pick's, each later round all since.
    assert "Provision 0 text." in first.user and first.system == research.FURTHER
    assert second.system == research.ROUND and POINTS_ON in second.user and "Search 1 for what was missing:" in second.user
    assert f'Searched for: "{TIME}"' in second.user and "Provision 0 text." in second.user
    assert "Search 2 for what was missing:" in third.user and "Provision 4 text." in third.user
    # D322: each later round's request opens with the one before it, whole, marked for the next round to read.
    assert (second.cache_through, second.cache_also) == (len(second.user), ())
    assert third.user.startswith(second.user) and (third.cache_through, third.cache_also) == (len(second.user), (len(third.user),))
    assert len(asked) == 3, "the first searches, the further search, then the later round's one search"
    assert [query["text"] for query in asked[2][0][0]] == [EXCLUDED]
    # The later rounds as kept: the one that searched, then the one that found nothing missing, which ended them.
    assert further["rounds_stopped"] == {"why": "nothing_missing", "reason": None}
    searched, last = further["rounds"]
    assert set(searched) == {"proposal", "searches", "failures", "picks", "judgments"} and last == {"proposal": {"questions": []}}
    assert [query["query_id"] for query in searched["searches"][work_id]["queries"]] == [f"{work_id}:round2.1"]
    # What it chose joins what the dispute reads, within each question's five provisions; each judgment is read once.
    chosen = research.chosen(record)[work_id]
    assert len(chosen) == research.SECTIONS_A_QUESTION == 5
    texts = {candidate["id"]: candidate["text"] for search in [record["searches"][work_id], *dict(
        research.further_searches(record)).values()] for candidate in search["candidates"]}
    assert "Section 4\nProvision 4 text." in [texts[identity] for identity in chosen]
    assert "Section 5\nProvision 5 text." not in [texts[identity] for identity in chosen], "the fifth was the question's last"
    assert [entry["case_id"] for entry in searched["judgments"]] == ["case3"]
    assert [entry["case_id"] for entry in research.judgments_read(record)["D1"]] == ["case0", "case2", "case3"]
    # The readers of a further search see the rounds as one search of the question, what is new to it in order.
    (shown_id, shown), = research.further_searches(record)
    assert shown_id == work_id
    ids = [candidate["id"] for candidate in shown["candidates"]]
    assert len(ids) == len(set(ids)) and not set(ids) & {c["id"] for c in record["searches"][work_id]["candidates"]}
    sources = answer_sources.build(ctx, record)
    assert any(row["kind"] == "provision" and "Provision 4 text." in row["text"] for row in sources.values())
    assert any(row["kind"] == "judgment" and "rule 3" in row["text"] for row in sources.values())
    # Saved and read again exactly; its part carries the rounds.
    assert research.validate(record, plan, ctx) == record
    assert research.part_of(record, "D1")["further"]["D1"] == further


def tampered(record, change):
    changed = deepcopy(record)
    change(changed["further"]["D1"])
    return changed


@pytest.mark.parametrize("change", [
    lambda f: f["rounds"][0]["proposal"]["questions"][0].update(phrases=["another way in"]),
    lambda f: f["rounds_stopped"].update(why="backstop"),
    lambda f: f["rounds_stopped"].update(why="nothing_new"),
    lambda f: f["rounds"].pop(),
    lambda f: f["rounds"].append({"proposal": {"questions": []}}),
    lambda f: f.pop("rounds_stopped"),
    lambda f: f["rounds"][0]["judgments"].clear(),
    lambda f: f["rounds"][0]["picks"]["provision"]["chosen"].update(
        {w: [*ids, f["rounds"][0]["searches"][w]["candidates"][1]["id"]] for w, ids in
         f["rounds"][0]["picks"]["provision"]["chosen"].items()}),
], ids=["asked-otherwise", "said-backstop", "said-nothing-new", "last-round-dropped", "round-added", "stop-dropped",
        "judgment-dropped", "beyond-five"])
def test_a_changed_later_round_is_refused_on_reading(change):
    model = Model(further=three_rounds)
    ctx, plan, record, _ = researched(model)
    with pytest.raises(ValueError):
        research.validate(tampered(record, change), plan, ctx)


def test_a_record_kept_before_the_rounds_is_read_exactly_as_before():
    model = Model(further=three_rounds)
    ctx, plan, record, _ = researched(model)
    before = tampered(record, lambda f: [f.pop(key) for key in ("rounds", "rounds_stopped")])
    assert research.validate(before, plan, ctx) == before
    # As the readers read it before D320: the further search alone.
    old = [(work_id, research._fresh(search, before["searches"].get(work_id)))
           for work_id, search in before["further"]["D1"]["searches"].items()]
    assert research.further_searches(before) == old
    assert [e["case_id"] for e in research.judgments_read(before)["D1"]] == ["case0", "case2"]
    # Only a further search made keeps later rounds.
    unavailable = Model(fail={"core_research_further"})
    ctx, plan, record, _ = researched(unavailable)
    assert set(record["further"]["D1"]) == research._FURTHER_FIELDS
    with pytest.raises(ValueError):
        research.validate(tampered(record, lambda f: f.update(rounds=[], rounds_stopped={"why": "nothing_missing",
                                                                                          "reason": None})), plan, ctx)


def test_a_round_that_chooses_nothing_new_ends_the_rounds():
    def again(user):
        if "Search 1 for what was missing:" in user:
            # Asked another way, it finds only what was already offered: nothing new to choose.
            return {"questions": [{"question_id": label(user), "missing": "When time runs.", "sections": [],
                                   "phrases": ["time runs again"]}]}
        return three_rounds(user)
    model = Model(further=again)
    ctx, plan, record, asked = researched(model)
    further = record["further"]["D1"]
    assert len(further_calls(model)) == 2 and len(asked) == 3
    assert further["rounds_stopped"] == {"why": "nothing_new", "reason": None}
    round_, = further["rounds"]
    assert {kind: pick["state"] for kind, pick in round_["picks"].items()} == {"provision": "not_needed",
                                                                               "judgment": "not_needed"}
    assert research.validate(record, plan, ctx) == record


def test_asking_again_only_for_what_was_searched_ends_the_rounds_and_a_section_named_afresh_is_searched():
    def repeated(user):
        if "Search 1 for what was missing:" in user:
            return {"questions": [{"question_id": label(user), "missing": "Time.", "sections": [],
                                   "phrases": ["  When TIME runs for the  suit "]}]}
        return three_rounds(user)
    model = Model(further=repeated)
    ctx, plan, record, asked = researched(model)
    further = record["further"]["D1"]
    assert further["rounds_stopped"] == {"why": "repeated", "reason": None} and len(asked) == 2
    assert research.validate(record, plan, ctx) == record
    # What is new of an answer: a section named afresh is read, beside the words given for it though those were searched before.
    work_id, labels = plan["work"][0]["id"], {plan["work"][0]["id"]: "Q1"}
    first = research._further_wanted(further["proposal"], plan, labels)
    before = research._asked_before(plan, record["searches"], [first])
    asked_for = {"questions": [{"question_id": "Q1", "missing": "The section it is subject to.", "phrases": [TIME],
                                "sections": [{"act": "Imagined Relief Act, 1907", "section": "Section 4"}]}]}
    named, new = research._round_wanted(asked_for, plan, labels, 2, before)
    assert new[work_id]["named"] == [{"act": "Imagined Relief Act, 1907", "section": "4"}]
    assert [enquiry["text"] for enquiry in new[work_id]["enquiries"]] == [TIME]
    later = research._asked_before(plan, record["searches"], [first, new])
    assert research._round_wanted(asked_for, plan, labels, 3, later) == (research._further_wanted(asked_for, plan, labels, 3), {})


def test_a_round_whose_call_cannot_be_made_ends_the_rounds_and_the_rest_stands():
    def fails(user):
        if "Search 1 for what was missing:" in user:
            raise SchemaViolation("Scripted failure for the later round")
        return three_rounds(user)
    model = Model(further=fails)
    ctx, plan, record, asked = researched(model)
    further = record["further"]["D1"]
    assert (further["rounds"], further["rounds_stopped"]) == ([], {"why": "unavailable", "reason": "SchemaViolation"})
    assert further["state"] == "evaluated" and further["searches"] and len(asked) == 2
    assert research.validate(record, plan, ctx) == record


def test_an_advocates_stop_during_a_round_is_not_a_reason_the_rounds_ended():
    def stopped(user):
        if "Search 1 for what was missing:" in user:
            raise StopRequested("The advocate stopped this answer")
        return three_rounds(user)
    with pytest.raises(StopRequested):
        researched(Model(further=stopped))


def test_each_later_round_takes_one_from_the_turns_backstop_before_it_is_paid_for():
    inner = Model(further=three_rounds)
    inner.knows_further = True  # the tests' turn calls otherwise answer a further search as finding nothing missing
    calls = TurnCalls(inner, corrections_used=ALLOWANCE - 1)
    ctx, plan, record, asked = researched(calls)
    further = record["further"]["D1"]
    assert len(further_calls(inner)) == 2, "the further search, then the one round the backstop allowed"
    assert further["rounds_stopped"]["why"] == "backstop" and further["rounds_stopped"]["reason"]
    assert len(further["rounds"]) == 1 and calls.corrections_used == ALLOWANCE
    assert calls.used("research.rounds.D1") == 1
    assert research.validate(record, plan, ctx) == record


def test_the_later_round_is_asked_for_in_plain_words():
    words = " ".join(research.ROUND.split())
    for part in ("Purpose:", "Outcome:", "Work in a loop", "a section it makes its rule subject to",
                 "not again for what was searched for before", "When nothing a question needs is missing, name nothing for it."):
        assert part in words, part
    item = research.ROUND_SCHEMA["properties"]["questions"]["items"]
    assert set(item["properties"]) == {"question_id", "missing", "sections", "phrases"}, "the cited judgments are the first's"
    assert research.LATER_ROUNDS == (research.CONTRACT, research.ADDED_CONTRACT)
