"""Authenticated, CSRF-protected private work; no unchecked answer leaves here."""
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from nm.shared.budget_contracts import Spend
from nm.shared.store_port import StaleWrite


class PrivateWorkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: int = Field(ge=1)
    turn_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=100000)
    selected_issue_ids: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(
        default_factory=list, max_length=64)


def router(*, owned: Callable, signed_in: Callable, session_current: Callable,
           csrf_protected: Callable, run: Callable) -> APIRouter:
    routes = APIRouter()

    @routes.post("/api/matters/{matter_id}/brain/preview",
                 dependencies=[Depends(csrf_protected)])
    def evaluate(request: Request, response: Response, matter_id: str,
                 body: PrivateWorkRequest, actor: str = Depends(signed_in)):
        owned(matter_id, actor)
        if not body.message.strip() or any(not value.strip() for value in body.selected_issue_ids):
            raise HTTPException(422, "Supply an instruction and valid dispute selections.")
        try:
            result = run(actor=actor, matter_id=matter_id, expected_version=body.version,
                turn_id=body.turn_id, message=body.message,
                selected_issue_ids=tuple(body.selected_issue_ids),
                session_current=lambda: session_current(request, actor))
        except StaleWrite as exc:
            raise HTTPException(409, "The file changed. Reopen it before continuing.") from exc
        except PermissionError as exc:
            raise HTTPException(
                403, "No current private-evaluation approval permits this work.") from exc
        if not session_current(request, actor):
            raise HTTPException(401, "Your session ended. Sign in to see the saved work.")
        # The projection enumerates trusted structural receipts. Neither the
        # candidate, question, private prompt nor unchecked diagnostics are a
        # second answer channel. Ordinary released answers still use _release.
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        spend: Spend = result.budget.spend
        matter = owned(matter_id, actor)
        return {"turn_id": body.turn_id, "matter_version": matter.version,
            "result_state": "not_released", "client_ready": False,
            "message": "The work is saved for checking. No legal answer has been released.",
            "attempts": [{"turn_id": row.record.identity.turn_id,
                          "terminal": row.record.terminal,
                          "event_count": len(row.record.events)} for row in result.attempts],
            "assessment_count": len(result.assessments), "spend": spend.as_dict()}

    return routes
