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
import logging
import os
import uuid
from dataclasses import replace
from datetime import date
from math import ceil
from pathlib import Path
from typing import Annotated, Literal

from fastapi import (
    BackgroundTasks,
    Cookie,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool

from nm.core import briefing as _briefing
from nm.core.turn import TurnEngine, TurnInput, TurnRefused
from nm.domain import attempts, brief
from nm.domain import summary as matter_memory
from nm.domain.advocate import (
    PASSWORD_RESET_MINUTES,
    SESSION_IDLE_MINUTES,
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
from nm.ports.directory import AccountBusy, AuthenticationUnavailable
from nm.ports.store import StaleWrite

#: How many surfaced cases one round asks the identity index about. Bounded,
#: and the bound is recorded on the adverse search's `target`.
ADVERSE_BOUND = 8

ROOT = Path(__file__).resolve().parents[3]

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


async def unavailable_authentication(_request: Request, _exc: AuthenticationUnavailable):
    return JSONResponse(status_code=503, headers={'Retry-After': '60'}, content={
        'detail': 'Account access is temporarily unavailable. Try again later.'})


app.add_exception_handler(AuthenticationUnavailable, unavailable_authentication)


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
    # P24. INTAKE READINESS, distinct from the turn completing. The web reads
    # this to show whether the file is ready for the task, which a finished turn
    # does not by itself establish (C1 NEVER[4]).
    briefing: dict = {}


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
                # `backend/nm/domain/brief.py`; the client groups and does not judge.
                "section": brief.section_of(e).value,
            }
            for e in answer.elements
        ],
        metrics=output.metrics.as_served(),
        replayed=output.replayed,
        committed=("replayed" if output.replayed else "committed") if receipt
        else "not_committed" if output.matter else "not_applicable",
        input_admitted=receipt.input_admitted if receipt is not None else False,
        matter_version=output.matter.version if output.matter else None,
        briefing=_briefing.block(output.matter),
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


def _client_label(user_agent: str | None) -> str:
    """Coarse client-reported description for recognition, never access authority.

    Do not retain the full header or infer location from it.
    """
    agent = (user_agent or '')[:1024]
    browser = next((name for marker, name in (
        ('Edg/', 'Edge'), ('Firefox/', 'Firefox'), ('Chrome/', 'Chrome'),
        ('Safari/', 'Safari')) if marker in agent), 'Other browser or client')
    platform = next((name for marker, name in (
        ('Android', 'Android'), ('iPhone', 'iPhone'), ('iPad', 'iPad'),
        ('Windows', 'Windows'), ('Macintosh', 'macOS'), ('Linux', 'Linux'))
        if marker in agent), '')
    return f'{browser} on {platform}' if platform else browser


def signed_in(request: Request, nm_session: str | None = Cookie(default=None),
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
    if session is None or application().directory.identity(session.advocate_id) is None:
        raise HTTPException(status_code=401, detail="not signed in")
    request.state.account_session = session
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
    # `signed_in`. That is not a harmless swap: `frontend/app.js` keys its
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
#: The mechanism is not new. `backend/nm/domain/identity.py` already existed (in
#: `tools/`) so a mutation record could not certify code it never saw, and
#: `backend/nm/knowledge/artefact.py` makes the same argument about the dense index:
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


@app.post("/api/dictation", dependencies=[CsrfProtected])
async def transcribe_dictation(request: Request, advocate_id: Advocate) -> dict:
    """SPEECH IN, WORDS OUT, NOTHING KEPT. Implementation Plan F-C-02.

    The advocate's recording is transcribed by this installation's own speech
    model and the words are returned for the brief box, where they are read and
    corrected before anything is sent. The recording is written nowhere: it
    exists in this request and in the model's working memory, and not after.

    REFUSED BEFORE IT IS READ when it is not audio or is too large, and a 503
    that says why when the speech model is not set up -- never empty text, which
    would read as "you said nothing".
    """
    from fastapi.concurrency import run_in_threadpool

    from nm.domain.dictation import DICTATION_MEDIA, MAX_DICTATION_BYTES
    from nm.ports.transcription import DictationUnavailable

    media_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if media_type not in DICTATION_MEDIA:
        raise HTTPException(415, "Dictation takes an audio recording. Nothing was transcribed.")
    audio = bytearray()
    async for chunk in request.stream():
        if len(audio) + len(chunk) > MAX_DICTATION_BYTES:
            raise HTTPException(
                413, "That recording is too long to transcribe at once. Record a shorter part.")
        audio.extend(chunk)
    if not audio:
        raise HTTPException(422, "No audio was received. Nothing was transcribed.")
    try:
        heard = await run_in_threadpool(
            application().transcriber.transcribe, bytes(audio), media_type)
    except DictationUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"text": heard.text, "language": heard.language, "seconds": heard.seconds,
            "device": heard.device, "stored": False}


def _socket_from_this_page(socket: WebSocket) -> bool:
    """The exact-origin rule of `_require_origin`, for a socket.

    `_origins` OWNS THE RULE and is asked here too; only the scheme is
    normalised, because a socket's own base URL is `ws://` or `wss://` while the
    page's `Origin` header is `http://` or `https://`.

    AN ABSENT ORIGIN IS REFUSED. A browser sends it on every WebSocket
    handshake, so its absence means this is not the page (§9: an absent input
    must never read as permission).
    """
    origin = (socket.headers.get("origin") or "").rstrip("/")
    if not origin:
        return False
    trusted = {o.replace("wss://", "https://", 1).replace("ws://", "http://", 1)
               for o in _origins(socket)}
    return origin in trusted


@app.websocket("/ws/dictation")
async def dictation_socket(socket: WebSocket,
                           nm_session: str | None = Cookie(default=None),
                           nm_device: str | None = Cookie(default=None),
                           user_agent: str | None = Header(default=None)) -> None:
    """THE WORDS WHILE THE ADVOCATE IS STILL SPEAKING. Implementation Plan F-C-03.

    Audio arrives as 16 kHz mono frames and the words heard so far go back after
    each one. They are PROVISIONAL: the text the advocate keeps is transcribed
    once, at the end, by `/api/dictation`, and the page replaces these with it.

    IT AUTHENTICATES ITSELF. A socket is not covered by the route-table sweeps
    that prove every `/api` route is authenticated and CSRF-protected, so the
    session cookie is checked here, bound to the device as everywhere else, and
    the handshake's origin is checked by the same rule as an unsafe write --
    which is what a socket has instead of a CSRF header.

    NOTHING IS KEPT. Each frame is fed to the recogniser and dropped; no audio
    is written, and the transcript is not saved by this route.
    """
    from fastapi.concurrency import run_in_threadpool

    from nm.domain.dictation import (
        LIVE_SAMPLE_RATE,
        MAX_LIVE_BYTES,
        MAX_LIVE_FRAME_BYTES,
    )
    from nm.ports.transcription import DictationUnavailable

    session = application().directory.session(
        nm_session or "", _device(nm_device, user_agent), utcnow())
    if session is None or not _socket_from_this_page(socket):
        # REFUSED BEFORE IT IS ACCEPTED, so no audio is ever read from a socket
        # this product has not authenticated.
        await socket.close(code=1008)
        return
    await socket.accept()
    try:
        listening = application().live_dictation.listen(LIVE_SAMPLE_RATE)
    except DictationUnavailable as exc:
        # SAID, NOT SILENT. The page keeps recording for the final transcription
        # and tells the advocate the live words are off.
        await socket.send_json({"live": False, "why": str(exc)})
        await socket.close(code=1011)
        return
    await socket.send_json({"live": True})
    heard = 0
    try:
        while True:
            frame = await socket.receive()
            if frame.get("type") == "websocket.disconnect":
                return
            if frame.get("text") is not None:
                words = await run_in_threadpool(listening.close)
                await socket.send_json({"words": words, "done": True})
                await socket.close()
                return
            audio = frame.get("bytes") or b""
            heard += len(audio)
            if len(audio) > MAX_LIVE_FRAME_BYTES or heard > MAX_LIVE_BYTES:
                await socket.send_json(
                    {"live": False,
                     "why": "That is longer than one dictation may run. What you said is "
                            "still recorded; stop to have it transcribed."})
                await socket.close(code=1009)
                return
            words = await run_in_threadpool(listening.hear, audio)
            await socket.send_json({"words": words})
    except WebSocketDisconnect:
        return
    except DictationUnavailable as exc:
        await socket.send_json({"live": False, "why": str(exc)})
        await socket.close(code=1011)


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
    from nm.domain.opening import recorded_brief

    return {**board_projection(m, _register_of(m)), "opening_brief": recorded_brief(m)}


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
    # THE VERSION THE CORRECTION ROUTE WANTS BACK, so a correction typed
    # against a file that has since moved is refused rather than applied to
    # an entry the advocate was not looking at.
    casefile["version"] = m.version
    return casefile


class PremiseStatement(BaseModel):
    """The advocate stating or correcting one legal premise on a thread. P22.

    A STATED premise outranks the product's inference on the next computation
    and carries who stated it. The kind is one of the three the arithmetic
    cannot establish for itself; the route rejects any other.
    """

    model_config = ConfigDict(extra="forbid")

    statement: NonBlank = Field(min_length=1)
    source: str = ""
    expected_version: int


@app.post("/api/matters/{matter_id}/threads/{thread_id}/premises/{kind}",
          dependencies=[CsrfProtected], status_code=201)
def state_premise(matter_id: str, thread_id: str, kind: str,
                  body: PremiseStatement, advocate_id: Advocate) -> dict:
    """Record a premise the advocate states. BK-65-AC2, P22.

    THE NEXT TURN COMPUTES UNDER IT. This does not recompute the limitation --
    that is the turn's job, on the turn's evidence -- it records the stated
    premise on the thread so the next computation reads it first and, where it
    was CONDITIONAL on an inferred accrual, becomes definitive. The record
    carries who stated it and when, because a premise with no reviewer is the
    `not_assessed` state the cover already distinguishes.
    """
    from dataclasses import replace as _replace

    from nm.core.premise import Kind
    from nm.domain.clock import today as _today

    valid = {k.value for k in Kind}
    if kind not in valid:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_REQUEST",
            "why": f"a premise is one of {sorted(valid)}, not {kind!r}",
            "committed": "not_committed"})
    m = _owned(matter_id, advocate_id)
    if m.version != body.expected_version:
        raise HTTPException(status_code=409, detail={
            "code": "STALE_VERSION",
            "why": (f"this matter moved while you were stating the premise: you "
                    f"were on version {body.expected_version} and it is now at "
                    f"{m.version}"),
            "expected_version": body.expected_version,
            "matter_version": m.version, "committed": "not_committed"})
    thread = m.thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="no such thread on this matter")
    today = _today().isoformat()
    stated = dict(getattr(thread, "premises_stated", {}) or {})
    stated[kind] = {"statement": body.statement.strip(),
                    "source": body.source.strip(), "by": advocate_id, "at": today}
    m = m.with_thread(_replace(thread, premises_stated=stated))
    m = _replace(m, last_activity=today)
    try:
        committed = application().store.commit(m, expected_version=body.expected_version)
    except StaleWrite as exc:
        raise HTTPException(status_code=409, detail={
            "code": "STALE_VERSION", "why": str(exc),
            "committed": "not_committed"}) from exc
    return {"state": "stated", "matter_id": committed.id,
            "version": committed.version, "thread_id": thread_id, "kind": kind,
            "premise": stated[kind]}


class ReliefStatement(BaseModel):
    """The advocate stating what a remedy is worth on a thread. BK-70 / E2.

    A STATED relief is the strong basis: the advocate knows the assets, the
    forum and the cost their client faces. The five coordinates use the
    product's own three-state vocabulary, and an unknown value is REJECTED
    rather than blanked -- the same rule `state_premise` keeps for a premise
    kind. The objective is what the relief is measured against; where the
    advocate does not restate it, the one already on the thread stands.
    """

    model_config = ConfigDict(extra="forbid")

    remedy: NonBlank = Field(min_length=1)
    objective: str = ""
    forum: str = ""
    availability: str = "not_assessed"
    value: str = "not_assessed"
    timing: str = "not_assessed"
    enforceability: str = "not_assessed"
    proportionality: str = "not_assessed"
    reason: str = ""
    source: str = ""
    expected_version: int


@app.post("/api/matters/{matter_id}/threads/{thread_id}/relief",
          dependencies=[CsrfProtected], status_code=201)
def state_relief(matter_id: str, thread_id: str, body: ReliefStatement,
                 advocate_id: Advocate) -> dict:
    """Record a relief the advocate states, and what it is worth. BK-70, E2.

    THE NEXT TURN READS IT FIRST. This does not itself recompute the
    recommendation -- that is the turn's job -- it records a STATED relief on
    the thread so the next turn's relief read treats it as established rather
    than inferring the coordinates. An established shortfall (unavailable,
    hollow, late, unenforceable) then changes the recommendation; a
    disproportionate route is stated alongside, never withheld (E3).
    """
    from dataclasses import replace as _replace

    from nm.core import relief as relief_mod
    from nm.core.premise import Basis
    from nm.domain.clock import today as _today

    coord_types = {
        "availability": relief_mod.Availability, "value": relief_mod.Value,
        "timing": relief_mod.Timing, "enforceability": relief_mod.Enforceability,
        "proportionality": relief_mod.Proportionality,
    }
    coords = {}
    for name, enum in coord_types.items():
        raw = getattr(body, name)
        valid = {e.value for e in enum}
        if raw not in valid:
            raise HTTPException(status_code=422, detail={
                "code": "INVALID_REQUEST",
                "why": f"{name} is one of {sorted(valid)}, not {raw!r}",
                "committed": "not_committed"})
        coords[name] = enum(raw)

    m = _owned(matter_id, advocate_id)
    if m.version != body.expected_version:
        raise HTTPException(status_code=409, detail={
            "code": "STALE_VERSION",
            "why": (f"this matter moved while you were stating the relief: you "
                    f"were on version {body.expected_version} and it is now at "
                    f"{m.version}"),
            "expected_version": body.expected_version,
            "matter_version": m.version, "committed": "not_committed"})
    thread = m.thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="no such thread on this matter")

    stored_obj = relief_mod.Objective.from_stored(getattr(thread, "objective", None))
    objective = body.objective.strip() or (stored_obj.statement if stored_obj else "")
    if not objective:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_REQUEST",
            "why": "a relief needs an objective it is measured against; state "
                   "one, or none is on the thread yet",
            "committed": "not_committed"})

    relief = relief_mod.Relief(
        remedy=body.remedy.strip(), objective=objective,
        forum=body.forum.strip(), basis=Basis.STATED,
        source=(body.source.strip() or "the advocate"),
        reason=(body.reason.strip() or "stated by the advocate"), **coords)

    # REPLACE A PRIOR STATEMENT OF THE SAME REMEDY, keep the rest. The turn's
    # own relief read overwrites this section each turn, so what persists is a
    # statement the next turn reads and then re-expresses as its position.
    kept = [r for r in relief_mod.reliefs_from_stored(getattr(thread, "reliefs", ()))
            if r.remedy != relief.remedy]
    kept.append(relief)
    obj_row = (relief_mod.Objective(objective, basis=Basis.STATED,
                                    source="the advocate").as_dict()
               if body.objective.strip() or stored_obj is None
               else stored_obj.as_dict())
    today = _today().isoformat()
    m = m.with_thread(_replace(
        thread, reliefs=tuple(r.as_dict() for r in kept), objective=obj_row))
    m = _replace(m, last_activity=today)
    try:
        committed = application().store.commit(m, expected_version=body.expected_version)
    except StaleWrite as exc:
        raise HTTPException(status_code=409, detail={
            "code": "STALE_VERSION", "why": str(exc),
            "committed": "not_committed"}) from exc
    return {"state": "stated", "matter_id": committed.id,
            "version": committed.version, "thread_id": thread_id,
            "relief": relief.as_dict(), "objective": obj_row}


class UnavailableNeed(BaseModel):
    """The advocate marking a briefing need they cannot obtain. P24 / C1
    NEVER[4]. The need is paused with a resume trigger -- not answered, not
    re-asked."""

    model_config = ConfigDict(extra="forbid")

    need: NonBlank = Field(min_length=1)
    resume_when: str = ""
    expected_version: int


class ResumeNeed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    need: NonBlank = Field(min_length=1)
    expected_version: int


def _commit_matter(m, expected_version: int):
    try:
        return application().store.commit(m, expected_version=expected_version)
    except StaleWrite as exc:
        raise HTTPException(status_code=409, detail={
            "code": "STALE_VERSION", "why": str(exc),
            "committed": "not_committed"}) from exc


@app.post("/api/matters/{matter_id}/briefing/unavailable",
          dependencies=[CsrfProtected], status_code=201)
def mark_need_unavailable(matter_id: str, body: UnavailableNeed,
                          advocate_id: Advocate) -> dict:
    """Pause a need the advocate cannot obtain. BK-54-AC3 / C1 NEVER[4].

    It is NOT recorded as answered -- intake stays incomplete on it -- and it is
    NOT re-asked; it waits for its resume trigger. This is the stop half of the
    stop-or-resume decision the criterion requires instead of an endless loop.
    """
    from nm.domain.clock import today as _today

    m = _owned(matter_id, advocate_id)
    if m.version != body.expected_version:
        raise HTTPException(status_code=409, detail={
            "code": "STALE_VERSION", "matter_version": m.version,
            "why": "this matter moved while you marked a need unavailable",
            "committed": "not_committed"})
    today = _today().isoformat()
    m = m.pause_need(body.need.strip(), body.resume_when, by=advocate_id, at=today)
    committed = _commit_matter(m, body.expected_version)
    return {"state": "paused", "matter_id": committed.id,
            "version": committed.version, "need": body.need.strip(),
            "resume_when": body.resume_when.strip() or "new material arrives"}


@app.post("/api/matters/{matter_id}/briefing/resume",
          dependencies=[CsrfProtected], status_code=201)
def resume_need(matter_id: str, body: ResumeNeed, advocate_id: Advocate) -> dict:
    """Reopen a paused need -- material or an instruction arrived. It becomes an
    ordinary gap again, asked at the smallest useful moment."""
    m = _owned(matter_id, advocate_id)
    if m.version != body.expected_version:
        raise HTTPException(status_code=409, detail={
            "code": "STALE_VERSION", "matter_version": m.version,
            "why": "this matter moved while you resumed a need",
            "committed": "not_committed"})
    m = m.resume_need(body.need.strip())
    committed = _commit_matter(m, body.expected_version)
    return {"state": "resumed", "matter_id": committed.id,
            "version": committed.version, "need": body.need.strip()}


class RetentionAsset(BaseModel):
    """One asset at one version. `VersionRef` in the served contract."""

    model_config = ConfigDict(extra="forbid")

    id: NonBlank = Field(min_length=1)
    version: int = Field(ge=0)


class RetentionCopy(BaseModel):
    """One place a copy is known to live, declared by the inventory.

    `kind` decides which retained-reason code an unresolved copy produces --
    `processor` and `backup` are the two the contract names separately, because
    "our processor still has it" and "a backup still has it" are different
    things to tell a client.
    """

    model_config = ConfigDict(extra="forbid")

    location: NonBlank = Field(min_length=1)
    kind: Literal["derivative", "processor", "backup", "original"] = "derivative"


class RetentionRequestBody(BaseModel):
    """`create-retention-request`. The body is closed and the actor is not in it.

    NO CLIENT-SUPPLIED STATE OR HOLD OVERRIDE, which the contract states as a
    semantic refusal and `extra="forbid"` enforces structurally: a caller that
    could post `state` could post `complete_for_declared_scope` and have the
    product tell the next reader the material is gone.
    """

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    scope: Literal["selected_assets", "matter_lifecycle_review"]
    asset_versions: list[RetentionAsset] = Field(default_factory=list, max_length=100)
    requested_action: Literal["restrict_access", "review_retention", "erase"]
    purpose: NonBlank = Field(min_length=1, max_length=4000)
    authority_id: NonBlank = Field(min_length=1)
    authority_version: int = Field(ge=0)
    copies: list[RetentionCopy] = Field(default_factory=list, max_length=200)
    expected_matter_version: int


@app.post("/api/retention-requests", dependencies=[CsrfProtected],
          status_code=201)
def create_retention_request(body: RetentionRequestBody,
                             advocate_id: Advocate) -> dict:
    """Receive a retention request. BK-85-AC4, BK-88-AC1. P33.

    IT RETURNS `review_requested` AND NOTHING ELSE, on every path. The contract
    says a receipt never means erased, and the way that is kept true is that
    this route has no way to say anything else: `retention.request` does not
    take a state, and every later state is reached through the transition rule.

    A request naming assets under an active hold is still RECEIVED. Refusing it
    outright would leave the person asking with no record that they asked and
    no statement of why the material is being kept -- the hold shows up as the
    state and the reason code, which is the answer they are entitled to.
    """
    from nm.core import retention as rt
    from nm.domain import retention as rd
    from nm.domain.clock import today as _today

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    now = _today().isoformat()

    try:
        made = rd.request(
            request_id=f"rr_{uuid.uuid4().hex[:12]}",
            matter_id=m.id, requested_by=advocate_id, requested_at=now,
            scope=rd.RequestScope(body.scope),
            requested_action=rd.RequestedAction(body.requested_action),
            purpose=body.purpose.strip(),
            authority_id=body.authority_id.strip(),
            authority_version=body.authority_version,
            assets=tuple(rd.AssetRef(id=a.id.strip(), version=a.version)
                         for a in body.asset_versions),
            copies=tuple(rd.Copy(location=c.location.strip(), kind=c.kind)
                         for c in body.copies),
            next_review_at=now)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_REQUEST", "why": str(exc),
            "committed": "not_committed"}) from exc

    existing = rt.rows(m)
    m = replace(m, retention=tuple(rt.as_dict(r) for r in rt.put(existing, made)),
                version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"request_id": made.request_id, "observed_at": now,
            "persistence": "committed", "state": made.state.value,
            "data": rt.projection(made), "operation_id": made.request_id,
            "matter_version": committed.version}


@app.get("/api/retention-requests/{retention_request_id}")
def get_retention_request(retention_request_id: str, matter_id: str,
                          advocate_id: Advocate) -> dict:
    """Read one retention request. BK-85-AC4, BK-88-AC1. P33.

    WHAT IS STILL RETAINED IS SAID, NOT IMPLIED. The contract's semantic
    refusal is that an incomplete processor or backup inventory cannot return
    `complete_for_declared_scope`, and `completion_problems` is served beside
    the state so the advocate is told WHICH copy is outstanding rather than
    being left to infer it from a count that does not add up.
    """
    from nm.core import retention as rt

    m = _owned(matter_id, advocate_id)
    found = rt.find(rt.rows(m), retention_request_id)
    if found is None:
        raise HTTPException(status_code=404, detail="no such retention request")
    return {"data": rt.projection(found),
            "outstanding": list(found.completion_problems()),
            "holds": [{"hold_id": h.hold_id, "reason": h.reason,
                       "active": h.is_active} for h in found.holds],
            "tombstones": [{"asset_id": t.asset_id, "erased_at": t.erased_at}
                           for t in found.tombstones]}


class HoldBody(BaseModel):
    """Place a hold. The reason is required and is shown to whoever asks why
    material was kept -- an unexplained hold is indistinguishable from a bug."""

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    reason: NonBlank = Field(min_length=1, max_length=2000)
    expected_matter_version: int


class ReleaseHoldBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    hold_id: NonBlank = Field(min_length=1)
    expected_matter_version: int


class ResolveCopyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    location: NonBlank = Field(min_length=1)
    expected_matter_version: int


class AdvanceBody(BaseModel):
    """Move a request. The target is named; the route does not infer it.

    A route that advanced "to the next state" would decide the lifecycle for
    the caller, and the one place that must not happen is the step into
    erasure.
    """

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    target: Literal["under_hold", "approved", "in_progress",
                    "erased_from_active_systems", "backup_expiry_pending",
                    "complete_for_declared_scope", "declined",
                    "review_requested"]
    expected_matter_version: int


class RestoreCheckBody(BaseModel):
    """What a restore proposes to bring back, before it brings any of it back."""

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    asset_ids: list[str] = Field(min_length=1, max_length=500)


def _retention_or_404(m, request_id: str):
    from nm.core import retention as rt
    found = rt.find(rt.rows(m), request_id)
    if found is None:
        raise HTTPException(status_code=404, detail="no such retention request")
    return found


def _save_retention(m, updated, expected_version: int) -> dict:
    from nm.core import retention as rt
    rows = rt.put(rt.rows(m), updated)
    m = replace(m, retention=tuple(rt.as_dict(r) for r in rows),
                version=m.version + 1)
    committed = _commit_matter(m, expected_version)
    return {"matter_id": committed.id, "version": committed.version,
            "data": rt.projection(updated),
            "outstanding": list(updated.completion_problems())}


@app.post("/api/retention-requests/{retention_request_id}/holds",
          dependencies=[CsrfProtected], status_code=201)
def place_retention_hold(retention_request_id: str, body: HoldBody,
                         advocate_id: Advocate) -> dict:
    """Place a hold. BK-85-AC4, BK-88-AC1. P33.

    The material stays. An erasure already approved stops here rather than
    completing and being reported as done.
    """
    import uuid as _uuid

    from nm.core import retention as rt
    from nm.domain import retention as rd
    from nm.domain.clock import today as _today

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    found = _retention_or_404(m, retention_request_id)
    hold = rd.Hold(hold_id=f"hold_{_uuid.uuid4().hex[:8]}",
                   reason=body.reason.strip(), placed_by=advocate_id,
                   placed_at=_today().isoformat())
    return _save_retention(m, rt.place_hold(found, hold),
                           body.expected_matter_version)


@app.post("/api/retention-requests/{retention_request_id}/hold-releases",
          dependencies=[CsrfProtected], status_code=201)
def release_retention_hold(retention_request_id: str, body: ReleaseHoldBody,
                           advocate_id: Advocate) -> dict:
    """Release one hold BY NAME. It does not resume the interrupted work."""
    from nm.core import retention as rt
    from nm.domain.clock import today as _today

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    found = _retention_or_404(m, retention_request_id)
    try:
        updated = rt.release_hold(found, body.hold_id.strip(),
                                  by=advocate_id, at=_today().isoformat())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_REQUEST", "why": str(exc),
            "committed": "not_committed"}) from exc
    return _save_retention(m, updated, body.expected_matter_version)


@app.post("/api/retention-requests/{retention_request_id}/resolved-copies",
          dependencies=[CsrfProtected], status_code=201)
def resolve_retention_copy(retention_request_id: str, body: ResolveCopyBody,
                           advocate_id: Advocate) -> dict:
    """Account for ONE inventoried copy. There is deliberately no bulk form."""
    from nm.core import retention as rt
    from nm.domain.clock import today as _today

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    found = _retention_or_404(m, retention_request_id)
    try:
        updated = rt.resolve_copy(found, body.location.strip(),
                                  at=_today().isoformat())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_REQUEST", "why": str(exc),
            "committed": "not_committed"}) from exc
    return _save_retention(m, updated, body.expected_matter_version)


@app.post("/api/retention-requests/{retention_request_id}/transitions",
          dependencies=[CsrfProtected], status_code=201)
def advance_retention_request(retention_request_id: str, body: AdvanceBody,
                              advocate_id: Advocate) -> dict:
    """Move a request through its lifecycle. THE TABLE DECIDES, NOT THE CALLER.

    A refused move returns 409 with the reason the domain gave, and the codes
    are the contract's: `RETENTION_HOLD` where a hold is what refuses, and
    `INVALID_TRANSITION` where the lifecycle does. They are told apart because
    they need different actions -- one waits for a release, the other is a
    mistake about where the request had got to.
    """
    from nm.core import retention as rt
    from nm.domain import retention as rd
    from nm.domain.clock import today as _today

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    found = _retention_or_404(m, retention_request_id)
    target = rd.RetentionState(body.target)

    refused = rd.refuse_transition(found, target)
    if refused:
        raise HTTPException(status_code=409, detail={
            "code": ("RETENTION_HOLD" if "hold" in refused.lower()
                     else "INVALID_TRANSITION"),
            "why": refused, "state": found.state.value,
            "outstanding": list(found.completion_problems()),
            "committed": "not_committed"})

    if target is rd.RetentionState.ERASED_FROM_ACTIVE_SYSTEMS:
        updated = rt.erase_from_active_systems(found, at=_today().isoformat())
    else:
        updated = rd.advance(found, target)
    return _save_retention(m, updated, body.expected_matter_version)


@app.post("/api/restore-checks", dependencies=[CsrfProtected], status_code=200)
def check_restore(body: RestoreCheckBody, advocate_id: Advocate) -> dict:
    """REPLAY THE TOMBSTONES BEFORE A RESTORE EXPOSES ANYTHING. BK-88-AC1.

    A backup predates the erasure that followed it, so restoring it re-exposes
    exactly the material somebody was told was gone -- and it looks like a
    successful recovery while it does. This is asked BEFORE the restore, and it
    answers with the assets that must not come back and why.
    """
    from nm.core import retention as rt

    m = _owned(body.matter_id, advocate_id)
    refused = rt.refuse_restore(rt.rows(m), tuple(body.asset_ids))
    return {"matter_id": m.id, "proposed": list(body.asset_ids),
            "refused": list(refused),
            "may_restore": [a for a in body.asset_ids if a not in refused],
            "why": ("these were erased under a completed retention request and "
                    "a backup taken before it does not know that"
                    if refused else "nothing proposed has been erased")}


class AdviceDecisionBody(BaseModel):
    """Record what was decided about a piece of advice. BK-55-AC3. P27.

    `disposition` is closed to the four the criterion names plus nothing:
    there is no "approve for filing" here, because this record does not
    authorise an external act and a value that sounded like it did would be
    read as one.
    """

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    disposition: Literal["accept", "reject", "narrow", "defer"]
    advice_version: NonBlank = Field(min_length=1)
    scope: NonBlank = Field(min_length=1, max_length=2000)
    owner: NonBlank = Field(min_length=1)
    review_trigger: NonBlank = Field(min_length=1, max_length=2000)
    narrowed_to: str = ""
    because: str = ""
    expected_matter_version: int


@app.post("/api/advice-decisions", dependencies=[CsrfProtected],
          status_code=201)
def record_advice_decision(body: AdviceDecisionBody,
                           advocate_id: Advocate) -> dict:
    """Record an accept / reject / narrow / defer. BK-55-AC3. P27.

    THE ACTOR IS SERVER-DERIVED. `decided_by` is the signed-in advocate and is
    not in the body: a caller that could name its own decider could record the
    client as having accepted advice the client never saw.

    The response carries `authority_note` on every path, so the thing this
    record does NOT do arrives with it rather than being inferred from silence.
    """
    import uuid as _uuid

    from nm.core import options as op
    from nm.domain import advice_decision as ad
    from nm.domain.clock import today as _today

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)

    decision = ad.AdviceDecision(
        decision_id=f"dec_{_uuid.uuid4().hex[:10]}",
        disposition=ad.Disposition(body.disposition),
        decided_by=advocate_id, decided_at=_today().isoformat(),
        advice_version=body.advice_version.strip(),
        scope=body.scope.strip(), owner=body.owner.strip(),
        review_trigger=body.review_trigger.strip(),
        narrowed_to=body.narrowed_to.strip(), because=body.because.strip())

    missing = decision.absent()
    if missing:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_REQUEST",
            "why": "the decision does not record: " + "; ".join(missing),
            "committed": "not_committed"})

    rows = op.put_decision(op.decision_rows(m), decision)
    m = replace(m, advice_decisions=tuple(op.decision_as_dict(d) for d in rows),
                version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": "recorded", "matter_id": committed.id,
            "version": committed.version,
            "decision": op.decision_projection(decision)}


@app.get("/api/matters/{matter_id}/advice-decisions")
def list_advice_decisions(matter_id: str, advocate_id: Advocate) -> dict:
    """Every decision on this matter, current and superseded.

    SUPERSEDED ONES ARE RETURNED TOO. Authority is withdrawn by a later record
    and never by deletion, so the history is what lets an advocate answer
    *when did we decide that, and against which advice*.
    """
    from nm.core import options as op

    m = _owned(matter_id, advocate_id)
    rows = op.decision_rows(m)
    return {"matter_id": m.id, "version": m.version,
            "decisions": [op.decision_projection(d) for d in rows],
            "current": [op.decision_projection(d) for d in rows if d.is_current]}


class ComparisonFigure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""
    certainty: Literal["established", "estimate", "unknown"] = "unknown"
    basis: str = ""


class ComparisonOption(BaseModel):
    """One route in the comparison. Figures carry their certainty."""

    model_config = ConfigDict(extra="forbid")

    route: Literal["litigate", "arbitrate", "negotiate", "settle",
                   "statutory_remedy", "do_nothing", "other"]
    summary: NonBlank = Field(min_length=1, max_length=2000)
    objective_fit: str = ""
    useful_recovery: ComparisonFigure = Field(default_factory=ComparisonFigure)
    cost: ComparisonFigure = Field(default_factory=ComparisonFigure)
    time: ComparisonFigure = Field(default_factory=ComparisonFigure)
    disruption: ComparisonFigure = Field(default_factory=ComparisonFigure)
    enforceability: ComparisonFigure = Field(default_factory=ComparisonFigure)
    proportionate: bool | None = None
    adverse: list[str] = Field(default_factory=list)
    why_it_loses: str = ""


class ComparisonBody(BaseModel):
    """Record a comparison of routes with the view taken. BK-96-AC1. P27."""

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    thread_id: NonBlank = Field(min_length=1)
    options: list[ComparisonOption] = Field(min_length=1, max_length=20)
    supported: str = ""
    because: str = ""
    no_view_because: str = ""
    expected_matter_version: int


@app.post("/api/comparisons", dependencies=[CsrfProtected], status_code=201)
def record_comparison(body: ComparisonBody, advocate_id: Advocate) -> dict:
    """Record a route comparison. BK-96-AC1. P27.

    THE PROBLEMS TRAVEL WITH IT. A comparison with no view and no reason, an
    unexplained loser, or a figure recorded as established with nothing behind
    it is stored and served WITH those problems named -- not silently smoothed
    into a tidy table. The reader is the person who would otherwise repeat the
    number to a client.
    """
    from nm.core import options as op
    from nm.domain import options as od

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)

    options = tuple(
        od.Option(
            route=od.Route(o.route), summary=o.summary.strip(),
            objective_fit=o.objective_fit.strip(),
            useful_recovery=od.Figure(text=o.useful_recovery.text,
                                      certainty=od.Certainty(o.useful_recovery.certainty),
                                      basis=o.useful_recovery.basis),
            cost=od.Figure(text=o.cost.text,
                           certainty=od.Certainty(o.cost.certainty),
                           basis=o.cost.basis),
            time=od.Figure(text=o.time.text,
                           certainty=od.Certainty(o.time.certainty),
                           basis=o.time.basis),
            disruption=od.Figure(text=o.disruption.text,
                                 certainty=od.Certainty(o.disruption.certainty),
                                 basis=o.disruption.basis),
            enforceability=od.Figure(text=o.enforceability.text,
                                     certainty=od.Certainty(o.enforceability.certainty),
                                     basis=o.enforceability.basis),
            proportionate=o.proportionate,
            adverse=tuple(o.adverse), why_it_loses=o.why_it_loses.strip())
        for o in body.options)

    try:
        comparison = od.compare(
            options,
            supported=od.Route(body.supported) if body.supported else None,
            because=body.because.strip(),
            no_view_because=body.no_view_because.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_REQUEST", "why": str(exc),
            "committed": "not_committed"}) from exc

    rows = dict(getattr(m, "comparisons", {}) or {})
    rows[body.thread_id.strip()] = op.comparison_as_dict(comparison)
    m = replace(m, comparisons=rows, version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": "compared", "matter_id": committed.id,
            "version": committed.version,
            "comparison": op.comparison_projection(comparison)}


@app.get("/api/matters/{matter_id}/comparisons/{thread_id}")
def get_comparison(matter_id: str, thread_id: str,
                   advocate_id: Advocate) -> dict:
    """Read back a recorded comparison, problems included."""
    from nm.core import options as op

    m = _owned(matter_id, advocate_id)
    stored = (getattr(m, "comparisons", {}) or {}).get(thread_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="no comparison on that thread")
    return {"matter_id": m.id, "thread_id": thread_id,
            "comparison": op.comparison_projection(
                op.comparison_from_dict(stored))}


class SourceBindingBody(BaseModel):
    """Attach an admitted source to a dispute. BK-94-AC5. P25.

    `thread_id` is REQUIRED here even though the binding type allows it to be
    empty. The type must be able to express *unbound* -- that is the state an
    admitted document sits in before anybody says. This route is the act of
    saying, so a request that names no thread is not an unbound source, it is
    an incomplete request.
    """

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    source_id: NonBlank = Field(min_length=1)
    source_version: NonBlank = Field(min_length=1)
    thread_id: NonBlank = Field(min_length=1)
    basis: Literal["stated", "inferred"]
    because: str = ""
    expected_matter_version: int


@app.post("/api/source-bindings", dependencies=[CsrfProtected],
          status_code=201)
def bind_source_to_thread(body: SourceBindingBody,
                          advocate_id: Advocate) -> dict:
    """Say which dispute an admitted source belongs to. BK-94-AC5. P25.

    RE-BINDING IS A CORRECTION, NOT AN OVERWRITE. Where a binding already
    exists for this source and version, the previous one is superseded and
    kept, and the response names the thread whose derived work now rests on a
    fact about a different dispute -- so the caller can reopen exactly that
    and nothing else.
    """
    import uuid as _uuid

    from nm.domain import binding as bd
    from nm.domain.clock import today as _today

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    now = _today().isoformat()
    key = f"{body.source_id.strip()}@{body.source_version.strip()}"

    stored = dict(getattr(m, "source_bindings", {}) or {})
    previous_thread = ""
    existing = stored.get(key)
    if existing and existing.get("thread_id") == body.thread_id.strip():
        raise HTTPException(status_code=409, detail={
            "code": "INVALID_TRANSITION",
            "why": (f"{body.source_id.strip()!r} is already attached to "
                    f"{body.thread_id.strip()!r}"),
            "committed": "not_committed"})
    if existing:
        previous_thread = str(existing.get("thread_id") or "")

    fresh = bd.SourceBinding(
        source_id=body.source_id.strip(),
        source_version=body.source_version.strip(),
        thread_id=body.thread_id.strip(), basis=bd.Basis(body.basis),
        bound_by=advocate_id, bound_at=now, because=body.because.strip())

    history = list(stored.get("__superseded__", [])) if isinstance(
        stored.get("__superseded__"), list) else []
    if existing:
        history.append({**existing,
                        "superseded_by": f"bind_{_uuid.uuid4().hex[:8]}",
                        "superseded_at": now})
    stored[key] = {"source_id": fresh.source_id,
                   "source_version": fresh.source_version,
                   "thread_id": fresh.thread_id, "basis": fresh.basis.value,
                   "bound_by": fresh.bound_by, "bound_at": fresh.bound_at,
                   "because": fresh.because}
    stored["__superseded__"] = history

    m = replace(m, source_bindings=stored, version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {
        "state": "bound", "matter_id": committed.id,
        "version": committed.version,
        "binding": {"source_id": fresh.source_id,
                    "source_version": fresh.source_version,
                    "thread_id": fresh.thread_id,
                    "basis": fresh.basis.value,
                    "provisional": fresh.provisional},
        # NAMED SO THE CALLER CAN REOPEN EXACTLY THAT THREAD'S WORK. P28 owns
        # the invalidation; this only says which dispute lost the source.
        "was_attached_to": previous_thread,
        "reopen_note": (
            f"work on {previous_thread!r} rested on this source and no longer "
            f"does" if previous_thread else "this source was not previously "
            "attached to a dispute"),
    }


@app.get("/api/matters/{matter_id}/source-bindings")
def list_source_bindings(matter_id: str, advocate_id: Advocate) -> dict:
    """Every binding on this matter, and what each unbound source is blocking.

    THE UNBOUND ONES ARE THE POINT. A list of what is attached tells an
    advocate nothing about the document sitting in the matter contributing
    nothing because nobody has said which dispute it belongs to.
    """
    from nm.domain import binding as bd

    m = _owned(matter_id, advocate_id)
    stored = getattr(m, "source_bindings", {}) or {}
    rows = []
    for key, row in stored.items():
        if key == "__superseded__":
            continue
        made = bd.SourceBinding(
            source_id=str(row.get("source_id") or "?"),
            source_version=str(row.get("source_version") or "?"),
            thread_id=str(row.get("thread_id") or ""),
            basis=bd.Basis(row.get("basis") or "unbound"),
            bound_by=str(row.get("bound_by") or ""),
            bound_at=str(row.get("bound_at") or ""),
            because=str(row.get("because") or ""))
        rows.append({"source_id": made.source_id,
                     "source_version": made.source_version,
                     "thread_id": made.thread_id,
                     "basis": made.basis.value,
                     "provisional": made.provisional,
                     "refused": bd.refuse_contribution(made)})
    return {"matter_id": m.id, "version": m.version, "bindings": rows,
            "superseded": list(stored.get("__superseded__", []) or [])}


class DraftClaim(BaseModel):
    """One material assertion, with where it came from."""

    model_config = ConfigDict(extra="forbid")

    text: NonBlank = Field(min_length=1, max_length=4000)
    provenance: Literal["supplied_text", "extracted_text", "established_fact",
                        "disputed_proposition", "inference", "legal_premise",
                        "unresolved_gap"]
    source_id: str = ""
    locator: str = ""
    source_version: str = ""
    quoted: str = ""
    why_unresolved: str = ""


class DraftingPackageBody(BaseModel):
    """Prepare a drafting package. BK-56-AC1/AC2. P29.

    `verified` IS NOT IN THIS BODY. A caller that could post it could mark its
    own quotations checked, which is the one field the whole packet exists to
    earn -- verification is a pass over the sources, run server-side.
    """

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    document: NonBlank = Field(min_length=1, max_length=200)
    audience: NonBlank = Field(min_length=1, max_length=200)
    purpose: NonBlank = Field(min_length=1, max_length=2000)
    posture: NonBlank = Field(min_length=1, max_length=200)
    cause_title: dict = Field(default_factory=dict)
    theory_sentence: str = ""
    material_facts: list[DraftClaim] = Field(default_factory=list, max_length=200)
    provisions: list[DraftClaim] = Field(default_factory=list, max_length=100)
    authorities: list[DraftClaim] = Field(default_factory=list, max_length=100)
    reliefs: list[str] = Field(default_factory=list, max_length=30)
    proof_positions: list[str] = Field(default_factory=list, max_length=100)
    facts_not_to_plead: list[dict] = Field(default_factory=list, max_length=100)
    arguments_parked: list[dict] = Field(default_factory=list, max_length=100)
    open_gaps: list[dict] = Field(default_factory=list, max_length=100)
    limitation: dict = Field(default_factory=dict)
    adverse: list[str] = Field(default_factory=list, max_length=100)
    reservations: list[str] = Field(default_factory=list, max_length=100)
    missing_instructions: list[str] = Field(default_factory=list, max_length=100)
    advice_version: str = ""
    blanks_permitted: bool = True
    expected_matter_version: int


def _draft_claims(rows) -> tuple:
    from nm.domain.drafting import Claim, Provenance
    return tuple(Claim(
        text=r.text.strip(), provenance=Provenance(r.provenance),
        source_id=r.source_id.strip(), locator=r.locator.strip(),
        source_version=r.source_version.strip(), quoted=r.quoted.strip(),
        why_unresolved=r.why_unresolved.strip()) for r in rows)


@app.post("/api/drafting-packages", dependencies=[CsrfProtected],
          status_code=201)
def prepare_drafting_package(body: DraftingPackageBody,
                             advocate_id: Advocate) -> dict:
    """Assemble and VERIFY a drafting package. BK-56-AC1/AC2/AC3. P29.

    Verification runs here, against the sources this matter actually holds --
    a package whose quotations were marked checked by its own caller would be
    a package that checked nothing. Staleness is read from P27's decisions,
    not recomputed.

    The response carries `filing_note` on every path. CHOICE-09's first-release
    rule is that this product prepares and exports and the ADVOCATE files; the
    sentence saying so travels with the package rather than being somewhere a
    reader might not look.
    """
    import uuid as _uuid

    from nm.core import drafting as dr
    from nm.core import options as op
    from nm.domain.clock import today as _today
    from nm.domain.drafting import DrafterBrief

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)

    brief = DrafterBrief(
        package_id=f"pkg_{_uuid.uuid4().hex[:10]}", matter_id=m.id,
        document=body.document.strip(), audience=body.audience.strip(),
        purpose=body.purpose.strip(), posture=body.posture.strip(),
        cause_title=dict(body.cause_title),
        theory_sentence=body.theory_sentence.strip(),
        material_facts=_draft_claims(body.material_facts),
        provisions=_draft_claims(body.provisions),
        authorities=_draft_claims(body.authorities),
        limitation=dict(body.limitation),
        reliefs=tuple(r.strip() for r in body.reliefs if r.strip()),
        proof_positions=tuple(body.proof_positions),
        facts_not_to_plead=tuple(body.facts_not_to_plead),
        arguments_parked=tuple(body.arguments_parked),
        open_gaps=tuple(body.open_gaps),
        blanks_permitted=body.blanks_permitted,
        adverse=tuple(body.adverse), reservations=tuple(body.reservations),
        missing_instructions=tuple(body.missing_instructions),
        advice_version=body.advice_version.strip())

    # THE SOURCES THIS MATTER HOLDS, not the ones the caller says it holds.
    sources = _matter_sources(m)
    brief = dr.verify(brief, sources)
    brief = replace(brief, stale_dependencies=dr.stale_against(
        brief, op.decision_rows(m)))
    # LOSSLESS IS EARNED. It is true only when every claim the caller sent
    # survived into the package -- never taken from the request.
    sent = len(body.material_facts) + len(body.provisions) + len(body.authorities)
    brief = replace(brief, lossless=(len(brief.claims) == sent))

    packages = dr.put(dr.rows(m), brief)
    m = replace(m, drafting_packages=tuple(dr.as_dict(b) for b in packages),
                version=m.version + 1, last_activity=_today().isoformat())
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": "prepared", "matter_id": committed.id,
            "version": committed.version,
            "package": dr.projection(brief)}


def _matter_sources(matter) -> dict:
    """Locator -> the words actually held there, from this matter's research.

    P21's reliances already carry the quote that was attached and the locator
    it came from, so verification checks the draft against what the advocate
    actually attached rather than against a source list the drafter supplied.
    """
    out: dict = {}
    for row in (getattr(matter, "research", ()) or ()):
        if not isinstance(row, dict):
            continue
        for rel in (row.get("reliances") or ()):
            if isinstance(rel, dict) and rel.get("locator"):
                out[str(rel["locator"])] = str(rel.get("quote") or "")
    return out


@app.get("/api/matters/{matter_id}/drafting-packages/{package_id}")
def get_drafting_package(matter_id: str, package_id: str,
                         advocate_id: Advocate) -> dict:
    """Read one package back, problems included."""
    from nm.core import drafting as dr

    m = _owned(matter_id, advocate_id)
    found = dr.find(dr.rows(m), package_id)
    if found is None:
        raise HTTPException(status_code=404, detail="no such drafting package")
    return {"matter_id": m.id, "package": dr.projection(found)}


@app.get("/api/matters/{matter_id}/drafting-packages/{package_id}/export")
def export_drafting_package(matter_id: str, package_id: str,
                            advocate_id: Advocate) -> dict:
    """The reviewable export. BK-92-AC3.

    It is a READ, not a dispatch: there is no POST here, because there is
    nothing to send. `dispatch_authority` is false in the payload and the
    renditions say `not_built` rather than returning empty bytes that would
    make a parity check pass over nothing.
    """
    from nm.core import drafting as dr

    m = _owned(matter_id, advocate_id)
    found = dr.find(dr.rows(m), package_id)
    if found is None:
        raise HTTPException(status_code=404, detail="no such drafting package")
    return {"matter_id": m.id, "export": dr.export(found)}


class HandoverBody(BaseModel):
    """Offer a matter to a named recipient. BK-58-AC3. P32.

    `state` is absent by design: a caller that could post one could post
    `accepted` and move responsibility onto somebody who never agreed.
    """

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    to_actor: NonBlank = Field(min_length=1)
    next_responsibility: NonBlank = Field(min_length=1, max_length=2000)
    outstanding: list[str] = Field(default_factory=list, max_length=100)
    expected_matter_version: int


class HandoverActBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    because: str = ""
    expected_matter_version: int


class ClosureBody(BaseModel):
    """Close a matter. BK-59-AC2."""

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    retention: str = ""
    work_product: dict = Field(default_factory=dict)
    continuing_obligations: list[dict] = Field(default_factory=list, max_length=100)
    archive: bool = False
    expected_matter_version: int


@app.get("/api/matters/{matter_id}/re-entry")
def matter_re_entry(matter_id: str, advocate_id: Advocate) -> dict:
    """What the advocate needs on coming back. BK-33-AC2.

    ONE MATTER, READ ONCE, through `_owned` -- which returns the same neutral
    404 whether the matter is absent or somebody else's. There is no second
    matter in scope, so there is nothing for another client's material to leak
    from.
    """
    from nm.core import handover as ho

    m = _owned(matter_id, advocate_id)
    return ho.re_entry(m)


@app.post("/api/handovers", dependencies=[CsrfProtected], status_code=201)
def offer_handover(body: HandoverBody, advocate_id: Advocate) -> dict:
    """Offer a matter. IT IS OFFERED, NOT HANDED OVER. BK-58-AC3. P32."""
    import uuid as _uuid

    from nm.core import handover as ho
    from nm.domain.clock import today as _today
    from nm.domain.handover import offer as make_offer

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    summary = replace(ho.summary_of(m),
                      next_responsibility=body.next_responsibility.strip())
    try:
        made = make_offer(
            handover_id=f"ho_{_uuid.uuid4().hex[:10]}", matter_id=m.id,
            from_actor=advocate_id, to_actor=body.to_actor.strip(),
            offered_at=_today().isoformat(), summary=summary,
            outstanding=tuple(body.outstanding))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_REQUEST", "why": str(exc),
            "committed": "not_committed"}) from exc

    rows = ho.put_handover(ho.handover_rows(m), made)
    m = replace(m, handovers=tuple(ho.handover_as_dict(h) for h in rows),
                version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": "offered", "matter_id": committed.id,
            "version": committed.version,
            "handover": ho.handover_projection(made),
            "summary_unassessed": list(summary.unassessed())}


@app.post("/api/handovers/{handover_id}/acceptance",
          dependencies=[CsrfProtected], status_code=201)
def accept_handover(handover_id: str, body: HandoverActBody,
                    advocate_id: Advocate) -> dict:
    """The named recipient takes it. NOBODY ELSE CAN. BK-58-AC3.

    The acceptor is the signed-in advocate and is server-derived. A body that
    could name its own acceptor could move responsibility onto a colleague who
    has not seen the file.

    NOTE ON OWNERSHIP: the matter is still the offeror's to load, so this route
    is reached by the OFFEROR's session in the current product. The recipient
    check is `by != to_actor`, which refuses regardless of whose session it is
    -- the guard is on the identity, not on the route.
    """
    from nm.core import handover as ho
    from nm.domain.clock import today as _today
    from nm.domain.handover import accept as take

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    rows = ho.handover_rows(m)
    found = next((h for h in rows if h.handover_id == handover_id), None)
    if found is None:
        raise HTTPException(status_code=404, detail="no such handover")
    try:
        taken = take(found, by=advocate_id, at=_today().isoformat())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "NOT_PERMITTED", "why": str(exc),
            "committed": "not_committed"}) from exc

    m = replace(m, handovers=tuple(
        ho.handover_as_dict(h) for h in ho.put_handover(rows, taken)),
        version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": "accepted", "matter_id": committed.id,
            "version": committed.version,
            "handover": ho.handover_projection(taken)}


@app.post("/api/handovers/{handover_id}/declination",
          dependencies=[CsrfProtected], status_code=201)
def decline_handover(handover_id: str, body: HandoverActBody,
                     advocate_id: Advocate) -> dict:
    """Refuse it. The work stays where it was and the reason is kept."""
    from nm.core import handover as ho
    from nm.domain.handover import decline as refuse

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    rows = ho.handover_rows(m)
    found = next((h for h in rows if h.handover_id == handover_id), None)
    if found is None:
        raise HTTPException(status_code=404, detail="no such handover")
    try:
        refused = refuse(found, by=advocate_id, because=body.because.strip())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "NOT_PERMITTED", "why": str(exc),
            "committed": "not_committed"}) from exc

    m = replace(m, handovers=tuple(
        ho.handover_as_dict(h) for h in ho.put_handover(rows, refused)),
        version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": "declined", "matter_id": committed.id,
            "version": committed.version,
            "handover": ho.handover_projection(refused)}


@app.post("/api/matters/{matter_id}/closure", dependencies=[CsrfProtected],
          status_code=201)
def close_matter(matter_id: str, body: ClosureBody,
                 advocate_id: Advocate) -> dict:
    """Close or archive a matter. BK-59-AC2, BK-59-AC3.

    IT REFUSES WHILE ANYTHING IS STILL OWED, and names what. Archiving is a
    SEPARATE lifecycle value from closing and neither is deletion -- what
    happens to the material is P33's retention request, named here and decided
    there.
    """
    from nm.core import handover as ho
    from nm.domain.clock import today as _today
    from nm.domain.closure import ClosureRecord, Lifecycle, Obligation

    m = _owned(matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    record = ClosureRecord(
        matter=m.id, closed_by=advocate_id, closed_at=_today().isoformat(),
        retention=body.retention.strip(),
        work_product=dict(body.work_product),
        continuing_obligations=tuple(
            Obligation(what=str(o.get("what") or "?"),
                       until=str(o.get("until") or ""),
                       owner=str(o.get("owner") or ""),
                       resolved=bool(o.get("resolved")),
                       transferred_to=str(o.get("transferred_to") or ""))
            for o in body.continuing_obligations),
        lifecycle=Lifecycle.ARCHIVED if body.archive else Lifecycle.CLOSED)

    if record.blockers:
        raise HTTPException(status_code=409, detail={
            "code": "INVALID_TRANSITION",
            "why": "this matter has work still owed",
            "blockers": list(record.blockers),
            "committed": "not_committed"})

    committed = _commit_matter(ho.with_closure(m, record),
                               body.expected_matter_version)
    return {"state": record.lifecycle.value, "matter_id": committed.id,
            "version": committed.version,
            "closure": ho.closure_projection(record)}


@app.post("/api/matters/{matter_id}/reopening", dependencies=[CsrfProtected],
          status_code=201)
def reopen_matter(matter_id: str, body: HandoverActBody,
                  advocate_id: Advocate) -> dict:
    """Reopen a closed matter, WITH the list of what must be re-established.

    BK-59-AC3. It does not refuse: a matter reopens because something happened,
    and refusing until the checks pass would leave the advocate unable to act
    on the development that made them reopen it.
    """
    from dataclasses import replace as _replace

    from nm.core import handover as ho
    from nm.domain.closure import Lifecycle, reopen_checks

    m = _owned(matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    closed = ho.closure_of(m)
    if closed is None or closed.lifecycle.is_live:
        raise HTTPException(status_code=409, detail={
            "code": "INVALID_TRANSITION",
            "why": "this matter is not closed",
            "committed": "not_committed"})

    checks = reopen_checks(closed)
    reopened = _replace(closed, lifecycle=Lifecycle.REOPENED)
    committed = _commit_matter(ho.with_closure(m, reopened),
                               body.expected_matter_version)
    return {"state": "reopened", "matter_id": committed.id,
            "version": committed.version,
            "recheck_before_working": list(checks),
            "closure": ho.closure_projection(reopened)}


class EventBody(BaseModel):
    """A material order, hearing, payment or instruction. BK-59-AC1. P32."""

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    kind: Literal["order", "hearing", "payment", "instruction"]
    event_id: NonBlank = Field(min_length=1)
    what: NonBlank = Field(min_length=1, max_length=2000)
    expected_matter_version: int


@app.post("/api/matters/{matter_id}/events", dependencies=[CsrfProtected],
          status_code=201)
def record_matter_event(matter_id: str, body: EventBody,
                        advocate_id: Advocate) -> dict:
    """Record a material event and reopen exactly what it reached. BK-59-AC1.

    THE PAST IS NOT REWRITTEN. That is P18's guarantee, inherited rather than
    restated: `invalidate` keeps the prior value as a `Revision` and touches
    nothing outside the closure a change actually reaches. The event is
    attributed to the advocate who recorded it and versioned by the matter.
    """
    from nm.core import dependency
    from nm.core import handover as ho
    from nm.domain.clock import today as _today

    m = _owned(matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    ledger = dependency.Ledger.from_stored(m.dependencies)
    ledger, reached = ho.record_event(
        ledger, kind=body.kind, event_id=body.event_id.strip(),
        reason=f"{body.kind} recorded by {advocate_id}: {body.what.strip()}",
        at=_today().isoformat())

    m = replace(m, dependencies=ledger.as_dict(), version=m.version + 1,
                last_activity=_today().isoformat())
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": "recorded", "matter_id": committed.id,
            "version": committed.version, "kind": body.kind,
            "event_id": body.event_id.strip(), "by": advocate_id,
            "reopened": list(reached),
            "note": (f"{len(reached)} conclusion(s) rested on this and are "
                     f"reopened; everything else is untouched")}


class ActionProposalBody(BaseModel):
    """Propose a consequential act. BK-56-AC4. P30.

    `state` and `receipt` are absent by design: a caller that could post
    either could report an action delivered that nobody performed.
    """

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    package_id: NonBlank = Field(min_length=1)
    authority: NonBlank = Field(min_length=1, max_length=500)
    object: NonBlank = Field(min_length=1, max_length=500)
    destination: NonBlank = Field(min_length=1, max_length=500)
    expected_matter_version: int


class ConfirmActionBody(BaseModel):
    """Confirm EXACT content. The digest is the caller's statement of what
    they read, and it is compared -- not trusted."""

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    content_digest: NonBlank = Field(min_length=1)
    expected_matter_version: int


class OutcomeBody(BaseModel):
    """What the ADVOCATE found out after filing or sending it themselves.

    `delivered` is not a boolean here. The state is named, and DELIVERED
    without a receipt is refused by the domain.
    """

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    state: Literal["delivery_unknown", "delivered", "refused", "cancelled"]
    receipt: str = ""
    because: str = ""
    expected_matter_version: int


class ReconcileBody(BaseModel):
    """Look again at an unknown outcome.

    THERE IS NO `success` FIELD, and that is the contract's own words: *user
    cannot submit success=true*. A receipt is evidence; a person's belief that
    it arrived is not.

    AND IT IS NOT CALLED `evidence`. `evidence` already names a PORT in this
    product, and `tests/test_every_evidence_adapter_answers_the_whole_port.py`
    reads every `x.evidence.y` in `backend/nm/` as a call against that port -- which is
    the right breadth for a guard whose absence once served a 500. A second
    owner of the word is the thing to remove, not the check that found it, so
    the field is `basis`: what the advocate looked at.
    """

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    basis: NonBlank = Field(min_length=1, max_length=2000)
    receipt: str = ""
    expected_matter_version: int


@app.post("/api/action-proposals", dependencies=[CsrfProtected],
          status_code=201)
def create_action_proposal(body: ActionProposalBody,
                           advocate_id: Advocate) -> dict:
    """Propose a consequential act against an exported drafting package.

    THE DIGEST COMES FROM THE PACKAGE, not from the caller. An approval is for
    exact bytes, and letting the proposer state which bytes would make the
    approval meaningless.
    """
    import uuid as _uuid

    from nm.core import action as ac
    from nm.core import drafting as dr
    from nm.domain.action import ActionProposal

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    package = dr.find(dr.rows(m), body.package_id.strip())
    if package is None:
        raise HTTPException(status_code=404, detail="no such drafting package")

    made = ActionProposal(
        proposal_id=f"ap_{_uuid.uuid4().hex[:10]}", matter_id=m.id,
        package_id=package.package_id, actor=advocate_id,
        authority=body.authority.strip(), object=body.object.strip(),
        destination=body.destination.strip(),
        content_digest=dr.export(package)["content_digest"])

    rows = ac.put(ac.rows(m), made)
    m = replace(m, action_proposals=tuple(ac.as_dict(a) for a in rows),
                version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": "prepared", "matter_id": committed.id,
            "version": committed.version, "proposal": ac.projection(made)}


@app.post("/api/action-proposals/{proposal_id}/confirmation",
          dependencies=[CsrfProtected], status_code=201)
def confirm_action(proposal_id: str, body: ConfirmActionBody,
                   advocate_id: Advocate) -> dict:
    """An authorised actor approves exact content. BK-56-AC4."""
    from nm.core import action as ac
    from nm.domain.action import confirm
    from nm.domain.clock import today as _today

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    rows = ac.rows(m)
    found = next((a for a in rows if a.proposal_id == proposal_id), None)
    if found is None:
        raise HTTPException(status_code=404, detail="no such action proposal")
    try:
        done = confirm(found, by=advocate_id, at=_today().isoformat(),
                       digest=body.content_digest.strip())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "PRECONDITION_REQUIRED", "why": str(exc),
            "committed": "not_committed"}) from exc

    m = replace(m, action_proposals=tuple(
        ac.as_dict(a) for a in ac.put(rows, done)), version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": "approved", "matter_id": committed.id,
            "version": committed.version, "proposal": ac.projection(done)}


@app.post("/api/action-proposals/{proposal_id}/execution",
          dependencies=[CsrfProtected], status_code=409)
def execute_action(proposal_id: str, body: ConfirmActionBody,
                   advocate_id: Advocate) -> dict:
    """THE DISPATCH ROUTE, AND IT ALWAYS REFUSES. CHOICE-09.

    It exists so the answer is a stated refusal with a reason rather than a
    404 somebody reads as "not built yet" -- and so the refusal is a served,
    tested behaviour rather than an absence. `CONNECTOR_DISABLED` is the
    contract's own error code for exactly this.

    The declared status is 409: there is no path through this function that
    succeeds while `CONNECTOR_ENABLED` is False.
    """
    from nm.core import action as ac
    from nm.domain.action import refuse_dispatch

    m = _owned(body.matter_id, advocate_id)
    rows = ac.rows(m)
    found = next((a for a in rows if a.proposal_id == proposal_id), None)
    if found is None:
        raise HTTPException(status_code=404, detail="no such action proposal")
    raise HTTPException(status_code=409, detail={
        "code": "CONNECTOR_DISABLED", "why": refuse_dispatch(found),
        "state": found.state.value, "committed": "not_committed"})


@app.post("/api/action-proposals/{proposal_id}/outcome",
          dependencies=[CsrfProtected], status_code=201)
def record_action_outcome(proposal_id: str, body: OutcomeBody,
                          advocate_id: Advocate) -> dict:
    """Record what the advocate found out. CHOICE-09's manual receipt capture."""
    from nm.core import action as ac
    from nm.domain.action import ActionState, export, record_outcome
    from nm.domain.clock import today as _today

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    rows = ac.rows(m)
    found = next((a for a in rows if a.proposal_id == proposal_id), None)
    if found is None:
        raise HTTPException(status_code=404, detail="no such action proposal")
    if found.state is ActionState.APPROVED:
        found = export(found)
    try:
        done = record_outcome(found, state=ActionState(body.state),
                              receipt=body.receipt.strip(),
                              because=body.because.strip(),
                              at=_today().isoformat())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_REQUEST", "why": str(exc),
            "committed": "not_committed"}) from exc

    m = replace(m, action_proposals=tuple(
        ac.as_dict(a) for a in ac.put(rows, done)), version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": done.state.value, "matter_id": committed.id,
            "version": committed.version, "proposal": ac.projection(done)}


@app.post("/api/action-proposals/{proposal_id}/reconciliation",
          dependencies=[CsrfProtected], status_code=201)
def reconcile_action(proposal_id: str, body: ReconcileBody,
                     advocate_id: Advocate) -> dict:
    """Resolve an unknown outcome on evidence. NO REDISPATCH, NO ASSERTION.

    An inconclusive reconciliation leaves the state exactly where it was and
    records that somebody looked -- *inconclusive remains outcome_unknown*.
    """
    from nm.core import action as ac
    from nm.domain.action import reconcile
    from nm.domain.clock import today as _today

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    rows = ac.rows(m)
    found = next((a for a in rows if a.proposal_id == proposal_id), None)
    if found is None:
        raise HTTPException(status_code=404, detail="no such action proposal")
    try:
        done = reconcile(found, evidence=body.basis.strip(),
                         receipt=body.receipt.strip(), at=_today().isoformat())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "INVALID_TRANSITION", "why": str(exc),
            "committed": "not_committed"}) from exc

    m = replace(m, action_proposals=tuple(
        ac.as_dict(a) for a in ac.put(rows, done)), version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": done.state.value, "matter_id": committed.id,
            "version": committed.version, "proposal": ac.projection(done),
            "resolved": done.state.is_settled}


class HearingPackBody(BaseModel):
    """Assemble preparation from a verified drafting package. BK-57-AC3. P31.

    `readiness` is absent by design: P29 derives it and a caller that could
    post it could declare a pack ready over an unverified package.
    """

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    package_id: NonBlank = Field(min_length=1)
    hard_questions: list[dict] = Field(default_factory=list, max_length=40)
    risk: list[str] = Field(default_factory=list, max_length=40)
    adverse_assessed: bool = False
    """WHETHER ANYBODY LOOKED at the countercase, which is not whether one was
    found. An unexamined countercase and an empty one render differently and
    only one of them is safe."""
    risk_assessed: bool = False
    expected_matter_version: int


class WitnessBody(BaseModel):
    """One witness plan. THERE IS NO FIELD FOR TESTIMONY.

    `topics` are subjects to ask about. A caller cannot post an answer because
    the record has nowhere to put one, and `refuse_scripting` reads the topics
    as a backstop over prose that arrived from a model.
    """

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    witness: NonBlank = Field(min_length=1, max_length=200)
    necessity: str = Field(default="", max_length=2000)
    materiality: list[str] = Field(default_factory=list, max_length=60)
    availability: Literal["confirmed", "expected", "doubtful", "not_assessed"] = "not_assessed"
    interest: str = Field(default="", max_length=2000)
    prior_statements: list[dict] = Field(default_factory=list, max_length=60)
    contradictions: list[dict] = Field(default_factory=list, max_length=60)
    proof_sequence: int = 0
    summons: dict = Field(default_factory=dict)
    interpreter: dict | None = None
    safety: str = Field(default="", max_length=2000)
    logistics_owner: str = Field(default="", max_length=200)
    contact_log: list[dict] = Field(default_factory=list, max_length=100)
    topics: list[str] = Field(default_factory=list, max_length=60)
    credibility: dict = Field(default_factory=dict)
    expected_matter_version: int


class ExpertBody(BaseModel):
    """One expert instruction. THERE IS NO FIELD FOR A CONCLUSION.

    `report` is not settable here either: it arrives when a report arrives, and
    a pack carrying an expert's conclusion before the report exists has
    invented one.
    """

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    expert: NonBlank = Field(min_length=1, max_length=200)
    discipline: str = Field(default="", max_length=200)
    purpose: str = Field(default="", max_length=2000)
    material_supplied: list[str] = Field(default_factory=list, max_length=100)
    material_withheld: list[dict] = Field(default_factory=list, max_length=100)
    assumptions: list[str] = Field(default_factory=list, max_length=60)
    instruction_balanced: bool = False
    independence_statement: str = Field(default="", max_length=2000)
    methodology_tested: Literal["tested", "untested", "not_assessed"] = "not_assessed"
    limitations: list[str] = Field(default_factory=list, max_length=60)
    conflicts: dict = Field(default_factory=dict)
    expected_matter_version: int


class ConcessionCheckBody(BaseModel):
    """ASK WHETHER A CONCESSION IS WITHIN AUTHORITY. It does not make one.

    The act lives at `/api/matters/{id}/concede`, which refuses on the same
    `permits` ruling this reads. Two answers to one question would be worse
    than none, because the advocate would have relied on the permissive one.
    """

    model_config = ConfigDict(extra="forbid")

    proposed: NonBlank = Field(min_length=1, max_length=2000)
    acting_as: str = ""


@app.post("/api/hearing-packs", dependencies=[CsrfProtected], status_code=201)
def create_hearing_pack(body: HearingPackBody, advocate_id: Advocate) -> dict:
    """Assemble preparation from a VERIFIED drafting package. BK-57-AC3.

    The pack is registered in P18's dependency ledger as it is stored, so a
    later order, correction or authority movement reaches it through the paths
    that already exist. Nothing in P31 walks that graph itself.
    """
    import uuid as _uuid

    from nm.core import dependency
    from nm.core import drafting as dr
    from nm.core import hearing as hp
    from nm.domain.clock import today as _today

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    package = dr.find(dr.rows(m), body.package_id.strip())
    if package is None:
        raise HTTPException(status_code=404, detail="no such drafting package")
    commission = Commission.from_stored(m.commission) or Commission()

    try:
        pack = hp.assemble(
            pack_id=f"hp_{_uuid.uuid4().hex[:10]}", brief=package,
            commission=commission, actor_id=advocate_id,
            acting_as=_capacity_of(m, advocate_id, None),
            hard_questions=tuple(body.hard_questions),
            risk=tuple(body.risk),
            adverse_assessed=body.adverse_assessed,
            risk_assessed=body.risk_assessed)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "PRECONDITION_REQUIRED", "why": str(exc),
            "committed": "not_committed"}) from exc

    ledger = hp.record_pack(
        dependency.Ledger.from_stored(m.dependencies), pack,
        at=_today().isoformat(),
        reason=f"assembled from drafting package {pack.package_id}")
    m = replace(m,
                hearing_packs=tuple(hp.as_dict(p) for p in
                                    hp.put(hp.rows(m), pack)),
                dependencies=ledger.as_dict(), version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": "prepared", "matter_id": committed.id,
            "version": committed.version,
            "pack": hp.projection(pack, ledger)}


@app.get("/api/hearing-packs/{pack_id}")
def get_hearing_pack(pack_id: str, matter_id: str,
                     advocate_id: Advocate) -> dict:
    """Read the pack, WITH ITS CURRENCY. BK-57-AC5.

    The ledger is passed so `stale` reads the recorded currency rather than
    the read reporting a pack as current because nothing told it otherwise.
    """
    from nm.core import dependency
    from nm.core import hearing as hp

    m = _owned(matter_id, advocate_id)
    pack = hp.find(hp.rows(m), pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="no such hearing pack")
    ledger = dependency.Ledger.from_stored(m.dependencies)
    return {"matter_id": m.id, "version": m.version,
            "pack": hp.projection(pack, ledger)}


@app.post("/api/hearing-packs/{pack_id}/witnesses",
          dependencies=[CsrfProtected], status_code=201)
def add_witness_plan(pack_id: str, body: WitnessBody,
                     advocate_id: Advocate) -> dict:
    """Add a witness plan. REFUSED IF ANY TOPIC SUPPLIES AN ANSWER. BK-57-AC2.

    A contaminated plan is not stored and then flagged: it is refused, because
    a recollection is contaminated the moment the words reach the witness and
    a warning beside a stored script does not un-say it.
    """
    from nm.core import hearing as hp
    from nm.domain.witness import Availability, WitnessPlan, refuse_scripting

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    pack = hp.find(hp.rows(m), pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="no such hearing pack")

    scripted = refuse_scripting(tuple(body.topics))
    if scripted:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_REQUEST", "why": list(scripted),
            "said": ("Preparation asks a witness what they recall. It does "
                     "not tell them, and this plan was not saved."),
            "committed": "not_committed"})

    plan = WitnessPlan(
        thread=pack.thread or "-", witness=body.witness.strip(),
        necessity=body.necessity.strip(),
        materiality=tuple(body.materiality),
        availability=Availability(body.availability),
        credibility=dict(body.credibility), interest=body.interest.strip(),
        prior_statements=tuple(body.prior_statements),
        contradictions=tuple(body.contradictions),
        proof_sequence=body.proof_sequence, summons=dict(body.summons),
        interpreter=body.interpreter, safety=body.safety.strip(),
        logistics_owner=body.logistics_owner.strip(),
        contact_log=tuple(body.contact_log), topics=tuple(body.topics))

    updated = replace(pack, witnesses=pack.witnesses + (plan,),
                       version=pack.version + 1)
    m = replace(m, hearing_packs=tuple(
        hp.as_dict(p) for p in hp.put(hp.rows(m), updated)),
        version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": "recorded", "matter_id": committed.id,
            "version": committed.version,
            "problems": list(plan.problems()),
            "pack": hp.projection(updated)}


@app.post("/api/hearing-packs/{pack_id}/experts",
          dependencies=[CsrfProtected], status_code=201)
def add_expert_instruction(pack_id: str, body: ExpertBody,
                           advocate_id: Advocate) -> dict:
    """Add an expert instruction. REFUSED IF IT SUPPLIES THE CONCLUSION."""
    from nm.core import hearing as hp
    from nm.domain.witness import (
        ExpertInstruction,
        Methodology,
        refuse_leading,
    )

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    pack = hp.find(hp.rows(m), pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="no such hearing pack")

    leading = refuse_leading((body.purpose,) + tuple(body.assumptions))
    if leading:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_REQUEST", "why": list(leading),
            "said": ("An instruction states the question; the expert states "
                     "the answer. This instruction was not saved."),
            "committed": "not_committed"})

    instruction = ExpertInstruction(
        thread=pack.thread or "-", expert=body.expert.strip(),
        discipline=body.discipline.strip(), purpose=body.purpose.strip(),
        material_supplied=tuple(body.material_supplied),
        material_withheld=tuple(body.material_withheld),
        assumptions=tuple(body.assumptions),
        instruction_balanced=body.instruction_balanced,
        independence_statement=body.independence_statement.strip(),
        methodology_tested=Methodology(body.methodology_tested),
        limitations=tuple(body.limitations), conflicts=dict(body.conflicts),
        report=None)

    updated = replace(pack, experts=pack.experts + (instruction,),
                       version=pack.version + 1)
    m = replace(m, hearing_packs=tuple(
        hp.as_dict(p) for p in hp.put(hp.rows(m), updated)),
        version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": "recorded", "matter_id": committed.id,
            "version": committed.version,
            "problems": list(instruction.problems()),
            "pack": hp.projection(updated)}


@app.get("/api/hearing-packs/{pack_id}/in-court")
def in_court_view(pack_id: str, matter_id: str, advocate_id: Advocate) -> dict:
    """THREE BUCKETS THAT NEVER MERGE, under time pressure. BK-57-AC4.

    Verified material, uncertain analysis and proposed action come back under
    three keys with the concession boundary beside them. A limit on another
    screen is a limit nobody reads at 10:29.
    """
    from nm.core import drafting as dr
    from nm.core import hearing as hp

    m = _owned(matter_id, advocate_id)
    pack = hp.find(hp.rows(m), pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="no such hearing pack")
    package = dr.find(dr.rows(m), pack.package_id)
    if package is None:
        raise HTTPException(status_code=409, detail={
            "code": "PRECONDITION_REQUIRED",
            "why": ("the drafting package this preparation rests on is no "
                    "longer on the file"),
            "committed": "not_committed"})
    shown = hp.in_court(pack, package)
    return {"matter_id": m.id, "version": m.version,
            **{k: list(v) if isinstance(v, tuple) else v
               for k, v in shown.items()}}


@app.post("/api/matters/{matter_id}/concession-check",
          dependencies=[CsrfProtected])
def check_concession(matter_id: str, body: ConcessionCheckBody,
                     advocate_id: Advocate) -> dict:
    """Is this concession within authority? BK-57-AC1. IT MAKES NONE.

    Nothing is written and nothing is given up. The ruling comes from the same
    `permits` the `/concede` route calls, so preparation and the act cannot
    disagree.
    """
    from nm.core import hearing as hp

    m = _owned(matter_id, advocate_id)
    commission = Commission.from_stored(m.commission) or Commission()
    acting_as = _capacity_of(m, advocate_id, body.acting_as or None)
    why = hp.refuse_concession(commission, actor_id=advocate_id,
                               acting_as=acting_as,
                               proposed=body.proposed.strip())
    boundary = hp.concession_boundary(commission, advocate_id, acting_as)
    return {"matter_id": m.id, "version": m.version,
            "within_authority": not why, "why": why,
            "boundary": boundary.render(),
            "said": ("This is a check. No concession has been made and "
                     "nothing was recorded on the file.")}


class ServiceAuthorityBody(BaseModel):
    """Authorise proactive work on a matter. BK-58-AC1. P45.

    THERE IS NO `state` FIELD. A caller that could post `granted` could
    authorise itself, and the whole record exists to say somebody else did.
    """

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    responsible_actor: NonBlank = Field(min_length=1, max_length=200)
    purpose: NonBlank = Field(min_length=1, max_length=2000)
    trigger: Literal["event", "cadence"]
    cadence: str = Field(default="", max_length=200)
    notify: Literal["in_product", "email", "none"]
    expires_on: str = Field(default="", max_length=10)
    expected_matter_version: int


class CancelServiceBody(BaseModel):
    """Withdraw it. The record is kept and the version moves."""

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    because: str = Field(default="", max_length=2000)
    expected_matter_version: int


class ServiceJobBody(BaseModel):
    """Ask for one unit of authorised work to be scheduled.

    `outcome` and `receipt` are absent by design: a caller that could post
    either could report an advocate notified when nobody was.
    """

    model_config = ConfigDict(extra="forbid")

    matter_id: NonBlank = Field(min_length=1)
    kind: Literal["deadline_reminder", "conflict_recheck", "hearing_alert"]
    due_on: NonBlank = Field(min_length=1, max_length=32)
    expected_matter_version: int


@app.post("/api/service-authorities", dependencies=[CsrfProtected],
          status_code=201)
def set_service_authority(body: ServiceAuthorityBody,
                          advocate_id: Advocate) -> dict:
    """Record who authorised proactive work, for what, and what makes it due.

    AUTHORITY TO READ IS NOT AUTHORITY TO ACT. `_owned` establishes that this
    advocate may open the file; `permits(..., Act.RECORD)` establishes that
    they may write on it. Neither is an instruction to monitor it, which is why
    this record exists at all rather than being inferred from membership.
    """
    import uuid as _uuid

    from nm.core import service as sv
    from nm.domain.clock import today as _today
    from nm.domain.service import Notify, Trigger, grant

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    acting_as = _capacity_of(m, advocate_id, None)
    ruling = permits(advocate_id, acting_as, Act.RECORD)
    if not ruling.authorises():
        _record_refusal(m, ruling)
        raise HTTPException(status_code=403, detail={
            "code": "NOT_PERMITTED", "why": ruling.said(),
            "committed": "not_committed"})

    now = _today().isoformat()
    try:
        made = grant(
            authority_id=f"sa_{_uuid.uuid4().hex[:10]}", matter_id=m.id,
            responsible_actor=body.responsible_actor,
            purpose=body.purpose, trigger=Trigger(body.trigger),
            notify=Notify(body.notify), granted_by=advocate_id,
            granted_at=now, cadence=body.cadence,
            expires_on=body.expires_on)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_REQUEST", "why": str(exc),
            "committed": "not_committed"}) from exc

    m = replace(m, service_authorities=tuple(
        sv.authority_as_dict(a) for a in sv.put_authority(
            sv.authorities(m), made)), version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": "authorised", "matter_id": committed.id,
            "version": committed.version,
            "authority": sv.authority_projection(made, now)}


@app.post("/api/service-authorities/{authority_id}/cancellation",
          dependencies=[CsrfProtected], status_code=201)
def cancel_service_authority(authority_id: str, body: CancelServiceBody,
                             advocate_id: Advocate) -> dict:
    """Withdraw the authority AND STOP WHAT IT STARTED. BK-58-AC1.

    Revocation that left running jobs alone would be a cancellation the
    advocate believes in and the queue does not, which is the worst of the
    three possible states.
    """
    from nm.core import service as sv
    from nm.domain.clock import today as _today
    from nm.domain.service import revoke

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    rows = sv.authorities(m)
    found = next((a for a in rows if a.authority_id == authority_id), None)
    if found is None:
        raise HTTPException(status_code=404,
                            detail="no such service authority")
    now = _today().isoformat()
    stopped = revoke(found, by=advocate_id, at=now)
    jobs = sv.revoke_reaches(sv.jobs(m), authority_id=authority_id, at=now)

    m = replace(
        m,
        service_authorities=tuple(sv.authority_as_dict(a) for a in
                                  sv.put_authority(rows, stopped)),
        service_jobs=tuple(sv.job_as_dict(j) for j in jobs),
        version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": "withdrawn", "matter_id": committed.id,
            "version": committed.version,
            "authority": sv.authority_projection(stopped, now),
            "stopped": [j.job_id for j in jobs
                        if j.authority_id == authority_id
                        and not j.outcome.settled()]}


@app.post("/api/service-jobs", dependencies=[CsrfProtected], status_code=201)
def schedule_service_job(body: ServiceJobBody, advocate_id: Advocate) -> dict:
    """Schedule one unit of work, ONCE. BK-58-AC1.

    A REPLAYED DUE EVENT RETURNS THE JOB THAT ALREADY COVERS IT. The
    idempotency key is derived from what the work is about -- matter, kind,
    due date, authority -- so two triggers of one cadence are one job however
    many times the trigger fires.
    """
    import uuid as _uuid

    from nm.core import service as sv
    from nm.domain.clock import today as _today

    m = _owned(body.matter_id, advocate_id)
    _stale(m, body.expected_matter_version)
    now = _today().isoformat()
    authority = sv.current_authority(m, now)
    existing = sv.jobs(m)
    try:
        job = sv.schedule(authority, job_id=f"sj_{_uuid.uuid4().hex[:10]}",
                          kind=body.kind, due_on=body.due_on.strip(),
                          today=now, existing=existing)
    except sv.ServiceRefused as exc:
        raise HTTPException(status_code=409, detail={
            "code": "NOT_AUTHORISED", "why": str(exc),
            "committed": "not_committed"}) from exc

    duplicate = any(j.job_id == job.job_id for j in existing)
    m = replace(m, service_jobs=tuple(
        sv.job_as_dict(j) for j in sv.put_job(existing, job)),
        version=m.version + 1)
    committed = _commit_matter(m, body.expected_matter_version)
    return {"state": "scheduled", "matter_id": committed.id,
            "version": committed.version,
            "job": sv.job_projection(job),
            "already_scheduled": duplicate,
            "said": ("This was already scheduled and has not been scheduled "
                     "again." if duplicate else
                     "Scheduled. It runs when the recorded trigger fires and "
                     "this product is running; it is not continuous "
                     "monitoring.")}


@app.get("/api/matters/{matter_id}/service")
def get_service(matter_id: str, advocate_id: Advocate) -> dict:
    """The proactive work on this matter, and the continuing watch. BK-58.

    THE CONFLICT FINDINGS DO NOT NAME ANOTHER FILE. `watch_report` carries
    `leaks_another_matter`, which is empty on a correct screen and is served
    so that a regression is visible on the page rather than only in a test.
    """
    from nm.core import service as sv
    from nm.domain.clock import today as _today

    m = _owned(matter_id, advocate_id)
    now = _today().isoformat()
    authority = sv.current_authority(m, now)
    return {"matter_id": m.id, "version": m.version,
            "authority": (sv.authority_projection(authority, now)
                          if authority is not None else None),
            "jobs": [sv.job_projection(j) for j in sv.jobs(m)],
            "watch": sv.watch_report(sv.conflict_screen_of(m), authority,
                                     today=now)}


class Correction(BaseModel):
    """One correction to one entry on the case file. BK-65-AC1, P18.

    THE COMPATIBILITY FORM OF `correct-proposition`, whose target route is
    design-only: `proposition n -> n+1 + prior preserved; dependent findings
    stale atomically; unaffected findings retained`. The replacement is a new
    fact; the old one is marked superseded and stays on the file, so the
    advocate can see both and the ledger can see what moved.

    `expected_version` IS REQUIRED. A correction is the one write on this
    surface an advocate composes while looking at a specific entry, and a
    file that moved under them may not hold that entry any more.
    """

    model_config = ConfigDict(extra="forbid")

    statement: str | None = None
    # `on`, ALIASED `date` ON THE WIRE. A field literally named `date` shadows
    # the type inside the class body, and pydantic then evaluates the
    # annotation `date | None` as `None | None` -- a TypeError at import,
    # found by the first test that imported the app.
    on: date | None = Field(default=None, alias="date")
    reason: NonBlank = Field(min_length=1)
    expected_version: int


@app.post("/api/matters/{matter_id}/facts/{fact_id}/corrections",
          dependencies=[CsrfProtected], status_code=201)
def correct_fact(matter_id: str, fact_id: str, body: Correction,
                 advocate_id: Advocate) -> dict:
    """Correct one entry, and invalidate exactly what rested on it. P18.

    ONE MECHANISM WITH THE TURN. The replacement goes through
    `Matter.recording`, the link through `Matter.superseding`, and the
    invalidation through `dependency.sync_inputs` -- the same three the turn
    uses when the advocate speaks a correction into the brief. A correction
    typed here and one spoken there leave the same record and reach the same
    closure, because there is one of each.

    WHAT IS RETURNED IS WHAT MOVED: the affected node names and the ones that
    were left alone, so the advocate -- and the test -- can see that the
    party role survived a corrected date. `history` carries `was`, the
    versions, the reason and who.
    """
    from nm.core import dependency
    from nm.core import options as _options
    from nm.core import reassessment as _reassessment
    from nm.domain.matter import Fact, Provenance
    from nm.edge.projections import currency_projection

    m = _owned(matter_id, advocate_id)
    if m.version != body.expected_version:
        raise HTTPException(status_code=409, detail={
            "code": "STALE_VERSION",
            "why": (f"this matter moved while you were correcting it: you were "
                    f"looking at version {body.expected_version} and it is now "
                    f"at {m.version}. Re-read the entry before correcting it."),
            "expected_version": body.expected_version,
            "matter_version": m.version,
            "committed": "not_committed",
        })
    old = m.fact(fact_id)
    if old is None:
        raise HTTPException(status_code=404, detail="no such entry on this matter")
    if old.superseded_by is not None:
        raise HTTPException(status_code=409, detail={
            "code": "INVALID_TRANSITION",
            "why": (f"entry {fact_id} was already replaced by {old.superseded_by}; "
                    f"correct the current entry, not the withdrawn one"),
            "committed": "not_committed",
        })
    statement = (body.statement or "").strip() or old.statement
    on = body.on if body.on is not None else old.date
    if statement == old.statement and on == old.date:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_REQUEST",
            "why": "the correction changes neither the words nor the date, so "
                   "there is nothing to correct",
            "committed": "not_committed",
        })

    today = forum_today()
    correction_id = f"correction-{m.version + 1}"
    replacement = Fact.create(
        statement=statement,
        provenance=Provenance(kind="advocate_statement", turn=correction_id,
                              span=body.reason.strip()),
        certainty=old.certainty, date=on, material=old.material)
    m, replacement = m.recording(replacement)
    m = m.superseding(old.id, replacement.id)
    # THE REPLACEMENT JOINS EVERY CHRONOLOGY THE ORIGINAL WAS ON, so the
    # next derivation runs from the corrected entry rather than from nothing.
    for thread in m.threads:
        if old.id in thread.chronology and replacement.id not in thread.chronology:
            m = m.with_thread(replace(
                thread, chronology=(*thread.chronology, replacement.id)))

    ledger = dependency.Ledger.from_stored(m.dependencies)
    ledger, affected, moved = dependency.sync_inputs(
        ledger, m, reason=f"corrected by {advocate_id}: {body.reason.strip()}",
        at=today.isoformat())
    m = replace(m, dependencies=ledger.as_dict(),
                last_activity=today.isoformat())

    try:
        committed = application().store.commit(m, expected_version=body.expected_version)
    except StaleWrite as exc:
        raise HTTPException(status_code=409, detail={
            "code": "STALE_VERSION", "why": str(exc),
            "committed": "not_committed"}) from exc

    untouched = tuple(n.name for n in ledger.nodes if n.name not in affected)
    return {
        "state": "corrected",
        "matter_id": committed.id,
        "version": committed.version,
        "fact": {"was": old.id, "now": replacement.id,
                 "was_statement": old.statement,
                 "now_statement": replacement.statement,
                 "was_date": old.date.isoformat() if old.date else None,
                 "now_date": (replacement.date.isoformat()
                              if replacement.date else None)},
        "moved": [r.as_dict() for r in moved],
        "affected": list(affected),
        "unaffected": list(untouched),
        # P28 / BK-55-AC5. A CORRECTION MAKES DEPENDENT DECISIONS STALE TOO,
        # and the dangerous half is not that they go out of date -- it is that
        # they keep saying ACCEPTED beside advice the acceptance was never
        # given for. They are reported, never deleted: the history is what
        # answers *what did we decide, and against which advice*.
        "stale_decisions": [
            {"decision_id": d.decision_id,
             "disposition": d.disposition.value,
             "advice_version": d.advice_version,
             "why": why}
            for d, why in _reassessment.stale_decisions(
                ledger, _options.decision_rows(committed))],
        "currency": currency_projection(committed),
        "by": advocate_id,
        "at": today.isoformat(),
    }


@app.get("/api/matters/{matter_id}/dependencies")
def get_dependencies(matter_id: str, advocate_id: Advocate) -> dict:
    """WHAT EVERY CONCLUSION ON THIS FILE RESTS ON, AND WHETHER IT STILL
    HOLDS. BK-65-AC1, P18.

    Read from the persisted ledger and nothing else, so what this returns
    after a restart is what the correction wrote before it. The cover
    carries the same block; this is the full record with every tracked input
    and every revision.
    """
    from nm.edge.projections import currency_projection

    m = _owned(matter_id, advocate_id)
    return {"state": "ok", "matter_id": m.id, "version": m.version,
            **currency_projection(m)}


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
    in `backend/nm/domain/authority.py`. This route does not decide who may instruct;
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
    # A MATERIAL CHANGE REACHES DERIVED WORK, NOT ONLY THE SCOPE SCREEN.
    # BK-57-AC5.
    #
    # `sync_inputs` observes every input the file holds and lets `observe`
    # decide what moved; the commission is one of them. Hearing preparation,
    # advice and anything else resting on the instruction is invalidated by
    # P18's own closure -- the past is kept as a `Revision` and nothing outside
    # the closure is touched.
    reopened_nodes: tuple[str, ...] = ()
    if moved:
        from nm.core import dependency as _dep

        ledger, reopened_nodes, _edges = _dep.sync_inputs(
            _dep.Ledger.from_stored(updated.dependencies), updated,
            reason=(f"the instruction changed ({', '.join(moved)}) and this "
                    f"rests on it"),
            at=proposed.recorded_at)
        updated = dataclasses.replace(updated, dependencies=ledger.as_dict())
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
        "reopened_work": list(reopened_nodes),
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

    `backend/nm/core/screens.unscreened` decides this. Recomputing it here would be
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
def turn(req: TurnRequest, advocate_id: Advocate, request: Request) -> _Released:
    from nm.domain.external_ai import ModelPermissionRefused

    payload = TurnInput(
        advocate_id=advocate_id,
        message=req.message,
        matter_id=req.matter_id,
        # The advocate naming a thread OUTRANKS every heuristic. The only
        # source better than a number of record is the person holding the file.
        thread_id=req.thread_id,
        # THE FORUM'S DATE, not the server's (BK-14). `frontend/app.js` sends
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

    wired = application()
    def session_current():
        session = wired.directory.session(
            request.cookies.get('nm_session', ''),
            _device(request.cookies.get('nm_device'), request.headers.get('user-agent')), utcnow())
        return bool(session and session.advocate_id == advocate_id)

    try:
        engine: TurnEngine = wired.engine_for(advocate_id, session_current=session_current)
        output = engine.run(payload)
    except ModelPermissionRefused as exc:
        # Do not assert that an interrupted/replayed turn could never have
        # committed. The durable receipt remains the authority for retries.
        raise HTTPException(403, detail={
            "code": "model_permission_required", "why": str(exc),
            "turn_id": req.turn_id, "committed": "unknown",
        }) from exc
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

# ============================================================ P21 — research ==
#
# THE RESEARCH WORKFLOW ON THE MATTER. `/api/search` stays what it is -- ranked
# paragraphs for a signed-in advocate, nothing matter-specific. These routes
# are the compatibility form of the design-only `start-research`,
# `get-research` and `get-source` commands: a research need is opened ON a
# matter, every index it consults is recorded by identity, the adverse search
# is recorded by STATE, a case is inspected through the record that consulted
# it, and a source is attached to an issue only by an exact locator with a
# verbatim quotation. Scope is the matter: a request for a file the advocate
# does not hold is the same 404 as every other matter lookup, and a readback
# or a reliance for a research need on another matter is refused.


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: NonBlank = Field(min_length=1)
    issue: NonBlank = Field(min_length=1)
    query: str = ""
    citation: str = ""
    court: str | None = None
    from_year: int | None = None
    to_year: int | None = None
    expected_version: int


class AttachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locator: NonBlank = Field(min_length=1)
    quote: NonBlank = Field(min_length=1)
    issue: str = ""
    expected_version: int


def _stale(m, expected: int) -> None:
    if m.version != expected:
        raise HTTPException(status_code=409, detail={
            "code": "STALE_VERSION",
            "why": (f"this matter moved while you were working: you were on "
                    f"version {expected} and it is now at {m.version}"),
            "expected_version": expected, "matter_version": m.version,
            "committed": "not_committed"})


def _research_rows(m):
    from nm.core import research as rs
    return rs.all_from_stored(getattr(m, "research", ()) or ())


def _research_or_404(m, research_id: str):
    from nm.core import research as rs
    found = rs.find(_research_rows(m), research_id)
    if found is None:
        # THE SAME 404 FOR "NOT ON THIS MATTER" AND "DOES NOT EXIST", for the
        # reason the matter lookup gives: a research id from another file
        # must learn nothing here.
        raise HTTPException(status_code=404, detail="no such research on this matter")
    return found


def _discovery_dict(d) -> dict:
    return {
        "query": d.query, "index": d.index, "coverage": d.coverage.value,
        "why": d.why, "filters": d.filters,
        "paragraphs_ranked": d.paragraphs_ranked,
        "identity": None if d.identity is None else {
            "built_at": d.identity.built_at, "source": d.identity.source,
            "corpus_version": d.identity.corpus_version,
            "held": d.identity.held, "of_source": d.identity.of_source,
            "scope": d.identity.scope,
            "fraction_of_source": d.identity.fraction_of_source},
        "cases": [{
            "case_id": c.case_id, "case_name": c.case_name, "court": c.court,
            "year": c.year, "paragraphs_matched": c.paragraphs_matched,
            "snippet": c.snippet, "origin": c.origin.value,
            "band": _rank_band(c.confidence)} for c in d.cases],
    }


def _rank_band(confidence: float) -> str:
    """WHERE IT SAT IN THIS SEARCH, never a percentage. The client renders the
    same three words; a number here would be read as calibrated confidence."""
    if confidence >= 0.66:
        return "top of this search"
    if confidence >= 0.33:
        return "middle of this search"
    return "lower in this search"


@app.post("/api/matters/{matter_id}/research", dependencies=[CsrfProtected],
          status_code=201)
def start_research(matter_id: str, body: ResearchRequest,
                   advocate_id: Advocate) -> dict:
    """Open or continue a research need on this matter. BK-38-AC1/AC2, BK-84-AC3.

    ONE ROUND PER CALL, against the record's bound. The round consults the
    index -- by exact citation when one is given, by case-level discovery
    otherwise -- and then runs the ADVERSE search for every case it surfaced:
    subsequent treatment, from the identity index, recorded by state. What
    comes back is the durable record plus this round's discovery, so the
    advocate sees the cases now and the file remembers what was asked of
    which index, with what result, for the restart.
    """
    from nm.core import research as rs
    from nm.domain.clock import today as _today

    m = _owned(matter_id, advocate_id)
    _stale(m, body.expected_version)
    if not (body.query or "").strip() and not (body.citation or "").strip():
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_REQUEST",
            "why": "a research round needs a query or an exact citation",
            "committed": "not_committed"})

    today = _today().isoformat()
    rows = _research_rows(m)
    rid = rs.research_id(m.id, body.objective, body.issue, today)
    record = rs.find(rows, rid) or rs.Research(
        id=rid, objective=body.objective.strip(), issue=body.issue.strip(),
        created_at=today, created_by=advocate_id)
    if record.rounds >= record.round_limit:
        raise HTTPException(status_code=409, detail={
            "code": "INVALID_TRANSITION",
            "why": (f"this research need has spent its {record.round_limit} "
                    f"round(s): {record.stopped_because} Open a new need with "
                    f"its own objective to search further."),
            "research_id": rid, "committed": "not_committed"})

    search = application().search
    discovery = None
    resolution = None
    if (body.citation or "").strip():
        resolution = search.resolve(body.citation)
        case_ids = (resolution.case_id,) if resolution.case_id else ()
        outcome = (rs.Outcome.RESULTS if case_ids
                   else rs.Outcome.UNAVAILABLE_INDEX
                   if resolution.state.value == "index_unavailable"
                   else rs.Outcome.SEARCHED_NO_RESULTS)
        consulted = rs.Consulted(
            query=body.citation.strip(), index=search.name,
            outcome=outcome, case_ids=case_ids, why=resolution.why)
    else:
        discovery = search.discover(
            body.query, court=body.court, from_year=body.from_year,
            to_year=body.to_year, limit=20)
        outcome = rs.classify(
            discovery.coverage, hits=len(discovery.cases), court=body.court,
            court_read_as=str(discovery.filters.get("court_read_as") or ""))
        ident = discovery.identity
        consulted = rs.Consulted(
            query=body.query.strip(), index=discovery.index, outcome=outcome,
            built_at=ident.built_at if ident else "",
            corpus_version=ident.corpus_version if ident else "",
            held=ident.held if ident else None,
            of_source=ident.of_source if ident else None,
            court=(body.court or "").strip(),
            court_read_as=str(discovery.filters.get("court_read_as") or ""),
            from_year=body.from_year, to_year=body.to_year,
            case_ids=tuple(c.case_id for c in discovery.cases),
            why=discovery.why or "")

    # THE ADVERSE SEARCH, BY STATE. For every case surfaced, subsequent
    # treatment is asked of the identity index. An index that cannot answer is
    # UNAVAILABLE -- never an empty success -- and no case surfaced means no
    # adverse search RAN, which `clean_bill` reads as not_assessed.
    adverse = None
    if consulted.case_ids:
        found: list[str] = []
        unavailable = ""
        for cid in consulted.case_ids[:ADVERSE_BOUND]:
            treatment = search.treatment(cid)
            if treatment.state.value == "not_checked" and "not built" in treatment.scope:
                unavailable = treatment.scope
                break
            if treatment.state.value == "negative":
                found.append(cid)
        adverse = rs.AdverseSearch(
            target=", ".join(consulted.case_ids[:ADVERSE_BOUND]),
            state=(rs.AdverseState.UNAVAILABLE if unavailable else rs.AdverseState.RAN),
            query="subsequent treatment of each surfaced case",
            outcome=(None if unavailable else
                     rs.Outcome.RESULTS if found else rs.Outcome.SEARCHED_NO_RESULTS),
            found=tuple(found), why=unavailable)
    record = rs.with_round(record, consulted, adverse)

    m = replace(m, research=tuple(r.as_dict() for r in rs.put(rows, record)),
                last_activity=today)
    try:
        committed = application().store.commit(m, expected_version=body.expected_version)
    except StaleWrite as exc:
        raise HTTPException(status_code=409, detail={
            "code": "STALE_VERSION", "why": str(exc),
            "committed": "not_committed"}) from exc

    return {
        "state": "recorded", "matter_id": committed.id,
        "version": committed.version,
        "research": record.as_dict(),
        "outcome": consulted.outcome.value,
        "discovery": _discovery_dict(discovery) if discovery else None,
        "resolution": None if resolution is None else {
            "raw": resolution.raw, "key": resolution.key,
            "state": resolution.state.value, "case_id": resolution.case_id,
            "why": resolution.why},
    }


@app.get("/api/matters/{matter_id}/research")
def list_research(matter_id: str, advocate_id: Advocate) -> dict:
    m = _owned(matter_id, advocate_id)
    rows = _research_rows(m)
    return {"state": "ok", "matter_id": m.id, "version": m.version,
            "research": [r.as_dict() for r in rows], "count": len(rows)}


@app.get("/api/matters/{matter_id}/research/{research_id}")
def get_research(matter_id: str, research_id: str, advocate_id: Advocate) -> dict:
    m = _owned(matter_id, advocate_id)
    record = _research_or_404(m, research_id)
    return {"state": "ok", "matter_id": m.id, "version": m.version,
            "research": record.as_dict()}


@app.get("/api/matters/{matter_id}/research/{research_id}/cases/{case_id}")
def inspect_case(matter_id: str, research_id: str, case_id: str,
                 advocate_id: Advocate, q: str | None = None) -> dict:
    """Grouped inspection: a case's paragraphs, read back through the research
    that surfaced it. SCOPE ON READBACK: a case this research did not consult
    is not read through it -- the same 404, so the route cannot be used to
    read the library through somebody else's file."""
    m = _owned(matter_id, advocate_id)
    record = _research_or_404(m, research_id)
    consulted = {cid for c in record.consulted for cid in c.case_ids}
    if case_id not in consulted:
        raise HTTPException(status_code=404,
                            detail="this research did not surface that case")
    search = application().search
    expansion = search.expand(case_id, query=q)
    identity = search.case_identity(case_id)
    return {
        "state": "ok", "matter_id": m.id, "research_id": record.id,
        "case_id": case_id, "index": expansion.index,
        "coverage": expansion.coverage.value, "why": expansion.why,
        # THREE VALUES. `None` is nobody measured this case's coverage.
        "complete": expansion.complete,
        "identity": None if expansion.identity is None else {
            "built_at": expansion.identity.built_at,
            "corpus_version": expansion.identity.corpus_version},
        "case": None if identity is None else {
            "title": identity.title, "court": identity.court,
            "year": identity.year, "bench": identity.describe(),
            "bench_inferred": identity.bench_inferred},
        "paragraphs": [{
            "locator": p.locator, "para_type": p.para_type, "text": p.text,
            "origin": p.origin.value} for p in expansion.paragraphs],
        "paragraph_count": len(expansion.paragraphs),
    }


@app.post("/api/matters/{matter_id}/research/{research_id}/attach",
          dependencies=[CsrfProtected], status_code=201)
def attach_source(matter_id: str, research_id: str, body: AttachRequest,
                  advocate_id: Advocate) -> dict:
    """Attach ONE passage to the issue, by exact locator, with its words.

    FIVE VERDICTS, SEPARATELY. Identity and quote fidelity decide whether it
    may be attached at all (`may_attach`); support is NOT_ASSESSED because
    nothing here can read meaning; treatment is asked of the identity index
    by state; applicability is the binding relationship for this forum. A
    ranked snippet fails the first two and is refused with the reason.

    THE ATTACHED PASSAGE BECOMES AN INPUT THE LEDGER TRACKS (P18), keyed
    `index:locator` and digested on its text, so a republished or withdrawn
    source reaches every conclusion that cites it.
    """
    from nm.core import dependency
    from nm.core import research as rs
    from nm.domain.clock import today as _today

    m = _owned(matter_id, advocate_id)
    _stale(m, body.expected_version)
    record = _research_or_404(m, research_id)
    today = _today().isoformat()
    search = application().search

    passage = search.passage(body.locator)
    consulted = {cid for c in record.consulted for cid in c.case_ids}
    if passage is None:
        identity = (rs.IdentityState.INDEX_UNAVAILABLE if not search.available
                    else rs.IdentityState.UNRESOLVED)
        quote = rs.QuoteState.NOT_CHECKED
        case_id = ""
    else:
        identity = (rs.IdentityState.RESOLVED if passage.case_id in consulted
                    else rs.IdentityState.UNRESOLVED)
        quote = rs.quote_fidelity(body.quote, passage.text)
        case_id = passage.case_id
    ok, why = rs.may_attach(identity, quote)
    if passage is not None and identity is rs.IdentityState.UNRESOLVED:
        why = (f"the locator names a paragraph of {passage.case_id!r}, which this "
               f"research did not surface; attach through the research that found it")
    if not ok:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_REQUEST", "why": why,
            "identity": identity.value, "quote_fidelity": quote.value,
            "committed": "not_committed"})

    treatment = search.treatment(case_id)
    ruling = application().binding_for(passage.court, passage.year)
    applicability, because = rs.applicability_of(
        ruling.status if ruling else None,
        forum_said=(ruling.reason if ruling else ""))
    source_version, dependency_id, dependency_why = application().record_source_dependency(
        work_id=m.id, case_id=case_id,
        fallback_version=(search.identity_version() or "unversioned index"))

    reliance = rs.Reliance(
        issue=(body.issue or record.issue).strip(), case_id=case_id,
        locator=body.locator.strip(), quote=body.quote.strip(),
        identity=identity, quote_fidelity=quote,
        support=rs.SupportState.NOT_ASSESSED,
        treatment_state=treatment.state.value, treatment_scope=treatment.scope,
        applicability=applicability, applicability_because=because,
        attached_by=advocate_id, at=today, source_version=source_version,
        text_digest=rs.digest_of(passage.text),
        ledger_id=f"{search.name}:{body.locator.strip()}")
    record = rs.with_reliance(record, reliance)

    # THE LEDGER LEARNS THE INPUT. The same observer the turn uses.
    ledger = dependency.Ledger.from_stored(m.dependencies)
    ledger, _did = dependency.observe(
        ledger, dependency.InputKind.AUTHORITY, reliance.ledger_id,
        dependency.digest_of(passage.text),
        reason=f"attached by {advocate_id} to {reliance.issue!r}")

    m = replace(m, research=tuple(r.as_dict() for r in rs.put(_research_rows(m), record)),
                dependencies=ledger.as_dict(), last_activity=today)
    try:
        committed = application().store.commit(m, expected_version=body.expected_version)
    except StaleWrite as exc:
        raise HTTPException(status_code=409, detail={
            "code": "STALE_VERSION", "why": str(exc),
            "committed": "not_committed"}) from exc
    return {"state": "attached", "matter_id": committed.id,
            "version": committed.version, "research_id": record.id,
            "reliance": reliance.as_dict(),
            "dependency": {"recorded": dependency_id is not None,
                           "id": dependency_id, "why": dependency_why},
            "research": record.as_dict()}


class Credentials(BaseModel):
    advocate_id: NonBlank = Field(min_length=1)
    password: str = Field(min_length=1)


class ModelPermissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: StrictBool
    notice_version: str = Field(min_length=1, max_length=64)
    expected_version: int = Field(strict=True, ge=0)


@app.get("/api/account/model-permission")
def model_permission(advocate_id: Advocate) -> dict:
    from nm.domain.external_ai import NOTICE_VERSION

    try:
        record = application().directory.model_permission(advocate_id)
    except AuthenticationUnavailable as exc:
        raise HTTPException(503, "AI permission is unavailable. Nothing has been enabled.") from exc
    return {"notice_version": NOTICE_VERSION, "version": record.version if record else 0,
            "accepted": bool(record and record.permits(advocate_id, utcnow())),
            "recorded_at": record.recorded_at.isoformat() if record else None}


@app.post("/api/account/model-permission", dependencies=[CsrfProtected])
def set_model_permission(req: ModelPermissionRequest, advocate_id: Advocate) -> dict:
    from nm.domain.external_ai import NOTICE_VERSION, ModelPermission

    if req.notice_version != NOTICE_VERSION:
        raise HTTPException(422, "The AI sharing notice changed. Reload and read it again.")
    record = ModelPermission(advocate_id, req.notice_version, req.accepted,
                             utcnow(), req.expected_version + 1)
    try:
        application().directory.record_model_permission(
            record, expected_version=req.expected_version)
    except (ValueError, AccountBusy) as exc:
        raise HTTPException(409, str(exc)) from exc
    except AuthenticationUnavailable as exc:
        raise HTTPException(
            503, "AI permission could not be recorded. Nothing has been enabled.") from exc
    return model_permission(advocate_id)


class RegistrationConsent(BaseModel):
    """Two required acknowledgements and a separate optional OpenAI choice.

    Implementation Plan F-A-09. STRICT booleans: `"true"` or `1` is not a person
    ticking a box, and a lax model would turn either into one.
    """

    model_config = ConfigDict(extra="forbid")

    notice_version: str = Field(min_length=1, max_length=64)
    agreed: StrictBool
    adult: StrictBool
    external_ai: StrictBool = False
    external_ai_notice_version: str | None = Field(default=None, max_length=64)


class Registration(BaseModel):
    """Public account creation, or password-only acceptance of an invitation.

    Public email is an unverified sign-in handle, not a qualification or a
    shared-firm assignment. The optional invitation header selects the older
    bound-identity lane; that lane cannot accept a caller-supplied email.

    `consent` is REQUIRED on the public lane, whose page shows the privacy
    notice; on the invitation lane it is recorded when given.
    """

    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(default=None, max_length=320)
    password: str = Field(min_length=1, max_length=_NEW_PASSWORD_MAX)
    password_again: str = Field(min_length=1, max_length=_NEW_PASSWORD_MAX)
    consent: RegistrationConsent | None = None


def _consent(given: RegistrationConsent | None, now):
    """The consent record a registration carries, or 422 saying what is missing."""
    from nm.domain.advocate import CONSENT_REQUIRED, registration_consent

    if given is None:
        raise HTTPException(422, CONSENT_REQUIRED)
    try:
        return registration_consent(given.notice_version, given.agreed, given.adult, now,
                                    external_ai=given.external_ai,
                                    external_ai_notice_version=given.external_ai_notice_version)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class ForgotPassword(BaseModel):
    """Ask for a reset link. Implementation Plan F-A-03."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)


class PasswordResetRequest(BaseModel):
    """Spend one emailed reset link on a new password."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)
    password: str = Field(min_length=1, max_length=_NEW_PASSWORD_MAX)
    password_again: str = Field(min_length=1, max_length=_NEW_PASSWORD_MAX)


#: THE ONE ANSWER TO "SEND ME A RESET LINK", whether or not an account exists.
#: It promises what is true in both cases and nothing more: it does not say a
#: message was sent, because for an unknown address none was.
_RESET_REQUESTED = (
    "If an account exists for that email, a link to set a new password is on "
    f"its way. The link works once and expires in {PASSWORD_RESET_MINUTES} minutes.")
#: Unknown, used, expired and superseded links all say exactly this.
_RESET_REFUSED = (
    "That reset link is not valid or has expired. Nothing was changed. Ask for "
    "a new link from Forgot password.")

_mail_log = logging.getLogger("nm.account_mail")


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
    "use Forgot password. If the problem continues, contact support.")
_REGISTRATION_REFUSED = (
    "Registration could not be completed. Try signing in or use Forgot "
    "password; otherwise contact support.")
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
    An unreadable counter cannot enforce guessing limits and refuses admission.
    No refused retry is itself a failure, so knocking cannot extend a pause.
    """
    counts = directory.failures_since(advocate_id, source, now - attempts.WINDOW)
    if counts is None or not directory.limiter_available():
        raise HTTPException(503, 'Account access is temporarily unavailable. Try again later.',
                            headers={'Retry-After': '60'})
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
    if not invited and not _public_registration_available():
        raise HTTPException(503, 'Public registration is not available while email delivery '
                            'is disabled. Existing accounts can still sign in.')
    invitation = (x_enrolment_invitation or "").strip()
    rate_key = f"invitation:{token_fingerprint(invitation)}"
    if invited:
        if "email" in body.model_fields_set:
            raise HTTPException(422, "An invitation supplies its own account identity.")
        consent = _consent(body.consent, now) if body.consent is not None else None
        _admit_auth_attempt(directory, rate_key, source, now, action="enrolment")
    else:
        try:
            email = registration_email(body.email)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        # CONSENT BEFORE ADMISSION. Implementation Plan F-A-09: this is the door the
        # register card uses, and the card shows the privacy notice, so an
        # account made here without its consent is refused -- before the
        # attempt is counted and before a password is derived.
        consent = _consent(body.consent, now)
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
            identity = directory.accept_invitation(invitation, credential, now,
                                                   consent=consent)
        else:
            identity = AdvocateIdentity(id=email, name=email, email=email)
            pending = directory.begin_pending_registration(Enrolment(
                identity=identity, credential=credential, created_at=now,
                consent=consent), now)
            _send_confirmation(email, pending['code'])
            return JSONResponse(status_code=202, content={
                'state': 'confirmation_required', 'email': email,
                'flow': pending['flow'], 'detail': _CONFIRMATION_REQUESTED,
                'delivery': 'mailbox' if getattr(application().mail, 'delivers_to_mailbox', False)
                else 'local_outbox_only'})
    except InvitationRefused as exc:
        directory.note_failure(rate_key, source, now)
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AlreadyEnrolled as exc:
        raise HTTPException(status_code=409, detail=(
            str(exc) if invited else _REGISTRATION_REFUSED)) from exc
    except (OSError, RegistrationUnavailable) as exc:
        raise HTTPException(503, _REGISTRATION_UNAVAILABLE,
                            headers={"Retry-After": "60"}) from exc

    # RETURNED BECAUSE IT IS WHAT THEY SIGN IN WITH. A registration that
    # succeeds and does not say what to type next has enrolled someone who
    # cannot get in.
    return {
        "advocate_id": identity.id,
        "name": identity.name,
    }


_CONFIRMATION_REQUESTED = (
    'If this address is eligible, a confirmation code has been requested. '
    'Enter the six-digit code within 15 minutes. You have five attempts. '
    'Already registered? Return to Sign in or Forgot password.')


def _public_registration_available() -> bool:
    settings = application().environment
    mode = settings.get('NM_PUBLIC_REGISTRATION', 'disabled')
    if mode == 'local-test':
        return (settings.get('NM_MODEL_PROVIDER') == 'scripted'
                and getattr(application().mail, 'delivery_mode', '') == 'local_outbox_only')
    return (mode == 'enabled' and bool(getattr(application().mail, 'delivers_to_mailbox', False))
            and bool(settings.get('NM_PUBLIC_URL', '').startswith('https://')))


@app.get('/api/account-capabilities')
def account_capabilities() -> dict:
    from nm.domain.account_confirmation import CODE_ATTEMPTS, CODE_MINUTES, RESEND_SECONDS
    return {'public_registration': _public_registration_available(),
            'mail_delivery': 'mailbox' if getattr(application().mail, 'delivers_to_mailbox', False)
            else getattr(application().mail, 'delivery_mode', 'disabled'), 'confirmation_digits': 6,
            'confirmation_minutes': CODE_MINUTES, 'confirmation_attempts': CODE_ATTEMPTS,
            'resend_seconds': RESEND_SECONDS}


def _send_confirmation(email: str, code: str | None) -> None:
    if code is None:
        return
    from nm.domain.mail import confirmation_mail
    try:
        application().mail.send(confirmation_mail(email, code))
    except (OSError, RuntimeError) as exc:
        _mail_log.error('confirmation not queued: %s', type(exc).__name__)
        raise HTTPException(503, 'Confirmation delivery could not be confirmed. '
                            'Wait before requesting another code.') from None


class ConfirmEmail(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=1, max_length=320)
    code: str = Field(pattern=r'^[0-9]{6}$')
    flow: str = Field(default='', max_length=128)
    password: str | None = Field(default=None, max_length=_NEW_PASSWORD_MAX)
    password_again: str | None = Field(default=None, max_length=_NEW_PASSWORD_MAX)


class PendingCancellation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=1, max_length=320)
    flow: str = Field(min_length=1, max_length=128)


@app.post('/api/register/cancel', dependencies=[Depends(registration_origin)])
def cancel_registration(body: PendingCancellation, request: Request) -> dict:
    from nm.domain.advocate import registration_email
    from nm.ports.directory import RegistrationUnavailable
    try:
        email = registration_email(body.email)
        directory = application().directory
        source = request.client.host if request.client else 'unknown-source'
        admitted = directory.admit_registration(email, source, utcnow())
        if not admitted.allowed:
            raise HTTPException(429, 'Too many requests. Wait before trying again.')
        return {'cancelled': application().directory.cancel_pending_registration(
            email, body.flow, utcnow())}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except (OSError, RegistrationUnavailable) as exc:
        raise HTTPException(503, 'The pending registration could not be changed.') from exc


@app.post('/api/register/confirm', dependencies=[Depends(registration_origin)])
def confirm_email(body: ConfirmEmail, request: Request) -> dict:
    from nm.domain.account_confirmation import ConfirmationRefused
    from nm.domain.advocate import enrol, registration_email
    from nm.ports.directory import RegistrationUnavailable
    try:
        email = registration_email(body.email)
        directory = application().directory
        source = request.client.host if request.client else 'unknown-source'
        _admit_auth_attempt(directory, 'confirm:' + email, source, utcnow(), action='confirmation')
        credential = None
        if body.password is not None:
            if body.password != body.password_again:
                raise ValueError('The two passwords do not match. Nothing was changed.')
            credential = enrol(body.password)
        try:
            identity = directory.confirm_registration(
                email, body.code, body.flow, credential, utcnow())
        except ConfirmationRefused:
            directory.note_failure('confirm:' + email, source, utcnow())
            raise
    except (ValueError, ConfirmationRefused) as exc:
        raise HTTPException(400, str(exc)) from None
    except (OSError, RegistrationUnavailable) as exc:
        raise HTTPException(503, 'Confirmation is unavailable. Wait and try again.') from exc
    return {'state': 'confirmed', 'advocate_id': identity.id,
            'detail': 'Email confirmed. Sign in with your password.'}


@app.post('/api/register/resend', dependencies=[Depends(registration_origin)], status_code=202)
def resend_confirmation(body: ForgotPassword, request: Request) -> dict:
    from nm.domain.advocate import registration_email
    from nm.ports.directory import RegistrationUnavailable
    try:
        email = registration_email(body.email)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    directory = application().directory
    source = request.client.host if request.client else 'unknown-source'
    try:
        admitted = directory.admit_registration(email, source, utcnow())
        if not admitted.allowed:
            raise HTTPException(429, 'Too many requests. Wait before trying again.',
                                headers={'Retry-After': str(max(
                                    1, ceil(admitted.retry_after.total_seconds())))})
        _send_confirmation(email, directory.resend_registration(email, utcnow()))
    except (OSError, RegistrationUnavailable) as exc:
        raise HTTPException(503, 'Confirmation is unavailable. Wait and try again.') from exc
    return {'detail': _CONFIRMATION_REQUESTED}


# ------------------------------------------------------- password reset ---
#
# Implementation Plan F-A-03: a forgotten password is replaced through a link
# sent to the account's email address. There are no recovery codes (F-A-04).


def public_origin(request: Request) -> None:
    """A public account door the page itself submits. Its origin is required.

    No session exists yet, so there is no CSRF value to double-submit; an exact
    same-origin check is what stops another site from driving these forms --
    for instance, from flooding strangers' inboxes with reset links.
    """
    _require_origin(request)


def login_origin(request: Request) -> None:
    """Refuse browser cross-origin login; credential-bearing API clients still work."""
    _require_origin(request, allow_absent=True)


def _public_base(request: Request) -> tuple[str, str]:
    """(the configured public URL or "", this request's own base URL).

    A RESET LINK IS NEVER BUILT FROM A REQUEST HEADER ALONE when it can reach a
    real mailbox. The Host header is the caller's to choose, and a link built
    from it lets an attacker ask for a reset of someone else's account and
    receive a link pointing at their own server -- carrying the victim's token.
    `NM_PUBLIC_URL` is the operator's statement of where this product lives;
    `_send_reset_link` refuses to mail a link without it unless the channel is
    the local outbox, which no attacker's inbox can read.
    """
    configured = (application().environment.get("NM_PUBLIC_URL") or "").strip()
    return configured.rstrip("/"), str(request.base_url).rstrip("/")


def _send_reset_link(email: str, configured: str, fallback: str, now) -> None:
    """Issue and queue one reset link. Runs AFTER the neutral answer is sent.

    WHY AFTER. Issuing a link and writing a message takes time that looking up
    an unknown address does not; doing it inside the request would make the
    answer's timing say whether the account exists. As a background task the
    response is identical in content and in timing either way.

    NEVER SILENT, NEVER RAISED INTO THE SERVER. The person who asked cannot be
    told a delivery failed -- that would say the account exists -- so a failure
    is logged at ERROR with its cause and never the link, and `/api/health`
    states what the mail channel is. A programming error is logged with its
    traceback, separately, so it cannot pass for a delivery problem.
    """
    from nm.domain.egress import EgressRefused
    from nm.domain.mail import password_reset_mail

    mail = application().mail
    base = configured or (
        "" if getattr(mail, "delivers_to_mailbox", True) else fallback)
    try:
        token = application().directory.issue_password_reset(email, now)
        if token is None:
            return
        if not base:
            _mail_log.error("password reset link not sent: NM_PUBLIC_URL is not "
                            "configured for a mailbox-delivering channel")
            return
        mail.send(password_reset_mail(email, f"{base}/#reset={token}"))
    except (OSError, EgressRefused) as exc:
        _mail_log.error("password reset link not delivered: %s", type(exc).__name__)
    except Exception:  # noqa: BLE001 -- a programming error, reported as one
        _mail_log.exception("password reset link failed with a programming error")


@app.post("/api/password/forgot", dependencies=[Depends(public_origin)],
          status_code=202)
@implements("A1")
def forgot_password(body: ForgotPassword, request: Request,
                    background: BackgroundTasks) -> dict:
    """Send a reset link to an account's email. The same answer either way.

    EVERY REQUEST IS COUNTED, whether or not an account exists, against the
    address and against the source. A counter that moved only for real accounts
    would itself say which addresses are registered, and the limit is what
    stops this door being used to fill a stranger's inbox.
    """
    from nm.domain.advocate import registration_email

    now = utcnow()
    source = request.client.host if request.client else "unknown-source"
    directory = application().directory
    try:
        email = registration_email(body.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    rate_key = f"password-reset:{email}"
    _admit_auth_attempt(directory, rate_key, source, now,
                        action="password reset request")
    directory.note_failure(rate_key, source, now)
    configured, fallback = _public_base(request)
    background.add_task(_send_reset_link, email, configured, fallback, now)
    return {"detail": _RESET_REQUESTED}


@app.post("/api/password/reset", dependencies=[Depends(public_origin)])
@implements("A1")
def reset_password(body: PasswordResetRequest, request: Request) -> dict:
    """Spend one reset link on a new password, and end every session.

    THE PASSWORDS ARE CHECKED BEFORE THE LINK IS TOUCHED. A mismatch or a
    password the rules refuse costs nothing and leaves the link usable; only a
    change that is about to happen spends it.
    """
    from nm.domain.advocate import enrol

    now = utcnow()
    source = request.client.host if request.client else "unknown-source"
    directory = application().directory
    # PER SOURCE. A key shared by everyone would let one caller's failures pause
    # every advocate's reset; the token itself is 256 random bits, so there is
    # no account to aim a guess at.
    rate_key = f"password-reset-link:{source}"
    _admit_auth_attempt(directory, rate_key, source, now,
                        action="password reset link")
    if body.password != body.password_again:
        raise HTTPException(
            status_code=400,
            detail="The two passwords do not match. Nothing was changed.")
    try:
        credential = enrol(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = directory.reset_password(body.token, credential, now)
    except AccountBusy as exc:
        raise HTTPException(
            status_code=503,
            detail="Account access is changing. Try again in a moment.") from exc
    if not result.success:
        directory.note_failure(rate_key, source, now)
        raise HTTPException(status_code=400, detail=_RESET_REFUSED)
    return {"reset": True, "sessions_ended": result.sessions_ended}


@app.post("/api/login", dependencies=[Depends(login_origin)])
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
            body.advocate_id, body.password, device, now,
            client_label=_client_label(user_agent), source=source)
    except AccountBusy as exc:
        raise HTTPException(
            status_code=503,
            detail="Account access is changing. Try sign-in again in a moment.") from exc
    except OSError as exc:
        raise HTTPException(503, 'Sign-in could not be saved. Try again later.') from exc
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
    identity, token = opened

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
                            # Device identity survives the draft lifetime; it
                            # grants no access without a separately live session.
                            max_age=60 * 60 * (24 * 30 if name == "nm_device" else 12),
                            path="/")
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
    # THE IDLE LIMIT TRAVELS WITH THE SESSION, so the page counts down the
    # server's number and does not keep a second copy of it (F-A-12).
    return {"advocate": identity.as_dict(), "workspace": _workspace(identity),
            "professional_approval": _professional_status(
                application().directory, identity, now),
            "session_idle_minutes": SESSION_IDLE_MINUTES,
            'access_window': _access_window(application().directory.session(
                token, _device(device_id, request.headers.get('user-agent')), now), now)}


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
    from nm.ports.directory import SessionsUnavailable

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
    now = utcnow()
    try:
        listed = directory.sessions_for(advocate_id)
    except (OSError, SessionsUnavailable) as exc:
        raise HTTPException(503, 'Your complete session list could not be read. '
                            'Try again; no sessions were changed.') from exc
    for session in listed:
        rows.append({
            'reference': session.reference,
            'client_label': session.client_label or 'Client details not recorded',
            'source': session.source or 'Not recorded',
            "device": session.device[:12],
            "issued_at": session.issued_at.isoformat(),
            "expires_at": session.expires_at.isoformat(),
            "ended_because": session.why_not(now),
            "live": session.live_at(now),
            'last_active_at': (session.last_active_at or session.issued_at).isoformat(),
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
    from nm.ports.directory import SessionsUnavailable
    try:
        ended = directory.close_all_sessions(
            advocate_id, "revoked by the advocate", except_token=nm_session or "")
    except (OSError, SessionsUnavailable) as exc:
        raise HTTPException(503, 'Revocation could not be confirmed. '
                            'Some sessions may still be signed in; retry is safe.') from exc
    return {"ended": ended}


class SelectedSession(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reference: str = Field(pattern=r'^[0-9a-f]{64}$')


@app.post('/api/sessions/revoke-one', dependencies=[CsrfProtected])
def revoke_selected_session(body: SelectedSession, advocate_id: Advocate,
                            nm_session: str | None = Cookie(default=None)) -> dict:
    from nm.ports.directory import SessionsUnavailable
    try:
        outcome = application().directory.close_selected_session(
            advocate_id, body.reference, 'revoked by the advocate',
            except_token=nm_session or '')
    except (OSError, SessionsUnavailable) as exc:
        raise HTTPException(503, 'Session closure could not be confirmed. '
                            'It may still be signed in; retry is safe.') from exc
    if outcome == 'unknown':
        raise HTTPException(404, 'That session is not available.')
    if outcome == 'current':
        raise HTTPException(409, 'Use Sign out to end your current session.')
    return {'outcome': outcome}


@app.get("/api/session")
def whoami(advocate_id: Advocate, request: Request) -> dict:
    """Who is signed in. 401 through the same dependency as everything else."""
    identity = application().directory.identity(advocate_id)
    if identity is None:
        # A LIVE SESSION FOR AN ADVOCATE WHO IS NOT THERE. The record was
        # deleted or will not open; either way this session must stop working
        # now rather than at expiry.
        raise HTTPException(status_code=401, detail="not signed in")
    directory = application().directory
    return {"advocate": identity.as_dict(), "workspace": _workspace(identity),
            "professional_approval": _professional_status(directory, identity, utcnow()),
            "session_idle_minutes": SESSION_IDLE_MINUTES,
            'access_window': _access_window(request.state.account_session, utcnow())}


def _access_window(session, now) -> dict:
    if session is None:
        raise HTTPException(401, 'not signed in')
    until = min(session.idle_expires_at, session.expires_at)
    return {'confirmed_at': now.isoformat(), 'valid_until': until.isoformat(),
            'remaining_seconds': max(0, (until - now).total_seconds()),
            'absolute_expires_at': session.expires_at.isoformat()}


@app.post('/api/session/activity', dependencies=[CsrfProtected])
def session_activity(advocate_id: Advocate, request: Request,
                     nm_session: str | None = Cookie(default=None),
                     nm_device: str | None = Cookie(default=None)) -> dict:
    now = utcnow()
    session = application().directory.touch_session(
        nm_session or '', _device(nm_device, request.headers.get('user-agent')), now)
    return {'access_window': _access_window(session, now)}


@app.get("/api/drafts/key")
def draft_key(advocate_id: Advocate, response: Response,
              nm_device: str | None = Cookie(default=None)) -> dict:
    """Unlock only this authenticated account's protected same-device drafts."""
    response.headers["Cache-Control"] = "no-store"
    try:
        return application().directory.device_draft_key(advocate_id, nm_device or "")
    except (OSError, ValueError, AccountBusy) as exc:
        raise HTTPException(503, "Draft protection could not be opened. "
                            "Unsent changes may not survive closing this page.") from exc


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


_WEB = ROOT / "frontend"
if _WEB.exists():
    app.mount("/static", _NeverStale(directory=str(_WEB)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        # THE PAGE ITSELF TOO. An index that is cached serves the old script
        # tags, so revalidating the assets it names buys nothing.
        return FileResponse(
            str(_WEB / "index.html"),
            headers={"cache-control": "no-cache, must-revalidate"})
