"""Time limits worked out inside an answer (owner decisions, 15 Oct 2026; item 9, A4).

The model proposes from the Acts' own words; code checks every quotation and does the
arithmetic; the answer carries a code-owned Working box per limit and the saved turn
recomputes it on replay. Scripted proposals prove the wiring and the checks, not how
well a model chooses the provision.
"""
import hashlib
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.core_engine import calculation, research, response_rendering
from nm.core_engine.conversation import ConversationRefused, chat_matter_id
from nm.core_engine.turn import saved_rows
from nm.shared.model_port import Completion, ModelResult, ProviderUnavailable, Usage
from tests.test_core_turn import ScriptedModel, run, store  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a
NI = "The Negotiable Instruments Act, 1881"
LIMITATION = "The Limitation Act, 1963"
CPC = "The Code of Civil Procedure, 1908"
TEXTS = {
    NI: ("138. Dishonour of cheque for insufficiency, etc., of funds in the account.\n(b) the payee ... makes a "
         "demand for the payment of the said amount of money by giving a notice; in writing, to the drawer of the "
         "cheque, 5[within thirty days] of the receipt of information by him from the bank regarding the return of "
         "the cheque as unpaid; and\n(c) the drawer of such cheque fails to make the payment ... within fifteen days "
         "of the receipt of the saidnotice.\n142. (b) such complaint is made within one month of the date on which "
         "the cause of action arises under clause (c) of the proviso to section 138:"),
    CPC: ("An Act to consolidate and amend the laws relating to the procedure of the Courts of Civil Judicature.\n"
          "THE FIRST SCHEDULE\nORDER VIII\n1. Written Statement.-The Defendant shall, within thirty days from the date "
          "of service of summons on him, present a written statement of his defence.\n"),
    LIMITATION: ("THE SCHEDULE\nFIRST DIVISION--SUITS\n19\nFor money payable for money lent.\nThree years\n"
                 "When the loan is made.\n"),
}
MESSAGE = ("The bank's return memo reached my client on 18 August 2026. Notice was delivered on 29 August 2026 "
           "and nothing was paid. We filed the complaint on 12 September 2026. Was it in time?")


class Held:
    def __init__(self):
        self.reads = []

    def read(self, title):
        self.reads.append(title)
        text = TEXTS[title]
        return {"title": title, "text": text, "sha256": hashlib.sha256(text.encode()).hexdigest(), "file": title}


def step(id_, what, words, period, start, **extra):
    blank = {"what": "", "date": "", "quote": ""}
    return {"id": id_, "what": what, "act": extra.get("act", NI), "provision": extra.get("provision", "s.138"),
            "article": extra.get("article", ""), "part": "", "words": words, "period_words": period,
            "start": start, "copies": [], "done": extra.get("done", blank),
            "earliest_after": extra.get("earliest_after", ""), "reasoning": "From the Act's words.",
            "assumptions": ["The dates are as reported."], "missing": [], "may_extend": extra.get("may_extend", [])}


def chain():
    # The model quotes in its own typography and spacing; code finds the words in the conversation.
    fact = lambda date, quote: {"after": "", "event": "", "date": date, "quote": quote}  # noqa: E731
    return {"needed": True, "why": "The advocate asks whether the complaint was in time.", "not_assessed": [],
            "calculations": [
                step("c1", "Last day for the drawer to pay", "within fifteen days of the receipt of the said notice",
                     "fifteen days", fact("2026-08-29", "notice was delivered on 29 August 2026.")),
                step("c2", "Last day to file the complaint",
                     "within one month of the date on which the cause of action arises", "one month",
                     {"after": "c1", "event": "the cause of action", "date": "", "quote": ""},
                     provision="s.142(1)(b)", earliest_after="c1",
                     done={"what": "complaint filed", "date": "2026-09-12",
                           "quote": "We filed the complaint on  12 September\n2026"},
                     may_extend=["Proviso to s.142(1)(b): cognizance after time on sufficient cause."]),
                step("bad", "A period misquoted", "within ninety days of the receipt", "ninety days",
                     fact("2026-08-18", "18 August 2026"))]}


class Calculating(ScriptedModel):
    def __init__(self, proposal=None, fails=None, correction=None, correction_fails=None):
        super().__init__(legal=True)
        self.proposal, self.fails, self.seen = proposal, fails, {}
        self.correction, self.correction_fails = correction, correction_fails

    def structured(self, prompt, schema, tier, **kwargs):
        if prompt.operation == "core_calculation_correct":
            self.seen.setdefault("correction", []).append(prompt)
            if self.correction_fails:
                raise self.correction_fails
            data = deepcopy(self.correction) if self.correction else {"calculations": [], "cannot": []}
            return ModelResult(None, data, tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                               completion=Completion.COMPLETE)
        if prompt.operation == "core_calculation":
            self.seen["calculation"] = prompt
            if self.fails:
                raise self.fails
            data = deepcopy(self.proposal) if self.proposal else {"needed": False, "why": "", "calculations": [],
                                                                   "not_assessed": []}
            return ModelResult(None, data, tier, "synthetic", "fixture", Usage(1, 1, 0), 0,
                               completion=Completion.COMPLETE)
        if prompt.operation in ("core_response_writer", "core_response_review"):
            self.seen.setdefault(prompt.operation, []).append(prompt.user)
        return super().structured(prompt, schema, tier, **kwargs)


def turn(store, model, held=None):
    return run(store, model, message=MESSAGE, held_acts=held or Held())


def test_the_answer_carries_a_working_box_for_each_checked_limit_and_reports_the_rest(store):
    model = Calculating(chain())
    reply = turn(store, model)
    prompt = model.seen["calculation"]
    assert "held text" in prompt.system and TEXTS[NI] in prompt.system and MESSAGE in prompt.user
    kinds = [element["kind"] for element in reply["elements"]]
    assert kinds[1:4] == ["WORKING", "WORKING", "WORKING"]  # after the opening paragraph
    pay, complaint, bad = reply["elements"][1:4]
    assert pay["working"]["last_day"] == "2026-09-13"
    assert complaint["working"]["last_day"] == "2026-10-14" and complaint["working"]["earliest_day"] == "2026-09-14"
    assert complaint["working"]["standing"] == {"state": "early", "days": 2}
    assert complaint["text"] == "Last day to file the complaint"  # the box's facts are data; words are the answer's
    assert complaint["working"]["counting_starts_after"] == "2026-09-14"
    assert complaint["working"]["runs_from"]["after"] == "c1" and complaint["working"]["may_extend"]
    # Shown as fixed labels over the saved values, never as sentences (owner, 15 Oct 2026),
    # with the day the standing was worked out (v9).
    row = saved_rows(store.load(chat_matter_id("owner", reply["chat_id"])), "owner")[0]
    as_of = response_rendering._date(row["activities"]["calculation"]["today"])
    assert complaint["working"]["rows"] == [
        ["Provision", f"s.142(1)(b), {NI}"], ["Period", "“one month”"],
        ["The Act’s words", "“within one month of the date on which the cause of action arises”"],
        ["Runs from", "14 September 2026 (Monday)"], ["Starts the day after", "Last day for the drawer to pay"],
        ["Event", "the cause of action"], ["Counting starts after", "14 September 2026 (Monday)"],
        ["Period ends", "14 October 2026 (Wednesday)"], ["Last day", "14 October 2026 (Wednesday)"],
        ["Earliest day", "14 September 2026 (Monday)"], ["Taken on", "12 September 2026 (Saturday)"],
        ["Whose words", "“We filed the complaint on 12 September 2026”"],
        ["As of", as_of], ["Result", "Early"],
        ["Days before the earliest day", "2"],
        ["Court closed on the last day", "Limitation Act s.4 not applied: the court calendar is not held"]]
    assert [title for title, _ in complaint["working"]["lists"]] == ["Assumed", "May extend time (not counted)"]
    assert ["Whose words", "“Notice was delivered on 29 August 2026”"] in pay["working"]["rows"]
    assert bad["text"] == "A period misquoted" and "not in its held text" in bad["working"]["not_assessed"]
    assert bad["working"]["rows"] == [["Not assessed", bad["working"]["not_assessed"]]]
    assert bad["working"]["lists"] == []
    # The writer and the reviewer were given the checked results, not the proposal.
    assert all('"time_limits"' in payload for payload in model.seen["core_response_writer"])
    assert all('"owned_time_limits"' in payload and "2026-10-14" in payload
               for payload in model.seen["core_response_review"])
    assert row["activities"]["calculation"]["state"] == "worked"
    # An answer saved under v8 still reopens as it was shown, without the date.
    earlier = response_rendering._working(row["activities"]["calculation"])
    assert ["As of", as_of] not in earlier[1]["working"]["rows"]
    assert [a["title"] for a in row["activities"]["calculation"]["acts"]] == [LIMITATION, NI, CPC]


def test_a_saved_limit_replays_without_the_corpus_and_a_changed_one_is_refused(store):
    held = Held()
    reply = turn(store, Calculating(chain()), held)
    reads = len(held.reads)
    matter = store.load(chat_matter_id("owner", reply["chat_id"]))
    assert saved_rows(matter, "owner")[0]["response"]["elements"] == reply["elements"]
    assert len(held.reads) == reads  # reopening read no Act
    damaged = deepcopy(matter.brain_chat)
    damaged[0]["activities"]["calculation"]["calculations"][1]["working"]["last_day"] = "2026-10-15"
    with pytest.raises(ConversationRefused):
        saved_rows(replace(matter, brain_chat=tuple(damaged)), "owner")
    # A record saved before code found the quoted words itself (v1) still reopens.
    earlier = calculation.unavailable("down") | {"contract": calculation.V1_CONTRACT}
    assert calculation.validate(earlier, None) == earlier
    # And one saved before the correction pass (v2), without a correction field.
    from nm.core_engine.turn import TurnContext
    row = saved_rows(matter, "owner")[0]
    context = TurnContext(matter, row["chat_id"], row["turn_id"], row["message"], []).payload()
    v2 = {key: value for key, value in row["activities"]["calculation"].items() if key != "correction"}
    v2["contract"] = calculation.V2_CONTRACT
    assert calculation.validate(v2, context) == v2
    with pytest.raises(ValueError):  # a correction claimed without its disposition
        calculation.validate(row["activities"]["calculation"] | {"correction": {"state": "corrected"}}, context)


def test_code_finds_the_quoted_words_and_refuses_what_it_cannot_check(store):
    proposal = chain()
    pay, complaint, _ = proposal["calculations"]
    pay["start"]["quote"] = "Notice was delivered on 30 August 2026"  # not what the advocate wrote
    complaint["start"]["after"] = "The drawer's period to pay has run."  # words, not a step's id
    proposal["calculations"].insert(0, step("c0", "Last day for the complaint period to run", "within one month of the "
                                            "date on which the cause of action arises", "one month",
                                            {"after": "", "event": "", "date": "2026-09-14", "quote": "12 September 2026"}))
    # A notice made premature by a period that ends after the notice's own last day: an empty window.
    proposal["calculations"].append(step("c9", "Last day to give notice", "within thirty days of the receipt of "
                                         "information", "thirty days",
                                         {"after": "", "event": "", "date": "2026-08-18",
                                          "quote": "The bank’s return memo reached my client on 18 August 2026"},
                                         earliest_after="c0"))
    reply = turn(store, Calculating(proposal))
    boxes = {e["text"]: e["working"] for e in reply["elements"] if e["kind"] == "WORKING"}
    assert boxes["Last day for the drawer to pay"]["not_assessed"] == (
        "the words given for the starting event are not in the conversation or documents as quoted")
    assert "which was not worked out first" in boxes["Last day to file the complaint"]["not_assessed"]
    assert boxes["Last day to give notice"]["not_assessed"].startswith(
        "its earliest day (2026-10-15) falls after its last day (2026-09-17)")


def fixed_bad():
    return step("bad", "A period misquoted", "within thirty days", "thirty days",
                {"after": "", "event": "", "date": "2026-08-18", "quote": "18 August 2026"})


def test_a_refused_limit_gets_one_correction_that_faces_the_same_checks(store):
    # Owner, 16 Oct 2026: one correction pass, only when code refused something.
    stray = step("c1", "A checked limit the correction must not replace", "within thirty days", "thirty days",
                 {"after": "", "event": "", "date": "2026-08-18", "quote": "18 August 2026"})
    model = Calculating(chain(), correction={"calculations": [fixed_bad(), stray], "cannot": []})
    reply = turn(store, model)
    prompt, = model.seen["correction"]
    assert prompt.system == model.seen["calculation"].system  # the same held Acts, cached alike
    assert MESSAGE in prompt.user and '"id": "bad"' in prompt.user
    assert "- bad (A period misquoted): the words quoted from" in prompt.user and "not in its held text" in prompt.user
    # Code shows the Act's own words nearest to the misquotation; the model judges what to quote.
    assert "The held text nearest to the words you quoted reads: “" in prompt.user and "of the receipt" in prompt.user
    boxes = {e["text"]: e["working"] for e in reply["elements"] if e["kind"] == "WORKING"}
    assert boxes["A period misquoted"]["last_day"] == "2026-09-17"  # corrected and checked
    assert boxes["Last day for the drawer to pay"]["last_day"] == "2026-09-13"  # checked first; stands
    row = saved_rows(store.load(chat_matter_id("owner", reply["chat_id"])), "owner")[0]
    record = row["activities"]["calculation"]
    assert record["contract"] == calculation.CONTRACT == "core_calculation_v3"
    assert record["correction"]["state"] == "corrected" and [r["id"] for r in record["correction"]["refused"]] == ["bad"]
    assert record["proposal"] == chain() and record["not_assessed"] == []
    assert saved_rows(store.load(chat_matter_id("owner", reply["chat_id"])), "owner")[0]["response"][
        "elements"] == reply["elements"]  # the corrected limit replays from the saved record


def test_the_nearest_held_words_are_found_for_a_quotation_with_a_word_dropped():
    held = ("which shall not be later than ninety days from the date of service of \r\n5[summons].] "
            "(2) A defendant may appear in person.")
    near = calculation._nearest("not later than ninety days from the date of service of summons", held)
    assert "shall not be later than ninety days from the date of service of 5[summons].]" in near
    assert calculation._nearest("words that appear nowhere in the Act", held) is None


def test_no_correction_call_when_nothing_was_refused(store):
    proposal = chain()
    proposal["calculations"].pop()  # without the misquoted period
    model = Calculating(proposal)
    turn(store, model)
    assert "correction" not in model.seen


def test_a_limit_the_correction_cannot_work_out_stays_not_assessed_with_both_reasons(store):
    model = Calculating(chain(), correction={"calculations": [], "cannot": [
        {"id": "bad", "why": "the held text gives no ninety-day period for this step"},
        {"id": "c1", "why": "a checked limit cannot be withdrawn this way"}]})
    reply = turn(store, model)
    boxes = {e["text"]: e["working"] for e in reply["elements"] if e["kind"] == "WORKING"}
    assert boxes["Last day for the drawer to pay"]["last_day"] == "2026-09-13"
    why = boxes["A period misquoted"]["not_assessed"]
    assert "not in its held text" in why and "on a second look: the held text gives no ninety-day period" in why


def test_a_correction_that_fails_leaves_the_first_check_standing(store):
    model = Calculating(chain(), correction_fails=ProviderUnavailable("down"))
    reply = turn(store, model)
    boxes = {e["text"]: e["working"] for e in reply["elements"] if e["kind"] == "WORKING"}
    assert "not in its held text" in boxes["A period misquoted"]["not_assessed"]
    assert boxes["Last day to file the complaint"]["last_day"] == "2026-10-14"
    row = saved_rows(store.load(chat_matter_id("owner", reply["chat_id"])), "owner")[0]
    correction = row["activities"]["calculation"]["correction"]
    assert correction["state"] == "unavailable" and correction["proposal"] is None


def test_a_failed_calculation_never_stops_the_answer_and_states_no_date(store):
    model = Calculating(fails=ProviderUnavailable("down"))
    reply = turn(store, model)
    assert reply["committed"] == "committed" and "WORKING" not in [e["kind"] for e in reply["elements"]]
    assert all('"unavailable"' in payload for payload in model.seen["core_response_writer"])
    row = saved_rows(store.load(chat_matter_id("owner", reply["chat_id"])), "owner")[0]
    assert row["activities"]["calculation"]["state"] == "unavailable"


def test_no_limit_needed_adds_nothing_the_answer_did_not_have_before(store):
    model = Calculating()
    reply = turn(store, model)
    assert "WORKING" not in [e["kind"] for e in reply["elements"]]
    assert not any('"time_limits"' in payload for payload in model.seen["core_response_writer"])
    assert not any('"owned_time_limits"' in payload for payload in model.seen["core_response_review"])


def test_a_message_needing_no_research_makes_no_calculation_call(store):
    model = ScriptedModel()  # a courtesy: research is not needed
    held = Held()
    run(store, model, held_acts=held)
    assert "core_calculation" not in [name for name, _ in model.calls] and held.reads == []


def test_an_act_not_listed_as_current_is_never_read_for_a_calculation():
    assert set(calculation.SUPPLIED) <= {LIMITATION, NI, "The Code of Civil Procedure, 1908"}
    assert "Today is" in research.conversation_text({"conversation": [], "latest": {"text": "x"}})


def test_an_act_too_large_to_supply_whole_is_given_as_its_provisions_that_state_a_period():
    from nm.core_engine import limitation
    code = ("ARRANGEMENT OF SECTIONS\n1. Summons within thirty days.\n"
            "An Act to consolidate the procedure.\n"
            "27. Summons to defendants.-A summons may be served on such day not beyond thirty days from date\n"
            "\n1. Subs. by Act 46 of 1999, s. 5, for certain words (w.e.f. 1-7-2002).\n53\n"
            "of the institution of the suit.\n"
            "28. Service of summons where defendant resides in another State.-A summons may be sent.\n"
            "THE FIRST SCHEDULE\nORDER VIII\n1. Written Statement.-The Defendant shall, within thirty days from "
            "the date of service of summons on him, present a written statement.\n"
            "APPENDIX A\n1. Form of plaint within ninety days.\n")
    parts = limitation.provisions_with_periods(code)
    assert [part["label"] for part in parts] == ["The sections", "The First Schedule, Order VIII"]
    # The section stays whole across the page: the editors' note and the page number are dropped.
    assert parts[0]["text"] == ("27. Summons to defendants.-A summons may be served on such day not beyond thirty days "
                                "from date\n\nof the institution of the suit.")
    held = {"title": CPC, "text": code + "x" * calculation.WHOLE_LIMIT}
    shown = calculation._held_text(held)
    assert "the rest of it is held but not shown here" in shown and "Form of plaint" not in shown
    assert "[The First Schedule, Order VIII]\n1. Written Statement." in shown
    assert calculation._held_text({"title": NI, "text": TEXTS[NI]}) == f"=== {NI} (held text) ===\n{TEXTS[NI]}"



def test_a_schedule_article_quoted_across_its_columns_is_read_as_its_own_words():
    # 17 Oct 2026, the owner's land matter: Articles 54, 59, 47 and 55 were proposed rightly and
    # all refused, because the period and its start were quoted joined by a semicolon, while
    # code joins the Schedule's columns itself. The entry is found by its number; the words
    # only confirm it was read, so they are compared by letters and digits alone.
    from nm.core_engine import limitation
    acts = {LIMITATION: Held().read(LIMITATION)}
    entries = limitation.schedule(acts[LIMITATION]["text"])
    item = step("a", "Suit to recover the loan", "Three years; When the loan is made", "Three years",
                {"after": "", "event": "", "date": "2024-01-10", "quote": "x"},
                act=LIMITATION, provision="Article 19", article="19")
    provision = calculation._provision(item, acts, entries)
    assert (provision["article"], provision["period_words"], provision["from"]) == (
        "19", "Three years", "When the loan is made.")
    for wrong in ("Three years; When the loan is repaid", "Two years; When the loan is made"):
        with pytest.raises(calculation._Unchecked, match="not in its held entry"):
            calculation._provision({**item, "words": wrong}, acts, entries)
