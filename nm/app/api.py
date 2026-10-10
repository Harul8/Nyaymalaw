"""Authenticated HTTP edge for the checked core engine.

Account boundaries are retained from the previous active API. Retired legal
engine routes are deliberately absent; their saved files are not modified.
"""
from __future__ import annotations
import hmac
import logging
import os
from datetime import date
from math import ceil
from pathlib import Path
from typing import Annotated
from fastapi import BackgroundTasks, Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, field_validator
from nm.app.static_assets import browser_assets_router
from nm.arrive import attempts_contracts as attempts
from nm.arrive.advocate_contracts import PASSWORD_RESET_MINUTES, SESSION_IDLE_MINUTES, csrf_token, utcnow
from nm.arrive.directory_port import AccountBusy, AuthenticationUnavailable
from nm.arrive.professional_access import read_professional_status
from nm.core_engine.conversation import HEADER, ConversationRefused, chat_matter_id
from nm.core_engine.turn import saved_rows
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.clock_contracts import FORUM
from nm.shared.identity_contracts import source_fingerprint
from nm.shared.traceability_contracts import implements

ROOT = Path(__file__).resolve().parents[2]
app = FastAPI(title='Nyaymalaw', version='0.2.0')
_application = None
_TRUSTED_ORIGINS = 'NM_TRUSTED_ORIGINS'
_CSRF_REFUSED = 'This request could not be verified as coming from the Nyaymalaw page in this browser. Reload the page and try again.'
_NEW_PASSWORD_MAX = 1024
_REFUSED_DEFAULT = (
    'Those credentials were not accepted. Check the email and password, or '
    'use Forgot password. If the problem continues, contact support.')
_REGISTRATION_REFUSED = (
    'Registration could not be completed. Try signing in or use Forgot '
    'password; otherwise contact support.')
_REGISTRATION_UNAVAILABLE = (
    'Registration is temporarily unavailable. Try again later; if it '
    'continues, contact support. Your existing account can still sign in.')
_CONFIRMATION_REQUESTED = (
    'If this address is eligible, a confirmation code has been requested. '
    'Enter the six-digit code within 15 minutes. You have five attempts. '
    'Already registered? Return to Sign in or Forgot password.')
_RESET_REQUESTED = (
    'If an account exists for that email, a link to set a new password is on '
    f'its way. The link works once and expires in {PASSWORD_RESET_MINUTES} minutes.')
_RESET_REFUSED = (
    'That reset link is not valid or has expired. Nothing was changed. Ask for '
    'a new link from Forgot password.')
_mail_log = logging.getLogger('nm.account_mail')
try:
    SERVING = source_fingerprint()
except Exception as exc:
    SERVING = f'unknown: {type(exc).__name__}'

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


async def unavailable_authentication(_request: Request, _exc: AuthenticationUnavailable):
    return JSONResponse(status_code=503, headers={'Retry-After': '60'}, content={
        'detail': 'Account access is temporarily unavailable. Try again later.'})


def application():
    """The wired application, INJECTED by the composition root.

    The edge deliberately does not build it. Which adapter is live is the
    composition root's business, and letting the serving path choose would put
    provider knowledge exactly where it must never be.
    """
    if _application is None:
        raise RuntimeError(
            "no application wired. The composition root must call "
            "set_application() before serving -- see nm.app.composition.")
    return _application


def set_application(app_) -> None:
    global _application
    _application = app_


class _Released(BaseModel):
    turn_id: str
    matter_id: str | None
    chat_id: str | None = None
    route: str
    mode: str
    mode_statement: str
    blocked: bool
    blocked_reason: str | None
    elements: list[dict]
    material: list[dict] = []
    material_coverage: dict = {}
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
    # LB-90. What this message changed on the board, and what waits for the
    # advocate -- the same note the saved receipt carries.
    board_changes: list[dict] = []
    # LB-83. When the answer was saved: the quiet as-at line under each reply.
    at: str | None = None
    # LB-76. The reply as the advocate reads it, told from `elements` and
    # checked on its own words. Empty: the checked findings are shown as they are.
    composed: list[dict] = []
    continuation: dict = {}
    service_status: str | None = None


def _release(output) -> _Released:
    """Validate the checked core's response at the HTTP byte boundary."""
    return _Released.model_validate(output)


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
    # `signed_in`. That is not a harmless swap: `nm/app/app.js` keys its
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


CsrfProtected = Depends(csrf_protected)

class TurnRequest(BaseModel):
    # NO `advocate_id`. It came from the body, which means the caller asserted
    # who they were and the product recorded that assertion on the file. It now
    # comes from the session, and there is no field here to override it with.
    message: str = Field(min_length=1)

    @field_validator("message")
    @classmethod
    def preserve_original_message(cls, value: str) -> str:
        """Reject blank input without normalising the advocate's source words."""
        _not_blank(value)
        return value

    matter_id: str | None = None
    chat_id: str | None = None
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

    keep_in_matter: bool = False
    """F-C-04. The advocate chose to keep a message NM asked about in this matter."""


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


app.add_exception_handler(RequestValidationError, invalid_request)
app.add_exception_handler(AuthenticationUnavailable, unavailable_authentication)

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
    from nm.shared.external_ai_contracts import NOTICE_VERSION

    try:
        record = application().directory.model_permission(advocate_id)
    except AuthenticationUnavailable as exc:
        raise HTTPException(503, "AI permission is unavailable. Nothing has been enabled.") from exc
    return {"notice_version": NOTICE_VERSION, "version": record.version if record else 0,
            "accepted": bool(record and record.permits(advocate_id, utcnow())),
            "recorded_at": record.recorded_at.isoformat() if record else None}


@app.post("/api/account/model-permission", dependencies=[CsrfProtected])
def set_model_permission(req: ModelPermissionRequest, advocate_id: Advocate) -> dict:
    from nm.shared.external_ai_contracts import NOTICE_VERSION, ModelPermission

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
    from nm.arrive.advocate_contracts import CONSENT_REQUIRED, registration_consent

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
    return read_professional_status(directory.professional_approval, identity.id, now)


def _professional_access(advocate_id: str) -> dict:
    return read_professional_status(application().directory.professional_approval,
                                    advocate_id, utcnow())


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
    from nm.arrive.advocate_contracts import (
        AdvocateIdentity,
        Enrolment,
        enrol,
        registration_email,
        token_fingerprint,
    )
    from nm.arrive.directory_port import (
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
    from nm.arrive.account_confirmation_contracts import CODE_ATTEMPTS, CODE_MINUTES, RESEND_SECONDS
    return {'public_registration': _public_registration_available(),
            'mail_delivery': 'mailbox' if getattr(application().mail, 'delivers_to_mailbox', False)
            else getattr(application().mail, 'delivery_mode', 'disabled'), 'confirmation_digits': 6,
            'confirmation_minutes': CODE_MINUTES, 'confirmation_attempts': CODE_ATTEMPTS,
            'resend_seconds': RESEND_SECONDS}


def _send_confirmation(email: str, code: str | None) -> None:
    if code is None:
        return
    from nm.arrive.mail_contracts import confirmation_mail
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
    from nm.arrive.advocate_contracts import registration_email
    from nm.arrive.directory_port import RegistrationUnavailable
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
    from nm.arrive.account_confirmation_contracts import ConfirmationRefused
    from nm.arrive.advocate_contracts import enrol, registration_email
    from nm.arrive.directory_port import RegistrationUnavailable
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
    from nm.arrive.advocate_contracts import registration_email
    from nm.arrive.directory_port import RegistrationUnavailable
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
    from nm.arrive.mail_contracts import password_reset_mail
    from nm.shared.egress_contracts import EgressRefused

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
    from nm.arrive.advocate_contracts import registration_email

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
    from nm.arrive.advocate_contracts import enrol

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
    from nm.leave.sign_out import end_session

    outcome = end_session(application().directory, nm_session)
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
    from nm.arrive.advocate_contracts import token_fingerprint as _fp
    from nm.arrive.directory_port import SessionsUnavailable

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
    from nm.arrive.directory_port import SessionsUnavailable
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
    from nm.arrive.directory_port import SessionsUnavailable
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


def _session_current(request, advocate_id):
    directory = application().directory
    session = directory.session(request.cookies.get('nm_session', ''),
        _device(request.cookies.get('nm_device'), request.headers.get('user-agent')), utcnow())
    return bool(session and session.advocate_id == advocate_id
                and directory.identity(advocate_id) is not None)

@app.post('/api/turn', dependencies=[CsrfProtected])
def turn(req: TurnRequest, advocate_id: Advocate, request: Request) -> _Released:
    if not _session_current(request, advocate_id):
        raise HTTPException(401, 'not signed in')
    legacy = (req.thread_id, req.today, req.work_product, req.parties,
              req.release, req.capacity, req.keep_in_matter)
    if any(value not in (None, '', {}, False) for value in legacy) or req.jurisdiction != FORUM:
        raise HTTPException(422, {'why': 'These action settings are not available in this conversation. '
            'Describe the requested work in your message instead.', 'code': 'unsupported_action_settings',
            'committed': 'unconfirmed', 'turn_id': req.turn_id, 'chat_id': req.chat_id,
            'retryable': False})
    try:
        output = application().run_turn(advocate_id=advocate_id,
            message=req.message, turn_id=req.turn_id, chat_id=req.chat_id,
            matter_id=req.matter_id, expected_version=req.expected_version,
            session_current=lambda: _session_current(request, advocate_id))
    except ConversationRefused as exc:
        raise HTTPException(exc.status, _conversation_error(exc, req)) from exc
    except ModelPermissionRefused as exc:
        if not _session_current(request, advocate_id):
            raise HTTPException(401, 'not signed in') from exc
        # No receipt lookup is implied by permission refusal: an earlier attempt
        # with this request identity may already be saved.
        raise HTTPException(403, {'why': str(exc), 'code': 'model_permission_required',
            'committed': 'unconfirmed', 'turn_id': req.turn_id, 'chat_id': req.chat_id,
            'retryable': False}) from exc
    if not _session_current(request, advocate_id):
        raise HTTPException(401, 'not signed in')
    return _release(output)


def _conversation_error(exc, req=None):
    """Owned service facts only; no rejected drafts or internal model feedback."""
    detail = {'why': exc.why, 'code': exc.code, 'committed': exc.committed,
              'retryable': exc.retryable}
    if req is not None:
        detail.update(turn_id=req.turn_id, chat_id=req.chat_id)
    return detail


def _read_chat(chat_id, advocate_id, request):
    """One account-derived lookup and checked replay for both chat and sources."""
    try:
        matter = application().store.load(chat_matter_id(advocate_id, chat_id))
    except (OSError, ValueError) as exc:
        raise HTTPException(503, 'This conversation could not be read reliably.') from exc
    if not _session_current(request, advocate_id):
        raise HTTPException(401, 'not signed in')
    if matter is None or matter.advocate_id != advocate_id:
        raise HTTPException(404, 'Conversation not available.')
    try:
        rows = saved_rows(matter, advocate_id)
    except ConversationRefused as exc:
        raise HTTPException(exc.status, _conversation_error(exc)) from exc
    if not _session_current(request, advocate_id):
        raise HTTPException(401, 'not signed in')
    return matter, rows

@app.get('/api/work')
def work(advocate_id: Advocate, request: Request):
    listing = application().store.list_for(advocate_id)
    chats, matters, unavailable = [], [], list(listing.unreadable)
    for matter in sorted(listing.matters, key=lambda m: listing.saved(m.id), reverse=True):
        if matter.advocate_id != advocate_id:
            raise HTTPException(503, 'Your work list could not be read reliably.')
        if HEADER in matter.intake_answers:
            try:
                rows = saved_rows(matter, advocate_id)
            except ConversationRefused:
                unavailable.append(matter.id)
                continue
            if rows:
                chats.append({'chat_id': rows[0]['chat_id'], 'preview': rows[0]['message'],
                    'turn_count': len(rows), 'last_updated': listing.saved(matter.id)})
            continue
        # Old records remain history; current replay never upgrades their contracts.
        matters.append({'matter_id': matter.id, 'matter': matter.title,
            'last_updated': listing.saved(matter.id), 'state': 'historical'})
    if not _session_current(request, advocate_id):
        raise HTTPException(401, 'not signed in')
    return {'state': 'partial' if unavailable else 'ok', 'chats': chats, 'matters': matters,
            'chat_count': len(chats), 'row_count': len(matters), 'unreadable': unavailable,
            'unavailable': unavailable}

@app.get('/api/chats')
def chats(advocate_id: Advocate, request: Request):
    return work(advocate_id, request)

@app.get('/api/chats/{chat_id}')
def chat(chat_id: str, advocate_id: Advocate, request: Request, response: Response):
    matter, rows = _read_chat(chat_id, advocate_id, request)
    # The existing UI expects a boolean release projection. Do not change the
    # canonical saved receipt's string commitment or its original snapshot.
    turns = [{**row['response'], 'message': row['message'], 'message_source': 'held',
              'committed': True, 'release_state': 'released'} for row in rows]
    if not _session_current(request, advocate_id):
        raise HTTPException(401, 'not signed in')
    response.headers['Cache-Control'] = 'no-store'
    return {'state': 'ok', 'chat_id': chat_id, 'matter_id': None,
            'matter_version': matter.version, 'turns': turns}


@app.get('/api/chats/{chat_id}/turns/{turn_id}/brain-sources/{element}/{source}')
def chat_source(chat_id: str, turn_id: str, element: int, source: int,
                advocate_id: Advocate, request: Request, response: Response):
    _, rows = _read_chat(chat_id, advocate_id, request)
    row = next((item for item in rows if item['turn_id'] == turn_id), None)
    if row is None or element < 0 or source < 0:
        raise HTTPException(404, 'Saved passage not available.')
    elements = row['response']['elements']
    if element >= len(elements) or source >= len(elements[element]['sources']):
        raise HTTPException(404, 'Saved passage not available.')
    selected = elements[element]['sources'][source]
    if not _session_current(request, advocate_id):
        raise HTTPException(401, 'not signed in')
    response.headers['Cache-Control'] = 'no-store'
    return selected

@app.get('/api/matters/{matter_id}')
@app.get('/api/matters/{matter_id}/transcript')
def historical_matter(matter_id: str, advocate_id: Advocate, request: Request):
    matter = application().store.load(matter_id)
    if not _session_current(request, advocate_id):
        raise HTTPException(401, 'not signed in')
    if matter is None or matter.advocate_id != advocate_id:
        raise HTTPException(404, 'Matter not available.')
    raise HTTPException(409, 'This matter belongs to the earlier brain. Its saved data is retained; opening it in the rebuilt brain is not available yet.')

app.include_router(browser_assets_router(
    asset_paths=lambda: application().browser_asset_paths(), root=ROOT))
