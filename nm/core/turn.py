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
from datetime import date, datetime, timezone

from nm.core import (
    adversarial,
    cascade,
    chronology,
    deadlines,
    grounding,
    limitation,
    proof,
    thresholds,
)
from nm.core import cause as cause_reader
from nm.core import dispute as dispute_reader
from nm.core import evidence_item as inventory
from nm.core import factors as factor_reader
from nm.core import gaps as gap_queue
from nm.core import issues as issue_reader
from nm.core import posture as posture_reader
from nm.core import theory as theory_reader
from nm.core.threading import BindResult, BindState, bind, identifiers_in
from nm.domain import issue
from nm.domain import summary as matter_memory
from nm.domain.answer import Answer, Element, ElementKind, Mode, Route, Signal
from nm.domain.matter import (
    Basis,
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
from nm.domain.text import refuses_blank_text
from nm.domain.traceability import implements
from nm.ports.coverage import CoveragePort
from nm.ports.evidence import (
    Coverage,
    EvidenceNeed,
    EvidencePort,
    EvidenceResult,
    Finding,
    SourceKind,
    TreatmentState,
)
from nm.ports.model import ModelError, ModelPort, Prompt, Tier
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
    """Raised before any ANSWER is emitted. THE ANSWER is not saved.

    What the advocate SAID is. The docstring said "nothing has been shown or
    saved" and that was true and was a leak: a withheld turn discarded their
    own words along with the answer, so GS-15 turn 1 was refused and the
    matter was never created. The gates that withhold are about whether the
    ANSWER is supported by what was retrieved — none of them is a finding
    about the input.

    It carries the gates that withheld it and the DISCLOSURES the turn had
    already computed. Withholding the answer is not the same as withholding the
    reason: a disclosure states what could not be established, asserts no law,
    and can mislead nobody -- while a bare refusal leaves the advocate with
    nothing to act on and no idea whether to try again.
    """

    def __init__(self, message: str, *, gates: tuple[str, ...] = (),
                 disclosures: tuple[str, ...] = (),
                 matter_id: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.gates = gates
        self.disclosures = disclosures
        self.matter_id = matter_id
        """The file the refused turn was about, where there is one.

        A caller that cannot name the matter opens a new one on the next
        turn — which is how GS-15 came to run four turns across four
        different files, each blocking on a posture nobody had stated."""


@refuses_blank_text()
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
            name=f"{what} on {thread.id}",
            value=str(produced),
            from_facts=tuple(from_facts),
            # A COUNT. It grows as the file grows, so its growth is not a
            # correction — but it is still watched for LOSS, which is the
            # forgetting this whole mechanism exists to find.
            kind=cascade.Kind.MEASUREMENT))


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
        matter, bound = self._admit_facts(matter, turn, metrics)
        metrics.stages["admit_ms"] = int((time.perf_counter() - t0) * 1000)

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
                gate="G-THREAD", signal=Signal.CONTRADICTION))
            if bound.proposal is not None:
                elements.append(Element(
                    kind=ElementKind.GROUND,
                    text=(f"Proposed merge, not performed: {bound.proposal.left} "
                          f"and {bound.proposal.right} on {bound.proposal.on}.")))
            answer = Answer(route=route, mode=mode, mode_statement=mode_statement,
                            elements=tuple(elements), blocked=True,
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
            metrics.fire("G-POSTURE", "unresolved",
                         f"thread {thread.id} has role=unknown; no directive step "
                         f"and no authority set is computed")
            described = thread.posture.client_described_as
            if described:
                # THE QUESTION NARROWS. Repeating the general question at an
                # advocate who has already named their client is how the
                # previous version trapped every multi-turn conversation.
                ask = (f"You act for the {described}. Did they file, or are they "
                       f"answering something filed against them? I am not able "
                       f"to recommend a step until that is settled — the same "
                       f"provision helps one side and hurts the other, and "
                       f"{described} does not by itself say which side they are "
                       f"on.")
            else:
                ask = ("Whose side are we on in this matter — do we act for the "
                       "party moving, or the party answering? I am not able to "
                       "recommend a step until that is settled, because the same "
                       "provision helps one side and hurts the other.")

            # ASKED TWICE ALREADY AND STILL OPEN. Putting it a third time in
            # the same words is the product failing to listen: an advocate
            # who has passed over a question twice is telling you something,
            # usually that they read it as rhetorical. So it stops being a
            # question and becomes a stated blocker with the answer spelled
            # out, which is the one form they have not yet ignored.
            standing = matter.open_question("G-POSTURE", thread.id)
            if standing is not None and standing.ignored:
                ask = (f"I have asked twice and this is still open, so I am "
                       f"stating it rather than asking again: NOTHING on this "
                       f"thread can be advised until I know which side we are "
                       f"on. Reply with one word — {'moving' !r} or "
                       f"{'defending' !r} — or name the role "
                       f"(plaintiff, defendant, petitioner, respondent, "
                       f"appellant, accused). Everything else you have told me "
                       f"is on the file and I will not ask for it again.")
            # THE QUESTION LEADS. It is the blocking thing, and S3 requires
            # the first element to be an action or a question -- what
            # follows is what could be established without knowing the side.
            elements.append(Element(
                kind=ElementKind.QUESTION, thread=thread.id, text=ask,
                gate="G-POSTURE", signal=Signal.UNRESOLVED_POSTURE,
            ))
            derived, relied_on, retrieved, derived_values = self._derive(
                thread, turn, metrics, memory, side_blind=True,
                facts=matter.facts, matter_id=matter.id)
            elements.extend(derived)
            answer = Answer(route=route, mode=mode, mode_statement=mode_statement,
                            elements=tuple(elements), blocked=True,
                            blocked_reason="G-POSTURE: posture unresolved")
        else:
            thread = bound.thread
            derived, relied_on, retrieved, derived_values = self._derive(
                thread, turn, metrics, memory, facts=matter.facts,
                matter_id=matter.id)
            elements.extend(derived)
            answer = Answer(route=route, mode=mode, mode_statement=mode_statement,
                            elements=tuple(elements))

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
        if not answer.blocked:
            answer = replace(answer, elements=tuple(
                [*answer.elements, *self._exposure(matter, metrics)]))

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
            try:
                matter = self._store.commit(
                    matter, expected_version=expected_version)
            except Exception as exc:  # noqa: BLE001 -- reported, never fatal
                # Losing the note is worse than the refusal and is not worth
                # turning the refusal into a crash over.
                metrics.violate(
                    "I1", f"a withheld turn did not keep what the advocate "
                          f"said: {type(exc).__name__}: {exc}")

            metrics.latency_ms = int((time.perf_counter() - started) * 1000)
            self._store.record_metrics(metrics.as_dict())
            self._record_turn(turn, answer, matter, metrics, derived_values)
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
                matter_id=matter.id)

        # ======== BYTE BOUNDARY: nothing above has been shown or saved.

        # ---------------- EMIT ----------------
        t2 = time.perf_counter()
        metrics.failed_phase = Phase.EMIT
        matter = self._remember_questions(matter, answer, metrics, turn)
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
        self._record_turn(turn, answer, matter, metrics, derived_values)
        return TurnOutput(turn.turn_id, answer, matter, metrics)

    def _record_turn(self, turn: TurnInput, answer: Answer, matter: Matter,
                     metrics: TurnMetrics,
                     derived: tuple = ()) -> None:
        """The served turn, kept. AFTER the commit, and never instead of it.

        Nothing else held this. The matter keeps facts and questions, the
        metrics keep counts and carry no client words by design, and the
        ANSWER -- the thing the advocate actually read -- was held by neither.
        A run could be inspected only while its stdout was still on screen,
        which is no way to review a conversation a week later.

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
                "today": turn.today.isoformat(),
                "message": turn.message,
                "route": answer.route.value,
                "mode": answer.mode.value,
                "mode_statement": answer.mode_statement,
                "blocked": answer.blocked,
                "blocked_reason": answer.blocked_reason,
                "elements": [
                    {"kind": e.kind.value, "text": e.text, "thread": e.thread,
                     "signal": e.signal.value, "disclosure": e.disclosure,
                     "gate": e.gate, "collapsible": e.collapsible,
                     "by_when": e.by_when.isoformat() if e.by_when else None,
                     "no_deadline_reason": e.no_deadline_reason,
                     "refs": list(e.refs)}
                    for e in answer.elements],
                "gates_fired": [
                    {"gate": g.gate_id, "state": g.state}
                    for g in metrics.gates_fired],
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
                    {"name": d.name, "value": d.value,
                     "from_facts": list(d.from_facts)}
                    for d in derived],
                "cost_usd": metrics.cost_usd,
                "llm_calls": metrics.llm_calls,
            })
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a silence
            metrics.violate(
                "I1", f"the turn was served and not recorded for review: "
                      f"{type(exc).__name__}: {exc}")

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

        # IS THIS THE SAME DISPUTE? Read only when it can matter: the
        # matter already has a thread and the message carries no number of
        # record. With a number, rule 2 or rule 3 decides and no model call
        # is needed; with no thread yet, there is nothing to confuse it
        # with.
        opens = None
        if matter.threads and not identifiers_in(turn.message):
            opens = self._read_dispute(matter, turn, metrics)

        bound = bind(matter, turn.message, fact, thread_hint=turn.thread_id,
                     opens_new_dispute=opens)
        if bound.state is not BindState.BOUND or bound.thread is None:
            return matter, bound

        thread = bound.thread
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
            matter = matter.with_fact(event)
            added.append(event)
            ids.append(event.id)

            # THE ROW SAYS WHAT IT REPLACES, so nothing has to rebuild the
            # relationship afterwards. `interpret` has already dropped an id
            # the file does not hold.
            if row.corrects:
                superseded = next(
                    (f for f in matter.facts if f.id == row.corrects), None)
                if superseded is not None and superseded.superseded_by is None:
                    metrics.fire("G-CORRECTION", "superseded",
                                 f"{row.corrects} replaced by {event.id}")
                    matter = matter.amending(
                        replace(superseded, superseded_by=event.id))

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
                    (f"You said {phrase!r}. I have not taken anything as "
                     f"replaced, so both are still on the file: "
                     + "; ".join(f"{f.statement[:44]} ({f.date.isoformat()})"
                                 for f in [*others, *added]
                                 if f.date is not None)
                     + ". Which one is right?"),
                    turn.turn_id, thread.id)


        if not posture.resolved:
            # THE WHOLE FILE, not just this message and not just the
            # narrative. What was already established, what has already
            # been asked, and what came back -- so an advocate who
            # answered on turn 2 is not asked again on turn 3.
            memory = matter_memory.build(
                matter, thread.id, about=turn.message,
                load_bearing=self._load_bearing(matter, thread))
            stated = self._read_posture(turn, metrics, memory)
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
                              f"{stated.quoted[:60]!r}")
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
                              f"({posture.client_described_as!r}): {why[:90]}")

        thread = replace(thread, posture=posture)
        return matter.with_thread(thread), replace(bound, thread=thread)

    @implements("D4")
    def _read_cause(self, turn: TurnInput, memory, metrics: TurnMetrics,
                    grounds: list[Element]) -> str | None:
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
        account = memory.account if memory else ""
        try:
            res = self._model.structured(
                cause_reader.build_prompt(turn.message, account),
                cause_reader.CAUSE_SCHEMA, Tier.ROUTINE, max_tokens=300)
            metrics.record_call(res)
            metrics.cause_reads += 1
            read = cause_reader.interpret(
                turn.message, res.data or {},
                advocate_words=memory.advocate_words if memory else "")
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
    def _read_dates(self, turn: TurnInput, matter: Matter, thread: Thread,
                    metrics: TurnMetrics, existing: tuple = ()):
        """The events in this message, with their dates where dates exist.

        A failed read yields NO ROWS, never a dated one. The asymmetry is the
        point: an event missing from the chart costs a question, and an event
        wrongly dated costs a limitation calculation the advocate acts on
        without knowing it was invented.
        """
        account = "\n".join(f.statement for f in matter.facts
                            if f.id in set(thread.chronology))
        try:
            res = self._model.structured(
                chronology.build_prompt(turn.message, turn.today, account,
                                        existing),
                chronology.DATE_SCHEMA, Tier.ROUTINE, max_tokens=700)
            metrics.record_call(res)
            metrics.chronology_reads += 1
            rows = chronology.interpret(
                turn.message, turn.today, res.data or {},
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
                                      f"{row.event[:40]!r}: {row.refused}")
        return rows

    @implements("C4")
    def _read_dispute(self, matter: Matter, turn: TurnInput,
                      metrics: TurnMetrics) -> bool | None:
        """Does this message continue the thread on the file, or open one?

        Returns THREE STATES, and `None` is the one that earns its keep: it
        means the read did not run or could not tell, and `bind` then ASKS
        rather than assuming a continuation. Defaulting to `False` here
        would restore the defect -- every failed read becoming a silent
        merge -- which is why this returns None and not a boolean.
        """
        on_file = "\n".join(
            f"- {t.label}" + (f" (we act for the {t.posture.role.value})"
                              if t.posture.role is not Role.UNKNOWN else "")
            for t in matter.threads)
        try:
            res = self._model.structured(
                dispute_reader.build_prompt(turn.message, on_file),
                dispute_reader.DISPUTE_SCHEMA, Tier.ROUTINE, max_tokens=200)
            metrics.record_call(res)
            metrics.binding_reads += 1
            read = dispute_reader.interpret(turn.message, res.data or {})
        except ModelError as exc:
            metrics.fire("G-MODEL", "unavailable",
                         f"the dispute read could not run: {exc}")
            return None
        except Exception as exc:  # noqa: BLE001 -- ERROR, never a warning
            metrics.violate("C4", f"dispute read failed: "
                                  f"{type(exc).__name__}: {exc}")
            return None

        if read.refused:
            metrics.violate("C4", f"dispute read refused: {read.refused}")
            return None
        if read.opens:
            # DISCLOSED. A split is the recoverable direction, but it is
            # still a decision about the advocate's file and they can see it.
            metrics.violate(
                "C4", f"read as a NEW dispute on {read.quoted[:50]!r}: "
                      f"{read.why[:90]}")
            return True
        if read.continues:
            return False
        return None

    @implements("C3")
    def _read_role(self, described: str, memory, metrics: TurnMetrics):
        """Which procedural role a NAMED client occupies. Never who they are.

        Failing to read it leaves posture unresolved and blocking, exactly
        as failing to read the posture does. A role that could not be read
        must never look like a role that was.
        """
        try:
            res = self._model.structured(
                posture_reader.build_role_prompt(
                    described, memory.advocate_words if memory else ""),
                posture_reader.ROLE_SCHEMA, Tier.ROUTINE, max_tokens=150)
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
                facts: tuple[Fact, ...] = (),
                matter_id: str = "",
                ) -> tuple[list[Element], tuple, tuple, tuple]:
        """Retrieve, then assemble. Returns (elements, relied_on, retrieved).

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
                            cause_of_action=self._read_cause(
                                turn, memory, metrics, grounds))
        result = self._fetch(need, metrics)
        retrieved.extend(result.findings)
        self._read_coverage(result, thread, metrics, grounds, relied_on)

        if self._wants_authority(turn.message) and not side_blind:
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
            authority = self._fetch(replace(
                need, want_authority=True,
                question=_subject_of(need.question, result.findings)), metrics)
            retrieved.extend(authority.findings)
            self._read_coverage(authority, thread, metrics, grounds, relied_on)

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
                thread, turn, result, metrics, facts)
            grounds.extend(rows)

            # D9 -- THE ISSUES, AFTER the thresholds and never before them.
            # A threshold disposes of a claim without reaching the merits, so
            # an issue list read first invites an hour on the theory of a suit
            # that cannot be maintained.
            issues_out = self._issues(turn, thread, memory, metrics)
            grounds.extend(issues_out)
            _record(derived, "issues", thread, thread.chronology,
                    sum(1 for e in issues_out
                        if e.kind is ElementKind.FINDING))

            # C7 -- WHAT THE EVIDENCE IS AND WHO HAS IT. After the issues,
            # because an inventory is only readable against what has to be
            # proved.
            inventory_out = self._inventory(
                turn, thread, memory, metrics, gaps)
            grounds.extend(inventory_out)
            _record(derived, "evidence", thread, thread.chronology,
                    sum(1 for e in inventory_out
                        if e.kind is ElementKind.FINDING))

            # D6 -- THE SPINE, LAST, because it is what the issues and the
            # evidence hang off. S8's whole point: stop producing a list of
            # issues and produce a spine with the issues hanging off it.
            theory_out = self._theory(turn, thread, memory, metrics, facts)
            grounds.extend(theory_out)
            _record(derived, "theory", thread, thread.chronology,
                    sum(1 for e in theory_out
                        if e.text.startswith("Theory:")))

            # D7 -- THE OTHER SIDE'S CASE, at its strongest. After the theory,
            # because an attack is read against a spine: "they will say X" is
            # only useful once there is something for X to be against.
            attacks_out = self._attacks(turn, thread, memory, metrics)
            grounds.extend(attacks_out)
            _record(derived, "the opponent's case", thread, thread.chronology,
                    sum(1 for e in attacks_out
                        if e.text.startswith("They will say")))

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

        if not side_blind:
            elements.append(
                self._recommend(thread, turn, result, metrics, memory,
                                register, position))
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
        elements.extend(self._ask(gaps, thread, metrics))
        return elements, tuple(relied_on), tuple(retrieved), tuple(derived)

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

    @implements("D1")
    def _thresholds(self, thread: Thread, turn: TurnInput, result,
                    metrics: TurnMetrics, facts: tuple[Fact, ...],
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
            thread, result, chart, turn, metrics, out)
        ours = (limitation.not_computed(
            thread.posture.side,
            "we are defending and nothing on this thread describes a claim of "
            "ours; a counterclaim would have its own accrual",
            thread.chronology) if defending else claimant)
        register = self._register(thread, claimant)
        map_ = thresholds.for_thread(
            {thresholds.Threshold.LIMITATION:
             thresholds.from_limitation(claimant)})

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
        if blocked:
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"{len(blocked)} of {len(map_)} thresholds are not "
                      f"assessed on this thread: "
                      f"{', '.join(a.threshold.value for a in blocked)}. Those "
                      f"are gaps in the map, not findings that they do not "
                      f"arise.")))
        return out, deadlines.register(register, turn.today), claimant

    @implements("D2")
    def _limitation(self, for_side: Side, thread: Thread, result,
                    chart: tuple[Fact, ...], turn: TurnInput,
                    metrics: TurnMetrics,
                    grounds: list[Element]) -> limitation.Limitation:
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
        accrual = next((f for f in chart if f.date is not None), None)
        if found is None:
            return limitation.not_computed(
                for_side, "no limitation Article was retrieved for this cause",
                live)
        if accrual is None:
            return limitation.not_computed(
                for_side, "no dated event on this thread to run the period from",
                live)

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
        bare = limitation.compute(
            for_side=for_side, article=found.ref, accrual=accrual.id,
            accrual_on=accrual.date, accrual_reason=accrual.statement[:70],
            chronology=live, period=period)

        read = self._factors(turn, thread, chart, metrics, grounds,
                             bare.expires_on)

        return limitation.compute(
            for_side=for_side, article=found.ref, accrual=accrual.id,
            accrual_on=accrual.date, accrual_reason=accrual.statement[:70],
            chronology=live, period=period,
            factors=read.factors)

    @implements("D3")
    def _register(self, thread: Thread, lim: limitation.Limitation,
                  ) -> tuple[deadlines.Deadline, ...]:
        """The limitation window as a register entry -- COMPUTED OR NOT.

        An uncomputed window is entered with `on=None`, which renders as
        NOT_COMPUTED. Leaving it off would tell the advocate there is no
        deadline, which is the opposite of what is known.
        """
        whose = "our" if lim.for_side is thread.posture.side else "their"
        return (deadlines.Deadline(
            thread=thread.id, kind=deadlines.DeadlineKind.LIMITATION,
            source=lim.article or "no Article retrieved",
            action=f"commence {whose} claim within the limitation period",
            owner="the instructing advocate",
            consequence="the claim is barred and the merits are never reached",
            on=lim.expires_on),)

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
            return [Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"I have not computed the limitation position for "
                      f"{whose} side on this thread: "
                      f"{lim.not_computed_because}."))]

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
            f"{f.statement[:44]} ({f.date.isoformat()})"
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
                "Run `python tools/releasegate.py --write`.")
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
                      memory=None):
        """What the advocate STATED about whom they act for, read by model.

        There is no phrase list. There was one, of ten exact phrases, and an
        advocate answering the blocking question in any other words was asked
        it again -- so every multi-turn conversation trapped the person using
        it. A longer list is the same defect at a larger size.

        `posture.interpret` refuses anything the message does not support, and
        a refusal leaves posture exactly where it was: unresolved, and
        blocking. Failing to read a posture must never look like reading one.
        """
        try:
            res = self._model.structured(
                posture_reader.build_prompt(
                    turn.message,
                    memory.as_context() if memory is not None else ""),
                posture_reader.POSTURE_SCHEMA, Tier.ROUTINE, max_tokens=200)
            metrics.record_call(res)
            metrics.posture_reads += 1
            # The span is checked against the whole account, because that is
            # what the model was given to read.
            # THE GUARD READS ONLY WHAT THE ADVOCATE WROTE, never the
            # prompt -- the prompt carries this product's own questions,
            # and one of them names both sides.
            stated = posture_reader.interpret(
                turn.message, res.data or {},
                advocate_words=memory.advocate_words if memory else "")
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

    def _fetch(self, need: EvidenceNeed, metrics: TurnMetrics):
        """One evidence round, counted against the bound.

        Every retrieval goes through here so the count cannot drift from the
        rounds actually run -- incrementing at each call site is how a bound
        stops matching reality.
        """
        if metrics.evidence_rounds >= MAX_EVIDENCE_ROUNDS:
            metrics.evidence_bound_hit = True
            return EvidenceResult(
                coverage=Coverage.NOT_HELD,
                missing=(f"the evidence bound of {MAX_EVIDENCE_ROUNDS} rounds "
                         f"was reached before this need could be met, so it was "
                         f"NOT searched."),
                searched_stores=("bound_reached",))
        metrics.evidence_rounds += 1
        return self._evidence.fetch(need)

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
        # AN INFERENCE THE RETRIEVAL RESTED ON. Disclosed before the
        # findings, because an advocate who is not told which Act was assumed
        # cannot tell a right answer from a right answer to the wrong question.
        if getattr(result, "assumption", None):
            grounds.append(Element(
                kind=ElementKind.GROUND, thread=thread.id,
                text=result.assumption, disclosure=True))

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
                        text=(f'{f.ref} — "{f.span.strip()[:400]}" ({f.locator}; '
                              f"{f.binding.value} for {f.binding_for} — "
                              f"{f.binding_reason}).{checked}"),
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
            res = self._model.structured(
                adversarial.build_salvage_prompt(
                    thread.label, why, retrieved),
                adversarial.SALVAGE_SCHEMA, Tier.ROUTINE, max_tokens=1200)
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
                 metrics: TurnMetrics) -> list[Element]:
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

        try:
            res = self._model.structured(
                adversarial.build_attack_prompt(
                    account, thread.posture.side.value),
                adversarial.ATTACK_SCHEMA, Tier.ROUTINE, max_tokens=900)
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

        for a in read.attacks:
            answer = (f"No good answer: {a.no_answer_because}"
                      if a.no_answer else a.our_answer)
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id,
                text=f"They will say, on {a.ground}: {a.their_case} — {answer}"))

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

    @implements("D7")
    def _exposure(self, matter: Matter, metrics: TurnMetrics) -> list[Element]:
        """E-082. ONE report per file, whatever the answer.

        A SINGLE-THREAD FILE STILL GETS ONE, saying none was found, because
        there is no pair for an exposure to exist in. A section that appears
        only sometimes is one the advocate cannot rely on being there — and
        cannot distinguish from one that found nothing.
        """
        threads = tuple(t.id for t in matter.threads)

        found: tuple | None
        if len(threads) < 2:
            # NOT a skip. `cross_thread` returns NONE_FOUND for a single-thread
            # file, which is a finding: there is no pair.
            found = ()
        else:
            try:
                res = self._model.structured(
                    adversarial.build_exposure_prompt(
                        tuple((t.id, t.label) for t in matter.threads)),
                    adversarial.EXPOSURE_SCHEMA, Tier.ROUTINE, max_tokens=700)
                metrics.record_call(res)
                found = adversarial.read_exposures(res.data or {}, threads)
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
                text=(f"THE CROSS-FILE PASS DID NOT RUN: "
                      f"{report.not_run_because}. Nothing here says these "
                      f"disputes do not damage each other — nobody looked."))]

        if report.state is adversarial.ExposureState.NONE_FOUND:
            return [Element(
                kind=ElementKind.GROUND, disclosure=True,
                text=("Across this file: I looked for a position on one "
                      "dispute that damages another and found none."))]

        return [Element(
            kind=ElementKind.GROUND, disclosure=True, signal=Signal.CONTRADICTION,
            text=(f"Across this file: {e.what} on {e.from_thread} — "
                  f"{e.consequence} on {e.to_thread}."))
            for e in report.exposures]

    @implements("D6")
    def _theory(self, turn: TurnInput, thread: Thread, memory,
                metrics: TurnMetrics,
                facts: tuple[Fact, ...]) -> list[Element]:
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
            adverse_said = self._model.structured(
                theory_reader.build_adverse_prompt(account, chart),
                theory_reader.ADVERSE_SCHEMA, Tier.ROUTINE, max_tokens=500)
            metrics.record_call(adverse_said)
            adverse, why = theory_reader.read_adverse(
                adverse_said.data or {}, chart)

            lines = tuple(f"{fid}: {next(f.statement for f in chart if f.id == fid)}"
                          f" — {why.get(fid, '')}" for fid in adverse)
            said = self._model.structured(
                theory_reader.build_theory_prompt(
                    account, lines, thread.posture.side.value),
                theory_reader.THEORY_SCHEMA, Tier.ROUTINE, max_tokens=800)
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
            out.append(Element(
                kind=ElementKind.FINDING, thread=thread.id,
                text=(f"Theory: {t.theme}"
                      + (f" Relief: {t.relief}." if t.relief else ""))))

        # E-080. THE ADVERSE FACTS NOBODY ANSWERED, BY NAME.
        left = theory_reader.unaccounted(read.adverse, read.theory)
        if left:
            metrics.fire("G-ADVERSE", "unaccounted", ", ".join(left))
            named = "; ".join(
                next((f.statement[:70] for f in chart if f.id == fid), fid)
                for fid in left)
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=(f"{len(left)} adverse fact(s) on this thread are neither "
                      f"explained nor conceded by the theory: {named}. A "
                      f"theory that works only because these went unmentioned "
                      f"reads perfectly and loses.")))
        elif read.adverse:
            metrics.fire("G-ADVERSE", "accounted",
                         f"{len(read.adverse)} adverse fact(s) accounted for")

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
        if position is None or position.state is not \
                limitation.LimitationState.COMPUTED:
            return ()
        return (cascade.Derived(
            name=f"limitation on {thread.id}",
            value=position.expires_on.isoformat(),
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
                      + "; ".join(f"{d.name} was {d.value} and is not "
                                  f"computed now" for d in gone)
                      + ". Nothing on the file was withdrawn — the reading "
                        "simply did not produce it this turn, and it is said "
                        "rather than left as a thinner answer."))]
            # AND IT BLOCKS, because a silently thinner answer is the failure
            # this whole mechanism exists to make impossible.
            gaps.append(gap_queue.Gap(
                what=(f"whether {gone[0].name} still holds — it was computed "
                      f"before and not on this turn"),
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
            text="A value on this thread has MOVED since the last turn. "
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
                from_facts=tuple(r.get("from_facts") or ()))
                for r in rows if r.get("name"))
        return None

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
                   gaps: list) -> list[Element]:
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
            res = self._model.structured(
                inventory.build_inventory_prompt(turn.message, account),
                inventory.INVENTORY_SCHEMA, Tier.ROUTINE, max_tokens=700)
            metrics.record_call(res)
            read = inventory.read_inventory(res.data or {}, account)
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

        out: list[Element] = []
        for refused in read.refused:
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"I did not take one item the reading offered: {refused}"))

        for item in read.items:
            out.append(Element(
                kind=ElementKind.FINDING, thread=thread.id,
                text=(f"{item.what} — held by {item.holder.value}, "
                      f"{item.form.value}")))

        # AT RISK AND NOBODY ASKED. This is the whole feature -- and it goes
        # into the GAP QUEUE rather than straight into the answer.
        #
        # §5.1: a senior does not run a script, they ask the question that
        # matters most next. A question emitted where it was detected is a
        # question that arrives in detection order, which is the order the
        # code happens to be written in.
        for what in inventory.unpreserved(read.items):
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
        for what in inventory.undelivered(read.items):
            gaps.append(gap_queue.Gap(
                what=f"when the preservation instruction for {what} goes out",
                blocks="relying on that document at trial",
                thread=thread.id, kind=gap_queue.GapKind.DEADLINE))

        # THE QUESTIONS NOBODY PUT. An inventory that lists ten items and
        # answered two questions of the thirty reads as an inventory that was
        # done.
        unasked = inventory.unasked(read.items)
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
                metrics: TurnMetrics) -> list[Element]:
        """D9. Spot the issues, and account for every one that was spotted.

        `nm/domain/issue.py` carried the whole register from slice 6 and
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
            res = self._model.structured(
                issue_reader.build_prompt(turn.message, account),
                issue_reader.ISSUE_SCHEMA, Tier.ROUTINE, max_tokens=700)
            metrics.record_call(res)
            read = issue_reader.read(res.data or {}, thread.id, account)
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

        classified = issue.classify(read.issues)

        # E-060. THE CONSERVATION INVARIANT, RUN -- not assumed because
        # `classify` looks like it cannot lose anything.
        lost = issue.accounted_for(read.issues, classified)
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
                text=(f"{i.statement} [{i.kind.value}; runs against "
                      f"{i.runs_against.value}; {effect.value} our case "
                      f"on posture v{basis}]")))

        for line in issue.considered_not_pursued(classified):
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"Considered, not pursued: {line}"))

        if read.state == "none_spotted" and read.why_not:
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"No issues identified yet: {read.why_not}"))
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
        for section in ("18", "19"):
            found = self._fetch(EvidenceNeed(
                question=f"Limitation Act 1963 section {section}",
                governing_date=turn.today,
                jurisdiction=turn.jurisdiction), metrics)
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
        account = "\n".join(f.statement for f in chart)

        try:
            res = self._model.structured(
                factor_reader.build_prompt(turn.message, account, dated),
                factor_reader.FACTOR_SCHEMA, Tier.ROUTINE, max_tokens=400)
            metrics.record_call(res)
            read = factor_reader.read(
                res.data or {}, dated, account, provisions, unextended_expiry)
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

    def _recommend(self, thread, turn, result, metrics: TurnMetrics,
                   memory=None,
                   register: "tuple[deadlines.Deadline, ...] | None" = None,
                   position: "limitation.Limitation | None" = None,
                   ) -> Element:
        side = thread.posture.side.value
        cited = ""
        if result.findings:
            cited = f" The provision to work from is {result.findings[0].ref}."

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
            else:
                worked = (f"\n\nNOT worked out: {position.not_computed_because}. "
                          f"Do not assume a position either way.")

        system = (
            "You are senior counsel advising an instructing advocate in India. "
            "Reply with ONE imperative next step in at most 40 words. "
            "No preamble, no options, no caveats. State the step, not the law.\n"
            "NEVER restate a calculation already made for them, and never "
            "recommend a step the worked position rules out. They are a "
            "professional peer: 'file within the limitation period' tells them "
            "nothing they did not know before they called.\n"
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
        # THE FILE, THEN THIS TURN. A next step recommended off the last
        # message alone re-opens ground the advocate has already covered,
        # which reads to them as the product having forgotten the matter --
        # and it is, because it had.
        file_note = memory.as_context() if memory is not None else ""
        user = f"The advocate acts for the {side} party.{cited}{worked}"
        if file_note:
            user += f"\n\n{file_note}"
        user += (f"\n\nWhat they have just asked: {turn.message.strip()[:1500]}"
                 f"\n\nThe single next step:")
        prompt = Prompt(system=system, user=user)
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
                kind=ElementKind.QUESTION, thread=thread.id, gate="G-MODEL",
                text=("I could not reach the model to form a recommendation on "
                      "this turn. Nothing has been recorded as advice. Resend, "
                      "or tell me what you would like me to work on first."))
        by_when, no_deadline = self._by_when(register, turn.today)
        return Element(
            kind=ElementKind.ACTION, thread=thread.id, text=text,
            by_when=by_when, no_deadline_reason=no_deadline)

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
        # S3 -- "the first content element is an action or a blocking
        # question" -- IS ENFORCED BY THE TYPE TOO, and the check that used to
        # sit here could no more fire than the D2 one described below.
        #
        # `Answer.__post_init__` raises on exactly this condition, so the
        # answer never reaches this line with a background element first. A
        # mutation disabling the runtime check SURVIVED, which is how it was
        # found -- and the paragraph immediately below had already written the
        # rule it was breaking three lines further up.
        #
        # D2 -- "every turn contains a recommendation or a blocking
        # question" -- IS ENFORCED BY THE TYPE, not here.
        #
        # `Answer.__post_init__` refuses a matter-route answer whose first
        # element is neither, so there is always at least one and the check
        # that used to sit here could never fire. A mutation deleting it
        # changed nothing, which is how it was found.
        #
        # A runtime check for something a type makes impossible is not a
        # second line of defence. It is a line that never executes, and a
        # reader takes it for a live guard.
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
