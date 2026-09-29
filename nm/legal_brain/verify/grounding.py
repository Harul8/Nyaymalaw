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

from nm.advise.answer_contracts import Answer, Element, ElementKind
from nm.legal_brain.common.citation_contracts import (
    cases_named,
    provisions_cited,
)
from nm.legal_brain.reason.matter_support import MatterDocumentSpan
from nm.legal_brain.retrieve.evidence_port import Finding
from nm.legal_brain.retrieve.source_excerpt import capture as capture_source
from nm.shared.gates_contracts import Response, gate
from nm.shared.text_contracts import fold, refuses_blank_text, snippet
from nm.shared.traceability_contracts import implements

# Quotation marks an advocate would read as a quotation: straight and curly
# doubles. Single quotes are excluded deliberately -- apostrophes in ordinary
# prose would make the check fire constantly, and a check that cries wolf is
# switched off, which is worse than not having it.
_QUOTED = re.compile(r'"([^"]{12,})"|“([^”]{12,})”')

# Text is compared on WORDS, not characters. The corpus stores hard-wrapped
# text with runs of whitespace and stray hyphenation, so a character-exact
# comparison would fail on formatting and teach everyone to disable the gate.
# THAT base fold is `nm.shared.text_contracts.fold` and this composes on it -- see the
# docstring below for what it adds and why that addition is not general.


def _citation_fold(text: str) -> str:
    """`text.fold`, PLUS the case-name pivot. A citation fold, not a text one.

    THE ADDITION IS ABOUT CITATIONS, NOT ABOUT TEXT, which is why it lives
    here and not in `nm.shared.text_contracts`. Folding `vs` to `v` is right for a case
    name and wrong for an advocate's sentence: "the notice vs the reply" is
    not "the notice v the reply", and a fold that erased the difference would
    quietly merge two facts on the chronology.

    `vs` and `v` ARE THE SAME WORD and folding them apart withheld a correct
    turn: a retrieved authority whose `ref` reads "K. Venkata Rao And Ors. vs
    Sunkara Venkata Ra" failed to match the same case written "... v Sunkara
    Venkata Ra" in the answer, so the gate reported an invented citation for a
    judgment it had itself just supplied.

    A gate that fires on its own retrieval is worse than no gate: it withholds
    good work, and the fix people reach for is to switch it off.
    """
    return " ".join("v" if t in ("vs", "versus") else t
                    for t in fold(text).split())


@refuses_blank_text()
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
                  findings: tuple[Finding, ...], *,
                  document_spans: tuple[MatterDocumentSpan, ...] = (),
                  own_words: tuple[str, ...] = ()) -> list[GroundingViolation]:
    """G-QUOTE. Every quotation must be findable, verbatim, in a retrieved span
    -- or in the advocate's own words.

    A quotation that matches NOTHING retrieved on this turn is treated as
    fabricated even if it happens to be accurate, because accuracy that cannot
    be demonstrated is indistinguishable from luck.

    THE ADVOCATE'S OWN WORDS ARE A SOURCE TOO (28 September 2026). A polite
    check that quotes back what they said (LB-81) was withheld as a fabricated
    quotation: the words were verbatim, just not from the corpus. `own_words`
    is their message and their statements on the file, which C1 keeps
    verbatim; quoting them is quoting, and nothing else is admitted by it.
    """
    corpus = [_citation_fold(f.span) for f in findings]
    for span in document_spans:
        if not isinstance(span, MatterDocumentSpan):
            raise ValueError("Document quotation support needs an exact typed captured window")
        span.validate()
        corpus.append(_citation_fold(span.text))
    corpus.extend(_citation_fold(words) for words in own_words if words)
    out: list[GroundingViolation] = []
    for element in elements:
        for quote in quoted_spans(element.text):
            folded = _citation_fold(quote)
            if not folded:
                continue
            if not any(folded in span for span in corpus):
                out.append(GroundingViolation(
                    "G-QUOTE",
                    f"quoted text is not verbatim in any retrieved span or in the "
                    f"advocate's own words: {snippet(quote, 120)!r}"))
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
# separately -- see nm/legal_brain/common/citation_contracts.py for what that cost.
__all__ = ["verify", "verify_reply", "verify_citations", "verify_quotes", "verify_findings",
           "unretrieved_authorities",
           "quoted_spans", "provisions_cited", "cases_named",
           "GroundingReport", "GroundingViolation"]


def _covered_provisions(findings: tuple[Finding, ...]) -> set[str]:
    """Every provision number traceable to something retrieved this turn.

    THE SPAN COUNTS, and leaving it out was wrong. A retrieved judgment that
    discusses s.53 in its own words makes s.53 *traceable to retrieved primary
    text* — which is exactly the promise. Reading only the ref withheld turns
    that quoted the retrieved authority accurately.

    It does widen what passes: a long span naming many sections covers all of
    them. That is the correct trade — the alternative refuses answers that are
    grounded, and a gate whose false positives outnumber its catches is one
    nobody leaves on.
    """
    covered: set[str] = set()
    for f in findings:
        # The proposition is the question/claim being assessed. Counting it
        # would let a requested but never retrieved citation certify itself.
        for text in (f.ref, f.locator, f.span):
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
    out: list[GroundingViolation] = []

    for element in elements:
        if element.disclosure:
            # Naming what could not be retrieved is not citing it. See
            # `Element.disclosure` -- the distinction is a field precisely so
            # this exception cannot be reached by phrasing.
            continue
        for kind, name in unretrieved_authorities(element.text, findings):
            if kind == "provision":
                out.append(GroundingViolation(
                    "G-GROUND",
                    f"the answer cites provision {name!r}, which was not "
                    f"retrieved on this turn. Retrieved: "
                    f"{sorted(covered) or 'nothing'}"))
            else:
                out.append(GroundingViolation(
                    "G-GROUND",
                    f"the answer names the case {name!r}, which was not "
                    f"retrieved on this turn"))
    return out


def unretrieved_authorities(text: str, findings: tuple[Finding, ...]
                            ) -> tuple[tuple[str, str], ...]:
    """Every provision or case named in `text` that no finding covers.

    G-GROUND's OWN TEST, CALLABLE ON ONE STRING. `verify_citations` asks it of
    every element of the assembled answer; a READ asks it of its own items
    before they are assembled, so it can drop the one item that names a
    remembered authority instead of letting that item withhold the whole turn.

    ONE DETECTOR, because two would disagree. CLAUDE.md section 4 records the
    grounding gate and the evidence adapter each holding a provision pattern,
    one hardened and one not, and a useless answer living in the gap between
    them. A read-level filter with its own notion of "names a case" would be
    that defect again: an item it kept could still be one the gate withholds.

    Returns `("provision", number)` and `("case", name)` pairs, in the order
    the gate reports them.
    """
    covered = _covered_provisions(findings)
    known_cases = {_citation_fold(f.ref) for f in findings}
    out: list[tuple[str, str]] = []
    for number in provisions_cited(text):
        if number not in covered:
            out.append(("provision", number))
    for case in cases_named(text):
        folded = _citation_fold(case)
        if not any(folded in ref for ref in known_cases):
            out.append(("case", case))
    return tuple(out)


@implements("P1")
def verify(answer: Answer, relied_on: tuple[Finding, ...],
           retrieved: tuple[Finding, ...] = (), *,
           independent_packages=(), independent_records=(),
           retrieved_documents=(), own_words: tuple[str, ...] = ()) -> GroundingReport:
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
    certified, uncovered_claim = _independently_supported(
        answer, pool, independent_packages, independent_records, retrieved_documents)
    document_spans = tuple(span for package in independent_packages
                           for span in (*package.documents, *package.document_contrary)
                           if span.captured_quote in retrieved_documents)
    report.violations.extend(verify_quotes(answer.elements, quotable,
                                          document_spans=document_spans,
                                          own_words=own_words))
    report.violations.extend(verify_citations(answer.elements, quotable))
    if uncovered_claim is not None:
        report.violations.append(GroundingViolation("G-GROUND", uncovered_claim))
    # A new independent proof is about this exact released claim, not a
    # rewriting of the earlier candidate's semantic status. Known negative
    # support is never waived, and source/time/authority constraints remain.
    for finding in relied_on:
        if finding.supports is None and finding in certified:
            reason = finding.source_blocking_reason
            if reason:
                gate_id = reason.split(":", 1)[0].strip()
                gate(gate_id)
                report.violations.append(GroundingViolation(gate_id, reason))
        else:
            report.violations.extend(verify_findings((finding,)))
    # Drawer text is published content too. A correct digest proves identity,
    # not retrieval: require the exact captured Finding, including its namespace.
    captured = tuple(capture_source(f) for f in quotable)
    for element in answer.elements:
        if element.source is not None and element.source not in captured:
            report.violations.append(GroundingViolation(
                "G-GROUND", "the saved source excerpt was not retrieved on this turn"))
    return report


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}
_TENS = ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_PERIOD = re.compile(
    r"\b(\d{1,4}|(?:(?:" + "|".join(_TENS) + r")[\s-]+)?(?:" + "|".join(_NUMBER_WORDS)
    + r"))[\s-]+(year|month|week|day)s?\b", re.I)


def periods_stated(text: str) -> frozenset[tuple[int, str]]:
    """EVERY SPAN OF TIME A TEXT STATES, as (number, unit): "twelve years", "12
    years", "a three-year period" and "30-day notice" all read the same way.

    Used for one rule: a period the reply states must be one a retrieved
    passage, the checked work or the advocate states. It decides nothing else.
    """
    found = set()
    for number, unit in _PERIOD.findall(text or ""):
        words = number.lower().replace("-", " ").split()
        if words and words[0].isdigit():
            value = int(words[0])
        else:
            value = sum(_NUMBER_WORDS.get(w, 0) for w in words)
        if value:
            found.add((value, unit.lower()))
    return frozenset(found)


def verify_periods(elements: tuple[Element, ...], sources: tuple[str, ...]
                   ) -> list[GroundingViolation]:
    """A PERIOD NOBODY STATED IS LAW FROM MEMORY (owner, 29 September 2026).

    Measured on the Farah Begum matter: with no passage retrieved, the reply said
    "a three-year period for property-related disputes" and "a six-month
    limitation" for an assault. Neither sentence cites a provision, so the
    citation check could not see them, and both were wrong. A limitation period,
    a notice period or a deadline is the law's own number: the reply may state
    one only where a retrieved passage, the checked work or the advocate's own
    words state it.
    """
    allowed: set[tuple[int, str]] = set()
    for text in sources:
        allowed |= periods_stated(text)
    out = []
    for element in elements:
        for value, unit in sorted(periods_stated(element.text) - allowed):
            out.append(GroundingViolation(
                "G-GROUND",
                f"the reply states a period of {value} {unit}(s) that no retrieved "
                "passage, checked finding or statement of the advocate states"))
    return out


@implements("P1")
def verify_reply(answer: Answer, relied_on: tuple[Finding, ...],
                 retrieved: tuple[Finding, ...] = (), *,
                 own_words: tuple[str, ...] = ()) -> GroundingReport:
    """THE SAME GATE, ON THE WORDS THE ADVOCATE READS. LB-76.

    `verify` checks the turn's working findings. When a composer retells them
    (`nm.legal_brain.communicate.compose`), the retelling is new text, and a
    check on the findings has checked a different string -- the gap this module's
    docstring was written about. So every composed paragraph is checked here as
    an asserting element, with the SAME detectors: each quotation verbatim in a
    retrieved span or in the advocate's own words, each provision and case named
    covered by what was retrieved, and each linked passage the exact captured
    source. A composed paragraph never carries `disclosure`, so it cannot name an
    unretrieved provision under a limit's licence. And every PERIOD it states
    must be one a retrieved passage, a checked finding or the advocate states
    (`verify_periods`): a limitation period written from memory names no section
    for the citation check to see.

    A paragraph that CARRIES an element is that element's checked words -- the
    type refuses anything else -- and was checked by `verify` as that element.

    `own_words` are the advocate's message and statements on the file: quoting
    them back is quoting, and they are the words C1 keeps verbatim.
    """
    pool = retrieved or relied_on
    quotable = tuple(f for f in pool if f.quotable)
    shown: list[Element] = []
    for paragraph in answer.composed:
        if paragraph.carries is not None:
            continue
        linked = answer.elements[paragraph.passage] if paragraph.passage is not None else None
        shown.append(Element(kind=ElementKind.FINDING, text=paragraph.text,
                             refs=linked.refs if linked is not None else (),
                             source=linked.source if linked is not None else None))
    report = GroundingReport(checked_elements=len(shown))
    report.checked_quotes = sum(len(quoted_spans(e.text)) for e in shown)
    report.violations.extend(verify_quotes(tuple(shown), quotable, own_words=own_words))
    report.violations.extend(verify_citations(tuple(shown), quotable))
    report.violations.extend(verify_periods(tuple(shown), (
        *(f.span for f in quotable), *own_words, *(e.text for e in answer.elements))))
    captured = tuple(capture_source(f) for f in quotable)
    for element in shown:
        if element.source is not None and element.source not in captured:
            report.violations.append(GroundingViolation(
                "G-GROUND", "the reply links a saved excerpt that was not retrieved on this turn"))
    return report


def _independently_supported(answer, retrieved, packages, records, documents=()):
    """No source-ID whitelist: exact visible claim AND exact proof are needed."""
    if not packages or not records:
        return ((), "The independent final-claim receipt population is incomplete"
                if packages or records else None)
    # Local import avoids a module cycle; the verifier itself calls the existing
    # quotation/citation checks before it can produce an independent record.
    from nm.legal_brain.verify.verifier import EvidencePackage, VerificationRecord, release_verified

    if any(not isinstance(row, EvidencePackage) for row in packages) or any(
            not isinstance(row, VerificationRecord) for row in records):
        raise ValueError("Independent grounding needs typed claim verification receipts")
    released = release_verified(tuple(packages), tuple(records)).released
    eligible = tuple(package for package in released if all(
        span.finding in retrieved and span.finding.supports is not False
        and not span.finding.source_blocking_reason
        for span in (*package.spans, *package.contrary)) and all(
            span.captured_quote in documents
            for span in (*package.documents, *package.document_contrary)))
    # The visible answer is the subject, not the author's labels or refs. An
    # extra unreferenced sentence or a sentence marked "disclosure" cannot
    # piggyback on one correctly verified claim. Genuine engine disclosures
    # are appended after this exact package boundary, not disguised as claims.
    matched = []
    for element in answer.elements:
        exact = tuple(package for package in eligible if element.text == package.claim
                      and ({span.finding.locator for span in package.spans}
                           | {span.locator for span in package.documents}) <= set(element.refs)
                      and set(element.refs) <= (
                          {span.finding.locator for span in (*package.spans, *package.contrary)}
                          | {span.locator for span in (*package.documents,
                                                      *package.document_contrary)}))
        if not exact:
            return (), "The visible answer contains a claim without an exact independent receipt"
        matched.append((element, exact))
    certified = []
    for finding in retrieved:
        subjects = tuple(exact for element, exact in matched
                         if finding.locator in element.refs)
        if not subjects:
            continue
        if all(any(any(
                span.finding == finding for span in package.spans)
                   for package in exact) for exact in subjects):
            certified.append(finding)
    return tuple(certified), None
