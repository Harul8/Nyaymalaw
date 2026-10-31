"""The chronology of each document (plan AN.27, P8; invariants I4 and I5).

A bundle of papers was answered from an understanding that held 18 or 19 facts of 56 pages, so what the papers record - a sale chain, the
orders a court recites, the proceedings it lists as pending - was lost between the papers and the answer. Each document is now read for
on its own, all at once, for what it records, event by event; code then finds each event's words on the pages the model was shown, reads
the dates, orders the events and numbers them. From research v13 (plan AN.28, D1-D3) each call answers for one paper's pages with the
rest of the file in view, and an event whose words or date its paper does not hold - or a date on a paper's pages that no event carries -
is looked at again in one check call for that paper. The papers here are synthetic, of the same shape.
"""
import re
import threading

import pytest

from nm.core_engine import research
from nm.core_engine.research import chronology_of, read_date
from nm.shared.model_port import OutputTruncated, SchemaViolation, UsageLimitReached
from tests.test_core_research import _result

pytestmark = pytest.mark.class_a


class Reading:
    """Answers the chronology call from a script keyed by the document's name; a name in `fail` fails as a shape error."""

    def __init__(self, script, fail=(), usage_limit=(), meet=None):
        self.script, self.fail, self.usage_limit, self.meet = script, set(fail), set(usage_limit), meet
        self.calls, self.lock = [], threading.Lock()

    def context_budget(self, tier):
        return 10 ** 9

    def structured(self, prompt, schema, tier, **kwargs):
        name = re.search(r'^Document: "(.*)"', prompt.user, re.M).group(1)
        with self.lock:
            self.calls.append((prompt.operation, name, prompt.user))
        if self.meet is not None and '"to_check"' not in prompt.user:
            self.meet.wait(timeout=10)          # every document's call must be in flight together, or this raises
        if name in self.usage_limit:
            raise UsageLimitReached("the account has no credit")
        if name in self.fail:
            raise SchemaViolation(f"scripted failure for {name}")
        events = self.script.get(name, [])
        return _result({"events": events(prompt.user) if callable(events) else events}, tier)


def row(turn, index, name, number, text, recording=False):
    about = {"name": name, "page": number, "read_by": "local", **({"recording": True} if recording else {})}
    return {"source_id": f"{turn}:d{index}p{number}", "turn_id": turn, "speaker": "document",
            "record_role": "supplied_document", "text": text, "document": about}


def context(*rows):
    return {"documents": list(rows), "conversation": [], "latest": {"text": "Read these."}}


def event(date, kind, what, words, said_by="the document"):
    return {"date": date, "kind": kind, "what": what, "said_by": said_by, "words": words}


DEED = [(1, "Sale Deed No. 100 dated 30-10-1985. The vendor sold Ac.1.18 guntas to the purchasers."),
        (2, "Registered at the Sub-Registrar's office. Mutation was ordered on 17-3-2008 in file B/54/2008.")]
ORDER = [(1, "ORDER. The Joint Collector allowed the revision on 17 August 2019. In the meanwhile revenue officers shall "
             "continue to maintain the name of the original\n\n[stamp: CERTIFIED TO BE TRUE COPY]\n[signature]"),
         (2, "[Handwritten: 4831/-]\n\nowner in the records. Suits O.S. 891 of 2014 and 892 of 2014 are pending before the "
             "District Court.")]
SCRIPT = {
    "deed.pdf": [event("30-10-1985", "transaction", "A sale of Ac.1.18 guntas.", "Sale Deed No. 100 dated 30-10-1985"),
                 event("17-3-2008", "order", "Mutation ordered in file B/54/2008.",
                       "Mutation was ordered on 17-3-2008 in file B/54/2008")],
    "order.pdf": [event("17 August 2019", "order", "The revision was allowed.",
                        "The Joint Collector allowed the revision on 17 August 2019", "the Joint Collector"),
                  event("undated", "order", "Revenue officers to keep the original owner's name in the records.",
                        "revenue officers shall continue to maintain the name of the original owner in the records"),
                  event("undated", "pending", "Two suits are pending.",
                        "Suits O.S. 891 of 2014 and 892 of 2014 are pending before the District Court"),
                  event("1 January 2020", "filing", "A petition was filed.", "The petition was filed on a day the page lacks")],
}


def papers():
    return context(*[row("t1", 1, "deed.pdf", n, text) for n, text in DEED],
                   *[row("t1", 2, "order.pdf", n, text) for n, text in ORDER])


def reads(model):
    """The reading calls, not the check calls."""
    return [call for call in model.calls if '"to_check"' not in call[2]]


def test_each_document_is_read_for_on_its_own_with_the_rest_of_the_file_in_view():
    model = Reading(SCRIPT)
    events, failures = chronology_of(model, papers())
    assert failures == []
    assert sorted(name for _, name, _ in reads(model)) == ["deed.pdf", "order.pdf"]
    for operation, name, seen in reads(model):
        assert operation == "core_research_chronology"
        other = "order.pdf" if name == "deed.pdf" else "deed.pdf"
        mine, rest = seen.split("The pages you read for:")[1], seen.split("The pages you read for:")[0]
        assert f'Document: "{name}"' in mine and f'Paper "{other}"' in rest, "the rest of the file is in view, before its pages"
        assert "The advocate's messages, oldest first:\n- Read these." in rest
    # The order's last event quotes words its pages do not hold: one check call for that paper looks again.
    (_, name, checked), = [call for call in model.calls if '"to_check"' in call[2]]
    assert name == "order.pdf" and "The petition was filed on a day the page lacks" in checked
    assert [(e["id"], e["sort"], e["document"], e["pages"], e["anchored"]) for e in events] == [
        ("E1", "1985-10-30", "deed.pdf", [1], True),
        ("E2", "2008-03-17", "deed.pdf", [2], True),
        ("E3", "2019-08-17", "order.pdf", [1], True),
        ("E4", "2020-01-01", "order.pdf", [], False),
        ("E5", "", "order.pdf", [1, 2], True),
        ("E6", "", "order.pdf", [2], True)]
    assert events[0]["what"] == "A sale of Ac.1.18 guntas." and events[0]["date"] == "30-10-1985" and events[0]["kind"] == "transaction"
    assert events[2]["said_by"] == "the Joint Collector" and events[4]["date"] == "undated"
    assert all(e["source"] in ("t1:d1", "t1:d2") for e in events)


def test_a_sentence_that_runs_over_a_page_break_is_anchored_to_both_pages_and_a_made_up_one_to_neither():
    events, _ = chronology_of(Reading(SCRIPT), papers())
    by_id = {e["id"]: e for e in events}
    assert by_id["E5"]["pages"] == [1, 2] and by_id["E5"]["anchored"] is True
    assert by_id["E4"]["pages"] == [] and by_id["E4"]["anchored"] is False, "kept, never cited as sourced"


def test_an_event_with_no_words_is_not_anchored():
    model = Reading({"deed.pdf": [event("1985", "other", "Something.", "")]})
    (found,), _ = chronology_of(model, context(row("t1", 1, "deed.pdf", 1, "Text.")))
    assert found["anchored"] is False and found["pages"] == []


def test_a_stretch_whose_call_failed_is_a_failure_not_an_empty_success():
    events, failures = chronology_of(Reading(SCRIPT, fail=["order.pdf"]), papers())
    assert failures == [{"document": "order.pdf", "pages": "1-2", "reason": "SchemaViolation"}]
    assert [e["document"] for e in events] == ["deed.pdf", "deed.pdf"]


def test_a_usage_limit_still_stops_the_turn():
    with pytest.raises(UsageLimitReached):
        chronology_of(Reading(SCRIPT, usage_limit=["deed.pdf"]), papers())


def test_a_long_document_is_read_in_stretches_and_every_page_is_read_once(monkeypatch):
    monkeypatch.setattr(research, "CHRONOLOGY_WINDOW", 130)
    pages = [(n, f"Page {n} of the long order: on {n}-1-2020 the court listed matter number {n}.") for n in range(1, 7)]
    model = Reading({"long.pdf": lambda seen: [
        event(f"{n}-1-2020", "order", f"Listed {n}.", f"on {n}-1-2020 the court listed matter number {n}")
        for n in range(1, 7) if f"[Page {n}]" in seen]})
    events, failures = chronology_of(model, context(*[row("t1", 1, "long.pdf", n, text) for n, text in pages]))
    shown = [sorted(int(n) for n in re.findall(r"\[Page (\d+)\]", seen)) for _, _, seen in model.calls]
    assert len(shown) >= 3 and sorted(n for stretch in shown for n in stretch) == [1, 2, 3, 4, 5, 6]
    assert all(len(stretch) <= 2 for stretch in shown), "a stretch holds at most what the limit allows"
    assert failures == [] and [e["sort"] for e in events] == [f"2020-01-0{n}" for n in range(1, 7)]
    assert all(e["anchored"] for e in events)


def test_an_event_is_anchored_by_its_words_in_its_own_document_and_never_in_another(monkeypatch):
    monkeypatch.setattr(research, "CHRONOLOGY_WINDOW", 130)
    pages = [(1, "The first page says the deed was signed on 3-3-1999 at the registry."),
             (2, "The second page says the order was passed on 4-4-2000 by the court.")]
    model = Reading({"long.pdf": lambda seen: [event("4-4-2000", "order", "An order.", "the order was passed on 4-4-2000 by the court")]
                     if "[Page 1]" in seen else [],
                     "other.pdf": [event("1999", "other", "A deed.", "the deed was signed on 3-3-1999 at the registry")]})
    events, _ = chronology_of(model, context(*[row("t1", 1, "long.pdf", n, text) for n, text in pages],
                                             row("t1", 2, "other.pdf", 1, "Nothing is said here of any deed.")))
    by_document = {e["document"]: e for e in events}
    assert (by_document["long.pdf"]["anchored"], by_document["long.pdf"]["pages"]) == (True, [2]), "anywhere in its own document"
    assert by_document["other.pdf"]["anchored"] is False and by_document["other.pdf"]["pages"] == [], "not in another's"


def test_two_files_of_one_name_are_two_documents():
    model = Reading({"deed.pdf": [event("1985", "other", "Something.", "Sale Deed")]})
    events, _ = chronology_of(model, context(row("t1", 1, "deed.pdf", 1, "Sale Deed one of 1985."),
                                              row("t2", 1, "deed.pdf", 1, "Sale Deed two of 1985.")))
    assert len(model.calls) == 2 and sorted(e["source"] for e in events) == ["t1:d1", "t2:d1"]


def test_the_documents_are_read_at_the_same_time():
    model = Reading(SCRIPT, meet=threading.Barrier(2))
    events, failures = chronology_of(model, papers())
    assert failures == [] and len(events) == 6


def test_a_recording_is_read_by_its_parts():
    model = Reading({"call.mp3": [event("1 May 2020", "other", "The sum was agreed.", "we agreed the sum")]})
    events, _ = chronology_of(model, context(row("t1", 1, "call.mp3", 1, "On 1 May 2020, yes, we agreed the sum.",
                                                 recording=True)))
    (seen,) = [text for _, _, text in model.calls]
    assert 'Document: "call.mp3" (a recording, transcribed by AI)' in seen and "[Part 1]" in seen
    assert events[0]["anchored"] is True


def test_no_documents_and_a_loop_that_is_not_wanted_make_no_calls():
    model = Reading(SCRIPT)
    assert chronology_of(model, {"conversation": [], "latest": {"text": "x"}}) == ([], [])
    assert chronology_of(model, papers(), wanted=lambda: False) == ([], [])
    assert model.calls == []


def test_the_prompt_states_the_message_the_purpose_what_to_look_for_and_the_outcome():
    prompt = research.CHRONOLOGY
    for part in ("Message:", "Purpose:", "Look for:", "Outcome:", "Do not work out, convert or guess a date",
                 "Work in a loop", "You are not judging which account is right", "Who says it."):
        assert part in prompt, part
    assert research.MAX_OUTPUT["chronology"] == 24000 and research.EVENT_KINDS == (
        "transaction", "order", "filing", "pending", "other")


@pytest.mark.parametrize("words,expected", [
    ("30-10-1985", "1985-10-30"), ("30.10.1985", "1985-10-30"), ("30/10/1985", "1985-10-30"), ("5.1-1980", "1980-01-05"),
    ("5th January 1980", "1980-01-05"), ("17 August 2019", "2019-08-17"), ("17th Aug. 2019", "2019-08-17"),
    ("August 17, 2019", "2019-08-17"), ("the 3rd day of March, 1999", "1999-03-03"), ("January 1980", "1980-01"),
    ("in 2008", "2008"), ("1961-62", "1961"), ("10-10-1955", "1955-10-10"), ("12/11/2020", "2020-11-12"),
    ("Sept 3, 1999", "1999-09-03"), ("order dated 28.06.2021 and 4.6.2019", "2021-06-28"),
    ("10-30-1985", "1985-10-30"),                      # month first only where that is the only way a day is a day
    ("31-02-1999", "1999"), ("32-13-1999", "1999"),   # not a date: the year is all there is
    ("undated", ""), ("", ""), ("market 2019", "2019"), ("the mayor 2019", "2019"),
    ("sold in 1985 and registered on 30-10-1986", "1985"),   # where the words hold more than one date, the first
])
def test_dates_are_read_by_code_day_first_and_never_guessed(words, expected):
    assert read_date(words) == expected


def test_a_date_sorts_as_the_papers_give_it_and_a_partial_date_before_a_full_one_of_its_year():
    assert sorted(["2008-03-17", "2008", "2007-12-31", "2008-01"]) == ["2007-12-31", "2008", "2008-01", "2008-03-17"]


class Truncating(Reading):
    """Answers with more events than the answer holds whenever it is shown more than `holds` pages."""

    def __init__(self, script, holds):
        super().__init__(script)
        self.holds = holds

    def structured(self, prompt, schema, tier, **kwargs):
        if len(re.findall(r"^\[Page \d+\]", prompt.user, re.M)) > self.holds:
            with self.lock:
                self.calls.append((prompt.operation, "truncated", prompt.user))
            raise OutputTruncated("stopped at the output ceiling")
        return super().structured(prompt, schema, tier, **kwargs)


def long_order(pages):
    return context(*[row("t1", 1, "long.pdf", n, f"Page {n} of the long order: on {n}-1-2020 the court listed matter number {n}.")
                     for n in range(1, pages + 1)])


LONG = {"long.pdf": lambda seen: [event(f"{n}-1-2020", "order", f"Listed {n}.", f"on {n}-1-2020 the court listed matter number {n}")
                                  for n in range(1, 13) if f"[Page {n}]" in seen]}


def test_a_stretch_with_more_events_than_one_answer_holds_is_read_again_in_halves():
    model = Truncating(LONG, holds=3)
    events, failures = chronology_of(model, long_order(12))
    assert failures == [] and [e["sort"] for e in events] == [f"2020-01-{n:02d}" for n in range(1, 13)]
    assert all(e["anchored"] for e in events)


def test_a_page_that_is_still_too_long_alone_is_a_failure_that_names_it_and_the_rest_is_kept():
    model = Truncating(LONG, holds=0)
    events, failures = chronology_of(model, long_order(2))
    assert events == [] and [f["pages"] for f in failures] == ["1", "2"] and {f["reason"] for f in failures} == {"OutputTruncated"}


def test_the_halving_stops_after_two_rounds():
    model = Truncating(LONG, holds=0)
    _, failures = chronology_of(model, long_order(12))
    assert len(model.calls) == 7 and [f["pages"] for f in failures] == ["1-3", "4-6", "7-9", "10-12"]


def test_the_prompt_gives_a_register_of_many_entries_as_one_event():
    assert "is one event for the whole list" in research.CHRONOLOGY


@pytest.mark.parametrize("words,expected", [("19/07/21", "2021-07-19"), ("5.1.80", "1980-01-05"), ("31/12/99", "1999-12-31"),
                                            ("1-1-30", "2030-01-01"), ("1-1-31", "1931-01-01"), ("19/07/2021", "2021-07-19")])
def test_a_two_digit_year_is_read_by_code(words, expected):
    assert read_date(words) == expected


def test_above_the_limit_each_call_sees_only_the_pages_it_reads_for(monkeypatch):
    # D1 (the owner: "a safe fixed limit like 100k tokens"): a file above it is not shown whole to each call.
    monkeypatch.setattr(research, "WHOLE_FILE_TOKENS", 1)
    model = Reading(SCRIPT)
    chronology_of(model, papers())
    for _, name, seen in reads(model):
        other = "order.pdf" if name == "deed.pdf" else "deed.pdf"
        assert f'Document: "{name}"' in seen and f'"{other}"' not in seen and "The rest of the file" not in seen


def test_a_date_its_paper_never_gives_is_looked_at_again_and_kept_undated_if_still_not_given():
    # Invented: the event's words are on the page, but its date is on no page of the paper.
    model = Reading({"deed.pdf": [event("14-02-2015", "filing", "A counter was filed.", "The counter was filed by the respondents")]})
    (found,), _ = chronology_of(model, context(row("t1", 1, "deed.pdf", 1, "The counter was filed by the respondents.")))
    checked, = [call[2] for call in model.calls if '"to_check"' in call[2]]
    assert "its date is in neither its words nor its pages" in checked
    assert found["anchored"] is True and found["date"] == "undated" and found["sort"] == ""


def test_a_date_on_a_paper_no_event_carries_is_asked_about_and_the_event_it_marks_is_added():
    def answer(seen):
        if '"to_check"' in seen:
            return [event("4-4-2000", "order", "An order was passed.", "the order was passed on 4-4-2000")]
        return [event("3-3-1999", "other", "A deed was signed.", "the deed was signed on 3-3-1999")]
    model = Reading({"deed.pdf": answer})
    events, _ = chronology_of(model, context(row("t1", 1, "deed.pdf", 1, "First the deed was signed on 3-3-1999. Then the "
                                                                           "order was passed on 4-4-2000 by the court.")))
    checked, = [call[2] for call in model.calls if '"to_check"' in call[2]]
    assert '"not_carried": [{"date": "4-4-2000", "page": 1}]' in checked
    assert [(e["sort"], e["anchored"]) for e in events] == [("1999-03-03", True), ("2000-04-04", True)]


def test_a_paper_whose_events_all_check_out_needs_no_check_call():
    model = Reading({"deed.pdf": [event("3-3-1999", "other", "A deed was signed.", "the deed was signed on 3-3-1999")]})
    chronology_of(model, context(row("t1", 1, "deed.pdf", 1, "The deed was signed on 3-3-1999.")))
    assert len(model.calls) == 1


@pytest.mark.parametrize("words,expected", [("-09-2017", "2017-09"), ("09/2017", "2017-09"), ("dated -09-2017", "2017-09"),
                                            ("28-09-2017", "2017-09-28"), ("1961-62", "1961")])
def test_v13_reads_a_numbered_month_and_year_as_that_month(words, expected):
    # Plan AN.28, B10 (invented dates): sorted by its month, not ahead of the year's earlier months.
    assert read_date(words, months=True) == expected and read_date(words) == expected[:4] if len(expected) == 7 else True


def test_the_v13_prompt_dates_an_event_by_when_it_happened_and_lists_a_recited_act_once():
    prompt = research.CHRONOLOGY_V13
    for part in ("Message:", "Purpose:", "Look for:", "Outcome:", "that date is that earlier act's, not this event's",
                 "what the authority found and what it directed", "who brought it and who answers it",
                 "records one event: list it once", "Work in a loop", "Do not work out, convert or guess a date"):
        assert part in prompt, part
    assert "Look again" in research.CHRONOLOGY_CHECK and "not_carried" in research.CHRONOLOGY_CHECK
