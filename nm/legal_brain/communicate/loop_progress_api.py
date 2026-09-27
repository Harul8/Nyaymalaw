"""Read-only authenticated progress from the sealed matter journal.

No route here starts a loop or releases a candidate. Following work is a
bounded view of already-committed stage receipts; the session and ownership
are checked again before each frame, including after a wait.
"""

import asyncio
from collections.abc import Callable
from time import monotonic

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from nm.legal_brain.communicate.loop_progress import (
    InvalidProgressCursor,
    cursor_at,
    links_released_turn,
    progress,
    resume_position,
    sse_frame,
)

FOLLOW_SECONDS = 30
POLL_SECONDS = 0.5


def router(*, owned: Callable, signed_in: Callable, session_current: Callable) -> APIRouter:
    routes = APIRouter()

    def record_for(matter_id, turn_id, actor):
        matter = owned(matter_id, actor)
        rows = [row for row in matter.loop_records if row.identity.turn_id == turn_id]
        if not rows:
            raise HTTPException(404, "no such recorded work")
        if (
            len(rows) != 1
            or rows[0].identity.advocate_id != actor
            or rows[0].identity.matter_id != matter_id
        ):
            raise HTTPException(503, "The complete work record could not be verified.")
        return matter, rows[0]

    @routes.get("/api/matters/{matter_id}/loops")
    def loops(matter_id: str, advocate_id: str = Depends(signed_in)) -> dict:
        matter = owned(matter_id, advocate_id)
        if any(
            row.identity.matter_id != matter_id or row.identity.advocate_id != advocate_id
            for row in matter.loop_records
        ):
            raise HTTPException(503, "The complete work record could not be verified.")
        return {
            "loops": [
                {
                    "turn_id": row.identity.turn_id,
                    "terminal": row.terminal,
                    "event_count": len(row.events),
                    "result_state": "not_released",
                    "linked_released_turn": links_released_turn(matter, row),
                    "cursor": cursor_at(row, len(row.events)),
                }
                for row in matter.loop_records
            ]
        }

    @routes.get("/api/matters/{matter_id}/loops/{turn_id}")
    def recorded(matter_id: str, turn_id: str, advocate_id: str = Depends(signed_in)) -> dict:
        matter, record = record_for(matter_id, turn_id, advocate_id)
        return progress(record, linked_turn=links_released_turn(matter, record))

    @routes.get("/api/matters/{matter_id}/loops/{turn_id}/progress")
    async def streamed(
        request: Request,
        matter_id: str,
        turn_id: str,
        advocate_id: str = Depends(signed_in),
        follow: bool = True,
        last_event_id: str | None = Header(default=None),
        after: str | None = None,
    ):
        # An invalid cursor is rejected before response headers or bytes leave.
        supplied_cursor = last_event_id if last_event_id is not None else after
        _, record = record_for(matter_id, turn_id, advocate_id)
        try:
            position = resume_position(record, supplied_cursor)
            if after is not None and resume_position(record, after) > position:
                raise InvalidProgressCursor("A reconnect cannot move behind its starting position.")
        except InvalidProgressCursor as exc:
            raise HTTPException(409, "The saved progress position could not be verified.") from exc
        cursor = cursor_at(record, position)

        async def frames():
            nonlocal cursor
            started = monotonic()
            while True:
                if await request.is_disconnected() or not session_current(request, advocate_id):
                    return
                try:
                    _, current = record_for(matter_id, turn_id, advocate_id)
                    projected = progress(current, after=cursor)
                except (HTTPException, InvalidProgressCursor):
                    # A mid-stream revocation or changed journal closes the
                    # view. The ordinary authenticated read names any failure;
                    # no stale source or sensitive diagnostic follows it.
                    return
                for row in projected["events"]:
                    if await request.is_disconnected() or not session_current(request, advocate_id):
                        return
                    try:
                        _, latest = record_for(matter_id, turn_id, advocate_id)
                        resume_position(latest, row["cursor"])
                    except (HTTPException, InvalidProgressCursor):
                        return
                    yield sse_frame(row)
                    cursor = row["cursor"]
                if current.terminal or not follow or monotonic() - started >= FOLLOW_SECONDS:
                    return
                await asyncio.sleep(POLL_SECONDS)

        return StreamingResponse(
            frames(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return routes
