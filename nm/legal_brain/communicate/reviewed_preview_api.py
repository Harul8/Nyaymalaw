"""Separate authenticated read of checked fictional preview, never raw private work."""
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response

from nm.legal_brain.communicate.reviewed_preview import PreviewSource, ReviewedPreview
from nm.legal_brain.verify.brain_release import ReviewRefused
from nm.shared.store_port import StaleWrite


def router(*, owned: Callable, signed_in: Callable, session_current: Callable,
           read: Callable, read_source: Callable | None = None,
           present_source: Callable | None = None) -> APIRouter:
    routes = APIRouter()

    @routes.get("/api/matters/{matter_id}/brain/reviewed-preview/{turn_id}")
    def preview(request: Request, response: Response, matter_id: str,
                turn_id: Annotated[str, Path(min_length=1, max_length=100,
                                            pattern=r"^[A-Za-z0-9_-]+$")],
                actor: str = Depends(signed_in)):
        headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        response.headers.update(headers)
        before = owned(matter_id, actor)
        try:
            result = read(actor=actor, matter_id=matter_id, turn_id=turn_id,
                          session_current=lambda: session_current(request, actor))
        except PermissionError as exc:
            raise HTTPException(403, "No current fictional-preview approval permits this read.",
                                headers=headers) from exc
        except StaleWrite as exc:
            raise HTTPException(409, "The file changed. Reopen it before continuing.",
                                headers=headers) from exc
        except (ReviewRefused, ValueError, KeyError, TypeError) as exc:
            # Never echo an internal exception: it may contain withheld text.
            raise HTTPException(409, "The saved work is not currently available for preview.",
                                headers=headers) from exc
        if not session_current(request, actor):
            raise HTTPException(401, "Your session ended. Sign in again.", headers=headers)
        after = owned(matter_id, actor)
        if (not isinstance(result, ReviewedPreview) or result.matter_id != matter_id
                or result.turn_id != turn_id):
            raise HTTPException(409, "The saved work is not currently available for preview.",
                                headers=headers)
        if before != after or result.matter_version != after.version:
            raise HTTPException(409, "The file changed. Reopen it before continuing.",
                                headers=headers)
        return result.as_dict()

    if (read_source is None) != (present_source is None):
        raise ValueError("Private-source reading and presentation must share one composition")
    if read_source is not None:
        @routes.get("/api/matters/{matter_id}/brain/reviewed-preview/{turn_id}/sources/{element_index}")
        def source(request: Request, response: Response, matter_id: str,
                   turn_id: Annotated[str, Path(min_length=1, max_length=100,
                                               pattern=r"^[A-Za-z0-9_-]+$")],
                   element_index: Annotated[int, Path(ge=0)],
                   actor: str = Depends(signed_in), offset: int = 0,
                   view: str = "passage", document_identity: str = "", reference: str = ""):
            headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
            response.headers.update(headers)
            before = owned(matter_id, actor)
            try:
                result = read_source(actor=actor, matter_id=matter_id, turn_id=turn_id,
                    element_index=element_index,
                    reference=reference,
                    session_current=lambda: session_current(request, actor))
                if not isinstance(result, PreviewSource) or result.matter_version != before.version:
                    raise ReviewRefused("The source is not bound to this checked private file")
                page = present_source(result.element.source, result.element, result.recorded_at,
                                      offset, view, document_identity)
            except PermissionError as exc:
                raise HTTPException(403, "No current fictional-preview approval permits this read.",
                                    headers=headers) from exc
            except (StaleWrite, ReviewRefused, ValueError, KeyError, TypeError) as exc:
                raise HTTPException(409, "The checked private source is not currently available.",
                                    headers=headers) from exc
            if not session_current(request, actor):
                raise HTTPException(401, "Your session ended. Sign in again.", headers=headers)
            if owned(matter_id, actor) != before:
                raise HTTPException(409, "The file changed. Reopen the source.", headers=headers)
            return page

    return routes
