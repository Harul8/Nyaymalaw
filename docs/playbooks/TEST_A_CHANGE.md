# Test a change

Use this playbook after Build is closed. It may also be opened during Start and
Build to design or run narrow proof, but it closes only against the reviewable
implementation.

**Entry:** closed Start and Build records, atomic acceptance criteria and an
implementation whose source boundary will remain stable during the gate.

**Exit:** an Evidence Pack states PASS, FAIL, NOT RUN, STALE or BLOCKED for
every required evidence link. Test does not decide release.

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

When law, retrieval, evidence, prompt, model, reasoning or counsel-facing
output can change:

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

- the source changes while a cumulative gate is running;
- the expected population is zero, incomplete or unexplained;
- a required test does not exist, collect or exercise the intended path;
- a critical control cannot reject its counterexample;
- served-path state is hand-authored;
- legal output changed without required real-model or counsel evidence;
- a failure is dismissed as flaky without measured cause;
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
<!-- BUILD_RULES: BG-011 BG-015 BG-016 BG-054 BG-055 BG-056 BG-070 BG-071 BG-072 BG-073 BG-074 -->
