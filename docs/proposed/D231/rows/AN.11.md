# AN.11 - Build: the exhausted AI account named, not retried, kept and told (P51)

Row 231 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.11

## Item

Build: the exhausted AI account named, not retried, kept and told (P51)

## Description

SEES: when the provider's credit is out, the advocate is told once, in the owner's words, where NM used to say 'the AI service did not respond': a turn that cannot be answered is refused with 'You have run out of your usage limits. Please upgrade to continue accessing NM.' and can be sent again after upgrading; an answer that lost a step to it says so in that step's notice; the call record and the refused turn's diagnosis name UsageLimitReached; nothing waits on a retry. MUST NEVER: retry it; call it a rate limit or an unresponsive service; present an answer as complete when a check was lost to it; save a turn none of whose sections could be made; hide a step that failed; show the provider's message or any private data; change how rate limits, other provider failures or an evaluation's dollar cap behave. WHEN IT FAILS: as today - a step lost is noted in the answer; a turn that cannot be answered is refused and can be sent again. DONE: offline, a provider error carrying the exhausted-credit code is raised as UsageLimitReached after exactly one call while a plain rate limit is still retried; a scripted turn whose every call hits it is refused with the owner's words and the code usage_limit, its attempt left retryable; a scripted answer whose check across the sections and overview hit it is saved with the reason 'usage' and notices in the owner's words, and reopens as saved; live and free while the account has no credit, one real call through the shipped application is named and shown in the owner's words, with the spend recorded as nothing; the owner sees it in their browser. Pieces, each verified, committed and pushed before the next (the first and third are cross-file pairs that cannot be split: the class and where it is raised; one reason with its words and its checks): (1) model_port.py and model_transport.py; (2) turn.py; (3) answer_sections.py, response_review.py and response_rendering.py; (4) app.js, the refusal shown plainly.

## Governs or depends on

P51; O18

## Status

Agreed 25 Oct 2026 (O18). Not built. | BUILT 25 Oct 2026, pieces 1-3 (see P51); piece 4 (app.js) not built, held for the owner's view of the live message. DONE: met offline; met live for the turn (402 and the owner's words from the real provider's answer, one call, no retry, no spend); not met: an answer cut off part-way (needs paid calls) and the owner's browser. | 25 Oct 2026: piece 4 BUILT as AN.14 pieces 1-2 (e853bfa0, f675c3f2): the refusal shows the owner's words plainly, in brass.
