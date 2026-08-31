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

from nm.core import chronology, deadlines, grounding, limitation, thresholds
from nm.core import dispute as dispute_reader
from nm.core import posture as posture_reader
from nm.core.threading import BindResult, BindState, bind, identifiers_in
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
        memory = matter_memory.build(
            matter, bound.thread.id if bound.thread is not None else None)

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
            derived, relied_on, retrieved = self._derive(
                thread, turn, metrics, memory, side_blind=True,
                facts=matter.facts)
            elements.extend(derived)
            answer = Answer(route=route, mode=mode, mode_statement=mode_statement,
                            elements=tuple(elements), blocked=True,
                            blocked_reason="G-POSTURE: posture unresolved")
        else:
            thread = bound.thread
            derived, relied_on, retrieved = self._derive(
                thread, turn, metrics, memory, facts=matter.facts)
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
        dated = self._read_dates(turn, matter, thread, metrics)
        ids = [fact.id]
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
            ids.append(event.id)

        thread = replace(thread, chronology=thread.chronology + tuple(ids))
        matter = matter.with_thread(thread)

        if not posture.resolved:
            # THE WHOLE FILE, not just this message and not just the
            # narrative. What was already established, what has already
            # been asked, and what came back -- so an advocate who
            # answered on turn 2 is not asked again on turn 3.
            memory = matter_memory.build(matter, thread.id)
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

    @implements("C5")
    def _read_dates(self, turn: TurnInput, matter: Matter, thread: Thread,
                    metrics: TurnMetrics):
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
                chronology.build_prompt(turn.message, turn.today, account),
                chronology.DATE_SCHEMA, Tier.ROUTINE, max_tokens=700)
            metrics.record_call(res)
            metrics.chronology_reads += 1
            rows = chronology.interpret(turn.message, turn.today, res.data or {})
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
                ) -> tuple[list[Element], tuple, tuple]:
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
                            account=memory.account if memory else "")
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
        if not side_blind:
            rows, register = self._thresholds(
                thread, turn, result, metrics, facts)
            grounds.extend(rows)

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
                                register))
        elements.extend(grounds)
        return elements, tuple(relied_on), tuple(retrieved)

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
                    ) -> tuple[list[Element], tuple[deadlines.Deadline, ...]]:
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

        ours = self._limitation(thread.posture.side, thread, result, chart)
        register = self._register(thread, ours)
        map_ = thresholds.for_thread(
            {thresholds.Threshold.LIMITATION: thresholds.from_limitation(ours)})

        # D1.1 -- arithmetic checked against THE FILE'S OWN DATES. A twelve-year
        # clock is not absurd; one that expires before the file's earliest
        # event is arithmetic about a different matter.
        for problem in thresholds.absurd(map_, dated):
            metrics.violate("D1", problem)
            out.append(Element(
                kind=ElementKind.GROUND, thread=thread.id, disclosure=True,
                text=f"I am not putting this figure in front of you: {problem}"))

        out.extend(self._limitation_elements(thread, turn, ours, "our"))

        # D2 -- THEIRS TOO, and on a defending thread it is often the whole
        # answer: it disposes of the claim without touching the merits.
        if thread.posture.side is Side.DEFENDING:
            theirs = self._limitation(Side.MOVING, thread, result, chart)
            register += self._register(thread, theirs)
            out.extend(self._limitation_elements(thread, turn, theirs, "their"))

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
        return out, deadlines.register(register, turn.today)

    @implements("D2")
    def _limitation(self, for_side: Side, thread: Thread, result,
                    chart: tuple[Fact, ...]) -> limitation.Limitation:
        """Limitation for one side -- or NOT COMPUTED, with the reason said.

        Slice 4 computes it where the retrieval produced an Article AND the
        chart holds a dated accrual. Anything else is NOT_COMPUTED carrying
        why, because a limitation nobody computed must never read as a
        limitation that is fine.
        """
        found = next((f for f in result.findings
                      if "Article" in f.ref or "Limitation" in f.ref), None)
        accrual = next((f for f in chart if f.date is not None), None)
        if found is None:
            return limitation.not_computed(
                for_side, "no limitation Article was retrieved for this cause",
                thread.chronology)
        if accrual is None:
            return limitation.not_computed(
                for_side, "no dated event on this thread to run the period from",
                thread.chronology)

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
                thread.chronology)
        return limitation.compute(
            for_side=for_side, article=found.ref, accrual=accrual.id,
            accrual_on=accrual.date, accrual_reason=accrual.statement[:70],
            chronology=thread.chronology, period=period,
            considered={f.id: "on the chart; it neither restarts nor extends"
                        for f in chart if f.id != accrual.id})

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
        out.append(Element(
            kind=ElementKind.GROUND, thread=thread.id,
            signal=Signal.LIMITATION_BAR if gone else Signal.NONE,
            text=(f"Limitation for {whose} side runs to "
                  f"{lim.expires_on.isoformat()} on {lim.article}, from "
                  f"{lim.accrual_reason} ({abs(days)} days "
                  f"{'ago' if gone else 'from today'})."
                  + ("" if not gone else
                     " That period has run. That is not the end of the file — "
                     "what else it offers is a separate question."))))
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

        metrics.fire("G-HELDNOTFOUND", "held_not_found",
                     f"held but not retrieved: {result.missing}")
        grounds.append(Element(
            kind=ElementKind.GROUND, thread=thread.id,
            text=(f"A source this product declares it holds was not retrieved: "
                  f"{result.missing} That is a defect in my retrieval, not a gap "
                  f"in the law, and it is recorded as one."),
            disclosure=True))

    @implements("E2")
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
                   ) -> Element:
        side = thread.posture.side.value
        cited = ""
        if result.findings:
            cited = f" The provision to work from is {result.findings[0].ref}."
        system = (
            "You are senior counsel advising an instructing advocate in India. "
            "Reply with ONE imperative next step in at most 40 words. "
            "No preamble, no options, no caveats. State the step, not the law."
        )
        # THE FILE, THEN THIS TURN. A next step recommended off the last
        # message alone re-opens ground the advocate has already covered,
        # which reads to them as the product having forgotten the matter --
        # and it is, because it had.
        file_note = memory.as_context() if memory is not None else ""
        user = f"The advocate acts for the {side} party.{cited}"
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
        first = answer.elements[0]
        if first.kind not in (ElementKind.ACTION, ElementKind.QUESTION):
            metrics.violate("S3", "first element is neither an action nor a question")
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
