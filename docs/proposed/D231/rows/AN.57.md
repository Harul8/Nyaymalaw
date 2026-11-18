# AN.57 - 17 Nov 2026, from the second review: the safety net watches the page. The browser journeys run on every push, the stand-in models answer every step, and lint and types are held on what changes.

Row 292 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.57

## Item

17 Nov 2026, from the second review: the safety net watches the page. The browser journeys run on every push, the stand-in models answer every step, and lint and types are held on what changes.

## Description

THE OWNER'S WORDS, 17 Nov 2026, giving Claude a second review of NM made in another session (product and code, measured; no AI key, so the legal quality of answers was not judged): "Look at attached, review it and make whatever makes sense as part of the build plan". WHAT THE REVIEW FOUND: the runner leaves out every browser journey, so nineteen of twenty-three journey checks had failed unseen (found and mended 15 Nov, AN.54 54b16-54b20); the stand-in models did not know every step, so a paper or a follow-up ended in a server error from the stand-in; the lint rules are not enforced and there is no type check; half the test modules borrow helpers from other test modules. CLAUDE'S CHECK OF THE REVIEW, 17 Nov 2026, on the branch as pushed (text search and counts; nothing run against a model). Its numbers hold to within a few per cent: 56,975 lines of production Python in 148 files; research.py 4,043 lines and api.py 3,615; app.js 11,652 lines with a renderTurn of 960; 2,348 plan references in the Python and 398 in the page; 92 broad catches and 86 lint waivers; 6,594 lines over the project's own limit of 100; 245 of 484 test modules import another test module; the runner leaves out every browser journey; no page file is compressed; the two public pages carry "[NN]" where numbers belong; there is no search of the history and no rename. WHERE IT IS WRONG OR ALREADY ANSWERED: the page does run in strict mode (line 11 of app.js); the build that was "red for days on one protected file" is mended (AN.54, 17 Nov, register item 16); the "permission gate" on the sixteen pinned files is the owner's D143, and under D250 ten exceptions were entered, built and proved by the free replay in two days, so the gate costs a replay and a plan line, not weeks; the stop after every step is the owner's own design (D134-D135), not a defect; the plan's form, the standing instructions and a tagged release are already D231, D229 and D232. Its price of 5,000 rupees a month is not in the repository and is not checked. The decisions below are Claude's proposals from that review, recorded at the owner's instruction; for the owner to correct before each piece is built. Nothing is built by this row. D263. THE BROWSER JOURNEYS RUN ON EVERY PUSH, on the hosted runner with its own Chromium, after the offline tests; a journey that fails marks the commit. No model is called.
D264. ONE STAND-IN MODEL ANSWERS EVERY STEP. A stand-in asked for a step it does not know fails the test with the step's name; it never answers with a server error. A test asserts that every operation the engine names is one the stand-in knows, so a new step cannot be added without it.
D265. LINT AND TYPES ARE HELD ON WHAT CHANGES, not all at once: the runner fails a push whose changed lines break the lint rules, and type-checks the files a push touches. The 6,594 long lines are not reflowed in one sweep.
D266. TEST HELPERS LIVE IN SUPPORT MODULES, moved as files are touched, beginning with the most borrowed (test_core_served, by about eighty). A test that reads source text stays only where it is a sweep with a planted control (the single-owner rules are such sweeps by design); one that pins wording is replaced by a test of behaviour when its file is next changed.
D267 (FOR THE OWNER). THE RETIRED SCREENS still ship in the page behind 52 skipped browser checks (the opening form, the History pane, the Legal library, the case file's header). Either they are deleted, with their checks, or what each did is brought into conversations. Each one is the owner's to decide; D60 holds the board and the reading pane as they are.
D267 (17 Nov 2026): decided as Claude recommended, by the owner's "go with your recoomendation" (Claude had made none, and makes this one). Each retired screen - the opening form, the History pane, the Legal library, the case file's header - is deleted with the browser checks skipped for it, once it is confirmed that nothing served still reaches it; where one still does something the conversations do not, that is put to the owner instead of deleting it. The board and the reading pane stay as they are (D60).
D292 (FOR THE OWNER, 17 Nov 2026; from D267's check, column 7). THE SCREENS OF A MATTER SAVED BEFORE CONVERSATIONS. The development store holds 207 such matters; the history lists each as an 'Earlier matter record', and its file icon opens the opening record, the Case file, the History pane, the matter cover and the records of custody, correction and urgency. Either (a) they are deleted with their skipped checks - those matters' records stay stored, but the page no longer opens them; or (b) they stay until the earlier matters are retired. Claude's recommendation: (a) if those matters are the development and test matters of September and October, which their numbers suggest; (b) if any is a real matter the owner still needs to read.
D292 DECIDED 17 Nov 2026 (night), the owner's words: "D292 - ok" - option (a), as recommended: the screens of a matter saved before conversations are deleted with their skipped browser checks (those matters' records stay stored; the page no longer opens them), and with them the Legal library, Home and Preparation screens, which nothing reaches. The board and the reading pane stay as they are (D60).

## Governs or depends on

AN.54 (54a the runner, 54b the journeys); D60; D143

## Status

PLANNED 17 Nov 2026 at the owner's instruction (column 3). BUILT and pushed 17 Nov 2026: 57a (the browser journeys run on every push, as a job of their own that finds its files from the source; evidence in column 7) - its first run on the hosted runner is its proof and has not been seen from here. NOT BUILT: 57b to 57e (D264 to D266), which need no decision and no model call. DECIDED 17 Nov 2026 as Claude recommended (column 3): D267 - each retired screen deleted with the checks skipped for it, once nothing served reaches it: CHECKED 17 Nov 2026 (column 7) - the earlier-matter screens are still reached, from the 207 matters the development store holds from before conversations, so they are put to the owner (D292); the Legal library, Home and Preparation, which nothing reaches, are deleted in the same piece once the owner answers; nothing deleted yet.
18 Nov 2026: 57f part one BUILT in the build copy, not applied - the Legal library, Home and Preparation deleted with their checks (column 7); part two, the earlier-matter screens, next; all of it goes on the owner's server only at the owner's word.
18 Nov 2026 (later): 57f part two BUILT in the build copy, not applied - the screens of a matter saved before conversations deleted with their checks (column 7). D292 is now built whole. It goes on the owner's server with D297, D298, D299, D301, D302 and D303, only at the owner's word. D300 is not built: it has had no answer.
18 Nov 2026 (evening): 57f APPLIED with D297-D303 by the owner's word (D304; AN.48 columns 10 and 12): the owner's checkout at cad508e7, both servers running it; the original-material window's files are no longer served. Not yet seen in a browser.
18 Nov 2026 (evening, later): D306 (the journey finder finds the two journeys it missed) and D307 (what D292 left on the server and in the page removed) BUILT in the build copy (AN.48 column 12); applied with D305 under D308.
18 Nov 2026 (late evening): D306 and D307 APPLIED with D305 by the owner's word (D308; AN.48 column 12): the owner's checkout at 2abeb974, both servers running it; the earlier-matter addresses answer 'not found'. Not yet seen in a browser.

## Notes

PIECES: 57a the runner's journey job (.github/workflows; no production file); 57b the stand-in's owner in a tests support module, with the test that it knows every operation; 57c the lint step on changed lines; 57d the type check on touched files, with its settings; 57e the first helpers moved (one borrowed module a piece); 57f each retired screen, as decided.

## Column 7

57a (17 Nov 2026; D263; .github/workflows/offline-tests.yml only, no production file, no model call), THE BROWSER JOURNEYS RUN ON EVERY PUSH. BUILT: a second job, 'journeys', beside the offline tests: it installs the journey extra and the runner's own Chromium, finds the journey files from the source (every test file that launches the browser or borrows the harness that does: 22 files today, so a new one is run the day it is added), checks that the browser library is there (a journey must fail here, not skip, if it is not), and runs them with each skip's reason printed. A job of its own, so a failing journey and a failing offline test are seen apart. NOT RUN HERE, said plainly: a run of the journeys on the owner's laptop was refused by the session's permission check, in keeping with the owner's rule against large runs there; the job's proof is its own first run on this push, which this session cannot read (no access to the runner's results). The owner sees it on the commit. If its first run fails on something the runner lacks, that is this piece's to mend. Last known result of the same files, in the cloud session of 15 Nov (AN.54 54b20): 72 passed, 52 skipped, none failing.
57a, completed the same day (17 Nov 2026): THE RUNNER FINDS EVERY BROWSER JOURNEY BY WHAT BORROWS FROM WHAT. The job first found its files by searching for two words; measured against the source, that search missed one file that borrows the browser through another file, and caught four that only mention the word. A small tool, development_environment/developer_tooling/journey_files.py, now lists every test file that names the browser library and every one that borrows from such a file, directly or through another (21 files today); the job runs what it lists. Test: tests/test_the_runner_finds_every_browser_journey.py (new, 2): planted files - one that uses the browser, one that borrows from it, one that borrows from that, one that does not - and the shipped journeys, with the runner's file asking the tool. FOUND MEANWHILE: this laptop has no browser installed for these tests (six registration tests could not start here for that reason), so the hosted runner is the only place they run - which is what the job is for. Still not seen: the job's first result.
D267, CHECKED BEFORE ANY DELETION (17 Nov 2026). The decision deletes each retired screen once nothing served reaches it, and puts to the owner any that still does something the conversations do not. WHAT REACHES THEM, from the source: the conversation history down the side lists every matter saved before conversations as an 'Earlier matter record' (nm/app/app.js, historyMatterRow); opening one shows its records, and its file icon offers the opening record, the Case file with its header, the History pane, the matter cover and the records of custody, correction and urgency - the screens most of the skipped browser checks were written for (their skip reasons say so: 'reached only from a matter saved before conversations'). The Legal library, Home and Preparation have no way in: the tab bar is not shown, and the library's tab is disabled. WHAT IS HELD, by file names only (no content read): the development store holds 225 saved matters - 18 conversations and 207 matters saved before conversations; the pilot's store holds none. SO: the earlier-matter screens are still reached, from the development store's 207 earlier matters, and still do what no conversation does - open those matters' records. They are not deleted; the choice is put to the owner (D292 on this row: delete them, and with them the way to open those records from the page - the records stay stored - or keep them until the earlier matters are retired). The Legal library, Home and Preparation are to be deleted with their skipped checks, in the same piece as the owner's answer, since they share the same files (index.html, app.js, app.css) and the same journey files; nothing is deleted yet.
18 Nov 2026 - 57f PART ONE BUILT (D292, in the build copy, not applied): the Legal library, Home and Preparation deleted, with the hidden tab bar that led to them. The page script loses 55 top-level blocks (about 1,040 lines: preparation, the hearing pack, handover, drafting, action proposals, the library's search and a matter's research); the page loses 260 lines and the stylesheet about 150 lines of rules only those screens used. The pane switcher now knows three panes (the conversation window, and the case file and history, which go in part two). The reading of the server's state is kept (the build banner and the rehearsal line); the library's line went with the one screen that showed it. Found while checking and fixed: the sign-out clearing still named the library search's fields, and would have stopped at the first missing one on every sign-out; the comment before the top bar's buttons, where two page tests cut the script, was put back. CHECKS: the 82 page ids removed appear nowhere else in the code or the tests; the 41 offline test files that read the page files: 409 passed and 2 failed on the missing comment, after which every page test passed through its runners; the page agrees with its script; one class, one owner. The four browser journeys changed load and lint clean; they need a browser and were not run here. The sign-in feature checks were changed (no tab bar; the person menu read to the end of the top bar) but NOT RUN: the tool's privacy guard refuses to run that file; the two changed assertions were checked directly against the page. Checks deleted, each for a retired screen: the Preparation journey (skipped whole), the library search's renderer check, the login journey's library search phase and Home's start button, the library line in the server-state page check and in three journeys, and the library search's late-reply case. DEPENDENT WORK, outside D292's words and the owner's to decide: the server still answers the addresses only those screens called (the library search, a matter's research and its cases, action proposals, drafting packages, handovers and hearing packs); removing them is a server change of its own.
18 Nov 2026 - 57f PART TWO BUILT (D292, in the build copy, not applied): the screens of a matter saved before conversations deleted.

WHAT WENT. The page script loses 75 top-level blocks (about 2,550 lines). These were:
- the earlier matter's own board, its dispute reader and its checklist;
- the opening form, its corrections and the matter's opening record;
- the file icon's menu and every record under it: the case file with its premises, relief, currency and corrections, the History pane, the bindings, decisions and retention, the protective handoff, and Recover a draft;
- the re-entry that reopened such a matter and its transcript.

The page loses 229 lines and the stylesheet about 400 lines of rules only those screens used. The original-material window is deleted whole, with its two files, its two lines in the layout's list of served files and its two lines in the page: nothing on the page could open it any more.

The conversation history now lists conversations only. The server still lists the earlier matters after them; the page leaves those rows out and counts and pages conversations alone. The pane switcher knows one pane.

WHAT CHANGED IN WHAT STAYS:
- A stale refusal, and a refusal that kept the message as a matter record, no longer reopen a matter. The server no longer gives the second.
- A sign-in after a session ended part-way through a brief opens a new matter, as before for a conversation. The brief's words stay in the device's keeping. Going back to the conversation is D300, which the owner has not answered.
- The kept draft the sign-in read, which nothing reads any more, is gone.

CHECKS:
- The 83 page ids removed appear nowhere else in the code. In the tests, they appear only in the browser journeys retired below.
- No function the page still calls is missing, and none left in it is uncalled.
- The page tests, each through its runner, all passed. That includes the frozen board and pane check.
- The 76 offline test files that read the page files: 1,022 passed. 4 failed and were mended, then passed:
  - the count of served files (now 28);
  - the history's generation guard, rewritten for conversations only;
  - the conflict-check sentence, which stood in the deleted form;
  - a stale declaration (below).
  5 errored at setup: they are a browser journey, and no browser is installed here.
- The page agrees with its script. One class, one owner. The shipped layout loads as the server loads it.
- The 14 browser journeys collect and lint clean. They need a browser and were not run here.
- The sign-in feature checks were changed but NOT RUN: the tool's privacy guard refuses to run that file. Every changed assertion in it was checked directly against the page.

CHECKS RETIRED, each for a deleted screen:
- the opening journey;
- the matter cover;
- the recorded answers read in History;
- the recorded urgency under the file icon;
- the journey of a correction in the case file;
- the journey of custody and decisions;
- the opening form's own page check;
- the earlier board's checklist renderer;
- the records helper;
- Recover a draft and the opening record in the recovery journey;
- the History phase of the login journey;
- the History surface, the opening form's draft-key waits, the transcript read-back and the protective retry in the workspace journey;
- the case-file correction and source phases of the comprehension journey;
- the matter re-entry case of the disclosure-fold check;
- the input-only case of the late-reply check.

FOUND WHILE CHECKING:
- The production-reach check failed before this work. The gathered case account was still declared unwired after D291 wired it. That declaration is deleted, in a commit of its own.
- The journey finder of 57a misses a journey that borrows another as a named module: the AI permission journey. The hosted journeys job therefore leaves it out. Not mended here; put to the owner.

DEPENDENT WORK, outside D292's words and the owner's to decide:
- The server still lists the earlier matters in the conversation history's list, and still answers the routes only those screens called: a matter's uploads, opening, corrections, transcript and records. Removing them is a server change of its own.
- The send envelope still carries the opening form's parties, release and capacity fields, now always empty.
- The words for an input-only refusal, which the server no longer gives, are still in the turn renderer.
- The board's buttons for an earlier matter's proposed changes are unreachable.
- The page's paths for a matter id in the delivery of a turn still exist.
- The vault's drafts are now offered back only by reopening their conversation (D300 is the owner's open question).
