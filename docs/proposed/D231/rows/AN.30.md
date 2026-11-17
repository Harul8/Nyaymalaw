# AN.30 - 1 Nov 2026: where and how more reasoning is used, to lower cost; the next paid runs, one on the new build and one that tries GPT-6.1 Terra on the steps that need most thought

Row 265 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.30

## Item

1 Nov 2026: where and how more reasoning is used, to lower cost; the next paid runs, one on the new build and one that tries GPT-6.1 Terra on the steps that need most thought

## Description

THE OWNER'S WORDS, 1 Nov 2026. Asked "Shall I finish the last checks and push?", the owner: "yes. Also, review and update where and how more reasoning should be used to optimize costs." Then: "Also ok to do a paid run once all this pending work is built -- also do a test run by using 6.1 terra for complex work requiring more reasoning and thinking."

D12 Where and how a step reasons is decided by what it is for and what it costs, in one place, and recorded; reasoning is given where it prevents a repeated pass or a wrong answer and withheld where thought cannot change the result. (Restates and widens D4 of AN.28, which left the efforts to Claude.)
D13 The paid run is approved once the pending work is built (this row and AN.29): within what remains of the $5 (D6). It is followed by a test run that tries GPT-6.1 Terra on the steps that need most reasoning. A comparison does not promote a model (as for Sol, 10 Oct).

DECISIONS OF CLAUDE WITHIN D12-D13 (the owner may change any).
(1) One policy, one module (reasoning.py): a step's level follows from its kind of work and from what it must read; a call that repeats another's work goes one level up; never above high. (2) The evidence is the three paid replays of 31 Oct (counts and costs; column 6). (3) Nothing about reasoning is changed that the owner has decided: the search steps stay at the release's own setting (14 Oct). (4) Terra is registered with the prices on OpenAI's own model and pricing pages (read 1 Nov 2026) and is given to no tier; the test run routes chosen steps to it by name in the measurement harness only. (5) Both paid runs are capped, count their spend and print only counts and costs; the matter stays in the scratch folder.

## Governs or depends on

AN.29; AN.28 (its D4 and stage 6); P33

## Status

BUILT and pushed 1 Nov 2026 (66002e2a), measured on the paid run P1 ($0.71, Luna only), REVISED (ccdf4a40: writing and reviewing back at medium) and confirmed on P2b; GPT-6.1 Terra tried on the steps that need most thought (P2a the understanding $0.38; P2b the answer's judgement steps, with the rest on Luna at the revised levels, $1.29): not promoted. Offline tests pass; not applied to the running tree. About $4.15 of the $5 is spent, $0.85 remains; no paid run is pending. Evidence and what is open: column 7.

## Notes

AN.30 DETAIL (1 Nov 2026). Counts and costs only; the owner's matter stays out of the plan.

WHAT THE REPLAYS SHOW (31 Oct; replay 3 = 96 calls, $0.80, six disputes). Fitting the three replays' per-step tokens to their costs gives $0.101 per million fresh input tokens, $0.012 cached input and $0.494 output - Luna's published prices. A turn's spend: 71% fresh input, 4% cached input, 25% output (the output includes the reasoning). So input, not thought, drives cost: a big pass (a section written, a review, a take-up) carries 100,000 to 200,000 tokens and costs about $0.015, while 4,000 more reasoning tokens cost about $0.002 - a seventh of a pass. The answer stage is 72% of a turn: review $0.286, writing $0.212, second looks $0.045, overview $0.021, check across sections $0.008; research is 28%. Seven pieces (six sections and the overview) took 16 writing and 20 review calls: nine and thirteen beyond one each, about $0.32 or 40% of the turn spent on repeats. Cache: 33% of input was read from the cache (research: none; the answer: about 40%).

THE PRINCIPLE. Think more where it can prevent a repeated pass or a wrong answer; do not where thought cannot change the result.
- More: the first writing of a piece that is large (it must take up a long coverage list); every second look (the revising of the understanding, the looks again at papers, the repair of a paragraph, the take-up, a rewrite a review asked for, a re-check of a revision) one level above its step; the review of a piece that was changed (a take-up, a second look or a rewrite changed it, and what was added is the riskiest part); the steps whose miss reaches the advocate and that ran at the release's low setting: the reading of the advocate's message, the check across the sections, the time limits.
- Unchanged: the search steps (phrases, picks) at the release's own setting (14 Oct); reading the papers at medium, a level up for a large file (AN.28); the first reading of a scan.
- Output limits are raised for every step that now may reason longer, so that none stops short (the understanding once stopped at its limit); every call's reasoning tokens are recorded, so that the next run shows the cost of each level, step by step.

NOT CHANGED, FOR THE OWNER'S DECISION (estimates from the replays' token counts).
(a) The rewrite for suggestions (P33): about $0.03 per piece (a writing and a review), about $0.18 or 22% of a six-dispute turn, for what the review calls could be better. (b) Priming the cache before parallel calls (research's reads, the sections' first writing): up to about $0.07 on research and $0.22 on the answer, about a third of a turn; it costs time. (c) Doing a take-up and a second look together before the next review, not one after the other, saves a review ($0.014) for each piece that needs both.

TERRA. GPT-6.1 Terra (gpt-6.1-terra): 1,050,000-token context, 128,000 output; $1.00 input, $0.05 cached input, $1.25 cache write (30 minutes), $5.00 output per million tokens - ten times Luna and half of Sol; above 272,000 input tokens twice the input and cache rates and 1.5 times the output; reasoning none, low, medium (default), high, xhigh, max. Tool calling needs the Responses interface. A whole turn on Terra would cost about $8 at the third replay's sizes, so the test routes only the steps that need most thought, with a cap on what Terra may spend.

PIECES (status in column 7 as each is built): 30a reasoning.py and every call site; 30b output limits; 30c reasoning tokens recorded in each call's usage; 30d Terra registered (prices, limits, transport); 30e the measurement harness (the new ledger report, steps routed by name, the Terra cap, reasoning tokens by step); 30f tests; 30g the two paid runs and their record.
NOT IN THIS ROW: promoting any model to a tier; the three estimates above.

## Column 7

AN.30 BUILT, MEASURED, REVISED AND TRIED ON TERRA, 1 Nov 2026. Counts and costs only; the owner's matter stays out of the plan.

BUILT (66002e2a; pieces as column 6). reasoning.py holds the table of steps and two rules (a step that reads more than 60,000 tokens runs a level higher where the table says so; a call that looks again at work already done runs a level above its step; never above high). Every call site asks it; a test scans the sources for a level set by hand. The adapter records each call's reasoning tokens in its usage. GPT-6.1 Terra is registered (prices, limits, transport) and given to no tier. Output limits are raised for the steps that may reason longer. Offline: 818 tests that import the changed code pass on the working copy and on a clean copy of the previous remote tip with the change laid over it (two of them read saved diagnostics that are not in git and pass once those are copied in). The module is declared in the layout (core: 30).

P1, THE FIRST PAID RUN OF THE NEW BUILD (1 Nov 2026; Luna only; the eight-paper turn of 31 Oct replayed in a synthetic account, read only on the owner's store; cap $1.20).
- 76 calls, $0.707 (the third replay of 31 Oct: 96 calls, $0.80); 5.58 million input tokens, 27% of them cached. The whole turn took 38.5 minutes (research 6.7), against about 22 on 31 Oct.
- What AN.29 changed, measured with the model (the understanding found four disputes now, six on 31 Oct, so the pieces differ): events with no date 83 -> 29 of 204 (199 anchored); the check of the understanding leaves 1 code problem after its second round (was 5) and 4 the model found; 26 transactions read (23 anchored), the ledger 10 subjects with 12 figures added, 6 listed and not added, 3 not read because their words were not on the page; 8 points read side by side, all anchored. Items the review found passed over: 9 on 31 Oct over 7 pieces; 1 in P1 - but that count leaves out the section that fell back after a service failure (never written or reviewed); P2b, with every piece written, found 4 over 3 of 5 pieces after 4 take-ups added 8 paragraphs.
- Reasoning, per call (tokens out, of which reasoning; seconds): a writing at high 27,600 (19,700) and 194 s, against about nine thousand and 90 s at medium on 31 Oct; a review at high 12,600 (12,000) and 137 s, against 6,100 (5,700) and 66 s at medium in the same run; the overview at high 15,100 (10,900) and 135 s; the take-up at high 2,100 (1,300) and 19 s; the repair 2,000 and 20 s; the check across the sections at medium 1,100 and 12 s. Research: the understanding at medium 19,000 (800) and 172 s; its revising at high 20,000 (5,000) and 144 s; a chronology at medium 4,700 (1,600) and 39 s, and its look again at high 3,200 (2,500) and 29 s.
- At high the cost of a call was small beside its time (a review $0.0195 against $0.0165) but the answer stage took 32 minutes, one writing in six was lost to the service after more than four minutes (that section fell back to its draft notes) and one look again at transactions was lost; nothing showed fewer repeats: 14 reviews for 5 pieces (2.8 a piece; 2.9 on 31 Oct), the answer $0.092 a piece (was $0.082).

REVISION (decisions of Claude within D12; the owner may change any), pushed ccdf4a40. Writing, the overview and the review stay at medium whatever the size of what they read; a correction keeps the effort of the call it corrects (a rewrite is as large as the writing); the review of a changed piece is not raised. Kept: every second look whose answer is small, a level above its step (the revising of an understanding, the re-check of a revision, the looks again at papers, the repair of a paragraph, the take-up, the correction of a time limit); the reading of the advocate's message, the check across the sections and the time limits at medium (they ran at the release's own setting); the search steps at the release's own setting (14 Oct); the raised output limits. The table now: release's own setting for phrases, picks and the first reading of a scan; medium for the message, the understanding, its check, the chronology, transactions and connections (a level up for a file over 60,000 tokens), writing, overview, review, the check across the sections, the time limits and the two looks at scans; high for the revising, the checks that follow a look again at papers, the re-check of a revision, the repair, the take-up and the correction of a time limit.

P2b, THE ANSWER STAGE AT THE REVISED LEVELS WITH TERRA ON ITS JUDGEMENT STEPS (1 Nov 2026; the answer stage from P1's plan; Terra for the take-up, the repair, the check across the sections, the overview and the review of the overview, each with an allowance, Luna for the rest; cap $1.45).
- 43 calls, $1.294: Terra 7 calls $0.903, Luna 36 calls $0.390; 5.52 million input tokens, 36% cached. The answer stage took 14.4 minutes (P1: 31.8). All five pieces were written (no fallback, no call lost).
- Luna at medium: a writing 10,200 out (5,500 reasoning), 83 s, $0.0135; a review 5,700 out (5,200), 54 s, $0.0141 (against 27,600 / 194 s and 12,600 / 137 s at high). 18 reviews and 7 writings for 5 pieces (3.6 and 1.4 a piece), 5 second looks, 4 take-ups. With Terra's calls priced as Luna's the answer stage would have cost about $0.46, or $0.093 a piece (P1: $0.092): the revision saved no money and more than half the time; the answer is as long (7,700 words; P1 7,100 without the fallback block).
- Terra's 7 calls: $0.903 against $0.084 for the same tokens at Luna's fitted prices (10.7 times); 8 to 34 s a call; 600 to 2,900 tokens out, 260 to 1,200 of them reasoning. Terra's cache is its own: only 2 of the 7 calls read from it (a marked prefix is written at $1.25 and read at $0.05 per million, so the first take-up cost $0.178 and the later ones $0.127 and $0.071).
- What Terra's steps produced: the take-ups added 8 paragraphs and declined none; the overview Terra wrote ended its review with no finding (P1's, written by Luna at high: one); the items still passed over (4 over 3 pieces) do not differ in kind from Luna's. One run: no sign that these steps need Terra.

P2a, THE UNDERSTANDING ON TERRA (1 Nov 2026; the same eight papers; Terra for the understanding, its check and its revising, Luna for the search phrases; cap $0.80).
- 10 calls, $0.375 (Terra 4 calls $0.371, Luna 6 calls $0.004); eight times Luna's $0.046 for the same steps. Time as Luna's: understanding 165 s (172), revising 148 s (144), checks 18 and 38 s (37 and 46). Terra wrote less (14,700 and 13,300 tokens out against 19,000 and 20,000) and reasoned very little (154 and 475 tokens at medium and high; Luna 800 and 5,000).
- What it found, with Luna's in brackets: disputes 5 (4); legal questions 20 (16); facts 27 (25); parties 21 (13); subjects 29 (23). The first draft had 4 problems the code finds (19) and 6 the model's check found (3); after the revising 1 (1) and 5 (4). The first draft misread the advocate's request to understand the matter as a direction not to research and left every question list empty; Terra's own check caught it and the revising corrected it. It also added a planning dispute that its own second check called overstated. Each model's check found points the other's missed: Terra's an adverse finding the understanding left out and a conflict between two accounts of one document; Luna's an omitted judgment, a statute issue and date differences between accounts.
- One run each; the model reads the papers differently every run (counts vary by about 25%): no difference in kind to set against eight times the cost. (The harness leaves the plan's issues empty in this mode, so none are compared.)

CONCLUSION (Claude's, within D13; a comparison does not promote its model). Terra is not given to any tier. Where it might pay, not tried: the independent check of the understanding (two calls, about $0.13 a turn against $0.016) or the review of the overview (about $0.14 a call), for a second model's eyes; Terra writing a section or reviewing every section was not tried (reviews alone would cost several times Luna's even with its cache). Costs of the other steps stay with Luna.

SPENT of the $5 (D6): $1.77 (31 Oct) + about $0.005 (the Terra toy call) + $0.707 (P1) + $0.375 (P2a) + $1.294 (P2b) = about $4.15; about $0.85 remains. No paid run is pending.

DECIDED 1 Nov 2026 (AN.31): applying AN.29 and AN.30 to the running tree (done); (a) the rewrite for suggestions (dropped), (b) the cache (built where it pays), (c) a take-up and a second look together (built); the independent check by a second model (tried). OPEN (owner's decision). (a) the rewrite for suggestions (P33), (b) priming the cache before parallel calls, (c) a take-up and a second look together before the next review (column 6); applying AN.29 and AN.30 to the running tree (it restarts the server; AN.28 is applied); the independent check by a second model, as above.

