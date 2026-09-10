"""The HTTP edge.

THE BYTE BOUNDARY IS ENFORCED HERE, on the bytes leaving the process -- not in
the module that composes the answer. That placement is the whole point: the
previous build's duty screen was correct inside the core and ran after the
advice had already been shown, and every defect the first external review found
lived in exactly this gap.

So `_release` is the only function in the codebase permitted to hand an answer
to the transport, and it refuses anything the core did not fully assemble,
invariant-check, and commit.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from nm.core.turn import TurnEngine, TurnInput, TurnRefused
from nm.domain import attempts, brief
from nm.domain import summary as matter_memory
from nm.domain.advocate import utcnow
from nm.domain.answer import Answer
from nm.domain.clock import FORUM
from nm.domain.clock import today as forum_today
from nm.domain.identity import source_fingerprint
from nm.domain.traceability import implements
from nm.edge.projections import board_projection, matter_list_projection
from nm.ports.store import StaleWrite

ROOT = Path(__file__).resolve().parents[2]

app = FastAPI(title="Nyaymalaw", version="0.1.0")
_application = None


def application():
    """The wired application, INJECTED by the composition root.

    The edge deliberately does not build it. Which adapter is live is the
    composition root's business, and letting the serving path choose would put
    provider knowledge exactly where it must never be.
    """
    if _application is None:
        raise RuntimeError(
            "no application wired. The composition root must call "
            "set_application() before serving -- see nm.bootstrap.composition.")
    return _application


def set_application(app_) -> None:
    global _application
    _application = app_


# ------------------------------------------------------------- the boundary ---


class _Released(BaseModel):
    turn_id: str
    matter_id: str | None
    route: str
    mode: str
    mode_statement: str
    blocked: bool
    blocked_reason: str | None
    elements: list[dict]
    metrics: dict
    replayed: bool
    # BK-36. WHAT HAPPENED TO THE BRIEF, in the caller's own terms.
    #
    # `replayed` already said "this turn id has been applied before", and the
    # browser had no way to ask the question it actually needs answered after
    # a lost response: WAS MY BRIEF SAVED? Those are the same fact from two
    # ends, and the browser was left inferring it from an HTTP status it never
    # received.
    #
    #   committed   the brief is on the file, derived from and served
    #   replayed    it was already on the file; this is that same turn again
    #
    # There is no third value HERE, and that is deliberate: a turn that was
    # not committed does not reach this function at all -- it raises, and the
    # error carries `turn_id` so the retry can name it.
    committed: str
    matter_version: int | None


def _release(output) -> _Released:
    """THE BYTE BOUNDARY. Nothing reaches the transport except through here.

    By the time this runs, the core has already asserted its invariants and
    committed. This function re-checks the two properties that would be
    catastrophic to get wrong at the edge, because being right in the core is
    not the same as being right on the wire.
    """
    answer: Answer = output.answer

    if output.metrics.gating_violations:
        # Belt and braces: the core raises before reaching here, so arriving in
        # this branch means a caller bypassed the engine.
        raise HTTPException(status_code=409, detail="output gated by a grounding violation")

    for element in answer.elements:
        if element.signal.is_loud and element.collapsible:
            raise HTTPException(
                status_code=500,
                detail=f"refusing to emit: {element.signal.value} marked collapsible")

    return _Released(
        turn_id=output.turn_id,
        matter_id=output.matter.id if output.matter else None,
        route=answer.route.value,
        mode=answer.mode.value,
        mode_statement=answer.mode_statement,
        blocked=answer.blocked,
        blocked_reason=answer.blocked_reason,
        elements=[
            {
                "kind": e.kind.value,
                "text": e.text,
                "thread": e.thread,
                "by_when": e.by_when.isoformat() if e.by_when else None,
                "no_deadline_reason": e.no_deadline_reason,
                "signal": e.signal.value,
                "collapsible": e.collapsible,
                "disclosure": e.disclosure,
                "refs": list(e.refs),
                # BK-37. WHICH QUESTION THIS ELEMENT ANSWERS.
                #
                # Computed HERE and not in the browser, because a renderer
                # that decided sections for itself would be a second opinion
                # about what an element IS -- two correct components and the
                # disagreement visible only on a screen nobody diffed. The
                # assignment is pure and has one owner in
                # `nm/domain/brief.py`; the client groups and does not judge.
                "section": brief.section_of(e).value,
            }
            for e in answer.elements
        ],
        metrics=output.metrics.as_dict(),
        replayed=output.replayed,
        committed="replayed" if output.replayed else "committed",
        matter_version=output.matter.version if output.matter else None,
    )


# ------------------------------------------------------------------ routes ---


def _not_blank(value: str) -> str:
    """`min_length` counts CHARACTERS, and "   " is three of them.

    A whitespace advocate id passed the wire and opened a matter, which is
    an anonymous session on an unattributable file. `Matter.create` now
    refuses it too -- this is here so the caller gets a 422 naming the
    field rather than a 500 from the core.
    """
    if not (value or "").strip():
        raise ValueError("must not be blank")
    return value.strip()


NonBlank = Annotated[str, AfterValidator(_not_blank)]

#: A1 — WHO IS ACTING, DERIVED FROM A SESSION THE SERVER ISSUED.
#:
#: This was `Annotated[str, Query(...)]`: the caller named whichever advocate
#: they liked and the product believed them. It was the only thing between one
#: advocate's client file and another's (B-082), and it satisfied E-010
#: because `anonymous` in the code meant the empty string while `anonymous` in
#: the spec meant unauthenticated.
#:
#: THE IDENTITY IS NO LONGER AN INPUT. It is read from a session cookie the
#: server minted, bound to the device that authenticated, and expiring.


#: How a device is recognised across requests. The cookie alone would follow a
#: copied jar; the user agent alone is shared by every Chrome on earth. Bound
#: together, a session presented from another browser -- the borrowed laptop
#: A1's first NEVER is about -- does not resolve.
def _device(device_cookie: str | None, user_agent: str | None) -> str:
    import hashlib
    return hashlib.sha256(
        f"{device_cookie or ''}|{user_agent or ''}".encode("utf8")).hexdigest()


def signed_in(nm_session: str | None = Cookie(default=None),
              nm_device: str | None = Cookie(default=None),
              user_agent: str | None = Header(default=None)) -> str:
    """The advocate id, or 401. NEVER a default and never a fallback.

    ONE FAILURE, in the same words, for no cookie / unknown token / expired /
    ended / wrong device. A1's second NEVER is that a failed or expired
    credential discloses nothing about what exists, and a message that
    distinguishes "expired" from "no such session" discloses that a session
    existed. The reason is written to the directory's audit instead.
    """
    session = application().directory.session(
        nm_session or "", _device(nm_device, user_agent), utcnow())
    if session is None:
        raise HTTPException(status_code=401, detail="not signed in")
    return session.advocate_id


Advocate = Annotated[str, Depends(signed_in)]


class TurnRequest(BaseModel):
    # NO `advocate_id`. It came from the body, which means the caller asserted
    # who they were and the product recorded that assertion on the file. It now
    # comes from the session, and there is no field here to override it with.
    message: NonBlank = Field(min_length=1)
    matter_id: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None
    today: date | None = None
    jurisdiction: str = FORUM
    # BK-36. THE VERSION THE CALLER BELIEVES IT IS WRITING ON TOP OF.
    #
    # The per-matter lock and the exact version check already stop two writers
    # silently winning INSIDE the store. What was missing is the browser's
    # half: a second tab that loaded the matter, sat for ten minutes and then
    # sent a brief was writing on top of a file it had never seen, and the
    # first it heard of it was a turn derived from facts it did not know
    # about.
    #
    # `None` MEANS THE CALLER DID NOT CHECK, and it is accepted rather than
    # refused: the API is used by tools and tests that legitimately do not
    # hold a version. What it must never do is read as "I checked and it
    # matched", so the two are different values and the mismatch is a 409 with
    # both numbers in it.
    expected_version: int | None = None

    parties: dict[str, str] = Field(default_factory=dict)
    """BK-34. Who is involved, given at intake: name -> side."""

    release: dict[str, str] = Field(default_factory=dict)
    """BK-34. Screens this advocate releases with this brief: kind -> why.

    The signed-in advocate is the named releaser -- the identity comes from
    the session, never from the body, so a caller cannot release a screen in
    somebody else's name.
    """


#: THE CODE THIS PROCESS ACTUALLY LOADED, captured ONCE at import.
#:
#: Computed here and never per-request, and that is the whole mechanism. A
#: fingerprint read from disk when the request arrives describes the working
#: tree, which a stale server would match perfectly while serving code from
#: yesterday. Frozen at import, it describes what is RUNNING.
#:
#: Measured on 31 August 2026: a scenario run made live model calls against a
#: server started the previous evening, found none of the slice it was meant to
#: prove, and exited 0. Three of the five scenarios also had no scripted turns.
#: The run cost money, measured nothing, and reported success -- defect shape
#: S1, on the tool whose whole job is to catch S1 in the product.
#:
#: The mechanism is not new. `nm/domain/identity.py` already existed (in
#: `tools/`) so a mutation record could not certify code it never saw, and
#: `nm/knowledge/artefact.py` makes the same argument about the dense index:
#: the only reason that index was KNOWABLY unusable is that it shipped an
#: identity. A running process is an artefact and needs one too.
try:
    SERVING = source_fingerprint()
except Exception as exc:  # noqa: BLE001 -- NOT ASSESSED, said as a value
    # Never a digest that happens to differ, and never one that happens to
    # match: a value that cannot be computed says so in words no comparison
    # will read as agreement.
    SERVING = f"unknown: {type(exc).__name__}"


def serving_state() -> dict:
    """WHAT THIS PROCESS IS RUNNING, AND WHETHER THE TREE HAS MOVED PAST IT.

    `SERVING` is frozen at import and describes what is RUNNING. Recomputing
    the fingerprint now describes what is ON DISK. The comparison is the whole
    point, and the server is the only party that has both numbers -- the
    browser cannot see the tree and the tree cannot see the process.

    WHY THIS IS HERE RATHER THAN IN A TOOL. It happened three times on
    6 September 2026, in one session, and each time it looked like a product
    defect and cost a round trip:

        the browser held a cached app.js and Register did nothing;
        :8071 had no /api/register at all, three commits behind;
        :8078 served the 12-character password rule after it became 8.

    The last one was reported with a screenshot of the OLD refusal message,
    against a fix that was already committed and green. The code was right,
    the running thing was old, and nothing anywhere said so. A tool would
    have caught it and nobody would have run it -- R-6's failure, which this
    plan already names.

    THREE STATES, and the third is why `stale` is not a bool. A fingerprint
    that could not be computed must not read as "nothing has changed": that is
    S1 on the check built to catch S1, and it has happened here before.
    """
    if SERVING.startswith("unknown:"):
        return {"serving": SERVING, "tree": "not assessed",
                "code_state": "not_assessed",
                "why": "the fingerprint of the running code could not be "
                       "computed, so nothing can be said about whether the "
                       "tree has moved past it"}
    try:
        tree = source_fingerprint()
    except Exception as exc:  # noqa: BLE001 -- NOT ASSESSED, said as a value
        return {"serving": SERVING, "tree": f"unknown: {type(exc).__name__}",
                "code_state": "not_assessed",
                "why": "the working tree could not be fingerprinted"}

    if tree == SERVING:
        return {"serving": SERVING, "tree": tree, "code_state": "current"}
    return {
        "serving": SERVING, "tree": tree, "code_state": "stale",
        "why": f"this process loaded {SERVING} and the working tree is now "
               f"{tree}. Everything it serves -- pages, refusals, gate "
               f"decisions -- is the older code. Restart it.",
    }


@app.get("/api/health")
def health() -> dict:
    return {**application().health(), **serving_state()}


@app.get("/api/matters/{matter_id}/transcript")
def transcript(matter_id: str, advocate_id: Advocate) -> dict:
    """THE CONVERSATION, AS IT WAS SERVED. For review, later.

    Every turn on this matter in full — what the advocate wrote, what came
    back, which gates fired and what was violated. Nothing else keeps it: the
    matter holds facts, the metrics hold counts and no client words, and the
    answer was held by neither.

    THE SAME 404 AS EVERY OTHER MATTER LOOKUP, and for the same reason: a
    failed lookup must disclose nothing about what exists. A transcript is the
    most privileged thing on the file, so the ownership check comes before the
    read rather than after it.
    """
    m = application().store.load(matter_id)
    if m is None or m.advocate_id != advocate_id:
        raise HTTPException(status_code=404, detail="no such matter")

    store = application().store
    turns = store.transcripts_for(matter_id)
    unreadable = [t for t in turns if t.get("unreadable")]

    # A FACT ABOUT THE STORE, NOT ABOUT THIS CONVERSATION.
    #
    # A transcript written before the filename carried its matter can only be
    # attributed by decrypting it, so one that will not decrypt belongs to no
    # known matter. It used to be appended to whichever matter was being
    # asked about, which marked every matter `incomplete` over one corrupt
    # file and put a stranger's turn id on each of them. It is disclosed here,
    # separately, because dropping it silently is the other half of that
    # defect.
    lost = (store.unattributable()
            if hasattr(store, "unattributable") else ())
    return {
        # NOT "ok" when a turn could not be decrypted. A review that renders
        # nine of ten turns and says "ok" is reviewing a different
        # conversation from the one that ran.
        "state": "ok" if not unreadable else "incomplete",
        "matter_id": matter_id,
        "title": m.title,
        "turns": [t for t in turns if not t.get("unreadable")],
        "turn_count": len(turns),
        "unreadable": [t["turn_id"] for t in unreadable],
        "unreadable_reason": (
            f"{len(unreadable)} turn(s) on this matter could not be read back "
            f"and are missing from what follows."
            if unreadable else None),
        "unattributable_count": len(lost),
        "unattributable_reason": (
            f"{len(lost)} transcript(s) in the store could not be read back at "
            f"all, so which matter they belong to is unknown. They may or may "
            f"not be from this one."
            if lost else None),
    }


def _register_of(matter) -> tuple:
    """Every deadline this matter's threads hold. ONE OWNER.

    `None` REMAINS REACHABLE AND MEANS WHAT IT SAYS. A matter whose threads
    carry no `deadlines` attribute at all -- decoded from a store that
    predates the field -- is not a matter with no deadlines, and returning
    `()` for it would be exactly the collapse the projection refuses.
    """
    from datetime import date as _date

    from nm.core.deadlines import Deadline, DeadlineKind

    rows: list = []
    saw_register = False
    for thread in getattr(matter, "threads", ()):
        held = getattr(thread, "deadlines", None)
        if held is None:
            continue
        saw_register = True
        for row in held:
            # REHYDRATED, BECAUSE `Thread.deadlines` IS `tuple[object, ...]`.
            #
            # The field is untyped for the cycle reason every persisted
            # derivation here carries -- `nm.core.deadlines` imports the
            # matter module -- so the store decoder cannot rebuild the type
            # and hands back dicts. `_thread_row` reads `d.thread` and
            # `d.status(today)`, so passing the raw rows raised
            # `AttributeError: 'dict' object has no attribute 'thread'` on
            # the first board that had ever been advised on.
            #
            # A DICT THAT CANNOT BE REBUILT IS SKIPPED AND THE REGISTER
            # STILL COUNTS AS PRESENT. Dropping the whole register for one
            # unreadable row would report `not_assessed` -- nobody looked --
            # for a file where somebody did.
            if not isinstance(row, dict):
                rows.append(row)
                continue
            try:
                on = row.get("on")
                rows.append(Deadline(
                    thread=str(row["thread"]),
                    kind=DeadlineKind(row["kind"]),
                    source=str(row["source"]), action=str(row["action"]),
                    owner=str(row["owner"]),
                    consequence=str(row["consequence"]),
                    on=_date.fromisoformat(on) if isinstance(on, str) else on))
            except (KeyError, ValueError, TypeError):
                continue
    return tuple(rows) if saw_register else None


def _registers(held) -> dict:
    return {m.id: _register_of(m) for m in held}


@app.get("/api/matters")
def matters(advocate_id: Advocate) -> dict:
    """THE MATTER LIST. One row per matter, nearest deadline first.

    Bounded by MATTER count -- never by threads, turns or facts.
    """
    held = application().store.list_for(advocate_id)
    # THE REGISTER IS ON THE THREADS AND WAS NEVER READ. BK-33.
    #
    # Both projections take a register and both were called without one, so
    # every row on every board reported `not_assessed` -- "nobody computed a
    # register" -- while `Thread.deadlines` held the windows the last turn
    # derived. The projection was right to refuse a default; the CALLER was
    # supplying nothing.
    #
    # `not assessed`, `none on this matter`, `upcoming` and `passed` are four
    # different facts and the advocate could only ever see the first.
    return matter_list_projection(held, registers=_registers(held))


@app.get("/api/matters/{matter_id}")
@implements("A1")
def matter(matter_id: str, advocate_id: Advocate) -> dict:
    """THE THREAD BOARD. One row per thread, bounded by THREAD count."""
    m = application().store.load(matter_id)
    if m is None or m.advocate_id != advocate_id:
        # The same response whether it does not exist or belongs to someone
        # else: a failed lookup must disclose nothing about what exists.
        raise HTTPException(status_code=404, detail="no such matter")
    # THE PERSISTED REGISTER, not `None`. BK-33.
    #
    # This passed `None` under a comment saying the view computes no register
    # -- true, and it does not have to: the register is derived on a turn and
    # WRITTEN TO THE THREAD, so the board reads what is on the file rather
    # than recomputing it. Passing `None` said "nobody has assessed the
    # deadlines on this matter", which was false on every matter that had
    # ever been advised on.
    return board_projection(m, _register_of(m))


@app.get("/api/matters/{matter_id}/summary")
def matter_summary(matter_id: str, advocate_id: Advocate) -> dict:
    """THE FILE. What is established, what was asked, what is still open.

    A projection over the matter, exactly like the two boards, holding
    nothing the matter does not. It is served because a memory only a
    prompt can read is a memory nobody can audit -- and the advocate finds
    out it was wrong by being advised from it.

    An unreadable matter is an EXPLICIT failure, never an empty summary:
    empty would tell the advocate the file holds nothing, and the product
    would then re-ask everything it had ever been told.
    """
    try:
        m = application().store.load(matter_id)
    except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
        return matter_memory.unbuildable(f"the matter could not be read: {exc}")
    if m is None or m.advocate_id != advocate_id:
        raise HTTPException(status_code=404, detail="no such matter")
    return matter_memory.build(m).as_dict()


@app.post("/api/turn")
def turn(req: TurnRequest, advocate_id: Advocate) -> _Released:
    engine: TurnEngine = application().engine
    payload = TurnInput(
        advocate_id=advocate_id,
        message=req.message,
        matter_id=req.matter_id,
        # The advocate naming a thread OUTRANKS every heuristic. The only
        # source better than a number of record is the person holding the file.
        thread_id=req.thread_id,
        # THE FORUM'S DATE, not the server's (BK-14). `web/app.js` sends
        # no `today`, so this default IS the production path -- and
        # `date.today()` meant "the date where this process happens to
        # run". A server keeping UTC is a day behind India from 18:30
        # UTC, so every limitation period computed in that window was a
        # day short.
        today=req.today or forum_today(),
        jurisdiction=req.jurisdiction,
        parties=dict(req.parties or {}),
        release=dict(req.release or {}),
        **({"turn_id": req.turn_id} if req.turn_id else {}),
    )
    # THE VERSION IS CHECKED BEFORE THE MODEL RUNS, not after. A stale write
    # detected at commit has already spent the calls; detected here it costs
    # one read, and the advocate gets the same answer sooner.
    if req.expected_version is not None and req.matter_id:
        try:
            held = application().store.load(req.matter_id)
        except Exception:  # noqa: BLE001 -- an unreadable matter is the store's
            held = None    # own error, raised where it is understood
        if held is not None and held.version != req.expected_version:
            raise HTTPException(status_code=409, detail={
                "why": (f"this matter moved while you were writing: you were "
                        f"working on version {req.expected_version} and it is "
                        f"now at {held.version}"),
                "expected_version": req.expected_version,
                "matter_version": held.version,
                "turn_id": req.turn_id,
                "committed": "not_committed",
            })

    try:
        output = engine.run(payload)
    except TurnRefused as exc:
        # 422 with the REASON, not just the refusal. The disclosures assert no
        # law -- they say what could not be established -- so passing them
        # through the byte boundary is safe, and withholding them as well would
        # leave the advocate with a dead end.
        raise HTTPException(status_code=422, detail={
            "withheld_by": list(getattr(exc, "gates", ())),
            "why": getattr(exc, "message", str(exc)),
            "not_established": list(getattr(exc, "disclosures", ())),
            # A WITHHELD TURN IS STILL A TURN THAT RAN. The id is what makes
            # a retry the SAME turn rather than a second one.
            "turn_id": req.turn_id,
            "committed": "not_committed",
        }) from exc
    except StaleWrite as exc:
        raise HTTPException(status_code=409, detail={
            "why": str(exc),
            "turn_id": req.turn_id,
            "committed": "not_committed",
        }) from exc
    return _release(output)


@app.get("/api/search")
@implements("A4")
def search(q: str, advocate_id: Advocate, court: str | None = None,
           from_year: int | None = None, to_year: int | None = None,
           limit: int = 20) -> dict:
    """A4 — SEARCH THE CORPUS. Ranked paragraphs, never an identified Act.

    THE RESPONSE ALWAYS CARRIES `coverage` AND `index`, including at zero.
    A bare `{"hits": []}` is the defect this whole feature is shaped around:
    the advocate reads it as "the law is not in the corpus" when it may mean
    the index is not built, the filter excluded everything, or they searched
    party names in a store that holds paragraphs (B-163).

    IT TAKES AN ADVOCATE and returns nothing matter-specific. The corpus is
    not privileged — every advocate may read the same law — but an
    unattributable search is still refused, because A1 requires the file to
    know who is acting and a search is how a matter starts.
    """
    result = application().search.search(
        q, court=court, from_year=from_year, to_year=to_year, limit=limit)
    return {
        "query": result.query,
        "index": result.index,
        "coverage": result.coverage.value,
        "why": result.why,
        "filters": result.filters,
        "hit_count": result.hit_count,
        "identity": None if result.identity is None else {
            "built_at": result.identity.built_at,
            "source": result.identity.source,
            "corpus_version": result.identity.corpus_version,
            "held": result.identity.held,
            "of_source": result.identity.of_source,
            # THE SCOPE, ON EVERY RESULT. An advocate with a Kerala question
            # reads an empty result as an answer about Kerala law unless the
            # answer says what law was searched.
            "scope": result.identity.scope,
            # `None` when unknown, never 0.0 -- a ratio of zero says the index
            # is empty, which is a different claim from not knowing.
            "fraction_of_source": result.identity.fraction_of_source,
        },
        "hits": [{
            "case_id": h.case_id, "case_name": h.case_name, "court": h.court,
            "year": h.year, "para_type": h.para_type, "snippet": h.snippet,
            "confidence": round(h.confidence, 3),
            # ALWAYS ON THE WIRE. The client renders it, and a hit that
            # reached the browser without it could be styled like an exact
            # lookup by whoever writes the next template.
            "origin": h.origin.value,
        } for h in result.hits],
    }


class Credentials(BaseModel):
    advocate_id: NonBlank = Field(min_length=1)
    password: str = Field(min_length=1)


class Registration(BaseModel):
    """An invited advocate choosing the credential for their account. A1.

    THE INVITATION OWNS THE IDENTITY. Name, canonical email, enrolment,
    practice and workspace are recorded once by the operator. Asking the
    advocate to retype them made an innocent difference indistinguishable from
    a forged token and then discarded the retyped values anyway.

    ENROLMENT IS INVITATION-GATED. BK-31, decided 9 September 2026.

    Two dated decisions contradicted each other. Self-service was permitted on
    6 September; a CONTROLLED PRIVATE ROSTER was recorded on 8 September, and
    the later one governs. What settled it was not the dates but a dependency:
    `nm/core/turn.py` relaxes scope and capacity release to ONE PERSON
    *because* "the deployment is a controlled roster of practising advocates
    and the advocate IS the firm". With open self-service that relaxation is
    unsound -- a stranger enrols and then releases their own professional
    screens. A product that advises on law cannot let the front door decide
    that.

    So the form survives behind a single-use, expiring invitation. The
    invitation fixes the complete server-owned roster identity; the body
    cannot redirect it to another advocate or firm. The invited advocate
    chooses their own password rather than receiving one from an operator.
    """

    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1)
    password_again: str = Field(min_length=1)


#: THE ONLY THING A FAILED SIGN-IN EVER SAYS.
#:
#: WHY A SIGN-IN FAILED, in the advocate's words. Three states.
#:
#: THIS OVERRIDES A1's SINGLE MESSAGE, on the advocate's instruction and
#: with the cost recorded. A1 collapsed every failure into one sentence so
#: a stranger could not use the form to discover which addresses are
#: enrolled -- the same reasoning as the timing note in `authenticate`,
#: which pays for a password derivation on an unknown advocate so the
#: stopwatch cannot answer either. That trade is now made the other way.
#:
#: WHAT IS BOUGHT is that three different problems stop reading as one.
#: `unreadable` in particular is neither a wrong email nor a wrong
#: password: it is a record encrypted under a key the server no longer
#: has, it happened on 7 September 2026, and the advocate was told to
#: check credentials that were correct.
#:
#: WHAT IS SPENT is that the form now confirms whether an address is
#: enrolled -- and enumeration is cheap in proportion to how fast it can
#: be tried, which is why this belongs WITH the login rate limit that
#: BK-18 still carries as open. The two go together.
#:
#: STILL ONE OWNER PER MESSAGE. Three constants, not three strings written
#: at call sites: the original comment's point was that copies drift, and
#: that is as true of three messages as of one.
_REFUSED = {
    "unknown": ("no advocate is enrolled with that email address. Check the "
                "spelling, or register."),
    "wrong_password": "that password is not right for this email address.",
    "unreadable": ("this account exists and could not be opened. It was "
                   "sealed with a different NM_MATTER_KEY than the server is "
                   "running with -- retyping the password will not fix it."),
}
_REFUSED_DEFAULT = "those credentials were not accepted"


@app.post("/api/register")
@implements("A1")
def register(body: Registration, request: Request,
             x_enrolment_invitation: str | None = Header(default=None)) -> dict:
    """Enrol an advocate, and DO NOT sign them in.

    Registration and authentication are separate acts. Issuing a session here
    would mean a form post that creates an account also creates a logged-in
    session on whatever machine sent it -- and A1's first NEVER is that a
    session cannot be presented from a machine that never authenticated. They
    register, then they sign in, and the sign-in is where the device binding
    is minted.

    THE PASSWORD MINIMUM IS NOT RESTATED HERE. `advocate.enrol` raises on a
    short one, and it is reached by this route, the enrolment tool, a
    migration and every test fixture. Its own docstring says why: *"a rule
    that lives at one door is a rule with a back one."* This route catches
    that refusal and passes the reason through rather than inventing a second
    threshold that will drift from the first.
    """
    from nm.domain.advocate import enrol, token_fingerprint
    from nm.ports.directory import AlreadyEnrolled, InvitationRefused

    now = utcnow()
    source = request.client.host if request.client else "unknown-source"
    invitation = (x_enrolment_invitation or "").strip()
    rate_key = f"invitation:{token_fingerprint(invitation)}"
    counts = application().directory.failures_since(
        rate_key, source, now - attempts.WINDOW)
    if counts is not None:
        seen = attempts.verdict(counts[0], counts[1], now)
        if not seen.allowed:
            raise HTTPException(status_code=429,
                                detail=seen.said_for("enrolment"))

    if body.password != body.password_again:
        # BEFORE the credential is derived, so a typo costs nothing and the
        # two strings never both reach the hash.
        raise HTTPException(
            status_code=400,
            detail="The two passwords do not match. Nothing was saved.")

    try:
        credential = enrol(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        identity = application().directory.accept_invitation(
            invitation, credential, now)
    except InvitationRefused as exc:
        application().directory.note_failure(rate_key, source, now)
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AlreadyEnrolled as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # RETURNED BECAUSE IT IS WHAT THEY SIGN IN WITH. A registration that
    # succeeds and does not say what to type next has enrolled someone who
    # cannot get in.
    return {"advocate_id": identity.id, "name": identity.name}


@app.post("/api/login")
@implements("A1")
def login(body: Credentials, request: Request, response: Response,
          nm_device: str | None = Cookie(default=None),
          user_agent: str | None = Header(default=None)) -> dict:
    """Authenticate, and issue a session bound to this device.

    THE DEVICE COOKIE IS MINTED HERE when the browser has none. That is what
    makes A1's first NEVER enforceable: a session cannot be presented from a
    machine that never authenticated, because the device half of the binding
    was never set there.
    """
    # ---- THE RATE LIMIT, BEFORE ANYTHING EXPENSIVE (BK-20/BK-18) ----
    #
    # The product had none, and said so in a message the ADVOCATE reads:
    # *this is the only thing standing between one advocate's client file
    # and another's, and the product has no rate limit yet.* Naming which
    # of three things failed at sign-in made that gap worth more, so the
    # two land together.
    #
    # THE SOURCE IS THE CLIENT ADDRESS, not the device cookie. A cookie is
    # attacker-controlled -- dropping it makes every attempt a new device
    # and leaves the per-source counter counting nothing. An address is
    # shared by a chambers, which is why PER_SOURCE is twenty and not five.
    now = utcnow()
    source = (request.client.host if request.client else "unknown-source")
    counts = application().directory.failures_since(
        body.advocate_id, source, now - attempts.WINDOW)

    if counts is None:
        # THE LIMITER COULD NOT RUN. The door opens -- refusing every
        # sign-in would be a self-inflicted outage on a product used under
        # time pressure -- and this is NOT silent: `/api/health` reports
        # rate limiting as NOT RUNNING, which is the third state the
        # operator sees before an incident rather than during one.
        pass
    else:
        seen = attempts.verdict(counts[0], counts[1], now)
        if not seen.allowed:
            # 429, NOT 401. A refused attempt is not a wrong password, and
            # calling it one would tell an advocate to check credentials
            # that may be perfectly correct.
            raise HTTPException(status_code=429, detail=seen.said)

    identity = application().directory.authenticate(
        body.advocate_id, body.password)
    if identity is None:
        # 401 AND NOTHING ELSE. Not 404 for an unknown advocate and 401 for a
        # wrong password -- the status code is a message too.
        # THE FAILURE IS COUNTED (BK-20). Recorded after the attempt so a
        # successful sign-in never adds to the count, and before the
        # response so the next attempt sees it.
        application().directory.note_failure(body.advocate_id, source, now)
        why = application().directory.why_last_sign_in_failed()
        raise HTTPException(
            status_code=401,
            detail=_REFUSED.get(why or "", _REFUSED_DEFAULT))

    import secrets
    device_id = nm_device or secrets.token_urlsafe(16)
    token = application().directory.open_session(
        identity.id, _device(device_id, user_agent), utcnow())

    # `secure` FROM THE CONNECTION, NOT FROM A FLAG (BK-18).
    #
    # The flags below reasoned carefully about `httponly` and `samesite`
    # and did not mention `secure` at all, which reads as overlooked
    # rather than decided -- so a session token for a product holding
    # privileged material travelled in clear over http or a downgrade.
    #
    # THE FIRST FIX DEFAULTED TO BROKEN: `secure=True` with an env-var
    # opt-out. A secure cookie on a plain connection is DROPPED by the
    # browser and never returned, so six served-path tests went 401 and
    # local development would have too. A default that needs a flag to
    # work is one somebody sets permanently, in the deployment where it
    # matters.
    #
    # `X-Forwarded-Proto` IS TRUSTED, AND ONLY UPWARDS. Forging it can
    # only make this MORE restrictive -- a secure cookie on a plain
    # connection is a broken login, not a leak -- and nothing here can be
    # talked OUT of securing a genuinely https request.
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0]
    secure = request.url.scheme == "https" or forwarded.strip() == "https"
    for name, value in (("nm_session", token), ("nm_device", device_id)):
        # httponly: script cannot read it, so an XSS bug is not a stolen
        # session. samesite=lax: a cross-site POST cannot ride the cookie.
        # secure: it does not travel over an unencrypted hop at all.
        response.set_cookie(name, value, httponly=True, samesite="lax",
                            secure=secure,
                            max_age=60 * 60 * 12, path="/")
    return {"advocate": identity.as_dict()}


@app.post("/api/logout")
def logout(response: Response,
           nm_session: str | None = Cookie(default=None)) -> dict:
    """Ends the session server-side, THEN clears the cookie, and SAYS WHICH.

    Clearing the cookie alone would leave a live session behind a token the
    browser merely forgot -- which is not a sign-out, it is a tidier screen.

    AND THE ANSWER USED TO BE `{"signed_out": true}` UNCONDITIONALLY, which
    is the same defect one layer up: `close_session` returned `None` whether
    it had ended a live session, found one already closed, or found nothing
    at all. The browser believed it, and BK-40's measured counterexample is
    an advocate being shown the sign-in screen after a logout the server
    never received.

    `outcome` carries which of the three it was. `signed_out` stays the
    caller's question -- can this token still authenticate -- and the answer
    is no in every branch, because the cookie is cleared and an `unknown`
    token was never usable. What `unknown` does NOT mean is that a session
    was ended, and a caller that needs that distinction now has it.
    """
    outcome = application().directory.close_session(nm_session or "",
                                                    "signed out")
    response.delete_cookie("nm_session", path="/")
    return {"signed_out": True, "outcome": outcome}


@app.get("/api/sessions")
def sessions(advocate_id: Advocate,
             nm_session: str | None = Cookie(default=None)) -> dict:
    """WHERE THIS ADVOCATE IS SIGNED IN. BK-31.

    NO TOKENS AND NO FINGERPRINTS ON THE WIRE. The fingerprint is what the
    server matches a cookie against; handing it to a browser would put the
    one value that identifies a session into a place this product does not
    control. What the advocate needs is when it started, when it expires,
    which device it is, and whether it is this one.
    """
    from nm.domain.advocate import token_fingerprint as _fp

    directory = application().directory
    if not hasattr(directory, "sessions_for"):
        # NOT AN EMPTY LIST. A directory that cannot answer is not a
        # directory with no sessions, and the difference is the whole point
        # of the route.
        raise HTTPException(
            status_code=501,
            detail="this deployment's directory cannot list sessions")

    mine = _fp(nm_session or "")
    rows = []
    for session in directory.sessions_for(advocate_id):
        rows.append({
            "device": session.device[:12],
            "issued_at": session.issued_at.isoformat(),
            "expires_at": session.expires_at.isoformat(),
            "ended_because": session.ended_because,
            "live": session.ended_because is None,
            "this_one": session.token_fingerprint == mine,
        })
    return {"sessions": rows, "count": len(rows)}


@app.post("/api/sessions/revoke")
def revoke_sessions(advocate_id: Advocate,
                    nm_session: str | None = Cookie(default=None)) -> dict:
    """Sign out everywhere else. BK-31.

    THE ONE THIS REQUEST CAME FROM SURVIVES. An advocate securing a device
    they no longer control should not have to sign in again on the one they
    are holding -- and a control that logs you out to protect you is a
    control nobody uses twice.

    THE COUNT IS RETURNED because "signed out everywhere" is unverifiable
    otherwise, and the case this exists for is the case where it matters.
    """
    directory = application().directory
    if not hasattr(directory, "close_all_sessions"):
        raise HTTPException(
            status_code=501,
            detail="this deployment's directory cannot revoke sessions")
    ended = directory.close_all_sessions(
        advocate_id, "revoked by the advocate", except_token=nm_session or "")
    return {"ended": ended}


@app.get("/api/session")
def whoami(advocate_id: Advocate) -> dict:
    """Who is signed in. 401 through the same dependency as everything else."""
    identity = application().directory.identity(advocate_id)
    if identity is None:
        # A LIVE SESSION FOR AN ADVOCATE WHO IS NOT THERE. The record was
        # deleted or will not open; either way this session must stop working
        # now rather than at expiry.
        raise HTTPException(status_code=401, detail="not signed in")
    return {"advocate": identity.as_dict()}


# ------------------------------------------------------------------- static ---

class _NeverStale(StaticFiles):
    """Static assets that must not outlive the code they were shipped with.

    MEASURED 6 SEPTEMBER 2026. A Register link was added, the server served
    the new `app.js` -- verified on the bytes, 29,265 of them, containing the
    handler -- and the advocate reported the link did nothing. Their browser
    was holding the previous file. `StaticFiles` sends no `cache-control`, so
    a browser applies its own heuristic and can serve a stale script for as
    long as it likes.

    THE FAILURE IS THE SAME SHAPE AS THE SERVER FINGERPRINT, one layer out. A
    scenario run against a server on other code proves nothing, and
    `run_scenario` refuses it; a UI a version behind its API is the same
    mismatch, with nobody refusing it and no way to see it. The advocate says
    a fix did not work, the code says it did, and both are right.

    `no-cache` and not `no-store`: the browser may keep the file and MUST
    revalidate, so an unchanged asset still costs a 304 rather than a
    download. The cost of getting this wrong in the other direction -- an
    advocate acting on a screen the product no longer serves -- is not a
    bandwidth question.
    """

    def is_not_modified(self, response_headers, request_headers) -> bool:
        # Revalidation still works; only the SILENT reuse is refused.
        return super().is_not_modified(response_headers, request_headers)

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["cache-control"] = "no-cache, must-revalidate"
        return response


_WEB = ROOT / "web"
if _WEB.exists():
    app.mount("/static", _NeverStale(directory=str(_WEB)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        # THE PAGE ITSELF TOO. An index that is cached serves the old script
        # tags, so revalidating the assets it names buys nothing.
        return FileResponse(
            str(_WEB / "index.html"),
            headers={"cache-control": "no-cache, must-revalidate"})
