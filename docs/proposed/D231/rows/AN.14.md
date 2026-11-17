# AN.14 - Build: the tool's details that need markup or script (P52, P51 piece 4)

Row 241 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.14

## Item

Build: the tool's details that need markup or script (P52, P51 piece 4)

## Description

SEES: the top bar's person button with the advocate's initials; the answer's own header (the NM mark, Nyaymalaw and the time); deadline chips with their icon and the days left; and, when the AI account's usage is exhausted (P51), the owner's sentence with Upgrade and See plans, the message kept in the box. MUST NEVER: change a saved answer or how it is read back (P46); show colour without words. PIECES: index.html and app.js, one file a piece, each with its focused test. Not started.

## Governs or depends on

P52; P51; AN.11; P46

## Status

Agreed 25 Oct 2026 (O23). Not started. | BUILT 25 Oct 2026: piece 1 (e853bfa0, app.js) the used-up AI account's message shown plainly in the owner's words, then whether the message was saved and Send this brief again (AN.11 piece 4); piece 2 (f675c3f2, app.css) that message in brass; piece 3 (9de597a0, app.js) deadline chips say the days left and how near the day is - urgent at 7 days or fewer, soon at 30 or fewer, open beyond, expired once passed (thresholds Claude's reading of the design: TO CONFIRM); piece 4 (bb7fa2f4, app.css) the chips' colours and marks. DONE OFFLINE: tests/js/turn_refusal.mjs and checklist_board.mjs extended (each fails on the earlier app.js), every renderer test, the JS wrapper and page-script tests. NOT YET: the owner's browser. NOT BUILT: the person button's initials and the answer's own header (optional polish); an Upgrade button (nothing to upgrade to until plans and payment exist). | CONFIRMED 25 Oct 2026 (O24 item 2): the chips' thresholds stand - urgent at 7 days or fewer, soon at 30 or fewer. | 26 Oct 2026: the person button's initials and the answer's own header, listed above as not built, are built as AN.20.
