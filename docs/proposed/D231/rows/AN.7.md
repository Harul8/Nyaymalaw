# AN.7 - Build: reopen from what is saved (P46)

Row 217 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.7

## Item

Build: reopen from what is saved (P46)

## Description

SEES: a conversation reopened from history shows each answer exactly as saved, at once; the board, the files and the reading pane read the saved record; the reading pane shows the saved passage and NM's saved checks for it. MUST NEVER: rebuild, re-check or re-render a saved answer when reading it (opening, continuing, the board, the files, the reading pane, the research note); show a record that fails its seal, digest-chain or ownership checks; change a saved record; present an earlier answer as fresh advice. WHEN IT FAILS: a conversation whose record fails those checks says it cannot be read reliably, its records unchanged. DONE: no reading path calls the rebuild (each caller listed from the source); every saved conversation in a copy of the owner's store opens showing exactly its saved answers, read only; the time to open measured before and after; a new answer is still checked once, when it is saved.

## Governs or depends on

P46; O13 (1); P35; nm/core_engine/turn.py, conversation.py; nm/app/api.py

## Status

Agreed 24 Oct 2026 (O13 (1)). Not built. Built before AN.6. | BUILT 24 Oct 2026 (nm/core_engine/turn.py: saved_rows reads the record's checks only - conversation.checked_rows and known_activity, the turn and rendering versions this code reads; the rebuild and its per-process memory removed; the one check at saving, and saving what an unfinished turn showed, keep P35's derive-once scope). Every reader goes through saved_rows: opening, continuing, the board, the files, the reading pane, the research note. Checked offline: 194 focused tests passed (reopening, turn, served app, source view, calculation, checklist, board, layout, sections, research note); a copy of the owner's store, read only: all 8 saved conversations open with every answer identical to before, in 0.2 s together (3.8 s before; the 28.9 MB one 0.11 s, 2.4 s before). Not yet checked in the owner's browser.

## Notes

Callers that rebuild on reading, found in the source 24 Oct 2026: opening a conversation (api.py, through turn.saved_rows) and continuing one before a new message is answered (turn.process, through saved_rows). The board, the files list and the reading pane read through the same opening path. | Changed with it: a record resealed with its digests made whole is now read as saved (before, a change inconsistent with the turn's own drafts was caught by the rebuild); a record of a turn or rendering version this code does not read is still refused. The tests that expected the rebuild to catch such a record now expect P46 (tests/test_core_turn.py, test_core_reopen_speed.py).
