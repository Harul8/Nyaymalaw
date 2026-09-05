"""EVERY MODEL CALL, KEPT — what was asked, what came back, and whether it was empty.

WHY THIS EXISTS, AND WHAT IT IS NOT
-------------------------------------
`TurnMetrics` already records `llm_calls: 7`. It does not record WHICH seven,
what any of them was asked, what came back, or which one returned nothing.

That gap has a cost and it has been paid. B-088 -- the correction read fires on
one run and not the next, on identical input -- was diagnosed by running GS-15
twice and DIFFING TWO TRANSCRIPTS BY HAND, because nothing on the record said
what the correction read was given or what it answered. The unit tests could
not see it either: every reader in this build is tested by handing it a model
answer and checking the guards, which proves the guards and says nothing about
whether the read produces that answer.

So this is not a dashboard. It is the missing half of an existing record.

WHAT IT IS NOT: A VENDOR
--------------------------
Langfuse and Opik were both surveyed on 5 September 2026. Both are genuinely
open-source and both REQUIRE A RUNNING SERVER -- Langfuse self-hosted is six
containers (web, worker, Postgres, ClickHouse, Redis, MinIO) at a recommended
4 CPU / 16 GiB / 100 GiB; Opik's `configure(use_local=True)` connects to a
Docker Compose or Kubernetes deployment, it is not an offline mode.

Neither is needed to CLOSE the gap. The gap is that per-call detail is not
kept; a hosted UI is a pleasant way to browse records that exist. So the
record is made first, in this product's own vocabulary, and exporting it --
both accept OTLP over HTTP -- stays a later, optional adapter that touches
nothing in `nm/`. That is the answer to "what refuses the second copy": the
call record has ONE owner and no provider SDK reaches the core.

WHERE IT GOES, AND WHY THAT IS ALREADY DECIDED
------------------------------------------------
A prompt contains everything the advocate has said. `file_store` already draws
the line this needs: `record_metrics` is plaintext BECAUSE it carries no client
words, and `record_turn` gets the matter cipher because it does. A call trace
is transcript-class material, so it rides in the TRANSCRIPT rather than in a
store of its own -- which also refuses a fourth store of one conversation, the
shape CLAUDE.md records against the three provision stores.

A TRACE MUST NEVER FAIL A TURN
--------------------------------
The advocate's answer is worth more than the record of how it was produced.
Every failure here is swallowed and counted; a trace that stopped working is
visible in `dropped` rather than discovered months later by its absence.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from nm.domain.reads import is_decisive
from nm.domain.text import refuses_blank_text
from nm.ports.model import EmbeddingResult, ModelPort, ModelResult, Prompt, Tier, TierUnavailable

#: How much of a prompt or an answer is kept per call.
#:
#: The account is budgeted at 3000 characters and a turn makes on the order of
#: fifteen calls, so keeping everything in full would make the transcript an
#: order of magnitude larger than the conversation it records. 4000 holds the
#: whole of every prompt this build actually sends while bounding the one that
#: grows unexpectedly -- and a truncated field SAYS it was truncated, because a
#: prompt silently cut at a boundary is a diagnosis pointing at the wrong line.
KEEP = 4000

_ELIDED = "\n[... {n} more characters not kept ...]"


def _clip(text: str | None) -> str:
    if not text:
        return ""
    if len(text) <= KEEP:
        return text
    return text[:KEEP] + _ELIDED.format(n=len(text) - KEEP)


def read_name(schema: Mapping[str, Any] | None) -> str:
    """WHICH READ THIS WAS, which is the whole diagnostic value.

    `x-nm-read` is this product's own marker and every structured schema
    carries one. A schema without it falls back to its title and then to
    `unnamed` -- reported as a VALUE rather than left blank, because a blank
    here reads as "no schema was sent", which is a different and more serious
    thing than "the schema was not labelled".
    """
    if not schema:
        return "no schema — free text"
    return str(schema.get("x-nm-read") or schema.get("title") or "unnamed")


@refuses_blank_text("model", "provider")
@dataclass(frozen=True)
class Call:
    """One model call, as the product would describe it.

    `model` and `provider` are EXEMPT, and the exemption is the failure path.
    A call that raised has no resolved model and may have no provider -- the
    exception arrived before either was known -- and refusing the blank would
    refuse to record the call most worth having. `kind`, `read` and `tier` are
    guarded: each is produced by this module from a closed set, so a blank one
    means the tracer itself is broken, and a trace naming no read is a record
    that cannot be read.

    `empty` is the field this was built for. A structured read that returns
    `{}` or a data block with nothing in it is the S1 shape at the model
    boundary -- an absent answer that every downstream guard treats as "the
    thing was not there". It is recorded as its own fact rather than left to
    be inferred from the answer bytes.
    """

    ordinal: int
    kind: str                 # "structured" | "complete" | "embed"
    read: str
    tier: str
    model: str
    provider: str
    latency_ms: int
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens: int = 0
    retries: int = 0
    downgraded_from: str | None = None
    system: str = ""
    user: str = ""
    answer: str = ""
    empty: bool = False
    failed: str = ""
    """The exception, where the call RAISED.

    A call that failed is the one most worth having a record of, and it is the
    one a naive tracer loses -- recording on the way back means recording
    nothing when there is no way back.
    """

    def as_dict(self) -> dict:
        return {
            "n": self.ordinal, "kind": self.kind, "read": self.read,
            "tier": self.tier, "model": self.model, "provider": self.provider,
            "latency_ms": self.latency_ms,
            "tokens": {"in": self.tokens_in, "out": self.tokens_out,
                       "cached": self.cached_tokens},
            "retries": self.retries,
            "downgraded_from": self.downgraded_from,
            "system": self.system, "user": self.user,
            "answer": self.answer, "empty": self.empty,
            "failed": self.failed,
        }


def _is_empty(result: ModelResult, schema: Mapping[str, Any] | None = None
              ) -> bool:
    """Did the model fail to ANSWER — which is not the same as answering none.

    THE DISTINCTION THIS FUNCTION EXISTS FOR, and it was got wrong first.
    `{"events": []}` from the date read is a CORRECT, schema-conformant answer
    meaning "there are no dates in this message". Treating it as an absence
    made G-READ fire on 77% of turns across all 13 scripted scenarios, every
    one of them the date read — which is a real answer reported as a failure,
    the S1 shape committed inside the mechanism built to refuse S1.

    A NON-ANSWER is `data` missing altogether, an empty object, or an object
    that omits a key the schema declares REQUIRED. That is the model failing
    to produce the shape it was asked for, and it is rare.
    """
    if result.data is None:
        return not (result.text or "").strip()
    if not result.data:
        return True
    required = list((schema or {}).get("required") or ())
    if required:
        return any(key not in result.data for key in required)
    # No schema to check against: an object with nothing in any field is the
    # best available reading of a non-answer.
    return not any(v not in (None, "", [], {}, ()) for v in result.data.values())


def _decisive(read: str) -> bool:
    """Does being wrong about this read change a number the advocate acts on?

    Asked of `nm.domain.reads`, which is the ONE table that decides it. A list
    here would be a second owner for one truth.
    """
    return is_decisive(read)


@dataclass
class TracedModel:
    """Any `ModelPort`, with every call kept.

    Satisfies the same Protocol and delegates everything, so nothing in the
    core knows it is here and the composition root decides whether to wrap.
    The alternative -- tracing inside each adapter -- is two owners of one
    decision, and a change described as global landing in half the product is
    the defect this file most wants to avoid being.
    """

    inner: ModelPort
    calls: list[Call] = field(default_factory=list)
    dropped: int = 0
    """Calls this failed to RECORD. Not calls that failed.

    Counted and reported rather than logged and forgotten: a tracer that has
    quietly stopped writing looks exactly like a turn that made no calls.
    """

    # -------------------------------------------------- pass-through -------

    @property
    def provider(self) -> str:
        return self.inner.provider

    def resolved_model(self, tier: Tier) -> str:
        return self.inner.resolved_model(tier)

    def context_budget(self, tier: Tier) -> int:
        return self.inner.context_budget(tier)

    # ------------------------------------------------------- traced --------

    def complete(self, prompt: Prompt, tier: Tier, *,
                 max_tokens: int | None = None) -> ModelResult:
        return self._traced("complete", "free text", prompt, tier,
                            lambda: self.inner.complete(
                                prompt, tier, max_tokens=max_tokens))

    def structured(self, prompt: Prompt, schema: Mapping[str, Any],
                   tier: Tier, *,
                   max_tokens: int | None = None) -> ModelResult:
        def run() -> ModelResult:
            try:
                return self.inner.structured(prompt, schema, tier,
                                             max_tokens=max_tokens)
            except TierUnavailable:
                # THE TIER IS NOT CONFIGURED HERE, AND THE ANSWER IS WORTH
                # LESS FOR IT. `nm/domain/reads.py` is explicit: a decisive
                # read that quietly falls back to the cheap tier is the same
                # defect as a screen that could not run returning a clean
                # result -- the answer looks identical and is worth less.
                #
                # So it degrades rather than failing the turn, and it says so:
                # `downgraded_from` is a field the port already has for
                # exactly this, and `TurnMetrics.record_call` already routes
                # it into `tier_downgrades`. Nothing new is invented; a
                # mechanism that existed and was never fed now is.
                if tier is Tier.ROUTINE:
                    raise
                result = self.inner.structured(prompt, schema, Tier.ROUTINE,
                                               max_tokens=max_tokens)
                return replace(result, downgraded_from=tier)

        return self._traced("structured", read_name(schema), prompt, tier,
                            run, schema=schema)

    def embed(self, texts: tuple[str, ...]) -> EmbeddingResult:
        """NOT TRACED, and that is a decision rather than an omission.

        An embedding call carries no prompt and no answer a person can read;
        what it would contribute is a latency and a count, both of which
        `TurnMetrics` already holds. Keeping the corpus text that was embedded
        would put the largest payloads in the build into every transcript to
        record the least diagnostic call.
        """
        return self.inner.embed(texts)

    # ------------------------------------------------------ the record -----

    def _traced(self, kind: str, read: str, prompt: Prompt, tier: Tier,
                run, schema: Mapping[str, Any] | None = None
                ) -> ModelResult:
        started = time.perf_counter()
        try:
            result = run()
        except Exception as exc:
            # THE FAILED CALL IS THE ONE MOST WORTH KEEPING, and recording on
            # the way back keeps nothing when there is no way back.
            self._keep(Call(
                ordinal=len(self.calls) + 1, kind=kind, read=read,
                tier=tier.value, model="", provider=self.inner.provider,
                latency_ms=int((time.perf_counter() - started) * 1000),
                system=_clip(prompt.system), user=_clip(prompt.user),
                failed=f"{type(exc).__name__}: {exc}"))
            raise

        self._keep(Call(
            ordinal=len(self.calls) + 1, kind=kind, read=read,
            tier=tier.value, model=result.model, provider=result.provider,
            latency_ms=result.latency_ms,
            tokens_in=result.usage.tokens_in,
            tokens_out=result.usage.tokens_out,
            cached_tokens=result.usage.cached_tokens,
            retries=result.retries,
            downgraded_from=(result.downgraded_from.value
                             if result.downgraded_from else None),
            system=_clip(prompt.system), user=_clip(prompt.user),
            answer=_clip(result.text if result.text is not None
                         else str(result.data)),
            empty=_is_empty(result, schema)))
        return result

    def _keep(self, call: Call) -> None:
        try:
            self.calls.append(call)
        except Exception:  # noqa: BLE001 -- a trace must never fail a turn
            self.dropped += 1

    # -------------------------------------------------------- drained ------

    def empty_decisive(self) -> tuple[str, ...]:
        """The decisive reads that answered with nothing THIS TURN.

        Read WITHOUT draining, because the turn asks this while deriving and
        the trace is drained after the commit. Two consumers of one list, and
        the one that resets is the later of them.
        """
        return tuple(sorted({c.read for c in self.calls
                             if c.empty and _decisive(c.read)}))

    def take(self) -> dict:
        """The trace for one turn, and RESET.

        Drained rather than read, because an instance lives for the process
        and a turn's trace that carried the previous turn's calls would put
        another matter's words into this matter's transcript.
        """
        calls = tuple(self.calls)
        dropped = self.dropped
        self.calls = []
        self.dropped = 0
        return {
            "calls": [c.as_dict() for c in calls],
            # WHICH DECISIVE READS ANSWERED WITH NOTHING.
            #
            # `empty` alone is a count and most empties are ordinary -- the
            # issues read finds no issue, the adverse read finds nothing
            # against us, and both are real answers. A DECISIVE read is the
            # one whose output IS a date, an amount, or which law is read, so
            # an empty answer there is indistinguishable from "that thing is
            # not present" and the arithmetic proceeds from the wrong value.
            "empty_decisive": sorted({c.read for c in calls if c.empty
                                      and _decisive(c.read)}),
            # COUNTS THAT ARE ALSO ANSWERS. `empty` is what B-088 needed and
            # no existing record held: how many reads answered with nothing.
            "count": len(calls),
            "empty": sum(1 for c in calls if c.empty),
            "failed": sum(1 for c in calls if c.failed),
            "dropped": dropped,
        }

