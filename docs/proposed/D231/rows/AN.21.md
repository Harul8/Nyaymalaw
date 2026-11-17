# AN.21 - Build: white backgrounds in the app (P52 amended by O27)

Row 252 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.21

## Item

Build: white backgrounds in the app (P52 amended by O27)

## Description

SEES: the signed-in workspace and the sign-in page on white: the page, the conversation, the matter board, the reading pane's passages, the sign-in page behind its card and the register card's privacy notice, in white and not in ivory; the small tinted spots (table header rows, hover highlights, quiet labels, the recorder panel) in a very light cool grey, not beige; the tile behind the NM mark on the sign-in story panel in white. MUST NEVER: change the amber and brass meaning colours (warnings, the usage limit, near deadlines); change a layout, a width or what any screen says; touch the public site. PIECES: nm/app/app.css (the tokens --paper, --board and --surface-2, and the one tile), then a guard test (tests/test_the_app_background_is_white.py). PASS: the stylesheet tests pass, the guard fails if the beige returns, and the owner sees white in their browser. FAILURE SCOPE: colour only. RECOVERY: revert the commit.

## Governs or depends on

P52; AN.13; O27

## Status

Agreed 26 Oct 2026 (O27). Building. | BUILT 26 Oct 2026, pieces 1-2: (1) 05701c74 nm/app/app.css - the paper and the matter board's ground are white (--paper, --board), so the page, the conversation, the history list, the sign-in page, the reading pane's passages and the register card's notice are white; the small tints that shared the beige (--surface-2: table header rows, hover highlights, quiet labels, the recorder panel) are a barely-there cool grey (#f4f7fb); the ivory on the sign-in story panel (its text, the NM tile and the ticks) is white; the amber and brass meaning colours are untouched; the board, the history list and the reading pane keep their 1px rules, which now tell them apart from the white conversation; (2) 6408d137 tests/test_the_app_background_is_white.py - the two tokens are white, each rule that paints a page-level background resolves to white, the small tint is light and cool, no beige value is left in the app's stylesheets, and the meaning colours are unchanged; it failed on the beige stylesheet (nine failures) and passes now. DONE OFFLINE: the stylesheet guards (one owner per class, no hidden overflow, the answer at the column's width), the sign-in features and the window, initials and usage tests. NOT YET: the owner's browser. NOT CHANGED, as the owner said 'the app': the public site, which keeps the signed-off ivory (nm/site/site.css) - offered.
