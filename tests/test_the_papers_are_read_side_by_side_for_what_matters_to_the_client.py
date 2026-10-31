"""The papers are read side by side for what matters to the client (plan AN.28, piece 3e; D1-D3; findings A1, A3, A4).

What matters only when two papers are set side by side belonged to no step: a member of the client's family among the respondents of an
appeal another paper lists, a sale dated after a death a third paper records. Research v13 reads every paper together once, with the
advocate's messages, for those points; code finds each point's words on the pages, a point whose words it cannot find is looked at
again once, and code finds where each of the client's people stands on the pages - a near spelling offered as a candidate, never taken
for the name. The papers, names and numbers here are invented.
"""
import pytest

from nm.core_engine import research
from nm.core_engine.research import accept, connections_of, plan
from nm.shared.model_port import SchemaViolation, UsageLimitReached
from tests.test_core_research import _result, understanding
from tests.test_the_chronology_of_each_document import row
from tests.test_the_plan_records_the_chronology import Beside, sent

pytestmark = pytest.mark.class_a

ORDER = "IN W.A. 6649 of 2016 the appellant is Navin Rastogi and the respondents include Leela Kulkarni. The appeal is pending."
DEATH = "Death certificate. Sarala Kulkarni died on 15-6-2013."
SALE = "Sale deed dated 20-1-2014 executed in the name of Sarala Kulkarni in favour of Navin Rastogi for Sy.No.9061. Witness: Leela Kulkarny."
POINTS = {"client_people": ["Sarala Kulkarni", "Leela Kulkarni", "Leela  Kulkarni"],
          "connections": [
              {"kind": "client_appears", "point": "Leela Kulkarni is a respondent in a pending writ appeal.",
               "why_it_matters": "She is one of the clients.", "words": "the respondents include Leela Kulkarni"},
              {"kind": "after_death", "point": "A sale in Sarala Kulkarni's name is dated after her recorded death.",
               "why_it_matters": "A dead person executes no deed.",
               "words": "Sarala Kulkarni died on 15-6-2013 ... Sale deed dated 20-1-2014 executed in the name of Sarala Kulkarni"},
              {"kind": "against_client", "point": "The appeal court found against the heirs.", "why_it_matters": "It binds them.",
               "words": "the court found against the heirs of Sarala Kulkarni"}]}


def papers():
    return {**sent(row("t1", 1, "order.pdf", 1, ORDER), row("t1", 2, "deed.pdf", 1, DEATH), row("t1", 2, "deed.pdf", 2, SALE)),
            "latest": {**sent()["latest"], "text": "We represent the heirs of Sarala Kulkarni. Understand the disputes."}}


class SideBySide(Beside):
    """The research double that also reads the papers side by side: `points` for the reading, `again` for the look again."""

    def __init__(self, points=POINTS, again=None, fail=False, usage=False):
        super().__init__({}, transfers={}, subject=understanding(words="We represent the heirs of Sarala Kulkarni"))
        self.points, self.again, self.fail_side, self.usage = points, again, fail, usage

    def structured(self, prompt, schema, tier, **kwargs):
        if prompt.operation == "core_research_connections":
            self.calls.append(prompt)
            if self.usage:
                raise UsageLimitReached("the account has no credit")
            if self.fail_side:
                raise SchemaViolation("scripted failure")
            looked = '"to_check"' in prompt.user
            return _result(self.again if looked and self.again is not None else self.points if not looked
                           else {"client_people": [], "connections": []}, tier)
        return super().structured(prompt, schema, tier, **kwargs)


def side(model):
    return [prompt for prompt in model.calls if prompt.operation == "core_research_connections"]


def test_every_paper_is_read_together_once_and_each_point_is_found_on_its_pages_across_papers():
    model = SideBySide()
    connections, people, appearances, failures = connections_of(model, papers())
    first = side(model)[0]
    assert first.system == research.CONNECTIONS_V13 and failures == []
    assert all(f'Paper "{name}"' in first.user for name in ("order.pdf", "deed.pdf")) and "We represent the heirs" in first.user
    (appears, after) = connections
    assert (appears["id"], appears["anchored"], [(place["document"], place["page"]) for place in appears["places"]]) == (
        "C1", True, [("order.pdf", 1)])
    assert after["anchored"] and [place["page"] for place in after["places"]] == [1, 2], "one point, two pages of one paper"
    assert people == ["Sarala Kulkarni", "Leela Kulkarni"], "each name once, however it was spaced"
    # The point whose words no page holds was looked at again and left out by the model; one it gives again with words still not
    # found is kept, marked, and supports nothing.
    kept, _, _, _ = connections_of(SideBySide(again={"client_people": [], "connections": [POINTS["connections"][2]]}), papers())
    assert (kept[2]["id"], kept[2]["anchored"], kept[2]["places"]) == ("C3", False, [])


def test_where_the_clients_people_stand_is_found_by_code_and_a_near_spelling_is_only_a_candidate():
    _, _, appearances, _ = connections_of(SideBySide(), papers())
    sarala, leela = appearances
    assert [(place["document"], place["page"]) for place in sarala["places"]] == [("deed.pdf", 1), ("deed.pdf", 2)]
    assert sarala["near"] == []
    assert [(place["document"], place["page"]) for place in leela["places"]] == [("order.pdf", 1)]
    assert [(near["as_written"], near["document"], near["page"]) for near in leela["near"]] == [("Leela Kulkarny", "deed.pdf", 2)]


def test_a_point_whose_words_are_not_found_is_looked_at_again_once_and_what_the_look_gives_replaces_it():
    fixed = {"client_people": [], "connections": [
        {"kind": "against_client", "point": "The appellant bought from a dead person's estate.", "why_it_matters": "Title is open.",
         "words": "in favour of Navin Rastogi for Sy.No.9061"}]}
    model = SideBySide(again=fixed)
    connections, _, _, _ = connections_of(model, papers())
    looked = side(model)[1]
    assert looked.system == research.CONNECTIONS_CHECK and '"to_check"' in looked.user and len(side(model)) == 2
    assert "the court found against the heirs of Sarala Kulkarni" in looked.user
    assert [(item["id"], item["kind"], item["anchored"]) for item in connections] == [
        ("C1", "client_appears", True), ("C2", "after_death", True), ("C3", "against_client", True)]


def test_a_file_above_the_limit_is_not_read_together_and_says_so_and_a_failure_is_said_never_an_empty_success(monkeypatch):
    model = SideBySide()
    monkeypatch.setattr(research, "WHOLE_FILE_TOKENS", 1)
    assert connections_of(model, papers()) == ([], [], [], [{"document": research.ALL_PAPERS, "pages": "all",
                                                             "reason": "TooLongToReadTogether"}])
    assert side(model) == []
    monkeypatch.setattr(research, "WHOLE_FILE_TOKENS", 100_000)
    assert connections_of(SideBySide(fail=True), papers())[3] == [{"document": research.ALL_PAPERS, "pages": "all",
                                                                   "reason": "SchemaViolation"}]
    with pytest.raises(UsageLimitReached):
        connections_of(SideBySide(usage=True), papers())
    assert connections_of(SideBySide(), sent()) == ([], [], [], []), "no papers, no call"


def test_the_plan_keeps_what_the_papers_read_together_show_and_refuses_a_record_code_would_not_make():
    ctx = papers()
    made = plan(SideBySide(), ctx)
    proposal = made["proposal"]
    assert [item["id"] for item in proposal["connections"]] == ["C1", "C2"] and proposal["connections_failures"] == []
    assert proposal["client_people"] == ["Sarala Kulkarni", "Leela Kulkarni"] and len(proposal["appearances"]) == 2
    assert accept(proposal, ctx) == made, "the plan replays from its own proposal"
    for tampered in ({**proposal, "appearances": []},
                     {**proposal, "connections": [{**proposal["connections"][0], "anchored": False, "places": []},
                                                  *proposal["connections"][1:]]},
                     {**proposal, "connections": proposal["connections"][1:]},
                     {**proposal, "connections_failures": [{"document": "order.pdf", "pages": "1", "reason": "SchemaViolation"}]}):
        with pytest.raises(SchemaViolation):
            accept(tampered, ctx)
    failed = plan(SideBySide(fail=True), ctx)
    assert [issue["mismatch"] for issue in failed["issues"]] == ["the papers read together unavailable: SchemaViolation"]


def test_the_prompts_say_what_to_look_for_and_that_no_legal_question_is_answered():
    prompt = " ".join(research.CONNECTIONS_V13.split())
    for part in ("Message:", "Purpose:", "Look for:", "Outcome:", "only when two papers, or two parts of one, are read together",
                 "You are not answering a legal question", "Whom the advocate acts for, from their messages",
                 "in another proceeding than the one the advocate speaks of", "goes against the client's position",
                 "dated after a party's death", "that the advocate has not mentioned", "Work in a loop",
                 "client_appears, against_client, after_death, after_time_limit, further_subject, or other"):
        assert part in prompt, part
    assert "Look again" in research.CONNECTIONS_CHECK and research.MAX_OUTPUT["connections"] == 8000
