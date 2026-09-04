"""The adversarial pass, and salvage. D7 and D8.

D7 RUNS ACROSS THE WHOLE FILE, AFTER THE THREADS
--------------------------------------------------
Not as a step inside each thread, and the counterexample says why: *a file where
the client's own recovery suit undermines his defence in the cheque matter, and
NO SINGLE THREAD REVEALS IT.* A per-thread pass cannot see it however carefully
each thread is worked, because the exposure exists only in the pair.

EXACTLY ONCE, EMPTY OR NOT
----------------------------
E-082 is precise: cross-thread exposure is produced *exactly once on every
multi-thread file, empty or not*, and its counterexample is *emitted twice, or
silently omitted*. Both halves are defects and they fail in opposite
directions — twice is noise the advocate learns to skip, and omitted reads as
"nothing found" when nobody looked.

So `ExposureReport` has three states and one of them is NOT_RUN. An empty
report and an absent one are different facts and this type refuses to let them
render alike.

D8: ALMOST EVERY "YOU LOSE" IS ONE COORDINATE FAILING
-------------------------------------------------------
*Treat a claim as a set of coordinates — party, cause, relief, forum, timing,
procedure, burden — and ask which coordinate can move.* The measured original
error was advice that a claim was dead where a different framing on the same
facts was available.

Hence `failure_scope`: **we lose** and **we lose on this framing** are different
answers, and the overwhelming majority of weak-case reports are the second.

AND THE BOUND, WHICH IS THE HARDER HALF
-----------------------------------------
*Never manufacture a route. A system rewarded for always finding a way out will
invent one, and a hopeless alternative cause costs the client money and the
advocate credibility.*

So `route=None` is a first-class outcome: a coordinate can be varied, the result
stated, and no route found. What the type refuses is the OPPOSITE — a route
with no strength and no citation, which is how a manufactured one arrives.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nm.domain.matter import ThreadId
from nm.domain.text import blank, refuses_blank_text
from nm.domain.traceability import implements

# ============================================================ D7 ==========


@refuses_blank_text("no_answer_because")
@dataclass(frozen=True)
class Attack:
    """The case the other side will run, on the grounds they will run it."""

    thread: ThreadId
    ground: str
    their_case: str
    our_answer: str = ""
    no_answer: bool = False
    no_answer_because: str = ""
    """What we DO about it, where there is no good answer.

    D7: *where an attack has no good answer, say so plainly and resolve it into
    what we do about it.* An unanswerable attack reported and left there is
    half a finding."""

    def __post_init__(self) -> None:
        if not self.no_answer and blank(self.our_answer):
            raise ValueError(
                f"the attack on {self.ground!r} carries no answer and does not "
                f"say it has none. Those are different findings: one is work "
                f"not done, the other is a fact about the case.")
        if self.no_answer and blank(self.no_answer_because):
            raise ValueError(
                f"the attack on {self.ground!r} is marked unanswerable and "
                f"stops there. D7 requires it resolved into what we do about "
                f"it — a problem stated and abandoned is half a finding.")


@refuses_blank_text()
@dataclass(frozen=True)
class Exposure:
    """Something on one thread that damages another."""

    from_thread: ThreadId
    to_thread: ThreadId
    what: str
    consequence: str

    def __post_init__(self) -> None:
        if self.from_thread == self.to_thread:
            raise ValueError(
                "cross-thread exposure between a thread and itself is a "
                "per-thread finding wearing the wrong name, and it would make "
                "the file-level pass look like it had found something.")


class ExposureState(str, Enum):
    FOUND = "found"
    NONE_FOUND = "none_found"
    """Looked, and there is none. AN ANSWER, and D7 requires it expressly."""
    NOT_RUN = "not_run"
    """Nobody looked. The state E-082's 'silently omitted' half produces."""


@dataclass(frozen=True)
class ExposureReport:
    """Produced EXACTLY ONCE per file. Empty is not absent."""

    state: ExposureState
    exposures: tuple[Exposure, ...] = ()
    not_run_because: str = ""

    def __post_init__(self) -> None:
        if self.state is ExposureState.FOUND and not self.exposures:
            raise ValueError(
                "an exposure report claiming findings and carrying none. "
                "NONE_FOUND is the state for 'we looked and there is nothing'.")
        if self.state is ExposureState.NONE_FOUND and self.exposures:
            raise ValueError("NONE_FOUND with exposures in it")
        if self.state is ExposureState.NOT_RUN and blank(self.not_run_because):
            raise ValueError(
                "a pass that did not run must say why. Without it, NOT_RUN and "
                "NONE_FOUND are the same sentence to the advocate, and they are "
                "opposite facts.")


@implements("D7")
def cross_thread(threads: tuple[ThreadId, ...],
                 found: tuple[Exposure, ...] | None) -> ExposureReport:
    """E-082. One report per file, whatever the answer.

    `found is None` means the pass did not run and produces NOT_RUN with the
    reason — never an empty FOUND, and never silence.

    A SINGLE-THREAD FILE STILL GETS A REPORT. It says NONE_FOUND, because there
    is no pair for an exposure to exist in, and that is a finding rather than a
    reason to skip the section. A section that appears only sometimes is one
    the advocate cannot rely on being there.
    """
    if found is None:
        return ExposureReport(
            ExposureState.NOT_RUN,
            not_run_because="the cross-file pass did not run on this turn")
    if len(threads) < 2:
        return ExposureReport(ExposureState.NONE_FOUND)
    real = tuple(e for e in found
                 if e.from_thread in threads and e.to_thread in threads)
    return (ExposureReport(ExposureState.FOUND, real) if real
            else ExposureReport(ExposureState.NONE_FOUND))


@implements("D7")
def unanswered(attacks: tuple[Attack, ...]) -> tuple[str, ...]:
    """E-083. Attacks with no answer and no express statement that there is none.

    Should be empty, because `Attack` refuses one at construction. Computed
    anyway: a type guard says nothing about objects decoded from an older
    store, and this is the check a recommendation is measured against.
    """
    return tuple(a.ground for a in attacks
                 if not a.no_answer and blank(a.our_answer))


# ============================================================ D8 ==========


class Coordinate(str, Enum):
    """D8's seven. *Almost every "you lose" is the failure of one of them.*"""

    PARTY = "party"
    CAUSE = "cause"
    RELIEF = "relief"
    FORUM = "forum"
    TIMING = "timing"
    PROCEDURE = "procedure"
    BURDEN = "burden"


class Strength(str, Enum):
    """*Never present a route NM would not itself run as though it would.*"""

    WOULD_RUN = "would_run"
    ARGUABLE = "arguable"
    WOULD_NOT_RUN = "would_not_run"
    NOT_ASSESSED = "not_assessed"


class FailureScope(str, Enum):
    """*Distinguish "we lose" from "we lose on this framing".*"""

    CASE = "case"
    FRAMING = "framing"
    NOT_ASSESSED = "not_assessed"


@refuses_blank_text("route")
@dataclass(frozen=True)
class Salvage:
    """One coordinate, varied. D8's PRODUCES."""

    coordinate: Coordinate
    varied_result: str
    """What changes when this dimension moves. REQUIRED whether or not a route
    was found -- D8 says state it BEFORE reporting that the claim fails."""
    route: str = ""
    strength: Strength = Strength.NOT_ASSESSED
    findings: tuple[str, ...] = ()
    """The retrieved provisions or authorities the route rests on."""

    def __post_init__(self) -> None:
        if self.route and self.strength is Strength.NOT_ASSESSED:
            raise ValueError(
                f"the route on {self.coordinate.value} carries no strength. "
                f"D8: never present a route NM would not itself run as though "
                f"it would — an unmarked route reads as a recommendation.")
        if self.route and not self.findings:
            raise ValueError(
                f"the route on {self.coordinate.value} rests on nothing "
                f"retrieved: {self.route[:60]!r}. D8 forbids grounding a route "
                f"on a plausible recollection that such a claim exists, and a "
                f"route with no citation is exactly a category-level "
                f"suggestion — 'consider a different forum' with no forum "
                f"named.")


@implements("D8")
def unvaried(considered: tuple[Salvage, ...]) -> tuple[str, ...]:
    """Coordinates nobody moved.

    THE POPULATION IS THE SEVEN, not what was tried. D8 requires the variation
    stated BEFORE reporting failure, so a report that varied two coordinates
    and concluded the case is dead has not done the work — and the two it did
    vary would make it look as though it had.
    """
    done = {s.coordinate for s in considered}
    return tuple(c.value for c in Coordinate if c not in done)


# ========================= READING THE OTHER SIDE ==========================
#
# TWO READS BECAUSE THEY ARE TWO QUESTIONS AT TWO SCALES
# -------------------------------------------------------
# Attacks are per thread: what will the other side run against THIS claim.
# Exposure is per FILE: what on one thread damages another. D7's counterexample
# is the second -- *the client\'s own recovery suit undermines his defence in
# the cheque matter, and no single thread reveals it* -- and no amount of care
# inside one thread finds it, because the exposure exists only in the pair.

ATTACK_SCHEMA: dict = {
    "x-nm-read": "attacks",
    "type": "object",
    "properties": {
        "attacks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ground": {
                        "type": "string",
                        "description": "The ground they will run it on.",
                    },
                    "their_case": {
                        "type": "string",
                        "description": "Their argument AT ITS STRONGEST, put "
                                       "as they would put it.",
                    },
                    "our_answer": {
                        "type": "string",
                        "description": "Our answer. Empty ONLY if there is "
                                       "genuinely none.",
                    },
                    "no_answer": {"type": "boolean"},
                    "no_answer_because": {
                        "type": "string",
                        "description": "What we DO about it where there is no "
                                       "good answer. Required when "
                                       "`no_answer` is true.",
                    },
                },
                "required": ["ground", "their_case", "our_answer",
                             "no_answer", "no_answer_because"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["attacks"],
    "additionalProperties": False,
}

ATTACK_SYSTEM = (
    "You put the OTHER SIDE\'s case against an Indian advocate\'s client, at "
    "its strongest.\n\n"
    "Not a list of weaknesses and not a hedge: the argument as opposing "
    "counsel would actually make it, on the ground they would actually take. "
    "A softened version of their case is worth nothing to prepare "
    "against.\n\n"
    "For each, give our answer. Where there is NO good answer, say so — "
    "`no_answer` true — and then say what we DO about it: concede it early, "
    "settle, plead in the alternative, prepare the client. An unanswerable "
    "attack reported and left there is half a finding."
)

EXPOSURE_SCHEMA: dict = {
    "x-nm-read": "exposure",
    "type": "object",
    "properties": {
        "exposures": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from_thread": {"type": "string"},
                    "to_thread": {"type": "string"},
                    "what": {
                        "type": "string",
                        "description": "What on the first thread damages the "
                                       "second.",
                    },
                    "consequence": {
                        "type": "string",
                        "description": "What follows for the second thread.",
                    },
                },
                "required": ["from_thread", "to_thread", "what", "consequence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["exposures"],
    "additionalProperties": False,
}

EXPOSURE_SYSTEM = (
    "You read an Indian advocate\'s FILE — several disputes for one client — "
    "and find where a position on ONE dispute damages another.\n\n"
    "The example that matters: the client\'s own recovery suit asserts he was "
    "owed money, and his defence in the cheque matter says the debt was never "
    "owed. Neither dispute reveals it alone.\n\n"
    "Name the threads by their ids. An empty list is a real answer and the "
    "usual one — do not manufacture a connection between unrelated disputes."
)


@dataclass(frozen=True)
class ReadAttacks:
    """THREE STATES. No attacks read is not "they have nothing"."""

    attacks: tuple["Attack", ...] = ()
    examined: bool = False
    why_not: str = "nothing has put the other side\'s case"
    refused: tuple[str, ...] = ()

    @property
    def state(self) -> str:
        if not self.examined:
            return "not_assessed"
        return "put" if self.attacks else "none_put"


UNREAD_ATTACKS = ReadAttacks()


def attacks_not_assessed(why: str) -> ReadAttacks:
    return ReadAttacks(examined=False, why_not=why)


@implements("D7")
def build_attack_prompt(account: str, acting_for: str):
    from nm.ports.model import Prompt

    return Prompt(system=ATTACK_SYSTEM,
                  user=f"WE ACT FOR: {acting_for}\n\nTHE FILE:\n{account}")


@implements("D7")
def build_exposure_prompt(threads: tuple[tuple[str, str], ...]):
    from nm.ports.model import Prompt

    listed = "\n".join(f"  {tid}\t{label}" for tid, label in threads)
    return Prompt(system=EXPOSURE_SYSTEM,
                  user=f"THE DISPUTES ON THIS FILE:\n{listed}")


@implements("D7")
def read_attacks(said: dict, thread: ThreadId) -> ReadAttacks:
    """Build attacks, refusing each that stops at the problem.

    `Attack` refuses at construction an attack with no answer that does not
    say it has none, and one marked unanswerable that stops there. Both are
    caught here as REFUSALS rather than crashes, because the second is the
    ordinary failure of a model asked a hard question -- and telling the
    advocate "I put this attack and could not resolve it" is worth more than
    dropping it.
    """
    rows = said.get("attacks")
    if not isinstance(rows, list):
        return attacks_not_assessed("the attack read returned no list")

    built: list[Attack] = []
    refused: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            refused.append("an attack that was not an object")
            continue
        try:
            built.append(Attack(
                # THE THREAD COMES FROM THE CALLER, never from the model.
                # It is not a question about the account: the turn knows which
                # thread it is deriving, and letting the read name one is a
                # way for an attack to land on a thread it was not made about.
                thread=thread,
                ground=str(row.get("ground") or "").strip(),
                their_case=str(row.get("their_case") or "").strip(),
                our_answer=str(row.get("our_answer") or ""),
                no_answer=bool(row.get("no_answer")),
                no_answer_because=str(row.get("no_answer_because") or ""),
            ))
        except ValueError as exc:
            refused.append(str(exc))

    return ReadAttacks(attacks=tuple(built), examined=True,
                       refused=tuple(refused),
                       why_not=("the other side has no case worth putting on "
                                "what is recorded"
                                if not built and not refused else ""))


@implements("D7")
def read_exposures(said: dict, threads: tuple[ThreadId, ...],
                   ) -> tuple[Exposure, ...]:
    """Exposures between threads THE FILE ACTUALLY HOLDS.

    A pair naming a thread that does not exist would make the file-level pass
    look as though it had found something, which is the one thing E-082's
    "emitted twice" half and this share: noise the advocate learns to skip.
    """
    rows = said.get("exposures")
    if not isinstance(rows, list):
        return ()
    known = set(threads)
    out: list[Exposure] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        frm, to = str(row.get("from_thread") or ""), str(row.get("to_thread") or "")
        if frm not in known or to not in known or frm == to:
            continue
        try:
            out.append(Exposure(
                from_thread=ThreadId(frm), to_thread=ThreadId(to),
                what=str(row.get("what") or "").strip(),
                consequence=str(row.get("consequence") or "").strip()))
        except ValueError:
            # The type refuses a blank `what` or `consequence`. An exposure
            # that names no consequence is a worry, not a finding.
            continue
    return tuple(out)


# =========================== READING A SALVAGE =============================
#
# WHEN IT RUNS, AND WHY NOT ALWAYS
# ----------------------------------
# D8 says state the variation BEFORE reporting that the claim fails. So it runs
# exactly where the turn is about to report a failure -- and nowhere else. Run
# on every turn it would be seven paragraphs of hypothetical restructuring
# attached to a claim that is fine, which is the survey this product rejects.
#
# THE BOUND IS THE HARDER HALF
# ------------------------------
# *Never manufacture a route. A system rewarded for always finding a way out
# will invent one, and a hopeless alternative cause costs the client money and
# the advocate credibility.*
#
# `route=None` is therefore a first-class outcome and the COMMON one. What the
# type refuses is the opposite: a route with no strength and no citation, which
# is how a manufactured one arrives -- "consider a different forum" with no
# forum named. And the citations offered here are checked against what was
# ACTUALLY RETRIEVED on this turn, because a route grounded in a plausible
# recollection that such a claim exists is exactly what D8 forbids.

SALVAGE_SCHEMA: dict = {
    "x-nm-read": "salvage",
    "type": "object",
    "properties": {
        "failure_scope": {"type": "string", "enum": ["case", "framing"]},
        "varied": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "coordinate": {
                        "type": "string",
                        "enum": [c.value for c in Coordinate],
                    },
                    "varied_result": {
                        "type": "string",
                        "description": "What CHANGES if this dimension moves. "
                                       "Required even where no route follows.",
                    },
                    "route": {
                        "type": "string",
                        "description": "The route, if there is one. EMPTY is "
                                       "the ordinary answer — do not invent "
                                       "one.",
                    },
                    "strength": {
                        "type": "string",
                        "enum": [s.value for s in Strength],
                    },
                    "citations": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Refs from the RETRIEVED list you were "
                                       "given. A route citing anything else "
                                       "will be discarded.",
                    },
                },
                "required": ["coordinate", "varied_result", "route",
                             "strength", "citations"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["failure_scope", "varied"],
    "additionalProperties": False,
}

SALVAGE_SYSTEM = (
    "An Indian advocate\'s claim is about to be reported as failing. Before "
    "that is said, treat the claim as a set of COORDINATES — party, cause, "
    "relief, forum, timing, procedure, burden — and ask which one can "
    "move.\n\n"
    "Almost every \"you lose\" is the failure of ONE of them, not of the "
    "case. For each coordinate say what CHANGES if it moves, whether or not a "
    "route follows.\n\n"
    "DO NOT MANUFACTURE A ROUTE. An empty `route` is the ordinary answer and a "
    "hopeless alternative cause costs the client money and the advocate "
    "credibility. Where you do give one, cite it from the RETRIEVED list you "
    "were given and mark how strongly you would run it — never present a route "
    "you would not run as though you would.\n\n"
    "`failure_scope` is `framing` where a different framing on these same "
    "facts is available, and `case` only where none is."
)


@dataclass(frozen=True)
class ReadSalvage:
    """THREE STATES, and `not_assessed` is what a weak case gets when nobody
    varied anything — which must not read as `nothing could be done`."""

    considered: tuple["Salvage", ...] = ()
    failure_scope: FailureScope = FailureScope.NOT_ASSESSED
    examined: bool = False
    why_not: str = "nothing has varied the coordinates of this claim"
    refused: tuple[str, ...] = ()

    @property
    def state(self) -> str:
        if not self.examined:
            return "not_assessed"
        return "varied" if self.considered else "none_varied"


UNREAD_SALVAGE = ReadSalvage()


def salvage_not_assessed(why: str) -> ReadSalvage:
    return ReadSalvage(examined=False, why_not=why)


@implements("D8")
def build_salvage_prompt(account: str, why_failing: str,
                         retrieved: tuple[str, ...]):
    from nm.ports.model import Prompt

    listed = "\n".join(f"  {r}" for r in retrieved) or "  (nothing retrieved)"
    return Prompt(
        system=SALVAGE_SYSTEM,
        user=(f"WHY THE CLAIM IS FAILING:\n{why_failing}\n\n"
              f"RETRIEVED ON THIS TURN — the only things a route may cite:\n"
              f"{listed}\n\nTHE FILE:\n{account}"))


@implements("D8")
def read_salvage(said: dict, retrieved: tuple[str, ...]) -> ReadSalvage:
    """Build the variations, discarding routes that rest on nothing retrieved.

    A CITATION THE TURN DID NOT RETRIEVE IS DROPPED, and dropping it usually
    takes the route with it -- `Salvage` refuses a route with no findings. That
    is the intended outcome: a route grounded in a recollection that such a
    claim exists is a category-level suggestion, and D8 names that exactly.
    """
    rows = said.get("varied")
    if not isinstance(rows, list):
        return salvage_not_assessed("the salvage read returned no list")

    held = set(retrieved)
    built: list[Salvage] = []
    refused: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            coordinate = Coordinate(str(row.get("coordinate")))
        except ValueError:
            refused.append(f"a coordinate outside the seven: "
                           f"{row.get('coordinate')!r}")
            continue

        cited = tuple(c for c in _strings(row.get("citations")) if c in held)
        route = str(row.get("route") or "").strip()
        if route and not cited:
            # THE ROUTE GOES, THE VARIATION STAYS. What changes when the
            # coordinate moves is still worth saying; what is not worth saying
            # is a way out resting on nothing.
            refused.append(
                f"{coordinate.value}: a route citing nothing retrieved on this "
                f"turn — {route[:60]!r}")
            route = ""

        try:
            strength = Strength(str(row.get("strength")))
        except ValueError:
            strength = Strength.NOT_ASSESSED

        try:
            built.append(Salvage(
                coordinate=coordinate,
                varied_result=str(row.get("varied_result") or "").strip(),
                route=route,
                strength=strength if route else Strength.NOT_ASSESSED,
                findings=cited if route else (),
            ))
        except ValueError as exc:
            refused.append(str(exc))

    try:
        scope = FailureScope(str(said.get("failure_scope")))
    except ValueError:
        scope = FailureScope.NOT_ASSESSED

    return ReadSalvage(considered=tuple(built), failure_scope=scope,
                       examined=True, refused=tuple(refused), why_not="")


def _strings(value) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(v).strip() for v in value if str(v).strip())
