# AN.15 - Build: sign-in and registration in the signed-off design (P52)

Row 242 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.15

## Item

Build: sign-in and registration in the signed-off design (P52)

## Description

SEES: the sign-in page and the registration steps as drawn (account; privacy and AI permission; confirm email; ready), the states in the drawn words. The optional professional-details step waits for its own backend (no route takes enrolment details today) and is recorded as dependent work, not shown. MUST NEVER: weaken a check the routes make, or say an account exists. PIECES: app.css, index.html, app.js, one file a piece. Not started.

## Governs or depends on

P52; F-A-01 to F-A-18

## Status

Agreed 25 Oct 2026 (O23). Not started. | BUILT 25 Oct 2026 in part: the sign-in page's look came with AN.13 piece 1; piece 1 (bc33dfa4, index.html) and piece 2 (943a2d59, app.css) put the design's three lines on the story panel in place of 'Take the brief / Work the file / Advise'. NOT BUILT: the registration steps (account; privacy and AI permission; confirm email; ready) - the register card is one card as before, and its contract (F-A-02) is pinned by tests that would change with it; the professional-details step (no route takes those details). | DECIDED 25 Oct 2026 (O24 item 5): in steps, as drawn. Building the steps the routes support - account, privacy and AI permission, confirm email, ready. The professional-details step stays dependent work: it needs its own route and storage, a new version of the privacy notice for the details it collects, and a decision on how the proof of enrolment is kept and who reviews it. | BUILT 26 Oct 2026 (O24 item 5), pieces 3-5: (3) 74d2d72d index.html lays the register card out in its steps - Account (email, the passwords with the rules beside them, Continue), Privacy and AI permission (the notice, the two required boxes, the optional AI permission, Back and Create account) - still one form posted once, and the confirmation card as the third step; the F-A-02 contract changes with the decision (feature file, step definitions and the Implementation Plan sheet's F-A-02 cell; F-A-09 names Create account); (4) 53fba2e5 their style; (5) ca50635f app.js moves between the steps sending nothing, catches a short or mismatched password on the account step (both put away), leaves the kinds of character to the server, and ends on the ready card: the account ready, its trial at 100%, and whether AI sharing is on. DONE OFFLINE: the sign-in features (71), the page-and-script contract, tests/js/register_steps.mjs. The browser journeys that walk registration press Continue and expect the ready card (changed, not run). NOT YET: the owner's browser. STILL DEPENDENT WORK: the professional-details step (its route and storage, a new privacy-notice version for what it collects, how the proof of enrolment is kept and who reviews it; and D-041 today forbids the public form any professional identity). | DECIDED 26 Oct 2026 (O25 item 3): the professional-details step is not needed and is dropped, not deferred; registration is complete as Account, Privacy and AI permission, Confirm your email, Ready.

## Notes

26 Oct 2026: with the step dropped (O25), D-041's rule that the public form claims no professional identity stands unchanged.
