"""Empty-body authenticated private display acknowledgement; no wording input."""
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import BaseModel, ConfigDict

from nm.Archives.legal_brain.communicate.preview_seen import PreviewDisplayReceipt
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused
from nm.shared.store_port import StaleWrite


class PreviewSeenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def router(*, owned: Callable, signed_in: Callable, session_current: Callable,
           csrf_protected: Callable, record: Callable) -> APIRouter:
    routes = APIRouter()

    @routes.post("/api/matters/{matter_id}/brain/reviewed-preview/{turn_id}/seen",
                 dependencies=[Depends(csrf_protected)])
    def acknowledge(request: Request, response: Response, matter_id: str,
                    turn_id: Annotated[str, Path(min_length=1, max_length=100,
                                                pattern=r"^[A-Za-z0-9_-]+$")],
                    body: PreviewSeenRequest, actor: str = Depends(signed_in)):
        headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        response.headers.update(headers)
        owned(matter_id, actor)
        if body.model_dump():
            raise HTTPException(422, "A private display acknowledgement carries no supplied words.")
        if not session_current(request, actor):
            raise HTTPException(
                401, "Your session ended. Sign in before acknowledging the preview.",
                headers=headers)
        try:
            receipt = record(actor=actor, matter_id=matter_id, turn_id=turn_id,
                             session_current=lambda: session_current(request, actor))
        except PermissionError as exc:
            raise HTTPException(403, "No current private-preview approval permits this read.",
                                headers=headers) from exc
        except (ReviewRefused, StaleWrite, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(409, "The checked preview is unavailable or changed. Reopen it.",
                                headers=headers) from exc
        if not session_current(request, actor):
            raise HTTPException(
                401, "Your session ended. The display record is not being returned.",
                headers=headers)
        matter = owned(matter_id, actor)
        if (not isinstance(receipt, PreviewDisplayReceipt) or receipt.matter_id != matter_id
                or receipt.turn_id != turn_id or receipt.matter_version != matter.version):
            raise HTTPException(409, "The exact display record is unavailable. Reopen the preview.",
                                headers=headers)
        return receipt.as_dict()

    return routes
