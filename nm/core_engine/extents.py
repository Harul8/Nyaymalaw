"""Figures added up by code (plan AN.27, P13d; AN.28, D3 and D7; invariant I6).

The analysis of the reviewed bundle found that no step adds extents: a model was left to say whether a claim "can be matched", and a
total less two smaller sales that comes to the claimed 6.06 acres was an inference nobody checked. Counting is code's work. This
module reads a figure as a paper writes it, in a measure whose units convert - an area (Ac.1.18 guntas, 6 acres 6 guntas, 29 guntas,
Ac.1.18 cents, 150 sq. yards, 1,200 sq. ft, 0.40 hectares; the unit before or after the number, any dash) into guntas (40 to an acre,
100 cents to an acre, 121 square yards to a gunta), or a sum of money (Rs.2,50,000/-, Rs.2.5 lakhs, Rupees Two Lakhs Fifty Thousand)
into rupees - renders it back as the papers write it, and sets out the transactions of each property or account giver by giver - the
seller, donor, settlor, lender or payer - each giver's figures added to that giver's alone (P20 (a)), areas with areas and sums with
sums, with what a paper's stated whole leaves after them or how far they go beyond it (AN.28, D7: one ledger for the transactions of
any matter). A share, a rate or a period is listed as written and never added. Where the model read a figure too (research v13;
AN.28, D3), code adds only a reading the paper's words bear: its own where the two agree, the model's where the words read more than
one way and the model's is one of them, or where code cannot read the words and every number of the model's reading stands in them;
two readings that differ are listed, never added. It reads, adds and subtracts; it decides nothing: a sum is only of the transactions
it was given, each counted once where papers report the same date, property, figure and receiver - or the same date, figure and kind
on pages that are copies of one page, however a name was read (P20 (b)), or the same document by the same giver (AN.28, B16) - and
says so.
"""
from __future__ import annotations

import re
from fractions import Fraction

GUNTAS_PER_ACRE = 40
SQUARE_YARDS_PER_GUNTA = 121
CENTS_PER_ACRE = 100
SQUARE_FEET_PER_SQUARE_YARD = 9
#: The acre is 4,046.8564224 square metres, so a gunta is a fortieth of it.
SQUARE_METRES_PER_GUNTA = Fraction("4046.8564224") / GUNTAS_PER_ACRE
SQUARE_METRES_PER_HECTARE = 10_000
#: The measures code adds, in the order a giver's sums are said.
MEASURES = ("area", "money")

_NUMBER = r"\d+"
#: A count of yards, feet or metres, or a sum, as a paper may write it: 1,200 / 2,50,000 / 0.40.
_AMOUNT = r"\d[\d,]*(?:\.\d+)?"
#: Ac.1.18 guntas / Ac. 1-18 / Ac.0.29 / Acs.2-20 gts.: acres, then guntas (under 40), the papers' own abbreviations included.
_AC_DOT = re.compile(rf"\bac(?:res?|s)?\.?\s*({_NUMBER})\s*[.\-]\s*({_NUMBER})(?!\d)(?:\s*(?:guntas?|gts?\.?))?", re.I)
#: Ac.1.18 cents / Ac. 1-18 cts: acres, then cents (under 100), as the papers of other places write them (AN.28, D7).
_AC_DOT_CENTS = re.compile(rf"\bac(?:res?|s)?\.?\s*({_NUMBER})\s*[.\-]\s*({_NUMBER})(?!\d)\s*(?:cents?|cts?)\b\.?", re.I)
#: 6 acres 6 guntas / 6 acres and 6 guntas / 6 ac. 6 g. / 6 acs 6 gts.
_ACRES_GUNTAS = re.compile(rf"\b({_NUMBER})\s*(?:acres?|acs?\.?)\s*(?:and\s*)?({_NUMBER})\s*(?:guntas?|gts?\.?)\b", re.I)
#: 1 acre 18 cents / 1 acre and 18 cents / 1 ac. 18 cts.
_ACRES_CENTS = re.compile(rf"\b({_NUMBER})\s*(?:acres?|acs?\.?)\s*(?:and\s*)?({_NUMBER})\s*(?:cents?|cts?)\b\.?", re.I)
#: Acres 3 Guntas 12 / Ac. 3 Gts. 12 / Acres 1 Cents 18: each unit before its number (AN.28, B15).
_ACRES_GUNTAS_FIRST = re.compile(rf"\bac(?:res?|s)?\.?\s*({_NUMBER})\s*(?:and\s*)?(?:guntas?|gts?)\.?\s*({_NUMBER})(?![\d.\-])", re.I)
_ACRES_CENTS_FIRST = re.compile(rf"\bac(?:res?|s)?\.?\s*({_NUMBER})\s*(?:and\s*)?(?:cents?|cts?)\.?\s*({_NUMBER})(?![\d.\-])", re.I)
#: 6.06 acres: acres and guntas written as a decimal, or decimal acres where the second part is 40 or more.
_DECIMAL_ACRES = re.compile(rf"\b({_NUMBER})\.({_NUMBER})\s*(?:acres?|acs?\b\.?)", re.I)
_WHOLE_ACRES = re.compile(rf"\b({_NUMBER})\s*(?:acres?|acs?\b\.?)(?!\s*(?:and\s*)?{_NUMBER}\s*guntas?)", re.I)
_GUNTAS = re.compile(rf"\b({_NUMBER})\s*(?:guntas?|gts?\.?)\b", re.I)
_CENTS = re.compile(rf"\b({_NUMBER}(?:\.\d+)?)\s*(?:cents?|cts?)\b\.?", re.I)
#: Guntas 12 / Cents 18: the unit before the number (B15).
_GUNTAS_FIRST = re.compile(rf"\b(?:guntas?|gts?)\.?\s*({_NUMBER})(?![\d.\-])", re.I)
_CENTS_FIRST = re.compile(rf"\b(?:cents?|cts?)\.?\s*({_NUMBER})(?![\d.\-])", re.I)
_YARDS = re.compile(rf"\b({_AMOUNT})\s*(?:sq\.?\s*(?:yards?|yds?\.?)|square\s+yards?)", re.I)
_FEET = re.compile(rf"\b({_AMOUNT})\s*(?:sq(?:uare)?\.?\s*(?:feet|foot|fts?)\b\.?|sft\b\.?)", re.I)
_METRES = re.compile(rf"\b({_AMOUNT})\s*(?:sq(?:uare)?\.?\s*(?:metres?|meters?|mtrs?|mts?|m)\b\.?|m2\b|m²)", re.I)
_HECTARES = re.compile(rf"\b({_AMOUNT})\s*(?:hectares?|hects?\b\.?|ha\b\.?)", re.I)
#: Acre 7 / Acres 7 / Ac. 7: whole acres written with the word before the number (plan AN.28, B15); a number that runs on into
#: guntas, cents or a point is not this.
_ACRES_FIRST = re.compile(rf"\bac(?:res?|s)?\.?\s*({_NUMBER})(?![\d.\-])(?!\s*(?:guntas?|gts?|cents?|cts?)\b)", re.I)
#: Every way a paper or its reading writes a dash between acres and guntas, read as the hyphen (plan AN.28, B14): hyphen, non-breaking
#: hyphen, figure dash, en and em dashes, horizontal bar and minus sign.
_DASHES = re.compile("[‐‑‒–—―−]")
_AREAS = ((_AC_DOT, "acres.guntas"), (_AC_DOT_CENTS, "acres.cents"), (_ACRES_GUNTAS, "acres and guntas"),
          (_ACRES_CENTS, "acres and cents"), (_ACRES_GUNTAS_FIRST, "acres and guntas"), (_ACRES_CENTS_FIRST, "acres and cents"),
          (_DECIMAL_ACRES, "decimal"), (_WHOLE_ACRES, "acres"), (_ACRES_FIRST, "acres"), (_GUNTAS, "guntas"),
          (_GUNTAS_FIRST, "guntas"), (_CENTS, "cents"), (_CENTS_FIRST, "cents"), (_YARDS, "square yards"), (_FEET, "square feet"),
          (_METRES, "square metres"), (_HECTARES, "hectares"))
#: What a sum of an area is said in, by how its figures were written: whole and decimal acres are written everywhere and say
#: nothing of it.
_UNITS = {"acres.guntas": "guntas", "acres and guntas": "guntas", "acres and guntas written 6.06": "guntas", "guntas": "guntas",
          "acres.cents": "cents", "acres and cents": "cents", "cents": "cents", "square yards": "square yards",
          "square feet": "square feet", "square metres": "square metres", "hectares": "hectares"}


def _extents_in(text):
    """The extents in some words, each once: a match inside another match (the guntas of "6 acres 6 guntas") is part of it, not a
    second extent."""
    found = []
    for pattern, how in _AREAS:
        found += [(match.start(), match.end(), how, match) for match in pattern.finditer(text)]
    found.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    kept = []
    for item in found:
        if not any(other[0] <= item[0] and item[1] <= other[1] for other in kept):
            kept.append(item)
    return kept


def _amount(written):
    return Fraction(written.replace(",", ""))


def _guntas(how, parts):
    """The guntas an extent written one of the ways comes to: (guntas, how), or (None, why not)."""
    if how in ("acres.guntas", "acres and guntas"):
        acres, guntas = int(parts[0]), int(parts[1])
        if guntas >= GUNTAS_PER_ACRE:
            return None, "the guntas are 40 or more"
        return Fraction(acres * GUNTAS_PER_ACRE + guntas), how
    if how in ("acres.cents", "acres and cents"):
        acres, cents = int(parts[0]), int(parts[1])
        if cents >= CENTS_PER_ACRE:
            return None, "the cents are 100 or more"
        return Fraction(acres * CENTS_PER_ACRE + cents, CENTS_PER_ACRE) * GUNTAS_PER_ACRE, how
    if how == "decimal":
        acres, after = int(parts[0]), parts[1]
        if len(after) == 2 and int(after) < GUNTAS_PER_ACRE:
            return Fraction(acres * GUNTAS_PER_ACRE + int(after)), "acres and guntas written 6.06"
        return (acres + Fraction(int(after), 10 ** len(after))) * GUNTAS_PER_ACRE, "decimal acres"
    if how == "acres":
        return Fraction(int(parts[0]) * GUNTAS_PER_ACRE), how
    if how == "guntas":
        return Fraction(int(parts[0])), how
    if how == "cents":
        return _amount(parts[0]) / CENTS_PER_ACRE * GUNTAS_PER_ACRE, how
    if how == "square feet":
        return _amount(parts[0]) / (SQUARE_YARDS_PER_GUNTA * SQUARE_FEET_PER_SQUARE_YARD), how
    if how == "square metres":
        return _amount(parts[0]) / SQUARE_METRES_PER_GUNTA, how
    if how == "hectares":
        return _amount(parts[0]) * SQUARE_METRES_PER_HECTARE / SQUARE_METRES_PER_GUNTA, how
    return _amount(parts[0]) / SQUARE_YARDS_PER_GUNTA, how


def _area(words):
    """The one extent some words write, as _extents_in finds it, or (None, why not)."""
    kept = _extents_in(_DASHES.sub("-", " ".join(str(words).split())))
    if not kept:
        return None, "no extent in these words"
    if len(kept) > 1:
        return None, "more than one extent in these words"
    return kept[0], None


def parse(words):
    """An extent as a paper writes it, in guntas: (guntas as a Fraction, how it was read), or (None, why not). Read as the paper
    writes it and no other way; where two readings are possible the way is said (6.06 acres is 6 acres 6 guntas, a paper's own
    notation, unless the part after the point is 40 or more, when it is decimal acres); more than one extent in the words, or none, is
    not read."""
    found, why = _area(words)
    if found is None:
        return None, why
    return _guntas(found[2], found[3].groups())


def _area_readings(words):
    """Every reading code can give the one extent some words write: (its own reading or None, the other ways the words read, how or
    why not). Acres with a two-digit part after a point or a dash and no unit after it (Ac.1.18, 6.06 acres) read as acres and
    guntas, and also as acres and cents, which are decimal acres: papers of one place write guntas so, of another cents."""
    found, why = _area(words)
    if found is None:
        return None, [], why
    value, how = _guntas(found[2], found[3].groups())
    match, others = found[3], []
    if found[2] in ("acres.guntas", "decimal") and not re.search(r"gunta|\bgts?\b", match.group(0), re.I) and len(match.group(2)) == 2:
        cents = Fraction(int(match.group(1)) * CENTS_PER_ACRE + int(match.group(2)), CENTS_PER_ACRE) * GUNTAS_PER_ACRE
        if cents != value:
            others.append(cents)
    return value, others, how


# Sums of money (AN.28, D7): rupees in figures, with lakhs and crores, or in words.
_SMALL_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
                "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
                "eighty": 80, "ninety": 90}
_SCALE_WORDS = {"thousand": 1000, "lakh": 10 ** 5, "lakhs": 10 ** 5, "lac": 10 ** 5, "lacs": 10 ** 5, "crore": 10 ** 7,
                "crores": 10 ** 7}
#: A day of the month as papers write it in words: the twelfth, the twenty first.
_ORDINAL_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
                  "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16,
                  "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20, "thirtieth": 30}
_TOKEN = re.compile(r"[a-z]+", re.I)
_CURRENCY = r"(?:\brs\b\.?|\brupees?\b|\binr\b|₹)"
_MONEY = re.compile(rf"{_CURRENCY}\s*({_AMOUNT})(?:\s*(thousand|lakhs?|lacs?|crores?)\b)?"
                    rf"|\b({_AMOUNT})(?:\s*(thousand|lakhs?|lacs?|crores?)\b)?\s*(?:\brupees?\b|\brs\b\.?)", re.I)


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


def _sums(text):
    """The sums of money some words write, each as (rupees, 'figures' or 'words')."""
    found = []
    for match in _MONEY.finditer(text):
        amount, scale = (match.group(1), match.group(2)) if match.group(1) else (match.group(3), match.group(4))
        found.append((_amount(amount) * (_SCALE_WORDS[scale.casefold()] if scale else 1), "figures"))
    for start, end, value, _ in _worded(text):
        if re.search(rf"{_CURRENCY}\s*$", text[:start], re.I) or re.match(r"\s*rupees?\b", text[end:], re.I):
            found.append((Fraction(value), "words"))
    return found


def sums_written(text):
    """Each sum of money some words write, as (the words as written, its rupees), in the order they stand: for the check that an
    understanding works out no sum (research, P23 made general by plan AN.28, D7)."""
    found = [(match.start(), match.group(0).strip(), value) for match in _MONEY.finditer(text)
             for value in [_amount(match.group(1) or match.group(3))
                           * (_SCALE_WORDS[(match.group(2) or match.group(4)).casefold()] if (match.group(2) or match.group(4)) else 1)]]
    found += [(start, text[start:end], Fraction(value)) for start, end, value, _ in _worded(text)
              if re.search(rf"{_CURRENCY}\s*$", text[:start], re.I) or re.match(r"\s*rupees?\b", text[end:], re.I)]
    return [(words, value) for _, words, value in sorted(found, key=lambda item: item[0])]


def parse_money(words):
    """A sum of money as a paper writes it, in rupees: (rupees as a Fraction, how it was read), or (None, why not). In figures -
    Rs.2,50,000/-, Rs. 2.5 lakhs, 50,000 rupees - or in words after Rupees; a sum written in figures and in words is one sum where
    they agree, and is not read where they do not; two different sums are not read."""
    text = " ".join(str(words).split())
    found = _sums(text)
    if not found:
        return None, "no sum of money in these words"
    kinds = {kind for _, kind in found}
    if len({value for value, _ in found}) > 1:
        return None, ("the figures and the words give different sums" if kinds == {"figures", "words"}
                      else "more than one sum in these words")
    return found[0][0], "rupees, in figures and in words" if len(kinds) == 2 else f"rupees in {found[0][1]}"


def _money_readings(words):
    value, how = parse_money(words)
    return value, [], how


def _numbers(words):
    """The numbers some words write - in figures, a figure's commas or none (2,50,000 is 250000; Ac.1.18 is 1 and 18), or in words
    (Two Lakhs Fifty Thousand) - which the numbers of a reading must be among (AN.28, D3)."""
    text = str(words)
    found = {int(number) for number in re.findall(r"\d+", text)}
    found |= {int(number.replace(",", "")) for number in re.findall(r"\d{1,3}(?:,\d{2,3})+", text)}
    return found | numbers_in_words(text)


#: How a reading that is not a figure code adds says so: a rate, a share and a period are listed as written (AN.28, D7).
_RATE = re.compile(r"\bper\s+(?:annum|year|month|mensem|week|day|acre|gunta|cent|square|sq)\b|\bp\.\s*a\.|/\s*(?:month|year|annum)\b",
                   re.I)
_SHARE = re.compile(r"\bshares?\b|%|\bper\s*cent\b|\bpercent(?:age)?\b", re.I)
_PERIOD = re.compile(r"\b(?:years?|months?|weeks?|days?)\b", re.I)
_AREA_WORDS = re.compile(r"\b(?:acres?|acs?|guntas?|gts?|cents?|cts?|sq|square|hectares?|ha)\b", re.I)
_LISTED = {"rate": "a rate, not a sum: code adds areas and sums of money only",
           "share": "a share of a whole: code adds areas and sums of money only",
           "period": "a period of time: code adds areas and sums of money only"}
_READERS = {"area": _area_readings, "money": _money_readings}
_ONE_READING = {"area": parse, "money": parse_money}


def _kind(reading):
    """What a model's plain reading of a figure says it is: a rate, a share, an area, a sum of money or a period; None where it says
    none of them."""
    if _RATE.search(reading):
        return "rate"
    if _SHARE.search(reading):
        return "share"
    if _area(reading)[0] is not None or _AREA_WORDS.search(reading):
        return "area"
    if _sums(reading) or re.search(_CURRENCY, reading, re.I):
        return "money"
    if _PERIOD.search(reading):
        return "period"
    return None


def _unit(measure, how):
    return "rupees" if measure == "money" else _UNITS.get(how)


def read(extent, reading=None):
    """A transaction's figure as code reads it: (measure, value, how, unit) - measure "area" (value in guntas) or "money" (value in
    rupees), unit what a sum of such figures is said in - or (None, None, why not, None), never added. reading: the model's plain
    reading of the figure with its unit (research v13); None for a record that has none (v12), whose figures are read as extents,
    as before. The model reads, code verifies (plan AN.28, D3): a rate, a share or a period, as the reading says, is listed and never
    added; code's own reading of the paper's words stands where the model's agrees with it or cannot be read; where the words read
    more than one way, the model's reading of them is taken if it is one of those ways; where code cannot read the words, the
    model's reading is taken if code can read it and every number in it stands in the words; two readings that differ are never
    added, and are said."""
    if reading is None:
        value, how = parse(extent)
        return ("area", value, how, _unit("area", how)) if value is not None else (None, None, how, None)
    reading = " ".join(str(reading).split())
    kind = _kind(reading) if reading else None
    if kind in _LISTED:
        return None, None, _LISTED[kind], None
    tried = [(measure, *_READERS[measure](extent)) for measure in ((kind,) if kind else MEASURES)]
    readable = [found for found in tried if found[1] is not None or found[2]]
    if readable:
        measure, value, others, how = readable[0]
    else:
        measure, value, others, how = tried[0]
        nothing = ("no extent in these words", "no sum of money in these words")
        if not kind:
            how = next((found[3] for found in tried if found[3] not in nothing), "no area or sum of money in these words")
    if not reading:
        return (measure, value, how, _unit(measure, how)) if value is not None else (None, None, how, None)
    second, way = _ONE_READING[measure](reading)
    if value is not None and (second is None or second == value):
        return measure, value, how, _unit(measure, how)
    if second is not None and second in others:
        return measure, second, f"{way}, as AI read words code reads more than one way", _unit(measure, way)
    if value is not None:
        return None, None, (f"code reads {render_value(measure, value, _unit(measure, how))} and the reading given for it "
                            f"{render_value(measure, second, _unit(measure, way))}: two readings"), None
    if second is None:
        return None, None, how, None
    if not _numbers(reading) <= _numbers(extent):
        return None, None, f"{how}; the reading given for it has numbers the paper's words do not", None
    return measure, second, f"{way}, as read by AI from words code could not read; its numbers are the paper's", _unit(measure, way)


def _held_in(measure, value, figure, words):
    """Whether a figure stands in the words that record its transaction (AN.28, D3): its numbers among theirs, or the words writing
    the same figure another way (Rupees Two Lakhs for Rs.2,00,000)."""
    if _numbers(figure) <= _numbers(words):
        return True
    if measure == "area":
        return any(value == reading for _, _, how, match in _extents_in(_DASHES.sub("-", " ".join(str(words).split())))
                   for reading in [_guntas(how, match.groups())[0]])
    return any(value == sum_ for sum_, _ in _sums(" ".join(str(words).split())))


def instrument_key(written):
    """The document a transaction is recorded in, as one key (plan AN.28, B16): its numbers in order, a year of four digits taken
    by its last two, so that 'Doc No. 1234/2001' and 'Sale Deed No. 1234 of 2001' (invented) are one. None where it has no number."""
    numbers = re.findall(r"\d+", str(written or ""))
    if not numbers:
        return None
    if len(numbers) > 1 and len(numbers[-1]) == 4:
        numbers[-1] = numbers[-1][-2:]
    return "/".join(str(int(number)) for number in numbers)


def _acres_and(value, per_acre, small):
    """An area in acres and a smaller unit, as the papers say it: '6 acres 6 guntas (Ac.6.06)', '1 acre 18 cents (Ac.1.18)'; a minus
    sign for less than nothing; a part that is not whole to two places."""
    sign = "-" if value < 0 else ""
    value = abs(Fraction(value))
    acres, rest = divmod(value, per_acre)
    whole = rest.denominator == 1
    shown = str(int(rest)) if whole else f"{float(rest):.2f}"
    words = " ".join(part for part in (
        f"{int(acres)} acre{'s' if acres != 1 else ''}" if acres else "",
        f"{shown} {small}{'s' if rest != 1 else ''}" if rest or not acres else "") if part)
    return f"{sign}{words} (Ac.{int(acres)}.{int(rest):02d})" if whole else f"{sign}{words}"


def render(guntas):
    """Guntas as the papers say an extent: '6 acres 6 guntas (Ac.6.06)'; a minus sign for less than nothing; a gunta that is not whole
    to two places."""
    return _acres_and(guntas, GUNTAS_PER_ACRE, "gunta")


def _grouped(number):
    """A whole number grouped as Indian papers group it: 2,50,000."""
    digits = str(number)
    if len(digits) <= 3:
        return digits
    return re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", digits[:-3]) + "," + digits[-3:]


def _plain(value, places=2):
    """A number grouped as the papers group it, to two places where it is not whole."""
    value = Fraction(value)
    sign = "-" if value < 0 else ""
    if value.denominator == 1:
        return f"{sign}{_grouped(abs(int(value)))}"
    whole, part = divmod(round(abs(value) * 10 ** places), 10 ** places)
    return f"{sign}{_grouped(whole)}.{part:0{places}d}"


def render_money(rupees):
    """Rupees as the papers write a sum: 'Rs 2,50,000', with paise where there are any."""
    paise = round(Fraction(rupees) * 100)
    sign = "-" if paise < 0 else ""
    whole, part = divmod(abs(paise), 100)
    return f"{sign}Rs {_grouped(whole)}" + (f".{part:02d}" if part else "")


def render_value(measure, value, unit=None):
    """A figure of a measure as the papers write it: an area in the unit its papers use (guntas where they say none), a sum in
    rupees."""
    if measure == "money":
        return render_money(value)
    if unit == "cents":
        return _acres_and(Fraction(value) * CENTS_PER_ACRE / GUNTAS_PER_ACRE, CENTS_PER_ACRE, "cent")
    if unit == "square yards":
        return f"{_plain(Fraction(value) * SQUARE_YARDS_PER_GUNTA)} square yards"
    if unit == "square feet":
        return f"{_plain(Fraction(value) * SQUARE_YARDS_PER_GUNTA * SQUARE_FEET_PER_SQUARE_YARD)} square feet"
    if unit == "square metres":
        return f"{_plain(Fraction(value) * SQUARE_METRES_PER_GUNTA)} square metres"
    if unit == "hectares":
        # To four places, as a hectare's parts are written, without the noughts after the second.
        shown = _plain(Fraction(value) * SQUARE_METRES_PER_GUNTA / SQUARE_METRES_PER_HECTARE, 4)
        return f"{shown[:-2] + shown[-2:].rstrip('0') if '.' in shown else shown} hectares"
    return render(value)


_SURVEY = re.compile(r"\b(?:survey|sy|s)\.?\s*(?:nos?|numbers?)?\.?\s*", re.I)


def parcel_key(parcel):
    """A parcel as one key: 'Sy.No.487/A' and 'Survey No. 487 / A' are one; 487 and 487/A are two."""
    text = _SURVEY.sub(" ", " ".join(str(parcel).split()), count=1)
    return re.sub(r"[^a-z0-9/]", "", text.casefold())


def _who(name):
    return re.sub(r"[^a-z0-9]", "", str(name).casefold())


def _copy_of(entry, sort, figure, kind, source, places, copies):
    """The transaction already kept that this one is the same as because they are read on pages that are copies of one page (P20
    (b)): the same date, figure and kind, reported by another paper than any that already reports it, on a page that copies one of
    the pages it is read on. A name read two ways, as OCR does, cannot tell two papers' copies apart: the pages' words already have."""
    for made in entry["transfers"]:
        where = entry["_where"][id(made)]
        if (where["sort"] == sort and (made["measure"], made["value"]) == figure and made["kind"] == kind
                and source not in where["sources"]
                and any(frozenset({kept, new}) in copies for kept in where["places"] for new in places)):
            return made
    return None


#: What a giver can be recorded as giving by their own act and have it added to what they gave: land or other property sold, given
#: or settled, money lent or paid. A partition allots a share among those who held the property together and a decree is a court's
#: order, so neither is the giver's own transfer (P20 (a)); a lease or a mortgage passes possession or security, not what the giver
#: holds (AN.28, D7).
ADDED_KINDS = ("sale", "gift", "settlement", "loan", "payment")
_NOT_ADDED = {"partition": "a partition allots a share; it is not a sale", "decree": "a court's decree is not the seller's sale",
              "other": "not a sale, a gift or a settlement",
              # v13 (AN.28, D7): the transactions of any subject.
              "lease": "a lease passes possession for a time, not what the owner holds",
              "mortgage": "a mortgage is security for a debt, not a sale"}


def _by_seller(transfers):
    """The transactions of one property or account grouped by who is recorded as making them (P20 (a)): a giver's sales, gifts,
    settlements, loans and payments are added to that giver's alone, measure by measure, never to another's - the papers' accounts
    of rival chains of title are not one holding. Two spellings of a name are one giver only where the papers make them so - they
    are read as the giver of one transaction, such as a sale reported on copies of one page, its seller's name read two ways -
    never because they look alike. A transaction whose giver is not named is listed and added to no one."""
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
        group = groups.setdefault(find(keys[0]) if keys else "", {"names": [], "transfers": [], "not_added": [], "added": {}})
        group["names"].extend(name for name in made["sellers"] if name not in group["names"])
        group["transfers" if made["kind"] in ADDED_KINDS and "twin_of" not in made else "not_added"].append(made)
    for key, group in groups.items():
        if key:
            for made in group["transfers"]:
                group["added"][made["measure"]] = group["added"].get(made["measure"], Fraction(0)) + made["value"]
    return list(groups.values())


def _stated(transfer, worded):
    """The whole a paper states for a transaction's property or account: (measure, value, how, unit), or (None, None, why not,
    None). A v12 record's is read as an extent; a v13 record's as an extent or a sum, and only where it stands in the words that
    record the transaction (AN.28, D3)."""
    if not worded:
        value, how = parse(transfer["total"])
        return ("area", value, how, _unit("area", how)) if value is not None else (None, None, how, None)
    found = read(transfer["total"], "")
    if found[1] is not None and not _held_in(found[0], found[1], transfer["total"], transfer.get("words", "")):
        return None, None, NOT_IN_WORDS, None
    return found


#: Why code does not use a figure the model gave: what fault() names, and the ledger lists.
NOT_IN_WORDS = "its figure is not in the words that record it"


def fault(transfer):
    """Why code cannot add a v13 transaction's figure or use the whole it gives, as the model gave them, or None (plan AN.28, D3):
    its figure read two ways, its reading's numbers not the paper's, its figure or its whole not in the words that record it. The
    ledger lists such a transaction and never adds it; research shows the model what code found, once, before the record is kept.
    A figure that is not one code adds - a share, a rate, a period, words with no figure - is no fault: it is listed as written."""
    measure, value, how, _ = read(transfer["extent"], transfer.get("reading", ""))
    if value is None and how.endswith((": two readings", "numbers the paper's words do not")):
        return how
    if value is not None and not _held_in(measure, value, transfer["extent"], transfer.get("words", "")):
        return NOT_IN_WORDS
    if str(transfer.get("total", "")).strip() and _stated(transfer, True)[2] == NOT_IN_WORDS:
        return "the whole it gives is not in the words that record it"
    return None


def ledger(transfers, copies=()):
    """The transactions of each property or account, added up giver by giver. transfers: dicts with id, parcel, extent, total, from,
    to, sort, kind, document, pages (and source, the turn's key of the document, where the plan gave it; and, from research v13, the
    model's reading of the figure, the number of the document that records it and the words that record it). copies: the pairs of
    pages that are copies of one page, each {(key, page), (key, page)}, as copy_figures.copies finds them. A transaction with no
    property or account is left out. Returns one entry per property or account, in the papers' order:
      sellers - its transactions grouped by who made them (_by_seller), in the order they first appear. Each transaction once (the
                same date, property, figure and receiver reported by several papers is one, with every paper that reports it; so is
                the same date, figure and kind read on pages that are copies of one page, whatever the receiver's name was read as,
                every reading of it kept in names; and so is one document reported again by its own giver or with none named, while
                one another paper reports with another giver is listed under that giver, linked to it and not added again), its
                figure, its measure and how it was read; the sales, gifts, settlements, loans and payments added in 'added', measure
                by measure (empty for a giver with none, or with no name), the rest in 'not_added';
      unread - the sales, gifts, settlements, loans and payments whose figure could not be read or added, with why, never added;
      complete - whether every one of them was added;
      totals - each different whole a paper states for it (one figure however it is written) and, for each giver who gave in its
               measure, what it leaves after that giver's figures (only where every transaction was added, and as if all of it was
               that giver's) or how far their figures go beyond it (named whether or not every transaction was added: more can only
               be more)."""
    parcels = {}
    for transfer in transfers:
        key = parcel_key(transfer.get("parcel", ""))
        if not key:
            continue
        entry = parcels.setdefault(key, {"parcel": " ".join(str(transfer["parcel"]).split()), "_seen": {}, "transfers": [],
                                         "unread": [], "_totals": {}, "_where": {}, "_instruments": {}})
        who = {"document": transfer["document"], "pages": list(transfer["pages"]), "id": transfer["id"]}
        # A v13 record carries the model's reading of its figure: code checks the figure against it and against the words (D3).
        worded = "reading" in transfer
        if transfer.get("anchored") is False:
            # Words the finder could not find on the paper's pages support no figure: listed, never added, and its stated whole
            # is not a stated whole.
            entry["unread"].append({"id": transfer["id"], "extent": " ".join(str(transfer["extent"]).split()),
                                    "why": "its words were not found on the page", "document": who["document"], "pages": []})
            continue
        if transfer.get("total", "").strip():
            measure, value, how, unit = _stated(transfer, worded)
            written = " ".join(transfer["total"].split())
            # One stated whole is one figure however it is written (Ac.8.24 guntas, Ac.8.24 gts): by its value where it can be read.
            stated = entry["_totals"].setdefault((measure, value) if value is not None else written,
                                                 {"text": written, "measure": measure, "value": value, "how": how, "unit": unit,
                                                  "ids": []})
            stated["ids"].append(transfer["id"])
        measure, value, how, unit = read(transfer["extent"], transfer.get("reading"))
        if worded and value is not None and not _held_in(measure, value, transfer["extent"], transfer.get("words", "")):
            measure, value, how, unit = None, None, NOT_IN_WORDS, None
        if value is None and transfer.get("kind", "") in ADDED_KINDS:
            entry["unread"].append({"id": transfer["id"], "extent": " ".join(str(transfer["extent"]).split()), "why": how, **{
                k: who[k] for k in ("document", "pages")}})
            continue
        # A partition, a decree or anything that is not added is never added, so a figure that cannot be read does not make the
        # property incomplete (P20 (d)): it is listed with the figure as written, and why it could not be read.
        sort, name = transfer.get("sort", ""), " ".join(str(transfer.get("to", "")).split())
        seller = " ".join(str(transfer.get("from", "")).split())
        source = transfer.get("source", transfer["document"])
        places = {(source, number) for number in transfer["pages"]}
        identity = (sort, measure, value, _who(name))
        instrument = instrument_key(transfer.get("instrument"))
        twin = entry["_instruments"].get(instrument) if instrument else None
        # One document another paper reports with another giver (B16): listed under that giver, linked, and added once, never
        # made one giver with the first.
        rival = twin is not None and bool(seller) and _who(seller) not in map(_who, twin["sellers"])
        seen = None
        if not rival:
            # The same transaction reported again: by its date, figure and receiver, on a copy of its page, or - by its own giver
            # or with none named - by the number of its document (B16); two documents of different numbers are two, however alike.
            for kept in (entry["_seen"].get(identity), _copy_of(entry, sort, (measure, value), transfer.get("kind", ""), source,
                                                                places, copies), twin):
                if kept is not None and not (instrument and kept["number"] and kept["number"] != instrument):
                    seen = kept
                    break
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
                "extent": " ".join(str(transfer["extent"]).split()), "measure": measure, "value": value, "how": how, "unit": unit,
                "papers": [{k: who[k] for k in ("document", "pages")}], "number": instrument,
                **({"twin_of": twin["ids"][0], "instrument": " ".join(str(transfer["instrument"]).split())} if rival else {})}
        if instrument and twin is None:
            entry["_instruments"][instrument] = made
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
                added = group["added"].get(stated["measure"]) if stated["value"] is not None else None
                if added is None:
                    continue
                beyond = added - stated["value"]
                if beyond > 0:
                    against.append({"seller": group["names"][0], "leaves": None, "exceeds": beyond})
                elif complete:
                    against.append({"seller": group["names"][0], "leaves": -beyond, "exceeds": None})
            totals.append({**{k: stated[k] for k in ("text", "measure", "value", "how", "unit", "ids")}, "by_seller": against})
        out.append({"parcel": entry["parcel"], "sellers": sellers, "unread": entry["unread"], "complete": complete, "totals": totals})
    return out


#: What every ledger says of itself: a sum is only of what was found, giver by giver, and adds every account as the papers state it.
CAVEAT = ("Figures are added as the papers state them, whoever states them, giver by giver - the seller, donor, settlor, lender or "
          "payer - and only the transactions NM found are added: areas with areas and sums of money with sums of money, never a share, "
          "a rate or a period. Each is counted once where papers report the same date, property, figure and receiver, the same date, "
          "figure and kind on copies of one page, or the same document by the same giver. A giver's figures are added to that giver's "
          "alone; nothing here says who held, owes or paid what, or which account is right. Transactions that are rival, overlapping or "
          "the same thing described twice are added as if each were separate and true, so a sum is a figure to check, not what anyone "
          "holds, owes or has paid. A transaction NM did not find, or a name written two ways, makes the sum wrong. Check it against "
          "the papers.")


def _unit_of(parcel):
    """What a property's areas are said in: the unit most of its figures are written in, the first of them where as many are written
    in another; guntas where none says."""
    counts = {}
    for unit in [made["unit"] for group in parcel["sellers"] for made in group["transfers"] + group["not_added"]] + [
            stated["unit"] for stated in parcel["totals"]]:
        if unit and unit != "rupees":
            counts[unit] = counts.get(unit, 0) + 1
    return max(counts, key=lambda unit: (counts[unit], -list(counts).index(unit))) if counts else "guntas"


def _entry(made, unit, **more):
    return {"ids": made["ids"], "date": made["date"], "kind": made["kind"], "to": made["to"], "extent": made["extent"],
            "as": render_value(made["measure"], made["value"], unit) if made["value"] is not None else None, "read_as": made["how"],
            "papers": made["papers"],
            **({"also_read_as": made["names"][1:]} if len(made["names"]) > 1 else {}), **more}


def shown(transfers, copies=()):
    """The ledger in words, as the board, the writer and the review are given it: for each property or account its givers, each with
    the transactions added, the ones listed and not added (and why), and what the giver's figures add up to, measure by measure;
    every figure rendered as the papers write it, how each was read, which papers report each transaction (and, where the
    receiver's name was read two ways on copies of a page, both readings); what could not be read or added; each stated whole with,
    for each giver, what it leaves or how far their figures go beyond it; and the caveat. There is no figure for the property as a
    whole."""
    out = []
    for parcel in ledger(transfers, copies):
        unit = _unit_of(parcel)

        def said(measure, value, unit=unit):
            return render_value(measure, value, unit) if value is not None else None
        out.append({
            "parcel": parcel["parcel"],
            "sellers": [{"names": group["names"],
                         "transfers": [_entry(made, unit) for made in group["transfers"]],
                         "not_added": [_entry(made, unit, why=(
                                           f"the same document ({made['instrument']}) as {made['twin_of']}, which another "
                                           "paper reports with another giver: added once, there" if "twin_of" in made
                                           else _NOT_ADDED.get(made["kind"], _NOT_ADDED["other"])))
                                       for made in group["not_added"]],
                         "added": "; ".join(said(measure, group["added"][measure]) for measure in MEASURES
                                            if measure in group["added"]) or None}
                        for group in parcel["sellers"]],
            "not_read": parcel["unread"],
            "complete": parcel["complete"],
            "totals": [{"text": s["text"], "measure": s["measure"], "read_as": s["how"], "as": said(s["measure"], s["value"]),
                        "ids": s["ids"],
                        "by_seller": [{"seller": b["seller"], "leaves": said(s["measure"], b["leaves"]),
                                       "exceeds": said(s["measure"], b["exceeds"])}
                                      for b in s["by_seller"]]}
                       for s in parcel["totals"]],
            "caveat": CAVEAT})
    return out
