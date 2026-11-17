# Sequence - Core-first build order

Row 157 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

Sequence

## Item

Core-first build order

## Description

Prioritise dependencies that determine trustworthy legal answers. Each sequence contains smaller atomic prompt/file slices. The development app now serves the core engine; SEQ.1-4 remains under quality and browser validation. Later stages remain planned. Paid experiments retain separately approved scope and spending under P16; integrated code alone does not complete a stage.

## Governs or depends on

Owner direction 10 Oct 2026; CE.3; P5/P6

## Status

SEQ.1-4 integrated for development validation; SEQ.5-9 planned.

## Notes

2026-10-14 PROPOSED ORDER after retrieval (owner froze retrieval for now and asked for a prioritised plan of downstream and upstream work; awaiting owner agreement). 1. Long turns with visible progress (upstream; SEQ.1/SEQ.4): a turn now takes about 3.5-5 minutes, accepted only with progress shown; run the turn as a background job the page can follow and resume after a reload, showing each stage. 2. Bounded paid end-to-end check of the new pipeline on a few test matters (downstream; SEQ.3/SEQ.4): writer input size against its 100,000-token budget, latency per stage, cost, release or withhold, answers read against the conversations. 3. Answer composition and independent review for research v7 (downstream; SEQ.4): answers organised by dispute and legal question, related points offered for the advocate's decision (owner decision 2 of 13 Oct), limits and next steps, built as a reasoning loop. 4. UI design pass (upstream): mock-ups of the whole advocate workspace (conversation, sources pane, matter board, related-point decisions, progress, uploads, voice) for owner review before building. 5. Conversation continuity and matter board (upstream; SEQ.5): carry the matter understanding forward and revise it instead of rebuilding each turn; restrictions, corrections and related-point decisions persist; faster follow-ups. 6. Document uploads with custody, readability and grounded summaries (upstream; SEQ.6). 7. Research note and documentation export with citations (downstream; SEQ.6/SEQ.7). 8. Voice notes and transcription (upstream; SEQ.8; needs provider permission). 9. Checked calculations (limitation dates first) and drafting (downstream; SEQ.7). Open decisions carried: currency register (SEQ.4), judgment pick (after the owner's review page), speed of the question-breakdown loop.
2026-10-14 OWNER DECISION: the proposed order is approved; implement items 1-9 one after the other; Claude takes the logical decisions needed and moves ahead (each recorded here before dependent implementation); up to $5 more may be spent on paid checks (tracked in its own ledger, outputs/core-engine-build-20261010/api-budget-20261014-owner5.sqlite). Standing safeguards still apply: atomic changes with focused offline tests, no full suite, gate or journeys, never force-push, downloads and outside processing only within what is installed or already permitted unless the owner is asked.
