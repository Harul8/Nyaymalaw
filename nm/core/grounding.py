"""THE GROUNDING GATE. Slice 2's whole promise, in one pure module.

    Nothing reaches the advocate that is not traceable to retrieved primary
    text.

WHY IT RUNS ON THE ASSEMBLED ANSWER AND NOT ON THE MODEL OUTPUT
----------------------------------------------------------------
Checking the model's reply as it comes back checks a string that may still be
edited, reordered, truncated or merged with another element before it is
emitted. Every defect the first external review of the previous build found
lived in exactly that gap -- between a correct check and the served bytes.

So this runs LAST, on the `Answer` object, immediately before the byte
boundary, and it is given the findings that were actually retrieved on this
turn. If a sentence cannot be traced to one of them, the turn is withheld.

THE FOUR CHECKS, AND THE DEFECT EACH REFUSES
---------------------------------------------
G-GROUND  Every provision number and every case name in the emitted text must
   (a)    be covered by something RETRIEVED ON THIS TURN.
          Defect: "section 27 of the Limitation Act" -- fluent, correctly
          formatted, never retrieved, and not what that section says. This is
          the check that bites; the three below are narrower.

G-QUOTE   A quoted string must appear VERBATIM in a retrieved span.
          Defect: the model paraphrases a section and puts the paraphrase in
          quotation marks. Every word plausible, the quotation invented. This
          is the one an advocate will read out in court.

G-GROUND  Every Finding carried into the answer must be usable -- its span
   (b)
          supports its proposition, its treatment was checked, its text was in
          force on the governing date.
          Defect: a case overruled in 2011 cited as good law, because the
          citator was silent and silence was read as clearance.

G-ATTRIB  A proposition attributed to a judgment must come from a ratio,
          reasoning or order paragraph.
          Defect: counsel's losing submission -- 14.8% of the case corpus --
          quoted as the court's holding. It is enforced in the `Finding`
          constructor as well, because a check that exists only at the edge is
          a check that a new call site bypasses.

WITHHOLD, NOT SOFTEN
--------------------
Every violation here maps to a gate whose response is WITHHOLD. That is the
whole of "fail closed on grounding": the advocate gets nothing and is told the
turn was withheld and why. They never get the answer with a caveat attached,
because a caveat is read as a hedge and acted on anyway.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from nm.domain.answer import Answer, Element
from nm.domain.citation import (
    cases_named,
    provisions_cited,
)
from nm.domain.gates import Response, gate
from nm.domain.traceability import implements
from nm.ports.evidence import Finding

# Quotation marks an advocate would read as a quotation: straight and curly
# doubles. Single quotes are excluded deliberately -- apostrophes in ordinary
# prose would make the check fire constantly, and a check that cries wolf is
# switched off, which is worse than not having it.
_QUOTED = re.compile(r'"([^"]{12,})"|“([^”]{12,})”')

# Text is compared on WORDS, not characters. The corpus stores hard-wrapped
# text with runs of whitespace and stray hyphenation, so a character-exact
# comparison would fail on formatting and teach everyone to disable the gate.
_WORDS = re.compile(r"[a-z0-9]+")

def _fold(text: str) -> str:
    return " ".join(_WORDS.findall((text or "").lower()))


@dataclass(frozen=True)
class GroundingViolation:
    gate_id: str
    detail: str

    @property
    def withholds(self) -> bool:
        return gate(self.gate_id).response is Response.WITHHOLD


@dataclass
class GroundingReport:
    checked_elements: int = 0
    checked_quotes: int = 0
    checked_findings: int = 0
    violations: list[GroundingViolation] = field(default_factory=list)

    @property
    def clear(self) -> bool:
        return not self.violations

    @property
    def withholding(self) -> list[GroundingViolation]:
        return [v for v in self.violations if v.withholds]

    def as_dict(self) -> dict:
        return {
            "elements": self.checked_elements,
            "quotes": self.checked_quotes,
            "findings": self.checked_findings,
            "violations": [{"gate": v.gate_id, "detail": v.detail}
                           for v in self.violations],
        }


def quoted_spans(text: str) -> list[str]:
    """Every quotation in a piece of emitted text."""
    return [a or b for a, b in _QUOTED.findall(text or "")]


@implements("P1")
def verify_quotes(elements: tuple[Element, ...],
                  findings: tuple[Finding, ...]) -> list[GroundingViolation]:
    """G-QUOTE. Every quotation must be findable, verbatim, in a retrieved span.

    A quotation that matches NOTHING retrieved on this turn is treated as
    fabricated even if it happens to be accurate, because accuracy that cannot
    be demonstrated is indistinguishable from luck.
    """
    corpus = [_fold(f.span) for f in findings]
    out: list[GroundingViolation] = []
    for element in elements:
        for quote in quoted_spans(element.text):
            folded = _fold(quote)
            if not folded:
                continue
            if not any(folded in span for span in corpus):
                out.append(GroundingViolation(
                    "G-QUOTE",
                    f"quoted text is not verbatim in any retrieved span: "
                    f"{quote[:120]!r}"))
    return out


@implements("P1")
def verify_findings(findings: tuple[Finding, ...]) -> list[GroundingViolation]:
    """G-GROUND / G-ATTRIB / G-BINDING / G-DATE, read off each Finding.

    The Finding knows why it cannot be used; this maps that reason onto the
    gate that owns it, so the response class is decided by the matrix rather
    than here.
    """
    out: list[GroundingViolation] = []
    for f in findings:
        reason = f.blocking_reason
        if reason is None:
            continue
        gate_id = reason.split(":", 1)[0].strip()
        try:
            gate(gate_id)
        except KeyError:
            gate_id = "G-GROUND"
        out.append(GroundingViolation(gate_id, reason))
    return out


# `provisions_cited` and `cases_named` are imported, NOT defined here. They
# used to be defined here, and the copy in the evidence adapter was hardened
# separately -- see nm/domain/citation.py for what that cost.
__all__ = ["verify", "verify_citations", "verify_quotes", "verify_findings",
           "quoted_spans", "provisions_cited", "cases_named",
           "GroundingReport", "GroundingViolation"]


def _covered_provisions(findings: tuple[Finding, ...]) -> set[str]:
    covered: set[str] = set()
    for f in findings:
        for text in (f.ref, f.proposition, f.locator):
            covered |= provisions_cited(text)
            # `Article_65` and `::6::` do not match the prose patterns, so the
            # locator's own conventions are read as well. A locator format the
            # checker cannot parse would silently uncover every citation.
            covered |= {m.upper() for m in re.findall(r"Article[_ ](\d+[A-Za-z]{0,2})",
                                                      text or "", re.I)}
            covered |= {m.upper() for m in re.findall(r"::(\d+[A-Za-z]{0,2})::",
                                                      text or "")}
    return covered


@implements("P1")
def verify_citations(elements: tuple[Element, ...],
                     findings: tuple[Finding, ...]) -> list[GroundingViolation]:
    """G-GROUND. THE CHECK THAT ACTUALLY BITES.

    A provision or a case named in the answer that was not retrieved on this
    turn is treated as fabricated. Not ranked lower, not caveated -- the turn
    is withheld.

    This is the one an advocate would otherwise carry into court: fluent,
    correctly formatted, and pointing at a section that does not say what the
    sentence claims, or a case that does not exist.
    """
    covered = _covered_provisions(findings)
    known_cases = {_fold(f.ref) for f in findings}
    out: list[GroundingViolation] = []

    for element in elements:
        if element.disclosure:
            # Naming what could not be retrieved is not citing it. See
            # `Element.disclosure` -- the distinction is a field precisely so
            # this exception cannot be reached by phrasing.
            continue
        for number in provisions_cited(element.text):
            if number not in covered:
                out.append(GroundingViolation(
                    "G-GROUND",
                    f"the answer cites provision {number!r}, which was not "
                    f"retrieved on this turn. Retrieved: "
                    f"{sorted(covered) or 'nothing'}"))
        for case in cases_named(element.text):
            folded = _fold(case)
            if not any(folded in ref for ref in known_cases):
                out.append(GroundingViolation(
                    "G-GROUND",
                    f"the answer names the case {case!r}, which was not "
                    f"retrieved on this turn"))
    return out


@implements("P1")
def verify(answer: Answer, relied_on: tuple[Finding, ...],
           retrieved: tuple[Finding, ...] = ()) -> GroundingReport:
    """The gate, run on the assembled answer immediately before emission.

    The two arguments are NOT the same set, and conflating them breaks the
    check in one direction or the other:

      `relied_on`  the Findings the answer actually rests on. Only these gate
                   the turn -- an unusable Finding that was DROPPED and
                   disclosed has not misled anyone, and withholding on it would
                   punish the product for being honest.
      `retrieved`  everything that came back this turn. Quotations are checked
                   against these, because a Finding may be quotable with its
                   status disclosed while being unable to carry a proposition
                   alone -- an authority whose treatment was never checked is
                   exactly that.
    """
    pool = retrieved or relied_on
    quotable = tuple(f for f in pool if f.quotable)
    report = GroundingReport(
        checked_elements=len(answer.elements),
        checked_findings=len(relied_on),
    )
    report.checked_quotes = sum(len(quoted_spans(e.text)) for e in answer.elements)
    report.violations.extend(verify_quotes(answer.elements, quotable))
    report.violations.extend(verify_citations(answer.elements, quotable))
    report.violations.extend(verify_findings(relied_on))
    return report
