# AN.13 - Build: the tool's look - colour, type, cards and spacing (P52, P50 amended)

Row 240 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.13

## Item

Build: the tool's look - colour, type, cards and spacing (P52, P50 amended)

## Description

SEES: the signed-in tool in the signed-off design: ivory paper, the blue brand, white cards on the matter board and around the answer's boxes, serif prose in the answer, the In short table, folds, the composer and the reading pane restyled, and the answer, its tables and the message box inside 10% margins on each side of the column (P50 amended, O22). Light only (O23). Fonts: Source Serif 4 and Source Sans 3 are named first and fall back to the fonts already on the device, so the workspace still never asks a font service for anything; serving the fonts ourselves is AN.18. MUST NEVER: change what an answer says, what is saved or how anything behaves; hide, fold or shrink a disclosure; give the answer a width of its own (P50's test); declare a class twice; change the window's layout grid (P38). PIECES: one production file, nm/app/app.css, with the guard test for the 10% margin. PASS: the stylesheet's own tests pass, and the owner sees the new look on the served page. FAILURE SCOPE: display only. RECOVERY: revert the commit.

## Governs or depends on

P52; P50; P38; O22; O23

## Status

Agreed 25 Oct 2026 (O23). Building. | BUILT 25 Oct 2026, piece 1 (ca9afc62): app.css restyled to the signed-off design - tokens (ivory paper, blue brand, brass, the meaning colours), fonts named and never fetched, the top bar, the board's dispute cards and marks (Not available now a dashed grey ring, not red), the conversation on paper with the 10% margin (P50 amended), the advocate's bubble in blue, serif prose in the answer, dispute headings numbered with the section sign, the In short table, folds, the need and check cards, the working box, the composer with its focus ring, the reading pane, the sign-in story panel in deep blue and its card, the new-matter form, dialogs; the dark override removed (O23). DONE OFFLINE: the eight stylesheet test files (179 passed) with a new guard for the 10% margin. NOT YET: the owner's browser. | AMENDED 26 Oct 2026 by O27: the 'ivory paper' of this restyle is replaced by white in the app (AN.21).

## Notes

25 Oct 2026: one rule of the old sheet had never applied - a dispute heading's size lost to a more specific rule for every answer paragraph - so the heading is now sized by the more specific selector. The layout grid of P38 (the board's and the pane's widths) is unchanged and its tests still pin it; the design's slightly wider board and pane were not taken, to keep P38.
