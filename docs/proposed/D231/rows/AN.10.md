# AN.10 - Build: the answer's text at the full width of the window (P50)

Row 228 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.10

## Item

Build: the answer's text at the full width of the window (P50)

## Description

SEES: the answer's paragraphs, lists, More on this fold and the checks' list run to the column's right edge, like its headings and table, at any window width, and wrap again as the window narrows; reopening any saved conversation shows the same. MUST NEVER: change what an answer says, how it is saved or its contract; cut, hide or scroll text sideways at a narrow width; leave a width set on any element inside the answer; change the message box or the advocate's own messages. WHEN IT FAILS: not applicable (style only). DONE: offline, no stylesheet rule caps the width of an element inside the answer and a test says so, and the stylesheet tests pass; in the owner's browser the paragraphs run the window's width and follow it as it is resized. One file (nm/app/app.css) and its test.

## Governs or depends on

P50; O17; P45

## Status

Agreed 25 Oct 2026 (O17). Not built. | BUILT 25 Oct 2026 as one commit (app.css and its test, 9471ba5f). DONE: offline met; the owner's browser has not yet confirmed it.
