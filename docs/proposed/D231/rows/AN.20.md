# AN.20 - Build: the person button's initials, the answer's own header, and the page reading under the usage limit (AN.14, P51)

Row 250 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.20

## Item

Build: the person button's initials, the answer's own header, and the page reading under the usage limit (AN.14, P51)

## Description

SEES: (1) the person button shows the advocate's initials in a circle in place of the generic person mark - the first letters of the first and last words of their name, or the first letter of their email's name - with the full name still read out; (2) each saved answer opens with its own header as the design draws it: the NM mark, Nyaymalaw and the time the answer was made; (3) when the AI account's credit runs out part-way through reading a document's scanned pages, the page says so in the owner's words of P51 and stays waiting to be read again, instead of 'could not read this page just now'. MUST NEVER: change what an answer says or how it is saved or reopened (P46); show a time for an answer that has none; lose a page already read. PIECES: index.html, app.css and app.js for (1); app.js for (2); page_reading.py for (3), each with its focused test. FAILURE SCOPE: display, and the reason a page waits. RECOVERY: revert the commits.

## Governs or depends on

AN.14; P51; P46; O26

## Status

Agreed 26 Oct 2026 (O26). Building. | BUILT 26 Oct 2026, pieces 1-7. The person button's initials: (1) 7056566f index.html - an initials circle in place of the generic person mark, not read out; (2) c72dd988 and f72b43c3 app.css - the circle in the brand blue, empty and so undrawn until it has letters, kept on a phone (the first commit carried a phone check that read only the first phone block and failed - it had gone in because a pipe hid the failing exit status; f72b43c3 corrected it); (3) 53699c6d app.js - the first letters of the first and last words of the name, after any title such as Adv. or Dr. (the design's 'Adv. Meera Rao' is MR), one letter for an email, nothing for nothing; emptied with the session; tests/js/person_initials.mjs, shown to catch five mistakes. The answer's own header: (4) 9e496a99 app.css - in the reply family of classes (an answer-* class would be read by P50's width guard as part of the answer); (5) a56e48a3 app.js - the NM mark, Nyaymalaw and the time saved with the answer between the advocate's message and the answer's first line; an answer with no time, or a time that is not a time, shows none; tests/js/answer_v18.mjs extended, shown to catch four mistakes. The page reading under the usage limit (P51's leftover): (6) 5eec8441 page_reading.py and (7) d5cc0bdb voice.py - a scanned page, or a recording, that meets the exhausted AI account now says 'you have run out of your usage limits; please upgrade to continue accessing NM', keeps waiting to be read again, and keeps the provider's words in the diagnosis; both tests fail without their change. DONE OFFLINE: as above; every script test, the renderer wrappers, the page-reading, voice and document-route tests pass. The browser-launching test of the legal signals cannot start here because the test runner's Chromium is not installed (with or without these changes). NOT YET: the owner's browser.

## Notes

26 Oct 2026, left alone: the answer-wording targets of AN.6 (sentences still average 24.4 words; NM's working phrases remain; next steps still ask for documents) need prompt changes measured by paid runs, so they wait for the owner's approval. Found in passing, not changed: the time-limit step (calculation.py) turns any model failure into 'the time limits could not be worked out (<kind>)', so if it alone meets the exhausted credit the kind's name is shown; the later steps then refuse the turn in the owner's words, so the effect is small. | 26 Oct 2026, a test fault found while checking this stretch and fixed in the tests (699cb0fb): the live-words socket tests (tests/test_arrive_sign_in_features.py and tests/test_live_dictation.py) failed now and then, as they had before any of the day's changes - their fake provider answered the committed audio and the final words before the page had sent 'done', and the server finished without them whenever the test's page was slower than the server. SHOWN: with the test's page made 0.4 s slow both tests failed every time, on the code as it stood before this stretch (03ff9472) as well as now; with the fake provider finalising only after the page's commit (as a real one does) both pass with the slow page and the whole files pass. Product code is not involved.
