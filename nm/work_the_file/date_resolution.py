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


def resolve(expression: str, reference: date) -> date | None:
    text = " ".join(expression.casefold().strip().split())
    text = re.sub(r"^(?:on|dated)\s+", "", text)
    offset = {"today": 0, "yesterday": -1, "tomorrow": 1}.get(text)
    if offset is not None:
        try:
            return reference + timedelta(days=offset)
        except OverflowError:
            return None
    relative = re.fullmatch(r"(\d+)\s+(days?|weeks?)\s+(ago|before today|after today)", text)
    if relative:
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
