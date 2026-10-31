"""Figures added up by code (plan AN.27, P13d; AN.28, D3 and D7; AN.29, D9; invariant I6).

A paper records what passes from one person to another - a sum of money, an area, a length, a weight, a volume. Counting is code's
work, never a model's. The model reads a figure into numbers and units from the words of the page, since it knows how papers write
them; code checks that every number stands in those words (and the unit as written), converts by its table of units, and adds - a
giver's figures to that giver's alone, each dimension by itself - never a share, a rate or a period, which are listed as written. It
reads nothing by a notation of its own: the one thing it knows of a unit is its size, in the table below. A sum is only of the
transactions it was given, each counted once where papers report the same date, subject, figure and receiver - or the same date,
figure and kind on pages that are copies of one page, however a name was read - or the same document by the same giver, and says so.
It reads, adds and subtracts; it decides nothing.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from fractions import Fraction

DIMENSIONS = ("money", "area", "length", "mass", "volume")


@dataclass(frozen=True)
class Unit:
    """A unit of measurement: its dimension, its size in that dimension's base unit, how it is said, and the ways a paper may write
    it (the aliases are for finding a figure in words, never for reading one)."""
    dimension: str
    size: Fraction
    one: str
    many: str
    aliases: tuple[str, ...]


def _unit(dimension, size, one, many, *aliases):
    return Unit(dimension, Fraction(size), one, many, tuple(aliases))


#: The units of measurement the papers use, by dimension. The base units are the rupee, the square metre, the metre, the gram and the
#: litre. This table is the only place a unit's size is held; the model names a unit from it and code does the arithmetic.
UNITS = {
    "rupee": _unit("money", 1, "rupee", "rupees", "rupees", "rupee", "rs.", "rs", "inr", "₹"),
    "paise": _unit("money", Fraction(1, 100), "paisa", "paise", "paise", "paisa"),
    "thousand": _unit("money", 1_000, "thousand", "thousand", "thousand"),
    "lakh": _unit("money", 100_000, "lakh", "lakhs", "lakhs", "lakh", "lacs", "lac"),
    "crore": _unit("money", 10_000_000, "crore", "crores", "crores", "crore"),
    "square_metre": _unit("area", 1, "square metre", "square metres", "square metres", "square metre", "square meters",
                          "square meter", "sq. m", "sq.m", "sq m", "m²"),
    "hectare": _unit("area", 10_000, "hectare", "hectares", "hectares", "hectare"),
    "square_foot": _unit("area", Fraction("0.09290304"), "square foot", "square feet", "square feet", "square foot", "sq. ft.",
                         "sq. ft", "sq.ft", "sq ft", "sqft", "sft"),
    "square_yard": _unit("area", Fraction("0.83612736"), "square yard", "square yards", "square yards", "square yard",
                         "sq. yards", "sq. yds", "sq. yd", "sq.yds", "sq yards", "sq yds", "sq yd"),
    "acre": _unit("area", Fraction("4046.8564224"), "acre", "acres", "acres", "acre", "ac.", "ac"),
    "gunta": _unit("area", Fraction("4046.8564224") / 40, "gunta", "guntas", "guntas", "gunta", "gts.", "gts"),
    "cent": _unit("area", Fraction("4046.8564224") / 100, "cent", "cents", "cents", "cent"),
    "metre": _unit("length", 1, "metre", "metres", "metres", "metre", "meters", "meter"),
    "kilometre": _unit("length", 1_000, "kilometre", "kilometres", "kilometres", "kilometre", "km"),
    "centimetre": _unit("length", Fraction(1, 100), "centimetre", "centimetres", "centimetres", "centimetre", "cm"),
    "foot": _unit("length", Fraction("0.3048"), "foot", "feet", "feet", "foot", "ft"),
    "inch": _unit("length", Fraction("0.0254"), "inch", "inches", "inches", "inch"),
    "yard": _unit("length", Fraction("0.9144"), "yard", "yards", "yards", "yard"),
    "mile": _unit("length", Fraction("1609.344"), "mile", "miles", "miles", "mile"),
    "gram": _unit("mass", 1, "gram", "grams", "grams", "gram"),
    "kilogram": _unit("mass", 1_000, "kilogram", "kilograms", "kilograms", "kilogram", "kgs", "kg"),
    "quintal": _unit("mass", 100_000, "quintal", "quintals", "quintals", "quintal"),
    "tonne": _unit("mass", 1_000_000, "tonne", "tonnes", "tonnes", "tonne"),
    "litre": _unit("volume", 1, "litre", "litres", "litres", "litre", "liters", "liter"),
    "millilitre": _unit("volume", Fraction(1, 1000), "millilitre", "millilitres", "millilitres", "millilitre", "ml"),
    "cubic_metre": _unit("volume", 1_000, "cubic metre", "cubic metres", "cubic metres", "cubic metre", "cubic meters"),
}


def _plainly(text):
    """A unit's name or alias with case, spacing, dots and dashes taken away: 'Sq. Ft.', 'sq ft' and 'SQFT' are one."""
    return re.sub(r"[\s.\-_]", "", str(text or "").casefold())


#: Every way a unit may be named - its key, its names and its aliases, tidied - to its key in the table. A model names a unit in plain
#: words as the page does and code finds it here; a unit not here is one code does not convert, and its figure is listed, never added.
_UNIT_NAMED = {_plainly(name): key for key, unit in UNITS.items() for name in (key, unit.one, unit.many, *unit.aliases)}


def unit_named(text):
    """The key in UNITS of the unit a model named, or None where code does not know it."""
    return _UNIT_NAMED.get(_plainly(text))


#: How a figure is said when the papers do not say it in more than one unit.
BASE = {"money": "rupee", "area": "square_metre", "length": "metre", "mass": "kilogram", "volume": "litre"}

#: What a kind of figure that code does not add is, in words (it is listed as the paper writes it). "none" is no figure at all.
LISTED_ONLY = {"share": "a share of a whole: code adds sums of money and quantities only",
               "rate": "a rate: code adds sums of money and quantities only",
               "period": "a period of time: code adds sums of money and quantities only",
               "none": "no figure"}
FIGURE_KINDS = (*DIMENSIONS, *LISTED_ONLY)
#: Why code does not use a reading of a figure that does not stand in the words that record it.
NOT_IN_WORDS = "its numbers are not in the words that record it"


# --- numbers -----------------------------------------------------------------------------------------------------------------

_DIGITS = re.compile(r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?|\d+")
_SMALL_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
                "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
                "eighty": 80, "ninety": 90}
#: A day of the month as papers write it in words: the twelfth, the twenty first.
_ORDINAL_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
                  "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16,
                  "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20, "thirtieth": 30}
_SCALE_WORDS = {"thousand": 1000, "lakh": 10 ** 5, "lakhs": 10 ** 5, "lac": 10 ** 5, "lacs": 10 ** 5, "crore": 10 ** 7,
                "crores": 10 ** 7}
_TOKEN = re.compile(r"[a-z]+", re.I)


def number_of(text):
    """A number as a model wrote it - digits, commas for grouping, one decimal point - as a Fraction, or None."""
    cleaned = str(text if text is not None else "").replace(",", "").replace(" ", "")
    if re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
        return Fraction(cleaned)
    return None


def _worded(text, ordinals=False):
    """Each run of number words some words hold - Two Lakhs Fifty Thousand, one hundred and five, and with ordinals the twelfth or the
    twenty first - as (start, end, value, its words). A run is words side by side, 'and' between two of them included; it needs a
    word below a hundred, so that 'lakhs' after a figure is not a number of its own."""
    small = {**_SMALL_WORDS, **_ORDINAL_WORDS} if ordinals else _SMALL_WORDS
    known = {*small, "hundred", *_SCALE_WORDS}
    tokens = list(_TOKEN.finditer(str(text)))
    runs, run = [], []
    for index, token in enumerate(tokens):
        word = token.group(0).casefold()
        joins = word == "and" and run and index + 1 < len(tokens) and tokens[index + 1].group(0).casefold() in known
        if word in known or joins:
            if run and not re.fullmatch(r"[\s,\-]*", str(text)[run[-1].end():token.start()]):
                runs.append(run)
                run = []
            run.append(token)
        elif run:
            runs.append(run)
            run = []
    if run:
        runs.append(run)
    found = []
    for run in runs:
        words = [token.group(0).casefold() for token in run if token.group(0).casefold() != "and"]
        if not any(word in small for word in words):
            continue
        total = current = 0
        for word in words:
            if word in small:
                current += small[word]
            elif word == "hundred":
                current = (current or 1) * 100
            else:
                total += (current or 1) * _SCALE_WORDS[word]
                current = 0
        found.append((run[0].start(), run[-1].end(), total + current, words))
    return found


def numbers_in_words(text):
    """The numbers some words write in words (plan AN.28, D3): each run's value - Two Lakhs Fifty Thousand, the twelfth, two thousand
    and twenty two - and a year said in two parts (nineteen ninety one) as that year too. For the checks that a figure or a date
    stands in a paper's words, which a paper often writes out."""
    found = set()
    for _, _, value, words in _worded(text, ordinals=True):
        found.add(value)
        small = {**_SMALL_WORDS, **_ORDINAL_WORDS}
        if len(words) > 1 and all(word in small for word in words):
            head, rest = small[words[0]], sum(small[word] for word in words[1:])
            if 10 <= head <= 99 and (head < 20 or rest >= 10) and rest < 100:
                found.add(head * 100 + rest)
    return found


def numbers_in(words):
    """Every number some words hold, as Fractions: each run of digits (so '1.18' holds 1 and 18 as well as 1.18), each decimal, each
    grouped number (2,50,000 is 250000), and each number written in words. What a reading's numbers must be found among."""
    text = str(words)
    found = {Fraction(match.group(0).replace(",", "")) for match in _DIGITS.finditer(text)}
    found |= {Fraction(run) for run in re.findall(r"\d+", text)}
    return found | {Fraction(value) for value in numbers_in_words(text)}


def squash(text):
    """Letters and digits only, in lower case: the form in which a unit as written is looked for among the words."""
    return _tidy(text or "")


# --- reading a figure ----------------------------------------------------------------------------------------------------------

def _read(figure, quantity, words):
    """(dimension, value in the dimension's base unit, how, the units it was written in, failed): or (None, None, why, None, failed).
    failed: the reading the model gave could not be verified against the words (as opposed to a kind of figure code does not add)."""
    quantity = quantity if isinstance(quantity, dict) else {}
    dimension = quantity.get("dimension") or "none"
    parts = quantity.get("parts") or []
    if dimension in LISTED_ONLY:
        if dimension == "none" and str(figure).strip():
            return None, None, "no quantity was read from it", None, True
        return None, None, LISTED_ONLY[dimension], None, False
    if dimension not in DIMENSIONS:
        return None, None, "its kind of figure is not one code adds", None, True
    if not parts:
        return None, None, "no number and unit were read from it", None, True
    total, ladder, numbers = Fraction(0), [], []
    for part in parts:
        part = part if isinstance(part, dict) else {}
        name = unit_named(part.get("unit"))
        if name is None:
            return None, None, "a unit it is read in is not one code can convert", None, True
        unit = UNITS[name]
        if unit.dimension != dimension:
            return None, None, "its units are not all of the kind the figure is", None, True
        number = number_of(part.get("number"))
        if number is None:
            return None, None, "a number read from it is not a number code can read", None, True
        total += number * unit.size
        numbers.append(number)
        ladder.append(name)
    known = numbers_in(words)
    if not (all(number in known for number in numbers) or (dimension == "money" and total in known)):
        return None, None, NOT_IN_WORDS, None, True
    squashed = squash(words)
    if any(squash(part.get("written")) and squash(part.get("written")) not in squashed for part in parts if isinstance(part, dict)):
        return None, None, "the unit as written is not in the words that record it", None, True
    said = " and ".join(f"{_plain(number)} {UNITS[name].many if number != 1 else UNITS[name].one}"
                        for number, name in zip(numbers, ladder, strict=True))
    return dimension, total, f"read from the words as {said}; every number is the page's own", tuple(ladder), False


def read(figure, quantity, words):
    """A figure as the model read it, checked against the words that record it (plan AN.28, D3: the model reads, code verifies):
    (dimension, value in the dimension's base unit, how, the units it was written in) or (None, None, why not, None)."""
    return _read(figure, quantity, words)[:4]


def fault(transaction):
    """Why code cannot use a transaction's figure, or the whole it gives, as the model read them, or None: a number or a unit not in
    the words that record it, units of different kinds, no reading. A kind of figure code does not add - a share, a rate, a period -
    is no fault: it is listed as the paper writes it. Research shows the model what code found, once, before the record is kept."""
    words = transaction.get("words", "")
    failed = _read(transaction.get("figure", ""), transaction.get("quantity"), words)
    if failed[4]:
        return failed[2]
    if str(transaction.get("whole", "")).strip():
        failed = _read(transaction["whole"], transaction.get("whole_quantity"), words)
        if failed[4]:
            return f"the whole it gives: {failed[2]}"
    return None


# --- saying a figure -----------------------------------------------------------------------------------------------------------

def _grouped(number):
    """A whole number grouped as Indian papers group it: 2,50,000."""
    digits = str(number)
    if len(digits) <= 3:
        return digits
    return re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", digits[:-3]) + "," + digits[-3:]


def _half_up(value):
    """A number rounded to a whole number, a half going up (as a paper rounds, not to the even)."""
    return int(Fraction(value) + Fraction(1, 2))


def _plain(value, places=2):
    """A number grouped as the papers group it, to two places where it is not whole."""
    value = Fraction(value)
    sign = "-" if value < 0 else ""
    if value.denominator == 1:
        return f"{sign}{_grouped(abs(int(value)))}"
    whole, part = divmod(_half_up(abs(value) * 10 ** places), 10 ** places)
    return f"{sign}{_grouped(whole)}.{part:0{places}d}"


def render_money(rupees):
    """Rupees as the papers write a sum: 'Rs 2,50,000', with paise where there are any."""
    paise = _half_up(abs(Fraction(rupees)) * 100)
    sign = "-" if Fraction(rupees) < 0 else ""
    whole, part = divmod(paise, 100)
    return f"{sign}Rs {_grouped(whole)}" + (f".{part:02d}" if part else "")


def render(dimension, value, ladder=()):
    """A figure as the papers say it: a sum as 'Rs 2,50,000'; a quantity in the units the papers wrote it in, the largest first, each
    but the last whole - '2 kg 300 g' - and the last to two places where it is not whole."""
    if dimension == "money":
        return render_money(value)
    names = sorted(set(ladder or (BASE[dimension],)), key=lambda name: -UNITS[name].size)
    sign = "-" if Fraction(value) < 0 else ""
    left, words = abs(Fraction(value)), []
    for index, name in enumerate(names):
        unit = UNITS[name]
        if index == len(names) - 1:
            amount = left / unit.size
            if amount or not words:
                words.append(f"{_plain(amount)} {unit.one if amount == 1 else unit.many}")
        else:
            whole, left = divmod(left, unit.size)
            if whole:
                words.append(f"{int(whole)} {unit.one if whole == 1 else unit.many}")
    return sign + " ".join(words)


# --- finding figures in words (for the check that the understanding works out none) -------------------------------------------

_ALIASES = sorted(((alias, name) for name, unit in UNITS.items() for alias in unit.aliases), key=lambda pair: -len(pair[0]))
_ALIAS = "|".join(re.escape(alias) for alias, _ in _ALIASES)
_NUMBER = r"\d+(?:,\d+)*(?:\.\d+)?"
_UNIT_NUMBER = re.compile(rf"(?<![A-Za-z0-9])({_ALIAS})\s*({_NUMBER})", re.I)
_NUMBER_UNIT = re.compile(rf"(?<![\w.,])({_NUMBER})\s*({_ALIAS})(?![A-Za-z0-9])", re.I)
_BY_ALIAS = {alias: name for alias, name in _ALIASES}
#: A scale after a number ('Rs. 7.4 lakhs'): the figure is the number of that scale, found beside, and not the rupees before it.
_SCALED = re.compile(r"\s*(?:thousand|lakhs?|lacs?|crores?)(?![A-Za-z0-9])", re.I)


def quantities_in(text):
    """Each figure some words write as a number with a unit beside it, in either order (Rs.1,260; 12 kg; 3 metres): [(the words as
    written, the number as written, the unit's name)], each once, in the order they stand. Found by the table's aliases alone."""
    found = []
    for match in _UNIT_NUMBER.finditer(text):
        if not _SCALED.match(text, match.end()):
            found.append((match.start(), match.group(0).strip(), match.group(2), _BY_ALIAS[match.group(1).casefold()]))
    for match in _NUMBER_UNIT.finditer(text):
        found.append((match.start(), match.group(0).strip(), match.group(1), _BY_ALIAS[match.group(2).casefold()]))
    seen, out = set(), []
    for start, words, number, name in sorted(found):
        if (start, name) not in seen:
            seen.add((start, name))
            out.append((words, number, name))
    return out


# --- identity ------------------------------------------------------------------------------------------------------------------

def _tidy(text, keep=""):
    """Letters and digits of any script, with the marks that belong to them, in lower case; spacing and punctuation dropped, but for
    the characters in keep."""
    return "".join(ch for ch in str(text).casefold() if ch.isalnum() or unicodedata.category(ch)[0] == "M" or ch in keep)


def subject_key(subject):
    """A subject as one key: the words tidied - case, spacing and punctuation aside, but for a slash - and no more. Two spellings
    nothing links stay two subjects (preserve ambiguity); a model is asked to name a subject the one way wherever it stands."""
    return _tidy(subject, "/")


def _who(name):
    return _tidy(name)


def instrument_key(written):
    """The document a transaction is recorded in, as one key: its numbers in order, a year of four digits taken by its last two, so
    that 'Doc No. 1234/2001' and 'Agreement No. 1234 of 2001' are one. None where it has no number."""
    numbers = re.findall(r"\d+", str(written or ""))
    if not numbers:
        return None
    if len(numbers) > 1 and len(numbers[-1]) == 4:
        numbers[-1] = numbers[-1][-2:]
    return "/".join(str(int(number)) for number in numbers)


# --- the ledger ----------------------------------------------------------------------------------------------------------------

#: What a giver can be recorded as giving by their own act and have it added to what they gave: something sold, given or settled,
#: money lent or paid. A partition allots a share among those who held something together and a decree is a court's order, so
#: neither is the giver's own transfer (P20 (a)); a lease or a mortgage passes use or security, not what the giver holds.
ADDED_KINDS = ("sale", "gift", "settlement", "loan", "payment")
_LISTED_WHY = {"partition": "a partition allots a share; it is not a sale", "decree": "a court's decree is not the giver's own transfer",
               "other": "not a sale, a gift, a settlement, a loan or a payment",
               "lease": "a lease passes use for a time, not what the owner holds",
               "mortgage": "a mortgage is security for a debt, not a sale"}


def _copy_of(entry, sort, figure, kind, source, places, copies):
    """The transaction already kept that this one is the same as because they are read on pages that are copies of one page (P20
    (b)): the same date, figure and kind, reported by another paper than any that already reports it, on a page that copies one of
    the pages it is read on. A name read two ways, as OCR does, cannot tell two papers' copies apart: the pages' words already have."""
    for made in entry["counted"]:
        where = entry["_where"][id(made)]
        if (where["sort"] == sort and (made["dimension"], made["value"]) == figure and made["kind"] == kind
                and source not in where["sources"]
                and any(frozenset({kept, new}) in copies for kept in where["places"] for new in places)):
            return made
    return None


def _by_giver(made_ones):
    """The transactions of one subject grouped by who is recorded as making them (P20 (a)): a giver's sales, gifts, settlements,
    loans and payments are added to that giver's alone, dimension by dimension, never to another's - the papers' accounts of rival
    chains of title are not one holding. Two spellings of a name are one giver only where the papers make them so - they are read as
    the giver of one transaction, such as a sale reported on copies of one page, its giver's name read two ways - never because they
    look alike. A transaction whose giver is not named is listed and added to no one."""
    parent = {}

    def find(key):
        while parent.get(key, key) != key:
            key = parent[key]
        return key
    for made in made_ones:
        keys = [_who(name) for name in made["givers"] if _who(name)]
        for other in keys[1:]:
            parent[find(other)] = find(keys[0])
    groups = {}
    for made in made_ones:
        keys = [_who(name) for name in made["givers"] if _who(name)]
        group = groups.setdefault(find(keys[0]) if keys else "", {"names": [], "counted": [], "listed": [], "added": {}})
        group["names"].extend(name for name in made["givers"] if name not in group["names"])
        group["counted" if made["kind"] in ADDED_KINDS and "twin_of" not in made else "listed"].append(made)
    for key, group in groups.items():
        if key:
            for made in group["counted"]:
                group["added"][made["dimension"]] = group["added"].get(made["dimension"], Fraction(0)) + made["value"]
    return list(groups.values())


def _after(sort, died):
    """Whether a date stands after a recorded death, to the precision both are given to (a year against a day compares by the year)."""
    width = min(len(sort or ""), len(died or ""))
    return bool(width) and sort[:width] > died[:width]


def ledger(transactions, copies=()):
    """The transactions of each subject, added up giver by giver. transactions: dicts with id, subject, figure, quantity (the model's
    reading of the figure), whole and whole_quantity (the whole the same passage states), from, to, sort, kind, document, pages, words
    (the exact words that record it), anchored, and where given source (the turn's key of the document), instrument (the number of
    the document that records it), giver_died and giver_died_sort. copies: the pairs of pages that are copies of one page, each
    {(key, page), (key, page)}, as copy_figures.copies finds them. A transaction with no subject is left out. Returns one entry per
    subject, in the papers' order:
      givers - its transactions grouped by who made them (_by_giver), in the order they first appear. Each transaction once (the same
               date, subject, figure and receiver reported by several papers is one, with every paper that reports it; so is the same
               date, figure and kind read on pages that are copies of one page, whatever the receiver's name was read as, every
               reading of it kept in names; and so is one document reported again by its own giver or with none named, while one
               another paper reports with another giver is listed under that giver, linked to it and not added again), its figure,
               its dimension and how it was read, and a remark where it is dated after the giver's recorded death; the sales, gifts,
               settlements, loans and payments added in 'added', dimension by dimension (empty for a giver with none, or with no
               name), the rest in 'listed';
      unread - the sales, gifts, settlements, loans and payments whose figure could not be read or added, with why, never added;
      complete - whether every one of them was added;
      totals - each different whole a paper states for it (one figure however it is written) and, for each giver who gave in its
               dimension, what it leaves after that giver's figures (only where every transaction was added, and as if all of it was
               that giver's) or how far their figures go beyond it (named whether or not every transaction was added: more can only
               be more)."""
    subjects = {}
    for transaction in transactions:
        key = subject_key(transaction.get("subject", ""))
        if not key:
            continue
        entry = subjects.setdefault(key, {"subject": " ".join(str(transaction["subject"]).split()), "_seen": {}, "counted": [],
                                          "unread": [], "_totals": {}, "_where": {}, "_instruments": {}})
        who = {"document": transaction["document"], "pages": list(transaction["pages"]), "id": transaction["id"]}
        figure = " ".join(str(transaction.get("figure", "")).split())
        if transaction.get("anchored") is False:
            # Words the finder could not find on the paper's pages support no figure: listed, never added, and its stated whole
            # is not a stated whole.
            entry["unread"].append({"id": transaction["id"], "figure": figure, "why": "its words were not found on the page",
                                    "document": who["document"], "pages": []})
            continue
        words = transaction.get("words", "")
        if str(transaction.get("whole", "")).strip():
            dimension, value, how, ladder, _ = _read(transaction["whole"], transaction.get("whole_quantity"), words)
            written = " ".join(str(transaction["whole"]).split())
            # One stated whole is one figure however it is written: by its value where it can be read.
            stated = entry["_totals"].setdefault((dimension, value) if value is not None else written,
                                                 {"text": written, "dimension": dimension, "value": value, "how": how,
                                                  "ladder": ladder, "ids": []})
            stated["ids"].append(transaction["id"])
        dimension, value, how, ladder, _ = _read(transaction.get("figure", ""), transaction.get("quantity"), words)
        if value is None and transaction.get("kind", "") in ADDED_KINDS:
            entry["unread"].append({"id": transaction["id"], "figure": figure, "why": how, **{
                k: who[k] for k in ("document", "pages")}})
            continue
        # A partition, a decree or anything that is not added is never added, so a figure that cannot be read does not make the
        # subject incomplete (P20 (d)): it is listed with the figure as written, and why it could not be read.
        sort, name = transaction.get("sort", ""), " ".join(str(transaction.get("to", "")).split())
        giver = " ".join(str(transaction.get("from", "")).split())
        source = transaction.get("source", transaction["document"])
        places = {(source, number) for number in transaction["pages"]}
        identity = (sort, dimension, value, _who(name))
        instrument = instrument_key(transaction.get("instrument"))
        twin = entry["_instruments"].get(instrument) if instrument else None
        # One document another paper reports with another giver: listed under that giver, linked, and added once, never made one
        # giver with the first.
        rival = twin is not None and bool(giver) and _who(giver) not in map(_who, twin["givers"])
        seen = None
        if not rival:
            # The same transaction reported again: by its date, figure and receiver, on a copy of its page, or - by its own giver
            # or with none named - by the number of its document; two documents of different numbers are two, however alike.
            for kept in (entry["_seen"].get(identity), _copy_of(entry, sort, (dimension, value), transaction.get("kind", ""),
                                                                source, places, copies), twin):
                if kept is not None and not (instrument and kept["number"] and kept["number"] != instrument):
                    seen = kept
                    break
        if seen is not None:
            seen["papers"].append({k: who[k] for k in ("document", "pages")})
            seen["ids"].append(transaction["id"])
            if name and name not in seen["names"]:
                seen["names"].append(name)
            if giver and giver not in seen["givers"]:
                seen["givers"].append(giver)
            where = entry["_where"][id(seen)]
            where["sources"].add(source)
            where["places"] |= places
            entry["_seen"].setdefault(identity, seen)
            continue
        died = " ".join(str(transaction.get("giver_died", "")).split())
        made = {"ids": [transaction["id"]], "date": transaction.get("date", ""), "kind": transaction.get("kind", ""),
                "to": transaction.get("to", ""), "names": [name] if name else [], "givers": [giver] if giver else [],
                "figure": figure, "dimension": dimension, "value": value, "how": how, "ladder": ladder,
                "papers": [{k: who[k] for k in ("document", "pages")}], "number": instrument,
                **({"remark": f"dated after the death of the giver that the papers record ({died})"}
                   if died and _after(sort, transaction.get("giver_died_sort", "")) else {}),
                **({"twin_of": twin["ids"][0], "instrument": " ".join(str(transaction["instrument"]).split())} if rival else {})}
        if instrument and twin is None:
            entry["_instruments"][instrument] = made
        entry["_seen"][identity] = made
        entry["_where"][id(made)] = {"sort": sort, "sources": {source}, "places": set(places)}
        entry["counted"].append(made)
    out = []
    for entry in subjects.values():
        complete = not entry["unread"]
        givers = _by_giver(entry["counted"])
        totals = []
        for stated in entry["_totals"].values():
            against = []
            for group in givers:
                added = group["added"].get(stated["dimension"]) if stated["value"] is not None else None
                if added is None:
                    continue
                beyond = added - stated["value"]
                if beyond > 0:
                    against.append({"giver": group["names"][0], "leaves": None, "exceeds": beyond})
                elif complete:
                    against.append({"giver": group["names"][0], "leaves": -beyond, "exceeds": None})
            totals.append({**{k: stated[k] for k in ("text", "dimension", "value", "how", "ladder", "ids")}, "by_giver": against})
        out.append({"subject": entry["subject"], "givers": givers, "unread": entry["unread"], "complete": complete, "totals": totals})
    return out


#: What every ledger says of itself: a sum is only of what was found, giver by giver, and adds every account as the papers state it.
CAVEAT = ("Figures are added as the papers state them, whoever states them, giver by giver - whoever sold, gave, settled, lent or "
          "paid - and only the transactions NM found are added: sums of money with sums of money and each kind of quantity with "
          "its own, never a share, a rate or a period. Each is counted once where papers report the same date, subject, figure and "
          "receiver, the same date, figure and kind on copies of one page, or the same document by the same giver. A giver's figures "
          "are added to that giver's alone; nothing here says who held, owes or paid what, or which account is right. Transactions "
          "that are rival, overlapping or the same thing described twice are added as if each were separate and true, so a sum is a "
          "figure to check, not what anyone holds, owes or has paid. A transaction NM did not find, or a name written two ways, "
          "makes the sum wrong. Check it against the papers.")


def _ladders(subject):
    """The units each dimension of a subject is said in: the way most of its figures were written, the first of them where as many
    were written another way."""
    counts = {}
    for group in subject["givers"]:
        for made in group["counted"] + group["listed"]:
            if made["ladder"]:
                counts.setdefault(made["dimension"], []).append(made["ladder"])
    for stated in subject["totals"]:
        if stated["ladder"]:
            counts.setdefault(stated["dimension"], []).append(stated["ladder"])
    return {dimension: max(seen, key=lambda ladder: (seen.count(ladder), -seen.index(ladder))) for dimension, seen in counts.items()}


def _entry(made, ladders, **more):
    return {"ids": made["ids"], "date": made["date"], "kind": made["kind"], "to": made["to"], "figure": made["figure"],
            "as": render(made["dimension"], made["value"], ladders.get(made["dimension"], ())) if made["value"] is not None else None,
            "read_as": made["how"], "papers": made["papers"],
            **({"also_read_as": made["names"][1:]} if len(made["names"]) > 1 else {}),
            **({"remark": made["remark"]} if "remark" in made else {}), **more}


def shown(transactions, copies=()):
    """The ledger in words, as the board, the writer and the review are given it: for each subject its givers, each with the
    transactions counted, the ones listed and not added (and why), and what the giver's figures add up to, dimension by dimension;
    every figure rendered as the papers write it, how each was read, which papers report each transaction (and, where the receiver's
    name was read two ways on copies of a page, both readings), and a remark on any dated after the giver's recorded death; what
    could not be read or added; each stated whole with, for each giver, what it leaves or how far their figures go beyond it; and the
    caveat. There is no figure for the subject as a whole."""
    out = []
    for subject in ledger(transactions, copies):
        ladders = _ladders(subject)

        def said(dimension, value, ladders=ladders):
            return render(dimension, value, ladders.get(dimension, ())) if value is not None else None
        out.append({
            "subject": subject["subject"],
            "givers": [{"names": group["names"],
                        "counted": [_entry(made, ladders) for made in group["counted"]],
                        "listed": [_entry(made, ladders, why=(
                            f"the same document ({made['instrument']}) as {made['twin_of']}, which another paper reports with "
                            "another giver: added once, there" if "twin_of" in made
                            else _LISTED_WHY.get(made["kind"], _LISTED_WHY["other"]))) for made in group["listed"]],
                        "added": "; ".join(said(dimension, group["added"][dimension]) for dimension in DIMENSIONS
                                           if dimension in group["added"]) or None}
                       for group in subject["givers"]],
            "not_read": subject["unread"],
            "complete": subject["complete"],
            "totals": [{"text": s["text"], "dimension": s["dimension"], "read_as": s["how"], "as": said(s["dimension"], s["value"]),
                        "ids": s["ids"],
                        "by_giver": [{"giver": b["giver"], "leaves": said(s["dimension"], b["leaves"]),
                                      "exceeds": said(s["dimension"], b["exceeds"])} for b in s["by_giver"]]}
                       for s in subject["totals"]],
            "caveat": CAVEAT})
    return out
