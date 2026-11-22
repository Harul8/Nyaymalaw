"""The public pages say what NM holds, from the library's own records (plan AN.56, piece 56a; D258, the second review of 17 Nov 2026).

The home page and What it holds name how many Acts and judgments NM holds, when the library was last updated, and the Acts themselves.
No figure is typed into a page: each is a marked place (an element with data-held="acts", "judgments", "updated" or "act-list") whose
written words say the figure is not available, and when the page is served these places are filled from the library's records
(nm/arrive/admin_library.py, AdminLibrary.held, the one reader of them). Where the records cannot be read the page is served as it is
written, and says so; it never shows a placeholder or a figure from memory.

This reads public law's descriptions only - no matter, no session - and writes only text, escaped.
"""
from __future__ import annotations

import html
import re
from datetime import date
from typing import Mapping

#: A marked place: an element whose data-held names what fills it; what it holds as written is what a page says without the records.
_PLACE = re.compile(r'(<(?P<tag>span|ul)\b[^>]*\bdata-held="(?P<name>acts|judgments|updated|act-list)"[^>]*>)(?P<body>.*?)(</(?P=tag)>)',
                    re.S)
#: The Acts list keeps its first item, the heading of its columns, as written.
_HEADING = re.compile(r'\A\s*<li class="head">.*?</li>', re.S)
_STANDING = {"in force": "In force", "not in force according to India Code": "Not in force according to India Code"}


def indian(number: int) -> str:
    """A count written the Indian way: 1,393; 34,037; 9,90,668."""
    digits = str(number)
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + groups + [tail])


def _day(day: date) -> str:
    return f"{day.day} {day:%B %Y}"


def _acts(rows) -> str:
    return "".join(
        f'<li><span>{html.escape(title)}</span><span>{html.escape(year) if year else "Year not recorded"}</span>'
        f'<span>{html.escape(_STANDING.get(standing, "Standing not recorded"))}</span></li>'
        for title, year, standing in rows)


def filled(page: str, held: Mapping[str, object] | None) -> str:
    """The page with its marked places filled from held - {"acts", "judgments", "updated", "act_list"}, as AdminLibrary.held gives
    it - or, where held is None (the records cannot be read), the page exactly as written."""
    if held is None:
        return page

    def fill(match):
        name, body = match["name"], match["body"]
        if name == "acts":
            body = indian(held["acts"])
        elif name == "judgments":
            body = indian(held["judgments"])
        elif name == "updated":
            body = _day(held["updated"])
        else:
            heading = _HEADING.match(body)
            body = (heading.group(0) if heading else "") + _acts(held["act_list"])
        return match.group(1) + body + match.group(5)
    return _PLACE.sub(fill, page)
