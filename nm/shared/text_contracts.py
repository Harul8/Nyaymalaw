"""One definition of "this value carries nothing". ONE COPY, and this is it.

WHY THIS EXISTS
---------------
`if not value:` is a CHARACTER test. `"   "` is three characters and no
content, so it passes — and three separate defects were the same sentence:

    B-046  `advocate_id = "   "` opened a matter, putting client material on a
           file nothing could attribute. The wire validated `min_length=1`.
    B-037  `client_described_as = "our client"` was recorded as a descriptor,
           and the narrowed question became "You act for the our client."
    B-042  `role_basis` was a required enum with no member meaning "there is no
           role", so the model returned `""` and validation failed open.

Each was fixed where it was found — a `.strip()`, a regex, an enum member — and
nothing would have caught the fourth. Sweeping the codebase for the shape found
three more sites that had never been hit: an API key, the reason on a NOT_HELD
result, and the no-deadline reason on an ACTION.

THE RULE: LENGTH IS NOT CONTENT. A value that is present and carries nothing is
ABSENT, and every place that requires content asks the same question here.

`tests/test_blank_values.py` walks every dataclass in `nm/` and fails the build
on a falsy test against a string field that does not come through this module —
so the next required string is covered on the day it is added, rather than on
the day a scenario happens to pass whitespace into it.
"""
from __future__ import annotations

import re


def blank(value: object) -> bool:
    """True when the value is absent, or present and carrying nothing.

    `None`, `""`, `"   "`, `"\\t\\n"` are all blank. Non-strings are blank only
    when falsy, so an empty tuple or a zero count reads as absent too — which
    is the same question asked of a different type.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return not value


def present(value: object) -> bool:
    """The complement, for call sites that read better in the positive."""
    return not blank(value)


def clean(value: str | None) -> str:
    """A string reduced to what it actually carries, or the empty string.

    Stored stripped, so two spellings of one identifier cannot become two
    identifiers -- `"  adv_1  "` and `"adv_1"` are the same advocate.
    """
    return (value or "").strip()


#: Words. Everything that is not a letter or a digit is separation, whatever
#: character it happens to be — a hyphen, a slash, a full stop, a run of
#: newlines the corpus hard-wrapped at column 72.
_WORDS = re.compile(r"[a-z0-9]+")


def fold(text: str | None) -> str:
    """One definition of "this is the same text". ONE COPY, and this is it.

    THE SECOND HALF OF THIS MODULE'S ARGUMENT. `blank` exists because "is
    there anything here" was answered six ways; this exists because "is this
    the same thing" was answered six ways too, and two of the answers
    disagreed.

    MEASURED, 6 September 2026, on the six definitions then in `nm/`:

        nm/work_the_file/chronology.py   words only  ── the same three characters
        nm/Archives/legal_brain/understand/dispute.py      words only
        nm/Archives/legal_brain/understand/posture.py      words only
        nm/Archives/legal_brain/verify/grounding.py    words only, plus the case-name `vs`/`v` pivot
        nm/Archives/legal_brain/reason/issue_contracts.py      WHITESPACE COLLAPSE ONLY — punctuation kept
        nm/advise/decision_contracts.py   WHITESPACE COLLAPSE ONLY

    So `chronology.conflicts` read "the agreement is dated 15-4-1984" and
    "The agreement is dated 15/4/1984" as ONE event with two dates, while
    `issue.merge` read "Is the agreement enforceable?" and "Is the agreement
    enforceable" as TWO issues. The second is the duplicate-issue defect
    (B-107's sibling) coming back through a door its own fix did not know
    about — the fix was `restates`, an id named by the read, with the folded
    statement as the fallback, and the fallback was folding on punctuation.

    THIS IS NOT FUZZY MATCHING (CLAUDE.md §5). There is no threshold, no
    score and no ranking: two strings fold to the same words or they do not.
    What it removes is typography, which is not information about whether two
    sentences say the same thing.

    A caller needing MORE normalisation than this composes on top and says
    why — `nm.Archives.legal_brain.verify.grounding` folds `vs` and `versus` to `v` because a case
    name written both ways is one case, and that is a fact about citations
    rather than about text. What no caller may do is define its own base.

    `tests/test_one_fold.py` scans `nm/` and fails the build on a second
    definition, for the same reason `test_citation_patterns.py` scans for a
    second provision pattern: the copies above were not written by someone
    ignoring a rule, they were written by six people who each needed a fold
    and had no one place to find it.
    """
    return " ".join(words(text))


def fold_spacing(text: str | None) -> str:
    """The OTHER folding question, owned HERE so nobody defines it again.

    `fold` above answers *are these the same words*: it lowercases and treats
    every non-alphanumeric character as separation. That is right for matching
    a proposition against a paragraph, and WRONG for a quotation.

    A quotation differing from its source only in line breaks is the same
    words; one differing in punctuation or case is not. Fold a quote with the
    word-based `fold` and *"the price, and delivery."* matches *"the price and
    delivery"* -- a paraphrase reported as VERBATIM, which is exactly what C1's
    third NEVER forbids and what `nm.Archives.legal_brain.retrieve.research.quote_fidelity` exists to
    refuse. So the quote comparison collapses WHITESPACE ONLY and keeps case
    and punctuation.

    It lives here rather than beside its one caller for the reason this whole
    module exists: `nm/Archives/legal_brain/retrieve/research.py` defined it privately and
    `tests/test_one_fold.py` caught it as a second base. TWO FOLDING NOTIONS IS
    FINE; two owners of one notion is the defect.
    """
    return " ".join((text or "").split())


def snippet(text: str | None, limit: int) -> str:
    """One definition of "shorten this sentence so it can be quoted inside
    another one". ONE COPY, and this is it.

    THE MEASURED DEFECT. A defending turn told an advocate:

        CONDITIONAL, not a deadline: on the reading that the period was run
        from the plaintiff says our client trespassed on 15 April 2019 and
        they hav because the cause carries no curated accrual trigger...

    `accrual.statement[:70]` cut the chronology entry mid-word. The sentence
    the advocate reads immediately before deciding whether to trust the
    arithmetic beside it ended "and they hav", and forty-one other sites in
    `nm/` cut prose the same way.

    TWO THINGS A BARE SLICE GETS WRONG, and both are this project's own
    recurring shapes rather than typography:

    * IT CUTS MID-WORD. `[:70]` counts characters, and a sentence is made of
      words. What comes out is not English, and an advocate who cannot read
      the premise cannot correct it -- which is the entire mechanism by which
      a wrong accrual is meant to be caught.
    * IT DOES NOT SAY IT CUT. A shortened statement rendered without a mark
      reads as the WHOLE statement, so "the plaintiff says our client
      trespassed on" looks like the complete entry rather than its first
      fifty characters. An absent remainder reading as no remainder is
      CLAUDE.md §9 wearing a smaller hat.

    So: fold the spacing (a statement carrying a newline breaks the line it is
    quoted into), cut at the last word boundary that fits, and mark the
    elision. Text that already fits comes back untouched and unmarked -- a
    mark on a complete sentence would be the opposite lie.

    A word longer than the limit is cut inside itself, because there is no
    better answer and reporting the whole of it would defeat the bound.

    `tests/test_prose_is_cut_on_words.py` scans `nm/` and fails the build on a
    constant-length slice of anything the vocabulary says is prose, for the
    same reason `test_one_fold.py` scans for a second fold: the forty-two
    sites were not written by people ignoring a rule, they were written by
    people who each needed to shorten a sentence and had nowhere to find it.
    """
    folded = fold_spacing(text)
    if limit <= 0:
        return ""
    if len(folded) <= limit:
        return folded
    cut = folded[:limit].rsplit(" ", 1)[0].rstrip(" ,;:.-")
    return f"{cut or folded[:limit]}…"


def words(text: str | None) -> tuple[str, ...]:
    """The words `fold` folds on, unjoined.

    THE SAME TOKENISATION, for the callers that want a SET rather than a
    string -- `nm.open_matter.intake` scores a question against a paragraph on
    overlap, and `nm.work_the_file.summary_contracts` does the same for the account. Both had
    their own copy of the pattern, which the package scan found and this
    grep for `def _fold` did not: they tokenise identically and then differ
    only in what they build from the tokens, so the thing to share is the
    tokenising and not the building.

    Overlap SCORING is what CLAUDE.md §5 permits fuzzy matching to do -- rank,
    never identify. Neither caller decides identity from it.
    """
    return tuple(_WORDS.findall((text or "").lower()))


#: Grammar, not vocabulary. An advocate stating their client speaks in the
#: first person about the representation; an account of events does not. This
#: set is CLOSED and complete in a way a list of party descriptors can never be.
#:
#: IT LIVES HERE BECAUSE TWO LAYERS NEED IT. `nm.Archives.legal_brain.understand.posture` asks it of one
#: quoted span; `nm.work_the_file.summary_contracts` asks it of a fact, to decide whether a
#: statement belongs to the whole file or to one dispute. `domain` may import
#: only `domain`, so a copy in core would have been a copy -- and the failure
#: this predicate guards is exactly the one a second copy reintroduces.
_FIRST_PERSON = re.compile(
    r"\b(?:we|we're|us|our|ours|my|mine|i|client'?s?|behalf)\b", re.I)


def speaks_of_the_representation(text: str | None) -> bool:
    """Has the advocate spoken in the FIRST PERSON about their own side?

    What separates an advocate stating their position -- `we act for`, `we
    want to file`, `our client`, `on behalf` -- from a description of events.

    C3's counterexample contains none of it: *the landlord has issued a quit
    notice to the tenant* names two parties and speaks of neither in the first
    person, so nothing here fires and the reinstatement defect stays impossible.

    ASK IT OF THE ADVOCATE'S WORDS AND NOTHING ELSE. Asked of a string this
    product composed it fires on our own prose -- `_FIRST_PERSON` matches the
    word `client`, and the note "How the client KNOWS any of this has not been
    assessed" once made it true on every matter, settling a COMPLAINANT posture
    out of "a cheque was dishonoured on 3 March". That is why `advocate_words`
    is built from the statements alone, and why this takes a string rather than
    reaching for one itself.
    """
    return bool(_FIRST_PERSON.search(text or ""))


#: WHERE A SENTENCE ENDS. ONE DEFINITION, used to cut an advocate's words into
#: the passages that ground disputes and objectives (the archived `nm.Archives.brain.disputes_objectives`)
#: and to separate the sentences that speak of the representation
#: (`representation_only` below). A boundary missed keeps two sentences together,
#: which is visible; a boundary invented cuts an amount, a section, a case number
#: or a name in half -- "I act for Mr. Rao" became "I act for Mr." So a mark ends
#: a sentence only when a space and a new sentence follow, and a full stop never
#: ends one after a short form. Measured 8 October 2026 on 80 random judgment
#: paragraphs: the earlier cut-at-every-mark rule made 994 cuts, 77 inside a
#: number or reference and 70 after an abbreviation; this one made 202, all clean.
_TERMINATOR_RUN = re.compile(r"([.!?…।]+)([\"'”’)\]}]*)(\s+)")
_OPENERS = "\"'“‘([{"
_CLOSERS = "\"'”’)]}"
_LINE_BREAK = re.compile(r"[ \t]*\n\s*")
#: "s. 34" at the start of a line is a section, not item s, so a lone letter is
#: a list marker only in bracket form: "(a)" or "a)".
_LIST_MARKER = re.compile(r"(?:[-*•·]\s|\(?\d{1,3}[.)]\s|\(?[a-zA-Z]\)\s|\([ivxlc]{1,5}\)\s)")
#: Short forms after which a full stop does not end a sentence: lower case,
#: without the stop. A missing entry only keeps two sentences together.
_SHORT_FORMS = frozenset("""
mr mrs ms dr sri smt shri kum no nos rs inr m/s ltd pvt co corp inc bros vs v viz etc ors anr anrs
sec secs s ss art arts cl cls para paras ch ord r o rr cr crl cri spl addl asst dy jt
govt dept dist hon adv advs st vol pp p ex exs exh exhs annex encl ref sl sr jr prof
capt col gen lt approx regd dt dtd ph mob tel fig misc appl petn resp app cf ibid
i ii iii iv vi vii viii ix xi xii xiii xiv xv
""".split())


def _starts_sentence(text: str, index: int) -> bool:
    """A sentence starts with a letter that is not lower case: a capital or a caseless script."""
    while index < len(text) and text[index] in _OPENERS:
        index += 1
    return index < len(text) and text[index].isalpha() and not text[index].islower()


def _ends_with_short_form(text: str, stop: int) -> bool:
    start = stop
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    token = text[start:stop].lstrip(_OPENERS).rstrip(_CLOSERS)
    if not token or token.replace(".", "").isdigit():
        return False  # A number or a dotted date, e.g. 6.10.2026, can end a sentence.
    return "." in token or (len(token) == 1 and token.isalpha()) or token.lower() in _SHORT_FORMS


def split_passages(text: str, *, every_line: bool = False) -> list[str]:
    """Cut text into passages at sentence ends; joining them gives the text back exactly.

    Each passage after the first starts at its first word; the spacing after a
    sentence stays with it. A blank line or a new list item always starts a
    passage. A single line break starts one only when the line ended a sentence
    and the next starts one -- so hard-wrapped pasted text stays whole -- unless
    `every_line` says each line is its own statement. A piece without letters
    (a bare list number) joins the piece after it.
    """
    cuts = set()
    for match in _TERMINATOR_RUN.finditer(text):
        run, after = match.group(1), match.end()
        if after >= len(text):
            continue
        if "।" in run:  # A Devanagari danda always ends a sentence.
            cuts.add(after)
        elif _starts_sentence(text, after) and not (
                run == "." and _ends_with_short_form(text, match.start(1))):
            cuts.add(after)
    for match in _LINE_BREAK.finditer(text):
        before, after = match.start(), match.end()
        if before == 0 or after >= len(text):
            continue
        if every_line or match.group().count("\n") > 1 or _LIST_MARKER.match(text, after):
            cuts.add(after)
            continue
        previous = text[:before].rstrip(_CLOSERS)
        mark = previous[-1:]
        ended = (mark in ":!?…।"
                 or mark == "." and not _ends_with_short_form(text, len(previous) - 1))
        if ended and (_starts_sentence(text, after) or text[after].isdigit()):
            cuts.add(after)
    pieces, last = [], 0
    for cut in sorted(cuts):
        pieces.append(text[last:cut])
        last = cut
    pieces.append(text[last:])
    passages, carry = [], ""
    for piece in pieces:
        if any(char.isalpha() for char in carry + piece):
            passages.append(carry + piece)
            carry = ""
        else:
            carry += piece
    if carry:
        if passages:
            passages[-1] += carry
        else:
            passages.append(carry)
    return passages


def representation_only(statement: str | None) -> str:
    """The parts of a statement that speak of the representation, and no more.

    AN OPENING BRIEF IS ONE FACT. `Fact.create(statement=turn.message)` records
    the whole message, so "I act for X" and four disputes' narratives share a
    single statement. Anything that wants the first without the others has to
    cut, and the cut belongs here beside the predicate that decides which parts
    qualify -- `nm.work_the_file.summary_contracts` carries these across disputes and
    `nm.Archives.legal_brain.understand.posture` guards one span against the same rule.

    MEASURED 22 September 2026. Carrying the whole fact for the sake of its
    first sentence put the cheque case's events into the lease dispute's
    quotable words, and the role read came back `respondent` reasoned out of
    the wrong dispute -- the client being the one owed rent. Sentences that
    narrate events are dropped; what is kept is what the advocate said about
    whom they act for, in their own words, so a quotation of it still matches.
    """
    # Each line is its own statement here: narrative on the next line must not
    # ride along with "I act for ...".
    parts = [p.strip() for p in split_passages(statement or "", every_line=True)]
    return "\n".join(p for p in parts
                     if p and speaks_of_the_representation(p))


def required_text_fields(cls, exempt: frozenset[str] = frozenset()) -> tuple[str, ...]:
    """Every field of `cls` annotated `str` with no default.

    No default means the TYPE says the caller must supply it. Derived from the
    dataclass rather than listed, so a field added tomorrow is covered tomorrow.
    """
    import dataclasses
    import typing

    try:
        hints = typing.get_type_hints(cls)
    except Exception:  # noqa: BLE001 -- an unresolvable annotation is not our business
        return ()
    out = []
    for f in dataclasses.fields(cls):
        if f.default is not dataclasses.MISSING:
            continue
        if f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
            continue
        if hints.get(f.name) is str and f.name not in exempt:
            out.append(f.name)
    return tuple(out)


def refuses_blank_text(*exempt: str):
    """Class decorator: every REQUIRED string field must carry content.

    ONE MECHANISM FOR ONE RULE, applied by adding a line rather than by writing
    another guard. Twenty-five required string fields accepted `"   "` when
    this was written, and not one of them had been hit -- the three that HAD
    been hit each got their own bespoke fix, which is the arrangement this
    replaces.

    IT WRAPS `__init__`, NOT `__post_init__`, and that is not a style choice.
    `dataclasses` decides whether the generated `__init__` calls
    `__post_init__` at the moment `@dataclass` runs, so attaching one
    afterwards is silently ignored on every class that did not already have
    one -- which is most of them, and exactly the classes this is for. The
    first version did that and validated nothing; it passed its own test
    because the test only exercised a class that already had `__post_init__`.

    The type's own validation runs first, so a class with a specific message
    keeps it and this catches only what that message does not cover. Exempt a
    field by name where its emptiness is a state the type must be able to
    express -- `quoted` on a posture read is how "the model quoted nothing" is
    reported, and refusing it would remove a state rather than add a guard.
    """
    exempted = frozenset(exempt)

    def decorate(cls):
        original_init = cls.__init__

        def __init__(self, *args, **kwargs) -> None:  # noqa: N807
            original_init(self, *args, **kwargs)
            for name in required_text_fields(type(self), exempted):
                if blank(getattr(self, name, None)):
                    raise ValueError(
                        f"{type(self).__name__}.{name} is required and carries "
                        f"nothing. A value that is PRESENT and EMPTY is absent: "
                        f"`if not x` is a character test and '   ' is three of "
                        f"them. Supply it, or exempt the field on the decorator "
                        f"with the reason its emptiness is meaningful.")

        cls.__init__ = __init__
        # RECORDED ON THE CLASS so nothing has to restate it. The test that
        # sweeps the population reads this rather than keeping its own copy --
        # two lists of "which fields may be empty" is the same second-copy
        # defect this module exists to close, one level up.
        cls.__nm_blank_exempt__ = exempted
        return cls

    return decorate
