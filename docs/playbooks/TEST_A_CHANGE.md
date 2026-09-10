# Test a change

Use this playbook during Start and Build to design proof and record results.
Its Evidence Pack closes only against the complete reviewable implementation.

**Entry:** named acceptance criteria and a known source boundary. Build may be
`OPEN` while evidence accumulates. `VERIFIED` requires a closed Build Record and
all evidence required for the complete claim.

**Exit:** an Evidence Pack states PASS, FAIL, NOT RUN, STALE or BLOCKED for
every required evidence link. Test does not decide release.

## Quick card

1. Identify the tested build, changed promises and applicable evidence types.
2. Run the narrowest useful test, including the actual failure boundary.
3. Show that each critical control rejects its real planted counterexample.
4. Exercise the affected served journey and specialist evaluations when required
   and approved; record any missing evidence explicitly.
5. Complete the cumulative suite required for the claim against a coherent build.
6. Link exact results and unresolved limits; claim `VERIFIED` only when every
   required result is current and passing.

## 1. Freeze the claim and test population

Before running anything, record:

- the item, source fingerprint or revision under test;
- exact acceptance criteria;
- affected features, journey steps and professional standards;
- expected population and denominator;
- required evidence types;
- tests or scenarios expected to collect;
- planned negative controls;
- evidence made stale by the implementation.

Do not edit the tested tree during a cumulative gate. A gate that observes
different source states at different stages measures no coherent build.

For model or counsel evidence also record the relevant model/provider,
configuration, prompt, corpus, governing date and jurisdiction; the rubric and
sample population; and the reviewer, role and reservations. An independent
judge is a separately identified evaluator, not the tested model grading its
own output. A name or PASS typed into a JSON record is not itself evidence of
qualified review. BK-80 owns the remaining mechanical validation of these
records; until then the reviewer must inspect the underlying evidence.

## 2. Map each promise to the right evidence

| Evidence | Use it to prove | It cannot prove alone |
|---|---|---|
| Class A logic | Pure domain invariants without corpus or model | Served integration or professional quality |
| Class B structure/runtime | Produced state or output has required mechanical structure | Legal correctness or corpus coverage |
| Class C corpus | Corpus identity, content, coverage and retrieval properties | Quality of composed legal advice |
| Class D judgment | Rubric-scored legal/professional quality with an approved independent judge | Persistence, isolation or browser behaviour |
| Integration/persistence | API, composition root, encryption, idempotency, concurrency and recovery | End-to-end usability |
| Served journey | Real transport, browser, state continuity and recovery | Counsel-grade judgment by itself |
| Counsel review | Accuracy, judgment, questions, candour, remedy, strategy, communication and usability | Mechanical safety or production fitness |
| Production measurement | Actual latency, failure, correction and incident behaviour | Unobserved or unrepresented behaviour |

Require every evidence type implied by the change. Do not let the implementer
choose a weaker class merely because it is easier to run.

## 3. Prove the narrow rule

Run the smallest relevant tests first so failure is diagnosable.

- Assert the intended success state.
- Assert blocking or refusal at the exact gate and scope.
- Assert failure/recovery, not only error creation.
- Assert persisted state and served output agree.
- Assert the named test exists and collects.
- Assert the expected population was parsed and evaluated.

When a defect was fixed, phrase the invariant as the general rule rather than
the example that exposed it.

### 3.1 For a fix: prove transfer and preservation

**A fixed incident is not transfer proof.** Keep the original failing witness
as a regression, then test the declared causal family in distinct contexts
not used to select or tune the fix. Use held-out cases where practical; once
inspected and used for tuning, they are regressions, not unseen evidence.

Test the Start contract's meaning-preserving transformations, such as permitted
paraphrases, irrelevant document reordering or equivalent supported formats.
Assert the invariant, not identical wording. Test distinguishing boundaries
too: a material role, jurisdiction, governing date, consent, source-version or
evidence change may require a different result or continued refusal. Do not
declare two cases equivalent merely because their wording resembles each other.
Use property-based/generated inputs where suitable; reviewed expected outcomes
and legal applicability cannot be inferred from the generator itself.

Include both directions: the forbidden behaviour is refused **and** legitimate
behaviour still works. Test empty, partial, unsupported and unavailable states,
and controls that must remain refusing after the fix. Plant an actual violation
at the shared boundary and require the intended failure, not any exception.
For suspected incident branches, remove or vary the incidental trigger in an
isolated test and retain the general result; do not remove genuine rule data.

Reconcile discovered, applicable and exercised populations. Check affected
consumers and predeclared unrelated-behaviour witnesses: tenant isolation,
source fidelity, persistence/recovery, latency/cost or UI/export agreement as
the impact inventory requires. Run the applicable cumulative suites; one new
regression test is not a no-collateral-impact claim. Record before/after source,
prompt/configuration/model and data identities, including manual identity
comparison for inputs outside the runner's fingerprint. Preserve baseline
failures and explain each changed result. No unexplained regression, reduced
population, weakened assertion or threshold may be hidden by a green total.

These are semantic and behavioural obligations. Registry/keyword checks can
prove the obligation remains written; they cannot prove a product fix
generalises. Unexecuted integration, approved real-model, browser and counsel
evidence remain NOT_RUN, with owner and next action.

## 4. Make every critical control bite

For each critical gate, sweep or reconciliation rule:

1. start from a clean baseline;
2. mutate a field or path that exists;
3. assert the mutation changed the intended input;
4. run the real control;
5. require the specific expected complaint or refusal;
6. restore the clean input and prove it passes.

A mutation of a misspelled or nonexistent field proves nothing. A test that
fails for an unrelated reason has not proved the named control.

## 5. Prove boundaries and recovery

Add the checks applicable to the change:

- API and composition-root behaviour;
- commit-before-emit and audit failure;
- replay and idempotency, including first-turn creation;
- stale concurrent writes and selective re-derivation;
- restart before, during and after commit;
- timeout, cancellation, retry and partial completion;
- wrong role, matter, party, thread, version and recipient;
- encryption, isolation, secret separation, expiry and logout;
- malformed, hostile, unsupported or low-confidence input;
- accessibility, keyboard, focus and responsive widths;
- performance budgets and honest degraded service.

Exercise the failure at the boundary where it can occur. A domain unit test
does not prove the API or browser preserves the same rule.

## 6. Prove the journey

For every affected journey step, run all applicable paths through the served
product:

1. success;
2. blocking or refusal;
3. failure and recovery;
4. multi-turn loop or return to an earlier state;
5. reload/re-entry with persisted state;
6. role-specific permitted and refused behaviour.

Use the state produced by the preceding served interaction. Do not hand-author
inter-stage state. Capture enough artifact detail to diagnose the exact step
and visible result.

For Take the Brief, include retrieval-first questioning, typed and multimodal
input as applicable, correction, pause, cancellation, retry, resume and return
from Work the File or Advise.

## 7. Prove legal and professional quality

When a change can affect substantive legal propositions, retrieval, evidence
interpretation, question selection, reasoning, advice maturity, strategy,
reservations or professional authority:

- run representative golden matters covering favourable, adverse and ambiguous
  positions;
- verify governing date, jurisdiction, binding hierarchy, treatment,
  proposition and source locator;
- verify facts, evidence, burden, standard, adverse case and reservations;
- compare remedies, enforcement, cost, time and practical constraints;
- confirm advice maturity matches readiness;
- use an approved judge different from the model under test;
- obtain named senior-counsel review against every applicable PA criterion.

Record material counsel reservations as owned work. A judge score does not
replace counsel acceptance.

An ordinary interface-label or layout change does not automatically require
new legal judgment evidence. Establish at Start whether it can alter meaning
or professional behaviour. If it cannot, record why counsel evaluation does
not apply and still test the changed interaction. Existing mandatory criteria
continue to bind.

## 8. Run cumulative regression

After narrow proof passes, run the required cumulative gate:

- the new rule and its counterexample;
- all earlier Class-A invariants;
- all affected local integration tests;
- prior verified behaviours required at the feature or phase close;
- the relevant scenario/golden filters when approved;
- plan, traceability and generated-view checks.

No new green result may hide an earlier regression or a required test that did
not run.

The cumulative set may comprise separate suites against the same identified
candidate and relevant inputs; it need not be one process. Resolve a failure
with a relevant corrected rerun, preserving the earlier result and cause.
Do not carry evidence across changed inputs by assertion. Where the current
mechanism invalidates the whole source fingerprint, rerun its required gate;
selective carry-forward requires a supported scope/identity rule, not a manual
override. Narrow checks during Build need not repeat unaffected suites after
every edit.

## 9. Apply change-specific minimums

| Change type | Minimum additional proof |
|---|---|
| UI/interaction | Served browser; realistic empty, partial, long, error and restored states; keyboard/focus/responsive review |
| Model/prompt | Typed validation; representative real-model evaluation; independent judge; cost/latency; counsel review |
| Retrieval/corpus | Exact identity; governing date; coverage denominator; primary text/locator; NOT HELD vs HELD-NOT-FOUND vs NOT ASSESSED |
| Persistence/API | Atomic commit; replay; concurrency; restart; audit failure; served response matches reopened file |
| Voice/media/file | Format matrix; immutable source/hash; quarantine; locators/confidence; correction; cancel/retry/resume; privacy boundary |
| External action | Authority; approved version; attempt vs confirmation; failed/unknown transmission; recovery and resulting obligations |
| Plan/control | Lint; non-zero populations; bidirectional links; waves/dependencies; generated views current; negative fixture |

These are floors. Add evidence for the actual risk.

For document-only changes, verify authoritative sources, generated views and
changed obligations. A spelling or layout correction does not require new
product tests; a changed promise requires the proof that promise implies.

## 10. Interpret results honestly

Use only these meanings:

- `PASS`: the named evidence ran against the current source and met its rule.
- `FAIL`: it ran and did not meet the rule.
- `NOT RUN`: required evidence has not been executed.
- `STALE`: evidence predates a change capable of affecting it.
- `BLOCKED`: the run could not proceed because a named prerequisite or decision
  is unresolved.

Missing, failed, not-run, stale and blocked evidence all prevent the claim that
requires them. Report the denominator and explain unexplained results; do not
turn them into a blended pass percentage.

`NOT_APPLICABLE` is permitted only with a recorded, justified applicability
decision. It is not a way to avoid a failing or unavailable required check.
For a served report, inspect expected and actual scenario populations,
duplicates, completion and source identity as well as the individual PASS rows.
BK-80 tracks the automated report-validity checks still to be implemented.

## Approval boundaries

The ordinary per-task gate may run Class A and local non-judged tests. Golden,
served end-to-end scenario and Class-D judged runs require explicit approval
for the named bounded run. Long ingest, index, training or similar jobs are
prepared and reported, not started automatically.

Routine repository commands are documented in `CLAUDE.md`. The ordinary gate
is:

```text
python tools/backlog.py check
python tools/check.py
```

Do not add approval-only suites to an automatic path merely to make this stage
look complete.

## Stop here when

- an input capable of affecting the running gate changes, or the runner reports
  a changed source fingerprint;
- the expected population is zero, incomplete or unexplained;
- a required test does not exist, collect or exercise the intended path;
- a critical control cannot reject its counterexample;
- served-path state is hand-authored;
- legal output changed without required real-model or counsel evidence;
- a failure is dismissed as flaky without measured cause;
- only the incident passes, a transfer/boundary or unrelated witness regresses,
  or a claimed held-out case was used to tune the fix without disclosure;
- the implementation must change to continue the run.

Return to Build for implementation defects and Start for contract, scope,
authority or evidence-design defects. Mark affected results stale.

## Close Test

Test is closed only when all applicable statements are true:

- [ ] Source identity and expected population are recorded.
- [ ] Every atomic acceptance criterion has every required evidence result.
- [ ] Named tests exist and collect.
- [ ] Critical controls reject their counterexamples for the intended reason.
- [ ] Success, refusal and failure/recovery pass.
- [ ] Persistence, concurrency, retry and restart pass where relevant.
- [ ] Served journey and return loops pass where required.
- [ ] Real-model and legal evaluation pass where required.
- [ ] Named counsel review and reservations are recorded where required.
- [ ] Security, privacy, accessibility and performance evidence is current.
- [ ] Earlier verified behaviour passes cumulatively.
- [ ] No result is silently skipped, stale or based on an empty population.
- [ ] Failures and blocked evidence have owners and next actions.

### Evidence Pack

```text
Item / source identity:
Acceptance criterion → required evidence → result → reference:
Expected / parsed / evaluated population:
Negative control → actual mutation → expected and observed failure:
Fix only — original / distinct or held-out / transfer / boundary witnesses and results:
Fix only — discovered / applicable / exercised sites; unrelated behaviours and results:
Fix only — before/after identities / changed results / unexplained regressions:
Success / refusal / failure-recovery scenarios:
Persistence and served-path results:
Legal/model evaluation:
Counsel review and reservations:
Security/privacy/accessibility/performance evidence:
Cumulative regression result:
FAIL / NOT RUN / STALE / BLOCKED evidence and owner:
VERIFIED: yes / no, with exact claim supported:
```

**Handoff to Sign-off:** provide the Start Record, Build Record and Evidence
Pack. Sign-off decides the strongest claim the complete current evidence earns.

---

<!-- THE RULES THIS PLAYBOOK CARRIES. `docs/backlog/build_rules.json`
     is the registry; this manifest is how the card CLAIMS its rules.
     Dropping one now means deleting an id here, which lint refuses --
     because two rules were lost when the guide was split and nothing
     noticed. Do not edit by hand except to add a genuinely new rule
     to the registry first. -->
<!-- BUILD_RULES: BG-011 BG-015 BG-016 BG-054 BG-055 BG-056 BG-070 BG-071 BG-072 BG-073 BG-074 BG-080 -->
