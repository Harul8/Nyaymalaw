"""THE READS. Every structured model call the product makes, and what it costs
to get one wrong.

WHY THIS TABLE EXISTS
----------------------
Eleven reads were added across ten slices, each with its own schema, its own
guards and its own tests. Nothing anywhere said which of them CHANGE A NUMBER
THE ADVOCATE ACTS ON and which enrich an answer — so all eleven ran on the
cheap tier, including the one that decides what a limitation period runs from.

Measured on GS-15 (B-088): the correction read fired on one run and returned
nothing on the next, on identical input. The scenario reported a claim as
expired in 1987 for an agreement dated 2024, and every citation on the turn was
verbatim and correct.

DECISIVE IS NOT "IMPORTANT"
-----------------------------
It is a narrow test and the narrowness is the point: does the read's output
change a DATE, an AMOUNT, or WHICH LAW IS READ? If it does, being wrong is not
a worse answer — it is a right-looking answer about something else, and no
downstream check can catch it because everything downstream is derived from it.

The issue read is not decisive and it matters enormously; a missed issue makes
the answer thinner, and the advocate can see it is thinner. A missed correction
makes the answer confident and wrong about the one number they will act on.

WHAT ESCALATION IS AND IS NOT
-------------------------------
PRD §7.4.1: a step moves to `hard` only with a recorded measurement showing the
quality it bought. B-088 is that measurement for the decisive reads. It is not
a measurement for the rest, and they stay where they are.

AND WHEN `hard` IS NOT CONFIGURED, THE DEGRADATION IS SAID OUT LOUD. A decisive
read that quietly falls back to the cheap tier is the same defect as a screen
that could not run returning a clean result — the answer looks identical and is
worth less.
"""
from __future__ import annotations

from dataclasses import dataclass

from nm.domain.text import refuses_blank_text


@refuses_blank_text()
@dataclass(frozen=True)
class Read:
    """One structured model call, and whether being wrong changes a number."""

    key: str
    """The schema's `x-nm-read` value. THE EXACT KEY the adapter dispatches on."""

    decisive: bool
    why: str
    """Why it is decisive, or why it is not. Both are worth writing down: the
    second is what stops the list growing until every read is decisive and the
    distinction stops meaning anything."""

    echoes: bool = False
    """Does this answer CONTAIN the advocate's own words, in a quantity that
    follows how much they wrote? BK-29.

    NOT "does it quote". Nearly every read here quotes -- the quotation guard
    is how this product refuses invention. The question is whether the SIZE of
    the answer follows the size of the input, which is true of a read that
    returns a LIST of spans and false of one that returns a verdict plus one
    span.

    IT DECIDES THE TOKEN CEILING and nothing else. An echoing read gets a
    ceiling derived from what it was shown (`backend/nm/core/ceiling.py`); a fixed one
    gets a stated number. The dispute read was capped at 200, began returning
    three verbatim spans, and its JSON truncated mid-string at character 827 --
    so the read was LOST rather than short, and the turn fell back to one
    thread on the strength of a parse error.

    DECLARED HERE BECAUSE IT IS A FACT ABOUT WHAT WAS ASKED FOR, beside the
    schema's own entry rather than in the ceiling module. A table over there
    would be a second place to record a property of the read.
    """


#: EVERY read the product makes. `tests/test_reads_registry.py` fails the build
#: on a schema in `backend/nm/` that is not here, so a twelfth read cannot be added
#: without someone deciding which kind it is.
READS: tuple[Read, ...] = (
    Read("step_dependency", False,
         "Assesses whether the exact proposed step depends on an unresolved "
         "limitation position. Does not establish a date or law; unknown blocks "
         "the step while evidence gathering and the conversation remain available.", echoes=True),
    Read("investigation", False,
         "Proposes a judgment search over exact current source spans. It cannot "
         "settle a legal identifier, deadline, fact or permission; returned "
         "findings still cross the evidence and grounding boundaries.", echoes=True),
    # ---- decisive: the output IS a date, an amount, or which law is read ----
    Read("dates", True,
         "Every date on the chronology comes from here, and the accrual is one "
         "of them. A missed or misread date moves the limitation period and "
         "every deadline derived from it. THE CORRECTION RIDES IN THIS READ "
         "and is not a second one — `corrects` is a field on the date row, "
         "because the sentence that identifies a correction is the same "
         "sentence the date was read out of (B-086). It was listed here as a "
         "separate `correction` read for a day, naming a schema that does not "
         "exist, which is what this module’s own docstring claimed a test "
         "prevented; the test did not exist either.",
         echoes=True),
    Read("accrual", True,
         "It decides WHICH DATED EVENT THE PERIOD RUNS FROM, so its output is "
         "the accrual date itself and the expiry is arithmetic on top of it. "
         "There is no narrower way for a read to be decisive.\n\n"
         "THE DEFECT IT REPLACED IS THE ARGUMENT FOR THE TIER. `_limitation` "
         "took `next(f for f in chart if f.date is not None)` -- the earliest "
         "dated fact, whatever the cause -- so Article 54 ran from a 2023 "
         "agreement when its trigger is the date fixed for performance, or "
         "notice that performance is refused. The expiry was declared, the "
         "Article was right, the period was read from retrieved text, the "
         "arithmetic was right, and the answer was wrong by a year with "
         "nothing on the turn to show it. Only the starting point was chosen "
         "by sort order.\n\n"
         "ITS GUARD IS EXACT MEMBERSHIP AND NOTHING ELSE, which is unusual "
         "here and worth saying: the answer space is this thread's own fact "
         "ids, a closed set the turn generated, so CLAUDE.md §5 reaches "
         "its easiest case -- an exact key exists and nothing is ranked. An "
         "id not on the chart names nothing, and no reading of the prose "
         "would make it name something."),
    Read("duty", False,
         "It decides whether an instruction is REFUSED, and it is not "
         "decisive in this table’s narrow sense: it moves no date, no "
         "amount, and no question of which law is read. What it moves is "
         "whether the turn runs at all.\n\n"
         "AND IT FAILS TOWARD ANSWERING, which is the opposite of every "
         "decisive read here. A refusal wrongly issued accuses an advocate "
         "of misconduct for asking an ordinary question, and one issued "
         "because a read timed out cannot be argued with. So a read that "
         "produced no answer is NOT_ASSESSED, the gate says so, and the "
         "turn proceeds — the disclosure is the mechanism here, not the "
         "block."),
    Read("cause", True,
         "It decides WHICH ACT is looked up. CLAUDE.md §5 measures what a wrong "
         "one costs: an exact section lookup sent into the wrong statute, "
         "returning a confident period that governs a different suit."),
    Read("factors", True,
         "An acknowledgment under s.18 restarts the period. Missing it reports "
         "a live claim as dead (B-073); inventing one reports a dead claim as "
         "live.",
         echoes=True),
    Read("route", True,
         "It decides whether there is a MATTER AT ALL, and a turn "
         "routed to NON_MATTER writes nothing to any file -- so a read "
         "that answers with nothing does not produce a thin answer, it "
         "produces no file. That is decisive on the narrowest reading "
         "of the test: it moves no date and no amount, and it decides "
         "whether any of them are computed.\n\n"
         "IT REPLACED TWO KEYWORD LISTS AND TWO LENGTH RULES on 7 "
         "September 2026. \u2018bail\u2019 is one word and a case fact; "
         "\u2018hi\u2019 is one word and a greeting; a count cannot tell "
         "them apart. Every refusal lands on MATTER, which is the "
         "asymmetry the routing has recorded since it was written."),
    Read("posture", True,
         "Which side we are on. Nothing side-dependent can be computed without "
         "it, and a wrong one advises the opponent's case. Exact representation "
         "and opponent-correction quotations can grow with the supplied instructions.",
         echoes=True),
    Read("role", True,
         "The procedural role, which resolves the posture. Same consequence, "
         "one step earlier."),

    # ---- not decisive: being wrong makes the answer thinner, not false ------
    Read("consistency", False,
         "It judges a SENTENCE against numbers this turn already computed, "
         "and it moves neither. The date, the register and the side are all "
         "settled before it runs; what it decides is whether the step written "
         "beside them is served, rewritten once, or replaced by a question.\n\n"
         "AND IT FAILS TOWARD SERVING, which is why it is here rather than "
         "among the decisive reads. Every other guard in this product refuses "
         "toward silence because a wrong answer costs more than a gap. This "
         "one is the exception and the asymmetry is the reason: refusing here "
         "DELETES ADVICE THAT IS PROBABLY SOUND, and an advocate cannot tell "
         "a step that was suppressed from a step that was never written. So a "
         "read that cannot run, names a fact it was not shown, or cannot "
         "quote the words it objects to lands `consistent` — with the refusal "
         "recorded, so a read that keeps failing its own guards is visible "
         "rather than merely tolerated."),
    Read("parties", False,
         "WHO IS IN THE MATTER, for the conflict screen. It moves no "
         "date, no amount and no choice of law, so it is not decisive on "
         "this table's narrow test -- and it is the closest call in the "
         "list, because what it feeds is a SCREEN." + chr(10) + chr(10) +
         "It stays here because its wrongness is bounded in the safe "
         "direction BY A GUARD rather than by luck. Every name must be "
         "quoted from the advocate's own words, so the read cannot invent "
         "a party; a name it garbles is dropped, and dropping them all "
         "leaves the conflict screen NOT_ASSESSED, naming what it wants. "
         "A screen that ran against a party nobody mentioned and cleared "
         "would be the decisive failure, and the quotation guard is what "
         "makes it unreachable.",
         echoes=True),
    Read("dispute", False,
         "Whether a message opens a new thread. Wrong, it puts the right "
         "analysis on the wrong thread — visible to the advocate immediately, "
         "and correctable in a sentence.",
         echoes=True),
    Read("requirements", False,
         "Applicable needs extracted from retrieved passages; no tick or legal conclusion. "
         "Failed or partial reads preserve previous requirements and remain unassessed.",
         echoes=True),
    Read("issues", False,
         "A missed issue makes the answer thinner and the advocate can SEE it "
         "is thinner. It changes no number.",
         echoes=True),
    Read("proof", False,
         "What the file can establish, element by element. NOT DECISIVE on "
         "the narrow test this table applies -- it moves no date, no amount "
         "and no choice of law -- and the reason it is close is worth "
         "recording rather than leaving to be re-argued.\n\n"
         "An empty answer here is already visible without the gate. Every "
         "curated element gets a position whether or not the read mentioned "
         "it, so a read that answers nothing produces a full list of "
         "NOT_ASSESSED rather than a short list that looks complete, and "
         "`uncovered` draws its population from the ELEMENTS. The disclosure "
         "G-READ would add is the one the turn already makes.\n\n"
         "What it CAN cost is a gap the advocate does not go looking for, and "
         "that is D5.1's drift rather than an empty read: the answer arrives "
         "full and soft. The type refuses an OBTAINABLE with nothing named "
         "that would obtain it, which turns the soft answer into work.",
         echoes=True),
    Read("inventory", False,
         "What evidence is mentioned and who holds it. A missed item costs a "
         "preservation question; it moves no date.",
         echoes=True),
    Read("adverse", False,
         "Which facts hurt us. Feeds the theory's completeness check, which "
         "reports what is unaccounted rather than computing anything.",
         echoes=True),
    Read("theory", False,
         "The spine accounts for each supplied adverse fact, including unresolved "
         "facts and their reasons. Its output grows with that population; it is "
         "not a fixed-size verdict. A theory remains provisional, not a verified fact.",
         echoes=True),
    Read("attacks", False,
         "The opponent's case. A weak one is a preparation gap, not a false "
         "statement about the file.",
         echoes=True),
    Read("exposure", False,
         "Cross-thread contradiction. Reports a relationship; computes nothing.",
         echoes=True),
    Read("salvage", False,
         "Coordinate variation. Its routes are already bound to retrieved "
         "citations by the type, so the read cannot manufacture one.",
         echoes=True),
)

BY_KEY: dict[str, Read] = {r.key: r for r in READS}

#: A FUNCTION WRITTEN FOR FUTURE USE IS FUTURE USE. `decisive_keys()` and
#: `is_decisive()` were both here and neither had a caller — M2 caught them
#: within the hour. They belong with the tier escalation that will call them,
#: not ahead of it, so what this module offers today is the TABLE: a place
#: where a twelfth read cannot be added without someone deciding which kind
#: it is.


def echoes(key: str) -> bool:
    """Does this read's answer follow the size of what it was shown? BK-29.

    THE SAFE DIRECTION IS `False` FOR AN UNKNOWN READ, and it is safe for the
    unusual reason that it is the LOUD one: a fixed ceiling on a read that
    should have been derived truncates, and a truncated read is a parse error
    the call site sees. Defaulting the other way would give every unlisted
    read a ceiling scaled to the brief, which spends tokens quietly and
    forever.

    `tests/test_no_read_picks_its_own_ceiling.py` fails the build on a read
    the product makes that is not in `READS`, so `False` here is never
    reached by a read nobody declared.
    """
    entry = BY_KEY.get(key)
    return bool(entry and entry.echoes)


def is_decisive(key: str) -> bool:
    """Does being wrong about this read change a number the advocate acts on?

    THE ONE OWNER OF THAT QUESTION. It was asked in two places for a day --
    here, and a private `_decisive` in the traced model adapter -- which is
    S9 in miniature: a seventh decisive read would have been guarded by
    whichever copy someone remembered.

    It returns a BOOLEAN and not a tier, because a tier is a ports concept and
    this is a domain fact. `nm.domain` may not import `nm.ports`, and the
    layer check said so the minute this was written the other way -- correctly:
    the table decides what is decisive, and the caller decides what to do
    about it.

    A read not in the table is not decisive, which is the safe direction and
    is not a silent default: `tests/test_reads_registry.py` fails the build on
    a schema the product sends that is not declared here.
    """
    entry = BY_KEY.get(key)
    return bool(entry and entry.decisive)
