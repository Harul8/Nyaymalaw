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

        nm/core/chronology.py   words only  ── the same three characters
        nm/core/dispute.py      words only
        nm/core/posture.py      words only
        nm/core/grounding.py    words only, plus the case-name `vs`/`v` pivot
        nm/domain/issue.py      WHITESPACE COLLAPSE ONLY — punctuation kept
        nm/domain/decision.py   WHITESPACE COLLAPSE ONLY

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
    why — `nm.core.grounding` folds `vs` and `versus` to `v` because a case
    name written both ways is one case, and that is a fact about citations
    rather than about text. What no caller may do is define its own base.

    `tests/test_one_fold.py` scans `nm/` and fails the build on a second
    definition, for the same reason `test_citation_patterns.py` scans for a
    second provision pattern: the copies above were not written by someone
    ignoring a rule, they were written by six people who each needed a fold
    and had no one place to find it.
    """
    return " ".join(words(text))


def words(text: str | None) -> tuple[str, ...]:
    """The words `fold` folds on, unjoined.

    THE SAME TOKENISATION, for the callers that want a SET rather than a
    string -- `nm.core.intake` scores a question against a paragraph on
    overlap, and `nm.domain.summary` does the same for the account. Both had
    their own copy of the pattern, which the package scan found and this
    grep for `def _fold` did not: they tokenise identically and then differ
    only in what they build from the tokens, so the thing to share is the
    tokenising and not the building.

    Overlap SCORING is what CLAUDE.md §5 permits fuzzy matching to do -- rank,
    never identify. Neither caller decides identity from it.
    """
    return tuple(_WORDS.findall((text or "").lower()))


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
