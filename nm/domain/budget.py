"""ONE BUDGET FOR ONE OPERATION, AND A TRUNCATION IS NEVER AN ANSWER.
BK-41-AC1, BK-29-AC1, BK-29-AC2, BK-49-AC1. P37.

    from nm.domain.budget import Budget, Spend, Completion, refuse_partial

WHY ONE MECHANISM AND NOT SIX
-------------------------------
An operation can exhaust six different things -- wall time, model tokens,
money, retries, delegated children, and the advocate's patience expressed as a
cancellation -- and every one of them was, before this, either unbounded or
bounded at a call site. Six separate limits mean six call sites deciding what
"over" means, and the one that matters on the day is whichever was forgotten.

    THE BUDGET IS ONE OBJECT AND `remaining()` ANSWERS FOR ALL SIX. A caller
    asks once, gets the reason, and cannot ask about time while forgetting
    money.

RESETTING PER CHILD IS THE DEFECT, NOT THE FEATURE
----------------------------------------------------
A delegated child that starts with a fresh budget makes the parent's budget a
suggestion: five children of one minute each is five minutes under a
one-minute cap. `Spend.plus` accumulates into the SAME ledger and
`Budget.for_child` hands down what is LEFT, never a copy of the original.

A TRUNCATED ANSWER IS NOT A SHORT ANSWER. BK-49
-------------------------------------------------
A provider that stops at the token limit returns prose that ends mid-sentence,
or JSON that happens to close its braces. Both parse. Both are wrong in a way
no downstream check can see, because what is missing left no trace -- and the
one place it will be noticed is a hearing.

`Completion` is therefore carried on every result and `COMPLETE` is not the
default: an adapter that says nothing about how the provider stopped produces
`NOT_ESTABLISHED`, which `usable_for_legal_work` refuses exactly as firmly as
a known truncation. §9's rule, at the point where the absent input is a
sentence somebody will read out in court.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from nm.domain.text import blank


class Completion(str, Enum):
    """HOW THE PROVIDER STOPPED. Five answers, and only one of them is done.

        COMPLETE         the model finished what it was saying.
        LENGTH_LIMITED   it ran out of room. The text ends where the budget
                         did, not where the thought did.
        FILTERED         the provider refused part or all of it.
        CANCELLED        we stopped it. Whatever arrived is partial by our own
                         choice, which is the one partial result that is
                         sometimes worth keeping.
        NOT_ESTABLISHED  the adapter did not say. NOT a synonym for complete.
    """

    COMPLETE = "complete"
    LENGTH_LIMITED = "length_limited"
    FILTERED = "filtered"
    CANCELLED = "cancelled"
    NOT_ESTABLISHED = "not_established"

    @classmethod
    def not_established(cls) -> "Completion":
        return cls.NOT_ESTABLISHED

    @property
    def usable_for_legal_work(self) -> bool:
        """ONLY `COMPLETE`, and written once so no consumer decides.

        `NOT_ESTABLISHED` is refused as firmly as a known truncation, because
        an adapter that did not look and a provider that cut the answer off
        are indistinguishable downstream -- and the difference does not matter
        to the advocate reading the result.
        """
        return self is Completion.COMPLETE

    def said(self) -> str:
        if self is Completion.COMPLETE:
            return "The model finished this answer."
        if self is Completion.LENGTH_LIMITED:
            return ("The model ran out of room and this answer stops where "
                    "the budget did, not where the reasoning did. It is not "
                    "a short answer; it is an unfinished one.")
        if self is Completion.FILTERED:
            return ("The provider refused part of this. That is a fact about "
                    "the provider and not about the matter.")
        if self is Completion.CANCELLED:
            return "This was stopped before it finished."
        return ("Nothing recorded how this answer ended, so it is not known "
                "to be finished.")


class Exhausted(str, Enum):
    """WHICH BUDGET RAN OUT. Named, because the next step differs.

    More time will not help a token exhaustion, and a bigger token ceiling
    will not help a cancelled operation. A single `over_budget` boolean sends
    whoever reads it to look at the wrong one.
    """

    NONE = "none"
    TIME = "time"
    TOKENS = "tokens"
    COST = "cost"
    RETRIES = "retries"
    CHILDREN = "children"
    CANCELLED = "cancelled"

    @classmethod
    def not_established(cls) -> "Exhausted":
        return cls.NONE


@dataclass(frozen=True)
class Spend:
    """WHAT ONE OPERATION HAS ALREADY USED, INCLUDING WHAT IT WASTED.

    `failed_children`, `retries` and `discarded_results` are counted here
    rather than dropped, because whole-task accounting is the whole point:
    an approach that is fast when its failures are not counted is not fast,
    and BK-92-AC4's negative control is exactly that exclusion.
    """

    elapsed_ms: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    retries: int = 0
    children: int = 0
    failed_children: int = 0
    discarded_results: int = 0
    """Work that completed and was not used -- a speculative child whose
    answer the lead did not need. IT WAS STILL PAID FOR."""

    def plus(self, other: "Spend") -> "Spend":
        return Spend(
            elapsed_ms=self.elapsed_ms + other.elapsed_ms,
            tokens=self.tokens + other.tokens,
            cost_usd=self.cost_usd + other.cost_usd,
            retries=self.retries + other.retries,
            children=self.children + other.children,
            failed_children=self.failed_children + other.failed_children,
            discarded_results=self.discarded_results + other.discarded_results)

    def as_dict(self) -> dict:
        return {"elapsed_ms": self.elapsed_ms, "tokens": self.tokens,
                "cost_usd": round(self.cost_usd, 6), "retries": self.retries,
                "children": self.children,
                "failed_children": self.failed_children,
                "discarded_results": self.discarded_results}


@dataclass(frozen=True)
class Budget:
    """What one operation may spend, and what it has. ONE OBJECT, SIX LIMITS.

    `cancelled` is a limit like the others rather than a separate flag,
    because a caller that asked "am I over budget?" and forgot to ask "was I
    cancelled?" keeps working after the advocate closed the tab.
    """

    max_ms: int = 0
    max_tokens: int = 0
    max_cost_usd: float = 0.0
    max_retries: int = 0
    max_children: int = 0
    spend: Spend = field(default_factory=Spend)
    cancelled_at: str = ""

    #: A LIMIT OF ZERO IS "NOT BOUNDED HERE", not "nothing allowed".
    #:
    #: The alternative reading was tried and is worse: a default-constructed
    #: budget would then refuse everything, and every caller would build one
    #: with six numbers it had not thought about -- which is the sixteen
    #: hand-picked ceilings this packet exists to remove, in a new place.
    #: `declared()` reports which limits are actually bounded, so an operation
    #: running under no limits is VISIBLE rather than silently unlimited.

    def declared(self) -> tuple[str, ...]:
        return tuple(name for name, value in (
            ("time", self.max_ms), ("tokens", self.max_tokens),
            ("cost", self.max_cost_usd), ("retries", self.max_retries),
            ("children", self.max_children)) if value)

    def exhausted(self) -> Exhausted:
        """WHICH ONE RAN OUT. Cancellation is checked first: an operation the
        advocate stopped is stopped whatever else is true of it."""
        if not blank(self.cancelled_at):
            return Exhausted.CANCELLED
        s = self.spend
        if self.max_ms and s.elapsed_ms >= self.max_ms:
            return Exhausted.TIME
        if self.max_tokens and s.tokens >= self.max_tokens:
            return Exhausted.TOKENS
        if self.max_cost_usd and s.cost_usd >= self.max_cost_usd:
            return Exhausted.COST
        if self.max_retries and s.retries >= self.max_retries:
            return Exhausted.RETRIES
        if self.max_children and s.children >= self.max_children:
            return Exhausted.CHILDREN
        return Exhausted.NONE

    @property
    def spent_out(self) -> bool:
        return self.exhausted() is not Exhausted.NONE

    def spend_on(self, more: Spend) -> "Budget":
        """Record what was used. THE LEDGER IS THE OPERATION'S, NOT A CALL'S."""
        return replace(self, spend=self.spend.plus(more))

    def cancel(self, at: str) -> "Budget":
        if blank(at):
            raise ValueError("a cancellation records when it was asked for")
        return self if not blank(self.cancelled_at) else replace(
            self, cancelled_at=at)

    def for_child(self) -> "Budget":
        """WHAT IS LEFT, never a fresh copy. BK-92-AC4.

        A child that started with the parent's original budget would make the
        parent's budget a suggestion -- five children of one minute each under
        a one-minute cap -- and the delegation comparison would then be
        measuring an approach that was never actually bounded.

        The child's own ledger starts empty because its spend is added back to
        the parent's by `spend_on`; carrying the parent's spend down as well
        would count every token twice.
        """
        s = self.spend
        return Budget(
            max_ms=max(0, self.max_ms - s.elapsed_ms) if self.max_ms else 0,
            max_tokens=max(0, self.max_tokens - s.tokens) if self.max_tokens else 0,
            max_cost_usd=(max(0.0, self.max_cost_usd - s.cost_usd)
                          if self.max_cost_usd else 0.0),
            max_retries=max(0, self.max_retries - s.retries) if self.max_retries else 0,
            max_children=max(0, self.max_children - s.children) if self.max_children else 0,
            cancelled_at=self.cancelled_at)

    def said(self) -> str:
        """WHAT THE ADVOCATE READS when an operation stops. BK-41-AC1.

        It names what ran out and what that means for the work, because "this
        took too long" and "this cost too much" call for different decisions
        and only one of them is fixed by waiting.
        """
        which = self.exhausted()
        if which is Exhausted.NONE:
            return ("This is still within its limits."
                    if self.declared() else
                    "No limit is recorded on this operation, so nothing here "
                    "would stop it running long.")
        if which is Exhausted.CANCELLED:
            return (f"You stopped this at {self.cancelled_at}. Whatever had "
                    f"already been saved is saved; nothing further was "
                    f"attempted.")
        return {
            Exhausted.TIME: ("This ran out of time. What was finished is "
                             "saved and the rest was not attempted."),
            Exhausted.TOKENS: ("This reached its output limit. The answer is "
                               "unfinished rather than short."),
            Exhausted.COST: ("This reached the cost limit set for it. Nothing "
                             "further was attempted."),
            Exhausted.RETRIES: ("This failed as many times as it was allowed "
                                "to retry. The failure is real rather than "
                                "transient."),
            Exhausted.CHILDREN: ("This reached the limit on delegated work. "
                                 "The lead finished on what it had."),
        }[which]

    def as_dict(self) -> dict:
        return {"max_ms": self.max_ms, "max_tokens": self.max_tokens,
                "max_cost_usd": self.max_cost_usd,
                "max_retries": self.max_retries,
                "max_children": self.max_children,
                "declared": list(self.declared()),
                "exhausted": self.exhausted().value,
                "cancelled_at": self.cancelled_at,
                "spend": self.spend.as_dict(),
                "said": self.said()}


def refuse_partial(completion: Completion, *, doing: str) -> str:
    """Why this result may not be used for legal work, or "". BK-29-AC2.

    ASKED BEFORE THE RESULT IS ACCEPTED, not after it has been rendered. The
    criterion's words are *before dependent legal work is accepted*, and a
    check that runs after the answer is on the page is a disclosure rather
    than a control.
    """
    if completion.usable_for_legal_work:
        return ""
    return (f"{doing} rests on a model answer that is "
            f"{completion.value.replace('_', ' ')}. {completion.said()} It is "
            f"not accepted as a complete result.")


#: PROGRESS AN OPERATION MAY REPORT, and it is a stage rather than a number.
#:
#: BK-41-AC1 asks that an advocate see *what is happening, what remains
#: reliable and what they can safely do next*. A percentage answers none of
#: those and is invented: nothing in this product knows how far through a
#: model read it is. A named stage that was actually reached is a fact.
STAGES: tuple[str, ...] = (
    "accepted", "reading the file", "retrieving authority", "reasoning",
    "checking quotations", "saved",
)


def progress(reached: str, *, saved: bool) -> dict:
    """Where this operation ACTUALLY got to. BK-41-AC1.

    NO PERCENTAGE. A number invented from a stage index is a claim about how
    much is left, and this product does not know that; it knows what it has
    finished and what it has written down. `saved` is read from the store by
    the caller, never assumed from the stage -- reaching "saved" and having
    saved are different facts, and the first one is the one a progress bar
    would happily report.
    """
    if reached not in STAGES:
        return {"stage": "not established", "saved": bool(saved),
                "said": ("Nothing recorded where this got to, so how far it "
                         "went is not known."),
                "safe_next": "Reopen the matter; anything saved is on the file."}
    return {
        "stage": reached,
        "saved": bool(saved),
        "said": (f"Reached: {reached}."
                 + (" What was reached is written to the file."
                    if saved else
                    " Nothing has been written to the file yet.")),
        "safe_next": ("Reopen the matter to see what was saved."
                      if saved else
                      "Nothing was saved, so nothing needs undoing."),
    }
