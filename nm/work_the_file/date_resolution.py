"""Reproducible calendar interpretation, never a model's remembered event date.

This is a bounded calendar grammar, not a legal/event-name classifier. Unsupported
language, missing years, external calendars and ambiguous ranges remain undated.
The original expression survives so a verified source or clarification can resolve
it later. No guessed year, fuzzy date parsing or silent truncation is permitted.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta


_RELATIVE_DAY = {"today": 0, "yesterday": -1, "tomorrow": 1}
_CALENDAR_DATE = r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4}|[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})"
_RELATIVE = r"(?:today|yesterday|tomorrow)"
_APPOSITION = r"\s*(?:,|:|\(|\)|\u2014)\s*"
_DAY_THEN_DATE = re.compile(rf"\b(?P<relative>{_RELATIVE})\b{_APPOSITION}(?P<calendar>{_CALENDAR_DATE})\b", re.I)
_DATE_THEN_DAY = re.compile(rf"\b(?P<calendar>{_CALENDAR_DATE})\b{_APPOSITION}(?P<relative>{_RELATIVE})\b", re.I)


def contextual_reference(message: str, reference: date) -> tuple[date | None, str]:
    """Use a calendar date expressly paired with a relative day in this account.

    A submitted brief may say "yesterday, 27 September 2026" even when opened
    on 29 September. The explicit pair fixes what *yesterday* means throughout
    that same contribution, including a separately scoped dispute. Conflicting
    pairs make relative dates unresolvable; they never fall back to the server
    clock. The second return value is the literal supporting span.
    """
    anchors: list[tuple[date, str]] = []
    for pattern in (_DAY_THEN_DATE, _DATE_THEN_DAY):
        for match in pattern.finditer(message or ""):
            on = resolve(match.group("calendar"), reference)
            if on is None:
                continue
            try:
                anchor = on - timedelta(days=_RELATIVE_DAY[match.group("relative").casefold()])
            except OverflowError:
                continue
            anchors.append((anchor, match.group(0)))
    if not anchors:
        return reference, ""
    if len({anchor for anchor, _ in anchors}) != 1:
        return None, "conflicting explicit relative-date anchors"
    return anchors[0]


def resolve(expression: str, reference: date | None) -> date | None:
    text = " ".join(expression.casefold().strip().split())
    text = re.sub(r"^(?:on|dated)\s+", "", text)
    offset = _RELATIVE_DAY.get(text)
    if offset is not None:
        if reference is None:
            return None
        try:
            return reference + timedelta(days=offset)
        except OverflowError:
            return None
    relative = re.fullmatch(r"(\d+)\s+(days?|weeks?)\s+(ago|before today|after today)", text)
    if relative:
        if reference is None:
            return None
        try:
            days = int(relative[1]) * (7 if relative[2].startswith("week") else 1)
            return reference + timedelta(days=days if relative[3] == "after today" else -days)
        except (OverflowError, ValueError):
            return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text)
        # Do not infer a locale from the installation. Ambiguous day/month
        # order needs clarification; two-digit years are also unsupported.
        numeric = re.fullmatch(r"(\d{1,2})([-/.])(\d{1,2})\2(\d{4})", text)
        if numeric:
            if int(numeric[1]) <= 12 and int(numeric[1]) != int(numeric[3]):
                return None
            return date(int(numeric[4]), int(numeric[3]), int(numeric[1]))
        months = {name.casefold(): i for i in range(1, 13)
                  for name in (calendar.month_name[i], calendar.month_abbr[i])}
        named = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\s+(\d{4})", text)
        if named and named[2] in months:
            return date(int(named[3]), months[named[2]], int(named[1]))
        named = re.fullmatch(r"([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(\d{4})", text)
        if named and named[1] in months:
            return date(int(named[3]), months[named[1]], int(named[2]))
    except ValueError:
        return None
    return None
