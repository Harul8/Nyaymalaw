# Review repairs and live-batch preflight — 22 September 2026

Status: **partially implemented; first live browser matter under review**.
Base: `43f80a9` on `s0-foundations`, plus the uncommitted changes in this pass.
This is a diagnostic record, not Class-A promotion, release approval or counsel review.

## What changed

- DG-01: the scenario generator selects `Implementation Plan` by name. It
  validates unique required columns, non-empty populations, state/body agreement,
  and generated-file agreement. The workbook retains 91 planned features, 19
  executable subsets and 72 explicit executable-coverage gaps. Existing prose and
  historical scenarios are retained. The active sheet can remain Before Build.
- DG-02: `G-LIMITATION` now guards the proposed step rather than blocking an entire
  discussion. Unknown or conditional dates require a model assessment bound to the
  exact proposed step; dependent or ambiguous steps are refused. Independent
  evidence gathering remains available. A refused recomputation removes an older
  current recommendation, without erasing its historical transcript. This does
  **not** prove that the live classifier always judges dependence correctly.
- DG-08: 115 LB/OM requirements now have uniquely identified, faithful Requirement
  rows in Implementation Plan. Both directions and mapped content reconcile.
  Delivery, release assignment and acceptance are not inferred from this link.
- The workbook now reflects the already-approved public email/password registration,
  six-digit email confirmation and separate optional global OpenAI text permission.
  Original owner descriptions and historical columns are unchanged. Obsolete
  invitation-only wording was replaced only in the approved-current requirement.
- DG-10: opt-in evaluation configuration adds durable per-dispatch spending
  reservations. The approved pinned GPT-4o mini model is enforced. Retries require
  new reservations; failed/unknown calls keep their reservation after restart;
  returned usage is accounted before truncation/schema rejection. No prompts,
  secrets or response text enter the spending ledger. The 40-turn batch limit is
  also tracked manually across browser submissions; it is not a per-call count.

`diagnostics.json` is the dated update payload/evidence record for thirteen DIAGNOSTIC
rows in Before Build (249–261), not a second feature-status registry. DG-11 records
the repaired answer-order exception, DG-12 the compact header/composer and durable
receipt changes, and DG-13 the outstanding live reasoning findings.

## Verified locally

| Record | Population / result | What it does not establish |
| --- | --- | --- |
| `plan-reconciliation.xml` | 18 passed | Delivery or full scenario coverage |
| `limitation-local.xml` | 63 passed, 1 HARD-configuration skip | Live legal/classifier quality |
| `combined-focused.xml` | 173 passed | A fresh full Class-A gate |
| `final-focused.xml` | 45 passed, including the tenth spending test | Actual provider usage |
| `retained-bdd.xml` | 73 passed | A real interactive Chrome journey |
| `final-regression.xml` | 247 passed, 0 failed/errors/skips, 60.514 seconds | Full Class-A, live quality or professional sign-off |
| `dg11-after.xml` | 59 passed | Full legal-quality acceptance |
| `dg12-journey.xml` | 67 passed, 0 failed/errors/skips, 150.706 seconds | Live model judgment; these browser tests use controlled responses |

These populations overlap; do not add them together. The final consolidated run
is recorded separately in `final-regression.xml`. Ruff over the
changed application/generator/tests and `git diff --check` passed.

Earlier failed reports remain visible: `limitation-first.xml` includes fixture
construction/counterexample failures corrected during development;
`limitation-served.xml` includes an incorrect assertion that the public response
exposed an internal gate ID. The final served test instead checks the actual
response, private metrics and persisted recommendation/history. No test failure
has been relabelled a live-model observation.

Workbook QA reopened the saved file, compared all untouched values/styles, checked
sheet/freeze/table structure, ran scenario reconciliation and visually reviewed
rendered changed cells. The bundled spreadsheet editing package was unavailable;
the spreadsheet skill's permitted openpyxl fallback was used. The original backup
and previews are under `outputs/01a07b76-6b21-71f3-bb09-261f64617594/`.

Code Review Graph was queried first and incrementally refreshed without paid
embeddings. It identified a broad impact radius around the turn engine/model
adapter. Direct source inspection and focused tests supplement the graph; its
keyword fallback and treatment of untracked files are not complete semantic proof.

## Live preflight — actual Chrome, not the scripted preview

- User-owned Chrome tab at `http://localhost:8071/` is signed in. Existing matters
  were not modified. This is not the older in-app preview at port 8095.
- The owner explicitly confirmed account-wide OpenAI text sharing. It was enabled
  through Profile > AI data sharing and verified saved. Raw media and other
  providers remain outside this permission and evaluation.
- Current server is the existing Python 3.11 NM process. A read-only composition
  preflight with that interpreter found the real corpus/provisions/authorities
  readable and the routine model pinned to `gpt-4o-mini-2024-07-18`. It also
  reported Telangana coverage unmet. Readability is not coverage or legal accuracy.
- The verified NM server was restarted with the existing encryption key and
  persistent evaluation ledger. GPT-5.1 and embedding dispatch remain refused.
- Two real Chrome submissions on one synthetic matter, including a same-receipt
  retry, produced 26 measured GPT-4o mini responses: 44,519 input and 3,897 output
  tokens, estimated USD0.009025. No unknown reservations at this checkpoint.
  Browser matters accepted complete: **0 of 5**. See `live-browser.md` for the
  actual failure, retry and remaining quality findings; no live-quality PASS.

## Resume boundary

Update for DG-15/16: reasoning and communication implementation and live results
are recorded in [the focused record](reasoning-communication.md). Current cumulative
evaluation is five browser submissions (including the original retry), 42 measured
GPT-4o mini responses, 73,877 input and 4,834 output tokens, USD0.014001 conservative
ledger charge. Three submissions in this increment verified the acknowledgement
repair and substantive routing. Four committed turns were inspected in History.
DG-13 and acceptance of all five matters remain open. Current service was restarted
on the same port with the same account storage and persistent budget ledger.

DG-14 presentation is implemented: one matter board, profile at the desktop
sidebar foot, full-height right conversation and ordered paragraphs rather than
internal labels. Actual Chrome and the selected regression population are
recorded in `dg14-ui.md`. This changes presentation, not the stored wording of
earlier answers or the unresolved DG-13 assessment. No additional paid model
call was made for the UI verification.

1. Continue matter 1 from DG-13; do not ask for the already-recorded sharing approval
   again unless its scope changes. Do not substitute an account or bypass consent.
2. When code changes, restart only the verified NM listener on 8071, with its existing configuration
   and encryption key, plus `NM_EVAL_BUDGET_FILE` pointing to the persistent
   `.nm/evaluations/legal-brain-20260922.sqlite` and `NM_EVAL_MAX_USD=25`.
   Keep any existing ledger; never reset it to obtain more allowance.
3. Reload Chrome and reopen SYNTHETIC LIVE 01 through the ordinary UI. Keep real
   user matters out. Do not recreate a matter or resend without its original receipt.
4. Inspect each genuine reply, cited text and opened source, facts vs allegations,
   limitation premise, adverse position, follow-up question and changed-fact
   reassessment. Record provider response IDs/token usage and all submitted turns.
5. Log each defect as a new DIAGNOSTIC in Before Build before making a generalized
   fix. Recheck the failed behaviour, then reload/reopen saved history. Advance to
   the next matter only after that matter's material issues are addressed.
6. Stop at 40 cumulative browser turns or the approved USD25 limit. Report actual
   measured usage, unknown reservations and remaining scope separately.

## Review findings still open

- DG-03: 92 served route declarations counted; missing surface families need
  explicit ownership, route-population enforcement and real UI proof. Literal
  frontend strings are not sufficient evidence of either reachability or absence.
- DG-04: incident domain/assurance code does not establish a production operational
  caller or incident response readiness.
- DG-05: account deletion/rights/profile/email-change is a broader uncompleted
  packet, not satisfied by the existing registration and session routes.
- DG-06: approved versioned terms and a validated Telugu translation remain open.
  No approval or retrospective consent is invented.
- DG-07: matter memory already exists (`domain/summary.py`, assembled from persisted
  state); the review's vocabulary-based inference was too broad. Multi-turn,
  correction, isolation and reopening quality still need the live evaluation.
- Protected-identity coverage, complete E–H route/feature acceptance mapping,
  production latency targets and model qualification are not closed by this pass.

Qualified legal review remains explicitly deferred. **BK-85-AC3 stays NOT_RUN.**
No full Class-A run, evidence promotion, commit or push was performed in this pass.
