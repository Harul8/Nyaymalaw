# Core-engine build evidence — 10 October 2026

The Advocate build plan owns status and scope; this file records linked evidence.
Owner resumed SEQ.1–SEQ.9, permits explicit nonblocking deferrals, and approved
one fresh $5 API development allowance. All paid work will use the shared ledger
`outputs/core-engine-build-20261010/api-budget.sqlite` with a $5 cap, including
restarts and repairs. No paid calls have been made for this build yet.

## SEQ.1 — exact conversation and receipts

Start READY: `conversation.py` owns canonical chat/request identity, full ordered
transcript assembly and immutable saved reply receipts. Existing FileMatterStore
owns sealed, version-checked atomic persistence. Public authentication remains
the caller's responsibility. Model/admitted legal work is outside this piece.
Pass: replay preserves exact words, roles, service notices and saved records/work;
one request saves once. Counterexamples: missing history, changed retry text,
wrong owner, concurrent writes, and uncertain persistence never become a new
empty history or successful effect claim. Recovery: same identity plus durable
receipt lookup; no provider calls or unconditional rewrite.

Reuse disclosed before implementation: private M1's owner-bound identity,
retry identity and receipt-lookup approach. No archived engine restored. Avoided
M1's chat-count/version equality, loss of displayed service text, null-chat retry
conflict and dependence on current stage implementations for old replay.

Build: one new production owner plus required source-layout registration.
Authentication checked before fresh commit and replay, and after confirmed save.
Chat sequence/tail integrity is independent of other matter version changes.

Evidence: `tests/test_core_conversation.py` — 16 passed against the real sealed
file store. Exercises legitimate neighbours and the counterexamples above,
including a saved response recovered after acknowledgement loss. No semantic
accuracy claim follows from these tests. Context adds zero model calls.

Conformance: mechanical prerequisite verified; SEQ.1 remains open until request
interpretation, shared correction/accounting and authenticated served integration
are implemented and exercised together. Browser/model acceptance is pending.

## Reference review retained for subsequent sequences

Read-only scans covered archived brains, Agentified NM, build guides and prior
source-reading evidence. Prefer live `retrieval.py` rank fusion, independent leg
failures, exact passage snapshots and context windows. Do not copy M1's lossy query
input or archived isolated-package reviewer. Natural grounded writing and one
whole-context independent review follow P10/S3. Court treatment must bind the
particular submitted proposition and the court's exact treatment, not a blanket
case or paragraph label.

SEQ.2 findings to resolve before promoting citation certainty: fuzzy one-party
name agreement; same-date/court merging; unassessed short quotations coexisting
with verified status; identity-index first-owner collision loss. No index rebuild
or changes to corpus content have occurred.
