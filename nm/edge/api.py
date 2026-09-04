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

from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AfterValidator, BaseModel, Field

from nm.core.turn import TurnEngine, TurnInput, TurnRefused
from nm.domain import summary as matter_memory
from nm.domain.answer import Answer
from nm.domain.identity import source_fingerprint
from nm.domain.traceability import implements
from nm.edge.projections import board_projection, matter_list_projection
from nm.ports.store import StaleWrite

ROOT = Path(__file__).resolve().parents[2]

app = FastAPI(title="Nyaymalaw", version="0.1.0")
_application = None


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
            }
            for e in answer.elements
        ],
        metrics=output.metrics.as_dict(),
        replayed=output.replayed,
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

#: The SAME guard on the read path. A1 restores the matter list only
#: after authentication succeeds, and a blank query parameter is not an
#: authenticated session -- it returned 200 and an empty list, which
#: reads to a caller as "this advocate has no matters" rather than as
#: "you are not signed in".
Advocate = Annotated[str, Query(min_length=1), AfterValidator(_not_blank)]


class TurnRequest(BaseModel):
    advocate_id: NonBlank = Field(min_length=1)
    message: NonBlank = Field(min_length=1)
    matter_id: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None
    today: date | None = None
    jurisdiction: str = "Telangana"


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
#: The mechanism is not new. `nm/domain/identity.py` already existed (in
#: `tools/`) so a mutation record could not certify code it never saw, and
#: `nm/knowledge/artefact.py` makes the same argument about the dense index:
#: the only reason that index was KNOWABLY unusable is that it shipped an
#: identity. A running process is an artefact and needs one too.
try:
    SERVING = source_fingerprint()
except Exception as exc:  # noqa: BLE001 -- NOT ASSESSED, said as a value
    # Never a digest that happens to differ, and never one that happens to
    # match: a value that cannot be computed says so in words no comparison
    # will read as agreement.
    SERVING = f"unknown: {type(exc).__name__}"


@app.get("/api/health")
def health() -> dict:
    return {**application().health(), "serving": SERVING}


@app.get("/api/matters/{matter_id}/transcript")
def transcript(matter_id: str, advocate_id: Advocate) -> dict:
    """THE CONVERSATION, AS IT WAS SERVED. For review, later.

    Every turn on this matter in full — what the advocate wrote, what came
    back, which gates fired and what was violated. Nothing else keeps it: the
    matter holds facts, the metrics hold counts and no client words, and the
    answer was held by neither.

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
        "state": "ok" if not unreadable else "incomplete",
        "matter_id": matter_id,
        "title": m.title,
        "turns": [t for t in turns if not t.get("unreadable")],
        "turn_count": len(turns),
        "unreadable": [t["turn_id"] for t in unreadable],
        "unreadable_reason": (
            f"{len(unreadable)} turn(s) on this matter could not be read back "
            f"and are missing from what follows."
            if unreadable else None),
        "unattributable_count": len(lost),
        "unattributable_reason": (
            f"{len(lost)} transcript(s) in the store could not be read back at "
            f"all, so which matter they belong to is unknown. They may or may "
            f"not be from this one."
            if lost else None),
    }


@app.get("/api/matters")
def matters(advocate_id: Advocate) -> dict:
    """THE MATTER LIST. One row per matter, nearest deadline first.

    Bounded by MATTER count -- never by threads, turns or facts.
    """
    return matter_list_projection(application().store.list_for(advocate_id))


@app.get("/api/matters/{matter_id}")
@implements("A1")
def matter(matter_id: str, advocate_id: Advocate) -> dict:
    """THE THREAD BOARD. One row per thread, bounded by THREAD count."""
    m = application().store.load(matter_id)
    if m is None or m.advocate_id != advocate_id:
        # The same response whether it does not exist or belongs to someone
        # else: a failed lookup must disclose nothing about what exists.
        raise HTTPException(status_code=404, detail="no such matter")
    # `None`, WRITTEN OUT. This view computes no deadline register -- the
    # register is derived on a turn, from the retrieval that turn made -- and
    # `None` is what says so. It was an omitted argument defaulting to `()`,
    # and every row then reported a file with no deadlines on it.
    return board_projection(m, None)


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


@app.post("/api/turn")
def turn(req: TurnRequest) -> _Released:
    engine: TurnEngine = application().engine
    payload = TurnInput(
        advocate_id=req.advocate_id,
        message=req.message,
        matter_id=req.matter_id,
        # The advocate naming a thread OUTRANKS every heuristic. The only
        # source better than a number of record is the person holding the file.
        thread_id=req.thread_id,
        today=req.today or date.today(),
        jurisdiction=req.jurisdiction,
        **({"turn_id": req.turn_id} if req.turn_id else {}),
    )
    try:
        output = engine.run(payload)
    except TurnRefused as exc:
        # 422 with the REASON, not just the refusal. The disclosures assert no
        # law -- they say what could not be established -- so passing them
        # through the byte boundary is safe, and withholding them as well would
        # leave the advocate with a dead end.
        raise HTTPException(status_code=422, detail={
            "withheld_by": list(getattr(exc, "gates", ())),
            "why": getattr(exc, "message", str(exc)),
            "not_established": list(getattr(exc, "disclosures", ())),
        }) from exc
    except StaleWrite as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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


# ------------------------------------------------------------------- static ---

_WEB = ROOT / "web"
if _WEB.exists():
    app.mount("/static", StaticFiles(directory=str(_WEB)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(str(_WEB / "index.html"))
