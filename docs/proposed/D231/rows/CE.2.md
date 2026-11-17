# CE.2 - Source-only checkpoint (earlier M1)

Row 46 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

CE.2

## Item

Source-only checkpoint (earlier M1)

## Description

ENTRY: once authorised and implemented, a signed-in advocate sends a message in a new or core-engine conversation.
DOES: interpret all requests in the complete attributed conversation; check recognised case citations; search each legal question; display checked citation results and exact candidate sources, explicitly as candidates.
NEVER: infer legal conclusions from lookup, claim a task complete from a model call, or mix users or matters.
PRODUCES: a version-checked atomic save of input, admitted results, operation evidence and the exact reply, before release.
REFUSES: unauthenticated input, missing context, ambiguous ownership, stale version or unsupported historical replay.
RECOVERS: one shared correction for malformed model output; preserve independent checked results; use a truthful service status for unavailable processing. Lost acknowledgement uses durable lookup or the same idempotency key, never a fresh effect.
EXIT: the saved reply reopens unchanged with the same evidence.
CALLS: target 1 understanding call, plus 1 batched search-enquiry call where needed; at most 1 shared correction. E3 is separate.
EVAL: offline public-boundary checks, then an authorised browser run. This is the earlier source-only contract retained as history. SEQ.1-4 owns the current answer pipeline and its acceptance.

## Governs or depends on

1.1, 1.2.1, 3.2.1, 3.3.1, 3.5.4; A1-A3 (sources only), A7, B5 (citations)

## Status

Historical private source-only candidate; not the current served answer pipeline.

## Notes

Earlier M1 candidate reportedly passed 249 scripted checks before being paused; historical evidence only. Preserved in .nm/paused-core-engine-m1/. Its source-only contract spans SEQ.1-SEQ.3 and requires fresh integration evidence. SEQ.4 adds grounded answers under S3. Current cleanup activates neither.
