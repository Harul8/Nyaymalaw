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
            # Calculation v5 (Q16): the step's own check of what its quoted words date; v6 (P34):
            # a period the facts set, empty unless given.
            "start": {"dated_event": "", "same_event": True, "period_words": "", "period_quote": "", **start}, "copies": [], "done": extra.get("done", blank),
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
    assert kinds[3:6] == ["WORKING", "WORKING", "WORKING"]  # after In short (rendering v18)
    pay, complaint, bad = reply["elements"][3:6]
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
    # P36 (v7): the advocate is told plainly that NM's working failed code's check; code's
    # own reason stays in the record.
    assert bad["text"] == "A period misquoted" and bad["working"]["not_assessed"] == calculation.UNCHECKED_ACT
    (kept,) = row["activities"]["calculation"]["not_assessed"]
    assert "not in its held text" in kept["code"] and kept["why"] == calculation.UNCHECKED_ACT
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


def test_a_remark_on_a_worked_out_limit_is_shown_beside_it_and_asks_no_rewrite(store):
    """Owner decision P29: what the independent check says about a worked-out time limit is
    shown beside that limit; the writer cannot change code's arithmetic, so nothing is
    rewritten or left out for it."""
    class Remarking(Calculating):
        def structured(self, prompt, schema, tier, **kwargs):
            if prompt.operation == "core_response_review" and "misleading" in schema["properties"]:
                self.seen.setdefault("core_response_review", []).append(prompt.user)
                return ModelResult(None, {"misleading": [{"kind": "unsupported", "where": ["T2"], "evidence": [],
                                                          "why": "T2 should run from the day the notice was "
                                                                 "delivered."}], "could_be_better": []},
                                   tier, "synthetic", "fixture", Usage(1, 1, 0), 0, completion=Completion.COMPLETE)
            return super().structured(prompt, schema, tier, **kwargs)
    model = Remarking(chain())
    reply = turn(store, model)
    assert [element["kind"] for element in reply["elements"]][3:7] == ["WORKING", "WORKING", "NOTE", "WORKING"]
    assert reply["elements"][4]["text"] == "Last day to file the complaint"
    assert reply["elements"][5]["text"] == ("The independent check remarked on this time limit: this time limit "
                                            "should run from the day the notice was delivered.")
    assert len(model.seen["core_response_writer"]) == 1 and reply["metrics"]["draft_corrections"] == 0
    row = saved_rows(store.load(chat_matter_id("owner", reply["chat_id"])), "owner")[0]
    assert row["response"]["elements"] == reply["elements"]


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
    # And one saved before a step taken had to be the step itself (v3).
    v3 = row["activities"]["calculation"] | {"contract": calculation.V3_CONTRACT}
    assert calculation.validate(v3, context) == v3


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
    # P36 (v7): what the advocate reads says NM's working failed code's check, never that
    # something they gave is missing; code's own reasons stay in the record.
    assert boxes["Last day for the drawer to pay"]["not_assessed"] == calculation.UNCHECKED_FACT
    assert boxes["Last day to file the complaint"]["not_assessed"] == calculation.UNCHECKED_WORKING
    assert boxes["Last day to give notice"]["not_assessed"] == calculation.UNCHECKED_WORKING
    codes = {entry["what"]: entry["code"] for entry in saved_rows(store.load(chat_matter_id(
        "owner", reply["chat_id"])), "owner")[0]["activities"]["calculation"]["not_assessed"]}
    assert codes["Last day for the drawer to pay"] == (
        "the words given for the starting event are not in the conversation or documents as quoted")
    assert codes["Last day to file the complaint"].endswith("which is not a time limit worked out before it")
    assert codes["Last day to give notice"].startswith(
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
    assert record["contract"] == calculation.CONTRACT == "core_calculation_v7"
    assert record["correction"]["state"] == "corrected" and [r["id"] for r in record["correction"]["refused"]] == ["bad"]
    assert record["proposal"] == chain() and record["not_assessed"] == []
    assert saved_rows(store.load(chat_matter_id("owner", reply["chat_id"])), "owner")[0]["response"][
        "elements"] == reply["elements"]  # the corrected limit replays from the saved record


def test_a_step_taken_quoted_from_the_event_time_runs_from_is_refused_then_corrected(store):
    """Two of three live runs (18 Oct 2026) gave the delivery as the price suit's step taken,
    so an unfiled suit read "in time": the words of the event time runs from are never the
    step taken, and the correction is told why."""
    proposal = chain()
    pay = proposal["calculations"][0]
    pay["done"] = {"what": "notice delivered", "date": "2026-08-29", "quote": "Notice was delivered on 29 August 2026"}
    corrected = deepcopy(pay)
    corrected["done"] = {"what": "", "date": "", "quote": ""}
    model = Calculating(proposal, correction={"calculations": [corrected, fixed_bad()], "cannot": []})
    reply = turn(store, model)
    prompt, = model.seen["correction"]
    assert "- c1 (Last day for the drawer to pay): the step taken is quoted from the words of the event time " \
           "runs from" in prompt.user
    assert 'Under "done", give the step this time limit governs only if' in model.seen["calculation"].system
    boxes = {e["text"]: e["working"] for e in reply["elements"] if e["kind"] == "WORKING"}
    pay_box = boxes["Last day for the drawer to pay"]
    assert pay_box["last_day"] == "2026-09-13" and pay_box["step_taken"] is None
    assert not any(label == "Taken on" for label, _ in pay_box["rows"])
    # Without a correction it stays not assessed, with the reason.
    plain = Calculating(deepcopy(proposal), correction={"calculations": [], "cannot": [
        {"id": "c1", "why": "The advocate gives no payment."}]})
    second = run(store, plain, message=MESSAGE, held_acts=Held(), turn_id="t-uncorrected")  # a new conversation
    boxes = {e["text"]: e["working"] for e in second["elements"] if e["kind"] == "WORKING"}
    # P36 (v7): told plainly, with the model's own reason; code's reason kept in the record.
    assert boxes["Last day for the drawer to pay"]["not_assessed"] == (
        f"{calculation.UNCHECKED_WORKING}; on a second look: The advocate gives no payment.")
    kept = {entry["what"]: entry for entry in saved_rows(store.load(chat_matter_id("owner", second["chat_id"])),
                                                          "owner")[0]["activities"]["calculation"]["not_assessed"]}
    assert kept["Last day for the drawer to pay"]["code"].startswith(
        "the step taken is quoted from the words of the event time runs from")


def test_a_missing_fact_spends_no_correction_and_what_waits_on_it_says_so_plainly(store):
    """Every live run (18 Oct 2026) spent the time-limit step's one correction on starting
    dates nobody had given; a correction cannot supply a fact. A limit waiting on one that
    could not be worked out names it in plain words, never by its internal ID."""
    proposal = chain()
    pay, complaint, _ = proposal["calculations"]
    pay["start"] = {"after": "", "event": "the drawer receiving the notice", "date": "", "quote": "",
                    "dated_event": "", "same_event": False, "period_words": "", "period_quote": ""}
    pay["missing"] = ["The date the drawer received the notice."]
    proposal["calculations"] = [pay, complaint]  # nothing a correction could fix
    model = Calculating(proposal)
    reply = turn(store, model)
    assert "correction" not in model.seen  # no correction call was made
    boxes = {e["text"]: e["working"] for e in reply["elements"] if e["kind"] == "WORKING"}
    assert boxes["Last day for the drawer to pay"]["not_assessed"] == (
        "the starting date is not given; needed: The date the drawer received the notice.")
    assert boxes["Last day to file the complaint"]["not_assessed"] == (
        "it starts once “Last day for the drawer to pay” ends, and that could not be worked out")
    assert "List only time limits" in model.seen["calculation"].system


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
    assert why == f"{calculation.UNCHECKED_ACT}; on a second look: the held text gives no ninety-day period for this step"


def test_a_correction_that_fails_leaves_the_first_check_standing(store):
    model = Calculating(chain(), correction_fails=ProviderUnavailable("down"))
    reply = turn(store, model)
    boxes = {e["text"]: e["working"] for e in reply["elements"] if e["kind"] == "WORKING"}
    assert boxes["A period misquoted"]["not_assessed"] == calculation.UNCHECKED_ACT
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
        with pytest.raises(calculation._Unchecked, match="not in its held entry") as refused:
            calculation._provision({**item, "words": wrong}, acts, entries)
        # The correction is shown the held entry's own words.
        assert refused.value.near == "For money payable for money lent. Three years When the loan is made."


def test_a_missing_starting_date_is_said_before_any_quotation_is_checked(store):
    """The fifth live run (18 Oct 2026) spent a correction on the quotation of a limit whose
    starting date nobody had given: the missing fact is what the advocate needs to hear."""
    proposal = chain()
    pay, complaint, _ = proposal["calculations"]
    pay["start"] = {"after": "", "event": "the drawer receiving the notice", "date": "", "quote": "",
                    "dated_event": "", "same_event": False, "period_words": "", "period_quote": ""}
    pay["words"] = "words the Act does not say"
    proposal["calculations"] = [pay, complaint]
    model = Calculating(proposal)
    boxes = {e["text"]: e["working"] for e in turn(store, model)["elements"] if e["kind"] == "WORKING"}
    assert "correction" not in model.seen
    assert boxes["Last day for the drawer to pay"]["not_assessed"] == "the starting date is not given"


def test_a_start_its_own_check_says_dates_another_event_is_not_given_and_spends_no_correction():
    """Q16 (owner, 19 Oct 2026): in two of three live runs the step dated the payee's thirty
    days for the demand notice from the bank's return of the cheque, not from the payee
    receiving the bank's information. Where the step's own check says the words it quotes date
    another event, the date stays not given and the limit is not worked out; the missing date
    is a fact no correction can supply."""
    from tests.test_core_understanding import context
    notice = step("n1", "Last day for the demand notice",
                  "within thirty days of the receipt of information by him from the bank regarding the return of "
                  "the cheque as unpaid", "thirty days",
                  {"after": "", "event": "the payee receiving the bank's information", "date": "2026-08-18",
                   "quote": "18 August 2026", "dated_event": "the bank returning the cheque", "same_event": False,
                   "period_words": "", "period_quote": ""})
    model = Calculating({"needed": True, "why": "The advocate asks about the notice.", "not_assessed": [],
                         "calculations": [notice]})
    record = calculation.work_out(model, context(MESSAGE), Held())
    assert record["calculations"] == [] and "correction" not in model.seen
    assert record["not_assessed"] == [{"what": "Last day for the demand notice", "why": (
        "the words quoted date the bank returning the cheque, not the event time runs from (the payee receiving the "
        "bank's information), whose date is not given")}]
    # Its own check confirming the very event, the same words are worked out.
    notice["start"].update(dated_event="the payee receiving the bank's return memo", same_event=True)
    confirmed = calculation.work_out(Calculating({"needed": True, "why": "", "not_assessed": [],
                                                  "calculations": [notice]}), context(MESSAGE), Held())
    assert [entry["working"]["last_day"] for entry in confirmed["calculations"]] == ["2026-09-17"]
    assert "Check that the words you quote date that very event" in calculation.SYSTEM



CREDIT_SALE = ("My client delivered a consignment worth Rs 2,10,000 on 10 March 2024 on 30 days' credit. Sai Traders "
               "accepted the goods but never paid.")


class CreditHeld(Held):
    """The Limitation Act's Schedule with Article 15 beside Article 19."""

    def read(self, title):
        held = super().read(title)
        if title == LIMITATION:
            text = held["text"].replace("19\nFor money", (
                "15\nFor the price of goods sold and delivered to be paid for after the expiry of a fixed period of "
                "credit.\nThree years\nWhen the period of credit expires.\n19\nFor money"))
            held = {**held, "text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}
        return held


def price_suit(**start):
    return step("p1", "Suit for the price of the consignment", "Three years; When the period of credit expires",
                "Three years", {"after": "", "event": "the period of credit expiring", "date": "2024-03-10",
                                "quote": "delivered a consignment worth Rs 2,10,000 on 10 March 2024",
                                "dated_event": "the delivery", "same_event": True, "period_words": "30 days",
                                "period_quote": "on 30 days' credit", **start},
                act=LIMITATION, provision="Article 15", article="15")


def test_a_limit_running_from_the_end_of_a_period_the_facts_set_is_worked_out_from_both_facts():
    """P34 (owner, 21 Oct 2026): live runs 2-4 left a suit for the price not worked out. Article 15
    runs "when the period of credit expires"; the advocate gave the delivery date and the credit,
    not the credit's end. Code counts the credit's end from both quoted facts; the Act's three
    years run from it, and the record says how."""
    from tests.test_core_understanding import context
    proposal = {"needed": True, "why": "A suit for the price.", "not_assessed": [], "calculations": [price_suit()]}
    ctx = context(CREDIT_SALE)
    record = calculation.work_out(Calculating(proposal), ctx, CreditHeld())
    (entry,) = record["calculations"]
    assert entry["start"]["date"] == "2024-04-09" and entry["working"]["last_day"] == "2027-04-09"
    agreed = entry["start"]["agreed"]
    assert agreed["runs_from"]["date"] == "2024-03-10" and agreed["period"]["quote"] == "on 30 days' credit"
    assert entry["assumptions"][-1] == ("The 30 days the facts set are counted from 2024-03-10, that day left out, "
                                        "ending on 2024-04-09; the agreement's own terms may count them differently.")
    assert calculation.validate(record, ctx) == record
    moved = deepcopy(record)
    moved["calculations"][0]["start"]["date"] = "2024-04-10"
    with pytest.raises(ValueError, match="agreed period"):
        calculation.validate(moved, ctx)
    assert "a period of credit, a time agreed for payment or performance" in calculation.SYSTEM


def test_an_agreed_period_not_in_the_words_quoted_for_it_is_not_worked_out():
    from tests.test_core_understanding import context
    proposal = {"needed": True, "why": "", "not_assessed": [],
                "calculations": [price_suit(period_words="45 days")]}
    record = calculation.work_out(Calculating(proposal), context(CREDIT_SALE), CreditHeld())
    assert record["calculations"] == []
    assert record["not_assessed"][0]["why"] == calculation.UNCHECKED_WORKING
    assert record["not_assessed"][0]["code"].startswith("the agreed period is not within the words quoted")


def test_the_working_box_shows_how_a_start_from_an_agreed_period_was_counted():
    from tests.test_core_understanding import context
    proposal = {"needed": True, "why": "A suit for the price.", "not_assessed": [], "calculations": [price_suit()]}
    record = calculation.work_out(Calculating(proposal), context(CREDIT_SALE), CreditHeld())
    (box,) = response_rendering._working(record)
    rows = dict(box["working"]["rows"])
    assert rows["Runs from"] == response_rendering._date("2024-04-09")
    assert rows["Period the facts set"] == "“30 days”" and rows["Whose words for the period"] == "“on 30 days' credit”"
    assert rows["Counted from"] == response_rendering._date("2024-03-10")
    assert rows["Whose words for that date"] == "“delivered a consignment worth Rs 2,10,000 on 10 March 2024”"
    assert rows["Last day"] == response_rendering._date("2027-04-09")


def test_a_fact_quoted_in_other_words_is_refused_with_the_words_the_advocate_wrote():
    """Live run 8 (the owner's browser, 21 Oct 2026): the step quoted the delivery as "I delivered
    a further consignment ..." where the advocate wrote "my client delivered ...", and its
    correction, told only that the words were not there, quoted them so again; the suit's limit
    was not worked out and the answer said the words were not available. The refusal now shows
    the words the advocate wrote nearest to the quotation, as it does an Act's."""
    from tests.test_core_understanding import context
    misquoted = price_suit(quote="I delivered a consignment worth Rs 2,10,000 on 10 March 2024")
    model = Calculating({"needed": True, "why": "A suit for the price.", "not_assessed": [], "calculations": [misquoted]},
                        correction={"calculations": [price_suit()], "cannot": []})
    ctx = context(CREDIT_SALE)
    record = calculation.work_out(model, ctx, CreditHeld())
    (prompt,) = model.seen["correction"]
    assert ("- p1 (Suit for the price of the consignment): the words given for the date the agreed period runs from "
            "are not in the conversation or documents as quoted. The held text nearest to the words you quoted reads: "
            f"“{CREDIT_SALE}”") in prompt.user
    assert [entry["working"]["last_day"] for entry in record["calculations"]] == ["2027-04-09"]
    assert record["correction"]["refused"][0]["near"] == CREDIT_SALE
    assert calculation.validate(record, ctx) == record
    with pytest.raises(calculation._Unchecked) as nowhere:
        calculation._fact({"date": "2024-03-10", "quote": "words the advocate never wrote at all"},
                          calculation.source_catalogue(ctx), "starting event",
                          calculation._facts_in(ctx, calculation.source_catalogue(ctx)))
    assert nowhere.value.near is None


def test_a_step_said_to_be_taken_without_its_date_is_taken_its_date_not_given(store):
    """P36 (owner, 21 Oct 2026): live run 8 showed a cheque already presented and dishonoured as
    "Open, 122 days left", the step giving the words saying so but no date. A step the facts say
    was taken, but not when, is kept as taken: no days are counted and whether it was in time is
    not known."""
    proposal = chain()
    complaint = proposal["calculations"][1]
    complaint["done"] = {"what": "complaint filed", "date": "", "quote": "We filed the complaint"}
    reply = turn(store, Calculating(proposal))
    box = next(e["working"] for e in reply["elements"] if e["kind"] == "WORKING"
               and e["text"] == "Last day to file the complaint")
    assert box["standing"] == {"state": "taken", "days": None}
    rows = dict(box["rows"])
    assert rows["Taken on"] == "Not given" and rows["Whose words"] == "“We filed the complaint”"
    assert rows["Result"] == "Taken; its date not given, so whether in time is not known"
    assert not [label for label in rows if label.startswith("Days")]
    matter = store.load(chat_matter_id("owner", reply["chat_id"]))
    row = saved_rows(matter, "owner")[0]
    record = row["activities"]["calculation"]
    (taken,) = [entry for entry in record["calculations"] if entry["id"] == "c2"]
    assert taken["done"]["date"] is None and taken["done"]["quote"] == "We filed the complaint"
    (limit,) = [entry for entry in row["records"]["checklist"]["disputes"][0]["time_limits"]
                if entry["what"] == "Last day to file the complaint"] or [None]
    if limit is not None:  # the board's line for it, where the section named it
        assert ["Result", rows["Result"]] in response_rendering.limit_rows(limit)
    from nm.core_engine.conversation import TurnContext
    original = TurnContext(matter, row["chat_id"], row["turn_id"], row["message"], ()).payload()
    assert calculation.validate(record, original) == record
    earlier = deepcopy(record) | {"contract": calculation.V6_CONTRACT}
    with pytest.raises(ValueError, match="v7"):
        calculation.validate(earlier, original)



def test_the_prompt_says_words_that_a_step_is_not_yet_taken_leave_done_empty():
    """P47 (owner, 25 Oct 2026): live run 4 returned, for a message saying no execution petition had
    been filed yet, a 'done' step whose words were those very words, and the answer showed the
    petition as taken. The step's prompt now says words that a step has not been taken, or not yet,
    are not words saying it was, and that done is then left empty."""
    text = " ".join(calculation.SYSTEM.split())
    assert "Words saying the step has not been taken, or not yet, are not words saying it was" in text
    assert 'leave "done" empty (its what, date and quote all empty)' in text
    # The rule it refines stays: a step taken but not when is given with its words and no date.
    assert "quote the words saying so and leave its date empty" in text


def test_a_step_the_facts_say_is_not_yet_taken_stands_open_with_its_days_left():
    """With 'done' left empty, as the prompt now asks, a step not yet taken stands open as of the
    day it was worked out, with its days left: never 'taken'. The same limit with the step said to be
    taken but not when still shows as taken (P36 (a), unchanged)."""
    from datetime import datetime, timezone
    from tests.test_core_understanding import context
    ctx = context(CREDIT_SALE + " No suit has been filed yet.")
    now = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)
    unfiled = {"needed": True, "why": "A suit for the price.", "not_assessed": [], "calculations": [price_suit()]}
    (entry,) = calculation.work_out(Calculating(unfiled), ctx, CreditHeld(), now=now)["calculations"]
    assert entry["done"] is None
    assert entry["standing"] == {"state": "open", "days": 166}  # 25 Oct 2026 to the last day, 9 April 2027
    taken = deepcopy(unfiled)
    taken["calculations"][0]["done"] = {"what": "Suit filed", "date": "", "quote": "No suit has been filed yet"}
    (entry,) = calculation.work_out(Calculating(taken), ctx, CreditHeld(), now=now)["calculations"]
    # Code cannot tell words saying a step was taken from words saying it was not: that is the
    # prompt's to keep right. What code keeps is the rule it was given for a step said to be taken.
    assert entry["standing"] == {"state": "taken", "days": None}
