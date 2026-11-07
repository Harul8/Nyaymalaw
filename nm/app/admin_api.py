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

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from nm.app import admin_views
from nm.arrive.admin_access import Level
from nm.arrive.admin_port import AdminUnavailable
from nm.arrive.advocate_contracts import utcnow
from nm.arrive.directory_port import AuthenticationUnavailable

LEVEL_LABELS = admin_views.LEVEL_LABELS
_NOT_HERE = "Not Found"  # the words FastAPI gives an address the server does not have
_UNAVAILABLE = "This part of the Admin area could not be read. Nothing has been changed."


class PasswordCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=1024)


def admin_router(*, application: Callable, signed_in: Callable, csrf: object, admit_attempt: Callable) -> APIRouter:
    router = APIRouter(prefix="/api/admin")

    def admin_level(advocate_id: str = Depends(signed_in)) -> Level:
        level = application().admin_roster.level_of(advocate_id)
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
        return {"level": level.value, "label": LEVEL_LABELS[level.value], "can_change": level is Level.ADMIN,
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

    @router.get("/access")
    def access(level: Level = Depends(admin_level)) -> dict:
        return read(lambda roster, directory, usage_port, now: admin_views.access_view(
            roster, directory, application().admin_record, now))

    return router
