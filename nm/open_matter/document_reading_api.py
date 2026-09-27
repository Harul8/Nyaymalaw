"""Owned local document requests; neither upload nor model output grants analysis.

The actual trusted checker is configured by the installation. HTTP callers
can instruct local reading, but cannot supply a clearance, parser or actor.
No raw original is released through this transport.
"""
from collections.abc import Callable
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from nm.open_matter.matter_documents_port import DocumentReadInstruction, DocumentRefused
from nm.open_matter.uploads_api import UploadRefused
from nm.shared.storage_errors_port import StoredObjectScopeRefused, StoredObjectUnreadable
from nm.shared.store_port import StaleWrite

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
OriginalId = Annotated[str, Field(min_length=1, max_length=100,
                               pattern=r"^[A-Za-z0-9_-]+$")]


class VersionedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: int = Field(ge=1)


class ReadRequest(VersionedRequest):
    request_key: str = Field(min_length=1, max_length=100)
    original_id: OriginalId
    asset_version: int = Field(ge=1)
    source_sha256: Sha256
    purpose: str = Field(min_length=1, max_length=2000)
    authority: str = Field(min_length=1, max_length=2000)
    analysis_allowed: bool


class QuoteRequest(VersionedRequest):
    original_id: OriginalId
    asset_version: int = Field(ge=1)
    source_sha256: Sha256
    derivative_sha256: Sha256
    number: int = Field(ge=1)
    location_kind: str = Field(min_length=1, max_length=100)
    part: str = Field(min_length=1, max_length=1000)
    start: int = Field(ge=0)
    end: int = Field(ge=1)


class SearchRequest(VersionedRequest):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=200, ge=1, le=200)


class RevokeRequest(VersionedRequest):
    original_id: OriginalId


def router(*, owned: Callable, signed_in: Callable, session_current: Callable,
           csrf_protected: Callable, service_for: Callable) -> APIRouter:
    routes = APIRouter()

    def perform(request, response, matter_id, actor, body, operation):
        matter = owned(matter_id, actor)
        if matter.version != body.version:
            raise HTTPException(409, "The file changed. Reopen it before continuing.")
        def current():
            return session_current(request, actor)
        if not current():
            raise HTTPException(401, "Your session ended. Sign in to continue.")
        service = service_for(session_current=current)
        if service is None:
            raise HTTPException(503, "Local document reading is not configured.")
        try:
            result = operation(service)
        except StaleWrite as exc:
            raise HTTPException(409, "The file changed. Reopen it before continuing.") from exc
        except UploadRefused as exc:
            raise HTTPException(exc.status, "That original is not available for this request.") \
                from exc
        except DocumentRefused as exc:
            raise HTTPException(422, "The exact document cannot be read under this instruction.") \
                from exc
        except (StoredObjectScopeRefused, StoredObjectUnreadable, OSError) as exc:
            raise HTTPException(503, "The protected document could not be opened safely.") from exc
        if not current():
            raise HTTPException(401, "Your session ended. Sign in to see the saved receipt.")
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return {"matter_version": owned(matter_id, actor).version, "result": result,
                "facts_established": False, "external_processing_granted": False}

    @routes.post("/api/matters/{matter_id}/documents/analyse",
                 dependencies=[Depends(csrf_protected)])
    def analyse(request: Request, response: Response, matter_id: str, body: ReadRequest,
                actor: str = Depends(signed_in)):
        try:
            instruction = DocumentReadInstruction(actor_id=actor,
                **body.model_dump(exclude={"version"}))
        except ValueError as exc:
            raise HTTPException(
                422, "Give an explicit, complete local-reading instruction.") from exc
        def operation(service):
            return service.analyse(matter_id, actor, body.version, instruction)
        return perform(request, response, matter_id, actor, body, operation)

    @routes.post("/api/matters/{matter_id}/documents/search",
                 dependencies=[Depends(csrf_protected)])
    def search(request: Request, response: Response, matter_id: str, body: SearchRequest,
               actor: str = Depends(signed_in)):
        return perform(request, response, matter_id, actor, body, lambda service: asdict(
            service.search(matter_id, actor, body.version, body.query, limit=body.limit)))

    @routes.post("/api/matters/{matter_id}/documents/quote",
                 dependencies=[Depends(csrf_protected)])
    def quote(request: Request, response: Response, matter_id: str, body: QuoteRequest,
              actor: str = Depends(signed_in)):
        return perform(request, response, matter_id, actor, body, lambda service: asdict(
            service.quote(matter_id, actor, body.version,
                          **body.model_dump(exclude={"version"}))))

    @routes.post("/api/matters/{matter_id}/documents/revoke",
                 dependencies=[Depends(csrf_protected)])
    def revoke(request: Request, response: Response, matter_id: str, body: RevokeRequest,
               actor: str = Depends(signed_in)):
        return perform(request, response, matter_id, actor, body, lambda service:
            service.revoke(matter_id, actor, body.version, body.original_id))

    return routes
