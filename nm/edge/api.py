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

import hmac
import os
from datetime import date
from math import ceil
from pathlib import Path
from typing import Annotated

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from nm.core.turn import TurnEngine, TurnInput, TurnRefused
from nm.domain import attempts, brief
from nm.domain import summary as matter_memory
from nm.domain.advocate import (
    REAUTHENTICATION_MINUTES,
    csrf_token,
    utcnow,
)
from nm.domain.answer import Answer
from nm.domain.authority import Act, ActingAs, capacity_for, permits
from nm.domain.clock import FORUM
from nm.domain.clock import today as forum_today
from nm.domain.commission import (
    Commission,
    Deadline,
    Party,
    WorkProduct,
    material_changes,
)
from nm.domain.emergency import Declaration, latest
from nm.domain.identity import source_fingerprint
from nm.domain.intake import MAX_CHUNK_BYTES
from nm.domain.traceability import implements
from nm.edge.projections import (
    board_projection,
    cover_projection,
    matter_list_projection,
)
from nm.edge.uploads import UploadRefused
from nm.ports.directory import AccountBusy, ProofRefused
from nm.ports.store import StaleWrite

ROOT = Path(__file__).resolve().parents[2]

app = FastAPI(title="Nyaymalaw", version="0.1.0")
_application = None


async def invalid_request(request: Request, exc: RequestValidationError):
    """Validation describes the rejected shape, never echoes submitted material.

    Pydantic's default `input`/`ctx` may contain credentials or legal content.
    Even an unexpected field NAME is caller-controlled. Known schema fields
    and numeric positions are useful; arbitrary extra keys are not disclosed.
    """
    known = {"body", "path", "query", "header", "cookie"}
    for model in tuple(globals().values()):
        if isinstance(model, type) and issubclass(model, BaseModel):
            known.update(model.model_fields)
    route = request.scope.get("route")
    known.update(getattr(route, "param_convertors", {}))
    details = []
    for error in exc.errors():
        kind = error["type"]
        reason = {
            "missing": "This field is required.",
            "extra_forbidden": "This field is not accepted.",
            "string_too_long": "The value exceeds the supported length.",
        }.get(kind, "The supplied value is not valid for this field.")
        details.append({
            "loc": [part if type(part) is int or part in known else "unrecognised_field"
                    for part in error.get("loc", ())],
            "type": kind, "msg": reason,
        })
    return JSONResponse(status_code=422, content={"detail": details})


# Explicit framework registration makes this callback's production consumer
# visible to the same reference sweep as ordinary called guards.
app.add_exception_handler(RequestValidationError, invalid_request)


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
    # A receipt establishes a saved released response. `input_admitted`
    # separately says whether the narrative passed admission: a safely saved
    # blocking question must not claim the unadmitted brief was retained.
    # Non-matter replies have no matter commitment to assert.
    committed: str
    input_admitted: bool
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

    from nm.domain.turn_receipt import release_index

    receipts, problems = release_index(output.matter) if output.matter else ({}, [])
    receipt = receipts.get(output.turn_id)
    if output.matter is not None and (problems or receipt is None):
        raise HTTPException(status_code=500, detail="released response has no valid saved receipt")
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
        committed=("replayed" if output.replayed else "committed") if receipt
        else "not_committed" if output.matter else "not_applicable",
        input_admitted=receipt.input_admitted if receipt is not None else False,
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


#: Origins this installation serves its own page from. Comma-separated. UNSET
#: MEANS SAME-ORIGIN ONLY, which is the correct default for a product served
#: with its own static page and needs no configuration to be right.
_TRUSTED_ORIGINS = "NM_TRUSTED_ORIGINS"

#: ONE REFUSAL FOR EVERY CSRF CAUSE. A missing header, a wrong header and a
#: foreign origin are three facts and the caller learns none of them, on the
#: same rule as every other refusal in this file.
_CSRF_REFUSED = ("This request could not be verified as coming from the "
                 "Nyaymalaw page in this browser. Reload the page and try "
                 "again.")


def _origins(request: Request) -> set[str]:
    configured = (os.environ.get(_TRUSTED_ORIGINS) or "").strip()
    if configured:
        return {o.strip().rstrip("/") for o in configured.split(",") if o.strip()}
    return {str(request.base_url).rstrip("/")}


def _require_origin(request: Request, *, allow_absent: bool = False) -> None:
    """One exact origin policy for credentialled writes and public signup."""
    origin = (request.headers.get("origin") or "").rstrip("/")
    referer = request.headers.get("referer") or ""
    trusted = _origins(request)
    if origin:
        accepted = origin in trusted
    elif referer:
        accepted = any(referer.startswith(o + "/") or referer.rstrip("/") == o
                       for o in trusted)
    else:
        accepted = allow_absent
    if not accepted:
        raise HTTPException(status_code=403, detail=_CSRF_REFUSED)


def csrf_protected(request: Request,
                   nm_session: str | None = Cookie(default=None),
                   x_nm_csrf: str | None = Header(default=None)) -> None:
    """Refuse an unsafe cookie-authenticated request the page did not make.

    BK-31-AC20. Until this existed the only thing between a signed-in advocate
    and a cross-site write was `samesite=lax` on the session cookie -- one
    control, owned by the browser rather than by us, absent in older clients
    and no help at all against a same-site origin.

    TWO CHECKS, BECAUSE EITHER ALONE FAILS OPEN SOMEWHERE.

    The origin check is exact and same-origin by default. It refuses a request
    that declares NO origin and no referer, which is the fail-closed choice: a
    browser sends `Origin` on every cross-origin unsafe request, so an absent
    one is either a same-origin request (which will also carry the header
    below) or a client this endpoint has no reason to serve. An absent input
    reading as permission is §9, and it is how most hand-written origin checks
    are bypassed.

    The token check is a double submit BOUND TO THE SESSION: the readable
    cookie carries `sha256("nm-csrf:" + session token)`, page script echoes it
    as a header, and the server recomputes it from the httponly session cookie
    it received. A cross-site page can read neither cookie nor set the header,
    and a token minted for one session cannot authorise a request carrying
    another -- which a random per-user token would allow.
    """
    # NO SESSION COOKIE, NOTHING TO PROTECT, AND THE 401 IS THE HONEST ANSWER.
    #
    # A route-level dependency runs BEFORE the handler's own, so without this a
    # caller with no session at all got 403 from here instead of 401 from
    # `signed_in`. That is not a harmless swap: `web/app.js` keys its
    # sign-out-and-restore behaviour on 401, and the contract test for the turn
    # route asserts it.
    #
    # It is not a weakening either. CSRF is the risk that a browser ATTACHES
    # CREDENTIALS the caller could not otherwise supply; with no session cookie
    # there is no credential to ride and no privileged operation to reach --
    # every route carrying this dependency also requires `Advocate`, which
    # `tests/test_every_unsafe_route_is_csrf_protected` enforces so this
    # sentence cannot quietly stop being true.
    if not nm_session:
        return

    _require_origin(request)

    expected = csrf_token(nm_session or "")
    if not x_nm_csrf or not hmac.compare_digest(x_nm_csrf, expected):
        raise HTTPException(status_code=403, detail=_CSRF_REFUSED)


#: Applied as a route dependency rather than at each call site, so a handler
#: cannot forget to call it. `tests/test_every_unsafe_route_is_csrf_protected`
#: draws its population from the router itself and fails on a new one.
CsrfProtected = Depends(csrf_protected)


def _uploads():
    service = application().uploads
    if service is None:
        raise HTTPException(503, "sealed original-byte intake is not configured")
    return service


def _upload_call(method, *args):
    try:
        return method(*args)
    except UploadRefused as exc:
        raise HTTPException(exc.status, str(exc)) from None
    except StaleWrite:
        raise HTTPException(409, "matter changed; reload its receipt before resuming") from None
    except Exception:
        # No key, filename, byte content or provider error escapes this edge.
        # A lost response does not prove rollback; the persisted receipt is
        # authoritative and must be read before retrying the same request key.
        raise HTTPException(503, "receipt could not be confirmed; reload before retrying") from None


@app.post("/api/matters/intake", dependencies=[CsrfProtected])
def open_upload_first_intake(body: dict, advocate_id: Advocate) -> dict:
    """An empty owned file, not a dummy brief, inferred fact or passed screen."""
    return _upload_call(_uploads().create_intake, advocate_id, body)


@app.post("/api/matters/{matter_id}/uploads", dependencies=[CsrfProtected])
def begin_upload(matter_id: str, body: dict, advocate_id: Advocate) -> dict:
    return _upload_call(_uploads().begin, matter_id, advocate_id, body)


@app.get("/api/matters/{matter_id}/uploads")
def list_uploads(matter_id: str, advocate_id: Advocate) -> dict:
    return _upload_call(_uploads().list, matter_id, advocate_id)


@app.get("/api/matters/{matter_id}/uploads/{upload_id}")
def inspect_upload(matter_id: str, upload_id: str, advocate_id: Advocate) -> dict:
    return _upload_call(_uploads().get, matter_id, advocate_id, upload_id)


@app.put("/api/matters/{matter_id}/uploads/{upload_id}/chunks/{offset}",
         dependencies=[CsrfProtected])
async def receive_upload_chunk(matter_id: str, upload_id: str, offset: int,
                               request: Request, advocate_id: Advocate) -> dict:
    service = _uploads()
    # Refuse foreign/nonexistent receipts before consuming request bytes.
    _upload_call(service.get, matter_id, advocate_id, upload_id)
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_CHUNK_BYTES:
            raise HTTPException(413, "chunk exceeds the observed-byte bound")
        data.extend(chunk)
    return _upload_call(service.append, matter_id, advocate_id, upload_id, offset, bytes(data))


@app.post("/api/matters/{matter_id}/uploads/{upload_id}/complete", dependencies=[CsrfProtected])
def complete_upload(matter_id: str, upload_id: str, advocate_id: Advocate) -> dict:
    return _upload_call(_uploads().complete, matter_id, advocate_id, upload_id)


@app.post("/api/matters/{matter_id}/uploads/{upload_id}/cancel", dependencies=[CsrfProtected])
def cancel_upload(matter_id: str, upload_id: str, advocate_id: Advocate) -> dict:
    return _upload_call(_uploads().cancel, matter_id, advocate_id, upload_id)


@app.get("/api/matters/{matter_id}/uploads/{upload_id}/content")
def held_upload_content(matter_id: str, upload_id: str, advocate_id: Advocate):
    row = _upload_call(_uploads().get, matter_id, advocate_id, upload_id)
    raise HTTPException(423, row["reason"] + "; original preview and download remain held")


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
    work_product: str = ""
    """An explicit protective_triage request is not permission without a live declaration."""
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

    capacity: dict[str, str] | None = None
    """Explicit capacity state/basis; authenticated actor and time are server-owned."""


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

    Canonical saved releases and explicitly marked unresolved/withheld archive
    records. Unapproved recommendations and raw model/diagnostic traces are
    not browser advice. Release receipts are checked against the applied-turn
    ledger; archival presence alone never establishes successful commitment.

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
    from nm.edge.transcripts import project

    projected, release_problems = project(m, turns)

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
        "state": "ok" if not unreadable and not release_problems else "incomplete",
        "matter_id": matter_id,
        "title": m.title,
        "turns": projected,
        "turn_count": len(projected),
        "release_problems": release_problems,
        "unreadable": [t["turn_id"] for t in unreadable],
        "unreadable_reason": (
            f"{len(unreadable)} diagnostic archive(s) could not be read back. "
            f"Only independently established releases are shown as answers; "
            f"the archive's completeness cannot be verified."
            if unreadable else "; ".join(release_problems) or None),
        "unattributable_count": len(lost),
        "unattributable_reason": (
            f"{len(lost)} transcript(s) in the store could not be read back at "
            f"all, so which matter they belong to is unknown. They may or may "
            f"not be from this one."
            if lost else None),
    }


def _register_of(matter):
    """One strict deadline read, including integrity and assessment provenance."""
    from nm.core.deadlines import read_matter

    return read_matter(matter)


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


@app.get("/api/matters/{matter_id}/cover")
@implements("A1")
def matter_cover(matter_id: str, advocate_id: Advocate) -> dict:
    """THE COVER. BK-33-AC1.

    Separate from the thread board because it answers a different question --
    *what is this file and who is it for* rather than *where does each dispute
    stand* -- and because giving the board a second subject would give its
    arity rule a second bound.
    """
    m = _owned(matter_id, advocate_id)
    return cover_projection(m, _register_of(m))


@app.get("/api/matters/{matter_id}/casefile")
def get_casefile(matter_id: str, advocate_id: Advocate) -> dict:
    """THE ATTRIBUTED LIVING FILE. BK-64-AC1, J-4-AC1. P17.

    A projection, holding nothing the matter does not: every entry carries its
    certainty, its confirmation state, where in the original it came from, the
    contradictions it is linked to and the version it superseded.

    THE TWO CHECKS ARE SERVED WITH IT rather than run somewhere the advocate
    cannot see. `repetition_upgrades` names any fact that reached DOCUMENTED
    with no document to be documented by, and `one_dispute_stays_one` names a
    statement recorded twice with two different answers. Both are normally
    empty, and an empty list is the honest way to say so.
    """
    from nm.core.casefile import build, one_dispute_stays_one, repetition_upgrades

    m = _owned(matter_id, advocate_id)
    casefile = build(m)
    casefile["repetition_upgrades"] = list(repetition_upgrades(m.facts or ()))
    casefile["split_disputes"] = list(one_dispute_stays_one(casefile["live"]))
    return casefile


@app.get("/api/matters/{matter_id}/commission")
def get_commission(matter_id: str, advocate_id: Advocate) -> dict:
    """The current commission, its history and what it does not establish."""
    m = _owned(matter_id, advocate_id)
    current = Commission.from_stored(m.commission)
    return {
        "state": "ok",
        "matter_id": m.id,
        "version": m.version,
        "commission": current.as_dict() if current else None,
        # THE HISTORY IS SERVED, not kept for an audit nobody can reach. An
        # advice given under version 1 was correct work under version 1, and
        # a receiving advocate has to be able to see which version it was.
        "history": [Commission.from_stored(h).as_dict()
                    for h in (m.commission_history or ())
                    if Commission.from_stored(h) is not None],
        "refusals": [r for r in (m.authority_refusals or ())],
    }


@app.post("/api/matters/{matter_id}/commission", dependencies=[CsrfProtected])
def set_commission(matter_id: str, body: dict, advocate_id: Advocate) -> dict:
    """Record or change what this advocate was instructed to do. BK-62-AC1.

    THE AUTHORITY IS ASKED BEFORE ANYTHING IS WRITTEN, through the one policy
    in `nm/domain/authority.py`. This route does not decide who may instruct;
    it asks, and it records the answer either way -- because BK-63-AC1 requires
    a refused operation to be refused AND RECORDED, and a 403 that leaves no
    trace records nothing.

    A MATERIAL CHANGE REOPENS WORK. `material_changes` names which fields
    moved, and the response says so, so an advocate who widens the scope is
    told which readiness state has reopened rather than discovering it later.
    """
    m = _owned(matter_id, advocate_id)
    # The version the advocate reviewed, not the one this request just loaded.
    # Store CAS still protects the interval from this read to the commit.
    observed_version = body.get("expected_version")
    if type(observed_version) is not int or observed_version < 0:
        raise HTTPException(
            status_code=422,
            detail="read the matter first and supply its nonnegative integer expected_version")
    if observed_version != m.version:
        raise HTTPException(
            status_code=409,
            detail=("the matter changed since these instructions were reviewed; "
                    "reopen before editing"))
    # TWO DIFFERENT QUESTIONS, and conflating them was the first draft's bug.
    #
    # (1) MAY THIS PERSON KEEP THE FILE? The advocate records what they were
    #     instructed; that is their ordinary work and is `Act.RECORD`. Asking
    #     `Act.INSTRUCT` here made an advocate unable to write down their own
    #     instructions, which the served test caught.
    acting_as = _capacity_of(m, advocate_id, body.get("acting_as"))
    ruling = permits(advocate_id, acting_as, Act.RECORD)
    if not ruling.authorises():
        _record_refusal(m, ruling)
        raise HTTPException(
            status_code=403,
            detail=(f"this instruction was not recorded: {ruling.why}"))

    previous = Commission.from_stored(m.commission)
    try:
        proposed = _commission_from(body, previous, advocate_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # (2) IS THE INSTRUCTION ATTRIBUTABLE? BK-63-AC1 asks that every material
    #     instruction be attributable to an ALLOWED ROLE -- a question about
    #     the party the commission names, not about the person typing. A
    #     commission recording that a clerk instructed a change of scope is
    #     not a record of an instruction; it is a record of a problem.
    moved = material_changes(previous, proposed)
    source = proposed.instructing
    if moved and source is not None:
        attributable = permits(source.party_id, source.capacity, Act.INSTRUCT)
        if not attributable.authorises():
            _record_refusal(m, attributable)
            raise HTTPException(
                status_code=403,
                detail=(f"this instruction is not attributable to anyone who "
                        f"could give it: {attributable.why} It is recorded on "
                        f"the file that it was attempted."))

    import dataclasses

    history = tuple(m.commission_history or ())
    if previous is not None:
        history = (*history, previous.as_dict())
    updated = dataclasses.replace(
        m, commission=proposed.as_dict(), commission_history=history,
        version=m.version + 1)
    if moved:
        from nm.core.screens import ScreenKind

        # Only scope rests on these instructions; retain unrelated assessments.
        prior_answer = (m.intake_answers or {}).get("scope")
        updated = dataclasses.replace(
            updated,
            intake_answers={k: v for k, v in (m.intake_answers or {}).items()
                            if k != "scope"},
            screens=tuple(s for s in (m.screens or ())
                          if getattr(s, "kind", None) is not ScreenKind.SCOPE
                          and not (isinstance(s, dict) and s.get("kind") == "scope")),
            commission_invalidations=(*(m.commission_invalidations or ()), {
                "from_version": previous.version, "to_version": proposed.version,
                "fields": list(moved), "by": advocate_id,
                "at": proposed.recorded_at, "prior_scope_answer": prior_answer,
                "why": "material instructions changed; scope must be confirmed again"}))
    try:
        application().store.commit(updated, expected_version=m.version)
    except StaleWrite as moved_underneath:
        raise HTTPException(status_code=409,
                            detail=str(moved_underneath)) from None
    return {
        "state": "commission_recorded",
        "matter_id": m.id,
        "version": updated.version,
        "commission": proposed.as_dict(),
        # WHAT THIS REOPENED. Empty is a real and common answer.
        "material_changes": list(moved),
        "reopened": bool(moved),
        "unknowns": list(proposed.unknowns()),
    }


@app.post("/api/matters/{matter_id}/emergency", dependencies=[CsrfProtected])
def declare_emergency(matter_id: str, body: dict, advocate_id: Advocate) -> dict:
    """Declare an emergency. BK-78-AC1.

    IT BUYS PROTECTIVE OR REFERRAL GUIDANCE AND NOTHING ELSE, and the record
    says so in the same words the screen module uses. What is persisted is the
    actor, the basis, the screens that were outstanding AT THAT MOMENT and an
    expiry -- because BK-78-AC2 requires the declaration and its expiry to
    survive retry and re-entry, and a boolean survives neither.

    A BASIS IS REQUIRED. A declaration with no basis is a switch, and a switch
    is what this route must not become.
    """
    import dataclasses

    m = _owned(matter_id, advocate_id)

    # REVOCATION IS THIS ROUTE, NOT A SECOND PATH. A `/emergency/revoke` path
    # existed here and was POST-only, so an unauthenticated GET answered 405
    # instead of 401 -- which discloses that the endpoint exists. One path
    # with a GET beside it cannot do that, and revocation is still a new
    # record rather than an erasure.
    if "urgency_command" in body:
        return _record_urgency(m, advocate_id, body)
    if "revoke" in body:
        if body["revoke"] is not True:
            raise HTTPException(status_code=422, detail="revocation must be explicitly true")
        return _revoke_emergency(m, advocate_id, body)

    # A screen exception is a professional act, unlike an ordinary capacity
    # report, instruction or recorded danger. Revocation above remains available
    # when approval lapses. A supplied request field cannot self-approve.
    if application().engine.professional_access(advocate_id)["state"] != "approved":
        raise HTTPException(
            status_code=403,
            detail="This screen exception needs current operator-reviewed professional approval. "
                   "Your own workspace, matters, ordinary advice and urgency records "
                   "remain available.")

    import re

    request_key = body.get("request_key")
    if not isinstance(request_key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", request_key):
        raise HTTPException(status_code=422, detail="supply a stable declaration request_key")
    basis = body.get("basis")
    if not isinstance(basis, str) or not basis.strip():
        raise HTTPException(
            status_code=400,
            detail=("an emergency declaration needs its basis -- what the "
                    "danger is. A declaration with no basis is a switch."))
    basis = basis.strip()
    hours = body.get("hours", 24)
    if not isinstance(hours, int) or isinstance(hours, bool):
        raise HTTPException(status_code=422, detail="emergency duration must be whole hours")
    offer = {"actor_id": advocate_id, "basis": basis, "hours": hours}
    matches = [row for row in (m.emergencies or ())
               if isinstance(row, dict) and row.get("request_key") == request_key]
    if matches:
        if len(matches) != 1:
            raise HTTPException(status_code=503, detail="declaration identity is ambiguous")
        prior = matches[0]
        if prior.get("request_offer") != offer:
            raise HTTPException(
                status_code=409, detail="declaration key names different instructions")
        declared = Declaration.from_stored(prior)
        if declared is None:
            raise HTTPException(status_code=503, detail="the recorded declaration is unreadable")
        # No clock arithmetic, mutation or fresh screening on a replay. Its
        # expiry, revocation and original outstanding population remain intact.
        observed = utcnow()
        return {"state": "emergency_declared", "matter_id": m.id,
                "request_key": request_key, "replayed": True,
                "emergency": declared.as_dict(), "said": declared.said(observed),
                "declaration_state": declared.state_at(observed),
                "permits_substance": False, "outstanding": list(declared.outstanding)}

    outstanding = _outstanding_screens(m)
    try:
        declared = Declaration.declare(
            actor_id=advocate_id, basis=basis, outstanding=outstanding,
            now=utcnow(), hours=hours)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    updated = dataclasses.replace(
        m, emergencies=(*(m.emergencies or ()), {
            **declared.as_dict(), "request_key": request_key, "request_offer": offer}),
        version=m.version + 1)
    try:
        application().store.commit(updated, expected_version=m.version)
    except StaleWrite as moved:
        raise HTTPException(status_code=409, detail=str(moved)) from None
    observed = utcnow()
    return {
        "state": "emergency_declared",
        "matter_id": m.id,
        "request_key": request_key,
        "replayed": False,
        "emergency": declared.as_dict(),
        "said": declared.said(observed),
        "declaration_state": declared.state_at(observed),
        "permits_substance": False,
        "outstanding": list(outstanding),
    }


@app.get("/api/matters/{matter_id}/emergency")
def get_emergency(matter_id: str, advocate_id: Advocate) -> dict:
    """What governs NOW, and everything ever declared.

    THE GOVERNING ONE IS COMPUTED FROM THE CLOCK rather than stored, so
    re-entry two days later gets the true answer instead of the one that was
    true when somebody last wrote a field.
    """
    m = _owned(matter_id, advocate_id)
    from nm.domain.urgency import project

    urgency = project(m.urgency_records)
    now = utcnow()
    governing, target_ref, _ = _emergency_target(m, now)
    history = [Declaration.from_stored(x) for x in (m.emergencies or ())]
    unreadable = sum(d is None for d in history)
    approval = application().engine.professional_access(advocate_id)
    permitted = (governing is not None and governing.active_at(now)
                 and governing.actor_id == advocate_id and approval["state"] == "approved")
    return {
        "state": "incomplete" if unreadable or urgency["unreadable_records"] else "ok",
        "matter_id": m.id,
        "version": m.version,
        "urgency_register": urgency,
        "governing_ref": target_ref,
        "governing": governing.as_dict() if governing else None,
        "professional_approval": approval,
        "permits_protective_handoff": permitted,
        "said": ("The declaration remains on file, but no screen exception is permitted without "
                 "current professional approval for its recorded actor. "
                 "Ordinary own-file work remains available."
                 if governing and governing.active_at(now) and not permitted
                 else governing.said(now) if governing
                 else "emergency history could not be assessed; no exception is granted"
                 if unreadable
                 else "no emergency exception is live on this matter"),
        "unreadable_records": unreadable,
        # HISTORY IS KEPT AND SERVED. An expired declaration is evidence of
        # why the file was handled as it was; only the permission lapsed.
        "history": [
            {**d.as_dict(), "state": d.state_at(now), "said": d.said(now)}
            for d in history if d is not None],
        "permits_substance": False,
    }


def _record_urgency(matter, advocate_id: str, body: dict) -> dict:
    """Persist a manual danger or its explicit resolution, never a permission."""
    import dataclasses
    import re

    from nm.domain.matter import new_id
    from nm.domain.urgency import (
        UrgencyReceipt,
        UrgencyRegister,
        normalise_instruction,
        read_receipts,
        read_register,
    )

    command = body.get("urgency_command")
    fields = {"urgency_command", "request_key", "expected_version"}
    fields |= {"urgency"} if command == "raise" else {"urgency_id", "resolution_basis"}
    expected, request_key = body.get("expected_version"), body.get("request_key")
    if (command not in ("raise", "resolve") or set(body) != fields
            or type(expected) is not int or expected < 0 or not isinstance(request_key, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", request_key)):
        raise HTTPException(status_code=422, detail="supply one exact keyed urgency command "
                            "and the observed matter version")
    offer = {"actor_id": advocate_id, "command": command, "expected_version": expected}
    try:
        if command == "raise":
            offer["urgency"] = normalise_instruction(body["urgency"])
        else:
            for name in ("urgency_id", "resolution_basis"):
                value = body[name]
                if not isinstance(value, str) or not value.strip() or len(value) > 4000:
                    raise ValueError(f"supply the named {name}")
                offer[name] = value.strip()
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    rows, unreadable = read_register(matter.urgency_records)
    operations = matter.urgency_operations
    if unreadable:
        raise HTTPException(status_code=503, detail="the urgency record cannot be reconciled")
    try:
        receipts = read_receipts(operations, rows, matter.id, matter.version)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(
            status_code=503, detail="the urgency receipt cannot be reconciled") from exc
    prior = receipts.get(request_key)
    if prior is not None:
        if prior.offer != offer:
            raise HTTPException(status_code=409, detail="urgency key names different instructions")
        return prior.projected(replayed=True)
    if expected != matter.version:
        raise HTTPException(status_code=409, detail="the file changed; reopen the urgency register")
    try:
        if command == "raise":
            changed = UrgencyRegister.raise_manual(new_id("urgency"), offer["urgency"],
                                                  advocate_id, utcnow())
            saved_rows = (*rows, changed)
        else:
            selected = next((row for row in rows if row.urgency_id == offer["urgency_id"]), None)
            if selected is None:
                raise HTTPException(status_code=404, detail="the named urgency was not found")
            changed = selected.resolve(advocate_id, offer["resolution_basis"], utcnow())
            saved_rows = tuple(changed if row.urgency_id == selected.urgency_id else row
                               for row in rows)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    receipt = UrgencyReceipt(request_key, offer, matter.id, changed.urgency_id, matter.version + 1)
    result = receipt.projected()
    updated = dataclasses.replace(
        matter, urgency_records=tuple(row.as_dict() for row in saved_rows),
        urgency_operations=(*operations, receipt.as_dict()), version=matter.version + 1)
    try:
        application().store.commit(updated, expected_version=matter.version)
    except StaleWrite as exc:
        raise HTTPException(
            status_code=409, detail="the file changed; reopen the urgency register") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="the urgency change was not confirmed") from exc
    return result


def _outstanding_screens(matter) -> tuple[str, ...]:
    """Which screens are not clear RIGHT NOW, through the screen owner.

    `nm/core/screens.unscreened` decides this. Recomputing it here would be
    the second copy that P14's own brief forbids -- *use the existing
    screening owner consistently* -- and the copy is where an incomplete
    screen starts counting as good enough.
    """
    from nm.core.screens import unscreened

    try:
        return tuple(unscreened(tuple(matter.screens or ())))
    except Exception:  # noqa: BLE001 -- an unreadable screen set is outstanding
        return ("the screen set on this matter could not be read",)


@app.get("/api/matters/{matter_id}/concede")
def conceded(matter_id: str, advocate_id: Advocate) -> dict:
    """What has been conceded on this matter, and what was refused.

    THIS EXISTS SO THE PATH IS NOT POST-ONLY, and it earns its place: the
    refused attempts were previously readable only through the commission
    route, which is a strange place to look for them.
    """
    m = _owned(matter_id, advocate_id)
    return {
        "state": "ok",
        "matter_id": m.id,
        "decisions": list(m.decisions or ()),
        "externally_effective": False,
        "refused": [r for r in (m.authority_refusals or ())
                    if isinstance(r, dict) and r.get("act") == "concede"],
    }


def _emergency_target(matter, now):
    """Name the exact governing append, including legacy unkeyed records."""
    import hashlib
    import json

    rows = matter.emergencies or ()
    governing = latest(rows, now)
    if governing is None:
        return None, None, None
    selected = max(i for i, row in enumerate(rows)
                   if Declaration.from_stored(row) == governing)
    identity = [matter.id, selected, rows[selected]]
    reference = hashlib.sha256(json.dumps(
        identity, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
    return governing, reference, selected


def _revoke_emergency(matter, advocate_id: str, body: dict) -> dict:
    """End only the declaration the user observed, never its replacement."""
    import dataclasses

    expected = body.get("expected_version")
    reference = body.get("governing_ref")
    if (type(expected) is not int or expected < 0 or not isinstance(reference, str)
            or len(reference) != 64 or any(c not in "0123456789abcdef" for c in reference)):
        raise HTTPException(
            status_code=422, detail="supply the observed declaration and file version")
    if expected != matter.version:
        raise HTTPException(status_code=409, detail="the file changed; reopen the declaration")
    now = utcnow()
    governing, current_ref, selected = _emergency_target(matter, now)
    if governing is None or reference != current_ref:
        raise HTTPException(
            status_code=409,
            detail="the observed exception is no longer current; reopen the declaration")
    revoked = governing.revoke(advocate_id, now)
    kept = list(matter.emergencies or ())
    # The governing append is the last equal declaration when second-precision
    # records coincide. Preserve every other record and the immutable request
    # identity on this one; revocation must not make its key available again.
    original = kept[selected] if isinstance(kept[selected], dict) else {}
    kept[selected] = {**original, **revoked.as_dict()}
    updated = dataclasses.replace(
        matter, emergencies=tuple(kept),
        version=matter.version + 1)
    try:
        application().store.commit(updated, expected_version=matter.version)
    except StaleWrite as moved:
        raise HTTPException(status_code=409, detail=str(moved)) from None
    return {"state": "emergency_revoked", "matter_id": matter.id,
            "governing_ref": reference, "version": updated.version,
            "said": revoked.said(now)}


@app.post("/api/matters/{matter_id}/concede", dependencies=[CsrfProtected])
def concede(matter_id: str, body: dict, advocate_id: Advocate) -> dict:
    """Give up a point. THE ACT THIS WHOLE PACKET EXISTS TO REFUSE WRONGLY.

    Served so that the refusal is exercisable through the real surface rather
    than only in a unit test: an advocate is `ADVISING`, and advising may not
    concede however reasonable the concession looks.
    """
    m = _owned(matter_id, advocate_id)
    acting_as = _capacity_of(m, advocate_id, body.get("acting_as"))
    ruling = permits(advocate_id, acting_as, Act.CONCEDE)
    if not ruling.authorises():
        _record_refusal(m, ruling)
        raise HTTPException(
            status_code=403,
            detail=(f"this concession was not made: {ruling.why} It is "
                    f"recorded on the file that it was attempted."))
    import dataclasses

    from nm.domain.matter import new_id

    point = str(body.get("on") or "").strip()
    if not point:
        raise HTTPException(status_code=422, detail="name the point being decided")
    decision_id = str(body.get("decision_id") or new_id("decision"))
    current = Commission.from_stored(m.commission)
    record = {"decision_id": decision_id, "on": point, "by": advocate_id,
              "act": ruling.act.value, "capacity": ruling.capacity.value,
              "commission_version": current.version if current else None,
              "at": utcnow().isoformat(), "externally_effective": False}
    previous = next((d for d in (m.decisions or ())
                     if isinstance(d, dict) and d.get("decision_id") == decision_id), None)
    if previous:
        if any(previous.get(k) != record[k] for k in
               ("on", "by", "act", "commission_version")):
            raise HTTPException(status_code=409,
                                detail="this decision key identifies another decision")
        record = previous
    else:
        try:
            application().store.commit(dataclasses.replace(
                m, decisions=(*(m.decisions or ()), record), version=m.version + 1),
                expected_version=m.version)
        except StaleWrite as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="the internal decision was not recorded; no action was taken") from exc
    return {"state": "decision_recorded", "matter_id": m.id,
            "decision": record, "externally_effective": False,
            "said": "Recorded as an internal decision only; "
                    "nothing was sent, filed or conceded externally."}


def _owned(matter_id: str, advocate_id: str):
    """The matter, or the same 404 whether it is absent or somebody else's."""
    m = application().store.load(matter_id)
    if m is None or m.advocate_id != advocate_id:
        raise HTTPException(status_code=404, detail="no such matter")
    return m


def _capacity_of(matter, advocate_id: str, claimed) -> ActingAs:
    """What this person is TO THIS MATTER. READ, NEVER TAKEN FROM THE REQUEST.

    A caller that could name its own capacity could name `deciding` and
    concede the client's case, which would make the whole policy decorative.
    Authored commissions are not grants. Trusted provisioning records are
    bound to a commission version, expire and can be revoked; a request may
    narrow those powers but cannot create them.
    """
    current = Commission.from_stored(matter.commission)
    return capacity_for(advocate_id, matter.authority_bindings,
                        current.version if current else 0, utcnow(), claimed)


def _record_refusal(matter, ruling) -> None:
    """Keep the attempt or disclose the failed audit; never permit the action."""
    import dataclasses

    try:
        line = {**ruling.as_dict(), "at": utcnow().isoformat(timespec="seconds")}
        application().store.commit(
            dataclasses.replace(
                matter,
                authority_refusals=(*(matter.authority_refusals or ()), line),
                version=matter.version + 1),
            expected_version=matter.version)
    except Exception as exc:  # noqa: BLE001 -- refusal stands, audit failure is visible
        raise HTTPException(status_code=503, detail=(
            "the operation was refused, but its audit record could not be saved; "
            "no decision or external action was made")) from exc


def _commission_from(body: dict, previous, recorded_by: str) -> "Commission":
    """Build the next version from what was sent, keeping what was not.

    A PATCH, NOT A REPLACE. An advocate correcting the deadline must not have
    to resend the objective, and a field they omitted must not silently become
    empty -- which would read as an instruction that said nothing.
    """
    base = previous or Commission()
    deadline = base.deadline
    sent = body.get("deadline")
    if isinstance(sent, dict):
        kind = str(sent.get("kind") or "unknown")
        if kind == "date":
            deadline = Deadline.on_date(
                on=str(sent.get("on") or "").strip(),
                basis=str(sent.get("basis") or "").strip())
        elif kind == "none_applies":
            deadline = Deadline.none_applies(
                str(sent.get("reason") or "").strip()
                or "the advocate recorded that none applies")
        else:
            deadline = Deadline.unknown(
                str(sent.get("reason") or "").strip()
                or "the advocate has not established it")

    def party(key: str, fallback):
        value = body.get(key)
        if not isinstance(value, dict):
            return fallback
        try:
            capacity = ActingAs(str(value.get("capacity") or "unknown"))
        except ValueError:
            capacity = ActingAs.UNKNOWN
        return Party(
            party_id=str(value.get("party_id") or "").strip() or "(unnamed)",
            described_as=(str(value.get("described_as") or "").strip()
                          or "(not described)"),
            capacity=capacity)

    try:
        work = (WorkProduct(str(body["work_product"]))
                if body.get("work_product") else base.work_product)
    except ValueError:
        work = base.work_product

    fields = dict(
        objective=str(body.get("objective", base.objective) or "").strip(),
        work_product=work,
        scope=str(body.get("scope", base.scope) or "").strip(),
        exclusions=tuple(body.get("exclusions", base.exclusions) or ()),
        instructing=party("instructing", base.instructing),
        deciding=party("deciding", base.deciding),
        forum=str(body.get("forum", base.forum) or "").strip(),
        deadline=deadline,
        constraints=tuple(body.get("constraints", base.constraints) or ()),
        recorded_by=recorded_by,
        recorded_at=utcnow().isoformat(timespec="seconds"),
        because=str(body.get("because") or "").strip(),
    )
    if previous is None:
        return Commission(version=1, **fields)
    return previous.next_version(**fields)


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


@app.post("/api/turn", dependencies=[CsrfProtected])
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
        work_product=req.work_product,
        parties=dict(req.parties or {}),
        release=dict(req.release or {}),
        capacity=dict(req.capacity) if req.capacity is not None else None,
        expected_version=req.expected_version,
        request_offer=req.model_dump(mode="json", exclude={"turn_id"}),
        **({"turn_id": req.turn_id} if req.turn_id else {}),
    )
    # The engine reconciles an exact durable receipt BEFORE stale new-work
    # admission, and both happen before any model read. Changing the caller's
    # expected version on retry would change its original instructions.

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
            "committed": ("previously_committed" if exc.prior_receipt_saved
                          else "not_committed"),
            **({"prior_receipt_saved": True, "release_state": "replay_refused"}
               if exc.prior_receipt_saved else {}),
        }) from exc
    except StaleWrite as exc:
        raise HTTPException(status_code=409, detail={
            "why": str(exc),
            "turn_id": req.turn_id,
            "committed": "not_committed",
            "expected_version": getattr(exc, "expected_version", req.expected_version),
            "matter_version": getattr(exc, "matter_version", None),
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


# One served new-credential input bound for signup and password replacement.
# It is not a verification limit: an existing credential may predate it.
_NEW_PASSWORD_MAX = 1024


class Credentials(BaseModel):
    advocate_id: NonBlank = Field(min_length=1)
    password: str = Field(min_length=1)


class Registration(BaseModel):
    """Public account creation, or password-only acceptance of an invitation.

    Public email is an unverified sign-in handle, not a qualification or a
    shared-firm assignment. The optional invitation header selects the older
    bound-identity lane; that lane cannot accept a caller-supplied email.
    """

    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(default=None, max_length=320)
    password: str = Field(min_length=1, max_length=_NEW_PASSWORD_MAX)
    password_again: str = Field(min_length=1, max_length=_NEW_PASSWORD_MAX)


class Recovery(BaseModel):
    """A public recovery request. Identity and code failures stay identical."""

    model_config = ConfigDict(extra="forbid")

    advocate_id: NonBlank = Field(min_length=1)
    recovery_code: str = Field(min_length=1)
    password: str = Field(min_length=1, max_length=_NEW_PASSWORD_MAX)
    password_again: str = Field(min_length=1, max_length=_NEW_PASSWORD_MAX)


_RECOVERY_REFUSED = (
    "That recovery attempt was not accepted. Check the email and unused "
    "recovery code, then try again. Nothing was changed.")


def _workspace(identity) -> dict:
    """The one server-owned context in which this advocate's files are held."""
    workspace_id = (identity.firm_id or "").strip()
    return {
        "id": workspace_id or f"advocate:{identity.id}",
        "label": workspace_id or f"{identity.name}'s private workspace",
        "scope": "the matters held for this advocate",
    }


def _professional_status(directory, identity, now) -> dict:
    """Expose only derived approval; unavailable approval never blocks sign-in."""
    from nm.core.professional_access import read_professional_status

    return read_professional_status(
        lambda account_id: directory.professional_approval(account_id), identity.id, now)


# Public authentication never diagnoses account existence; the directory's
# operator audit retains the cause. Registration returns no existing identity.
_REFUSED_DEFAULT = (
    "Those credentials were not accepted. Check the email and password, or "
    "use account recovery. If the problem continues, contact support.")
_REGISTRATION_REFUSED = (
    "Registration could not be completed. Try signing in or use account "
    "recovery; otherwise contact support.")
_REGISTRATION_UNAVAILABLE = (
    "Registration is temporarily unavailable. Try again later; if it "
    "continues, contact support. Your existing account can still sign in.")


def registration_origin(request: Request,
                        x_enrolment_invitation: str | None = Header(default=None)) -> None:
    """Public signup needs the page origin; invitation API clients need their token.

    A supplied foreign origin is refused on either lane. Header presence,
    including an empty/invalid token, selects the invited lane and never falls
    back to public signup. Its ordinary token controls still decide admission.
    """
    _require_origin(request, allow_absent=x_enrolment_invitation is not None)


def _admit_auth_attempt(directory, advocate_id, source, now, *, action: str) -> None:
    """One admission boundary for every failure-counted authentication door.

    Counters and thresholds remain owned by the directory and attempts policy.
    The existing controlled-local availability policy remains explicit: an
    unreadable counter cannot enforce and health reports it as not running.
    No refused retry is itself a failure, so knocking cannot extend a pause.
    """
    counts = directory.failures_since(advocate_id, source, now - attempts.WINDOW)
    if counts is None:
        return
    seen = attempts.verdict(counts[0], counts[1], now)
    if not seen.allowed:
        retry_after = max(1, ceil(seen.retry_after.total_seconds()))
        raise HTTPException(status_code=429, detail=seen.said_for(action),
                            headers={"Retry-After": str(retry_after)})


@app.post("/api/register", dependencies=[Depends(registration_origin)])
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
    from nm.domain.advocate import (
        AdvocateIdentity,
        Enrolment,
        enrol,
        registration_email,
        token_fingerprint,
    )
    from nm.ports.directory import (
        AlreadyEnrolled,
        InvitationRefused,
        RegistrationUnavailable,
    )

    now = utcnow()
    source = request.client.host if request.client else "unknown-source"
    directory = application().directory
    invited = x_enrolment_invitation is not None
    invitation = (x_enrolment_invitation or "").strip()
    rate_key = f"invitation:{token_fingerprint(invitation)}"
    if invited:
        if "email" in body.model_fields_set:
            raise HTTPException(422, "An invitation supplies its own account identity.")
        _admit_auth_attempt(directory, rate_key, source, now, action="enrolment")
    else:
        try:
            email = registration_email(body.email)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        try:
            admitted = directory.admit_registration(email, source, now)
        except RegistrationUnavailable as exc:
            raise HTTPException(503, _REGISTRATION_UNAVAILABLE,
                                headers={"Retry-After": "60"}) from exc
        if not admitted.allowed:
            retry_after = max(1, ceil(admitted.retry_after.total_seconds()))
            raise HTTPException(
                429, "Too many registration attempts. Wait and try again.",
                headers={"Retry-After": str(retry_after)})

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
        if invited:
            identity, recovery_codes = directory.accept_invitation(
                invitation, credential, now)
        else:
            identity = AdvocateIdentity(id=email, name=email, email=email)
            recovery_codes = directory.enrol(Enrolment(
                identity=identity, credential=credential, created_at=now))
    except InvitationRefused as exc:
        directory.note_failure(rate_key, source, now)
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AlreadyEnrolled as exc:
        raise HTTPException(status_code=409, detail=(
            str(exc) if invited else _REGISTRATION_REFUSED)) from exc
    except OSError as exc:
        raise HTTPException(503, _REGISTRATION_UNAVAILABLE,
                            headers={"Retry-After": "60"}) from exc

    # RETURNED BECAUSE IT IS WHAT THEY SIGN IN WITH. A registration that
    # succeeds and does not say what to type next has enrolled someone who
    # cannot get in.
    return {
        "advocate_id": identity.id,
        "name": identity.name,
        "recovery_codes": list(recovery_codes),
    }


@app.post("/api/recover")
@implements("A1")
def recover(body: Recovery, request: Request) -> dict:
    """Use one advocate-held code; reveal nothing about account existence."""
    from nm.domain.advocate import canonical_id, enrol

    now = utcnow()
    source = request.client.host if request.client else "unknown-source"
    rate_key = f"recovery:{canonical_id(body.advocate_id)}"
    _admit_auth_attempt(application().directory, rate_key, source, now,
                        action="recovery")

    if body.password != body.password_again:
        raise HTTPException(
            status_code=400,
            detail="The two passwords do not match. Nothing was changed.")
    try:
        credential = enrol(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = application().directory.recover(
        body.advocate_id, body.recovery_code, credential, now)
    if not result.success:
        application().directory.note_failure(rate_key, source, now)
        raise HTTPException(status_code=403, detail=_RECOVERY_REFUSED)
    return {"recovered": True, "sessions_ended": result.sessions_ended}


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
    _admit_auth_attempt(application().directory, body.advocate_id, source, now,
                        action="sign-in")

    import secrets

    device_id = nm_device or secrets.token_urlsafe(16)
    device = _device(device_id, user_agent)
    try:
        opened = application().directory.authenticate_and_open_session(
            body.advocate_id, body.password, device, now)
    except AccountBusy as exc:
        raise HTTPException(
            status_code=503,
            detail="Account access is changing. Try sign-in again in a moment.") from exc
    if opened is None:
        # 401 AND NOTHING ELSE. Not 404 for an unknown advocate and 401 for a
        # wrong password -- the status code is a message too.
        # THE FAILURE IS COUNTED (BK-20). Recorded after the attempt so a
        # successful sign-in never adds to the count, and before the
        # response so the next attempt sees it.
        application().directory.note_failure(body.advocate_id, source, now)
        raise HTTPException(
            status_code=401,
            detail=_REFUSED_DEFAULT)
    identity, token, recovery_codes = opened

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
    # THE CSRF HALF, AND IT IS THE ONE COOKIE THAT MUST BE READABLE.
    #
    # `samesite=lax` already blocks a cross-site POST from carrying the session
    # cookie in a current browser, and it was the only thing standing between a
    # signed-in advocate and a cross-site request until now. It is one control,
    # it is the browser's rather than ours, and it does not cover a same-site
    # attacker or a client that predates it. `strict` here because this value
    # has no top-level-navigation use at all.
    response.set_cookie("nm_csrf", csrf_token(token), httponly=False,
                        samesite="strict", secure=secure,
                        max_age=60 * 60 * 12, path="/")
    result = {"advocate": identity.as_dict(), "workspace": _workspace(identity),
              "professional_approval": _professional_status(
                  application().directory, identity, now)}
    if recovery_codes:
        result["recovery_codes"] = list(recovery_codes)
    return result


@app.post("/api/logout", dependencies=[CsrfProtected])
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


@app.post("/api/sessions/revoke", dependencies=[CsrfProtected])
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
    # THE CURRENT RECOVERY GENERATION, so a page can state what it was looking
    # at when it asks to replace the set. BK-31-AC20.
    #
    # A COUNTER, NOT A SECRET: it says how many times this advocate's own codes
    # have been replaced and nothing about their value. Without it the client
    # would have to echo whatever the proof told it, which makes the
    # compare-and-set agree with itself instead of with what the advocate saw.
    directory = application().directory
    reader = getattr(directory, "account_security", None)
    generation = reader(advocate_id) if callable(reader) else None
    return {"advocate": identity.as_dict(), "workspace": _workspace(identity),
            "professional_approval": _professional_status(directory, identity, utcnow()),
            # THREE STATES. `null` means this deployment's directory cannot say,
            # which a client must treat as "do not attempt a rotation" rather
            # than as generation zero.
            "recovery_generation": generation}


# ------------------------------------------- replacing the recovery codes ---


class ReauthenticateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Verify the same existing credential that login accepts, including one
    # created before the public new-password input bound existed.
    password: str = Field(min_length=1)


class RotateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proof: str = Field(min_length=1, max_length=512)
    #: THE GENERATION THE PAGE WAS LOOKING AT. Required, not optional: a
    #: default would let a client that never read the current state replace a
    #: set it has not seen, and "the caller did not say" would then be
    #: indistinguishable from "the caller checked and it matched".
    expected_recovery_generation: int = Field(ge=0)


@app.post("/api/reauthenticate", dependencies=[CsrfProtected])
def reauthenticate(body: ReauthenticateRequest, request: Request,
                   advocate_id: Advocate,
                   nm_session: str | None = Cookie(default=None),
                   nm_device: str | None = Cookie(default=None),
                   user_agent: str | None = Header(default=None)) -> dict:
    """Prove the current password again, inside this session. BK-31-AC20.

    A SEPARATE STEP FROM THE ROTATION ON PURPOSE. Replacing the last-resort
    credential on the strength of a session cookie alone means an unlocked
    laptop is enough; requiring the password at the moment of the change is
    what makes it a decision the advocate made.

    401 FOR EVERY FAILURE, and the response says nothing about which. A signed
    in advocate who could distinguish "wrong password" from "your session is
    not valid here" has an oracle the rest of this file is built to deny them.
    """
    directory = application().directory
    if not hasattr(directory, "reauthenticate"):
        raise HTTPException(
            status_code=501,
            detail="this deployment's directory cannot re-authenticate")
    now = utcnow()
    source = request.client.host if request.client else "unknown-source"
    _admit_auth_attempt(directory, advocate_id, source, now,
                        action="re-authentication")
    proof = directory.reauthenticate(
        advocate_id, body.password, nm_session or "",
        _device(nm_device, user_agent), now, source=source)
    if not proof:
        raise HTTPException(status_code=401, detail="that did not match")
    # THE PROOF TRAVELS IN THE BODY, NOT A COOKIE. A cookie would ride along
    # with every later request for its whole life; this is handed to the page,
    # held in a variable, spent once and dropped.
    return {"proof": proof, "expires_in_seconds": REAUTHENTICATION_MINUTES * 60}


@app.post("/api/recovery-codes/rotate", dependencies=[CsrfProtected])
def rotate_recovery_codes(body: RotateRequest, request: Request,
                          advocate_id: Advocate,
                          nm_session: str | None = Cookie(default=None),
                          nm_device: str | None = Cookie(default=None),
                          user_agent: str | None = Header(default=None)) -> dict:
    """Replace every recovery code at once. THE CODES ARE RETURNED ONCE.

    D-013 promised this and nothing served it, so an advocate whose printed
    codes had been seen had one route back: spend one of the compromised codes
    to recover, leaving the other nine exactly as exposed.

    THERE IS NO READ-BACK ENDPOINT AND THERE MUST NEVER BE ONE. These codes
    exist in this response and nowhere else -- not on disk, not in the audit
    line, not in a later `GET`. An advocate who loses this response
    re-authenticates and replaces the set again, which is a minor inconvenience
    and the only design in which a stolen store is not a stolen account.
    """
    directory = application().directory
    if not hasattr(directory, "rotate_recovery_codes"):
        raise HTTPException(
            status_code=501,
            detail="this deployment's directory cannot replace recovery codes")
    now = utcnow()
    source = request.client.host if request.client else "unknown-source"
    _admit_auth_attempt(directory, advocate_id, source, now,
                        action="recovery-code replacement")
    try:
        codes = directory.rotate_recovery_codes(
            advocate_id, body.proof, nm_session or "",
            _device(nm_device, user_agent),
            body.expected_recovery_generation, now, source=source)
    except ProofRefused as refused:
        # 409, NOT 403. The caller is authenticated and permitted; what failed
        # is that the state they were acting on has moved or their proof is
        # spent. A 403 here would read as "you may not do this", which sends
        # the advocate to an administrator instead of to the retry that works.
        raise HTTPException(status_code=409, detail=str(refused)) from None
    except AccountBusy:
        raise HTTPException(
            status_code=409,
            detail="another change to this account is in progress. "
                   "Wait a moment and try again.") from None
    return {"recovery_codes": list(codes), "replaced": len(codes)}


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
