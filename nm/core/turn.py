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
from dataclasses import dataclass, field
from datetime import date

from nm.domain.answer import Answer, Element, ElementKind, Mode, Route, Signal
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
from nm.ports.evidence import Coverage, EvidenceNeed, EvidencePort
from nm.ports.model import ModelError, ModelPort, Prompt, Tier
from nm.ports.store import StaleWrite, StorePort

MAX_EVIDENCE_ROUNDS = 3


class TurnRefused(Exception):
    """Raised before anything is emitted. Nothing has been shown or saved."""


@dataclass
class TurnInput:
    advocate_id: str
    message: str
    turn_id: str = field(default_factory=lambda: new_id("turn"))
    matter_id: str | None = None
    today: date = field(default_factory=date.today)


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


class TurnEngine:
    """Pure orchestration. Every dependency arrives as a port."""

    def __init__(self, store: StorePort, evidence: EvidencePort, model: ModelPort) -> None:
        self._store = store
        self._evidence = evidence
        self._model = model

    def run(self, turn: TurnInput) -> TurnOutput:
        metrics = TurnMetrics(turn_id=turn.turn_id, matter_id=turn.matter_id)
        started = time.perf_counter()
        try:
            return self._run(turn, metrics, started)
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
        matter, thread = self._admit_facts(matter, turn)
        metrics.stages["admit_ms"] = int((time.perf_counter() - t0) * 1000)

        # ======== SCREEN BOUNDARY: nothing below runs on unscreened substance.

        # ---------------- DERIVE ----------------
        t1 = time.perf_counter()
        metrics.failed_phase = Phase.DERIVE
        elements: list[Element] = []

        if not thread.posture.resolved:
            # A BLOCKING GATE. Downstream derivations are NOT COMPUTED AT ALL:
            # nothing wrong is generated, and nothing is paid for. The block IS
            # the answer.
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
                            blocked_reason="posture unresolved")
        else:
            elements.extend(self._derive(thread, turn, metrics))
            answer = Answer(route=route, mode=mode, mode_statement=mode_statement,
                            elements=tuple(elements))

        # Class-B invariants, asserted on the ASSEMBLED object, before emission.
        self._assert_invariants(answer, metrics)
        metrics.stages["derive_ms"] = int((time.perf_counter() - t1) * 1000)

        if metrics.gating_violations:
            # A grounding violation GATES the output. It does not soften it.
            metrics.outcome = Outcome.GATED
            metrics.latency_ms = int((time.perf_counter() - started) * 1000)
            self._store.record_metrics(metrics.as_dict())
            raise TurnRefused(
                "output gated by a grounding violation: "
                + "; ".join(v.detail for v in metrics.gating_violations))

        # ======== BYTE BOUNDARY: nothing above has been shown or saved.

        # ---------------- EMIT ----------------
        t2 = time.perf_counter()
        metrics.failed_phase = Phase.EMIT
        matter = matter.applied(turn.turn_id)
        try:
            matter = self._store.commit(matter, expected_version=expected_version)
        except StaleWrite:
            # The matter moved underneath. Re-derive rather than overwrite.
            raise
        metrics.outcome = Outcome.BLOCKED if answer.blocked else Outcome.OK
        metrics.failed_phase = None
        metrics.stages["emit_ms"] = int((time.perf_counter() - t2) * 1000)
        metrics.latency_ms = int((time.perf_counter() - started) * 1000)
        self._store.record_metrics(metrics.as_dict())
        return TurnOutput(turn.turn_id, answer, matter, metrics)

    # ------------------------------------------------------------ helpers ---
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
    def _admit_facts(self, matter: Matter, turn: TurnInput) -> tuple[Matter, Thread]:
        fact = Fact.create(
            statement=turn.message.strip(),
            provenance=Provenance(kind="advocate_statement", turn=turn.turn_id),
            certainty=Certainty.ASSERTED,
        )
        matter = matter.with_fact(fact)

        thread = matter.threads[0] if matter.threads else Thread.create(
            label=turn.message.strip().split("\n")[0][:48] or "Thread 1")

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
        return matter.with_thread(thread), thread

    def _derive(self, thread: Thread, turn: TurnInput, metrics: TurnMetrics) -> list[Element]:
        elements: list[Element] = []

        need = EvidenceNeed(question=turn.message.strip(), governing_date=turn.today)
        result = self._evidence.fetch(need)
        metrics.evidence_rounds += 1

        ground: Element | None = None
        if result.coverage is Coverage.ANSWERED and result.findings:
            f = result.findings[0]
            if not f.usable:
                metrics.violate("H5", f"span does not support: {f.proposition}", gating=True)
            else:
                ground = Element(
                    kind=ElementKind.GROUND, thread=thread.id,
                    text=f"{f.ref} — \"{f.span.strip()[:400]}\" ({f.locator}; "
                         f"{f.binding.value} for {f.binding_for}).",
                    refs=(f.locator,))
        elif result.coverage is Coverage.NOT_HELD:
            ground = Element(
                kind=ElementKind.GROUND, thread=thread.id,
                text=f"Not held in the corpus: {result.missing}. I am telling you "
                     f"what is missing rather than answering from memory.")
        else:
            # HELD BUT NOT FOUND is a DEFECT that escalates -- never disclosed
            # to the advocate as a corpus gap.
            metrics.violate("H8", f"held but not retrieved: {result.missing}")

        recommendation = self._recommend(thread, turn, result, metrics)
        elements.append(recommendation)
        if ground is not None:
            elements.append(ground)
        return elements

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
            metrics.violate("7.4.4", f"model unavailable: {exc}")
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
