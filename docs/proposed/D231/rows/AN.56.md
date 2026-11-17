# AN.56 - 17 Nov 2026, from the second review: what the advocate is told. The public pages say what NM holds and who to write to; every error is a plain sentence; and each answer says how much of the law it needed NM holds.

Row 291 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.56

## Item

17 Nov 2026, from the second review: what the advocate is told. The public pages say what NM holds and who to write to; every error is a plain sentence; and each answer says how much of the law it needed NM holds.

## Description

THE OWNER'S WORDS, 17 Nov 2026, giving Claude a second review of NM made in another session (product and code, measured; no AI key, so the legal quality of answers was not judged): "Look at attached, review it and make whatever makes sense as part of the build plan". WHAT THE REVIEW FOUND: the public pages show "[NN]" where the numbers of Acts and judgments belong, leave support, grievance and address blank while registration is open, and describe a form that no longer exists; errors show system words ("HTTP 500", "turn id", "malware checker"); a model step that fails can reach the advocate as a server error. The decisions below are Claude's proposals from that review, recorded at the owner's instruction; for the owner to correct before each piece is built. Nothing is built by this row. D258. THE PUBLIC PAGES SAY WHAT IS HELD, FROM THE DATED MANIFEST: the numbers of Acts and judgments and their date are read from the library's own manifest when the page is served, never typed; where the manifest cannot be read the page says the figures are not available, not a placeholder.
D259. SUPPORT, GRIEVANCE AND ADDRESS ARE THE OWNER'S TO GIVE. Until they are given the pages do not print empty headings; registration for advocates other than the pilot's is the owner's decision once they are in.
D260. 'HOW IT WORKS' DESCRIBES THE PRODUCT AS IT IS: one message box, papers attached, NM working step by step.
D261. EVERY FAILURE IS A SENTENCE THE ADVOCATE CAN ACT ON. One sweep of every message the page can show and every error a route can answer: no status number, no identifier, no name of a component; each says what happened to the advocate's work and what to do. A failure nobody caught is answered by code's one sentence with a reference the operator can find in the log. It continues AN.52 52i, AN.53 53e3 and 53j; tests/test_the_product_does_not_speak_in_identifiers.py is the sweep to extend.
D262. EACH ANSWER SAYS HOW MUCH OF THE LAW IT NEEDED NM HOLDS. With AN.51's D199 (the limits of the search): the Acts and judgments the matter named that are held, and those named and not held, in code's words from the search record. Built with 51e.
D259 (17 Nov 2026): stands as written. The owner's "go with your recoomendation" decides how the pages behave until the details are given (no empty headings); the support, grievance and address details themselves are still the owner's to give.

## Governs or depends on

AN.51 51e (D199, D253); AN.52 52i; AN.53 53e3, 53j; AN.45 (the manifest); the site pages in nm/site

## Status

PLANNED 17 Nov 2026 at the owner's instruction (column 3). BUILT and pushed 17 Nov 2026 with AN.51's 51e: D262 (under each answer, which of the Acts and sections the matter named NM holds, in code's words; evidence on AN.51, column 7). NOT BUILT: D258, D260 and D261, which need no decision. WAITING ON THE OWNER: the contact details of D259 (17 Nov 2026: D259 stands; the details are the owner's to give).

## Notes

PIECES: 56a the site's reader of the manifest and the two pages (nm/site); 56b 'How it works'; 56c the sweep of D261 - the page's messages (app.js), then the routes' answers (api.py), each with the sweep test extended and its control; 56d the catch-all's sentence and reference; 56e D262 with 51e. No model call.
