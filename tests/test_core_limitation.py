"""Limitation arithmetic against the thirteen scenarios of docs/LIMITATION_SCENARIOS.md
(owner rulings, 15 Oct 2026). The legal inputs here (provision, period words, starting
date, copy dates) are the scenarios' own; choosing them is the calculation step's work.
These prove the arithmetic and the held schedule, not the legal choice.
"""
from datetime import date
from pathlib import Path

import pytest

from nm.core_engine import limitation as L
from nm.shared.held_acts import ActUnavailable, CURRENT_ACTS, HeldActs

pytestmark = pytest.mark.class_a
TODAY = date(2026, 10, 15)
ACTS = Path(__file__).resolve().parents[1] / "legal_database" / "raw_data" / "BareActs"
held = pytest.mark.skipif(not (ACTS / CURRENT_ACTS["The Limitation Act, 1963"]).is_file(),
                          reason="the held bare Acts are not on this machine")


@pytest.mark.parametrize("scenario,start,words,copies,last,state", [
    ("1 money lent", date(2023, 3, 10), "Three years", (), date(2026, 3, 10), "expired"),
    ("2 acknowledgment", date(2025, 2, 1), "Three years", (), date(2028, 2, 1), "open"),
    ("3 part payment", date(2026, 1, 5), "Three years", (), date(2029, 1, 5), "open"),
    ("4 demand note", date(2023, 8, 1), "Three years", (), date(2026, 8, 1), "expired"),
    ("5a fixed date", date(2024, 6, 30), "Three years", (), date(2027, 6, 30), "open"),
    ("5b refusal", date(2024, 2, 12), "Three years", (), date(2027, 2, 12), "open"),
    ("6 leap day", date(2024, 2, 29), "Three years", (), date(2027, 2, 28), "open"),
    ("7 HC appeal", date(2026, 6, 2), "Ninety days", ((date(2026, 6, 5), date(2026, 6, 20)),), date(2026, 9, 16),
     "expired"),
    ("8 district appeal", date(2026, 1, 31), "Thirty days", (), date(2026, 3, 2), "expired"),
    ("9a ex parte served", date(2026, 7, 10), "Thirty days", (), date(2026, 8, 9), "expired"),
    ("9b ex parte knowledge", date(2026, 10, 1), "Thirty days", (), date(2026, 10, 31), "open"),
    ("10 execution", date(2014, 11, 15), "Twelve years", (), date(2026, 11, 15), "open"),
    ("12 Sunday", date(2026, 9, 4), "Thirty days", (), date(2026, 10, 4), "expired"),
], ids=lambda value: value if isinstance(value, str) else None)
def test_each_scenario_s_last_day_and_where_it_stands_today(scenario, start, words, copies, last, state):
    worked = L.working(start, words, copies=copies)
    assert worked["last_day"] == last.isoformat() and worked["start"] == start.isoformat()
    assert L.standing(last, today=TODAY)["state"] == state
    # The working is data only: putting it into words is the writer's work (owner, 15 Oct 2026).
    assert all(not isinstance(value, str) or len(value) <= 40 for value in worked.values())


def test_the_owner_s_rulings_are_applied_only_where_needed_and_named():
    assert L.working(date(2024, 2, 28), "Three years")["rulings"] == []
    assert L.working(date(2024, 2, 29), "Three years")["rulings"] == ["missing_date"]
    assert L.working(date(2026, 1, 31), "one month")["last_day"] == "2026-02-28"
    copy = L.working(date(2026, 6, 2), "Ninety days", copies=((date(2026, 6, 5), date(2026, 6, 20)),))
    assert copy["copy_days"] == 16 and copy["rulings"] == ["copy_time"]
    assert (copy["period_end"], copy["last_day"]) == ("2026-08-31", "2026-09-16")
    assert set(L.RULINGS) == {"missing_date", "copy_time"}
    # Overlapping copy periods (decree and judgment) are left out once.
    assert L.copy_days(((date(2026, 6, 5), date(2026, 6, 10)), (date(2026, 6, 8), date(2026, 6, 12)))) == 8
    with pytest.raises(L.LimitationUnassessed):
        L.copy_days(((date(2026, 6, 10), date(2026, 6, 5)),))


def test_the_cheque_timeline_scenario_11_step_by_step():
    notice = L.working(date(2026, 8, 18), "within thirty days of the receipt of information")
    pay = L.working(date(2026, 8, 29), "within fifteen days of the receipt of the said notice")
    cause = date.fromisoformat(pay["last_day"]).toordinal() + 1
    complaint = L.working(date.fromordinal(cause), "within one month of the date on which the cause of action arises")
    assert (notice["last_day"], pay["last_day"], date.fromordinal(cause).isoformat(), complaint["last_day"]) == (
        "2026-09-17", "2026-09-13", "2026-09-14", "2026-10-14")
    last, earliest = date(2026, 10, 14), date(2026, 9, 14)
    assert L.standing(last, today=TODAY, done_on=date(2026, 9, 12), earliest=earliest) == {"state": "early", "days": 2}
    assert L.standing(last, today=TODAY, done_on=date(2026, 10, 14), earliest=earliest)["state"] == "in_time"
    assert L.standing(last, today=TODAY, done_on=TODAY, earliest=earliest) == {"state": "late", "days": 1}
    assert L.standing(date(2027, 2, 1), today=TODAY, done_on=date(2026, 8, 10))["state"] == "in_time"


@pytest.mark.parametrize("words,expected", [
    ("Three years", (3, "years", "Three years")), ("Twelve years", (12, "years", "Twelve years")),
    ("Ninety days", (90, "days", "Ninety days")), ("within thirty days of the receipt", (30, "days", "thirty days")),
    ("within a period of six months from the date", (6, "months", "six months")),
    ("within one month of the date", (1, "months", "one month")),
    ("one hundred and twenty days", (120, "days", "one hundred and twenty days")),
    ("During the life of the plaintiff", None), ("When the loan is made.", None), ("", None),
])
def test_period_words_are_read_as_written_or_not_at_all(words, expected):
    assert L.period_from_words(words) == expected


@held
def test_the_held_schedule_gives_each_scenario_s_article_word_for_word():
    act = HeldActs(ACTS).read("The Limitation Act, 1963")
    entries = L.schedule(act["text"])
    expected = {"19": [(None, "Three years", "When the loan is made.")],
                "21": [(None, "Three years", "When the loan is made.")],
                "35": [(None, "Three years", "The date of the bill or note.")],
                "116": [("a", "Ninety days", "The date of the decree or order."),
                        ("b", "Thirty days", "The date of the decree or order.")],
                "117": [(None, "Thirty days", "The date of the decree or order.")]}
    for article, rows in expected.items():
        assert [(e["part"], e["period"], e["from"]) for e in entries[article]] == rows
    assert entries["54"][0]["from"].startswith("The date fixed for the performance, or, if no such date is fixed")
    assert entries["123"][0]["period"] == "Thirty days" and entries["136"][0]["period"] == "Twelve years"
    assert len(entries) >= 130 and "105" not in entries  # an uncountable period is left out, never guessed


@held
def test_only_acts_listed_as_current_are_read_and_each_reading_names_its_text():
    acts = HeldActs(ACTS)
    for title in CURRENT_ACTS:
        read = acts.read(title)
        assert read["text"] and len(read["sha256"]) == 64 and read["file"] == CURRENT_ACTS[title]
    # Scenario 13: the held Consumer Protection Act is the repealed 1986 Act.
    with pytest.raises(ActUnavailable, match="not listed as current"):
        acts.read("The Consumer Protection Act, 1986")


def test_an_unreadable_act_is_unavailable_not_empty(tmp_path):
    with pytest.raises(ActUnavailable, match="could not be read"):
        HeldActs(tmp_path).read("The Limitation Act, 1963")
