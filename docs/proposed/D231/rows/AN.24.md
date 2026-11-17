# AN.24 - Fix: the first use of the usage store and the turn-attempt store is safe when callers arrive together (AN.17, O30)

Row 258 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.24

## Item

Fix: the first use of the usage store and the turn-attempt store is safe when callers arrive together (AN.17, O30)

## Description

SEES: nothing changes for an advocate except that the very first turn on a brand-new installation can no longer be refused with 'usage could not be checked' (503, retryable). THE INVARIANT: a store file is published whole or not at all - nobody, at any moment, can find an empty or half-made file where the store is meant to be - and a lazily built store is built once, however many callers arrive together. THE MECHANISM, one for every site of this shape: a small helper makes the SQLite file complete in a temporary file beside it and links it into place only if none exists yet (the creator that loses discards its copy and uses the winner's); the usage store and the turn-attempt store use it in place of building inside the file where it is meant to stay; the lazy adapter in nm/app/composition.py builds its store under a lock; and each store logs the KIND of error when it refuses (the error's class and, for SQLite, its name and, for the operating system, its number - never a message, a path or a word of a matter), where it used to discard the reason. MUST NEVER: remake a store whose file was lost (an existing adapter still refuses; a file that exists but is empty or foreign is still refused, never initialised); give a second trial allowance; leave a temporary file behind; weaken the checks that refuse a schema the store did not make; treat unknown usage as free. NOT CHANGED, because it is not the measured cause: no retry loop (no transient lock or disk error was seen in about 1,600 checks under load; the new log will say if one occurs). FAILURE SCOPE: the first use of a new store. PIECES (one production file each, with focused tests): the helper (nm/shared/sqlite_creation.py, declared in the layout); the usage store; the turn-attempt store; the lazy adapter. PASS: four callers' first use of a new store, 150 rounds each for the usage store and the turn-attempt store, refuse none (12 of 600 refused before); an existing empty or foreign file is still refused; deliberate mistakes in each piece are caught. RECOVERY: revert the commits.

## Governs or depends on

AN.17; O30

## Status

Agreed 26 Oct 2026 (the owner asked how to avoid it; the measured cause and the fix were put to the owner with O30). Building. | BUILT 26 Oct 2026, pieces 1-4 (de787da6, fd3dace6, 4727f73e, 7b42cae9): (1) nm/shared/sqlite_creation.py - create_if_absent makes the file complete in a temporary file beside its path and links it into place only if none exists (one creator wins, the loser's copy is removed, a failed build leaves nothing), and why() names a fault by kind for a log; declared in the layout; (2) the usage store and (3) the turn-attempt store use it, log the kind of fault on nm.usage and nm.attempts (never a message, a path or a word of a matter), keep refusing a file that exists and is empty or damaged, and leave the carrying over of earlier versions untouched; (4) the lazy adapter in nm/app/composition.py builds under a lock, so callers arriving together build it once. TESTS: 7, 7, 9 and 5 (the helper with a positive control that shows the old defect is visible; each store's first use by four callers at once, 150 rounds; the empty, damaged and foreign files still refused; the logs; the adapter); deliberate mistakes tried 8, 7, 8 and 4, each caught except one that changes only speed; the first try left the attempt store's cannot-be-opened path untested and a test was added. MEASURED AGAIN with the same experiment as before the fix: four first uses of a new usage store arriving together, 150 rounds - 0 of 600 refused (12 of 600 before); the single-caller and 16-caller runs unchanged, none refused. NOT CHANGED: no retry (none was needed in any measurement; the new log will say if a transient fault ever occurs); the usage check's tail latency with 16 callers at once (p99 about 1.5 s) because every check is a write transaction on one file - a read-first check now, and a shared database before several servers, are the real answers (O30).
