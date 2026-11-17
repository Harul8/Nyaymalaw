# AN.34 - 2 Nov 2026: more of each turn's input read from the cache - the second passes, one opening for every research call, one for the answer's steps - tried in small runs on one or two small papers

Row 269 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.34

## Item

2 Nov 2026: more of each turn's input read from the cache - the second passes, one opening for every research call, one for the answer's steps - tried in small runs on one or two small papers

## Description

THE OWNER'S WORDS, 2 Nov 2026. Told of the second measuring run's cost (about 72% of it input: each step reading the conversation and papers), they asked: "why is this not cached?" Told why (research's calls carry no cache marks, and each paper's reading shows the rest of the file without its own pages, so no two readings open alike; the answer's steps keep a cache each because their instructions come first) and of three ways to cache more, they said: "I want you to do small specific runs with may be one or two small files to test this, not the current full run".
D29 SMALL RUNS. Each way is tried in small specific paid runs on one or two of the smallest papers of the owner's matter, in a synthetic account, on Luna at Medium, each against the build without it: the input read from the cache, the cost, the time, and what the step gives (for the reading: the points per paper, those found on their page, any set on a page the call did not read for). A way is kept only where what the step gives holds. The full 8-paper run is not made. All these runs together stay under $0.40.

## Governs or depends on

AN.33 (D27, D28; the second run's costs); AN.31 (the cache: cache_through, cache_also); AN.30

## Status

AGREED 2 Nov 2026 (D29). Probed and measured in small runs ($0.37 of the $0.40), the two largest papers included. 34b (33477786) and 34d (2c2f2f51) BUILT and pushed; on the largest papers what the readings found held, and looked better (column 7); APPLIED to the live server at the owner's word ("push to live server", 2 Nov 2026; one restart; the 12 saved conversations reopen unchanged; the live branch is the remote tip). 34a DROPPED and 34c NOT POSSIBLE: a call reads a cached opening only where its effort, its answer's schema and its instructions are those of the call that wrote it (column 7).

## Notes

AN.34 PIECES.
PROBE (invented text, a few cents at most): whether calls started at the same moment read a cache another call is writing, after what head start they do, and whether a cached opening is answered sooner.
34a [DROPPED, 2 Nov 2026: the second pass reasons at high, its reading at the step's own level, so it cannot read it] The second passes read their reading's prompt from the cache: the reading and its second pass marked at the same places; the text the model reads is unchanged.
34b One opening for every research call that is shown the file: the advocate's messages and the whole file, the same in every call, before the pages the call reads for (given after it, as now); the readings' instructions say so. The calls of one step then share one cache.
34c [NOT POSSIBLE, 2 Nov 2026: each of the answer's steps answers in its own schema, and several at their own effort, so none can read another's cache whatever the order] One opening for the answer's steps: the conversation and papers before each step's own instructions, so that the writer, the review, the repair and the take-up read one cache.
34d A head start for calls that share one opening: a request whose cached opening another request began writing less than 2 seconds before waits the rest of those 2 seconds, so that it reads the opening rather than writing it again (the adapter's; every step that starts calls together gains, the papers' readings and their settling most).
MEASURED IN EACH RUN: input, cached input, output, cost and seconds per step, against the same run on the build without the piece.

## Column 7

AN.34 PROBE, 2 Nov 2026 (invented text; 16 calls on Luna, $0.018): four calls with one fresh opening of about 23,500 tokens each time. Started together, 2 of the 4 read it and 2 wrote it; started 2 seconds after the first, 3 of 3 read it; 6 seconds after, 3 of 3; after the first had finished, 3 of 3. A call that wrote the opening cost $0.0030, one that read it $0.00025 (an unmarked call would cost about $0.0024). At this size a cached opening was not answered measurably sooner (1.3-2.2 seconds against 1.6-2.9 for the call that wrote it); time is to be measured on the papers.

SECOND PROBE, 2 Nov 2026 (invented text; 8 calls, $0.021): each time a call wrote a fresh opening of about 23,500 tokens and, once it was answered, a second call with the same opening and one thing changed was made. With the same effort, schema and instructions the second read all of it (23,526 tokens); at high after medium it wrote it again; with another answer schema it wrote it again; with other instructions it wrote it again. A call reads a cached opening only where its effort, its answer's schema and its instructions are those of the call that wrote it.
CONSEQUENCES. 34a DROPPED: a paper's second pass reasons at high and its reading at the step's own level, so it cannot read its reading's prompt from the cache (measured: the second passes read none of it), and marking for it cost a write and saved nothing. Running the second pass at its reading's level would let it, at the price of the care AN.33 chose for it - not done. 34c NOT POSSIBLE: the answer's steps (writer, review, repair, take-up, overview, cross-check) each answer in their own schema and several at their own effort, so no order of their instructions and material lets one read another's cache; each kind keeps its own, as now. The calls of one step share: the readings, the second passes among themselves, the settling calls, the transactions' readings.
34b BUILT (33477786): every research call shown the file opens with the advocate's messages and the whole file, its own pages among them, marked where that ends, before the pages it reads for (given after it, as before); the readings' instructions say so. 34d BUILT (2c2f2f51): a request whose opening another request began writing less than 2 seconds before - the same model, effort, answer schema, instructions and first marked part - waits the rest of them, or until that request is answered, whichever is sooner (the first small run found that a key without the effort and the schema let a later step take an earlier step's opening as written). Offline: 1,390 passed in the research and model-adapter tests (7 new).
SMALL RUNS (2 Nov 2026; papers 1 and 7 of the measured turn, 11 pages; Luna, Medium; synthetic account):
- Research stage, the build on the server: 26 calls, $0.084, about 9 minutes; input 221,754 tokens (1% from the cache); output 123,043, about 73% of the cost - on small papers the answers cost more than the reading. Reading: 77 points, all found on their page; the second passes added 9.
- Research stage, the new build (before the key's fix): 26 calls, $0.080, about 9 minutes; 7% of the input from the cache: of each step's two readings, the second read the opening the first wrote (6,538 and 6,336 tokens); the second passes wrote theirs (the key, since fixed). Reading: 70 points, 64 found on their page.
- Readings only (readings, second passes, settling): the server's build 74 points, 67 found, $0.020, 218 s; the new build 80 points, 79 found, $0.016, 180 s, and 85 points, 83 found, $0.020, 265 s (both read openings the run before had written within the cache's 30 minutes - 59-60% of their input - as a step's later calls do in one turn).
- Not found on their page, by run: the server's build 0 and 7; the new build 6, 1 and 2 - none of them on another paper: slips in long quotations, varying run to run on both builds. No sign that the new layout reads fewer points or places fewer. Time: no measurable change (the probe found a cached opening answered no sooner at 23,500 tokens).
ESTIMATE FOR THE 8-PAPER TURN (the second measuring run's 39 reading, second-pass, settling and transactions calls, each shown the whole file of about 30,000 tokens): each step's first call writes the file and the rest read it at a tenth of the price - about $0.08 less a turn on Luna (about 9%), about $0.8 on Terra and $1.6 on Sol; the head start adds at most about 2 seconds to each step whose calls start together.
SPENT on AN.34: $0.26 of the $0.40 (two probes $0.039; five small runs $0.219).
LARGEST PAPERS, 2 Nov 2026 (the owner: "Check the two largest papers first"; papers 4 and 5, 26 pages, each read in two stretches; the readings, their second passes and settling only; one run on each build):
- The server's build: 10 calls, $0.064, about 7 minutes; 1% of the input from the cache. two points fewer than the new build's; 16 not found on their page, 13 of those in the words of the other paper; the settling found 10 recorded elsewhere, 4 as listed and 5 clerical slips; the second passes added 30; 22 pairs of one paper's points are the same passage of the same kind.
- The new build: 10 calls, $0.048, about 4 minutes; 49% of the input from the cache (each step's first call wrote the file, about 21,500 tokens, and the rest read it). 177 points; all but 2 found on their page, those 2 in the other paper's words; the settling found 2 clerical slips; the second passes added 28; 9 pairs the same passage.
- Of the $0.016 between them about $0.006 is the cache; the rest is that the new build's run wrote less (58,379 tokens against 77,628). The time follows the writing and the settling (fewer points to settle).
- On these papers the new layout - the whole file, then the pages read for - took far fewer points from the other paper and listed fewer twice. One run each: what the readings found held, and looked better.
- Applying 34b and 34d to the server was refused by the session's permission check (a deploy to the running server): it awaits the owner's own word. SPENT on AN.34: $0.37 of the $0.40.
34b and 34d APPLIED, 2 Nov 2026 (owner: "push to live server"): after an idle check (no turn running, no matter file changed for about a day), one restart onto the new code (the server's health reports the new tree, ready); the 12 saved conversations reopen unchanged and their boards are drawn; the local branch set to the remote tip.
