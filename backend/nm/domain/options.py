"""COMPARING ROUTES, AND SAYING WHICH ONE. BK-96-AC1, BK-55-AC1/AC2. P27.

    from nm.domain.options import Option, Figure, Certainty, compare

WHAT THIS IS FOR
------------------
An advocate has four ways to get the client what they want, and the useful
answer is not four tidy paragraphs. BK-96-AC1 says it in as many words: NM
states its supported view and why the alternatives lose, *without replacing it
with a neutral menu or fabricated practical figures*.

Those are the two failures, and they pull in opposite directions:

* THE MENU. Four equally polished options and no view. It looks balanced and
  it hands the whole judgement back to the reader, who asked precisely because
  they wanted it exercised.
* THE FABRICATED FIGURE. A cost, a duration or a recovery invented to make the
  comparison look complete. A number in a table reads as measured whatever
  produced it, and it is the part a client repeats.

`Figure` refuses the second by construction: every number carries whether it is
ESTABLISHED, an ESTIMATE, or UNKNOWN, and an unknown is rendered as unknown
rather than dropped or guessed.

DOING NOTHING AND SETTLING ARE ROUTES
---------------------------------------
`Route.DO_NOTHING` and `Route.SETTLE` are members, not omissions. A comparison
that silently excludes them is a comparison rigged toward acting -- and doing
nothing is frequently the right advice on a claim whose relief is hollow, which
is exactly what P23's `ReliefState.DEFEATED` reports.

PROPORTIONALITY DOES NOT VETO
-------------------------------
It is compared and stated; it never removes a route from the comparison. That
is E3's NEVER, and `nm.core.relief` already keeps proportionality out of its
`_DELIVERS` set for the same reason. A disproportionate route the client
insists on is still their decision to take.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nm.domain.spoken import named
from nm.domain.text import blank, refuses_blank_text


class Route(str, Enum):
    """The kinds of thing an advocate can actually do. NOT_ASSESSED is the
    third state for a route somebody named without classifying."""

    LITIGATE = "litigate"
    ARBITRATE = "arbitrate"
    NEGOTIATE = "negotiate"
    SETTLE = "settle"
    STATUTORY_REMEDY = "statutory_remedy"
    DO_NOTHING = "do_nothing"
    OTHER = "other"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_established(cls) -> "Route":
        return cls.NOT_ASSESSED


class Certainty(str, Enum):
    """WHERE A NUMBER CAME FROM. The whole point of `Figure`.

    An ESTIMATE presented as ESTABLISHED is the fabricated practical figure
    BK-96-AC1 names, and the reader cannot tell them apart from the number
    alone -- which is why the number never travels without this.
    """

    ESTABLISHED = "established"
    ESTIMATE = "estimate"
    UNKNOWN = "unknown"

    @classmethod
    def not_established(cls) -> "Certainty":
        return cls.UNKNOWN


@refuses_blank_text("basis", "text")
@dataclass(frozen=True)
class Figure:
    """One quantity, with where it came from.

    `text` is what the advocate reads; `basis` is what it rests on. An
    ESTABLISHED figure with no basis is refused by `problems()` -- established
    means somebody can check it, and a figure nobody can check is an estimate
    whatever it is called.
    """

    text: str = ""
    certainty: Certainty = Certainty.UNKNOWN
    basis: str = ""

    def problems(self) -> tuple[str, ...]:
        out: list[str] = []
        if self.certainty is Certainty.ESTABLISHED and blank(self.basis):
            out.append(f"{named(self.text)} is recorded as established and names "
                       f"nothing it rests on; established means checkable")
        if self.certainty is not Certainty.UNKNOWN and blank(self.text):
            out.append("a figure with no value is not an estimate, it is a gap")
        return tuple(out)

    def render(self) -> str:
        """How it reads. An unknown says so rather than showing as blank --
        CLAUDE.md §9's third state, visible in the OUTPUT."""
        if self.certainty is Certainty.UNKNOWN or blank(self.text):
            return "not established"
        if self.certainty is Certainty.ESTIMATE:
            return f"{self.text} (estimate: {self.basis or 'no basis recorded'})"
        return self.text


@refuses_blank_text("why_it_loses", "objective_fit")
@dataclass(frozen=True)
class Option:
    """One route, compared on what actually decides between routes.

    The five quantities are `Figure`s rather than strings so the comparison
    can tell a measured cost from a guessed one. `enforceability` is here and
    not on the relief because the question *can this route's outcome actually
    be enforced* differs by route -- an award and a decree are not enforced
    the same way.
    """

    route: Route
    summary: str
    objective_fit: str = ""
    """HOW IT SERVES THE CLIENT'S RECORDED OBJECTIVE. BK-55-AC2 compares
    against that objective, not against an abstract idea of a good outcome."""

    useful_recovery: Figure = field(default_factory=Figure)
    cost: Figure = field(default_factory=Figure)
    time: Figure = field(default_factory=Figure)
    disruption: Figure = field(default_factory=Figure)
    enforceability: Figure = field(default_factory=Figure)
    proportionate: bool | None = None
    """None means NOT ASSESSED. It never removes the option from the
    comparison -- E3's NEVER -- it is stated alongside."""

    adverse: tuple[str, ...] = ()
    """Material adverse law or evidence against this route. BK-55-AC4."""

    why_it_loses: str = ""
    """Filled by `compare` on every option that is not the supported view. An
    option that loses without a reason is a menu item."""

    def figures(self) -> tuple[Figure, ...]:
        return (self.useful_recovery, self.cost, self.time, self.disruption,
                self.enforceability)

    def problems(self) -> tuple[str, ...]:
        return tuple(p for f in self.figures() for p in f.problems())

    def unknown_count(self) -> int:
        return sum(1 for f in self.figures()
                   if f.certainty is Certainty.UNKNOWN)


@dataclass(frozen=True)
class Comparison:
    """The compared routes and the view taken. NOT a ranked list.

    `supported` names one option, or nothing with a reason. Both are answers;
    what this type cannot express is a comparison that quietly has no view.
    """

    options: tuple[Option, ...] = ()
    supported: Route | None = None
    because: str = ""
    no_view_because: str = ""

    def problems(self) -> tuple[str, ...]:
        """Everything that makes this comparison unfit to serve."""
        out: list[str] = [p for o in self.options for p in o.problems()]
        if not self.options:
            out.append("nothing was compared")
        if self.supported is None and blank(self.no_view_because):
            out.append(
                "no option is supported and no reason is given for having no "
                "view; that is a menu, and BK-96-AC1 refuses one")
        if self.supported is not None and blank(self.because):
            out.append(
                f"{self.supported.value} is supported and nothing says why")
        losing = [o for o in self.options if o.route is not self.supported]
        for option in losing:
            if blank(option.why_it_loses):
                out.append(
                    f"{option.route.value} is in the comparison and nothing "
                    f"says why it loses")
        return tuple(out)


def compare(options: tuple[Option, ...], *, supported: Route | None,
            because: str = "", no_view_because: str = "") -> Comparison:
    """Assemble a comparison. IT DOES NOT PICK THE WINNER.

    The view is passed in because choosing between routes is legal judgement,
    and a scoring function over five figures would be exactly the "confidently
    wrong" arithmetic CLAUDE.md §5 refuses for a different question. What this
    DOES enforce is that a view was taken, or that its absence was explained.

    A route named as supported that is not among the options is refused rather
    than added -- the alternative is a recommendation for a route nobody
    compared.
    """
    if supported is not None and not any(o.route is supported for o in options):
        raise ValueError(
            f"{supported.value} is supported and is not among the options "
            f"compared ({[o.route.value for o in options]}); a view about a "
            f"route nobody compared rests on nothing")
    return Comparison(options=options, supported=supported, because=because,
                      no_view_because=no_view_because)
