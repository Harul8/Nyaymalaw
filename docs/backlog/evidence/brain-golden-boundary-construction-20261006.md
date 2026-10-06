# Boundary test construction and observed limits

The candidate `test_brain_golden_boundaries.py` contains 19 paired cases:
14 through authenticated public turns and the real atomic FileMatterStore,
and five through the owning production continuation reference validator.
It adds no production changes, API calls, browser calls or invented authority.

## Construction history

- `/tmp/nm-golden-boundaries-first.xml`: 15 passed, one failed. The failed replay
  supplied a new matter ID returned by the first request, whereas the original
  request had omitted that field. Production correctly refused this different
  offer under the same turn ID. This was a fixture contract error, not an NM bug.
- The test now replays exactly the original offer. No identity check was changed.
- `/tmp/nm-golden-boundaries-second.xml`: all initial 16 passed.
- `/tmp/nm-golden-boundaries-third.xml`: expanded 19 passed, including actual
  two-turn GS-15 correction and wholly unread required extraction.
- `/tmp/nm-golden-boundaries-final.xml`: 19 passed in 4.79 seconds. Ruff passed.
  The external test harness produced a marker warning because it loaded the
  repository conftest outside its usual root configuration; it was not a failure.

## New two-turn GS-15 qualification

The initial input includes only the exact curated `it is dated 15-4-1984` words,
the GS-17 legal examination quote, and exact GS-18 custody words. The second
input supplies the exact `sorry, 15-4-2024` correction with unchanged examination
and custody context. No date, actor or court finding was invented.

The correct-target case retires the actual saved date predecessor, saves the
2024 correction, preserves the custody record and acknowledges the exact effect.

The wrong-target case deliberately fabricates a false independent target-identity
ACCEPT: the date proposal is bound to the genuinely owned custody record rather
than the date record. Code blocks fulfillment of the requested date target and
leaves the 1984 date active. However, the false semantic identity judgment admits
retirement of the custody record and saves the date proposition against that
wrong lineage. This is labelled `semantic_dependency` / `gap_demonstrated`.
It must not be summarized as entirely prevented wrong-target work merely because
the false completion claim was blocked. The ownership/effect-completion checks
and semantic identity admission have different guarantees.

## Other deliberate semantic limit

The identical invented success prose is replaced under explicit pure record
acknowledgement delivery, while an incorrect semantic ACCEPT allows that prose
under substantive delivery despite the accurate unfinished code outcome.
That substantive case is also marked `gap_demonstrated`, not a prevention pass.

## Fail-closed and false-rejection neighbours

The suite also observes real save failure, lost-acknowledgement receipt lookup,
exact replay with zero additional calls, no fresh write for already-current state
or complete no-change review, declared empty metadata needing no retry, populated
contradictory metadata needing one correction, absent operation receipts blocking
performed claims, unrelated owned effects not completing the selected request,
and wholly unread required extraction stopping before a new saved turn/reply.

The direct five-case validator set rejects foreign record and legal source IDs,
assessment without checked law, and loss of a checked legal use owner, while
admitting its exact attributed factual neighbour. These cases do not constitute
legal reasoning verification or an atomic save trace.

Passing a fabricated oracle characterizes the exercised contract and its limits;
it does not establish live-model semantics, legal correctness or a measured
zero false-positive rate. Golden text is exact repository curated scenario input,
not freshly acquired judgment PDFs or twenty authentic client files.
