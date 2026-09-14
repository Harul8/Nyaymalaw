"""An enum reaches the advocate through a PHRASE IT OWNS, never as its value.

THE DEFECT THIS REFUSES, measured 7 September 2026. Six `Element` sites in the
turn engine rendered an enum value straight onto the page:

    {i.statement} [{i.kind.value}; runs against {i.runs_against.value}; ...]
    {pos.element} [burden {whose}; {elements.standard.value}; {detail}]
    {item.what} — held by {item.holder.value}, {item.form.value}

So an advocate read `held_not_found`, `balance_of_probabilities`,
`certified_copy` and `opposite_party`. Those are identifiers. `held_not_found`
in particular means nothing at all to a reader — it is this product's word for
a retrieval defect, and the one place it must never appear is in front of the
person it was invented to protect.

WHY A MIXIN AND NOT A PHRASE TABLE
------------------------------------
A table mapping every enum member to a phrase, kept anywhere else, is a second
owner: add a member, forget the row, and the member renders as its value again
with nothing failing. CLAUDE.md §4 asks what makes the second copy impossible,
and the answer here is that the phrases live ON the enum and completeness is
checked WHEN THE CLASS IS CREATED. A member with no phrase is an ImportError,
not a surprise in a served turn.

`__init_subclass__` runs before the members exist, so the check is deferred to
`complete()`, which each enum calls immediately after its own definition. That
call is itself checked -- `tests/test_spoken.py` draws its population from
`backend/nm/` and fails on a `Spoken` enum that never called it, because a check
somebody must remember to invoke is the arrangement this file exists against.

WHAT `said` IS NOT
--------------------
It is not a translation layer and it is not prose. It is the SHORTEST phrase an
advocate would actually use for that member -- "a certified copy", not "the
document is a certified copy". The sentence around it belongs to the caller,
who knows the sentence.
"""
from __future__ import annotations

from enum import Enum


class Spoken:
    """Mixin for an enum whose members are shown to the advocate.

    Subclasses declare `SAID = nonmember({...})`, a mapping from member VALUE
    to the phrase, and call `complete()` after the class body. `said` reads it.

    `nonmember` IS NOT OPTIONAL. Any plain assignment inside an `Enum` body
    becomes a member, so `SAID = {...}` makes a member whose value is the
    dict -- and on a `str, Enum` that is the dict rendered as a string.
    """

    #: member VALUE -> the phrase. Declared with `enum.nonmember` in each
    #: subclass, because ANY plain assignment in an Enum body becomes a
    #: member: the first version of this made `SAID` an enum member whose
    #: value was the dict rendered as a string, and `complete()` then reported
    #: twenty-six stale members, one per character. The failure was loud,
    #: which is the only reason it cost minutes rather than a slice.
    SAID: dict[str, str] = {}

    @property
    def said(self) -> str:
        """The phrase for this member.

        No fallback to `self.value`. A fallback is what makes a missing phrase
        invisible -- the member renders as an identifier and the build stays
        green, which is precisely the failure being removed. `complete()`
        makes the KeyError unreachable rather than caught.
        """
        return self.SAID[self.value]

    @classmethod
    def complete(cls) -> None:
        """Every member has a phrase, checked at import.

        Called immediately after the class body because `__init_subclass__`
        runs before the members are attached and cannot see them.

        RAISES RATHER THAN ASSERTS, so the promise holds under `python -O`.
        It did not for half a day: an assert here is deleted by `-O`, which
        would have made this a no-op and moved the failure to a `KeyError`
        from `said` in the middle of a served turn (BK-17).
        """
        # RAISED, NOT ASSERTED. This method's whole promise is that a
        # missing phrase is an ImportError rather than a surprise in a
        # served turn -- and `python -O` deletes an assert, which would
        # make `complete()` a no-op and `said` raise KeyError mid-turn.
        # The docstring said the opposite for half a day (BK-17).
        missing = sorted(m.value for m in cls if m.value not in cls.SAID)
        if missing:
            raise ValueError(
                f"{cls.__name__} is shown to the advocate and these members "
                f"have no phrase: {missing}. Add one to SAID -- without it "
                f"the member renders as its own identifier, which is what "
                f"`said` exists to prevent.")

        stale = sorted(set(cls.SAID) - {m.value for m in cls})
        if stale:
            raise ValueError(
                f"{cls.__name__}.SAID carries phrases for members that no "
                f"longer exist: {stale}. A phrase that outlives its member "
                f"is a rule nobody can reach and the next reader has to "
                f"work out why.")


def dispute(label: str) -> str:
    """How a THREAD is named to a person. Never its key. B-103, J-5.

    THE KEY AND THE LABEL ARE TWO STRINGS AND ONE CANNOT BE BOTH. A derived
    value is keyed by thread id so that two threads' limitations are different
    values; the advocate reads the label, because nobody can answer a question
    addressed to a database key.

    WHERE NO LABEL EXISTS the answer is that the dispute is unlabelled -- NOT
    the id. A fallback to the key is precisely how this leak reached a served
    turn: the fallback is what makes a missing label invisible, and the line
    then reads as though the product meant to say `thr_380e2b97f5a6`.

    It lives beside `Spoken` because it is the same rule one level out: an
    internal name reaches an advocate through a phrase somebody wrote, or it
    does not reach them at all.
    """
    clean = (label or "").strip()
    return repr(clean) if clean else "an unlabelled dispute"


def phrase(value: Enum | None, absent: str = "not stated") -> str:
    """`said` for a value that may be missing.

    A separate function rather than a default on `said`, because ABSENT and
    UNKNOWN are different facts and the caller is the only one who knows which
    it has. An enum member called `unknown` says "not established"; a `None`
    says nobody asked.
    """
    if value is None:
        return absent
    said = getattr(value, "said", None)
    if said is not None:
        return said
    # A plain enum that nothing has taught to speak. Deliberately loud rather
    # than a quiet fallback to `.value`: this is the exact silence the module
    # exists to remove, and it should be found in a test, not in a transcript.
    raise TypeError(
        f"{type(value).__name__} is being shown to the advocate and does not "
        f"subclass Spoken, so it would render as its own identifier. Give it "
        f"a SAID mapping.")
