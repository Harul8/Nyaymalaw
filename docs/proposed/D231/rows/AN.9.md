# AN.9 - Build: the execution deadline worked out on a stated assumption (P49)

Row 225 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.9

## Item

Build: the execution deadline worked out on a stated assumption (P49)

## Description

SEES: for a decree whose date is given, the limit to apply to execute it is worked out in almost every run, from the decree's date, with the assumption that it became enforceable then, and what would change it, in the Working box and the answer. MUST NEVER: take a later event as happening at the dated one (receipt as posting, the bank's information as the cheque's return); work out a limit where nothing dates the event or one it follows from (a decree without its date); hide the assumption; add a call, a contract version or a schema change. WHEN IT FAILS: as today - a limit code's checks refuse is reported not assessed (P36 (b)). DONE: offline, the prompt states the rule; live, on the step alone and nothing else of a turn: the message of live run 4 worked out in at least 15 of 16 runs with its assumption stated and done empty (the current prompt measured on the same message, 5 of 18 not worked out); and controls - a decree whose date is not given is still not worked out; a notice posted whose receipt is not known is still not worked out from the posting date; the cheque matter's chain is as before and P34's credit-sale limit is worked out at least as often as under the prompt before this change (8 of 9 and 6 of 8 in the checks of 25 Oct); the spend and evidence recorded. One prompt, one file (calculation.py).

## Governs or depends on

P49; O16; P23; P34

## Status

Agreed 25 Oct 2026 (O16). Not built. | BUILT 25 Oct 2026 as one commit (calculation.py prompt v2 and its offline test). DONE: offline met. Live, the step alone: the execution message worked out in 16 of 16 runs with done empty and the assumption stated in 15 (the bar was at least 15 of 16, so met at its edge: one run gave the right limit with no assumption stated - whether a dated event is the Act's event is the model's judgment, so code has no sure way to tell when an assumption is owed, and the residual stays recorded); a decree without its date not worked out in 4 of 4; a notice posted with receipt unknown not worked out from the posting date in 6 of 6; the cheque chain in 10 of 10 as before; P34's credit-sale limit in 10 of 10 against 8 of 9 and 6 of 8 (not worse). Evidence and spend in P49 column F. Not measured: a whole turn, so how the answer and the Working box word the assumption has not been seen live; the follow-up path.
