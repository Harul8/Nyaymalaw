# AN.59 - 17 Nov 2026, from the second review: the shape of the code. The largest files are split by what they do, and the history of decisions moves out of the comments - after the safety net of AN.57 is in place, not before.

Row 294 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.59

## Item

17 Nov 2026, from the second review: the shape of the code. The largest files are split by what they do, and the history of decisions moves out of the comments - after the safety net of AN.57 is in place, not before.

## Description

THE OWNER'S WORDS, 17 Nov 2026, giving Claude a second review of NM made in another session (product and code, measured; no AI key, so the legal quality of answers was not judged): "Look at attached, review it and make whatever makes sense as part of the build plan". WHAT THE REVIEW FOUND: every route sits in one file of 3,615 lines; the page is one script of 11,652 lines with a drawing function of 960; turn.process is about 500 lines and 26 functions pass 100; the code carries about 2,700 references to plan rows and decisions, and narrative that goes stale. The decisions below are Claude's proposals from that review, recorded at the owner's instruction; for the owner to correct before each piece is built. Nothing is built by this row. D271. THE ORDER IS FIXED: nothing here is split until the browser journeys run on every push (D263). Splitting the page or the routes without that net is the risk the review itself names.
D272. THE ROUTES ARE SPLIT BY AREA (account, conversation, papers, steps, Admin), each a module the application includes; the address of every route and its guards stay exactly as they are, shown by the route-table tests (AN.54 54c) passing unchanged.
D273. THE PAGE BECOMES MODULES, the drawing of a turn first; the board and the reading pane keep their look and structure (D60), shown by the frozen-board test and the journeys.
D274. A TURN'S STEPS ARE EACH THEIR OWN FUNCTION. turn.py is not pinned; the pinned pieces it calls are not changed.
D275. HISTORY LEAVES THE COMMENTS AS A FILE IS TOUCHED: a comment says what the code does and why it must; the decision's number goes in the commit and the decision's record (with D231, which is the owner's). No sweep that rewrites comments for its own sake.
D276 (FOR THE OWNER). WHAT THE PINS BECOME. D143 pins sixteen files by fingerprint so that the redesign changed orchestration only. Once the owner has accepted the redesign in the browser (D141), Claude's recommendation is that the fingerprints give way to what proves behaviour - the recorded replay and the pieces' own tests - so that a change that replays SAME needs no register entry. Until the owner says, the register stands.
D276 (17 Nov 2026): decided as Claude recommended, by the owner's "go with your recoomendation": once the owner has accepted the redesign in the browser (D141), the fingerprints give way to what proves behaviour - the recorded replay and the pieces' own tests - so that a change that replays SAME needs no register entry. Until then the register stands.

## Governs or depends on

AN.57 (D263 first); D60; D143, D141; AN.54 54c, D231

## Status

PLANNED 17 Nov 2026 at the owner's instruction (column 3). Nothing built, and by D271 nothing is to be until AN.57's 57a runs. DECIDED 17 Nov 2026 as Claude recommended (column 3): D276 - the pins give way to the replay and the pieces' tests once the owner accepts the redesign in the browser (D141); until then the register stands.

## Notes

PIECES, each proved by the replay and the journeys saying the same before and after, and moving code without changing it: 59a the routes, one area a piece; 59b the page, one module a piece, the turn's drawing first; 59c the turn's steps; 59d comments, with each file's next change.
