"""Land extents added up by code (plan AN.27, P13d; invariant I6).

The analysis of the reviewed bundle found that no step adds extents: a model was left to say whether a claim "can be matched", and a
total less two smaller sales that comes to the claimed 6.06 acres was an inference nobody checked. Counting is code's work. This
module reads an extent as a paper writes it - Ac.1.18 guntas, 6 acres 6 guntas, 29 guntas, 150 sq. yards - into guntas (40 to an
acre, 121 square yards to a gunta), renders guntas back as the papers do, and sets out the transfers of each parcel seller by seller,
each seller's sales added to that seller's alone (P20 (a)), with what a paper's stated whole extent leaves after them or how far they
go beyond it. It reads, adds and subtracts; it decides nothing: a sum is
only of the transfers it was given, each counted once where papers report the same date, parcel, extent and buyer - or the same
date, extent and kind on pages that are copies of one page, however a name was read (P20 (b)) - and says so.
"""
from __future__ import annotations

import re
from fractions import Fraction

GUNTAS_PER_ACRE = 40
SQUARE_YARDS_PER_GUNTA = 121

_NUMBER = r"\d+"
#: Ac.1.18 guntas / Ac. 1-18 / Ac.0.29 / Acs.2-20 gts.: acres, then guntas (under 40), the papers' own abbreviations included.
_AC_DOT = re.compile(rf"\bac(?:res?|s)?\.?\s*({_NUMBER})\s*[.\-]\s*({_NUMBER})(?!\d)(?:\s*(?:guntas?|gts?\.?))?", re.I)
#: 6 acres 6 guntas / 6 acres and 6 guntas / 6 ac. 6 g. / 6 acs 6 gts.
_ACRES_GUNTAS = re.compile(rf"\b({_NUMBER})\s*(?:acres?|acs?\.?)\s*(?:and\s*)?({_NUMBER})\s*(?:guntas?|gts?\.?)\b", re.I)
#: 6.06 acres: acres and guntas written as a decimal, or decimal acres where the second part is 40 or more.
_DECIMAL_ACRES = re.compile(rf"\b({_NUMBER})\.({_NUMBER})\s*(?:acres?|acs?\b\.?)", re.I)
_WHOLE_ACRES = re.compile(rf"\b({_NUMBER})\s*(?:acres?|acs?\b\.?)(?!\s*(?:and\s*)?{_NUMBER}\s*guntas?)", re.I)
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


def _copy_of(entry, sort, value, kind, source, places, copies):
    """The transfer already kept that this one is the same as because they are read on pages that are copies of one page (P20 (b)): the
    same date, extent and kind, reported by another paper than any that already reports it, on a page that copies one of the pages it
    is read on. A name read two ways, as OCR does, cannot tell two papers' copies apart: the pages' words already have."""
    for made in entry["transfers"]:
        where = entry["_where"][id(made)]
        if (where["sort"] == sort and made["guntas"] == value and made["kind"] == kind and source not in where["sources"]
                and any(frozenset({kept, new}) in copies for kept in where["places"] for new in places)):
            return made
    return None


#: What a seller can be recorded as giving away by their own act and have it added to what they sold: a partition allots a share among
#: those who held the land together and a decree is a court's order, so neither is a sale (P20 (a)).
SOLD_KINDS = ("sale", "gift", "settlement")
_NOT_ADDED = {"partition": "a partition allots a share; it is not a sale", "decree": "a court's decree is not the seller's sale",
              "other": "not a sale, a gift or a settlement"}


def _by_seller(transfers):
    """The transfers of one parcel grouped by who is recorded as making them (P20 (a)): a seller's sales, gifts and settlements are
    added to that seller's alone, never to another's - the papers' accounts of rival chains of title are not one holding. Two spellings
    of a name are one seller only where the papers make them so - they are read as the seller of one transaction, such as a sale
    reported on copies of one page, its seller's name read two ways - never because they look alike. A transfer whose seller is not
    named is listed and added to no one."""
    parent = {}

    def find(key):
        while parent.get(key, key) != key:
            key = parent[key]
        return key
    for made in transfers:
        keys = [_who(name) for name in made["sellers"] if _who(name)]
        for other in keys[1:]:
            parent[find(other)] = find(keys[0])
    groups = {}
    for made in transfers:
        keys = [_who(name) for name in made["sellers"] if _who(name)]
        group = groups.setdefault(find(keys[0]) if keys else "", {"names": [], "transfers": [], "not_added": [], "sold": None})
        group["names"].extend(name for name in made["sellers"] if name not in group["names"])
        group["transfers" if made["kind"] in SOLD_KINDS else "not_added"].append(made)
    for key, group in groups.items():
        if key and group["transfers"]:
            group["sold"] = sum((made["guntas"] for made in group["transfers"]), Fraction(0))
    return list(groups.values())


def ledger(transfers, copies=()):
    """The transfers of each parcel, added up seller by seller. transfers: dicts with id, parcel, extent, total, from, to, sort, kind,
    document, pages (and source, the turn's key of the document, where the plan gave it). copies: the pairs of pages that are copies
    of one page, each {(key, page), (key, page)}, as copy_figures.copies finds them. A parcel with no key is left out. Returns one
    entry per parcel, in the papers' order:
      sellers - the parcel's transfers grouped by who made them (_by_seller), in the order they first appear. Each transfer once (the
                same date, parcel, extent and buyer reported by several papers is one, with every paper that reports it; so is the
                same date, extent and kind read on pages that are copies of one page, whatever the buyer's name was read as, every
                reading of it kept in names), its extent in guntas and how it was read; the sales, gifts and settlements added in
                'sold' (None for a seller with none, or with no name), the rest in 'not_added';
      unread - the sales, gifts and settlements whose extent could not be read, with why, never added;
      complete - whether every sale, gift and settlement of the parcel was read;
      totals - each different whole extent a paper states for the parcel (one extent however it is written) and, for each seller who
               sold, what it leaves after that
               seller's sales (only where every transfer was read, and as if that seller held all of it) or how far their sales go
               beyond it (named whether or not every transfer was read: more can only be more)."""
    parcels = {}
    for transfer in transfers:
        key = parcel_key(transfer.get("parcel", ""))
        if not key:
            continue
        entry = parcels.setdefault(key, {"parcel": " ".join(str(transfer["parcel"]).split()), "_seen": {}, "transfers": [],
                                         "unread": [], "_totals": {}, "_where": {}})
        who = {"document": transfer["document"], "pages": list(transfer["pages"]), "id": transfer["id"]}
        if transfer.get("anchored") is False:
            # Words the finder could not find on the paper's pages support no extent: listed, never added, and its stated total
            # is not a stated total.
            entry["unread"].append({"id": transfer["id"], "extent": " ".join(str(transfer["extent"]).split()),
                                    "why": "its words were not found on the page", "document": who["document"], "pages": []})
            continue
        if transfer.get("total", "").strip():
            value, how = parse(transfer["total"])
            written = " ".join(transfer["total"].split())
            # One stated whole is one extent however it is written (Ac.8.24 guntas, Ac.8.24 gts): by its value where it can be read.
            stated = entry["_totals"].setdefault(value if value is not None else written,
                                                 {"text": written, "guntas": value, "how": how, "ids": []})
            stated["ids"].append(transfer["id"])
        value, how = parse(transfer["extent"])
        if value is None and transfer.get("kind", "") in SOLD_KINDS:
            entry["unread"].append({"id": transfer["id"], "extent": " ".join(str(transfer["extent"]).split()), "why": how, **{
                k: who[k] for k in ("document", "pages")}})
            continue
        # A partition, a decree or anything but a sale, gift or settlement is never added, so an extent that cannot be read does not make
        # the parcel incomplete (P20 (d)): it is listed with the extent as written, and why it could not be read.
        sort, name = transfer.get("sort", ""), " ".join(str(transfer.get("to", "")).split())
        seller = " ".join(str(transfer.get("from", "")).split())
        source = transfer.get("source", transfer["document"])
        places = {(source, number) for number in transfer["pages"]}
        identity = (sort, value, _who(name))
        seen = entry["_seen"].get(identity) or _copy_of(entry, sort, value, transfer.get("kind", ""), source, places, copies)
        if seen is not None:
            seen["papers"].append({k: who[k] for k in ("document", "pages")})
            seen["ids"].append(transfer["id"])
            if name and name not in seen["names"]:
                seen["names"].append(name)
            if seller and seller not in seen["sellers"]:
                seen["sellers"].append(seller)
            where = entry["_where"][id(seen)]
            where["sources"].add(source)
            where["places"] |= places
            entry["_seen"].setdefault(identity, seen)
            continue
        made = {"ids": [transfer["id"]], "date": transfer.get("date", ""), "kind": transfer.get("kind", ""),
                "to": transfer.get("to", ""), "names": [name] if name else [], "sellers": [seller] if seller else [],
                "extent": " ".join(str(transfer["extent"]).split()), "guntas": value, "how": how,
                "papers": [{k: who[k] for k in ("document", "pages")}]}
        entry["_seen"][identity] = made
        entry["_where"][id(made)] = {"sort": sort, "sources": {source}, "places": set(places)}
        entry["transfers"].append(made)
    out = []
    for entry in parcels.values():
        complete = not entry["unread"]
        sellers = _by_seller(entry["transfers"])
        totals = []
        for stated in entry["_totals"].values():
            against = []
            for group in sellers:
                if group["sold"] is None or stated["guntas"] is None:
                    continue
                beyond = group["sold"] - stated["guntas"]
                if beyond > 0:
                    against.append({"seller": group["names"][0], "leaves": None, "exceeds": beyond})
                elif complete:
                    against.append({"seller": group["names"][0], "leaves": -beyond, "exceeds": None})
            totals.append({"text": stated["text"], "guntas": stated["guntas"], "how": stated["how"], "ids": stated["ids"],
                           "by_seller": against})
        out.append({"parcel": entry["parcel"], "sellers": sellers, "unread": entry["unread"], "complete": complete, "totals": totals})
    return out


#: What every ledger says of itself: a sum is only of what was found, seller by seller, and adds every account as the papers state it.
CAVEAT = ("Extents are added as the papers state them, whoever states them, seller by seller, and only the transfers NM found are added, "
          "each counted once where papers report the same date, parcel, extent and buyer, or the same date, extent and kind on copies of "
          "one page. A seller's sales are added to that seller's alone; nothing here says who held what or which account is right. "
          "Transfers that are rival, overlapping or the same land described twice are added as if each were separate and true, so a sum "
          "is a figure to check, not an extent anyone holds. A transfer NM did not find, or a buyer or seller named two ways, makes the "
          "sum wrong. Check it against the papers.")


def _in_words(made, **more):
    return {"ids": made["ids"], "date": made["date"], "kind": made["kind"], "to": made["to"], "extent": made["extent"],
            "in_guntas": render(made["guntas"]) if made["guntas"] is not None else None, "read_as": made["how"],
            "papers": made["papers"],
            **({"also_read_as": made["names"][1:]} if len(made["names"]) > 1 else {}), **more}


def shown(transfers, copies=()):
    """The ledger in words, as the board, the writer and the review are given it: for each parcel its sellers, each with the
    transfers added, the ones listed and not added (and why), and what the seller's sales add up to; every extent rendered as the
    papers write it, how each was read, which papers report each transfer (and, where the buyer's name was read two ways on copies
    of a page, both readings); what could not be read; each stated whole extent with, for each seller, what it leaves or how far the
    sales go beyond it; and the caveat. There is no figure for the parcel as a whole."""
    out = []
    for parcel in ledger(transfers, copies):
        out.append({
            "parcel": parcel["parcel"],
            "sellers": [{"names": group["names"],
                         "transfers": [_in_words(made) for made in group["transfers"]],
                         "not_added": [_in_words(made, why=_NOT_ADDED.get(made["kind"], _NOT_ADDED["other"]))
                                       for made in group["not_added"]],
                         "sold": render(group["sold"]) if group["sold"] is not None else None}
                        for group in parcel["sellers"]],
            "not_read": parcel["unread"],
            "complete": parcel["complete"],
            "totals": [{"text": s["text"], "read_as": s["how"], "as": render(s["guntas"]) if s["guntas"] is not None else None,
                        "ids": s["ids"],
                        "by_seller": [{"seller": b["seller"], "leaves": render(b["leaves"]) if b["leaves"] is not None else None,
                                       "exceeds": render(b["exceeds"]) if b["exceeds"] is not None else None}
                                      for b in s["by_seller"]]}
                       for s in parcel["totals"]],
            "caveat": CAVEAT})
    return out
