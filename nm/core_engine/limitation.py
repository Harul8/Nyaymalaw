"""Limitation arithmetic (owner decisions, 15 Oct 2026; item 9, A4). No storage, network or
model here, and no legal choices.

Which provision governs, which event starts time, which period applies and what may be
left out are read from the Acts' own words (owner's governing principle) by the
calculation step and checked as exact quotations there. This module only does the
arithmetic on them: the starting day is left out (Limitation Act s.12(1); Saketh India
v India Securities on calendar months), and two owner rulings apply only where an Act
is silent, each named in the working when applied:
  - a period whose matching date does not exist ends on the last day of that month;
  - copy time under s.12(2) and (3) counts both the application day and the ready day.
Court closure (s.4) is never applied, only flagged: the court calendar is not held.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

CONTRACT = "core_limitation_arithmetic_v1"
RULING_MISSING_DATE = ("The matching date does not exist in that month, so the period ends on the last day "
                       "of the month (owner's ruling where the Act is silent, 15 Oct 2026).")
RULING_COPY_DAYS = ("Copy time counts both the day the copy was applied for and the day it was ready "
                    "(owner's ruling where the Act is silent, 15 Oct 2026).")
_SMALL = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
          "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
          "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
         "ninety": 90}
_UNIT = re.compile(r"\b(days?|months?|years?)\b", re.I)


class LimitationUnassessed(ValueError):
    """The words give no period this arithmetic can count, or the dates do not fit."""


def _number(tokens):
    total = 0
    for token in tokens:
        if token.isdigit():
            total += int(token)
        elif token in _SMALL:
            total += _SMALL[token]
        elif token in _TENS:
            total += _TENS[token]
        elif token == "hundred":
            total = (total or 1) * 100
        elif token != "and":
            return None
    return total or None


def period_from_words(words):
    """The period the held words state ('Three years', 'within thirty days', 'one month'):
    (number, unit, the exact words read), or None when they state no countable period."""
    for unit in _UNIT.finditer(words or ""):
        before = re.split(r"[\s\-]+", words[:unit.start()].strip())
        for size in range(min(5, len(before)), 0, -1):
            tokens = [token.lower().strip("(),.;:") for token in before[-size:]]
            number = _number(tokens)
            if number is not None and tokens[0] != "and":
                start = words.rfind(before[-size], 0, unit.start())
                name = unit.group(1).lower()
                return number, name if name.endswith("s") else name + "s", words[start:unit.end()]
    return None


def end_of_period(start, number, unit):
    """The last day of a period counted from `start`, that day left out; and any ruling applied."""
    if unit == "days":
        return start + timedelta(days=number), None
    months = number * 12 if unit == "years" else number
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    last = calendar.monthrange(year, month)[1]
    if start.day > last:
        return date(year, month, last), RULING_MISSING_DATE
    return date(year, month, start.day), None


def shown(day):
    return f"{day.day} {day:%B %Y} ({day:%A})"


def copy_days(spans):
    """Days of copy time to leave out, both ends counted (owner's ruling), overlaps once."""
    covered = set()
    for applied, ready in spans:
        if ready < applied:
            raise LimitationUnassessed("A copy cannot be ready before it was applied for.")
        covered.update(applied + timedelta(days=offset) for offset in range((ready - applied).days + 1))
    return len(covered)


def working(start, period_words, *, copies=()):
    """The arithmetic for one period, step by step, with the rulings it applied."""
    period = period_from_words(period_words)
    if period is None:
        raise LimitationUnassessed(f"No countable period in the words {period_words!r}.")
    number, unit, words = period
    end, ruling = end_of_period(start, number, unit)
    steps = [f"The period is “{words}”. Counting starts after {shown(start)}, which is left out; "
             f"{number} {unit} then end on {shown(end)}."]
    rulings = [ruling] if ruling else []
    if ruling:
        steps.append(ruling)
    excluded = copy_days(copies)
    if excluded:
        spans = "; ".join(f"{shown(a)} to {shown(b)}" for a, b in copies)
        end = end + timedelta(days=excluded)
        steps.append(f"Copy time left out: {excluded} days ({spans}), so the last day moves to {shown(end)}.")
        rulings.append(RULING_COPY_DAYS)
        steps.append(RULING_COPY_DAYS)
    return {"contract": CONTRACT, "start": start.isoformat(), "period": {"words": words, "number": number,
            "unit": unit}, "copy_days": excluded, "last_day": end.isoformat(), "steps": steps,
            "rulings": rulings,
            "court_closed": (f"If the court is closed on {shown(end)}, the step may be taken on the day it "
                             "reopens (Limitation Act s.4); the court calendar is not held, so that day is "
                             "not assumed.")}


def standing(last_day, *, today, done_on=None, earliest=None):
    """Where a step stands against its window: done early, in time or late, or still open."""
    if done_on is not None:
        if earliest is not None and done_on < earliest:
            return {"state": "early", "days": (earliest - done_on).days}
        if done_on <= last_day:
            return {"state": "in_time", "days": (last_day - done_on).days}
        return {"state": "late", "days": (done_on - last_day).days}
    if today <= last_day:
        return {"state": "open", "days": (last_day - today).days}
    return {"state": "expired", "days": (today - last_day).days}


_PERIOD_LINE = re.compile(r"^(?:\d+|[A-Za-z]+(?:[\s\-]+[A-Za-z]+){0,3})\s+(?:days?|months?|years?)\.?$")


def schedule(text):
    """The Limitation Act's schedule as held: for each article, its entries in order, each
    with its part, description, period and starting point exactly as the held text gives
    them. An article whose period is not a countable phrase is left out, never guessed."""
    lines = [line.strip() for line in text.splitlines()]
    begin = next((i for i, line in enumerate(lines) if line.upper().startswith("FIRST DIVISION")), None)
    if begin is None:
        return {}
    entries, article, buffer, index = {}, None, [], begin
    while index < len(lines):
        line = lines[index]
        if re.fullmatch(r"\d{1,3}", line) and (article is None or int(line) > int(article)):
            article, buffer = line, []
        elif article and _PERIOD_LINE.match(line) and period_from_words(line) and index + 1 < len(lines):
            description = " ".join(part for part in buffer if part)
            part = re.search(r"\(([a-z])\)\s*[^()]*$", description)
            entries.setdefault(article, []).append({
                "article": article, "part": part.group(1) if part else None,
                "description": description, "period": line, "from": lines[index + 1]})
            buffer, index = [], index + 1
        elif article:
            buffer.append(line)
        index += 1
    return entries
