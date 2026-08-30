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

import re
import time
from dataclasses import dataclass, field, replace
from datetime import date

from nm.core import grounding
from nm.core.threading import BindResult, BindState, bind
from nm.domain.answer import Answer, Element, ElementKind, Mode, Route, Signal
from nm.domain.coverage import CoverageState
from nm.domain.matter import (
    Basis,
    Certainty,
    Fact,
    Matter,
    Posture,
    Provenance,
    Role,
    Thread,
    new_id,
)
from nm.domain.metrics import Outcome, Phase, TurnMetrics
from nm.domain.traceability import implements
from nm.ports.coverage import CoveragePort
from nm.ports.evidence import (
    Coverage,
    EvidenceNeed,
    EvidencePort,
    Finding,
    SourceKind,
    TreatmentState,
)
from nm.ports.model import ModelError, ModelPort, Prompt, Tier
from nm.ports.store import StaleWrite, StorePort

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

def _subject_of(question: str, provisions: tuple[Finding, ...]) -> str:
    """The question, widened by the subject of the provision it resolved to.

    A provision span opens with the Act name and the marginal note -- for
    Specific Relief Act s.6 that is *"Suit by person dispossessed of immovable
    property"*. The marginal note is the subject; the question usually is not.

    The original question is KEPT rather than replaced. Widening recall is the
    intent; discarding what the advocate actually asked would be a different
    and worse change, and H4 is explicit that nothing which might be right is
    dropped before it can be considered.
    """
    if not provisions:
        return question
    span = " ".join(provisions[0].span.split())
    # The span opens with the store's own identifier prefix -- "Union Of India
    # 1963 1 The Specific Relief Act, 1963, - s.6:" - before the marginal note.
    # Left in, `union` and `india` occupy two of eight term slots and deflate
    # every confidence score, because they match nothing in a judgment.
    marker = re.search(r"s\.\s*\d+[A-Za-z]*\s*:", span)
    head = span[marker.end():].strip() if marker else span
    head = head[:220]
    # THE SUBJECT LEADS. The term budget is small and spent in order, so
    # putting the question first spends every slot on "is there any judgment we
    # can rely on" and none on "dispossessed of immovable property".
    return f"{head} {question}"


# An advocate asking for authority is asking a different question from one
# asking what a section says, and the two need different retrieval. Read from
# what the message ASKS FOR -- never from its length.
_WANTS_AUTHORITY = (
    "authority", "authorities", "judgment", "judgement", "judgments",
    "precedent", "case law", "caselaw", "ruling", "citation", "cited",
)


class TurnRefused(Exception):
    """Raised before any ANSWER is emitted. Nothing has been shown or saved.

    It carries the gates that withheld it and the DISCLOSURES the turn had
    already computed. Withholding the answer is not the same as withholding the
    reason: a disclosure states what could not be established, asserts no law,
    and can mislead nobody -- while a bare refusal leaves the advocate with
    nothing to act on and no idea whether to try again.
    """

    def __init__(self, message: str, *, gates: tuple[str, ...] = (),
                 disclosures: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.message = message
        self.gates = gates
        self.disclosures = disclosures


@dataclass
class TurnInput:
    advocate_id: str
    message: str
    turn_id: str = field(default_factory=lambda: new_id("turn"))
    matter_id: str | None = None
    thread_id: str | None = None
    today: date = field(default_factory=date.today)
    jurisdiction: str = "Telangana"


@dataclass
class TurnOutput:
    turn_id: str
    answer: Answer
    matter: Matter | None
    metrics: TurnMetrics
    replayed: bool = False


# ============================================================== ADMIT =====


_MATTER_SIGNALS = (
    "client", "police", "arrest", "notice", "cheque", "suit", "court", "case",
    "landlord", "tenant", "accused", "complaint", "fir", "decree", "appeal",
    "possession", "land", "divorce", "maintenance", "bail", "agreement",
    "dispute", "sued", "filed", "summons", "eviction", "recovery",
)

_ABOUT_NM = ("what can you do", "who are you", "what areas", "how do you work",
             "what do you cover")


@implements("B1")
def classify_route(message: str) -> tuple[Route, Mode, str]:
    """Route on WHAT THE MESSAGE DISCLOSES, never on its length.

    Length was a measured live defect in both directions: a five-word emergency
    read as a greeting, and a full workup run on "what can you help me with?".
    """
    text = message.strip().lower()
    if not text:
        raise TurnRefused("an empty message discloses nothing")

    if any(p in text for p in _ABOUT_NM):
        return Route.NON_MATTER, Mode.SHORT_QUESTION, \
            "Taking this as a question about what I do, not a matter."

    if any(s in text for s in _MATTER_SIGNALS):
        mode = Mode.FULL_BRIEF if len(text.split()) > 25 else Mode.SHORT_QUESTION
        return Route.MATTER, mode, \
            "Taking this as a matter. Say if I have that wrong."

    greetings = {"hi", "hello", "hey", "good morning", "good evening", "thanks",
                 "how are you", "how are you today"}
    if text.rstrip("?.! ") in greetings or len(text.split()) <= 3:
        return Route.NON_MATTER, Mode.SHORT_QUESTION, \
            "No matter disclosed yet."

    # Ambiguity resolves to MATTER: a full workup on a question wastes time,
    # while a matter read as a greeting is negligent.
    return Route.MATTER, Mode.SHORT_QUESTION, \
        "Taking this as a matter. Say if I have that wrong."


_ROLE_WORDS: dict[str, Role] = {
    "our client is the accused": Role.ACCUSED,
    "we act for the accused": Role.ACCUSED,
    "we are the complainant": Role.COMPLAINANT,
    "we act for the complainant": Role.COMPLAINANT,
    "we act for the plaintiff": Role.PLAINTIFF,
    "we act for the defendant": Role.DEFENDANT,
    "we act for the tenant": Role.RESPONDENT,
    "we act for the landlord": Role.PLAINTIFF,
    "we act for the wife": Role.PETITIONER,
    "we act for the husband": Role.RESPONDENT,
}


@implements("C3")
def read_posture(message: str) -> tuple[Role, Basis]:
    """Posture is taken from what the advocate STATED, never inferred from
    familiar vocabulary.

    "The landlord has issued a quit notice" does not tell you which side the
    client is on. Guessing there is the defect that told an employer he could
    claim reinstatement from himself -- every citation correct, the whole
    analysis on the wrong side.
    """
    text = message.lower()
    for phrase, role in _ROLE_WORDS.items():
        if phrase in text:
            return role, Basis.STATED
    return Role.UNKNOWN, Basis.UNKNOWN


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


class TurnEngine:
    """Pure orchestration. Every dependency arrives as a port."""

    def __init__(self, store: StorePort, evidence: EvidencePort, model: ModelPort,
                 coverage: CoveragePort | None = None) -> None:
        self._store = store
        self._evidence = evidence
        self._model = model
        # Optional, and its ABSENCE IS NOT SILENCE: with no coverage port the
        # engine fires G-COVERAGE in the `not_measured` state rather than
        # skipping the gate, so an unwired installation discloses that it
        # cannot vouch for coverage instead of implying it can.
        self._coverage = coverage

    def run(self, turn: TurnInput) -> TurnOutput:
        metrics = TurnMetrics(turn_id=turn.turn_id, matter_id=turn.matter_id)
        started = time.perf_counter()
        try:
            return self._run(turn, metrics, started)
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

    # ---------------------------------------------------------------------
    def _run(self, turn: TurnInput, metrics: TurnMetrics, started: float) -> TurnOutput:
        # ---------------- ADMIT ----------------
        t0 = time.perf_counter()
        metrics.failed_phase = Phase.ADMIT

        route, mode, mode_statement = classify_route(turn.message)

        if route is Route.NON_MATTER:
            # NOTHING is written to any file on this route.
            answer = self._non_matter_answer(turn, mode, mode_statement, metrics)
            metrics.outcome = Outcome.OK
            metrics.stages["admit_ms"] = int((time.perf_counter() - t0) * 1000)
            metrics.latency_ms = int((time.perf_counter() - started) * 1000)
            self._store.record_metrics(metrics.as_dict())
            return TurnOutput(turn.turn_id, answer, None, metrics)

        matter = self._load_or_create(turn)
        metrics.matter_id = matter.id

        # Idempotency: replaying a turn returns the committed result rather
        # than applying it twice. Without this a network retry duplicates
        # facts, splits threads, and re-raises resolved urgencies -- invisibly.
        if matter.has_applied(turn.turn_id):
            metrics.outcome = Outcome.OK
            metrics.latency_ms = int((time.perf_counter() - started) * 1000)
            self._store.record_metrics(metrics.as_dict())
            return TurnOutput(turn.turn_id, self._replay_answer(mode, mode_statement),
                              matter, metrics, replayed=True)

        expected_version = matter.version

        # ---- ADMIT-A: screens, on names and danger only --------------------
        # An external review found this code doing what the first draft of the
        # spec described: extracting and binding substance BEFORE the screens.
        # That both retains material on an uncleared file and sends privileged
        # content to a model provider before the matter is cleared to hold it.
        screens = self._run_screens(matter, turn, metrics)
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
            metrics.latency_ms = int((time.perf_counter() - started) * 1000)
            self._store.record_metrics(metrics.as_dict())
            return TurnOutput(turn.turn_id, answer, None, metrics)

        # ======== SCREEN BOUNDARY: no substance is read, retained, or sent to
        # a provider above this line.

        # ---- ADMIT-B: substance ---------------------------------------------
        matter, bound = self._admit_facts(matter, turn)
        metrics.stages["admit_ms"] = int((time.perf_counter() - t0) * 1000)

        # ---------------- DERIVE ----------------
        t1 = time.perf_counter()
        metrics.failed_phase = Phase.DERIVE
        elements: list[Element] = []
        relied_on: tuple[Finding, ...] = ()
        retrieved: tuple[Finding, ...] = ()

        if bound.blocks:
            # G-THREAD. The account is KEPT on the matter -- it is the binding
            # that is refused, not the facts. Guessing here attaches one
            # thread's posture and limitation to another thread's facts, and
            # every citation stays correct while the advice inverts.
            metrics.fire("G-THREAD", bound.state.value, bound.reason)
            elements.append(Element(
                kind=ElementKind.QUESTION, text=bound.question,
                signal=Signal.CONTRADICTION))
            if bound.proposal is not None:
                elements.append(Element(
                    kind=ElementKind.GROUND,
                    text=(f"Proposed merge, not performed: {bound.proposal.left} "
                          f"and {bound.proposal.right} on {bound.proposal.on}.")))
            answer = Answer(route=route, mode=mode, mode_statement=mode_statement,
                            elements=tuple(elements), blocked=True,
                            blocked_reason=f"G-THREAD: {bound.reason}")
            thread = None
        elif not bound.thread.posture.resolved:
            # G-POSTURE. Downstream derivations are NOT COMPUTED AT ALL:
            # nothing wrong is generated, and nothing is paid for. The block IS
            # the answer.
            thread = bound.thread
            metrics.fire("G-POSTURE", "unresolved",
                         f"thread {thread.id} has role=unknown; no directive step "
                         f"is computed")
            elements.append(Element(
                kind=ElementKind.QUESTION,
                thread=thread.id,
                text=("Whose side are we on in this matter — do we act for the "
                      "party moving, or the party answering? I am not able to "
                      "recommend a step until that is settled, because the same "
                      "provision helps one side and hurts the other."),
                signal=Signal.UNRESOLVED_POSTURE,
            ))
            answer = Answer(route=route, mode=mode, mode_statement=mode_statement,
                            elements=tuple(elements), blocked=True,
                            blocked_reason="G-POSTURE: posture unresolved")
        else:
            thread = bound.thread
            derived, relied_on, retrieved = self._derive(thread, turn, metrics)
            elements.extend(derived)
            answer = Answer(route=route, mode=mode, mode_statement=mode_statement,
                            elements=tuple(elements))

        # Class-B invariants, asserted on the ASSEMBLED object, before emission.
        self._assert_invariants(answer, metrics)

        # THE GROUNDING GATE, on the assembled answer and on the findings it
        # actually rests on. It runs LAST because everything before it can
        # still edit, reorder or truncate the text that will be emitted, and a
        # check that runs on an earlier draft has checked a different string.
        report = grounding.verify(answer, relied_on, retrieved)
        metrics.grounding = report.as_dict()
        for violation in report.violations:
            metrics.fire(violation.gate_id,
                         _GROUNDING_STATE[violation.gate_id], violation.detail)
        metrics.stages["derive_ms"] = int((time.perf_counter() - t1) * 1000)

        if metrics.gating_violations:
            # A grounding violation GATES the output. It does not soften it.
            metrics.outcome = Outcome.GATED
            metrics.latency_ms = int((time.perf_counter() - started) * 1000)
            self._store.record_metrics(metrics.as_dict())
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
                disclosures=tuple(e.text for e in answer.elements if e.disclosure))

        # ======== BYTE BOUNDARY: nothing above has been shown or saved.

        # ---------------- EMIT ----------------
        t2 = time.perf_counter()
        metrics.failed_phase = Phase.EMIT
        matter = matter.applied(turn.turn_id)
        try:
            matter = self._store.commit(matter, expected_version=expected_version)
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
        return TurnOutput(turn.turn_id, answer, matter, metrics)

    # ------------------------------------------------------------ helpers ---
    def _run_screens(self, matter: Matter, turn: TurnInput,
                     metrics: TurnMetrics) -> ScreenResult:
        """ADMIT-A. Names and danger only.

        SLICE 1 SCOPE, STATED HONESTLY: the conflict registry, competence and
        engagement screens are features B3-B5 and are NOT BUILT (slice 10).
        This method therefore clears every matter, and records that it did so
        WITHOUT having screened -- because a screen that has not run must never
        be indistinguishable from one that passed.

        When B3-B5 land, they land here, above the screen boundary.
        """
        metrics.fire(
            "G-UNSCREENED", "unscreened",
            "conflict, competence and engagement screens (B3-B5) are not built "
            "(slice 10). This matter was NOT screened before substance was "
            "admitted, and the output says so rather than reading as though it "
            "had passed.")
        return ScreenResult(clear=True, assessed=False)

    def _load_or_create(self, turn: TurnInput) -> Matter:
        if turn.matter_id:
            existing = self._store.load(turn.matter_id)
            if existing is None:
                raise TurnRefused(f"matter {turn.matter_id} not found")
            if existing.advocate_id != turn.advocate_id:
                raise TurnRefused("this matter belongs to another advocate")
            return existing
        title = turn.message.strip().split("\n")[0][:60] or "New matter"
        return Matter.create(advocate_id=turn.advocate_id, title=title)

    @implements("C1")
    def _admit_facts(self, matter: Matter, turn: TurnInput) -> tuple[Matter, BindResult]:
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

        bound = bind(matter, turn.message, fact, thread_hint=turn.thread_id)
        if bound.state is not BindState.BOUND or bound.thread is None:
            return matter, bound

        thread = bound.thread
        role, basis = read_posture(turn.message)
        posture: Posture = thread.posture
        if role is not Role.UNKNOWN:
            posture = posture.enrich(role, basis, source_fact=fact.id)

        thread = Thread(
            id=thread.id, label=thread.label, aliases=thread.aliases,
            identifiers=thread.identifiers, posture=posture,
            chronology=thread.chronology + (fact.id,),
            deferred_reason=thread.deferred_reason,
        )
        return matter.with_thread(thread), replace(bound, thread=thread)

    def _derive(self, thread: Thread, turn: TurnInput,
                metrics: TurnMetrics) -> tuple[list[Element], tuple, tuple]:
        """Retrieve, then assemble. Returns (elements, relied_on, retrieved).

        The two Finding tuples are returned SEPARATELY because the grounding
        gate treats them differently: what the answer rests on can withhold the
        turn, and what merely came back cannot. Collapsing them would either
        punish the product for disclosing an unusable source, or let an
        unusable source ground an answer.
        """
        elements: list[Element] = []
        retrieved: list[Finding] = []
        relied_on: list[Finding] = []
        grounds: list[Element] = []

        need = EvidenceNeed(question=turn.message.strip(),
                            governing_date=turn.today,
                            jurisdiction=turn.jurisdiction)
        result = self._evidence.fetch(need)
        metrics.evidence_rounds += 1
        retrieved.extend(result.findings)
        self._read_coverage(result, thread, metrics, grounds, relied_on)

        if self._wants_authority(turn.message):
            # G-COVERAGE, and it fires BEFORE the search rather than after it.
            # Told afterwards, the advocate reads it as a note on a result they
            # have already started trusting; told first, it is a fact about
            # what this corpus can answer.
            self._disclose_coverage(turn, thread, metrics, grounds)

            # A SECOND, DIFFERENT need. Authority retrieval is not a variation
            # on provision retrieval: different store, different attribution
            # rules, different binding computation.
            #
            # RESOLUTION BEFORE SEARCH (H3), in the only form available before
            # slice 5: seed the query from the provision this turn already
            # resolved. An advocate asks "any judgment on section 6?" and the
            # subject words are in the SECTION, not in the question.
            authority = self._evidence.fetch(replace(
                need, want_authority=True,
                question=_subject_of(need.question, result.findings)))
            metrics.evidence_rounds += 1
            retrieved.extend(authority.findings)
            self._read_coverage(authority, thread, metrics, grounds, relied_on)

        recommendation = self._recommend(thread, turn, result, metrics)
        elements.append(recommendation)
        elements.extend(grounds)
        return elements, tuple(relied_on), tuple(retrieved)

    def _disclose_coverage(self, turn: TurnInput, thread: Thread,
                           metrics: TurnMetrics, grounds: list[Element]) -> None:
        """G-COVERAGE. What this corpus can and cannot answer for, said first.

        The review's stop-ship #1: the product claims Telangana coverage
        against a corpus holding ZERO Telangana High Court judgments. That was
        measured, written down, and inert. It is now a gate.
        """
        if self._coverage is None:
            position_state, detail = "not_measured", (
                "no coverage measurement is wired into this installation, so I "
                "cannot tell you whether the binding court's output is held. "
                "Run `python tools/releasegate.py --write`.")
        else:
            position = self._coverage.position(turn.jurisdiction)
            if position.state is CoverageState.MET:
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

    @staticmethod
    def _wants_authority(message: str) -> bool:
        low = (message or "").lower()
        return any(p in low for p in _WANTS_AUTHORITY)

    def _read_coverage(self, result, thread: Thread, metrics: TurnMetrics,
                       grounds: list[Element], relied_on: list[Finding]) -> None:
        """Turn a retrieval result into elements and gate firings.

        THE THREE COVERAGE STATES ARE NOT INTERCHANGEABLE, and the whole point
        of the manifest is that this method can tell them apart:

          ANSWERED        cite it, or say why the Finding cannot be used
          NOT_HELD        an honest gap, NAMED -- disclosed to the advocate
          HELD_NOT_FOUND  a RETRIEVAL DEFECT that escalates. It is never shown
                          to the advocate as though the corpus lacked it
        """
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
                    grounds.append(Element(
                        kind=ElementKind.GROUND, thread=thread.id,
                        text=(f'{f.ref} — "{f.span.strip()[:400]}" ({f.locator}; '
                              f"{f.binding.value} for {f.binding_for} — "
                              f"{f.binding_reason})."),
                        refs=(f.locator,)))
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
                    note = (f"ADVERSE TREATMENT — {', '.join(f.treatment.verbs)}. "
                            f"Do not rely on this without reading it."
                            if adverse else
                            "Not relied on: subsequent treatment unverified.")
                    grounds.append(Element(
                        kind=ElementKind.GROUND, thread=thread.id,
                        text=(f'{f.ref} — "{f.span.strip()[:300]}" ({f.locator}; '
                              f"{f.binding.value} for {f.binding_for}). {note}"),
                        refs=(f.locator,),
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

        metrics.fire("G-HELDNOTFOUND", "held_not_found",
                     f"held but not retrieved: {result.missing}")
        grounds.append(Element(
            kind=ElementKind.GROUND, thread=thread.id,
            text=(f"A source this product declares it holds was not retrieved: "
                  f"{result.missing} That is a defect in my retrieval, not a gap "
                  f"in the law, and it is recorded as one."),
            disclosure=True))

    @implements("E2")
    def _recommend(self, thread, turn, result, metrics: TurnMetrics) -> Element:
        side = thread.posture.side.value
        cited = ""
        if result.findings:
            cited = f" The provision to work from is {result.findings[0].ref}."
        system = (
            "You are senior counsel advising an instructing advocate in India. "
            "Reply with ONE imperative next step in at most 40 words. "
            "No preamble, no options, no caveats. State the step, not the law."
        )
        prompt = Prompt(
            system=system,
            user=(f"The advocate acts for the {side} party.{cited}\n\n"
                  f"Brief: {turn.message.strip()[:1500]}\n\n"
                  f"The single next step:"),
        )
        try:
            res = self._model.complete(prompt, Tier.ROUTINE, max_tokens=120)
            metrics.record_call(res)
            text = (res.text or "").strip()
        except ModelError as exc:
            # Fail the NEED, not the turn. The gap becomes visible.
            metrics.fire("G-MODEL", "unavailable", f"model unavailable: {exc}")
            text = ""

        if not text:
            return Element(
                kind=ElementKind.QUESTION, thread=thread.id,
                text=("I could not reach the model to form a recommendation on "
                      "this turn. Nothing has been recorded as advice. Resend, "
                      "or tell me what you would like me to work on first."))
        return Element(
            kind=ElementKind.ACTION, thread=thread.id, text=text,
            no_deadline_reason="no statutory window identified on this turn")

    def _non_matter_answer(self, turn, mode, mode_statement, metrics) -> Answer:
        text = ("Brief me and I will take it from there — who the client is, "
                "what happened, and when.")
        low = turn.message.strip().lower()
        if any(p in low for p in _ABOUT_NM):
            text = ("I advise practising advocates on matters in Telangana and "
                    "the Union of India, working from the statutes and judgments "
                    "in my corpus. Brief me on a matter and I will give you a view.")
        return Answer(route=Route.NON_MATTER, mode=mode, mode_statement=mode_statement,
                      elements=(Element(kind=ElementKind.GROUND, text=text),))

    def _replay_answer(self, mode, mode_statement) -> Answer:
        return Answer(
            route=Route.MATTER, mode=mode, mode_statement=mode_statement,
            elements=(Element(
                kind=ElementKind.QUESTION,
                text="This turn was already applied to the file; nothing has been "
                     "changed a second time. Send the next instruction."),))

    def _assert_invariants(self, answer: Answer, metrics: TurnMetrics) -> None:
        """Class-B checks, on the assembled Answer, BEFORE the byte boundary."""
        if answer.route is Route.NON_MATTER:
            return
        first = answer.elements[0]
        if first.kind not in (ElementKind.ACTION, ElementKind.QUESTION):
            metrics.violate("S3", "first element is neither an action nor a question")
        if not any(e.kind in (ElementKind.ACTION, ElementKind.QUESTION)
                   for e in answer.elements):
            metrics.violate("D2", "no recommendation and no blocking question")
        for e in answer.loud_signals:
            if e.collapsible:
                metrics.violate("S5", f"loud signal {e.signal.value} is collapsible")
