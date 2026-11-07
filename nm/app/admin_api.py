"""The Admin area's HTTP edge (plan AN.46, piece 46g; owner decisions D116-D119, D124, 7 Nov 2026).

GIVEN THE EDGE'S OWN PIECES, IMPORTING NOTHING FROM IT. The router is built by a function that is handed the signed-in dependency, the
CSRF dependency, the application and the failed-attempt limiter, so this module does not import `nm.app.api` (which includes it) and
the Admin routes can never use a door the rest of the edge does not use.

NOT AN ADMIN IS NOT HERE (D117). A request with no session is the edge's usual 401. A signed-in advocate who is not named in the
settings gets 404 with the words of any address the server does not have, so the Admin area's existence is not told to anyone it is
not for, and the page learns whether to show the Admin entry from `/api/admin/me` answering at all.

EVERY ROUTE READS (view only is enough); the password check is the one write, and it writes only that this session's holder gave their
password just now (D116). The changes an Admin may make come as later pieces and each asks that check, a reason, and writes the audit
entry in the same step.

THE PASSWORD CHECK IS A SIGN-IN CHECK. It goes through the directory's own `authenticate`, behind the same failed-attempt limit as a
sign-in, and its failures are counted with sign-in's; the password is never stored or logged.

A SOURCE THAT CANNOT BE READ FAILS ITS OWN ROUTE (503, in plain words) and nothing else (D128).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from nm.app import admin_changes, admin_views
from nm.arrive.admin_access import Action, Level
from nm.arrive.admin_port import AdminChangeRefused, AdminUnavailable
from nm.arrive.advocate_contracts import canonical_id, utcnow
from nm.arrive.directory_port import AuthenticationUnavailable

LEVEL_LABELS = admin_views.LEVEL_LABELS
_NOT_HERE = "Not Found"  # the words FastAPI gives an address the server does not have
_UNAVAILABLE = "This part of the Admin area could not be read. Nothing has been changed."


class PasswordCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=1024)


class Reason(BaseModel):
    """What every change is sent with. The length is judged by the change itself, in words an admin can act on."""
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(max_length=2000)


class AllowanceChange(Reason):
    usd: Decimal = Field(gt=0, le=1000, decimal_places=6)


class UserTypeChange(Reason):
    user_type: str = Field(pattern="^(advocate|admin)$")


def admin_router(*, application: Callable, signed_in: Callable, csrf: object, admit_attempt: Callable,
                 serving: Callable[[], dict] = lambda: {},
                 send_reset: Callable[[str, Request, object], str] = lambda email, request, now: "not-configured") -> APIRouter:
    router = APIRouter(prefix="/api/admin")

    def admin_level(advocate_id: str = Depends(signed_in)) -> Level:
        level = application().admin_level_of(advocate_id)
        if level is None:
            raise HTTPException(status_code=404, detail=_NOT_HERE)
        return level

    def read(view: Callable, *args):
        try:
            return view(application().admin_roster, application().admin_directory, application().admin_usage,
                        utcnow(), *args)
        except AdminUnavailable as exc:
            raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc

    @router.get("/me")
    def me(request: Request, level: Level = Depends(admin_level)) -> dict:
        session = request.state.account_session
        try:
            confirmed = application().admin_record.password_confirmed(session.token_fingerprint, utcnow())
        except AdminUnavailable:
            confirmed = False
        return {"id": session.advocate_id, "level": level.value, "label": LEVEL_LABELS[level.value], "can_change": level is Level.ADMIN,
                "password_confirmed": confirmed}

    @router.post("/password", dependencies=[csrf])
    def confirm_password(body: PasswordCheck, request: Request, level: Level = Depends(admin_level)) -> dict:
        now = utcnow()
        advocate_id = request.state.account_session.advocate_id
        source = request.client.host if request.client else "unknown-source"
        directory = application().directory
        admit_attempt(directory, advocate_id, source, now, action="password")
        try:
            identity = directory.authenticate(advocate_id, body.password)
        except AuthenticationUnavailable as exc:
            raise HTTPException(503, "The password could not be checked. Try again later.") from exc
        if identity is None:
            directory.note_failure(advocate_id, source, now)
            raise HTTPException(status_code=403, detail="That password was not right.")
        try:
            until = application().admin_record.confirm_password(request.state.account_session.token_fingerprint, now)
        except AdminUnavailable as exc:
            raise HTTPException(503, "The password check could not be saved. Nothing has been changed.") from exc
        return {"confirmed_until": until.isoformat()}

    @router.get("/overview")
    def overview(level: Level = Depends(admin_level)) -> dict:
        return read(lambda roster, directory, usage_port, now: admin_views.overview_view(
            roster, directory, usage_port, now, application().admin_turns))

    @router.get("/users")
    def users(level: Level = Depends(admin_level)) -> dict:
        return read(admin_views.users_view)

    @router.get("/users/{account_id}")
    def user(account_id: str, level: Level = Depends(admin_level)) -> dict:
        found = read(lambda roster, directory, usage, now, wanted: admin_views.user_view(
            wanted, roster, directory, usage, now), account_id)
        if found is None:
            raise HTTPException(status_code=404, detail=_NOT_HERE)
        return found

    @router.get("/usage")
    def usage(days: int = 30, level: Level = Depends(admin_level)) -> dict:
        if days not in admin_views.PERIODS:
            raise HTTPException(status_code=422, detail=f"Usage is shown for {', '.join(map(str, admin_views.PERIODS))} days.")
        return read(lambda roster, directory, usage_port, now, period: admin_views.usage_view(
            roster, directory, usage_port, now, period, application().admin_turns), days)

    # ------------------------------------------------------------------ changes (D116, D121) ---

    def make(request: Request, level: Level, account_id: str, action: Action, label: str, reason: str, do: Callable) -> dict:
        """The account must be there and readable; then the one path every change takes (nm/app/admin_changes.py)."""
        session, now = request.state.account_session, utcnow()
        wanted = canonical_id(account_id)
        account = next((a for a in application().admin_directory.listing(now).accounts if a.id == wanted), None) if wanted else None
        if account is None:
            raise HTTPException(status_code=404, detail=_NOT_HERE)
        if not account.readable:
            raise HTTPException(status_code=409, detail="This account's record could not be read, so it was not changed.")
        try:
            return admin_changes.make_change(
                record=application().admin_record, level=level, actor=session.advocate_id,
                session_fingerprint=session.token_fingerprint, now=now, action=action, label=label, target=account.id,
                reason=reason, do=lambda: do(account, session, now))
        except AdminChangeRefused as exc:
            code = getattr(exc, "code", None)
            raise HTTPException(status_code=exc.status, detail={"code": code, "message": exc.detail} if code else exc.detail) from exc
        except AdminUnavailable as exc:
            raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc

    @router.post("/users/{account_id}/allowance", dependencies=[csrf])
    def add_allowance(account_id: str, body: AllowanceChange, request: Request, level: Level = Depends(admin_level)) -> dict:
        micro = int(body.usd * 1_000_000)
        if Decimal(micro) != body.usd * 1_000_000:
            raise HTTPException(status_code=422, detail="The amount is in US dollars, to at most six decimal places.")

        def grant(account, session, now):
            standing = application().usage.grant(account.id, micro, note=f"{session.advocate_id}: {body.reason.strip()}"[:200])
            return {"allowance": {"granted": standing["granted"], "spent": standing["spent"], "left_percent": standing["left"]}}
        return make(request, level, account_id, Action.ALLOWANCE, f"allowance add usd {format(body.usd.normalize(), 'f')}", body.reason, grant)

    @router.post("/users/{account_id}/end-sessions", dependencies=[csrf])
    def end_sessions(account_id: str, body: Reason, request: Request, level: Level = Depends(admin_level)) -> dict:
        def end(account, session, now):
            keep = session.token_fingerprint if account.id == canonical_id(session.advocate_id) else ""
            return {"sessions_ended": application().admin_accounts.end_sessions(account.id, "ended by an admin", keep)}
        return make(request, level, account_id, Action.SESSIONS, "sessions end", body.reason, end)

    _RESET_WORDS = {
        "mailed": "A password-reset link was emailed to the account.",
        "local-outbox": "A password-reset link was written to this installation's local outbox. No email leaves this computer until "
                        "mail delivery is set up, so the person has not been sent it.",
    }

    @router.post("/users/{account_id}/reset-email", dependencies=[csrf])
    def reset_email(account_id: str, body: Reason, request: Request, level: Level = Depends(admin_level)) -> dict:
        def send(account, session, now):
            sent = send_reset(account.id, request, now)
            if sent == "no-address":
                raise AdminChangeRefused(409, "This account has no email address to send a link to.")
            if sent == "not-configured":
                raise AdminChangeRefused(503, "The public address of this installation is not set, so a link cannot be built.")
            if sent == "not-delivered":
                raise AdminChangeRefused(503, "The link could not be delivered just now. Nothing was sent.")
            return {"sent": sent, "message": _RESET_WORDS[sent]}
        return make(request, level, account_id, Action.RESET_EMAIL, "reset email", body.reason, send)

    def refuse_an_admin(account_id: str) -> None:
        if application().admin_level_of(account_id) is not None:
            raise HTTPException(status_code=409, detail="This account is an admin. Admins are not suspended from here: make it an "
                                                        "advocate first, or take it out of the server's settings if it is named there.")

    @router.post("/users/{account_id}/suspend", dependencies=[csrf])
    def suspend(account_id: str, body: Reason, request: Request, level: Level = Depends(admin_level)) -> dict:
        refuse_an_admin(account_id)

        def stop(account, session, now):
            changed = application().admin_accounts.set_suspended(account.id, True, now)
            ended = application().admin_accounts.end_sessions(account.id, "account suspended by an admin")
            return {"suspended": True, "changed": changed, "sessions_ended": ended}
        return make(request, level, account_id, Action.SUSPEND, "suspend", body.reason, stop)

    @router.post("/users/{account_id}/user-type", dependencies=[csrf])
    def set_user_type(account_id: str, body: UserTypeChange, request: Request, level: Level = Depends(admin_level)) -> dict:
        wanted = canonical_id(account_id)
        if application().admin_roster.level_of(wanted) is not None:
            raise HTTPException(status_code=409, detail="This account is named in the server's settings. Its type is changed there, "
                                                        "not here.")
        if wanted == canonical_id(request.state.account_session.advocate_id):
            raise HTTPException(status_code=409, detail="You cannot change your own user type. Another admin can.")

        def change(account, session, now):
            changed = application().admin_accounts.set_user_type(account.id, body.user_type)
            return {"user_type": body.user_type, "changed": changed}
        return make(request, level, account_id, Action.USER_TYPE, f"user type {body.user_type}", body.reason, change)

    @router.post("/users/{account_id}/reinstate", dependencies=[csrf])
    def reinstate(account_id: str, body: Reason, request: Request, level: Level = Depends(admin_level)) -> dict:
        def allow(account, session, now):
            return {"suspended": False, "changed": application().admin_accounts.set_suspended(account.id, False, now)}
        return make(request, level, account_id, Action.SUSPEND, "reinstate", body.reason, allow)

    @router.get("/library")
    def library(level: Level = Depends(admin_level)) -> dict:
        return read(lambda roster, directory, usage_port, now: admin_views.library_view(application().admin_library, now))

    @router.get("/diagnostics")
    def diagnostics(level: Level = Depends(admin_level)) -> dict:
        return read(lambda roster, directory, usage_port, now: admin_views.diagnostics_view(
            roster, usage_port, application().admin_turns, application().admin_checks, now, serving(), application().health()))

    @router.get("/access")
    def access(level: Level = Depends(admin_level)) -> dict:
        return read(lambda roster, directory, usage_port, now: admin_views.access_view(
            roster, directory, application().admin_record, now))

    return router
