"""Land extents added up by code (plan AN.27, P13d; invariant I6).

The analysis of the reviewed bundle found that no step adds extents: a model was left to say whether a claim "can be matched", and a
total less two smaller sales that comes to the claimed 6.06 acres was an inference nobody checked. Counting is code's work. This
module reads an extent as a paper writes it - Ac.1.18 guntas, 6 acres 6 guntas, 29 guntas, 150 sq. yards - into guntas (40 to an
acre, 121 square yards to a gunta), renders guntas back as the papers do, and sets out the transfers of each parcel with their sum
and, where a paper states the parcel's whole extent, what that leaves. It reads, adds and subtracts; it decides nothing: a sum is
only of the transfers it was given, each counted once where papers report the same date, parcel, extent and buyer, and says so.
"""
from __future__ import annotations

import re
from fractions import Fraction

GUNTAS_PER_ACRE = 40
SQUARE_YARDS_PER_GUNTA = 121

_NUMBER = r"\d+"
#: Ac.1.18 guntas / Ac. 1-18 / Ac.0.29: acres, then guntas (under 40).
_AC_DOT = re.compile(rf"\bac(?:res?)?\.?\s*({_NUMBER})\s*[.\-]\s*({_NUMBER})(?!\d)(?:\s*guntas?)?", re.I)
#: 6 acres 6 guntas / 6 acres and 6 guntas / 6 ac. 6 g.
_ACRES_GUNTAS = re.compile(rf"\b({_NUMBER})\s*(?:acres?|ac\.?)\s*(?:and\s*)?({_NUMBER})\s*(?:guntas?|gts?\.?)\b", re.I)
#: 6.06 acres: acres and guntas written as a decimal, or decimal acres where the second part is 40 or more.
_DECIMAL_ACRES = re.compile(rf"\b({_NUMBER})\.({_NUMBER})\s*(?:acres?|ac\b\.?)", re.I)
_WHOLE_ACRES = re.compile(rf"\b({_NUMBER})\s*(?:acres?|ac\b\.?)(?!\s*(?:and\s*)?{_NUMBER}\s*guntas?)", re.I)
_GUNTAS = re.compile(rf"\b({_NUMBER})\s*(?:guntas?|gts?\.?)\b", re.I)
_YARDS = re.compile(rf"\b({_NUMBER}(?:\.\d+)?)\s*(?:sq\.?\s*(?:yards?|yds?\.?)|square\s+yards?)", re.I)


def _extents_in(text):
    """The extents in some words, each once: a match inside another match (the guntas of "6 acres 6 guntas") is part of it, not a
    second extent."""
    found = []
    for pattern, how in ((_AC_DOT, "acres.guntas"), (_ACRES_GUNTAS, "acres and guntas"), (_DECIMAL_ACRES, "decimal"),
                         (_WHOLE_ACRES, "acres"), (_GUNTAS, "guntas"), (_YARDS, "square yards")):
        found += [(match.start(), match.end(), how, match) for match in pattern.finditer(text)]
    found.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    kept = []
    for item in found:
        if not any(other[0] <= item[0] and item[1] <= other[1] for other in kept):
            kept.append(item)
    return kept


def _guntas(how, parts):
    """The guntas an extent written one of the ways comes to: (guntas, how), or (None, why not)."""
    if how in ("acres.guntas", "acres and guntas"):
        acres, guntas = int(parts[0]), int(parts[1])
        if guntas >= GUNTAS_PER_ACRE:
            return None, "the guntas are 40 or more"
        return Fraction(acres * GUNTAS_PER_ACRE + guntas), how
    if how == "decimal":
        acres, after = int(parts[0]), parts[1]
        if len(after) == 2 and int(after) < GUNTAS_PER_ACRE:
            return Fraction(acres * GUNTAS_PER_ACRE + int(after)), "acres and guntas written 6.06"
        return (acres + Fraction(int(after), 10 ** len(after))) * GUNTAS_PER_ACRE, "decimal acres"
    if how == "acres":
        return Fraction(int(parts[0]) * GUNTAS_PER_ACRE), how
    if how == "guntas":
        return Fraction(int(parts[0])), how
    return Fraction(parts[0]) / SQUARE_YARDS_PER_GUNTA, how


def parse(words):
    """An extent as a paper writes it, in guntas: (guntas as a Fraction, how it was read), or (None, why not). Read as the paper
    writes it and no other way; where two readings are possible the way is said (6.06 acres is 6 acres 6 guntas, a paper's own
    notation, unless the part after the point is 40 or more, when it is decimal acres); more than one extent in the words, or none, is
    not read."""
    kept = _extents_in(" ".join(str(words).split()))
    if not kept:
        return None, "no extent in these words"
    if len(kept) > 1:
        return None, "more than one extent in these words"
    return _guntas(kept[0][2], kept[0][3].groups())


def render(guntas):
    """Guntas as the papers say an extent: '6 acres 6 guntas (Ac.6.06)'; a minus sign for less than nothing; a gunta that is not whole
    to two places."""
    sign = "-" if guntas < 0 else ""
    guntas = abs(Fraction(guntas))
    acres, rest = divmod(guntas, GUNTAS_PER_ACRE)
    whole = rest.denominator == 1
    shown = str(int(rest)) if whole else f"{float(rest):.2f}"
    words = " ".join(part for part in (
        f"{int(acres)} acre{'s' if acres != 1 else ''}" if acres else "",
        f"{shown} gunta{'s' if rest != 1 else ''}" if rest or not acres else "") if part)
    return f"{sign}{words} (Ac.{int(acres)}.{int(rest):02d})" if whole else f"{sign}{words}"


_SURVEY = re.compile(r"\b(?:survey|sy|s)\.?\s*(?:nos?|numbers?)?\.?\s*", re.I)


def parcel_key(parcel):
    """A parcel as one key: 'Sy.No.487/A' and 'Survey No. 487 / A' are one; 487 and 487/A are two."""
    text = _SURVEY.sub(" ", " ".join(str(parcel).split()), count=1)
    return re.sub(r"[^a-z0-9/]", "", text.casefold())


def _who(name):
    return re.sub(r"[^a-z0-9]", "", str(name).casefold())


def ledger(transfers):
    """The transfers of each parcel, added up. transfers: dicts with id, parcel, extent, total, to, sort, kind, document, pages.
    A parcel with no key is left out. Returns one entry per parcel, in the papers' order:
      transfers - each distinct transfer once (the same date, parcel, extent and buyer reported by several papers is one, with every
                  paper that reports it), its extent in guntas and how it was read;
      unread - those whose extent could not be read, with why, never added;
      sum - what the transfers read add up to, and 'complete' whether every transfer of the parcel was read;
      totals - each different whole extent a paper states for the parcel, and what it leaves after the sum (only where every
               transfer was read)."""
    parcels = {}
    for transfer in transfers:
        key = parcel_key(transfer.get("parcel", ""))
        if not key:
            continue
        entry = parcels.setdefault(key, {"parcel": " ".join(str(transfer["parcel"]).split()), "_seen": {}, "transfers": [],
                                         "unread": [], "_totals": {}})
        who = {"document": transfer["document"], "pages": list(transfer["pages"]), "id": transfer["id"]}
        if transfer.get("total", "").strip():
            value, how = parse(transfer["total"])
            stated = entry["_totals"].setdefault(" ".join(transfer["total"].split()), {"text": " ".join(transfer["total"].split()),
                                                                                       "guntas": value, "how": how, "ids": []})
            stated["ids"].append(transfer["id"])
        value, how = parse(transfer["extent"])
        if value is None:
            entry["unread"].append({"id": transfer["id"], "extent": " ".join(str(transfer["extent"]).split()), "why": how, **{
                k: who[k] for k in ("document", "pages")}})
            continue
        identity = (transfer.get("sort", ""), value, _who(transfer.get("to", "")))
        seen = entry["_seen"].get(identity)
        if seen is not None:
            seen["papers"].append({k: who[k] for k in ("document", "pages")})
            seen["ids"].append(transfer["id"])
            continue
        made = {"ids": [transfer["id"]], "date": transfer.get("date", ""), "kind": transfer.get("kind", ""),
                "to": transfer.get("to", ""), "extent": " ".join(str(transfer["extent"]).split()), "guntas": value, "how": how,
                "papers": [{k: who[k] for k in ("document", "pages")}]}
        entry["_seen"][identity] = made
        entry["transfers"].append(made)
    out = []
    for entry in parcels.values():
        total = sum((t["guntas"] for t in entry["transfers"]), Fraction(0))
        complete = not entry["unread"]
        totals = [{"text": s["text"], "guntas": s["guntas"], "how": s["how"], "ids": s["ids"],
                   "leaves": (s["guntas"] - total) if complete and s["guntas"] is not None else None}
                  for s in entry["_totals"].values()]
        out.append({"parcel": entry["parcel"], "transfers": entry["transfers"], "unread": entry["unread"], "sum": total,
                    "complete": complete, "totals": totals})
    return out


#: What every ledger says of itself: a sum is only of what was found.
CAVEAT = ("Only the transfers NM found are added, each counted once where papers report the same date, parcel, extent and buyer; a "
          "transfer NM did not find, or a buyer named two ways, makes the sum wrong. Check it against the papers.")


def shown(transfers):
    """The ledger in words, as the board, the writer and the review are given it: every extent and sum rendered as the papers write
    it, how each was read, which papers report each transfer, and the caveat."""
    out = []
    for parcel in ledger(transfers):
        out.append({
            "parcel": parcel["parcel"],
            "transfers": [{"ids": t["ids"], "date": t["date"], "kind": t["kind"], "to": t["to"], "extent": t["extent"],
                           "in_guntas": render(t["guntas"]), "read_as": t["how"], "papers": t["papers"]}
                          for t in parcel["transfers"]],
            "not_read": parcel["unread"],
            "sum": render(parcel["sum"]) if parcel["transfers"] else None,
            "complete": parcel["complete"],
            "totals": [{"text": s["text"], "read_as": s["how"], "as": render(s["guntas"]) if s["guntas"] is not None else None,
                        "ids": s["ids"], "leaves": render(s["leaves"]) if s["leaves"] is not None else None}
                       for s in parcel["totals"]],
            "caveat": CAVEAT})
    return out
