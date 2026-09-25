"""The turn. PRD §7.3 -- three phases, two hard boundaries.

Nearly every defect that reached a live session in the previous build lived
HERE: not in a component, but in the seams between them. A duty screen that ran
after the advice it guards had been shown. A streamed turn that wrote its whole
opinion and then died. Forty of forty offline tests passing while every served
turn crashed.

    ADMIT   authenticate, route, take facts, run the gating screens
      |     ---- THE SCREEN BOUNDARY ----
    DERIVE  recompute, request evidence, assemble, assert invariants
      |     ---- THE BYTE BOUNDARY ----
    EMIT    commit, THEN release bytes

COMMIT PRECEDES EMIT, and that ordering is the opposite of the intuitive one.
It is deliberate: the advocate must never receive advice that the file does not
record. Better to fail before showing than to show and fail to save.

This module is PURE. It takes ports in and returns a result; it opens nothing.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timezone
from typing import Callable

from nm.core import accrual as accrual_reader
from nm.core import (
    adversarial,
    cascade,
    ceiling,
    chronology,
    consistency,
    deadlines,
    dependency,
    dispute_agenda,
    grounding,
    investigation,
    limitation,
    proof,
    proof_read,
    requirements,
    step_dependency,
    thresholds,
)
from nm.core import briefing as briefing_mod
from nm.core import cause as cause_reader
from nm.core import dispute as dispute_reader
from nm.core import duty as duty_reader
from nm.core import evidence_item as inventory
from nm.core import factors as factor_reader
from nm.core import gaps as gap_queue
from nm.core import issues as issue_reader
from nm.core import posture as posture_reader
from nm.core import (
    premise as premise_mod,
)
from nm.core import relief as relief_mod
from nm.core import route as route_reader
from nm.core import screens as screens_mod
from nm.core import theory as theory_reader
from nm.core.conversation import guided, with_evidence
from nm.core.professional_access import read_professional_status
from nm.core.source_excerpt import capture as capture_source
from nm.core.threading import BindResult, BindState, bind
from nm.domain import advice, citation, decision, engagement, issue, reads, reservation
from nm.domain import brief as brief_mod
from nm.domain import proof as domain_proof
from nm.domain import summary as matter_memory
from nm.domain.answer import Answer, Element, ElementKind, Mode, Route, Signal
from nm.domain.budget import refuse_partial
from nm.domain.capacity import CapacityPosition
from nm.domain.capacity import record_on as record_capacity
from nm.domain.clock import FORUM
from nm.domain.gates import Response
from nm.domain.matter import (
    Basis,
    CauseOfAction,
    Certainty,
    Fact,
    Matter,
    Posture,
    Provenance,
    Role,
    Side,
    Thread,
    new_id,
)
from nm.domain.metrics import Outcome, Phase, TurnMetrics
from nm.domain.proof import ProofStatus
from nm.domain.quotable import Quotable
from nm.domain.register import PEER
from nm.domain.spoken import dispute
from nm.domain.spoken import named as in_prose
from nm.domain.text import blank, refuses_blank_text, snippet
from nm.domain.traceability import implements
from nm.domain.turn_receipt import (
    TurnReceipt,
    answer_from_payload,
    answer_payload,
    opening_id,
    release_index,
)
from nm.domain.turn_receipt import fingerprint as offer_fingerprint
from nm.ports.coverage import CoveragePort
from nm.ports.elements import ElementsPort
from nm.ports.evidence import (
    Coverage,
    EvidenceNeed,
    EvidencePort,
    EvidenceResult,
    Finding,
    SourceKind,
    TreatmentState,
)
from nm.ports.institution import Against, PreInstitutionPort
from nm.ports.model import (
    ModelError,
    ModelPort,
    OutputTruncated,
    Prompt,
    Tier,
)
from nm.ports.store import StaleWrite, StorePort

#: The most evidence rounds one turn may run. DECLARED SINCE SLICE 1 AND READ
#: BY NOTHING until now -- `evidence_bound_hit` was a field no code ever set.
#: A bound that is not enforced is not a bound, and the failure it exists to
#: prevent is the expensive one: a turn that keeps asking for evidence, hits no
#: limit, and eventually answers as though it had found what it was looking for.
MAX_EVIDENCE_ROUNDS = 3

# How many authorities an answer SHOWS. Retrieval keeps every candidate -- H4
# forbids discarding what might be right -- but forty grounds in one answer is
# not an answer, and the count not shown is stated rather than hidden.
MAX_AUTHORITIES_SHOWN = 3

# The failing state each grounding gate reports. Held here rather than inside
# `grounding.py` so the gate matrix stays the only place a state vocabulary is
# declared, and an unknown gate id raises instead of becoming a free-text label.
_GROUNDING_STATE = {
    "G-QUOTE": "not_verbatim",
    "G-GROUND": "unsupported",
    "G-ATTRIB": "not_attributable",
    "G-BINDING": "not_assessed",
    "G-INFORCE": "not_in_force",
}

class TurnRefused(Exception):
    """No new answer is emitted; input persistence depends on admission.

    A grounding refusal may retain admitted input without saving its derived
    answer. A refused replay is different: prior_receipt_saved identifies the
    already recorded response, whose current release is refused. Neither case
    may assert that unadmitted narrative was saved or that a new answer exists.

    It carries the gates that withheld it and the DISCLOSURES the turn had
    already computed. Withholding the answer is not the same as withholding the
    reason: a disclosure states what could not be established, asserts no law,
    and can mislead nobody -- while a bare refusal leaves the advocate with
    nothing to act on and no idea whether to try again.
    """

    def __init__(self, message: str, *, gates: tuple[str, ...] = (),
                 disclosures: tuple[str, ...] = (),
                 matter_id: str | None = None,
                 prior_receipt_saved: bool = False,
                 persistence: str = "not_committed",
                 matter_version: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.gates = gates
        self.disclosures = disclosures
        self.matter_id = matter_id
        """The file the refused turn was about, where there is one.

        A caller that cannot name the matter opens a new one on the next
        turn — which is how GS-15 came to run four turns across four
        different files, each blocking on a posture nobody had stated."""
        self.prior_receipt_saved = prior_receipt_saved
        self.persistence = persistence
        self.matter_version = matter_version


@refuses_blank_text()
@dataclass
class TurnInput:
    advocate_id: str
    message: str
    turn_id: str = field(default_factory=lambda: new_id("turn"))
    matter_id: str | None = None
    thread_id: str | None = None
    today: date = field(default_factory=date.today)
    jurisdiction: str = FORUM
    work_product: str = ""
    request_offer: dict | None = None
    """Normalized transport offer, excluding only its id; None for core callers."""
    expected_version: int | None = None
    session_reference: str = ""
    """Server-derived management reference, never a cookie or authentication token."""

    parties: dict = field(default_factory=dict)
    """BK-34. WHO IS INVOLVED, given at intake: name -> `client` | `adverse`
    | `related`.

    Carried on the turn for the same reason the release is: it is an act by a
    person, recorded on the file with who and when, rather than a setting.
    The engine writes it to `Matter.intake_parties` BEFORE the screens run, so
    the conflict screen reads the file and answers on its own -- no call site
    decides to skip a screen.
    """

    release: dict = field(default_factory=dict)
    """BK-34. Screens the advocate is RELEASING with this brief.

    `screen kind -> because`. B4 requires a NAMED HUMAN release, and the
    advocate sending the turn is that human: the deployment is a controlled
    roster of practising advocates and, in a solo practice, the advocate IS
    the firm. Requiring a second person would stop every matter at intake --
    not a stricter product, an unusable one.

    IT TRAVELS ON THE TURN AND NOT IN A SETTING, and that is what keeps it
    honest. A release held in configuration is the blanket exception this row
    removed, wearing a different name; a release carried by the brief it
    clears is an act by a person, at a time, recorded on the file with both.
    The engine writes it to `Matter.released_screens` BEFORE the screens run,
    so the screen sees it and clears -- rather than the engine deciding to
    skip a screen, which no call site is allowed to do.

    EMPTY IS THE ORDINARY VALUE. Most turns release nothing because the
    matter was released once, when it was opened.
    """

    capacity: dict[str, str] | None = None
    """Explicit human capacity state and basis; actor/time belong to the server."""


@dataclass
class TurnOutput:
    turn_id: str
    answer: Answer
    matter: Matter | None
    metrics: TurnMetrics
    replayed: bool = False


# ============================================================== ADMIT =====


@implements("B1")
def classify_route(message: str,
                   on_open_matter: bool = False) -> tuple[Route, Mode, str]:
    """THE FALLBACK, for when the route read could not run.

    THIS USED TO BE THE WHOLE MECHANISM: two keyword lists and two length
    rules, under a docstring that said *"Route on WHAT THE MESSAGE DISCLOSES,
    never on its length."* It routed on length three lines below that
    sentence -- `<= 3` words meant not a matter, `> 25` meant a full brief.

    LENGTH CARRIES NO INFORMATION HERE. "bail" is one word and a case fact;
    "hi" is one word and a greeting. A count cannot tell them apart because
    the difference is meaning. `nm.core.route` reads it now.

    WHAT SURVIVES IS THE ASYMMETRY, which was always the real rule: a full
    workup on a question wastes time, while a matter read as a greeting is
    NEGLIGENT -- and NON_MATTER writes nothing to any file, so the turn is
    gone. With no model there is nothing to read the meaning with, so this
    refuses to guess and takes the safe direction.

    AN EMPTY MESSAGE IS STILL REFUSED. That is not a judgement about content;
    there is no content.
    """
    text = message.strip()
    if not text:
        raise TurnRefused("an empty message discloses nothing")

    return Route.MATTER, Mode.SHORT_QUESTION, \
        "Taking this as a matter. Say if I have that wrong."


# ============================================================ the turn =====


@dataclass(frozen=True)
class ScreenResult:
    """The outcome of ADMIT-A. THREE STATES, not two.

    `clear` false with `assessed` false means the screen COULD NOT RUN, which
    is not the same as a refusal and is never the same as a pass.
    """

    clear: bool
    assessed: bool
    reason: str | None = None
    blocking_question: str = ""
    urgent: bool = False
    rows: tuple[str, ...] = ()

    screens: tuple[object, ...] = ()
    """The `Screen` objects behind `rows`. The rows are prose for the
    advocate; these are the state the handover carries, and reading one
    back out of the other would be parsing an undeclared format.
    """
    """Every screen and its state, for the ADVOCATE.

    The states were in the type and in the metrics and nowhere
    an advocate could see them -- measured at zero lines on
    7 September 2026. §9: the third state must be visible in the
    OUTPUT, not only in the type."""


# `_tier` WAS HERE, AND IT IS WITHDRAWN. See backend/nm/domain/tiers.py: the
# escalation was measured on 6 September 2026 and the cause read ran at 33% on
# gpt-5.2 against 97% on gpt-4o-mini, on one fixed prompt. A decisive read is
# not made safer by a model that is worse at it.
#
# `nm.domain.reads.is_decisive` STAYS and still has callers: it is what makes
# G-READ fire on a decisive read that answers with nothing. What is withdrawn
# is the tier mapping, not the table.


def _arguable(assumption: str) -> tuple[str, ...]:
    """The rivals the routing named, out of its own sentence.

    The corpus adapter already writes them: ". Also arguable: X; Y". Parsed
    back rather than plumbed through a new field because the sentence is the
    contract the adapter already keeps -- and a second channel for the same
    fact is the shape this build refuses. If the wording changes, this returns
    nothing and the decision records no alternatives, which is worse than a
    wrong list and is visibly worse.
    """
    marker = "Also arguable:"
    if marker not in (assumption or ""):
        return ()
    tail = assumption.split(marker, 1)[1]
    return tuple(a.strip() for a in tail.split(";") if a.strip())


def _record(into: list, what: str, thread: Thread,
            from_facts: tuple, produced: int) -> None:
    """Record a derivation, or record NOTHING and let the absence speak.

    `produced == 0` appends no row on purpose. A row carrying a count of zero
    would make "this read found nothing this turn" look like an ordinary
    value that happens to be small, and `cascade.lost` would never see it.
    The absence of the row IS the loss.
    """
    if produced:
        into.append(cascade.Derived(
            # THE KEY carries the thread id, so two threads' counts are
            # different values. THE LABEL is what a person reads. B-103.
            name=f"{what} on {thread.id}",
            shown=f"{what} on {dispute(thread.label)}",
            value=str(produced),
            from_facts=tuple(from_facts),
            # A COUNT. It grows as the file grows, so its growth is not a
            # correction — but it is still watched for LOSS, which is the
            # forgetting this whole mechanism exists to find.
            kind=cascade.Kind.MEASUREMENT))



#: How much of a retrieved span an ANSWER shows. B-078.
#:
#: E-102's judge read a turn that reproduced the whole bare text of Article 14
#: as its ground. An advocate knows what the Article says; what they need from
#: a ground is WHICH provision was read and a handle to read the rest, which is
#: the locator sitting beside it.
EXCERPT = 180



def _excerpt(span: str, cap: int = EXCERPT) -> str:
    """The first sentence of a span, capped. NEVER with the ellipsis inside.

    THE ELLIPSIS GOES OUTSIDE THE QUOTATION MARKS at the call site, and that
    is load-bearing rather than typographic: `nm.core.grounding` pulls quoted
    runs out of an element and looks for them in the retrieved text, so an
    ellipsis inside the quotes would make the product fail to find its own
    excerpt and withhold the turn on its own rendering.

    A SENTENCE RATHER THAN A CHARACTER COUNT. `[:400]` cuts mid-word, and text
    that reads as broken is text an advocate discounts -- which is the
    opposite of what a ground is for.
    """
    text = " ".join((span or "").split())
    if len(text) <= cap:
        return text
    stop = text.rfind(". ", 0, cap + 1)
    if stop > cap // 3:
        return text[:stop + 1]
    cut = text.rfind(" ", 0, cap + 1)
    return text[:cut if cut > 0 else cap]


def _shortened(span: str, cap: int = EXCERPT) -> bool:
    """Whether `_excerpt` dropped anything, so the caller can say so."""
    return _excerpt(span, cap) != " ".join((span or "").split())




def _label_of(value: str, labels: dict) -> str:
    """A thread the advocate can recognise.

    The exposure prompt sends labels now, so a well-behaved read answers
    in them and this returns the value unchanged. It exists for the other
    case: a read that answers with an id anyway must not put one in front
    of an advocate, and a bare `unknown` would be worse than the id -- it
    would name no dispute at all.
    """
    if value in labels:
        return dispute(labels[value])
    return in_prose(value) if not str(value).startswith(("thr_", "mat_")) \
        else "another dispute on this file"

def _positions_note(thread) -> str:
    """What the file establishes, for the read that recommends the next step.

    B-078. THE STEP HAD NOTHING SPECIFIC TO BE ABOUT, so it described the
    general case -- what a compliant letter would contain rather than what
    the letter on the file does. These positions were already computed and
    already persisted; showing them is the whole change.

    ONLY WHAT IS SETTLED ENOUGH TO ACT ON. A NOT_ASSESSED position says
    nobody worked it out, and handing that to a read whose output is an
    imperative invites a step recommended on an element nobody examined.
    """
    from nm.domain import proof as _proof
    from nm.domain.proof import ProofStatus as Status

    positions = _proof.from_stored(getattr(thread, "proof", ()) or ())
    lines = []
    for p in positions:
        if p.status is Status.HELD:
            lines.append(f"  ESTABLISHED — {p.element}: {'; '.join(p.material)}")
        elif p.status is Status.OBTAINABLE:
            lines.append(f"  NOT YET — {p.element}: {p.closing_material}")
        elif p.status is Status.ABSENT:
            lines.append(f"  NOTHING WOULD ESTABLISH — {p.element}: {p.dead_end}")
    if not lines:
        return ""
    return ("\n\nWHAT THIS FILE ESTABLISHES, element by element. A step about "
            "any of these is about THE MATERIAL NAMED, not about what such "
            "material should look like:\n" + "\n".join(lines))


def _provision_of(position: str) -> str:
    """The provision a reservation is about, or "".

    The position is written as `the provision this rests on: <ref>` at the
    one site that records one, so the ref is everything after the colon.
    Parsing it here rather than storing it separately keeps ONE owner of
    the format -- and the alternative, a second field carrying the ref,
    is a copy that can disagree with the sentence it came from.
    """
    _, _, ref = position.partition(":")
    return ref.strip()


def _reactivated(matter) -> list:
    """E5. A reservation a NEW FACT brought back, as a current finding.

    *...and then as a current finding with its consequence, never as
    vindication.* The tone is owned by `Reservation.as_current_finding`, not
    composed here: three call sites would be three tones and one of them would
    be smug.

    NOT LIVE IS THE ORDINARY CASE and produces nothing. That silence IS the
    feature -- E5's counterexample is the same objection restated on every
    turn after the advocate went the other way, so a reservation that appears
    when nothing reactivated it would be the defect rather than the fix.
    """
    from nm.domain import reservation as res

    back = res.live(res.from_stored(matter.reservations))
    if not back:
        return []
    return [Element(
        kind=ElementKind.FINDING, disclosure=True, signal=Signal.CONTRADICTION,
        text=("A point you went the other way on is live again. "
              + " ".join(r.as_current_finding() for r in back)))]


def _with_screens(elements: list, screens, split=None, *, mode: Mode | None = None) -> tuple:
    """The answer's elements, with the trailing background after the action.

    BACKGROUND FOLLOWS THE ACTION. `Answer.__post_init__` refuses a leading
    GROUND -- PRD §6.2 S3 -- and appending this at the top of the list put it
    first on every turn. The type refused it before any test had to.

    ONE OWNER, THREE CALL SITES. Each of the three branches that builds an
    Answer needs this, and a note composed independently in three places is
    three notes that drift.
    """
    # G-SPLIT RIDES HERE FOR THE SAME REASON AND NOT BESIDE IT. A second
    # place that appends trailing background is a second place to get the
    # ordering wrong, and this one already has the rule written down.
    # DG-11: reads performed before derivation can already have emitted a
    # disclosure (for example a party the conflict screen did not cover).
    # Lead with the actual operative element, preserving every other element
    # and its type/order. Never invent a step or disguise support as one: if
    # there is none, Answer still rejects the result.
    ordered = list(elements)
    explanatory = mode in (Mode.EXPLANATION, Mode.ASSESSMENT)
    lead = next((i for i, element in enumerate(ordered)
                 if element.kind in (ElementKind.ACTION, ElementKind.QUESTION)
                 and (not explanatory or element.gate)), None)
    if lead is not None and lead > 0:
        ordered.insert(0, ordered.pop(lead))
    tail = [split] if split is not None else []
    if screens.rows and screens.clear and screens.assessed and screens.screens:
        # Routine successful checks are retained in the matter/audit record,
        # not recited as the advocate's answer. A permitted-but-limited screen
        # (notably corpus coverage) remains visible and cannot be hidden merely
        # because it did not block processing.
        for screen in screens.screens:
            gate_id, outcome = screens_mod.gate_for(screen)
            material = (screen.state is not screens_mod.ScreenState.CLEAR
                        or (screen.kind is screens_mod.ScreenKind.COMPETENCE
                            and outcome != "covered") or screen.released is not None)
            if material:
                tail.append(Element(
                    kind=ElementKind.GROUND, disclosure=True,
                    text=screen.detail or screen.not_assessed_because,
                    gate=gate_id))
    elif screens.rows:
        # THE ROW SAYS WHAT HAPPENED, AND SAYS IT ONCE.
        #
        # It used to hard-code "none of which has run" and a closing sentence
        # about substance being admitted under an exception, because before
        # BK-34 both were unconditionally true. They are not any more, and the
        # result was visible on a served turn: *"Screens on this matter, none
        # of which has run: Screens on this matter, all cleared: emergency —
        # …"* — the fixed prefix wrapped around a row that carried its own.
        #
        # A SENTENCE THAT WAS TRUE OF EVERY CASE STOPS BEING CHECKED, and
        # this one had drifted from the product by a whole feature. The
        # prefix now comes from the same place the outcome does.
        cleared = screens.clear and screens.assessed
        tail.append(Element(
            kind=ElementKind.GROUND, disclosure=not cleared,
            text=("; ".join(screens.rows)
                  + ("" if cleared else
                     ". Substance is admitted with them outstanding, which "
                     "is recorded as an exception and is not a finding that "
                     "they clear."))))
    return (*ordered, *tail)



def _matter_name(message: str, parties: dict | None) -> str:
    """`X v Y` where the parties are known, else a whole-word opening.

    ONE OWNER, and it is a module function rather than a method because the
    projection needs the same answer for a matter opened before intake
    existed -- and a second implementation of "what is this file called"
    would be two names for one file.
    """
    given = parties or {}
    client = next((n for n, side in given.items() if side == "client"), "")
    adverse = next((n for n, side in given.items() if side == "adverse"), "")
    if client and adverse:
        return f"{client} v {adverse}"
    if client or adverse:
        return client or f"against {adverse}"

    first = (message or "").strip().split("\n")[0].strip()
    if not first:
        return "New matter"
    # ON A WORD BOUNDARY. `[:60]` produced "...Goods were suppl".
    #
    # THIS WAS THE SECOND COPY, and finding it is what turned a one-line fix
    # into a rule. Cutting on the last space that fits was worked out HERE,
    # for the matter title, and then thirty-six other places in `backend/nm/`
    # shortened a sentence with a bare `[:N]` -- including the limitation
    # premise the advocate is asked to confirm, which reached a served turn
    # ending "and they hav". One person solving it privately is how six folds
    # and two provision patterns happened; `nm.domain.text.snippet` owns it.
    return snippet(first, 60)


#: THRESHOLDS THAT ALREADY HAVE AN OWNER FOR THEIR PROSE, so the map does not
#: say them twice. A declared set rather than a condition written inline: the
#: second threshold to get a dedicated renderer is an entry here, and a
#: renderer added without one is a duplicated line an advocate reads as two
#: findings. That is CLAUDE.md section 4 -- what refuses the second copy.
#:
#: `LIMITATION` is rendered in full by `_limitation_elements`, with its
#: Article, its accrual and its alternatives.
_THRESHOLDS_RENDERED_ELSEWHERE = frozenset({thresholds.Threshold.LIMITATION})


class TurnEngine:
    """Pure orchestration. Every dependency arrives as a port."""

    def __init__(self, store: StorePort, evidence: EvidencePort, model: ModelPort,
                 coverage: CoveragePort | None = None,
                 elements: "ElementsPort | None" = None, clock=None,
                 professional_approval: Callable[[str], object] | None = None,
                 pre_institution: "PreInstitutionPort | None" = None) -> None:
        from nm.domain.advocate import utcnow

        self._clock = clock or utcnow
        self._professional_approval = professional_approval
        self._store = store
        self._evidence = evidence
        self._model = model
        # D5's ELEMENT TABLE, and its absence is not silence either. With no
        # port the proof read does not run and the turn SAYS SO, in the same
        # `not_assessed` shape everything else here uses -- an advocate who
        # sees no proof positions must be able to tell "nothing was worked
        # out" from "everything is held".
        self._elements = elements
        # LB-121's PRE-INSTITUTION TABLE, and its absence is not silence: with
        # no port the `statutory_notice` threshold stays BLOCKED with the
        # map's own "not assessed on this thread" reason, exactly as it read
        # before this table existed. An unwired installation says nothing it
        # cannot support rather than reporting that no condition arises.
        self._pre_institution = pre_institution
        # Optional, and its ABSENCE IS NOT SILENCE: with no coverage port the
        # engine fires G-COVERAGE in the `not_measured` state rather than
        # skipping the gate, so an unwired installation discloses that it
        # cannot vouch for coverage instead of implying it can.
        self._coverage = coverage

    def professional_access(self, account_id: str) -> dict:
        """An independent, live privilege read; never consulted for ordinary work."""
        return read_professional_status(self._professional_approval, account_id, self._clock())

    def run(self, turn: TurnInput) -> TurnOutput:
        metrics = TurnMetrics(turn_id=turn.turn_id, matter_id=turn.matter_id)
        started = time.perf_counter()
        try:
            known = self._known_matter(turn)
            if known is not None:
                receipt = self._matching_receipt(known, turn)
                if receipt is not None:
                    from nm.domain.emergency import PERMITTED_WORK

                    if turn.work_product == PERMITTED_WORK:
                        # A prior receipt does not extend emergency permission.
                        return self._protective_turn(turn, metrics, started)
                    metrics.matter_id = known.id
                    metrics.outcome = Outcome.BLOCKED if receipt.answer["blocked"] else Outcome.OK
                    self._store.record_metrics(metrics.as_dict())
                    return TurnOutput(turn.turn_id, answer_from_payload(receipt.answer),
                                      known, metrics, replayed=True)
                self._require_version(known, turn)
            return self._run(turn, metrics, started, known)
        except TurnRefused:
            # A DELIBERATE refusal, already recorded by the branch that raised
            # it, with its outcome and the gate that fired. Re-recording here
            # would overwrite `gated` with `failed` and make every withheld
            # turn look like a crash -- which is the difference between "the
            # gate worked" and "the product is broken" in every metric built
            # on this file.
            raise
        except Exception as exc:
            # A turn that crashed must still leave a record, or the most
            # diagnostically valuable turns are the only ones with none.
            metrics.outcome = Outcome.FAILED
            metrics.failure = f"{type(exc).__name__}: {exc}"
            metrics.latency_ms = int((time.perf_counter() - started) * 1000)
            self._store.record_metrics(metrics.as_dict())
            raise

    def _known_matter(self, turn: TurnInput) -> Matter | None:
        matter = self._store.load(turn.matter_id or opening_id(turn.advocate_id, turn.turn_id))
        if matter is not None and matter.advocate_id != turn.advocate_id:
            raise TurnRefused("this matter belongs to another advocate")
        if turn.matter_id and matter is None:
            raise TurnRefused("the requested matter could not be found")
        return matter

    @staticmethod
    def _require_version(matter: Matter, turn: TurnInput) -> None:
        if turn.expected_version is not None and matter.version != turn.expected_version:
            moved = StaleWrite(
                f"this matter moved from version {turn.expected_version} to {matter.version}")
            moved.expected_version = turn.expected_version
            moved.matter_version = matter.version
            raise moved

    @staticmethod
    def _offer(turn: TurnInput, matter_id: str) -> str:
        offer = dict(turn.request_offer) if turn.request_offer is not None else {
            key: value for key, value in asdict(turn).items()
            if key not in {"request_offer", "turn_id", "session_reference"}}
        # The assigned id and an opening whose id was not acknowledged name
        # the same target, not different instructions. Every other field stays.
        offer["matter_id"] = matter_id
        return offer_fingerprint(offer)

    def _matching_receipt(self, matter: Matter, turn: TurnInput) -> TurnReceipt | None:
        receipts, problems = release_index(matter)
        if problems:
            raise TurnRefused("recorded release evidence is inconsistent; no replay is authorised")
        if turn.turn_id in receipts:
            receipt = receipts[turn.turn_id]
            if receipt.offer_fingerprint != self._offer(turn, matter.id):
                raise StaleWrite("this turn identity names different original instructions")
            return receipt
        if matter.has_applied(turn.turn_id):
            raise TurnRefused(
                "the legacy turn has no verifiable original-offer receipt; review the file")
        return None

    def _commit_released(self, matter: Matter, turn: TurnInput, answer: Answer,
                         expected_version: int, *, input_admitted: bool = True) -> Matter:
        receipt = TurnReceipt(
            turn_id=turn.turn_id, offer_fingerprint=self._offer(turn, matter.id),
            recorded_at=self._clock().isoformat(), answer=answer_payload(answer),
            message=turn.message if input_admitted else "", input_admitted=input_admitted)
        updated = replace(matter.applied(turn.turn_id),
                          turn_receipts=(*matter.turn_receipts, receipt))
        return self._store.commit(updated, expected_version=expected_version)

    # ---------------------------------------------------------------------
    def _run(self, turn: TurnInput, metrics: TurnMetrics, started: float,
             admitted_snapshot: Matter | None) -> TurnOutput:
        from nm.domain.emergency import PERMITTED_WORK

        if turn.work_product == PERMITTED_WORK:
            return self._protective_turn(turn, metrics, started)
        try:
            if turn.release is not None:
                if (not isinstance(turn.release, dict)
                        or set(turn.release) - {"scope", "capacity"}):
                    raise ValueError("intake answers must name only scope or legacy capacity")
                if any(not isinstance(answer, str) or blank(answer)
                       for answer in turn.release.values()):
                    raise ValueError("an intake answer must be nonblank text")
            if turn.capacity is not None and (turn.release or {}).get("capacity"):
                raise ValueError("use the explicit capacity assessment, not two capacity answers")
            capacity = (CapacityPosition.record(
                turn.capacity, actor=turn.advocate_id, now=self._clock())
                if turn.capacity is not None else None)
        except (ValueError, TypeError) as exc:
            raise TurnRefused(str(exc)) from exc
        # ---------------- ADMIT ----------------
        t0 = time.perf_counter()
        metrics.failed_phase = Phase.ADMIT

        # READ, NEVER COUNTED. The matter is part of what the turn
        # discloses: an advocate five turns in who types "and now?" has
        # not stopped talking about their matter, and NON_MATTER writes
        # nothing to any file.
        route, mode, mode_statement = self._read_route(turn, metrics)

        if route is Route.NON_MATTER:
            answer = self._non_matter_answer(turn, mode, mode_statement, metrics)
            # No implicit matter creation for a courtesy or an abstract question.
            # Inside an explicitly opened file, retain the released conversation
            # as a receipt, never as an admitted case fact or cleared screen.
            recorded = None
            if admitted_snapshot is not None:
                recorded = self._commit_released(
                    admitted_snapshot, turn, answer, admitted_snapshot.version)
                metrics.matter_id = recorded.id
            metrics.outcome = Outcome.OK
            metrics.stages["admit_ms"] = int((time.perf_counter() - t0) * 1000)
            metrics.latency_ms = int((time.perf_counter() - started) * 1000)
            self._store.record_metrics(metrics.as_dict())
            return TurnOutput(turn.turn_id, answer, recorded, metrics)

        matter = self._load_or_create(turn, admitted_snapshot)
        metrics.matter_id = matter.id

        # ---- G-DUTY: is this an instruction that must be REFUSED? ---------
        #
        # AFTER THE FILE IS LOADED AND BEFORE POSTURE.
        # Whether a document may be backdated does not depend on which side
        # we act for, so the posture gate has no business in front of it --
        # and it was: `draft me a backdated acknowledgment so the limitation
        # restarts` opened a matter and asked whose side we were on.
        #
        # It sees the file because EVERY read does: on turn four, `And what
        # is the limitation on that?` is unreadable without it. Placing it
        # earlier kept a refused instruction off the file and made the one
        # read that judges an instruction the only one flying blind.
        refusal = self._read_duty(turn, matter, metrics)
        metrics.fire("G-DUTY",
                     "refused" if refusal.must_refuse else
                     ("not_assessed" if refusal.refused else "clear"),
                     refusal.refused or refusal.why
                     or "nothing here requires refusal")
        if refusal.must_refuse:
            answer = self._refusal_answer(turn, refusal, mode,
                                          mode_statement, metrics)
            matter = self._commit_released(
                matter, turn, answer, matter.version, input_admitted=False)
            metrics.outcome = Outcome.BLOCKED
            metrics.stages["admit_ms"] = int((time.perf_counter() - t0) * 1000)
            metrics.latency_ms = int((time.perf_counter() - started) * 1000)
            self._store.record_metrics(metrics.as_dict())
            return TurnOutput(turn.turn_id, answer, matter, metrics)


        expected_version = matter.version

        # THE RELEASE IS RECORDED BEFORE THE SCREENS READ IT.
        #
        # Order matters and it is the whole design: the engine does not decide
        # to skip a screen. It writes what the advocate released onto the
        # file, and the screen then reads the file and clears itself. No call
        # site is permitted to bypass a screen, which is the rule that made
        # `may_admit_substance` the one owner of that decision in the first
        # place.
        # WHEN THIS FILE WAS LAST WORKED. The forum's date, from the
        # turn -- never the machine's (BK-14).
        matter = replace(matter, last_activity=turn.today.isoformat())
        if turn.parties:
            matter = replace(matter, intake_parties={
                **(matter.intake_parties or {}),
                **{str(n).strip(): str(side) for n, side in turn.parties.items()
                   if str(n).strip()},
            })
        if turn.release:
            matter = replace(matter, intake_answers={
                **(matter.intake_answers or {}),
                **{kind: {"by": turn.advocate_id, "answer": answer,
                          "at": self._clock().isoformat()}
                   for kind, answer in turn.release.items()},
            })
        if capacity is not None:
            matter = record_capacity(matter, capacity)

        # ---- ADMIT-A: screens, on names and danger only --------------------
        # An external review found this code doing what the first draft of the
        # spec described: extracting and binding substance BEFORE the screens.
        # That both retains material on an uncleared file and sends privileged
        # content to a model provider before the matter is cleared to hold it.
        screens = self._run_screens(matter, turn, metrics)

        # THE SCREENS LAND ON THE FILE, before the blocked branch below.
        #
        # A matter whose screens REFUSED it is the one a receiving
        # advocate most needs the states for, so recording them after the
        # `clear` check would lose them on exactly that file.
        #
        # `assessed` gains the name here rather than through `concluded`:
        # that dict is the DERIVE phase's record and these run in ADMIT-A,
        # before any substance is read. Same field, same rule, one level
        # up -- a second mechanism for matter-level sections would be the
        # copy S9 is about.
        matter = replace(
            matter, screens=screens.screens,
            assessed=tuple(dict.fromkeys((*matter.assessed, "screens"))))
        if not screens.clear:
            # An INCOMPLETE screen is not a passed screen. The block is the
            # answer, and no substance is read on the way to producing it.
            answer = Answer(
                route=route, mode=mode, mode_statement=mode_statement,
                elements=(Element(
                    kind=ElementKind.QUESTION,
                    text=screens.blocking_question,
                    signal=Signal.EMERGENCY if screens.urgent else Signal.NONE),),
                blocked=True, blocked_reason=screens.reason)
            metrics.outcome = Outcome.BLOCKED
            # AND THEY ACTUALLY LAND. The comment above says the screen
            # states are recorded before this branch, and they were --
            # onto a local immutable matter that this branch then threw
            # away by returning without committing, and with `None` as
            # the matter. So the one file a receiving advocate most
            # needs the states for was the one file that never kept
            # them.
            #
            # Committing is safe here for the reason the branch exists:
            # NO SUBSTANCE has been read. The receipt retains only the safe
            # question and offer digest, not the unadmitted narrative. A failed
            # commit must not be reported as a saved instruction.
            matter = self._commit_released(
                matter, turn, answer, matter.version, input_admitted=False)
            metrics.latency_ms = int((time.perf_counter() - started) * 1000)
            self._store.record_metrics(metrics.as_dict())
            return TurnOutput(turn.turn_id, answer, matter, metrics)

        # ======== SCREEN BOUNDARY: no substance is read, retained, or sent to
        # a provider above this line.

        # ---- ADMIT-B: substance ---------------------------------------------
        matter, bound = self._admit_facts(matter, turn, metrics)
        # The original input remains the receipt/history. Derivation receives
        # only the active dispute's allocated words, never a mixed chronology.
        scopes = dict(bound.allocations)
        work_turn = turn
        if bound.thread is not None and bound.thread.id in scopes:
            scoped = "\n".join(scopes[bound.thread.id])
            work_turn = replace(
                turn, message=scoped or f"Review the recorded dispute: {bound.thread.label}")
        metrics.stages["admit_ms"] = int((time.perf_counter() - t0) * 1000)

        # WHAT MOVED ON THE FILE, before anything is derived from it. P18.
        #
        # A correction spoken on this turn has just superseded a fact. Every
        # conclusion recorded against that fact is stale FROM THIS LINE, and
        # the derivation below reworks it -- so the correction turn itself
        # shows the old value, the new value and why, rather than the turn
        # after it noticing a difference. This is an INPUT fact about the
        # file and it is kept on a withheld turn too: `admitted` is taken
        # below this line on purpose.
        matter = self._currency_inputs(matter, turn, metrics)

        # THE FILE, BUILT ONCE AND GIVEN TO EVERYTHING THAT DERIVES.
        # A projection over the matter, holding nothing the matter does
        # not -- so it can never disagree with the file it summarises.
        # SELECTED, NOT TAILED. The account is chosen against what this turn
        # is about, with every dated fact and every fact a live derivation
        # rests on pinned so it cannot be dropped for a character count.
        memory = matter_memory.build(
            matter, bound.thread.id if bound.thread is not None else None,
            about=turn.message,
            load_bearing=self._load_bearing(matter, bound.thread))

        # ---------------- DERIVE ----------------
        t1 = time.perf_counter()
        metrics.failed_phase = Phase.DERIVE
        elements: list[Element] = []

        # THE FACTS THIS TURN DID NOT ADD. Taken BEFORE the derive phase,
        # because a reservation is reactivated by a NEW fact and every
        # fact looks new to a comparison made after they are recorded.
        seen_before = frozenset(f.id for f in matter.facts)

        relied_on: tuple[Finding, ...] = ()
        retrieved: tuple[Finding, ...] = ()
        # THE NON-DERIVED ELEMENTS, bound BEFORE the branch and not inside
        # the one that happens to need it. B-104's second assembly reads
        # this, and binding it in a single branch left it unbound on the
        # two that block -- pylint E0601, which is in the gate for exactly
        # this and has now caught the same shape THREE times in one
        # session. The third was a patch script whose deletion range ran
        # past its own insert, which is why the check is mechanical.
        head: list[Element] = []
        # WHAT THIS TURN CONCLUDED, bound before the branch for the same
        # reason `head` is: the blocking branches do not derive, and a
        # variable assigned in one branch and read after it is the E0601
        # shape this file has now produced three times in one session.
        # EMPTY on a blocked turn is the right value, not a missing one --
        # a turn that asked a question concluded nothing, and nothing is
        # what must be written over the standing theory.
        concluded: dict = {}

        # G-SPLIT. THE COUNT IS REPORTED, AND THE FILE IS NOT SPLIT ON IT.
        #
        # This used to open a thread per dispute the read described. The read
        # measures 2-3 of 6 across six briefs and is unstable on identical
        # input, so the file is no longer split on it -- the advocate is told
        # what the message looked like and invites the split themselves.
        #
        # `threading.py`'s asymmetry justified splitting because a wrong merge
        # inverts the advice SILENTLY. This is the disclosure that makes it
        # not silent.
        if bound.thread is None:
            # An ambiguous bind placed nothing. Reporting a count here would
            # be a finding about a message nobody managed to file.
            pass
        elif not bound.counted:
            # NOBODY COUNTED. One thread, and that is a fallback and not a
            # finding -- said so rather than left to look like `single`.
            metrics.fire("G-SPLIT", "not_assessed",
                         "the dispute count could not be read on this turn, "
                         "so this file holds one thread by fallback and not "
                         "because one dispute was found")
        elif bound.looks_like > 1:
            metrics.fire("G-SPLIT", "split",
                         f"instructions allocated across {bound.looks_like} working disputes")
        else:
            metrics.fire("G-SPLIT", "single",
                         "this message reads as one dispute")

        split_note = None
        if bound.thread is not None and bound.counted and bound.looks_like > 1:
            split_note = (Element(
                kind=ElementKind.GROUND,
                text=(f"I have organised these instructions across {bound.looks_like} "
                      f"disputes on the board and am working on {dispute(bound.thread.label)}. "
                      "Please check the allocation; you can change the focus "
                      "or correct that organisation."),
                gate="G-SPLIT", disclosure=True, signal=Signal.NONE))

        if bound.blocks:
            # G-THREAD. The account is KEPT on the matter -- it is the binding
            # that is refused, not the facts. Guessing here attaches one
            # thread's posture and limitation to another thread's facts, and
            # every citation stays correct while the advice inverts.
            metrics.fire("G-THREAD", bound.state.value, bound.reason)
            elements.append(Element(
                kind=ElementKind.QUESTION, text=bound.question,
                gate="G-THREAD", signal=Signal.CONTRADICTION))
            if bound.proposal is not None:
                elements.append(Element(
                    kind=ElementKind.GROUND,
                    text=(f"Proposed merge, not performed: {bound.proposal.left} "
                          f"and {bound.proposal.right} on {bound.proposal.on}.")))
            answer = Answer(route=route, mode=mode, mode_statement=mode_statement,
                            elements=_with_screens(elements, screens, split_note),
                            blocked=True,
                            blocked_reason=f"G-THREAD: {bound.reason}")
            thread = None
            # DERIVED NOTHING, SAID SO. This branch never reaches `_derive`,
            # so `derived_values` was UNBOUND and `_record_turn` raised on
            # every G-THREAD block — CLAUDE.md §6 exactly, and pylint E0601
            # exists in the gate for it.
            #
            # `()` and not `None`: a turn that derived nothing is a real
            # answer, and the cascade needs it to be one. `None` would mean
            # "no turn to compare against", which is a different claim.
            derived_values: tuple = ()
        elif not bound.thread.posture.resolved:
            # G-POSTURE, and it blocks THE DIRECTIVE STEP rather than the
            # turn. Nothing side-dependent is computed: no recommendation,
            # no authority set. What a provision SAYS is read back, because
            # that is the legislature's words and they do not change with
            # the side -- and refusing them meant an advocate asking a bare
            # question of law was told "whose side are we on?".
            thread = bound.thread
            no_proceeding = (thread.posture.role in (Role.NOT_APPLICABLE, Role.NOT_INSTITUTED)
                             and thread.posture.basis is Basis.STATED)
            source_explanation = no_proceeding and mode is Mode.EXPLANATION
            metrics.fire("G-POSTURE", "unresolved",
                         f"thread {thread.id} has role={thread.posture.role.value}; "
                         f"no directive step "
                         f"and no authority set is computed")
            described = thread.posture.client_described_as
            if described:
                # THE QUESTION NARROWS. Repeating the general question at an
                # advocate who has already named their client is how the
                # previous version trapped every multi-turn conversation.
                #
                # IT ASKS ABOUT THE SIDE, NOT ABOUT THE FILING. "Did they file"
                # is answerable "no" on every advice-only matter, and a "no"
                # leaves the gate exactly where it was -- which is how five
                # live matters blocked turn after turn. What the gate needs is
                # who is SEEKING and who is RESISTING, and an advocate advising
                # before any proceeding can always answer that.
                question = (f"You act for {described}. Are they the one seeking "
                            f"something here, or the one resisting what the other "
                            f"side seeks? I am not able to recommend a step until "
                            f"that is settled — the same provision helps one side "
                            f"and hurts the other, and {described} does not by "
                            f"itself say which side they are on.")
            else:
                question = ("Whose side are we on in this matter — is the client "
                            "the one seeking something, or the one resisting what "
                            "the other side seeks? I am not able to recommend a "
                            "step until that is settled, because the same provision "
                            "helps one side and hurts the other.")

            # A repeated unresolved question is not evidence that the advocate
            # ignored us. State the remaining limitation without blame or an
            # instruction to invent a procedural role.
            preface = ""
            repeat = True
            standing = matter.open_question("G-POSTURE", thread.id)
            if standing is not None and standing.ignored:
                # THE ONE BRANCH THAT DELIBERATELY STOPS ASKING. An advocate who
                # has left the question alone is not to be nagged. It still says
                # what would lift the block, because a limitation stated without
                # its remedy is a dead end rather than a courtesy.
                repeat = False
                question = ("The client's position on this issue remains unresolved "
                            "in my assessment. I have retained your instructions, but "
                            "have not released a side-dependent recommendation. You "
                            "need not repeat the brief or choose a role that does not "
                            "fit; we can retain the material and review the relevant "
                            "provisions while that limitation remains. When you are "
                            "ready, naming the client as the one seeking or the one "
                            "resisting is all it takes.")
            opening = matter.intake_answers.get("opening", {}).get("answer", {})
            if opening.get("proceedings") == "none" or no_proceeding:
                # A recorded absence of proceedings is not a missing answer to
                # "which side". IT PREFACES THE QUESTION; IT DOES NOT REPLACE IT.
                #
                # THE MEASURED DEFECT, 22 September 2026, matter 5 turn 1. This
                # branch ASSIGNED OVER the narrowed question above, so an
                # advocate who had written "I act for Anjali Sharma" and "We
                # want an injunction urgently" was served a paragraph about this
                # product's own assessment and was asked NOTHING. The turn
                # blocked, and blocked again on the next turn, because the one
                # thing that would lift the block was never requested.
                #
                # It is the review's 1.5 conflation surviving one level up. That
                # fix taught the MODEL that being unfiled and having a side are
                # two different facts; this branch was still treating the first
                # as an answer to the second, in the sentence an advocate reads.
                #
                # THE GENERAL RULE: a branch that knows a DIFFERENT fact may add
                # to the ask and may never silently discard it. `ask` is composed
                # below from a preface and a question, so these branches stop
                # being last-writer-wins over a value whose conditions are not
                # mutually exclusive -- `no_proceeding` and `described` are both
                # true on an ordinary advice-only brief.
                preface = ("Your instructions record no proceedings, and I have "
                           "retained that — I will not assign a filed role. That is "
                           "not the same as knowing which side the client is on, "
                           "and the side is what I still need. ")
            # COMPOSED ONCE, from the parts the branches above established, and
            # never by assignment. A preface cannot eat the question: whatever
            # else this turn says, the advocate can always read what would lift
            # the block.
            ask = f"{preface}{question}" if repeat else question
            # THE QUESTION LEADS. It is the blocking thing, and S3 requires
            # the first element to be an action or a question -- what
            # follows is what could be established without knowing the side.
            if source_explanation:
                ask = ("No filed role is needed to read the retrieved provisions below. "
                       "This is a limited source explanation, not a concluded assessment "
                       "of how the law applies to your client's position or a recommendation.")
            elements.append(Element(
                kind=ElementKind.GROUND if source_explanation else ElementKind.QUESTION,
                thread=thread.id, text=ask, disclosure=source_explanation,
                gate="G-POSTURE", signal=Signal.UNRESOLVED_POSTURE,
            ))
            derived, relied_on, retrieved, derived_values = self._derive(
                thread, work_turn, metrics, memory, side_blind=True,
                # THE SAME EXPRESSION THE ANSWER IS BUILT WITH, four lines
                # below. Deriving "will this be served?" twice from different
                # conditions is how the two drift.
                blocked=not source_explanation,
                facts=matter.facts, matter_id=matter.id, response_mode=mode,
                parties=self._parties_of(matter).names)
            elements.extend(derived)
            answer = Answer(route=route, mode=mode, mode_statement=mode_statement,
                            elements=_with_screens(elements, screens, split_note, mode=mode),
                            blocked=not source_explanation,
                            blocked_reason=None if source_explanation
                                else "G-POSTURE: posture unresolved")
        else:
            thread = bound.thread
            # WHO THIS BRIEF NAMES, recorded for the NEXT turn's conflict
            # screen. BK-34.
            #
            # THE SEQUENCING IS THE WHOLE DESIGN. The screens run in ADMIT-A,
            # before this turn's words have been read by anything -- so a
            # party named today cannot be screened today without admitting
            # the brief first, which is exactly what B3 forbids. What it can
            # do is be RECORDED today and screened from tomorrow, and the
            # advocate names the principals at intake so the first turn is
            # not screened against nobody.
            #
            # A PARTY ARRIVING ON TURN SIX IS THE CASE THIS EXISTS FOR.
            # `Screen.stale_for` already refuses a clearance that floats free
            # of its party set -- "a conflict check that cleared two parties
            # says nothing about the third who arrives on turn six" -- and
            # until this read existed there was no way for a third party to
            # arrive at all.
            #
            # HERE AND NOT IN `_derive`, because `_derive` holds a
            # `matter_id` and not the matter, and what this read produces is
            # a change to the file.
            matter = self._read_parties(turn, memory, matter, metrics, elements)
            # Carry these disclosures into any late-source re-derivation too.
            head = list(elements)
            derived, relied_on, retrieved, derived_values = self._derive(
                thread, work_turn, metrics, memory, facts=matter.facts,
                matter_id=matter.id, concluded=concluded,
                paused=matter.paused_need_texts, response_mode=mode,
                parties=self._parties_of(matter).names)
            elements.extend(derived)
            answer = Answer(route=route, mode=mode, mode_statement=mode_statement,
                            elements=_with_screens(elements, screens, split_note, mode=mode))

        # D7 -- THE CROSS-FILE PASS, AFTER the threads and EXACTLY ONCE.
        #
        # Not a step inside each thread. D7's counterexample says why: *the
        # client's own recovery suit undermines his defence in the cheque
        # matter, and NO SINGLE THREAD REVEALS IT.* A per-thread pass cannot
        # see it however carefully each thread is worked, because the exposure
        # exists only in the pair.
        #
        # E-082 is precise about the shape: produced *exactly once on every
        # multi-thread file, empty or not*, and its counterexample is *emitted
        # twice, or silently omitted*. Both are defects and they fail in
        # opposite directions — twice is noise the advocate learns to skip,
        # and omitted reads as "nothing found" when nobody looked.
        # NOT ON A BLOCKED TURN, and that is not an exception to "exactly
        # once". E-082 is about a turn that PRODUCES ANALYSIS: the exposure
        # line belongs to an answer, and a blocked turn has none — it asked a
        # question and stopped.
        #
        # Running it anyway cost a model call on every blocked turn, which a
        # slice-1 invariant already refused: a turn that blocks because the
        # thread binding is ambiguous must be CHEAP, or the product charges
        # the advocate for its own uncertainty.
        # WHAT THE TURN CONCLUDED GOES ON THE THREAD, before the commit.
        #
        # Phase 1. Until 6 September 2026 the matter held facts and forgot
        # conclusions, so every turn rebuilt the theory from the account and
        # GS-15 produced five different ones in five turns. This is where a
        # conclusion stops being this turn's output and starts being the
        # thread's state.
        #
        # ONLY ON A TURN THAT DERIVED. A blocked turn asked a question and
        # concluded nothing, and writing an empty conclusion over a standing
        # theory would lose it exactly as regeneration did.
        # THE INPUT, AS IT STOOD BEFORE ANY CONCLUSION WAS WRITTEN.
        #
        # Everything above this line is what the ADVOCATE put on the file:
        # the facts they stated, the screens, the thread binding, the
        # posture. Everything below is what this turn WORKED OUT.
        #
        # A withheld turn commits this and not `matter`. The gated branch
        # has always said `the input is committed and the answer is not`,
        # and it was committing `matter` -- which by then carried the
        # theory, the decisions, the authorities and eight assessed
        # sections. The answer was refused and the conclusions were kept,
        # so the next turn read as settled what was never grounded and
        # never served.
        admitted = matter

        if concluded:
            # WRITTEN BY NAME, NOT BY `**concluded`.
            #
            # The dynamic form worked and was invisible: the sweep that asks
            # which persisted fields nothing ever writes could not see it, and
            # reported `Thread.decisions` as a field that reads as a capability
            # and is permanently empty. It was being written the whole time --
            # by a keyword nothing could read.
            #
            # A write no check can see is a write no check can VERIFY, and the
            # two neighbouring fields passed only because `issues=` and
            # `theory=` happen to appear as keywords on unrelated types. That
            # is passing for the wrong reason, which is worse than failing.
            settled = replace(
                thread,
                theory=concluded.get("theory", thread.theory),
                issues=concluded.get("issues", thread.issues),
                decisions=concluded.get("decisions", thread.decisions),
                proof=concluded.get("proof", thread.proof),
                deadlines=concluded.get("deadlines", thread.deadlines),
                premises=concluded.get("premises", thread.premises),
                objective=concluded.get("objective", thread.objective),
                reliefs=concluded.get("reliefs", thread.reliefs),
                recommendation=concluded.get(
                    "recommendation", thread.recommendation),
                gaps=concluded.get("gaps", thread.gaps),
                authorities=concluded.get(
                    "authorities", thread.authorities),
                # F-B-17. MERGED IN `_requirements`, so a later judgment adds a
                # row without dropping what the section established.
                requirements=concluded.get(
                    "requirements", thread.requirements),
                requirement_reads=concluded.get("requirement_reads", thread.requirement_reads),
                requirement_outcomes=concluded.get(
                    "requirement_outcomes", thread.requirement_outcomes),
                checklist_session=concluded.get("checklist_session", thread.checklist_session),
                evidence=concluded.get("evidence", thread.evidence),
                thresholds_told=concluded.get(
                    "thresholds_told", thread.thresholds_told),
                # WHAT WAS ASSESSED, FROM THE KEYS AND NOT FROM A LIST.
                #
                # Every field above persists as empty until written, so
                # empty means either "built and found nothing" or "never
                # built". The handover cannot tell those apart without
                # this, and they are opposite facts (BK-10).
                #
                # `concluded` already knows precisely which sections this
                # turn worked out. Reading its keys means a section added
                # to the dict is recorded here the same day, rather than
                # waiting for somebody to remember a second list.
                assessed=tuple(dict.fromkeys(
                    (*thread.assessed, *concluded))),
            )
            matter = matter.with_thread(settled)
            thread = settled

            # THE RESERVATIONS ARE MATTER-SCOPED and were being written
            # into the THREAD's channel, where `_run`'s named write-back
            # dropped them silently. Found by
            # `test_every_persisted_field_has_a_writer`, which is exactly
            # its job: a field that reads as a capability and is
            # permanently empty is indistinguishable from the thing never
            # having happened.
            #
            # REACTIVATED HERE TOO, against the facts this turn recorded.
            # A fact whose statement CONTAINS the provision reference the
            # reservation names is material about the very thing the
            # advocate overruled us on. Exact matching on a citation --
            # §5's one reliable key -- and not a similarity score.
            if "reservations" in concluded:
                standing_res = reservation.from_stored(
                    concluded["reservations"])
            else:
                standing_res = reservation.from_stored(matter.reservations)

            fresh = {f.id: f.statement for f in matter.facts
                     if f.id not in seen_before}
            touches = {
                r.position: fid
                for r in standing_res
                for fid, statement in fresh.items()
                if _provision_of(r.position)
                and _provision_of(r.position) in statement}
            standing_res = reservation.reactivate(
                standing_res, frozenset(fresh), touches)

            matter = replace(
                matter, reservations=standing_res,
                assessed=tuple(dict.fromkeys(
                    (*matter.assessed, "reservations"))))

        exposure: list[Element] = []
        if not answer.blocked:
            # THE THREADS THIS MESSAGE OPENED, so the pass does not argue
            # across a split nothing has confirmed.
            born = frozenset(
                t.id for t in (*bound.others,
                               *( (bound.thread,) if bound.created
                                  and bound.thread is not None else ()))
            )
            # Source-bound multi-dispute admission is not the old count-only
            # split. All admitted accounts must be compared, including siblings.
            exposure = list(self._exposure(
                matter, metrics, frozenset() if bound.allocations else born))
            answer = replace(answer, elements=tuple(
                [*answer.elements, *exposure]))

        # A DECISIVE READ CAME BACK EMPTY, AND THE ANSWER WAS COMPUTED ANYWAY.
        #
        # THE GENERAL FORM OF B-088, and it replaces the guard that was
        # written for the correction read alone. Six reads are declared
        # DECISIVE in `backend/nm/domain/reads.py` -- dates, cause, factors, posture,
        # role, and the correction that rides inside dates -- on one narrow
        # test: does the output change a DATE, an AMOUNT, or WHICH LAW IS
        # READ? For those, an empty answer is indistinguishable from "that
        # thing is not present", and every number downstream is derived from
        # it, so no later check can catch it.
        #
        # The population is the TABLE, not a list here: a seventh decisive
        # read is covered the day it is declared. Asked of the model port,
        # which is the single place every structured read passes through --
        # the alternative is six call sites each remembering to ask, which is
        # the arrangement that produced one guard for one read.
        answer = replace(answer, elements=tuple(
            [*answer.elements, *self._decisive_empties(metrics),
             *self._refused_reads(metrics), *_reactivated(matter),
             *self._tier_degraded(metrics)]))

        # WHAT THIS TURN DERIVED, RECORDED AGAINST WHAT IT RESTED ON. P18.
        #
        # After the answer is assembled and before the invariants read it,
        # because the one thing this can add to the answer is a disclosure
        # that something on the file is still stale -- and a disclosure
        # appended after the invariants and the grounding gate have run is a
        # sentence nothing checked.
        matter, currency_notes = self._currency_settle(
            matter, thread, derived_values, concluded, retrieved, turn, metrics,
            # A BLOCKED TURN DID NOT TRY. A posture question is not a failed
            # recomputation, and counting it against the rework bound would
            # exhaust a node on three unanswered questions.
            attempted=not answer.blocked)
        if currency_notes:
            answer = replace(answer, elements=tuple(
                [*answer.elements, *currency_notes]))

        # Class-B invariants, asserted on the ASSEMBLED object, before emission.
        self._assert_invariants(answer, metrics)

        # THE GROUNDING GATE, on the assembled answer and on the findings it
        # actually rests on. It runs LAST because everything before it can
        # still edit, reorder or truncate the text that will be emitted, and a
        # check that runs on an earlier draft has checked a different string.
        report = grounding.verify(answer, relied_on, retrieved)

        # B-104. A BOUNDED SECOND ROUND, BEFORE THE REPORT IS RECORDED.
        #
        # Measured on GS-15's served run of 5 September 2026: the advocate
        # said "the agreement was never registered", the answer reached for
        # TRANSFER OF PROPERTY ACT s.53A -- part performance, which is the
        # correct provision for that question -- and the turn was withheld
        # because s.53A had not been retrieved. Two of five turns produced no
        # advice. THE GATE WAS RIGHT EVERY TIME. What was missing is that the
        # withholding named a provision the product could simply look up.
        #
        # So a citation the answer names and retrieval did not fetch is
        # treated as a RETRIEVAL NEED THE TURN DISCOVERED LATE: fetch it, and
        # if it is held, DERIVE AGAIN with the text in front of the reads that
        # write the answer. Re-verifying the old answer against a newly
        # fetched provision would be worse than withholding -- the prose was
        # composed without it, so passing the citation check would certify
        # text nobody wrote from the source.
        #
        # ONCE, AND THE BOUND IS THE WHOLE SAFETY ARGUMENT. An unbounded loop
        # lets a model conjure citations until one lands, which is the failure
        # G-GROUND exists to stop. A second failure withholds, exactly as
        # before.
        #
        # Recorded BEFORE `metrics.fire`, because a violation the second round
        # clears must not sit on the record as a gate the turn failed. What IS
        # recorded is the round itself, and the advocate is told.
        if report.violations and not answer.blocked:
            late = self._fetch_late_citations(answer, retrieved, turn, metrics)
            if late:
                concluded.clear()
                derived, relied_on, retrieved, derived_values = self._derive(
                    thread, work_turn, metrics, memory, facts=matter.facts,
                    matter_id=matter.id, seed=late, concluded=concluded,
                    paused=matter.paused_need_texts, response_mode=mode,
                parties=self._parties_of(matter).names)
                # ONE CONSTRUCTION, THROUGH THE ASSEMBLER, like every
                # other branch. This built an Answer from `head`, then
                # replaced it with a longer tail, and neither call went
                # through `_with_screens` -- so the screen rows and the
                # split notice were dropped on every turn that needed a
                # second citation attempt, while `G-UNSCREENED` fired
                # exactly as it does on the turns that do show them.
                # B-128's shape, on the one path nothing counted.
                #
                # Assembling the list before constructing, rather than
                # constructing twice, is also what stops the rows being
                # added once at each step.
                # THE SECOND DERIVATION IS THE ONE THAT COUNTS, so the ledger
                # is settled again against it -- `record` re-stamps, and a
                # node recomputed twice on one turn is recomputed once in
                # the history because the revision was already closed.
                matter, currency_notes = self._currency_settle(
                    matter, thread, derived_values, concluded, retrieved,
                    turn, metrics, attempted=True)
                answer = Answer(
                    route=route, mode=mode, mode_statement=mode_statement,
                    elements=_with_screens(
                        [*head, *derived, *exposure, *self._late_note(late),
                         *self._decisive_empties(metrics),
                         *self._refused_reads(metrics), *_reactivated(matter),
                         *self._tier_degraded(metrics), *currency_notes],
                        screens, split_note, mode=mode))
                self._assert_invariants(answer, metrics)
                report = grounding.verify(answer, relied_on, retrieved)

        metrics.grounding = report.as_dict()
        for violation in report.violations:
            metrics.fire(violation.gate_id,
                         _GROUNDING_STATE[violation.gate_id], violation.detail)
        metrics.stages["derive_ms"] = int((time.perf_counter() - t1) * 1000)

        if metrics.gating_violations:
            # A grounding violation GATES the output. It does not soften it.
            metrics.outcome = Outcome.GATED

            # THE ANSWER IS REFUSED. WHAT THEY SAID IS KEPT.
            #
            # The commit used to sit below this, so a withheld turn saved
            # NOTHING — GS-15 turn 1 was withheld and the matter was never
            # created, so the next turn opened a fresh one and everything the
            # advocate had written was gone.
            #
            # These gates are about whether the ANSWER is supported by what
            # was retrieved. None of them is a finding about the input, so the
            # input is committed and the answer is not. `turns_applied` is
            # deliberately NOT set: the turn is not done, and a retry must
            # re-derive rather than replay a no-op.
            persistence = "unknown"
            try:
                # `admitted`, NOT `matter`. See the snapshot above: what
                # this turn derived is discarded with the answer it was
                # derived for, and what the advocate said is kept.
                matter = self._store.commit(
                    admitted, expected_version=expected_version)
                persistence = "input_only"
            except Exception as exc:  # noqa: BLE001 -- reported, never fatal
                # Losing the note is worse than the refusal and is not worth
                # turning the refusal into a crash over.
                metrics.violate(
                    "I1", f"a withheld turn did not keep what the advocate "
                          f"said: {type(exc).__name__}: {exc}")

            metrics.latency_ms = int((time.perf_counter() - started) * 1000)
            self._store.record_metrics(metrics.as_dict())
            gates_withheld = tuple(sorted({v.rule
                                           for v in metrics.gating_violations}))
            self._record_turn(turn, answer, matter, metrics, derived_values,
                              withheld_by=gates_withheld)
            # NAME THE GATES. "Gated by a grounding violation" tells the
            # advocate nothing they can act on and tells an operator nothing
            # they can find; the gate id is the handle for both.
            gates = tuple(sorted({v.rule for v in metrics.gating_violations}))
            raise TurnRefused(
                "output withheld by " + ", ".join(gates) + ": "
                + "; ".join(v.detail for v in metrics.gating_violations),
                gates=gates,
                # The disclosures survive the withhold. They are the only part
                # of the turn that says what could NOT be established, and they
                # are the part the advocate most needs when they are refused.
                disclosures=tuple(e.text for e in answer.elements if e.disclosure),
                # THE FILE THEY ARE ON. Without it a caller cannot continue
                # the conversation and opens a new matter on the next turn,
                # which is how GS-15 came to run four turns on four files.
                matter_id=matter.id, persistence=persistence,
                matter_version=matter.version if persistence == "input_only" else None)

        # ======== BYTE BOUNDARY: nothing above has been shown or saved.

        # ---------------- EMIT ----------------
        t2 = time.perf_counter()
        metrics.failed_phase = Phase.EMIT
        matter = self._remember_questions(matter, answer, metrics, turn)

        # THE ENGAGEMENT, WHERE THE FILE IS SETTLED. Tenet 4.
        #
        # Nothing new is read: how the advocate described their client is
        # C3's `client_described_as` and the disputes are C4's threads.
        # Those two ARE the engagement as far as this file knows it, and
        # `not_recorded` names the five things Appendix E wants that
        # nothing here records.
        #
        # NOT IN ADMIT-A, where it was written first and came out empty on
        # every turn -- no thread has opened that early, so `covers` was
        # `()` and `client` was `""`: a record present in the type and
        # absent in fact, which is S1 inside the feature closing S1's last
        # blocker.
        #
        # NOT IN `concluded` EITHER. A blocked turn opens threads too, and
        # its engagement is as real as any other: a file that asked a
        # question instead of answering one still has a client and a
        # dispute on it.
        #
        # THIS IS NOT `G-SCOPE`. Refusing a step outside recorded scope is
        # B5 at slice 10 and stays there. Recording what the file covers
        # is the disclosure that makes the gate's absence visible.
        matter = replace(
            matter,
            engagement=engagement.of(
                next((t.posture.client_described_as for t in matter.threads
                      if t.posture.client_described_as), ""),
                tuple(t.label for t in matter.threads)),
            assessed=tuple(dict.fromkeys(
                (*matter.assessed, "engagement"))))

        # A current review requires actual assessed sections and a released
        # answer, not merely a finished turn or a nonempty thread list.
        if thread is not None and not answer.blocked:
            from nm.domain.summary import DERIVED_SECTIONS

            current = matter.thread(thread.id)
            if current is not None and set(DERIVED_SECTIONS) <= set(current.assessed):
                matter = matter.with_thread(replace(current, assessed=tuple(dict.fromkeys(
                    (*current.assessed, "review_current")))))

        try:
            matter = self._commit_released(matter, turn, answer, expected_version)
        except StaleWrite as exc:
            # The matter moved underneath. Re-derive rather than overwrite --
            # and NAME the gate, so the matrix's claim is one the metrics can
            # be checked against.
            metrics.fire("G-STALE", "stale", str(exc))
            metrics.outcome = Outcome.GATED
            metrics.latency_ms = int((time.perf_counter() - started) * 1000)
            self._store.record_metrics(metrics.as_dict())
            raise
        metrics.outcome = Outcome.BLOCKED if answer.blocked else Outcome.OK
        metrics.failed_phase = None
        metrics.stages["emit_ms"] = int((time.perf_counter() - t2) * 1000)
        metrics.latency_ms = int((time.perf_counter() - started) * 1000)
        self._store.record_metrics(metrics.as_dict())
        self._record_turn(turn, answer, matter, metrics, derived_values)
        return TurnOutput(turn.turn_id, answer, matter, metrics)

    def _briefing_block(self, matter: Matter | None) -> dict:
        """The intake readiness the advocate reads, from the one owner. P24 /
        BK-54-AC3. Readiness is derived from the OPEN GAPS minus the needs the
        advocate marked unavailable -- never from the turn having finished."""
        return briefing_mod.block(matter)

    def _record_turn(self, turn: TurnInput, answer: Answer, matter: Matter,
                     metrics: TurnMetrics,
                     derived: tuple = (), withheld_by: tuple[str, ...] = ()
                     ) -> None:
        """A diagnostic archive, never a substitute for the canonical receipt.

        Released answers are now sealed with the matter in TurnReceipt. This
        archive additionally keeps derivation/call traces and, when withheld,
        an unapproved draft. Browser readback must use the release projection,
        not assume every archived draft was shown or successfully committed.

        FAILING TO RECORD MUST NOT FAIL THE TURN. The advocate has been given
        advice and the file has it; losing the review copy is a real defect and
        it is not one worth throwing their answer away over. So it is caught,
        recorded as a violation, and the turn stands -- and because it is a
        violation rather than a silence, a transcript store that has quietly
        stopped writing is visible rather than discovered when someone comes
        looking months later.
        """
        # THE CALL TRACE, where the model port keeps one.
        #
        # Asked of the port by DUCK TYPE rather than by import: the core must
        # not know an adapter exists, and a `hasattr` here is the whole of the
        # coupling. A port that does not trace contributes nothing and the
        # transcript simply has no `model_calls` key -- absent, not an empty
        # list, because an empty list would claim the turn made no calls.
        trace = None
        take = getattr(self._model, "take", None)
        if callable(take):
            try:
                trace = take()
            except Exception as exc:  # noqa: BLE001 -- never fail a turn
                metrics.violate("I1", f"the call trace could not be drained: "
                                      f"{type(exc).__name__}: {exc}")

        # TWO COUNTS OF ONE THING MUST AGREE, and this is not belt-and-braces.
        #
        # `llm_calls` is incremented by the turn after a read returns; the
        # trace is written by the port as the call is made. They count the
        # same calls by different routes, so a disagreement means one of them
        # is wrong -- and the failure mode is a trace that records NOTHING,
        # which reads exactly like a turn that made no calls.
        #
        # Measured, 5 September 2026: the tracer read `usage.input_tokens`,
        # which this port does not have. It raised inside every read, the
        # reads' own `except` recorded the AttributeError as a violation, and
        # the transcript then said the turn made zero calls. The product was
        # right and the record was silent about which half had failed.
        if trace is not None and trace["count"] != metrics.llm_calls:
            metrics.violate(
                "I1", f"the call trace and the turn disagree about how many "
                      f"model calls were made: traced {trace['count']}, "
                      f"counted {metrics.llm_calls}. One of them is wrong and "
                      f"the transcript cannot be read as a record of this turn.")

        try:
            self._store.record_turn({
                "turn_id": turn.turn_id,
                "matter_id": matter.id,
                **({"model_calls": trace} if trace is not None else {}),
                "advocate_id": turn.advocate_id,
                "at": datetime.now(timezone.utc).isoformat(),
                # B-101. WAS THIS SHOWN TO THE ADVOCATE?
                #
                # A LIST AND NEVER A NULL, so the three states are on the
                # record as values: `[]` is a turn that was served, and a
                # populated list is a turn withheld naming the gates that
                # withheld it. `blocked` below is a DIFFERENT thing -- the
                # ANSWER's own blocked flag, set when a gate stops a step --
                # and it reads False on a withheld turn, which is how the
                # judge came to grade text the advocate never saw.
                #
                # The transcript is kept for REVIEW, where the refused draft
                # is exactly what you want, and used for SCORING, where it is
                # exactly what you must not have. One record, two uses; this
                # field is what lets a reader tell them apart.
                "withheld_by": list(withheld_by),
                "today": turn.today.isoformat(),
                "message": turn.message,
                "route": answer.route.value,
                "mode": answer.mode.value,
                "mode_statement": answer.mode_statement,
                "blocked": answer.blocked,
                "blocked_reason": answer.blocked_reason,
                # P24. INTAKE READINESS, which is NOT the turn completing. A
                # controlling gap open keeps the file not-ready however cleanly
                # the turn answered; a need marked unavailable is paused, not
                # looped. C1 NEVER[4] made a served field the advocate reads.
                "briefing": self._briefing_block(matter),
                "elements": [
                    {"kind": e.kind.value, "text": e.text, "thread": e.thread,
                     "signal": e.signal.value, "disclosure": e.disclosure,
                     "gate": e.gate, "collapsible": e.collapsible,
                     "by_when": e.by_when.isoformat() if e.by_when else None,
                     "no_deadline_reason": e.no_deadline_reason,
                     # BK-37's section, so a turn READ BACK renders the way
                     # it was served. Without it a restored conversation
                     # falls into one section and the advocate sees a
                     # different shape from the one they were given -- which
                     # is the transcript disagreeing with the answer, and the
                     # transcript is what they would rely on to say what they
                     # were told.
                     "section": brief_mod.section_of(e).value,
                     "refs": list(e.refs)}
                    for e in answer.elements],
                "gates_fired": [
                    {"gate": g.gate_id, "state": g.state}
                    for g in metrics.gates_fired],
                "step_assessments": [dict(row) for row in metrics.step_assessments],
                "violations": [
                    {"rule": v.rule, "detail": v.detail}
                    for v in metrics.violations],
                # A3 §5.4. WHAT THIS TURN DERIVED, so the NEXT turn has a
                # `before` to compare against. Without it the cascade has no
                # trigger: `changes(before, after)` needs both, and a turn
                # only ever has an after.
                #
                # Re-deriving the previous position from today's facts would
                # not do: the matter holds facts, not derivations, so it would
                # be computed FROM the corrected fact and would always agree
                # with itself.
                "derived": [
                    {"name": d.name, "shown": d.shown, "value": d.value,
                     "from_facts": list(d.from_facts)}
                    for d in derived],
                "cost_usd": metrics.cost_usd,
                "llm_calls": metrics.llm_calls,
            })
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a silence
            metrics.violate(
                "I1", f"the turn was served and not recorded for review: "
                      f"{type(exc).__name__}: {exc}")

    @implements("B2")
    def _protective_turn(self, turn: TurnInput, metrics: TurnMetrics,
                         started: float) -> TurnOutput:
        """A recorded emergency handoff, before any narrative or model read.

        No legal merits, new facts or screen clearance are produced here. The
        declaration permits a bounded protective/referral step only; it cannot
        authorise sending the raw brief to a provider.

        B2 is partial: this consumes the persisted declaration, rechecks its
        permission against the clock and records a protective-only handoff.
        The manual per-danger UrgencyRegister leads this handoff, including
        unknown times. Automatic every-turn assessment and calibration remain
        unbuilt; a recorded action is not verified advice or performed work.
        """
        from nm.domain.emergency import latest
        from nm.domain.urgency import protective_texts

        matter = self._store.load(turn.matter_id) if turn.matter_id else None
        if matter is None or matter.advocate_id != turn.advocate_id:
            raise TurnRefused("open an authorised matter before requesting protective triage")
        now = self._clock()
        declaration = latest(matter.emergencies or (), now)
        approval = self.professional_access(turn.advocate_id)
        permitted = (declaration is not None and declaration.permits(turn.work_product)
                     and declaration.actor_id == turn.advocate_id
                     and approval["state"] == "approved")
        prior = self._matching_receipt(matter, turn)
        if prior is not None:
            recorded = prior.validated_answer()
            metrics.matter_id = matter.id
            metrics.latency_ms = int((time.perf_counter() - started) * 1000)
            if not recorded.blocked and not permitted:
                metrics.outcome = Outcome.BLOCKED
                self._store.record_metrics(metrics.as_dict())
                raise TurnRefused(
                    "The earlier handoff remains recorded, but its protective permission "
                    "is no longer live. No answer is replayed and no new work is committed. "
                    "Review the declaration and make a new request if appropriate.",
                    matter_id=matter.id, prior_receipt_saved=True)
            # A historical refusal remains a refusal even if permission changed.
            # Changes to danger records do not rewrite the old released bytes.
            metrics.outcome = Outcome.BLOCKED if recorded.blocked else Outcome.OK
            self._store.record_metrics(metrics.as_dict())
            return TurnOutput(turn.turn_id, recorded, matter, metrics, replayed=True)
        self._require_version(matter, turn)
        text = (
            "Confirm the immediate danger, the verified deadline and the person "
            "who can give instructions; arrange urgent assistance from the "
            "responsible advocate or appropriate emergency service if needed. "
            "Keep the original material available. No merits position, filing "
            "or communication is authorised by this handoff."
            if permitted else
            "A live emergency declaration and current professional approval are required "
            "for this screen-exception handoff. "
            "The recorded urgency remains on the file. Renew or review the "
            "declaration; ordinary screens still govern any substantive advice."
        )
        elements = [Element(kind=ElementKind.QUESTION, text=line, signal=Signal.EMERGENCY)
                    for line in protective_texts(matter.urgency_records)]
        elements.append(Element(kind=ElementKind.QUESTION, text=text,
                                signal=Signal.EMERGENCY))
        if declaration and permitted:
            elements.append(Element(kind=ElementKind.GROUND, disclosure=True,
                                    signal=Signal.EMERGENCY,
                                    text=declaration.said(now)))
        answer = Answer(route=Route.MATTER, mode=Mode.SHORT_QUESTION,
                        mode_statement="Protective handoff only; no legal merits assessed.",
                        elements=tuple(elements), blocked=not permitted,
                        blocked_reason=None if permitted else
                        "no live emergency declaration with current professional approval")
        # Even a refusal retains its attempt, but never the unadmitted narrative.
        receipt = {"turn_id": turn.turn_id, "actor_id": turn.advocate_id,
                   "at": now.isoformat(), "permitted": permitted,
                   "work_product": turn.work_product,
                   "declaration": declaration.as_dict() if declaration else None,
                   "professional_approval": approval,
                   "substance_admitted": False}
        updated = replace(matter,
                          emergency_triage=(*(matter.emergency_triage or ()), receipt))
        matter = self._commit_released(
            updated, turn, answer, matter.version, input_admitted=False)
        metrics.matter_id = matter.id
        metrics.outcome = Outcome.OK if permitted else Outcome.BLOCKED
        metrics.latency_ms = int((time.perf_counter() - started) * 1000)
        self._store.record_metrics(metrics.as_dict())
        return TurnOutput(turn.turn_id, answer, matter, metrics)

    # ------------------------------------------------------------ helpers ---
    @implements("B3")
    def _run_screens(self, matter: Matter, turn: TurnInput,
                     metrics: TurnMetrics) -> ScreenResult:
        """ADMIT-A. Every screen, named, and every one NOT_ASSESSED.

        SLICE 1 SCOPE, STATED HONESTLY AND NOW VISIBLY. The conflict,
        competence and engagement screens are B3-B5 and are slice 10. What
        this admits is that none of them has run -- and until 7 September 2026
        it admitted that to the METRICS ONLY. Measured: zero screen-related
        lines reached the advocate, under a comment claiming "the output says
        so rather than reading as though it had passed".

        THE POPULATION IS `ScreenKind`, through `screens.unscreened`, so the
        five rows come from the vocabulary rather than from what happened to
        run. An advocate reading four rows believes the fifth was checked;
        an advocate reading none believes there was nothing to check.

        `may_admit_substance` DECIDES, rather than this returning True. Every
        screen is outstanding, so it refuses -- and substance is admitted
        under a DECLARED exception, recorded the way the emergency exception
        is. When B3 lands, one screen starts answering and nothing here moves.
        """
        outstanding = tuple(self._screen(kind, matter, turn, metrics)
                            for kind in screens_mod.ScreenKind)

        # EVERY SCREEN FIRES ITS GATE. BK-34.
        #
        # `trace` T9 caught this the moment the producers landed: *a gate
        # declared unbuilt that something consults fails harder -- the matrix
        # would be telling the advocate nothing evaluates a condition while
        # something quietly does.* The screens were built and the gates still
        # said `built=False`, so the matrix was one release behind the code.
        #
        # THE STATE VOCABULARIES ARE THE GATES' OWN, not the screens'. A gate
        # that accepted `ScreenState` values would be a second vocabulary for
        # one fact, and `metrics.fire` refuses an out-of-vocabulary state --
        # which is what forces the mapping to be written down here rather than
        # assumed at five call sites.
        for screen in outstanding:
            gate_id, state = screens_mod.gate_for(screen)
            if gate_id:
                metrics.fire(gate_id, state,
                             screen.detail or screen.not_assessed_because)

        may, why = screens_mod.may_admit_substance(outstanding)

        # THE BLANKET EXCEPTION IS GONE (BK-34).
        #
        # This used to build five NOT_ASSESSED screens, watch
        # `may_admit_substance` refuse them, and then admit substance anyway
        # under a general "slice 10" exception -- on EVERY matter, including
        # conflict, competence, scope, capacity and emergency. Registration
        # simultaneously told the advocate the firm's conflict registry
        # governed the session. Both statements were false and the second was
        # a false assurance about the one check whose value is being trusted.
        #
        # What replaces it is not a stricter rule but a TRUTHFUL one: every
        # screen that can be answered is answered, and the ones that need a
        # person are BLOCKED with the question rather than waved through. A
        # blocked screen is a finding the advocate can clear in one line; the
        # blanket exception was a sentence nobody read.
        if may:
            metrics.fire("G-UNSCREENED", "screened",
                         "every screen on this matter clears: " + why)
            # THE ROWS STILL GO OUT, and this was a regression for about
            # twenty minutes. `rows=()` on the cleared path meant an advocate
            # whose matter passed every screen was told NOTHING about the
            # screens -- which is §9 from the other side: the state has to be
            # visible in the OUTPUT, and "it cleared" is a state.
            #
            # ONE LINE, NOT FIVE. Five cleared rows every turn is the noise
            # BK-7 closed for the thresholds, and an advocate who scrolls past
            # them will scroll past the turn they do not clear.
            return ScreenResult(
                clear=True, assessed=True,
                reason="every screen clears: " + why,
                rows=(("Screens on this matter permit the current work within the "
                       "recorded limits; this is not complete legal coverage: "
                       + "; ".join(f"{s.kind.value} — {s.detail}"
                                   for s in outstanding)),),
                screens=outstanding)

        metrics.fire(
            "G-UNSCREENED", "unscreened",
            "this matter is not cleared to hold substance: " + why)
        # THE BLOCK IS THE ANSWER, so it has to BE an answer. `Element`
        # refuses blank text and this returned a `ScreenResult` with no
        # `blocking_question` at all -- 191 tests failed with `an Element must
        # say something`, which is the type catching a screen that refused a
        # matter and could not say what it wanted.
        #
        # THE QUESTION IS THE SCREENS' OWN DETAIL, not a sentence composed
        # here. Each screen already says what it is waiting for, in words
        # aimed at the advocate; writing a second version of that in the
        # engine would be a second owner for the same question.
        asks = [s.detail or s.not_assessed_because
                for s in outstanding
                if s.state is not screens_mod.ScreenState.CLEAR]
        return ScreenResult(
            clear=False, assessed=True,
            reason=why,
            blocking_question=(
                "Before I work substance on this file: "
                + "; ".join(a for a in asks if a)
                or "this matter is not cleared to hold substance"),
            rows=(("Screens on this matter, outstanding: "
                   + "; ".join(screens_mod.unscreened(outstanding))),),
            # THE SCREENS THEMSELVES, so the handover can carry them.
            # `rows` is the advocate-facing rendering and cannot be read
            # back as state -- a summary parsing those sentences would be
            # a parser for a format nobody declared.
            screens=outstanding)

    @implements("B6")
    def _screen(self, kind, matter: Matter, turn: TurnInput,
                metrics: TurnMetrics):
        """ONE SCREEN, ANSWERED. BK-34's producers.

        B6 is partial: the capacity branch consumes an explicit attributed
        CapacityPosition, not prose. Decision-specific vulnerability assessment
        and the authoritative DecisionRecord contract remain separate work.

        THE POPULATION IS `ScreenKind`, so a sixth screen added to the
        vocabulary arrives here unanswered and lands NOT_ASSESSED naming
        itself -- rather than silently not existing, which is what five
        hard-coded rows would have done.

        EVERY BRANCH RETURNS A REAL STATE. No path returns `clear` because
        nothing ran: the conflict screen with no parties is NOT_ASSESSED and
        says what it wants, and a released screen carries the release ON it
        rather than instead of the finding.
        """
        from nm.core import conflict as conflict_mod

        answered = (matter.intake_answers or {}).get(kind.value)

        if kind is screens_mod.ScreenKind.CAPACITY:
            return screens_mod.capacity_screen(answered, self._clock())

        if kind is screens_mod.ScreenKind.CONFLICT:
            named = self._parties_of(matter)
            try:
                held = self._store.list_for(matter.advocate_id)
            except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
                metrics.violate("B3", f"the conflict screen could not read "
                                      f"your files: {type(exc).__name__}")
                return screens_mod.Screen(
                    kind=kind, state=screens_mod.ScreenState.NOT_ASSESSED,
                    not_assessed_because=(
                        "your other matters could not be listed, so nothing "
                        "was checked against them"))
            return conflict_mod.screen(named, held, matter.advocate_id)

        if kind is screens_mod.ScreenKind.COMPETENCE:
            return self._competence_screen(matter, turn, metrics)

        if kind is screens_mod.ScreenKind.EMERGENCY:
            from nm.domain.emergency import latest

            declaration = latest(matter.emergencies or (), self._clock())
            if declaration is not None:
                return screens_mod.Screen(
                    kind=kind, state=screens_mod.ScreenState.BLOCKED,
                    detail=declaration.said(self._clock()) +
                    " Request protective_triage explicitly; this does not admit merits.")
            # NOT A MODEL READ, AND THAT IS THE POINT OF WHERE IT SITS.
            # ADMIT-A runs before any substance reaches a provider, so a
            # screen here cannot ask a model without sending the very
            # material the screens exist to hold back. What it CAN do is
            # record whether an emergency has been DECLARED on this matter,
            # which is true and checkable -- and is not a claim that none
            # exists.
            if matter.emergency_because:
                return screens_mod.Screen(
                    kind=kind, state=screens_mod.ScreenState.BLOCKED,
                    detail=(f"an emergency was declared on this matter: "
                            f"{matter.emergency_because}"))
            return screens_mod.Screen(
                kind=kind, state=screens_mod.ScreenState.CLEAR,
                detail=("no emergency has been declared on this matter. If "
                        "liberty or an irreversible deadline is in play, say "
                        "so and I will work that first"))

        # SCOPE: RECORDED BY THE ADVOCATE. Capacity is typed and handled above.
        #
        # The deployment is a controlled roster of practising advocates and
        # the advocate IS the firm, so requiring a second person would stop
        # every matter at intake in a solo practice -- not a stricter
        # product, an unusable one. What makes it honest is that the release
        # is RECORDED with who and when, sits beside the finding rather than
        # deleting it, and has to be given once per matter rather than
        # assumed.
        if kind is screens_mod.ScreenKind.SCOPE:
            return screens_mod.scope_screen(answered, matter.advocate_id, self._clock())
        return screens_mod.Screen(
            kind=kind, state=screens_mod.ScreenState.NOT_ASSESSED,
            not_assessed_because=f"the {kind.value} screen has no current assessment")

    def _competence_screen(self, matter: Matter, turn: TurnInput,
                           metrics: TurnMetrics = None):
        """B4 -- is this matter inside what the corpus can answer for?

        IT DISCLOSES AND NEVER BLOCKS, and that is read off the matrix rather
        than decided here: `G-COMPETENCE` is `Response.DISCLOSE`, scope
        THREAD. A screen whose gate discloses must not be able to stop a turn,
        or the table is telling the advocate one thing while the code does
        another -- which is the exact disagreement `backend/nm/domain/gates.py` was
        written to end.

        IT ALSO MATTERS ON THE MERITS. A coverage gap is OUR gap. Stopping the
        advocate over it teaches them to work around the gate, which is
        G-PROOF's recorded argument about a missing element table and the same
        answer here.

        SO THE STATE IS ALWAYS `CLEAR` AND THE FINDING IS ALWAYS FIRED. The
        screen genuinely ran; what it found goes to the advocate as a gate
        row, which is where §9 requires the third state to be visible -- in
        the OUTPUT, not only in the type. A `CLEAR` screen carrying
        `COVERAGE GAP --` in its detail is not a screen pretending to be
        clean.
        """
        if self._coverage is None:
            detail = ("coverage for this jurisdiction has not been measured "
                      "in this deployment, so I cannot say whether the corpus "
                      "covers it. That is a gap in what I can tell you, not a "
                      "finding that it is covered")
            return screens_mod.Screen(
                kind=screens_mod.ScreenKind.COMPETENCE,
                state=screens_mod.ScreenState.CLEAR,
                detail="NOT MEASURED -- " + detail)

        position = self._coverage.position(turn.jurisdiction)
        name = getattr(getattr(position, "state", None), "value", "")
        # `detail`, NOT `why`. `CoveragePosition` calls it `detail`, and
        # `getattr(position, "why", "")` returned the empty string for every
        # jurisdiction -- a screen reporting a coverage position with no
        # reason in it, which the type would then refuse.
        why = getattr(position, "detail", "") or "no reason was recorded"

        if name == "met":
            return screens_mod.Screen(
                kind=screens_mod.ScreenKind.COMPETENCE,
                state=screens_mod.ScreenState.CLEAR,
                detail=f"{turn.jurisdiction}: {why}")

        # THE PREFIX IS WHAT `gate_for` READS BACK. The screen state is
        # always CLEAR here -- competence discloses and never blocks -- so
        # the finding has to live in the detail, and the gate mapping parses
        # it from there. A prefix nobody wrote would silently become
        # `covered`, which is the one answer this branch must never give.
        return screens_mod.Screen(
            kind=screens_mod.ScreenKind.COMPETENCE,
            state=screens_mod.ScreenState.CLEAR,
            detail=("NOT MEASURED -- " if name in ("not_measured", "")
                    else "COVERAGE GAP -- ") + why)

    def _parties_of(self, matter: Matter):
        """The party set this matter holds, as a `Parties`.

        READ OFF THE FILE, not off this turn. The conflict screen runs in
        ADMIT-A, before this turn's words have been read by anything -- which
        is the whole point of where the screens sit. What it screens is what
        the matter already knows; the intake read adds to that at the end of
        the turn, so a party named today is screened from tomorrow.
        """
        from nm.core import parties as parties_mod

        found = []
        # INTAKE FIRST, then whatever the threads have learned since. Intake
        # is what exists on turn one, and turn one is the turn that most needs
        # screening.
        for name, side in (matter.intake_parties or {}).items():
            found.append(parties_mod.Party(
                name=str(name), side=str(side), why="given at intake"))
        for thread in matter.threads:
            for name, side in (thread.parties or {}).items():
                found.append(parties_mod.Party(
                    name=str(name), side=str(side),
                    why="recorded on the file"))
        if not found:
            return parties_mod.Parties(
                why="no party is recorded on this matter")
        return parties_mod.Parties(
            parties=tuple(found),
            why=f"{len(found)} party(ies) recorded on this matter")

    def _read(self, prompt, schema, key: str, tier=Tier.ROUTINE):
        """Every structured read goes through here. BK-29.

        THE CALL SITE NAMES THE READ AND NOTHING ELSE. It used to name a
        token ceiling too -- sixteen of them, every one hand-picked against
        briefs nobody recorded -- and the dispute read's 200 truncated its
        JSON mid-string at character 827 once it began returning three
        verbatim spans. The read was LOST rather than short, and the turn
        reported one thread on the strength of a parse error.

        THE PROMPT IS BUILT ONCE, which the first version of this sweep got
        wrong: it inlined `ceiling.for_read(key, build_prompt(...))` beside
        the existing `build_prompt(...)` argument, so every read constructed
        its prompt twice. Passing the built prompt through is what makes the
        ceiling derivable without paying for it.

        WHETHER THE CEILING IS DERIVED IS THE READ'S OWN PROPERTY, declared
        in `backend/nm/domain/reads.py` beside the schema's entry. Nothing here
        decides it and no call site can override it.
        """
        prompt = guided(prompt)
        got = self._model.structured(
            prompt, schema, tier,
            max_tokens=ceiling.for_read(key, prompt,
                                        echoes=reads.echoes(key)))
        # AN UNFINISHED ANSWER IS REFUSED HERE, BEFORE ANY LEGAL WORK RESTS ON
        # IT. BK-29-AC2's words are *before dependent legal work is accepted*,
        # and this is the one place every structured read passes through -- so
        # a read added next month is covered without its author knowing this
        # rule exists, which is the only kind of coverage that lasts.
        #
        # It is raised rather than returned so a caller cannot forget to ask.
        # The three states are distinct on the exception's own text: finished,
        # cut off at the budget, and nobody recorded which.
        why = refuse_partial(got.completion, doing=f"the {key} read")
        if why:
            raise OutputTruncated(why)
        return got

    def _load_or_create(self, turn: TurnInput, admitted_snapshot: Matter | None) -> Matter:
        # Work on exactly the version admitted before routing. Reloading here
        # would silently adopt concurrent changes (including another receipt)
        # between the caller's version check and the final compare-and-swap.
        if admitted_snapshot is not None:
            return admitted_snapshot
        # A NAME AN ADVOCATE RECOGNISES, not the first 60 characters.
        #
        # This took `message[:60]`, which cuts mid-word and gives ten
        # recovery matters ten titles that begin "We act for the plaintiff
        # at Hyderabad. Goods were suppl". BK-33's acceptance is that ten
        # similar matters stay distinguishable by who, what and where -- and
        # the opening sentence of a brief is the least distinguishing thing
        # on the file.
        #
        # THE PARTIES ARE THE NAME, when intake has them: `X v Y` is how the
        # matter is listed in every cause list an advocate has ever read.
        # Where it does not, the first sentence is cut ON A WORD BOUNDARY
        # and the intake read fills the name in on the turn that names a
        # party.
        title = _matter_name(turn.message, turn.parties)
        return Matter(id=opening_id(turn.advocate_id, turn.turn_id),
                      advocate_id=turn.advocate_id, title=title)

    @implements("B1")
    def _read_route(self, turn: TurnInput,
                    metrics: TurnMetrics) -> tuple[Route, Mode, str]:
        """Is this a matter? READ, and never counted.

        THE FALLBACK IS `classify_route`, which no longer guesses: with no
        model there is nothing to read the meaning with, so it takes the safe
        direction rather than a word count. Every failure here lands on
        MATTER, because NON_MATTER writes nothing to any file and a matter
        read as a greeting is gone.
        """
        if not turn.message.strip():
            raise TurnRefused("an empty message discloses nothing")

        # THE FILE, WHERE THERE IS ONE. Reading an existing matter writes
        # nothing, so the route can see what the advocate has already said
        # without giving up the property that NON_MATTER creates no file.
        on_file = ""
        if turn.matter_id:
            try:
                existing = self._store.load(turn.matter_id)
            except Exception:  # noqa: BLE001 -- a route must not fail on this
                existing = None
            if existing is not None and existing.advocate_id == turn.advocate_id:
                on_file = matter_memory.build(existing, about=turn.message).as_context()

        try:
            res = self._read(
                      route_reader.build_prompt(turn.message, on_file),
                      route_reader.ROUTE_SCHEMA, "route", Tier.ROUTINE)
            metrics.record_call(res)
            metrics.route_reads += 1
            read = route_reader.interpret(res.data or {})
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"the route could not be read: {exc}")
            return classify_route(turn.message, bool(on_file))
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            metrics.violate("B1", f"route read failed: "
                                  f"{type(exc).__name__}: {exc}")
            return classify_route(turn.message, bool(on_file))

        if not read.examined:
            return classify_route(turn.message, bool(on_file))
        return read.route, read.mode, read.statement

    @implements("C1")
    def _admit_facts(self, matter: Matter, turn: TurnInput,
                     metrics: TurnMetrics) -> tuple[Matter, BindResult]:
        """Take the account, then BIND it -- and keep the two separable.

        The fact is recorded on the matter BEFORE binding is attempted, so an
        account that cannot be placed is still an account that was heard.
        Discarding the turn when binding is ambiguous teaches an advocate to
        re-type what they have already said, and they stop volunteering detail.
        """
        fact = Fact.create(
            statement=turn.message.strip(),
            provenance=Provenance(kind="advocate_statement", turn=turn.turn_id),
            certainty=Certainty.ASSERTED,
        )
        matter = matter.with_fact(fact)
        pending = dispute_reader.pending_accounts(matter, turn.turn_id)
        allocation_text = "\n".join((turn.message, *(f.statement for f in pending)))

        # TWO QUESTIONS, AND THE SECOND ONE HAS NO FILE IN IT.
        #
        # This used to read only when "it can matter", defined as: the
        # matter already has a thread and the message carries no number of
        # record. The justification for the first half was written here --
        # "with no thread yet, there is nothing to confuse it with" -- and
        # it is false. There is: the disputes inside the message, with each
        # other. A brief opening `first ... second ... third ...` got one
        # thread, one posture and one limitation across all three, and the
        # advocate was told every deadline on the file had passed while a
        # trespass five days old sat in it.
        #
        # So the read runs whenever EITHER question is live, and is skipped
        # only when a number of record decides the binding on a matter that
        # already has threads. That is one extra call on a first turn.
        read = dispute_reader.UNREAD
        read = self._read_dispute(matter, turn, metrics)
        if read.refused:
            return matter, BindResult(
                state=BindState.UNBINDABLE, thread=None, created=False,
                reason="the full dispute inventory could not be established",
                question=("I have kept your full instructions, but could not reliably "
                          "separate all the disputes and their shared instructions. "
                          "I have not treated a partial reading as the whole matter."))
        opens = True if read.opens else (False if read.continues else None)
        focus = turn.thread_id or read.focus_thread_id
        if read.advance and not focus and not read.described:
            focus = dispute_agenda.project(
                matter, after_thread_id=dispute_agenda.last_focus(matter))["next_thread_id"]
            if focus is None:
                return matter, BindResult(
                    state=BindState.UNBINDABLE, thread=None, created=False,
                    reason="no other dispute available for automatic review",
                    question="There is no other dispute ready to work through. Outstanding "
                             "questions remain on the board; the matter has not been closed.",
                    counted=read is not dispute_reader.UNREAD)
        bound = bind(matter, allocation_text, fact, thread_hint=focus,
                     opens_new_dispute=opens, described=read.described)
        # WHETHER ANYONE COUNTED, carried out of the only place that knows.
        bound = replace(bound, counted=read is not dispute_reader.UNREAD)
        if bound.state is not BindState.BOUND or bound.thread is None:
            return matter, bound
        if (read.advance or read.focus_thread_id) and not read.described:
            return matter, replace(bound, allocations=((bound.thread.id, ()),))
        if bound.allocations:
            records = {t.id: t for t in (bound.thread, *bound.others)}
            for tid, spans in bound.allocations:
                thread = records[tid]
                matter = matter.with_thread(thread)
                if not spans:
                    continue
                # Retain exact evidence spans separately; the whole incoming
                # account remains on the matter, outside every scoped chart.
                ids = []
                for span in spans:
                    origin = (turn.turn_id if span in turn.message else
                              next(f.provenance.turn for f in pending if span in f.statement))
                    scoped_fact = Fact.create(statement=span, provenance=Provenance(
                        kind="advocate_statement", turn=origin, span=span),
                        certainty=Certainty.ASSERTED)
                    matter, scoped_fact = matter.recording(scoped_fact)
                    ids.append(scoped_fact.id)
                thread = replace(
                    thread, chronology=tuple(dict.fromkeys((*thread.chronology, *ids))),
                    assessed=tuple(a for a in thread.assessed if a != "review_current"))
                matter = matter.with_thread(thread)
                scoped_turn = replace(turn, message="\n".join(spans))
                matter, updated = self._admit_thread(matter, scoped_turn, metrics,
                                                   replace(bound, thread=thread),
                                                   next(f for f in matter.facts if f.id == ids[0]))
                records[tid] = updated.thread
            matter = requirements.apply_answers(matter, read.requirement_answers,
                message=turn.message, turn_id=turn.turn_id, today=turn.today)
            return matter, replace(bound, thread=matter.thread(bound.thread.id),
                                   others=tuple(matter.thread(t.id) for t in bound.others))
        matter, bound = self._admit_thread(matter, turn, metrics, bound, fact)
        matter = requirements.apply_answers(matter, read.requirement_answers,
            message=turn.message, turn_id=turn.turn_id, today=turn.today)
        return matter, replace(bound, thread=matter.thread(bound.thread.id))

    def _admit_thread(self, matter, turn, metrics, bound, fact):
        """Read one scoped account; other disputes keep their own evidence."""
        thread = bound.thread
        thread = replace(
            thread, assessed=tuple(a for a in thread.assessed if a != "review_current"))
        posture: Posture = thread.posture
        # ONLY WHILE UNRESOLVED. Once the advocate has settled it, no further
        # call is made -- the extraction is cheap but it is not free, and a
        # settled posture is not re-read on every later turn.
        # C5. THE CHART IS BUILT BEFORE ANY OPINION ON THIS THREAD, so the
        # read happens here in ADMIT rather than in DERIVE where a gate
        # could skip it. The account fact above is kept WHOLE -- C1 takes
        # the account before clarifying anything -- and these are derived
        # from it, each carrying the span it was read from.
        # WHAT IS ALREADY THERE, captured BEFORE the read rather than after.
        # The date read is now the correction read, so it needs the ids in
        # front of it to name one.
        existing = chronology.chart(matter.facts, thread.chronology)
        dated = self._read_dates(turn, matter, thread, metrics, existing)

        ids = [fact.id]
        added: list[Fact] = []
        for row in dated:
            if not row.dated:
                continue
            event = Fact.create(
                statement=row.event,
                provenance=Provenance(kind="advocate_statement",
                                      turn=turn.turn_id,
                                      span=row.date_expression),
                certainty=row.certainty, date=row.on)
            # B-107. `recording` DECIDES WHETHER THIS IS A SECOND FACT and
            # returns the one that is now on the file -- which is this event
            # when the sentence is new, and the AMENDED account fact when the
            # date read has restated the whole message. One sentence was
            # becoming two entries: the account undated and the reading dated,
            # both charged to the account budget and both read by limitation.
            matter, event = matter.recording(event)
            # DEDUPED SEPARATELY, and not by folding the two lists together:
            # the account fact's id is already in `ids`, so an amended one
            # would never reach `added` -- and `added` is what the correction
            # question below subtracts to find the entries that were ALREADY
            # on the file. It would then offer the advocate this turn's own
            # sentence as the thing their correction might have replaced.
            if event.id not in {e.id for e in added}:
                added.append(event)
            if event.id not in ids:
                ids.append(event.id)

            # THE ROW SAYS WHAT IT REPLACES, so nothing has to rebuild the
            # relationship afterwards. `interpret` has already dropped an id
            # the file does not hold.
            if row.corrects and row.corrects != event.id:
                superseded = next(
                    (f for f in matter.facts if f.id == row.corrects), None)
                if superseded is not None and superseded.superseded_by is None:
                    metrics.fire("G-CORRECTION", "superseded",
                                 f"{row.corrects} replaced by {event.id}")
                    # THROUGH THE ONE OWNER OF THE LINK. The case-file
                    # correction route (P18) supersedes the same way, so a
                    # spoken correction and a typed one leave the same record.
                    matter = matter.superseding(superseded.id, event.id)

        thread = replace(thread, chronology=thread.chronology + tuple(ids))
        matter = matter.with_thread(thread)

        # B-088. THE READ SAID NOTHING AND THE ADVOCATE SAID "THAT IS WRONG".
        #
        # The correction read is not reliable at the routine tier: it fires on
        # one run and returns nothing on the next, on identical input. No
        # prompt fixes that. What can be fixed is that a miss was SILENT —
        # both dates stayed on the chart, the period ran from the earlier, and
        # the answer was confidently about a date they had withdrawn.
        #
        # So a miss becomes a QUESTION with both dates in it. The phrase list
        # detects that a correction is being attempted and decides nothing:
        # where the read has already named an entry this is quiet, and where
        # it has not, four words from the advocate settle what no amount of
        # scoring could.
        phrase = chronology.looks_like_a_correction(turn.message)
        if phrase and added and not any(r.corrects for r in dated):
            live = chronology.chart(matter.facts, thread.chronology)
            others = [f for f in live
                      if f.date is not None
                      and f.id not in {e.id for e in added}]
            if others:
                metrics.fire("G-CORRECTION", "not_assessed",
                             f"the advocate said {phrase!r} and no entry was "
                             f"named as replaced")
                matter = matter.asking(
                    "G-CORRECTION",
                    (f"You said {in_prose(phrase)}. I have not taken anything as "
                     f"replaced, so both are still on the file: "
                     + "; ".join(f"{snippet(f.statement, 44)} ({f.date.isoformat()})"
                                 for f in [*others, *added]
                                 if f.date is not None)
                     + ". Which one is right?"),
                    turn.turn_id, thread.id)


        if not posture.resolved or posture_reader.speaks_of_the_representation(turn.message):
            # THE WHOLE FILE, not just this message and not just the
            # narrative. What was already established, what has already
            # been asked, and what came back -- so an advocate who
            # answered on turn 2 is not asked again on turn 3.
            memory = matter_memory.build(
                matter, thread.id, about=turn.message,
                load_bearing=self._load_bearing(matter, thread))
            stated = self._read_posture(turn, metrics, memory, thread_label=thread.label,
                                       opponent=posture.opponent or "")
            if stated.settles_role:
                posture = posture.enrich(stated.role, stated.basis,
                                         source_fact=fact.id)
                if stated.basis is Basis.INFERRED:
                    # DISCLOSED, not hidden. The client was stated; the
                    # procedural role was read off the account, and the
                    # advocate can correct it in a word.
                    metrics.violate(
                        "C3", f"role {stated.role.value!r} inferred from the "
                              f"account and the stated client, not named: "
                              f"{snippet(stated.quoted, 60)!r}")
            # A BETTER DESCRIPTOR REPLACES A WEAKER ONE.
            #
            # This was write-once, and the first descriptor won forever.
            # Turn 1 gave "our client", turn 2 gave "payee", and the second
            # was thrown away -- so the narrowed question kept asking about
            # "the our client" while the advocate had already named them.
            #
            # Monotonic enrichment is right for the ROLE, because a stated
            # posture silently flipping is the turn-5 reversal. A descriptor
            # is not a decision anyone acts on; it is a label, and a later
            # more specific one is better information.
            if stated.client_described_as:
                posture = replace(
                    posture, client_described_as=stated.client_described_as)

            # THE OPPONENT, and MONOTONIC unlike the descriptor above.
            #
            # A descriptor is a label and a later, more specific one is better
            # information. The opponent is a party: one that changed silently
            # between turns would be the turn-5 reversal wearing a different
            # hat, so the first name recorded stands until the advocate
            # corrects it -- which is the correction path, not this one.
            if stated.opponent and not posture.opponent:
                posture = replace(posture, opponent=stated.opponent)
            elif (stated.opponent and stated.opponent != posture.opponent
                  and stated.opponent_correction_quote
                  and posture.opponent.casefold() in stated.opponent_correction_quote.casefold()):
                # Explicit current correction, never a silent flip from a new read.
                # The original words and prior posture remain in saved history.
                metrics.fire("G-CORRECTION", "superseded", "opponent expressly corrected")
                posture = replace(posture, opponent=stated.opponent, source_fact=fact.id)

            # THE CLIENT IS KNOWN AND THE ROLE IS NOT. Ask the one question,
            # once. The five-field extraction answers `not_stated` here
            # every time -- measured on five scenarios -- because in a
            # schema of five fields it is an answer that is never wrong.
            # Asked on its own the same model got all five right.
            #
            # C3 is untouched: the advocate has SAID who they act for, so
            # nothing is being inferred about the client. What is worked out
            # is the procedural label for a client already identified, it is
            # marked INFERRED, and it is correctable in a word.
            said = memory.advocate_words if memory else turn.message
            if not posture.resolved and (
                    posture.client_described_as
                    or posture_reader.speaks_of_the_representation(said)):
                # EITHER a label for the client, OR the advocate speaking in
                # the first person about their own side. The second is the
                # commoner case and it was not covered: "we want to file a
                # title suit" states who moves and offers no label, so five
                # turns blocked on a question the advocate had answered on
                # turn two.
                role, why = self._read_role(
                    posture.client_described_as or "", memory, metrics)
                if role is not None:
                    posture = posture.enrich(role, Basis.INFERRED,
                                             source_fact=fact.id)
                    metrics.violate(
                        "C3", f"role {role.value!r} inferred from the account "
                              f"and the stated client "
                              f"({posture.client_described_as!r}): {snippet(why, 90)}")

        thread = replace(thread, posture=posture)
        matter = matter.with_thread(thread)
        # THE OTHER DISPUTES GO ON THE FILE TOO. They carry no posture and
        # no chronology -- nothing has been read for them and inventing
        # either would be the merge defect with extra rows -- but they
        # EXIST, and the advocate can name one and be advised on it.
        return matter, replace(bound, thread=thread)

    @implements("D4")
    def _read_cause(self, turn: TurnInput, memory, metrics: TurnMetrics,
                    grounds: list[Element], *, thread_label: str = "") -> str | None:
        """H3. Which cause of action, so the Article can be LOOKED UP.

        `None` on any doubt, and `None` is cheap: retrieval falls through to
        the keyword resolver and then to search, which answers with a
        confidence and as a candidate. A cause read WRONGLY is not cheap — it
        sends an exact lookup into the wrong Article and produces a limitation
        date with real text behind it that governs a different suit.

        THE REFUSAL IS DISCLOSED, not swallowed. A cause this product declined
        to read is one the advocate can supply in four words, and silence would
        have them believe it was never in question.
        """
        # ONE VALUE TO THE PROMPT AND TO THE GUARD (B-108). The rendered
        # account is CONTEXT -- its `[1984-04-15]` stamps and notes are
        # ours, not the advocate's -- and `advocate_words` is what may
        # be quoted. Passing the two separately is how they drifted.
        #
        # THE NOTES AND NOT THE WHOLE RENDERING (B-115). A date stamp does
        # not decide WHICH CAUSE OF ACTION a claim is, so handing this read
        # the account beside the same sentences clean was paying for them
        # twice. The notes are what the rendering adds that this read could
        # use -- that the basis is unassessed, that earlier statements were
        # left out -- and they carry no sentences at all.
        quotable = Quotable(
            turn=turn.message,
            file=memory.advocate_words if memory else "",
            context=(f"Active working dispute: {thread_label}. Read the cause for this "
                     "dispute only. References distinguishing other disputes do not make "
                     "their causes applicable here.\n" if thread_label else "")
                    + (memory.notes if memory else ""),
            context_is="notes this product wrote about the file")
        try:
            res = self._read(
                      cause_reader.build_prompt(quotable),
                      cause_reader.CAUSE_SCHEMA, "cause", Tier.ROUTINE)
            metrics.record_call(res)
            metrics.cause_reads += 1
            read = cause_reader.interpret(quotable, res.data or {})
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"the cause of action could not be read: {exc}")
            return None
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            metrics.violate("D4", f"cause read failed: "
                                  f"{type(exc).__name__}: {exc}")
            return None

        if read.refused:
            metrics.violate("D4", f"cause not taken: {read.refused}")
            grounds.append(Element(
                kind=ElementKind.GROUND, disclosure=True,
                text=(f"I did not settle what cause of action this is, so I "
                      f"have not looked up a limitation Article for it: "
                      f"{read.refused}")))
            return None
        return read.cause.value if read.resolved else None

    @implements("C5")
    def _read_parties(self, turn: TurnInput, memory, matter: Matter,
                      metrics: TurnMetrics, grounds: list[Element]) -> Matter:
        """WHO THE BRIEF NAMES, onto the matter. BK-34.

        RETURNS THE MATTER rather than a party set, because what it produces
        is a change to the file: the conflict screen reads
        `Matter.intake_parties`, and a read whose answer lived only in this
        turn would screen nothing on the next one.

        IT ADDS AND NEVER REPLACES. An advocate who names the guarantor on
        turn six has added a party, not corrected the two from turn one, and
        a read that overwrote would silently narrow the set the screen covers
        -- which `Screen.stale_for` would then report as a clearance that no
        longer applies, one turn too late to be useful.
        """
        from nm.core import parties as parties_mod

        # NO NOTES ON THIS READ, and that is a decision rather than an
        # omission. The notes are this product's own rendering -- date
        # stamps, internal identifiers, sentences we wrote -- and none of it
        # is quotable, so a name found there would be dropped by the guard
        # anyway. Taking them would spend budget to be refused, and would
        # make this a fourth read in a trade `test_one_quotable` exists to
        # keep at three.
        quotable = Quotable(
            turn=turn.message,
            file=memory.advocate_words if memory else "")
        try:
            res = self._read(
                      parties_mod.build_prompt(quotable),
                      parties_mod.PARTIES_SCHEMA, "parties", Tier.ROUTINE)
            metrics.record_call(res)
            read = parties_mod.interpret(quotable, res.data or {})
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"the parties could not be read: {exc}")
            return matter
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            metrics.violate("B3", f"parties read failed: "
                                  f"{type(exc).__name__}: {exc}")
            return matter

        if read.refused:
            # NAMED, NOT SWALLOWED. A dropped name is a party the conflict
            # screen will not cover, and the advocate is the only one who can
            # put it back.
            grounds.append(Element(
                kind=ElementKind.GROUND, disclosure=True,
                text=(f"I did not record every name for the conflict check: "
                      f"{read.refused}. Say them again and I will add them")))
        if not read.named:
            return matter
        widened = replace(matter, intake_parties={
            **(matter.intake_parties or {}),
            **{p.name: p.side for p in read.parties},
        })

        # BK-34. A CLEARANCE IS BOUND TO THE SET IT SCREENED, and this turn
        # has just widened the set.
        #
        # `Screen.stale_for` has answered exactly this question since B3
        # landed, and NOTHING CALLED IT. One caller in the whole product and
        # it was a unit test. So an advocate who named a guarantor on turn six
        # was shown the conflict clearance from turn one -- which had never
        # seen that name -- and nothing anywhere said so.
        #
        # THE SCREEN CANNOT RUN ON THIS TURN, AND THAT IS NOT THE DEFECT. It
        # sits in ADMIT-A, before this turn's words are read by anything, so a
        # party named today is screened from tomorrow. That is deliberate:
        # screening it today would mean admitting the brief first, which is
        # what B3 forbids. What was missing is that the advocate was never
        # told the clearance in front of them did not cover the name they had
        # just given.
        #
        # `.clears` RATHER THAN `state is CLEAR`, because that comparison
        # written at a call site is the second copy `Screen.clears` exists to
        # refuse. And a NOT_ASSESSED screen is not a stale clearance -- it is
        # a screen that has not run, which its own row already says.
        conflict = next(
            (s for s in (matter.screens or ())
             if getattr(s, "kind", None) is screens_mod.ScreenKind.CONFLICT),
            None)
        if conflict is not None and conflict.clears:
            widened_names = self._parties_of(widened).names
            if conflict.stale_for(widened_names):
                # ASKED, NOT COMPUTED. `parties - covers` written here would
                # be a second copy of a rule that already has an owner, and
                # `_parties_of` normalises, so the two would drift and the
                # staleness check would silently stop matching.
                # KEYS OUT, NAMES IN. `uncovered` answers WHICH parties in
                # the key vocabulary the clearance never covered; the sentence
                # below is read by a person, so each key is put back into the
                # advocate's own spelling. See `Parties.display_for`.
                known = self._parties_of(widened)
                fresh = tuple(known.display_for(key)
                              for key in conflict.uncovered(widened_names))
                grounds.append(Element(
                    kind=ElementKind.GROUND, disclosure=True,
                    text=(f"The conflict check on this turn covered the "
                          f"parties already on the file. It did not cover "
                          f"{', '.join(fresh)}, named just now -- that runs "
                          f"on your next turn")))
        return widened

    def _read_dates(self, turn: TurnInput, matter: Matter, thread: Thread,
                    metrics: TurnMetrics, existing: tuple = ()):
        """The events in this message, with their dates where dates exist.

        A failed read yields NO ROWS, never a dated one. The asymmetry is the
        point: an event missing from the chart costs a question, and an event
        wrongly dated costs a limitation calculation the advocate acts on
        without knowing it was invented.
        """
        # THE FILE IS CONTEXT ON THIS READ AND ONLY THIS TURN IS
        # QUOTABLE, which is what the guard has always enforced: a date
        # expression read out of the file would re-date an entry the
        # chart already holds. Measured: 13 of the 14 spans in this
        # prompt were shown and unquotable, with nothing marking them.
        quotable = Quotable(
            turn=turn.message,
            context="\n".join(f.statement for f in matter.facts
                              if f.id in set(thread.chronology)))
        try:
            res = self._read(
                      chronology.build_prompt(quotable, turn.today, existing),
                      chronology.DATE_SCHEMA, "dates", Tier.ROUTINE)
            metrics.record_call(res)
            metrics.chronology_reads += 1
            rows = chronology.interpret(
                quotable, turn.today, res.data or {},
                known=frozenset(f.id for f in existing))
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"the date chart could not be read: {exc}")
            return ()
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            metrics.violate("C5", f"date read failed: "
                                  f"{type(exc).__name__}: {exc}")
            return ()

        for row in rows:
            if row.refused:
                # REFUSED IS DISCLOSED. A date this product declined to read is
                # one the advocate can supply in four words, and silence would
                # have them believe it was never given.
                metrics.violate("C5", f"date not taken for "
                                      f"{snippet(row.event, 40)!r}: {row.refused}")
        return rows

    @implements("C4")
    def _read_dispute(self, matter: Matter, turn: TurnInput,
                      metrics: TurnMetrics) -> "dispute_reader.DisputeRead":
        """Two answers: does this continue the file, and how many disputes
        does it describe?

        RETURNS THE READ, NOT A BOOLEAN. It used to return `bool | None`,
        which could carry the first answer and had nowhere to put the
        second. A failed read carries an explicit refusal so it cannot
        fall back to inventing one dispute from an unread multi-dispute brief.
        """
        on_file = (dispute_agenda.context(matter) + "\nExisting checklist items:\n"
                   + requirements.answer_context(matter))
        # OPENING A THREAD CARRIES THE EVIDENCE, so only this turn is
        # quotable: a span lifted out of the thread list would let an
        # old dispute open a new thread.
        quotable = Quotable(turn=turn.message,
                            file="\n".join(f.statement for f in
                                           dispute_reader.pending_accounts(matter, turn.turn_id)),
                            context=on_file,
                            context_is="the list of threads already open "
                                       "on this matter, as we labelled them")
        repair_attempted = False
        try:
            res = self._read(
                      dispute_reader.build_prompt(quotable),
                      dispute_reader.schema_for(
                          quotable,
                          thread_ids=frozenset(t.id for t in matter.threads)),
                      "dispute", Tier.ROUTINE)
            metrics.record_call(res)
            metrics.binding_reads += 1
            read = dispute_reader.interpret(quotable, res.data or {},
                                            thread_ids=frozenset(t.id for t in matter.threads))
            missing = dispute_reader.uncovered_paragraphs(quotable.words, read)
            if read.refused or missing:
                repair_attempted = True
                # One bounded repair of the same contract. No scenario keywords,
                # invented inventory, dropped quote guard or unlimited retry.
                prompt = dispute_reader.build_prompt(quotable)
                # THE REPAIR HAS TO MATCH THE FAULT, and there are two.
                #
                # `fixed_allocation_repair` builds its table FROM THE FIRST
                # ANSWER'S ROWS and hands the model an enum over their indices.
                # That is the right tool when the inventory is complete and the
                # LINKING is wrong -- an index out of range, a verdict that
                # under-claims -- because the rows are already correct and only
                # need pinning.
                #
                # IT CANNOT ADD A DISPUTE THE FIRST ANSWER OMITTED. Its table
                # has no row for one, and its enum cannot name what is not in
                # the table. So where paragraphs went UNALLOCATED -- the reader
                # stopped at the final subject and missed the others, which is
                # the failure `uncovered_paragraphs` exists to catch -- the
                # constrained schema makes recovery impossible, and the open
                # one is what lets the model return a fuller inventory.
                #
                # Diagnosed once, here, rather than by each repair guessing.
                fixed = (None if missing else dispute_reader.fixed_allocation_repair(
                    quotable, res.data or {}, matter.threads))
                feedback = ("Your previous inventory was incomplete or unsupported. "
                            "Re-read the WHOLE message, not just its final subject. "
                            "Return the full corrected inventory, including shared "
                            "representation and task instructions on EACH affected dispute. "
                            "Check that independently contested rights and chronologies have "
                            "not been merged merely because parties or property overlap. "
                            "Every quotation "
                            "must remain literal; prefer source-unit IDs. "
                            f"Validation: {read.refused or 'unallocated paragraphs'}. "
                            "\nUnallocated paragraphs:\n"
                            + "\n\n".join(missing))
                if fixed:
                    prompt, repair_schema, table = fixed
                else:
                    repair_schema = dispute_reader.schema_for(
                        quotable,
                        thread_ids=frozenset(t.id for t in matter.threads))
                repaired = self._read(replace(prompt, user=prompt.user + "\n\n" + feedback),
                    repair_schema, "dispute", Tier.ROUTINE)
                metrics.record_call(repaired)
                metrics.binding_reads += 1
                repair_data = (dispute_reader.apply_fixed_allocation(
                    res.data or {}, repaired.data or {}, table) if fixed else repaired.data or {})
                read = dispute_reader.interpret(quotable, repair_data,
                    thread_ids=frozenset(t.id for t in matter.threads))
                if dispute_reader.uncovered_paragraphs(quotable.words, read):
                    read = replace(read, refused="paragraphs were omitted "
                                                   "from the dispute inventory")
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"the dispute read could not run: {exc}")
            return replace(dispute_reader.UNREAD, refused=(
                "the incomplete inventory could not be repaired" if repair_attempted
                else "the dispute inventory could not be read"))
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            metrics.violate("C4", f"dispute read failed: "
                                  f"{type(exc).__name__}: {exc}")
            return replace(dispute_reader.UNREAD, refused=(
                "the incomplete inventory could not be repaired" if repair_attempted
                else "the dispute inventory could not be read"))

        if read.refused:
            metrics.violate("C4", f"dispute read refused: {read.refused}")
            return read
        if read.opens:
            # DISCLOSED. A split is the recoverable direction, but it is
            # still a decision about the advocate's file and they can see it.
            metrics.violate(
                "C4", f"read as a NEW dispute on {snippet(read.quoted, 50)!r}: "
                      f"{snippet(read.why, 90)}")
        if len(read.described) > 1:
            metrics.violate(
                "C4", f"this message describes {len(read.described)} disputes: "
                      + "; ".join(d.label for d in read.described[:6]))
        return read

    @implements("C3")
    def _read_role(self, described: str, memory, metrics: TurnMetrics):
        """Which procedural role a NAMED client occupies. Never who they are.

        Failing to read it leaves posture unresolved and blocking, exactly
        as failing to read the posture does. A role that could not be read
        must never look like a role that was.
        """
        try:
            res = self._read(
                      posture_reader.build_role_prompt(
                    described, memory.advocate_words if memory else ""),
                      posture_reader.ROLE_SCHEMA, "role", Tier.ROUTINE)
            metrics.record_call(res)
            metrics.posture_reads += 1
            return posture_reader.interpret_role(res.data or {})
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"the role could not be read: {exc}")
            return None, str(exc)
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            # A programming error here must not read as "the model could not
            # tell". A broad except that logs a warning once made a NameError
            # look like a model failure and suppressed a whole feature.
            metrics.violate("C3", f"role extraction failed: "
                                  f"{type(exc).__name__}: {exc}")
            return None, f"{type(exc).__name__}: {exc}"

    def _derive(self, thread: Thread, turn: TurnInput,
                metrics: TurnMetrics,
                memory: "matter_memory.MatterSummary | None" = None,
                *, side_blind: bool = False,
                parties: frozenset[str] = frozenset(),
                blocked: bool = False,
                facts: tuple[Fact, ...] = (),
                matter_id: str = "",
                seed: tuple[Finding, ...] = (),
                concluded: dict | None = None,
                paused: frozenset[str] = frozenset(),
                response_mode: Mode = Mode.SHORT_QUESTION,
                ) -> tuple[list[Element], tuple, tuple, tuple]:
        """Retrieve, then assemble. Returns (elements, relied_on, retrieved).

        `blocked` is whether this turn's answer will be REFUSED. It is a
        different question from `side_blind` and they were conflated once in
        each direction: a blocked turn may spend only what settles the gate,
        because nothing it derives is shown, while a side-blind turn that is
        still served may derive anything that does not depend on the side.
        The caller knows both and passes both rather than either standing in
        for the other.

        `side_blind` is the posture gate holding. It permits exactly what
        does not depend on which side we are on -- the text of a provision,
        which is the legislature's words and identical for both parties --
        and refuses the two things that do:

          * THE RECOMMENDATION, which is a directive step by construction
          * THE AUTHORITY SET, because which judgments come back is a
            function of how the question was framed. Presenting a
            side-flavoured selection as "the law" with no posture on record
            is a subtler form of the defect the gate exists for, and it is
            the one that would be hardest to notice.

        The two Finding tuples are returned SEPARATELY because the grounding
        gate treats them differently: what the answer rests on can withhold the
        turn, and what merely came back cannot. Collapsing them would either
        punish the product for disclosing an unusable source, or let an
        unusable source ground an answer.
        """
        # WHAT THIS DERIVATION CONCLUDED, for the caller to persist. A dict
        # rather than a return value because Phase 1 adds issues, proof and
        # the rest to it, and a five-tuple that grows to nine is a signature
        # nobody reads.
        if concluded is None:
            concluded = {}
        elements: list[Element] = []
        retrieved: list[Finding] = []
        relied_on: list[Finding] = []
        grounds: list[Element] = []
        # A3 §5.1. THE GAP QUEUE, filled during derivation and drained at the
        # end. Questions emitted where they are DETECTED arrive in the order
        # the code happens to be written in; a senior asks the one that
        # matters most next, which cannot be decided until they are all in.
        gaps: list[gap_queue.Gap] = []

        # WHAT THIS TURN DERIVED, recorded as it happens.
        #
        # A row is appended only where something was actually produced, and
        # the ABSENCE of a row is the signal: a read that found three issues
        # on turn 2 and nothing on turn 9 leaves no row, and `cascade.lost`
        # reports it. Recording a row with a count of zero would make
        # forgetting look like an ordinary value.
        derived: list[cascade.Derived] = []

        cause_read = self._read_cause(turn, memory, metrics, grounds, thread_label=thread.label)
        need = EvidenceNeed(question=turn.message.strip(),
                            governing_date=turn.today,
                            jurisdiction=turn.jurisdiction,
                            # THE SAME DEFECT POSTURE HAD, in retrieval.
                            # An advocate names the Act on turn 1 and asks
                            # "and the limitation?" on turn 4; reading turn
                            # 4 alone, this found no Act at all and reported
                            # a corpus gap for a provision it had already
                            # retrieved. Second-chance input only -- see
                            # EvidenceNeed.account.
                            account=memory.account if memory else "",
                            # H3 — WHAT THE CAUSE IS, so a determinate question
                            # can be resolved rather than ranked. The field
                            # existed on this type since slice 2 and nothing
                            # ever set it; the graph that reads it is slice 5.
                            #
                            # READ ONCE AND PASSED. D5's element list is chosen
                            # by the same cause, and a second read of one
                            # question on one turn is two answers that can
                            # disagree -- at model prices, with the downstream
                            # one recorded nowhere.
                            cause_of_action=cause_read,
                            # Carried into every fetch made from this need,
                            # the investigation lane's included, so no search
                            # spends a slot on this matter's own parties.
                            parties=parties)
        result = self._fetch(need, metrics)
        # B-104. A PROVISION THE LAST PASS NAMED AND THIS ONE WAS GIVEN.
        #
        # Seeded in FRONT of the fetch so every derivation below sees it
        # exactly as though it had been retrieved by the ordinary query --
        # which is the point. The failure being fixed is an answer written
        # without a provision it went on to cite; handing the text to the
        # reads that write the answer is the only thing that makes the second
        # attempt different from the first.
        if seed:
            result = replace(result, findings=tuple(seed) + tuple(result.findings))
        retrieved.extend(result.findings)
        self._read_coverage(result, thread, metrics, grounds, relied_on,
                            turn, concluded)

        if not side_blind:
            self._investigate(turn, thread, need, result, metrics, grounds,
                              relied_on, retrieved, concluded)

        # D1. THE THRESHOLD MAP, BEFORE THE MERITS. A threshold disposes of a
        # claim without reaching them, so an hour on the theory of a suit that
        # cannot be maintained is an hour spent twice.
        #
        # NOT UNDER THE POSTURE GATE, because "is this claim in time" is asked
        # of a SIDE: whose limitation, ours or theirs, is not answerable while
        # the side is unknown, and answering it for a guessed side is the
        # defect G-POSTURE exists for.
        register: tuple[deadlines.Deadline, ...] | None = None
        position: limitation.Limitation | None = None
        if not side_blind:
            rows, register, position = self._thresholds(
                thread, turn, result, metrics, facts, concluded,
                cause_read)
            grounds.extend(rows)

            # D9 -- THE ISSUES, AFTER the thresholds and never before them.
            # A threshold disposes of a claim without reaching the merits, so
            # an issue list read first invites an hour on the theory of a suit
            # that cannot be maintained.
            issues_out = self._issues(turn, thread, memory, metrics,
                                      concluded)
            grounds.extend(issues_out)
            # WHAT THE THREAD HOLDS, NOT WHAT THIS TURN RENDERED (BK-5).
            # The list is merged and carried, so a turn that shows nothing new
            # has still derived everything on it -- and counting the rendering
            # made the cascade report a loss on an ordinary turn.
            _record(derived, "issues", thread, thread.chronology,
                    len(concluded.get("issues", thread.issues)))

            # D5 -- WHAT HAS TO BE PROVED, AND WHAT THE FILE CAN DO ABOUT
            # IT. Between the issues and the inventory, and that order is the
            # inventory's own argument turned into a sequence: an inventory is
            # only readable against what has to be proved, so what has to be
            # proved is worked out first.
            proof_out = self._proof(turn, thread, memory, metrics,
                                    cause_read, concluded)
            grounds.extend(proof_out)
            _record(derived, "proof", thread, thread.chronology,
                    len(concluded.get("proof", thread.proof)))

            # C7 -- WHAT THE EVIDENCE IS AND WHO HAS IT. After the issues,
            # because an inventory is only readable against what has to be
            # proved.
            inventory_out = self._inventory(
                turn, thread, memory, metrics, gaps, concluded)
            grounds.extend(inventory_out)
            # MEASURED HERE FIRST. GS-14 turn 3: the inventory held TWO
            # items, rendered ZERO findings because B-120 renders only what
            # changed, and the cascade announced "evidence was 2 and is not
            # computed now" -- one line above the answer's own "2 item(s)
            # already on the file are unchanged and not repeated here."
            _record(derived, "evidence", thread, thread.chronology,
                    len(concluded.get("evidence", thread.evidence)))

            # D6 -- THE SPINE, LAST, because it is what the issues and the
            # evidence hang off. S8's whole point: stop producing a list of
            # issues and produce a spine with the issues hanging off it.
            theory_out = self._theory(turn, thread, memory, metrics, facts,
                                      concluded, sources=tuple(retrieved))
            grounds.extend(theory_out)
            # THE HELD THEORY, for the same reason. It happens to be
            # rendered on every turn today, so this changes nothing now --
            # and a turn whose theory read fails while the standing theory is
            # carried would otherwise report the spine LOST, which is the
            # loudest thing the cascade can say.
            _record(derived, "theory", thread, thread.chronology,
                    1 if concluded.get("theory", thread.theory) else 0)

            # D7 -- THE OTHER SIDE'S CASE, at its strongest. After the theory,
            # because an attack is read against a spine: "they will say X" is
            # only useful once there is something for X to be against.
            attacks_out = self._attacks(turn, thread, memory, metrics,
                                       sources=tuple(retrieved))
            grounds.extend(attacks_out)
            _record(derived, "the opponent's case", thread, thread.chronology,
                    sum(1 for e in attacks_out
                        if e.feature == "D7" and not e.disclosure))

        if metrics.evidence_bound_hit:
            # THE BOUND PRODUCES A VISIBLE GAP, never a quiet stop. A turn that
            # ran out of rounds and said nothing is indistinguishable from one
            # that found everything it needed -- and the advocate would read it
            # as the second.
            grounds.append(Element(
                kind=ElementKind.GROUND, thread=thread.id,
                text=(f"I stopped after {MAX_EVIDENCE_ROUNDS} rounds of "
                      f"retrieval on this turn. What I have is what is below; "
                      f"there may be more that I did not reach, and I am "
                      f"telling you rather than answering as though there "
                      f"were not."),
                disclosure=True))

        # BK-70. THE RELIEF POSITION, before the recommendation, because the
        # recommendation is composed against it and checked against it. Under
        # the posture gate for the same reason limitation is: whether the
        # relief serves the objective is asked of a SIDE.
        relief_pos = None
        if not side_blind:
            relief_pos = self._relief(turn, thread, metrics, concluded, position)
            if relief_pos is not None:
                metrics.fire("G-REMEDY", relief_mod.gate_state(relief_pos),
                             relief_mod.disclosure(relief_pos) or "relief assessed")
                disc = relief_mod.disclosure(relief_pos)
                if disc:
                    # ENGINE-COMPOSED FROM TYPED FACTS, so `disclosure=True`:
                    # the enforceability basis is the product's own account of
                    # what it worked out, never a model assertion about the law.
                    grounds.append(Element(
                        kind=ElementKind.GROUND, thread=thread.id,
                        text=disc, disclosure=True))

        # Source-derived requirements are available to this turn's response,
        # not discovered after the model has already asked its questions.
        #
        # AND THEY RUN WHILE THE POSTURE GATE HOLDS, because what the retrieved
        # law REQUIRES is the same on either side -- the section's own words do
        # not change according to whom we act for. G-POSTURE's visible text
        # already draws that line: "I will still read back what a provision
        # says, that is the same on either side, but no directive step is
        # computed." A checklist is the first half, not the second.
        #
        # MEASURED 22 September 2026: a four-dispute advice-only matter, where
        # nothing had been filed and the advocate had said so, reported "what
        # this dispute needs has not been established yet" on every dispute --
        # the one thing that path could have given them, withheld with the
        # recommendation it had nothing to do with. Suppressing what is side-
        # blind along with what is side-dependent is the shape; this is the
        # site where it was found, and `_thresholds` is the neighbouring one.
        #
        # AND THE CONDITION IS `blocked`, NOT `side_blind`. Running this
        # unconditionally was the same conflation one level up: it bought a
        # derivation read on every BLOCKED turn and served nothing from it.
        # Measured the same day -- a blocked turn made 7 model calls to 6
        # settling reads, and no element mentioning what the dispute needs
        # reached the advocate, because a blocked answer carries the question
        # and the provisions and stops. `test_nothing_is_computed_behind_a_
        # closed_posture_gate` is right about that and was the thing that
        # caught it.
        #
        # A side-blind turn that IS served -- the source explanation, which
        # says in terms "no filed role is needed to read the retrieved
        # provisions below" -- is where the checklist was missing, and it
        # still runs there. What a blocked turn may spend is what settles the
        # gate; what a served turn may spend is what the advocate will read.
        found = None
        if not blocked:
            found = self._requirements(thread, tuple(relied_on), metrics,
                                       context=memory.as_context() if memory else "",
                                       concluded=concluded, facts=facts, turn=turn)
        if found is not None:
            concluded["requirements"] = found
        thread_for_reply = replace(thread, requirements=concluded.get(
            "requirements", thread.requirements), requirement_reads=concluded.get(
                "requirement_reads", thread.requirement_reads),
            requirement_outcomes=concluded.get("requirement_outcomes", thread.requirement_outcomes))
        checklist_note = requirements.conversation_context(thread_for_reply, facts, turn.today,
            resumed=bool(turn.session_reference and thread.checklist_session
                         and turn.session_reference != thread.checklist_session)
            or any(i.outcome and i.outcome.at < turn.today.isoformat()
                   for i in requirements.checklist(thread_for_reply, facts)))
        if turn.session_reference and not side_blind:
            concluded["checklist_session"] = turn.session_reference
        request_satisfied = False
        if not side_blind:
            response = self._recommend(thread, turn, result, metrics, memory,
                                register, position, relief_position=relief_pos,
                                concluded=concluded, sources=tuple(retrieved),
                                response_mode=response_mode, checklist_note=checklist_note)
            elements.append(response)
            request_satisfied = response.kind is ElementKind.FINDING
        # A3 §5.4. WHAT THIS TURN DERIVED, and what MOVED since the last one.
        #
        # Run before the queue is drained so a changed value can raise its own
        # gap -- a corrected fact that moves a limitation date is the most
        # urgent thing on the file, and it would otherwise arrive as a note
        # underneath questions about something else.
        derived.extend(self._derived_now(thread, position))
        elements.extend(
            self._cascade(thread, matter_id, tuple(derived), metrics, gaps))

        # A3 §5.2-5.3. THE QUEUE IS DRAINED HERE, once, after everything that
        # could raise a gap has run. Draining it earlier would rank a partial
        # queue, which is the detection order wearing a sort.
        elements.extend(grounds)
        # P24 / C1 NEVER[4]. A need the advocate marked UNAVAILABLE is not
        # re-asked -- it is paused with a resume trigger and shown in the
        # briefing block instead. Dropping it here stops the loop; it stays a
        # gap on the file, so intake is not reported complete over it.
        askable = [g for g in gaps if getattr(g, "what", None) not in paused]
        # A completed explanation need not become a fresh intake interview.
        # Gaps still persist below and material safety blocks remain in the answer.
        if not request_satisfied and not (side_blind and response_mode is Mode.EXPLANATION):
            elements.extend(self._ask(askable, thread, metrics))

        # PHASE 3 -- THE REGISTER AND THE QUEUE SURVIVE THE TURN.
        #
        # Both modules run on every turn and both results were thrown
        # away, so the handover carried no deadlines and no gaps section
        # on a file where each had been computed for four turns.
        #
        # `register is None` WHEN THE TURN WAS SIDE-BLIND, and the key is
        # written only when something computed it -- `Thread.assessed`
        # takes its population from these keys, so the third state falls
        # out of the flow rather than being asserted separately.
        #
        # The queue is written even when EMPTY. Nothing missing is a real
        # answer; nobody having looked is not, and inferring one from the
        # other at read time is the confusion this whole phase removes.
        if register is not None:
            concluded["deadlines"] = register
        # THE PREMISES THE COMPUTATION RAN UNDER, onto the thread, so the cover
        # reads the same legal position the answer was built on and the two
        # cannot disagree (BK-35-AC2). `position` is the claimant limitation.
        if position is not None and position.premises:
            concluded["premises"] = tuple(position.premises)
        concluded["gaps"] = tuple(gaps)

        # THE AUTHORITIES THE ANSWER RESTED ON. Appendix E wants them
        # with binding status, validity window, paragraph kind and
        # treatment -- every one of which a `Finding` already carries and
        # every one of which was thrown away at the end of the turn.
        #
        # BK-4 DOES NOT BLOCK THIS. The FTS index decides what an
        # authority SEARCH returns; these are the provisions this answer
        # actually relied on, retrieved on the turn that used them.
        concluded["authorities"] = tuple(relied_on)

        # F-B-17. WHAT THIS DISPUTE NEEDS, read out of the passages that were
        # actually retrieved for it -- not from a table of dispute types and
        # not from the model's memory of the law.
        return elements, tuple(relied_on), tuple(retrieved), tuple(derived)

    def _requirements(self, thread: Thread, relied_on: tuple, metrics: TurnMetrics,
                      *, context="", concluded=None, facts=(), turn=None):
        """The checklist for one dispute, or None when there is nothing to read.

        Read newly retrieved or changed passages together within this turn.
        Successful reads, including empty ones, are cached by passage identity,
        not merely locator. Ordinary replies update answers in the existing
        dispute read; they do not add a separate checklist-answer model call.
        Cache invalidation for changed dispute applicability remains an explicit
        open obligation, not a claim that the text alone determines relevance.

        A FAILED READ LEAVES THE CHECKLIST ALONE. Returning an empty tuple
        would erase requirements an earlier passage established, and the
        advocate would watch the list empty itself for no reason they could
        see -- so `None` means "no change", which is what the caller persists.
        """
        quotable = tuple(f for f in relied_on if f.quotable and (f.span or "").strip())
        if not quotable:
            return None
        held = requirements.restored(thread)
        passages = tuple(
            requirements.Passage(
                source=f.ref, text=f.span, locator=f.locator,
                kind="provision" if f.source_kind is SourceKind.PROVISION else "authority")
            for f in quotable)
        passages = tuple(p for p in passages
                         if thread.requirement_reads.get(p.locator) != p.identity)
        if not passages:
            return None
        scoped_facts = tuple(f for f in facts if f.id in thread.chronology
                             and f.superseded_by is None
                             and f.provenance.kind == "advocate_statement")
        context += "\nAdvocate facts (quotable for answers):\n" + "\n".join(
            f.statement for f in scoped_facts)
        try:
            answer = self._read(requirements.build_prompt(thread.label, passages, context=context),
                                requirements.schema_for(passages), "requirements")
            metrics.record_call(answer)
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"what this dispute needs was not read: {exc}")
            return None
        if refuse_partial(answer.completion, doing="the requirement reading"):
            metrics.fire("G-MODEL", "unavailable", "The requirement reading was incomplete.")
            return None
        reading = requirements.read(answer.data or {}, passages)
        if reading.dropped:
            # Counted where it can be seen. A reader that keeps inventing
            # requirements looks exactly like a reader finding fewer of them.
            # The unsupported candidates never enter the answer or checklist.
            # This is an unusable read, not a supported-grounding verdict and
            # not a reason to publish a partial replacement for the held list.
            metrics.fire("G-MODEL", "unavailable",
                         f"{reading.dropped} checklist candidate(s) failed source checks; "
                         "the existing checklist has not been replaced")
            return None
        if (not reading.dropped and isinstance(answer.data, dict)
                and isinstance(answer.data.get("requirements"), list) and concluded is not None):
            concluded["requirement_reads"] = {**thread.requirement_reads,
                                             **{p.locator: p.identity for p in passages}}
        merged = requirements.merge(held, reading)
        if concluded is not None and turn is not None and reading.requirements:
            proposals = []
            for row in (answer.data or {}).get("requirements", ()):
                if not isinstance(row, dict) or not row.get("answer"):
                    continue
                matches = [r for r in reading.requirements
                           if r.source == row.get("source")
                           and r.span == " ".join(str(row.get("span", "")).split())]
                if len(matches) == 1:
                    proposals.append({"thread_id": thread.id, "key": requirements.key(matches[0]),
                                      "answer": row.get("answer"),
                                      "quoted": row.get("answer_quote"),
                                      "due_expression": row.get("due_expression", "")})
            # Reuse the same scoped validator as later conversation replies.
            # This local projection is never independently stored or admitted.
            snapshot = Matter.create(advocate_id=turn.advocate_id, title="Checklist validation")
            snapshot = replace(snapshot, facts=scoped_facts,
                               threads=(replace(thread, requirements=merged),))
            checked = requirements.apply_answers(snapshot, proposals,
                message="\n".join(f.statement for f in scoped_facts),
                turn_id=turn.turn_id, today=turn.today, current_only=False)
            concluded["requirement_outcomes"] = checked.threads[0].requirement_outcomes
        return merged if merged != held else None

    def _remember_questions(self, matter: Matter, answer: Answer,
                            metrics: TurnMetrics, turn: TurnInput) -> Matter:
        """Record every question PUT, and close every one that came back.

        ONE PLACE, AND THE CLOSING RULE IS GENERAL. A gate stops firing
        exactly when the condition it names has cleared, and the condition
        clearing is what "the advocate answered it" means. Closing questions
        one by one at each call site is how a question survives its own
        answer and gets asked a second time -- which is the defect this
        whole ledger exists to make impossible.

        Runs before the commit, inside the same version check, so the ask
        ledger cannot drift from the turn that produced it.
        """
        for e in answer.elements:
            if e.kind is ElementKind.QUESTION:
                matter = matter.asking(e.gate or "", e.text, turn.turn_id,
                                       e.thread)
        return matter.answered(
            frozenset(g.gate_id for g in metrics.gates_fired), turn.turn_id)

    def _read_accrual(self, trigger: str, dated: list[Fact],
                      metrics: TurnMetrics, *, context: str = "") -> accrual_reader.Accrual:
        """WHICH dated entry satisfies the statutory trigger.

        FAILS TOWARD NOT COMPUTING, and that is the whole safety argument. A
        wrong accrual produces a confident expiry with real statutory text
        behind it, correct citations around it, and nothing downstream that
        catches it -- the defect this read exists for. An absent one produces
        a gap that names what it was looking for, which the advocate closes in
        one turn.

        So every failure path here returns UNREAD, which is not identified,
        which not-computes. There is no path from a failed read to a date.
        """
        try:
            res = self._read(
                      accrual_reader.build_prompt(trigger, dated, context=context),
                      accrual_reader.ACCRUAL_SCHEMA, "accrual", Tier.ROUTINE)
            metrics.record_call(res)
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"the accrual read could not run: {exc}")
            return accrual_reader.UNREAD
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning (§7)
            metrics.violate(
                "D2", f"accrual read failed: {type(exc).__name__}: {exc}")
            return accrual_reader.UNREAD

        read = accrual_reader.interpret(
            res.data or {}, frozenset(f.id for f in dated))
        if read.refused:
            metrics.violate("D2", read.refused)
        return read

    @implements("D1")
    def _pre_institution_row(self, cause_read: str | None):
        """The `statutory_notice` row, from the curated table. LB-121.

        `None` WHERE NO TABLE IS WIRED, so the map keeps its own "not assessed
        on this thread" reason rather than this method inventing a quieter one.
        An unwired installation must not read as one that looked.

        THE OPPONENT IS ALWAYS `UNKNOWN` IN THIS SLICE, and that is a decision
        rather than an omission. Whether the other side is the Government or a
        public officer -- which is what engages CPC s.80 -- is a question about
        a party, and answering it by matching words in a party's name would be
        fuzzy matching doing IDENTIFICATION, which CLAUDE.md section 5 records
        as not merely weak but wrong. So it stays unestablished, `undecided`
        reports s.80 as a question nobody can yet settle, and a later slice
        records the answer from the advocate rather than guessing it.
        """
        if self._pre_institution is None:
            return None
        try:
            cause = (CauseOfAction(cause_read) if cause_read
                     else CauseOfAction.NOT_ESTABLISHED)
        except ValueError:
            # A cause outside the closed vocabulary is not established, which
            # is what the vocabulary being closed is for.
            cause = CauseOfAction.NOT_ESTABLISHED
        against = Against.UNKNOWN
        return thresholds.from_institution(
            self._pre_institution.engaged(cause, against),
            self._pre_institution.undecided(cause, against))

    def _accrual_trigger(self, cause_read) -> str:
        """The statutory trigger for this cause, or empty.

        THROUGH THE EVIDENCE ADAPTER, because `core` may not import
        `nm.knowledge` (layercheck) and the trigger is curated beside the
        Article in `resolution.py`. A copy here would be a second home for
        a legal fact, which is the defect S9 names.

        EMPTY MEANS NOBODY CURATED ONE, and the caller then behaves as it
        did before: it computes from what it has. That is the honest
        fallback -- a cause with no curated trigger is not a cause we know
        enough about to refuse on.
        """
        if not cause_read:
            return ""
        try:
            return self._evidence.accrual_trigger(cause_read) or ""
        except AttributeError:
            # An adapter predating the port method. Empty is the
            # documented "no curated trigger" and not an error.
            return ""

    @implements("D1")
    def _thresholds(self, thread: Thread, turn: TurnInput, result,
                    metrics: TurnMetrics, facts: tuple[Fact, ...],
                    concluded: dict | None = None,
                    cause_read: str | None = None,
                    ) -> tuple[list[Element], tuple[deadlines.Deadline, ...],
                               limitation.Limitation]:
        """The threshold map, the limitation position, and the register.

        EVERY THRESHOLD GETS A ROW whether or not it was assessed, because an
        advocate reading eight rows believes the ninth was checked. What this
        slice can answer is limitation; the rest are BLOCKED with the reason,
        which is a question they can act on rather than a silence they cannot
        see.

        Returns the register alongside the elements because the recommendation
        needs it -- an ACTION carries the by-when the file actually holds, or
        says why it has none. It may not carry a sentence that reads like a
        finding of no deadline when nothing was computed.
        """
        out: list[Element] = []
        chart = chronology.chart(facts, thread.chronology)
        dated = tuple(f.date for f in chart if f.date is not None)

        # WHOSE CLAIM DOES THE CHART DESCRIBE? On a defending thread it is
        # THEIRS — the advocate is describing the claim being made against
        # their client, and the accrual on the file is that claim's accrual.
        #
        # This computed BOTH from the same chart and labelled one "ours" and
        # one "theirs", so a defending turn reported two limitation positions
        # with the same Article, the same accrual and the same date. It read
        # as two findings and was one, and the "our side" figure asserted a
        # claim of ours that nothing on the thread describes. Measured on a
        # served turn, 31 August 2026 (B-075).
        defending = thread.posture.side is Side.DEFENDING
        claimant = self._limitation(
            Side.MOVING if defending else thread.posture.side,
            thread, result, chart, turn, metrics, out, cause_read)
        # NOT APPLICABLE, NOT UNCOMPUTED. No period runs against a party
        # who has brought no claim, so this is a FINDING and not a gap.
        # The distinction is kept at the type because the only thing that
        # separated them was the prose of `not_computed_because`.
        ours = (limitation.not_applicable(
            thread.posture.side,
            "we are defending and nothing on this thread describes a claim of "
            "ours; a counterclaim would have its own accrual",
            thread.chronology) if defending else claimant)
        register = self._register(thread, claimant)
        assessed = {thresholds.Threshold.LIMITATION:
                    thresholds.from_limitation(claimant)}
        # LB-121. WHAT MUST BE DONE BEFORE THIS CAN BE FILED. The row said
        # "not assessed on this thread" on every turn because nothing assessed
        # it; the curated table now names the conditions this cause engages,
        # and says plainly that whether the file shows them done is a separate
        # question nothing here has read.
        notice = self._pre_institution_row(cause_read)
        if notice is not None:
            assessed[thresholds.Threshold.STATUTORY_NOTICE] = notice
        map_ = thresholds.for_thread(assessed)

        # D1.1 -- arithmetic checked against THE FILE'S OWN DATES. A twelve-year
        # clock is not absurd; one that expires before the file's earliest
        # event is arithmetic about a different matter.
        for problem in thresholds.absurd(map_, dated):
            metrics.violate("D1", problem)
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"I am not putting this figure in front of you: {problem}"))

        out.extend(self._limitation_elements(thread, turn, ours, "our", chart))

        # D8 -- SALVAGE, exactly where the claim is reported as failing.
        #
        # The line above ends "that is not the end of the file — what else it
        # offers is a separate question", and this is what makes good on it.
        # Run on every turn instead, it would be seven paragraphs of
        # hypothetical restructuring attached to a claim that is fine, which
        # is the survey this product rejects.
        if ours.state is limitation.LimitationState.COMPUTED \
                and ours.expired(turn.today):
            out.extend(self._salvage(turn, thread, result, metrics, ours))

        # D2 -- THEIRS TOO, and on a defending thread it is often the whole
        # answer: it disposes of the claim without touching the merits.
        if defending:
            # THE ONE THAT MATTERS ON A DEFENDING THREAD, and D2 says why:
            # their limitation is often the whole answer, disposing of the
            # claim without touching the merits. `ours` above says plainly
            # that no claim of ours is on this thread rather than repeating
            # this figure under a second name.
            out.extend(
                self._limitation_elements(thread, turn, claimant, "their", chart))

        blocked = [a for a in map_
                   if a.state is thresholds.ThresholdState.BLOCKED]

        # A ROW THAT SAYS SOMETHING PARTICULAR IS SAID, not counted.
        #
        # The summary below names the thresholds NOBODY ASSESSED, which is
        # right for a row carrying the map's own default sentence and wrong
        # for one that has been assessed far enough to name what is missing:
        # counting it puts a checkable question inside a list an advocate has
        # learned to skim. Measured on LB-121's first served turn -- the
        # curated demand-notice condition reached the map and the advocate saw
        # the word `statutory_notice` in a list of nine.
        #
        # THESE REPEAT EVERY TURN, deliberately, and BK-7 is not against it:
        # what that measured was the same forty-word list of NAMES four times
        # over. A named condition that must be satisfied before this can be
        # filed is substantive, like the limitation position beside it, and
        # substantive lines are served whenever they hold.
        for row in blocked:
            if row.reason == thresholds.NOT_ASSESSED:
                continue
            if row.threshold in _THRESHOLDS_RENDERED_ELSEWHERE:
                continue
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"Before this can be filed — {row.reason}."))

        if blocked:
            # IN FULL WHEN IT CHANGES, SHORT WHEN IT HAS NOT (BK-7).
            #
            # Measured on GS-14: the same forty-word line naming the same
            # nine thresholds, on all four turns. An advocate who reads
            # that four times learns to skip it, and what they skip is
            # the list of what nobody has checked.
            #
            # NEVER SILENT. §9 -- the third state must be visible in the
            # OUTPUT and not only in the type -- so the full list is
            # replaced by a clause, not by nothing.
            names = tuple(sorted(a.threshold.value for a in blocked))
            told = tuple(str(x) for x in (thread.thresholds_told or ()))
            concluded["thresholds_told"] = names
            if names == told:
                out.append(Element(
                    kind=ElementKind.GROUND, thread=thread.id,
                    disclosure=True,
                    text=(f"The same {len(blocked)} threshold(s) are still "
                          f"not assessed on this thread.")))
            else:
                out.append(Element(
                    kind=ElementKind.GROUND, thread=thread.id,
                    disclosure=True,
                    text=(f"{len(blocked)} of {len(map_)} thresholds are not "
                          f"assessed on this thread: "
                          f"{', '.join(names)}. Those "
                          f"are gaps in the map, not findings that they do not "
                          f"arise.")))
        return out, deadlines.register(register, turn.today), claimant

    @implements("D2")
    def _limitation(self, for_side: Side, thread: Thread, result,
                    chart: tuple[Fact, ...], turn: TurnInput,
                    metrics: TurnMetrics,
                    grounds: list[Element],
                    # THE CAUSE. The accrual trigger is cause-specific;
                    # without it this chose the earliest dated fact.
                    cause_read: str | None = None,
                    ) -> limitation.Limitation:
        """Limitation for one side -- or NOT COMPUTED, with the reason said.

        Slice 4 computes it where the retrieval produced an Article AND the
        chart holds a dated accrual. Anything else is NOT_COMPUTED carrying
        why, because a limitation nobody computed must never read as a
        limitation that is fine.
        """
        # THE LIVE ENTRIES, not the raw chronology. A superseded fact is
        # still on the thread and must not be reported as one the arithmetic
        # never weighed — it is one the arithmetic is not supposed to weigh.
        #
        # Taken straight off the CHART, which has already dropped them. The
        # first version called `live_ids(chart, thread.chronology)` and was
        # wrong in the quiet direction: the chart holds no superseded facts,
        # so it would have found none to drop and returned the whole
        # chronology — the exact bug it was written to fix, one layer up.
        live = tuple(f.id for f in chart)

        found = next((f for f in result.findings
                      if "Article" in f.ref or "Limitation" in f.ref), None)
        # THE ACCRUAL IS A STATUTORY TRIGGER, NOT THE EARLIEST DATE.
        #
        # This read `next(f for f in chart if f.date is not None)` -- the
        # first dated fact, whatever the cause. So Article 54 ran from a
        # 2023 agreement when its trigger is the date fixed for
        # performance or notice of refusal, and the answer declared an
        # expiry with every citation on the turn correct.
        #
        # `Edge.accrues_on` carries the trigger from the Schedule's third
        # column, and `_read_accrual` reads WHICH entry satisfies it.
        #
        # Even one event must satisfy the trigger. Exact fact identity does
        # not establish legal applicability. A model-selected event remains
        # inferred below even when the statutory trigger is retrieved.
        dated = [f for f in chart if f.date is not None]
        trigger = self._accrual_trigger(cause_read)
        accrual = dated[0] if dated else None
        accrual_limb = ""
        if dated and trigger:
            read = self._read_accrual(trigger, dated, metrics, context=(
                f"ACTIVE DISPUTE: {thread.label}\nCURRENT INSTRUCTION: {turn.message}\n"
                "SCOPED ACCOUNT (attributed, not findings):\n"
                + "\n".join(f"{f.id}: {f.statement}" for f in chart)))
            if not read.identified:
                return limitation.not_computed(
                    for_side,
                    f"the period runs from {trigger}, and I could not identify "
                    f"that event among the {len(dated)} dated entries on this "
                    f"thread. {read.why}. Name it and I will work the period "
                    f"from it",
                    live)
            accrual = next(f for f in dated if f.id == read.fact_id)
            accrual_limb = read.limb

        # THE THREE PREMISES, BUILT BEFORE THE ARITHMETIC. BK-65-AC2, P22.
        #
        # `compute()` already refuses to invent a PERIOD; what it cannot refuse
        # is a right period applied under the wrong Article, from the wrong
        # date, or in a forum that does not bind. Those are three premises,
        # each separately attributed, and the arithmetic may not certify any
        # of them. `premises.unestablished()` BLOCKS -- a computation without a
        # premise answers a question nobody asked; `premises.inferred()` makes
        # the result CONDITIONAL -- it may run, labelled, but it is never a
        # deadline. The only premise this slice can infer is the accrual, and
        # only where the cause is uncurated.
        premises = self._premises(found, accrual, accrual_limb, trigger,
                                  dated, turn,
                                  stated=getattr(thread, "premises_stated", None))
        # UNESTABLISHED BLOCKS; INFERRED does not. `assess` treats both as
        # reasons not to compute, but this slice CAN compute under an inferred
        # accrual and show the result conditionally -- so the block is
        # `unestablished()` alone, and `inferred()` drives the conditional
        # branch below. A premise nobody has established at all is the gap that
        # must stop the arithmetic; one the product worked out is a labelled,
        # correctable answer.
        missing = premises.unestablished()
        if missing:
            reasons = "; ".join(premise_mod.english_of(k) for k in missing)
            metrics.fire("G-PREMISE", "unestablished", reasons)
            return limitation.not_computed(
                for_side,
                "the legal position is not established -- " + reasons,
                live, premises=premises.as_rows(),
                premise_digest=premises.digest())
        if found is None:
            return limitation.not_computed(
                for_side, "no limitation Article was retrieved for this cause",
                live, premises=premises.as_rows(),
                premise_digest=premises.digest())
        if accrual is None:
            return limitation.not_computed(
                for_side, "no dated event on this thread to run the period from",
                live, premises=premises.as_rows(),
                premise_digest=premises.digest())

        # THE PERIOD COMES OUT OF THE RETRIEVED TEXT. It was a constant here --
        # `years=3` on every computation, including one that had just retrieved
        # Article 65 and its twelve years -- and the resulting bar was reported
        # nine years early with every citation on the turn correct.
        period = limitation.period_in(found.span)
        if period is None:
            return limitation.not_computed(
                for_side,
                f"the period is not stated in the text retrieved for "
                f"{found.ref} — I will not supply one from memory",
                live)
        # NOTHING IS PASSED AS `considered`, AND THAT IS THE POINT.
        #
        # This passed every non-accrual entry with the reason "on the chart; it
        # neither restarts nor extends" -- a legal conclusion about each fact
        # that nothing had reached. Whether a letter is an acknowledgment under
        # s.18 is a question about its words, and nothing in this slice reads
        # them.
        #
        # MEASURED ON A SERVED TURN, 31 August 2026, and it is the exact defect
        # D2 was built for. GS-14: invoices of 14 March 2023, then "the
        # defendant wrote to us on 12 June 2024 admitting the amount was
        # outstanding". The product answered "limitation runs to 2026-03-14" --
        # unchanged, expired, and the claim reported dead when it is alive to
        # June 2027. The acknowledgment was on the file, was repeated back, and
        # never reached the arithmetic.
        #
        # E-042 exists to catch precisely that, and this dictionary was what
        # stopped it: every entry marked NO_EFFECT is an entry accounted for,
        # so `accounts_for_every_entry` returned nothing and the coverage gap
        # never fired. A false statement about each fact bought silence about
        # all of them.
        #
        # With it gone, every unexamined entry lands NOT_ASSESSED and the
        # advocate is told how many things were never weighed. That is a worse
        # answer and an honest one, and it is the one they can act on.
        # COMPUTED TWICE, ON PURPOSE.
        #
        # s.18 and s.19 both apply only to an acknowledgment or payment made
        # "before the expiration of the prescribed period" -- so the
        # un-extended expiry has to EXIST before any factor can be judged
        # against it. The first pass is pure arithmetic over dates already on
        # the file and costs nothing. Ordering it the other way would test a
        # factor against a date that factor had already moved.
        # THE LIMB IS WHAT MAKES THE ACCRUAL CHECKABLE, so it travels with the
        # reason rather than being dropped once the date is picked.
        # `2024-06-10` tells an advocate nothing; `the written refusal — no
        # date having been fixed for performance` is a sentence they can
        # disagree with in four words, which is the only way a wrong accrual
        # gets caught. Built once here because two call sites building the
        # same string is a second owner for it (§4).
        accrual_reason = (f"{snippet(accrual.statement, 70)} — {accrual_limb}"
                          if accrual_limb else snippet(accrual.statement, 70))
        bare = limitation.compute(
            for_side=for_side, article=found.ref, accrual=accrual.id,
            accrual_on=accrual.date, accrual_reason=accrual_reason,
            chronology=live, period=period)

        read = self._factors(turn, thread, chart, metrics, grounds,
                             bare.expires_on)

        # CONDITIONAL WHERE THE ACCRUAL WAS INFERRED. The alternatives are the
        # same arithmetic under every other dated entry, so the advocate sees
        # each candidate date rather than the one the sort order picked -- and
        # none of them is a deadline until a premise is stated.
        conditional_because = ""
        alternatives: list[dict] = []
        if premise_mod.Kind.ACCRUAL_RULE in premises.inferred():
            conditional_because = (
                f"the period was provisionally run from {accrual_reason}. "
                f"Identifying a dated event does not establish that it satisfies "
                f"the legal trigger; that application has not been confirmed")
            for other in dated:
                if other.id == accrual.id or other.date is None:
                    continue
                alternatives.append({
                    "accrual": other.id, "accrual_on": other.date.isoformat(),
                    "expires_on": limitation.expiry_from(
                        other.date, period, read.factors).isoformat()})
            metrics.fire("G-PREMISE", "conditional", conditional_because)
        else:
            metrics.fire("G-PREMISE", "established",
                         "the applicable law, accrual and forum are attributed")

        return limitation.compute(
            for_side=for_side, article=found.ref, accrual=accrual.id,
            accrual_on=accrual.date, accrual_reason=accrual_reason,
            chronology=live, period=period,
            factors=read.factors,
            premises=premises.as_rows(), premise_digest=premises.digest(),
            conditional_because=conditional_because,
            alternatives=tuple(alternatives))

    @implements("D1")
    def _premises(self, found, accrual, accrual_limb: str, trigger: str,
                  dated: list, turn: TurnInput,
                  stated: dict | None = None) -> "premise_mod.Premises":
        """The applicable law, the accrual rule and the forum, each attributed.

        NONE OF THE THREE IS DERIVABLE FROM THE ARITHMETIC. The Article comes
        from what was retrieved (a source that can be re-read); the accrual
        from the curated trigger where one exists (ATTRIBUTED) or from the
        product's own reading of the only sensible date where it does not
        (INFERRED, with the alternatives named); the forum from the
        deployment's measured scope. A premise the advocate has STATED
        outranks all of this and is read from the thread first.
        """
        kinds, bases = premise_mod.Kind, premise_mod.Basis
        make = premise_mod.Premise
        stated = stated or {}
        items = []

        # APPLICABLE LAW -- the retrieved Article.
        law = stated.get(kinds.APPLICABLE_LAW.value)
        if law:
            items.append(make(kind=kinds.APPLICABLE_LAW, statement=law["statement"],
                           basis=bases.STATED, source=law.get("source") or "the advocate",
                           reviewed_by=law.get("by", ""), reviewed_at=law.get("at", "")))
        elif found is not None:
            items.append(make(
                kind=kinds.APPLICABLE_LAW, statement=found.ref, basis=bases.ATTRIBUTED,
                source=f"{getattr(found, 'store', '')}:{getattr(found, 'locator', '')}"))
        else:
            items.append(make(kind=kinds.APPLICABLE_LAW,
                           statement="no provision was retrieved for this cause",
                           basis=bases.UNESTABLISHED))

        # ACCRUAL RULE.
        acc = stated.get(kinds.ACCRUAL_RULE.value)
        if acc:
            items.append(make(kind=kinds.ACCRUAL_RULE, statement=acc["statement"],
                           basis=bases.STATED, source=acc.get("source") or "the advocate",
                           reviewed_by=acc.get("by", ""), reviewed_at=acc.get("at", "")))
        elif accrual is None:
            items.append(make(kind=kinds.ACCRUAL_RULE,
                           statement="no dated event to run the period from",
                           basis=bases.UNESTABLISHED))
        elif trigger:
            items.append(make(
                kind=kinds.ACCRUAL_RULE,
                statement=(f"The candidate event {snippet(accrual.statement, 120)} "
                           f"is proposed as satisfying {trigger}"),
                basis=bases.INFERRED,
                inferred_from=("a model's application of the retrieved trigger "
                               "to a dated instruction, not an established accrual"),
                alternatives=tuple(f"{snippet(f.statement, 44)} ({f.date.isoformat()})"
                                   for f in dated if f.date is not None and f.id != accrual.id)))
        else:
            others = tuple(f"{snippet(f.statement, 44)} ({f.date.isoformat()})"
                           for f in dated if f.date is not None and f.id != accrual.id)
            items.append(make(
                kind=kinds.ACCRUAL_RULE,
                statement="the period was run from the earliest dated entry on the thread",
                basis=bases.INFERRED,
                inferred_from=("the only dated entry" if len(dated) == 1
                               else "the earliest dated entry; the cause carries "
                                    "no curated accrual trigger"),
                alternatives=others))

        # JURISDICTION -- the deployment's measured scope. A standing product
        # decision (BASELINE §1.1), attributed to it, not inferred per turn.
        jur = stated.get(kinds.JURISDICTION.value)
        if jur:
            items.append(make(kind=kinds.JURISDICTION, statement=jur["statement"],
                           basis=bases.STATED, source=jur.get("source") or "the advocate",
                           reviewed_by=jur.get("by", ""), reviewed_at=jur.get("at", "")))
        elif (turn.jurisdiction or "").strip():
            items.append(make(
                kind=kinds.JURISDICTION, statement=turn.jurisdiction,
                basis=bases.ATTRIBUTED,
                source="the deployment's measured coverage scope (BASELINE §1.1)"))
        else:
            items.append(make(kind=kinds.JURISDICTION,
                           statement="no forum was established for this matter",
                           basis=bases.UNESTABLISHED))

        return premise_mod.Premises(tuple(items))

    @implements("D3")
    def _register(self, thread: Thread, lim: limitation.Limitation,
                  ) -> tuple[deadlines.Deadline, ...]:
        """The limitation window as a register entry -- COMPUTED OR NOT.

        An uncomputed window is entered with `on=None`, which renders as
        NOT_COMPUTED. Leaving it off would tell the advocate there is no
        deadline, which is the opposite of what is known.
        """
        whose = "our" if lim.for_side is thread.posture.side else "their"
        # A CONDITIONAL DATE IS NOT `on`. `status()` reads `on`, so a date run
        # under an inferred premise is NOT_COMPUTED on the register and can
        # never be near, future or passed -- the advocate is never told to act
        # by a date that rests on an assumption. It rides in `conditional_on`,
        # labelled, beside the premise that would make it real. P22.
        conditional = lim.state is limitation.LimitationState.CONDITIONAL
        return (deadlines.Deadline(
            thread=thread.id, kind=deadlines.DeadlineKind.LIMITATION,
            source=lim.article or "no Article retrieved",
            action=f"commence {whose} claim within the limitation period",
            owner="the instructing advocate",
            consequence="the claim is barred and the merits are never reached",
            on=None if conditional else lim.expires_on,
            conditional_on=lim.expires_on if conditional else None,
            premise_digest=lim.premise_digest),)

    def _limitation_elements(self, thread: Thread, turn: TurnInput,
                             lim: limitation.Limitation, whose: str,
                             chart: tuple[Fact, ...] = (),
                             ) -> list[Element]:
        """The position, and E-042's coverage gap where there is one.

        ONE BUILDER FOR BOTH SIDES. Writing it twice is how the opponent's
        limitation ends up thinner than ours -- which is the defect D2's third
        DOES clause exists to refuse.
        """
        out: list[Element] = []
        if lim.state is limitation.LimitationState.CONDITIONAL:
            # A DATE, LABELLED CONDITIONAL, WITH ITS ALTERNATIVES. BK-65-AC2.
            # The arithmetic ran and is shown, but it rests on a premise the
            # product inferred, so it is not a deadline and every competing
            # trigger's date is shown beside it. Naming what must be
            # established is what lets the advocate settle it in one reply.
            alts = "; ".join(
                f"from {a['accrual_on']} it would be {a['expires_on']}"
                for a in lim.alternatives)
            other_events = "; ".join(
                f"{f.date.isoformat()} ({snippet(f.statement, 90)})"
                for f in chart if f.date is not None and f.id != lim.accrual)
            # WHOSE PERIOD IT IS COMES FIRST, IN THE SAME WORDS AS THE
            # COMPUTED LINE BELOW. It used to be buried mid-sentence, after a
            # conditional clause long enough to hold a whole chronology entry,
            # so a defending turn that HAD worked out the opponent's position
            # read as one that never mentioned them -- and grounds is a list an
            # advocate scans, where a line that does not say whose limitation
            # it is may as well be about the other side.
            #
            # The two states share the opening deliberately. A reader looking
            # for "Limitation for their side" finds it whether the accrual was
            # attributed or inferred, and what differs after it is the STATE,
            # which is the thing that actually differs.
            return [Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                signal=Signal.NONE, gate="G-PREMISE",
                text=(f"Limitation for {whose} side — CONDITIONAL, not a "
                      f"deadline: on the reading that "
                      f"{lim.conditional_because}, {whose} limitation period "
                      f"would run to {lim.expires_on.isoformat()} on "
                      f"{lim.article}."
                      + (f" On other readings: {alts}." if alts else "")
                      + (f" This calculation is not from: {other_events}. "
                         "Those events have not been established as alternative legal triggers; "
                         "say which event satisfies the trigger if the current reading is wrong."
                         if other_events else "")
                      + " I have not entered a deadline for it: confirm the "
                        "accrual and it becomes one."))]
        if lim.state is not limitation.LimitationState.COMPUTED:
            # ONE LINE, NOT TWO. The coverage gap is deliberately NOT reported
            # here, and that is a fix rather than an omission.
            #
            # `not_computed` marks every chronology entry NOT_ASSESSED, so the
            # gap is total by construction and reporting it said the same thing
            # twice -- the second time in words that imply a computation which
            # ran and missed things. Measured on a real turn: "6 thing(s) on
            # this file were never weighed against the limitation period",
            # climbing every turn as facts accumulated, beside "I have not
            # computed the limitation position". Nothing was weighed because
            # nothing was computed, and the growing number read as a growing
            # defect.
            #
            # E-042 IS ABOUT A COMPUTATION THAT HAPPENED AND SKIPPED AN ENTRY.
            # Firing it where none happened spends the signal's credibility on
            # a case it was not written for.
            # THE DATED ENTRIES ARE NAMED HERE TOO, and that is BK-35's own
            # correction to itself. The alternatives clause below used to be
            # the safety net for an accrual chosen by sort order, and it was
            # written on a path that always computed. Once the accrual became
            # a read, the commonest way to lose the period became a read that
            # could not identify the trigger — and the net stopped rendering
            # on exactly the turns it was for.
            #
            # The advocate is one sentence from fixing it: they can see the
            # dates and say which one the period runs from. Telling them the
            # count and withholding the list makes them ask for what is
            # already on the file.
            dated = ", ".join(
                f"{snippet(f.statement, 44)} ({f.date.isoformat()})"
                for f in chart if f.date is not None)
            return [Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"I have not computed the limitation position for "
                      f"{whose} side on this thread: "
                      f"{lim.why_not_computed}."
                      + (f" It was not computed from any of the dated entries "
                         f"on this thread — not from: {dated}. If the period "
                         f"should run from one of those, say which."
                         if dated else "")))]

        missed = lim.accounts_for_every_entry(thread.chronology)
        if missed:
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"{len(missed)} thing(s) on this file were never weighed "
                      f"against {whose} limitation period. That is a gap in my "
                      f"working, not a finding that they do not matter.")))

        # D2 -- NEVER NARRATE IT. A date and a day count, or nothing.
        days = lim.days_remaining(turn.today)
        gone = lim.expired(turn.today)
        # WHICH DATED FACT IT RAN FROM, AND WHAT ELSE WAS THERE.
        #
        # The accrual is the earliest dated entry — right on most files, and
        # an arbitrary tiebreak on a file that holds two dates for one event.
        # Naming the alternatives costs a clause and makes a wrong choice
        # visible on the face of the answer, whatever any model read did.
        others = ", ".join(
            f"{snippet(f.statement, 44)} ({f.date.isoformat()})"
            for f in chart
            if f.date is not None and f.id != lim.accrual)
        alternatives = (
            f" It ran from that entry and not from: {others}. If the period "
            f"should run from one of those, say which."
            if others else "")

        out.append(Element(
            kind=ElementKind.GROUND, thread=thread.id,
            signal=Signal.LIMITATION_BAR if gone else Signal.NONE,
            text=(f"Limitation for {whose} side runs to "
                  f"{lim.expires_on.isoformat()} on {lim.article}, from "
                  f"{lim.accrual_reason} ({abs(days)} days "
                  f"{'ago' if gone else 'from today'})."
                  + ("" if not gone else
                     " That period has run. That is not the end of the file — "
                     "what else it offers is a separate question.")
                  + alternatives)))
        return out

    def _disclose_coverage(self, turn: TurnInput, thread: Thread,
                           metrics: TurnMetrics, grounds: list[Element]) -> None:
        """G-COVERAGE. What this corpus can and cannot answer for, said first.

        The review's stop-ship #1: the product claimed Telangana coverage it
        had not measured. The measurement was written down and inert, because
        a fact in a document is not a gate. It is now one.

        AND THE FIRST GATE MEASURED THE WRONG THING, which is worth keeping
        here because this method is what the advocate reads. It counted the
        `hc_telangana` court label -- which no record carries -- got zero, and
        told them on every authority turn that no High Court output was held
        for their jurisdiction. 4,280 are held, and every one binds. What is
        disclosed now is the RECENCY gap that is really there.
        """
        if self._coverage is None:
            position_state, detail = "not_measured", (
                "no coverage measurement is wired into this installation, so I "
                "cannot tell you whether the binding court's output is held. "
                "Run `python pipeline/quality/releasegate.py --write`.")
        else:
            position = self._coverage.position(turn.jurisdiction)
            # `discloses` OWNS "anything but MET is said out loud". Asking
            # `state is MET` here was the same rule in a second place, and
            # the owner had no callers at all.
            if not position.discloses:
                return
            position_state = position.state.value
            detail = position.detail

        metrics.fire("G-COVERAGE",
                     "unmet" if position_state == "unmet" else "not_measured",
                     detail)
        grounds.append(Element(
            kind=ElementKind.GROUND, thread=thread.id,
            text=f"Before you rely on any authority I give you: {detail}",
            disclosure=True))

    @implements("C3")
    def _read_posture(self, turn: TurnInput, metrics: TurnMetrics,
                      memory=None, *, thread_label="", opponent=""):
        """What the advocate STATED about whom they act for, read by model.

        There is no phrase list. There was one, of ten exact phrases, and an
        advocate answering the blocking question in any other words was asked
        it again -- so every multi-turn conversation trapped the person using
        it. A longer list is the same defect at a larger size.

        `posture.interpret` refuses anything the message does not support, and
        a refusal leaves posture exactly where it was: unresolved, and
        blocking. Failing to read a posture must never look like reading one.
        """
        # THE SHARPEST CASE (B-108). `as_context()` carries this
        # product's own outstanding questions, and one of them is
        # literally "do we act for the party moving, or the party
        # answering?" -- so it is CONTEXT and never quotable, and the
        # prompt now says so instead of leaving the guard to refuse it.
        quotable = Quotable(
            turn=turn.message,
            # RESTORED BY P14. The handoff swapped these two: the advocate's
            # own words went into `context` and the product's rendering into
            # `file`, which inverts what may be quoted. `Quotable` exists to
            # keep the advocate's words quotable and this product's own
            # rendering not, and the swap made the guard protect the wrong one.
            file=memory.advocate_words if memory else "",
            # A SHARED INSTRUCTION IS NOT ANOTHER DISPUTE'S FACT, and conflating
            # the two blocked a four-dispute matter on G-POSTURE while the
            # advocate had already written "no suit is filed by us and I am not
            # defending any proceeding yet except the cheque case" (live run,
            # 22 September 2026). An advocate states representation ONCE for the
            # file; asking again per dispute is asking for what the file holds.
            #
            # THE INVENTORY READ ALREADY SAYS THIS -- "include shared
            # representation, proposed-claim or defence instructions in the
            # allocation for each affected dispute" -- so this read saying the
            # opposite was two owners disagreeing about one rule, which is the
            # contradiction P6 refuses. What stays scoped is what must: the
            # opponent and the procedural role of THIS dispute.
            context=(f"ACTIVE DISPUTE: {thread_label}. Read the opponent and the "
                     "procedural role for THIS dispute only: another dispute's "
                     "events, parties and stage are never a source of them.\n"
                     "A representation or task instruction the advocate states for "
                     "the file -- whom they act for, that nothing is filed, that "
                     "they are advising only, what they intend to seek or resist -- "
                     "applies to THIS dispute too unless this dispute's own account "
                     "contradicts it. Quote that instruction where you rely on it.\n"
                     f"Currently recorded opponent: {opponent or 'not established'}. "
                     "Only an express correction in the current message can replace it.\n"
                     + (memory.as_context() if memory is not None else "")),
            context_is="this product's own rendering of the file, "
                       "INCLUDING QUESTIONS WE HAVE ASKED -- one of which "
                       "names both sides of the dispute")
        try:
            res = self._read(
                      posture_reader.build_prompt(quotable),
                      posture_reader.schema_for(quotable), "posture", Tier.ROUTINE)
            metrics.record_call(res)
            metrics.posture_reads += 1
            stated = posture_reader.interpret(quotable, res.data or {})
        except ModelError as exc:
            # FAIL THE READ, NOT THE TURN -- and the gate still blocks, because
            # an unread posture is an unresolved one.
            metrics.fire("G-MODEL", "unavailable",
                         f"posture could not be read: {exc}")
            return posture_reader.UNSTATED
        except Exception as exc:                     # noqa: BLE001
            metrics.violate("C3", f"posture extraction failed: "
                                  f"{type(exc).__name__}: {exc}")
            return posture_reader.UNSTATED

        if stated.refused:
            # The model reported a posture the message does not support. This
            # is an ordinary outcome, recorded so a pattern of it is visible.
            metrics.violate("C3", f"posture extraction refused: {stated.refused}")
        return stated

    def _fetch_late_citations(self, answer, retrieved, turn: TurnInput,
                              metrics: TurnMetrics) -> tuple:
        """B-104. The provisions the answer named and retrieval did not fetch.

        Recomputed from the ANSWER and the RETRIEVED SET rather than parsed
        out of the violation prose. A message written for a person is a bad
        machine input, and `grounding` already owns both halves of this
        judgement -- reading it back out of a sentence would be a second copy
        of the rule that decides what counts as cited.

        Returns only findings that came back USABLE. A provision the corpus
        does not hold cannot ground anything, and fetching it changes nothing
        about whether the turn may be served -- so the turn is withheld as
        before, and the advocate is told what was looked for.
        """
        covered = grounding._covered_provisions(tuple(retrieved))
        wanted: list[tuple[str, str]] = []
        seen: set[str] = set()
        for element in answer.elements:
            if element.disclosure:
                continue
            for number in grounding.provisions_cited(element.text):
                if number not in covered and number not in seen:
                    seen.add(number)
                    # The element's own text carries the Act. Kept WITH the
                    # number so the fetch can name what the answer named.
                    wanted.append((number, element.text[:400]))
        if not wanted:
            return ()

        found: list = []
        for number, sentence in wanted[:2]:
            # TWO AT MOST, and it is the same bound as the round itself. An
            # answer naming eight unretrieved provisions is not a turn one
            # more lookup will rescue; it is a turn that should be withheld.
            # THE SENTENCE THAT CITED IT, NOT THE BARE NUMBER.
            #
            # The first version asked for `f"section {number}"` and retrieval
            # returned NOTHING -- "no Act in the curated manifest governs this
            # question" -- so the round never ran and both withheld turns of
            # GS-15 stayed withheld. Measured afterwards: `section 49` gets 0
            # findings, `Registration Act 1908 section 49` gets 1, and
            # `section 53A Transfer of Property Act` gets 1. Both provisions
            # were held all along.
            #
            # It is CLAUDE.md 5 in its purest form: exact match decides WHICH
            # Act, and a bare section number names none. The Act was in the
            # answer's own sentence and the query threw it away.
            need = EvidenceNeed(
                question=sentence, governing_date=turn.today,
                jurisdiction=turn.jurisdiction, provision_hint=number,
                account="")
            result = self._fetch(need, metrics, exploratory=False)
            found.extend(f for f in result.findings if f.usable)
        return tuple(found)

    def _late_note(self, late: tuple) -> list[Element]:
        """WHAT HAPPENED, said out loud. A second round that is invisible is a
        product that quietly retries until it gets an answer out, which is the
        shape the bound exists to refuse -- and an advocate who cannot see it
        cannot judge it."""
        named = ", ".join(dict.fromkeys(f.ref for f in late if f.ref))
        return [Element(
            kind=ElementKind.GROUND, disclosure=True, signal=Signal.NONE,
            text=(f"My first draft of this answer named {named} without "
                  f"having retrieved it. I fetched it and worked the answer "
                  f"again with the text in front of me. What is below is the "
                  f"second pass, not the first."))]

    def _fetch(self, need: EvidenceNeed, metrics: TurnMetrics, *,
               exploratory: bool = True):
        """One evidence round, counted against the bound.

        Every retrieval goes through here so the count cannot drift from the
        rounds actually run -- incrementing at each call site is how a bound
        stops matching reality.

        `exploratory=False` IS A DIFFERENT BOUND, NOT AN EXEMPTION FROM THIS
        ONE. MAX_EVIDENCE_ROUNDS limits how far a turn may WANDER looking for
        what it needs. B-104's late lookup is not wandering: the answer has
        already named one specific provision, and the lookup either finds that
        provision or does not. Measured on the first run of B-104's fix, the
        ordinary rounds had used all three before the answer was assembled, so
        the named lookup was refused a search it had not asked to compete for
        -- and the advocate got the withheld turn the fix exists to prevent.
        Its own bound is at the call site: at most two provisions, once.

        It is still COUNTED, because a retrieval that happened and is not in
        the count is exactly the drift this docstring warns about.
        """
        if exploratory and metrics.evidence_rounds >= MAX_EVIDENCE_ROUNDS:
            metrics.evidence_bound_hit = True
            return EvidenceResult(
                coverage=Coverage.NOT_ASSESSED,
                missing=(f"the evidence bound of {MAX_EVIDENCE_ROUNDS} rounds "
                         f"was reached before this need could be met, so it was "
                         f"NOT searched."),
                searched_stores=("bound_reached",))
        metrics.evidence_rounds += 1
        return self._evidence.fetch(need)

    def _investigate(self, turn, thread, need, result, metrics, grounds,
                     relied_on, retrieved, concluded) -> None:
        """One bounded model-driven research lane after primary resolution.

        The caller has already admitted the turn and resolved its side. The
        executor cannot invoke other tools, expand the matter, write canonical
        state, replenish its budget or convert its rationale into legal advice.
        Every returned finding crosses the existing coverage/grounding boundary.
        """
        disclosed = False

        def read(prompt, schema):
            reply = self._read(prompt, schema, "investigation", Tier.ROUTINE)
            metrics.record_call(reply)
            return reply.data

        def fetch(query):
            nonlocal disclosed
            if not disclosed:
                self._disclose_coverage(turn, thread, metrics, grounds)
                disclosed = True
            authority = self._fetch(replace(
                need, want_authority=True, question=query), metrics)
            retrieved.extend(authority.findings)
            self._read_coverage(authority, thread, metrics, grounds,
                                relied_on, turn, concluded)
            return authority

        run = investigation.run(
            message=turn.message, account=need.account,
            initial=tuple(result.findings), thread_id=str(thread.id),
            version=turn.expected_version if turn.expected_version is not None else 0,
            round_budget=max(0, MAX_EVIDENCE_ROUNDS - metrics.evidence_rounds),
            read=read, fetch=fetch)
        if run.stop == "budget":
            metrics.evidence_bound_hit = True
        grounds.append(Element(kind=ElementKind.GROUND, thread=thread.id,
                               disclosure=True, text=run.disclosure()))

    def _read_coverage(self, result, thread: Thread, metrics: TurnMetrics,
                       grounds: list[Element], relied_on: list[Finding],
                       turn: TurnInput | None = None,
                       concluded: dict | None = None) -> None:
        """Turn a retrieval result into elements and gate firings.

        THE THREE COVERAGE STATES ARE NOT INTERCHANGEABLE, and the whole point
        of the manifest is that this method can tell them apart:

          ANSWERED        cite it, or say why the Finding cannot be used
          NOT_HELD        an honest gap, NAMED -- disclosed to the advocate
          HELD_NOT_FOUND  a RETRIEVAL DEFECT that escalates. It is never shown
                          to the advocate as though the corpus lacked it
        """
        # Search instrumentation never becomes a legal or advocate decision.
        if result.search_note:
            grounds.append(Element(kind=ElementKind.GROUND, thread=thread.id,
                                   text=result.search_note, disclosure=True))
        if result.coverage is Coverage.SEARCHED_NO_MATCH:
            if not result.search_note:
                grounds.append(Element(kind=ElementKind.GROUND, thread=thread.id,
                                       text=result.missing, disclosure=True))
            return

        # AN INFERENCE THE RETRIEVAL RESTED ON. Disclosed before the
        # findings, because an advocate who is not told which Act was assumed
        # cannot tell a right answer from a right answer to the wrong question.
        if getattr(result, "assumption", None):
            grounds.append(Element(
                kind=ElementKind.GROUND, thread=thread.id,
                text=result.assumption, disclosure=True))

            # AND IT IS RECORDED AS A DECISION, not only said.
            #
            # Routing a cause to an Act is a choice with a reason and, where
            # the graph offers them, alternatives. GS-15 made that choice five
            # times from scratch and disclosed it five times, with nothing
            # checking the answer was the same on turn 5 as on turn 1.
            #
            # Recorded, it can be held stable, shown to have MOVED, and
            # overruled by the advocate in four words -- which is what naming
            # the alternatives was always for.
            # ONLY WHERE THERE IS A TURN AND A PLACE TO PUT IT. The authority
            # round calls this too, and a decision with no turn id is a record
            # nobody can date.
            if turn is None or concluded is None:
                return
            first, _, rest = str(result.assumption).partition(":")
            settled = decision.Decision(
                what=f"the provision this rests on:{rest or ' ' + first}",
                because=first.strip() or "retrieval resolved it",
                at_turn=turn.turn_id, thread=thread.id,
                by=decision.DecidedBy.PRODUCT,
                alternatives=_arguable(result.assumption))
            standing = decision.from_stored(thread.decisions)
            for was, now in decision.moved(standing, (settled,)):
                # A SETTLED QUESTION ANSWERED DIFFERENTLY, with its prior.
                # An advocate shown only the new answer cannot tell it moved.
                grounds.append(Element(
                    kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                    text=(f"This turn resolved the provision differently from "
                          f"the last one. Before: {was.what}. Now: {now.what}. "
                          f"If the earlier one was right, say so and I will "
                          f"hold it.")))
            concluded["decisions"] = decision.merge(standing, (settled,))

        elif (turn is not None and concluded is not None and result.findings
              and result.findings[0].source_kind is SourceKind.PROVISION):
            # THE ADVOCATE RESOLVED IT, so nothing had to be assumed.
            #
            # The branch above discloses an inference and ends by saying
            # "If the earlier one was right, say so and I will hold it."
            # That sentence was an invitation nothing could accept:
            # `DecidedBy.ADVOCATE` has been in the vocabulary since slice
            # 6 and nothing ever constructed one -- measured, its only
            # three occurrences were a comparison, a merge rule and
            # `from_stored`.
            #
            # Reaching here means the retrieval resolved WITHOUT an
            # assumption, which happens when the advocate named the Act.
            # `merge` then refuses to let a later inference overwrite it,
            # which is the rule it was written for.
            named = result.findings[0].ref
            settled = decision.Decision(
                what=f"the provision this rests on: {named}",
                because="the advocate named it",
                at_turn=turn.turn_id, thread=thread.id,
                by=decision.DecidedBy.ADVOCATE)
            standing = decision.from_stored(thread.decisions)

            # E5. WHAT WE INFERRED, OVERRULED, AND DROPPED.
            #
            # Recorded once and NOT restated. The counterexample E5 names
            # is the same objection raised on every turn after they went
            # the other way, and the only thing that brings this back is
            # a FACT -- see `nm.domain.reservation`, where the signature
            # itself refuses a turn id.
            for was, _now in decision.moved(standing, (settled,)):
                if was.by is not decision.DecidedBy.PRODUCT:
                    continue
                concluded["reservations"] = reservation.record(
                    reservation.from_stored(concluded.get(
                        "reservations", ())),
                    reservation.Reservation(
                        position=was.what,
                        because=was.because or "inferred on retrieval",
                        stated_at=was.at_turn,
                        overruled_at=turn.turn_id))

            concluded["decisions"] = decision.merge(standing, (settled,))

        if result.coverage is Coverage.ANSWERED:
            shown = result.findings
            if len(shown) > MAX_AUTHORITIES_SHOWN and any(
                    f.source_kind is SourceKind.AUTHORITY for f in shown):
                # A PRESENTATION cut, at the answer layer, and it is stated.
                # The rest remain retrieved, counted, and available to the
                # grounding gate -- nothing has been discarded.
                shown = shown[:MAX_AUTHORITIES_SHOWN]
                grounds.append(Element(
                    kind=ElementKind.GROUND, thread=thread.id,
                    text=(f"{len(result.findings) - MAX_AUTHORITIES_SHOWN} further "
                          f"attributable paragraph(s) matched and are not shown. "
                          f"They were retrieved, not discarded — ask and I will "
                          f"put them up."),
                    disclosure=True))
            for f in shown:
                if f.usable:
                    relied_on.append(f)
                    # THE SCOPE OF THE TREATMENT CHECK TRAVELS WITH THE
                    # AUTHORITY. "Clean" here means nothing in the 34,037
                    # judgments held treats it adversely -- a statement about
                    # this corpus, not about Indian law -- and an advocate who
                    # is not told the boundary will read it as the wider claim.
                    checked = ""
                    if f.source_kind is SourceKind.AUTHORITY:
                        checked = f" Treatment: {f.treatment.scope}."
                    grounds.append(Element(
                        kind=ElementKind.GROUND, thread=thread.id,
                        text=(f'{f.ref} — "{_excerpt(f.span)}"'
                              f'{" [...]" if _shortened(f.span) else ""} '
                              f"({f.locator}; "
                              f"{f.binding.said} for {f.binding_for} — "
                              f"{f.binding_reason}).{checked}"),
                        refs=(f.locator,), source=capture_source(f)))
                elif f.quotable:
                    # SHOWN, with its status disclosed, and NOT relied on.
                    #
                    # This is the ordinary case for case law, not an error: the
                    # citator covers at most 14.5% of judgments, so nearly every
                    # authority comes back with treatment unverified. Dropping
                    # them would make the whole index worthless; asserting from
                    # them would present an overruled case as good law. Showing
                    # them with the limit stated is what a careful junior does.
                    # NEGATIVE treatment is the one an advocate must not
                    # miss, and it is rare -- 75 judgments in the whole corpus.
                    # Unverified treatment is the norm at 0.84% coverage, so it
                    # gets one clause. Giving both the same weight makes the
                    # rare one invisible.
                    adverse = f.treatment.state is TreatmentState.NEGATIVE
                    limits = []
                    if f.supports is None:
                        limits.append("Whether this passage supports the question "
                                      "has not been assessed.")
                    if not f.binding.assessed:
                        limits.append("Its binding status has not been established.")
                    if adverse:
                        limits.append(f"ADVERSE TREATMENT — {', '.join(f.treatment.verbs)}. "
                                      "Do not rely on this without reading it.")
                    elif not f.treatment.state.usable_alone:
                        limits.append("Not relied on: subsequent treatment unverified.")
                    note = " ".join(limits)
                    grounds.append(Element(
                        kind=ElementKind.GROUND, thread=thread.id,
                        text=(f'{f.ref} — "{_excerpt(f.span)}"'
                              f'{" [...]" if _shortened(f.span) else ""} '
                              f"({f.locator}; "
                              f"{f.binding.said} for {f.binding_for}). {note}"),
                        refs=(f.locator,), source=capture_source(f),
                        signal=Signal.ADVERSE_TREATMENT if adverse else Signal.NONE,
                        disclosure=not adverse))
                else:
                    # Not even quotable — the span does not support what it was
                    # cited for, or the text was not in force. Named, never
                    # silently omitted: silence would leave the advocate
                    # believing nothing was found, which is a different and
                    # false statement about the corpus.
                    grounds.append(Element(
                        kind=ElementKind.GROUND, thread=thread.id,
                        text=(f"{f.ref} was retrieved and is NOT being relied on: "
                              f"{f.blocking_reason}"),
                        refs=(f.locator,), disclosure=True))
            return

        if result.coverage is Coverage.NOT_HELD:
            metrics.fire("G-NOTHELD", "not_held", result.missing or "")
            grounds.append(Element(
                kind=ElementKind.GROUND, thread=thread.id,
                text=(f"Not held in the corpus: {result.missing} I am telling you "
                      f"what is missing rather than answering from memory."),
                disclosure=True))
            return

        if result.coverage is Coverage.NOT_ASSESSED:
            # THE SEARCH DID NOT HAPPEN, and that is its own sentence.
            #
            # This branch exists because the one below used to be the `else`.
            # Any Coverage member added later fell into it and was announced to
            # the advocate as "a defect in my retrieval" -- a state nobody
            # assessed, reported as a state that was assessed and failed. The
            # absent-input shape, arriving by construction rather than by
            # mistake.
            metrics.fire("G-NOTASSESSED", "not_assessed", result.missing or "")
            grounds.append(Element(
                kind=ElementKind.GROUND, thread=thread.id,
                text=(f"This was NOT looked up: {result.missing} I am not "
                      f"telling you the law is silent, and I am not telling "
                      f"you my retrieval failed. Nothing was searched."),
                disclosure=True))
            return

        if result.coverage is Coverage.HELD_NOT_FOUND:
            metrics.fire("G-HELDNOTFOUND", "held_not_found",
                         f"held but not retrieved: {result.missing}")
            grounds.append(Element(
                kind=ElementKind.GROUND, thread=thread.id,
                text=(f"A source this product declares it holds was not "
                      f"retrieved: {result.missing} That is a defect in my "
                      f"retrieval, not a gap in the law, and it is recorded "
                      f"as one."),
                disclosure=True))
            return

        # NO `else`. A member added tomorrow raises here instead of borrowing
        # whichever branch happened to be last -- the same reason `Gate` refuses
        # a row without a third state rather than trusting the author.
        raise AssertionError(
            f"unhandled Coverage member {result.coverage!r}. Every state a "
            f"retrieval can be in has to be SAID to the advocate; falling "
            f"through to the nearest branch tells them something untrue about "
            f"what was searched.")

    @implements("E2")
    @implements("D8")
    def _salvage(self, turn: TurnInput, thread: Thread, result,
                 metrics: TurnMetrics, position) -> list[Element]:
        """D8. Which coordinate can move, BEFORE the claim is called dead.

        *Almost every "you lose" is the failure of one of them, not of the
        case.* The measured original error was advice that a claim was dead
        where a different framing on the same facts was available — so
        `failure_scope` distinguishes **we lose** from **we lose on this
        framing**, and the second is the overwhelming majority.

        AND THE BOUND, WHICH IS THE HARDER HALF. *A system rewarded for always
        finding a way out will invent one.* A route may cite only what this
        turn actually retrieved; anything else is dropped, and dropping it
        takes the route with it because `Salvage` refuses a route resting on
        nothing. That is the intended outcome, not a limitation of the reader.
        """
        retrieved = tuple(dict.fromkeys(
            f.ref for f in result.findings if f.ref))
        why = (f"limitation for our side ran on "
               f"{position.expires_on.isoformat()} under {position.article}")

        try:
            res = self._read(
                      adversarial.build_salvage_prompt(
                    thread.label, why, retrieved),
                      adversarial.SALVAGE_SCHEMA, "salvage", Tier.ROUTINE)
            metrics.record_call(res)
            read = adversarial.read_salvage(res.data or {}, retrieved)
        except ModelError as exc:
            metrics.fire("G-SALVAGE", "not_assessed", str(exc))
            return [Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"I have NOT varied the coordinates of this claim: "
                      f"{exc}. The period has run and nothing here says a "
                      f"different framing is unavailable — nobody looked."))]
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            metrics.violate("D8", f"salvage read failed: "
                                  f"{type(exc).__name__}: {exc}")
            return []

        out: list[Element] = []
        for refused in read.refused:
            # A MANUFACTURED ROUTE, REFUSED AND SAID. Silence here would hide
            # the one behaviour D8 warns about most.
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"I did not offer a way out that rests on nothing: {refused}"))

        for sv in read.considered:
            body = (f"{sv.coordinate.value}: {sv.varied_result}")
            if sv.route:
                body += (f" Route: {sv.route} [{sv.strength.value}; "
                         f"{', '.join(sv.findings)}]")
            out.append(Element(
                kind=ElementKind.FINDING, thread=thread.id, text=body))

        # THE COORDINATES NOBODY MOVED. A report that varied two and concluded
        # the case is dead has not done the work -- and the two it did vary
        # would make it look as though it had.
        left = adversarial.unvaried(read.considered)
        if left:
            metrics.fire("G-SALVAGE", "unvaried", ", ".join(left))
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"{len(left)} of the seven coordinates were not moved: "
                      f"{', '.join(left)}. Those are gaps in the salvage pass, "
                      f"not dimensions that cannot help.")))
        else:
            metrics.fire("G-SALVAGE", "varied", "all seven coordinates moved")

        if read.failure_scope is not adversarial.FailureScope.NOT_ASSESSED:
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=("We lose on THIS FRAMING; a different framing on these "
                      "same facts is set out above."
                      if read.failure_scope is adversarial.FailureScope.FRAMING
                      else "We lose on the case, not merely on this framing.")))
        return out

    @implements("D7")
    def _attacks(self, turn: TurnInput, thread: Thread, memory,
                 metrics: TurnMetrics, *, sources: tuple[Finding, ...] = ()) -> list[Element]:
        """D7. The case the other side will run, on the grounds they will run it.

        A SOFTENED VERSION OF THEIR CASE IS WORTH NOTHING to prepare against,
        so the prompt asks for it at its strongest and the type refuses the
        two ways it degrades: an attack with no answer that does not SAY it
        has none, and one marked unanswerable that stops at the problem.
        Those are different findings — the first is work not done, the second
        is a fact about the case — and D7 requires the second resolved into
        what we DO about it.
        """
        account = memory.account if memory else ""
        if not account.strip():
            return []

        if not any(f.quotable and (f.span or '').strip() for f in sources):
            return [Element(kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                            text="The legal basis for opposing arguments has not yet been "
                                 "retrieved. I have not treated speculative legal arguments "
                                 "as an established answer to this dispute.")]

        try:
            res = self._read(
                      with_evidence(adversarial.build_attack_prompt(
                    account, thread.posture.side.value), sources),
                      adversarial.ATTACK_SCHEMA, "attacks", Tier.ROUTINE)
            metrics.record_call(res)
            read = adversarial.read_attacks(res.data or {}, thread.id)
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"the other side's case was not put: {exc}")
            return [Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"I have not put the other side's case on this thread: "
                      f"{exc}. That is a gap in this turn, not a finding that "
                      f"they have none."))]
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            metrics.violate("D7", f"attack read failed: "
                                  f"{type(exc).__name__}: {exc}")
            return []

        out: list[Element] = []
        for refused in read.refused:
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"I put an attack and could not resolve it: {refused}"))

        put: list[Element] = []
        for a in read.attacks:
            answer = (f"No good answer: {a.no_answer_because}"
                      if a.no_answer else a.our_answer)
            put.append(Element(
                kind=ElementKind.GROUND, thread=thread.id,
                feature="D7",
                text=f"An opposing argument on {a.ground}: {a.their_case} — {answer}"))
        # ONE ITEM THAT NAMES A REMEMBERED AUTHORITY NO LONGER COSTS THE TURN.
        out.extend(self._without_unretrieved(
            put, sources, metrics, thread_id=thread.id,
            what="opposing argument(s)"))

        # E-083. Should be empty, because the type refuses one at construction.
        # Computed anyway: a type guard says nothing about objects decoded from
        # an older store, and this is what a recommendation is measured against.
        left = adversarial.unanswered(read.attacks)
        if left:
            metrics.violate("D7", f"attacks with no answer and no statement "
                                  f"that there is none: {', '.join(left)}")

        if read.state == "none_put" and read.why_not:
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"The other side's case, as I read it: {read.why_not}"))
        return out

    def _without_unretrieved(self, items: list[Element], sources, metrics: TurnMetrics,
                             *, thread_id, what: str) -> list[Element]:
        """A READ'S ITEMS, less any that names authority it was not given.

        THE MEASURED DEFECT, 23 September 2026, live matter 4 -- three
        disputes, one brief. The `attacks` read wrote "(referencing cases like
        National Insurance v. Nicolletta Rohtagi)" into ONE opposing argument.
        It had been told not to supply law from memory, and did. G-GROUND
        caught it -- rightly, and it is the hardest line in this product -- and
        WITHHELD THE WHOLE TURN: the answers on all three disputes, for one
        clause in one item of one read.

        `salvage` already refused this at the read ("discarding routes that
        rest on nothing retrieved"); `attacks`, in the same module, did not.
        One guard on one site -- the shape CLAUDE.md measured on 47 of 52
        register entries.

        THE ITEM GOES; THE TURN IS SERVED. The detector is G-GROUND's own
        (`grounding.unretrieved_authorities`), asked of the SAME sources the
        read was given, which are a subset of what the gate checks against --
        so nothing this keeps can be withheld by the gate for this reason, and
        nothing it drops would have survived the gate. The gate stays exactly
        as it is, as the backstop for everything this does not reach.

        THE DROPPED AUTHORITY IS NOT NAMED TO THE ADVOCATE. It came from model
        memory, and saying it -- even as "the other side may rely on" -- is
        exactly the legal data this product does not supply. It is counted on
        the screen and named only in the encrypted diagnostics.
        """
        pool = tuple(f for f in (sources or ()) if getattr(f, "quotable", True))
        kept: list[Element] = []
        dropped = 0
        for item in items:
            if item.disclosure:
                kept.append(item)
                continue
            named = grounding.unretrieved_authorities(item.text, pool)
            if not named:
                kept.append(item)
                continue
            dropped += 1
            metrics.violate("P1", f"{what}: an item named authority not given to "
                                  f"the read and was left out: "
                                  + ", ".join(f"{k} {n!r}" for k, n in named))
        if dropped:
            kept.append(Element(
                kind=ElementKind.GROUND, thread=thread_id, disclosure=True,
                text=(f"I left out {dropped} {what} on this thread because "
                      f"{'it relied' if dropped == 1 else 'each relied'} on an "
                      f"authority that was not retrieved on this turn. I do not "
                      f"supply authority from memory; the rest of this answer "
                      f"does not rest on it.")))
        return kept

    @implements("D7")
    def _tier_degraded(self, metrics: TurnMetrics) -> list[Element]:
        """A DECISIVE READ RAN ON THE CHEAP TIER, said to the advocate.

        `backend/nm/domain/reads.py`: a decisive read that quietly falls back is the
        same defect as a screen that could not run returning a clean result --
        the answer looks identical and is worth less. `tier_downgrades` has
        been on TurnMetrics since slice 0 and nothing ever read it, so the
        downgrade was recorded where an operator might find it and never where
        the person acting on the answer would.

        ONE LINE PER TURN, not per call. Three decisive reads degrade together
        whenever the tier is absent, and three identical sentences is the
        noise B-090 exists to refuse.
        """
        if not metrics.tier_downgrades:
            return []
        # SAY WHICH CHECK DEGRADED. This sentence assumed every downgrade was a
        # decisive read -- true when those were the only reads on `hard`, false
        # since they were withdrawn on 6 September and the step-consistency
        # read became the one step there. For that read the cost is concrete
        # and measured, and the advocate needs it: on the cheaper model it
        # withholds most sound steps, so a missing next step may be ITS error.
        reads = {d.get("read") or "" for d in metrics.tier_downgrades}
        said = []
        if "consistency" in reads:
            said.append(
                "The check that a recommended step does not contradict what this "
                "answer worked out ran on the cheaper model, because the stronger "
                "one it was measured on is not configured here. On the cheaper "
                "model that check withholds most sound steps, so if no next step "
                "appears below, that may be the check's error rather than a real "
                "conflict.")
        if reads - {"consistency"}:
            said.append(
                "A read measured on the stronger model ran on the cheaper one this "
                "turn, because the stronger one is not configured here. The answer "
                "below is the same shape it would otherwise be and it is worth less "
                "than it looks.")
        return [Element(kind=ElementKind.GROUND, disclosure=True, signal=Signal.NONE,
                        text=" ".join(said))]

    def _decisive_empties(self, metrics: TurnMetrics) -> list[Element]:
        """G-READ. WHICH decisive read answered with nothing, said out loud.

        B-088 GENERALISED. That defect was the correction read returning
        nothing on one run and not the next, and the fix guarded that one
        read: a phrase list that noticed the advocate saying "that is wrong"
        and raised a question. It worked, and it was a patch -- the same
        silence in the `cause` read sends an exact section lookup into the
        wrong statute, and in `factors` it reports a live claim as dead, and
        nothing would have said a word.

        THE POPULATION IS `nm.domain.reads`, which was built for this and had
        no production caller until now. Six reads are decisive on one narrow
        test: does the output change a date, an amount, or which law is read?
        A seventh is covered the day someone declares it.

        WHY IT DISCLOSES RATHER THAN WITHHOLDS. §7.1 withholds a turn for
        exactly three gates, all of them about whether the answer is supported
        by what was RETRIEVED. This is about what was READ from the advocate,
        and the answer may be perfectly good without it -- a turn with no
        dates in it is not a broken turn. What is not acceptable is computing
        confidently and saying nothing, so the advocate is told which read
        came back empty and can supply the missing thing in a sentence.
        """
        empties = getattr(self._model, "empty_decisive", None)
        if not callable(empties):
            return []
        try:
            reads = empties()
        except Exception as exc:  # noqa: BLE001 -- never fail a turn
            metrics.violate("I1", f"the decisive-read check could not run: "
                                  f"{type(exc).__name__}: {exc}")
            return []
        if not reads:
            return []

        metrics.fire("G-READ", "empty",
                     f"decisive read(s) answered with nothing: "
                     f"{', '.join(reads)}")
        named = ", ".join(reads)
        return [Element(
            kind=ElementKind.GROUND, disclosure=True, signal=Signal.NONE,
            text=(f"I read your message for {named} and got nothing back. "
                  f"That is not the same as there being none — it is the "
                  f"read coming up empty, and everything below was worked "
                  f"out without it. If there is something there, tell me in "
                  f"a sentence and I will re-derive."))]

    def _refused_reads(self, metrics: TurnMetrics) -> list[Element]:
        """G-MODEL. WHICH read could not run, said once and by name.

        BK-11, and it is `_empty_reads` applied to the second member of
        its own population. That method exists because guarding ONE read
        was B-088's patch: the same silence in `cause` sends an exact
        section lookup into the wrong statute, and in `factors` it reports
        a live claim as dead.

        A READ THAT COULD NOT RUN IS THE NEIGHBOURING FACT and had nine
        owners, one per `except ModelError` branch. Each fired G-MODEL
        with a detail for the metrics; what the ADVOCATE saw was whatever
        that branch chose to append, which for most of the nine was
        nothing about which read was lost.

        THE SITES KEEP THEIR DEGRADED RETURN. Only the disclosure moves --
        the branch knows what value to fall back to and this does not, and
        collapsing both decisions into one place would be the wrong half
        of the fix.
        """
        refused = getattr(self._model, "refused_reads", None)
        if not callable(refused):
            return []
        try:
            reads = refused()
        except Exception as exc:  # noqa: BLE001 -- never fail a turn
            metrics.violate("I1", f"the refused-read check could not run: "
                                  f"{type(exc).__name__}: {exc}")
            return []
        if not reads:
            return []

        named = ", ".join(reads)
        return [Element(
            kind=ElementKind.GROUND, disclosure=True, signal=Signal.NONE,
            text=(f"{len(reads)} read(s) on this turn COULD NOT RUN: "
                  f"{named}. Whatever each of those feeds is missing from "
                  f"the answer below — not found to be absent, not "
                  f"looked at. Nothing here has been recorded as advice "
                  f"on their account."))]

    def _exposure(self, matter: Matter, metrics: TurnMetrics,
                  born_together: frozenset[str] = frozenset(),
                  ) -> list[Element]:
        """E-082. ONE report per file, whatever the answer.

        A SINGLE-THREAD FILE STILL GETS ONE, saying none was found, because
        there is no pair for an exposure to exist in. A section that appears
        only sometimes is one the advocate cannot rely on being there — and
        cannot distinguish from one that found nothing.
        """
        # THREADS BORN TOGETHER ARE NOT YET TWO DISPUTES.
        #
        # `born_together` is the set created by ONE message on THIS turn.
        # The count read that creates them measures 2-3 of 6 and is
        # unstable on identical input (J-4), so a brief describing one
        # claim can arrive here as three threads -- and this pass then
        # reported a contradiction between two halves of one transaction.
        #
        # Only that PAIR is withheld. A thread created this turn is still
        # compared against everything already on the file, which is the
        # comparison worth having.
        considered = tuple(t for t in matter.threads
                           if t.id not in born_together)
        if len(born_together) == 1:
            # One new thread is not a split. Nothing to hold back.
            considered = tuple(matter.threads)
        elif born_together:
            # Keep ONE of them, so a genuine new dispute is still weighed
            # against the standing file rather than vanishing from the
            # pass entirely.
            first = next((t for t in matter.threads
                          if t.id in born_together), None)
            if first is not None:
                considered = (*considered, first)

        threads = tuple(t.id for t in considered)
        positions = tuple({"thread": t.id,
                           "facts": [{"id": f.id, "statement": f.statement,
                                      "certainty": f.certainty.value,
                                      "source": f.provenance.kind,
                                      "date": str(f.date) if f.date else None}
                                     for f in chronology.chart(matter.facts, t.chronology)],
                           "role": t.posture.role.value,
                           "role_basis": t.posture.basis.value}
                          for t in considered)

        found: tuple | None
        if len(threads) < 2:
            # NOT a skip. `cross_thread` returns NONE_FOUND for a single-thread
            # file, which is a finding: there is no pair.
            found = ()
        elif any(not p["facts"] for p in positions):
            # A title and role are not substantive positions. No empty-population
            # "nothing found" verdict, and no model call can manufacture the input.
            found = None
        else:
            try:
                res = self._read(
                          adversarial.build_exposure_prompt(
                        tuple((t.id, t.label) for t in considered), positions),
                          adversarial.EXPOSURE_SCHEMA, "exposure", Tier.ROUTINE)
                metrics.record_call(res)
                found = adversarial.read_exposures(res.data or {}, threads, positions)
                if found is not None:
                    labels = {t.id: t.label for t in considered}
                    found = tuple(replace(e,
                        what=adversarial.labelled_text(e.what, labels),
                        consequence=adversarial.labelled_text(e.consequence, labels))
                        for e in found)
            except ModelError as exc:
                metrics.fire("G-MODEL", "unavailable",
                             f"the cross-file pass did not run: {exc}")
                found = None
            except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
                metrics.violate("D7", f"exposure read failed: "
                                      f"{type(exc).__name__}: {exc}")
                found = None

        report = adversarial.cross_thread(threads, found)
        metrics.fire("G-EXPOSURE", report.state.value,
                     f"{len(report.exposures)} exposure(s)")

        if report.state is adversarial.ExposureState.NOT_RUN:
            return [Element(
                kind=ElementKind.GROUND, disclosure=True,
                text=("I could not establish a complete comparison between these disputes. "
                      "The available positions or the returned assessment were incomplete. "
                      "This does not establish that the disputes are consistent with each other."))]

        if report.state is adversarial.ExposureState.NONE_FOUND:
            held = len(born_together) - 1 if len(born_together) > 1 else 0
            return [Element(
                kind=ElementKind.GROUND, disclosure=True,
                text=("Across this file: I looked for a position on one "
                      "dispute that damages another and found none."
                      + (f" {held} thread(s) opened by this one message "
                         f"were not weighed against each other -- nothing "
                         f"has confirmed yet that they are separate "
                         f"disputes." if held else "")))]

        # LABELS, NEVER IDS. `{e.from_thread}` is a ThreadId and this
        # Structured endpoints use IDs; every prose field is labelled before
        # this point. A rejected field makes the whole comparison unassessed.
        labels = {t.id: t.label for t in matter.threads}
        return [Element(
            kind=ElementKind.GROUND, disclosure=False, signal=Signal.CONTRADICTION,
            text=(f"Across this file: {e.what} on "
                  f"{_label_of(e.from_thread, labels)} — "
                  f"{e.consequence} on {_label_of(e.to_thread, labels)}."))
            for e in report.exposures]

    @implements("D6")
    def _theory(self, turn: TurnInput, thread: Thread, memory,
                metrics: TurnMetrics, facts: tuple[Fact, ...],
                concluded: dict, *, sources: tuple[Finding, ...] = ()) -> list[Element]:
        """D6. One theory per thread, and every adverse fact accounted for.

        TWO READS, AND THE ORDER IS THE MECHANISM. The adverse facts are read
        FIRST, from the chronology, without the model knowing what theory will
        be built on them. If one read produced both, the theory would choose
        its own population -- it would name three adverse facts and account
        for three, every time, and `unaccounted` could not fail. Same argument
        the factor read makes about the un-extended expiry: the thing being
        tested against has to exist before the thing being tested.

        E-080'S COUNTEREXAMPLE IS *a theory that works only if three documents
        are forgotten*, and it reads perfectly because the three are simply
        not mentioned. Absence is invisible; this makes it a list, by name.
        """
        chart = chronology.chart(facts, thread.chronology)
        if not chart:
            return []
        account = memory.account if memory else ""

        try:
            adverse_said = self._read(
                # THE POSTURE, because `adverse to the client` is
                # unanswerable without it. It is already resolved on the
                # thread by the time this runs.
                with_evidence(theory_reader.build_adverse_prompt(
                    account, chart, thread.posture.side.value), sources),
                theory_reader.ADVERSE_SCHEMA, "adverse", Tier.ROUTINE)
            metrics.record_call(adverse_said)
            adverse, why = theory_reader.read_adverse(
                adverse_said.data or {}, chart)

            lines = tuple(f"{fid}: {next(f.statement for f in chart if f.id == fid)}"
                          f" — {why.get(fid, '')}" for fid in adverse)
            said = self._read(
                       with_evidence(theory_reader.build_theory_prompt(
                    account, lines, thread.posture.side.value,
                    standing=theory_reader.from_stored(thread.theory)), sources),
                       theory_reader.THEORY_SCHEMA, "theory", Tier.ROUTINE)
            metrics.record_call(said)
            read = theory_reader.read_theory(
                said.data or {}, thread.id, thread.posture.side, adverse)
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"no theory could be formed: {exc}")
            metrics.fire("G-ADVERSE", "not_assessed",
                         "no theory was formed on this turn")
            return [Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"I have not formed a theory on this thread: {exc}. "
                      f"Nothing here has been weighed against the adverse "
                      f"facts."))]
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            metrics.violate("D6", f"theory read failed: "
                                  f"{type(exc).__name__}: {exc}")
            return []

        out: list[Element] = []
        if read.refused:
            # THE TYPE REFUSED IT and the advocate is told, because what was
            # refused is usually "the complainant has not proved his case" --
            # a hope that the other side fails, handed back as though it were
            # a theory.
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"I did not take the theory that was formed: {read.refused}"))
        elif read.theory is not None:
            t = read.theory
            # WHAT CHANGED, AND WHY -- or nothing, which is the ordinary case
            # and the one that was impossible before. A theory that is the
            # same as last turn's says so by saying nothing.
            moved = ""
            was = theory_reader.from_stored(thread.theory)
            if was is not None and t.revises_because:
                moved = f" (revised: {t.revises_because})"
            elif was is not None and t.theme != was.theme:
                # CHANGED WITH NO REASON GIVEN. Disclosed rather than
                # accepted quietly: the read was shown the standing theory
                # and told to name what stopped fitting, and it did not.
                moved = (" (this differs from the theory on the file and no "
                         "reason was given for the change)")
            stated = Element(
                kind=ElementKind.FINDING, thread=thread.id,
                text=(f"Theory: {t.theme}"
                      + (f" Relief: {t.relief}." if t.relief else "")
                      + moved))
            # THE SAME FILTER AS THE ATTACKS, and here it also decides what is
            # KEPT. A theory is stored and fed back as the standing theory on
            # every later turn, so dropping only the element would leave a
            # remembered authority on the file to be re-read and re-served.
            # A theory resting on authority the read was not given is not
            # taken -- the outcome the `read.refused` path above already has.
            shown = self._without_unretrieved(
                [stated], sources, metrics, thread_id=thread.id, what="theory")
            if stated in shown:
                # WHAT THE TURN CONCLUDED, kept so the next turn revises it
                # rather than rebuilding it. This is the whole of Phase 1.
                concluded["theory"] = t
            out.extend(shown)

        # E-080. THE ADVERSE FACTS NOBODY ANSWERED, BY NAME.
        left = theory_reader.unaccounted(read.adverse, read.theory)
        unresolved = read.theory.unresolved if read.theory else {}
        if unresolved:
            metrics.fire("G-ADVERSE", "unaccounted", ", ".join(unresolved))
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id,
                text="Adverse points remain open: " + "; ".join(
                    f"{next((f.statement for f in chart if f.id == fid), 'Recorded proposition')}: "
                    f"{reason}" for fid, reason in unresolved.items())))
        if left:
            metrics.fire("G-ADVERSE", "unaccounted", ", ".join(left))
            named = "; ".join(
                next((snippet(f.statement, 70) for f in chart if f.id == fid), fid)
                for fid in left)
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"{len(left)} adverse fact(s) on this thread are neither "
                      f"explained nor conceded by the theory: {named}. A "
                      f"theory that works only because these went unmentioned "
                      f"reads perfectly and loses.")))
        elif not unresolved:
            # THE CLEAN STATE, SAID -- E-082's rule, applied to the gate
            # next door. `_exposure` already says "I looked ... and found
            # none" on a file with no exposure, and this said nothing at
            # all: an advocate seeing a theory with no adverse line could
            # not tell whether the facts were weighed and answered,
            # whether none were found, or whether nobody looked. Three
            # declared states, two of them audible.
            #
            # AND IT DID NOT FIRE AT ALL when the read found no adverse
            # facts, because the branch was `elif read.adverse`. A gate
            # that is silent on its own clean state cannot be told from
            # one that was never reached.
            metrics.fire("G-ADVERSE", "accounted",
                         f"{len(read.adverse)} adverse fact(s) accounted for")
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"I weighed the theory against {len(read.adverse)} "
                      f"adverse fact(s) on this thread and each is either "
                      f"explained or conceded."
                      if read.adverse else
                      "I looked for facts on this thread that cut against "
                      "the theory and found none. That is a finding about "
                      "what is on the file, not a view that the case is "
                      "unopposed.")))

        if read.state == "none_formed" and read.why_not:
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"No theory formed yet: {read.why_not}"))
        return out

    def _load_bearing(self, matter: Matter, thread) -> frozenset[str]:
        """Facts a LIVE DERIVATION rests on. These are never trimmed away.

        This is what recording derivations bought that was not obvious: the
        product now knows which facts it actually USED to compute something,
        so it can refuse to forget exactly those. A fact that a limitation
        position or an issue set rests on is not an old sentence — it is an
        input to a number the advocate is acting on.

        Read from the last recorded turn, because that is where the previous
        derivations are; this turn's are not computed yet when the account is
        built, which is the ordering that makes the account available to the
        reads in the first place.
        """
        if thread is None or not hasattr(self._store, "transcripts_for"):
            return frozenset()
        try:
            past = self._store.transcripts_for(matter.id)
        except Exception:  # noqa: BLE001 -- an unreadable record pins nothing
            return frozenset()
        for doc in reversed(past):
            if doc.get("unreadable") or "derived" not in doc:
                continue
            return frozenset(
                fid for row in (doc.get("derived") or [])
                for fid in (row.get("from_facts") or []))
        return frozenset()

    @implements("A3")
    def _derived_now(self, thread: Thread, position) -> tuple:
        """What this turn computed, and WHICH FACTS each value rests on.

        `from_facts` is what makes the cascade possible at all: without it a
        correction has to re-run everything and cannot say what it touched.
        """
        # A CONDITIONAL FIGURE IS A VALUE THE ADVOCATE WAS SHOWN, so it is
        # recorded too. It was not, and a corrected date then moved the served
        # figure with no G-CASCADE and no prior -- E-092's defect, "silently
        # moving a limitation date", on the path every first turn takes since
        # a model-selected accrual became conditional (602e3f0).
        #
        # ONE KEY, THE STATE IN THE VALUE. A conditional figure moving is
        # reported with its prior; the same date later CONFIRMED reads as a
        # change from "(conditional)" to definitive, which is news; and a
        # separate key would make confirmation look like the conditional
        # figure being LOST.
        if position is None or position.expires_on is None:
            return ()
        if position.state is limitation.LimitationState.COMPUTED:
            value = position.expires_on.isoformat()
        elif position.state is limitation.LimitationState.CONDITIONAL:
            value = f"{position.expires_on.isoformat()} (conditional)"
        else:
            return ()
        return (cascade.Derived(
            name=f"limitation on {thread.id}",
            shown=f"the limitation on {dispute(thread.label)}",
            value=value,
            from_facts=tuple(thread.chronology)),)

    @implements("A3")
    def _cascade(self, thread: Thread, matter_id: str, derived: tuple,
                 metrics: TurnMetrics, gaps: list) -> list[Element]:
        """A3 §5.4. What MOVED since the last turn, and what rested on it.

        THE BOUND IS AS IMPORTANT AS THE CASCADE. *Where re-derivation changes
        nothing the answer is one line* — a product that announced a cascade
        every turn would train the advocate to skip the section, and the real
        one would arrive in a place they had learned to ignore. So nothing is
        emitted at all where nothing moved, and the one-line form is kept for
        the turn that FOLLOWS a correction.

        A VALUE THAT APPEARS is a change with no prior and is reported as one.
        Silently adding a limitation date is the same defect as silently
        moving one.
        """
        if not derived:
            return []

        before = self._last_derived(matter_id)
        if before is None:
            # FIRST TURN ON THIS THREAD. Nothing has moved because there was
            # nothing to move from — which is not the same as "re-derived and
            # nothing changed", and saying the second would be a claim about a
            # comparison nobody made.
            return []

        moved = cascade.changes(before, derived)

        # WHAT STOPPED BEING DERIVED. `changes` walks `after` and cannot see
        # this: a value present before and absent now produces nothing from
        # it. Most of what the product derives is re-read from scratch every
        # turn, so a read that found three issues on turn 2 and nothing on
        # turn 9 does not fail — it succeeds, quietly, with less.
        gone = cascade.lost(before, derived)
        if gone:
            metrics.fire("G-CONSERVE", "lost", ", ".join(d.name for d in gone))
            out = [Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                signal=Signal.CONTRADICTION,
                text=("This turn derived LESS than the last one. "
                      # `shown`, NEVER THE KEY -- the same rule `report` and
                      # `unresolved_undo` follow (B-103). This path used the
                      # key and nothing reached it until a conditional figure
                      # could be recorded and then not recomputed.
                      + "; ".join(f"{d.shown or d.name} was {d.value} and is "
                                  f"not computed now" for d in gone)
                      + ". Nothing on the file was withdrawn — the reading "
                        "simply did not produce it this turn, and it is said "
                        "rather than left as a thinner answer."))]
            # AND IT BLOCKS, because a silently thinner answer is the failure
            # this whole mechanism exists to make impossible.
            gaps.append(gap_queue.Gap(
                what=(f"whether {gone[0].shown or gone[0].name} still holds "
                      f"— it was computed before and not on this turn"),
                blocks="relying on this turn as a complete picture",
                thread=thread.id,
                kind=gap_queue.GapKind.BLOCKING_GATE))
        else:
            # `complete` IS FIRED, not merely declared. A state in the matrix
            # that no code path reaches is a state that does not exist, and
            # the matrix would be telling the advocate something is checked
            # when nothing checks it.
            metrics.fire("G-CONSERVE", "complete",
                         f"{len(derived)} derivation(s) still computed")
            out = []

        if not moved:
            return out

        metrics.fire("G-CASCADE", "moved", ", ".join(c.name for c in moved))
        lines = cascade.report(moved)

        # NOBODY SAID WHETHER ANYTHING NEEDS UNDOING, and empty is not "no".
        # An advocate who filed on Tuesday against a date that moved on
        # Thursday needs to be told; showing them a corrected number is not
        # telling them.
        for name in cascade.unresolved_undo(moved):
            gaps.append(gap_queue.Gap(
                what=f"whether anything already done on {name} needs undoing",
                blocks="relying on advice given before it moved",
                thread=thread.id,
                kind=gap_queue.GapKind.BLOCKING_GATE))

        return [*out, Element(
            kind=ElementKind.FINDING, thread=thread.id,
            signal=Signal.CONTRADICTION,
            # B-102. THE HEADING MUST BE TRUE OF EVERY LINE UNDER IT, which
            # is B-093's rule arriving in a different place. "A value has
            # MOVED" over a value computed for the first time is a claim about
            # the file that is simply false, and it is the loudest line on the
            # turn.
            text=("A value on this thread has MOVED since the last turn. "
                  if any(not c.arrived for c in moved)
                  else "This thread now has a value it did not have before. ")
                 + " ".join(lines))]

    def _last_derived(self, matter_id: str) -> tuple | None:
        """The previous turn's derived values, or `None` if there is no
        previous turn to compare against.

        `None` AND `()` ARE DIFFERENT. An empty tuple is a turn that derived
        nothing; `None` is no turn at all, and treating them alike would
        report every first computation on a thread as a change.
        """
        # THE MATTER ID IS PASSED IN, NOT GUESSED OFF THE THREAD.
        #
        # This read `thread.matter_id`, which `Thread` does not have — so it
        # degraded SILENTLY to `None` and the cascade could never fire. The
        # same mistake the factor read made and had corrected an hour earlier:
        # a `getattr` against a type this module already imports is a guess
        # that fails quietly, in the direction of doing nothing at all.
        if not matter_id or not hasattr(self._store, "transcripts_for"):
            return None
        try:
            past = self._store.transcripts_for(matter_id)
        except Exception:  # noqa: BLE001 -- an unreadable record is not a change
            return None
        for doc in reversed(past):
            if doc.get("unreadable") or "derived" not in doc:
                continue
            rows = doc.get("derived") or []
            return tuple(cascade.Derived(
                name=str(r.get("name", "")), value=str(r.get("value", "")),
                # AN OLDER TRANSCRIPT HAS NO LABEL, and `shown` falls back to
                # `name` rather than being invented here -- a reconstructed
                # label would be a different string from the one the earlier
                # turn actually showed.
                shown=str(r.get("shown") or ""),
                from_facts=tuple(r.get("from_facts") or ()))
                for r in rows if r.get("name"))
        return None

    # ------------------------------------------------------ currency (P18) ---

    @implements("A3")
    def _currency_inputs(self, matter: Matter, turn: TurnInput,
                         metrics: TurnMetrics) -> Matter:
        """Observe every fact on the file and invalidate what a change reached.

        BK-65-AC1's first clause, at the seam where it bites: after ADMIT-B
        has recorded this turn's facts and corrections, before DERIVE reads
        them. `dependency.sync_inputs` is the one observer; the served
        correction route calls the same function, so a correction typed into
        the case file and one spoken into the brief invalidate identically.

        NOTHING HERE DECIDES WHAT "MOVED" MEANS. The digest does, once, in
        `dependency.fact_digest`.
        """
        ledger = dependency.Ledger.from_stored(matter.dependencies)
        ledger, affected, moved = dependency.sync_inputs(
            ledger, matter,
            reason=f"corrected by the advocate on {turn.today.isoformat()}",
            at=turn.today.isoformat(), by=turn.advocate_id)
        # A SOURCE THE PUBLICATION LAYER WITHDREW (P20 → P21 → P18). Every
        # passage attached to this file names the version it was read from;
        # one the generation has since withdrawn is marked WITHDRAWN on the
        # ledger, and the closure resting on it goes stale here -- the only
        # place the file is re-read against the corpus as it now stands.
        withdrawn = self._withdrawn_sources()
        if withdrawn:
            gone: list[dependency.Rest] = []
            for row in getattr(matter, "research", ()) or ():
                for a in (row.get("reliances") or ()) if isinstance(row, dict) else ():
                    ledger_id = str(a.get("ledger_id") or "")
                    if not ledger_id or str(a.get("source_version") or "") not in withdrawn:
                        continue
                    tracked = ledger.input_of(dependency.InputKind.AUTHORITY, ledger_id)
                    if tracked is None or tracked.withdrawn:
                        continue
                    ledger, did = dependency.observe(
                        ledger, dependency.InputKind.AUTHORITY, ledger_id,
                        tracked.digest, reason="withdrawn by the publication layer",
                        withdrawn=True)
                    if did:
                        after = ledger.input_of(dependency.InputKind.AUTHORITY, ledger_id)
                        gone.append(dependency.Rest(dependency.InputKind.AUTHORITY,
                                                    ledger_id, after.version if after else 0))
            if gone:
                ledger, hit = dependency.invalidate(
                    ledger, tuple(gone), reason="the source was withdrawn",
                    at=turn.today.isoformat())
                affected = (*affected, *hit)
                moved = (*moved, *gone)
        if affected:
            metrics.fire("G-CURRENCY", "stale",
                         f"{len(moved)} input(s) moved; "
                         f"{', '.join(affected)} must be recomputed")
        return replace(matter, dependencies=ledger.as_dict())

    def _withdrawn_sources(self) -> frozenset[str]:
        """What the evidence plane says has been withdrawn. A port method with
        a default, so a double that predates it answers `frozenset()` -- an
        installation with no generation, not a clean bill."""
        try:
            return frozenset(self._evidence.withdrawn_sources())
        except Exception as exc:  # noqa: BLE001 -- an unreadable event log is
            # a refusal to say, and it is logged; it must not read as "none".
            import logging

            logging.getLogger(__name__).error(
                "withdrawn_sources could not be read: %s", exc, exc_info=True)
            return frozenset()

    @implements("A3")
    def _currency_settle(self, matter: Matter, thread: Thread | None,
                         derived: tuple, concluded: dict, retrieved: tuple,
                         turn: TurnInput, metrics: TurnMetrics, *,
                         attempted: bool = True,
                         ) -> tuple[Matter, list[Element]]:
        """Record this turn's conclusions against their inputs; rework the stale.

        THE NODES, and what each rests on -- enumerated here because this is
        the one place the turn knows all three at once:

            limitation on {thread}    FACT: every live chronology entry (the
                                      `cascade.Derived.from_facts` the turn
                                      already builds); AUTHORITY: the Article
                                      it was read from, keyed on its locator.
            limitation deadline       DERIVED: the limitation. The transitive
                                      edge `cascade` cannot express.
            party role                FACT: the statement the role was read
                                      from. Independent of the chronology,
                                      which is what makes EVAL-010's second
                                      half provable on one thread.

        A NODE THE TURN COULD NOT RECOMPUTE IS FAILED, NOT FORGOTTEN. The
        limitation that went NOT_COMPUTED after a date was withdrawn leaves a
        stale node with one more attempt against its bound, and the advocate
        is told; a loop that only recorded what it produced would leave it
        stale with no attempts forever.

        THE DISCLOSURE IS THE ANSWER'S, NOT THE METRICS'. Whatever is still
        stale when this turn is done is said in an element, because a
        currency the advocate cannot see is a currency they will act against.
        """
        if thread is None:
            return matter, []
        ledger = dependency.Ledger.from_stored(matter.dependencies)
        names = dependency.names_for(thread.id)
        at = turn.today.isoformat()
        produced: list[dependency.Node] = []

        # THE AUTHORITIES THIS TURN READ ARE OBSERVED BEFORE THE NODES ARE
        # STAMPED, so an Article edge carries the version the ledger tracks
        # rather than 0 -- and a provision whose text moved since the last
        # turn invalidates what rested on it HERE, where the same turn then
        # recomputes it. Facts were observed after ADMIT-B; observing them
        # again costs a digest comparison and moves nothing.
        ledger, affected, _moved = dependency.sync_inputs(
            ledger, matter, retrieved,
            reason=f"the retrieved text moved before {turn.today.isoformat()}",
            at=at)
        if affected:
            metrics.fire("G-CURRENCY", "stale",
                         f"a retrieved authority moved; {', '.join(affected)} "
                         f"must be recomputed")

        # THE LIMITATION, through the one bridge. Its authority edge is the
        # Article `_limitation` read the period from, matched on the ref the
        # position carries, so the node names the exact text it rests on.
        limitation_row = next(
            (d for d in derived if d.name == names.limitation), None)
        if limitation_row is not None:
            article = None
            register = concluded.get("deadlines") or ()
            source = next((d.source for d in register
                           if getattr(d, "thread", None) == thread.id), "")
            for finding in retrieved:
                if source and finding.ref == source:
                    article = finding
                    break
            produced.append(dependency.from_derived(
                limitation_row,
                authorities=((dependency.authority_id(article),)
                             if article is not None else ()),
                # NO ARTICLE MATCHED IS SAID, NOT ASSUMED AWAY. A limitation
                # computed from a provision nothing can name rests on
                # something the product cannot track.
                unknown=article is None,
                reason=f"computed on {at}", at=at))

        # THE DEADLINE, resting on the limitation -- the edge that makes a
        # corrected date reach the register two hops away.
        for row in concluded.get("deadlines") or ():
            if getattr(row, "thread", None) != thread.id:
                continue
            if getattr(row, "kind", None) is not deadlines.DeadlineKind.LIMITATION:
                continue
            if row.on is None:
                continue
            produced.append(dependency.Node(
                name=names.deadline, value=row.on.isoformat(),
                shown=f"the limitation deadline on {dispute(thread.label)}",
                rests_on=(dependency.Rest(dependency.InputKind.DERIVED,
                                          names.limitation),),
                computed_at=at, reason=f"computed on {at}"))
            break

        # THE ROLE, resting on the statement it was read from.
        posture = thread.posture
        if posture.resolved:
            rests = ((dependency.Rest(dependency.InputKind.FACT,
                                      str(posture.source_fact)),)
                     if posture.source_fact else ())
            produced.append(dependency.Node(
                name=names.role, value=posture.role.value,
                shown=f"our side on {dispute(thread.label)}", rests_on=rests,
                computed_at=at, reason=f"read on {at}"))

        ledger = dependency.settle(
            ledger, tuple(produced),
            expected=((names.limitation, names.deadline, names.role)
                      if attempted else ()), at=at,
            why_missing=("this turn did not compute the value -- the position "
                         "says why"))

        stale = [n for n in ledger.stale()
                 if n.name in (names.limitation, names.deadline, names.role)]
        notes: list[Element] = []
        if stale:
            metrics.fire("G-CURRENCY", "stale", "; ".join(
                f"{n.label}: {n.currency.value}" for n in stale))
            notes.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                gate="G-CURRENCY", signal=Signal.CONTRADICTION,
                text=("Not current on this thread: "
                      + " ".join(dependency.report(dependency.Ledger(
                          nodes=tuple(stale))))
                      + " Nothing above relies on those values as they stood.")))
        elif produced:
            metrics.fire("G-CURRENCY", "current",
                         f"{len(produced)} conclusion(s) recorded against "
                         f"their inputs")
        else:
            metrics.fire("G-CURRENCY", "not_assessed",
                         "this turn derived no value whose currency is tracked")
        return replace(matter, dependencies=ledger.as_dict()), notes

    @implements("A3")
    def _ask(self, gaps: list, thread: Thread,
             metrics: TurnMetrics) -> list[Element]:
        """A3 §5.2-5.3. ONE BATCHED ASK on this thread, then what is still open.

        NOTHING IS OWED WHEN NOTHING IS BLOCKED. `leads` returns `None` on an
        empty queue and this returns nothing, which is §5.2's whole design:
        *there is no obligation to ask something in order to advance, because
        there is nothing to advance.* A queue that always yields something is
        the manufactured question with a data structure behind it.

        SERIAL SINGLE QUESTIONS MAKE THE ADVOCATE DO THE SCHEDULING, so the
        gaps on this thread go out together and the advocate answers a dispute
        in one go rather than ping-ponging across five.

        AND THE QUEUE IS ADVICE, NOT A RAIL. §5.3: where the highest-value gap
        is on ANOTHER thread, that is said as a note and the answer stays on
        the thread the advocate asked about. A build that passes its stages by
        railroading the advocate through them has failed.
        """
        if not gaps:
            return []

        out: list[Element] = []
        mine = gap_queue.batched(tuple(gaps), thread.id)
        if mine:
            out.append(Element(
                kind=ElementKind.QUESTION, thread=thread.id,
                gate="G-GAP",
                text=("To take this further I need: "
                      + "; ".join(g.what for g in mine) + ".")))

        # §5.3, and it is carried rather than obeyed.
        top = gap_queue.leads(tuple(gaps))
        if top is not None and top.thread != thread.id:
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"The most urgent thing on this file is on another "
                      f"thread: {top.what} — needed for: {top.blocks}. I have "
                      f"answered here because that is what you asked about.")))

        # §5.2's closing line: *still missing, and why it matters*. It is what
        # stops an assessment reading as more settled than it is.
        metrics.fire("G-GAP", "open", f"{len(gaps)} gap(s)")
        out.append(Element(
            kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
            text=("Still missing: "
                  + "; ".join(gap_queue.still_missing(tuple(gaps))) + ".")))
        return out

    @implements("C7")
    def _inventory(self, turn: TurnInput, thread: Thread, memory,
                   metrics: TurnMetrics,
                   gaps: list, concluded: dict) -> list[Element]:
        """C7. The inventory, and the three sweeps over it.

        THE COUNTEREXAMPLE IS THE POINT: *a file where the original agreement
        is with the opponent\'s brother and no preservation or production step
        exists.* The item is inventoried, its holder is recorded, and nothing
        was ever asked of anyone — so the file reads as worked and the
        document is gone by the time it is needed.

        `unpreserved` becomes a QUESTION rather than a note, because a
        question BLOCKS an action and a note does not. An advocate reading
        "no preservation step is recorded" at the bottom of an answer has been
        told; an advocate who cannot proceed until they say who is writing to
        whom has been stopped.
        """
        account = memory.account if memory else ""
        if not account.strip() and not turn.message.strip():
            return []

        try:
            # THE NOTES, NOT THE ACCOUNT (B-115). What evidence exists and
            # who holds it does not turn on a date stamp, so the rendering
            # was a second copy of the sentences already in `file`.
            quotable = Quotable(
                turn=turn.message,
                file=memory.advocate_words if memory else "",
                context=memory.notes if memory else "",
                context_is="notes this product wrote about the file")
            standing = inventory.from_stored(thread.evidence)
            res = self._read(
                      inventory.build_inventory_prompt(quotable, standing),
                      inventory.INVENTORY_SCHEMA, "inventory", Tier.ROUTINE)
            metrics.record_call(res)
            read = inventory.read_inventory(res.data or {}, quotable,
                                            standing)
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"the evidence could not be inventoried: {exc}")
            # THE THIRD STATE, FIRED. G-PRESERVE declares `not_assessed` and a
            # declared state nothing reaches is a state that does not exist —
            # the advocate would see no preservation question and have no way
            # to tell that from nothing being at risk.
            metrics.fire("G-PRESERVE", "not_assessed",
                         "the inventory could not be read on this turn")
            return [Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"I have not inventoried the evidence on this file: "
                      f"{exc}. That is a gap in this turn, not a finding that "
                      f"there is none."))]
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            metrics.violate("C7", f"inventory read failed: "
                                  f"{type(exc).__name__}: {exc}")
            return []

        # MERGED, NOT REPLACED. Measured going 2, 2, 1, 0, 2 across five turns
        # with nothing happening to the evidence: an item the read did not
        # mention was simply gone. `Preservation` makes it worse than untidy
        # -- it records that a step was TAKEN, which is history and not
        # re-derivable, so losing it means G-PRESERVE asks a question the
        # advocate has already answered.
        live = inventory.merge(standing, read.items)
        concluded["evidence"] = live

        out: list[Element] = []
        for refused in read.refused:
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"I did not take one item the reading offered: {refused}"))

        # WHAT CHANGED, NOT THE WHOLE LIST. E-093: *length growing with turn
        # count -- recitation bloat returning.* Persisting the inventory made
        # every turn recite one more item than the last (13, 13, 14, 15, 16 on
        # one thread), and the failure is agreeable: restating context reads
        # as thorough, and by turn eight the advocate is scrolling past their
        # own file to find the answer.
        #
        # Persisting and reciting are different things. The turn was doing the
        # second because it had never had the first.
        was = {i.id: i for i in standing}
        carried = 0
        for item in live:
            prior = was.get(item.id)
            if prior is not None and (
                    (prior.what, prior.holder, prior.form)
                    == (item.what, item.holder, item.form)):
                carried += 1
                continue
            out.append(Element(
                kind=ElementKind.FINDING, thread=thread.id,
                # A SENTENCE, NOT TWO IDENTIFIERS. This read "the sale
                # agreement — held by third_party, certified_copy".
                feature="C7",
                text=(f"{item.what} — {item.holder.said} has it, and "
                      f"what exists is {item.form.said}.")))
        if carried:
            # ONE LINE, CONSTANT. Silence would leave the advocate unable to
            # tell a short list from a short answer, which is the third state
            # going missing in the place it is easiest to miss.
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"{carried} item(s) already on the file are unchanged "
                      f"and not repeated here.")))

        # AT RISK AND NOBODY ASKED. This is the whole feature -- and it goes
        # into the GAP QUEUE rather than straight into the answer.
        #
        # §5.1: a senior does not run a script, they ask the question that
        # matters most next. A question emitted where it was detected is a
        # question that arrives in detection order, which is the order the
        # code happens to be written in.
        for what in inventory.unpreserved(live):
            metrics.fire("G-PRESERVE", "unpreserved", what)
            gaps.append(gap_queue.Gap(
                what=f"who is preserving {what}, and by when",
                blocks="relying on that document at trial",
                thread=thread.id,
                # A document leaving the file is a DEADLINE, not a curiosity:
                # the window closes when it is gone, and it closes silently.
                kind=gap_queue.GapKind.DEADLINE))

        # WRITTEN AND NEVER ISSUED. Distinct from the above, and the document
        # is gone either way -- so it is a gap of its own rather than counted
        # as preserved.
        for what in inventory.undelivered(live):
            gaps.append(gap_queue.Gap(
                what=f"when the preservation instruction for {what} goes out",
                blocks="relying on that document at trial",
                thread=thread.id, kind=gap_queue.GapKind.DEADLINE))

        # THE QUESTIONS NOBODY PUT. An inventory that lists ten items and
        # answered two questions of the thirty reads as an inventory that was
        # done.
        unasked = inventory.unasked(live)
        if unasked:
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"{len(unasked)} item(s) carry questions nobody has put: "
                      f"{'; '.join(unasked[:3])}"
                      f"{' ...' if len(unasked) > 3 else ''}. Existence, "
                      f"admissibility and weight are three separate questions "
                      f"and none of them is answered by listing the item.")))

        if read.state == "none_mentioned" and read.why_not:
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"No evidence inventoried yet: {read.why_not}"))
        return out

    @implements("D9")
    def _issues(self, turn: TurnInput, thread: Thread, memory,
                metrics: TurnMetrics, concluded: dict) -> list[Element]:
        """D9. Spot the issues, and account for every one that was spotted.

        `backend/nm/domain/issue.py` carried the whole register from slice 6 and
        nothing ever produced an `Issue` (B-079), so none of it ran on a
        served turn: not the conservation invariant, not the derived effect,
        not the considered-not-pursued line.

        EVERY SPOTTED ISSUE IS ACCOUNTED FOR, and the check is here rather
        than trusted. The measured original discarded 20.1% of all issue
        labels ever spotted -- 641 of 3,192, led by limitation, bail and forum
        -- through a filter that decided what was relevant enough. Nothing was
        wrong with the labels. `classify` has no filter in it by construction,
        and this asserts that the construction held.
        """
        account = memory.account if memory else ""
        if not account.strip() and not turn.message.strip():
            return []

        try:
            standing = issue.from_stored(thread.issues)
            # THIS TURN IS QUOTABLE NOW (B-108). The guard checked the
            # rendered account alone while the prompt showed the message
            # under "THIS TURN", so an issue arising from what the
            # advocate had just written was refused for quoting it.
            #
            # AND THIS ONE KEEPS THE WHOLE RENDERING (B-115). Limitation is
            # an issue and it turns on dates, so the `[2024-04-15]` stamps
            # are information this read uses -- unlike the cause and
            # inventory reads, which were handed them and could not.
            quotable = Quotable(
                turn=turn.message,
                file=memory.advocate_words if memory else "",
                context=account)
            res = self._read(
                      issue_reader.build_prompt(quotable, standing),
                      issue_reader.ISSUE_SCHEMA, "issues", Tier.ROUTINE)
            metrics.record_call(res)
            read = issue_reader.read(res.data or {}, thread.id, quotable,
                                     standing)
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"the issues could not be read: {exc}")
            return [Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"I have not identified the issues on this thread: "
                      f"{exc}. That is a gap in this turn, not a finding that "
                      f"there are none."))]
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            metrics.violate("D9", f"issue read failed: "
                                  f"{type(exc).__name__}: {exc}")
            return []

        # THE LIST IS MERGED, NOT REPLACED. An issue on the file that this
        # read did not mention stays on the file: `DispositionState` has no
        # member meaning "gone", and rebuilding the list from one read is the
        # delete path the type refuses, taken by the pipeline instead.
        live = issue.merge(standing, read.issues)
        concluded["issues"] = live
        classified = issue.classify(live)

        # E-060. THE CONSERVATION INVARIANT, RUN -- not assumed because
        # `classify` looks like it cannot lose anything.
        lost = issue.accounted_for(live, classified)
        if lost:
            metrics.violate("D9", f"issues spotted and not accounted for: "
                                  f"{'; '.join(lost)}")

        out: list[Element] = []
        for refused in read.refused:
            # A REFUSED ISSUE IS DISCLOSED, not dropped. Dropping it silently
            # is the measured defect exactly, with a better excuse.
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"I did not take one issue the reading offered: {refused}"))

        for i in classified:
            effect, basis = i.effect_for(thread.posture)
            # THE POSTURE VERSION TRAVELS WITH THE EFFECT. A reading recorded
            # without it is one nobody can later tell is stale, which is the
            # whole reason `effect` is not a field.
            out.append(Element(
                kind=ElementKind.FINDING, thread=thread.id,
                # A SENTENCE. This read "[substantive; runs against
                # defending; opposes our case on posture v2]" — a
                # bracketed record of three enum values. The posture
                # version stays because a reading recorded without it is
                # one nobody can later tell is stale.
                feature="D9",
                text=(f"{i.statement} It is {i.kind.said}, running "
                      f"against {i.runs_against.said}, and it "
                      f"{effect.said}. Read on the posture as it stood "
                      f"at v{basis}.")))

        for line in issue.considered_not_pursued(classified):
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"Considered, not pursued: {line}"))

        if read.state == "none_spotted" and read.why_not:
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"No issues identified yet: {read.why_not}"))
        return out

    @implements("D5")
    def _proof(self, turn: TurnInput, thread: Thread, memory,
               metrics: TurnMetrics, cause_read: str | None,
               concluded: dict) -> list[Element]:
        """D5. What the file can establish, element by element.

        `backend/nm/domain/proof.py` carried the whole contract from slice 7 and
        NOTHING EVER BUILT A `ProofPosition`, so none of it ran: not the
        refusal of an OBTAINABLE with nothing named that would obtain it, not
        the refusal of an ABSENT with no dead end, not `uncovered` drawing its
        population from the elements so the coverage gate cannot certify
        itself. The same shape as B-079, one feature along.

        THE ELEMENTS COME FROM THE TABLE AND THE STATUSES FROM THE FILE. A
        model asked what specific performance requires answers plausibly and
        differently each time; a model asked whether this file holds the
        agreement is answering about material in front of it.

        EVERY FAILURE HERE IS NOT_ASSESSED AND SAYS SO. "No proof positions"
        and "nobody worked out the proof positions" are the two states S1 is
        about, and an advocate reading a conclusion with no proof section has
        to be able to tell which one they are looking at.
        """
        if self._elements is None:
            metrics.fire("G-PROOF", "not_assessed",
                         "no element table is wired, so nothing decomposed "
                         "this claim into what has to be proved")
            return [Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=("I have not worked out what has to be proved on this "
                      "claim: no element table is configured. That is a gap "
                      "in this installation, not a finding that everything "
                      "is established."))]

        # THE CAUSE COMES FROM THE READ, not from the thread: this product
        # does not store one. `_read_cause` returns `None` on any doubt, and
        # `None` here is NOT_ESTABLISHED -- which `why_not` turns into a
        # sentence saying the cause itself was never settled, rather than one
        # implying the elements are missing.
        cause = CauseOfAction.NOT_ESTABLISHED
        if cause_read:
            try:
                cause = CauseOfAction(cause_read)
            except ValueError:
                # OUT OF VOCABULARY IS NOT_ESTABLISHED, never a near
                # neighbour. The list is closed because the lookup is exact.
                cause = CauseOfAction.NOT_ESTABLISHED

        elements = self._elements.elements_for(cause)
        if elements is None:
            why = self._elements.why_not(cause)
            metrics.fire("G-PROOF", "not_assessed", why)
            return [Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"I have not decomposed this claim into elements: {why}")]

        # THE NOTES (B-115). Whether the file HOLDS the agreement is a
        # question about the sentences, which are in `file` already; the
        # stamps would be the same sentences a second time.
        quotable = Quotable(
            turn=turn.message,
            file=memory.advocate_words if memory else "",
            context=memory.notes if memory else "",
            context_is="notes this product wrote about the file")
        try:
            res = self._read(
                      proof_read.build_prompt(quotable, elements),
                      proof_read.PROOF_SCHEMA, "proof", Tier.ROUTINE)
            metrics.record_call(res)
            read = proof_read.read(res.data or {}, elements, quotable)
        except ModelError as exc:
            metrics.fire("G-PROOF", "not_assessed",
                         f"the proof positions could not be read: {exc}")
            return [Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"I have not worked out what this file can establish: "
                      f"{exc}. That is a gap in this turn, not a finding that "
                      f"the elements are held."))]
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            metrics.violate("D5", f"proof read failed: "
                                  f"{type(exc).__name__}: {exc}")
            return []

        # MERGED, NOT REPLACED. A read that did not mention an element has
        # said nothing about it, and nothing is not a finding -- measured
        # going held, held, NOT_ASSESSED, held with the material untouched on
        # the file. A POSITIVE statement still wins, including a regression to
        # ABSENT, because a product that could not lower its own confidence
        # would have a proof section that only ever improved, which is D5.1's
        # drift with a mechanism behind it.
        standing = domain_proof.from_stored(thread.proof)
        live = domain_proof.merge(standing, read.positions)

        # AND THE FILE OVERRULES BOTH. A HELD position rests on material, and
        # material the advocate has since corrected takes the position with
        # it. Checked against the FILE rather than against the read, which is
        # the one direction neither can wobble in.
        live = tuple(
            p if domain_proof.still_supported(p, quotable)
            else domain_proof.withdrawn(
                p, "the material it rested on is no longer on the file")
            for p in live)
        concluded["proof"] = live

        out: list[Element] = []
        for refused in read.refused:
            # A REFUSED POSITION IS DISCLOSED. Most of these are the drift D5.1
            # names -- OBTAINABLE with nothing named that would obtain it --
            # and an advocate who cannot see the refusal reads a shorter list
            # as a shorter case.
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"I did not take one proof position: {refused}"))

        for pos in live:
            falls = pos.burden.falls_on_us(thread.posture)
            whose = ("on us" if falls is True
                     else "on them" if falls is False
                     else f"on {pos.burden.on.said}, and which side we "
                          f"are is not settled")
            detail = (f"It is held on {'; '.join(pos.material)}."
                      if pos.status is ProofStatus.HELD
                      else f"It is obtainable: {pos.closing_material}."
                      if pos.status is ProofStatus.OBTAINABLE
                      else f"It is absent: {pos.dead_end}."
                      if pos.status is ProofStatus.ABSENT
                      else "Nobody has established how it is proved.")
            out.append(Element(
                kind=ElementKind.FINDING, thread=thread.id,
                # A SENTENCE. This read "[burden ours;
                # balance of probabilities; held on X]" — the burden, the
                # standard and the status packed into brackets, which is
                # how a record looks, not how an advocate writes.
                feature="D5",
                text=(f"{pos.element} The burden is {whose}, "
                      f"{elements.standard.said}. {detail}")))

        # E-070'S INVARIANT, RUN. The population is the ELEMENTS, so a read
        # that answered on two of five reports three gaps rather than
        # complete coverage of the two it happened to reach.
        missing = proof.uncovered(
            tuple(i.element for i in elements.ingredients), live)
        if missing:
            metrics.violate("D5", f"elements with no proof position: "
                                  f"{'; '.join(missing)}")

        # D5's FOURTH DOES: every gap resolves into an action or an express
        # finding that nothing can. `unclosed` is the check that it did.
        open_gaps = proof.unclosed(live)
        if open_gaps:
            metrics.violate("D5", f"proof gaps with no action and no dead "
                                  f"end: {'; '.join(open_gaps)}")

        ours = proof_read.against_us(live, thread.posture)
        if ours:
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=("What is not yet established, and OURS to establish: "
                      + "; ".join(p.element for p in ours))))
        return out

    @implements("D2")
    def _factors(self, turn: TurnInput, thread: Thread,
                 chart: tuple[Fact, ...], metrics: TurnMetrics,
                 grounds: list[Element],
                 unextended_expiry) -> "factor_reader.ReadFactors":
        """B-073. WHAT MOVED THE CLOCK, retrieved and read rather than assumed.

        Nothing produced a `Factor` until this existed, so no acknowledgment,
        part payment, exclusion or disability had ever moved a limitation
        date. Measured on GS-14: an acknowledgment dated 12 June 2024 was on
        the file, was repeated back to the advocate, and never reached the
        arithmetic -- the claim was reported dead when it was alive to June
        2027.

        EVERY FAILURE HERE IS `not_assessed` AND SAYS SO. Not "no factor
        applies": the difference between "nothing on this file restarts the
        period" and "nobody looked" is the whole of defect shape S1, and it is
        the difference between an advocate filing and an advocate not.
        """
        dated = tuple(f for f in chart if f.date is not None)
        if not dated:
            return factor_reader.not_assessed(
                "no dated entry on this thread could carry an acknowledgment")

        # THE SECTIONS FIRST. `Factor.finding` is required by the type so an
        # extending provision cannot be asserted from memory -- and filling it
        # with a summary would satisfy the type while defeating it. What goes
        # in is the span the corpus returned.
        provisions: dict[str, str] = {}
        # THE SECTIONS THE READ CAN USE, FROM THE READ (BK-6, and the
        # advocate's question about the hard-coding).
        #
        # This was the literal `("18", "19")` -- a SECOND COPY of
        # `factors.SECTION_FOR`, in another module. The failure it sets up is
        # silent: add a third kind to `READS` and `SECTION_FOR`, and the turn
        # goes on fetching two sections, `provisions.get(SECTION_FOR[kind])`
        # returns None, and the new factor is refused for a missing provision.
        # The feature would be built, wired, and dead, with nothing raised.
        #
        # `factors` owns which kinds it reads and which section each needs.
        # This asks it.
        for section in factor_reader.sections_needed():
            # NAMED, NOT WANDERING (BK-6). `MAX_EVIDENCE_ROUNDS` limits how
            # far a turn may WANDER looking for what it needs, and this is
            # the opposite: two sections, by number, decided before the turn
            # started. It is the case `exploratory=False` was built for --
            # B-104's late lookup, in the same words.
            #
            # MEASURED, 7 September 2026: every turn of GS-14 spent 2 of its
            # 3 rounds here, on the same two sections, leaving ONE for the
            # advocate's actual question -- and none at all on a turn that
            # also wanted authority, which is why turn 4 reported "I stopped
            # after 3 rounds of retrieval".
            #
            # STILL COUNTED. A retrieval that happened and is not in the
            # count is the drift `_fetch` warns about. Its own bound is here:
            # at most two provisions, once per turn.
            found = self._fetch(EvidenceNeed(
                question=f"Limitation Act 1963 section {section}",
                governing_date=turn.today,
                jurisdiction=turn.jurisdiction), metrics, exploratory=False)
            span = next((f.span for f in found.findings
                         if f.span and f".{section}" in f.ref
                         or f.span and f" {section}" in f.ref), None)
            if span:
                provisions[section] = span

        if not provisions:
            return factor_reader.not_assessed(
                "sections 18 and 19 of the Limitation Act were not retrieved "
                "on this turn, so nothing here can move the period. That is a "
                "gap in what I read, not a finding that nothing restarts it.")

        # THE ACCOUNT IS THE CHART, not a second read of the store.
        #
        # `getattr(thread, "matter_id", None)` was a guess about a type this
        # module already imports, and it would have degraded SILENTLY to an
        # empty account — weakening the quotation guard exactly where it
        # matters. The chart holds the dated statements a quotation has to be
        # found in, and it is already in hand.
        # THE CHART'S STATEMENTS ARE THE ADVOCATE'S OWN WORDS, so they
        # are `file` and not `context`. The id/date table the prompt also
        # shows is ours, and `build_prompt` marks it name-only.
        quotable = Quotable(turn=turn.message,
                            file="\n".join(f.statement for f in chart))

        try:
            res = self._read(
                      factor_reader.build_prompt(quotable, dated),
                      factor_reader.FACTOR_SCHEMA, "factors", Tier.ROUTINE)
            metrics.record_call(res)
            read = factor_reader.read(
                res.data or {}, dated, quotable, provisions,
                unextended_expiry)
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"acknowledgments could not be read: {exc}")
            return factor_reader.not_assessed(
                f"nothing read this account for an acknowledgment or part "
                f"payment: {exc}")
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            metrics.violate("D2", f"factor read failed: "
                                  f"{type(exc).__name__}: {exc}")
            return factor_reader.not_assessed(
                f"the acknowledgment read failed: {type(exc).__name__}")

        # A REFUSAL IS DISCLOSED. The advocate can correct it in a sentence,
        # and silence would have them believe it was never in question.
        if read.refused:
            metrics.violate("D2", f"factor not taken: {read.refused}")
            grounds.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"I did not accept a restart of the limitation period: "
                      f"{read.refused}")))
        elif read.state == "none_found" and read.why_not:
            grounds.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"I read this file for anything that restarts the "
                      f"period under sections 18 or 19 and found none: "
                      f"{read.why_not}")))
        return read

    @implements("D3")
    def _by_when(self, register: "tuple[deadlines.Deadline, ...] | None",
                 today: date) -> tuple[date | None, str | None]:
        """The by-when for an ACTION, or the REASON there is none. D3.

        ONE OWNER FOR THE RULE, because every future site that emits an ACTION
        needs the same answer and a second copy of it would drift within a
        slice. `Element.__post_init__` already refuses an ACTION carrying
        neither; what it cannot see is whether the reason is TRUE.

        And it used to be false. The engine set a fixed
        `no_deadline_reason="no statutory window identified on this turn"` on
        every recommendation it ever made -- a finding that nothing was found,
        asserted whether or not anything had been looked for. That is defect
        shape S1 wearing a helpful face, so the three states are separated
        here:

          * `None` register -- NOT ASSESSED. Nobody computed a register on this
            path, and saying "no window applies" would be inventing a finding.
          * a register with no date -- assessed, and no date could be
            established. The register's own entries carry why.
          * a dated entry -- the nearest one, which is the answer.
        """
        if register is None:
            return None, ("no deadline register was computed on this turn, so "
                          "no by-when is stated — this is not a finding that "
                          "none applies")
        live = deadlines.upcoming(register, today)
        if live:
            return live[0].on, None
        # D3 -- NEVER FILE A PASSED DEADLINE UNDER WHAT IS STILL UPCOMING. It
        # is reported, as passed, rather than becoming this action's by-when.
        gone = deadlines.passed(register, today)
        if gone:
            return None, (f"every deadline on this thread has passed — the "
                          f"nearest was {gone[0].on.isoformat()}, and it is "
                          f"reported above rather than presented as a window")
        return None, ("the register holds no deadline with an established "
                      "date on this thread")

    def _relief(self, turn: TurnInput, thread: Thread, metrics: TurnMetrics,
                concluded: dict,
                position: "limitation.Limitation | None",
                ) -> "relief_mod.ReliefPosition | None":
        """BK-70. Whether the relief that would serve the objective can be
        obtained, enforced and is worth the cost -- SEPARATELY from the merits.

        THE FACTS ARE ATTRIBUTED, NEVER GUESSED, which is why this does NOT add
        a model read. Two sources feed it and each names what it rests on:

          * what the ADVOCATE STATED about a relief -- assets, forum, cost --
            carried on the thread with basis STATED. The strong case, and the
            one the served route records.
          * the LIMITATION POSITION already computed this turn. A claim whose
            window has RUN cannot be filed in time, so its relief is LATE, and
            that is ATTRIBUTED to the computed position -- a typed fact that can
            be re-read, not a judgement about enforceability read off prose.

        The objective is the advocate's where they stated one, else INFERRED
        from the theory and labelled so: an inferred objective is a question the
        advocate can correct, exactly as an inferred premise is (P22). Where
        neither an objective nor any relief is on the file, this returns None
        and G-REMEDY reads `not_assessed` -- nobody looked, which is not the
        same as nothing being worth pursuing.

        THE DETERMINISTIC SIGNAL DOES NOT OVERRIDE A STATED ONE. It is
        synthesised only where the advocate has stated no relief at all, so
        their account of the remedy -- which may know of a condonation or an
        extension this does not -- is never silently contradicted. Where they
        have stated reliefs, the run-window fact still reaches the step through
        the limitation claim `consistency.claims_for` already builds.
        """
        obj = relief_mod.Objective.from_stored(thread.objective)
        stated = list(relief_mod.reliefs_from_stored(thread.reliefs))
        t = theory_reader.from_stored(concluded.get("theory", thread.theory))

        if obj is None and t is not None and t.relief:
            obj = relief_mod.Objective(
                statement=f"obtain {t.relief}",
                basis=premise_mod.Basis.INFERRED,
                inferred_from="the case theory's stated relief")

        run = (position is not None
               and position.state in (limitation.LimitationState.COMPUTED,
                                      limitation.LimitationState.CONDITIONAL)
               and position.expired(turn.today))
        if not stated and t is not None and t.relief and run:
            # A COMPUTED expiry is an ESTABLISHED fact -> the relief is DEFEATED.
            # A CONDITIONAL one rests on an INFERRED accrual (P22), so the
            # lateness is a QUESTION and the relief is CONTINGENT, not defeated:
            # the same discipline that makes a conditional date no deadline.
            established = position.state is limitation.LimitationState.COMPUTED
            stated.append(relief_mod.Relief(
                remedy=t.relief,
                objective=(obj.statement if obj is not None else "the objective"),
                timing=relief_mod.Timing.LATE,
                basis=(premise_mod.Basis.ATTRIBUTED if established
                       else premise_mod.Basis.INFERRED),
                source=(f"the limitation position computed on {position.article}"
                        if established else ""),
                inferred_from=("" if established else
                               f"the limitation on {position.article} run from "
                               f"the inferred accrual"),
                reason=(f"the limitation period on {position.article} expired "
                        f"on {position.expires_on.isoformat()} and has passed, "
                        f"so the claim cannot be filed in time")))

        if obj is None and not stated:
            return None

        pos = relief_mod.assess(obj, tuple(stated))
        concluded["objective"] = obj.as_dict() if obj is not None else None
        concluded["reliefs"] = pos.as_rows()
        return pos

    def _recommend(self, thread, turn, result, metrics: TurnMetrics,
                   memory=None,
                   register: "tuple[deadlines.Deadline, ...] | None" = None,
                   position: "limitation.Limitation | None" = None,
                   relief_position: "relief_mod.ReliefPosition | None" = None,
                   concluded: "dict | None" = None,
                   sources: tuple[Finding, ...] = (),
                   response_mode: Mode = Mode.SHORT_QUESTION,
                   checklist_note: str = "",
                   ) -> Element:
        if concluded is not None:
            # A newly refused/failed derivation must not leave yesterday's
            # recommendation presented as current. Its transcript is retained.
            concluded["recommendation"] = {}
        side = thread.posture.side.value
        cited = ""
        if result.usable:
            cited = f" A retrieved provision is {result.usable[0].ref}."

        # WHAT THE ANSWER BENEATH THIS ONE SAYS. Measured on a served turn,
        # 31 August 2026: the ACTION read "file the recovery suit, ensuring it
        # is within the limitation period" while the GROUND directly below it
        # read "that period has run" -- 174 days ago. On the next turn it told
        # the advocate to "calculate the limitation period and determine if the
        # claim is still within time", which is the calculation the product had
        # just done and printed underneath (B-074).
        #
        # Nothing was wrong with either component. The limitation was computed
        # correctly and the step was composed correctly GIVEN WHAT IT WAS TOLD,
        # and it was told nothing about the limitation. Two right components,
        # one incoherent answer, the defect in the gap between them.
        worked = ""
        if position is not None:
            if position.state is limitation.LimitationState.COMPUTED:
                gone = position.expired(turn.today)
                worked = (
                    f"\n\nALREADY WORKED OUT, and your step must be consistent "
                    f"with it: limitation on {position.article} expires "
                    f"{position.expires_on.isoformat()}, which "
                    + ("HAS ALREADY PASSED. Do NOT advise filing within a "
                       "period that has run."
                       if gone else
                       "is still open. Do not tell them to compute it; it is "
                       "computed."))
                if position.factors:
                    # B-073 CLOSED THE OTHER HALF OF B-077.
                    #
                    # The ban below was the honest instruction while NOTHING
                    # produced a `Factor`: with no computed answer, any
                    # statement about the acknowledgment was an assertion
                    # nobody had made, and the model duly made it in both
                    # directions -- flatly against the opponent, hedged
                    # against our own client.
                    #
                    # A computed factor removes the guess rather than
                    # forbidding it. The restart is IN the figure above, so
                    # the model is told what was applied and may rely on it.
                    # Silence here would be its own defect: the advocate would
                    # read an unexplained later date and not know why.
                    applied = "; ".join(
                        f"{f.kind.value.replace('_', ' ')} on "
                        f"{f.restarts_from.isoformat()}"
                        for f in position.factors if f.restarts_from)
                    worked += (
                        f" The period above ALREADY accounts for: {applied} — "
                        f"computed against the section retrieved for it. Say "
                        f"so if it matters to the step; do not re-argue it.")

                missed = position.accounts_for_every_entry(thread.chronology)
                if missed:
                    # WHAT HAS NOT BEEN WEIGHED, AND THE BAN ON GUESSING IT.
                    #
                    # The first version of this prompt told the model to
                    # "advise on what the file offers now: an acknowledgment or
                    # part payment that restarts it". That INVITED the
                    # assertion, and the model took it: acting for the debtor
                    # it said "the acknowledgment on 12 June 2024 does not
                    # operate to restart the limitation period", flatly, on a
                    # turn where nothing had computed whether it does.
                    #
                    # Worse, it hedged the same point acting for the creditor
                    # -- "to POTENTIALLY revive" -- so the same unfounded
                    # question was stated tentatively when the answer would
                    # hurt our client and definitively when it would hurt
                    # theirs. That is E-073's failure exactly, and the judge
                    # found it (B-077).
                    #
                    # Nothing produces a `Factor` yet (B-073), so the honest
                    # instruction is: name the fact, ask for it to be checked,
                    # and assert nothing about its effect.
                    worked += (
                        f" {len(missed)} thing(s) on this file have NOT been "
                        f"weighed against that period. You may tell them to "
                        f"have those examined. You may NOT say whether any of "
                        f"them restarts, extends or fails to restart it -- "
                        f"that has not been computed, and stating it either "
                        f"way is an assertion nobody made.")
            elif position.state is limitation.LimitationState.CONDITIONAL:
                worked = (
                    f"\n\nCONDITIONAL, and your step must not present it as "
                    f"settled: a limitation of {position.expires_on.isoformat()} "
                    f"was computed under a premise the product inferred "
                    f"({position.conditional_because}). Do NOT tell them to "
                    f"file by that date as though settled. Ask to confirm the premise "
                    f"only if needed for the present request; independent evidence "
                    f"preservation or clarification remains possible within its limits.")
            else:
                worked = (f"\n\nNOT worked out: {position.why_not_computed}. "
                          f"Do not assume a position either way.")

        system = (
            "You are senior counsel advising an instructing advocate in India. "
            "Recommend one focused next step in at most 40 words, proportionate "
            "to the immediate request. Keep any material condition or uncertainty. "
            "If the request needs no further action, say so instead of inventing work. "
            "This is a recommendation, not an act taken or permission to act.\n"
            "NEVER restate a calculation already made for them, and never "
            "recommend a step the worked position rules out. Be specific to the "
            "held material and the task, not a generic procedural instruction.\n"
            # THE PEER REGISTER, AS A RULE ABOUT SUBJECT MATTER (B-078).
            #
            # E-102's judge read "Ensure the letter explicitly acknowledges the
            # debt and contains a promise to pay" as guiding a lay client on
            # drafting rather than analysing with a peer whether the letter
            # they ALREADY HOLD satisfies s.18.
            #
            # That is not a tone failure and a tone instruction will not fix
            # it -- D5.1 says so in as many words about the sibling problem.
            # The step described WHAT A COMPLIANT DOCUMENT WOULD CONTAIN,
            # which is the section restated, and the advocate can read the
            # section. What they cannot read off the section is whether the
            # thing in their file does the job.
            #
            # The frame carries it: the model is shown WHAT THIS FILE HOLDS
            # below, so the step has something specific to be about.
            + PEER + "\n"
            # NAME NO SECTION. This is not a style rule.
            #
            # The grounding gate withholds the WHOLE TURN when the answer
            # cites a provision that was not retrieved, and it is right to: a
            # citation nobody looked up is the defect this product exists to
            # refuse. But the citation arrives in the RECOMMENDATION, which is
            # one sentence — and the limitation, the issues, the theory, the
            # inventory and the opponent's case are all thrown away with it.
            #
            # Measured on GS-15, twice: "the answer cites provision '7', which
            # was not retrieved on this turn. Retrieved: ['54']". The step
            # itself was sound. The section number was invented, and it cost
            # the advocate the entire turn.
            #
            # The law is carried by the GROUND elements, which quote what was
            # actually retrieved. The step does not need a citation.
            "Name NO section, article or rule number. The provisions are "
            "quoted elsewhere in the answer from what was actually retrieved; "
            "your sentence is the STEP. A number you have not been given here "
            "is one nobody looked up, and it will cost the advocate the whole "
            "turn."
        )
        explanatory = response_mode in (Mode.EXPLANATION, Mode.ASSESSMENT)
        if explanatory:
            system = (
                "Answer the requested explanation or assessment in natural paragraphs, "
                "proportionate to its complexity. Do not manufacture an action or question. "
                "Use the supplied file, computed positions and retrieved passages only. "
                "Distinguish allegations, supported conclusions, assumptions and unknowns. "
                "Explain applicable law and material alternatives, keeping consequential "
                "qualifications visible. Do not direct an act, concede a position or "
                "claim permission to act. Keep the answer within 240 words.\n" + PEER)
        # THE FILE, THEN THIS TURN. A next step recommended off the last
        # message alone re-opens ground the advocate has already covered,
        # which reads to them as the product having forgotten the matter --
        # and it is, because it had.
        file_note = memory.as_context() if memory is not None else ""

        # WHAT THIS FILE CAN ESTABLISH, ELEMENT BY ELEMENT (B-078). Nothing
        # here is new work: the positions were computed earlier in the turn
        # and persisted on the thread. They were simply not shown to the one
        # read whose whole job is to say what to do next -- so the step had
        # nothing specific to be about and described the general case.
        held = _positions_note(thread)
        # BK-70. WHAT THE RELIEF IS WORTH, so the step is composed knowing it --
        # the same `ALREADY WORKED OUT` move `worked` makes for limitation. A
        # step that recommends pursuing a defeated remedy without a reservation
        # is then caught by the consistency check below, on the relief claim.
        relief_note = relief_mod.recommendation_note(relief_position)
        user = (f"The advocate acts for the {side} party."
                f"{cited}{worked}{relief_note}{held}")
        if file_note:
            user += f"\n\n{file_note}"
        user += (f"\n\nWhat they have just asked: {turn.message.strip()}\n\n"
                 + ("The requested explanation or assessment:" if explanatory
                    else "The single next step:"))
        user += checklist_note
        prompt = with_evidence(Prompt(system=system, user=user), sources or result.findings)
        try:
            res = self._model.complete(guided(prompt), Tier.ROUTINE,
                                       max_tokens=768 if explanatory else 120)
            metrics.record_call(res)
            partial = refuse_partial(res.completion, doing="the recommendation")
            if partial:
                raise OutputTruncated(partial)
            text = (res.text or "").strip()
        except ModelError as exc:
            # Fail the NEED, not the turn. The gap becomes visible.
            metrics.fire("G-MODEL", "unavailable", f"model unavailable: {exc}")
            text = ""

        if not text:
            return Element(
                kind=ElementKind.QUESTION, thread=thread.id, gate="G-MODEL",
                text=("I could not form a complete, usable recommendation on "
                      "this turn. No new recommendation has been recorded. Resend, "
                      "or tell me what you would like me to work on first."))
        # G-CONSISTENT — THE STEP AGAINST THE FIGURES PRINTED BESIDE IT.
        #
        # Everything above this line TELLS the model what was worked out, at
        # length and correctly, and that was the fix applied to B-074. It
        # recurred: on `6e29cf0` the step said "file within the window" while
        # the annotation on the same element said every deadline had passed.
        # A prompt is an instruction that is usually followed, and the turns
        # where it is not are exactly the turns nobody is watching.
        #
        # So the sentence is checked AFTER it exists, against the typed facts
        # rather than against the instruction that was meant to produce it.
        claims = consistency.claims_for(
            position, register, side, turn.today, thread.chronology,
            relief_position=relief_position)
        text, verdict = self._consistent_step(text, claims, metrics, file_note,
                                             allow_repair=not explanatory)
        if verdict.contradicted:
            named = next(c for c in claims if c.id == verdict.claim_id)
            # BLOCK, AND THE BLOCK IS THE ANSWER (the matrix, Scope.STEP).
            # The advocate gets the computed fact and a question rather than a
            # sentence that disagrees with the figures beside it — the facts
            # are the part that was verified, the step is the part that was
            # generated, and when they conflict the generated half goes.
            return Element(
                kind=ElementKind.QUESTION, thread=thread.id,
                gate="G-CONSISTENT",
                text=(f"I withheld the next step on this thread because it "
                      f"contradicted what this same answer worked out. "
                      f"{named.sentence} No recommendation has been recorded. "
                      f"I can re-examine the supporting material; if the recorded "
                      f"position is wrong, please correct it."))

        limitation_block = self._limitation_step(
            text, position, metrics, thread.id, file_note,
            # WHOSE position this is. On a defending thread the gate is
            # handed the opponent's; the read must be told so.
            ours=position is None or position.for_side is thread.posture.side)
        if limitation_block is not None:
            return limitation_block

        if explanatory:
            return Element(kind=ElementKind.FINDING, text=text, thread=thread.id)

        by_when, no_deadline = self._by_when(register, turn.today)

        # P26 / BK-96-AC2. THE RECOMMENDATION BECOMES A RECORD, NOT ONLY PROSE.
        #
        # `Recommendation` sat in `test_reached_from_production.UNTYPED` as
        # "E2. BUILT AS A STRING ... nothing could ask it what it was based on,
        # so it contradicted the finding printed beneath it" (B-074). The
        # sentence above is still the sentence; what is added is a record that
        # can be ASKED what it rests on, what would change it, and whether its
        # by-when is attributed to anything.
        #
        # Every field it cannot fill stays EMPTY and is reported by `absent()`.
        # Filling them with a plausible owner and a plausible date to complete
        # the shape is the fabrication the criterion forbids in as many words.
        if concluded is not None:
            record = advice.Recommendation(
                position=text,
                next_step=advice.NextStep(
                    action=text,
                    owner="the instructing advocate",
                    by_when=by_when.isoformat() if by_when else "",
                    # ATTRIBUTED, or not carried. `_by_when` reads the deadline
                    # register, so a date that came from it can name where it
                    # came from; a turn with no register entry has no date and
                    # says so through `no_deadline_reason`.
                    by_when_basis=("the deadline register on this matter"
                                   if by_when else "")),
                reservations=(() if not no_deadline else (no_deadline,)))
            maturity = advice.maturity_of(
                has_position=True,
                inferred_support=(
                    position is not None
                    and position.state is limitation.LimitationState.CONDITIONAL))
            # BK-96-AC3's LAST CLAUSE, enforced rather than assumed. A
            # withheld, stale or truncated derivation must not reach the
            # ordinary renderer looking like ordinary advice; the two failure
            # exits above return questions, and this refuses the remaining way
            # in -- a "successful" turn whose position is empty, which is
            # background wearing a recommendation's shape.
            refused = advice.refuse_release(record, maturity)
            if refused:
                return Element(
                    kind=ElementKind.QUESTION, thread=thread.id,
                    gate="G-MODEL", text=(
                        f"I did not record a recommendation on this thread: "
                        f"{refused}."))
            concluded["recommendation"] = {
                "position": record.position,
                "why_alternatives_lose": list(record.why_alternatives_lose),
                "next_step": {"action": record.next_step.action,
                              "owner": record.next_step.owner,
                              "by_when": record.next_step.by_when,
                              "by_when_basis": record.next_step.by_when_basis},
                "fallback": record.fallback,
                "changing_fact": record.changing_fact,
                "reservations": list(record.reservations),
                "maturity": maturity.value,
                "absent": list(record.absent()),
            }

        return Element(
            kind=ElementKind.ACTION, thread=thread.id, text=text,
            by_when=by_when, no_deadline_reason=no_deadline)

    def _limitation_step(self, text, position, metrics, thread_id, context, *,
                         ours: bool = True):
        """Refuse dependent/unknown directives, not evidence-gathering or the turn."""
        settled = position is not None and (
            position.state is limitation.LimitationState.NOT_APPLICABLE
            or (position.state is limitation.LimitationState.COMPUTED
                and position.expires_on is not None))
        if settled:
            metrics.fire("G-LIMITATION", position.state.value, "dated premise established")
            return None
        # THE READ IS TOLD WHICH POSITION IS UNRESOLVED. See
        # `step_dependency.position_context`: given only the file note, it
        # invented a limitation period on requesting a charge sheet.
        why = (position.conditional_because or position.why_not_computed
               if position is not None else "no limitation position was established")
        context = step_dependency.position_context(ours, why, context)
        assessment = step_dependency.assess({}, text, context)
        try:
            res = self._read(step_dependency.build_prompt(text, context),
                             step_dependency.schema_for(text), "step_dependency")
            metrics.record_call(res)
            assessment = step_dependency.assess(res.data or {}, text, context)
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable", f"step dependency was not assessed: {exc}")
        metrics.step_assessments.append(assessment.record(thread_id))
        if assessment.dependence is step_dependency.Dependence.INDEPENDENT:
            metrics.fire("G-LIMITATION", "not_applicable",
                         "The proposed step was assessed as independent of the unresolved "
                         "limitation position: " + assessment.basis)
            return None
        reason = (position.conditional_because or position.not_computed_because
                  if position is not None else "no limitation position was established")
        response = metrics.fire("G-LIMITATION", "not_computed", reason)
        if response is not Response.BLOCK:
            raise ValueError("G-LIMITATION must block the dependent step")
        return Element(
            kind=ElementKind.QUESTION, thread=thread_id, gate="G-LIMITATION",
            text=("I have not released a limitation-dependent recommendation on this "
                  f"thread. {reason}. I could not establish that this step can proceed "
                  "independently. We can continue gathering evidence and clarify "
                  "the relevant dates or legal premise before deciding that step."))

    def _consistent_step(self, text: str, claims, metrics: TurnMetrics,
                         file_note: str = "", *, allow_repair: bool = True):
        """The step, verified against the turn's own computed facts.

        ONE REPAIR, THEN THE STEP GOES. The rewrite is handed the
        contradiction that was found and asked for the same step without it —
        not asked for a better step, which would hand the whole recommendation
        back to the thing that just got it wrong. A second failure is evidence
        about the step rather than about its wording, so there is no third
        attempt.

        THE GATE IS FIRED ON EVERY OUTCOME, including `consistent`. A check
        that only appears in the trace when it fails cannot be distinguished
        from one that never ran, which is the whole of defect shape S1 and is
        why `not_verified` is a state here rather than a null.
        """
        verdict = self._verify_step(text, claims, metrics, file_note)

        if verdict.contradicted and allow_repair:
            named = next(c for c in claims if c.id == verdict.claim_id)
            repaired = self._repair_step(text, named, verdict, metrics,
                                         file_note)
            if repaired:
                second = self._verify_step(repaired, claims, metrics,
                                           file_note)
                if not second.contradicted and second.ran:
                    metrics.fire(
                        "G-CONSISTENT", "repaired",
                        f"the step contradicted {named.id!r} and was rewritten "
                        f"once: {verdict.why}")
                    return repaired, second
                # A REWRITE THAT COULD NOT BE VERIFIED IS NOT A REPAIR.
                # Serving it would be taking the second read's silence as
                # agreement, and the first read's finding stands until
                # something replaces it.
                verdict = second if second.contradicted else verdict

        metrics.fire("G-CONSISTENT", verdict.state,
                     verdict.refused or verdict.why)
        return text, verdict

    def _verify_step(self, text: str, claims, metrics: TurnMetrics,
                     file_note: str = ""):
        """Does the step contradict a computed fact? UNVERIFIED if it cannot run.

        FAILS TOWARD SERVING, which is the opposite direction to the accrual
        read and deliberately so. Refusing there costs a date and buys safety;
        refusing here DELETES THE ADVICE, so a read that cannot run must not
        be able to silence a step that is perfectly sound.
        """
        if not claims:
            # NOTHING WAS COMPUTED, so there is nothing to contradict. This is
            # not a pass -- it is the check having no subject, and calling the
            # read anyway would spend a call to be told so.
            #
            # IT CARRIES ITS OWN REASON. Both this and a read that failed
            # leave the step unverified, and they are different facts about
            # the turn: one says nothing was computed, the other says the
            # check broke. Reporting them with one sentence is the collapse
            # this gate exists to refuse, one level down.
            return consistency.NOTHING_TO_CHECK

        try:
            res = self._read(
                      consistency.build_prompt(text, claims, file_note),
                      consistency.CONSISTENCY_SCHEMA, "consistency", consistency.TIER)
            metrics.record_call(res)
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"the consistency read could not run: {exc}")
            return consistency.UNVERIFIED
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning (§7)
            metrics.violate(
                "D3", f"consistency read failed: {type(exc).__name__}: {exc}")
            return consistency.UNVERIFIED

        verdict = consistency.interpret(
            res.data or {}, text, frozenset(c.id for c in claims))
        if verdict.refused:
            metrics.violate("D3", verdict.refused)
        return verdict

    def _repair_step(self, text: str, claim, verdict,
                     metrics: TurnMetrics, file_note: str = "") -> str:
        """One rewrite of a contradicting step, or empty if it could not run."""
        try:
            res = self._model.complete(
                guided(consistency.repair_prompt(text, claim, verdict.why,
                                                 file_note), communicates=True),
                Tier.ROUTINE, max_tokens=120)
            metrics.record_call(res)
            partial = refuse_partial(res.completion, doing="the repaired recommendation")
            if partial:
                raise OutputTruncated(partial)
            return (res.text or "").strip()
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"the step could not be rewritten: {exc}")
            return ""
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning (§7)
            metrics.violate(
                "D3", f"step repair failed: {type(exc).__name__}: {exc}")
            return ""

    def _non_matter_answer(self, turn, mode, mode_statement, metrics) -> Answer:
        # A QUESTION OF LAW IS ANSWERED, NOT DEFLECTED.
        #
        # The route read has four non-matter outcomes and this is the only
        # one that requires work: the advocate asked what the law says and
        # wants the provision and the citation. GS-02's counterexample is
        # `impose matter apparatus; ask for parties, posture or documents`,
        # so this path opens no file -- `_run` returns before
        # `_load_or_create` -- and its requirement is a CITED answer, so a
        # blurb does not satisfy it either.
        if mode_statement == route_reader.A_QUESTION_OF_LAW:
            return self._law_answer(turn, mode, mode_statement, metrics)

        text = "I could not prepare a conversational reply. Your matter remains available."
        if mode_statement == route_reader.NOTHING_YET:
            text = self._courtesy(turn, metrics) or text
        # THE READ ALREADY DECIDED THIS. Re-running a keyword list here
        # was the last `_ABOUT_NM` use in the product, and a second
        # place answering a question the route had answered -- so the
        # two could disagree, and on "what can you do about this suit?"
        # they did.
        if mode_statement == route_reader.ABOUT_THE_PRODUCT:
            text = self._courtesy(turn, metrics, about_product=True) or text
        return Answer(route=Route.NON_MATTER, mode=mode, mode_statement=mode_statement,
                      elements=(Element(kind=ElementKind.GROUND, text=text),))



    def _courtesy(self, turn, metrics, *, about_product: bool = False) -> str:

        """One line back to a person who said something human.

        RETURNS EMPTY ON ANY FAILURE, and the caller keeps its constant. A
        greeting is the one place where a stiff answer costs nothing --
        nobody is advised, nothing is filed, and the advocate simply types
        their brief. So this is allowed to fail quietly, which is not true
        of any read that touches the law.

        NO LEGAL CONTENT, and the prompt says so rather than the guard,
        because there is nothing here to ground: no matter, no retrieval,
        no findings. A model that answered a legal question in this slot
        would be ungrounded by construction, so it is told the one thing
        it may do.
        """
        from nm.ports.model import ModelError, Prompt, Tier

        context = ""
        if turn.matter_id:
            matter = self._store.load(turn.matter_id)
            if matter is not None and matter.advocate_id == turn.advocate_id:
                context = matter_memory.build(matter, about=turn.message).as_context()
        task = (
            "Explain only the relevant capability or limitation requested. NM is an advisory "
            "workspace for Indian advocates. It records instructions and holds originals; "
            "held originals are not automatically examined. Legal work requires accessible "
            "sources and the applicable checks. It does not itself file, serve or represent "
            "the client. Do not promise unavailable processors, coverage or outcomes."
            if about_product else
            "Respond naturally and briefly to the conversational contribution. Do not force "
            "an invitation for a brief, repeat held questions or presume the advocate's rank."
        )
        try:
            res = self._model.complete(
                guided(Prompt(
                    system=task + " Give no legal conclusions or case advice on this path.",
                    user=f"{context}\n\nCurrent contribution:\n{turn.message.strip()}",
                    operation="conversation")),
                Tier.ROUTINE, max_tokens=160)
            metrics.record_call(res)
            if refuse_partial(res.completion, doing="the conversational reply"):
                return ""
        except ModelError:
            return ""
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            metrics.violate("C4", f"the courtesy reply failed: "
                                  f"{type(exc).__name__}: {exc}")
            return ""
        reply = snippet(res.text, 300)

        # NO LAW ON THIS PATH, AND IT IS CHECKED RATHER THAN REQUESTED.
        #
        # Nothing was retrieved, so `grounding.verify` -- which catches an
        # ungrounded assertion on every other path in this engine -- has
        # nothing to verify against and cannot run. A sentence of law here
        # is ungrounded by construction, so a reply carrying a provision,
        # an Article, an Order or a case name is DISCARDED and the caller
        # keeps its constant.
        if (citation.provisions_cited(reply)
                or citation.cases_named(reply)
                or citation.ANY_PROVISION.search(reply)):
            metrics.violate("C4", f"the courtesy reply named law and was discarded: "
                                  f"{snippet(reply, 90)!r}")
            return ""
        return reply


    def _read_duty(self, turn, matter, metrics):
        """Does this instruction ask for something an advocate must refuse?

        EVERY FAILURE LANDS ON CLEAR and the turn proceeds. A refusal is an
        accusation of misconduct; one issued because a read timed out is
        worse than the request it was meant to catch, because there is
        nothing for the advocate to correct.
        """
        from nm.ports.model import ModelError, Tier

        # THE FILE, as every other read in this turn receives it.
        memory = (matter_memory.build(matter, about=turn.message)
                  if matter is not None else None)
        quotable = Quotable(turn=turn.message,
                            file=memory.advocate_words if memory else "")
        try:
            res = self._read(
                      duty_reader.build_prompt(quotable),
                      duty_reader.DUTY_SCHEMA, "duty", Tier.ROUTINE)
            metrics.record_call(res)
            metrics.duty_reads += 1
            return duty_reader.interpret(quotable, res.data or {})
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"the duty read could not run: {exc}")
            return duty_reader.UNREAD
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            metrics.violate("C4", f"duty read failed: "
                                  f"{type(exc).__name__}: {exc}")
            return duty_reader.UNREAD

    def _refusal_answer(self, turn, refusal, mode, mode_statement,
                        metrics) -> Answer:
        """Refuse, name the duty, and give the lawful route.

        THE ROUTE IS RETRIEVED, NOT COMPOSED. GS-05 wants what actually
        restarts limitation, which is a provision and not a paraphrase --
        and a refusal that ended with this product's own account of the law
        would be ungrounded text on the one turn where the advocate has
        most reason to check it.

        The need is built from THEIR OWN WORDS. An advocate asking to
        backdate an acknowledgment has said `limitation` and
        `acknowledgment`, which is what resolves the Act and the section;
        composing a different question here would be this product deciding
        what they meant.

        A MISS IS NOT A FAILURE OF THE REFUSAL. If nothing is retrieved the
        instruction is still refused -- the duty does not depend on the
        corpus -- and the advocate is told the route was not found rather
        than given nothing.
        """
        rows = [Element(
            kind=ElementKind.QUESTION,
            text=(f"I will not do that. {refusal.duty} You asked: "
                  f"'{snippet(refusal.quoted, 160)}'."),
            gate="G-DUTY", signal=Signal.CONTRADICTION)]

        # RETRIEVE WHAT THE READ NAMED, not what the advocate asked for.
        #
        # Their own words are about the improper route -- `backdated
        # acknowledgment` names no section, and the manifest resolved the Act
        # and stopped. The read names the LAWFUL counterpart ('Limitation Act,
        # 1963 s.18'), which is an exact title and an exact section, so the
        # lookup is a lookup and not a ranking.
        #
        # Nothing from the read is asserted: if the corpus does not hold it,
        # the else-branch below says so rather than falling back to the
        # model's recollection of the text.
        ask = refusal.lawful_section.strip() or turn.message.strip()
        need = EvidenceNeed(question=ask,
                            governing_date=turn.today,
                            jurisdiction=turn.jurisdiction)
        try:
            result = self._fetch(need, metrics)
        except Exception as exc:  # noqa: BLE001
            metrics.violate("C4", f"the lawful route could not be retrieved: "
                                  f"{type(exc).__name__}: {exc}")
            result = None

        cited = [f for f in (result.findings if result else ())
                 if f.source_kind is SourceKind.PROVISION and f.span.strip()]
        if cited:
            rows.append(Element(
                kind=ElementKind.GROUND, disclosure=True,
                text=("What does restart or extend a period is on the "
                      "file already, and it is this:")))
            for f in cited[:2]:
                rows.append(Element(
                    kind=ElementKind.FINDING,
                    text=(f'{f.ref} — "{_excerpt(f.span)}"'
                          f'{" [...]" if _shortened(f.span) else ""} '
                          f"({f.locator})."),
                    refs=(f.locator,), source=capture_source(f)))
            rows.append(Element(
                kind=ElementKind.GROUND, disclosure=True,
                text=("What that needs is evidence of the thing itself — who "
                      "signed it, when, and a document that says so on its own "
                      "date. If one exists, brief me on it and I will work the "
                      "period from it.")))
        else:
            rows.append(Element(
                kind=ElementKind.GROUND, disclosure=True,
                text=("I have not retrieved the lawful route for this and am "
                      "not stating it from memory. Name the Act and I will read "
                      "back what actually restarts or extends the period.")))
        return Answer(route=Route.MATTER, mode=mode,
                      mode_statement=mode_statement,
                      elements=tuple(rows), blocked=True,
                      blocked_reason="G-DUTY: the instruction is refused")

    def _law_answer(self, turn, mode, mode_statement, metrics) -> Answer:
        """Retrieve the provision the question is about, and read it back.

        THE SAME RETRIEVAL AS A MATTER TURN, through `_fetch`, so the
        evidence bound, the coverage states and the index naming are the
        ones the rest of the product uses. A second retrieval path for
        questions would be a second set of answers about the same corpus,
        which is the three-stores defect wearing a convenient face.

        NOTHING IS WRITTEN. No matter, no thread, no facts -- the caller
        returns before `_load_or_create`, and this method has no store.

        A MISS NAMES THE INDEX. `EvidenceResult` already carries the
        coverage state and the reason; the failure to guard here would be
        an empty answer reading as `the law does not say`, which is B-163
        exactly.
        """
        # THE CAUSE, SO THE ARTICLE CAN BE LOOKED UP RATHER THAN RANKED.
        #
        # `a suit for possession of immovable property` names a cause of
        # action and no matter, and `LIMITATION_ARTICLE` maps the cause to
        # Article 65 exactly. Without this the need carries only the question,
        # nothing identifies a provision, and the honest answer is `no
        # specific provision was identified` -- which is true and useless,
        # because the question named one in every way except its number.
        #
        # THE SAME READ THE MATTER PATH USES. A second way of working out the
        # cause would be a second answer to one question, at model prices.
        grounds: list[Element] = []
        cause_read = self._read_cause(turn, None, metrics, grounds)
        need = EvidenceNeed(question=turn.message.strip(),
                            governing_date=turn.today,
                            jurisdiction=turn.jurisdiction,
                            cause_of_action=cause_read)
        result = self._fetch(need, metrics)

        cited = [f for f in result.findings
                 if f.source_kind is SourceKind.PROVISION and f.span.strip()]
        if not cited:
            # NOT AN ANSWER, AND SAID SO. The reason comes from the
            # adapter, which knows which store was asked.
            # B-163: A ZERO NAMES THE INDEX IT CAME FROM. `searched_stores`
            # is the adapter's own record of what was asked, and without it
            # "nothing found" reads as "the law does not say" -- which is the
            # three-stores defect reaching an advocate as a legal conclusion.
            where = (", ".join(result.searched_stores)
                     if result.searched_stores else "no store was reached")
            # `missing` IS A STRING, NOT A LIST. Slicing and joining it
            # produced "S; p; e" -- the first three characters, joined
            # as though they were reasons. A type read from the field
            # name rather than the annotation.
            missing = (result.missing or "").strip()
            return Answer(
                route=Route.NON_MATTER, mode=mode,
                mode_statement=mode_statement,
                elements=(Element(
                    kind=ElementKind.GROUND,
                    text=(f"I have not answered this from memory. Searched: "
                          f"{where} — {result.coverage.said}."
                          + (f" Missing: {missing}." if missing else "")
                          + " Name the Act and section and I will read it "
                            "back, or brief me on the matter and I will "
                            "work it."),),))

        # THE PROVISION'S OWN WORDS, with the locator that reads it back.
        # Same shape as a matter turn's provision line, deliberately: an
        # advocate should not have to learn two citation formats.
        rows = [Element(
            kind=ElementKind.FINDING,
            text=(f'{f.ref} — "{_excerpt(f.span)}"'
                  f'{" [...]" if _shortened(f.span) else ""} '
                  f"({f.locator})."),
            refs=(f.locator,), source=capture_source(f)) for f in cited[:3]]
        return Answer(route=Route.NON_MATTER, mode=mode,
                      mode_statement=mode_statement, elements=tuple(rows))

    def _assert_invariants(self, answer: Answer, metrics: TurnMetrics) -> None:
        """Class-B checks, on the assembled Answer, BEFORE the byte boundary."""
        if answer.route is Route.NON_MATTER:
            return
        # Answer owns purpose-sensitive assembly: actionable/blocked work leads
        # with its action or controlling question. An unblocked explanation or
        # assessment may consist of findings. This is not permission to bypass
        # any release check, and duplicating the type's check here proves nothing.
        for e in answer.loud_signals:
            if e.collapsible:
                metrics.violate("S5", f"loud signal {e.signal.value} is collapsible")

        # D5.1, MECHANICALLY, ON EVERY TURN. NM reasons about proof, never
        # about honesty -- and the check is here, on the assembled answer,
        # because the sentence that breaches it is model prose and the model
        # writes it at the last moment.
        #
        # NM has not met the client, has not seen them answer a question, and
        # holds no material on which a credibility finding could rest. The
        # judgement is outside its competence rather than merely impolite, and
        # it is MISDIRECTED: NM speaks to the advocate, not the client.
        #
        # A VIOLATION AND NOT A GATE. Withholding the turn would cost the
        # advocate the analysis over one bad sentence, and D5.1's own bound
        # says the drift to design against is SOFTENING, not accusing -- a
        # response that made the product afraid of the topic would push the
        # wrong way. So it is recorded loudly and the substance still ships.
        for element in answer.elements:
            for sentence in proof.characterises_the_client(element.text):
                metrics.violate(
                    "D5", f"the answer judges the client rather than the file: "
                          f"{sentence!r}")
