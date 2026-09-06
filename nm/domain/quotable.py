"""What a read may QUOTE, and what it may only READ. One value for both.

THE DEFECT THIS EXISTS FOR — B-108
------------------------------------
A stronger model quoted this product's own text back at it, and the guard
correctly refused the read. On the first turn after the hard-tier escalation,
the cause read quoted a span running across three lines of the account
including our own `[1984-04-15]` date stamp. The verbatim guard refused it —
the span is not in anything the advocate wrote — the cause was not taken, and
the turn was withheld.

THE GUARD WAS RIGHT. Accepting that span would let a model settle a cause by
quoting our own rendering back at us, and the posture reader was measured
failing exactly that way: the prompt carries this product's own outstanding
questions, and one of them names both sides of a dispute.

WHAT WAS WRONG IS THAT THE PROMPT INVITED IT. The account is handed over as
one block with no mark saying which parts are the advocate's words, and the
model was asked to guess. The gap between what a model is SHOWN and what it
may QUOTE widened the moment the model got good enough to use its whole
context.

MEASURED ACROSS EVERY GUARDED READ, 6 September 2026
------------------------------------------------------
It was not one read. On a three-fact matter with one follow-up question:

    read          the guard accepted        shown and NOT quotable
    ------------  ------------------------  -----------------------------
    cause         message + advocate words  6 of 8 spans
    posture       message + advocate words  6 of 8 spans
    chronology    the message ONLY          13 of 14 — the whole file
    dispute       the message ONLY          8 of 9
    issues        the account ONLY          2 of 7 — INCLUDING THIS TURN
    factors       account + the entry       6 of 11

Two reads could not quote the file they were shown. Two could not quote the
message they were handed. Every one of them was shown `[2024-04-15]` stamps,
`fact_e2f2a82f86f0` identifiers and this product's own headings, with nothing
saying those were off limits.

WHY A TYPE AND NOT A SENTENCE IN EACH PROMPT
----------------------------------------------
Because the sentence would drift from the guard within a slice, which is what
already happened. `build_prompt(message, account)` and `interpret(message,
data, advocate_words)` took SEPARATE parameters, and a caller passing
different things to the two is not a mistake anyone can see — it is what the
signatures ask for.

One value goes to both. `block()` renders the prompt section and `accepts()`
is the guard, off the same fields, so a second copy is not possible rather
than merely discouraged (CLAUDE.md §4).

THE SPLIT IS TURN / FILE / CONTEXT, and it is not cosmetic:

    turn     what the advocate said THIS TURN
    file     what the advocate said on earlier turns, verbatim
    context  this product's own rendering — stamps, notes, identifiers

`turn` and `file` are quotable and `context` is not, so a read that may only
quote the latest message simply leaves `file` empty. The labels then say so in
the prompt, from the same fields, with no second list to keep in step.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from nm.domain.text import fold

#: THE SECTION HEADINGS, as constants, because two other places need to find
#: these sections in a rendered prompt and a literal copy there goes stale the
#: moment the wording changes.
#:
#: The scripted model doubles slice on WORDS_HEADING to read the advocate's
#: content and skip this product's own instructions -- which is right, and is
#: exactly what a real model has to do from the words alone. They used to slice
#: on a hard-coded "THE FILE SO FAR"; when that heading went, `str.find`
#: returned -1, the fallback scanned the WHOLE prompt, and the doubles began
#: spotting issues in our own instructions. Nothing failed loudly.
WORDS_HEADING = "THE ADVOCATE'S OWN WORDS"
NOTHING_HEADING = "THE ADVOCATE HAS WRITTEN NOTHING"
CONTEXT_HEADING = "FOR CONTEXT ONLY"


@dataclass(frozen=True)
class Quotable:
    """The advocate's words, split by when they were said, plus context.

    EMPTY IS A LEGITIMATE VALUE for every field. A first turn has no `file`; a
    read that shows no rendering has no `context`; and `words` being empty
    means NOTHING MAY BE QUOTED, which `accepts` refuses rather than treating
    as "no restriction" — an absent input must never read as permission.
    """

    turn: str = ""
    file: str = ""
    context: str = ""

    #: What the context IS, in the advocate's terms. Rendered into the prompt
    #: so the model is told why it may not quote from it, rather than only
    #: that it may not -- a rule with a reason is one a model can apply to the
    #: line this list did not anticipate.
    context_is: str = ("this product's own rendering of the file: date stamps "
                       "in [brackets], internal identifiers, and notes we "
                       "wrote")

    @property
    def words(self) -> str:
        """The one string a quotation must be found in.

        `accepts` checks this and `block` labels its two halves. There is no
        third place, which is the entire point of the type.
        """
        return "\n".join(part for part in (self.turn, self.file)
                         if part.strip())

    def accepts(self, quoted: str) -> bool:
        """Is this span the advocate's own words?

        Folded, so typography does not decide it -- the corpus and the models
        both reflow text, and a character-exact comparison would fail on
        formatting and teach everyone to switch the guard off. Folding is
        exact after typography, never a similarity score (CLAUDE.md §5).
        """
        if not quoted.strip():
            return False
        held = fold(self.words)
        return bool(held) and fold(quoted) in held

    def refusal(self, quoted: str) -> str:
        """The refusal, worded once.

        Six reads each had their own sentence for this and they had drifted
        apart in the detail that matters -- whether the span was empty, and
        whether there was anything to check it against at all.
        """
        if not quoted.strip():
            return "nothing quoted to support it"
        if not fold(self.words):
            return (f"there is nothing the advocate has written to check a "
                    f"quotation against, so {quoted[:60]!r} cannot be "
                    f"accepted as their words")
        return f"the quoted span is in nothing the advocate wrote: {quoted[:60]!r}"

    def plus(self, more: str) -> "Quotable":
        """The same, with one more piece of the advocate's own text quotable.

        For a read that walks entries and may quote the entry it is on --
        `factors` does, because the account it was shown may have been
        truncated by the budget while the entry itself is whole. The PROMPT
        showed that entry, so accepting a quotation from it is not a widening;
        refusing one would be the gap this module exists to close.
        """
        return replace(self, file="\n".join(
            p for p in (self.file, more) if p.strip()))

    def block(self) -> str:
        """The prompt section, labelled so the model is not guessing.

        ORDER IS DELIBERATE. The quotable text comes FIRST and the rule is
        stated on it, because a model that stops reading early must stop
        having read the part it is allowed to use.
        """
        out: list[str] = []
        if self.words.strip():
            out.append(
                f"{WORDS_HEADING}. A quotation MUST be copied from this "
                f"section, exactly, and from nowhere else:")
            if self.turn.strip():
                out.append(f"  [this turn]\n{self.turn.strip()}")
            if self.file.strip():
                out.append(f"  [earlier turns]\n{self.file.strip()}")
        else:
            # SAID, NOT LEFT BLANK. A read handed nothing quotable and told
            # nothing about it will quote from the context and be refused for
            # doing what the prompt implied.
            out.append(
                f"{NOTHING_HEADING} THIS READ MAY QUOTE. Do not quote "
                f"anything; report what needs no quotation, or nothing.")

        if self.context.strip():
            out.append(
                f"{CONTEXT_HEADING} - DO NOT QUOTE FROM THIS SECTION. It "
                f"is {self.context_is}. Read it to understand the matter; "
                f"a span copied from here will be refused:"
                f"\n{self.context.strip()}")
        return "\n\n".join(out)
