"""The legal graph. RESOLUTION BEFORE SEARCH — PRD §4.2, control H3.

WHAT THIS REPLACES, AND WHY IT IS THE WHOLE OF SLICE 5
-------------------------------------------------------
`Manifest.resolve` picks an Act by exact title or, failing that, by keyword,
and its own docstring says what it is: *"the resolution layer at its thinnest;
the cause-of-action graph that replaces it is slice 5."*

The size of that gap was measured on 31 August 2026, not estimated. Five golden
scenarios, twenty-three served turns, and the limitation position was
NOT_COMPUTED on every single one, because no Article was ever retrieved. The
sharpest instance is GS-14 turn 3 — the advocate asks *"is the claim still in
time"* and the product answers *"no Act in the curated manifest governs this
question"*. The Limitation Act is held in full. Its keywords are `limitation`,
`time-barred`, `acknowledgment`. The advocate's words contained none of them
(B-065).

The wrong fix is to add `in time`, `still in time` and `barred` to the keyword
list. This project has already paid for that once: ten exact phrases meant *"we
act for the workman"*, and an advocate whose phrasing was missing from the list
was asked the same question forever. Lengthening a phrase list is the patch
that cannot be repaired by lengthening it.

The right fix is that *"what is the limitation for a suit on an unpaid
invoice"* is a DETERMINATE question. It has one answer, the answer does not
depend on how it was phrased, and it should be a LOOKUP.

EXACT MATCH DECIDES; FUZZY MAY ONLY RANK
-----------------------------------------
CLAUDE.md §5 is measured, and the numbers are not close: matching case NAMES
reached 0.83% of held judgments, matching reporter CITATIONS — an exact key —
reached 90.9%. Exact matching did not merely avoid wrong answers, it beat fuzzy
a hundredfold at the one job where both were measured.

So every edge here is an exact lookup on a closed vocabulary. Nothing in this
module scores, ranks, or compares strings for similarity. A cause this graph
does not hold resolves to NOTHING and says so, which sends the question to
search — carrying its own confidence, as a candidate — rather than to a
plausible neighbour.

AN EDGE IS A ROUTE, NOT A HOLDING
----------------------------------
`Edge` says WHICH Article to read. It does not say what the Article provides,
and it carries no period. The period is read from the retrieved text by
`nm.core.limitation.period_in`, which refuses one the span does not state.

That division is deliberate and it is what makes a wrong edge survivable. A
mis-routed cause retrieves the wrong Article, and the advocate sees the Article
name, its retrieved text and the note saying what the routing inferred from —
so they can correct it in four words. A graph that also asserted the period
would produce a confident number with no text behind it, which is B-057 again.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from nm.domain.matter import CauseOfAction
from nm.domain.text import refuses_blank_text
from nm.domain.traceability import implements


@refuses_blank_text()
@dataclass(frozen=True)
class Edge:
    """One curated route: a cause of action to the provision that governs it.

    `curated_from` IS REQUIRED BY THE TYPE. It is the same rule
    `nm.core.limitation.Factor.finding` and `Period.read_from` apply — a legal
    routing decision that cannot say where it came from is one somebody
    remembered, and this file is exactly where remembering would be invisible.

    The decorator is `nm.domain.text.refuses_blank_text` and not a loop written
    here. The first draft of this class DID write the loop, and the M1 sweep
    caught it on its first run — a second copy of "a value that is present and
    carries nothing is absent", which is the rule that already had three
    separate ad-hoc implementations before it was given one owner.
    """

    cause: CauseOfAction
    act: str
    provision: str
    """The corpus's own key: `Article_14`, `65`, `138`. Not prose.

    `nm/domain/citation.py` renders Schedule Articles as `Article_N` and the
    chunk store's `section_number` column holds that form, so an edge that
    wrote "Article 14" would look up nothing and report a corpus gap for a
    provision held in full."""
    curated_from: str
    alternatives: tuple[str, ...] = ()
    """Other provisions that plausibly govern this cause.

    NAMED IN THE DISCLOSURE, so a wrong route is visible at a glance rather
    than discovered after the advocate has acted on it. The same arrangement
    `Resolution.alternatives` already uses for Acts, and for the same reason:
    the correction handle matters more than the guess."""



#: Cause of action to the Limitation Article. TASK T-052.
#:
#: "The single highest-value edge. Turns the Article from a ranking into a
#: lookup. This is real curation work and is the asset that makes the product
#: hard to copy."
#:
#: Curated conservatively. A cause whose Article is genuinely arguable is left
#: OUT rather than guessed: an absent edge falls through to search, which is a
#: worse answer and an honest one, while a wrong edge is a confident answer
#: and there is nothing downstream that catches it.
LIMITATION_ARTICLE: dict[CauseOfAction, Edge] = {
    CauseOfAction.GOODS_SOLD_PRICE: Edge(
        cause=CauseOfAction.GOODS_SOLD_PRICE,
        act="Limitation Act, 1963", provision="Article_14",
        curated_from="Limitation Act, 1963, Schedule I, Part II — suits for "
                     "the price of goods sold and delivered where no fixed "
                     "period of credit was agreed",
        alternatives=("Article_15 where a fixed period of credit was agreed",
                      "Article_113 if the cause is not on the price itself")),
    CauseOfAction.MONEY_LENT: Edge(
        cause=CauseOfAction.MONEY_LENT,
        act="Limitation Act, 1963", provision="Article_19",
        curated_from="Limitation Act, 1963, Schedule I — money payable for "
                     "money lent",
        alternatives=("Article_21 where the loan is on a promissory note "
                      "payable on demand",)),
    CauseOfAction.BREACH_OF_CONTRACT: Edge(
        cause=CauseOfAction.BREACH_OF_CONTRACT,
        act="Limitation Act, 1963", provision="Article_55",
        curated_from="Limitation Act, 1963, Schedule I — compensation for "
                     "breach of a contract",
        alternatives=("Article_113 as the residuary article",)),
    CauseOfAction.SPECIFIC_PERFORMANCE: Edge(
        cause=CauseOfAction.SPECIFIC_PERFORMANCE,
        act="Limitation Act, 1963", provision="Article_54",
        curated_from="Limitation Act, 1963, Schedule I — specific performance "
                     "of a contract",
        alternatives=()),
    CauseOfAction.POSSESSION_ON_TITLE: Edge(
        cause=CauseOfAction.POSSESSION_ON_TITLE,
        act="Limitation Act, 1963", provision="Article_65",
        curated_from="Limitation Act, 1963, Schedule I — possession of "
                     "immovable property based on title",
        alternatives=("Article_64 where the suit rests on previous possession "
                      "rather than title",)),
    CauseOfAction.POSSESSION_ON_PREVIOUS_POSSESSION: Edge(
        cause=CauseOfAction.POSSESSION_ON_PREVIOUS_POSSESSION,
        act="Limitation Act, 1963", provision="Article_64",
        curated_from="Limitation Act, 1963, Schedule I — possession based on "
                     "previous possession and not on title",
        alternatives=("Specific Relief Act, 1963 s.6, which runs six months "
                      "and asks no question of title",)),
    CauseOfAction.DECLARATION: Edge(
        cause=CauseOfAction.DECLARATION,
        act="Limitation Act, 1963", provision="Article_58",
        curated_from="Limitation Act, 1963, Schedule I — to obtain any other "
                     "declaration",
        alternatives=("Article_56 and Article_57 for the specific "
                      "declarations they name",)),
}


@implements("D4")
def article_for(cause: CauseOfAction) -> Edge | None:
    """The Limitation Article for a cause. EXACT, or `None`.

    `None` is not failure and must not be treated as one: a cause this graph
    does not hold falls through to search, which answers with a confidence and
    as a candidate. Returning a near neighbour instead would be the wrong Act
    problem one level down, and nothing downstream would catch it.
    """
    if cause is CauseOfAction.NOT_ESTABLISHED:
        return None
    return LIMITATION_ARTICLE.get(cause)


# ------------------------------------------------- the 2024 code transition ---

#: When the new codes came into force. TASK T-051, control D3B.
TRANSITION = date(2024, 7, 1)


@refuses_blank_text()
@dataclass(frozen=True)
class Correspondence:
    """One provision under the old code and the same subject under the new.

    NOT AN EQUIVALENCE, and the field is named `corresponds_to` rather than
    `equals` for that reason. The provisions are not identical and saying they
    are would be a legal assertion this graph is not entitled to make. What it
    asserts is narrower and checkable: authority decided under the old number
    is authority a court will read on the new one, so a search for the new
    number that ignores the old retrieves almost nothing.
    """

    old_act: str
    old_provision: str
    new_act: str
    new_provision: str
    subject: str
    curated_from: str


#: TASK T-051. "Case law is overwhelmingly pre-2024 and cites the old
#: numbering, so a system searching only the new number retrieves almost
#: nothing. Verified pairs exist: s.57/s.58, s.438/s.482, IPC 447/BNS 329."
#:
#: These three are the ones the plan names as verified. The list is short and
#: honest: an unverified pair would send an advocate to authority on a
#: different subject, which is worse than retrieving nothing.
CORRESPONDS: tuple[Correspondence, ...] = (
    Correspondence(
        old_act="Code of Criminal Procedure, 1973", old_provision="57",
        new_act="Bharatiya Nagarik Suraksha Sanhita, 2023", new_provision="58",
        subject="the twenty-four hour limit on detention without a "
                "magistrate's authority",
        curated_from="named as a verified pair in the project plan, T-051"),
    Correspondence(
        old_act="Code of Criminal Procedure, 1973", old_provision="438",
        new_act="Bharatiya Nagarik Suraksha Sanhita, 2023", new_provision="482",
        subject="direction for release on bail in anticipation of arrest",
        curated_from="named as a verified pair in the project plan, T-051"),
    Correspondence(
        old_act="Indian Penal Code, 1860", old_provision="447",
        new_act="Bharatiya Nyaya Sanhita, 2023", new_provision="329",
        subject="criminal trespass",
        curated_from="named as a verified pair in the project plan, T-051"),
)


#: Every code title this graph holds a correspondence for, both sides.
#:
#: Derived from `CORRESPONDS` rather than retyped beside it. A second list
#: would go stale the first time a pair was added, and the failure would be
#: silent: the new pair would simply never be consulted.
CODE_TITLES: tuple[str, ...] = tuple(dict.fromkeys(
    [c.old_act for c in CORRESPONDS] + [c.new_act for c in CORRESPONDS]))


@implements("D4")
def corresponding(act: str, provision: str) -> Correspondence | None:
    """The same subject under the other code, in EITHER direction.

    Both directions are needed and for different reasons. New to old is the one
    the plan names — a charge under BNS s.329 whose authority all cites IPC
    s.447, so searching only the new number finds nothing. Old to new matters
    on the advice side: conduct in 2023 is governed by the IPC and the advocate
    still has to file under the BNSS today.

    Exact on the pair, never on the number alone. `s.447` means different
    things in different codes, and a lookup that matched on the digits would be
    the wrong-Act defect with a new face.
    """
    key = (act.strip(), str(provision).strip())
    for c in CORRESPONDS:
        if (c.old_act, c.old_provision) == key:
            return c
        if (c.new_act, c.new_provision) == key:
            return c
    return None


@implements("D4")
def governs(on: date) -> str:
    """Which body of criminal law governs conduct on a date. THE ERA RULE.

    *The governing date is the date of the CONDUCT*, never the date of the
    advice — which is the whole of GS-16 and the reason `EvidenceNeed` refuses
    a query with no governing date (H2).

    Returned as a label rather than a boolean because "old" and "new" is a
    distinction the advocate reads, and a boolean at a call site would have to
    be re-explained at every one of them.
    """
    return "the 2023 codes" if on >= TRANSITION else "the 1860/1898/1973 codes"
