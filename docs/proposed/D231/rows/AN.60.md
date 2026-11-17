# AN.60 - 17 Nov 2026, from the second review: running NM for paying advocates. Backups and library updates without stopping the service, what holds the data, papers where no scanner runs, and one bounded proof of the legal quality.

Row 295 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.60

## Item

17 Nov 2026, from the second review: running NM for paying advocates. Backups and library updates without stopping the service, what holds the data, papers where no scanner runs, and one bounded proof of the legal quality.

## Description

THE OWNER'S WORDS, 17 Nov 2026, giving Claude a second review of NM made in another session (product and code, measured; no AI key, so the legal quality of answers was not judged): "Look at attached, review it and make whatever makes sense as part of the build plan". WHAT THE REVIEW FOUND: a backup needs the service stopped; adding Acts needs it stopped and is run by the owner from a terminal; with no malware scanner a paper is held and never read; the store is files and SQLite on one machine; and nothing yet shows how good the answers are on matters whose answers are known. The decisions below are Claude's proposals from that review, recorded at the owner's instruction; for the owner to correct before each piece is built. Nothing is built by this row. D277. A BACKUP DOES NOT STOP THE SERVICE. On the hosted server a snapshot of the data volume is taken while NM runs, at a moment the store marks as whole (no save half-written: AN.50's publish makes each file whole, and the small databases are copied by their own online backup); the restore drill (50e3) is run against such a copy. The stop-then-copy of the hosting guide stays as the way on a laptop. Belongs with D176's build.
D278. ACTS ARE ADDED WITHOUT STOPPING: the new index is built beside the one in use and taken up between searches; a search under way finishes on the one it began with. The build itself stays the owner's run (corpus discipline).
D279 (FOR THE OWNER). WHAT HOLDS THE DATA. Claude's recommendation: files and SQLite stay for the pilot - each matter sealed under its own key and destroyed key-first is what the files give - and the decision is taken again at a stated point (a second server, or a number of advocates the owner names), with the cost of moving measured then. Not a move to a database now.
D280. PAPERS WHERE NO SCANNER RUNS are said, to the advocate at once (the paper is kept and will be read when the scanner is back) and to the operator at start and on the Admin page (D242 already prints it at start). A hosted server does not run without one.
D281 (FOR THE OWNER; a paid run). THE LEGAL QUALITY IS MEASURED ONCE, BOUNDED: ten matters whose answers the owner already knows, made anonymous by the owner, each run once and marked by the owner against what a careful advocate would have said - what was right, what was missing, what was wrong, what was not held. It needs the owner's matters, a named amount (about ten times a matter's usual cost) and the owner's marking. With docs/GOLDEN_SET.md.
D279 (17 Nov 2026): decided as Claude recommended, by the owner's "go with your recoomendation": files and SQLite stay for the pilot; the question is taken again at a second server, or at a number of advocates the owner names, with the cost of moving measured then.
D281 - THE OWNER'S WORDS, 17 Nov 2026: "D281 - we will do this once everything is ready". Not run now: when the build is complete, with the owner's matters, made anonymous, an amount the owner names, and the owner's marking.

## Governs or depends on

AN.48 D176 (the hosting); AN.50 50e (backup and restore); AN.46 (the Acts' staging); D242; docs/GOLDEN_SET.md; P16

## Status

PLANNED 17 Nov 2026 at the owner's instruction (column 3). D277 and D278 belong with the hosting build on branch nyaymalaw-aws; D280 can be built without a decision. DECIDED 17 Nov 2026 (column 3): D279 as Claude recommended - files and SQLite stay for the pilot; D281 in the owner's words - run once everything is ready, with the owner's matters, amount and marking.

## Notes

PIECES: 60a the store's 'whole' moment and the online copy of each small database, then the hosting guide; 60b the index taken up between searches (retrieval.py is pinned: a register exception, proved by the replay); 60c what is said where no scanner runs - the page, the Admin diagnostics; 60d the run of D281, only on the owner's word.
