"""Injectable authenticated account-memory routes, without an API-owner import."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from nm.arrive.directory_port import AccountBusy, DirectoryPort, MemoryStale, MemoryUnavailable
from nm.Archives.legal_brain.understand.advocate_memory import delete_memory, memory_view, save_memory
from nm.Archives.legal_brain.understand.advocate_memory_contracts import PreferenceKey


class PreferenceApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: StrictBool
    expected_version: int = Field(strict=True, ge=0)


class PreferenceUpdateRequest(PreferenceApprovalRequest):
    settings: dict = Field(max_length=len(PreferenceKey))


def install_advocate_memory_routes(
    app,
    *,
    authenticated: Callable,
    csrf_protected: Callable,
    directory: Callable[[], DirectoryPort],
    clock: Callable[[], datetime],
) -> None:
    """Root owns authentication/CSRF/session freshness; no caller-selected account."""
    router = APIRouter(prefix="/api/account/advocate-memory")

    def execute(operation):
        try:
            return operation()
        except (AccountBusy, MemoryStale) as exc:
            raise HTTPException(
                409, "Preferences changed or the account is busy. Reload and retry."
            ) from exc
        except MemoryUnavailable as exc:
            raise HTTPException(
                503, "Preference memory is unavailable. Nothing was changed."
            ) from exc
        except ValueError as exc:
            # Fixed schema explanations, never echo rejected client/source material.
            raise HTTPException(
                422, "Only explicitly approved supported preferences are accepted."
            ) from exc

    @router.get("")
    def read(account_id: str = Depends(authenticated)):
        return execute(lambda: memory_view(directory(), account_id))

    @router.put("", dependencies=[Depends(csrf_protected)])
    def write(request: PreferenceUpdateRequest, account_id: str = Depends(authenticated)):
        port = directory()
        execute(
            lambda: save_memory(
                port,
                account_id,
                request.settings,
                approved=request.approved,
                expected_version=request.expected_version,
                now=clock(),
            )
        )
        return execute(lambda: memory_view(port, account_id))

    def remove(request, account_id, key):
        port = directory()
        execute(
            lambda: delete_memory(
                port,
                account_id,
                key,
                approved=request.approved,
                expected_version=request.expected_version,
                now=clock(),
            )
        )
        return execute(lambda: memory_view(port, account_id))

    @router.delete("", dependencies=[Depends(csrf_protected)])
    def remove_all(request: PreferenceApprovalRequest, account_id: str = Depends(authenticated)):
        return remove(request, account_id, None)

    @router.delete("/{key}", dependencies=[Depends(csrf_protected)])
    def remove_entry(
        key: PreferenceKey,
        request: PreferenceApprovalRequest,
        account_id: str = Depends(authenticated),
    ):
        return remove(request, account_id, key)

    app.include_router(router)
